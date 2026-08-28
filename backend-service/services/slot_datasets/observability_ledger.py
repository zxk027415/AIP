"""Per-slot observability ledger for pv_day / pv_point calendars (relative paths only)."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services.slot_datasets.errors import SlotDatasetError

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALLOWED_SLOTS = frozenset({"pv_day", "pv_point"})
EXPECTED_POINTS = 288
OCCUPANCY_READY = 173
HOLD_DAYS = 3
DAY_SOURCE_REL = "../fault-diag-algo-release-3.1/enos_fault_diag/test/predict_small.parquet"
GOLD_REL = {
    "pv_day": "data/slot_datasets/pv_day/gold/all_labeled_combined.parquet",
    "pv_point": "data/slot_datasets/pv_point/gold/point-poc-k4-labeled.parquet",
}
MAX_CALENDAR_DAYS = 30
MAX_DEVICE_ROWS = 50


def _assert_slot(slot: str) -> str:
    key = str(slot or "").strip()
    if key not in _ALLOWED_SLOTS:
        raise SlotDatasetError("invalid_slot", f"slot must be one of {sorted(_ALLOWED_SLOTS)!r}")
    return key


def _ledger_path(slot: str) -> Path:
    return _BACKEND_DIR / "data" / "slot_datasets" / slot / "observability" / "ledger.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _empty_ledger(slot: str) -> dict[str, Any]:
    return {
        "slot": slot,
        "watermark_day": None,
        "occupancy_ready": OCCUPANCY_READY,
        "expected_points": EXPECTED_POINTS,
        "hold_days": HOLD_DAYS,
        "cells": {},
        "audits": [],
        "updated_at": _now_iso(),
    }


def load_ledger(slot: str) -> dict[str, Any]:
    key = _assert_slot(slot)
    path = _ledger_path(key)
    if not path.is_file():
        return _empty_ledger(key)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return _empty_ledger(key)
    payload.setdefault("slot", key)
    payload.setdefault("cells", {})
    payload.setdefault("audits", [])
    payload.setdefault("occupancy_ready", OCCUPANCY_READY)
    payload.setdefault("expected_points", EXPECTED_POINTS)
    payload.setdefault("hold_days", HOLD_DAYS)
    return payload


def save_ledger(slot: str, payload: dict[str, Any]) -> dict[str, Any]:
    key = _assert_slot(slot)
    path = _ledger_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["slot"] = key
    payload["updated_at"] = _now_iso()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _resolve_source_path(rel: str) -> Path:
    text = str(rel or "").replace("\\", "/")
    if text.startswith("../"):
        return (_BACKEND_DIR / text).resolve()
    return _BACKEND_DIR / text


def _read_source_frame(slot: str) -> pd.DataFrame:
    candidates = [DAY_SOURCE_REL if slot == "pv_day" else GOLD_REL[slot], GOLD_REL[slot]]
    for rel in candidates:
        path = _resolve_source_path(rel)
        if not path.is_file():
            continue
        if path.suffix.lower() == ".parquet":
            frame = pd.read_parquet(path)
        else:
            frame = pd.read_csv(path, encoding="utf-8")
        if frame is not None and not frame.empty:
            return frame
    raise SlotDatasetError("source_not_found", f"no observability source for {slot}")


def _device_key(row: pd.Series) -> str:
    return "|".join(str(row.get(col, "")) for col in ("site_id", "device_id", "branch_id"))


def _row_date(row: pd.Series) -> str:
    if "date" in row.index and pd.notna(row.get("date")):
        return str(row.get("date"))[:10]
    for col in ("time", "event_time", "data_date"):
        if col in row.index and pd.notna(row.get(col)):
            stamp = pd.to_datetime(row.get(col), errors="coerce")
            if pd.notna(stamp):
                return stamp.strftime("%Y-%m-%d")
    return ""


def occupancy_by_device_day(slot: str, day_from: str, day_to: str) -> dict[str, dict[str, int]]:
    frame = _read_source_frame(slot).copy()
    if "date" in frame.columns:
        day_series = frame["date"].astype(str).str.slice(0, 10)
    else:
        time_col = next((c for c in ("time", "event_time", "data_date") if c in frame.columns), None)
        if time_col is None:
            return {}
        day_series = pd.to_datetime(frame[time_col], errors="coerce").dt.strftime("%Y-%m-%d")
    parts = []
    for col in ("site_id", "device_id", "branch_id"):
        if col in frame.columns:
            parts.append(frame[col].astype(str))
        else:
            parts.append(pd.Series([""] * len(frame), index=frame.index))
    device = parts[0]
    for part in parts[1:]:
        device = device + "|" + part
    work = pd.DataFrame({"device": device, "day": day_series})
    work = work[(work["day"] >= day_from) & (work["day"] <= day_to)]
    grouped = work.groupby(["device", "day"], dropna=False).size()
    counts: dict[str, dict[str, int]] = {}
    for (device_key, day), count in grouped.items():
        counts.setdefault(str(device_key), {})[str(day)] = int(count)
    return counts


def _cell_key(device: str, day: str) -> str:
    return f"{device}|{day}"


def _parse_day(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def advance_watermark_day(slot: str, *, operator: str = "ui") -> dict[str, Any]:
    key = _assert_slot(slot)
    if key != "pv_day":
        raise SlotDatasetError("invalid_slot", "advance-day is only for pv_day")
    ledger = load_ledger(key)
    current = ledger.get("watermark_day")
    if not current:
        counts = occupancy_by_device_day(key, "1970-01-01", "9999-12-31")
        days = sorted({day for per in counts.values() for day in per})
        ledger["watermark_day"] = days[0] if days else datetime.now().strftime("%Y-%m-%d")
    else:
        ledger["watermark_day"] = (_parse_day(str(current)) + timedelta(days=1)).isoformat()
    ledger.setdefault("audits", []).append(
        {
            "action": "advance_day",
            "operator": operator,
            "watermark_day": ledger["watermark_day"],
            "at": _now_iso(),
        }
    )
    return save_ledger(key, ledger)


def prepare_day_detect_batch(slot: str = "pv_day") -> dict[str, Any]:
    """Filter current watermark day to occupancy-ready devices before predict."""
    key = _assert_slot(slot)
    if key != "pv_day":
        raise SlotDatasetError("invalid_slot", "day detect gate is only for pv_day")
    ledger = load_ledger(key)
    if not ledger.get("watermark_day"):
        ledger = advance_watermark_day(key, operator="scheduler")
    day = str(ledger["watermark_day"])
    occupancy = occupancy_by_device_day(key, day, day)
    ready: list[str] = []
    waiting: list[str] = []
    skipped: list[str] = []
    cells = dict(ledger.get("cells") or {})
    for device, per_day in occupancy.items():
        arrived = int(per_day.get(day, 0))
        ck = _cell_key(device, day)
        cell = dict(cells.get(ck) or {"device_key": device, "date": day})
        previous_arrived = int(cell.get("arrived_count") or 0)
        cell["arrived_count"] = arrived
        cell["expected_count"] = EXPECTED_POINTS
        cell["completeness"] = round(arrived / EXPECTED_POINTS, 4) if EXPECTED_POINTS else 0
        if cell.get("status") in {"detected", "skipped"} and arrived > previous_arrived:
            cell["late_arrival"] = True
        if cell.get("status") == "detected":
            cells[ck] = cell
            continue
        if arrived >= OCCUPANCY_READY:
            cell["status"] = "ready"
            cell["skip_reason"] = None
            ready.append(device)
        else:
            wait_from = cell.get("wait_started_on") or day
            cell["wait_started_on"] = wait_from
            waited = (_parse_day(day) - _parse_day(str(wait_from))).days
            if waited >= HOLD_DAYS:
                cell["status"] = "skipped"
                cell["skip_reason"] = "expired_incomplete"
                skipped.append(device)
            else:
                cell["status"] = "waiting"
                cell["skip_reason"] = "incomplete"
                waiting.append(device)
        cells[ck] = cell
    ledger["cells"] = cells
    save_ledger(key, ledger)

    filtered_rel = None
    if ready:
        frame = _read_source_frame(key)
        device = (
            frame.get("site_id", "").astype(str)
            + "|"
            + frame.get("device_id", "").astype(str)
            + "|"
            + frame.get("branch_id", "").astype(str)
        )
        if "date" in frame.columns:
            day_series = frame["date"].astype(str).str.slice(0, 10)
        else:
            time_col = next((c for c in ("time", "event_time", "data_date") if c in frame.columns), None)
            day_series = pd.to_datetime(frame[time_col], errors="coerce").dt.strftime("%Y-%m-%d")
        out = frame[(day_series == day) & device.isin(set(ready))].copy()
        rel = f"data/slot_datasets/{key}/observability/detect_batch_{day}.parquet"
        abs_path = _BACKEND_DIR / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(abs_path, index=False)
        filtered_rel = rel.replace("\\", "/")

    return {
        "slot": key,
        "watermark_day": day,
        "ready_devices": ready,
        "waiting_devices": waiting,
        "skipped_devices": skipped,
        "input_file_path": filtered_rel,
        "occupancy_ready": OCCUPANCY_READY,
        "expected_points": EXPECTED_POINTS,
    }


def calendar_grid(slot: str, day_from: str, day_to: str, *, page: int = 1) -> dict[str, Any]:
    key = _assert_slot(slot)
    start = str(day_from or "")[:10]
    end = str(day_to or "")[:10]
    if not start or not end:
        raise SlotDatasetError("invalid_range", "from and to dates are required")
    if (_parse_day(end) - _parse_day(start)).days + 1 > MAX_CALENDAR_DAYS:
        raise SlotDatasetError("range_too_long", f"calendar range cannot exceed {MAX_CALENDAR_DAYS} days")
    occupancy = occupancy_by_device_day(key, start, end)
    ledger = load_ledger(key)
    cells = ledger.get("cells") or {}
    devices = sorted(occupancy.keys())
    page = max(1, int(page or 1))
    start_idx = (page - 1) * MAX_DEVICE_ROWS
    page_devices = devices[start_idx: start_idx + MAX_DEVICE_ROWS]
    days: list[str] = []
    cursor = _parse_day(start)
    last = _parse_day(end)
    while cursor <= last:
        days.append(cursor.isoformat())
        cursor += timedelta(days=1)
    grid = []
    for device in page_devices:
        row_cells = []
        for day in days:
            arrived = int((occupancy.get(device) or {}).get(day, 0))
            stored = dict(cells.get(_cell_key(device, day)) or {})
            status = stored.get("status")
            if not status:
                if arrived <= 0:
                    status = "empty"
                elif arrived >= OCCUPANCY_READY or key == "pv_point":
                    status = "arrived"
                else:
                    status = "waiting"
            row_cells.append(
                {
                    "date": day,
                    "arrived_count": stored.get("arrived_count", arrived),
                    "expected_count": stored.get("expected_count", EXPECTED_POINTS if key == "pv_day" else arrived),
                    "completeness": stored.get("completeness")
                    or (round(arrived / EXPECTED_POINTS, 4) if key == "pv_day" and EXPECTED_POINTS else None),
                    "status": status,
                    "model_id": stored.get("model_id"),
                    "skip_reason": stored.get("skip_reason"),
                    "late_arrival": bool(stored.get("late_arrival")),
                }
            )
        parts = device.split("|")
        grid.append(
            {
                "device_key": device,
                "site_id": parts[0] if parts else "",
                "device_id": parts[1] if len(parts) > 1 else "",
                "branch_id": parts[2] if len(parts) > 2 else "",
                "cells": row_cells,
            }
        )
    return {
        "slot": key,
        "from": start,
        "to": end,
        "watermark_day": ledger.get("watermark_day"),
        "occupancy_ready": OCCUPANCY_READY,
        "expected_points": EXPECTED_POINTS,
        "page": page,
        "page_size": MAX_DEVICE_ROWS,
        "device_total": len(devices),
        "days": days,
        "rows": grid,
    }


def curve_for_device(slot: str, device_key: str, day_from: str, day_to: str) -> dict[str, Any]:
    key = _assert_slot(slot)
    frame = _read_source_frame(key)
    points: list[dict[str, Any]] = []
    value_col = next((c for c in ("i_cal", "value", "current", "power") if c in frame.columns), None)
    time_col = next((c for c in ("time", "event_time", "data_date") if c in frame.columns), None)
    kept = 0
    for _, row in frame.iterrows():
        if _device_key(row) != device_key:
            continue
        day = _row_date(row)
        if day < day_from or day > day_to:
            continue
        kept += 1
        if kept % max(1, 1) != 0 and len(points) > 400:
            continue
        points.append(
            {
                "time": str(row.get(time_col) if time_col else day),
                "value": None if value_col is None or pd.isna(row.get(value_col)) else float(row.get(value_col)),
                "label": None if "label" not in row.index or pd.isna(row.get("label")) else row.get("label"),
            }
        )
        if len(points) >= 800:
            break
    return {
        "slot": key,
        "device_key": device_key,
        "from": day_from,
        "to": day_to,
        "points": points,
        "downsampled": True,
    }


def mark_devices_detected(slot: str, devices: list[str], *, day: str, model_id: Optional[str] = None) -> None:
    ledger = load_ledger(slot)
    for device in devices:
        ck = _cell_key(device, day)
        cell = dict((ledger.get("cells") or {}).get(ck) or {"device_key": device, "date": day})
        cell["status"] = "detected"
        cell["model_id"] = model_id
        cell["detected_at"] = _now_iso()
        ledger.setdefault("cells", {})[ck] = cell
    save_ledger(slot, ledger)


def record_manual_detect(
    slot: str,
    *,
    device_key: str,
    day: Optional[str] = None,
    operator: str = "ui",
    reason: str = "manual",
    model_id: Optional[str] = None,
) -> dict[str, Any]:
    key = _assert_slot(slot)
    ledger = load_ledger(key)
    target_day = str(day or ledger.get("watermark_day") or datetime.now().strftime("%Y-%m-%d"))[:10]
    ck = _cell_key(device_key, target_day)
    cell = dict((ledger.get("cells") or {}).get(ck) or {"device_key": device_key, "date": target_day})
    cell["status"] = "detected"
    cell["skip_reason"] = None
    cell["model_id"] = model_id
    cell["detected_at"] = _now_iso()
    cell["manual"] = True
    ledger.setdefault("cells", {})[ck] = cell
    ledger.setdefault("audits", []).append(
        {
            "action": "manual_detect",
            "operator": operator,
            "reason": reason,
            "device_key": device_key,
            "date": target_day,
            "at": _now_iso(),
        }
    )
    save_ledger(key, ledger)
    return {"ok": True, "cell": cell}
