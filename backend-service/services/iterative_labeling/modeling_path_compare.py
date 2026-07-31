# @AI_GENERATED
"""新旧建模路径 A/B 精度对比（K7）。

同一批测量数据分别走老路径（merged parquet + solar_mode）与新路径（SnapshotBuilder + sample_id），
复用 stratified_cv_eval 工作流与 split_mode_compare 的指标提取/落盘模式。
"""

from __future__ import annotations

import json
import logging
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.iterative_labeling.split_mode_compare import (
    _BACKEND,
    _TRAIN_WORKFLOW_ID,
    _atomic_write_json,
    _config_get,
    _config_set,
    _extract_metrics,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = _BACKEND.parent

DEFAULT_COMPARE_PATHS = [
    "legacy_day",
    "point_label_by_day",
    "point_label_by_day_night",
]

PATH_LABELS = {
    "legacy_day": "老路径（label 列 + 按值 day/night 切分）",
    "point_label_by_day": "新路径 by_day（point_labels + 时钟窗）",
    "point_label_by_day_night": "新路径 by_day_night（默认新口径）",
}

DEFAULT_LEGACY_DATASET_CANDIDATES = (
    "backend-service/datasets/pv_cumulative_labeled_merged.parquet",
    "fault-diag-algo-release-3.1/相关数据/pv_cumulative_labeled_merged.parquet",
    "pv_cumulative_labeled_merged.parquet",
)

_COMPARE_LOCKS: Dict[str, Any] = {}


def _compare_dir(slot: str) -> Path:
    return _BACKEND / "data" / "iterative_labeling" / "modeling_path_compare" / slot


def _compare_store_path(slot: str) -> Path:
    return _compare_dir(slot) / "latest.json"


def _status_path(slot: str) -> Path:
    return _compare_dir(slot) / "status.json"


def _slot_lock_held(slot: str) -> bool:
    lock = _COMPARE_LOCKS.get(slot)
    return bool(lock is not None and lock.locked())


def resolve_legacy_dataset_path(explicit: Optional[str] = None) -> str:
    """返回相对项目根的老路径 merged parquet。"""
    if explicit and str(explicit).strip():
        rel = str(explicit).strip().replace("\\", "/")
        candidate = (_PROJECT_ROOT / rel).resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"老路径数据集不存在: {rel}")
        return rel
    for rel in DEFAULT_LEGACY_DATASET_CANDIDATES:
        if (_PROJECT_ROOT / rel).exists():
            return rel
    raise FileNotFoundError("未找到 pv_cumulative_labeled_merged.parquet")


_SCOPE_COLS = ["site_id", "device_id", "branch_id", "_date"]


def compute_common_scope(legacy_rel_path: str, site_id: Optional[str] = None) -> Dict[str, Any]:
    """计算两条路径的**共同设备-天范围**，使 A/B 对比数据源可比（需求 23.2）。

    背景（review 发现的核心缺陷）：老路径直接读 merged parquet（实测 1,056,806 行 /
    4,457 设备-天），新路径读 `training_samples` ⨝ `point_labels`（实测 317,832 行 /
    1,130 设备-天）——两边数据量差 3.3 倍，F1 差异无法归因于路径优劣，对比不成立。

    本函数取两边都存在的 `(site_id, device_id, branch_id, 自然日)` 交集，
    两条路径都只用这个交集，使 `n_samples` 可比。

    Returns:
        {"scope": set[tuple], "legacy_device_days", "point_label_device_days",
         "common_device_days", "coverage_vs_legacy", "coverage_vs_point_label"}
    """
    import pandas as pd

    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from services.db.repositories.point_label import PointLabelRepository
    from services.db.repositories.pv_fault import PVFaultRepository
    from services.iterative_labeling.snapshot_builder import SnapshotBuilder

    legacy_abs = _PROJECT_ROOT / legacy_rel_path
    legacy_df = pd.read_parquet(
        legacy_abs, columns=["time", "site_id", "device_id", "branch_id", "label"]
    )
    legacy_df = legacy_df[legacy_df["label"].notna()]
    if site_id:
        legacy_df = legacy_df[legacy_df["site_id"].astype(str) == str(site_id)]
    legacy_df["_date"] = pd.to_datetime(legacy_df["time"]).dt.normalize()
    legacy_scope = set(
        map(tuple, legacy_df[_SCOPE_COLS].astype(str).drop_duplicates().values.tolist())
    )

    adapter = DBAdapter(DBConfig())
    builder = SnapshotBuilder(PointLabelRepository(adapter), PVFaultRepository(adapter))
    measurements = builder._load_measurements(site_id)
    if measurements.empty:
        raise ValueError("training_samples 为空，无法计算共同范围")
    measurements["_date"] = pd.to_datetime(measurements["time"]).dt.normalize()
    pl_scope = set(
        map(tuple, measurements[_SCOPE_COLS].astype(str).drop_duplicates().values.tolist())
    )

    common = legacy_scope & pl_scope
    return {
        "scope": common,
        "legacy_device_days": len(legacy_scope),
        "point_label_device_days": len(pl_scope),
        "common_device_days": len(common),
        "coverage_vs_legacy": round(len(common) / len(legacy_scope), 4) if legacy_scope else None,
        "coverage_vs_point_label": round(len(common) / len(pl_scope), 4) if pl_scope else None,
    }


def _apply_scope(df: "pd.DataFrame", scope: Optional[set]) -> "pd.DataFrame":
    """把 DataFrame 过滤到给定的 (site,device,branch,date) 范围内。"""
    import pandas as pd

    if not scope:
        return df
    out = df.copy()
    out["_date"] = pd.to_datetime(out["time"]).dt.normalize()
    keys = list(map(tuple, out[_SCOPE_COLS].astype(str).values.tolist()))
    mask = [k in scope for k in keys]
    out = out[mask].drop(columns=["_date"])
    return out


def build_legacy_dataset(
    *,
    legacy_rel_path: str,
    slot: str,
    job_id: str,
    scope: Optional[set] = None,
    site_id: Optional[str] = None,
) -> str:
    """构建老路径数据集：按共同范围裁剪后落一份临时 parquet。

    scope 为空时退化为直接使用原始 parquet（保留旧行为，便于对照）。
    """
    import pandas as pd

    if not scope:
        return legacy_rel_path

    legacy_abs = _PROJECT_ROOT / legacy_rel_path
    df = pd.read_parquet(legacy_abs)
    df = df[df["label"].notna()]
    if site_id:
        df = df[df["site_id"].astype(str) == str(site_id)]
    scoped = _apply_scope(df, scope)
    if scoped.empty:
        raise ValueError("老路径数据集在共同范围内为空")
    if scoped["label"].nunique() < 2:
        raise ValueError("老路径数据集在共同范围内至少需要两个标签类别")

    out_dir = _compare_dir(slot) / "datasets"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job_id}-legacy_scoped.parquet"
    scoped.to_parquet(out_path, index=False)
    return out_path.relative_to(_PROJECT_ROOT).as_posix()


def build_point_label_dataset(
    *,
    split_mode: str,
    slot: str,
    job_id: str,
    site_id: Optional[str] = None,
    scope: Optional[set] = None,
) -> str:
    """从 DB 构建 point_label 快照 parquet，返回相对项目根路径。"""
    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from services.db.repositories.point_label import PointLabelRepository
    from services.db.repositories.pv_fault import PVFaultRepository
    from services.iterative_labeling.daylight_window import DaylightWindowResolver
    from services.iterative_labeling.sample_builder import SampleStrategy
    from services.iterative_labeling.snapshot_builder import SnapshotBuilder

    adapter = DBAdapter(DBConfig())
    builder = SnapshotBuilder(PointLabelRepository(adapter), PVFaultRepository(adapter))
    measurements = builder._load_measurements(site_id)
    if measurements.empty:
        raise ValueError("training_samples 为空，无法构建新路径对比数据集")
    # 与老路径用同一批设备-天，使 n_samples 可比（需求 23.2）
    measurements = _apply_scope(measurements, scope)
    if measurements.empty:
        raise ValueError("新路径测量数据在共同范围内为空")

    daylight_table = DaylightWindowResolver().build_table(measurements)
    strategy = SampleStrategy(
        split_mode=str(split_mode),
        min_points=12,
        daylight_windows=daylight_table,
    )
    combined, meta = builder.build(strategy, measurements_df=measurements)
    if combined["label"].nunique() < 2:
        raise ValueError("新路径快照至少需要两个标签类别")

    out_dir = _compare_dir(slot) / "datasets"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job_id}-{split_mode}.parquet"
    builder.write_parquet(combined, meta, out_path)
    rel = out_path.relative_to(_PROJECT_ROOT).as_posix()
    return rel


def _dataset_for_path(
    path_key: str,
    *,
    slot: str,
    job_id: str,
    legacy_dataset_path: Optional[str],
    site_id: Optional[str],
    scope: Optional[set] = None,
) -> str:
    if path_key == "legacy_day":
        return build_legacy_dataset(
            legacy_rel_path=resolve_legacy_dataset_path(legacy_dataset_path),
            slot=slot, job_id=job_id, scope=scope, site_id=site_id,
        )
    if path_key == "point_label_by_day":
        return build_point_label_dataset(
            split_mode="by_day", slot=slot, job_id=job_id, site_id=site_id, scope=scope
        )
    if path_key == "point_label_by_day_night":
        return build_point_label_dataset(
            split_mode="by_day_night", slot=slot, job_id=job_id, site_id=site_id, scope=scope
        )
    raise ValueError(f"未知建模路径: {path_key}")


def _patch_workflow_for_path(
    workflow: Any,
    *,
    dataset_path: str,
    path_key: str,
    n_repeats: int,
    test_ratio: float,
    random_state: int,
) -> None:
    use_solar = path_key == "legacy_day"
    for node in workflow.nodes:
        config = node.data.config
        fid = _config_get(config, "functionId")
        if fid == "load_csv":
            _config_set(config, "file_path", dataset_path)
        elif fid == "time_window_split":
            if use_solar:
                _config_set(config, "solar_mode", "day_and_night")
                _config_set(config, "power_col", "value")
                _config_set(config, "irr_threshold", 0.05)
                _config_set(config, "attach_night_features", True)
            else:
                if isinstance(config, dict):
                    config.pop("solar_mode", None)
                else:
                    try:
                        setattr(config, "solar_mode", None)
                    except Exception:
                        pass
        elif fid == "stratified_cv_eval":
            _config_set(config, "n_repeats", int(n_repeats))
            _config_set(config, "test_ratio", float(test_ratio))
            _config_set(config, "random_state", int(random_state))
            _config_set(config, "save_final_model", False)
            if use_solar:
                if isinstance(config, dict):
                    config.pop("group_col", None)
                else:
                    try:
                        setattr(config, "group_col", None)
                    except Exception:
                        pass
            else:
                _config_set(config, "group_col", "group_key")


def run_one_path(
    *,
    path_key: str,
    dataset_path: str,
    n_repeats: int = 3,
    test_ratio: float = 0.2,
    random_state: int = 90,
) -> Dict[str, Any]:
    """对单条建模路径跑训练评估工作流。"""
    import copy
    import sys

    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from api.workflows_enhanced import _execute_pipeline_sync, load_workflow_from_file

    started = time.time()
    label = PATH_LABELS.get(path_key, path_key)

    try:
        workflow = load_workflow_from_file(_TRAIN_WORKFLOW_ID)
        if workflow is None:
            raise RuntimeError(f"训练工作流不存在: {_TRAIN_WORKFLOW_ID}")
        try:
            workflow = copy.deepcopy(workflow)
        except Exception:
            pass

        _patch_workflow_for_path(
            workflow,
            dataset_path=dataset_path,
            path_key=path_key,
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
            "path_key": path_key,
            "label": label,
            "dataset_path": dataset_path,
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
            "per_class_recall_mean": metrics.get("per_class_recall_mean") or {},
            "per_class_metrics": metrics.get("per_class_metrics") or {},
            "warnings": metrics.get("warnings") or [],
            "error": None,
        }
    except Exception as exc:
        logger.exception("modeling path compare failed for %s", path_key)
        return {
            "path_key": path_key,
            "label": label,
            "dataset_path": dataset_path,
            "status": "failed",
            "elapsed_sec": round(time.time() - started, 1),
            "macro_f1_mean": None,
            "accuracy_mean": None,
            "error": str(exc),
        }


def _compute_deltas(results: List[Dict[str, Any]], baseline_key: str = "legacy_day") -> Dict[str, Any]:
    baseline = next((r for r in results if r.get("path_key") == baseline_key and r.get("status") == "ok"), None)
    if not baseline:
        return {}
    base_f1 = float(baseline.get("macro_f1_mean") or 0)
    base_acc = float(baseline.get("accuracy_mean") or 0)
    deltas: Dict[str, Any] = {}
    for row in results:
        key = str(row.get("path_key") or "")
        if key == baseline_key or row.get("status") != "ok":
            continue
        f1 = row.get("macro_f1_mean")
        acc = row.get("accuracy_mean")
        deltas[key] = {
            "macro_f1_delta": round(float(f1) - base_f1, 4) if f1 is not None else None,
            "accuracy_delta": round(float(acc) - base_acc, 4) if acc is not None else None,
            "vs_baseline": baseline_key,
        }
    return deltas


def load_compare_status(slot: str) -> Dict[str, Any]:
    path = _status_path(slot)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("status") == "running" and not _slot_lock_held(slot):
                payload = {
                    **payload,
                    "status": "interrupted",
                    "message": "对比进程已中断（通常因后端重启），可重新启动",
                    "updated_at": datetime.utcnow().isoformat(),
                }
                try:
                    _atomic_write_json(_status_path(slot), payload)
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
        "message": "尚无路径对比任务",
        "partial_results": [],
    }


def load_latest_compare(slot: str) -> Optional[Dict[str, Any]]:
    path = _compare_store_path(slot)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def compare_modeling_paths(
    *,
    slot: str,
    paths: Optional[List[str]] = None,
    n_repeats: int = 3,
    test_ratio: float = 0.2,
    random_state: int = 90,
    job_id: Optional[str] = None,
    legacy_dataset_path: Optional[str] = None,
    site_id: Optional[str] = None,
    align_scope: bool = True,
) -> Dict[str, Any]:
    """串行对比多条建模路径。

    Args:
        align_scope: 默认 True——把所有路径裁剪到共同设备-天范围，使 n_samples
            可比（需求 23.2）。设为 False 会退回旧行为（老路径用全量 parquet、
            新路径用 training_samples），此时 F1 差异**不可**归因于路径优劣。
    """
    selected = list(paths) if paths else list(DEFAULT_COMPARE_PATHS)
    if not selected:
        selected = list(DEFAULT_COMPARE_PATHS)
    normalized = [str(p).strip() for p in selected if str(p).strip()]
    for key in normalized:
        if key not in PATH_LABELS:
            raise ValueError(f"不支持的建模路径: {key}")

    job = job_id or f"pathcmp-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    started = time.time()
    started_at = datetime.utcnow().isoformat()
    rows: List[Dict[str, Any]] = []
    total = len(normalized)
    legacy_resolved = resolve_legacy_dataset_path(legacy_dataset_path)

    # 计算共同设备-天范围，使各路径 n_samples 可比（需求 23.2）
    scope_info: Dict[str, Any] = {}
    scope: Optional[set] = None
    if align_scope:
        scope_info = compute_common_scope(legacy_resolved, site_id)
        scope = scope_info.pop("scope")
        if not scope:
            raise ValueError(
                "老路径与新路径没有共同的设备-天范围，无法做可比的 A/B 对比；"
                "请先确认 training_samples 是否已灌入与 parquet 对应的测量数据"
            )
        logger.info(
            "A/B 共同范围对齐：legacy %d 设备-天、point_label %d 设备-天、共同 %d 设备-天",
            scope_info["legacy_device_days"], scope_info["point_label_device_days"],
            scope_info["common_device_days"],
        )

    _atomic_write_json(
        _status_path(slot),
        {
            "status": "running",
            "job_id": job,
            "slot": slot,
            "paths": normalized,
            "legacy_dataset_path": legacy_resolved,
            "n_repeats": n_repeats,
            "total": total,
            "completed": 0,
            "current_path": normalized[0] if normalized else None,
            "partial_results": [],
            "started_at": started_at,
            "updated_at": started_at,
            "message": f"开始路径对比，共 {total} 条路径",
            "premise": (
                "新旧口径不同；对比建立在同一批测量数据分别完整跑两条/三条路径之上，"
                "不能拿历史老口径模型指标直接比。"
            ),
        },
    )

    try:
        for idx, path_key in enumerate(normalized):
            _atomic_write_json(
                _status_path(slot),
                {
                    "status": "running",
                    "job_id": job,
                    "slot": slot,
                    "paths": normalized,
                    "legacy_dataset_path": legacy_resolved,
                    "n_repeats": n_repeats,
                    "total": total,
                    "completed": idx,
                    "current_path": path_key,
                    "current_label": PATH_LABELS.get(path_key, path_key),
                    "partial_results": rows,
                    "started_at": started_at,
                    "updated_at": datetime.utcnow().isoformat(),
                    "message": f"正在评估 {PATH_LABELS.get(path_key, path_key)}（{idx + 1}/{total}）",
                },
            )
            dataset_path = _dataset_for_path(
                path_key,
                slot=slot,
                job_id=job,
                legacy_dataset_path=legacy_resolved,
                site_id=site_id,
                scope=scope,
            )
            rows.append(
                run_one_path(
                    path_key=path_key,
                    dataset_path=dataset_path,
                    n_repeats=n_repeats,
                    test_ratio=test_ratio,
                    random_state=random_state,
                )
            )

        ok_rows = [r for r in rows if r.get("status") == "ok" and r.get("macro_f1_mean") is not None]
        best = max(ok_rows, key=lambda r: float(r.get("macro_f1_mean") or -1)) if ok_rows else None
        deltas = _compute_deltas(rows)

        payload = {
            "job_id": job,
            "slot": slot,
            "paths": normalized,
            "legacy_dataset_path": legacy_resolved,
            "n_repeats": n_repeats,
            "test_ratio": test_ratio,
            "random_state": random_state,
            "created_at": datetime.utcnow().isoformat(),
            "elapsed_sec": round(time.time() - started, 1),
            "results": rows,
            "deltas_vs_legacy": deltas,
            "best_path_key": (best or {}).get("path_key"),
            "best_label": (best or {}).get("label"),
            "best_macro_f1_mean": (best or {}).get("macro_f1_mean"),
            "align_scope": align_scope,
            "scope_info": scope_info,
            "comparability": (
                "各路径已裁剪到共同设备-天范围，n_samples 可比，F1 差异可归因于路径本身"
                if align_scope else
                "未对齐范围：老路径用全量 parquet、新路径用 training_samples，"
                "两者数据量不同，F1 差异不可归因于路径优劣"
            ),
            "premise": (
                "默认新路径 split_mode=by_day_night 且白天夜间按时钟判定；"
                "老路径为天级 + 按值判定。对比必须分别完整跑一遍，不可直接比历史模型。"
            ),
            "note": "不会切换生产模型、不会改工作流模板落盘。",
        }
        _atomic_write_json(_compare_store_path(slot), payload)
        _atomic_write_json(
            _status_path(slot),
            {
                "status": "completed",
                "job_id": job,
                "slot": slot,
                "paths": normalized,
                "total": total,
                "completed": total,
                "partial_results": rows,
                "updated_at": datetime.utcnow().isoformat(),
                "message": "路径对比完成",
                "best_path_key": payload.get("best_path_key"),
                "best_label": payload.get("best_label"),
                "best_macro_f1_mean": payload.get("best_macro_f1_mean"),
            },
        )
        return payload
    except Exception as exc:
        logger.exception("compare_modeling_paths failed job=%s", job)
        _atomic_write_json(
            _status_path(slot),
            {
                "status": "failed",
                "job_id": job,
                "slot": slot,
                "paths": normalized,
                "total": total,
                "completed": len(rows),
                "partial_results": rows,
                "updated_at": datetime.utcnow().isoformat(),
                "message": f"路径对比失败: {exc}",
                "error": str(exc),
            },
        )
        raise


def start_compare_job(
    *,
    slot: str,
    paths: Optional[List[str]] = None,
    n_repeats: int = 3,
    test_ratio: float = 0.2,
    random_state: int = 90,
    legacy_dataset_path: Optional[str] = None,
    site_id: Optional[str] = None,
    align_scope: bool = True,
) -> Dict[str, Any]:
    """后台启动路径对比。"""
    import threading

    existing = load_compare_status(slot)
    if existing.get("status") == "running" and _slot_lock_held(slot):
        return {"accepted": False, "reason": "already_running", **existing}

    lock = _COMPARE_LOCKS.setdefault(slot, threading.Lock())
    if not lock.acquire(blocking=False):
        return {"accepted": False, "reason": "already_running", **load_compare_status(slot)}

    job_id = f"pathcmp-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
    selected = list(paths) if paths else list(DEFAULT_COMPARE_PATHS)
    normalized = [str(p).strip() for p in selected if str(p).strip()] or list(DEFAULT_COMPARE_PATHS)

    def _runner() -> None:
        try:
            compare_modeling_paths(
                slot=slot,
                paths=normalized,
                n_repeats=n_repeats,
                test_ratio=test_ratio,
                random_state=random_state,
                job_id=job_id,
                legacy_dataset_path=legacy_dataset_path,
                site_id=site_id,
                align_scope=align_scope,
            )
        except Exception:
            pass
        finally:
            try:
                lock.release()
            except RuntimeError:
                pass

    _atomic_write_json(
        _status_path(slot),
        {
            "status": "running",
            "job_id": job_id,
            "slot": slot,
            "paths": normalized,
            "n_repeats": n_repeats,
            "total": len(normalized),
            "completed": 0,
            "current_path": normalized[0] if normalized else None,
            "partial_results": [],
            "started_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "message": "路径对比已受理，正在排队启动",
        },
    )
    thread = threading.Thread(target=_runner, name=f"path-compare-{slot}", daemon=True)
    thread.start()
    return {
        "accepted": True,
        "job_id": job_id,
        "status": "running",
        "slot": slot,
        "message": "建模路径对比已在后台启动",
        "total": len(normalized),
        "completed": 0,
    }

# @AI_GENERATED: end
