# @AI_GENERATED
"""Run real registered models on mock data for pv_day (RFC) and pv_point (TCN).

This module is the bridge between loop_demo and the actual trained model artifacts.
It replaces the rule-based ``_predict_i_cal`` with real model inference while keeping
the same output schema (list of outcome dicts with predicted_label / gold_label / confidence).
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENTITY_KEYS = ["site_id", "device_id", "branch_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# Model loading
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_model_artifact(slot: str) -> dict[str, Any]:
    """Use the same resolution logic as slot_workflow_runner: champion → rolling → challenger → latest."""
    from services.scheduler.slot_workflow_runner import resolve_slot_scheduler_model
    resolved = resolve_slot_scheduler_model(slot)
    # normalize keys for callers
    resolved["artifact_ref"] = resolved.get("model_artifact_ref") or ""
    resolved["candidate_id"] = resolved.get("model_candidate_id") or ""
    return resolved


def _load_rfc_model(artifact_ref: str) -> dict[str, Any]:
    """Load a pickled RFC model dict: {model, feature_list, ...}."""
    path = _BACKEND_DIR / artifact_ref.replace("\\", "/")
    if not path.is_file():
        # try without backend-service prefix
        alt = _BACKEND_DIR.parent / artifact_ref.replace("\\", "/")
        if alt.is_file():
            path = alt
        else:
            raise FileNotFoundError(f"RFC model not found: {artifact_ref} (tried {path} and {alt})")
    with open(path, "rb") as f:
        return pickle.load(f)


def _load_tcn_artifact(artifact_ref: str):
    """Load a TCN artifact directory using the realtime_point loader.

    ``artifact_ref`` is expected to be a project-root-relative path like
    ``backend-service/data/models/timeseries_point/rtpoint-tcn-…``.
    ``load_realtime_point_artifact`` resolves it from the project root internally.
    """
    from services.iterative_labeling.realtime_point.artifact import load_realtime_point_artifact
    # @AI_GENERATED
    # The artifact loader expects a project-root-relative path, not an absolute one.
    # artifact_ref from the registry is already relative (e.g. "backend-service/data/models/…").
    ref = artifact_ref.replace("\\", "/").strip()
    if not ref:
        raise FileNotFoundError("TCN artifact_ref is empty")
    return load_realtime_point_artifact(ref, device="cpu")
    # @AI_GENERATED: end


# ═══════════════════════════════════════════════════════════════════════════════
# pv_day: RFC feature extraction + predict
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_rfc_features(chunk: pd.DataFrame) -> pd.DataFrame:
    """Replicate the extract_statistical_features groupby_aggregate pipeline.

    Groups by (site_id, device_id, branch_id, date) and computes the same 50
    features the RFC was trained on.
    """
    from scipy.stats import kurtosis as scipy_kurtosis, skew as scipy_skew

    group_keys = _ENTITY_KEYS + ["date"]
    value_fields = ["value", "i_cal"]

    # ensure date column
    work = chunk.copy()
    if "date" not in work.columns:
        work["date"] = pd.to_datetime(work["time"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    else:
        work["date"] = work["date"].astype(str).str[:10]

    groups = work.groupby(group_keys)
    rows = []
    for keys, group in groups:
        row = dict(zip(group_keys, keys if isinstance(keys, tuple) else (keys,)))
        for col in value_fields:
            vals = group[col].dropna().values.astype(float)
            if len(vals) == 0:
                vals = np.array([0.0])
            diff = np.diff(vals) if len(vals) > 1 else np.array([0.0])

            # basic stats
            row[f"{col}_max"] = float(np.nanmax(vals))
            row[f"{col}_min"] = float(np.nanmin(vals))
            row[f"{col}_mean"] = float(np.nanmean(vals))
            row[f"{col}_median"] = float(np.nanmedian(vals))
            row[f"{col}_std"] = float(np.nanstd(vals))
            row[f"{col}_kurtosis"] = float(scipy_kurtosis(vals, fisher=True, bias=False)) if len(vals) > 1 else 0.0
            row[f"{col}_skew"] = float(scipy_skew(vals, bias=False)) if len(vals) > 1 else 0.0
            row[f"{col}_max_min"] = float(np.nanmax(vals) - np.nanmin(vals))
            mean_val = float(np.nanmean(vals))
            row[f"{col}_above_mean_ratio"] = float(np.sum(vals > mean_val) / len(vals)) if len(vals) > 0 else 0.0
            row[f"{col}_variation_coef"] = float(np.nanstd(vals) / abs(mean_val)) if abs(mean_val) > 1e-9 else 0.0

            # quantiles
            row[f"{col}_quantile_25"] = float(np.nanquantile(vals, 0.25))
            row[f"{col}_quantile_75"] = float(np.nanquantile(vals, 0.75))

            # autocorrelation lag 1-3
            for lag in (1, 2, 3):
                if len(vals) > lag:
                    c0 = np.var(vals)
                    if c0 > 1e-12:
                        cl = np.mean((vals[lag:] - mean_val) * (vals[:-lag] - mean_val))
                        row[f"{col}_autocorr_lag{lag}"] = float(cl / c0)
                    else:
                        row[f"{col}_autocorr_lag{lag}"] = 0.0
                else:
                    row[f"{col}_autocorr_lag{lag}"] = 0.0

            # flat features
            if len(vals) > 1:
                is_flat = np.abs(np.diff(vals)) < 1e-6
                flat_runs = []
                run_len = 0
                for v in is_flat:
                    if v:
                        run_len += 1
                    else:
                        if run_len > 0:
                            flat_runs.append(run_len)
                        run_len = 0
                if run_len > 0:
                    flat_runs.append(run_len)
                row[f"{col}_flat_rate"] = float(np.sum(is_flat) / len(is_flat))
                row[f"{col}_flat_max"] = float(max(flat_runs)) if flat_runs else 0.0
                row[f"{col}_flat_count"] = float(len(flat_runs))
                row[f"{col}_max_drop"] = float(np.min(np.diff(vals)))
            else:
                row[f"{col}_flat_rate"] = 0.0
                row[f"{col}_flat_max"] = 0.0
                row[f"{col}_flat_count"] = 0.0
                row[f"{col}_max_drop"] = 0.0

            # diff stats
            row[f"{col}_diff_max"] = float(np.nanmax(diff)) if len(diff) > 0 else 0.0
            row[f"{col}_diff_min"] = float(np.nanmin(diff)) if len(diff) > 0 else 0.0
            row[f"{col}_diff_mean"] = float(np.nanmean(diff)) if len(diff) > 0 else 0.0
            row[f"{col}_diff_median"] = float(np.nanmedian(diff)) if len(diff) > 0 else 0.0
            row[f"{col}_diff_std"] = float(np.nanstd(diff)) if len(diff) > 0 else 0.0
            row[f"{col}_diff_kurtosis"] = float(scipy_kurtosis(diff, fisher=True, bias=False)) if len(diff) > 2 else 0.0

        rows.append(row)
    return pd.DataFrame(rows)


def detect_day_with_rfc(
    chunk: pd.DataFrame,
    gold: pd.DataFrame,
    *,
    model_info: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], str]:
    """Detect all 5-min points in chunk using the real RFC model.

    Returns (outcomes_list, model_id).
    The RFC predicts per device-day, but we emit per-point outcomes
    so the frontend can draw the intraday curve.
    """
    if model_info is None:
        resolved = _resolve_model_artifact("pv_day")
        artifact_ref = str(resolved.get("artifact_ref") or "")
        model_id = str(resolved.get("candidate_id") or resolved.get("model_candidate_id") or "unknown")
    else:
        artifact_ref = str(model_info.get("artifact_ref") or model_info.get("model_artifact_ref") or "")
        model_id = str(model_info.get("candidate_id") or model_info.get("model_candidate_id") or "unknown")

    rfc_bundle = _load_rfc_model(artifact_ref)
    model = rfc_bundle["model"]
    feature_list = rfc_bundle.get("feature_list") or list(model.feature_names_in_)

    # extract features per device-day
    features_df = _extract_rfc_features(chunk)
    group_keys = _ENTITY_KEYS + ["date"]

    # predict per device-day
    if features_df.empty:
        return [], model_id
    X = features_df[feature_list].fillna(0)
    preds = model.predict(X)
    probas = model.predict_proba(X) if hasattr(model, "predict_proba") else None

    # build per-device-day prediction map
    day_pred_map: dict[str, tuple[int, float]] = {}
    for i, (_, row) in enumerate(features_df.iterrows()):
        key = "|".join(str(row.get(k) or "") for k in group_keys)
        pred_label = int(preds[i])
        conf = float(np.max(probas[i])) if probas is not None else 0.8
        day_pred_map[key] = (pred_label, conf)

    # build gold lookup (point-level)
    gold_copy = gold.copy()
    if "date" not in gold_copy.columns:
        gold_copy["date"] = pd.to_datetime(gold_copy["time"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    gold_copy["_pk"] = (
        gold_copy["site_id"].astype(str) + "|"
        + gold_copy["device_id"].astype(str) + "|"
        + gold_copy["branch_id"].astype(str) + "|"
        + gold_copy["time"].astype(str)
    )
    gold_by_point = dict(zip(gold_copy["_pk"], gold_copy["label"].astype(int)))

    # emit per-point outcomes (day prediction is broadcast to each point)
    work = chunk.copy()
    if "date" not in work.columns:
        work["date"] = pd.to_datetime(work["time"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    items: list[dict[str, Any]] = []
    for _, row in work.iterrows():
        site = str(row.get("site_id") or "")
        device = str(row.get("device_id") or "")
        branch = str(row.get("branch_id") or "")
        date = str(row.get("date") or "")[:10]
        time_str = str(row.get("time") or "")
        day_key = f"{site}|{device}|{branch}|{date}"
        point_key = f"{site}|{device}|{branch}|{time_str}"
        pred, conf = day_pred_map.get(day_key, (0, 0.5))
        truth = gold_by_point.get(point_key)
        if truth is None:
            truth = int(pred)  # fallback if gold miss
        i_cal = float(row.get("i_cal") or row.get("value") or 0.0)
        value = float(row.get("value") or i_cal)
        items.append({
            "unit_key": point_key,
            "site_id": site,
            "device_id": device,
            "branch_id": branch,
            "date": date,
            "time": time_str,
            "predicted_label": pred,
            "gold_label": int(truth),
            "confidence": conf,
            "kind": "prediction",
            "i_cal": i_cal,
            "value": value,
        })
    return items, model_id


# ═══════════════════════════════════════════════════════════════════════════════
# pv_point: TCN point-level predict
# ═══════════════════════════════════════════════════════════════════════════════

def _build_derived_channels(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived channels the TCN expects: is_measured, time_since_measured, tod_sin, tod_cos, is_daylight."""
    work = df.copy()
    work["is_measured"] = 1.0
    work["time_since_measured"] = 0.0
    ts = pd.to_datetime(work["time"], errors="coerce", utc=True)
    hour_frac = ts.dt.hour + ts.dt.minute / 60.0
    work["tod_sin"] = np.sin(2 * np.pi * hour_frac / 24.0)
    work["tod_cos"] = np.cos(2 * np.pi * hour_frac / 24.0)
    work["is_daylight"] = ((hour_frac >= 6.0) & (hour_frac <= 20.0)).astype(float)
    return work


def detect_point_with_tcn(
    chunk: pd.DataFrame,
    gold: pd.DataFrame,
    *,
    model_info: Optional[dict[str, Any]] = None,
    context_length: int = 8,
) -> tuple[list[dict[str, Any]], str]:
    """Detect each 5-min point using the real TCN model.

    For each point, we build a causal window of ``context_length`` prior points
    (same entity), pass the raw [B,W,C] ndarray to ``artifact.forward()`` which
    handles normalization and torch inference internally.

    Returns (outcomes_list, model_id).
    """

    if model_info is None:
        resolved = _resolve_model_artifact("pv_point")
        artifact_ref = str(resolved.get("artifact_ref") or "")
        model_id = str(resolved.get("candidate_id") or resolved.get("model_candidate_id") or "unknown")
    else:
        artifact_ref = str(model_info.get("artifact_ref") or model_info.get("model_artifact_ref") or "")
        model_id = str(model_info.get("candidate_id") or model_info.get("model_candidate_id") or "unknown")

    loaded = _load_tcn_artifact(artifact_ref)
    meta = loaded.metadata
    channels = list(meta.get("channels") or ["value", "i_cal", "is_measured", "time_since_measured", "tod_sin", "tod_cos", "is_daylight"])
    ctx = int(meta.get("context_length") or context_length)
    class_map = list(meta.get("class_index_to_label") or [0, 1, 2])
    # NOTE: loaded.forward() handles normalization internally via FixedRobustScaler

    # gold lookup
    gold_copy = gold.copy()
    gold_copy["_pk"] = (
        gold_copy["site_id"].astype(str) + "|"
        + gold_copy["device_id"].astype(str) + "|"
        + gold_copy["branch_id"].astype(str) + "|"
        + gold_copy["time"].astype(str)
    )
    gold_by_point = dict(zip(gold_copy["_pk"], gold_copy["label"].astype(int)))

    # prepare data with derived channels
    work = _build_derived_channels(chunk)
    work = work.sort_values(["site_id", "device_id", "branch_id", "time"]).reset_index(drop=True)
    if "date" not in work.columns:
        work["date"] = pd.to_datetime(work["time"], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")

    items: list[dict[str, Any]] = []
    # group by entity for causal windowing
    entity_groups = work.groupby(_ENTITY_KEYS)
    for entity_key, entity_df in entity_groups:
        entity_df = entity_df.sort_values("time").reset_index(drop=True)
        site, device, branch = (str(k) for k in (entity_key if isinstance(entity_key, tuple) else (entity_key,)))

        for idx in range(len(entity_df)):
            row = entity_df.iloc[idx]
            time_str = str(row.get("time") or "")
            date_str = str(row.get("date") or "")[:10]
            point_key = f"{site}|{device}|{branch}|{time_str}"
            i_cal = float(row.get("i_cal") or row.get("value") or 0.0)
            value = float(row.get("value") or i_cal)
            truth = gold_by_point.get(point_key)

            # not enough history for a window yet
            if idx < ctx - 1:
                pred = 0
                conf = 0.0
                kind = "no_decision"
                if truth is None:
                    truth = 0
                items.append({
                    "unit_key": point_key,
                    "site_id": site, "device_id": device, "branch_id": branch,
                    "date": date_str, "time": time_str,
                    "predicted_label": pred, "gold_label": int(truth),
                    "confidence": conf, "kind": kind,
                    "i_cal": i_cal, "value": value,
                })
                continue

            # build raw window: [1, ctx, channels] — artifact.forward does normalization
            window = entity_df.iloc[max(0, idx - ctx + 1):idx + 1]
            raw_window = np.zeros((ctx, len(channels)), dtype=np.float32)
            for ci, ch in enumerate(channels):
                if ch in window.columns:
                    vals = window[ch].values.astype(np.float32)
                else:
                    vals = np.zeros(len(window), dtype=np.float32)
                padded = np.zeros(ctx, dtype=np.float32)
                padded[-len(vals):] = vals
                raw_window[:, ci] = padded

            # forward: artifact handles normalization + torch internally
            try:
                logits = loaded.forward(raw_window[np.newaxis])  # [1, ctx, C] -> logits
                logits_np = logits.detach().cpu().numpy()
                if logits_np.ndim == 3:
                    logits_np = logits_np[0, -1]
                elif logits_np.ndim == 2:
                    logits_np = logits_np[0]
                else:
                    logits_np = logits_np.reshape(-1)
                shifted = logits_np - np.max(logits_np)
                probs = np.exp(shifted) / np.sum(np.exp(shifted))
                class_idx = int(np.argmax(probs))
                pred = int(class_map[class_idx]) if class_idx < len(class_map) else 0
                conf = float(probs[class_idx])
                kind = "prediction"
            except Exception as exc:
                logger.warning("[real_model_detect] TCN forward failed for %s: %s", point_key, exc)
                pred = 0
                conf = 0.0
                kind = "no_decision"

            if truth is None:
                truth = int(pred)
            items.append({
                "unit_key": point_key,
                "site_id": site, "device_id": device, "branch_id": branch,
                "date": date_str, "time": time_str,
                "predicted_label": pred, "gold_label": int(truth),
                "confidence": conf, "kind": kind,
                "i_cal": i_cal, "value": value,
            })

    return items, model_id
# @AI_GENERATED: end
