"""
precision_ops/accuracy_tracker.py — 精度跟踪器

提供：
  - RollingMetrics  : 滚动精度指标 TypedDict
  - AccuracyTracker : 精度计算、滚动窗口维护、排行榜

存储路径：{BASE_DATA_DIR}/{slot}/accuracy_metrics.json

JSON 结构：
{
  "slot": "default",
  "evaluation_window_days": 7,
  "metrics": {
    "workflow-id": {
      "rolling_mape": 4.12,
      "rolling_mae": 15.3,
      "valid_cycle_count": 7,
      "total_cycle_count": 8,
      "last_evaluated_at": "2026-06-08T08:00:00+00:00",
      "status": "active"
    }
  },
  "updated_at": "2026-06-08T08:00:00+00:00"
}
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from typing import TypedDict
except ImportError:  # Python < 3.8
    from typing_extensions import TypedDict  # type: ignore

from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled, _parse_iso
from services.precision_ops.utils import (
    BASE_DATA_DIR,
    _atomic_write_json,
    ensure_data_dir,
    load_json_safe,
    now_iso,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDict
# ---------------------------------------------------------------------------

class RollingMetrics(TypedDict):
    """
    RollingMetrics — 单版本滚动精度指标快照

    字段说明（英文 — 中文）：
      rolling_mape        — 滚动 MAPE（%），越低越好
      rolling_mae         — 滚动 MAE（绝对误差均值）
      valid_cycle_count   — 有效周期数（覆盖率 ≥ 90% 的周期）
      total_cycle_count   — 总周期数（含超时/失败/低覆盖率的周期）
      last_evaluated_at   — 最后评估时间（ISO 8601 字符串）
      status              — "active"（数据充分）| "insufficient_data"（数据不足）
    """

    rolling_mape: float
    rolling_mae: float
    valid_cycle_count: int
    total_cycle_count: int
    last_evaluated_at: str
    status: str


# ---------------------------------------------------------------------------
# AccuracyTracker
# ---------------------------------------------------------------------------

class AccuracyTracker:
    """
    AccuracyTracker — 精度指标计算、滚动窗口维护、排行榜

    存储路径：{BASE_DATA_DIR}/{slot}/accuracy_metrics.json

    使用方式（两种均可）：

        # 构造时注入 PredictionStore
        tracker = AccuracyTracker(prediction_store=store)
        tracker.evaluate_cycle("default", "cycle-001")

        # 方法参数注入（refresh_all_metrics）
        tracker = AccuracyTracker()
        tracker.refresh_all_metrics("default", 7, prediction_store=store)

    :param prediction_store: PredictionStore 实例；evaluate_cycle 使用；
                             不传则仅支持 refresh_all_metrics（显式传参）。
    """

    def __init__(self, prediction_store: Optional[Any] = None) -> None:
        """
        :param prediction_store: PredictionStore 实例（可选）。
                                 显式传入，不在内部创建，方便测试隔离。
        """
        self._prediction_store = prediction_store

    # ------------------------------------------------------------------
    # 每周期评估
    # ------------------------------------------------------------------

    def evaluate_cycle(
        self,
        slot: str,
        cycle_id: str,
        min_valid_cycles: int = 3,
    ) -> None:
        """
        评估指定预测周期，更新 accuracy_metrics.json。

        流程：
        1. 从 accuracy_metrics.json 读取已知 workflow_id 列表
        2. 对每个 workflow，通过 PredictionStore.get_predictions_in_window
           获取近 30 天内的预测记录，再按 prediction_cycle_id 过滤
        3. 计算覆盖率：evaluated 记录数 / 总记录数 ≥ 90% 才计算精度
        4. 计算 MAPE（排除 actual=0 的点）和 MAE（包含 actual=0 的点）
        5. 更新 valid_cycle_count / total_cycle_count / status，原子写入

        :param slot:             槽位名称（分区键）
        :param cycle_id:         预测周期 ID
        :param min_valid_cycles: 有效周期数达到此值才标记 status=active
        :raises ValueError:      prediction_store 未注入时抛出
        """
        if self._prediction_store is None:
            raise ValueError(
                "evaluate_cycle 需要 PredictionStore；"
                "请在构造时传入 prediction_store 参数"
            )

        metrics_path = BASE_DATA_DIR / slot / "accuracy_metrics.json"
        data = load_json_safe(metrics_path, default={})
        metrics_dict: Dict[str, Any] = data.get("metrics", {})

        if not metrics_dict:
            logger.warning(
                "evaluate_cycle: slot=%s 的 accuracy_metrics.json 中没有已知 workflow，跳过",
                slot,
            )
            return

        # 使用近 30 天作为查询窗口，保证能覆盖近期所有周期
        now_dt = datetime.now(tz=timezone.utc)
        window_start = (now_dt - timedelta(days=30)).isoformat()
        window_end = now_dt.isoformat()

        updated = False

        for workflow_id in list(metrics_dict.keys()):
            # 获取时间窗口内的所有记录，再按 cycle_id 过滤
            try:
                all_records = self._prediction_store.get_predictions_in_window(
                    slot, workflow_id, window_start, window_end
                )
            except Exception as exc:
                logger.warning(
                    "evaluate_cycle: 查询 slot=%s workflow=%s 失败: %s",
                    slot, workflow_id, exc,
                )
                continue

            cycle_records = [
                r for r in all_records
                if r.get("prediction_cycle_id") == cycle_id
            ]

            if not cycle_records:
                continue

            current: Dict[str, Any] = metrics_dict.get(workflow_id, {})
            new_total = current.get("total_cycle_count", 0) + 1

            # 覆盖率检查
            total_count = len(cycle_records)
            evaluated_count = sum(
                1 for r in cycle_records
                if r.get("actual_value") is not None
            )
            coverage = evaluated_count / total_count if total_count > 0 else 0.0

            if coverage < 0.9:
                logger.info(
                    "evaluate_cycle: slot=%s workflow=%s cycle=%s 覆盖率=%.2f < 0.9，跳过精度计算",
                    slot, workflow_id, cycle_id, coverage,
                )
                metrics_dict[workflow_id] = {
                    **current,
                    "total_cycle_count": new_total,
                }
                updated = True
                continue

            # MAPE：排除 actual=0 的点
            mape_records = [
                r for r in cycle_records
                if r.get("actual_value") is not None
                and r.get("actual_value") != 0.0
            ]
            cycle_mape: Optional[float] = None
            if mape_records:
                errors = [
                    abs(r["predicted_value"] - r["actual_value"]) / abs(r["actual_value"])
                    for r in mape_records
                ]
                cycle_mape = sum(errors) / len(errors) * 100

            # MAE：包含 actual=0 的点
            mae_records = [
                r for r in cycle_records
                if r.get("actual_value") is not None
            ]
            cycle_mae: Optional[float] = None
            if mae_records:
                abs_errors = [
                    abs(r["predicted_value"] - r["actual_value"])
                    for r in mae_records
                ]
                cycle_mae = sum(abs_errors) / len(abs_errors)

            new_valid = current.get("valid_cycle_count", 0) + 1
            status = "active" if new_valid >= min_valid_cycles else "insufficient_data"

            metrics_dict[workflow_id] = {
                **current,
                "rolling_mape": cycle_mape
                    if cycle_mape is not None
                    else current.get("rolling_mape", 0.0),
                "rolling_mae": cycle_mae
                    if cycle_mae is not None
                    else current.get("rolling_mae", 0.0),
                "valid_cycle_count": new_valid,
                "total_cycle_count": new_total,
                "last_evaluated_at": now_iso(),
                "status": status,
            }
            updated = True

        if updated:
            ensure_data_dir(slot)
            payload = {
                "slot": slot,
                "evaluation_window_days": data.get("evaluation_window_days", 7),
                "metrics": metrics_dict,
                "updated_at": now_iso(),
            }
            _atomic_write_json(metrics_path, payload)

    # ------------------------------------------------------------------
    # 滚动指标计算（纯函数）
    # ------------------------------------------------------------------

    def compute_rolling_mape(
        self,
        records: List[dict],
        window_days: int,
    ) -> Optional[float]:
        """
        计算滚动 MAPE（Mean Absolute Percentage Error）。

        过滤规则：
        - evaluated_at 不为 None（已回填实际值）
        - actual_value 不为 0（排除零值，避免除零）
        - forecast_timestamp 在 [now - window_days, now] 范围内

        :param records:     PredictionStore.get_predictions_in_window 返回的记录列表
        :param window_days: 评估窗口天数
        :return: MAPE（%），无有效点时返回 None
        """
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=window_days)
        ).isoformat()
        now_str = datetime.now(tz=timezone.utc).isoformat()

        valid = [
            r for r in records
            if r.get("evaluated_at") is not None
            and r.get("actual_value") is not None
            and r.get("actual_value") != 0.0
            and r.get("forecast_timestamp") is not None
            and cutoff <= r["forecast_timestamp"] <= now_str
        ]

        if not valid:
            return None

        errors = [
            abs(r["predicted_value"] - r["actual_value"]) / abs(r["actual_value"])
            for r in valid
        ]
        return sum(errors) / len(errors) * 100

    def compute_rolling_mae(
        self,
        records: List[dict],
        window_days: int,
    ) -> Optional[float]:
        """
        计算滚动 MAE（Mean Absolute Error）。

        过滤规则与 compute_rolling_mape 相同，但不排除 actual_value=0 的点。

        :param records:     PredictionStore.get_predictions_in_window 返回的记录列表
        :param window_days: 评估窗口天数
        :return: MAE，无有效点时返回 None
        """
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=window_days)
        ).isoformat()
        now_str = datetime.now(tz=timezone.utc).isoformat()

        valid = [
            r for r in records
            if r.get("evaluated_at") is not None
            and r.get("actual_value") is not None
            and r.get("forecast_timestamp") is not None
            and cutoff <= r["forecast_timestamp"] <= now_str
        ]

        if not valid:
            return None

        abs_errors = [
            abs(r["predicted_value"] - r["actual_value"])
            for r in valid
        ]
        return sum(abs_errors) / len(abs_errors)

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get_rolling_metrics(
        self,
        slot: str,
        workflow_id: str,
    ) -> Optional[RollingMetrics]:
        """
        读取指定版本的滚动精度指标。

        :param slot:        槽位名称（分区键）
        :param workflow_id: 工作流模板 ID
        :return: RollingMetrics TypedDict，或 None（版本不存在）
        """
        metrics_path = BASE_DATA_DIR / slot / "accuracy_metrics.json"
        data = load_json_safe(metrics_path, default={})
        metrics_dict = data.get("metrics", {})

        entry = metrics_dict.get(workflow_id)
        if entry is None:
            return None

        return RollingMetrics(
            rolling_mape=float(entry.get("rolling_mape", 0.0)),
            rolling_mae=float(entry.get("rolling_mae", 0.0)),
            valid_cycle_count=int(entry.get("valid_cycle_count", 0)),
            total_cycle_count=int(entry.get("total_cycle_count", 0)),
            last_evaluated_at=str(entry.get("last_evaluated_at", "")),
            status=str(entry.get("status", "insufficient_data")),
        )

    # ------------------------------------------------------------------
    # 排行榜
    # ------------------------------------------------------------------

    def get_leaderboard(self, slot: str) -> List[dict]:
        """
        返回精度排行榜。

        规则：
        - 排除 status=insufficient_data 的版本
        - 按 rolling_mape 升序排列
        - rolling_mape 差异 < 0.0001 时按 valid_cycle_count 降序排列
        - 每项包含 workflow_id + RollingMetrics 的所有字段

        :param slot: 槽位名称（分区键）
        :return: 排行榜列表
        """
        metrics_path = BASE_DATA_DIR / slot / "accuracy_metrics.json"
        data = load_json_safe(metrics_path, default={})
        metrics_dict: Dict[str, Any] = data.get("metrics", {})

        board = []
        for workflow_id, entry in metrics_dict.items():
            if entry.get("status") == "insufficient_data":
                continue
            board.append({
                "workflow_id": workflow_id,
                "rolling_mape": float(entry.get("rolling_mape", 0.0)),
                "rolling_mae": float(entry.get("rolling_mae", 0.0)),
                "valid_cycle_count": int(entry.get("valid_cycle_count", 0)),
                "total_cycle_count": int(entry.get("total_cycle_count", 0)),
                "last_evaluated_at": str(entry.get("last_evaluated_at", "")),
                "status": str(entry.get("status", "insufficient_data")),
            })

        board.sort(
            key=lambda x: (
                round(x["rolling_mape"] / 0.0001) * 0.0001,  # 差异 < 0.0001 视为相同
                -x["valid_cycle_count"],                       # 相同 MAPE 时 valid_cycle_count 降序
            )
        )

        return board

    # ------------------------------------------------------------------
    # 全量刷新
    # ------------------------------------------------------------------

    def refresh_all_metrics(
        self,
        slot: str,
        window_days: int,
        prediction_store: Any,
        min_valid_cycles: int = 3,
    ) -> None:
        """
        对 accuracy_metrics.json 中所有版本重新计算滚动指标。

        使用 PredictionStore 从 SQLite 拉取窗口内全量记录，
        调用 compute_rolling_mape / compute_rolling_mae 重新计算，
        更新 status（valid_cycle_count < min_valid_cycles → insufficient_data），
        更新 last_evaluated_at，原子写入。

        :param slot:             槽位名称（分区键）
        :param window_days:      评估窗口天数
        :param prediction_store: PredictionStore 实例（显式传参，方便测试）
        :param min_valid_cycles: 有效周期数阈值
        """
        metrics_path = BASE_DATA_DIR / slot / "accuracy_metrics.json"
        data = load_json_safe(metrics_path, default={})
        metrics_dict: Dict[str, Any] = data.get("metrics", {})

        if not metrics_dict:
            logger.info("refresh_all_metrics: slot=%s 无已知 workflow，跳过", slot)
            return

        now_dt = datetime.now(tz=timezone.utc)
        window_start = (now_dt - timedelta(days=window_days)).isoformat()
        window_end = now_dt.isoformat()
        evaluated_at = now_iso()

        for workflow_id, entry in metrics_dict.items():
            try:
                records = prediction_store.get_predictions_in_window(
                    slot, workflow_id, window_start, window_end
                )
            except Exception as exc:
                logger.warning(
                    "refresh_all_metrics: 查询 slot=%s workflow=%s 失败: %s",
                    slot, workflow_id, exc,
                )
                continue

            rolling_mape = self.compute_rolling_mape(records, window_days)
            rolling_mae = self.compute_rolling_mae(records, window_days)

            valid_count = int(entry.get("valid_cycle_count", 0))
            status = "active" if valid_count >= min_valid_cycles else "insufficient_data"

            if rolling_mape is not None:
                entry["rolling_mape"] = rolling_mape
            if rolling_mae is not None:
                entry["rolling_mae"] = rolling_mae

            entry["status"] = status
            entry["last_evaluated_at"] = evaluated_at

        ensure_data_dir(slot)
        payload = {
            "slot": slot,
            "evaluation_window_days": window_days,
            "metrics": metrics_dict,
            "updated_at": evaluated_at,
        }
        _atomic_write_json(metrics_path, payload)

    # ------------------------------------------------------------------
    # 指定版本更新
    # ------------------------------------------------------------------

    def update_metrics(
        self,
        slot: str,
        workflow_id: str,
        metrics: dict,
    ) -> None:
        """
        更新指定版本的指标，原子写入 accuracy_metrics.json。

        若版本不存在则新增；若已存在则合并（updates 覆盖旧字段）。

        :param slot:        槽位名称（分区键）
        :param workflow_id: 工作流模板 ID
        :param metrics:     要写入的指标字典（可以是部分字段）
        """
        metrics_path = BASE_DATA_DIR / slot / "accuracy_metrics.json"
        data = load_json_safe(metrics_path, default={})

        metrics_dict: Dict[str, Any] = data.get("metrics", {})
        existing = metrics_dict.get(workflow_id, {})
        metrics_dict[workflow_id] = {**existing, **metrics}

        ensure_data_dir(slot)
        payload = {
            "slot": data.get("slot", slot),
            "evaluation_window_days": data.get("evaluation_window_days", 7),
            "metrics": metrics_dict,
            "updated_at": now_iso(),
        }
        _atomic_write_json(metrics_path, payload)

        # DB dual-write（异步，best-effort）
        if _is_db_enabled():
            _slot, _wf_id, _metrics = slot, workflow_id, dict(metrics)

            def _db_write():
                repo = _get_lf_repo()
                if repo is None:
                    return
                try:
                    db_m = dict(_metrics)
                    if isinstance(db_m.get("last_evaluated_at"), str):
                        db_m["last_evaluated_at"] = _parse_iso(db_m["last_evaluated_at"])
                    repo.upsert_accuracy_metrics(_slot, _wf_id, db_m)
                except Exception as _exc:
                    logger.warning("DB 写入 accuracy_metrics 失败（忽略）: %s", _exc)

            threading.Thread(target=_db_write, daemon=True).start()
