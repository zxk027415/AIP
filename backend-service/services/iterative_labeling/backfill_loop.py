# @AI_GENERATED
# -*- coding: utf-8 -*-
"""共享人工标签事实到两条建模路径的消费投影。

这里的 BackfillLoop 是“标签回流”而非历史推理 BackfillRunner。它不创建第二份标签存储：
``SharedLabelPool`` 只包装既有 ``label_ops`` / ``point_labels`` 真相仓储的 reader/writer，
按路径过滤后把事实交给训练快照消费者。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

_ALLOWED_PATHS = frozenset({"legacy_day", "seq_annotation"})
_POINT_GRANULARITY = "point"
_DAY_GRANULARITY = "day"
_ALLOWED_GRANULARITIES = frozenset({_POINT_GRANULARITY, _DAY_GRANULARITY})
_PURE_DAY_SOURCES = frozenset({"day_label", "human_day", "parquet_day_label"})


@dataclass(frozen=True)
class SharedLabelFact:
    """共享标签事实的只读投影。

    ``fact_id`` — 既有标签事实 ID；``sequence`` — 单调变更序号；``granularity`` — 标签
    粒度（point/day）；``business_date`` — 业务日期；其余设备字段组成设备三元组。
    """

    fact_id: str
    sequence: int
    site_id: str
    device_id: str
    branch_id: str
    business_date: date
    label_id: int
    granularity: str
    source: str
    event_time: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "sequence": self.sequence,
            "site_id": self.site_id,
            "device_id": self.device_id,
            "branch_id": self.branch_id,
            "business_date": self.business_date.isoformat(),
            "label_id": self.label_id,
            "granularity": self.granularity,
            "source": self.source,
            "event_time": self.event_time.isoformat() if self.event_time else None,
        }


@dataclass(frozen=True)
class BackfillConsumptionResult:
    """一次路径标签回流结果。"""

    modeling_path: str
    consumed_fact_ids: List[str]
    change_units: int
    previous_sequence: int
    consumed_sequence: int


class SharedLabelPool:
    """既有 label_ops/point_labels 的无状态适配器，不持久化标签副本。"""

    def __init__(
        self,
        fact_reader: Callable[[], Iterable[Mapping[str, Any]]],
        *,
        fact_writer: Optional[Callable[[Mapping[str, Any]], Any]] = None,
    ) -> None:
        self._fact_reader = fact_reader
        self._fact_writer = fact_writer

    def write_once(self, fact: SharedLabelFact) -> Any:
        """把标签事实写入注入的唯一真相仓储；未注入 writer 时明确拒绝。"""

        if self._fact_writer is None:
            raise RuntimeError("SharedLabelPool 未配置 label_ops/point_labels writer")
        return self._fact_writer(fact.to_dict())

    def list_for_path(
        self,
        modeling_path: str,
        *,
        after_sequence: int = 0,
    ) -> List[SharedLabelFact]:
        """按路径返回只读投影；Legacy 把逐点事实聚合为天级，Seq 只取真实逐点事实。"""

        path = str(modeling_path or "").strip()
        if path not in _ALLOWED_PATHS:
            raise ValueError(f"不支持的 modeling_path: {path}")
        threshold = max(0, int(after_sequence))
        facts = sorted(
            (self._parse_fact(raw) for raw in self._fact_reader()),
            key=lambda item: (item.sequence, item.fact_id),
        )
        visible = [fact for fact in facts if fact.sequence > threshold]
        if path == "seq_annotation":
            return [
                fact
                for fact in visible
                if fact.granularity == _POINT_GRANULARITY
                and fact.source not in _PURE_DAY_SOURCES
                and fact.event_time is not None
            ]
        return self._project_legacy_days(visible)

    @staticmethod
    def _project_legacy_days(facts: List[SharedLabelFact]) -> List[SharedLabelFact]:
        """生成 Legacy 天级只读投影；显式天级事实优先，否则按逐点多数票聚合。"""

        grouped: Dict[tuple[str, str, str, date], List[SharedLabelFact]] = {}
        for fact in facts:
            key = (fact.site_id, fact.device_id, fact.branch_id, fact.business_date)
            grouped.setdefault(key, []).append(fact)

        projected: List[SharedLabelFact] = []
        for key, group in grouped.items():
            explicit_days = [item for item in group if item.granularity == _DAY_GRANULARITY]
            if explicit_days:
                projected.append(max(explicit_days, key=lambda item: (item.sequence, item.fact_id)))
                continue
            point_facts = [item for item in group if item.granularity == _POINT_GRANULARITY]
            if not point_facts:
                continue
            counts: Dict[int, int] = {}
            for item in point_facts:
                counts[item.label_id] = counts.get(item.label_id, 0) + 1
            latest = max(point_facts, key=lambda item: (item.sequence, item.fact_id))
            winning_label = max(
                counts,
                key=lambda label: (counts[label], label == latest.label_id, label),
            )
            site_id, device_id, branch_id, business_date = key
            projected.append(
                SharedLabelFact(
                    fact_id=(
                        "legacy-day-projection:"
                        f"{site_id}:{device_id}:{branch_id}:{business_date.isoformat()}"
                    ),
                    sequence=max(item.sequence for item in point_facts),
                    site_id=site_id,
                    device_id=device_id,
                    branch_id=branch_id,
                    business_date=business_date,
                    label_id=winning_label,
                    granularity=_DAY_GRANULARITY,
                    source="point_aggregate",
                    event_time=None,
                )
            )
        return sorted(projected, key=lambda item: (item.sequence, item.fact_id))

    @staticmethod
    def _parse_fact(raw: Mapping[str, Any]) -> SharedLabelFact:
        granularity = str(raw.get("granularity") or "").strip()
        if granularity not in _ALLOWED_GRANULARITIES:
            raise ValueError(f"非法标签 granularity: {granularity!r}")
        raw_date = raw.get("business_date")
        business_date = (
            raw_date.date()
            if isinstance(raw_date, datetime)
            else raw_date
            if isinstance(raw_date, date)
            else date.fromisoformat(str(raw_date)[:10])
        )
        raw_time = raw.get("event_time")
        event_time: Optional[datetime]
        if isinstance(raw_time, datetime):
            event_time = raw_time
        elif raw_time in (None, ""):
            event_time = None
        else:
            event_time = datetime.fromisoformat(str(raw_time))
        fact = SharedLabelFact(
            fact_id=str(raw.get("fact_id") or "").strip(),
            sequence=int(raw.get("sequence") or 0),
            site_id=str(raw.get("site_id") or "").strip(),
            device_id=str(raw.get("device_id") or "").strip(),
            branch_id=str(raw.get("branch_id") or "").strip(),
            business_date=business_date,
            label_id=int(raw["label_id"]),
            granularity=granularity,
            source=str(raw.get("source") or "").strip(),
            event_time=event_time,
        )
        if (
            not fact.fact_id
            or fact.sequence < 1
            or not fact.site_id
            or not fact.device_id
            or not fact.branch_id
            or not fact.source
        ):
            raise ValueError("共享标签事实缺少 fact_id/sequence/设备三元组/source")
        return fact


class BackfillLoop:
    """按路径消费共享标签事实并返回独立 Retrain Consumption Watermark。"""

    def __init__(
        self,
        pool: SharedLabelPool,
        consumer: Callable[[str, List[SharedLabelFact]], Any],
    ) -> None:
        self._pool = pool
        self._consumer = consumer

    def run_once(
        self,
        modeling_path: str,
        *,
        consumed_sequence: int = 0,
    ) -> BackfillConsumptionResult:
        """只推进调用路径水位；另一条路径和共享标签事实均不修改。"""

        facts = self._pool.list_for_path(
            modeling_path,
            after_sequence=consumed_sequence,
        )
        if facts:
            self._consumer(modeling_path, facts)
        next_sequence = max(
            [int(consumed_sequence), *(fact.sequence for fact in facts)]
        )
        return BackfillConsumptionResult(
            modeling_path=modeling_path,
            consumed_fact_ids=[fact.fact_id for fact in facts],
            change_units=len(facts),
            previous_sequence=max(0, int(consumed_sequence)),
            consumed_sequence=next_sequence,
        )


__all__ = [
    "BackfillConsumptionResult",
    "BackfillLoop",
    "SharedLabelFact",
    "SharedLabelPool",
]
# @AI_GENERATED: end
