# -*- coding: utf-8 -*-
"""
services/iterative_labeling/label_materializer.py — 标签物化器

**职责**：把 `label_ops`（标注操作日志，可能重叠）算成 `point_labels`
（逐点生效标签，互不重叠）。取代旧方案的段裁剪算法——**没有任何区间差集
运算**，物化规则只有一句话：一个采样点被多条 active 操作覆盖时，取
`(priority DESC, created_at DESC, op_id DESC)` 排序后的第一条。

物化算法（design.md 组件 1，需求 4 第 1 条）：
1. 查该设备维度下 `status='active'` 且与 `[t_start, t_end)` 有交集的全部 `label_ops`。
2. 查该范围内 `training_samples` 的采样时刻集合（标签只能落在真实存在的采样点上）。
3. 对每个采样点，从覆盖它的 active 操作中按三级排序取第一条——保证结果对输入顺序无关。
4. 未被任何操作覆盖的点写 `label_id=NULL`（unknown）。
5. 按主键 upsert 进 `point_labels`；先删除范围内旧行再写，避免范围收缩后遗留过期点。

对应设计文档 `.kiro/specs/pv-fault-label-segment-redesign/design.md` 组件 1。
需求：4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
"""

# @AI_GENERATED
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository

logger = logging.getLogger(__name__)


class LabelMaterializer:
    """标签物化器。

    用法：
        materializer = LabelMaterializer(point_label_repo, pv_fault_repo)
        result = materializer.materialize("S1", "D1", "1", t_start, t_end)
    """

    def __init__(
        self,
        point_label_repo: PointLabelRepository,
        pv_fault_repo: PVFaultRepository,
    ) -> None:
        self._labels = point_label_repo
        self._samples = pv_fault_repo

    def materialize(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: datetime,
        t_end: datetime,
    ) -> Dict[str, int]:
        """重物化指定设备维度、指定时间范围的逐点标签。

        Returns:
            {"points_written": int, "points_unknown": int, "ops_considered": int}

        Requirements: 4.1, 4.3, 4.5, 4.7
        """
        ops = self._labels.query_active_ops(site_id, device_id, branch_id, t_start, t_end)
        sample_times = self._samples.query_sample_times(site_id, device_id, branch_id, t_start, t_end)

        if not sample_times:
            logger.debug(
                "materialize: 设备(%s,%s,%s) 范围[%s,%s) 无测量数据，无需物化",
                site_id, device_id, branch_id, t_start, t_end,
            )
            return {"points_written": 0, "points_unknown": 0, "ops_considered": len(ops)}

        rows, n_unknown = self._resolve_points(site_id, device_id, branch_id, sample_times, ops)

        # 先清空范围内旧行，再写入新结果（避免范围收缩后遗留过期点，需求 4.7）
        self._labels.delete_points_in_range(site_id, device_id, branch_id, t_start, t_end)
        written = self._labels.upsert_points(rows) if rows else 0

        logger.info(
            "materialize: 设备(%s,%s,%s) 范围[%s,%s) ops=%d points=%d unknown=%d",
            site_id, device_id, branch_id, t_start, t_end, len(ops), len(rows), n_unknown,
        )
        return {
            "points_written": len(rows),
            "points_unknown": n_unknown,
            "ops_considered": len(ops),
        }

    def verify(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: datetime,
        t_end: datetime,
    ) -> List[Dict[str, Any]]:
        """一致性校验：重算逐点标签并与库中现有 point_labels 比对，返回差异明细。

        不写库，纯只读比对，供运维独立运行。

        Returns:
            差异明细列表，每条含 {"time", "expected", "actual"}；无差异返回空列表。

        Requirements: 4.8
        """
        ops = self._labels.query_active_ops(site_id, device_id, branch_id, t_start, t_end)
        sample_times = self._samples.query_sample_times(site_id, device_id, branch_id, t_start, t_end)
        expected_rows, _ = self._resolve_points(site_id, device_id, branch_id, sample_times, ops)
        expected_by_time = {r["time"]: r["label_id"] for r in expected_rows}
        # 未被任何操作覆盖的点，期望值为 None（不在 expected_rows 中，因为 upsert_points
        # 只写有 op_id 的行；unknown 点在库中应表现为「不存在该主键行」或 label_id=NULL）
        expected_full = {t: expected_by_time.get(t) for t in sample_times}

        actual_rows = self._labels.query_points(site_id, device_id, branch_id, t_start, t_end)
        actual_by_time = {r["time"]: r["label_id"] for r in actual_rows}

        diffs: List[Dict[str, Any]] = []
        for t in sample_times:
            expected = expected_full.get(t)
            actual = actual_by_time.get(t)
            if expected != actual:
                diffs.append({"time": t, "expected": expected, "actual": actual})
        return diffs

    # ------------------------------------------------------------------
    # 内部：核心排序取最大逻辑
    # ------------------------------------------------------------------

    def _resolve_points(
        self,
        site_id: str,
        device_id: str,
        branch_id: str,
        sample_times: List[datetime],
        ops: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], int]:
        """核心物化逻辑：对每个采样点从覆盖它的 active 操作中取排序最优的一条。

        排序键 (priority DESC, created_at DESC, op_id DESC) 保证顺序无关性
        （需求 4.4）与同优先级同时刻的确定裁决（需求 4.6）。

        Returns:
            (待写入 point_labels 的行列表, unknown 点数)
        """
        if not ops:
            return [], len(sample_times)

        # 按排序键预排好，之后对每个点只需线性扫描找第一个覆盖它的操作
        sorted_ops = sorted(
            ops,
            key=lambda op: (op["priority"], op["created_at"], op["op_id"]),
            reverse=True,
        )

        rows: List[Dict[str, Any]] = []
        n_unknown = 0
        now = datetime.utcnow()

        for t in sample_times:
            winner = None
            for op in sorted_ops:
                if op["t_start"] <= t < op["t_end"]:
                    winner = op
                    break
            if winner is None:
                n_unknown += 1
                continue
            rows.append({
                "site_id": site_id,
                "device_id": device_id,
                "branch_id": branch_id,
                "time": t,
                "label_id": winner["label_id"],
                "source": winner["source"],
                "priority": winner["priority"],
                "op_id": winner["op_id"],
                "label_space_version": winner["label_space_version"],
                "updated_at": now,
            })
            if winner["label_id"] is None:
                n_unknown += 1

        return rows, n_unknown

# @AI_GENERATED: end
