#!/usr/bin/env python3
"""
合并所有有标签数据为统一训练集。

输入：相关数据/train_ori/ 下有 label 列的 CSV + enos_fault_diag/test/train_small.parquet
输出：merged_train_all.parquet（统一格式，可直接喂给 AIP 训练工作流）

统一后的列：time, site_id, device_id, branch_id, value, i_cal, label
"""
import os
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
TRAIN_ORI = os.path.join(ROOT, "相关数据", "train_ori")
OUTPUT_PATH = os.path.join(ROOT, "merged_train_all.parquet")


def load_and_normalize(filepath: str, station_name: str) -> pd.DataFrame:
    """加载单个 CSV 并统一列名格式"""
    df = pd.read_csv(filepath)

    # 去掉无用的 index 列
    if 'Unnamed: 0' in df.columns:
        df = df.drop(columns=['Unnamed: 0'])

    # 统一时间列名: data_date → time
    if 'data_date' in df.columns:
        df = df.rename(columns={'data_date': 'time'})

    # 统一 branch 列名: branch → branch_id
    if 'branch' in df.columns and 'branch_id' not in df.columns:
        df = df.rename(columns={'branch': 'branch_id'})

    # 统一 label 列: 有些文件是 label_x / label_y（两列相同，取 label_x）
    if 'label' not in df.columns:
        if 'label_x' in df.columns:
            df['label'] = df['label_x']
        elif 'label_y' in df.columns:
            df['label'] = df['label_y']

    # 只保留需要的列
    keep_cols = ['time', 'site_id', 'device_id', 'branch_id', 'value', 'i_cal', 'label']
    missing = [c for c in keep_cols if c not in df.columns]
    if missing:
        print(f"  ⚠️ {station_name} 缺少列: {missing}，跳过")
        return pd.DataFrame()

    df = df[keep_cols].copy()

    # 转换类型
    df['time'] = pd.to_datetime(df['time'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    df['i_cal'] = pd.to_numeric(df['i_cal'], errors='coerce')
    df['label'] = pd.to_numeric(df['label'], errors='coerce').astype('Int64')
    df['branch_id'] = df['branch_id'].astype(str)
    df['site_id'] = df['site_id'].astype(str)
    df['device_id'] = df['device_id'].astype(str)

    # 丢弃无标签行
    df = df.dropna(subset=['label'])
    df['label'] = df['label'].astype(int)

    return df


def main():
    print("=" * 60)
    print("合并所有有标签数据为统一训练集")
    print("=" * 60)

    all_frames = []

    # 1. 加载 train_small.parquet（原始小数据集）
    train_small_path = os.path.join(ROOT, "enos_fault_diag", "test", "train_small.parquet")
    label_small_path = os.path.join(ROOT, "enos_fault_diag", "test", "label_small.parquet")

    if os.path.exists(train_small_path) and os.path.exists(label_small_path):
        print("\n加载 train_small + label_small...")
        ts = pd.read_parquet(train_small_path)
        ls = pd.read_parquet(label_small_path)
        ts['time'] = pd.to_datetime(ts['time'])
        ls['time'] = pd.to_datetime(ls['time'])
        ls['label'] = ls['custom_label_id'].astype(int)
        ls['date'] = ls['time'].dt.date
        ts['date'] = ts['time'].dt.date

        # merge label
        id_cols = ['site_id', 'device_id', 'branch_id']
        merged_small = ts.merge(
            ls[id_cols + ['date', 'label']],
            on=id_cols + ['date'],
            how='inner'
        ).drop(columns=['date'])

        # 统一 branch_id 为 str
        merged_small['branch_id'] = merged_small['branch_id'].astype(str)
        merged_small['site_id'] = merged_small['site_id'].astype(str)
        merged_small['device_id'] = merged_small['device_id'].astype(str)

        keep = ['time', 'site_id', 'device_id', 'branch_id', 'value', 'i_cal', 'label']
        merged_small = merged_small[keep]
        all_frames.append(merged_small)
        print(f"  train_small: {len(merged_small)} 行, 标签: {sorted(merged_small['label'].unique().tolist())}")

    # 2. 加载相关数据中有标签的文件
    labeled_files = [
        ("fengning", "data_long#fengning&_&_.csv"),
        ("huarong-1008", "data_long#huarong&_&1008.csv"),
        ("wuming", "data_long#wuming&_&_.csv"),
        ("xiangyin", "data_long#xiangyin&_&_.csv"),
        ("yuncheng", "data_long#yuncheng&_&_.csv"),
        ("zhongqi", "data_long#zhongqi&_&_.csv"),
    ]

    print("\n加载相关数据有标签文件...")
    for station, filename in labeled_files:
        filepath = os.path.join(TRAIN_ORI, filename)
        if not os.path.exists(filepath):
            print(f"  ❌ {filename} 不存在，跳过")
            continue
        df = load_and_normalize(filepath, station)
        if df.empty:
            continue
        all_frames.append(df)
        labels = sorted(df['label'].unique().tolist())
        print(f"  {station:15s}: {len(df):>7d} 行, 标签: {labels}")

    # 3. 合并
    print("\n合并中...")
    combined = pd.concat(all_frames, ignore_index=True)
    combined = combined.drop_duplicates()

    print(f"\n合并后总行数: {len(combined)}")
    print(f"标签分布:")
    dist = combined.groupby('label').size().sort_index()
    for label, count in dist.items():
        print(f"  label_{label:>2d}: {count:>7d} 行")
    print(f"\n类别总数: {len(dist)}")

    # 窗口级统计
    combined['date'] = combined['time'].dt.date
    windows = combined.groupby(['site_id', 'device_id', 'branch_id', 'date'])['label'].max().reset_index()
    print(f"\n窗口级样本数（设备×日期）: {len(windows)}")
    print(f"窗口级标签分布:")
    w_dist = windows.groupby('label').size().sort_index()
    for label, count in w_dist.items():
        print(f"  label_{label:>2d}: {count:>5d} 窗口")

    # 4. 保存
    output = combined.drop(columns=['date'], errors='ignore')
    output.to_parquet(OUTPUT_PATH, index=False)
    print(f"\n✅ 已保存到: {OUTPUT_PATH}")
    print(f"   大小: {os.path.getsize(OUTPUT_PATH) / 1024 / 1024:.1f} MB")
    print(f"   可直接用于 AIP 训练工作流的 load_csv 节点")


if __name__ == "__main__":
    main()
