# -*- coding: utf-8 -*-
"""
services/db/repositories/load_forecast.py — 负荷预测 CRUD Repository

LoadForecastRepository: 提供负荷预测数据管线的所有 CRUD 操作。
所有写操作使用事务（由 DBAdapter.get_sync_session 管理），失败整体 rollback。

Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

# @AI_GENERATED: StationData evidence aggregation dependency
from sqlalchemy import func, update
# @AI_GENERATED: end
from sqlalchemy.dialects.mysql import insert as mysql_insert

from ..adapter import DBAdapter
from ..models.load_forecast import (
    AccuracyMetric,
    CandidatePool,
    ExperimentRun,
    PrelaunchQueue,
    PredictionResult,
    StationData,
    VersionRegistry,
)


@dataclass
class StationDataRecord:
    """站点数据写入记录 — insert_station_data 的输入类型。"""

    station_id: str
    """station_id — 站点唯一标识"""
    timestamp_utc: datetime
    """timestamp_utc — 数据时间戳（UTC）"""
    feature_name: str
    """feature_name — 特征名称"""
    value: float
    """value — 测量值"""
    slot: str
    """slot — 槽位标识（多环境/多产品线分区键）"""


class LoadForecastRepository:
    """
    负荷预测数据管线 CRUD Repository。

    所有写操作通过 DBAdapter.get_sync_session() 管理事务；
    失败时由 contextmanager 自动 rollback。
    """

    def __init__(self, adapter: DBAdapter) -> None:
        self._adapter = adapter

    # ------------------------------------------------------------------
    # StationData — 站点实测数据
    # ------------------------------------------------------------------

    def insert_station_data(self, records: List[StationDataRecord]) -> int:
        """
        批量插入站点数据，返回实际插入行数。

        使用 INSERT IGNORE 避免唯一键冲突导致失败；重复行静默跳过。
        """
        if not records:
            return 0

        now = datetime.utcnow()
        rows = [
            {
                "station_id": r.station_id,
                "timestamp_utc": r.timestamp_utc,
                "feature_name": r.feature_name,
                "value": r.value,
                "slot": r.slot,
                "ingested_at": now,
            }
            for r in records
        ]

        with self._adapter.get_sync_session() as session:
            stmt = mysql_insert(StationData).prefix_with("IGNORE").values(rows)
            result = session.execute(stmt)
            return result.rowcount

    def query_station_data(
        self,
        slot: str,
        station_id: str,
        time_start: datetime,
        time_end: datetime,
    ) -> List[StationData]:
        """
        按槽位、站点 ID、时间范围查询站点数据 [time_start, time_end)。
        """
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(StationData)
                .filter(
                    StationData.slot == slot,
                    StationData.station_id == station_id,
                    StationData.timestamp_utc >= time_start,
                    StationData.timestamp_utc < time_end,
                )
                .all()
            )
            session.expunge_all()
            return rows

    # @AI_GENERATED: scheduler data-pull evidence query
    def get_station_data_evidence(self, slot: str, sample_limit: int = 48) -> Dict[str, Any]:
        """Return a bounded, read-only snapshot of station data persisted for one slot."""
        bounded_limit = max(1, min(int(sample_limit), 200))
        with self._adapter.get_sync_session() as session:
            base_query = session.query(StationData).filter(StationData.slot == slot)
            total_rows = int(base_query.with_entities(func.count(StationData.id)).scalar() or 0)
            if total_rows == 0:
                return {
                    "slot": slot,
                    "total_rows": 0,
                    "station_count": 0,
                    "feature_names": [],
                    "time_start": None,
                    "time_end": None,
                    "latest": None,
                    "samples": [],
                }

            time_start, time_end = base_query.with_entities(
                func.min(StationData.timestamp_utc),
                func.max(StationData.timestamp_utc),
            ).one()
            station_count = int(
                base_query.with_entities(func.count(func.distinct(StationData.station_id))).scalar() or 0
            )
            feature_names = [
                str(feature_name)
                for (feature_name,) in base_query.with_entities(StationData.feature_name)
                .distinct()
                .order_by(StationData.feature_name.asc())
                .all()
            ]
            latest = (
                base_query.order_by(
                    StationData.timestamp_utc.desc(),
                    StationData.id.desc(),
                )
                .first()
            )
            newest_first = (
                base_query.order_by(
                    StationData.timestamp_utc.desc(),
                    StationData.id.desc(),
                )
                .limit(bounded_limit)
                .all()
            )

            def serialize(row: StationData) -> Dict[str, Any]:
                return {
                    "station_id": row.station_id,
                    "timestamp_utc": row.timestamp_utc,
                    "feature_name": row.feature_name,
                    "value": float(row.value),
                    "ingested_at": row.ingested_at,
                }

            return {
                "slot": slot,
                "total_rows": total_rows,
                "station_count": station_count,
                "feature_names": feature_names,
                "time_start": time_start,
                "time_end": time_end,
                "latest": serialize(latest) if latest is not None else None,
                "samples": [serialize(row) for row in reversed(newest_first)],
            }
    # @AI_GENERATED: end

    # ------------------------------------------------------------------
    # ExperimentRun — 实验运行记录
    # ------------------------------------------------------------------

    def save_experiment_run(self, run_data: dict) -> ExperimentRun:
        """
        Upsert 实验运行记录（按 id 字段判重）。

        id 已存在则更新所有字段，不存在则插入新记录。
        """
        with self._adapter.get_sync_session() as session:
            obj = session.get(ExperimentRun, run_data["id"])
            if obj is None:
                obj = ExperimentRun(**run_data)
                session.add(obj)
            else:
                for k, v in run_data.items():
                    setattr(obj, k, v)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_experiment_run(self, run_id: str) -> Optional[ExperimentRun]:
        """按 run_id 查询实验记录，不存在返回 None。"""
        with self._adapter.get_sync_session() as session:
            obj = session.get(ExperimentRun, run_id)
            if obj is not None:
                session.expunge(obj)
            return obj

    # ------------------------------------------------------------------
    # CandidatePool — 候选池
    # ------------------------------------------------------------------

    def upsert_candidate(self, candidate_data: dict) -> CandidatePool:
        """
        Upsert 候选记录（按 id 字段判重）。

        id 已存在则更新所有字段，不存在则插入新记录。
        """
        with self._adapter.get_sync_session() as session:
            obj = session.get(CandidatePool, candidate_data["id"])
            if obj is None:
                obj = CandidatePool(**candidate_data)
                session.add(obj)
            else:
                for k, v in candidate_data.items():
                    setattr(obj, k, v)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def query_candidates(
        self, slot: str, status: Optional[str] = None
    ) -> List[CandidatePool]:
        """
        按槽位查询候选池；可选按 status 过滤。

        status=None 时返回该槽位全部候选记录。
        """
        with self._adapter.get_sync_session() as session:
            q = session.query(CandidatePool).filter(CandidatePool.slot == slot)
            if status is not None:
                q = q.filter(CandidatePool.status == status)
            rows = q.all()
            session.expunge_all()
            return rows

    # ------------------------------------------------------------------
    # PredictionResult — 预测结果
    # ------------------------------------------------------------------

    def save_prediction_result(self, result_data: dict) -> PredictionResult:
        """插入一条预测结果记录，返回含自增 id 的对象。"""
        with self._adapter.get_sync_session() as session:
            obj = PredictionResult(**result_data)
            session.add(obj)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def query_predictions(
        self,
        slot: str,
        workflow_id: str,
        time_start: datetime,
        time_end: datetime,
    ) -> List[PredictionResult]:
        """
        按槽位、工作流、预测时间范围查询预测结果 [time_start, time_end)。
        """
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(PredictionResult)
                .filter(
                    PredictionResult.slot == slot,
                    PredictionResult.workflow_id == workflow_id,
                    PredictionResult.forecast_timestamp >= time_start,
                    PredictionResult.forecast_timestamp < time_end,
                )
                .all()
            )
            session.expunge_all()
            return rows

    def update_actual_value(
        self, prediction_cycle_id: str, slot: str, actual_value: float
    ) -> int:
        """
        回填实际值 — 按 prediction_cycle_id + slot 定位记录并写入 actual_value。

        Returns:
            更新的行数（0 表示未匹配到记录）。
        """
        with self._adapter.get_sync_session() as session:
            result = session.execute(
                update(PredictionResult)
                .where(
                    PredictionResult.prediction_cycle_id == prediction_cycle_id,
                    PredictionResult.slot == slot,
                )
                .values(
                    actual_value=actual_value,
                    evaluated_at=datetime.utcnow(),
                )
            )
            return result.rowcount

    # ------------------------------------------------------------------
    # AccuracyMetric — 精度指标
    # ------------------------------------------------------------------

    def upsert_accuracy_metrics(
        self, slot: str, workflow_id: str, metrics: dict
    ) -> AccuracyMetric:
        """
        Upsert 精度指标（按 slot + workflow_id 唯一约束判重）。

        已存在则更新 metrics 字段并刷新 updated_at，不存在则插入新记录。
        """
        with self._adapter.get_sync_session() as session:
            obj = (
                session.query(AccuracyMetric)
                .filter_by(slot=slot, workflow_id=workflow_id)
                .first()
            )
            if obj is None:
                obj = AccuracyMetric(slot=slot, workflow_id=workflow_id, **metrics)
                session.add(obj)
            else:
                for k, v in metrics.items():
                    setattr(obj, k, v)
                obj.updated_at = datetime.utcnow()
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_accuracy_metrics(
        self, slot: str, workflow_id: str
    ) -> Optional[AccuracyMetric]:
        """按 slot + workflow_id 查询精度指标，不存在返回 None。"""
        with self._adapter.get_sync_session() as session:
            obj = (
                session.query(AccuracyMetric)
                .filter_by(slot=slot, workflow_id=workflow_id)
                .first()
            )
            if obj is not None:
                session.expunge(obj)
            return obj

    # ------------------------------------------------------------------
    # VersionRegistry — 版本注册表
    # ------------------------------------------------------------------

    def save_version_registry(self, registry_data: dict) -> VersionRegistry:
        """插入版本注册记录，返回含自增 id 的对象。"""
        with self._adapter.get_sync_session() as session:
            obj = VersionRegistry(**registry_data)
            session.add(obj)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_active_version(self, slot: str) -> Optional[VersionRegistry]:
        """
        获取指定槽位当前生产版本（status='production'）。

        多条 production 记录时返回 registered_at 最新的一条。
        """
        with self._adapter.get_sync_session() as session:
            obj = (
                session.query(VersionRegistry)
                .filter(
                    VersionRegistry.slot == slot,
                    VersionRegistry.status == "production",
                )
                .order_by(VersionRegistry.registered_at.desc())
                .first()
            )
            if obj is not None:
                session.expunge(obj)
            return obj

    # ------------------------------------------------------------------
    # PrelaunchQueue — 预上线队列
    # ------------------------------------------------------------------

    def save_prelaunch(self, prelaunch_data: dict) -> PrelaunchQueue:
        """插入预上线队列记录，返回已持久化的对象。"""
        with self._adapter.get_sync_session() as session:
            obj = PrelaunchQueue(**prelaunch_data)
            session.add(obj)
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_prelaunch_queue(self, slot: str) -> List[PrelaunchQueue]:
        """获取指定槽位所有预上线队列记录。"""
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(PrelaunchQueue)
                .filter(PrelaunchQueue.slot == slot)
                .all()
            )
            session.expunge_all()
            return rows
