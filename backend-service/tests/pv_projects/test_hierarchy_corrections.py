# @AI_GENERATED
"""层级修正回归测试（design/pv_three_chain_hierarchy_lifecycle_2026-09-11.md 第 11 章 1/2/3/4/6 项）。

覆盖：
1. 总览 stage **消费 readiness**：项目有数据版本 ≠ 该路径"数据就绪"。
2. `workflow_kind`：training 可多个；detection **不可自建**。
3. 训练工作流绑定 `source_snapshot_id`：跨路径快照类型不匹配 → 拒绝。
4. preflight 路径契约硬校验：标签粒度不满足路径真值口径 → blocked；训练未绑快照 → warning + experiment_only。
5. 启用路径 intent：合法性校验 + 总览回显。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator

import pytest

from services.pv_projects import ScopeContext, dataset_profiles, dataset_versions, snapshots
from services.pv_projects import projects as project_service
from services.pv_projects import repositories as repo
from services.pv_projects import workflows as wf
from services.pv_projects.errors import ScopeError


@contextmanager
def temp_storage() -> Iterator[None]:
    tmp = tempfile.mkdtemp(prefix="pvproj_hier_")
    repo.set_storage_base(tmp)
    try:
        yield
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _new_project() -> str:
    rec = project_service.create_project(project_name="层级修正测试", solution_id="pv_fault")
    return rec["project_id"]


def _publish_version(pid: str, *, granularity: str = "", mapping_ok: bool = True) -> str:
    """在项目级发布一个数据版本 + 画像（直接写存储，避免依赖上传链路）。"""
    scope = ScopeContext.create(pid)
    mapping = {"time_col": "ts", "device_col": "dev", "value_col": "val"} if mapping_ok else {}
    profile = dataset_profiles.append(
        scope,
        {
            "dataset_profile_id": "dsp-hier-1",
            "mapping": mapping,
            "mapping_digest": "sha256:test",
            "label_policy": {"granularity": granularity} if granularity else {},
            "facts": {},
        },
    )
    version = dataset_versions.append(
        scope,
        {
            "dataset_version_id": "dsv-hier-1",
            "dataset_profile_id": profile["dataset_profile_id"],
            "artifact_ref": "data/slot_datasets/projects/x/dsv-hier-1.json",
            "content_digest": "sha256:aa",
            "immutable": True,
        },
    )
    return version["dataset_version_id"]


# ---------------------------------------------------------------------------
# 1. 总览消费 readiness
# ---------------------------------------------------------------------------

def test_overview_stage_consumes_readiness_not_blanket_data_ready() -> None:
    """设备日标签的数据：pv_day/pv_tsc 可用，pv_point 应为缺标签而非"数据就绪"。"""
    with temp_storage():
        pid = _new_project()
        _publish_version(pid, granularity="device_day")
        ov = project_service.project_overview(pid)
        by_slot = {p["slot"]: p for p in ov["paths"]}

        # pv_point：设备日标签不能当逐点真值 → 缺标签
        assert by_slot["pv_point"]["stage"] == "DATA_NEEDS_LABELS", by_slot["pv_point"]
        assert by_slot["pv_point"]["readiness_status"] == "needs_labels"
        assert by_slot["pv_point"]["readiness_primary_blocker"] == "device_day_label_not_point_truth"

        # pv_day / pv_tsc：标签粒度满足 → 可创建工作流
        for slot in ("pv_day", "pv_tsc"):
            assert by_slot[slot]["stage"] == "DATA_READY", by_slot[slot]
            assert by_slot[slot]["readiness_status"] in ("ready", "experiment_only")


def test_overview_stage_needs_mapping_when_profile_incomplete() -> None:
    with temp_storage():
        pid = _new_project()
        _publish_version(pid, mapping_ok=False)
        ov = project_service.project_overview(pid)
        for path in ov["paths"]:
            assert path["stage"] == "DATA_NEEDS_MAPPING", path
            assert path["readiness_status"] == "needs_mapping"


def test_overview_unconfigured_without_versions() -> None:
    with temp_storage():
        pid = _new_project()
        ov = project_service.project_overview(pid)
        assert all(p["stage"] == "UNCONFIGURED" for p in ov["paths"])
        # 未确认启用路径时回显 None，且三条路径始终返回（不隐藏）
        assert ov["enabled_slots"] is None
        assert len(ov["paths"]) == 3


def test_downstream_progress_overrides_readiness_stage() -> None:
    """已有下游产物（快照）时，阶段应反映进度，而不是回退到数据阶段。"""
    with temp_storage():
        pid = _new_project()
        _publish_version(pid, granularity="device_day")
        scope = ScopeContext.create(pid, "pv_point", require_slot=True)
        snapshots.append(scope, {"snapshot_id": "snap-1", "snapshot_type": "whole_day_point_box",
                                 "included_count": 3})
        ov = project_service.project_overview(pid)
        by_slot = {p["slot"]: p for p in ov["paths"]}
        path = by_slot["pv_point"]
        assert path["stage"] == "SNAPSHOT_READY", path
        # stage 回答历史进度；readiness 始终回答最新数据能否喂当前路径，二者互不覆盖。
        assert path["readiness_status"] == "needs_labels", path
        assert path["readiness_primary_blocker"] == "device_day_label_not_point_truth", path


# ---------------------------------------------------------------------------
# 2 & 3. workflow_kind + 快照绑定
# ---------------------------------------------------------------------------

def _scope(pid: str, slot: str = "pv_tsc") -> ScopeContext:
    return ScopeContext.create(pid, slot, require_slot=True, allow_legacy=False)


def test_multiple_training_workflows_per_path() -> None:
    with temp_storage():
        pid = _new_project()
        scope = _scope(pid)
        a = wf.create_project_workflow(scope, mode="blank", name="训练A")
        b = wf.create_project_workflow(scope, mode="blank", name="训练B")
        assert a["workflow_kind"] == "training" and b["workflow_kind"] == "training"
        assert a["project_workflow_id"] != b["project_workflow_id"]
        assert len(wf.list_project_workflows(scope)) == 2  # 1 路径 : N 训练工作流


def test_detection_workflow_cannot_be_created() -> None:
    with temp_storage():
        scope = _scope(_new_project())
        with pytest.raises(ValueError) as ei:
            wf.create_project_workflow(scope, mode="blank", name="自建检测", workflow_kind="detection")
        assert "detection" in str(ei.value)


def test_unknown_workflow_kind_rejected() -> None:
    with temp_storage():
        scope = _scope(_new_project())
        with pytest.raises(ValueError):
            wf.create_project_workflow(scope, mode="blank", name="x", workflow_kind="whatever")


def test_training_workflow_binds_snapshot() -> None:
    with temp_storage():
        pid = _new_project()
        scope = _scope(pid, "pv_tsc")
        snapshots.append(scope, {"snapshot_id": "snap-tsc", "snapshot_type": "tsc_288x3_grid",
                                 "included_count": 5})
        rec = wf.create_project_workflow(scope, mode="blank", name="训练", source_snapshot_id="snap-tsc")
        assert rec["bound_snapshot_id"] == "snap-tsc"
        assert rec["bound_snapshot_type"] == "tsc_288x3_grid"


def test_cross_path_snapshot_type_rejected() -> None:
    """把 point 路径的整日盒快照绑到 TSC 训练工作流 → 拒绝。"""
    with temp_storage():
        pid = _new_project()
        scope = _scope(pid, "pv_tsc")
        snapshots.append(scope, {"snapshot_id": "snap-wrong", "snapshot_type": "whole_day_point_box"})
        with pytest.raises(ValueError) as ei:
            wf.create_project_workflow(scope, mode="blank", name="训练", source_snapshot_id="snap-wrong")
        assert "快照类型与路径不匹配" in str(ei.value)


def test_missing_snapshot_rejected() -> None:
    with temp_storage():
        scope = _scope(_new_project())
        with pytest.raises(ValueError):
            wf.create_project_workflow(scope, mode="blank", name="训练", source_snapshot_id="snap-nope")


# ---------------------------------------------------------------------------
# 4. preflight 路径契约
# ---------------------------------------------------------------------------

def _checks_by_key(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["key"]: c for c in result["checks"]}


def test_preflight_blocks_granularity_mismatch_for_point_path() -> None:
    """设备日标签 + pv_point → 路径契约阻断。"""
    with temp_storage():
        pid = _new_project()
        version_id = _publish_version(pid, granularity="device_day")
        scope = _scope(pid, "pv_point")
        pwf = wf.create_project_workflow(
            scope, mode="blank", name="点训练",
            nodes=[{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            dataset_version_id=version_id,
        )
        res = wf.run_preflight(scope, project_workflow_id=pwf["project_workflow_id"])
        checks = _checks_by_key(res)
        assert checks["path_contract"]["status"] == "blocked", checks["path_contract"]
        assert res["overall"] == "blocked"
        assert res["allowed_to_run"] is False


def test_preflight_training_without_snapshot_is_experiment_only() -> None:
    with temp_storage():
        pid = _new_project()
        version_id = _publish_version(pid, granularity="device_day")
        scope = _scope(pid, "pv_tsc")
        pwf = wf.create_project_workflow(
            scope, mode="blank", name="无快照训练",
            nodes=[{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            dataset_version_id=version_id,
        )
        res = wf.run_preflight(scope, project_workflow_id=pwf["project_workflow_id"])
        checks = _checks_by_key(res)
        assert checks["training_input"]["status"] == "warning"
        assert res["experiment_only"] is True
        assert res["allowed_to_run"] is True  # 可做实验，只是不能成为可治理候选


def test_preflight_training_with_matching_snapshot_passes_contract() -> None:
    with temp_storage():
        pid = _new_project()
        version_id = _publish_version(pid, granularity="device_day")
        scope = _scope(pid, "pv_tsc")
        snapshots.append(scope, {"snapshot_id": "snap-ok", "snapshot_type": "tsc_288x3_grid",
                                 "included_count": 7})
        pwf = wf.create_project_workflow(
            scope, mode="blank", name="带快照训练",
            nodes=[{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            dataset_version_id=version_id, source_snapshot_id="snap-ok",
        )
        res = wf.run_preflight(scope, project_workflow_id=pwf["project_workflow_id"])
        checks = _checks_by_key(res)
        assert checks["path_contract"]["status"] == "passed"
        assert checks["training_input"]["status"] == "passed"
        assert res["overall"] != "blocked"


# ---------------------------------------------------------------------------
# 5. 启用路径 intent
# ---------------------------------------------------------------------------

def test_set_enabled_slots_roundtrip() -> None:
    with temp_storage():
        pid = _new_project()
        project_service.set_enabled_slots(pid, ["pv_tsc"])
        ov = project_service.project_overview(pid)
        assert ov["enabled_slots"] == ["pv_tsc"]
        assert len(ov["paths"]) == 3  # 仍返回三条，由前端开关决定是否只显示已启用

        # 撤销确认
        project_service.set_enabled_slots(pid, None)
        assert project_service.project_overview(pid)["enabled_slots"] is None


def test_set_enabled_slots_rejects_invalid() -> None:
    with temp_storage():
        pid = _new_project()
        with pytest.raises(ScopeError):
            project_service.set_enabled_slots(pid, ["pv_day", "not_a_slot"])
        with pytest.raises(ScopeError):
            project_service.set_enabled_slots(pid, [])


def test_legacy_project_cannot_set_enabled_slots() -> None:
    with temp_storage():
        with pytest.raises(ScopeError):
            project_service.set_enabled_slots("legacy", ["pv_day"])

# @AI_GENERATED: end
