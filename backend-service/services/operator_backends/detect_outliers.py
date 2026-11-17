# @AI_GENERATED
"""
detect_outliers operator backend — Detects and replaces outliers in time series data.

Reuses logic from data_process.chebyshev_detector (rolling MAD).
Supports zscore/iqr/isolation_forest methods.
Only uses historical data (shift(1)) to avoid future data leakage.
Returns DataFrame with outliers replaced by NaN and outlier index list.
"""
import json

import numpy as np
import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "detect_outliers"


def _to_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    return bool(v)


def _detect_zscore(series: pd.Series, window: int, threshold: float) -> pd.Series:
    """
    Rolling MAD-based z-score detection (reuses chebyshev_detector logic).
    Uses shift(1) to avoid future data leakage.
    Returns boolean mask where True = outlier.
    """
    x = pd.to_numeric(series, errors="coerce")
    min_periods = max(5, window // 10)

    # Rolling robust stats — past-only via shift(1)
    med = x.rolling(window=window, min_periods=min_periods).median().shift(1)
    mad = (x - med).abs().rolling(window=window, min_periods=min_periods).median().shift(1)
    scale = 1.4826 * mad  # MAD -> approx std

    denom = scale.replace(0, np.nan)
    score = (x - med).abs() / denom
    return score > threshold


def _detect_iqr(series: pd.Series, window: int, threshold: float) -> pd.Series:
    """
    Rolling IQR-based outlier detection.
    Uses shift(1) to avoid future data leakage.
    """
    x = pd.to_numeric(series, errors="coerce")
    min_periods = max(5, window // 10)

    q1 = x.rolling(window=window, min_periods=min_periods).quantile(0.25).shift(1)
    q3 = x.rolling(window=window, min_periods=min_periods).quantile(0.75).shift(1)
    iqr = q3 - q1
    lower = q1 - threshold * iqr
    upper = q3 + threshold * iqr
    return (x < lower) | (x > upper)


def _clip_one_col(group: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """
    移植自 DataCleaner.get_robust_data。
    按差分排序，将首尾极值（最小差分和最大两条）置为 NaN，其余值保留。
    """
    data = group.copy()
    data[f"{value_col}_diff"] = data[value_col].diff()
    data = data.sort_values(by=f"{value_col}_diff")
    # 排序后：第 0 行是最小差分（含 NaN diff），最后两行是最大差分
    # new_val: 首位和末两位置 NaN，中间保持原值
    new_val = [np.nan] + data[value_col].iloc[1:-2].tolist() + [np.nan, np.nan]
    data[value_col] = new_val
    data.sort_index(inplace=True)
    return data.drop(columns=[f"{value_col}_diff"])


def _robust_clip(df: pd.DataFrame, id_fields: list, value_fields: list) -> pd.DataFrame:
    """
    移植自 DataCleaner.transform 中的异常值裁剪逻辑。
    对每个 value_field，仅在组内数据量中位数 > 24 时执行 _clip_one_col。
    """
    result = df.copy()
    for col in value_fields:
        if col not in result.columns:
            continue
        # 计算各分组的非空计数中位数作为参考数据量
        group_counts = result.groupby(id_fields)[col].count()
        median_count = group_counts.median()
        if median_count > 24:
            result = result.groupby(id_fields, group_keys=False).apply(
                _clip_one_col, col
            )
    return result


def _detect_isolation_forest(series: pd.Series, threshold: float) -> pd.Series:
    """
    Isolation Forest outlier detection.
    threshold is used as contamination parameter (clamped to valid range).
    """
    x = pd.to_numeric(series, errors="coerce")
    valid_mask = x.notna()
    result = pd.Series(False, index=series.index)

    if valid_mask.sum() < 10:
        return result

    try:
        from sklearn.ensemble import IsolationForest
    except ImportError:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "DependencyError",
            "scikit-learn is required for isolation_forest method",
        )

    contamination = min(max(1.0 / threshold / 10, 0.01), 0.5)
    values = x[valid_mask].values.reshape(-1, 1)
    clf = IsolationForest(contamination=contamination, random_state=42)
    preds = clf.fit_predict(values)
    outlier_flags = preds == -1
    result.loc[valid_mask] = outlier_flags
    return result


def execute(params: dict, inputs: dict) -> dict:
    """
    Detect outliers in time series data.

    Args:
        params: Operator parameters including:
            - method (str, optional): Detection method: zscore/iqr/isolation_forest. Default "zscore".
            - threshold (float, optional): Detection sensitivity. Default 3.0.
            - load_field (str, optional): Target column name. Default "load".
            - window_size (int, optional): Rolling window size. Default 96.
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame (outliers replaced with NaN), "outlier_indices": List[int]}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # Parse options
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    method = params.get("method") or options.get("method") or "zscore"
    threshold = float(params.get("threshold") or options.get("threshold") or 3.0)
    load_field = params.get("load_field") or options.get("load_field") or "load"
    window_size = int(params.get("window_size") or options.get("window_size") or 96)

    # robust_clip 专用参数
    id_fields_raw = params.get("id_fields") or options.get("id_fields")
    if isinstance(id_fields_raw, str):
        try:
            id_fields_raw = json.loads(id_fields_raw)
        except json.JSONDecodeError:
            id_fields_raw = [id_fields_raw]
    id_fields: list = id_fields_raw if isinstance(id_fields_raw, list) else []

    value_fields_raw = params.get("value_fields") or options.get("value_fields")
    if isinstance(value_fields_raw, str):
        try:
            value_fields_raw = json.loads(value_fields_raw)
        except json.JSONDecodeError:
            value_fields_raw = [value_fields_raw]
    value_fields: list = value_fields_raw if isinstance(value_fields_raw, list) else []
    gcfg = params.get("_global_config") or {}
    strict_alignment_raw = params.get("strict_alignment_mode")
    if strict_alignment_raw is None:
        strict_alignment_raw = options.get("strict_alignment_mode")
    if strict_alignment_raw is None and isinstance(gcfg, dict):
        strict_alignment_raw = gcfg.get("strict_alignment_mode")
    strict_alignment_mode = _to_bool(strict_alignment_raw, False)
    skip_when_strict = _to_bool(
        params.get("skip_when_strict_alignment")
        if params.get("skip_when_strict_alignment") is not None
        else options.get("skip_when_strict_alignment"),
        False,
    )

    valid_methods = {"zscore", "iqr", "isolation_forest", "robust_clip"}
    if method not in valid_methods:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Invalid method '{method}'. Must be one of {sorted(valid_methods)}",
        )

    df = data.copy()
    if strict_alignment_mode and skip_when_strict:
        logger.info(f"[{OPERATOR_ID}] strict_alignment_mode enabled, skip outlier detection")
        return {"data": df, "outlier_indices": []}

    if df.empty:
        logger.warning(f"[{OPERATOR_ID}] Empty data, returning as-is")
        return {"data": df, "outlier_indices": []}

    # robust_clip: 按分组裁剪极值，不走 mask 路径，直接返回
    if method == "robust_clip":
        effective_id_fields = [f for f in id_fields if f in df.columns]
        effective_value_fields = [f for f in value_fields if f in df.columns]
        if not effective_id_fields:
            logger.warning(
                f"[{OPERATOR_ID}] robust_clip: id_fields {id_fields} 中无有效列，返回原数据"
            )
            return {"data": df, "outlier_indices": []}
        if not effective_value_fields:
            logger.warning(
                f"[{OPERATOR_ID}] robust_clip: value_fields {value_fields} 中无有效列，返回原数据"
            )
            return {"data": df, "outlier_indices": []}
        df = _robust_clip(df, effective_id_fields, effective_value_fields)
        logger.info(
            f"[{OPERATOR_ID}] robust_clip applied "
            f"(id_fields={effective_id_fields}, value_fields={effective_value_fields})"
        )
        return {"data": df, "outlier_indices": []}

    if load_field not in df.columns:
        logger.warning(
            f"[{OPERATOR_ID}] '{load_field}' column not found, returning as-is"
        )
        return {"data": df, "outlier_indices": []}

    # Detect outliers based on method
    if method == "zscore":
        mask = _detect_zscore(df[load_field], window_size, threshold)
    elif method == "iqr":
        mask = _detect_iqr(df[load_field], window_size, threshold)
    elif method == "isolation_forest":
        mask = _detect_isolation_forest(df[load_field], threshold)
    else:
        mask = pd.Series(False, index=df.index)

    # Collect outlier indices (as integer positions)
    outlier_indices = df.index[mask.fillna(False)].tolist()
    n_outliers = len(outlier_indices)

    # Replace outliers with NaN
    if n_outliers > 0:
        df.loc[mask.fillna(False), load_field] = np.nan

    logger.info(
        f"[{OPERATOR_ID}] Detected {n_outliers} outliers "
        f"(method={method}, threshold={threshold}, window={window_size})"
    )

    return {"data": df, "outlier_indices": outlier_indices}
# @AI_GENERATED: end
