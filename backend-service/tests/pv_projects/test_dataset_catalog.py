# @AI_GENERATED
"""平台级数据集目录的 RED 基线（数据集切片第 2b 步）。

要固定的语义：

**先做质量检测 → 发布成不可变条目 → 新建项目时直接选。** 条目自带「适用路径」，
适用性由**真实 facts + 各路径真值口径**推出，不是人工拍脑袋：

- 标签粒度必须落在该路径的 `truth_granularity` 内（设备日标签不能当 pv_point 的逐点真值）；
- 覆盖事实必须足够（`sufficient_coverage`）。

首批条目 = 三条路径各自的**累计训练数据集**（`data/slot_datasets/<slot>/snapshots/`
下的冻结快照），这是用户明确要求的起点；后续新数据集再增量检测 + 发布。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

import pytest

pd = pytest.importorskip("pandas")

from services.pv_projects import catalog as cat  # noqa: E402
from services.pv_projects import repositories as repo  # noqa: E402
from services.pv_projects import source_resolver as src  # noqa: E402

MAPPING = {"time_col": "time", "device_col": "device_id", "value_col": "value",
           "label_col": "label"}


@contextmanager
def temp_env() -> Iterator[str]:
    tmp = tempfile.mkdtemp(prefix="pvcatalog_")
    repo.set_storage_base(tmp)
    src.set_source_base(tmp)
    try:
        yield tmp
    finally:
        repo.set_storage_base(None)
        src.set_source_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _snapshot(tmp: str, slot: str, rows: int, *, device: str = "dev-0",
              label: str = "normal", ext: str = ".csv") -> str:
    """在 data/slot_datasets/<slot>/snapshots/ 下写一个冻结快照。"""
    d = os.path.join(tmp, "data", "slot_datasets", slot, "snapshots")
    os.makedirs(d, exist_ok=True)
    data = []
    for i in range(rows):
        day = i // 24 + 1
        h = i % 24
        data.append({"time": f"2026-01-{day:02d} {h:02d}:00:00",
                     "site_id": "s1", "device_id": device,
                     "branch_id": "1", "value": 1.0, "i_cal": 0.9,
                     "label": label})
    df = pd.DataFrame(data)
    if ext == ".parquet":
        p = os.path.join(d, f"snap-{slot}-v1.parquet")
        df.to_parquet(p, index=False)
    else:
        p = os.path.join(d, f"snap-{slot}-v1.csv")
        df.to_csv(p, index=False)
    return f"slot_datasets/{slot}/snapshots/{os.path.basename(p)}"


# ---------------------------------------------------------------------------
# 1. 发现三条路径的累计训练数据集
# ---------------------------------------------------------------------------

def test_discovers_path_cumulative_snapshots() -> None:
    with temp_env() as tmp:
        _snapshot(tmp, "pv_day", 48, device="dev-day")
        _snapshot(tmp, "pv_point", 24, device="dev-point")
        _snapshot(tmp, "pv_tsc", 24, device="dev-tsc", ext=".parquet")

        found = cat.discover_path_cumulative_datasets()
        by_slot = {d["origin_slot"]: d for d in found}
        assert set(by_slot) == {"pv_day", "pv_point", "pv_tsc"}
        for slot, item in by_slot.items():
            assert item["dataset_ref"] == f"slot_datasets/{slot}/snapshots/snap-{slot}-v1" + (
                ".parquet" if slot == "pv_tsc" else ".csv")
            assert item["origin"] == "path_cumulative_snapshot"


def test_discovers_latest_snapshot_when_several_exist() -> None:
    """同一路径有多个快照时，按**文件名降序**取第一个（确定性规则，不依赖 mtime）。"""
    with temp_env() as tmp:
        d = os.path.join(tmp, "data", "slot_datasets", "pv_day", "snapshots")
        os.makedirs(d, exist_ok=True)
        for name in ("snap-pv_day-20260827-034105-f21fda.csv",
                     "snap-pv_day-20260901-120000-abcd.csv"):
            pd.DataFrame([{"time": "2026-01-01 00:00:00", "device_id": "d1", "value": 1.0}]).to_csv(
                os.path.join(d, name), index=False)
        found = cat.discover_path_cumulative_datasets()
        refs = [f["dataset_ref"] for f in found if f["origin_slot"] == "pv_day"]
        assert refs == ["slot_datasets/pv_day/snapshots/snap-pv_day-20260901-120000-abcd.csv"]


# ---------------------------------------------------------------------------
# 2. 检测：facts + 适用路径
# ---------------------------------------------------------------------------

def test_inspect_returns_facts_and_applicable_paths() -> None:
    with temp_env() as tmp:
        ref = _snapshot(tmp, "pv_day", 72)  # 3 天 × 24 点，单设备
        draft = cat.inspect_dataset(ref, mapping=MAPPING, label_policy={"granularity": "device_day"})

        assert draft["facts"]["row_count"] == 72
        assert draft["facts"]["facts_source"] == "computed_from_file"
        ap = draft["applicable_paths"]
        assert set(ap) == {"pv_day", "pv_point", "pv_tsc"}
        # 路径累计冻结快照是路径资产：即使 device_day 真值口径也能被 TSC 理解，
        # 它仍只归 pv_day，不跨路径复用。
        assert ap["pv_day"]["applicable"] is True
        assert ap["pv_tsc"]["applicable"] is False
        assert ap["pv_point"]["applicable"] is False
        assert "归属 pv_day" in ap["pv_tsc"]["reason"]
        assert "归属 pv_day" in ap["pv_point"]["reason"]
        assert draft["origin_slot"] == "pv_day"


def test_coverage_gaps_are_reported_separately_from_applicability() -> None:
    """覆盖质量与路径所有权分离。

    路径累计快照无论覆盖是否充足，都只归自己的 origin_slot；覆盖不足仍单独记录在
    coverage，不把“仅实验”误写成“跨路径可用”。
    """
    with temp_env() as tmp:
        ref = _snapshot(tmp, "pv_day", 24)  # 单设备 1 天 → 覆盖不足
        draft = cat.inspect_dataset(ref, mapping=MAPPING, label_policy={"granularity": "device_day"})

        cov = draft["coverage"]
        assert cov["sufficient"] is False
        assert "device_count" in cov["gaps"]
        assert cov["hint"] == "experiment_only"

        # 路径所有权不受覆盖门槛影响：pv_day 保持适用，pv_point 仍被拒绝。
        assert draft["applicable_paths"]["pv_day"]["applicable"] is True
        assert draft["applicable_paths"]["pv_point"]["applicable"] is False
        assert "归属 pv_day" in draft["applicable_paths"]["pv_point"]["reason"]


# ---------------------------------------------------------------------------
# 3. 发布：不可变 + 幂等
# ---------------------------------------------------------------------------

def test_publish_creates_immutable_entry_and_is_idempotent() -> None:
    with temp_env() as tmp:
        ref = _snapshot(tmp, "pv_day", 72)
        draft = cat.inspect_dataset(ref, mapping=MAPPING, label_policy={"granularity": "device_day"})

        first = cat.publish_dataset(draft)
        assert first["entry_id"].startswith("dsc-")
        assert first["immutable"] is True
        assert first["idempotent_hit"] is False

        again = cat.publish_dataset(draft)
        assert again["entry_id"] == first["entry_id"]
        assert again["idempotent_hit"] is True

        entries = cat.list_catalog()
        assert len(entries) == 1
        assert cat.get_catalog_entry(first["entry_id"])["dataset_ref"] == ref


def test_publish_carries_applicable_paths_and_facts() -> None:
    with temp_env() as tmp:
        ref = _snapshot(tmp, "pv_tsc", 72, ext=".parquet")
        draft = cat.inspect_dataset(ref, mapping=MAPPING, label_policy={"granularity": "device_day"})
        entry = cat.publish_dataset(draft)
        assert entry["applicable_paths"]["pv_tsc"]["applicable"] is True
        assert entry["applicable_paths"]["pv_day"]["applicable"] is False
        assert entry["applicable_paths"]["pv_point"]["applicable"] is False
        assert entry["facts"]["row_count"] == 72
        assert entry["shard_count"] == 1
        assert entry["origin_slot"] == "pv_tsc"


def test_catalog_is_platform_level_not_per_project() -> None:
    """目录是平台级的：换项目/不传 project 也能读到同一份。"""
    with temp_env() as tmp:
        ref = _snapshot(tmp, "pv_day", 72)
        cat.publish_dataset(cat.inspect_dataset(ref, mapping=MAPPING,
                                                label_policy={"granularity": "device_day"}))
        # 平台级存储路径不含"项目分区段" projects/<pid>/
        p = cat.catalog_path().as_posix()
        assert "/projects/" not in p, p
        assert p.endswith("data/pv_projects/dataset_catalog.json"), p
        assert cat.list_catalog()


# @AI_GENERATED: end
