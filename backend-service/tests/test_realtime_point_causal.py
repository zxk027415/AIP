# -*- coding: utf-8 -*-
# @AI_GENERATED
"""实时点 Causal TCN、固定归一化和 past-only 对齐的因果契约测试。"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
import torch

from services.iterative_labeling.realtime_point.model import CausalTCNRealtime
from services.iterative_labeling.realtime_point.trainer import FixedRobustScaler
from services.iterative_labeling.seq_annotation.causal_window_builder import (
    CHANNELS,
    _align_causal_grid,
    _extract_target_windows,
)


def test_causal_tcn_future_mutation_does_not_change_past_logits() -> None:
    torch.manual_seed(0)
    model = CausalTCNRealtime(
        in_channels=7,
        n_classes=8,
        hidden_channels=16,
        dilations=(1, 2, 4, 8),
        dropout=0.1,
    )
    model.eval()
    window = torch.randn(2, 72, 7)
    mutated = window.clone()
    mutated[:, 36:, :] += 1000.0
    with torch.no_grad():
        original_logits = model(window)
        mutated_logits = model(mutated)
    torch.testing.assert_close(
        original_logits[:, :36],
        mutated_logits[:, :36],
        rtol=0.0,
        atol=1e-5,
    )
    assert original_logits.shape == (2, 72, 8)
    assert model.receptive_field_points == 61


def test_fixed_robust_scaler_is_train_only_and_causal() -> None:
    channels = list(CHANNELS)
    train = np.zeros((4, 8, 7), dtype=np.float32)
    train[:, :, 0] = np.arange(8, dtype=np.float32)
    train[:, :, 1] = np.arange(8, dtype=np.float32) * 2
    train[:, :, 2] = 1.0
    train[:, 3, 2] = 0.0
    train[:, :, 3] = [0, 1, 2, 3, 0, 1, 2, 3]
    scaler = FixedRobustScaler(channels).fit(train)
    original = train[:1].copy()
    mutated = original.copy()
    mutated[:, 5:, :] += 50.0
    left = scaler.transform(original)
    right = scaler.transform(mutated)
    np.testing.assert_array_equal(left[:, :5], right[:, :5])
    assert scaler.transforms[3] == "log1p_robust"
    assert scaler.scale[3] >= math.log(2.0) - 1e-6


def test_align_causal_grid_does_not_use_future_values() -> None:
    times = pd.date_range("2026-08-01 10:00:00", periods=6, freq="5min")
    measurements = pd.DataFrame(
        {
            "time": times,
            "value": [1.0, np.nan, np.nan, np.nan, 9.0, 10.0],
            "i_cal": [2.0, np.nan, np.nan, np.nan, 8.0, 9.0],
        }
    )
    aligned = _align_causal_grid(
        measurements,
        start=times[0],
        end=times[-1] + pd.Timedelta(minutes=5),
        slot_minutes=5,
        max_forward_fill_slots=2,
    )
    assert list(aligned["is_measured"]) == [1.0, 0.0, 0.0, 0.0, 1.0, 1.0]
    assert aligned.loc[1, "value"] == pytest.approx(1.0)
    assert aligned.loc[2, "value"] == pytest.approx(1.0)
    assert aligned.loc[3, "value"] == pytest.approx(0.0)
    mutated = measurements.copy()
    mutated.loc[mutated["time"] >= times[4], ["value", "i_cal"]] = 1000.0
    changed = _align_causal_grid(
        mutated,
        start=times[0],
        end=times[-1] + pd.Timedelta(minutes=5),
        slot_minutes=5,
        max_forward_fill_slots=2,
    )
    pd.testing.assert_frame_equal(
        aligned.loc[aligned["time"] < times[4], CHANNELS],
        changed.loc[changed["time"] < times[4], CHANNELS],
    )


def test_midnight_window_uses_previous_day_context() -> None:
    target = pd.Timestamp("2026-08-02 00:00:00")
    start = target - pd.Timedelta(minutes=71 * 5)
    times = pd.date_range(start, target, freq="5min")
    synthetic = pd.DataFrame(
        {
            "time": times,
            "value": np.arange(len(times), dtype=np.float32),
            "i_cal": np.arange(len(times), dtype=np.float32),
        }
    )
    aligned = _align_causal_grid(
        synthetic,
        start=start,
        end=target + pd.Timedelta(minutes=5),
        slot_minutes=5,
        max_forward_fill_slots=2,
    )
    labels = pd.DataFrame({"time": [target], "label_id": [7], "source": ["human_range"]})
    windows, targets, metadata = _extract_target_windows(
        aligned,
        labels=labels,
        target_start=target,
        target_end=target + pd.Timedelta(minutes=5),
        window_size=72,
        stride=1,
        slot_minutes=5,
        min_measured_ratio=1.0,
        max_gap_multiplier=6,
        require_label=True,
    )
    assert len(windows) == 1
    assert pd.Timestamp(metadata[0]["start_time"]).date() < target.date()
    assert pd.Timestamp(metadata[0]["target_time"]) == target
    assert int(targets[0][-1]) == 7
    assert int(targets[0][0]) == -1


def test_class_weights_none_vs_balanced() -> None:
    from services.iterative_labeling.realtime_point.trainer import RealtimePointTrainer

    counts = np.asarray([80, 10, 10], dtype=np.int64)
    none = RealtimePointTrainer._class_weights(counts, mode="none")
    balanced = RealtimePointTrainer._class_weights(counts, mode="balanced")
    np.testing.assert_array_equal(none, np.ones(3, dtype=np.float32))
    assert balanced[0] < balanced[1]
    assert abs(float(balanced.mean()) - 1.0) < 1e-5


def test_daylight_loss_mask_drops_night_last_points() -> None:
    from services.iterative_labeling.realtime_point.trainer import RealtimePointTrainer

    trainer = RealtimePointTrainer(target_mode="last_point", loss_slot_mask="daylight")
    trainer._daylight_index = 6
    y = np.asarray([[-1, 0], [1, 1], [0, 0]], dtype=np.int64)
    x = np.zeros((3, 2, 7), dtype=np.float32)
    x[0, 1, 6] = 1.0
    x[1, 1, 6] = 0.0
    x[2, 1, 6] = 1.0
    mask = trainer._target_mask_numpy(y, x)
    assert mask.tolist() == [[False, True], [False, False], [False, True]]
# @AI_GENERATED: end
