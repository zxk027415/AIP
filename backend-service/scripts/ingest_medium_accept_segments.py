# @AI_GENERATED
# -*- coding: utf-8 -*-
"""写入已审过的中置信定位段（不放宽算法门槛）。

只吃两类 accept：
- medium_judged.csv 里 decision=accept（规则已判清晰）
- borderline_final.csv 里 final_decision=accept（人工/终审）

写成 cluster 故障段；与已有非 0 cluster 重叠则跳过。当天其余留给
backfill_cluster_day_rest.py 再补。

  python scripts/ingest_medium_accept_segments.py
  python scripts/ingest_medium_accept_segments.py --execute
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.models.pv_fault import LabelOp
from services.db.repositories.point_label import PointLabelRepository
from services.db.repositories.pv_fault import PVFaultRepository
from services.iterative_labeling.point_label_service import NORMAL_LABEL_ID, PointLabelService

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(name)s %(message)s")
logger = logging.getLogger("ingest_medium_accept")

BATCH_ID = "medium-accept-20260821"
SEG_DIR = BACKEND / "data" / "auto_located_segments"
Key = Tuple[str, str, str]


def _parse_ts(value: Any) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.to_pydatetime()


def _intervals_overlap(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> bool:
    return a0 < b1 and b0 < a1


def _load_accepts() -> pd.DataFrame:
    judged = pd.read_csv(SEG_DIR / "medium_judged.csv")
    borderline = pd.read_csv(SEG_DIR / "borderline_final.csv")
    clear = judged[judged["decision"] == "accept"].copy()
    final = borderline[borderline["final_decision"] == "accept"].copy()
    cols = ["site_id", "device_id", "branch_id", "date", "label", "t_start", "t_end", "mean_residual"]
    frames = []
    if not clear.empty:
        frames.append(clear[cols].assign(accept_from="medium_judged"))
    if not final.empty:
        frames.append(final[cols].assign(accept_from="borderline_final"))
    if not frames:
        return pd.DataFrame(columns=cols + ["accept_from"])
    out = pd.concat(frames, ignore_index=True)
    out["branch_id"] = out["branch_id"].astype(str)
    out["t_start"] = out["t_start"].map(_parse_ts)
    out["t_end"] = out["t_end"].map(_parse_ts)
    out["label"] = out["label"].astype(int)
    return out.drop_duplicates(subset=["site_id", "device_id", "branch_id", "t_start", "t_end"])


def _active_cluster_ops(adapter: DBAdapter) -> Dict[Key, List[LabelOp]]:
    with adapter.get_sync_session() as session:
        ops = session.execute(
            select(LabelOp).where(LabelOp.source == "cluster", LabelOp.status == "active")
        ).scalars().all()
    by_device: Dict[Key, List[LabelOp]] = {}
    for op in ops:
        key = (op.site_id, op.device_id, str(op.branch_id))
        by_device.setdefault(key, []).append(op)
    return by_device


def _plan(accepts: pd.DataFrame, existing: Dict[Key, List[LabelOp]]) -> Dict[str, Any]:
    to_write: List[Dict[str, Any]] = []
    skipped_overlap = 0
    skipped_duplicate = 0
    skipped_zero = 0
    for row in accepts.itertuples(index=False):
        if int(row.label) == NORMAL_LABEL_ID:
            skipped_zero += 1
            continue
        key = (str(row.site_id), str(row.device_id), str(row.branch_id))
        t_start, t_end = row.t_start, row.t_end
        overlap_fault = False
        duplicate = False
        for op in existing.get(key, []):
            if not _intervals_overlap(t_start, t_end, op.t_start, op.t_end):
                continue
            if (op.label_id or 0) == NORMAL_LABEL_ID:
                continue
            if op.t_start == t_start and op.t_end == t_end and int(op.label_id or -1) == int(row.label):
                duplicate = True
                break
            overlap_fault = True
            break
        if duplicate:
            skipped_duplicate += 1
            continue
        if overlap_fault:
            skipped_overlap += 1
            continue
        to_write.append({
            "site_id": key[0],
            "device_id": key[1],
            "branch_id": key[2],
            "t_start": t_start,
            "t_end": t_end,
            "label_id": int(row.label),
            "mean_residual": float(row.mean_residual),
            "accept_from": row.accept_from,
            "date": str(row.date),
        })
    return {
        "accept_rows": int(len(accepts)),
        "to_write": to_write,
        "skipped_overlap_fault": skipped_overlap,
        "skipped_duplicate": skipped_duplicate,
        "skipped_zero_label": skipped_zero,
        "new_device_days": len({(x["site_id"], x["device_id"], x["branch_id"], x["date"]) for x in to_write}),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="写入已审中置信 accept 段")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    accepts = _load_accepts()
    adapter = DBAdapter(DBConfig())
    plan = _plan(accepts, _active_cluster_ops(adapter))
    report = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "dry_run": not args.execute,
        "batch_id": BATCH_ID,
        "accept_rows": plan["accept_rows"],
        "to_write": len(plan["to_write"]),
        "new_device_days": plan["new_device_days"],
        "skipped_overlap_fault": plan["skipped_overlap_fault"],
        "skipped_duplicate": plan["skipped_duplicate"],
        "skipped_zero_label": plan["skipped_zero_label"],
        "label_counts": {},
        "sample": [
            {
                "site_id": item["site_id"],
                "device_id": item["device_id"],
                "date": item["date"],
                "label_id": item["label_id"],
                "t_start": item["t_start"].isoformat(),
                "t_end": item["t_end"].isoformat(),
                "accept_from": item["accept_from"],
            }
            for item in plan["to_write"][:8]
        ],
    }
    counts: Dict[int, int] = {}
    for item in plan["to_write"]:
        counts[item["label_id"]] = counts.get(item["label_id"], 0) + 1
    report["label_counts"] = {str(k): v for k, v in sorted(counts.items())}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.execute:
        logger.info("dry-run 完成，未写库")
        return 0

    service = PointLabelService(PointLabelRepository(adapter), PVFaultRepository(adapter))
    written = failed = 0
    errors: List[str] = []
    for item in plan["to_write"]:
        try:
            service.submit_op(
                site_id=item["site_id"],
                device_id=item["device_id"],
                branch_id=item["branch_id"],
                t_start=item["t_start"],
                t_end=item["t_end"],
                label_id=item["label_id"],
                source="cluster",
                reviewer="medium_accept_review",
                source_ref=f"peer_residual:medium_accept:{item['mean_residual']}",
                rest_of_day_policy="untouched",
                migration_batch_id=BATCH_ID,
            )
            written += 1
        except Exception as exc:
            failed += 1
            if len(errors) < 10:
                errors.append(f"{item['site_id']}/{item['device_id']}: {exc}")
    result = {"written": written, "failed": failed, "batch_id": BATCH_ID, "errors": errors}
    logger.info("中置信 accept 写入 written=%s failed=%s", written, failed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
