# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/db/repositories/ingestion_tracker.py — 设备-天完整性判定 + 按设备预测游标

IngestionTrackerRepository 封装两张表的读写：

  - measurement_ingestion_daily — 设备-天数据完整性判定表。每次原始测量写入
    ``training_samples`` 后调用 ``record_arrival()`` 同步更新该设备-天的
    ``point_count``；点数达到 ``expected_point_count`` 的完整性阈值比例时
    自动置 ``is_complete=True``。
  - device_prediction_cursor — 按设备维度的预测游标，替代全局单点游标
    （``prediction_cursor.json``），支撑设备异步到达场景下的按日滚动预测。

两张表的写入方与数据来源无关：不管是 ``PvFaultMockFeeder`` 还是未来真实采集
管道写入 ``training_samples``，都应调用本仓库的同一套方法同步完整性进度。

对应设计讨论：.kiro/specs/pv-fault-timeseries-diagnosis/ 按日滚动预测生产表结构。
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Integer, and_, cast, func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from services.db.adapter import DBAdapter
from services.db.models.pv_fault import DevicePredictionCursor, MeasurementIngestionDaily

logger = logging.getLogger(__name__)

#: 完整性判定阈值比例 —— point_count / expected_point_count 达到此比例才算完整。
#: 与 SampleBuilder.min_points（样本是否够格训练）是两个独立口径，不混用：
#: 本阈值回答"这一天数据到齐了没"，min_points 回答"这一天的数据够不够切一条样本"。
DEFAULT_COMPLETENESS_RATIO = 0.9

#: 一个自然日的理论采样点数（288 = 24h * 12点/h，采样间隔 300 秒）。
DEFAULT_EXPECTED_POINT_COUNT = 288


class IngestionTrackerRepository:
    """设备-天完整性判定与按设备预测游标的数据仓库。"""

    def __init__(
        self,
        adapter: DBAdapter,
        *,
        completeness_ratio: float = DEFAULT_COMPLETENESS_RATIO,
    ) -> None:
        self._adapter = adapter
        self._completeness_ratio = completeness_ratio

    # ------------------------------------------------------------------
    # measurement_ingestion_daily：完整性判定
    # ------------------------------------------------------------------

    def record_arrival(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        business_date: date,
        *,
        point_delta: int,
        expected_point_count: int = DEFAULT_EXPECTED_POINT_COUNT,
        arrived_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """记录一批测量值到达，累加该设备-天的 point_count 并重新判定完整性。

        Args:
            point_delta: 本次新增的采样点数（去重后的真实插入行数，不是尝试写入数）。
            expected_point_count: 该设备-天理论应有点数，默认 288（1 天 / 5 分钟）。
            arrived_at: 到达时刻，默认当前 UTC 时间。

        Returns:
            更新后的完整性行（dict），含 is_complete/point_count 等字段。
        """
        now = arrived_at or datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            row = session.get(
                MeasurementIngestionDaily,
                {
                    "site_id": site_id,
                    "device_id": device_id,
                    "branch_id": branch_id,
                    "business_date": business_date,
                },
            )
            if row is None:
                row = MeasurementIngestionDaily(
                    site_id=site_id,
                    device_id=device_id,
                    branch_id=branch_id,
                    business_date=business_date,
                    point_count=0,
                    expected_point_count=expected_point_count,
                    is_complete=False,
                    first_seen_at=now,
                )
                session.add(row)

            row.point_count = int(row.point_count or 0) + int(point_delta)
            row.expected_point_count = expected_point_count
            row.updated_at = now
            if row.first_seen_at is None:
                row.first_seen_at = now

            threshold = expected_point_count * self._completeness_ratio
            newly_complete = (not row.is_complete) and row.point_count >= threshold
            if newly_complete:
                row.is_complete = True
                row.completed_at = now

            session.flush()
            result = self._row_to_dict(row)
        if newly_complete:
            logger.info(
                "ingestion_tracker: 设备(%s,%s,%s) 业务日 %s 已完整（%d/%d）",
                site_id, device_id, branch_id, business_date,
                result["point_count"], expected_point_count,
            )
        return result

    def query_device_day(
        self, site_id: str, device_id: str, branch_id: str, business_date: date,
    ) -> Optional[Dict[str, Any]]:
        """查单个设备-天的完整性行，不存在返回 None。"""
        with self._adapter.get_sync_session() as session:
            row = session.get(
                MeasurementIngestionDaily,
                {
                    "site_id": site_id,
                    "device_id": device_id,
                    "branch_id": branch_id,
                    "business_date": business_date,
                },
            )
            if row is None:
                return None
            return self._row_to_dict(row)

    def query_site_overview(self, business_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """按站点聚合完整性总览：设备总数、已完整设备数、完成度。

        Args:
            business_date: 指定业务日；None 时返回每个站点"最新业务日"的总览
                （按站点分组取 MAX(business_date)）。
        Returns:
            每个站点一条：site_id / business_date / device_total /
            device_complete / completion_ratio / latest_updated_at。
        """
        with self._adapter.get_sync_session() as session:
            if business_date is not None:
                stmt = (
                    select(
                        MeasurementIngestionDaily.site_id,
                        MeasurementIngestionDaily.business_date,
                        func.count().label("device_total"),
                        # @AI_GENERATED: cast 到 Integer，避免 SQLAlchemy 对 Boolean 列的
                        # result-processor 把 SUM() 聚合结果强制转回 True/False（丢失计数值）。
                        func.sum(cast(MeasurementIngestionDaily.is_complete, Integer)).label("device_complete"),
                        # @AI_GENERATED: end
                        func.max(MeasurementIngestionDaily.updated_at).label("latest_updated_at"),
                    )
                    .where(MeasurementIngestionDaily.business_date == business_date)
                    .group_by(MeasurementIngestionDaily.site_id, MeasurementIngestionDaily.business_date)
                    .order_by(MeasurementIngestionDaily.site_id.asc())
                )
            else:
                # 每个站点的最新业务日：先算每个站点的 max(business_date)，再据此聚合
                latest_subq = (
                    select(
                        MeasurementIngestionDaily.site_id,
                        func.max(MeasurementIngestionDaily.business_date).label("latest_date"),
                    )
                    .group_by(MeasurementIngestionDaily.site_id)
                    .subquery()
                )
                stmt = (
                    select(
                        MeasurementIngestionDaily.site_id,
                        MeasurementIngestionDaily.business_date,
                        func.count().label("device_total"),
                        func.sum(cast(MeasurementIngestionDaily.is_complete, Integer)).label("device_complete"),
                        func.max(MeasurementIngestionDaily.updated_at).label("latest_updated_at"),
                    )
                    .join(
                        latest_subq,
                        and_(
                            MeasurementIngestionDaily.site_id == latest_subq.c.site_id,
                            MeasurementIngestionDaily.business_date == latest_subq.c.latest_date,
                        ),
                    )
                    .group_by(MeasurementIngestionDaily.site_id, MeasurementIngestionDaily.business_date)
                    .order_by(MeasurementIngestionDaily.site_id.asc())
                )
            rows = session.execute(stmt).all()

        result = []
        for row in rows:
            device_total = int(row.device_total or 0)
            device_complete = int(row.device_complete or 0)
            result.append({
                "site_id": row.site_id,
                "business_date": row.business_date.isoformat() if row.business_date else None,
                "device_total": device_total,
                "device_complete": device_complete,
                "completion_ratio": round(device_complete / device_total, 4) if device_total else 0.0,
                "latest_updated_at": row.latest_updated_at.isoformat() if row.latest_updated_at else None,
            })
        return result

    def query_device_detail(
        self, site_id: str, business_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """列出某站点下所有设备在指定业务日（或各自最新业务日）的完整性明细。

        供前端"设备到达明细"下钻表格使用。
        """
        with self._adapter.get_sync_session() as session:
            if business_date is not None:
                stmt = (
                    select(MeasurementIngestionDaily)
                    .where(
                        MeasurementIngestionDaily.site_id == site_id,
                        MeasurementIngestionDaily.business_date == business_date,
                    )
                    .order_by(MeasurementIngestionDaily.device_id.asc(), MeasurementIngestionDaily.branch_id.asc())
                )
                rows = session.execute(stmt).scalars().all()
            else:
                # 每个设备三元组取其最新业务日的一行
                latest_subq = (
                    select(
                        MeasurementIngestionDaily.site_id,
                        MeasurementIngestionDaily.device_id,
                        MeasurementIngestionDaily.branch_id,
                        func.max(MeasurementIngestionDaily.business_date).label("latest_date"),
                    )
                    .where(MeasurementIngestionDaily.site_id == site_id)
                    .group_by(
                        MeasurementIngestionDaily.site_id,
                        MeasurementIngestionDaily.device_id,
                        MeasurementIngestionDaily.branch_id,
                    )
                    .subquery()
                )
                stmt = (
                    select(MeasurementIngestionDaily)
                    .join(
                        latest_subq,
                        and_(
                            MeasurementIngestionDaily.site_id == latest_subq.c.site_id,
                            MeasurementIngestionDaily.device_id == latest_subq.c.device_id,
                            MeasurementIngestionDaily.branch_id == latest_subq.c.branch_id,
                            MeasurementIngestionDaily.business_date == latest_subq.c.latest_date,
                        ),
                    )
                    .order_by(MeasurementIngestionDaily.device_id.asc(), MeasurementIngestionDaily.branch_id.asc())
                )
                rows = session.execute(stmt).scalars().all()
            return [self._row_to_dict(r) for r in rows]

    def query_pending_predictable(
        self, site_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查已完整但尚未被对应设备游标预测过的设备-天（供人工确认批量预测使用）。

        判定条件：``is_complete=True`` 且
        （无对应 device_prediction_cursor 行，或
         ``business_date > DATE(last_predicted_time)``）。
        """
        with self._adapter.get_sync_session() as session:
            stmt = (
                select(MeasurementIngestionDaily, DevicePredictionCursor.last_predicted_time)
                .outerjoin(
                    DevicePredictionCursor,
                    and_(
                        MeasurementIngestionDaily.site_id == DevicePredictionCursor.site_id,
                        MeasurementIngestionDaily.device_id == DevicePredictionCursor.device_id,
                        MeasurementIngestionDaily.branch_id == DevicePredictionCursor.branch_id,
                    ),
                )
                .where(MeasurementIngestionDaily.is_complete.is_(True))
            )
            if site_id is not None:
                stmt = stmt.where(MeasurementIngestionDaily.site_id == site_id)
            rows = session.execute(stmt).all()

        result = []
        for ingestion_row, last_predicted_time in rows:
            # 游标是精确时刻，转换成 date 后与 business_date 比较
            last_predicted_date = last_predicted_time.date() if last_predicted_time else None
            if last_predicted_date is not None and ingestion_row.business_date <= last_predicted_date:
                continue
            item = self._row_to_dict(ingestion_row)
            item["last_predicted_business_date"] = last_predicted_date.isoformat() if last_predicted_date else None
            result.append(item)
        return result

    @staticmethod
    def _row_to_dict(row: MeasurementIngestionDaily) -> Dict[str, Any]:
        return {
            "site_id": row.site_id,
            "device_id": row.device_id,
            "branch_id": row.branch_id,
            "business_date": row.business_date.isoformat() if row.business_date else None,
            "point_count": row.point_count,
            "expected_point_count": row.expected_point_count,
            "is_complete": bool(row.is_complete),
            "first_seen_at": row.first_seen_at.isoformat() if row.first_seen_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    # ------------------------------------------------------------------
    # device_prediction_cursor：按设备预测游标
    # ------------------------------------------------------------------

    def get_cursor(
        self, site_id: str, device_id: str, branch_id: str,
    ) -> Optional[Dict[str, Any]]:
        """查单个设备的预测游标，不存在返回 None。"""
        with self._adapter.get_sync_session() as session:
            row = session.get(
                DevicePredictionCursor,
                {"site_id": site_id, "device_id": device_id, "branch_id": branch_id},
            )
            if row is None:
                return None
            return self._cursor_to_dict(row)

    def advance_cursor(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        predicted_time: datetime,
        *,
        model_version_id: Optional[str] = None,
        predicted_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """推进设备预测游标（只应在预测成功写入 PredictionRecord 后调用）。

        Upsert 语义：不存在则新建；存在则覆盖 last_predicted_time。
        ``predicted_time`` 是本次预测的 cutoff 时刻（精确到秒），替代旧的 business_date。
        """
        now = predicted_at or datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            payload = {
                "site_id": site_id,
                "device_id": device_id,
                "branch_id": branch_id,
                "last_predicted_time": predicted_time,
                "last_predicted_at": now,
                "model_version_id": model_version_id,
                "updated_at": now,
            }
            stmt = mysql_insert(DevicePredictionCursor).values(**payload)
            update_cols = {
                col: stmt.inserted[col]
                for col in (
                    "last_predicted_time", "last_predicted_at",
                    "model_version_id", "updated_at",
                )
            }
            stmt = stmt.on_duplicate_key_update(**update_cols)
            session.execute(stmt)
            row = session.get(
                DevicePredictionCursor,
                {"site_id": site_id, "device_id": device_id, "branch_id": branch_id},
            )
            result = self._cursor_to_dict(row)
        logger.info(
            "ingestion_tracker: 设备(%s,%s,%s) 预测游标推进至 %s",
            site_id, device_id, branch_id, predicted_time,
        )
        return result

    @staticmethod
    def _cursor_to_dict(row: DevicePredictionCursor) -> Dict[str, Any]:
        return {
            "site_id": row.site_id,
            "device_id": row.device_id,
            "branch_id": row.branch_id,
            "last_predicted_time": (
                row.last_predicted_time.isoformat()
                if row.last_predicted_time else None
            ),
            "last_predicted_at": row.last_predicted_at.isoformat() if row.last_predicted_at else None,
            "model_version_id": row.model_version_id,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
# @AI_GENERATED: end
