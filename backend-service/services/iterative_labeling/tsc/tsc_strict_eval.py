# @AI_GENERATED
"""
严格口径多次划分评估 —— 所有对外数字必须走这里。

为什么必须多次划分（2026-08-03 方差量化结论）：
  同一协议（口径C, window=288/stride=72）两次运行得到 macro F1 = 0.7635 与 0.6495，
  相差 0.11。10 种子实测 std=0.075、极差 0.20。**单次划分的数字不可引用。**
  详见 data/tsc_experiments/variance_quantification/results.json

三种划分口径（严格程度递增）：
  device   —— 按设备划分。train/test 共享同一时期 -> "同期跨设备"，非生产口径，会高估
  time     —— 按日期划分。test 是训练时未出现过的、时间上更晚的日期，但设备可能见过
  strict   —— 时间 + 设备双隔离。test 的日期与设备都未出现在训练中。**生产口径，应以此为准**

术语澄清（易混淆，勿删）：
  本模块服务的任务是**故障诊断（Diagnosis）**——输入一段已发生的时序，输出它属于哪一类
  故障，时间方向是回看。这里的"时间隔离"**不是** Prognosis / 故障预测（判断将来会不会坏）。
  之所以诊断任务也要隔离日期：模型上线后 predict() 的输入永远来自它没见过的新的一天，
  若 train/test 共享日期，模型可利用当天全站共享的气象条件（某时刻云层导致曲线同时下凹）
  抄近道，而该捷径在线上不存在，分数因此虚高。隔离日期是为了让 test 的"天"对模型陌生。

指标口径：
  macro 指标固定在完整标签空间上计算（labels=全集）。若不指定 labels，sklearn 只在
  test 中出现的类上平均，缺席的稀有类被静默排除，macro F1 会虚高（实测差 0.147）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

logger = logging.getLogger(__name__)

SPLIT_MODES = ("strict", "time", "device")


@dataclass
class StrictEvalConfig:
    """多次划分评估配置。"""

    split_mode: str = "strict"
    """划分口径: strict（时间+设备双隔离，推荐）/ time / device。"""

    n_repeats: int = 10
    """划分次数。<10 时标准差估计不可靠，故默认 10。"""

    test_ratio: float = 0.2
    """device 口径下测试集设备比例。"""

    held_device_ratio: float = 0.3
    """strict 口径下保留作 test 的设备比例。"""

    n_test_days: int = 3
    """time / strict 口径下作为 test 的末尾天数。"""

    base_seed: int = 0
    """随机种子基数，第 i 次划分用 base_seed + i。"""

    min_test_samples: int = 30
    """test 样本数下限，低于则跳过该次划分。"""

    require_isolation: bool = True
    """是否强制要求隔离自检通过（设备/日期/字节级重复），不通过则跳过该划分。"""


def _window_start_dates(meta: pd.DataFrame) -> np.ndarray:
    return pd.to_datetime(meta["t_start"]).dt.date.values


def _isolation_report(
    X: np.ndarray,
    meta: pd.DataFrame,
    tr: np.ndarray,
    te: np.ndarray,
    d0: np.ndarray,
) -> Dict[str, Any]:
    """
    隔离自检。

    identical_windows 检查字节级完全相同的窗口 —— 实测夜间全零窗口在不同设备间
    内容一致，会构成直接泄漏（用 SamplerConfig.min_std 可剔除）。
    """
    dev_tr = set(meta.iloc[tr]["device_id"])
    dev_te = set(meta.iloc[te]["device_id"])
    hashes = np.array([hash(X[i].tobytes()) for i in np.concatenate([tr, te])])
    h_tr = set(hashes[: len(tr)].tolist())
    identical = int(np.isin(hashes[len(tr):], list(h_tr)).sum())
    device_overlap = len(dev_tr & dev_te)
    date_overlap = len(set(d0[tr]) & set(d0[te]))
    return {
        "device_overlap": device_overlap,
        "date_overlap": date_overlap,
        "identical_windows": identical,
        "clean": bool(device_overlap == 0 and identical == 0),
    }


def _make_split(
    y: np.ndarray,
    meta: pd.DataFrame,
    d0: np.ndarray,
    cfg: StrictEvalConfig,
    seed: int,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """按配置口径生成一次 train/test 索引。"""
    devices = np.sort(pd.unique(meta["device_id"]))  # 排序保证设备顺序确定、可复现
    rng = np.random.default_rng(seed)

    if cfg.split_mode == "device":
        from sklearn.model_selection import GroupShuffleSplit
        gss = GroupShuffleSplit(n_splits=1, test_size=cfg.test_ratio, random_state=seed)
        tr, te = next(gss.split(np.zeros(len(y)), y, groups=meta["device_id"].values))
        return tr, te

    days = sorted(set(d0.tolist()))
    if len(days) < cfg.n_test_days + 1:
        logger.warning(
            "可切窗日期只有 %d 天，不足以按时间划分（需 > %d）",
            len(days), cfg.n_test_days,
        )
        return None
    cut = days[-cfg.n_test_days]
    future = d0 >= cut

    if cfg.split_mode == "time":
        return np.where(~future)[0], np.where(future)[0]

    # strict：时间 + 设备双隔离
    n_held = max(1, int(len(devices) * cfg.held_device_ratio))
    held = set(rng.choice(devices, size=n_held, replace=False).tolist())
    in_held = meta["device_id"].isin(held).values
    return np.where((~future) & (~in_held))[0], np.where(future & in_held)[0]


def _metrics(y_true: np.ndarray, y_pred: np.ndarray, labels_all: List[int]) -> Dict[str, float]:
    """全部 macro 指标固定在完整标签空间上算。"""
    return {
        "macro_f1": float(f1_score(y_true, y_pred, average="macro", labels=labels_all, zero_division=0)),
        "macro_precision": float(precision_score(y_true, y_pred, average="macro", labels=labels_all, zero_division=0)),
        "macro_recall": float(recall_score(y_true, y_pred, average="macro", labels=labels_all, zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "weighted_f1": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
    }


def _aggregate(values: List[float]) -> Dict[str, float]:
    a = np.asarray(values, dtype=float)
    if not len(a):
        return {"mean": None, "std": None, "min": None, "max": None, "n": 0}
    return {
        "mean": round(float(a.mean()), 4),
        "std": round(float(a.std()), 4),
        "min": round(float(a.min()), 4),
        "max": round(float(a.max()), 4),
        "n": int(len(a)),
    }


def evaluate_model_multi_split(
    model_name: str,
    X: np.ndarray,
    y: np.ndarray,
    meta: pd.DataFrame,
    config: Optional[StrictEvalConfig] = None,
    model_params: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    在多次划分上评估单个模型，返回 mean ± std。

    Parameters
    ----------
    X : ndarray [n_samples, window_length, n_channels]，已预处理
    y : ndarray [n_samples]
    meta : DataFrame，需含 device_id 与 t_start 列

    Returns
    -------
    dict —— 每个指标是 {mean, std, min, max, n}；另含 per_split 明细与 isolation 汇总。
    """
    from .model_registry import get_model

    cfg = config or StrictEvalConfig()
    if cfg.split_mode not in SPLIT_MODES:
        raise ValueError(f"未知 split_mode={cfg.split_mode}，可选 {SPLIT_MODES}")

    labels_all = sorted(int(v) for v in np.unique(y))
    d0 = _window_start_dates(meta)

    per_split: List[Dict[str, Any]] = []
    collected: Dict[str, List[float]] = {}
    skipped: List[Dict[str, Any]] = []

    for i in range(cfg.n_repeats):
        seed = cfg.base_seed + i
        split = _make_split(y, meta, d0, cfg, seed)
        if split is None:
            skipped.append({"seed": seed, "reason": "日期不足，无法按时间划分"})
            break  # 日期不足是数据问题，重试其他种子也没用
        tr, te = split

        if len(te) < cfg.min_test_samples or len(np.unique(y[te])) < 2:
            skipped.append({"seed": seed, "reason": f"test 样本不足 (n={len(te)}, "
                                                    f"classes={len(np.unique(y[te])) if len(te) else 0})"})
            continue

        iso = _isolation_report(X, meta, tr, te, d0)
        if cfg.require_isolation and not iso["clean"]:
            skipped.append({"seed": seed, "reason": "隔离自检未通过", "isolation": iso})
            continue

        wrapper = get_model(model_name, **(model_params or {}))
        wrapper.fit(X[tr], y[tr])
        preds = wrapper.predict(X[te])
        m = _metrics(y[te], preds, labels_all)

        for k, v in m.items():
            collected.setdefault(k, []).append(v)
        per_split.append({
            "seed": seed, "n_train": int(len(tr)), "n_test": int(len(te)),
            "test_classes": int(len(np.unique(y[te]))),
            "isolation": iso,
            "metrics": {k: round(v, 4) for k, v in m.items()},
            "train_time_sec": wrapper.train_time_sec,
        })

    result: Dict[str, Any] = {
        "model_name": model_name,
        "split_mode": cfg.split_mode,
        "n_splits_completed": len(per_split),
        "n_splits_requested": cfg.n_repeats,
        "n_labels_full": len(labels_all),
        "labels": labels_all,
        "metric_note": "macro 指标在完整标签空间上计算；数字为多次划分的 mean ± std",
    }
    for k, vals in collected.items():
        result[k] = _aggregate(vals)
    result["per_split"] = per_split
    if skipped:
        result["skipped_splits"] = skipped
    if not per_split:
        result["status"] = "failed"
        result["error"] = "没有任何划分成功完成，见 skipped_splits"
    else:
        result["status"] = "ok"
        if len(per_split) < 10:
            result["warning"] = (
                f"仅完成 {len(per_split)} 次划分（<10），标准差估计不可靠，"
                f"不应作为对外结论"
            )
    return result


def compare_models_multi_split(
    model_names: List[str],
    X: np.ndarray,
    y: np.ndarray,
    meta: pd.DataFrame,
    config: Optional[StrictEvalConfig] = None,
    baseline_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    多模型在同一批划分上对比，并给出**逐划分配对差**。

    配对差比各自的 mean ± std 更有说服力：同一划分上比较消除了划分难度的影响。
    实测例：MultiRocket vs 聚合特征基线，各自 std 约 0.07，
    但配对差 +0.1094 ± 0.0669 且 9/10 划分胜出 —— 后者才是可辩护的结论。
    """
    cfg = config or StrictEvalConfig()
    results = {}
    for name in model_names:
        try:
            results[name] = evaluate_model_multi_split(name, X, y, meta, cfg)
        except Exception as e:
            logger.exception("模型 %s 评估失败", name)
            results[name] = {"model_name": name, "status": "failed", "error": str(e)}

    ok = {k: v for k, v in results.items() if v.get("status") == "ok"}
    ranking = sorted(ok, key=lambda k: ok[k]["macro_f1"]["mean"], reverse=True)

    out: Dict[str, Any] = {
        "split_mode": cfg.split_mode,
        "n_repeats": cfg.n_repeats,
        "results": results,
        "ranking_by_macro_f1": ranking,
        "best_model": ranking[0] if ranking else None,
        "metric_note": (
            "对外引用请使用 macro_f1.mean ± macro_f1.std；"
            "不要引用单次划分数字（实测 std 可达 0.075、极差 0.20）"
        ),
    }

    # 逐划分配对差（相对基线）
    base = baseline_model if baseline_model in ok else None
    if base and len(ok) > 1:
        base_by_seed = {s["seed"]: s["metrics"]["macro_f1"] for s in ok[base]["per_split"]}
        pairwise = {}
        for name, r in ok.items():
            if name == base:
                continue
            diffs = [
                s["metrics"]["macro_f1"] - base_by_seed[s["seed"]]
                for s in r["per_split"] if s["seed"] in base_by_seed
            ]
            if diffs:
                a = np.asarray(diffs)
                pairwise[name] = {
                    "vs": base,
                    "macro_f1_diff_mean": round(float(a.mean()), 4),
                    "macro_f1_diff_std": round(float(a.std()), 4),
                    "macro_f1_diff_min": round(float(a.min()), 4),
                    "macro_f1_diff_max": round(float(a.max()), 4),
                    "wins": int((a > 0).sum()),
                    "n_paired": int(len(a)),
                }
        out["pairwise_vs_baseline"] = pairwise
    return out


def format_metric(agg: Optional[Dict[str, Any]], digits: int = 4) -> str:
    """把 {mean,std,...} 格式化成 '0.6315 ± 0.0750'，供日志/前端展示。"""
    if not agg or agg.get("mean") is None:
        return "—"
    return f"{agg['mean']:.{digits}f} ± {agg['std']:.{digits}f}"
# @AI_GENERATED: end
