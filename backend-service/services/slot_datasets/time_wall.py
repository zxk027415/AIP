"""Fixed calendar-day time wall: last 20% labeled business days are holdout.

Persisted per slot so mock scoring and cumulative freeze share one locked wall.
Train/freeze keep rows with calendar day < holdout_start_day.
Mock scores only rows on or after that day. Features may still read history
to the left of the wall; the predicted unit's label must not have been trained on.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

HOLD_OUT_DAY_FRACTION = 0.20
MIN_HOLDOUT_UNITS = 4
MIN_CLASS_SUPPORT = 2
MIN_PROMOTE_UNITS = 30

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_GOLD_REL = {
    "pv_day": "data/slot_datasets/pv_day/gold/all_labeled_combined.parquet",
    "pv_point": "data/slot_datasets/pv_point/gold/point-poc-k4-labeled.parquet",
}


def time_wall_rel_path(slot: str) -> str:
    return f"data/slot_datasets/{str(slot).strip()}/time_wall.json"


def _root(backend_dir: Path | None = None) -> Path:
    return Path(backend_dir) if backend_dir is not None else _BACKEND_DIR


def _wall_abs(slot: str, backend_dir: Path | None = None) -> Path:
    return _root(backend_dir) / time_wall_rel_path(slot)


def calendar_day_of(value: Any) -> str:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.notna(parsed):
        return parsed.strftime("%Y-%m-%d")
    raw = str(value or "").strip()
    return raw[:10] if len(raw) >= 10 else raw


def _stamp_series(frame: pd.DataFrame) -> pd.Series:
    if "time" in frame.columns:
        return frame["time"]
    if "time_window" in frame.columns:
        return frame["time_window"]
    if "date" in frame.columns:
        return frame["date"]
    return pd.Series([pd.NaT] * len(frame), index=frame.index)


def calendar_day_series(frame: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(_stamp_series(frame), utc=True, errors="coerce").dt.strftime("%Y-%m-%d")


def unique_labeled_days(frame: pd.DataFrame) -> list[str]:
    if frame is None or frame.empty:
        return []
    work = frame
    if "label" in work.columns:
        work = work.dropna(subset=["label"])
    if work.empty:
        return []
    days = calendar_day_series(work).dropna()
    return sorted(
        {
            str(day)
            for day in days
            if str(day) not in {"NaT", "None", "nan", ""} and len(str(day)) == 10
        }
    )


def wall_from_days(
    days: list[str],
    *,
    fraction: float = HOLD_OUT_DAY_FRACTION,
) -> Optional[dict[str, Any]]:
    ordered = sorted(day for day in days if day)
    n = len(ordered)
    if n == 0:
        return None
    holdout_n = max(1, math.ceil(n * float(fraction)))
    holdout_days = ordered[-holdout_n:]
    train_days = ordered[:-holdout_n]
    return {
        "fraction": float(fraction),
        "labeled_day_count": n,
        "holdout_day_count": holdout_n,
        "train_day_count": len(train_days),
        "holdout_start_day": holdout_days[0],
        "holdout_end_day": holdout_days[-1],
        "train_start_day": train_days[0] if train_days else None,
        "train_end_day": train_days[-1] if train_days else None,
    }


def rows_before_wall(frame: pd.DataFrame, holdout_start_day: str) -> pd.DataFrame:
    if frame is None or frame.empty or not str(holdout_start_day or "").strip():
        return frame.copy() if frame is not None else pd.DataFrame()
    days = calendar_day_series(frame)
    return frame.loc[days < str(holdout_start_day)].copy()


def rows_on_or_after_wall(frame: pd.DataFrame, holdout_start_day: str) -> pd.DataFrame:
    if frame is None or frame.empty or not str(holdout_start_day or "").strip():
        return frame.iloc[0:0].copy() if frame is not None else pd.DataFrame()
    days = calendar_day_series(frame)
    return frame.loc[days >= str(holdout_start_day)].copy()


def load_time_wall(slot: str, *, backend_dir: Path | None = None) -> Optional[dict[str, Any]]:
    path = _wall_abs(slot, backend_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not str(payload.get("holdout_start_day") or "").strip():
        return None
    return payload


def save_time_wall(slot: str, payload: dict[str, Any], *, backend_dir: Path | None = None) -> dict[str, Any]:
    path = _wall_abs(slot, backend_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = dict(payload)
    out["slot"] = str(slot).strip()
    out["locked"] = True
    out["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _read_gold_time_label(abs_path: Path) -> Optional[pd.DataFrame]:
    if not abs_path.is_file():
        return None
    suffix = abs_path.suffix.lower()
    try:
        if suffix == ".parquet":
            try:
                return pd.read_parquet(abs_path, columns=["time", "label"])
            except Exception:
                return pd.read_parquet(abs_path)
        if suffix in {".csv", ".txt"}:
            return pd.read_csv(abs_path, encoding="utf-8")
    except Exception:
        return None
    return None


def compute_time_wall_from_frame(slot: str, frame: pd.DataFrame) -> Optional[dict[str, Any]]:
    spec = wall_from_days(unique_labeled_days(frame))
    if spec is None:
        return None
    spec["slot"] = str(slot).strip()
    spec["source"] = "gold_labeled_days"
    return spec


def ensure_time_wall(
    slot: str,
    gold: pd.DataFrame | None = None,
    *,
    gold_path: str | None = None,
    backend_dir: Path | None = None,
) -> Optional[dict[str, Any]]:
    """Return the locked wall; compute once from gold labeled days if missing."""
    root = _root(backend_dir)
    existing = load_time_wall(slot, backend_dir=root)
    if existing is not None:
        return existing
    frame = gold
    rel = str(gold_path or "").replace("\\", "/").strip() or _GOLD_REL.get(str(slot).strip())
    if frame is None and rel:
        frame = _read_gold_time_label(root / rel)
    if frame is None:
        return None
    spec = compute_time_wall_from_frame(slot, frame)
    if spec is None:
        return None
    if rel:
        spec["gold_path"] = rel
    return save_time_wall(slot, spec, backend_dir=root)


def class_support_from_pairs(pairs: list[tuple[int, int]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _pred, truth in pairs:
        key = str(int(truth))
        counts[key] = counts.get(key, 0) + 1
    return counts
