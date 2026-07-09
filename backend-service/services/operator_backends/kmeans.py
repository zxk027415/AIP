# @AI_GENERATED
"""
kmeans operator backend — K-Means 聚类。

基于 sklearn.cluster.KMeans 实现，自动选取输入 DataFrame 的数值列。

参数 (params)
-------------
- n_clusters   (int):  聚类数，默认 3
- random_state (int):  随机种子，默认 42

输入 (inputs)
-------------
- data (pd.DataFrame): 待聚类数据（含数值列）

返回 (dict)
-----------
- labels          (np.ndarray): 每个样本所属的簇标签（0 ~ n_clusters-1）
- cluster_centers (np.ndarray): 各簇中心坐标，shape=(n_clusters, n_features)
- inertia         (float):      各样本到所属簇中心距离平方和（越小越紧凑）

错误
----
- InputError: 若 data 不是 DataFrame
- InputError: 若数值列样本数 < 2
"""
import logging

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "kmeans"

logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    K-Means 聚类。

    Args:
        params:
            - n_clusters   (int): 聚类数，默认 3
            - random_state (int): 随机种子，默认 42
        inputs:
            - data (pd.DataFrame): 待聚类数据

    Returns:
        {
            "labels":          np.ndarray,  # 簇标签，长度 = n_samples
            "cluster_centers": np.ndarray,  # shape=(n_clusters, n_numeric_features)
            "inertia":         float,       # 簇内平方和
        }
    """
    # ── 解析输入 ──────────────────────────────────────────────────────────────
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'data' must be a pandas DataFrame"
        )

    # ── 解析参数 ──────────────────────────────────────────────────────────────
    try:
        n_clusters = int(params.get("n_clusters") or 3)
    except (TypeError, ValueError):
        n_clusters = 3

    try:
        random_state = int(params.get("random_state") or 42)
    except (TypeError, ValueError):
        random_state = 42

    # ── 自动选取数值列 ────────────────────────────────────────────────────────
    numeric_df = data.select_dtypes(include=[np.number])
    if numeric_df.empty:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "No numeric columns found in input DataFrame"
        )

    n_samples = len(numeric_df)
    if n_samples < 2:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"KMeans requires at least 2 samples, got {n_samples}"
        )

    # n_clusters 不能超过样本数
    if n_clusters > n_samples:
        logger.warning(
            f"[{OPERATOR_ID}] n_clusters ({n_clusters}) > n_samples ({n_samples}), "
            f"clamping to {n_samples}"
        )
        n_clusters = n_samples

    # ── 填充缺失值（用列均值）────────────────────────────────────────────────
    X = numeric_df.fillna(numeric_df.mean()).values

    # ── 执行 KMeans ───────────────────────────────────────────────────────────
    km = KMeans(n_clusters=n_clusters, random_state=random_state, n_init="auto")
    km.fit(X)

    labels: np.ndarray = km.labels_.astype(int)
    cluster_centers: np.ndarray = km.cluster_centers_
    inertia: float = float(km.inertia_)

    logger.info(
        f"[{OPERATOR_ID}] n_clusters={n_clusters}, n_samples={n_samples}, "
        f"n_features={X.shape[1]}, inertia={inertia:.4f}"
    )

    return {
        "labels": labels,
        "cluster_centers": cluster_centers,
        "inertia": inertia,
    }
# @AI_GENERATED: end
