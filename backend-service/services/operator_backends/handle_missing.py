# @AI_GENERATED
"""
handle_missing operator backend — Fills missing values in time series data.

Reuses logic from data_process.get_completed_df (interpolate(method='time')).
Supports linear/ffill/bfill/mean methods.
After interpolation, ffill+bfill as fallback to ensure no NaN.
Non-target columns use ffill/bfill.
Advanced params: time_field, load_field.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "handle_missing"


def _drop_insufficient(
    df: pd.DataFrame,
    id_fields: list,
    value_fields: list,
    keep_threshold: float = 0.75,
) -> pd.DataFrame:
    """
    移植自 DataCleaner.check_missing。
    丢弃任意 value_field 的非空计数低于 (中位数 * keep_threshold) 的数据组。
    """
    groupby_series = [df[col] for col in id_fields]
    not_null_count = df[value_fields].notnull().groupby(groupby_series).sum()
    not_null_count_median = not_null_count.median()
    min_keep_len = not_null_count_median * keep_threshold
    logger.info(f"[{OPERATOR_ID}] drop_insufficient: min_keep_len={min_keep_len.to_dict()}")
    check_df = (not_null_count < min_keep_len).any(axis=1)
    keep_df = check_df[~check_df].reset_index()
    keep_index = keep_df[id_fields]
    return df.merge(keep_index, on=id_fields, how="right")


def _pick_target_column(df: pd.DataFrame, primary: str, fallbacks: list[str]) -> str:
    """Pick a target column with the most finite numeric values."""
    candidates = [primary] + [c for c in fallbacks if c and c != primary]
    best_col = None
    best_score = -1
    for col in candidates:
        if col not in df.columns:
            continue
        score = int(pd.to_numeric(df[col], errors="coerce").notna().sum())
        if score > best_score:
            best_col = col
            best_score = score
    return best_col or primary


def execute(params: dict, inputs: dict) -> dict:
    """
    Fill missing values in time series data.

    Args:
        params: Operator parameters including:
            - method (str, optional): Fill method: linear/ffill/bfill/mean. Default "linear".
            - time_field (str, optional): Timestamp column name. Default "record_time".
            - load_field (str, optional): Target column name. Default "load".
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with no NaN values.
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

    method = params.get("method") or options.get("method") or "linear"
    time_field = params.get("time_field") or options.get("time_field") or "record_time"
    load_field = params.get("load_field") or options.get("load_field") or "load"
    gcfg = params.get("_global_config") or {}

    # drop_insufficient 专用参数
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

    keep_threshold = float(
        params.get("keep_threshold") or options.get("keep_threshold") or 0.75
    )

    valid_methods = {"linear", "ffill", "bfill", "mean", "drop_insufficient"}
    if method not in valid_methods:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Invalid method '{method}'. Must be one of {sorted(valid_methods)}",
        )

    # drop_insufficient: 丢弃数据量不足的组，直接返回，不进入插值逻辑
    if method == "drop_insufficient":
        df = data.copy()
        if df.empty:
            logger.warning(f"[{OPERATOR_ID}] Input DataFrame is empty, returning as-is")
            return {"data": df}
        effective_id_fields = [f for f in id_fields if f in df.columns]
        effective_value_fields = [f for f in value_fields if f in df.columns]
        if not effective_id_fields:
            logger.warning(
                f"[{OPERATOR_ID}] drop_insufficient: id_fields {id_fields} 中无有效列，返回原数据"
            )
            return {"data": df}
        if not effective_value_fields:
            logger.warning(
                f"[{OPERATOR_ID}] drop_insufficient: value_fields {value_fields} 中无有效列，返回原数据"
            )
            return {"data": df}
        before_groups = df.groupby(effective_id_fields).ngroups
        df = _drop_insufficient(df, effective_id_fields, effective_value_fields, keep_threshold)
        after_groups = df.groupby(effective_id_fields).ngroups if not df.empty else 0
        logger.info(
            f"[{OPERATOR_ID}] drop_insufficient: {before_groups} groups -> {after_groups} groups "
            f"(keep_threshold={keep_threshold})"
        )
        return {"data": df}

    df = data.copy()
    resolved_load_field = _pick_target_column(
        df,
        load_field,
        [
            params.get("target_column"),
            options.get("target_column"),
            "value",
            "load",
        ],
    )
    if resolved_load_field != load_field:
        logger.warning(
            f"[{OPERATOR_ID}] 目标列从 '{load_field}' 自动回退为 '{resolved_load_field}'"
        )
        load_field = resolved_load_field

    if df.empty:
        logger.warning(f"[{OPERATOR_ID}] Input DataFrame is empty, returning as-is")
        return {"data": df}

    nan_before = int(df.isna().sum().sum())

    # Ensure time_field is datetime and sorted
    if time_field in df.columns:
        df[time_field] = pd.to_datetime(df[time_field], errors="coerce")
        df = df.sort_values(time_field)

    # Fill target column (load_field)
    if load_field in df.columns:
        df[load_field] = pd.to_numeric(df[load_field], errors="coerce")
        is_backtest = (
            isinstance(gcfg, dict)
            and str(gcfg.get("operate_status", "")).lower() == "backtest"
            and bool(gcfg.get("backtest_mask_target_values", False))
        )
        pred_start_dt = None
        if is_backtest and time_field in df.columns and gcfg.get("backtest_pred_start"):
            pred_start_dt = pd.to_datetime(gcfg.get("backtest_pred_start"), errors="coerce")
            if pd.isna(pred_start_dt):
                logger.warning(
                    f"[{OPERATOR_ID}] backtest_pred_start={gcfg.get('backtest_pred_start')} 解析失败，"
                    "将跳过回测预测窗掩码保护，避免误把全量标签置空"
                )
                pred_start_dt = None
        logger.info(
            f"[{OPERATOR_ID}] 回测检查: is_backtest={is_backtest}, pred_start_dt={pred_start_dt}, "
            f"operate_status={gcfg.get('operate_status')}, mask_target={gcfg.get('backtest_mask_target_values')}, "
            f"pred_start_cfg={gcfg.get('backtest_pred_start')}, time_field_exists={time_field in df.columns}"
        )
        train_mask = None
        if pred_start_dt is not None and time_field in df.columns:
            train_mask = df[time_field] < pred_start_dt

        def _fill_target(series_df: pd.DataFrame) -> pd.Series:
            s = series_df[load_field].copy()
            if method == "linear":
                if time_field in series_df.columns:
                    # IMPORTANT: keep original row index to avoid index-alignment corruption
                    # when assigning back to DataFrame.
                    time_idx = pd.to_datetime(series_df[time_field], errors="coerce")
                    tmp = pd.Series(s.to_numpy(), index=time_idx)
                    try:
                        tmp = tmp.interpolate(method="time", limit_direction="forward")
                    except Exception:
                        # Fallback for invalid/duplicated datetime index scenarios
                        tmp = pd.Series(s.to_numpy()).interpolate(
                            method="linear", limit_direction="forward"
                        )
                    s = pd.Series(tmp.to_numpy(), index=series_df.index)
                else:
                    s = s.interpolate(method="linear", limit_direction="forward")
            elif method == "ffill":
                s = s.ffill()
            elif method == "bfill":
                s = s.bfill()
            elif method == "mean":
                s = s.fillna(s.mean())
            return s.ffill().bfill()

        if train_mask is not None:
            # Only fill training window; keep prediction-day target as NaN to avoid leakage
            train_part = df.loc[train_mask].copy()
            pred_part = df.loc[~train_mask].copy()
            # Preserve true target for evaluation in downstream split/metrics operators.
            helper_target_col = "__backtest_true_target"
            if helper_target_col not in train_part.columns:
                train_part[helper_target_col] = train_part[load_field]
            if helper_target_col not in pred_part.columns:
                pred_part[helper_target_col] = pred_part[load_field]
            logger.info(
                f"[{OPERATOR_ID}] 回测窗口切分: train_rows={len(train_part)}, pred_rows={len(pred_part)}, "
                f"pred_start={pred_start_dt}"
            )
            if not train_part.empty:
                train_part[load_field] = _fill_target(train_part)
            if not pred_part.empty:
                pred_part[load_field] = pd.NA
            df = pd.concat([train_part, pred_part], axis=0).sort_index()
        else:
            df[load_field] = _fill_target(df)

    # Fill non-target columns with ffill/bfill
    for col in df.columns:
        if col in (time_field, load_field):
            continue
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].ffill().bfill()

    nan_after = int(df.isna().sum().sum())
    if load_field in df.columns:
        target_finite = int(pd.to_numeric(df[load_field], errors="coerce").notna().sum())
        logger.info(
            f"[{OPERATOR_ID}] 目标列有效值计数: finite={target_finite}, total={len(df)}"
        )
    logger.info(
        f"[{OPERATOR_ID}] Filled missing values: {nan_before} NaN -> {nan_after} NaN "
        f"(method={method})"
    )

    return {"data": df}
# @AI_GENERATED: end
