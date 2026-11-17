# -*- coding: utf-8 -*-
"""验证 pv_fault slot-overview 含累计训练摘要，供 StoryRail 消费。"""

from __future__ import annotations

import json

import services.iterative_labeling.pv_training_workspace as workspace_module
from services.iterative_labeling.orchestrator import LoopOrchestrator
from services.iterative_labeling.pv_training_workspace import PVTrainingWorkspaceService


def test_build_slot_overview_includes_cumulative_training_for_story_rail():
    overview = PVTrainingWorkspaceService().build_slot_overview("pv_fault")

    assert overview["domain"] == "pv_fault"
    assert "prediction_summary" in overview
    assert "review_progress" in overview
    assert "review_coverage_rate" in overview["review_progress"]
    assert "ground_truth_summary" in overview
    assert "cumulative_training" in overview

    cumulative = overview["cumulative_training"]
    assert "pending_change_count" in cumulative
    assert "retrain_label_threshold" in cumulative
    assert "next_retrain_in" in cumulative
    assert "latest_completed_model_ref" in cumulative
    assert isinstance(cumulative["pending_change_count"], int)
    assert isinstance(cumulative["retrain_label_threshold"], int)


def test_build_slot_overview_includes_prediction_batch_evidence():
    workspace = PVTrainingWorkspaceService()
    overview = workspace.build_slot_overview("pv_fault")

    assert "prediction_batches" in overview
    assert isinstance(overview["prediction_batches"], list)

    if overview["prediction_summary"]["total_batches"] > 0:
        latest = overview["latest_prediction_detail"]
        assert latest is not None
        assert latest.get("batch_id")
        assert "created_at" in latest
        assert "time_window_min" in latest
        assert "time_window_max" in latest
        assert "sample_predictions" in latest
        assert "label_distribution" in latest

        batches = workspace.list_prediction_batches("pv_fault")
        assert batches
        assert "time_window_min" in batches[0]
        assert "prediction_count" in batches[0]

    quality = overview.get("quality_metrics")
    if quality and quality.get("counted_units", 0) > 0:
        matrix = quality.get("confusion_matrix")
        assert matrix is not None
        assert len(matrix["labels"]) == len(matrix["label_names"])
        assert len(matrix["matrix"]) == len(matrix["labels"])
        assert all(len(row) == len(matrix["labels"]) for row in matrix["matrix"])


def test_prediction_batch_detail_contains_review_quality_metrics(tmp_path, monkeypatch):
    backend_dir = tmp_path / "backend-service"
    batch_dir = backend_dir / "data" / "iterative_labeling" / "prediction_batches" / "pv_fault"
    review_dir = backend_dir / "data" / "iterative_labeling" / "review_results" / "pv_fault"
    batch_dir.mkdir(parents=True)
    review_dir.mkdir(parents=True)
    monkeypatch.setattr(workspace_module, "_BACKEND_SERVICE_DIR", backend_dir)

    (batch_dir / "pred-batch-a.json").write_text(
        json.dumps(
            {
                "model_ref": "model-a",
                "predictions": [
                    {"predicted_label": 0, "confidence": 0.9},
                    {"predicted_label": 1, "confidence": 0.8},
                    {"predicted_label": 1, "confidence": 0.7},
                ],
            }
        ),
        encoding="utf-8",
    )
    units = [
        {
            "classifier_prediction": {"predicted_label": predicted},
            "current_verdict": {"action_type": "confirm", "verdict_label": actual},
        }
        for predicted, actual in [(0, 0), (1, 1), (1, 0)]
    ]
    (review_dir / "review-a.json").write_text(
        json.dumps({"prediction_batch_id": "pred-batch-a", "units": units}),
        encoding="utf-8",
    )
    (review_dir / "review-other.json").write_text(
        json.dumps(
            {
                "prediction_batch_id": "pred-batch-b",
                "units": [
                    {
                        "classifier_prediction": {"predicted_label": 1},
                        "current_verdict": {"action_type": "confirm", "verdict_label": 1},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    workspace = PVTrainingWorkspaceService()
    monkeypatch.setattr(workspace, "_load_label_names", lambda slot: {0: "正常", 1: "故障"})
    detail = workspace.get_prediction_batch("pred-batch-a", "pv_fault")

    quality = detail["quality_metrics"]
    assert quality["counted_units"] == 3
    assert quality["accuracy"] == 0.6667
    assert quality["confusion_matrix"]["matrix"] == [[1, 1], [0, 1]]
    assert [item["label_name"] for item in quality["per_class_metrics"]] == ["正常", "故障"]
    assert detail["ground_truth_summary"] == {
        "has_ground_truth": True,
        "counted_units": 3,
        "pending_ground_truth_units": 0,
        "coverage_rate": 1.0,
    }


def test_normalize_accuracy_record_preserves_visualization_fields():
    metrics = LoopOrchestrator._normalize_accuracy_record(
        {
            "accuracy_mean": 0.88,
            "accuracy_std": 0.02,
            "macro_f1_mean": 0.81,
            "per_repeat_macro_f1": [0.8, 0.82],
            "per_class_metrics": [{"label": "0", "precision": 0.9, "recall": 0.8, "f1": 0.85}],
            "confusion_matrix": {"labels": ["0"], "data": [[10]]},
            "n_samples": 100,
            "n_repeats": 2,
        }
    )

    assert metrics["accuracy_mean"] == 0.88
    assert metrics["per_repeat_macro_f1"] == [0.8, 0.82]
    assert metrics["per_class_metrics"][0]["f1"] == 0.85
    assert metrics["confusion_matrix"]["data"] == [[10]]
    assert metrics["n_samples"] == 100
