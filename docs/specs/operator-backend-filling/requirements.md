<!-- @AI_GENERATED -->
# Requirements Document

## Introduction

本功能为 AIP 工业 AI 算法平台补充常用算子的真实后端实现，并在前端提供可视化标记，让用户一眼区分哪些算子已有可运行的后端代码（"可直接使用"）、哪些仍是空壳元数据定义。当前 functions.json 定义了约 769 个算子，但仅有 46 个在 `backend-service/services/operator_backends/` 目录下有实际实现。本次优先覆盖数据预处理、特征工程、分类、回归、聚类、异常检测、评估、可视化、数据输出、时序和数据源等 P0 级高频算子。

## Glossary

- **Operator_Backend**: `backend-service/services/operator_backends/` 目录下的 Python 模块，导出 `OPERATOR_ID` 字符串和 `execute(params, inputs) -> dict` 函数，由 OperatorRouter 自动发现并注册。
- **OperatorRouter**: `backend-service/services/operator_execution/router.py` 中的路由器类，负责自动扫描 Operator_Backend 目录、注册算子并根据 operator_id 分派执行。
- **Functions_JSON**: `backend-service/data/functions.json`，定义所有 769 个算子的元数据（id、name、category、parameters、return_type、examples）。
- **Function_Library_Page**: 前端 `frontend-sevice/src/pages/FunctionLibraryPage.tsx`，展示算子库列表和分类的页面。
- **Backend_Ready_Badge**: 前端在算子卡片或列表项上显示的视觉标记，指示该算子已有真实后端实现。
- **Backend_Status_API**: 后端暴露的 HTTP 接口，返回当前已注册（有真实后端实现）的算子 ID 列表。
- **P0_Operators**: 本次优先实现的高频算子集合，包括：min_max_scale、z_score_scale、column_select、data_merge、remove_duplicates、pca、logistic_regression、svm_classifier、decision_tree_classifier、linear_regression、lasso_regression、elastic_net、kmeans、dbscan、isolation_forest、one_class_svm、r2_score、mape_score、roc_auc、line_chart、scatter_chart、histogram、export_csv、export_excel、arima、prophet、load_parquet、load_json。

## Requirements

### Requirement 1: Backend Status Discovery API

**User Story:** As a frontend developer, I want to query which operators have real backend implementations, so that I can display readiness indicators in the UI without hardcoding operator IDs.

#### Acceptance Criteria

1. THE Backend_Status_API SHALL expose a GET endpoint at `/api/functions/backend-status` that returns a JSON object containing a list of operator IDs with registered backends.
2. WHEN the Backend_Status_API endpoint is called, THE OperatorRouter SHALL return all operator IDs currently registered via auto-discovery.
3. THE Backend_Status_API response SHALL include a `total_registered` integer count and a `registered_operators` string array.
4. WHEN the OperatorRouter has no registered backends, THE Backend_Status_API SHALL return `total_registered: 0` and an empty `registered_operators` array.

### Requirement 2: Data Preprocessing Operator Backends

**User Story:** As a data scientist, I want to use standard data preprocessing operators (min-max scaling, z-score normalization, column selection, data merging, deduplication) in workflows, so that I can prepare data without writing custom code.

#### Acceptance Criteria

1. WHEN a DataFrame and target columns are provided, THE min_max_scale Operator_Backend SHALL scale each specified column to the range [0, 1] using (x - min) / (max - min).
2. WHEN a DataFrame and target columns are provided, THE z_score_scale Operator_Backend SHALL standardize each specified column to mean 0 and standard deviation 1.
3. WHEN a DataFrame and a list of column names are provided, THE column_select Operator_Backend SHALL return a DataFrame containing only the specified columns.
4. WHEN two DataFrames and a join key are provided, THE data_merge Operator_Backend SHALL merge them using the specified join type (inner, left, right, outer) on the specified key column.
5. WHEN a DataFrame is provided, THE remove_duplicates Operator_Backend SHALL remove duplicate rows and return a deduplicated DataFrame.
6. IF a specified column does not exist in the input DataFrame, THEN THE data preprocessing Operator_Backend SHALL raise an OperatorExecutionError with error_type "ColumnNotFoundError".
7. IF the input DataFrame is empty, THEN THE data preprocessing Operator_Backend SHALL return an empty DataFrame without raising an error.

### Requirement 3: Feature Engineering Operator Backend (PCA)

**User Story:** As a data scientist, I want to reduce dataset dimensionality using PCA, so that I can improve model training speed and reduce noise.

#### Acceptance Criteria

1. WHEN a DataFrame and n_components parameter are provided, THE pca Operator_Backend SHALL perform Principal Component Analysis and return a DataFrame with n_components columns named PC_1, PC_2, ..., PC_n.
2. THE pca Operator_Backend SHALL also return an `explained_variance_ratio` array showing the variance explained by each component.
3. IF n_components exceeds the number of features in the input, THEN THE pca Operator_Backend SHALL raise an OperatorExecutionError with error_type "ParameterError".
4. IF the input DataFrame contains non-numeric columns, THEN THE pca Operator_Backend SHALL automatically exclude non-numeric columns and log a warning.

### Requirement 4: Classification Operator Backends

**User Story:** As a data scientist, I want to train and predict with standard classification algorithms (logistic regression, SVM, decision tree), so that I can build classification models within the platform workflow.

#### Acceptance Criteria

1. WHEN mode is "train" and features/target inputs are provided, THE logistic_regression Operator_Backend SHALL fit a LogisticRegression model, save it to disk, and return the model object, model_id, predictions on a holdout split, and feature importances (coefficients).
2. WHEN mode is "predict" and a model_id or model object is provided, THE logistic_regression Operator_Backend SHALL return predictions for the given input features.
3. WHEN mode is "train" and features/target inputs are provided, THE svm_classifier Operator_Backend SHALL fit an SVM classifier with configurable kernel (linear, rbf, poly) and C parameter.
4. WHEN mode is "train" and features/target inputs are provided, THE decision_tree_classifier Operator_Backend SHALL fit a DecisionTreeClassifier with configurable max_depth and min_samples_split.
5. THE classification Operator_Backends SHALL follow the same train/predict pattern as the existing random_forest_classifier: 80/20 holdout evaluation, full-data retraining for saved model, serialization via pickle.
6. IF the target input contains fewer than 2 unique classes, THEN THE classification Operator_Backend SHALL raise an OperatorExecutionError with error_type "InputError".

### Requirement 5: Regression Operator Backends

**User Story:** As a data scientist, I want to use standard regression algorithms (linear regression, lasso, elastic net), so that I can build predictive models for continuous target variables.

#### Acceptance Criteria

1. WHEN mode is "train" and features/target inputs are provided, THE linear_regression Operator_Backend SHALL fit a LinearRegression model and return coefficients, intercept, model_id, and predictions on a holdout split.
2. WHEN mode is "train" and an alpha parameter is provided, THE lasso_regression Operator_Backend SHALL fit a Lasso model with the specified regularization strength.
3. WHEN mode is "train" and alpha/l1_ratio parameters are provided, THE elastic_net Operator_Backend SHALL fit an ElasticNet model with specified alpha and l1_ratio.
4. THE regression Operator_Backends SHALL follow the same train/predict pattern as classification operators: holdout evaluation, model serialization, model_id return.
5. IF the target input contains non-numeric values, THEN THE regression Operator_Backend SHALL raise an OperatorExecutionError with error_type "InputError".

### Requirement 6: Clustering Operator Backends

**User Story:** As a data scientist, I want to perform clustering analysis (KMeans, DBSCAN) within the platform workflow, so that I can discover patterns in unlabeled data.

#### Acceptance Criteria

1. WHEN a DataFrame and n_clusters parameter are provided, THE kmeans Operator_Backend SHALL perform K-Means clustering and return cluster labels, cluster centers, and inertia score.
2. WHEN a DataFrame and eps/min_samples parameters are provided, THE dbscan Operator_Backend SHALL perform DBSCAN clustering and return cluster labels and the number of clusters found (excluding noise).
3. THE clustering Operator_Backends SHALL return a `labels` array aligned with the input DataFrame rows.
4. IF the input DataFrame contains fewer than 2 samples, THEN THE clustering Operator_Backend SHALL raise an OperatorExecutionError with error_type "InputError".

### Requirement 7: Anomaly Detection Operator Backends

**User Story:** As a data scientist, I want to use anomaly detection algorithms (Isolation Forest, One-Class SVM), so that I can identify outliers in industrial data.

#### Acceptance Criteria

1. WHEN a DataFrame is provided, THE isolation_forest Operator_Backend SHALL fit an IsolationForest model with configurable contamination and n_estimators parameters, and return anomaly labels (-1 for anomaly, 1 for normal) and anomaly scores.
2. WHEN a DataFrame is provided, THE one_class_svm Operator_Backend SHALL fit a OneClassSVM model with configurable kernel and nu parameters, and return anomaly labels and decision function scores.
3. THE anomaly detection Operator_Backends SHALL support both "fit_predict" mode (train and predict on same data) and "predict" mode (use a previously saved model).
4. IF the input DataFrame is empty, THEN THE anomaly detection Operator_Backend SHALL raise an OperatorExecutionError with error_type "InputError".

### Requirement 8: Evaluation Metric Operator Backends

**User Story:** As a data scientist, I want to compute standard evaluation metrics (R², MAPE, ROC AUC), so that I can assess model performance within the workflow.

#### Acceptance Criteria

1. WHEN y_true and y_pred arrays are provided, THE r2_score Operator_Backend SHALL compute and return the coefficient of determination (R²).
2. WHEN y_true and y_pred arrays are provided, THE mape_score Operator_Backend SHALL compute and return the Mean Absolute Percentage Error.
3. WHEN y_true and y_score arrays are provided, THE roc_auc Operator_Backend SHALL compute and return the Area Under the ROC Curve.
4. IF y_true and y_pred have different lengths, THEN THE evaluation Operator_Backend SHALL raise an OperatorExecutionError with error_type "InputError".
5. IF y_true contains zero values, THEN THE mape_score Operator_Backend SHALL handle division by zero by excluding zero-valued entries and logging a warning.
6. WHEN computing roc_auc for multiclass problems, THE roc_auc Operator_Backend SHALL use the "ovr" (one-vs-rest) strategy with macro averaging.

### Requirement 9: Visualization Operator Backends

**User Story:** As a data scientist, I want to generate chart configurations (line chart, scatter plot, histogram) within the workflow, so that results can be rendered by the frontend.

#### Acceptance Criteria

1. WHEN a DataFrame with x and y columns is provided, THE line_chart Operator_Backend SHALL return an ECharts-compatible option JSON for a line chart.
2. WHEN a DataFrame with x and y columns is provided, THE scatter_chart Operator_Backend SHALL return an ECharts-compatible option JSON for a scatter plot.
3. WHEN a DataFrame and a target column are provided, THE histogram Operator_Backend SHALL return an ECharts-compatible option JSON for a histogram with configurable bin count.
4. THE visualization Operator_Backends SHALL return output in the format `{"chart_option": dict, "chart_type": str}` so the frontend can render the chart using ECharts.
5. IF the specified x or y column does not exist in the input DataFrame, THEN THE visualization Operator_Backend SHALL raise an OperatorExecutionError with error_type "ColumnNotFoundError".

### Requirement 10: Data Output Operator Backends

**User Story:** As a data scientist, I want to export workflow results to CSV or Excel files, so that I can share processed data with other systems.

#### Acceptance Criteria

1. WHEN a DataFrame and output_path parameter are provided, THE export_csv Operator_Backend SHALL write the DataFrame to a CSV file at the specified relative path and return the written file path.
2. WHEN a DataFrame and output_path parameter are provided, THE export_excel Operator_Backend SHALL write the DataFrame to an Excel (.xlsx) file at the specified relative path and return the written file path.
3. THE data output Operator_Backends SHALL create parent directories if they do not exist.
4. THE data output Operator_Backends SHALL use relative paths (relative to backend-service/) for output files.
5. IF the output_path parameter is not provided, THEN THE data output Operator_Backend SHALL generate a default filename using a timestamp pattern (e.g., `data/exports/export_YYYYMMDD_HHMMSS.csv`).

### Requirement 11: Time Series Operator Backends

**User Story:** As a data scientist, I want to use time series forecasting algorithms (ARIMA, Prophet), so that I can build forecasting models within the platform workflow.

#### Acceptance Criteria

1. WHEN a time series DataFrame with timestamp and value columns is provided, THE arima Operator_Backend SHALL fit an ARIMA model with configurable (p, d, q) order parameters and return forecasted values for the specified forecast_horizon.
2. WHEN a time series DataFrame with ds and y columns is provided, THE prophet Operator_Backend SHALL fit a Prophet model and return forecasted values with upper and lower confidence bounds.
3. THE time series Operator_Backends SHALL return output containing `forecast` (array of predicted values) and `forecast_dates` (array of corresponding timestamps).
4. IF the input time series has fewer than 10 data points, THEN THE time series Operator_Backend SHALL raise an OperatorExecutionError with error_type "InputError" with a message indicating insufficient data.
5. IF the Prophet library is not installed, THEN THE prophet Operator_Backend SHALL raise an OperatorExecutionError with error_type "DependencyError" and a message instructing to install the prophet package.

### Requirement 12: Data Source Operator Backends

**User Story:** As a data scientist, I want to load data from Parquet and JSON files, so that I can use diverse data formats as workflow inputs.

#### Acceptance Criteria

1. WHEN a file_path pointing to a .parquet file is provided, THE load_parquet Operator_Backend SHALL read the file and return a DataFrame.
2. WHEN a file_path pointing to a .json file is provided, THE load_json Operator_Backend SHALL read the file and return a DataFrame (supporting both array-of-objects and records format).
3. THE data source Operator_Backends SHALL use the same relative path resolution strategy as the existing load_csv operator (search workspace_root → aip_dir → backend_dir → cwd).
4. IF the specified file does not exist in any searched directory, THEN THE data source Operator_Backend SHALL raise an OperatorExecutionError with error_type "FileNotFoundError".

### Requirement 13: Frontend Backend-Ready Badge

**User Story:** As a platform user, I want to visually distinguish which operators have real backend implementations in the function library page, so that I know which operators I can use immediately in workflows.

#### Acceptance Criteria

1. WHEN the Function_Library_Page loads, THE Frontend SHALL fetch the backend status from the Backend_Status_API and cache the result for the session.
2. THE Frontend SHALL display a Backend_Ready_Badge (a green badge or tag labeled "可执行" / "Ready") on each operator card or list item whose ID is in the `registered_operators` list.
3. WHILE an operator does not have a registered backend, THE Frontend SHALL display a neutral indicator (a grey badge labeled "仅定义" / "Definition Only") on the operator card.
4. THE Frontend SHALL allow filtering operators by backend readiness status (all / ready / definition-only).
5. WHEN the Backend_Status_API returns an error or is unreachable, THE Frontend SHALL display all operators without badges and log a console warning.
<!-- @AI_GENERATED: end -->
