# @AI_GENERATED
"""
smote_oversample operator backend — SMOTE-based minority class oversampling.

移植自 fault-diag-algo-release-3.1/enos_fault_diag/models/utils/smote.py。

逻辑：
- 对每个类别分组，若样本数 < limit，则用 KNN（k=1）合成合计到 limit 条
- limit 限制少数类最大合成后样本数，多数类样本不做改动
- 若 imbalanced-learn 可用则优先用 SMOTE；否则用 sklearn NearestNeighbors 实现简版 SMOTE
- 任何异常（数据不足、合成失败等）均 fallback 到原始数据并记录 warning，不中断流水线
"""
import logging

import numpy as np
import pandas as pd

from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "smote_oversample"

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 简版 SMOTE（不依赖 imbalanced-learn）
# ──────────────────────────────────────────────

def _make_sample_simple(X: np.ndarray, num_to_add: int) -> np.ndarray:
    """
    基于 NearestNeighbors（k=1 最近邻）生成合成样本。
    移植自源码 make_sample()，去掉已废弃的 DataFrame.append 调用。
    """
    from sklearn.neighbors import NearestNeighbors

    n = len(X)
    if n < 2:
        # 样本不足 2 条，无法找最近邻，直接复制
        indices = np.random.randint(0, n, size=num_to_add)
        return X[indices]

    nn = NearestNeighbors(n_neighbors=2).fit(X)
    # kneighbors 返回 (distances, indices)；取第 1 列（第 0 列是自身）
    neighbor_indices = nn.kneighbors(X, return_distance=False)[:, 1]

    rnd_indices = np.random.randint(0, n, size=num_to_add)
    dists = np.random.uniform(-1, 1, size=(num_to_add, X.shape[1]))

    synthetic = np.empty((num_to_add, X.shape[1]), dtype=X.dtype if np.issubdtype(X.dtype, np.floating) else float)
    for i, (src_idx, d) in enumerate(zip(rnd_indices, dists)):
        neighbor_idx = neighbor_indices[src_idx]
        synthetic[i] = X[src_idx] + d * (X[src_idx] - X[neighbor_idx])

    return synthetic


def _smote_simple(X: pd.DataFrame, y: np.ndarray, limit: int) -> tuple[pd.DataFrame, np.ndarray]:
    """
    简版 SMOTE：对每个类别，若样本数 < limit，则合成到 limit。

    Args:
        X:     特征 DataFrame
        y:     标签数组（int）
        limit: 少数类合成后最大样本数

    Returns:
        (X_resampled, y_resampled)
    """
    X_parts = []
    y_parts = []

    classes = np.unique(y)
    X_arr = X.to_numpy(dtype=float)

    for cls in classes:
        mask = y == cls
        X_cls = X_arr[mask]
        n = len(X_cls)

        if n < limit:
            num_to_add = limit - n
            synthetic = _make_sample_simple(X_cls, num_to_add)
            X_combined = np.vstack([X_cls, synthetic])
            y_combined = np.full(len(X_combined), cls, dtype=y.dtype)
        else:
            X_combined = X_cls
            y_combined = y[mask]

        X_parts.append(X_combined)
        y_parts.append(y_combined)

    X_new = pd.DataFrame(np.vstack(X_parts), columns=X.columns)
    y_new = np.concatenate(y_parts)
    return X_new, y_new


def _smote_imblearn(X: pd.DataFrame, y: np.ndarray, limit: int) -> tuple[pd.DataFrame, np.ndarray]:
    """
    使用 imbalanced-learn 的 SMOTE，通过 sampling_strategy 控制 limit。
    """
    from imblearn.over_sampling import SMOTE

    classes, counts = np.unique(y, return_counts=True)
    # sampling_strategy: 指定每个少数类合成后的目标样本数（不超过 limit）
    strategy = {}
    majority_count = counts.max()
    for cls, cnt in zip(classes, counts):
        if cnt < majority_count:
            strategy[cls] = min(limit, majority_count)

    if not strategy:
        # 已经平衡，不需要合成
        return X.copy(), y.copy()

    sm = SMOTE(sampling_strategy=strategy, random_state=42)
    X_res, y_res = sm.fit_resample(X, y)
    return pd.DataFrame(X_res, columns=X.columns), y_res


# ──────────────────────────────────────────────
# 主 execute()
# ──────────────────────────────────────────────

def execute(params: dict, inputs: dict) -> dict:
    """
    SMOTE 过采样：对少数类合成样本，使每类样本数接近 limit。

    Args:
        params:
            - limit (int): 少数类合成后最大样本数，默认 500
        inputs:
            - features (pd.DataFrame): 特征矩阵
            - target   (np.ndarray | list): 标签数组

    Returns:
        {
            "features": pd.DataFrame,  # 过采样后的特征矩阵
            "target":   np.ndarray,    # 过采样后的标签数组
        }

    行为：
    - 任何运行时异常均 fallback 到原始数据，记录 warning，不中断流水线
    """
    # ── 解析输入 ──────────────────────────────────────────────────────────────
    features = inputs.get("features")
    target = inputs.get("target")

    # 兼容上游用 selected_features 传出的情况
    if features is None:
        features = inputs.get("selected_features")

    if features is None or not isinstance(features, pd.DataFrame):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'features' must be a pandas DataFrame"
        )
    if target is None:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            "Input 'target' (labels) is required"
        )

    # ── 解析参数 ──────────────────────────────────────────────────────────────
    try:
        limit = int(params.get("limit") or 500)
    except (TypeError, ValueError):
        limit = 500

    if limit <= 0:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError",
            f"'limit' must be a positive integer, got {limit}"
        )

    # ── 准备数据 ──────────────────────────────────────────────────────────────
    X = features.copy()
    y = np.asarray(target)

    if len(X) != len(y):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError",
            f"features rows ({len(X)}) != target length ({len(y)})"
        )

    if X.empty or len(y) == 0:
        logger.warning(f"[{OPERATOR_ID}] Empty input, returning as-is")
        return {"features": X, "target": y}

    classes, counts = np.unique(y, return_counts=True)
    if len(classes) < 2:
        logger.warning(
            f"[{OPERATOR_ID}] Only one class found (y={classes}), "
            "SMOTE requires ≥2 classes — returning original data"
        )
        return {"features": X, "target": y}

    logger.info(
        f"[{OPERATOR_ID}] Before SMOTE: {dict(zip(classes, counts))}, limit={limit}"
    )

    # ── 执行 SMOTE ───────────────────────────────────────────────────────────
    try:
        try:
            X_res, y_res = _smote_imblearn(X, y, limit)
            logger.info(f"[{OPERATOR_ID}] Used imblearn SMOTE")
        except ImportError:
            logger.warning(
                f"[{OPERATOR_ID}] imbalanced-learn not available, "
                "falling back to simple SMOTE (sklearn NearestNeighbors)"
            )
            X_res, y_res = _smote_simple(X, y, limit)
            logger.info(f"[{OPERATOR_ID}] Used simple SMOTE")

        new_classes, new_counts = np.unique(y_res, return_counts=True)
        logger.info(
            f"[{OPERATOR_ID}] After SMOTE: {dict(zip(new_classes, new_counts))}"
        )
        return {"features": X_res, "target": y_res}

    except Exception as exc:
        logger.warning(
            f"[{OPERATOR_ID}] SMOTE failed ({type(exc).__name__}: {exc}), "
            "falling back to original data"
        )
        return {"features": X, "target": y}
# @AI_GENERATED: end
