# -*- coding: utf-8 -*-
"""自由时间窗打标：审核页框选区间 → PointLabelService（pv_fault）或 legacy 切片。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.iterative_labeling.cumulative_training import CumulativeTrainingService
from services.iterative_labeling.label_registry import LabelRegistryService
from services.iterative_labeling.point_label_service import PointLabelService, PointLabelValidationError
from services.iterative_labeling.point_label_wiring import submit_freeform_as_point_label
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
        point_label_service: Optional[PointLabelService] = None,
    ):
        self.slot = slot
        self.review_service = review_service or ReviewSessionService(slot=slot)
        self.registry = registry or LabelRegistryService(slot=slot)
        self.workspace = workspace or PVTrainingWorkspaceService()
        self.cumulative = cumulative or CumulativeTrainingService(slot=slot)
        self.point_label_service = point_label_service

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

        if self.slot == "pv_fault":
            prediction_context = session.get("prediction_context") or {}
            granularity = str(prediction_context.get("prediction_granularity") or "").strip()
            if granularity != "point":
                raise ValueError(
                    "自由时间窗只允许 prediction_granularity=point 的审核会话；"
                    "缺失或 day 会话禁止猜测点路径"
                )
            if self.point_label_service is None:
                raise RuntimeError("pv_fault 点标签服务不可用，已拒绝降级到 legacy 切片")

        start = _parse_ts(t_start)
        end = _parse_ts(t_end)
        if end <= start:
            raise ValueError("t_end 必须晚于 t_start")

        if source_unit_key:
            for unit in session.get("units") or []:
                if unit.get("unit_key") == source_unit_key:
                    site_id = site_id if site_id is not None else unit.get("site_id")
                    device_id = device_id if device_id is not None else unit.get("device_id")
                    branch_id = branch_id if branch_id is not None else unit.get("branch_id")
                    break
        if device_id is None:
            raise ValueError("缺少 device_id（或有效的 source_unit_key）")
        branch_id = branch_id if branch_id is not None else "1"
        site_id = str(site_id) if site_id is not None else ""

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

        unit_key = freeform_unit_key(site_id, device_id, branch_id, t_start, t_end)
        window_key = freeform_time_window_key(t_start, t_end)

        if self.slot == "pv_fault" and self.point_label_service is not None:
            return self._create_point_label(
                review_id=review_id,
                session=session,
                site_id=site_id,
                device_id=str(device_id),
                branch_id=str(branch_id),
                start=start,
                end=end,
                label_id=label_id,
                action_type=action_type,
                reviewer=reviewer,
                source_unit_key=source_unit_key,
                unit_key=unit_key,
                window_key=window_key,
            )

        return self._create_legacy_slice(
            review_id=review_id,
            session=session,
            site_id=site_id,
            device_id=device_id,
            branch_id=branch_id,
            start=start,
            end=end,
            label_id=label_id,
            action_type=action_type,
            reviewer=reviewer,
            source_unit_key=source_unit_key,
            unit_key=unit_key,
            window_key=window_key,
            t_start=t_start,
            t_end=t_end,
        )

    def _create_point_label(
        self,
        *,
        review_id: str,
        session: Dict[str, Any],
        site_id: str,
        device_id: str,
        branch_id: str,
        start: datetime,
        end: datetime,
        label_id: int,
        action_type: str,
        reviewer: str,
        source_unit_key: Optional[str],
        unit_key: str,
        window_key: str,
    ) -> Dict[str, Any]:
        service = self.point_label_service
        assert service is not None
        overlaps = service._labels.query_active_human_range_overlap(
            site_id, device_id, branch_id, start, end,
        )
        if overlaps:
            raise ValueError(
                f"与已有 human_range 标注重叠: {overlaps[0].get('op_id')}"
            )

        pl_result = submit_freeform_as_point_label(
            service,
            review_id=review_id,
            site_id=site_id,
            device_id=device_id,
            branch_id=branch_id,
            t_start=start,
            t_end=end,
            label_id=label_id,
            reviewer=reviewer,
        )
        # @AI_GENERATED: point label 回流显式携带逐点来源，避免误计纯天级 Seq 水位
        cumulative_training = self.cumulative.admit_point_label_op(
            review_id=review_id,
            op_id=pl_result["op_id"],
            verdict={
                "is_ground_truth": True,
                "action_type": action_type,
                "verdict_label": label_id,
                "reviewer": reviewer,
            },
            label_source="human_range",
        )
        # @AI_GENERATED: end

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
            "op_id": pl_result["op_id"],
            "companion_op_ids": pl_result.get("companion_op_ids") or [],
            "materialized": pl_result.get("materialized"),
            "cumulative_training": cumulative_training,
            "label_backend": "point_label",
            "dataset_path": "",
            "row_count": (pl_result.get("materialized") or {}).get("row_count"),
        }
        existing = list(session.get("freeform_labels") or [])
        existing.append(record)
        session["freeform_labels"] = existing
        self.review_service.review_repo.save_verdict(self.slot, review_id, session)
        logger.info(
            "freeform point_label created review=%s op=%s",
            review_id,
            pl_result["op_id"],
        )
        return record

    def _create_legacy_slice(
        self,
        *,
        review_id: str,
        session: Dict[str, Any],
        site_id: Any,
        device_id: Any,
        branch_id: Any,
        start: datetime,
        end: datetime,
        label_id: int,
        action_type: str,
        reviewer: str,
        source_unit_key: Optional[str],
        unit_key: str,
        window_key: str,
        t_start: str,
        t_end: str,
    ) -> Dict[str, Any]:
        ctx = session.get("prediction_context") or {}
        source_csv_path = str(ctx.get("source_csv_path") or "").strip()
        if not source_csv_path:
            raise ValueError("审核会话缺少 prediction_context.source_csv_path")

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
                raise ValueError(f"与已有自由窗标注重叠: {item.get('unit_key')}")

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

        slot_key = str(self.slot or "").strip()
        # @AI_GENERATED: pv_tsc joins the unified session-level ledger on completion.
        if slot_key in {"pv_day", "pv_point", "pv_tsc"}:
            import_result: Dict[str, Any] = {"deferred_cumulative_admission": True}
        else:
            import_result = self.cumulative.register_labeled_dataset(
                dataset_path=meta["dataset_path"],
                source_name=f"freeform-{meta['slice_id']}",
                change_units=1,
            )
        # @AI_GENERATED: end

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
            "label_backend": "legacy_slice",
        }
        existing.append(record)
        session["freeform_labels"] = existing
        self.review_service.review_repo.save_verdict(self.slot, review_id, session)
        logger.info("freeform legacy label created review=%s unit=%s", review_id, unit_key)
        return record

    def revoke_label(self, review_id: str, unit_key: str) -> Dict[str, Any]:
        session = self.review_service.get_session(review_id)
        if not session:
            raise KeyError(review_id)
        labels = list(session.get("freeform_labels") or [])
        target = next((item for item in labels if item.get("unit_key") == unit_key), None)
        if target is None:
            raise KeyError(unit_key)

        revoke_result: Dict[str, Any] = {"revoked": True, "unit_key": unit_key}
        if (
            self.slot == "pv_fault"
            and self.point_label_service is not None
            and target.get("op_id")
        ):
            try:
                revoke_result = self.point_label_service.revoke_op(str(target["op_id"]))
                # @AI_GENERATED: 撤销逐点事实时沿用原投影来源，只推进对应路径变更计数
                self.cumulative.admit_point_label_op(
                    review_id=review_id,
                    op_id=str(target["op_id"]),
                    verdict={"is_ground_truth": False, "action_type": "skip"},
                    label_source="human_range",
                )
                # @AI_GENERATED: end
            except PointLabelValidationError as exc:
                raise ValueError(str(exc)) from exc

        kept = [item for item in labels if item.get("unit_key") != unit_key]
        session["freeform_labels"] = kept
        self.review_service.review_repo.save_verdict(self.slot, review_id, session)
        revoke_result["remaining"] = len(kept)
        return revoke_result
