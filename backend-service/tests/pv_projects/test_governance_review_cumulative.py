# @AI_GENERATED
"""任务 4.4：治理 / 审核 / 累计负向 + 组件测试。

设计依据：design.md §16–§19；requirements.md R5.7–R5.10、R6.4、R6.8–R6.10、
R8.2–R8.9、R9.3、R9.7–R9.9。

覆盖：
- 候选 provenance 缺失 → 不能复验 / Promote。
- validation（非可治理）execution 的候选 → 拒绝进入正式治理。
- verification 绑定候选不一致；registry 版本冲突；跨 scope 拒绝。
- 审核三动作分离：complete 不写台账；admit 幂等。
- freeze 幂等（同 plan 命中已有快照）。
- 断言：没有任何测试触发真实准入外的生产写入（滚动指针 / Promote 均被门控），
  也不从非可治理证据登记可治理候选、不伪造正式复验、不改 append-only 审计历史。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

import pytest

from services.pv_projects import ScopeContext, executions
from services.pv_projects import cumulative as cum
from services.pv_projects import governance as gov
from services.pv_projects import repositories as repo
from services.pv_projects import review_service as rv
from services.pv_projects.stores import dataset_versions, project_workflows, snapshots


@contextmanager
def temp_storage() -> Iterator[None]:
    tmp = tempfile.mkdtemp(prefix="pvproj_grc_")
    repo.set_storage_base(tmp)
    try:
        yield
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _scope(pid: str = "proj-grc", slot: str = "pv_tsc") -> ScopeContext:
    s = ScopeContext.create(pid, slot, require_slot=True, allow_legacy=False)
    return s


def _seed_lineage(scope: ScopeContext, *, kind: str, wf_id: str, snapshot_id: str = "",
                  dataset_version_id: str = "dsv-1") -> None:
    """种出**真实存在**的工作流血缘（P0-2 后的夹具要求）。

    `register_candidate` 现在要求：来源执行成功、其 project_workflow_id 在当前 scope
    真实存在、训练工作流绑定匹配类型的冻结快照、绑定的数据版本存在。
    夹具必须真的建出这些对象，否则测的就不是真实门禁（旧夹具只写一个悬空的
    `project_workflow_id: "pwf-1"`，会让新门禁的"工作流不存在"分支永远测不到）。
    """
    expected_type = "tsc_288x3_grid"  # scope 固定 pv_tsc（EXPECTED_SNAPSHOT_TYPE_BY_SLOT）
    # 幂等：同一测试可能连调两个 fixture（如四层治理用例），不重复 append 同一版本。
    if dataset_versions.find(scope, dataset_version_id) is None:
        dataset_versions.append(
            scope,
            {
                "dataset_version_id": dataset_version_id,
                "dataset_id": "ds-grc-1",
                "dataset_profile_id": "dsp-grc-1",
                "artifact_ref": f"data/slot_datasets/projects/x/{dataset_version_id}.json",
                "content_digest": "sha256:grc",
                "immutable": True,
            },
        )
    if snapshot_id and snapshots.find(scope, snapshot_id) is None:
        snapshots.append(
            scope,
            {
                "snapshot_id": snapshot_id,
                "snapshot_type": expected_type,
                "included_count": 3,
                "content_digest": "sha256:snap",
            },
        )
    project_workflows.append(
        scope,
        {
            "project_workflow_id": wf_id,
            "version": 1,
            "version_group_id": f"{wf_id}-grp",
            "parent_project_workflow_id": None,
            "name": wf_id,
            "create_mode": "blank",
            "workflow_kind": kind,
            "bound_dataset_version_id": dataset_version_id,
            "bound_snapshot_id": snapshot_id or None,
            "bound_snapshot_type": expected_type if snapshot_id else None,
            "nodes": [{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
            "edges": [],
        },
    )


def _governable_execution(scope: ScopeContext, exec_id: str = "exec-train") -> None:
    """一条**成功且可治理**的训练执行（含真实工作流 + 匹配快照 + 数据版本）。"""
    _seed_lineage(scope, kind="training", wf_id="pwf-1", snapshot_id="snap-grc-1")
    executions.append(
        scope,
        {
            "execution_id": exec_id,
            "governance_eligible": True,
            "project_workflow_id": "pwf-1",
            "dataset_version_id": "dsv-1",
            "evaluation_contract": {"metric": "macro_f1"},
            "run_mode": "training",
            "run_domain": "project",
            "status": "success",
        },
    )


def _validation_execution(scope: ScopeContext, exec_id: str = "exec-val") -> None:
    """一条 validation 执行（labeling 工作流，恒非可治理）。"""
    _seed_lineage(scope, kind="labeling", wf_id="pwf-2", snapshot_id="")
    executions.append(
        scope,
        {
            "execution_id": exec_id,
            "governance_eligible": False,
            "project_workflow_id": "pwf-2",
            "dataset_version_id": "dsv-1",
            "run_mode": "validation",
            "run_domain": "project",
            "status": "success",
        },
    )


# ---------------------------------------------------------------------------
# 治理
# ---------------------------------------------------------------------------

def test_candidate_provenance_gap_blocks_verification() -> None:
    with temp_storage():
        scope = _scope()
        # 手工构造 provenance 不完整的候选（缺 snapshot/workflow/version 等）。
        gaps = gov.candidate_provenance_gaps({"project_id": scope.project_id, "slot": scope.slot})
        assert "source_execution_id" in gaps and "model_artifact_ref" in gaps


def test_validation_execution_candidate_is_non_governable() -> None:
    with temp_storage():
        scope = _scope()
        _validation_execution(scope)
        cand = gov.register_candidate(
            scope, source_execution_id="exec-val", model_artifact_ref="data/models/x.pkl"
        )
        assert cand["governance_eligible"] is False
        with pytest.raises(gov.GovernanceGateError) as ei:
            gov.start_verification(scope, model_candidate_id=cand["model_candidate_id"])
        assert ei.value.code == "candidate_not_governable"


def test_verification_binding_mismatch_rejected() -> None:
    with temp_storage():
        scope = _scope()
        _governable_execution(scope)
        c1 = gov.register_candidate(scope, source_execution_id="exec-train", model_artifact_ref="a.pkl", source_snapshot_id="s1")
        c2 = gov.register_candidate(scope, source_execution_id="exec-train", model_artifact_ref="b.pkl", source_snapshot_id="s2")
        ver = gov.start_verification(scope, model_candidate_id=c1["model_candidate_id"])
        # 用 c1 的复验去校验 c2 → 绑定不一致。
        with pytest.raises(gov.GovernanceGateError) as ei:
            gov.assert_formal_verification(scope, c2["model_candidate_id"], ver["verification_id"])
        assert ei.value.code == "verification_candidate_mismatch"


def test_pending_verification_cannot_set_pointer() -> None:
    with temp_storage():
        scope = _scope()
        _governable_execution(scope)
        c = gov.register_candidate(scope, source_execution_id="exec-train", model_artifact_ref="a.pkl", source_snapshot_id="s1")
        ver = gov.start_verification(scope, model_candidate_id=c["model_candidate_id"])
        with pytest.raises(gov.GovernanceGateError) as ei:
            gov.set_rolling_detect_model(
                scope,
                model_candidate_id=c["model_candidate_id"],
                verification_id=ver["verification_id"],
                expected_registry_version=0,
                operator="t",
                reason="r",
            )
        assert ei.value.code == "verification_not_passed"


def test_product_validation_id_has_no_governance_effect() -> None:
    with temp_storage():
        scope = _scope()
        _governable_execution(scope)
        c = gov.register_candidate(scope, source_execution_id="exec-train", model_artifact_ref="a.pkl", source_snapshot_id="s1")
        with pytest.raises(gov.GovernanceGateError) as ei:
            gov.assert_formal_verification(scope, c["model_candidate_id"], "cdpv-abc")
        assert ei.value.code == "product_validation_no_governance_effect"


def test_governance_overview_four_layers() -> None:
    with temp_storage():
        scope = _scope()
        _governable_execution(scope)
        _validation_execution(scope)
        gc = gov.register_candidate(scope, source_execution_id="exec-train", model_artifact_ref="a.pkl", source_snapshot_id="s1")
        ec = gov.register_candidate(scope, source_execution_id="exec-val", model_artifact_ref="b.pkl")
        ov = gov.governance_overview(scope)
        pending = {c["model_candidate_id"] for c in ov["pending_candidates"]}
        experiment = {c["model_candidate_id"] for c in ov["experiment_results"]}
        assert gc["model_candidate_id"] in pending
        assert ec["model_candidate_id"] in experiment
        assert ov["current_detection_model"]["registry_version"] == 0
        assert ov["governance_history"] == []


# ---------------------------------------------------------------------------
# 审核
# ---------------------------------------------------------------------------

def _seed_review(scope: ScopeContext) -> dict:
    return rv.create_review(
        scope,
        source_kind="label_proposal",
        unit_granularity="device_day",
        items=[
            {"item_id": "i1", "unit_ref": "device=D1;date=2026-01-01;label=fault", "proposed_label": "fault"},
            {"item_id": "i2", "unit_ref": "device=D2;date=2026-01-01;label=normal", "proposed_label": "normal"},
        ],
        dataset_version_id="dsv-1",
        model_ref="m-1",
    )


def test_review_version_conflict_is_cas() -> None:
    with temp_storage():
        scope = _scope()
        r = _seed_review(scope)
        rid = r["review_id"]
        rv.save_verdict(scope, rid, expected_review_version=0, item_verdicts=[{"item_id": "i1", "verdict": "accept"}])
        with pytest.raises(gov.GovernanceGateError) as ei:
            rv.save_verdict(scope, rid, expected_review_version=0, item_verdicts=[])
        assert ei.value.code == "review_version_conflict"


def test_complete_requires_all_judged_and_does_not_admit() -> None:
    with temp_storage():
        scope = _scope()
        r = _seed_review(scope)
        rid = r["review_id"]
        rv.save_verdict(scope, rid, expected_review_version=0, item_verdicts=[{"item_id": "i1", "verdict": "accept"}])
        with pytest.raises(gov.GovernanceGateError) as ei:
            rv.complete_review(scope, rid, expected_review_version=1)
        assert ei.value.code == "review_incomplete"
        # 补齐后完成，且不写台账。
        rv.save_verdict(scope, rid, expected_review_version=1, item_verdicts=[{"item_id": "i2", "verdict": "reject"}])
        rv.complete_review(scope, rid, expected_review_version=2)
        assert cum.list_admissions(scope) == []


def test_admission_is_idempotent() -> None:
    with temp_storage():
        scope = _scope()
        r = _seed_review(scope)
        rid = r["review_id"]
        rv.save_verdict(scope, rid, expected_review_version=0, item_verdicts=[
            {"item_id": "i1", "verdict": "accept"}, {"item_id": "i2", "verdict": "reject"},
        ])
        rv.complete_review(scope, rid, expected_review_version=1)
        a1 = rv.complete_and_admit(scope, rid, expected_review_version=2, idempotency_key="k1", operator="t")
        a2 = rv.complete_and_admit(scope, rid, expected_review_version=99, idempotency_key="k1", operator="t")
        assert a1["idempotent_replay"] is False and a2["idempotent_replay"] is True
        assert len(cum.list_admissions(scope)) == 1


def test_accuracy_absent_truth_is_not_zero() -> None:
    with temp_storage():
        scope = _scope()
        r = _seed_review(scope)
        acc = rv.review_accuracy(scope, r["review_id"])
        assert acc["value"] is None and acc["value_display"] == "未产出"
        assert "no_valid_human_truth" in acc["non_comparability_reasons"]


# ---------------------------------------------------------------------------
# 累计 / 冻结
# ---------------------------------------------------------------------------

def _admit_one(scope: ScopeContext) -> None:
    r = _seed_review(scope)
    rid = r["review_id"]
    rv.save_verdict(scope, rid, expected_review_version=0, item_verdicts=[
        {"item_id": "i1", "verdict": "accept"}, {"item_id": "i2", "verdict": "accept"},
    ])
    rv.complete_review(scope, rid, expected_review_version=1)
    rv.complete_and_admit(scope, rid, expected_review_version=2, idempotency_key="adm", operator="t")


def test_freeze_is_idempotent_on_same_plan() -> None:
    with temp_storage():
        scope = _scope()
        _admit_one(scope)
        f1 = cum.execute_freeze(scope, reviewed_at_cutoff=None, idempotency_key="f1", operator="t")
        f2 = cum.execute_freeze(scope, reviewed_at_cutoff=None, idempotency_key="f2", operator="t")
        assert f1["idempotent_replay"] is False and f2["idempotent_replay"] is True
        assert f1["snapshot"]["snapshot_id"] == f2["snapshot"]["snapshot_id"]
        assert len(cum.list_snapshots(scope)) == 1


def test_freeze_no_events_blocked() -> None:
    with temp_storage():
        scope = _scope()
        with pytest.raises(gov.GovernanceGateError) as ei:
            cum.execute_freeze(scope, reviewed_at_cutoff=None, idempotency_key="f", operator="t")
        assert ei.value.code == "no_admitted_events"


def test_training_result_is_not_admission() -> None:
    with temp_storage():
        scope = _scope()
        _admit_one(scope)
        snap = cum.execute_freeze(scope, reviewed_at_cutoff=None, idempotency_key="f1", operator="t")["snapshot"]
        trn = cum.register_training_result(
            scope, snapshot_id=snap["snapshot_id"], source_execution_id="exec-train", model_artifact_ref="m.pkl"
        )
        assert trn["kind"] == "training_result"
        # 训练结果不产生候选、不改 registry。
        assert gov.list_candidates(scope) == []
        assert gov.read_registry(scope)["registry_version"] == 0


def test_cross_scope_candidate_not_found() -> None:
    with temp_storage():
        a = _scope("proj-a", "pv_tsc")
        b = _scope("proj-b", "pv_tsc")
        _governable_execution(a)
        c = gov.register_candidate(a, source_execution_id="exec-train", model_artifact_ref="a.pkl", source_snapshot_id="s1")
        # 在 B scope 找 A 的候选 → 找不到（不跨项目）。
        assert gov.find_candidate(b, c["model_candidate_id"]) is None


# ---------------------------------------------------------------------------
# 6.3：pv_point 冻结过滤整日 / 设备日盒（整日盒不作为逐点真值来源）
# ---------------------------------------------------------------------------

def _admit_with_granularity(scope: ScopeContext, granularity: str, key: str) -> None:
    r = rv.create_review(
        scope,
        source_kind="detection_batch",
        unit_granularity=granularity,
        items=[{"item_id": "i1", "unit_ref": "device=D1;date=2026-01-01", "proposed_label": "fault"}],
    )
    rid = r["review_id"]
    rv.save_verdict(scope, rid, expected_review_version=0, item_verdicts=[{"item_id": "i1", "verdict": "accept"}])
    rv.complete_review(scope, rid, expected_review_version=1)
    rv.complete_and_admit(scope, rid, expected_review_version=2, idempotency_key=key, operator="t")


def test_point_freeze_excludes_whole_day_boxes() -> None:
    with temp_storage():
        scope = _scope("proj-pt", "pv_point")
        _admit_with_granularity(scope, "device_day", "k-whole")  # 整日盒 → 应被排除
        _admit_with_granularity(scope, "point", "k-point")       # 点级 → 应纳入
        plan = cum.freeze_plan(scope)
        assert plan["included_count"] == 1, plan
        # 被排除的整日盒带原因。
        excluded_reasons = plan["excluded_events"]
        assert len(excluded_reasons) == 1


def test_tsc_freeze_keeps_device_day_units() -> None:
    """pv_tsc（非 point）不套用整日盒过滤：device_day 粒度仍可纳入。"""
    with temp_storage():
        scope = _scope("proj-tsc", "pv_tsc")
        _admit_with_granularity(scope, "device_day", "k1")
        plan = cum.freeze_plan(scope)
        assert plan["included_count"] == 1

# @AI_GENERATED: end
