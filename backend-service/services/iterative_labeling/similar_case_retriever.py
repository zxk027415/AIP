"""相似案例检索 MVP：NearestNeighbors 索引。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class SimilarCaseRetriever:
    def __init__(self):
        self._nn = None
        self._metadata: List[Dict[str, Any]] = []
        self._matrix: Optional[np.ndarray] = None

    def build_index(
        self,
        labeled_feature_matrix: np.ndarray,
        labeled_metadata: List[Dict[str, Any]],
        *,
        metric: str = "euclidean",
    ) -> None:
        matrix = np.asarray(labeled_feature_matrix, dtype=float)
        if matrix.ndim != 2 or matrix.shape[0] == 0:
            self._nn = None
            self._metadata = []
            self._matrix = None
            return
        from sklearn.neighbors import NearestNeighbors

        self._matrix = matrix
        self._metadata = list(labeled_metadata)
        self._nn = NearestNeighbors(n_neighbors=min(10, matrix.shape[0]), metric=metric)
        self._nn.fit(matrix)

    def retrieve(
        self,
        query_vector: np.ndarray,
        k: int = 3,
        metric: str = "euclidean",
    ) -> List[Dict[str, Any]]:
        if self._nn is None or self._matrix is None or not self._metadata:
            return []
        q = np.asarray(query_vector, dtype=float).reshape(1, -1)
        n_neighbors = min(max(1, int(k)), self._matrix.shape[0])
        if getattr(self._nn, "metric", None) != metric:
            from sklearn.neighbors import NearestNeighbors

            self._nn = NearestNeighbors(n_neighbors=n_neighbors, metric=metric)
            self._nn.fit(self._matrix)
        distances, indices = self._nn.kneighbors(q, n_neighbors=n_neighbors)
        results: List[Dict[str, Any]] = []
        for dist, idx in zip(distances[0], indices[0]):
            meta = dict(self._metadata[int(idx)])
            similarity = float(1.0 / (1.0 + float(dist)))
            results.append(
                {
                    "unit_key": meta.get("unit_key"),
                    "label_name": meta.get("label_name"),
                    "label": meta.get("label"),
                    "similarity_score": similarity,
                    "distance": float(dist),
                }
            )
        return results
