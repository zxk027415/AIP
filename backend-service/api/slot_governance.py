# @AI_GENERATED
"""Slot governance API — registry, candidates, verification, promote (G4 skeleton)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.slot_governance.evaluation_contracts import get_evaluation_contract
from services.slot_governance.model_candidates import (
    find_model_candidate,
    list_model_candidates,
    register_model_candidate,
)
from services.slot_governance.promote import PromoteError, list_promotions_log, promote_model_candidate
from services.slot_governance.provenance import ProvenanceError
from services.slot_governance.registry import (
    get_registry_store,
    set_candidate_model,
    set_production_model,
    set_rolling_detect_model,
)
from services.slot_governance.verification import (
    VerificationError,
    list_verifications,
    register_verification,
)
from services.slot_governance.verify_async import (
    complete_verification_async,
    get_verification_job,
    list_verification_jobs,
    start_verification_async,
)

router = APIRouter(prefix="/api/slot-governance", tags=["slot-governance"])


class RegisterModelCandidateRequest(BaseModel):
    slot: str = Field(..., description="Product slot partition key")
    source_workflow_id: str
    source_workflow_version: Optional[str] = None
    source_execution_id: str
    model_artifact_ref: str
    model_ref: Optional[str] = None
    scenario_key: Optional[str] = Field(default=None, description="Rejected — use slot directly")


class RegisterVerificationRequest(BaseModel):
    slot: str
    model_candidate_id: str
    evaluation_contract_ref: str
    idempotency_key: str
    passed: bool = True
    registry_version_at_start: int = 0
    baseline_model_ref: Optional[str] = None
    verification_source_workflow_id: Optional[str] = None
    verification_source_execution_id: Optional[str] = None
    evaluation_artifact_ref: Optional[str] = None


class PromoteRequest(BaseModel):
    verification_id: str
    operator: str
    reason: str
    expected_registry_version: int
    idempotency_key: str
    production_slot: Optional[str] = None
    set_as_production: bool = False


class StartVerifyAsyncRequest(BaseModel):
    slot: str
    model_candidate_id: str
    idempotency_key: str
    evaluation_contract_ref: Optional[str] = None
    registry_version_at_start: Optional[int] = None
    verification_workflow_ref: Optional[str] = None


class CompleteVerifyAsyncRequest(BaseModel):
    verification_execution_id: str


class SetRollingDetectModelRequest(BaseModel):
    model_candidate_id: Optional[str] = None
    model_artifact_ref: Optional[str] = None
    operator: str = "ui"
    reason: Optional[str] = None


def _provenance_http(exc: ProvenanceError) -> HTTPException:
    status = 400
    if exc.code in {"execution_not_found", "execution_id_mismatch"}:
        status = 404
    if exc.code == "benchmark_governance_forbidden":
        status = 403
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


def _verification_http(exc: VerificationError) -> HTTPException:
    status = 400
    if exc.code == "candidate_not_found":
        status = 404
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


def _promote_http(exc: PromoteError) -> HTTPException:
    status = 400
    if exc.code in {"candidate_not_found", "verification_not_found"}:
        status = 404
    if exc.code == "registry_version_conflict":
        status = 409
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


@router.get("/registry/{slot}", summary="读取 slot model registry（只读）")
def get_slot_registry(slot: str) -> Dict[str, Any]:
    return get_registry_store().get(slot)


@router.put("/registry/{slot}/rolling-detect-model", summary="指定下次按日检测使用的模型（兼容旧指针）")
def put_rolling_detect_model(slot: str, req: SetRollingDetectModelRequest) -> Dict[str, Any]:
    try:
        registry = set_rolling_detect_model(
            slot,
            model_candidate_id=req.model_candidate_id,
            model_artifact_ref=req.model_artifact_ref,
            operator=req.operator,
            reason=req.reason,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if message.startswith("candidate_not_found") else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"registry": registry, "rolling_detect_model": registry.get("rolling_detect_model")}


@router.put("/registry/{slot}/production-model", summary="设为生产模型（champion，并同步检测指针）")
def put_production_model(slot: str, req: SetRollingDetectModelRequest) -> Dict[str, Any]:
    try:
        registry = set_production_model(
            slot,
            model_candidate_id=req.model_candidate_id,
            model_artifact_ref=req.model_artifact_ref,
            operator=req.operator,
            reason=req.reason,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if message.startswith("candidate_not_found") else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"registry": registry, "champion": registry.get("champion")}


@router.put("/registry/{slot}/candidate-model", summary="设为候选模型（challenger，不进按日检测）")
def put_candidate_model(slot: str, req: SetRollingDetectModelRequest) -> Dict[str, Any]:
    try:
        registry = set_candidate_model(
            slot,
            model_candidate_id=req.model_candidate_id,
            model_artifact_ref=req.model_artifact_ref,
            operator=req.operator,
            reason=req.reason,
        )
    except ValueError as exc:
        message = str(exc)
        status = 404 if message.startswith("candidate_not_found") else 400
        raise HTTPException(status_code=status, detail=message) from exc
    return {"registry": registry, "challenger": registry.get("challenger")}


@router.get("/evaluation-contract/{slot}", summary="读取 slot 评测量约")
def get_slot_evaluation_contract(slot: str) -> Dict[str, Any]:
    try:
        return get_evaluation_contract(slot)
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.get("/model-candidates", summary="列出 slot 内 model candidate（含项目归属）")
def get_model_candidates(slot: str = Query(..., description="Product slot")) -> Dict[str, Any]:
    try:
        items = list_model_candidates(slot)
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    # @AI_GENERATED: 补 project_attribution —— 让「模型部署」页看得出模型来自哪个项目。
    # 归属解析只读、永不抛错；解析不出就是 None（该候选不是项目训练产出的）。
    from services.slot_governance.project_attribution import annotate_candidates_with_project

    items = annotate_candidates_with_project(slot, items)
    # @AI_GENERATED: end
    return {"slot": slot, "candidates": items}


@router.get("/model-candidates/{model_candidate_id}", summary="按 ID 读取 model candidate")
def get_model_candidate(model_candidate_id: str) -> Dict[str, Any]:
    slot, candidate = find_model_candidate(model_candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    return {"slot": slot, "candidate": candidate}


@router.post("/model-candidates", summary="登记 model candidate（需 succeeded execution 来源）")
def post_model_candidate(req: RegisterModelCandidateRequest) -> Dict[str, Any]:
    try:
        candidate = register_model_candidate(
            slot=req.slot,
            source_workflow_id=req.source_workflow_id,
            source_execution_id=req.source_execution_id,
            model_artifact_ref=req.model_artifact_ref,
            source_workflow_version=req.source_workflow_version,
            model_ref=req.model_ref,
            scenario_key=req.scenario_key,
        )
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"candidate": candidate}


@router.get("/verifications", summary="列出 slot 复验记录")
def get_verifications(slot: str = Query(...)) -> Dict[str, Any]:
    try:
        items = list_verifications(slot)
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"slot": slot, "verifications": items}


@router.post("/verifications", summary="登记复验记录（骨架：手工登记，不含 async 执行）")
def post_verification(req: RegisterVerificationRequest) -> Dict[str, Any]:
    try:
        record = register_verification(
            slot=req.slot,
            model_candidate_id=req.model_candidate_id,
            evaluation_contract_ref=req.evaluation_contract_ref,
            idempotency_key=req.idempotency_key,
            passed=req.passed,
            registry_version_at_start=req.registry_version_at_start,
            baseline_model_ref=req.baseline_model_ref,
            verification_source_workflow_id=req.verification_source_workflow_id,
            verification_source_execution_id=req.verification_source_execution_id,
            evaluation_artifact_ref=req.evaluation_artifact_ref,
        )
    except VerificationError as exc:
        raise _verification_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"verification": record}


@router.post("/verifications/verify-async", summary="发起异步复验（需后续 complete + 真实 execution）")
def post_verify_async(req: StartVerifyAsyncRequest) -> Dict[str, Any]:
    try:
        job = start_verification_async(
            slot=req.slot,
            model_candidate_id=req.model_candidate_id,
            evaluation_contract_ref=req.evaluation_contract_ref,
            idempotency_key=req.idempotency_key,
            registry_version_at_start=req.registry_version_at_start,
            verification_workflow_ref=req.verification_workflow_ref,
        )
    except VerificationError as exc:
        raise _verification_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"job": job}


@router.get("/verifications/verify-async", summary="列出 slot 异步复验任务")
def get_verify_async_jobs(
    slot: str = Query(...),
    status: Optional[str] = Query(default=None, description="pending | completed"),
) -> Dict[str, Any]:
    try:
        jobs = list_verification_jobs(slot, status=status)
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"slot": slot, "jobs": jobs}


@router.get("/verifications/verify-async/{comparison_id}", summary="查询异步复验任务")
def get_verify_async(comparison_id: str) -> Dict[str, Any]:
    try:
        return get_verification_job(comparison_id)
    except VerificationError as exc:
        raise _verification_http(exc) from exc


@router.post("/verifications/verify-async/{comparison_id}/complete", summary="完成异步复验（绑定 evaluation execution）")
def post_verify_async_complete(comparison_id: str, req: CompleteVerifyAsyncRequest) -> Dict[str, Any]:
    try:
        return complete_verification_async(
            comparison_id,
            verification_execution_id=req.verification_execution_id,
        )
    except VerificationError as exc:
        raise _verification_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.post("/model-candidates/{model_candidate_id}/promote", summary="Promote model candidate")
def post_promote(model_candidate_id: str, req: PromoteRequest) -> Dict[str, Any]:
    try:
        return promote_model_candidate(
            model_candidate_id,
            verification_id=req.verification_id,
            operator=req.operator,
            reason=req.reason,
            expected_registry_version=req.expected_registry_version,
            idempotency_key=req.idempotency_key,
            production_slot=req.production_slot,
            set_as_production=req.set_as_production,
        )
    except PromoteError as exc:
        raise _promote_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.get("/promotions-log/{slot}", summary="Promote 审计日志（append-only）")
def get_promotions_log(slot: str) -> Dict[str, Any]:
    try:
        events = list_promotions_log(slot)
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"slot": slot, "events": events}
