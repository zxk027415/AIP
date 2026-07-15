# -*- coding: utf-8 -*-
"""
services/scheduler/tasks/pv_fault_tasks.py — 光伏故障诊断调度任务。

每日拉取只保存原始观测与可能的人工标签；每日预测仅消费未标注观测，并复用
quickval 预测工作流与累计训练完成的模型，不会伪造预测或训练标签。
"""

# @AI_GENERATED: 正常 default 光伏调度：未标注观测拉取、真实预测和审核批次持久化
from __future__ import annotations

import json
import logging
import math
import os
import pickle
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from services.db.datasources.base import DataSourceError, StationDataSource
from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.cumulative_training import CumulativeTrainingService

logger = logging.getLogger(__name__)

_MAX_RECORDS_PER_PULL = 10_000
_SLOT = "default"
_BACKEND_SERVICE_DIR = Path(__file__).resolve().parents[3]
_PROJECT_ROOT = _BACKEND_SERVICE_DIR.parent


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


def _latest_completed_model_ref() -> Optional[str]:
    """Read the newest completed cumulative-retrain model reference for default."""
    return CumulativeTrainingService(slot=_SLOT).get_latest_completed_model_ref()


_PREDICTION_CURSOR_PATH = (
    _BACKEND_SERVICE_DIR
    / "data"
    / "iterative_labeling"
    / "pv_scheduler"
    / _SLOT
    / "prediction_cursor.json"
)


def _load_prediction_cursor() -> Optional[datetime]:
    """Load the latest successful prediction watermark without storing an absolute path."""
    if not _PREDICTION_CURSOR_PATH.exists():
        return None
    try:
        payload = json.loads(_PREDICTION_CURSOR_PATH.read_text(encoding="utf-8"))
        timestamp = payload.get("last_predicted_time")
        return datetime.fromisoformat(timestamp) if timestamp else None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("PV prediction cursor unreadable; replaying unlabelled observations safely: %s", exc)
        return None


def _save_prediction_cursor(batch_id: str, last_predicted_time: Any) -> None:
    """Atomically advance the watermark only after records and the review batch are durable."""
    timestamp = pd.Timestamp(last_predicted_time).to_pydatetime().replace(tzinfo=None).isoformat()
    _PREDICTION_CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "batch_id": batch_id,
        "last_predicted_time": timestamp,
        "updated_at": datetime.utcnow().isoformat(),
    }
    temp_path = _PREDICTION_CURSOR_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(_PREDICTION_CURSOR_PATH)


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


def _load_feature_list(model_file: Path) -> List[str]:
    """Load the feature contract saved beside the trained classifier."""
    with model_file.open("rb") as handle:
        payload = pickle.load(handle)
    feature_list = payload.get("feature_list") if isinstance(payload, dict) else None
    if not isinstance(feature_list, list) or not feature_list:
        raise ValueError("模型 pkl 缺少非空 feature_list，拒绝执行不一致的预测")
    return [str(feature) for feature in feature_list]


def _workflow_config_set(config: Any, key: str, value: Any) -> None:
    """Update a workflow node config regardless of its Pydantic/dict representation."""
    if isinstance(config, dict):
        config[key] = value
    else:
        setattr(config, key, value)


def _write_prediction_input(rows: List[Dict[str, object]], batch_id: str) -> Tuple[Path, str]:
    """Persist raw, unlabeled observations as the review/backfill source CSV."""
    input_dir = (
        _BACKEND_SERVICE_DIR
        / "data"
        / "iterative_labeling"
        / "prediction_inputs"
        / _SLOT
    )
    input_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir / f"{batch_id}.csv"
    columns = ["time", "site_id", "device_id", "branch_id", "value", "i_cal"]
    frame = pd.DataFrame(rows)
    frame = frame.reindex(columns=columns)
    if frame.empty:
        raise ValueError("未标注样本为空，不能创建预测输入")
    frame.to_csv(input_path, index=False, encoding="utf-8")
    return input_path, _to_project_relative(input_path)


def _normalize_predictions(raw_predictions: Any) -> List[Dict[str, Any]]:
    """Validate real workflow results before they become auditable predictions."""
    if not isinstance(raw_predictions, list) or not raw_predictions:
        raise RuntimeError("预测工作流未返回非空 fault_predictions")

    predictions: List[Dict[str, Any]] = []
    required_fields = ("site_id", "device_id", "branch_id", "time_window")
    for index, raw in enumerate(raw_predictions):
        if not isinstance(raw, dict):
            raise RuntimeError(f"fault_predictions[{index}] 不是对象")
        missing = [field for field in required_fields if _is_missing(raw.get(field))]
        raw_label = raw.get("predicted_label", raw.get("predictions", raw.get("predict_label")))
        if _is_missing(raw_label):
            missing.append("predicted_label")
        if missing:
            raise RuntimeError(f"fault_predictions[{index}] 缺少必要字段: {', '.join(missing)}")
        try:
            predicted_label = int(raw_label)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"fault_predictions[{index}] 的 predicted_label 无法转换为整数") from exc

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
    return predictions


def _write_prediction_batch(
    batch_id: str,
    *,
    source_dataset_path: str,
    model_ref: str,
    model_path: str,
    predictions: List[Dict[str, Any]],
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
        "predictions": predictions,
        "created_at": datetime.utcnow().isoformat(),
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


def make_pv_data_pull_task(
    station_source: StationDataSource,
    pv_repo: PVFaultRepository,
) -> Callable[[], None]:
    """Create the daily PV raw-observation pull task with high-watermark handling."""
    failure_count: int = 0

    def pv_data_pull_task() -> None:
        nonlocal failure_count

        hw = pv_repo.get_high_watermark()
        since_ts = hw if hw is not None else datetime(1970, 1, 1)
        try:
            records = station_source.pull_latest(
                station_id="pv",
                since_timestamp=since_ts,
            )
        except DataSourceError as exc:
            failure_count += 1
            logger.warning(
                "pv_data_pull_task: 数据源不可达，跳过本次拉取（累计失败 %d 次）: %s",
                failure_count,
                exc,
            )
            return

        if not records:
            logger.info("pv_data_pull_task: 无新记录，跳过本次写入。since=%s", since_ts)
            return

        batch = records[:_MAX_RECORDS_PER_PULL]
        logger.info(
            "pv_data_pull_task: 拉取 %d 条（数据源共 %d 条），写入数据库。",
            len(batch),
            len(records),
        )
        rows = [
            {
                "time": record.timestamp.replace(tzinfo=None)
                if record.timestamp.tzinfo is not None
                else record.timestamp,
                "site_id": record.station_id,
                "device_id": record.feature_name,
                "branch_id": _SLOT,
                "value": record.value,
                "i_cal": 0.0,
                "label": None,
            }
            for record in batch
        ]

        fd, tmp_path = tempfile.mkstemp(suffix=".parquet")
        os.close(fd)
        try:
            pd.DataFrame(rows).to_parquet(tmp_path, index=False)
            result = pv_repo.ingest_parquet(tmp_path)
            logger.info(
                "pv_data_pull_task: 写入完成 inserted=%d skipped=%d",
                result["inserted"],
                result["skipped"],
            )
        except Exception as exc:
            failure_count += 1
            logger.error(
                "pv_data_pull_task: 写入数据库失败（累计失败 %d 次）: %s",
                failure_count,
                exc,
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    return pv_data_pull_task


def make_pv_prediction_task(
    pv_repo: PVFaultRepository,
    model_ref: Optional[str] = None,
) -> Callable[[], None]:
    """Create the daily PV prediction task using the latest completed cumulative model.

    An explicit ``model_ref`` is honoured for controlled operations.  When omitted,
    the task safely waits for a completed default-slot cumulative retrain request.
    """

    def pv_prediction_task() -> None:
        resolved_ref = str(model_ref or "").strip() or _latest_completed_model_ref()
        if not resolved_ref:
            logger.info(
                "MODEL_PENDING: pv_prediction_task is waiting for a completed default cumulative retrain model"
            )
            return

        try:
            model_id, model_file, model_path, execution_model_path = _resolve_model_artifact(resolved_ref)
        except FileNotFoundError:
            logger.info(
                "MODEL_PENDING: pv_prediction_task is waiting for model artifact model_ref=%s",
                resolved_ref,
            )
            return
        feature_list = _load_feature_list(model_file)
        prediction_cursor = _load_prediction_cursor()
        unlabeled_rows = pv_repo.query_unlabeled_training_samples(after_time=prediction_cursor)
        if not unlabeled_rows:
            logger.info("pv_prediction_task: 无预测游标之后的未标注观测，跳过真实推理。")
            return

        batch_id = f"pred-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        _input_path, source_dataset_path = _write_prediction_input(unlabeled_rows, batch_id)

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
        if not all(required_nodes.values()):
            missing = [node for node, found in required_nodes.items() if not found]
            raise RuntimeError(f"预测工作流缺少必要节点: {', '.join(missing)}")

        execution_result = _execute_pipeline_sync(workflow)
        if not execution_result.get("success", False):
            raise RuntimeError(f"预测工作流执行失败: {execution_result.get('error', '未知错误')}")
        predictions = _normalize_predictions(execution_result.get("fault_predictions"))

        model_version = pv_repo.get_model_version(model_id)
        for prediction in predictions:
            pv_repo.insert_prediction_record(
                {
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
                }
            )

        _write_prediction_batch(
            batch_id,
            source_dataset_path=source_dataset_path,
            model_ref=resolved_ref,
            model_path=model_path,
            predictions=predictions,
        )
        _save_prediction_cursor(
            batch_id,
            max(row["time"] for row in unlabeled_rows if row.get("time") is not None),
        )
        logger.info(
            "pv_prediction_task: 完成真实推理 batch=%s inputs=%d predictions=%d model_ref=%s",
            batch_id,
            len(unlabeled_rows),
            len(predictions),
            resolved_ref,
        )

    return pv_prediction_task
# @AI_GENERATED: end
