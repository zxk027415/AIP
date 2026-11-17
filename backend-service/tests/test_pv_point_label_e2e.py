# -*- coding: utf-8 -*-
"""端到端：迁移 → 物化 → 快照（point_label 路径）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.daylight_window import DaylightWindowResolver
from services.iterative_labeling.sample_builder import SampleStrategy
from services.iterative_labeling.snapshot_builder import SnapshotBuilder

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent


def _find_parquet() -> Path | None:
    for rel in (
        "backend-service/datasets/pv_cumulative_labeled_merged.parquet",
        "fault-diag-algo-release-3.1/相关数据/pv_cumulative_labeled_merged.parquet",
        "pv_cumulative_labeled_merged.parquet",
    ):
        path = PROJECT / rel
        if path.exists():
            return path
    return None


def test_synthetic_device_snapshot_pipeline():
    """合成数据：submit_op → 物化 → 快照，验证 time_window 含 #。"""
    from services.iterative_labeling.point_label_service import PointLabelService
    from services.iterative_labeling.label_registry import LabelRegistryService

    adapter = DBAdapter(DBConfig())
    point_repo = PointLabelRepository(adapter)
    sample_repo = PVFaultRepository(adapter)
    service = PointLabelService(point_repo, sample_repo, LabelRegistryService(slot="pv_fault"))

    rows = sample_repo.query_training_samples()
    if not rows:
        pytest.skip("training_samples 为空")

    for op in point_repo.query_all_active_ops():
        if str(op.get("source_ref", "")).startswith("e2e-synthetic"):
            try:
                service.revoke_op(op["op_id"])
            except Exception:
                pass

    result = None
    for candidate in rows[:50]:
        site, device, branch = str(candidate.site_id), str(candidate.device_id), str(candidate.branch_id)
        day_start = candidate.time.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        op_id = PointLabelService._make_op_id(site, device, branch, day_start, day_end, 0, "day_label")
        existing = point_repo.query_op_by_id(op_id)
        if existing and existing.get("status") != "active":
            continue
        if existing and existing.get("status") == "active":
            result = {"op_id": op_id}
            break
        result = service.submit_op(
            site_id=site,
            device_id=device,
            branch_id=branch,
            t_start=day_start,
            t_end=day_end,
            label_id=0,
            source="day_label",
            reviewer=None,
            source_ref="e2e-synthetic",
        )
        break

    if result is None:
        pytest.skip("前 50 条采样日均已存在 revoked 同内容 op，无法插入")
    op_row = point_repo.query_op_by_id(result["op_id"])
    site = str(op_row["site_id"])
    device = str(op_row["device_id"])
    branch = str(op_row["branch_id"])
    assert result["op_id"]

    builder = SnapshotBuilder(point_repo, sample_repo)
    measurements = builder._load_measurements(site)
    if measurements.empty:
        pytest.skip("该站点无测量数据")

    resolver = DaylightWindowResolver()
    table = resolver.build_table(measurements)
    snapshot, meta = builder.build(
        SampleStrategy(split_mode="by_day", min_points=12, daylight_windows=table),
        measurements_df=measurements,
    )
    assert meta["label_snapshot_hash"]
    assert snapshot["time_window"].astype(str).str.contains("#").all()
    assert snapshot["group_key"].notna().all()

    service.revoke_op(result["op_id"])


@pytest.mark.skipif(_find_parquet() is None, reason="缺少 pv_cumulative_labeled_merged.parquet")
def test_snapshot_wudanghu_case_no_duplicate_times():
    """武当湖 04#/2020-05-08：新路径应消除同刻重复行。"""
    adapter = DBAdapter(DBConfig())
    point_repo = PointLabelRepository(adapter)
    sample_repo = PVFaultRepository(adapter)
    builder = SnapshotBuilder(point_repo, sample_repo)

    measurements = builder._load_measurements(None)
    if measurements.empty:
        pytest.skip("training_samples 为空")

    active = point_repo.query_all_active_ops()
    if not active:
        pytest.skip("point_labels 尚未迁移，跳过 E2E")

    resolver = DaylightWindowResolver()
    table = resolver.build_table(measurements)
    strategy = SampleStrategy(split_mode="by_day", min_points=12, daylight_windows=table)
    snapshot, _meta = builder.build(strategy, measurements_df=measurements)

    target = snapshot[
        (snapshot["site_id"].astype(str) == "武当湖")
        & (snapshot["device_id"].astype(str) == "04#箱变_汇流箱01")
        & (snapshot["branch_id"].astype(str) == "1")
        & (pd.to_datetime(snapshot["time"]).dt.date == datetime(2020, 5, 8).date())
    ]
    if target.empty:
        pytest.skip("未找到武当湖 04# 2020-05-08 数据")

    assert len(target) <= 288
    assert target["time"].duplicated().sum() == 0
    assert target["time_window"].astype(str).str.contains("#").all()


@pytest.mark.skipif(_find_parquet() is None, reason="缺少 parquet")
def test_split_mode_sample_counts_order_of_magnitude():
    adapter = DBAdapter(DBConfig())
    point_repo = PointLabelRepository(adapter)
    sample_repo = PVFaultRepository(adapter)
    builder = SnapshotBuilder(point_repo, sample_repo)
    if not point_repo.query_all_active_ops():
        pytest.skip("point_labels 尚未迁移")

    measurements = builder._load_measurements(None)
    resolver = DaylightWindowResolver()
    table = resolver.build_table(measurements)

    by_day, _ = builder.build(
        SampleStrategy(split_mode="by_day", daylight_windows=table),
        measurements_df=measurements,
    )
    by_dn, _ = builder.build(
        SampleStrategy(split_mode="by_day_night", daylight_windows=table),
        measurements_df=measurements,
    )
    assert by_day["time_window"].nunique() >= 1000
    assert by_dn["time_window"].nunique() >= 3000
    assert by_dn["time_window"].nunique() > by_day["time_window"].nunique()
