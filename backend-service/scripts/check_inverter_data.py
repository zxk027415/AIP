# @AI_GENERATED: Kiro v1.0
"""
检查不同逆变器的数据特征
"""

import pandas as pd
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')

df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)

print("Plant 1 逆变器数据统计:")
print("=" * 80)

for inverter in df['SOURCE_KEY'].unique():
    inv_data = df[df['SOURCE_KEY'] == inverter]['DC_POWER']
    print(f"\n逆变器: {inverter}")
    print(f"  记录数: {len(inv_data)}")
    print(f"  最小值: {inv_data.min():.2f}")
    print(f"  最大值: {inv_data.max():.2f}")
    print(f"  平均值: {inv_data.mean():.2f}")
    print(f"  非零记录数: {(inv_data > 0).sum()}")
    print(f"  零值记录数: {(inv_data == 0).sum()}")

# 检查ipynb可能使用的数据
print("\n" + "=" * 80)
print("检查ipynb可能的数据处理方式:")

# 方式1: 只用第一个逆变器
first_inv = df['SOURCE_KEY'].unique()[0]
first_data = df[df['SOURCE_KEY'] == first_inv]['DC_POWER']
print(f"\n第一个逆变器 ({first_inv}):")
print(f"  范围: {first_data.min():.0f} - {first_data.max():.0f}")

# 方式2: 所有逆变器聚合
all_data = df.groupby('DATE_TIME')['DC_POWER'].sum()
print(f"\n所有逆变器聚合:")
print(f"  范围: {all_data.min():.0f} - {all_data.max():.0f}")

# 方式3: 过滤掉零值
nonzero_data = first_data[first_data > 0]
print(f"\n第一个逆变器(去除零值):")
print(f"  范围: {nonzero_data.min():.0f} - {nonzero_data.max():.0f}")
print(f"  记录数: {len(nonzero_data)} (原{len(first_data)})")
# @AI_GENERATED: end
