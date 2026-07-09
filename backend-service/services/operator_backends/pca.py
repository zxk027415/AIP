# @AI_GENERATED
"""
pca operator backend — 主成分分析（PCA）降维。

使用 sklearn PCA，对输入 DataFrame 的所有数值列做降维，
返回 PC_1..PC_n 列组成的 DataFrame 以及各主成分解释方差比。

校验：
  - n_components > 数值列数时，抛 ParameterError
  - data 不是 pd.DataFrame 时，抛 InputError
  - n_components <= 0 时，抛 ParameterError
"""
import logging

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "pca"

logger = logging.getLogger(__name__)


def execute(params: dict, inputs: dict) -> dict:
    """
    主成分分析降维算子。

    Args:
        params:
            - n_components (int): 主成分数量，默认 2
        inputs:
            - data (pd.DataFrame): 输入特征矩阵，仅使用数值列

    Returns:
        {
            "data":                     pd.DataFrame,  # 列名为 PC_1..PC_n
            "explained_variance_ratio": list[float],   # 各主成分解释方差比
        }

    Raises:
        OperatorExecutionError (InputError):     data 不是 pd.DataFrame
        OperatorExecutionError (ParameterError): n_components > 数值列数 或 <= 0
    """
    # ── 解析参数 ──────────────────────────────────────────────────────────────
    try:
        n_components = int(params.get("n_components") or 2)
    except (TypeError, ValueError):
        n_components = 2

    # ── 输入校验 ──────────────────────────────────────────────────────────────
    data = inputs.get("data")
    if data is None or not isinstance(data, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "input 'data' must be a pd.DataFrame"
        )
    if len(data) == 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "input 'data' is empty"
        )

    # 选取数值列
    numeric_cols = data.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) == 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "input 'data' contains no numeric columns to apply PCA"
        )

    # ── 参数校验 ──────────────────────────────────────────────────────────────
    if n_components <= 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"n_components must be a positive integer, got {n_components}"
        )
    if n_components > len(numeric_cols):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"n_components ({n_components}) exceeds the number of numeric features "
            f"({len(numeric_cols)}): {numeric_cols}"
        )

    # ── PCA 计算 ──────────────────────────────────────────────────────────────
    X = data[numeric_cols].values
    pca = PCA(n_components=n_components)
    X_pca = pca.fit_transform(X)

    # 构建输出 DataFrame：列名 PC_1..PC_n
    pc_cols = [f"PC_{i + 1}" for i in range(n_components)]
    result_df = pd.DataFrame(X_pca, columns=pc_cols, index=data.index)
    explained = pca.explained_variance_ratio_.tolist()

    logger.info(
        f"[{OPERATOR_ID}] n_components={n_components}, "
        f"n_numeric_features={len(numeric_cols)}, "
        f"explained_variance_ratio={[round(v, 4) for v in explained]}"
    )

    return {
        "data": result_df,
        "explained_variance_ratio": explained,
    }
# @AI_GENERATED: end
