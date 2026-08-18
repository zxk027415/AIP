# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PV Deployment Arena 只读适配：把 PVModelRegistry 映射成展示槽位。

`pv_fault` 的可写真相只在 PVModelRegistry。本适配器只读映射 Champion /
Challenger / Retired，供 Deployment Arena 展示；任何 Arena 写路径应抛
`PvFaultRegistryReadOnlyError`（code=`pv_fault_registry_read_only`）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.deployment.models import DeploymentSlot, ModelVersion
from services.iterative_labeling.pv_model_registry import (
    DEFAULT_SLOT,
    ModelRegistration,
    PVModelRegistry,
    PVSlotState,
)

PV_FAULT_SLOT = DEFAULT_SLOT
PV_FAULT_READ_ONLY_CODE = "pv_fault_registry_read_only"
PV_FAULT_READ_ONLY_MESSAGE = (
    "pv_fault 槽位只读，模型治理请前往 PV 双路径控制台；"
    "请使用 cumulative-training/modeling-paths 与 promote 接口，"
    "禁止通过 Deployment Arena 写入。"
)


def is_pv_fault_slot(slot: Optional[str]) -> bool:
    return str(slot or "").strip() == PV_FAULT_SLOT


def reject_pv_fault_write(slot: Optional[str]) -> None:
    if is_pv_fault_slot(slot):
        raise PvFaultRegistryReadOnlyError()


class PvFaultRegistryReadOnlyError(ValueError):
    """通用部署入口试图写入 pv_fault 时的结构化拒绝。"""

    def __init__(self, message: str = PV_FAULT_READ_ONLY_MESSAGE) -> None:
        super().__init__(message)
        self.code: str = PV_FAULT_READ_ONLY_CODE
        self.message: str = message

    def __repr__(self) -> str:  # pragma: no cover
        return f"PvFaultRegistryReadOnlyError(code={self.code!r}, message={self.message!r})"


@dataclass
class DeploymentSlotView:
    """Arena 展示用只读视图；不得当作 slots.json 可写快照。"""

    slot: str
    production_path: str
    fallback_path: str
    production_model: Optional[ModelVersion]
    shadow_models: List[ModelVersion]
    retired_models: List[ModelVersion]
    path_models: Dict[str, Any]
    updated_at: str
    note: Optional[str] = None
    active_activation_epoch_id: Optional[str] = None
    read_only: bool = True
    registry_source: str = "pv_model_registry"

    def to_deployment_slot(self) -> DeploymentSlot:
        # Arena 约定 retired 也挂在 shadow_models 里，用 status 区分
        shadows: List[ModelVersion] = list(self.shadow_models) + list(self.retired_models)
        return DeploymentSlot(
            slot=self.slot,
            production_model=self.production_model,
            shadow_models=shadows,
            prelaunch_models=[],
            auto_switch_enabled=False,
            updated_at=self.updated_at or datetime.utcnow().isoformat(),
        )


class PVDeploymentReadAdapter:
    """只把 PVModelRegistry 映射成 Arena 展示模型，不写 slots.json。"""

    def __init__(self, registry: Optional[PVModelRegistry] = None) -> None:
        self._registry = registry

    def _registry_or_default(self) -> PVModelRegistry:
        if self._registry is None:
            self._registry = PVModelRegistry()
        return self._registry

    def get_slot_view(self, slot: str = PV_FAULT_SLOT) -> DeploymentSlotView:
        if not is_pv_fault_slot(slot):
            raise ValueError("PVDeploymentReadAdapter 仅服务 pv_fault 槽位")
        state = self._registry_or_default().get_slot(PV_FAULT_SLOT)
        return self._map_state(state)

    def get_slot(self, slot: str = PV_FAULT_SLOT) -> DeploymentSlot:
        return self.get_slot_view(slot).to_deployment_slot()

    def _map_state(self, state: PVSlotState) -> DeploymentSlotView:
        production_path = state.production_path or "legacy_day"
        production_model: Optional[ModelVersion] = None
        shadows: List[ModelVersion] = []
        retired: List[ModelVersion] = []

        production_state = state.path_models.get(production_path)
        if production_state is not None and production_state.champion is not None:
            production_model = _to_model_version(
                production_state.champion,
                status="production",
                modeling_path=production_path,
            )

        for path_name, path_state in state.path_models.items():
            if path_state.champion is not None and path_name != production_path:
                shadows.append(
                    _to_model_version(
                        path_state.champion,
                        status="shadow",
                        modeling_path=path_name,
                    )
                )
            for challenger in path_state.challengers:
                shadows.append(
                    _to_model_version(
                        challenger,
                        status="shadow",
                        modeling_path=path_name,
                    )
                )
            for item in path_state.retired:
                retired.append(
                    _to_model_version(
                        item,
                        status="retired",
                        modeling_path=path_name,
                    )
                )

        note = state.note or PV_FAULT_READ_ONLY_MESSAGE
        return DeploymentSlotView(
            slot=PV_FAULT_SLOT,
            production_path=production_path,
            fallback_path=state.fallback_path or "seq_annotation",
            production_model=production_model,
            shadow_models=shadows,
            retired_models=retired,
            path_models={
                name: path_state.to_dict() for name, path_state in state.path_models.items()
            },
            updated_at=state.updated_at or datetime.utcnow().isoformat(),
            note=note,
            active_activation_epoch_id=state.active_activation_epoch_id,
        )


def _to_model_version(
    registration: ModelRegistration,
    *,
    status: str,
    modeling_path: str,
) -> ModelVersion:
    return ModelVersion(
        workflow_id=registration.model_ref,
        version_tag=f"{modeling_path}:{registration.evaluation_id}",
        status=status,
        deployed_at=registration.registered_at or "",
        accuracy_score=registration.gate_metric_value,
        source_candidate_id=registration.candidate_id or None,
    )
# @AI_GENERATED: end
