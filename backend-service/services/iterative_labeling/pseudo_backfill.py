"""伪标签回流 MVP：高置信预测截断后写入 is_pseudo 记录（不自动进累计训练集）。"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PseudoBackfillService:
    def __init__(self, data_root: Optional[Path] = None):
        backend = Path(__file__).resolve().parents[2]
        self.data_root = Path(data_root) if data_root else backend / "data" / "iterative_labeling"

    def execute(
        self,
        *,
        slot: str,
        loop_id: str,
        prediction_batch_id: str,
        predictions: List[Dict[str, Any]],
        pseudo_label_threshold: float = 0.92,
        pseudo_label_max_ratio: float = 0.5,
    ) -> Dict[str, Any]:
        threshold = float(pseudo_label_threshold)
        max_ratio = max(0.0, min(1.0, float(pseudo_label_max_ratio)))

        candidates = []
        for row in predictions or []:
            conf = float(row.get("confidence") or 0.0)
            label = row.get("predicted_label")
            if label is None or conf < threshold:
                continue
            candidates.append(
                {
                    "unit_key": row.get("unit_key")
                    or f"{row.get('site_id')}|{row.get('device_id')}|{row.get('branch_id')}|{row.get('time_window')}",
                    "site_id": row.get("site_id"),
                    "device_id": row.get("device_id"),
                    "branch_id": row.get("branch_id"),
                    "time_window": row.get("time_window"),
                    "pseudo_label": int(label),
                    "confidence": conf,
                    "is_pseudo": True,
                }
            )

        candidates.sort(key=lambda r: (-float(r["confidence"]), str(r["unit_key"])))
        total = len(predictions or [])
        max_keep = int(total * max_ratio) if total else 0
        truncated = False
        selected = candidates
        if max_keep >= 0 and len(candidates) > max_keep:
            selected = candidates[:max_keep]
            truncated = True

        backfill_id = f"pseudo-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        out_dir = self.data_root / "pseudo_backfills" / slot
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "backfill_id": backfill_id,
            "loop_id": loop_id,
            "prediction_batch_id": prediction_batch_id,
            "pseudo_label_threshold": threshold,
            "pseudo_label_max_ratio": max_ratio,
            "candidate_count": len(candidates),
            "final_pseudo_count": len(selected),
            "truncated": truncated,
            "warnings": [] if selected else ["no_high_confidence_candidates"],
            "records": selected,
            "created_at": datetime.utcnow().isoformat(),
            "note": "MVP：伪标签仅落盘，不自动写入累计训练集；需人工确认后导入。",
        }
        path = out_dir / f"{backfill_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        project_root = self.data_root.parent.parent.parent  # AIP/
        try:
            rel = path.relative_to(project_root).as_posix()
        except ValueError:
            rel = path.as_posix()
        logger.info(
            "伪标签回流 %s：candidates=%s kept=%s truncated=%s",
            backfill_id,
            len(candidates),
            len(selected),
            truncated,
        )
        return {
            "backfill_id": backfill_id,
            "final_pseudo_count": len(selected),
            "truncated": truncated,
            "warnings": payload["warnings"],
            "artifact_path": rel,
        }
