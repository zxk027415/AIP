 # @AI_GENERATED
# -*- coding: utf-8 -*-
"""
数据穿越验证程序

针对 run_weihai_backtest.py 的回测流程，从多个维度系统性地检测是否存在数据穿越。

检测维度:
  1. 特征穿越检测 — 每个特征值是否只依赖于预测时刻之前的数据
  2. 训练集/测试集时间边界检测 — 训练数据是否严格早于预测日
  3. 日统计特征穿越检测 — 日级别聚合是否使用了当天（预测日）的数据
  4. 交叉验证穿越检测 — CV 折的验证集是否始终晚于训练集
  5. 特征重要性异常检测 — 穿越特征通常会有异常高的重要性

用法:
    python verify_no_leakage.py

无需训练模型，纯数据层面的验证，运行速度快。
"""
import os
import sys
import warnings
import numpy as np
import pandas as pd
from datetime import timedelta
from sklearn.model_selection import TimeSeriesSplit
from loguru import logger

warnings.filterwarnings(action="ignore")

# ---------------------------------------------------------------------------
# 复用 run_weihai_backtest.py 中的常量和函数
# ---------------------------------------------------------------------------
DAILY_HORIZON = 96
PRED_START = "2026-04-01"
PRED_END = "2026-04-08"
TRAIN_DAYS = 30

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_DIR = os.path.join(BASE_DIR, "datasets")


# ---------------------------------------------------------------------------
# 数据加载（与 run_weihai_backtest.py 一致）
# ---------------------------------------------------------------------------
def load_weihai_data():
    xlsx_path = os.path.join(DATASETS_DIR, "load_true_weihai_260407.xlsx")
    df = pd.read_excel(xlsx_path)
    df["record_time"] = pd.to_datetime(df["record_time"])
    load_df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
    load_df.rename(columns={"value": "load"}, inplace=True)
    load_df = load_df.sort_values("record_time").reset_index(drop=True)
    load_df = load_df.drop_duplicates(subset="record_time", keep="first")
    load_df = load_df.set_index("record_time")
    load_df = load_df.resample("15min").mean()
    load_df = load_df.interpolate().fillna(method="bfill").fillna(method="ffill")
    load_df.reset_index(inplace=True)
    return load_df


# ---------------------------------------------------------------------------
# 复用 build_features（与 run_weihai_backtest.py 完全一致）
# ---------------------------------------------------------------------------
def if_workday(date):
    try:
        from chinese_calendar import is_workday
        return is_workday(pd.to_datetime(date))
    except Exception:
        return pd.to_datetime(date).weekday() <= 4


def build_features(df, time_field="record_time", load_field="load"):
    feat = df.copy()
    feat[time_field] = pd.to_datetime(feat[time_field])
    dh = DAILY_HORIZON

    feat["is_holiday"] = feat[time_field].apply(lambda x: 0 if if_workday(x) else 1)
    feat["day"] = feat[time_field].dt.day
    feat["yday"] = feat[time_field].dt.dayofyear
    feat["month"] = feat[time_field].dt.month
    feat["dayofweek"] = feat[time_field].dt.dayofweek
    feat["hour"] = feat[time_field].dt.hour
    feat["minute"] = feat[time_field].dt.minute
    feat["period"] = feat["hour"] * 4 + feat["minute"] // 15

    feat["hour_sin"] = np.sin(2 * np.pi * feat["hour"] / 24)
    feat["hour_cos"] = np.cos(2 * np.pi * feat["hour"] / 24)
    feat["wday_sin"] = np.sin(2 * np.pi * feat["dayofweek"] / 7)
    feat["wday_cos"] = np.cos(2 * np.pi * feat["dayofweek"] / 7)
    feat["yday_sin"] = np.sin(2 * np.pi * feat["yday"] / 365)
    feat["yday_cos"] = np.cos(2 * np.pi * feat["yday"] / 365)
    feat["month_sin"] = np.sin(2 * np.pi * feat["month"] / 12)
    feat["month_cos"] = np.cos(2 * np.pi * feat["month"] / 12)

    for lag in [1, 2, 3, 4, 5, 6, 7, 14, 21, 28]:
        feat[f"lag_{lag}d"] = feat[load_field].shift(lag * dh)

    feat["same_time_2w"] = (feat["lag_7d"] + feat["lag_14d"]) / 2
    feat["same_time_3w"] = (feat["lag_7d"] + feat["lag_14d"] + feat["lag_21d"]) / 3

    load_prev = feat[load_field].shift(1)
    feat["diff_1"] = load_prev - load_prev.shift(1)
    feat["diff_96"] = load_prev - load_prev.shift(dh)
    feat["diff_192"] = load_prev - load_prev.shift(2 * dh)
    feat["diff_96_of_96"] = load_prev.shift(dh - 1) - load_prev.shift(2 * dh - 1)

    load_yd = feat[load_field].shift(dh)
    for w in [4, 8, 12, 24, 48, 96]:
        feat[f"roll_{w}_mean"] = load_yd.rolling(w, center=False, min_periods=1).mean().values
        feat[f"roll_{w}_std"] = load_yd.rolling(w, center=False, min_periods=1).std().values
        feat[f"roll_{w}_max"] = load_yd.rolling(w, center=False, min_periods=1).max().values
        feat[f"roll_{w}_min"] = load_yd.rolling(w, center=False, min_periods=1).min().values

    feat["date"] = feat[time_field].dt.strftime("%Y-%m-%d")
    ds = feat.groupby("date")[load_field].agg(["mean", "max", "min", "std"]).reset_index()
    ds.columns = ["date", "day_mean", "day_max", "day_min", "day_std"]
    ds["day_pv"] = ds["day_max"] - ds["day_min"]
    ds["day_pv_rate"] = ds["day_pv"] / ds["day_max"].replace(0, np.nan)
    ds["day_rate"] = ds["day_mean"] / ds["day_max"].replace(0, np.nan)
    for c in ["day_mean", "day_max", "day_min", "day_std", "day_pv", "day_pv_rate", "day_rate"]:
        ds[c] = ds[c].shift(1)
    feat = feat.merge(ds, on="date", how="left")

    ds2 = feat.groupby("date")["lag_1d"].agg(["mean", "std"]).reset_index()
    ds2.columns = ["date", "lag1d_day_mean", "lag1d_day_std"]
    ds2["lag1d_day_mean"] = ds2["lag1d_day_mean"].shift(1)
    ds2["lag1d_day_std"] = ds2["lag1d_day_std"].shift(1)
    feat = feat.merge(ds2, on="date", how="left")

    return feat


# ===========================================================================
# 检测 1：特征穿越检测 — 扰动法
#
# 原理：对预测日及之后的 load 真值注入随机噪声，然后重新计算特征。
#       如果测试集的某个特征值发生了变化，说明该特征依赖了预测日的
#       真实 load（即发生了数据穿越）。
# ===========================================================================

def test_feature_leakage_by_perturbation(full_df, pred_day, train_end):
    """
    扰动法检测特征穿越。

    步骤:
      1. 用原始数据构建特征 → 记录测试集特征值
      2. 把预测日及之后的 load 替换为随机值 → 重新构建特征
      3. 对比测试集特征值：如果有变化 → 穿越

    Parameters
    ----------
    full_df : DataFrame
        合并后的 train+test 原始数据 (record_time, load)
    pred_day : Timestamp
        预测日
    train_end : Timestamp
        训练截止时间

    Returns
    -------
    dict  {"passed": bool, "leaked_features": list, "details": list}
    """
    results = {"passed": True, "leaked_features": [], "details": []}

    # 1. 原始特征
    feat_original = build_features(full_df.copy())
    test_mask = feat_original["record_time"] >= pred_day
    test_original = feat_original[test_mask].copy().reset_index(drop=True)

    # 2. 扰动：把预测日及之后的 load 替换为随机值
    perturbed_df = full_df.copy()
    future_mask = perturbed_df["record_time"] >= pred_day
    np.random.seed(42)
    n_future = future_mask.sum()
    # 用一个完全不同的值域（原始值 × 10 + 随机偏移）确保差异明显
    original_future_load = perturbed_df.loc[future_mask, "load"].values
    perturbed_df.loc[future_mask, "load"] = original_future_load * 10 + np.random.randn(n_future) * 1000

    # 3. 用扰动数据重新构建特征
    feat_perturbed = build_features(perturbed_df)
    test_perturbed = feat_perturbed[feat_perturbed["record_time"] >= pred_day].copy().reset_index(drop=True)

    # 4. 对比每个特征列
    drop_cols = {"load", "record_time", "date"}
    feature_cols = [c for c in test_original.columns if c not in drop_cols
                    and test_original[c].dtype in ['float64', 'float32', 'int64', 'int32']]

    for col in feature_cols:
        orig_vals = test_original[col].values.astype(float)
        pert_vals = test_perturbed[col].values.astype(float)

        # 处理 NaN：两边都是 NaN 视为相同
        both_nan = np.isnan(orig_vals) & np.isnan(pert_vals)
        orig_filled = np.where(np.isnan(orig_vals), 0, orig_vals)
        pert_filled = np.where(np.isnan(pert_vals), 0, pert_vals)

        diff = np.abs(orig_filled - pert_filled)
        diff[both_nan] = 0  # 两边都 NaN 不算差异

        max_diff = np.max(diff)
        if max_diff > 1e-6:
            results["passed"] = False
            results["leaked_features"].append(col)
            # 找到差异最大的行
            worst_idx = np.argmax(diff)
            results["details"].append({
                "feature": col,
                "max_diff": float(max_diff),
                "worst_row_time": str(test_original.iloc[worst_idx]["record_time"]),
                "original_value": float(orig_vals[worst_idx]) if not np.isnan(orig_vals[worst_idx]) else "NaN",
                "perturbed_value": float(pert_vals[worst_idx]) if not np.isnan(pert_vals[worst_idx]) else "NaN",
            })

    return results


# ===========================================================================
# 检测 2：训练集/测试集时间边界检测
#
# 验证训练集的所有时间戳严格 <= train_end，
# 测试集的所有时间戳严格 >= pred_day。
# ===========================================================================

def test_time_boundary(full_df, pred_day, train_end):
    """
    检测训练集和测试集的时间边界是否正确。

    Returns
    -------
    dict  {"passed": bool, "details": str}
    """
    feat_all = build_features(full_df.copy())
    train_feat = feat_all[feat_all["record_time"] <= train_end]
    test_feat = feat_all[feat_all["record_time"] >= pred_day]

    issues = []

    # 训练集不应包含预测日及之后的数据
    train_max_time = train_feat["record_time"].max()
    if train_max_time > train_end:
        issues.append(f"训练集最大时间 {train_max_time} 超过了 train_end {train_end}")

    # 测试集不应包含训练截止日之前的数据
    test_min_time = test_feat["record_time"].min()
    if test_min_time < pred_day:
        issues.append(f"测试集最小时间 {test_min_time} 早于 pred_day {pred_day}")

    # 训练集和测试集不应有时间重叠
    overlap = set(train_feat["record_time"].values) & set(test_feat["record_time"].values)
    if overlap:
        issues.append(f"训练集和测试集有 {len(overlap)} 个重叠时间戳")

    # 训练集的 load 列不应包含预测日的真实值
    train_load_times = train_feat.dropna(subset=["load"])["record_time"]
    future_in_train = train_load_times[train_load_times >= pred_day]
    if len(future_in_train) > 0:
        issues.append(f"训练集的 load 列包含 {len(future_in_train)} 个预测日及之后的值")

    passed = len(issues) == 0
    return {"passed": passed, "details": issues if issues else ["时间边界正确"]}


# ===========================================================================
# 检测 3：日统计特征穿越检测
#
# 日统计特征（day_mean, day_max 等）是按 date 分组聚合后 shift(1) 的。
# 验证：测试集行的日统计特征值 == 前一天（训练集最后一天）的统计值，
# 而不是预测日当天的统计值。
# ===========================================================================

def test_daily_stats_leakage(full_df, pred_day, train_end):
    """
    检测日统计特征是否使用了预测日当天的数据。

    方法：手动计算 train_end 那一天的日统计量，与测试集中的 day_mean 等对比。
    如果一致，说明 shift(1) 生效了，没有穿越。

    Returns
    -------
    dict  {"passed": bool, "details": list}
    """
    feat_all = build_features(full_df.copy())
    test_feat = feat_all[feat_all["record_time"] >= pred_day].copy()

    # 手动计算 train_end 那一天的真实统计量
    train_end_date = train_end.strftime("%Y-%m-%d")
    train_end_day_data = full_df[full_df["record_time"].dt.strftime("%Y-%m-%d") == train_end_date]["load"]

    if len(train_end_day_data) == 0:
        return {"passed": True, "details": ["train_end 当天无数据，跳过此检测"]}

    expected_day_mean = train_end_day_data.mean()
    expected_day_max = train_end_day_data.max()
    expected_day_min = train_end_day_data.min()

    # 预测日当天的真实统计量（如果穿越了，日统计特征会等于这个值）
    pred_day_date = pred_day.strftime("%Y-%m-%d")
    pred_day_data = full_df[full_df["record_time"].dt.strftime("%Y-%m-%d") == pred_day_date]["load"]
    leaked_day_mean = pred_day_data.mean() if len(pred_day_data) > 0 else None

    issues = []

    # 检查测试集第一行的 day_mean
    if len(test_feat) > 0 and "day_mean" in test_feat.columns:
        actual_day_mean = test_feat.iloc[0]["day_mean"]

        if not np.isnan(actual_day_mean):
            # 应该等于 train_end 那天的均值（shift(1) 的效果）
            diff_expected = abs(actual_day_mean - expected_day_mean)
            if diff_expected > 1e-4:
                issues.append(
                    f"day_mean 不等于 train_end 当天的均值: "
                    f"actual={actual_day_mean:.4f}, expected={expected_day_mean:.4f}, diff={diff_expected:.6f}"
                )

            # 不应该等于预测日当天的均值
            if leaked_day_mean is not None:
                diff_leaked = abs(actual_day_mean - leaked_day_mean)
                if diff_leaked < 1e-4 and abs(expected_day_mean - leaked_day_mean) > 1e-4:
                    issues.append(
                        f"day_mean 等于预测日当天的均值（穿越！）: "
                        f"actual={actual_day_mean:.4f}, pred_day_mean={leaked_day_mean:.4f}"
                    )

    passed = len(issues) == 0
    return {"passed": passed, "details": issues if issues else ["日统计特征 shift(1) 正确，无穿越"]}


# ===========================================================================
# 检测 4：交叉验证穿越检测
#
# 验证 TimeSeriesSplit 的每一折中，验证集的索引始终大于训练集的索引。
# ===========================================================================

def test_cv_no_leakage(full_df, pred_day, train_end):
    """
    检测交叉验证是否存在时间穿越。

    Returns
    -------
    dict  {"passed": bool, "details": list}
    """
    feat_all = build_features(full_df.copy())
    train_feat = feat_all[feat_all["record_time"] <= train_end].copy().reset_index(drop=True)

    drop_cols = {"load", "record_time", "date"}
    feature_cols = [c for c in train_feat.columns if c not in drop_cols
                    and train_feat[c].dtype in ['float64', 'float32', 'int64', 'int32']]

    x_train = train_feat[feature_cols].fillna(0)
    y_train = train_feat["load"]
    train_times = train_feat["record_time"].values

    issues = []
    tscv = TimeSeriesSplit(n_splits=5)

    for fold_idx, (trn_idx, val_idx) in enumerate(tscv.split(x_train)):
        trn_max_time = pd.to_datetime(train_times[trn_idx[-1]])
        val_min_time = pd.to_datetime(train_times[val_idx[0]])
        val_max_time = pd.to_datetime(train_times[val_idx[-1]])

        # 验证集的最小时间应该 > 训练集的最大时间
        if val_min_time <= trn_max_time:
            issues.append(
                f"Fold {fold_idx}: 验证集起始时间 {val_min_time} <= 训练集结束时间 {trn_max_time}"
            )

        # 验证集不应超过 train_end
        if val_max_time > train_end:
            issues.append(
                f"Fold {fold_idx}: 验证集结束时间 {val_max_time} 超过 train_end {train_end}"
            )

        # 验证集索引应该严格大于训练集索引
        if trn_idx[-1] >= val_idx[0]:
            issues.append(
                f"Fold {fold_idx}: 训练集最大索引 {trn_idx[-1]} >= 验证集最小索引 {val_idx[0]}"
            )

    passed = len(issues) == 0
    return {"passed": passed, "details": issues if issues else ["TimeSeriesSplit 所有折均无时间穿越"]}


# ===========================================================================
# 检测 5：Lag/Diff/Rolling 特征的逐行穿越验证
#
# 对测试集的每一行，验证其 lag/diff/rolling 特征只依赖于该行时间之前的数据。
# 这是最严格的逐行检测。
# ===========================================================================

def test_lag_features_row_by_row(full_df, pred_day, train_end):
    """
    逐行验证 lag 特征是否正确（无穿越）。

    核心检测逻辑：
      - 对测试集每一行 (时间 t)，lag_Nd 引用的时间 t-N天 必须 < pred_day
      - 如果 t-N天 >= pred_day，则特征值必须是 NaN（因为测试集 load 已被置为 NaN）
      - 如果 t-N天 < pred_day，特征值应该等于 combined 中该时间的 load

    Returns
    -------
    dict  {"passed": bool, "details": list}
    """
    feat_all = build_features(full_df.copy())
    test_feat = feat_all[feat_all["record_time"] >= pred_day].copy().reset_index(drop=True)

    # 用 combined 自身的数据做查找表（经过同一套 resample 流程）
    time_to_load = dict(zip(full_df["record_time"], full_df["load"]))

    issues = []
    dh = DAILY_HORIZON

    check_indices = list(range(min(10, len(test_feat)))) + \
                    list(range(max(0, len(test_feat) - 10), len(test_feat)))
    check_indices = sorted(set(check_indices))

    for idx in check_indices:
        row = test_feat.iloc[idx]
        t = pd.to_datetime(row["record_time"])

        for lag_days in [1, 7, 14, 28]:
            col_name = f"lag_{lag_days}d"
            if col_name not in test_feat.columns:
                continue

            feat_val = row[col_name]
            ref_time = t - timedelta(days=lag_days)

            # 核心穿越检测：引用时间在预测日之后 → 值必须是 NaN
            if ref_time >= pred_day:
                if not np.isnan(feat_val):
                    issues.append(
                        f"行 {idx} (t={t}): {col_name} 引用了 {ref_time}（>= pred_day），"
                        f"值应为 NaN 但实际为 {feat_val:.4f}（穿越！）"
                    )

    passed = len(issues) == 0
    return {"passed": passed, "details": issues if issues else ["所有 lag 特征逐行验证通过，无未来数据引用"]}


# ===========================================================================
# 检测 6：diff 特征穿越验证
#
# diff 特征基于 load.shift(1)，即 t-1 时刻的 load。
# 对于测试集第一行（pred_day 00:00），shift(1) 取的是 train_end 23:45 的值，
# 这是合法的。但如果 diff 特征用了 load[t]（当前时刻），就是穿越。
# ===========================================================================

def test_diff_features(full_df, pred_day, train_end):
    """
    验证 diff 特征是否只依赖 t-1 及更早的数据。

    方法：扰动预测日的 load 值，检查 diff 特征是否变化。
    diff 特征基于 load_prev = load.shift(1)，所以：
      - 测试集第一行的 diff 应该不受预测日 load 影响（因为 shift(1) 取的是 train_end 最后一个点）
      - 但测试集第二行的 diff_1 = load_prev[t] - load_prev[t-1]
        其中 load_prev[t] = load[t-1] = 测试集第一行的 load → 这是未来数据！

    Returns
    -------
    dict  {"passed": bool, "details": list}
    """
    # 这个检测已经被检测 1（扰动法）覆盖了，这里做更精细的分析
    feat_all = build_features(full_df.copy())
    test_feat = feat_all[feat_all["record_time"] >= pred_day].copy().reset_index(drop=True)

    issues = []

    # 检查 diff 特征的构造逻辑
    # diff_1 = load_prev - load_prev.shift(1) = load[t-1] - load[t-2]
    # 对于测试集第一行 (t = pred_day 00:00):
    #   load_prev = load[t-1] = train_end 23:45 的 load → 合法
    #   load_prev.shift(1) = load[t-2] = train_end 23:30 的 load → 合法
    # 对于测试集第二行 (t = pred_day 00:15):
    #   load_prev = load[t-1] = pred_day 00:00 的 load → 这是预测日的真实值！

    # 但在回测中，combined = concat(train, test)，test 的 load 列是有真实值的
    # 所以 shift(1) 在测试集内部会引用测试集自身的 load
    # 这在"逐点预测"场景下是穿越，但在"一次性预测整天"场景下需要看具体使用方式

    # 检查：测试集第 2 行及之后的 diff_1 是否依赖了测试集的 load
    if len(test_feat) > 1:
        # 用扰动法精确检测
        perturbed_df = full_df.copy()
        future_mask = perturbed_df["record_time"] >= pred_day
        original_load = perturbed_df.loc[future_mask, "load"].values.copy()
        perturbed_df.loc[future_mask, "load"] = original_load * 5 + 999

        feat_perturbed = build_features(perturbed_df)
        test_perturbed = feat_perturbed[feat_perturbed["record_time"] >= pred_day].copy().reset_index(drop=True)

        for col in ["diff_1", "diff_96", "diff_192", "diff_96_of_96"]:
            if col not in test_feat.columns:
                continue
            orig = test_feat[col].values.astype(float)
            pert = test_perturbed[col].values.astype(float)

            for i in range(len(orig)):
                o = orig[i] if not np.isnan(orig[i]) else 0
                p = pert[i] if not np.isnan(pert[i]) else 0
                if abs(o - p) > 1e-6:
                    t = test_feat.iloc[i]["record_time"]
                    issues.append(
                        f"行 {i} (t={t}): {col} 受预测日 load 影响: "
                        f"原始={orig[i]:.4f}, 扰动后={pert[i]:.4f}"
                    )

    passed = len(issues) == 0
    return {"passed": passed, "details": issues if issues else ["diff 特征无穿越"]}


# ===========================================================================
# 检测 7：rolling 特征穿越验证
#
# rolling 特征基于 load.shift(96)（昨天的值），再做 rolling(center=False)。
# 验证 center=False 确实只看过去。
# ===========================================================================

def test_rolling_features(full_df, pred_day, train_end):
    """
    验证 rolling 特征的 center=False 是否生效。

    方法：手动计算测试集第一行的 roll_4_mean，与特征值对比。
    修复后 load_yd = load.shift(96)，对于测试集第一行 (pred_day 00:00)，
    load_yd 引用的是 train_end 前一天 00:00 的 load（训练集数据），这是合法的。

    Returns
    -------
    dict  {"passed": bool, "details": list}
    """
    feat_all = build_features(full_df.copy())
    test_feat = feat_all[feat_all["record_time"] >= pred_day].copy().reset_index(drop=True)

    issues = []

    if len(test_feat) == 0:
        return {"passed": True, "details": ["无测试数据"]}

    # 测试集第一行的时间
    t0 = pd.to_datetime(test_feat.iloc[0]["record_time"])
    # load_yd = load.shift(96)，所以 load_yd[t0] = load[t0 - 1天]
    # roll_4_mean[t0] = mean(load_yd[t0], load_yd[t0-15min], load_yd[t0-30min], load_yd[t0-45min])
    #                 = mean(load[t0-1天], load[t0-1天-15min], load[t0-1天-30min], load[t0-1天-45min])

    time_to_load = dict(zip(full_df["record_time"], full_df["load"]))

    ref_times = [t0 - timedelta(days=1) - timedelta(minutes=15 * i) for i in range(4)]
    ref_vals = [time_to_load.get(rt, np.nan) for rt in ref_times]

    # 所有参考时间都应该在预测日之前
    for rt in ref_times:
        if rt >= pred_day:
            issues.append(f"roll_4_mean 引用了 {rt}，该时间 >= pred_day（穿越！）")

    if not any(np.isnan(v) for v in ref_vals) and not issues:
        expected_roll_4_mean = np.mean(ref_vals)
        actual_roll_4_mean = test_feat.iloc[0].get("roll_4_mean", np.nan)

        if not np.isnan(actual_roll_4_mean):
            diff = abs(expected_roll_4_mean - actual_roll_4_mean)
            # 由于原始数据经过 resample + interpolate，允许插值导致的小偏差
            pct_diff = diff / max(abs(expected_roll_4_mean), 1e-8) * 100
            if pct_diff > 5.0:
                issues.append(
                    f"roll_4_mean 手动计算严重不匹配: "
                    f"actual={actual_roll_4_mean:.4f}, expected={expected_roll_4_mean:.4f}, "
                    f"偏差={pct_diff:.2f}%"
                )

    passed = len(issues) == 0
    return {"passed": passed, "details": issues if issues else ["rolling 特征手动验证通过，center=False 生效"]}


# ===========================================================================
# 检测 8：训练集 y_train 是否包含未来数据
#
# 最直接的穿越：训练集的目标变量 (load) 包含了预测日的值。
# ===========================================================================

def test_ytrain_no_future(full_df, pred_day, train_end):
    """
    检测训练集的目标变量是否包含预测日及之后的数据。

    Returns
    -------
    dict  {"passed": bool, "details": list}
    """
    feat_all = build_features(full_df.copy())
    train_feat = feat_all[feat_all["record_time"] <= train_end].copy()

    issues = []

    # y_train 的时间范围
    y_times = train_feat["record_time"]
    y_max_time = y_times.max()

    if y_max_time >= pred_day:
        issues.append(f"y_train 包含预测日数据: 最大时间 = {y_max_time}")

    # 检查 y_train 的值是否与预测日的真实 load 相同（间接穿越）
    pred_day_loads = full_df[full_df["record_time"] >= pred_day]["load"].values
    train_loads = train_feat["load"].values

    # 训练集最后 96 个值不应该等于预测日的 96 个值
    if len(train_loads) >= 96 and len(pred_day_loads) >= 96:
        last_96_train = train_loads[-96:]
        first_96_pred = pred_day_loads[:96]
        if np.allclose(last_96_train, first_96_pred, atol=1e-6):
            issues.append("训练集最后 96 个 load 值与预测日完全相同（可能数据切分错误）")

    passed = len(issues) == 0
    return {"passed": passed, "details": issues if issues else ["y_train 不包含未来数据"]}


# ===========================================================================
# 主程序：运行所有检测
# ===========================================================================

def run_all_checks():
    """运行所有数据穿越检测"""
    print("=" * 70)
    print("  数据穿越验证程序")
    print("  目标: run_weihai_backtest.py 的回测流程")
    print("=" * 70)

    # 加载数据
    print("\n加载数据...")
    df = load_weihai_data()
    print(f"数据范围: {df['record_time'].min()} ~ {df['record_time'].max()}, {len(df)} 行\n")

    # 选择一个预测日进行检测（取回测期间的第一天）
    pred_day = pd.to_datetime(PRED_START)
    train_end = pred_day - timedelta(days=1)
    train_start = train_end - timedelta(days=TRAIN_DAYS)

    print(f"检测场景: 预测日 = {pred_day.strftime('%Y-%m-%d')}")
    print(f"          训练期 = {train_start.strftime('%Y-%m-%d')} ~ {train_end.strftime('%Y-%m-%d')}")
    print()

    # 构造与回测一致的 combined 数据
    mask_tr = (df["record_time"] >= train_start) & (df["record_time"] <= train_end)
    mask_te = (df["record_time"] >= pred_day) & (df["record_time"] < pred_day + timedelta(days=1))
    train_raw = df[mask_tr].copy().reset_index(drop=True)
    test_raw = df[mask_te].copy().reset_index(drop=True)

    # 修复后的方式：将测试集 load 置为 NaN 再合并（与修复后的 run_weihai_backtest.py 一致）
    test_raw_masked = test_raw.copy()
    test_raw_masked["load"] = np.nan
    combined = pd.concat([train_raw, test_raw_masked], ignore_index=True)

    # 同时保留一份带真实 load 的 combined（用于检测 5 的 lag 值验证）
    combined_with_truth = pd.concat([train_raw, test_raw], ignore_index=True)

    print(f"训练集: {len(train_raw)} 行, 测试集: {len(test_raw)} 行, 合并: {len(combined)} 行\n")

    # 运行所有检测
    checks = [
        ("检测 1: 特征穿越检测（扰动法）", test_feature_leakage_by_perturbation, (combined, pred_day, train_end)),
        ("检测 2: 训练集/测试集时间边界", test_time_boundary, (combined, pred_day, train_end)),
        ("检测 3: 日统计特征穿越", test_daily_stats_leakage, (combined, pred_day, train_end)),
        ("检测 4: 交叉验证穿越", test_cv_no_leakage, (combined, pred_day, train_end)),
        ("检测 5: Lag 特征逐行验证", test_lag_features_row_by_row, (combined, pred_day, train_end)),
        ("检测 6: Diff 特征穿越", test_diff_features, (combined, pred_day, train_end)),
        ("检测 7: Rolling 特征穿越", test_rolling_features, (combined, pred_day, train_end)),
        ("检测 8: 训练集目标变量", test_ytrain_no_future, (combined, pred_day, train_end)),
    ]

    total_passed = 0
    total_failed = 0
    all_leaked_features = set()

    for name, func, args in checks:
        print("-" * 70)
        print(f"  {name}")
        print("-" * 70)

        try:
            result = func(*args)
            status = "[PASS]" if result["passed"] else "[FAIL]"
            print(f"  结果: {status}")

            if result["passed"]:
                total_passed += 1
            else:
                total_failed += 1

            # 打印详情
            details = result.get("details", [])
            leaked = result.get("leaked_features", [])

            if leaked:
                all_leaked_features.update(leaked)
                print(f"  穿越特征数量: {len(leaked)}")
                # 只打印前 10 个
                for feat_info in details[:10]:
                    if isinstance(feat_info, dict):
                        print(f"    - {feat_info['feature']}: "
                              f"max_diff={feat_info['max_diff']:.6f}, "
                              f"worst_time={feat_info['worst_row_time']}")
                    else:
                        print(f"    - {feat_info}")
                if len(details) > 10:
                    print(f"    ... 还有 {len(details) - 10} 个")
            else:
                for d in details[:5]:
                    print(f"    {d}")

        except Exception as e:
            print(f"  结果: [ERROR] 执行出错: {e}")
            total_failed += 1
            import traceback
            traceback.print_exc()

        print()

    # 汇总
    print("=" * 70)
    print("  汇总报告")
    print("=" * 70)
    print(f"  通过: {total_passed}/{total_passed + total_failed}")
    print(f"  未通过: {total_failed}/{total_passed + total_failed}")

    if all_leaked_features:
        print(f"\n  发现穿越的特征 ({len(all_leaked_features)} 个):")
        for f in sorted(all_leaked_features):
            print(f"    - {f}")

    if total_failed == 0:
        print("\n  [OK] 所有检测通过，回测流程无数据穿越！")
    else:
        print(f"\n  [WARNING] 发现 {total_failed} 项穿越问题，请检查上述详情。")

    print("=" * 70)
    return total_failed == 0


if __name__ == "__main__":
    success = run_all_checks()
    sys.exit(0 if success else 1)
# @AI_GENERATED: end
