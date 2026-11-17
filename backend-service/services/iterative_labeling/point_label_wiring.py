# -*- coding: utf-8 -*-
"""标签 API 接线：整日裁决 → DayLabelService，自由框选 → PointLabelService。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.day_label_service import DayLabelService
from services.iterative_labeling.point_label_service import PointLabelService
from services.iterative_labeling.sample_builder import SampleStrategy, build_samples
from services.iterative_labeling.sample_id import is_sample_id, parse_sample_id

logger = logging.getLogger(__name__)

SAMPLING_SECONDS = 300
_VALID_GROUND_TRUTH = frozenset({"confirm", "correct", "new_label"})


def _align_grid(ts: datetime) -> datetime:
    ts = ts.replace(microsecond=0)
    seconds = ts.hour * 3600 + ts.minute * 60 + ts.second
    rem = seconds % SAMPLING_SECONDS
    if rem:
        ts = ts - timedelta(seconds=rem)
    return ts


def resolve_sample_bounds(
    unit: Dict[str, Any],
    pv_repo: PVFaultRepository,
    *,
    split_mode: str = "by_day",
) -> Tuple[str, str, str, datetime, datetime]:
    """从审核单元解析设备三元组与样本半开区间 [t_start, t_end)。"""
    unit_key = str(unit.get("unit_key") or "").strip()
    sample_id = unit_key if is_sample_id(unit_key) else str(unit.get("time_window") or "").strip()
    if not is_sample_id(sample_id):
        raise ValueError(f"unit_key 不是 sample_id，无法落点标签: {unit_key!r}")

    parsed = parse_sample_id(sample_id)
    site_id = str(unit.get("site_id") or "")
    device_id = str(unit.get("device_id") or "")
    branch_id = str(unit.get("branch_id") or "1")
    if not site_id or not device_id:
        raise ValueError("审核单元缺少 site_id/device_id")

    day_start = parsed["t_start"].replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=2)
    times = pv_repo.query_sample_times(site_id, device_id, branch_id, day_start, day_end)
    if not times:
        raise ValueError(f"设备 ({site_id},{device_id},{branch_id}) 无测量数据")

    rows = pd.DataFrame({
        "time": times,
        "label_id": 0,
        "source": "placeholder",
        "op_id": "placeholder",
        "site_id": site_id,
        "device_id": device_id,
        "branch_id": branch_id,
    })
    strategy = SampleStrategy(split_mode=split_mode, min_points=1)
    samples, _ = build_samples(rows, strategy, namespace=parsed["namespace"])
    matched = next((s for s in samples if s.sample_id == sample_id), None)
    if matched is None:
        raise ValueError(
            f"sample_id 未匹配到真实测量样本，禁止猜测整日边界: {sample_id}"
        )

    sub = rows.iloc[list(matched.row_indices)]
    t_start = _align_grid(pd.to_datetime(sub["time"].min()).to_pydatetime())
    t_end = _align_grid(pd.to_datetime(sub["time"].max()).to_pydatetime()) + timedelta(seconds=SAMPLING_SECONDS)
    return site_id, device_id, branch_id, t_start, t_end


def submit_review_verdict_as_day_label(
    service: DayLabelService,
    pv_repo: PVFaultRepository,
    *,
    review_id: str,
    unit: Dict[str, Any],
    verdict: Dict[str, Any],
    split_mode: str = "by_day",
) -> Optional[Dict[str, Any]]:
    """将整日 confirm/correct/new_label 裁决写入独立天标签账本；skip 不写。"""
    action = str(verdict.get("action_type") or "")
    if action not in _VALID_GROUND_TRUTH:
        return None
    if verdict.get("verdict_label") is None:
        raise ValueError("有效裁决缺少 verdict_label")

    site_id, device_id, branch_id, t_start, _ = resolve_sample_bounds(
        unit, pv_repo, split_mode=split_mode,
    )
    day_start = t_start.replace(hour=0, minute=0, second=0, microsecond=0)
    return service.submit_op(
        site_id=site_id,
        device_id=device_id,
        branch_id=branch_id,
        t_start=day_start,
        t_end=day_start + timedelta(days=1),
        label_id=int(verdict["verdict_label"]),
        source="human_day",
        reviewer=str(verdict.get("reviewer") or "operator"),
        source_ref=review_id,
    )


def submit_freeform_as_point_label(
    service: PointLabelService,
    *,
    review_id: str,
    site_id: str,
    device_id: str,
    branch_id: str,
    t_start: datetime,
    t_end: datetime,
    label_id: int,
    reviewer: str,
    rest_of_day_policy: str = "normal",
) -> Dict[str, Any]:
    """自由框选 → human_range + K4 伴生；边界必须由调用方显式对齐 5 分钟栅格。"""
    if not (t_start < t_end):
        raise ValueError("t_start 必须早于 t_end")
    return service.submit_op(
        site_id=site_id,
        device_id=device_id,
        branch_id=branch_id,
        t_start=t_start,
        t_end=t_end,
        label_id=label_id,
        source="human_range",
        reviewer=reviewer,
        source_ref=review_id,
        rest_of_day_policy=rest_of_day_policy,
    )
