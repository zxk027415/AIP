# @AI_GENERATED
"""P0 门禁回归测试（semantic-review/2026-09-14-102909-pr-0.md 的 P0-1 / P0-2 / P0-3）。

本文件是 Wave 1 的 **RED 基线**：三条用例在修复前必须失败，修复后必须通过。

覆盖：
1. P0-1 — execution 不得绕过项目工作流与 preflight：
   不存在的 `project_workflow_id` 必须被拒绝（当前会静默落一条 governance_eligible=true 的执行记录）。
2. P0-2 — candidate 不得由客户端覆盖治理资格：
   对 validation execution 登记候选时，`governance_eligible` 必须恒为 false
   （当前请求体传 True 即可覆盖）。
3. P0-3 — preflight 必须能真正 passed：
   完整 ready + 匹配快照 + 齐备契约时，`overall == "passed"` 且 `experiment_only is False`
   （当前 `resource_estimate` 恒为 warning，导致 overall 上界为 warning、experiment_only 恒 true）。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

import pytest

from services.pv_projects import ScopeContext, dataset_profiles, dataset_versions, snapshots
from services.pv_projects import governance as gov
from services.pv_projects import projects as project_service
from services.pv_projects import repositories as repo
from services.pv_projects import workflows as wf
from services.pv_projects.errors import ScopeError
from services.pv_projects.runner import get_runner
from services.pv_projects.stores import executions


@contextmanager
def temp_storage() -> Iterator[None]:
    tmp = tempfile.mkdtemp(prefix="pvproj_p0_")
    repo.set_storage_base(tmp)
    try:
        yield
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _new_project() -> str:
    rec = project_service.create_project(project_name="P0 门禁测试", solution_id="pv_fault")
    return rec["project_id"]


def _publish_ready_version(pid: str, *, slot: str, granularity: str = "device_day") -> str:
    """发布一个 readiness=ready 的数据版本 + 画像（直接写存储，不依赖上传链路）。

    `facts.sufficient_coverage=True` 是 readiness 判定 ready 的唯一开关
    （services/pv_projects/readiness.py::evaluate_path_readiness）。
    """
    scope = ScopeContext.create(pid)
    profile = dataset_profiles.append(
        scope,
        {
            "dataset_profile_id": "dsp-p0-1",
            "mapping": {"time_col": "ts", "device_col": "dev", "value_col": "val"},
            "mapping_digest": "sha256:p0",
            "label_policy": {"granularity": granularity},
            "facts": {"sufficient_coverage": True},
        },
    )
    version = dataset_versions.append(
        scope,
        {
            "dataset_version_id": "dsv-p0-1",
            "dataset_profile_id": profile["dataset_profile_id"],
            "artifact_ref": "data/slot_datasets/projects/x/dsv-p0-1.json",
            "content_digest": "sha256:p0",
            "immutable": True,
        },
    )
    return version["dataset_version_id"]


def _scope(pid: str, slot: str = "pv_tsc") -> ScopeContext:
    return ScopeContext.create(pid, slot, require_slot=True, allow_legacy=False)


# ---------------------------------------------------------------------------
# P0-1：execution 不得绕过工作流与 preflight
# ---------------------------------------------------------------------------

def test_execution_rejects_unknown_workflow() -> None:
    """`project_workflow_id` 在当前 scope 不存在时必须拒绝，不得形成执行记录。

    修复前：runner.start_execution 从不查 stores.project_workflows，
    任意字符串都能落一条 running 记录（run_mode=training 时 governance_eligible=true）。
    """
    with temp_storage():
        pid = _new_project()
        scope = _scope(pid, "pv_tsc")

        with pytest.raises(ScopeError):
            get_runner().start_execution(
                scope,
                project_workflow_id="pwf-does-not-exist",
                run_mode="training",
            )

        # 关键副作用断言：不得留下任何执行记录。
        assert executions.list(scope) == []


def test_execution_rejects_blocked_preflight() -> None:
    """预检 blocked 时不得创建执行。

    构造：pv_point 路径 + 设备日标签 + 工作流带 load 节点 → path_contract 阻断。
    修复前：runner 不调 preflight，直接落 running 记录。
    """
    with temp_storage():
        pid = _new_project()
        version_id = _publish_ready_version(pid, slot="pv_point", granularity="device_day")
        scope = _scope(pid, "pv_point")

        pwf = wf.create_project_workflow(
            scope,
            mode="blank",
            name="点路径训练（粒度不符）",
            nodes=[{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            dataset_version_id=version_id,
        )
        pre = wf.run_preflight(scope, project_workflow_id=pwf["project_workflow_id"])
        assert pre["overall"] == "blocked", pre  # 先确认 fixture 真的 blocked

        with pytest.raises(ScopeError):
            get_runner().start_execution(
                scope,
                project_workflow_id=pwf["project_workflow_id"],
                run_mode="training",
            )
        assert executions.list(scope) == []


def test_execution_fixates_workflow_lineage() -> None:
    """执行记录必须固化工作流用途 / 版本 / 绑定数据版本 / 绑定快照 / preflight 摘要。

    修复前：记录里只有 project_workflow_id 这个不透明字符串，没有可核验的固化字段。
    """
    with temp_storage():
        pid = _new_project()
        version_id = _publish_ready_version(pid, slot="pv_tsc", granularity="device_day")
        scope = _scope(pid, "pv_tsc")
        snapshots.append(
            scope,
            {"snapshot_id": "snap-p0", "snapshot_type": "tsc_288x3_grid", "included_count": 4},
        )
        pwf = wf.create_project_workflow(
            scope,
            mode="blank",
            name="TSC 训练",
            workflow_kind="training",
            nodes=[{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            dataset_version_id=version_id,
            source_snapshot_id="snap-p0",
        )
        rec = get_runner().start_execution(
            scope,
            project_workflow_id=pwf["project_workflow_id"],
            run_mode="training",
        )
        assert rec["workflow_kind"] == "training", rec
        assert rec["workflow_version"] == pwf["version"], rec
        assert rec["bound_dataset_version_id"] == version_id, rec
        assert rec["bound_snapshot_id"] == "snap-p0", rec
        assert isinstance(rec.get("preflight"), dict), rec
        assert rec["preflight"]["overall"] == "passed", rec["preflight"]


def test_run_mode_must_match_workflow_kind() -> None:
    """labeling 工作流不得以 run_mode=training 执行（否则可伪装成可治理训练）。"""
    with temp_storage():
        pid = _new_project()
        scope = _scope(pid, "pv_tsc")
        pwf = wf.create_project_workflow(scope, mode="blank", name="打标", workflow_kind="labeling")
        with pytest.raises(ScopeError):
            get_runner().start_execution(
                scope,
                project_workflow_id=pwf["project_workflow_id"],
                run_mode="training",
            )


# ---------------------------------------------------------------------------
# P0-2：candidate 不得由客户端覆盖治理资格 / 伪造 lineage
# ---------------------------------------------------------------------------

def _validation_execution(scope: ScopeContext, workflow_id: str) -> str:
    """直接写一条 validation execution（governance_eligible=false）。

    刻意绕过 runner：本条用例考的是候选登记门禁，不是执行门禁。
    """
    rec = executions.append(
        scope,
        {
            "execution_id": "exec-validation-p0",
            "project_workflow_id": workflow_id,
            "dataset_version_id": None,
            "run_mode": "validation",
            "run_domain": "project",
            "governance_eligible": False,
            "status": "success",
            "node_timeline": [],
            "result_destination": "validation_execution",
        },
    )
    return rec["execution_id"]


def test_candidate_cannot_self_grant_governance() -> None:
    """validation execution 的候选恒不可治理，即使请求体传 governance_eligible=True。

    修复前：register_candidate 只在形参为 None 时才推导，传 True 即被采信。
    """
    with temp_storage():
        pid = _new_project()
        scope = _scope(pid, "pv_tsc")
        pwf = wf.create_project_workflow(scope, mode="blank", name="打标", workflow_kind="labeling")
        exec_id = _validation_execution(scope, pwf["project_workflow_id"])

        candidate = gov.register_candidate(
            scope,
            source_execution_id=exec_id,
            model_artifact_ref="data/models/p0/model.pkl",
            governance_eligible=True,  # 客户端试图自授治理资格
        )
        assert candidate["governance_eligible"] is False, candidate


def test_candidate_lineage_derived_from_execution() -> None:
    """候选的 source_workflow_id / source_dataset_version_id 必须与 execution 一致。"""
    with temp_storage():
        pid = _new_project()
        version_id = _publish_ready_version(pid, slot="pv_tsc", granularity="device_day")
        scope = _scope(pid, "pv_tsc")
        snapshots.append(
            scope,
            {"snapshot_id": "snap-p0b", "snapshot_type": "tsc_288x3_grid", "included_count": 2},
        )
        pwf = wf.create_project_workflow(
            scope,
            mode="blank",
            name="TSC 训练",
            workflow_kind="training",
            nodes=[{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            dataset_version_id=version_id,
            source_snapshot_id="snap-p0b",
        )
        exec_rec = get_runner().start_execution(
            scope,
            project_workflow_id=pwf["project_workflow_id"],
            run_mode="training",
        )
        get_runner().finalize(scope, exec_rec["execution_id"], status="success",
                              result_destination="governable_candidate")

        candidate = gov.register_candidate(
            scope,
            source_execution_id=exec_rec["execution_id"],
            model_artifact_ref="data/models/p0/model.pkl",
            # 客户端提供与 execution 不符的血缘，必须被拒绝或忽略
            source_workflow_id="pwf-forged",
            source_snapshot_id="snap-forged",
        )
        assert candidate["source_workflow_id"] == pwf["project_workflow_id"], candidate
        assert candidate["source_snapshot_id"] == "snap-p0b", candidate
        assert candidate["governance_eligible"] is True, candidate


def test_candidate_requires_successful_execution() -> None:
    """未成功的 execution 不得产出候选。"""
    with temp_storage():
        pid = _new_project()
        scope = _scope(pid, "pv_tsc")
        pwf = wf.create_project_workflow(scope, mode="blank", name="训练", workflow_kind="training")
        executions.append(
            scope,
            {
                "execution_id": "exec-failed-p0",
                "project_workflow_id": pwf["project_workflow_id"],
                "run_mode": "training",
                "run_domain": "project",
                "governance_eligible": True,
                "status": "failed",
                "node_timeline": [],
                "failure_reason": "boom",
            },
        )
        with pytest.raises(gov.GovernanceGateError):
            gov.register_candidate(
                scope,
                source_execution_id="exec-failed-p0",
                model_artifact_ref="data/models/p0/model.pkl",
            )


# ---------------------------------------------------------------------------
# P0-3：preflight 必须能真正 passed
# ---------------------------------------------------------------------------

def test_preflight_passes_when_ready_and_snapshot_matched() -> None:
    """ready + 匹配快照 + 齐备契约 → overall=passed 且 experiment_only=false。

    修复前：`resource_estimate` 无条件以 CHECK_WARNING 追加，
    使 overall 上界恒为 warning、experiment_only 恒为 true。
    """
    with temp_storage():
        pid = _new_project()
        version_id = _publish_ready_version(pid, slot="pv_tsc", granularity="device_day")
        scope = _scope(pid, "pv_tsc")
        snapshots.append(
            scope,
            {"snapshot_id": "snap-p0c", "snapshot_type": "tsc_288x3_grid", "included_count": 9},
        )
        pwf = wf.create_project_workflow(
            scope,
            mode="blank",
            name="完整训练",
            workflow_kind="training",
            nodes=[{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            dataset_version_id=version_id,
            source_snapshot_id="snap-p0c",
        )
        res = wf.run_preflight(scope, project_workflow_id=pwf["project_workflow_id"])

        checks = {c["key"]: c for c in res["checks"]}
        assert checks["path_contract"]["status"] == "passed", checks["path_contract"]
        assert checks["training_input"]["status"] == "passed", checks["training_input"]
        assert checks["coverage"]["status"] == "passed", checks["coverage"]

        assert res["overall"] == "passed", res
        assert res["experiment_only"] is False, res
        assert res["allowed_to_run"] is True, res


def test_resource_estimate_warning_is_informational() -> None:
    """资源估计是信息性提示，不得降级治理资格（不得把 overall 压成 warning）。"""
    with temp_storage():
        pid = _new_project()
        version_id = _publish_ready_version(pid, slot="pv_tsc", granularity="device_day")
        scope = _scope(pid, "pv_tsc")
        snapshots.append(
            scope,
            {"snapshot_id": "snap-p0d", "snapshot_type": "tsc_288x3_grid", "included_count": 1},
        )
        pwf = wf.create_project_workflow(
            scope,
            mode="blank",
            name="完整训练2",
            workflow_kind="training",
            nodes=[{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            dataset_version_id=version_id,
            source_snapshot_id="snap-p0d",
        )
        res = wf.run_preflight(scope, project_workflow_id=pwf["project_workflow_id"])
        checks = {c["key"]: c for c in res["checks"]}
        # 信息性检查仍以 warning 呈现给用户，但带 governance_impact=none
        assert checks["resource_estimate"]["status"] == "warning"
        assert checks["resource_estimate"]["governance_impact"] == "none"
        assert res["overall"] == "passed"


# @AI_GENERATED: end
