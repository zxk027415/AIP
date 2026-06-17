from services.autoresearch_multifidelity_scheduler import AutoResearchMultiFidelityScheduler


def test_scheduler_disabled_for_single_batch_or_single_window():
    scheduler = AutoResearchMultiFidelityScheduler()

    assert scheduler.enabled({"multi_fidelity_enabled": True}, 1, [{"a": 1}, {"a": 2}]) is False
    assert scheduler.enabled({"multi_fidelity_enabled": True}, 3, [{"a": 1}]) is False
    assert scheduler.enabled({}, 3, [{"a": 1}, {"a": 2}]) is False


def test_initial_windows_respects_fraction_and_minimum():
    scheduler = AutoResearchMultiFidelityScheduler()
    windows = [{"idx": i} for i in range(6)]

    selected = scheduler.initial_windows(windows, min_windows=2, fraction=0.34)

    assert selected == windows[:3]


def test_select_promotions_keeps_top_successful_rows():
    scheduler = AutoResearchMultiFidelityScheduler()
    rows = [
        {"group_idx": 0, "state": {"status": "success", "summary": {"score_advantage": 0.1}}},
        {"group_idx": 1, "state": {"status": "success", "summary": {"score_advantage": 0.4}}},
        {"group_idx": 2, "state": {"status": "failed", "summary": {"score_advantage": 9.0}}},
        {"group_idx": 3, "state": {"status": "success", "summary": {"score_advantage": 0.2}}},
    ]

    promoted = scheduler.select_promotions(rows, reduction_factor=2)

    assert promoted == [1, 3]


def test_mark_pruned_groups_preserves_promoted_and_failed():
    scheduler = AutoResearchMultiFidelityScheduler()
    rows = [
        {"group_idx": 0, "state": {"status": "success"}},
        {"group_idx": 1, "state": {"status": "success"}},
        {"group_idx": 2, "state": {"status": "failed"}},
    ]

    marked = scheduler.mark_pruned_groups(rows, [1])

    assert marked[0]["state"]["status"] == "pruned"
    assert marked[1]["state"]["status"] == "success"
    assert marked[2]["state"]["status"] == "failed"
