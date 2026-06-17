from services.autoresearch_memory_store import AutoResearchMemoryStore


def test_memory_store_append_load_and_retrieve(tmp_path):
    path = tmp_path / "memory.json"
    store = AutoResearchMemoryStore(str(path))
    case = {
        "case_id": "mem-1",
        "created_at": "2026-05-21T12:00:00",
        "baseline_workflow_id": "wf-base",
        "scenario_tags": ["industrial", "weekend"],
        "fingerprint": {
            "granularity": "daily",
            "load_type": "industrial",
            "seasonality": None,
            "weekend_sensitivity": "high",
            "backtest_mode": "rolling",
            "train_days": 30,
            "span_days": 20,
            "anomaly_ratio": 0.1,
        },
        "outcome": {
            "improved": True,
            "mape_delta": 1.2,
            "meets_constraints": True,
            "primary_error_source": "weekend_pattern_shift",
        },
    }

    store.append(case)
    rows = store.retrieve(
        "wf-base",
        ["industrial"],
        query_fingerprint={
            "granularity": "daily",
            "load_type": "industrial",
            "seasonality": None,
            "weekend_sensitivity": "high",
            "backtest_mode": "rolling",
            "train_days": 30,
            "span_days": 21,
            "anomaly_ratio": 0.1,
        },
        query_diagnosis="weekend_pattern_shift",
    )

    assert store.load()[0]["case_id"] == "mem-1"
    assert rows[0]["case_id"] == "mem-1"
    assert rows[0]["retrieval_score"] > 0
    assert rows[0]["fingerprint_similarity"] > 0.9


def test_compute_scenario_fingerprint_from_state_and_windows(tmp_path):
    store = AutoResearchMemoryStore(str(tmp_path / "memory.json"))
    fingerprint = store.compute_scenario_fingerprint(
        {
            "scenario_tags": ["industrial", "summer_peak", "weekend"],
            "evaluation_contract": {
                "daily_horizon": 1,
                "backtest_mode": "rolling",
                "train_days": 30,
            },
            "iterations": [
                {
                    "error_profile": {"high_error_days_count": 2},
                    "data_coverage": {"total_days": 10},
                }
            ],
        },
        windows=[
            {"start_date": "2026-05-01", "end_date": "2026-05-03"},
            {"start_date": "2026-05-10", "end_date": "2026-05-12"},
        ],
    )

    assert fingerprint["granularity"] == "daily"
    assert fingerprint["span_days"] == 12
    assert fingerprint["load_type"] == "industrial"
    assert fingerprint["seasonality"] == "summer_peak"
    assert fingerprint["weekend_sensitivity"] == "high"
    assert fingerprint["anomaly_ratio"] == 0.2
