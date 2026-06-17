# @AI_GENERATED: Kiro v1.0
"""
单个逆变器的LSTM vs Ridge对比训练和绘图
复现ipynb中的方法：只用Plant 1的DC_POWER数据
"""

import pandas as pd
import numpy as np
import os
import json

# 设置非交互式后端
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from sklearn.preprocessing import MinMaxScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# 数据路径
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')

SEQ_LENGTH = 24  # 与ipynb一致


def create_sequences(data, seq_length):
    """创建时序序列"""
    x, y = [], []
    for i in range(len(data) - seq_length):
        x.append(data[i:(i + seq_length)])
        y.append(data[i + seq_length])
    return np.array(x), np.array(y)


def main():
    print("=" * 70)
    print("单个逆变器 LSTM vs Ridge 对比")
    print("=" * 70)
    
    # 1. 加载Plant 1数据（与ipynb一致）
    print("\n1. 加载数据...")
    df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
    df = df.sort_values('DATE_TIME')
    
    print(f"  原始数据: {len(df)} 条记录")
    print(f"  时间范围: {df['DATE_TIME'].min()} 到 {df['DATE_TIME'].max()}")
    print(f"  逆变器数量: {df['SOURCE_KEY'].nunique()}")
    
    # 2. 只取第一个逆变器的数据（与ipynb一致）
    first_inverter = df['SOURCE_KEY'].unique()[0]
    df_single = df[df['SOURCE_KEY'] == first_inverter].copy()
    df_single = df_single.sort_values('DATE_TIME').reset_index(drop=True)
    
    print(f"\n  选择逆变器: {first_inverter}")
    print(f"  单逆变器数据: {len(df_single)} 条记录")
    
    # 3. 特征缩放
    data = df_single[['DC_POWER']].values
    scaler = MinMaxScaler(feature_range=(0, 1))
    scaled_data = scaler.fit_transform(data)
    
    # 4. 创建序列
    X, y = create_sequences(scaled_data, SEQ_LENGTH)
    print(f"\n  序列形状: X={X.shape}, y={y.shape}")
    
    # 5. 训练/测试划分（80/20，与ipynb一致）
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]
    
    print(f"  训练集: {len(X_train)}, 测试集: {len(X_test)}")
    
    # 获取对应的时间戳
    timestamps = df_single['DATE_TIME'].values[SEQ_LENGTH:]
    train_timestamps = timestamps[:split]
    test_timestamps = timestamps[split:]
    
    print(f"\n  训练集时间: {pd.Timestamp(train_timestamps[0])} 到 {pd.Timestamp(train_timestamps[-1])}")
    print(f"  测试集时间: {pd.Timestamp(test_timestamps[0])} 到 {pd.Timestamp(test_timestamps[-1])}")
    
    # 6. Ridge回归训练
    print("\n2. 训练Ridge回归...")
    X_train_flat = X_train.reshape(X_train.shape[0], -1)
    X_test_flat = X_test.reshape(X_test.shape[0], -1)
    
    ridge = Ridge(alpha=1.0)
    ridge.fit(X_train_flat, y_train.ravel())
    
    ridge_train_pred = ridge.predict(X_train_flat)
    ridge_test_pred = ridge.predict(X_test_flat)
    
    # 反归一化
    ridge_train_pred_inv = scaler.inverse_transform(ridge_train_pred.reshape(-1, 1)).ravel()
    ridge_test_pred_inv = scaler.inverse_transform(ridge_test_pred.reshape(-1, 1)).ravel()
    y_train_inv = scaler.inverse_transform(y_train).ravel()
    y_test_inv = scaler.inverse_transform(y_test).ravel()
    
    ridge_test_mae = mean_absolute_error(y_test_inv, ridge_test_pred_inv)
    ridge_test_rmse = np.sqrt(mean_squared_error(y_test_inv, ridge_test_pred_inv))
    ridge_test_r2 = r2_score(y_test_inv, ridge_test_pred_inv)
    
    print(f"  Ridge 测试集: MAE={ridge_test_mae:.2f}, RMSE={ridge_test_rmse:.2f}, R²={ridge_test_r2:.4f}")
    
    # 7. LSTM训练
    print("\n3. 训练LSTM...")
    try:
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import LSTM, Dense, Dropout
        from tensorflow.keras.callbacks import EarlyStopping
        
        # 构建LSTM模型（与ipynb一致）
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
        
        print("  开始训练...")
        history = model.fit(
            X_train, y_train,
            batch_size=32,
            epochs=50,
            validation_split=0.1,
            callbacks=[early_stop],
            verbose=1
        )
        
        lstm_train_pred = model.predict(X_train)
        lstm_test_pred = model.predict(X_test)
        
        # 反归一化
        lstm_train_pred_inv = scaler.inverse_transform(lstm_train_pred).ravel()
        lstm_test_pred_inv = scaler.inverse_transform(lstm_test_pred).ravel()
        
        lstm_test_mae = mean_absolute_error(y_test_inv, lstm_test_pred_inv)
        lstm_test_rmse = np.sqrt(mean_squared_error(y_test_inv, lstm_test_pred_inv))
        lstm_test_r2 = r2_score(y_test_inv, lstm_test_pred_inv)
        
        print(f"\n  LSTM 测试集: MAE={lstm_test_mae:.2f}, RMSE={lstm_test_rmse:.2f}, R²={lstm_test_r2:.4f}")
        has_lstm = True
        
    except Exception as e:
        print(f"  LSTM训练失败: {e}")
        has_lstm = False
        lstm_train_pred_inv = None
        lstm_test_pred_inv = None
    
    # 8. 绘图
    print("\n4. 生成图表...")

    # 图1: 测试集前200点（与ipynb一致）
    fig1, ax1 = plt.subplots(figsize=(15, 6))
    
    plot_len = min(200, len(y_test_inv))
    
    ax1.plot(range(plot_len), y_test_inv[:plot_len], 'b-', linewidth=1.2, 
             alpha=0.8, label='实际值')
    ax1.plot(range(plot_len), ridge_test_pred_inv[:plot_len], 'r--', linewidth=1.2, 
             alpha=0.8, label='Ridge预测')
    
    if has_lstm:
        ax1.plot(range(plot_len), lstm_test_pred_inv[:plot_len], 'orange', linewidth=1.2, 
                 linestyle='--', alpha=0.8, label='LSTM预测')
    
    ax1.fill_between(range(plot_len), y_test_inv[:plot_len], ridge_test_pred_inv[:plot_len], 
                     alpha=0.1, color='red')
    
    ax1.set_xlabel('时间步 (15分钟间隔)')
    ax1.set_ylabel('DC功率 (kW)')
    ax1.set_title(f'单逆变器预测对比 - 测试集前{plot_len}点 (约{plot_len*15/60:.0f}小时)\n'
                  f'时间: {pd.Timestamp(test_timestamps[0]).strftime("%Y-%m-%d %H:%M")} 起')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    output_file1 = os.path.join(DATA_DIR, 'single_inverter_test_200.png')
    plt.tight_layout()
    plt.savefig(output_file1, dpi=150, bbox_inches='tight')
    print(f"  保存: {output_file1}")
    plt.close()
    
    # 图2: 测试集完整时序图（带日期）
    fig2, axes2 = plt.subplots(2 if has_lstm else 1, 1, figsize=(16, 10 if has_lstm else 6))
    if not has_lstm:
        axes2 = [axes2]
    
    test_ts = pd.to_datetime(test_timestamps)
    
    ax2 = axes2[0]
    ax2.plot(test_ts, y_test_inv, 'b-', linewidth=0.8, alpha=0.8, label='实际值')
    ax2.plot(test_ts, ridge_test_pred_inv, 'r-', linewidth=0.8, alpha=0.8, label='Ridge预测')
    ax2.set_xlabel('日期')
    ax2.set_ylabel('DC功率 (kW)')
    ax2.set_title(f'Ridge回归 - 单逆变器测试集 (MAE={ridge_test_mae:.1f}kW, R²={ridge_test_r2:.4f})')
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax2.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
    
    if has_lstm:
        ax3 = axes2[1]
        ax3.plot(test_ts, y_test_inv, 'b-', linewidth=0.8, alpha=0.8, label='实际值')
        ax3.plot(test_ts, lstm_test_pred_inv, 'orange', linewidth=0.8, alpha=0.8, label='LSTM预测')
        ax3.set_xlabel('日期')
        ax3.set_ylabel('DC功率 (kW)')
        ax3.set_title(f'LSTM - 单逆变器测试集 (MAE={lstm_test_mae:.1f}kW, R²={lstm_test_r2:.4f})')
        ax3.legend(loc='upper right')
        ax3.grid(True, alpha=0.3)
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax3.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    output_file2 = os.path.join(DATA_DIR, 'single_inverter_test_full.png')
    plt.savefig(output_file2, dpi=150, bbox_inches='tight')
    print(f"  保存: {output_file2}")
    plt.close()
    
    # 图3: 训练集时序图
    fig3, axes3 = plt.subplots(2 if has_lstm else 1, 1, figsize=(16, 10 if has_lstm else 6))
    if not has_lstm:
        axes3 = [axes3]
    
    train_ts = pd.to_datetime(train_timestamps)
    # 只取最后7天
    last_7days = train_ts[-7*96:]  # 7天 * 96个15分钟
    last_7days_idx = len(train_ts) - len(last_7days)
    
    ax4 = axes3[0]
    ax4.plot(last_7days, y_train_inv[last_7days_idx:], 'b-', linewidth=0.8, alpha=0.8, label='实际值')
    ax4.plot(last_7days, ridge_train_pred_inv[last_7days_idx:], 'r-', linewidth=0.8, alpha=0.8, label='Ridge预测')
    ax4.set_xlabel('日期')
    ax4.set_ylabel('DC功率 (kW)')
    ax4.set_title(f'Ridge回归 - 单逆变器训练集最后7天')
    ax4.legend(loc='upper right')
    ax4.grid(True, alpha=0.3)
    ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax4.xaxis.set_major_locator(mdates.DayLocator(interval=1))
    plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)
    
    if has_lstm:
        ax5 = axes3[1]
        ax5.plot(last_7days, y_train_inv[last_7days_idx:], 'b-', linewidth=0.8, alpha=0.8, label='实际值')
        ax5.plot(last_7days, lstm_train_pred_inv[last_7days_idx:], 'orange', linewidth=0.8, alpha=0.8, label='LSTM预测')
        ax5.set_xlabel('日期')
        ax5.set_ylabel('DC功率 (kW)')
        ax5.set_title(f'LSTM - 单逆变器训练集最后7天')
        ax5.legend(loc='upper right')
        ax5.grid(True, alpha=0.3)
        ax5.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax5.xaxis.set_major_locator(mdates.DayLocator(interval=1))
        plt.setp(ax5.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    output_file3 = os.path.join(DATA_DIR, 'single_inverter_train.png')
    plt.savefig(output_file3, dpi=150, bbox_inches='tight')
    print(f"  保存: {output_file3}")
    plt.close()
    
    # 保存结果
    results = {
        'inverter': first_inverter,
        'train_samples': len(X_train),
        'test_samples': len(X_test),
        'ridge': {
            'mae': float(ridge_test_mae),
            'rmse': float(ridge_test_rmse),
            'r2': float(ridge_test_r2)
        }
    }
    
    if has_lstm:
        results['lstm'] = {
            'mae': float(lstm_test_mae),
            'rmse': float(lstm_test_rmse),
            'r2': float(lstm_test_r2)
        }
    
    results_file = os.path.join(DATA_DIR, 'single_inverter_results.json')
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  保存: {results_file}")
    
    print("\n" + "=" * 70)
    print("完成！")
    print("=" * 70)
    print(f"\n结果对比:")
    print(f"  Ridge: MAE={ridge_test_mae:.2f}kW, RMSE={ridge_test_rmse:.2f}kW, R²={ridge_test_r2:.4f}")
    if has_lstm:
        print(f"  LSTM:  MAE={lstm_test_mae:.2f}kW, RMSE={lstm_test_rmse:.2f}kW, R²={lstm_test_r2:.4f}")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
