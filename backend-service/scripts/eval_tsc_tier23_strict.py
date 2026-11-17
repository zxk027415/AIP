# @AI_GENERATED
"""
Tier 2/3 深度模型在严格口径下补测（选型定论前最后一块）。

为什么必须重测：
  v1 报告的 ResNet 0.8591 / Inception 0.7771 / CNN-LSTM 0.4464 /
  CNN-BiLSTM-Attention 0.6420 全部基于
    (a) 跨支路混合 + merge 笛卡尔积的脏数据
    (b) 只取 200 设备（462 训练窗口）
    (c) 错误的 macro F1 口径（排除 test 中缺席的稀有类）
    (d) 宽松的按设备划分（同期跨设备）
  四条全部作废。v1 得出的"深度模型因样本不足而垫底"结论**不成立**——
  那个"不足"是当时取样造成的，不是数据的硬限制。

本脚本：
  - 口径 C 三隔离（未来 N 天 × 未见过的设备），10 次划分，mean ± std
  - baseline = multirocket（当前擂主），输出逐划分配对差
  - 逐模型增量落盘，任一模型失败或超时不影响已完成结果

用法：
    conda activate cp_web
    cd backend-service
    python scripts/eval_tsc_tier23_strict.py                    # 全部 Tier2+Tier3
    python scripts/eval_tsc_tier23_strict.py --models resnet    # 只跑指定模型
    python scripts/eval_tsc_tier23_strict.py --n-repeats 5      # 减少划分次数（会带 warning）
    python scripts/eval_tsc_tier23_strict.py --epochs 30        # 深度模型训练轮数

输出：
    backend-service/data/tsc_experiments/tier23_strict/results.json
    backend-service/data/tsc_experiments/tier23_strict/progress.log
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.iterative_labeling.tsc.data_loader import preprocess_X  # noqa: E402
from services.iterative_labeling.tsc.sliding_window_sampler import (  # noqa: E402
    SamplerConfig, SlidingWindowSampler,
)
from services.iterative_labeling.tsc.tsc_strict_eval import (  # noqa: E402
    StrictEvalConfig, evaluate_model_multi_split, format_metric,
)

# 唯一能做时间切分的块（7 天全连续）。见 time_split_report.json
DATASET = _BACKEND / "datasets" / "dataset_combined.parquet"
OUT_DIR = _BACKEND / "data" / "tsc_experiments" / "tier23_strict"
BASELINE = "multirocket"

# Tier 2 走 aeon(tensorflow)，Tier 3 是自实现 torch 模型
DEEP_MODELS = ["resnet", "inception_single", "cnn_lstm", "cnn_bilstm_attention"]


def log(msg: str, path: Path) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(_PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier 2/3 严格口径补测")
    ap.add_argument("--models", nargs="*", default=None,
                    help=f"要测的模型，默认 {DEEP_MODELS}")
    ap.add_argument("--n-repeats", type=int, default=10, help="划分次数，建议 >=10")
    ap.add_argument("--n-test-days", type=int, default=3, help="末尾多少天作为 test")
    ap.add_argument("--held-device-ratio", type=float, default=0.3)
    ap.add_argument("--epochs", type=int, default=60, help="深度模型训练轮数")
    ap.add_argument("--window-length", type=int, default=288)
    ap.add_argument("--stride", type=int, default=72)
    args = ap.parse_args()

    models = args.models or DEEP_MODELS
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    plog = OUT_DIR / "progress.log"
    rpath = OUT_DIR / "results.json"
    plog.write_text("", encoding="utf-8")

    t_global = time.time()
    log(f"START Tier2/3 严格口径补测: models={models}, n_repeats={args.n_repeats}, "
        f"epochs={args.epochs}", plog)

    if not DATASET.exists():
        log(f"[ERROR] 数据集不存在: {rel(DATASET)}", plog)
        return 1

    # ---------- 数据准备（与 selection 实验完全一致，保证可比） ----------
    df = pd.read_parquet(DATASET)
    if "branch_id" not in df.columns:
        df["branch_id"] = 1
    if "site_id" not in df.columns:
        df["site_id"] = "combined"
    df["time"] = pd.to_datetime(df["time"])

    cfg = SamplerConfig(window_length=args.window_length, stride=args.stride, min_std=1e-6)
    sampler = SlidingWindowSampler(cfg)
    X, y, meta = sampler.transform_multi_device(df)
    if len(y) == 0:
        log("[ERROR] 切分后无样本", plog)
        return 1
    X = preprocess_X(X, method="per_sample_zscore")
    labels_all = sorted(int(v) for v in np.unique(y))
    log(f"数据: 窗口={len(y):,} 设备={meta['device_id'].nunique()} "
        f"序列={meta['series_id'].nunique()} 类别={labels_all}", plog)

    eval_cfg = StrictEvalConfig(
        split_mode="strict", n_repeats=args.n_repeats,
        n_test_days=args.n_test_days, held_device_ratio=args.held_device_ratio,
    )

    payload = {
        "_comment": "@AI_GENERATED",
        "experiment": "tier23_strict_backfill",
        "dataset": rel(DATASET),
        "protocol": {
            "split_mode": "strict（时间+设备双隔离）",
            "n_repeats": args.n_repeats,
            "n_test_days": args.n_test_days,
            "held_device_ratio": args.held_device_ratio,
            "window_length": args.window_length, "stride": args.stride, "min_std": 1e-6,
            "preprocess": "per_sample_zscore",
            "metric": "macro 指标固定在完整标签空间上计算",
            "deep_model_epochs": args.epochs,
        },
        "data_summary": {
            "n_windows": int(len(y)), "n_devices": int(meta["device_id"].nunique()),
            "n_series": int(meta["series_id"].nunique()), "labels": labels_all,
            "class_distribution": {int(k): int(v) for k, v in
                                   zip(*np.unique(y, return_counts=True))},
        },
        "baseline": BASELINE,
        "results": {},
        "status": "running",
    }

    def save():
        with open(rpath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    save()

    # ---------- 逐模型评估（baseline 先跑，供配对差用） ----------
    todo = [BASELINE] + [m for m in models if m != BASELINE]
    for name in todo:
        # 深度模型给 epochs；ROCKET 家族不接受该参数
        params = {}
        if name in ("resnet", "inception_single"):
            params = {"n_epochs": args.epochs, "batch_size": 32}
        elif name in ("cnn_lstm", "cnn_bilstm_attention"):
            params = {"n_epochs": args.epochs, "batch_size": 32,
                      "patience": max(5, args.epochs // 6)}

        log(f"--- {name} START (params={params}) ---", plog)
        t0 = time.time()
        try:
            r = evaluate_model_multi_split(name, X, y, meta, eval_cfg, model_params=params)
            r["elapsed_sec"] = round(time.time() - t0, 1)
            payload["results"][name] = r
            if r.get("status") == "ok":
                log(f"--- {name} DONE: macroF1={format_metric(r['macro_f1'])}  "
                    f"balAcc={format_metric(r['balanced_accuracy'])}  "
                    f"splits={r['n_splits_completed']}  {r['elapsed_sec']:.0f}s ---", plog)
            else:
                log(f"--- {name} 未完成: {r.get('error')} ---", plog)
        except Exception as e:
            payload["results"][name] = {
                "model_name": name, "status": "failed", "error": str(e)[:400],
                "elapsed_sec": round(time.time() - t0, 1),
            }
            log(f"--- {name} FAILED after {time.time() - t0:.0f}s: {str(e)[:220]} ---", plog)
            traceback.print_exc()
        save()  # 增量落盘

    # ---------- 配对差 ----------
    ok = {k: v for k, v in payload["results"].items() if v.get("status") == "ok"}
    base = ok.get(BASELINE)
    if base:
        base_by_seed = {s["seed"]: s["metrics"]["macro_f1"] for s in base["per_split"]}
        pw = {}
        for name, r in ok.items():
            if name == BASELINE:
                continue
            diffs = [s["metrics"]["macro_f1"] - base_by_seed[s["seed"]]
                     for s in r["per_split"] if s["seed"] in base_by_seed]
            if diffs:
                a = np.asarray(diffs)
                pw[name] = {
                    "vs": BASELINE,
                    "macro_f1_diff_mean": round(float(a.mean()), 4),
                    "macro_f1_diff_std": round(float(a.std()), 4),
                    "macro_f1_diff_min": round(float(a.min()), 4),
                    "macro_f1_diff_max": round(float(a.max()), 4),
                    "wins": int((a > 0).sum()), "n_paired": int(len(a)),
                }
        payload["pairwise_vs_baseline"] = pw

    ranking = sorted(ok, key=lambda k: ok[k]["macro_f1"]["mean"], reverse=True)
    payload["ranking_by_macro_f1"] = ranking
    payload["best_model"] = ranking[0] if ranking else None
    payload["elapsed_sec"] = round(time.time() - t_global, 1)
    payload["status"] = "completed"
    save()

    # ---------- 报告 ----------
    log("=" * 70, plog)
    log(f"{'模型':<24} {'macro F1':>18} {'balanced acc':>18}", plog)
    for name in ranking:
        r = ok[name]
        log(f"{name:<24} {format_metric(r['macro_f1']):>18} "
            f"{format_metric(r['balanced_accuracy']):>18}", plog)
    if payload.get("pairwise_vs_baseline"):
        log("", plog)
        log(f"逐划分配对差（相对 {BASELINE}）:", plog)
        for name, v in payload["pairwise_vs_baseline"].items():
            d, s = v["macro_f1_diff_mean"], v["macro_f1_diff_std"]
            verdict = ("显著优于" if d > s and v["wins"] >= 8
                       else "略优但不稳定" if d > 0 else "不优于")
            log(f"  {name:<24} {d:+.4f} ± {s:.4f}  胜 {v['wins']}/{v['n_paired']}"
                f"  -> {verdict} {BASELINE}", plog)
    log(f"\nBEST: {payload['best_model']}   总耗时 {payload['elapsed_sec']:.0f}s", plog)
    log(f"Saved: {rel(rpath)}", plog)
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
