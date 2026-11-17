# @AI_GENERATED
# -*- coding: utf-8 -*-
"""把旧 ``label_ops`` 拆到天/点独立账本，并执行迁移作用域双读对账。

默认及 ``--dry-run`` 都是只读：不建表、不写库；如果新表已存在，则读取真实新表
并报告差异。只有 ``--execute`` 会建表、规范化来源并幂等 upsert。旧 ``label_ops``
始终保留，不删除。注意 MySQL DDL 可能隐式提交，因此回滚保证只覆盖迁移 DML。

PowerShell::

  python scripts/migrate_label_path_isolation.py --dry-run
  python scripts/migrate_label_path_isolation.py --execute
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Type

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import inspect, select
from sqlalchemy.dialects.mysql import insert as mysql_insert

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.models.pv_fault import DayLabel, DayLabelOp, LabelOp, PointLabelOp
from services.iterative_labeling.label_path_isolation import (
    compare_path_ledgers,
    materialize_day_labels,
    plan_legacy_ops_by_path,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s %(message)s")
logger = logging.getLogger("migrate_label_path_isolation")


def _op_to_dict(op: LabelOp) -> Dict[str, Any]:
    return {
        "op_id": op.op_id,
        "site_id": op.site_id,
        "device_id": op.device_id,
        "branch_id": op.branch_id,
        "t_start": op.t_start,
        "t_end": op.t_end,
        "label_id": op.label_id,
        "source": op.source,
        "priority": op.priority,
        "status": op.status,
        "reviewer": op.reviewer,
        "source_ref": op.source_ref,
        "rest_of_day_policy": op.rest_of_day_policy,
        "parent_op_id": op.parent_op_id,
        "label_space_version": op.label_space_version,
        "migration_batch_id": op.migration_batch_id,
        "created_at": op.created_at,
        "updated_at": op.updated_at,
    }


def _ensure_tables(adapter: DBAdapter) -> None:
    engine = adapter._sync_engine
    DayLabelOp.__table__.create(engine, checkfirst=True)
    DayLabel.__table__.create(engine, checkfirst=True)
    PointLabelOp.__table__.create(engine, checkfirst=True)


def _row_to_dict(row: Any, fields: Sequence[str]) -> Dict[str, Any]:
    return {name: getattr(row, name) for name in fields}


_POINT_OP_FIELDS = [
    "op_id", "site_id", "device_id", "branch_id", "t_start", "t_end", "label_id",
    "source", "priority", "status", "reviewer", "source_ref", "rest_of_day_policy",
    "parent_op_id", "label_space_version", "migration_batch_id", "created_at", "updated_at",
]
_DAY_OP_FIELDS = _POINT_OP_FIELDS[:4] + ["business_date"] + _POINT_OP_FIELDS[4:]
_DAY_LABEL_FIELDS = [
    "site_id", "device_id", "branch_id", "business_date", "label_id",
    "source", "op_id", "reviewer", "label_space_version", "updated_at",
]


def _load_rows_if_table_exists(
    adapter: DBAdapter,
    session,
    model: Type[Any],
    fields: Sequence[str],
) -> List[Dict[str, Any]]:
    table_name = model.__table__.name
    if not inspect(adapter._sync_engine).has_table(table_name):
        return []
    return [
        _row_to_dict(row, fields)
        for row in session.execute(select(model)).scalars().all()
    ]


def _upsert_rows(session, model: Type[Any], rows: List[Dict[str, Any]], fields: Sequence[str]) -> None:
    if not rows:
        return
    statement = mysql_insert(model).values(rows)
    updates = {
        field: getattr(statement.inserted, field)
        for field in fields
        if field != "op_id"
    }
    session.execute(statement.on_duplicate_key_update(**updates))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="迁移天/点标签到隔离表")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只读真实新表并输出计划/对账（默认）")
    mode.add_argument("--execute", action="store_true", help="真正建表、写库并对账")
    args = parser.parse_args(argv)
    dry_run = not args.execute

    adapter = DBAdapter(DBConfig())
    if args.execute:
        _ensure_tables(adapter)

    with adapter.get_sync_session() as session:
        legacy = [_op_to_dict(op) for op in session.execute(select(LabelOp)).scalars().all()]
        plan = plan_legacy_ops_by_path(legacy)
        expected_day_labels = materialize_day_labels(plan["day_ops"])
        existing_point = _load_rows_if_table_exists(
            adapter, session, PointLabelOp, _POINT_OP_FIELDS
        )
        existing_day_ops = _load_rows_if_table_exists(
            adapter, session, DayLabelOp, _DAY_OP_FIELDS
        )
        existing_day_labels = _load_rows_if_table_exists(
            adapter, session, DayLabel, _DAY_LABEL_FIELDS
        )

        compare = compare_path_ledgers(
            legacy_ops=legacy,
            point_ops=existing_point,
            day_ops=existing_day_ops,
            day_labels=existing_day_labels,
        )
        report: Dict[str, Any] = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "dry_run": dry_run,
            "legacy_ops": len(legacy),
            "point_ops_to_copy": len(plan["point_ops"]),
            "day_ops_to_copy": len(plan["day_ops"]),
            "day_labels_to_upsert": len(expected_day_labels),
            "ambiguous_count": len(plan["ambiguous"]),
            "ambiguous": plan["ambiguous"],
            "existing_point_ops": len(existing_point),
            "existing_day_ops": len(existing_day_ops),
            "existing_day_labels": len(existing_day_labels),
            "compare": compare,
        }
        if plan["ambiguous"]:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            logger.error("存在无法判定的操作，拒绝写库")
            return 2

        if dry_run:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            logger.info("dry-run 完成，读取真实新表但未建表、未写库")
            return 0

        _upsert_rows(session, PointLabelOp, plan["point_ops"], _POINT_OP_FIELDS)
        _upsert_rows(session, DayLabelOp, plan["day_ops"], _DAY_OP_FIELDS)
        if expected_day_labels:
            now = datetime.utcnow()
            day_label_rows = [dict(row, updated_at=now) for row in expected_day_labels]
            statement = mysql_insert(DayLabel).values(day_label_rows)
            session.execute(statement.on_duplicate_key_update(
                label_id=statement.inserted.label_id,
                source=statement.inserted.source,
                op_id=statement.inserted.op_id,
                reviewer=statement.inserted.reviewer,
                label_space_version=statement.inserted.label_space_version,
                updated_at=statement.inserted.updated_at,
            ))

        copied_point = [
            _row_to_dict(row, _POINT_OP_FIELDS)
            for row in session.execute(select(PointLabelOp)).scalars().all()
        ]
        copied_day_ops = [
            _row_to_dict(row, _DAY_OP_FIELDS)
            for row in session.execute(select(DayLabelOp)).scalars().all()
        ]
        copied_day_labels = [
            _row_to_dict(row, _DAY_LABEL_FIELDS)
            for row in session.execute(select(DayLabel)).scalars().all()
        ]
        post_compare = compare_path_ledgers(
            legacy_ops=legacy,
            point_ops=copied_point,
            day_ops=copied_day_ops,
            day_labels=copied_day_labels,
        )
        report["compare"] = post_compare
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if not post_compare["passed"]:
            session.rollback()
            logger.error("双读对账失败，已回滚迁移 DML；DDL 不在回滚保证内")
            return 3
        session.commit()
        logger.info("隔离表拷贝完成并对账通过；旧 label_ops 保留只读")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
