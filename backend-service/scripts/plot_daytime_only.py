# @AI_GENERATED: Kiro v1.0
"""
只绘制白天数据（过滤掉零值）- 复现ipynb风格
"""

import pandas as pd
import numpy as np
import os

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid")
plt.rc('figure', figsize=(15, 6))

from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')
SEQ_LENGTH = 24


def create_sequences(data, seq_length):
    x, y = [], []
    for i in range(len(data) - seq_length):
        x.append(data[i:(i + seq_length)])
        y.append(data[i + seq_length])
    return np.array(x), np.array(y)


def main():
    print("只绘制白天数据（过滤零值）...")
    
    # 加载数据
    df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    df = df.sort_values('DATE_TIME')
    
    # 第一个逆变器
    first_inv = df['SOURCE_KEY'].unique()[0]
    df_single = df[df['SOURCE_KEY'] == first_inv].copy()
    df_single = df_single.sort_values('DATE_TIME').reset_index(drop=True)
    
    print(f"原始数据: {len(df_single)} 条")
    
    # 方法1: 过滤掉DC_POWER为0的数据（只保留白天）
    df_daytime = df_single[df_single['DC_POWER'] > 0].copy()
    df_daytime = df_daytime.reset_index(drop=True)
    print(f"白天数据: {len(df_daytime)} 条")
    
    # 特征缩放
    data = df_daytime[['DC_POWER']].values
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    
    # 创建序列
    X, y = create_sequences(scaled_data, SEQ_LENGTH)
    print(f"序列数: {len(X)}")
    
    # 80/20划分
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    print(f"训练集: {len(X_train)}, 测试集: {len(X_test)}")
    
    # Ridge回归
    X_train_flat = X_train.reshape(X_train.shape[0], -1)
    X_test_flat = X_test.reshape(X_test.shape[0], -1)
    
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train_flat, y_train.ravel())
    ridge_pred = ridge.predict(X_test_flat)
    
    # LSTM
    try:
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout
        from tensorflow.keras.callbacks import EarlyStopping
        
        model = Sequential([
            LSTM(64, return_sequences=True, input_shape=(SEQ_LENGTH, 1)),
            Dropout(0.2),
            LSTM(32),
            Dense(16, activation='relu'),
            Dense(1)
        ])
        
        model.compile(optimizer='adam', loss='mean_squared_error')
        early_stop = EarlyStopping(monitor='val_loss', patience=5, restore_best_weights=True)
        
        model.fit(X_train, y_train, batch_size=32, epochs=50, 
                  validation_split=0.1, callbacks=[early_stop], verbose=1)
        
        lstm_pred = model.predict(X_test)
        has_lstm = True
    except Exception as e:
        print(f"LSTM失败: {e}")
        has_lstm = False
    
    # 反归一化
    actual_values = scaler.inverse_transform(y_test)
    ridge_values = scaler.inverse_transform(ridge_pred.reshape(-1, 1))
    if has_lstm:
        lstm_values = scaler.inverse_transform(lstm_pred)
    
    # 绘图 - ipynb风格
    plt.figure(figsize=(15, 6))
    
    plt.plot(actual_values[:200], label='Actual Power Generation', color='#2c3e50', alpha=0.7)
    
    if has_lstm:
        plt.plot(lstm_values[:200], label='LSTM Forecast', color='#f39c12', linestyle='--', linewidth=2)
        plt.fill_between(range(200), actual_values[:200].flatten(), lstm_values[:200].flatten(), 
                         color='#f1c40f', alpha=0.1)
    
    plt.plot(ridge_values[:200], label='Ridge Forecast', color='#e74c3c', linestyle=':', linewidth=2)
    
    plt.title("Solar Energy Forecast: 50-Hour Performance (Daytime Only)", fontsize=18)
    plt.xlabel("Time Steps (15-min intervals, daytime only)", fontsize=14)
    plt.ylabel("DC Power (kW)", fontsize=14)
    plt.legend(loc='upper right', fontsize=12)
    plt.grid(True, alpha=0.3)
    
    output_file = os.path.join(DATA_DIR, 'daytime_only_comparison.png')
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n保存: {output_file}")
    plt.close()
    
    # 指标
    ridge_mae = mean_absolute_error(actual_values, ridge_values)
    ridge_rmse = np.sqrt(mean_squared_error(actual_values, ridge_values))
    print(f"\nRidge: MAE={ridge_mae:.2f}kW, RMSE={ridge_rmse:.2f}kW")
    
    if has_lstm:
        lstm_mae = mean_absolute_error(actual_values, lstm_values)
        lstm_rmse = np.sqrt(mean_squared_error(actual_values, lstm_values))
        print(f"LSTM:  MAE={lstm_mae:.2f}kW, RMSE={lstm_rmse:.2f}kW")
    
    print(f"\n数据范围: {actual_values[:200].min():.0f} - {actual_values[:200].max():.0f} kW")
    print("完成!")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
