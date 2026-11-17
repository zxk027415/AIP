"""Loop demo: feed a day, auto-review against gold, never admit to cumulative."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def demo_env(tmp_path, monkeypatch):
    backend = tmp_path / "backend-service"
    import services.slot_datasets.loop_demo as demo
    import services.slot_datasets.observability_ledger as obs

    monkeypatch.setattr(demo, "_BACKEND_DIR", backend)
    monkeypatch.setattr(obs, "_BACKEND_DIR", backend)
    return backend


def test_feed_detect_review_does_not_admit(demo_env):
    from services.slot_datasets.loop_demo import ensure_loop_demo, load_daily_accuracy, run_next_demo_day

    ensure_loop_demo("pv_point")
    first = run_next_demo_day("pv_point", operator="test")
    assert first["fed_day"] == "2024-06-03"
    assert first["admitted"] is False
    assert first["review_id"].startswith("rev-loop-demo-")
    assert first["detected_units"] > 0
    acc = first["accuracy"]
    assert acc["counted_units"] == first["detected_units"]
    # 点路径一次只推进一个测点：单点精度只能取 0 或 1，不会是中间值。
    assert acc["classifier_accuracy"] in (0.0, 1.0)
    stored = load_daily_accuracy("pv_point")
    assert stored["latest"]["day"] == "2024-06-03"
    assert stored["latest"]["admitted"] is False
    from services.iterative_labeling.storage.file_backend import FileReviewResultRepository
    repo = FileReviewResultRepository()
    repo.data_root = demo_env / "data" / "iterative_labeling"
    saved = repo.load_session("pv_point", first["review_id"])
    unit = saved["units"][0]
    assert "classifier_prediction" in unit
    assert unit["classifier_prediction"]["predicted_label"] in {0, 1, 3}
    assert unit["current_verdict"]["action_type"] in {"confirm", "correct"}

    # 点路径按点推进（用户设计语义）：第二次仍在同一天前进一个点，不跨日、不计入 fed。
    second = run_next_demo_day("pv_point")
    assert second["fed_day"] == "2024-06-03"
    assert second["granularity"] == "point"
    assert second["day_finished"] is False
    assert second["cursor"]["day_index"] == 0


def test_seven_days_then_exhausted(demo_env):
    from services.slot_datasets.errors import SlotDatasetError
    from services.slot_datasets.loop_demo import DEMO_DAYS, ensure_loop_demo, run_next_demo_day

    ensure_loop_demo("pv_day")
    days = []
    for _ in range(DEMO_DAYS):
        days.append(run_next_demo_day("pv_day")["fed_day"])
    assert len(days) == 7
    with pytest.raises(SlotDatasetError) as exc:
        run_next_demo_day("pv_day")
    assert exc.value.code == "demo_exhausted"


def test_day_and_point_isolation(demo_env):
    from services.slot_datasets.loop_demo import ensure_loop_demo, run_next_demo_day

    ensure_loop_demo("pv_day")
    ensure_loop_demo("pv_point")
    day_run = run_next_demo_day("pv_day")
    point_run = run_next_demo_day("pv_point")
    assert day_run["fed_day"] == point_run["fed_day"]
    assert day_run["review_id"] != point_run["review_id"]
    assert "pv_day" in day_run["review_id"]
    assert "pv_point" in point_run["review_id"]


def test_unfed_calendar_uses_demo_week_not_watermark(demo_env):
    from services.slot_datasets.loop_demo import ensure_loop_demo
    from services.slot_datasets import observability_ledger as obs

    ensure_loop_demo("pv_point")
    start, end = obs.default_calendar_range("pv_point")
    assert start == "2024-06-03"
    assert end == "2024-06-09"
    body = obs.calendar_grid("pv_point")
    assert body["from"] == "2024-06-03"
    assert {row["device_id"] for row in body["rows"]} == {"inv_a", "inv_b", "inv_c"}
    assert all(cell["status"] == "empty" for row in body["rows"] for cell in row["cells"])


def test_outcomes_window_after_feed(demo_env):
    from services.slot_datasets.loop_demo import ensure_loop_demo, outcomes_for_window, run_next_demo_day

    ensure_loop_demo("pv_point")
    run_next_demo_day("pv_point")
    body = outcomes_for_window("pv_point", "2024-06-03", "2024-06-03")
    # 点路径一次推进只产生一个测点的 outcome（「按点推进」的设计语义）
    assert body["count"] == 1
    assert body["items"][0]["predicted_label"] in {0, 1, 3}
    empty = outcomes_for_window("pv_point", "2024-06-04", "2024-06-04")
    assert empty["count"] == 0


def test_pv_day_outcomes_have_intraday_curve(demo_env):
    from services.slot_datasets.loop_demo import POINTS_PER_DAY, ensure_loop_demo, outcomes_for_window, run_next_demo_day

    ensure_loop_demo("pv_day")
    first = run_next_demo_day("pv_day")
    assert first["detected_units"] == 3 * POINTS_PER_DAY
    body = outcomes_for_window("pv_day", "2024-06-03", "2024-06-03")
    assert body["count"] == 3 * POINTS_PER_DAY
    times = {str(item.get("time") or "") for item in body["items"]}
    assert len(times) > 1
    assert all(item.get("i_cal") is not None for item in body["items"])
    assert any(int(item.get("gold_label") or 0) != 0 for item in body["items"])
    daily = body["daily_units"]
    assert len(daily) == 3
    point_acc = sum(int(i["predicted_label"]) == int(i["gold_label"]) for i in body["items"]) / body["count"]
    day_acc = sum(int(i["predicted_label"]) == int(i["gold_label"]) for i in daily) / len(daily)
    assert first["accuracy"]["counted_units"] == 3
    assert abs(day_acc - point_acc) > 1e-9 or first["accuracy"]["counted_units"] != first["detected_units"]


def test_day0_has_consecutive_fault_for_alarm(demo_env):
    from services.slot_datasets.loop_demo import ensure_loop_demo, load_outcomes, run_next_demo_day

    # 告警连续性需要一天内的多点序列。点路径按点推进，单次只有 1 个点、
    # 构不成「连续」，故这里用日路径一次喂整天来验证该性质。
    ensure_loop_demo("pv_day")
    run_next_demo_day("pv_day")
    rows = [item for item in load_outcomes("pv_day") if item.get("device_id") == "inv_b"]
    rows.sort(key=lambda item: str(item.get("time") or ""))
    longest = current = 0
    for item in rows:
        if int(item.get("predicted_label") or 0) != 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    assert longest >= 3
    assert any(int(item.get("gold_label") or 0) == 1 for item in rows)


def test_legacy_review_units_normalize_for_ui():
    from services.iterative_labeling.review_session import normalize_review_units_for_ui

    session = {
        "review_id": "rev-x",
        "reviewer": "mock_gold",
        "verdicts": [{"unit_key": "a", "verdict_label": 1, "action_type": "correct"}],
        "units": [{
            "unit_key": "a",
            "predicted_label": 0,
            "confidence": 0.8,
            "final_label": 1,
            "site_id": "s",
            "device_id": "d",
            "date": "2024-06-03",
        }],
    }
    unit = normalize_review_units_for_ui(session)["units"][0]
    assert unit["classifier_prediction"]["predicted_label"] == 0
    assert unit["classifier_prediction"]["confidence"] == 0.8
    assert unit["current_verdict"]["action_type"] == "correct"
    assert unit["time_window"] == "2024-06-03"
    parsed = normalize_review_units_for_ui({
        "units": [{"unit_key": "demo_site|inv_b|1|2024-06-03T10:00:00+00:00", "predicted_label": 1, "confidence": 0.9}],
    })["units"][0]
    assert parsed["site_id"] == "demo_site"
    assert parsed["device_id"] == "inv_b"
    assert parsed["time_window"].startswith("2024-06-03")
