"""Admit day-path full labels + point-path K4 POC snapshot into cumulative ledgers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.slot_datasets.gold_bootstrap import admit_gold_bases


def _summarize(result: dict) -> dict:
    out = {"exported": result.get("exported")}
    ledgers = result.get("ledgers") or {}
    out["ledgers"] = {}
    for slot, ledger in ledgers.items():
        latest = ledger.get("latest_freeze") or {}
        out["ledgers"][slot] = {
            "event_count": ledger.get("event_count"),
            "latest_freeze_version": latest.get("snapshot_version"),
            "artifact_ref": latest.get("artifact_ref"),
            "included_labeled_version_ids": latest.get("included_labeled_version_ids"),
        }
    return out


def main() -> None:
    result = admit_gold_bases()
    print(json.dumps(_summarize(result), ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
