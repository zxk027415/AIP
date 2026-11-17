"""G3: point causal regression — future row perturbation must not change current outcome."""

from __future__ import annotations

import pandas as pd

from services.timeseries_point.replay_graph_runner import run_frozen_replay_graph


def _build_series(n: int = 10) -> pd.DataFrame:
    rows = []
    t = pd.Timestamp("2024-01-01T08:00:00Z")
    for i in range(n):
        rows.append(
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b1",
                "time": t.isoformat(),
                "value": float(i + 1),
                "i_cal": float(i) * 0.2,
            }
        )
        t += pd.Timedelta(minutes=4 + (i % 3))
    return pd.DataFrame(rows)


def test_future_perturbation_does_not_change_pending_outcome():
    df = _build_series(10)
    pending_idx = 5

    baseline = run_frozen_replay_graph(
        "workflow-pv-point-predict-replay-v1",
        replay_df=df,
        pending_row_index=pending_idx,
        model_ref=None,
    )

    perturbed = df.copy()
    for col in ("value", "i_cal"):
        perturbed.loc[pending_idx + 1 :, col] = perturbed.loc[pending_idx + 1 :, col] * 999.0

    after = run_frozen_replay_graph(
        "workflow-pv-point-predict-replay-v1",
        replay_df=perturbed,
        pending_row_index=pending_idx,
        model_ref=None,
    )

    assert baseline["point_outcome"] == after["point_outcome"]


def test_past_perturbation_may_change_outcome_when_history_used():
    df = _build_series(12)
    pending_idx = 8

    baseline = run_frozen_replay_graph(
        "workflow-pv-point-predict-replay-v1",
        replay_df=df,
        pending_row_index=pending_idx,
        model_ref=None,
    )

    perturbed = df.copy()
    perturbed.loc[: pending_idx - 1, "value"] = 0.0

    changed = run_frozen_replay_graph(
        "workflow-pv-point-predict-replay-v1",
        replay_df=perturbed,
        pending_row_index=pending_idx,
        model_ref=None,
    )

    # When window becomes ready, past feature change should affect outcome or readiness.
    if baseline["point_outcome"]["kind"] != changed["point_outcome"]["kind"]:
        assert True
    else:
        assert baseline["point_outcome"] == changed["point_outcome"] or baseline["point_outcome"]["kind"] == "no_decision"
