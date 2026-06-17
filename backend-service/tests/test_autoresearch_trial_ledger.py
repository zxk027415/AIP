import math

import pytest

from services.autoresearch_trial_ledger import AutoResearchTrialLedger
from services.autoresearch_persister import AutoResearchPersister
from api import workflows_enhanced as wf


def test_trial_ledger_appends_trials_and_decisions(tmp_path):
    ledger = AutoResearchTrialLedger(root_dir=str(tmp_path))

    trial = ledger.append_trial(
        "ares-ledger-1",
        {
            "iteration_no": 1,
            "status": "success",
            "mape_improvement": math.inf,
            "override": {"train_days": 45},
        },
    )
    decision = ledger.append_decision(
        "ares-ledger-1",
        {
            "decision_type": "proposal_applied",
            "actor": "system",
            "reason": "test",
        },
    )

    trials = ledger.list_trials("ares-ledger-1")
    decisions = ledger.list_decisions("ares-ledger-1")

    assert trial["id"] == "ares-ledger-1:trial-1"
    assert trial["mape_improvement"] is None
    assert decision["decision_type"] == "proposal_applied"
    assert trials[0]["override"]["train_days"] == 45
    assert decisions[0]["reason"] == "test"


def test_trial_ledger_stats_aggregate_trials(tmp_path):
    ledger = AutoResearchTrialLedger(root_dir=str(tmp_path))
    ledger.append_trial(
        "ares-ledger-stats",
        {"iteration_no": 1, "status": "success", "mape_improvement": 0.03, "override": {"train_days": 45}},
    )
    ledger.append_trial(
        "ares-ledger-stats",
        {"iteration_no": 2, "status": "failed", "mape_improvement": -0.01, "override": {"train_days": 60}},
    )
    ledger.append_decision("ares-ledger-stats", {"decision_type": "proposal_applied"})

    stats = ledger.stats()

    assert stats["total_trials"] == 2
    assert stats["success_trials"] == 1
    assert stats["failed_trials"] == 1
    assert stats["avg_mape_improvement"] == 0.01
    assert stats["decision_counts"]["proposal_applied"] == 1
    assert stats["top_params"][0]["param_key"] == "train_days"


@pytest.mark.asyncio
async def test_trial_ledger_endpoints_read_rows(tmp_path, monkeypatch):
    ledger = AutoResearchTrialLedger(root_dir=str(tmp_path))
    ledger.append_trial("ares-ledger-2", {"iteration_no": 2, "status": "failed"})
    ledger.append_decision("ares-ledger-2", {"decision_type": "cancel_requested"})
    monkeypatch.setattr(wf, "_auto_research_persister", AutoResearchPersister(trial_ledger=ledger))

    trial_result = await wf.list_auto_research_trials("ares-ledger-2")
    decision_result = await wf.list_auto_research_decisions("ares-ledger-2")
    stats_result = await wf.get_auto_research_stats()

    assert trial_result["total"] == 1
    assert trial_result["trials"][0]["status"] == "failed"
    assert decision_result["total"] == 1
    assert decision_result["decisions"][0]["decision_type"] == "cancel_requested"
    assert stats_result["total_trials"] == 1
