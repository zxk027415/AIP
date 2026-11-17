# @AI_GENERATED
"""
dbscan operator backend — DBSCAN 密度聚类。

基于 sklearn.cluster.DBSCAN 实现，自动选取输入 DataFrame 的数值列。
噪声点的标签为 -1，不计入 n_clusters_found。

参数 (params)
-------------
- eps         (float): 邻域半径，默认 0.5
- min_samples (int):   核心点的最少邻居数，默认 5

输入 (inputs)
-------------
- data (pd.DataFrame): 待聚类数据（含数值列）

返回 (dict)
-----------
- labels          (np.ndarray): 每个样本的簇标签（-1 表示噪声）
- n_clusters_found (int):       发现的簇数（不含噪声标签 -1）

错误
----
- InputError: 若 data 不是 DataFrame
- InputError: 若数值列样本数 < 2
"""
import logging

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "dbscan"

logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    DBSCAN 密度聚类。

    Args:
        params:
            - eps         (float): 邻域半径，默认 0.5
            - min_samples (int):   核心点最少邻居数，默认 5
        inputs:
            - data (pd.DataFrame): 待聚类数据

    Returns:
        {
            "labels":           np.ndarray,  # 簇标签；-1 表示噪声点
            "n_clusters_found": int,         # 有效簇数（不含噪声）
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
        eps = float(params.get("eps") or 0.5)
    except (TypeError, ValueError):
        eps = 0.5

    try:
        min_samples = int(params.get("min_samples") or 5)
    except (TypeError, ValueError):
        min_samples = 5

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
            f"DBSCAN requires at least 2 samples, got {n_samples}"
        )

    # ── 填充缺失值（用列均值）────────────────────────────────────────────────
    X = numeric_df.fillna(numeric_df.mean()).values

    # ── 执行 DBSCAN ───────────────────────────────────────────────────────────
    db = DBSCAN(eps=eps, min_samples=min_samples)
    db.fit(X)

    labels: np.ndarray = db.labels_.astype(int)
    # 噪声标签为 -1，不计入簇数
    n_clusters_found: int = int(len(set(labels)) - (1 if -1 in labels else 0))
    n_noise: int = int(np.sum(labels == -1))

    logger.info(
        f"[{OPERATOR_ID}] eps={eps}, min_samples={min_samples}, "
        f"n_samples={n_samples}, n_clusters={n_clusters_found}, n_noise={n_noise}"
    )

    return {
        "labels": labels,
        "n_clusters_found": n_clusters_found,
    }
# @AI_GENERATED: end
