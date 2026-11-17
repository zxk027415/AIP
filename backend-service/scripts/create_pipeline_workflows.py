# @AI_GENERATED
"""
Create enhanced workflow JSON files for the 3 load forecast pipeline templates
and mount them to the load_forecast scenario.
"""
import json
import os
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF_DIR = os.path.join(BACKEND_DIR, "data", "workflows_enhanced")
MOUNT_FILE = os.path.join(BACKEND_DIR, "data", "scenario_workflow_mounts.json")
os.makedirs(WF_DIR, exist_ok=True)


def _make_node(idx, operator_id, label, x, y, params, description=""):
    return {
        "id": f"tpl-{operator_id}-{idx}",
        "type": "enhanced",
        "position": {"x": x, "y": y},
        "data": {
            "label": label,
            "type": "function",
            "icon": None,
            "inputs": [{"id": "input-0", "name": "data", "type": "input", "dataType": "any"}],
            "outputs": [{"id": "output-0", "name": "data", "type": "output", "dataType": "any"}],
            "config": {"functionId": operator_id, **params},
            "status": "idle",
            "error": None,
            "description": description,
        },
    }


def _make_edge(idx, src_op, src_idx, tgt_op, tgt_idx):
    return {
        "id": f"tpl-edge-{idx}",
        "source": f"tpl-{src_op}-{src_idx}",
        "target": f"tpl-{tgt_op}-{tgt_idx}",
        "sourceHandle": None,
        "targetHandle": None,
        "type": "smoothstep",
        "data": None,
    }


TRAINING_DEFS = [
    (0, "load_csv", "CSV数据加载", 100, 100,
     {"timestamp_column": "record_time", "delimiter": ",", "encoding": "utf-8", "header_row": 0,
      "file_path": "datasets/load_true_weihai_260415.csv",
      "parent_field": "parent_id", "child_field": "child_id", "parent_id": "park_01", "child_id": "yARGkDuq"},
     "从 CSV 文件加载负荷时序数据，支持指定时间戳列和数值列"),
    (1, "row_filter", "行过滤", 300, 100,
     {"column_filters": "{\"parent_id\": \"park_01\", \"child_id\": \"yARGkDuq\"}"},
     "按父子节点 ID 过滤数据行，筛选出目标测量点的负荷数据"),
    (2, "resample_timeseries", "时序重采样", 500, 100,
     {"frequency": "15min", "method": "mean", "time_field": "record_time", "load_field": "value"},
     "将数据重采样到 15 分钟粒度，补全缺失时间戳"),
    (3, "detect_outliers", "异常值检测", 700, 100,
     {"method": "zscore", "threshold": 6.0, "load_field": "value", "window_size": 96},
     "使用滚动 Z-Score 检测异常值，将异常点标记为 NaN"),
    (4, "handle_missing", "缺失值处理", 900, 100,
     {"method": "linear", "time_field": "record_time", "load_field": "value"},
     "使用线性插值填充缺失值，确保数据无 NaN"),
    (5, "extract_time_features", "时间特征", 100, 300,
     {"features": ["hour", "dayofweek", "month", "day", "quarter"], "time_field": "record_time"},
     "提取小时、星期、月份等时间特征"),
    (6, "holiday_features", "节假日特征", 300, 300,
     {"time_field": "record_time", "remove_spring_festival": False},
     "标记中国法定节假日，区分节假日用电模式"),
    (7, "workday_features", "工作日特征", 500, 300,
     {"time_field": "record_time"},
     "标记工作日/休息日，区分工作日用电模式"),
    (8, "rolling_statistics", "滚动统计", 700, 300,
     {"target_column": "value", "window_sizes": [24, 48, 96, 168], "statistics": ["mean", "std"]},
     "计算滚动均值和标准差，捕捉局部趋势"),
    (9, "create_lag_features", "滞后特征", 900, 300,
     {"lags": [1, 24, 168], "target_column": "value"},
     "生成 1 步、24 步、168 步滞后特征"),
    (10, "sliding_window", "滑动窗口", 100, 500,
     {"window_size": 96, "step": 1, "target_column": "value"},
     "按 96 点窗口切片数据，生成模型输入样本"),
    (11, "train_test_split_ts", "数据切分", 300, 500,
     {"train_ratio": 0.8, "val_ratio": 0.1, "target_column": "value", "time_field": "record_time"},
     "按 80/10/10 比例切分训练集/验证集/测试集"),
    (12, "multi_step_forecast", "多步预测配置", 500, 500,
     {"forecast_steps": 96, "strategy": "recursive", "step_size": 1, "forecast_start_time": "00:15"},
     "配置预测 96 步（未来 24 小时），递归策略"),
    (13, "auto_tune_xgboost", "贝叶斯超参优化", 600, 650,
     {"n_trials": 30, "cv_folds": 5, "metric": "rmse"},
     "贝叶斯优化搜索 XGBoost 最优超参数（5折交叉验证，30轮搜索）"),
    (14, "xgboost_forecast", "XGBoost预测", 750, 500,
     {"n_estimators": 200, "auto_tune": False, "mode": "train",
      "separate_modeling": "true", "prefer_unit_len": 2, "default_retrain": True, "sample_weight_decay": 0.99, "task_type": "D"},
     "使用优化后的超参数训练 XGBoost 模型并预测"),
    (15, "smape_score", "SMAPE评估", 900, 500,
     {},
     "计算 SMAPE 对称百分比误差"),
    (16, "mse_rmse_mae", "MSE/RMSE/MAE", 900, 650,
     {},
     "计算 MSE、RMSE、MAE 三个误差指标"),
]

TRAINING_EDGE_DEFS = [
    (0, "load_csv", 0, "row_filter", 1),
    (1, "row_filter", 1, "resample_timeseries", 2),
    (2, "resample_timeseries", 2, "detect_outliers", 3),
    (3, "detect_outliers", 3, "handle_missing", 4),
    (4, "handle_missing", 4, "extract_time_features", 5),
    (5, "extract_time_features", 5, "holiday_features", 6),
    (6, "holiday_features", 6, "workday_features", 7),
    (7, "workday_features", 7, "rolling_statistics", 8),
    (8, "rolling_statistics", 8, "create_lag_features", 9),
    (9, "create_lag_features", 9, "sliding_window", 10),
    (10, "sliding_window", 10, "train_test_split_ts", 11),
    (11, "train_test_split_ts", 11, "multi_step_forecast", 12),
    (12, "multi_step_forecast", 12, "auto_tune_xgboost", 13),
    (13, "auto_tune_xgboost", 13, "xgboost_forecast", 14),
    (14, "xgboost_forecast", 14, "smape_score", 15),
    (15, "xgboost_forecast", 14, "mse_rmse_mae", 16),
]

WORKFLOWS = [
    {
        "id": "workflow-load-forecast-training-v2",
        "name": "负荷预测训练流水线（通用算子版）",
        "description": "基于16个通用算子的完整负荷预测训练流程",
        "node_defs": TRAINING_DEFS,
        "edge_defs": TRAINING_EDGE_DEFS,
    },
    {
        "id": "workflow-load-forecast-prediction-v2",
        "name": "负荷预测推理流水线（通用算子版）",
        "description": "使用已训练模型执行负荷预测推理",
        "node_defs": TRAINING_DEFS[:10] + [
            (10, "multi_step_forecast", "多步预测配置", 100, 500,
             {"forecast_steps": 96, "strategy": "recursive", "step_size": 1, "forecast_start_time": "00:15"},
             "配置预测 96 步，递归策略"),
            (11, "xgboost_forecast", "XGBoost预测", 400, 500,
             {"mode": "predict", "model_ref": "", "task_type": "D", "time_field": "record_time"},
             "加载已训练模型执行推理预测"),
        ],
        "edge_defs": TRAINING_EDGE_DEFS[:9] + [
            (9, "create_lag_features", 9, "multi_step_forecast", 10),
            (10, "multi_step_forecast", 10, "xgboost_forecast", 11),
        ],
    },
    {
        "id": "workflow-load-forecast-backtest-v2",
        "name": "负荷预测回测流水线（通用算子版）",
        "description": "按日期范围逐日执行训练+推理，评估模型回测表现",
        "node_defs": TRAINING_DEFS,
        "edge_defs": TRAINING_EDGE_DEFS,
    },
    {
        "id": "workflow-load-forecast-tuning-v1",
        "name": "负荷预测调优流水线（通用算子版）",
        "description": "用于参数调优候选验证的标准流水线",
        "node_defs": TRAINING_DEFS,
        "edge_defs": TRAINING_EDGE_DEFS,
    },
]


def create_workflows():
    now = datetime.now().isoformat()
    created_ids = []

    for wf_def in WORKFLOWS:
        nodes = [_make_node(*d) for d in wf_def["node_defs"]]
        edges = [_make_edge(*d) for d in wf_def["edge_defs"]]

        mode_by_id = {
            "workflow-load-forecast-training-v2": "train",
            "workflow-load-forecast-prediction-v2": "predict",
            "workflow-load-forecast-backtest-v2": "backtest",
            "workflow-load-forecast-tuning-v1": "tuning",
        }
        run_mode = mode_by_id.get(wf_def["id"], "train")
        global_config = {
            "time_zone": "Asia/Shanghai",
            "operate_status": run_mode,
            "nowtime": "",
            "run_mode": run_mode,
        }
        if run_mode == "backtest":
            global_config.update({
                "backtest_mode": "rolling_retrain",
                "backtest_model_ref": "",
            })
        elif run_mode == "tuning":
            global_config.update({
                "backtest_mode": "rolling_retrain",
                "backtest_start_date": "",
                "backtest_end_date": "",
                "tuning_objective": "avg_smape",
                "tuning_trials": 20,
                "tuning_orchestration": {
                    "enabled": True,
                    "strategy": "template_candidate_loop",
                    "rank_by": "candidate_score",
                },
                "tuning_candidates": [],
            })

        wf = {
            "id": wf_def["id"],
            "name": wf_def["name"],
            "description": wf_def["description"],
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "global_config": global_config,
                "template_type": "load_forecast",
            },
            "createdAt": now,
            "updatedAt": now,
        }

        path = os.path.join(WF_DIR, f"{wf_def['id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(wf, f, ensure_ascii=False, indent=2)
        print(f"  Created: {wf_def['name']} -> {path}")
        created_ids.append(wf_def["id"])

    return created_ids


def mount_to_scenario(workflow_ids):
    """Mount workflows to load_forecast scenario."""
    mounts = {}
    if os.path.exists(MOUNT_FILE):
        with open(MOUNT_FILE, "r", encoding="utf-8") as f:
            mounts = json.load(f)

    # The scenario key for 负荷预测 under 楼宇园区
    scenario_key = "load_forecast_industrial_load"
    if scenario_key not in mounts:
        mounts[scenario_key] = []

    now = datetime.now().isoformat()
    for wf_id in workflow_ids:
        # Skip if already mounted
        if any(m["id"] == wf_id for m in mounts[scenario_key]):
            print(f"  Already mounted: {wf_id}")
            continue

        # Load workflow info
        wf_path = os.path.join(WF_DIR, f"{wf_id}.json")
        with open(wf_path, "r", encoding="utf-8") as f:
            wf = json.load(f)

        mounts[scenario_key].append({
            "id": wf_id,
            "name": wf["name"],
            "node_count": len(wf["nodes"]),
            "edge_count": len(wf["edges"]),
            "mounted_at": now,
        })
        print(f"  Mounted: {wf['name']} -> {scenario_key}")

    with open(MOUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(mounts, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print("1. Creating enhanced workflow JSON files...")
    ids = create_workflows()
    print(f"\n2. Mounting to load_forecast scenario...")
    mount_to_scenario(ids)
    print("\nDone!")
# @AI_GENERATED: end
