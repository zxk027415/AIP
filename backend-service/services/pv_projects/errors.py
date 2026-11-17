# @AI_GENERATED
"""pv_projects scope / path errors.

统一的 scope 与相对路径错误类型。与既有 `SlotDatasetError` / `ProvenanceError`
保持同样的 `(code, message)` 形状，但额外携带 `next_action` / `retryable`，
以便 API 层（任务 1.3）直接映射为设计 §26.5 的统一错误响应
（`reason_code` / `message` / `next_action` / `retryable` / `scope` / `correlation_id`）。

本模块只定义异常，不做任何 I/O，也不返回机器绝对路径（红线）。
"""

from __future__ import annotations

from typing import Any, Optional


class ScopeError(Exception):
    """项目 / 槽位 / 数据版本 scope 校验失败。

    Attributes:
        code: 稳定英文机器原因码（reason_code），用于日志、测试与追踪。
        message: 面向用户的中文说明（展示层）。
        next_action: 最短下一步（可选）。
        retryable: 是否可按原输入重试（默认 False：scope 类错误多数需要修正输入）。
        scope: 触发错误时已知的 scope 片段（project_id / slot / dataset_version_id）。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        next_action: Optional[str] = None,
        retryable: bool = False,
        scope: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.next_action = next_action
        self.retryable = bool(retryable)
        self.scope = dict(scope) if scope else None

    def to_dict(self) -> dict[str, Any]:
        """转成可 JSON 序列化的原因体（不含堆栈、凭据或绝对路径）。"""
        payload: dict[str, Any] = {
            "reason_code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.next_action:
            payload["next_action"] = self.next_action
        if self.scope:
            payload["scope"] = self.scope
        return payload


class PathScopeError(ScopeError):
    """相对路径解析 / 校验失败（缺失、非法、越界或机器绝对路径）。"""


# @AI_GENERATED: end
