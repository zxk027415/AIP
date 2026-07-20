# -*- coding: utf-8 -*-
"""
合并光伏累计训练数据，并单独导出 mock 喂数源（label 置空）。

输出（相对项目根）：
  backend-service/datasets/pv_cumulative_labeled_merged.parquet  — 有真值，供累计训练登记
  backend-service/datasets/pv_mock_feed_source.parquet           — 无真值，供 mock 喂数 cron

用法：
  cd backend-service
  python scripts/build_pv_dataset_splits.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
OUT_DIR = BACKEND / "datasets"

SOURCES_LABELED = [
    PROJECT / "fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet",
    BACKEND / "datasets/dataset_combined.parquet",
]

KEY_COLS = ["time", "site_id", "device_id", "branch_id"]
OUTPUT_COLS = ["time", "site_id", "device_id", "branch_id", "value", "i_cal", "label"]


def _load_normalized(path: Path, source_name: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_parquet(path)
    missing = [c for c in OUTPUT_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{source_name} 缺少列: {missing}")
    out = df[OUTPUT_COLS].copy()
    out["time"] = pd.to_datetime(out["time"], errors="coerce")
    out["site_id"] = out["site_id"].astype(str)
    out["device_id"] = out["device_id"].astype(str)
    out["branch_id"] = pd.to_numeric(out["branch_id"], errors="coerce")
    out["_source"] = source_name
    return out


def main() -> None:
    frames = []
    for path in SOURCES_LABELED:
        name = path.stem
        frames.append(_load_normalized(path, name))

    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=KEY_COLS, keep="first")
    deduped = before - len(combined)

    labeled = combined[combined["label"].notna()].copy()
    labeled = labeled.drop(columns=["_source"])
    labeled = labeled.sort_values(KEY_COLS).reset_index(drop=True)

    cumulative_path = OUT_DIR / "pv_cumulative_labeled_merged.parquet"
    labeled.to_parquet(cumulative_path, index=False)

    # 喂数源：沿用 dataset_combined 的时间线（7 天），写入时 label 置空
    feed_src = _load_normalized(BACKEND / "datasets/dataset_combined.parquet", "dataset_combined")
    feed_out = feed_src.drop(columns=["_source"]).copy()
    feed_out["label"] = pd.NA
    feed_out = feed_out.sort_values(KEY_COLS).reset_index(drop=True)
    feed_path = OUT_DIR / "pv_mock_feed_source.parquet"
    feed_out.to_parquet(feed_path, index=False)

    summary = {
        "cumulative_labeled_merged": {
            "path": str(cumulative_path.relative_to(PROJECT)).replace("\\", "/"),
            "rows": int(len(labeled)),
            "label_classes": int(labeled["label"].nunique()),
            "time_min": str(labeled["time"].min()),
            "time_max": str(labeled["time"].max()),
            "unique_days": int(labeled["time"].dt.date.nunique()),
            "sources": [str(p.relative_to(PROJECT)).replace("\\", "/") for p in SOURCES_LABELED],
            "deduped_rows": int(deduped),
        },
        "mock_feed_source": {
            "path": str(feed_path.relative_to(PROJECT)).replace("\\", "/"),
            "rows": int(len(feed_out)),
            "label_note": "label 列已全部置空，mock feeder 可直接读取",
            "time_min": str(feed_out["time"].min()),
            "time_max": str(feed_out["time"].max()),
            "unique_days": int(feed_out["time"].dt.date.nunique()),
            "env_override": "设置 PV_MOCK_PARQUET_PATH=datasets/pv_mock_feed_source.parquet 切换喂数源",
        },
        "register_cumulative_training": (
            "在数据集管理页登记: backend-service/datasets/pv_cumulative_labeled_merged.parquet"
        ),
    }
    meta_path = OUT_DIR / "pv_dataset_splits_summary.json"
    meta_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
