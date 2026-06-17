# @AI_GENERATED: Kiro v1.0
"""
分析测试集7天的气象数据，判断天气状况
"""

import pandas as pd
import numpy as np
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')
POINTS_PER_DAY = 96

def main():
    print("加载数据...")
    power_df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
    power_df['DATE_TIME'] = pd.to_datetime(power_df['DATE_TIME'], dayfirst=True)
    power_df['date'] = power_df['DATE_TIME'].dt.date
    
    weather_df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Weather_Sensor_Data.csv'))
    weather_df['DATE_TIME'] = pd.to_datetime(weather_df['DATE_TIME'], dayfirst=True)
    weather_df['date'] = weather_df['DATE_TIME'].dt.date
    weather_df['hour'] = weather_df['DATE_TIME'].dt.hour
    
    dates = power_df['date'].unique()
    test_dates = dates[-7:]
    train_dates = dates[:-7]
    
    print("\n" + "=" * 70)
    print("测试集7天气象分析")
    print("=" * 70)
    
    # 计算训练集的平均日辐照度作为基准
    train_daily_irr = []
    for d in train_dates:
        day_irr = weather_df[weather_df['date'] == d]['IRRADIATION'].sum()
        if day_irr > 0:
            train_daily_irr.append(day_irr)
    avg_train_irr = np.mean(train_daily_irr)
    print(f"\n训练集平均日辐照度总和: {avg_train_irr:.2f}")
    
    # 分析测试集每天
    print("\n测试集各天气象情况:")
    print("-" * 70)
    print(f"{'日期':<12} {'日辐照总和':<12} {'相对训练集':<12} {'最大辐照':<10} {'天气判断':<10}")
    print("-" * 70)
    
    test_weather_info = []
    for d in test_dates:
        day_weather = weather_df[weather_df['date'] == d]
        day_irr_sum = day_weather['IRRADIATION'].sum()
        day_irr_max = day_weather['IRRADIATION'].max()
        
        ratio = day_irr_sum / avg_train_irr if avg_train_irr > 0 else 0
        
        # 判断天气
        if ratio < 0.6:
            weather_type = "阴天/多云"
        elif ratio < 0.85:
            weather_type = "多云"
        else:
            weather_type = "晴天"
        
        test_weather_info.append({
            'date': d,
            'irr_sum': day_irr_sum,
            'irr_max': day_irr_max,
            'ratio': ratio,
            'weather': weather_type
        })
        
        print(f"{str(d):<12} {day_irr_sum:<12.2f} {ratio:<12.1%} {day_irr_max:<10.3f} {weather_type:<10}")
    
    # 统计
    cloudy_days = sum(1 for w in test_weather_info if '阴' in w['weather'] or '多云' in w['weather'])
    print(f"\n测试集中阴天/多云天数: {cloudy_days}/7")
    
    # 分析训练集的天气分布
    print("\n" + "=" * 70)
    print("训练集天气分布")
    print("=" * 70)
    
    train_weather_counts = {'晴天': 0, '多云': 0, '阴天/多云': 0}
    for d in train_dates:
        day_irr_sum = weather_df[weather_df['date'] == d]['IRRADIATION'].sum()
        ratio = day_irr_sum / avg_train_irr if avg_train_irr > 0 else 0
        
        if ratio < 0.6:
            train_weather_counts['阴天/多云'] += 1
        elif ratio < 0.85:
            train_weather_counts['多云'] += 1
        else:
            train_weather_counts['晴天'] += 1
    
    total_train = len(train_dates)
    for wtype, count in train_weather_counts.items():
        print(f"  {wtype}: {count}天 ({count/total_train:.1%})")
    
    # 绘制对比图
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. 测试集7天辐照度曲线
    ax1 = axes[0, 0]
    for i, d in enumerate(test_dates):
        day_weather = weather_df[weather_df['date'] == d].sort_values('DATE_TIME')
        if len(day_weather) >= POINTS_PER_DAY:
            irr = day_weather.head(POINTS_PER_DAY)['IRRADIATION'].values
            label = f"{str(d)[-5:]} ({test_weather_info[i]['weather']})"
            ax1.plot(irr, label=label, alpha=0.8)
    ax1.set_xlabel('Time Points')
    ax1.set_ylabel('Irradiation')
    ax1.set_title('Test Set: Daily Irradiation Curves')
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)
    
    # 2. 日辐照度总和对比
    ax2 = axes[0, 1]
    test_irr_sums = [w['irr_sum'] for w in test_weather_info]
    colors = ['#e74c3c' if '阴' in w['weather'] else '#f39c12' if '多云' in w['weather'] else '#2ecc71' 
              for w in test_weather_info]
    bars = ax2.bar(range(7), test_irr_sums, color=colors)
    ax2.axhline(y=avg_train_irr, color='blue', linestyle='--', label=f'Train Avg: {avg_train_irr:.1f}')
    ax2.set_xlabel('Test Day')
    ax2.set_ylabel('Daily Irradiation Sum')
    ax2.set_title('Test Set: Daily Irradiation vs Train Average')
    ax2.set_xticks(range(7))
    ax2.set_xticklabels([str(d)[-5:] for d in test_dates], rotation=45)
    ax2.legend()
    
    # 3. 训练集天气分布
    ax3 = axes[1, 0]
    weather_types = list(train_weather_counts.keys())
    weather_counts = list(train_weather_counts.values())
    colors = ['#2ecc71', '#f39c12', '#e74c3c']
    ax3.pie(weather_counts, labels=weather_types, colors=colors, autopct='%1.1f%%')
    ax3.set_title('Training Set: Weather Distribution')
    
    # 4. 建议
    ax4 = axes[1, 1]
    ax4.text(0.5, 0.9, 'Analysis Summary', fontsize=14, fontweight='bold', 
             ha='center', transform=ax4.transAxes)
    
    summary = f"""
Test Set Weather Analysis:
- Cloudy/Overcast days: {cloudy_days}/7
- Average irradiation ratio: {np.mean([w['ratio'] for w in test_weather_info]):.1%}

Training Set Weather Distribution:
- Sunny: {train_weather_counts['晴天']} days ({train_weather_counts['晴天']/total_train:.1%})
- Partly Cloudy: {train_weather_counts['多云']} days ({train_weather_counts['多云']/total_train:.1%})
- Cloudy: {train_weather_counts['阴天/多云']} days ({train_weather_counts['阴天/多云']/total_train:.1%})

Recommendation:
If test set has more cloudy days than training set,
model may overpredict power (learned sunny patterns).

Solution: Add weather condition feature (sunny/cloudy)
or use irradiation-based scaling.
"""
    ax4.text(0.1, 0.7, summary, fontsize=10, transform=ax4.transAxes, 
             verticalalignment='top', family='monospace')
    ax4.axis('off')
    
    plt.tight_layout()
    plt.savefig(os.path.join(DATA_DIR, 'test_weather_analysis.png'), dpi=150)
    print(f"\n保存: test_weather_analysis.png")
    plt.close()
    
    # 返回关键信息
    return test_weather_info, train_weather_counts


if __name__ == '__main__':
    main()
# @AI_GENERATED: end
