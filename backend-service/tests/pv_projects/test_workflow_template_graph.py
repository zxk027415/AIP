# @AI_GENERATED
"""template 模式必须真正加载 canonical 模板图（「复用已有工作流」的核心缺口）。

此前 `create_project_workflow(mode='template')` 只把 `source_template_id` 记进记录、
**不加载模板的 nodes/edges**，于是"从模板创建"产出的是**空图**：界面上能看到工作流，
但它没有任何可执行节点，发起执行无从谈起。

本组用例固定：template 模式确实把 `data/workflows_enhanced/<id>.json` 的图装进来了，
且不存在的模板 id 要 fail-closed（而不是静默产出空图）。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

from services.pv_projects import ScopeContext  # noqa: E402
from services.pv_projects import repositories as repo  # noqa: E402
from services.pv_projects import workflows as wf_service  # noqa: E402

PID = "proj-tmpl-1"
TSC_TEMPLATE = "workflow-pv-tsc-train-eval-v1"
DAY_TEMPLATE = "workflow-pv-day-train-eval-v1"


@contextmanager
def env() -> Iterator[str]:
    tmp = tempfile.mkdtemp(prefix="pvtmpl_")
    repo.set_storage_base(tmp)
    try:
        yield tmp
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def test_template_mode_loads_canonical_graph() -> None:
    with env():
        scope = ScopeContext.create(PID, "pv_tsc")
        created = wf_service.create_project_workflow(
            scope,
            mode="template",
            name="TSC 训练（复用 canonical）",
            workflow_kind="training",
            source_template_id=TSC_TEMPLATE,
        )

        assert created["source_template_id"] == TSC_TEMPLATE
        assert created["create_mode"] == "template"
        # 核心断言：图非空 —— 修复前这里是 [] （空图）
        assert len(created["nodes"]) > 0, "template 模式必须装载模板节点"
        assert created["edges"] is not None
        # 节点确实来自该模板（带 functionId 配置）
        function_ids = {
            str((n.get("data") or {}).get("config", {}).get("functionId") or "")
            for n in created["nodes"]
        }
        assert "tsc_sliding_window" in function_ids, function_ids


def test_template_graph_differs_by_path() -> None:
    """不同路径复用各自的模板，图不同 —— 证明不是写死同一个。"""
    with env():
        tsc = wf_service.create_project_workflow(
            ScopeContext.create(PID, "pv_tsc"),
            mode="template",
            name="TSC",
            workflow_kind="training",
            source_template_id=TSC_TEMPLATE,
        )
        day = wf_service.create_project_workflow(
            ScopeContext.create(PID, "pv_day"),
            mode="template",
            name="Day",
            workflow_kind="training",
            source_template_id=DAY_TEMPLATE,
        )
        tsc_ids = {n.get("id") for n in tsc["nodes"]}
        day_ids = {n.get("id") for n in day["nodes"]}
        assert tsc_ids and day_ids
        assert tsc_ids != day_ids


def test_missing_template_fails_closed() -> None:
    """模板 id 不存在 → 抛错，不静默产出空图（空图会导致"看起来建好了但不能跑"）。"""
    with env():
        scope = ScopeContext.create(PID, "pv_tsc")
        try:
            wf_service.create_project_workflow(
                scope,
                mode="template",
                name="不存在的模板",
                workflow_kind="training",
                source_template_id="workflow-does-not-exist-v9",
            )
        except ValueError as exc:
            assert "模板不存在" in str(exc)
        else:
            raise AssertionError("缺模板时必须 fail-closed")


def test_copy_mode_still_copies_project_workflow_graph() -> None:
    """copy 模式行为不变：复制既有项目工作流的图。"""
    with env():
        scope = ScopeContext.create(PID, "pv_tsc")
        base = wf_service.create_project_workflow(
            scope,
            mode="template",
            name="v1",
            workflow_kind="training",
            source_template_id=TSC_TEMPLATE,
        )
        copied = wf_service.create_project_workflow(
            scope,
            mode="copy",
            name="v2",
            source_project_workflow_id=base["project_workflow_id"],
        )
        assert copied["version"] == int(base["version"]) + 1
        assert copied["version_group_id"] == base["version_group_id"]
        assert copied["parent_project_workflow_id"] == base["project_workflow_id"]
        assert len(copied["nodes"]) == len(base["nodes"])


# @AI_GENERATED: end
