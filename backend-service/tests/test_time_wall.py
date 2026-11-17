"""Calendar-day time wall: last 20% labeled days are holdout."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.slot_datasets.time_wall import (
    MIN_HOLDOUT_UNITS,
    ensure_time_wall,
    rows_on_or_after_wall,
    unique_labeled_days,
    wall_from_days,
)


def test_wall_from_days_uses_last_20_percent():
    days = [f"2024-03-{i:02d}" for i in range(1, 11)]
    spec = wall_from_days(days, fraction=0.20)
    assert spec is not None
    assert spec["holdout_start_day"] == "2024-03-09"
    assert spec["holdout_end_day"] == "2024-03-10"
    assert spec["train_end_day"] == "2024-03-08"
    assert spec["holdout_day_count"] == 2


def test_ensure_time_wall_locks_and_does_not_recompute(tmp_path):
    gold = pd.DataFrame(
        {
            "time": pd.to_datetime([f"2024-01-{i:02d}" for i in range(1, 21)], utc=True),
            "label": [0] * 20,
        }
    )
    first = ensure_time_wall("pv_day", gold, backend_dir=tmp_path)
    assert first["holdout_start_day"] == "2024-01-17"
    shifted = gold.copy()
    shifted["time"] = pd.to_datetime([f"2025-01-{i:02d}" for i in range(1, 21)], utc=True)
    second = ensure_time_wall("pv_day", shifted, backend_dir=tmp_path)
    assert second["holdout_start_day"] == first["holdout_start_day"]


def test_mock_join_only_scores_holdout_days(tmp_path, monkeypatch):
    from services.slot_datasets import mock_gold_review as mgr
    from services.slot_datasets import mock_gold_scoring as scoring
    from services.slot_datasets import time_wall as tw

    backend = tmp_path / "backend-service"
    gold_rel = "data/slot_datasets/pv_point/gold/g.parquet"
    gold_path = backend / gold_rel
    gold_path.parent.mkdir(parents=True)
    review_root = backend / "data" / "iterative_labeling"
    batch_dir = review_root / "prediction_batches" / "pv_point"
    batch_dir.mkdir(parents=True)
    times = pd.to_datetime([f"2024-03-{i:02d}T00:00:00+00:00" for i in range(1, 21)], utc=True)
    gold = pd.DataFrame(
        {
            "site_id": ["s1"] * 20,
            "device_id": ["d1"] * 20,
            "branch_id": ["1"] * 20,
            "time": times,
            "label": [i % 3 for i in range(20)],
            "value": [1.0] * 20,
        }
    )
    gold.to_parquet(gold_path, index=False)
    units = []
    for stamp, idx in zip(times, range(20)):
        units.append(
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "1",
                "time_window": stamp.isoformat(),
                "predicted_label": idx % 3,
                "confidence": 0.5,
            }
        )
    (batch_dir / "pb-all.json").write_text(
        json.dumps({"prediction_batch_id": "pb-all", "units": units}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mgr, "_BACKEND_DIR", backend)
    monkeypatch.setattr(mgr, "_GOLD", {"pv_point": gold_rel, "pv_day": gold_rel})
    monkeypatch.setattr(scoring, "_BACKEND_DIR", backend)
    monkeypatch.setattr(tw, "_BACKEND_DIR", backend)
    monkeypatch.setenv("ITERATIVE_LABELING_DATA_ROOT", str(review_root))
    monkeypatch.setattr(
        mgr,
        "resolve_role_models",
        lambda _slot: [{"role": "production", "model_candidate_id": "mc-prod", "model_artifact_ref": "data/models/x.pkl"}],
    )
    monkeypatch.setattr(
        mgr,
        "complete_review_session_and_admit",
        lambda **_kwargs: {"completed": True, "source": "daily_review", "skipped": True, "reason": "holdout_only"},
    )

    result = mgr.run_mock_gold_review("pv_point", max_units=30)
    assert result["usable"] is True
    assert result["promote_eligible"] is False
    assert result["time_wall"]["holdout_start_day"] == "2024-03-17"
    days = {item["unit_key"].split("|")[-1][:10] for item in json.loads(
        (review_root / "review_results" / "pv_point" / f"{result['review_id']}.json").read_text(encoding="utf-8")
    )["units"]}
    assert min(days) >= "2024-03-17"
    assert "2024-03-01" not in days
    assert result["hit_count"] == 4


def test_mock_holdout_too_small_does_not_show_accuracy(tmp_path, monkeypatch):
    from services.slot_datasets import mock_gold_review as mgr
    from services.slot_datasets import mock_gold_scoring as scoring
    from services.slot_datasets import time_wall as tw

    backend = tmp_path / "backend-service"
    gold_rel = "data/slot_datasets/pv_point/gold/g.parquet"
    gold_path = backend / gold_rel
    gold_path.parent.mkdir(parents=True)
    gold = pd.DataFrame(
        {
            "site_id": ["s1", "s1", "s1"],
            "device_id": ["d1", "d1", "d1"],
            "branch_id": ["1", "1", "1"],
            "time": pd.to_datetime(["2024-03-01", "2024-03-02", "2024-03-03"], utc=True),
            "label": [0, 1, 2],
            "value": [1.0, 1.0, 1.0],
        }
    )
    gold.to_parquet(gold_path, index=False)
    monkeypatch.setattr(mgr, "_BACKEND_DIR", backend)
    monkeypatch.setattr(mgr, "_GOLD", {"pv_point": gold_rel, "pv_day": gold_rel})
    monkeypatch.setattr(scoring, "_BACKEND_DIR", backend)
    monkeypatch.setattr(tw, "_BACKEND_DIR", backend)

    result = mgr.run_mock_gold_review("pv_point", max_units=30)
    assert result["usable"] is False
    assert result["promote_eligible"] is False
    assert result["reason"] == "no_unseen_holdout"
    assert result["by_model"] == {}
    assert "review_id" not in result
    stored = json.loads((backend / "data/slot_datasets/pv_point/mock_accuracy.json").read_text(encoding="utf-8"))
    assert stored["empty"] is True
    assert unique_labeled_days(gold) == ["2024-03-01", "2024-03-02", "2024-03-03"]
    holdout = rows_on_or_after_wall(gold, result["time_wall"]["holdout_start_day"])
    assert len(holdout) < MIN_HOLDOUT_UNITS
