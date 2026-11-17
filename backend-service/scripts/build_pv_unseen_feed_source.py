"""
构建「训练集未见过」的 mock 喂数源，用于真实的盲测预测验证。

背景
----
默认喂数源 ``datasets/pv_mock_feed_source.parquet`` 与累计训练集
``datasets/pv_cumulative_labeled_merged.parquet`` **100% 重叠**——两者都由
``fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet`` 产出，
区别仅是喂数源把 ``label`` 置空。用它喂数只能演练链路，不能评估模型效果，
因为预测的全是训练时已见过的样本。

本脚本从 ``enos_fault_diag/test/predict_small.parquet`` 产出一份真正未见过的
喂数源：站点 HRZzKE4v / 设备 3Fh2D94S 的 16 个支路、2021-11-18~11-24 共 7 天，
该设备在累计训练集中完全不存在，因此这是一次**跨设备泛化**盲测。

输出（相对项目根）
------------------
  backend-service/datasets/pv_mock_feed_unseen.parquet
  backend-service/datasets/pv_mock_feed_unseen.parquet.meta.json

不覆盖 ``pv_mock_feed_source.parquet``，可随时切回。

用法
----
  cd backend-service
  python scripts/build_pv_unseen_feed_source.py

切换喂数源（相对 backend-service/ 解析）：
  PV_MOCK_PARQUET_PATH=datasets/pv_mock_feed_unseen.parquet

可选环境变量
------------
  PV_UNSEEN_ALLOW_OVERLAP=1 — 允许与训练集存在重叠（默认重叠即报错退出）
"""
# @AI_GENERATED
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = BACKEND.parent
OUT_DIR = BACKEND / "datasets"

#: 未见过数据的来源。predict_small 本就是无标签预测样例数据。
SOURCE = PROJECT / "fault-diag-algo-release-3.1/enos_fault_diag/test/predict_small.parquet"
#: 累计训练集，用作「已见过」基准。
TRAIN_REF = OUT_DIR / "pv_cumulative_labeled_merged.parquet"
OUT_PATH = OUT_DIR / "pv_mock_feed_unseen.parquet"

#: feeder 实际读取并写库的列（多余列会被 feeder 丢弃，这里提前裁掉）。
FEEDER_COLUMNS = ["time", "site_id", "device_id", "branch_id", "value", "i_cal", "label"]
KEY_COLS = ["time", "site_id", "device_id", "branch_id"]


def _normalize(path: Path, name: str) -> pd.DataFrame:
    """统一列名与键列类型，使跨文件比键可靠。"""
    if not path.exists():
        raise FileNotFoundError(f"{name} 不存在: {path}")
    df = pd.read_parquet(path)
    # 原始导出可能用 data_date / branch 命名
    df = df.rename(columns={"data_date": "time", "branch": "branch_id"})
    missing = [c for c in KEY_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{name} 缺少键列 {missing}，实际列={list(df.columns)}")
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    if getattr(df["time"].dt, "tz", None) is not None:
        df["time"] = df["time"].dt.tz_convert("UTC").dt.tz_localize(None)
    for col in ("site_id", "device_id", "branch_id"):
        df[col] = df[col].astype(str)
    return df


def _keyset(df: pd.DataFrame) -> set:
    return set(map(tuple, df[KEY_COLS].itertuples(index=False, name=None)))


def main() -> int:
    src = _normalize(SOURCE, "predict_small")
    train = _normalize(TRAIN_REF, "pv_cumulative_labeled_merged")

    src_keys = _keyset(src)
    train_keys = _keyset(train)
    overlap = src_keys & train_keys
    allow_overlap = (os.environ.get("PV_UNSEEN_ALLOW_OVERLAP") or "").strip() in {"1", "true", "True"}

    print(f"来源           : {SOURCE.relative_to(PROJECT).as_posix()}")
    print(f"训练集基准     : {TRAIN_REF.relative_to(PROJECT).as_posix()}")
    print(f"来源行数       : {len(src)}   唯一键: {len(src_keys)}")
    print(f"训练集唯一键   : {len(train_keys)}")
    print(f"与训练集重叠键 : {len(overlap)}")

    if overlap and not allow_overlap:
        # 这个门禁是本脚本存在的意义：一旦重叠，盲测就不成立。
        print(
            f"\n[FAIL] 来源与累计训练集存在 {len(overlap)} 个重叠键，盲测前提不成立。\n"
            "       如确认要继续，设 PV_UNSEEN_ALLOW_OVERLAP=1。",
            file=sys.stderr,
        )
        return 2

    out = src.copy()
    for col in FEEDER_COLUMNS:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[FEEDER_COLUMNS]
    # 喂数源必须无标签：模拟数据库新收到的原始观测。
    out["label"] = pd.NA
    out = out.sort_values(KEY_COLS).reset_index(drop=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)

    dates = sorted({d.isoformat() for d in out["time"].dt.date.dropna().unique().tolist()})

    sys.path.insert(0, str(BACKEND))
    from services.db.datasources.pv_fault_mock import write_pv_mock_source_meta

    meta_path = write_pv_mock_source_meta(
        OUT_PATH,
        unique_dates=dates,
        row_count=int(len(out)),
        built_from="predict_small(unseen_by_training)",
    )

    devices = out[["site_id", "device_id", "branch_id"]].drop_duplicates()
    print()
    print(f"已写出       : {OUT_PATH.relative_to(PROJECT).as_posix()}")
    print(f"meta         : {meta_path.relative_to(PROJECT).as_posix()}")
    print(f"行数         : {len(out)}")
    print(f"label 全空   : {bool(out['label'].isna().all())}")
    print(f"自然日 ({len(dates)}): {dates}")
    print(f"设备三元组   : {len(devices)}  (站点 {out['site_id'].nunique()} / 设备 {out['device_id'].nunique()})")
    print(f"预期样本数   : {len(devices)} 支路 x {len(dates)} 天 = {len(devices) * len(dates)}（by_day 口径，未计 min_points 过滤）")
    print()
    print("切换喂数源：PV_MOCK_PARQUET_PATH=datasets/pv_mock_feed_unseen.parquet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# @AI_GENERATED: end
