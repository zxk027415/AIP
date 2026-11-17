"""Tests for real-point timeseries core and ts_point operators."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from services.operator_execution.router import OperatorRouter, OperatorExecutionError
from services.timeseries_point.causal_impute import causal_impute_existing_rows
from services.timeseries_point.causal_window import build_causal_window_for_pending_point
from services.timeseries_point.label_join import join_point_labels
from services.timeseries_point.metrics import compute_point_metrics
from services.timeseries_point.predict import predict_point_outcome
from services.timeseries_point.temporal_split import temporal_entity_split
from services.timeseries_point.train_adapter import build_real_point_dataset, train_real_point_classifier
from services.timeseries_point.validate_schema import validate_point_schema


CONTRACT = {
    "entity_keys": ["entity_id"],
    "time_column": "event_time",
    "feature_columns": ["value", "i_cal"],
    "label_column": "label",
    "context_length": 8,
}


def _sample_df() -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2024-01-01T08:00:00Z")
    for entity in ["A", "B", "C"]:
        t = base
        for i in range(12):
            rows.append(
                {
                    "entity_id": entity,
                    "event_time": t.isoformat(),
                    "value": float(i + 1),
                    "i_cal": float(i) * 0.5,
                    "label": 0 if i < 8 else 1,
                }
            )
            t += pd.Timedelta(minutes=7 + i % 3)
    return pd.DataFrame(rows)


def test_entity_disjoint_split_puts_rare_label_in_train():
    """Rare class on the modulo-val entity must still land in train."""
    from services.timeseries_point.train_adapter import (
        _DEVICE_COLUMNS,
        _assign_entity_disjoint_splits,
        _map_entity_columns,
    )

    rows = []
    base = pd.Timestamp("2024-01-01T08:00:00Z")
    for entity, labels in [("A", [0]), ("B", [0, 8]), ("C", [0])]:
        t = base
        for i, label in enumerate(labels * 6):
            rows.append(
                {
                    "entity_id": entity,
                    "event_time": (t + pd.Timedelta(minutes=i)).isoformat(),
                    "value": float(i + 1),
                    "i_cal": float(i) * 0.5,
                    "label": label,
                }
            )
    mapped = _map_entity_columns(pd.DataFrame(rows), ["entity_id"])
    split_df = _assign_entity_disjoint_splits(
        mapped, label_column="label", time_column="event_time"
    )
    rare = split_df[split_df["label"] == 8]
    assert not rare.empty
    assert set(rare["_split"].unique()) <= {"train"}
    assert set(split_df["_split"].unique()) == {"train", "val", "test"}
    train_labels = set(
        int(value) for value in split_df.loc[split_df["_split"] == "train", "label"].unique()
    )
    assert 8 in train_labels
    for _, group in split_df.groupby(_DEVICE_COLUMNS, dropna=False):
        assert group["_split"].nunique() == 1


def test_rare_label_holders_all_go_to_train():
    from services.timeseries_point.train_adapter import (
        _assign_entity_disjoint_splits,
        _map_entity_columns,
    )

    rows = []
    base = pd.Timestamp("2024-01-01T08:00:00Z")
    for entity, labels in [("A", [0]), ("B", [0, 8]), ("C", [0]), ("D", [0, 8])]:
        t = base
        for i, label in enumerate(labels * 4):
            rows.append(
                {
                    "entity_id": entity,
                    "event_time": (t + pd.Timedelta(minutes=i)).isoformat(),
                    "value": float(i + 1),
                    "i_cal": float(i) * 0.5,
                    "label": label,
                }
            )
    mapped = _map_entity_columns(pd.DataFrame(rows), ["entity_id"])
    split_df = _assign_entity_disjoint_splits(
        mapped, label_column="label", time_column="event_time"
    )
    rare = split_df[split_df["label"] == 8]
    assert set(rare["_split"].unique()) == {"train"}
    assert set(split_df["_split"].unique()) == {"train", "val", "test"}



def test_validate_schema_rejects_duplicates():
    df = _sample_df()
    dup = pd.concat([df.iloc[[0]], df.iloc[[0]]], ignore_index=True)
    report = validate_point_schema(dup, CONTRACT)
    assert report["valid"] is False
    assert any(issue["code"] == "duplicate_entity_time" for issue in report["issues"])


def test_validate_operator_dedupes_duplicates_and_returns_data():
    from services.operator_backends.ts_point_validate_schema import execute as validate_execute

    df = _sample_df()
    mixed = df.copy()
    mixed.loc[0, "event_time"] = str(mixed.loc[0, "event_time"]).replace("T", " ").replace("+00:00", "")
    dup = pd.concat([mixed, df.iloc[[0]]], ignore_index=True)
    out = validate_execute({"contract": CONTRACT}, {"data": dup})
    assert out["valid"] is True
    assert isinstance(out["data"], pd.DataFrame)
    assert len(out["data"]) == len(df)
    assert out["report"].get("normalized") is True


def test_label_join_rejects_day_label_broadcast():
    df = _sample_df()
    labels = pd.DataFrame(
        [
            {
                "entity_id": "A",
                "event_time": df.iloc[0]["event_time"],
                "label": 99,
                "source": "day_label",
            }
        ]
    )
    joined, audit = join_point_labels(
        df,
        labels,
        entity_keys=["entity_id"],
        time_column="event_time",
    )
    assert audit["forbidden_sources_rejected"] == 1


def test_causal_impute_preserves_row_count():
    df = _sample_df()
    df.loc[0, "value"] = np.nan
    imputed, _ = causal_impute_existing_rows(
        df,
        entity_keys=["entity_id"],
        time_column="event_time",
        feature_columns=["value", "i_cal"],
    )
    assert len(imputed) == len(df)


def test_causal_window_not_ready_for_first_point():
    df = _sample_df()
    result = build_causal_window_for_pending_point(
        df,
        entity_keys=["entity_id"],
        time_column="event_time",
        feature_columns=["value", "i_cal"],
        pending_row_index=0,
        context_length=8,
    )
    assert result.status == "not_ready"


def test_causal_window_ready_and_causal():
    df = _sample_df()
    entity_a = df[df["entity_id"] == "A"].reset_index(drop=True)
    idx = 5
    ready = build_causal_window_for_pending_point(
        entity_a,
        entity_keys=["entity_id"],
        time_column="event_time",
        feature_columns=["value", "i_cal"],
        pending_row_index=idx,
        context_length=8,
    )
    assert ready.status == "ready"
    future = entity_a.copy()
    future.loc[6:, "value"] = 999.0
    again = build_causal_window_for_pending_point(
        future,
        entity_keys=["entity_id"],
        time_column="event_time",
        feature_columns=["value", "i_cal"],
        pending_row_index=idx,
        context_length=8,
    )
    np.testing.assert_array_equal(ready.window_tensor, again.window_tensor)


def test_temporal_split_entity_isolation():
    df = _sample_df()
    split_df, audit = temporal_entity_split(
        df,
        entity_keys=["entity_id"],
        time_column="event_time",
        train_ratio=0.6,
        val_ratio=0.2,
    )
    assert "_split" in split_df.columns
    assert audit["split_counts"]["train"] >= 2


def test_predict_uses_last_timestep_logits():
    from services.timeseries_point.contract import WindowResult

    window = WindowResult(
        status="ready",
        window_tensor=np.zeros((1, 8, 7), dtype=np.float32),
        context_length=8,
    )

    class _FakeLoaded:
        metadata = {"constructor_config": {"in_channels": 7}, "context_length": 8, "target_mode": "last_point"}
        class_index_to_label = (0, 1)

        def forward(self, raw_windows):
            import torch

            # [B, W, C] like CausalTCNRealtime
            return torch.zeros((1, 8, 2))

    outcome = predict_point_outcome(window, artifact_dir="ignored", artifact_loader=lambda *_a, **_k: _FakeLoaded())
    assert outcome.kind == "prediction"
    assert outcome.label in (0, 1)
    assert outcome.confidence is not None


def test_metrics_and_no_decision():
    outcomes = [
        {"kind": "prediction", "label": 1, "true_label": 1},
        {"kind": "no_decision", "reason": "insufficient_history"},
    ]
    metrics = compute_point_metrics(outcomes)
    assert metrics["prediction_count"] == 1
    assert metrics["no_decision_count"] == 1

    from services.timeseries_point.contract import WindowResult

    outcome = predict_point_outcome(WindowResult(status="not_ready", reason="insufficient_history"))
    assert outcome.kind == "no_decision"


def test_operator_router_discovers_ts_point_backends():
    router = OperatorRouter()
    backends_dir = str(Path(__file__).resolve().parents[1] / "services" / "operator_backends")
    router.auto_discover(backends_dir)
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
    ]:
        assert router.has_operator(op_id), op_id


def test_p1_operators_raise_disabled():
    router = OperatorRouter()
    backends_dir = str(Path(__file__).resolve().parents[1] / "services" / "operator_backends")
    router.auto_discover(backends_dir)
    for op_id in ["ts_point_cross_validate", "ts_point_persistence_alarm"]:
        with pytest.raises(OperatorExecutionError):
            router.execute(op_id, {}, {})


@pytest.mark.slow
def test_real_point_min_retrain_uses_trainer():
    df = _sample_df()
    split_df, _ = temporal_entity_split(
        df,
        entity_keys=["entity_id"],
        time_column="event_time",
        train_ratio=0.6,
        val_ratio=0.2,
    )
    dataset = build_real_point_dataset(
        split_df,
        entity_keys=["entity_id"],
        time_column="event_time",
        feature_columns=["value", "i_cal"],
        context_length=8,
        output_root="backend-service/data/timeseries_point/datasets_test",
    )
    assert "realpoint-w8-" in dataset["dataset_version"]
    project_root = Path(__file__).resolve().parents[2]
    report_path = project_root / dataset["dataset_dir"]
    report = json.loads((report_path / "build_report.json").read_text(encoding="utf-8"))
    assert report.get("contract") == "real_point_v1_no_grid"
    assert report.get("slot_minutes") == 0

    trained = train_real_point_classifier(
        split_df,
        contract={**CONTRACT, "split_column": "_split"},
        output_root="backend-service/data/models/timeseries_point_test",
        epochs=1,
        max_train_batches=2,
        context_length=8,
    )
    assert trained["model_path"]
    assert trained["contract"] == "real_point_v1_no_grid"
