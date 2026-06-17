# @AI_GENERATED
"""
row_filter operator backend — Filters DataFrame rows by conditions.

Supports column_filters (exact match dict) and expression (pandas query string).
Preserves original column structure.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "row_filter"


def execute(params: dict, inputs: dict) -> dict:
    """
    Filter rows of an input DataFrame.

    Args:
        params: Operator parameters including:
            - column_filters (dict, optional): {column_name: value} exact match
            - expression (str, optional): pandas query expression string
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame (filtered, preserving original columns)}
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    df = data.copy()
    original_columns = list(df.columns)

    # Parse options if provided as JSON string
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    # column_filters from params or options
    column_filters = params.get("column_filters") or options.get("column_filters")
    expression = params.get("expression") or options.get("expression")

    if isinstance(column_filters, str):
        try:
            column_filters = json.loads(column_filters)
        except json.JSONDecodeError:
            column_filters = None

    rows_before = len(df)

    # Apply column_filters (exact match)
    if column_filters and isinstance(column_filters, dict):
        for col, val in column_filters.items():
            if col in df.columns:
                df = df[df[col] == val]

    # Apply expression (pandas query)
    if expression and isinstance(expression, str):
        try:
            df = df.query(expression)
        except Exception as e:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "ExpressionError",
                f"Failed to evaluate filter expression '{expression}': {e}",
            )

    # Backtest rolling window clamp + future-target masking (no leakage)
    gcfg = params.get("_global_config") or {}
    if (
        isinstance(gcfg, dict)
        and str(gcfg.get("operate_status", "")).lower() == "backtest"
        and "record_time" in df.columns
    ):
        try:
            apply_window = bool(gcfg.get("backtest_apply_window_filter", False))
            apply_mask = bool(gcfg.get("backtest_mask_target_values", False))
            ts = pd.to_datetime(df["record_time"], errors="coerce")
            start_s = gcfg.get("backtest_train_start")
            end_s = gcfg.get("backtest_pred_end")
            train_end_s = gcfg.get("backtest_train_end")
            pred_start_s = gcfg.get("backtest_pred_start")
            if apply_window and start_s:
                start_dt = pd.to_datetime(start_s, errors="coerce")
                df = df[ts >= start_dt]
                ts = pd.to_datetime(df["record_time"], errors="coerce")
            if apply_window and end_s:
                end_dt = pd.to_datetime(end_s, errors="coerce")
                df = df[ts < end_dt]
                ts = pd.to_datetime(df["record_time"], errors="coerce")
            strict_alignment = bool(gcfg.get("strict_alignment_mode", False))
            exclude_gap = gcfg.get("backtest_exclude_gap_from_features")
            if exclude_gap is None:
                exclude_gap = strict_alignment
            if apply_window and exclude_gap and train_end_s and pred_start_s:
                train_end_dt = pd.to_datetime(train_end_s, errors="coerce")
                pred_start_dt_for_gap = pd.to_datetime(pred_start_s, errors="coerce")
                if not pd.isna(train_end_dt) and not pd.isna(pred_start_dt_for_gap):
                    keep_mask = (ts <= train_end_dt) | (ts >= pred_start_dt_for_gap)
                    removed = int((~keep_mask).sum())
                    if removed > 0:
                        df = df[keep_mask]
                        ts = pd.to_datetime(df["record_time"], errors="coerce")
                        logger.info(
                            f"[row_filter] 严格对齐：已从特征工程输入中移除 gap 区间 {removed} 行 "
                            f"({train_end_s} ~ {pred_start_s})"
                        )
            # Align with local rolling backtest: mask prediction-day true load before feature engineering
            target_col = params.get("target_column") or options.get("target_column") or params.get("load_field") or options.get("load_field") or "load"
            # 自动回退：如果指定的 target_col 不在 df 中，尝试 "value" 和 "load"
            if target_col not in df.columns:
                for fallback in ("value", "load"):
                    if fallback in df.columns:
                        target_col = fallback
                        break
            logger.info(
                f"[row_filter] 回测遮蔽: apply_mask={apply_mask}, target_col={target_col}, "
                f"pred_start={pred_start_s}, col_exists={target_col in df.columns}, "
                f"columns={list(df.columns)[:10]}"
            )
            if apply_mask and pred_start_s and target_col in df.columns:
                pred_start_dt = pd.to_datetime(pred_start_s, errors="coerce")
                helper_col = "__backtest_true_target"
                if helper_col not in df.columns:
                    df[helper_col] = df[target_col].copy()
                # 是否实际遮蔽 value 列（默认 True；设为 False 时只创建 helper 不遮蔽）
                do_mask = params.get("mask_value_column", True)
                if isinstance(do_mask, str):
                    do_mask = do_mask.lower() not in ("false", "0", "no", "off")
                if do_mask:
                    # 重新计算 ts（窗口过滤后 df 可能已变）并 reset index 确保对齐
                    df = df.reset_index(drop=True)
                    ts_fresh = pd.to_datetime(df["record_time"], errors="coerce")
                    mask_pred = ts_fresh >= pred_start_dt
                    mask_count = int(mask_pred.sum())
                    df.loc[mask_pred, target_col] = pd.NA
                    logger.info(
                        f"[row_filter] 已遮蔽 {mask_count} 行的 '{target_col}' 列 (pred_start={pred_start_s})"
                    )
                else:
                    logger.info(
                        f"[row_filter] mask_value_column=False，不遮蔽 '{target_col}'，"
                        f"仅创建 '{helper_col}' 供下游 split 使用"
                    )
        except Exception as e:
            logger.error(f"[row_filter] 回测遮蔽异常: {e}")

    # Preserve original column structure
    keep_columns = list(original_columns)
    if "__backtest_true_target" in df.columns and "__backtest_true_target" not in keep_columns:
        keep_columns.append("__backtest_true_target")
    df = df[keep_columns].reset_index(drop=True)

    logger.info(
        f"[row_filter] Filtered {rows_before} -> {len(df)} rows"
    )
    return {"data": df}
# @AI_GENERATED: end
