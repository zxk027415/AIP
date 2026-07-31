# -*- coding: utf-8 -*-
"""
services/iterative_labeling/point_label_service.py — 逐点标签服务（标注唯一写入入口）

**职责**：受理所有标注操作，校验不变量，写 `label_ops`，触发 `LabelMaterializer`
重物化。所有写操作都是「校验 → 写操作 → 重物化」三步。

**K4「未框选即正常」**（需求 5 第 4~10 条）：人在图上框故障时只会框有问题的时段，
所以 `human_range` 打标默认额外写一条**伴生操作**（`human_day`、`label_id=0`、
覆盖该设备该自然日），靠 `priority` 规则自然让框内故障压过框外正常：

    框选 06:00~18:40 标故障1
      ├─ 操作A：human_range priority=100 [06:00,18:45) label=1
      └─ 操作B：human_day   priority=80  [当日00:00,次日00:00) label=0  parent_op_id=A
           ↓ 物化
      框内 → 故障1（A 的 100 胜）；当日其余 → 正常（B 的 80 胜，压过 day_label 的 10）

`op_scope` 严格限定为 `(site_id, device_id, branch_id, 框选起点所属自然日)`——实测
自由段输入源含 189 个设备、跨 5 个不连续自然日，不限定范围会误判为覆盖全文件。

**撤销联动**（需求 6 第 3 条）：撤 `human_range` 时按 `parent_op_id` 一并撤伴生
`human_day`，避免「问题时段撤了但『其余正常』还挂着」。

对应设计文档 `.kiro/specs/pv-fault-label-segment-redesign/design.md` 组件 2。
需求：3.1~3.3, 5.1~5.14, 6.1~6.8, 18.1~18.2, 19.x
"""

# @AI_GENERATED
from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.label_materializer import LabelMaterializer
from services.iterative_labeling.label_registry import LabelRegistryService

logger = logging.getLogger(__name__)

# source → priority 映射（需求 3 第 1 条）。由服务层强制，调用方不得显式指定 priority。
SOURCE_PRIORITY: Dict[str, int] = {
    "human_range": 100,   # 人工在图上框选的精确时段
    "human_day": 80,      # 人工对设备-天/时段单元的裁决（含 K4 伴生操作）
    "cluster": 50,        # 聚类批量命名后二次确认
    "day_label": 10,      # 历史天级批量标注
    "pseudo": 0,          # 高置信伪标签
}

# 采样栅格（秒）。边界必须对齐到该栅格。
SAMPLING_INTERVAL_SECONDS = 300

# 操作最大跨度（天），兜住源数据异常导致的无界长操作（需求 5 第 12 条）
DEFAULT_MAX_OP_SPAN_DAYS = 31

# 「正常」标签的固定编码（需求 18 第 3 条：label_id=0 恒为正常）
NORMAL_LABEL_ID = 0

# 设备维度写入串行化（需求 21.6）：DB 不支持 FOR UPDATE 时退化为进程内锁
_DEVICE_LOCKS: Dict[tuple, threading.RLock] = defaultdict(threading.RLock)


class PointLabelValidationError(ValueError):
    """标注操作校验失败。API 层应转成 HTTP 422。"""

    def __init__(self, message: str, detail: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.detail = detail or {}


class PointLabelService:
    """逐点标签服务 —— 标注的唯一写入入口。

    用法：
        service = PointLabelService(point_label_repo, pv_fault_repo, registry, slot="pv_fault")
        result = service.submit_op(
            site_id="S1", device_id="D1", branch_id="1",
            t_start=..., t_end=..., label_id=1,
            source="human_range", reviewer="zhangsan", source_ref="rev-x",
        )
    """

    def __init__(
        self,
        point_label_repo: PointLabelRepository,
        pv_fault_repo: PVFaultRepository,
        label_registry: Optional[LabelRegistryService] = None,
        slot: str = "pv_fault",
        max_op_span_days: int = DEFAULT_MAX_OP_SPAN_DAYS,
    ) -> None:
        self._labels = point_label_repo
        self._samples = pv_fault_repo
        # LabelRegistryService 的 slot 在构造时固定，get_current() 不接受参数
        self._registry = label_registry or LabelRegistryService(slot=slot)
        self._slot = slot
        self._max_op_span = timedelta(days=max_op_span_days)
        self._materializer = LabelMaterializer(point_label_repo, pv_fault_repo)

    # ------------------------------------------------------------------
    # 写入主入口
    # ------------------------------------------------------------------

    def submit_op(
        self,
        *,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: datetime,
        t_end: datetime,
        label_id: Optional[int],
        source: str,
        reviewer: Optional[str] = None,
        source_ref: Optional[str] = None,
        rest_of_day_policy: str = "normal",
        migration_batch_id: Optional[str] = None,
        priority: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """受理一次标注操作：校验 → 写 label_ops → 重物化。

        Args:
            rest_of_day_policy: 仅对 `source='human_range'` 生效，`normal`（默认，K4：
                当日其余时段判为正常）或 `untouched`（只写框选区间，不动其余）。
            priority: **不允许显式指定**，传入即报错（需求 3 第 3 条）。

        Returns:
            {"op_id", "companion_op_ids", "materialized"}

        Raises:
            PointLabelValidationError: 任一不变量校验失败。
        """
        # 双层串行化（需求 21.6、21.7）：进程内 RLock 挡同进程并发，
        # DB 顾问锁（MySQL GET_LOCK）挡跨进程/多 worker 并发。
        # 只有进程内锁在多进程部署下不足，故补 DB 级锁兜底。
        device_key = (site_id, device_id, branch_id)
        with _DEVICE_LOCKS[device_key], self._device_db_lock(site_id, device_id, branch_id):
            return self._submit_op_locked(
                site_id=site_id,
                device_id=device_id,
                branch_id=branch_id,
                t_start=t_start,
                t_end=t_end,
                label_id=label_id,
                source=source,
                reviewer=reviewer,
                source_ref=source_ref,
                rest_of_day_policy=rest_of_day_policy,
                migration_batch_id=migration_batch_id,
                priority=priority,
                created_at=created_at,
            )

    def _submit_op_locked(
        self,
        *,
        site_id: str,
        device_id: str,
        branch_id: str,
        t_start: datetime,
        t_end: datetime,
        label_id: Optional[int],
        source: str,
        reviewer: Optional[str] = None,
        source_ref: Optional[str] = None,
        rest_of_day_policy: str = "normal",
        migration_batch_id: Optional[str] = None,
        priority: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        if priority is not None:
            raise PointLabelValidationError(
                "priority 由 source 唯一推导，不允许显式指定",
                {"source": source, "given_priority": priority},
            )

        resolved_priority = self._resolve_priority(source)
        self._validate_boundaries(t_start, t_end)
        self._validate_human_source_fields(source, reviewer, source_ref)
        label_space_version = self._validate_label_id(label_id)

        if source == "human_range":
            self._check_human_range_overlap(site_id, device_id, branch_id, t_start, t_end)

        now = created_at or datetime.utcnow()
        main_op_id = self._make_op_id(site_id, device_id, branch_id, t_start, t_end, label_id, source)
        self._labels.insert_op({
            "op_id": main_op_id,
            "site_id": site_id, "device_id": device_id, "branch_id": branch_id,
            "t_start": t_start, "t_end": t_end, "label_id": label_id,
            "source": source, "priority": resolved_priority, "status": "active",
            "reviewer": reviewer, "source_ref": source_ref,
            "rest_of_day_policy": rest_of_day_policy if source == "human_range" else None,
            "parent_op_id": None,
            "label_space_version": label_space_version,
            "migration_batch_id": migration_batch_id,
            "created_at": now, "updated_at": now,
        })

        companion_ids: List[str] = []
        if source == "human_range" and rest_of_day_policy == "normal":
            companion_ids = self._write_rest_of_day_companions(
                site_id=site_id, device_id=device_id, branch_id=branch_id,
                t_start=t_start, t_end=t_end, parent_op_id=main_op_id,
                reviewer=reviewer, source_ref=source_ref,
                label_space_version=label_space_version,
                migration_batch_id=migration_batch_id, created_at=now,
            )

        # 重物化范围需覆盖主操作与全部伴生操作（伴生操作按自然日展开，范围更大）
        mat_start, mat_end = self._materialize_range(t_start, t_end, bool(companion_ids))
        materialized = self._materializer.materialize(
            site_id, device_id, branch_id, mat_start, mat_end
        )

        logger.info(
            "submit_op: op=%s source=%s 设备(%s,%s,%s) [%s,%s) companions=%d materialized=%s",
            main_op_id, source, site_id, device_id, branch_id,
            t_start, t_end, len(companion_ids), materialized,
        )
        return {
            "op_id": main_op_id,
            "companion_op_ids": companion_ids,
            "materialized": materialized,
        }

    def revoke_op(self, op_id: str) -> Dict[str, Any]:
        """撤销一条操作并联动撤销其伴生操作，随后重物化受影响范围。

        Requirements: 6.1, 6.2, 6.3, 6.4, 6.8
        """
        op = self._labels.query_op_by_id(op_id)
        if op is None:
            raise PointLabelValidationError("op_id 不存在", {"op_id": op_id})

        device_key = (op["site_id"], op["device_id"], op["branch_id"])
        with _DEVICE_LOCKS[device_key], self._device_db_lock(
            op["site_id"], op["device_id"], op["branch_id"]
        ):
            revoked_ids = []
            if self._labels.revoke_op(op_id):
                revoked_ids.append(op_id)

            companion_start, companion_end = op["t_start"], op["t_end"]
            for companion in self._labels.query_ops_by_parent(op_id):
                if companion["status"] == "active" and self._labels.revoke_op(companion["op_id"]):
                    revoked_ids.append(companion["op_id"])
                    companion_start = min(companion_start, companion["t_start"])
                    companion_end = max(companion_end, companion["t_end"])

            materialized = self._materializer.materialize(
                op["site_id"], op["device_id"], op["branch_id"], companion_start, companion_end
            )
        logger.info("revoke_op: revoked=%s materialized=%s", revoked_ids, materialized)
        return {"revoked_op_ids": revoked_ids, "materialized": materialized}

    def correct_op(
        self,
        *,
        old_op_id: str,
        label_id: Optional[int],
        reviewer: Optional[str] = None,
        source_ref: Optional[str] = None,
    ) -> Dict[str, Any]:
        """改判：新增一条同范围操作 + 把旧操作置 revoked（需求 6 第 2 条、19 第 10 条）。"""
        old = self._labels.query_op_by_id(old_op_id)
        if old is None:
            raise PointLabelValidationError("待改判的 op_id 不存在", {"op_id": old_op_id})

        self.revoke_op(old_op_id)
        return self.submit_op(
            site_id=old["site_id"], device_id=old["device_id"], branch_id=old["branch_id"],
            t_start=old["t_start"], t_end=old["t_end"], label_id=label_id,
            source=old["source"], reviewer=reviewer or old["reviewer"],
            source_ref=source_ref or old["source_ref"],
            rest_of_day_policy=old.get("rest_of_day_policy") or "normal",
        )

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    @contextmanager
    def _device_db_lock(self, site_id: str, device_id: str, branch_id: str):
        """DB 级设备顾问锁的可选包装。

        仓库实现了 `device_advisory_lock` 时取 DB 顾问锁（跨进程串行化）；
        未实现时退化为空上下文，仅依赖进程内 `_DEVICE_LOCKS`。这样
        `PointLabelService` 不强绑定具体仓库实现（测试可注入轻量 Stub），
        同时生产环境仍然拿到跨进程保护。
        """
        acquirer = getattr(self._labels, "device_advisory_lock", None)
        if acquirer is None:
            yield None
            return
        with acquirer(site_id, device_id, branch_id) as acquired:
            yield acquired

    @staticmethod
    def _resolve_priority(source: str) -> int:
        """由 source 唯一推导 priority；`inference` 与未知取值一律拒绝。"""
        if source == "inference":
            raise PointLabelValidationError(
                "inference 不属于 source 枚举值，推理样本不落库",
                {"source": source},
            )
        if source not in SOURCE_PRIORITY:
            raise PointLabelValidationError(
                f"未知 source 取值，仅支持 {sorted(SOURCE_PRIORITY)}",
                {"source": source},
            )
        return SOURCE_PRIORITY[source]

    def _validate_boundaries(self, t_start: datetime, t_end: datetime) -> None:
        """校验 t_start < t_end、边界对齐采样栅格、跨度不超上限。"""
        if not (t_start < t_end):
            raise PointLabelValidationError(
                "要求 t_start < t_end", {"t_start": str(t_start), "t_end": str(t_end)}
            )
        for name, ts in (("t_start", t_start), ("t_end", t_end)):
            seconds = ts.hour * 3600 + ts.minute * 60 + ts.second
            if seconds % SAMPLING_INTERVAL_SECONDS != 0 or ts.microsecond != 0:
                raise PointLabelValidationError(
                    f"{name} 未对齐到 {SAMPLING_INTERVAL_SECONDS} 秒采样栅格",
                    {name: str(ts)},
                )
        if (t_end - t_start) > self._max_op_span:
            raise PointLabelValidationError(
                f"操作跨度超过上限 {self._max_op_span.days} 天",
                {"span_days": (t_end - t_start).days},
            )

    @staticmethod
    def _validate_human_source_fields(
        source: str, reviewer: Optional[str], source_ref: Optional[str]
    ) -> None:
        """human_* 来源必须带 reviewer 与 source_ref（需求 5 第 3 条）。"""
        if source.startswith("human_"):
            missing = [
                name for name, val in (("reviewer", reviewer), ("source_ref", source_ref))
                if not (val and str(val).strip())
            ]
            if missing:
                raise PointLabelValidationError(
                    f"source={source} 要求 {missing} 为非空值", {"missing": missing}
                )

    def _validate_label_id(self, label_id: Optional[int]) -> str:
        """校验 label_id 在当前标签空间内；label_id 为 None（unknown）时跳过校验。

        Returns:
            当前 label_space_version（写入操作时记录）。

        Requirements: 18.1, 18.2, 18.4, 18.8
        """
        current = self._registry.get_current()
        version = str(current.get("label_space_version", "ls-v1"))
        if label_id is None:
            return version
        known_ids = {int(item["label_id"]) for item in current.get("labels", [])}
        if int(label_id) not in known_ids:
            raise PointLabelValidationError(
                "label_id 不在当前标签空间中",
                {"label_id": label_id, "label_space_version": version,
                 "known_label_ids": sorted(known_ids)},
            )
        return version

    def _check_human_range_overlap(
        self, site_id: str, device_id: str, branch_id: str,
        t_start: datetime, t_end: datetime,
    ) -> None:
        """全表检查 active human_range 重叠（覆盖所有 review_id，修复跨会话漏检）。

        Requirements: 5.11, 16.2, 16.3
        """
        overlaps = self._labels.query_active_human_range_overlap(
            site_id, device_id, branch_id, t_start, t_end
        )
        if overlaps:
            raise PointLabelValidationError(
                "该设备该时段已存在 active 的人工框选标注，不允许重叠",
                {"conflicts": [
                    {"op_id": o["op_id"], "t_start": str(o["t_start"]), "t_end": str(o["t_end"])}
                    for o in overlaps
                ]},
            )

    # ------------------------------------------------------------------
    # K4：未框选即正常
    # ------------------------------------------------------------------

    def _write_rest_of_day_companions(
        self, *, site_id: str, device_id: str, branch_id: str,
        t_start: datetime, t_end: datetime, parent_op_id: str,
        reviewer: Optional[str], source_ref: Optional[str],
        label_space_version: str, migration_batch_id: Optional[str],
        created_at: datetime,
    ) -> List[str]:
        """为框选跨越的每个自然日各写一条 `human_day` / `label_id=0` 伴生操作。

        `op_scope` = (site_id, device_id, branch_id, 该自然日)，严格不外溢到
        其他设备或其他自然日（需求 5 第 5、6 条）。

        Requirements: 5.4, 5.5, 5.6, 5.9
        """
        companion_ids: List[str] = []
        for day_start in self._iter_covered_days(t_start, t_end):
            day_end = day_start + timedelta(days=1)
            companion_id = self._make_op_id(
                site_id, device_id, branch_id, day_start, day_end,
                NORMAL_LABEL_ID, "human_day", salt=parent_op_id,
            )
            self._labels.insert_op({
                "op_id": companion_id,
                "site_id": site_id, "device_id": device_id, "branch_id": branch_id,
                "t_start": day_start, "t_end": day_end,
                "label_id": NORMAL_LABEL_ID,
                "source": "human_day", "priority": SOURCE_PRIORITY["human_day"],
                "status": "active", "reviewer": reviewer, "source_ref": source_ref,
                "rest_of_day_policy": "normal", "parent_op_id": parent_op_id,
                "label_space_version": label_space_version,
                "migration_batch_id": migration_batch_id,
                "created_at": created_at, "updated_at": created_at,
            })
            companion_ids.append(companion_id)
        return companion_ids

    @staticmethod
    def _iter_covered_days(t_start: datetime, t_end: datetime) -> List[datetime]:
        """列出 [t_start, t_end) 覆盖到的每个自然日起点（右开：恰好落在 00:00 的
        终点不算新的一天）。"""
        first_day = t_start.replace(hour=0, minute=0, second=0, microsecond=0)
        days = []
        cursor = first_day
        while cursor < t_end:
            days.append(cursor)
            cursor = cursor + timedelta(days=1)
        return days

    @staticmethod
    def _materialize_range(
        t_start: datetime, t_end: datetime, has_companions: bool
    ) -> tuple[datetime, datetime]:
        """重物化范围：有伴生操作时按自然日边界外扩，确保覆盖伴生操作全范围。"""
        if not has_companions:
            return t_start, t_end
        start = t_start.replace(hour=0, minute=0, second=0, microsecond=0)
        end_day = t_end.replace(hour=0, minute=0, second=0, microsecond=0)
        end = end_day if end_day == t_end else end_day + timedelta(days=1)
        return start, end

    @staticmethod
    def _make_op_id(
        site_id: str, device_id: str, branch_id: str,
        t_start: datetime, t_end: datetime,
        label_id: Optional[int], source: str,
        salt: str = "",
    ) -> str:
        """按内容哈希生成 `op-{hex12}`，使同源同内容的重复写入幂等（需求 14 第 15 条）。"""
        key = f"{source}|{site_id}|{device_id}|{branch_id}|{t_start.isoformat()}|{t_end.isoformat()}|{label_id}|{salt}"
        return f"op-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}"

# @AI_GENERATED: end
