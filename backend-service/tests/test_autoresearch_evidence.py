from services.autoresearch_evidence import AutoResearchEvidenceBuilder


def test_single_window_positive_requires_confirmation():
    evidence = AutoResearchEvidenceBuilder().build_for_group(
        run_id="ares-test",
        group={
            "iteration": 3,
            "group_idx": 1,
            "target_direction": "feature",
            "target_layer": "feature",
            "status": "success",
            "windows_total": 1,
            "windows_done": 1,
            "mape_improvement": 0.12,
            "override": {"train_days": 45},
        },
    )

    assert evidence.evidence_strength == "single_window_positive"
    assert evidence.needs_multi_window_confirmation is True
    assert evidence.changed_variables == ["train_days"]


def test_multi_window_positive_is_confirmed():
    evidence = AutoResearchEvidenceBuilder().build_for_group(
        run_id="ares-test",
        group={
            "iteration": 4,
            "group_idx": 2,
            "target_direction": "model",
            "target_layer": "model",
            "status": "success",
            "windows_total": 3,
            "windows_done": 3,
            "mape_improvement": 0.5,
        },
    )

    assert evidence.evidence_strength == "multi_window_confirmed"
    assert evidence.needs_multi_window_confirmation is False


def test_failed_group_still_has_evidence_record():
    evidence = AutoResearchEvidenceBuilder().build_for_group(
        run_id="ares-test",
        group={
            "iteration": 5,
            "group_idx": 0,
            "target_direction": "risk",
            "target_layer": "model",
            "status": "failed",
            "error": "batch_eval_timeout",
        },
    )

    assert evidence.status == "failed"
    assert evidence.failure_reason == "batch_eval_timeout"
    assert evidence.evidence_strength == "insufficient_evidence"


def test_evidence_summary_counts_strength_and_direction():
    builder = AutoResearchEvidenceBuilder()
    rows = [
        builder.build_for_group(run_id="r", group={"target_direction": "feature", "status": "success", "windows_total": 1, "windows_done": 1, "mape_improvement": 1}).to_dict(),
        builder.build_for_group(run_id="r", group={"target_direction": "model", "status": "success", "windows_total": 2, "windows_done": 2, "mape_improvement": -1}).to_dict(),
    ]

    summary = builder.summarize(rows)

    assert summary["total"] == 2
    assert summary["by_strength"]["single_window_positive"] == 1
    assert summary["by_strength"]["multi_window_rejected"] == 1
    assert summary["needs_multi_window_confirmation"] == 1
