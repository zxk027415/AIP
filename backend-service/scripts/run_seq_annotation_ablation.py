# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
scripts/run_seq_annotation_ablation.py - 消融实验：对比 CE vs Focal Loss + WeightedSampler

跑两组实验：
  A: Baseline (CrossEntropyLoss + class_weight + 均匀采样)
  B: Improved (FocalLoss gamma=2 + WeightedRandomSampler + sample_weight)

每组跑 3 个模型（unet1d_wide / bilstm_attn / transformer）× 3 折。
输出对比表格，供汇报。

用法:
    python scripts/run_seq_annotation_ablation.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.iterative_labeling.seq_annotation.grid_align import split_mask_channel

# 在导入 torch/BLAS 前锁定单线程，避免 Windows 上 bilstm/transformer 训练死锁
# （与 reference_rolling_backtest/models.py 的同款处理保持一致）。
for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_var, "1")

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

torch.set_num_threads(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ablation")

IGNORE_INDEX = -1
# 主要故障类（排除极稀有 label=9/10/16）
PRIMARY_LABELS = [0, 1, 2, 3, 4, 6, 7, 8, 11, 12]


def compute_metrics(y_true, y_pred, labels):
    from sklearn.metrics import f1_score, accuracy_score
    yt, yp = y_true.flatten(), y_pred.flatten()
    mask = yt != IGNORE_INDEX
    yt, yp = yt[mask], yp[mask]
    return {
        "macro_f1_all": float(f1_score(yt, yp, average="macro", labels=labels, zero_division=0)),
        "macro_f1_primary": float(f1_score(yt, yp, average="macro", labels=PRIMARY_LABELS, zero_division=0)),
        "binary_f1": float(f1_score((yt != 0).astype(int), (yp != 0).astype(int), average="binary", zero_division=0)),
        "accuracy": float(accuracy_score(yt, yp)),
    }


def train_one_epoch(model, dl, criterion, optimizer, n_classes):
    model.train()
    total_loss = 0
    for xb, yb, wb in dl:
        logits = model(xb)
        loss = criterion(logits.reshape(-1, n_classes), yb.reshape(-1))
        # 如果用 sample_weight，对整个序列的 loss 做加权
        # 注意：FocalLoss 内部已经 ignore_index，这里的 wb 是序列级权重
        if wb is not None:
            # wb: [B] -> [B,1] -> broadcast to [B, L] -> flatten
            seq_len = yb.shape[1]
            w_expanded = wb.unsqueeze(1).expand(-1, seq_len).reshape(-1)
            valid = yb.reshape(-1) != IGNORE_INDEX
            if valid.any():
                loss = (loss if loss.dim() > 0 else loss.unsqueeze(0))
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total_loss += loss.item()
    return total_loss / max(len(dl), 1)


def run_one_config(
    config_name: str,
    model_name: str,
    X_all, Y_all, meta, labels, n_classes,
    use_focal: bool,
    use_weighted_sampler: bool,
    use_sample_weight: bool,
    n_splits: int = 3,
    epochs: int = 100,
    batch_size: int = 32,
    mask_channel_index: int | None = None,
) -> Dict:
    from sklearn.model_selection import GroupShuffleSplit
    from services.iterative_labeling.seq_annotation.models import get_model
    from services.iterative_labeling.seq_annotation.focal_loss import FocalLoss

    groups = meta["device_id"].values
    per_split = []

    for split_i in range(n_splits):
        seed = 42 + split_i
        gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=seed)
        tr_idx, te_idx = next(gss.split(X_all, Y_all[:, 0], groups=groups))

        X_tr_np, Y_tr_np = X_all[tr_idx], Y_all[tr_idx]
        X_te_np, Y_te_np = X_all[te_idx], Y_all[te_idx]

        # 只用原始数据做 test（排除增强）
        te_orig_mask = meta.iloc[te_idx]["is_augmented"].values == False
        X_te_np_orig = X_te_np[te_orig_mask]
        Y_te_np_orig = Y_te_np[te_orig_mask]

        # 归一化：逐序列逐通道 z-score，但跳过 is_measured 掩码通道。
        # 掩码是 0/1 语义，z-score 会让「整天全实测」的序列 std=0 而整列变 0，
        # 与部分实测的序列不可比，等于毁掉这条信息。
        def norm(a):
            mu = a.mean(axis=1, keepdims=True)
            sd = a.std(axis=1, keepdims=True) + 1e-8
            out = (a - mu) / sd
            if mask_channel_index is not None:
                out[:, :, mask_channel_index] = a[:, :, mask_channel_index]
            return out

        X_tr = torch.from_numpy(norm(X_tr_np)).float()
        Y_tr = torch.from_numpy(Y_tr_np).long()
        X_te = torch.from_numpy(norm(X_te_np_orig)).float()

        # 序列级 sample weight；只在改进组参与逐点 loss 聚合。
        if use_sample_weight:
            sw = torch.from_numpy(meta.iloc[tr_idx]["sample_weight"].values.astype(np.float32))
        else:
            sw = torch.ones(len(X_tr), dtype=torch.float32)

        # DataLoader
        dataset = TensorDataset(X_tr, Y_tr, sw)
        if use_weighted_sampler:
            # 序列级采样权重 = 该序列中间点 label 的逆频率。
            # copy() 避免把 padding 的临时归并写回 Y_tr_np。
            seq_labels = Y_tr_np[:, Y_tr_np.shape[1] // 2].copy()
            seq_labels[seq_labels < 0] = 0
            counts = np.bincount(seq_labels, minlength=n_classes).astype(float)
            counts[counts == 0] = 1
            seq_weights = 1.0 / counts[seq_labels]
            sampler = WeightedRandomSampler(seq_weights, num_samples=len(seq_weights), replacement=True)
            dl = DataLoader(dataset, batch_size=batch_size, sampler=sampler)
        else:
            dl = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        # Loss 必须返回逐点值，才能将 tier/sample_weight 真正用于反向传播。
        valid_Y = Y_tr_np[Y_tr_np != IGNORE_INDEX]
        class_counts = np.bincount(valid_Y, minlength=n_classes).astype(float)
        class_counts[class_counts == 0] = 1

        if use_focal:
            alpha = 1.0 / class_counts
            alpha = alpha / alpha.sum() * n_classes
            criterion = FocalLoss(
                alpha=torch.from_numpy(alpha).float(),
                gamma=2.0,
                ignore_index=IGNORE_INDEX,
                reduction="none",
            )
        else:
            weights = 1.0 / class_counts
            weights = weights / weights.sum() * n_classes
            criterion = nn.CrossEntropyLoss(
                weight=torch.from_numpy(weights).float(),
                ignore_index=IGNORE_INDEX,
                reduction="none",
            )

        # Model：输入通道数来自快照契约；网格版是 value/i_cal/is_measured 三通道，
        # 旧快照仍可保持两通道。
        model = get_model(
            model_name,
            in_channels=int(X_all.shape[2]),
            n_classes=n_classes,
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

        t0 = time.time()
        for epoch in range(epochs):
            model.train()
            for xb, yb, wb in dl:
                logits = model(xb)
                flat_targets = yb.reshape(-1)
                valid = flat_targets != IGNORE_INDEX
                if not valid.any():
                    continue
                point_losses = criterion(
                    logits.reshape(-1, n_classes)[valid],
                    flat_targets[valid],
                )
                if use_sample_weight:
                    point_weights = (
                        wb.unsqueeze(1).expand_as(yb).reshape(-1)[valid]
                    )
                    loss = (point_losses * point_weights).sum() / point_weights.sum().clamp_min(1e-8)
                else:
                    loss = point_losses.mean()
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            scheduler.step()
        elapsed = time.time() - t0

        # Evaluate
        model.eval()
        with torch.no_grad():
            pred_tr = model.predict(X_tr).numpy()
            pred_te = model.predict(X_te).numpy()

        m_tr = compute_metrics(Y_tr_np, pred_tr, labels)
        m_te = compute_metrics(Y_te_np_orig, pred_te, labels)

        per_split.append({
            "seed": seed,
            "train_time_sec": round(elapsed, 1),
            "train": m_tr,
            "test": m_te,
        })
        print(f"  {config_name}/{model_name} seed={seed}: "
              f"test_primary_f1={m_te['macro_f1_primary']:.4f} "
              f"binary_f1={m_te['binary_f1']:.4f} ({elapsed:.0f}s)")

    # Aggregate
    def agg(key):
        vals = [s["test"][key] for s in per_split]
        return {"mean": round(np.mean(vals), 4), "std": round(np.std(vals), 4)}

    return {
        "config": config_name,
        "model": model_name,
        "n_splits": n_splits,
        "test_macro_f1_primary": agg("macro_f1_primary"),
        "test_macro_f1_all": agg("macro_f1_all"),
        "test_binary_f1": agg("binary_f1"),
        "test_accuracy": agg("accuracy"),
        "per_split": per_split,
    }


def main() -> int:
    import argparse
    from services.iterative_labeling.seq_annotation.dataset_builder import load_current_dataset

    ap = argparse.ArgumentParser(description="序列标注实验：架构选型 / 损失消融")
    ap.add_argument(
        "--mode", type=str, default="arch_selection",
        choices=["arch_selection", "ablation"],
        help="实验模式：arch_selection=固定 CE 只比模型（默认）；ablation=CE vs Focal 对比",
    )
    ap.add_argument("--smoke", action="store_true", help="小验证：1 折 × 5 epochs，确认链路")
    ap.add_argument("--epochs", type=int, default=None, help="每折训练轮数（默认 100，smoke 5）")
    ap.add_argument("--splits", type=int, default=None, help="交叉验证折数（默认 3，smoke 1）")
    ap.add_argument("--models", type=str, default=None,
                    help="逗号分隔的模型名子集（默认全部 unet1d_wide,bilstm_attn,transformer）")
    args = ap.parse_args()

    n_splits = 1 if args.smoke else (args.splits if args.splits else 3)
    epochs = 5 if args.smoke else (args.epochs if args.epochs else 100)
    models = (["unet1d_wide", "bilstm_attn", "transformer"]
              if not args.models else [m.strip() for m in args.models.split(",") if m.strip()])

    logger.info("Loading dataset...")
    X_all, Y_all, meta, report = load_current_dataset()
    labels = [int(label) for label in report["labels"]]
    # 业务标签会跳号（如 0/1/2/3/4/6/7/8/11/12）。必须映射到连续类别索引 0..K-1，
    # 与正式 trainer/predictor 的 class_index_to_label 契约一致；否则 max(labels)+1
    # 会凭空造出 5/9/10 等不存在的类别，消融结论也就无法支撑正式默认策略。
    n_classes = len(labels)
    label_to_class_index = {label: index for index, label in enumerate(labels)}
    Y_model = np.full(Y_all.shape, IGNORE_INDEX, dtype=np.int64)
    for label, class_index in label_to_class_index.items():
        Y_model[Y_all == label] = class_index
    Y_all = Y_model
    # 网格对齐后的数据集含 is_measured 掩码通道，归一化时要跳过它。
    _, mask_channel_index = split_mask_channel(
        list(report.get("channels") or ["value", "i_cal"])
    )
    logger.info(
        "Dataset: %d seq, seq_len=%d, %d classes, channels=%s, mask_channel_index=%s",
        len(X_all), X_all.shape[1], len(labels),
        report.get("channels"), mask_channel_index,
    )

    # ---- 实验配置 ----
    if args.mode == "arch_selection":
        # 架构选型：固定 CE + 逆频率权重 + 均匀 shuffle，只变模型。
        # 这是前期消融已确认 CE 胜出后的默认模式。
        configs = [("CE_baseline", False, False, False)]
        print("\n" + "=" * 70)
        print("模式: 架构选型（固定 CE + 逆频率权重，比较模型架构）")
        print(f"模型: {models}")
        print(f"折数: {n_splits}, Epochs: {epochs}")
        print("=" * 70)
    else:
        # 损失消融：CE vs Focal+WeightedSampler，适合再确认或新数据集验证。
        configs = [
            ("A_baseline_CE", False, False, False),
            ("B_focal_weighted", True, True, True),
        ]
        print("\n" + "=" * 70)
        print("模式: 损失消融（CE vs Focal+WeightedSampler）")
        print(f"模型: {models}")
        print(f"折数: {n_splits}, Epochs: {epochs}")
        print("=" * 70)

    all_results = []
    for config_name, use_focal, use_sampler, use_sw in configs:
        print(f"\n{'='*70}")
        print(f"Config: {config_name}")
        print(f"  Focal={use_focal} WeightedSampler={use_sampler} SampleWeight={use_sw}")
        print(f"{'='*70}")
        for model_name in models:
            r = run_one_config(
                config_name, model_name, X_all, Y_all, meta, labels, n_classes,
                use_focal=use_focal,
                use_weighted_sampler=use_sampler,
                use_sample_weight=use_sw,
                n_splits=n_splits, epochs=epochs, batch_size=32,
                mask_channel_index=mask_channel_index,
            )
            all_results.append(r)

    # Summary table
    print(f"\n{'='*78}")
    if args.mode == "arch_selection":
        print("Architecture Selection Results")
    else:
        print("Ablation Results Summary")
    print(f"{'='*78}")
    print(f"{'Config':<22}{'Model':<16}{'Primary F1':>14}{'Binary F1':>12}{'Accuracy':>11}")
    for r in all_results:
        pf1 = r["test_macro_f1_primary"]
        bf1 = r["test_binary_f1"]
        acc = r["test_accuracy"]
        print(f"  {r['config']:<20}{r['model']:<16}"
              f"{pf1['mean']:.4f}+/-{pf1['std']:.4f}"
              f"{bf1['mean']:>8.4f}+/-{bf1['std']:.3f}"
              f"{acc['mean']:>8.4f}")

    # Save
    out_dir = _BACKEND / "data" / "seq_annotation_experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        "arch_selection_report.json"
        if args.mode == "arch_selection"
        else "ablation_report.json"
    )
    (out_dir / filename).write_text(
        json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"\nResults saved: data/seq_annotation_experiments/{filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
