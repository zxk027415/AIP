"""Seven-day unlabeled+gold fixture for product-slot rolling detect demo.

Feed one calendar day at a time. Detect + auto-review against gold.
Never admit into the cumulative training ledger.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from services.iterative_labeling.accuracy_evaluator import AccuracyEvaluator
from services.slot_datasets.errors import SlotDatasetError

_BACKEND_DIR = Path(__file__).resolve().parents[2]
#: 可参与回放的路径。三条路径都要有回放能力（用户要求"三条路径都做完善"）。
#: 注意：这里放开的是**回放数据链**（写各自 data/slot_datasets/<slot>/loop_demo/），
#: 不影响 observability_ledger._DEMO_WRITE_SLOTS —— pv_tsc 的生产观测仍然只读，
#: 回放走独立通道，生产 ledger 不被 demo 水位污染。
_ALLOWED = frozenset({"pv_day", "pv_point", "pv_tsc"})
logger = logging.getLogger(__name__)

# @AI_GENERATED
# Default label names for display — also written to manifest by realistic_mock_builder
_DEFAULT_LABEL_NAMES: dict[str, str] = {
    "0": "正常", "1": "组串失配", "2": "组串老化", "3": "组串遮挡",
    "4": "旁路二极管故障", "6": "接线盒虚焊", "7": "热斑效应", "8": "PID衰减",
    "9": "逆变器限功率", "10": "CT异常", "11": "电网波动", "12": "组串断路",
    "16": "其他故障",
}


def _load_label_names(slot: str) -> dict[str, str]:
    """Load label_names from manifest if available, else return defaults."""
    folder = _BACKEND_DIR / "data" / "slot_datasets" / slot / "loop_demo"
    manifest_path = folder / "manifest.json"
    if manifest_path.is_file():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            names = m.get("label_names")
            if isinstance(names, dict) and names:
                return names
        except (OSError, json.JSONDecodeError):
            pass
    return dict(_DEFAULT_LABEL_NAMES)
# @AI_GENERATED: end
DEMO_START = "2024-06-03"
DEMO_DAYS = 7
DEMO_GEN = "v2-alarm-bursts"
POINTS_PER_DAY = 192  # 06:00–21:55 UTC, 5 min
LABELS = (
    (0, "正常"),
    (1, "组串失配"),
    (3, "其他故障"),
)
DEVICES = (
    ("demo_site", "inv_a", "1"),
    ("demo_site", "inv_b", "1"),
    ("demo_site", "inv_c", "1"),
)


def _assert_slot(slot: str) -> str:
    key = str(slot or "").strip()
    if key not in _ALLOWED:
        raise SlotDatasetError("invalid_slot", "loop demo only supports pv_day/pv_point/pv_tsc")
    return key


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def demo_dir(slot: str) -> Path:
    return _BACKEND_DIR / "data" / "slot_datasets" / _assert_slot(slot) / "loop_demo"


def _unlabeled_rel(slot: str) -> str:
    return f"data/slot_datasets/{slot}/loop_demo/unlabeled.parquet"


def _gold_rel(slot: str) -> str:
    return f"data/slot_datasets/{slot}/loop_demo/gold.parquet"


def _arrived_rel(slot: str) -> str:
    return f"data/slot_datasets/{slot}/loop_demo/arrived.parquet"


def _cursor_rel(slot: str) -> str:
    return f"data/slot_datasets/{slot}/loop_demo/feed_cursor.json"


def _outcomes_rel(slot: str) -> str:
    return f"data/slot_datasets/{slot}/loop_demo/outcomes.json"


def _accuracy_rel(slot: str) -> str:
    return f"data/slot_datasets/{slot}/loop_demo/daily_accuracy.json"


def demo_days() -> list[str]:
    start = datetime.strptime(DEMO_START, "%Y-%m-%d").date()
    return [(start + timedelta(days=i)).isoformat() for i in range(DEMO_DAYS)]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _device_day_label(device_id: str, day_index: int) -> int:
    if device_id == "inv_b" and day_index in {2, 3}:
        return 1
    if device_id == "inv_c" and day_index in {4, 5}:
        return 3
    return 0


def _point_label(device_id: str, day_index: int, step: int) -> int:
    """Per-point gold. Full-day faults plus intra-day bursts so alarms can open."""
    day_label = _device_day_label(device_id, day_index)
    if day_label != 0:
        return day_label
    if device_id == "inv_b" and day_index == 0 and 48 <= step < 72:
        return 1
    if device_id == "inv_a" and day_index == 1 and 72 <= step < 96:
        return 1
    if device_id == "inv_c" and day_index == 0 and 120 <= step < 136:
        return 3
    return 0


def _i_cal_for_label(label_id: int, rng: float) -> float:
    base = {0: 8.2, 1: 4.1, 3: 1.15}.get(int(label_id), 8.0)
    return round(max(0.05, base + (rng - 0.5) * 1.6), 4)


def _predict_i_cal(i_cal: float) -> int:
    # 故意和生成簇错开：正常点约 7.4–9.0，阈值 7.8 会让一部分被判成失配。
    if i_cal > 7.8:
        return 0
    if i_cal > 3.6:
        return 1
    return 3


def _confidence_for_i_cal(i_cal: float, pred: int) -> float:
    """Distance-to-boundary score. Near 7.8 / 3.6 → low; far → high. Not a trained probability."""
    if pred == 0:
        dist = float(i_cal) - 7.8
    elif pred == 1:
        dist = min(float(i_cal) - 3.6, 7.8 - float(i_cal))
    else:
        dist = 3.6 - float(i_cal)
    return round(min(0.98, max(0.52, 0.52 + max(0.0, dist) / 2.0 * 0.46)), 3)


def build_gold_frame() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for day_index, day in enumerate(demo_days()):
        for site, device, branch in DEVICES:
            for step in range(POINTS_PER_DAY):
                label = _point_label(device, day_index, step)
                hour = 6 + (step * 5) // 60
                minute = (step * 5) % 60
                stamp = f"{day}T{hour:02d}:{minute:02d}:00+00:00"
                rng = ((step * 17 + day_index * 13 + ord(device[-1])) % 100) / 100.0
                i_cal = _i_cal_for_label(label, rng)
                rows.append(
                    {
                        "site_id": site,
                        "device_id": device,
                        "branch_id": branch,
                        "time": stamp,
                        "date": day,
                        "i_cal": i_cal,
                        "value": i_cal,
                        "label": label,
                    }
                )
    return pd.DataFrame(rows)


def ensure_loop_demo(slot: str, *, backend_dir: Optional[Path] = None) -> dict[str, Any]:
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    folder = root / "data" / "slot_datasets" / key / "loop_demo"
    folder.mkdir(parents=True, exist_ok=True)
    gold_path = folder / "gold.parquet"
    unlabeled_path = folder / "unlabeled.parquet"
    manifest_path = folder / "manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.is_file() else {}
    stale = str(manifest.get("generation") or "") != DEMO_GEN
    if not gold_path.is_file() or not unlabeled_path.is_file() or stale:
        gold = build_gold_frame()
        gold.to_parquet(gold_path, index=False)
        unlabeled = gold.drop(columns=["label"])
        unlabeled.to_parquet(unlabeled_path, index=False)
        _write_json(
            manifest_path,
            {
                "slot": key,
                "generation": DEMO_GEN,
                "start_day": DEMO_START,
                "days": demo_days(),
                "device_count": len(DEVICES),
                "points_per_device_day": POINTS_PER_DAY,
                "labels": [{"label_id": lid, "label_name": name} for lid, name in LABELS],
                "unlabeled": f"data/slot_datasets/{key}/loop_demo/unlabeled.parquet",
                "gold": f"data/slot_datasets/{key}/loop_demo/gold.parquet",
                "note": "演示集：按日喂 unlabeled，gold 只用于自动审核和精度，不写入累计账本。含连续故障段，告警可 open。",
            },
        )
        if stale:
            reset_feed(key, backend_dir=root)
    cursor_path = folder / "feed_cursor.json"
    if not cursor_path.is_file():
        _write_json(
            cursor_path,
            {
                "slot": key,
                "days": demo_days(),
                "fed_days": [],
                "last_fed_day": None,
                "exhausted": False,
                "updated_at": _now_iso(),
            },
        )
    return load_cursor(key, backend_dir=root)


def load_cursor(slot: str, *, backend_dir: Optional[Path] = None) -> dict[str, Any]:
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    path = root / "data" / "slot_datasets" / key / "loop_demo" / "feed_cursor.json"
    payload = _read_json(path)
    payload.setdefault("slot", key)
    payload.setdefault("days", demo_days())
    payload.setdefault("fed_days", [])
    payload.setdefault("last_fed_day", None)
    payload.setdefault("exhausted", False)
    return payload


def arrived_frame(slot: str, *, backend_dir: Optional[Path] = None) -> pd.DataFrame:
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    path = root / "data" / "slot_datasets" / key / "loop_demo" / "arrived.parquet"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_parquet(path)


def _selected_dataset_ref(slot: str, root: Path) -> Optional[str]:
    """该 slot 运行时选中的喂数源；未选则 None（回落 loop_demo/unlabeled.parquet）。"""
    from services.slot_datasets import feed_sources as feed_sources_service

    selection = feed_sources_service.get_selection(slot, backend_dir=root)
    if not selection:
        return None
    ref = str(selection.get("dataset_ref") or "").strip()
    return ref or None


def _calendar_days(frame: pd.DataFrame) -> list[str]:
    days = sorted(
        {
            str(value)[:10]
            for value in frame["date"].astype(str)
            if str(value)[:10] not in {"", "None", "nan", "NaT", "NaN"}
        }
    )
    if not days:
        raise SlotDatasetError("empty_calendar", "喂数源没有可用业务日")
    return days


def _load_unlabeled_source(slot: str, root: Path) -> tuple[pd.DataFrame, Optional[str]]:
    """读当前喂数帧：有选中则读白名单 parquet，否则读内置 unlabeled.parquet。"""
    from services.slot_datasets import feed_sources as feed_sources_service

    key = _assert_slot(slot)
    ref = _selected_dataset_ref(key, root)
    if ref:
        try:
            frame = feed_sources_service.load_frame(ref)
        except feed_sources_service.FeedSourceError as exc:
            raise SlotDatasetError(exc.code, exc.message) from exc
        return frame, ref
    unlabeled_path = root / _unlabeled_rel(key)
    if not unlabeled_path.is_file():
        raise SlotDatasetError("missing_unlabeled", f"{key} 缺少内置 unlabeled.parquet")
    frame = pd.read_parquet(unlabeled_path)
    if "date" not in frame.columns:
        try:
            frame = feed_sources_service._normalize_date_column(frame)
        except feed_sources_service.FeedSourceError as exc:
            raise SlotDatasetError(exc.code, exc.message) from exc
    else:
        frame = frame.copy()
        frame["date"] = frame["date"].astype(str).str.slice(0, 10)
    return frame, None


def _reset_runtime_artifacts(folder: Path) -> None:
    for name in ("arrived.parquet", "outcomes.json", "daily_accuracy.json"):
        path = folder / name
        if path.is_file():
            path.unlink()


def _bind_cursor_to_source(
    slot: str,
    root: Path,
    dataset_ref: Optional[str],
    days: list[str],
) -> dict[str, Any]:
    """选中源与游标不一致时重置 arrived/outcomes/精度，避免两套数据混在一条回放链。"""
    key = _assert_slot(slot)
    cursor = load_cursor(key, backend_dir=root)
    bound = str(cursor.get("dataset_ref") or "").strip() or None
    ref = str(dataset_ref or "").strip() or None
    if bound == ref:
        return cursor
    folder = root / "data" / "slot_datasets" / key / "loop_demo"
    folder.mkdir(parents=True, exist_ok=True)
    _reset_runtime_artifacts(folder)
    cursor = {
        "slot": key,
        "dataset_ref": ref,
        "days": list(days),
        "fed_days": [],
        "last_fed_day": None,
        "exhausted": False,
        "updated_at": _now_iso(),
    }
    _write_json(folder / "feed_cursor.json", cursor)
    return cursor


def gold_frame(slot: str, *, backend_dir: Optional[Path] = None) -> pd.DataFrame:
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    ref = _selected_dataset_ref(key, root)
    if ref:
        from services.slot_datasets import feed_sources as feed_sources_service

        try:
            frame = feed_sources_service.load_frame(ref)
        except feed_sources_service.FeedSourceError:
            return pd.DataFrame()
        gold_col = feed_sources_service.truth_column_of(frame)
        if not gold_col:
            # 选中源无真值：不得回落到内置 gold.parquet，否则两套数据对在一起。
            return pd.DataFrame()
        out = frame.copy()
        if gold_col != "label":
            out["label"] = out[gold_col]
        return out
    path = root / "data" / "slot_datasets" / key / "loop_demo" / "gold.parquet"
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_outcomes(slot: str, *, backend_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    path = root / "data" / "slot_datasets" / key / "loop_demo" / "outcomes.json"
    payload = _read_json(path)
    items = payload.get("items") if isinstance(payload, dict) else None
    return list(items) if isinstance(items, list) else []


def outcomes_for_window(
    slot: str,
    day_from: Optional[str] = None,
    day_to: Optional[str] = None,
    *,
    backend_dir: Optional[Path] = None,
) -> dict[str, Any]:
    key = _assert_slot(slot)
    start = str(day_from or "")[:10]
    end = str(day_to or "")[:10]
    items = load_outcomes(key, backend_dir=backend_dir)
    if start and end:
        items = [item for item in items if start <= str(item.get("date") or "")[:10] <= end]
    enriched = []
    for item in items:
        row = dict(item)
        i_cal = row.get("i_cal")
        pred = row.get("predicted_label")
        if i_cal is not None and pred is not None:
            try:
                row["confidence"] = _confidence_for_i_cal(float(i_cal), int(pred))
            except (TypeError, ValueError):
                pass
        enriched.append(row)
    daily_units = _aggregate_device_day_units(enriched) if key == "pv_day" else []
    # @AI_GENERATED
    label_names = _load_label_names(key)
    # @AI_GENERATED: end
    return {
        "slot": key,
        "from": start or None,
        "to": end or None,
        "count": len(enriched),
        "items": enriched,
        "daily_units": daily_units,
        "daily_count": len(daily_units),
        "label_names": label_names,
        "source": "loop_demo",
    }


def _aggregate_device_day_units(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Day-path Acc unit: one row per device-day. Curves keep per-point items."""
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for item in items:
        key = (
            str(item.get("site_id") or ""),
            str(item.get("device_id") or ""),
            str(item.get("branch_id") or ""),
            str(item.get("date") or "")[:10],
        )
        groups.setdefault(key, []).append(item)
    units: list[dict[str, Any]] = []
    for (site, device, branch, day), rows in groups.items():
        if not day:
            continue
        mean_i = sum(float(row.get("i_cal") or 0.0) for row in rows) / max(len(rows), 1)
        # @AI_GENERATED
        # Use the model's own per-point predictions (majority vote) instead of
        # re-predicting with the rule.  For RFC models, all points in a device-day
        # share the same prediction (broadcast from the day-level RFC output).
        preds = [int(row.get("predicted_label") or 0) for row in rows]
        pred = max(set(preds), key=preds.count) if preds else 0
        # 只统计**真的有标签**的点：缺标签既不折算成 0（那会把「未打标」当成「正常」），
        # 也不回落到模型自己的预测（那是自证真值，精度会虚高到接近满分）。
        golds = [
            int(row["gold_label"])
            for row in rows
            if row.get("gold_label") is not None
        ]
        truth = max(set(golds), key=golds.count) if golds else None
        # confidence: use average of per-point confidence from model
        confs = [float(row.get("confidence") or 0.0) for row in rows]
        avg_conf = sum(confs) / max(len(confs), 1)
        # @AI_GENERATED: end
        units.append(
            {
                "unit_key": f"{site}|{device}|{branch}|{day}",
                "site_id": site,
                "device_id": device,
                "branch_id": branch,
                "date": day,
                "time": f"{day}T12:00:00+00:00",
                "predicted_label": pred,
                "gold_label": truth,
                "confidence": avg_conf,
                "kind": "prediction",
                "i_cal": mean_i,
                "point_count": len(rows),
            }
        )
    units.sort(key=lambda row: (str(row.get("date") or ""), str(row.get("device_id") or "")))
    return units


def load_daily_accuracy(slot: str, *, backend_dir: Optional[Path] = None) -> dict[str, Any]:
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    path = root / "data" / "slot_datasets" / key / "loop_demo" / "daily_accuracy.json"
    payload = _read_json(path)
    if not payload:
        return {"slot": key, "empty": True, "by_day": [], "latest": None}
    payload.setdefault("slot", key)
    payload.setdefault("empty", not bool(payload.get("by_day")))
    by_day = [item for item in (payload.get("by_day") or []) if isinstance(item, dict)]
    counted = sum(int(item.get("counted_units") or 0) for item in by_day)
    confirm = sum(int(item.get("confirm_count") or 0) for item in by_day)
    correct = sum(int(item.get("correct_count") or 0) for item in by_day)
    payload["cumulative"] = {
        "day_count": len(by_day),
        "counted_units": counted,
        "confirm_count": confirm,
        "correct_count": correct,
        "classifier_accuracy": (confirm / counted) if counted else None,
        "note": "已喂天数按样本加权累计，不是每日 Acc 再取平均。",
    }
    return payload


def _stamp(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value or "")


def _unit_key(row: pd.Series, slot: str) -> str:
    site = str(row.get("site_id") or "")
    device = str(row.get("device_id") or "")
    branch = str(row.get("branch_id") or "")
    if slot == "pv_day":
        day = str(row.get("date") or "")[:10]
        return f"{site}|{device}|{branch}|{day}"
    return f"{site}|{device}|{branch}|{_stamp(row.get('time'))}"


def _pending_entry(cursor: dict[str, Any], day: str) -> dict[str, Any]:
    pending = cursor.setdefault("pending_days", {})
    entry = pending.get(day)
    if not isinstance(entry, dict):
        entry = {"attempts": 0, "first_seen_at": _now_iso()}
        pending[day] = entry
    return entry


def _waited_days(cursor: dict[str, Any], day: str) -> int:
    """该待定日已经过多少个观察周期。

    回放语义下「一次推进 = 一个业务日观察周期」，故用尝试次数而非墙钟天数——
    否则同一秒内连续推进永远等不到 HOLD_DAYS，超期出口形同虚设。
    """
    entry = _pending_entry(cursor, day)
    return int(entry.get("attempts") or 0)


def _coverage_for(chunk: Any) -> Optional[float]:
    """窗口覆盖率：非 NaN 测量点占 EXPECTED_POINTS 的比例（TSC 门禁用）。"""
    try:
        from services.slot_datasets.observability_ledger import EXPECTED_POINTS

        if EXPECTED_POINTS <= 0:
            return None
        return float(len(chunk)) / float(EXPECTED_POINTS)
    except Exception:
        return None


def feed_next_day(
    slot: str,
    *,
    operator: str = "ui",
    backend_dir: Optional[Path] = None,
    skip_ensure: bool = False,
) -> dict[str, Any]:
    """推进一步喂数 —— **粒度与到达判据按 slot 语义分派**。

    三条路径的设计语义不同（集中声明在 services/slot_datasets/feed_semantics.py）：

      - ``pv_point``：**按点**推进。一次只前进一个测点，逐点累积该日进度；
        该日全部点喂完才计入 ``fed_days``。
      - ``pv_day`` / ``pv_tsc``：**按整日**推进，且必须先过到达判据：
        未达 ``OCCUPANCY_READY``（TSC 另需窗口覆盖率）时**不落 arrived、不计入
        fed_days**，返回可解释的 ``skipped_reason``；连续超过 ``HOLD_DAYS`` 未到齐
        转 ``expired_incomplete``。

    红线：**落盘与计入 fed 同进同退** —— 不允许出现「水位前进了但样本没进」
    （此前 pv_point 2021-08-26 那天 units=0 却已计入 fed_days 就是这个缺陷）。
    """
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    selected_ref = _selected_dataset_ref(key, root)
    # 已选外部源时不得 ensure_loop_demo：那会用内置 7 日覆盖用户数据。
    if not skip_ensure and not selected_ref and not _is_realistic_built(key, root):
        ensure_loop_demo(key, backend_dir=root)
    source, selected_ref = _load_unlabeled_source(key, root)
    if selected_ref:
        cursor = _bind_cursor_to_source(key, root, selected_ref, _calendar_days(source))
    else:
        cursor = load_cursor(key, backend_dir=root)
    days: list[str] = list(cursor.get("days") or demo_days())
    fed: list[str] = list(cursor.get("fed_days") or [])
    remaining = [day for day in days if day not in fed]
    if not remaining:
        cursor["exhausted"] = True
        _write_json(root / _cursor_rel(key), cursor)
        raise SlotDatasetError("demo_exhausted", "当前喂数源日历已喂完，可重置游标或换数据集再演")
    day = remaining[0]
    chunk = source[source["date"].astype(str).str.slice(0, 10) == day].copy()

    from services.slot_datasets import feed_semantics as semantics

    granularity = semantics.granularity_for(key)

    if granularity == semantics.GRANULARITY_POINT:
        # 点路径：按点推进。取该日第 progress 个点，而非整日灌入。
        ordered = chunk.sort_values("time").reset_index(drop=True) if not chunk.empty else chunk
        total_points = int(len(ordered))
        day_progress = int((cursor.get("point_progress") or {}).get(day) or 0)
        if total_points == 0 or day_progress >= total_points:
            return {
                "slot": key,
                "fed_day": None,
                "granularity": granularity,
                "status": "skipped",
                "skipped_reason": "no_point_available",
                "arrived_points": day_progress,
                "required_points": None,
                "row_count": 0,
                "cursor": cursor,
            }
        step = ordered.iloc[[day_progress]].copy()
        next_progress = day_progress + 1
        day_finished = next_progress >= total_points
        cursor.setdefault("point_totals", {})[day] = total_points
    else:
        # 日路径 / TSC：先过到达判据，判据不过一律不落盘、不计入 fed。
        status = semantics.resolve_arrival_status(
            key,
            arrived_points=int(len(chunk)),
            waited_days=_waited_days(cursor, day),
            coverage=_coverage_for(chunk) if key == "pv_tsc" else None,
        )
        if status["status"] != semantics.STATUS_READY:
            entry = _pending_entry(cursor, day)
            entry["attempts"] = int(entry.get("attempts") or 0) + 1
            entry["status"] = status["status"]
            entry["reason"] = status["reason"]
            entry["arrived_points"] = int(len(chunk))
            entry["checked_at"] = _now_iso()
            _write_json(root / _cursor_rel(key), cursor)
            return {
                "slot": key,
                "fed_day": None,
                "granularity": granularity,
                "status": status["status"],
                "skipped_reason": status["reason"],
                "arrived_points": int(len(chunk)),
                "required_points": (status["gate"] or {}).get("min_points"),
                "row_count": 0,
                "cursor": cursor,
            }
        step = chunk
        next_progress = None
        day_finished = True

    # 过了门禁 / 取到点 —— 现在才落盘，落盘成功才计 fed。
    arrived_path = root / _arrived_rel(key)
    if arrived_path.is_file():
        prev = pd.read_parquet(arrived_path)
        out = pd.concat([prev, step], ignore_index=True)
    else:
        out = step
    arrived_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(arrived_path, index=False)

    if granularity == semantics.GRANULARITY_POINT:
        cursor.setdefault("point_progress", {})[day] = next_progress
    if day_finished:
        fed.append(day)
        pending = cursor.get("pending_days")
        if isinstance(pending, dict):
            pending.pop(day, None)

    cursor.update(
        {
            "fed_days": fed,
            "last_fed_day": day if day_finished else cursor.get("last_fed_day"),
            "exhausted": len(fed) >= len(days),
            "last_operator": operator,
            "updated_at": _now_iso(),
            "day_index": len(fed),
            "total_days": len(days),
            "dataset_ref": selected_ref,
        }
    )
    _write_json(root / _cursor_rel(key), cursor)
    return {
        "slot": key,
        "fed_day": day,
        "granularity": granularity,
        "status": "fed",
        "skipped_reason": None,
        "arrived_points": int(len(step)),
        "required_points": None,
        "row_count": int(len(step)),
        "day_finished": bool(day_finished),
        "cursor": cursor,
    }


def reset_feed(slot: str, *, backend_dir: Optional[Path] = None) -> dict[str, Any]:
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    folder = root / "data" / "slot_datasets" / key / "loop_demo"
    _reset_runtime_artifacts(folder)
    selected_ref = _selected_dataset_ref(key, root)
    if selected_ref:
        source, _ref = _load_unlabeled_source(key, root)
        days = _calendar_days(source)
    else:
        days = demo_days()
    cursor = {
        "slot": key,
        "dataset_ref": selected_ref,
        "days": days,
        "fed_days": [],
        "last_fed_day": None,
        "exhausted": False,
        "updated_at": _now_iso(),
    }
    _write_json(folder / "feed_cursor.json", cursor)
    try:
        from services.slot_datasets import observability_ledger as obs

        if backend_dir is not None:
            obs._BACKEND_DIR = root
        ledger = obs.load_ledger(key)
        demo = set(demo_days())
        cells = {
            ck: cell
            for ck, cell in dict(ledger.get("cells") or {}).items()
            if str((cell or {}).get("date") or "")[:10] not in demo
            and not str((cell or {}).get("device_key") or "").startswith("demo_site|")
        }
        ledger["cells"] = cells
        if str(ledger.get("watermark_day") or "")[:10] in demo:
            ledger["watermark_day"] = None
        obs.save_ledger(key, ledger)
    except Exception:
        pass
    return cursor


def _row_i_cal(row: pd.Series) -> float:
    raw = row.get("i_cal")
    if raw is None or pd.isna(raw):
        raw = row.get("value")
    try:
        return 0.0 if raw is None or pd.isna(raw) else float(raw)
    except (TypeError, ValueError):
        return 0.0


def _detect_chunk(
    slot: str,
    chunk: pd.DataFrame,
    *,
    use_real_model: bool = False,
    backend_dir: Optional[Path] = None,
) -> tuple[list[dict[str, Any]], str]:
    """Per-timestamp outcomes for both slots so accuracy-ops can draw the same 5-min curve.

    Returns ``(items, model_id)``.  When *use_real_model* is True, the registered
    production model (RFC for pv_day, TCN for pv_point) is loaded and used for
    prediction instead of the built-in ``_predict_i_cal`` rule.
    """
    # @AI_GENERATED
    gold = gold_frame(slot, backend_dir=backend_dir)
    if use_real_model:
        try:
            from services.slot_datasets.real_model_detect import detect_day_with_rfc, detect_point_with_tcn
            if slot == "pv_day":
                return detect_day_with_rfc(chunk, gold)
            else:
                return detect_point_with_tcn(chunk, gold)
        except Exception as exc:
            logger.warning("[loop_demo] real model detect failed, falling back to rule: %s", exc)
    # @AI_GENERATED: end

    # ── rule-based fallback (original logic) ─────────────────────────────────
    gold_by_point: dict[str, int] = {}
    if gold is not None and not gold.empty and "label" in gold.columns:
        gold = gold.copy()
        gold["_key"] = [_unit_key(row, "pv_point") for _, row in gold.iterrows()]
        gold_by_point = {
            str(key): int(label)
            for key, label in zip(gold["_key"], gold["label"])
            if key is not None and pd.notna(label)
        }
    items: list[dict[str, Any]] = []
    for _, row in chunk.iterrows():
        i_cal = _row_i_cal(row)
        pred = _predict_i_cal(i_cal)
        key = _unit_key(row, "pv_point")
        gold_truth = gold_by_point.get(key)
        truth = int(gold_truth) if gold_truth is not None else None
        value = None if "value" not in row.index or pd.isna(row.get("value")) else float(row.get("value"))
        items.append(
            {
                "unit_key": key,
                "site_id": str(row.get("site_id") or ""),
                "device_id": str(row.get("device_id") or ""),
                "branch_id": str(row.get("branch_id") or ""),
                "date": str(row.get("date") or "")[:10],
                "time": str(row.get("time") or ""),
                "predicted_label": pred,
                "gold_label": truth,
                "confidence": _confidence_for_i_cal(i_cal, pred),
                "kind": "prediction",
                "i_cal": i_cal,
                "value": value if value is not None else i_cal,
            }
        )
    return items, "loop_demo_rule"


def _auto_review_session(
    slot: str,
    day: str,
    units: list[dict[str, Any]],
    *,
    # @AI_GENERATED
    model_id: str,
    # @AI_GENERATED: end
    backend_dir: Optional[Path] = None,
) -> dict[str, Any]:
    from services.iterative_labeling.storage.file_backend import FileReviewResultRepository

    evaluator = AccuracyEvaluator()
    verdicts = []
    session_units = []
    pending_units = 0
    for item in units:
        pred = int(item["predicted_label"])
        raw_truth = item.get("gold_label")
        if raw_truth is None:
            # 无真值：只登记「待打标」单元，不写 verdict、不计入精度。
            # 这样精度要么来自真值、要么诚实显示为「待打标 N 条」，不会自证虚高。
            pending_units += 1
            session_units.append(
                {
                    "unit_key": item["unit_key"],
                    "site_id": item.get("site_id"),
                    "device_id": item.get("device_id"),
                    "branch_id": item.get("branch_id"),
                    "time_window": item.get("time") or item.get("date") or day,
                    "classifier_prediction": {
                        "predicted_label": pred,
                        "confidence": float(item.get("confidence") or 0.0),
                    },
                    "llm_suggestion": None,
                    "disagreement": False,
                    "current_verdict": None,
                    "predicted_label": pred,
                    "confidence": float(item.get("confidence") or 0.0),
                    "status": "pending_label",
                    "final_label": None,
                    "annotation_role_recommended": "learning",
                }
            )
            continue
        truth = int(raw_truth)
        action = "confirm" if pred == truth else "correct"
        verdict = {
            "unit_key": item["unit_key"],
            "verdict_label": truth,
            "predicted_label": pred,
            "action_type": action,
            "is_ground_truth": True,
            "reviewer": "mock_gold",
        }
        session_units.append(
            {
                "unit_key": item["unit_key"],
                "site_id": item.get("site_id"),
                "device_id": item.get("device_id"),
                "branch_id": item.get("branch_id"),
                "time_window": item.get("time") or item.get("date") or day,
                "classifier_prediction": {
                    "predicted_label": pred,
                    "confidence": float(item.get("confidence") or 0.0),
                },
                "llm_suggestion": None,
                "disagreement": False,
                "current_verdict": {
                    "verdict_label": truth,
                    "action_type": action,
                    "reviewer": "mock_gold",
                },
                "predicted_label": pred,
                "confidence": float(item.get("confidence") or 0.0),
                "status": "confirmed",
                "final_label": truth,
                "annotation_role_recommended": "learning",
            }
        )
        verdicts.append(verdict)
        evaluator.update(
            {"verdict_label": truth, "action_type": action},
            {"predicted_label": pred},
            label_source="loop_demo",
        )
    accuracy = evaluator.get_current_accuracy()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    review_id = f"rev-loop-demo-{slot}-{day}-{stamp}"
    session = {
        "review_id": review_id,
        "slot": slot,
        "status": "reviewed",
        "reviewer": "mock_gold",
        "reviewed_count": len(session_units),
        "total_count": len(session_units),
        "units": session_units,
        "verdicts": verdicts,
        "prediction_context": {
            "source": "loop_demo",
            "fed_day": day,
            # @AI_GENERATED
            # 真实模型回放时必须记实际 mc-*；此前恒写 loop_demo_rule，
            # 审核记录会与同一天 daily_accuracy.model_id 互相矛盾。
            "model_id": model_id,
            # @AI_GENERATED: end
        },
        "accuracy_snapshot": accuracy,
        "pending_label_units": pending_units,
        "counted_units": len(verdicts),
        "loop_id": "",
        "cumulative_admission": {
            "completed": False,
            "skipped": True,
            "reason": "loop_demo_no_admit",
            "note": "演示审核完成，未写入累计账本，避免污染训练集。",
        },
        "created_at": _now_iso(),
        "review_completed_at": _now_iso(),
    }
    repo = FileReviewResultRepository()
    label_root = (Path(backend_dir) if backend_dir is not None else _BACKEND_DIR) / "data" / "iterative_labeling"
    label_root.mkdir(parents=True, exist_ok=True)
    repo.data_root = label_root
    repo.save_verdict(slot, review_id, session)
    return {"review_id": review_id, "accuracy": accuracy, "session": session}


def _is_realistic_built(key: str, root: Path) -> bool:
    """该 slot 是否已由 realistic_mock_builder 生成过数据集。

    ``ensure_loop_demo`` 会用内置生成覆盖 loop_demo 数据；若已是 realistic 数据集
    则**不得**覆盖——那份数据用的是真实站点/设备名（用户为验证打标回流而 mock）。
    2026-09-14 实际发生过一次静默覆盖，故把判断抽成共用函数，供 demo_status 与
    run_next_demo_day 使用同一口径。
    """
    manifest_path = root / "data" / "slot_datasets" / key / "loop_demo" / "manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return str(manifest.get("mode") or "") == "realistic"


def run_next_demo_day(slot: str, *, operator: str = "ui", backend_dir: Optional[Path] = None, use_real_model: bool = False) -> dict[str, Any]:
    """Feed one day, detect, open rev, auto-review against gold. Do not admit."""
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    selected_ref = _selected_dataset_ref(key, root)
    # @AI_GENERATED
    # 数据来源与检测器是两件正交的事：`use_real_model` 只决定「用真实模型还是内置规则」，
    # **不应该**顺手改数据。此前 use_real_model=True 会无条件 build_realistic_mock，
    # 把用户刚选中的外部喂数源覆盖掉 —— 于是「用项目数据 + 项目模型出精度」永远做不到。
    if selected_ref:
        # 已选外部源：任何情况下都不许用内置生成覆盖它。
        pass
    elif use_real_model:
        from services.slot_datasets.realistic_mock_builder import build_realistic_mock
        build_realistic_mock(key, backend_dir=root)
    elif not _is_realistic_built(key, root):
        ensure_loop_demo(key, backend_dir=root)
    # @AI_GENERATED: end
    fed = feed_next_day(key, operator=operator, backend_dir=root, skip_ensure=True)
    day = fed.get("fed_day")
    if not day:
        # 未过到达门禁 / 该日无可喂点：不建空会话、不写精度。
        # 此前这里会把 None 字符串化后继续跑，产出 units=0 的空转记录。
        return {
            "slot": key,
            "fed_day": None,
            "day_index": int((fed.get("cursor") or {}).get("day_index") or 0),
            "total_days": len(list((fed.get("cursor") or {}).get("days") or demo_days())),
            "row_count": 0,
            "detected_units": 0,
            "review_id": None,
            "accuracy": None,
            "admitted": False,
            "exhausted": bool((fed.get("cursor") or {}).get("exhausted")),
            "cursor": fed.get("cursor"),
            "status": fed.get("status"),
            "skipped_reason": fed.get("skipped_reason"),
            "granularity": fed.get("granularity"),
            "note": (
                f"业务日未推进（{fed.get('skipped_reason')}）："
                f"到达 {fed.get('arrived_points')} / 门槛 {fed.get('required_points')}"
                if fed.get("required_points") is not None
                else f"业务日未推进（{fed.get('skipped_reason')}）"
            ),
            "use_real_model": use_real_model,
        }
    day = str(day)
    arrived = arrived_frame(key, backend_dir=root)
    chunk = arrived[arrived["date"].astype(str).str.slice(0, 10) == day].copy()
    outcomes, model_id = _detect_chunk(key, chunk, use_real_model=use_real_model, backend_dir=root)
    existing = load_outcomes(key, backend_dir=root)
    existing = [item for item in existing if str(item.get("date") or "")[:10] != day]
    existing.extend(outcomes)
    _write_json(
        root / _outcomes_rel(key),
        {"slot": key, "items": existing, "updated_at": _now_iso()},
    )
    review_units = _aggregate_device_day_units(outcomes) if key == "pv_day" else outcomes
    # @AI_GENERATED
    review = _auto_review_session(
        key, day, review_units, model_id=model_id, backend_dir=root
    )
    # @AI_GENERATED: end
    acc_store = load_daily_accuracy(key, backend_dir=root)
    by_day = [item for item in (acc_store.get("by_day") or []) if item.get("day") != day]
    day_row = {
        "day": day,
        "review_id": review["review_id"],
        "counted_units": (review["accuracy"] or {}).get("counted_units"),
        "classifier_accuracy": (review["accuracy"] or {}).get("classifier_accuracy"),
        "macro_f1": ((review["accuracy"] or {}).get("macro") or {}).get("f1"),
        "macro_precision": ((review["accuracy"] or {}).get("macro") or {}).get("precision"),
        "macro_recall": ((review["accuracy"] or {}).get("macro") or {}).get("recall"),
        "confirm_count": sum(
            1
            for item in review_units
            if item.get("gold_label") is not None and int(item["predicted_label"]) == int(item["gold_label"])
        ),
        "correct_count": sum(
            1
            for item in review_units
            if item.get("gold_label") is not None and int(item["predicted_label"]) != int(item["gold_label"])
        ),
        "admitted": False,
        "model_id": model_id,
        "evaluation_unit": "device_day" if key == "pv_day" else "point",
    }
    by_day.append(day_row)
    acc_payload = {
        "slot": key,
        "empty": False,
        "usable": True,
        "promote_eligible": False,
        "origin": "loop_demo",
        "evaluation_kind": "loop_demo",
        "note": "演示按日对照精度，未写入累计账本。",
        "by_day": by_day,
        "latest": day_row,
        "updated_at": _now_iso(),
    }
    _write_json(root / _accuracy_rel(key), acc_payload)

    from services.slot_datasets import observability_ledger as obs

    # pv_tsc 生产观测只读：回放只写 loop_demo 目录，不污染 production ledger。
    if key != "pv_tsc":
        if backend_dir is not None:
            obs._BACKEND_DIR = root
        devices = sorted({f"{u['site_id']}|{u['device_id']}|{u['branch_id']}" for u in outcomes})
        obs.mark_devices_detected(key, devices, day=day, model_id=model_id)
        ledger = obs.load_ledger(key)
        ledger["watermark_day"] = day
        ledger["demo"] = True
        obs.save_ledger(key, ledger)
    cursor_payload = fed.get("cursor") or {}
    total_days = len(list(cursor_payload.get("days") or demo_days()))
    day_index = int(cursor_payload.get("day_index") or 0)
    return {
        "slot": key,
        "fed_day": day,
        "day_index": day_index,
        "total_days": total_days,
        "row_count": int(fed.get("row_count") or 0),
        "detected_units": len(outcomes),
        "granularity": fed.get("granularity"),
        "day_finished": fed.get("day_finished"),
        "review_id": review["review_id"],
        "accuracy": review["accuracy"],
        "admitted": False,
        "exhausted": bool(cursor_payload.get("exhausted")),
        "cursor": cursor_payload,
        "dataset_ref": cursor_payload.get("dataset_ref") or selected_ref,
        "note": (
            f"{'真实模型' if use_real_model else '演示规则'}第 {day_index}/{total_days} 天 {day}："
            f"已检测并自动审核，未写入累计。"
            + (" 未写入 pv_tsc 生产观测。" if key == "pv_tsc" else "")
        ),
        "use_real_model": use_real_model,
        "model_id": model_id,
    }


def detect_one_device_day(slot: str, device_key: str, day: str, *, backend_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """Re-run the demo detector on one arrived device-day. Does not admit."""
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    arrived = arrived_frame(key, backend_dir=root)
    if arrived is None or arrived.empty:
        raise SlotDatasetError("no_arrived", "没有到达数据可补检")
    parts = str(device_key).split("|")
    site, device, branch = (parts + ["", "", ""])[:3]
    chunk = arrived[
        (arrived["site_id"].astype(str) == site)
        & (arrived["device_id"].astype(str) == device)
        & (arrived["branch_id"].astype(str) == branch)
        & (arrived["date"].astype(str).str.slice(0, 10) == str(day)[:10])
    ].copy()
    if chunk.empty:
        raise SlotDatasetError("no_arrived", f"{device_key} 在 {day} 没有到达点")
    items, _mid = _detect_chunk(key, chunk, backend_dir=root)
    existing = load_outcomes(key, backend_dir=root)
    keys = {str(item.get("unit_key")) for item in items}
    existing = [item for item in existing if str(item.get("unit_key")) not in keys]
    existing.extend(items)
    _write_json(root / _outcomes_rel(key), {"slot": key, "items": existing, "updated_at": _now_iso()})
    return items


def demo_status(slot: str, *, backend_dir: Optional[Path] = None, create: bool = False) -> dict[str, Any]:
    key = _assert_slot(slot)
    root = Path(backend_dir) if backend_dir is not None else _BACKEND_DIR
    cursor_path = root / "data" / "slot_datasets" / key / "loop_demo" / "feed_cursor.json"
    # @AI_GENERATED
    # If realistic mock already built, don't overwrite with ensure_loop_demo
    is_realistic = _is_realistic_built(key, root)
    selected_ref = _selected_dataset_ref(key, root)
    if create and not is_realistic and not selected_ref:
        cursor = ensure_loop_demo(key, backend_dir=root)
    elif cursor_path.is_file():
        cursor = load_cursor(key, backend_dir=root)
    elif selected_ref:
        cursor = {
            "slot": key,
            "dataset_ref": selected_ref,
            "days": [],
            "fed_days": [],
            "last_fed_day": None,
            "exhausted": False,
        }
    # @AI_GENERATED: end
    else:
        return {
            "slot": key,
            "demo": False,
            "clock": {"kind": "business_day" if key == "pv_day" else "event_time", "day": None, "timestamp": None, "source": None},
            "progress": {"day_index": 0, "total_days": DEMO_DAYS, "fed_days": [], "exhausted": False},
            "window": {"from": None, "to": None},
            "accuracy": None,
            "feed": {"dataset_ref": None, "point_progress": {}, "point_totals": {}, "pending_days": {}},
            "note": "尚未启用演示喂数",
        }
    fed_days = list(cursor.get("fed_days") or [])
    last = str(cursor.get("last_fed_day") or "")[:10] or None
    acc = load_daily_accuracy(key, backend_dir=backend_dir)
    latest_acc = acc.get("latest") if isinstance(acc, dict) else None
    if isinstance(latest_acc, dict) and latest_acc.get("confirm_count") is None:
        day = str(latest_acc.get("day") or last or "")[:10]
        day_items = [item for item in load_outcomes(key, backend_dir=backend_dir) if str(item.get("date") or "")[:10] == day]
        if day_items:
            latest_acc = dict(latest_acc)
            latest_acc["confirm_count"] = sum(int(item.get("predicted_label")) == int(item.get("gold_label")) for item in day_items)
            latest_acc["correct_count"] = len(day_items) - int(latest_acc["confirm_count"])
    days = list(cursor.get("days") or demo_days())
    total_days = len(days)
    if last:
        end = datetime.strptime(last, "%Y-%m-%d").date()
        start = end - timedelta(days=6)
        if fed_days:
            first = datetime.strptime(str(fed_days[0])[:10], "%Y-%m-%d").date()
            if start < first:
                start = first
        window_from, window_to = start.isoformat(), last
    else:
        window_from, window_to = (days[0], days[-1]) if days else (None, None)
    pending = cursor.get("pending_days") if isinstance(cursor.get("pending_days"), dict) else {}
    waiting = sum(1 for item in pending.values() if isinstance(item, dict) and item.get("status") == "waiting")
    expired = sum(
        1 for item in pending.values() if isinstance(item, dict) and item.get("status") == "expired_incomplete"
    )
    return {
        "slot": key,
        "demo": True,
        "clock": {
            "kind": "business_day" if key == "pv_day" else "event_time",
            "day": last,
            "timestamp": f"{last}T21:55:00+00:00" if last else None,
            "source": "loop_demo",
        },
        "progress": {
            "day_index": len(fed_days),
            "total_days": total_days,
            "fed_days": fed_days,
            "exhausted": bool(cursor.get("exhausted")),
        },
        "window": {"from": window_from, "to": window_to},
        "accuracy": latest_acc,
        "feed": {
            "dataset_ref": cursor.get("dataset_ref") or selected_ref,
            "point_progress": cursor.get("point_progress") or {},
            "point_totals": cursor.get("point_totals") or {},
            "pending_days": pending,
            "waiting_days": waiting,
            "expired_days": expired,
        },
        "note": (
            f"演示喂数第 {len(fed_days)}/{total_days or '?'} 天"
            + (f" · 业务日 {last}" if last else " · 尚未喂入")
        ),
    }
