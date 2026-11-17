# @AI_GENERATED
"""Sample realistic mock datasets from real training data for pv_day / pv_point.

The sampled data comes from the same distribution as the model's training set,
has multiple fault classes, and includes consecutive fault segments suitable for
alarm demonstration.  Gold labels are preserved as ``mock_truth`` but never
exposed to the model at inference time.

Usage::

    from services.slot_datasets.realistic_mock_builder import build_realistic_mock
    info = build_realistic_mock("pv_day", days=7, devices=3)
    # writes  data/slot_datasets/pv_day/loop_demo/unlabeled.parquet
    #         data/slot_datasets/pv_day/loop_demo/mock_truth.parquet
    #         data/slot_datasets/pv_day/loop_demo/manifest.json
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]

# ── source data paths (relative to backend-service/) ─────────────────────────
_DAY_SOURCE = "data/slot_datasets/pv_day/gold/all_labeled_combined.parquet"
_POINT_SOURCE = "data/slot_datasets/pv_point/gold/point-poc-k4-labeled.parquet"

# ── sampling defaults ─────────────────────────────────────────────────────────
_DEFAULT_DAYS = 7
_DEFAULT_DEVICES_DAY = 3            # pv_day: 3 devices (天路径设备天数多)
_DEFAULT_DEVICES_POINT = 8          # pv_point: 8 devices (点路径大部分设备只有 1-2 天)
_MIN_POINTS_PER_DEVICE_DAY = 48     # skip sparse device-days
_MIN_FAULT_DEVICE_DAYS = 2          # guarantee at least 2 device-days with faults
_GENERATION = "realistic-v2"

# ── keys ──────────────────────────────────────────────────────────────────────
_ENTITY_KEYS = ["site_id", "device_id", "branch_id"]
_TIME_COL = "time"
_DATE_COL = "date"

# ── label names (shared with frontend) ────────────────────────────────────────
_LABEL_NAMES: dict[str, str] = {
    "0": "正常",
    "1": "组串失配",
    "2": "组串老化",
    "3": "组串遮挡",
    "4": "旁路二极管故障",
    "6": "接线盒虚焊",
    "7": "热斑效应",
    "8": "PID衰减",
    "9": "逆变器限功率",
    "10": "CT异常",
    "11": "电网波动",
    "12": "组串断路",
    "16": "其他故障",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _demo_dir(slot: str) -> Path:
    return _BACKEND_DIR / "data" / "slot_datasets" / slot / "loop_demo"


def _load_source(slot: str, *, backend_dir: Optional[Path] = None) -> pd.DataFrame:
    root = Path(backend_dir) if backend_dir else _BACKEND_DIR
    rel = _DAY_SOURCE if slot == "pv_day" else _POINT_SOURCE
    path = root / rel
    if not path.is_file():
        raise FileNotFoundError(f"Source data not found: {rel}")
    df = pd.read_parquet(path)
    if "label" not in df.columns:
        raise ValueError(f"Source data missing 'label' column: {rel}")
    # ensure date column
    if _DATE_COL not in df.columns:
        df[_DATE_COL] = pd.to_datetime(df[_TIME_COL], errors="coerce", utc=True).dt.strftime("%Y-%m-%d")
    else:
        df[_DATE_COL] = df[_DATE_COL].astype(str).str[:10]
    return df


def _pick_devices(df: pd.DataFrame, n: int, seed: int) -> list[tuple[str, str, str]]:
    """Pick *n* devices, preferring those with many days AND both normal + fault labels."""
    rng = np.random.RandomState(seed)
    device_groups = df.groupby(_ENTITY_KEYS)

    # score each device: (has_both_classes, day_count, point_count)
    scored: list[tuple[float, tuple[str, str, str]]] = []
    for keys, group in device_groups:
        tup = tuple(str(k) for k in (keys if isinstance(keys, tuple) else (keys,)))
        labeled = group.dropna(subset=["label"])
        if len(labeled) < _MIN_POINTS_PER_DEVICE_DAY:
            continue
        labels = set(labeled["label"].astype(int).unique())
        has_fault = bool(labels - {0})
        has_normal = 0 in labels
        day_count = group[_DATE_COL].nunique() if _DATE_COL in group.columns else 1
        # score: prefer both classes > fault-only > normal-only; then by day count
        class_score = 3.0 if (has_fault and has_normal) else (2.0 if has_fault else 1.0)
        # small random jitter to avoid always picking the same devices
        jitter = rng.random() * 0.5
        score = class_score * 100 + day_count * 10 + jitter
        scored.append((score, tup))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [tup for _, tup in scored[:n]]


def _pick_days(df: pd.DataFrame, device_keys: list[tuple], n_days: int, seed: int, *, slot: str = "pv_day") -> list[str]:
    """Pick up to n_days calendar days that have data for selected devices.

    For pv_day: tries to find a consecutive window with fault coverage.
    For pv_point: takes the union of all devices' days (data is naturally sparse).
    """
    rng = np.random.RandomState(seed + 1)
    # build device-day inventory
    mask = pd.Series(False, index=df.index)
    for keys in device_keys:
        dev_mask = pd.Series(True, index=df.index)
        for col, val in zip(_ENTITY_KEYS, keys):
            dev_mask &= df[col].astype(str) == val
        mask |= dev_mask
    subset = df[mask].copy()
    subset[_DATE_COL] = subset[_DATE_COL].astype(str).str[:10]
    all_days = sorted(subset[_DATE_COL].unique())

    if slot == "pv_point":
        # pv_point: data is sparse per device — just take all available days up to n_days
        if len(all_days) <= n_days:
            return all_days
        # prefer days where more devices have data
        day_device_count = subset.groupby(_DATE_COL).apply(
            lambda g: g.groupby(_ENTITY_KEYS).ngroups
        ).to_dict()
        ranked = sorted(all_days, key=lambda d: day_device_count.get(d, 0), reverse=True)
        return sorted(ranked[:n_days])

    # pv_day: try consecutive window
    if len(all_days) < n_days:
        return all_days
    best_window = None
    best_fault_count = 0
    for start_idx in range(len(all_days) - n_days + 1):
        window = all_days[start_idx:start_idx + n_days]
        win_data = subset[subset[_DATE_COL].isin(set(window))]
        fault_device_days = win_data[win_data["label"].dropna().astype(int) != 0].groupby(
            _ENTITY_KEYS + [_DATE_COL]
        ).ngroups
        if fault_device_days >= _MIN_FAULT_DEVICE_DAYS:
            if best_window is None or rng.random() < 0.3:
                best_window = window
                best_fault_count = fault_device_days
    if best_window is not None:
        return list(best_window)
    return all_days[-n_days:]


def build_realistic_mock(
    slot: str,
    *,
    days: int = _DEFAULT_DAYS,
    devices: Optional[int] = None,
    seed: int = 42,
    backend_dir: Optional[Path] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Sample mock data from real training data and write to loop_demo directory.

    Returns manifest dict with sampling metadata.
    """
    if slot not in ("pv_day", "pv_point"):
        raise ValueError(f"slot must be pv_day or pv_point, got {slot!r}")
    if devices is None:
        devices = _DEFAULT_DEVICES_POINT if slot == "pv_point" else _DEFAULT_DEVICES_DAY

    root = Path(backend_dir) if backend_dir else _BACKEND_DIR
    folder = root / "data" / "slot_datasets" / slot / "loop_demo"
    manifest_path = folder / "manifest.json"

    # idempotency: skip if already built with same generation
    if not force and manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if str(existing.get("generation") or "") == _GENERATION:
                logger.info("[realistic_mock] %s already built (gen=%s), skipping", slot, _GENERATION)
                return existing
        except (OSError, json.JSONDecodeError):
            pass

    source = _load_source(slot, backend_dir=root)
    selected_devices = _pick_devices(source, devices, seed)
    selected_days = _pick_days(source, selected_devices, days, seed, slot=slot)

    # filter source to selected devices + days
    mask = pd.Series(False, index=source.index)
    for keys in selected_devices:
        dev_mask = pd.Series(True, index=source.index)
        for col, val in zip(_ENTITY_KEYS, keys):
            dev_mask &= source[col].astype(str) == val
        mask |= dev_mask
    subset = source[mask].copy()
    subset[_DATE_COL] = subset[_DATE_COL].astype(str).str[:10]
    subset = subset[subset[_DATE_COL].isin(set(selected_days))].copy()
    subset = subset.sort_values([_DATE_COL, *_ENTITY_KEYS, _TIME_COL]).reset_index(drop=True)
    # drop rows with NaN label — mock truth must have labels
    subset = subset.dropna(subset=["label"]).reset_index(drop=True)
    subset["label"] = subset["label"].astype(int)

    if subset.empty:
        raise ValueError(f"No data after sampling for {slot} with {devices} devices × {days} days")

    # label distribution
    label_col = subset["label"].dropna()
    label_dist = label_col.astype(int).value_counts().to_dict()
    device_day_groups = subset.groupby(_ENTITY_KEYS + [_DATE_COL])
    fault_device_days = sum(
        1 for _, g in device_day_groups if (g["label"].dropna().astype(int) != 0).any()
    )

    # write files
    folder.mkdir(parents=True, exist_ok=True)
    truth_path = folder / "mock_truth.parquet"
    unlabeled_path = folder / "unlabeled.parquet"
    gold_path = folder / "gold.parquet"

    subset.to_parquet(truth_path, index=False)
    # also write as gold.parquet for _auto_review_session compatibility
    subset.to_parquet(gold_path, index=False)
    unlabeled = subset.drop(columns=["label"])
    unlabeled.to_parquet(unlabeled_path, index=False)

    manifest = {
        "slot": slot,
        "generation": _GENERATION,
        "mode": "realistic",
        "source": _DAY_SOURCE if slot == "pv_day" else _POINT_SOURCE,
        "start_day": selected_days[0] if selected_days else None,
        "days": selected_days,
        "devices": ["|".join(d) for d in selected_devices],
        "device_count": len(selected_devices),
        "total_rows": int(len(subset)),
        "points_per_device_day": int(len(subset) / max(len(selected_devices) * len(selected_days), 1)),
        "label_distribution": {str(k): int(v) for k, v in sorted(label_dist.items())},
        "label_names": _LABEL_NAMES,
        "fault_device_days": fault_device_days,
        "total_device_days": device_day_groups.ngroups,
        "seed": seed,
        "note": "从真实训练数据采样，多类故障，用于真实模型推理验证。label 在 mock_truth.parquet 中。",
        "built_at": _now_iso(),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # clean stale feed state
    for name in ("arrived.parquet", "outcomes.json", "daily_accuracy.json"):
        p = folder / name
        if p.is_file():
            p.unlink()
    # @AI_GENERATED
    # write fresh feed_cursor with realistic days
    cursor = {
        "slot": slot,
        "days": selected_days,
        "fed_days": [],
        "last_fed_day": None,
        "exhausted": False,
        "updated_at": _now_iso(),
        "mode": "realistic",
    }
    cursor_path = folder / "feed_cursor.json"
    cursor_path.write_text(
        json.dumps(cursor, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    # @AI_GENERATED: end

    logger.info(
        "[realistic_mock] built %s: %d rows, %d devices, %d days, %d fault device-days",
        slot, len(subset), len(selected_devices), len(selected_days), fault_device_days,
    )
    return manifest
# @AI_GENERATED: end
