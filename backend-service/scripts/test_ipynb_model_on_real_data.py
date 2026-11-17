# @AI_GENERATED: Kiro v1.0
"""
用ipynb原始方法训练的模型，测试在真实场景下的预测效果：
1. 单个逆变器的时序预测
2. 整个场站(Plant1)总功率的时序预测
"""

import pandas as pd
import numpy as np
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

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


def train_ipynb_model():
    """按ipynb原始方式训练模型（混合所有逆变器数据）"""
    print("=" * 60)
    print("Step 1: 按ipynb原始方式训练模型")
    print("=" * 60)
    
    df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    
    # 混合所有逆变器数据
    data = df[['DC_POWER']].values
    print(f"训练数据: {len(data)} 样本 (22个逆变器混合)")
    
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    
    X, y = create_sequences(scaled_data, SEQ_LENGTH)
    split = int(len(X) * 0.8)
    X_train, y_train = X[:split], y[:split]
    
    # 训练LSTM (简化版，加速训练)
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense
    
    model = Sequential([
        LSTM(32, input_shape=(SEQ_LENGTH, 1)),
        Dense(1)
    ])
    model.compile(optimizer='adam', loss='mse', metrics=['mae'])
    print("训练中 (3 epochs)...")
    model.fit(X_train, y_train, epochs=3, batch_size=64, validation_split=0.1, verbose=1)
    
    print("模型训练完成")
    return model, scaler


def test_single_inverter(model, scaler):
    """测试单个逆变器的预测效果"""
    print("\n" + "=" * 60)
    print("Step 2: 测试单个逆变器预测")
    print("=" * 60)
    
    df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    
    # 选择第一个逆变器
    inverter_id = df['SOURCE_KEY'].unique()[0]
    inv_df = df[df['SOURCE_KEY'] == inverter_id].copy()
    inv_df = inv_df.sort_values('DATE_TIME').reset_index(drop=True)
    
    print(f"逆变器: {inverter_id}")
    print(f"数据点: {len(inv_df)}")
    
    # 准备数据
    data = inv_df[['DC_POWER']].values
    scaled_data = scaler.transform(data)
    
    X, y = create_sequences(scaled_data, SEQ_LENGTH)
    
    # 使用后20%作为测试集
    split = int(len(X) * 0.8)
    X_test, y_test = X[split:], y[split:]
    times = inv_df['DATE_TIME'].values[split + SEQ_LENGTH:]
    
    # 预测
    predictions_scaled = model.predict(X_test, verbose=0)
    actual = scaler.inverse_transform(y_test.reshape(-1, 1))
    predicted = scaler.inverse_transform(predictions_scaled)
    
    mae = mean_absolute_error(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))
    print(f"MAE: {mae:.2f} kW, RMSE: {rmse:.2f} kW")
    
    return times, actual.flatten(), predicted.flatten(), inverter_id, mae, rmse


def test_plant_total(model, scaler):
    """测试整个场站总功率的预测效果"""
    print("\n" + "=" * 60)
    print("Step 3: 测试场站总功率预测")
    print("=" * 60)
    
    df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    
    # 按时间聚合所有逆变器的功率
    plant_df = df.groupby('DATE_TIME').agg({'DC_POWER': 'sum'}).reset_index()
    plant_df = plant_df.sort_values('DATE_TIME').reset_index(drop=True)
    
    print(f"场站总功率数据点: {len(plant_df)}")
    print(f"功率范围: {plant_df['DC_POWER'].min():.0f} - {plant_df['DC_POWER'].max():.0f} kW")
    
    # 准备数据 - 需要用场站数据重新fit scaler
    data = plant_df[['DC_POWER']].values
    plant_scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = plant_scaler.fit_transform(data)
    
    X, y = create_sequences(scaled_data, SEQ_LENGTH)
    
    # 使用后20%作为测试集
    split = int(len(X) * 0.8)
    X_test, y_test = X[split:], y[split:]
    times = plant_df['DATE_TIME'].values[split + SEQ_LENGTH:]
    
    # 预测
    predictions_scaled = model.predict(X_test, verbose=0)
    actual = plant_scaler.inverse_transform(y_test.reshape(-1, 1))
    predicted = plant_scaler.inverse_transform(predictions_scaled)
    
    mae = mean_absolute_error(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))
    print(f"MAE: {mae:.2f} kW, RMSE: {rmse:.2f} kW")
    
    return times, actual.flatten(), predicted.flatten(), mae, rmse


def plot_results(inv_times, inv_actual, inv_pred, inv_id, inv_mae, inv_rmse,
                 plant_times, plant_actual, plant_pred, plant_mae, plant_rmse):
    """绘制对比图"""
    print("\n" + "=" * 60)
    print("Step 4: 绘制时序对比图")
    print("=" * 60)
    
    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    
    # 图1: 单个逆变器
    ax1 = axes[0]
    n_points = min(200, len(inv_actual))
    ax1.plot(inv_times[:n_points], inv_actual[:n_points], 
             label='Actual', color='#2c3e50', alpha=0.7, linewidth=1.5)
    ax1.plot(inv_times[:n_points], inv_pred[:n_points], 
             label='Predicted', color='#e74c3c', linestyle='--', linewidth=1.5)
    ax1.fill_between(inv_times[:n_points], inv_actual[:n_points], inv_pred[:n_points],
                     color='#e74c3c', alpha=0.1)
    ax1.set_title(f'Single Inverter Prediction ({inv_id[:20]}...)\nMAE: {inv_mae:.2f} kW, RMSE: {inv_rmse:.2f} kW',
                  fontsize=12)
    ax1.set_xlabel('Time')
    ax1.set_ylabel('DC Power (kW)')
    ax1.legend(loc='upper right')
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    ax1.tick_params(axis='x', rotation=45)
    ax1.grid(True, alpha=0.3)
    
    # 图2: 场站总功率
    ax2 = axes[1]
    n_points = min(200, len(plant_actual))
    ax2.plot(plant_times[:n_points], plant_actual[:n_points], 
             label='Actual', color='#2c3e50', alpha=0.7, linewidth=1.5)
    ax2.plot(plant_times[:n_points], plant_pred[:n_points], 
             label='Predicted', color='#27ae60', linestyle='--', linewidth=1.5)
    ax2.fill_between(plant_times[:n_points], plant_actual[:n_points], plant_pred[:n_points],
                     color='#27ae60', alpha=0.1)
    ax2.set_title(f'Plant 1 Total Power Prediction (22 Inverters Sum)\nMAE: {plant_mae:.2f} kW, RMSE: {plant_rmse:.2f} kW',
                  fontsize=12)
    ax2.set_xlabel('Time')
    ax2.set_ylabel('DC Power (kW)')
    ax2.legend(loc='upper right')
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    ax2.tick_params(axis='x', rotation=45)
    ax2.grid(True, alpha=0.3)
    
    plt.suptitle('ipynb Mixed-Inverter Model Applied to Real Scenarios', fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    output_file = os.path.join(DATA_DIR, 'ipynb_model_real_scenarios.png')
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"保存: {output_file}")
    plt.close()


def main():
    # 训练模型
    model, scaler = train_ipynb_model()
    
    # 测试单个逆变器
    inv_times, inv_actual, inv_pred, inv_id, inv_mae, inv_rmse = test_single_inverter(model, scaler)
    
    # 测试场站总功率
    plant_times, plant_actual, plant_pred, plant_mae, plant_rmse = test_plant_total(model, scaler)
    
    # 绘图
    plot_results(inv_times, inv_actual, inv_pred, inv_id, inv_mae, inv_rmse,
                 plant_times, plant_actual, plant_pred, plant_mae, plant_rmse)
    
    # 总结
    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    print(f"单逆变器预测: MAE={inv_mae:.2f} kW, RMSE={inv_rmse:.2f} kW")
    print(f"场站总功率预测: MAE={plant_mae:.2f} kW, RMSE={plant_rmse:.2f} kW")
    print("\n完成!")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
