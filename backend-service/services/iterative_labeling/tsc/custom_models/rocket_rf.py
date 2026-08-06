# @AI_GENERATED
"""
ROCKET + RandomForest 两阶段对照模型。

用途：与 RF 路线最大程度对比（只换特征提取，不换分类器），
帮助归因精度提升来源。

Pipeline: ROCKET Transform → StandardScaler → RandomForest(class_weight=balanced)
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import RidgeClassifierCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


class RocketRFClassifier:
    """
    ROCKET 特征提取 + RandomForest 分类器。

    sklearn 兼容接口: fit(X, y) / predict(X) / predict_proba(X)

    Parameters
    ----------
    num_kernels : int
        ROCKET 随机卷积核数量。
    n_estimators : int
        RandomForest 树数量。
    class_weight : str or dict
        类别权重。
    random_state : int
        随机种子。
    """

    def __init__(
        self,
        n_kernels: int = 10000,
        n_estimators: int = 200,
        class_weight: str = "balanced",
        random_state: int = 90,
    ):
        self.n_kernels = n_kernels
        self.n_estimators = n_estimators
        self.class_weight = class_weight
        self.random_state = random_state
        self._rocket = None
        self._pipeline = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RocketRFClassifier":
        """
        训练。

        Parameters
        ----------
        X : ndarray [n_samples, series_length, n_channels] — time-first
            注意：本模型自己处理转置，不依赖 TSCModelWrapper 的 is_aeon 转置。
        y : ndarray [n_samples]
        """
        from aeon.transformations.collection.convolution_based import Rocket

        # aeon Rocket 需要 [n_samples, n_channels, series_length]
        X_aeon = np.ascontiguousarray(X.transpose(0, 2, 1)) if X.ndim == 3 else X[:, np.newaxis, :]

        self._rocket = Rocket(n_kernels=self.n_kernels, random_state=self.random_state)
        X_features = self._rocket.fit_transform(X_aeon)

        self._pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("rf", RandomForestClassifier(
                n_estimators=self.n_estimators,
                class_weight=self.class_weight,
                random_state=self.random_state,
                n_jobs=-1,
            )),
        ])
        self._pipeline.fit(X_features, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别。"""
        X_features = self._transform(X)
        return self._pipeline.predict(X_features)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测类别概率。"""
        X_features = self._transform(X)
        return self._pipeline.predict_proba(X_features)

    def _transform(self, X: np.ndarray) -> np.ndarray:
        """对输入做 ROCKET 特征提取。"""
        X_aeon = np.ascontiguousarray(X.transpose(0, 2, 1)) if X.ndim == 3 else X[:, np.newaxis, :]
        return self._rocket.transform(X_aeon)
# @AI_GENERATED: end
