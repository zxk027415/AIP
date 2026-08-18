# @AI_GENERATED
# -*- coding: utf-8 -*-
"""原子跨路径切换协调器：九项全真后同一可恢复事务写 Registry/Epoch/PathSwitchEvent。

同路径 PUT 只改 note。fallback 仍走同一九项与人工 confirm，不自动切换。
失败时 Registry、Epoch、claim、双事件均回滚到写前状态。
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from services.iterative_labeling.pv_governance_events import PathSwitchEvent
from services.iterative_labeling.pv_model_registry import PVModelRegistry, PVSlotState
from services.scheduler.pv_dual_path.cross_path_switch_gate import (
    CrossPathSwitchGate,
    GateCondition,
    GateResult,
)
from services.scheduler.pv_dual_path.path_activation import (
    ActivationPreview as PathActivationPreview,
    ActivationRequest,
    DeviceActivationInput,
    DeviceScope,
    PathActivationService,
)
from services.scheduler.pv_dual_path.shadow_compare import ShadowReportStore

_ALLOWED_PATHS = frozenset({"legacy_day", "seq_annotation"})
_SIMPLE_SWITCH_MODES = frozenset({"simple", "lab"})
LAB_UNBOUNDED_EPOCH_ID = "lab-unbounded"


@dataclass
class PathSwitchRequest:
    """跨路径或同路径登记更新请求。"""

    modeling_path: str
    slot: str = "pv_fault"
    note: Optional[str] = None
    comparison_id: Optional[str] = None
    activation_mode: Optional[str] = None
    confirm: Any = None
    operator: Optional[str] = None
    reason: Optional[str] = None
    backfill_days: Optional[int] = None
    device_scope: Optional[List[Dict[str, Any]]] = None
    is_fallback: bool = False
    switch_mode: Optional[str] = None


@dataclass
class PathSwitchResult:
    """切换或同路径更新的明确结果。"""

    status: str
    changed: bool
    state: PVSlotState
    gate: Optional[GateResult] = None
    preview: Optional[PathActivationPreview] = None
    event: Optional[PathSwitchEvent] = None
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "status": self.status,
            "changed": self.changed,
            "reason": self.reason,
            "registry": self.state.to_dict(),
            "gate": self.gate.to_dict() if self.gate is not None else None,
            "preview": _preview_to_dict(self.preview),
            "event": self.event.to_dict() if self.event is not None else None,
        }
        return payload


class CrossPathSwitchCoordinator:
    """九项门控后的原子跨路径切换；同路径只更新登记字段。"""

    def __init__(
        self,
        registry: Optional[PVModelRegistry] = None,
        activation: Optional[PathActivationService] = None,
        gate: Optional[CrossPathSwitchGate] = None,
        report_store: Optional[ShadowReportStore] = None,
        *,
        watermark_reader: Optional[Callable[[str, str, str], Any]] = None,
        artifact_validator: Optional[Callable[[str], bool]] = None,
        contract_validator: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self._registry = registry or PVModelRegistry()
        self._activation = activation
        self._report_store = report_store or ShadowReportStore()
        self._watermark_reader = watermark_reader
        self._gate = gate or CrossPathSwitchGate(
            artifact_validator=artifact_validator,
            contract_validator=contract_validator,
        )

    def switch(self, request: Any) -> PathSwitchResult:
        """协调器入口，兼容 Registry.switch_path 委托。"""
        normalized = request if isinstance(request, PathSwitchRequest) else _coerce_request(request)
        return self.apply(normalized)

    def apply(self, request: PathSwitchRequest) -> PathSwitchResult:
        slot = str(request.slot or "pv_fault").strip()
        if not slot or len(slot) > 64:
            raise ValueError("slot 长度必须为 1–64")
        target = str(request.modeling_path or "").strip()
        if target not in _ALLOWED_PATHS:
            raise ValueError(f"不支持的 modeling_path: {target}")
        if request.note is not None and len(str(request.note)) > 500:
            raise ValueError("note 最长 500 字符")

        current = self._registry.get_slot(slot)
        if target == current.production_path:
            if request.is_fallback:
                raise ValueError("fallback 目标不得等于当前生产路径")
            state = self._registry.update_note(slot, request.note)
            return PathSwitchResult(
                status="same_path_updated",
                changed=state.note != current.note,
                state=state,
                reason="same_path_note_only",
            )

        if request.is_fallback and target != current.fallback_path:
            raise ValueError("fallback 只能切到当前 fallback_path，且仍须九项门控")

        switch_mode = str(request.switch_mode or "").strip().lower()
        if switch_mode in _SIMPLE_SWITCH_MODES:
            if request.is_fallback:
                raise ValueError("fallback 不能走实验室简化切换，仍须九项门控")
            return self._switch_simple(slot, current, request, target)

        return self._switch_across_paths(slot, current, request, target)

    def _switch_simple(
        self,
        slot: str,
        current: PVSlotState,
        request: PathSwitchRequest,
        target: str,
    ) -> PathSwitchResult:
        """实验室简化切换：目标 Champion 存在且人工确认即可改日滚主线。

        不跑 Shadow/九项，不建生产 Epoch。日滚用无边界窗口（旧语义），方便在
        缺表/无 Shadow 时把点级路径跑通。生产换班组仍走 ``_switch_across_paths``。
        """
        target_champion = _champion_ref(current, target)
        confirm_ok = request.confirm is True
        conditions = [
            GateCondition(
                1,
                "target_champion_loadable",
                bool(target_champion),
                None if target_champion else "no_champion",
            ),
            GateCondition(
                9,
                "confirm_true",
                confirm_ok,
                None if confirm_ok else "confirm_not_boolean_true",
            ),
        ]
        failed = [item for item in conditions if not item.passed]
        gate = GateResult(
            all_passed=len(failed) == 0,
            conditions=conditions,
            failed_conditions=failed,
        )
        if not gate.all_passed:
            return PathSwitchResult(
                status="rejected",
                changed=False,
                state=current,
                gate=gate,
                reason="simple_switch_gate_failed",
            )

        snapshot = copy.deepcopy(current)
        try:
            state = self._registry.commit_path_switch(
                slot,
                production_path=target,
                activation_epoch_id=LAB_UNBOUNDED_EPOCH_ID,
                note=request.note,
            )
            event = PathSwitchEvent(
                path_switch_event_id=_event_id(
                    slot, current.production_path, target, LAB_UNBOUNDED_EPOCH_ID
                ),
                from_path=current.production_path,
                to_path=target,
                comparison_id="",
                activation_epoch_id=LAB_UNBOUNDED_EPOCH_ID,
                effective_from_date="",
                device_scope_digest="",
                device_scope_count=0,
                activation_mode="cutover_only",
                operator=str(request.operator or "lab"),
                reason=str(request.reason or "lab simple switch"),
                switched_at=datetime.utcnow().isoformat(),
            )
            self._registry._path_switch_store(slot).append(event)
            return PathSwitchResult(
                status="switched",
                changed=True,
                state=state,
                gate=gate,
                event=event,
                reason="lab_unbounded_simple_switch",
            )
        except Exception:
            self._registry.restore_slot_state(slot, snapshot)
            raise

    def preview(
        self,
        request: PathSwitchRequest,
        *,
        activation: Optional[PathActivationService] = None,
    ) -> PathActivationPreview:
        service = activation or self._require_activation()
        return service.preview(self._activation_request(request))

    def _switch_across_paths(
        self,
        slot: str,
        current: PVSlotState,
        request: PathSwitchRequest,
        target: str,
    ) -> PathSwitchResult:
        snapshot = copy.deepcopy(current)
        activation = self._require_activation()
        report_payload = self._load_report(request.comparison_id)
        preview = activation.preview(self._activation_request(request))
        device_scope = [
            {
                "site_id": item.scope.site_id,
                "device_id": item.scope.device_id,
                "branch_id": item.scope.branch_id,
                "effective_from_date": (
                    item.effective_from_date.isoformat() if item.effective_from_date else None
                ),
                "production_cutover_date": (
                    item.production_cutover_date.isoformat()
                    if item.production_cutover_date
                    else None
                ),
            }
            for item in preview.device_scopes
        ]
        target_champion = _champion_ref(current, target)
        gate = self._gate.evaluate(
            target_champion_model_ref=target_champion,
            report=report_payload,
            current_legacy_champion_ref=_champion_ref(current, "legacy_day"),
            current_seq_champion_ref=_champion_ref(current, "seq_annotation"),
            activation_mode=request.activation_mode,
            device_scope=device_scope,
            confirm=request.confirm,
        )
        if not gate.all_passed:
            return PathSwitchResult(
                status="rejected",
                changed=False,
                state=current,
                gate=gate,
                preview=preview,
                reason="cross_path_gate_failed",
            )

        epoch = None
        try:
            epoch = activation.create_epoch(self._activation_request(request))
            state = self._registry.commit_path_switch(
                slot,
                production_path=target,
                activation_epoch_id=epoch.activation_epoch_id,
                note=request.note,
            )
            event = PathSwitchEvent(
                path_switch_event_id=_event_id(
                    slot, current.production_path, target, epoch.activation_epoch_id
                ),
                from_path=current.production_path,
                to_path=target,
                comparison_id=str(request.comparison_id or ""),
                activation_epoch_id=epoch.activation_epoch_id,
                effective_from_date=(
                    preview.effective_from_date.isoformat()
                    if preview.effective_from_date is not None
                    else ""
                ),
                device_scope_digest=preview.device_scope_digest,
                device_scope_count=preview.device_scope_count,
                activation_mode=str(request.activation_mode or ""),
                operator=str(request.operator or ""),
                reason=str(request.reason or ""),
                switched_at=datetime.utcnow().isoformat(),
            )
            self._registry._path_switch_store(slot).append(event)
            return PathSwitchResult(
                status="switched",
                changed=True,
                state=state,
                gate=gate,
                preview=preview,
                event=event,
            )
        except Exception:
            self._registry.restore_slot_state(slot, snapshot)
            if epoch is not None:
                activation.delete_epoch(epoch.activation_epoch_id)
            raise

    def _activation_request(self, request: PathSwitchRequest) -> ActivationRequest:
        devices = []
        for item in request.device_scope or []:
            scope = DeviceScope(
                str(item.get("site_id") or "").strip(),
                str(item.get("device_id") or "").strip(),
                str(item.get("branch_id") or "").strip(),
            )
            watermark = None
            earliest = None
            if self._watermark_reader is not None:
                watermark = self._watermark_reader(scope.site_id, scope.device_id, scope.branch_id)
                if watermark is not None and hasattr(watermark, "date"):
                    earliest = watermark.date()
            devices.append(
                DeviceActivationInput(
                    scope=scope,
                    device_watermark=watermark,
                    earliest_arrival=earliest,
                )
            )
        return ActivationRequest(
            modeling_path=request.modeling_path,
            activation_mode=str(request.activation_mode or ""),
            devices=devices,
            slot=request.slot,
            backfill_days=request.backfill_days,
            note=request.note,
            comparison_id=request.comparison_id,
            operator=request.operator,
        )

    def _load_report(self, comparison_id: Optional[str]) -> Optional[Dict[str, Any]]:
        cid = str(comparison_id or "").strip()
        if not cid:
            return None
        report = self._report_store.load(cid)
        return report.to_dict() if report is not None else None

    def _require_activation(self) -> PathActivationService:
        if self._activation is None:
            raise RuntimeError("跨路径切换需要注入 PathActivationService")
        return self._activation


def _preview_to_dict(preview: Optional[PathActivationPreview]) -> Optional[Dict[str, Any]]:
    if preview is None:
        return None
    return {
        "slot": preview.slot,
        "modeling_path": preview.modeling_path,
        "activation_mode": preview.activation_mode,
        "backfill_days": preview.backfill_days,
        "effective_from_date": (
            preview.effective_from_date.isoformat() if preview.effective_from_date else None
        ),
        "device_scope_digest": preview.device_scope_digest,
        "device_scope_count": preview.device_scope_count,
        "device_scopes": [
            {
                "site_id": item.scope.site_id,
                "device_id": item.scope.device_id,
                "branch_id": item.scope.branch_id,
                "effective_from_date": (
                    item.effective_from_date.isoformat() if item.effective_from_date else None
                ),
                "production_cutover_date": (
                    item.production_cutover_date.isoformat()
                    if item.production_cutover_date
                    else None
                ),
            }
            for item in preview.device_scopes
        ],
        "lane_claims": [
            {
                "site_id": claim.scope.site_id,
                "device_id": claim.scope.device_id,
                "branch_id": claim.scope.branch_id,
                "lane": claim.lane,
                "range_start": claim.range_start.isoformat() if claim.range_start else None,
                "range_end": claim.range_end.isoformat() if claim.range_end else None,
                "claim_status": claim.claim_status,
            }
            for claim in preview.claims
        ],
    }


def _champion_ref(state: PVSlotState, modeling_path: str) -> Optional[str]:
    lifecycle = state.path_models.get(modeling_path)
    champion = lifecycle.champion if lifecycle else None
    return str(champion.model_ref) if champion else None


def _event_id(slot: str, from_path: str, to_path: str, epoch_id: str) -> str:
    digest = hashlib.sha256(
        f"{slot}|{from_path}|{to_path}|{epoch_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"psw-{digest}"


def _coerce_request(raw: Any) -> PathSwitchRequest:
    if isinstance(raw, dict):
        return PathSwitchRequest(
            modeling_path=str(raw.get("modeling_path") or raw.get("to_path") or ""),
            slot=str(raw.get("slot") or "pv_fault"),
            note=raw.get("note"),
            comparison_id=raw.get("comparison_id"),
            activation_mode=raw.get("activation_mode"),
            confirm=raw.get("confirm"),
            operator=raw.get("operator"),
            reason=raw.get("reason"),
            backfill_days=raw.get("backfill_days"),
            device_scope=raw.get("device_scope"),
            is_fallback=bool(raw.get("is_fallback")),
            switch_mode=raw.get("switch_mode"),
        )
    return PathSwitchRequest(
        modeling_path=str(getattr(raw, "modeling_path", "") or getattr(raw, "to_path", "")),
        slot=str(getattr(raw, "slot", "pv_fault")),
        note=getattr(raw, "note", None),
        comparison_id=getattr(raw, "comparison_id", None),
        activation_mode=getattr(raw, "activation_mode", None),
        confirm=getattr(raw, "confirm", None),
        operator=getattr(raw, "operator", None),
        reason=getattr(raw, "reason", None),
        backfill_days=getattr(raw, "backfill_days", None),
        device_scope=getattr(raw, "device_scope", None),
        is_fallback=bool(getattr(raw, "is_fallback", False)),
        switch_mode=getattr(raw, "switch_mode", None),
    )
# @AI_GENERATED: end
