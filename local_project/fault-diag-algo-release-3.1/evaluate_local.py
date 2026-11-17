#!/usr/bin/env python3
"""
本地精度评估 — 直接在原始代码的特征提取结果上做分层留出评估。

由于原始代码 DataCleaner 有 pandas 版本兼容性问题（groupby apply 后 index 歧义），
我们用两种方式评估：
  A. 用原始代码 test_first_training 的同样数据流程（train_dataset.parquet，已预处理过）
  B. 用 train_small + label_small 手动处理全部 8 类数据

用法：cd fault-diag-algo-release-3.1 && python evaluate_local.py
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
    """复刻原始 smote.py 逻辑，使用 imblearn"""
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
    sm = SMOTE(sampling_strategy=strategy, k_neighbors=k, random_state=90)
    X_res, y_res = sm.fit_resample(X, y)
    return pd.DataFrame(X_res, columns=X.columns), y_res


def run_feature_extraction(data, id_fields, value_fields):
    """直接调用 FeatureEngineer（跳过 DataCleaner 的 pandas 兼容问题）"""
    from features.feature_engineer import FeatureEngineer
    fe = FeatureEngineer(id_fields, value_fields)
    fe_df = fe.transform(data)
    return fe_df, fe


def evaluate_stratified(X, y, feature_list, n_repeats=10, test_ratio=0.2, 
                        random_state=90, k_features=None, smote_limit=500):
    """分层重复留出评估，mRMR 只在 train，SMOTE 只在 train"""
    if k_features and len(feature_list) > k_features:
        feature_list = feature_list[:k_features]
    X_sel = X[feature_list]

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

        # SMOTE 只在训练折
        try:
            X_tr_sm, y_tr_sm = smote_local(X_tr, y_tr, limit=smote_limit)
        except Exception:
            X_tr_sm, y_tr_sm = X_tr, y_tr

        clf = RandomForestClassifier(n_estimators=80, random_state=90, n_jobs=-1)
        clf.fit(X_tr_sm, y_tr_sm)
        y_pred = clf.predict(X_te)
        acc_list.append(accuracy_score(y_te, y_pred))
        f1_list.append(f1_score(y_te, y_pred, average='macro', zero_division=0))
        all_y_true.extend(y_te.tolist())
        all_y_pred.extend(y_pred.tolist())

    labels_sorted = sorted(np.unique(y).tolist())
    cm = confusion_matrix(all_y_true, all_y_pred, labels=labels_sorted)
    report = classification_report(all_y_true, all_y_pred, labels=labels_sorted, zero_division=0)

    return {
        'accuracy_mean': np.mean(acc_list),
        'accuracy_std': np.std(acc_list),
        'f1_mean': np.mean(f1_list),
        'f1_std': np.std(f1_list),
        'per_repeat_f1': f1_list,
        'confusion_matrix': cm,
        'labels': labels_sorted,
        'report': report,
    }


def main():
    print("=" * 60)
    print("光伏故障诊断 release-3.1 本地精度评估")
    print("=" * 60)

    # ═══ 加载数据 ═══
    train_small = pd.read_parquet(os.path.join(DIAG_PATH, "test", "train_small.parquet"))
    label_small = pd.read_parquet(os.path.join(DIAG_PATH, "test", "label_small.parquet"))
    train_small['time'] = pd.to_datetime(train_small['time'])
    label_small['time'] = pd.to_datetime(label_small['time'])

    print(f"\n训练时序: {train_small.shape[0]} 行")
    print(f"标签数据: {label_small.shape[0]} 行")
    print(f"标签分布 (窗口级):")
    print(label_small['custom_label_id'].value_counts().sort_index().to_string())

    # ═══ 合并标签 + 时间窗口 ═══
    id_fields_merge = ['site_id', 'device_id', 'branch_id']
    label_small['label'] = label_small['custom_label_id'].astype(int)
    label_small['date'] = label_small['time'].dt.date
    train_small['date'] = train_small['time'].dt.date

    merged = train_small.merge(
        label_small[id_fields_merge + ['date', 'label']],
        on=id_fields_merge + ['date'],
        how='inner'
    ).drop_duplicates()

    # 加 time_window（简单按 date 即可，因为 diagnosis_window='1d'）
    merged['time_window'] = pd.to_datetime(merged['date'])

    print(f"\n合并后: {merged.shape[0]} 行, 8 类")
    print(f"标签分布 (行级 → 后面按 group 聚合为窗口级):")
    print(merged.groupby('label').size().to_string())

    # 统计窗口级样本数（特征提取后每组变 1 行）
    id_fields = ['site_id', 'device_id', 'branch_id', 'time_window']
    value_fields = ['i_cal', 'value']
    window_counts = merged.groupby(id_fields)['label'].max().reset_index()
    print(f"\n窗口级样本数: {len(window_counts)}")
    print(f"窗口级标签分布:")
    print(window_counts['label'].value_counts().sort_index().to_string())

    # ═══ 特征提取（跳过 DataCleaner，直接做特征工程）═══
    print("\n特征提取中（FeatureEngineer，跳过 DataCleaner 兼容性问题）...")
    # 确保数值列
    merged[value_fields] = merged[value_fields].astype(float)
    
    fe_df, fe_obj = run_feature_extraction(merged, id_fields, value_fields)
    print(f"特征矩阵: {fe_df.shape}")

    # 合并标签
    label_series = merged.groupby(id_fields)['label'].max()
    fe_df = pd.concat([fe_df, label_series], axis=1)
    fe_df = fe_df.dropna(how='any')

    X = fe_df.drop('label', axis=1)
    y = fe_df['label'].astype(int).to_numpy()
    # Reset index to avoid mRMR index alignment issues
    X = X.reset_index(drop=True)

    print(f"可用样本: {X.shape[0]} 样本 × {X.shape[1]} 特征")
    classes, counts = np.unique(y, return_counts=True)
    print(f"类别分布: {dict(zip(classes.tolist(), counts.tolist()))}")

    # ═══ mRMR 特征选择 ═══
    print("\nmRMR 特征选择 (K=50)...")
    feature_list_50 = fe_obj.select_features(X, pd.DataFrame(y, columns=['label']), K=50)
    print(f"选出 {len(feature_list_50)} 个特征")
    print(f"Top-10: {feature_list_50[:10]}")

    # ═══ 方式 A：原始代码方式（全量训练+自评）═══
    print("\n" + "=" * 60)
    print("方式 A: 全量 SMOTE + 全量训练 (原始代码做法，无 test split)")
    print("=" * 60)
    X_sel = X[feature_list_50]
    X_smote, y_smote = smote_local(X_sel, y, limit=500)
    clf = RandomForestClassifier(n_estimators=80, random_state=90, n_jobs=-1)
    clf.fit(X_smote, y_smote)
    y_pred_self = clf.predict(X_sel)
    print(f"  训练集自评 Accuracy: {accuracy_score(y, y_pred_self):.4f}")
    print(f"  训练集自评 Macro F1: {f1_score(y, y_pred_self, average='macro', zero_division=0):.4f}")
    print("  ⚠️ 严重过拟合，不代表真实泛化能力")

    # ═══ 方式 B：分层留出 K=50（原始代码特征数）═══
    print("\n" + "=" * 60)
    print("方式 B: 分层重复留出 (K=50, SMOTE limit=500, n_repeats=10)")
    print("=" * 60)
    res_b = evaluate_stratified(X, y, feature_list_50, k_features=50, smote_limit=500)
    print(f"  Accuracy: {res_b['accuracy_mean']:.4f} ± {res_b['accuracy_std']:.4f}")
    print(f"  Macro F1: {res_b['f1_mean']:.4f} ± {res_b['f1_std']:.4f}")
    print(f"  Per-repeat F1: {[round(x, 4) for x in res_b['per_repeat_f1']]}")
    print(f"\n  混淆矩阵 (行=真实, 列=预测):")
    print(f"  类别: {res_b['labels']}")
    for lbl, row in zip(res_b['labels'], res_b['confusion_matrix']):
        print(f"    label_{lbl}: {row.tolist()}")
    print(f"\n  Classification Report:\n{res_b['report']}")

    # ═══ 方式 C：分层留出 K=20（AIP 平台默认）═══
    print("\n" + "=" * 60)
    print("方式 C: 分层重复留出 (K=20, SMOTE limit=300, n_repeats=10) — AIP 平台设置")
    print("=" * 60)
    res_c = evaluate_stratified(X, y, feature_list_50, k_features=20, smote_limit=300)
    print(f"  Accuracy: {res_c['accuracy_mean']:.4f} ± {res_c['accuracy_std']:.4f}")
    print(f"  Macro F1: {res_c['f1_mean']:.4f} ± {res_c['f1_std']:.4f}")
    print(f"  Per-repeat F1: {[round(x, 4) for x in res_c['per_repeat_f1']]}")
    print(f"\n  Classification Report:\n{res_c['report']}")

    # ═══ 总结 ═══
    print("\n" + "=" * 60)
    print("总结对比")
    print("=" * 60)
    print(f"  方式 A (全量训练自评):  Acc={accuracy_score(y, y_pred_self):.4f}, F1={f1_score(y, y_pred_self, average='macro', zero_division=0):.4f} [过拟合]")
    print(f"  方式 B (K=50, 无泄漏): Acc={res_b['accuracy_mean']:.4f}±{res_b['accuracy_std']:.4f}, F1={res_b['f1_mean']:.4f}±{res_b['f1_std']:.4f}")
    print(f"  方式 C (K=20, AIP):    Acc={res_c['accuracy_mean']:.4f}±{res_c['accuracy_std']:.4f}, F1={res_c['f1_mean']:.4f}±{res_c['f1_std']:.4f}")

    print("\n如果你看到 AIP 平台上精度比这些值低很多，排查方向:")
    print("  1. AIP 平台上特征提取的输入数据是否和这里的 train_small 一致（列名、行数）")
    print("  2. AIP merge_label 的合并逻辑是否导致匹配到更少的窗口")
    print("  3. AIP handle_missing（drop_insufficient）是否丢弃了太多样本")
    print("  4. 少数类样本太少（如 label_12 只有 2 个窗口）导致 SMOTE 失败或分层不稳定")
    print("  5. mRMR 在 AIP 和本地选出的特征是否一致（取决于输入特征命名差异）")


if __name__ == "__main__":
    main()
