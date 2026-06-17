from services.autoresearch_diagnostics import AutoResearchDiagnostics


def test_iteration_error_profile_aggregates_metrics_and_coverage():
    diagnostics = AutoResearchDiagnostics()
    profile = diagnostics.compute_iteration_error_profile([
        {
            "challenger": {
                "avg_metrics": {"avg_mape": 0.1, "avg_bias": 0.02},
                "success_days": 2,
                "failed_days": 1,
                "skipped_days": 0,
            },
            "challenger_score": 0.8,
            "baseline_score": 0.9,
        },
        {
            "challenger": {
                "avg_metrics": {"avg_mape": 0.2, "avg_bias": 0.0},
                "success_days": 3,
                "failed_days": 0,
                "skipped_days": 1,
            },
            "challenger_score": 0.95,
            "baseline_score": 0.9,
        },
    ])

    assert profile["error_profile"]["avg_mape"] == 0.15000000000000002
    assert profile["error_profile"]["max_daily_mape"] == 0.2
    assert profile["error_profile"]["bias_direction"] == "neutral"
    assert profile["error_profile"]["high_error_days_count"] == 1
    assert profile["data_coverage"]["total_days"] == 7
    assert profile["data_coverage"]["success_days"] == 5


def test_error_diagnosis_detects_model_divergence():
    diagnostics = AutoResearchDiagnostics()
    report = {
        "iterations": [
            {
                "status": "success",
                "comparison_id": "cmp-1",
                "error_profile": {"avg_mape": 0.1, "max_daily_mape": 0.12},
                "data_coverage": {"total_days": 14, "success_days": 12},
            }
        ]
    }
    comparison_store = {
        "cmp-1": {
            "per_model_metrics": {
                "xgb": {"avg_smape": 8.0},
                "lgbm": {"avg_smape": 12.5},
            }
        }
    }

    diagnosis = diagnostics.compute_error_diagnosis(report, comparison_store=comparison_store)

    assert diagnosis["primary_error_source"] == "model_divergence"
    assert diagnosis["evidence"]["model_divergence"] == 4.5


def test_error_diagnosis_detects_data_coverage():
    diagnostics = AutoResearchDiagnostics()
    report = {
        "iterations": [
            {
                "status": "success",
                "error_profile": {"avg_mape": 0.1, "max_daily_mape": 0.12},
                "data_coverage": {"total_days": 10, "success_days": 6},
            }
        ]
    }

    diagnosis = diagnostics.compute_error_diagnosis(report)

    assert diagnosis["primary_error_source"] == "data_coverage_insufficient"
