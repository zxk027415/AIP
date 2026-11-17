# @AI_GENERATED: Kiro v1.0
"""
绘制 LSTM vs Ridge 预测结果的时序曲线对比图
"""

import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

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
    print("绘制 LSTM vs Ridge 时序对比图")
    print("=" * 70)
    
    # 1. 加载数据
    gen_file = os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv')
    weather_file = os.path.join(DATA_DIR, 'Plant_1_Weather_Sensor_Data.csv')
    
    df = pd.read_csv(gen_file)
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    
    weather_df = pd.read_csv(weather_file)
    weather_df['DATE_TIME'] = pd.to_datetime(weather_df['DATE_TIME'], dayfirst=True)
    
    print(f"数据量: {len(df)} 条记录")
    print(f"时间范围: {df['DATE_TIME'].min()} ~ {df['DATE_TIME'].max()}")
    
    # 2. 准备 LSTM 数据
    data = df[['DC_POWER']].values
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    
    SEQ_LENGTH = 24
    X_seq, y_seq = create_sequences(scaled_data, SEQ_LENGTH)
    
    split = int(len(X_seq) * 0.8)
    X_train_seq, X_test_seq = X_seq[:split], X_seq[split:]
    y_train_seq, y_test_seq = y_seq[:split], y_seq[split:]
    
    test_start_idx = split + SEQ_LENGTH
    
    # 3. 准备 Ridge 数据
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
    timestamps_train = timestamps_all[:test_start_idx]
    timestamps_test = timestamps_all[test_start_idx:]
    
    # 4. 训练 Ridge
    print("\n训练 Ridge 模型...")
    X_mean = X_train_ridge.mean(axis=0)
    X_std = X_train_ridge.std(axis=0) + 1e-8
    X_train_norm = (X_train_ridge - X_mean) / X_std
    X_test_norm = (X_test_ridge - X_mean) / X_std
    
    lambda_reg = 0.01
    n_features = X_train_norm.shape[1]
    X_train_bias = np.c_[np.ones(len(X_train_norm)), X_train_norm]
    X_test_bias = np.c_[np.ones(len(X_test_norm)), X_test_norm]
    
    I = np.eye(n_features + 1)
    I[0, 0] = 0
    theta = np.linalg.inv(X_train_bias.T @ X_train_bias + lambda_reg * I) @ X_train_bias.T @ y_train_ridge
    
    y_pred_ridge_train = X_train_bias @ theta
    y_pred_ridge_test = X_test_bias @ theta
    
    # Ridge 指标
    mae_ridge = mean_absolute_error(y_test_ridge, y_pred_ridge_test)
    rmse_ridge = np.sqrt(mean_squared_error(y_test_ridge, y_pred_ridge_test))
    r2_ridge = r2_score(y_test_ridge, y_pred_ridge_test)
    print(f"Ridge - MAE: {mae_ridge:.2f}, RMSE: {rmse_ridge:.2f}, R²: {r2_ridge:.4f}")
    
    # 5. 训练 LSTM
    has_lstm = False
    try:
        import tensorflow as tf
        print("\n训练 LSTM 模型...")
        
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
        model.fit(
            X_train_seq, y_train_seq, 
            epochs=50, batch_size=32, 
            validation_split=0.1, 
            callbacks=[early_stop],
            verbose=0
        )
        
        # 预测
        y_pred_lstm_train_scaled = model.predict(X_train_seq, verbose=0)
        y_pred_lstm_test_scaled = model.predict(X_test_seq, verbose=0)
        
        # 反归一化
        y_train_lstm = scaler.inverse_transform(y_train_seq).flatten()
        y_test_lstm = scaler.inverse_transform(y_test_seq).flatten()
        y_pred_lstm_train = scaler.inverse_transform(y_pred_lstm_train_scaled).flatten()
        y_pred_lstm_test = scaler.inverse_transform(y_pred_lstm_test_scaled).flatten()
        
        # LSTM 时间戳（比 Ridge 少 SEQ_LENGTH 个点）
        timestamps_lstm_train = timestamps_all[SEQ_LENGTH:SEQ_LENGTH+len(y_train_lstm)]
        timestamps_lstm_test = timestamps_all[test_start_idx:test_start_idx+len(y_test_lstm)]
        
        # LSTM 指标
        mae_lstm = mean_absolute_error(y_test_lstm, y_pred_lstm_test)
        rmse_lstm = np.sqrt(mean_squared_error(y_test_lstm, y_pred_lstm_test))
        r2_lstm = r2_score(y_test_lstm, y_pred_lstm_test)
        print(f"LSTM - MAE: {mae_lstm:.2f}, RMSE: {rmse_lstm:.2f}, R²: {r2_lstm:.4f}")
        
        has_lstm = True
    except ImportError:
        print("TensorFlow 未安装，仅绘制 Ridge 结果")
    
    # 6. 绘图
    print("\n生成图表...")
    
    # 图1: 全局时序图（训练+测试）
    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    
    # 子图1: Ridge 全局
    ax1 = axes[0]
    ax1.plot(timestamps_train, y_train_ridge, 'b-', alpha=0.5, linewidth=0.5, label='实际值(训练)')
    ax1.plot(timestamps_train, y_pred_ridge_train, 'g-', alpha=0.5, linewidth=0.5, label='Ridge预测(训练)')
    ax1.plot(timestamps_test, y_test_ridge, 'b-', linewidth=0.8, label='实际值(测试)')
    ax1.plot(timestamps_test, y_pred_ridge_test, 'r-', linewidth=0.8, label='Ridge预测(测试)')
    ax1.axvline(x=timestamps_test[0], color='k', linestyle='--', linewidth=2, label='训练/测试分界')
    ax1.set_xlabel('时间')
    ax1.set_ylabel('DC功率 (kW)')
    ax1.set_title(f'Ridge回归预测结果 (测试集 MAE={mae_ridge:.1f}kW, R²={r2_ridge:.4f})')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    # 子图2: LSTM 全局（如果有）
    ax2 = axes[1]
    if has_lstm:
        ax2.plot(timestamps_lstm_train, y_train_lstm, 'b-', alpha=0.5, linewidth=0.5, label='实际值(训练)')
        ax2.plot(timestamps_lstm_train, y_pred_lstm_train, 'g-', alpha=0.5, linewidth=0.5, label='LSTM预测(训练)')
        ax2.plot(timestamps_lstm_test, y_test_lstm, 'b-', linewidth=0.8, label='实际值(测试)')
        ax2.plot(timestamps_lstm_test, y_pred_lstm_test, 'orange', linewidth=0.8, label='LSTM预测(测试)')
        ax2.axvline(x=timestamps_lstm_test[0], color='k', linestyle='--', linewidth=2, label='训练/测试分界')
        ax2.set_title(f'LSTM预测结果 (测试集 MAE={mae_lstm:.1f}kW, R²={r2_lstm:.4f})')
    else:
        ax2.text(0.5, 0.5, 'TensorFlow 未安装，无法显示 LSTM 结果', 
                 ha='center', va='center', transform=ax2.transAxes, fontsize=14)
    ax2.set_xlabel('时间')
    ax2.set_ylabel('DC功率 (kW)')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    plt.tight_layout()
    output_file1 = os.path.join(OUTPUT_DIR, 'comparison_full_timeseries.png')
    plt.savefig(output_file1, dpi=150, bbox_inches='tight')
    print(f"保存: {output_file1}")
    
    # 图2: 测试集局部放大（选取一段典型时间）
    fig2, axes2 = plt.subplots(2, 1, figsize=(16, 10))
    
    # 选取测试集前500个点进行放大展示
    zoom_len = min(500, len(y_test_ridge))
    
    ax3 = axes2[0]
    ax3.plot(timestamps_test[:zoom_len], y_test_ridge[:zoom_len], 'b-', linewidth=1.5, label='实际值', marker='o', markersize=2)
    ax3.plot(timestamps_test[:zoom_len], y_pred_ridge_test[:zoom_len], 'r-', linewidth=1.5, label='Ridge预测', marker='s', markersize=2)
    ax3.set_xlabel('时间')
    ax3.set_ylabel('DC功率 (kW)')
    ax3.set_title(f'Ridge回归 - 测试集局部放大 (前{zoom_len}个点)')
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
    
    ax4 = axes2[1]
    if has_lstm:
        zoom_len_lstm = min(500, len(y_test_lstm))
        ax4.plot(timestamps_lstm_test[:zoom_len_lstm], y_test_lstm[:zoom_len_lstm], 'b-', linewidth=1.5, label='实际值', marker='o', markersize=2)
        ax4.plot(timestamps_lstm_test[:zoom_len_lstm], y_pred_lstm_test[:zoom_len_lstm], 'orange', linewidth=1.5, label='LSTM预测', marker='s', markersize=2)
        ax4.set_title(f'LSTM - 测试集局部放大 (前{zoom_len_lstm}个点)')
    else:
        ax4.text(0.5, 0.5, 'TensorFlow 未安装', ha='center', va='center', transform=ax4.transAxes, fontsize=14)
    ax4.set_xlabel('时间')
    ax4.set_ylabel('DC功率 (kW)')
    ax4.legend(loc='upper right')
    ax4.grid(True, alpha=0.3)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    output_file2 = os.path.join(OUTPUT_DIR, 'comparison_test_zoom.png')
    plt.savefig(output_file2, dpi=150, bbox_inches='tight')
    print(f"保存: {output_file2}")
    
    # 图3: 误差对比图
    fig3, axes3 = plt.subplots(2, 2, figsize=(14, 10))
    
    # 误差时序
    errors_ridge = y_pred_ridge_test - y_test_ridge
    ax5 = axes3[0, 0]
    ax5.plot(timestamps_test, errors_ridge, 'r-', linewidth=0.5, alpha=0.7)
    ax5.axhline(y=0, color='k', linestyle='-', linewidth=1)
    ax5.fill_between(timestamps_test, errors_ridge, 0, alpha=0.3, color='red')
    ax5.set_xlabel('时间')
    ax5.set_ylabel('预测误差 (kW)')
    ax5.set_title('Ridge 预测误差时序')
    ax5.grid(True, alpha=0.3)
    ax5.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    if has_lstm:
        errors_lstm = y_pred_lstm_test - y_test_lstm
        ax6 = axes3[0, 1]
        ax6.plot(timestamps_lstm_test, errors_lstm, 'orange', linewidth=0.5, alpha=0.7)
        ax6.axhline(y=0, color='k', linestyle='-', linewidth=1)
        ax6.fill_between(timestamps_lstm_test, errors_lstm, 0, alpha=0.3, color='orange')
        ax6.set_xlabel('时间')
        ax6.set_ylabel('预测误差 (kW)')
        ax6.set_title('LSTM 预测误差时序')
        ax6.grid(True, alpha=0.3)
        ax6.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    # 误差分布直方图
    ax7 = axes3[1, 0]
    ax7.hist(errors_ridge, bins=50, color='red', alpha=0.7, edgecolor='black')
    ax7.axvline(x=0, color='k', linestyle='--', linewidth=2)
    ax7.axvline(x=np.mean(errors_ridge), color='blue', linestyle='-', linewidth=2, label=f'均值={np.mean(errors_ridge):.1f}')
    ax7.set_xlabel('预测误差 (kW)')
    ax7.set_ylabel('频次')
    ax7.set_title(f'Ridge 误差分布 (std={np.std(errors_ridge):.1f})')
    ax7.legend()
    ax7.grid(True, alpha=0.3)
    
    if has_lstm:
        ax8 = axes3[1, 1]
        ax8.hist(errors_lstm, bins=50, color='orange', alpha=0.7, edgecolor='black')
        ax8.axvline(x=0, color='k', linestyle='--', linewidth=2)
        ax8.axvline(x=np.mean(errors_lstm), color='blue', linestyle='-', linewidth=2, label=f'均值={np.mean(errors_lstm):.1f}')
        ax8.set_xlabel('预测误差 (kW)')
        ax8.set_ylabel('频次')
        ax8.set_title(f'LSTM 误差分布 (std={np.std(errors_lstm):.1f})')
        ax8.legend()
        ax8.grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_file3 = os.path.join(OUTPUT_DIR, 'comparison_errors.png')
    plt.savefig(output_file3, dpi=150, bbox_inches='tight')
    print(f"保存: {output_file3}")
    
    # 图4: 散点图对比
    fig4, axes4 = plt.subplots(1, 2, figsize=(14, 6))
    
    ax9 = axes4[0]
    ax9.scatter(y_test_ridge, y_pred_ridge_test, alpha=0.3, s=5, c='red')
    max_val = max(y_test_ridge.max(), y_pred_ridge_test.max())
    ax9.plot([0, max_val], [0, max_val], 'k--', linewidth=2, label='理想线 y=x')
    ax9.set_xlabel('实际值 (kW)')
    ax9.set_ylabel('预测值 (kW)')
    ax9.set_title(f'Ridge 散点图 (R²={r2_ridge:.4f})')
    ax9.legend()
    ax9.grid(True, alpha=0.3)
    ax9.set_aspect('equal')
    
    if has_lstm:
        ax10 = axes4[1]
        ax10.scatter(y_test_lstm, y_pred_lstm_test, alpha=0.3, s=5, c='orange')
        max_val_lstm = max(y_test_lstm.max(), y_pred_lstm_test.max())
        ax10.plot([0, max_val_lstm], [0, max_val_lstm], 'k--', linewidth=2, label='理想线 y=x')
        ax10.set_xlabel('实际值 (kW)')
        ax10.set_ylabel('预测值 (kW)')
        ax10.set_title(f'LSTM 散点图 (R²={r2_lstm:.4f})')
        ax10.legend()
        ax10.grid(True, alpha=0.3)
        ax10.set_aspect('equal')
    
    plt.tight_layout()
    output_file4 = os.path.join(OUTPUT_DIR, 'comparison_scatter.png')
    plt.savefig(output_file4, dpi=150, bbox_inches='tight')
    print(f"保存: {output_file4}")
    
    print("\n" + "=" * 70)
    print("图表生成完成！")
    print("=" * 70)
    print(f"\n生成的图表文件:")
    print(f"  1. {output_file1} - 全局时序图")
    print(f"  2. {output_file2} - 测试集局部放大")
    print(f"  3. {output_file3} - 误差分析图")
    print(f"  4. {output_file4} - 散点对比图")
    
    # 关闭所有图表（不显示交互窗口）
    plt.close('all')


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
