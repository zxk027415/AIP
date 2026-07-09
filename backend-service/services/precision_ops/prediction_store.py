"""
precision_ops/prediction_store.py — 预测结果 SQLite 存储层

职责：
  - 持久化每个预测周期内各版本（工作流）的预测值
  - 在实际值到达后回填，供 AccuracyTracker 计算精度指标
  - 提供按时间窗口的高效范围查询
  - 清理超出保留期的历史记录

数据库路径：BASE_DATA_DIR/predictions.db（注意：在根目录，不在 slot 子目录）
WAL 模式，写操作 5s 超时。

复合唯一键：(slot, workflow_id, prediction_cycle_id, forecast_timestamp)
使用 INSERT OR IGNORE 防止重复写入。
"""
from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from services.precision_ops._db_helper import _get_lf_repo, _is_db_enabled, _parse_iso
from services.precision_ops.utils import BASE_DATA_DIR, now_iso

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS predictions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    slot                TEXT NOT NULL,
    workflow_id         TEXT NOT NULL,
    version_tag         TEXT NOT NULL,
    prediction_cycle_id TEXT NOT NULL,
    forecast_timestamp  TEXT NOT NULL,
    predicted_value     REAL NOT NULL,
    actual_value        REAL,
    status              TEXT DEFAULT 'predicted',
    created_at          TEXT NOT NULL,
    evaluated_at        TEXT,
    UNIQUE(slot, workflow_id, prediction_cycle_id, forecast_timestamp)
);
"""

_CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_pred_slot_cycle   ON predictions(slot, prediction_cycle_id);",
    "CREATE INDEX IF NOT EXISTS idx_pred_slot_wf_time ON predictions(slot, workflow_id, forecast_timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_pred_retention    ON predictions(created_at);",
]


class PredictionStore:
    """
    SQLite 预测结果存储。

    使用方式：
        store = PredictionStore()                      # 默认路径
        store = PredictionStore(db_path=Path("/tmp/test.db"))  # 测试隔离

    `init_db()` 在 `__init__` 中自动调用，可重复调用（幂等）。
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """
        初始化存储层。

        :param db_path: 自定义数据库路径（用于测试隔离）；
                        默认使用 BASE_DATA_DIR / "predictions.db"。
        """
        if db_path is None:
            self.db_path: Path = BASE_DATA_DIR / "predictions.db"
        else:
            self.db_path = Path(db_path)

        # 确保父目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.init_db()

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """
        建表及索引（幂等，可重复调用）。

        启用 WAL（Write-Ahead Logging）模式以提高并发写入性能；
        写操作超时 5.0 秒。
        """
        with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(_CREATE_TABLE_SQL)
            for idx_sql in _CREATE_INDEXES_SQL:
                conn.execute(idx_sql)
            conn.commit()

    # ------------------------------------------------------------------
    # 写入预测记录
    # ------------------------------------------------------------------

    def record_prediction(
        self,
        slot: str,
        workflow_id: str,
        version_tag: str,
        cycle_id: str,
        forecast_timestamp: str,
        predicted_value: float,
    ) -> None:
        """
        写入一条预测记录。

        使用 INSERT OR IGNORE，相同复合键（slot, workflow_id,
        prediction_cycle_id, forecast_timestamp）已存在时静默跳过，
        不抛出异常，防止重复写入。

        :param slot:               槽位名称（分区键），如 "default"
        :param workflow_id:        工作流模板 ID
        :param version_tag:        版本标签，如 "v2026-06-08-ares-abc123"
        :param cycle_id:           预测周期 ID
        :param forecast_timestamp: 预测目标时间戳（ISO 8601 字符串）
        :param predicted_value:    预测值
        """
        sql = """
        INSERT OR IGNORE INTO predictions
            (slot, workflow_id, version_tag, prediction_cycle_id,
             forecast_timestamp, predicted_value, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'predicted', ?)
        """
        with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
            conn.execute(sql, (
                slot,
                workflow_id,
                version_tag,
                cycle_id,
                forecast_timestamp,
                predicted_value,
                now_iso(),
            ))
            conn.commit()

        # DB dual-write（异步，best-effort）
        if _is_db_enabled():
            _slot, _wf, _vtag, _cid, _fts, _pv = (
                slot, workflow_id, version_tag, cycle_id, forecast_timestamp, predicted_value
            )

            def _db_write():
                repo = _get_lf_repo()
                if repo is None:
                    return
                try:
                    repo.save_prediction_result({
                        "slot": _slot,
                        "workflow_id": _wf,
                        "version_tag": _vtag,
                        "prediction_cycle_id": _cid,
                        "forecast_timestamp": _parse_iso(_fts),
                        "predicted_value": _pv,
                        "status": "predicted",
                        "is_shadow": False,
                    })
                except Exception as _exc:
                    logger.warning("DB 写入 prediction_result 失败（忽略）: %s", _exc)

            threading.Thread(target=_db_write, daemon=True).start()

    # ------------------------------------------------------------------
    # 回填实际值
    # ------------------------------------------------------------------

    def fill_actuals(
        self,
        slot: str,
        cycle_id: str,
        actuals: Dict[str, float],
    ) -> None:
        """
        回填一个预测周期的实际值。

        :param slot:     槽位名称
        :param cycle_id: 预测周期 ID
        :param actuals:  实际值字典，格式为
                         ``{forecast_timestamp: actual_value}``
        """
        if not actuals:
            return

        sql = """
        UPDATE predictions
        SET actual_value = ?,
            status       = 'evaluated',
            evaluated_at = ?
        WHERE slot                = ?
          AND prediction_cycle_id = ?
          AND forecast_timestamp  = ?
        """
        evaluated_at = now_iso()
        with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
            for forecast_ts, actual_val in actuals.items():
                conn.execute(sql, (actual_val, evaluated_at, slot, cycle_id, forecast_ts))
            conn.commit()

        # DB dual-write（异步，best-effort）— 按 slot + cycle_id + forecast_timestamp 精确更新
        if _is_db_enabled():
            _slot, _cycle_id, _actuals = slot, cycle_id, dict(actuals)
            def _sync_actuals():
                repo = _get_lf_repo()
                if repo is None:
                    return
                try:
                    from sqlalchemy import update as sa_update
                    from services.db.models.load_forecast import PredictionResult as PRModel
                    from datetime import datetime as _dt
                    with repo._adapter.get_sync_session() as session:
                        for _fts, _aval in _actuals.items():
                            session.execute(
                                sa_update(PRModel)
                                .where(
                                    PRModel.slot == _slot,
                                    PRModel.prediction_cycle_id == _cycle_id,
                                    PRModel.forecast_timestamp == _parse_iso(_fts),
                                )
                                .values(
                                    actual_value=_aval,
                                    evaluated_at=_dt.utcnow(),
                                )
                            )
                except Exception as exc:
                    logger.warning("fill_actuals DB sync failed: %s", exc)
            threading.Thread(target=_sync_actuals, daemon=True).start()

    # ------------------------------------------------------------------
    # 窗口范围查询
    # ------------------------------------------------------------------

    def get_predictions_in_window(
        self,
        slot: str,
        workflow_id: str,
        window_start: str,
        window_end: str,
    ) -> List[dict]:
        """
        查询指定时间窗口内的预测记录。

        返回 ``forecast_timestamp`` 在 ``[window_start, window_end]``
        区间内的所有记录。

        :param slot:         槽位名称
        :param workflow_id:  工作流模板 ID
        :param window_start: 窗口起始时间戳（ISO 8601，含）
        :param window_end:   窗口结束时间戳（ISO 8601，含）
        :return: 记录列表，每条为 dict（含所有列）
        """
        sql = """
        SELECT id, slot, workflow_id, version_tag, prediction_cycle_id,
               forecast_timestamp, predicted_value, actual_value,
               status, created_at, evaluated_at
        FROM predictions
        WHERE slot            = ?
          AND workflow_id     = ?
          AND forecast_timestamp >= ?
          AND forecast_timestamp <= ?
        ORDER BY forecast_timestamp ASC
        """
        with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, (slot, workflow_id, window_start, window_end))
            return [dict(row) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # 标记实际值缺失
    # ------------------------------------------------------------------

    def mark_actuals_missing(
        self,
        slot: str,
        cycle_id: str,
    ) -> None:
        """
        将该周期内所有仍处于 ``status='predicted'``（未回填实际值）
        的记录标记为 ``status='actuals_missing'``。

        典型调用场景：超过规定等待时长（如 48h）后实际值仍未到达，
        调用此方法标记相关记录，以便精度跟踪器在统计时正确排除。

        :param slot:     槽位名称
        :param cycle_id: 预测周期 ID
        """
        sql = """
        UPDATE predictions
        SET status = 'actuals_missing'
        WHERE slot                = ?
          AND prediction_cycle_id = ?
          AND status              = 'predicted'
        """
        with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
            conn.execute(sql, (slot, cycle_id))
            conn.commit()

    # ------------------------------------------------------------------
    # 清理过期记录
    # ------------------------------------------------------------------

    def cleanup_expired(self, retention_days: int) -> int:
        """
        删除 ``created_at`` 超过 ``retention_days`` 天的记录。

        :param retention_days: 保留天数（正整数）
        :return: 实际删除的行数
        """
        cutoff = (
            datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
        ).isoformat()

        sql = "DELETE FROM predictions WHERE created_at < ?"
        with sqlite3.connect(str(self.db_path), timeout=5.0) as conn:
            cursor = conn.execute(sql, (cutoff,))
            deleted = cursor.rowcount
            conn.commit()
        logger.info(
            "cleanup_expired: 删除 %d 条超过 %d 天的预测记录（cutoff=%s）",
            deleted,
            retention_days,
            cutoff,
        )
        return deleted
