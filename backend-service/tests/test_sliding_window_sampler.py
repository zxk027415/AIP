# @AI_GENERATED
"""
单元测试：SlidingWindowSampler

验证滑动窗口切分器的核心功能：
- 基本切分逻辑
- 跨天窗口
- 纯度过滤
- 覆盖率过滤
- 多策略对比
- 边界情况
- 配置持久化
- 真实数据冒烟测试
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 确保能导入 backend-service 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.iterative_labeling.tsc.sliding_window_sampler import (
    SamplerConfig,
    SlidingWindowSampler,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_device_data(n_points: int, label_pattern: list, interval_min: int = 5) -> tuple:
    """生成合成设备时序 + 标签数据。

    label_pattern: 重复填充到 n_points 长度的标签列表。
    """
    times = pd.date_range("2021-01-01", periods=n_points, freq=f"{interval_min}min")
    # 构造简单的正弦波功率 + 理论值
    values = np.sin(np.linspace(0, 4 * np.pi, n_points)) * 5 + 10
    i_cal = values * 1.05  # 理论电流略高于实际

    ts_df = pd.DataFrame({"time": times, "value": values, "i_cal": i_cal})

    # 标签：重复 pattern 填满
    full_labels = (label_pattern * ((n_points // len(label_pattern)) + 1))[:n_points]
    label_df = pd.DataFrame({"time": times, "label": full_labels})

    return ts_df, label_df


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBasicSlicing:
    """基本切分逻辑测试。"""

    def test_correct_window_count(self):
        """288 点序列 + stride=288 应切出恰好 1 个窗口。"""
        ts, labels = _make_device_data(288, [0])
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert X.shape == (1, 288, 2)
        assert y.shape == (1,)
        assert len(meta) == 1

    def test_multiple_windows(self):
        """576 点序列 + stride=72 应切出多个窗口。"""
        # n_windows = (576 - 288) // 72 + 1 = 288//72 + 1 = 5
        ts, labels = _make_device_data(576, [0])
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=72))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        expected_count = (576 - 288) // 72 + 1  # = 5
        assert X.shape[0] == expected_count
        assert X.shape[1] == 288
        assert X.shape[2] == 2

    def test_too_short_sequence(self):
        """序列比窗口短时返回空。"""
        ts, labels = _make_device_data(100, [0])
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=72))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert X.shape == (0, 288, 2)
        assert len(y) == 0
        assert len(meta) == 0


class TestCrossDayWindow:
    """跨天窗口验证：窗口不强制按天断开。"""

    def test_window_spans_midnight(self):
        """窗口可以横跨自然日边界（如 23:00 → 次日 05:00）。"""
        # 600 点 × 5min = 50h，跨越至少 2 个自然日
        ts, labels = _make_device_data(600, [0])
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=144))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        # 第一个窗口从 00:00 开始，跨过第一天整
        # 第二个窗口从 12:00 开始，跨入第二天
        assert X.shape[0] >= 2
        # 验证第二个窗口的 t_start 在第一天内，t_end 在第二天
        t_start_1 = meta.iloc[1]["t_start"]
        t_end_1 = meta.iloc[1]["t_end"]
        assert t_start_1.day == 1  # 同一天内开始
        assert t_end_1.day == 2    # 跨入第二天


class TestPurityFilter:
    """纯度过滤：混合标签窗口被正确丢弃。"""

    def test_pure_window_kept(self):
        """全为同一标签的窗口保留。"""
        ts, labels = _make_device_data(288, [1])
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288, purity_threshold=0.7))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert len(y) == 1
        assert y[0] == 1
        assert meta.iloc[0]["purity"] == 1.0

    def test_mixed_window_discarded(self):
        """标签 50/50 混合（纯度=0.5 < 阈值 0.7）的窗口被丢弃。"""
        # 前 144 点 label=0，后 144 点 label=1 → 纯度 0.5
        pattern = [0] * 144 + [1] * 144
        ts, labels = _make_device_data(288, pattern)
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288, purity_threshold=0.7))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert len(y) == 0  # 被丢弃

    def test_barely_pure_window_kept(self):
        """纯度刚好达标（0.75 > 0.7）的窗口保留。"""
        # 216 点 label=0 + 72 点 label=1 → 纯度 216/288 = 0.75
        pattern = [0] * 216 + [1] * 72
        ts, labels = _make_device_data(288, pattern)
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288, purity_threshold=0.7))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert len(y) == 1
        assert y[0] == 0
        assert meta.iloc[0]["purity"] == pytest.approx(0.75, abs=0.01)


class TestCoverageFilter:
    """覆盖率过滤：NaN 过多的窗口被丢弃。"""

    def test_all_nan_discarded(self):
        """全 NaN 窗口被丢弃。"""
        ts, labels = _make_device_data(288, [0])
        ts["value"] = np.nan
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert len(y) == 0

    def test_partial_nan_above_threshold_kept(self):
        """NaN 比例在阈值内（< 10%）的窗口保留。"""
        ts, labels = _make_device_data(288, [0])
        # 只有 20 个点是 NaN（20/288 = 6.9% < 10%）
        ts.loc[:19, "value"] = np.nan
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288, min_coverage=0.9))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert len(y) == 1

    def test_partial_nan_below_threshold_discarded(self):
        """NaN 比例超阈值（> 10%）的窗口丢弃。"""
        ts, labels = _make_device_data(288, [0])
        # 50 个点是 NaN（50/288 = 17.4% > 10%）
        ts.loc[:49, "value"] = np.nan
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288, min_coverage=0.9))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert len(y) == 0


class TestLabelStrategies:
    """多策略对比测试。"""

    def test_majority_vs_fault_priority_different_output(self):
        """相同数据在 majority 和 fault_priority 下输出不同。"""
        # 250 点 normal + 38 点 fault → majority=normal(86.8%), fault_priority=fault(38/288=13.2%>10%)
        pattern = [0] * 250 + [1] * 38
        ts, labels = _make_device_data(288, pattern)

        sampler_maj = SlidingWindowSampler(SamplerConfig(
            window_length=288, stride=288, label_strategy="majority", purity_threshold=0.7
        ))
        sampler_fp = SlidingWindowSampler(SamplerConfig(
            window_length=288, stride=288, label_strategy="fault_priority", fault_priority_min_ratio=0.1
        ))

        _, y_maj, _ = sampler_maj.transform(ts, labels, device_id="dev1")
        _, y_fp, _ = sampler_fp.transform(ts, labels, device_id="dev1")

        assert len(y_maj) == 1
        assert y_maj[0] == 0  # majority → normal

        assert len(y_fp) == 1
        assert y_fp[0] == 1  # fault_priority → fault（38 >= 288*0.1=28.8）


class TestEdgeCases:
    """边界情况。"""

    def test_all_unlabeled(self):
        """全部未标注（label=NaN）返回空。"""
        ts, _ = _make_device_data(288, [0])
        labels = pd.DataFrame({"time": ts["time"], "label": [np.nan] * 288})
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert len(y) == 0

    def test_empty_dataframe(self):
        """空 DataFrame 返回空。"""
        ts = pd.DataFrame({"time": [], "value": [], "i_cal": []})
        labels = pd.DataFrame({"time": [], "label": []})
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, meta = sampler.transform(ts, labels, device_id="dev1")

        assert X.shape == (0, 288, 2)


class TestConfigPersistence:
    """配置持久化。"""

    def test_get_config_returns_all_fields(self):
        """get_config() 返回完整配置字典。"""
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=72))
        config = sampler.get_config()

        assert config["window_length"] == 288
        assert config["stride"] == 72
        assert config["label_strategy"] == "majority"
        assert config["channels"] == ["value", "i_cal"]
        assert "purity_threshold" in config
        assert "min_coverage" in config

    def test_config_roundtrip(self):
        """配置序列化→反序列化不丢失。"""
        original = SamplerConfig(window_length=576, stride=144, purity_threshold=0.8)
        d = original.to_dict()
        restored = SamplerConfig.from_dict(d)

        assert restored.window_length == 576
        assert restored.stride == 144
        assert restored.purity_threshold == 0.8


class TestMultiDevice:
    """多设备批量切分。"""

    def test_multi_device_concatenation(self):
        """多设备数据拼接输出。"""
        # 两台设备，各 576 点
        ts1, _ = _make_device_data(576, [0])
        ts1["device_id"] = "dev_A"
        ts1["label"] = 0

        ts2, _ = _make_device_data(576, [1])
        ts2["device_id"] = "dev_B"
        ts2["label"] = 1
        ts2["time"] = ts1["time"]  # 同一时间段

        combined = pd.concat([ts1, ts2], ignore_index=True)

        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, meta = sampler.transform_multi_device(combined)

        # 每设备 (576-288)//288 + 1 = 2 个窗口，两设备共 4 个
        assert X.shape[0] == 4
        assert set(meta["device_id"].unique()) == {"dev_A", "dev_B"}


class TestDegenerateWindowFilter:
    """
    min_std 退化窗口过滤（2026-08-03 数据审计后新增）。

    背景：实测 4.4% 的窗口是常数序列（多为夜间全零），其中 302/303 属同一类。
    这些窗口在不同设备间内容完全相同，造成 train/test 46 个字节级重复窗口（占 test 3.7%），
    属直接泄漏且让模型免费答对，虚高精度。
    """

    def test_constant_window_discarded_when_min_std_set(self):
        """min_std > 0 时常数窗口被丢弃。"""
        ts, labels = _make_device_data(288, [0])
        ts["value"] = 5.0  # 常数
        ts["i_cal"] = 5.0
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288, min_std=1e-6))
        X, y, meta = sampler.transform(ts, labels, device_id="const_dev")
        assert len(y) == 0

    def test_constant_window_kept_when_min_std_zero(self):
        """min_std=0（默认）时保留，保持向后兼容。"""
        ts, labels = _make_device_data(288, [0])
        ts["value"] = 5.0
        ts["i_cal"] = 5.0
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288, min_std=0.0))
        X, y, meta = sampler.transform(ts, labels, device_id="const_dev")
        assert len(y) == 1

    def test_all_zero_window_discarded(self):
        """全零窗口（夜间）被丢弃。"""
        ts, labels = _make_device_data(288, [0])
        ts["value"] = 0.0
        ts["i_cal"] = 0.0
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288, min_std=1e-6))
        X, y, _ = sampler.transform(ts, labels, device_id="zero_dev")
        assert len(y) == 0

    def test_varying_window_kept(self):
        """正常有波动的窗口不受影响。"""
        ts, labels = _make_device_data(288, [0])
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288, min_std=1e-6))
        X, y, _ = sampler.transform(ts, labels, device_id="ok_dev")
        assert len(y) == 1

    def test_min_std_in_config(self):
        """min_std 随配置持久化。"""
        sampler = SlidingWindowSampler(SamplerConfig(min_std=1e-6))
        assert sampler.get_config()["min_std"] == 1e-6


class TestNullableLabelDtype:
    """
    回归：label 为 pandas nullable 整型（Int16Dtype 等）时不能崩。

    背景 bug：_aggregate_label 里 np.issubdtype(dtype, np.floating) 无法解析
    pandas 扩展 dtype，会抛 TypeError: Cannot interpret 'Int16Dtype()' as a data type。
    实测 dataset_combined.parquet 的 label 列就是 Int16。
    """

    @pytest.mark.parametrize("dtype", ["Int16", "Int32", "Int64"])
    def test_nullable_int_label(self, dtype):
        ts, labels = _make_device_data(288, [0])
        labels["label"] = labels["label"].astype(dtype)
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, meta = sampler.transform(ts, labels, device_id="nullable_dev")
        assert len(y) == 1
        assert y[0] == 0

    def test_nullable_int_with_missing(self):
        """含 pd.NA 的 nullable 列：缺失点被正确当作未标注。"""
        ts, labels = _make_device_data(288, [0])
        labels["label"] = labels["label"].astype("Int16")
        labels.loc[:99, "label"] = pd.NA  # 前 100 点未标注
        sampler = SlidingWindowSampler(SamplerConfig(
            window_length=288, stride=288, purity_threshold=0.5))
        X, y, meta = sampler.transform(ts, labels, device_id="na_dev")
        # 剩余 188 点全为 0，纯度 1.0（纯度只在已标注点上算）
        assert len(y) == 1
        assert y[0] == 0

    def test_all_na_label(self):
        """全为 pd.NA 时返回空，不崩。"""
        ts, labels = _make_device_data(288, [0])
        labels["label"] = pd.Series([pd.NA] * 288, dtype="Int16")
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, _ = sampler.transform(ts, labels, device_id="allna_dev")
        assert len(y) == 0


class TestMultiBranchSeriesKey:
    """
    回归测试：多支路序列必须按 (site_id, device_id, branch_id) 独立切分。

    背景 bug（2026-08-03 修复）：
      1. transform_multi_device 只按 device_id 分组 —— 实测数据里 15.2% 的设备
         有 2~16 条 branch，混在一起按 time 排序后切窗，样本会跨物理序列跳变。
      2. transform() 内 merge(point_labels, on="time") 在时间戳重复时产生笛卡尔积
         —— 2 支路变 4 行/时间戳，16 支路变 256 行，窗口数被虚增一倍以上。
    """

    @staticmethod
    def _make_two_branch_frame(n_points: int = 600):
        """同一 device 两条 branch，时间戳完全重叠；branch1 值=1.0，branch2 值=100.0。"""
        times = pd.date_range("2021-01-01", periods=n_points, freq="5min")
        rows = []
        for branch, val in (("1", 1.0), ("2", 100.0)):
            for t in times:
                rows.append({
                    "time": t, "site_id": "siteA", "device_id": "devA", "branch_id": branch,
                    "value": val, "i_cal": val, "label": 0,
                })
        return pd.DataFrame(rows)

    def test_branches_not_mixed(self):
        """每个窗口只能来自单一支路：窗口内数值必须全 1.0 或全 100.0，不能混。"""
        df = self._make_two_branch_frame(600)
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, meta = sampler.transform_multi_device(df)

        assert X.shape[0] > 0
        for i in range(X.shape[0]):
            uniq = np.unique(X[i, :, 0])
            assert len(uniq) == 1, f"窗口 {i} 混合了不同支路的值: {uniq}"
            assert uniq[0] in (1.0, 100.0)

    def test_no_cartesian_row_explosion(self):
        """
        时间戳跨支路重复时不能笛卡尔放大。

        每支路 600 点 @ window=288/stride=288 -> 每支路 2 窗口, 两支路共 4 窗口。
        修复前按 device_id 分组 + merge 会得到远多于 4 的窗口数。
        """
        df = self._make_two_branch_frame(600)
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, _, meta = sampler.transform_multi_device(df)

        expected = 2 * ((600 - 288) // 288 + 1)  # 每支路 2 个 -> 共 4
        assert X.shape[0] == expected, f"期望 {expected} 窗口，实际 {X.shape[0]}（疑似笛卡尔放大）"

    def test_meta_has_series_and_device_id(self):
        """meta 必须同时带 series_id（完整主键）和 device_id（用于防泄漏分组）。"""
        df = self._make_two_branch_frame(600)
        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        _, _, meta = sampler.transform_multi_device(df)

        assert "series_id" in meta.columns
        assert "device_id" in meta.columns
        # 两条支路 -> 两个不同 series_id，但同一个 device_id
        assert meta["series_id"].nunique() == 2
        assert meta["device_id"].nunique() == 1
        assert set(meta["series_id"]) == {"siteA|devA|1", "siteA|devA|2"}

    def test_resolve_series_keys_full(self):
        """三列齐全时用完整主键。"""
        df = self._make_two_branch_frame(300)
        sampler = SlidingWindowSampler()
        assert sampler.resolve_series_keys(df) == ["site_id", "device_id", "branch_id"]

    def test_resolve_series_keys_partial(self):
        """只有部分主键列时取交集。"""
        df = self._make_two_branch_frame(300).drop(columns=["site_id"])
        sampler = SlidingWindowSampler()
        assert sampler.resolve_series_keys(df) == ["device_id", "branch_id"]

    def test_resolve_series_keys_fallback(self):
        """一个主键列都没有时退回 device_id。"""
        df = self._make_two_branch_frame(300).drop(columns=["site_id", "branch_id"])
        sampler = SlidingWindowSampler()
        assert sampler.resolve_series_keys(df) == ["device_id"]

    def test_sample_id_unique_across_series_same_site(self):
        """
        回归：同站点不同设备的 sample_id 不能撞车。

        原实现 sample_id = f"tsc-{device_id[:16]}-{start:06d}"，而 series_id 形如
        "site|device|branch"，截前 16 字符只剩 site_id -> 同站点所有设备撞 id，
        导致 load_and_split_all_devices 按 sample_id 去重时静默丢窗口。
        """
        times = pd.date_range("2021-01-01", periods=600, freq="5min")
        rows = []
        # 同一 site，两台不同 device（site_id 长度 16，正好覆盖旧实现的截断长度）
        for dev in ("1e0ebdaa84800000", "1e0ebdaa57802000"):
            for t in times:
                rows.append({
                    "time": t, "site_id": "1e0ebc23f1002000", "device_id": dev,
                    "branch_id": "1", "value": 1.0, "i_cal": 1.0, "label": 0,
                })
        df = pd.DataFrame(rows)

        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, meta = sampler.transform_multi_device(df)

        assert meta["series_id"].nunique() == 2
        assert meta["sample_id"].nunique() == len(meta), (
            f"sample_id 撞车：{len(meta)} 个窗口只有 {meta['sample_id'].nunique()} 个唯一 id"
        )

    def test_duplicate_timestamps_deduped_in_transform(self):
        """transform() 单序列内遇到重复时间戳时去重兜底，不放大行数。"""
        times = pd.date_range("2021-01-01", periods=288, freq="5min")
        # 故意构造重复时间戳（模拟未按完整主键分组的输入）
        ts = pd.DataFrame({
            "time": list(times) + list(times),
            "value": [1.0] * 288 + [2.0] * 288,
            "i_cal": [1.0] * 288 + [2.0] * 288,
        })
        labels = pd.DataFrame({"time": list(times) + list(times), "label": [0] * 576})

        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=288))
        X, y, meta = sampler.transform(ts, labels, device_id="dup_test")

        # 去重后只剩 288 点 -> 恰好 1 个窗口，且值全为首次出现的 1.0
        assert X.shape[0] == 1
        assert np.unique(X[0, :, 0]).tolist() == [1.0]


class TestRealDataSmoke:
    """真实数据冒烟测试（如果数据文件存在）。"""

    @pytest.fixture
    def real_data(self):
        p = Path(__file__).resolve().parents[1] / "data" / "iterative_labeling" / "modeling_path_compare" / "pv_fault" / "datasets" / "pathcmp-20260803021250-ea9c92ab-by_day.parquet"
        if not p.exists():
            pytest.skip("真实数据文件不存在")
        df = pd.read_parquet(p, columns=["time", "device_id", "value", "i_cal", "label"])
        return df

    def test_real_data_produces_samples(self, real_data):
        """真实数据能切出样本且不报错。"""
        # 取前 5 个设备
        devices = real_data["device_id"].unique()[:5]
        subset = real_data[real_data["device_id"].isin(devices)].copy()

        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=72))
        X, y, meta = sampler.transform_multi_device(subset)

        assert X.shape[0] > 0
        assert X.shape[1] == 288
        assert X.shape[2] == 2
        assert len(y) == X.shape[0]
        assert len(meta) == X.shape[0]
        assert all(c in meta.columns for c in ["sample_id", "t_start", "t_end", "purity", "device_id"])

    def test_real_data_class_distribution(self, real_data):
        """真实数据切分后类别分布合理。"""
        devices = real_data["device_id"].unique()[:20]
        subset = real_data[real_data["device_id"].isin(devices)].copy()

        sampler = SlidingWindowSampler(SamplerConfig(window_length=288, stride=72))
        X, y, meta = sampler.transform_multi_device(subset)

        unique_labels = np.unique(y)
        # 至少应有 2 个类别（正常 + 某种故障）
        assert len(unique_labels) >= 1
        # 所有纯度应 >= purity_threshold
        assert (meta["purity"] >= 0.7).all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
# @AI_GENERATED: end
