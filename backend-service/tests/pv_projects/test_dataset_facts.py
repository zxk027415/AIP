# @AI_GENERATED
"""数据集来源解析 + 真实质量检测的 RED 基线（数据集切片第 1 步）。

固定两件事：

1. `services/pv_projects/source_resolver.py`
   —— 把**逻辑别名引用**（`uploads/x.csv`）解析成真实数据文件；越界 / 绝对路径 / 符号链接 /
      不支持的扩展名一律拒；能扫描允许的来源根，回答"磁盘上现在有哪些可挂载的数据"。
   —— alias → 真实根的映射与 `services/timeseries_profiles/path_guard.py` 的 `root_alias` 同模式：
      `uploads` 对应 `backend-service/data/uploads`，所以夹具必须写在 `data/<alias>/` 下。
2. `services/pv_projects/facts.py`
   —— 从真实 CSV/Parquet **算出**覆盖事实（行数 / 日期跨度 / 离散日期 / 设备数 / 采样完整率 /
      标签分布 / 标签粒度），并据此判定 `sufficient_coverage`。
   —— 这是 readiness 能给出 `ready` 的唯一开关：本次改动前该字段由客户端传入、后端从不计算。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

import pytest

from services.pv_projects import facts as facts_mod
from services.pv_projects import source_resolver as src

MAPPING = {"time_col": "time", "device_col": "device_id", "value_col": "value"}


@contextmanager
def temp_sources() -> Iterator[str]:
    """把数据来源根重定向到临时目录（不碰真实 data/）。"""
    tmp = tempfile.mkdtemp(prefix="pvsrc_")
    src.set_source_base(tmp)
    try:
        yield tmp
    finally:
        src.set_source_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _src(tmp: str, ref: str) -> str:
    """把 alias 形式引用映射成临时目录里的真实路径（alias → data/<alias>）。

    真实布局是 `backend-service/data/uploads/...`，因此应用层引用写 `uploads/...`。
    """
    alias, _, rest = ref.partition("/")
    return os.path.join(tmp, "data", alias, *[p for p in rest.split("/") if p])


def _write_csv(path: str, *, devices: int = 3, dates: int = 5, per_day: int = 24,
               with_label: bool = False, label_col: str = "custom_label_id") -> None:
    """写一份确定性 CSV：devices × dates × per_day 行，间隔 1 小时。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = ["site_id", "device_id", "branch_id", "time", "value"]
    if with_label:
        header.append(label_col)
    lines = [",".join(header)]
    for d in range(devices):
        for day in range(dates):
            for h in range(per_day):
                row = [
                    "site-1",
                    f"dev-{d}",
                    "1",
                    f"2026-01-{day + 1:02d} {h:02d}:00:00",
                    f"{10 + d + h * 0.1:.3f}",
                ]
                if with_label:
                    # 每设备日一个标签 → 应被判为 device_day 粒度
                    row.append(str((d + day) % 4))
                lines.append(",".join(row))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# 1. 来源解析：安全边界
# ---------------------------------------------------------------------------

def test_resolve_accepts_relative_ref_under_source_root() -> None:
    with temp_sources() as tmp:
        _write_csv(_src(tmp, "uploads/a.csv"))
        p = src.resolve_source_ref("uploads/a.csv")
        assert os.path.isfile(p)
        assert str(p).replace("\\", "/").endswith("data/uploads/a.csv")


def test_resolve_rejects_traversal_and_absolute_and_uri() -> None:
    with temp_sources():
        for bad in ("../secret.csv", "uploads/../../x.csv", "/etc/passwd",
                    "C:\\Windows\\x.csv", "\\\\server\\share\\x.csv",
                    "s3://bucket/x.csv"):
            with pytest.raises(Exception) as ei:
                src.resolve_source_ref(bad)
            assert getattr(ei.value, "code", None), f"{bad!r} 必须以带 code 的错误被拒"


def test_resolve_rejects_unsupported_extension_and_missing_file() -> None:
    with temp_sources() as tmp:
        _write_csv(_src(tmp, "uploads/a.csv"))
        with pytest.raises(Exception) as ei:
            src.resolve_source_ref("uploads/a.txt")
        assert getattr(ei.value, "code", None) in {"unsupported_extension", "source_not_found"}

        with pytest.raises(Exception) as ei2:
            src.resolve_source_ref("uploads/missing.csv")
        assert getattr(ei2.value, "code", None) == "source_not_found"


def test_resolve_rejects_symlink() -> None:
    with temp_sources() as tmp:
        real = _src(tmp, "uploads/real.csv")
        _write_csv(real)
        link = _src(tmp, "uploads/link.csv")
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError):
            pytest.skip("本环境不支持创建符号链接（Windows 需开发者模式/管理员）")
        with pytest.raises(Exception) as ei:
            src.resolve_source_ref("uploads/link.csv")
        assert getattr(ei.value, "code", None) == "symlink_forbidden"


# ---------------------------------------------------------------------------
# 2. 来源发现：回答"现在有哪些可挂载的数据"
# ---------------------------------------------------------------------------

def test_discover_lists_only_supported_files_under_roots() -> None:
    with temp_sources() as tmp:
        _write_csv(_src(tmp, "uploads/a.csv"))
        _write_csv(_src(tmp, "demo/b.csv"))
        _write_csv(_src(tmp, "uploads/sub/c.csv"))
        # 非支持扩展名不得进入清单
        os.makedirs(os.path.dirname(_src(tmp, "uploads/note.txt")), exist_ok=True)
        with open(_src(tmp, "uploads/note.txt"), "w", encoding="utf-8") as fh:
            fh.write("ignore me")

        found = src.discover_sources()
        refs = sorted(item["source_ref"] for item in found)
        assert refs == ["demo/b.csv", "uploads/a.csv", "uploads/sub/c.csv"]
        first = found[0]
        for key in ("source_ref", "root_alias", "size_bytes", "extension"):
            assert key in first, f"缺少字段 {key}"


def test_discovered_refs_round_trip_through_resolve() -> None:
    """发现产出的引用必须能直接喂给解析器（否则前端选中后会立刻失败）。"""
    with temp_sources() as tmp:
        _write_csv(_src(tmp, "uploads/a.csv"))
        _write_csv(_src(tmp, "demo/b.csv"))
        found = src.discover_sources()
        assert found, "夹具应至少发现一个来源"
        for item in found:
            p = src.resolve_source_ref(item["source_ref"])
            assert os.path.isfile(p)


# ---------------------------------------------------------------------------
# 3. 真实 facts 计算
# ---------------------------------------------------------------------------

def test_computes_row_date_device_and_sampling_facts() -> None:
    with temp_sources() as tmp:
        _write_csv(_src(tmp, "uploads/a.csv"), devices=3, dates=5, per_day=24)
        f = facts_mod.compute_dataset_facts("uploads/a.csv", mapping=MAPPING)

        assert f["row_count"] == 3 * 5 * 24
        assert f["distinct_dates"] == 5
        assert f["date_span_days"] == 5
        assert f["date_coverage_ratio"] == 1.0
        assert f["device_count"] == 3
        # 每小时一个点 → 24 点/设备日，完整率 1.0
        assert f["sampling_interval_seconds"] == 3600
        assert f["sampling_completeness"] == pytest.approx(1.0, abs=0.01)
        assert f["value_null_ratio"] == 0.0
        assert f["facts_source"] == "computed_from_file"
        assert f["source_extension"] == ".csv"


def test_date_coverage_ratio_detects_gaps() -> None:
    """5 个离散日期却跨 9 天 → 覆盖率 < 1，不能被"行数多"掩盖。"""
    with temp_sources() as tmp:
        p = _src(tmp, "uploads/gap.csv")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        lines = ["device_id,time,value"]
        for day in (1, 3, 5, 7, 9):
            for h in range(24):
                lines.append(f"dev-0,2026-01-{day:02d} {h:02d}:00:00,1.0")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write("\n".join(lines) + "\n")

        f = facts_mod.compute_dataset_facts("uploads/gap.csv", mapping=MAPPING)
        assert f["distinct_dates"] == 5
        assert f["date_span_days"] == 9
        assert f["date_coverage_ratio"] == pytest.approx(5 / 9, abs=0.01)
        assert f["sufficient_coverage"] is False
        assert "date_coverage_ratio" in f["coverage_gaps"]


def test_sufficient_coverage_rule_is_explicit_and_testable() -> None:
    """覆盖判定必须由命名阈值算出，且阈值随 facts 一起返回（可解释）。"""
    with temp_sources() as tmp:
        assert facts_mod.COVERAGE_THRESHOLDS["min_date_coverage_ratio"] > 0
        _write_csv(_src(tmp, "uploads/ok.csv"), devices=3, dates=5, per_day=24)
        f = facts_mod.compute_dataset_facts("uploads/ok.csv", mapping=MAPPING)
        assert f["sufficient_coverage"] is True
        assert f["coverage_gaps"] == []
        assert f["coverage_thresholds"] == facts_mod.COVERAGE_THRESHOLDS

        # 单设备 → 设备数不足
        _write_csv(_src(tmp, "uploads/one.csv"), devices=1, dates=5, per_day=24)
        f1 = facts_mod.compute_dataset_facts("uploads/one.csv", mapping=MAPPING)
        assert f1["sufficient_coverage"] is False
        assert "device_count" in f1["coverage_gaps"]


def test_label_distribution_and_granularity_detected() -> None:
    with temp_sources() as tmp:
        _write_csv(_src(tmp, "uploads/lab.csv"), devices=2, dates=3, per_day=24, with_label=True)
        f = facts_mod.compute_dataset_facts(
            "uploads/lab.csv",
            mapping={**MAPPING, "label_col": "custom_label_id"},
            label_policy={"granularity": "device_day"},
        )
        assert sum(f["label_distribution"].values()) == f["row_count"]
        # 每设备日单一标签 → device_day
        assert f["label_granularity_detected"] == "device_day"
        assert f["declared_label_granularity"] == "device_day"


def test_no_label_column_reports_unknown_granularity() -> None:
    with temp_sources() as tmp:
        _write_csv(_src(tmp, "uploads/nolabel.csv"))
        f = facts_mod.compute_dataset_facts("uploads/nolabel.csv", mapping=MAPPING)
        assert f["label_distribution"] == {}
        assert f["label_granularity_detected"] == "unknown"


def test_missing_required_mapping_is_rejected() -> None:
    with temp_sources() as tmp:
        _write_csv(_src(tmp, "uploads/a.csv"))
        with pytest.raises(Exception) as ei:
            facts_mod.compute_dataset_facts("uploads/a.csv", mapping={"time_col": "time"})
        assert getattr(ei.value, "code", None) == "incomplete_mapping"


def test_mapping_column_not_present_in_file_is_rejected() -> None:
    with temp_sources() as tmp:
        _write_csv(_src(tmp, "uploads/a.csv"))
        with pytest.raises(Exception) as ei:
            facts_mod.compute_dataset_facts(
                "uploads/a.csv",
                mapping={"time_col": "no_such_time", "device_col": "device_id", "value_col": "value"},
            )
        assert getattr(ei.value, "code", None) == "mapping_column_missing"


def test_sampling_completeness_measures_within_device_day_not_staggered_rows() -> None:
    """采样完整率度量"设备日内缺不缺"，不把"设备交错出现在不同日期"误判为残缺。

    构造：3 个设备各自只覆盖**自己那一天**（完整 24 点），离散日期合计 3 天。
    行数为 3×24=72，若用 `行数/(设备数×日期数×每日点数)` 会得到 72/(3×3×24)=0.33；
    按设备日看则是满的 → 1.0。
    """
    with temp_sources() as tmp:
        p = _src(tmp, "uploads/staggered.csv")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        lines = ["device_id,time,value"]
        for d in range(3):
            for h in range(24):
                lines.append(f"dev-{d},2026-01-{d + 1:02d} {h:02d}:00:00,1.0")
        with open(p, "w", encoding="utf-8", newline="") as fh:
            fh.write("\n".join(lines) + "\n")

        f = facts_mod.compute_dataset_facts("uploads/staggered.csv", mapping=MAPPING)
        assert f["device_count"] == 3
        assert f["distinct_dates"] == 3
        assert f["sampling_completeness"] == pytest.approx(1.0, abs=0.01)
        assert "sampling_completeness" not in f["coverage_gaps"]


def test_parquet_source_is_supported() -> None:
    pd = pytest.importorskip("pandas")
    with temp_sources() as tmp:
        p = _src(tmp, "benchmark_raw/x.parquet")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        rows = []
        for d in range(2):
            for day in range(3):
                for h in range(24):
                    rows.append({"device_id": f"dev-{d}",
                                 "time": f"2026-01-{day + 1:02d} {h:02d}:00:00",
                                 "value": 1.0})
        pd.DataFrame(rows).to_parquet(p, index=False)

        f = facts_mod.compute_dataset_facts("benchmark_raw/x.parquet", mapping=MAPPING)
        assert f["row_count"] == 2 * 3 * 24
        assert f["device_count"] == 2
        assert f["source_extension"] == ".parquet"


# @AI_GENERATED: end
