# @AI_GENERATED: Kiro v1.0
"""
从保存的预测结果文件绘制时序对比图
"""

import pandas as pd
import numpy as np
import os
import json

# 设置非交互式后端（必须在 import pyplot 之前）
import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 数据路径
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')


def main():
    print("=" * 70)
    print("从保存的数据绘制时序对比图")
    print("=" * 70)
    
    # 1. 加载数据
    print("\n加载预测结果...")
    
    ridge_file = os.path.join(DATA_DIR, 'ridge_predictions.csv')
    lstm_file = os.path.join(DATA_DIR, 'lstm_predictions.csv')
    metadata_file = os.path.join(DATA_DIR, 'model_metadata.json')
    
    # 加载 Ridge 数据
    ridge_df = pd.read_csv(ridge_file)
    ridge_df['timestamp'] = pd.to_datetime(ridge_df['timestamp'])
    print(f"  Ridge 数据: {len(ridge_df)} 条记录")
    
    # 加载 LSTM 数据（如果存在）
    has_lstm = os.path.exists(lstm_file)
    if has_lstm:
        lstm_df = pd.read_csv(lstm_file)
        lstm_df['timestamp'] = pd.to_datetime(lstm_df['timestamp'])
        print(f"  LSTM 数据: {len(lstm_df)} 条记录")
    else:
        print("  LSTM 数据: 不存在")
    
    # 加载元数据
    with open(metadata_file, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
    
    ridge_metrics = metadata['ridge']
    lstm_metrics = metadata.get('lstm', None)
    
    # 分离训练集和测试集
    ridge_train = ridge_df[ridge_df['is_train'] == True]
    ridge_test = ridge_df[ridge_df['is_train'] == False]
    
    if has_lstm:
        lstm_train = lstm_df[lstm_df['is_train'] == True]
        lstm_test = lstm_df[lstm_df['is_train'] == False]
    
    print(f"\n数据划分:")
    print(f"  Ridge 训练集: {len(ridge_train)}, 测试集: {len(ridge_test)}")
    if has_lstm:
        print(f"  LSTM 训练集: {len(lstm_train)}, 测试集: {len(lstm_test)}")
    
    # 2. 绘图
    print("\n生成图表...")
    
    # 图1: 全局时序图
    fig, axes = plt.subplots(2 if has_lstm else 1, 1, figsize=(16, 10 if has_lstm else 6))
    if not has_lstm:
        axes = [axes]
    
    # Ridge 全局
    ax1 = axes[0]
    ax1.plot(ridge_train['timestamp'], ridge_train['actual'], 'b-', alpha=0.5, linewidth=0.5, label='实际值(训练)')
    ax1.plot(ridge_train['timestamp'], ridge_train['predicted'], 'g-', alpha=0.5, linewidth=0.5, label='Ridge预测(训练)')
    ax1.plot(ridge_test['timestamp'], ridge_test['actual'], 'b-', linewidth=0.8, label='实际值(测试)')
    ax1.plot(ridge_test['timestamp'], ridge_test['predicted'], 'r-', linewidth=0.8, label='Ridge预测(测试)')
    ax1.axvline(x=ridge_test['timestamp'].iloc[0], color='k', linestyle='--', linewidth=2, label='训练/测试分界')
    ax1.set_xlabel('时间')
    ax1.set_ylabel('DC功率 (kW)')
    ax1.set_title(f'Ridge回归预测结果 (测试集 MAE={ridge_metrics["mae"]:.1f}kW, R²={ridge_metrics["r2"]:.4f})')
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    # LSTM 全局（如果有）
    if has_lstm:
        ax2 = axes[1]
        ax2.plot(lstm_train['timestamp'], lstm_train['actual'], 'b-', alpha=0.5, linewidth=0.5, label='实际值(训练)')
        ax2.plot(lstm_train['timestamp'], lstm_train['predicted'], 'g-', alpha=0.5, linewidth=0.5, label='LSTM预测(训练)')
        ax2.plot(lstm_test['timestamp'], lstm_test['actual'], 'b-', linewidth=0.8, label='实际值(测试)')
        ax2.plot(lstm_test['timestamp'], lstm_test['predicted'], 'orange', linewidth=0.8, label='LSTM预测(测试)')
        ax2.axvline(x=lstm_test['timestamp'].iloc[0], color='k', linestyle='--', linewidth=2, label='训练/测试分界')
        ax2.set_xlabel('时间')
        ax2.set_ylabel('DC功率 (kW)')
        ax2.set_title(f'LSTM预测结果 (测试集 MAE={lstm_metrics["mae"]:.1f}kW, R²={lstm_metrics["r2"]:.4f})')
        ax2.legend(loc='upper right')
        ax2.grid(True, alpha=0.3)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    plt.tight_layout()
    output_file1 = os.path.join(DATA_DIR, 'comparison_full_timeseries.png')
    plt.savefig(output_file1, dpi=150, bbox_inches='tight')
    print(f"  保存: {output_file1}")
    plt.close()
    
    # 图2: 连续多天时序图（横坐标是日期时间）- 测试集
    fig2, axes2 = plt.subplots(2 if has_lstm else 1, 1, figsize=(16, 10 if has_lstm else 6))
    if not has_lstm:
        axes2 = [axes2]
    
    # 先按时间戳聚合数据（因为有多个逆变器/电站）
    ridge_test_agg = ridge_test.groupby('timestamp').agg({
        'actual': 'sum',
        'predicted': 'sum'
    }).reset_index().sort_values('timestamp')
    
    # 取前14天的数据
    start_date = ridge_test_agg['timestamp'].min()
    end_date = start_date + pd.Timedelta(days=14)
    ridge_14days = ridge_test_agg[(ridge_test_agg['timestamp'] >= start_date) & 
                                   (ridge_test_agg['timestamp'] < end_date)]
    
    ax3 = axes2[0]
    ax3.plot(ridge_14days['timestamp'], ridge_14days['actual'] / 1000, 'b-', 
             linewidth=0.8, alpha=0.8, label='实际值')
    ax3.plot(ridge_14days['timestamp'], ridge_14days['predicted'] / 1000, 'r-', 
             linewidth=0.8, alpha=0.8, label='Ridge预测')
    ax3.set_xlabel('日期')
    ax3.set_ylabel('DC功率 (MW)')
    ax3.set_title(f'Ridge回归 - 测试集前14天时序曲线 (2020年)')
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax3.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
    
    if has_lstm:
        lstm_test_agg = lstm_test.groupby('timestamp').agg({
            'actual': 'sum',
            'predicted': 'sum'
        }).reset_index().sort_values('timestamp')
        
        start_date_lstm = lstm_test_agg['timestamp'].min()
        end_date_lstm = start_date_lstm + pd.Timedelta(days=14)
        lstm_14days = lstm_test_agg[(lstm_test_agg['timestamp'] >= start_date_lstm) & 
                                     (lstm_test_agg['timestamp'] < end_date_lstm)]
        
        ax4 = axes2[1]
        ax4.plot(lstm_14days['timestamp'], lstm_14days['actual'] / 1000, 'b-', 
                 linewidth=0.8, alpha=0.8, label='实际值')
        ax4.plot(lstm_14days['timestamp'], lstm_14days['predicted'] / 1000, 'orange', 
                 linewidth=0.8, alpha=0.8, label='LSTM预测')
        ax4.set_xlabel('日期')
        ax4.set_ylabel('DC功率 (MW)')
        ax4.set_title(f'LSTM - 测试集前14天时序曲线 (2020年)')
        ax4.legend(loc='upper right')
        ax4.grid(True, alpha=0.3)
        ax4.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax4.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    output_file2 = os.path.join(DATA_DIR, 'comparison_test_zoom.png')
    plt.savefig(output_file2, dpi=150, bbox_inches='tight')
    print(f"  保存: {output_file2}")
    plt.close()
    
    # 图2b: 训练集时序图
    fig2b, axes2b = plt.subplots(2 if has_lstm else 1, 1, figsize=(16, 10 if has_lstm else 6))
    if not has_lstm:
        axes2b = [axes2b]
    
    # Ridge 训练集聚合
    ridge_train_agg = ridge_train.groupby('timestamp').agg({
        'actual': 'sum',
        'predicted': 'sum'
    }).reset_index().sort_values('timestamp')
    
    # 取训练集最后14天
    end_date_train = ridge_train_agg['timestamp'].max()
    start_date_train = end_date_train - pd.Timedelta(days=14)
    ridge_train_14days = ridge_train_agg[(ridge_train_agg['timestamp'] >= start_date_train) & 
                                          (ridge_train_agg['timestamp'] <= end_date_train)]
    
    ax3b = axes2b[0]
    ax3b.plot(ridge_train_14days['timestamp'], ridge_train_14days['actual'] / 1000, 'b-', 
              linewidth=0.8, alpha=0.8, label='实际值')
    ax3b.plot(ridge_train_14days['timestamp'], ridge_train_14days['predicted'] / 1000, 'r-', 
              linewidth=0.8, alpha=0.8, label='Ridge预测')
    ax3b.set_xlabel('日期')
    ax3b.set_ylabel('DC功率 (MW)')
    ax3b.set_title(f'Ridge回归 - 训练集最后14天时序曲线 (2020年)')
    ax3b.legend(loc='upper right')
    ax3b.grid(True, alpha=0.3)
    ax3b.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax3b.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    plt.setp(ax3b.xaxis.get_majorticklabels(), rotation=45)
    
    if has_lstm:
        lstm_train_agg = lstm_train.groupby('timestamp').agg({
            'actual': 'sum',
            'predicted': 'sum'
        }).reset_index().sort_values('timestamp')
        
        end_date_train_lstm = lstm_train_agg['timestamp'].max()
        start_date_train_lstm = end_date_train_lstm - pd.Timedelta(days=14)
        lstm_train_14days = lstm_train_agg[(lstm_train_agg['timestamp'] >= start_date_train_lstm) & 
                                            (lstm_train_agg['timestamp'] <= end_date_train_lstm)]
        
        ax4b = axes2b[1]
        ax4b.plot(lstm_train_14days['timestamp'], lstm_train_14days['actual'] / 1000, 'b-', 
                  linewidth=0.8, alpha=0.8, label='实际值')
        ax4b.plot(lstm_train_14days['timestamp'], lstm_train_14days['predicted'] / 1000, 'orange', 
                  linewidth=0.8, alpha=0.8, label='LSTM预测')
        ax4b.set_xlabel('日期')
        ax4b.set_ylabel('DC功率 (MW)')
        ax4b.set_title(f'LSTM - 训练集最后14天时序曲线 (2020年)')
        ax4b.legend(loc='upper right')
        ax4b.grid(True, alpha=0.3)
        ax4b.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax4b.xaxis.set_major_locator(mdates.DayLocator(interval=2))
        plt.setp(ax4b.xaxis.get_majorticklabels(), rotation=45)
    
    plt.tight_layout()
    output_file2b = os.path.join(DATA_DIR, 'comparison_train_timeseries.png')
    plt.savefig(output_file2b, dpi=150, bbox_inches='tight')
    print(f"  保存: {output_file2b}")
    plt.close()
    
    # 图3: 误差分析
    fig3, axes3 = plt.subplots(2, 2, figsize=(14, 10))
    
    # Ridge 误差时序
    errors_ridge = ridge_test['predicted'].values - ridge_test['actual'].values
    ax5 = axes3[0, 0]
    ax5.plot(ridge_test['timestamp'], errors_ridge, 'r-', linewidth=0.5, alpha=0.7)
    ax5.axhline(y=0, color='k', linestyle='-', linewidth=1)
    ax5.fill_between(ridge_test['timestamp'], errors_ridge, 0, alpha=0.3, color='red')
    ax5.set_xlabel('时间')
    ax5.set_ylabel('预测误差 (kW)')
    ax5.set_title('Ridge 预测误差时序')
    ax5.grid(True, alpha=0.3)
    ax5.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    
    if has_lstm:
        errors_lstm = lstm_test['predicted'].values - lstm_test['actual'].values
        ax6 = axes3[0, 1]
        ax6.plot(lstm_test['timestamp'], errors_lstm, 'orange', linewidth=0.5, alpha=0.7)
        ax6.axhline(y=0, color='k', linestyle='-', linewidth=1)
        ax6.fill_between(lstm_test['timestamp'], errors_lstm, 0, alpha=0.3, color='orange')
        ax6.set_xlabel('时间')
        ax6.set_ylabel('预测误差 (kW)')
        ax6.set_title('LSTM 预测误差时序')
        ax6.grid(True, alpha=0.3)
        ax6.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    else:
        axes3[0, 1].text(0.5, 0.5, 'LSTM 数据不可用', ha='center', va='center', 
                         transform=axes3[0, 1].transAxes, fontsize=14)
        axes3[0, 1].set_title('LSTM 预测误差时序')
    
    # Ridge 误差分布
    ax7 = axes3[1, 0]
    ax7.hist(errors_ridge, bins=50, color='red', alpha=0.7, edgecolor='black')
    ax7.axvline(x=0, color='k', linestyle='--', linewidth=2)
    ax7.axvline(x=np.mean(errors_ridge), color='blue', linestyle='-', linewidth=2, 
                label=f'均值={np.mean(errors_ridge):.1f}')
    ax7.set_xlabel('预测误差 (kW)')
    ax7.set_ylabel('频次')
    ax7.set_title(f'Ridge 误差分布 (std={np.std(errors_ridge):.1f})')
    ax7.legend()
    ax7.grid(True, alpha=0.3)
    
    if has_lstm:
        ax8 = axes3[1, 1]
        ax8.hist(errors_lstm, bins=50, color='orange', alpha=0.7, edgecolor='black')
        ax8.axvline(x=0, color='k', linestyle='--', linewidth=2)
        ax8.axvline(x=np.mean(errors_lstm), color='blue', linestyle='-', linewidth=2, 
                    label=f'均值={np.mean(errors_lstm):.1f}')
        ax8.set_xlabel('预测误差 (kW)')
        ax8.set_ylabel('频次')
        ax8.set_title(f'LSTM 误差分布 (std={np.std(errors_lstm):.1f})')
        ax8.legend()
        ax8.grid(True, alpha=0.3)
    else:
        axes3[1, 1].text(0.5, 0.5, 'LSTM 数据不可用', ha='center', va='center', 
                         transform=axes3[1, 1].transAxes, fontsize=14)
        axes3[1, 1].set_title('LSTM 误差分布')
    
    plt.tight_layout()
    output_file3 = os.path.join(DATA_DIR, 'comparison_errors.png')
    plt.savefig(output_file3, dpi=150, bbox_inches='tight')
    print(f"  保存: {output_file3}")
    plt.close()
    
    # 图4: 散点图
    fig4, axes4 = plt.subplots(1, 2, figsize=(14, 6))
    
    ax9 = axes4[0]
    ax9.scatter(ridge_test['actual'], ridge_test['predicted'], alpha=0.3, s=5, c='red')
    max_val = max(ridge_test['actual'].max(), ridge_test['predicted'].max())
    ax9.plot([0, max_val], [0, max_val], 'k--', linewidth=2, label='理想线 y=x')
    ax9.set_xlabel('实际值 (kW)')
    ax9.set_ylabel('预测值 (kW)')
    ax9.set_title(f'Ridge 散点图 (R²={ridge_metrics["r2"]:.4f})')
    ax9.legend()
    ax9.grid(True, alpha=0.3)
    ax9.set_aspect('equal')
    
    if has_lstm:
        ax10 = axes4[1]
        ax10.scatter(lstm_test['actual'], lstm_test['predicted'], alpha=0.3, s=5, c='orange')
        max_val_lstm = max(lstm_test['actual'].max(), lstm_test['predicted'].max())
        ax10.plot([0, max_val_lstm], [0, max_val_lstm], 'k--', linewidth=2, label='理想线 y=x')
        ax10.set_xlabel('实际值 (kW)')
        ax10.set_ylabel('预测值 (kW)')
        ax10.set_title(f'LSTM 散点图 (R²={lstm_metrics["r2"]:.4f})')
        ax10.legend()
        ax10.grid(True, alpha=0.3)
        ax10.set_aspect('equal')
    else:
        axes4[1].text(0.5, 0.5, 'LSTM 数据不可用', ha='center', va='center', 
                      transform=axes4[1].transAxes, fontsize=14)
        axes4[1].set_title('LSTM 散点图')
    
    plt.tight_layout()
    output_file4 = os.path.join(DATA_DIR, 'comparison_scatter.png')
    plt.savefig(output_file4, dpi=150, bbox_inches='tight')
    print(f"  保存: {output_file4}")
    plt.close()
    
    print("\n" + "=" * 70)
    print("图表生成完成！")
    print("=" * 70)
    print(f"\n生成的图表文件:")
    print(f"  1. {output_file1}")
    print(f"  2. {output_file2}")
    print(f"  3. {output_file3}")
    print(f"  4. {output_file4}")


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
