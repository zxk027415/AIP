# @AI_GENERATED: Kiro v1.0
"""
迭代19：简化气象特征 - 只用D+1辐照度
- D日功率
- D+1辐照度预报（最关键的驱动因子）
- 时间特征
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


def create_simple_weather_samples(power_df, weather_df):
    """简化特征：D日功率 + D+1辐照度预报 + 时间"""
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
                
                # 简化特征：功率 + D+1辐照度 + 时间
                X = np.column_stack([
                    power_d0,     # D日功率
                    irr_d1,       # D+1辐照度预报
                    hour_sin,
                    hour_cos
                ])
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


def main():
    print("=" * 60)
    print("迭代19：简化气象 - D日功率 + D+1辐照度")
    print("=" * 60)
    
    power_df, weather_df = load_data()
    X, y, meta = create_simple_weather_samples(power_df, weather_df)
    print(f"样本: {len(X)}, 特征: {X.shape[2]} (功率+辐照度+时间)")
    
    dates = power_df['date'].unique()
    test_dates = set(dates[-7:])
    train_idx = [i for i, m in enumerate(meta) if m['date'] not in test_dates]
    test_idx = [i for i, m in enumerate(meta) if m['date'] in test_dates]
    
    X_train, y_train = X[train_idx], y[train_idx]
    X_test, y_test = X[test_idx], y[test_idx]
    test_meta = [meta[i] for i in test_idx]
    
    X_train_aug, y_train_aug = augment_data(X_train, y_train, n_augment=2)
    print(f"增强后训练: {len(X_train_aug)}, 测试: {len(X_test)}")
    
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
    y_pred = scaler_power.inverse_transform(y_pred_s.reshape(-1,1)).reshape(-1, POINTS_PER_DAY)
    y_pred = np.maximum(y_pred, 0)
    
    from collections import defaultdict
    daily_actual, daily_pred, daily_irr = defaultdict(list), defaultdict(list), defaultdict(list)
    for i, m in enumerate(test_meta):
        daily_actual[m['date']].append(y_test[i])
        daily_pred[m['date']].append(y_pred[i])
        daily_irr[m['date']].append(X_test[i, :, 1])  # D+1辐照度
    
    all_actual, all_pred, all_irr = [], [], []
    print("\n场站级别:")
    for d in sorted(daily_actual.keys()):
        pa = np.sum(daily_actual[d], axis=0)
        pp = np.sum(daily_pred[d], axis=0)
        pi = np.mean(daily_irr[d], axis=0)  # 辐照度取平均（所有逆变器共用）
        mae = mean_absolute_error(pa, pp)
        print(f"  {d}: MAE={mae:.0f}")
        all_actual.extend(pa)
        all_pred.extend(pp)
        all_irr.extend(pi)
    
    total_mae = mean_absolute_error(all_actual, all_pred)
    total_rmse = np.sqrt(mean_squared_error(all_actual, all_pred))
    print(f"\n总体: MAE={total_mae:.0f}, RMSE={total_rmse:.0f}")
    print(f"对比V10(无气象): MAE=14,953")
    
    # 双子图：上面功率，下面辐照度
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 8), height_ratios=[2, 1], sharex=True)
    
    # 上图：功率预测
    ax1.plot(all_actual, label='Actual Power', color='#2c3e50', linewidth=1)
    ax1.plot(all_pred, label='Predicted Power', color='#e74c3c', linestyle='--', linewidth=1)
    ax1.set_ylabel('DC Power (kW)')
    ax1.set_title(f'Iter19: D-Power + D+1-Irradiation Forecast\nMAE: {total_mae:.0f}, RMSE: {total_rmse:.0f}')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    # 下图：辐照度预报
    ax2.fill_between(range(len(all_irr)), all_irr, alpha=0.3, color='#f39c12')
    ax2.plot(all_irr, label='D+1 Irradiation Forecast', color='#f39c12', linewidth=1)
    ax2.set_xlabel('Time Points (15-min intervals)')
    ax2.set_ylabel('Irradiation (kW/m²)')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_DIR, 'lstm_iter19_simple_weather.png'), dpi=150)
    print(f"保存: lstm_iter19_simple_weather.png")
    plt.close()


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
