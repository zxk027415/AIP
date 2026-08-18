# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PV 双路径分离的 append-only 治理事件仓储。

PromotionEvent 只表达同路径 Challenger→Champion；PathSwitchEvent 只表达经过九项门控的
跨路径切换。两类事件按 ``slot + event_id`` 分区、使用不同 JSON 文件，不提供更新或删除。
写入复用相对路径原子 JSON 工具，并用进程内 RLock 保护 read-modify-write；确定性事件 ID
重放时幂等返回，不重复追加。
"""

from __future__ import annotations

import json
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.scheduler.pv_dual_path.persistence_utils import atomic_write_json

DEFAULT_SLOT = "pv_fault"
_BACKEND_SERVICE_DIR = Path(__file__).resolve().parents[2]
_ENV_EVENTS_DIR = "PV_GOVERNANCE_EVENTS_DIR"
_DEFAULT_EVENTS_DIR = _BACKEND_SERVICE_DIR / "data" / "pv_dual_path" / "governance_events"
_EVENT_LOCKS: Dict[str, threading.RLock] = defaultdict(threading.RLock)


def _resolve_events_dir() -> Path:
    override = os.environ.get(_ENV_EVENTS_DIR)
    if override:
        candidate = Path(override)
        return candidate if candidate.is_absolute() else _BACKEND_SERVICE_DIR / candidate
    return _DEFAULT_EVENTS_DIR


def _read_list(target_path: Path) -> List[Dict[str, Any]]:
    if not target_path.exists():
        return []
    with target_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"事件仓储格式错误，期望 JSON list: {target_path.name}")
    return [dict(item) for item in payload]


@dataclass
class PromotionEvent:
    """路径内晋升事件。

    最小字段保持 design.md §11 契约；可选字段记录旧 Champion、双方指标、margin 与指标
    方向，便于解释严格晋升判定。可选字段缺失时不会在旧事件读取中伪造值。
    """

    promotion_event_id: str
    modeling_path: str
    champion_model_ref: str
    challenger_model_ref: str
    evaluation_id: str
    promoted_at: str
    previous_champion_model_ref: Optional[str] = None
    champion_gate_metric_value: Optional[float] = None
    challenger_gate_metric_value: Optional[float] = None
    promotion_margin: Optional[float] = None
    metric_direction: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "promotion_event_id": self.promotion_event_id,
            "modeling_path": self.modeling_path,
            "champion_model_ref": self.champion_model_ref,
            "challenger_model_ref": self.challenger_model_ref,
            "evaluation_id": self.evaluation_id,
            "promoted_at": self.promoted_at,
        }
        optional = {
            "previous_champion_model_ref": self.previous_champion_model_ref,
            "champion_gate_metric_value": self.champion_gate_metric_value,
            "challenger_gate_metric_value": self.challenger_gate_metric_value,
            "promotion_margin": self.promotion_margin,
            "metric_direction": self.metric_direction,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PromotionEvent":
        return cls(
            promotion_event_id=str(payload["promotion_event_id"]),
            modeling_path=str(payload["modeling_path"]),
            champion_model_ref=str(payload["champion_model_ref"]),
            challenger_model_ref=str(payload["challenger_model_ref"]),
            evaluation_id=str(payload["evaluation_id"]),
            promoted_at=str(payload["promoted_at"]),
            previous_champion_model_ref=payload.get("previous_champion_model_ref"),
            champion_gate_metric_value=payload.get("champion_gate_metric_value"),
            challenger_gate_metric_value=payload.get("challenger_gate_metric_value"),
            promotion_margin=payload.get("promotion_margin"),
            metric_direction=payload.get("metric_direction"),
        )


@dataclass
class PathSwitchEvent:
    """跨路径切换事件；完整字段必须来自任务 10.3 的九项门控协调器。"""

    path_switch_event_id: str
    from_path: str
    to_path: str
    comparison_id: str
    activation_epoch_id: str
    effective_from_date: str
    device_scope_digest: str
    device_scope_count: int
    activation_mode: str
    operator: str
    reason: str
    switched_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path_switch_event_id": self.path_switch_event_id,
            "from_path": self.from_path,
            "to_path": self.to_path,
            "comparison_id": self.comparison_id,
            "activation_epoch_id": self.activation_epoch_id,
            "effective_from_date": self.effective_from_date,
            "device_scope_digest": self.device_scope_digest,
            "device_scope_count": self.device_scope_count,
            "activation_mode": self.activation_mode,
            "operator": self.operator,
            "reason": self.reason,
            "switched_at": self.switched_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PathSwitchEvent":
        return cls(
            path_switch_event_id=str(payload["path_switch_event_id"]),
            from_path=str(payload["from_path"]),
            to_path=str(payload["to_path"]),
            comparison_id=str(payload["comparison_id"]),
            activation_epoch_id=str(payload["activation_epoch_id"]),
            effective_from_date=str(payload["effective_from_date"]),
            device_scope_digest=str(payload["device_scope_digest"]),
            device_scope_count=int(payload.get("device_scope_count", 0)),
            activation_mode=str(payload["activation_mode"]),
            operator=str(payload["operator"]),
            reason=str(payload["reason"]),
            switched_at=str(payload["switched_at"]),
        )


class PromotionEventStore:
    """路径内晋升事件只追加仓储。"""

    def __init__(self, base_dir: Optional[Path] = None, slot: str = DEFAULT_SLOT) -> None:
        self._base_dir = (
            Path(base_dir) if base_dir is not None else _resolve_events_dir()
        ).resolve()
        self._slot = slot

    def _events_path(self) -> Path:
        return self._base_dir / f"{self._slot}_promotion_events.json"

    def append_if_absent(self, event: PromotionEvent) -> bool:
        """按 promotion_event_id 幂等追加；同 ID 不同内容视为冲突。"""
        path = self._events_path()
        with _EVENT_LOCKS[str(path)]:
            events = _read_list(path)
            existing = next(
                (
                    item
                    for item in events
                    if item.get("promotion_event_id") == event.promotion_event_id
                ),
                None,
            )
            if existing is not None:
                if existing != event.to_dict():
                    raise ValueError("promotion_event_id 已存在但事件内容不同")
                return False
            events.append(event.to_dict())
            atomic_write_json(path, events, base_dir=self._base_dir)
            return True

    def append(self, event: PromotionEvent) -> None:
        self.append_if_absent(event)

    def list_recent(
        self,
        limit: int = 50,
        modeling_path: Optional[str] = None,
    ) -> List[PromotionEvent]:
        path = self._events_path()
        with _EVENT_LOCKS[str(path)]:
            events = [PromotionEvent.from_dict(item) for item in _read_list(path)]
        if modeling_path is not None:
            events = [event for event in events if event.modeling_path == modeling_path]
        return list(reversed(events))[: max(0, int(limit))]


class PathSwitchEventStore:
    """跨路径切换事件只追加仓储。"""

    def __init__(self, base_dir: Optional[Path] = None, slot: str = DEFAULT_SLOT) -> None:
        self._base_dir = (
            Path(base_dir) if base_dir is not None else _resolve_events_dir()
        ).resolve()
        self._slot = slot

    def _events_path(self) -> Path:
        return self._base_dir / f"{self._slot}_path_switch_events.json"

    def append_if_absent(self, event: PathSwitchEvent) -> bool:
        """按 path_switch_event_id 幂等追加；同 ID 不同内容视为冲突。"""
        path = self._events_path()
        with _EVENT_LOCKS[str(path)]:
            events = _read_list(path)
            existing = next(
                (
                    item
                    for item in events
                    if item.get("path_switch_event_id") == event.path_switch_event_id
                ),
                None,
            )
            if existing is not None:
                if existing != event.to_dict():
                    raise ValueError("path_switch_event_id 已存在但事件内容不同")
                return False
            events.append(event.to_dict())
            atomic_write_json(path, events, base_dir=self._base_dir)
            return True

    def append(self, event: PathSwitchEvent) -> None:
        self.append_if_absent(event)

    def list_recent(
        self,
        limit: int = 50,
        from_path: Optional[str] = None,
        to_path: Optional[str] = None,
    ) -> List[PathSwitchEvent]:
        path = self._events_path()
        with _EVENT_LOCKS[str(path)]:
            events = [PathSwitchEvent.from_dict(item) for item in _read_list(path)]
        if from_path is not None:
            events = [event for event in events if event.from_path == from_path]
        if to_path is not None:
            events = [event for event in events if event.to_path == to_path]
        return list(reversed(events))[: max(0, int(limit))]
# @AI_GENERATED: end
