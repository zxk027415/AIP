"""Build unlabeled labeling-demo CSVs (relative paths, no label column)."""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

_BACKEND = Path(__file__).resolve().parents[1]


def _bell(index: int, peak: float = 8.0) -> float:
    x = (index - 48) / 22.0
    return max(0.05, peak * math.exp(-0.5 * x * x))


def _emit(site: str, device: str, branch: str, kind: str, times: pd.DatetimeIndex) -> list[dict]:
    rows: list[dict] = []
    for index, stamp in enumerate(times):
        ical = _bell(index)
        if kind == "normal":
            value = ical * 0.97
        elif kind == "shade":
            value = ical * (0.35 if 36 <= index <= 52 else 0.96)
        elif kind == "mismatch":
            value = ical * 0.62
        else:
            value = ical * (1.8 if index in (40, 41, 42) else 0.95)
        rows.append(
            {
                "time": stamp.strftime("%Y-%m-%dT%H:%M:%S"),
                "site_id": site,
                "device_id": device,
                "branch_id": branch,
                "value": round(value, 4),
                "i_cal": round(ical, 4),
            }
        )
    return rows


def main() -> None:
    times = pd.date_range("2024-03-01 08:00", periods=96, freq="5min")
    specs = {
        "pv_point": [
            ("demo_point", "inv1", "1", "normal"),
            ("demo_point", "inv1", "2", "shade"),
            ("demo_point", "inv2", "1", "mismatch"),
            ("demo_point", "inv2", "2", "spike"),
        ],
        "pv_day": [
            ("demo_day", "box1", "1", "normal"),
            ("demo_day", "box1", "2", "shade"),
            ("demo_day", "box2", "1", "mismatch"),
            ("demo_day", "box2", "2", "spike"),
        ],
    }
    for slot, devices in specs.items():
        rows: list[dict] = []
        for spec in devices:
            rows.extend(_emit(*spec, times))
        out_dir = _BACKEND / "data" / "slot_datasets" / slot / "unlabeled"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "labeling_demo_unlabeled.csv"
        frame = pd.DataFrame(rows)
        assert "label" not in frame.columns
        frame.to_csv(path, index=False, encoding="utf-8")
        rel = path.relative_to(_BACKEND).as_posix()
        print(f"{slot} {rel} rows={len(frame)}")


if __name__ == "__main__":
    main()
