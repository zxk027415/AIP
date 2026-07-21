# -*- coding: utf-8 -*-
"""自由时间窗打标：审核页框选区间 → 专属窗口键样本 → 累计训练集。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.iterative_labeling.cumulative_training import CumulativeTrainingService
from services.iterative_labeling.label_registry import LabelRegistryService
from services.iterative_labeling.pv_training_workspace import PVTrainingWorkspaceService
from services.iterative_labeling.review_session import ReviewSessionService

logger = logging.getLogger(__name__)


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00").replace(" ", "T"))


def _intervals_overlap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def freeform_time_window_key(t_start: str, t_end: str) -> str:
    """Stable window key so feature engineering aggregates the brushed span as one sample."""
    start = _parse_ts(t_start).strftime("%Y-%m-%dT%H:%M:%S")
    end = _parse_ts(t_end).strftime("%Y-%m-%dT%H:%M:%S")
    return f"{start}__{end}#freeform"


def freeform_unit_key(
    site_id: Any,
    device_id: Any,
    branch_id: Any,
    t_start: str,
    t_end: str,
) -> str:
    return (
        f"{site_id}|{device_id}|{branch_id}|freeform|"
        f"{_parse_ts(t_start).strftime('%Y-%m-%dT%H:%M:%S')}|"
        f"{_parse_ts(t_end).strftime('%Y-%m-%dT%H:%M:%S')}"
    )


class FreeformLabelingService:
    """Create / list / revoke freeform labels bound to a review session."""

    def __init__(
        self,
        slot: str = "pv_fault",
        *,
        review_service: Optional[ReviewSessionService] = None,
        registry: Optional[LabelRegistryService] = None,
        workspace: Optional[PVTrainingWorkspaceService] = None,
        cumulative: Optional[CumulativeTrainingService] = None,
    ):
        self.slot = slot
        self.review_service = review_service or ReviewSessionService(slot=slot)
        self.registry = registry or LabelRegistryService(slot=slot)
        self.workspace = workspace or PVTrainingWorkspaceService()
        self.cumulative = cumulative or CumulativeTrainingService(slot=slot)

    def list_labels(self, review_id: str) -> List[Dict[str, Any]]:
        session = self.review_service.get_session(review_id)
        if not session:
            raise KeyError(review_id)
        labels = session.get("freeform_labels") or []
        return list(labels) if isinstance(labels, list) else []

    def create_label(
        self,
        review_id: str,
        *,
        t_start: str,
        t_end: str,
        action_type: str,
        reviewer: str = "operator",
        verdict_label: Optional[int] = None,
        new_label_name: Optional[str] = None,
        source_unit_key: Optional[str] = None,
        site_id: Optional[Any] = None,
        device_id: Optional[Any] = None,
        branch_id: Optional[Any] = None,
    ) -> Dict[str, Any]:
        session = self.review_service.get_session(review_id)
        if not session:
            raise KeyError(review_id)

        start = _parse_ts(t_start)
        end = _parse_ts(t_end)
        if end <= start:
            raise ValueError("t_end 必须晚于 t_start")

        ctx = session.get("prediction_context") or {}
        source_csv_path = str(ctx.get("source_csv_path") or "").strip()
        if not source_csv_path:
            raise ValueError("审核会话缺少 prediction_context.source_csv_path")

        # Resolve device identity from source unit when omitted.
        if source_unit_key:
            for unit in session.get("units") or []:
                if unit.get("unit_key") == source_unit_key:
                    site_id = site_id if site_id is not None else unit.get("site_id")
                    device_id = device_id if device_id is not None else unit.get("device_id")
                    branch_id = branch_id if branch_id is not None else unit.get("branch_id")
                    break
        if device_id is None:
            raise ValueError("缺少 device_id（或有效的 source_unit_key）")

        existing = self.list_labels(review_id)
        for item in existing:
            if str(item.get("site_id")) != str(site_id):
                continue
            if str(item.get("device_id")) != str(device_id):
                continue
            if str(item.get("branch_id")) != str(branch_id):
                continue
            if _intervals_overlap(
                start,
                end,
                _parse_ts(str(item["t_start"])),
                _parse_ts(str(item["t_end"])),
            ):
                raise ValueError(
                    f"与已有自由窗标注重叠: {item.get('unit_key')}"
                )

        if action_type == "new_label":
            if not new_label_name or not str(new_label_name).strip():
                raise ValueError("new_label 需要 new_label_name")
            allocated = self.registry.allocate_label(str(new_label_name).strip())
            label_id = int(allocated["label_id"])
        elif action_type == "correct":
            if verdict_label is None:
                raise ValueError("correct 需要 verdict_label")
            label_id = int(verdict_label)
        else:
            raise ValueError("action_type 仅支持 correct / new_label")

        window_key = freeform_time_window_key(t_start, t_end)
        unit_key = freeform_unit_key(site_id, device_id, branch_id, t_start, t_end)

        meta = self.workspace.create_confirmed_time_slice(
            source_path=source_csv_path,
            time_start=start.isoformat(sep=" "),
            time_end=end.isoformat(sep=" "),
            label_id=label_id,
            reviewer=reviewer,
            site_id=str(site_id) if site_id is not None else None,
            device_id=str(device_id),
            branch_id=str(branch_id) if branch_id is not None else None,
            time_window_override=window_key,
        )

        import_result = self.cumulative.register_labeled_dataset(
            dataset_path=meta["dataset_path"],
            source_name=f"freeform-{meta['slice_id']}",
            change_units=1,
        )

        record = {
            "unit_key": unit_key,
            "period_role": "freeform",
            "t_start": start.isoformat(sep=" "),
            "t_end": end.isoformat(sep=" "),
            "time_window": window_key,
            "verdict_label": label_id,
            "action_type": action_type,
            "reviewer": reviewer,
            "reviewed_at": datetime.utcnow().isoformat(),
            "source_review_id": review_id,
            "source_unit_key": source_unit_key,
            "site_id": site_id,
            "device_id": device_id,
            "branch_id": branch_id,
            "slice_id": meta["slice_id"],
            "dataset_path": meta["dataset_path"],
            "row_count": meta.get("row_count"),
            "cumulative_training": import_result,
        }
        existing.append(record)
        session["freeform_labels"] = existing
        self.review_service.review_repo.save_verdict(self.slot, review_id, session)
        logger.info("freeform label created review=%s unit=%s rows=%s", review_id, unit_key, meta.get("row_count"))
        return record

    def revoke_label(self, review_id: str, unit_key: str) -> Dict[str, Any]:
        session = self.review_service.get_session(review_id)
        if not session:
            raise KeyError(review_id)
        labels = list(session.get("freeform_labels") or [])
        kept = [item for item in labels if item.get("unit_key") != unit_key]
        if len(kept) == len(labels):
            raise KeyError(unit_key)
        session["freeform_labels"] = kept
        self.review_service.review_repo.save_verdict(self.slot, review_id, session)
        # Note: labeled_imports are content-hashed; revoke removes session pointer only.
        # Next snapshot rebuild still includes prior imports unless operator re-imports cleanly.
        # MVP documents this limitation; full ledger remove is phase-2.
        return {"revoked": True, "unit_key": unit_key, "remaining": len(kept)}
