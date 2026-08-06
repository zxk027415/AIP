# @AI_GENERATED
"""
TSCPipeline — 时序分类训练评估主流程。

完整流程: 加载数据 → 滑窗切分 → 预处理 → 交叉验证训练评估 → 输出指标。
输出指标格式与 split_mode_compare.py 对齐（macro_f1_mean/std, accuracy_mean/std 等）。

设计文档: .kiro/specs/pv-fault-timeseries-diagnosis/design.md §三
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import StratifiedKFold

from .data_loader import load_and_split_all_devices, preprocess_X, split_by_device
from .model_registry import get_model
from .model_wrapper import TSCModelWrapper
from .sliding_window_sampler import SamplerConfig

logger = logging.getLogger(__name__)


class TSCPipeline:
    """
    时序分类训练评估 Pipeline。

    Parameters
    ----------
    sampler_config : SamplerConfig
        滑窗切分器配置。
    model_name : str
        模型名（注册表中的 key）。
    model_params : dict, optional
        覆盖模型默认参数。
    preprocess_method : str
        预处理方法: 'per_sample_zscore' / 'per_sample_minmax' / 'none'。
    n_splits : int
        交叉验证折数。
    n_repeats : int
        重复次数（不同随机种子）。
    test_ratio : float
        按设备划分的测试集比例。
    random_state : int
        随机种子（与 RF 路线保持一致）。
    fault_oversample : bool
        是否对故障时段过采样。
    """

    def __init__(
        self,
        sampler_config: Optional[SamplerConfig] = None,
        model_name: str = "multirocket",
        model_params: Optional[Dict] = None,
        preprocess_method: str = "per_sample_zscore",
        n_splits: int = 5,
        n_repeats: int = 5,
        test_ratio: float = 0.2,
        random_state: int = 90,
        fault_oversample: bool = True,
    ):
        self.sampler_config = sampler_config or SamplerConfig()
        self.model_name = model_name
        self.model_params = model_params or {}
        self.preprocess_method = preprocess_method
        self.n_splits = n_splits
        self.n_repeats = n_repeats
        self.test_ratio = test_ratio
        self.random_state = random_state
        self.fault_oversample = fault_oversample

    def run(self, dataset_path: str) -> Dict[str, Any]:
        """
        执行完整 Pipeline。

        Parameters
        ----------
        dataset_path : str
            parquet 数据集路径。

        Returns
        -------
        dict — 指标结果（格式与 split_mode_compare.py 对齐）。
        """
        started = time.time()

        # 1. 加载 + 切分
        logger.info("加载数据: %s", dataset_path)
        X, y, meta, load_stats = load_and_split_all_devices(
            dataset_path,
            sampler_config=self.sampler_config,
            fault_oversample=self.fault_oversample,
        )

        if len(y) == 0:
            return self._empty_result("切分后无有效样本", time.time() - started)

        # 2. 预处理
        X = preprocess_X(X, method=self.preprocess_method)

        # 3. 按设备划分 train/test
        X_train, y_train, X_test, y_test, meta_train, meta_test = split_by_device(
            X, y, meta, test_ratio=self.test_ratio, random_state=self.random_state
        )

        if len(y_train) < self.n_splits:
            return self._empty_result(
                f"训练样本太少 ({len(y_train)})，不足以做 {self.n_splits}-fold CV",
                time.time() - started,
            )

        # 完整标签空间：所有指标都固定在这个集合上算 macro，避免稀有类缺席导致虚高
        all_labels = sorted(int(v) for v in np.unique(y))

        # 4. 交叉验证
        cv_results = self._cross_validate(X_train, y_train, meta_train, all_labels=all_labels)

        # 5. 最终在 holdout test set 上评估
        holdout_result = self._evaluate_holdout(
            X_train, y_train, X_test, y_test, all_labels=all_labels
        )

        elapsed = round(time.time() - started, 2)

        # 6. 汇总结果
        result = {
            "model_name": self.model_name,
            "status": "ok",
            "elapsed_sec": elapsed,
            # 与 split_mode_compare.py 对齐的指标
            "macro_f1_mean": cv_results["macro_f1_mean"],
            "macro_f1_std": cv_results["macro_f1_std"],
            "accuracy_mean": cv_results["accuracy_mean"],
            "accuracy_std": cv_results["accuracy_std"],
            "macro_precision_mean": cv_results["macro_precision_mean"],
            "macro_recall_mean": cv_results["macro_recall_mean"],
            "n_samples": int(len(y)),
            "n_classes": int(len(np.unique(y))),
            # 时序路线额外指标
            "per_class_f1": holdout_result.get("per_class_f1"),
            "confusion_matrix": holdout_result.get("confusion_matrix"),
            "train_time_sec": cv_results["train_time_sec"],
            "predict_time_sec": cv_results["predict_time_sec"],
            "window_length": self.sampler_config.window_length,
            "stride": self.sampler_config.stride,
            "n_train_samples": int(len(y_train)),
            "n_test_samples": int(len(y_test)),
            "n_discarded_windows": load_stats.get("n_samples", 0) - int(len(y)),
            "class_distribution": load_stats.get("class_distribution", {}),
            "holdout_macro_f1": holdout_result.get("macro_f1"),
            "holdout_accuracy": holdout_result.get("accuracy"),
            "holdout_macro_f1_labels_in_test_only": holdout_result.get(
                "macro_f1_labels_in_test_only"),
            "n_labels_full": holdout_result.get("n_labels_full"),
            "n_labels_in_test": holdout_result.get("n_labels_in_test"),
            "metric_note": (
                "macro 指标在完整标签空间上计算；"
                "holdout_macro_f1_labels_in_test_only 是仅按 test 出现类平均的对照值（偏高）"
            ),
            "error": None,
        }

        logger.info(
            "Pipeline 完成: model=%s, cv_f1=%.4f±%.4f, holdout_f1=%.4f, 耗时=%.1fs",
            self.model_name,
            result["macro_f1_mean"],
            result["macro_f1_std"],
            result.get("holdout_macro_f1", 0),
            elapsed,
        )

        return result

    def _cross_validate(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        meta_train,
        all_labels: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        在训练集上做分层交叉验证。

        all_labels: 完整标签空间。**必须显式传入**，否则 sklearn 的 macro 平均只在
        「该 fold 中出现的类」上计算，缺席的稀有类被静默排除，macro F1 会系统性偏高
        （实测差异可达 0.15）。
        """
        f1_scores: List[float] = []
        acc_scores: List[float] = []
        prec_scores: List[float] = []
        rec_scores: List[float] = []
        train_times: List[float] = []
        predict_times: List[float] = []

        for repeat in range(self.n_repeats):
            seed = self.random_state + repeat
            skf = StratifiedKFold(n_splits=self.n_splits, shuffle=True, random_state=seed)

            for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X_train, y_train)):
                X_tr, y_tr = X_train[train_idx], y_train[train_idx]
                X_val, y_val = X_train[val_idx], y_train[val_idx]

                # 训练
                wrapper = get_model(self.model_name, **self.model_params)
                t0 = time.time()
                wrapper.fit(X_tr, y_tr)
                train_times.append(time.time() - t0)

                # 预测
                t0 = time.time()
                preds = wrapper.predict(X_val)
                predict_times.append(time.time() - t0)

                # 指标：labels=all_labels 固定在完整标签空间上平均，保证跨 fold /
                # 跨模型可比，且不会因稀有类缺席而虚高
                f1_scores.append(f1_score(
                    y_val, preds, average="macro", labels=all_labels, zero_division=0))
                acc_scores.append(accuracy_score(y_val, preds))
                prec_scores.append(precision_score(
                    y_val, preds, average="macro", labels=all_labels, zero_division=0))
                rec_scores.append(recall_score(
                    y_val, preds, average="macro", labels=all_labels, zero_division=0))

        return {
            "macro_f1_mean": round(float(np.mean(f1_scores)), 6),
            "macro_f1_std": round(float(np.std(f1_scores)), 6),
            "accuracy_mean": round(float(np.mean(acc_scores)), 6),
            "accuracy_std": round(float(np.std(acc_scores)), 6),
            "macro_precision_mean": round(float(np.mean(prec_scores)), 6),
            "macro_recall_mean": round(float(np.mean(rec_scores)), 6),
            "train_time_sec": round(float(np.mean(train_times)), 3),
            "predict_time_sec": round(float(np.mean(predict_times)), 5),
        }

    def _evaluate_holdout(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray,
        all_labels: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        在 holdout test set 上用全训练集训练一个模型做最终评估。

        macro 指标固定在 all_labels（完整标签空间）上计算。同时额外给出
        「仅 test 中出现的类」口径，便于对照历史数字，但主指标以全类为准。
        """
        wrapper = get_model(self.model_name, **self.model_params)
        wrapper.fit(X_train, y_train)
        preds = wrapper.predict(X_test)

        labels = all_labels or sorted(
            int(v) for v in np.unique(np.concatenate([y_train, y_test]))
        )
        cm = confusion_matrix(y_test, preds, labels=labels)

        per_class = {}
        f1_per = f1_score(y_test, preds, average=None, labels=labels, zero_division=0)
        for lbl, f1_val in zip(labels, f1_per):
            per_class[int(lbl)] = round(float(f1_val), 4)

        labels_in_test = sorted(int(v) for v in np.unique(y_test))

        return {
            # 主指标：完整标签空间
            "macro_f1": round(float(f1_score(
                y_test, preds, average="macro", labels=labels, zero_division=0)), 6),
            "accuracy": round(float(accuracy_score(y_test, preds)), 6),
            # 对照口径：仅 test 中出现的类（会偏高，仅供与历史数字比对）
            "macro_f1_labels_in_test_only": round(float(f1_score(
                y_test, preds, average="macro", labels=labels_in_test, zero_division=0)), 6),
            "n_labels_full": len(labels),
            "n_labels_in_test": len(labels_in_test),
            "per_class_f1": per_class,
            "confusion_matrix": cm.tolist(),
            "confusion_matrix_labels": labels,
        }

    def _empty_result(self, error_msg: str, elapsed: float) -> Dict[str, Any]:
        """生成一个失败/空结果。"""
        return {
            "model_name": self.model_name,
            "status": "failed",
            "elapsed_sec": round(elapsed, 2),
            "macro_f1_mean": None,
            "macro_f1_std": None,
            "accuracy_mean": None,
            "accuracy_std": None,
            "macro_precision_mean": None,
            "macro_recall_mean": None,
            "n_samples": 0,
            "n_classes": 0,
            "error": error_msg,
        }
# @AI_GENERATED: end
