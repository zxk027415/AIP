"""Integration test: pv_point.train_eval workflow execution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.workflows_enhanced import _execute_pipeline_sync, load_workflow_from_file


PV_CONTRACT = {
    "entity_keys": ["site_id", "device_id", "branch_id"],
    "time_column": "time",
    "feature_columns": ["value", "i_cal"],
    "label_column": "label",
}


def _labeled_point_parquet(path: Path) -> None:
    rows = []
    base = pd.Timestamp("2024-03-01T08:00:00Z")
    for device_idx, device_id in enumerate(["d1", "d2", "d3"]):
        t = base
        for i in range(14):
            rows.append(
                {
                    "site_id": "s1",
                    "device_id": device_id,
                    "branch_id": "b1",
                    "time": t.isoformat(),
                    "value": float(i + device_idx),
                    "i_cal": float(i) * 0.3,
                    "label": 0 if i < 10 else 1,
                }
            )
            t += pd.Timedelta(minutes=6 + i % 4)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_functions_json_lists_ts_point_operators():
    functions_path = Path(__file__).resolve().parents[1] / "data" / "functions.json"
    payload = json.loads(functions_path.read_text(encoding="utf-8"))
    ids = {item["id"] for item in payload.get("functions", [])}
    for op_id in [
        "ts_point_profile_map",
        "ts_point_validate_schema",
        "ts_point_label_join",
        "ts_point_causal_impute",
        "ts_point_temporal_split",
        "ts_point_causal_window",
        "ts_point_train_classifier",
        "ts_point_predict",
        "ts_point_metrics",
        "ts_point_candidate_intervals",
        "load_model_artifact",
    ]:
        assert op_id in ids, op_id


@pytest.mark.integration
def test_pv_point_train_eval_workflow_runs():
    backend = Path(__file__).resolve().parents[1]
    fixture_dir = backend / "data" / "timeseries_point" / "test_fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    data_path = fixture_dir / "labeled_points.parquet"
    _labeled_point_parquet(data_path)
    rel_path = f"data/timeseries_point/test_fixtures/{data_path.name}"

    workflow = load_workflow_from_file("workflow-pv-point-train-eval-v1")
    assert workflow is not None

    contract_json = json.dumps(PV_CONTRACT)
    for node in workflow.nodes:
        config = node.data.config
        cfg = config.dict() if hasattr(config, "dict") else dict(config)
        if cfg.get("functionId") == "load_csv":
            if hasattr(config, "file_path"):
                config.file_path = rel_path
            else:
                cfg["file_path"] = rel_path
        if cfg.get("functionId", "").startswith("ts_point_") and cfg.get("functionId") != "ts_point_profile_map":
            if hasattr(config, "contract"):
                config.contract = contract_json
        if cfg.get("functionId") == "ts_point_profile_map":
            if hasattr(config, "contract"):
                config.contract = contract_json

    result = _execute_pipeline_sync(workflow)
    assert result["success"] is True, result.get("error")
    train_node = (result.get("nodeResults") or {}).get("pp-train") or {}
    assert train_node.get("status") == "success"
    summary = train_node.get("outputSummary") or {}
    assert summary.get("model_path")
