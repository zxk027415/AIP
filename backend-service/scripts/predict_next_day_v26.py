# @AI_GENERATED: Kiro v1.0
"""
迭代26：基于天气状况的自适应模型
- 根据D+1辐照度预报判断天气类型（晴天/多云/阴天）
- 对不同天气类型应用不同的预测策略
- 多云/阴天时降低预测值
"""

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings('ignore')
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')
POINTS_PER_DAY = 96


def load_data():
    print("加载数据...")
    power_df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    power_df['DATE_TIME'] = pd.to_datetime(power_df['DATE_TIME'], dayfirst=True)
    power_df['date'] = power_df['DATE_TIME'].dt.date
    power_df['hour'] = power_df['DATE_TIME'].dt.hour
    power_df['minute'] = power_df['DATE_TIME'].dt.minute
    
    weather_df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Weather_Sensor_Data.csv'))
    weather_df['DATE_TIME'] = pd.to_datetime(weather_df['DATE_TIME'], dayfirst=True)
    weather_df['date'] = weather_df['DATE_TIME'].dt.date
    
    return power_df, weather_df


def get_daily_irradiation(weather_df, date):
    day_weather = weather_df[weather_df['date'] == date].sort_values('DATE_TIME')
    if len(day_weather) < POINTS_PER_DAY:
        return None
    return day_weather.head(POINTS_PER_DAY)['IRRADIATION'].values


def classify_weather(irr_sum, avg_irr):
    """根据日辐照度总和判断天气类型"""
    ratio = irr_sum / avg_irr if avg_irr > 0 else 0
    if ratio < 0.6:
        return 'cloudy', ratio
    elif ratio < 0.85:
        return 'partly_cloudy', ratio
    else:
        return 'sunny', ratio


def create_samples_with_weather(power_df, weather_df, avg_daily_irr):
    """创建带天气类型特征的样本"""
    inverters = power_df['SOURCE_KEY'].unique()
    dates = power_df['date'].unique()
    
    X_list, y_list, meta_list = [], [], []
    
    for inv in inverters:
        inv_df = power_df[power_df['SOURCE_KEY'] == inv].sort_values('DATE_TIME')
        
        for i in range(len(dates) - 1):
            day0 = dates[i]
            day1 = dates[i + 1]
            
            day0_df = inv_df[inv_df['date'] == day0]
            day1_df = inv_df[inv_df['date'] == day1]
            irr_d1 = get_daily_irradiation(weather_df, day1)
            
            if len(day0_df) == POINTS_PER_DAY and len(day1_df) == POINTS_PER_DAY and irr_d1 is not None:
                power_d0 = day0_df['DC_POWER'].values
                hours = (day0_df['hour'] + day0_df['minute']/60).values
                hour_sin = np.sin(2 * np.pi * hours / 24)
                hour_cos = np.cos(2 * np.pi * hours / 24)
                
                # 计算D+1天气类型
                irr_sum = irr_d1.sum()
                weather_type, weather_ratio = classify_weather(irr_sum, avg_daily_irr)
                
                # 天气特征：辐照度比值（相对于平均值）
                weather_factor = np.full(POINTS_PER_DAY, weather_ratio)
                
                X = np.column_stack([
                    power_d0,       # D日功率
                    irr_d1,         # D+1辐照度
                    hour_sin,
                    hour_cos,
                    weather_factor  # 天气因子
                ])
                y = day1_df['DC_POWER'].values
                
                X_list.append(X)
                y_list.append(y)
                meta_list.append({
                    'inv': inv, 
                    'date': day1, 
                    'weather': weather_type,
                    'weather_ratio': weather_ratio
                })
    
    return np.array(X_list), np.array(y_list), meta_list


def augment_data(X, y, n_augment=2):
    X_aug, y_aug = [X], [y]
    for _ in range(n_augment):
        noise_scale = 0.02
        X_noisy = X.copy()
        X_noisy[:,:,0] = X[:,:,0] * (1 + np.random.randn(*X[:,:,0].shape) * noise_scale)
        X_noisy[:,:,0] = np.maximum(X_noisy[:,:,0], 0)
        y_noisy = y * (1 + np.random.randn(*y.shape) * noise_scale)
        y_noisy = np.maximum(y_noisy, 0)
        X_aug.append(X_noisy)
        y_aug.append(y_noisy)
        
        scale = np.random.uniform(0.9, 1.1, size=(X.shape[0], 1))
        X_scaled = X.copy()
        X_scaled[:,:,0] = X[:,:,0] * scale
        y_scaled = y * scale
        X_aug.append(X_scaled)
        y_aug.append(y_scaled)
    return np.concatenate(X_aug), np.concatenate(y_aug)


def build_seq2seq_model(input_shape, output_len):
    from tensorflow.keras.models import Model
    from tensorflow.keras.layers import Input, LSTM, Dense, RepeatVector, TimeDistributed
    
    encoder_input = Input(shape=input_shape)
    encoder = LSTM(128, return_state=True)
    _, state_h, state_c = encoder(encoder_input)
    
    decoder_input = RepeatVector(output_len)(state_h)
    decoder_lstm = LSTM(128, return_sequences=True)
    decoder_output = decoder_lstm(decoder_input, initial_state=[state_h, state_c])
    
    output = TimeDistributed(Dense(64, activation='relu'))(decoder_output)
    output = TimeDistributed(Dense(1))(output)
    
    model = Model(encoder_input, output)
    model.compile(optimizer='adam', loss='huber')
    return model


def apply_weather_correction(y_pred, weather_ratio):
    """根据天气比值应用修正"""
    # 如果天气比值低于1（多云/阴天），降低预测值
    if weather_ratio < 0.85:
        # 修正系数：天气越差，修正越大
        correction = 0.85 + 0.15 * weather_ratio  # 范围约0.85-1.0
        return y_pred * correction
    return y_pred


def main():
    print("=" * 60)
    print("迭代26：天气自适应模型")
    print("=" * 60)
    
    power_df, weather_df = load_data()
    
    # 计算训练集平均日辐照度
    dates = power_df['date'].unique()
    test_dates = set(dates[-7:])
    train_dates = [d for d in dates if d not in test_dates]
    
    train_daily_irr = []
    for d in train_dates:
        irr = get_daily_irradiation(weather_df, d)
        if irr is not None:
            train_daily_irr.append(irr.sum())
    avg_daily_irr = np.mean(train_daily_irr)
    print(f"训练集平均日辐照度: {avg_daily_irr:.2f}")
    
    X, y, meta = create_samples_with_weather(power_df, weather_df, avg_daily_irr)
    print(f"样本: {len(X)}, 特征: {X.shape[2]}")
    
    train_idx = [i for i, m in enumerate(meta) if m['date'] not in test_dates]
    test_idx = [i for i, m in enumerate(meta) if m['date'] in test_dates]
    
    X_train, y_train = X[train_idx], y[train_idx]
    X_test, y_test = X[test_idx], y[test_idx]
    test_meta = [meta[i] for i in test_idx]
    
    # 显示测试集天气
    print("\n测试集天气情况:")
    for d in sorted(test_dates):
        day_meta = [m for m in test_meta if m['date'] == d]
        if day_meta:
            print(f"  {d}: {day_meta[0]['weather']} (ratio={day_meta[0]['weather_ratio']:.2f})")
    
    X_train_aug, y_train_aug = augment_data(X_train, y_train, n_augment=2)
    print(f"\n增强后训练: {len(X_train_aug)}, 测试: {len(X_test)}")
    
    # 归一化
    scaler_power = MinMaxScaler()
    scaler_irr = MinMaxScaler()
    
    all_power = np.concatenate([X_train_aug[:,:,0].flatten(), y_train_aug.flatten()])
    scaler_power.fit(all_power.reshape(-1, 1))
    scaler_irr.fit(X_train_aug[:,:,1].flatten().reshape(-1, 1))
    
    X_train_s = X_train_aug.copy()
    X_train_s[:,:,0] = scaler_power.transform(X_train_aug[:,:,0].reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    X_train_s[:,:,1] = scaler_irr.transform(X_train_aug[:,:,1].reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    y_train_s = scaler_power.transform(y_train_aug.reshape(-1,1)).reshape(-1, POINTS_PER_DAY, 1)
    
    X_test_s = X_test.copy()
    X_test_s[:,:,0] = scaler_power.transform(X_test[:,:,0].reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    X_test_s[:,:,1] = scaler_irr.transform(X_test[:,:,1].reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    
    print("\n训练Seq2Seq...")
    model = build_seq2seq_model((POINTS_PER_DAY, X.shape[2]), POINTS_PER_DAY)
    
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
    model.fit(X_train_s, y_train_s, epochs=80, batch_size=32,
              validation_split=0.1, 
              callbacks=[EarlyStopping(patience=10, restore_best_weights=True),
                        ReduceLROnPlateau(patience=5, factor=0.5)],
              verbose=0)
    print("训练完成")
    
    y_pred_s = model.predict(X_test_s, verbose=0)
    y_pred_raw = scaler_power.inverse_transform(y_pred_s.reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    y_pred_raw = np.maximum(y_pred_raw, 0)
    
    # 应用天气修正
    y_pred = y_pred_raw.copy()
    for i, m in enumerate(test_meta):
        y_pred[i] = apply_weather_correction(y_pred_raw[i], m['weather_ratio'])
    
    from collections import defaultdict
    daily_actual, daily_pred, daily_pred_raw, daily_irr = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    daily_weather = {}
    for i, m in enumerate(test_meta):
        daily_actual[m['date']].append(y_test[i])
        daily_pred[m['date']].append(y_pred[i])
        daily_pred_raw[m['date']].append(y_pred_raw[i])
        daily_irr[m['date']].append(X_test[i, :, 1])
        daily_weather[m['date']] = m['weather']
    
    all_actual, all_pred, all_pred_raw, all_irr = [], [], [], []
    print("\n场站级别:")
    for d in sorted(daily_actual.keys()):
        pa = np.sum(daily_actual[d], axis=0)
        pp = np.sum(daily_pred[d], axis=0)
        pp_raw = np.sum(daily_pred_raw[d], axis=0)
        pi = np.mean(daily_irr[d], axis=0)
        mae = mean_absolute_error(pa, pp)
        mae_raw = mean_absolute_error(pa, pp_raw)
        weather = daily_weather[d]
        print(f"  {d} [{weather:>13}]: MAE={mae:.0f} (原始: {mae_raw:.0f})")
        all_actual.extend(pa)
        all_pred.extend(pp)
        all_pred_raw.extend(pp_raw)
        all_irr.extend(pi)
    
    total_mae = mean_absolute_error(all_actual, all_pred)
    total_mae_raw = mean_absolute_error(all_actual, all_pred_raw)
    total_rmse = np.sqrt(mean_squared_error(all_actual, all_pred))
    print(f"\n总体: MAE={total_mae:.0f} (原始: {total_mae_raw:.0f})")
    print(f"RMSE: {total_rmse:.0f}")
    print(f"对比V10: MAE=14,953")
    
    # 绘图
    fig, axes = plt.subplots(3, 1, figsize=(16, 10), height_ratios=[2, 2, 1])
    
    ax1 = axes[0]
    ax1.plot(all_actual, label='Actual', color='#2c3e50', linewidth=1)
    ax1.plot(all_pred_raw, label='Predicted (raw)', color='#e74c3c', linestyle='--', linewidth=1)
    ax1.set_ylabel('DC Power (kW)')
    ax1.set_title(f'Before Weather Correction - MAE: {total_mae_raw:.0f}')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    ax2 = axes[1]
    ax2.plot(all_actual, label='Actual', color='#2c3e50', linewidth=1)
    ax2.plot(all_pred, label='Predicted (corrected)', color='#27ae60', linestyle='--', linewidth=1)
    ax2.set_ylabel('DC Power (kW)')
    ax2.set_title(f'After Weather Correction - MAE: {total_mae:.0f}')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    # 标记多云天
    for day_idx, d in enumerate(sorted(daily_actual.keys())):
        if daily_weather[d] == 'partly_cloudy':
            start = day_idx * 96
            end = (day_idx + 1) * 96
            ax1.axvspan(start, end, alpha=0.1, color='gray')
            ax2.axvspan(start, end, alpha=0.1, color='gray')
    
    ax3 = axes[2]
    ax3.fill_between(range(len(all_irr)), all_irr, alpha=0.3, color='#f39c12')
    ax3.plot(all_irr, label='D+1 Irradiation', color='#f39c12', linewidth=1)
    ax3.set_xlabel('Time Points')
    ax3.set_ylabel('Irradiation')
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_DIR, 'lstm_iter26_weather_adaptive.png'), dpi=150)
    print(f"\n保存: lstm_iter26_weather_adaptive.png")
    plt.close()


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
