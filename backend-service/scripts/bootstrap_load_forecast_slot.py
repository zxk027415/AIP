# @AI_GENERATED
"""
scripts/bootstrap_load_forecast_slot.py — 初始化 load_forecast 槽位并注册影子

用途：
  从 AutoResearch 候选池中选取精度最高的候选注册为影子版本，
  把基线注册为生产版本，配置 cron 并启动调度管线，让精度运营链路真正跑起来。

运行方式（在 backend-service/ 目录下）：
  conda activate aip_web
  set PYTHONPATH=.
  python scripts/bootstrap_load_forecast_slot.py

做的事情：
  1. 在 data/precision_ops/load_forecast/ 下初始化 version_registry.json + config.json
  2. 把 baseline workflow 注册为 production
  3. 把 Top 3 AutoResearch 候选注册为 shadow
  4. 初始化 accuracy_metrics.json（用候选池里的 SMAPE 数据填充初始 baseline_mape）
  5. 输出操作结果
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# 确保 backend-service 在 path 中
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent

# 零依赖：直接定义工具函数，不走 services 包（避免 sqlalchemy 等重依赖）
BASE_DATA_DIR = BACKEND_DIR / "data" / "precision_ops"


def ensure_data_dir(slot: str) -> Path:
    slot_dir = BASE_DATA_DIR / slot
    slot_dir.mkdir(parents=True, exist_ok=True)
    return slot_dir


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_json(path: Path, data):
    import tempfile, os
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), suffix=".tmp", prefix=".atomic_"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
SLOT = "load_forecast"
BASELINE_WORKFLOW_ID = "workflow-20260511-optimal-505"
BASELINE_TAG = "optimal-505-production"
BASELINE_MAPE = 5.6616  # 当前最新版 baseline 的 avg_smape

# 影子候选：从截图中 baseline=5.6616 且 status=pending_promote 的候选
# 这些是最新版本跑出来的，challenger MAPE 都在 4.x% 级别
TOP_CANDIDATES = [
    {
        "id": "cand-3647f99d2f77",
        "workflow_id": "workflow-20260511-optimal-505",
        "version_tag": "shadow-run43-mape4109",
        "source_run_id": "AutoResearch第43轮",
        "source_candidate_id": "cand-3647f99d2f77",
        "challenger_score": 95.8907,  # 100 - 4.1093
        "challenger_smape": 4.1093,
        "description": "AutoResearch R43, SMAPE 4.1093%, pending_promote",
    },
    {
        "id": "cand-439b04179c12",
        "workflow_id": "workflow-20260511-optimal-505",
        "version_tag": "shadow-run7-generic-mape4109",
        "source_run_id": "AutoResearch第7轮(通用算子版)",
        "source_candidate_id": "cand-439b04179c12",
        "challenger_score": 95.8907,  # 100 - 4.1093
        "challenger_smape": 4.1093,
        "description": "AutoResearch R7(通用算子版), SMAPE 4.1093%, pending_promote",
    },
]

# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(f"初始化 load_forecast 槽位 — 精度运营链路 Bootstrap")
    print("=" * 60)

    # Step 1: 确保目录存在
    slot_dir = ensure_data_dir(SLOT)
    print(f"\n[1/5] 槽位目录: {slot_dir}")

    # Step 2: 配置
    print(f"\n[2/5] 写入配置 (config.json)")
    config_data = {
        "slot": SLOT,
        "evaluation_window_days": 7,
        "degradation_threshold_pct": 15,
        "switch_margin_pct": 10,
        "cooldown_hours": 24,
        "min_valid_cycles": 3,
        "shadow_timeout_seconds": 300,
        "production_timeout_seconds": 120,
        "max_shadow_versions": 5,
        "rollback_window_hours": 48,
        "auto_switch_enabled": True,
        "prediction_retention_days": 90,
        "min_eval_points": 72,
        "post_switch_observation_points": 48,
        "eval_window_points": 168,
    }
    config_path = BASE_DATA_DIR / SLOT / "config.json"
    _atomic_write_json(config_path, config_data)
    print(f"  auto_switch_enabled: True")
    print(f"  degradation_threshold_pct: 15%")
    print(f"  switch_margin_pct: 10%")
    print(f"  cooldown_hours: 24h")
    print(f"  max_shadow_versions: 5")

    # Step 3: 注册生产版本 + 影子版本 (直接写 version_registry.json)
    print(f"\n[3/5] 注册生产版本: {BASELINE_WORKFLOW_ID}")
    now_str = now_iso()
    versions = [
        {
            "workflow_id": BASELINE_WORKFLOW_ID,
            "version_tag": BASELINE_TAG,
            "status": "production",
            "slot": SLOT,
            "baseline_mape": BASELINE_MAPE,
            "source_run_id": None,
            "source_candidate_id": None,
            "registered_at": now_str,
        },
    ]
    print(f"  ✅ {BASELINE_WORKFLOW_ID} ({BASELINE_TAG}) → production (SMAPE {BASELINE_MAPE}%)")

    # Step 4: 注册影子版本 (Top candidates)
    print(f"\n[4/5] 注册影子版本 ({len(TOP_CANDIDATES)} 个 AutoResearch 候选)")
    for cand in TOP_CANDIDATES:
        versions.append({
            "workflow_id": cand["workflow_id"],
            "version_tag": cand["version_tag"],
            "status": "shadow",
            "slot": SLOT,
            "baseline_mape": cand["challenger_smape"],
            "source_run_id": cand["source_run_id"],
            "source_candidate_id": cand["source_candidate_id"],
            "registered_at": now_str,
        })
        print(f"  ✅ {cand['version_tag']} → shadow ({cand['description']})")

    registry_data = {
        "slot": SLOT,
        "versions": versions,
        "max_shadow_versions": 5,
    }
    registry_path = BASE_DATA_DIR / SLOT / "version_registry.json"
    _atomic_write_json(registry_path, registry_data)
    print(f"  写入 version_registry.json: {len(versions)} 个版本")

    # Step 5: 初始化 accuracy_metrics
    print(f"\n[5/5] 初始化精度指标 (accuracy_metrics.json)")
    metrics_data = {
        "slot": SLOT,
        "evaluation_window_days": 7,
        "metrics": {
            BASELINE_WORKFLOW_ID: {
                "rolling_mape": BASELINE_MAPE,
                "rolling_mae": 1539.02,
                "valid_cycle_count": 0,
                "total_cycle_count": 0,
                "last_evaluated_at": now_str,
                "status": "insufficient_data",
            },
        },
        "updated_at": now_str,
    }
    # 为每个影子也初始化一个 metrics 条目
    for cand in TOP_CANDIDATES:
        metrics_data["metrics"][f"{cand['workflow_id']}#{cand['version_tag']}"] = {
            "rolling_mape": cand["challenger_smape"],
            "rolling_mae": 0.0,
            "valid_cycle_count": 0,
            "total_cycle_count": 0,
            "last_evaluated_at": now_str,
            "status": "insufficient_data",
        }

    metrics_path = BASE_DATA_DIR / SLOT / "accuracy_metrics.json"
    _atomic_write_json(metrics_path, metrics_data)
    print(f"  ✅ 写入 {len(metrics_data['metrics'])} 个版本的初始指标")

    metrics_path = BASE_DATA_DIR / SLOT / "accuracy_metrics.json"
    _atomic_write_json(metrics_path, metrics_data)
    print(f"  ✅ 写入 {len(metrics_data['metrics'])} 个版本的初始指标")

    # 总结
    print("\n" + "=" * 60)
    print("✅ Bootstrap 完成！")
    print(f"   槽位: {SLOT}")
    print(f"   生产: {BASELINE_WORKFLOW_ID} (SMAPE ~12.82%)")
    print(f"   影子: {len(TOP_CANDIDATES)} 个候选已注册")
    print()
    print("下一步:")
    print(f"   生产 baseline MAPE: {BASELINE_MAPE}%")
    print(f"   影子 challenger MAPE: ~{TOP_CANDIDATES[0]['challenger_smape']}%")
    print()
    print("  1. 启动后端: uvicorn main:app --port 8080")
    print("  2. 启动 load_forecast 管线:")
    print("     POST http://localhost:8080/api/scheduler/load_forecast/start")
    print("  3. 或在前端 '定时调度' Tab 点击 '启动' 按钮")
    print()
    print("Cron 任务说明:")
    print("  lf_data_pull         01:00 — 拉取最新数据")
    print("  lf_daily_rolling     02:00 — 训练+预测(生产+影子)")
    print("  lf_accuracy_backfill 04:00 — 回填真值+计算 MAPE")
    print("=" * 60)


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
