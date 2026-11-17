# -*- coding: utf-8 -*-
"""Audit PV-related datasets: labeled vs unlabeled split for cumulative training vs mock feed."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent

TARGETS = [
    {
        "id": "all_labeled_combined",
        "path": PROJECT / "fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet",
        "role_hint": "legacy labeled reference",
    },
    {
        "id": "dataset_combined",
        "path": BACKEND / "datasets/dataset_combined.parquet",
        "role_hint": "mock feed + current cumulative import",
    },
]

TRAIN_ORI_DIR = BACKEND / "datasets/相关数据/train_ori"


def _summarize_frame(df: pd.DataFrame, source_id: str) -> dict:
    out: dict = {"source_id": source_id, "rows": int(len(df)), "columns": list(df.columns)}
    if "time" in df.columns:
        t = pd.to_datetime(df["time"], errors="coerce")
        out["time_min"] = str(t.min())
        out["time_max"] = str(t.max())
        out["unique_days"] = int(t.dt.date.nunique())
    for col in ("site_id", "device_id", "branch_id"):
        if col in df.columns:
            out[f"unique_{col}"] = int(df[col].nunique(dropna=True))
    if "label" in df.columns:
        labeled = df[df["label"].notna()].copy()
        unlabeled = df[df["label"].isna()].copy()
        out["labeled_rows"] = int(len(labeled))
        out["unlabeled_rows"] = int(len(unlabeled))
        out["labeled_pct"] = round(100 * len(labeled) / max(len(df), 1), 4)
        out["label_classes"] = int(labeled["label"].nunique()) if len(labeled) else 0
        out["label_distribution"] = {
            str(k): int(v)
            for k, v in labeled["label"].value_counts().head(20).items()
        }
        if len(labeled) and "time" in labeled.columns:
            lt = pd.to_datetime(labeled["time"], errors="coerce")
            out["labeled_time_min"] = str(lt.min())
            out["labeled_time_max"] = str(lt.max())
            out["labeled_unique_days"] = int(lt.dt.date.nunique())
        if len(unlabeled) and "time" in unlabeled.columns:
            ut = pd.to_datetime(unlabeled["time"], errors="coerce")
            out["unlabeled_time_min"] = str(ut.min())
            out["unlabeled_time_max"] = str(ut.max())
            out["unlabeled_unique_days"] = int(ut.dt.date.nunique())
    else:
        out["labeled_rows"] = 0
        out["unlabeled_rows"] = int(len(df))
        out["note"] = "no label column"
    return out


def _peek_csv(path: Path) -> dict:
    try:
        df = pd.read_csv(path, nrows=5)
    except Exception as exc:
        return {"path": str(path.relative_to(PROJECT)).replace("\\", "/"), "error": str(exc)}
    return {
        "path": str(path.relative_to(PROJECT)).replace("\\", "/"),
        "columns": list(df.columns),
        "has_label": "label" in df.columns,
    }


def main() -> None:
    reports = []
    for item in TARGETS:
        p: Path = item["path"]
        entry = {
            "source_id": item["id"],
            "relative_path": str(p.relative_to(PROJECT)).replace("\\", "/"),
            "exists": p.exists(),
            "role_hint": item["role_hint"],
        }
        if p.exists():
            df = pd.read_parquet(p)
            entry.update(_summarize_frame(df, item["id"]))
            entry["file_size_mb"] = round(p.stat().st_size / (1024 * 1024), 2)
        reports.append(entry)

    csv_files = sorted(TRAIN_ORI_DIR.glob("*.csv")) if TRAIN_ORI_DIR.exists() else []
    csv_peek = [_peek_csv(p) for p in csv_files]

    # Cross-check overlap between the two parquets on key dimensions if both exist
    overlap = {}
    p1 = PROJECT / "fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet"
    p2 = BACKEND / "datasets/dataset_combined.parquet"
    if p1.exists() and p2.exists():
        a = pd.read_parquet(p1, columns=["time", "site_id", "device_id", "branch_id", "label"])
        b = pd.read_parquet(p2, columns=["time", "site_id", "device_id", "branch_id", "label"])
        a["time"] = pd.to_datetime(a["time"], errors="coerce")
        b["time"] = pd.to_datetime(b["time"], errors="coerce")
        key_cols = ["time", "site_id", "device_id", "branch_id"]
        a_keys = set(map(tuple, a[key_cols].itertuples(index=False, name=None)))
        b_keys = set(map(tuple, b[key_cols].itertuples(index=False, name=None)))
        overlap = {
            "all_labeled_keys": len(a_keys),
            "dataset_combined_keys": len(b_keys),
            "intersection_keys": len(a_keys & b_keys),
            "all_labeled_only_keys": len(a_keys - b_keys),
            "dataset_combined_only_keys": len(b_keys - a_keys),
            "all_labeled_all_have_label": bool(a["label"].notna().all()),
            "dataset_combined_labeled_rows": int(b["label"].notna().sum()),
            "dataset_combined_unlabeled_rows": int(b["label"].isna().sum()),
        }

    result = {
        "parquet_reports": reports,
        "train_ori_csv_count": len(csv_files),
        "train_ori_csv_peek": csv_peek[:5],
        "train_ori_csv_peek_note": f"showing first 5 of {len(csv_files)} files",
        "overlap": overlap,
        "recommendation": {
            "cumulative_training_candidates": [
                "fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet (if all rows labeled)",
                "backend-service/datasets/dataset_combined.parquet rows where label IS NOT NULL",
            ],
            "mock_feed_candidates": [
                "backend-service/datasets/dataset_combined.parquet rows where label IS NULL",
            ],
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
