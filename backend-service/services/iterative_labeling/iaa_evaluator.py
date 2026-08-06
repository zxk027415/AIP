"""IAA 一致性评估 MVP：Overlap_Batch + Cohen/Fleiss Kappa + 简单偏差检测。"""

from __future__ import annotations

import logging
import random
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class IAAEvaluator:
    def create_overlap_batch(
        self,
        total_units: List[str],
        overlap_ratio: float = 0.1,
        *,
        seed: Optional[int] = None,
    ) -> List[str]:
        units = [u for u in total_units if u]
        if not units:
            return []
        ratio = max(0.0, min(1.0, float(overlap_ratio)))
        n = max(1, int(round(len(units) * ratio))) if ratio > 0 else 0
        n = min(n, len(units))
        rng = random.Random(seed)
        return rng.sample(units, n) if n else []

    def compute_kappa(
        self,
        overlap_verdicts: Dict[str, List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        """overlap_verdicts: reviewer_id -> [{unit_key, verdict_label}, ...]"""
        reviewers = sorted(overlap_verdicts.keys())
        if len(reviewers) < 2:
            return {
                "iaa_score": None,
                "iaa_method": None,
                "per_unit_agreement": {},
                "warning": "need_at_least_two_reviewers",
            }

        # unit -> reviewer -> label
        by_unit: Dict[str, Dict[str, Any]] = defaultdict(dict)
        for reviewer, rows in overlap_verdicts.items():
            for row in rows or []:
                uk = str(row.get("unit_key") or "")
                if not uk:
                    continue
                by_unit[uk][reviewer] = row.get("verdict_label")

        common_units = [
            uk for uk, mapping in by_unit.items() if len(mapping) >= 2
        ]
        per_unit_agreement: Dict[str, float] = {}
        for uk in common_units:
            labels = list(by_unit[uk].values())
            mode_count = Counter(labels).most_common(1)[0][1]
            per_unit_agreement[uk] = float(mode_count) / float(len(labels))

        if len(reviewers) == 2:
            r0, r1 = reviewers[0], reviewers[1]
            y0, y1 = [], []
            for uk in common_units:
                if r0 in by_unit[uk] and r1 in by_unit[uk]:
                    y0.append(by_unit[uk][r0])
                    y1.append(by_unit[uk][r1])
            if not y0:
                return {
                    "iaa_score": None,
                    "iaa_method": "cohen",
                    "per_unit_agreement": per_unit_agreement,
                    "warning": "no_overlapping_labels",
                }
            from sklearn.metrics import cohen_kappa_score

            score = float(cohen_kappa_score(y0, y1))
            return {
                "iaa_score": score,
                "iaa_method": "cohen",
                "per_unit_agreement": per_unit_agreement,
            }

        # Fleiss' Kappa（多人）
        score = self._fleiss_kappa(by_unit, reviewers, common_units)
        return {
            "iaa_score": score,
            "iaa_method": "fleiss",
            "per_unit_agreement": per_unit_agreement,
        }

    def detect_bias(
        self,
        all_verdicts: Dict[str, List[Dict[str, Any]]],
        bias_threshold: float = 0.2,
    ) -> List[Dict[str, Any]]:
        overall = Counter()
        per_reviewer: Dict[str, Counter] = {}
        for reviewer, rows in all_verdicts.items():
            c = Counter()
            for row in rows or []:
                lab = row.get("verdict_label")
                if lab is None:
                    continue
                c[lab] += 1
                overall[lab] += 1
            per_reviewer[reviewer] = c

        total = sum(overall.values()) or 1
        overall_ratio = {k: v / total for k, v in overall.items()}
        biased: List[Dict[str, Any]] = []
        for reviewer, counts in per_reviewer.items():
            n = sum(counts.values()) or 1
            biased_labels = []
            max_dev = 0.0
            for lab, cnt in counts.items():
                ratio = cnt / n
                base = overall_ratio.get(lab, 0.0)
                dev = abs(ratio - base)
                max_dev = max(max_dev, dev)
                if dev >= float(bias_threshold):
                    biased_labels.append(lab)
            if biased_labels:
                biased.append(
                    {
                        "reviewer": reviewer,
                        "biased_labels": biased_labels,
                        "deviation": float(max_dev),
                    }
                )
        return biased

    @staticmethod
    def _fleiss_kappa(
        by_unit: Dict[str, Dict[str, Any]],
        reviewers: List[str],
        common_units: List[str],
    ) -> Optional[float]:
        if not common_units:
            return None
        # 收集类别
        categories = sorted(
            {
                by_unit[uk][r]
                for uk in common_units
                for r in reviewers
                if r in by_unit[uk]
            },
            key=lambda x: (x is None, str(x)),
        )
        if len(categories) < 2:
            return 1.0
        cat_index = {c: i for i, c in enumerate(categories)}
        n_items = len(common_units)
        n_cats = len(categories)
        n_raters = len(reviewers)
        matrix = [[0] * n_cats for _ in range(n_items)]
        for i, uk in enumerate(common_units):
            for r in reviewers:
                if r not in by_unit[uk]:
                    continue
                matrix[i][cat_index[by_unit[uk][r]]] += 1

        # P_i
        p_i = []
        for row in matrix:
            s = sum(row)
            if s <= 1:
                p_i.append(0.0)
            else:
                p_i.append((sum(v * v for v in row) - s) / float(s * (s - 1)))
        p_bar = sum(p_i) / float(n_items)
        # p_j
        col_sums = [sum(matrix[i][j] for i in range(n_items)) for j in range(n_cats)]
        total = float(n_items * n_raters) or 1.0
        p_j = [c / total for c in col_sums]
        p_e = sum(p * p for p in p_j)
        if abs(1.0 - p_e) < 1e-12:
            return 1.0
        return float((p_bar - p_e) / (1.0 - p_e))
