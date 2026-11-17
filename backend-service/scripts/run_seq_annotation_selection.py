# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
scripts/run_seq_annotation_selection.py — 序列标注模型选型实验

对比 7 个候选模型（U-Net / TCN / BiLSTM / Transformer 等），
每个模型跑 N 个随机划分（按设备隔离），输出 mean ± std。

评估口径（参照 TSC 选型的严谨度）：
  - 按设备划分（同设备不跨 train/test）
  - 多次划分取 mean ± std（单次不可引用）
  - 逐点 macro F1（完整标签空间）+ 正常/故障二分类 F1 + 段边界 IoU
  - padding 点（Y=-1）不参与 loss 和评估

用法::

    python scripts/run_seq_annotation_selection.py --n-splits 3 --epochs 100
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("selection")

IGNORE_INDEX = -1  # padding 标签


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, labels: List[int]) -> Dict:
    """
    逐点指标。padding（-1）已在调用前剔除。

    - macro_f1: 完整标签空间上的 macro F1（缺席类计 0，不静默排除）
    - binary_f1: 正常(0) vs 故障(≠0) 的二分类 F1（业务最关心：能不能识别故障时段）
    """
    from sklearn.metrics import f1_score, accuracy_score, classification_report

    return {
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", labels=labels, zero_division=0)),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "binary_f1": float(f1_score(
            (y_true != 0).astype(int), (y_pred != 0).astype(int),
            average="binary", zero_division=0,
        )),
        "per_class": classification_report(
            y_true, y_pred, labels=labels, zero_division=0, output_dict=True
        ),
    }


def segment_iou(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    段边界 IoU：把逐点标签视为「故障 vs 正常」的二值掩码算 Jaccard。
    衡量预测的故障时段与真实故障时段的重叠程度。
    """
    t = (y_true != 0)
    p = (y_pred != 0)
    inter = np.logical_and(t, p).sum()
    union = np.logical_or(t, p).sum()
    return float(inter / union) if union > 0 else 0.0


def train_one(
    model: nn.Module, X_tr: torch.Tensor, Y_tr: torch.Tensor,
    n_classes: int, class_weights: torch.Tensor,
    epochs: int, batch_size: int = 32, lr: float = 1e-3,
) -> float:
    """训练单个模型，返回耗时（秒）。"""
    dl = DataLoader(TensorDataset(X_tr, Y_tr), batch_size=batch_size, shuffle=True)
    criterion = nn.CrossEntropyLoss(weight=class_weights, ignore_index=IGNORE_INDEX)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    t0 = time.time()
    model.train()
    for _ in range(epochs):
        for xb, yb in dl:
            logits = model(xb)
            loss = criterion(logits.reshape(-1, n_classes), yb.reshape(-1))
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
        sched.step()
    return time.time() - t0


def evaluate(model: nn.Module, X: torch.Tensor, Y: np.ndarray, labels: List[int]) -> Dict:
    """评估：剔除 padding 后算指标。"""
    model.eval()
    with torch.no_grad():
        pred = model.predict(X).numpy()

    mask = Y != IGNORE_INDEX
    yt = Y[mask]
    yp = pred[mask]

    m = compute_metrics(yt, yp, labels)
    m["segment_iou"] = segment_iou(yt, yp)
    return m


def aggregate(values: List[float]) -> Dict:
    a = np.asarray(values, dtype=float)
    return {
        "mean": round(float(a.mean()), 4),
        "std": round(float(a.std()), 4),
        "min": round(float(a.min()), 4),
        "max": round(float(a.max()), 4),
        "n": len(a),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="序列标注模型选型")
    ap.add_argument("--n-splits", type=int, default=3, help="划分次数（≥3 才有 std 意义）")
    ap.add_argument("--epochs", type=int, default=100, help="每个模型训练轮数")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--models", nargs="*", default=None, help="指定模型（默认全部）")
    ap.add_argument("--test-ratio", type=float, default=0.3)
    args = ap.parse_args()

    from services.iterative_labeling.seq_annotation.dataset_builder import load_current_dataset
    from services.iterative_labeling.seq_annotation.models import MODEL_REGISTRY, get_model, list_models
    from sklearn.model_selection import GroupShuffleSplit

    # ---- 加载数据集 ----
    logger.info("加载当前数据集...")
    X_all, Y_all, meta, report = load_current_dataset()
    labels = report["labels"]
    n_classes = max(labels) + 1
    logger.info("数据集: %d 序列, seq_len=%d, 标签=%s", len(X_all), X_all.shape[1], labels)

    print("=" * 78)
    print("序列标注模型选型实验")
    print("=" * 78)
    print(f"  数据集版本: {report['version']}")
    print(f"  序列数: {report['n_sequences']}  seq_len: {report['seq_len']}")
    print(f"  数据来源: {report['data_type_counts']}")
    print(f"  标签: {labels}")
    print(f"  划分次数: {args.n_splits}  训练轮数: {args.epochs}")

    model_names = args.models or list(MODEL_REGISTRY.keys())
    print(f"  候选模型: {model_names}")
    print()

    groups = meta["device_id"].values
    results: Dict[str, Dict] = {}

    for name in model_names:
        logger.info("=== 评估模型: %s ===", name)
        per_split = []

        for split_i in range(args.n_splits):
            seed = 42 + split_i
            gss = GroupShuffleSplit(n_splits=1, test_size=args.test_ratio, random_state=seed)
            tr_idx, te_idx = next(gss.split(X_all, Y_all[:, 0], groups=groups))

            X_tr_np, Y_tr_np = X_all[tr_idx], Y_all[tr_idx]
            X_te_np, Y_te_np = X_all[te_idx], Y_all[te_idx]

            # per-sample z-score（padding 位置为 0，不影响统计太多）
            def norm(a):
                mu = a.mean(axis=1, keepdims=True)
                sd = a.std(axis=1, keepdims=True) + 1e-8
                return (a - mu) / sd

            X_tr = torch.from_numpy(norm(X_tr_np)).float()
            Y_tr = torch.from_numpy(Y_tr_np).long()
            X_te = torch.from_numpy(norm(X_te_np)).float()

            # 类别权重（忽略 padding）
            valid = Y_tr_np[Y_tr_np != IGNORE_INDEX]
            counts = np.bincount(valid, minlength=n_classes).astype(float)
            counts[counts == 0] = 1
            w = 1.0 / counts
            w = w / w.sum() * n_classes
            class_weights = torch.from_numpy(w).float()

            try:
                model = get_model(name, in_channels=X_all.shape[2], n_classes=n_classes)
                n_params = sum(p.numel() for p in model.parameters())
                elapsed = train_one(model, X_tr, Y_tr, n_classes, class_weights,
                                    epochs=args.epochs, batch_size=args.batch_size)
                m_tr = evaluate(model, X_tr, Y_tr_np, labels)
                m_te = evaluate(model, X_te, Y_te_np, labels)

                per_split.append({
                    "seed": seed,
                    "n_train": len(tr_idx), "n_test": len(te_idx),
                    "n_params": n_params,
                    "train_time_sec": round(elapsed, 1),
                    "train": {k: v for k, v in m_tr.items() if k != "per_class"},
                    "test": {k: v for k, v in m_te.items() if k != "per_class"},
                    "test_per_class": m_te["per_class"],
                })
                print(f"  {name} seed={seed}: train_f1={m_tr['macro_f1']:.4f} "
                      f"test_f1={m_te['macro_f1']:.4f} binary_f1={m_te['binary_f1']:.4f} "
                      f"iou={m_te['segment_iou']:.4f} ({elapsed:.0f}s)")

            except Exception as e:
                logger.exception("模型 %s seed=%d 失败", name, seed)
                per_split.append({"seed": seed, "error": str(e)})

        ok_splits = [s for s in per_split if "error" not in s]
        if not ok_splits:
            results[name] = {"status": "failed", "per_split": per_split}
            continue

        results[name] = {
            "status": "ok",
            "desc": MODEL_REGISTRY[name]["desc"],
            "n_params": ok_splits[0]["n_params"],
            "n_splits": len(ok_splits),
            "train_macro_f1": aggregate([s["train"]["macro_f1"] for s in ok_splits]),
            "test_macro_f1": aggregate([s["test"]["macro_f1"] for s in ok_splits]),
            "test_binary_f1": aggregate([s["test"]["binary_f1"] for s in ok_splits]),
            "test_segment_iou": aggregate([s["test"]["segment_iou"] for s in ok_splits]),
            "test_accuracy": aggregate([s["test"]["accuracy"] for s in ok_splits]),
            "train_time_sec": aggregate([s["train_time_sec"] for s in ok_splits]),
            "per_split": per_split,
        }

    # ---- 排名 ----
    ok = {k: v for k, v in results.items() if v.get("status") == "ok"}
    ranking = sorted(ok, key=lambda k: ok[k]["test_macro_f1"]["mean"], reverse=True)

    print()
    print("=" * 78)
    print("选型结果（按 test macro F1 排名）")
    print("=" * 78)
    print(f"  {'模型':<16}{'参数量':>9}{'test macroF1':>18}{'binary F1':>14}{'段IoU':>12}{'耗时s':>8}")
    for name in ranking:
        r = ok[name]
        print(f"  {name:<16}{r['n_params']:>9,}"
              f"{r['test_macro_f1']['mean']:>10.4f}±{r['test_macro_f1']['std']:.4f}"
              f"{r['test_binary_f1']['mean']:>9.4f}±{r['test_binary_f1']['std']:.3f}"
              f"{r['test_segment_iou']['mean']:>8.4f}"
              f"{r['train_time_sec']['mean']:>8.0f}")

    print()
    print("  train macro F1（看 overfit 能力）:")
    for name in ranking:
        r = ok[name]
        print(f"    {name:<16} {r['train_macro_f1']['mean']:.4f} ± {r['train_macro_f1']['std']:.4f}")

    if ranking:
        best = ranking[0]
        print()
        print(f"  ★ 最优: {best}  —  {ok[best]['desc']}")
        print(f"     test macro F1 = {ok[best]['test_macro_f1']['mean']:.4f} "
              f"± {ok[best]['test_macro_f1']['std']:.4f}")

    # ---- 保存 ----
    out_dir = _BACKEND / "data" / "seq_annotation_experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset_version": report["version"],
        "dataset_report": report,
        "config": {
            "n_splits": args.n_splits, "epochs": args.epochs,
            "batch_size": args.batch_size, "test_ratio": args.test_ratio,
        },
        "results": results,
        "ranking": ranking,
        "best_model": ranking[0] if ranking else None,
        "metric_note": (
            "对外引用 test_macro_f1.mean ± std；binary_f1 是正常/故障二分类（业务最关心）；"
            "segment_iou 衡量预测故障时段与真实的重叠"
        ),
    }
    (out_dir / "selection_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print()
    print(f"报告已保存: data/seq_annotation_experiments/selection_report.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
