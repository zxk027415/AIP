# @AI_GENERATED: Kiro v1.0
import sys, os, logging, time
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('w2s')
SD = os.path.dirname(os.path.abspath(__file__))
BD = os.path.dirname(SD)
WT = os.path.abspath(os.path.join(BD, '..', 'frontend', 'src', 'solar_fcst', 'wind_power_analysis_tool-master'))
sys.path.insert(0, WT)
from backend.data_loader import DataLoader
from backend.feature_engineer import PolarsFeatureEngineer
from backend.models.custom_model_epf import CustomModelEpfWrapper
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
t0 = time.time()
SID, SRCS = 'WF0121', ['EC_10D', 'ENS_AVG']
FG = ['raw_meteorological', 'time_features', 'business_features', 'statistical_features']
log.info(f'{SID} {SRCS}')
loader = DataLoader()
cap = loader.get_station_capacity(SID)
raw = loader.load_station_data(SID, '2024-12-01', '2026-01-31', load_all=True)
tdf = raw['true']
tdf = tdf[tdf['timestamp'].dt.minute == 0].reset_index(drop=True)
nwp = raw['nwp']
kc = ['timestamp', 'forecast_time']
for c in nwp.columns:
    if c not in kc and any(c.startswith(s+'_') for s in SRCS):
        kc.append(c)
nwp = nwp[kc]
log.info(f'NWP {nwp.shape}')
eng = PolarsFeatureEngineer({'nwp': nwp, 'true': tdf})
fm = eng.build_feature_matrix(FG)
fc = [c for c in fm.columns if c not in ['timestamp', 'forecast_time']]
ts, te = pd.to_datetime('2024-12-01'), pd.to_datetime('2025-12-31')
tm = (tdf['timestamp'] >= ts) & (tdf['timestamp'] <= te)
td = pd.merge(tdf[tm], fm, on='timestamp', how='outer')
Xt, yt = td[fc], td[['WS','WS_min','WS_median','WS_max','POWER']]
log.info(f'Train {Xt.shape}')
mdl = CustomModelEpfWrapper(farm_id=SID, capacity=cap)
r = mdl.train(Xt, yt, enable_search=True)
log.info(f'CV: {r.get("metrics",{})}')
ds, de = pd.to_datetime('2025-12-01'), pd.to_datetime('2025-12-31')
dm = (fm['timestamp']>=ds)&(fm['timestamp']<=de)
pd_dec = np.clip(mdl.predict(fm[dm][fc]),0,cap)
dd = pd.DataFrame({'timestamp':fm[dm]['timestamp'].values,'prediction':pd_dec})
da = dd.groupby('timestamp')['prediction'].mean().reset_index()
dt = tdf[(tdf['timestamp']>=ds)&(tdf['timestamp']<=de)]
dec = pd.merge(dt[['timestamp','POWER']], da, on='timestamp', how='inner')
ps, pe = pd.to_datetime('2026-01-01'), pd.to_datetime('2026-01-31')
vm = (fm['timestamp']>=ps)&(fm['timestamp']<=pe)
pd_val = np.clip(mdl.predict(fm[vm][fc]),0,cap)
vd = pd.DataFrame({'timestamp':fm[vm]['timestamp'].values,'prediction':pd_val})
va = vd.groupby('timestamp')['prediction'].mean().reset_index()
vt = tdf[(tdf['timestamp']>=ps)&(tdf['timestamp']<=pe)]
val = pd.merge(vt[['timestamp','POWER']], va, on='timestamp', how='inner')
def mx(a,p,lb):
    v=~(np.isnan(a)|np.isnan(p)); a2,p2=a[v],p[v]
    rm=np.sqrt(mean_squared_error(a2,p2)); ma=mean_absolute_error(a2,p2); r2=r2_score(a2,p2)
    print(f'{lb}: RMSE={rm:.2f} MAE={ma:.2f} R2={r2:.4f} RMSE%={rm/cap*100:.2f}%',flush=True)
    return {'rmse':rm,'mae':ma,'r2':r2}
print(f'\n{"="*60}',flush=True)
print(f'EC_10D+ENS_AVG XGB | {SID} cap={cap}',flush=True)
dm2=mx(dec['POWER'].values,dec['prediction'].values,'Dec25')
vm2=mx(val['POWER'].values,val['prediction'].values,'Jan26')
print(f'CV: {r.get("metrics",{})}',flush=True)
print(f'Time: {time.time()-t0:.1f}s',flush=True)
print(f'{"="*60}',flush=True)
fig,axes=plt.subplots(2,1,figsize=(16,10),dpi=100)
ax=axes[0]
ax.plot(dec['timestamp'],dec['POWER'],'b-',alpha=0.7,lw=0.8,label='Actual')
ax.plot(dec['timestamp'],dec['prediction'],'r-',alpha=0.7,lw=0.8,label='Predicted')
ax.set_title(f'Train Dec25 RMSE={dm2["rmse"]:.0f} R2={dm2["r2"]:.4f}')
ax.set_ylabel('Power(MW)'); ax.legend(); ax.grid(True,alpha=0.3)
ax=axes[1]
ax.plot(val['timestamp'],val['POWER'],'b-',alpha=0.7,lw=0.8,label='Actual')
ax.plot(val['timestamp'],val['prediction'],'r-',alpha=0.7,lw=0.8,label='Predicted')
ax.set_title(f'Val Jan26 RMSE={vm2["rmse"]:.0f} R2={vm2["r2"]:.4f}')
ax.set_ylabel('Power(MW)'); ax.set_xlabel('Time'); ax.legend(); ax.grid(True,alpha=0.3)
plt.tight_layout()
out=os.path.join(BD,'data','demo','wind_2source_xgb.png')
plt.savefig(out,bbox_inches='tight')
print(f'Plot: {out}',flush=True)
plt.close()
# @AI_GENERATED: end