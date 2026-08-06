# @AI_GENERATED
"""
构建 2021-11-18~24 待标注批次（优先级 1）。

背景（见 data/tsc_experiments/expansion_and_variance_report.json）：
  - 主数据集 pv_cumulative_labeled_merged.parquet 只有 35 个日期、散落 10 个不连续簇，
    唯一能做时间切分验证的块是 dataset_combined（2020-05-06~12，7 天，单站点 241 设备）。
  - 时间切分口径下 macro F1 方差高达 std=0.075（10 种子），根因是评估块只有一个、
    设备只有 241 台、测试期只有 3 天。
  - train_ori 下有 552,664 行未标注数据。其中 2021-11-18~24 是**7 天全连续**且有
    5 个未标注站点，标注后可得第二个连续多站点评估块，直接降低上述方差。

本脚本做什么：
  1. 从 train_ori 收集覆盖 2021-11-18~24 的所有源，归一化到标准 schema
  2. 剔除已存在于主数据集的行（按 site_id|device_id|branch_id|time 主键）
  3. 按主键去重
  4. 落盘为 parquet（label 列留空），供 POST /api/iterative-labeling/review-sessions/from-dataset 消费
  5. 打印可标注单元数（设备×日期）与逐日/逐站点分布，便于评估标注工作量

用法：
    conda activate cp_web
    cd backend-service
    python scripts/build_pv_2021_11_labeling_batch.py            # 干跑，只报告不落盘
    python scripts/build_pv_2021_11_labeling_batch.py --write    # 落盘

输出路径（相对项目根，符合 relative-paths-only 约定）：
    backend-service/datasets/pv_labeling_batch_2021_11.parquet
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# backend-service 目录（本脚本位于 backend-service/scripts/）
_BACKEND = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _BACKEND.parent

BLOCK_START = pd.Timestamp("2021-11-18").date()
BLOCK_END = pd.Timestamp("2021-11-24").date()

TRAIN_ORI_GLOB = str(_BACKEND / "datasets" / "相关数据" / "train_ori" / "*.csv")
MAIN_DATASET = _BACKEND / "datasets" / "pv_cumulative_labeled_merged.parquet"
OUT_PATH = _BACKEND / "datasets" / "pv_labeling_batch_2021_11.parquet"
OUT_META = _BACKEND / "datasets" / "pv_labeling_batch_2021_11.parquet.meta.json"

# from-dataset 端点必需 device_id + time；波形展示需要 value / i_cal
REQUIRED_COLS = ["time", "site_id", "device_id", "branch_id", "value", "i_cal"]


def _rel(p: Path) -> str:
    """转成相对项目根的路径（写入元数据用，禁止绝对路径）。"""
    try:
        return str(p.relative_to(_PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p)


def load_train_ori(path: str) -> pd.DataFrame | None:
    """train_ori 长表 -> 标准 schema。列名约定：data_date=时间戳, branch=支路。"""
    df = pd.read_csv(path)
    df = df.drop(columns=[c for c in df.columns if str(c).startswith("Unnamed")], errors="ignore")
    df = df.rename(columns={"data_date": "time", "branch": "branch_id"})
    # 原 date 列是字符串日期，统一从 time 重算，避免格式不一致
    if "date" in df.columns:
        df = df.drop(columns=["date"])
    if "time" not in df.columns or "device_id" not in df.columns:
        return None
    if "branch_id" not in df.columns:
        df["branch_id"] = 1
    if "site_id" not in df.columns:
        df["site_id"] = Path(path).stem
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])
    for c in ("value", "i_cal"):
        if c not in df.columns:
            df[c] = np.nan
    df["date"] = df["time"].dt.date
    keep = REQUIRED_COLS + ["date"] + (["label"] if "label" in df.columns else [])
    return df[keep]


def main() -> int:
    ap = argparse.ArgumentParser(description="构建 2021-11-18~24 待标注批次")
    ap.add_argument("--write", action="store_true", help="落盘（默认只干跑报告）")
    ap.add_argument("--include-labeled", action="store_true",
                    help="保留已有标签的行（默认剔除，只输出待标注部分）")
    args = ap.parse_args()

    print("=" * 78)
    print(f"构建待标注批次: {BLOCK_START} ~ {BLOCK_END}（7 天全连续）")
    print("=" * 78)

    if not MAIN_DATASET.exists():
        print(f"[ERROR] 主数据集不存在: {_rel(MAIN_DATASET)}")
        return 1

    # ---------- 1. 主数据集主键集合（用于剔除已有行） ----------
    main = pd.read_parquet(MAIN_DATASET, columns=["time", "site_id", "device_id", "branch_id"])
    main["time"] = pd.to_datetime(main["time"])
    main_keys = set(zip(
        main["site_id"].astype(str), main["device_id"].astype(str),
        main["branch_id"].astype(str), main["time"].values,
    ))
    print(f"主数据集: {len(main):,} 行 / {len(main_keys):,} 唯一主键")

    # ---------- 2. 收集覆盖目标区间的源 ----------
    parts, contributors = [], []
    for f in sorted(glob.glob(TRAIN_ORI_GLOB)):
        df = load_train_ori(f)
        if df is None:
            print(f"  跳过（schema 不匹配）: {Path(f).name}")
            continue
        sub = df[(df["date"] >= BLOCK_START) & (df["date"] <= BLOCK_END)]
        if sub.empty:
            continue
        has_label = "label" in sub.columns and sub["label"].notna().any()
        parts.append(sub)
        contributors.append({
            "file": Path(f).name, "rows": int(len(sub)),
            "devices": int(sub["device_id"].nunique()),
            "days": int(sub["date"].nunique()),
            "has_label": bool(has_label),
        })
        print(f"  纳入 {Path(f).name:<38} rows={len(sub):>7,} "
              f"dev={sub['device_id'].nunique():>4} days={sub['date'].nunique()} "
              f"label={'有' if has_label else '无'}")

    if not parts:
        print("[ERROR] 目标区间内没有找到任何数据源")
        return 1

    blk = pd.concat(parts, ignore_index=True)
    print(f"\n拼合后: {len(blk):,} 行")

    # ---------- 3. 按主键去重 ----------
    before = len(blk)
    blk = blk.drop_duplicates(subset=["site_id", "device_id", "branch_id", "time"])
    print(f"主键去重: {before:,} -> {len(blk):,} (去掉 {before - len(blk):,})")

    # ---------- 4. 剔除已在主数据集的行 ----------
    keys = list(zip(
        blk["site_id"].astype(str), blk["device_id"].astype(str),
        blk["branch_id"].astype(str), blk["time"].values,
    ))
    already = np.fromiter((k in main_keys for k in keys), dtype=bool, count=len(keys))
    print(f"已在主数据集: {already.sum():,} 行 ({already.mean() * 100:.2f}%) -> 剔除")
    blk = blk[~already].copy()
    if blk.empty:
        print("[WARN] 剔除后为空：该区间数据已全部在主数据集内，无需标注")
        return 0

    # ---------- 5. 处理已有标签的行 ----------
    if "label" in blk.columns:
        n_lab = int(blk["label"].notna().sum())
        if n_lab and not args.include_labeled:
            print(f"剔除已有标签的行: {n_lab:,}（用 --include-labeled 保留）")
            blk = blk[blk["label"].isna()]
        elif n_lab:
            print(f"保留已有标签的行: {n_lab:,}")
    # 输出统一带空 label 列，供标注写入
    blk["label"] = pd.NA

    if blk.empty:
        print("[WARN] 剔除后为空")
        return 0

    # ---------- 6. 报告 ----------
    blk = blk.sort_values(["site_id", "device_id", "branch_id", "time"]).reset_index(drop=True)
    unit_cols = ["site_id", "device_id", "branch_id", "date"]
    n_units = blk.drop_duplicates(subset=unit_cols).shape[0]
    days = sorted(blk["date"].unique())

    print("\n" + "-" * 78)
    print(f"待标注批次汇总")
    print("-" * 78)
    print(f"  行数        : {len(blk):,}")
    print(f"  站点数      : {blk['site_id'].nunique()}")
    print(f"  设备数      : {blk['device_id'].nunique()}")
    print(f"  序列数      : {blk.groupby(['site_id','device_id','branch_id']).ngroups}")
    print(f"  日期        : {len(days)} 天 ({days[0]} ~ {days[-1]})")
    print(f"  ★ 可标注单元 (设备×日期): {n_units:,}")
    print(f"\n  逐日行数: { {str(k): int(v) for k, v in blk['date'].value_counts().sort_index().items()} }")
    print(f"  逐站点设备数: { blk.groupby('site_id')['device_id'].nunique().to_dict() }")
    nan_ratio = blk[["value", "i_cal"]].isna().mean().round(4).to_dict()
    print(f"  value/i_cal 缺失率: {nan_ratio}")

    # 连续性校验：目标是 7 天全连续
    gaps = [str(b) for a, b in zip(days, days[1:]) if (b - a).days != 1]
    print(f"  日期连续性: {'连续' if not gaps else f'存在断点，断在 {gaps}'}")

    # ---------- 7. 落盘 ----------
    if not args.write:
        print(f"\n[干跑] 未落盘。加 --write 写入 {_rel(OUT_PATH)}")
        return 0

    out_df = blk[REQUIRED_COLS + ["label"]].copy()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_parquet(OUT_PATH, index=False)

    meta = {
        "_comment": "@AI_GENERATED",
        "purpose": "2021-11-18~24 待人工标注批次（补第二个连续多站点评估块，降低时间切分口径的方差）",
        "dataset_path_relative": _rel(OUT_PATH),
        "block_start": str(BLOCK_START),
        "block_end": str(BLOCK_END),
        "rows": int(len(out_df)),
        "n_sites": int(blk["site_id"].nunique()),
        "n_devices": int(blk["device_id"].nunique()),
        "n_series": int(blk.groupby(["site_id", "device_id", "branch_id"]).ngroups),
        "n_days": len(days),
        "days": [str(d) for d in days],
        "dates_consecutive": not gaps,
        "labelable_units_device_x_day": int(n_units),
        "rows_per_day": {str(k): int(v) for k, v in blk["date"].value_counts().sort_index().items()},
        "devices_per_site": {str(k): int(v) for k, v in blk.groupby("site_id")["device_id"].nunique().items()},
        "value_icat_nan_ratio": {k: float(v) for k, v in nan_ratio.items()},
        "contributors": contributors,
        "excluded_rows_already_in_main": int(already.sum()),
        "how_to_start_labeling": {
            "endpoint": "POST /api/iterative-labeling/review-sessions/from-dataset",
            "body": {
                "dataset_path": _rel(OUT_PATH),
                "slot": "pv_fault",
                "reviewer": "<标注人>",
                "max_units": n_units,
            },
            "note": "dataset_path 必须是相对项目根的路径；端点会按 (site_id, device_id, branch_id, 日期) 聚合成标注单元",
        },
        "_comment_end": "@AI_GENERATED: end",
    }
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n[已落盘] {_rel(OUT_PATH)}  ({OUT_PATH.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"[元数据] {_rel(OUT_META)}")
    print(f"\n下一步：调用 POST /api/iterative-labeling/review-sessions/from-dataset")
    print(f"  dataset_path = {_rel(OUT_PATH)}")
    print(f"  预计生成 {n_units:,} 个待标注单元")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
