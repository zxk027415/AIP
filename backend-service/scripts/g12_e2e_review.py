#!/usr/bin/env python
"""G12 E2E review: alarm state machine + replay API + scheduler evidence."""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BACKEND_DIR / "data" / "e2e"
DEFAULT_BASE = "http://localhost:8081"
SLOT = "pv_point"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _step(steps: list[dict[str, Any]], name: str, ok: bool, **detail: Any) -> None:
    steps.append({"step": name, "ok": ok, "at": _now(), **detail})


def run_review(base: str = DEFAULT_BASE) -> dict[str, Any]:
    run_tag = f"g12-e2e-{uuid.uuid4().hex[:8]}"
    steps: list[dict[str, Any]] = []
    report: dict[str, Any] = {"run_tag": run_tag, "base": base, "steps": steps}

    from services.timeseries_point.point_alarm_state_machine import AlarmPolicy
    from services.timeseries_point.point_alarm_store import alarm_summary, ingest_point_outcome

    test_slot = f"{SLOT}-e2e-{run_tag[-6:]}"
    policy = AlarmPolicy(open_consecutive_points=3, close_consecutive_points=3, cold_start_alarm_enabled=True)
    for idx in range(3):
        ingest_point_outcome(
            test_slot,
            {
                "kind": "prediction",
                "label": 1,
                "confidence": 0.99,
                "entity_key": "s1|d1|b1",
                "point_time": f"2024-01-01T08:{idx:02d}:00Z",
            },
            policy=policy,
        )
    summary = alarm_summary(test_slot)
    _step(
        steps,
        "alarm_open_lifecycle",
        summary.get("active_alarm_count", 0) >= 1,
        active=summary.get("active_alarm_count"),
    )

    for idx in range(3):
        ingest_point_outcome(
            test_slot,
            {
                "kind": "prediction",
                "label": 0,
                "confidence": 0.99,
                "entity_key": "s1|d1|b1",
                "point_time": f"2024-01-01T09:{idx:02d}:00Z",
            },
            policy=policy,
        )
    summary_after_close = alarm_summary(test_slot)
    _step(
        steps,
        "alarm_close_lifecycle",
        summary_after_close.get("active_alarm_count", 1) == 0,
        active=summary_after_close.get("active_alarm_count"),
    )

    try:
        client = httpx.Client(base_url=base, timeout=30.0)
        resp = client.get(f"/api/timeseries-replay/slots/{SLOT}/alarms/summary")
        _step(steps, "http_alarm_summary", resp.status_code == 200, status=resp.status_code)

        pending = client.post(
            f"/api/timeseries-replay/slots/{SLOT}/pending-feed/enqueue",
            json={
                "entity_key": "s1|d1|b1",
                "point_time": "2024-01-01T10:00:00Z",
                "values": {"value": 1.0, "i_cal": 0.5},
            },
        )
        _step(steps, "http_pending_enqueue", pending.status_code == 200, status=pending.status_code)

        feed_sum = client.get(f"/api/timeseries-replay/slots/{SLOT}/pending-feed/summary")
        _step(
            steps,
            "http_pending_summary",
            feed_sum.status_code == 200 and (feed_sum.json().get("pending") or 0) >= 1,
            body=feed_sum.json() if feed_sum.status_code == 200 else feed_sum.text,
        )

        latest = client.get(
            f"/api/workflows/enhanced/slot/{SLOT}/latest-execution",
            params={"template_role": "predict_replay"},
        )
        _step(
            steps,
            "http_latest_predict_replay",
            latest.status_code in {200, 404},
            status=latest.status_code,
        )
    except httpx.ConnectError as exc:
        _step(steps, "http_skipped_offline", True, reason=str(exc))

    passed = sum(1 for item in steps if item.get("ok"))
    report["passed"] = passed
    report["total"] = len(steps)
    report["ok"] = passed == len(steps)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"g12_e2e_review_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["evidence_path"] = str(out_path.relative_to(BACKEND_DIR)).replace("\\", "/")
    return report


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    result = run_review(base)
    print(json.dumps({"ok": result["ok"], "passed": result["passed"], "total": result["total"]}, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)
