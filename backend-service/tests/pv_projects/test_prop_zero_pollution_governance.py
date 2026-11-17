# @AI_GENERATED
"""Property tests P-SANDBOX-01 / P-GOV-01 / P-GOV-02（任务 8.5，必需）。

设计依据：design.md §29.1；requirements.md R7.8–R7.12、R8.1–R8.9、R9.1–R9.10、R12.*、R15.11、R15.12。

不变量：
- P-SANDBOX-01（零污染）：跨数据集验证只读输入源，输入源哈希跑前 / 跑后一致；
  A 项目的验证批次不改变 B 项目存储（A/B scope 隔离）。
- P-GOV-01（非升级治理）：跨数据集 / 产品验证 ID（xdpv-/cdpv-）永远不能作为正式复验 verification_id；
  证据束 can_be_verification_evidence=False，governance_effect=none。
- P-GOV-02（非升级治理）：离线基准证据 governance_effect=none、只读、无 calibration_audit_id；
  validation execution 候选恒非可治理，不能设指针 / Promote。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from typing import Any, Iterator

from hypothesis import given, settings
from hypothesis import strategies as st

from services.pv_projects import ScopeContext, validation_batches
from services.pv_projects import repositories as repo
from services.pv_projects import governance as gov
from services.pv_projects.cross_dataset import (
    VALIDATION_ID_PREFIX,
    CrossDatasetValidationService,
    register_offline_benchmark_evidence,
)


@contextmanager
def temp_storage() -> Iterator[None]:
    tmp = tempfile.mkdtemp(prefix="pvproj_zp_")
    repo.set_storage_base(tmp)
    try:
        yield
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _scope(pid: str = "proj-xd") -> ScopeContext:
    return ScopeContext.create(pid, allow_legacy=False)


_dataset_lists = st.lists(
    st.builds(
        lambda k, v: {"dataset_key": f"ds-{k}", "source_ref": f"data/ext/{k}.parquet", "dataset_version_id": f"dsv-{v}", "content_digest": f"sha256:{v:064d}"},
        st.integers(min_value=0, max_value=50),
        st.integers(min_value=0, max_value=999),
    ),
    min_size=1,
    max_size=4,
    unique_by=lambda d: d["dataset_key"],
)


# ===========================================================================
# P-SANDBOX-01：零污染 + A/B 隔离
# ===========================================================================

@settings(max_examples=30, deadline=None)
@given(datasets=_dataset_lists)
def test_zero_pollution_input_hash_stable(datasets: list[dict[str, Any]]) -> None:
    with temp_storage():
        scope = _scope()
        batch = CrossDatasetValidationService.create_batch(scope, datasets=datasets)
        vid = batch["validation_id"]
        # 跑每个数据集结果（只读评测）。
        for ds in datasets:
            CrossDatasetValidationService.record_result(scope, vid, dataset_key=ds["dataset_key"], metrics={"macro_f1": 0.5})
        zp = CrossDatasetValidationService.verify_zero_pollution(scope, vid)
        assert zp["zero_pollution"] is True
        for check in zp["checks"]:
            assert check["unchanged"] is True
            assert check["baseline_hash"] == check["recomputed_hash"]


@settings(max_examples=20, deadline=None)
@given(datasets=_dataset_lists)
def test_ab_scope_isolation(datasets: list[dict[str, Any]]) -> None:
    """A 项目创建验证批次不影响 B 项目存储。"""
    with temp_storage():
        a = _scope("proj-a")
        b = _scope("proj-b")
        CrossDatasetValidationService.create_batch(a, datasets=datasets)
        assert len(validation_batches.list(a)) == 1
        assert validation_batches.list(b) == []  # B 不受影响


# ===========================================================================
# P-GOV-01：跨数据集 / 产品验证 ID 不能升级为治理证据
# ===========================================================================

@settings(max_examples=30, deadline=None)
@given(datasets=_dataset_lists)
def test_validation_id_uses_xdpv_prefix(datasets: list[dict[str, Any]]) -> None:
    with temp_storage():
        scope = _scope()
        batch = CrossDatasetValidationService.create_batch(scope, datasets=datasets)
        assert batch["validation_id"].startswith(VALIDATION_ID_PREFIX)
        assert batch["governance_effect"] == "none"


def test_product_validation_id_rejected_as_verification() -> None:
    """xdpv-/cdpv- 前缀的 ID 被 governance 拒绝作为正式复验。"""
    with temp_storage():
        gscope = ScopeContext.create("proj-g", "pv_tsc", require_slot=True, allow_legacy=False)
        for vid in (f"{VALIDATION_ID_PREFIX}abc123", "cdpv-deadbeef"):
            try:
                gov.assert_formal_verification(gscope, "cand-x", vid)
                raise AssertionError(f"{vid} must be rejected")
            except gov.GovernanceGateError as e:
                assert e.code == "product_validation_no_governance_effect"


def test_evidence_bundle_cannot_be_verification() -> None:
    with temp_storage():
        scope = _scope()
        batch = CrossDatasetValidationService.create_batch(
            scope, datasets=[{"dataset_key": "d1", "source_ref": "data/ext/d1.parquet"}]
        )
        vid = batch["validation_id"]
        CrossDatasetValidationService.record_result(scope, vid, dataset_key="d1", metrics={"macro_f1": 0.6}, dimension_findings={"migration": True})
        bundle = CrossDatasetValidationService.aggregate_evidence(scope, vid)
        assert bundle["governance_effect"] == "none"
        assert bundle["can_be_verification_evidence"] is False
        assert bundle["dimension_summary"]["migration"] == ["d1"]


# ===========================================================================
# P-GOV-02：离线基准证据 + validation 候选非升级
# ===========================================================================

def test_offline_benchmark_evidence_is_read_only_no_audit_id() -> None:
    with temp_storage():
        scope = _scope()
        ev = register_offline_benchmark_evidence(scope, benchmark_source="pvdaq", manifest_ref="data/benchmark_raw/pvdaq/reruns/.../run_manifest.json")
        assert ev["governance_effect"] == "none"
        assert ev["read_only"] is True
        assert ev["calibration_audit_id"] is None  # 无注册表，如实置空


def test_validation_execution_candidate_cannot_set_pointer() -> None:
    """来自 validation execution 的候选（governance_eligible=false）不能设滚动指针。"""
    from services.pv_projects import executions
    from services.pv_projects.stores import project_workflows

    with temp_storage():
        scope = ScopeContext.create("proj-g", "pv_tsc", require_slot=True, allow_legacy=False)
        # P0-2 后候选血缘必须可核验：执行要成功、其工作流要真实存在。
        # validation 的 run_mode 合同只允许 labeling 工作流。
        project_workflows.append(
            scope,
            {
                "project_workflow_id": "pwf-g-val",
                "version": 1,
                "version_group_id": "pwfg-g-val",
                "name": "打标",
                "create_mode": "blank",
                "workflow_kind": "labeling",
                "bound_dataset_version_id": None,
                "bound_snapshot_id": None,
                "nodes": [],
                "edges": [],
            },
        )
        executions.append(
            scope,
            {
                "execution_id": "exec-val",
                "governance_eligible": False,
                "project_workflow_id": "pwf-g-val",
                "run_mode": "validation",
                "run_domain": "project",
                "status": "success",
            },
        )
        cand = gov.register_candidate(scope, source_execution_id="exec-val", model_artifact_ref="m.pkl")
        assert cand["governance_eligible"] is False
        try:
            gov.set_rolling_detect_model(
                scope, model_candidate_id=cand["model_candidate_id"], verification_id="ver-x",
                expected_registry_version=0, operator="t", reason="r",
            )
            raise AssertionError("validation candidate must not set pointer")
        except gov.GovernanceGateError as e:
            assert e.code == "candidate_not_governable"

# @AI_GENERATED: end
