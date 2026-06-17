# @AI_GENERATED
"""
Add energy forecast templates under power-grid scenario in industry_templates.json
and mount load forecast workflows to the new business scenarios.
"""
import json
import os
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_FILE = os.path.join(BACKEND_DIR, "data", "industry_templates.json")
MOUNT_FILE = os.path.join(BACKEND_DIR, "data", "scenario_workflow_mounts.json")
WF_DIR = os.path.join(BACKEND_DIR, "data", "workflows_enhanced")

# New energy forecast templates under power-grid
NEW_TEMPLATES = [
    {
        "id": "energy_load_forecast",
        "name": "负荷预测",
        "scenario_id": "power-grid",
        "display_category": "能源预测",
        "description": "电力负荷预测，支持节点负荷、母线负荷和区域负荷等多种场景",
        "default_workflows": [
            {
                "profile": "high-accuracy",
                "name": "通用算子方案（贝叶斯优化）",
                "layers": {
                    "数据管理层": ["load_csv", "row_filter"],
                    "数据处理层": ["resample_timeseries", "detect_outliers", "handle_missing"],
                    "特征工程层": ["extract_time_features", "holiday_features", "workday_features", "rolling_statistics", "create_lag_features", "sliding_window"],
                    "算法模型层": ["train_test_split_ts", "multi_step_forecast", "auto_tune_xgboost", "xgboost_forecast"],
                    "评估输出层": ["smape_score", "mse_rmse_mae"]
                }
            },
            {
                "profile": "balanced",
                "name": "快速训练方案",
                "layers": {
                    "数据管理层": ["load_csv"],
                    "数据处理层": ["resample_timeseries", "handle_missing"],
                    "算法模型层": ["xgboost_forecast"],
                    "评估输出层": ["smape_score"]
                }
            }
        ]
    },
    {
        "id": "energy_wind_forecast",
        "name": "风力发电预测",
        "scenario_id": "power-grid",
        "display_category": "能源预测",
        "description": "风力发电功率预测，支持陆上风电和海上风电场景",
        "default_workflows": [
            {
                "profile": "high-accuracy",
                "name": "深度学习方案",
                "layers": {
                    "数据管理层": ["load_csv", "load_timeseries_db"],
                    "数据处理层": ["handle_missing", "resample_timeseries", "min_max_scale"],
                    "算法模型层": ["lstm_forecast", "xgboost_forecast"],
                    "评估输出层": ["mape_metric", "rmse_metric"]
                }
            }
        ]
    },
    {
        "id": "energy_pv_forecast",
        "name": "光伏发电预测",
        "scenario_id": "power-grid",
        "display_category": "能源预测",
        "description": "光伏发电功率预测，支持集中式和分布式光伏场景",
        "default_workflows": [
            {
                "profile": "high-accuracy",
                "name": "深度学习方案",
                "layers": {
                    "数据管理层": ["load_csv", "load_timeseries_db"],
                    "数据处理层": ["handle_missing", "resample_timeseries", "wavelet_denoise"],
                    "算法模型层": ["lstm_forecast", "transformer_forecast"],
                    "评估输出层": ["mape_metric", "rmse_metric"]
                }
            }
        ]
    },
    {
        "id": "energy_hydro_forecast",
        "name": "水电预测",
        "scenario_id": "power-grid",
        "display_category": "能源预测",
        "description": "水力发电功率预测，支持水库式和径流式水电场景",
        "default_workflows": [
            {
                "profile": "balanced",
                "name": "统计学习方案",
                "layers": {
                    "数据管理层": ["load_csv"],
                    "数据处理层": ["handle_missing", "resample_timeseries"],
                    "算法模型层": ["xgboost_forecast", "random_forest_forecast"],
                    "评估输出层": ["mape_metric", "rmse_metric"]
                }
            }
        ]
    },
    {
        "id": "energy_thermal_forecast",
        "name": "火电预测",
        "scenario_id": "power-grid",
        "display_category": "能源预测",
        "description": "火力发电出力预测，支持燃煤和燃气火电场景",
        "default_workflows": [
            {
                "profile": "balanced",
                "name": "机器学习方案",
                "layers": {
                    "数据管理层": ["load_csv"],
                    "数据处理层": ["handle_missing", "resample_timeseries"],
                    "算法模型层": ["xgboost_forecast"],
                    "评估输出层": ["mape_metric", "rmse_metric"]
                }
            }
        ]
    },
    {
        "id": "energy_price_forecast",
        "name": "价格预测",
        "scenario_id": "power-grid",
        "display_category": "能源预测",
        "description": "电力市场价格预测，支持现货和期货价格场景",
        "default_workflows": [
            {
                "profile": "balanced",
                "name": "时序预测方案",
                "layers": {
                    "数据管理层": ["load_csv"],
                    "数据处理层": ["handle_missing", "resample_timeseries"],
                    "算法模型层": ["arima_forecast", "xgboost_forecast"],
                    "评估输出层": ["mape_metric", "rmse_metric"]
                }
            }
        ]
    },
]


def add_templates():
    with open(TEMPLATES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_ids = {t["id"] for t in data["templates"]}
    added = 0
    for tpl in NEW_TEMPLATES:
        if tpl["id"] not in existing_ids:
            data["templates"].append(tpl)
            added += 1
            print(f"  Added: {tpl['name']} ({tpl['id']})")
        else:
            print(f"  Exists: {tpl['name']} ({tpl['id']})")

    data["total_templates"] = len(data["templates"])

    with open(TEMPLATES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  Total templates: {data['total_templates']} (+{added})")


def mount_workflows():
    """Mount load forecast workflows to the new energy_load_forecast business scenarios."""
    mounts = {}
    if os.path.exists(MOUNT_FILE):
        with open(MOUNT_FILE, "r", encoding="utf-8") as f:
            mounts = json.load(f)

    now = datetime.now().isoformat()
    workflow_ids = [
        "workflow-load-forecast-training-v2",
        "workflow-load-forecast-prediction-v2",
        "workflow-load-forecast-backtest-v2",
    ]

    # Mount to each new business scenario
    for scenario_id in ["node_load", "busbar_load", "regional_load"]:
        key = f"energy_load_forecast_{scenario_id}"
        if key not in mounts:
            mounts[key] = []

        for wf_id in workflow_ids:
            if any(m["id"] == wf_id for m in mounts[key]):
                continue
            wf_path = os.path.join(WF_DIR, f"{wf_id}.json")
            if os.path.exists(wf_path):
                with open(wf_path, "r", encoding="utf-8") as f:
                    wf = json.load(f)
                mounts[key].append({
                    "id": wf_id,
                    "name": wf["name"],
                    "node_count": len(wf["nodes"]),
                    "edge_count": len(wf["edges"]),
                    "mounted_at": now,
                })
                print(f"  Mounted: {wf['name']} -> {key}")

    with open(MOUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(mounts, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print("1. Adding energy forecast templates to industry_templates.json...")
    add_templates()
    print("\n2. Mounting load forecast workflows to new business scenarios...")
    mount_workflows()
    print("\nDone!")
# @AI_GENERATED: end
