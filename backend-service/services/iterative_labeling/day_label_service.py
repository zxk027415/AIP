# @AI_GENERATED
# -*- coding: utf-8 -*-
"""天标签服务：校验完整自然日后写 day_label_ops/day_labels。"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from services.db.repositories.day_label import DayLabelRepository
from services.iterative_labeling.label_registry import LabelRegistryService

DAY_SOURCE_PRIORITY = {
    "human_day": 80,
    "day_label": 10,
    "day_import": 10,
}
LEGACY_DAY_SOURCES = frozenset({"parquet_day_label"})


class DayLabelValidationError(ValueError):
    """天标签操作违反来源、边界或标签空间合同时抛出。"""

    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.detail = detail or {}


class DayLabelService:
    """天路径唯一写入口；不依赖点仓储，也不触发逐点物化。"""

    def __init__(
        self,
        repository: DayLabelRepository,
        label_registry: Optional[LabelRegistryService] = None,
        *,
        slot: str = "pv_fault",
    ) -> None:
        self._labels = repository
        self._registry = label_registry or LabelRegistryService(slot=slot)

    def submit_op(
        self,
        *,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: datetime,
        t_end: datetime,
        label_id: Optional[int],
        source: str,
        reviewer: Optional[str] = None,
        source_ref: Optional[str] = None,
        migration_batch_id: Optional[str] = None,
        priority: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if priority is not None:
            raise DayLabelValidationError(
                "priority 由 source 唯一推导，不允许显式指定",
                {"source": source, "given_priority": priority},
            )
        if source in LEGACY_DAY_SOURCES:
            raise DayLabelValidationError(
                "历史天来源仅允许迁移读取，新写入请使用 day_import",
                {"source": source, "path": "day"},
            )
        if source not in DAY_SOURCE_PRIORITY:
            raise DayLabelValidationError(
                "点来源或未知来源禁止进入天路径",
                {"source": source, "path": "day"},
            )
        business_date = self._validate_full_day(t_start, t_end)
        if source == "human_day":
            missing = [
                name
                for name, value in (("reviewer", reviewer), ("source_ref", source_ref))
                if not (value and str(value).strip())
            ]
            if missing:
                raise DayLabelValidationError(
                    "human_day 缺少人工审计字段", {"missing": missing}
                )
        label_space_version = self._validate_label_id(label_id)
        now = created_at or datetime.utcnow()
        op_id = self._make_op_id(
            site_id, device_id, branch_id, t_start, t_end, label_id, source
        )
        self._labels.insert_op({
            "op_id": op_id,
            "site_id": site_id,
            "device_id": device_id,
            "branch_id": branch_id,
            "business_date": business_date,
            "t_start": t_start,
            "t_end": t_end,
            "label_id": label_id,
            "source": source,
            "priority": DAY_SOURCE_PRIORITY[source],
            "status": "active",
            "reviewer": reviewer,
            "source_ref": source_ref,
            "rest_of_day_policy": None,
            "parent_op_id": None,
            "label_space_version": label_space_version,
            "migration_batch_id": migration_batch_id,
            "created_at": now,
            "updated_at": now,
        })
        return {
            "path": "day",
            "source": source,
            "op_id": op_id,
            "business_date": business_date.isoformat(),
        }

    def revoke_op(self, op_id: str) -> Dict[str, Any]:
        op = self._labels.query_op_by_id(op_id)
        if op is None:
            raise DayLabelValidationError("op_id 不存在", {"op_id": op_id})
        revoked = self._labels.revoke_op(op_id)
        return {"path": "day", "op_id": op_id, "revoked": revoked}

    @staticmethod
    def _validate_full_day(t_start: datetime, t_end: datetime):
        day_start = t_start.replace(hour=0, minute=0, second=0, microsecond=0)
        if t_start != day_start or t_end != day_start + timedelta(days=1):
            raise DayLabelValidationError(
                "天标签必须覆盖完整自然日",
                {"t_start": str(t_start), "t_end": str(t_end)},
            )
        return day_start.date()

    def _validate_label_id(self, label_id: Optional[int]) -> str:
        current = self._registry.get_current()
        version = str(current.get("label_space_version", "ls-v1"))
        if label_id is None:
            return version
        known_ids = {int(item["label_id"]) for item in current.get("labels", [])}
        if int(label_id) not in known_ids:
            raise DayLabelValidationError(
                "label_id 不在当前标签空间中",
                {
                    "label_id": label_id,
                    "label_space_version": version,
                    "known_label_ids": sorted(known_ids),
                },
            )
        return version

    @staticmethod
    def _make_op_id(
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: datetime,
        t_end: datetime,
        label_id: Optional[int],
        source: str,
    ) -> str:
        key = (
            f"{source}|{site_id}|{device_id}|{branch_id}|"
            f"{t_start.isoformat()}|{t_end.isoformat()}|{label_id}"
        )
        return f"op-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}"
# @AI_GENERATED: end
