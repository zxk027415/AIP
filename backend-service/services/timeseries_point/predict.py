"""Predict current point from window + artifact."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from .contract import PointOutcome, WindowResult


def predict_point_outcome(
    window: WindowResult,
    *,
    artifact_dir: Optional[str] = None,
    artifact_loader=None,
) -> PointOutcome:
    if window.status != "ready" or window.window_tensor is None:
        return PointOutcome(
            kind="no_decision",
            reason=window.reason or "window_not_ready",
            evidence={"window_status": window.status},
        )
    if not artifact_dir:
        return PointOutcome(kind="no_decision", reason="missing_model_ref")

    if artifact_loader is None:
        from services.iterative_labeling.realtime_point.artifact import load_realtime_point_artifact

        artifact_loader = load_realtime_point_artifact

    try:
        loaded = artifact_loader(artifact_dir, device="cpu")
    except Exception as exc:
        return PointOutcome(kind="no_decision", reason="artifact_load_failed", evidence={"error": str(exc)})

    expected_channels = int(loaded.metadata.get("constructor_config", {}).get("in_channels") or 0)
    actual_channels = window.window_tensor.shape[-1]
    expected_window = int(loaded.metadata.get("context_length") or 0)
    if expected_channels and actual_channels != expected_channels:
        return PointOutcome(
            kind="no_decision",
            reason="artifact_channel_mismatch",
            evidence={"expected": expected_channels, "actual": actual_channels},
        )
    if expected_window and window.context_length != expected_window:
        return PointOutcome(
            kind="no_decision",
            reason="artifact_window_mismatch",
            evidence={"expected": expected_window, "actual": window.context_length},
        )

    logits = loaded.forward(window.window_tensor)
    logits_arr = logits.detach().cpu().numpy()
    if logits_arr.ndim == 3:
        # Causal TCN emits per-timestep logits [B, W, C]; realtime point predicts at window tail.
        logits_np = logits_arr[0, -1]
    elif logits_arr.ndim == 2:
        logits_np = logits_arr[0]
    else:
        logits_np = logits_arr.reshape(-1)
    if logits_np.size == 0:
        return PointOutcome(kind="no_decision", reason="empty_logits")
    shifted = logits_np - np.max(logits_np)
    exp = np.exp(shifted)
    probs = exp / np.sum(exp)
    class_idx = int(np.argmax(probs))
    if class_idx < 0 or class_idx >= len(loaded.class_index_to_label):
        return PointOutcome(
            kind="no_decision",
            reason="class_index_out_of_range",
            evidence={"class_idx": class_idx, "label_space_size": len(loaded.class_index_to_label)},
        )
    label = int(loaded.class_index_to_label[class_idx])
    confidence = float(np.asarray(probs[class_idx]).reshape(-1)[0])
    return PointOutcome(
        kind="prediction",
        label=label,
        confidence=confidence,
        evidence={"class_index": class_idx},
    )
