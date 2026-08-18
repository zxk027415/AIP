<!-- @AI_GENERATED -->
# 需求文档：基于 AIP 通用算子填充实现负荷预测流水线

## 简介

本文档定义了将本地负荷预测代码的各步骤逻辑**映射并填充到 AIP 平台已有的通用算子**中的功能需求。核心思路是：**不新建自定义负荷预测算子**，而是复用 AIP 平台已注册的 814 个通用算子（如 `load_csv`、`detect_outliers`、`extract_time_features`、`xgboost_forecast` 等），为每个通用算子实现真实的后端执行逻辑，使其能够运行本地负荷预测代码中对应的功能。

这种方式的核心优势在于**复用性**：同一个 `load_csv` 算子填充后，不仅可用于负荷预测，也可用于光伏预测、风电预测等其他算法场景；同一个 `detect_outliers` 算子可用于任何需要异常检测的流水线。负荷预测流水线本身只是这些通用算子的一种特定组合（模板）。

当前系统已具备以下基础：
- 后端 `functions.json` 中已注册 814 个通用算子定义，涵盖数据源、数据预处理、特征工程、时序预测、模型训练、评估指标等 19 个类别
- 前端已有增强版工作流编辑器（`WorkflowEditorPage`）支持节点拖拽和连线
- 本地负荷预测代码已实现完整的训练流水线（数据加载 → 异常检测 → 特征工程 → 模型训练 → 预测 → 评估）

本次需求的核心目标是：**为 AIP 平台已有的通用算子逐个填充后端执行逻辑，使负荷预测流水线可以通过组合这些通用算子来运行，同时保证这些算子对其他算法场景同样通用。**

## 术语表

- **Generic_Operator（通用算子）**: AIP 平台 `functions.json` 中已注册的通用功能算子（如 `load_csv`、`detect_outliers`），具备标准化的输入输出端口和参数定义，可被任意工作流复用
- **Operator_Backend（算子后端）**: 通用算子对应的 Python 执行逻辑，接收算子参数和上游数据，执行实际计算并返回结果
- **Operator_Filling（算子填充）**: 为已注册但尚未实现后端逻辑的通用算子编写真实的执行代码，使其从"空壳定义"变为"可执行算子"
- **Pipeline_Template（流水线模板）**: 由多个通用算子按特定顺序组合而成的工作流模板，代表一种特定算法的执行流程（如负荷预测模板、光伏预测模板）
- **Workflow_Editor（工作流编辑器）**: 前端增强版可视化编辑器页面（`WorkflowEditorPage`），用户在此拖拽算子、连线、配置参数并执行工作流
- **Workflow_Executor（工作流执行器）**: 后端 `workflows_enhanced.py` 中的 `execute_workflow` 端点，按拓扑排序逐节点执行工作流
- **Operator_Config_Panel（算子配置面板）**: 用户点击算子节点后弹出的参数编辑侧边栏，展示该算子的所有可配置参数
- **Operator_Registry（算子注册表）**: `functions.json` 文件，存储所有通用算子的元数据定义（ID、参数、输入输出类型等）
- **Scenario_Config（场景配置）**: 负荷预测的 6 种预测场景（DI/D/WI/W/MI/M）的推荐参数配置
- **Data_Contract（数据契约）**: 算子间传递数据的格式规范，定义了每个算子输出的 DataFrame 列名、数据类型和结构约束，以及下游算子期望的输入 Schema
- **Schema_Validator（Schema 校验器）**: 在算子执行前后自动校验数据是否符合 Data_Contract 定义的格式规范的组件
- **Pipeline_Data_Flow（流水线数据流）**: 负荷预测流水线中算子间数据传递的完整链路定义，包含每一对相邻算子之间的输入输出 Schema 映射关系
- **Humanized_Param（人性化参数）**: 算子参数的用户友好展示形式，包含中文标签、描述文字、合理默认值和匹配的输入控件类型（下拉框、滑块、开关等），使非技术用户也能直观配置算子行为
- **Multi_Step_Forecast（多步预测算子）**: `functions.json` 中 `ts_forecast` 类别下已注册的通用算子，负责配置预测步长（forecast horizon）和预测策略（递归/直接/混合），是跨层概念"step 配置"的预测步数维度
- **Sliding_Window（滑动窗口算子）**: `functions.json` 中 `data_preprocessing` 类别下已注册的通用算子，负责将时序数据按滑动窗口方式切片为模型输入样本，是跨层概念"step 配置"的输入窗口维度
- **Domain_Options（业务参数）**: 通过通用算子的 `options` JSON 字段承载的领域特定配置参数（如负荷预测的 `task_type`、`separate_modeling`、`time_zone` 等），这些参数不属于通用算子的标准参数，而是特定算法场景的扩展配置
- **Options_Schema（业务参数 Schema）**: 每个算子在特定算法场景下的 `options` JSON 字段的结构定义，包含字段名、类型、默认值和中文描述，用于 Operator_Config_Panel 自动生成业务参数编辑表单
- **Pipeline_Progress_Tracker（流水线进度追踪器）**: 工作流编辑器中的执行进度组件，以步骤条形式展示流水线中所有算子节点的实时执行状态，复用 `load-forecast-training-ui` 中 ProgressTracker 的设计模式
- **Pipeline_Log_Console（流水线日志控制台）**: 工作流编辑器中的执行日志组件，以深色背景终端风格面板展示带时间戳的算子执行日志，复用 `load-forecast-training-ui` 中 LogConsole 的设计模式
- **Pipeline_Result_Dashboard（流水线结果仪表盘）**: 工作流编辑器中的执行结果展示组件，展示耗时统计、模型信息、评估指标和回测结果，复用 `load-forecast-training-ui` 中 ResultDashboard 和 MetricsChart 的设计模式
- **Prediction_Pipeline_Template（推理流水线模板）**: 由通用算子组成的负荷预测推理流水线模板，复用训练流水线中的数据加载、异常检测、特征工程算子，并以"预测模式"调用 `xgboost_forecast` 算子，需要指定已训练的 `model_id` 加载模型
- **Prediction_Result_Dashboard（推理结果仪表盘）**: 推理流水线执行完成后的结果展示组件，展示预测时间戳、预测值、预测曲线图表和所用模型信息
- **Backtest_Pipeline_Template（回测流水线模板）**: 高层编排模板，按日期范围循环执行"训练子流水线 → 推理子流水线"，收集每日预测结果并计算评估指标
- **Backtest_Result_Dashboard（回测结果仪表盘）**: 回测流水线执行完成后的结果展示组件，展示回测汇总统计、每日预测对比曲线、评估指标和逐日明细表
- **Backtest_Evaluation_Metrics（回测评估指标）**: 回测过程中计算的精度评估指标集合，包含 SMAPE、MAE、RMSE 的逐日值和整体平均值

## 需求

### 需求 1：数据源算子填充 — load_csv

**用户故事：** 作为平台用户，我想使用通用的 `load_csv` 算子加载 CSV/Excel 格式的时序数据文件，以便在负荷预测、光伏预测等多种算法流水线中复用同一个数据加载能力。

#### 验收标准

1. WHEN 用户在工作流中配置 `load_csv` 算子并指定 `file_path` 参数, THE Operator_Backend SHALL 调用 `pd.read_csv` 读取文件并返回 MATRIX 类型的 DataFrame 数据
2. WHEN `load_csv` 算子的 `timestamp_column` 参数非空, THE Operator_Backend SHALL 将该列解析为 datetime 类型并设置为时间索引
3. WHEN `load_csv` 算子的 `value_columns` 参数非空, THE Operator_Backend SHALL 仅加载指定的数值列和时间戳列，忽略其他列
4. THE `load_csv` Operator_Backend SHALL 支持 `delimiter`（分隔符）、`encoding`（编码）、`header_row`（表头行号）参数，与 `functions.json` 中的定义一致
5. IF 指定的 `file_path` 不存在或文件格式无法解析, THEN THE Operator_Backend SHALL 返回包含错误原因的错误信息
6. THE `load_csv` Operator_Backend SHALL 对加载的数据按时间戳列排序并去除重复行，确保输出数据的时间有序性

### 需求 2：数据源算子填充 — load_database

**用户故事：** 作为平台用户，我想使用通用的 `load_database` 算子从关系型数据库中查询时序数据，以便在生产环境中从 MySQL 等数据库拉取负荷真值数据。

#### 验收标准

1. WHEN 用户配置 `load_database` 算子并提供 `db_type`、`connection_string` 和 `query` 参数, THE Operator_Backend SHALL 连接数据库执行 SQL 查询并返回 MATRIX 类型的 DataFrame 数据
2. THE `load_database` Operator_Backend SHALL 支持 `mysql`、`postgresql`、`sqlite` 三种数据库类型
3. IF 数据库连接失败或 SQL 执行出错, THEN THE Operator_Backend SHALL 返回包含错误原因的错误信息并关闭数据库连接
4. THE `load_database` Operator_Backend SHALL 对查询结果按时间戳列排序（当结果包含可识别的时间列时）

### 需求 3：数据源算子填充 — load_api

**用户故事：** 作为平台用户，我想使用通用的 `load_api` 算子从 REST API 拉取远程数据，以便接入在线数据服务获取实时负荷数据或气象数据。

#### 验收标准

1. WHEN 用户配置 `load_api` 算子并提供 `url` 和 `method` 参数, THE Operator_Backend SHALL 发送 HTTP 请求并将响应数据解析为 MATRIX 类型的 DataFrame
2. THE `load_api` Operator_Backend SHALL 支持 GET 和 POST 请求方法，支持 `headers` 和 `body` 参数配置
3. IF HTTP 请求返回非 2xx 状态码或响应数据无法解析, THEN THE Operator_Backend SHALL 返回包含 HTTP 状态码和错误原因的错误信息

### 需求 4：数据预处理算子填充 — resample_timeseries

**用户故事：** 作为平台用户，我想使用通用的 `resample_timeseries` 算子对时序数据进行重采样和时间戳补全，以便将不同频率的原始数据对齐到统一的时间粒度。

#### 验收标准

1. WHEN 用户配置 `resample_timeseries` 算子并指定 `frequency` 参数（如 `15min`、`1H`）, THE Operator_Backend SHALL 将输入数据重采样到目标频率并返回连续时间网格的 MATRIX 数据
2. THE `resample_timeseries` Operator_Backend SHALL 支持 `mean`、`sum`、`max`、`min` 四种聚合方法，通过 `method` 参数配置
3. THE `resample_timeseries` Operator_Backend SHALL 在重采样过程中自动生成完整的时间戳网格（从数据最小时间到最大时间），对缺失时间点填充 NaN
4. THE `resample_timeseries` Operator_Backend SHALL 实现与本地代码 `get_completed_timestamp` 等价的时间戳补全逻辑，确保输出数据具有连续的时间索引

### 需求 5：数据预处理算子填充 — detect_outliers

**用户故事：** 作为平台用户，我想使用通用的 `detect_outliers` 算子检测时序数据中的异常值，以便在负荷预测、设备监控等多种场景中复用同一个异常检测能力。

#### 验收标准

1. WHEN 用户配置 `detect_outliers` 算子并指定 `method` 为 `zscore`, THE Operator_Backend SHALL 使用滚动中位数和 MAD（中位绝对偏差）方法检测异常值，与本地代码 `chebyshev_detector` 的 rolling MAD 逻辑等价
2. THE `detect_outliers` Operator_Backend SHALL 支持 `zscore`、`iqr`、`isolation_forest` 三种检测方法
3. THE `detect_outliers` Operator_Backend SHALL 通过 `threshold` 参数控制检测灵敏度（默认 3.0），将超过阈值的数据点标记为异常
4. THE `detect_outliers` Operator_Backend SHALL 返回异常值的索引列表（ARRAY 类型），供下游算子使用
5. THE `detect_outliers` Operator_Backend SHALL 在滚动统计计算中仅使用历史数据（向后偏移 1 步），避免未来数据泄露

### 需求 6：数据预处理算子填充 — handle_missing

**用户故事：** 作为平台用户，我想使用通用的 `handle_missing` 算子处理时序数据中的缺失值，以便在数据清洗阶段灵活选择填补策略。

#### 验收标准

1. WHEN 用户配置 `handle_missing` 算子并指定 `method` 为 `linear`, THE Operator_Backend SHALL 使用基于时间索引的线性插值填充缺失值，与本地代码 `get_completed_df` 的 `interpolate(method='time')` 逻辑等价
2. THE `handle_missing` Operator_Backend SHALL 支持 `linear`（线性插值）、`ffill`（前向填充）、`bfill`（后向填充）、`mean`（均值填充）四种方法
3. THE `handle_missing` Operator_Backend SHALL 在插值后对仍存在的缺失值执行 ffill 再 bfill 兜底填充，确保输出数据无 NaN
4. THE `handle_missing` Operator_Backend SHALL 对非目标列（非 load 列）使用 ffill/bfill 策略填充


### 需求 7：特征工程算子填充 — extract_time_features

**用户故事：** 作为平台用户，我想使用通用的 `extract_time_features` 算子从时间戳中提取小时、星期、月份等时间特征，以便在负荷预测、光伏预测等多种时序预测场景中复用。

#### 验收标准

1. WHEN 用户配置 `extract_time_features` 算子并指定 `features` 列表（如 `["hour", "dayofweek", "month"]`）, THE Operator_Backend SHALL 从输入时间戳数组中提取对应的时间特征列并返回 MATRIX 数据
2. THE `extract_time_features` Operator_Backend SHALL 支持以下特征类型：`hour`（小时）、`dayofweek`（星期几）、`month`（月份）、`day`（日）、`quarter`（季度）、`is_holiday`（是否节假日）
3. THE `extract_time_features` Operator_Backend SHALL 实现与本地代码 `add_more_features` 中时间特征提取部分等价的逻辑
4. THE `extract_time_features` Operator_Backend SHALL 将提取的特征列合并到输入数据中一起返回

### 需求 8：特征工程算子填充 — holiday_features

**用户故事：** 作为平台用户，我想使用通用的 `holiday_features` 算子标记中国法定节假日，以便在负荷预测中区分节假日和工作日的用电模式差异。

#### 验收标准

1. WHEN 用户配置 `holiday_features` 算子, THE Operator_Backend SHALL 使用 `chinese_calendar` 库为每个时间戳标记是否为中国法定节假日
2. THE `holiday_features` Operator_Backend SHALL 生成 `is_holiday`（是否节假日）和 `holiday_name`（节假日名称）两个特征列
3. THE `holiday_features` Operator_Backend SHALL 实现与本地代码中 `chinese_calendar.get_holiday_detail` 调用等价的逻辑
4. THE `holiday_features` Operator_Backend SHALL 支持通过 `options` 参数配置是否剔除春节数据（与本地代码 `remove_special_data` 逻辑对应）

### 需求 9：特征工程算子填充 — workday_features

**用户故事：** 作为平台用户，我想使用通用的 `workday_features` 算子标记工作日、休息日和班次信息，以便在负荷预测中捕捉工作日和休息日的用电规律差异。

#### 验收标准

1. WHEN 用户配置 `workday_features` 算子, THE Operator_Backend SHALL 为每个时间戳生成 `is_workday`（是否工作日）特征列
2. THE `workday_features` Operator_Backend SHALL 实现与本地代码 `common.holidays.if_workday` 等价的工作日判断逻辑
3. THE `workday_features` Operator_Backend SHALL 支持通过 `options` 参数配置班次划分规则（如早班/中班/晚班的时间段定义）

### 需求 10：特征工程算子填充 — rolling_statistics

**用户故事：** 作为平台用户，我想使用通用的 `rolling_statistics` 算子计算滚动统计特征（均值、标准差、分位数），以便在时序预测中捕捉数据的局部趋势和波动特征。

#### 验收标准

1. WHEN 用户配置 `rolling_statistics` 算子, THE Operator_Backend SHALL 计算指定窗口大小的滚动均值、标准差和分位数特征
2. THE `rolling_statistics` Operator_Backend SHALL 支持通过 `options` 参数配置窗口大小列表（如 `[24, 48, 96, 168]`）和统计量类型（`mean`、`std`、`quantile`）
3. THE `rolling_statistics` Operator_Backend SHALL 实现与本地代码 `get_rolling_features` 等价的滚动统计逻辑
4. THE `rolling_statistics` Operator_Backend SHALL 仅使用历史数据计算滚动统计量，避免未来数据泄露

### 需求 11：特征工程算子填充 — create_lag_features

**用户故事：** 作为平台用户，我想使用通用的 `create_lag_features` 算子生成滞后特征，以便在时序预测中利用历史值作为模型输入。

#### 验收标准

1. WHEN 用户配置 `create_lag_features` 算子并指定 `lags` 列表（如 `[1, 24, 168]`）, THE Operator_Backend SHALL 为输入数据的目标列生成对应步数的滞后特征列
2. THE `create_lag_features` Operator_Backend SHALL 实现与本地代码中 shift 操作等价的滞后特征生成逻辑
3. THE `create_lag_features` Operator_Backend SHALL 对滞后产生的 NaN 值保留不填充，由下游算子决定处理策略

### 需求 12：特征工程算子填充 — diff_features 和 pct_change_features

**用户故事：** 作为平台用户，我想使用通用的 `diff_features` 和 `pct_change_features` 算子生成差分特征和变化率特征，以便在时序预测中捕捉数据的变化趋势。

#### 验收标准

1. WHEN 用户配置 `diff_features` 算子, THE Operator_Backend SHALL 计算一阶差分和季节差分特征，与本地代码 `get_diff_features` 等价
2. WHEN 用户配置 `pct_change_features` 算子, THE Operator_Backend SHALL 计算百分比变化率特征，与本地代码 `get_pct_rate_feature` 等价
3. THE `diff_features` Operator_Backend SHALL 支持通过 `options` 参数配置差分阶数和季节周期
4. THE `pct_change_features` Operator_Backend SHALL 支持通过 `options` 参数配置变化率的计算周期

### 需求 13：特征工程算子填充 — extract_statistical_features、peak_valley_features、shift_features

**用户故事：** 作为平台用户，我想使用通用的统计特征、峰谷时段特征和班次特征算子，以便在负荷预测中捕捉用电的统计规律和时段特征。

#### 验收标准

1. WHEN 用户配置 `extract_statistical_features` 算子, THE Operator_Backend SHALL 计算历史同期统计特征（均值、最大值、最小值、标准差），与本地代码 `get_stat_features` 和 `get_hist_period_statis` 等价
2. WHEN 用户配置 `peak_valley_features` 算子, THE Operator_Backend SHALL 标记峰时段、谷时段和平时段，与本地代码中的峰谷时段划分逻辑等价
3. WHEN 用户配置 `shift_features` 算子, THE Operator_Backend SHALL 标记当前时间点所属的班次（早班/中班/晚班），与本地代码中的班次划分逻辑等价

### 需求 14：模型训练算子填充 — train_test_split_ts

**用户故事：** 作为平台用户，我想使用通用的 `train_test_split_ts` 算子按时间顺序切分时序数据，以便在模型训练中正确划分训练集和验证集。

#### 验收标准

1. WHEN 用户配置 `train_test_split_ts` 算子并指定 `train_ratio` 和 `val_ratio`, THE Operator_Backend SHALL 按时间顺序将数据切分为训练集、验证集和测试集
2. THE `train_test_split_ts` Operator_Backend SHALL 保持数据的时间顺序不打乱，确保验证集和测试集的时间晚于训练集
3. THE `train_test_split_ts` Operator_Backend SHALL 支持通过 `split_date` 参数按指定日期切分（优先于比例切分）
4. THE `train_test_split_ts` Operator_Backend SHALL 实现与本地代码中 `model_prefer_trainer` 的训练/验证数据划分逻辑等价的功能

### 需求 15：模型训练算子填充 — auto_tune_xgboost

**用户故事：** 作为平台用户，我想使用通用的 `auto_tune_xgboost` 算子自动搜索 XGBoost 最优超参数，以便在负荷预测和其他回归任务中获得最佳模型性能。

#### 验收标准

1. WHEN 用户配置 `auto_tune_xgboost` 算子并提供 `train_features` 和 `train_target`, THE Operator_Backend SHALL 使用贝叶斯优化搜索 XGBoost 最优超参数（`n_estimators`、`max_depth`、`learning_rate`、`subsample`、`lambda`）
2. THE `auto_tune_xgboost` Operator_Backend SHALL 支持通过 `n_trials` 参数配置搜索次数（默认 50），通过 `metric` 参数配置优化指标（`rmse`/`mae`/`mape`）
3. THE `auto_tune_xgboost` Operator_Backend SHALL 支持通过 `cv_folds` 参数配置交叉验证折数（默认 5）
4. THE `auto_tune_xgboost` Operator_Backend SHALL 实现与本地代码 `xgb_model_trainer` 中贝叶斯优化（`BayesianOptimization`）等价的调参逻辑
5. THE `auto_tune_xgboost` Operator_Backend SHALL 返回最优参数和训练好的模型对象

### 需求 16：时序预测算子填充 — xgboost_forecast

**用户故事：** 作为平台用户，我想使用通用的 `xgboost_forecast` 算子进行 XGBoost 时序预测，以便在负荷预测、光伏预测等多种场景中复用同一个 XGBoost 预测能力。

#### 验收标准

1. WHEN 用户配置 `xgboost_forecast` 算子并提供 `train_features` 和 `train_target`, THE Operator_Backend SHALL 训练 XGBoost 模型并返回预测结果
2. WHEN `auto_tune` 参数为 `true`, THE Operator_Backend SHALL 自动调用贝叶斯优化搜索最优超参数后再训练模型
3. THE `xgboost_forecast` Operator_Backend SHALL 支持通过 `n_estimators` 参数配置树的数量（默认 100）
4. THE `xgboost_forecast` Operator_Backend SHALL 实现与本地代码 `model_prefer_trainer` 和 `LoadForecastWrapper.predict` 等价的训练和预测逻辑
5. THE `xgboost_forecast` Operator_Backend SHALL 返回预测值数组（ARRAY 类型）和训练好的模型对象，供下游评估算子使用
6. THE `xgboost_forecast` Operator_Backend SHALL 支持样本权重机制，与本地代码中 `sample_weigths` 的近期数据加权逻辑等价

### 需求 17：评估指标算子填充 — smape_score 和 mse_rmse_mae

**用户故事：** 作为平台用户，我想使用通用的评估指标算子计算 SMAPE、MSE、RMSE、MAE 等精度指标，以便在任意预测任务中量化评估模型效果。

#### 验收标准

1. WHEN 用户配置 `smape_score` 算子并提供 `y_true` 和 `y_pred`, THE Operator_Backend SHALL 计算对称平均绝对百分比误差（SMAPE），与本地代码 `utils.smape` 等价
2. WHEN 用户配置 `mse_rmse_mae` 算子并提供 `y_true` 和 `y_pred`, THE Operator_Backend SHALL 同时计算 MSE、RMSE 和 MAE 三个指标
3. THE `smape_score` Operator_Backend SHALL 返回 NUMBER 类型的 SMAPE 值（百分比形式）
4. THE `mse_rmse_mae` Operator_Backend SHALL 返回包含 `mse`、`rmse`、`mae` 三个键值对的结果
5. IF `y_true` 和 `y_pred` 长度不一致, THEN THE Operator_Backend SHALL 返回参数校验错误信息

### 需求 18：算子后端执行框架

**用户故事：** 作为平台开发者，我想建立统一的算子后端执行框架，以便所有通用算子的后端逻辑遵循一致的接口规范，支持快速填充新算子。

#### 验收标准

1. THE Workflow_Executor SHALL 提供统一的算子执行接口，每个算子后端实现一个标准的 `execute(params, inputs)` 函数，接收算子参数和上游数据，返回执行结果
2. THE Workflow_Executor SHALL 通过 Operator_Registry（`functions.json`）中的算子 ID 自动路由到对应的后端执行函数
3. WHEN 新的算子后端实现被注册, THE Workflow_Executor SHALL 在不修改框架代码的情况下自动发现并调用该实现
4. THE Workflow_Executor SHALL 在算子执行前校验输入数据类型是否与 `functions.json` 中定义的 `parameters` 类型匹配
5. IF 算子执行过程中抛出异常, THEN THE Workflow_Executor SHALL 捕获异常并返回包含算子 ID、错误类型和错误信息的标准化错误响应

### 需求 19：算子参数编辑面板

**用户故事：** 作为平台用户，我想在工作流编辑器中点击任意算子节点后编辑该算子的参数，以便根据实际业务需求定制每个算子的行为。

#### 验收标准

1. WHEN 用户在 Workflow_Editor 中双击或选中一个算子节点, THE Operator_Config_Panel SHALL 在编辑器右侧以侧边栏形式展示该算子的所有可配置参数
2. THE Operator_Config_Panel SHALL 根据 Operator_Registry 中的 `parameters` 定义自动生成参数编辑表单，支持 STRING、NUMBER、BOOLEAN、ARRAY 和 SELECT 类型
3. WHEN 用户修改参数并点击"保存"按钮, THE Operator_Config_Panel SHALL 将参数值写入该节点的 `config` 字段并持久化到工作流数据中
4. IF 用户未填写必填参数并尝试保存, THEN THE Operator_Config_Panel SHALL 高亮未填写的必填字段并展示校验错误提示
5. THE Operator_Config_Panel SHALL 为每个参数提供 tooltip 说明文字，鼠标悬停时展示参数的详细描述

### 需求 20：负荷预测流水线模板

**用户故事：** 作为平台用户，我想在工作流编辑器中一键加载负荷预测流水线模板，以便快速搭建由通用算子组成的完整预测工作流，且模板中每对相邻算子的输入输出格式已预定义并保证兼容。

#### 验收标准

1. THE Workflow_Editor SHALL 在模板列表中提供"负荷预测完整流水线"模板，该模板由以下通用算子按顺序组成：`load_csv` → `resample_timeseries` → `detect_outliers` → `handle_missing` → `extract_time_features` → `holiday_features` → `workday_features` → `rolling_statistics` → `create_lag_features` → `sliding_window` → `train_test_split_ts` → `multi_step_forecast` → `xgboost_forecast` → `smape_score` + `mse_rmse_mae`
2. WHEN 用户选择该模板, THE Workflow_Editor SHALL 自动在画布上创建所有算子节点并建立正确的数据流连线
3. THE Workflow_Editor SHALL 为模板中的每个算子节点预填充负荷预测场景的推荐默认参数值（如 `load_csv` 的 `timestamp_column` 预填 `record_time`，`resample_timeseries` 的 `frequency` 预填 `15min`）
4. WHEN 模板加载完成, THE Workflow_Editor SHALL 允许用户修改任意算子的参数、增删算子节点后再执行
5. THE Pipeline_Template SHALL 为每对相邻算子定义明确的 Data_Contract，指定以下数据流契约：
   - `load_csv` → `resample_timeseries`：输出 MATRIX，必含 `record_time`（datetime）列和 `load`（float）列
   - `resample_timeseries` → `detect_outliers`：输出 MATRIX，具有连续时间索引，数值列中缺失值为 NaN
   - `detect_outliers` → `handle_missing`：输出 MATRIX，异常值已替换为 NaN；附带 ARRAY 类型的异常索引列表
   - `handle_missing` → `extract_time_features`：输出 MATRIX，无 NaN 值，必含 `record_time`（datetime）列和 `load`（float）列
   - `extract_time_features` → `holiday_features` / `workday_features` / `rolling_statistics` / `create_lag_features`：输出 MATRIX，在输入基础上新增 `hour`（int）、`dayofweek`（int）、`month`（int）等时间特征列
   - 特征算子链输出 → `sliding_window`：输出 MATRIX（feat_df），包含所有特征列和 `load`（float）目标列
   - `sliding_window` → `train_test_split_ts`：输出 MATRIX，按滑动窗口切片后的样本数据，包含窗口化的特征列和目标列
   - `train_test_split_ts` → `multi_step_forecast`：输出 `train_features`（MATRIX）、`train_target`（ARRAY，float）、`test_features`（MATRIX）、`test_target`（ARRAY，float）
   - `multi_step_forecast` → `xgboost_forecast`：输出 OBJECT，包含 `forecast_config`（预测策略配置：strategy、forecast_steps、step_size）和透传的训练/测试数据
   - `xgboost_forecast` → `smape_score` / `mse_rmse_mae`：输出 `predictions`（ARRAY，float）和 `model`（OBJECT）；评估算子接收 `y_true`（ARRAY，float）和 `y_pred`（ARRAY，float）
6. WHEN 模板加载完成, THE Workflow_Editor SHALL 在每条连线上以 tooltip 形式展示该连线对应的 Data_Contract 摘要（包含传递的数据类型和关键列名）

### 需求 21：工作流逐节点执行

**用户故事：** 作为平台用户，我想在工作流编辑器中点击"执行"按钮后，系统按拓扑排序逐节点执行由通用算子组成的流水线，并实时展示每个节点的执行状态。

#### 验收标准

1. WHEN 用户在 Workflow_Editor 中点击"执行"按钮, THE Workflow_Executor SHALL 对工作流进行拓扑排序并按顺序逐节点调用对应的 Operator_Backend 执行
2. WHILE 一个算子节点正在执行, THE Workflow_Editor SHALL 将该节点的状态标记为"执行中"并展示加载动画
3. WHEN 一个算子节点执行完成, THE Workflow_Editor SHALL 将该节点标记为"已完成"状态并展示执行耗时
4. IF 一个算子节点执行失败, THEN THE Workflow_Editor SHALL 将该节点标记为"失败"状态，展示错误信息，并停止后续节点的执行
5. WHEN 所有节点执行完成, THE Workflow_Editor SHALL 展示整体执行结果摘要，包含总耗时和各节点耗时
6. THE Workflow_Executor SHALL 在相邻节点之间自动传递数据，上游节点的输出端口数据作为下游节点的输入端口数据

### 需求 22：算子执行结果预览

**用户故事：** 作为平台用户，我想在工作流执行后点击任意已完成的算子节点查看该节点的执行结果，以便了解每个步骤的中间产出。

#### 验收标准

1. WHEN 用户点击一个已完成执行的算子节点, THE Operator_Config_Panel SHALL 在结果标签页中展示该节点的执行结果摘要
2. THE Operator_Config_Panel SHALL 根据算子的 `return_type` 展示不同的结果视图：MATRIX 类型展示数据行数、列名和前 10 行预览；ARRAY 类型展示数组长度和前 20 个元素；NUMBER 类型直接展示数值
3. IF 算子节点的输出为 MATRIX 类型, THEN THE Operator_Config_Panel SHALL 以数据表格形式展示前 10 行数据预览

### 需求 23：算子执行日志

**用户故事：** 作为平台用户，我想在工作流执行过程中查看每个算子的详细执行日志，以便排查问题和了解执行细节。

#### 验收标准

1. WHILE Workflow_Executor 执行工作流, THE Workflow_Editor SHALL 在底部面板以日志控制台形式展示实时执行日志
2. WHEN 一个算子节点开始执行, THE Workflow_Editor SHALL 追加日志条目 `[HH:MM:SS] ▶ {算子名称} 开始执行...`
3. WHEN 一个算子节点执行完成, THE Workflow_Editor SHALL 追加日志条目 `[HH:MM:SS] ✓ {算子名称} 完成 (耗时 X.XXs)`
4. IF 一个算子节点执行失败, THEN THE Workflow_Editor SHALL 追加日志条目 `[HH:MM:SS] ✗ {算子名称} 失败: {错误信息}` 并以红色标记

### 需求 24：算子端口类型校验

**用户故事：** 作为平台用户，我想在连接两个算子时系统自动校验端口类型是否兼容，以便避免构建无效的工作流。

#### 验收标准

1. WHEN 用户尝试连接两个算子节点, THE Workflow_Editor SHALL 校验源节点的 `return_type` 与目标节点输入参数的 `type` 是否兼容
2. IF 端口类型不兼容, THEN THE Workflow_Editor SHALL 阻止连线创建并展示类型不匹配的提示信息
3. THE Workflow_Editor SHALL 支持以下端口数据类型：MATRIX（表格数据）、ARRAY（数组数据）、NUMBER（数值）、STRING（字符串）、OBJECT（模型对象或字典）
4. THE Workflow_Editor SHALL 在连线时以颜色区分不同的数据类型

### 需求 25：算子扩展机制

**用户故事：** 作为平台开发者，我想通过标准化的算子注册和填充机制添加新算子的后端实现，以便后续快速扩展更多算法场景（如光伏预测、风电预测等）。

#### 验收标准

1. THE Workflow_Executor SHALL 通过 Operator_Registry（`functions.json`）中的 Function 定义自动发现和注册算子，新增算子只需在 `functions.json` 中添加定义并在执行服务中实现对应的 `execute` 函数
2. THE Operator_Config_Panel SHALL 根据 Operator_Registry 中的 `parameters` 定义自动生成参数编辑表单，无需为每个算子编写专用的前端组件
3. THE Workflow_Editor SHALL 在左侧函数库面板中按 `category` 分组展示所有已注册的算子，用户可通过拖拽将算子添加到画布
4. WHEN 新的 Function 定义添加到 Operator_Registry, THE Workflow_Editor SHALL 在刷新后自动展示新算子，无需修改前端代码

### 需求 26：算子间数据契约规范与自动校验

**用户故事：** 作为平台用户，我想保证负荷预测流水线中每个算子的输出格式与下游算子的输入格式完全匹配，以便通过工作流方式搭建的负荷预测流程能够端到端运行，算子与算子之间的输入输出格式完全打通。

#### 验收标准

1. THE Workflow_Executor SHALL 为负荷预测流水线中的每对相邻算子定义形式化的 Data_Contract，每个 Data_Contract 包含以下字段：`required_columns`（必需列名列表）、`column_types`（列名到数据类型的映射）、`data_type`（MATRIX / ARRAY / NUMBER / OBJECT）、`constraints`（附加约束条件，如"无 NaN"、"时间有序"）
2. THE Workflow_Executor SHALL 定义以下具体的 Data_Contract 规范：
   - **load_csv 输出契约**：data_type=MATRIX，required_columns=[`record_time`, `load`]，column_types={`record_time`: datetime64, `load`: float64}，constraints=[按 `record_time` 升序排列, 无重复行]
   - **resample_timeseries 输出契约**：data_type=MATRIX，required_columns=[`record_time`, `load`]，column_types={`record_time`: datetime64, `load`: float64}，constraints=[时间索引连续且等间隔, 缺失时间点填充 NaN]
   - **detect_outliers 输出契约**：data_type=MATRIX + ARRAY，MATRIX 部分 required_columns=[`record_time`, `load`]，异常值位置已替换为 NaN；ARRAY 部分为异常点索引列表（int 类型）
   - **handle_missing 输出契约**：data_type=MATRIX，required_columns=[`record_time`, `load`]，column_types={`record_time`: datetime64, `load`: float64}，constraints=[所有数值列无 NaN]
   - **extract_time_features 输出契约**：data_type=MATRIX，required_columns=[`record_time`, `load`, `hour`, `dayofweek`, `month`]，column_types={`hour`: int, `dayofweek`: int, `month`: int}，constraints=[特征列合并到输入 DataFrame]
   - **holiday_features 输出契约**：data_type=MATRIX，在输入基础上新增 required_columns=[`is_holiday`]，column_types={`is_holiday`: int}
   - **workday_features 输出契约**：data_type=MATRIX，在输入基础上新增 required_columns=[`is_workday`]，column_types={`is_workday`: int}
   - **rolling_statistics 输出契约**：data_type=MATRIX，在输入基础上新增滚动统计列（如 `load_rolling_mean_24`、`load_rolling_std_24`），column_types={新增列: float64}
   - **create_lag_features 输出契约**：data_type=MATRIX，在输入基础上新增滞后列（如 `load_lag_1`、`load_lag_24`、`load_lag_168`），column_types={新增列: float64}
   - **sliding_window 输出契约**：data_type=MATRIX，按滑动窗口切片后的样本数据，required_columns=[输入特征列 + 目标列]，column_types={所有列: float64}，constraints=[窗口大小一致, 步长对齐, 无跨窗口数据泄露]
   - **multi_step_forecast 输出契约**：data_type=OBJECT，包含两个键：`forecast_config`（OBJECT，包含 `strategy`: string、`forecast_steps`: int、`step_size`: int）和透传的训练/测试数据（与上游输入一致），constraints=[forecast_steps > 0, strategy ∈ {recursive, direct, hybrid}]
   - **train_test_split_ts 输出契约**：data_type=OBJECT，包含四个键：`train_features`（MATRIX，float64 类型，不含目标列）、`train_target`（ARRAY，float64）、`test_features`（MATRIX，float64 类型，列名与 train_features 一致）、`test_target`（ARRAY，float64）
   - **xgboost_forecast 输出契约**：data_type=OBJECT，包含两个键：`predictions`（ARRAY，float64）、`model`（OBJECT，XGBoost 模型实例）
   - **smape_score 输出契约**：data_type=NUMBER，float64 类型，取值范围 [0, 200]
   - **mse_rmse_mae 输出契约**：data_type=OBJECT，包含三个键：`mse`（float64）、`rmse`（float64）、`mae`（float64）
3. WHEN 一个算子执行完成且存在下游算子, THE Schema_Validator SHALL 自动校验该算子的输出数据是否符合其输出 Data_Contract 定义，校验内容包括：必需列是否存在、列数据类型是否匹配、约束条件是否满足
4. IF Schema_Validator 校验发现输出数据不符合 Data_Contract, THEN THE Workflow_Executor SHALL 在传递数据给下游算子之前中止执行，并返回包含以下信息的错误：违规算子名称、期望的 Schema、实际的 Schema、具体的不匹配字段
5. THE Workflow_Executor SHALL 提供可选的 Data_Adapter（数据适配器）机制：WHEN 上游算子输出的列名与下游算子期望的列名存在可映射的对应关系（如 `timestamp` → `record_time`）, THE Data_Adapter SHALL 自动执行列名重映射，避免因列名差异导致流水线中断
6. THE Workflow_Executor SHALL 在 Data_Adapter 执行自动转换时记录转换日志，包含源列名、目标列名和转换规则，供用户在执行日志中查看
7. THE Schema_Validator SHALL 对 ARRAY 类型数据校验元素的数据类型和数组长度一致性（如 `y_true` 和 `y_pred` 长度相等）
8. THE Data_Contract 定义 SHALL 以 JSON 格式存储在 Pipeline_Template 的元数据中，每条连线关联一个 Data_Contract ID，支持用户在 Workflow_Editor 中查看和自定义

### 需求 27：负荷预测流水线端到端集成验证

**用户故事：** 作为平台用户，我想验证通过工作流编辑器搭建的负荷预测流水线能够从数据加载到评估指标输出完整运行，以便确认所有算子之间的数据格式已完全打通。

#### 验收标准

1. THE Workflow_Executor SHALL 提供"流水线预检"功能：WHEN 用户在 Workflow_Editor 中点击"预检"按钮, THE Workflow_Executor SHALL 使用小规模样本数据（前 100 行）按拓扑顺序逐节点执行，验证每对相邻算子之间的数据传递是否符合 Data_Contract
2. WHEN 预检执行完成, THE Workflow_Editor SHALL 展示预检报告，包含每对相邻算子之间的数据传递状态（通过/失败）、传递的数据 Schema 摘要（列名、类型、行数）和耗时
3. IF 预检过程中某对算子之间的数据传递失败, THEN THE Workflow_Editor SHALL 在对应的连线上标记红色警告图标，并在预检报告中展示具体的 Schema 不匹配详情
4. THE Workflow_Executor SHALL 提供"端到端集成测试"功能：WHEN 用户提供完整的负荷数据文件, THE Workflow_Executor SHALL 执行完整流水线并验证最终输出包含有效的 SMAPE 值（NUMBER 类型，取值范围 [0, 200]）和 MSE/RMSE/MAE 值（均为非负 NUMBER 类型）
5. WHEN 端到端集成测试完成, THE Workflow_Editor SHALL 展示完整的数据流追踪报告，包含每个算子的输入行数、输出行数、输出列名列表和执行耗时
6. THE Workflow_Executor SHALL 在端到端集成测试中验证以下关键数据流转换的正确性：
   - `load_csv` 输出的 DataFrame 行数大于 0 且包含 `record_time` 和 `load` 列
   - `resample_timeseries` 输出的时间索引间隔等于配置的 `frequency` 参数值
   - `handle_missing` 输出的 DataFrame 中 `load` 列无 NaN 值
   - `extract_time_features` 输出的 DataFrame 列数大于输入的 DataFrame 列数
   - `train_test_split_ts` 输出的 `train_features` 和 `test_features` 具有相同的列名集合
   - `xgboost_forecast` 输出的 `predictions` 数组长度等于 `test_target` 数组长度
   - `smape_score` 和 `mse_rmse_mae` 输出的数值为有限值（非 NaN、非 Inf）

### 需求 28：负荷预测算子人性化可配置参数

**用户故事：** 作为平台用户，我想在配置负荷预测流水线中的每个算子时看到清晰的中文参数标签、合理的默认值和直观的输入控件，以便无需查阅文档即可快速理解和调整算子行为。

#### 验收标准

1. THE Operator_Config_Panel SHALL 为负荷预测流水线中每个算子的参数提供中文标签（`label`）和中文描述（`description`），替代原始的英文参数名展示
2. THE Operator_Config_Panel SHALL 根据参数的值域类型自动匹配输入控件：枚举类型使用下拉选择框（Dropdown），数值范围类型使用滑块（Slider）配合数字输入框，布尔类型使用开关（Toggle），自由文本使用文本输入框
3. THE Operator_Config_Panel SHALL 将每个算子的参数分为"基础参数"和"高级参数"两组，基础参数默认展开，高级参数默认折叠，用户可点击展开
4. THE Operator_Config_Panel SHALL 为负荷预测流水线中的以下算子定义具体的 Humanized_Param 配置：
   - **load_csv**：`file_path`（标签：数据文件路径）、`timestamp_column`（标签：时间戳列名，默认 `record_time`）、`value_columns`（标签：数值列名列表）、`delimiter`（标签：分隔符，默认 `,`）、`encoding`（标签：文件编码，下拉选择 `utf-8`/`gbk`/`gb2312`）
   - **resample_timeseries**：`frequency`（标签：目标时间粒度，下拉选择 `5min`/`15min`/`30min`/`1H`/`1D`，默认 `15min`）、`method`（标签：聚合方法，下拉选择 `mean`/`sum`/`max`/`min`，默认 `mean`）
   - **detect_outliers**：`method`（标签：检测方法，下拉选择 `zscore`/`iqr`/`isolation_forest`，默认 `zscore`）、`threshold`（标签：异常阈值，滑块范围 1.0–10.0，默认 `6.0`）
   - **handle_missing**：`method`（标签：填充方法，下拉选择 `linear`/`ffill`/`bfill`/`mean`，默认 `linear`）
   - **extract_time_features**：`features`（标签：提取特征列表，多选复选框 `hour`/`dayofweek`/`month`/`day`/`quarter`/`is_holiday`，默认全选）
   - **rolling_statistics**：`window_sizes`（标签：滚动窗口大小列表，默认 `[24, 48, 96, 168]`）、`statistics`（标签：统计量类型，多选复选框 `mean`/`std`/`quantile`，默认 `mean` 和 `std`）
   - **create_lag_features**：`lags`（标签：滞后步数列表，默认 `[1, 24, 168]`）
   - **train_test_split_ts**：`train_ratio`（标签：训练集比例，滑块范围 0.5–0.9，默认 `0.8`）、`val_ratio`（标签：验证集比例，滑块范围 0.05–0.3，默认 `0.1`）、`split_date`（标签：指定切分日期，日期选择器，可选）
   - **xgboost_forecast**：`n_estimators`（标签：树的数量，滑块范围 50–500，默认 `200`）、`auto_tune`（标签：自动调参，开关，默认关闭）
   - **smape_score**：无额外可配置参数，面板展示算子说明文字"计算对称平均绝对百分比误差（SMAPE）"
5. THE Operator_Config_Panel SHALL 为每个参数的默认值提供"恢复默认"按钮，用户点击后将该参数重置为推荐默认值
6. WHEN 用户将鼠标悬停在参数标签上, THE Operator_Config_Panel SHALL 以 tooltip 形式展示该参数的详细中文描述和取值建议
7. THE Operator_Config_Panel SHALL 对数值类型参数进行输入范围校验：WHEN 用户输入超出合理范围的值, THE Operator_Config_Panel SHALL 展示红色边框和校验错误提示（如"`threshold` 取值范围为 1.0–10.0"）

### 需求 29：通过 options 扩展承载负荷预测业务参数

**用户故事：** 作为平台用户，我想在通用算子上配置负荷预测特有的业务参数（如预测场景类型、预测时长、时区等），以便在不修改通用算子定义的前提下灵活适配负荷预测的业务需求，同时保持算子对其他算法场景的通用性。

#### 验收标准

1. THE Operator_Config_Panel SHALL 为每个算子的 `options` 参数渲染一个可折叠的"业务参数"（Domain_Options）配置区域，默认折叠，用户点击"业务参数"标题可展开编辑
2. THE Operator_Config_Panel SHALL 根据当前流水线模板的 Options_Schema 定义，将 `options` JSON 字符串解析为结构化表单字段，每个字段具有中文标签、输入控件和默认值
3. WHEN 用户从负荷预测流水线模板加载工作流, THE Pipeline_Template SHALL 为每个算子的 `options` 字段预填充以下负荷预测场景的默认值：
   - **load_csv** options：`{"time_field": "record_time", "load_field": "load", "parent_field": "parent_id", "child_field": "child_id", "parent_id": "", "child_id": ""}`
   - **resample_timeseries** options：`{"task_type": "D", "time_granularity": "15min", "time_field": "record_time", "load_field": "load"}`
   - **detect_outliers** options：`{"load_field": "load", "window_size": 96}`
   - **handle_missing** options：`{"time_field": "record_time", "load_field": "load"}`
   - **extract_time_features** options：`{"time_zone": "Asia/Shanghai", "task_type": "D", "forecast_start_time": "00:15"}`
   - **holiday_features** options：`{"remove_spring_festival": true}`
   - **rolling_statistics** options：`{"target_column": "load", "window_sizes": [24, 48, 96, 168]}`
   - **create_lag_features** options：`{"target_column": "load", "lag_periods": [1, 24, 168]}`
   - **train_test_split_ts** options：`{"time_field": "record_time", "target_column": "load", "task_type": "D"}`
   - **xgboost_forecast** options：`{"task_type": "D", "separate_modeling": "true", "sample_weight_decay": 0.99}`
4. THE Operator_Config_Panel SHALL 为 Domain_Options 中的每个字段提供中文标签和描述：
   - `task_type`：标签"预测场景"，下拉选择 `DI`（日内）/ `D`（日前）/ `WI`（周内）/ `W`（周前）/ `MI`（月内）/ `M`（月前），默认 `D`
   - `time_granularity`：标签"时间粒度"，下拉选择 `5min`/`15min`/`30min`/`1H`/`1D`，默认 `15min`
   - `time_zone`：标签"时区"，下拉选择常用时区，默认 `Asia/Shanghai`
   - `time_field`：标签"时间戳字段名"，文本输入框，默认 `record_time`
   - `load_field`：标签"负荷字段名"，文本输入框，默认 `load`
   - `target_column`：标签"目标列名"，文本输入框，默认 `load`
   - `separate_modeling`：标签"分开建模（工作日/休息日）"，开关，默认开启
   - `sample_weight_decay`：标签"样本权重衰减系数"，滑块范围 0.9–1.0，默认 `0.99`
   - `remove_spring_festival`：标签"剔除春节数据"，开关，默认开启
   - `window_size`：标签"滚动窗口大小"，数字输入框，默认 `96`
   - `forecast_start_time`：标签"预测起始时刻"，时间选择器，默认 `00:15`
   - `parent_field`：标签"父节点字段"，文本输入框，默认 `parent_id`
   - `child_field`：标签"子节点字段"，文本输入框，默认 `child_id`
5. WHEN 用户修改 Domain_Options 表单中的字段值并保存, THE Operator_Config_Panel SHALL 将所有字段序列化为 JSON 字符串并写入该算子节点的 `options` 参数
6. THE Operator_Backend SHALL 在执行算子时解析 `options` JSON 字符串，提取业务参数并用于定制算子的执行行为（如 `resample_timeseries` 根据 `task_type` 决定重采样策略，`xgboost_forecast` 根据 `separate_modeling` 决定是否分工作日/休息日建模）
7. THE Options_Schema SHALL 支持扩展：WHEN 新的算法场景（如光伏预测、风电预测）需要不同的业务参数, THE Options_Schema SHALL 允许在 Pipeline_Template 元数据中定义新的 Options_Schema 而无需修改通用算子的 `functions.json` 定义
8. WHEN 用户切换 `task_type` 业务参数的值, THE Operator_Config_Panel SHALL 根据所选场景自动更新关联参数的推荐默认值（如选择 `DI` 场景时 `separate_modeling` 默认关闭，选择 `D` 场景时 `separate_modeling` 默认开启），与 `common/constants.py` 中 `SCENARIO_CONFIGS` 的场景配置一致

### 需求 30：工作流执行时的训练过程可视化

**用户故事：** 作为平台用户，我想在工作流编辑器中执行负荷预测流水线时实时查看各算子的执行进度和详细日志，以便直观了解流水线的运行状态和每个算子的执行情况。

> 参考设计：本需求复用 `load-forecast-training-ui` 规格中 ProgressTracker（Steps 步骤条组件）和 LogConsole（深色终端日志面板）的设计模式，将其适配到工作流编辑器的执行上下文中。

#### 验收标准

1. WHEN 用户在 Workflow_Editor 中点击"执行"按钮启动负荷预测流水线, THE Workflow_Editor SHALL 在底部面板或侧边面板中展示 Pipeline_Progress_Tracker 组件，以步骤条形式展示流水线中所有算子节点的执行状态（等待中 / 执行中 / 已完成 / 失败）
2. WHILE Workflow_Executor 逐节点执行流水线, THE Pipeline_Progress_Tracker SHALL 每 2 秒轮询执行状态，将当前正在执行的算子节点标记为"执行中"状态并展示加载动画，将已完成的算子节点标记为"已完成"状态并展示该节点的执行耗时
3. THE Workflow_Editor SHALL 在 Pipeline_Progress_Tracker 下方展示 Pipeline_Log_Console 组件，采用深色背景、等宽字体的终端风格面板（与 `load-forecast-training-ui` 中 LogConsole 组件的视觉风格一致）
4. WHEN 一个算子节点开始执行, THE Pipeline_Log_Console SHALL 追加带时间戳的日志条目 `[HH:MM:SS] ▶ {算子名称} 开始执行...`，以高亮颜色标记
5. WHEN 一个算子节点执行完成, THE Pipeline_Log_Console SHALL 追加日志条目 `[HH:MM:SS] ✓ {算子名称} 完成 (耗时 X.XXs)`，以绿色标记
6. IF 一个算子节点执行失败, THEN THE Pipeline_Log_Console SHALL 追加日志条目 `[HH:MM:SS] ✗ {算子名称} 失败: {错误信息}`，以红色标记
7. THE Pipeline_Log_Console SHALL 在流水线执行开始时展示执行配置摘要，包含流水线模板名称、算子总数和关键业务参数（如 `task_type`、`forecast_steps`）
8. THE Pipeline_Log_Console SHALL 支持自动滚动到最新日志条目，用户手动滚动查看历史日志时暂停自动滚动
9. WHEN 流水线执行完成或失败, THE Pipeline_Progress_Tracker SHALL 停止状态轮询并展示最终执行状态摘要（总耗时、成功/失败算子数量）

### 需求 31：工作流执行结果仪表盘与回测

**用户故事：** 作为平台用户，我想在负荷预测流水线执行完成后查看详细的执行结果（包括耗时统计、模型信息、评估指标）并快速发起回测验证，以便评估模型效果并决定是否投入使用。

> 参考设计：本需求复用 `load-forecast-training-ui` 规格中 ResultDashboard（结果仪表盘）、MetricsChart（ECharts 图表）和 TrainingHistory（训练历史）的设计模式，将其适配到工作流编辑器的执行结果展示上下文中。

#### 验收标准

1. WHEN 负荷预测流水线执行成功完成, THE Workflow_Editor SHALL 在执行面板中展示 Pipeline_Result_Dashboard 组件，包含以下信息：总执行时间、流水线模板名称、执行完成时间
2. THE Pipeline_Result_Dashboard SHALL 以水平条形图（使用 ECharts 渲染）展示每个算子节点的执行耗时分布
3. THE Pipeline_Result_Dashboard SHALL 以饼图或环形图（使用 ECharts 渲染）展示各算子耗时占总执行时间的百分比
4. WHEN 流水线中包含 `xgboost_forecast` 算子且该算子执行成功, THE Pipeline_Result_Dashboard SHALL 展示模型信息区域，包含 `model_id` 和"复制 Model ID"按钮，点击后将 `model_id` 复制到系统剪贴板
5. WHEN 流水线中包含 `smape_score` 和 `mse_rmse_mae` 评估算子且执行成功, THE Pipeline_Result_Dashboard SHALL 展示评估指标区域，以卡片形式展示 SMAPE、MAE、RMSE 数值
6. WHEN 流水线执行成功且包含模型训练算子, THE Pipeline_Result_Dashboard SHALL 展示"快速回测"按钮
7. WHEN 用户点击"快速回测"按钮, THE Workflow_Editor SHALL 调用 `POST /api/load-forecast/backtest` 并传递流水线执行时使用的参数和日期范围，发起回测验证
8. WHEN 回测完成, THE Pipeline_Result_Dashboard SHALL 以折线图（使用 ECharts 渲染）展示每日预测值与实际值的对比曲线
9. WHEN 回测完成, THE Pipeline_Result_Dashboard SHALL 以柱状图（使用 ECharts 渲染）展示每日回测的预测点数量分布
10. WHEN 回测完成, THE Pipeline_Result_Dashboard SHALL 展示回测汇总统计信息：成功天数、跳过天数、失败天数、总回测耗时
11. THE Workflow_Editor SHALL 在执行面板中维护当前会话的流水线执行历史记录列表，展示每次执行的执行 ID、流水线模板名称、执行状态、model_id（如有）和总耗时
12. WHEN 用户点击执行历史记录中的某条记录, THE Workflow_Editor SHALL 自动将该次执行使用的算子参数配置回填到工作流画布中对应的算子节点，允许用户基于历史配置重新执行
13. IF 流水线执行失败, THEN THE Pipeline_Result_Dashboard SHALL 展示失败算子名称和错误信息，以红色警告样式呈现

### 需求 32：负荷预测推理流水线模板

**用户故事：** 作为平台用户，我想在工作流编辑器中一键加载负荷预测推理流水线模板，以便使用已训练好的模型对未来负荷进行预测，且推理流水线复用训练流水线中相同的通用算子和数据契约。

#### 验收标准

1. THE Workflow_Editor SHALL 在模板列表中提供"负荷预测推理流水线"模板，该模板由以下通用算子按顺序组成：`load_csv` → `resample_timeseries` → `detect_outliers` → `handle_missing` → `extract_time_features` → `holiday_features` → `workday_features` → `rolling_statistics` → `create_lag_features` → `sliding_window` → `multi_step_forecast` → `xgboost_forecast`（预测模式）→ 后处理输出
2. WHEN 用户选择该模板, THE Workflow_Editor SHALL 自动在画布上创建所有算子节点并建立正确的数据流连线，与训练流水线模板中共享算子的连线和 Data_Contract 保持一致
3. THE Prediction_Pipeline_Template SHALL 要求用户提供 `model_id` 参数，用于加载已训练好的模型；WHEN `model_id` 为空或对应模型不存在, THE Workflow_Executor SHALL 在执行前返回参数校验错误
4. THE `xgboost_forecast` Operator_Backend SHALL 支持 `mode` 参数区分训练模式和预测模式：WHEN `mode` 为 `predict`, THE Operator_Backend SHALL 加载 `model_id` 指定的已训练模型执行推理，而非重新训练
5. THE Prediction_Pipeline_Template SHALL 为推理流水线中每个算子的 `options` 字段预填充与训练流水线一致的负荷预测场景默认值，并额外包含 `model_id` 参数
6. THE Prediction_Pipeline_Template 中共享算子（`load_csv`、`resample_timeseries`、`detect_outliers`、`handle_missing`、`extract_time_features`、`holiday_features`、`workday_features`、`rolling_statistics`、`create_lag_features`、`sliding_window`、`multi_step_forecast`）的 Data_Contract 定义 SHALL 与训练流水线模板（需求 20）中的定义完全一致，确保同一算子在训练和推理场景下的输入输出格式相同
7. THE `xgboost_forecast` 算子在预测模式下的输出契约 SHALL 为：data_type=OBJECT，包含 `forecast_timestamps`（ARRAY，string 类型，格式 `YYYY-MM-DD HH:MM:SS`）和 `forecast_values`（ARRAY，float64 类型）
8. THE Prediction_Pipeline_Template SHALL 为推理流水线中的 Humanized_Param 配置复用训练流水线（需求 28）中相同算子的中文标签、描述文字、默认值和输入控件类型
9. THE Operator_Config_Panel SHALL 为推理流水线中的 `xgboost_forecast` 算子额外展示以下预测模式专属参数：`model_id`（标签：模型 ID，文本输入框，必填）、`mode`（标签：运行模式，下拉选择 `train`/`predict`，默认 `predict`）
10. THE Operator_Config_Panel SHALL 为推理流水线中的 Domain_Options 复用训练流水线（需求 29）中相同算子的 Options_Schema 定义和中文标签

### 需求 33：负荷预测推理过程可视化与结果展示

**用户故事：** 作为平台用户，我想在推理流水线执行过程中实时查看各算子的执行进度和日志，并在推理完成后查看预测结果曲线和模型信息，以便直观了解推理过程和预测产出。

> 参考设计：本需求复用需求 30 中 Pipeline_Progress_Tracker 和 Pipeline_Log_Console 的设计模式，并扩展 Prediction_Result_Dashboard 展示推理特有的结果内容。

#### 验收标准

1. WHEN 用户在 Workflow_Editor 中执行推理流水线, THE Pipeline_Progress_Tracker SHALL 以步骤条形式展示推理流水线中所有算子节点的实时执行状态（等待中 / 执行中 / 已完成 / 失败），复用需求 30 中的进度追踪设计
2. WHILE Workflow_Executor 逐节点执行推理流水线, THE Pipeline_Log_Console SHALL 以深色终端风格面板展示带时间戳的算子执行日志，日志格式和颜色标记规则与需求 30 中的训练流水线日志一致
3. WHEN 推理流水线执行成功完成, THE Prediction_Result_Dashboard SHALL 展示以下基本信息：总执行时间、使用的 `model_id`、执行完成时间
4. THE Prediction_Result_Dashboard SHALL 以折线图（使用 ECharts 渲染）展示预测曲线，X 轴为 `forecast_timestamps`（时间戳），Y 轴为 `forecast_values`（预测值），图表支持缩放和数据点悬停查看具体数值
5. THE Prediction_Result_Dashboard SHALL 以数据表格形式展示预测结果明细，包含时间戳列和预测值列，支持分页浏览
6. THE Prediction_Result_Dashboard SHALL 展示模型信息区域，包含所用 `model_id` 和"复制 Model ID"按钮
7. THE Prediction_Result_Dashboard SHALL 提供"导出预测结果"按钮，WHEN 用户点击该按钮, THE Prediction_Result_Dashboard SHALL 将 `forecast_timestamps` 和 `forecast_values` 导出为 CSV 文件供用户下载
8. THE Prediction_Result_Dashboard SHALL 以水平条形图（使用 ECharts 渲染）展示推理流水线中每个算子节点的执行耗时分布
9. IF 推理流水线执行失败, THEN THE Prediction_Result_Dashboard SHALL 展示失败算子名称和错误信息，以红色警告样式呈现

### 需求 34：负荷预测回测流水线模板

**用户故事：** 作为平台用户，我想在工作流编辑器中一键加载负荷预测回测流水线模板，以便按日期范围循环执行"训练 → 预测"流程，系统化评估模型在历史数据上的预测精度。

#### 验收标准

1. THE Workflow_Editor SHALL 在模板列表中提供"负荷预测回测流水线"模板，该模板为高层编排模板，内部按日期循环执行训练子流水线和推理子流水线
2. THE Backtest_Pipeline_Template SHALL 要求用户配置以下回测专属参数：`start_date`（标签：回测开始日期，日期选择器，必填）、`end_date`（标签：回测结束日期，日期选择器，必填）
3. THE Backtest_Pipeline_Template SHALL 同时包含训练流水线和推理流水线的全部算子参数配置，用户可在回测模板中统一配置所有参数（场景类型、数据源、特征工程参数等）
4. WHEN 用户选择回测模板, THE Workflow_Editor SHALL 在画布上展示回测流水线的整体结构：日期循环节点 → 训练子流水线（`load_csv` → ... → `xgboost_forecast` 训练模式）→ 推理子流水线（`load_csv` → ... → `xgboost_forecast` 预测模式）→ 结果收集节点
5. THE Workflow_Executor SHALL 按日期范围（`start_date` 到 `end_date`）逐日循环执行：每日先执行训练子流水线生成当日模型，再执行推理子流水线使用当日模型进行预测，收集每日的预测结果
6. THE Workflow_Executor SHALL 为每日执行收集以下结果：日期（`date`）、执行状态（`success` / `skipped` / `failed`）、执行耗时（`duration_seconds`）、预测时间戳数组（`forecast_timestamps`）、预测值数组（`forecast_values`）、预测点数量（`point_count`）
7. IF 某日训练数据不满足最低要求, THEN THE Workflow_Executor SHALL 将该日标记为 `skipped` 状态并记录跳过原因，继续执行下一日
8. IF 某日训练或预测过程中发生异常, THEN THE Workflow_Executor SHALL 将该日标记为 `failed` 状态并记录错误信息，继续执行下一日
9. WHEN 所有日期执行完成, THE Workflow_Executor SHALL 汇总回测结果，包含：总天数、成功天数、跳过天数、失败天数、总回测耗时
10. THE Backtest_Pipeline_Template 中训练子流水线和推理子流水线的算子 SHALL 复用需求 20 和需求 32 中定义的 Data_Contract、Humanized_Param 和 Domain_Options 配置
11. IF `start_date` 晚于 `end_date` 或日期范围为空, THEN THE Workflow_Executor SHALL 在执行前返回参数校验错误

### 需求 35：负荷预测回测过程可视化与结果展示

**用户故事：** 作为平台用户，我想在回测流水线执行过程中实时查看整体进度和每日执行详情，并在回测完成后查看全面的评估指标和可视化图表，以便系统化评估模型的预测精度并对比不同参数配置的效果。

> 参考设计：本需求复用需求 30 中 Pipeline_Progress_Tracker 和 Pipeline_Log_Console 的设计模式，并扩展 Backtest_Result_Dashboard 展示回测特有的多维度结果内容。

#### 验收标准

1. WHEN 用户在 Workflow_Editor 中执行回测流水线, THE Pipeline_Progress_Tracker SHALL 展示双层进度：外层展示整体回测进度（第 X 天 / 共 N 天），内层展示当前日期的子流水线算子执行状态
2. WHILE Workflow_Executor 逐日执行回测, THE Pipeline_Log_Console SHALL 展示分日的执行日志，每日日志以分隔线和日期标题区分，格式为 `══════ 第 X 天 / 共 N 天：YYYY-MM-DD ══════`
3. WHEN 某日训练子流水线开始执行, THE Pipeline_Log_Console SHALL 追加日志 `[HH:MM:SS] ▶ [YYYY-MM-DD] 训练阶段开始...`
4. WHEN 某日推理子流水线开始执行, THE Pipeline_Log_Console SHALL 追加日志 `[HH:MM:SS] ▶ [YYYY-MM-DD] 推理阶段开始...`
5. WHEN 某日执行完成, THE Pipeline_Log_Console SHALL 追加日志 `[HH:MM:SS] ✓ [YYYY-MM-DD] 完成 (耗时 X.XXs, 预测点数 N)`，以绿色标记
6. IF 某日被跳过, THEN THE Pipeline_Log_Console SHALL 追加日志 `[HH:MM:SS] ⊘ [YYYY-MM-DD] 跳过: {原因}`，以黄色标记
7. IF 某日执行失败, THEN THE Pipeline_Log_Console SHALL 追加日志 `[HH:MM:SS] ✗ [YYYY-MM-DD] 失败: {错误信息}`，以红色标记
8. WHEN 回测流水线执行完成, THE Backtest_Result_Dashboard SHALL 展示回测汇总统计卡片：总天数、成功天数、跳过天数、失败天数、总回测耗时
9. THE Backtest_Result_Dashboard SHALL 以折线图（使用 ECharts 渲染）展示每日预测值与实际值的对比曲线，X 轴为时间戳，Y 轴为负荷值，预测值和实际值分别以不同颜色的折线展示，图表支持按日期范围缩放
10. THE Backtest_Result_Dashboard SHALL 以柱状图（使用 ECharts 渲染）展示每日预测点数量分布，X 轴为日期，Y 轴为预测点数量
11. THE Backtest_Result_Dashboard SHALL 以数据表格形式展示逐日明细，包含以下列：日期、执行状态（以颜色标签区分 success/skipped/failed）、执行耗时、预测点数量，表格支持按状态筛选和按日期排序
12. THE Backtest_Result_Dashboard SHALL 展示评估指标区域，计算并展示以下精度指标：
    - 逐日 SMAPE 值，以折线图展示趋势
    - 逐日 MAE 值，以折线图展示趋势
    - 逐日 RMSE 值，以折线图展示趋势
    - 整体平均 SMAPE、平均 MAE、平均 RMSE，以数值卡片形式展示
13. THE Backtest_Result_Dashboard SHALL 提供"导出回测报告"按钮，WHEN 用户点击该按钮, THE Backtest_Result_Dashboard SHALL 将回测汇总统计、逐日明细和评估指标导出为 CSV 文件供用户下载
14. THE Workflow_Editor SHALL 在回测执行历史记录中保存每次回测的参数配置和结果摘要，WHEN 用户点击历史记录中的某条回测记录, THE Workflow_Editor SHALL 自动回填该次回测使用的全部参数配置（包含 `start_date`、`end_date` 和所有算子参数）
15. IF 回测流水线执行过程中所有日期均失败或被跳过, THEN THE Backtest_Result_Dashboard SHALL 展示警告信息"回测无有效结果"并建议用户检查数据源和参数配置

### 需求 36：时序预测算子填充 — multi_step_forecast

**用户故事：** 作为平台用户，我想使用通用的 `multi_step_forecast` 算子配置预测步长和预测策略（递归/直接/混合），以便在负荷预测、光伏预测等多种时序预测场景中灵活控制预测多少步以及采用何种多步预测方法。

> 说明：`multi_step_forecast` 是 `functions.json` 中 `ts_forecast` 类别下已注册的通用算子。负荷预测代码中的 step 配置是一个跨层概念：`resample_timeseries` 决定时间粒度（如 15min vs 1h），`sliding_window` 决定输入窗口大小，`multi_step_forecast` 决定预测多少步。将 `forecast_horizon` 从 Domain_Options 中移出，映射到此通用算子的标准参数，使预测步长配置可被任意算法场景复用。

#### 验收标准

1. WHEN 用户配置 `multi_step_forecast` 算子并指定 `forecast_steps` 参数, THE Operator_Backend SHALL 将预测步数配置注入下游预测算子的执行上下文中，控制模型预测的输出长度
2. THE `multi_step_forecast` Operator_Backend SHALL 支持 `strategy` 参数配置预测策略，可选值为 `recursive`（递归预测：逐步预测，将上一步预测值作为下一步输入）、`direct`（直接预测：为每个预测步训练独立模型）、`hybrid`（混合预测：结合递归和直接策略），默认 `recursive`
3. THE `multi_step_forecast` Operator_Backend SHALL 支持 `step_size` 参数配置每步对应的时间单位数量（如 `step_size=1` 表示每步预测 1 个时间粒度的数据点），默认 `1`
4. THE `multi_step_forecast` Operator_Backend SHALL 输出 OBJECT 类型数据，包含 `forecast_config`（预测策略配置对象，含 `strategy`、`forecast_steps`、`step_size` 三个字段）和透传的上游训练/测试数据
5. WHEN `strategy` 为 `recursive`, THE Operator_Backend SHALL 配置下游预测算子以逐步迭代方式生成多步预测，每步使用前一步的预测结果作为输入特征
6. WHEN `strategy` 为 `direct`, THE Operator_Backend SHALL 配置下游预测算子为每个预测步独立训练模型，各步预测互不依赖
7. WHEN `strategy` 为 `hybrid`, THE Operator_Backend SHALL 配置下游预测算子将预测步分组，组内使用递归策略，组间使用直接策略
8. IF `forecast_steps` 参数值小于等于 0, THEN THE Operator_Backend SHALL 返回参数校验错误信息
9. THE `multi_step_forecast` Operator_Backend SHALL 与 `resample_timeseries` 的时间粒度配置协同工作：预测的实际时间跨度 = `forecast_steps` × `step_size` × 时间粒度（如 `forecast_steps=96`、`step_size=1`、时间粒度=15min 表示预测未来 24 小时）

### 需求 37：数据预处理算子填充 — sliding_window

**用户故事：** 作为平台用户，我想使用通用的 `sliding_window` 算子将时序数据按滑动窗口方式切片为模型输入样本，以便在负荷预测、光伏预测等多种时序预测场景中灵活控制输入窗口大小和滑动步长。

> 说明：`sliding_window` 是 `functions.json` 中 `data_preprocessing` 类别下已注册的通用算子。负荷预测代码中的输入窗口配置是跨层概念"step 配置"的输入窗口维度：`sliding_window` 决定用多少历史数据点作为模型的一次输入。将窗口大小和步长从隐式的代码逻辑中提取为显式的算子参数，使输入窗口配置可被任意算法场景复用。

#### 验收标准

1. WHEN 用户配置 `sliding_window` 算子并指定 `window_size` 参数, THE Operator_Backend SHALL 将输入时序数据按指定窗口大小进行滑动窗口切片，生成多个等长的样本窗口
2. THE `sliding_window` Operator_Backend SHALL 支持 `step_size` 参数配置滑动步长（即相邻窗口之间的偏移量），默认 `1`（逐点滑动）
3. THE `sliding_window` Operator_Backend SHALL 支持 `target_column` 参数指定目标列名（如 `load`），用于区分特征列和目标列，确保窗口切片时正确分离输入特征和预测目标
4. THE `sliding_window` Operator_Backend SHALL 输出 MATRIX 类型数据，每行代表一个窗口化的样本，列包含窗口内的所有特征值和对应的目标值
5. THE `sliding_window` Operator_Backend SHALL 确保窗口切片过程中不发生未来数据泄露：每个样本窗口仅包含该时间点及之前的历史数据
6. IF `window_size` 参数值大于输入数据的总行数, THEN THE Operator_Backend SHALL 返回参数校验错误信息，提示窗口大小超过可用数据量
7. IF `window_size` 参数值小于等于 0, THEN THE Operator_Backend SHALL 返回参数校验错误信息
8. THE `sliding_window` Operator_Backend SHALL 丢弃因窗口切片产生的不完整样本（即数据头部不足一个完整窗口的部分），确保输出的每个样本均为完整窗口
9. THE `sliding_window` Operator_Backend SHALL 与 `resample_timeseries` 的时间粒度配置协同工作：窗口的实际时间跨度 = `window_size` × 时间粒度（如 `window_size=96`、时间粒度=15min 表示使用过去 24 小时的数据作为输入窗口）
<!-- @AI_GENERATED: end -->