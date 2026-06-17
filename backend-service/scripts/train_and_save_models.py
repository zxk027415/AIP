# @AI_GENERATED: Kiro v1.0
"""
训练 Ridge 和 LSTM 模型，保存所有预测结果到文件
后续画图脚本可以直接读取，无需重新训练
"""

import pandas as pd
import numpy as np
import os
import json
import time
from datetime import datetime

from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# 数据路径
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')


def create_sequences(data, seq_length):
    """创建序列数据"""
    x, y = [], []
    for i in range(len(data) - seq_length):
        x.append(data[i:(i + seq_length)])
        y.append(data[i + seq_length])
    return np.array(x), np.array(y)


def main():
    print("=" * 70)
    print("训练模型并保存预测结果")
    print("=" * 70)
    
    start_time = time.time()
    
    # 1. 加载数据
    print("\n[1/5] 加载数据...")
    gen_file = os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv')
    weather_file = os.path.join(DATA_DIR, 'Plant_1_Weather_Sensor_Data.csv')
    
    df = pd.read_csv(gen_file)
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    
    weather_df = pd.read_csv(weather_file)
    weather_df['DATE_TIME'] = pd.to_datetime(weather_df['DATE_TIME'], dayfirst=True)
    
    print(f"  数据量: {len(df)} 条记录")
    print(f"  时间范围: {df['DATE_TIME'].min()} ~ {df['DATE_TIME'].max()}")
    
    # 2. 准备数据
    print("\n[2/5] 准备数据...")
    
    # LSTM 数据准备
    data = df[['DC_POWER']].values
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    
    SEQ_LENGTH = 24
    X_seq, y_seq = create_sequences(scaled_data, SEQ_LENGTH)
    
    split = int(len(X_seq) * 0.8)
    X_train_seq, X_test_seq = X_seq[:split], X_seq[split:]
    y_train_seq, y_test_seq = y_seq[:split], y_seq[split:]
    
    test_start_idx = split + SEQ_LENGTH
    
    # Ridge 数据准备
    df_merged = pd.merge(df, weather_df[['DATE_TIME', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'IRRADIATION']], 
                         on='DATE_TIME', how='left')
    df_merged['IRRADIATION'] = df_merged['IRRADIATION'].fillna(0)
    df_merged['AMBIENT_TEMPERATURE'] = df_merged['AMBIENT_TEMPERATURE'].fillna(df_merged['AMBIENT_TEMPERATURE'].mean())
    df_merged['MODULE_TEMPERATURE'] = df_merged['MODULE_TEMPERATURE'].fillna(df_merged['MODULE_TEMPERATURE'].mean())
    df_merged['hour'] = df_merged['DATE_TIME'].dt.hour
    df_merged['hour_sin'] = np.sin(2 * np.pi * df_merged['hour'] / 24)
    df_merged['hour_cos'] = np.cos(2 * np.pi * df_merged['hour'] / 24)
    
    feature_cols = ['IRRADIATION', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'hour_sin', 'hour_cos']
    X_all = df_merged[feature_cols].values
    y_all = df_merged['DC_POWER'].values
    timestamps_all = df_merged['DATE_TIME'].values
    
    X_train_ridge = X_all[:test_start_idx]
    X_test_ridge = X_all[test_start_idx:]
    y_train_ridge = y_all[:test_start_idx]
    y_test_ridge = y_all[test_start_idx:]
    
    print(f"  Ridge 训练集: {len(X_train_ridge)}, 测试集: {len(X_test_ridge)}")
    print(f"  LSTM 训练集: {len(X_train_seq)}, 测试集: {len(X_test_seq)}")
    
    # 3. 训练 Ridge
    print("\n[3/5] 训练 Ridge 模型...")
    ridge_start = time.time()
    
    X_mean = X_train_ridge.mean(axis=0)
    X_std = X_train_ridge.std(axis=0) + 1e-8
    X_train_norm = (X_train_ridge - X_mean) / X_std
    X_test_norm = (X_test_ridge - X_mean) / X_std
    
    # 训练集全量归一化用于预测
    X_all_norm = (X_all - X_mean) / X_std
    
    lambda_reg = 0.01
    n_features = X_train_norm.shape[1]
    X_train_bias = np.c_[np.ones(len(X_train_norm)), X_train_norm]
    X_test_bias = np.c_[np.ones(len(X_test_norm)), X_test_norm]
    X_all_bias = np.c_[np.ones(len(X_all_norm)), X_all_norm]
    
    I = np.eye(n_features + 1)
    I[0, 0] = 0
    theta = np.linalg.inv(X_train_bias.T @ X_train_bias + lambda_reg * I) @ X_train_bias.T @ y_train_ridge
    
    # 预测全量数据
    y_pred_ridge_all = X_all_bias @ theta
    y_pred_ridge_train = y_pred_ridge_all[:test_start_idx]
    y_pred_ridge_test = y_pred_ridge_all[test_start_idx:]
    
    ridge_time = time.time() - ridge_start
    
    # Ridge 指标
    mae_ridge = mean_absolute_error(y_test_ridge, y_pred_ridge_test)
    rmse_ridge = np.sqrt(mean_squared_error(y_test_ridge, y_pred_ridge_test))
    r2_ridge = r2_score(y_test_ridge, y_pred_ridge_test)
    
    print(f"  训练时间: {ridge_time:.2f} 秒")
    print(f"  MAE: {mae_ridge:.2f} kW, RMSE: {rmse_ridge:.2f} kW, R²: {r2_ridge:.4f}")
    
    # 4. 训练 LSTM
    print("\n[4/5] 训练 LSTM 模型...")
    lstm_start = time.time()
    
    has_lstm = False
    lstm_results = {}
    
    try:
        import tensorflow as tf
        
        # 设置 TensorFlow 日志级别
        tf.get_logger().setLevel('ERROR')
        
        model = tf.keras.Sequential([
            tf.keras.layers.LSTM(64, return_sequences=True, input_shape=(SEQ_LENGTH, 1)),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.LSTM(32),
            tf.keras.layers.Dense(16, activation='relu'),
            tf.keras.layers.Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        
        early_stop = tf.keras.callbacks.EarlyStopping(
            monitor='val_loss', patience=5, restore_best_weights=True
        )
        
        print("  开始训练 (50 epochs, early stopping)...")
        history = model.fit(
            X_train_seq, y_train_seq, 
            epochs=50, batch_size=32, 
            validation_split=0.1, 
            callbacks=[early_stop],
            verbose=1
        )
        
        actual_epochs = len(history.history['loss'])
        print(f"  实际训练 epochs: {actual_epochs}")
        
        # 预测
        print("  生成预测...")
        y_pred_lstm_train_scaled = model.predict(X_train_seq, verbose=0)
        y_pred_lstm_test_scaled = model.predict(X_test_seq, verbose=0)
        
        # 反归一化
        y_train_lstm = scaler.inverse_transform(y_train_seq).flatten()
        y_test_lstm = scaler.inverse_transform(y_test_seq).flatten()
        y_pred_lstm_train = scaler.inverse_transform(y_pred_lstm_train_scaled).flatten()
        y_pred_lstm_test = scaler.inverse_transform(y_pred_lstm_test_scaled).flatten()
        
        lstm_time = time.time() - lstm_start
        
        # LSTM 指标
        mae_lstm = mean_absolute_error(y_test_lstm, y_pred_lstm_test)
        rmse_lstm = np.sqrt(mean_squared_error(y_test_lstm, y_pred_lstm_test))
        r2_lstm = r2_score(y_test_lstm, y_pred_lstm_test)
        
        print(f"  训练时间: {lstm_time:.2f} 秒")
        print(f"  MAE: {mae_lstm:.2f} kW, RMSE: {rmse_lstm:.2f} kW, R²: {r2_lstm:.4f}")
        
        lstm_results = {
            'mae': mae_lstm,
            'rmse': rmse_lstm,
            'r2': r2_lstm,
            'train_time': lstm_time,
            'actual_epochs': actual_epochs
        }
        
        has_lstm = True
        
    except ImportError as e:
        print(f"  TensorFlow 未安装，跳过 LSTM: {e}")
        lstm_time = 0
    
    # 5. 保存结果
    print("\n[5/5] 保存结果...")
    
    # 保存 Ridge 预测结果
    ridge_df = pd.DataFrame({
        'timestamp': pd.to_datetime(timestamps_all),
        'actual': y_all,
        'predicted': y_pred_ridge_all,
        'is_train': [i < test_start_idx for i in range(len(y_all))]
    })
    ridge_file = os.path.join(OUTPUT_DIR, 'ridge_predictions.csv')
    ridge_df.to_csv(ridge_file, index=False)
    print(f"  Ridge 预测结果: {ridge_file}")
    
    # 保存 LSTM 预测结果
    if has_lstm:
        # LSTM 时间戳（比 Ridge 少 SEQ_LENGTH 个点）
        lstm_train_timestamps = timestamps_all[SEQ_LENGTH:SEQ_LENGTH+len(y_train_lstm)]
        lstm_test_timestamps = timestamps_all[test_start_idx:test_start_idx+len(y_test_lstm)]
        
        lstm_train_df = pd.DataFrame({
            'timestamp': pd.to_datetime(lstm_train_timestamps),
            'actual': y_train_lstm,
            'predicted': y_pred_lstm_train,
            'is_train': True
        })
        
        lstm_test_df = pd.DataFrame({
            'timestamp': pd.to_datetime(lstm_test_timestamps),
            'actual': y_test_lstm,
            'predicted': y_pred_lstm_test,
            'is_train': False
        })
        
        lstm_df = pd.concat([lstm_train_df, lstm_test_df], ignore_index=True)
        lstm_file = os.path.join(OUTPUT_DIR, 'lstm_predictions.csv')
        lstm_df.to_csv(lstm_file, index=False)
        print(f"  LSTM 预测结果: {lstm_file}")
    
    # 保存元数据
    total_time = time.time() - start_time
    metadata = {
        'timestamp': datetime.now().isoformat(),
        'total_time_seconds': total_time,
        'data_info': {
            'total_records': len(df),
            'train_records': test_start_idx,
            'test_records': len(df) - test_start_idx,
            'seq_length': SEQ_LENGTH
        },
        'ridge': {
            'mae': mae_ridge,
            'rmse': rmse_ridge,
            'r2': r2_ridge,
            'train_time': ridge_time,
            'features': feature_cols
        }
    }
    
    if has_lstm:
        metadata['lstm'] = lstm_results
    
    metadata_file = os.path.join(OUTPUT_DIR, 'model_metadata.json')
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"  元数据: {metadata_file}")
    
    # 总结
    print("\n" + "=" * 70)
    print("训练完成！")
    print("=" * 70)
    print(f"\n总耗时: {total_time:.2f} 秒")
    print(f"\n模型性能对比:")
    print(f"  {'模型':<10} {'MAE (kW)':<12} {'RMSE (kW)':<12} {'R²':<10} {'训练时间':<10}")
    print(f"  {'-'*54}")
    print(f"  {'Ridge':<10} {mae_ridge:<12.2f} {rmse_ridge:<12.2f} {r2_ridge:<10.4f} {ridge_time:<10.2f}s")
    if has_lstm:
        print(f"  {'LSTM':<10} {mae_lstm:<12.2f} {rmse_lstm:<12.2f} {r2_lstm:<10.4f} {lstm_time:<10.2f}s")
    
    print(f"\n保存的文件:")
    print(f"  - {ridge_file}")
    if has_lstm:
        print(f"  - {lstm_file}")
    print(f"  - {metadata_file}")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
