"""
预上线端到端验证实验

假设今天是 2026-04-01，用威海负荷真实数据模拟 7 天预上线观察期。

两个模型：
  - production (mock-persistence-v1): 昨天同时刻值作为今天预测
  - prelaunch  (mock-rolling-avg-v1): 过去 7 天同时刻均值作为预测

流程：
  1. 重置 precision_ops 状态：persistence 设为 production，清除 rolling-avg
  2. 模拟入预上线：rolling-avg 注册为 shadow + 创建 prelaunch 队列项
  3. 逐天写入两个模型的预测 → 回填实际值 → 计算 MAPE
  4. 7 天后评估预上线是否毕业

运行方式:
  cd backend-service
  PYTHONPATH=. /opt/miniconda3/envs/aip_web/bin/python scripts/run_prelaunch_experiment.py
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import pandas as pd
import numpy as np

# 确保项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.precision_ops.utils import (
    BASE_DATA_DIR, _atomic_write_json, ensure_data_dir, generate_event_id, now_iso,
)
from services.precision_ops.prelaunch_manager import PrelaunchManager
from services.precision_ops.version_registry import VersionRegistry
from services.precision_ops.accuracy_tracker import AccuracyTracker
from services.precision_ops.prediction_store import PredictionStore

# ============================================================================
# 配置
# ============================================================================
SLOT = "default"
DATA_CSV = Path(__file__).resolve().parent.parent / "datasets" / "load_true_weihai_260415.csv"
EXPERIMENT_START = datetime(2026, 4, 1, tzinfo=timezone.utc)  # "今天"
OBSERVATION_DAYS = 7
PRODUCTION_WORKFLOW = "mock-persistence-v1"
PRODUCTION_TAG = "persistence-baseline"
PRELAUNCH_WORKFLOW = "mock-rolling-avg-v1"
PRELAUNCH_TAG = "prelaunch-rolling-7d"
CANDIDATE_ID = "experiment-candidate-001"

# ============================================================================
# Step 0: 加载数据
# ============================================================================
print("=" * 60)
print("预上线验证实验")
print("=" * 60)
print(f"\n[Step 0] 加载数据: {DATA_CSV.name}")

df = pd.read_csv(DATA_CSV)
df["record_time"] = pd.to_datetime(df["record_time"])
df = df.sort_values("record_time").reset_index(drop=True)
# 只保留 load 列
df = df[df["feature_name"] == "load"][["record_time", "value"]].copy()
df.columns = ["timestamp", "load"]

print(f"  数据范围: {df['timestamp'].min()} → {df['timestamp'].max()}")
print(f"  总行数: {len(df)}")
print(f"  时间间隔: 15 分钟")

# 构建 lookup: timestamp → load value
load_lookup = dict(zip(df["timestamp"], df["load"]))

# ============================================================================
# Step 1: 重置 precision_ops 状态
# ============================================================================
print(f"\n[Step 1] 重置 precision_ops 状态")

ensure_data_dir(SLOT)

# 重写 version_registry: persistence 为 production
registry_data = {
    "slot": SLOT,
    "versions": [
        {
            "workflow_id": PRODUCTION_WORKFLOW,
            "version_tag": PRODUCTION_TAG,
            "status": "production",
            "slot": SLOT,
            "baseline_mape": None,
            "registered_at": "2026-03-25T00:00:00+00:00",
            "source_run_id": None,
            "source_candidate_id": None,
        }
    ],
    "max_shadow_versions": 5,
}
_atomic_write_json(BASE_DATA_DIR / SLOT / "version_registry.json", registry_data)
print(f"  production: {PRODUCTION_WORKFLOW} ({PRODUCTION_TAG})")
print(f"  已清除 rolling-avg（将通过预上线流程重新注册）")

# 清除旧的 prelaunch_queue
prelaunch_path = BASE_DATA_DIR / SLOT / "prelaunch_queue.json"
if prelaunch_path.exists():
    prelaunch_path.unlink()

# 清除旧的 accuracy_metrics
_atomic_write_json(BASE_DATA_DIR / SLOT / "accuracy_metrics.json", {
    "slot": SLOT,
    "evaluation_window_days": 7,
    "metrics": {},
    "updated_at": now_iso(),
})

# ============================================================================
# Step 2: 入预上线
# ============================================================================
print(f"\n[Step 2] 模拟入预上线: {PRELAUNCH_WORKFLOW}")

pm = PrelaunchManager()
vr = VersionRegistry()

# 注册为 shadow
vr.register({
    "workflow_id": PRELAUNCH_WORKFLOW,
    "version_tag": PRELAUNCH_TAG,
    "status": "shadow",
    "slot": SLOT,
    "baseline_mape": None,
    "source_candidate_id": CANDIDATE_ID,
})

# 创建预上线队列项
item = pm.enqueue(
    slot=SLOT,
    candidate_id=CANDIDATE_ID,
    workflow_id=PRELAUNCH_WORKFLOW,
    version_tag=PRELAUNCH_TAG,
    observation_days=OBSERVATION_DAYS,
    graduate_tolerance_pct=5.0,
    note="端到端验证实验: rolling-7d vs persistence",
)
print(f"  预上线 ID: {item['id']}")
print(f"  观察天数: {OBSERVATION_DAYS}")
print(f"  毕业容差: 5%")

# ============================================================================
# Step 3: 逐天模拟预测 + 回填实际值 + 计算 MAPE
# ============================================================================
print(f"\n[Step 3] 模拟 {OBSERVATION_DAYS} 天预测观察期")
print(f"  假设今天: {EXPERIMENT_START.strftime('%Y-%m-%d')}")
print(f"  观察期: {EXPERIMENT_START.strftime('%Y-%m-%d')} → "
      f"{(EXPERIMENT_START + timedelta(days=OBSERVATION_DAYS)).strftime('%Y-%m-%d')}")
print()

# 初始化 prediction store
ps = PredictionStore()

daily_results = []

for day_offset in range(OBSERVATION_DAYS):
    current_date = EXPERIMENT_START + timedelta(days=day_offset)
    cycle_id = f"cycle-{current_date.strftime('%Y%m%d')}"

    # 获取当天所有 15 分钟时间点
    day_timestamps = []
    t = current_date
    while t < current_date + timedelta(days=1):
        day_timestamps.append(t)
        t += timedelta(minutes=15)

    prod_errors = []
    prelaunch_errors = []
    pred_count = 0

    for ts in day_timestamps:
        ts_naive = ts.replace(tzinfo=None)
        actual = load_lookup.get(pd.Timestamp(ts_naive))
        if actual is None or actual == 0:
            continue

        # Production: persistence (昨天同时刻)
        yesterday = ts_naive - timedelta(days=1)
        prod_pred = load_lookup.get(pd.Timestamp(yesterday))

        # Prelaunch: 7 天滚动均值
        rolling_preds = []
        for d in range(1, 8):
            past = ts_naive - timedelta(days=d)
            val = load_lookup.get(pd.Timestamp(past))
            if val is not None:
                rolling_preds.append(val)
        prelaunch_pred = np.mean(rolling_preds) if rolling_preds else None

        if prod_pred is None or prelaunch_pred is None:
            continue

        # 计算误差
        prod_error = abs(prod_pred - actual) / actual
        prelaunch_error = abs(prelaunch_pred - actual) / actual
        prod_errors.append(prod_error)
        prelaunch_errors.append(prelaunch_error)
        pred_count += 1

        # 写入 prediction store (每小时采样一次，避免写太多)
        if ts_naive.minute == 0:
            forecast_ts = ts.isoformat()
            ps.record_prediction(SLOT, PRODUCTION_WORKFLOW, PRODUCTION_TAG,
                                 cycle_id, forecast_ts, prod_pred)
            ps.record_prediction(SLOT, PRELAUNCH_WORKFLOW, PRELAUNCH_TAG,
                                 cycle_id, forecast_ts, prelaunch_pred)

    prod_mape = np.mean(prod_errors) * 100 if prod_errors else None
    prelaunch_mape = np.mean(prelaunch_errors) * 100 if prelaunch_errors else None

    daily_results.append({
        "date": current_date.strftime("%Y-%m-%d"),
        "prod_mape": prod_mape,
        "prelaunch_mape": prelaunch_mape,
        "points": pred_count,
    })

    winner = "预上线" if (prelaunch_mape and prod_mape and prelaunch_mape < prod_mape) else "生产"
    print(f"  {current_date.strftime('%m/%d')} | "
          f"生产 MAPE: {prod_mape:.4f}%  |  预上线 MAPE: {prelaunch_mape:.4f}%  |  "
          f"胜出: {winner}  |  {pred_count} 点")

# ============================================================================
# Step 4: 汇总 + 写入 accuracy_metrics
# ============================================================================
print(f"\n[Step 4] 汇总精度指标")

avg_prod_mape = np.mean([r["prod_mape"] for r in daily_results if r["prod_mape"]])
avg_prelaunch_mape = np.mean([r["prelaunch_mape"] for r in daily_results if r["prelaunch_mape"]])
total_points = sum(r["points"] for r in daily_results)
prelaunch_win_days = sum(1 for r in daily_results
                         if r["prelaunch_mape"] and r["prod_mape"]
                         and r["prelaunch_mape"] < r["prod_mape"])

print(f"  生产 7 天平均 MAPE: {avg_prod_mape:.4f}%")
print(f"  预上线 7 天平均 MAPE: {avg_prelaunch_mape:.4f}%")
print(f"  预上线胜出天数: {prelaunch_win_days}/{OBSERVATION_DAYS}")
print(f"  总评估点数: {total_points}")

# 写入 accuracy_metrics（模拟 AccuracyTracker 的输出）
metrics_data = {
    "slot": SLOT,
    "evaluation_window_days": OBSERVATION_DAYS,
    "metrics": {
        PRODUCTION_WORKFLOW: {
            "rolling_mape": round(avg_prod_mape, 4),
            "rolling_mae": 0,
            "valid_cycle_count": OBSERVATION_DAYS,
            "total_cycle_count": OBSERVATION_DAYS,
            "last_evaluated_at": (EXPERIMENT_START + timedelta(days=OBSERVATION_DAYS)).isoformat(),
            "status": "active",
        },
        PRELAUNCH_WORKFLOW: {
            "rolling_mape": round(avg_prelaunch_mape, 4),
            "rolling_mae": 0,
            "valid_cycle_count": OBSERVATION_DAYS,
            "total_cycle_count": OBSERVATION_DAYS,
            "last_evaluated_at": (EXPERIMENT_START + timedelta(days=OBSERVATION_DAYS)).isoformat(),
            "status": "active",
        },
    },
    "updated_at": (EXPERIMENT_START + timedelta(days=OBSERVATION_DAYS)).isoformat(),
}
_atomic_write_json(BASE_DATA_DIR / SLOT / "accuracy_metrics.json", metrics_data)

# ============================================================================
# Step 5: 评估预上线毕业
# ============================================================================
print(f"\n[Step 5] 评估预上线毕业条件")

tolerance_pct = 5.0
threshold = avg_prod_mape * (1 + tolerance_pct / 100)
print(f"  毕业条件: 预上线 MAPE ≤ 生产 MAPE × {1 + tolerance_pct/100:.2f}")
print(f"  阈值: {threshold:.4f}%")
print(f"  预上线 MAPE: {avg_prelaunch_mape:.4f}%")

if avg_prelaunch_mape <= threshold:
    print(f"\n  ✅ 预上线通过！MAPE {avg_prelaunch_mape:.4f}% ≤ 阈值 {threshold:.4f}%")
    print(f"     → 可以毕业上线（替换 persistence 成为新 production）")

    # 更新 prelaunch_queue 状态
    queue = pm.get_queue(SLOT)
    for q_item in queue:
        if q_item.get("status") == "observing":
            q_item["current_rolling_mape"] = round(avg_prelaunch_mape, 4)
            q_item["production_rolling_mape"] = round(avg_prod_mape, 4)
            q_item["evaluated_cycles"] = OBSERVATION_DAYS
    pm._save(SLOT, queue)
else:
    print(f"\n  ❌ 预上线未通过。MAPE {avg_prelaunch_mape:.4f}% > 阈值 {threshold:.4f}%")
    print(f"     → 保留为 shadow，不上线")

# ============================================================================
# Step 6: 打印实验结果表
# ============================================================================
print(f"\n{'='*60}")
print("实验结果汇总")
print(f"{'='*60}")
print(f"\n{'日期':<12} {'生产 MAPE%':<12} {'预上线 MAPE%':<14} {'差异':<10} {'胜出'}")
print("-" * 60)
for r in daily_results:
    diff = r["prelaunch_mape"] - r["prod_mape"]
    winner = "预上线 ✓" if diff < 0 else "生产"
    print(f"{r['date']:<12} {r['prod_mape']:<12.4f} {r['prelaunch_mape']:<14.4f} "
          f"{diff:+.4f}    {winner}")
print("-" * 60)
print(f"{'平均':<12} {avg_prod_mape:<12.4f} {avg_prelaunch_mape:<14.4f} "
      f"{avg_prelaunch_mape - avg_prod_mape:+.4f}")
print()
print("实验结论:")
print(f"  - 滚动7天均值模型在 {prelaunch_win_days}/{OBSERVATION_DAYS} 天优于 persistence 模型")
if avg_prelaunch_mape <= threshold:
    print(f"  - 预上线毕业条件满足，推荐正式上线")
    print(f"  - 上线后，原 persistence 模型将降级为影子版本继续对比")
else:
    print(f"  - 预上线未达标，建议继续观察或更换候选")

print(f"\n数据已写入:")
print(f"  - {BASE_DATA_DIR / SLOT / 'version_registry.json'}")
print(f"  - {BASE_DATA_DIR / SLOT / 'accuracy_metrics.json'}")
print(f"  - {BASE_DATA_DIR / SLOT / 'prelaunch_queue.json'}")
print(f"  - {BASE_DATA_DIR / 'predictions.db'} (SQLite)")
print(f"\n启动后端 + 前端后，可在 Research Cockpit「预上线」Tab 看到结果。")
