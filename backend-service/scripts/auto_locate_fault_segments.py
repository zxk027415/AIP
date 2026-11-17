# -*- coding: utf-8 -*-
"""
scripts/auto_locate_fault_segments.py — 同期对标故障候选导出（只读）

**用途**：把天级标签细化为待人工复核的子天候选段。脚本只读取数据并导出
CSV/JSON 候选报告，绝不写 ``point_label_ops``、``point_labels`` 或伴生正常点。
候选具有稳定 ``source_candidate_id``、``proposed_label_id``、``review_status``
和 ``algorithm_version``，批准后的真值写入由独立审核 API 负责。

**方法**：见 `services/iterative_labeling/peer_residual_locator.py` 模块文档。
一句话：用同站点同时刻其他设备的中位数作基准，残差 = 本设备值/基准值，
残差持续低于阈值的连续区间即候选故障段。天气影响被中位数吸收，不会误报。

用法::

    # 导出候选和报告（始终不写数据库）
    python scripts/auto_locate_fault_segments.py

    # 抽查若干案例的残差明细
    python scripts/auto_locate_fault_segments.py --inspect 20
"""

# @AI_GENERATED
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.iterative_labeling.peer_residual_locator import (  # noqa: E402
    LocatorConfig,
    PeerResidualLocator,
    segments_to_dataframe,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("auto_locate")

DEFAULT_DATASET = "datasets/pv_cumulative_labeled_merged.parquet"
DEFAULT_OUT_DIR = "data/auto_located_segments"


def _load_dataset(rel_path: str) -> pd.DataFrame:
    """按相对路径加载数据集（相对 backend-service，符合项目路径规范）。"""
    p = Path(rel_path)
    if not p.is_absolute():
        p = _BACKEND / rel_path
    if not p.exists():
        raise FileNotFoundError(f"数据集不存在: {rel_path}")
    cols = ["site_id", "device_id", "branch_id", "time", "value", "i_cal", "label"]
    df = pd.read_parquet(p, columns=cols)
    df["time"] = pd.to_datetime(df["time"])
    logger.info("已加载 %s: %d 行", rel_path, len(df))
    return df


def _print_report(report: dict, seg_df: pd.DataFrame) -> None:
    stats = report["stats"]
    print("=" * 78)
    print("同期对标故障段定位 — 运行报告")
    print("=" * 78)
    print(f"  设备-天总数                  = {stats['device_days_total']}")
    print(f"  跳过：标签在跳过名单(0/2)    = {stats['skipped_label_in_skiplist']}")
    print(f"  跳过：稀有标签(天数<10)      = {stats['skipped_rare_label']}")
    print(f"  跳过：对照组不足(<5 序列)    = {stats['skipped_small_peer_group']}")
    print(f"  跳过：白天有效点不足         = {stats['skipped_few_daylight_points']}")
    print(f"  跳过：故障占比越界(整天/噪声)= {stats['skipped_fault_ratio_out_of_range']}")
    print(f"  跳过：无有效连续段           = {stats['skipped_no_segment']}")
    print(f"  ★ 成功定位的设备-天          = {stats['located']}")
    print()
    print(f"  产出候选段总数               = {report['n_segments']}")
    print(f"    高置信 (mean_residual<0.5) = {report['n_high_confidence']}")
    print(f"    中置信 (0.5~0.7)           = {report['n_medium_confidence']}")

    if seg_df.empty:
        print("\n  未产出任何候选段。")
        return

    print()
    print("-" * 78)
    print("按 label 分布")
    print("-" * 78)
    g = seg_df.groupby("label").agg(
        段数=("n_points", "size"),
        设备天数=("date", "nunique"),
        中位段长点数=("n_points", "median"),
        中位残差=("mean_residual", "median"),
        高置信段数=("confidence", lambda s: int((s == "high").sum())),
    )
    print(g.to_string())

    print()
    print("-" * 78)
    print("段长分布（点数，1 点 = 5 分钟）")
    print("-" * 78)
    q = seg_df["n_points"].quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    for k, v in q.items():
        print(f"  p{int(k*100):>2} = {v:>6.0f} 点 ({v*5/60:>5.1f} 小时)")

    print()
    print("-" * 78)
    print("每个设备-天产出的段数分布（>1 说明一天内有多次故障/恢复）")
    print("-" * 78)
    per_day = seg_df.groupby(["site_id", "device_id", "branch_id", "date"]).size()
    for n, cnt in per_day.value_counts().sort_index().items():
        print(f"  {n} 段: {cnt} 个设备-天")


def _inspect(df: pd.DataFrame, seg_df: pd.DataFrame, cfg: LocatorConfig, n: int) -> None:
    """抽查若干候选段，打印段内外残差对比，便于人工判断是否合理。"""
    if seg_df.empty:
        print("无候选段可抽查。")
        return

    print()
    print("=" * 78)
    print(f"抽查 {n} 个候选段（按残差从低到高，即最可疑的优先）")
    print("=" * 78)

    sample = seg_df.nsmallest(n, "mean_residual")
    df = df.copy()
    # 用独立列名，避免与 locate() 内部的 _date（dt.date 而非 str）混淆
    df["_d_str"] = df["time"].dt.date.astype(str)

    for i, row in enumerate(sample.itertuples(), 1):
        site, dev, br, date = row.site_id, row.device_id, row.branch_id, row.date
        site_day = df[(df["site_id"] == site) & (df["_d_str"] == str(date))]
        if site_day.empty:
            print(f"[{i}] 跳过：站点 {site} / {date} 无数据")
            continue
        hours = site_day["time"].dt.hour
        site_day = site_day[
            (hours >= cfg.daylight_start_hour) & (hours < cfg.daylight_end_hour)
        ]
        baseline = site_day.groupby("time")["value"].median()

        one = site_day[
            (site_day["device_id"] == dev) & (site_day["branch_id"].astype(str) == str(br))
        ].sort_values("time")
        if one.empty:
            print(f"[{i}] 跳过：{site}/{dev}/支路{br}/{date} 白天无数据")
            continue
        base = one["time"].map(baseline).to_numpy(dtype=float)
        res = one["value"].to_numpy(dtype=float) / base
        t = pd.to_datetime(one["time"])

        t_start = pd.Timestamp(row.t_start)
        t_end = pd.Timestamp(row.t_end)
        in_seg = (t >= t_start) & (t < t_end)

        print()
        print(f"[{i}] {site} / {dev} / 支路{br} / {date}  label={row.label}")
        print(f"    候选段: {t_start.strftime('%H:%M')} ~ {t_end.strftime('%H:%M')}"
              f"  ({row.n_points} 点 = {row.n_points*5/60:.1f}h)"
              f"  置信度={row.confidence}  对照组={row.peer_count} 序列")
        seg_res = res[in_seg.to_numpy()]
        out_res = res[(~in_seg).to_numpy()]
        seg_res = seg_res[np.isfinite(seg_res)]
        out_res = out_res[np.isfinite(out_res)]
        print(f"    段内残差: mean={seg_res.mean():.3f}  min={seg_res.min():.3f}  "
              f"max={seg_res.max():.3f}")
        if out_res.size:
            print(f"    段外残差: mean={out_res.mean():.3f}  min={out_res.min():.3f}  "
                  f"max={out_res.max():.3f}   ← 应接近 1.0 才说明定位准确")
        # ASCII 残差曲线
        print("    残差曲线 (│=段边界, #=段内, .=段外; 纵向 1.0 → 0.0):")
        _ascii_plot(t.to_numpy(), res, t_start, t_end)


def _ascii_plot(times: np.ndarray, res: np.ndarray, t_start, t_end, rows: int = 8) -> None:
    """在终端画残差曲线，快速目检段边界是否卡在信号突变处。"""
    n = len(res)
    width = min(100, n)
    idx = np.linspace(0, n - 1, width).astype(int)
    r = res[idx]
    ts = pd.to_datetime(times[idx])
    inseg = (ts >= t_start) & (ts < t_end)

    for row in range(rows):
        hi = 1.2 - row * (1.2 / rows)
        lo = hi - (1.2 / rows)
        line = []
        for j, v in enumerate(r):
            if not np.isfinite(v):
                line.append(" ")
            elif lo <= v < hi or (row == rows - 1 and v < lo):
                line.append("#" if inseg[j] else ".")
            else:
                line.append(" ")
        print(f"      {hi:>4.1f} |{''.join(line)}")
    # 时间轴
    marks = [" "] * width
    for j in range(width):
        if inseg[j] and (j == 0 or not inseg[j - 1]):
            marks[j] = "|"
        if inseg[j] and (j == width - 1 or not inseg[j + 1]):
            marks[j] = "|"
    print(f"           {''.join(marks)}")
    print(f"           {ts[0].strftime('%H:%M')}"
          f"{' ' * max(0, width - 11)}{ts[-1].strftime('%H:%M')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="同期对标自动定位故障段")
    ap.add_argument("--dataset", default=DEFAULT_DATASET, help="数据集相对路径")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="结果输出目录（相对 backend-service）")
    ap.add_argument("--inspect", type=int, default=0, help="抽查 N 个候选段的残差明细")
    ap.add_argument("--fault-threshold", type=float, default=None, help="覆盖残差故障阈值")
    ap.add_argument("--min-segment-points", type=int, default=None, help="覆盖最小段长（点数）")
    args = ap.parse_args()

    cfg = LocatorConfig()
    if args.fault_threshold is not None:
        cfg.residual_fault_threshold = args.fault_threshold
    if args.min_segment_points is not None:
        cfg.min_segment_points = args.min_segment_points

    df = _load_dataset(args.dataset)
    locator = PeerResidualLocator(cfg)
    segments, report = locator.locate(df)
    seg_df = segments_to_dataframe(segments)

    _print_report(report, seg_df)

    out_dir = _BACKEND / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    csv_path = out_dir / f"segments-{stamp}.csv"
    json_path = out_dir / f"report-{stamp}.json"
    seg_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print()
    print(f"候选段明细已写入: {args.out_dir}/{csv_path.name}")
    print(f"运行报告已写入:   {args.out_dir}/{json_path.name}")

    if args.inspect > 0:
        _inspect(df, seg_df, cfg, args.inspect)

    print()
    print("候选仅供人工复核，脚本没有数据库写入入口。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
