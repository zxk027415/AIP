# @AI_GENERATED: Kiro v1.0
"""
从前端 scenarioTemplates.ts 数据生成 backend/data/industry_templates.json
每个场景算法方案生成默认竞争算法模板（由基础模块搭建）
"""
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "industry_templates.json")

# 场景算法方案 → 默认算法模板的基础模块映射规则
# 根据模板类型自动选择合适的基础模块组合
WORKFLOW_PRESETS = {
    "能源预测": {
        "high-accuracy": {
            "name": "深度学习方案",
            "layers": {
                "数据管理层": ["load_csv", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "resample_timeseries", "wavelet_denoise", "min_max_scale"],
                "算法模型层": ["lstm_forecast", "transformer_forecast"],
                "评估输出层": ["mape_metric", "rmse_metric", "forecast_plot"]
            }
        },
        "balanced": {
            "name": "机器学习方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "resample_timeseries", "z_score_scale"],
                "算法模型层": ["xgboost_forecast"],
                "评估输出层": ["mape_metric", "rmse_metric"]
            }
        },
        "low-latency": {
            "name": "统计模型方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["arima_forecast"],
                "评估输出层": ["mape_metric"]
            }
        }
    },
    "故障诊断": {
        "high-accuracy": {
            "name": "深度学习方案",
            "layers": {
                "数据管理层": ["load_csv", "load_opcua"],
                "数据处理层": ["handle_missing", "z_score_scale", "wavelet_denoise"],
                "算法模型层": ["cnn_classifier", "random_forest_classifier"],
                "评估输出层": ["f1_metric", "confusion_matrix"]
            }
        },
        "balanced": {
            "name": "机器学习方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "z_score_scale"],
                "算法模型层": ["random_forest_classifier"],
                "评估输出层": ["f1_metric", "accuracy_metric"]
            }
        }
    },
    "异常检测": {
        "high-accuracy": {
            "name": "深度学习方案",
            "layers": {
                "数据管理层": ["load_csv", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "z_score_scale", "wavelet_denoise"],
                "算法模型层": ["isolation_forest", "autoencoder_anomaly"],
                "评估输出层": ["f1_metric", "precision_metric", "anomaly_plot"]
            }
        },
        "balanced": {
            "name": "统计方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "z_score_scale"],
                "算法模型层": ["isolation_forest"],
                "评估输出层": ["f1_metric"]
            }
        }
    },
    "工业聚类": {
        "high-accuracy": {
            "name": "深度聚类方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "z_score_scale", "pca_reduction"],
                "算法模型层": ["kmeans_cluster", "dbscan_cluster"],
                "评估输出层": ["silhouette_metric", "scatter_plot"]
            }
        },
        "balanced": {
            "name": "经典聚类方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "min_max_scale"],
                "算法模型层": ["kmeans_cluster"],
                "评估输出层": ["silhouette_metric"]
            }
        }
    },
    "电力信号分析": {
        "high-accuracy": {
            "name": "多方法融合方案",
            "layers": {
                "数据管理层": ["load_csv", "load_iec61850"],
                "数据处理层": ["handle_missing", "bandpass_filter", "fft_transform"],
                "算法模型层": ["wavelet_analysis", "lstm_forecast"],
                "评估输出层": ["rmse_metric", "spectrogram_plot"]
            }
        },
        "balanced": {
            "name": "经典信号处理方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "bandpass_filter"],
                "算法模型层": ["fft_analysis"],
                "评估输出层": ["spectrogram_plot"]
            }
        }
    },
    "工业过程优化": {
        "high-accuracy": {
            "name": "智能优化方案",
            "layers": {
                "数据管理层": ["load_csv", "load_database"],
                "数据处理层": ["handle_missing", "z_score_scale", "feature_select"],
                "算法模型层": ["genetic_algorithm", "xgboost_forecast"],
                "评估输出层": ["rmse_metric", "optimization_report"]
            }
        },
        "balanced": {
            "name": "经典优化方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "min_max_scale"],
                "算法模型层": ["linear_programming"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
    "工业视觉": {
        "high-accuracy": {
            "name": "深度视觉方案",
            "layers": {
                "数据管理层": ["load_image", "load_video"],
                "数据处理层": ["image_resize", "image_augment", "image_normalize"],
                "算法模型层": ["yolo_detector", "resnet_classifier"],
                "评估输出层": ["map_metric", "f1_metric"]
            }
        },
        "balanced": {
            "name": "轻量视觉方案",
            "layers": {
                "数据管理层": ["load_image"],
                "数据处理层": ["image_resize", "image_normalize"],
                "算法模型层": ["cnn_classifier"],
                "评估输出层": ["accuracy_metric"]
            }
        }
    },
    "调度优化": {
        "high-accuracy": {
            "name": "智能调度方案",
            "layers": {
                "数据管理层": ["load_csv", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "z_score_scale"],
                "算法模型层": ["genetic_algorithm", "lstm_forecast"],
                "评估输出层": ["rmse_metric", "optimization_report"]
            }
        },
        "balanced": {
            "name": "规则调度方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["linear_programming"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
    "能源调度优化": {
        "high-accuracy": {
            "name": "智能调度方案",
            "layers": {
                "数据管理层": ["load_csv", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "z_score_scale"],
                "算法模型层": ["genetic_algorithm", "lstm_forecast"],
                "评估输出层": ["rmse_metric", "optimization_report"]
            }
        },
        "balanced": {
            "name": "经典调度方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["linear_programming"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
    "负荷与需求侧管理": {
        "high-accuracy": {
            "name": "深度学习方案",
            "layers": {
                "数据管理层": ["load_csv", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "resample_timeseries", "min_max_scale"],
                "算法模型层": ["lstm_forecast", "xgboost_forecast"],
                "评估输出层": ["mape_metric", "rmse_metric"]
            }
        },
        "balanced": {
            "name": "统计方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["arima_forecast"],
                "评估输出层": ["mape_metric"]
            }
        }
    },
    "碳管理与综合能源": {
        "high-accuracy": {
            "name": "综合分析方案",
            "layers": {
                "数据管理层": ["load_csv", "load_database"],
                "数据处理层": ["handle_missing", "z_score_scale"],
                "算法模型层": ["xgboost_forecast", "linear_regression"],
                "评估输出层": ["rmse_metric", "r2_metric"]
            }
        },
        "balanced": {
            "name": "统计方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["linear_regression"],
                "评估输出层": ["r2_metric"]
            }
        }
    },
    "LLM与工业智能": {
        "high-accuracy": {
            "name": "RAG增强方案",
            "layers": {
                "数据管理层": ["load_csv", "load_database"],
                "数据处理层": ["text_clean", "tokenize"],
                "算法模型层": ["tfidf_classifier", "embedding_model"],
                "评估输出层": ["accuracy_metric", "f1_metric"]
            }
        },
        "balanced": {
            "name": "关键词方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["text_clean"],
                "算法模型层": ["keyword_extractor"],
                "评估输出层": ["accuracy_metric"]
            }
        }
    },
    "时序与信号可视化": {
        "high-accuracy": {
            "name": "多维可视化方案",
            "layers": {
                "数据管理层": ["load_csv", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "resample_timeseries"],
                "算法模型层": ["moving_average", "fft_analysis"],
                "评估输出层": ["timeseries_plot", "spectrogram_plot"]
            }
        },
        "balanced": {
            "name": "基础可视化方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["moving_average"],
                "评估输出层": ["timeseries_plot"]
            }
        }
    },
    "工业专用可视化": {
        "high-accuracy": {
            "name": "多维可视化方案",
            "layers": {
                "数据管理层": ["load_csv", "load_database"],
                "数据处理层": ["handle_missing", "data_aggregate"],
                "算法模型层": ["moving_average"],
                "评估输出层": ["dashboard_render", "heatmap_render"]
            }
        },
        "balanced": {
            "name": "基础可视化方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["moving_average"],
                "评估输出层": ["dashboard_render"]
            }
        }
    },
    "交互与报告": {
        "high-accuracy": {
            "name": "交互式报告方案",
            "layers": {
                "数据管理层": ["load_csv", "load_database"],
                "数据处理层": ["handle_missing", "data_aggregate"],
                "算法模型层": ["moving_average"],
                "评估输出层": ["interactive_dashboard", "report_export"]
            }
        },
        "balanced": {
            "name": "静态报告方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["moving_average"],
                "评估输出层": ["report_export"]
            }
        }
    },
    "图像分类与检测": {
        "high-accuracy": {
            "name": "深度视觉方案",
            "layers": {
                "数据管理层": ["load_image", "load_video"],
                "数据处理层": ["image_resize", "image_augment", "image_normalize"],
                "算法模型层": ["yolo_detector", "resnet_classifier"],
                "评估输出层": ["map_metric", "f1_metric"]
            }
        },
        "balanced": {
            "name": "轻量视觉方案",
            "layers": {
                "数据管理层": ["load_image"],
                "数据处理层": ["image_resize", "image_normalize"],
                "算法模型层": ["cnn_classifier"],
                "评估输出层": ["accuracy_metric"]
            }
        }
    },
    "语义分割": {
        "high-accuracy": {
            "name": "深度分割方案",
            "layers": {
                "数据管理层": ["load_image"],
                "数据处理层": ["image_resize", "image_augment", "image_normalize"],
                "算法模型层": ["unet_segmentation", "deeplabv3_segmentation"],
                "评估输出层": ["iou_metric", "dice_metric"]
            }
        },
        "balanced": {
            "name": "轻量分割方案",
            "layers": {
                "数据管理层": ["load_image"],
                "数据处理层": ["image_resize", "image_normalize"],
                "算法模型层": ["unet_segmentation"],
                "评估输出层": ["iou_metric"]
            }
        }
    },
    "工业缺陷检测": {
        "high-accuracy": {
            "name": "深度检测方案",
            "layers": {
                "数据管理层": ["load_image", "load_video"],
                "数据处理层": ["image_resize", "image_augment", "image_normalize"],
                "算法模型层": ["yolo_detector", "anomaly_detection_vision"],
                "评估输出层": ["map_metric", "f1_metric"]
            }
        },
        "balanced": {
            "name": "经典检测方案",
            "layers": {
                "数据管理层": ["load_image"],
                "数据处理层": ["image_resize", "image_normalize"],
                "算法模型层": ["cnn_classifier"],
                "评估输出层": ["accuracy_metric", "f1_metric"]
            }
        }
    },
    "设备健康管理专用": {
        "high-accuracy": {
            "name": "综合诊断方案",
            "layers": {
                "数据管理层": ["load_csv", "load_opcua", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "fft_transform", "wavelet_denoise", "z_score_scale"],
                "算法模型层": ["lstm_forecast", "isolation_forest", "random_forest_classifier"],
                "评估输出层": ["f1_metric", "rmse_metric", "anomaly_plot"]
            }
        },
        "balanced": {
            "name": "统计诊断方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "z_score_scale"],
                "算法模型层": ["random_forest_classifier"],
                "评估输出层": ["f1_metric"]
            }
        }
    },
}

# 场景专用分类的特殊算法模板覆盖
SCENARIO_SPECIFIC_PRESETS = {
    "港口与运输专用": {
        "high-accuracy": {
            "name": "智能调度方案",
            "layers": {
                "数据管理层": ["load_csv", "load_database", "load_mqtt"],
                "数据处理层": ["handle_missing", "z_score_scale", "feature_select"],
                "算法模型层": ["genetic_algorithm", "lstm_forecast", "a_star_pathfinding"],
                "评估输出层": ["rmse_metric", "optimization_report"]
            }
        },
        "balanced": {
            "name": "规则优化方案",
            "layers": {
                "数据管理层": ["load_csv", "load_database"],
                "数据处理层": ["handle_missing", "min_max_scale"],
                "算法模型层": ["linear_programming"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
    "钢铁行业专用": {
        "high-accuracy": {
            "name": "多模型融合方案",
            "layers": {
                "数据管理层": ["load_csv", "load_opcua", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "z_score_scale", "pca_reduction"],
                "算法模型层": ["xgboost_forecast", "random_forest_classifier", "cnn_classifier"],
                "评估输出层": ["rmse_metric", "f1_metric"]
            }
        },
        "balanced": {
            "name": "机器学习方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "z_score_scale"],
                "算法模型层": ["xgboost_forecast"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
    "光伏制造专用": {
        "high-accuracy": {
            "name": "视觉+数据融合方案",
            "layers": {
                "数据管理层": ["load_csv", "load_image", "load_opcua"],
                "数据处理层": ["handle_missing", "image_resize", "image_normalize", "z_score_scale"],
                "算法模型层": ["cnn_classifier", "xgboost_forecast"],
                "评估输出层": ["f1_metric", "accuracy_metric"]
            }
        },
        "balanced": {
            "name": "机器学习方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "z_score_scale"],
                "算法模型层": ["random_forest_classifier"],
                "评估输出层": ["accuracy_metric"]
            }
        }
    },
    "动力电池制造专用": {
        "high-accuracy": {
            "name": "多模型融合方案",
            "layers": {
                "数据管理层": ["load_csv", "load_timeseries_db", "load_canbus"],
                "数据处理层": ["handle_missing", "kalman_filter", "z_score_scale"],
                "算法模型层": ["lstm_forecast", "isolation_forest"],
                "评估输出层": ["rmse_metric", "f1_metric"]
            }
        },
        "balanced": {
            "name": "机器学习方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "z_score_scale"],
                "算法模型层": ["xgboost_forecast"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
    "楼宇园区专用": {
        "high-accuracy": {
            "name": "智能控制方案",
            "layers": {
                "数据管理层": ["load_csv", "load_bacnet", "load_mqtt"],
                "数据处理层": ["handle_missing", "resample_timeseries", "z_score_scale"],
                "算法模型层": ["lstm_forecast", "pid_controller", "genetic_algorithm"],
                "评估输出层": ["rmse_metric", "energy_report"]
            }
        },
        "balanced": {
            "name": "规则控制方案",
            "layers": {
                "数据管理层": ["load_csv", "load_bacnet"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["pid_controller"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
    "储能管理": {
        "high-accuracy": {
            "name": "多模型融合方案",
            "layers": {
                "数据管理层": ["load_csv", "load_canbus", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "kalman_filter", "z_score_scale"],
                "算法模型层": ["lstm_forecast", "ekf_estimator"],
                "评估输出层": ["rmse_metric", "mae_metric"]
            }
        },
        "balanced": {
            "name": "经典估计方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "kalman_filter"],
                "算法模型层": ["ekf_estimator"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
    "发电侧管理": {
        "high-accuracy": {
            "name": "综合监控方案",
            "layers": {
                "数据管理层": ["load_csv", "load_mqtt", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "resample_timeseries", "z_score_scale"],
                "算法模型层": ["lstm_forecast", "xgboost_forecast"],
                "评估输出层": ["mape_metric", "dashboard_render"]
            }
        },
        "balanced": {
            "name": "统计监控方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing", "resample_timeseries"],
                "算法模型层": ["arima_forecast"],
                "评估输出层": ["mape_metric"]
            }
        }
    },
    "电网与微网管理": {
        "high-accuracy": {
            "name": "智能分析方案",
            "layers": {
                "数据管理层": ["load_csv", "load_iec61850", "load_timeseries_db"],
                "数据处理层": ["handle_missing", "bandpass_filter", "z_score_scale"],
                "算法模型层": ["power_flow_solver", "genetic_algorithm"],
                "评估输出层": ["rmse_metric", "single_line_diagram"]
            }
        },
        "balanced": {
            "name": "经典计算方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["power_flow_solver"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
    "通用工业专用": {
        "high-accuracy": {
            "name": "综合管理方案",
            "layers": {
                "数据管理层": ["load_csv", "load_database", "load_opcua"],
                "数据处理层": ["handle_missing", "z_score_scale", "feature_select"],
                "算法模型层": ["xgboost_forecast", "spc_analyzer"],
                "评估输出层": ["rmse_metric", "dashboard_render"]
            }
        },
        "balanced": {
            "name": "基础管理方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["spc_analyzer"],
                "评估输出层": ["dashboard_render"]
            }
        }
    },
    "工艺优化": {
        "high-accuracy": {
            "name": "智能优化方案",
            "layers": {
                "数据管理层": ["load_csv", "load_opcua"],
                "数据处理层": ["handle_missing", "z_score_scale", "feature_select"],
                "算法模型层": ["genetic_algorithm", "xgboost_forecast"],
                "评估输出层": ["rmse_metric", "optimization_report"]
            }
        },
        "balanced": {
            "name": "经典优化方案",
            "layers": {
                "数据管理层": ["load_csv"],
                "数据处理层": ["handle_missing"],
                "算法模型层": ["linear_programming"],
                "评估输出层": ["rmse_metric"]
            }
        }
    },
}


# 合并：场景专用覆盖通用
def _get_preset(category):
    if category in SCENARIO_SPECIFIC_PRESETS:
        return SCENARIO_SPECIFIC_PRESETS[category]
    if category in WORKFLOW_PRESETS:
        return WORKFLOW_PRESETS[category]
    return WORKFLOW_PRESETS.get("工业过程优化", {})


# 从 scenarioTemplates.ts 提取的完整模板数据
SCENARIO_TEMPLATES_RAW = {
    "renewable-energy": [
        {"category": "能源预测", "functions": [
            {"id": "pv_power_forecast", "name": "光伏发电功率预测", "desc": "基于气象数据和历史发电数据预测光伏电站输出功率"},
            {"id": "wind_power_forecast", "name": "风电功率预测", "desc": "基于风速风向等气象数据预测风电场输出功率"},
            {"id": "load_demand_forecast", "name": "电力负荷预测", "desc": "预测区域电力负荷需求"},
            {"id": "electricity_price_forecast", "name": "电价预测", "desc": "预测电力市场现货/期货价格"},
        ]},
        {"category": "故障诊断", "functions": [
            {"id": "inverter_fault_classifier", "name": "逆变器故障诊断", "desc": "基于运行数据诊断逆变器故障类型"},
            {"id": "pv_module_fault_classifier", "name": "光伏组件故障分类", "desc": "光伏组件故障类型识别"},
            {"id": "wind_turbine_fault_classifier", "name": "风机故障诊断", "desc": "风力发电机组故障诊断"},
            {"id": "transformer_fault_classifier", "name": "变压器故障诊断", "desc": "变压器故障类型诊断"},
        ]},
        {"category": "工业聚类", "functions": [
            {"id": "generation_pattern_cluster", "name": "发电模式聚类", "desc": "发电模式聚类分析"},
            {"id": "weather_pattern_cluster", "name": "气象模式聚类", "desc": "气象模式聚类分析"},
        ]},
        {"category": "电力信号分析", "functions": [
            {"id": "islanding_detect", "name": "孤岛检测", "desc": "分布式电源孤岛检测"},
            {"id": "power_quality_analyze", "name": "电能质量分析", "desc": "电能质量综合分析"},
        ]},
        {"category": "发电侧管理", "functions": [
            {"id": "pv_plant_monitor", "name": "光伏电站监控", "desc": "光伏电站运行状态监控"},
            {"id": "wind_farm_monitor", "name": "风电场监控", "desc": "风电场运行状态监控"},
            {"id": "generation_schedule", "name": "发电计划编制", "desc": "发电计划编制与优化"},
            {"id": "curtailment_analyze", "name": "弃风弃光分析", "desc": "弃风弃光原因分析"},
            {"id": "resource_assessment", "name": "资源评估", "desc": "风光资源评估"},
            {"id": "capacity_factor", "name": "容量因子计算", "desc": "发电容量因子计算"},
            {"id": "wake_effect_model", "name": "尾流效应模型", "desc": "风机尾流效应建模"},
            {"id": "soiling_loss_estimate", "name": "灰尘损失估计", "desc": "光伏灰尘损失估计"},
            {"id": "inverter_clipping", "name": "逆变器限幅分析", "desc": "逆变器限幅损失分析"},
            {"id": "string_mismatch", "name": "组串失配分析", "desc": "光伏组串失配分析"},
            {"id": "performance_ratio", "name": "性能比计算", "desc": "光伏电站性能比计算"},
            {"id": "degradation_rate", "name": "衰减率分析", "desc": "光伏组件衰减率分析"},
        ]},
    ],
    "energy-storage": [
        {"category": "能源预测", "functions": [
            {"id": "battery_soc_forecast", "name": "储能SOC预测", "desc": "储能系统SOC状态预测"},
            {"id": "load_demand_forecast", "name": "电力负荷预测", "desc": "预测区域电力负荷需求"},
        ]},
        {"category": "异常检测", "functions": [
            {"id": "battery_anomaly_detect", "name": "电池异常检测", "desc": "电池运行异常检测"},
            {"id": "thermal_anomaly_detect", "name": "热异常检测", "desc": "设备热异常检测"},
        ]},
        {"category": "故障诊断", "functions": [
            {"id": "battery_fault_classifier", "name": "电池故障分类", "desc": "电池故障类型分类"},
            {"id": "fault_severity_classifier", "name": "故障严重度分级", "desc": "故障严重程度分级"},
        ]},
        {"category": "调度优化", "functions": [
            {"id": "battery_schedule", "name": "储能调度优化", "desc": "储能系统充放电调度优化"},
            {"id": "ev_charging_schedule", "name": "电动车充电调度", "desc": "电动车充电策略优化"},
        ]},
        {"category": "储能管理", "functions": [
            {"id": "soc_estimate", "name": "SOC估计", "desc": "电池荷电状态估计"},
            {"id": "soh_estimate", "name": "SOH估计", "desc": "电池健康状态估计"},
            {"id": "rul_battery", "name": "电池寿命预测", "desc": "电池剩余使用寿命预测"},
            {"id": "thermal_management", "name": "热管理优化", "desc": "电池热管理策略优化"},
            {"id": "cell_balancing", "name": "电芯均衡策略", "desc": "电芯均衡充放电策略"},
            {"id": "charge_strategy", "name": "充电策略优化", "desc": "充电策略优化"},
            {"id": "capacity_fade_model", "name": "容量衰减模型", "desc": "电池容量衰减建模"},
            {"id": "impedance_estimate", "name": "阻抗估计", "desc": "电池内阻估计"},
            {"id": "safety_warning", "name": "安全预警", "desc": "电池安全预警"},
            {"id": "energy_throughput", "name": "能量吞吐统计", "desc": "储能系统能量吞吐统计"},
        ]},
    ],
    "power-grid": [
        {"category": "电力信号分析", "functions": [
            {"id": "power_quality_analyze", "name": "电能质量分析", "desc": "电能质量综合分析"},
            {"id": "flicker_analyze", "name": "闪变分析", "desc": "电压闪变分析"},
            {"id": "sag_swell_detect", "name": "暂降暂升检测", "desc": "电压暂降暂升检测"},
            {"id": "transient_analyze", "name": "暂态分析", "desc": "电力暂态过程分析"},
            {"id": "frequency_deviation", "name": "频率偏差分析", "desc": "电网频率偏差分析"},
            {"id": "phase_angle_analyze", "name": "相角分析", "desc": "电力相角分析"},
            {"id": "symmetrical_component", "name": "对称分量分析", "desc": "三相对称分量分析"},
            {"id": "impedance_analyze", "name": "阻抗分析", "desc": "电力系统阻抗分析"},
            {"id": "partial_discharge_analyze", "name": "局部放电分析", "desc": "局部放电检测分析"},
            {"id": "traveling_wave_analyze", "name": "行波分析", "desc": "行波故障定位分析"},
            {"id": "pmu_data_analyze", "name": "PMU数据分析", "desc": "相量测量单元数据分析"},
            {"id": "power_oscillation_detect", "name": "功率振荡检测", "desc": "电力系统功率振荡检测"},
            {"id": "islanding_detect", "name": "孤岛检测", "desc": "分布式电源孤岛检测"},
        ]},
        {"category": "能源调度优化", "functions": [
            {"id": "unit_commitment", "name": "机组组合优化", "desc": "发电机组启停组合优化"},
            {"id": "economic_dispatch", "name": "经济调度", "desc": "发电经济调度优化"},
            {"id": "optimal_power_flow", "name": "最优潮流", "desc": "最优潮流计算"},
            {"id": "microgrid_dispatch", "name": "微网调度优化", "desc": "微电网调度优化"},
            {"id": "vpp_dispatch", "name": "虚拟电厂调度", "desc": "虚拟电厂聚合调度"},
        ]},
        {"category": "电网与微网管理", "functions": [
            {"id": "power_flow_calc", "name": "潮流计算", "desc": "电力系统潮流计算"},
            {"id": "short_circuit_calc", "name": "短路计算", "desc": "短路电流计算"},
            {"id": "voltage_stability", "name": "电压稳定分析", "desc": "电压稳定性分析"},
            {"id": "frequency_regulation", "name": "频率调节", "desc": "电网频率调节"},
            {"id": "reactive_power_optimize", "name": "无功优化", "desc": "无功功率优化"},
            {"id": "network_reconfiguration", "name": "网络重构", "desc": "配电网络重构"},
            {"id": "fault_location", "name": "故障定位", "desc": "电网故障定位"},
            {"id": "protection_coordination", "name": "保护协调", "desc": "继电保护协调"},
            {"id": "dg_integration", "name": "分布式电源接入", "desc": "分布式电源并网分析"},
            {"id": "grid_resilience", "name": "电网韧性评估", "desc": "电网韧性评估"},
            {"id": "loss_reduction", "name": "线损分析", "desc": "线路损耗分析"},
            {"id": "contingency_analysis", "name": "预想事故分析", "desc": "N-1/N-2预想事故分析"},
        ]},
        {"category": "异常检测", "functions": [
            {"id": "power_quality_anomaly", "name": "电能质量异常检测", "desc": "电能质量异常检测"},
            {"id": "grid_anomaly_detect", "name": "电网异常检测", "desc": "电网运行异常检测"},
        ]},
    ],
    "steel-manufacturing": [
        {"category": "工业过程优化", "functions": [
            {"id": "process_parameter_optimize", "name": "工艺参数优化", "desc": "工艺参数多目标优化"},
            {"id": "production_schedule", "name": "生产排程优化", "desc": "生产排程优化"},
            {"id": "cutting_stock_optimize", "name": "下料优化", "desc": "钢材下料方案优化"},
            {"id": "blend_optimize", "name": "配料优化", "desc": "原料配比优化"},
            {"id": "job_shop_schedule", "name": "作业车间调度", "desc": "车间作业调度优化"},
        ]},
        {"category": "钢铁行业专用", "functions": [
            {"id": "steel_quality_predict", "name": "钢材质量预测", "desc": "钢材质量预测"},
            {"id": "steel_defect_classify", "name": "钢材缺陷分类", "desc": "钢材缺陷类型分类"},
            {"id": "rolling_force_predict", "name": "轧制力预测", "desc": "轧制力预测"},
            {"id": "temperature_model", "name": "温度场模型", "desc": "温度场建模"},
            {"id": "composition_optimize", "name": "成分优化", "desc": "钢材成分优化"},
            {"id": "energy_balance", "name": "能量平衡计算", "desc": "能量平衡计算"},
            {"id": "yield_optimize", "name": "成材率优化", "desc": "成材率优化"},
            {"id": "furnace_optimize", "name": "加热炉优化", "desc": "加热炉优化控制"},
            {"id": "cooling_control", "name": "冷却控制", "desc": "冷却过程控制"},
            {"id": "surface_inspect", "name": "表面检测", "desc": "钢材表面质量检测"},
        ]},
        {"category": "故障诊断", "functions": [
            {"id": "steel_grade_classifier", "name": "钢材牌号分类", "desc": "钢材牌号自动分类"},
            {"id": "product_quality_classifier", "name": "产品质量分级", "desc": "产品质量等级分类"},
            {"id": "bearing_fault_classifier", "name": "轴承故障诊断", "desc": "轴承故障诊断"},
        ]},
        {"category": "工业视觉", "functions": [
            {"id": "steel_surface_defect", "name": "钢材表面缺陷检测", "desc": "钢材表面缺陷视觉检测"},
            {"id": "hot_rolled_defect", "name": "热轧缺陷检测", "desc": "热轧产品缺陷检测"},
        ]},
    ],
    "pv-manufacturing": [
        {"category": "光伏制造专用", "functions": [
            {"id": "cell_efficiency_predict", "name": "电池片效率预测", "desc": "光伏电池片转换效率预测"},
            {"id": "wafer_defect_detect", "name": "硅片缺陷检测", "desc": "硅片缺陷检测"},
            {"id": "el_image_analyze", "name": "EL图像分析", "desc": "电致发光图像分析"},
            {"id": "color_sorting", "name": "色选分级", "desc": "电池片色选分级"},
            {"id": "string_welding_inspect", "name": "串焊检测", "desc": "串焊质量检测"},
            {"id": "lamination_quality", "name": "层压质量检测", "desc": "层压质量检测"},
            {"id": "iv_curve_analyze", "name": "IV曲线分析", "desc": "IV特性曲线分析"},
            {"id": "module_power_predict", "name": "组件功率预测", "desc": "光伏组件功率预测"},
        ]},
        {"category": "工业视觉", "functions": [
            {"id": "pv_cell_defect", "name": "光伏电池缺陷检测", "desc": "光伏电池缺陷视觉检测"},
            {"id": "micro_crack_detect", "name": "隐裂检测", "desc": "光伏电池隐裂检测"},
            {"id": "hotspot_detect", "name": "热斑检测", "desc": "光伏组件热斑检测"},
        ]},
        {"category": "故障诊断", "functions": [
            {"id": "pv_module_fault_classifier", "name": "光伏组件故障分类", "desc": "光伏组件故障分类"},
            {"id": "inverter_fault_classifier", "name": "逆变器故障诊断", "desc": "逆变器故障诊断"},
            {"id": "degradation_stage_classifier", "name": "退化阶段分类", "desc": "设备退化阶段分类"},
        ]},
        {"category": "工艺优化", "functions": [
            {"id": "process_parameter_optimize", "name": "工艺参数优化", "desc": "工艺参数优化"},
            {"id": "energy_efficiency_optimize", "name": "能效优化", "desc": "能效优化"},
        ]},
    ],
    "battery-manufacturing": [
        {"category": "动力电池制造专用", "functions": [
            {"id": "cell_consistency", "name": "电芯一致性分析", "desc": "电芯一致性分析"},
            {"id": "formation_optimize", "name": "化成工艺优化", "desc": "化成工艺优化"},
            {"id": "electrode_quality", "name": "极片质量检测", "desc": "极片质量检测"},
            {"id": "electrolyte_optimize", "name": "电解液配方优化", "desc": "电解液配方优化"},
            {"id": "capacity_grading", "name": "容量分选", "desc": "电池容量分选"},
            {"id": "self_discharge_test", "name": "自放电测试", "desc": "电池自放电测试"},
            {"id": "nail_penetration_sim", "name": "针刺仿真", "desc": "电池针刺安全仿真"},
            {"id": "cycle_life_predict", "name": "循环寿命预测", "desc": "电池循环寿命预测"},
        ]},
        {"category": "故障诊断", "functions": [
            {"id": "battery_fault_classifier", "name": "电池故障分类", "desc": "电池故障分类"},
            {"id": "fault_severity_classifier", "name": "故障严重度分级", "desc": "故障严重度分级"},
            {"id": "thermal_fault_classifier", "name": "热故障分类", "desc": "热故障分类"},
            {"id": "degradation_stage_classifier", "name": "退化阶段分类", "desc": "退化阶段分类"},
        ]},
        {"category": "异常检测", "functions": [
            {"id": "battery_anomaly_detect", "name": "电池异常检测", "desc": "电池异常检测"},
            {"id": "thermal_anomaly_detect", "name": "热异常检测", "desc": "热异常检测"},
            {"id": "process_anomaly", "name": "工艺过程异常", "desc": "工艺过程异常检测"},
        ]},
        {"category": "工艺优化", "functions": [
            {"id": "blend_optimize", "name": "配料优化", "desc": "配料优化"},
            {"id": "process_parameter_optimize", "name": "工艺参数优化", "desc": "工艺参数优化"},
            {"id": "energy_efficiency_optimize", "name": "能效优化", "desc": "能效优化"},
        ]},
    ],
    "general-manufacturing": [
        {"category": "工业过程优化", "functions": [
            {"id": "process_parameter_optimize", "name": "工艺参数优化", "desc": "工艺参数优化"},
            {"id": "production_schedule", "name": "生产排程优化", "desc": "生产排程优化"},
            {"id": "maintenance_schedule", "name": "检修计划优化", "desc": "检修计划优化"},
            {"id": "inventory_optimize", "name": "库存优化", "desc": "库存优化"},
            {"id": "job_shop_schedule", "name": "作业车间调度", "desc": "作业车间调度"},
            {"id": "energy_efficiency_optimize", "name": "能效优化", "desc": "能效优化"},
            {"id": "pid_tune", "name": "PID参数整定", "desc": "PID参数整定"},
            {"id": "mpc_control", "name": "模型预测控制", "desc": "模型预测控制"},
            {"id": "setpoint_optimize", "name": "设定值优化", "desc": "设定值优化"},
        ]},
        {"category": "故障诊断", "functions": [
            {"id": "bearing_fault_classifier", "name": "轴承故障诊断", "desc": "轴承故障诊断"},
            {"id": "motor_fault_classifier", "name": "电机故障诊断", "desc": "电机故障诊断"},
            {"id": "pump_fault_classifier", "name": "泵故障诊断", "desc": "泵故障诊断"},
            {"id": "compressor_fault_classifier", "name": "压缩机故障诊断", "desc": "压缩机故障诊断"},
            {"id": "conveyor_fault_classifier", "name": "输送带故障诊断", "desc": "输送带故障诊断"},
            {"id": "product_quality_classifier", "name": "产品质量分级", "desc": "产品质量分级"},
        ]},
        {"category": "异常检测", "functions": [
            {"id": "process_anomaly", "name": "工艺过程异常", "desc": "工艺过程异常检测"},
            {"id": "vibration_anomaly", "name": "振动异常检测", "desc": "振动异常检测"},
            {"id": "leakage_detect", "name": "泄漏检测", "desc": "泄漏检测"},
            {"id": "corrosion_detect", "name": "腐蚀检测", "desc": "腐蚀检测"},
        ]},
        {"category": "通用工业专用", "functions": [
            {"id": "oee_calculate", "name": "OEE计算", "desc": "设备综合效率计算"},
            {"id": "spc_control", "name": "SPC统计过程控制", "desc": "统计过程控制"},
            {"id": "tpm_management", "name": "TPM管理", "desc": "全面生产维护管理"},
        ]},
    ],
    "port-logistics": [
        {"category": "港口与运输专用", "functions": [
            {"id": "berth_allocation", "name": "泊位分配优化", "desc": "港口泊位分配优化"},
            {"id": "agv_path_plan", "name": "AGV路径规划", "desc": "自动导引车路径规划"},
            {"id": "crane_schedule", "name": "岸桥调度", "desc": "岸桥作业调度优化"},
            {"id": "yard_management", "name": "堆场管理", "desc": "集装箱堆场管理优化"},
            {"id": "vessel_schedule", "name": "船舶调度", "desc": "船舶进出港调度"},
            {"id": "container_tracking", "name": "集装箱追踪", "desc": "集装箱全程追踪"},
            {"id": "throughput_forecast", "name": "吞吐量预测", "desc": "港口吞吐量预测"},
            {"id": "port_energy_manage", "name": "港口能耗管理", "desc": "港口能耗管理优化"},
        ]},
        {"category": "工业过程优化", "functions": [
            {"id": "logistics_route_optimize", "name": "物流路径优化", "desc": "物流路径优化"},
            {"id": "bin_packing_optimize", "name": "装箱优化", "desc": "集装箱装箱优化"},
            {"id": "production_schedule", "name": "生产排程优化", "desc": "生产排程优化"},
            {"id": "maintenance_schedule", "name": "检修计划优化", "desc": "检修计划优化"},
            {"id": "inventory_optimize", "name": "库存优化", "desc": "库存优化"},
            {"id": "energy_efficiency_optimize", "name": "能效优化", "desc": "能效优化"},
            {"id": "pid_tune", "name": "PID参数整定", "desc": "PID参数整定"},
        ]},
    ],
    "building-campus": [
        {"category": "楼宇园区专用", "functions": [
            {"id": "hvac_control", "name": "暖通空调控制", "desc": "暖通空调控制"},
            {"id": "lighting_optimize", "name": "照明优化", "desc": "照明优化"},
            {"id": "energy_audit", "name": "能源审计", "desc": "能源审计"},
            {"id": "comfort_index", "name": "舒适度指数", "desc": "舒适度指数计算"},
            {"id": "occupancy_detect", "name": "人员检测", "desc": "人员检测"},
            {"id": "elevator_optimize", "name": "电梯调度优化", "desc": "电梯调度优化"},
            {"id": "water_management", "name": "水务管理", "desc": "水务管理"},
            {"id": "fire_detection", "name": "消防检测", "desc": "消防检测"},
        ]},
        {"category": "工业过程优化", "functions": [
            {"id": "hvac_optimize", "name": "暖通空调优化", "desc": "暖通空调优化"},
            {"id": "energy_efficiency_optimize", "name": "能效优化", "desc": "能效优化"},
            {"id": "setpoint_optimize", "name": "设定值优化", "desc": "设定值优化"},
            {"id": "pid_tune", "name": "PID参数整定", "desc": "PID参数整定"},
        ]},
        {"category": "负荷与需求侧管理", "functions": [
            {"id": "load_forecast", "name": "负荷预测", "desc": "负荷预测"},
            {"id": "demand_response", "name": "需求响应", "desc": "需求响应"},
            {"id": "peak_shaving", "name": "削峰填谷", "desc": "削峰填谷"},
            {"id": "energy_baseline", "name": "能耗基线", "desc": "能耗基线"},
        ]},
    ],
    "carbon-management": [
        {"category": "碳管理与综合能源", "functions": [
            {"id": "carbon_accounting", "name": "碳核算", "desc": "碳核算"},
            {"id": "carbon_footprint", "name": "碳足迹追踪", "desc": "碳足迹追踪"},
            {"id": "carbon_trading_strategy", "name": "碳交易策略", "desc": "碳交易策略"},
            {"id": "carbon_quota_manage", "name": "碳配额管理", "desc": "碳配额管理"},
            {"id": "emission_factor", "name": "排放因子计算", "desc": "排放因子计算"},
            {"id": "carbon_sink_estimate", "name": "碳汇估算", "desc": "碳汇估算"},
            {"id": "green_certificate", "name": "绿证管理", "desc": "绿证管理"},
            {"id": "carbon_report", "name": "碳报告生成", "desc": "碳报告生成"},
            {"id": "reduction_path", "name": "减排路径规划", "desc": "减排路径规划"},
            {"id": "carbon_neutral_plan", "name": "碳中和方案", "desc": "碳中和方案"},
        ]},
        {"category": "能源调度优化", "functions": [
            {"id": "carbon_emission_optimize", "name": "碳排放优化", "desc": "碳排放优化"},
            {"id": "energy_trading_optimize", "name": "电力交易优化", "desc": "电力交易优化"},
            {"id": "demand_response_optimize", "name": "需求响应优化", "desc": "需求响应优化"},
            {"id": "economic_dispatch", "name": "经济调度", "desc": "经济调度"},
        ]},
    ],
    # @AI_GENERATED: Kiro v1.0
    "industrial-data-analysis": [
        {"category": "聚类与分群分析", "functions": [
            {"id": "kmeans_cluster", "name": "K-Means聚类", "desc": "K-Means聚类分析"},
            {"id": "dbscan_cluster", "name": "DBSCAN密度聚类", "desc": "DBSCAN密度聚类"},
            {"id": "hierarchical_cluster", "name": "层次聚类", "desc": "层次聚类分析"},
            {"id": "customer_segmentation", "name": "客户分群", "desc": "客户分群分析"},
            {"id": "pattern_cluster", "name": "模式聚类", "desc": "工业模式聚类"},
        ]},
        {"category": "异常检测与模式挖掘", "functions": [
            {"id": "isolation_forest_anomaly", "name": "孤立森林异常检测", "desc": "孤立森林异常检测"},
            {"id": "lof_anomaly", "name": "LOF局部异常检测", "desc": "LOF局部异常检测"},
            {"id": "association_rule", "name": "关联规则挖掘", "desc": "关联规则挖掘"},
            {"id": "sequence_pattern", "name": "序列模式挖掘", "desc": "序列模式挖掘"},
            {"id": "time_pattern_mining", "name": "时序模式挖掘", "desc": "时序模式挖掘"},
        ]},
        {"category": "降维与特征分析", "functions": [
            {"id": "pca_analysis", "name": "PCA主成分分析", "desc": "PCA主成分分析"},
            {"id": "tsne_visualization", "name": "t-SNE可视化", "desc": "t-SNE降维可视化"},
            {"id": "feature_importance", "name": "特征重要性分析", "desc": "特征重要性分析"},
        ]},
    ],
    # @AI_GENERATED: end
    "industrial-llm": [
        {"category": "LLM与工业智能", "functions": [
            {"id": "llm_chat", "name": "LLM对话", "desc": "LLM对话"},
            {"id": "rag_query", "name": "RAG检索增强", "desc": "RAG检索增强"},
            {"id": "llm_function_call", "name": "LLM函数调用", "desc": "LLM函数调用"},
            {"id": "log_parse", "name": "工业日志解析", "desc": "工业日志解析"},
            {"id": "alarm_text_parse", "name": "告警文本解析", "desc": "告警文本解析"},
            {"id": "report_generate", "name": "报告自动生成", "desc": "报告自动生成"},
            {"id": "fine_tune_llm", "name": "LLM微调", "desc": "LLM微调"},
            {"id": "embedding_generate", "name": "文本嵌入生成", "desc": "文本嵌入生成"},
            {"id": "vector_search", "name": "向量检索", "desc": "向量检索"},
            {"id": "document_ocr", "name": "文档OCR识别", "desc": "文档OCR识别"},
            {"id": "table_ocr", "name": "表格OCR识别", "desc": "表格OCR识别"},
            {"id": "knowledge_extract", "name": "知识抽取", "desc": "知识抽取"},
            {"id": "intent_recognition", "name": "意图识别", "desc": "意图识别"},
        ]},
    ],
    "industrial-vision": [
        {"category": "图像分类与检测", "functions": [
            {"id": "image_classifier", "name": "图像分类", "desc": "图像分类"},
            {"id": "object_detector_yolo", "name": "YOLO目标检测", "desc": "YOLO目标检测"},
            {"id": "object_detector_rcnn", "name": "R-CNN目标检测", "desc": "R-CNN目标检测"},
            {"id": "object_detector_ssd", "name": "SSD目标检测", "desc": "SSD目标检测"},
            {"id": "face_detector", "name": "人脸检测", "desc": "人脸检测"},
            {"id": "ocr_detector", "name": "OCR文字检测", "desc": "OCR文字检测"},
            {"id": "keypoint_detector", "name": "关键点检测", "desc": "关键点检测"},
            {"id": "instance_segmentation", "name": "实例分割", "desc": "实例分割"},
        ]},
        {"category": "语义分割", "functions": [
            {"id": "semantic_segmentation", "name": "语义分割", "desc": "语义分割"},
            {"id": "panoptic_segmentation", "name": "全景分割", "desc": "全景分割"},
            {"id": "medical_segmentation", "name": "医学图像分割", "desc": "医学图像分割"},
            {"id": "point_cloud_segmentation", "name": "点云分割", "desc": "点云分割"},
            {"id": "video_segmentation", "name": "视频分割", "desc": "视频分割"},
        ]},
        {"category": "工业缺陷检测", "functions": [
            {"id": "surface_defect_detect", "name": "表面缺陷检测", "desc": "表面缺陷检测"},
            {"id": "weld_defect_detect", "name": "焊缝缺陷检测", "desc": "焊缝缺陷检测"},
            {"id": "pcb_defect_detect", "name": "PCB缺陷检测", "desc": "PCB缺陷检测"},
            {"id": "fabric_defect_detect", "name": "织物缺陷检测", "desc": "织物缺陷检测"},
            {"id": "bottle_defect_detect", "name": "瓶体缺陷检测", "desc": "瓶体缺陷检测"},
            {"id": "crack_detect", "name": "裂纹检测", "desc": "裂纹检测"},
            {"id": "scratch_detect", "name": "划痕检测", "desc": "划痕检测"},
            {"id": "dent_detect", "name": "凹陷检测", "desc": "凹陷检测"},
            {"id": "color_defect_detect", "name": "色差检测", "desc": "色差检测"},
            {"id": "dimension_measure", "name": "尺寸测量", "desc": "尺寸测量"},
            {"id": "alignment_check", "name": "对位检测", "desc": "对位检测"},
            {"id": "completeness_check", "name": "完整性检测", "desc": "完整性检测"},
            {"id": "anomaly_detection_vision", "name": "视觉异常检测", "desc": "视觉异常检测"},
        ]},
    ],
    "equipment-health": [
        {"category": "设备健康管理专用", "functions": [
            {"id": "condition_monitoring", "name": "状态监测", "desc": "设备状态监测"},
            {"id": "predictive_maintenance", "name": "预测性维护", "desc": "预测性维护"},
            {"id": "fmea_analysis", "name": "FMEA分析", "desc": "FMEA分析"},
            {"id": "reliability_analysis", "name": "可靠性分析", "desc": "可靠性分析"},
            {"id": "maintenance_optimize", "name": "维护策略优化", "desc": "维护策略优化"},
            {"id": "spare_parts_predict", "name": "备件需求预测", "desc": "备件需求预测"},
            {"id": "asset_lifecycle", "name": "资产全生命周期", "desc": "资产全生命周期管理"},
            {"id": "warranty_analysis", "name": "质保分析", "desc": "质保分析"},
            {"id": "mtbf_calculate", "name": "MTBF计算", "desc": "平均故障间隔时间计算"},
            {"id": "availability_analysis", "name": "可用率分析", "desc": "设备可用率分析"},
            {"id": "failure_rate_model", "name": "故障率模型", "desc": "故障率建模"},
            {"id": "weibull_analysis", "name": "Weibull分析", "desc": "Weibull寿命分析"},
        ]},
        {"category": "故障诊断", "functions": [
            {"id": "bearing_fault_classifier", "name": "轴承故障诊断", "desc": "轴承故障诊断"},
            {"id": "motor_fault_classifier", "name": "电机故障诊断", "desc": "电机故障诊断"},
            {"id": "gearbox_fault_classifier", "name": "齿轮箱故障诊断", "desc": "齿轮箱故障诊断"},
            {"id": "pump_fault_classifier", "name": "泵故障诊断", "desc": "泵故障诊断"},
            {"id": "compressor_fault_classifier", "name": "压缩机故障诊断", "desc": "压缩机故障诊断"},
            {"id": "vibration_pattern_classifier", "name": "振动模式分类", "desc": "振动模式分类"},
            {"id": "acoustic_fault_classifier", "name": "声学故障分类", "desc": "声学故障分类"},
            {"id": "thermal_fault_classifier", "name": "热故障分类", "desc": "热故障分类"},
            {"id": "multi_fault_classifier", "name": "复合故障诊断", "desc": "复合故障诊断"},
            {"id": "fault_severity_classifier", "name": "故障严重度分级", "desc": "故障严重度分级"},
            {"id": "remaining_useful_life", "name": "剩余寿命预测(RUL)", "desc": "剩余使用寿命预测"},
            {"id": "health_indicator", "name": "健康指标构建", "desc": "健康指标构建"},
            {"id": "degradation_stage_classifier", "name": "退化阶段分类", "desc": "退化阶段分类"},
            {"id": "energy_label_classifier", "name": "能效等级分类", "desc": "能效等级分类"},
        ]},
    ],
}


def generate():
    """生成 industry_templates.json"""
    templates = []
    seen_ids = set()

    for scenario_id, categories in SCENARIO_TEMPLATES_RAW.items():
        for cat_data in categories:
            category = cat_data["category"]
            preset = _get_preset(category)

            for fn in cat_data["functions"]:
                if fn["id"] in seen_ids:
                    continue
                seen_ids.add(fn["id"])

                workflows = []
                for profile, wf_data in preset.items():
                    workflows.append({
                        "profile": profile,
                        "name": wf_data["name"],
                        "layers": wf_data["layers"],
                    })

                templates.append({
                    "id": fn["id"],
                    "name": fn["name"],
                    "scenario_id": scenario_id,
                    "display_category": category,
                    "description": fn.get("desc", fn["name"]),
                    "default_workflows": workflows,
                })

    output = {
        "_comment": "行业算法方案数据（自动生成）。层级：行业场景(L1) → 场景算法方案(L2) → 竞争算法模板(L3，由基础模块L4搭建)。display_category 仅用于前端展示分组。",
        "total_templates": len(templates),
        "templates": templates,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"已生成 {len(templates)} 个行业算法方案 -> {OUTPUT_PATH}")

    by_scenario = {}
    for t in templates:
        by_scenario.setdefault(t["scenario_id"], []).append(t)
    print("\n按场景统计:")
    for sid, tpls in by_scenario.items():
        print(f"  {sid}: {len(tpls)} 个模板")


if __name__ == "__main__":
    generate()
# @AI_GENERATED: end
