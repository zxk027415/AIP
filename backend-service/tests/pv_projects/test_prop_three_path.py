# @AI_GENERATED
"""Property tests P-PATH-01 / P-TSC-01：三路径语义 + canonical/shortcut 分离（任务 7.6，必需）。

设计依据：design.md §29.1（P-PATH-01 / P-TSC-01）；requirements.md R4.1–R4.8、R5.1–R5.10、
R11.5–R11.7、R14.2–R14.5、R14.13、R14.18–R14.20。

不变量：
- P-PATH-01：三路径（pv_day / pv_point / pv_tsc）语义各自独立：
  - 日路径生产复用 quickval 预测工作流，无专用日级生产图；
  - 点路径逐点严格因果（P-POINT-01 覆盖），非日批；
  - TSC canonical 打标链路固定为 tsc_predict→emit_tsc_label_proposal；
  - 各槽 canonical 打标工作流互不相同、不串。
- P-TSC-01：canonical（workflow-pv-tsc-label-v1）与 shortcut（KMeans REST）严格分离：
  - shortcut.is_canonical == False；shortcut 的 preferred 指向 canonical，但两者不等同；
  - strict-10 / validation 证据恒非可治理；production_contract_valid 不代表精度 / 可治理。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

from hypothesis import given, settings
from hypothesis import strategies as st

from services.pv_projects import ScopeContext
from services.pv_projects import repositories as repo
from services.pv_projects import day_adapter as day
from services.pv_projects import tsc_adapter as tsc
from services.pv_projects.scope import PRODUCT_SLOTS


@contextmanager
def temp_storage() -> Iterator[None]:
    tmp = tempfile.mkdtemp(prefix="pvproj_path_")
    repo.set_storage_base(tmp)
    try:
        yield
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


_slots = st.sampled_from(list(PRODUCT_SLOTS))
_project_ids = st.from_regex(r"proj-[a-z0-9]{1,6}", fullmatch=True)


# ===========================================================================
# P-PATH-01：三路径语义独立
# ===========================================================================

def test_day_production_fact_is_quickval_not_dedicated_graph() -> None:
    with temp_storage():
        scope = ScopeContext.create("proj-d", "pv_day", require_slot=True)
        fact = day.day_production_fact(scope)
        assert fact["production_workflow_id"] == "workflow-pv-fault-diag-quickval-predict-v1"
        assert fact["dedicated_day_production_graph"] is False
        assert fact["production_strategy"] == "LegacyDayStrategy"


@settings(max_examples=30, deadline=None)
@given(pid=_project_ids)
def test_canonical_label_workflow_distinct_per_slot(pid: str) -> None:
    """三槽 canonical 打标工作流互不相同，且不串槽。"""
    with temp_storage():
        ids = {}
        for slot in PRODUCT_SLOTS:
            scope = ScopeContext.create(pid, slot, require_slot=True)
            entry = tsc.canonical_labeling_entry(scope)
            ids[slot] = entry["canonical_workflow_id"]
        assert ids["pv_day"] == "workflow-pv-day-label-v1"
        assert ids["pv_point"] == "workflow-pv-point-label-v1"
        assert ids["pv_tsc"] == "workflow-pv-tsc-label-v1"
        assert len(set(ids.values())) == 3  # 三者互不相同


def test_tsc_canonical_lineage_fixed() -> None:
    with temp_storage():
        scope = ScopeContext.create("proj-t", "pv_tsc", require_slot=True)
        entry = tsc.canonical_labeling_entry(scope)
        assert entry["lineage"] == ["tsc_predict", "emit_tsc_label_proposal"]
        # 非 TSC 槽不套用该链路。
        day_scope = ScopeContext.create("proj-t", "pv_day", require_slot=True)
        assert tsc.canonical_labeling_entry(day_scope)["lineage"] == []


# ===========================================================================
# P-TSC-01：canonical vs shortcut 分离
# ===========================================================================

@settings(max_examples=30, deadline=None)
@given(pid=_project_ids, slot=_slots)
def test_shortcut_is_never_canonical(pid: str, slot: str) -> None:
    with temp_storage():
        scope = ScopeContext.create(pid, slot, require_slot=True)
        sc = tsc.shortcut_distinction(scope)
        assert sc["labeling_mode"] == "shortcut"
        assert sc["is_canonical"] is False
        # preferred 指向 canonical，但 shortcut 本身不等同 canonical。
        assert sc["preferred_labeling_workflow_id"] == tsc.CANONICAL_LABEL_WORKFLOW_BY_SLOT[slot]


def test_strict10_evidence_always_non_governable() -> None:
    with temp_storage():
        scope = ScopeContext.create("proj-t", "pv_tsc", require_slot=True, allow_legacy=False)
        # 即便合同完整、给了 macro_f1，证据仍非可治理。
        ev = tsc.register_strict10_evidence(
            scope,
            source_execution_id="exec-validation-d741dc207593",
            macro_f1=0.87,
            production_contract_valid=True,
        )
        assert ev["governance_eligible"] is False
        assert ev["production_contract_valid"] is True
        assert "精度" in ev["production_contract_note"]
        view = tsc.strict10_evidence_view(scope)
        assert view["all_validation_non_governable"] is True
        assert view["contract"]["splits"] == 10 and view["contract"]["grid"] == "288x3"


def test_strict10_missing_macro_f1_is_not_zero() -> None:
    with temp_storage():
        scope = ScopeContext.create("proj-t", "pv_tsc", require_slot=True, allow_legacy=False)
        ev = tsc.register_strict10_evidence(scope, source_execution_id="exec-v", macro_f1=None)
        assert ev["macro_f1"] is None
        assert ev["macro_f1_display"] == "未产出"


def test_tsc_production_observability_read_only() -> None:
    with temp_storage():
        scope = ScopeContext.create("proj-t", "pv_tsc", require_slot=True)
        status = tsc.tsc_production_status(scope)
        assert status["read_only"] is True
        assert status["has_current_receipt"] is False
        assert status["status_display"] == "未产出"
        assert status["cursor_advances_on_failed_day"] is False
        assert status["manual_advance_allowed"] is False


def test_manual_production_write_rejected() -> None:
    from services.pv_projects.governance import GovernanceGateError

    with temp_storage():
        scope = ScopeContext.create("proj-t", "pv_tsc", require_slot=True)
        try:
            tsc.assert_no_manual_production_write(scope, "advance_one_day")
            raise AssertionError("manual production write must be rejected")
        except GovernanceGateError as e:
            assert e.code == "tsc_production_observability_read_only"
            assert e.category == "read_only"


def test_tsc_candidate_gate_rejects_validation() -> None:
    from services.pv_projects.governance import GovernanceGateError

    with temp_storage():
        scope = ScopeContext.create("proj-t", "pv_tsc", require_slot=True)
        # validation 候选（governance_eligible=False）→ 拒绝。
        try:
            tsc.assert_tsc_candidate_governable(scope, {"governance_eligible": False})
            raise AssertionError("validation candidate must be rejected")
        except GovernanceGateError as e:
            assert e.code == "tsc_candidate_not_governable"
        # provenance 不完整 → 拒绝，且不合成字段。
        try:
            tsc.assert_tsc_candidate_governable(scope, {"governance_eligible": True})
            raise AssertionError("incomplete provenance must be rejected")
        except GovernanceGateError as e:
            assert e.code == "tsc_candidate_provenance_incomplete"

# @AI_GENERATED: end
