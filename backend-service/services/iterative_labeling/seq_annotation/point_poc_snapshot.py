# @AI_GENERATED
# -*- coding: utf-8 -*-
"""实时点路径 Phase 0 不可变 POC 快照构建器。

本模块只读取共享的外部测量源和现有逐点标签，发布点路径专属快照；不修改生产表，
不复用旧全天双侧插值，也不让后续训练运行时查询天路径测量表。
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from services.iterative_labeling.point_label_service import POINT_PATH_LABEL_SOURCES

logger = logging.getLogger(__name__)

_BACKEND = Path(__file__).resolve().parents[3]
_PROJECT_ROOT = _BACKEND.parent
_DEFAULT_OUTPUT_ROOT = _BACKEND / "data" / "realtime_point_poc" / "snapshots"

EXPECTED_ORIGINAL_COUNT = 374
SNAPSHOT_SCHEMA_VERSION = "point-poc-snapshot-v1"
PHASE0_POINT_SOURCES = frozenset(POINT_PATH_LABEL_SOURCES)
_DEVICE_COLUMNS = ["site_id", "device_id", "branch_id"]
_INDEX_COLUMNS = [*_DEVICE_COLUMNS, "date"]
_MEASUREMENT_COLUMNS = ["time", *_DEVICE_COLUMNS, "value", "i_cal"]
_POINT_COLUMNS = [
    *_DEVICE_COLUMNS,
    "time",
    "label_id",
    "source",
    "priority",
    "op_id",
    "label_space_version",
    "updated_at",
]
_OP_COLUMNS = [
    "op_id",
    *_DEVICE_COLUMNS,
    "t_start",
    "t_end",
    "label_id",
    "source",
    "priority",
    "status",
    "reviewer",
    "source_ref",
    "rest_of_day_policy",
    "parent_op_id",
    "label_space_version",
    "migration_batch_id",
    "created_at",
    "updated_at",
]


def _normalise_relative_arg(path: str, param_name: str) -> str:
    """校验项目根相对路径，并统一为 POSIX 形式用于持久化。"""
    if not path or Path(path).is_absolute() or os.path.isabs(path):
        raise ValueError(f"参数 {param_name} 必须是项目根相对路径: {path!r}")
    normalised = Path(path.replace("\\", "/")).as_posix()
    resolved = (_PROJECT_ROOT / normalised).resolve()
    try:
        resolved.relative_to(_PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"参数 {param_name} 越界项目根: {path}") from exc
    return normalised


def _resolve_relative(path: str, param_name: str = "path") -> Path:
    normalised = _normalise_relative_arg(path, param_name)
    return (_PROJECT_ROOT / normalised).resolve()


def _to_project_relative(path: Path) -> str:
    return path.resolve().relative_to(_PROJECT_ROOT.resolve()).as_posix()


def _compute_file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dispose_adapter(adapter: Any) -> None:
    """释放同步/异步连接池，规避当前 DBAdapter.dispose() 未 await 异步 dispose 的 warning。"""
    sync_engine = getattr(adapter, "_sync_engine", None)
    if sync_engine is not None:
        sync_engine.dispose()
    async_engine = getattr(adapter, "_async_engine", None)
    if async_engine is None:
        return
    dispose_result = async_engine.dispose()
    if not inspect.isawaitable(dispose_result):
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(dispose_result)
    else:
        loop.create_task(dispose_result)


def _normalise_time(series: pd.Series, field_name: str) -> pd.Series:
    parsed = pd.to_datetime(series, errors="raise")
    timezone = getattr(parsed.dt, "tz", None)
    if timezone is not None:
        parsed = parsed.dt.tz_convert("UTC").dt.tz_localize(None)
        logger.info("字段 %s 已从带时区时间统一为 UTC naive", field_name)
    return parsed


def _canonical_frame_hash(
    frame: pd.DataFrame,
    *,
    fields: Sequence[str],
    sort_fields: Sequence[str],
) -> str:
    """对 DataFrame 做稳定 JSON 序列化并计算 SHA-256。"""
    if frame.empty:
        payload = "[]"
    else:
        canonical = frame.reindex(columns=list(fields)).copy()
        canonical = canonical.sort_values(list(sort_fields), kind="mergesort").reset_index(drop=True)
        rows: List[Dict[str, Any]] = []
        for record in canonical.to_dict(orient="records"):
            row: Dict[str, Any] = {}
            for key, value in record.items():
                if isinstance(value, (datetime, pd.Timestamp)):
                    value = value.isoformat()
                elif pd.isna(value):
                    value = None
                row[key] = value
            rows.append(row)
        payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _active_op_hash(ops_df: pd.DataFrame) -> str:
    fields = [
        "op_id",
        *_DEVICE_COLUMNS,
        "t_start",
        "t_end",
        "label_id",
        "source",
        "priority",
        "status",
        "parent_op_id",
        "rest_of_day_policy",
        "label_space_version",
    ]
    active = ops_df[ops_df["status"] == "active"] if not ops_df.empty else ops_df
    return _canonical_frame_hash(active, fields=fields, sort_fields=["op_id"])


def _point_label_hash(points_df: pd.DataFrame) -> str:
    fields = [
        *_DEVICE_COLUMNS,
        "time",
        "label_id",
        "source",
        "priority",
        "op_id",
        "label_space_version",
    ]
    return _canonical_frame_hash(
        points_df,
        fields=fields,
        sort_fields=[*_DEVICE_COLUMNS, "time"],
    )


def load_original_index(
    index_path: str,
    *,
    context_length: int = 72,
    slot_minutes: int = 5,
) -> pd.DataFrame:
    """加载 374 个 original 设备日，并固化目标范围和前置上下文范围。"""
    if context_length <= 0:
        raise ValueError("context_length 必须大于 0")
    if slot_minutes <= 0 or 1440 % slot_minutes != 0:
        raise ValueError("slot_minutes 必须为可整除 1440 的正整数")

    resolved = _resolve_relative(index_path, "index_path")
    if not resolved.is_file():
        raise FileNotFoundError(f"索引文件不存在: {index_path}")

    meta = pd.read_parquet(resolved)
    required = {*_INDEX_COLUMNS, "is_augmented"}
    missing = sorted(required - set(meta.columns))
    if missing:
        raise ValueError(f"索引缺少必需列: {missing}")

    original = meta.loc[~meta["is_augmented"].fillna(True).astype(bool), _INDEX_COLUMNS].copy()
    for column in _DEVICE_COLUMNS:
        original[column] = original[column].astype(str)
    original["date"] = _normalise_time(original["date"], "date").dt.normalize()
    original = original.drop_duplicates(_INDEX_COLUMNS).sort_values(_INDEX_COLUMNS).reset_index(drop=True)
    if len(original) != EXPECTED_ORIGINAL_COUNT:
        raise ValueError(
            f"期望 {EXPECTED_ORIGINAL_COUNT} 个 original 设备日，去重后实际 {len(original)}"
        )

    original["target_start"] = original["date"]
    original["target_end"] = original["date"] + pd.Timedelta(days=1)
    original["context_start"] = original["target_start"] - pd.Timedelta(
        minutes=(context_length - 1) * slot_minutes
    )
    original["context_length"] = int(context_length)
    original["slot_minutes"] = int(slot_minutes)
    original["index_id"] = [f"idx-{i:04d}" for i in range(len(original))]
    return original


def load_source_measurements(
    source_path: str,
    index_df: pd.DataFrame,
    *,
    slot_minutes: int = 5,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """提取目标日和前置历史测量，不读取外部天级 label 列。"""
    resolved = _resolve_relative(source_path, "source_path")
    if not resolved.is_file():
        raise FileNotFoundError(f"外部测量源不存在: {source_path}")

    raw = pd.read_parquet(resolved, columns=_MEASUREMENT_COLUMNS)
    raw["time"] = _normalise_time(raw["time"], "time")
    for column in _DEVICE_COLUMNS:
        raw[column] = raw[column].astype(str)
    for column in ["value", "i_cal"]:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")

    off_grid = (
        (raw["time"].dt.second != 0)
        | (raw["time"].dt.microsecond != 0)
        | ((raw["time"].dt.minute % slot_minutes) != 0)
    )
    if off_grid.any():
        examples = raw.loc[off_grid, "time"].head(5).astype(str).tolist()
        raise ValueError(f"外部测量包含非 {slot_minutes} 分钟槽时间，示例: {examples}")

    key_columns = [*_DEVICE_COLUMNS, "time"]
    duplicate_mask = raw.duplicated(key_columns, keep=False)
    duplicate_rows = int(duplicate_mask.sum())
    if duplicate_rows:
        duplicate_groups = raw.loc[duplicate_mask].groupby(key_columns, dropna=False)
        conflicting = sum(
            1
            for _, group in duplicate_groups
            if group[["value", "i_cal"]].drop_duplicates().shape[0] > 1
        )
        if conflicting:
            raise ValueError(f"外部测量存在 {conflicting} 组同键冲突值，拒绝静默聚合")
        raw = raw.drop_duplicates(key_columns, keep="first")

    intervals = index_df[
        ["index_id", *_DEVICE_COLUMNS, "context_start", "target_start", "target_end"]
    ]
    joined = raw.merge(intervals, on=_DEVICE_COLUMNS, how="inner", validate="many_to_many")
    in_snapshot = (joined["time"] >= joined["context_start"]) & (joined["time"] < joined["target_end"])
    selected = joined.loc[in_snapshot, _MEASUREMENT_COLUMNS].drop_duplicates(key_columns)
    selected = selected.sort_values(key_columns).reset_index(drop=True)

    target_rows = joined.loc[
        (joined["time"] >= joined["target_start"]) & (joined["time"] < joined["target_end"]),
        "index_id",
    ]
    hit_ids = set(target_rows.astype(str))
    missing_ids = sorted(set(index_df["index_id"].astype(str)) - hit_ids)
    if missing_ids:
        raise ValueError(
            f"外部源只命中 {len(index_df) - len(missing_ids)}/{len(index_df)} 个目标设备日，"
            f"缺失示例: {missing_ids[:5]}"
        )

    report = {
        "target_index_count": int(len(index_df)),
        "target_hit_count": int(len(hit_ids)),
        "measurement_rows": int(len(selected)),
        "source_duplicate_rows_dropped": duplicate_rows,
        "context_rows": int(
            len(
                joined.loc[
                    in_snapshot & (joined["time"] < joined["target_start"]),
                    key_columns,
                ].drop_duplicates()
            )
        ),
    }
    return selected, report


def _read_relevant_label_snapshot(repo: Any, index_df: pd.DataFrame) -> Dict[str, Any]:
    """从 DB 读取目标设备日相关的点标签和 active 操作，并执行来源白名单过滤。"""
    points: List[Dict[str, Any]] = []
    ops_by_id: Dict[str, Dict[str, Any]] = {}
    rejected_point_sources: Dict[str, int] = {}
    rejected_op_sources: Dict[str, int] = {}

    for row in index_df.itertuples(index=False):
        t_start = pd.Timestamp(row.target_start).to_pydatetime()
        t_end = pd.Timestamp(row.target_end).to_pydatetime()
        queried_points = repo.query_points(row.site_id, row.device_id, row.branch_id, t_start, t_end)
        for point in queried_points:
            source = str(point.get("source") or "")
            if source not in PHASE0_POINT_SOURCES:
                rejected_point_sources[source] = rejected_point_sources.get(source, 0) + 1
                continue
            if point.get("label_id") is not None:
                points.append(point)

        queried_ops = repo.query_active_ops(row.site_id, row.device_id, row.branch_id, t_start, t_end)
        for op in queried_ops:
            source = str(op.get("source") or "")
            if source not in PHASE0_POINT_SOURCES:
                rejected_op_sources[source] = rejected_op_sources.get(source, 0) + 1
                continue
            ops_by_id[str(op["op_id"])] = op

    points_df = pd.DataFrame(points, columns=_POINT_COLUMNS)
    if not points_df.empty:
        points_df["time"] = _normalise_time(points_df["time"], "point_labels.time")
        for column in _DEVICE_COLUMNS:
            points_df[column] = points_df[column].astype(str)
        points_df = points_df.drop_duplicates([*_DEVICE_COLUMNS, "time"], keep="last")
        points_df = points_df.sort_values([*_DEVICE_COLUMNS, "time"]).reset_index(drop=True)

    ops_df = pd.DataFrame(list(ops_by_id.values()), columns=_OP_COLUMNS)
    if not ops_df.empty:
        for column in ["t_start", "t_end", "created_at", "updated_at"]:
            ops_df[column] = _normalise_time(ops_df[column], f"label_ops.{column}")
        for column in _DEVICE_COLUMNS:
            ops_df[column] = ops_df[column].astype(str)
        ops_df = ops_df.sort_values("op_id").reset_index(drop=True)

    op_hash = _active_op_hash(ops_df)
    point_hash = _point_label_hash(points_df)
    combined = hashlib.sha256(f"{op_hash}|{point_hash}".encode("utf-8")).hexdigest()
    return {
        "point_labels_df": points_df,
        "label_ops_df": ops_df,
        "active_op_hash": op_hash,
        "point_label_hash": point_hash,
        "label_snapshot_hash": combined,
        "rejected_point_sources": rejected_point_sources,
        "rejected_op_sources": rejected_op_sources,
    }


def _artifact_manifest(tmp_dir: Path, final_dir: Path) -> Dict[str, Dict[str, Any]]:
    artifacts: Dict[str, Dict[str, Any]] = {}
    for filename in ["index.parquet", "measurements.parquet", "point_labels.parquet", "label_ops.parquet"]:
        temp_path = tmp_dir / filename
        artifacts[filename] = {
            "path": _to_project_relative(final_dir / filename),
            "sha256": _compute_file_sha256(temp_path),
            "bytes": int(temp_path.stat().st_size),
        }
    return artifacts


def build_snapshot(
    *,
    source_path: str,
    index_path: str,
    output_root: Optional[str] = None,
    context_length: int = 72,
    slot_minutes: int = 5,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """构建并原子发布点路径 POC 快照；dry-run 不连接 DB 且不写文件。"""
    source_path = _normalise_relative_arg(source_path, "source_path")
    index_path = _normalise_relative_arg(index_path, "index_path")
    if output_root is not None:
        output_root = _normalise_relative_arg(output_root, "output_root")

    source_file = _resolve_relative(source_path, "source_path")
    source_sha_before = _compute_file_sha256(source_file)
    index_df = load_original_index(
        index_path,
        context_length=context_length,
        slot_minutes=slot_minutes,
    )
    measurements_df, source_report = load_source_measurements(
        source_path,
        index_df,
        slot_minutes=slot_minutes,
    )
    source_sha_after_read = _compute_file_sha256(source_file)
    if source_sha_before != source_sha_after_read:
        raise RuntimeError("外部测量源在读取期间发生变化，拒绝构建快照")

    if dry_run:
        return {
            "status": "dry_run_ok",
            "original_count": int(len(index_df)),
            "source_hit": source_report["target_hit_count"],
            "source_rows": source_report["measurement_rows"],
            "context_rows": source_report["context_rows"],
            "source_sha256": source_sha_before,
        }

    from services.db.adapter import DBAdapter
    from services.db.config import DBConfig
    from services.db.repositories.point_label import PointLabelRepository

    adapter = DBAdapter(DBConfig())
    try:
        repo = PointLabelRepository(adapter)
        label_before = _read_relevant_label_snapshot(repo, index_df)
        if label_before["point_labels_df"].empty:
            raise ValueError(
                "目标 374 设备日没有点路径逐点标签，无法生成训练 POC 快照"
            )

        out_base = _resolve_relative(output_root, "output_root") if output_root else _DEFAULT_OUTPUT_ROOT
        out_base.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="point-poc-tmp-", dir=str(out_base)))
        try:
            index_df.to_parquet(temp_dir / "index.parquet", index=False)
            measurements_df.to_parquet(temp_dir / "measurements.parquet", index=False)
            label_before["point_labels_df"].to_parquet(temp_dir / "point_labels.parquet", index=False)
            label_before["label_ops_df"].to_parquet(temp_dir / "label_ops.parquet", index=False)

            label_after = _read_relevant_label_snapshot(repo, index_df)
            if label_before["label_snapshot_hash"] != label_after["label_snapshot_hash"]:
                raise RuntimeError(
                    "相关 point_labels/label_ops 在构建期间发生变化，拒绝发布快照"
                )
            source_sha_after_write = _compute_file_sha256(source_file)
            if source_sha_before != source_sha_after_write:
                raise RuntimeError("外部测量源在构建期间发生变化，拒绝发布快照")

            pre_digest = hashlib.sha256(
                "|".join(
                    [
                        source_sha_before,
                        label_before["label_snapshot_hash"],
                        str(context_length),
                        str(slot_minutes),
                    ]
                ).encode("utf-8")
            ).hexdigest()
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            snapshot_name = f"point-poc-{timestamp}-{pre_digest[:8]}"
            final_dir = out_base / snapshot_name
            if final_dir.exists():
                raise FileExistsError(f"快照目录已存在，拒绝覆盖: {_to_project_relative(final_dir)}")

            artifacts = _artifact_manifest(temp_dir, final_dir)
            manifest = {
                "snapshot_version": snapshot_name,
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "created_at": datetime.utcnow().isoformat() + "Z",
                "source_path": source_path,
                "source_sha256": source_sha_before,
                "index_path": index_path,
                "allowed_point_sources": sorted(PHASE0_POINT_SOURCES),
                "context_length": int(context_length),
                "slot_minutes": int(slot_minutes),
                "original_count": int(len(index_df)),
                "measurement_rows": int(len(measurements_df)),
                "point_label_rows": int(len(label_before["point_labels_df"])),
                "label_op_rows": int(len(label_before["label_ops_df"])),
                "active_op_hash": label_before["active_op_hash"],
                "point_label_hash": label_before["point_label_hash"],
                "label_snapshot_hash": label_before["label_snapshot_hash"],
                "source_report": source_report,
                "rejected_point_sources": label_before["rejected_point_sources"],
                "rejected_op_sources": label_before["rejected_op_sources"],
                "artifacts": artifacts,
                "causal_provenance_note": (
                    "measurements.parquet 只含原始测量列和已发生的前置上下文，未执行双侧插值；"
                    "外部 parquet 入仓前是否被预处理无法由本仓库证明，须结合 source_sha256 审计。"
                ),
            }
            (temp_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            temp_dir.rename(final_dir)
        except BaseException:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise
    finally:
        _dispose_adapter(adapter)

    relative_snapshot = _to_project_relative(final_dir)
    logger.info("点路径 POC 快照已发布: %s", relative_snapshot)
    return {
        "status": "ok",
        "snapshot_dir": relative_snapshot,
        "manifest": manifest,
    }
# @AI_GENERATED: end
