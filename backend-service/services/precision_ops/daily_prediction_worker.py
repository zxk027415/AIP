"""
precision_ops/daily_prediction_worker.py — 每日预测模拟 Worker

加速模拟生产环境的每日滚动预测循环：
  - 每隔 interval_seconds 推进一天
  - 生产模型 + 预上线模型同时做当天预测
  - 回填真值 → 重算滚动 MAPE → 检查预上线毕业

正常生产中这是每天凌晨跑一次，这里为了 demo 加速为每 30s 一天。

使用方式:
  worker = DailyPredictionWorker(slot="default")
  worker.start()   # 后台线程启动
  worker.stop()    # 停止

或通过 API 启动/停止。
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from services.precision_ops.utils import (
    BASE_DATA_DIR,
    _atomic_write_json,
    ensure_data_dir,
    load_json_safe,
    now_iso,
)
from services.precision_ops.rolling_forecast_experiment import (
    _build_features,
    _build_features_extended,
    _train_and_predict_one_day,
    _calc_mape,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker 状态（模块级单例）
# ---------------------------------------------------------------------------
_worker_instance: Optional["DailyPredictionWorker"] = None
_worker_lock = threading.Lock()


def get_worker() -> Optional["DailyPredictionWorker"]:
    return _worker_instance


class DailyPredictionWorker:
    """
    模拟每日预测的后台 worker。

    每隔 interval_seconds 推进一天:
      1. 用截止 T-1 的数据训练生产模型 + 预上线模型
      2. 预测 T 日 96 个点
      3. 用 T 日真值计算 MAPE
      4. 更新 accuracy_metrics 和 prelaunch_queue
      5. 检查预上线是否满足毕业条件
    """

    def __init__(
        self,
        slot: str = "default",
        csv_path: str = "",
        start_date: str = "2026-04-01",
        observation_days: int = 7,
        train_days: int = 60,
        interval_seconds: float = 30.0,
        production_n_estimators: int = 200,
        prelaunch_n_estimators: int = 500,
        graduate_tolerance_pct: float = 5.0,
    ):
        self.slot = slot
        self.start_date = start_date
        self.observation_days = observation_days
        self.train_days = train_days
        self.interval_seconds = interval_seconds
        self.production_n_estimators = production_n_estimators
        self.prelaunch_n_estimators = prelaunch_n_estimators
        self.graduate_tolerance_pct = graduate_tolerance_pct

        # 数据
        if not csv_path:
            from pathlib import Path
            csv_path = str(
                Path(__file__).resolve().parent.parent.parent
                / "datasets" / "load_true_weihai_260415.csv"
            )
        self.csv_path = csv_path
        self._df: Optional[pd.DataFrame] = None

        # 状态
        self.current_day: int = 0  # 已完成的天数
        self.daily_results: List[Dict[str, Any]] = []
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # 控制
    # ------------------------------------------------------------------

    def start(self) -> Dict[str, Any]:
        """启动 worker（后台线程）"""
        global _worker_instance
        if self.running:
            return {"status": "already_running", "current_day": self.current_day}

        self._load_data()
        self._init_state()
        self._stop_event.clear()
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        with _worker_lock:
            _worker_instance = self

        logger.info(
            "DailyPredictionWorker started: slot=%s start=%s interval=%ss",
            self.slot, self.start_date, self.interval_seconds,
        )
        return {"status": "started", "current_day": 0, "total_days": self.observation_days}

    def stop(self) -> Dict[str, Any]:
        """停止 worker"""
        global _worker_instance
        self._stop_event.set()
        self.running = False
        with _worker_lock:
            _worker_instance = None
        return {"status": "stopped", "current_day": self.current_day}

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        start_dt = datetime.fromisoformat(self.start_date)
        current_sim_date = (start_dt + timedelta(days=self.current_day)).strftime("%Y-%m-%d")
        return {
            "running": self.running,
            "current_day": self.current_day,
            "total_days": self.observation_days,
            "current_sim_date": current_sim_date,
            "daily_results": self.daily_results,
            "completed": self.current_day >= self.observation_days,
            "interval_seconds": self.interval_seconds,
        }

    # ------------------------------------------------------------------
    # 内部循环
    # ------------------------------------------------------------------

    def _run_loop(self):
        """后台循环: 每 interval_seconds 执行一天"""
        while not self._stop_event.is_set() and self.current_day < self.observation_days:
            try:
                self._execute_one_day()
            except Exception as exc:
                logger.error("Worker day %d failed: %s", self.current_day, exc, exc_info=True)

            # 等待下一天（可被 stop 打断）
            self._stop_event.wait(self.interval_seconds)

        self.running = False
        logger.info("DailyPredictionWorker finished: %d/%d days", self.current_day, self.observation_days)

    def _execute_one_day(self):
        """执行单天的训练+预测+评估"""
        start_dt = datetime.fromisoformat(self.start_date)
        predict_date = start_dt + timedelta(days=self.current_day)
        day_label = predict_date.strftime("%Y-%m-%d")

        logger.info("Worker executing day %d: %s", self.current_day + 1, day_label)

        # 生产模型: 基础特征 + 200 棵
        prod_pred, prod_true, _ = _train_and_predict_one_day(
            self._df, predict_date,
            n_estimators=self.production_n_estimators,
            train_days=self.train_days,
            use_extended_features=False,
        )

        # 预上线模型: 扩展特征 + 500 棵
        pre_pred, pre_true, _ = _train_and_predict_one_day(
            self._df, predict_date,
            n_estimators=self.prelaunch_n_estimators,
            train_days=self.train_days,
            use_extended_features=True,
        )

        prod_mape = _calc_mape(prod_pred, prod_true)
        pre_mape = _calc_mape(pre_pred, pre_true)

        day_result = {
            "date": day_label,
            "day_number": self.current_day + 1,
            "production_mape": round(prod_mape, 4) if prod_mape else None,
            "prelaunch_mape": round(pre_mape, 4) if pre_mape else None,
            "points": len(prod_pred),
            "winner": (
                "prelaunch" if (pre_mape and prod_mape and pre_mape < prod_mape)
                else "production"
            ),
        }
        self.daily_results.append(day_result)
        self.current_day += 1

        logger.info(
            "  Day %d done: prod=%.4f%% pre=%.4f%% winner=%s",
            self.current_day, prod_mape or 0, pre_mape or 0, day_result["winner"],
        )

        # 更新持久化状态
        self._update_precision_ops_state()

    def _update_precision_ops_state(self):
        """每天执行后更新 accuracy_metrics 和 prelaunch_queue"""
        ensure_data_dir(self.slot)
        start_dt = datetime.fromisoformat(self.start_date)

        prod_mapes = [r["production_mape"] for r in self.daily_results if r["production_mape"]]
        pre_mapes = [r["prelaunch_mape"] for r in self.daily_results if r["prelaunch_mape"]]
        avg_prod = float(np.mean(prod_mapes)) if prod_mapes else 0
        avg_pre = float(np.mean(pre_mapes)) if pre_mapes else 0

        eval_date = (start_dt + timedelta(days=self.current_day)).isoformat()

        PROD_WF = "xgboost-200-baseline"
        PRE_WF = "xgboost-500-extended"

        # accuracy_metrics
        _atomic_write_json(BASE_DATA_DIR / self.slot / "accuracy_metrics.json", {
            "slot": self.slot,
            "evaluation_window_days": self.observation_days,
            "metrics": {
                PROD_WF: {
                    "rolling_mape": round(avg_prod, 4),
                    "rolling_mae": 0,
                    "valid_cycle_count": self.current_day,
                    "total_cycle_count": self.current_day,
                    "last_evaluated_at": eval_date,
                    "status": "active",
                },
                PRE_WF: {
                    "rolling_mape": round(avg_pre, 4),
                    "rolling_mae": 0,
                    "valid_cycle_count": self.current_day,
                    "total_cycle_count": self.current_day,
                    "last_evaluated_at": eval_date,
                    "status": "active",
                },
            },
            "updated_at": now_iso(),
        })

        # prelaunch_queue
        queue = load_json_safe(BASE_DATA_DIR / self.slot / "prelaunch_queue.json", default=[])
        for item in queue:
            if item.get("status") == "observing":
                item["current_rolling_mape"] = round(avg_pre, 4)
                item["production_rolling_mape"] = round(avg_prod, 4)
                item["evaluated_cycles"] = self.current_day

                # 检查是否满足毕业条件（观察天数满）
                if self.current_day >= self.observation_days:
                    threshold = avg_prod * (1 + self.graduate_tolerance_pct / 100)
                    if avg_pre <= threshold:
                        item["status"] = "graduated"
                        item["graduated_at"] = now_iso()
                        item["graduate_reason"] = (
                            f"auto: {self.current_day}d 观察完成, "
                            f"prelaunch_mape={avg_pre:.4f}% ≤ "
                            f"threshold={threshold:.4f}%"
                        )
                        logger.info("Prelaunch auto-graduated: mape=%.4f <= %.4f", avg_pre, threshold)
                    else:
                        item["status"] = "failed"
                        item["failed_at"] = now_iso()
                        item["fail_reason"] = (
                            f"auto: {self.current_day}d 观察完成, "
                            f"prelaunch_mape={avg_pre:.4f}% > "
                            f"threshold={threshold:.4f}%"
                        )
                        logger.info("Prelaunch auto-failed: mape=%.4f > %.4f", avg_pre, threshold)

        _atomic_write_json(BASE_DATA_DIR / self.slot / "prelaunch_queue.json", queue)

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def _load_data(self):
        """加载 CSV 数据"""
        df = pd.read_csv(self.csv_path)
        df["record_time"] = pd.to_datetime(df["record_time"])
        df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
        df.columns = ["timestamp", "load"]
        df = df.sort_values("timestamp").reset_index(drop=True)
        self._df = df

    def _init_state(self):
        """初始化精度运营状态"""
        ensure_data_dir(self.slot)
        start_dt = datetime.fromisoformat(self.start_date)

        PROD_WF = "xgboost-200-baseline"
        PROD_TAG = "production-xgb200"
        PRE_WF = "xgboost-500-extended"
        PRE_TAG = "prelaunch-xgb500-ext"
        CAND_ID = "sim-rolling-forecast-001"

        # version_registry
        _atomic_write_json(BASE_DATA_DIR / self.slot / "version_registry.json", {
            "slot": self.slot,
            "versions": [
                {
                    "workflow_id": PROD_WF,
                    "version_tag": PROD_TAG,
                    "status": "production",
                    "slot": self.slot,
                    "baseline_mape": None,
                    "registered_at": (start_dt - timedelta(days=7)).isoformat(),
                    "source_run_id": None,
                    "source_candidate_id": None,
                },
                {
                    "workflow_id": PRE_WF,
                    "version_tag": PRE_TAG,
                    "status": "shadow",
                    "slot": self.slot,
                    "baseline_mape": None,
                    "registered_at": start_dt.isoformat(),
                    "source_run_id": None,
                    "source_candidate_id": CAND_ID,
                },
            ],
            "max_shadow_versions": 5,
        })

        # prelaunch_queue
        _atomic_write_json(BASE_DATA_DIR / self.slot / "prelaunch_queue.json", [{
            "id": f"prelaunch-worker-{CAND_ID[:8]}",
            "candidate_id": CAND_ID,
            "workflow_id": PRE_WF,
            "version_tag": PRE_TAG,
            "slot": self.slot,
            "status": "observing",
            "started_at": start_dt.isoformat(),
            "observation_days": self.observation_days,
            "graduate_tolerance_pct": self.graduate_tolerance_pct,
            "source_run_id": None,
            "baseline_mape_at_entry": None,
            "current_rolling_mape": None,
            "production_rolling_mape": None,
            "evaluated_cycles": 0,
            "graduated_at": None,
            "failed_at": None,
            "cancelled_at": None,
            "note": f"定时滚动预测: 每 {self.interval_seconds}s 推进一天, 共 {self.observation_days} 天",
        }])

        # 清空 accuracy_metrics
        _atomic_write_json(BASE_DATA_DIR / self.slot / "accuracy_metrics.json", {
            "slot": self.slot,
            "evaluation_window_days": self.observation_days,
            "metrics": {},
            "updated_at": now_iso(),
        })

        # 重置内部状态
        self.current_day = 0
        self.daily_results = []
