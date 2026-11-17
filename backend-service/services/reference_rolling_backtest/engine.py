# -*- coding: utf-8 -*-
"""
按日滚动回测主循环（与 run_weihai_backtest.rolling_backtest 对齐）。
"""
from datetime import timedelta
import threading
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from loguru import logger

from .config import ReferenceBacktestConfig
from .data_io import load_wide_or_long_load_series, resolve_dataset_path
from .features import build_features
from .metrics import evaluate
from .models import compute_cv_fold_metrics, ensemble_predict, release_models, train_all_models


def _numeric_feature_cols(df: pd.DataFrame, drop_cols) -> List[str]:
    return [
        c
        for c in df.columns
        if c not in drop_cols
        and str(df[c].dtype) in ("float64", "float32", "int64", "int32")
    ]


def run_rolling_backtest(
    load_df: pd.DataFrame,
    pred_start: str,
    pred_end: str,
    cfg: Optional[ReferenceBacktestConfig] = None,
    cancel_event: Optional[threading.Event] = None,
) -> pd.DataFrame:
    """
    pred_end: 与参考脚本一致为 exclusive（不预测该日及之后）。
    """
    if cfg is None:
        cfg = ReferenceBacktestConfig()
    time_col, load_col, dh = cfg.time_field, cfg.load_field, int(cfg.daily_horizon)
    all_days = pd.date_range(pred_start, pred_end, freq="D", inclusive="left")
    results = []
    tr_days = int(cfg.train_days)

    for pred_day in all_days:
        if cancel_event is not None and cancel_event.is_set():
            break
        day_str = pred_day.strftime("%Y-%m-%d")
        # @AI_GENERATED
        # gap_days: 训练数据截止到 pred_day - 1 - gap_days
        # 默认 gap_days=1，即 D 日预测时只能用到 D-2 的数据（D-1 数据未采集完）
        train_end = pred_day - timedelta(days=1 + int(cfg.gap_days))
        # @AI_GENERATED: end
        train_start = train_end - timedelta(days=tr_days)
        mask_tr = (load_df[time_col] >= pd.Timestamp(train_start)) & (
            load_df[time_col] <= pd.Timestamp(train_end)
        )
        mask_te = (load_df[time_col] >= pred_day) & (
            load_df[time_col] < pred_day + timedelta(days=1)
        )
        train_raw = load_df[mask_tr].copy().reset_index(drop=True)
        test_raw = load_df[mask_te].copy().reset_index(drop=True)
        if len(train_raw) < tr_days * dh * cfg.min_train_row_frac:
            logger.warning(f"{day_str}: 训练数据不足 ({len(train_raw)} 行), 跳过")
            continue
        if len(test_raw) == 0:
            logger.warning(f"{day_str}: 无测试数据, 跳过")
            continue
        test_raw_masked = test_raw.copy()
        test_raw_masked[load_col] = np.nan
        combined = pd.concat([train_raw, test_raw_masked], ignore_index=True)
        feat_all = build_features(combined, time_col, load_col, dh)
        train_feat = feat_all[feat_all[time_col] <= pd.Timestamp(train_end)].copy()
        test_feat = feat_all[feat_all[time_col] >= pred_day].copy()
        drop_cols = {load_col, time_col, "date"}
        feature_cols = _numeric_feature_cols(train_feat, drop_cols)
        train_feat[feature_cols] = (
            train_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
        )
        test_feat[feature_cols] = test_feat[feature_cols].fillna(0).replace([np.inf, -np.inf], 0)
        x_tr = train_feat[feature_cols]
        y_tr = train_feat[load_col]
        # 预测日 load 在特征构造链上被掩为 NaN；评估/落库的真实值取原始 test_raw
        tr_ord = test_raw.sort_values(time_col).reset_index(drop=True)
        te_ord = test_feat.sort_values(time_col).reset_index(drop=True)
        n_te = min(len(tr_ord), len(te_ord))
        x_te = te_ord[feature_cols].iloc[:n_te]
        y_true_vec = tr_ord[load_col].to_numpy(dtype=float)[:n_te]
        logger.info(f"训练 {day_str}: train={len(x_tr)}, test={n_te}")
        cv_fold_metrics = compute_cv_fold_metrics(x_tr, y_tr, n_splits=int(cfg.n_splits))
        models, flist, weights = train_all_models(x_tr, y_tr, forecast_length=dh, cfg=cfg)
        y_pred, single_preds = ensemble_predict(models, flist, weights, x_te)
        y_pred = np.asarray(y_pred, dtype=float).reshape(-1)
        mlen = int(min(y_pred.size, y_true_vec.size))
        y_pred = y_pred[:mlen]
        y_true_vec = y_true_vec[:mlen]
        rt = te_ord[time_col].values[:mlen]
        row: Dict[str, Any] = {
            "record_time": rt,
            "true": y_true_vec,
            "pred": y_pred,
            "pred_day": day_str,
            "cv_fold_metrics": [cv_fold_metrics for _ in range(mlen)],
        }
        keymap = {"xgb": "pred_xgb", "lgb": "pred_lgb", "catb": "pred_catb", "ridge": "pred_ridge"}
        for k, col in keymap.items():
            if k in single_preds and single_preds[k] is not None:
                sp = np.asarray(single_preds[k], dtype=float).reshape(-1)[:mlen]
                row[col] = sp
        results.append(pd.DataFrame(row))
        m = evaluate(y_true_vec, y_pred, label=day_str)
        logger.info(
            f"  {day_str} Ensemble: SMAPE={m['SMAPE']:.2f}%  MAE={m['MAE']:.1f}  RMSE={m['RMSE']:.1f}"
        )
        release_models(models)

    if not results:
        return pd.DataFrame()
    return pd.concat(results, ignore_index=True)


def run_from_file(
    file_path: str,
    backend_dir: str,
    pred_start: str,
    pred_end: str,
    cfg: Optional[ReferenceBacktestConfig] = None,
    cancel_event: Optional[threading.Event] = None,
) -> pd.DataFrame:
    import os

    abs_path = resolve_dataset_path(file_path, backend_dir)
    if not abs_path or not os.path.exists(abs_path):
        raise FileNotFoundError(f"数据文件未找到: {file_path} (尝试解析为 {abs_path})")
    c = cfg or ReferenceBacktestConfig()
    df = load_wide_or_long_load_series(
        abs_path, parent_id=c.parent_id, child_id=c.child_id
    )
    return run_rolling_backtest(df, pred_start, pred_end, c, cancel_event=cancel_event)


def to_platform_daily_results(result_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """转为 workflows_enhanced 回测 API 的 daily_results 项。"""
    if result_df is None or result_df.empty:
        return []
    from .metrics import evaluate as ev

    out: List[Dict[str, Any]] = []
    for day in sorted(result_df["pred_day"].unique()):
        g = result_df[result_df["pred_day"] == day]
        yt = g["true"].to_numpy(dtype=float)
        yp = g["pred"].to_numpy(dtype=float)
        m = ev(yt, yp, str(day))
        out.append(
            {
                "date": str(day),
                "status": "success",
                "duration": 0.0,
                "metrics": {
                    "smape": m["SMAPE"],
                    "mae": m["MAE"],
                    "rmse": m["RMSE"],
                },
                "y_true": yt.tolist(),
                "y_pred": yp.tolist(),
                "point_count": len(yp),
                "cv_fold_metrics": (
                    g["cv_fold_metrics"].iloc[0]
                    if "cv_fold_metrics" in g.columns and len(g) > 0
                    else []
                ),
            }
        )
    return out
