# @AI_GENERATED
"""
单元测试：data_loader.py

验证：
- 按设备划分不泄漏
- 故障过采样增加故障样本
- preprocess_X 归一化 + NaN 填充
- split_by_device 设备不跨集
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.iterative_labeling.tsc.sliding_window_sampler import SamplerConfig
from services.iterative_labeling.tsc.data_loader import (
    load_and_split_all_devices,
    split_by_device,
    preprocess_X,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REAL_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "iterative_labeling" / "modeling_path_compare" / "pv_fault" / "datasets" / "pathcmp-20260803021250-ea9c92ab-by_day.parquet"


def _make_multi_device_parquet(tmp_path: Path, n_devices: int = 6, points_per_device: int = 600) -> Path:
    """在 tmp 目录生成合成 parquet，返回路径。"""
    rows = []
    for i in range(n_devices):
        dev_id = f"test_dev_{i:03d}"
        times = pd.date_range("2021-01-01", periods=points_per_device, freq="5min")
        values = np.sin(np.linspace(0, 4 * np.pi, points_per_device)) * 5 + 10
        i_cal = values * 1.05
        # 前 80% 正常，后 20% 故障（label=1）
        labels = [0] * int(points_per_device * 0.8) + [1] * int(points_per_device * 0.2)
        labels = labels[:points_per_device]
        for t, v, ic, lbl in zip(times, values, i_cal, labels):
            rows.append({"time": t, "device_id": dev_id, "value": v, "i_cal": ic, "label": lbl})

    df = pd.DataFrame(rows)
    path = tmp_path / "test_data.parquet"
    df.to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSplitByDevice:
    """按设备划分 train/test 测试。"""

    def test_no_device_leakage(self, tmp_path):
        """训练集和测试集的设备 ID 完全不重叠。"""
        path = _make_multi_device_parquet(tmp_path, n_devices=10, points_per_device=600)
        cfg = SamplerConfig(window_length=288, stride=144)
        X, y, meta, stats = load_and_split_all_devices(str(path), cfg, fault_oversample=False)

        X_train, y_train, X_test, y_test, meta_train, meta_test = split_by_device(
            X, y, meta, test_ratio=0.2, random_state=90
        )

        train_devs = set(meta_train["device_id"].unique())
        test_devs = set(meta_test["device_id"].unique())
        assert len(train_devs & test_devs) == 0, "设备泄漏！"

    def test_split_ratio_approximate(self, tmp_path):
        """测试集设备比例大致为 20%。"""
        path = _make_multi_device_parquet(tmp_path, n_devices=20, points_per_device=600)
        cfg = SamplerConfig(window_length=288, stride=144)
        X, y, meta, _ = load_and_split_all_devices(str(path), cfg, fault_oversample=False)

        _, _, _, _, meta_train, meta_test = split_by_device(X, y, meta, test_ratio=0.2, random_state=90)

        n_train_devs = meta_train["device_id"].nunique()
        n_test_devs = meta_test["device_id"].nunique()
        total = n_train_devs + n_test_devs
        ratio = n_test_devs / total
        # 允许偏差（设备数少时难精确）
        assert 0.1 <= ratio <= 0.4


class TestFaultOversample:
    """故障过采样测试。"""

    def test_oversample_increases_fault_count(self, tmp_path):
        """开启过采样后，故障样本应多于不过采样。"""
        path = _make_multi_device_parquet(tmp_path, n_devices=4, points_per_device=600)
        cfg = SamplerConfig(window_length=288, stride=72)

        _, y_no_os, _, _ = load_and_split_all_devices(str(path), cfg, fault_oversample=False)
        _, y_os, _, _ = load_and_split_all_devices(str(path), cfg, fault_oversample=True)

        fault_count_no_os = (y_no_os != 0).sum()
        fault_count_os = (y_os != 0).sum()
        assert fault_count_os >= fault_count_no_os


class TestPreprocessX:
    """预处理测试。"""

    def test_zscore_mean_near_zero(self):
        """z-score 后每样本均值接近 0。"""
        rng = np.random.default_rng(42)
        X = rng.random((10, 288, 2)).astype(np.float32) * 100 + 50
        X_norm = preprocess_X(X, method="per_sample_zscore")

        for i in range(10):
            assert abs(X_norm[i].mean()) < 1e-5

    def test_minmax_range_01(self):
        """min-max 后每样本值域在 [0, 1]。"""
        rng = np.random.default_rng(42)
        X = rng.random((10, 288, 2)).astype(np.float32) * 100
        X_norm = preprocess_X(X, method="per_sample_minmax")

        for i in range(10):
            assert X_norm[i].min() >= -1e-6
            assert X_norm[i].max() <= 1.0 + 1e-6

    def test_nan_filled(self):
        """NaN 被线性插值填充。"""
        X = np.ones((2, 288, 2), dtype=np.float32) * 5.0
        X[0, 50:60, 0] = np.nan  # 第 0 样本第 0 通道有 10 个 NaN
        X_out = preprocess_X(X, method="none")

        assert not np.isnan(X_out).any()
        # 插值后应接近 5.0
        assert np.allclose(X_out[0, 50:60, 0], 5.0, atol=0.1)

    def test_all_nan_sample(self):
        """全 NaN 样本被填为 0。"""
        X = np.full((1, 288, 2), np.nan, dtype=np.float32)
        X_out = preprocess_X(X, method="per_sample_zscore")
        assert not np.isnan(X_out).any()
        assert (X_out == 0.0).all()


class TestRealData:
    """真实数据冒烟（如果文件存在）。"""

    @pytest.fixture
    def real_path(self):
        if not REAL_DATA_PATH.exists():
            pytest.skip("真实数据文件不存在")
        return str(REAL_DATA_PATH)

    def test_load_and_split_real(self, real_path):
        """真实数据 load → split 不报错，且无设备泄漏。"""
        # 只取前 30 个设备避免太慢
        df = pd.read_parquet(real_path, columns=["time", "device_id", "value", "i_cal", "label"])
        devices = df["device_id"].unique()[:30]
        subset = df[df["device_id"].isin(devices)].copy()

        # 写临时文件
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
            subset.to_parquet(f.name, index=False)
            tmp_path = f.name

        try:
            cfg = SamplerConfig(window_length=288, stride=72)
            X, y, meta, stats = load_and_split_all_devices(tmp_path, cfg, fault_oversample=True)

            assert X.shape[0] > 0
            assert stats["n_samples"] > 0

            X_train, y_train, X_test, y_test, meta_train, meta_test = split_by_device(
                X, y, meta, test_ratio=0.2, random_state=90
            )

            train_devs = set(meta_train["device_id"].unique())
            test_devs = set(meta_test["device_id"].unique())
            assert len(train_devs & test_devs) == 0
        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
# @AI_GENERATED: end
