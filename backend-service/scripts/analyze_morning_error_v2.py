# @AI_GENERATED: Kiro v1.0
"""
简化版早上误差分析 - 快速分析早上时段效率差异
"""

import pandas as pd
import numpy as np
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')

def main():
    print("加载数据...")
    power_df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    power_df['DATE_TIME'] = pd.to_datetime(power_df['DATE_TIME'], dayfirst=True)
    power_df['date'] = power_df['DATE_TIME'].dt.date
    power_df['hour'] = power_df['DATE_TIME'].dt.hour
    
    weather_df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Weather_Sensor_Data.csv'))
    weather_df['DATE_TIME'] = pd.to_datetime(weather_df['DATE_TIME'], dayfirst=True)
    weather_df['date'] = weather_df['DATE_TIME'].dt.date
    weather_df['hour'] = weather_df['DATE_TIME'].dt.hour
    
    # 聚合场站总功率
    plant_power = power_df.groupby(['date', 'hour'])['DC_POWER'].sum().reset_index()
    weather_hourly = weather_df.groupby(['date', 'hour'])['IRRADIATION'].mean().reset_index()
    
    merged = plant_power.merge(weather_hourly, on=['date', 'hour'], how='left')
    merged = merged.dropna()
    
    # 计算效率 (功率/辐照度)
    merged['efficiency'] = merged['DC_POWER'] / (merged['IRRADIATION'] + 0.001)
    
    print("\n" + "=" * 60)
    print("各时段效率分析 (功率/辐照度)")
    print("=" * 60)
    
    # 按小时分析
    hourly_stats = merged[merged['IRRADIATION'] > 0.01].groupby('hour').agg({
        'DC_POWER': 'mean',
        'IRRADIATION': 'mean',
        'efficiency': ['mean', 'std']
    }).round(0)
    
    print("\n小时 | 平均功率(kW) | 平均辐照度 | 平均效率 | 效率标准差")
    print("-" * 60)
    for h in range(6, 18):
        if h in hourly_stats.index:
            power = hourly_stats.loc[h, ('DC_POWER', 'mean')]
            irr = merged[(merged['hour'] == h) & (merged['IRRADIATION'] > 0.01)]['IRRADIATION'].mean()
            eff = hourly_stats.loc[h, ('efficiency', 'mean')]
            eff_std = hourly_stats.loc[h, ('efficiency', 'std')]
            print(f"  {h:2d}  |  {power:>10,.0f}  |   {irr:.3f}    |  {eff:>8,.0f} |  {eff_std:>8,.0f}")
    
    # 时段对比
    print("\n" + "=" * 60)
    print("时段对比")
    print("=" * 60)
    
    periods = {
        '早上(6-9)': (6, 9),
        '上午(9-12)': (9, 12),
        '中午(12-15)': (12, 15),
        '下午(15-18)': (15, 18)
    }
    
    period_effs = {}
    for name, (h1, h2) in periods.items():
        data = merged[(merged['hour'] >= h1) & (merged['hour'] < h2) & (merged['IRRADIATION'] > 0.01)]
        if len(data) > 0:
            avg_eff = data['efficiency'].mean()
            period_effs[name] = avg_eff
            print(f"{name}: 平均效率 = {avg_eff:,.0f}")
    
    # 关键发现
    morning_eff = period_effs.get('早上(6-9)', 0)
    noon_eff = period_effs.get('中午(12-15)', 0)
    
    print("\n" + "=" * 60)
    print("关键发现")
    print("=" * 60)
    if noon_eff > 0:
        ratio = morning_eff / noon_eff
        print(f"\n早上效率 / 中午效率 = {ratio:.2f}")
        print(f"\n问题原因:")
        print(f"  - 早上太阳角度低，辐照度低")
        print(f"  - 但早上的功率/辐照度比值(效率)比中午{'高' if ratio > 1 else '低'}")
        print(f"  - 模型用辐照度预测功率时，使用了全天平均的转换关系")
        print(f"  - 导致早上预测{'偏高' if ratio < 1 else '偏低'}")
    
    # 绘图
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. 效率随小时变化
    ax1 = axes[0, 0]
    hours = list(range(6, 18))
    effs = [hourly_stats.loc[h, ('efficiency', 'mean')] if h in hourly_stats.index else 0 for h in hours]
    ax1.bar(hours, effs, color=['#e74c3c' if 6<=h<9 else '#3498db' for h in hours])
    ax1.set_xlabel('Hour')
    ax1.set_ylabel('Efficiency (Power/Irradiation)')
    ax1.set_title('Hourly Efficiency: Morning (red) vs Other (blue)')
    ax1.axhline(y=np.mean(effs), color='green', linestyle='--', label='Average')
    ax1.legend()
    
    # 2. 功率-辐照度散点图
    ax2 = axes[0, 1]
    morning = merged[(merged['hour'] >= 6) & (merged['hour'] < 9) & (merged['IRRADIATION'] > 0.01)]
    noon = merged[(merged['hour'] >= 11) & (merged['hour'] < 14) & (merged['IRRADIATION'] > 0.01)]
    
    ax2.scatter(morning['IRRADIATION'], morning['DC_POWER'], alpha=0.5, label='Morning(6-9)', color='#e74c3c', s=20)
    ax2.scatter(noon['IRRADIATION'], noon['DC_POWER'], alpha=0.5, label='Noon(11-14)', color='#2ecc71', s=20)
    
    # 拟合线
    if len(morning) > 0:
        z_m = np.polyfit(morning['IRRADIATION'], morning['DC_POWER'], 1)
        x_line = np.linspace(0, morning['IRRADIATION'].max(), 100)
        ax2.plot(x_line, np.polyval(z_m, x_line), 'r--', linewidth=2, label=f'Morning slope: {z_m[0]:,.0f}')
    if len(noon) > 0:
        z_n = np.polyfit(noon['IRRADIATION'], noon['DC_POWER'], 1)
        x_line = np.linspace(0, noon['IRRADIATION'].max(), 100)
        ax2.plot(x_line, np.polyval(z_n, x_line), 'g--', linewidth=2, label=f'Noon slope: {z_n[0]:,.0f}')
    
    ax2.set_xlabel('Irradiation (kW/m²)')
    ax2.set_ylabel('Power (kW)')
    ax2.set_title('Power vs Irradiation: Different Slopes')
    ax2.legend()
    
    # 3. 时段效率对比
    ax3 = axes[1, 0]
    names = list(period_effs.keys())
    values = list(period_effs.values())
    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12']
    ax3.bar(names, values, color=colors)
    ax3.set_ylabel('Average Efficiency')
    ax3.set_title('Efficiency by Time Period')
    ax3.axhline(y=np.mean(values), color='black', linestyle='--', label='Average')
    
    # 4. 建议的改进方案
    ax4 = axes[1, 1]
    ax4.text(0.5, 0.9, 'Improvement Suggestions', fontsize=14, fontweight='bold', 
             ha='center', transform=ax4.transAxes)
    suggestions = [
        '1. Add time-of-day segment feature',
        '   (morning/noon/afternoon)',
        '',
        '2. Add solar elevation angle feature',
        '   (captures sun position effect)',
        '',
        '3. Use different efficiency coefficients',
        '   for different time periods',
        '',
        '4. Add morning efficiency correction',
        '   factor in post-processing'
    ]
    ax4.text(0.1, 0.7, '\n'.join(suggestions), fontsize=11, 
             transform=ax4.transAxes, verticalalignment='top', family='monospace')
    ax4.axis('off')
    
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_DIR, 'morning_analysis.png'), dpi=150)
    print(f"\n保存: morning_analysis.png")
    plt.close()

if __name__ == '__main__':
    main()
# @AI_GENERATED: end
