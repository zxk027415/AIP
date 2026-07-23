# @AI_GENERATED
"""版本级精度指标追踪器。

指标以 ``workflow_id@version_tag`` 为键写入 ``accuracy_metrics.json``；旧的
workflow_id 键仍可读取。数据库的既有 ``accuracy_metric.workflow_id`` 列也存该键，
因此无需迁移表结构即可区分同一工作流的多个已部署版本。
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

try:
    from typing import TypedDict
except ImportError:  # pragma: no cover
    from typing_extensions import TypedDict  # type: ignore

from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled, _parse_iso
from services.precision_ops.utils import BASE_DATA_DIR, _atomic_write_json, ensure_data_dir, load_json_safe, now_iso
from services.precision_ops.versioning import make_version_key, split_version_key

logger = logging.getLogger(__name__)


class RollingMetrics(TypedDict):
    """单个部署版本在滚动评估窗口内的指标快照。"""

    rolling_mape: float
    rolling_wmape: Optional[float]
    rolling_mae: float
    valid_cycle_count: int
    total_cycle_count: int
    coverage_rate: Optional[float]
    window_days: Optional[int]
    last_evaluated_at: str
    status: str


class AccuracyTracker:
    """读写版本级滚动精度指标，并保留旧 ``workflow_id`` 调用兼容性。"""

    def __init__(self, prediction_store: Optional[Any] = None) -> None:
        self._prediction_store = prediction_store

    @staticmethod
    def _record_in_window(record: dict, window_days: int) -> bool:
        """判断已评估预测是否属于以当前时间结束的滚动窗口。"""
        timestamp = record.get("forecast_timestamp")
        if record.get("evaluated_at") is None or timestamp is None:
            return False
        if isinstance(timestamp, datetime):
            timestamp_dt = timestamp
            if timestamp_dt.tzinfo is None:
                timestamp_dt = timestamp_dt.replace(tzinfo=timezone.utc)
        else:
            try:
                timestamp_dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if timestamp_dt.tzinfo is None:
                    timestamp_dt = timestamp_dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                return False
        return datetime.now(tz=timezone.utc) - timedelta(days=window_days) <= timestamp_dt <= datetime.now(tz=timezone.utc)

    def compute_rolling_mape(self, records: List[dict], window_days: int) -> Optional[float]:
        """计算窗口内逐点平均百分比误差；actual=0 的点不参与分母。"""
        valid = [
            row for row in records
            if self._record_in_window(row, window_days)
            and row.get("actual_value") not in (None, 0.0)
        ]
        if not valid:
            return None
        return sum(
            abs(float(row["predicted_value"]) - float(row["actual_value"]))
            / abs(float(row["actual_value"]))
            for row in valid
        ) / len(valid) * 100

    def compute_rolling_wmape(self, records: List[dict], window_days: int) -> Optional[float]:
        """计算窗口内 WMAPE：Σ|预测-实际| / Σ|实际| × 100。"""
        valid = [
            row for row in records
            if self._record_in_window(row, window_days) and row.get("actual_value") is not None
        ]
        denominator = sum(abs(float(row["actual_value"])) for row in valid)
        if not valid or denominator == 0:
            return None
        numerator = sum(abs(float(row["predicted_value"]) - float(row["actual_value"])) for row in valid)
        return numerator / denominator * 100

    def compute_rolling_mae(self, records: List[dict], window_days: int) -> Optional[float]:
        """计算窗口内 MAE，零负荷点也会参与。"""
        valid = [row for row in records if self._record_in_window(row, window_days) and row.get("actual_value") is not None]
        if not valid:
            return None
        return sum(abs(float(row["predicted_value"]) - float(row["actual_value"])) for row in valid) / len(valid)

    def get_rolling_metrics(
        self,
        slot: str,
        workflow_id: str,
        version_tag: Optional[str] = None,
    ) -> Optional[RollingMetrics]:
        """读取版本级指标；带标签查询未命中时 fail-closed，无标签查询保留旧 workflow_id 键兼容。"""
        data = load_json_safe(BASE_DATA_DIR / slot / "accuracy_metrics.json", default={})
        entries: Dict[str, Any] = data.get("metrics", {})
        version_key = make_version_key(workflow_id, version_tag)
        entry = entries.get(version_key)
        # @AI_GENERATED: 部署版本带标签时 fail closed，禁止把旧裸 workflow 指标误归属到新版本
        if entry is None and version_tag:
            return None
        # @AI_GENERATED: end
        if entry is None:
            return None
        return {
            "rolling_mape": float(entry.get("rolling_mape", 0.0)),
            "rolling_wmape": (float(entry["rolling_wmape"]) if entry.get("rolling_wmape") is not None else None),
            "rolling_mae": float(entry.get("rolling_mae", 0.0)),
            "valid_cycle_count": int(entry.get("valid_cycle_count", 0)),
            "total_cycle_count": int(entry.get("total_cycle_count", 0)),
            "coverage_rate": (float(entry["coverage_rate"]) if entry.get("coverage_rate") is not None else None),
            "window_days": (int(entry["window_days"]) if entry.get("window_days") is not None else None),
            "last_evaluated_at": str(entry.get("last_evaluated_at", "")),
            "status": str(entry.get("status", "insufficient_data")),
        }

    def update_metrics(
        self,
        slot: str,
        workflow_id: str,
        metrics: dict,
        version_tag: Optional[str] = None,
    ) -> None:
        """原子合并写入版本级指标，并 best-effort 双写到既有数据库表。"""
        path = BASE_DATA_DIR / slot / "accuracy_metrics.json"
        data = load_json_safe(path, default={})
        entries: Dict[str, Any] = data.get("metrics", {})
        version_key = make_version_key(workflow_id, version_tag)
        entries[version_key] = {**entries.get(version_key, {}), **metrics}
        ensure_data_dir(slot)
        _atomic_write_json(path, {
            "slot": data.get("slot", slot),
            "evaluation_window_days": data.get("evaluation_window_days", metrics.get("window_days", 7)),
            "metrics": entries,
            "updated_at": now_iso(),
        })

        if not _is_db_enabled():
            return

        db_metrics = {
            key: value for key, value in metrics.items()
            if key in {"rolling_mape", "rolling_mae", "valid_cycle_count", "total_cycle_count", "status", "last_evaluated_at"}
        }
        if not db_metrics:
            return

        def _db_write() -> None:
            repo = _get_lf_repo()
            if repo is None:
                return
            try:
                if isinstance(db_metrics.get("last_evaluated_at"), str):
                    db_metrics["last_evaluated_at"] = _parse_iso(db_metrics["last_evaluated_at"])
                repo.upsert_accuracy_metrics(slot, version_key, db_metrics)
            except Exception as exc:  # best-effort mirror must not block monitoring
                logger.warning("DB 写入 accuracy_metrics 失败（忽略）: %s", exc)

        threading.Thread(target=_db_write, daemon=True).start()

    def get_leaderboard(self, slot: str) -> List[dict]:
        """返回 active 版本的排行榜，优先按 WMAPE、缺失时按 MAPE 升序。"""
        data = load_json_safe(BASE_DATA_DIR / slot / "accuracy_metrics.json", default={})
        board: List[dict] = []
        for version_key, entry in data.get("metrics", {}).items():
            if entry.get("status") != "active":
                continue
            workflow_id, version_tag = split_version_key(version_key)
            board.append({
                "workflow_id": workflow_id,
                "version_tag": version_tag,
                "rolling_mape": float(entry.get("rolling_mape", 0.0)),
                "rolling_wmape": entry.get("rolling_wmape"),
                "rolling_mae": float(entry.get("rolling_mae", 0.0)),
                "valid_cycle_count": int(entry.get("valid_cycle_count", 0)),
                "total_cycle_count": int(entry.get("total_cycle_count", 0)),
                "coverage_rate": entry.get("coverage_rate"),
                "window_days": entry.get("window_days"),
                "last_evaluated_at": str(entry.get("last_evaluated_at", "")),
                "status": "active",
            })
        board.sort(key=lambda item: (float(item["rolling_wmape"] if item["rolling_wmape"] is not None else item["rolling_mape"]), -item["valid_cycle_count"]))
        return board

    def evaluate_cycle(self, slot: str, cycle_id: str, min_valid_cycles: int = 3) -> None:
        """兼容旧调用：按已登记版本评估单个周期，并不会跨版本混算。"""
        if self._prediction_store is None:
            raise ValueError("evaluate_cycle 需要 PredictionStore；请在构造时传入 prediction_store 参数")
        data = load_json_safe(BASE_DATA_DIR / slot / "accuracy_metrics.json", default={})
        for version_key in data.get("metrics", {}):
            workflow_id, version_tag = split_version_key(version_key)
            records = self._prediction_store.get_predictions_in_window(slot, workflow_id, "", "")
            cycle_records = [
                row for row in records
                if row.get("prediction_cycle_id") == cycle_id and (not version_tag or row.get("version_tag") == version_tag)
            ]
            total = len(cycle_records)
            evaluated = [row for row in cycle_records if row.get("actual_value") is not None]
            if not total:
                continue
            coverage = len(evaluated) / total
            previous = self.get_rolling_metrics(slot, workflow_id, version_tag) or {}
            valid_cycles = int(previous.get("valid_cycle_count", 0)) + int(coverage >= 0.9)
            self.update_metrics(slot, workflow_id, {
                "rolling_mape": self.compute_rolling_mape(cycle_records, 30) or previous.get("rolling_mape", 0.0),
                "rolling_wmape": self.compute_rolling_wmape(cycle_records, 30),
                "rolling_mae": self.compute_rolling_mae(cycle_records, 30) or previous.get("rolling_mae", 0.0),
                "valid_cycle_count": valid_cycles,
                "total_cycle_count": int(previous.get("total_cycle_count", 0)) + 1,
                "coverage_rate": coverage,
                "window_days": 30,
                "last_evaluated_at": now_iso(),
                "status": "active" if valid_cycles >= min_valid_cycles else "insufficient_data",
            }, version_tag=version_tag)
# @AI_GENERATED: end
