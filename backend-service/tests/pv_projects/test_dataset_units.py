# @AI_GENERATED
"""数据集单元（文件 / 目录分片组）的 RED 基线（数据集切片第 2a 步）。

要固定的语义：

**「数据集」不等于「文件」。** `data/benchmark_raw/pvdaq/converted/<系统ID>/*.parquet`
是同一系统的月度分片，合起来才是一个数据集；而 `uploads/` 是平铺目录、文件互不相关。
若按「一文件一数据集」发布，光 benchmark_raw 就有 2863 条，清单不可用。

同时必须**排除研究工作产物**（实测 `benchmark_raw` 下 220 个目录 / 2863 个文件里绝大多数是
派生指标、特征矩阵、日分区样本、实验重跑产物），否则目录窗口会被噪音淹没。
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from typing import Iterator

import pytest

pd = pytest.importorskip("pandas")

from services.pv_projects import facts as facts_mod  # noqa: E402
from services.pv_projects import source_resolver as src  # noqa: E402

MAPPING = {"time_col": "time", "device_col": "device_id", "value_col": "value"}


@contextmanager
def temp_sources() -> Iterator[str]:
    tmp = tempfile.mkdtemp(prefix="pvunit_")
    src.set_source_base(tmp)
    try:
        yield tmp
    finally:
        src.set_source_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _src(tmp: str, ref: str) -> str:
    alias, _, rest = ref.partition("/")
    return os.path.join(tmp, "data", alias, *[p for p in rest.split("/") if p])


def _parquet(path: str, *, device: str, month: int, days: int, per_day: int = 24) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = []
    for day in range(1, days + 1):
        for h in range(per_day):
            rows.append({"device_id": device,
                         "time": f"2026-{month:02d}-{day:02d} {h:02d}:00:00",
                         "value": 1.0})
    pd.DataFrame(rows).to_parquet(path, index=False)


def _csv(path: str, *, device: str = "dev-0", days: int = 3, per_day: int = 24) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["device_id,time,value"]
    for day in range(1, days + 1):
        for h in range(per_day):
            lines.append(f"{device},2026-01-{day:02d} {h:02d}:00:00,1.0")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# 1. 数据集单元发现
# ---------------------------------------------------------------------------

def test_discover_datasets_groups_converted_shards_by_system() -> None:
    """converted/<系统ID>/ 下的月度分片应被归为**一个**数据集。"""
    with temp_sources() as tmp:
        _parquet(_src(tmp, "benchmark_raw/pvdaq/converted/4/2019-05.parquet"), device="s4", month=5, days=3)
        _parquet(_src(tmp, "benchmark_raw/pvdaq/converted/4/2019-06.parquet"), device="s4", month=6, days=3)
        _parquet(_src(tmp, "benchmark_raw/pvdaq/converted/1284/2013-11.parquet"), device="s1284", month=11, days=3)

        units = src.discover_datasets()
        by_ref = {u["dataset_ref"]: u for u in units}
        assert set(by_ref) == {"benchmark_raw/pvdaq/converted/4",
                               "benchmark_raw/pvdaq/converted/1284"}
        assert by_ref["benchmark_raw/pvdaq/converted/4"]["unit_kind"] == "shard_group"
        assert by_ref["benchmark_raw/pvdaq/converted/4"]["shard_count"] == 2
        assert by_ref["benchmark_raw/pvdaq/converted/1284"]["shard_count"] == 1


def test_discover_datasets_treats_uploads_and_demo_as_one_file_each() -> None:
    with temp_sources() as tmp:
        _csv(_src(tmp, "uploads/a.csv"))
        _csv(_src(tmp, "uploads/b.csv"))
        _csv(_src(tmp, "demo/c.csv"))

        units = src.discover_datasets()
        by_ref = {u["dataset_ref"]: u for u in units}
        assert set(by_ref) == {"uploads/a.csv", "uploads/b.csv", "demo/c.csv"}
        for u in units:
            assert u["unit_kind"] == "file"
            assert u["shard_count"] == 1


def test_discover_datasets_excludes_derived_research_outputs() -> None:
    """派生指标 / 特征矩阵 / 日分区样本 / 实验重跑产物不得进入数据集清单。"""
    with temp_sources() as tmp:
        _parquet(_src(tmp, "benchmark_raw/pvdaq/converted/4/2019-05.parquet"), device="s4", month=5, days=2)
        # 以下都是研究产物，必须被排除
        _parquet(_src(tmp, "benchmark_raw/pvdaq/metrics__system_4__part000.parquet"),
                 device="s4", month=5, days=2)
        _csv(_src(tmp, "benchmark_raw/pvdaq/analysis/q1_rf_features.csv"))
        _parquet(_src(tmp, "benchmark_raw/pvdaq/cohort_scan_samples/system_id=4/year=2019/month=5/day=3/x.parquet"),
                 device="s4", month=5, days=1)
        _parquet(_src(tmp, "benchmark_raw/pvdaq/reruns/expansion/x.parquet"), device="s4", month=5, days=1)

        refs = {u["dataset_ref"] for u in src.discover_datasets()}
        assert refs == {"benchmark_raw/pvdaq/converted/4"}, refs


def test_discovered_dataset_refs_round_trip_through_resolve() -> None:
    with temp_sources() as tmp:
        _parquet(_src(tmp, "benchmark_raw/pvdaq/converted/4/2019-05.parquet"), device="s4", month=5, days=2)
        _csv(_src(tmp, "uploads/a.csv"))
        for u in src.discover_datasets():
            unit = src.resolve_dataset_unit(u["dataset_ref"])
            assert unit["shard_paths"], u
            for p in unit["shard_paths"]:
                assert os.path.isfile(p)


# ---------------------------------------------------------------------------
# 2. 单元解析
# ---------------------------------------------------------------------------

def test_resolve_dataset_unit_returns_all_shards_sorted() -> None:
    with temp_sources() as tmp:
        _parquet(_src(tmp, "benchmark_raw/pvdaq/converted/4/2019-06.parquet"), device="s4", month=6, days=2)
        _parquet(_src(tmp, "benchmark_raw/pvdaq/converted/4/2019-05.parquet"), device="s4", month=5, days=2)

        unit = src.resolve_dataset_unit("benchmark_raw/pvdaq/converted/4")
        assert unit["unit_kind"] == "shard_group"
        names = [os.path.basename(p) for p in unit["shard_paths"]]
        assert names == sorted(names), "分片必须稳定排序，保证聚合结果可复现"
        assert len(names) == 2


def test_directory_ref_without_shards_is_rejected() -> None:
    with temp_sources() as tmp:
        os.makedirs(_src(tmp, "benchmark_raw/pvdaq/converted/4"), exist_ok=True)
        with pytest.raises(Exception) as ei:
            src.resolve_dataset_unit("benchmark_raw/pvdaq/converted/4")
        assert getattr(ei.value, "code", None) == "no_shards_in_directory"


# ---------------------------------------------------------------------------
# 3. facts 对分片组做聚合
# ---------------------------------------------------------------------------

def test_facts_aggregate_across_shards() -> None:
    """分片数据集的质量检测必须看全部月份，而不是只看第一个文件。"""
    with temp_sources() as tmp:
        _parquet(_src(tmp, "benchmark_raw/pvdaq/converted/4/2019-05.parquet"),
                 device="s4", month=5, days=31)
        _parquet(_src(tmp, "benchmark_raw/pvdaq/converted/4/2019-06.parquet"),
                 device="s4", month=6, days=30)

        f = facts_mod.compute_dataset_facts("benchmark_raw/pvdaq/converted/4", mapping=MAPPING)
        assert f["row_count"] == (31 + 30) * 24
        assert f["distinct_dates"] == 61
        assert f["shard_count"] == 2
        assert f["source_extension"] == ".parquet"
        # 单设备 → 设备数不足；但日期覆盖与采样完整率都满
        assert f["date_coverage_ratio"] == 1.0
        assert f["sampling_completeness"] == pytest.approx(1.0, abs=0.01)
        assert f["coverage_gaps"] == ["device_count"]


def test_file_dataset_still_reports_single_shard() -> None:
    with temp_sources() as tmp:
        _csv(_src(tmp, "uploads/a.csv"))
        f = facts_mod.compute_dataset_facts("uploads/a.csv", mapping=MAPPING)
        assert f["shard_count"] == 1


# @AI_GENERATED: end
