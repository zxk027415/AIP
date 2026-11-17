# @AI_GENERATED: 正常光伏闭环的累计训练集账本、不可变快照与阈值重训请求
"""正常光伏迭代标注的累计训练集服务。

该服务只接收人工确认的 ``confirm``、``correct``、``new_label`` 裁决；未审核数据和
``skip`` 不会进入训练集。每个审核单元以 ``review_id + unit_key`` 幂等记录，改判覆盖旧标签
且只计作一次新增训练变更。达到阈值后，服务会冻结一个不可变的全量 CSV 快照并创建重训请求。

持久化约定：所有写入状态、导入源和快照路径均使用相对于项目根目录的路径，避免机器路径泄漏。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

import pandas as pd

from .backfill import BackfillService
from .accuracy_gated_retrainer import AccuracyGatedRetrainer, EvaluationContract
from .pv_model_registry import LifecycleOperationResult, PVModelRegistry
from .storage.file_backend import (
    FileGroundTruthRepository,
    FileReviewResultRepository,
    _atomic_write_json,
    _get_data_root,
)


_VALID_GROUND_TRUTH_ACTIONS = frozenset({"confirm", "correct", "new_label"})
_DEFAULT_RETRAIN_LABEL_THRESHOLD = 200
_DEFAULT_RETRAIN_PERIOD_DAYS = 7
# 建模路径：天级传统模型、全天逐点序列模型、时序分类诊断（TSC MultiRocket）。
_ALLOWED_MODELING_PATHS = frozenset({"legacy_day", "seq_annotation", "tsc"})
_LEGACY_DAY_PATH_ALIASES = frozenset(
    {"point_label_by_day", "point_label_by_day_night"}
)
_DEFAULT_PRODUCTION_PATH = "legacy_day"
_DEFAULT_FALLBACK_PATH = "seq_annotation"
_MODELING_PATH_SCHEMA_VERSION = 3


def _canonical_modeling_path(value: Any) -> str:
    """把历史 RF 切分路径归并到天级路径；切分策略不再充当业务路径。"""
    key = str(value or "").strip()
    return "legacy_day" if key in _LEGACY_DAY_PATH_ALIASES else key


def _normalize_modeling_path_state(state: Dict[str, Any]) -> bool:
    """将旧三路径状态迁移为 legacy_day / seq_annotation 两路径状态。"""
    changed = False
    raw_production = str(state.get("production_path") or _DEFAULT_PRODUCTION_PATH).strip()
    production_path = _canonical_modeling_path(raw_production)
    if production_path not in _ALLOWED_MODELING_PATHS:
        production_path = _DEFAULT_PRODUCTION_PATH

    path_models = dict(state.get("path_models") or {})
    alias_entries = {
        key: dict(path_models[key])
        for key in _LEGACY_DAY_PATH_ALIASES
        if isinstance(path_models.get(key), dict)
    }
    if alias_entries:
        preferred_key: Optional[str] = None
        if raw_production in alias_entries:
            preferred_key = raw_production
        elif "legacy_day" not in path_models:
            preferred_key = max(
                alias_entries,
                key=lambda key: str(alias_entries[key].get("updated_at") or ""),
            )
        if preferred_key is not None and path_models.get("legacy_day") != alias_entries[preferred_key]:
            path_models["legacy_day"] = alias_entries[preferred_key]
            changed = True
    for alias in _LEGACY_DAY_PATH_ALIASES:
        if path_models.pop(alias, None) is not None:
            changed = True

    fallback_path = _canonical_modeling_path(state.get("fallback_path"))
    if fallback_path not in _ALLOWED_MODELING_PATHS or fallback_path == production_path:
        # 从允许的路径中选一个不等于 production 的作为 fallback
        candidates = sorted(p for p in _ALLOWED_MODELING_PATHS if p != production_path)
        fallback_path = candidates[0] if candidates else "legacy_day"

    for key, value in (
        ("production_path", production_path),
        ("fallback_path", fallback_path),
        ("path_models", path_models),
    ):
        if state.get(key) != value:
            state[key] = value
            changed = True

    model_path_key = _canonical_modeling_path(state.get("production_model_path_key"))
    if model_path_key in _ALLOWED_MODELING_PATHS and state.get("production_model_path_key") != model_path_key:
        state["production_model_path_key"] = model_path_key
        changed = True

    for request in (state.get("retrain_requests") or {}).values():
        target = _canonical_modeling_path(request.get("target_modeling_path"))
        if target in _ALLOWED_MODELING_PATHS and request.get("target_modeling_path") != target:
            request["target_modeling_path"] = target
            changed = True
        train_summary = request.get("train_summary")
        if isinstance(train_summary, dict):
            result_path = _canonical_modeling_path(train_summary.get("modeling_path"))
            if result_path in _ALLOWED_MODELING_PATHS and train_summary.get("modeling_path") != result_path:
                train_summary["modeling_path"] = result_path
                changed = True

    for audit in state.get("path_switch_audit") or []:
        for field in ("from_path", "to_path", "path"):
            canonical = _canonical_modeling_path(audit.get(field))
            if canonical in _ALLOWED_MODELING_PATHS and audit.get(field) != canonical:
                audit[field] = canonical
                changed = True
    for history in state.get("production_path_history") or []:
        for field in ("from", "to"):
            canonical = _canonical_modeling_path(history.get(field))
            if canonical in _ALLOWED_MODELING_PATHS and history.get(field) != canonical:
                history[field] = canonical
                changed = True

    if int(state.get("schema_version") or 1) < _MODELING_PATH_SCHEMA_VERSION:
        state["schema_version"] = _MODELING_PATH_SCHEMA_VERSION
        changed = True
    return changed


def _ensure_retrain_watermarks(state: Dict[str, Any]) -> bool:
    """为旧状态补按路径消费水位，保留全局 pending 字段供旧 UI 兼容。"""

    changed = False
    raw = state.get("retrain_watermarks")
    if not isinstance(raw, dict):
        raw = {}
        state["retrain_watermarks"] = raw
        changed = True
    legacy_pending = max(0, int(state.get("pending_change_count") or 0))
    production_path = _canonical_modeling_path(
        state.get("production_path") or _DEFAULT_PRODUCTION_PATH
    )
    now = datetime.utcnow().isoformat()
    for path in sorted(_ALLOWED_MODELING_PATHS):
        item = raw.get(path)
        if not isinstance(item, dict):
            item = {
                "consumed_sequence": 0,
                "pending_change_count": legacy_pending if path == production_path else 0,
                "last_consumed_at": None,
                "last_failed_sequence": 0,
                "last_failed_pending_count": 0,
                "updated_at": now,
            }
            raw[path] = item
            changed = True
        else:
            defaults = {
                "consumed_sequence": 0,
                "pending_change_count": 0,
                "last_consumed_at": None,
                "last_failed_sequence": 0,
                "last_failed_pending_count": 0,
                "updated_at": now,
            }
            for field, default in defaults.items():
                if field not in item:
                    item[field] = default
                    changed = True
            item["consumed_sequence"] = max(0, int(item.get("consumed_sequence") or 0))
            item["pending_change_count"] = max(
                0, int(item.get("pending_change_count") or 0)
            )
    return changed


def _record_path_change(
    state: Dict[str, Any],
    modeling_paths: List[str],
    units: int = 1,
) -> None:
    """把一次共享标签事实变更投影到可消费该粒度的路径计数。"""

    _ensure_retrain_watermarks(state)
    delta = max(0, int(units))
    now = datetime.utcnow().isoformat()
    for raw_path in modeling_paths:
        path = _canonical_modeling_path(raw_path)
        if path not in _ALLOWED_MODELING_PATHS:
            raise ValueError(f"不支持的建模路径: {path}")
        watermark = state["retrain_watermarks"][path]
        watermark["pending_change_count"] = int(
            watermark.get("pending_change_count") or 0
        ) + delta
        watermark["updated_at"] = now


_STATE_LOCKS: Dict[str, threading.RLock] = defaultdict(threading.RLock)
logger = logging.getLogger(__name__)


class CumulativeTrainingService:
    """维护指定 slot 的唯一累计训练集和重训请求队列。

    输入为审核会话的完整状态及单条裁决；输出为当前累计状态。快照包含：
    1. 已通过 ``register_labeled_dataset`` 登记的带真值导入数据；
    2. 当前账本内所有有效审核会话回贴出的原始时序数据。

    ``BackfillService.backfill_to_raw_dataset`` 负责复用现有的原始时序回贴、窗口归一化和标签过滤
    逻辑，本服务只负责跨会话去重、快照冻结和重训请求状态机。
    """

    def __init__(
        self,
        slot: str = "default",
        review_repo: Optional[FileReviewResultRepository] = None,
        data_root: Optional[Path] = None,
        retrain_label_threshold: Optional[int] = None,
        retrain_period_days: Optional[int] = None,
        pv_model_registry: Optional[PVModelRegistry] = None,
    ) -> None:
        self.slot = str(slot or "default")
        self.review_repo = review_repo or FileReviewResultRepository()
        self.data_root = (data_root or _get_data_root()).resolve()
        self.project_root = Path(__file__).resolve().parents[3]
        self.root = self.data_root / "cumulative_training" / self.slot
        self.state_path = self.root / "state.json"
        # Registry 是新模型治理真相；仅在对应 slot 文件真实存在时优先读取，缺文件继续
        # 使用旧 state.json，避免兼容期把 Registry 的内置默认态误当成已迁移数据。
        self._pv_model_registry = pv_model_registry or PVModelRegistry()
        configured_threshold = (
            retrain_label_threshold
            if retrain_label_threshold is not None
            else os.getenv("PV_RETRAIN_LABEL_THRESHOLD", _DEFAULT_RETRAIN_LABEL_THRESHOLD)
        )
        try:
            self.retrain_label_threshold = max(1, int(configured_threshold))
        except (TypeError, ValueError):
            self.retrain_label_threshold = _DEFAULT_RETRAIN_LABEL_THRESHOLD
        configured_period = (
            retrain_period_days
            if retrain_period_days is not None
            else os.getenv("PV_RETRAIN_PERIOD_DAYS", _DEFAULT_RETRAIN_PERIOD_DAYS)
        )
        try:
            self.retrain_period_days = max(1, int(configured_period))
        except (TypeError, ValueError):
            self.retrain_period_days = _DEFAULT_RETRAIN_PERIOD_DAYS
        self._lock = _STATE_LOCKS[str(self.state_path)]

    def get_state(self) -> Dict[str, Any]:
        """返回可展示的累计训练状态，不暴露本机绝对路径。"""
        with self._lock:
            state = self._load_state()
            auto_request = self._maybe_create_auto_retrain_request(state)
            self._save_state(state)
            summary = self._summarize_state(state)
            if auto_request and auto_request.get("auto_execute"):
                summary["_auto_retrain_request_id"] = auto_request["request_id"]
            return summary

    def request_manual_retrain(
        self,
        target_modeling_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """基于当前累计训练集立即创建指定建模路径的手动重训请求。"""
        with self._lock:
            state = self._load_state()
            active_running = next(
                (
                    request
                    for request in state["retrain_requests"].values()
                    if request.get("status") == "running"
                ),
                None,
            )
            if active_running is not None:
                raise ValueError("已有重训正在执行，请等待完成后再手动触发")
            request = self._create_retrain_request(
                state,
                trigger_reason="manual",
                target_modeling_path=target_modeling_path,
            )
            if request is None:
                blocker = state.get("last_retrain_blocker") or "累计训练集不满足重训条件"
                raise ValueError(str(blocker))
            self._save_state(state)
            summary = self._summarize_state(state)
            summary["retrain_request"] = request
            return summary

    def reserve_manual_retrain_request(
        self,
        target_modeling_path: Optional[str] = None,
        *,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """登记一条「待冻结快照」的手动重训请求，本身不做任何重活，立即返回。

        与 ``request_manual_retrain`` 的唯一区别是**不在调用线程里构建快照**。
        快照冻结要全量拉取测量数据（实测约 660s），远超前端 axios 的 120s 超时；
        原同步实现下浏览器在 120s 中断后就再也不会调用 ``/run``，请求于是永久
        停在 ``queued`` / 进度 0%，表现为「点重训没反应」。快照改由后台线程的
        ``attach_snapshot_to_request`` 完成。

        Returns:
            ``_summarize_state`` 结果，并附 ``retrain_request`` 为新建请求。
        Raises:
            ValueError: 已有重训在执行、正在准备快照或路径无效。
        """
        requested_path = str(target_modeling_path or "").strip() or None
        if requested_path is not None and requested_path not in _ALLOWED_MODELING_PATHS:
            raise ValueError(f"不支持的建模路径: {requested_path}")
        with self._lock:
            state = self._load_state()
            requested_path = requested_path or _canonical_modeling_path(
                state.get("production_path") or _DEFAULT_PRODUCTION_PATH
            )
            _ensure_retrain_watermarks(state)
            running = next(
                (
                    request
                    for request in state["retrain_requests"].values()
                    if request.get("status") == "running"
                ),
                None,
            )
            if running is not None:
                raise ValueError("已有重训正在执行，请等待完成后再手动触发")
            preparing = next(
                (
                    request
                    for request in state["retrain_requests"].values()
                    if request.get("status") == "queued" and request.get("active_job")
                ),
                None,
            )
            if preparing is not None:
                raise ValueError("已有重训正在冻结快照，请等待完成后再手动触发")

            now = datetime.utcnow().isoformat()
            # 沿用 _create_retrain_request 的既有语义：新请求取代旧的排队请求。
            for request in state["retrain_requests"].values():
                if request.get("status") == "queued":
                    request["status"] = "cancelled"
                    request["cancelled_reason"] = "superseded_by_newer_snapshot"
                    request["updated_at"] = now
                    request["finished_at"] = now

            request_id = f"retrain-{uuid.uuid4().hex[:12]}"
            request = {
                "request_id": request_id,
                "status": "queued",
                # active_job 标记「这条请求有后台线程正在推进」，用于拒绝并发手动触发；
                # 与历史遗留的 queued 请求区分开。
                "active_job": True,
                "snapshot_id": None,
                "dataset_path": None,
                "sample_count": None,
                "label_count": None,
                "target_modeling_path": requested_path,
                "overrides": overrides if isinstance(overrides, dict) else None,
                "trigger_reason": "manual",
                "auto_execute": False,
                "triggered_change_count": int(
                    state["retrain_watermarks"][requested_path].get("pending_change_count") or 0
                ),
                "consumed_through_sequence": int(state.get("next_sequence") or 0),
                "pending_reset_on_create": False,
                "threshold": self.retrain_label_threshold,
                "created_at": now,
                "updated_at": now,
                "progress": {
                    "stage": "preparing_snapshot",
                    "percent": 3,
                    "message": "正在冻结累计训练快照（需全量拉取测量数据，通常数分钟）",
                    "updated_at": now,
                },
            }
            state["retrain_requests"][request_id] = request
            self._save_state(state)
            summary = self._summarize_state(state)
            summary["retrain_request"] = dict(request)
            return summary

    def attach_snapshot_to_request(self, request_id: str) -> Dict[str, Any]:
        """后台线程调用：冻结快照并回填到请求，使其可被 ``/run`` 执行。

        已带 ``dataset_path`` 的请求直接返回，因此对「复用已有快照的排队请求」
        也是安全的（后台执行既有 queued 请求时会走到这里）。

        快照构建刻意放在锁外：它耗时数分钟，若持锁会把 ``get_state`` 的状态轮询
        一起堵死，前端整页转圈——那正是本次修复要消除的现象之一。
        """
        with self._lock:
            state = self._load_state()
            request = state["retrain_requests"].get(request_id)
            if request is None:
                raise KeyError(request_id)
            if str(request.get("dataset_path") or "").strip():
                return dict(request)
            if request.get("status") != "queued":
                raise ValueError(f"状态 {request.get('status')} 不允许冻结快照")
            target_modeling_path = request.get("target_modeling_path")

        scratch = self._load_state()
        snapshot = self._create_snapshot(
            scratch,
            target_modeling_path=target_modeling_path,
        )

        with self._lock:
            state = self._load_state()
            request = state["retrain_requests"].get(request_id)
            if request is None:
                raise KeyError(request_id)
            if request.get("status") != "queued":
                raise ValueError(f"状态 {request.get('status')} 不允许回填快照")
            now = datetime.utcnow().isoformat()
            state["snapshots"][snapshot["snapshot_id"]] = snapshot
            request.update(
                {
                    "snapshot_id": snapshot["snapshot_id"],
                    "dataset_path": snapshot["dataset_path"],
                    "sample_count": snapshot["sample_count"],
                    "label_count": snapshot["label_count"],
                    "updated_at": now,
                    "progress": {
                        "stage": "snapshot_ready",
                        "percent": 8,
                        "message": (
                            f"快照已冻结（{snapshot['sample_count']} 样本 / "
                            f"{snapshot['label_count']} 类），即将开始训练"
                        ),
                        "updated_at": now,
                    },
                }
            )
            state.pop("last_retrain_blocker", None)
            self._save_state(state)
            return dict(request)

    def clear_retrain_job_flag(self, request_id: str) -> None:
        """清除 ``active_job`` 标记，避免后台线程异常退出后永久占位。"""
        with self._lock:
            state = self._load_state()
            request = state["retrain_requests"].get(request_id)
            if request is None:
                return
            if request.pop("active_job", None) is not None:
                self._save_state(state)

    def admit_verdict(
        self,
        review_id: str,
        session: Dict[str, Any],
        verdict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """同步一条人工裁决到累计账本，并在阈值达到时冻结快照。

        有效真值会按 ``review_id + unit_key`` 幂等写入；同一单元改判覆盖旧标签且仅产生一次
        新变更。若改为 ``skip``，已有有效标签会从账本撤出，确保后续快照不保留已撤销真值。
        """
        unit_key = str(verdict.get("unit_key") or "").strip()
        if not review_id or not unit_key:
            raise ValueError("review_id 和 unit_key 不能为空")
        entry_key = f"{review_id}|{unit_key}"
        is_ground_truth = (
            bool(verdict.get("is_ground_truth"))
            and verdict.get("action_type") in _VALID_GROUND_TRUTH_ACTIONS
        )

        if not is_ground_truth:
            with self._lock:
                state = self._load_state()
                removed = state["verdict_entries"].pop(entry_key, None) is not None
                if removed:
                    state["pending_change_count"] += 1
                    _record_path_change(state, ["legacy_day"], 1)
                request = self._maybe_create_auto_retrain_request(state)
                self._save_state(state)
                summary = self._summarize_state(state)
                summary.update(
                    {
                        "admitted": False,
                        "removed": removed,
                        "reason": "ground_truth_removed" if removed else "not_ground_truth",
                        "retrain_request": request,
                    }
                )
                if request and request.get("auto_execute"):
                    summary["_auto_retrain_request_id"] = request["request_id"]
                return summary

        source_csv_path = str((session.get("prediction_context") or {}).get("source_csv_path") or "").strip()
        if not source_csv_path:
            raise ValueError("审核会话缺少 prediction_context.source_csv_path，无法将人工标签纳入累计训练集")
        if Path(source_csv_path).is_absolute():
            raise ValueError("source_csv_path 必须是相对项目根目录路径")
        if verdict.get("verdict_label") is None:
            raise ValueError("有效人工裁决必须包含 verdict_label")

        normalized = {
            "review_id": review_id,
            "unit_key": unit_key,
            "verdict_label": int(verdict["verdict_label"]),
            "action_type": verdict["action_type"],
            "reviewer": verdict.get("reviewer"),
            "reviewed_at": verdict.get("reviewed_at") or datetime.utcnow().isoformat(),
            "source_csv_path": source_csv_path.replace("\\", "/"),
        }

        with self._lock:
            state = self._load_state()
            previous = state["verdict_entries"].get(entry_key)
            # 同一 review_id + unit_key 的重复提交会刷新 reviewed_at；它不代表训练标签变更，
            # 因而不得消耗一次重训阈值。仅标签语义、动作、审核人或输入数据来源变化才重新计数。
            comparison_keys = {"review_id", "unit_key", "verdict_label", "action_type", "reviewer", "source_csv_path"}
            previous_comparable = (
                {key: previous.get(key) for key in comparison_keys}
                if previous
                else None
            )
            normalized_comparable = {key: normalized.get(key) for key in comparison_keys}
            changed = previous_comparable != normalized_comparable
            if changed:
                state["next_sequence"] += 1
                normalized["sequence"] = state["next_sequence"]
                state["verdict_entries"][entry_key] = normalized
                state["pending_change_count"] += 1
                _record_path_change(state, ["legacy_day"], 1)

            request = self._maybe_create_auto_retrain_request(state)
            self._save_state(state)
            summary = self._summarize_state(state)
            summary.update(
                {
                    "admitted": changed,
                    "reason": "accepted" if changed else "duplicate_verdict",
                    "retrain_request": request,
                }
            )
            if request and request.get("auto_execute"):
                summary["_auto_retrain_request_id"] = request["request_id"]
            return summary

    def admit_day_label_op(
        self,
        review_id: str,
        op_id: str,
        verdict: Dict[str, Any],
        *,
        label_source: str = "human_day",
    ) -> Dict[str, Any]:
        """day_labels 主链路：独立记录天操作，只推进 legacy_day 水位。"""
        if not review_id or not op_id:
            raise ValueError("review_id 和 op_id 不能为空")
        source = str(label_source or "").strip()
        if source not in {"human_day", "day_label", "day_import"}:
            raise ValueError(f"day_label_ops 不接受 source={source!r}")
        entry_key = f"{review_id}|{op_id}"
        is_ground_truth = (
            bool(verdict.get("is_ground_truth"))
            and verdict.get("action_type") in _VALID_GROUND_TRUTH_ACTIONS
        )
        with self._lock:
            state = self._load_state()
            state.setdefault("day_label_ops", {})
            previous = state["day_label_ops"].get(entry_key)
            if not is_ground_truth:
                removed = state["day_label_ops"].pop(entry_key, None) is not None
                if removed:
                    state["pending_change_count"] += 1
                    _record_path_change(state, ["legacy_day"], 1)
                request = self._maybe_create_auto_retrain_request(state)
                self._save_state(state)
                summary = self._summarize_state(state)
                summary.update({
                    "admitted": False,
                    "removed": removed,
                    "reason": "ground_truth_removed" if removed else "not_ground_truth",
                    "retrain_request": request,
                    "snapshot_mode": "day_label",
                })
                return summary
            if verdict.get("verdict_label") is None:
                raise ValueError("有效人工裁决必须包含 verdict_label")
            normalized = {
                "review_id": review_id,
                "op_id": op_id,
                "verdict_label": int(verdict["verdict_label"]),
                "action_type": verdict["action_type"],
                "reviewer": verdict.get("reviewer"),
                "reviewed_at": verdict.get("reviewed_at") or datetime.utcnow().isoformat(),
                "source": source,
            }
            comparison_keys = {
                "review_id", "op_id", "verdict_label", "action_type", "reviewer", "source"
            }
            previous_comparable = (
                {key: previous.get(key) for key in comparison_keys} if previous else None
            )
            normalized_comparable = {key: normalized.get(key) for key in comparison_keys}
            changed = previous_comparable != normalized_comparable
            if changed:
                state["next_sequence"] += 1
                normalized["sequence"] = state["next_sequence"]
                state["day_label_ops"][entry_key] = normalized
                state["pending_change_count"] += 1
                _record_path_change(state, ["legacy_day"], 1)
            request = self._maybe_create_auto_retrain_request(state)
            self._save_state(state)
            summary = self._summarize_state(state)
            summary.update({
                "admitted": changed,
                "reason": "accepted" if changed else "duplicate_op",
                "retrain_request": request,
                "snapshot_mode": "day_label",
                "op_id": op_id,
            })
            if request and request.get("auto_execute"):
                summary["_auto_retrain_request_id"] = request["request_id"]
            return summary

    def admit_point_label_op(
        self,
        review_id: str,
        op_id: str,
        verdict: Dict[str, Any],
        *,
        label_source: str = "human_range",
    ) -> Dict[str, Any]:
        """point_labels 主链路：只保存幂等索引，并按来源投影可消费路径水位。"""
        if not review_id or not op_id:
            raise ValueError("review_id 和 op_id 不能为空")
        source = str(label_source or "").strip()
        if source not in {"human_range", "point_rest_normal", "peer_residual", "pseudo_point"}:
            raise ValueError(f"point_label_ops 不接受 source={source!r}")
        consumable_paths = sorted(_ALLOWED_MODELING_PATHS)
        entry_key = f"{review_id}|{op_id}"
        is_ground_truth = (
            bool(verdict.get("is_ground_truth"))
            and verdict.get("action_type") in _VALID_GROUND_TRUTH_ACTIONS
        )

        if not is_ground_truth:
            with self._lock:
                state = self._load_state()
                state.setdefault("point_label_ops", {})
                previous = state["point_label_ops"].pop(entry_key, None)
                removed = previous is not None
                if removed:
                    state["pending_change_count"] += 1
                    previous_source = str((previous or {}).get("source") or source)
                    previous_paths = (
                        ["legacy_day"]
                        if previous_source in {"day_label", "human_day", "parquet_day_label"}
                        else sorted(_ALLOWED_MODELING_PATHS)
                    )
                    _record_path_change(state, previous_paths, 1)
                request = self._maybe_create_auto_retrain_request(state)
                self._save_state(state)
                summary = self._summarize_state(state)
                summary.update(
                    {
                        "admitted": False,
                        "removed": removed,
                        "reason": "ground_truth_removed" if removed else "not_ground_truth",
                        "retrain_request": request,
                        "snapshot_mode": "point_label",
                    }
                )
                if request and request.get("auto_execute"):
                    summary["_auto_retrain_request_id"] = request["request_id"]
                return summary

        if verdict.get("verdict_label") is None:
            raise ValueError("有效人工裁决必须包含 verdict_label")

        normalized = {
            "review_id": review_id,
            "op_id": op_id,
            "verdict_label": int(verdict["verdict_label"]),
            "action_type": verdict["action_type"],
            "reviewer": verdict.get("reviewer"),
            "reviewed_at": verdict.get("reviewed_at") or datetime.utcnow().isoformat(),
            "source": source,
        }

        with self._lock:
            state = self._load_state()
            state.setdefault("point_label_ops", {})
            previous = state["point_label_ops"].get(entry_key)
            comparison_keys = {
                "review_id", "op_id", "verdict_label", "action_type", "reviewer", "source"
            }
            previous_comparable = (
                {key: previous.get(key) for key in comparison_keys}
                if previous
                else None
            )
            normalized_comparable = {key: normalized.get(key) for key in comparison_keys}
            changed = previous_comparable != normalized_comparable
            if changed:
                state["next_sequence"] += 1
                normalized["sequence"] = state["next_sequence"]
                state["point_label_ops"][entry_key] = normalized
                state["pending_change_count"] += 1
                _record_path_change(state, consumable_paths, 1)

            request = self._maybe_create_auto_retrain_request(state)
            self._save_state(state)
            summary = self._summarize_state(state)
            summary.update(
                {
                    "admitted": changed,
                    "reason": "accepted" if changed else "duplicate_op",
                    "retrain_request": request,
                    "snapshot_mode": "point_label",
                    "op_id": op_id,
                }
            )
            if request and request.get("auto_execute"):
                summary["_auto_retrain_request_id"] = request["request_id"]
            return summary

    def register_labeled_dataset(
        self,
        dataset_path: str,
        source_name: Optional[str] = None,
        *,
        change_units: Optional[int] = None,
    ) -> Dict[str, Any]:
        """登记带真实 ``label`` 列的数据导入，并纳入下一次全量快照。

        未带 ``label`` 列的数据只可作为预测输入，不能通过本方法进入累计训练集。

        ``change_units``：计入重训阈值的变更次数。自由窗打标应传 ``1``（一个诊断样本），
        不传则按带标签行数累加（兼容历史大数据集导入）。
        """
        normalized_path = self._normalize_relative_path(dataset_path)
        frame = self._read_dataset(normalized_path)
        if "label" not in frame.columns:
            raise ValueError("导入数据缺少 label 列；无真值数据必须先预测并完成人工审核")
        labeled_count = int(frame["label"].notna().sum())
        if labeled_count <= 0:
            raise ValueError("导入数据没有有效 label，不能进入累计训练集")

        digest = self._sha256_file(self.project_root / normalized_path)
        import_id = f"imp-{digest[:16]}"
        delta = int(change_units) if change_units is not None else labeled_count
        if delta < 1:
            delta = 1
        with self._lock:
            state = self._load_state()
            existing = state["labeled_imports"].get(import_id)
            if existing is None:
                state["next_sequence"] += 1
                state["labeled_imports"][import_id] = {
                    "import_id": import_id,
                    "dataset_path": normalized_path,
                    "source_name": source_name or Path(normalized_path).name,
                    "row_count": int(len(frame)),
                    "labeled_row_count": labeled_count,
                    "change_units": delta,
                    "content_sha256": digest,
                    "sequence": state["next_sequence"],
                    "registered_at": datetime.utcnow().isoformat(),
                }
                state["pending_change_count"] += delta
                _record_path_change(state, ["legacy_day"], delta)

            request = self._maybe_create_auto_retrain_request(state)
            self._save_state(state)
            summary = self._summarize_state(state)
            summary.update(
                {
                    "imported": existing is None,
                    "import_id": import_id,
                    "change_units": delta if existing is None else 0,
                    "retrain_request": request,
                }
            )
            if request and request.get("auto_execute"):
                summary["_auto_retrain_request_id"] = request["request_id"]
            return summary

    def get_retrain_request(self, request_id: str) -> Dict[str, Any]:
        """读取单个重训请求；不存在时抛出 KeyError。"""
        with self._lock:
            state = self._load_state()
            request = state["retrain_requests"].get(request_id)
            if request is None:
                raise KeyError(request_id)
            return dict(request)

    def get_production_model_ref(self) -> Optional[str]:
        """返回当前生产路径 Champion；Registry 未迁移时才回退旧 state。"""
        with self._lock:
            if self.slot == "pv_fault" and self._pv_model_registry.has_slot(self.slot):
                registry_state = self._pv_model_registry.get_slot(self.slot)
                path_state = registry_state.path_models.get(registry_state.production_path)
                champion = path_state.champion if path_state else None
                return str(champion.model_ref).strip() if champion else None
            state = self._load_state()
            production_ref = str(state.get("production_model_ref") or "").strip()
            if production_ref:
                return production_ref
            latest = self._latest_promoted_request(state)
            return str(latest["model_ref"]).strip() if latest else None

    def get_latest_completed_model_ref(self) -> Optional[str]:
        """兼容旧调用；生产预测应使用 ``get_production_model_ref``。"""
        return self.get_production_model_ref()

    def get_modeling_paths(self) -> Dict[str, Any]:
        """返回生产路径与模型生命周期；pv_fault 有 Registry 后以其为唯一读真相。"""
        with self._lock:
            if self.slot == "pv_fault" and self._pv_model_registry.has_slot(self.slot):
                registry_state = self._pv_model_registry.get_slot(self.slot)
                path_models: Dict[str, Dict[str, Any]] = {}
                for path, lifecycle in registry_state.path_models.items():
                    lifecycle_payload = lifecycle.to_dict()
                    champion = lifecycle.champion
                    path_models[path] = {
                        **lifecycle_payload,
                        "model_ref": champion.model_ref if champion else None,
                        "metrics": (
                            {
                                "metric_name": champion.metric_name,
                                "gate_metric_value": champion.gate_metric_value,
                            }
                            if champion
                            else {}
                        ),
                    }
                production_lifecycle = registry_state.path_models.get(
                    registry_state.production_path
                )
                production_champion = (
                    production_lifecycle.champion if production_lifecycle else None
                )
                return {
                    "available_paths": sorted(_ALLOWED_MODELING_PATHS),
                    "production_path": registry_state.production_path,
                    "fallback_path": registry_state.fallback_path,
                    "active_activation_epoch_id": registry_state.active_activation_epoch_id,
                    "path_models": path_models,
                    "production_model_ref": (
                        production_champion.model_ref if production_champion else None
                    ),
                    "registry_source": "pv_model_registry",
                    "updated_at": registry_state.updated_at,
                    "note": registry_state.note,
                }
            state = self._load_state()
            return self._summarize_modeling_paths(state)

    # seq_annotation 生产登记、显式 Promote 与契约准入门控
    @staticmethod
    def _assert_seq_production_ready(path_entry: Dict[str, Any]) -> None:
        """校验登记项是否完整复现最终 BiLSTM 生产方案。"""
        from services.iterative_labeling.seq_annotation.production_contract import (
            assert_final_sequence_contract,
        )

        raw_contract = path_entry.get("sequence_contract")
        assert_final_sequence_contract(raw_contract)
        contract = dict(raw_contract or {})
        contract["trained_full_day"] = path_entry.get("trained_full_day")
        assert_final_sequence_contract(contract)

    def _gate_metric_from_summary(
        self,
        modeling_path: str,
        summary: Dict[str, Any],
    ) -> float:
        """从重训摘要取守门指标；缺失时记 0，由合同判定阻断而不是猜一个高分。"""

        accuracy = dict(summary.get("accuracy_record") or {})
        if modeling_path == "seq_annotation":
            raw = accuracy.get("point_macro_f1", accuracy.get("macro_f1_mean", summary.get("macro_f1_mean")))
        else:
            raw = accuracy.get("macro_f1_mean", summary.get("macro_f1_mean"))
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return 0.0
        return value if math.isfinite(value) else 0.0

    def _evaluation_contract_from_summary(
        self,
        modeling_path: str,
        summary: Dict[str, Any],
        request_id: str,
    ) -> EvaluationContract:
        """把训练摘要投影为同口径评测合同；字段不足时让 validator 阻断晋升。"""

        accuracy = dict(summary.get("accuracy_record") or {})
        sequence_contract = dict(summary.get("sequence_contract") or {})
        sample_digest = str(
            summary.get("sample_digest")
            or summary.get("label_snapshot_hash")
            or request_id
        ).strip()
        split_digest = str(summary.get("split_digest") or sample_digest).strip()
        seed_raw = summary.get(
            "random_seed",
            accuracy.get("random_seed", 42 if modeling_path == "seq_annotation" else 90),
        )
        try:
            random_seed = int(seed_raw)
        except (TypeError, ValueError):
            random_seed = -1
        if modeling_path == "seq_annotation":
            metric_name = "point_macro_f1"
            try:
                seq_len = int(sequence_contract.get("seq_len") or 0) or None
            except (TypeError, ValueError):
                seq_len = None
            trained_full_day = sequence_contract.get(
                "trained_full_day", summary.get("trained_full_day")
            )
            if not isinstance(trained_full_day, bool):
                trained_full_day = None
            production_contract_valid = trained_full_day is True and seq_len == 288
            production_contract_digest = str(
                summary.get("production_contract_digest")
                or f"seq:{seq_len}:{trained_full_day}"
            ).strip()
        else:
            metric_name = "macro_f1_mean"
            seq_len = None
            trained_full_day = None
            production_contract_valid = True
            production_contract_digest = str(
                summary.get("production_contract_digest")
                or f"legacy:{summary.get('artifact_format') or 'pickle'}"
            ).strip()
        return EvaluationContract(
            sample_digest=sample_digest,
            split_digest=split_digest,
            random_seed=random_seed,
            metric_name=metric_name,
            production_contract_digest=production_contract_digest,
            production_contract_valid=production_contract_valid,
            seq_len=seq_len,
            trained_full_day=trained_full_day,
        )

    def _publish_pv_fault_retrain_to_registry(
        self,
        *,
        request_id: str,
        modeling_path: str,
        model_ref: str,
        summary: Dict[str, Any],
        try_promote: bool,
    ) -> Dict[str, Any]:
        """pv_fault 重训产物只进 Registry：先 Challenger，可选同路径守门，绝不切路径。"""

        production_path_before = self._pv_model_registry.get_slot(self.slot).production_path
        retrainer = AccuracyGatedRetrainer(
            self._pv_model_registry,
            retrain_change_threshold=self.retrain_label_threshold,
            retrain_period_days=self.retrain_period_days,
        )
        contract = self._evaluation_contract_from_summary(modeling_path, summary, request_id)
        metric_value = self._gate_metric_from_summary(modeling_path, summary)
        if try_promote:
            lifecycle = retrainer.register_and_evaluate(
                modeling_path,
                slot=self.slot,
                model_ref=model_ref,
                evaluation_id=request_id,
                gate_metric_value=metric_value,
                contract=contract,
                metadata={"request_id": request_id, "source": "mark_retrain_request"},
            )
        else:
            registered = retrainer.register_challenger(
                modeling_path,
                slot=self.slot,
                model_ref=model_ref,
                evaluation_id=request_id,
                gate_metric_value=metric_value,
                contract=contract,
                metadata={"request_id": request_id, "source": "mark_retrain_request"},
            )
            lifecycle = {
                "registration": registered,
                "promotion": LifecycleOperationResult(
                    status="skipped",
                    changed=False,
                    reason="promote_not_requested",
                    registration=registered.registration,
                ),
            }
        production_path_after = self._pv_model_registry.get_slot(self.slot).production_path
        if production_path_before != production_path_after:
            raise AssertionError("pv_fault Registry 发布不得修改 production_path")
        registration = lifecycle["registration"]
        promotion = lifecycle["promotion"]
        return {
            "registration_status": registration.status,
            "promotion_status": promotion.status,
            "reason": promotion.reason or registration.reason,
            "production_path": production_path_after,
        }

    def set_modeling_paths(
        self,
        production_path: str,
        fallback_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """设置生产主线与备选路径指针（K7）。"""
        prod = str(production_path or "").strip()
        if prod not in _ALLOWED_MODELING_PATHS:
            raise ValueError(f"不支持的生产主线路径: {prod}")
        with self._lock:
            state = self._load_state()
            if fallback_path is None:
                candidates = sorted(p for p in _ALLOWED_MODELING_PATHS if p != prod)
                fb = candidates[0] if candidates else "legacy_day"
            else:
                fb = str(fallback_path or "").strip()
                if not fb:
                    candidates = sorted(p for p in _ALLOWED_MODELING_PATHS if p != prod)
                    fb = candidates[0] if candidates else "legacy_day"
            if fb not in _ALLOWED_MODELING_PATHS:
                raise ValueError(f"不支持的备选路径: {fb}")
            if fb == prod:
                raise ValueError("生产主线与备选路径不能相同")
            current_path = str(state.get("production_path") or _DEFAULT_PRODUCTION_PATH)
            path_entry = dict((state.get("path_models") or {}).get(prod) or {})
            if prod != current_path and not str(path_entry.get("model_ref") or "").strip():
                raise ValueError(f"建模路径 {prod} 尚无已登记模型，不能设为生产主线")
            if prod == "seq_annotation":
                self._assert_seq_production_ready(path_entry)

            state["production_path"] = prod
            state["fallback_path"] = fb
            registered_ref = str(path_entry.get("model_ref") or "").strip()
            if registered_ref:
                state["production_model_ref"] = registered_ref
                state["production_model_path_key"] = prod
                if path_entry.get("request_id"):
                    state["production_retrain_request_id"] = path_entry["request_id"]
            if prod != current_path:
                state.setdefault("path_switch_audit", []).append(
                    {
                        "action": "explicit_path_switch",
                        "from_path": current_path,
                        "to_path": prod,
                        "model_ref": registered_ref or None,
                        "at": datetime.utcnow().isoformat(),
                    }
                )
            self._save_state(state)
            return self._summarize_modeling_paths(state)

    def register_path_model(
        self,
        path_key: str,
        model_ref: str,
        *,
        request_id: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """登记候选模型；生产指针只能通过显式 Promote/路径切换更新。"""
        key = str(path_key or "").strip()
        ref = str(model_ref or "").strip()
        if key not in _ALLOWED_MODELING_PATHS:
            raise ValueError(f"不支持的建模路径: {key}")
        if not ref:
            raise ValueError("model_ref 不能为空")
        if key == "seq_annotation":
            raise ValueError(
                "seq_annotation 只能通过正式重训登记，并在完整生产契约校验后显式 Promote"
            )
        with self._lock:
            state = self._load_state()
            path_models = state.setdefault("path_models", {})
            path_models[key] = {
                "model_ref": ref,
                "request_id": request_id,
                "metrics": metrics or {},
                "updated_at": datetime.utcnow().isoformat(),
            }
            state.setdefault("path_switch_audit", []).append(
                {
                    "action": "path_model_registered",
                    "path": key,
                    "model_ref": ref,
                    "request_id": request_id,
                    "promoted": False,
                    "at": datetime.utcnow().isoformat(),
                }
            )
            self._save_state(state)
            return self._summarize_modeling_paths(state)

    def switch_to_fallback_path(self, reason: str) -> Dict[str, Any]:
        """主线出问题时的回退：交换主线/备选指针并切到备选最近模型。"""
        audit_reason = str(reason or "").strip()
        if not audit_reason:
            raise ValueError("回退必须提供 reason")
        with self._lock:
            state = self._load_state()
            prod = str(state.get("production_path") or _DEFAULT_PRODUCTION_PATH)
            fb = str(state.get("fallback_path") or _DEFAULT_FALLBACK_PATH)
            path_models = state.setdefault("path_models", {})
            fb_entry = path_models.get(fb) or {}
            fb_ref = str(fb_entry.get("model_ref") or "").strip()
            if not fb_ref:
                raise ValueError(f"备选路径 {fb} 尚无可用模型，无法回退")
            if fb == "seq_annotation":
                self._assert_seq_production_ready(dict(fb_entry))

            state["production_path"] = fb
            state["fallback_path"] = prod
            state["production_model_ref"] = fb_ref
            if fb_entry.get("request_id"):
                state["production_retrain_request_id"] = fb_entry["request_id"]
            state["production_promoted_at"] = datetime.utcnow().isoformat()
            audit = state.setdefault("path_switch_audit", [])
            audit.append(
                {
                    "action": "fallback_switch",
                    "from_path": prod,
                    "to_path": fb,
                    "model_ref": fb_ref,
                    "reason": audit_reason,
                    "at": datetime.utcnow().isoformat(),
                }
            )
            self._save_state(state)
            return self._summarize_modeling_paths(state)

    @staticmethod
    def _summarize_modeling_paths(state: Dict[str, Any]) -> Dict[str, Any]:
        production_path = str(state.get("production_path") or _DEFAULT_PRODUCTION_PATH)
        fallback_path = str(state.get("fallback_path") or _DEFAULT_FALLBACK_PATH)
        path_models = {
            key: dict(value)
            for key, value in (state.get("path_models") or {}).items()
            if key in _ALLOWED_MODELING_PATHS and isinstance(value, dict)
        }
        active_ref = str(state.get("production_model_ref") or "").strip()
        return {
            "available_paths": sorted(_ALLOWED_MODELING_PATHS),
            "production_path": production_path,
            "fallback_path": fallback_path,
            "path_models": path_models,
            "production_model_ref": active_ref or None,
            "path_switch_audit": list(state.get("path_switch_audit") or [])[-10:],
        }

    def mark_retrain_request(
        self,
        request_id: str,
        status: str,
        *,
        model_ref: Optional[str] = None,
        error: Optional[str] = None,
        train_summary: Optional[Dict[str, Any]] = None,
        promote_to_production: bool = True,
    ) -> Dict[str, Any]:
        """更新重训请求状态。

        ``pv_fault`` 完成时只把产物交给 PVModelRegistry：默认登记 Challenger；
        ``promote_to_production=True`` 只允许同路径精度守门，不得改 ``production_path``。
        其他 slot 保留旧自动晋升语义。
        """
        allowed_statuses = {"queued", "running", "completed", "failed", "cancelled"}
        if status not in allowed_statuses:
            raise ValueError(f"不支持的重训请求状态: {status}")
        if not isinstance(promote_to_production, bool):
            raise ValueError("promote_to_production 必须为 JSON boolean")
        with self._lock:
            state = self._load_state()
            request = state["retrain_requests"].get(request_id)
            if request is None:
                raise KeyError(request_id)
            request["status"] = status
            request["updated_at"] = datetime.utcnow().isoformat()
            if status == "running":
                request.setdefault("started_at", request["updated_at"])
            if status in {"completed", "failed", "cancelled"}:
                request["finished_at"] = request["updated_at"]
            if model_ref:
                request["model_ref"] = model_ref
            if error:
                request["error"] = error
            if train_summary:
                request["train_summary"] = train_summary
            pending_auto_request: Optional[Dict[str, Any]] = None
            if status == "completed":
                production_ref = str(request.get("model_ref") or "").strip()
                if not production_ref:
                    raise ValueError("重训完成时必须提供有效 model_ref")
                completed_at = request["updated_at"]
                summary = train_summary or {}
                modeling_path = str(summary.get("modeling_path") or "").strip()
                if modeling_path not in _ALLOWED_MODELING_PATHS:
                    raise ValueError(f"重训结果缺少有效 modeling_path: {modeling_path}")

                path_entry = {
                    "model_ref": production_ref,
                    "model_path": summary.get("model_path"),
                    "artifact_format": summary.get("artifact_format"),
                    "trained_full_day": summary.get("trained_full_day"),
                    "sequence_contract": summary.get("sequence_contract"),
                    "request_id": request_id,
                    "metrics": {
                        **dict(summary.get("accuracy_record") or {}),
                        **{
                            key: summary.get(key)
                            for key in ("macro_f1_mean", "accuracy_mean", "n_samples")
                            if summary.get(key) is not None
                        },
                    },
                    "updated_at": completed_at,
                }
                pv_fault_slot = self.slot == "pv_fault"
                if modeling_path == "seq_annotation" and promote_to_production and not pv_fault_slot:
                    self._assert_seq_production_ready(path_entry)

                path_models = state.setdefault("path_models", {})
                path_models[modeling_path] = path_entry
                production_path_before = str(
                    state.get("production_path") or _DEFAULT_PRODUCTION_PATH
                )

                if pv_fault_slot:
                    governance = self._publish_pv_fault_retrain_to_registry(
                        request_id=request_id,
                        modeling_path=modeling_path,
                        model_ref=production_ref,
                        summary=summary,
                        try_promote=promote_to_production,
                    )
                    request["promote_to_production"] = False
                    request["pv_registry_governance"] = governance
                    promotion_status = str(governance.get("promotion_status") or "")
                    request["progress"] = {
                        "stage": "completed",
                        "percent": 100,
                        "message": (
                            "训练完成，路径内已换将"
                            if promotion_status == "promoted"
                            else "训练完成，已登记 Challenger（未改生产路径）"
                        ),
                        "updated_at": completed_at,
                    }
                    state.setdefault("path_switch_audit", []).append(
                        {
                            "action": "experimental_model_registered",
                            "path": modeling_path,
                            "model_ref": production_ref,
                            "request_id": request_id,
                            "at": completed_at,
                            "promotion_status": promotion_status or None,
                        }
                    )
                    if str(state.get("production_path") or "") != production_path_before:
                        raise AssertionError("pv_fault 重训完成不得修改 production_path")
                elif promote_to_production:
                    request["promote_to_production"] = True
                    request["promoted_to_production_at"] = completed_at
                    request["progress"] = {
                        "stage": "completed",
                        "percent": 100,
                        "message": "训练完成，生产模型已切换",
                        "updated_at": completed_at,
                    }
                    state["production_model_ref"] = production_ref
                    state["production_retrain_request_id"] = request_id
                    state["production_promoted_at"] = completed_at
                    previous_path = production_path_before
                    if modeling_path != previous_path:
                        state["production_path"] = modeling_path
                        state["fallback_path"] = previous_path
                        state.setdefault("production_path_history", []).append(
                            {
                                "from": previous_path,
                                "to": modeling_path,
                                "reason": "retrain_completed",
                                "model_ref": production_ref,
                                "request_id": request_id,
                                "at": completed_at,
                            }
                        )
                    state["production_model_path_key"] = modeling_path
                else:
                    request["promote_to_production"] = False
                    request["progress"] = {
                        "stage": "completed",
                        "percent": 100,
                        "message": "训练完成，实验模型已登记（未切生产）",
                        "updated_at": completed_at,
                    }
                    state.setdefault("path_switch_audit", []).append(
                        {
                            "action": "experimental_model_registered",
                            "path": modeling_path,
                            "model_ref": production_ref,
                            "request_id": request_id,
                            "at": completed_at,
                        }
                    )

                _ensure_retrain_watermarks(state)
                watermark = state["retrain_watermarks"][modeling_path]
                consumed_units = int(request.get("triggered_change_count") or 0)
                if not bool(request.get("pending_reset_on_create")):
                    watermark["pending_change_count"] = max(
                        0,
                        int(watermark.get("pending_change_count") or 0) - consumed_units,
                    )
                    if modeling_path == _canonical_modeling_path(
                        state.get("production_path")
                    ):
                        state["pending_change_count"] = max(
                            0, int(state.get("pending_change_count") or 0) - consumed_units
                        )
                watermark["consumed_sequence"] = max(
                    int(watermark.get("consumed_sequence") or 0),
                    int(request.get("consumed_through_sequence") or 0),
                )
                watermark["last_consumed_at"] = completed_at
                watermark["last_failed_sequence"] = 0
                watermark["last_failed_pending_count"] = 0
                watermark["updated_at"] = completed_at

                # 若训练期间继续累积变更，完成后按当前生产路径排队下一次快照。
                pending_auto_request = self._maybe_create_auto_retrain_request(state)
            elif status == "failed":
                previous_progress = request.get("progress") or {}
                request["progress"] = {
                    "stage": "failed",
                    "percent": int(previous_progress.get("percent") or 0),
                    "message": error or "重训失败",
                    "updated_at": request["updated_at"],
                }
                failed_path = _canonical_modeling_path(request.get("target_modeling_path"))
                if failed_path in _ALLOWED_MODELING_PATHS:
                    _ensure_retrain_watermarks(state)
                    failed_watermark = state["retrain_watermarks"][failed_path]
                    failed_watermark["last_failed_sequence"] = max(
                        int(failed_watermark.get("last_failed_sequence") or 0),
                        int(request.get("consumed_through_sequence") or 0),
                    )
                    failed_watermark["last_failed_pending_count"] = int(
                        failed_watermark.get("pending_change_count") or 0
                    )
                    failed_watermark["updated_at"] = request["updated_at"]
            self._save_state(state)
            result = dict(request)
            if pending_auto_request and pending_auto_request.get("auto_execute"):
                result["_pending_auto_retrain_request_id"] = pending_auto_request["request_id"]
            return result

    def update_retrain_progress(
        self,
        request_id: str,
        *,
        stage: str,
        percent: int,
        message: str,
    ) -> Dict[str, Any]:
        """持久化真实重训阶段，供状态接口和前端轮询读取。"""
        with self._lock:
            state = self._load_state()
            request = state["retrain_requests"].get(request_id)
            if request is None:
                raise KeyError(request_id)
            if request.get("status") not in {"queued", "running"}:
                raise ValueError(f"状态 {request.get('status')} 不允许更新重训进度")
            now = datetime.utcnow().isoformat()
            request["progress"] = {
                "stage": str(stage),
                "percent": max(0, min(100, int(percent))),
                "message": str(message),
                "updated_at": now,
            }
            request["updated_at"] = now
            self._save_state(state)
            return dict(request)

    def _maybe_create_auto_retrain_request(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """按路径检查“变更阈值 AND 重训周期”，一次只排队一条 Challenger 重训。"""

        _ensure_retrain_watermarks(state)
        production_path = _canonical_modeling_path(
            state.get("production_path") or _DEFAULT_PRODUCTION_PATH
        )
        ordered_paths = [production_path] + sorted(
            path for path in _ALLOWED_MODELING_PATHS if path != production_path
        )
        trigger = AccuracyGatedRetrainer(
            self._pv_model_registry,
            retrain_change_threshold=self.retrain_label_threshold,
            retrain_period_days=self.retrain_period_days,
        )
        for target_path in ordered_paths:
            watermark = state["retrain_watermarks"][target_path]
            pending_count = int(watermark.get("pending_change_count") or 0)
            if pending_count <= int(watermark.get("last_failed_pending_count") or 0):
                continue
            raw_last = watermark.get("last_consumed_at")
            try:
                last_retrained_at = datetime.fromisoformat(str(raw_last)) if raw_last else None
            except ValueError:
                last_retrained_at = None
            decision = trigger.maybe_trigger(
                pending_change_count=pending_count,
                last_retrained_at=last_retrained_at,
            )
            if decision.should_trigger:
                return self._create_retrain_request(
                    state,
                    trigger_reason=str(decision.trigger_reason),
                    target_modeling_path=target_path,
                )
        return None

    def _create_retrain_request(
        self,
        state: Dict[str, Any],
        *,
        trigger_reason: str,
        target_modeling_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        requested_path = str(target_modeling_path or "").strip() or str(
            state.get("production_path") or _DEFAULT_PRODUCTION_PATH
        )
        if requested_path not in _ALLOWED_MODELING_PATHS:
            raise ValueError(f"不支持的建模路径: {requested_path}")
        active = next(
            (
                request
                for request in state["retrain_requests"].values()
                if request.get("status") in {"queued", "running"}
            ),
            None,
        )
        if active is not None:
            if active.get("status") == "running":
                return None
            # 带 active_job 的 queued 请求正由后台线程冻结快照（数分钟），
            # 不能当成陈旧排队请求取代掉：否则既会中断正在跑的重训，又会让本函数
            # 在 get_state 轮询里同步重建快照，把状态接口堵死数分钟。
            if active.get("active_job"):
                return None
            active["status"] = "cancelled"
            active["cancelled_reason"] = "superseded_by_newer_snapshot"
            active["updated_at"] = datetime.utcnow().isoformat()
            active["finished_at"] = active["updated_at"]

        try:
            snapshot = self._create_snapshot(
                state,
                target_modeling_path=requested_path,
            )
        except ValueError as exc:
            # 审核裁决已经可靠落账；若当前样本不满足训练条件，只阻断重训申请，不能丢失标签。
            state["last_retrain_blocker"] = str(exc)
            return None
        state.pop("last_retrain_blocker", None)
        _ensure_retrain_watermarks(state)
        target_watermark = state["retrain_watermarks"][requested_path]
        pending_before_reset = int(target_watermark.get("pending_change_count") or 0)
        consumed_through_sequence = int(state.get("next_sequence") or 0)
        request_id = f"retrain-{uuid.uuid4().hex[:12]}"
        is_auto = trigger_reason.startswith("auto_")
        request = {
            "request_id": request_id,
            "status": "queued",
            "snapshot_id": snapshot["snapshot_id"],
            "dataset_path": snapshot["dataset_path"],
            "sample_count": snapshot["sample_count"],
            "label_count": snapshot["label_count"],
            "target_modeling_path": requested_path,
            "trigger_reason": trigger_reason,
            "auto_execute": is_auto,
            "triggered_change_count": pending_before_reset,
            "consumed_through_sequence": consumed_through_sequence,
            "pending_reset_on_create": False,
            "threshold": self.retrain_label_threshold,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "progress": {
                "stage": "queued",
                "percent": 0,
                "message": (
                    "已达变更阈值，正在自动重训"
                    if is_auto
                    else "等待手动执行重训"
                ),
                "updated_at": datetime.utcnow().isoformat(),
            },
        }
        state["retrain_requests"][request_id] = request
        # 请求创建只冻结消费边界；失败/取消不得提前推进水位或清零待消费变更。
        return dict(request)

    def _create_snapshot(
        self,
        state: Dict[str, Any],
        *,
        target_modeling_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        modeling_path = str(target_modeling_path or _DEFAULT_PRODUCTION_PATH).strip()
        if modeling_path == "seq_annotation":
            return self._create_snapshot_seq_annotation(state)
        if modeling_path == "legacy_day":
            return self._create_snapshot_legacy(state)
        if modeling_path == "tsc":
            return self._create_snapshot_tsc(state)
        raise ValueError(f"不支持的建模路径: {modeling_path}")

    def _create_snapshot_seq_annotation(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """构建全天 288 点不可变 NPZ 快照，供序列标注专用训练器使用。"""
        from services.iterative_labeling.seq_annotation.dataset_builder import build_dataset
        from services.iterative_labeling.seq_annotation.trainer import (
            _is_full_day_grid_validated,
        )

        # 采用构建器默认的网格覆盖门槛（min_occupied_slots=173 等）。
        # 不要再传旧的 min_points：那个参数卡的是原始行数，会把「夜间 10 分钟采样、
        # 物理完整」的自然日整批误杀，实测会让点粒度金标从 196 天掉到 30 天。
        result = build_dataset(seq_len=288)
        report = dict(result["report"])
        dataset_path = str(result["output_dir"])
        dataset_dir = self.project_root / "backend-service" / dataset_path
        grid_contract = dict(report.get("grid_contract") or {})
        # 与 trainer 共用同一套严格判定：全天资格必须由网格结构（288 槽 / 5 分钟 /
        # 24 小时覆盖门控 / is_measured 通道）加真实覆盖证据共同成立。只看布尔值会让
        # 半天或旧口径快照冒充全天，进而拿到夜间诊断与生产切换资格。
        full_day_grid_validated = _is_full_day_grid_validated(
            report=report,
            grid_contract=grid_contract,
            channels=list(report.get("channels") or []),
            seq_len=int(report["seq_len"]),
        )
        trained_full_day = bool(
            int(report["seq_len"]) == 288
            and list(report.get("daylight_hours") or []) == [0, 24]
            and full_day_grid_validated
        )
        snapshot = {
            "snapshot_id": str(result["version"]),
            "dataset_path": dataset_path,
            "sample_count": int(report["n_sequences"]),
            "row_count": int(report["n_sequences"]) * int(report["seq_len"]),
            "label_count": int(report["n_classes"]),
            "content_sha256": self._sha256_file(dataset_dir / "dataset.npz"),
            "label_snapshot_hash": report.get("label_snapshot_hash"),
            "sample_strategy": {
                "split_mode": "seq_annotation",
                "seq_len": int(report["seq_len"]),
                "channels": list(report.get("channels") or ["value", "i_cal"]),
                "trained_full_day": trained_full_day,
                "full_day_grid_validated": full_day_grid_validated,
            },
            "snapshot_mode": "seq_annotation",
            "grid_contract": grid_contract or None,
            "sources": [
                {
                    "kind": "point_labels_and_measurements",
                    "night_label_policy": report.get("night_label_policy"),
                }
            ],
            "created_at": datetime.utcnow().isoformat(),
        }
        state["snapshots"][snapshot["snapshot_id"]] = snapshot
        return snapshot

    # @AI_GENERATED
    def _create_snapshot_tsc(self, state: Dict[str, Any]) -> Dict[str, Any]:
        # @AI_GENERATED
        """构建 TSC（时序分类诊断）不可变 NPZ 快照，供 MultiRocket 训练使用。

        P1-1 改动 A：从旧版 ``SlidingWindowSampler``（288×2 连续滑窗）切换到
        ``grid_day_builder.build_tsc_grid_dataset``（288×3 clock-grid + measured mask），
        保证累计训练和画布算子使用同一表示。

        流程：从累积标签池中加载 parquet 原始时序 + 逐点标签，调用
        ``build_tsc_grid_dataset`` 按设备-天网格化为 ``[N, 288, 3]``
        (value/i_cal/is_measured) 样本，做 mask-aware ``per_sample_zscore``
        预处理后保存为 ``.npz``。
        """
        from services.iterative_labeling.tsc.grid_day_builder import (
            TSC_GRID_CHANNELS,
            build_tsc_grid_dataset,
            preprocess_grid_X,
        )

        # ---- 1. 确定源数据集路径 ----
        # unified ledger 是 pv_tsc 在线真源：有 freeze 就消费最新 freeze；已有新事件
        # 但尚未 freeze 时明确阻断，避免静默训练旧 state。仅迁移前空 ledger 回退旧账。
        from services.slot_datasets.snapshots import get_cumulative_ledger

        dataset_path: Optional[str] = None
        ledger = get_cumulative_ledger("pv_tsc")
        latest_freeze = ledger.get("latest_freeze") or {}
        latest_artifact = str(latest_freeze.get("artifact_ref") or "").strip()
        if latest_artifact:
            dataset_path = latest_artifact.replace("\\", "/")
        elif ledger.get("events"):
            raise ValueError(
                "TSC 累计账本已有新审核数据但尚未 freeze；请先冻结 pv_tsc 累计版本再训练"
            )

        # 兼容迁移前实例：unified ledger 完全为空时才读取旧 snapshots/imports。
        if not dataset_path:
            snapshots = sorted(
                (
                    snap for snap in state.get("snapshots", {}).values()
                    if snap.get("snapshot_mode") in ("legacy_day", None)
                    and snap.get("dataset_path")
                ),
                key=lambda s: s.get("created_at", ""),
                reverse=True,
            )
            if snapshots:
                dataset_path = snapshots[0]["dataset_path"]

        if not dataset_path:
            imports = sorted(
                state.get("labeled_imports", {}).values(),
                key=lambda imp: imp.get("sequence", 0),
                reverse=True,
            )
            for imp in imports:
                if imp.get("dataset_path"):
                    dataset_path = imp["dataset_path"]
                    break

        if not dataset_path:
            raise ValueError(
                "TSC 快照无法创建：无可用累计训练数据；请先完成审核入账并冻结 pv_tsc 版本"
            )

        # 拒绝消费旧的 NPZ 快照目录——网格化需要原始 parquet/csv 行数据。
        from pathlib import Path as _Path
        _resolved = _Path(self.project_root / self._normalize_relative_path(dataset_path))
        if _resolved.is_dir() or _resolved.suffix.lower() == ".npz":
            raise ValueError(
                f"TSC 网格化快照不能消费旧 NPZ 产物 ({dataset_path})；"
                "请确保 freeze artifact 指向原始 parquet/csv 数据"
            )

        # ---- 2. 网格化构建 [N, 288, 3] ----
        df = self._read_dataset(dataset_path)
        X, y, meta, grid_stats = build_tsc_grid_dataset(
            df,
            purity_threshold=0.7,
        )

        if len(y) == 0:
            raise ValueError(
                "TSC 快照切分结果为空：可能数据量不足或全部设备日被覆盖率/纯度过滤丢弃"
            )

        # 断言网格合同
        if X.ndim != 3 or tuple(X.shape[1:]) != (288, 3):
            raise ValueError(
                f"TSC 网格合同违反：期望 [N, 288, 3]，实际 {tuple(X.shape)}"
            )

        # ---- 3. mask-aware 预处理 ----
        X_preprocessed = preprocess_grid_X(X, method="per_sample_zscore")

        # ---- 4. 保存 NPZ ----
        snapshot_id = f"tsc-snap-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        snapshot_dir = self.root / "snapshots" / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        npz_path = snapshot_dir / "dataset.npz"
        np.savez_compressed(
            str(npz_path),
            X=X_preprocessed,
            y=y,
            sample_ids=meta["device_id"].astype(str).values + "_" + meta["date"].astype(str).values
            if {"device_id", "date"}.issubset(meta.columns)
            else np.arange(len(y)).astype(str),
        )

        # 同时保存 meta CSV 与 manifest，训练端直接消费冻结样本，不再把目录当原始 parquet 二次切窗。
        meta_path = snapshot_dir / "meta.csv"
        meta.to_csv(str(meta_path), index=False, encoding="utf-8")

        unique_labels, label_counts = np.unique(y, return_counts=True)
        class_distribution = {int(k): int(v) for k, v in zip(unique_labels, label_counts)}
        sample_strategy = {
            "representation": "clock_grid_288_mask",
            "window_length": 288,
            "stride": 288,
            "channels": list(TSC_GRID_CHANNELS),
            "purity_threshold": 0.7,
            "preprocess_method": "per_sample_zscore",
            "class_distribution": class_distribution,
        }
        manifest = {
            "schema_version": 2,
            "snapshot_id": snapshot_id,
            "dataset_file": "dataset.npz",
            "meta_file": "meta.csv",
            "preprocessed": True,
            "sample_count": int(len(y)),
            "label_count": int(len(unique_labels)),
            "sample_strategy": sample_strategy,
            "load_stats": grid_stats,
            "source_dataset_path": str(dataset_path).replace("\\", "/"),
            "created_at": datetime.utcnow().isoformat(),
        }
        manifest_path = snapshot_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        content_sha256 = self._sha256_file(npz_path)
        rel_dataset_path = self._to_project_relative(npz_path)
        rel_manifest_path = self._to_project_relative(manifest_path)

        snapshot = {
            "snapshot_id": snapshot_id,
            "dataset_path": rel_dataset_path,
            "manifest_path": rel_manifest_path,
            "sample_count": int(len(y)),
            "row_count": int(len(y)) * 288,
            "label_count": int(len(unique_labels)),
            "content_sha256": content_sha256,
            "sample_strategy": sample_strategy,
            "snapshot_mode": "tsc",
            "representation": "clock_grid_288_mask",
            "sources": [
                {
                    "kind": "cumulative_labeled_data",
                    "source_dataset_path": str(dataset_path).replace("\\", "/"),
                    "devices_processed": grid_stats.get("devices_processed", 0),
                }
            ],
            "created_at": datetime.utcnow().isoformat(),
        }
        state["snapshots"][snapshot["snapshot_id"]] = snapshot
        return snapshot
        # @AI_GENERATED: end

    def _create_snapshot_legacy(self, state: Dict[str, Any]) -> Dict[str, Any]:
        frames: List[pd.DataFrame] = []
        source_descriptions: List[Dict[str, Any]] = []

        for imported in sorted(state["labeled_imports"].values(), key=lambda item: item["sequence"]):
            frame = self._read_dataset(imported["dataset_path"])
            frames.append(frame)
            source_descriptions.append(
                {"kind": "labeled_import", "id": imported["import_id"], "path": imported["dataset_path"]}
            )

        review_entries = list(state["verdict_entries"].values())
        entries_by_review: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for entry in review_entries:
            entries_by_review[entry["review_id"]].append(entry)

        materializer = BackfillService(
            slot=self.slot,
            review_repo=self.review_repo,
            ground_truth_repo=FileGroundTruthRepository(),
        )
        for review_id, entries in sorted(
            entries_by_review.items(),
            key=lambda item: max(entry["sequence"] for entry in item[1]),
        ):
            result = materializer.backfill_to_raw_dataset(
                review_id=review_id,
                merge_base=False,
                output_dir=str(self.root / "materialized_reviews"),
            )
            frame = self._read_dataset(result["csv_path"])
            frames.append(frame)
            source_descriptions.append(
                {
                    "kind": "review",
                    "id": review_id,
                    "path": result["csv_path"],
                    "entry_count": len(entries),
                }
            )

        if not frames:
            raise ValueError("累计训练集为空，无法创建重训快照")

        combined = pd.concat(frames, ignore_index=True, sort=False)
        if "label" not in combined.columns:
            raise ValueError("累计训练集快照缺少 label 列")
        combined = combined[combined["label"].notna()].copy()
        if combined.empty:
            raise ValueError("累计训练集没有有效 label，无法创建重训快照")
        combined["label"] = pd.to_numeric(combined["label"], errors="raise").astype(int)
        if combined["label"].nunique() < 2:
            raise ValueError("累计训练集至少需要两个有效标签类别，当前不创建重训请求")

        identity_columns = [
            column
            for column in ("time", "site_id", "device_id", "branch_id", "time_window")
            if column in combined.columns
        ]
        # 含 time_window 时，自由窗与整天样本可共存同一时间戳；不含时退回旧四元组去重。
        if len(identity_columns) >= 4:
            combined = combined.drop_duplicates(subset=identity_columns, keep="last")
        combined = (
            combined.sort_values(identity_columns).reset_index(drop=True)
            if identity_columns
            else combined.reset_index(drop=True)
        )

        snapshot_id = f"snapshot-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        snapshot_path = self.root / "snapshots" / f"{snapshot_id}.csv"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(snapshot_path, index=False, encoding="utf-8")
        dataset_path = self._to_project_relative(snapshot_path)
        content_sha256 = self._sha256_file(snapshot_path)
        snapshot = {
            "snapshot_id": snapshot_id,
            "dataset_path": dataset_path,
            "sample_count": int(len(combined)),
            "label_count": int(combined["label"].nunique()),
            "content_sha256": content_sha256,
            "sources": source_descriptions,
            "created_at": datetime.utcnow().isoformat(),
        }
        state["snapshots"][snapshot_id] = snapshot
        return snapshot

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {
                "schema_version": _MODELING_PATH_SCHEMA_VERSION,
                "slot": self.slot,
                "retrain_label_threshold": self.retrain_label_threshold,
                "next_sequence": 0,
                "pending_change_count": 0,
                "retrain_watermarks": {
                    path: {
                        "consumed_sequence": 0,
                        "pending_change_count": 0,
                        "last_consumed_at": None,
                        "last_failed_sequence": 0,
                        "last_failed_pending_count": 0,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                    for path in sorted(_ALLOWED_MODELING_PATHS)
                },
                "verdict_entries": {},
                "point_label_ops": {},
                "day_label_ops": {},
                "labeled_imports": {},
                "snapshots": {},
                "retrain_requests": {},
                "production_path": _DEFAULT_PRODUCTION_PATH,
                "fallback_path": _DEFAULT_FALLBACK_PATH,
                "path_models": {},
                "path_switch_audit": [],
            }
        try:
            with self.state_path.open("r", encoding="utf-8") as file:
                state = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise IOError(f"累计训练集状态损坏，无法读取: {self.state_path}") from exc
        if state.get("slot") != self.slot:
            raise ValueError("累计训练集状态槽位不匹配")
        state.setdefault("next_sequence", 0)
        state.setdefault("pending_change_count", 0)
        state.setdefault("verdict_entries", {})
        state.setdefault("point_label_ops", {})
        state.setdefault("day_label_ops", {})
        state.setdefault("labeled_imports", {})
        state.setdefault("snapshots", {})
        state.setdefault("retrain_requests", {})
        state.setdefault("production_path", _DEFAULT_PRODUCTION_PATH)
        state.setdefault("fallback_path", _DEFAULT_FALLBACK_PATH)
        state.setdefault("path_models", {})
        state.setdefault("path_switch_audit", [])
        state["retrain_label_threshold"] = self.retrain_label_threshold
        modeling_path_changed = _normalize_modeling_path_state(state)
        watermark_changed = _ensure_retrain_watermarks(state)
        if modeling_path_changed or watermark_changed:
            # 一次性持久化迁移，后续接口和 UI 不再看到旧伪点路径或全局单水位。
            _atomic_write_json(self.state_path, state)
        return state

    def _save_state(self, state: Dict[str, Any]) -> None:
        state["updated_at"] = datetime.utcnow().isoformat()
        _atomic_write_json(self.state_path, state)

    def _summarize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        production_request_id = str(state.get("production_retrain_request_id") or "").strip()
        production_model_ref = str(state.get("production_model_ref") or "").strip()
        latest_completed_raw = self._latest_completed_request(state)
        latest_promoted_raw = self._latest_promoted_request(state)
        if not production_model_ref and latest_promoted_raw:
            production_model_ref = str(latest_promoted_raw.get("model_ref") or "").strip()
            production_request_id = str(latest_promoted_raw.get("request_id") or "").strip()

        requests = sorted(
            (
                {
                    **request,
                    "is_production": bool(
                        production_request_id
                        and str(request.get("request_id") or "") == production_request_id
                    ),
                }
                for request in state["retrain_requests"].values()
            ),
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )
        snapshots = sorted(
            state["snapshots"].values(),
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )
        latest_completed_id = str((latest_completed_raw or {}).get("request_id") or "")
        latest_completed = next(
            (
                request
                for request in requests
                if str(request.get("request_id") or "") == latest_completed_id
            ),
            None,
        )
        production_request = next(
            (request for request in requests if request.get("is_production")),
            latest_completed,
        )
        display_snapshot = snapshots[0] if snapshots else None
        if production_request and production_request.get("snapshot_id"):
            matched = state["snapshots"].get(str(production_request["snapshot_id"]))
            if isinstance(matched, dict):
                display_snapshot = matched
        modeling_paths_summary = self.get_modeling_paths()
        registry_production_ref = str(
            modeling_paths_summary.get("production_model_ref") or production_model_ref or ""
        ).strip()
        displayed_production_model: Optional[Dict[str, Any]] = production_request
        if modeling_paths_summary.get("registry_source") == "pv_model_registry":
            production_lifecycle = (
                modeling_paths_summary.get("path_models") or {}
            ).get(modeling_paths_summary.get("production_path")) or {}
            champion_payload = production_lifecycle.get("champion")
            if isinstance(champion_payload, dict):
                displayed_production_model = {
                    **champion_payload,
                    "is_production": True,
                    "source": "pv_model_registry",
                }
        return {
            "slot": self.slot,
            "effective_labeled_unit_count": len(state["verdict_entries"]),
            "labeled_import_count": len(state["labeled_imports"]),
            "pending_change_count": int(state["pending_change_count"]),
            "retrain_watermarks": {
                path: {
                    **dict(item),
                    "next_retrain_in": max(
                        0,
                        self.retrain_label_threshold
                        - int(item.get("pending_change_count") or 0),
                    ),
                }
                for path, item in (state.get("retrain_watermarks") or {}).items()
                if path in _ALLOWED_MODELING_PATHS and isinstance(item, dict)
            },
            "retrain_label_threshold": self.retrain_label_threshold,
            "retrain_period_days": self.retrain_period_days,
            "next_retrain_in": max(0, self.retrain_label_threshold - int(state["pending_change_count"])),
            "retrain_blocker": state.get("last_retrain_blocker"),
            "latest_snapshot": display_snapshot,
            "latest_retrain_request": requests[0] if requests else None,
            "latest_completed_retrain": latest_completed,
            "production_model": displayed_production_model,
            "production_model_ref": registry_production_ref or None,
            "production_promoted_at": (
                state.get("production_promoted_at")
                or (production_request or {}).get("promoted_to_production_at")
                or (production_request or {}).get("finished_at")
            ),
            "retrain_history": requests,
            "latest_completed_model_ref": registry_production_ref or None,
            "modeling_paths": modeling_paths_summary,
        }

    @staticmethod
    def _latest_completed_request(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        completed = [
            request
            for request in state["retrain_requests"].values()
            if request.get("status") == "completed"
            and str(request.get("model_ref") or "").strip()
        ]
        return max(
            completed,
            key=lambda request: (
                request.get("finished_at") or "",
                request.get("updated_at") or "",
                request.get("created_at") or "",
            ),
            default=None,
        )

    @staticmethod
    def _latest_promoted_request(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """返回最近已晋升请求；旧状态缺字段时按历史自动晋升语义兼容。"""
        promoted = [
            request
            for request in state["retrain_requests"].values()
            if request.get("status") == "completed"
            and str(request.get("model_ref") or "").strip()
            and request.get("promote_to_production") is not False
        ]
        return max(
            promoted,
            key=lambda request: (
                request.get("promoted_to_production_at") or "",
                request.get("finished_at") or "",
                request.get("updated_at") or "",
                request.get("created_at") or "",
            ),
            default=None,
        )

    def _normalize_relative_path(self, path_value: str) -> str:
        path = Path(str(path_value or "").strip())
        if not str(path) or path.is_absolute():
            raise ValueError("数据集路径必须使用相对于项目根目录的路径")
        candidate = (self.project_root / path).resolve()
        try:
            relative = candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError("数据集路径不能逃逸项目根目录") from exc
        if not candidate.exists():
            raise ValueError(f"数据集文件不存在: {relative.as_posix()}")
        return relative.as_posix()

    def _read_dataset(self, relative_path: str) -> pd.DataFrame:
        path = self.project_root / self._normalize_relative_path(relative_path)
        if path.suffix.lower() == ".parquet":
            return pd.read_parquet(path)
        return pd.read_csv(path)

    def _to_project_relative(self, absolute_path: Path) -> str:
        return absolute_path.resolve().relative_to(self.project_root).as_posix()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
# @AI_GENERATED: end
