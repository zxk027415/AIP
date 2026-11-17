"""独立运行一次单天回测的所有算子，打印每步的关键信息"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
import numpy as np

from services.operator_execution.router import OperatorRouter
from services.operator_execution.global_config_injector import GlobalConfigInjector

router = OperatorRouter()
router.auto_discover(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'services', 'operator_backends'))

gcfg = {
    "time_zone": "Asia/Shanghai",
    "operate_status": "backtest",
    "nowtime": "2026-03-04 00:00:00",
    "run_mode": "backtest",
    "backtest_mode": "rolling_retrain",
    "backtest_train_days": 30,
    "backtest_daily_horizon": 96,
    "backtest_gap_days": 1,
    "backtest_train_start": "2026-01-03 00:00:00",
    "backtest_train_end": "2026-03-02 00:00:00",
    "backtest_pred_start": "2026-03-04 00:00:00",
    "backtest_pred_end": "2026-03-05 00:00:00",
    "backtest_split_date": "2026-03-02 00:00:00",
    "backtest_apply_window_filter": True,
    "backtest_mask_target_values": True,
    "xgb_seed": 42,
    "xgb_nthread": 4,
    "auto_tune_n_trials": 1,
}
inj = GlobalConfigInjector(gcfg)

import json
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data/workflows_enhanced/workflow-20260511-optimal-505.json')) as f:
    wf = json.load(f)

configs = {n['data']['config']['functionId']: n['data']['config'] for n in wf['nodes']}

def call(fid, inputs):
    cfg = configs.get(fid, {})
    params = {k: v for k, v in cfg.items() if k not in ('functionId', 'operation', 'chartType', 'icon')}
    params = inj.inject(params)
    return router.execute(fid, params, inputs)

r = call('load_csv', {})
df = r['data']
print(f"1. load_csv: {len(df)} rows")

r = call('row_filter', {'data': df})
df = r['data']
ts = pd.to_datetime(df['record_time'])
pred_mask = ts >= '2026-03-04'
print(f"2. row_filter: {len(df)} rows, value NaN in pred: {df.loc[pred_mask, 'value'].isna().sum()}/{pred_mask.sum()}, has_helper: {'__backtest_true_target' in df.columns}")

r = call('resample_timeseries', {'data': df})
df = r['data']
ts = pd.to_datetime(df['record_time'])
pred_mask = ts >= '2026-03-04'
print(f"3. resample: {len(df)} rows, value NaN in pred: {df.loc[pred_mask, 'value'].isna().sum()}/{pred_mask.sum()}")

r = call('detect_outliers', {'data': df})
df = r['data']

r = call('handle_missing', {'data': df})
df = r['data']
ts = pd.to_datetime(df['record_time'])
pred_mask = ts >= '2026-03-04'
print(f"5. handle_missing: value NaN in pred: {df.loc[pred_mask, 'value'].isna().sum()}/{pred_mask.sum()}, value sample: {df.loc[pred_mask, 'value'].head(3).tolist()}")

for fid in ['extract_time_features', 'holiday_features', 'workday_features']:
    r = call(fid, {'data': df})
    df = r['data']

r = call('rolling_statistics', {'data': df})
df = r['data']

r = call('create_lag_features', {'data': df})
df = r['data']
ts = pd.to_datetime(df['record_time'])
pred_mask = ts >= '2026-03-04'
lag_cols = [c for c in df.columns if 'lag' in c.lower() and 'value' in c]
print(f"10. create_lag_features: lag_cols={lag_cols}")
for c in lag_cols[:3]:
    print(f"    {c} at pred[0:3]: {df.loc[pred_mask, c].head(3).tolist()}")

r = call('diff_features', {'data': df})
df = r['data']

r = call('train_test_split_ts', {'data': df})
print(f"\nsplit: train={len(r['train_features'])}, test={len(r['test_features'])}")
print(f"  train_target finite: {np.isfinite(r['train_target']).sum()}/{len(r['train_target'])}")
print(f"  test_target finite: {np.isfinite(r['test_target']).sum()}/{len(r['test_target'])}")
print(f"  test_target sample: {r['test_target'][:5].tolist()}")

test_f = r['test_features']
train_f = r['train_features']
numeric_cols = test_f.select_dtypes(include=[np.number]).columns.tolist()
print(f"\n  test_features cols: {len(numeric_cols)}")

# 对比 train 和 test 的特征统计
print("\n  特征质量对比 (train vs test):")
for c in ['value_lag_96', 'value_lag_192', 'value_rolling_mean_96']:
    if c in train_f.columns and c in test_f.columns:
        tr_mean = train_f[c].mean()
        te_mean = test_f[c].mean()
        tr_nan = train_f[c].isna().sum()
        te_nan = test_f[c].isna().sum()
        print(f"    {c}: train mean={tr_mean:.1f} nan={tr_nan}, test mean={te_mean:.1f} nan={te_nan}")
