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

from sqlalchemy import and_, case, func, inspect as sa_inspect, select, update
from sqlalchemy.exc import OperationalError
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

#: 点级路径可检测门槛：与训练侧 MIN_OCCUPIED_SLOTS 对齐（173/288 ≈ 60%）。
#: 光伏白天完整日常见约 200 实测点，达不到 288×90%，不能再用 is_complete 卡点级。
SEQ_MIN_OCCUPIED_SLOTS = 173


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
        self._cursor_has_partition_columns: Optional[bool] = None

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

    def query_site_overview(
        self,
        business_date: Optional[date] = None,
        *,
        modeling_path: str = "legacy_day",
    ) -> List[Dict[str, Any]]:
        """按站点聚合完整性总览：设备总数、已完整设备数、完成度。

        Args:
            business_date: 指定业务日；None 时返回每个站点"最新业务日"的总览
                （按站点分组取 MAX(business_date)）。
            modeling_path: 当前日滚路径。点级用占用门槛计「完整」，天级用 is_complete。
        Returns:
            每个站点一条：site_id / business_date / device_total /
            device_complete / device_seq_ready / completion_ratio / latest_updated_at。
        """
        path = str(modeling_path or "legacy_day").strip() or "legacy_day"
        ready_flag = self._path_ready_flag(path)
        seq_ready_flag = case(
            (MeasurementIngestionDaily.point_count >= SEQ_MIN_OCCUPIED_SLOTS, 1),
            else_=0,
        )
        with self._adapter.get_sync_session() as session:
            if business_date is not None:
                stmt = (
                    select(
                        MeasurementIngestionDaily.site_id,
                        MeasurementIngestionDaily.business_date,
                        func.count().label("device_total"),
                        func.sum(ready_flag).label("device_complete"),
                        func.sum(seq_ready_flag).label("device_seq_ready"),
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
                        func.sum(ready_flag).label("device_complete"),
                        func.sum(seq_ready_flag).label("device_seq_ready"),
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
            device_seq_ready = int(row.device_seq_ready or 0)
            result.append({
                "site_id": row.site_id,
                "business_date": row.business_date.isoformat() if row.business_date else None,
                "device_total": device_total,
                "device_complete": device_complete,
                "device_seq_ready": device_seq_ready,
                "completion_ratio": round(device_complete / device_total, 4) if device_total else 0.0,
                "latest_updated_at": row.latest_updated_at.isoformat() if row.latest_updated_at else None,
                "modeling_path": path,
                "ready_criterion": (
                    "seq_occupied_173" if path == "seq_annotation" else "legacy_no_completeness_gate"
                ),
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
        self,
        site_id: Optional[str] = None,
        *,
        slot: str = "pv_fault",
        modeling_path: str = "legacy_day",
    ) -> List[Dict[str, Any]]:
        """查当前路径已可检测、但尚未被该路径游标处理过的设备-天。

        点级才走占用闸门：实测点数 ≥ ``SEQ_MIN_OCCUPIED_SLOTS``。
        天级不走完整等待，凡到达表里有的设备-天都可以进待预测（与检测侧
        ``admissible_for_path(legacy_day)=True`` 一致）。
        游标按 ``slot + modeling_path`` 分区比较，两条路径互不冒充。
        """
        path = str(modeling_path or "legacy_day").strip() or "legacy_day"
        slot_key = str(slot or "pv_fault").strip() or "pv_fault"
        with self._adapter.get_sync_session() as session:
            join_parts = [
                MeasurementIngestionDaily.site_id == DevicePredictionCursor.site_id,
                MeasurementIngestionDaily.device_id == DevicePredictionCursor.device_id,
                MeasurementIngestionDaily.branch_id == DevicePredictionCursor.branch_id,
            ]
            if self._cursor_partition_columns_ready(session):
                join_parts.extend(
                    (
                        DevicePredictionCursor.slot == slot_key,
                        DevicePredictionCursor.modeling_path == path,
                    )
                )
            stmt = (
                select(MeasurementIngestionDaily, DevicePredictionCursor.last_predicted_time)
                .outerjoin(DevicePredictionCursor, and_(*join_parts))
            )
            # @AI_GENERATED: TSC 共用点级 173 占用预检
            if path in ("seq_annotation", "tsc"):
            # @AI_GENERATED: end
                stmt = stmt.where(
                    MeasurementIngestionDaily.point_count >= SEQ_MIN_OCCUPIED_SLOTS
                )
            if site_id is not None:
                stmt = stmt.where(MeasurementIngestionDaily.site_id == site_id)
            try:
                rows = session.execute(stmt).all()
            except OperationalError as exc:
                session.rollback()
                err = str(exc)
                if "Unknown column" not in err or "slot" not in err:
                    raise
                self._cursor_has_partition_columns = False
                logger.warning("待预测列表命中未迁移游标表，回退三元组 JOIN: %s", err[:200])
                triple_join = and_(
                    MeasurementIngestionDaily.site_id == DevicePredictionCursor.site_id,
                    MeasurementIngestionDaily.device_id == DevicePredictionCursor.device_id,
                    MeasurementIngestionDaily.branch_id == DevicePredictionCursor.branch_id,
                )
                stmt = (
                    select(MeasurementIngestionDaily, DevicePredictionCursor.last_predicted_time)
                    .outerjoin(DevicePredictionCursor, triple_join)
                )
                # @AI_GENERATED: TSC 共用点级 173 占用预检
                if path in ("seq_annotation", "tsc"):
                # @AI_GENERATED: end
                    stmt = stmt.where(
                        MeasurementIngestionDaily.point_count >= SEQ_MIN_OCCUPIED_SLOTS
                    )
                if site_id is not None:
                    stmt = stmt.where(MeasurementIngestionDaily.site_id == site_id)
                rows = session.execute(stmt).all()

        result = []
        for ingestion_row, last_predicted_time in rows:
            last_predicted_date = last_predicted_time.date() if last_predicted_time else None
            if last_predicted_date is not None and ingestion_row.business_date <= last_predicted_date:
                continue
            item = self._row_to_dict(ingestion_row)
            item["last_predicted_business_date"] = last_predicted_date.isoformat() if last_predicted_date else None
            item["modeling_path"] = path
            result.append(item)
        return result

    # @AI_GENERATED
    def reset_path_cursors(
        self,
        *,
        slot: str = "pv_fault",
        modeling_path: Optional[str] = None,
        device_scope: Optional[List[Dict[str, str]]] = None,
    ) -> int:
        """清空指定槽位（可选路径）的设备预测游标，不删设备行。

        Parameters
        ----------
        device_scope : 可选设备三元组列表，每项含 site_id/device_id/branch_id。
            传入时只重置列表中的设备游标，不动其他设备——避免两千多台逐台
            打 MAX(time) 造成重置后第一轮像卡死。
            不传（None）则保持旧行为：清空该 slot 下全部设备。
        """
        now = datetime.utcnow()
        slot_key = str(slot or "pv_fault").strip() or "pv_fault"
        with self._adapter.get_sync_session() as session:
            stmt = update(DevicePredictionCursor)
            if self._cursor_partition_columns_ready(session):
                stmt = stmt.where(DevicePredictionCursor.slot == slot_key)
                if modeling_path:
                    stmt = stmt.where(
                        DevicePredictionCursor.modeling_path == str(modeling_path).strip()
                    )
            if device_scope:
                # 只重置指定设备列表；用 OR 拼三元组条件
                from sqlalchemy import and_, or_, tuple_
                triplets = [
                    tuple_(
                        DevicePredictionCursor.site_id,
                        DevicePredictionCursor.device_id,
                        DevicePredictionCursor.branch_id,
                    ).in_(
                        [
                            (d["site_id"], d["device_id"], d["branch_id"])
                            for d in device_scope
                        ]
                    )
                ]
                stmt = stmt.where(*triplets)
            result = session.execute(
                stmt.values(last_predicted_time=None, updated_at=now)
            )
            return int(result.rowcount or 0)
    # @AI_GENERATED: end

    def _cursor_partition_columns_ready(self, session: Any) -> bool:
        """公司库若未跑双路径迁移，device_prediction_cursor 没有 slot/modeling_path。"""
        if self._cursor_has_partition_columns is not None:
            return self._cursor_has_partition_columns
        try:
            columns = {
                str(col.get("name") or "")
                for col in sa_inspect(session.get_bind()).get_columns("device_prediction_cursor")
            }
            ready = "slot" in columns and "modeling_path" in columns
        except Exception as exc:  # noqa: BLE001 — 探测失败时按旧表结构查询，避免整页 500
            logger.warning("探测 device_prediction_cursor 分区列失败，按旧结构查询: %s", exc)
            ready = False
        if not ready:
            logger.warning(
                "device_prediction_cursor 缺少 slot/modeling_path，待预测列表回退三元组 JOIN。"
                "点级游标隔离需要执行 scripts/migrations/20260816_add_dual_path_runtime_schema.py"
            )
        self._cursor_has_partition_columns = ready
        return ready

    # @AI_GENERATED: TSC 共用点级 173 占用预检门槛（真正推理还需全天覆盖等额外条件）。
    @staticmethod
    def _path_ready_flag(modeling_path: str):
        """站点总览用的路径就绪计数。点级和 TSC 走占用闸门；天级有到达即计就绪。"""
        if str(modeling_path or "") in ("seq_annotation", "tsc"):
            return case(
                (MeasurementIngestionDaily.point_count >= SEQ_MIN_OCCUPIED_SLOTS, 1),
                else_=0,
            )
        return case((MeasurementIngestionDaily.point_count > 0, 1), else_=0)
    # @AI_GENERATED: end

    @staticmethod
    def _row_to_dict(row: MeasurementIngestionDaily) -> Dict[str, Any]:
        point_count = int(row.point_count or 0)
        return {
            "site_id": row.site_id,
            "device_id": row.device_id,
            "branch_id": row.branch_id,
            "business_date": row.business_date.isoformat() if row.business_date else None,
            "point_count": point_count,
            "expected_point_count": row.expected_point_count,
            "is_complete": bool(row.is_complete),
            "is_seq_ready": point_count >= SEQ_MIN_OCCUPIED_SLOTS,
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
