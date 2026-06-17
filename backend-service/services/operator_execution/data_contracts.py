# @AI_GENERATED
"""
Data Contract Registry - Defines all data contracts for the load forecast pipeline.

Each contract specifies the expected format of data passed between operators,
including required columns, column types, and constraints.
"""
from .schema_validator import DataContract


LOAD_FORECAST_CONTRACTS = {
    "load_csv_output": DataContract(
        contract_id="load_csv_output",
        data_type="MATRIX",
        required_columns=["record_time", "load"],
        column_types={"record_time": "datetime64", "load": "float64"},
        constraints=["time_ordered", "no_duplicates"],
        description="CSV 加载输出：含时间戳和负荷列的有序 DataFrame",
    ),
    "row_filter_output": DataContract(
        contract_id="row_filter_output",
        data_type="MATRIX",
        required_columns=["record_time", "load"],
        column_types={"record_time": "datetime64", "load": "float64"},
        constraints=["time_ordered"],
        description="行过滤输出：按条件过滤后的 DataFrame，保留原始列结构",
    ),
    "resample_output": DataContract(
        contract_id="resample_output",
        data_type="MATRIX",
        required_columns=["record_time", "load"],
        column_types={"record_time": "datetime64", "load": "float64"},
        constraints=["time_ordered", "continuous_index"],
        description="重采样输出：连续时间索引，缺失点为 NaN",
    ),
    "detect_outliers_output": DataContract(
        contract_id="detect_outliers_output",
        data_type="OBJECT",
        required_columns=["record_time", "load"],
        column_types={"record_time": "datetime64", "load": "float64"},
        constraints=["outliers_replaced_nan"],
        description="异常检测输出：异常值已替换为 NaN + 异常索引列表",
    ),
    "handle_missing_output": DataContract(
        contract_id="handle_missing_output",
        data_type="MATRIX",
        required_columns=["record_time", "load"],
        column_types={"record_time": "datetime64", "load": "float64"},
        constraints=["no_nan", "time_ordered"],
        description="缺失值处理输出：所有数值列无 NaN",
    ),
    "time_features_output": DataContract(
        contract_id="time_features_output",
        data_type="MATRIX",
        required_columns=["record_time", "load", "hour", "dayofweek", "month"],
        column_types={"hour": "int", "dayofweek": "int", "month": "int"},
        constraints=["features_merged"],
        description="时间特征输出：在输入基础上新增时间特征列",
    ),
    "holiday_features_output": DataContract(
        contract_id="holiday_features_output",
        data_type="MATRIX",
        required_columns=["is_holiday"],
        column_types={"is_holiday": "int"},
        constraints=["features_merged"],
        description="节假日特征输出：新增 is_holiday 列",
    ),
    "workday_features_output": DataContract(
        contract_id="workday_features_output",
        data_type="MATRIX",
        required_columns=["is_workday"],
        column_types={"is_workday": "int"},
        constraints=["features_merged"],
        description="工作日特征输出：新增 is_workday 列",
    ),
    "rolling_stats_output": DataContract(
        contract_id="rolling_stats_output",
        data_type="MATRIX",
        required_columns=[],
        column_types={},
        constraints=["features_merged"],
        description="滚动统计输出：新增滚动统计列",
    ),
    "lag_features_output": DataContract(
        contract_id="lag_features_output",
        data_type="MATRIX",
        required_columns=[],
        column_types={},
        constraints=["features_merged"],
        description="滞后特征输出：新增滞后列",
    ),
    "sliding_window_output": DataContract(
        contract_id="sliding_window_output",
        data_type="MATRIX",
        required_columns=[],
        column_types={},
        constraints=["window_size_consistent", "step_aligned", "no_future_leak"],
        description="滑动窗口输出：按窗口切片后的样本数据",
    ),
    "train_test_split_output": DataContract(
        contract_id="train_test_split_output",
        data_type="OBJECT",
        required_columns=[],
        column_types={},
        constraints=["train_test_same_columns", "time_ordered"],
        description="数据切分输出：train_features, train_target, test_features, test_target",
    ),
    "multi_step_forecast_output": DataContract(
        contract_id="multi_step_forecast_output",
        data_type="OBJECT",
        required_columns=[],
        column_types={},
        constraints=["forecast_steps_positive", "strategy_valid"],
        description="多步预测配置输出：forecast_config + 透传训练/测试数据",
    ),
    "xgboost_train_output": DataContract(
        contract_id="xgboost_train_output",
        data_type="OBJECT",
        required_columns=[],
        column_types={},
        constraints=[],
        description="XGBoost 训练输出：predictions (ARRAY) + model (OBJECT) + y_true/y_pred",
    ),
    "xgboost_predict_output": DataContract(
        contract_id="xgboost_predict_output",
        data_type="OBJECT",
        required_columns=[],
        column_types={},
        constraints=[],
        description="XGBoost 预测输出：forecast_timestamps + forecast_values",
    ),
    "smape_output": DataContract(
        contract_id="smape_output",
        data_type="NUMBER",
        required_columns=[],
        column_types={},
        constraints=["range_0_200", "finite"],
        description="SMAPE 输出：百分比形式，取值 [0, 200]",
    ),
    "mse_rmse_mae_output": DataContract(
        contract_id="mse_rmse_mae_output",
        data_type="OBJECT",
        required_columns=[],
        column_types={},
        constraints=["non_negative", "finite"],
        description="MSE/RMSE/MAE 输出：三个非负浮点数",
    ),
}
# @AI_GENERATED: end
