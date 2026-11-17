# @AI_GENERATED
"""
PVDAQ i_cal 统计回归构造器
===========================
为每台设备用 (poa_irradiance, module_temp) → dc_current 拟合回归模型，
产出 i_cal 列（预测电流基线），注入到转换后 parquet 中。

**策略**：
  - 每台设备独立拟合一个 RandomForestRegressor
  - 训练数据 = 该设备所有"正常日"（PR 金标 label=normal）的白天时刻
  - 白天定义：poa_irradiance > 10 W/m²
  - 拟合后对全量数据（含异常日）预测 i_cal
  - 夜间（poa ≤ 10）i_cal 设为 0

**输出**：
  覆盖 converted/ 目录下的 parquet，新增 i_cal 列；
  同时产出 is_measured 列（全 1，表示实测数据）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DAYLIGHT_POA_THRESHOLD = 10.0
"""白天定义：poa_irradiance > 此值 (W/m²)"""

REGRESSOR_FEATURES = ["poa_irradiance", "module_temp"]
"""回归输入特征"""

TARGET_COL = "value"
"""回归目标（dc_current = value 列）"""


# ---------------------------------------------------------------------------
# 核心逻辑
# ---------------------------------------------------------------------------

def build_ical_for_device(
    device_df: pd.DataFrame,
    normal_dates: set,
    random_state: int = 42,
) -> pd.DataFrame:
    """
    为单台设备构造 i_cal 列。

    Parameters
    ----------
    device_df : pd.DataFrame
        该设备所有月份合并后的宽表（含 time, value, poa_irradiance, module_temp）
    normal_dates : set
        该设备的正常日 date 集合（来自 PR 金标）
    random_state : int
        回归器随机种子

    Returns
    -------
    pd.DataFrame
        新增 i_cal 和 is_measured 列
    """
    out = device_df.copy()
    out["date"] = out["time"].dt.date
    out["i_cal"] = 0.0
    out["is_measured"] = 1  # PVDAQ 全量实测

    # 训练集：正常日 + 白天 + 特征/目标均非空
    train_mask = (
        out["date"].isin(normal_dates)
        & (out["poa_irradiance"] > DAYLIGHT_POA_THRESHOLD)
        & out["poa_irradiance"].notna()
        & out["module_temp"].notna()
        & out[TARGET_COL].notna()
    )
    train_data = out[train_mask]

    if len(train_data) < 50:
        logger.warning(
            "device %s: 训练数据不足 (%d 行)，i_cal 全填 0",
            out["device_id"].iloc[0] if "device_id" in out.columns else "?",
            len(train_data),
        )
        out.drop(columns=["date"], inplace=True)
        return out

    X_train = train_data[REGRESSOR_FEATURES].values
    y_train = train_data[TARGET_COL].values

    reg = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        random_state=random_state,
        n_jobs=-1,
    )
    reg.fit(X_train, y_train)

    # 预测全量白天数据
    daylight_mask = (
        (out["poa_irradiance"] > DAYLIGHT_POA_THRESHOLD)
        & out["poa_irradiance"].notna()
        & out["module_temp"].notna()
    )
    if daylight_mask.any():
        X_pred = out.loc[daylight_mask, REGRESSOR_FEATURES].values
        out.loc[daylight_mask, "i_cal"] = reg.predict(X_pred)

    # 夜间保持 0
    # 质量统计
    r2 = reg.score(X_train, y_train)
    daylight_pts = daylight_mask.sum()
    device_id = out["device_id"].iloc[0] if "device_id" in out.columns else "?"
    logger.info(
        "  device %s: train R²=%.3f, train_pts=%d, daylight_pts=%d",
        device_id, r2, len(train_data), daylight_pts,
    )

    out.drop(columns=["date"], inplace=True)
    return out


# ---------------------------------------------------------------------------
# 批量入口
# ---------------------------------------------------------------------------

def build_all_ical(
    converted_dir: str | Path,
    truth_csv: str | Path,
) -> List[Dict[str, Any]]:
    """
    为全部 cohort 设备构造 i_cal 列，覆盖写入 converted/ parquet。

    Parameters
    ----------
    converted_dir : path
        转换后 parquet 目录
    truth_csv : path
        q1_daily_truth.csv 金标文件

    Returns
    -------
    list[dict]
        每台设备的构造统计
    """
    converted_dir = Path(converted_dir)
    truth = pd.read_csv(truth_csv)
    truth["date"] = pd.to_datetime(truth["date"]).dt.date

    stats: List[Dict[str, Any]] = []

    # 按 system_id（= device）分组
    for sid, grp in truth.groupby("system_id"):
        sid = int(sid)
        normal_dates = set(grp[grp["label"] == "normal"]["date"])
        device_id = f"pvdaq-system-{sid}"

        sys_dir = converted_dir / str(sid)
        if not sys_dir.exists():
            logger.warning("system %d: 目录不存在", sid)
            stats.append({"system_id": sid, "status": "dir_not_found"})
            continue

        logger.info("构造 i_cal: system=%d (%d 正常日)", sid, len(normal_dates))

        # 加载该设备全部月份合并
        month_files = sorted(sys_dir.glob("*.parquet"))
        all_months = []
        for f in month_files:
            df = pd.read_parquet(f)
            df["_source_file"] = f.name
            all_months.append(df)

        if not all_months:
            stats.append({"system_id": sid, "status": "no_data"})
            continue

        combined = pd.concat(all_months, ignore_index=True)

        # 构造 i_cal
        result = build_ical_for_device(combined, normal_dates)

        # 拆回各月份写入
        for f in month_files:
            month_mask = result["_source_file"] == f.name
            month_df = result[month_mask].drop(columns=["_source_file"]).reset_index(drop=True)
            month_df.to_parquet(f, index=False, engine="pyarrow")

        stats.append({
            "system_id": sid,
            "status": "ok",
            "normal_days": len(normal_dates),
            "total_rows": len(combined),
        })

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="PVDAQ i_cal 统计回归构造器")
    parser.add_argument("--converted-dir", default="data/benchmark_raw/pvdaq/converted")
    parser.add_argument("--truth-csv", default="data/benchmark_raw/pvdaq/analysis/q1_daily_truth.csv")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    stats = build_all_ical(args.converted_dir, args.truth_csv)
    ok = sum(1 for s in stats if s.get("status") == "ok")
    print(f"\ni_cal 构造完成: {ok}/{len(stats)} 系统成功")
    for s in stats:
        print(f"  system {s['system_id']}: {s['status']}")


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
