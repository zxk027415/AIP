# @AI_GENERATED: Kiro v1.0
"""
迭代25：基于V10 + 简单早上缩放
- 使用V10的模型结构（无气象，只用历史功率）
- 预测后对早上时段(6-9点)应用固定缩放因子
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


def create_samples_v10(power_df, weather_df):
    """V10样本：D日功率 + D+1辐照度 + 时间"""
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
                
                X = np.column_stack([power_d0, irr_d1, hour_sin, hour_cos])
                y = day1_df['DC_POWER'].values
                
                X_list.append(X)
                y_list.append(y)
                meta_list.append({'inv': inv, 'date': day1})
    
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


def apply_morning_scale(y_pred, scale_6=0.6, scale_7=0.75, scale_8=0.9):
    """对早上时段应用缩放因子"""
    y_scaled = y_pred.copy()
    # 6点: 24-28 (4个点)
    y_scaled[:, 24:28] *= scale_6
    # 7点: 28-32
    y_scaled[:, 28:32] *= scale_7
    # 8点: 32-36
    y_scaled[:, 32:36] *= scale_8
    return y_scaled


def main():
    print("=" * 60)
    print("迭代25：V10基础 + 早上缩放")
    print("=" * 60)
    
    power_df, weather_df = load_data()
    X, y, meta = create_samples_v10(power_df, weather_df)
    print(f"样本: {len(X)}, 特征: {X.shape[2]}")
    
    dates = power_df['date'].unique()
    test_dates = set(dates[-7:])
    val_dates = set(dates[-14:-7])
    
    train_idx = [i for i, m in enumerate(meta) if m['date'] not in test_dates and m['date'] not in val_dates]
    val_idx = [i for i, m in enumerate(meta) if m['date'] in val_dates]
    test_idx = [i for i, m in enumerate(meta) if m['date'] in test_dates]
    
    X_train, y_train = X[train_idx], y[train_idx]
    X_val, y_val = X[val_idx], y[val_idx]
    X_test, y_test = X[test_idx], y[test_idx]
    test_meta = [meta[i] for i in test_idx]
    
    X_train_aug, y_train_aug = augment_data(X_train, y_train, n_augment=2)
    print(f"训练: {len(X_train_aug)}, 验证: {len(X_val)}, 测试: {len(X_test)}")
    
    # 归一化
    scaler_power = MinMaxScaler()
    scaler_irr = MinMaxScaler()
    
    all_power = np.concatenate([X_train_aug[:,:,0].flatten(), y_train_aug.flatten()])
    scaler_power.fit(all_power.reshape(-1, 1))
    scaler_irr.fit(X_train_aug[:,:,1].flatten().reshape(-1, 1))
    
    def scale_X(X_data):
        X_s = X_data.copy()
        X_s[:,:,0] = scaler_power.transform(X_data[:,:,0].reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
        X_s[:,:,1] = scaler_irr.transform(X_data[:,:,1].reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
        return X_s
    
    X_train_s = scale_X(X_train_aug)
    y_train_s = scaler_power.transform(y_train_aug.reshape(-1,1)).reshape(-1, POINTS_PER_DAY, 1)
    X_val_s = scale_X(X_val)
    X_test_s = scale_X(X_test)
    
    print("\n训练Seq2Seq...")
    model = build_seq2seq_model((POINTS_PER_DAY, X.shape[2]), POINTS_PER_DAY)
    
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
    model.fit(X_train_s, y_train_s, epochs=80, batch_size=32,
              validation_split=0.1, 
              callbacks=[EarlyStopping(patience=10, restore_best_weights=True),
                        ReduceLROnPlateau(patience=5, factor=0.5)],
              verbose=0)
    print("训练完成")
    
    # 在验证集上找最优缩放因子
    print("\n在验证集上优化早上缩放因子...")
    y_val_pred_s = model.predict(X_val_s, verbose=0)
    y_val_pred = scaler_power.inverse_transform(y_val_pred_s.reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    y_val_pred = np.maximum(y_val_pred, 0)
    
    best_mae = float('inf')
    best_scales = (1.0, 1.0, 1.0)
    
    for s6 in [0.5, 0.6, 0.7, 0.8]:
        for s7 in [0.6, 0.7, 0.8, 0.9]:
            for s8 in [0.8, 0.9, 1.0]:
                y_val_scaled = apply_morning_scale(y_val_pred, s6, s7, s8)
                mae = mean_absolute_error(y_val.flatten(), y_val_scaled.flatten())
                if mae < best_mae:
                    best_mae = mae
                    best_scales = (s6, s7, s8)
    
    print(f"最优缩放因子: 6点={best_scales[0]}, 7点={best_scales[1]}, 8点={best_scales[2]}")
    print(f"验证集MAE: {best_mae:.0f}")
    
    # 在测试集上预测
    y_pred_s = model.predict(X_test_s, verbose=0)
    y_pred_raw = scaler_power.inverse_transform(y_pred_s.reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    y_pred_raw = np.maximum(y_pred_raw, 0)
    
    y_pred = apply_morning_scale(y_pred_raw, *best_scales)
    y_pred = np.maximum(y_pred, 0)
    
    from collections import defaultdict
    daily_actual, daily_pred, daily_pred_raw, daily_irr = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for i, m in enumerate(test_meta):
        daily_actual[m['date']].append(y_test[i])
        daily_pred[m['date']].append(y_pred[i])
        daily_pred_raw[m['date']].append(y_pred_raw[i])
        daily_irr[m['date']].append(X_test[i, :, 1])
    
    all_actual, all_pred, all_pred_raw, all_irr = [], [], [], []
    print("\n场站级别:")
    for d in sorted(daily_actual.keys()):
        pa = np.sum(daily_actual[d], axis=0)
        pp = np.sum(daily_pred[d], axis=0)
        pp_raw = np.sum(daily_pred_raw[d], axis=0)
        pi = np.mean(daily_irr[d], axis=0)
        mae = mean_absolute_error(pa, pp)
        mae_raw = mean_absolute_error(pa, pp_raw)
        print(f"  {d}: MAE={mae:.0f} (原始: {mae_raw:.0f})")
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
    
    # 分析早上时段
    print("\n早上时段(6-9点)误差:")
    morning_actual, morning_pred, morning_pred_raw = [], [], []
    for i in range(len(all_actual)):
        hour = (i % 96) // 4
        if 6 <= hour < 9:
            morning_actual.append(all_actual[i])
            morning_pred.append(all_pred[i])
            morning_pred_raw.append(all_pred_raw[i])
    if morning_actual:
        morning_mae = mean_absolute_error(morning_actual, morning_pred)
        morning_mae_raw = mean_absolute_error(morning_actual, morning_pred_raw)
        print(f"  缩放后MAE: {morning_mae:.0f}")
        print(f"  原始MAE: {morning_mae_raw:.0f}")
    
    # 绘图
    fig, axes = plt.subplots(3, 1, figsize=(16, 10), height_ratios=[2, 2, 1])
    
    ax1 = axes[0]
    ax1.plot(all_actual, label='Actual', color='#2c3e50', linewidth=1)
    ax1.plot(all_pred_raw, label='Predicted (raw)', color='#e74c3c', linestyle='--', linewidth=1)
    ax1.set_ylabel('DC Power (kW)')
    ax1.set_title(f'Before Morning Scale - MAE: {total_mae_raw:.0f}')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    for day in range(7):
        ax1.axvspan(day*96+6*4, day*96+9*4, alpha=0.1, color='orange')
    
    ax2 = axes[1]
    ax2.plot(all_actual, label='Actual', color='#2c3e50', linewidth=1)
    ax2.plot(all_pred, label='Predicted (scaled)', color='#27ae60', linestyle='--', linewidth=1)
    ax2.set_ylabel('DC Power (kW)')
    ax2.set_title(f'After Morning Scale ({best_scales[0]}/{best_scales[1]}/{best_scales[2]}) - MAE: {total_mae:.0f}')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    for day in range(7):
        ax2.axvspan(day*96+6*4, day*96+9*4, alpha=0.1, color='green')
    
    ax3 = axes[2]
    ax3.fill_between(range(len(all_irr)), all_irr, alpha=0.3, color='#f39c12')
    ax3.plot(all_irr, label='D+1 Irradiation', color='#f39c12', linewidth=1)
    ax3.set_xlabel('Time Points')
    ax3.set_ylabel('Irradiation')
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_DIR, 'lstm_iter25_morning_scale.png'), dpi=150)
    print(f"\n保存: lstm_iter25_morning_scale.png")
    plt.close()


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
