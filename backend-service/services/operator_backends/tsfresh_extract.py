# @AI_GENERATED
"""
tsfresh_extract operator backend — Grouped tsfresh feature extraction.

When id_fields is provided, groups the input DataFrame by those fields and
computes a fixed set of tsfresh features per group per value column:

  abs_energy, sum_values, benford_correlation, absolute_sum_of_changes,
  first_location_of_minimum, first_location_of_maximum,
  last_location_of_minimum, last_location_of_maximum,
  cid (complexity invariant distance), variance_larger_than_standard_deviation

Output:
  MATRIX with MultiIndex rows keyed by id_fields — same structure as
  extract_statistical_features groupby_aggregate output, so pd.concat works directly.

When id_fields is absent or empty, returns an empty DataFrame (no-op path).
"""
import json

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "tsfresh_extract"


# ──────────────────────────────────────────────
# Inline CID (Complexity Invariant Distance)
# ──────────────────────────────────────────────

def _cid(x) -> float:
    """CID — 移植自 fault-diag-algo-release-3.1/enos_fault_diag/features/utils/statistics.py"""
    arr = np.asarray(x, dtype=float)
    diff = np.diff(arr)
    return float(np.sqrt(np.dot(diff, diff)))


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _parse_list(value, default: list) -> list:
    """Parse a list-or-JSON-string parameter."""
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
        except json.JSONDecodeError:
            pass
        return [x.strip() for x in value.split(",") if x.strip()]
    return list(default)


def _apply_tsfresh_features(series: pd.Series, col: str) -> dict:
    """
    Compute all required tsfresh features for a single series.

    Uses tsfresh.feature_extraction.feature_calculators where available and
    the inline CID implementation for complexity features.

    Returns a flat dict: {f"{col}_{feature_name}": value, ...}
    """
    from tsfresh.feature_extraction.feature_calculators import (
        abs_energy,
        sum_values,
        benford_correlation,
        absolute_sum_of_changes,
        first_location_of_minimum,
        first_location_of_maximum,
        last_location_of_minimum,
        last_location_of_maximum,
        variance_larger_than_standard_deviation,
    )

    # Drop NaN before computing; tsfresh calculators expect a clean array/Series
    arr = series.dropna().values.astype(float)

    # Guard: calculators need at least 1 element; some need ≥ 2
    if len(arr) == 0:
        return {}

    row = {}

    # ── energy / sum ───────────────────────────────
    row[f"{col}_abs_energy"] = float(abs_energy(arr))
    row[f"{col}_sum_values"] = float(sum_values(arr))

    # ── absolute sum of changes (needs ≥ 2 elements) ──
    if len(arr) >= 2:
        row[f"{col}_absolute_sum_of_changes"] = float(absolute_sum_of_changes(arr))
    else:
        row[f"{col}_absolute_sum_of_changes"] = 0.0

    # ── benford_correlation ────────────────────────
    # Returns NaN on invalid distributions; keep as 0 for fillna consistency
    try:
        bc = benford_correlation(arr)
        row[f"{col}_benford_correlation"] = float(bc) if np.isfinite(bc) else 0.0
    except Exception:
        row[f"{col}_benford_correlation"] = 0.0

    # ── location features (need ≥ 1 element) ──────
    row[f"{col}_first_location_of_minimum"] = float(first_location_of_minimum(arr))
    row[f"{col}_first_location_of_maximum"] = float(first_location_of_maximum(arr))
    row[f"{col}_last_location_of_minimum"] = float(last_location_of_minimum(arr))
    row[f"{col}_last_location_of_maximum"] = float(last_location_of_maximum(arr))

    # ── CID (needs ≥ 2 elements for diff) ─────────
    if len(arr) >= 2:
        row[f"{col}_cid"] = _cid(arr)
    else:
        row[f"{col}_cid"] = 0.0

    # ── variance_larger_than_standard_deviation ────
    # Returns bool; cast to int for numeric matrix consistency
    try:
        vtsd = variance_larger_than_standard_deviation(arr)
        row[f"{col}_variance_larger_than_std"] = int(bool(vtsd))
    except Exception:
        row[f"{col}_variance_larger_than_std"] = 0

    return row


def _compute_grouped_features(
    df: pd.DataFrame,
    id_fields: list,
    value_fields: list,
) -> pd.DataFrame:
    """
    Group df by id_fields and compute tsfresh features on each value_field per group.

    Returns a DataFrame whose index is a MultiIndex (names=id_fields) matching
    the output format of extract_statistical_features groupby_aggregate mode.
    """
    df = df.dropna(subset=value_fields, how="all").copy()
    groups = df.groupby(id_fields, sort=False)

    records = {}  # key → flat feature dict
    for key, group in groups:
        row = {}
        for col in value_fields:
            if col not in group.columns:
                continue
            feats = _apply_tsfresh_features(group[col], col)
            row.update(feats)
        # Normalise key to always be a tuple so we can build MultiIndex uniformly
        if not isinstance(key, tuple):
            key = (key,)
        records[key] = row

    if not records:
        # Return empty DataFrame with correct MultiIndex names
        empty_idx = pd.MultiIndex.from_tuples([], names=id_fields)
        return pd.DataFrame(index=empty_idx)

    result = pd.DataFrame(records).T
    result.index.names = id_fields
    result = result.fillna(0)
    result = result.round(6)
    return result


# ──────────────────────────────────────────────
# Main execute()
# ──────────────────────────────────────────────

def execute(params: dict, inputs: dict) -> dict:
    """
    Extract tsfresh features, optionally grouped by id_fields.

    Args:
        params:
            - id_fields (list | str): Group-by columns (e.g. ["site_id","device_id","time_window"]).
              When absent or empty, returns an empty DataFrame (no-op).
            - value_fields (list | str): Numeric columns to extract features from.
              When absent, uses all numeric columns not in id_fields.
        inputs:
            - data (pd.DataFrame): Input time-series data.

    Returns:
        {"data": pd.DataFrame}
            Rows are indexed by id_fields (MultiIndex). Columns are feature names
            in the form "{value_col}_{feature_name}". Compatible with pd.concat
            alongside extract_statistical_features groupby_aggregate output.
    """
    # ── Input validation ────────────────────────────────────────────────────
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # ── Parse params ─────────────────────────────────────────────────────────
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    id_fields_raw = params.get("id_fields") or options.get("id_fields")
    id_fields = _parse_list(id_fields_raw, [])

    value_fields_raw = params.get("value_fields") or options.get("value_fields")
    value_fields = _parse_list(value_fields_raw, [])

    # ── No id_fields → no-op (return empty) ─────────────────────────────────
    if not id_fields:
        logger.warning(
            f"[{OPERATOR_ID}] No id_fields provided; returning empty DataFrame. "
            "Provide id_fields to enable grouped feature extraction."
        )
        return {"data": pd.DataFrame()}

    if data.empty:
        logger.warning(f"[{OPERATOR_ID}] Input DataFrame is empty, returning empty output.")
        empty_idx = pd.MultiIndex.from_tuples([], names=id_fields)
        return {"data": pd.DataFrame(index=empty_idx)}

    # ── Validate id_fields exist in data ────────────────────────────────────
    actual_id_fields = [f for f in id_fields if f in data.columns]
    if not actual_id_fields:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"None of the id_fields {id_fields} found in DataFrame columns: {list(data.columns)}",
        )
    if len(actual_id_fields) < len(id_fields):
        missing = [f for f in id_fields if f not in data.columns]
        logger.warning(
            f"[{OPERATOR_ID}] Some id_fields not found in data and will be ignored: {missing}"
        )

    # ── Determine value_fields ───────────────────────────────────────────────
    if not value_fields:
        # Auto-detect: all numeric columns not in id_fields
        numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
        value_fields = [c for c in numeric_cols if c not in actual_id_fields]
        logger.info(
            f"[{OPERATOR_ID}] Auto-detected value_fields: {value_fields}"
        )

    if not value_fields:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            "No numeric value_fields found in the input DataFrame after excluding id_fields.",
        )

    # Validate value_fields
    missing_val = [f for f in value_fields if f not in data.columns]
    if missing_val:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"value_fields not found in DataFrame: {missing_val}",
        )

    # ── Compute features ────────────────────────────────────────────────────
    logger.info(
        f"[{OPERATOR_ID}] Computing tsfresh features — "
        f"id_fields={actual_id_fields}, value_fields={value_fields}, "
        f"n_rows={len(data)}"
    )

    result = _compute_grouped_features(data, actual_id_fields, value_fields)

    logger.info(
        f"[{OPERATOR_ID}] Done — output shape: {result.shape} "
        f"(groups={len(result)}, features={result.shape[1] if not result.empty else 0})"
    )

    return {"data": result}
# @AI_GENERATED: end
