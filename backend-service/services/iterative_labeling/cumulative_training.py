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
import os
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

import pandas as pd

from .backfill import BackfillService
from .snapshot_builder import SnapshotBuilder
from .sample_builder import SampleStrategy
from services.db.config import DBConfig
from services.db.adapter import DBAdapter
from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.daylight_window import DaylightWindowResolver
from .storage.file_backend import (
    FileGroundTruthRepository,
    FileReviewResultRepository,
    _atomic_write_json,
    _get_data_root,
)


_VALID_GROUND_TRUTH_ACTIONS = frozenset({"confirm", "correct", "new_label"})
_DEFAULT_RETRAIN_LABEL_THRESHOLD = 20
_ALLOWED_MODELING_PATHS = frozenset(
    {"legacy_day", "point_label_by_day", "point_label_by_day_night"}
)
_DEFAULT_PRODUCTION_PATH = "legacy_day"
_DEFAULT_FALLBACK_PATH = "point_label_by_day_night"
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
    ) -> None:
        self.slot = str(slot or "default")
        self.review_repo = review_repo or FileReviewResultRepository()
        self.data_root = (data_root or _get_data_root()).resolve()
        self.project_root = Path(__file__).resolve().parents[3]
        self.root = self.data_root / "cumulative_training" / self.slot
        self.state_path = self.root / "state.json"
        configured_threshold = (
            retrain_label_threshold
            if retrain_label_threshold is not None
            else os.getenv("PV_RETRAIN_LABEL_THRESHOLD", _DEFAULT_RETRAIN_LABEL_THRESHOLD)
        )
        try:
            self.retrain_label_threshold = max(1, int(configured_threshold))
        except (TypeError, ValueError):
            self.retrain_label_threshold = _DEFAULT_RETRAIN_LABEL_THRESHOLD
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

    def request_manual_retrain(self) -> Dict[str, Any]:
        """基于当前累计训练集立即创建手动重训请求（不依赖变更阈值）。"""
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
                reset_pending_count=False,
            )
            if request is None:
                blocker = state.get("last_retrain_blocker") or "累计训练集不满足重训条件"
                raise ValueError(str(blocker))
            self._save_state(state)
            summary = self._summarize_state(state)
            summary["retrain_request"] = request
            return summary

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

    def admit_point_label_op(
        self,
        review_id: str,
        op_id: str,
        verdict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """point_labels 主链路：按 review_id + op_id 幂等计入重训阈值。"""
        if not review_id or not op_id:
            raise ValueError("review_id 和 op_id 不能为空")
        entry_key = f"{review_id}|{op_id}"
        is_ground_truth = (
            bool(verdict.get("is_ground_truth"))
            and verdict.get("action_type") in _VALID_GROUND_TRUTH_ACTIONS
        )

        if not is_ground_truth:
            with self._lock:
                state = self._load_state()
                state.setdefault("point_label_ops", {})
                removed = state["point_label_ops"].pop(entry_key, None) is not None
                if removed:
                    state["pending_change_count"] += 1
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
        }

        with self._lock:
            state = self._load_state()
            state.setdefault("point_label_ops", {})
            previous = state["point_label_ops"].get(entry_key)
            comparison_keys = {"review_id", "op_id", "verdict_label", "action_type", "reviewer"}
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
        """返回本 slot 当前生产模型；兼容读取自动切模上线前的历史状态。"""
        with self._lock:
            state = self._load_state()
            production_ref = str(state.get("production_model_ref") or "").strip()
            if production_ref:
                return production_ref
            latest = self._latest_completed_request(state)
            return str(latest["model_ref"]).strip() if latest else None

    def get_latest_completed_model_ref(self) -> Optional[str]:
        """兼容旧调用；生产预测应使用 ``get_production_model_ref``。"""
        return self.get_production_model_ref()

    def get_modeling_paths(self) -> Dict[str, Any]:
        """返回生产主线路径、备选路径及各路径最近模型登记。"""
        with self._lock:
            state = self._load_state()
            return self._summarize_modeling_paths(state)

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
                fb = str(state.get("fallback_path") or _DEFAULT_FALLBACK_PATH).strip()
            else:
                fb = str(fallback_path or "").strip() or _DEFAULT_FALLBACK_PATH
            if fb not in _ALLOWED_MODELING_PATHS:
                raise ValueError(f"不支持的备选路径: {fb}")
            if fb == prod:
                raise ValueError("生产主线与备选路径不能相同")
            state["production_path"] = prod
            state["fallback_path"] = fb
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
        """登记某建模路径的最近可用模型。"""
        key = str(path_key or "").strip()
        ref = str(model_ref or "").strip()
        if key not in _ALLOWED_MODELING_PATHS:
            raise ValueError(f"不支持的建模路径: {key}")
        if not ref:
            raise ValueError("model_ref 不能为空")
        with self._lock:
            state = self._load_state()
            path_models = state.setdefault("path_models", {})
            path_models[key] = {
                "model_ref": ref,
                "request_id": request_id,
                "metrics": metrics or {},
                "updated_at": datetime.utcnow().isoformat(),
            }
            if key == str(state.get("production_path") or _DEFAULT_PRODUCTION_PATH):
                state["production_model_ref"] = ref
                if request_id:
                    state["production_retrain_request_id"] = request_id
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
        path_models = dict(state.get("path_models") or {})
        active_ref = str(state.get("production_model_ref") or "").strip()
        return {
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
    ) -> Dict[str, Any]:
        """更新重训请求状态；只有训练调用方可将 queued 变为 running/completed/failed。"""
        allowed_statuses = {"queued", "running", "completed", "failed", "cancelled"}
        if status not in allowed_statuses:
            raise ValueError(f"不支持的重训请求状态: {status}")
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
                request["progress"] = {
                    "stage": "completed",
                    "percent": 100,
                    "message": "训练完成，生产模型已切换",
                    "updated_at": request["updated_at"],
                }
                production_ref = str(request.get("model_ref") or "").strip()
                if not production_ref:
                    raise ValueError("重训完成时必须提供有效 model_ref，生产模型未切换")
                promoted_at = request["updated_at"]
                request["promoted_to_production_at"] = promoted_at
                state["production_model_ref"] = production_ref
                state["production_retrain_request_id"] = request_id
                state["production_promoted_at"] = promoted_at
                modeling_path = str((train_summary or {}).get("modeling_path") or "").strip()
                if modeling_path in _ALLOWED_MODELING_PATHS:
                    path_models = state.setdefault("path_models", {})
                    path_models[modeling_path] = {
                        "model_ref": production_ref,
                        "request_id": request_id,
                        "metrics": {
                            k: (train_summary or {}).get(k)
                            for k in ("macro_f1_mean", "accuracy_mean", "n_samples")
                            if (train_summary or {}).get(k) is not None
                        },
                        "updated_at": promoted_at,
                    }
                    # @AI_GENERATED: 生产登记一致性（需求 23.5）。
                    # 修复前 production_path 与 production_model_ref 各自独立更新，
                    # 出现过「production_path=legacy_day 但生产模型由 by_day_night
                    # 产出」的矛盾。这里把实际产出该模型的路径同步为主线，并把原
                    # 主线降为备选，使两个指针恒一致、可审计。
                    prev_path = str(state.get("production_path") or _DEFAULT_PRODUCTION_PATH)
                    if modeling_path != prev_path:
                        state["production_path"] = modeling_path
                        state["fallback_path"] = prev_path
                        state.setdefault("production_path_history", []).append({
                            "from": prev_path,
                            "to": modeling_path,
                            "reason": "retrain_completed",
                            "model_ref": production_ref,
                            "request_id": request_id,
                            "at": promoted_at,
                        })
                        logger.info(
                            "生产主线路径随重训切换: %s -> %s (model=%s)",
                            prev_path, modeling_path, production_ref,
                        )
                    state["production_model_path_key"] = modeling_path
                    # @AI_GENERATED: end
                # 若登记/审核在 running 期间继续累积变更，完成后自动排队下一次全量快照。
                pending_auto_request = self._maybe_create_auto_retrain_request(state)
            elif status == "failed":
                previous_progress = request.get("progress") or {}
                request["progress"] = {
                    "stage": "failed",
                    "percent": int(previous_progress.get("percent") or 0),
                    "message": error or "重训失败",
                    "updated_at": request["updated_at"],
                }
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
        if state["pending_change_count"] < self.retrain_label_threshold:
            return None
        return self._create_retrain_request(
            state,
            trigger_reason="auto_threshold",
            reset_pending_count=True,
        )

    def _create_retrain_request(
        self,
        state: Dict[str, Any],
        *,
        trigger_reason: str,
        reset_pending_count: bool,
    ) -> Optional[Dict[str, Any]]:
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
            active["status"] = "cancelled"
            active["cancelled_reason"] = "superseded_by_newer_snapshot"
            active["updated_at"] = datetime.utcnow().isoformat()
            active["finished_at"] = active["updated_at"]

        try:
            snapshot = self._create_snapshot(state)
        except ValueError as exc:
            # 审核裁决已经可靠落账；若当前样本不满足训练条件，只阻断重训申请，不能丢失标签。
            state["last_retrain_blocker"] = str(exc)
            return None
        state.pop("last_retrain_blocker", None)
        pending_before_reset = int(state["pending_change_count"])
        request_id = f"retrain-{uuid.uuid4().hex[:12]}"
        is_auto = trigger_reason == "auto_threshold"
        request = {
            "request_id": request_id,
            "status": "queued",
            "snapshot_id": snapshot["snapshot_id"],
            "dataset_path": snapshot["dataset_path"],
            "sample_count": snapshot["sample_count"],
            "label_count": snapshot["label_count"],
            "trigger_reason": trigger_reason,
            "auto_execute": is_auto,
            "triggered_change_count": pending_before_reset,
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
        if reset_pending_count:
            state["pending_change_count"] = 0
        return dict(request)

    def _create_snapshot(self, state: Dict[str, Any]) -> Dict[str, Any]:
        mode = str(state.get("snapshot_mode") or os.getenv("PV_SNAPSHOT_MODE", "point_label")).strip().lower()
        if mode == "legacy":
            return self._create_snapshot_legacy(state)
        try:
            return self._create_snapshot_point_label(state)
        except Exception as exc:
            logger.warning("point_label 快照构建失败，回退 legacy: %s", exc)
            return self._create_snapshot_legacy(state)

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

    def _create_snapshot_point_label(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """从 point_labels + training_samples 构建新路径快照（含 sample_id）。"""
        adapter = DBAdapter(DBConfig())
        point_repo = PointLabelRepository(adapter)
        sample_repo = PVFaultRepository(adapter)
        builder = SnapshotBuilder(point_repo, sample_repo)

        split_mode = str(state.get("split_mode") or os.getenv("PV_SPLIT_MODE", "by_day_night"))
        measurements = builder._load_measurements(None)
        resolver = DaylightWindowResolver()
        daylight_table = resolver.build_table(measurements)

        strategy = SampleStrategy(
            split_mode=split_mode,
            min_points=int(state.get("min_points") or 12),
            daylight_windows=daylight_table,
        )
        combined, meta = builder.build(strategy, measurements_df=measurements)

        if combined["label"].nunique() < 2:
            raise ValueError("point_label 快照至少需要两个有效标签类别")

        snapshot_id = f"snapshot-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        snapshot_path = self.root / "snapshots" / f"{snapshot_id}.parquet"
        rel_path = builder.write_parquet(combined, meta, snapshot_path)
        dataset_path = self._to_project_relative(Path(rel_path))

        snapshot = {
            "snapshot_id": snapshot_id,
            "dataset_path": dataset_path,
            "sample_count": int(meta.get("sample_count", 0)),
            "row_count": int(meta.get("row_count", len(combined))),
            "label_count": int(combined["label"].nunique()),
            "content_sha256": hashlib.sha256(
                combined.to_csv(index=False).encode("utf-8")
            ).hexdigest(),
            "label_snapshot_hash": meta.get("label_snapshot_hash"),
            "sample_strategy": meta.get("sample_strategy"),
            "snapshot_mode": "point_label",
            "sources": [{"kind": "point_labels", "split_mode": split_mode}],
            "created_at": datetime.utcnow().isoformat(),
        }
        state["snapshots"][snapshot_id] = snapshot
        return snapshot

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {
                "schema_version": 1,
                "slot": self.slot,
                "retrain_label_threshold": self.retrain_label_threshold,
                "next_sequence": 0,
                "pending_change_count": 0,
                "verdict_entries": {},
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
        state.setdefault("labeled_imports", {})
        state.setdefault("snapshots", {})
        state.setdefault("retrain_requests", {})
        state.setdefault("production_path", _DEFAULT_PRODUCTION_PATH)
        state.setdefault("fallback_path", _DEFAULT_FALLBACK_PATH)
        state.setdefault("path_models", {})
        state.setdefault("path_switch_audit", [])
        state["retrain_label_threshold"] = self.retrain_label_threshold
        return state

    def _save_state(self, state: Dict[str, Any]) -> None:
        state["updated_at"] = datetime.utcnow().isoformat()
        _atomic_write_json(self.state_path, state)

    def _summarize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        production_request_id = str(state.get("production_retrain_request_id") or "").strip()
        production_model_ref = str(state.get("production_model_ref") or "").strip()
        latest_completed_raw = self._latest_completed_request(state)
        if not production_model_ref and latest_completed_raw:
            production_model_ref = str(latest_completed_raw.get("model_ref") or "").strip()
            production_request_id = str(latest_completed_raw.get("request_id") or "").strip()

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
        return {
            "slot": self.slot,
            "effective_labeled_unit_count": len(state["verdict_entries"]),
            "labeled_import_count": len(state["labeled_imports"]),
            "pending_change_count": int(state["pending_change_count"]),
            "retrain_label_threshold": self.retrain_label_threshold,
            "next_retrain_in": max(0, self.retrain_label_threshold - int(state["pending_change_count"])),
            "retrain_blocker": state.get("last_retrain_blocker"),
            "latest_snapshot": display_snapshot,
            "latest_retrain_request": requests[0] if requests else None,
            "latest_completed_retrain": latest_completed,
            "production_model": production_request,
            "production_model_ref": production_model_ref or None,
            "production_promoted_at": (
                state.get("production_promoted_at")
                or (production_request or {}).get("promoted_to_production_at")
                or (production_request or {}).get("finished_at")
            ),
            "retrain_history": requests,
            "latest_completed_model_ref": production_model_ref or None,
            "modeling_paths": self._summarize_modeling_paths(state),
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
