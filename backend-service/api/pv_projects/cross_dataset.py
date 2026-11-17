# @AI_GENERATED
"""跨数据集验证 / 离线基准证据 API（design D-GOV-01；任务 8.1–8.3）。

路由：
- POST /api/pv-projects/{project_id}/validation-batches                 创建跨数据集验证批次
- GET  /api/pv-projects/{project_id}/validation-batches                 列出批次
- POST /api/pv-projects/{project_id}/validation-batches/{validation_id}/results     登记逐数据集结果
- GET  /api/pv-projects/{project_id}/validation-batches/{validation_id}/evidence     聚合证据束
- GET  /api/pv-projects/{project_id}/validation-batches/{validation_id}/zero-pollution 零污染校验
- POST /api/pv-projects/{project_id}/offline-benchmark-evidence          只读登记离线基准证据
- GET  /api/pv-projects/{project_id}/offline-benchmark-evidence          列出离线基准证据

红线：验证批次为项目级（不按 slot 分区）；governance_effect=none；validation_id 用 xdpv- 前缀，
不能作为正式复验证据；离线基准证据只读、无 calibration_audit_id。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import build_scope, gate_error_to_http
from services.pv_projects.cross_dataset import (
    CrossDatasetValidationService,
    list_offline_benchmark_evidence,
    register_offline_benchmark_evidence,
)
from services.pv_projects.governance import GovernanceGateError

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-cross-dataset"])


class CreateBatchRequest(BaseModel):
    datasets: List[Dict[str, Any]] = Field(..., description="数据集列表（dataset_key/source_ref/dataset_version_id/content_digest）")
    evaluation_contract: Optional[Dict[str, Any]] = Field(default=None, description="评测合同（尺子）")
    note: Optional[str] = Field(default=None, description="备注")


class RecordResultRequest(BaseModel):
    dataset_key: str = Field(..., description="数据集键")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="评测指标")
    dimension_findings: Optional[Dict[str, Any]] = Field(default=None, description="迁移 / 交互 / 隔离维度发现")


class RegisterBenchmarkRequest(BaseModel):
    benchmark_source: str = Field(..., description="基准来源（如 pvdaq）")
    manifest_ref: Optional[str] = Field(default=None, description="相对 manifest 引用")
    metrics: Optional[Dict[str, Any]] = Field(default=None, description="离线指标")
    calibration_note: Optional[str] = Field(default=None, description="校准说明")


@router.post("/{project_id}/validation-batches", summary="创建跨数据集验证批次")
def post_create_batch(project_id: str, req: CreateBatchRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, allow_legacy=False)
    try:
        batch = CrossDatasetValidationService.create_batch(
            scope, datasets=req.datasets, evaluation_contract=req.evaluation_contract, note=req.note
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "batch": batch}


@router.get("/{project_id}/validation-batches", summary="列出跨数据集验证批次")
def get_batches(project_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id)
    return {**scope.echo(), "batches": CrossDatasetValidationService.list_batches(scope)}


@router.post("/{project_id}/validation-batches/{validation_id}/results", summary="登记逐数据集结果")
def post_record_result(project_id: str, validation_id: str, req: RecordResultRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, allow_legacy=False)
    try:
        batch = CrossDatasetValidationService.record_result(
            scope, validation_id, dataset_key=req.dataset_key, metrics=req.metrics, dimension_findings=req.dimension_findings
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "batch": batch}


@router.get("/{project_id}/validation-batches/{validation_id}/evidence", summary="聚合证据束")
def get_evidence(project_id: str, validation_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id)
    try:
        return CrossDatasetValidationService.aggregate_evidence(scope, validation_id)
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc


@router.get("/{project_id}/validation-batches/{validation_id}/zero-pollution", summary="零污染校验")
def get_zero_pollution(project_id: str, validation_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id)
    try:
        return CrossDatasetValidationService.verify_zero_pollution(scope, validation_id)
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc


@router.post("/{project_id}/offline-benchmark-evidence", summary="只读登记离线基准证据")
def post_register_benchmark(project_id: str, req: RegisterBenchmarkRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, allow_legacy=False)
    try:
        rec = register_offline_benchmark_evidence(
            scope,
            benchmark_source=req.benchmark_source,
            manifest_ref=req.manifest_ref,
            metrics=req.metrics,
            calibration_note=req.calibration_note,
        )
    except GovernanceGateError as exc:
        raise gate_error_to_http(exc, scope=scope.echo()) from exc
    return {**scope.echo(), "evidence": rec}


@router.get("/{project_id}/offline-benchmark-evidence", summary="列出离线基准证据")
def get_benchmark_evidence(project_id: str) -> Dict[str, Any]:
    scope = build_scope(project_id)
    return {**scope.echo(), "evidence": list_offline_benchmark_evidence(scope)}


# @AI_GENERATED: end
