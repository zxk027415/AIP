# @AI_GENERATED
"""ks_test — 两样本 Kolmogorov-Smirnov 分布漂移检验。"""
from __future__ import annotations

import numpy as np
from loguru import logger
from scipy import stats

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "ks_test"


def execute(params: dict, inputs: dict) -> dict:
    """
    inputs: sample_a, sample_b (array-like)
    params: alpha (默认 0.05)
    returns: statistic, pvalue, drift_detected (p < alpha)
    """
    a = inputs.get("sample_a")
    b = inputs.get("sample_b")
    if a is None or b is None:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "sample_a and sample_b are required")

    try:
        alpha = float(params.get("alpha") if params.get("alpha") is not None else 0.05)
    except (TypeError, ValueError) as e:
        raise OperatorExecutionError(OPERATOR_ID, "ParameterError", f"Invalid alpha: {e}")

    va = np.asarray(a, dtype=float)
    vb = np.asarray(b, dtype=float)
    va = va[np.isfinite(va)]
    vb = vb[np.isfinite(vb)]
    if len(va) < 5 or len(vb) < 5:
        raise OperatorExecutionError(OPERATOR_ID, "InputError", "Each sample needs >=5 finite points")

    stat, pval = stats.ks_2samp(va, vb)
    drift = bool(pval < alpha)
    logger.info(f"[{OPERATOR_ID}] stat={stat:.4f}, p={pval:.4g}, drift={drift}")
    return {
        "statistic": float(stat),
        "pvalue": float(pval),
        "drift_detected": drift,
        "alpha": alpha,
    }
# @AI_GENERATED: end
