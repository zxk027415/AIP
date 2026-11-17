# @AI_GENERATED: Kiro v1.0
"""
Kaggle 铜牌代码复现测试
从 solar-power-forecasting.ipynb 提取的 LSTM 模型代码
"""

import pandas as pd
import numpy as np
import os
import sys

# 导入 sklearn
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# 检查是否有 TensorFlow
try:
    import tensorflow as tf
    HAS_TF = True
except ImportError:
    HAS_TF = False
    print("TensorFlow 未安装，将跳过 LSTM 测试")

# 数据路径
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')


def create_sequences(data, seq_length):
    """创建序列数据 - 来自 Kaggle notebook"""
    x, y = [], []
    for i in range(len(data) - seq_length):
        x.append(data[i:(i + seq_length)])
        y.append(data[i + seq_length])
    return np.array(x), np.array(y)


def run_kaggle_lstm_method():
    """
    复现 Kaggle 铜牌 notebook 的 LSTM 方法
    """
    print("=" * 60)
    print("Kaggle 铜牌代码复现: LSTM 太阳能发电预测")
    print("=" * 60)
    
    # 1. 加载数据 - 与 Kaggle notebook 相同
    gen_file = os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv')
    print(f"\n1. 加载数据: {gen_file}")
    
    df = pd.read_csv(gen_file)
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    
    # 聚合到电站级别（Kaggle notebook 直接用了逆变器级别数据）
    # 为了公平比较，我们也聚合一下
    df_plant = df.groupby('DATE_TIME').agg({
        'DC_POWER': 'sum',
        'AC_POWER': 'sum'
    }).reset_index()
    df_plant = df_plant.sort_values('DATE_TIME').reset_index(drop=True)
    
    print(f"   数据量: {len(df_plant)} 条记录")
    print(f"   时间范围: {df_plant['DATE_TIME'].min()} ~ {df_plant['DATE_TIME'].max()}")
    
    # 2. 特征缩放 - Kaggle 方法（全量数据归一化 - 存在泄露）
    print("\n2. 特征缩放 (Kaggle 方法 - 全量数据归一化)")
    data = df_plant[['DC_POWER']].values
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    
    # 3. 创建序列
    SEQ_LENGTH = 24  # 6小时的历史数据
    print(f"\n3. 创建序列 (序列长度: {SEQ_LENGTH})")
    X, y = create_sequences(scaled_data, SEQ_LENGTH)
    print(f"   X shape: {X.shape}, y shape: {y.shape}")
    
    # 4. 训练/测试划分 - Kaggle 方法（时序划分 80/20）
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    print(f"\n4. 数据划分 (80/20 时序划分)")
    print(f"   训练集: {len(X_train)}, 测试集: {len(X_test)}")
    
    if HAS_TF:
        # 5. 构建 LSTM 模型 - 与 Kaggle notebook 完全相同
        print("\n5. 构建 LSTM 模型")
        model = tf.keras.Sequential([
            tf.keras.layers.LSTM(64, return_sequences=True, input_shape=(SEQ_LENGTH, 1)),
            tf.keras.layers.Dropout(0.2),
            tf.keras.layers.LSTM(32),
            tf.keras.layers.Dense(16, activation='relu'),
            tf.keras.layers.Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        model.summary()
        
        # 6. 训练模型
        print("\n6. 训练模型 (10 epochs)")
        history = model.fit(
            X_train, y_train, 
            epochs=10, 
            batch_size=32, 
            validation_split=0.1, 
            verbose=1
        )
        
        # 7. 预测和评估
        print("\n7. 预测和评估")
        y_pred_scaled = model.predict(X_test)
        
        # 反归一化
        y_test_original = scaler.inverse_transform(y_test)
        y_pred_original = scaler.inverse_transform(y_pred_scaled)
        
        # 计算指标
        mae = mean_absolute_error(y_test_original, y_pred_original)
        rmse = np.sqrt(mean_squared_error(y_test_original, y_pred_original))
        r2 = r2_score(y_test_original, y_pred_original)
        
        # 计算 MAPE（排除零值）
        mask = y_test_original.flatten() > 0
        if mask.sum() > 0:
            mape = np.mean(np.abs((y_test_original[mask] - y_pred_original[mask]) / y_test_original[mask])) * 100
        else:
            mape = float('inf')
        
        print("\n" + "=" * 60)
        print("Kaggle LSTM 方法结果:")
        print("=" * 60)
        print(f"MAE:  {mae:.2f} kW")
        print(f"RMSE: {rmse:.2f} kW")
        print(f"R²:   {r2:.4f}")
        print(f"MAPE: {mape:.2f}%")
        
        return {
            'method': 'Kaggle LSTM',
            'mae': mae,
            'rmse': rmse,
            'r2': r2,
            'mape': mape
        }
    else:
        print("\n跳过 LSTM 训练（TensorFlow 未安装）")
        return None


def run_our_ridge_method():
    """
    我们的 Ridge 回归方法（无泄露版本）
    """
    print("\n" + "=" * 60)
    print("我们的方法: Ridge 回归 + 气象特征 (无泄露)")
    print("=" * 60)
    
    # 加载数据
    gen_file = os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv')
    weather_file = os.path.join(DATA_DIR, 'Plant_1_Weather_Sensor_Data.csv')
    
    gen_df = pd.read_csv(gen_file)
    weather_df = pd.read_csv(weather_file)
    
    # 解析日期
    gen_df['DATE_TIME'] = pd.to_datetime(gen_df['DATE_TIME'], dayfirst=True)
    weather_df['DATE_TIME'] = pd.to_datetime(weather_df['DATE_TIME'], dayfirst=True)
    
    # 聚合发电数据
    gen_agg = gen_df.groupby('DATE_TIME').agg({
        'DC_POWER': 'sum',
        'AC_POWER': 'sum'
    }).reset_index()
    
    # 合并
    merged = pd.merge(gen_agg, weather_df[['DATE_TIME', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'IRRADIATION']], 
                      on='DATE_TIME', how='inner')
    merged = merged.sort_values('DATE_TIME').reset_index(drop=True)
    
    print(f"合并后数据量: {len(merged)}")
    
    # 添加时间特征
    merged['hour'] = merged['DATE_TIME'].dt.hour
    merged['hour_sin'] = np.sin(2 * np.pi * merged['hour'] / 24)
    merged['hour_cos'] = np.cos(2 * np.pi * merged['hour'] / 24)
    
    # 特征和目标
    feature_cols = ['IRRADIATION', 'AMBIENT_TEMPERATURE', 'MODULE_TEMPERATURE', 'hour_sin', 'hour_cos']
    X = merged[feature_cols].values
    y = merged['DC_POWER'].values
    
    # 时序划分（最后7天作为测试集）
    test_days = 7
    samples_per_day = 96  # 15分钟间隔
    test_size = test_days * samples_per_day
    
    X_train, X_test = X[:-test_size], X[-test_size:]
    y_train, y_test = y[:-test_size], y[-test_size:]
    
    print(f"训练集: {len(X_train)}, 测试集: {len(X_test)}")
    
    # 仅训练集归一化
    X_mean = X_train.mean(axis=0)
    X_std = X_train.std(axis=0) + 1e-8
    X_train_norm = (X_train - X_mean) / X_std
    X_test_norm = (X_test - X_mean) / X_std
    
    # Ridge 回归（Normal Equation）
    lambda_reg = 0.01
    n_features = X_train_norm.shape[1]
    X_train_bias = np.c_[np.ones(len(X_train_norm)), X_train_norm]
    X_test_bias = np.c_[np.ones(len(X_test_norm)), X_test_norm]
    
    I = np.eye(n_features + 1)
    I[0, 0] = 0  # 不正则化偏置项
    
    theta = np.linalg.inv(X_train_bias.T @ X_train_bias + lambda_reg * I) @ X_train_bias.T @ y_train
    
    # 预测
    y_pred = X_test_bias @ theta
    
    # 评估
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)
    
    mask = y_test > 0
    if mask.sum() > 0:
        mape = np.mean(np.abs((y_test[mask] - y_pred[mask]) / y_test[mask])) * 100
    else:
        mape = float('inf')
    
    print("\n" + "=" * 60)
    print("Ridge 回归方法结果:")
    print("=" * 60)
    print(f"MAE:  {mae:.2f} kW")
    print(f"RMSE: {rmse:.2f} kW")
    print(f"R²:   {r2:.4f}")
    print(f"MAPE: {mape:.2f}%")
    
    return {
        'method': 'Ridge (无泄露)',
        'mae': mae,
        'rmse': rmse,
        'r2': r2,
        'mape': mape
    }


def main():
    print("\n" + "#" * 60)
    print("# Kaggle 铜牌代码 vs 我们的方法 对比测试")
    print("#" * 60)
    
    results = []
    
    # 运行 Kaggle LSTM 方法
    lstm_result = run_kaggle_lstm_method()
    if lstm_result:
        results.append(lstm_result)
    
    # 运行我们的 Ridge 方法
    ridge_result = run_our_ridge_method()
    results.append(ridge_result)
    
    # 对比结果
    if len(results) > 1:
        print("\n" + "=" * 60)
        print("方法对比总结")
        print("=" * 60)
        print(f"{'方法':<20} {'MAE (kW)':<12} {'RMSE (kW)':<12} {'R²':<10} {'MAPE (%)':<10}")
        print("-" * 60)
        for r in results:
            print(f"{r['method']:<20} {r['mae']:<12.2f} {r['rmse']:<12.2f} {r['r2']:<10.4f} {r['mape']:<10.2f}")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
