# @AI_GENERATED
"""
ts_comparison_features operator backend — Pairwise time series comparison features.

移植自 fault-diag-algo-release-3.1 的 FeatureEngineer.get_compare_features。
对 value_fields 中所有变量按 id_fields 分组后，两两组合计算：
  - Spearman / Pearson 相关系数（可选）
  - 归一化欧氏距离 / DTW 距离（可选）
  - 线性回归斜率（可选）
  - 差值序列统计：max, std, median, absolute_sum_of_changes, sum_values（始终计算）

单变量情况（value_fields 只有 1 个或更少）：跳过所有对比特征，返回空 DataFrame，不报错。
"""
import itertools
import json

import numpy as np
import pandas as pd
from loguru import logger
from scipy.stats import spearmanr, pearsonr
from sklearn.linear_model import LinearRegression
from tsfresh.feature_extraction.feature_calculators import (
    absolute_sum_of_changes,
    sum_values,
)
from tslearn.metrics import dtw

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "ts_comparison_features"


# ---------------------------------------------------------------------------
# 内联工具函数（避免依赖原算法仓库路径）
# ---------------------------------------------------------------------------

def _safe_spearman(s1: pd.Series, s2: pd.Series) -> float:
    """Spearman 相关系数；常量序列返回 0。"""
    if round(float(np.std(s1)), 6) == 0 or round(float(np.std(s2)), 6) == 0:
        return 0.0
    return float(spearmanr(s1, s2)[0])


def _safe_pearson(s1: pd.Series, s2: pd.Series) -> float:
    """Pearson 相关系数；常量序列返回 0。"""
    if round(float(np.std(s1)), 6) == 0 or round(float(np.std(s2)), 6) == 0:
        return 0.0
    return float(pearsonr(s1, s2)[0])


def _normalize(arr: np.ndarray) -> np.ndarray:
    """Min-Max 归一化；常量数组返回全 0。"""
    max_ = arr.max()
    min_ = arr.min()
    return (arr - min_) / (max_ - min_ + 1e-10)


def _euclidean_distance(s1: pd.Series, s2: pd.Series) -> float:
    """归一化后的平均欧氏距离。"""
    a = _normalize(s1.to_numpy(dtype=float))
    b = _normalize(s2.to_numpy(dtype=float))
    dist = np.sqrt(np.sum(np.square(a - b)) / len(a))
    return round(float(dist), 6)


def _linear_slope(s1: pd.Series, s2: pd.Series) -> float:
    """以 s1 为 X、s2 为 y 做线性回归，返回斜率。"""
    lr = LinearRegression()
    lr.fit(s1.to_numpy().reshape(-1, 1), s2.to_numpy().reshape(-1, 1))
    return round(float(lr.coef_[0][0]), 6)


def _parse_list(value, default: list) -> list:
    """将参数解析为列表。"""
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


# ---------------------------------------------------------------------------
# 核心计算
# ---------------------------------------------------------------------------

def _compute_comparison(
    df: pd.DataFrame,
    id_fields: list,
    value_fields: list,
    opts: dict,
) -> pd.DataFrame:
    """
    按 id_fields 分组，对 value_fields 两两配对计算对比特征。

    Args:
        df: 输入 DataFrame，已去除 value_fields 上的 NaN 行。
        id_fields: 分组字段列表（MultiIndex 键）。
        value_fields: 数值列名列表。
        opts: 配置字典，含 compute_correlation / compute_distance / compute_regression。

    Returns:
        DataFrame，行索引为 id_fields 的 MultiIndex，列为对比特征名。
    """
    compute_corr = bool(opts.get("compute_correlation", True))
    compute_dist = bool(opts.get("compute_distance", True))
    compute_reg = bool(opts.get("compute_regression", True))

    combinations = list(itertools.combinations(value_fields, 2))
    groups = df.groupby(id_fields)
    merge_list = []

    for col1, col2 in combinations:
        # 差值列，临时挂在 df 上（按分组统计后不需要持久保留）
        diff_col = f"diff_{col1}_{col2}"
        df[diff_col] = df[col1] - df[col2]

        # --- 差值统计（始终计算） ---
        # 使用字符串 agg 避免 pandas FutureWarning（np.nanmax 等 callable 即将弃用）
        stat_fe = groups[diff_col].agg(["max", "std", "median"])
        stat_fe.columns = [
            f"{diff_col}_nanmax",
            f"{diff_col}_nanstd",
            f"{diff_col}_nanmedian",
        ]
        merge_list.append(stat_fe)

        # tsfresh 差值统计
        tsfresh_fe = groups[diff_col].agg(
            [absolute_sum_of_changes, sum_values]
        )
        tsfresh_fe.columns = [
            f"{diff_col}_absolute_sum_of_changes",
            f"{diff_col}_sum_values",
        ]
        merge_list.append(tsfresh_fe)

        # --- 逐组计算相关/距离/斜率 ---
        # groupby(list) 时 key 始终是元组，即使只有一个字段也是 ("s1",)。
        # 为与 stat_fe/tsfresh_fe 的 Index（字符串 or 多级）对齐，单字段时解包为标量。
        pair_dict: dict = {}
        for key, group in groups:
            row: dict = {}
            g1 = group[col1]
            g2 = group[col2]

            if compute_corr:
                row[f"{col1}_{col2}_spearman"] = _safe_spearman(g1, g2)
                row[f"{col1}_{col2}_pearson_"] = _safe_pearson(g1, g2)

            if compute_dist:
                row[f"{col1}_{col2}_eu_dist"] = _euclidean_distance(g1, g2)
                row[f"{col1}_{col2}_dtw"] = float(
                    dtw(g1.to_numpy().ravel(), g2.to_numpy().ravel())
                )

            if compute_reg:
                row[f"{col1}_{col2}_scope"] = _linear_slope(g1, g2)

            # 单字段时 key 是 ("s1",) -> 解包为 "s1"
            norm_key = key[0] if (isinstance(key, tuple) and len(id_fields) == 1) else key
            pair_dict[norm_key] = row

        if pair_dict:
            keys = list(pair_dict.keys())
            rows = list(pair_dict.values())
            pair_fe = pd.DataFrame(rows, index=pd.Index(keys))
            if len(id_fields) == 1:
                pair_fe.index.name = id_fields[0]
            else:
                pair_fe.index.names = id_fields
            merge_list.append(pair_fe)

        # 清理临时差值列
        df.drop(columns=[diff_col], inplace=True)

    if not merge_list:
        return pd.DataFrame()

    result = pd.concat(merge_list, axis=1)
    result.fillna(0, inplace=True)
    return result


# ---------------------------------------------------------------------------
# 算子入口
# ---------------------------------------------------------------------------

def execute(params: dict, inputs: dict) -> dict:
    """
    Pairwise time series comparison features.

    Args:
        params:
            id_fields (list | str):  分组字段列表（必填）。
            value_fields (list | str): 数值列名列表（必填）。
            options (str | dict):    JSON 配置，支持：
                compute_correlation (bool, default True)   — 计算 Spearman/Pearson
                compute_distance (bool, default True)      — 计算欧氏距离/DTW
                compute_regression (bool, default True)    — 计算线性回归斜率
        inputs:
            data (pd.DataFrame): 含 id_fields 和 value_fields 的时序数据。

    Returns:
        {"data": pd.DataFrame}
            行索引为 id_fields 的 MultiIndex（或单字段 Index），
            列为对比特征名。
            单变量情况直接返回空 DataFrame。
    """
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'data' must be a pandas DataFrame"
        )

    # --- 解析 options ---
    options = params.get("options")
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except json.JSONDecodeError:
            options = {}
    elif not isinstance(options, dict):
        options = {}

    # --- 解析参数 ---
    id_fields = _parse_list(
        params.get("id_fields") or options.get("id_fields"),
        [],
    )
    value_fields = _parse_list(
        params.get("value_fields") or options.get("value_fields"),
        [],
    )

    if not id_fields:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "Parameter 'id_fields' is required and must be non-empty"
        )
    if not value_fields:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "Parameter 'value_fields' is required and must be non-empty"
        )

    # --- 单变量情况：直接返回空 DataFrame，不报错 ---
    if len(value_fields) < 2:
        logger.info(
            f"[{OPERATOR_ID}] Only {len(value_fields)} value field(s), "
            "skipping pairwise comparison and returning empty DataFrame"
        )
        return {"data": pd.DataFrame()}

    df = data.copy()

    # 检查列是否存在
    missing_id = [f for f in id_fields if f not in df.columns]
    if missing_id:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"id_fields not found in DataFrame: {missing_id}. "
            f"Available columns: {list(df.columns)}",
        )
    missing_val = [f for f in value_fields if f not in df.columns]
    if missing_val:
        raise OperatorExecutionError(
            OPERATOR_ID,
            "InputError",
            f"value_fields not found in DataFrame: {missing_val}. "
            f"Available columns: {list(df.columns)}",
        )

    # 去除 value_fields 上有 NaN 的行（与原算法 dropna(how='any') 一致）
    df.dropna(subset=value_fields, how="any", inplace=True)

    if df.empty:
        logger.warning(f"[{OPERATOR_ID}] DataFrame is empty after dropna, returning empty DataFrame")
        return {"data": pd.DataFrame()}

    result = _compute_comparison(df, id_fields, value_fields, options)

    n_rows = len(result)
    n_cols = len(result.columns)
    n_pairs = len(list(itertools.combinations(value_fields, 2)))
    logger.info(
        f"[{OPERATOR_ID}] Computed {n_cols} comparison features "
        f"for {n_rows} groups, {n_pairs} pairs from {len(value_fields)} value fields "
        f"(id_fields={id_fields})"
    )

    return {"data": result}
# @AI_GENERATED: end
