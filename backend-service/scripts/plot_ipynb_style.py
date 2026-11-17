# @AI_GENERATED: Kiro v1.0
"""
复现ipynb中的绘图风格 - 测试集前200点
"""

import pandas as pd
import numpy as np
import os
import json

# 设置非交互式后端
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import seaborn as sns

# 设置与ipynb一致的风格
sns.set_theme(style="whitegrid")
plt.rc('figure', figsize=(15, 6))

from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

# 数据路径
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')

SEQ_LENGTH = 24


def create_sequences(data, seq_length):
    """创建时序序列"""
    x, y = [], []
    for i in range(len(data) - seq_length):
        x.append(data[i:(i + seq_length)])
        y.append(data[i + seq_length])
    return np.array(x), np.array(y)


def main():
    print("复现ipynb绘图风格...")
    
    # 1. 加载Plant 1数据
    df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    df = df.sort_values('DATE_TIME')
    
    # 2. 只取第一个逆变器
    first_inverter = df['SOURCE_KEY'].unique()[0]
    df_single = df[df['SOURCE_KEY'] == first_inverter].copy()
    df_single = df_single.sort_values('DATE_TIME').reset_index(drop=True)
    
    print(f"逆变器: {first_inverter}")
    print(f"数据量: {len(df_single)}")
    
    # 3. 特征缩放
    data = df_single[['DC_POWER']].values
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    
    # 4. 创建序列
    X, y = create_sequences(scaled_data, SEQ_LENGTH)
    
    # 5. 训练/测试划分（80/20）
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    # 获取时间戳
    timestamps = df_single['DATE_TIME'].values[SEQ_LENGTH:]
    test_timestamps = timestamps[split:]
    
    print(f"测试集时间范围: {pd.Timestamp(test_timestamps[0])} 到 {pd.Timestamp(test_timestamps[-1])}")
    print(f"测试集样本数: {len(y_test)}")
    
    # 6. Ridge回归
    X_train_flat = X_train.reshape(X_train.shape[0], -1)
    X_test_flat = X_test.reshape(X_test.shape[0], -1)
    
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train_flat, y_train.ravel())
    ridge_pred = ridge.predict(X_test_flat)
    
    # 7. LSTM
    try:
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout
        from tensorflow.keras.callbacks import EarlyStopping
        
        model = Sequential([
            LSTM(50, return_sequences=True, input_shape=(SEQ_LENGTH, 1)),
            Dropout(0.2),
            LSTM(50, return_sequences=False),
            Dropout(0.2),
            Dense(25),
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
    
    # 8. 反归一化
    actual_values = scaler.inverse_transform(y_test)
    ridge_values = scaler.inverse_transform(ridge_pred.reshape(-1, 1))
    if has_lstm:
        lstm_values = scaler.inverse_transform(lstm_pred)
    
    # 9. 绘图 - 完全复现ipynb风格
    plt.figure(figsize=(15, 6))
    
    # ipynb风格：前200点
    plt.plot(actual_values[:200], label='Actual Power Generation', color='#2c3e50', alpha=0.7)
    
    if has_lstm:
        plt.plot(lstm_values[:200], label='LSTM Forecast', color='#f39c12', linestyle='--', linewidth=2)
        plt.fill_between(range(200), actual_values[:200].flatten(), lstm_values[:200].flatten(), 
                         color='#f1c40f', alpha=0.1)
    
    # 添加Ridge对比
    plt.plot(ridge_values[:200], label='Ridge Forecast', color='#e74c3c', linestyle=':', linewidth=2)
    
    # 获取测试集起始时间
    test_start = pd.Timestamp(test_timestamps[0])
    test_end_200 = pd.Timestamp(test_timestamps[199])
    
    plt.title(f"☀️ Solar Energy Forecast: 50-Hour Performance\n"
              f"Test Period: {test_start.strftime('%Y-%m-%d %H:%M')} to {test_end_200.strftime('%Y-%m-%d %H:%M')}", 
              fontsize=18)
    plt.xlabel("Time Steps (15-min intervals)", fontsize=14)
    plt.ylabel("DC Power (kW)", fontsize=14)
    plt.legend(loc='upper right', fontsize=12)
    plt.grid(True, alpha=0.3)
    
    output_file = os.path.join(DATA_DIR, 'ipynb_style_comparison.png')
    plt.tight_layout()
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n保存: {output_file}")
    plt.close()
    
    # 计算指标
    ridge_mae = mean_absolute_error(actual_values, ridge_values)
    ridge_rmse = np.sqrt(mean_squared_error(actual_values, ridge_values))
    
    print(f"\nRidge: MAE={ridge_mae:.2f}kW, RMSE={ridge_rmse:.2f}kW")
    
    if has_lstm:
        lstm_mae = mean_absolute_error(actual_values, lstm_values)
        lstm_rmse = np.sqrt(mean_squared_error(actual_values, lstm_values))
        print(f"LSTM:  MAE={lstm_mae:.2f}kW, RMSE={lstm_rmse:.2f}kW")
    
    print("\n完成!")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
