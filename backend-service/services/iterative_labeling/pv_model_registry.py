# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PV 双路径模型 Registry、同路径晋升、兼容迁移与生产路径无状态门面。

`PVModelRegistry` 是 `pv_fault` 的唯一可写真相：按 `slot + modeling_path` 保存
Champion/Challenger/Retired 生命周期、当前生产路径、fallback 与 active Epoch。
`ProductionPathPointer` 不保存第二份状态，只把 get/switch 委托给 Registry。

持久化文件位于部署配置指定的相对目录，默认相对于 backend-service/ 的
``data/pv_dual_path/model_registry``。所有读改写由进程内 RLock 串行化，单文件写复用
pv_dual_path 的原子 JSON 工具。同路径晋升先写 Registry 再追加 PromotionEvent；事件
追加失败时补偿恢复晋升前 Registry 状态。跨路径九项门控及跨介质事务属于任务
10.1/10.3，本模块只允许调用注入的切换协调器，绝不自行改 production_path。
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import logging
import os
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from services.scheduler.pv_dual_path.persistence_utils import atomic_write_json, to_relative_path

from .pv_governance_events import (
    PathSwitchEvent,
    PathSwitchEventStore,
    PromotionEvent,
    PromotionEventStore,
)

logger = logging.getLogger(__name__)

DEFAULT_SLOT = "pv_fault"
_ALLOWED_MODELING_PATHS = frozenset({"legacy_day", "seq_annotation"})
_LEGACY_DAY_PATH_ALIASES = frozenset({"point_label_by_day", "point_label_by_day_night"})
_BACKEND_SERVICE_DIR = Path(__file__).resolve().parents[2]
_ENV_REGISTRY_DIR = "PV_MODEL_REGISTRY_DIR"
_DEFAULT_REGISTRY_DIR = _BACKEND_SERVICE_DIR / "data" / "pv_dual_path" / "model_registry"
_MIGRATION_VERSION = "legacy-cumulative-training-v1"
_REGISTRY_LOCKS: Dict[str, threading.RLock] = defaultdict(threading.RLock)

ValidationCallback = Callable[..., Any]
SwitchCoordinator = Callable[[Any], Any]


def _utc_now() -> str:
    return datetime.utcnow().isoformat()


def _canonical_modeling_path(value: Any) -> str:
    path = str(value or "").strip()
    return "legacy_day" if path in _LEGACY_DAY_PATH_ALIASES else path


def _resolve_registry_dir() -> Path:
    override = os.environ.get(_ENV_REGISTRY_DIR)
    if override:
        candidate = Path(override)
        return candidate if candidate.is_absolute() else _BACKEND_SERVICE_DIR / candidate
    return _DEFAULT_REGISTRY_DIR


def _stable_id(prefix: str, *parts: Any) -> str:
    encoded = "\x1f".join(str(part or "") for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:24]}"


def _payload_digest(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _call_callback(callback: ValidationCallback, *args: Any) -> Any:
    """按回调可接收的位置参数个数调用，兼容简单的一参数 validator。"""
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return callback(*args)
    positional = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
    ]
    if any(parameter.kind == parameter.VAR_POSITIONAL for parameter in signature.parameters.values()):
        return callback(*args)
    return callback(*args[: len(positional)])


def _validation_decision(result: Any, default_reason: str) -> Tuple[bool, Optional[str]]:
    if isinstance(result, tuple):
        allowed = bool(result[0]) if result else False
        reason = str(result[1]).strip() if len(result) > 1 and result[1] else None
        return allowed, reason if not allowed else None
    if isinstance(result, dict):
        allowed = bool(result.get("allowed", result.get("valid", False)))
        reason = str(result.get("reason") or "").strip() or None
        return allowed, reason if not allowed else None
    allowed = bool(result)
    return allowed, None if allowed else default_reason


@dataclass
class ModelRegistration:
    """模型生命周期登记。

    `model_ref` — 模型工件相对路径或稳定 ID；`evaluation_id` — 评估幂等键；
    `gate_metric_value` — 守门指标值；`registered_at` — UTC 登记时间；
    `candidate_id` — 稳定候选 ID；`qualified` — 当前是否具备晋升资格；
    `blocking_reasons` — 不合格或迁移阻断原因；`metric_name` — 指标名称；
    `metadata` — 兼容旧字段的只读补充信息。
    """

    model_ref: str
    evaluation_id: str
    gate_metric_value: float
    registered_at: str
    candidate_id: str = ""
    qualified: bool = True
    blocking_reasons: List[str] = field(default_factory=list)
    metric_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_ref": self.model_ref,
            "evaluation_id": self.evaluation_id,
            "gate_metric_value": self.gate_metric_value,
            "registered_at": self.registered_at,
            "candidate_id": self.candidate_id,
            "qualified": self.qualified,
            "blocking_reasons": list(self.blocking_reasons),
            "metric_name": self.metric_name,
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ModelRegistration":
        return cls(
            model_ref=str(payload["model_ref"]),
            evaluation_id=str(payload["evaluation_id"]),
            gate_metric_value=float(payload.get("gate_metric_value", 0.0)),
            registered_at=str(payload.get("registered_at") or ""),
            candidate_id=str(payload.get("candidate_id") or ""),
            qualified=bool(payload.get("qualified", True)),
            blocking_reasons=[str(reason) for reason in payload.get("blocking_reasons") or []],
            metric_name=payload.get("metric_name"),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class PathModelState:
    """单条 modeling_path 的 Champion/Challenger/Retired 生命周期。"""

    champion: Optional[ModelRegistration] = None
    challengers: List[ModelRegistration] = field(default_factory=list)
    retired: List[ModelRegistration] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "champion": self.champion.to_dict() if self.champion else None,
            "challengers": [item.to_dict() for item in self.challengers],
            "retired": [item.to_dict() for item in self.retired],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PathModelState":
        champion = payload.get("champion")
        return cls(
            champion=ModelRegistration.from_dict(champion) if champion else None,
            challengers=[ModelRegistration.from_dict(item) for item in payload.get("challengers") or []],
            retired=[ModelRegistration.from_dict(item) for item in payload.get("retired") or []],
        )


@dataclass
class PVSlotState:
    """一个 slot 的完整 Registry 状态。"""

    production_path: str
    fallback_path: str
    active_activation_epoch_id: Optional[str] = None
    path_models: Dict[str, PathModelState] = field(default_factory=dict)
    updated_at: str = ""
    note: Optional[str] = None
    legacy_audit: List[Dict[str, Any]] = field(default_factory=list)
    migration: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "production_path": self.production_path,
            "fallback_path": self.fallback_path,
            "active_activation_epoch_id": self.active_activation_epoch_id,
            "path_models": {key: value.to_dict() for key, value in self.path_models.items()},
            "updated_at": self.updated_at,
            "note": self.note,
            "legacy_audit": copy.deepcopy(self.legacy_audit),
            "migration": copy.deepcopy(self.migration),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "PVSlotState":
        return cls(
            production_path=str(payload.get("production_path") or "legacy_day"),
            fallback_path=str(payload.get("fallback_path") or "seq_annotation"),
            active_activation_epoch_id=payload.get("active_activation_epoch_id"),
            path_models={
                key: PathModelState.from_dict(value)
                for key, value in (payload.get("path_models") or {}).items()
                if isinstance(value, dict)
            },
            updated_at=str(payload.get("updated_at") or ""),
            note=payload.get("note"),
            legacy_audit=[dict(item) for item in payload.get("legacy_audit") or []],
            migration=dict(payload.get("migration") or {}),
        )


@dataclass
class LifecycleOperationResult:
    """登记/晋升的明确结果；拒绝和幂等重放均不靠模糊的 None 表示。"""

    status: str
    changed: bool
    reason: Optional[str] = None
    registration: Optional[ModelRegistration] = None
    event: Optional[PromotionEvent] = None


@dataclass
class MigrationResult:
    """旧累计训练状态迁移结果。"""

    status: str
    changed: bool
    champions_migrated: int = 0
    challengers_migrated: int = 0
    promotion_events_migrated: int = 0
    path_switch_events_migrated: int = 0
    legacy_audit_preserved: int = 0


class PVModelRegistry:
    """PV 模型治理唯一可写真相。"""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        *,
        events_base_dir: Optional[Path] = None,
        switch_coordinator: Optional[SwitchCoordinator] = None,
        promotion_store_factory: Optional[Callable[[str], PromotionEventStore]] = None,
        path_switch_store_factory: Optional[Callable[[str], PathSwitchEventStore]] = None,
    ) -> None:
        self._base_dir = (Path(base_dir) if base_dir is not None else _resolve_registry_dir()).resolve()
        self._events_base_dir = Path(events_base_dir).resolve() if events_base_dir is not None else None
        self._switch_coordinator = switch_coordinator
        self._promotion_store_factory = promotion_store_factory
        self._path_switch_store_factory = path_switch_store_factory

    def _slot_path(self, slot: str) -> Path:
        return self._base_dir / f"{slot}.json"

    def _lock_for_slot(self, slot: str) -> threading.RLock:
        return _REGISTRY_LOCKS[str(self._slot_path(slot))]

    def _promotion_store(self, slot: str) -> PromotionEventStore:
        if self._promotion_store_factory:
            return self._promotion_store_factory(slot)
        return PromotionEventStore(base_dir=self._events_base_dir, slot=slot)

    def _path_switch_store(self, slot: str) -> PathSwitchEventStore:
        if self._path_switch_store_factory:
            return self._path_switch_store_factory(slot)
        return PathSwitchEventStore(base_dir=self._events_base_dir, slot=slot)

    def has_slot(self, slot: str = DEFAULT_SLOT) -> bool:
        """仅判断 Registry 真相文件是否已建立，不把缺文件默认态误认为已迁移。"""
        return self._slot_path(slot).exists()

    def get_slot(self, slot: str = DEFAULT_SLOT) -> PVSlotState:
        """读取 slot；缺文件时返回无写副作用的默认初始态。"""
        with self._lock_for_slot(slot):
            slot_path = self._slot_path(slot)
            if not slot_path.exists():
                return PVSlotState("legacy_day", "seq_annotation")
            with slot_path.open("r", encoding="utf-8") as handle:
                return PVSlotState.from_dict(json.load(handle))

    def _save_slot(self, slot: str, state: PVSlotState) -> None:
        state.updated_at = _utc_now()
        atomic_write_json(self._slot_path(slot), state.to_dict(), base_dir=self._base_dir)

    def _normalize_registration(
        self,
        slot: str,
        modeling_path: str,
        model: ModelRegistration,
    ) -> ModelRegistration:
        if not str(model.model_ref or "").strip():
            raise ValueError("model_ref 不能为空")
        if not str(model.evaluation_id or "").strip():
            raise ValueError("evaluation_id 不能为空")
        normalized_ref = to_relative_path(model.model_ref, base_dir=_BACKEND_SERVICE_DIR)
        normalized = copy.deepcopy(model)
        normalized.model_ref = normalized_ref
        normalized.registered_at = normalized.registered_at or _utc_now()
        normalized.candidate_id = normalized.candidate_id or _stable_id(
            "pvcand", slot, modeling_path, normalized.evaluation_id
        )
        normalized.blocking_reasons = list(dict.fromkeys(normalized.blocking_reasons))
        if normalized.blocking_reasons:
            normalized.qualified = False
        return normalized

    @staticmethod
    def _find_evaluation(state: PVSlotState, evaluation_id: str) -> Optional[ModelRegistration]:
        for path_state in state.path_models.values():
            candidates = list(path_state.challengers) + list(path_state.retired)
            if path_state.champion:
                candidates.append(path_state.champion)
            for registration in candidates:
                if registration.evaluation_id == evaluation_id:
                    return registration
        return None

    def register_challenger(
        self,
        modeling_path: str,
        model: ModelRegistration,
        *,
        slot: str = DEFAULT_SLOT,
        qualification_validator: Optional[ValidationCallback] = None,
    ) -> LifecycleOperationResult:
        """按 `slot + modeling_path + evaluation_id` 幂等登记 Challenger。

        同 evaluation_id 的同内容重放返回 ``duplicate``；不同内容返回
        ``evaluation_id_conflict``。validator 拒绝时仍登记 Challenger，但写入明确阻断原因。
        任何结果都不修改 production_path、active Epoch 或 Champion。
        """
        path = _canonical_modeling_path(modeling_path)
        if path not in _ALLOWED_MODELING_PATHS:
            raise ValueError(f"不支持的 modeling_path: {path}")
        normalized = self._normalize_registration(slot, path, model)
        with self._lock_for_slot(slot):
            state = self.get_slot(slot)
            existing = self._find_evaluation(state, normalized.evaluation_id)
            if existing:
                same = (
                    existing.model_ref == normalized.model_ref
                    and existing.gate_metric_value == normalized.gate_metric_value
                )
                return LifecycleOperationResult(
                    status="duplicate" if same else "evaluation_id_conflict",
                    changed=False,
                    reason=None if same else "同一 evaluation_id 已登记不同模型或指标",
                    registration=existing,
                )

            if qualification_validator is not None:
                allowed, reason = _validation_decision(
                    _call_callback(qualification_validator, normalized, path, slot),
                    "qualification_validator_rejected",
                )
                if not allowed:
                    normalized.qualified = False
                    normalized.blocking_reasons.append(reason or "qualification_validator_rejected")

            state.path_models.setdefault(path, PathModelState()).challengers.append(normalized)
            before = (
                state.production_path,
                state.fallback_path,
                state.active_activation_epoch_id,
            )
            self._save_slot(slot, state)
            after = (
                state.production_path,
                state.fallback_path,
                state.active_activation_epoch_id,
            )
            if before != after:
                raise AssertionError("Challenger 登记不得修改生产路径、fallback 或 active Epoch")
            return LifecycleOperationResult(
                status="registered" if normalized.qualified else "registered_blocked",
                changed=True,
                reason=(normalized.blocking_reasons[0] if normalized.blocking_reasons else None),
                registration=normalized,
            )

    def promote_within_path(
        self,
        modeling_path: str,
        evaluation_id: str,
        *,
        slot: str = DEFAULT_SLOT,
        promotion_margin: float = 0.0,
        metric_direction: str = "higher_is_better",
        production_contract_validator: Optional[ValidationCallback] = None,
    ) -> LifecycleOperationResult:
        """严格门控后把指定路径 Challenger 晋升为唯一 Champion。

        高值指标要求 ``challenger > champion + margin``；低值指标要求
        ``challenger < champion - margin``，因此默认 margin=0 时平局也不会晋升。
        成功只追加 PromotionEvent；production_path/fallback/active Epoch 均保持不变。
        """
        path = _canonical_modeling_path(modeling_path)
        if path not in _ALLOWED_MODELING_PATHS:
            raise ValueError(f"不支持的 modeling_path: {path}")
        if promotion_margin < 0:
            raise ValueError("promotion_margin 不能为负数")
        if metric_direction not in {"higher_is_better", "lower_is_better"}:
            raise ValueError("metric_direction 必须是 higher_is_better 或 lower_is_better")

        with self._lock_for_slot(slot):
            state = self.get_slot(slot)
            path_state = state.path_models.get(path)
            if path_state is None:
                return LifecycleOperationResult("not_found", False, "该路径尚无模型登记")
            if path_state.champion and path_state.champion.evaluation_id == evaluation_id:
                return LifecycleOperationResult(
                    "already_promoted", False, registration=path_state.champion
                )
            candidate = next(
                (item for item in path_state.challengers if item.evaluation_id == evaluation_id),
                None,
            )
            if candidate is None:
                return LifecycleOperationResult("not_found", False, "该路径不存在指定 Challenger")
            if not candidate.qualified or candidate.blocking_reasons:
                return LifecycleOperationResult(
                    "rejected",
                    False,
                    "; ".join(candidate.blocking_reasons) or "challenger_not_qualified",
                    candidate,
                )

            champion = path_state.champion
            if champion is not None:
                if metric_direction == "higher_is_better":
                    metric_passed = candidate.gate_metric_value > (
                        champion.gate_metric_value + promotion_margin
                    )
                else:
                    metric_passed = candidate.gate_metric_value < (
                        champion.gate_metric_value - promotion_margin
                    )
                if not metric_passed:
                    reason = "promotion_margin_not_met"
                    candidate.qualified = False
                    candidate.blocking_reasons.append(reason)
                    self._save_slot(slot, state)
                    return LifecycleOperationResult("rejected", True, reason, candidate)

            if production_contract_validator is not None:
                allowed, reason = _validation_decision(
                    _call_callback(
                        production_contract_validator,
                        candidate,
                        champion,
                        path,
                        slot,
                    ),
                    "production_contract_rejected",
                )
                if not allowed:
                    candidate.qualified = False
                    candidate.blocking_reasons.append(reason or "production_contract_rejected")
                    self._save_slot(slot, state)
                    return LifecycleOperationResult(
                        "rejected", True, reason or "production_contract_rejected", candidate
                    )

            old_payload = state.to_dict()
            invariant = (
                state.production_path,
                state.fallback_path,
                state.active_activation_epoch_id,
            )
            path_state.challengers = [
                item for item in path_state.challengers if item.evaluation_id != evaluation_id
            ]
            if champion is not None:
                path_state.retired.append(champion)
            path_state.champion = candidate
            promoted_at = _utc_now()
            event = PromotionEvent(
                promotion_event_id=_stable_id("pvprom", slot, path, evaluation_id),
                modeling_path=path,
                champion_model_ref=candidate.model_ref,
                challenger_model_ref=candidate.model_ref,
                evaluation_id=evaluation_id,
                promoted_at=promoted_at,
                previous_champion_model_ref=champion.model_ref if champion else None,
                champion_gate_metric_value=champion.gate_metric_value if champion else None,
                challenger_gate_metric_value=candidate.gate_metric_value,
                promotion_margin=float(promotion_margin),
                metric_direction=metric_direction,
            )
            try:
                self._save_slot(slot, state)
                self._promotion_store(slot).append_if_absent(event)
            except Exception as exc:
                try:
                    restored = PVSlotState.from_dict(old_payload)
                    self._save_slot(slot, restored)
                except Exception as rollback_exc:
                    raise RuntimeError(
                        "PromotionEvent 追加失败且 Registry 补偿恢复失败"
                    ) from rollback_exc
                raise RuntimeError(
                    "PromotionEvent 追加失败，Registry 已补偿恢复到晋升前状态"
                ) from exc

            current_invariant = (
                state.production_path,
                state.fallback_path,
                state.active_activation_epoch_id,
            )
            if invariant != current_invariant:
                raise AssertionError("路径内晋升不得修改 production_path/fallback/active Epoch")
            return LifecycleOperationResult("promoted", True, registration=candidate, event=event)

    def update_note(self, slot: str, note: Optional[str]) -> PVSlotState:
        """同路径 PUT：只覆盖允许的登记备注，不建 Epoch、不写 PathSwitchEvent。"""
        if note is not None and len(str(note)) > 500:
            raise ValueError("note 最长 500 字符")
        with self._lock_for_slot(slot):
            state = self.get_slot(slot)
            state.note = None if note is None else str(note)
            self._save_slot(slot, state)
            return self.get_slot(slot)

    def commit_path_switch(
        self,
        slot: str,
        *,
        production_path: str,
        activation_epoch_id: str,
        note: Optional[str] = None,
    ) -> PVSlotState:
        """由跨路径协调器写入 production_path 与 active Epoch；不追加 PromotionEvent。"""
        path = _canonical_modeling_path(production_path)
        if path not in _ALLOWED_MODELING_PATHS:
            raise ValueError(f"不支持的 modeling_path: {path}")
        epoch_id = str(activation_epoch_id or "").strip()
        if not epoch_id:
            raise ValueError("activation_epoch_id 不可为空")
        if note is not None and len(str(note)) > 500:
            raise ValueError("note 最长 500 字符")
        with self._lock_for_slot(slot):
            state = self.get_slot(slot)
            if path == state.fallback_path:
                state.fallback_path = state.production_path
            state.production_path = path
            state.active_activation_epoch_id = epoch_id
            if note is not None:
                state.note = str(note)
            self._save_slot(slot, state)
            return self.get_slot(slot)

    def restore_slot_state(self, slot: str, snapshot: PVSlotState) -> None:
        """切换失败补偿：把 Registry 恢复到事务开始前的快照。"""
        with self._lock_for_slot(slot):
            restored = copy.deepcopy(snapshot)
            self._save_slot(slot, restored)

    def switch_path(self, request: Any) -> Any:
        """只委托任务 10.3 注入的跨路径协调器；未注入时明确拒绝，绝不旁路九项门控。"""
        if self._switch_coordinator is None:
            raise RuntimeError(
                "跨路径切换协调器尚未注入；九项门控与原子切换由任务 10.1/10.3 实现"
            )
        coordinator = self._switch_coordinator
        switch_method = getattr(coordinator, "switch", None)
        return switch_method(request) if callable(switch_method) else coordinator(request)

    def migrate_legacy_state(
        self,
        old_state: Dict[str, Any],
        artifact_validator: ValidationCallback,
        contract_validator: ValidationCallback,
        *,
        slot: Optional[str] = None,
    ) -> MigrationResult:
        """保守、幂等地迁移旧 path_models 与 path_switch_audit。

        工件可加载且生产契约确认的 latest_model 才成为 Champion；否则保留为带阻断原因的
        Challenger。旧审计只有字段足以构造真实新事件时才分类，缺字段项原样保留在
        ``legacy_audit``，不制造 comparison/Epoch/device scope 等历史事实。
        """
        target_slot = str(slot or old_state.get("slot") or DEFAULT_SLOT)
        source_digest = _payload_digest(old_state)
        with self._lock_for_slot(target_slot):
            current = self.get_slot(target_slot)
            migration = current.migration
            if (
                migration.get("version") == _MIGRATION_VERSION
                and migration.get("source_digest") == source_digest
            ):
                return MigrationResult("already_migrated", False)

            old_payload = current.to_dict()
            state = copy.deepcopy(current)
            production_path = _canonical_modeling_path(
                old_state.get("production_path") or state.production_path
            )
            fallback_path = _canonical_modeling_path(
                old_state.get("fallback_path") or state.fallback_path
            )
            if production_path in _ALLOWED_MODELING_PATHS:
                state.production_path = production_path
            if fallback_path in _ALLOWED_MODELING_PATHS and fallback_path != state.production_path:
                state.fallback_path = fallback_path

            champions = 0
            challengers = 0
            raw_models = dict(old_state.get("path_models") or {})
            canonical_entries: Dict[str, Dict[str, Any]] = {}
            for raw_path, raw_entry in raw_models.items():
                path = _canonical_modeling_path(raw_path)
                if path not in _ALLOWED_MODELING_PATHS or not isinstance(raw_entry, dict):
                    continue
                if "champion" in raw_entry or "challengers" in raw_entry:
                    continue
                existing = canonical_entries.get(path)
                if existing is None or str(raw_entry.get("updated_at") or "") > str(
                    existing.get("updated_at") or ""
                ):
                    canonical_entries[path] = dict(raw_entry)

            for path, legacy_entry in canonical_entries.items():
                model_ref = str(legacy_entry.get("model_ref") or "").strip()
                if not model_ref:
                    continue
                try:
                    normalized_ref = to_relative_path(model_ref, base_dir=_BACKEND_SERVICE_DIR)
                    artifact_ok, artifact_reason = _validation_decision(
                        _call_callback(artifact_validator, normalized_ref, path, legacy_entry),
                        "legacy_artifact_unloadable",
                    )
                except (TypeError, ValueError) as exc:
                    normalized_ref = model_ref
                    artifact_ok, artifact_reason = False, f"legacy_artifact_invalid: {exc}"
                contract_ok, contract_reason = _validation_decision(
                    _call_callback(contract_validator, normalized_ref, path, legacy_entry),
                    "legacy_contract_unconfirmed",
                )
                reasons = [
                    reason
                    for ok, reason in (
                        (artifact_ok, artifact_reason),
                        (contract_ok, contract_reason),
                    )
                    if not ok and reason
                ]
                metrics = dict(legacy_entry.get("metrics") or {})
                gate_value = legacy_entry.get("gate_metric_value")
                metric_name = legacy_entry.get("metric_name")
                if gate_value is None:
                    for key in ("macro_f1_mean", "accuracy_mean", "f1", "accuracy"):
                        if metrics.get(key) is not None:
                            gate_value = metrics[key]
                            metric_name = key
                            break
                evaluation_id = str(legacy_entry.get("evaluation_id") or "").strip() or _stable_id(
                    "legacy-eval",
                    target_slot,
                    path,
                    legacy_entry.get("request_id"),
                    normalized_ref,
                    legacy_entry.get("updated_at"),
                )
                registration = ModelRegistration(
                    model_ref=normalized_ref,
                    evaluation_id=evaluation_id,
                    gate_metric_value=float(gate_value or 0.0),
                    registered_at=str(legacy_entry.get("updated_at") or ""),
                    candidate_id=_stable_id("pvcand", target_slot, path, evaluation_id),
                    qualified=artifact_ok and contract_ok,
                    blocking_reasons=reasons,
                    metric_name=str(metric_name) if metric_name else None,
                    metadata={
                        "legacy_request_id": legacy_entry.get("request_id"),
                        "legacy_metrics": metrics,
                    },
                )
                existing = self._find_evaluation(state, evaluation_id)
                if existing:
                    continue
                path_state = state.path_models.setdefault(path, PathModelState())
                if artifact_ok and contract_ok and path_state.champion is None:
                    path_state.champion = registration
                    champions += 1
                else:
                    if artifact_ok and contract_ok and path_state.champion is not None:
                        registration.qualified = False
                        registration.blocking_reasons.append("legacy_champion_conflict")
                    path_state.challengers.append(registration)
                    challengers += 1

            promotion_events: List[PromotionEvent] = []
            path_switch_events: List[PathSwitchEvent] = []
            legacy_audit_added = 0
            raw_audits = list(old_state.get("path_switch_audit") or []) + list(
                old_state.get("production_path_history") or []
            )
            known_legacy = {_payload_digest(item) for item in state.legacy_audit}
            for audit in raw_audits:
                if not isinstance(audit, dict):
                    continue
                from_path = _canonical_modeling_path(audit.get("from_path", audit.get("from")))
                to_path = _canonical_modeling_path(audit.get("to_path", audit.get("to")))
                path = _canonical_modeling_path(audit.get("path") or to_path or from_path)
                timestamp = str(
                    audit.get("promoted_at") or audit.get("switched_at") or audit.get("at") or ""
                )
                evaluation_id = str(audit.get("evaluation_id") or "").strip()
                challenger_ref = str(
                    audit.get("challenger_model_ref") or audit.get("model_ref") or ""
                ).strip()
                action = str(audit.get("action") or "").strip()
                is_promotion = (
                    action in {"promotion", "model_promoted", "same_path_model_replaced"}
                    or (from_path and from_path == to_path)
                )
                if (
                    is_promotion
                    and path in _ALLOWED_MODELING_PATHS
                    and evaluation_id
                    and challenger_ref
                    and timestamp
                ):
                    promotion_events.append(
                        PromotionEvent(
                            promotion_event_id=str(audit.get("promotion_event_id") or "")
                            or _stable_id("legacy-prom", target_slot, path, evaluation_id),
                            modeling_path=path,
                            champion_model_ref=str(
                                audit.get("champion_model_ref") or challenger_ref
                            ),
                            challenger_model_ref=challenger_ref,
                            evaluation_id=evaluation_id,
                            promoted_at=timestamp,
                            previous_champion_model_ref=audit.get("previous_champion_model_ref"),
                        )
                    )
                    continue

                required_switch_fields = (
                    from_path,
                    to_path,
                    audit.get("comparison_id"),
                    audit.get("activation_epoch_id"),
                    audit.get("effective_from_date"),
                    audit.get("device_scope_digest"),
                    audit.get("activation_mode"),
                    audit.get("operator"),
                    audit.get("reason"),
                    timestamp,
                )
                if from_path != to_path and all(required_switch_fields):
                    path_switch_events.append(
                        PathSwitchEvent(
                            path_switch_event_id=str(audit.get("path_switch_event_id") or "")
                            or _stable_id(
                                "legacy-switch",
                                target_slot,
                                from_path,
                                to_path,
                                audit.get("comparison_id"),
                            ),
                            from_path=from_path,
                            to_path=to_path,
                            comparison_id=str(audit["comparison_id"]),
                            activation_epoch_id=str(audit["activation_epoch_id"]),
                            effective_from_date=str(audit["effective_from_date"]),
                            device_scope_digest=str(audit["device_scope_digest"]),
                            device_scope_count=int(audit.get("device_scope_count") or 0),
                            activation_mode=str(audit["activation_mode"]),
                            operator=str(audit["operator"]),
                            reason=str(audit["reason"]),
                            switched_at=timestamp,
                        )
                    )
                    continue

                digest = _payload_digest(audit)
                if digest not in known_legacy:
                    state.legacy_audit.append(copy.deepcopy(audit))
                    known_legacy.add(digest)
                    legacy_audit_added += 1

            try:
                self._save_slot(target_slot, state)
                promotion_count = sum(
                    1
                    for event in promotion_events
                    if self._promotion_store(target_slot).append_if_absent(event)
                )
                switch_count = sum(
                    1
                    for event in path_switch_events
                    if self._path_switch_store(target_slot).append_if_absent(event)
                )
                state.migration = {
                    "version": _MIGRATION_VERSION,
                    "source_digest": source_digest,
                    "migrated_at": _utc_now(),
                }
                self._save_slot(target_slot, state)
            except Exception as exc:
                self._save_slot(target_slot, PVSlotState.from_dict(old_payload))
                raise RuntimeError("旧 Registry 状态迁移失败，Registry 已补偿恢复") from exc

            return MigrationResult(
                "migrated",
                True,
                champions_migrated=champions,
                challengers_migrated=challengers,
                promotion_events_migrated=promotion_count,
                path_switch_events_migrated=switch_count,
                legacy_audit_preserved=legacy_audit_added,
            )


class ProductionPathPointer:
    """无状态生产路径门面：get/switch 均直接委托同一个 PVModelRegistry。"""

    def __init__(self, registry: PVModelRegistry) -> None:
        self._registry = registry

    def get(self, slot: str = DEFAULT_SLOT) -> str:
        return self._registry.get_slot(slot).production_path

    def switch(self, request: Any) -> Any:
        return self._registry.switch_path(request)


def migrate_legacy_state(
    old_state: Dict[str, Any],
    artifact_validator: ValidationCallback,
    contract_validator: ValidationCallback,
    *,
    registry: Optional[PVModelRegistry] = None,
    slot: Optional[str] = None,
) -> MigrationResult:
    """模块级兼容入口；默认迁移到部署配置指定的 PVModelRegistry。"""
    target_registry = registry or PVModelRegistry()
    return target_registry.migrate_legacy_state(
        old_state,
        artifact_validator,
        contract_validator,
        slot=slot,
    )
# @AI_GENERATED: end
