# @AI_GENERATED
"""
PVDAQ → pv schema 转换器
========================
将 PVDAQ 公开数据的原始 daily 长表 parquet 转换为平台 pv schema 宽表。

**输入**：
  - 原始 daily parquet（长表：measured_on | utc_measured_on | metric_id | value）
  - cohort 决策表 q1_cohort_selected.csv（含 core_role_metric_ids、dc_power_provenance 等）
  - metrics 元数据 metrics__system_<sid>__part000.parquet（含 calc_scale / calc_offset）

**输出**：
  逐系统-月宽表 parquet，列 =
    time | site_id | device_id | branch_id |
    value(=dc_current) | dc_power | ac_power | poa_irradiance | module_temp

**关键逻辑**：
  1. sentinel 清洗（raw ≤ -90000 → NaN，在 scale 之前做）
  2. calc_scale / calc_offset 换算
  3. 长表透视为宽表（多 metric 同角色取均值）
  4. RTC 系统 DC power V×I 重建（仅在直接 metric 缺行时使用）
  5. cadence 门（system 51 排除非 60s epoch 日期）
  6. 5min 重采样（1min 系统 mean 下采样）或 15min 保持（system 34）
  7. 实体键注入（site_id / device_id / branch_id）

**约束**：
  - round1 不含 i_cal 列
  - 不修改原始 parquet
  - 全部使用相对路径
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

SENTINEL_THRESHOLD = -90000
"""PVDAQ 哨兵值阈值：raw value ≤ 此值视为 NaN"""

# 物理范围门：各角色在 sentinel 清洗后仍需检查的下界
# 用于过滤 sentinel 阈值未覆盖但物理不可能的坏值（如 POA -7999 W/m²）
PHYSICAL_FLOOR: Dict[str, float] = {
    "poa_irradiance": -10.0,   # 夜间可微负，但 < -10 不合理
    "module_temp": -80.0,      # 极寒 -80°C 以下不合理
}
"""角色 → 物理下界。值 < 此下界 → NaN"""

FIVE_CORE_ROLES = ["ac_power", "dc_power", "dc_current", "poa_irradiance", "module_temp"]
"""五核心角色（与 cohort 决策表 core_role_metric_ids 的 key 对齐）"""

OUTPUT_COLUMNS = [
    "time", "site_id", "device_id", "branch_id",
    "value", "dc_power", "ac_power", "poa_irradiance", "module_temp",
]
"""输出 parquet 列顺序。value 列 = dc_current（与平台 pv schema 对齐）"""

# RTC 系统 V×I 重建所需的额外 metric_id 映射
# key = system_id, value = dict of inverter structure
# 每个 inverter: { "voltage": metric_id, "currents": [metric_id, ...] }
RTC_VI_METRIC_MAP: Dict[int, List[Dict[str, Any]]] = {
    1403: [
        {"voltage": 4202, "currents": [4203, 4204]},
        {"voltage": 4208, "currents": [4209, 4210]},
    ],
    1422: [
        {"voltage": 4825, "currents": [4826, 4827]},
        {"voltage": 4831, "currents": [4832, 4833]},
    ],
    1423: [
        {"voltage": 4849, "currents": [4850, 4851]},
        {"voltage": 4855, "currents": [4856, 4857]},
    ],
    1429: [
        {"voltage": 4912, "currents": [4913, 4914]},
        {"voltage": 4918, "currents": [4919, 4920]},
    ],
}


# ---------------------------------------------------------------------------
# cohort 加载
# ---------------------------------------------------------------------------

def load_cohort(cohort_csv: str | Path) -> pd.DataFrame:
    """
    加载 cohort 决策表，解析 core_role_metric_ids JSON 列。

    Parameters
    ----------
    cohort_csv : str | Path
        q1_cohort_selected.csv 的路径（相对或绝对）

    Returns
    -------
    pd.DataFrame
        每行一个系统，core_role_metric_ids 列已解析为 dict
    """
    df = pd.read_csv(cohort_csv)
    df["core_role_metric_ids"] = df["core_role_metric_ids"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else x
    )
    return df


def load_metrics_meta(metrics_parquet: str | Path) -> pd.DataFrame:
    """
    加载单个系统的 metrics 元数据 parquet。

    Returns
    -------
    pd.DataFrame
        含 metric_id, sensor_name, calc_scale, calc_offset 等列
    """
    return pd.read_parquet(metrics_parquet)


# ---------------------------------------------------------------------------
# 单日转换核心逻辑
# ---------------------------------------------------------------------------

def _apply_sentinel_and_scale(
    df: pd.DataFrame,
    metrics_meta: pd.DataFrame,
) -> pd.DataFrame:
    """
    1. sentinel 清洗：raw value ≤ -90000 → NaN（在 scale 之前）
    2. 应用 calc_scale / calc_offset：scaled = raw * scale + offset

    Parameters
    ----------
    df : pd.DataFrame
        原始长表（measured_on, metric_id, value）
    metrics_meta : pd.DataFrame
        该系统的 metrics 元数据（含 calc_scale, calc_offset）

    Returns
    -------
    pd.DataFrame
        同结构，value 列已清洗并换算
    """
    out = df.copy()
    # sentinel → NaN
    out.loc[out["value"] <= SENTINEL_THRESHOLD, "value"] = np.nan

    # 合并 scale/offset
    scale_map = metrics_meta.set_index("metric_id")[["calc_scale", "calc_offset"]]
    out = out.merge(scale_map, left_on="metric_id", right_index=True, how="left")

    # 有 scale 信息时做换算，无信息时保持原值
    has_scale = out["calc_scale"].notna()
    out.loc[has_scale, "value"] = (
        out.loc[has_scale, "value"] * out.loc[has_scale, "calc_scale"]
        + out.loc[has_scale, "calc_offset"]
    )
    out.drop(columns=["calc_scale", "calc_offset"], inplace=True)
    return out


def _pivot_to_wide(
    df: pd.DataFrame,
    core_role_metric_ids: Dict[str, List[int]],
) -> pd.DataFrame:
    """
    长表透视为宽表：按 metric_id 过滤五核心角色，按 measured_on 透视。
    多 metric 同角色（如多个温度传感器）→ 取时刻均值。

    Parameters
    ----------
    df : pd.DataFrame
        清洗换算后的长表（measured_on, metric_id, value）
    core_role_metric_ids : dict
        五核心角色→metric_id 列表映射，如 {"ac_power": [315], "dc_current": [317], ...}

    Returns
    -------
    pd.DataFrame
        宽表：time | ac_power | dc_power | dc_current | poa_irradiance | module_temp
        dc_current 也同时作为 value 列的来源
    """
    # 建立 metric_id → role 反向映射
    mid_to_role: Dict[int, str] = {}
    for role, mids in core_role_metric_ids.items():
        for mid in mids:
            mid_to_role[mid] = role

    # 过滤并标记角色
    relevant_mids = set(mid_to_role.keys())
    filtered = df[df["metric_id"].isin(relevant_mids)].copy()
    if filtered.empty:
        return pd.DataFrame(columns=["time"] + FIVE_CORE_ROLES)

    filtered["role"] = filtered["metric_id"].map(mid_to_role)

    # 物理范围门：在取均值之前，将各角色超出物理下界的值置 NaN
    for role_name, floor_val in PHYSICAL_FLOOR.items():
        role_mask = filtered["role"] == role_name
        bad_mask = role_mask & (filtered["value"] < floor_val)
        if bad_mask.any():
            filtered.loc[bad_mask, "value"] = np.nan

    # 透视：同角色多 metric 在同一时刻取均值
    wide = (
        filtered
        .groupby(["measured_on", "role"])["value"]
        .mean()
        .unstack(level="role")
        .reset_index()
        .rename(columns={"measured_on": "time"})
    )

    # 确保五核心列都存在（缺失列填 NaN）
    for role in FIVE_CORE_ROLES:
        if role not in wide.columns:
            wide[role] = np.nan

    return wide[["time"] + FIVE_CORE_ROLES]


def _rebuild_dc_power_vi(
    df_long: pd.DataFrame,
    system_id: int,
    metrics_meta: pd.DataFrame,
) -> Optional[pd.Series]:
    """
    RTC 系统 DC power V×I 重建。
    公式：DC_power = sum_i( V_i × sum_j(I_ij) )
    其中 i = 逆变器编号，j = 该逆变器的电流通道编号。

    仅对 RTC_VI_METRIC_MAP 中注册的系统生效。

    Parameters
    ----------
    df_long : pd.DataFrame
        清洗换算后的长表
    system_id : int
        系统 ID
    metrics_meta : pd.DataFrame
        该系统 metrics 元数据（用于确认 metric 存在）

    Returns
    -------
    Optional[pd.Series]
        索引 = measured_on，值 = derived DC power (W)。
        如果该系统不需要或无法重建，返回 None。
    """
    if system_id not in RTC_VI_METRIC_MAP:
        return None

    inverters = RTC_VI_METRIC_MAP[system_id]
    all_needed_mids = set()
    for inv in inverters:
        all_needed_mids.add(inv["voltage"])
        all_needed_mids.update(inv["currents"])

    # 检查数据中是否有这些 metric
    available_mids = set(df_long["metric_id"].unique())
    if not all_needed_mids.issubset(available_mids):
        missing = all_needed_mids - available_mids
        logger.warning(
            "system %d: V×I 重建所需 metric %s 不在当日数据中，跳过重建",
            system_id, missing,
        )
        return None

    # 透视出各 metric 的时间序列
    vi_mids = list(all_needed_mids)
    vi_data = df_long[df_long["metric_id"].isin(vi_mids)].copy()
    vi_wide = vi_data.pivot_table(
        index="measured_on", columns="metric_id", values="value", aggfunc="mean",
    )

    # 计算 sum_i(V_i × sum_j(I_ij))
    dc_power = pd.Series(0.0, index=vi_wide.index, dtype=float)
    for inv in inverters:
        v_col = inv["voltage"]
        i_cols = inv["currents"]
        if v_col not in vi_wide.columns:
            continue
        voltage = vi_wide[v_col]
        current_sum = pd.Series(0.0, index=vi_wide.index, dtype=float)
        for ic in i_cols:
            if ic in vi_wide.columns:
                current_sum = current_sum.add(vi_wide[ic], fill_value=0.0)
        dc_power = dc_power + voltage * current_sum

    dc_power.name = "dc_power_derived"
    return dc_power


def _check_cadence(
    df_wide: pd.DataFrame,
    admitted_interval_seconds: int,
) -> bool:
    """
    检查单日宽表的采样间隔是否符合准入要求。

    Parameters
    ----------
    df_wide : pd.DataFrame
        宽表（含 time 列）
    admitted_interval_seconds : int
        允许的采样间隔（秒），如 60 或 900

    Returns
    -------
    bool
        True = 该日 cadence 合格
    """
    if len(df_wide) < 3:
        return False
    diffs = df_wide["time"].diff().dropna().dt.total_seconds()
    median_interval = diffs.median()
    # 允许 ±10% 容差
    return abs(median_interval - admitted_interval_seconds) / admitted_interval_seconds < 0.1


def _resample_to_target(
    df_wide: pd.DataFrame,
    target_analysis_interval: str,
) -> pd.DataFrame:
    """
    重采样到目标间隔。

    Parameters
    ----------
    df_wide : pd.DataFrame
        宽表（time 列为 datetime）
    target_analysis_interval : str
        "5min_from_1min" → 从 1min 下采样到 5min（mean）
        "15min_native" → 保持 15min 不重采样

    Returns
    -------
    pd.DataFrame
        重采样后的宽表
    """
    if target_analysis_interval == "15min_native":
        # 不做重采样
        return df_wide

    if target_analysis_interval == "5min_from_1min":
        numeric_cols = [c for c in FIVE_CORE_ROLES if c in df_wide.columns]
        resampled = (
            df_wide
            .set_index("time")
            [numeric_cols]
            .resample("5min")
            .mean()
            .reset_index()
        )
        return resampled

    logger.warning("未知 target_analysis_interval: %s，保持原样", target_analysis_interval)
    return df_wide


def _inject_entity_keys(
    df_wide: pd.DataFrame,
    site_id: str,
    device_id: str,
    branch_id: str = "main",
) -> pd.DataFrame:
    """
    注入实体键：site_id / device_id / branch_id。

    PVDAQ 单逆变器/单阵列，无真实 branch 维度，统一用 "main"。
    """
    out = df_wide.copy()
    out["site_id"] = site_id
    out["device_id"] = device_id
    out["branch_id"] = branch_id
    return out


def _format_output(df: pd.DataFrame) -> pd.DataFrame:
    """
    最终格式化：
    - dc_current → value（平台 pv schema 约定 value = dc_current）
    - 列顺序对齐 OUTPUT_COLUMNS
    - 删除不需要的列
    """
    out = df.copy()
    # dc_current → value
    if "dc_current" in out.columns:
        out.rename(columns={"dc_current": "value"}, inplace=True)
    elif "value" not in out.columns:
        out["value"] = np.nan

    # 确保所有输出列存在
    for col in OUTPUT_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan

    return out[OUTPUT_COLUMNS]


# ---------------------------------------------------------------------------
# 单系统-月批量转换
# ---------------------------------------------------------------------------

def convert_system_month(
    system_id: int,
    year: int,
    month: int,
    raw_base_dir: str | Path,
    cohort_row: pd.Series,
    metrics_meta: pd.DataFrame,
) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
    """
    转换单个系统某月的全部原始 daily parquet → 合并为一个月宽表。

    Parameters
    ----------
    system_id : int
        PVDAQ system_id
    year : int
        年份
    month : int
        月份
    raw_base_dir : str | Path
        原始数据根目录（如 backend-service/data/benchmark_raw/pvdaq）
    cohort_row : pd.Series
        该系统在 cohort 决策表中的行
    metrics_meta : pd.DataFrame
        该系统 metrics 元数据

    Returns
    -------
    (df_month, stats)
        df_month: 合并后的月宽表（OUTPUT_COLUMNS），如果全部日期被排除则为 None
        stats: 转换统计信息
    """
    raw_base_dir = Path(raw_base_dir)
    month_dir = raw_base_dir / f"system_id={system_id}" / f"year={year}" / f"month={month}"

    if not month_dir.exists():
        logger.warning("目录不存在: %s", month_dir)
        return None, {"status": "dir_not_found", "system_id": system_id,
                       "year": year, "month": month}

    # 解析 cohort 配置
    core_roles: Dict[str, List[int]] = cohort_row["core_role_metric_ids"]
    dc_prov = str(cohort_row.get("dc_power_provenance", "direct_metric"))
    admitted_interval = int(cohort_row.get("admitted_epoch_interval_seconds", 60))
    target_interval = str(cohort_row.get("target_analysis_interval", "5min_from_1min"))
    site_id = str(int(cohort_row["site_id"])) if pd.notna(cohort_row["site_id"]) else "unknown"
    device_id = f"pvdaq-system-{system_id}"

    # 收集 V×I 重建额外需要的 metric_id
    vi_extra_mids: set = set()
    if system_id in RTC_VI_METRIC_MAP:
        for inv in RTC_VI_METRIC_MAP[system_id]:
            vi_extra_mids.add(inv["voltage"])
            vi_extra_mids.update(inv["currents"])

    # 遍历该月所有 daily parquet
    daily_files = sorted(month_dir.glob("*.parquet"))
    if not daily_files:
        logger.warning("月目录为空: %s", month_dir)
        return None, {"status": "empty_month", "system_id": system_id,
                       "year": year, "month": month}

    daily_frames: List[pd.DataFrame] = []
    stats = {
        "system_id": system_id,
        "year": year,
        "month": month,
        "total_daily_files": len(daily_files),
        "cadence_passed": 0,
        "cadence_failed": 0,
        "vi_rebuilt_days": 0,
        "status": "ok",
    }

    for fpath in daily_files:
        try:
            raw = pd.read_parquet(fpath)
        except Exception as e:
            logger.error("读取失败 %s: %s", fpath, e)
            continue

        if raw.empty:
            continue

        # Step 1: sentinel 清洗 + scale 换算
        cleaned = _apply_sentinel_and_scale(raw, metrics_meta)

        # Step 2: 透视为宽表
        wide = _pivot_to_wide(cleaned, core_roles)
        if wide.empty or len(wide) < 3:
            continue

        # Step 3: RTC DC power 重建（仅在 dc_power 列全 NaN 或缺行时）
        dc_all_nan = wide["dc_power"].isna().all() if "dc_power" in wide.columns else True
        if dc_all_nan and dc_prov != "direct_metric":
            derived = _rebuild_dc_power_vi(cleaned, system_id, metrics_meta)
            if derived is not None:
                # 将 derived DC power 合并到宽表
                derived_df = derived.reset_index()
                derived_df.columns = ["time", "dc_power_derived"]
                wide = wide.merge(derived_df, on="time", how="left")
                # 用 derived 值填补 dc_power
                if "dc_power" in wide.columns:
                    wide["dc_power"] = wide["dc_power"].fillna(wide["dc_power_derived"])
                else:
                    wide["dc_power"] = wide["dc_power_derived"]
                wide.drop(columns=["dc_power_derived"], inplace=True)
                stats["vi_rebuilt_days"] += 1

        # Step 4: cadence 门
        if not _check_cadence(wide, admitted_interval):
            stats["cadence_failed"] += 1
            continue
        stats["cadence_passed"] += 1

        # Step 5: 重采样
        resampled = _resample_to_target(wide, target_interval)

        daily_frames.append(resampled)

    if not daily_frames:
        stats["status"] = "all_days_excluded"
        return None, stats

    # 合并月数据
    month_df = pd.concat(daily_frames, ignore_index=True)
    month_df.sort_values("time", inplace=True)

    # Step 6: 注入实体键
    month_df = _inject_entity_keys(month_df, site_id, device_id)

    # Step 7: 格式化输出
    month_df = _format_output(month_df)

    return month_df, stats


# ---------------------------------------------------------------------------
# 批量转换入口
# ---------------------------------------------------------------------------

def convert_all(
    raw_base_dir: str | Path,
    cohort_csv: str | Path,
    output_dir: str | Path,
    systems: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """
    批量转换全部 cohort 系统的多月数据。

    Parameters
    ----------
    raw_base_dir : str | Path
        PVDAQ 原始数据根目录
    cohort_csv : str | Path
        q1_cohort_selected.csv 路径
    output_dir : str | Path
        转换结果输出目录（如 .../pvdaq/converted/）
    systems : list[int] | None
        指定要转换的系统 ID 列表；None = 全部

    Returns
    -------
    list[dict]
        每个系统-月的转换统计
    """
    raw_base_dir = Path(raw_base_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cohort = load_cohort(cohort_csv)
    all_stats: List[Dict[str, Any]] = []

    for _, row in cohort.iterrows():
        sid = int(row["system_id"])
        if systems is not None and sid not in systems:
            continue

        # 加载该系统 metrics 元数据
        metrics_path = raw_base_dir / f"metrics__system_{sid}__part000.parquet"
        if not metrics_path.exists():
            logger.error("metrics 元数据不存在: %s", metrics_path)
            all_stats.append({
                "system_id": sid, "status": "metrics_not_found",
            })
            continue
        metrics_meta = load_metrics_meta(metrics_path)

        # 扫描该系统所有已下载的 year/month
        sys_dir = raw_base_dir / f"system_id={sid}"
        if not sys_dir.exists():
            logger.warning("系统目录不存在: %s", sys_dir)
            all_stats.append({
                "system_id": sid, "status": "sys_dir_not_found",
            })
            continue

        for year_dir in sorted(sys_dir.iterdir()):
            if not year_dir.is_dir() or not year_dir.name.startswith("year="):
                continue
            yr = int(year_dir.name.split("=")[1])

            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir() or not month_dir.name.startswith("month="):
                    continue
                mo = int(month_dir.name.split("=")[1])

                logger.info("转换 system=%d year=%d month=%d ...", sid, yr, mo)

                df_month, st = convert_system_month(
                    system_id=sid,
                    year=yr,
                    month=mo,
                    raw_base_dir=raw_base_dir,
                    cohort_row=row,
                    metrics_meta=metrics_meta,
                )
                all_stats.append(st)

                if df_month is not None and not df_month.empty:
                    out_path = output_dir / str(sid) / f"{yr}-{mo:02d}.parquet"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    df_month.to_parquet(out_path, index=False, engine="pyarrow")
                    logger.info(
                        "  → %s  (%d 行, %d 天通过 cadence)",
                        out_path.relative_to(output_dir),
                        len(df_month),
                        st.get("cadence_passed", 0),
                    )
                else:
                    logger.warning(
                        "  → system=%d %d-%02d 无有效数据输出",
                        sid, yr, mo,
                    )

    return all_stats


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    """
    命令行入口：从 backend-service 目录运行
        python -m services.benchmark.pvdaq_converter
    或
        python services/benchmark/pvdaq_converter.py
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="PVDAQ → pv schema 转换器：将原始 daily 长表转换为平台宽表格式",
    )
    parser.add_argument(
        "--raw-dir",
        default="data/benchmark_raw/pvdaq",
        help="PVDAQ 原始数据根目录（相对于 CWD，默认 data/benchmark_raw/pvdaq）",
    )
    parser.add_argument(
        "--cohort-csv",
        default="data/benchmark_raw/pvdaq/analysis/q1_cohort_selected.csv",
        help="cohort 决策表路径",
    )
    parser.add_argument(
        "--output-dir",
        default="data/benchmark_raw/pvdaq/converted",
        help="输出目录",
    )
    parser.add_argument(
        "--systems",
        type=int,
        nargs="*",
        default=None,
        help="指定系统 ID（空 = 全部 cohort 系统）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细日志输出",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    stats = convert_all(
        raw_base_dir=args.raw_dir,
        cohort_csv=args.cohort_csv,
        output_dir=args.output_dir,
        systems=args.systems,
    )

    # 汇总
    ok = sum(1 for s in stats if s.get("status") == "ok")
    excluded = sum(1 for s in stats if s.get("status") == "all_days_excluded")
    errors = sum(1 for s in stats if s.get("status") not in ("ok", "all_days_excluded"))
    total_vi = sum(
        s.get("vi_rebuilt_days", 0) for s in stats if s.get("status") == "ok"
    )

    print(f"\n{'='*60}")
    print(f"转换完成：{ok} 成功 / {excluded} 全排除 / {errors} 错误")
    print(f"V×I 重建天数：{total_vi}")
    print(f"{'='*60}")

    # 输出详细统计
    stats_df = pd.DataFrame(stats)
    stats_path = Path(args.output_dir) / "_conversion_stats.csv"
    stats_df.to_csv(stats_path, index=False)
    print(f"统计已保存: {stats_path}")


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
