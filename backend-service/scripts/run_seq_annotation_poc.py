# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
scripts/run_seq_annotation_poc.py — 序列标注 PoC：训练 + 评估

目的：验证用 194 个有段边界的设备-天能否训出逐点分类模型。
判断标准：
  - train F1 > 0.9 → 数据格式没问题，模型能 overfit
  - test F1 > 0.5  → 模型学到了有用的东西
  - test F1 < 0.3  → 数据不够或模型不对

用法::

    python scripts/run_seq_annotation_poc.py
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import numpy as np

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("seq_poc")


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, labels: list) -> dict:
    """逐点 macro F1 + 每类 F1。"""
    from sklearn.metrics import f1_score, accuracy_score, classification_report

    yt = y_true.flatten()
    yp = y_pred.flatten()
    return {
        "macro_f1": float(f1_score(yt, yp, average="macro", labels=labels, zero_division=0)),
        "weighted_f1": float(f1_score(yt, yp, average="weighted", zero_division=0)),
        "accuracy": float(accuracy_score(yt, yp)),
        "per_class_report": classification_report(yt, yp, labels=labels, zero_division=0, output_dict=True),
    }


def main() -> int:
    from services.iterative_labeling.seq_annotation.data_loader import (
        load_seq_annotation_dataset,
        split_by_device,
    )
    from services.iterative_labeling.seq_annotation.unet1d import UNet1D

    # ---- 1. 加载数据 ----
    logger.info("加载序列标注数据集...")
    try:
        X, Y, meta, info = load_seq_annotation_dataset(
            min_points=60, daylight_only=True,
            include_whole_day_fault=True, max_whole_day_per_label=300,
        )
    except Exception as e:
        logger.error("加载失败: %s", e)
        return 1

    print("=" * 70)
    print("数据集信息")
    print("=" * 70)
    for k, v in info.items():
        print(f"  {k}: {v}")
    if "data_type" in meta.columns:
        print(f"\n  数据类型分布:")
        for dt, cnt in meta["data_type"].value_counts().items():
            print(f"    {dt}: {cnt} 条序列")

    # ---- 2. 划分 ----
    X_train, Y_train, X_test, Y_test, meta_train, meta_test = split_by_device(
        X, Y, meta, test_ratio=0.3, random_state=42
    )
    print(f"\n  train: {X_train.shape[0]} 序列 / test: {X_test.shape[0]} 序列")
    print(f"  train 设备数: {meta_train['device_id'].nunique()} / "
          f"test 设备数: {meta_test['device_id'].nunique()}")

    labels = info["labels"]
    n_classes = max(labels) + 1  # 标签是 0,1,3,6,7,8,11,12 不连续，用 max+1 做类别数

    # ---- 3. 归一化 ----
    # per-sample z-score（和 TSC 一致）
    mean = X_train.mean(axis=1, keepdims=True)
    std = X_train.std(axis=1, keepdims=True) + 1e-8
    X_train_n = (X_train - mean) / std

    mean_te = X_test.mean(axis=1, keepdims=True)
    std_te = X_test.std(axis=1, keepdims=True) + 1e-8
    X_test_n = (X_test - mean_te) / std_te

    # ---- 4. 转 Tensor ----
    X_tr = torch.from_numpy(X_train_n).float()
    Y_tr = torch.from_numpy(Y_train).long()
    X_te = torch.from_numpy(X_test_n).float()
    Y_te = torch.from_numpy(Y_test).long()

    train_ds = TensorDataset(X_tr, Y_tr)
    train_dl = DataLoader(train_ds, batch_size=16, shuffle=True)

    # ---- 5. 模型 ----
    model = UNet1D(in_channels=2, n_classes=n_classes, base_filters=16)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"\n  模型参数量: {n_params:,}")

    # 类别权重（处理不平衡：正常点远多于故障点）
    class_counts = np.bincount(Y_train.flatten(), minlength=n_classes).astype(float)
    class_counts[class_counts == 0] = 1  # 避免除零
    weights = 1.0 / class_counts
    weights = weights / weights.sum() * n_classes
    class_weights = torch.from_numpy(weights).float()

    criterion = nn.CrossEntropyLoss(weight=class_weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=100)

    # ---- 6. 训练 ----
    n_epochs = 150
    print(f"\n训练 {n_epochs} 轮...")
    t0 = time.time()

    for epoch in range(n_epochs):
        model.train()
        total_loss = 0
        for xb, yb in train_dl:
            logits = model(xb)  # [B, L, C]
            loss = criterion(logits.reshape(-1, n_classes), yb.reshape(-1))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        scheduler.step()

        if (epoch + 1) % 30 == 0 or epoch == 0:
            model.eval()
            with torch.no_grad():
                pred_tr = model.predict(X_tr).numpy()
                pred_te = model.predict(X_te).numpy()
            m_tr = compute_metrics(Y_train, pred_tr, labels)
            m_te = compute_metrics(Y_test, pred_te, labels)
            print(f"  epoch {epoch+1:>3}: loss={total_loss/len(train_dl):.4f}  "
                  f"train_f1={m_tr['macro_f1']:.4f}  test_f1={m_te['macro_f1']:.4f}  "
                  f"test_acc={m_te['accuracy']:.4f}")

    elapsed = time.time() - t0
    print(f"\n训练完成，耗时 {elapsed:.1f}s")

    # ---- 7. 最终评估 ----
    model.eval()
    with torch.no_grad():
        pred_train = model.predict(X_tr).numpy()
        pred_test = model.predict(X_te).numpy()

    m_train = compute_metrics(Y_train, pred_train, labels)
    m_test = compute_metrics(Y_test, pred_test, labels)

    print()
    print("=" * 70)
    print("最终结果")
    print("=" * 70)
    print(f"  Train macro F1:    {m_train['macro_f1']:.4f}")
    print(f"  Train accuracy:    {m_train['accuracy']:.4f}")
    print(f"  Test  macro F1:    {m_test['macro_f1']:.4f}")
    print(f"  Test  accuracy:    {m_test['accuracy']:.4f}")
    print(f"  Test  weighted F1: {m_test['weighted_f1']:.4f}")

    print()
    print("  逐类 test F1:")
    for lbl in labels:
        k = str(lbl)
        if k in m_test["per_class_report"]:
            r = m_test["per_class_report"][k]
            print(f"    label={lbl:>3}  f1={r['f1-score']:.3f}  "
                  f"precision={r['precision']:.3f}  recall={r['recall']:.3f}  "
                  f"support={r['support']}")

    # ---- 8. 判断 ----
    print()
    print("=" * 70)
    print("PoC 判断")
    print("=" * 70)
    if m_train["macro_f1"] > 0.9 and m_test["macro_f1"] > 0.5:
        verdict = "PASS — 方向正确，模型能学到段边界信号。需要更多数据提升泛化。"
    elif m_train["macro_f1"] > 0.9 and m_test["macro_f1"] < 0.4:
        verdict = "OVERFIT — 模型能力OK但数据太少/泛化差。需扩充数据。"
    elif m_train["macro_f1"] < 0.7:
        verdict = "FAIL — 模型连训练集都拟合不了。检查数据格式/标签质量/模型结构。"
    else:
        verdict = f"PARTIAL — train={m_train['macro_f1']:.3f} test={m_test['macro_f1']:.3f}，需进一步分析。"
    print(f"  {verdict}")

    # ---- 9. 保存结果 ----
    out_dir = _BACKEND / "data" / "seq_annotation_poc"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "dataset": info,
        "train_samples": int(X_train.shape[0]),
        "test_samples": int(X_test.shape[0]),
        "n_params": n_params,
        "n_epochs": n_epochs,
        "elapsed_sec": round(elapsed, 1),
        "train_metrics": m_train,
        "test_metrics": m_test,
        "verdict": verdict,
    }
    (out_dir / "poc_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\n结果已保存: data/seq_annotation_poc/poc_result.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
