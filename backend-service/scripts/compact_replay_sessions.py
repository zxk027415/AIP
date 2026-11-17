#!/usr/bin/env python
"""One-off: compact replay session JSON (drop inlined source_rows when profile-bound)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SESSION_ROOT = BACKEND / "data" / "timeseries_point" / "replay_sessions"


def compact(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    before = path.stat().st_size
    if payload.get("dataset_profile_id"):
        payload["source_rows"] = []
    payload["committed_history"] = []
    outcomes = payload.get("outcomes")
    if isinstance(outcomes, list) and len(outcomes) > 64:
        payload["outcomes"] = outcomes[-64:]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    after = path.stat().st_size
    return {
        "session_id": payload.get("session_id", path.stem),
        "before_bytes": before,
        "after_bytes": after,
    }


def main() -> int:
    targets = sorted(SESSION_ROOT.glob("*.json"))
    if not targets:
        print("no replay sessions")
        return 0
    for path in targets:
        result = compact(path)
        print(
            f"{result['session_id']}: {result['before_bytes']} -> {result['after_bytes']} bytes"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
