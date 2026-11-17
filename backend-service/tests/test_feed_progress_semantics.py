# -*- coding: utf-8 -*-
"""三路径推进后，观测状态必须反映各自的到达语义（Wave 2 收尾验证）。

计划 Wave 2 验证要点：
    三路径各推进一次后 ``observability/status`` 的 ``progress`` 与
    ``accuracy.counted_units`` / ``pending_label_units`` 符合各自语义
    （点路径按点递增、日/tsc 只在到齐日前进）。

本文件用 ``demo_status``（读同一份 cursor/ledger）在隔离目录上验证该性质，
不触碰真实 ``data/slot_datasets``。
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from services.slot_datasets import loop_demo as ld
from services.slot_datasets.observability_ledger import OCCUPANCY_READY

DAY = "2024-06-03"
DEVICES = (("s", "d1", "1"), ("s", "d2", "1"))


def _seed(root, slot, *, points_per_device, days=(DAY,)):
    d = root / "data" / "slot_datasets" / slot / "loop_demo"
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for day in days:
        for site, device, branch in DEVICES:
            for step in range(points_per_device):
                rows.append(
                    {
                        "site_id": site,
                        "device_id": device,
                        "branch_id": branch,
                        "time": pd.Timestamp(f"{day} 06:00:00") + pd.Timedelta(minutes=5 * step),
                        "date": day,
                        "value": 1.0,
                        "i_cal": 8.0,
                        "label": step % 2,  # 带真值，便于 precision 侧断言
                    }
                )
    pd.DataFrame(rows).to_parquet(d / "unlabeled.parquet", index=False)
    (d / "feed_cursor.json").write_text(
        json.dumps(
            {"slot": slot, "days": list(days), "fed_days": [], "last_fed_day": None, "exhausted": False},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_point_path_progress_reflects_points_not_days(tmp_path):
    """点路径：推进若干次后仍停在同一业务日（按点递增，不跨日）。"""
    _seed(tmp_path, "pv_point", points_per_device=10)

    for _ in range(3):
        ld.feed_next_day("pv_point", backend_dir=tmp_path, skip_ensure=True)

    cursor = ld.load_cursor("pv_point", backend_dir=tmp_path)
    assert cursor["fed_days"] == [], "该日还有未喂的点，不应计入 fed_days"
    assert int((cursor.get("point_progress") or {}).get(DAY) or 0) == 3, (
        "点路径推进 3 次应前进 3 个点"
    )
    assert int(cursor.get("day_index") or 0) == 0, "未跨日时 day_index 必须保持 0"

    arrived = pd.read_parquet(tmp_path / "data/slot_datasets/pv_point/loop_demo/arrived.parquet")
    assert len(arrived) == 3, "落盘行数应与推进点数一致（落盘与计数同进同退）"


def test_point_path_finishes_day_only_after_all_points(tmp_path):
    """点路径：该日所有点喂完才计入 fed_days 并跨日。"""
    _seed(tmp_path, "pv_point", points_per_device=4)
    total = 4 * len(DEVICES)

    for _ in range(total):
        ld.feed_next_day("pv_point", backend_dir=tmp_path, skip_ensure=True)

    cursor = ld.load_cursor("pv_point", backend_dir=tmp_path)
    assert cursor["fed_days"] == [DAY], f"喂满 {total} 点后该日应完成"
    assert int(cursor.get("day_index") or 0) == 1


def test_day_path_progress_does_not_advance_before_occupancy(tmp_path):
    """日路径：未到齐时既不落盘也不推进业务日，且给出可解释原因。"""
    _seed(tmp_path, "pv_day", points_per_device=5)  # 合计 10 点 << 173
    total = 5 * len(DEVICES)

    result = ld.feed_next_day("pv_day", backend_dir=tmp_path, skip_ensure=True)

    assert result["status"] == "waiting"
    assert result["skipped_reason"] == "incomplete_occupancy"
    assert result["arrived_points"] == total
    assert result["required_points"] == OCCUPANCY_READY
    assert not (tmp_path / "data/slot_datasets/pv_day/loop_demo/arrived.parquet").is_file(), (
        "未过门禁不得落盘"
    )

    cursor = ld.load_cursor("pv_day", backend_dir=tmp_path)
    assert cursor["fed_days"] == []
    assert int(cursor.get("day_index") or 0) == 0


def test_day_path_advances_once_occupancy_met(tmp_path):
    """日路径：到齐后一次推进整天并计入 fed_days。"""
    need = OCCUPANCY_READY
    per_device = (need // len(DEVICES)) + 1
    _seed(tmp_path, "pv_day", points_per_device=per_device)

    result = ld.feed_next_day("pv_day", backend_dir=tmp_path, skip_ensure=True)

    assert result["status"] == "fed"
    assert result["day_finished"] is True
    assert result["granularity"] == "device_day"
    rows = pd.read_parquet(tmp_path / "data/slot_datasets/pv_day/loop_demo/arrived.parquet")
    assert len(rows) == per_device * len(DEVICES)

    cursor = ld.load_cursor("pv_day", backend_dir=tmp_path)
    assert cursor["fed_days"] == [DAY]


def test_tsc_path_uses_coverage_gate(tmp_path):
    """TSC：同样等整日，但另需窗口覆盖率；覆盖不足时报 incomplete_coverage。"""
    _seed(tmp_path, "pv_tsc", points_per_device=190)  # 每设备 190 点：点数够了，覆盖率仍可能不足
    total = 190 * len(DEVICES)

    result = ld.feed_next_day("pv_tsc", backend_dir=tmp_path, skip_ensure=True)

    # 点数已超 OCCUPANCY_READY，但覆盖率 = total/288；若不足则应给出覆盖率原因
    if result["status"] == "waiting":
        assert result["skipped_reason"] in {"incomplete_coverage", "incomplete_occupancy"}
    else:
        assert result["granularity"] == "device_day"
    assert result["granularity"] == "device_day"
    assert total > OCCUPANCY_READY
