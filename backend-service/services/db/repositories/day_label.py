# @AI_GENERATED
# -*- coding: utf-8 -*-
"""天标签独立仓储：只访问 day_label_ops/day_labels。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from services.db.adapter import DBAdapter
from services.db.models.pv_fault import DayLabel, DayLabelOp
from services.iterative_labeling.label_path_isolation import materialize_day_labels

_NEW_DAY_OP_SOURCES = frozenset({"human_day", "day_label", "day_import"})


class DayLabelRepository:
    """持久化天级裁决，并在同一事务内维护每设备日唯一生效标签。"""

    def __init__(self, adapter: DBAdapter) -> None:
        self._adapter = adapter

    def insert_op(self, op_data: Dict[str, Any]) -> Dict[str, Any]:
        """幂等写入天操作；已存在（含 revoked）时禁止普通重试复活。"""
        payload = dict(op_data)
        payload.setdefault("status", "active")
        source = str(payload.get("source") or "")
        if source not in _NEW_DAY_OP_SOURCES:
            raise ValueError(f"day_label_ops 禁止新写 source={source!r}")
        with self._adapter.get_sync_session() as session:
            existing = session.get(DayLabelOp, payload["op_id"])
            if existing is not None:
                immutable_fields = (
                    "site_id", "device_id", "branch_id", "business_date",
                    "t_start", "t_end", "label_id", "source", "priority",
                    "parent_op_id",
                )
                conflicts = [
                    field for field in immutable_fields
                    if getattr(existing, field) != payload.get(field)
                ]
                if conflicts:
                    raise ValueError(
                        f"day_label_ops op_id 冲突，字段不一致: {conflicts}"
                    )
                return self._op_to_dict(existing)
            op = DayLabelOp(**payload)
            session.add(op)
            session.flush()
            self._resync_label_locked(
                session,
                site_id=op.site_id,
                device_id=op.device_id,
                branch_id=op.branch_id,
                business_date=op.business_date,
            )
            session.refresh(op)
            return self._op_to_dict(op)

    def revoke_op(self, op_id: str) -> bool:
        with self._adapter.get_sync_session() as session:
            op = session.get(DayLabelOp, op_id)
            if op is None:
                return False
            op.status = "revoked"
            op.updated_at = datetime.utcnow()
            session.add(op)
            self._resync_label_locked(
                session,
                site_id=op.site_id,
                device_id=op.device_id,
                branch_id=op.branch_id,
                business_date=op.business_date,
            )
        return True

    def query_op_by_id(self, op_id: str) -> Optional[Dict[str, Any]]:
        with self._adapter.get_sync_session() as session:
            op = session.get(DayLabelOp, op_id)
            return self._op_to_dict(op) if op is not None else None

    def query_active_ops(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        business_date: date,
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(DayLabelOp)
            .where(
                DayLabelOp.site_id == site_id,
                DayLabelOp.device_id == device_id,
                DayLabelOp.branch_id == branch_id,
                DayLabelOp.business_date == business_date,
                DayLabelOp.status == "active",
            )
            .order_by(DayLabelOp.priority.desc(), DayLabelOp.created_at.desc())
        )
        with self._adapter.get_sync_session() as session:
            rows = session.execute(stmt).scalars().all()
            return [self._op_to_dict(row) for row in rows]

    def query_label(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        business_date: date,
    ) -> Optional[Dict[str, Any]]:
        key = (site_id, device_id, branch_id, business_date)
        with self._adapter.get_sync_session() as session:
            row = session.get(DayLabel, key)
            return self._label_to_dict(row) if row is not None else None

    def _resync_label_locked(
        self,
        session,
        *,
        site_id: str,
        device_id: str,
        branch_id: str,
        business_date: date,
    ) -> None:
        rows = session.execute(
            select(DayLabelOp).where(
                DayLabelOp.site_id == site_id,
                DayLabelOp.device_id == device_id,
                DayLabelOp.branch_id == branch_id,
                DayLabelOp.business_date == business_date,
                DayLabelOp.status == "active",
            )
        ).scalars().all()
        ops = [self._op_to_dict(row) for row in rows]
        winners = materialize_day_labels(ops)
        key = (site_id, device_id, branch_id, business_date)
        existing = session.get(DayLabel, key)
        if not winners:
            if existing is not None:
                session.delete(existing)
            return
        winner = dict(winners[0])
        winner["updated_at"] = datetime.utcnow()
        if existing is None:
            session.add(DayLabel(**winner))
            return
        for field, value in winner.items():
            setattr(existing, field, value)

    @staticmethod
    def _op_to_dict(row: DayLabelOp) -> Dict[str, Any]:
        return {
            "op_id": row.op_id,
            "site_id": row.site_id,
            "device_id": row.device_id,
            "branch_id": row.branch_id,
            "business_date": row.business_date,
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

    @staticmethod
    def _label_to_dict(row: DayLabel) -> Dict[str, Any]:
        return {
            "site_id": row.site_id,
            "device_id": row.device_id,
            "branch_id": row.branch_id,
            "business_date": row.business_date,
            "label_id": row.label_id,
            "source": row.source,
            "op_id": row.op_id,
            "reviewer": row.reviewer,
            "label_space_version": row.label_space_version,
            "updated_at": row.updated_at,
        }
# @AI_GENERATED: end
