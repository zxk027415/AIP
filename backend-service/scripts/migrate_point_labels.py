#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/migrate_point_labels.py — 四源标签迁移到 label_ops + point_labels

用法（conda cp_web，backend-service 目录）：
  python scripts/migrate_point_labels.py --dry-run
  python scripts/migrate_point_labels.py --execute
  python scripts/migrate_point_labels.py --rollback-batch mig-20260730-001
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.label_materializer import LabelMaterializer
from services.iterative_labeling.point_label_service import PointLabelService, SOURCE_PRIORITY
from services.iterative_labeling.sample_id import is_sample_id, parse_sample_id

logger = logging.getLogger(__name__)
SAMPLING_SECONDS = 300
NORMAL_LABEL_ID = 0
VALID_VERDICT_ACTIONS = frozenset({"confirm", "correct", "new_label"})


def _project_root() -> Path:
    return BACKEND.parent


def _data_paths() -> Dict[str, Path]:
    root = BACKEND / "data" / "iterative_labeling"
    return {
        "state": root / "cumulative_training" / "pv_fault" / "state.json",
        "workspace": root / "training_workspace" / "pv_fault",
        "parquet_a": BACKEND / "datasets" / "pv_cumulative_labeled_merged.parquet",
        "parquet_b": BACKEND / "datasets" / "dataset_combined.parquet",
    }


def _default_parquet() -> Path:
    paths = _data_paths()
    candidates = [
        paths["parquet_a"],
        _project_root() / "fault-diag-algo-release-3.1" / "相关数据" / "pv_cumulative_labeled_merged.parquet",
        _project_root() / "pv_cumulative_labeled_merged.parquet",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("未找到 pv_cumulative_labeled_merged.parquet")


def _make_batch_id() -> str:
    return f"mig-{datetime.utcnow().strftime('%Y%m%d')}-{hashlib.sha256(datetime.utcnow().isoformat().encode()).hexdigest()[:6]}"


def _parse_ts(value: str) -> datetime:
    text = str(value).strip().replace("Z", "+00:00").replace(" ", "T")
    return datetime.fromisoformat(text)


def _align_grid(ts: datetime) -> datetime:
    ts = ts.replace(microsecond=0)
    seconds = ts.hour * 3600 + ts.minute * 60 + ts.second
    rem = seconds % SAMPLING_SECONDS
    if rem:
        ts = ts - timedelta(seconds=rem)
    return ts


def _make_op_id(
    site_id: str,
    device_id: str,
    branch_id: str,
    t_start: datetime,
    t_end: datetime,
    label_id: Optional[int],
    source: str,
    salt: str = "",
) -> str:
    key = f"{source}|{site_id}|{device_id}|{branch_id}|{t_start.isoformat()}|{t_end.isoformat()}|{label_id}|{salt}"
    return f"op-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:12]}"


def _iter_covered_days(t_start: datetime, t_end: datetime) -> List[datetime]:
    first_day = t_start.replace(hour=0, minute=0, second=0, microsecond=0)
    days: List[datetime] = []
    cursor = first_day
    while cursor < t_end:
        days.append(cursor)
        cursor = cursor + timedelta(days=1)
    return days


def _build_op(
    *,
    site_id: str,
    device_id: str,
    branch_id: str,
    t_start: datetime,
    t_end: datetime,
    label_id: int,
    source: str,
    batch_id: str,
    reviewer: Optional[str] = None,
    source_ref: Optional[str] = None,
    parent_op_id: Optional[str] = None,
    rest_of_day_policy: Optional[str] = None,
    label_space_version: str = "ls-v2",
    salt: str = "",
) -> Dict[str, Any]:
    now = datetime.utcnow()
    return {
        "op_id": _make_op_id(site_id, device_id, branch_id, t_start, t_end, label_id, source, salt=salt),
        "site_id": str(site_id),
        "device_id": str(device_id),
        "branch_id": str(branch_id),
        "t_start": t_start,
        "t_end": t_end,
        "label_id": int(label_id),
        "source": source,
        "priority": SOURCE_PRIORITY[source],
        "status": "active",
        "reviewer": reviewer,
        "source_ref": source_ref,
        "rest_of_day_policy": rest_of_day_policy,
        "parent_op_id": parent_op_id,
        "label_space_version": label_space_version,
        "migration_batch_id": batch_id,
        "created_at": now,
        "updated_at": now,
    }


def _day_label_ops(df: pd.DataFrame, batch_id: str, label_space_version: str = "ls-v2") -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    ops: List[Dict[str, Any]] = []
    frame = df.copy()
    frame["time"] = pd.to_datetime(frame["time"])
    for key, grp in frame.groupby(["site_id", "device_id", "branch_id", frame["time"].dt.normalize()]):
        site_id, device_id, branch_id, day = key
        label_id = int(pd.to_numeric(grp["label"], errors="coerce").dropna().iloc[0])
        t_start = pd.Timestamp(day).to_pydatetime()
        t_end = t_start + timedelta(days=1)
        ops.append(_build_op(
            site_id=str(site_id),
            device_id=str(device_id),
            branch_id=str(branch_id),
            t_start=t_start,
            t_end=t_end,
            label_id=label_id,
            source="day_label",
            batch_id=batch_id,
            source_ref="migrate:parquet",
            label_space_version=label_space_version,
        ))
    return ops


def _human_range_ops_from_slices(
    workspace: Path,
    batch_id: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ops: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    slice_dir = workspace / "time_slices"
    if not slice_dir.exists():
        return ops, failures

    for meta_path in sorted(slice_dir.glob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append({"slice": meta_path.name, "reason": f"meta 读取失败: {exc}"})
            continue

        required = ("site_id", "device_id", "branch_id", "time_start", "time_end", "label_id", "row_count")
        if any(meta.get(field) is None for field in required):
            failures.append({"slice": meta_path.name, "reason": "meta 缺少必要字段"})
            continue

        t_start = _align_grid(_parse_ts(str(meta["time_start"])))
        t_end = _align_grid(_parse_ts(str(meta["time_end"]))) + timedelta(seconds=SAMPLING_SECONDS)
        if not (t_start < t_end):
            failures.append({"slice": meta_path.name, "reason": "时间范围非法"})
            continue

        main = _build_op(
            site_id=str(meta["site_id"]),
            device_id=str(meta["device_id"]),
            branch_id=str(meta["branch_id"]),
            t_start=t_start,
            t_end=t_end,
            label_id=int(meta["label_id"]),
            source="human_range",
            batch_id=batch_id,
            reviewer=meta.get("reviewer"),
            source_ref=str(meta.get("slice_id") or meta_path.stem),
            rest_of_day_policy="normal",
        )
        ops.append(main)

        for day_start in _iter_covered_days(t_start, t_end):
            ops.append(_build_op(
                site_id=str(meta["site_id"]),
                device_id=str(meta["device_id"]),
                branch_id=str(meta["branch_id"]),
                t_start=day_start,
                t_end=day_start + timedelta(days=1),
                label_id=NORMAL_LABEL_ID,
                source="point_rest_normal",
                batch_id=batch_id,
                reviewer=meta.get("reviewer"),
                source_ref=str(meta.get("slice_id") or meta_path.stem),
                parent_op_id=main["op_id"],
                rest_of_day_policy="normal",
                salt=main["op_id"],
            ))
    return ops, failures


def _verdict_bounds(unit_key: str, verdict_label: int) -> Tuple[str, str, str, datetime, datetime]:
    if is_sample_id(unit_key):
        parsed = parse_sample_id(unit_key)
        t_start = _align_grid(parsed["t_start"])
        if parsed["period_role"] == "whole":
            t_end = t_start.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            t_start = t_start.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            t_end = t_start + timedelta(days=1)
        raise ValueError("sample_id 裁决需结合会话单元解析设备三元组")

    parts = str(unit_key).split("|")
    if len(parts) < 4:
        raise ValueError(f"无法解析 unit_key: {unit_key!r}")
    site_id, device_id, branch_id = parts[0], parts[1], parts[2]
    time_part = "|".join(parts[3:])
    t_start = _align_grid(_parse_ts(time_part))
    day_start = t_start.replace(hour=0, minute=0, second=0, microsecond=0)
    return str(site_id), str(device_id), str(branch_id), day_start, day_start + timedelta(days=1)


def _human_day_ops_from_verdicts(
    state_path: Path,
    batch_id: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ops: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    if not state_path.exists():
        return ops, failures

    state = json.loads(state_path.read_text(encoding="utf-8"))
    entries = state.get("verdict_entries") or {}
    for entry_key, entry in entries.items():
        action = str(entry.get("action_type") or "")
        if action not in VALID_VERDICT_ACTIONS:
            continue
        if entry.get("verdict_label") is None:
            failures.append({"entry_key": entry_key, "reason": "缺少 verdict_label"})
            continue
        unit_key = str(entry.get("unit_key") or "")
        if is_sample_id(unit_key):
            failures.append({"entry_key": entry_key, "reason": "sample_id 裁决需会话上下文，暂跳过"})
            continue
        try:
            site_id, device_id, branch_id, t_start, t_end = _verdict_bounds(unit_key, int(entry["verdict_label"]))
        except ValueError as exc:
            failures.append({"entry_key": entry_key, "reason": str(exc)})
            continue
        ops.append(_build_op(
            site_id=site_id,
            device_id=device_id,
            branch_id=branch_id,
            t_start=t_start,
            t_end=t_end,
            label_id=int(entry["verdict_label"]),
            source="human_day",
            batch_id=batch_id,
            reviewer=entry.get("reviewer"),
            source_ref=str(entry.get("review_id") or entry_key),
        ))
    return ops, failures


def _cluster_ops_from_workspace(workspace: Path, batch_id: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ops: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    if not workspace.exists():
        return ops, failures

    for run_path in sorted(workspace.glob("clust-*/run.json")):
        try:
            run = json.loads(run_path.read_text(encoding="utf-8"))
        except Exception as exc:
            failures.append({"run": run_path.parent.name, "reason": f"run.json 读取失败: {exc}"})
            continue
        if run.get("status") != "confirmed":
            failures.append({
                "run": run_path.parent.name,
                "reason": f"状态 {run.get('status')} 非 confirmed，跳过",
            })
            continue
        label_id_map = run.get("label_id_map") or {}
        for cluster in (run.get("clusters") or {}).values():
            label_name = cluster.get("proposed_label_name")
            selected = cluster.get("selected_member_keys") or []
            if not selected or not label_name:
                continue
            label_id = label_id_map.get(label_name)
            if label_id is None:
                failures.append({"run": run_path.parent.name, "reason": f"簇 {label_name} 缺少 label_id"})
                continue
            for member_key in selected:
                parts = str(member_key).split("|")
                if len(parts) < 4:
                    failures.append({"member_key": member_key, "reason": "格式非法"})
                    continue
                site_id, device_id, branch_id, day_str = parts[0], parts[1], parts[2], parts[3]
                day_start = _parse_ts(day_str).replace(hour=0, minute=0, second=0, microsecond=0)
                ops.append(_build_op(
                    site_id=str(site_id),
                    device_id=str(device_id),
                    branch_id=str(branch_id),
                    t_start=day_start,
                    t_end=day_start + timedelta(days=1),
                    label_id=int(label_id),
                    source="cluster",
                    batch_id=batch_id,
                    source_ref=str(run.get("run_id") or run_path.parent.name),
                ))
    return ops, failures


def _preflight_probe(parquet_path: Path, state_path: Path, workspace: Path) -> Dict[str, Any]:
    report: Dict[str, Any] = {"ok": True, "warnings": []}
    if not parquet_path.exists():
        report["ok"] = False
        report["warnings"].append(f"缺少 parquet: {parquet_path.as_posix()}")
        return report

    df = pd.read_parquet(parquet_path, columns=["time", "site_id", "device_id", "branch_id", "label"])
    report["parquet_rows"] = int(len(df))

    # @AI_GENERATED: 采样间隔必须按设备三元组分组后再 diff。
    # 旧实现 df["time"].sort_values().diff() 是全表排序后 diff——多设备共享同一
    # 时间戳，相邻差大量为 0，median 会算出 0.0，使需求 15.6/15.7 的
    # 「采样间隔须为 300 秒，不符则标记事实基线已变化」这道门禁形同失效。
    # 实测：旧实现得 0.0，按设备分组得 300.0。
    deltas = (
        df.sort_values(["site_id", "device_id", "branch_id", "time"])
        .groupby(["site_id", "device_id", "branch_id"])["time"]
        .diff()
        .dropna()
        .dt.total_seconds()
    )
    if not deltas.empty:
        median_seconds = float(deltas.median())
        report["sampling_seconds_median"] = median_seconds
        # 门禁：采样间隔偏离预期即判定事实基线已变化，阻断迁移（需求 15.6、15.7）
        if median_seconds != float(SAMPLING_SECONDS):
            report["ok"] = False
            report["warnings"].append(
                f"事实基线已变化：采样间隔中位数为 {median_seconds} 秒，"
                f"预期 {SAMPLING_SECONDS} 秒；请重新确认迁移方案后再执行"
            )
    else:
        report["ok"] = False
        report["warnings"].append("无法计算采样间隔（按设备分组后无相邻样本）")
    # @AI_GENERATED: end

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        report["verdict_entries"] = len(state.get("verdict_entries") or {})
        report["labeled_imports"] = len(state.get("labeled_imports") or {})
    else:
        report["warnings"].append("缺少 cumulative state.json")

    slice_dir = workspace / "time_slices"
    if slice_dir.exists():
        metas = list(slice_dir.glob("*.meta.json"))
        report["time_slice_count"] = len(metas)
        report["time_slice_row_counts"] = sorted(
            int(json.loads(p.read_text(encoding="utf-8")).get("row_count") or 0) for p in metas
        )
    else:
        report["warnings"].append("缺少 time_slices 目录")
    return report


def _count_points_in_range(
    pv_repo: PVFaultRepository,
    site_id: str,
    device_id: str,
    branch_id: str,
    t_start: datetime,
    t_end: datetime,
) -> int:
    times = pv_repo.query_sample_times(site_id, device_id, branch_id, t_start, t_end)
    return len(times)


def _reconcile_ops(
    ops: List[Dict[str, Any]],
    pv_repo: PVFaultRepository,
    *,
    expected_by_ref: Optional[Dict[str, int]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    accepted: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    expected_by_ref = expected_by_ref or {}
    for op in ops:
        if op["source"] != "human_range":
            accepted.append(op)
            continue
        expected = expected_by_ref.get(str(op.get("source_ref") or ""))
        if expected is None:
            accepted.append(op)
            continue
        actual = _count_points_in_range(
            pv_repo,
            op["site_id"],
            op["device_id"],
            op["branch_id"],
            op["t_start"],
            op["t_end"],
        )
        if actual != expected:
            failures.append({
                "op_id": op["op_id"],
                "source": op["source"],
                "source_ref": op.get("source_ref"),
                "expected_points": expected,
                "actual_points": actual,
            })
            continue
        accepted.append(op)
    return accepted, failures


def _collect_all_ops(
    parquet_path: Path,
    batch_id: str,
    *,
    include_parquet: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    paths = _data_paths()
    meta: Dict[str, Any] = {"failures": [], "preflight": _preflight_probe(parquet_path, paths["state"], paths["workspace"])}

    ops: List[Dict[str, Any]] = []
    if include_parquet:
        df = pd.read_parquet(parquet_path)
        ops.extend(_day_label_ops(df, batch_id))

    slice_ops, slice_failures = _human_range_ops_from_slices(paths["workspace"], batch_id)
    ops.extend(slice_ops)
    meta["failures"].extend(slice_failures)

    verdict_ops, verdict_failures = _human_day_ops_from_verdicts(paths["state"], batch_id)
    ops.extend(verdict_ops)
    meta["failures"].extend(verdict_failures)

    cluster_ops, cluster_failures = _cluster_ops_from_workspace(paths["workspace"], batch_id)
    ops.extend(cluster_ops)
    meta["failures"].extend(cluster_failures)

    # 对账期望：time_slices row_count
    expected_by_ref: Dict[str, int] = {}
    slice_dir = paths["workspace"] / "time_slices"
    if slice_dir.exists():
        for meta_path in slice_dir.glob("*.meta.json"):
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            ref = str(payload.get("slice_id") or meta_path.stem)
            expected_by_ref[ref] = int(payload.get("row_count") or 0)

    meta["ops_by_source"] = {}
    for op in ops:
        src = op["source"]
        meta["ops_by_source"][src] = meta["ops_by_source"].get(src, 0) + 1
    meta["total_ops"] = len(ops)
    meta["expected_by_ref"] = expected_by_ref
    return ops, meta


def migrate_execute(
    parquet_path: Path | None,
    batch_id: str,
    dry_run: bool = False,
    *,
    from_db: bool = False,
    skip_parquet: bool = False,
    force: bool = False,
) -> dict:
    """执行迁移。

    Args:
        force: 为 True 时绕过 preflight 阻断（仅在确认基线变化属预期时使用）。
    """
    paths = _data_paths()
    if from_db:
        ops_preview = _day_label_ops_from_db(batch_id)
        report = {
            "batch_id": batch_id,
            "source": "training_samples",
            "ops_written": 0,
            "materialized_devices": 0,
            "dry_run": dry_run,
            "day_label_ops": len(ops_preview),
        }
        if dry_run:
            return report
        return _write_ops_and_materialize(ops_preview, batch_id, report)

    if parquet_path is None and not skip_parquet:
        parquet_path = _default_parquet()

    ops, meta = _collect_all_ops(
        parquet_path if parquet_path else paths["parquet_a"],
        batch_id,
        include_parquet=not skip_parquet and parquet_path is not None and parquet_path.exists(),
    )
    report: Dict[str, Any] = {
        "batch_id": batch_id,
        "dry_run": dry_run,
        "preflight": meta["preflight"],
        "ops_by_source_before_reconcile": meta["ops_by_source"],
        "total_ops_before_reconcile": meta["total_ops"],
        "source_failures": meta["failures"],
        "reconcile_failures": [],
        "ops_written": 0,
        "materialized_devices": 0,
    }
    if dry_run:
        report["would_write_ops"] = meta["total_ops"]
        return report

    # @AI_GENERATED: preflight 门禁真正生效（需求 15.10、15.11）。
    # 修复前 preflight.ok 只被写进报告、从不检查，迁移照跑——门禁形同失效。
    if not meta["preflight"].get("ok", True) and not force:
        report["status"] = "blocked_by_preflight"
        report["blocked_reason"] = meta["preflight"].get("warnings", [])
        logger.error(
            "迁移被前置校验阻断：%s（如确认基线变化属预期，可用 force=True 绕过）",
            report["blocked_reason"],
        )
        return report
    # @AI_GENERATED: end

    adapter = DBAdapter(DBConfig())
    pv_repo = PVFaultRepository(adapter)
    accepted, reconcile_failures = _reconcile_ops(ops, pv_repo, expected_by_ref=meta["expected_by_ref"])
    report["reconcile_failures"] = reconcile_failures
    report["total_ops_after_reconcile"] = len(accepted)
    report["ops_by_source"] = {}
    for op in accepted:
        src = op["source"]
        report["ops_by_source"][src] = report["ops_by_source"].get(src, 0) + 1

    return _write_ops_and_materialize(accepted, batch_id, report, pv_repo=pv_repo)


def _day_label_ops_from_db(batch_id: str, label_space_version: str = "ls-v2") -> list:
    adapter = DBAdapter(DBConfig())
    pv_repo = PVFaultRepository(adapter)
    rows = pv_repo.query_training_samples()
    if not rows:
        return []
    records = [{
        "time": r.time,
        "site_id": r.site_id,
        "device_id": r.device_id,
        "branch_id": r.branch_id,
        "label": r.label,
    } for r in rows if r.label is not None]
    if not records:
        return []
    return _day_label_ops(pd.DataFrame(records), batch_id, label_space_version)


def _write_ops_and_materialize(
    ops: List[Dict[str, Any]],
    batch_id: str,
    report: Dict[str, Any],
    *,
    pv_repo: Optional[PVFaultRepository] = None,
) -> Dict[str, Any]:
    adapter = DBAdapter(DBConfig())
    repo = PointLabelRepository(adapter)
    pv_repo = pv_repo or PVFaultRepository(adapter)
    materializer = LabelMaterializer(repo, pv_repo)

    # @AI_GENERATED: 按设备各自的 op 范围物化，不用全局 t_min/t_max。
    # 旧实现对所有 ops 取全局 [t_min, t_max)（本数据集跨 22 个月），再让每个设备
    # 都在这个大范围上物化一次——既违反需求 4.7「只重算受影响范围」，也让
    # 2000+ 设备各扫 22 个月，白跑大量 IO。
    device_ranges: Dict[tuple, List[datetime]] = {}
    for op in ops:
        try:
            repo.insert_op(op)
            report["ops_written"] = int(report.get("ops_written") or 0) + 1
        except Exception as exc:
            logger.warning("跳过重复/失败 op %s: %s", op.get("op_id"), exc)
        key = (str(op["site_id"]), str(op["device_id"]), str(op["branch_id"]))
        rng = device_ranges.get(key)
        if rng is None:
            device_ranges[key] = [op["t_start"], op["t_end"]]
        else:
            rng[0] = min(rng[0], op["t_start"])
            rng[1] = max(rng[1], op["t_end"])

    materialized_points = 0
    for (site_id, device_id, branch_id), (dev_start, dev_end) in device_ranges.items():
        res = materializer.materialize(site_id, device_id, branch_id, dev_start, dev_end)
        materialized_points += int(res.get("points_written") or 0)
        report["materialized_devices"] = int(report.get("materialized_devices") or 0) + 1
    # @AI_GENERATED: end

    # 迁移后对账摘要
    labeled_rows = pv_repo.query_training_samples()
    report["source_labeled_rows"] = len(labeled_rows)
    active_ops = repo.query_all_active_ops()
    report["active_ops_total"] = len(active_ops)
    report["active_ops_by_source"] = {}
    for op in active_ops:
        src = str(op.get("source") or "unknown")
        report["active_ops_by_source"][src] = report["active_ops_by_source"].get(src, 0) + 1

    # @AI_GENERATED: 空转 ops 与物化覆盖率对账（需求 14.16、14.21：
    # 总量差异须逐处可解释）。
    # 背景：迁移基于 parquet 生成 ops，但物化只能标注 training_samples 中真实
    # 存在的测量点。若 DB 里的测量数据少于 parquet，就会产生「写了 op 但没有
    # 任何点可标」的空转 ops。旧报告完全没暴露这一点，导致 4457 条 ops 里
    # 有 3000+ 条空转却看不出来。
    report["materialized_points_total"] = materialized_points
    ops_without_points = 0
    for (site_id, device_id, branch_id), (dev_start, dev_end) in device_ranges.items():
        if not pv_repo.query_sample_times(site_id, device_id, branch_id, dev_start, dev_end):
            ops_without_points += 1
    report["devices_in_ops"] = len(device_ranges)
    report["devices_without_measurements"] = ops_without_points
    report["device_materialization_coverage"] = (
        round((len(device_ranges) - ops_without_points) / len(device_ranges), 4)
        if device_ranges else None
    )
    if ops_without_points:
        report.setdefault("reconcile_notes", []).append(
            f"{ops_without_points}/{len(device_ranges)} 个设备在 label_ops 中有操作但 "
            f"training_samples 无对应测量点，这些操作为空转（不影响标签正确性，"
            f"但说明 DB 测量数据少于源 parquet；A/B 对比时须注意两条路径数据量不可比）"
        )
    # @AI_GENERATED: end

    report_path = BACKEND / "data" / "iterative_labeling" / f"migration_report_{batch_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    report["report_path"] = report_path.relative_to(BACKEND.parent).as_posix()
    return report


def rollback_batch(batch_id: str) -> dict:
    if not batch_id:
        raise ValueError("必须指定 migration_batch_id")
    adapter = DBAdapter(DBConfig())
    repo = PointLabelRepository(adapter)
    pv_repo = PVFaultRepository(adapter)
    service = PointLabelService(repo, pv_repo)
    ops = repo.query_ops_by_migration_batch(batch_id)
    revoked = []
    for op in ops:
        if op.get("status") == "active":
            service.revoke_op(op["op_id"])
            revoked.append(op["op_id"])
    return {"batch_id": batch_id, "revoked_ops": len(revoked), "op_ids": revoked}


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="迁移标签到 point_labels/label_ops")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--parquet", type=str, default="")
    parser.add_argument("--batch-id", type=str, default="")
    parser.add_argument("--from-db", action="store_true", help="从 training_samples 迁移 day_label")
    parser.add_argument("--skip-parquet", action="store_true", help="只迁移 verdict/time_slices/cluster")
    parser.add_argument("--rollback-batch", type=str, default="")
    parser.add_argument(
        "--force", action="store_true",
        help="绕过 preflight 阻断（仅在确认事实基线变化属预期时使用）",
    )
    args = parser.parse_args()

    if args.rollback_batch:
        result = rollback_batch(args.rollback_batch)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    batch_id = args.batch_id or _make_batch_id()
    parquet: Path | None
    if args.parquet:
        parquet = Path(args.parquet)
    elif args.from_db or args.skip_parquet:
        parquet = None
    else:
        try:
            parquet = _default_parquet()
        except FileNotFoundError:
            parquet = None
    dry_run = args.dry_run or not args.execute
    result = migrate_execute(
        parquet,
        batch_id,
        dry_run=dry_run,
        from_db=args.from_db,
        skip_parquet=args.skip_parquet,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
