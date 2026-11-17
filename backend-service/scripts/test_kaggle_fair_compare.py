# @AI_GENERATED: Kiro v1.0
"""
公平对比测试：在完全相同的测试集上比较 LSTM 和 Ridge 方法
使用与 Kaggle notebook 完全相同的数据处理方式
"""

import pandas as pd
import numpy as np
import os

from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# 数据路径
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')


def create_sequences(data, seq_length):
    """创建序列数据"""
    x, y = [], []
    for i in range(len(data) - seq_length):
        x.append(data[i:(i + seq_length)])
        y.append(data[i + seq_length])
    return np.array(x), np.array(y)


def main():
    print("=" * 70)
    print("公平对比：在相同测试集上比较 LSTM vs Ridge")
    print("=" * 70)
    
    # 1. 加载数据 - 与 Kaggle notebook 完全相同（不聚合，使用原始逆变器数据）
    gen_file = os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv')
    weather_file = os.path.join(DATA_DIR, 'Plant_1_Weather_Sensor_Data.csv')
    
    df = pd.read_csv(gen_file)
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    
    print(f"\n原始数据量: {len(df)} 条记录")
    print(f"逆变器数量: {df['SOURCE_KEY'].nunique()}")
    
    # 2. Kaggle 方法的数据处理
    # 使用 DC_POWER 单一特征
    data = df[['DC_POWER']].values
    
    # 全量数据归一化（Kaggle 方法 - 存在泄露）
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    
    # 创建序列
    SEQ_LENGTH = 24
    X_seq, y_seq = create_sequences(scaled_data, SEQ_LENGTH)
    print(f"序列数据: X shape = {X_seq.shape}, y shape = {y_seq.shape}")
    
    # 80/20 时序划分
    split = int(len(X_seq) * 0.8)
    X_train_seq, X_test_seq = X_seq[:split], X_seq[split:]
    y_train_seq, y_test_seq = y_seq[:split], y_seq[split:]
    
    print(f"训练集: {len(X_train_seq)}, 测试集: {len(X_test_seq)}")
    
    # 获取测试集对应的原始索引（用于 Ridge 方法）
    test_start_idx = split + SEQ_LENGTH
    test_indices = list(range(test_start_idx, len(df)))
    
    print(f"\n测试集时间范围:")
    print(f"  开始: {df.iloc[test_start_idx]['DATE_TIME']}")
    print(f"  结束: {df.iloc[-1]['DATE_TIME']}")
    
    # ========================================
    # 方法1: Ridge 回归（在相同测试集上）
    # ========================================
    print("\n" + "-" * 70)
    print("方法1: Ridge 回归 + 气象特征")
    print("-" * 70)
    
    # 加载气象数据
    weather_df = pd.read_csv(weather_file)
    weather_df['DATE_TIME'] = pd.to_datetime(weather_df['DATE_TIME'], dayfirst=True)
    
    # 合并气象数据到发电数据
    df_merged = pd.merge(df, weather_df[['DATE_TIME', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'IRRADIATION']], 
                         on='DATE_TIME', how='left')
    
    # 填充缺失值
    df_merged['IRRADIATION'] = df_merged['IRRADIATION'].fillna(0)
    df_merged['AMBIENT_TEMPERATURE'] = df_merged['AMBIENT_TEMPERATURE'].fillna(df_merged['AMBIENT_TEMPERATURE'].mean())
    df_merged['MODULE_TEMPERATURE'] = df_merged['MODULE_TEMPERATURE'].fillna(df_merged['MODULE_TEMPERATURE'].mean())
    
    # 添加时间特征
    df_merged['hour'] = df_merged['DATE_TIME'].dt.hour
    df_merged['hour_sin'] = np.sin(2 * np.pi * df_merged['hour'] / 24)
    df_merged['hour_cos'] = np.cos(2 * np.pi * df_merged['hour'] / 24)
    
    # 特征
    feature_cols = ['IRRADIATION', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'hour_sin', 'hour_cos']
    X_all = df_merged[feature_cols].values
    y_all = df_merged['DC_POWER'].values
    
    # 使用相同的划分点
    X_train_ridge = X_all[:test_start_idx]
    X_test_ridge = X_all[test_start_idx:]
    y_train_ridge = y_all[:test_start_idx]
    y_test_ridge = y_all[test_start_idx:]
    
    print(f"Ridge 训练集: {len(X_train_ridge)}, 测试集: {len(X_test_ridge)}")
    
    # 仅训练集归一化（无泄露）
    X_mean = X_train_ridge.mean(axis=0)
    X_std = X_train_ridge.std(axis=0) + 1e-8
    X_train_norm = (X_train_ridge - X_mean) / X_std
    X_test_norm = (X_test_ridge - X_mean) / X_std
    
    # Ridge 回归
    lambda_reg = 0.01
    n_features = X_train_norm.shape[1]
    X_train_bias = np.c_[np.ones(len(X_train_norm)), X_train_norm]
    X_test_bias = np.c_[np.ones(len(X_test_norm)), X_test_norm]
    
    I = np.eye(n_features + 1)
    I[0, 0] = 0
    
    theta = np.linalg.inv(X_train_bias.T @ X_train_bias + lambda_reg * I) @ X_train_bias.T @ y_train_ridge
    y_pred_ridge = X_test_bias @ theta
    
    # 评估 Ridge
    mae_ridge = mean_absolute_error(y_test_ridge, y_pred_ridge)
    rmse_ridge = np.sqrt(mean_squared_error(y_test_ridge, y_pred_ridge))
    r2_ridge = r2_score(y_test_ridge, y_pred_ridge)
    
    print(f"\nRidge 回归结果:")
    print(f"  MAE:  {mae_ridge:.2f} kW")
    print(f"  RMSE: {rmse_ridge:.2f} kW")
    print(f"  R²:   {r2_ridge:.4f}")
    
    # ========================================
    # 方法2: LSTM（Kaggle 方法）
    # ========================================
    print("\n" + "-" * 70)
    print("方法2: LSTM (Kaggle 铜牌方法)")
    print("-" * 70)
    
    try:
        import tensorflow as tf
        
        # 构建模型
        model = tf.keras.Sequential([
            tf.keras.layers.LSTM(64, return_sequences=True, input_shape=(SEQ_LENGTH, 1)),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.LSTM(32),
            tf.keras.layers.Dense(16, activation='relu'),
            tf.keras.layers.Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        
        # 训练 - 增加 epochs 并添加 early stopping
        print("训练 LSTM 模型 (50 epochs, early stopping)...")
        early_stop = tf.keras.callbacks.EarlyStopping(
            monitor='val_loss', patience=5, restore_best_weights=True
        )
        history = model.fit(
            X_train_seq, y_train_seq, 
            epochs=50, 
            batch_size=32, 
            validation_split=0.1, 
            callbacks=[early_stop],
            verbose=1
        )
        print(f"实际训练 epochs: {len(history.history['loss'])}")
        
        # 预测
        y_pred_lstm_scaled = model.predict(X_test_seq, verbose=0)
        
        # 反归一化
        y_test_lstm = scaler.inverse_transform(y_test_seq)
        y_pred_lstm = scaler.inverse_transform(y_pred_lstm_scaled)
        
        # 评估 LSTM
        mae_lstm = mean_absolute_error(y_test_lstm, y_pred_lstm)
        rmse_lstm = np.sqrt(mean_squared_error(y_test_lstm, y_pred_lstm))
        r2_lstm = r2_score(y_test_lstm, y_pred_lstm)
        
        print(f"\nLSTM 结果:")
        print(f"  MAE:  {mae_lstm:.2f} kW")
        print(f"  RMSE: {rmse_lstm:.2f} kW")
        print(f"  R²:   {r2_lstm:.4f}")
        
        has_lstm = True
    except ImportError:
        print("TensorFlow 未安装，跳过 LSTM")
        has_lstm = False
    
    # ========================================
    # 对比总结
    # ========================================
    print("\n" + "=" * 70)
    print("对比总结（相同测试集）")
    print("=" * 70)
    print(f"\nKaggle notebook 报告的 LSTM 结果:")
    print(f"  MAE:  247.07 kW")
    print(f"  RMSE: 613.71 kW")
    
    print(f"\n我们复现的结果:")
    if has_lstm:
        print(f"  LSTM:  MAE = {mae_lstm:.2f} kW, RMSE = {rmse_lstm:.2f} kW, R² = {r2_lstm:.4f}")
    print(f"  Ridge: MAE = {mae_ridge:.2f} kW, RMSE = {rmse_ridge:.2f} kW, R² = {r2_ridge:.4f}")
    
    if has_lstm:
        print(f"\n改进幅度:")
        print(f"  MAE 降低:  {(mae_lstm - mae_ridge) / mae_lstm * 100:.1f}%")
        print(f"  RMSE 降低: {(rmse_lstm - rmse_ridge) / rmse_lstm * 100:.1f}%")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
