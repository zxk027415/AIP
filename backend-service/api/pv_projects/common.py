# @AI_GENERATED
"""项目化 API 公共层：scope 依赖、统一错误响应、门控→HTTP 映射。

设计依据：`design.md` §26.2（服务端必须重新读取对象自身 scope）、§26.5（统一错误响应）、
§24.2（禁用原因分类）；`requirements.md` R1.1–R1.9、R2.2–R2.4。

统一错误响应字段（不含堆栈 / 凭据 / 机器绝对路径）：
`reason_code` / `message` / `next_action` / `scope` / `retryable` / `correlation_id`
（涉及门槛时补 `current_value` / `required_value`；门控附 `category`）。
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import HTTPException

from services.pv_projects.governance import GovernanceGateError
from services.pv_projects.scope import ScopeContext
from services.pv_projects.errors import ScopeError

# reason_code → HTTP 状态。缺省 400（业务门禁多为 409）。
_SCOPE_STATUS: dict[str, int] = {
    "scope_mismatch": 409,
    "legacy_read_only": 403,
    "legacy_project_not_allowed": 403,
    "absolute_path_forbidden": 400,
    "path_escapes_scope": 400,
}

_CATEGORY_STATUS: dict[str, int] = {
    "permission_denied": 403,
    "read_only": 403,
    "sandbox_only": 403,
    "scope_mismatch": 409,
    "business_gate_blocked": 409,
}


def new_correlation_id() -> str:
    """诊断关联 ID，用于把一次失败在日志 / 前端 / 追踪之间对齐。"""
    return f"corr-{uuid.uuid4().hex[:12]}"


def production_writes_authorized() -> bool:
    """本轮是否获得 production 写入人工授权。

    自动化环境固定 `production_writes_authorized=false`（红线）：默认不授权，
    只有显式设置环境变量 `AIP_PRODUCTION_WRITES_AUTHORIZED=1/true/yes/on` 才放行。
    """
    import os

    return os.getenv("AIP_PRODUCTION_WRITES_AUTHORIZED", "").strip().lower() in {"1", "true", "yes", "on"}


def assert_production_writes_authorized(scope: Optional[dict[str, Any]] = None) -> None:
    """滚动指针 / Promote 等会改变生产真源的写入前置门禁。未授权即 403。"""
    if not production_writes_authorized():
        raise unified_error(
            "production_writes_not_authorized",
            "本环境未授权 production 写入，滚动指针 / Promote 等真实写入被阻止（仅允许只读、Sandbox 或负向验证）。",
            status=403,
            next_action="在获得人工授权并设置 AIP_PRODUCTION_WRITES_AUTHORIZED 后再执行",
            scope=scope,
            category="permission_denied",
        )


def unified_error(
    reason_code: str,
    message: str,
    *,
    status: int = 400,
    next_action: Optional[str] = None,
    scope: Optional[dict[str, Any]] = None,
    retryable: bool = False,
    current_value: Any = None,
    required_value: Any = None,
    category: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> HTTPException:
    """构造设计 §26.5 形状的统一错误 HTTPException。"""
    detail: dict[str, Any] = {
        "reason_code": reason_code,
        "message": message,
        "retryable": bool(retryable),
        "correlation_id": correlation_id or new_correlation_id(),
    }
    if next_action:
        detail["next_action"] = next_action
    if scope:
        detail["scope"] = scope
    if current_value is not None:
        detail["current_value"] = current_value
    if required_value is not None:
        detail["required_value"] = required_value
    if category:
        detail["category"] = category
    return HTTPException(status_code=status, detail=detail)


def scope_error_to_http(exc: ScopeError) -> HTTPException:
    """ScopeError → 统一错误响应。"""
    status = _SCOPE_STATUS.get(exc.code, 400)
    return unified_error(
        exc.code,
        exc.message,
        status=status,
        next_action=exc.next_action,
        scope=exc.scope,
        retryable=exc.retryable,
        category="scope_mismatch" if exc.code == "scope_mismatch" else None,
    )


def gate_error_to_http(exc: GovernanceGateError, *, scope: Optional[dict[str, Any]] = None) -> HTTPException:
    """GovernanceGateError → 统一错误响应（保留 5 类禁用原因 category）。"""
    status = _CATEGORY_STATUS.get(exc.category, 409)
    return unified_error(
        exc.code,
        exc.message,
        status=status,
        next_action=exc.next_action,
        scope=scope,
        retryable=exc.retryable,
        current_value=exc.current_value,
        required_value=exc.required_value,
        category=exc.category,
    )


def build_scope(
    project_id: str,
    slot: Optional[str] = None,
    dataset_version_id: Optional[str] = None,
    *,
    require_slot: bool = False,
    require_dataset_version: bool = False,
    allow_legacy: bool = True,
    require_registered: bool = True,
) -> ScopeContext:
    """从 path / query 构造并校验 ScopeContext；失败即映射为统一错误响应。

    这是服务端“重新读取对象自身 scope”的入口：handler 不能只相信 path / body，
    必须经此校验后再操作 scoped 存储。

    `require_registered`（**默认开启**，P1-5）：除标识符形状校验外，还要求项目**已在项目索引登记**。
    修复前所有写端点只做形状校验，于是「格式合法但不存在的 project_id」能一路写出孤儿数据——
    数据落在 `data/**/projects/<不存在的 id>/` 下，永远不会出现在项目列表里，也无法通过 UI 找回。
    显式传 `False` 只应用于确实需要操作未登记项目的一次性运维场景；legacy 只读项目自动豁免。
    """
    try:
        scope = ScopeContext.create(
            project_id,
            slot,
            dataset_version_id,
            require_slot=require_slot,
            require_dataset_version=require_dataset_version,
            allow_legacy=allow_legacy,
        )
    except ScopeError as exc:
        raise scope_error_to_http(exc) from exc

    if require_registered and not scope.is_legacy:
        # 延迟导入：避免 api 层在模块加载期依赖 services 的具体实现顺序。
        from services.pv_projects import projects as project_service

        if project_service.get_project(scope.project_id) is None:
            raise unified_error(
                "project_not_found",
                f"项目 {scope.project_id!r} 未登记，拒绝在该 scope 下读写。",
                status=404,
                next_action="先创建项目，或确认 project_id 是否正确",
                scope=scope.echo(),
            )
    return scope


# @AI_GENERATED: end
