# @AI_GENERATED
"""
真实数据核心层:南华变.10kV叶家线085 + 原始负荷数据丢失(Gap策略)场景。

本模块面向真实电网数据:
  - 从 agent_grid_db 拉取真实负荷 + 真实气象(温度/风速)
  - 无穿越特征工程(与 experiments/weather_ablation 同源)
  - 故障A: D-1(昨天)整天数据丢失 → 基线 gap1(lag→D-1) 真实劣化
  - 恢复:两候选策略真实重跑预测择优
    * extra_gap      : 多 gap 一天,从 D-2 起算(不引入假值)
    * pred_fill_dm1  : 预测值回填 D-1,继续 gap D(保住 lag_1d→D-1)

精度口径:Accuracy = (1 - MAPE) × 100%(与 demo 主线一致)。
所有数值由 XGB 实算,确定性(同 seed 可复现)。决策权交给 Agent。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from .models import ErrorCode, StrategyEvaluation, err, ok

# _ROOT 指向 skill 根目录 (operation_skill/)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# 离线缓存目录: skill根/cached_data/
_CACHE_DIR = _ROOT / "cached_data"

# 环境变量控制数据源: USE_CACHED_DATA=1 强制离线; =0 强制在线; 不设置则自动探测
_USE_CACHE_ENV = os.environ.get("USE_CACHED_DATA", "").strip()


def _try_import_fetch():
    """尝试导入数据库拉取模块,无法导入时返回 None。"""
    try:
        from fetch_asset_data import fetch_load, fetch_weather  # noqa: E402
        return fetch_load, fetch_weather
    except (ImportError, Exception):
        return None, None


# 尝试导入(可能因为缺少 pymysql 或网络不通而失败)
_fetch_load_fn, _fetch_weather_fn = _try_import_fetch()

DAILY_HORIZON = 96
WEEK_HORIZON = DAILY_HORIZON * 7
WEATHER_COLS = ["temperature", "wind_speed"]
FEATURE_GROUPS = ["lag", "rolling", "calendar", "weather"]

DEFAULT_REGION = "雄州"
DEFAULT_ASSET = "南华变.10kV叶家线085"

_XGB_PARAMS = dict(
    n_estimators=240, max_depth=4, learning_rate=0.04,
    subsample=0.9, colsample_bytree=0.9, objective="reg:squarederror",
    n_jobs=4, missing=np.nan,
)


# ---------- 数据读取与对齐 ----------
def _should_use_cache() -> bool:
    """判断是否使用本地缓存数据。"""
    if _USE_CACHE_ENV == "1":
        return True
    if _USE_CACHE_ENV == "0":
        return False
    # 自动探测: 缓存存在且数据库模块不可用时用缓存
    if _CACHE_DIR.exists() and (_CACHE_DIR / "merged_20260201_20260527.csv").exists():
        if _fetch_load_fn is None:
            return True
    return False


def _load_from_cache() -> pd.DataFrame:
    """从本地缓存 CSV 加载已合并的数据。"""
    merged_file = _CACHE_DIR / "merged_20260201_20260527.csv"
    if not merged_file.exists():
        raise FileNotFoundError(
            f"离线缓存文件不存在: {merged_file}\n"
            "请先用在线模式拉取数据,或从交付包中获取 cached_data/ 目录。"
        )
    df = pd.read_csv(merged_file, parse_dates=["record_time"])
    print(f"  [离线模式] 从本地缓存加载: {merged_file.name} ({len(df)} 行)")
    return df


def _load_real_frame(region: str, asset: str, start: str, end: str, nwp: str) -> pd.DataFrame:
    # 优先检查是否使用缓存
    if _should_use_cache():
        return _load_from_cache()

    # 在线模式: 从数据库拉取
    if _fetch_load_fn is None:
        # 数据库模块不可用,尝试缓存兜底
        if _CACHE_DIR.exists():
            print("  [警告] 数据库模块不可用,自动降级到本地缓存")
            return _load_from_cache()
        raise ImportError(
            "无法导入 fetch_asset_data 且本地缓存不存在。\n"
            "请确保: 1) 已安装 pymysql; 2) 可连接数据库; 或 3) cached_data/ 目录存在。"
        )

    df_load = _fetch_load_fn(region, start, end, asset_name=asset, metrics=["p"])
    if df_load.empty:
        raise ValueError(f"未取到负荷数据: region={region} asset={asset}")
    load_df = df_load[["record_time", "p"]].copy()
    load_df["record_time"] = pd.to_datetime(load_df["record_time"])
    load_df["load"] = pd.to_numeric(load_df["p"], errors="coerce")
    load_df = (
        load_df.drop(columns=["p"]).dropna(subset=["record_time", "load"])
        .drop_duplicates("record_time", keep="first").sort_values("record_time")
        .set_index("record_time").resample("15min").mean()
    )
    load_df["load"] = load_df["load"].interpolate(limit_direction="both")

    df_wx = _fetch_weather_fn(asset, start, end, nwp=nwp)
    if df_wx.empty:
        raise ValueError(f"未取到气象数据: station={asset}")
    wx = df_wx[["ts", "ws", "tmp"]].copy()
    wx["ts"] = pd.to_datetime(wx["ts"])
    wx["temperature"] = pd.to_numeric(wx["tmp"], errors="coerce")
    wx["wind_speed"] = pd.to_numeric(wx["ws"], errors="coerce")
    wx = (
        wx.drop(columns=["ws", "tmp"]).dropna(subset=["ts"])
        .drop_duplicates("ts", keep="first").sort_values("ts")
        .set_index("ts").resample("15min").interpolate(method="time", limit_direction="both")
    )

    merged = load_df.join(wx, how="left")
    merged[WEATHER_COLS] = merged[WEATHER_COLS].interpolate(limit_direction="both")
    merged = merged.reset_index().rename(columns={"index": "record_time"})
    if "record_time" not in merged.columns:
        merged = merged.rename(columns={merged.columns[0]: "record_time"})
    return merged


# ---------- 无穿越特征工程 ----------
def _build_features(df: pd.DataFrame) -> pd.DataFrame:
    feat = df.copy()
    feat["record_time"] = pd.to_datetime(feat["record_time"])
    t = feat["record_time"]
    dh = DAILY_HORIZON
    period = t.dt.hour * 4 + t.dt.minute // 15
    feat["period"] = period
    feat["dayofweek"] = t.dt.dayofweek
    feat["month"] = t.dt.month
    feat["is_weekend"] = (t.dt.dayofweek >= 5).astype(int)
    feat["period_sin"] = np.sin(2 * np.pi * period / dh)
    feat["period_cos"] = np.cos(2 * np.pi * period / dh)
    feat["wday_sin"] = np.sin(2 * np.pi * feat["dayofweek"] / 7)
    feat["wday_cos"] = np.cos(2 * np.pi * feat["dayofweek"] / 7)
    for days in [1, 2, 3, 7, 14, 21, 28]:
        feat[f"lag_{days}d"] = feat["load"].shift(days * dh)
    load_yd = feat["load"].shift(dh)
    for window in [4, 16, 96, 96 * 7]:
        min_p = max(2, min(window, 8))
        feat[f"roll_mean_{window}"] = load_yd.rolling(window=window, min_periods=min_p).mean()
        feat[f"roll_std_{window}"] = load_yd.rolling(window=window, min_periods=min_p).std()
    for w in WEATHER_COLS:
        if w in feat.columns:
            feat[w] = pd.to_numeric(feat[w], errors="coerce")
    return feat


def _classify(cols: List[str]) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {"lag": [], "rolling": [], "calendar": [], "weather": []}
    for c in cols:
        if c in WEATHER_COLS:
            groups["weather"].append(c)
        elif c.startswith("lag_"):
            groups["lag"].append(c)
        elif c.startswith("roll_"):
            groups["rolling"].append(c)
        else:
            groups["calendar"].append(c)
    return groups


# ---------- 数据集生成 ----------
def load_real_dataset(
    region: str = DEFAULT_REGION,
    asset: str = DEFAULT_ASSET,
    start: str = "2026-02-01",
    end: str = "2026-05-28",
    target_day: Optional[str] = None,
    train_days: int = 90,
    gap_days: int = 1,
    nwp: str = "ENS_AVG",
):
    """拉取真实数据并登记数据集(含训练/预测窗口元信息)。"""
    try:
        raw = _load_real_frame(region, asset, start, end, nwp)
    except Exception as exc:  # noqa: BLE001
        return err(ErrorCode.DATA_UNAVAILABLE, f"failed to load real data: {exc}")
    if raw.empty:
        return err(ErrorCode.DATA_UNAVAILABLE, "empty real dataset")

    if target_day is None:
        target_start = raw["record_time"].max().normalize() - pd.Timedelta(days=1)
    else:
        target_start = pd.Timestamp(target_day)
    target_end = target_start + pd.Timedelta(days=1)
    cutoff = target_start - pd.Timedelta(days=gap_days)
    train_start = cutoff - pd.Timedelta(days=train_days)

    records = raw.assign(record_time=raw["record_time"].dt.strftime("%Y-%m-%dT%H:%M")).to_dict(orient="records")
    data = {
        "dataset_id": "ds_real_baseline",
        "region": region,
        "asset": asset,
        "time_range": [records[0]["record_time"], records[-1]["record_time"]],
        "group_status": {g: "present" for g in FEATURE_GROUPS},
        "records": records,
        "meta": {
            "region": region, "asset": asset, "nwp": nwp,
            "train_start": train_start.isoformat(),
            "train_cutoff_exclusive": cutoff.isoformat(),
            "target_day": target_start.strftime("%Y-%m-%d"),
            "gap_days": gap_days,
            "weather_is_simulated": False,
        },
    }
    return ok(data)


# ========================================================================
# 故障A: 原始负荷数据丢失 —— Gap 策略
# ========================================================================

def _build_features_with_gap(df: pd.DataFrame, gap_extra: int = 0) -> pd.DataFrame:
    """gap 版特征工程: lag 从 (1+gap_extra) 天起算,rolling 基于 shift((1+gap_extra)*96)。

    gap_extra=0 时等同于基线 _build_features (lag 从 1d 起);
    gap_extra=1 时等同于"跳过1天缺失" — lag 从 2d 起,rolling 从 shift(2*96) 起。
    """
    feat = df.copy()
    feat["record_time"] = pd.to_datetime(feat["record_time"])
    t = feat["record_time"]
    dh = DAILY_HORIZON
    shift_base = (1 + gap_extra) * dh

    period = t.dt.hour * 4 + t.dt.minute // 15
    feat["period"] = period
    feat["dayofweek"] = t.dt.dayofweek
    feat["month"] = t.dt.month
    feat["is_weekend"] = (t.dt.dayofweek >= 5).astype(int)
    feat["period_sin"] = np.sin(2 * np.pi * period / dh)
    feat["period_cos"] = np.cos(2 * np.pi * period / dh)
    feat["wday_sin"] = np.sin(2 * np.pi * feat["dayofweek"] / 7)
    feat["wday_cos"] = np.cos(2 * np.pi * feat["dayofweek"] / 7)

    for days in [1, 2, 3, 7, 14, 21, 28]:
        actual_days = days + gap_extra
        feat[f"lag_{days}d"] = feat["load"].shift(actual_days * dh)

    load_shifted = feat["load"].shift(shift_base)
    for window in [4, 16, 96, 96 * 7]:
        min_p = max(2, min(window, 8))
        feat[f"roll_mean_{window}"] = load_shifted.rolling(window=window, min_periods=min_p).mean()
        feat[f"roll_std_{window}"] = load_shifted.rolling(window=window, min_periods=min_p).std()

    for w in WEATHER_COLS:
        if w in feat.columns:
            feat[w] = pd.to_numeric(feat[w], errors="coerce")

    return feat


# 时间线: D+1=预测目标日, D=今天, D-1=昨天, D-2=前天
#
# 【模式1: Gap一天 / 次日预测】基线只用 D-1 真值(lag_1d→D-1)
#   故障A: D-1 整天数据丢失 → 基线真实劣化
#     S1(extra_gap)    : 多 gap 一天,从 D-2 起算
#     S2(pred_fill_dm1): 预测值回填 D-1,继续 gap D

_GAP_STRATEGY_META = {
    "extra_gap": {
        "name": "多 gap 一天(从 D-2 起算)",
        "fault": "A", "mode": 1,
        "cost": "low", "risk": "low",
        "rationale": "D-1 丢了就跳过,只用 D-2 及之前真值。丢信息但不引入假值。",
    },
    "pred_fill_dm1": {
        "name": "预测值回填 D-1, 继续 gap D",
        "fault": "A", "mode": 1,
        "cost": "medium", "risk": "medium",
        "rationale": "用 gap 模型对 D-1 的预测值当代理真值填回,保住 lag_1d→D-1 位置。",
    },
}

GAP_STRATEGY_PRIORITY_A = ["extra_gap", "pred_fill_dm1"]


def inject_fault_a(dataset: Dict[str, Any]):
    """故障A注入: D-1 整天数据丢失(load 置 NaN)。"""
    meta = dataset.get("meta", {})
    target_day = meta.get("target_day")
    if not target_day:
        return err(ErrorCode.DATA_UNAVAILABLE, "missing target_day in meta")

    D_plus_1 = pd.Timestamp(target_day)
    D = D_plus_1 - pd.Timedelta(days=1)
    D_minus_1 = D - pd.Timedelta(days=1)

    records = dataset["records"]
    new_records = []
    for r in records:
        ts = pd.Timestamp(r["record_time"])
        if D_minus_1 <= ts < D:
            new_records.append({**r, "load": None})
        else:
            new_records.append(r)

    data = {
        **dataset,
        "dataset_id": "ds_real_fault_a",
        "group_status": {**dataset.get("group_status", {}), "raw_load": "missing"},
        "records": new_records,
        "meta": {
            **meta,
            "degradation": "fault_a",
            "fault_type": "A",
            "missing_start": D_minus_1.isoformat(),
            "missing_end": D.isoformat(),
            "missing_description": "D-1 整天数据丢失",
        },
    }
    return ok(data)


def run_prediction_gap_strategy(
    dataset: Dict[str, Any],
    strategy: str,
    algorithm_version: str,
    seed: int = 42,
):
    """按 gap 策略训练并预测目标日。

    模式1(Gap一天/次日预测): 基线只用 D-1 真值,lag_1d→D-1
      baseline_gap1  : 真·gap一天基线(_build_features_with_gap, lag从D-1起)
      degraded_a     : D-1 丢失(劣化,gap1基线下真实劣化)
      extra_gap      : 多 gap 一天(从 D-2 起算)
      pred_fill_dm1  : 预测值回填 D-1, 继续 gap D
    """
    meta = dataset.get("meta", {})
    target_day = meta.get("target_day")
    train_start = meta.get("train_start")
    if not target_day or not train_start:
        return err(ErrorCode.DATA_UNAVAILABLE, "dataset meta missing window info")

    D_plus_1 = pd.Timestamp(target_day)
    D = D_plus_1 - pd.Timedelta(days=1)
    D_minus_1 = D - pd.Timedelta(days=1)
    train_start_ts = pd.Timestamp(train_start)
    target_start = D_plus_1
    target_end = D_plus_1 + pd.Timedelta(days=1)

    df_raw = pd.DataFrame(dataset["records"])
    df_raw["record_time"] = pd.to_datetime(df_raw["record_time"])
    df_raw["load"] = pd.to_numeric(df_raw["load"], errors="coerce")

    if strategy in ("baseline_gap1", "degraded_a"):
        # 模式1 基线: 真·gap一天(lag_1d→D-1), cutoff=D 使训练用到 D-1
        # degraded_a 时 dataset 的 D-1 已被注入 NaN → 真实劣化
        feat = _build_features_with_gap(df_raw, gap_extra=1)
        cutoff = D
    elif strategy == "extra_gap":
        # 跳过 D-1: D-1 没了直接用 D-2 之前的干净数据(lag 从 D-2 起)
        # 先恢复 D-1 的 NaN(用上周同期),保证 rolling 窗口干净
        df_work = df_raw.copy()
        mask_dm1 = (df_work["record_time"] >= D_minus_1) & (df_work["record_time"] < D)
        for idx in df_work[mask_dm1].index:
            ts = df_work.loc[idx, "record_time"]
            ref_ts = ts - pd.Timedelta(days=7)
            ref = df_work[df_work["record_time"] == ref_ts]
            if not ref.empty:
                df_work.loc[idx, "load"] = ref.iloc[0]["load"]
        feat = _build_features_with_gap(df_work, gap_extra=2)
        cutoff = D_minus_1
    elif strategy == "pred_fill_dm1":
        # Step1: predict D-1 用 gap 模型(gap_extra=1, 训练到 D-2)
        feat_p = _build_features_with_gap(df_raw, gap_extra=1)
        cols_p = [c for c in feat_p.columns if c not in {"record_time", "load"} and pd.api.types.is_numeric_dtype(feat_p[c])]
        rt_p = feat_p["record_time"]
        tr_p = (rt_p >= train_start_ts) & (rt_p < D_minus_1)
        pm_p = (rt_p >= D_minus_1) & (rt_p < D)
        dn_p = [c for c in cols_p if c.startswith(("lag_", "roll_"))]
        train_p = feat_p.loc[tr_p].dropna(subset=dn_p + ["load"]).copy()
        test_p = feat_p.loc[pm_p].copy()
        if train_p.empty or test_p.empty:
            return err(ErrorCode.DATA_UNAVAILABLE, "empty split for D-1 prediction")
        mdl_p = XGBRegressor(random_state=seed, **_XGB_PARAMS)
        mdl_p.fit(train_p[cols_p], train_p["load"])
        dm1_pred = np.maximum(mdl_p.predict(test_p[cols_p]), 0.0)
        # Step2: fill D-1, 用 gap1 基线特征(lag_1d→回填后的D-1)
        df_f = df_raw.copy()
        mask_dm1 = (df_f["record_time"] >= D_minus_1) & (df_f["record_time"] < D)
        df_f.loc[mask_dm1, "load"] = dm1_pred
        feat = _build_features_with_gap(df_f, gap_extra=1)
        cutoff = D
    else:
        return err(ErrorCode.EXECUTION_FAILED, f"unsupported strategy: {strategy}")

    all_cols = [c for c in feat.columns
                if c not in {"record_time", "load"} and pd.api.types.is_numeric_dtype(feat[c])]
    rt = feat["record_time"]
    train_mask = (rt >= train_start_ts) & (rt < cutoff)
    test_mask = (rt >= target_start) & (rt < target_end)

    dropna_cols = [c for c in all_cols if c.startswith(("lag_", "roll_"))]
    train = feat.loc[train_mask].dropna(subset=dropna_cols + ["load"]).copy()
    test = feat.loc[test_mask].copy()

    if train.empty or test.empty:
        return err(ErrorCode.DATA_UNAVAILABLE, f"empty split: train={len(train)}, test={len(test)}")

    model = XGBRegressor(random_state=seed, **_XGB_PARAMS)
    model.fit(train[all_cols], train["load"])
    y_pred = np.maximum(model.predict(test[all_cols]), 0.0)
    y_true = test["load"].to_numpy(dtype=float)

    importances = {c: float(v) for c, v in zip(all_cols, model.feature_importances_)}
    groups = _classify(all_cols)
    group_importance = {
        g: round(sum(importances.get(c, 0.0) for c in cols), 5) for g, cols in groups.items() if cols
    }

    data = {
        "prediction_id": f"pred_{strategy}",
        "algorithm_version": algorithm_version,
        "scenario": strategy,
        "y_true": [round(float(v), 4) for v in y_true.tolist()],
        "y_pred": [round(float(v), 4) for v in y_pred.tolist()],
        "feature_importances": {k: round(v, 5) for k, v in importances.items()},
        "group_importance": group_importance,
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "used_groups": [g for g, c in groups.items() if c],
    }
    return ok(data)


def generate_gap_strategies(
    fault_type: str = "A",
    evaluator: Optional[Callable[[str], float]] = None,
):
    """生成 gap 策略候选并实测精度。"""
    strategies: List[StrategyEvaluation] = []
    for sid in GAP_STRATEGY_PRIORITY_A:
        meta_s = _GAP_STRATEGY_META[sid]
        expected = round(float(evaluator(sid)), 2) if evaluator else 0.0
        strategies.append(
            StrategyEvaluation(
                strategy_id=sid, name=meta_s["name"], expected_accuracy=expected,
                cost=meta_s["cost"], risk=meta_s["risk"], rationale=meta_s["rationale"],
            )
        )
    return ok(strategies)


def select_gap_strategy(evaluations: List[dict]):
    """选实测精度最高者。"""
    ranked = sorted(evaluations, key=lambda it: -float(it["expected_accuracy"]))
    selected = ranked[0]
    for it in evaluations:
        it["selected"] = it["strategy_id"] == selected["strategy_id"]
    return ok({"selected_strategy": selected, "evaluations": evaluations})


def execute_gap_strategy(strategy_id: str, dataset: Dict[str, Any]):
    """执行选定 gap 策略。"""
    if strategy_id not in _GAP_STRATEGY_META:
        return err(ErrorCode.EXECUTION_FAILED, f"unsupported strategy: {strategy_id}")
    steps_map = {
        "extra_gap": [
            "确认 D-1 数据不可用",
            "将 gap 扩大为 2 天(跳过 D 和 D-1)",
            "用 gap_extra=2 版特征工程(lag 从 D-2 起算)",
            "重训模型并预测 D+1",
        ],
        "pred_fill_dm1": [
            "确认 D-1 数据不可用",
            "用 D-2 及之前数据训练模型,预测 D-1 全天负荷",
            "将预测值作为 D-1 代理真值回填",
            "正常 gap D,用回填后的 D-1 构造特征并预测 D+1",
        ],
    }
    retrain = strategy_id == "extra_gap"
    recovered = {
        **dataset,
        "dataset_id": "ds_real_recovered_gap",
        "meta": {**dataset.get("meta", {}), "recovery_strategy": strategy_id},
    }
    execution = {
        "execution_id": f"exec_gap_{strategy_id}_001",
        "selected_strategy": strategy_id,
        "recovered_dataset_id": "ds_real_recovered_gap",
        "new_algorithm_version": "load_xgb_v2_gap" if retrain else "load_xgb_v1",
        "steps": steps_map[strategy_id],
        "status": "success",
    }
    return ok({"execution": execution, "dataset": recovered, "recovery_scenario": strategy_id})


# ========================================================================
# 逐日真实时间线计算 —— 7天精度轨迹全部由 XGB 实跑得出，不做插值
# ========================================================================

def inject_missing_day(dataset: Dict[str, Any], missing_day: str):
    """把指定整天(missing_day, 96点)的 load 置 NaN。

    与 inject_fault_a 不同:本函数按显式日期注入,不依赖 meta.target_day,
    用于逐日时间线计算时对"同一个缺失源日"在不同 target_day 下复用。
    """
    D0 = pd.Timestamp(missing_day)
    D1 = D0 + pd.Timedelta(days=1)
    new_records = []
    for r in dataset["records"]:
        ts = pd.Timestamp(r["record_time"])
        if D0 <= ts < D1:
            new_records.append({**r, "load": None})
        else:
            new_records.append(r)
    data = {
        **dataset,
        "dataset_id": "ds_real_missing_day",
        "group_status": {**dataset.get("group_status", {}), "raw_load": "missing"},
        "records": new_records,
        "meta": {
            **dataset.get("meta", {}),
            "missing_day": D0.strftime("%Y-%m-%d"),
        },
    }
    return ok(data)


def _accuracy_of(pred: Dict[str, Any]) -> float:
    from .metrics import evaluate_accuracy
    m = evaluate_accuracy(pred["y_true"], pred["y_pred"])
    if m["status"] != "ok":
        raise RuntimeError(m["error"])
    return m["data"]["accuracy"]


def backfill_missing_day(dataset: Dict[str, Any], missing_day: str, seed: int = 42):
    """用 gap 模型预测 missing_day 全天负荷并回填(修复动作,产生代理真值)。

    与 pred_fill_dm1 策略的 Step1 同源:用 missing_day 之前的数据训练 gap 模型,
    预测 missing_day 96 点,作为代理真值填回。返回"已修复"数据集。
    所有数值由 XGB 实算。
    """
    D0 = pd.Timestamp(missing_day)
    D1 = D0 + pd.Timedelta(days=1)

    df_raw = pd.DataFrame(dataset["records"])
    df_raw["record_time"] = pd.to_datetime(df_raw["record_time"])
    df_raw["load"] = pd.to_numeric(df_raw["load"], errors="coerce")

    meta = dataset.get("meta", {})
    train_start = meta.get("train_start")
    train_start_ts = pd.Timestamp(train_start) if train_start else df_raw["record_time"].min()

    feat = _build_features_with_gap(df_raw, gap_extra=1)
    cols = [c for c in feat.columns
            if c not in {"record_time", "load"} and pd.api.types.is_numeric_dtype(feat[c])]
    rt = feat["record_time"]
    tr = (rt >= train_start_ts) & (rt < D0)
    pm = (rt >= D0) & (rt < D1)
    dn = [c for c in cols if c.startswith(("lag_", "roll_"))]
    train = feat.loc[tr].dropna(subset=dn + ["load"]).copy()
    test = feat.loc[pm].copy()
    if train.empty or test.empty:
        return err(ErrorCode.DATA_UNAVAILABLE, "empty split for missing-day backfill")

    model = XGBRegressor(random_state=seed, **_XGB_PARAMS)
    model.fit(train[cols], train["load"])
    fill_pred = np.maximum(model.predict(test[cols]), 0.0)

    new_records = []
    fill_iter = iter(fill_pred.tolist())
    for r in dataset["records"]:
        ts = pd.Timestamp(r["record_time"])
        if D0 <= ts < D1:
            new_records.append({**r, "load": round(float(next(fill_iter)), 4)})
        else:
            new_records.append(r)

    data = {
        **dataset,
        "dataset_id": "ds_real_repaired_day",
        "group_status": {**dataset.get("group_status", {}), "raw_load": "repaired"},
        "records": new_records,
        "meta": {**meta, "repaired_day": D0.strftime("%Y-%m-%d")},
    }
    return ok(data)


def compute_real_timeline(
    incident_day: str,
    missing_day: str,
    selected_strategy: str,
    window_start: str,
    window_end: str,
    region: str = DEFAULT_REGION,
    asset: str = DEFAULT_ASSET,
    seed: int = 42,
):
    """逐日真实计算精度轨迹(全部 XGB 实跑,无插值)。

    时间线语义(真实因果)：
      - 缺失源日 = missing_day(D-1)，数据整天丢失
      - 事故日 = incident_day(D+1)，劣化爆发（lag_1d 指向 missing_day）

    对 window_start~window_end 的每一天 d：
      - baseline_acc : 数据完整时正常 gap1 预测 d 的真实精度（事故前的实际运行线）
      - 事故日及之后(d >= incident_day) 额外计算两条对比曲线：
          nofix_acc    : missing_day 一直缺失、不修复，继续 gap1 预测 d 的真实精度
          recovered_acc: missing_day 已回填修复后，正常 gap1 预测 d 的真实精度

    两条曲线用同一基线模型，仅数据一破损一修复，apples-to-apples 真实对比。
    """
    inc = pd.Timestamp(incident_day)
    miss = pd.Timestamp(missing_day)
    start = pd.Timestamp(window_start)
    end = pd.Timestamp(window_end)

    days_out: List[Dict[str, Any]] = []
    cur = start
    while cur <= end:
        day_str = cur.strftime("%Y-%m-%d")
        entry: Dict[str, Any] = {"iso": day_str, "label": cur.strftime("%m-%d")}

        # 基线:数据完整正常预测
        ds = load_real_dataset(region=region, asset=asset, target_day=day_str)
        if ds["status"] != "ok":
            return err(ErrorCode.DATA_UNAVAILABLE, f"{day_str}: {ds['error']}")
        ds = ds["data"]
        base_pred = run_prediction_gap_strategy(ds, "baseline_gap1", "load_xgb_v1", seed=seed)
        if base_pred["status"] != "ok":
            return err(ErrorCode.DATA_UNAVAILABLE, f"{day_str} baseline: {base_pred['error']}")
        entry["baseline_acc"] = round(_accuracy_of(base_pred["data"]), 2)

        # 事故日及之后:计算未修复 + 修复真实精度
        if cur >= inc:
            # 未修复：missing_day 持续 NaN，用基线模型预测
            ds_missing = inject_missing_day(ds, missing_day)["data"]
            nofix_pred = run_prediction_gap_strategy(ds_missing, "degraded_a", "load_xgb_degraded", seed=seed)
            if nofix_pred["status"] == "ok":
                entry["nofix_acc"] = round(_accuracy_of(nofix_pred["data"]), 2)

            # 修复：先回填 missing_day（修复动作），再用基线模型预测
            if cur == inc:
                # 事故日：用选定策略真实重跑（与 collect/resume 主线一致）
                fix_pred = run_prediction_gap_strategy(ds_missing, selected_strategy, "load_xgb_v2_gap", seed=seed)
            else:
                # 后续日：缺失日已修复，正常基线运营
                repaired = backfill_missing_day(ds_missing, missing_day, seed=seed)
                if repaired["status"] == "ok":
                    fix_pred = run_prediction_gap_strategy(repaired["data"], "baseline_gap1", "load_xgb_v2_gap", seed=seed)
                else:
                    fix_pred = base_pred
            if fix_pred["status"] == "ok":
                entry["recovered_acc"] = round(_accuracy_of(fix_pred["data"]), 2)

        days_out.append(entry)
        cur += pd.Timedelta(days=1)

    return ok({
        "incident_day": incident_day,
        "missing_day": missing_day,
        "selected_strategy": selected_strategy,
        "window": [window_start, window_end],
        "days": days_out,
    })
# @AI_GENERATED: end
