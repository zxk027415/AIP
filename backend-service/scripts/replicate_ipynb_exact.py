# @AI_GENERATED: Kiro v1.0
"""
精确复现ipynb的数据处理流程
关键：使用所有逆变器的混合数据，不按逆变器过滤
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
    print("精确复现ipynb数据流...")
    print()
    
    # 1. Load and Clean - 与ipynb完全一致
    df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    
    print(f"原始数据形状: {df.shape}")
    print(f"逆变器数量: {df['SOURCE_KEY'].nunique()}")
    print(f"时间范围: {df['DATE_TIME'].min()} 到 {df['DATE_TIME'].max()}")
    
    # 2. Feature Scaling - 直接取DC_POWER，不按逆变器过滤！
    data = df[['DC_POWER']].values
    print(f"\nDC_POWER数据形状: {data.shape}")
    print(f"DC_POWER范围: {data.min():.2f} 到 {data.max():.2f}")
    
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    
    # 3. Sequence Engineering
    X, y = create_sequences(scaled_data, SEQ_LENGTH)
    print(f"\n序列形状: X={X.shape}, y={y.shape}")
    
    # 4. Train/Test Split
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    print(f"训练集: {X_train.shape}, 测试集: {X_test.shape}")
    
    # 5. 训练LSTM
    print("\n训练LSTM...")
    try:
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout
        
        model = Sequential([
            LSTM(64, return_sequences=True, input_shape=(SEQ_LENGTH, 1)),
            Dropout(0.2),
            LSTM(32),
            Dense(16, activation='relu'),
            Dense(1)
        ])
        
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        
        # 与ipynb一致：10个epoch (verbose=0 减少输出)
        history = model.fit(X_train, y_train, epochs=10, batch_size=32, 
                           validation_split=0.1, verbose=0)
        
        # 6. Generate Predictions
        predictions_scaled = model.predict(X_test, verbose=0)
        
        # 7. Inverse Scaling
        actual_values = scaler.inverse_transform(y_test.reshape(-1, 1))
        predicted_values = scaler.inverse_transform(predictions_scaled)
        
        # 8. Calculate Metrics
        mae = mean_absolute_error(actual_values, predicted_values)
        rmse = np.sqrt(mean_squared_error(actual_values, predicted_values))
        
        print(f"\nEvaluation Complete.")
        print(f"MAE: {mae:.2f} kW")
        print(f"RMSE: {rmse:.2f} kW")
        
        # 9. 检查测试集前200点的数据特征
        print(f"\n测试集前200点统计:")
        print(f"  最小值: {actual_values[:200].min():.2f}")
        print(f"  最大值: {actual_values[:200].max():.2f}")
        print(f"  平均值: {actual_values[:200].mean():.2f}")
        print(f"  零值数量: {(actual_values[:200] == 0).sum()}")
        
        # 10. 绘图 - 与ipynb完全一致
        plt.figure(figsize=(15, 6))
        plt.plot(actual_values[:200], label='Actual Power Generation', color='#2c3e50', alpha=0.7)
        plt.plot(predicted_values[:200], label='LSTM Forecast', color='#f39c12', linestyle='--', linewidth=2)
        plt.fill_between(range(200), actual_values[:200].flatten(), predicted_values[:200].flatten(), 
                        color='#f1c40f', alpha=0.1)
        
        plt.title("Solar Energy Forecast: 50-Hour Performance (Exact ipynb Replication)", fontsize=18)
        plt.xlabel("Time Steps (15-min Intervals)")
        plt.ylabel("Power Output (kW)")
        plt.legend(loc='upper right')
        
        output_file = os.path.join(DATA_DIR, 'ipynb_exact_replication.png')
        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"\n保存: {output_file}")
        plt.close()
        
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n完成!")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
