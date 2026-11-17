"""Tests for frozen replay graph runner."""

from __future__ import annotations

import pandas as pd

from services.timeseries_point.replay_graph_runner import run_frozen_replay_graph


def test_frozen_replay_graph_produces_point_outcome():
    rows = []
    t = pd.Timestamp("2024-01-01T08:00:00Z")
    for i in range(6):
        rows.append(
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b1",
                "time": t.isoformat(),
                "value": float(i + 1),
                "i_cal": float(i),
            }
        )
        t += pd.Timedelta(minutes=5)
    df = pd.DataFrame(rows)
    result = run_frozen_replay_graph(
        "workflow-pv-point-predict-replay-v1",
        replay_df=df,
        pending_row_index=len(df) - 1,
        model_ref=None,
    )
    assert "point_outcome" in result
    assert result["point_outcome"]["kind"] == "no_decision"
    assert result["workflow_id"] == "workflow-pv-point-predict-replay-v1"
