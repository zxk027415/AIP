"""Gold mock accuracy must compare real predictions to gold, not copy gold as predicted."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_accuracy_from_pairs_counts_mismatch():
    from services.slot_datasets.mock_gold_scoring import accuracy_from_pairs

    snap = accuracy_from_pairs([(1, 1), (2, 0), (0, 0), (3, 1)])
    assert snap["counted_units"] == 4
    assert snap["classifier_accuracy"] == pytest.approx(0.5)


def test_join_predictions_with_gold_uses_batch_pred_not_gold_label(tmp_path, monkeypatch):
    from services.slot_datasets import mock_gold_scoring as scoring

    backend = tmp_path / "backend-service"
    batch_dir = backend / "data" / "iterative_labeling" / "prediction_batches" / "pv_point"
    batch_dir.mkdir(parents=True)
    monkeypatch.setattr(scoring, "_BACKEND_DIR", backend)
    gold = pd.DataFrame(
        {
            "site_id": ["s1", "s1"],
            "device_id": ["d1", "d1"],
            "branch_id": ["1", "1"],
            "time": pd.to_datetime(["2021-08-24T00:00:00+00:00", "2021-08-24T00:10:00+00:00"], utc=True),
            "label": [0, 9],
            "value": [1.0, 2.0],
        }
    )
    (batch_dir / "pb-test.json").write_text(
        json.dumps(
            {
                "prediction_batch_id": "pb-test",
                "units": [
                    {
                        "site_id": "s1",
                        "device_id": "d1",
                        "branch_id": "1",
                        "time_window": "2021-08-24T00:00:00+00:00",
                        "predicted_label": 7,
                    },
                    {
                        "site_id": "s1",
                        "device_id": "d1",
                        "branch_id": "1",
                        "time": "2021-08-24T00:10:00+00:00",
                        "predicted_label": 9,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    hits = scoring.join_predictions_with_gold("pv_point", gold, max_units=8)
    assert len(hits) == 2
    by_key = {item["unit_key"]: item for item in hits}
    first = [item for item in hits if item["gold_label"] == 0][0]
    assert first["predicted_label"] == 7
    assert first["predicted_label"] != first["gold_label"]
    second = [item for item in hits if item["gold_label"] == 9][0]
    assert second["predicted_label"] == 9
    assert by_key  # keys populated


def test_mock_gold_review_writes_confirm_and_correct(tmp_path, monkeypatch):
    from services.slot_datasets import mock_gold_review as mgr
    from services.slot_datasets import mock_gold_scoring as scoring

    backend = tmp_path / "backend-service"
    gold_rel = "data/slot_datasets/pv_point/gold/g.parquet"
    gold_path = backend / gold_rel
    gold_path.parent.mkdir(parents=True)
    review_root = backend / "data" / "iterative_labeling"
    review_root.mkdir(parents=True)
    batch_dir = review_root / "prediction_batches" / "pv_point"
    batch_dir.mkdir(parents=True)
    times = pd.to_datetime(
        [f"2021-08-24T00:{i:02d}:00+00:00" for i in range(0, 50, 10)],
        utc=True,
    )
    gold = pd.DataFrame(
        {
            "site_id": ["s1"] * 5,
            "device_id": ["d1"] * 5,
            "branch_id": ["1"] * 5,
            "time": times,
            "label": [0, 0, 9, 9, 1],
            "value": [1.0, 1.0, 2.0, 2.0, 3.0],
        }
    )
    gold.to_parquet(gold_path, index=False)
    units = []
    preds = [7, 0, 9, 2, 1]
    for stamp, pred in zip(times, preds):
        units.append(
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "1",
                "time_window": stamp.isoformat(),
                "predicted_label": pred,
                "confidence": 0.4,
            }
        )
    (batch_dir / "pb-join.json").write_text(json.dumps({"prediction_batch_id": "pb-join", "units": units}), encoding="utf-8")

    monkeypatch.setattr(mgr, "_BACKEND_DIR", backend)
    monkeypatch.setattr(mgr, "_GOLD", {"pv_point": gold_rel, "pv_day": gold_rel})
    monkeypatch.setattr(scoring, "_BACKEND_DIR", backend)
    monkeypatch.setenv("ITERATIVE_LABELING_DATA_ROOT", str(review_root))
    monkeypatch.setattr(
        mgr,
        "resolve_role_models",
        lambda _slot: [{"role": "production", "model_candidate_id": "mc-prod", "model_artifact_ref": "data/models/x.pkl"}],
    )
    monkeypatch.setattr(
        mgr,
        "complete_review_session_and_admit",
        lambda **_kwargs: {"completed": True, "source": "daily_review", "row_count": 5},
    )

    result = mgr.run_mock_gold_review("pv_point", max_units=5)
    assert result["origin"] == "detection_join"
    assert result["accuracy"]["counted_units"] == 5
    assert result["accuracy"]["classifier_accuracy"] == pytest.approx(0.6)
    stored = json.loads((review_root / "review_results" / "pv_point" / f"{result['review_id']}.json").read_text(encoding="utf-8"))
    predicted = [int(item["predicted_label"]) for item in stored["units"]]
    truth = [int(item["final_label"]) for item in stored["units"]]
    assert predicted != truth
    assert 7 in predicted
    assert 0 in truth
    acc_file = backend / "data" / "slot_datasets" / "pv_point" / "mock_accuracy.json"
    payload = json.loads(acc_file.read_text(encoding="utf-8"))
    assert payload["by_model"]["mc-prod"]["counted_units"] == 5
    actions = {item["action_type"] for item in stored["verdicts"]}
    assert "confirm" in actions
    assert "correct" in actions
