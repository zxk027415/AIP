"""Pending real-point feed queue — alternative to file replay (G12.2)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_FEED_ROOT = _BACKEND_DIR / "data" / "timeseries_point" / "pending_feed"
_LOCK = threading.Lock()


def _feed_path(slot: str) -> Path:
    safe = str(slot or "").strip().replace("/", "_")
    return _FEED_ROOT / f"{safe}.json"


def _load(slot: str) -> dict[str, Any]:
    path = _feed_path(slot)
    if not path.is_file():
        return {"slot": slot, "points": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"slot": slot, "points": []}
    payload.setdefault("slot", slot)
    payload.setdefault("points", [])
    return payload


def _save(slot: str, payload: dict[str, Any]) -> None:
    _FEED_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = _feed_path(slot).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_feed_path(slot))


def enqueue_pending_point(slot: str, point: dict[str, Any]) -> dict[str, Any]:
    """Append one unprocessed real point for a slot (entity-time stable order enforced by caller)."""
    with _LOCK:
        payload = _load(slot)
        points = list(payload.get("points") or [])
        point_id = str(point.get("point_id") or f"pt-{len(points)+1}")
        entry = dict(point)
        entry["point_id"] = point_id
        entry.setdefault("status", "pending")
        points.append(entry)
        payload["points"] = points
        _save(slot, payload)
    return entry


def list_pending_points(
    slot: str,
    *,
    entity_key: Optional[str] = None,
    limit: int = 32,
) -> list[dict[str, Any]]:
    payload = _load(slot)
    pending = [
        item
        for item in (payload.get("points") or [])
        if isinstance(item, dict) and str(item.get("status") or "pending") == "pending"
    ]
    if entity_key is not None:
        pending = [item for item in pending if str(item.get("entity_key") or "") == entity_key]
    return pending[: max(1, min(limit, 256))]


def mark_processed(slot: str, point_id: str) -> bool:
    with _LOCK:
        payload = _load(slot)
        changed = False
        for item in payload.get("points") or []:
            if isinstance(item, dict) and str(item.get("point_id")) == str(point_id):
                item["status"] = "processed"
                changed = True
        if changed:
            _save(slot, payload)
        return changed


def pending_summary(slot: str) -> dict[str, Any]:
    payload = _load(slot)
    points = [item for item in (payload.get("points") or []) if isinstance(item, dict)]
    pending = [item for item in points if str(item.get("status") or "pending") == "pending"]
    return {
        "slot": slot,
        "total": len(points),
        "pending": len(pending),
        "processed": len(points) - len(pending),
    }
