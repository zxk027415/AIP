# @AI_GENERATED
# -*- coding: utf-8 -*-
"""把已有 cluster 故障段所在日的空洞补成 cluster + 0（当天其余正常）。

不新增 source。已有 normal_complement 占用的时段会跳过，只补夜里和没标到的缝。

  python scripts/backfill_cluster_day_rest.py
  python scripts/backfill_cluster_day_rest.py --execute
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import select

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.models.pv_fault import LabelOp
from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.day_split_complements import complement_intervals
from services.iterative_labeling.point_label_service import NORMAL_LABEL_ID, PointLabelService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s %(message)s")
logger = logging.getLogger("backfill_cluster_day_rest")

BATCH_ID = "cluster-day-rest-20260821"
Key = Tuple[str, str, str, datetime]


def _midnight(ts: datetime) -> datetime:
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="补 cluster 当天其余为 label_id=0")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    adapter = DBAdapter(DBConfig())
    service = PointLabelService(PointLabelRepository(adapter), PVFaultRepository(adapter))
    with adapter.get_sync_session() as session:
        ops = session.execute(
            select(LabelOp).where(LabelOp.source == "cluster", LabelOp.status == "active")
        ).scalars().all()

    by_day: Dict[Key, List[LabelOp]] = defaultdict(list)
    for op in ops:
        by_day[(op.site_id, op.device_id, str(op.branch_id), _midnight(op.t_start))].append(op)

    planned = []
    skipped_no_fault = 0
    for key, day_ops in sorted(by_day.items()):
        if not any((op.label_id or 0) != NORMAL_LABEL_ID for op in day_ops):
            skipped_no_fault += 1
            continue
        occupied = [(op.t_start, op.t_end) for op in day_ops]
        day = key[3]
        holes = complement_intervals(day, day + timedelta(days=1), occupied)
        if holes:
            planned.append({"key": key, "holes": holes, "existing_ops": len(day_ops)})

    report = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "dry_run": not args.execute,
        "batch_id": BATCH_ID,
        "cluster_device_days": len(by_day),
        "days_needing_rest": len(planned),
        "rest_intervals": sum(len(item["holes"]) for item in planned),
        "skipped_no_fault": skipped_no_fault,
        "sample": [
            {
                "site_id": item["key"][0],
                "device_id": item["key"][1],
                "date": item["key"][3].date().isoformat(),
                "holes": [(a.isoformat(), b.isoformat()) for a, b in item["holes"]],
            }
            for item in planned[:5]
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.execute:
        logger.info("dry-run 完成，未写库")
        return 0

    written = 0
    for item in planned:
        site_id, device_id, branch_id, day = item["key"]
        for t_start, t_end in item["holes"]:
            service.submit_op(
                site_id=site_id,
                device_id=device_id,
                branch_id=branch_id,
                t_start=t_start,
                t_end=t_end,
                label_id=NORMAL_LABEL_ID,
                source="cluster",
                reviewer="auto_locate_script",
                source_ref="peer_residual:day_rest",
                rest_of_day_policy="untouched",
                migration_batch_id=BATCH_ID,
            )
            written += 1
    logger.info("已写入 cluster+0 其余区间 %s 条", written)
    print(json.dumps({"written": written, "batch_id": BATCH_ID}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
