#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @AI_GENERATED: pv-fault-dual-path-serving 任务 2.4 —— 双路径运行时 schema 幂等迁移
"""
为 PV 双路径生产补齐 Ledger/Epoch/Lane schema，并提供安全的数据迁移骨架。

默认只执行 dry-run；只有显式传入 ``--execute`` 才会发送 DDL/DML。本脚本不会从旧
Device Cursor 推断 Seq 进度，也不会处理旧模型生命周期或旧审计分类（由任务 5.2 完成）。
MySQL DDL 可能隐式提交，因此每一步都先探测、可中断重跑，不依赖跨 DDL 的事务回滚。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

BACKEND = Path(__file__).parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402

from services.db.adapter import DBAdapter  # noqa: E402
from services.db.config import DBConfig  # noqa: E402

logger = logging.getLogger(__name__)

_VERSION = "20260816"
_SLOT = "pv_fault"
_ALLOWED_PATHS = {"legacy_day", "seq_annotation", "tsc"}
_DEFAULT_BATCH_DIR = Path("data/iterative_labeling/prediction_batches/pv_fault")

_NEW_TABLE_DDLS: Mapping[str, str] = {
    "seq_device_day_ledger": """
CREATE TABLE `seq_device_day_ledger` (
  `slot` VARCHAR(64) NOT NULL DEFAULT 'pv_fault',
  `modeling_path` VARCHAR(32) NOT NULL DEFAULT 'seq_annotation',
  `site_id` VARCHAR(128) NOT NULL,
  `device_id` VARCHAR(128) NOT NULL,
  `branch_id` VARCHAR(128) NOT NULL,
  `business_date` DATE NOT NULL,
  `status` VARCHAR(32) NOT NULL DEFAULT 'waiting_data',
  `input_fingerprint` VARCHAR(64) NULL,
  `batch_id` VARCHAR(128) NULL,
  `supersedes_batch_id` VARCHAR(128) NULL,
  `attempt_count` INT NOT NULL DEFAULT 0,
  `last_error` TEXT NULL,
  `activation_epoch_id` VARCHAR(64) NOT NULL,
  `processed_at` DATETIME NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`slot`, `modeling_path`, `site_id`, `device_id`, `branch_id`, `business_date`),
  CONSTRAINT `ck_seq_device_day_ledger_status` CHECK (`status` IN
    ('waiting_data', 'ready', 'running', 'succeeded', 'failed', 'revision_pending')),
  CONSTRAINT `ck_seq_device_day_ledger_attempt_count_non_negative` CHECK (`attempt_count` >= 0),
  INDEX `ix_seq_device_day_ledger_status_business_date`
    (`slot`, `modeling_path`, `status`, `business_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""".strip(),
    "path_activation_epochs": """
CREATE TABLE `path_activation_epochs` (
  `activation_epoch_id` VARCHAR(64) NOT NULL,
  `slot` VARCHAR(64) NOT NULL DEFAULT 'pv_fault',
  `modeling_path` VARCHAR(32) NOT NULL,
  `activation_mode` VARCHAR(32) NOT NULL,
  `backfill_days` INT NULL,
  `activated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `note` VARCHAR(500) NULL,
  `comparison_id` VARCHAR(64) NULL,
  `operator` VARCHAR(128) NULL,
  PRIMARY KEY (`activation_epoch_id`),
  CONSTRAINT `ck_path_activation_epochs_mode` CHECK
    (`activation_mode` IN ('cutover_only', 'recent_window', 'full_backfill')),
  INDEX `ix_path_activation_epochs_slot_path` (`slot`, `modeling_path`, `activated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""".strip(),
    "path_activation_device_scopes": """
CREATE TABLE `path_activation_device_scopes` (
  `activation_epoch_id` VARCHAR(64) NOT NULL,
  `site_id` VARCHAR(128) NOT NULL,
  `device_id` VARCHAR(128) NOT NULL,
  `branch_id` VARCHAR(128) NOT NULL,
  `activation_watermark` DATETIME NULL,
  `effective_from_date` DATE NULL,
  `production_cutover_date` DATE NULL,
  PRIMARY KEY (`activation_epoch_id`, `site_id`, `device_id`, `branch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""".strip(),
    "path_activation_lane_claims": """
CREATE TABLE `path_activation_lane_claims` (
  `activation_epoch_id` VARCHAR(64) NOT NULL,
  `site_id` VARCHAR(128) NOT NULL,
  `device_id` VARCHAR(128) NOT NULL,
  `branch_id` VARCHAR(128) NOT NULL,
  `lane` VARCHAR(32) NOT NULL,
  `range_start` DATE NOT NULL,
  `range_end` DATE NULL,
  `claim_status` VARCHAR(32) NOT NULL DEFAULT 'claimed',
  `backfill_task_id` VARCHAR(64) NULL,
  PRIMARY KEY (`activation_epoch_id`, `site_id`, `device_id`, `branch_id`, `lane`, `range_start`),
  CONSTRAINT `ck_path_activation_lane_claims_lane` CHECK
    (`lane` IN ('production', 'historical_backfill')),
  CONSTRAINT `ck_path_activation_lane_claims_status` CHECK
    (`claim_status` IN ('claimed', 'running', 'succeeded', 'failed', 'cancelled')),
  INDEX `ix_path_activation_lane_claims_lane_status`
    (`activation_epoch_id`, `lane`, `claim_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""".strip(),
}


class MigrationSafetyError(RuntimeError):
    """迁移无法确认事实时的安全停止；调用方不得用猜测值继续。"""


@dataclass(frozen=True)
class DeviceWatermark:
    site_id: str
    device_id: str
    branch_id: str
    watermark: Optional[datetime]


@dataclass(frozen=True)
class ConfirmedSeqFact:
    site_id: str
    device_id: str
    branch_id: str
    business_date: date
    batch_id: str
    processed_at: datetime


@dataclass(frozen=True)
class CompatibilityHooks:
    """任务 5.2 的兼容迁移扩展点；2.4 只调用，不实现分类或写入。"""

    migrate_legacy_models: Callable[[Any, bool, list[str]], None]
    migrate_legacy_audit: Callable[[Any, bool, list[str]], None]


def _deferred_legacy_models(_session: Any, _dry_run: bool, actions: list[str]) -> None:
    actions.append("DEFER legacy model registry migration to task 5.2")


def _deferred_legacy_audit(_session: Any, _dry_run: bool, actions: list[str]) -> None:
    actions.append("DEFER legacy path audit classification to task 5.2")


_DEFAULT_COMPATIBILITY_HOOKS = CompatibilityHooks(
    migrate_legacy_models=_deferred_legacy_models,
    migrate_legacy_audit=_deferred_legacy_audit,
)


def _current_database(session: Any) -> str:
    row = session.execute(text("SELECT DATABASE()")).fetchone()
    if not row or not row[0]:
        raise MigrationSafetyError("无法确定当前数据库名")
    return str(row[0])


def _table_exists(session: Any, db: str, table: str) -> bool:
    row = session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl"
        ),
        {"db": db, "tbl": table},
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def _column_exists(session: Any, db: str, table: str, column: str) -> bool:
    row = session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
        ),
        {"db": db, "tbl": table, "col": column},
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def _index_exists(session: Any, db: str, table: str, index: str) -> bool:
    row = session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND INDEX_NAME = :idx"
        ),
        {"db": db, "tbl": table, "idx": index},
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def _pk_columns(session: Any, db: str, table: str) -> list[str]:
    rows = session.execute(
        text(
            "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl "
            "AND CONSTRAINT_NAME = 'PRIMARY' ORDER BY ORDINAL_POSITION"
        ),
        {"db": db, "tbl": table},
    ).fetchall()
    return [str(row[0]) for row in rows]


def _execute_or_plan(session: Any, sql: str, params: Optional[dict], dry_run: bool, actions: list[str]) -> None:
    actions.append(" ".join(sql.split()))
    if not dry_run:
        session.execute(text(sql), params or {})


def _ensure_new_tables(session: Any, db: str, dry_run: bool, actions: list[str]) -> None:
    for table, ddl in _NEW_TABLE_DDLS.items():
        if _table_exists(session, db, table):
            continue
        _execute_or_plan(session, ddl, None, dry_run, actions)


def _ensure_partition_column(
    session: Any,
    db: str,
    table: str,
    column: str,
    column_type: str,
    default: str,
    dry_run: bool,
    actions: list[str],
) -> None:
    """按 add-nullable → 回填 NULL → not-null 的顺序补分区列。"""
    if not _table_exists(session, db, table):
        actions.append(f"SKIP missing base table {table}; create it through its owning migration")
        return
    exists = _column_exists(session, db, table, column)
    if not exists:
        _execute_or_plan(
            session,
            f"ALTER TABLE `{table}` ADD COLUMN `{column}` {column_type} NULL",
            None,
            dry_run,
            actions,
        )
    # dry-run 中列尚未实际创建，不能发送 COUNT；计划仍明确只更新 NULL。
    update_sql = f"UPDATE `{table}` SET `{column}` = :default WHERE `{column}` IS NULL"
    _execute_or_plan(session, update_sql, {"default": default}, dry_run, actions)
    _execute_or_plan(
        session,
        f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` {column_type} NOT NULL DEFAULT '{default}'",
        None,
        dry_run,
        actions,
    )


def _ensure_cursor_primary_key(session: Any, db: str, dry_run: bool, actions: list[str]) -> None:
    table = "device_prediction_cursor"
    if not _table_exists(session, db, table):
        return
    target = ["slot", "modeling_path", "site_id", "device_id", "branch_id"]
    current = _pk_columns(session, db, table)
    if current == target:
        return
    cols = ", ".join(f"`{name}`" for name in target)
    operation = "DROP PRIMARY KEY, ADD PRIMARY KEY" if current else "ADD PRIMARY KEY"
    _execute_or_plan(
        session,
        f"ALTER TABLE `{table}` {operation} ({cols})",
        None,
        dry_run,
        actions,
    )


def _ensure_record_index(session: Any, db: str, dry_run: bool, actions: list[str]) -> None:
    table = "prediction_records"
    index = "ix_prediction_records_slot_path_device"
    if not _table_exists(session, db, table) or _index_exists(session, db, table, index):
        return
    _execute_or_plan(
        session,
        f"CREATE INDEX `{index}` ON `{table}` "
        "(`slot`, `modeling_path`, `site_id`, `device_id`, `branch_id`, `business_date`)",
        None,
        dry_run,
        actions,
    )


def _ensure_existing_table_extensions(session: Any, db: str, dry_run: bool, actions: list[str]) -> None:
    _ensure_partition_column(
        session, db, "device_prediction_cursor", "slot", "VARCHAR(64)", _SLOT, dry_run, actions
    )
    _ensure_partition_column(
        session,
        db,
        "device_prediction_cursor",
        "modeling_path",
        "VARCHAR(32)",
        "legacy_day",
        dry_run,
        actions,
    )
    _ensure_partition_column(
        session,
        db,
        "device_prediction_cursor",
        "cursor_semantics",
        "VARCHAR(32)",
        "event_time_watermark",
        dry_run,
        actions,
    )
    _ensure_partition_column(
        session, db, "prediction_records", "slot", "VARCHAR(64)", _SLOT, dry_run, actions
    )
    _ensure_partition_column(
        session,
        db,
        "prediction_records",
        "modeling_path",
        "VARCHAR(32)",
        "legacy_day",
        dry_run,
        actions,
    )
    _ensure_cursor_primary_key(session, db, dry_run, actions)
    _ensure_record_index(session, db, dry_run, actions)


def _initial_epoch_id(slot: str, modeling_path: str) -> str:
    digest = hashlib.sha256(f"{_VERSION}:{slot}:{modeling_path}".encode("utf-8")).hexdigest()[:16]
    return f"pv-init-cutover-{digest}"


def _latest_closed_day(watermark: Optional[datetime]) -> Optional[date]:
    return None if watermark is None else watermark.date() - timedelta(days=1)


def _read_current_production_path(slot: str = _SLOT) -> str:
    """从现有登记只读当前生产路径；失败时安全停止而非猜 legacy_day。"""
    from services.iterative_labeling.cumulative_training import CumulativeTrainingService

    summary = CumulativeTrainingService(slot=slot).get_modeling_paths()
    path = str(summary.get("production_path") or "").strip()
    if path not in _ALLOWED_PATHS:
        raise MigrationSafetyError(f"无法确认当前生产路径: {path!r}")
    return path


def _load_device_watermarks(session: Any, db: str) -> list[DeviceWatermark]:
    """按完整性表/游标并集读取设备水位，包含无数据但有游标设备。

    不 JOIN ``training_samples``：实验室库该表可达百万行，旧写法
    ``UNION 全表 × LEFT JOIN 全表`` 会把迁移卡死。运行时设备全集以游标和
    日完整表为准；样本水位由 ``MAX(last_predicted_time/business_date)`` 代替。
    """
    merged: dict[tuple[str, str, str], Optional[datetime]] = {}

    def _put(site_id: Any, device_id: Any, branch_id: Any, watermark: Optional[datetime]) -> None:
        key = (str(site_id), str(device_id), str(branch_id))
        current = merged.get(key)
        if key not in merged or (watermark is not None and (current is None or watermark > current)):
            merged[key] = watermark

    if _table_exists(session, db, "device_prediction_cursor"):
        time_col = (
            "last_predicted_time"
            if _column_exists(session, db, "device_prediction_cursor", "last_predicted_time")
            else "last_predicted_at"
        )
        rows = session.execute(
            text(
                f"SELECT site_id, device_id, branch_id, `{time_col}` "
                "FROM device_prediction_cursor"
            )
        ).fetchall()
        for site_id, device_id, branch_id, watermark in rows:
            _put(site_id, device_id, branch_id, watermark)

    if _table_exists(session, db, "measurement_ingestion_daily"):
        rows = session.execute(
            text(
                "SELECT site_id, device_id, branch_id, MAX(business_date) "
                "FROM measurement_ingestion_daily "
                "GROUP BY site_id, device_id, branch_id"
            )
        ).fetchall()
        for site_id, device_id, branch_id, fallback_date in rows:
            watermark = None
            if fallback_date is not None:
                watermark = datetime.combine(fallback_date, datetime.min.time())
            _put(site_id, device_id, branch_id, watermark)

    return [
        DeviceWatermark(site_id, device_id, branch_id, watermark)
        for (site_id, device_id, branch_id), watermark in sorted(merged.items())
    ]


def _ensure_initial_cutover_epoch(
    session: Any,
    production_path: str,
    watermarks: Sequence[DeviceWatermark],
    dry_run: bool,
    actions: list[str],
) -> str:
    """建立确定 ID 的初始 cutover_only Epoch；无水位设备只建空边界 Scope。"""
    if production_path not in _ALLOWED_PATHS:
        raise MigrationSafetyError(f"非法生产路径: {production_path!r}")
    epoch_id = _initial_epoch_id(_SLOT, production_path)
    existing = session.execute(
        text(
            "SELECT slot, modeling_path, activation_mode FROM path_activation_epochs "
            "WHERE activation_epoch_id = :epoch_id"
        ),
        {"epoch_id": epoch_id},
    ).fetchone()
    expected_identity = (_SLOT, production_path, "cutover_only")
    if existing and tuple(existing) != expected_identity:
        raise MigrationSafetyError(f"初始 Epoch {epoch_id} 已存在但身份冲突")
    if not existing:
        _execute_or_plan(
            session,
            "INSERT INTO path_activation_epochs "
            "(activation_epoch_id, slot, modeling_path, activation_mode, backfill_days, note, operator) "
            "VALUES (:epoch_id, :slot, :path, 'cutover_only', NULL, :note, :operator)",
            {
                "epoch_id": epoch_id,
                "slot": _SLOT,
                "path": production_path,
                "note": f"initial cutover-only epoch from migration {_VERSION}",
                "operator": f"migration:{_VERSION}",
            },
            dry_run,
            actions,
        )

    for item in watermarks:
        key_params = {
            "epoch_id": epoch_id,
            "site_id": item.site_id,
            "device_id": item.device_id,
            "branch_id": item.branch_id,
        }
        scope_exists = session.execute(
            text(
                "SELECT COUNT(*) FROM path_activation_device_scopes WHERE activation_epoch_id = :epoch_id "
                "AND site_id = :site_id AND device_id = :device_id AND branch_id = :branch_id"
            ),
            key_params,
        ).fetchone()
        cutover = _latest_closed_day(item.watermark)
        if not scope_exists or int(scope_exists[0]) == 0:
            _execute_or_plan(
                session,
                "INSERT INTO path_activation_device_scopes "
                "(activation_epoch_id, site_id, device_id, branch_id, activation_watermark, "
                "effective_from_date, production_cutover_date) VALUES "
                "(:epoch_id, :site_id, :device_id, :branch_id, :watermark, :cutover, :cutover)",
                {**key_params, "watermark": item.watermark, "cutover": cutover},
                dry_run,
                actions,
            )
        # range_start 是主键且不可空；无数据设备绝不伪造 claim。
        if cutover is None:
            continue
        claim_params = {**key_params, "range_start": cutover}
        claim_exists = session.execute(
            text(
                "SELECT COUNT(*) FROM path_activation_lane_claims WHERE activation_epoch_id = :epoch_id "
                "AND site_id = :site_id AND device_id = :device_id AND branch_id = :branch_id "
                "AND lane = 'production' AND range_start = :range_start"
            ),
            claim_params,
        ).fetchone()
        if not claim_exists or int(claim_exists[0]) == 0:
            _execute_or_plan(
                session,
                "INSERT INTO path_activation_lane_claims "
                "(activation_epoch_id, site_id, device_id, branch_id, lane, range_start, range_end, claim_status) "
                "VALUES (:epoch_id, :site_id, :device_id, :branch_id, 'production', :range_start, NULL, 'claimed')",
                claim_params,
                dry_run,
                actions,
            )
    return epoch_id


def _parse_datetime(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _extract_confirmable_seq_units(payload: Mapping[str, Any], batch_id: str) -> list[ConfirmedSeqFact]:
    """只从结构完整的不可变 Seq point 批次提取候选事实；不代表已可回填。"""
    if payload.get("modeling_path") != "seq_annotation":
        return []
    if payload.get("prediction_granularity") != "point":
        return []
    if not str(payload.get("dataset_version") or "").strip():
        return []
    if not str(payload.get("model_ref") or "").strip():
        return []
    processed_at = _parse_datetime(payload.get("created_at"))
    predictions = payload.get("predictions")
    advances = payload.get("cursor_advance_times")
    if processed_at is None or not isinstance(predictions, list) or not predictions:
        return []
    if not isinstance(advances, list) or not advances:
        return []
    advance_keys = {
        (str(item.get("site_id")), str(item.get("device_id")), str(item.get("branch_id")))
        for item in advances
        if isinstance(item, dict) and _parse_datetime(item.get("last_predicted_time")) is not None
    }
    facts: dict[tuple[str, str, str, date], ConfirmedSeqFact] = {}
    for item in predictions:
        if not isinstance(item, dict):
            return []
        key3 = tuple(str(item.get(name) or "").strip() for name in ("site_id", "device_id", "branch_id"))
        if not all(key3) or key3 not in advance_keys:
            return []
        try:
            business_date = date.fromisoformat(str(item.get("time_window") or "")[:10])
        except ValueError:
            return []
        key = (*key3, business_date)
        facts[key] = ConfirmedSeqFact(*key3, business_date, batch_id, processed_at)
    return sorted(facts.values(), key=lambda fact: (fact.business_date, fact.site_id, fact.device_id, fact.branch_id))


def _filter_confirmed_seq_facts(
    candidates: Iterable[ConfirmedSeqFact],
    prediction_record_keys: set[tuple[str, str, str, date, str]],
    scope_effective_from: Mapping[tuple[str, str, str], Optional[date]],
) -> list[ConfirmedSeqFact]:
    """要求 DB 批次引用一致且日期属于 Epoch；否则不猜 succeeded。"""
    confirmed = []
    for fact in candidates:
        device = (fact.site_id, fact.device_id, fact.branch_id)
        effective_from = scope_effective_from.get(device)
        record_key = (*device, fact.business_date, fact.batch_id)
        if effective_from is None or fact.business_date < effective_from:
            continue
        if record_key not in prediction_record_keys:
            continue
        confirmed.append(fact)
    return confirmed


def _scan_batch_payloads(batch_dir: Path = _DEFAULT_BATCH_DIR) -> Iterable[tuple[str, Mapping[str, Any]]]:
    if not batch_dir.exists():
        return []
    payloads = []
    for path in sorted(batch_dir.glob("pred-seq-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payloads.append((path.stem, payload))
    return payloads


def _backfill_confirmed_seq_successes(
    session: Any,
    epoch_id: str,
    dry_run: bool,
    actions: list[str],
    batch_payloads: Optional[Iterable[tuple[str, Mapping[str, Any]]]] = None,
) -> int:
    """按不可变批次 + PredictionRecord + Epoch Scope 三方事实安全回填 succeeded。"""
    raw_candidates = []
    for batch_id, payload in batch_payloads if batch_payloads is not None else _scan_batch_payloads():
        raw_candidates.extend(_extract_confirmable_seq_units(payload, batch_id))
    if not raw_candidates:
        return 0

    rows = session.execute(
        text(
            "SELECT site_id, device_id, branch_id, business_date, "
            "JSON_UNQUOTE(JSON_EXTRACT(input_feature_json, '$.prediction_batch_id')) AS batch_id "
            "FROM prediction_records WHERE slot = :slot AND modeling_path = 'seq_annotation'"
        ),
        {"slot": _SLOT},
    ).fetchall()
    record_keys = {(str(a), str(b), str(c), d, str(batch)) for a, b, c, d, batch in rows if d and batch}
    scope_rows = session.execute(
        text(
            "SELECT site_id, device_id, branch_id, effective_from_date "
            "FROM path_activation_device_scopes WHERE activation_epoch_id = :epoch_id"
        ),
        {"epoch_id": epoch_id},
    ).fetchall()
    scopes = {(str(a), str(b), str(c)): effective for a, b, c, effective in scope_rows}
    confirmed = _filter_confirmed_seq_facts(raw_candidates, record_keys, scopes)
    for fact in confirmed:
        _execute_or_plan(
            session,
            "INSERT INTO seq_device_day_ledger "
            "(slot, modeling_path, site_id, device_id, branch_id, business_date, activation_epoch_id, "
            "status, input_fingerprint, batch_id, supersedes_batch_id, attempt_count, processed_at) "
            "SELECT :slot, 'seq_annotation', :site_id, :device_id, :branch_id, :business_date, :epoch_id, "
            "'succeeded', NULL, :batch_id, NULL, 0, :processed_at FROM DUAL WHERE NOT EXISTS "
            "(SELECT 1 FROM seq_device_day_ledger WHERE slot = :slot AND modeling_path = 'seq_annotation' "
            "AND site_id = :site_id AND device_id = :device_id AND branch_id = :branch_id "
            "AND business_date = :business_date)",
            {
                "slot": _SLOT,
                "site_id": fact.site_id,
                "device_id": fact.device_id,
                "branch_id": fact.branch_id,
                "business_date": fact.business_date,
                "epoch_id": epoch_id,
                "batch_id": fact.batch_id,
                "processed_at": fact.processed_at,
            },
            dry_run,
            actions,
        )
    return len(confirmed)


def migrate_session(
    session: Any,
    *,
    dry_run: bool = True,
    production_path: Optional[str] = None,
    watermarks: Optional[Sequence[DeviceWatermark]] = None,
    batch_payloads: Optional[Iterable[tuple[str, Mapping[str, Any]]]] = None,
    compatibility_hooks: CompatibilityHooks = _DEFAULT_COMPATIBILITY_HOOKS,
) -> dict[str, Any]:
    actions: list[str] = []
    db = _current_database(session)
    _ensure_new_tables(session, db, dry_run, actions)
    _ensure_existing_table_extensions(session, db, dry_run, actions)

    selected_path = production_path or _read_current_production_path(_SLOT)
    selected_watermarks = list(watermarks) if watermarks is not None else _load_device_watermarks(session, db)
    epoch_id = _ensure_initial_cutover_epoch(session, selected_path, selected_watermarks, dry_run, actions)
    confirmed_count = _backfill_confirmed_seq_successes(
        session, epoch_id, dry_run, actions, batch_payloads=batch_payloads
    )

    # 任务 5.2 可替换这两个 hook；本版本只明确记录 defer，不猜模型/审计语义。
    compatibility_hooks.migrate_legacy_models(session, dry_run, actions)
    compatibility_hooks.migrate_legacy_audit(session, dry_run, actions)
    return {
        "dry_run": dry_run,
        "action_count": len(actions),
        "actions": actions,
        "initial_epoch_id": epoch_id,
        "confirmed_seq_successes": confirmed_count,
    }


def run(dry_run: bool = True) -> dict[str, Any]:
    adapter = DBAdapter(DBConfig())
    try:
        with adapter.get_sync_session() as session:
            return migrate_session(session, dry_run=dry_run)
    finally:
        adapter.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="PV 双路径运行时 schema 幂等迁移（默认 dry-run）")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="只探测并打印计划（默认）")
    group.add_argument("--execute", action="store_true", help="显式执行幂等 DDL/DML")
    args = parser.parse_args()
    result = run(dry_run=not args.execute)
    for action in result["actions"]:
        print(action)
    print(json.dumps({key: value for key, value in result.items() if key != "actions"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
