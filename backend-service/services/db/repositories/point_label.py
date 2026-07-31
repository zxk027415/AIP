# -*- coding: utf-8 -*-
"""
services/db/repositories/point_label.py — 逐点标签数据仓库

PointLabelRepository: 封装 point_labels（逐点标签）与 label_ops（标注操作日志）
两张表的所有 CRUD 操作，是光伏故障逐点标签重构（pv-fault-label-segment-redesign）
存储层的唯一数据库访问入口。

标签唯一事实来源：point_labels 存生效标签（由 LabelMaterializer 物化产生），
label_ops 存标注操作日志（撤销与审计的唯一单元）。两表均不含测量数值列。

主要方法：
  - upsert_points          批量 upsert 逐点标签（物化结果写入）
  - query_points           按设备三元组 + 时间范围查逐点标签
  - insert_op              写入一条标注操作
  - revoke_op              把一条操作置为 revoked（不物理删除）
  - query_active_ops       查某设备维度下与给定时间范围有交集的 active 操作
  - query_ops_by_parent    按 parent_op_id 查伴生操作（K4 联动撤销用）
  - query_op_by_id         按 op_id 查单条操作

对应设计文档 `.kiro/specs/pv-fault-label-segment-redesign/design.md` 组件 1、2。

Requirements: 2.5, 2.6, 21.3
"""

# @AI_GENERATED
from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, or_, select, text
from sqlalchemy.dialects.mysql import insert as mysql_insert

from services.db.adapter import DBAdapter
from services.db.models.pv_fault import LabelOp, PointLabel

logger = logging.getLogger(__name__)

# 单批 upsert 的行数上限，避免单条 SQL 过大
_BATCH_SIZE = 500


class PointLabelRepository:
    """
    逐点标签数据仓库。

    所有操作通过 DBAdapter 获取同步 Session，在事务内完成写入/查询。

    用法示例：
        from services.db.config import DBConfig
        from services.db.adapter import DBAdapter
        from services.db.repositories.point_label import PointLabelRepository

        adapter = DBAdapter(DBConfig())
        repo = PointLabelRepository(adapter)
        repo.insert_op({...})
        repo.upsert_points([...])
    """

    def __init__(self, adapter: DBAdapter) -> None:
        self._adapter = adapter

    # ------------------------------------------------------------------
    # point_labels：逐点标签
    # ------------------------------------------------------------------

    def upsert_points(self, rows: Sequence[Dict[str, Any]]) -> int:
        """按主键 (site_id, device_id, branch_id, time) upsert 逐点标签。

        每次调用是 LabelMaterializer 物化结果的落库入口：同一采样点被
        重复物化时覆盖旧值（`ON DUPLICATE KEY UPDATE`），不产生重复行，
        满足需求 2 第 11 条「同一采样点只有一条记录」。

        Args:
            rows: 每个 dict 至少含 site_id/device_id/branch_id/time/source/
                  priority/op_id/label_space_version，label_id 可为 None。

        Returns:
            实际写入（含更新）的行数。

        Requirements: 2.1, 2.11, 4.3
        """
        if not rows:
            return 0

        total = 0
        with self._adapter.get_sync_session() as session:
            for i in range(0, len(rows), _BATCH_SIZE):
                batch = list(rows[i : i + _BATCH_SIZE])
                stmt = mysql_insert(PointLabel).values(batch)
                update_cols = {
                    col: stmt.inserted[col]
                    for col in (
                        "label_id", "source", "priority", "op_id",
                        "label_space_version", "updated_at",
                    )
                }
                stmt = stmt.on_duplicate_key_update(**update_cols)
                result = session.execute(stmt)
                total += result.rowcount
        logger.info("upsert_points: rows=%d affected=%d", len(rows), total)
        return total

    def query_points(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: Optional[datetime] = None,
        t_end: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """按设备三元组 + 可选时间范围（半开区间 [t_start, t_end)）查逐点标签。

        结果按 time 升序，返回普通 dict 便于跨 session 使用。

        Requirements: 21.3
        """
        stmt = select(PointLabel).where(
            PointLabel.site_id == site_id,
            PointLabel.device_id == device_id,
            PointLabel.branch_id == branch_id,
        )
        if t_start is not None:
            stmt = stmt.where(PointLabel.time >= t_start)
        if t_end is not None:
            stmt = stmt.where(PointLabel.time < t_end)
        stmt = stmt.order_by(PointLabel.time.asc())

        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).scalars().all()
            result = [self._point_to_dict(r) for r in rows]
        return result

    def delete_points_in_range(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: datetime,
        t_end: datetime,
    ) -> int:
        """删除指定设备维度、指定半开区间内的逐点标签行。

        供 LabelMaterializer 重物化前清理旧结果使用（重物化 = 先删范围内旧行，
        再按当前 active 操作重新计算 upsert，避免范围收缩后遗留过期点）。

        Requirements: 4.7
        """
        from sqlalchemy import delete as sa_delete

        stmt = sa_delete(PointLabel).where(
            PointLabel.site_id == site_id,
            PointLabel.device_id == device_id,
            PointLabel.branch_id == branch_id,
            PointLabel.time >= t_start,
            PointLabel.time < t_end,
        )
        with self._adapter.get_sync_session() as session:
            result = session.execute(stmt)
        return result.rowcount

    @staticmethod
    def _point_to_dict(row: PointLabel) -> Dict[str, Any]:
        return {
            "site_id": row.site_id,
            "device_id": row.device_id,
            "branch_id": row.branch_id,
            "time": row.time,
            "label_id": row.label_id,
            "source": row.source,
            "priority": row.priority,
            "op_id": row.op_id,
            "label_space_version": row.label_space_version,
            "updated_at": row.updated_at,
        }

    # ------------------------------------------------------------------
    # label_ops：标注操作日志
    # ------------------------------------------------------------------

    def insert_op(self, op_data: Dict[str, Any]) -> Dict[str, Any]:
        """写入一条标注操作，`status` 未指定时默认为 `active`。

        Requirements: 2.2, 6.1
        """
        payload = dict(op_data)
        payload.setdefault("status", "active")
        op = LabelOp(**payload)
        with self._adapter.get_sync_session() as session:
            session.add(op)
            session.flush()
            session.refresh(op)
            result = self._op_to_dict(op)
        return result

    def revoke_op(self, op_id: str) -> bool:
        """把一条操作的 status 置为 revoked，不物理删除。

        Returns:
            True 表示找到并更新了该操作；False 表示 op_id 不存在。

        Requirements: 6.1, 6.2, 6.8
        """
        with self._adapter.get_sync_session() as session:
            op = session.get(LabelOp, op_id)
            if op is None:
                return False
            op.status = "revoked"
            op.updated_at = datetime.utcnow()
            session.add(op)
        return True

    def query_op_by_id(self, op_id: str) -> Optional[Dict[str, Any]]:
        """按 op_id 查单条操作，不存在返回 None。"""
        with self._adapter.get_sync_session() as session:
            op = session.get(LabelOp, op_id)
            if op is None:
                return None
            result = self._op_to_dict(op)
        return result

    def query_active_ops(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: Optional[datetime] = None,
        t_end: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """查某设备维度下与给定时间范围有交集的 active 操作。

        区间交集判定：操作 `[op.t_start, op.t_end)` 与查询范围
        `[t_start, t_end)` 有交集 ⟺ `op.t_start < t_end AND op.t_end > t_start`
        （查询范围为 None 时视为不限）。供 LabelMaterializer 物化时取覆盖点的
        候选操作集合，以及 PointLabelService 做 human_range 重叠检查。

        Requirements: 4.1, 5.11, 16.2
        """
        stmt = select(LabelOp).where(
            LabelOp.site_id == site_id,
            LabelOp.device_id == device_id,
            LabelOp.branch_id == branch_id,
            LabelOp.status == "active",
        )
        if t_end is not None:
            stmt = stmt.where(LabelOp.t_start < t_end)
        if t_start is not None:
            stmt = stmt.where(LabelOp.t_end > t_start)
        stmt = stmt.order_by(LabelOp.priority.desc(), LabelOp.created_at.desc())

        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).scalars().all()
            result = [self._op_to_dict(r) for r in rows]
        return result

    def query_active_human_range_overlap(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: datetime,
        t_end: datetime,
    ) -> List[Dict[str, Any]]:
        """查该设备维度下与给定区间重叠的 active `human_range` 操作。

        专供需求 5 第 11 条与需求 16 第 2 条的跨会话重叠检查：检查范围覆盖
        全表（不限 review_id），不像现状 `list_labels(review_id)` 只查单会话。

        Requirements: 5.11, 16.2
        """
        stmt = select(LabelOp).where(
            LabelOp.site_id == site_id,
            LabelOp.device_id == device_id,
            LabelOp.branch_id == branch_id,
            LabelOp.status == "active",
            LabelOp.source == "human_range",
            LabelOp.t_start < t_end,
            LabelOp.t_end > t_start,
        )
        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).scalars().all()
            result = [self._op_to_dict(r) for r in rows]
        return result

    def query_ops_by_parent(self, parent_op_id: str) -> List[Dict[str, Any]]:
        """按 parent_op_id 查伴生操作（K4 联动撤销：撤主操作时一并撤伴生操作）。

        Requirements: 6.3
        """
        stmt = select(LabelOp).where(LabelOp.parent_op_id == parent_op_id)
        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).scalars().all()
            result = [self._op_to_dict(r) for r in rows]
        return result

    def query_ops_by_migration_batch(self, migration_batch_id: str) -> List[Dict[str, Any]]:
        """按 migration_batch_id 查该批次迁入的全部操作（供批次回滚使用）。

        Requirements: 17.9, 17.10
        """
        stmt = select(LabelOp).where(LabelOp.migration_batch_id == migration_batch_id)
        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).scalars().all()
            result = [self._op_to_dict(r) for r in rows]
        return result

    def query_all_active_ops(self) -> List[Dict[str, Any]]:
        """查全部 active 操作（供 label_snapshot_hash 与快照隔离使用）。"""
        stmt = (
            select(LabelOp)
            .where(LabelOp.status == "active")
            .order_by(LabelOp.op_id.asc())
        )
        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).scalars().all()
            return [self._op_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 跨进程串行化（需求 21.6、21.7）
    # ------------------------------------------------------------------

    @contextmanager
    def device_advisory_lock(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        timeout_seconds: int = 30,
    ):
        """按设备三元组取 MySQL 顾问锁（`GET_LOCK`），实现**跨进程**串行化。

        进程内 `threading.RLock` 只能挡住同一进程的并发；多 worker / 多进程部署下
        两个进程会同时进入「写操作 + 重物化」临界区，破坏需求 21.7 的一致性。
        MySQL 的 `GET_LOCK` 是连接级命名锁，同一实例上跨连接互斥，正好兜住这个缺口。

        锁名为 `pl:{site}:{device}:{branch}` 的哈希（`GET_LOCK` 名称上限 64 字节，
        设备三元组拼接可能超长，故取哈希）。

        非 MySQL 后端或取锁失败时**降级为不加锁**并记 warning，不阻断业务
        （降级后仍有进程内锁保护，与修复前行为一致）。
        """
        lock_name = "pl_" + hashlib.sha256(
            f"{site_id}|{device_id}|{branch_id}".encode("utf-8")
        ).hexdigest()[:48]
        acquired = False
        session = None
        try:
            session_ctx = self._adapter.get_sync_session()
            session = session_ctx.__enter__()
            try:
                got = session.execute(
                    text("SELECT GET_LOCK(:name, :timeout)"),
                    {"name": lock_name, "timeout": int(timeout_seconds)},
                ).scalar()
                acquired = (got == 1)
                if not acquired:
                    logger.warning(
                        "未取到设备顾问锁(%s,%s,%s)，%ds 超时；降级为仅进程内锁",
                        site_id, device_id, branch_id, timeout_seconds,
                    )
            except Exception as exc:
                logger.warning("当前数据库不支持 GET_LOCK，降级为仅进程内锁: %s", exc)
            yield acquired
        finally:
            if session is not None:
                try:
                    if acquired:
                        session.execute(
                            text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name}
                        )
                except Exception as exc:
                    logger.warning("释放设备顾问锁失败(%s): %s", lock_name, exc)
                try:
                    session_ctx.__exit__(None, None, None)
                except Exception:
                    pass

    @staticmethod
    def _op_to_dict(row: LabelOp) -> Dict[str, Any]:
        return {
            "op_id": row.op_id,
            "site_id": row.site_id,
            "device_id": row.device_id,
            "branch_id": row.branch_id,
            "t_start": row.t_start,
            "t_end": row.t_end,
            "label_id": row.label_id,
            "source": row.source,
            "priority": row.priority,
            "status": row.status,
            "reviewer": row.reviewer,
            "source_ref": row.source_ref,
            "rest_of_day_policy": row.rest_of_day_policy,
            "parent_op_id": row.parent_op_id,
            "label_space_version": row.label_space_version,
            "migration_batch_id": row.migration_batch_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

# @AI_GENERATED: end
