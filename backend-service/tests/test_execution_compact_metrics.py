"""Compact execution payloads keep confusion matrices for slot dashboards."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.workflows_enhanced import _build_output_summary, _compact_execution_state


def test_output_summary_keeps_confusion_matrix_and_repeat_curve():
    summary = _build_output_summary(
        {
            "accuracy_mean": 0.98,
            "per_repeat_macro_f1": [0.9, 0.91, 0.92],
            "confusion_matrix": {"labels": ["0", "1"], "data": [[3, 1], [0, 4]]},
            "predictions": object(),
        }
    )
    assert summary["accuracy_mean"] == 0.98
    assert summary["per_repeat_macro_f1"] == [0.9, 0.91, 0.92]
    assert summary["confusion_matrix"]["data"] == [[3, 1], [0, 4]]
    assert summary["predictions"] == "object"


def test_compact_state_exposes_metrics_and_prediction_overview():
    compact = _compact_execution_state(
        {
            "execution_id": "exec-1",
            "workflow_id": "workflow-pv-day-predict-v1",
            "status": "success",
            "metrics": {
                "macro_f1_mean": 0.948,
                "confusion_matrix": {"labels": ["0"], "data": [[1]]},
            },
            "fault_predictions": [
                {"predictions": 0, "confidence": 0.9},
                {"predictions": 1, "confidence": 0.8},
                {"predictions": 0, "confidence": 0.7},
            ],
            "nodeResults": {
                "p9": {"status": "success", "outputSummary": {"model_id": "rfc"}, "executionTime": 0.1},
            },
        }
    )
    assert compact["metrics"]["macro_f1_mean"] == 0.948
    assert compact["prediction_overview"]["n_predicted"] == 3
    assert compact["prediction_overview"]["label_counts"] == {"0": 2, "1": 1}
    assert compact["nodeResults"]["p9"]["outputSummary"]["model_id"] == "rfc"
