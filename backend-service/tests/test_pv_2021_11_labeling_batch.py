# @AI_GENERATED
"""
验证 2021-11 待标注批次能被 from-dataset 标注入口消费。

被测产物: backend-service/datasets/pv_labeling_batch_2021_11.parquet
由 scripts/build_pv_2021_11_labeling_batch.py 生成。

这里复刻 POST /api/iterative-labeling/review-sessions/from-dataset
（api/iterative_labeling.py::create_manual_review_from_dataset）的校验与聚合逻辑，
确保数据落盘格式与端点契约一致 —— 避免"文件生成了但端点读不了"。
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_BACKEND = Path(__file__).resolve().parents[1]
BATCH = _BACKEND / "datasets" / "pv_labeling_batch_2021_11.parquet"
META = _BACKEND / "datasets" / "pv_labeling_batch_2021_11.parquet.meta.json"


@pytest.fixture(scope="module")
def batch():
    if not BATCH.exists():
        pytest.skip(
            "待标注批次未生成，先跑: "
            "python scripts/build_pv_2021_11_labeling_batch.py --write"
        )
    return pd.read_parquet(BATCH)


class TestEndpointContract:
    """from-dataset 端点的硬性契约。"""

    def test_has_device_id(self, batch):
        """端点缺 device_id 会返回 422。"""
        assert "device_id" in batch.columns

    def test_has_time_or_time_window(self, batch):
        """端点要求 time 或 time_window 之一。"""
        assert "time" in batch.columns or "time_window" in batch.columns

    def test_not_empty(self, batch):
        """端点对空数据集返回 422。"""
        assert not batch.empty

    def test_time_parseable(self, batch):
        """端点用 pd.to_datetime(...).dt.strftime('%Y-%m-%d') 生成单元键，必须可解析。"""
        parsed = pd.to_datetime(batch["time"], errors="coerce")
        assert parsed.notna().all(), f"{parsed.isna().sum()} 行 time 无法解析"

    def test_unit_aggregation_yields_units(self, batch):
        """复刻端点聚合逻辑，确认能产出待标注单元（否则端点返回 422）。"""
        working = batch.copy()
        working["_manual_time_window"] = pd.to_datetime(
            working["time"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")
        working = working[working["_manual_time_window"].notna()]
        unit_fields = [
            f for f in ("site_id", "device_id", "branch_id", "_manual_time_window")
            if f in working.columns
        ]
        units = working.drop_duplicates(subset=unit_fields)
        assert len(units) > 0
        # 与元数据里记录的单元数一致
        if META.exists():
            import json
            meta = json.loads(META.read_text(encoding="utf-8"))
            assert len(units) == meta["labelable_units_device_x_day"]

    def test_waveform_columns_present(self, batch):
        """审核页波形展示读 value / i_cal（见 api 中 for col in ['value','i_cal']）。"""
        assert "value" in batch.columns
        assert "i_cal" in batch.columns


class TestBatchQuality:
    """批次数据质量 —— 决定标注产出能否真正降低评估方差。"""

    def test_label_column_empty(self, batch):
        """待标注批次的 label 必须为空，否则会被误当成已有真值。"""
        assert "label" in batch.columns
        assert batch["label"].isna().all()

    def test_seven_consecutive_days(self, batch):
        """必须是 7 天全连续 —— 这是它作为时间切分评估块的前提。"""
        days = sorted(pd.to_datetime(batch["time"]).dt.date.unique())
        assert len(days) == 7
        gaps = [b for a, b in zip(days, days[1:]) if (b - a).days != 1]
        assert not gaps, f"日期不连续，断点: {gaps}"

    def test_multi_site(self, batch):
        """多站点是本批次的核心价值（现有块只有单站点，无法验证跨站点泛化）。"""
        assert batch["site_id"].nunique() >= 2

    def test_more_devices_than_existing_block(self, batch):
        """设备数应超过现有唯一可用块 dataset_combined 的 241 台。"""
        assert batch["device_id"].nunique() > 241

    def test_no_missing_measurements(self, batch):
        """value / i_cal 不应缺失，否则切窗时会被 min_coverage 过滤掉。"""
        assert batch["value"].isna().mean() < 0.05
        assert batch["i_cal"].isna().mean() < 0.05

    def test_no_duplicate_primary_key(self, batch):
        """(site,device,branch,time) 必须唯一 —— 重复会导致切分器 merge 笛卡尔积。"""
        dup = batch.duplicated(subset=["site_id", "device_id", "branch_id", "time"]).sum()
        assert dup == 0, f"{dup} 行主键重复"


class TestNoOverlapWithMainDataset:
    """不能与主数据集重叠，否则标注是白做的。"""

    def test_disjoint_from_main(self, batch):
        main_path = _BACKEND / "datasets" / "pv_cumulative_labeled_merged.parquet"
        if not main_path.exists():
            pytest.skip("主数据集不存在")
        main = pd.read_parquet(
            main_path, columns=["time", "site_id", "device_id", "branch_id"]
        )
        main["time"] = pd.to_datetime(main["time"])
        main_keys = set(zip(
            main["site_id"].astype(str), main["device_id"].astype(str),
            main["branch_id"].astype(str), main["time"].values,
        ))
        b = batch.copy()
        b["time"] = pd.to_datetime(b["time"])
        keys = set(zip(
            b["site_id"].astype(str), b["device_id"].astype(str),
            b["branch_id"].astype(str), b["time"].values,
        ))
        overlap = len(keys & main_keys)
        assert overlap == 0, f"{overlap} 个主键已存在于主数据集，标注会重复劳动"


class TestSlicingUsability:
    """批次能被滑窗切分器正常处理（标注完成后要走这条链路）。"""

    def test_sampler_can_slice(self, batch):
        from services.iterative_labeling.tsc.sliding_window_sampler import (
            SamplerConfig, SlidingWindowSampler,
        )
        b = batch.copy()
        b["time"] = pd.to_datetime(b["time"])
        # 用占位标签模拟标注完成后的形态
        b["label"] = 0
        sampler = SlidingWindowSampler(SamplerConfig(
            window_length=288, stride=72, min_std=1e-6))
        assert sampler.resolve_series_keys(b) == ["site_id", "device_id", "branch_id"]
        X, y, meta = sampler.transform_multi_device(b)
        assert X.shape[0] > 0, "切不出窗口，标注后无法用于建模"
        assert X.shape[1] == 288
        assert meta["series_id"].nunique() > 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
# @AI_GENERATED: end
