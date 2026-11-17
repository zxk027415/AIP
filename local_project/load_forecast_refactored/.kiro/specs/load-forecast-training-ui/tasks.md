<!-- @AI_GENERATED -->
# Implementation Plan: 负荷预测训练可视化界面

## Overview

基于现有 React 18 + TypeScript + Ant Design 5 + ECharts + zustand + axios 技术栈，实现负荷预测训练可视化界面。遵循项目现有的分层架构模式（types → services → stores → components → pages），逐步构建从类型定义到页面集成的完整功能。所有组件对接后端已有的 `/api/load-forecast/*` REST API 端点。

## Tasks

- [x] 1. 定义 TypeScript 类型与常量
  - 创建 `src/types/load-forecast.ts`，定义所有接口和类型：`ScenarioConfig`、`TrainingParams`、`TaskStatus`、`TrainingStepName`、`TrainingStepInfo`、`LogEntry`、`TrainingResult`、`BacktestParams`、`BacktestDailyResult`、`BacktestResult`、`TrainingRecord`、`ScenariosResponse`、`TrainResponse`、`TaskStatusResponse`
  - 定义常量 `TRAINING_STEPS`（四步训练流程标签）和 `TASK_TYPE_LABELS`（6 种场景中文标签映射）
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 4.2, 5.2, 6.1, 7.4, 9.1_

- [x] 2. 实现 API 服务层
  - 创建 `src/services/loadForecastApi.ts`，使用项目现有的 axios 实例（`import api from './api'`）
  - 封装四个 API 方法：`getScenarios()`、`startTraining(params)`、`getTaskStatus(taskId)`、`startBacktest(params)`
  - 对应后端端点：`GET /load-forecast/scenarios`、`POST /load-forecast/train`、`GET /load-forecast/status/{task_id}`、`POST /load-forecast/backtest`
  - _Requirements: 1.1, 3.1, 4.1, 7.2_

- [x] 3. 实现 zustand 状态管理 Store
  - 创建 `src/stores/loadForecastStore.ts`，使用 `create` from zustand
  - 实现场景管理：`fetchScenarios`、`selectScenario`（自动填充推荐配置）
  - 实现训练流程：`startTraining`（调用 API 并启动轮询）、`pollStatus`（每 2 秒轮询，更新步骤状态和日志）、`stopPolling`（清除定时器）
  - 实现轮询容错：单次失败静默重试，连续 3 次失败展示警告，连续 10 次失败停止轮询
  - 实现日志生成：步骤开始追加 `▶` 日志、步骤完成追加 `✓` 日志（含耗时）、步骤失败追加 `✗` 日志（含错误信息）
  - 实现回测：`startBacktest`（调用回测 API 并存储结果）
  - 实现训练历史：每次训练完成后追加 `TrainingRecord`，支持 `loadHistoryParams` 回填参数
  - 实现 `resetTraining` 重置训练状态
  - _Requirements: 1.1, 1.3, 3.1, 3.3, 4.1, 4.3, 4.4, 4.5, 4.6, 5.2, 5.3, 5.4, 5.5, 5.7, 7.2, 9.1, 9.2, 9.3_

- [x] 4. Checkpoint - 确保类型、API 层和 Store 编译通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. 实现场景选择器和参数表单组件
  - [x] 5.1 实现 ScenarioSelector 组件
    - 创建 `src/components/load-forecast/ScenarioSelector.tsx`
    - 以 Ant Design Card 网格（Row/Col）展示 6 种预测场景卡片，每张卡片显示 task_type、name、description
    - 选中卡片高亮显示，点击触发 `onSelect` 回调
    - 支持 loading 状态展示 Skeleton 占位，场景加载失败展示 Alert + 重试按钮
    - _Requirements: 1.2, 1.3, 1.4_

  - [x] 5.2 实现 ParameterForm 组件
    - 创建 `src/components/load-forecast/ParameterForm.tsx`
    - 使用 Ant Design Form 组件，必填字段：task_type（Select）、csv_path（Input）、parent_id（Input）、child_id（Input）
    - 可选字段：forecast_horizon（InputNumber, 默认 1, 正整数校验 min=1）、time_granularity（Select, 默认 "15min"）、separate_modeling（Switch, 默认 true）、forecast_start_time（TimePicker, 默认 "00:15"）
    - 实现表单校验：必填字段 `required: true`，forecast_horizon 正整数校验
    - 支持 `initialValues` prop 用于场景推荐配置自动填充和历史记录回填
    - 训练中禁用表单提交（`disabled` prop）
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 1.3, 9.2_

  - [ ]* 5.3 编写 ScenarioSelector 和 ParameterForm 的属性测试
    - **Property 3: Form validation rejects incomplete required fields**
    - **Property 4: forecast_horizon positive integer validation**
    - **Validates: Requirements 2.3, 2.4**

- [x] 6. 实现训练进度和日志组件
  - [x] 6.1 实现 ProgressTracker 组件
    - 创建 `src/components/load-forecast/ProgressTracker.tsx`
    - 使用 Ant Design Steps 组件展示四个训练步骤：数据获取、异常检测、特征工程、模型训练
    - 根据 `steps` 数组中每个步骤的 status 映射 Steps 组件状态：waiting→wait、running→process（带 LoadingOutlined）、completed→finish、error→error
    - 已完成步骤展示 step_durations 耗时（如 "12.5s"）
    - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_

  - [x] 6.2 实现 LogConsole 组件
    - 创建 `src/components/load-forecast/LogConsole.tsx`
    - 深色背景（#1e1e1e）、等宽字体（monospace）的终端风格面板
    - 日志条目根据 type 着色：start→高亮蓝色、success→绿色、error→红色、info→白色、config→灰色
    - 使用 `useRef` + `scrollIntoView` 实现自动滚动到最新日志
    - 训练开始时展示配置摘要（场景类型、数据源、关键参数）
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 6.3 编写日志格式化和步骤状态映射的属性测试
    - **Property 6: Step status mapping from API response**
    - **Property 7: Log entry formatting for step transitions**
    - **Property 8: Config summary contains key parameters**
    - **Validates: Requirements 4.3, 4.4, 5.2, 5.3, 5.4, 5.5, 5.7**

- [x] 7. 实现训练结果和回测组件
  - [x] 7.1 实现 ResultDashboard 组件
    - 创建 `src/components/load-forecast/ResultDashboard.tsx`
    - 训练成功时展示：model_id（带复制按钮）、总耗时、训练场景类型、训练时间
    - 使用 `navigator.clipboard.writeText` 实现复制 Model ID 功能
    - 展示"快速回测"按钮，点击触发 `onStartBacktest` 回调
    - 训练失败时展示 error_step 和 error_message，红色 Alert 样式
    - _Requirements: 6.1, 6.2, 6.5, 7.1_

  - [x] 7.2 实现 MetricsChart 组件
    - 创建 `src/components/load-forecast/MetricsChart.tsx`
    - 使用 echarts-for-react 渲染四种图表：
      - `step-duration-bar`：水平条形图展示各步骤耗时
      - `step-duration-pie`：饼图/环形图展示各步骤耗时占比
      - `backtest-line`：折线图展示每日预测值与实际值对比
      - `backtest-bar`：柱状图展示每日回测预测点数量分布
    - 数据异常时展示 Ant Design Empty 占位符
    - _Requirements: 6.3, 6.4, 7.3, 7.5_

  - [x] 7.3 实现 TrainingHistory 组件
    - 创建 `src/components/load-forecast/TrainingHistory.tsx`
    - 使用 Ant Design List 或 Table 展示当前会话训练记录：task_id、场景类型、状态（Tag 颜色区分）、model_id、总耗时
    - 点击记录触发 `onSelect` 回调，回填参数到 ParameterForm
    - _Requirements: 9.1, 9.2_

  - [ ]* 7.4 编写结果仪表盘和回测统计的属性测试
    - **Property 10: Step duration percentage calculation**
    - **Property 12: Backtest summary statistics**
    - **Validates: Requirements 6.4, 7.4**

- [x] 8. Checkpoint - 确保所有组件编译通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 实现页面组件并集成路由和导航
  - [x] 9.1 实现 LoadForecastTrainingPage 页面组件
    - 创建 `src/pages/LoadForecastTrainingPage.tsx`
    - 页面顶部展示标题"负荷预测训练"和功能简介
    - 使用 Ant Design Row/Col 布局：左侧 Col span=16（场景选择 + 参数配置 Card、训练进度 + 日志 Card、训练结果 Card），右侧 Col span=8（训练历史 Card、快速操作 Card）
    - 页面加载时调用 `store.fetchScenarios()` 获取场景列表
    - 根据训练状态条件渲染：idle 时展示配置区域，running 时展示进度和日志，success/failed 时展示结果仪表盘
    - 组合所有子组件：ScenarioSelector、ParameterForm、ProgressTracker、LogConsole、ResultDashboard、MetricsChart、TrainingHistory
    - _Requirements: 1.1, 3.1, 3.2, 3.3, 3.4, 3.5, 7.1, 7.2, 7.3, 7.4, 7.5, 8.2, 8.3, 9.3_

  - [x] 9.2 注册路由和侧边栏导航
    - 在 `src/App.tsx` 中添加 `<Route path="/load-forecast/training" element={<LoadForecastTrainingPage />} />` 路由
    - 在 `src/components/MainLayout.tsx` 侧边栏菜单中添加"负荷预测训练"菜单项（放在算法服务分组下）
    - 在 MainLayout Header 中添加 `/load-forecast/training` 路径对应的标题"负荷预测训练"
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 10. Final checkpoint - 确保所有代码编译通过并完成集成
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- 所有代码使用 TypeScript，遵循项目现有的 Ant Design + zustand + axios 模式
- 后端 API 已完整实现，前端仅需对接，不修改后端代码
- 日志格式化和步骤状态映射逻辑应提取为纯函数（放在 store 或 utils 中），便于属性测试
<!-- @AI_GENERATED: end -->
