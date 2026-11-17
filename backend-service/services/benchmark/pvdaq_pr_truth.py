# @AI_GENERATED
"""
PVDAQ Q1 物理 PR 真值生成器
============================
在转换后的 pv schema 宽表上，按设备-日计算 Performance Ratio (PR)，
产出日级二分类金标（normal / abnormal）。

**公式**：
    PR = AC日发电量(kWh) / (额定功率(kW) × POA日辐照量(kWh/m²))

**覆盖门**：五核心通道每个 ≥90% 非空才计算 PR

**金标**：
    - 每设备取合格日 PR 中位数作为 baseline_pr
    - relative_pr = PR / baseline_pr
    - label = "abnormal" if relative_pr < 0.7 else "normal"

**独立于模型输出**：不允许 truth = pred 自造 gold。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

COVERAGE_THRESHOLD = 0.90
"""五核心通道每个的最低非空率（≥90% 才计算 PR）"""

ABNORMAL_RELATIVE_PR_THRESHOLD = 0.70
"""relative_pr < 此值判为 abnormal"""

FIVE_CORE_COLUMNS = ["value", "dc_power", "ac_power", "poa_irradiance", "module_temp"]
"""转换后 parquet 中的五核心通道列名（value = dc_current）"""

MIN_POA_DAILY_KWH_M2 = 0.5
"""日辐照量最低门槛 (kWh/m²)：低于此值（如阴天/夜间）跳过，避免 PR 分母过小"""


# ---------------------------------------------------------------------------
# 核心计算
# ---------------------------------------------------------------------------

def _compute_daily_pr(
    df_day: pd.DataFrame,
    rated_power_kw: float,
    interval_minutes: float,
) -> Optional[float]:
    """
    计算单日 PR。

    Parameters
    ----------
    df_day : pd.DataFrame
        单日宽表数据（含 ac_power, poa_irradiance 列，单位 W 和 W/m²）
    rated_power_kw : float
        系统额定功率 (kW)
    interval_minutes : float
        采样间隔（分钟），用于积分：5min 或 15min

    Returns
    -------
    float | None
        PR 值。如果辐照量过低或额定功率无效，返回 None。
    """
    if rated_power_kw <= 0:
        return None

    # AC 日发电量 (kWh) = sum(ac_power_W) × interval_min / 60 / 1000
    ac_energy_kwh = df_day["ac_power"].sum() * interval_minutes / 60.0 / 1000.0

    # POA 日辐照量 (kWh/m²) = sum(poa_W_per_m2) × interval_min / 60 / 1000
    poa_energy_kwh_m2 = df_day["poa_irradiance"].sum() * interval_minutes / 60.0 / 1000.0

    if poa_energy_kwh_m2 < MIN_POA_DAILY_KWH_M2:
        return None

    pr = ac_energy_kwh / (rated_power_kw * poa_energy_kwh_m2)
    return pr


def _check_daily_coverage(df_day: pd.DataFrame) -> Dict[str, float]:
    """
    计算单日五核心通道的非空率。

    Returns
    -------
    dict
        {channel_name: coverage_pct}，coverage_pct 范围 [0.0, 1.0]
    """
    coverages = {}
    for col in FIVE_CORE_COLUMNS:
        if col in df_day.columns:
            coverages[col] = df_day[col].notna().mean()
        else:
            coverages[col] = 0.0
    return coverages


def compute_system_truth(
    df_month: pd.DataFrame,
    system_id: int,
    rated_power_kw: float,
    interval_minutes: float,
) -> pd.DataFrame:
    """
    计算单系统单月所有日期的 PR 和覆盖率。

    Parameters
    ----------
    df_month : pd.DataFrame
        单系统单月的转换后宽表
    system_id : int
        系统 ID
    rated_power_kw : float
        额定功率 (kW)
    interval_minutes : float
        采样间隔（分钟）

    Returns
    -------
    pd.DataFrame
        每行一天：system_id | date | coverage_* | passes_coverage_gate |
        ac_energy_kwh | poa_energy_kwh_m2 | pr | points_count
    """
    records = []
    df_month = df_month.copy()
    df_month["date"] = df_month["time"].dt.date

    for date_val, day_group in df_month.groupby("date"):
        coverages = _check_daily_coverage(day_group)
        passes_gate = all(c >= COVERAGE_THRESHOLD for c in coverages.values())

        pr = None
        ac_kwh = None
        poa_kwh_m2 = None

        if passes_gate:
            ac_kwh = day_group["ac_power"].sum() * interval_minutes / 60.0 / 1000.0
            poa_kwh_m2 = day_group["poa_irradiance"].sum() * interval_minutes / 60.0 / 1000.0
            pr = _compute_daily_pr(day_group, rated_power_kw, interval_minutes)

        record = {
            "system_id": system_id,
            "date": date_val,
            "points_count": len(day_group),
            "rated_power_kw": rated_power_kw,
            "interval_minutes": interval_minutes,
            "ac_energy_kwh": ac_kwh,
            "poa_energy_kwh_m2": poa_kwh_m2,
            "pr": pr,
            "passes_coverage_gate": passes_gate,
        }
        for col in FIVE_CORE_COLUMNS:
            record["coverage_%s" % col] = coverages.get(col, 0.0)

        records.append(record)

    return pd.DataFrame(records)


def assign_labels(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    为每个设备计算 baseline_pr、relative_pr 和二分类金标。

    逻辑：
    1. 每设备取合格日（passes_coverage_gate=True 且 pr 非 None）PR 中位数 → baseline_pr
    2. relative_pr = pr / baseline_pr
    3. label = "abnormal" if relative_pr < 0.7 else "normal"
    4. 不合格日的 label 为 NaN（不参与训练/评估）

    Parameters
    ----------
    daily_df : pd.DataFrame
        compute_system_truth 产出的汇总表（可跨多系统）

    Returns
    -------
    pd.DataFrame
        新增列：baseline_pr | relative_pr | label
    """
    out = daily_df.copy()
    out["baseline_pr"] = np.nan
    out["relative_pr"] = np.nan
    out["label"] = None

    for sid, grp in out.groupby("system_id"):
        valid_mask = grp["passes_coverage_gate"] & grp["pr"].notna()
        valid_prs = grp.loc[valid_mask, "pr"]

        if len(valid_prs) == 0:
            logger.warning("system %s: 无合格日，无法计算 baseline_pr", sid)
            continue

        baseline = valid_prs.median()
        out.loc[grp.index, "baseline_pr"] = baseline

        # relative_pr 只对合格日计算
        valid_idx = grp.index[valid_mask]
        out.loc[valid_idx, "relative_pr"] = out.loc[valid_idx, "pr"] / baseline

        # 标签
        for idx in valid_idx:
            rpr = out.loc[idx, "relative_pr"]
            if pd.notna(rpr):
                out.loc[idx, "label"] = (
                    "abnormal" if rpr < ABNORMAL_RELATIVE_PR_THRESHOLD else "normal"
                )

    return out


# ---------------------------------------------------------------------------
# 批量处理入口
# ---------------------------------------------------------------------------

def generate_all_truth(
    converted_dir: str | Path,
    cohort_csv: str | Path,
    output_dir: str | Path,
) -> pd.DataFrame:
    """
    批量计算全部 cohort 系统的日级 PR 真值和二分类金标。

    Parameters
    ----------
    converted_dir : str | Path
        转换后数据目录（pvdaq/converted/）
    cohort_csv : str | Path
        q1_cohort_selected.csv 路径
    output_dir : str | Path
        输出目录（写入 q1_daily_truth.csv 和 q1_truth_summary.csv）

    Returns
    -------
    pd.DataFrame
        全量日级真值表
    """
    converted_dir = Path(converted_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cohort = pd.read_csv(cohort_csv)

    all_daily: List[pd.DataFrame] = []

    for _, row in cohort.iterrows():
        sid = int(row["system_id"])
        rated_kw = float(row["rated_power_kw"])
        target_interval = str(row.get("target_analysis_interval", "5min_from_1min"))

        # 推断采样间隔
        if target_interval == "15min_native":
            interval_min = 15.0
        else:
            interval_min = 5.0

        sys_dir = converted_dir / str(sid)
        if not sys_dir.exists():
            logger.warning("system %d: 转换目录不存在 %s", sid, sys_dir)
            continue

        for parquet_file in sorted(sys_dir.glob("*.parquet")):
            logger.info("计算 PR: system=%d file=%s", sid, parquet_file.name)
            df_month = pd.read_parquet(parquet_file)
            daily = compute_system_truth(df_month, sid, rated_kw, interval_min)
            all_daily.append(daily)

    if not all_daily:
        logger.error("无有效数据")
        return pd.DataFrame()

    combined = pd.concat(all_daily, ignore_index=True)
    combined = assign_labels(combined)
    combined.sort_values(["system_id", "date"], inplace=True)
    combined.reset_index(drop=True, inplace=True)

    # 保存日级真值
    truth_path = output_dir / "q1_daily_truth.csv"
    combined.to_csv(truth_path, index=False)
    logger.info("日级真值已保存: %s (%d 行)", truth_path, len(combined))

    # 生成汇总统计
    summary_records = []
    for sid, grp in combined.groupby("system_id"):
        valid = grp[grp["passes_coverage_gate"] & grp["pr"].notna()]
        labeled = grp[grp["label"].notna()]
        n_normal = (labeled["label"] == "normal").sum()
        n_abnormal = (labeled["label"] == "abnormal").sum()

        summary_records.append({
            "system_id": sid,
            "total_days": len(grp),
            "coverage_gate_passed": len(valid),
            "coverage_gate_failed": len(grp) - len(valid),
            "pr_computed": len(valid),
            "baseline_pr": valid["baseline_pr"].iloc[0] if len(valid) > 0 else None,
            "pr_mean": valid["pr"].mean() if len(valid) > 0 else None,
            "pr_std": valid["pr"].std() if len(valid) > 0 else None,
            "pr_min": valid["pr"].min() if len(valid) > 0 else None,
            "pr_max": valid["pr"].max() if len(valid) > 0 else None,
            "labeled_days": len(labeled),
            "n_normal": n_normal,
            "n_abnormal": n_abnormal,
            "abnormal_rate": n_abnormal / len(labeled) if len(labeled) > 0 else None,
        })

    summary_df = pd.DataFrame(summary_records)
    summary_path = output_dir / "q1_truth_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    logger.info("汇总统计已保存: %s", summary_path)

    # 打印汇总
    print("\n" + "=" * 70)
    print("Q1 PR 真值生成完成")
    print("=" * 70)
    print(summary_df.to_string(index=False))
    total_labeled = summary_df["labeled_days"].sum()
    total_abnormal = summary_df["n_abnormal"].sum()
    total_normal = summary_df["n_normal"].sum()
    print("\n总计: %d 标注日 = %d normal + %d abnormal (异常率 %.1f%%)" % (
        total_labeled, total_normal, total_abnormal,
        total_abnormal / total_labeled * 100 if total_labeled > 0 else 0,
    ))

    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """
    命令行入口：从 backend-service 目录运行
        python -m services.benchmark.pvdaq_pr_truth
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="PVDAQ Q1 物理 PR 真值生成器",
    )
    parser.add_argument(
        "--converted-dir",
        default="data/benchmark_raw/pvdaq/converted",
        help="转换后数据目录",
    )
    parser.add_argument(
        "--cohort-csv",
        default="data/benchmark_raw/pvdaq/analysis/q1_cohort_selected.csv",
        help="cohort 决策表路径",
    )
    parser.add_argument(
        "--output-dir",
        default="data/benchmark_raw/pvdaq/analysis",
        help="输出目录（写入 q1_daily_truth.csv 和 q1_truth_summary.csv）",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    generate_all_truth(
        converted_dir=args.converted_dir,
        cohort_csv=args.cohort_csv,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
