# @AI_GENERATED
"""
TSCModelWrapper — 时序分类模型统一包装器。

所有模型（aeon Tier1/2 + 自定义 Tier3）统一为 sklearn 兼容的
fit / predict / predict_proba / save / load 接口。

aeon 模型的 X 形状约定为 [n_samples, n_channels, series_length]（channel-first），
而我们的 pipeline 输出为 [n_samples, series_length, n_channels]（time-first），
包装器内部自动转置。

设计文档: .kiro/specs/pv-fault-timeseries-diagnosis/design.md §2.2.1
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


class TSCModelWrapper:
    """
    时序分类模型统一包装器。

    Parameters
    ----------
    model_name : str
        模型标识名（如 'minirocket', 'cnn_lstm'）。
    model : object
        实际模型实例（sklearn 兼容接口或自定义模型）。
    is_aeon : bool
        是否为 aeon 库模型（需要 channel-first 转置）。
    hyperparams : dict
        超参数记录。
    """

    def __init__(
        self,
        model_name: str,
        model: Any,
        is_aeon: bool = True,
        hyperparams: Optional[Dict] = None,
    ):
        self.model_name = model_name
        self.model = model
        self.is_aeon = is_aeon
        self.hyperparams = hyperparams or {}
        self.window_config: Optional[Dict] = None
        self.train_time_sec: float = 0.0
        self.is_fitted: bool = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TSCModelWrapper":
        """
        训练模型。

        Parameters
        ----------
        X : ndarray [n_samples, series_length, n_channels] — time-first
        y : ndarray [n_samples]
        """
        X_input = self._prepare_input(X)
        t0 = time.time()
        self.model.fit(X_input, y)
        self.train_time_sec = round(time.time() - t0, 3)
        self.is_fitted = True
        logger.info("%s fit 完成, 耗时 %.2fs, 样本数=%d", self.model_name, self.train_time_sec, len(y))
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别标签。"""
        X_input = self._prepare_input(X)
        return self.model.predict(X_input)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        预测类别概率（如果模型支持）。

        Returns
        -------
        ndarray [n_samples, n_classes] 或 None
        """
        X_input = self._prepare_input(X)
        if hasattr(self.model, "predict_proba"):
            return self.model.predict_proba(X_input)
        # 部分模型（如 RidgeClassifierCV）无 predict_proba
        if hasattr(self.model, "decision_function"):
            from scipy.special import softmax
            decisions = self.model.decision_function(X_input)
            if decisions.ndim == 1:
                decisions = np.column_stack([-decisions, decisions])
            return softmax(decisions, axis=1)
        return None

    def save(self, dir_path: str) -> None:
        """
        持久化模型 + 元数据到指定目录。

        文件结构:
          dir_path/
            model.pkl      — pickle 序列化的模型
            metadata.json  — 模型名、超参、窗口配置、训练时间
        """
        out = Path(dir_path)
        out.mkdir(parents=True, exist_ok=True)

        # 保存模型
        model_path = out / "model.pkl"
        with open(model_path, "wb") as f:
            pickle.dump(self.model, f, protocol=pickle.HIGHEST_PROTOCOL)

        # 保存元数据
        metadata = self.get_metadata()
        meta_path = out / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        model_size_mb = model_path.stat().st_size / 1024 / 1024
        logger.info("%s 已保存到 %s (模型大小 %.2f MB)", self.model_name, dir_path, model_size_mb)

    @classmethod
    def load(cls, dir_path: str) -> "TSCModelWrapper":
        """从目录加载持久化模型。"""
        d = Path(dir_path)
        meta_path = d / "metadata.json"
        model_path = d / "model.pkl"

        if not meta_path.exists() or not model_path.exists():
            raise FileNotFoundError(f"模型文件不完整: {dir_path}")

        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        with open(model_path, "rb") as f:
            model = pickle.load(f)

        wrapper = cls(
            model_name=metadata.get("model_name", "unknown"),
            model=model,
            is_aeon=metadata.get("is_aeon", True),
            hyperparams=metadata.get("hyperparams", {}),
        )
        wrapper.window_config = metadata.get("window_config")
        wrapper.train_time_sec = metadata.get("train_time_sec", 0.0)
        wrapper.is_fitted = True
        return wrapper

    def get_metadata(self) -> Dict:
        """返回完整元数据字典。"""
        model_size_mb = 0.0
        # 尝试估计内存大小
        try:
            import sys
            model_size_mb = sys.getsizeof(pickle.dumps(self.model)) / 1024 / 1024
        except Exception:
            pass

        return {
            "model_name": self.model_name,
            "is_aeon": self.is_aeon,
            "hyperparams": self.hyperparams,
            "window_config": self.window_config,
            "train_time_sec": self.train_time_sec,
            "is_fitted": self.is_fitted,
            "model_size_mb": round(model_size_mb, 3),
        }

    def set_window_config(self, config: Dict) -> None:
        """绑定窗口配置（训练时调用）。"""
        self.window_config = config

    def _prepare_input(self, X: np.ndarray) -> np.ndarray:
        """
        将 pipeline 输出的 time-first [n, T, C] 转换为模型需要的格式。

        aeon 模型需要 channel-first: [n, C, T]
        自定义 PyTorch 模型直接使用 time-first: [n, T, C]
        """
        if X.ndim == 2:
            # 单通道 [n, T] → 扩展为 [n, 1, T] (aeon) 或 [n, T, 1]
            if self.is_aeon:
                return X[:, np.newaxis, :]
            return X[:, :, np.newaxis]

        if X.ndim == 3:
            if self.is_aeon:
                # [n, T, C] → [n, C, T]
                return np.ascontiguousarray(X.transpose(0, 2, 1))
            return X

        return X
# @AI_GENERATED: end
