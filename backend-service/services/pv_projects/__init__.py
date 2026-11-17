# @AI_GENERATED
"""pv_projects：项目化 scope 与 scoped 存储的共享基础设施。

本包提供 `pv-three-chain-product-validation` 规格的最小上下文原语：
- `ScopeContext`：已校验的 `(project_id, slot, dataset_version_id)` 上下文；
- 相对路径解析：scoped 相对目录 / 文件引用，绝对路径拒绝与相对化。

上层 API handler、service 与 repository 共用这些原语实现项目 / 槽位硬隔离
与 legacy 只读兼容。
"""

from __future__ import annotations

from services.pv_projects.errors import PathScopeError, ScopeError
from services.pv_projects.scope import (
    LEGACY_ONLY_SLOTS,
    LEGACY_PROJECT_ID,
    PRODUCT_SLOTS,
    ScopeContext,
    check_response_scope,
)
from services.pv_projects.paths import (
    PROJECTS_SEGMENT,
    assert_relative_ref,
    backend_dir,
    is_machine_absolute,
    project_root,
    resolve_for_io,
    scoped_io_dir,
    scoped_io_path,
    scoped_relative_dir,
    scoped_relative_path,
    to_relative_ref,
)
from services.pv_projects.repositories import (
    ScopedAppendOnlyLog,
    ScopedCollectionRepository,
    ScopedDocRepository,
    ensure_project_layout,
    migrate_projects_index,
    read_projects_index,
    register_project_in_index,
)
from services.pv_projects.stores import (
    SCOPED_STORAGE_ROOTS,
    ScopedRegistryStore,
    candidates,
    cumulative_events,
    cursors,
    dataset_assets,
    dataset_profiles,
    dataset_versions,
    ensure_layout,
    executions,
    get_scoped_registry_store,
    materialization_tasks,
    migrate,
    promotions_log,
    project_workflows,
    results,
    reviews,
    sandbox_runs,
    snapshots,
    validation_batches,
    benchmark_evidence,
    verifications,
)

__all__ = [
    "ScopeError",
    "PathScopeError",
    "ScopeContext",
    "check_response_scope",
    "PRODUCT_SLOTS",
    "LEGACY_ONLY_SLOTS",
    "LEGACY_PROJECT_ID",
    "PROJECTS_SEGMENT",
    "backend_dir",
    "project_root",
    "is_machine_absolute",
    "assert_relative_ref",
    "to_relative_ref",
    "resolve_for_io",
    "scoped_relative_dir",
    "scoped_relative_path",
    "scoped_io_dir",
    "scoped_io_path",
    # repositories
    "ScopedDocRepository",
    "ScopedCollectionRepository",
    "ScopedAppendOnlyLog",
    "ensure_project_layout",
    "migrate_projects_index",
    "read_projects_index",
    "register_project_in_index",
    # stores
    "ScopedRegistryStore",
    "get_scoped_registry_store",
    "SCOPED_STORAGE_ROOTS",
    "candidates",
    "verifications",
    "promotions_log",
    "dataset_versions",
    "dataset_profiles",
    "dataset_assets",
    "materialization_tasks",
    "executions",
    "reviews",
    "cumulative_events",
    "snapshots",
    "results",
    "cursors",
    "project_workflows",
    "validation_batches",
    "benchmark_evidence",
    "sandbox_runs",
    "migrate",
    "ensure_layout",
]

# @AI_GENERATED: end
