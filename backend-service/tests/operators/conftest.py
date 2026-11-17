# @AI_GENERATED
"""
tests/operators/conftest.py — 共享 fixture。

提供：
- router: 已完成 auto_discover 的 OperatorRouter 单例
- 各种合成数据 fixture（数值 / 分类 / 时序 / 混合类型）
- backends_dir: operator_backends 目录绝对路径
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd
import pytest

# 确保 backend-service 在 PYTHONPATH（与其它测试保持一致）
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_TESTS_DIR = os.path.dirname(_THIS_DIR)
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from services.operator_execution.router import OperatorRouter


@pytest.fixture(scope="session")
def backends_dir() -> str:
    """operator_backends 目录绝对路径。"""
    return os.path.join(_BACKEND_DIR, "services", "operator_backends")


@pytest.fixture(scope="session")
def router(backends_dir) -> OperatorRouter:
    """已完成 auto_discover 的 router，跨全部测试复用。"""
    r = OperatorRouter()
    r.auto_discover(backends_dir)
    return r


# ────────────────────────────────────────────────────────────────────────────
# 合成数据 fixture
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def numeric_df_small() -> pd.DataFrame:
    """10 行 × 3 列纯数值 DataFrame。列 a/b/c 有确定值方便断言。"""
    return pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        "b": [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0],
        "c": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    })


@pytest.fixture
def numeric_df_medium() -> pd.DataFrame:
    """50 行 × 5 列随机数值 DataFrame。"""
    rng = np.random.RandomState(42)
    return pd.DataFrame(
        rng.randn(50, 5),
        columns=list("abcde"),
    )


@pytest.fixture
def numeric_df_with_duplicates() -> pd.DataFrame:
    """含重复行的 DataFrame，8 行数据其中 3 行为重复。"""
    return pd.DataFrame({
        "a": [1, 2, 3, 1, 4, 2, 5, 3],
        "b": [10, 20, 30, 10, 40, 20, 50, 30],
    })


@pytest.fixture
def mixed_type_df() -> pd.DataFrame:
    """混合类型 DataFrame：数值 + 字符串分类 + 日期。"""
    return pd.DataFrame({
        "num": [1.0, 2.0, 3.0, 4.0, 5.0],
        "cat": ["A", "B", "A", "C", "B"],
        "date": pd.date_range("2024-01-01", periods=5),
    })


@pytest.fixture
def timeseries_df() -> pd.DataFrame:
    """50 点等距时序数据。timestamp + value 两列。"""
    ts = pd.date_range("2024-01-01", periods=50, freq="h")
    values = np.sin(np.arange(50) / 5.0) * 10.0 + np.arange(50) * 0.5
    return pd.DataFrame({"timestamp": ts, "value": values})


@pytest.fixture
def classification_data():
    """40 样本 × 5 特征的二分类合成数据。返回 (features_df, target_array)。"""
    from sklearn.datasets import make_classification
    X, y = make_classification(
        n_samples=40, n_features=5, n_informative=3, n_redundant=1,
        n_classes=2, random_state=42,
    )
    return pd.DataFrame(X, columns=list("abcde")), y


@pytest.fixture
def multiclass_data():
    """60 样本 × 4 特征的三分类合成数据。"""
    from sklearn.datasets import make_classification
    X, y = make_classification(
        n_samples=60, n_features=4, n_informative=3, n_redundant=0,
        n_classes=3, n_clusters_per_class=1, random_state=42,
    )
    return pd.DataFrame(X, columns=list("abcd")), y


@pytest.fixture
def regression_data():
    """40 样本 × 3 特征的回归合成数据。"""
    from sklearn.datasets import make_regression
    X, y = make_regression(n_samples=40, n_features=3, noise=0.1, random_state=42)
    return pd.DataFrame(X, columns=list("abc")), y


@pytest.fixture
def blob_data():
    """80 样本 × 2 特征的三簇聚类数据。返回 (features_df, true_labels)。"""
    from sklearn.datasets import make_blobs
    X, y = make_blobs(n_samples=80, n_features=2, centers=3, random_state=42)
    return pd.DataFrame(X, columns=["x", "y"]), y


@pytest.fixture
def tiny_csv_file(tmp_path) -> str:
    """临时 CSV 文件供 load_csv / export_csv 测试使用。"""
    p = tmp_path / "tiny.csv"
    pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}).to_csv(p, index=False)
    return str(p)


@pytest.fixture
def tiny_parquet_file(tmp_path) -> str:
    """临时 Parquet 文件供 load_parquet 测试使用。"""
    p = tmp_path / "tiny.parquet"
    pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]}).to_parquet(p)
    return str(p)


@pytest.fixture
def tiny_json_file(tmp_path) -> str:
    """临时 JSON 文件供 load_json 测试使用。"""
    p = tmp_path / "tiny.json"
    pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]}).to_json(p, orient="records")
    return str(p)
# @AI_GENERATED: end
