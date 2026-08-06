"""同一训练快照上，对比多种 solar_mode 切分的离线评估精度。

不切换生产模型、不改工作流模板落盘；仅内存改节点参数后跑训练评估工作流。
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[2]
_TRAIN_WORKFLOW_ID = "workflow-pv-fault-diag-quickval-cv-v1"

DEFAULT_COMPARE_MODES = [
    "",
    "daylight",
    "night",
    "day_and_night",
    "solar_period",
    "multiscale",
]

MODE_LABELS = {
    "": "关闭（整天按天切）",
    "daylight": "仅白天",
    "night": "仅夜间",
    "day_and_night": "白天+夜间",
    "solar_period": "日照峰/过渡段",
    "multiscale": "多尺度",
}

_COMPARE_LOCKS: Dict[str, Any] = {}


def _compare_dir(slot: str) -> Path:
    return _BACKEND / "data" / "iterative_labeling" / "split_mode_compare" / slot


def _compare_store_path(slot: str) -> Path:
    return _compare_dir(slot) / "latest.json"


def _status_path(slot: str) -> Path:
    return _compare_dir(slot) / "status.json"


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", text=True)
    try:
        import os

        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp).replace(path)
    except Exception:
        try:
            Path(tmp).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _write_status(slot: str, payload: Dict[str, Any]) -> None:
    _atomic_write_json(_status_path(slot), payload)


def _slot_lock_held(slot: str) -> bool:
    lock = _COMPARE_LOCKS.get(slot)
    return bool(lock is not None and lock.locked())


def load_compare_status(slot: str) -> Dict[str, Any]:
    """读取运行状态；若无 status 文件则根据 latest 推断。

    进程重启后可能遗留 status=running：若本进程未持有该 slot 锁，则标记为 interrupted。
    """
    path = _status_path(slot)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("status") == "running" and not _slot_lock_held(slot):
                payload = {
                    **payload,
                    "status": "interrupted",
                    "message": "对比进程已中断（通常因后端重启），可重新点击开始对比",
                    "updated_at": datetime.utcnow().isoformat(),
                }
                try:
                    _write_status(slot, payload)
                except Exception:
                    pass
            return payload
        except Exception:
            pass
    latest = load_latest_compare(slot)
    if latest:
        return {
            "status": "completed",
            "slot": slot,
            "updated_at": latest.get("created_at"),
            "message": "已完成（历史结果）",
            "partial_results": latest.get("results") or [],
            "job_id": latest.get("job_id"),
        }
    return {
        "status": "idle",
        "slot": slot,
        "message": "尚无对比任务",
        "partial_results": [],
    }


def _config_get(config: Any, key: str) -> Any:
    if isinstance(config, dict):
        return config.get(key)
    return getattr(config, key, None)


def _config_set(config: Any, key: str, value: Any) -> None:
    if isinstance(config, dict):
        config[key] = value
    else:
        setattr(config, key, value)


def _patch_workflow_for_mode(
    workflow: Any,
    *,
    dataset_path: str,
    solar_mode: Optional[str],
    n_repeats: int,
    test_ratio: float,
    random_state: int,
) -> None:
    mode = None if solar_mode is None else str(solar_mode).strip()
    if mode == "":
        mode = None

    for node in workflow.nodes:
        config = node.data.config
        fid = _config_get(config, "functionId")
        if fid == "load_csv":
            _config_set(config, "file_path", dataset_path)
        elif fid == "time_window_split":
            if mode is None:
                # 关闭日照切分
                if isinstance(config, dict):
                    config.pop("solar_mode", None)
                else:
                    try:
                        setattr(config, "solar_mode", None)
                    except Exception:
                        pass
            else:
                _config_set(config, "solar_mode", mode)
                _config_set(config, "power_col", "value")
                _config_set(config, "irr_threshold", 0.05)
                _config_set(config, "attach_night_features", True)
        elif fid == "stratified_cv_eval":
            _config_set(config, "n_repeats", int(n_repeats))
            _config_set(config, "test_ratio", float(test_ratio))
            _config_set(config, "random_state", int(random_state))
            # 对比不落生产模型，避免污染 models 目录
            _config_set(config, "save_final_model", False)


def _extract_metrics(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    metrics = execution_result.get("metrics")
    if isinstance(metrics, dict) and metrics:
        return metrics
    node_results = execution_result.get("nodeResults") or {}
    for node in node_results.values():
        if not isinstance(node, dict):
            continue
        summary = node.get("outputSummary")
        if isinstance(summary, dict) and (
            "macro_f1_mean" in summary or "accuracy_mean" in summary
        ):
            return summary
    return {}


def run_one_mode(
    *,
    dataset_path: str,
    solar_mode: Optional[str],
    n_repeats: int = 3,
    test_ratio: float = 0.2,
    random_state: int = 90,
) -> Dict[str, Any]:
    """对单一切分模式跑一遍训练评估工作流，返回指标摘要。"""
    import copy
    import sys

    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from api.workflows_enhanced import _execute_pipeline_sync, load_workflow_from_file

    started = time.time()
    mode_key = "" if not solar_mode else str(solar_mode).strip()
    label = MODE_LABELS.get(mode_key, mode_key or "关闭（整天按天切）")

    try:
        workflow = load_workflow_from_file(_TRAIN_WORKFLOW_ID)
        if workflow is None:
            raise RuntimeError(f"训练工作流不存在: {_TRAIN_WORKFLOW_ID}")
        # 深拷贝，避免污染模板缓存
        try:
            workflow = copy.deepcopy(workflow)
        except Exception:
            pass

        _patch_workflow_for_mode(
            workflow,
            dataset_path=dataset_path,
            solar_mode=mode_key,
            n_repeats=n_repeats,
            test_ratio=test_ratio,
            random_state=random_state,
        )
        execution_result = _execute_pipeline_sync(workflow)
        if not execution_result.get("success", False):
            raise RuntimeError(execution_result.get("error") or "工作流执行失败")

        metrics = _extract_metrics(execution_result)
        if not metrics:
            raise RuntimeError("未从评估节点拿到指标")

        return {
            "solar_mode": mode_key,
            "label": label,
            "status": "ok",
            "elapsed_sec": round(time.time() - started, 1),
            "n_samples": metrics.get("n_samples"),
            "n_classes": metrics.get("n_classes"),
            "macro_f1_mean": metrics.get("macro_f1_mean"),
            "macro_f1_std": metrics.get("macro_f1_std"),
            "accuracy_mean": metrics.get("accuracy_mean"),
            "accuracy_std": metrics.get("accuracy_std"),
            "macro_precision_mean": metrics.get("macro_precision_mean"),
            "macro_recall_mean": metrics.get("macro_recall_mean"),
            "warnings": metrics.get("warnings") or [],
            "error": None,
        }
    except Exception as exc:
        logger.exception("split mode compare failed for %s", mode_key or "(daily)")
        return {
            "solar_mode": mode_key,
            "label": label,
            "status": "failed",
            "elapsed_sec": round(time.time() - started, 1),
            "macro_f1_mean": None,
            "accuracy_mean": None,
            "error": str(exc),
        }


def compare_split_modes(
    *,
    slot: str,
    dataset_path: str,
    modes: Optional[List[Optional[str]]] = None,
    n_repeats: int = 3,
    test_ratio: float = 0.2,
    random_state: int = 90,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    """串行对比多种切分模式；过程写入 status.json，结束写入 latest.json。"""
    import uuid

    selected = list(modes) if modes is not None else list(DEFAULT_COMPARE_MODES)
    if not selected:
        selected = list(DEFAULT_COMPARE_MODES)

    normalized: List[str] = []
    for m in selected:
        if m is None:
            normalized.append("")
        else:
            normalized.append(str(m).strip())

    job = job_id or f"cmp-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    started = time.time()
    started_at = datetime.utcnow().isoformat()
    rows: List[Dict[str, Any]] = []
    total = len(normalized)

    _write_status(
        slot,
        {
            "status": "running",
            "job_id": job,
            "slot": slot,
            "dataset_path": dataset_path,
            "n_repeats": n_repeats,
            "modes": normalized,
            "total": total,
            "completed": 0,
            "current_mode": normalized[0] if normalized else None,
            "current_label": MODE_LABELS.get(normalized[0], normalized[0]) if normalized else None,
            "partial_results": [],
            "started_at": started_at,
            "updated_at": started_at,
            "message": f"开始对比，共 {total} 种模式",
        },
    )

    try:
        for idx, mode in enumerate(normalized):
            _write_status(
                slot,
                {
                    "status": "running",
                    "job_id": job,
                    "slot": slot,
                    "dataset_path": dataset_path,
                    "n_repeats": n_repeats,
                    "modes": normalized,
                    "total": total,
                    "completed": idx,
                    "current_mode": mode,
                    "current_label": MODE_LABELS.get(mode, mode or "关闭（整天按天切）"),
                    "partial_results": rows,
                    "started_at": started_at,
                    "updated_at": datetime.utcnow().isoformat(),
                    "message": f"正在评估 {MODE_LABELS.get(mode, mode or '关闭')}（{idx + 1}/{total}）",
                },
            )
            rows.append(
                run_one_mode(
                    dataset_path=dataset_path,
                    solar_mode=mode,
                    n_repeats=n_repeats,
                    test_ratio=test_ratio,
                    random_state=random_state,
                )
            )

        ok_rows = [r for r in rows if r.get("status") == "ok" and r.get("macro_f1_mean") is not None]
        best = None
        if ok_rows:
            best = max(ok_rows, key=lambda r: float(r.get("macro_f1_mean") or -1))

        payload = {
            "job_id": job,
            "slot": slot,
            "dataset_path": dataset_path,
            "n_repeats": n_repeats,
            "test_ratio": test_ratio,
            "random_state": random_state,
            "created_at": datetime.utcnow().isoformat(),
            "elapsed_sec": round(time.time() - started, 1),
            "results": rows,
            "best_solar_mode": (best or {}).get("solar_mode"),
            "best_label": (best or {}).get("label"),
            "best_macro_f1_mean": (best or {}).get("macro_f1_mean"),
            "note": (
                "对比使用同一快照、同一评估口径（重复分层留出）；"
                "默认减少重复次数以控制耗时；不会切换生产模型、不会改模板落盘。"
            ),
        }
        _atomic_write_json(_compare_store_path(slot), payload)
        _write_status(
            slot,
            {
                "status": "completed",
                "job_id": job,
                "slot": slot,
                "dataset_path": dataset_path,
                "n_repeats": n_repeats,
                "modes": normalized,
                "total": total,
                "completed": total,
                "current_mode": None,
                "partial_results": rows,
                "updated_at": datetime.utcnow().isoformat(),
                "message": "对比完成",
                "best_solar_mode": payload.get("best_solar_mode"),
                "best_label": payload.get("best_label"),
                "best_macro_f1_mean": payload.get("best_macro_f1_mean"),
            },
        )
        return payload
    except Exception as exc:
        logger.exception("compare_split_modes failed job=%s", job)
        _write_status(
            slot,
            {
                "status": "failed",
                "job_id": job,
                "slot": slot,
                "dataset_path": dataset_path,
                "modes": normalized,
                "total": total,
                "completed": len(rows),
                "partial_results": rows,
                "updated_at": datetime.utcnow().isoformat(),
                "message": f"对比失败: {exc}",
                "error": str(exc),
            },
        )
        raise


def start_compare_job(
    *,
    slot: str,
    dataset_path: str,
    modes: Optional[List[Optional[str]]] = None,
    n_repeats: int = 3,
    test_ratio: float = 0.2,
    random_state: int = 90,
) -> Dict[str, Any]:
    """后台启动对比任务；若同 slot 已在跑则返回当前状态。"""
    import threading
    import uuid

    existing = load_compare_status(slot)
    if existing.get("status") == "running" and _slot_lock_held(slot):
        return {
            "accepted": False,
            "reason": "already_running",
            **existing,
        }

    lock = _COMPARE_LOCKS.setdefault(slot, threading.Lock())
    if not lock.acquire(blocking=False):
        return {
            "accepted": False,
            "reason": "already_running",
            **load_compare_status(slot),
        }

    job_id = f"cmp-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    def _runner() -> None:
        try:
            compare_split_modes(
                slot=slot,
                dataset_path=dataset_path,
                modes=modes,
                n_repeats=n_repeats,
                test_ratio=test_ratio,
                random_state=random_state,
                job_id=job_id,
            )
        except Exception:
            pass
        finally:
            try:
                lock.release()
            except RuntimeError:
                pass

    # 先落 running，避免前端轮询到 idle
    selected = list(modes) if modes is not None else list(DEFAULT_COMPARE_MODES)
    normalized = [("" if m is None else str(m).strip()) for m in selected] or list(DEFAULT_COMPARE_MODES)
    _write_status(
        slot,
        {
            "status": "running",
            "job_id": job_id,
            "slot": slot,
            "dataset_path": dataset_path,
            "n_repeats": n_repeats,
            "modes": normalized,
            "total": len(normalized),
            "completed": 0,
            "current_mode": normalized[0] if normalized else None,
            "partial_results": [],
            "started_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "message": "任务已受理，正在排队启动",
        },
    )

    thread = threading.Thread(target=_runner, name=f"split-compare-{slot}", daemon=True)
    thread.start()
    return {
        "accepted": True,
        "job_id": job_id,
        "status": "running",
        "slot": slot,
        "message": "切分对比已在后台启动，可离开页面稍后回来查看",
        "total": len(normalized),
        "completed": 0,
    }


def load_latest_compare(slot: str) -> Optional[Dict[str, Any]]:
    path = _compare_store_path(slot)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
