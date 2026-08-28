# @AI_GENERATED
"""Slot datasets API — annotation candidates, reviews, snapshots (G5 skeleton)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.slot_datasets.annotation_candidates import (
    list_annotation_candidates,
    register_annotation_candidate,
)
from services.slot_datasets.rare_class_review_queue import (
    build_rare_class_review_queue,
    load_rare_class_review_queue,
    save_rare_class_review_queue,
    sync_review_queue_to_annotation_candidates,
)
from services.slot_datasets.errors import SlotDatasetError
from services.slot_datasets.reviewed_annotations import (
    approve_annotation_candidate,
    list_reviewed_annotations,
    reject_annotation_candidate,
)
from services.slot_datasets.snapshots import (
    bootstrap_snapshot,
    build_snapshot_increment,
    complete_bootstrap_async,
    freeze_cumulative_at,
    get_cumulative_ledger,
    get_snapshot_chain,
    preview_snapshot,
    resolve_snapshot_ref,
    start_bootstrap_async,
)
from services.slot_governance.provenance import ProvenanceError

router = APIRouter(prefix="/api/slot-datasets", tags=["slot-datasets"])


def _dataset_http(exc: SlotDatasetError) -> HTTPException:
    status = 400
    if exc.code in {"candidate_not_found", "snapshot_not_found", "reviewed_annotation_not_found"}:
        status = 404
    if exc.code in {"snapshot_chain_exists", "base_version_conflict", "idempotency_conflict"}:
        status = 409
    if exc.code == "locked_holdout_forbidden":
        status = 403
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


def _provenance_http(exc: ProvenanceError) -> HTTPException:
    status = 400
    if exc.code in {"execution_not_found", "execution_id_mismatch"}:
        status = 404
    if exc.code == "benchmark_governance_forbidden":
        status = 403
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message})


class RegisterAnnotationCandidateRequest(BaseModel):
    slot: str
    source_workflow_id: str
    source_execution_id: str
    dataset_profile_ref: str
    entity_key: str
    boundary_start: str
    boundary_end: str
    suggested_label: Any
    model_ref: Optional[str] = None
    confidence: Optional[float] = None
    policy_version: str = "v1"
    candidate_projection_enabled: bool = True
    scenario_key: Optional[str] = None


class ApproveAnnotationRequest(BaseModel):
    slot: str
    reviewer: str
    idempotency_key: str
    final_label: Optional[Any] = None
    label_space_version: str = "v1"
    annotation_role: str = "learning"


class RejectAnnotationRequest(BaseModel):
    slot: str
    reviewer: str
    idempotency_key: str
    reason: str


class BootstrapSnapshotRequest(BaseModel):
    slot: str
    idempotency_key: str
    source_digest: str
    base_artifact_ref: str
    dataset_profile_ref: str
    reason: str
    source_workflow_id: Optional[str] = None
    source_execution_id: Optional[str] = None
    role_partition: Optional[Dict[str, Any]] = None


class BuildSnapshotRequest(BaseModel):
    slot: str
    snapshot_id: str
    base_snapshot_version: int
    reviewed_annotation_ids: List[str]
    idempotency_key: str
    reason: str


class StartBootstrapAsyncRequest(BaseModel):
    slot: str
    idempotency_key: str
    dataset_profile_ref: str
    reason: str
    bootstrap_workflow_ref: Optional[str] = None


class CompleteBootstrapAsyncRequest(BaseModel):
    bootstrap_execution_id: str
    source_digest: str
    base_artifact_ref: str


class FreezeCumulativeLedgerRequest(BaseModel):
    slot: str
    reviewed_at_cutoff: str
    reason: Optional[str] = None
    idempotency_key: Optional[str] = None


@router.get("/annotation-candidates", summary="列出 annotation candidate")
def get_annotation_candidates(
    slot: str = Query(...),
    review_status: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    try:
        items = list_annotation_candidates(slot, review_status=review_status)
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"slot": slot, "candidates": items}


@router.get("/rare-class-review-queue", summary="读取稀有类人工金标审核队列")
def get_rare_class_review_queue(slot: str = Query(default="pv_point")) -> Dict[str, Any]:
    try:
        payload = load_rare_class_review_queue()
    except SlotDatasetError as exc:
        if exc.code == "review_queue_not_found":
            raise HTTPException(status_code=404, detail=exc.message) from exc
        raise _dataset_http(exc) from exc
    if payload.get("slot") != slot:
        raise HTTPException(status_code=404, detail=f"review queue slot mismatch: expected {slot!r}")
    return payload


@router.post("/rare-class-review-queue/rebuild", summary="重建稀有类人工金标审核队列")
def post_rebuild_rare_class_review_queue(slot: str = Query(default="pv_point")) -> Dict[str, Any]:
    if slot != "pv_point":
        raise HTTPException(status_code=422, detail="当前仅支持 slot=pv_point")
    payload = build_rare_class_review_queue(slot=slot)
    rel = save_rare_class_review_queue(payload)
    sync = sync_review_queue_to_annotation_candidates(payload)
    return {"queue_path": rel, "queue": payload, "annotation_candidates_sync": sync}


@router.post("/annotation-candidates", summary="登记 annotation candidate")
def post_annotation_candidate(req: RegisterAnnotationCandidateRequest) -> Dict[str, Any]:
    try:
        candidate = register_annotation_candidate(
            slot=req.slot,
            source_workflow_id=req.source_workflow_id,
            source_execution_id=req.source_execution_id,
            model_ref=req.model_ref,
            dataset_profile_ref=req.dataset_profile_ref,
            entity_key=req.entity_key,
            boundary_start=req.boundary_start,
            boundary_end=req.boundary_end,
            suggested_label=req.suggested_label,
            confidence=req.confidence,
            policy_version=req.policy_version,
            candidate_projection_enabled=req.candidate_projection_enabled,
            scenario_key=req.scenario_key,
        )
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"candidate": candidate}


@router.get("/reviewed-annotations", summary="列出 reviewed annotation")
def get_reviewed_annotations(slot: str = Query(...)) -> Dict[str, Any]:
    try:
        items = list_reviewed_annotations(slot)
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"slot": slot, "annotations": items}


@router.post("/annotation-candidates/{annotation_candidate_id}/approve", summary="批准标注候选")
def post_approve_annotation(annotation_candidate_id: str, req: ApproveAnnotationRequest) -> Dict[str, Any]:
    try:
        return approve_annotation_candidate(
            slot=req.slot,
            annotation_candidate_id=annotation_candidate_id,
            reviewer=req.reviewer,
            idempotency_key=req.idempotency_key,
            final_label=req.final_label,
            label_space_version=req.label_space_version,
            annotation_role=req.annotation_role,
        )
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.post("/annotation-candidates/{annotation_candidate_id}/reject", summary="拒绝标注候选")
def post_reject_annotation(annotation_candidate_id: str, req: RejectAnnotationRequest) -> Dict[str, Any]:
    try:
        return reject_annotation_candidate(
            slot=req.slot,
            annotation_candidate_id=annotation_candidate_id,
            reviewer=req.reviewer,
            idempotency_key=req.idempotency_key,
            reason=req.reason,
        )
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.get("/snapshots/chain", summary="读取 slot 快照链")
def get_chain(slot: str = Query(...)) -> Dict[str, Any]:
    try:
        return get_snapshot_chain(slot)
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.post("/snapshots/bootstrap", summary="Bootstrap 快照 v1（同步版）")
def post_bootstrap_snapshot(req: BootstrapSnapshotRequest) -> Dict[str, Any]:
    try:
        return bootstrap_snapshot(
            slot=req.slot,
            idempotency_key=req.idempotency_key,
            source_digest=req.source_digest,
            base_artifact_ref=req.base_artifact_ref,
            dataset_profile_ref=req.dataset_profile_ref,
            reason=req.reason,
            source_workflow_id=req.source_workflow_id,
            source_execution_id=req.source_execution_id,
            role_partition=req.role_partition,
        )
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.post("/snapshots/bootstrap-async", summary="发起 bootstrap 异步任务")
def post_bootstrap_async(req: StartBootstrapAsyncRequest) -> Dict[str, Any]:
    try:
        job = start_bootstrap_async(
            slot=req.slot,
            idempotency_key=req.idempotency_key,
            dataset_profile_ref=req.dataset_profile_ref,
            reason=req.reason,
            bootstrap_workflow_ref=req.bootstrap_workflow_ref,
        )
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc
    return {"job": job}


@router.post("/snapshots/bootstrap-async/{bootstrap_job_id}/complete", summary="完成 bootstrap（需 succeeded execution）")
def post_bootstrap_async_complete(bootstrap_job_id: str, req: CompleteBootstrapAsyncRequest) -> Dict[str, Any]:
    try:
        return complete_bootstrap_async(
            bootstrap_job_id,
            bootstrap_execution_id=req.bootstrap_execution_id,
            source_digest=req.source_digest,
            base_artifact_ref=req.base_artifact_ref,
        )
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.post("/snapshots/build", summary="基于 reviewed annotation 构建快照 +1")
def post_build_snapshot(req: BuildSnapshotRequest) -> Dict[str, Any]:
    try:
        return build_snapshot_increment(
            slot=req.slot,
            snapshot_id=req.snapshot_id,
            base_snapshot_version=req.base_snapshot_version,
            reviewed_annotation_ids=req.reviewed_annotation_ids,
            idempotency_key=req.idempotency_key,
            reason=req.reason,
        )
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.get("/snapshots/preview", summary="读取训练快照内容（parquet/csv）")
def get_snapshot_preview(
    slot: str = Query(...),
    freeze_id: str = Query(...),
) -> Dict[str, Any]:
    try:
        return preview_snapshot(slot, freeze_id)
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc


@router.get("/snapshots/resolve", summary="解析 snapshot_id@version 供重训路径参数")
def get_resolve_snapshot(
    slot: str = Query(...),
    snapshot_id: str = Query(...),
    snapshot_version: int = Query(...),
) -> Dict[str, Any]:
    try:
        return resolve_snapshot_ref(slot, snapshot_id, snapshot_version)
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc
    except ProvenanceError as exc:
        raise _provenance_http(exc) from exc


@router.get("/cumulative-ledger", summary="读取累计训练账本与冻结版本")
def get_cumulative_training_ledger(slot: str = Query(...)) -> Dict[str, Any]:
    try:
        return get_cumulative_ledger(slot)
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc


@router.post("/cumulative-ledger/freeze", summary="按人工审核结束时间冻结累计训练版本")
def post_freeze_cumulative_ledger(req: FreezeCumulativeLedgerRequest) -> Dict[str, Any]:
    try:
        freeze = freeze_cumulative_at(
            slot=req.slot,
            reviewed_at_cutoff=req.reviewed_at_cutoff,
            idempotency_key=req.idempotency_key,
            reason=req.reason,
        )
        ledger = get_cumulative_ledger(req.slot)
        return {"freeze": freeze, "ledger": ledger}
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc


class ObservabilityAdvanceRequest(BaseModel):
    slot: str
    operator: str = "ui"


class ObservabilityManualDetectRequest(BaseModel):
    slot: str
    device_key: str
    day: Optional[str] = None
    operator: str = "ui"
    reason: str = "manual"


class MockGoldReviewRequest(BaseModel):
    slot: str
    max_units: int = 30


@router.get("/observability/calendar", summary="设备×日观测网格")
def get_observability_calendar(
    slot: str = Query(...),
    day_from: str = Query(..., alias="from"),
    day_to: str = Query(..., alias="to"),
    page: int = Query(default=1),
) -> Dict[str, Any]:
    from services.slot_datasets.observability_ledger import calendar_grid

    try:
        return calendar_grid(slot, day_from, day_to, page=page)
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc


@router.get("/observability/curve", summary="设备时段曲线")
def get_observability_curve(
    slot: str = Query(...),
    device: str = Query(...),
    day_from: str = Query(..., alias="from"),
    day_to: str = Query(..., alias="to"),
) -> Dict[str, Any]:
    from services.slot_datasets.observability_ledger import curve_for_device

    try:
        return curve_for_device(slot, device, day_from, day_to)
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc


@router.post("/observability/advance-day", summary="推进 pv_day 检测水位日")
def post_observability_advance_day(req: ObservabilityAdvanceRequest) -> Dict[str, Any]:
    from services.slot_datasets.observability_ledger import advance_watermark_day

    try:
        ledger = advance_watermark_day(req.slot, operator=req.operator)
        return {"ledger": ledger, "watermark_day": ledger.get("watermark_day")}
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc


@router.post("/observability/manual-detect", summary="手动补检设备-日")
def post_observability_manual_detect(req: ObservabilityManualDetectRequest) -> Dict[str, Any]:
    from services.slot_datasets.observability_ledger import record_manual_detect

    try:
        return record_manual_detect(
            req.slot,
            device_key=req.device_key,
            day=req.day,
            operator=req.operator,
            reason=req.reason,
        )
    except SlotDatasetError as extra:
        raise _dataset_http(extra) from extra


@router.post("/mock-gold-review", summary="用 gold 模拟一小批审核并入库")
def post_mock_gold_review(req: MockGoldReviewRequest) -> Dict[str, Any]:
    from services.slot_datasets.mock_gold_review import run_mock_gold_review

    try:
        return run_mock_gold_review(req.slot, max_units=req.max_units)
    except SlotDatasetError as exc:
        raise _dataset_http(exc) from exc

@router.get("/mock-accuracy", summary="读取最近一次 gold mock 对照精度")
def get_mock_accuracy(slot: str = Query(...)) -> Dict[str, Any]:
    from services.slot_datasets.mock_gold_review import load_mock_accuracy

    return load_mock_accuracy(slot)

