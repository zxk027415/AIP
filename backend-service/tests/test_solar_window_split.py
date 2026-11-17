# -*- coding: utf-8 -*-
"""solar_window / night_anomaly / time_window_split solar_mode tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.operator_backends.night_anomaly import compute_night_anomaly_features
from services.operator_backends.solar_window import segment_solar_window
from services.operator_backends.time_window_split import execute as time_window_split_exec


def _synthetic_day():
    times = pd.date_range("2026-07-20 00:00:00", periods=24, freq="1h")
    value = np.array(
        [0.0] * 6 + [0.2, 0.5, 0.8, 1.0, 0.9, 0.7, 0.4, 0.2] + [0.0] * 10,
        dtype=float,
    )
    return pd.DataFrame(
        {
            "time": times,
            "site_id": ["s1"] * 24,
            "device_id": ["d1"] * 24,
            "branch_id": ["b1"] * 24,
            "value": value,
            "i_cal": value * 0.9,
        }
    )


def test_daylight_excludes_night_rows():
    df, warnings = segment_solar_window(
        _synthetic_day(),
        id_cols=["site_id", "device_id", "branch_id"],
        time_col="time",
        solar_mode="daylight",
        irr_threshold=0.05,
        power_col="value",
    )
    assert not df.empty
    assert (df["period_role"] == "daylight").all()
    assert set(df["time_window"].astype(str)) == {"2026-07-20"}
    assert df["value"].min() >= 0.05 * 1.0


def test_day_and_night_produces_both_windows():
    df, _ = segment_solar_window(
        _synthetic_day(),
        id_cols=["site_id", "device_id", "branch_id"],
        time_col="time",
        solar_mode="day_and_night",
        power_col="value",
    )
    roles = set(df["period_role"].astype(str))
    assert "daylight" in roles and "night" in roles
    assert "2026-07-20#night" in set(df["time_window"].astype(str))


def test_night_anomaly_detects_nonzero_current():
    night = pd.DataFrame({"value": [0.0, 0.0, 0.5, 0.2], "power": [0, 0, 0.1, 0]})
    feats = compute_night_anomaly_features(night, current_col="value", power_col="power")
    assert feats["night_nonzero_current_ratio"] == 0.5
    assert feats["night_current_max"] == 0.5
    assert feats["night_over_threshold_duration"] == 2.0


def test_time_window_split_solar_mode_attaches_night_features():
    data = _synthetic_day()
    base = time_window_split_exec(
        {"window": "1d", "id_fields": ["site_id", "device_id", "branch_id"]},
        {"data": data},
    )["data"]
    solar = time_window_split_exec(
        {
            "window": "1d",
            "id_fields": ["site_id", "device_id", "branch_id"],
            "solar_mode": "day_and_night",
            "power_col": "value",
        },
        {"data": data},
    )["data"]
    assert "time_window" in base.columns
    assert "period_role" in solar.columns
    assert solar["time_window"].astype(str).str.contains("#night").any()
    assert "night_nonzero_current_ratio" in solar.columns

def test_time_window_split_preserves_freeform_keys():
    data = _synthetic_day().copy()
    freeform_key = "2026-07-20T10:00:00__2026-07-20T12:00:00#freeform"
    # mark midday hours as freeform sample
    mask = (data["time"] >= "2026-07-20 10:00:00") & (data["time"] <= "2026-07-20 12:00:00")
    data.loc[mask, "time_window"] = freeform_key
    data.loc[mask, "label"] = 3
    out = time_window_split_exec(
        {"window": "1d", "id_fields": ["site_id", "device_id", "branch_id"]},
        {"data": data},
    )["data"]
    preserved = out[out["time_window"].astype(str) == freeform_key]
    assert len(preserved) == int(mask.sum())
    # remaining rows still get daily windows
    other = out[out["time_window"].astype(str) != freeform_key]
    assert len(other) > 0
    assert other["time_window"].notna().all()
