# @AI_GENERATED: per-slot observability includes pv_tsc as an isolated read-only daily calendar.
"""Per-slot observability ledger for pv_day, pv_point, and pv_tsc (relative paths only)."""
# @AI_GENERATED: end

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services.slot_datasets.errors import SlotDatasetError

_BACKEND_DIR = Path(__file__).resolve().parents[2]
# @AI_GENERATED: pv_tsc 复用日级原始观测语义，但保持独立 ledger；demo 写链仍只允许原双槽。
_DAILY_SLOTS = frozenset({"pv_day", "pv_tsc"})
_ALLOWED_SLOTS = frozenset({"pv_day", "pv_point", "pv_tsc"})
_DEMO_WRITE_SLOTS = frozenset({"pv_day", "pv_point"})
# @AI_GENERATED: end
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
    # @AI_GENERATED: TSC 复用日级原始序列做只读占用率观测，不复用 pv_day ledger/游标。
    candidates = (
        [DAY_SOURCE_REL, GOLD_REL["pv_day"]]
        if slot in _DAILY_SLOTS
        else [GOLD_REL[slot]]
    )
    # @AI_GENERATED: end
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


def _read_calendar_frame(slot: str) -> pd.DataFrame:
    """Product calendar prefers loop_demo arrived rows so unfed days stay empty."""
    try:
        from services.slot_datasets.loop_demo import arrived_frame, load_cursor

        cursor_path = _BACKEND_DIR / "data" / "slot_datasets" / slot / "loop_demo" / "feed_cursor.json"
        arrived_path = _BACKEND_DIR / "data" / "slot_datasets" / slot / "loop_demo" / "arrived.parquet"
        if arrived_path.is_file() or cursor_path.is_file():
            arrived = arrived_frame(slot, backend_dir=_BACKEND_DIR)
            if arrived is not None and not arrived.empty:
                return arrived
            return pd.DataFrame(columns=["site_id", "device_id", "branch_id", "time", "date", "i_cal"])
    except SlotDatasetError:
        pass
    return _read_source_frame(slot)


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


def _occupancy_from_frame(frame: pd.DataFrame, day_from: str, day_to: str) -> dict[str, dict[str, int]]:
    if frame is None or frame.empty:
        return {}
    work_frame = frame.copy()
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


def _expire_waiting_cells(cells: dict[str, Any], as_of: date) -> list[str]:
    """Mark waiting device-days skipped when watermark - wait_started_on >= HOLD_DAYS."""
    skipped: list[str] = []
    for cell in cells.values():
        if not isinstance(cell, dict) or cell.get("status") != "waiting":
            continue
        wait_from = cell.get("wait_started_on")
        if not wait_from:
            continue
        waited = (as_of - _parse_day(str(wait_from))).days
        if waited >= HOLD_DAYS:
            cell["status"] = "skipped"
            cell["skip_reason"] = "expired_incomplete"
            skipped.append(str(cell.get("device_key") or ""))
    return skipped


def occupancy_by_device_day(slot: str, day_from: str, day_to: str) -> dict[str, dict[str, int]]:
    return _occupancy_from_frame(_read_calendar_frame(slot), day_from, day_to)


def _cell_key(device: str, day: str) -> str:
    return f"{device}|{day}"


def _parse_day(value: str) -> date:
    return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()


def _latest_source_day(slot: str) -> Optional[date]:
    frame = _read_source_frame(slot)
    if "date" in frame.columns:
        series = pd.to_datetime(frame["date"], errors="coerce")
    else:
        time_col = next((c for c in ("time", "event_time", "data_date") if c in frame.columns), None)
        if time_col is None:
            return None
        series = pd.to_datetime(frame[time_col], errors="coerce")
    if series.notna().any():
        stamp = series.max()
        if getattr(stamp, "tzinfo", None) is not None:
            stamp = stamp.tz_convert("UTC")
        return stamp.date()
    return None


def anchor_calendar_day(slot: str) -> date:
    """Detect watermark first; never fall back to the machine clock."""
    key = _assert_slot(slot)
    raw = str((load_ledger(key).get("watermark_day") or "")).strip()[:10]
    if raw:
        try:
            return _parse_day(raw)
        except ValueError:
            pass
    latest = _latest_source_day(key)
    if latest is not None:
        return latest
    raise SlotDatasetError("no_calendar_anchor", f"{key} 没有检测水位，源数据也没有业务日")


# @AI_GENERATED: pv_tsc 是真实日级源的只读观测槽，不创建双槽 loop_demo 产物。
def _readonly_tsc_status(slot: str) -> dict[str, Any]:
    key = _assert_slot(slot)
    ledger = load_ledger(key)
    anchor: Optional[date]
    try:
        anchor = anchor_calendar_day(key)
    except SlotDatasetError:
        anchor = None
    end = anchor.isoformat() if anchor else None
    start = (anchor - timedelta(days=6)).isoformat() if anchor else None
    return {
        "slot": key,
        "demo": False,
        "readonly": True,
        "clock": {
            "kind": "business_day",
            "day": end,
            "timestamp": None,
            "source": (
                "ledger"
                if ledger.get("watermark_day")
                else "source_data"
                if anchor is not None
                else None
            ),
        },
        "progress": {
            "day_index": 0,
            "total_days": None,
            "fed_days": [],
            "exhausted": False,
        },
        "window": {"from": start, "to": end},
        "accuracy": None,
        "note": "pv_tsc 使用独立真实调度回执；观测日历只读，不推进 demo 水位",
    }


def default_calendar_range(slot: str, *, span_days: int = 6) -> tuple[str, str]:
    key = _assert_slot(slot)
    if key == "pv_tsc":
        end = anchor_calendar_day(key)
        start = end - timedelta(days=max(0, int(span_days)))
        return start.isoformat(), end.isoformat()
    try:
        from services.slot_datasets.loop_demo import DEMO_START, demo_status

        status = demo_status(key, backend_dir=_BACKEND_DIR, create=False)
        window = status.get("window") or {}
        if status.get("demo") and window.get("from") and window.get("to"):
            return str(window["from"])[:10], str(window["to"])[:10]
        if not status.get("demo"):
            try:
                end = anchor_calendar_day(key)
                start = end - timedelta(days=max(0, int(span_days)))
                return start.isoformat(), end.isoformat()
            except SlotDatasetError:
                return DEMO_START, DEMO_START
    except SlotDatasetError:
        pass
    end = anchor_calendar_day(key)
    start = end - timedelta(days=max(0, int(span_days)))
    return start.isoformat(), end.isoformat()


def observability_status(slot: str) -> dict[str, Any]:
    key = _assert_slot(slot)
    if key == "pv_tsc":
        status = _readonly_tsc_status(key)
        from services.slot_datasets.loop_demo import demo_status

        # 独立回放进度：给前端 demo 卡片用，不覆盖生产只读 clock。
        status["demo_replay"] = demo_status(key, backend_dir=_BACKEND_DIR, create=False)
    else:
        from services.slot_datasets.loop_demo import demo_status

        status = demo_status(key, backend_dir=_BACKEND_DIR, create=True)
        # 日/点路径的回放进度就是顶层 status 自身。这里必须放**浅拷贝**：
        # 直接写 status["demo_replay"] = status 会让 dict 自引用，FastAPI
        # jsonable_encoder 递归爆栈，GET /observability/status?slot=pv_day|pv_point 直接 500。
        status["demo_replay"] = dict(status)
    status["occupancy_ready"] = OCCUPANCY_READY
    status["expected_points"] = EXPECTED_POINTS
    if key == "pv_point":
        status["replay"] = _replay_observatory_status()
    return status
# @AI_GENERATED: end


def _replay_observatory_status() -> dict[str, Any]:
    try:
        from services.timeseries_point.replay_activity import load_session

        sess = load_session("sched-pv_point-default")
        last_time = None
        last_entity = None
        for item in reversed(list(sess.outcomes or [])):
            last_time = item.get("point_time") or item.get("event_time")
            last_entity = item.get("entity_key")
            if last_time:
                break
        return {
            "session_id": sess.session_id,
            "selection_policy": sess.selection_policy,
            "legacy": str(sess.selection_policy or "") != "earliest_event_time",
            "cursor": sess.cursor,
            "total": len(sess.source_rows or []),
            "status": sess.status,
            "event_clock": last_time or sess.range_start,
            "last_entity": last_entity,
        }
    except Exception:
        return {"empty": True, "legacy": False}


# @AI_GENERATED
def advance_watermark_day(slot: str, *, operator: str = "ui", use_real_model: bool = False) -> dict[str, Any]:
    """Product observatory: feed next loop_demo day, detect, auto-review. No cumulative admit."""
    from services.slot_datasets.loop_demo import run_next_demo_day

    key = _assert_slot(slot)
    if key not in _DEMO_WRITE_SLOTS:
        raise SlotDatasetError(
            "read_only_slot",
            "pv_tsc 由真实 Challenger 调度推进，观测页禁止写入 demo 水位",
        )
    cycle = run_next_demo_day(key, operator=operator, use_real_model=use_real_model)
# @AI_GENERATED: end
    return {
        "watermark_day": cycle.get("fed_day"),
        "demo": True,
        "cycle": cycle,
        "note": cycle.get("note"),
    }


def prepare_day_detect_batch(slot: str = "pv_day") -> dict[str, Any]:
    """Filter current watermark day to occupancy-ready devices before predict."""
    key = _assert_slot(slot)
    if key != "pv_day":
        raise SlotDatasetError("invalid_slot", "day detect gate is only for pv_day")
    ledger = load_ledger(key)
    if not ledger.get("watermark_day"):
        latest = _latest_source_day(key)
        if latest is None:
            raise SlotDatasetError("no_calendar_anchor", f"{key} 没有检测水位")
        ledger["watermark_day"] = latest.isoformat()
        save_ledger(key, ledger)
    day = str(ledger["watermark_day"])[:10]
    cal_frame = _read_calendar_frame(key)
    occupancy = _occupancy_from_frame(cal_frame, day, day)
    as_of = _parse_day(day)
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
        if cell.get("status") == "skipped":
            skipped.append(device)
            cells[ck] = cell
            continue
        if arrived >= OCCUPANCY_READY:
            cell["status"] = "ready"
            cell["skip_reason"] = None
            ready.append(device)
        else:
            wait_from = cell.get("wait_started_on") or day
            cell["wait_started_on"] = wait_from
            waited = (as_of - _parse_day(str(wait_from))).days
            if waited >= HOLD_DAYS:
                cell["status"] = "skipped"
                cell["skip_reason"] = "expired_incomplete"
                skipped.append(device)
            else:
                cell["status"] = "waiting"
                cell["skip_reason"] = "incomplete"
                waiting.append(device)
        cells[ck] = cell
    extra_skipped = _expire_waiting_cells(cells, as_of)
    skipped.extend(extra_skipped)
    ledger["cells"] = cells
    save_ledger(key, ledger)

    filtered_rel = None
    if ready:
        frame = cal_frame if cal_frame is not None and not cal_frame.empty else _read_source_frame(key)
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


def calendar_grid(slot: str, day_from: str | None = None, day_to: str | None = None, *, page: int = 1) -> dict[str, Any]:
    key = _assert_slot(slot)
    start = str(day_from or "")[:10]
    end = str(day_to or "")[:10]
    if not start or not end:
        start, end = default_calendar_range(key)
    if (_parse_day(end) - _parse_day(start)).days + 1 > MAX_CALENDAR_DAYS:
        raise SlotDatasetError("range_too_long", f"calendar range cannot exceed {MAX_CALENDAR_DAYS} days")
    occupancy = occupancy_by_device_day(key, start, end)
    # @AI_GENERATED: pv_tsc 不调用双槽 loop_demo，仅展示独立只读业务日时钟。
    if key == "pv_tsc":
        demo = _readonly_tsc_status(key)
        demo_devices: tuple[tuple[str, str, str], ...] = ()
    else:
        from services.slot_datasets.loop_demo import DEVICES, demo_status

        demo = demo_status(key, backend_dir=_BACKEND_DIR, create=False)
        demo_devices = tuple(DEVICES)
    if not occupancy and demo.get("demo"):
        occupancy = {
            f"{site}|{device}|{branch}": {}
            for site, device, branch in demo_devices
        }
    # @AI_GENERATED: end
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
            # @AI_GENERATED: pv_day 与 pv_tsc 都按设备日 288 点口径展示完整度。
            row_cells.append(
                {
                    "date": day,
                    "arrived_count": stored.get("arrived_count", arrived),
                    "expected_count": stored.get(
                        "expected_count",
                        EXPECTED_POINTS if key in _DAILY_SLOTS else arrived,
                    ),
                    "completeness": stored.get("completeness")
                    or (
                        round(arrived / EXPECTED_POINTS, 4)
                        if key in _DAILY_SLOTS and EXPECTED_POINTS
                        else None
                    ),
                    "status": status,
                    "model_id": stored.get("model_id"),
                    "skip_reason": stored.get("skip_reason"),
                    "late_arrival": bool(stored.get("late_arrival")),
                }
            )
            # @AI_GENERATED: end
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
        "watermark_day": ledger.get("watermark_day") or ((demo.get("clock") or {}).get("day")),
        "occupancy_ready": OCCUPANCY_READY,
        "expected_points": EXPECTED_POINTS,
        "page": page,
        "page_size": MAX_DEVICE_ROWS,
        "device_total": len(devices),
        "days": days,
        "rows": grid,
        "clock": demo.get("clock"),
        "demo_note": demo.get("note"),
        "accuracy": demo.get("accuracy"),
        # @AI_GENERATED: 前端据此对 pv_tsc 日历实施双重只读防御。
        "readonly": bool(demo.get("readonly")),
        # @AI_GENERATED: end
    }


def curve_for_device(slot: str, device_key: str, day_from: str, day_to: str) -> dict[str, Any]:
    key = _assert_slot(slot)
    frame = _read_calendar_frame(key)
    pred_by_time: dict[str, Any] = {}
    gold_by_time: dict[str, Any] = {}
    try:
        from services.slot_datasets.loop_demo import gold_frame, load_outcomes

        for item in load_outcomes(key):
            if f"{item.get('site_id')}|{item.get('device_id')}|{item.get('branch_id')}" != device_key:
                continue
            pred_by_time[str(item.get("time") or "")] = item.get("predicted_label")
        gold = gold_frame(key)
        for _, grow in gold.iterrows():
            if _device_key(grow) != device_key:
                continue
            gold_by_time[str(grow.get("time"))] = None if pd.isna(grow.get("label")) else grow.get("label")
    except Exception:
        pass
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
        stamp = str(row.get(time_col) if time_col else day)
        points.append(
            {
                "time": stamp,
                "value": None if value_col is None or pd.isna(row.get(value_col)) else float(row.get(value_col)),
                "label": gold_by_time.get(stamp, None if "label" not in row.index or pd.isna(row.get("label")) else row.get("label")),
                "predicted_label": pred_by_time.get(stamp),
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
    # @AI_GENERATED: TSC 检测必须走固定 Challenger 调度，禁止观测页伪造手工检测结果。
    if key not in _DEMO_WRITE_SLOTS:
        raise SlotDatasetError(
            "read_only_slot",
            "pv_tsc 观测仅只读；请通过 pv_tsc_predict 调度运行 MultiRocket",
        )
    # @AI_GENERATED: end
    ledger = load_ledger(key)
    target_day = str(day or ledger.get("watermark_day") or "").strip()[:10]
    if not target_day:
        target_day = anchor_calendar_day(key).isoformat()
    ck = _cell_key(device_key, target_day)
    cell = dict((ledger.get("cells") or {}).get(ck) or {"device_key": device_key, "date": target_day})
    cell["skip_reason"] = None
    cell["manual"] = True
    ran = False
    detect_note = None
    try:
        from services.slot_datasets.loop_demo import detect_one_device_day

        items = detect_one_device_day(key, device_key, target_day)
        ran = bool(items)
        detect_note = f"loop_demo_rule n={len(items)}"
        model_id = model_id or "loop_demo_rule"
        cell["status"] = "detected"
        cell["detected_at"] = _now_iso()
        cell["model_id"] = model_id
        cell["model_ran"] = True
        cell["detect_note"] = detect_note
    except SlotDatasetError:
        raise
    except Exception as exc:
        detect_note = f"detector:{exc}"
        cell["model_ran"] = False
        cell["detect_note"] = detect_note
        cell["model_id"] = model_id
    else:
        ledger.setdefault("cells", {})[ck] = cell
        ledger.setdefault("audits", []).append(
            {
                "action": "manual_detect",
                "operator": operator,
                "reason": reason,
                "device_key": device_key,
                "date": target_day,
                "model_ran": ran,
                "at": _now_iso(),
            }
        )
        save_ledger(key, ledger)
        return {"ok": True, "cell": cell, "model_ran": ran, "note": detect_note}
    ledger.setdefault("cells", {})[ck] = cell
    ledger.setdefault("audits", []).append(
        {
            "action": "manual_detect",
            "operator": operator,
            "reason": reason,
            "device_key": device_key,
            "date": target_day,
            "model_ran": False,
            "note": detect_note,
            "at": _now_iso(),
        }
    )
    save_ledger(key, ledger)
    return {"ok": True, "cell": cell, "model_ran": ran, "note": detect_note}


def rebuild_point_replay_session(slot: str, *, operator: str = "ui") -> dict[str, Any]:
    """Cancel legacy sched-pv_point-default so the next ensure uses earliest_event_time."""
    key = _assert_slot(slot)
    if key != "pv_point":
        raise SlotDatasetError("invalid_slot", "rebuild replay is only for pv_point")
    from services.timeseries_point.replay_activity import load_session
    from services.timeseries_point import replay_activity as replay_mod
    from services.scheduler.slot_workflow_runner import resolve_slot_scheduler_model
    from services.scheduler.tasks.slot_product_tasks import _binding_for_slot, _ensure_replay_session

    session_id = "sched-pv_point-default"
    try:
        sess = load_session(session_id)
        sess.status = "cancelled"
        sess.error = f"rebuilt_by_{operator}_for_earliest_event_time"
        replay_mod._save_session(sess)
    except FileNotFoundError:
        pass
    model_ctx = resolve_slot_scheduler_model(key)
    new_id = _ensure_replay_session(
        key,
        model_artifact_ref=str(model_ctx.get("model_artifact_ref") or "") or None,
        binding=_binding_for_slot(key),
    )
    try:
        policy = load_session(new_id).selection_policy
    except Exception:
        policy = "earliest_event_time"
    return {"ok": True, "session_id": new_id, "selection_policy": policy, "legacy": False}


def replay_observatory_step(slot: str, points: int = 1, *, operator: str = "ui") -> dict[str, Any]:
    key = _assert_slot(slot)
    if key != "pv_point":
        raise SlotDatasetError("invalid_slot", "replay step is only for pv_point")
    n = max(1, min(50, int(points)))
    from services.scheduler.slot_workflow_runner import resolve_slot_scheduler_model
    from services.scheduler.tasks.slot_product_tasks import _binding_for_slot, _ensure_replay_session
    from services.timeseries_point.replay_activity import replay_next_point

    model_ctx = resolve_slot_scheduler_model(key)
    artifact = model_ctx.get("model_artifact_ref")
    binding = _binding_for_slot(key)
    session_id = _ensure_replay_session(
        key,
        model_artifact_ref=str(artifact) if artifact else None,
        binding=binding,
    )
    last: dict[str, Any] | None = None
    for index in range(n):
        last = replay_next_point(
            session_id,
            idempotency_key=f"ui-{operator}-{index}-{_now_iso()}",
            context_length=int(binding.get("context_length") or 288),
        )
        if (last or {}).get("status") == "completed":
            break
    return {"ok": True, "session_id": session_id, "requested": n, "last": last}
