# @AI_GENERATED
# -*- coding: utf-8 -*-
"""把历史 K4 companion 的 source 从 human_day 改成 point_rest_normal。

默认 dry-run。真正写入需要 --execute。
无法判定的记录只进入失败明细，不会被改写。

PowerShell：
  python scripts/migrate_k4_point_rest_normal.py
  python scripts/migrate_k4_point_rest_normal.py --execute
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import select, update

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.models.pv_fault import LabelOp, PointLabel
from services.iterative_labeling.k4_companion_migration import plan_k4_companion_source_rewrite
from services.iterative_labeling.point_label_service import K4_COMPANION_SOURCE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s %(message)s")
logger = logging.getLogger("migrate_k4_point_rest_normal")


def _op_to_dict(op: LabelOp) -> Dict[str, Any]:
    return {
        "op_id": op.op_id,
        "source": op.source,
        "parent_op_id": op.parent_op_id,
        "rest_of_day_policy": op.rest_of_day_policy,
        "label_id": op.label_id,
        "status": op.status,
        "t_start": op.t_start,
        "t_end": op.t_end,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="迁移 K4 companion 来源")
    parser.add_argument("--execute", action="store_true", help="真正写库；默认只打印计划")
    args = parser.parse_args(argv)

    adapter = DBAdapter(DBConfig())
    with adapter.get_sync_session() as session:
        ops = session.execute(select(LabelOp).where(LabelOp.source == "human_day")).scalars().all()
        plan = plan_k4_companion_source_rewrite(_op_to_dict(op) for op in ops)
        report = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "dry_run": not args.execute,
            "human_day_ops_scanned": len(ops),
            "migrate_count": len(plan["migrate_to_point_rest_normal"]),
            "keep_human_day_count": len(plan["keep_human_day"]),
            "ambiguous_count": len(plan["ambiguous"]),
            "ambiguous": plan["ambiguous"],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        if plan["ambiguous"]:
            logger.error("存在无法判定的 human_day，拒绝执行写库")
            return 2
        if not args.execute:
            logger.info("dry-run 完成，未写库")
            return 0

        migrate_ids = [item["op_id"] for item in plan["migrate_to_point_rest_normal"]]
        if not migrate_ids:
            logger.info("没有需要改写的 K4 companion")
            return 0
        op_result = session.execute(
            update(LabelOp)
            .where(LabelOp.op_id.in_(migrate_ids), LabelOp.source == "human_day")
            .values(source=K4_COMPANION_SOURCE, updated_at=datetime.utcnow())
        )
        point_result = session.execute(
            update(PointLabel)
            .where(PointLabel.op_id.in_(migrate_ids), PointLabel.source == "human_day")
            .values(source=K4_COMPANION_SOURCE, updated_at=datetime.utcnow())
        )
        session.commit()
        logger.info(
            "已改写 label_ops=%s point_labels=%s",
            op_result.rowcount,
            point_result.rowcount,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
