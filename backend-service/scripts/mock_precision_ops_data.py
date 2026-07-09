#!/usr/bin/env python3
"""
mock_precision_ops_data.py — 用威海负荷数据模拟精度运营多日预测周期

数据源：datasets/load_true_weihai_260415.csv
防数据穿越：预测第 D 天时仅使用第 D-1 天及更早数据

两个模拟版本：
  A) Persistence — 用前一天同时刻负荷值作为预测
  B) Rolling-7d  — 用前 7 天同时刻均值作为预测

用法：
  cd /Users/zxk/Desktop/project/AIP/backend-service
  PYTHONPATH=. conda run -n aip_web python scripts/mock_precision_ops_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone

from services.precision_ops.utils import BASE_DATA_DIR, now_iso, ensure_data_dir, _atomic_write_json
from services.precision_ops.prediction_store import PredictionStore
from services.precision_ops.accuracy_tracker import AccuracyTracker
from services.precision_ops.version_registry import VersionRegistry

SLOT = "default"
CSV_PATH = Path(__file__).parent.parent / "datasets" / "load_true_weihai_260415.csv"

# 两个模拟版本的配置
VERSION_A = {
    "workflow_id": "mock-persistence-v1",
    "version_tag": "mock-persistence",
    "status": "production",
    "baseline_mape": 3.0,
}
VERSION_B = {
    "workflow_id": "mock-rolling-avg-v1",
    "version_tag": "mock-rolling-7d",
    "status": "shadow",
    "baseline_mape": 2.5,
}

POINTS_PER_DAY = 96
HISTORY_DAYS = 7      # 版本 B 需要 7 天历史
FORECAST_DAYS = 10    # 模拟 10 天预测周期


def load_data() -> pd.DataFrame:
    """加载 CSV，按 record_time 排序，只保留 load 值"""
    df = pd.read_csv(CSV_PATH)
    df["record_time"] = pd.to_datetime(df["record_time"])
    df = df.sort_values("record_time").reset_index(drop=True)
    return df[["record_time", "value"]].copy()


def group_by_day(df: pd.DataFrame) -> dict:
    """按天分组，只保留有完整 96 个点的天。返回 {date: DataFrame}"""
    df["date"] = df["record_time"].dt.date
    groups = {}
    for date, group in df.groupby("date"):
        if len(group) == POINTS_PER_DAY:
            groups[date] = group.reset_index(drop=True)
    return groups


def clean_mock_data(store: PredictionStore):
    """清除已有的 mock 预测数据和精度指标"""
    # 清除 predictions.db 中 mock 版本的记录
    with sqlite3.connect(str(store.db_path), timeout=5.0) as conn:
        conn.execute(
            "DELETE FROM predictions WHERE workflow_id IN (?, ?)",
            (VERSION_A["workflow_id"], VERSION_B["workflow_id"]),
        )
        conn.commit()
        deleted = conn.execute(
            "SELECT changes()"
        ).fetchone()[0]
    print(f"🗑️  清除已有 mock 预测记录: {deleted} 条")

    # 清除 accuracy_metrics.json 中 mock 版本的条目
    metrics_path = BASE_DATA_DIR / SLOT / "accuracy_metrics.json"
    if metrics_path.exists():
        import json
        with open(metrics_path, "r") as f:
            data = json.load(f)
        metrics = data.get("metrics", {})
        for wf_id in [VERSION_A["workflow_id"], VERSION_B["workflow_id"]]:
            metrics.pop(wf_id, None)
        data["metrics"] = metrics
        _atomic_write_json(metrics_path, data)
    print("🗑️  清除已有 mock 精度指标")


def register_versions(registry: VersionRegistry):
    """注册两个模拟版本（幂等，已存在则跳过）"""
    for ver in [VERSION_A, VERSION_B]:
        entry = {
            "workflow_id": ver["workflow_id"],
            "version_tag": ver["version_tag"],
            "status": ver["status"],
            "slot": SLOT,
            "baseline_mape": ver["baseline_mape"],
        }
        try:
            registry.register(entry)
            print(f"✅ 注册版本: {ver['version_tag']} ({ver['status']})")
        except ValueError as e:
            if "已存在" in str(e):
                print(f"⏭️  版本已存在，跳过: {ver['version_tag']}")
            else:
                raise


def simulate_predictions(
    day_groups: dict,
    sorted_dates: list,
    store: PredictionStore,
):
    """
    模拟 10 天的预测周期。
    对于每天 D（day_8 到 day_17）：
      - 版本 A: pred_D_t = actual_{D-1}_t（persistence）
      - 版本 B: pred_D_t = mean(actual_{D-7}_t, ..., actual_{D-1}_t)（rolling 7d）
      - 存储预测 + 回填实际值
    """
    start_idx = HISTORY_DAYS  # 从第 8 天开始（索引 7），确保有 7 天历史
    end_idx = start_idx + FORECAST_DAYS

    if end_idx > len(sorted_dates):
        print(f"⚠️  数据不足：需要 {end_idx} 天，实际只有 {len(sorted_dates)} 天")
        end_idx = len(sorted_dates)

    total_predictions = 0

    for day_idx in range(start_idx, end_idx):
        target_date = sorted_dates[day_idx]
        target_df = day_groups[target_date]
        cycle_id = f"mock-cycle-{target_date.isoformat()}"

        # 版本 A: Persistence（D-1 天同时刻）
        prev_date = sorted_dates[day_idx - 1]
        prev_df = day_groups[prev_date]

        for i in range(POINTS_PER_DAY):
            forecast_ts = target_df.iloc[i]["record_time"].isoformat()
            pred_a = float(prev_df.iloc[i]["value"])
            store.record_prediction(
                slot=SLOT,
                workflow_id=VERSION_A["workflow_id"],
                version_tag=VERSION_A["version_tag"],
                cycle_id=cycle_id,
                forecast_timestamp=forecast_ts,
                predicted_value=pred_a,
            )

        # 版本 B: Rolling 7d 均值
        for i in range(POINTS_PER_DAY):
            forecast_ts = target_df.iloc[i]["record_time"].isoformat()
            # 取 D-7 到 D-1 共 7 天同时刻的值
            history_values = []
            for offset in range(1, HISTORY_DAYS + 1):
                hist_date = sorted_dates[day_idx - offset]
                hist_df = day_groups[hist_date]
                history_values.append(float(hist_df.iloc[i]["value"]))
            pred_b = float(np.mean(history_values))
            store.record_prediction(
                slot=SLOT,
                workflow_id=VERSION_B["workflow_id"],
                version_tag=VERSION_B["version_tag"],
                cycle_id=cycle_id,
                forecast_timestamp=forecast_ts,
                predicted_value=pred_b,
            )

        # 回填实际值（两个版本共用同一个 cycle_id + forecast_timestamp）
        actuals = {}
        for i in range(POINTS_PER_DAY):
            forecast_ts = target_df.iloc[i]["record_time"].isoformat()
            actuals[forecast_ts] = float(target_df.iloc[i]["value"])
        store.fill_actuals(slot=SLOT, cycle_id=cycle_id, actuals=actuals)

        total_predictions += POINTS_PER_DAY * 2
        day_num = day_idx - start_idx + 1
        print(f"  📅 Day {day_num:2d} ({target_date}) — cycle_id={cycle_id}")

    return total_predictions, end_idx - start_idx


def compute_and_store_metrics(store: PredictionStore, tracker: AccuracyTracker, num_cycles: int):
    """为两个版本手动计算精度指标并写入 accuracy_metrics.json"""
    # 获取所有预测记录
    window_start = "2020-01-01T00:00:00"
    window_end = "2030-01-01T00:00:00"

    for ver in [VERSION_A, VERSION_B]:
        wf_id = ver["workflow_id"]
        records = store.get_predictions_in_window(SLOT, wf_id, window_start, window_end)

        # 过滤已评估的记录
        evaluated = [r for r in records if r.get("actual_value") is not None]
        if not evaluated:
            print(f"  ⚠️  {ver['version_tag']}: 无已评估记录")
            continue

        # MAPE: 排除 actual=0
        mape_records = [r for r in evaluated if r["actual_value"] != 0.0]
        if mape_records:
            errors = [
                abs(r["predicted_value"] - r["actual_value"]) / abs(r["actual_value"])
                for r in mape_records
            ]
            rolling_mape = sum(errors) / len(errors) * 100
        else:
            rolling_mape = 0.0

        # MAE: 包含 actual=0
        abs_errors = [
            abs(r["predicted_value"] - r["actual_value"])
            for r in evaluated
        ]
        rolling_mae = sum(abs_errors) / len(abs_errors)

        metrics = {
            "rolling_mape": round(rolling_mape, 4),
            "rolling_mae": round(rolling_mae, 4),
            "valid_cycle_count": num_cycles,
            "total_cycle_count": num_cycles,
            "last_evaluated_at": now_iso(),
            "status": "active",
        }
        tracker.update_metrics(SLOT, wf_id, metrics)
        print(f"  📊 {ver['version_tag']:20s} | MAPE={rolling_mape:.4f}% | MAE={rolling_mae:.2f}")


def main():
    print(f"📊 加载数据集: {CSV_PATH}")
    df = load_data()
    print(f"   总记录数: {len(df)}")

    day_groups = group_by_day(df)
    sorted_dates = sorted(day_groups.keys())
    print(f"   完整天数: {len(sorted_dates)} (每天 {POINTS_PER_DAY} 个点)")
    print(f"   日期范围: {sorted_dates[0]} ~ {sorted_dates[-1]}")

    if len(sorted_dates) < HISTORY_DAYS + FORECAST_DAYS:
        print(f"❌ 数据不足：需要至少 {HISTORY_DAYS + FORECAST_DAYS} 天完整数据")
        sys.exit(1)

    # 初始化服务
    ensure_data_dir(SLOT)
    store = PredictionStore()
    tracker = AccuracyTracker()
    registry = VersionRegistry()

    # 1. 清理已有 mock 数据
    print("\n🧹 清理已有 mock 数据...")
    clean_mock_data(store)

    # 2. 注册版本
    print("\n📝 注册模拟版本...")
    register_versions(registry)

    # 3. 模拟预测周期
    print(f"\n🔄 模拟 {FORECAST_DAYS} 天预测周期 (day_{HISTORY_DAYS+1} ~ day_{HISTORY_DAYS+FORECAST_DAYS})...")
    total_preds, num_cycles = simulate_predictions(day_groups, sorted_dates, store)
    print(f"   总预测点数: {total_preds}")

    # 4. 计算精度指标
    print("\n📈 计算精度指标...")
    compute_and_store_metrics(store, tracker, num_cycles)

    # 5. 验证输出
    print("\n✅ 完成！数据写入位置:")
    print(f"   预测数据库: {store.db_path}")
    metrics_path = BASE_DATA_DIR / SLOT / "accuracy_metrics.json"
    print(f"   精度指标:   {metrics_path}")
    registry_path = BASE_DATA_DIR / SLOT / "version_registry.json"
    print(f"   版本注册:   {registry_path}")

    # 打印最终 accuracy_metrics.json 内容
    from services.precision_ops.utils import load_json_safe
    final_metrics = load_json_safe(metrics_path, default={})
    print(f"\n📋 accuracy_metrics.json 最终内容:")
    import json
    print(json.dumps(final_metrics, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
