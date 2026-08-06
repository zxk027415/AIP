# @AI_GENERATED
"""
多模型对比运行器 — 串行跑多个 (model, window_config) 组合，生成排名。

设计文档: .kiro/specs/pv-fault-timeseries-diagnosis/design.md §2.2.3
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .sliding_window_sampler import SamplerConfig
from .tsc_pipeline import TSCPipeline

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[3]
_EXPERIMENTS_DIR = _BACKEND / "data" / "tsc_experiments"


def run_strict_comparison(
    *,
    dataset_path: str,
    model_names: Optional[List[str]] = None,
    window_length: int = 288,
    stride: int = 72,
    min_std: float = 1e-6,
    split_mode: str = "strict",
    n_repeats: int = 10,
    n_test_days: int = 3,
    held_device_ratio: float = 0.3,
    preprocess_method: str = "per_sample_zscore",
    baseline_model: Optional[str] = "rocket_rf",
    progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    严格口径多次划分对比 —— **对外数字请用这个函数，不要用 run_model_comparison**。

    与 run_model_comparison 的区别：
      - 按 split_mode（默认 strict = 时间+设备双隔离）划分，而非单纯按设备
      - 跑 n_repeats 次不同划分，输出 mean ± std（单次划分实测 std 可达 0.075）
      - macro 指标固定在完整标签空间上算
      - 额外给出逐划分配对差（相对 baseline_model）

    设计依据见 data/tsc_experiments/expansion_and_variance_report.json。
    """
    from .data_loader import load_parquet_dataset, preprocess_X
    from .sliding_window_sampler import SamplerConfig, SlidingWindowSampler
    from .tsc_strict_eval import StrictEvalConfig, compare_models_multi_split

    if model_names is None:
        model_names = ["minirocket", "multirocket", "rocket"]
        if baseline_model and baseline_model not in model_names:
            model_names.append(baseline_model)

    experiment_id = f"tsc-strict-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    started = time.time()
    logger.info("开始严格口径对比 %s: split_mode=%s, n_repeats=%d, 模型=%s",
                experiment_id, split_mode, n_repeats, model_names)

    if progress_callback:
        progress_callback(0, len(model_names), "加载与切分数据")

    cfg = SamplerConfig(window_length=window_length, stride=stride, min_std=min_std)
    key_cols = list(cfg.series_keys)
    cols = list(dict.fromkeys(["time", "label"] + key_cols + cfg.channels))
    df = load_parquet_dataset(dataset_path, columns=cols, optional_columns=key_cols)

    sampler = SlidingWindowSampler(cfg)
    X, y, meta = sampler.transform_multi_device(df)
    if len(y) == 0:
        return {
            "experiment_id": experiment_id, "status": "failed",
            "error": "切分后无有效样本",
            "config": {"dataset_path": dataset_path, "window_length": window_length, "stride": stride},
        }
    X = preprocess_X(X, method=preprocess_method)

    eval_cfg = StrictEvalConfig(
        split_mode=split_mode, n_repeats=n_repeats,
        n_test_days=n_test_days, held_device_ratio=held_device_ratio,
    )
    if progress_callback:
        progress_callback(1, len(model_names) + 1, "多次划分评估中")

    cmp_out = compare_models_multi_split(
        model_names, X, y, meta, config=eval_cfg, baseline_model=baseline_model,
    )

    unique, counts = np.unique(y, return_counts=True)
    output = {
        "experiment_id": experiment_id,
        "evaluation": "strict_multi_split",
        "started_at": datetime.utcnow().isoformat(),
        "elapsed_sec": round(time.time() - started, 2),
        "config": {
            "dataset_path": dataset_path,
            "window_length": window_length, "stride": stride, "min_std": min_std,
            "split_mode": split_mode, "n_repeats": n_repeats,
            "n_test_days": n_test_days, "held_device_ratio": held_device_ratio,
            "preprocess_method": preprocess_method,
            "series_keys": sampler.resolve_series_keys(df),
        },
        "data_summary": {
            "n_windows": int(len(y)),
            "n_series": int(meta["series_id"].nunique()) if "series_id" in meta.columns else None,
            "n_devices": int(meta["device_id"].nunique()),
            "n_classes": int(len(unique)),
            "class_distribution": {int(k): int(v) for k, v in zip(unique, counts)},
        },
        "status": "ok",
        **cmp_out,
    }
    _save_experiment(experiment_id, output)
    logger.info("严格口径对比完成 %s: best=%s, 耗时 %.1fs",
                experiment_id, output.get("best_model"), output["elapsed_sec"])
    return output


def run_model_comparison(
    *,
    dataset_path: str,
    window_configs: Optional[List[Dict]] = None,
    model_names: Optional[List[str]] = None,
    n_repeats: int = 5,
    test_ratio: float = 0.2,
    random_state: int = 90,
    tier_filter: Optional[int] = None,
    preprocess_method: str = "per_sample_zscore",
    fault_oversample: bool = True,
    progress_callback: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    运行多模型 × 多窗口参数的全对比实验（**单次划分，仅供快速探索**）。

    ⚠️ 本函数按设备做单次划分，输出的是单个数字，**不可用于对外汇报**：
       - 单次划分实测 std 可达 0.075、极差 0.20（见方差量化报告）
       - 按设备划分是"同期跨设备"口径，train/test 共享同一时期，会高估
       对外数字请用 run_strict_comparison()（严格三隔离 + 多次划分 + mean ± std）。

    Parameters
    ----------
    dataset_path : str
        parquet 数据集路径。
    window_configs : list[dict], optional
        多组窗口参数，如 [{"window_length": 288, "stride": 72}]。默认只跑 288/72。
    model_names : list[str], optional
        要对比的模型列表。默认跑全部 Tier 1。
    n_repeats : int
        CV 重复次数。
    test_ratio : float
        设备级测试集比例。
    random_state : int
        随机种子。
    tier_filter : int, optional
        只跑指定 tier 的模型。
    preprocess_method : str
        预处理方式。
    fault_oversample : bool
        是否过采样。
    progress_callback : callable, optional
        进度回调 fn(completed: int, total: int, current_model: str)。

    Returns
    -------
    dict — 完整对比结果（含 ranking + best_model）。
    """
    from .model_registry import list_models

    # 确定模型列表
    if model_names is None:
        available = list_models(tier_filter=tier_filter, gpu_available=True)
        model_names = [m["name"] for m in available]
        if tier_filter is None:
            # 默认只跑 Tier 1（快速验证）
            model_names = [m["name"] for m in available if m["tier"] == 1]

    # 确定窗口配置列表
    if window_configs is None:
        window_configs = [{"window_length": 288, "stride": 72}]

    experiment_id = f"tsc-cmp-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    total_runs = len(model_names) * len(window_configs)
    started = time.time()
    results: List[Dict[str, Any]] = []
    completed = 0

    logger.info(
        "开始对比实验 %s: %d 模型 × %d 窗口配置 = %d 组",
        experiment_id, len(model_names), len(window_configs), total_runs,
    )

    for wc in window_configs:
        sampler_cfg = SamplerConfig(
            window_length=wc.get("window_length", 288),
            stride=wc.get("stride", 72),
        )
        for model_name in model_names:
            completed += 1
            if progress_callback:
                progress_callback(completed, total_runs, model_name)

            logger.info("[%d/%d] 模型=%s, window=%d, stride=%d",
                       completed, total_runs, model_name,
                       sampler_cfg.window_length, sampler_cfg.stride)

            try:
                pipeline = TSCPipeline(
                    sampler_config=sampler_cfg,
                    model_name=model_name,
                    preprocess_method=preprocess_method,
                    n_repeats=n_repeats,
                    test_ratio=test_ratio,
                    random_state=random_state,
                    fault_oversample=fault_oversample,
                )
                result = pipeline.run(dataset_path)
                result["window_length"] = sampler_cfg.window_length
                result["stride"] = sampler_cfg.stride
                results.append(result)
            except Exception as e:
                logger.exception("模型 %s 执行失败", model_name)
                results.append({
                    "model_name": model_name,
                    "window_length": sampler_cfg.window_length,
                    "stride": sampler_cfg.stride,
                    "status": "failed",
                    "error": str(e),
                    "macro_f1_mean": None,
                    "accuracy_mean": None,
                })

    # 生成排名
    ranking = _generate_ranking(results)

    output = {
        "experiment_id": experiment_id,
        "started_at": datetime.utcnow().isoformat(),
        "elapsed_sec": round(time.time() - started, 2),
        "config": {
            "dataset_path": dataset_path,
            "model_names": model_names,
            "window_configs": window_configs,
            "n_repeats": n_repeats,
            "test_ratio": test_ratio,
            "random_state": random_state,
            "preprocess_method": preprocess_method,
        },
        "results": results,
        "ranking": ranking,
        "best_model": ranking["by_f1"][0] if ranking["by_f1"] else None,
        "best_window_length": _best_window(results),
    }

    # 持久化
    _save_experiment(experiment_id, output)

    logger.info(
        "对比实验完成: %s, best=%s (F1=%.4f), 总耗时=%.1fs",
        experiment_id,
        output["best_model"],
        _get_best_f1(results),
        output["elapsed_sec"],
    )

    return output


def _generate_ranking(results: List[Dict]) -> Dict[str, List[str]]:
    """根据结果生成多维排名。"""
    valid = [r for r in results if r.get("status") == "ok" and r.get("macro_f1_mean") is not None]

    by_f1 = sorted(valid, key=lambda r: r["macro_f1_mean"], reverse=True)
    by_acc = sorted(valid, key=lambda r: r.get("accuracy_mean", 0), reverse=True)
    by_eff = sorted(
        valid,
        key=lambda r: (r["macro_f1_mean"] / max(r.get("train_time_sec", 1), 0.001)),
        reverse=True,
    )

    return {
        "by_f1": [f"{r['model_name']}@{r.get('window_length', '?')}" for r in by_f1],
        "by_accuracy": [f"{r['model_name']}@{r.get('window_length', '?')}" for r in by_acc],
        "by_efficiency": [f"{r['model_name']}@{r.get('window_length', '?')}" for r in by_eff],
    }


def _best_window(results: List[Dict]) -> Optional[int]:
    valid = [r for r in results if r.get("status") == "ok" and r.get("macro_f1_mean") is not None]
    if not valid:
        return None
    best = max(valid, key=lambda r: r["macro_f1_mean"])
    return best.get("window_length")


def _get_best_f1(results: List[Dict]) -> float:
    valid = [r for r in results if r.get("status") == "ok" and r.get("macro_f1_mean") is not None]
    if not valid:
        return 0.0
    return max(r["macro_f1_mean"] for r in valid)


def _save_experiment(experiment_id: str, output: Dict) -> None:
    """持久化实验结果到 data/tsc_experiments/。"""
    out_dir = _EXPERIMENTS_DIR / experiment_id
    out_dir.mkdir(parents=True, exist_ok=True)

    results_path = out_dir / "results.json"
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    logger.info("实验结果已保存: %s", results_path)
# @AI_GENERATED: end
