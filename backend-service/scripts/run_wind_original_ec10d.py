# @AI_GENERATED: Kiro v1.0
"""
用原始代码跑 EC_10D 单源 XGBoost Stacking
训练集: 2024-12-01 ~ 2025-12-31
验证集: 2026-01-01 ~ 2026-01-31
"""
import sys, os, logging, time
import pandas as pd
import numpy as np

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 加入原工程路径
wind_tool = os.path.join(os.path.dirname(__file__), '..', '..', 'frontend', 'src', 'solar_fcst', 'wind_power_analysis_tool-master')
sys.path.insert(0, wind_tool)

from backend.data_loader import DataLoader
from backend.feature_engineer import PolarsFeatureEngineer
from backend.models.custom_model_epf import CustomModelEpfWrapper
from backend.utils import resample_both_dimensions

start_time = time.time()

# 参数
station_id = 'WF0121'
train_start = '2024-12-01'
train_end = '2025-12-31'
predict_start = '2026-01-01'
predict_end = '2026-01-31'
sources = ['EC_10D_WS']
feature_groups = ['raw_meteorological', 'time_features', 'business_features', 'statistical_features']

logger.info(f'场站: {station_id}')
logger.info(f'训练: {train_start} ~ {train_end}')
logger.info(f'验证: {predict_start} ~ {predict_end}')
logger.info(f'气象源: EC_10D, 模型: XGBoost Stacking')

# Step 1: 加载数据
logger.info('Step 1: 加载数据')
loader = DataLoader()
capacity = loader.get_station_capacity(station_id)
logger.info(f'容量: {capacity} MW')

raw_data = loader.load_station_data(
    station_id=station_id,
    start_date=train_start,
    end_date=predict_end,
    load_all=True
)

# 真实数据过滤为整点
true_df = raw_data['true']
true_df = true_df[true_df['timestamp'].dt.minute == 0]
true_df.reset_index(inplace=True, drop=True)

processed_data = {'nwp': raw_data['nwp'], 'true': true_df}
logger.info(f'NWP: {raw_data["nwp"].shape}, True: {true_df.shape}')

# Step 2: 特征工程
logger.info('Step 2: 特征工程')
engineer = PolarsFeatureEngineer(processed_data)
feature_matrix = engineer.build_feature_matrix(feature_groups)
features_train = [x for x in feature_matrix.columns if x not in ['timestamp', 'forecast_time']]

# Step 3: 过滤训练数据
logger.info('Step 3: 过滤训练数据')
ts = pd.to_datetime(train_start)
te = pd.to_datetime(train_end)
train_mask = (true_df['timestamp'] >= ts) & (true_df['timestamp'] <= te)

train_data = pd.merge(true_df[train_mask], feature_matrix, on='timestamp', how='outer')
X_train = train_data[features_train]
y_train = train_data[['WS', 'WS_min', 'WS_median', 'WS_max', 'POWER']]
logger.info(f'训练数据: X={X_train.shape}, y={y_train.shape}')

# Step 4: 训练
logger.info('Step 4: 训练 XGBoost Stacking (EC_10D 单源)')
model = CustomModelEpfWrapper(farm_id=station_id, capacity=capacity)
train_result = model.train(X_train, y_train, param_grid=None, enable_search=True)

train_metrics = train_result.get('metrics', {})
logger.info(f'训练指标: {train_metrics}')

# Step 5: 预测
logger.info('Step 5: 预测验证集')
ps = pd.to_datetime(predict_start)
pe = pd.to_datetime(predict_end)
predict_mask = (feature_matrix['timestamp'] >= ps) & (feature_matrix['timestamp'] <= pe)
X_predict = feature_matrix[predict_mask][features_train]
logger.info(f'预测数据: {X_predict.shape}')

predictions_raw = model.predict(X_predict)

# predict() 输出已经是原始功率值（修复后不再多乘capacity）
predictions_power = np.clip(predictions_raw, 0, capacity)
logger.info(f'预测值范围: [{predictions_power.min():.1f}, {predictions_power.max():.1f}]')

df_pred = pd.DataFrame({
    'timestamp': feature_matrix[predict_mask]['timestamp'].values,
    'prediction': predictions_power,
    'forecast_time': feature_matrix[predict_mask]['forecast_time'].values,
})

# resample + 24H 过滤（原工程逻辑）
df_pred = resample_both_dimensions(df_pred, '15min')
df_pred['dist'] = (df_pred['timestamp'] - df_pred['forecast_time']).dt.total_seconds() / 3600
df_pred = df_pred[df_pred['dist'].isin(range(24))]
df_pred = pd.merge(df_pred, true_df[['timestamp', 'POWER']], on='timestamp', how='left')

valid = ~(pd.isna(df_pred['POWER']) | pd.isna(df_pred['prediction']))
actual = df_pred['POWER'][valid]
pred = df_pred['prediction'][valid]
logger.info(f'真实值范围: [{actual.min():.1f}, {actual.max():.1f}], 预测值范围: [{pred.min():.1f}, {pred.max():.1f}]')

from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

if len(actual) > 0:
    rmse = np.sqrt(mean_squared_error(actual, pred))
    mae = mean_absolute_error(actual, pred)
    r2 = r2_score(actual, pred)
    rmse_norm = rmse / capacity if capacity else rmse
    mae_norm = mae / capacity if capacity else mae

    elapsed = time.time() - start_time

    print('\n' + '=' * 60)
    print('原始代码 EC_10D XGBoost Stacking 结果')
    print('=' * 60)
    print(f'场站: {station_id}, 容量: {capacity} MW')
    print(f'训练: {train_start} ~ {train_end}')
    print(f'验证: {predict_start} ~ {predict_end}')
    print(f'训练样本: {len(X_train)}, 预测样本: {len(df_pred)}, 有效样本: {len(actual)}')
    print(f'\n训练指标 (5折CV):')
    for k, v in train_metrics.items():
        print(f'  {k}: {v:.6f}')
    print(f'\n验证指标 (2026年1月):')
    print(f'  RMSE:           {rmse:.4f}')
    print(f'  MAE:            {mae:.4f}')
    print(f'  R2:             {r2:.6f}')
    print(f'  RMSE(归一化):   {rmse_norm:.6f}')
    print(f'  MAE(归一化):    {mae_norm:.6f}')
    print(f'\n耗时: {elapsed:.1f}秒')
    print('=' * 60)
else:
    print('无有效预测数据')
# @AI_GENERATED: end
