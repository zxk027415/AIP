# @AI_GENERATED: Kiro v1.0
import sys, os, time, logging
import numpy as np
import pandas as pd
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
SD = os.path.dirname(os.path.abspath(__file__))
BD = os.path.dirname(SD)
sys.path.insert(0, BD)
WT = os.path.abspath(os.path.join(BD, '..', 'frontend', 'src', 'solar_fcst', 'wind_power_analysis_tool-master'))
sys.path.insert(0, WT)
from services.wind_execution_service import WindExecutionService
svc = WindExecutionService()
t0 = time.time()
SRCS = ['EC_10D', 'ENS_AVG']
# Node 1: Load data
print('=== Node 1: Load Data ===', flush=True)
r1 = svc.execute_function('load_dataset', {'station_id': 'WF0121', 'start_date': '2024-12-01', 'end_date': '2026-01-31', 'load_all_nwp': True, 'dataset_id': 'wind'}, {})
nwp = r1['nwp']
kc = ['timestamp', 'forecast_time']
for c in nwp.columns:
    if c not in kc and any(c.startswith(s+'_') for s in SRCS):
        kc.append(c)
r1['nwp'] = nwp[kc]
print(f'  NWP: {r1["nwp"].shape}, True: {r1["true"].shape}, cap={r1["capacity"]}', flush=True)
# Node 2: Feature Build
print('=== Node 2: Feature Build ===', flush=True)
r2 = svc.execute_function('wind_feature_build', {'nwp': r1['nwp'], 'true_data': r1['true']}, {})
print(f'  FM: {r2["feature_matrix"].shape}', flush=True)
# Node 3: Train/Predict Split
print('=== Node 3: Train Split ===', flush=True)
r3 = svc.execute_function('wind_train_split', {'feature_matrix': r2['feature_matrix'], 'true': r1['true'], 'feature_columns': r2['feature_columns'], 'train_start': '2024-12-01', 'train_end': '2025-12-31', 'predict_start': '2026-01-01', 'predict_end': '2026-01-31'}, {})
print(f'  Train: {r3["X_train"].shape}, Predict: {r3["X_predict"].shape}', flush=True)
# Node 4-5: Per-source WS + Power train
ctx = {**r3, 'capacity': r1['capacity'], 'sources': SRCS}
for src in SRCS:
    print(f'=== Node 4: WS Train ({src}) ===', flush=True)
    ctx['nwp_source'] = src
    ctx = svc.execute_function('wind_ws_xgb_train', ctx, {})
    print(f'=== Node 5: Power Train ({src}) ===', flush=True)
    ctx = svc.execute_function('wind_power_xgb_train', ctx, {})
# Node 6: Fusion Train
print('=== Node 6: Fusion Train ===', flush=True)
ctx = svc.execute_function('wind_fusion_train', ctx, {})
# Node 7-8: Per-source WS + Power predict
for src in SRCS:
    print(f'=== Node 7: WS Predict ({src}) ===', flush=True)
    ctx['nwp_source'] = src
    ctx = svc.execute_function('wind_ws_xgb_predict', ctx, {})
    print(f'=== Node 8: Power Predict ({src}) ===', flush=True)
    ctx = svc.execute_function('wind_power_xgb_predict', ctx, {})
# Node 9: Fusion Predict
print('=== Node 9: Fusion Predict ===', flush=True)
ctx = svc.execute_function('wind_fusion_predict', ctx, {})
# Node 10: Evaluate
print('=== Node 10: Evaluate ===', flush=True)
ps, pe = pd.to_datetime('2026-01-01'), pd.to_datetime('2026-01-31')
vt = r1['true'][(r1['true']['timestamp']>=ps)&(r1['true']['timestamp']<=pe)]
pred_df = pd.DataFrame({'timestamp': ctx['predict_timestamps'].values, 'prediction': ctx['final_predictions']})
pred_agg = pred_df.groupby('timestamp')['prediction'].mean().reset_index()
merged = pd.merge(vt[['timestamp','POWER']], pred_agg, on='timestamp', how='inner')
ctx['predictions'] = merged['prediction'].values
ctx['actuals'] = merged['POWER'].values
ctx['label'] = 'Jan2026'
result = svc.execute_function('wind_evaluate', ctx, {})
print(f'\n{"="*60}', flush=True)
print(f'Workflow Nodes Result | Time: {time.time()-t0:.1f}s', flush=True)
print(f'Metrics: {result["metrics"]}', flush=True)
print(f'{"="*60}', flush=True)
# @AI_GENERATED: end