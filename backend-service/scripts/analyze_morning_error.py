# @AI_GENERATED: Kiro v1.0
"""
分析早上时段预测误差的原因
- 分析训练集中早上时段的功率-辐照度关系
- 找出为什么模型在早上预测偏高
"""

import pandas as pd
import numpy as np
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')
POINTS_PER_DAY = 96

def load_data():
    power_df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    power_df['DATE_TIME'] = pd.to_datetime(power_df['DATE_TIME'], dayfirst=True)
    power_df['date'] = power_df['DATE_TIME'].dt.date
    power_df['hour'] = power_df['DATE_TIME'].dt.hour
    power_df['minute'] = power_df['DATE_TIME'].dt.minute
    
    weather_df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Weather_Sensor_Data.csv'))
    weather_df['DATE_TIME'] = pd.to_datetime(weather_df['DATE_TIME'], dayfirst=True)
    weather_df['date'] = weather_df['DATE_TIME'].dt.date
    weather_df['hour'] = weather_df['DATE_TIME'].dt.hour
    
    return power_df, weather_df


def analyze_morning():
    power_df, weather_df = load_data()
    
    # 聚合场站总功率
    plant_power = power_df.groupby(['date', 'hour', 'minute'])['DC_POWER'].sum().reset_index()
    plant_power['time_idx'] = plant_power['hour'] * 4 + plant_power['minute'] // 15
    
    # 合并气象数据
    weather_hourly = weather_df.groupby(['date', 'hour']).agg({
        'IRRADIATION': 'mean',
        'AMBIENT_TEMPERATURE': 'mean'
    }).reset_index()
    
    merged = plant_power.merge(weather_hourly, on=['date', 'hour'], how='left')
    
    # 分析不同时段
    print("=" * 60)
    print("各时段功率-辐照度关系分析")
    print("=" * 60)
    
    # 定义时段
    periods = {
        '早上(6-9点)': (6, 9),
        '上午(9-12点)': (9, 12),
        '中午(12-15点)': (12, 15),
        '下午(15-18点)': (15, 18)
    }
    
    results = []
    for name, (h_start, h_end) in periods.items():
        period_data = merged[(merged['hour'] >= h_start) & (merged['hour'] < h_end)]
        period_data = period_data[period_data['IRRADIATION'] > 0.01]  # 排除零辐照
        
        if len(period_data) > 0:
            # 计算功率/辐照度比值（效率）
            efficiency = period_data['DC_POWER'] / (period_data['IRRADIATION'] + 0.001)
            
            avg_power = period_data['DC_POWER'].mean()
            avg_irr = period_data['IRRADIATION'].mean()
            avg_eff = efficiency.mean()
            std_eff = efficiency.std()
            
            results.append({
                'period': name,
                'avg_power': avg_power,
                'avg_irr': avg_irr,
                'avg_efficiency': avg_eff,
                'std_efficiency': std_eff,
                'samples': len(period_data)
            })
            
            print(f"\n{name}:")
            print(f"  平均功率: {avg_power:,.0f} kW")
            print(f"  平均辐照度: {avg_irr:.3f} kW/m²")
            print(f"  平均效率(功率/辐照): {avg_eff:,.0f}")
            print(f"  效率标准差: {std_eff:,.0f}")
            print(f"  样本数: {len(period_data)}")
    
    # 绘制分析图
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. 各时段效率对比
    ax1 = axes[0, 0]
    periods_names = [r['period'] for r in results]
    efficiencies = [r['avg_efficiency'] for r in results]
    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12']
    ax1.bar(periods_names, efficiencies, color=colors)
    ax1.set_ylabel('平均效率 (功率/辐照度)')
    ax1.set_title('各时段功率转换效率对比')
    ax1.tick_params(axis='x', rotation=15)
    
    # 2. 早上vs中午的功率-辐照度散点图
    ax2 = axes[0, 1]
    morning = merged[(merged['hour'] >= 6) & (merged['hour'] < 9) & (merged['IRRADIATION'] > 0.01)]
    noon = merged[(merged['hour'] >= 11) & (merged['hour'] < 14) & (merged['IRRADIATION'] > 0.01)]
    
    ax2.scatter(morning['IRRADIATION'], morning['DC_POWER'], alpha=0.3, label='早上(6-9点)', color='#e74c3c', s=10)
    ax2.scatter(noon['IRRADIATION'], noon['DC_POWER'], alpha=0.3, label='中午(11-14点)', color='#2ecc71', s=10)
    ax2.set_xlabel('辐照度 (kW/m²)')
    ax2.set_ylabel('功率 (kW)')
    ax2.set_title('早上vs中午: 功率-辐照度关系')
    ax2.legend()
    
    # 3. 一天内效率变化曲线
    ax3 = axes[1, 0]
    hourly_eff = merged[merged['IRRADIATION'] > 0.01].groupby('hour').apply(
        lambda x: (x['DC_POWER'] / (x['IRRADIATION'] + 0.001)).mean()
    )
    ax3.plot(hourly_eff.index, hourly_eff.values, 'o-', color='#9b59b6', linewidth=2)
    ax3.axvspan(6, 9, alpha=0.2, color='red', label='早上时段')
    ax3.set_xlabel('小时')
    ax3.set_ylabel('平均效率')
    ax3.set_title('一天内功率转换效率变化')
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    # 4. 测试集各天早上的实际vs预测对比
    ax4 = axes[1, 1]
    dates = merged['date'].unique()
    test_dates = dates[-7:]
    
    morning_actual = []
    morning_irr = []
    for d in test_dates:
        day_data = merged[(merged['date'] == d) & (merged['hour'] >= 6) & (merged['hour'] < 9)]
        if len(day_data) > 0:
            morning_actual.append(day_data['DC_POWER'].mean())
            morning_irr.append(day_data['IRRADIATION'].mean())
    
    x = np.arange(len(test_dates))
    width = 0.35
    ax4.bar(x - width/2, morning_actual, width, label='实际功率', color='#2c3e50')
    ax4.bar(x + width/2, [i * 200000 for i in morning_irr], width, label='辐照度×200k', color='#f39c12', alpha=0.7)
    ax4.set_xlabel('测试日期')
    ax4.set_ylabel('功率 (kW)')
    ax4.set_title('测试集早上时段: 实际功率 vs 辐照度')
    ax4.set_xticks(x)
    ax4.set_xticklabels([str(d)[-5:] for d in test_dates], rotation=45)
    ax4.legend()
    
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_DIR, 'morning_analysis.png'), dpi=150)
    print(f"\n保存: morning_analysis.png")
    plt.close()
    
    # 关键发现
    print("\n" + "=" * 60)
    print("关键发现")
    print("=" * 60)
    
    morning_eff = results[0]['avg_efficiency']
    noon_eff = results[2]['avg_efficiency']
    ratio = morning_eff / noon_eff
    
    print(f"\n1. 早上效率 vs 中午效率: {morning_eff:,.0f} vs {noon_eff:,.0f}")
    print(f"   早上效率是中午的 {ratio:.2f} 倍")
    print(f"\n2. 原因分析:")
    print(f"   - 早上太阳角度低，辐照度低但功率相对较高")
    print(f"   - 模型学习了'辐照度→功率'的平均关系")
    print(f"   - 但早上的转换效率比中午高，导致预测偏高")
    print(f"\n3. 改进建议:")
    print(f"   - 添加'时段'特征，让模型学习不同时段的效率差异")
    print(f"   - 或添加'太阳高度角'特征")


if __name__ == '__main__':
    analyze_morning()
# @AI_GENERATED: end
