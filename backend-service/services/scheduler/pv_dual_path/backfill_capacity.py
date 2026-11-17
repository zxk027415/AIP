# @AI_GENERATED
# -*- coding: utf-8 -*-
"""生产检测与历史回放共享资源的令牌仲裁器。

``BackfillCapacityArbiter`` 不执行任务，也不保存业务进度；它只根据 worker、数据库连接、
内存预算和模型加载槽四个独立瓶颈计算可并发令牌，并确保 ``historical_backfill`` — 历史回放
车道永远不能占用 ``production`` — 生产车道的保留容量。
"""
from __future__ import annotations

import math
import threading
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

_PRODUCTION = "production"
_HISTORICAL_BACKFILL = "historical_backfill"
_ALLOWED_LANES = frozenset({_PRODUCTION, _HISTORICAL_BACKFILL})


@dataclass(frozen=True)
class CapacityResources:
    """一次容量探测的四项资源令牌。

    ``worker_slots`` — 可用 worker 槽；``db_connection_slots`` — 可用数据库连接槽；
    ``memory_slots`` — 按内存水位换算的模型执行槽；``model_load_slots`` — 同时加载模型槽；
    ``low_resource`` — 是否触发资源低水位，触发时暂停新历史任务。
    """

    worker_slots: int
    db_connection_slots: int
    memory_slots: int
    model_load_slots: int
    low_resource: bool = False

    def __post_init__(self) -> None:
        values = {
            "worker_slots": self.worker_slots,
            "db_connection_slots": self.db_connection_slots,
            "memory_slots": self.memory_slots,
            "model_load_slots": self.model_load_slots,
        }
        for field, value in values.items():
            if isinstance(value, bool) or int(value) != value or value < 0:
                raise ValueError(f"{field} — 资源槽必须是非负整数，收到 {value!r}")
        if not isinstance(self.low_resource, bool):
            raise ValueError("low_resource — 低水位标记必须是 JSON/Python boolean")

    @property
    def total_tokens(self) -> int:
        """返回四项瓶颈的最小值。"""

        return min(
            self.worker_slots,
            self.db_connection_slots,
            self.memory_slots,
            self.model_load_slots,
        )

    @classmethod
    def from_memory_watermark(
        cls,
        *,
        worker_slots: int,
        db_connection_slots: int,
        memory_available_mb: int,
        memory_reserved_mb: int,
        memory_mb_per_token: int,
        model_load_slots: int,
    ) -> "CapacityResources":
        """把可用内存和保留水位换算为内存令牌。

        当 ``memory_available_mb`` — 可用内存 MB 小于或等于
        ``memory_reserved_mb`` — 低水位阈值 MB 时进入低水位并暂停新增历史任务；内存令牌仍按
        全部可用内存除以 ``memory_mb_per_token`` — 每令牌内存 MB 计算，供生产车道在历史任务
        让行后继续运行，而不是把保留内存同时从生产容量中扣除。
        """

        if memory_available_mb < 0 or memory_reserved_mb < 0:
            raise ValueError("内存水位必须是非负 MB")
        if memory_mb_per_token <= 0:
            raise ValueError("memory_mb_per_token 必须大于 0")
        memory_slots = int(memory_available_mb) // int(memory_mb_per_token)
        return cls(
            worker_slots=worker_slots,
            db_connection_slots=db_connection_slots,
            memory_slots=memory_slots,
            model_load_slots=model_load_slots,
            low_resource=memory_available_mb <= memory_reserved_mb,
        )


@dataclass(frozen=True)
class CapacitySnapshot:
    """仲裁器当前可观察状态，不暴露内部可变映射。"""

    total_tokens: int
    production_reserved_tokens: int
    backfill_limit_tokens: int
    production_in_use: int
    backfill_in_use: int
    free_tokens: int
    pressure_state: str
    backfill_should_yield: bool


@dataclass(frozen=True)
class CapacityDecision:
    """一次令牌申请结果。"""

    granted: bool
    lane: str
    tokens: int
    reason: str
    lease_id: Optional[str]
    snapshot: CapacitySnapshot


class BackfillCapacityArbiter:
    """线程安全的生产优先令牌仲裁器。"""

    def __init__(
        self,
        resources: CapacityResources,
        *,
        production_capacity_reserved_ratio: float = 0.8,
    ) -> None:
        ratio = float(production_capacity_reserved_ratio)
        if not math.isfinite(ratio) or ratio < 0.0 or ratio > 1.0:
            raise ValueError("production_capacity_reserved_ratio 必须在 [0, 1] 范围内")
        self._ratio = ratio
        self._resources = resources
        self._leases: Dict[str, tuple[str, int]] = {}
        self._lock = threading.RLock()

    def refresh(self, resources: CapacityResources) -> CapacitySnapshot:
        """更新资源探测值；不强制撤销 lease，但会阻止超额历史申请并发出让行信号。"""

        with self._lock:
            self._resources = resources
            return self._snapshot_locked()

    def snapshot(self) -> CapacitySnapshot:
        """返回当前容量、占用和压力状态。"""

        with self._lock:
            return self._snapshot_locked()

    def acquire(self, lane: str, tokens: int = 1) -> CapacityDecision:
        """为指定车道申请令牌；失败无副作用且返回结构化原因。"""

        normalized_lane = str(lane or "").strip()
        if normalized_lane not in _ALLOWED_LANES:
            raise ValueError(f"lane — 执行车道仅允许 {sorted(_ALLOWED_LANES)!r}")
        if isinstance(tokens, bool) or int(tokens) != tokens or tokens <= 0:
            raise ValueError("tokens — 申请令牌数必须是正整数")
        requested = int(tokens)
        with self._lock:
            before = self._snapshot_locked()
            if normalized_lane == _HISTORICAL_BACKFILL and self._resources.low_resource:
                return CapacityDecision(
                    False, normalized_lane, requested, "resource_pressure", None, before
                )
            if before.total_tokens == 0:
                return CapacityDecision(
                    False, normalized_lane, requested, "no_capacity", None, before
                )
            if normalized_lane == _HISTORICAL_BACKFILL:
                lane_available = max(
                    0,
                    before.backfill_limit_tokens - before.backfill_in_use,
                )
                if requested > lane_available:
                    return CapacityDecision(
                        False,
                        normalized_lane,
                        requested,
                        "production_capacity_reserved",
                        None,
                        before,
                    )
            if requested > before.free_tokens:
                return CapacityDecision(
                    False, normalized_lane, requested, "capacity_exhausted", None, before
                )

            lease_id = f"capacity-{uuid.uuid4().hex}"
            self._leases[lease_id] = (normalized_lane, requested)
            return CapacityDecision(
                True,
                normalized_lane,
                requested,
                "granted",
                lease_id,
                self._snapshot_locked(),
            )

    def release(self, lease_id: str) -> bool:
        """归还 lease；重复或未知 ID 返回 False，不影响其他租约。"""

        normalized = str(lease_id or "").strip()
        if not normalized:
            return False
        with self._lock:
            return self._leases.pop(normalized, None) is not None

    def _snapshot_locked(self) -> CapacitySnapshot:
        total = self._resources.total_tokens
        reserved = min(total, int(math.ceil(total * self._ratio)))
        backfill_limit = 0 if self._resources.low_resource else max(0, total - reserved)
        production_in_use = sum(
            tokens for lane, tokens in self._leases.values() if lane == _PRODUCTION
        )
        backfill_in_use = sum(
            tokens for lane, tokens in self._leases.values() if lane == _HISTORICAL_BACKFILL
        )
        free = max(0, total - production_in_use - backfill_in_use)
        if self._resources.low_resource or total == 0:
            pressure_state = "paused"
        elif backfill_in_use > backfill_limit or production_in_use + backfill_in_use > total:
            pressure_state = "draining"
        elif total < max(
            self._resources.worker_slots,
            self._resources.db_connection_slots,
            self._resources.model_load_slots,
        ):
            pressure_state = "throttled"
        else:
            pressure_state = "normal"
        should_yield = bool(
            backfill_in_use
            and (
                self._resources.low_resource
                or backfill_in_use > backfill_limit
                or production_in_use < reserved
                and free < reserved - production_in_use
            )
        )
        return CapacitySnapshot(
            total_tokens=total,
            production_reserved_tokens=reserved,
            backfill_limit_tokens=backfill_limit,
            production_in_use=production_in_use,
            backfill_in_use=backfill_in_use,
            free_tokens=free,
            pressure_state=pressure_state,
            backfill_should_yield=should_yield,
        )


__all__ = [
    "BackfillCapacityArbiter",
    "CapacityDecision",
    "CapacityResources",
    "CapacitySnapshot",
]
# @AI_GENERATED: end
