#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @AI_GENERATED: pv-fault-dual-path-serving 任务 1.2 —— modeling_path 分区迁移
"""
scripts/migrations/20260815_add_modeling_path_partition.py
    —— 为双路径生产接入增加 modeling_path 分区维度（幂等迁移）

对应 spec：.kiro/specs/pv-fault-dual-path-serving/
  - design.md → Data Models「迁移策略（Q2：不迁移旧游标、两分区从初始水位重建）」
  - requirements.md → Req5.1 / Req5.6（路径隔离分区键）、Req10.8（不破坏脏工作区）

本脚本做且仅做 schema 变更 + 空值回填，绝不 TRUNCATE / DROP 任何业务数据或未跟踪产物，
可重复运行（每一步先探测后执行，等价 `ADD COLUMN IF NOT EXISTS`）。

改动内容（全部幂等）：
  1. device_prediction_cursor 增列 `modeling_path`（先可空）——已存在则跳过。
  2. prediction_records      增列 `modeling_path`（先可空）——已存在则跳过。
  3. prediction_records.modeling_path 历史 NULL 行回填 `legacy_day`，再置为 NOT NULL。
  4. prediction_records 增索引 ix_prediction_records_path_device——已存在则跳过。
  5. device_prediction_cursor.modeling_path NULL 行回填 `legacy_day`，置 NOT NULL，
     主键在单条 ALTER（原子）内重建为含 modeling_path 的复合键——已含则跳过。

Q2「不迁移旧游标」：不把旧 cursor 行按分区拆分、不物理删除；旧无分区行统一标记
`legacy_day`（满足复合主键非空约束），seq_annotation 分区首轮由业务代码从初始水位
自然重建；legacy_day 分区亦由首轮按事件时间游标覆盖，脚本不预置任何游标水位。

用法（conda cp_web，backend-service 目录）：
  python scripts/migrations/20260815_add_modeling_path_partition.py --dry-run   # 只探测+打印计划，不改库
  python scripts/migrations/20260815_add_modeling_path_partition.py --execute   # 实际执行 DDL
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# scripts/migrations/xxx.py -> scripts -> backend-service
BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import text  # noqa: E402

from services.db.adapter import DBAdapter  # noqa: E402
from services.db.config import DBConfig  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# --- 迁移目标常量 ---
_DEFAULT_PATH = "legacy_day"          # 历史行统一视为传统路径（现状即传统路径）
_MODELING_PATH_COL = "modeling_path"
_COL_TYPE = "VARCHAR(32)"

_CURSOR_TABLE = "device_prediction_cursor"
_RECORD_TABLE = "prediction_records"
_PATH_INDEX = "ix_prediction_records_path_device"
# 复合主键目标列顺序（与 ORM DevicePredictionCursor 主键一致）
_CURSOR_PK_COLS = ["site_id", "device_id", "branch_id", _MODELING_PATH_COL]
# 索引列顺序（与 ORM PredictionRecord.ix_prediction_records_path_device 一致）
_PATH_INDEX_COLS = ["modeling_path", "site_id", "device_id", "branch_id", "business_date"]


# ---------------------------------------------------------------------------
# 探测辅助（information_schema，只读，不改库）
# ---------------------------------------------------------------------------
def _current_database(session) -> str:
    """返回连接当前所选数据库名，供 information_schema 过滤。"""
    row = session.execute(text("SELECT DATABASE()")).fetchone()
    if not row or not row[0]:
        raise RuntimeError("无法确定当前数据库名（SELECT DATABASE() 为空）")
    return str(row[0])


def _column_exists(session, db: str, table: str, column: str) -> bool:
    row = session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND COLUMN_NAME = :col"
        ),
        {"db": db, "tbl": table, "col": column},
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def _index_exists(session, db: str, table: str, index: str) -> bool:
    row = session.execute(
        text(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl AND INDEX_NAME = :idx"
        ),
        {"db": db, "tbl": table, "idx": index},
    ).fetchone()
    return bool(row and int(row[0]) > 0)


def _pk_columns(session, db: str, table: str) -> list[str]:
    """返回主键列（按 ORDINAL_POSITION 排序）；无主键返回空列表。"""
    rows = session.execute(
        text(
            "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = :db AND TABLE_NAME = :tbl "
            "AND CONSTRAINT_NAME = 'PRIMARY' ORDER BY ORDINAL_POSITION"
        ),
        {"db": db, "tbl": table},
    ).fetchall()
    return [str(r[0]) for r in rows]


def _null_count(session, table: str, column: str) -> int:
    row = session.execute(
        text(f"SELECT COUNT(*) FROM `{table}` WHERE `{column}` IS NULL")
    ).fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# 迁移步骤（每步先探测后执行；dry_run 只打印计划）
# ---------------------------------------------------------------------------
def _add_column_if_missing(session, db: str, table: str, dry_run: bool, actions: list) -> None:
    """加 modeling_path 列（先可空，便于回填后再置非空）。已存在则跳过。"""
    if _column_exists(session, db, table, _MODELING_PATH_COL):
        logger.info("[skip] %s.%s 已存在，跳过加列", table, _MODELING_PATH_COL)
        return
    ddl = (
        f"ALTER TABLE `{table}` "
        f"ADD COLUMN `{_MODELING_PATH_COL}` {_COL_TYPE} NULL"
    )
    actions.append(ddl)
    if dry_run:
        logger.info("[plan] %s", ddl)
        return
    session.execute(text(ddl))
    logger.info("[done] %s 已加列 %s（可空）", table, _MODELING_PATH_COL)


def _backfill_and_set_not_null(session, db: str, table: str, dry_run: bool, actions: list) -> None:
    """回填历史 NULL 行为 legacy_day，然后把列改为 NOT NULL DEFAULT 'legacy_day'。

    幂等：回填只作用于 NULL 行；若列已是 NOT NULL，MODIFY 为等价定义不产生副作用。
    """
    # 列尚不存在（dry-run 且上一步未真正加列）时，按"将新增"处理，回填对象为 0 行
    col_present = _column_exists(session, db, table, _MODELING_PATH_COL)
    null_rows = _null_count(session, table, _MODELING_PATH_COL) if col_present else 0

    backfill_sql = (
        f"UPDATE `{table}` SET `{_MODELING_PATH_COL}` = :p "
        f"WHERE `{_MODELING_PATH_COL}` IS NULL"
    )
    actions.append(f"{backfill_sql}  -- 影响 {null_rows} 行")
    if dry_run:
        logger.info("[plan] 回填 %s.%s NULL→%s（约 %d 行）", table, _MODELING_PATH_COL, _DEFAULT_PATH, null_rows)
    else:
        if null_rows:
            res = session.execute(text(backfill_sql), {"p": _DEFAULT_PATH})
            logger.info("[done] 回填 %s.%s NULL→%s，%s 行", table, _MODELING_PATH_COL, _DEFAULT_PATH, res.rowcount)
        else:
            logger.info("[skip] %s.%s 无 NULL 行需回填", table, _MODELING_PATH_COL)

    modify_sql = (
        f"ALTER TABLE `{table}` "
        f"MODIFY COLUMN `{_MODELING_PATH_COL}` {_COL_TYPE} NOT NULL DEFAULT '{_DEFAULT_PATH}'"
    )
    actions.append(modify_sql)
    if dry_run:
        logger.info("[plan] %s", modify_sql)
        return
    session.execute(text(modify_sql))
    logger.info("[done] %s.%s 置为 NOT NULL DEFAULT '%s'", table, _MODELING_PATH_COL, _DEFAULT_PATH)


def _add_path_index_if_missing(session, db: str, dry_run: bool, actions: list) -> None:
    """加 ix_prediction_records_path_device 索引，已存在则跳过。"""
    if _index_exists(session, db, _RECORD_TABLE, _PATH_INDEX):
        logger.info("[skip] 索引 %s 已存在", _PATH_INDEX)
        return
    cols = ", ".join(f"`{c}`" for c in _PATH_INDEX_COLS)
    ddl = f"CREATE INDEX `{_PATH_INDEX}` ON `{_RECORD_TABLE}` ({cols})"
    actions.append(ddl)
    if dry_run:
        logger.info("[plan] %s", ddl)
        return
    session.execute(text(ddl))
    logger.info("[done] 已创建索引 %s", _PATH_INDEX)


def _rebuild_cursor_pk_if_needed(session, db: str, dry_run: bool, actions: list) -> None:
    """把 device_prediction_cursor 主键重建为含 modeling_path 的复合键。

    幂等：主键已含 modeling_path 则跳过。用单条 `ALTER TABLE ... DROP PRIMARY KEY,
    ADD PRIMARY KEY (...)`（MySQL 单语句原子执行）满足"先删旧 PK 再建新 PK 在事务内完成"。
    """
    current_pk = _pk_columns(session, db, _CURSOR_TABLE)
    if _MODELING_PATH_COL in current_pk:
        logger.info("[skip] %s 主键已含 %s（当前：%s）", _CURSOR_TABLE, _MODELING_PATH_COL, current_pk)
        return

    pk_cols = ", ".join(f"`{c}`" for c in _CURSOR_PK_COLS)
    if current_pk:
        ddl = (
            f"ALTER TABLE `{_CURSOR_TABLE}` "
            f"DROP PRIMARY KEY, ADD PRIMARY KEY ({pk_cols})"
        )
    else:
        # 理论上不会发生（该表本有复合主键）；兜底只加不删
        ddl = f"ALTER TABLE `{_CURSOR_TABLE}` ADD PRIMARY KEY ({pk_cols})"
    actions.append(ddl)
    if dry_run:
        logger.info("[plan] %s（旧主键：%s）", ddl, current_pk or "<none>")
        return
    session.execute(text(ddl))
    logger.info("[done] %s 主键重建为 %s", _CURSOR_TABLE, _CURSOR_PK_COLS)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def run(dry_run: bool = True) -> dict:
    adapter = DBAdapter(DBConfig())
    actions: list[str] = []
    try:
        with adapter.get_sync_session() as session:
            db = _current_database(session)
            logger.info("目标数据库：%s（dry_run=%s）", db, dry_run)

            # 1) prediction_records：加列 → 回填 → 置非空 → 加索引
            _add_column_if_missing(session, db, _RECORD_TABLE, dry_run, actions)
            _backfill_and_set_not_null(session, db, _RECORD_TABLE, dry_run, actions)
            _add_path_index_if_missing(session, db, dry_run, actions)

            # 2) device_prediction_cursor：加列 → 回填 → 置非空 → 重建复合主键
            _add_column_if_missing(session, db, _CURSOR_TABLE, dry_run, actions)
            _backfill_and_set_not_null(session, db, _CURSOR_TABLE, dry_run, actions)
            _rebuild_cursor_pk_if_needed(session, db, dry_run, actions)
    finally:
        adapter.dispose()

    result = {"dry_run": dry_run, "action_count": len(actions), "actions": actions}
    logger.info("迁移%s完成：%d 条 DDL/DML %s",
                "预演" if dry_run else "", len(actions),
                "（未执行）" if dry_run else "（已执行）")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="为 device_prediction_cursor / prediction_records 增加 modeling_path 分区维度（幂等）"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="只探测并打印计划，不改库（默认）")
    group.add_argument("--execute", action="store_true", help="实际执行 DDL/DML")
    args = parser.parse_args()

    # 默认安全：未显式 --execute 时按 dry-run 处理
    dry_run = not args.execute
    run(dry_run=dry_run)


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
