# @AI_GENERATED: Kiro v1.0
"""
迭代21：后处理修正 - 基于训练集学习各时段的效率修正系数
- 保持V19的模型结构
- 训练后分析各时段的预测偏差
- 应用时段修正系数
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


def create_samples(power_df, weather_df):
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


def learn_hourly_correction(y_actual, y_pred):
    """从验证集学习每小时的修正系数"""
    corrections = {}
    for h in range(24):
        start_idx = h * 4
        end_idx = (h + 1) * 4
        
        actual_h = y_actual[:, start_idx:end_idx].flatten()
        pred_h = y_pred[:, start_idx:end_idx].flatten()
        
        # 只考虑有功率的时段
        mask = (actual_h > 100) | (pred_h > 100)
        if mask.sum() > 0:
            actual_valid = actual_h[mask]
            pred_valid = pred_h[mask]
            
            # 计算修正系数：actual / pred 的中位数
            ratios = actual_valid / (pred_valid + 1)
            correction = np.median(ratios)
            correction = np.clip(correction, 0.5, 2.0)  # 限制范围
        else:
            correction = 1.0
        
        corrections[h] = correction
    
    return corrections


def apply_correction(y_pred, corrections):
    """应用小时修正系数"""
    y_corrected = y_pred.copy()
    for h in range(24):
        start_idx = h * 4
        end_idx = (h + 1) * 4
        y_corrected[:, start_idx:end_idx] *= corrections[h]
    return y_corrected


def main():
    print("=" * 60)
    print("迭代21：后处理时段修正")
    print("=" * 60)
    
    power_df, weather_df = load_data()
    X, y, meta = create_samples(power_df, weather_df)
    print(f"样本: {len(X)}, 特征: {X.shape[2]}")
    
    dates = power_df['date'].unique()
    test_dates = set(dates[-7:])
    val_dates = set(dates[-14:-7])  # 用前一周做验证集学习修正系数
    
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
    
    # 在验证集上学习修正系数
    print("\n学习时段修正系数...")
    y_val_pred_s = model.predict(X_val_s, verbose=0)
    y_val_pred = scaler_power.inverse_transform(y_val_pred_s.reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    y_val_pred = np.maximum(y_val_pred, 0)
    
    corrections = learn_hourly_correction(y_val, y_val_pred)
    print("各小时修正系数:")
    for h in range(6, 18):
        print(f"  {h:2d}点: {corrections[h]:.3f}")
    
    # 在测试集上预测
    y_pred_s = model.predict(X_test_s, verbose=0)
    y_pred_raw = scaler_power.inverse_transform(y_pred_s.reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    y_pred_raw = np.maximum(y_pred_raw, 0)
    
    # 应用修正
    y_pred = apply_correction(y_pred_raw, corrections)
    y_pred = np.maximum(y_pred, 0)
    
    from collections import defaultdict
    daily_actual, daily_pred, daily_pred_raw, daily_irr = defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
    for i, m in enumerate(test_meta):
        daily_actual[m['date']].append(y_test[i])
        daily_pred[m['date']].append(y_pred[i])
        daily_pred_raw[m['date']].append(y_pred_raw[i])
        daily_irr[m['date']].append(X_test[i, :, 1])
    
    all_actual, all_pred, all_pred_raw, all_irr = [], [], [], []
    print("\n场站级别 (修正后):")
    for d in sorted(daily_actual.keys()):
        pa = np.sum(daily_actual[d], axis=0)
        pp = np.sum(daily_pred[d], axis=0)
        pp_raw = np.sum(daily_pred_raw[d], axis=0)
        pi = np.mean(daily_irr[d], axis=0)
        mae = mean_absolute_error(pa, pp)
        mae_raw = mean_absolute_error(pa, pp_raw)
        print(f"  {d}: MAE={mae:.0f} (修正前: {mae_raw:.0f})")
        all_actual.extend(pa)
        all_pred.extend(pp)
        all_pred_raw.extend(pp_raw)
        all_irr.extend(pi)
    
    total_mae = mean_absolute_error(all_actual, all_pred)
    total_mae_raw = mean_absolute_error(all_actual, all_pred_raw)
    total_rmse = np.sqrt(mean_squared_error(all_actual, all_pred))
    print(f"\n总体: MAE={total_mae:.0f} (修正前: {total_mae_raw:.0f})")
    print(f"RMSE: {total_rmse:.0f}")
    print(f"对比V19: MAE=14,582-17,093")
    
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
        print(f"  修正后MAE: {morning_mae:.0f}")
        print(f"  修正前MAE: {morning_mae_raw:.0f}")
    
    # 绘图
    fig, axes = plt.subplots(3, 1, figsize=(16, 10), height_ratios=[2, 2, 1])
    
    # 1. 修正前
    ax1 = axes[0]
    ax1.plot(all_actual, label='Actual', color='#2c3e50', linewidth=1)
    ax1.plot(all_pred_raw, label='Predicted (raw)', color='#e74c3c', linestyle='--', linewidth=1)
    ax1.set_ylabel('DC Power (kW)')
    ax1.set_title(f'Before Correction - MAE: {total_mae_raw:.0f}')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    for day in range(7):
        ax1.axvspan(day*96+6*4, day*96+9*4, alpha=0.1, color='orange')
    
    # 2. 修正后
    ax2 = axes[1]
    ax2.plot(all_actual, label='Actual', color='#2c3e50', linewidth=1)
    ax2.plot(all_pred, label='Predicted (corrected)', color='#27ae60', linestyle='--', linewidth=1)
    ax2.set_ylabel('DC Power (kW)')
    ax2.set_title(f'After Correction - MAE: {total_mae:.0f}')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    for day in range(7):
        ax2.axvspan(day*96+6*4, day*96+9*4, alpha=0.1, color='green')
    
    # 3. 辐照度
    ax3 = axes[2]
    ax3.fill_between(range(len(all_irr)), all_irr, alpha=0.3, color='#f39c12')
    ax3.plot(all_irr, label='D+1 Irradiation', color='#f39c12', linewidth=1)
    ax3.set_xlabel('Time Points')
    ax3.set_ylabel('Irradiation')
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_DIR, 'lstm_iter21_correction.png'), dpi=150)
    print(f"\n保存: lstm_iter21_correction.png")
    plt.close()


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
