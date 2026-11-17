#!/usr/bin/env python3
"""
合并后数据集精度评估 — 分层重复留出，所有 13 类全部保留（含 label_9/16）。
"""
import sys
import os
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.abspath(__file__))
DIAG_PATH = os.path.join(ROOT, "enos_fault_diag")
sys.path.insert(0, DIAG_PATH)

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, f1_score, classification_report, confusion_matrix
)


def smote_local(X, y, limit=500):
    from imblearn.over_sampling import SMOTE
    classes, counts = np.unique(y, return_counts=True)
    majority_count = counts.max()
    strategy = {}
    for c, cnt in zip(classes, counts):
        if cnt < majority_count and cnt >= 2:
            strategy[c] = min(limit, majority_count)
    if not strategy:
        return X, y
    min_cnt = min(cnt for c, cnt in zip(classes, counts) if c in strategy)
    k = max(1, min(5, min_cnt - 1))
    try:
        sm = SMOTE(sampling_strategy=strategy, k_neighbors=k, random_state=90)
        X_res, y_res = sm.fit_resample(X, y)
        return pd.DataFrame(X_res, columns=X.columns), y_res
    except Exception as e:
        print(f"  SMOTE 失败: {e}，使用原始数据")
        return X, y


def main():
    print("=" * 60)
    print("合并后数据集精度评估（13 类全保留）")
    print("=" * 60)

    # 加载合并数据
    data_path = os.path.join(ROOT, "merged_train_all.parquet")
    df = pd.read_parquet(data_path)
    df['time'] = pd.to_datetime(df['time'])
    print(f"\n数据: {len(df)} 行")

    # 加 time_window（按 date）
    df['time_window'] = df['time'].dt.normalize()

    id_fields = ['site_id', 'device_id', 'branch_id', 'time_window']
    value_fields = ['i_cal', 'value']

    # 确保数值
    df[value_fields] = df[value_fields].apply(pd.to_numeric, errors='coerce')

    print(f"窗口级样本: {df.groupby(id_fields).ngroups}")
    print(f"类别: {sorted(df['label'].unique().tolist())}")

    # 特征提取
    print("\n特征提取中...")
    from features.feature_engineer import FeatureEngineer
    fe = FeatureEngineer(id_fields, value_fields)
    fe_df = fe.transform(df)

    # 合并标签
    label_series = df.groupby(id_fields)['label'].max()
    fe_df = pd.concat([fe_df, label_series], axis=1)
    fe_df = fe_df.dropna(how='any')

    X = fe_df.drop('label', axis=1).reset_index(drop=True)
    y = fe_df['label'].astype(int).to_numpy()

    print(f"特征矩阵: {X.shape[0]} 样本 × {X.shape[1]} 特征")
    classes, counts = np.unique(y, return_counts=True)
    print(f"类别分布 (窗口级):")
    for c, cnt in zip(classes, counts):
        print(f"  label_{c:>2d}: {cnt:>5d} 窗口")

    # mRMR 特征选择
    print("\nmRMR 特征选择 (K=50)...")
    feature_list = fe.select_features(X, pd.DataFrame(y, columns=['label']), K=50)
    print(f"选出 {len(feature_list)} 个特征")

    # ═══ 评估 K=50 ═══
    print("\n" + "=" * 60)
    print("方式 A: 分层重复留出 (K=50, SMOTE limit=500, n_repeats=10)")
    print("=" * 60)

    n_repeats = 10
    test_ratio = 0.2
    random_state = 90
    X_sel = X[feature_list[:50]]

    acc_list, f1_list = [], []
    all_y_true, all_y_pred = [], []

    for i in range(n_repeats):
        rng = np.random.RandomState(random_state + i)
        train_idx, test_idx = [], []
        for cls in np.unique(y):
            idx = np.where(y == cls)[0]
            rng.shuffle(idx)
            n = len(idx)
            if n < 2:
                train_idx.extend(idx.tolist())
                continue
            n_test = max(1, min(int(round(n * test_ratio)), n - 1))
            test_idx.extend(idx[:n_test].tolist())
            train_idx.extend(idx[n_test:].tolist())

        X_tr = X_sel.iloc[train_idx].reset_index(drop=True)
        y_tr = y[train_idx]
        X_te = X_sel.iloc[test_idx].reset_index(drop=True)
        y_te = y[test_idx]

        X_tr_sm, y_tr_sm = smote_local(X_tr, y_tr, limit=500)
        clf = RandomForestClassifier(n_estimators=80, random_state=90, n_jobs=-1)
        clf.fit(X_tr_sm, y_tr_sm)
        y_pred = clf.predict(X_te)
        acc_list.append(accuracy_score(y_te, y_pred))
        f1_list.append(f1_score(y_te, y_pred, average='macro', zero_division=0))
        all_y_true.extend(y_te.tolist())
        all_y_pred.extend(y_pred.tolist())

    labels_sorted = sorted(np.unique(y).tolist())
    print(f"\n  Accuracy: {np.mean(acc_list):.4f} ± {np.std(acc_list):.4f}")
    print(f"  Macro F1: {np.mean(f1_list):.4f} ± {np.std(f1_list):.4f}")
    print(f"  Per-repeat F1: {[round(x, 4) for x in f1_list]}")
    report = classification_report(all_y_true, all_y_pred, labels=labels_sorted, zero_division=0)
    print(f"\n  Classification Report:\n{report}")

    cm = confusion_matrix(all_y_true, all_y_pred, labels=labels_sorted)
    print(f"  混淆矩阵 (行=真实, 列=预测), 类别: {labels_sorted}")
    for lbl, row in zip(labels_sorted, cm):
        print(f"    label_{lbl:>2d}: {row.tolist()}")

    # ═══ 评估 K=20 (AIP 默认) ═══
    print("\n" + "=" * 60)
    print("方式 B: 分层重复留出 (K=20, SMOTE limit=300) — AIP 平台设置")
    print("=" * 60)

    X_sel_20 = X[feature_list[:20]]
    acc2, f12 = [], []
    for i in range(n_repeats):
        rng = np.random.RandomState(random_state + i)
        train_idx, test_idx = [], []
        for cls in np.unique(y):
            idx = np.where(y == cls)[0]
            rng.shuffle(idx)
            n = len(idx)
            if n < 2:
                train_idx.extend(idx.tolist())
                continue
            n_test = max(1, min(int(round(n * test_ratio)), n - 1))
            test_idx.extend(idx[:n_test].tolist())
            train_idx.extend(idx[n_test:].tolist())

        X_tr = X_sel_20.iloc[train_idx].reset_index(drop=True)
        y_tr = y[train_idx]
        X_te = X_sel_20.iloc[test_idx].reset_index(drop=True)
        y_te = y[test_idx]

        X_tr_sm, y_tr_sm = smote_local(X_tr, y_tr, limit=300)
        clf = RandomForestClassifier(n_estimators=80, random_state=90, n_jobs=-1)
        clf.fit(X_tr_sm, y_tr_sm)
        y_pred = clf.predict(X_te)
        acc2.append(accuracy_score(y_te, y_pred))
        f12.append(f1_score(y_te, y_pred, average='macro', zero_division=0))

    print(f"\n  Accuracy: {np.mean(acc2):.4f} ± {np.std(acc2):.4f}")
    print(f"  Macro F1: {np.mean(f12):.4f} ± {np.std(f12):.4f}")
    print(f"  Per-repeat F1: {[round(x, 4) for x in f12]}")

    # ═══ 总结对比 ═══
    print("\n" + "=" * 60)
    print("总结对比（合并数据 vs 原来 272 样本）")
    print("=" * 60)
    print(f"  原来 (272 样本, K=50):  F1 ≈ 0.84")
    print(f"  原来 (272 样本, K=20):  F1 ≈ 0.61")
    print(f"  合并后 ({X.shape[0]} 样本, K=50): F1 = {np.mean(f1_list):.4f}")
    print(f"  合并后 ({X.shape[0]} 样本, K=20): F1 = {np.mean(f12):.4f}")


if __name__ == "__main__":
    main()
