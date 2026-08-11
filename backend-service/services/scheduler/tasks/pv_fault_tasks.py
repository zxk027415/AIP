# -*- coding: utf-8 -*-
"""
services/scheduler/tasks/pv_fault_tasks.py — 光伏故障诊断调度任务。

模拟喂数据由 pv_mock_data_feed 写入 training_samples；本模块负责每日预测，
复用 quickval 预测工作流与累计训练完成的模型，不会伪造预测或训练标签。
"""

# @AI_GENERATED: 正常 pv_fault 光伏调度：未标注观测拉取、真实预测和审核批次持久化
from __future__ import annotations

import json
import logging
import math
import os
import pickle
import re
import tempfile
import uuid
from datetime import datetime, timezone
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


def _create_prediction_review_session(
    batch_id: str,
    *,
    source_dataset_path: str,
    model_ref: str,
    predictions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Turn a persisted scheduler prediction batch into an idempotent review queue."""
    prediction_units = []
    for row in predictions:
        device_id = row.get("device_id")
        time_window = row.get("time_window")
        if device_id is None or time_window is None:
            continue
        site_id = row.get("site_id")
        branch_id = row.get("branch_id")
        prediction_units.append(
            {
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
        )
    if not prediction_units:
        raise ValueError(f"预测批次 {batch_id} 没有可审核的诊断单元")

    registry = LabelRegistryService(slot=_SLOT)
    return ReviewSessionService(slot=_SLOT, registry_service=registry).create_session(
        loop_id=f"scheduler-{batch_id}",
        prediction_batch_id=batch_id,
        prediction_units=prediction_units,
        llm_suggestions={},
        prediction_context={
            "source_csv_path": source_dataset_path,
            "load_config": {},
            "window_config": {},
            "label_map": registry.get_current().get("label_map", {}),
            "model_ref": model_ref,
            "source": "scheduled_prediction",
        },
    )


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


def reset_prediction_cursor(reason: str = "manual_reset") -> Dict[str, Any]:
    """手动清空预测游标，并绑定当前数据源指纹。"""
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
    _save_prediction_last_run(
        {
            "status": "cursor_reset",
            "reason": reason,
            "message": "预测进度已重置，下次预测将从当前数据源重新计算。",
            "source_fingerprint": payload.get("source_fingerprint"),
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


#: 逐点标签建模路径。这些路径下预测必须按模型持久化策略切样本。
_POINT_LABEL_MODELING_PATHS = frozenset({"point_label_by_day", "point_label_by_day_night"})


def _production_modeling_path() -> str:
    """读取当前生产建模路径（legacy_day / point_label_by_day / point_label_by_day_night）。"""
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
) -> Tuple[Path, str]:
    """Persist raw, unlabeled observations as the review/backfill source CSV.

    Args:
        rows: 观测行列表或已切好样本的 DataFrame。
        extra_columns: 需要一并写出的附加列（逐点标签路径下是 ``time_window`` /
            ``period_role`` 及 ``period_is_*`` / ``night_*`` 派生列）。带 ``#`` 的
            ``time_window`` 会被 ``time_window_split`` 识别为显式样本边界并原样保留，
            从而让预测样本粒度与训练完全一致。
    """
    input_dir = (
        _BACKEND_SERVICE_DIR
        / "data"
        / "iterative_labeling"
        / "prediction_inputs"
        / _SLOT
    )
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

        predictions.append(
            _json_safe(
                {
                    "site_id": raw["site_id"],
                    "device_id": raw["device_id"],
                    "branch_id": raw["branch_id"],
                    "time_window": raw["time_window"],
                    "predicted_label": predicted_label,
                    "confidence": normalized_confidence,
                }
            )
        )

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


def _write_prediction_batch(
    batch_id: str,
    *,
    source_dataset_path: str,
    model_ref: str,
    model_path: str,
    predictions: List[Dict[str, Any]],
    unit_features: Optional[Dict[str, Any]] = None,
    feature_list: Optional[List[str]] = None,
) -> None:
    """Persist the same batch shape consumed by iterative-labeling review sessions."""
    batch_dir = (
        _BACKEND_SERVICE_DIR
        / "data"
        / "iterative_labeling"
        / "prediction_batches"
        / _SLOT
    )
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_path = batch_dir / f"{batch_id}.json"
    payload = {
        "dataset_version": source_dataset_path,
        "model_ref": model_ref,
        "model_path": model_path,
        "feature_list": list(feature_list or []),
        "unit_features": unit_features or {},
        "predictions": predictions,
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


def make_pv_prediction_task(
    pv_repo: PVFaultRepository,
    model_ref: Optional[str] = None,
) -> Callable[[], None]:
    """Create the daily PV prediction task using the latest completed cumulative model.

    An explicit ``model_ref`` is honoured for controlled operations.  When omitted,
    the task safely waits for a completed pv_fault-slot cumulative retrain request.
    """

    def pv_prediction_task() -> None:
        try:
            _run_pv_prediction_cycle(pv_repo, model_ref)
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

    try:
        model_id, model_file, model_path, execution_model_path = _resolve_model_artifact(resolved_ref)
    except FileNotFoundError:
        logger.info("MODEL_PENDING: pv_prediction_task model artifact not found model_ref=%s", resolved_ref)
        _save_prediction_last_run({"status": "skipped", "reason": "model_pending",
                                   "message": f"模型工件不存在：{resolved_ref}", "updated_at": _utc_now_iso()})
        return

    feature_list, sample_strategy = _load_model_contract(model_file)
    modeling_path = _production_modeling_path()
    use_point_label_path = modeling_path in _POINT_LABEL_MODELING_PATHS
    if use_point_label_path and not sample_strategy:
        message = (
            f"生产建模路径为 {modeling_path}，但模型 {resolved_ref} 的 pkl 里没有 "
            "sample_strategy，无法复现训练切分口径，预测已跳过。"
        )
        logger.error("pv_prediction_task: %s", message)
        _save_prediction_last_run({"status": "skipped", "reason": "sample_strategy_missing",
                                   "message": message, "model_ref": resolved_ref,
                                   "modeling_path": modeling_path, "updated_at": _utc_now_iso()})
        return

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
        if use_point_label_path
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
    if use_point_label_path:
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
        elif function_id == "time_window_split" and use_point_label_path:
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
    )
    review_session = _create_prediction_review_session(
        batch_id,
        source_dataset_path=source_dataset_path,
        model_ref=resolved_ref,
        predictions=predictions,
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
# @AI_GENERATED: end
