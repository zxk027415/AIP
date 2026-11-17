<!-- @AI_GENERATED -->
# 实施计划：基于 AIP 通用算子填充实现负荷预测流水线

## 概述

本实施计划将设计文档中的技术方案转化为可执行的编码任务。后端使用 Python（FastAPI + pandas + XGBoost），前端使用 TypeScript（React + Ant Design + ECharts + zustand）。核心思路是先搭建算子执行框架，再逐步填充各算子后端逻辑，然后实现前端组件和流水线模板，最后进行端到端集成。

## 任务

- [x] 1. 搭建算子执行框架与核心基础设施
  - [x] 1.1 创建 `AIP-service/backend/services/operator_execution/` 目录结构，实现 `OperatorRouter`（算子路由器）
    - 创建 `router.py`，实现 `_registry` 字典、`register()`、`auto_discover()`、`execute()`、`has_operator()` 方法
    - `auto_discover()` 扫描 `operator_backends/` 目录下所有 Python 模块，自动注册导出 `OPERATOR_ID` 和 `execute` 函数的模块
    - _需求: 18.1, 18.2, 18.3_

  - [x] 1.2 实现 `SchemaValidator`（Schema 校验器）和 `DataContract` 数据模型
    - 创建 `schema_validator.py`，实现 `DataContract` dataclass、`SchemaValidator` 类
    - `validate_output()` 校验必需列、列数据类型、约束条件（no_nan、time_ordered、continuous_index 等）
    - `check_array_consistency()` 校验两个数组长度一致性
    - _需求: 18.4, 26.1, 26.3, 26.4, 26.7_

  - [x] 1.3 实现 `DataAdapter`（数据适配器）
    - 创建 `data_adapter.py`，实现列名重映射逻辑
    - `adapt()` 方法根据 source/target DataContract 自动执行列名映射
    - 记录转换日志（源列名、目标列名、转换规则）
    - _需求: 26.5, 26.6_

  - [x] 1.4 实现 `GlobalConfigInjector`（全局配置注入器）
    - 创建 `global_config_injector.py`，从 `metadata.global_config` 读取 `time_zone`/`operate_status`/`nowtime`
    - `inject()` 方法将全局配置合并到算子 params 中，不覆盖算子自身已有的同名参数
    - _需求: 工作流全局配置设计_

  - [x] 1.5 创建 `DataContractRegistry`（数据契约注册表）
    - 创建 `data_contracts.py`，定义 `LOAD_FORECAST_CONTRACTS` 字典，包含所有 16 个数据契约定义
    - 每个契约包含 `contract_id`、`data_type`、`required_columns`、`column_types`、`constraints`、`description`
    - _需求: 26.1, 26.2, 26.8_

  - [x] 1.6 创建算子后端基类和统一接口
    - 创建 `AIP-service/backend/services/operator_backends/base.py`，定义 `OPERATOR_ID` 和 `execute(params, inputs)` 接口规范
    - 定义 `OperatorExecutionError` 异常类
    - _需求: 18.1, 18.5_

  - [ ]* 1.7 为算子执行框架编写属性测试
    - **Property 17: 算子路由正确性** — 已注册算子 ID 正确路由，未注册 ID 返回错误
    - **Validates: Requirements 18.2**
    - **Property 18: Schema 校验捕获违规** — 缺少必需列、类型不匹配、约束违反时返回失败
    - **Validates: Requirements 26.3, 26.4, 26.7**
    - **Property 25: 全局配置注入正确性** — 注入后包含全局配置字段，不覆盖已有同名参数
    - **Validates: 工作流全局配置设计**

  - [ ]* 1.8 为算子执行框架编写单元测试
    - 测试 OperatorRouter 的注册、发现、路由逻辑
    - 测试 SchemaValidator 的各种校验场景
    - 测试 DataAdapter 的列名映射和日志记录
    - 测试 GlobalConfigInjector 的注入和不覆盖逻辑
    - _需求: 18.1–18.5, 26.1–26.8_

- [x] 2. Checkpoint — 确保框架基础设施测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 3. 实现数据源算子后端
  - [x] 3.1 实现 `load_csv` 算子后端
    - 创建 `operator_backends/load_csv.py`，复用 `pd.read_csv`
    - 支持 `file_path`、`timestamp_column`、`value_columns`、`delimiter`、`encoding`、`header_row` 参数
    - 高级参数：`parent_field`/`child_field`/`parent_id`/`child_id` 用于数据过滤
    - 输出按 `timestamp_column` 排序并去重
    - 文件不存在或格式错误时返回标准化错误信息
    - _需求: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 3.2 实现 `load_database` 算子后端
    - 创建 `operator_backends/load_database.py`
    - 支持 `mysql`/`postgresql`/`sqlite` 三种数据库类型
    - 连接失败或 SQL 错误时返回错误信息并关闭连接
    - 查询结果按时间戳列排序
    - _需求: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.3 实现 `load_api` 算子后端
    - 创建 `operator_backends/load_api.py`
    - 支持 GET/POST 请求，支持 `headers`/`body` 参数
    - 非 2xx 状态码或解析失败时返回错误信息
    - _需求: 3.1, 3.2, 3.3_

  - [x] 3.4 实现 `row_filter` 算子后端
    - 创建 `operator_backends/row_filter.py`
    - 支持 `column_filters`（精确匹配）和 `expression`（pandas query 表达式）两种过滤方式
    - 保留原始列结构
    - _需求: 29.1（parent_field/child_field 过滤场景）_

  - [ ]* 3.5 为数据源算子编写属性测试
    - **Property 1: load_csv 输出排序、去重与列过滤** — 输出按时间戳升序、无重复行、仅含指定列
    - **Validates: Requirements 1.3, 1.6**
    - **Property 24: row_filter 过滤正确性** — 输出仅含满足条件的行，保留原始列结构
    - **Validates: Requirements 29.1**

  - [ ]* 3.6 为数据源算子编写单元测试
    - `load_csv`：文件不存在、空文件、不同编码/分隔符
    - `load_database`：连接失败、SQL 错误、空结果集
    - `load_api`：HTTP 错误码、响应解析失败
    - `row_filter`：空过滤条件、无匹配行、全部匹配
    - _需求: 1.1–1.6, 2.1–2.4, 3.1–3.3_

- [x] 4. 实现数据预处理算子后端
  - [x] 4.1 实现 `resample_timeseries` 算子后端
    - 创建 `operator_backends/resample_timeseries.py`，复用 `data_process.get_completed_timestamp` 逻辑
    - 支持 `frequency` 参数和 `mean`/`sum`/`max`/`min` 四种聚合方法
    - 自动生成完整时间戳网格，缺失时间点填充 NaN
    - 高级参数：`task_type`、`time_granularity`、`time_field`、`load_field`
    - _需求: 4.1, 4.2, 4.3, 4.4_

  - [x] 4.2 实现 `detect_outliers` 算子后端
    - 创建 `operator_backends/detect_outliers.py`，复用 `data_process.chebyshev_detector` 的 rolling MAD 逻辑
    - 支持 `zscore`/`iqr`/`isolation_forest` 三种方法
    - `threshold` 参数控制灵敏度（默认 3.0）
    - 仅使用历史数据（shift(1)），避免未来数据泄露
    - 返回 DataFrame（异常值替换为 NaN）和异常索引列表
    - _需求: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 4.3 实现 `handle_missing` 算子后端
    - 创建 `operator_backends/handle_missing.py`，复用 `data_process.get_completed_df` 的 `interpolate(method='time')` 逻辑
    - 支持 `linear`/`ffill`/`bfill`/`mean` 四种方法
    - 插值后 ffill+bfill 兜底，确保输出无 NaN
    - 非目标列使用 ffill/bfill 策略
    - _需求: 6.1, 6.2, 6.3, 6.4_

  - [x] 4.4 实现 `sliding_window` 算子后端
    - 创建 `operator_backends/sliding_window.py`
    - 支持 `window_size`（必填）、`step`（默认 1）、`target_column`（默认 "load"）参数
    - 确保窗口切片无未来数据泄露，丢弃不完整样本
    - `window_size <= 0` 或 `window_size > 数据行数` 时返回参数校验错误
    - _需求: 37.1, 37.2, 37.3, 37.4, 37.5, 37.6, 37.7, 37.8, 37.9_

  - [ ]* 4.5 为数据预处理算子编写属性测试
    - **Property 2: resample_timeseries 连续时间网格与聚合正确性**
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - **Property 3: detect_outliers 阈值单调性**
    - **Validates: Requirements 5.3**
    - **Property 4: 无未来数据泄露**（detect_outliers 部分）
    - **Validates: Requirements 5.5**
    - **Property 5: handle_missing 无 NaN 保证**
    - **Validates: Requirements 6.3, 6.4**
    - **Property 23: sliding_window 窗口切片正确性**
    - **Validates: Requirements 37.1, 37.2, 37.5, 37.6, 37.7, 37.8**

  - [ ]* 4.6 为数据预处理算子编写单元测试
    - `resample_timeseries`：空数据、单行数据、已对齐数据
    - `detect_outliers`：无异常、全异常、三种方法对比
    - `handle_missing`：无缺失、全缺失、四种方法对比
    - `sliding_window`：window_size=1、window_size=数据长度、step_size>1
    - _需求: 4.1–4.4, 5.1–5.5, 6.1–6.4, 37.1–37.9_

- [x] 5. Checkpoint — 确保数据源和预处理算子测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 6. 实现特征工程算子后端
  - [x] 6.1 实现 `extract_time_features` 算子后端
    - 创建 `operator_backends/extract_time_features.py`，复用 `features/engine.py` 中时间特征提取逻辑
    - 支持 `hour`/`dayofweek`/`month`/`day`/`quarter`/`is_holiday` 特征
    - `time_zone` 从全局配置注入获取
    - 提取的特征列合并到输入数据中返回
    - _需求: 7.1, 7.2, 7.3, 7.4_

  - [x] 6.2 实现 `holiday_features` 算子后端
    - 创建 `operator_backends/holiday_features.py`，复用 `chinese_calendar.get_holiday_detail`
    - 生成 `is_holiday` 和 `holiday_name` 两个特征列
    - 高级参数 `remove_spring_festival` 控制是否剔除春节数据
    - _需求: 8.1, 8.2, 8.3, 8.4_

  - [x] 6.3 实现 `workday_features` 算子后端
    - 创建 `operator_backends/workday_features.py`，复用 `common.holidays.if_workday`
    - 生成 `is_workday` 特征列
    - 高级参数 `shift_rules` 支持班次划分规则配置
    - _需求: 9.1, 9.2, 9.3_

  - [x] 6.4 实现 `rolling_statistics` 算子后端
    - 创建 `operator_backends/rolling_statistics.py`，复用 `add_features.get_rolling_features` 逻辑
    - 高级参数：`target_column`、`window_sizes`（默认 [24,48,96,168]）、`statistics`（mean/std/quantile）
    - 仅使用历史数据，避免未来数据泄露
    - _需求: 10.1, 10.2, 10.3, 10.4_

  - [x] 6.5 实现 `create_lag_features` 算子后端
    - 创建 `operator_backends/create_lag_features.py`
    - 支持 `lags` 列表参数（如 [1, 24, 168]）
    - 对目标列执行 shift 操作，NaN 保留不填充
    - _需求: 11.1, 11.2, 11.3_

  - [x] 6.6 实现 `diff_features`、`pct_change_features`、`extract_statistical_features`、`peak_valley_features`、`shift_features` 算子后端
    - 分别创建对应的 `operator_backends/` 模块
    - `diff_features`：复用 `add_features.get_diff_features`，支持差分阶数和季节周期配置
    - `pct_change_features`：复用 `add_features.get_pct_rate_feature`，支持计算周期配置
    - `extract_statistical_features`：复用 `add_features.get_stat_features` 和 `get_hist_period_statis`
    - `peak_valley_features`：标记峰/谷/平时段
    - `shift_features`：标记早班/中班/晚班
    - _需求: 12.1, 12.2, 12.3, 12.4, 13.1, 13.2, 13.3_

  - [ ]* 6.7 为特征工程算子编写属性测试
    - **Property 6: extract_time_features 特征值正确性与列保留**
    - **Validates: Requirements 7.1, 7.2, 7.4**
    - **Property 7: 特征提取保留原始列**
    - **Validates: Requirements 8.2, 9.1, 10.1, 11.1**
    - **Property 8: holiday_features 节假日标记正确性**
    - **Validates: Requirements 8.1, 8.3, 8.4**
    - **Property 9: workday_features 工作日标记正确性**
    - **Validates: Requirements 9.1, 9.2**
    - **Property 10: rolling_statistics 滚动统计正确性**
    - **Validates: Requirements 10.1, 10.2, 10.3**
    - **Property 4: 无未来数据泄露**（rolling_statistics + sliding_window 部分）
    - **Validates: Requirements 10.4, 37.5**
    - **Property 11: create_lag_features 滞后特征正确性**
    - **Validates: Requirements 11.1, 11.3**
    - **Property 12: diff_features 差分正确性**
    - **Validates: Requirements 12.1**
    - **Property 13: pct_change_features 变化率正确性**
    - **Validates: Requirements 12.2**

  - [ ]* 6.8 为特征工程算子编写单元测试
    - 各算子的空输入、单行输入、特殊日期（春节、闰年）
    - _需求: 7.1–7.4, 8.1–8.4, 9.1–9.3, 10.1–10.4, 11.1–11.3, 12.1–12.4, 13.1–13.3_

- [x] 7. 实现模型训练与预测算子后端
  - [x] 7.1 实现 `train_test_split_ts` 算子后端
    - 创建 `operator_backends/train_test_split_ts.py`
    - 支持 `train_ratio`/`val_ratio`/`split_date` 参数，`split_date` 优先于比例切分
    - 保持时间顺序不打乱
    - 高级参数：`time_field`、`target_column`、`task_type`、`forecast_horizon`
    - 输出 `train_features`/`train_target`/`test_features`/`test_target`
    - _需求: 14.1, 14.2, 14.3, 14.4_

  - [x] 7.2 实现 `auto_tune_xgboost` 算子后端
    - 创建 `operator_backends/auto_tune_xgboost.py`，复用 `models_pkg/trainer.py` 中 `xgb_model_trainer` 的 BayesianOptimization 逻辑
    - 支持 `n_trials`/`metric`/`cv_folds` 参数
    - 返回最优参数和训练好的模型对象
    - _需求: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 7.3 实现 `multi_step_forecast` 算子后端
    - 创建 `operator_backends/multi_step_forecast.py`
    - 支持 `forecast_steps`（必填）、`strategy`（recursive/direct/hybrid，默认 recursive）、`step_size`（默认 1）参数
    - 高级参数：`forecast_start_time`
    - 输出 `forecast_config` 对象 + 透传上游训练/测试数据
    - `forecast_steps <= 0` 时返回参数校验错误
    - _需求: 36.1, 36.2, 36.3, 36.4, 36.5, 36.6, 36.7, 36.8, 36.9_

  - [x] 7.4 实现 `xgboost_forecast` 算子后端
    - 创建 `operator_backends/xgboost_forecast.py`，复用 `model_prefer_trainer` 和 `LoadForecastWrapper.predict` 逻辑
    - 训练模式（`mode=train`）：训练 XGBoost 模型并返回预测结果
    - 预测模式（`mode=predict`）：加载 `model_id` 指定的已训练模型执行推理
    - 高级参数：`separate_modeling`、`prefer_unit_len`、`default_retrain`、`sample_weight_decay`、`task_type`
    - 支持 `auto_tune` 参数自动调用贝叶斯优化
    - 支持样本权重机制（`sample_weigths` 近期数据加权）
    - _需求: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

  - [x] 7.5 实现 `smape_score` 和 `mse_rmse_mae` 评估指标算子后端
    - 创建 `operator_backends/smape_score.py`，复用 `utils.smape` 逻辑
    - 创建 `operator_backends/mse_rmse_mae.py`
    - `y_true` 和 `y_pred` 长度不一致时返回参数校验错误
    - _需求: 17.1, 17.2, 17.3, 17.4, 17.5_

  - [ ]* 7.6 为模型训练与预测算子编写属性测试
    - **Property 14: train_test_split_ts 时间顺序保持与列一致性**
    - **Validates: Requirements 14.1, 14.2**
    - **Property 15: SMAPE 公式正确性**
    - **Validates: Requirements 17.1, 17.3**
    - **Property 16: MSE/RMSE/MAE 公式正确性**
    - **Validates: Requirements 17.2, 17.4**
    - **Property 22: multi_step_forecast 配置输出正确性**
    - **Validates: Requirements 36.1, 36.2, 36.4, 36.8**

  - [ ]* 7.7 为模型训练与预测算子编写单元测试
    - `train_test_split_ts`：split_date 优先于比例、极端比例
    - `multi_step_forecast`：各策略配置、无效参数
    - `smape_score`：全零输入、完全匹配、长度不一致
    - `mse_rmse_mae`：全零输入、完全匹配、长度不一致
    - _需求: 14.1–14.4, 15.1–15.5, 16.1–16.6, 17.1–17.5, 36.1–36.9_

- [x] 8. Checkpoint — 确保所有算子后端测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 9. 增强工作流执行器
  - [x] 9.1 增强 `workflows_enhanced.py` 中的 `execute_workflow` 端点，集成算子执行框架
    - 加载工作流定义后读取 `metadata.global_config`
    - 初始化 `GlobalConfigInjector`
    - 拓扑排序后逐节点执行：收集上游输入 → 注入全局配置 → SchemaValidator 校验输入 → DataAdapter 适配列名 → OperatorRouter 路由执行 → SchemaValidator 校验输出 → 记录日志和耗时
    - _需求: 21.1, 21.5, 21.6_

  - [x] 9.2 新增异步执行和状态轮询端点
    - `POST /api/workflows/enhanced/{id}/execute-async`：异步执行，返回 `execution_id`
    - `GET /api/workflows/enhanced/{id}/execution-status/{execution_id}`：轮询状态，返回节点状态和日志
    - _需求: 30.2_

  - [x] 9.3 新增预检端点
    - `POST /api/workflows/enhanced/{id}/preflight`：使用前 100 行样本数据按拓扑顺序逐节点执行
    - 返回预检报告：每对相邻算子的数据传递状态、Schema 摘要、耗时
    - _需求: 27.1, 27.2, 27.3_

  - [x] 9.4 扩展 `EnhancedWorkflow` 模型支持 `metadata` 字段
    - 在 `EnhancedWorkflow` Pydantic 模型中添加 `metadata: Optional[Dict[str, Any]]` 字段
    - 确保保存/加载工作流时正确持久化 `metadata.global_config`
    - _需求: 工作流全局配置设计_

  - [x] 9.5 实现回测执行逻辑
    - 按日期范围逐日循环执行训练子流水线 + 推理子流水线
    - 每日自动设置 `nowtime` 为当前回测日期
    - 收集每日结果：日期、状态、耗时、预测时间戳/值、预测点数
    - 单日数据不足标记 `skipped`，异常标记 `failed`，继续下一日
    - 汇总回测结果：总天数、成功/跳过/失败天数、总耗时
    - _需求: 34.5, 34.6, 34.7, 34.8, 34.9, 34.11_

  - [ ]* 9.6 为工作流执行器编写属性测试和单元测试
    - **Property 19: 执行日志格式正确性**
    - **Validates: Requirements 23.2, 23.3, 23.4**
    - **Property 20: 端口类型兼容性检查**
    - **Validates: Requirements 24.1, 24.2**
    - **Property 21: 回测汇总统计正确性**
    - **Validates: Requirements 34.9, 35.8**

- [x] 10. Checkpoint — 确保工作流执行器测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 11. 实现前端类型定义与状态管理
  - [x] 11.1 创建前端 TypeScript 类型定义文件
    - 创建 `src/types/pipeline.ts`，定义所有接口：`WorkflowGlobalConfig`、`OperatorParameter`、`DataContract`、`PipelineTemplate`、`ExecutionStatus`、`NodeExecutionStatus`、`PipelineLogEntry`、`NodeExecutionResult`、`TrainingPipelineResult`、`PredictionPipelineResult`、`BacktestPipelineResult`、`BacktestDailyResult`、`ExecutionRecord`、`PORT_TYPE_COLORS`
    - _需求: 24.3, 24.4_

  - [x] 11.2 实现 `pipelineExecutionStore`（zustand 状态管理）
    - 创建 `src/stores/pipelineExecutionStore.ts`
    - 状态：`executionId`、`executionStatus`、`nodeStatuses`、`logs`、`isExecuting`、`globalConfig`、`trainingResult`/`predictionResult`/`backtestResult`、`executionHistory`
    - Actions：`executePipeline`、`executePreflightCheck`、`pollExecutionStatus`（每 2 秒轮询）、`stopPolling`、`startBacktest`、`updateGlobalConfig`、`exportResults`、`loadHistoryConfig`、`reset`
    - _需求: 30.2, 31.11, 31.12_

  - [x] 11.3 扩展 API 服务层
    - 扩展 `src/services/workflowEnhancedApi.ts`，新增 `pipelineApi` 对象
    - `executeAsync(workflowId, params)`、`getExecutionStatus(workflowId, executionId)`、`preflight(workflowId)`、`getNodeResult(workflowId, executionId, nodeId)`
    - _需求: 21.1, 27.1, 30.2_

- [x] 12. 实现前端算子配置面板
  - [x] 12.1 实现 `OperatorConfigPanel` 组件
    - 创建 `src/components/workflow-enhanced/OperatorConfigPanel.tsx`
    - 根据 `functions.json` 的 `parameters` 定义自动生成表单：STRING→Input、NUMBER→InputNumber/Slider、BOOLEAN→Switch、ARRAY→TagInput、SELECT→Select
    - 参数分为"基础参数"（默认展开）和"高级参数"（默认折叠）
    - 必填字段校验 + 数值范围校验 + 红色边框错误提示
    - 每个参数提供 tooltip 说明文字和"恢复默认"按钮
    - 执行结果预览标签页（MATRIX→表格前10行、ARRAY→前20元素、NUMBER→数值）
    - _需求: 19.1, 19.2, 19.3, 19.4, 19.5, 22.1, 22.2, 22.3, 28.1, 28.2, 28.3, 28.5, 28.6, 28.7_

  - [x] 12.2 为 `OperatorConfigPanel` 配置负荷预测场景的 Humanized_Param
    - 为 `load_csv`、`resample_timeseries`、`detect_outliers`、`handle_missing`、`extract_time_features`、`rolling_statistics`、`create_lag_features`、`train_test_split_ts`、`xgboost_forecast`、`smape_score` 定义中文标签、描述、默认值和控件类型
    - _需求: 28.4_

  - [x] 12.3 实现 `WorkflowGlobalConfigPanel` 组件
    - 创建 `src/components/workflow-enhanced/WorkflowGlobalConfigPanel.tsx`
    - 工具栏中"工作流设置"按钮触发
    - 编辑 `time_zone`（时区下拉选择）、`operate_status`（运行状态下拉选择）、`nowtime`（日期时间选择器）
    - 保存时写入 `EnhancedWorkflow.metadata.global_config`
    - _需求: 工作流全局配置设计_

  - [x] 12.4 实现 `DataContractTooltip` 组件
    - 创建 `src/components/workflow-enhanced/DataContractTooltip.tsx`
    - 在连线上以 tooltip 形式展示 Data Contract 摘要（数据类型、关键列名、约束条件）
    - _需求: 20.6_

  - [x] 12.5 实现端口类型校验逻辑
    - 在工作流编辑器中连接两个节点时校验源端口 `return_type` 与目标端口 `type` 是否兼容
    - 不兼容时阻止连线并展示提示
    - 连线以颜色区分不同数据类型（MATRIX=蓝、ARRAY=绿、NUMBER=黄、STRING=紫、OBJECT=粉）
    - _需求: 24.1, 24.2, 24.3, 24.4_

  - [ ]* 12.6 为 OperatorConfigPanel 编写单元测试
    - 组件渲染测试：各参数类型的表单控件正确渲染
    - 校验逻辑测试：必填字段、数值范围
    - _需求: 19.1–19.5, 28.1–28.7_

- [x] 13. 实现前端流水线模板
  - [x] 13.1 创建流水线模板数据定义
    - 创建 `src/data/pipelineTemplates.ts`
    - 定义 `TRAINING_PIPELINE_TEMPLATE`：16 个算子节点（load_csv → row_filter → resample → detect_outliers → handle_missing → extract_time_features → holiday_features → workday_features → rolling_statistics → create_lag_features → sliding_window → train_test_split_ts → multi_step_forecast → xgboost_forecast → smape_score + mse_rmse_mae）、连线、数据契约、默认参数
    - 定义 `PREDICTION_PIPELINE_TEMPLATE`：推理流水线，xgboost_forecast 使用 `mode: 'predict'`，要求 `model_id`
    - 定义 `BACKTEST_PIPELINE_TEMPLATE`：回测流水线，包含 `start_date`/`end_date` 参数
    - _需求: 20.1, 20.2, 20.3, 20.4, 20.5, 32.1, 32.2, 32.5, 34.1, 34.2, 34.3, 34.4_

  - [x] 13.2 实现 `PipelineTemplateMenu` 组件
    - 创建 `src/components/workflow-enhanced/PipelineTemplateMenu.tsx`
    - 提供三种模板选择：负荷预测训练流水线、推理流水线、回测流水线
    - 选择模板后自动在画布上创建所有算子节点和连线
    - _需求: 20.1, 20.2, 32.1, 34.1_

  - [ ]* 13.3 为 options 序列化/反序列化编写属性测试
    - **Property 26: options 序列化/反序列化往返一致性**
    - **Validates: Requirements 29.5**

- [x] 14. Checkpoint — 确保前端基础组件和模板测试通过
  - 确保所有测试通过，如有问题请询问用户。

- [x] 15. 实现前端执行可视化组件
  - [x] 15.1 实现 `PipelineProgressTracker` 组件
    - 创建 `src/components/workflow-enhanced/PipelineProgressTracker.tsx`
    - 以步骤条形式展示所有算子节点的执行状态（等待中/执行中/已完成/失败）
    - 执行中节点展示加载动画，已完成节点展示耗时
    - 回测模式支持双层进度（外层日期进度 + 内层算子进度）
    - 复用 `load-forecast-training-ui` 中 ProgressTracker 的 Steps 步骤条设计模式
    - _需求: 30.1, 30.2, 30.9, 35.1_

  - [x] 15.2 实现 `PipelineLogConsole` 组件
    - 创建 `src/components/workflow-enhanced/PipelineLogConsole.tsx`
    - 深色背景、等宽字体的终端风格面板
    - 日志格式：`[HH:MM:SS] ▶ {算子名称} 开始执行...`（高亮）、`[HH:MM:SS] ✓ {算子名称} 完成 (耗时 X.XXs)`（绿色）、`[HH:MM:SS] ✗ {算子名称} 失败: {错误信息}`（红色）
    - 流水线开始时展示执行配置摘要
    - 支持自动滚动，手动滚动时暂停自动滚动
    - 回测模式支持分日日志分隔：`══════ 第 X 天 / 共 N 天：YYYY-MM-DD ══════`
    - _需求: 23.1, 23.2, 23.3, 23.4, 30.3, 30.4, 30.5, 30.6, 30.7, 30.8, 35.2, 35.3, 35.4, 35.5, 35.6, 35.7_

  - [x] 15.3 实现 `TrainingResultDashboard` 组件
    - 创建 `src/components/workflow-enhanced/TrainingResultDashboard.tsx`
    - 展示总执行时间、模板名称、完成时间
    - ECharts 水平条形图展示每个算子耗时分布
    - ECharts 饼图/环形图展示各算子耗时占比
    - 模型信息区域：`model_id` + "复制 Model ID"按钮
    - 评估指标卡片：SMAPE、MAE、RMSE
    - "快速回测"按钮
    - 执行失败时展示失败算子和错误信息（红色警告）
    - _需求: 31.1, 31.2, 31.3, 31.4, 31.5, 31.6, 31.7, 31.13_

  - [x] 15.4 实现 `PredictionResultDashboard` 组件
    - 创建 `src/components/workflow-enhanced/PredictionResultDashboard.tsx`
    - 展示总执行时间、`model_id`、完成时间
    - ECharts 折线图展示预测曲线（支持缩放和数据点悬停）
    - 数据表格展示预测结果明细（时间戳 + 预测值，支持分页）
    - "导出预测结果"按钮（CSV 下载）
    - ECharts 水平条形图展示算子耗时分布
    - _需求: 33.3, 33.4, 33.5, 33.6, 33.7, 33.8, 33.9_

  - [x] 15.5 实现 `BacktestResultDashboard` 组件
    - 创建 `src/components/workflow-enhanced/BacktestResultDashboard.tsx`
    - 汇总统计卡片：总天数、成功/跳过/失败天数、总耗时
    - ECharts 折线图展示每日预测值与实际值对比曲线（支持日期范围缩放）
    - ECharts 柱状图展示每日预测点数量分布
    - 逐日明细数据表格（日期、状态标签、耗时、预测点数，支持筛选和排序）
    - 评估指标区域：逐日 SMAPE/MAE/RMSE 折线图 + 整体平均值卡片
    - "导出回测报告"按钮（CSV 下载）
    - 无有效结果时展示警告信息
    - _需求: 35.8, 35.9, 35.10, 35.11, 35.12, 35.13, 35.15_

  - [x] 15.6 实现执行历史记录功能
    - 在执行面板中维护当前会话的执行历史列表
    - 展示每次执行的 ID、模板名称、状态、model_id、耗时
    - 点击历史记录自动回填算子参数配置到画布
    - _需求: 31.11, 31.12, 35.14_

  - [ ]* 15.7 为执行可视化组件编写单元测试
    - `PipelineProgressTracker`：各状态渲染、回测双层进度
    - `PipelineLogConsole`：日志格式、自动滚动、分日分隔
    - `TrainingResultDashboard`/`PredictionResultDashboard`/`BacktestResultDashboard`：数据渲染
    - _需求: 30.1–30.9, 31.1–31.13, 33.1–33.9, 35.1–35.15_

- [x] 16. 集成连线与端到端验证
  - [x] 16.1 将 `OperatorConfigPanel`、`WorkflowGlobalConfigPanel`、`PipelineTemplateMenu`、`PipelineProgressTracker`、`PipelineLogConsole`、结果仪表盘组件集成到 `WorkflowEditorPage`
    - 双击/选中算子节点时打开 OperatorConfigPanel 侧边栏
    - 工具栏添加"工作流设置"按钮和模板选择菜单
    - 执行时底部/侧边面板展示进度追踪器和日志控制台
    - 执行完成后展示对应类型的结果仪表盘
    - _需求: 19.1, 20.4, 21.2, 21.3, 21.4, 25.3_

  - [x] 16.2 实现工作流节点状态实时更新
    - 执行中节点标记"执行中"并展示加载动画
    - 完成节点标记"已完成"并展示耗时
    - 失败节点标记"失败"并展示错误信息，停止后续执行
    - _需求: 21.2, 21.3, 21.4_

  - [ ]* 16.3 编写端到端集成测试
    - 使用 `datasets/load_true_weihai_260415.csv` 样本数据
    - 执行完整训练流水线，验证最终输出包含有效的 SMAPE 和 MSE/RMSE/MAE 值
    - 验证每对相邻算子之间的数据传递符合 DataContract
    - 验证 GlobalConfigInjector 正确注入 time_zone/nowtime
    - _需求: 27.4, 27.5, 27.6_

- [x] 17. Final Checkpoint — 确保所有测试通过
  - 确保所有测试通过，如有问题请询问用户。

## 备注

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号以确保可追溯性
- Checkpoint 任务确保增量验证
- 属性测试验证设计文档中定义的 26 个正确性属性
- 单元测试验证具体示例和边界条件
- 后端算子实现应复用现有代码（`data_process.py`、`features/engine.py`、`models_pkg/trainer.py`、`models_pkg/wrapper.py`、`data_fetch/fetcher.py`、`add_features.py`），不重写
<!-- @AI_GENERATED: end -->
