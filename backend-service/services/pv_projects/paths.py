# @AI_GENERATED
"""scoped 相对路径解析模块。

设计依据：`design.md` §9（浏览器不直接读磁盘路径）、§16（registry 相对目录由部署配置决定）、
§26.5/§26.6（相对引用、不持久化机器绝对路径），以及工作区规则 `relative-paths-only`。

职责：
1. 按 `ScopeContext` 生成**相对**存储目录 / 文件引用（`projects/<project_id>/<slot>/...`），
   供 handler、service 与 repository 共用。
2. 把运行时解析出的绝对路径转回**相对引用**再持久化（`to_relative_ref`），
   绝不把机器绝对路径写回持久化结果（红线）。
3. 把相对引用解析为运行时可读写的绝对路径（`resolve_for_io`，搜索项目根 → backend → cwd）。
4. 拒绝缺失 / 非法 scope 与机器绝对路径输入（fail-closed）。

路径约定（与 `api/iterative_labeling._resolve_data_path` 一致）：
- 平台持久化数据（`data/...`）相对 `backend-service/` 解析。
- 外部数据集等相对引用优先相对项目根解析。
- 存储引用统一使用正斜杠（POSIX 风格），跨 macOS / Linux / Windows 可迁移。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

from services.pv_projects.errors import PathScopeError
from services.pv_projects.scope import ScopeContext

# backend-service/services/pv_projects/paths.py -> parents[2] == backend-service/
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_PROJECT_ROOT = _BACKEND_DIR.parent

#: 项目分区段名，scoped 目录形如 `<root>/projects/<project_id>/<slot>`。
PROJECTS_SEGMENT = "projects"

RootSpec = Union[str, Sequence[str]]


def backend_dir() -> Path:
    """backend-service/ 绝对目录（仅供运行时 I/O，不持久化）。"""
    return _BACKEND_DIR


def project_root() -> Path:
    """项目根 AIP/ 绝对目录（仅供运行时 I/O，不持久化）。"""
    return _PROJECT_ROOT


# ---------------------------------------------------------------------------
# 绝对路径检测与拒绝
# ---------------------------------------------------------------------------

def is_machine_absolute(path: object) -> bool:
    """判断输入是否为机器绝对路径（POSIX `/`、UNC `\\` 或 Windows 盘符 `C:\\`）。"""
    text = str(path or "")
    if not text:
        return False
    if text.startswith("/") or text.startswith("\\"):
        return True
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        return True
    return bool(os.path.isabs(text))


def assert_relative_ref(path: object, *, field: str = "artifact_ref") -> str:
    """确保 `path` 是相对引用（不是机器绝对路径），并归一化为正斜杠。

    Raises:
        PathScopeError: 输入为空、绝对路径或包含 `..` 越界。
    """
    text = str(path or "").strip()
    if not text:
        raise PathScopeError(
            f"missing_{field}",
            f"缺少 {field}，无法持久化相对引用。",
        )
    if is_machine_absolute(text):
        raise PathScopeError(
            "absolute_path_forbidden",
            f"{field} 不能是机器绝对路径：{text!r}。持久化只允许相对引用。",
            next_action="改用相对项目根或 backend-service 的相对路径",
        )
    normalized = text.replace("\\", "/")
    # 拒绝越界（指向存储根之外）。允许 `../` 仅在 to_relative_ref 归一化后出现受控前缀。
    if any(part == ".." for part in normalized.split("/")):
        raise PathScopeError(
            "path_escapes_scope",
            f"{field} 含有越界片段 `..`：{text!r}。",
            next_action="改用不含 `..` 的相对引用",
        )
    return normalized


# ---------------------------------------------------------------------------
# 相对 <-> 绝对 转换
# ---------------------------------------------------------------------------

def to_relative_ref(path: object, *, base: str = "backend", field: str = "artifact_ref") -> str:
    """把任意路径转成用于**持久化**的相对引用（正斜杠），绝不返回机器绝对路径。

    Args:
        path: 绝对或相对路径。
        base: `backend` 相对 backend-service/；`root` 相对项目根 AIP/。

    Raises:
        PathScopeError: 空值，或绝对路径落在允许的存储根之外。
    """
    text = str(path or "").strip()
    if not text:
        raise PathScopeError(f"missing_{field}", f"缺少 {field}，无法生成相对引用。")

    anchor = _BACKEND_DIR if base == "backend" else _PROJECT_ROOT

    if is_machine_absolute(text):
        abs_path = Path(text)
        for candidate_base in (anchor, _BACKEND_DIR, _PROJECT_ROOT):
            try:
                rel = os.path.relpath(str(abs_path), start=str(candidate_base))
            except (ValueError, OSError):
                continue
            rel_posix = rel.replace("\\", "/")
            if not rel_posix.startswith("../"):
                return rel_posix
        raise PathScopeError(
            "absolute_path_out_of_scope",
            f"{field} 绝对路径落在存储根之外，无法安全持久化：{text!r}。",
            next_action="把工件放到项目内相对目录后再登记",
        )

    # 已是相对路径：归一化正斜杠，去掉多余 `./`。
    normalized = text.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def resolve_for_io(relative_ref: object, *, must_exist: bool = False, field: str = "artifact_ref") -> Path:
    """把相对引用解析为运行时可读写的绝对路径（**不得持久化返回值**）。

    搜索顺序（对齐既有约定）：
    - `data/` 前缀：优先 backend-service/，再项目根；
    - 其他：优先项目根，再 backend-service/，最后 cwd。

    Raises:
        PathScopeError: 输入为绝对路径 / 越界；或 `must_exist=True` 但找不到文件。
    """
    normalized = assert_relative_ref(relative_ref, field=field)

    if normalized.startswith("data/"):
        search_bases: Iterable[Path] = (_BACKEND_DIR, _PROJECT_ROOT, Path.cwd())
    else:
        search_bases = (_PROJECT_ROOT, _BACKEND_DIR, Path.cwd())

    candidates = [base / normalized for base in search_bases]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    if must_exist:
        raise PathScopeError(
            "artifact_not_found",
            f"未找到相对引用对应的文件：{normalized!r}。",
            next_action="确认工件已生成并使用正确的相对引用",
        )
    # 找不到时返回首选候选（供写入场景创建），仍为绝对路径但不持久化。
    return candidates[0]


# ---------------------------------------------------------------------------
# scoped 目录 / 文件引用
# ---------------------------------------------------------------------------

def _split_root(root: RootSpec) -> list[str]:
    if isinstance(root, str):
        return [seg for seg in root.replace("\\", "/").split("/") if seg]
    return [str(seg).strip() for seg in root if str(seg).strip()]


def scoped_relative_dir(
    scope: ScopeContext,
    *,
    root: RootSpec,
    include_slot: bool = True,
    include_version: bool = False,
) -> str:
    """生成 scoped **相对**目录引用，如 `data/slot_governance/projects/proj-1/pv_tsc`。

    Args:
        scope: 已校验的项目 scope。
        root: 存储根（相对 backend-service），如 `"data/slot_governance"`。
        include_slot: 是否加入 slot 段（缺失则 fail-closed）。
        include_version: 是否加入 dataset_version_id 段（缺失则 fail-closed）。
    """
    segments = _split_root(root) + [PROJECTS_SEGMENT, scope.project_id]
    if include_slot:
        segments.append(scope.require_slot())
    if include_version:
        segments.append(scope.require_dataset_version())
    return "/".join(segments)


def scoped_relative_path(
    scope: ScopeContext,
    filename: str,
    *,
    root: RootSpec,
    include_slot: bool = True,
    include_version: bool = False,
) -> str:
    """在 scoped 目录下拼接一个文件名，返回相对引用。"""
    name = str(filename or "").strip().replace("\\", "/")
    if not name or name.startswith("/") or ".." in name.split("/"):
        raise PathScopeError(
            "invalid_filename",
            f"非法文件名：{filename!r}。",
        )
    base = scoped_relative_dir(
        scope,
        root=root,
        include_slot=include_slot,
        include_version=include_version,
    )
    return f"{base}/{name}"


def scoped_io_dir(
    scope: ScopeContext,
    *,
    root: RootSpec,
    include_slot: bool = True,
    include_version: bool = False,
    create: bool = False,
) -> Path:
    """返回 scoped 目录的运行时绝对路径（相对 backend-service 解析；**不持久化**）。"""
    rel = scoped_relative_dir(
        scope,
        root=root,
        include_slot=include_slot,
        include_version=include_version,
    )
    abs_dir = _BACKEND_DIR / Path(rel)
    if create:
        abs_dir.mkdir(parents=True, exist_ok=True)
    return abs_dir


def scoped_io_path(
    scope: ScopeContext,
    filename: str,
    *,
    root: RootSpec,
    include_slot: bool = True,
    include_version: bool = False,
    create_parent: bool = False,
) -> Path:
    """返回 scoped 文件的运行时绝对路径（**不持久化**）。"""
    rel = scoped_relative_path(
        scope,
        filename,
        root=root,
        include_slot=include_slot,
        include_version=include_version,
    )
    abs_path = _BACKEND_DIR / Path(rel)
    if create_parent:
        abs_path.parent.mkdir(parents=True, exist_ok=True)
    return abs_path


# @AI_GENERATED: end
