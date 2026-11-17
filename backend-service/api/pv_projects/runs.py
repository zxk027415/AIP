# @AI_GENERATED
"""运行中心 API：项目工作流创建 / 执行前 preflight / ScopedWorkflowRunner 执行。

设计依据：design.md D-RUN-01 / D-STATE-01；requirements.md R2.1–R2.13、R7.1–R7.3、R7.11–R7.12。

路由（前缀 /api/pv-projects）：
- POST /{project_id}/project-workflows                 创建项目工作流版本（template/copy/blank，绑定数据版本）
- GET  /{project_id}/project-workflows?slot=            列出项目工作流
- POST /{project_id}/preflight                          执行前预检（blocked/warning/passed）
- POST /{project_id}/executions                         登记一次 run（ScopedWorkflowRunner）
- GET  /{project_id}/executions?slot=                   执行列表
- GET  /{project_id}/executions/{execution_id}?slot=    执行详情（节点时间线）
- POST /{project_id}/executions/{execution_id}/node     更新节点状态
- POST /{project_id}/executions/{execution_id}/finalize 终态 + 结果去向
- POST /{project_id}/executions/{execution_id}/retry    用原输入重试（新 execution）
- POST /{project_id}/executions/{execution_id}/modify-rerun  改后重跑（新 execution）
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.pv_projects.common import build_scope, scope_error_to_http, unified_error
from services.pv_projects import workflows as workflow_service
from services.pv_projects.errors import ScopeError
from services.pv_projects.runner import get_runner
from services.pv_projects.scope import ScopeContext

router = APIRouter(prefix="/api/pv-projects", tags=["pv-projects-runs"])


# ---------------------------------------------------------------------------
# 项目工作流创建
# ---------------------------------------------------------------------------

class CreateProjectWorkflowRequest(BaseModel):
    slot: str = Field(..., description="诊断路径 slot（pv_day/pv_point/pv_tsc）")
    mode: str = Field(..., description="创建模式：template/copy/blank")
    name: str = Field(..., description="项目工作流名称")
    source_template_id: Optional[str] = Field(default=None, description="canonical 模板 ID（template 模式）")
    source_project_workflow_id: Optional[str] = Field(default=None, description="来源项目工作流 ID（copy 模式）")
    dataset_version_id: Optional[str] = Field(default=None, description="绑定到 load 节点的不可变数据版本 ID")
    workflow_kind: str = Field(default="training", description="工作流用途：training（可 N 个）/ labeling（canonical）/ detection（不可自建）")
    source_snapshot_id: Optional[str] = Field(default=None, description="训练输入冻结快照 ID（训练工作流应绑定；类型须与本路径匹配）")
    nodes: Optional[List[Dict[str, Any]]] = Field(default=None, description="画布节点（复制/带入时）")
    edges: Optional[List[Dict[str, Any]]] = Field(default=None, description="画布连线")
    load_node_id: Optional[str] = Field(default=None, description="指定 load 节点 ID（缺省自动识别 load_csv/load_labeled_dataset）")


@router.get("/workflow-templates", summary="按路径列出可复用的 canonical 模板")
def list_workflow_templates(slot: str) -> Dict[str, Any]:
    """平台级（不带 project_id）：列出该诊断路径下可复用的 canonical 模板。

    供前端「从模板创建项目工作流」时选择；按路径前缀过滤，避免把 pv_day 的图建到 pv_tsc 上。
    """
    return workflow_service.list_templates_for_slot(slot)


@router.post("/{project_id}/project-workflows", summary="创建项目工作流版本")
def create_project_workflow(project_id: str, req: CreateProjectWorkflowRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, req.slot, require_slot=True)
    try:
        return workflow_service.create_project_workflow(
            scope,
            mode=req.mode,
            name=req.name,
            source_template_id=req.source_template_id,
            source_project_workflow_id=req.source_project_workflow_id,
            dataset_version_id=req.dataset_version_id,
            source_snapshot_id=req.source_snapshot_id,
            workflow_kind=req.workflow_kind,
            nodes=req.nodes,
            edges=req.edges,
            load_node_id=req.load_node_id,
        )
    except ValueError as exc:
        raise unified_error("invalid_project_workflow_request", str(exc), status=400,
                            scope=scope.echo()) from exc


@router.get("/{project_id}/project-workflows", summary="列出项目工作流")
def list_project_workflows(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    items = workflow_service.list_project_workflows(scope)
    return {**scope.echo(), "workflows": items, "total": len(items)}


# ---------------------------------------------------------------------------
# 执行前 preflight
# ---------------------------------------------------------------------------

class PreflightRequest(BaseModel):
    slot: str = Field(..., description="诊断路径 slot")
    project_workflow_id: str = Field(..., description="项目工作流 ID")
    dataset_version_id: Optional[str] = Field(default=None, description="覆盖绑定的数据版本（可选）")


@router.post("/{project_id}/preflight", summary="执行前预检")
def run_preflight(project_id: str, req: PreflightRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, req.slot, require_slot=True)
    return workflow_service.run_preflight(
        scope,
        project_workflow_id=req.project_workflow_id,
        dataset_version_id=req.dataset_version_id,
    )


# ---------------------------------------------------------------------------
# ScopedWorkflowRunner 执行
# ---------------------------------------------------------------------------

class StartExecutionRequest(BaseModel):
    slot: str = Field(..., description="诊断路径 slot")
    project_workflow_id: str = Field(..., description="项目工作流 ID")
    run_mode: str = Field(..., description="运行模式：experiment/validation/training/prediction/replay")
    run_domain: str = Field(default="project", description="运行域：project/sandbox")
    dataset_version_id: Optional[str] = Field(default=None, description="数据版本 ID")
    node_ids: Optional[List[str]] = Field(default=None, description="节点 ID 列表（用于时间线）")
    evaluation_contract: Optional[Dict[str, Any]] = Field(default=None, description="评测合同（固定尺子）")
    idempotency_key: Optional[str] = Field(default=None, description="幂等键（防重复提交）")


def _echo(scope: ScopeContext) -> Dict[str, Any]:
    return scope.echo()


@router.post("/{project_id}/executions", summary="登记一次执行")
def start_execution(project_id: str, req: StartExecutionRequest) -> Dict[str, Any]:
    """登记一次执行。

    服务端门禁（P0-1，全部在 `ScopedWorkflowRunner.start_execution` 内）：
    项目工作流须在当前 scope 存在 → `run_mode` 须与工作流用途合同一致 →
    执行前预检不得 `blocked`。任一不满足即拒，不产生执行记录。
    """
    scope = build_scope(project_id, req.slot, require_slot=True)
    try:
        return get_runner().start_execution(
            scope,
            project_workflow_id=req.project_workflow_id,
            run_mode=req.run_mode,
            run_domain=req.run_domain,
            dataset_version_id=req.dataset_version_id,
            node_ids=req.node_ids,
            evaluation_contract=req.evaluation_contract,
            idempotency_key=req.idempotency_key,
        )
    except ScopeError as exc:
        # 门禁拒绝（unknown_project_workflow / run_mode 合同不符 / preflight blocked）：
        # 走 §26.5 统一错误响应，不落执行记录。
        raise scope_error_to_http(exc) from exc
    except ValueError as exc:
        raise unified_error("invalid_execution_request", str(exc), status=400,
                            scope=scope.echo()) from exc


@router.get("/{project_id}/executions", summary="执行列表")
def list_executions(project_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    items = get_runner().list_executions(scope)
    return {**scope.echo(), "executions": items, "total": len(items)}


@router.get("/{project_id}/executions/{execution_id}", summary="执行详情（节点时间线）")
def get_execution(project_id: str, execution_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    rec = get_runner().get_execution(scope, execution_id)
    if rec is None:
        # 后端记录缺失：显式 404，不臆造状态
        raise unified_error("backend_record_missing", f"execution 记录缺失：{execution_id}",
                            status=404, scope=scope.echo(),
                            next_action="刷新当前项目后重试，或重新提交执行")
    return rec


class NodeStatusRequest(BaseModel):
    slot: str
    node_id: str
    status: str
    error: Optional[str] = None


@router.post("/{project_id}/executions/{execution_id}/node", summary="更新节点状态")
def update_node_status(project_id: str, execution_id: str, req: NodeStatusRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, req.slot, require_slot=True)
    try:
        return get_runner().update_node_status(scope, execution_id, req.node_id, req.status, error=req.error)
    except ValueError as exc:
        raise unified_error("invalid_node_status", str(exc), status=400, scope=scope.echo()) from exc
    except LookupError as exc:
        raise unified_error("backend_record_missing", str(exc), status=404, scope=scope.echo()) from exc


class FinalizeRequest(BaseModel):
    slot: str
    status: str = Field(..., description="终态：success/failed/cancelled")
    result_destination: Optional[str] = Field(default=None, description="成功时结果去向")
    failure_reason: Optional[str] = Field(default=None, description="失败原因")
    # @AI_GENERATED: 训练落终态时带上模型工件 → 自动登记候选 → 领域桥进 slot 候选池，
    # 使「模型部署 / 精度运营」页能看到项目训练产出的模型。两个字段都可选，不传即旧行为。
    model_artifact_ref: Optional[str] = Field(
        default=None,
        description="模型工件相对引用（如 data/models/tsc/xxx）；给出且执行可治理时自动登记候选",
    )
    node_results: Optional[Dict[str, Any]] = Field(
        default=None,
        description="节点产出摘要 {node_id: {outputSummary: {...}}}；未显式给工件时从这里提取",
    )
    # @AI_GENERATED: end


@router.post("/{project_id}/executions/{execution_id}/finalize", summary="执行终态 + 结果去向")
def finalize_execution(project_id: str, execution_id: str, req: FinalizeRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, req.slot, require_slot=True)
    try:
        return get_runner().finalize(
            scope, execution_id, status=req.status,
            result_destination=req.result_destination, failure_reason=req.failure_reason,
            model_artifact_ref=req.model_artifact_ref,
            node_results=req.node_results,
        )
    except ValueError as exc:
        raise unified_error("invalid_finalize_request", str(exc), status=400, scope=scope.echo()) from exc
    except LookupError as exc:
        raise unified_error("backend_record_missing", str(exc), status=404, scope=scope.echo()) from exc


class RerunRequest(BaseModel):
    slot: str
    run_mode: Optional[str] = None
    dataset_version_id: Optional[str] = None
    node_ids: Optional[List[str]] = None


@router.post("/{project_id}/executions/{execution_id}/retry", summary="用原输入重试（新 execution）")
def retry_execution(project_id: str, execution_id: str, slot: str) -> Dict[str, Any]:
    scope = build_scope(project_id, slot, require_slot=True)
    try:
        return get_runner().retry_with_original_input(scope, execution_id)
    except LookupError as exc:
        raise unified_error("backend_record_missing", str(exc), status=404, scope=scope.echo()) from exc


@router.post("/{project_id}/executions/{execution_id}/modify-rerun", summary="改后重跑（新 execution）")
def modify_rerun_execution(project_id: str, execution_id: str, req: RerunRequest) -> Dict[str, Any]:
    scope = build_scope(project_id, req.slot, require_slot=True)
    try:
        return get_runner().modify_and_rerun(
            scope, execution_id,
            run_mode=req.run_mode, dataset_version_id=req.dataset_version_id, node_ids=req.node_ids,
        )
    except ValueError as exc:
        raise unified_error("invalid_rerun_request", str(exc), status=400, scope=scope.echo()) from exc
    except LookupError as exc:
        raise unified_error("backend_record_missing", str(exc), status=404, scope=scope.echo()) from exc


# @AI_GENERATED: end
