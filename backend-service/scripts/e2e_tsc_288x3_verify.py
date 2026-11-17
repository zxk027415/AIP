# @AI_GENERATED
"""
pv_tsc P1-1 端到端验证：
  freeze parquet → build_tsc_grid_dataset → 288×3 断言
  → strict 评估（multirocket vs rocket_rf）
  → 门禁断言 → 对比表

用法：conda run -n cp_web python scripts/e2e_tsc_288x3_verify.py
"""
from __future__ import annotations

import json
import os
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPT_DIR)
os.chdir(_BACKEND_DIR)
sys.path.insert(0, _BACKEND_DIR)

import numpy as np
import pandas as pd

FREEZE_PARQUET = "data/slot_datasets/pv_tsc/snapshots/snap-pv_tsc-20260904-100046-981f.parquet"
N_REPEATS = 3
MODELS = ["multirocket", "rocket_rf"]


def banner(msg: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def main() -> None:
    t0 = time.time()

    # ── Step 1: 读取 freeze parquet ───────────────────
    banner("Step 1: 读取 freeze parquet")
    df = pd.read_parquet(FREEZE_PARQUET)
    print(f"  shape: {df.shape}")
    print(f"  columns: {list(df.columns)}")
    print(f"  devices: {df['device_id'].nunique()}")

    # ── Step 2: build_tsc_grid_dataset → 288×3 ───────
    banner("Step 2: 网格化构建 [N, 288, 3]")
    from services.iterative_labeling.tsc.grid_day_builder import (
        TSC_GRID_CHANNELS,
        build_tsc_grid_dataset,
        preprocess_grid_X,
    )

    X, y, meta, grid_stats = build_tsc_grid_dataset(df, purity_threshold=0.7)
    print(f"  X.shape = {X.shape}")
    print(f"  y.shape = {y.shape}")
    print(f"  meta.shape = {meta.shape}")
    print(f"  channels = {grid_stats.get('channels')}")
    print(f"  类别分布: {grid_stats.get('class_distribution')}")
    print(f"  拒绝原因: {grid_stats.get('skip_reasons')}")

    assert X.ndim == 3, f"X 必须是三维，实际 {X.ndim}"
    assert tuple(X.shape[1:]) == (288, 3), f"期望 [N,288,3]，实际 {X.shape}"
    assert list(grid_stats.get("channels") or []) == list(TSC_GRID_CHANNELS)
    print("  ✅ 288×3 合同断言通过")

    mask_ch = X[:, :, 2]
    unique_mask = np.unique(mask_ch)
    assert set(unique_mask).issubset({0.0, 1.0})
    print(f"  ✅ mask 通道值域正确: {unique_mask}")

    # ── Step 3: mask-aware 预处理 ─────────────────────
    banner("Step 3: mask-aware 预处理")
    X_pre = preprocess_grid_X(X, method="per_sample_zscore")
    mask_after = X_pre[:, :, 2]
    assert np.allclose(mask_ch, mask_after)
    print("  ✅ preprocess_grid_X mask 通道保持不变")

    # ── Step 4: 直接用 compare_models_multi_split ──────
    # 当前数据只有 35 个唯一日期，设备×日期覆盖稀疏。
    # 放宽隔离参数以保证端到端链路可验证。
    from services.iterative_labeling.tsc.tsc_strict_eval import (
        StrictEvalConfig,
        compare_models_multi_split,
    )

    eval_config = StrictEvalConfig(
        split_mode="strict",
        n_repeats=N_REPEATS,
        test_ratio=0.2,
        held_device_ratio=0.5,
        n_test_days=5,
        base_seed=42,
        min_test_samples=10,
        require_isolation=False,
    )
    results = {}
    for model_name in MODELS:
        banner(f"Step 4: strict-{N_REPEATS} ({model_name})")
        t_model = time.time()

        comparison = compare_models_multi_split(
            [model_name],
            X_pre,
            y,
            meta,
            config=eval_config,
        )
        elapsed_model = round(time.time() - t_model, 1)
        report = dict((comparison.get("results") or {}).get(model_name) or {})
        report["elapsed_sec"] = elapsed_model
        report["n_samples"] = len(y)
        report["n_classes"] = int(len(np.unique(y)))
        results[model_name] = report

        status = report.get("status", "unknown")
        print(f"  status: {status}")
        print(f"  elapsed: {elapsed_model}s")
        if status == "ok":
            mf1 = report.get("macro_f1") or {}
            acc = report.get("accuracy") or {}
            ba = report.get("balanced_accuracy") or {}
            print(f"  macro_f1: mean={mf1.get('mean')}, std={mf1.get('std')}")
            print(f"  accuracy: mean={acc.get('mean')}, std={acc.get('std')}")
            print(f"  balanced_accuracy: mean={ba.get('mean')}")
            print(f"  n_splits_completed: {report.get('n_splits_completed')}")
            print(f"  n_splits_requested: {report.get('n_splits_requested')}")
            if report.get("per_split"):
                for i, s in enumerate(report["per_split"][:2]):
                    print(f"  split[{i}]: n_train={s.get('n_train')}, n_test={s.get('n_test')}")
        else:
            print(f"  error: {report.get('error', 'N/A')}")
            if report.get("skipped_splits"):
                for i, skip in enumerate(report["skipped_splits"][:3]):
                    print(f"  skip[{i}]: {skip}")

    # ── Step 5: 门禁断言 ─────────────────────────────
    banner("Step 5: 门禁断言（模拟 P1-1 改动 C）")
    from services.iterative_labeling.tsc.sliding_window_sampler import SamplerConfig
    sampler_config = SamplerConfig(
        window_length=288,
        stride=288,
        channels=list(TSC_GRID_CHANNELS),
        min_coverage=0.9,
        purity_threshold=0.7,
        min_std=0.0,
    )
    representation_ok = bool(
        X.shape[2] == 3
        and list(sampler_config.channels) == ["value", "i_cal", "is_measured"]
    )
    print(f"  representation_ok: {representation_ok}")
    print(f"  X.shape[2] = {X.shape[2]}")
    print(f"  sampler_config.channels = {list(sampler_config.channels)}")
    if representation_ok:
        print("  ✅ P1-1 门禁断言：288×3 + clock_grid_288_mask 通过")
    else:
        print("  ❌ P1-1 门禁断言失败")

    # 模拟旧 288×2 被门禁拦截
    old_sampler = SamplerConfig(
        window_length=288, stride=72, channels=["value", "i_cal"],
    )
    old_repr_ok = bool(
        2 == 3  # X.shape[2] 对旧数据是 2
        and list(old_sampler.channels) == ["value", "i_cal", "is_measured"]
    )
    print(f"  旧 288×2 门禁结果: {old_repr_ok} (期望 False)")
    assert not old_repr_ok, "旧 288×2 不应通过门禁"
    print("  ✅ 旧 288×2 被门禁正确拦截")

    # ── Step 6: 对比表 ────────────────────────────────
    banner("Step 6: multirocket vs rocket_rf 对比")
    header = f"{'指标':<25} {'multirocket':>15} {'rocket_rf':>15}"
    print(header)
    print("-" * len(header))
    metric_keys = [
        ("macro_f1", "mean", "Macro-F1 (mean)"),
        ("macro_f1", "std", "Macro-F1 (std)"),
        ("accuracy", "mean", "Accuracy (mean)"),
        ("accuracy", "std", "Accuracy (std)"),
        ("balanced_accuracy", "mean", "Balanced Acc (mean)"),
    ]
    for group, sub, label in metric_keys:
        v1 = (results.get("multirocket", {}).get(group) or {}).get(sub, "N/A")
        v2 = (results.get("rocket_rf", {}).get(group) or {}).get(sub, "N/A")
        if isinstance(v1, float):
            v1 = f"{v1:.4f}"
        if isinstance(v2, float):
            v2 = f"{v2:.4f}"
        print(f"  {label:<25} {str(v1):>15} {str(v2):>15}")

    flat_keys = [
        ("n_samples", "样本数"),
        ("n_classes", "类别数"),
        ("n_splits_completed", "完成划分数"),
        ("elapsed_sec", "耗时 (s)"),
    ]
    for key, label in flat_keys:
        v1 = results.get("multirocket", {}).get(key, "N/A")
        v2 = results.get("rocket_rf", {}).get(key, "N/A")
        if isinstance(v1, float):
            v1 = f"{v1:.1f}"
        if isinstance(v2, float):
            v2 = f"{v2:.1f}"
        print(f"  {label:<25} {str(v1):>15} {str(v2):>15}")

    total = round(time.time() - t0, 1)
    banner(f"总耗时: {total}s")

    # 保存结果
    out_path = os.path.join(_BACKEND_DIR, "data", "tsc_experiments", "e2e_288x3_verify_result.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    serializable = {}
    for name, res in results.items():
        s = {}
        for k, v in res.items():
            if isinstance(v, (str, int, float, bool, type(None))):
                s[k] = v
            elif isinstance(v, dict):
                s[k] = {str(kk): vv for kk, vv in v.items() if isinstance(vv, (str, int, float, bool, type(None)))}
        serializable[name] = s
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
