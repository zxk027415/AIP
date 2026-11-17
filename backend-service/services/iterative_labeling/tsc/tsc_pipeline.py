# @AI_GENERATED
"""TSC 时序分类训练评估主流程。

``legacy`` 口径仅保留给历史实验；平台训练和累计重训必须显式使用 ``strict``，
执行日期、设备、重复窗口三类隔离，多次划分全部通过后才产出可治理模型工件。
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
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

from .data_loader import load_tsc_samples, preprocess_X, split_by_device
from .model_registry import get_model
from .sliding_window_sampler import SamplerConfig

logger = logging.getLogger(__name__)


class TSCPipeline:
    """MultiRocket 训练器，同时提供历史 CV 与生产 strict 两种明确口径。"""

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
        evaluation: str = "legacy",
        split_mode: str = "strict",
        n_test_days: int = 3,
        held_device_ratio: float = 0.3,
        min_test_samples: int = 30,
        baseline_model: Optional[str] = None,
        require_production_contract: bool = True,
    ) -> None:
        self.sampler_config = sampler_config or SamplerConfig()
        self.model_name = model_name
        self.model_params = model_params or {}
        self.preprocess_method = preprocess_method
        self.n_splits = int(n_splits)
        self.n_repeats = int(n_repeats)
        self.test_ratio = float(test_ratio)
        self.random_state = int(random_state)
        self.fault_oversample = bool(fault_oversample)
        self.evaluation = str(evaluation or "legacy").strip().lower()
        self.split_mode = str(split_mode or "strict").strip().lower()
        self.n_test_days = int(n_test_days)
        self.held_device_ratio = float(held_device_ratio)
        self.min_test_samples = int(min_test_samples)
        self.baseline_model = str(baseline_model or "").strip() or None
        self.require_production_contract = bool(require_production_contract)

    def run(self, dataset_path: str) -> Dict[str, Any]:
        """从原始 CSV/Parquet 或冻结 NPZ 训练，并返回同一套扁平指标字段。"""
        started = time.time()
        logger.info("加载 TSC 数据: %s", dataset_path)
        try:
            X, y, meta, load_stats, preprocessed = load_tsc_samples(
                dataset_path,
                sampler_config=self.sampler_config,
                fault_oversample=self.fault_oversample,
            )
        except Exception as exc:  # 训练入口统一返回结构化失败，便于工作流展示
            logger.exception("TSC 数据加载失败")
            return self._empty_result(f"数据加载失败: {exc}", time.time() - started)

        result = self.run_samples(X, y, meta, load_stats, preprocessed)
        result["elapsed_sec"] = round(time.time() - started, 2)
        return result

    def run_samples(
        self,
        X: np.ndarray,
        y: np.ndarray,
        meta,
        load_stats: Dict[str, Any],
        preprocessed: bool,
    ) -> Dict[str, Any]:
        """训练内存窗口样本，供路径入口和工作流算子共享同一评估契约。"""
        started = time.time()
        try:
            values = np.asarray(X, dtype=np.float32)
            labels = np.asarray(y).reshape(-1)
        except Exception as exc:
            return self._empty_result(f"TSC 样本无法转换为数组: {exc}", time.time() - started)
        if values.ndim != 3:
            return self._empty_result(
                f"TSC X 必须是三维 [n_samples, window_length, n_channels]，当前 shape={values.shape}",
                time.time() - started,
            )
        if len(values) != len(labels):
            return self._empty_result(
                f"TSC 样本数不一致: X={len(values)}, y={len(labels)}",
                time.time() - started,
            )
        if not hasattr(meta, "columns") or len(meta) != len(labels):
            return self._empty_result(
                f"TSC meta 必须是与 y 等长的 DataFrame: meta={len(meta) if hasattr(meta, '__len__') else 'invalid'}, y={len(labels)}",
                time.time() - started,
            )
        required_meta = {"device_id", "t_start"} if self.evaluation == "strict" else {"device_id"}
        missing_meta = sorted(required_meta - set(meta.columns))
        if missing_meta:
            return self._empty_result(
                f"TSC meta 缺少评估字段: {missing_meta}",
                time.time() - started,
            )
        if len(labels) == 0:
            return self._empty_result("切分后无有效样本", time.time() - started)
        if len(np.unique(labels)) < 2:
            return self._empty_result("TSC 训练至少需要两个标签类别", time.time() - started)
        if not bool(preprocessed):
            values = preprocess_X(values, method=self.preprocess_method)

        stats = load_stats if isinstance(load_stats, dict) else {}
        if self.evaluation == "strict":
            return self._run_strict(values, labels, meta, stats, started)
        if self.evaluation != "legacy":
            return self._empty_result(
                f"未知 evaluation={self.evaluation!r}，仅支持 strict/legacy",
                time.time() - started,
            )
        return self._run_legacy(values, labels, meta, stats, started)

    def _run_strict(
        self,
        X: np.ndarray,
        y: np.ndarray,
        meta,
        load_stats: Dict[str, Any],
        started: float,
    ) -> Dict[str, Any]:
        """执行生产 strict 多次划分；证据不完整时不保存模型。"""
        from .tsc_strict_eval import StrictEvalConfig, compare_models_multi_split

        eval_config = StrictEvalConfig(
            split_mode=self.split_mode,
            n_repeats=self.n_repeats,
            test_ratio=self.test_ratio,
            held_device_ratio=self.held_device_ratio,
            n_test_days=self.n_test_days,
            base_seed=self.random_state,
            min_test_samples=self.min_test_samples,
            require_isolation=True,
        )
        model_names = [self.model_name]
        if self.baseline_model and self.baseline_model != self.model_name:
            model_names.append(self.baseline_model)
        comparison = compare_models_multi_split(
            model_names,
            X,
            y,
            meta,
            config=eval_config,
            baseline_model=self.baseline_model,
        )
        model_report = dict((comparison.get("results") or {}).get(self.model_name) or {})
        if model_report.get("status") != "ok":
            failed = self._empty_result(
                str(model_report.get("error") or "strict 评估没有成功划分"),
                time.time() - started,
            )
            failed.update(
                {
                    "evaluation": "strict_multi_split",
                    "evaluation_report": comparison,
                    "n_samples": int(len(y)),
                    "n_classes": int(len(np.unique(y))),
                }
            )
            return failed

        completed = int(model_report.get("n_splits_completed") or 0)
        requested = int(model_report.get("n_splits_requested") or self.n_repeats)
        isolation_clean = bool(model_report.get("per_split")) and all(
            bool((row.get("isolation") or {}).get("clean"))
            for row in model_report.get("per_split") or []
        )
        # @AI_GENERATED
        # P1-1 改动 C：门禁增加表示合同断言——288×2 不可登记 Challenger。
        representation_ok = bool(
            X.shape[2] == 3
            and list(self.sampler_config.channels) == ["value", "i_cal", "is_measured"]
        )
        # @AI_GENERATED: end
        production_contract_valid = bool(
            completed == requested
            and requested >= 10
            and self.split_mode == "strict"
            and isolation_clean
            and representation_ok
        )
        if self.require_production_contract and not production_contract_valid:
            # @AI_GENERATED
            _reason_parts = []
            if not (completed == requested and requested >= 10):
                _reason_parts.append(f"划分不足(completed={completed},requested={requested})")
            if self.split_mode != "strict":
                _reason_parts.append(f"split_mode={self.split_mode}")
            if not isolation_clean:
                _reason_parts.append("隔离自检未全部 clean")
            if not representation_ok:
                _reason_parts.append(
                    f"表示合同不满足(shape[2]={X.shape[2]},channels={list(self.sampler_config.channels)})"
                )
            _reason = "strict 生产契约未通过：" + "；".join(_reason_parts) if _reason_parts else "未知原因"
            # @AI_GENERATED: end
            failed = self._empty_result(
                _reason,
                time.time() - started,
            )
            failed.update(
                {
                    "evaluation": "strict_multi_split",
                    "evaluation_report": comparison,
                    "n_samples": int(len(y)),
                    "n_classes": int(len(np.unique(y))),
                    "n_splits_completed": completed,
                    "n_splits_requested": requested,
                    "production_contract_valid": False,
                }
            )
            return failed

        labels = sorted(int(value) for value in np.unique(y))
        sample_digest = self._sample_digest(y, meta)
        split_payload = {
            "split_mode": self.split_mode,
            "n_repeats": requested,
            "n_test_days": self.n_test_days,
            "held_device_ratio": self.held_device_ratio,
            "base_seed": self.random_state,
            "splits": [
                {
                    "seed": row.get("seed"),
                    "n_train": row.get("n_train"),
                    "n_test": row.get("n_test"),
                    "isolation": row.get("isolation"),
                }
                for row in model_report.get("per_split") or []
            ],
        }
        split_digest = self._digest(split_payload)
        production_contract = {
            "artifact_format": "tsc_model_directory_v1",
            "model_name": self.model_name,
            "sampler_config": self.sampler_config.to_dict(),
            "preprocess_method": self.preprocess_method,
            "label_classes": labels,
            "evaluation": "strict_multi_split",
            "split_digest": split_digest,
            # @AI_GENERATED
            "representation": "clock_grid_288_mask" if representation_ok else "unknown",
            "channels": list(self.sampler_config.channels),
            # @AI_GENERATED: end
        }
        production_contract_digest = self._digest(production_contract)
        evaluation_contract = {
            "sample_digest": sample_digest,
            "split_digest": split_digest,
            "random_seed": self.random_state,
            "metric_name": "macro_f1_mean",
            "production_contract_digest": production_contract_digest,
            "production_contract_valid": production_contract_valid,
            "split_mode": self.split_mode,
            "n_splits_completed": completed,
            "n_splits_requested": requested,
            # @AI_GENERATED
            "representation": "clock_grid_288_mask" if representation_ok else "unknown",
            "channels": list(self.sampler_config.channels),
            # @AI_GENERATED: end
        }

        final_wrapper = get_model(self.model_name, **self.model_params)
        final_wrapper.fit(X, y)
        final_wrapper.set_window_config(
            {
                **self.sampler_config.to_dict(),
                "preprocess_method": self.preprocess_method,
                "label_classes": labels,
                "evaluation_contract": evaluation_contract,
            }
        )
        model_dir_path, model_ref = self._allocate_model_dir()
        final_wrapper.save(str(model_dir_path))
        evaluation_report_path = model_dir_path / "evaluation_report.json"
        evaluation_report_path.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        macro_f1 = model_report.get("macro_f1") or {}
        accuracy = model_report.get("accuracy") or {}
        balanced_accuracy = model_report.get("balanced_accuracy") or {}
        macro_precision = model_report.get("macro_precision") or {}
        macro_recall = model_report.get("macro_recall") or {}
        elapsed = round(time.time() - started, 2)
        result = {
            "model_name": self.model_name,
            "status": "ok",
            "evaluation": "strict_multi_split",
            "elapsed_sec": elapsed,
            "model_dir": model_ref,
            "model_ref": model_ref,
            "model_path": model_ref,
            "artifact_format": "tsc_model_directory_v1",
            "evaluation_report_path": f"{model_ref}/evaluation_report.json",
            "evaluation_report": comparison,
            "macro_f1_mean": macro_f1.get("mean"),
            "macro_f1_std": macro_f1.get("std"),
            "accuracy_mean": accuracy.get("mean"),
            "accuracy_std": accuracy.get("std"),
            "balanced_accuracy_mean": balanced_accuracy.get("mean"),
            "balanced_accuracy_std": balanced_accuracy.get("std"),
            "macro_precision_mean": macro_precision.get("mean"),
            "macro_recall_mean": macro_recall.get("mean"),
            "n_samples": int(len(y)),
            "n_classes": int(len(labels)),
            "n_splits_completed": completed,
            "n_splits_requested": requested,
            "window_length": self.sampler_config.window_length,
            "stride": self.sampler_config.stride,
            "class_distribution": load_stats.get("class_distribution", {}),
            "sample_strategy": {
                **self.sampler_config.to_dict(),
                "split_mode": "tsc",
                "preprocess_method": self.preprocess_method,
                "fault_oversample": self.fault_oversample,
            },
            "evaluation_contract": evaluation_contract,
            "production_contract_valid": production_contract_valid,
            "production_contract_digest": production_contract_digest,
            "split_digest": split_digest,
            "label_snapshot_hash": sample_digest,
            "pairwise_vs_baseline": comparison.get("pairwise_vs_baseline"),
            "metric_note": model_report.get("metric_note"),
            "error": None,
        }
        logger.info(
            "Strict TSC 完成: model=%s macro_f1=%s±%s balanced_acc=%s splits=%d/%d",
            self.model_name,
            result["macro_f1_mean"],
            result["macro_f1_std"],
            result["balanced_accuracy_mean"],
            completed,
            requested,
        )
        return result

    def _run_legacy(
        self,
        X: np.ndarray,
        y: np.ndarray,
        meta,
        load_stats: Dict[str, Any],
        started: float,
    ) -> Dict[str, Any]:
        """保留历史 device holdout + StratifiedKFold，明确标记不可用于生产晋升。"""
        try:
            X_train, y_train, X_test, y_test, meta_train, _ = split_by_device(
                X,
                y,
                meta,
                test_ratio=self.test_ratio,
                random_state=self.random_state,
            )
        except Exception as exc:
            return self._empty_result(f"设备隔离划分失败: {exc}", time.time() - started)
        if len(y_train) < self.n_splits:
            return self._empty_result(
                f"训练样本太少 ({len(y_train)})，不足以做 {self.n_splits}-fold CV",
                time.time() - started,
            )
        all_labels = sorted(int(value) for value in np.unique(y))
        cv_results = self._cross_validate(X_train, y_train, meta_train, all_labels=all_labels)
        holdout_result = self._evaluate_holdout(
            X_train,
            y_train,
            X_test,
            y_test,
            all_labels=all_labels,
        )
        trained_wrapper = holdout_result.pop("_trained_wrapper", None)
        model_ref = ""
        if trained_wrapper is not None:
            model_dir_path, model_ref = self._allocate_model_dir()
            trained_wrapper.save(str(model_dir_path))

        elapsed = round(time.time() - started, 2)
        return {
            "model_name": self.model_name,
            "status": "ok",
            "evaluation": "legacy_exploration_only",
            "elapsed_sec": elapsed,
            "model_dir": model_ref,
            "model_ref": model_ref,
            "model_path": model_ref,
            "artifact_format": "tsc_model_directory_v1",
            "macro_f1_mean": cv_results["macro_f1_mean"],
            "macro_f1_std": cv_results["macro_f1_std"],
            "accuracy_mean": cv_results["accuracy_mean"],
            "accuracy_std": cv_results["accuracy_std"],
            "balanced_accuracy_mean": None,
            "balanced_accuracy_std": None,
            "macro_precision_mean": cv_results["macro_precision_mean"],
            "macro_recall_mean": cv_results["macro_recall_mean"],
            "n_samples": int(len(y)),
            "n_classes": int(len(np.unique(y))),
            "per_class_f1": holdout_result.get("per_class_f1"),
            "confusion_matrix": holdout_result.get("confusion_matrix"),
            "train_time_sec": cv_results["train_time_sec"],
            "predict_time_sec": cv_results["predict_time_sec"],
            "window_length": self.sampler_config.window_length,
            "stride": self.sampler_config.stride,
            "n_train_samples": int(len(y_train)),
            "n_test_samples": int(len(y_test)),
            "n_discarded_windows": 0,
            "class_distribution": load_stats.get("class_distribution", {}),
            "holdout_macro_f1": holdout_result.get("macro_f1"),
            "holdout_accuracy": holdout_result.get("accuracy"),
            "holdout_macro_f1_labels_in_test_only": holdout_result.get(
                "macro_f1_labels_in_test_only"
            ),
            "n_labels_full": holdout_result.get("n_labels_full"),
            "n_labels_in_test": holdout_result.get("n_labels_in_test"),
            "production_contract_valid": False,
            "metric_note": (
                "legacy_exploration_only：仅供历史实验；生产晋升必须使用 strict 多次划分"
            ),
            "error": None,
        }

    def _cross_validate(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        meta_train,
        all_labels: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        f1_scores: List[float] = []
        acc_scores: List[float] = []
        prec_scores: List[float] = []
        rec_scores: List[float] = []
        train_times: List[float] = []
        predict_times: List[float] = []

        for repeat in range(self.n_repeats):
            seed = self.random_state + repeat
            skf = StratifiedKFold(n_splits=self.n_splits, shuffle=True, random_state=seed)
            for train_idx, val_idx in skf.split(X_train, y_train):
                wrapper = get_model(self.model_name, **self.model_params)
                t0 = time.time()
                wrapper.fit(X_train[train_idx], y_train[train_idx])
                train_times.append(time.time() - t0)
                t0 = time.time()
                preds = wrapper.predict(X_train[val_idx])
                predict_times.append(time.time() - t0)
                labels = all_labels or sorted(int(value) for value in np.unique(y_train))
                f1_scores.append(
                    f1_score(y_train[val_idx], preds, average="macro", labels=labels, zero_division=0)
                )
                acc_scores.append(accuracy_score(y_train[val_idx], preds))
                prec_scores.append(
                    precision_score(
                        y_train[val_idx], preds, average="macro", labels=labels, zero_division=0
                    )
                )
                rec_scores.append(
                    recall_score(
                        y_train[val_idx], preds, average="macro", labels=labels, zero_division=0
                    )
                )

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
        wrapper = get_model(self.model_name, **self.model_params)
        wrapper.fit(X_train, y_train)
        labels = all_labels or sorted(
            int(value) for value in np.unique(np.concatenate([y_train, y_test]))
        )
        wrapper.set_window_config(
            {
                **self.sampler_config.to_dict(),
                "preprocess_method": self.preprocess_method,
                "label_classes": labels,
                "evaluation_contract": {"evaluation": "legacy_exploration_only"},
            }
        )
        preds = wrapper.predict(X_test)
        matrix = confusion_matrix(y_test, preds, labels=labels)
        f1_values = f1_score(y_test, preds, average=None, labels=labels, zero_division=0)
        labels_in_test = sorted(int(value) for value in np.unique(y_test))
        return {
            "macro_f1": round(
                float(f1_score(y_test, preds, average="macro", labels=labels, zero_division=0)),
                6,
            ),
            "accuracy": round(float(accuracy_score(y_test, preds)), 6),
            "macro_f1_labels_in_test_only": round(
                float(
                    f1_score(
                        y_test,
                        preds,
                        average="macro",
                        labels=labels_in_test,
                        zero_division=0,
                    )
                ),
                6,
            ),
            "n_labels_full": len(labels),
            "n_labels_in_test": len(labels_in_test),
            "per_class_f1": {
                int(label): round(float(value), 4)
                for label, value in zip(labels, f1_values)
            },
            "confusion_matrix": matrix.tolist(),
            "confusion_matrix_labels": labels,
            "_trained_wrapper": wrapper,
        }

    def _allocate_model_dir(self) -> tuple[Path, str]:
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        model_ref_name = f"tsc-{self.model_name}-{timestamp}-{uuid.uuid4().hex[:8]}"
        backend_dir = Path(__file__).resolve().parents[3]
        model_dir_path = backend_dir / "data" / "models" / "tsc" / model_ref_name
        model_dir_path.mkdir(parents=True, exist_ok=True)
        return model_dir_path, model_dir_path.relative_to(backend_dir).as_posix()

    @staticmethod
    def _sample_digest(y: np.ndarray, meta) -> str:
        hasher = hashlib.sha256(np.ascontiguousarray(y).tobytes())
        if "sample_id" in meta.columns:
            hasher.update("\n".join(meta["sample_id"].astype(str)).encode("utf-8"))
        else:
            hasher.update(str(len(meta)).encode("utf-8"))
        return hasher.hexdigest()

    @staticmethod
    def _digest(payload: Dict[str, Any]) -> str:
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _empty_result(self, error_msg: str, elapsed: float) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "status": "failed",
            "evaluation": self.evaluation,
            "elapsed_sec": round(elapsed, 2),
            "macro_f1_mean": None,
            "macro_f1_std": None,
            "accuracy_mean": None,
            "accuracy_std": None,
            "balanced_accuracy_mean": None,
            "balanced_accuracy_std": None,
            "macro_precision_mean": None,
            "macro_recall_mean": None,
            "n_samples": 0,
            "n_classes": 0,
            "production_contract_valid": False,
            "error": error_msg,
        }
# @AI_GENERATED: end
