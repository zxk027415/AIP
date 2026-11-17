# -*- coding: utf-8 -*-
"""
scripts/plot_located_segments.py — 把自动定位的故障段画成图，供人工目检

配合 `scripts/auto_locate_fault_segments.py` 使用：后者产出候选段 CSV，
本脚本读该 CSV，对每个设备-天画三层图：

  上：本设备功率 vs 同站点同期基准（中位数）—— 看偏离程度
  中：残差曲线 = 本设备 / 基准 —— 看阈值线与段边界是否吻合
  下：同站点若干台设备的功率叠加 —— 看「这是天气还是本设备的问题」

红色阴影 = 自动识别的故障段。判断标准：
  段内残差应明显低于阈值线，段外应贴近 1.0；
  下图若同站点其他设备也一起降，说明是天气不是故障（该段应视为误判）。

用法::

    # 画高置信段（残差最低的 12 个设备-天）
    python scripts/plot_located_segments.py --n 12 --confidence high

    # 画中置信段（这批最需要人工判断）
    python scripts/plot_located_segments.py --n 12 --confidence medium

    # 指定某个设备-天
    python scripts/plot_located_segments.py --device zQJNoBLM --date 2021-08-23

输出：data/auto_located_segments/plots/*.png
"""

# @AI_GENERATED
from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import matplotlib
matplotlib.use("Agg")  # 无 GUI 环境，只出文件
import matplotlib.pyplot as plt
from matplotlib import font_manager

from services.iterative_labeling.peer_residual_locator import LocatorConfig  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("plot_segments")

DEFAULT_DATASET = "datasets/pv_cumulative_labeled_merged.parquet"
SEG_DIR = "data/auto_located_segments"


def _setup_chinese_font() -> None:
    """按可用性挑一个中文字体，避免图上出现方块。"""
    names = {f.name for f in font_manager.fontManager.ttflist}
    for cand in ("Microsoft YaHei", "SimHei", "DengXian", "SimSun"):
        if cand in names:
            plt.rcParams["font.family"] = cand
            break
    plt.rcParams["axes.unicode_minus"] = False  # 负号正常显示


def _latest_segments_csv() -> Path:
    files = sorted((_BACKEND / SEG_DIR).glob("segments-*.csv"))
    if not files:
        raise FileNotFoundError(
            f"{SEG_DIR} 下没有 segments-*.csv，请先运行 auto_locate_fault_segments.py"
        )
    return files[-1]


def _plot_one(
    df_site_day: pd.DataFrame,
    segs: pd.DataFrame,
    cfg: LocatorConfig,
    out_path: Path,
    *,
    site_id: str,
    device_id: str,
    branch_id,
    date: str,
    label: int,
) -> bool:
    """画单个设备-天的三层诊断图。返回是否成功。"""
    hours = df_site_day["time"].dt.hour
    day = df_site_day[
        (hours >= cfg.daylight_start_hour) & (hours < cfg.daylight_end_hour)
    ]
    if day.empty:
        return False

    baseline = day.groupby("time")["value"].median()
    baseline_f = baseline.where(baseline >= cfg.min_peer_baseline)

    one = day[
        (day["device_id"] == device_id)
        & (day["branch_id"].astype(str) == str(branch_id))
    ].sort_values("time")
    if one.empty:
        return False

    t = pd.to_datetime(one["time"])
    val = one["value"].to_numpy(dtype=float)
    base = one["time"].map(baseline_f).to_numpy(dtype=float)
    res = val / base
    peer_count = day.groupby(["device_id", "branch_id"]).ngroups

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True,
                             gridspec_kw={"height_ratios": [3, 2, 3]})

    # ---- 上：本设备 vs 基准 ----
    ax = axes[0]
    ax.plot(t, val, lw=1.8, color="#1f77b4", label="本设备功率")
    ax.plot(t, base, lw=1.5, color="#2ca02c", ls="--",
            label=f"同站点同期基准（{peer_count} 条序列中位数）")
    ax.fill_between(t, val, base, where=(val < base), alpha=0.15, color="red",
                    label="低于基准的部分")
    ax.set_ylabel("功率 value")
    ax.set_title(
        f"{site_id} / {device_id} / 支路{branch_id} / {date}   "
        f"天级标签 label={label}   对照组={peer_count} 条序列",
        fontsize=13, pad=12,
    )
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.3)

    # ---- 中：残差 ----
    ax = axes[1]
    ax.plot(t, res, lw=1.8, color="#d62728", label="残差 = 本设备 / 基准")
    ax.axhline(1.0, color="gray", ls=":", lw=1.2, label="1.0（与同期一致）")
    ax.axhline(cfg.residual_fault_threshold, color="orange", ls="--", lw=1.4,
               label=f"故障阈值 {cfg.residual_fault_threshold}")
    ax.axhline(cfg.residual_high_conf_threshold, color="purple", ls="--", lw=1.2,
               label=f"高置信阈值 {cfg.residual_high_conf_threshold}")
    ax.set_ylabel("残差")
    ax.set_ylim(-0.05, max(1.6, np.nanpercentile(res, 99) if np.isfinite(res).any() else 1.6))
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    ax.grid(alpha=0.3)

    # ---- 下：同站点其他设备叠加（区分天气 vs 故障）----
    ax = axes[2]
    others = day[
        ~((day["device_id"] == device_id)
          & (day["branch_id"].astype(str) == str(branch_id)))
    ]
    plotted = 0
    for (d, b), g in others.groupby(["device_id", "branch_id"], sort=False):
        if plotted >= 25:  # 太多线看不清
            break
        g = g.sort_values("time")
        ax.plot(pd.to_datetime(g["time"]), g["value"], lw=0.7, alpha=0.35, color="gray")
        plotted += 1
    ax.plot(t, val, lw=2.2, color="#1f77b4", label="本设备（蓝）")
    ax.plot(t, base, lw=1.5, color="#2ca02c", ls="--", label="基准（绿虚线）")
    ax.set_ylabel("功率 value")
    ax.set_xlabel("时间")
    ax.legend(loc="upper left", fontsize=9)
    ax.set_title(f"同站点其他 {plotted} 条序列叠加（灰）—— 若灰线也一起降说明是天气，"
                 f"不是本设备故障", fontsize=10)
    ax.grid(alpha=0.3)

    # ---- 三层图统一标出故障段 ----
    for _, s in segs.iterrows():
        ts, te = pd.Timestamp(s["t_start"]), pd.Timestamp(s["t_end"])
        for a in axes:
            a.axvspan(ts, te, alpha=0.16, color="red")
            a.axvline(ts, color="red", lw=1.0, alpha=0.6)
            a.axvline(te, color="red", lw=1.0, alpha=0.6)
        axes[1].annotate(
            f"{s['n_points']}点 {s['n_points']*5/60:.1f}h\n残差{s['mean_residual']:.3f}\n{s['confidence']}",
            xy=(ts + (te - ts) / 2, 1.35), ha="center", va="top", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", fc="#fff3cd", ec="orange", alpha=0.9),
        )

    fig.autofmt_xdate()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="把自动定位的故障段画成图")
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--segments-csv", default=None, help="默认取最新的 segments-*.csv")
    ap.add_argument("--n", type=int, default=12, help="画多少个设备-天")
    ap.add_argument("--confidence", default="all", choices=["high", "medium", "all"])
    ap.add_argument("--label", type=int, default=None, help="只画指定 label")
    ap.add_argument("--device", default=None, help="只画指定 device_id")
    ap.add_argument("--date", default=None, help="只画指定日期 YYYY-MM-DD")
    ap.add_argument("--sort", default="residual", choices=["residual", "duration", "random"],
                    help="挑样本的排序方式：residual=最可疑优先 / duration=段最长优先 / random")
    ap.add_argument("--out-subdir", default="plots")
    args = ap.parse_args()

    _setup_chinese_font()
    cfg = LocatorConfig()

    csv_path = Path(args.segments_csv) if args.segments_csv else _latest_segments_csv()
    if not csv_path.is_absolute():
        csv_path = _BACKEND / csv_path
    seg = pd.read_csv(csv_path)
    logger.info("读取候选段: %s (%d 段)", csv_path.name, len(seg))

    if args.confidence != "all":
        seg = seg[seg["confidence"] == args.confidence]
    if args.label is not None:
        seg = seg[seg["label"] == args.label]
    if args.device:
        seg = seg[seg["device_id"] == args.device]
    if args.date:
        seg = seg[seg["date"] == args.date]
    if seg.empty:
        print("按当前过滤条件没有候选段。")
        return 1

    # 按设备-天聚合（一个设备-天可能有多段，画在同一张图上）
    keys = ["site_id", "device_id", "branch_id", "date", "label"]
    grouped = seg.groupby(keys, sort=False)
    agg = grouped.agg(
        n_seg=("n_points", "size"),
        total_points=("n_points", "sum"),
        min_residual=("mean_residual", "min"),
    ).reset_index()

    if args.sort == "residual":
        agg = agg.sort_values("min_residual")
    elif args.sort == "duration":
        agg = agg.sort_values("total_points", ascending=False)
    else:
        agg = agg.sample(frac=1.0, random_state=42)
    agg = agg.head(args.n)

    logger.info("加载数据集 %s ...", args.dataset)
    p = _BACKEND / args.dataset
    df = pd.read_parquet(p, columns=["site_id", "device_id", "branch_id", "time", "value", "label"])
    df["time"] = pd.to_datetime(df["time"])
    df["_d"] = df["time"].dt.date.astype(str)

    out_dir = _BACKEND / SEG_DIR / args.out_subdir
    ok = fail = 0
    for i, row in enumerate(agg.itertuples(), 1):
        site_day = df[(df["site_id"] == row.site_id) & (df["_d"] == str(row.date))]
        if site_day.empty:
            fail += 1
            continue
        segs_here = seg[
            (seg["site_id"] == row.site_id)
            & (seg["device_id"] == row.device_id)
            & (seg["branch_id"].astype(str) == str(row.branch_id))
            & (seg["date"] == row.date)
        ]
        safe_dev = str(row.device_id).replace("/", "_").replace("#", "").replace("\\", "_")
        fname = f"{i:02d}_L{row.label}_{safe_dev}_{row.date}_res{row.min_residual:.3f}.png"
        if _plot_one(site_day, segs_here, cfg, out_dir / fname,
                     site_id=str(row.site_id), device_id=str(row.device_id),
                     branch_id=row.branch_id, date=str(row.date), label=int(row.label)):
            ok += 1
            print(f"  [{i:>2}] {fname}   段数={row.n_seg} 最低残差={row.min_residual:.3f}")
        else:
            fail += 1

    print()
    print(f"已生成 {ok} 张图（失败 {fail}）")
    print(f"输出目录: {SEG_DIR}/{args.out_subdir}/")
    print()
    print("怎么看图：")
    print("  上图 — 蓝线(本设备)明显低于绿虚线(同期基准) = 疑似故障")
    print("  中图 — 残差曲线掉到橙色阈值线以下 = 触发判定；红色阴影是自动识别的段")
    print("  下图 — 若灰线(其他设备)也一起降 -> 是天气，该段属误判；")
    print("         若只有蓝线降、灰线正常 -> 是本设备故障，定位正确")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# @AI_GENERATED: end
