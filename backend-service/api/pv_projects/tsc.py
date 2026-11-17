# @AI_GENERATED
"""pv_tsc canonical 打标 / strict-10 证据 / 只读生产观测 API（design D-PATH-01；任务 7.1–7.3）。

路由：
- GET  /api/pv-projects/{project_id}/slots/{slot}/tsc/canonical-labeling-entry  canonical 打标入口
- GET  /api/pv-projects/{project_id}/slots/{slot}/tsc/shortcut-distinction       shortcut 与 canonical 区分
- GET  /api/pv-projects/{project_id}/slots/{slot}/tsc/strict10-evidence          strict-10 证据视图
- POST /api/pv-projects/{project_id}/slots/{slot}/tsc/strict10-evidence          登记 strict-10 证据（scoped）
- GET  /api/pv-projects/{project_id}/slots/{slot}/tsc/production-status          只读生产观测

红线：canonical = workflow-pv-tsc-label-v1（tsc_predict→emit_tsc_label_proposal）；shortcut≠canonical；
strict-10 validation 恒非可治理；生产观测只读、失败日不推进游标、手工写入拒绝。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import build_scope, gate_error_to_http
from services.pv_projects import tsc_adapter as tsc
from services.pv_projects.governance import GovernanceGateError

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-tsc"])


class RegisterStrict10Request(BaseModel):
    model_config = {"protected_namespaces": ()}
    source_execution_id: str = Field(..., description="strict-10 validation execution ID")
    macro_f1: Optional[float] = Field(default=None, description="固定标签空间 Macro-F1（缺失置空，不臆造）")
    production_contract_valid: bool = Field(default=False, description="合同是否完整（≠精度达标 / 可治理）")
    qualified_device_days: Optional[int] = Field(default=None, description="合格设备日数")
    rejected_device_days: Optional[int] = Field(default=None, description="拒收设备日数")
    class_distribution: Optional[Dict[str, int]] = Field(default=None, description="类别分布")


@router.get("/{project_id}/slots/{slot}/tsc/canonical-labeling-entry", summary="canonical 打标入口")
def get_canonical_entry(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return tsc.canonical_labeling_entry(scope)


@router.get("/{project_id}/slots/{slot}/tsc/shortcut-distinction", summary="shortcut 与 canonical 区分")
def get_shortcut_distinction(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return tsc.shortcut_distinction(scope)


@router.get("/{project_id}/slots/{slot}/tsc/strict10-evidence", summary="strict-10 证据视图")
def get_strict10_evidence(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return tsc.strict10_evidence_view(scope)


@router.post("/{project_id}/slots/{slot}/tsc/strict10-evidence", summary="登记 strict-10 证据（scoped）")
def post_strict10_evidence(project_id: str, slot: str, req: RegisterStrict10Request) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True, allow_legacy=False)
    try:
        rec = tsc.register_strict10_evidence(
            scope,
            source_execution_id=req.source_execution_id,
            macro_f1=req.macro_f1,
            production_contract_valid=req.production_contract_valid,
            qualified_device_days=req.qualified_device_days,
            rejected_device_days=req.rejected_device_days,
            class_distribution=req.class_distribution,
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "evidence": rec}


@router.get("/{project_id}/slots/{slot}/tsc/production-status", summary="只读生产观测")
def get_production_status(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    return tsc.tsc_production_status(scope)


# @AI_GENERATED: end
