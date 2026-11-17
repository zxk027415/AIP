# -*- coding: utf-8 -*-
"""
services/scheduler/tasks/pv_fault_tasks.py — 光伏故障诊断调度任务。

模拟喂数据由 pv_mock_data_feed 写入 training_samples；本模块负责每日预测，
复用 quickval 预测工作流与累计训练完成的模型，不会伪造预测或训练标签。
"""

from __future__ import annotations

# @AI_GENERATED: 稳定 seq 预测批次内容寻址
import hashlib
# @AI_GENERATED: end
import json
import logging
import math
import os
import pickle
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.cumulative_training import CumulativeTrainingService
from services.iterative_labeling.label_registry import LabelRegistryService
from services.iterative_labeling.review_session import ReviewSessionService
# @AI_GENERATED: 点粒度时间窗口改造 — 按设备游标遍历预测
from services.db.models.pv_fault import DevicePredictionCursor
# @AI_GENERATED: end

logger = logging.getLogger(__name__)

_SLOT = "pv_fault"
_UNKNOWN_LABEL_RE = re.compile(r"^unknown_(\d+)$", re.IGNORECASE)
_BACKEND_SERVICE_DIR = Path(__file__).resolve().parents[3]
_PROJECT_ROOT = _BACKEND_SERVICE_DIR.parent


def _utc_now_iso() -> str:
    """Return an unambiguous UTC timestamp for persisted scheduler artifacts."""
    return datetime.now(timezone.utc).isoformat()


def _review_unit_id(value: Any) -> str:
    """Normalize database-like numeric IDs for stable review unit keys."""
    if value is None:
        return ""
    text = str(value)
    return text[:-2] if text.endswith(".0") else text


# @AI_GENERATED
def _create_prediction_review_session(
    batch_id: str,
    *,
    source_dataset_path: str,
    model_ref: str,
    predictions: List[Dict[str, Any]],
    modeling_path: str = "legacy_day",
    slot: str = _SLOT,
    window_config: Optional[Dict[str, Any]] = None,
    model_source: Optional[str] = None,
    model_candidate_id: Optional[str] = None,
) -> Dict[str, Any]:
    """把预测批次写入同一 ``slot`` 的审核队列，保留 TSC 日级结论与逐窗证据。"""
    resolved_slot = str(slot or "").strip()
    if not resolved_slot:
        raise ValueError("预测审核会话 slot 不能为空")

    effective_model_source = str(model_source or "").strip() or None
    effective_candidate_id = str(model_candidate_id or "").strip() or None
    if resolved_slot == "pv_tsc" and (not effective_model_source or not effective_candidate_id):
        try:
            from services.scheduler.slot_workflow_runner import resolve_slot_scheduler_model

            model_context = resolve_slot_scheduler_model(resolved_slot)
            resolved_artifact = str(model_context.get("model_artifact_ref") or "").replace("\\", "/")
            requested_artifact = str(model_ref or "").replace("\\", "/")
            if not resolved_artifact or resolved_artifact == requested_artifact:
                effective_model_source = (
                    effective_model_source
                    or str(model_context.get("source") or "").strip()
                    or None
                )
                effective_candidate_id = (
                    effective_candidate_id
                    or str(model_context.get("model_candidate_id") or "").strip()
                    or None
                )
        except Exception as exc:  # noqa: BLE001 — 审核主链不能因角色元数据查询失败而中断
            logger.warning("解析 %s 审核模型角色失败: %s", resolved_slot, exc)

    prediction_units = []
    detection_days: set[str] = set()
    for row in predictions:
        device_id = row.get("device_id")
        time_window = row.get("time_window")
        if device_id is None or time_window is None:
            continue
        site_id = row.get("site_id")
        branch_id = row.get("branch_id")
        detection_day = str(row.get("target_day") or time_window)[:10]
        if detection_day:
            detection_days.add(detection_day)
        unit: Dict[str, Any] = {
            "unit_key": (
                f"{_review_unit_id(site_id)}|{_review_unit_id(device_id)}|"
                f"{_review_unit_id(branch_id)}|{time_window}"
            ),
            "site_id": site_id,
            "device_id": device_id,
            "branch_id": branch_id,
            "time_window": time_window,
            "predicted_label": row.get("predicted_label"),
            "confidence": row.get("confidence", 0.0),
        }
        if resolved_slot == "pv_tsc" or modeling_path == "tsc":
            unit.update(
                {
                    "target_day": row.get("target_day") or time_window,
                    "n_windows": int(row.get("n_windows") or 0),
                    "per_window_predictions": _json_safe(
                        row.get("per_window_predictions") or []
                    ),
                    "per_window_details": _json_safe(row.get("per_window_details") or []),
                    "aggregation": row.get("aggregation") or "majority",
                    "model_name": row.get("model_name") or "MultiRocket",
                    "model_window_config": _json_safe(
                        row.get("model_window_config") or window_config or {}
                    ),
                    "model_ref": model_ref,
                    "model_source": effective_model_source,
                    "model_role": effective_model_source,
                    "model_candidate_id": effective_candidate_id,
                }
            )
        prediction_units.append(unit)
    if not prediction_units:
        raise ValueError(f"预测批次 {batch_id} 没有可审核的诊断单元")

    ordered_days = sorted(detection_days)
    detection_date = (
        ordered_days[0]
        if len(ordered_days) == 1
        else f"{ordered_days[0]}~{ordered_days[-1]}"
        if ordered_days
        else None
    )
    registry = LabelRegistryService(slot=resolved_slot)
    return ReviewSessionService(
        slot=resolved_slot,
        registry_service=registry,
    ).create_session(
        loop_id=f"scheduler-{batch_id}",
        prediction_batch_id=batch_id,
        prediction_units=prediction_units,
        llm_suggestions={},
        prediction_context={
            "slot": resolved_slot,
            "source_csv_path": source_dataset_path,
            "load_config": {},
            "window_config": dict(window_config or {}),
            "model_window_config": dict(window_config or {}),
            "label_map": registry.get_current().get("label_map", {}),
            "model_ref": model_ref,
            "modeling_path": modeling_path,
            "prediction_granularity": (
                "point" if modeling_path == _SEQ_ANNOTATION_MODELING_PATH else "day"
            ),
            "source": "scheduled_prediction",
            "review_kind": (
                "tsc_device_day_review"
                if resolved_slot == "pv_tsc" or modeling_path == "tsc"
                else "scheduled_prediction_review"
            ),
            "detection_date": detection_date,
            "model_source": effective_model_source,
            "model_role": effective_model_source,
            "model_candidate_id": effective_candidate_id,
        },
    )
# @AI_GENERATED: end


def _to_project_relative(path: Path) -> str:
    """Return a POSIX project-root-relative path suitable for persisted state."""
    try:
        return path.resolve().relative_to(_PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(f"路径不能位于项目根目录之外: {path}") from exc


def _is_missing(value: Any) -> bool:
    """Return whether a scalar prediction field is absent without coercing it."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _json_safe(value: Any) -> Any:
    """Convert pandas/NumPy scalar values to strict JSON-compatible values."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _production_model_ref() -> Optional[str]:
    """Read the pv_fault production pointer updated after successful retraining."""
    return CumulativeTrainingService(slot=_SLOT).get_production_model_ref()


_PREDICTION_CURSOR_PATH = (
    _BACKEND_SERVICE_DIR
    / "data"
    / "iterative_labeling"
    / "pv_scheduler"
    / _SLOT
    / "prediction_cursor.json"
)

_PREDICTION_LAST_RUN_PATH = (
    _BACKEND_SERVICE_DIR
    / "data"
    / "iterative_labeling"
    / "pv_scheduler"
    / _SLOT
    / "prediction_last_run.json"
)


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _current_source_fingerprint() -> Dict[str, Any]:
    """读取当前 mock 数据源指纹；失败时返回可诊断的占位信息。"""
    from services.db.datasources.pv_fault_mock import compute_pv_source_fingerprint

    return compute_pv_source_fingerprint()


def _load_prediction_cursor_state() -> Dict[str, Any]:
    """读取预测游标完整状态（含数据源指纹）。"""
    if not _PREDICTION_CURSOR_PATH.exists():
        return {}
    try:
        payload = json.loads(_PREDICTION_CURSOR_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("PV prediction cursor unreadable; treating as empty: %s", exc)
        return {}


def _parse_cursor_time(state: Dict[str, Any]) -> Optional[datetime]:
    timestamp = state.get("last_predicted_time")
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(str(timestamp))
    except ValueError:
        return None


def _align_prediction_cursor_to_source(
    source_fp: Dict[str, Any],
) -> Tuple[Optional[datetime], bool, Optional[str]]:
    """按数据源指纹对齐游标。

    返回 (effective_cursor, reset_happened, previous_fingerprint)。
    指纹缺失或不一致时清空业务时间游标，避免跨数据集时间线串扰。
    """
    state = _load_prediction_cursor_state()
    previous_fp = None
    if isinstance(state.get("source_fingerprint"), dict):
        previous_fp = state["source_fingerprint"].get("fingerprint")
    current_fp = source_fp.get("fingerprint")
    cursor = _parse_cursor_time(state)

    if previous_fp and current_fp and previous_fp == current_fp:
        return cursor, False, previous_fp

    # 无指纹的老游标，或指纹变更：重置业务时间水位，绑定新指纹
    reset_payload = {
        "batch_id": state.get("batch_id"),
        "last_predicted_time": None,
        "source_fingerprint": source_fp,
        "updated_at": _utc_now_iso(),
        "reset_reason": "source_fingerprint_changed" if previous_fp else "source_fingerprint_initialized",
        "previous_fingerprint": previous_fp,
        "previous_last_predicted_time": state.get("last_predicted_time"),
    }
    _atomic_write_json(_PREDICTION_CURSOR_PATH, reset_payload)
    logger.info(
        "pv_prediction_task: prediction cursor reset for source fingerprint "
        "previous=%s current=%s previous_time=%s",
        previous_fp,
        current_fp,
        state.get("last_predicted_time"),
    )
    return None, True, previous_fp


def _save_prediction_cursor(
    batch_id: str,
    last_predicted_time: Any,
    source_fp: Optional[Dict[str, Any]] = None,
) -> None:
    """Atomically advance the watermark only after records and the review batch are durable."""
    timestamp = pd.Timestamp(last_predicted_time).to_pydatetime().replace(tzinfo=None).isoformat()
    payload: Dict[str, Any] = {
        "batch_id": batch_id,
        "last_predicted_time": timestamp,
        "updated_at": _utc_now_iso(),
    }
    if source_fp is not None:
        payload["source_fingerprint"] = source_fp
    else:
        existing = _load_prediction_cursor_state()
        if existing.get("source_fingerprint"):
            payload["source_fingerprint"] = existing["source_fingerprint"]
    _atomic_write_json(_PREDICTION_CURSOR_PATH, payload)


def reset_prediction_cursor(reason: str = "manual_reset", device_scope: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """手动清空预测游标，并绑定当前数据源指纹。

    Parameters
    ----------
    device_scope : 可选设备三元组列表。传入时只重置这些设备的游标，
        不动其他两千多台——避免重置后第一轮对所有设备逐台 MAX(time) 像卡死。
        不传则保持旧行为（全部重置）。
    """
    try:
        source_fp = _current_source_fingerprint()
    except Exception as exc:
        source_fp = {"error": str(exc)}
    previous = _load_prediction_cursor_state()
    payload = {
        "batch_id": None,
        "last_predicted_time": None,
        "source_fingerprint": source_fp if "fingerprint" in source_fp else None,
        "updated_at": _utc_now_iso(),
        "reset_reason": reason,
        "previous_fingerprint": (
            previous.get("source_fingerprint", {}).get("fingerprint")
            if isinstance(previous.get("source_fingerprint"), dict)
            else None
        ),
        "previous_last_predicted_time": previous.get("last_predicted_time"),
    }
    _atomic_write_json(_PREDICTION_CURSOR_PATH, payload)
    cleared_cursors = 0
    try:
        from services.db.adapter import DBAdapter
        from services.db.config import DBConfig
        from services.db.repositories.ingestion_tracker import IngestionTrackerRepository

        adapter = DBAdapter(DBConfig())
        try:
            # 两条路径的设备游标都清：验证点级时不会被旧 seq 游标挡住。
            # device_scope 不为空时只重置指定设备，避免全量重置后逐台打 MAX(time) 卡死。
            cleared_cursors = IngestionTrackerRepository(adapter).reset_path_cursors(
                slot="pv_fault",
                modeling_path=None,
                device_scope=device_scope,
            )
        finally:
            dispose = getattr(adapter, "dispose", None)
            if callable(dispose):
                dispose()
    except Exception as exc:  # noqa: BLE001 — JSON 游标已清，设备表失败不能阻断手动重置
        logger.warning("reset_prediction_cursor: 清空路径设备游标失败: %s", exc)
    payload["cleared_device_cursors"] = cleared_cursors
    _save_prediction_last_run(
        {
            "status": "cursor_reset",
            "reason": reason,
            "message": "预测进度已重置，下次预测将从当前数据源重新计算。",
            "source_fingerprint": payload.get("source_fingerprint"),
            "cleared_device_cursors": cleared_cursors,
            "updated_at": payload["updated_at"],
        }
    )
    return payload


def _save_prediction_last_run(payload: Dict[str, Any]) -> None:
    _atomic_write_json(_PREDICTION_LAST_RUN_PATH, payload)


def get_prediction_cursor_status() -> Dict[str, Any]:
    """供调度/精度运营读取：游标、指纹对齐、最近一次跳过原因。"""
    state = _load_prediction_cursor_state()
    last_run: Dict[str, Any] = {}
    if _PREDICTION_LAST_RUN_PATH.exists():
        try:
            loaded = json.loads(_PREDICTION_LAST_RUN_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                last_run = loaded
        except (OSError, ValueError, json.JSONDecodeError):
            last_run = {}

    current_fp: Optional[Dict[str, Any]] = None
    fingerprint_error: Optional[str] = None
    try:
        current_fp = _current_source_fingerprint()
    except Exception as exc:
        fingerprint_error = str(exc)

    stored_fp = state.get("source_fingerprint") if isinstance(state.get("source_fingerprint"), dict) else None
    aligned = bool(
        current_fp
        and stored_fp
        and current_fp.get("fingerprint")
        and stored_fp.get("fingerprint") == current_fp.get("fingerprint")
    )
    return {
        "task_id": "pv_prediction",
        "cursor": {
            "last_predicted_time": state.get("last_predicted_time"),
            "batch_id": state.get("batch_id"),
            "updated_at": state.get("updated_at"),
            "source_fingerprint": stored_fp,
            "reset_reason": state.get("reset_reason"),
        },
        "current_source_fingerprint": current_fp,
        "fingerprint_aligned": aligned,
        "fingerprint_error": fingerprint_error,
        "last_run": last_run,
    }


def _load_prediction_cursor() -> Optional[datetime]:
    """兼容旧调用：仅返回业务时间水位（不做指纹对齐）。"""
    return _parse_cursor_time(_load_prediction_cursor_state())


def _resolve_model_artifact(model_ref: str) -> Tuple[str, Path, str, str]:
    """Resolve a model ID or safe relative pkl path without persisting absolutes."""
    requested = str(model_ref or "").strip()
    if not requested:
        raise ValueError("model_ref 不能为空")
    requested_path = Path(requested)
    if requested_path.is_absolute():
        raise ValueError("model_ref 必须是模型标识或相对项目根目录路径")

    candidates: List[Path] = []
    if requested_path.suffix.lower() == ".pkl" or len(requested_path.parts) > 1:
        candidates.extend((_PROJECT_ROOT / requested_path, _BACKEND_SERVICE_DIR / requested_path))
    else:
        model_id = requested_path.stem
        candidates.append(_BACKEND_SERVICE_DIR / "data" / "models" / f"{model_id}.pkl")

    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(_PROJECT_ROOT)
        except ValueError:
            continue
        if resolved.is_file() and resolved.suffix.lower() == ".pkl":
            return (
                resolved.stem,
                resolved,
                _to_project_relative(resolved),
                os.path.relpath(resolved, _BACKEND_SERVICE_DIR).replace(os.sep, "/"),
            )
    raise FileNotFoundError(f"PV fault model not found for model_ref={requested}")


def _resolve_seq_annotation_artifact(model_ref: str) -> Tuple[str, Path, str]:
    """解析目录型序列标注工件，拒绝绝对路径和项目外目录。"""
    requested = str(model_ref or "").strip()
    if not requested:
        raise ValueError("model_ref 不能为空")
    requested_path = Path(requested)
    if requested_path.is_absolute():
        raise ValueError("model_ref 必须是模型标识或相对路径")

    candidates: List[Path] = []
    if len(requested_path.parts) > 1:
        candidates.extend(
            (_BACKEND_SERVICE_DIR / requested_path, _PROJECT_ROOT / requested_path)
        )
    else:
        candidates.append(
            _BACKEND_SERVICE_DIR / "data" / "models" / "seq_annotation" / requested
        )
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
            resolved.relative_to(_PROJECT_ROOT)
        except ValueError:
            continue
        if (resolved / "metadata.json").is_file() and (resolved / "model.pt").is_file():
            metadata = json.loads((resolved / "metadata.json").read_text(encoding="utf-8"))
            artifact_ref = str(metadata.get("model_ref") or "").strip()
            if artifact_ref and artifact_ref != requested_path.name:
                continue
            return requested_path.name, resolved, _to_project_relative(resolved)
    raise FileNotFoundError(
        f"PV fault seq_annotation artifact not found for model_ref={requested}"
    )


# @AI_GENERATED: 预测必须同时读回特征契约与样本策略
# （原 _load_feature_list 只读 feature_list，已被本函数取代并删除）
def _load_model_contract(model_file: Path) -> Tuple[List[str], Optional[Dict[str, Any]]]:
    """读回模型 pkl 里的 ``feature_list`` 与 ``sample_strategy``。

    ``sample_strategy`` 决定预测侧如何把测量数据切成样本。原实现只读
    ``feature_list``，切分交给工作流模板里写死的 ``solar_mode=day_and_night``
    （按功率值判定），与逐点标签路径按自然日/时钟的切法不一致：模型在整天聚合上
    训练、预测时却喂半天聚合，夜间窗的统计特征会整体塌向 0，结果不可信。

    Returns:
        (feature_list, sample_strategy)；后者可能为 None（老模型/legacy 路径）。
    """
    with model_file.open("rb") as handle:
        payload = pickle.load(handle)
    feature_list = payload.get("feature_list") if isinstance(payload, dict) else None
    if not isinstance(feature_list, list) or not feature_list:
        raise ValueError("模型 pkl 缺少非空 feature_list，拒绝执行不一致的预测")
    strategy = payload.get("sample_strategy") if isinstance(payload, dict) else None
    if strategy is not None and not isinstance(strategy, dict):
        logger.warning(
            "pv_prediction_task: 模型 %s 的 sample_strategy 类型异常(%s)，按缺失处理",
            model_file.name,
            type(strategy).__name__,
        )
        strategy = None
    return [str(feature) for feature in feature_list], strategy


# 全天逐点序列路径；传统模型内部采样策略从模型工件读取，
# 不再作为独立建模路径暴露。
_SEQ_ANNOTATION_MODELING_PATH = "seq_annotation"


def _production_modeling_path() -> str:
    """读取当前生产建模路径（legacy_day / seq_annotation）。"""
    try:
        paths = CumulativeTrainingService(slot=_SLOT).get_modeling_paths()
        return str(paths.get("production_path") or "legacy_day").strip() or "legacy_day"
    except Exception as exc:
        # 读不到指针时按 legacy 处理：宁可走老口径，也不要用错误的切分静默预测。
        logger.warning("pv_prediction_task: 无法读取生产建模路径，按 legacy_day 处理: %s", exc)
        return "legacy_day"
# @AI_GENERATED: end


def _workflow_config_set(config: Any, key: str, value: Any) -> None:
    """Update a workflow node config regardless of its Pydantic/dict representation."""
    if isinstance(config, dict):
        config[key] = value
    else:
        setattr(config, key, value)


_PREDICTION_INPUT_BASE_COLUMNS = ["time", "site_id", "device_id", "branch_id", "value", "i_cal"]


def _write_prediction_input(
    rows: Any,
    batch_id: str,
    extra_columns: Optional[List[str]] = None,
    # @AI_GENERATED: 允许第三产品槽将不可变预测输入写入自己的分区
    *,
    slot: str = _SLOT,
    # @AI_GENERATED: end
) -> Tuple[Path, str]:
    """Persist raw, unlabeled observations as the review/backfill source CSV.

    Args:
        rows: 观测行列表或已切好样本的 DataFrame。
        extra_columns: 需要一并写出的附加列（带持久化采样策略的传统模型会使用
            ``time_window`` / ``period_role`` 及 ``period_is_*`` / ``night_*`` 派生列）。带 ``#`` 的
            ``time_window`` 会被 ``time_window_split`` 识别为显式样本边界并原样保留，
            从而让预测样本粒度与训练完全一致。
    """
    # @AI_GENERATED: 输入证据必须与调用产品槽同目录，禁止 pv_tsc 写入 pv_fault
    resolved_slot = str(slot or "").strip()
    if not resolved_slot:
        raise ValueError("预测输入 slot 不能为空")
    input_dir = (
        _BACKEND_SERVICE_DIR
        / "data"
        / "iterative_labeling"
        / "prediction_inputs"
        / resolved_slot
    )
    # @AI_GENERATED: end
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / f"{batch_id}.csv"
    frame = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    columns = list(_PREDICTION_INPUT_BASE_COLUMNS)
    # @AI_GENERATED: 附加列只写实际存在的，避免整列 NaN 污染下游特征
    for column in extra_columns or []:
        if column in frame.columns and column not in columns:
            columns.append(column)
    # @AI_GENERATED: end
    frame = frame.reindex(columns=columns)
    if frame.empty:
        raise ValueError("未标注样本为空，不能创建预测输入")
    frame.to_csv(input_path, index=False, encoding="utf-8")
    return input_path, _to_project_relative(input_path)


def _load_label_name_to_id() -> Dict[str, int]:
    """Load pv_fault label registry name→id map for decoded workflow strings.

    读失败必须抛出：工作流输出的是标签名，没有这张映射表 ``_parse_predicted_label``
    会把每条预测静默解析成 ``None`` 并整批丢弃，最终表现为「预测跑完了但一条没落库」。
    """
    # @AI_GENERATED: 原实现 except 后返回 {}，会静默丢弃全部预测；改为抛出。
    from services.iterative_labeling.label_registry import LabelRegistryService

    try:
        registry = LabelRegistryService(slot=_SLOT).get_current()
    except Exception as exc:
        raise RuntimeError(
            f"pv_fault 标签注册表不可读，无法把预测标签名解析为 label_id：{exc}"
        ) from exc
    mapping: Dict[str, int] = {}
    for item in registry.get("labels", []):
        name = str(item.get("label_name") or "").strip()
        label_id = item.get("label_id")
        if name and label_id is not None:
            mapping[name] = int(label_id)
    if not mapping:
        raise RuntimeError("pv_fault 标签注册表为空，无法解析预测标签名")
    return mapping
    # @AI_GENERATED: end


def _parse_predicted_label(
    raw_label: Any,
    label_name_to_id: Optional[Dict[str, int]] = None,
) -> Optional[int]:
    """Parse workflow label outputs; treat empty/NaN placeholders as missing."""
    if _is_missing(raw_label):
        return None
    if isinstance(raw_label, str):
        stripped = raw_label.strip()
        if not stripped or stripped.lower() in {"nan", "none", "null"}:
            return None
        # label_encode decode 对训练 label_map 未覆盖的类会输出 unknown_{int}
        unknown_match = _UNKNOWN_LABEL_RE.match(stripped)
        if unknown_match:
            return int(unknown_match.group(1))
        name_map = label_name_to_id or {}
        if stripped in name_map:
            return name_map[stripped]
        raw_label = stripped
    try:
        return int(float(raw_label))
    except (TypeError, ValueError):
        return None


def _normalize_predictions(raw_predictions: Any) -> List[Dict[str, Any]]:
    """Validate real workflow results before they become auditable predictions."""
    if not isinstance(raw_predictions, list) or not raw_predictions:
        raise RuntimeError("预测工作流未返回非空 fault_predictions")

    predictions: List[Dict[str, Any]] = []
    skipped_invalid_label = 0
    label_name_to_id = _load_label_name_to_id()
    required_fields = ("site_id", "device_id", "branch_id", "time_window")
    for index, raw in enumerate(raw_predictions):
        if not isinstance(raw, dict):
            raise RuntimeError(f"fault_predictions[{index}] 不是对象")
        missing = [field for field in required_fields if _is_missing(raw.get(field))]
        raw_label = raw.get("predicted_label", raw.get("predictions", raw.get("predict_label")))
        predicted_label = _parse_predicted_label(raw_label, label_name_to_id)
        if predicted_label is None:
            skipped_invalid_label += 1
            logger.warning(
                "pv_prediction_task: skip fault_predictions[%d] due to unparseable predicted_label=%r",
                index,
                raw_label,
            )
            continue
        if missing:
            raise RuntimeError(f"fault_predictions[{index}] 缺少必要字段: {', '.join(missing)}")

        confidence = raw.get("confidence")
        if _is_missing(confidence):
            normalized_confidence = None
        else:
            try:
                normalized_confidence = float(confidence)
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"fault_predictions[{index}] 的 confidence 非数值") from exc
            if not 0.0 <= normalized_confidence <= 1.0:
                raise RuntimeError(f"fault_predictions[{index}] 的 confidence 超出 [0, 1]")

        normalized = {
            "site_id": raw["site_id"],
            "device_id": raw["device_id"],
            "branch_id": raw["branch_id"],
            "time_window": raw["time_window"],
            "predicted_label": predicted_label,
            "confidence": normalized_confidence,
        }
        detail = raw.get("prediction_detail")
        if detail is not None:
            if not isinstance(detail, dict):
                raise RuntimeError(f"fault_predictions[{index}] 的 prediction_detail 不是对象")
            timestamps = detail.get("timestamps") or []
            point_predictions = detail.get("point_predictions") or []
            raw_point_predictions = detail.get("raw_point_predictions") or []
            point_confidences = detail.get("point_confidences") or []
            segments = detail.get("segment_predictions") or []
            postprocessing = detail.get("postprocessing") or {}
            if not all(
                isinstance(values, list)
                for values in (
                    timestamps,
                    point_predictions,
                    raw_point_predictions,
                    point_confidences,
                    segments,
                )
            ):
                raise RuntimeError(f"fault_predictions[{index}] 的逐点详情字段必须是数组")
            if not isinstance(postprocessing, dict):
                raise RuntimeError(f"fault_predictions[{index}] 的 postprocessing 必须是对象")
            if not (
                len(timestamps) == len(point_predictions) == len(point_confidences)
            ):
                raise RuntimeError(f"fault_predictions[{index}] 的逐点详情长度不一致")
            if raw_point_predictions and len(raw_point_predictions) != len(timestamps):
                raise RuntimeError(f"fault_predictions[{index}] 的 raw_point_predictions 长度不一致")
            # @AI_GENERATED: 审计布尔严格保留 JSON 语义，禁止字符串真值污染
            trained_full_day = detail.get("trained_full_day")
            if not isinstance(trained_full_day, bool):
                raise RuntimeError(
                    f"fault_predictions[{index}] 的 trained_full_day 必须为 JSON boolean"
                )
            normalized["prediction_detail"] = {
                "granularity": "point",
                "timestamps": timestamps,
                "point_predictions": point_predictions,
                "raw_point_predictions": raw_point_predictions,
                "point_confidences": point_confidences,
                "segment_predictions": segments,
                "postprocessing": postprocessing,
                "n_points_predicted": len(point_predictions),
                "model_name": detail.get("model_name"),
                "seq_len_used": detail.get("seq_len_used"),
                "trained_full_day": trained_full_day,
            }
            # @AI_GENERATED: end
        predictions.append(_json_safe(normalized))

    if not predictions:
        raise RuntimeError(
            "预测工作流返回的结果均无法解析为有效标签"
            + (f"（跳过 {skipped_invalid_label} 条空标签）" if skipped_invalid_label else "")
        )
    if skipped_invalid_label:
        logger.warning(
            "pv_prediction_task: skipped %d predictions with empty/invalid labels; kept %d",
            skipped_invalid_label,
            len(predictions),
        )
    return predictions


# @AI_GENERATED: seq 设备日幂等键、不可变批次恢复与原子审核持久化

def _seq_sample_key(time_window: str):
    """把序列标注的设备日窗口解析为 (business_date, sample_id) 幂等键。

    seq_annotation 场景下 ``time_window`` 为 ISO 日期（如 ``2026-08-12``）。
    ``sample_id`` 采用 ``{date}#point`` 对齐逐点样本粒度；解析失败时业务日回退为
    当天日期（键仍需保持确定性），以保证失败重试的幂等。
    """
    raw = str(time_window or "").strip()
    try:
        business_date = datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        business_date = datetime.utcnow().date()
    sample_id = f"{raw[:10]}#point" if raw else f"{business_date.isoformat()}#point"
    return business_date, sample_id


def _seq_prediction_batch_id(
    model_ref: str,
    predictions: List[Dict[str, Any]],
) -> str:
    """为同一模型和同一组设备日生成稳定批次 ID，供失败重试复用审核会话。"""
    units = sorted(
        {
            (
                _review_unit_id(item.get("site_id")),
                _review_unit_id(item.get("device_id")),
                _review_unit_id(item.get("branch_id")),
                str(item.get("time_window") or ""),
            )
            for item in predictions
        }
    )
    if not units:
        raise ValueError("seq_annotation 预测为空，不能生成批次 ID")
    canonical = json.dumps(
        {"model_ref": str(model_ref), "units": units},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    return f"pred-seq-{digest}"


def _load_seq_recovery_batch(
    batch_id: str,
    model_ref: str,
) -> Tuple[List[Dict[str, Any]], str, Dict[tuple, datetime]]:
    """加载首次落盘的不可变 seq 批次，禁止重试用新推理覆盖旧审核事实。"""
    from services.iterative_labeling.review_explanations import load_prediction_batch

    payload = load_prediction_batch(_SLOT, batch_id)
    if not isinstance(payload, dict):
        raise RuntimeError(f"恢复批次 {batch_id} 缺失或损坏，拒绝覆盖重建")
    if str(payload.get("model_ref") or "") != str(model_ref):
        raise RuntimeError(f"恢复批次 {batch_id} 的 model_ref 不一致")
    if payload.get("modeling_path") != _SEQ_ANNOTATION_MODELING_PATH:
        raise RuntimeError(f"恢复批次 {batch_id} 不是 seq_annotation 批次")

    raw_predictions = payload.get("predictions")
    if not isinstance(raw_predictions, list) or not raw_predictions:
        raise RuntimeError(f"恢复批次 {batch_id} 没有有效 predictions")
    predictions = _normalize_predictions(raw_predictions)
    source_dataset_path = str(payload.get("dataset_version") or "").strip()
    if not source_dataset_path:
        raise RuntimeError(f"恢复批次 {batch_id} 缺少 dataset_version")

    raw_advances = payload.get("cursor_advance_times")
    if not isinstance(raw_advances, list) or not raw_advances:
        raise RuntimeError(f"恢复批次 {batch_id} 缺少 cursor_advance_times")
    advance_times: Dict[tuple, datetime] = {}
    for index, item in enumerate(raw_advances):
        if not isinstance(item, dict):
            raise RuntimeError(f"恢复批次 {batch_id} 的游标项 {index} 不是对象")
        try:
            advance_time = datetime.fromisoformat(str(item["last_predicted_time"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"恢复批次 {batch_id} 的游标项 {index} 时间无效"
            ) from exc
        key = (item.get("site_id"), item.get("device_id"), item.get("branch_id"))
        advance_times[key] = advance_time
    return predictions, source_dataset_path, advance_times


def _partition_seq_predictions_for_recovery(
    pv_repo: PVFaultRepository,
    model_ref: str,
    predictions: List[Dict[str, Any]],
    recovery_candidates: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """按数据库首次批次引用拆分本轮新增设备日与待恢复旧批次。"""

    def unit_key(item: Dict[str, Any]) -> tuple:
        business_date, sample_id = _seq_sample_key(item["time_window"])
        return (
            item["site_id"],
            item["device_id"],
            item["branch_id"],
            business_date,
            sample_id,
        )

    candidates_by_key: Dict[tuple, Dict[str, Any]] = {}
    for candidate in [*predictions, *(recovery_candidates or [])]:
        candidates_by_key[unit_key(candidate)] = candidate

    existing_keys: set[tuple] = set()
    recovery_batches: Dict[str, str] = {}
    for key, candidate in candidates_by_key.items():
        existing = pv_repo.find_prediction_record(
            site_id=candidate["site_id"],
            device_id=candidate["device_id"],
            branch_id=candidate["branch_id"],
            business_date=key[3],
            sample_id=key[4],
        )
        if existing is None:
            continue

        existing_keys.add(key)
        raw_existing_context = existing.input_feature_json
        existing_context = (
            raw_existing_context if isinstance(raw_existing_context, dict) else {}
        )
        existing_batch_id = str(
            existing_context.get("prediction_batch_id") or ""
        ).strip()
        existing_model_ref = str(existing_context.get("model_ref") or "").strip()
        if existing_batch_id.startswith("pred-seq-") and existing_model_ref:
            # 数据库记录中的首次 batch ID 和 model ref 才是恢复真源；当前生产模型
            # 可能已 Promote，不能拿 M2 去校验或重建 M1 的不可变批次。
            previous_model_ref = recovery_batches.get(existing_batch_id)
            if previous_model_ref and previous_model_ref != existing_model_ref:
                raise RuntimeError(
                    f"恢复批次 {existing_batch_id} 存在冲突 model_ref"
                )
            recovery_batches[existing_batch_id] = existing_model_ref
            if existing_model_ref != str(model_ref):
                logger.info(
                    "pv_prediction_task: recover seq batch %s from prior model %s "
                    "while current model is %s",
                    existing_batch_id,
                    existing_model_ref,
                    model_ref,
                )
            continue
        logger.info(
            "pv_prediction_task: seq_annotation skip duplicate %s %s %s",
            candidate["device_id"],
            candidate["time_window"],
            key[4],
        )

    new_predictions = [
        prediction for prediction in predictions if unit_key(prediction) not in existing_keys
    ]
    return new_predictions, recovery_batches


# @AI_GENERATED
def _write_prediction_batch(
    batch_id: str,
    *,
    source_dataset_path: str,
    model_ref: str,
    model_path: str,
    predictions: List[Dict[str, Any]],
    unit_features: Optional[Dict[str, Any]] = None,
    feature_list: Optional[List[str]] = None,
    modeling_path: str = "legacy_day",
    cursor_advance_times: Optional[Dict[tuple, datetime]] = None,
    slot: str = _SLOT,
) -> None:
    """持久化审核批次；目录和 payload 的 ``slot`` 必须与调用产品槽一致。"""
    resolved_slot = str(slot or "").strip()
    if not resolved_slot:
        raise ValueError("预测批次 slot 不能为空")
    batch_dir = (
        _BACKEND_SERVICE_DIR
        / "data"
        / "iterative_labeling"
        / "prediction_batches"
        / resolved_slot
    )
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_path = batch_dir / f"{batch_id}.json"
    payload = {
        "slot": resolved_slot,
        "dataset_version": source_dataset_path,
        "model_ref": model_ref,
        "model_path": model_path,
        "modeling_path": modeling_path,
        "prediction_granularity": (
            "point" if modeling_path == _SEQ_ANNOTATION_MODELING_PATH else "day"
        ),
        "feature_list": list(feature_list or []),
        "unit_features": unit_features or {},
        "predictions": predictions,
        "cursor_advance_times": [
            {
                "site_id": key[0],
                "device_id": key[1],
                "branch_id": key[2],
                "last_predicted_time": value.isoformat(),
            }
            for key, value in sorted(
                (cursor_advance_times or {}).items(),
                key=lambda item: tuple(str(part) for part in item[0]),
            )
        ],
        "created_at": _utc_now_iso(),
    }
    temp_fd, temp_path = tempfile.mkstemp(dir=str(batch_dir), suffix=".tmp", text=True)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        Path(temp_path).replace(batch_path)
    except Exception:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise
# @AI_GENERATED: end


# @AI_GENERATED: 保留任务注册外壳，每轮惰性读取生产路径并分派双路径策略
def make_pv_prediction_task(
    pv_repo: PVFaultRepository,
    model_ref: Optional[str] = None,
) -> Callable[[], None]:
    """创建光伏预测任务外壳，并在每次触发时按当前生产路径即时分派。

    ``model_ref`` 参数仅为兼容既有任务注册调用保留；实际模型引用由
    ``DualPathScheduler`` 每轮读取 modeling-paths 登记取得，路径切换无需重启服务。
    """

    def pv_prediction_task() -> None:
        try:
            from services.scheduler.pv_dual_path.legacy_day_strategy import (
                LegacyDayStrategy,
            )
            from services.scheduler.pv_dual_path.scheduler import DualPathScheduler
            from services.scheduler.pv_dual_path.seq_daily_strategy import (
                SeqDailyStrategy,
            )

            scheduler = DualPathScheduler(
                strategies={
                    "legacy_day": LegacyDayStrategy(pv_repo),
                    "seq_annotation": SeqDailyStrategy(pv_repo),
                }
            )
            scheduler.dispatch(slot="pv_fault")
        except Exception as exc:
            _save_prediction_last_run(
                {
                    "status": "failed",
                    "reason": "exception",
                    "message": str(exc),
                    "updated_at": _utc_now_iso(),
                }
            )
            raise

    return pv_prediction_task
# @AI_GENERATED: end


def _run_seq_annotation_prediction_cycle(
    pv_repo: PVFaultRepository,
    model_ref: str,
) -> None:
    """按设备自然日执行全天逐点诊断；不完整的当天不推进游标。"""
    try:
        model_id, model_dir, model_path = _resolve_seq_annotation_artifact(model_ref)
        from services.iterative_labeling.seq_annotation.predictor import (
            SeqAnnotationPredictor,
        )

        from services.iterative_labeling.seq_annotation.production_contract import (
            assert_final_sequence_contract,
        )

        predictor = SeqAnnotationPredictor(str(model_dir))
        assert_final_sequence_contract(predictor.metadata)
    except (FileNotFoundError, TypeError, ValueError, RuntimeError) as exc:
        logger.error("pv_prediction_task: seq_annotation 工件不可用: %s", exc)
        _save_prediction_last_run(
            {
                "status": "skipped",
                "reason": "seq_annotation_model_invalid",
                "message": str(exc),
                "model_ref": model_ref,
                "modeling_path": _SEQ_ANNOTATION_MODELING_PATH,
                "updated_at": _utc_now_iso(),
            }
        )
        return
    if not predictor.supports_night or predictor.seq_len != 288:
        message = "序列标注模型不是全天 288 点工件，拒绝进入生产预测"
        logger.error("pv_prediction_task: %s", message)
        _save_prediction_last_run(
            {
                "status": "skipped",
                "reason": "seq_annotation_not_full_day",
                "message": message,
                "model_ref": model_ref,
                "updated_at": _utc_now_iso(),
            }
        )
        return

    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from sqlalchemy import select

    cutoff = datetime.utcnow()
    cursor_adapter = DBAdapter(DBConfig())
    with cursor_adapter.get_sync_session() as session:
        cursor_rows = session.execute(select(DevicePredictionCursor)).scalars().all()
        device_cursors: Dict[tuple, Optional[datetime]] = {
            (row.site_id, row.device_id, row.branch_id): row.last_predicted_time
            for row in cursor_rows
        }
    cursor_adapter.dispose()
    if not device_cursors:
        _save_prediction_last_run(
            {
                "status": "skipped",
                "reason": "no_device_cursors",
                "message": "device_prediction_cursor 表为空，请先运行初始化脚本。",
                "modeling_path": _SEQ_ANNOTATION_MODELING_PATH,
                "updated_at": _utc_now_iso(),
            }
        )
        return

    all_rows: List[Dict[str, Any]] = []
    rows_by_device: Dict[tuple, List[Dict[str, Any]]] = {}
    for device_key, last_time in device_cursors.items():
        rows = pv_repo.query_unlabeled_by_point_labels(
            after_time=last_time,
            before_time=cutoff,
            site_id=device_key[0],
            device_id=device_key[1],
            branch_id=device_key[2],
        )
        if rows:
            rows_by_device[device_key] = rows
            all_rows.extend(rows)
    if not all_rows:
        _save_prediction_last_run(
            {
                "status": "skipped",
                "reason": "skipped_caught_up",
                "message": "所有设备均无新增待预测数据。",
                "modeling_path": _SEQ_ANNOTATION_MODELING_PATH,
                "updated_at": _utc_now_iso(),
            }
        )
        return

    raw_predictions: List[Dict[str, Any]] = []
    prediction_input_rows: List[Dict[str, Any]] = []
    recovery_candidates: List[Dict[str, Any]] = []
    skipped_incomplete_days = 0

    for device_key, rows in rows_by_device.items():
        frame = pd.DataFrame(rows)
        frame["time"] = pd.to_datetime(frame["time"], errors="coerce")
        frame = frame.dropna(subset=["time"]).sort_values("time")
        frame["_date"] = frame["time"].dt.date
        completed = frame[frame["_date"] < cutoff.date()]
        if completed.empty:
            skipped_incomplete_days += 1
            continue
        for day, _candidate_day_frame in completed.groupby("_date", sort=True):
            recovery_candidates.append(
                {
                    "site_id": device_key[0],
                    "device_id": device_key[1],
                    "branch_id": device_key[2],
                    "time_window": str(day),
                }
            )
            day_start = datetime.combine(day, datetime.min.time())
            full_day_rows = pv_repo.query_device_measurements(
                site_id=device_key[0],
                device_id=device_key[1],
                branch_id=device_key[2],
                time_start=day_start,
                time_end=day_start + timedelta(days=1),
            )
            if not full_day_rows:
                skipped_incomplete_days += 1
                continue
            day_frame = pd.DataFrame(full_day_rows)
            day_frame["time"] = pd.to_datetime(day_frame["time"], errors="coerce")
            day_frame = day_frame.dropna(subset=["time"]).sort_values("time")
            prediction_input_rows.extend(full_day_rows)
            result = predictor.predict_device_day(day_frame, include_night=True)
            if result.get("error"):
                logger.warning(
                    "pv_prediction_task: seq_annotation skip %s %s: %s",
                    device_key,
                    day,
                    result["error"],
                )
                skipped_incomplete_days += 1
                break
            raw_predictions.append(
                {
                    "site_id": device_key[0],
                    "device_id": device_key[1],
                    "branch_id": device_key[2],
                    "time_window": str(day),
                    "predicted_label": result["predicted_label"],
                    "confidence": result["confidence"],
                    "prediction_detail": {
                        "timestamps": result["timestamps"],
                        "point_predictions": result["point_predictions"],
                        "raw_point_predictions": result.get("raw_point_predictions") or [],
                        "point_confidences": result["point_confidences"],
                        "segment_predictions": result["segment_predictions"],
                        "postprocessing": result.get("postprocessing") or {},
                        "model_name": result["model_name"],
                        "seq_len_used": result["seq_len_used"],
                        "trained_full_day": result["trained_full_day"],
                    },
                }
            )

    predictions = (
        _normalize_predictions(raw_predictions) if raw_predictions else []
    )
    model_version = pv_repo.get_model_version(model_id)
    new_predictions, recovery_batches = _partition_seq_predictions_for_recovery(
        pv_repo,
        model_ref,
        predictions,
        recovery_candidates=recovery_candidates,
    )
    if not predictions and not recovery_batches:
        _save_prediction_last_run(
            {
                "status": "skipped",
                "reason": "no_complete_device_day",
                "message": "新增数据中没有满足质量门控的完整设备日，游标未推进。",
                "model_ref": model_ref,
                "modeling_path": _SEQ_ANNOTATION_MODELING_PATH,
                "updated_at": _utc_now_iso(),
            }
        )
        return

    batch_results: List[Dict[str, Any]] = []
    final_device_advance_times: Dict[tuple, datetime] = {}
    final_device_model_ids: Dict[tuple, Optional[str]] = {}
    inserted_records: List[Any] = []

    def merge_advance_times(
        values: Dict[tuple, datetime],
        cursor_model_id: Optional[str],
    ) -> None:
        for key, value in values.items():
            current = final_device_advance_times.get(key)
            if current is None or value >= current:
                final_device_advance_times[key] = value
                final_device_model_ids[key] = cursor_model_id

    # 先从数据库记录引用的不可变批次补建审核。即使本轮设备日集合发生增减，
    # 也不会覆盖首次 predictions/source/cursor 事实。
    for recovery_batch_id in sorted(recovery_batches):
        recovery_model_ref = recovery_batches[recovery_batch_id]
        recovered_predictions, recovered_source_path, recovered_advances = (
            _load_seq_recovery_batch(recovery_batch_id, recovery_model_ref)
        )
        recovered_session = _create_prediction_review_session(
            recovery_batch_id,
            source_dataset_path=recovered_source_path,
            model_ref=recovery_model_ref,
            predictions=recovered_predictions,
            modeling_path=_SEQ_ANNOTATION_MODELING_PATH,
        )
        recovery_model_version = pv_repo.get_model_version(recovery_model_ref)
        recovery_model_id = (
            recovery_model_ref if recovery_model_version is not None else None
        )
        merge_advance_times(recovered_advances, recovery_model_id)
        batch_results.append(
            {
                "batch_id": recovery_batch_id,
                "review_id": recovered_session["review_id"],
                "model_ref": recovery_model_ref,
                "prediction_count": len(recovered_predictions),
                "inserted_count": 0,
                "recovered": True,
            }
        )

    # 本轮数据库中不存在的设备日独立形成新批次；其身份和游标不混入旧批次。
    if new_predictions:
        new_batch_id = _seq_prediction_batch_id(model_ref, new_predictions)
        new_unit_keys = {
            (
                prediction["site_id"],
                prediction["device_id"],
                prediction["branch_id"],
                str(prediction["time_window"]),
            )
            for prediction in new_predictions
        }
        new_input_rows = []
        new_advance_times: Dict[tuple, datetime] = {}
        for row in prediction_input_rows:
            try:
                row_timestamp = pd.Timestamp(row["time"])
                row_day = str(row_timestamp.date())
            except (KeyError, TypeError, ValueError):
                continue
            row_key = (
                row.get("site_id"),
                row.get("device_id"),
                row.get("branch_id"),
                row_day,
            )
            if row_key in new_unit_keys:
                new_input_rows.append(row)
                device_key = row_key[:3]
                advance_time = row_timestamp.to_pydatetime()
                previous_time = new_advance_times.get(device_key)
                if previous_time is None or advance_time > previous_time:
                    new_advance_times[device_key] = advance_time
        if not new_input_rows or not new_advance_times:
            raise RuntimeError("新增 seq 预测没有对应的不可变输入测量和游标时间")

        _, new_source_dataset_path = _write_prediction_input(
            new_input_rows, new_batch_id
        )
        _write_prediction_batch(
            new_batch_id,
            source_dataset_path=new_source_dataset_path,
            model_ref=model_ref,
            model_path=model_path,
            predictions=new_predictions,
            modeling_path=_SEQ_ANNOTATION_MODELING_PATH,
            cursor_advance_times=new_advance_times,
        )

        record_payloads: List[Dict[str, Any]] = []
        for prediction in new_predictions:
            detail = prediction.get("prediction_detail") or {}
            business_date, sample_id = _seq_sample_key(prediction["time_window"])
            record_payloads.append(
                {
                    "model_version_id": model_id if model_version is not None else None,
                    "site_id": prediction["site_id"],
                    "device_id": prediction["device_id"],
                    "branch_id": prediction["branch_id"],
                    "predicted_label": prediction["predicted_label"],
                    "confidence": prediction["confidence"],
                    "business_date": business_date,
                    "sample_id": sample_id,
                    "input_feature_json": {
                        "prediction_batch_id": new_batch_id,
                        "time_window": prediction["time_window"],
                        "source_dataset_path": new_source_dataset_path,
                        "model_ref": model_ref,
                        "modeling_path": _SEQ_ANNOTATION_MODELING_PATH,
                        "prediction_granularity": "point",
                        "segment_predictions": detail.get("segment_predictions") or [],
                        "detail_ref": f"{new_batch_id}:{prediction['time_window']}",
                    },
                }
            )

        inserted_records = pv_repo.insert_prediction_records(record_payloads)
        new_review_session = _create_prediction_review_session(
            new_batch_id,
            source_dataset_path=new_source_dataset_path,
            model_ref=model_ref,
            predictions=new_predictions,
            modeling_path=_SEQ_ANNOTATION_MODELING_PATH,
        )
        merge_advance_times(
            new_advance_times,
            model_id if model_version is not None else None,
        )
        batch_results.append(
            {
                "batch_id": new_batch_id,
                "review_id": new_review_session["review_id"],
                "model_ref": model_ref,
                "prediction_count": len(new_predictions),
                "inserted_count": len(inserted_records),
                "recovered": False,
            }
        )

    if not batch_results:
        _save_prediction_last_run(
            {
                "status": "skipped",
                "reason": "all_duplicate",
                "message": "本批设备日预测记录均已存在且无可恢复批次，游标未推进。",
                "model_ref": model_ref,
                "modeling_path": _SEQ_ANNOTATION_MODELING_PATH,
                "updated_at": _utc_now_iso(),
            }
        )
        return

    if not final_device_advance_times:
        raise RuntimeError("seq 预测批次已送审但没有可推进的设备游标")

    from sqlalchemy.dialects.mysql import insert as mysql_insert

    now = datetime.utcnow()
    cursor_records = [
        {
            "site_id": key[0],
            "device_id": key[1],
            "branch_id": key[2],
            "last_predicted_time": advance_time,
            "last_predicted_at": now,
            "model_version_id": final_device_model_ids.get(key),
            "updated_at": now,
        }
        for key, advance_time in final_device_advance_times.items()
    ]
    write_adapter = DBAdapter(DBConfig())
    with write_adapter.get_sync_session() as session:
        statement = mysql_insert(DevicePredictionCursor).values(cursor_records)
        statement = statement.on_duplicate_key_update(
            last_predicted_time=statement.inserted.last_predicted_time,
            last_predicted_at=statement.inserted.last_predicted_at,
            model_version_id=statement.inserted.model_version_id,
            updated_at=statement.inserted.updated_at,
        )
        session.execute(statement)
    write_adapter.dispose()

    batch_ids = [item["batch_id"] for item in batch_results]
    review_ids = [item["review_id"] for item in batch_results]
    prediction_count = sum(item["prediction_count"] for item in batch_results)
    inserted_count = sum(item["inserted_count"] for item in batch_results)
    recovered_batch_count = sum(
        item.get("recovered") is True for item in batch_results
    )
    _save_prediction_last_run(
        {
            "status": "success",
            "reason": "predicted",
            "message": (
                f"序列标注已提交 {prediction_count} 个设备日逐点结果"
                f"（本次新增入库 {inserted_count} 条，恢复旧批次 "
                f"{recovered_batch_count} 个）"
            ),
            # 保留单值字段兼容现有状态消费者；多批次事实由复数字段完整表达。
            "batch_id": batch_ids[-1],
            "review_id": review_ids[-1],
            "batch_ids": batch_ids,
            "review_ids": review_ids,
            "prediction_count": prediction_count,
            "inserted_count": inserted_count,
            "device_count": len(final_device_advance_times),
            "recovered_batch_count": recovered_batch_count,
            "skipped_incomplete_days": skipped_incomplete_days,
            "model_ref": model_ref,
            "modeling_path": _SEQ_ANNOTATION_MODELING_PATH,
            "updated_at": _utc_now_iso(),
        }
    )
# @AI_GENERATED: end


def _run_pv_prediction_cycle(
    pv_repo: PVFaultRepository,
    model_ref: Optional[str] = None,
) -> None:
    # @AI_GENERATED: 点粒度时间窗口预测改造
    # 原逻辑：读全局 prediction_cursor.json → 整批取全部未标注行 → 整批预测
    # 新逻辑：读 device_prediction_cursor 表 → 每台设备按 (last_predicted_time, cutoff]
    #         取各自的测量点 → 各自跑 InferenceSampleGenerator → 整批写 PredictionRecord
    #         → 各自推进游标（失败不推进，下次补）
    # 后到的点：不需要任何特殊处理，下次 cron 触发时游标还在原处，
    #           晚到的点时间戳自然落进下次窗口，自动补上。
    # @AI_GENERATED: end

    resolved_ref = str(model_ref or "").strip() or _production_model_ref()
    if not resolved_ref:
        logger.info("MODEL_PENDING: pv_prediction_task is waiting for a pv_fault production model")
        _save_prediction_last_run({"status": "skipped", "reason": "model_pending",
                                   "message": "尚无可用模型，预测已跳过。", "updated_at": _utc_now_iso()})
        return

    modeling_path = _production_modeling_path()
    if modeling_path == _SEQ_ANNOTATION_MODELING_PATH:
        _run_seq_annotation_prediction_cycle(pv_repo, resolved_ref)
        return

    try:
        model_id, model_file, model_path, execution_model_path = _resolve_model_artifact(resolved_ref)
    except FileNotFoundError:
        logger.info("MODEL_PENDING: pv_prediction_task model artifact not found model_ref=%s", resolved_ref)
        _save_prediction_last_run({"status": "skipped", "reason": "model_pending",
                                   "message": f"模型工件不存在：{resolved_ref}", "updated_at": _utc_now_iso()})
        return

    feature_list, sample_strategy = _load_model_contract(model_file)
    # 历史 RF 模型可能保存 by_day / by_day_night 采样契约；它仍须在推理时复现，
    # 但该契约只是 legacy_day 的内部实现，不再形成第三、第四条业务路径。
    use_persisted_sample_strategy = bool(sample_strategy)

    # @AI_GENERATED: 点粒度改造 — cutoff = 本次 cron 触发时刻（UTC）
    cutoff = datetime.utcnow()
    # @AI_GENERATED: end
    # @AI_GENERATED: 点粒度改造 — 从 device_prediction_cursor 表读各设备游标
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from services.db.models.pv_fault import DevicePredictionCursor
    from sqlalchemy import select

    _db_adapter = DBAdapter(DBConfig())
    with _db_adapter.get_sync_session() as _sess:
        cursor_rows = _sess.execute(select(DevicePredictionCursor)).scalars().all()
        device_cursors: Dict[tuple, Optional[datetime]] = {
            (r.site_id, r.device_id, r.branch_id): r.last_predicted_time
            for r in cursor_rows
        }
    _db_adapter.dispose()

    if not device_cursors:
        logger.info("pv_prediction_task: device_prediction_cursor 为空，无设备可预测")
        _save_prediction_last_run({"status": "skipped", "reason": "no_device_cursors",
                                   "message": "device_prediction_cursor 表为空，请先运行初始化脚本。",
                                   "updated_at": _utc_now_iso()})
        return

    # 按设备查各自时间窗口内的测量点，汇总后一次性跑预测
    _query_by_time = (
        pv_repo.query_unlabeled_by_point_labels
        if use_persisted_sample_strategy
        else pv_repo.query_unlabeled_training_samples
    )

    all_rows: List[Dict[str, Any]] = []
    device_new_rows: Dict[tuple, List[Dict[str, Any]]] = {}
    skipped_caught_up = 0

    for (site_id, device_id, branch_id), last_time in device_cursors.items():
        rows = _query_by_time(
            after_time=last_time,
            before_time=cutoff,
            site_id=site_id,
            device_id=device_id,
            branch_id=branch_id,
        )
        if not rows:
            skipped_caught_up += 1
            continue
        device_new_rows[(site_id, device_id, branch_id)] = rows
        all_rows.extend(rows)

    if not all_rows:
        logger.info(
            "pv_prediction_task: cutoff=%s，%d 台设备均已追平，无新增待预测数据",
            cutoff.isoformat(), skipped_caught_up,
        )
        _save_prediction_last_run({
            "status": "skipped", "reason": "skipped_caught_up",
            "message": f"所有 {skipped_caught_up} 台设备截止 {cutoff.isoformat()} 均无新增数据。",
            "cutoff": cutoff.isoformat(), "modeling_path": modeling_path,
            "updated_at": _utc_now_iso(),
        })
        return

    logger.info(
        "pv_prediction_task: cutoff=%s，%d 台设备有新数据，共 %d 行，跳过 %d 台已追平",
        cutoff.isoformat(), len(device_new_rows), len(all_rows), skipped_caught_up,
    )
    # @AI_GENERATED: end

    batch_id = f"pred-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    # @AI_GENERATED: 点粒度改造 — 用所有设备汇总的测量行切推理样本
    split_audit: Optional[Dict[str, Any]] = None
    if use_persisted_sample_strategy:
        from services.iterative_labeling.inference_sample import (
            INFERENCE_DERIVED_COLUMNS,
            InferenceSampleGenerator,
        )
        measurements = pd.DataFrame(all_rows)
        measurements["time"] = pd.to_datetime(measurements["time"])
        try:
            sample_frame, split_audit = InferenceSampleGenerator().generate_inference_samples(
                measurements, str(model_file)
            )
        except ValueError as exc:
            message = (
                f"待预测数据未能按策略 {sample_strategy.get('split_mode')} 切出推理样本：{exc}"
            )
            logger.warning("pv_prediction_task: %s", message)
            _save_prediction_last_run({"status": "skipped", "reason": "no_inference_sample",
                                       "message": message, "model_ref": resolved_ref,
                                       "modeling_path": modeling_path,
                                       "unlabeled_rows": len(all_rows), "updated_at": _utc_now_iso()})
            return
        extra_columns = ["time_window", "period_role", *INFERENCE_DERIVED_COLUMNS]
        _input_path, source_dataset_path = _write_prediction_input(
            sample_frame, batch_id, extra_columns=extra_columns
        )
        logger.info(
            "pv_prediction_task: 推理样本已按 split_mode=%s 切出 samples=%d rows=%d",
            split_audit.get("split_mode"), split_audit.get("sample_count"), split_audit.get("row_count"),
        )
    else:
        _input_path, source_dataset_path = _write_prediction_input(all_rows, batch_id)
    # @AI_GENERATED: end

    from api.workflows_enhanced import _execute_pipeline_sync, load_workflow_from_file

    workflow = load_workflow_from_file("workflow-pv-fault-diag-quickval-predict-v1")
    if workflow is None:
        raise RuntimeError("预测工作流模板 workflow-pv-fault-diag-quickval-predict-v1 不存在")

    required_nodes = {"load_csv": False, "feature_select": False, "random_forest_classifier": False}
    for node in workflow.nodes:
        config = node.data.config
        function_id = config.get("functionId") if isinstance(config, dict) else getattr(config, "functionId", None)
        if function_id == "load_csv":
            _workflow_config_set(config, "file_path", source_dataset_path)
            required_nodes[function_id] = True
        elif function_id == "feature_select":
            _workflow_config_set(config, "feature_list", feature_list)
            _workflow_config_set(config, "model_path", execution_model_path)
            required_nodes[function_id] = True
        elif function_id == "random_forest_classifier":
            _workflow_config_set(config, "model_id", model_id)
            _workflow_config_set(config, "model_path", execution_model_path)
            required_nodes[function_id] = True
        elif function_id == "time_window_split" and use_persisted_sample_strategy:
            _workflow_config_set(config, "solar_mode", None)
            _workflow_config_set(config, "attach_night_features", False)
    if not all(required_nodes.values()):
        missing = [n for n, found in required_nodes.items() if not found]
        raise RuntimeError(f"预测工作流缺少必要节点: {', '.join(missing)}")

    execution_result = _execute_pipeline_sync(workflow)
    if not execution_result.get("success", False):
        raise RuntimeError(f"预测工作流执行失败: {execution_result.get('error', '未知错误')}")
    raw_predictions = execution_result.get("fault_predictions")
    unit_features: Dict[str, Any] = {}
    for raw in raw_predictions or []:
        if not isinstance(raw, dict):
            continue
        feats = raw.get("_features")
        if not isinstance(feats, dict) or not feats:
            continue
        uk = (
            f"{_review_unit_id(raw.get('site_id'))}|{_review_unit_id(raw.get('device_id'))}|"
            f"{_review_unit_id(raw.get('branch_id'))}|{raw.get('time_window')}"
        )
        unit_features[uk] = _json_safe(feats)
    predictions = _normalize_predictions(raw_predictions)

    model_version = pv_repo.get_model_version(model_id)
    for prediction in predictions:
        pv_repo.insert_prediction_record({
            "model_version_id": model_id if model_version is not None else None,
            "site_id": prediction["site_id"],
            "device_id": prediction["device_id"],
            "branch_id": prediction["branch_id"],
            "predicted_label": prediction["predicted_label"],
            "confidence": prediction["confidence"],
            "input_feature_json": {
                "prediction_batch_id": batch_id,
                "time_window": prediction["time_window"],
                "source_dataset_path": source_dataset_path,
                "model_ref": resolved_ref,
            },
        })

    _write_prediction_batch(
        batch_id,
        source_dataset_path=source_dataset_path,
        model_ref=resolved_ref,
        model_path=model_path,
        predictions=predictions,
        unit_features=unit_features,
        feature_list=feature_list,
        modeling_path=modeling_path,
    )
    review_session = _create_prediction_review_session(
        batch_id,
        source_dataset_path=source_dataset_path,
        model_ref=resolved_ref,
        predictions=predictions,
        modeling_path=modeling_path,
    )
    review_id = str(review_session["review_id"])

    # @AI_GENERATED: 点粒度改造 — 按设备推进各自游标到 cutoff（只推进有新数据的设备）
    from services.db.adapter import DBAdapter as _DBAdapter
    from services.db.config import DBConfig as _DBConfig
    from sqlalchemy.dialects.mysql import insert as _mysql_insert

    _cursor_adapter = _DBAdapter(_DBConfig())
    _now = datetime.utcnow()
    _cursor_records = [
        {
            "site_id": dk[0],
            "device_id": dk[1],
            "branch_id": dk[2],
            "last_predicted_time": cutoff,
            "last_predicted_at": _now,
            "model_version_id": model_id,
            "updated_at": _now,
        }
        for dk in device_new_rows
    ]
    with _cursor_adapter.get_sync_session() as _sess:
        _stmt = _mysql_insert(DevicePredictionCursor).values(_cursor_records)
        _stmt = _stmt.on_duplicate_key_update(
            last_predicted_time=_stmt.inserted.last_predicted_time,
            last_predicted_at=_stmt.inserted.last_predicted_at,
            model_version_id=_stmt.inserted.model_version_id,
            updated_at=_stmt.inserted.updated_at,
        )
        _sess.execute(_stmt)
    _cursor_adapter.dispose()
    logger.info("pv_prediction_task: 已推进 %d 台设备游标到 cutoff=%s", len(_cursor_records), cutoff.isoformat())
    # @AI_GENERATED: end

    _save_prediction_last_run({
        "status": "success",
        "reason": "predicted",
        "message": f"已写出预测结果 {batch_id}（{len(predictions)} 条），处理 {len(device_new_rows)} 台设备",
        "batch_id": batch_id,
        "review_id": review_id,
        "prediction_count": len(predictions),
        "device_count": len(device_new_rows),
        "skipped_caught_up": skipped_caught_up,
        "cutoff": cutoff.isoformat(),
        "model_ref": resolved_ref,
        "modeling_path": modeling_path,
        "split_audit": _json_safe(split_audit) if split_audit else None,
        "updated_at": _utc_now_iso(),
    })
    logger.info(
        "pv_prediction_task: 完成 batch=%s review=%s inputs=%d predictions=%d "
        "devices=%d skipped=%d model_ref=%s cutoff=%s",
        batch_id, review_id, len(all_rows), len(predictions),
        len(device_new_rows), skipped_caught_up, resolved_ref, cutoff.isoformat(),
    )
