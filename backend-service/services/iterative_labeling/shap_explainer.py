"""SHAP 解释 MVP：优先 TreeExplainer；无 shap 包时回退 feature_importances_ 近似。"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class ShapExplainer:
    def compute_explanations(
        self,
        model: Any,
        feature_matrix: np.ndarray,
        feature_names: List[str],
        shap_top_k: int = 5,
        timeout_seconds: float = 10.0,
    ) -> List[Dict[str, Any]]:
        matrix = np.asarray(feature_matrix, dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            return []
        names = list(feature_names) if feature_names else [f"f{i}" for i in range(matrix.shape[1])]
        top_k = max(1, int(shap_top_k))

        def _run() -> List[Dict[str, Any]]:
            try:
                import shap  # type: ignore

                explainer = shap.TreeExplainer(model)
                values = explainer.shap_values(matrix)
                # 多分类时取预测类或均值绝对值
                if isinstance(values, list):
                    # list[class][n_samples, n_features]
                    abs_stack = np.mean([np.abs(v) for v in values], axis=0)
                    signed = values[0]
                else:
                    abs_stack = np.abs(values)
                    signed = values
                return self._pack(matrix, names, signed, abs_stack, top_k, source="shap")
            except Exception as exc:
                logger.warning("SHAP 不可用，回退 importance 近似: %s", exc)
                return self._importance_fallback(model, matrix, names, top_k)

        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_run)
            try:
                return fut.result(timeout=float(timeout_seconds))
            except FuturesTimeout:
                logger.warning("SHAP 计算超时（%ss）", timeout_seconds)
                return [
                    {
                        "unit_index": i,
                        "available": False,
                        "reason": "timeout",
                        "top_features": [],
                    }
                    for i in range(matrix.shape[0])
                ]

    def _importance_fallback(
        self,
        model: Any,
        matrix: np.ndarray,
        names: List[str],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        importances = getattr(model, "feature_importances_", None)
        if importances is None:
            return [
                {
                    "unit_index": i,
                    "available": False,
                    "reason": "shap_and_importance_unavailable",
                    "top_features": [],
                }
                for i in range(matrix.shape[0])
            ]
        imp = np.asarray(importances, dtype=float)
        # 用 |x| * importance 近似贡献
        approx = np.abs(matrix) * imp.reshape(1, -1)
        return self._pack(matrix, names, matrix * imp.reshape(1, -1), approx, top_k, source="importance_proxy")

    @staticmethod
    def _pack(
        matrix: np.ndarray,
        names: List[str],
        signed: np.ndarray,
        abs_vals: np.ndarray,
        top_k: int,
        *,
        source: str,
    ) -> List[Dict[str, Any]]:
        n_features = min(len(names), matrix.shape[1], abs_vals.shape[1])
        out: List[Dict[str, Any]] = []
        for i in range(matrix.shape[0]):
            order = np.argsort(-abs_vals[i, :n_features])[:top_k]
            top_features = []
            for j in order:
                top_features.append(
                    {
                        "name": names[int(j)],
                        "value": float(matrix[i, int(j)]),
                        "shap_value": float(signed[i, int(j)]),
                    }
                )
            out.append(
                {
                    "unit_index": i,
                    "available": True,
                    "source": source,
                    "top_features": top_features,
                }
            )
        return out
