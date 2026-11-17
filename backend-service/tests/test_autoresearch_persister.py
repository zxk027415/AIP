from services.autoresearch_persister import AutoResearchPersister


def test_persister_records_snapshot_trial_decision_and_stats(tmp_path):
    persister = AutoResearchPersister(root_dir=str(tmp_path))
    run_id = "ares-persister-1"

    persister.save_snapshot(run_id, {
        "run_id": run_id,
        "status": "running",
        "progress": {"iteration": 1, "total_iterations": 2},
    })
    persister.record_trial_from_candidate(run_id, {
        "iteration": 1,
        "status": "success",
        "override": {"train_days": 45},
        "evaluation": {
            "mape_improvement": 0.02,
            "score_advantage": 0.01,
            "challenger_mape": 0.05,
            "baseline_mape": 0.07,
        },
    })
    persister.record_decision(run_id, "proposal_applied", {"actor": "system"})

    loaded = persister.load_for_status(run_id, active_in_memory=True)
    trials = persister.list_trials(run_id)
    decisions = persister.list_decisions(run_id)
    stats = persister.stats()

    assert loaded["status"] == "running"
    assert trials[0]["mape_improvement"] == 0.02
    assert decisions[0]["decision_type"] == "proposal_applied"
    assert stats["total_trials"] == 1
    assert stats["top_params"][0]["param_key"] == "train_days"


def test_persister_list_runs_merges_memory_state(tmp_path):
    persister = AutoResearchPersister(root_dir=str(tmp_path))
    persister.save_snapshot("ares-persister-2", {"run_id": "ares-persister-2", "status": "running"})

    rows = persister.list_runs(
        limit=10,
        memory_store={"ares-persister-2": {"status": "success", "progress": {"iteration": 2}}},
    )

    assert rows[0]["run_id"] == "ares-persister-2"
    assert rows[0]["status"] == "success"
    assert rows[0]["snapshot_source"] == "memory+disk"

