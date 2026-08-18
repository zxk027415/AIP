<!-- @AI_GENERATED -->
# Requirements Document

## Introduction

本文档定义了 AIP 工业AI算法平台中**负荷预测训练可视化界面**的功能需求。该界面允许用户配置训练参数、触发负荷预测模型训练、以类似 Weights & Biases 风格实时监控训练进度与日志，并在训练完成后查看精度指标和可视化图表。

后端已提供完整的 REST API 端点（`/api/load-forecast/*`），前端需要构建与之对接的可视化交互界面。训练流程包含四个步骤：**数据获取 → 异常检测 → 特征工程 → 模型训练**，整体耗时约 1-2 分钟。系统支持 6 种预测场景：DI（日内）、D（日前）、WI（周内）、W（周前）、MI（月内）、M（月前）。

## Glossary

- **Training_Page**: 负荷预测训练可视化界面，用户配置参数、触发训练、监控进度和查看结果的主页面组件
- **Scenario_Selector**: 预测场景选择器，展示 6 种预测场景（DI/D/WI/W/MI/M）供用户选择
- **Parameter_Form**: 训练参数配置表单，收集训练所需的全部参数（场景类型、数据源路径、父子节点 ID、预测步长等）
- **Progress_Tracker**: 训练进度追踪器，通过轮询 `/api/load-forecast/status/{task_id}` 端点实时展示训练步骤状态
- **Log_Console**: 训练日志控制台，以类似终端的深色面板实时展示训练过程中的步骤日志、时间戳和状态变更
- **Result_Dashboard**: 训练结果仪表盘，展示训练成功后的 model_id、总耗时、各步骤耗时以及精度指标和可视化图表
- **Metrics_Chart**: 指标可视化图表组件，使用 ECharts 展示训练结果的精度指标（如步骤耗时分布、回测精度曲线等）
- **Load_Forecast_API**: 后端负荷预测 REST API 服务，提供 train、predict、backtest、scenarios、status 端点
- **Training_Step**: 训练流程中的单个步骤，包括 data_fetch（数据获取）、anomaly_detection（异常检测）、feature_engineering（特征工程）、model_train（模型训练）
- **Task_Status**: 后端返回的任务状态对象，包含 status、current_step、completed_steps、step_durations、error_message 等字段

## Requirements

### Requirement 1: 场景配置加载

**User Story:** 作为平台用户，我想在训练页面加载时自动获取可用的预测场景列表，以便了解各场景的用途并选择合适的场景。

#### Acceptance Criteria

1. WHEN Training_Page 加载完成, THE Scenario_Selector SHALL 调用 `GET /api/load-forecast/scenarios` 获取 6 种预测场景配置
2. THE Scenario_Selector SHALL 以卡片或选项列表形式展示每个场景的 task_type、name、description 和 recommended_config 信息
3. WHEN 用户选择一个场景, THE Parameter_Form SHALL 自动填充该场景的推荐配置（forecast_horizon、separate_modeling、time_granularity）
4. IF 场景列表请求失败, THEN THE Training_Page SHALL 展示错误提示信息并提供重试按钮

### Requirement 2: 训练参数配置

**User Story:** 作为平台用户，我想配置训练所需的参数（场景类型、数据源路径、节点 ID、预测步长等），以便按需启动训练任务。

#### Acceptance Criteria

1. THE Parameter_Form SHALL 提供以下必填参数的输入控件：task_type（场景类型）、csv_path（CSV 数据文件路径）、parent_id（父节点 ID）、child_id（子节点 ID）
2. THE Parameter_Form SHALL 提供以下可选参数的输入控件并设置默认值：forecast_horizon（预测步长，默认 1）、time_granularity（时间粒度，默认 15min）、separate_modeling（分段建模，默认 true）、forecast_start_time（预测起始时间，默认 00:15）
3. WHEN 用户未填写必填参数并点击训练按钮, THE Parameter_Form SHALL 高亮未填写的必填字段并展示验证错误提示
4. THE Parameter_Form SHALL 对 forecast_horizon 参数进行数值范围校验，确保其为正整数

### Requirement 3: 触发训练

**User Story:** 作为平台用户，我想通过点击按钮触发模型训练，以便启动负荷预测模型的训练流程。

#### Acceptance Criteria

1. WHEN 用户点击"开始训练"按钮且参数校验通过, THE Training_Page SHALL 调用 `POST /api/load-forecast/train` 并传递 Parameter_Form 中的所有参数
2. WHILE 训练请求正在发送, THE Training_Page SHALL 禁用"开始训练"按钮并展示加载状态
3. WHEN 训练请求成功返回 task_id, THE Progress_Tracker SHALL 开始轮询训练状态
4. IF 训练请求返回 HTTP 400 错误（参数校验失败）, THEN THE Training_Page SHALL 展示后端返回的 error_message
5. IF 训练请求返回网络错误或 HTTP 500 错误, THEN THE Training_Page SHALL 展示"训练启动失败"的错误提示并允许用户重试

### Requirement 4: 实时训练进度监控

**User Story:** 作为平台用户，我想实时查看训练进度（当前步骤、已完成步骤、各步骤耗时），以便了解训练是否正常进行。

#### Acceptance Criteria

1. WHILE 训练任务状态为 "running", THE Progress_Tracker SHALL 每 2 秒调用 `GET /api/load-forecast/status/{task_id}` 获取最新状态
2. THE Progress_Tracker SHALL 以步骤条（Steps 组件）形式展示四个训练步骤：数据获取、异常检测、特征工程、模型训练
3. WHEN 后端返回 current_step 字段, THE Progress_Tracker SHALL 将对应步骤标记为"进行中"状态并展示加载动画
4. WHEN 后端返回 completed_steps 列表, THE Progress_Tracker SHALL 将已完成步骤标记为"已完成"状态并展示该步骤的 step_durations 耗时
5. WHEN 训练任务状态变为 "success", THE Progress_Tracker SHALL 停止轮询并将所有步骤标记为已完成
6. WHEN 训练任务状态变为 "failed", THE Progress_Tracker SHALL 停止轮询，将失败步骤标记为错误状态，并展示 error_message

### Requirement 5: 训练日志控制台

**User Story:** 作为平台用户，我想在训练过程中看到类似 Weights & Biases 风格的实时日志输出，以便详细了解每个步骤的执行情况和时间消耗。

#### Acceptance Criteria

1. THE Log_Console SHALL 以深色背景、等宽字体的终端风格面板展示训练日志
2. WHEN Progress_Tracker 检测到步骤状态变更, THE Log_Console SHALL 追加一条带时间戳的日志条目，格式为 `[HH:MM:SS] 步骤名称 - 状态描述`
3. WHEN 一个 Training_Step 开始执行, THE Log_Console SHALL 追加 `[HH:MM:SS] ▶ 步骤名称 开始执行...` 日志并以高亮颜色标记
4. WHEN 一个 Training_Step 完成, THE Log_Console SHALL 追加 `[HH:MM:SS] ✓ 步骤名称 完成 (耗时 X.XXs)` 日志并以成功颜色（绿色）标记
5. IF 一个 Training_Step 失败, THEN THE Log_Console SHALL 追加 `[HH:MM:SS] ✗ 步骤名称 失败: 错误信息` 日志并以错误颜色（红色）标记
6. THE Log_Console SHALL 自动滚动到最新日志条目
7. THE Log_Console SHALL 在训练开始时展示训练配置摘要（场景类型、数据源、关键参数）

### Requirement 6: 训练结果仪表盘

**User Story:** 作为平台用户，我想在训练完成后查看详细的训练结果，包括模型标识、耗时统计和精度指标图表，以便评估训练效果并决定是否使用该模型。

#### Acceptance Criteria

1. WHEN 训练任务状态变为 "success", THE Result_Dashboard SHALL 展示以下基本信息：model_id、总耗时（total_duration）、训练场景类型、训练时间
2. THE Result_Dashboard SHALL 提供"复制 Model ID"按钮，点击后将 model_id 复制到系统剪贴板
3. THE Result_Dashboard SHALL 以水平条形图展示各 Training_Step 的耗时分布，使用 ECharts 渲染
4. THE Result_Dashboard SHALL 以饼图或环形图展示各步骤耗时占总耗时的百分比
5. WHEN 训练失败, THE Result_Dashboard SHALL 展示失败步骤名称（error_step）和错误信息（error_message），并以红色警告样式呈现

### Requirement 7: 训练后快速回测验证

**User Story:** 作为平台用户，我想在训练完成后快速发起回测，以便验证模型的预测精度并查看精度指标图表。

#### Acceptance Criteria

1. WHEN 训练成功完成, THE Result_Dashboard SHALL 展示"快速回测"按钮
2. WHEN 用户点击"快速回测"按钮, THE Training_Page SHALL 调用 `POST /api/load-forecast/backtest` 并传递训练时使用的参数和日期范围
3. WHEN 回测完成, THE Metrics_Chart SHALL 以折线图展示每日预测值与实际值的对比曲线
4. WHEN 回测完成, THE Metrics_Chart SHALL 展示汇总精度指标：成功天数、跳过天数、失败天数、总耗时
5. THE Metrics_Chart SHALL 以柱状图展示每日回测的预测点数量分布

### Requirement 8: 页面路由与导航集成

**User Story:** 作为平台用户，我想通过侧边栏导航访问负荷预测训练页面，以便快速进入训练功能。

#### Acceptance Criteria

1. THE Training_Page SHALL 注册路由路径 `/load-forecast/training`，并在 MainLayout 侧边栏导航中添加对应菜单项
2. THE Training_Page SHALL 遵循项目现有的页面布局模式（使用 Ant Design Card、Row、Col 等组件）
3. THE Training_Page SHALL 在页面顶部展示标题"负荷预测训练"和功能简介

### Requirement 9: 训练历史与重新训练

**User Story:** 作为平台用户，我想查看当前会话中的训练记录并能快速重新训练，以便对比不同参数的训练效果。

#### Acceptance Criteria

1. THE Training_Page SHALL 在页面中维护当前会话的训练记录列表，展示每次训练的 task_id、场景类型、状态、model_id 和总耗时
2. WHEN 用户点击训练记录中的某条记录, THE Parameter_Form SHALL 自动填充该次训练使用的参数配置
3. WHEN 训练完成（成功或失败）, THE Training_Page SHALL 重新启用"开始训练"按钮，允许用户修改参数后再次训练
<!-- @AI_GENERATED: end -->
