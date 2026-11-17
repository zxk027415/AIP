# @AI_GENERATED
"""共享项目上下文模型（ScopeContext）。

设计依据：`design.md` §6–8（scope 与 legacy 兼容）、§26.4（字段全链路）、
`requirements.md` R1.1–R1.12、R13.1–R13.4。

`ScopeContext` 接收来自 API path / query / body 的项目、槽位与数据版本，
输出供 handler、service 与 repository 共用的**已校验 scope**。目标最低隔离键是
`(project_id, slot)`；数据相关对象再细分到 `dataset_version_id`。

红线（本模块必须保证）：
1. 新项目请求缺失 / 非法 / 无法解析 `project_id` → fail-closed，不分配默认项目，
   不回退到任意 `slot` 或 `legacy`（R1.6）。
2. `project_id=legacy` 是**显式**历史兼容值，只读；绝不作为新请求的默认值（R1.10、R1.12）。
3. `slot` 有效值固定为 `pv_day` / `pv_point` / `pv_tsc`；历史 `pv_fault` 仅在 legacy 项目下只读兼容。
4. 所有标识符都必须通过安全校验（无路径分隔符、无 `..`、非绝对路径），
   避免把 scope 值直接拼进文件路径造成越界。

本模块不做任何 I/O。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from services.pv_projects.errors import ScopeError

# ---------------------------------------------------------------------------
# 常量：槽位与 legacy
# ---------------------------------------------------------------------------

#: 当前有效的诊断路径（产品槽位）。
PRODUCT_SLOTS: tuple[str, ...] = ("pv_day", "pv_point", "pv_tsc")

#: 仅在 legacy 项目下只读兼容的历史槽位。
LEGACY_ONLY_SLOTS: tuple[str, ...] = ("pv_fault",)

#: 显式历史兼容项目 ID。现有仅按 slot 分区的状态统一只读映射到该项目。
LEGACY_PROJECT_ID: str = "legacy"

#: 安全标识符：字母/数字开头，允许 `_ - .`，长度 1..128；额外禁止 `..`。
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _looks_absolute(value: str) -> bool:
    """粗略判断字符串是否像机器绝对路径（用于拒绝，不用于解析）。"""
    text = str(value or "")
    if not text:
        return False
    if text.startswith("/") or text.startswith("\\"):
        return True
    # Windows drive letter, e.g. C:\ or C:/
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        return True
    return False


def _validate_identifier(
    value: Any,
    *,
    field: str,
    next_action: str,
) -> str:
    """校验单个 scope 标识符；失败即 fail-closed 抛 ScopeError。"""
    if value is None:
        raise ScopeError(
            f"missing_{field}",
            f"缺少 {field}，无法确定当前 scope。",
            next_action=next_action,
        )
    text = str(value).strip()
    if not text:
        raise ScopeError(
            f"missing_{field}",
            f"{field} 为空，无法确定当前 scope。",
            next_action=next_action,
        )
    if _looks_absolute(text) or "/" in text or "\\" in text or ".." in text:
        raise ScopeError(
            f"invalid_{field}",
            f"{field} 含有非法字符或绝对路径片段：{text!r}。",
            next_action=next_action,
        )
    if not _SAFE_ID_RE.match(text):
        raise ScopeError(
            f"invalid_{field}",
            f"{field} 不是合法标识符：{text!r}。",
            next_action=next_action,
        )
    return text


@dataclass(frozen=True)
class ScopeContext:
    """已校验的项目 scope。

    字段：
        project_id: 客户 / 交付项目硬隔离键（必填）。
        slot: 诊断路径（可选；project 级页面可为 None）。
        dataset_version_id: 不可变数据版本（可选；数据相关对象才需要）。
        is_legacy: 是否为历史兼容项目（`project_id=legacy`）。
        read_only: 该 scope 是否只读（legacy 恒为只读）。
    """

    project_id: str
    slot: Optional[str] = None
    dataset_version_id: Optional[str] = None
    is_legacy: bool = False
    read_only: bool = False

    # -- 构造 --------------------------------------------------------------

    @classmethod
    def create(
        cls,
        project_id: Any,
        slot: Any = None,
        dataset_version_id: Any = None,
        *,
        require_slot: bool = False,
        require_dataset_version: bool = False,
        allow_legacy: bool = True,
    ) -> "ScopeContext":
        """从请求参数构造并校验一个 ScopeContext。

        Args:
            project_id: 必填。缺失 / 非法 / 无法解析都会 fail-closed。
            slot: 可选诊断路径；`require_slot=True` 时必填。
            dataset_version_id: 可选数据版本；`require_dataset_version=True` 时必填。
            require_slot: 是否要求 slot。
            require_dataset_version: 是否要求 dataset_version_id。
            allow_legacy: 是否允许 `project_id=legacy`（只读兼容页设 True，
                新产品写入路径应设 False，从源头拒绝把 legacy 当默认）。

        Raises:
            ScopeError: 任一校验失败。
        """
        pid = _validate_identifier(
            project_id,
            field="project_id",
            next_action="返回项目列表并选择或创建一个有效项目",
        )
        is_legacy = pid == LEGACY_PROJECT_ID
        if is_legacy and not allow_legacy:
            raise ScopeError(
                "legacy_project_not_allowed",
                "legacy 是历史只读兼容项目，不能承接新的产品写入或该操作。",
                next_action="切换到一个真实项目后重试",
                scope={"project_id": pid},
            )

        resolved_slot: Optional[str] = None
        if slot is not None and str(slot).strip() != "":
            resolved_slot = _validate_slot(slot, is_legacy=is_legacy)
        elif require_slot:
            raise ScopeError(
                "missing_slot",
                "缺少诊断路径 slot，无法确定当前 scope。",
                next_action="选择一个有效诊断路径（pv_day / pv_point / pv_tsc）",
                scope={"project_id": pid},
            )

        resolved_version: Optional[str] = None
        if dataset_version_id is not None and str(dataset_version_id).strip() != "":
            resolved_version = _validate_identifier(
                dataset_version_id,
                field="dataset_version_id",
                next_action="重新选择一个已发布的数据版本",
            )
        elif require_dataset_version:
            raise ScopeError(
                "missing_dataset_version_id",
                "缺少数据版本 dataset_version_id，无法确定当前数据 scope。",
                next_action="先在数据接入页发布或选择一个不可变数据版本",
                scope={"project_id": pid, "slot": resolved_slot},
            )

        return cls(
            project_id=pid,
            slot=resolved_slot,
            dataset_version_id=resolved_version,
            is_legacy=is_legacy,
            read_only=is_legacy,
        )

    # -- 取值 --------------------------------------------------------------

    def require_slot(self) -> str:
        """返回 slot；缺失则 fail-closed。"""
        if not self.slot:
            raise ScopeError(
                "missing_slot",
                "当前操作需要明确的诊断路径 slot。",
                next_action="选择一个有效诊断路径（pv_day / pv_point / pv_tsc）",
                scope=self.echo(),
            )
        return self.slot

    def require_dataset_version(self) -> str:
        """返回 dataset_version_id；缺失则 fail-closed。"""
        if not self.dataset_version_id:
            raise ScopeError(
                "missing_dataset_version_id",
                "当前操作需要明确的数据版本 dataset_version_id。",
                next_action="先在数据接入页发布或选择一个不可变数据版本",
                scope=self.echo(),
            )
        return self.dataset_version_id

    def with_slot(self, slot: Any) -> "ScopeContext":
        """派生一个带指定 slot 的新 scope（校验后）。"""
        return ScopeContext.create(
            self.project_id,
            slot,
            self.dataset_version_id,
            allow_legacy=self.is_legacy,
        )

    def with_dataset_version(self, dataset_version_id: Any) -> "ScopeContext":
        """派生一个带指定数据版本的新 scope（校验后）。"""
        return ScopeContext.create(
            self.project_id,
            self.slot,
            dataset_version_id,
            allow_legacy=self.is_legacy,
        )

    # -- 写入门禁 ----------------------------------------------------------

    def assert_writable(self) -> None:
        """legacy 只读兼容项目禁止新产品写入（R1.12）。"""
        if self.read_only or self.is_legacy:
            raise ScopeError(
                "legacy_read_only",
                "legacy 是历史只读兼容项目，禁止新准入 / freeze / candidate / registry / cursor 等写入。",
                next_action="切换到一个真实项目后重试",
                scope=self.echo(),
            )

    # -- 序列化与比对 ------------------------------------------------------

    def echo(self) -> dict[str, Any]:
        """产出用于响应回显与 scope mismatch 比对的 scope 片段。

        始终包含 project_id；slot / dataset_version_id 存在时才包含。
        """
        payload: dict[str, Any] = {"project_id": self.project_id}
        if self.slot is not None:
            payload["slot"] = self.slot
        if self.dataset_version_id is not None:
            payload["dataset_version_id"] = self.dataset_version_id
        return payload

    def partition(self) -> str:
        """repository 分区安全字符串，如 `legacy/pv_tsc` 或 `proj-1/pv_day`。"""
        parts = [self.project_id]
        if self.slot:
            parts.append(self.slot)
        return "/".join(parts)

    def key(self) -> tuple[Optional[str], ...]:
        """可哈希的 scope 键（用于缓存 / 断言 / 分区）。"""
        return (self.project_id, self.slot, self.dataset_version_id)

    def mismatches(self, payload: Any, *, fields: Optional[Iterable[str]] = None) -> list[str]:
        """比对响应 payload 是否回显了相同 scope。

        Returns:
            不一致或缺失的字段名列表（空列表表示一致）。
        """
        checked = tuple(fields) if fields is not None else self._default_check_fields()
        result: list[str] = []
        data = payload if isinstance(payload, dict) else {}
        for field in checked:
            expected = getattr(self, field)
            if expected is None:
                continue
            actual = data.get(field)
            if actual is None or str(actual) != str(expected):
                result.append(field)
        return result

    def _default_check_fields(self) -> tuple[str, ...]:
        fields = ["project_id"]
        if self.slot is not None:
            fields.append("slot")
        if self.dataset_version_id is not None:
            fields.append("dataset_version_id")
        return tuple(fields)


def _validate_slot(slot: Any, *, is_legacy: bool) -> str:
    """校验 slot 值；legacy 项目额外允许历史 `pv_fault`（只读）。"""
    key = str(slot or "").strip()
    if not key:
        raise ScopeError(
            "missing_slot",
            "缺少诊断路径 slot。",
            next_action="选择一个有效诊断路径（pv_day / pv_point / pv_tsc）",
        )
    if key in PRODUCT_SLOTS:
        return key
    if is_legacy and key in LEGACY_ONLY_SLOTS:
        return key
    allowed = list(PRODUCT_SLOTS) + (list(LEGACY_ONLY_SLOTS) if is_legacy else [])
    raise ScopeError(
        "invalid_slot",
        f"slot 必须是 {allowed!r} 之一，收到 {key!r}。",
        next_action="选择一个有效诊断路径（pv_day / pv_point / pv_tsc）",
    )


def check_response_scope(
    scope: ScopeContext,
    payload: Any,
    *,
    fields: Optional[Iterable[str]] = None,
) -> None:
    """断言响应 payload 回显了与请求一致的 scope，否则 fail-closed。

    供服务端在返回前二次校验，前端 `scopedApi` 也遵循同样契约（任务 1.4）。
    """
    bad = scope.mismatches(payload, fields=fields)
    if bad:
        raise ScopeError(
            "scope_mismatch",
            f"响应 scope 与当前请求不一致或缺失：{bad}。已拒绝渲染 / 写入。",
            next_action="清空旧状态并重新读取当前项目",
            scope=scope.echo(),
        )


# @AI_GENERATED: end
