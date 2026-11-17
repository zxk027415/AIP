# @AI_GENERATED
"""TSC 模型统一包装器：形状适配、训练契约和可移植目录工件。"""

from __future__ import annotations

import json
import logging
import pickle
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class TSCModelWrapper:
    """把 aeon/sklearn 模型统一为 time-first ``[n, T, C]`` 接口。"""

    def __init__(
        self,
        model_name: str,
        model: Any,
        is_aeon: bool = True,
        hyperparams: Optional[Dict] = None,
    ) -> None:
        self.model_name = model_name
        self.model = model
        self.is_aeon = bool(is_aeon)
        self.hyperparams = hyperparams or {}
        self.window_config: Optional[Dict[str, Any]] = None
        self.training_contract: Optional[Dict[str, Any]] = None
        self.label_classes: List[int] = []
        self.train_time_sec = 0.0
        self.is_fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TSCModelWrapper":
        values = np.asarray(X)
        labels = np.asarray(y)
        if len(values) == 0 or len(values) != len(labels):
            raise ValueError(f"TSC fit 样本数非法: X={len(values)}, y={len(labels)}")
        X_input = self._prepare_input(values)
        started = time.time()
        self.model.fit(X_input, labels)
        self.train_time_sec = round(time.time() - started, 3)
        model_classes = getattr(self.model, "classes_", None)
        classes = model_classes if model_classes is not None else np.unique(labels)
        self.label_classes = [int(value) for value in np.asarray(classes).tolist()]
        self.is_fitted = True
        logger.info(
            "%s fit 完成, 耗时 %.2fs, 样本数=%d, classes=%s",
            self.model_name,
            self.train_time_sec,
            len(labels),
            self.label_classes,
        )
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        self._assert_fitted()
        return np.asarray(self.model.predict(self._prepare_input(np.asarray(X))))

    def predict_proba(self, X: np.ndarray) -> Optional[np.ndarray]:
        self._assert_fitted()
        X_input = self._prepare_input(np.asarray(X))
        if hasattr(self.model, "predict_proba"):
            return np.asarray(self.model.predict_proba(X_input))
        if hasattr(self.model, "decision_function"):
            from scipy.special import softmax

            decisions = np.asarray(self.model.decision_function(X_input))
            if decisions.ndim == 1:
                decisions = np.column_stack([-decisions, decisions])
            return np.asarray(softmax(decisions, axis=1))
        return None

    def save(self, dir_path: str) -> None:
        output_dir = Path(dir_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        model_path = output_dir / "model.pkl"
        with model_path.open("wb") as handle:
            pickle.dump(self.model, handle, protocol=pickle.HIGHEST_PROTOCOL)
        (output_dir / "metadata.json").write_text(
            json.dumps(self.get_metadata(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "%s 已保存到 %s (模型大小 %.2f MB)",
            self.model_name,
            dir_path,
            model_path.stat().st_size / 1024 / 1024,
        )

    @classmethod
    def load(cls, dir_path: str) -> "TSCModelWrapper":
        model_dir = Path(dir_path)
        metadata_path = model_dir / "metadata.json"
        model_path = model_dir / "model.pkl"
        if not metadata_path.is_file() or not model_path.is_file():
            raise FileNotFoundError(f"模型文件不完整: {dir_path}")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        with model_path.open("rb") as handle:
            model = pickle.load(handle)
        wrapper = cls(
            model_name=str(metadata.get("model_name") or "unknown"),
            model=model,
            is_aeon=bool(metadata.get("is_aeon", True)),
            hyperparams=dict(metadata.get("hyperparams") or {}),
        )
        wrapper.window_config = dict(metadata.get("window_config") or {}) or None
        wrapper.training_contract = dict(metadata.get("training_contract") or {}) or None
        wrapper.label_classes = [int(value) for value in metadata.get("label_classes") or []]
        if not wrapper.label_classes:
            wrapper.label_classes = [
                int(value) for value in np.asarray(getattr(model, "classes_", [])).tolist()
            ]
        wrapper.train_time_sec = float(metadata.get("train_time_sec") or 0.0)
        wrapper.is_fitted = True
        return wrapper

    def get_metadata(self) -> Dict[str, Any]:
        model_size_mb = 0.0
        try:
            model_size_mb = len(pickle.dumps(self.model)) / 1024 / 1024
        except Exception:  # 元数据估算失败不影响工件保存
            pass
        return {
            "schema_version": 2,
            "model_name": self.model_name,
            "is_aeon": self.is_aeon,
            "hyperparams": self.hyperparams,
            "window_config": self.window_config,
            "training_contract": self.training_contract,
            "label_classes": list(self.label_classes),
            "train_time_sec": self.train_time_sec,
            "is_fitted": self.is_fitted,
            "model_size_mb": round(model_size_mb, 3),
        }

    def set_window_config(self, config: Dict[str, Any]) -> None:
        self.window_config = dict(config)
        contract = self.window_config.get("evaluation_contract")
        self.training_contract = dict(contract) if isinstance(contract, dict) else None
        classes = self.window_config.get("label_classes")
        if isinstance(classes, list):
            self.label_classes = [int(value) for value in classes]

    def class_labels(self, n_columns: Optional[int] = None) -> List[int]:
        labels = list(self.label_classes)
        if not labels:
            labels = [int(value) for value in np.asarray(getattr(self.model, "classes_", [])).tolist()]
        if n_columns is not None and labels and len(labels) != int(n_columns):
            raise ValueError(
                f"模型类别元数据与概率列不一致: classes={len(labels)}, proba={n_columns}"
            )
        if n_columns is not None and not labels:
            labels = list(range(int(n_columns)))
        return labels

    def _assert_fitted(self) -> None:
        if not self.is_fitted:
            raise RuntimeError(f"TSC 模型 {self.model_name} 尚未 fit/load")

    def _prepare_input(self, X: np.ndarray) -> np.ndarray:
        if X.ndim not in (2, 3):
            raise ValueError(f"TSC 输入必须是 [n,T] 或 [n,T,C]，当前 shape={X.shape}")
        if X.ndim == 2:
            return X[:, np.newaxis, :] if self.is_aeon else X[:, :, np.newaxis]
        expected_length = (self.window_config or {}).get("window_length")
        expected_channels = (self.window_config or {}).get("channels")
        if expected_length and X.shape[1] != int(expected_length):
            raise ValueError(
                f"TSC 输入窗口长度 {X.shape[1]} 与模型契约 {expected_length} 不一致"
            )
        if expected_channels and X.shape[2] != len(expected_channels):
            raise ValueError(
                f"TSC 输入通道数 {X.shape[2]} 与模型契约 {len(expected_channels)} 不一致"
            )
        if self.is_aeon:
            return np.ascontiguousarray(X.transpose(0, 2, 1))
        return np.ascontiguousarray(X)
# @AI_GENERATED: end
