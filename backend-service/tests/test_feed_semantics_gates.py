# -*- coding: utf-8 -*-
"""回放链路的到达语义门禁 —— Wave 2 红灯测试。

**本文件在修复前必须红**，且红的原因来自被测那一层（``loop_demo.feed_next_day``
的真实行为），不是 mock 来的假红。三条断言对应计划里的 N1 / N2 / N4：

  1. 点路径按点推进：一次 feed 只前进一个测点（当前整天整块追加）
  2. 日路径等整日到齐：未达 ``OCCUPANCY_READY`` 的日子不得计入 ``fed_days``
     （当前无条件 ``fed.append(day)``）
  3. 日路径超期出口：连续超过 ``HOLD_DAYS`` 仍未到齐的日子应报
     ``expired_incomplete``（当前永远当作喂成功）

修复后这三条转绿即视为 N1/N2/N4 收口。
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from services.slot_datasets import loop_demo as ld
from services.slot_datasets.observability_ledger import (
    HOLD_DAYS,
    OCCUPANCY_READY,
)

DAY = "2024-06-03"
DEVICES = (("demo_site", "inv_a", "1"), ("demo_site", "inv_b", "1"))
_LOW_POINTS = 5  # 每设备 5 点 → 合计 10 点，远低于 OCCUPANCY_READY


def _loop_dir(root, slot):
    return root / "data" / "slot_datasets" / slot / "loop_demo"


def _write_unlabeled(root, slot, *, points_per_device, day=DAY, devices=DEVICES):
    """手写一个可控的喂数源：只含一天、点数为参数（便于造「未到齐」场景）。"""
    d = _loop_dir(root, slot)
    d.mkdir(parents=True, exist_ok=True)
    rows = []
    for site, device, branch in devices:
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
                }
            )
    pd.DataFrame(rows).to_parquet(d / "unlabeled.parquet", index=False)
    (d / "feed_cursor.json").write_text(
        json.dumps(
            {
                "slot": slot,
                "days": [day],
                "fed_days": [],
                "last_fed_day": None,
                "exhausted": False,
                "mode": "test",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return d


def _arrived_rows(root, slot):
    p = _loop_dir(root, slot) / "arrived.parquet"
    if not p.is_file():
        return 0
    return len(pd.read_parquet(p))


def test_point_path_feed_advances_one_point_at_a_time(tmp_path):
    """点路径：一次推进 = 一个测点（当前整天整块追加，期望红）。"""
    _write_unlabeled(tmp_path, "pv_point", points_per_device=10)

    result = ld.feed_next_day("pv_point", backend_dir=tmp_path, skip_ensure=True)

    rows = _arrived_rows(tmp_path, "pv_point")
    assert rows == 1, (
        f"点路径一次推进必须只前进一个测点，实际落盘 {rows} 行"
        f"（源里同一天有 {10 * len(DEVICES)} 点）——说明粒度仍是整天"
    )
    assert result.get("granularity") == "point"


def test_day_path_does_not_count_day_before_occupancy_ready(tmp_path):
    """日路径：未到齐不得计入 fed_days（当前无条件 append，期望红）。"""
    _write_unlabeled(tmp_path, "pv_day", points_per_device=_LOW_POINTS)
    total_points = _LOW_POINTS * len(DEVICES)

    result = ld.feed_next_day("pv_day", backend_dir=tmp_path, skip_ensure=True)

    cursor = result.get("cursor") or {}
    assert DAY not in list(cursor.get("fed_days") or []), (
        f"当天只有 {total_points} 点（门槛 {OCCUPANCY_READY}），不应计入 fed_days"
    )
    assert result.get("skipped_reason"), "未到齐的日子必须给出可解释的 skipped_reason"


def test_day_path_expires_after_hold_days(tmp_path):
    """日路径：连续未到齐超过 HOLD_DAYS 后应报 expired_incomplete。"""
    _write_unlabeled(tmp_path, "pv_day", points_per_device=_LOW_POINTS)

    statuses = []
    for _ in range(HOLD_DAYS + 1):
        result = ld.feed_next_day("pv_day", backend_dir=tmp_path, skip_ensure=True)
        statuses.append(str(result.get("status") or result.get("skipped_reason") or "").lower())

    assert any("expired" in s for s in statuses), (
        f"连续 {HOLD_DAYS + 1} 轮未到齐必须报 expired_incomplete，实际状态序列 {statuses}"
    )


def test_arrived_is_not_written_by_day_slot_before_gate_passes(tmp_path):
    """日路径未过门禁时不得把样本写进 arrived（否则水位与样本会脱节）。"""
    _write_unlabeled(tmp_path, "pv_day", points_per_device=_LOW_POINTS)
    ld.feed_next_day("pv_day", backend_dir=tmp_path, skip_ensure=True)
    assert _arrived_rows(tmp_path, "pv_day") == 0, (
        "未到齐的日子不应落 arrived —— 落盘与计入 fed 必须同进同退"
    )


def test_tsc_slot_is_reachable_by_feed_path(tmp_path):
    """TSC 也必须有回放通道（当前 loop_demo._ALLOWED 直接拒绝，期望红）。

    红灯形式：断言 feed_next_day("pv_tsc") 能正常返回而不是抛 SlotDatasetError。
    T8 落地独立 demo 通道后此条转绿。
    """
    _write_unlabeled(tmp_path, "pv_tsc", points_per_device=10)

    result = ld.feed_next_day("pv_tsc", backend_dir=tmp_path, skip_ensure=True)

    assert result["slot"] == "pv_tsc"
    assert "fed_day" in result
