# @AI_GENERATED: Kiro v1.0
"""
检查测试集前200点的数据特征
"""

import pandas as pd
import numpy as np
import os
from sklearn.preprocessing import MinMaxScaler

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')
SEQ_LENGTH = 24

# 加载数据
df = pd.read_csv(os.path.join(DATA_DIR, 'Plant_1_Generation_Data.csv'))
df['DATE_TIME'] = pd.to_datetime(df['DATE_TIME'], dayfirst=True)
df = df.sort_values('DATE_TIME')

# 第一个逆变器
first_inv = df['SOURCE_KEY'].unique()[0]
df_single = df[df['SOURCE_KEY'] == first_inv].copy()
df_single = df_single.sort_values('DATE_TIME').reset_index(drop=True)

# 特征缩放
data = df_single[['DC_POWER']].values
scaler = MinMaxScaler(feature_range=(0, 1))
scaled_data = scaler.fit_transform(data)

# 创建序列
def create_sequences(data, seq_length):
    x, y = [], []
    for i in range(len(data) - seq_length):
        x.append(data[i:(i + seq_length)])
        y.append(data[i + seq_length])
    return np.array(x), np.array(y)

X, y = create_sequences(scaled_data, SEQ_LENGTH)

# 80/20划分
split = int(len(X) * 0.8)
y_test = y[split:]

# 反归一化
actual_values = scaler.inverse_transform(y_test)

# 获取时间戳
timestamps = df_single['DATE_TIME'].values[SEQ_LENGTH:]
test_timestamps = timestamps[split:]

print("测试集前200点数据分析:")
print("=" * 60)
print(f"时间范围: {pd.Timestamp(test_timestamps[0])} 到 {pd.Timestamp(test_timestamps[199])}")
print(f"\n实际值统计:")
print(f"  最小值: {actual_values[:200].min():.2f}")
print(f"  最大值: {actual_values[:200].max():.2f}")
print(f"  平均值: {actual_values[:200].mean():.2f}")
print(f"  零值数量: {(actual_values[:200] == 0).sum()}")

print(f"\n前20个值:")
for i in range(20):
    ts = pd.Timestamp(test_timestamps[i])
    val = actual_values[i][0]
    print(f"  {ts}: {val:.2f} kW")
# @AI_GENERATED: end
