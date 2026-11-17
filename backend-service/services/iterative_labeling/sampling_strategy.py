"""审核队列采样排序：uncertainty / diversity / disagreement_first / random。"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

VALID_STRATEGIES = ("uncertainty", "diversity", "disagreement_first", "random")


class SamplingStrategy:
    """对 Review_Session.units 按策略重排，不修改单元内容。"""

    def sort_units(
        self,
        units: List[Dict[str, Any]],
        strategy: str = "uncertainty",
        *,
        disagreement_first: bool = False,
        n_clusters: int = 5,
        diversity_conf_threshold: float = 0.5,
        feature_vectors: Optional[np.ndarray] = None,
        seed: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        if not units:
            return []

        strategy = (strategy or "uncertainty").strip().lower()
        if strategy not in VALID_STRATEGIES:
            logger.warning("未知 sampling_strategy=%s，回退 uncertainty", strategy)
            strategy = "uncertainty"

        # disagreement_first 可作为独立策略，也可叠在其他策略上
        if strategy == "disagreement_first":
            disagreement_first = True
            strategy = "uncertainty"

        indexed = list(enumerate(units))

        def _confidence(item: tuple) -> float:
            unit = item[1]
            return float((unit.get("classifier_prediction") or {}).get("confidence") or 0.0)

        def _unit_key(item: tuple) -> str:
            return str(item[1].get("unit_key") or "")

        if strategy == "random":
            rng = random.Random(seed)
            ordered = indexed[:]
            rng.shuffle(ordered)
        elif strategy == "diversity":
            ordered = self._diversity_order(
                indexed,
                n_clusters=n_clusters,
                diversity_conf_threshold=diversity_conf_threshold,
                feature_vectors=feature_vectors,
                seed=seed,
            )
        else:
            # uncertainty：低置信度优先
            ordered = sorted(indexed, key=lambda it: (_confidence(it), _unit_key(it)))

        if disagreement_first:
            disagree = [it for it in ordered if bool(it[1].get("disagreement"))]
            agree = [it for it in ordered if not bool(it[1].get("disagreement"))]
            ordered = disagree + agree

        return [it[1] for it in ordered]

    def _diversity_order(
        self,
        indexed: List[tuple],
        *,
        n_clusters: int,
        diversity_conf_threshold: float,
        feature_vectors: Optional[np.ndarray],
        seed: Optional[int],
    ) -> List[tuple]:
        """低置信度子集做 KMeans，代表样本前置；无特征时退化为 uncertainty。"""
        low_conf = [
            it
            for it in indexed
            if float((it[1].get("classifier_prediction") or {}).get("confidence") or 0.0)
            < float(diversity_conf_threshold)
        ]
        if not low_conf or feature_vectors is None:
            return sorted(
                indexed,
                key=lambda it: (
                    float((it[1].get("classifier_prediction") or {}).get("confidence") or 0.0),
                    str(it[1].get("unit_key") or ""),
                ),
            )

        try:
            from sklearn.cluster import KMeans
        except ImportError:
            logger.warning("sklearn 不可用，diversity 回退 uncertainty")
            return sorted(
                indexed,
                key=lambda it: (
                    float((it[1].get("classifier_prediction") or {}).get("confidence") or 0.0),
                    str(it[1].get("unit_key") or ""),
                ),
            )

        positions = [it[0] for it in low_conf]
        try:
            matrix = np.asarray(feature_vectors, dtype=float)[positions]
        except Exception:
            return sorted(
                indexed,
                key=lambda it: (
                    float((it[1].get("classifier_prediction") or {}).get("confidence") or 0.0),
                    str(it[1].get("unit_key") or ""),
                ),
            )

        k = max(1, min(int(n_clusters), len(low_conf), matrix.shape[0]))
        if k <= 1 or matrix.ndim != 2 or matrix.shape[0] < 2:
            reps = [it[0] for it in low_conf]
        else:
            km = KMeans(n_clusters=k, random_state=seed if seed is not None else 42, n_init=10)
            labels = km.fit_predict(matrix)
            reps: List[int] = []
            for cluster_id in range(k):
                members = [i for i, lab in enumerate(labels) if int(lab) == cluster_id]
                if not members:
                    continue
                # 取离质心最近的代表
                center = km.cluster_centers_[cluster_id]
                best = min(members, key=lambda i: float(np.linalg.norm(matrix[i] - center)))
                reps.append(low_conf[best][0])

        rep_set = set(reps)
        representatives = [it for it in indexed if it[0] in rep_set]
        others = [it for it in indexed if it[0] not in rep_set]
        representatives.sort(
            key=lambda it: (
                float((it[1].get("classifier_prediction") or {}).get("confidence") or 0.0),
                str(it[1].get("unit_key") or ""),
            )
        )
        others.sort(
            key=lambda it: (
                float((it[1].get("classifier_prediction") or {}).get("confidence") or 0.0),
                str(it[1].get("unit_key") or ""),
            )
        )
        return representatives + others
