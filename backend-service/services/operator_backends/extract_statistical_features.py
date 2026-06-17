# @AI_GENERATED
"""
extract_statistical_features operator backend — Computes historical period statistics.

Calculates mean/max/min/std over historical periods for the target column.
Reuses logic from add_features.get_stat_features and get_hist_period_statis.
"""
import json

import pandas as pd
from loguru import logger

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "extract_statistical_features"

DEFAULT_PERIOD = 24
DEFAULT_STATISTICS = ["mean", "max", "min", "std"]
SUPPORTED_STATISTICS = {"mean", "max", "min", "std"}


def _parse_list(value, default):
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


def _to_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "on"}
    return bool(v)


def execute(params: dict, inputs: dict) -> dict:
    """
    Compute historical period statistical features on target column.

    Args:
        params: Operator parameters including:
            - target_column (str, optional): Column to compute stats. Default "load".
            - period (int, optional): Period length for grouping. Default 24.
            - statistics (list, optional): Stats to compute. Default ["mean","max","min","std"].
        inputs: {"data": DataFrame}

    Returns:
        {"data": DataFrame} with new statistical feature columns.
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

    target_column = (
        params.get("target_column")
        or options.get("target_column")
        or "load"
    )

    period = params.get("period") or options.get("period")
    if period is not None:
        period = int(period)
    else:
        period = DEFAULT_PERIOD

    statistics = _parse_list(
        params.get("statistics") or options.get("statistics"),
        DEFAULT_STATISTICS,
    )
    mode = str(params.get("mode") or options.get("mode") or "expanding").strip().lower()
    source_column = (
        params.get("source_column")
        or options.get("source_column")
        or target_column
    )
    output_prefix = str(params.get("output_prefix") or options.get("output_prefix") or "").strip()
    group_by = params.get("group_by") or options.get("group_by")
    group_by_from_time = str(
        params.get("group_by_from_time")
        or options.get("group_by_from_time")
        or ""
    ).strip().lower()
    group_shift = int(params.get("group_shift") or options.get("group_shift") or 0)
    time_field = params.get("time_field") or options.get("time_field") or "record_time"
    add_daily_derived = _to_bool(
        params.get("add_daily_derived")
        if params.get("add_daily_derived") is not None
        else options.get("add_daily_derived", False)
    )

    # Validate statistics
    invalid = set(statistics) - SUPPORTED_STATISTICS
    if invalid:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "ParameterError",
            f"Unsupported statistics: {sorted(invalid)}. "
            f"Supported: {sorted(SUPPORTED_STATISTICS)}",
        )

    df = data.copy()

    if df.empty:
        logger.warning(f"[{OPERATOR_ID}] Input DataFrame is empty, returning as-is")
        return {"data": df}

    # groupby_aggregate has its own field handling — bypass the legacy column checks
    if mode == "groupby_aggregate":
        return _execute_groupby_aggregate(params, options, df, OPERATOR_ID)

    if target_column not in df.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"Target column '{target_column}' not found. "
            f"Available columns: {list(df.columns)}",
        )
    if source_column not in df.columns:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"Source column '{source_column}' not found. "
            f"Available columns: {list(df.columns)}",
        )

    if mode == "groupby":
        group_col = None
        if group_by:
            group_col = str(group_by)
        elif group_by_from_time:
            if time_field not in df.columns:
                raise OperatorExecutionError(
                    OPERATOR_ID,
                    "InputError",
                    f"time_field '{time_field}' not found for group_by_from_time",
                )
            ts = pd.to_datetime(df[time_field], errors="coerce")
            if group_by_from_time == "date":
                group_col = "__group_date"
                df[group_col] = ts.dt.strftime("%Y-%m-%d")
            elif group_by_from_time == "month":
                group_col = "__group_month"
                df[group_col] = ts.dt.strftime("%Y-%m")
            elif group_by_from_time == "week":
                group_col = "__group_week"
                iso = ts.dt.isocalendar()
                df[group_col] = iso.year.astype(str) + "-W" + iso.week.astype(str)
            else:
                raise OperatorExecutionError(
                    OPERATOR_ID,
                    "ParameterError",
                    f"Unsupported group_by_from_time '{group_by_from_time}'",
                )
        else:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "ParameterError",
                "mode='groupby' requires group_by or group_by_from_time",
            )

        if group_col not in df.columns:
            raise OperatorExecutionError(
                OPERATOR_ID,
                "InputError",
                f"group column '{group_col}' not found",
            )
        agg = (
            df.groupby(group_col, dropna=False)[source_column]
            .agg(statistics)
            .reset_index()
        )
        if group_shift != 0:
            agg = agg.sort_values(group_col).reset_index(drop=True)
            for stat in statistics:
                agg[stat] = agg[stat].shift(group_shift)
        base_prefix = output_prefix or (
            "day" if (group_by_from_time == "date" and source_column == target_column) else source_column
        )
        rename_map = {stat: f"{base_prefix}_{stat}" for stat in statistics}
        agg = agg.rename(columns=rename_map)
        new_cols = len(statistics)

        if (
            add_daily_derived
            and f"{base_prefix}_max" in agg.columns
            and f"{base_prefix}_min" in agg.columns
        ):
            max_col = f"{base_prefix}_max"
            min_col = f"{base_prefix}_min"
            mean_col = f"{base_prefix}_mean"
            agg[f"{base_prefix}_pv"] = agg[max_col] - agg[min_col]
            agg[f"{base_prefix}_pv_rate"] = agg[f"{base_prefix}_pv"] / agg[max_col].replace(0, pd.NA)
            if mean_col in agg.columns:
                agg[f"{base_prefix}_rate"] = agg[mean_col] / agg[max_col].replace(0, pd.NA)
            new_cols += 2 + (1 if mean_col in agg.columns else 0)

        merge_cols = [group_col] + [c for c in agg.columns if c != group_col]
        df = df.merge(agg[merge_cols], on=group_col, how="left")
        if group_col.startswith("__group_"):
            df = df.drop(columns=[group_col], errors="ignore")
        logger.info(
            f"[{OPERATOR_ID}] Added {new_cols} group statistical columns "
            f"(mode=groupby, group_col={group_col}, source={source_column}, stats={statistics}, "
            f"group_shift={group_shift}, output_prefix={output_prefix or base_prefix})"
        )
        return {"data": df}

    # Legacy expanding mode: keeps backward compatibility
    shifted = df[source_column].shift(1)
    expanding = shifted.expanding(min_periods=1)
    new_cols = 0
    base_prefix = output_prefix or source_column
    for stat in statistics:
        col_name = f"{base_prefix}_hist_{stat}"
        if stat == "mean":
            df[col_name] = expanding.mean()
        elif stat == "max":
            df[col_name] = expanding.max()
        elif stat == "min":
            df[col_name] = expanding.min()
        elif stat == "std":
            df[col_name] = expanding.std()
        new_cols += 1

    logger.info(
        f"[{OPERATOR_ID}] Added {new_cols} historical statistical columns "
        f"(mode=expanding, period={period}, stats={statistics}, target={target_column}, source={source_column})"
    )

    return {"data": df}
# @AI_GENERATED: end


# ---------------------------------------------------------------------------
# groupby_aggregate mode — ported from fault-diag-algo-release-3.1
# ---------------------------------------------------------------------------
# Inlined utility functions (prefixed _fa_ to avoid naming collisions)
# Source: enos_fault_diag/features/utils/

import numpy as np
from scipy.stats import kurtosis as _scipy_kurtosis, skew as _scipy_skew

try:
    from tsfresh.feature_extraction.feature_calculators import (
        autocorrelation as _tsfresh_autocorrelation,
        count_above_mean as _tsfresh_count_above_mean,
    )
    _TSFRESH_AVAILABLE = True
except ImportError:
    _TSFRESH_AVAILABLE = False
    logger.warning("[extract_statistical_features] tsfresh not available; autocorrelation/above_mean_ratio will be skipped")


# --- inlined from features/utils/statistics.py ---

def _fa_above_mean_ratio(arr):
    """均值以上样本占比 (above_mean_ratio)"""
    if not _TSFRESH_AVAILABLE or len(arr) == 0:
        return 0.0
    return _tsfresh_count_above_mean(arr) / len(arr)


def _fa_max_min(arr):
    """极差 (max - min)"""
    return np.nanmax(arr) - np.nanmin(arr)


# --- inlined from features/utils/variation_coefficient.py ---

def _fa_variation_coefficient(arr):
    """变异系数 (std / mean)"""
    m = np.nanmean(arr)
    return np.nanstd(arr) / m if m != 0 else 0.0


# --- inlined from features/utils/correlation.py ---

def _fa_autocorrelation_1(arr):
    """滞后-1 自相关"""
    if not _TSFRESH_AVAILABLE:
        return 0.0
    return _tsfresh_autocorrelation(arr, 1)


def _fa_autocorrelation_2(arr):
    """滞后-2 自相关"""
    if not _TSFRESH_AVAILABLE:
        return 0.0
    return _tsfresh_autocorrelation(arr, 2)


def _fa_autocorrelation_3(arr):
    """滞后-3 自相关"""
    if not _TSFRESH_AVAILABLE:
        return 0.0
    return _tsfresh_autocorrelation(arr, 3)


# --- inlined from features/utils/fluctuation.py ---

def _fa_gradient(data):
    """计算梯度数组 (相邻差分)"""
    if len(data) < 2:
        return np.array(data, dtype=float)
    arr = np.array(data, dtype=float)
    return np.round(arr[1:] - arr[:-1], 3)


def _fa_flat_features(arr, tag):
    """
    波动/平坦特征 — 移植自 fluctuation.get_features
    返回 dict: {tag_flat_rate, tag_flat_max, tag_flat_count, tag_max_drop}
    """
    arr = np.array(arr, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return {
            f"{tag}_flat_rate": 0.0,
            f"{tag}_flat_max": 0,
            f"{tag}_flat_count": 0,
            f"{tag}_max_drop": 0.0,
        }
    grad = _fa_gradient(arr)
    flat_count_pts = int(np.sum(grad == 0))
    flat_rate = round(flat_count_pts / len(arr), 6)
    max_drop = float(np.max(np.abs(grad)))

    count = 0
    flat_area = []
    for i in range(len(grad)):
        if grad[i] == 0:
            count += 1
        if (grad[i] != 0 or i == len(grad) - 1) and count > 0:
            flat_area.append(count)
            count = 0

    flat_max = max(flat_area) if flat_area else 0

    return {
        f"{tag}_flat_rate": flat_rate,
        f"{tag}_flat_max": flat_max,
        f"{tag}_flat_count": len(flat_area),
        f"{tag}_max_drop": max_drop,
    }


# --- helper: groupby aggregate for a list of scalar functions ---

def _fa_groupby_scalar(groups, value_cols, func_list):
    """
    对 groups[value_cols] 每列应用 func_list 中每个函数，
    返回 DataFrame，列名格式：{col}_{func.__name__}

    逐函数聚合然后水平拼接，避免 pandas 多函数 agg 的列名歧义问题。
    """
    func_defs = [(fn, getattr(fn, "__name__", str(fn))) for fn in func_list]
    return _fa_groupby_named(groups, value_cols, func_defs)


def _fa_groupby_named(groups, value_cols, func_defs):
    """
    对 groups[value_cols] 每列应用 func_defs 中 (fn, alias) 对，
    返回 DataFrame，列名格式：{col}_{alias}
    """
    result_frames = []
    for fn, alias in func_defs:
        col_fe = groups[value_cols].agg(fn)
        if isinstance(col_fe, pd.DataFrame):
            col_fe.columns = [f"{col}_{alias}" for col in col_fe.columns]
        else:
            col_fe = col_fe.rename(f"{value_cols}_{alias}")
        result_frames.append(col_fe)
    fe_df = pd.concat(result_frames, axis=1)
    return fe_df.round(6)


# --- main groupby_aggregate implementation ---

def _execute_groupby_aggregate(params: dict, options: dict, df: pd.DataFrame, operator_id: str) -> dict:
    """
    groupby_aggregate mode:
    输入宽表（多设备×多时间行），按 id_fields 分组，
    提取统计/分位数/自相关/平坦性特征，
    输出 MATRIX：每行=一个分组（设备×窗口），列=所有特征，fillna(0)。
    """
    # --- 参数解析 ---
    id_fields = _parse_list(
        params.get("id_fields") or options.get("id_fields"), []
    )
    value_fields = _parse_list(
        params.get("value_fields") or options.get("value_fields"), []
    )
    compute_diff = _to_bool(
        params.get("compute_diff") if params.get("compute_diff") is not None
        else options.get("compute_diff", True),
        default=True,
    )
    quantiles = params.get("quantiles") or options.get("quantiles") or [0.15, 0.25, 0.35, 0.65, 0.75, 0.85, 0.95]
    if isinstance(quantiles, str):
        try:
            quantiles = json.loads(quantiles)
        except json.JSONDecodeError:
            quantiles = [0.15, 0.25, 0.35, 0.65, 0.75, 0.85, 0.95]

    # 自动检测 id_fields：过滤掉不在 df 中的列
    actual_id_fields = [f for f in id_fields if f in df.columns]
    if not actual_id_fields:
        raise OperatorExecutionError(
            operator_id,
            "ParameterError",
            f"None of id_fields {id_fields} found in DataFrame columns: {list(df.columns)}",
        )

    # 自动检测 value_fields：如未指定则取所有非 id 数值列
    if not value_fields:
        value_fields = [
            c for c in df.columns
            if c not in actual_id_fields and pd.api.types.is_numeric_dtype(df[c])
        ]
    else:
        value_fields = [f for f in value_fields if f in df.columns]

    if not value_fields:
        raise OperatorExecutionError(
            operator_id,
            "ParameterError",
            "No valid value_fields found in DataFrame",
        )

    # 删除 value_fields 全部为 NaN 的行
    data = df.dropna(subset=value_fields, how="all").copy()
    if data.empty:
        logger.warning(f"[{operator_id}] groupby_aggregate: all rows dropped after dropna, returning empty DataFrame")
        return {"data": data}

    groups = data.groupby(actual_id_fields)

    merge_list = []

    # ── 1. 基础统计 ──────────────────────────────────────────────────────────
    # 基础统计函数，配名称别名
    _basic_func_defs = [
        (np.nanmax,                 "max"),
        (np.nanmin,                 "min"),
        (np.nanmean,                "mean"),
        (np.nanmedian,              "median"),
        (np.nanstd,                 "std"),
        (_scipy_kurtosis,           "kurtosis"),
        (_scipy_skew,               "skew"),
        (_fa_max_min,               "max_min"),
        (_fa_above_mean_ratio,      "above_mean_ratio"),
        (_fa_variation_coefficient, "variation_coef"),
    ]
    basic_fe = _fa_groupby_named(groups, value_fields, _basic_func_defs).reset_index()
    merge_list.append(basic_fe)

    # ── 2. 分位数（avg_count >= 48 才计算）────────────────────────────────────
    avg_count = groups[value_fields].count().mean().mean()
    if avg_count >= 48:
        q_agg_funcs = [
            (lambda x, q=q: np.nanquantile(x.dropna(), q)) for q in quantiles
        ]
        # 手动命名，避免 lambda 名称都叫 <lambda>
        for i, q in enumerate(quantiles):
            q_agg_funcs[i].__name__ = f"quantile_{int(round(q * 100))}"
        q_fe = _fa_groupby_scalar(groups, value_fields, q_agg_funcs).reset_index()
        merge_list.append(q_fe)

    # ── 3. 自相关 lag-1/2/3 ──────────────────────────────────────────────────
    if _TSFRESH_AVAILABLE:
        autocorr_fe = _fa_groupby_named(
            groups, value_fields,
            [(_fa_autocorrelation_1, "autocorr_lag1"),
             (_fa_autocorrelation_2, "autocorr_lag2"),
             (_fa_autocorrelation_3, "autocorr_lag3")],
        ).reset_index()
        merge_list.append(autocorr_fe)

    # ── 4. 波动/平坦特征 ─────────────────────────────────────────────────────
    flat_rows = []
    for key, group in groups:
        row = {}
        # id_fields 值
        if len(actual_id_fields) == 1:
            row[actual_id_fields[0]] = key
        else:
            for field, val in zip(actual_id_fields, key):
                row[field] = val
        for col in value_fields:
            row.update(_fa_flat_features(group[col].values, tag=col))
        flat_rows.append(row)

    if flat_rows:
        flat_fe = pd.DataFrame(flat_rows)
        merge_list.append(flat_fe)

    # ── 5. compute_diff：对差分数据重复计算基础统计 ───────────────────────────
    if compute_diff:
        diff_data = data.copy()
        diff_cols = []
        for col in value_fields:
            diff_col = f"{col}_diff"
            diff_data[diff_col] = diff_data.groupby(actual_id_fields)[col].diff()
            diff_cols.append(diff_col)

        diff_groups = diff_data.dropna(subset=diff_cols, how="all").groupby(actual_id_fields)
        diff_basic_fe = _fa_groupby_named(diff_groups, diff_cols, _basic_func_defs).reset_index()
        merge_list.append(diff_basic_fe)

    # ── 6. 合并所有特征：以 actual_id_fields 为 key 逐个 merge，fillna(0) ────
    result = merge_list[0]
    for fe in merge_list[1:]:
        # 只保留 id 列 + 新特征列（避免重复 id 列）
        new_cols = actual_id_fields + [c for c in fe.columns if c not in result.columns]
        result = result.merge(fe[new_cols], on=actual_id_fields, how="left")
    result = result.fillna(0)

    logger.info(
        f"[{operator_id}] groupby_aggregate: "
        f"groups={len(result)}, features={len(result.columns)}, "
        f"id_fields={actual_id_fields}, value_fields={value_fields}, "
        f"avg_count={avg_count:.1f}, compute_diff={compute_diff}"
    )

    return {"data": result}
