# @AI_GENERATED: Kiro v1.0
"""
更新场景算法映射和领域约束文件
- 删除旧场景: general-manufacturing, industrial-data-analysis, industrial-llm, industrial-vision, equipment-health
- 新增场景: thermal-power, semiconductor, chemical-process, water-environment
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# 要删除的旧场景
OLD_SCENARIOS = [
    "general-manufacturing",
    "industrial-data-analysis", 
    "industrial-llm",
    "industrial-vision",
    "equipment-health"
]

# 新场景的算法映射
NEW_SCENARIO_MAPPINGS = {
    "thermal-power": {
        "high-accuracy": {
            "数据管理层": ["load_csv"],
            "数据处理层": ["handle_missing", "normalize_features", "extract_statistical_features"],
            "算法模型层": ["lstm_forecast", "xgboost_forecast", "arima_forecast"],
            "评估输出层": ["mape_metric", "rmse_metric", "r2_score"]
        },
        "balanced": {
            "数据管理层": ["load_csv"],
            "数据处理层": ["handle_missing", "normalize_features"],
            "算法模型层": ["xgboost_forecast"],
            "评估输出层": ["mape_metric", "rmse_metric"]
        }
    },
    "semiconductor": {
        "high-accuracy": {
            "数据管理层": ["load_csv"],
            "数据处理层": ["handle_missing", "normalize_features", "detect_outliers"],
            "算法模型层": ["xgboost_forecast", "random_forest_classifier", "svm_classifier"],
            "评估输出层": ["f1_score", "accuracy_score", "rmse_metric"]
        },
        "balanced": {
            "数据管理层": ["load_csv"],
            "数据处理层": ["handle_missing", "normalize_features"],
            "算法模型层": ["xgboost_forecast", "random_forest_classifier"],
            "评估输出层": ["f1_score", "accuracy_score"]
        }
    },
    "chemical-process": {
        "high-accuracy": {
            "数据管理层": ["load_csv"],
            "数据处理层": ["handle_missing", "normalize_features", "extract_statistical_features"],
            "算法模型层": ["lstm_forecast", "xgboost_forecast", "isolation_forest_anomaly"],
            "评估输出层": ["rmse_metric", "mape_metric", "f1_score"]
        },
        "balanced": {
            "数据管理层": ["load_csv"],
            "数据处理层": ["handle_missing", "normalize_features"],
            "算法模型层": ["xgboost_forecast"],
            "评估输出层": ["rmse_metric", "mape_metric"]
        }
    },
    "water-environment": {
        "high-accuracy": {
            "数据管理层": ["load_csv"],
            "数据处理层": ["handle_missing", "normalize_features", "detect_outliers"],
            "算法模型层": ["lstm_forecast", "xgboost_forecast", "arima_forecast"],
            "评估输出层": ["rmse_metric", "mape_metric", "r2_score"]
        },
        "balanced": {
            "数据管理层": ["load_csv"],
            "数据处理层": ["handle_missing", "normalize_features"],
            "算法模型层": ["arima_forecast"],
            "评估输出层": ["rmse_metric", "mape_metric"]
        }
    }
}

# 新场景的领域约束
NEW_DOMAIN_CONSTRAINTS = {
    "thermal-power": {
        "scenario_name": "火力发电",
        "parameter_constraints": {
            "coal_price_range": {"type": "range", "min": 300, "max": 1500, "unit": "CNY/t"},
            "generation_capacity": {"type": "range", "min": 100, "max": 1000, "unit": "MW"},
            "coal_inventory_days": {"type": "range", "min": 7, "max": 30, "unit": "days"},
            "efficiency_target": {"type": "threshold", "min": 38, "unit": "%"}
        },
        "evaluation_metrics": ["MAPE", "RMSE", "R2", "Cost_Saving"],
        "business_rules": [
            {"rule": "coal_forecast_requires_market_data", "severity": "warning"},
            {"rule": "inventory_optimization_requires_demand_forecast", "severity": "error"}
        ]
    },
    "semiconductor": {
        "scenario_name": "半导体制造",
        "parameter_constraints": {
            "yield_target": {"type": "threshold", "min": 90, "unit": "%"},
            "defect_density": {"type": "threshold", "max": 0.1, "unit": "defects/cm²"},
            "process_temperature": {"type": "range", "min": 20, "max": 1200, "unit": "°C"},
            "cleanroom_class": {"type": "enum", "values": ["ISO1", "ISO2", "ISO3", "ISO4", "ISO5"]}
        },
        "evaluation_metrics": ["Yield", "F1", "Accuracy", "Defect_Rate"],
        "business_rules": [
            {"rule": "yield_prediction_requires_process_data", "severity": "error"},
            {"rule": "defect_detection_requires_image_input", "severity": "warning"}
        ]
    },
    "chemical-process": {
        "scenario_name": "化工流程",
        "parameter_constraints": {
            "reaction_temperature": {"type": "range", "min": -50, "max": 500, "unit": "°C"},
            "pressure_range": {"type": "range", "min": 0.1, "max": 100, "unit": "MPa"},
            "conversion_rate": {"type": "threshold", "min": 85, "unit": "%"},
            "safety_margin": {"type": "threshold", "min": 10, "unit": "%"}
        },
        "evaluation_metrics": ["RMSE", "MAPE", "Conversion_Rate", "Safety_Score"],
        "business_rules": [
            {"rule": "safety_prediction_requires_sensor_data", "severity": "error"},
            {"rule": "process_optimization_requires_kinetic_model", "severity": "warning"}
        ]
    },
    "water-environment": {
        "scenario_name": "水务环保",
        "parameter_constraints": {
            "cod_limit": {"type": "threshold", "max": 50, "unit": "mg/L"},
            "bod_limit": {"type": "threshold", "max": 20, "unit": "mg/L"},
            "ph_range": {"type": "range", "min": 6, "max": 9, "unit": ""},
            "turbidity_limit": {"type": "threshold", "max": 1, "unit": "NTU"}
        },
        "evaluation_metrics": ["RMSE", "MAPE", "Compliance_Rate", "Energy_Efficiency"],
        "business_rules": [
            {"rule": "water_quality_prediction_requires_sensor_data", "severity": "error"},
            {"rule": "treatment_optimization_requires_flow_data", "severity": "warning"}
        ]
    }
}


def update_scenario_algorithm_mappings():
    """更新场景算法映射文件"""
    file_path = DATA_DIR / "scenario_algorithm_mappings.json"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 删除旧场景
    for scenario in OLD_SCENARIOS:
        if scenario in data:
            del data[scenario]
            print(f"  删除场景: {scenario}")
    
    # 添加新场景
    for scenario, mapping in NEW_SCENARIO_MAPPINGS.items():
        data[scenario] = mapping
        print(f"  新增场景: {scenario}")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 更新完成: {file_path}")
    return len(data) - 1  # 减去 _comment


def update_domain_constraints():
    """更新领域约束文件"""
    file_path = DATA_DIR / "domain_constraints.json"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 删除旧场景
    for scenario in OLD_SCENARIOS:
        if scenario in data:
            del data[scenario]
            print(f"  删除场景: {scenario}")
    
    # 添加新场景
    for scenario, constraints in NEW_DOMAIN_CONSTRAINTS.items():
        data[scenario] = constraints
        print(f"  新增场景: {scenario}")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 更新完成: {file_path}")
    return len(data) - 1  # 减去 _comment


def main():
    print("=" * 60)
    print("更新场景算法映射和领域约束")
    print("=" * 60)
    
    print("\n📝 更新 scenario_algorithm_mappings.json...")
    mapping_count = update_scenario_algorithm_mappings()
    
    print("\n📝 更新 domain_constraints.json...")
    constraint_count = update_domain_constraints()
    
    print("\n" + "=" * 60)
    print("更新完成!")
    print(f"  - 场景算法映射: {mapping_count} 个场景")
    print(f"  - 领域约束: {constraint_count} 个场景")
    print("=" * 60)


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
