# @AI_GENERATED
"""具体的 scoped 对象仓储（registry / candidate / execution / review / ...）。

在 `repositories.py` 的通用核心之上，为每类产品对象配置存储根、文件名与 legacy 映射。

关键约定（对齐 `design.md` §7、§16 与 `requirements.md` R3.6–R3.9）：
- `registry.json` 是当前模型指针**单独真源**（Champion / Challenger / rolling_detect_model /
  registry_version）；legacy 读取直接复用现有 slot-only registry，保证行为一致且只读。
- `model_candidates.json` 与当前指针分开；候选历史不等于当前模型。
- `promotions_log.json` 只追加，不改历史。
- 缺失对象返回“当前项目未产出”空态，绝不读取 legacy 同槽或其他项目补位。
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from services.pv_projects.repositories import (
    ScopedAppendOnlyLog,
    ScopedCollectionRepository,
    ScopedDocRepository,
    ensure_project_layout,
    migrate_projects_index,
)
from services.pv_projects.scope import ScopeContext

# 各对象类型使用的存储根（相对 backend-service）。
_GOVERNANCE_ROOT = "data/slot_governance"
_DATASETS_ROOT = "data/slot_datasets"
_PROJECTS_ROOT = "data/pv_projects"

#: 创建新项目时需要幂等建骨架的存储根集合。
SCOPED_STORAGE_ROOTS = [_GOVERNANCE_ROOT, _DATASETS_ROOT, _PROJECTS_ROOT]


# ---------------------------------------------------------------------------
# registry：当前模型指针单独真源
# ---------------------------------------------------------------------------

class ScopedRegistryStore:
    """按 `(project_id, slot)` 读写当前模型登记；legacy 只读复用现有 slot registry。"""

    def __init__(self) -> None:
        self._repo = ScopedDocRepository(
            root=_GOVERNANCE_ROOT,
            filename="registry.json",
            doc_kind="registry",
        )

    def _empty_view(self, scope: ScopeContext, *, diagnostic: Optional[str] = None) -> dict[str, Any]:
        return {
            "project_id": scope.project_id,
            "slot": scope.slot,
            "registry_version": 0,
            "updated_at": None,
            "champion": None,
            "challenger": None,
            "rolling_detect_model": None,
            # 随路径累计快照继承的只读 baseline；不具 Promote / rolling 治理效力。
            "inherited_baseline": None,
            "note": None,
            "empty": True,
            "read_only": scope.read_only,
            "diagnostic": diagnostic or "当前项目未产出该 registry",
        }

    def get(self, scope: ScopeContext) -> dict[str, Any]:
        if scope.is_legacy:
            # legacy 只读映射：直接复用现有 slot-only registry，行为完全一致。
            from services.slot_governance.registry import get_registry_store

            view = dict(get_registry_store().get(scope.require_slot()))
            view["project_id"] = "legacy"
            view["read_only"] = True
            return view
        doc = self._repo.read(scope)
        if doc is None:
            return self._empty_view(scope)
        doc.setdefault("project_id", scope.project_id)
        doc.setdefault("slot", scope.slot)
        doc.setdefault("inherited_baseline", None)
        doc["empty"] = int(doc.get("registry_version") or 0) == 0
        doc.setdefault("read_only", False)
        return doc

    def save(self, scope: ScopeContext, payload: dict[str, Any]) -> dict[str, Any]:
        """写入 registry；legacy 只读则拒绝。版本号由调用方显式设置（与既有语义一致）。"""
        scope.assert_writable()
        return self._repo.write(scope, payload)

    def update(
        self,
        scope: ScopeContext,
        mutator: Callable[[dict[str, Any]], Optional[dict[str, Any]]],
    ) -> dict[str, Any]:
        """原子 read-modify-write；mutator 返回 None 表示幂等命中、不写不增版本。

        继承 baseline 可能与人工 Promote 同时更新同一份 registry。单独 ``get`` 后再
        ``save`` 会让后写者覆盖先写者；这里复用 repository 的同路径可重入锁，把读、
        合并、原子替换包进同一临界区。
        """
        scope.assert_writable()
        from services.pv_projects.repositories import _write_lock

        with _write_lock(
            scope,
            root=self._repo.root,
            filename=self._repo.filename,
            include_slot=self._repo.include_slot,
            include_version=self._repo.include_version,
        ):
            current = self.get(scope)
            updated = mutator(dict(current))
            if updated is None:
                return current
            return self.save(scope, updated)

    def next_version(self, scope: ScopeContext) -> int:
        return int(self.get(scope).get("registry_version") or 0) + 1


_registry_store = ScopedRegistryStore()


def get_scoped_registry_store() -> ScopedRegistryStore:
    return _registry_store


# ---------------------------------------------------------------------------
# 集合类对象仓储实例
# ---------------------------------------------------------------------------

# 候选历史（与当前指针分开）
candidates = ScopedCollectionRepository(
    root=_GOVERNANCE_ROOT,
    filename="model_candidates.json",
    items_key="candidates",
    id_field="model_candidate_id",
)

# 正式复验记录
verifications = ScopedCollectionRepository(
    root=_GOVERNANCE_ROOT,
    filename="verifications.json",
    items_key="verifications",
    id_field="verification_id",
)

# Promote 审计日志（append-only）
promotions_log = ScopedAppendOnlyLog(
    root=_GOVERNANCE_ROOT,
    filename="promotions_log.json",
    items_key="events",
    id_field="promotion_id",
)

# 数据版本（不可变发布记录）——项目级：一个版本可服务三条诊断路径（design §3），不按 slot 分区
dataset_versions = ScopedCollectionRepository(
    root=_DATASETS_ROOT,
    filename="dataset_versions.json",
    items_key="versions",
    id_field="dataset_version_id",
    include_slot=False,
)

# 数据画像 / 字段映射版本（项目级，不可变）
dataset_profiles = ScopedCollectionRepository(
    root=_DATASETS_ROOT,
    filename="dataset_profiles.json",
    items_key="profiles",
    id_field="dataset_profile_id",
    include_slot=False,
)

# execution 证据（新项目 scoped 记录；legacy execution 仍由 execution_history 现有模块服务）
executions = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="executions.json",
    items_key="executions",
    id_field="execution_id",
)

# 审核会话
reviews = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="reviews.json",
    items_key="reviews",
    id_field="review_id",
)

# 累计入账事件
cumulative_events = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="cumulative_events.json",
    items_key="events",
    id_field="event_id",
)

# 冻结快照
snapshots = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="snapshots.json",
    items_key="snapshots",
    id_field="snapshot_id",
)

# 结果对象（预测批次 / 实验工件索引）
results = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="results.json",
    items_key="results",
    id_field="result_id",
)

# 数据资产（项目级：一个资产可有多个不可变版本，可服务多条诊断路径；不按 slot 分区）
dataset_assets = ScopedCollectionRepository(
    root=_DATASETS_ROOT,
    filename="dataset_assets.json",
    items_key="assets",
    id_field="dataset_id",
    include_slot=False,
)

# 长连接器物化任务（项目级；用于刷新后按 task_id 恢复进度）
materialization_tasks = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="materialization_tasks.json",
    items_key="tasks",
    id_field="task_id",
    include_slot=False,
)

# 检测 / replay 游标（每个 scope 一份文档）
cursors = ScopedDocRepository(
    root=_PROJECTS_ROOT,
    filename="cursor.json",
    doc_kind="cursor",
)

# 项目工作流版本（从 canonical 模板 / 复制 / 空白创建，绑定 dataset_version_id；
# 与共享模板分离，绝不覆盖共享模板）——按 slot 分区（一条工作流属于某条诊断路径）
project_workflows = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="project_workflows.json",
    items_key="workflows",
    id_field="project_workflow_id",
)

# 跨数据集验收批次（product-validation；governance_effect=none）——项目级
validation_batches = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="validation_batches.json",
    items_key="batches",
    id_field="validation_id",
    include_slot=False,
)

# 只读离线基准证据版本（offline_benchmark_evidence；governance_effect=none）——项目级
benchmark_evidence = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="benchmark_evidence.json",
    items_key="evidence",
    id_field="benchmark_evidence_version",
    include_slot=False,
)

# Sandbox 运行域状态（按 (project_id, sandbox_id, slot) 隔离水位/cursor/审核/结果）——slot 分区
sandbox_runs = ScopedCollectionRepository(
    root=_PROJECTS_ROOT,
    filename="sandbox_runs.json",
    items_key="sandboxes",
    id_field="sandbox_id",
)


# ---------------------------------------------------------------------------
# 迁移与骨架
# ---------------------------------------------------------------------------

def migrate() -> dict[str, Any]:
    """幂等迁移入口：建立项目索引并登记 legacy 只读映射（不复制 legacy 记录）。"""
    return migrate_projects_index()


def ensure_layout(scope: ScopeContext) -> None:
    """为一个真实项目幂等创建 scoped 目录骨架。"""
    ensure_project_layout(scope, roots=SCOPED_STORAGE_ROOTS)


# @AI_GENERATED: end
