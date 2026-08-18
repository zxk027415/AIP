<!-- @AI_GENERATED -->
# Implementation Plan: 精度运营（Accuracy Operations）

## Overview

本实现计划将精度运营编排层分解为可增量交付的编码任务。后端使用 Python（FastAPI，conda `aip_web`），前端使用 React + TypeScript + Vite + AntD（目录 `frontend-sevice`）。

**范围说明**：
- 仅实现通道A（影子切换），**不实现通道B（训练重训）**
- RCA 输出强化为诊断报告：误差画像、数据质量诊断、可执行建议
- 无达标影子时走 observe 通道，等 AutoResearch 自然产出更好的影子

所有持久化路径一律相对路径（相对 `backend-service/`）。复用已有 `switch_engine`、`accuracy_tracker`、`version_registry`、`config_manager`、`scheduler/engine`，不重建。

## Tasks

- [ ] 1. 数据模型与持久化层
  - [ ] 1.1 创建 Pydantic 数据模型 `backend-service/services/accuracy_operations/models.py`
    - 定义 `AccuracyAlert`（含 `alert_id` — 告警ID格式 `alert-{8hex}`、`slot` — 槽位、`model_form` — 形态枚举 production/shadow、`workflow_id`、`version_tag`、`baseline_mape`、`current_rolling_mape`、`degradation_pct`、`degradation_trend` — sudden/gradual/stable、`severity` — warning/critical、`status` — open/rca_running/recovering/observing/closed、`cooldown_until`、`rca_report_id`、`recovery_decision_id`、`recovery_evidence`、`created_at`/`updated_at`）
    - 定义 `ErrorProfile`（误差画像：`mape_by_hour` — 24小时分组MAPE dict、`mape_by_weekday` — 7天分组MAPE dict、`worst_windows` — 最差5个窗口列表、`error_bias` — over_forecast/under_forecast/balanced、`peak_valley_error_ratio` — 峰谷误差比）
    - 定义 `DataQualityDiagnosis`（数据质量诊断：`missing_rate`、`outlier_rate`、`feature_drift_detected` bool、`feature_drift_details` — 漂移特征列表、`data_freshness_lag_hours` — 数据时效滞后小时数）
    - 定义 `ActionableInsight`（可执行建议：`insight_type` — 枚举 feature_engineering/data_sourcing/model_retraining_signal/observation/hyperparameter_hint、`priority` — high/medium/low、`description` — 中文具体建议、`supporting_evidence` — 依据列表）
    - 定义 `RCAReport`（含 `rca_report_id` — 格式 `rca-{8hex}`、`alert_id`、`trigger_type` — scheduled/alert/manual、`root_cause`、`confidence` — 0.0~1.0、`reasoning`、`supporting_evidence`、`undetermined` bool、`error_profile` ErrorProfile可选、`data_quality_diagnosis` DataQualityDiagnosis可选、`actionable_insights` — ActionableInsight列表、`artifacts_dir`、`status` — running/succeeded/failed/timeout、`created_at`）
    - 定义 `RecoveryDecision`（含 `decision_id` — 格式 `rec-{8hex}`、`alert_id`、`rca_report_id`、`channel` — **仅 shadow_switch/observe 两个值**、`decision_reason`、`confidence_gate_passed` bool、`switch_event_id` 可选、`sla_deadline`、`rollback_of` 可选、`status` — pending/executing/succeeded/failed/rolled_back、`created_at`/`updated_at`）
    - 添加 ID 生成辅助函数（`secrets.token_hex(4)` 拼前缀）
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

  - [ ] 1.2 创建持久化 store 模块 `backend-service/services/accuracy_operations/store.py`
    - 实现 `AccuracyOperationsStore` 类，负责 alerts/rca/recovery 的 JSON 读写（**不再有 training_tasks**）
    - 所有路径使用 `os.path.relpath(path, start=backend_service_dir)` 转换，禁止 `os.path.abspath()`
    - 存储目录：`data/precision_ops/{slot}/accuracy_ops/alerts/{alert_id}.json`、`rca/{rca_report_id}.json`、`recovery/{decision_id}.json`
    - slot 名称校验：仅允许小写字母、数字、下划线和连字符
    - 路径写入前校验 `not os.path.isabs(path)`，违反则抛 ValueError
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [ ] 1.3 创建包入口 `backend-service/services/accuracy_operations/__init__.py`
    - 导出核心组件：AccuracyMonitor、RCAOrchestrator、RecoveryArbitrator、AccuracyOperationsStore
    - _Requirements: 8.1_

  - [ ]* 1.4 Write property test for data model serialization round-trip
    - **Property: 数据模型序列化 round-trip**
    - 使用 hypothesis 生成合法的 AccuracyAlert / RCAReport / RecoveryDecision 实例，序列化为 JSON 再反序列化应产出等价对象
    - **Validates: Requirements 12.1, 12.2, 12.3**

  - [ ]* 1.5 Write property test for relative path enforcement
    - **Property: 持久化路径均为相对路径**
    - 使用 hypothesis 验证 store 写入的所有路径满足 `not os.path.isabs(path)`
    - **Validates: Requirements 8.1, 8.4**

- [ ] 2. Checkpoint - 数据模型与持久化层验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 3. AccuracyMonitor 精度监控组件
  - [ ] 3.1 实现 `backend-service/services/accuracy_operations/monitor.py`
    - 创建 `AccuracyMonitor` 类，注入 `accuracy_tracker`、`version_registry`、`config_manager`、`store`
    - 实现 `evaluate(slot)` 方法：对 production 和 shadow 做退化检测
    - 退化公式：`(current_rolling_mape - baseline_mape) / baseline_mape * 100 >= config.degradation_threshold_pct`
    - baseline_mape 取自 version_registry 注册基线值，若不存在回退使用 accuracy_tracker 当前 rolling_mape
    - 对 prelaunch/AutoResearch 只输出监控快照，不生成 AccuracyAlert
    - 告警去重：同 slot + model_form + workflow_id 已有 open alert 则不重复生成
    - accuracy_tracker 返回空数据或 status 不为 active 时跳过，不抛异常
    - severity 分级：degradation_pct >= 2 × threshold → critical，否则 → warning
    - degradation_trend 判定：sudden（单周期骤升）/ gradual（多周期渐升）/ stable（持续高位）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 3.2 Write property test for alert form restriction
    - **Property: 告警仅限 production/shadow 形态**
    - 验证 AccuracyMonitor 对 prelaunch/AutoResearch 不产出 AccuracyAlert
    - **Validates: Requirements 1.4, 1.5**

  - [ ]* 3.3 Write property test for degradation threshold correctness
    - **Property: 退化阈值触发正确性**
    - 当且仅当退化公式成立时产出告警
    - **Validates: Requirement 1.2**

  - [ ]* 3.4 Write property test for alert deduplication
    - **Property: 告警去重（幂等性）**
    - 已有 open alert 时重复调用 evaluate 不增加告警
    - **Validates: Requirement 1.3**

- [ ] 4. RCAOrchestrator 根因分析编排
  - [ ] 4.1 实现 RCA skill 调用封装 `backend-service/services/accuracy_operations/rca_skill_client.py`
    - 封装子进程调用：拼 rca_input JSON（按 `examples/rca_input_sample.json` schema）
    - 命令：`conda run -n cp_web python scripts/run_collect.py` 和 `run_report.py`
    - 工作目录：项目根下 `operation_skill/`
    - 超时 900s per script，重试 2 次（5s/15s 退避），失败返回 timeout/failed 状态
    - 收 artifacts（rca_decision.json + HTML 报告）拷回 `data/precision_ops/{slot}/accuracy_ops/rca/{id}/`
    - **解析 rca_decision.json 时提取 error_profile、data_quality_diagnosis、actionable_insights 字段**，映射为 Pydantic 模型；若 skill 未产出这些字段则以空值填充，不报错
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ] 4.2 实现 `backend-service/services/accuracy_operations/rca_orchestrator.py`
    - 创建 `RCAOrchestrator` 类，注入 `rca_skill_client`、`store`
    - 冷却/去重逻辑：同一 alert 在 cooldown_until 期内幂等返回既有 RCAReport
    - manual 触发忽略冷却期
    - 触发时将 alert 状态迁移为 rca_running
    - 子进程成功 → RCAReport（status=succeeded，含 error_profile/data_quality_diagnosis/actionable_insights）
    - 失败/超时 → status=failed/timeout，alert 状态回退为 open
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 7.1, 7.6_

  - [ ]* 4.3 Write property test for RCA cooldown idempotency
    - **Property: RCA 冷却期幂等性**
    - 冷却期内重复触发返回既有 RCAReport，数量 ≤ 1
    - **Validates: Requirements 2.2**

- [ ] 5. Checkpoint - 监控与 RCA 组件验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. RecoveryArbitrator 恢复仲裁（仅通道A）
  - [ ] 6.1 实现 `backend-service/services/accuracy_operations/arbitrator.py`
    - 创建 `RecoveryArbitrator` 类，注入 `version_registry`、`accuracy_tracker`、`config_manager`、`switch_engine`、`store`
    - **不注入 training_adjuster，无通道B逻辑**
    - 置信度门控：`confidence < 0.6` 或 `undetermined=true` → channel=observe（SLA=12h）
    - root_cause = external → channel=observe（SLA=12h）
    - 其他情况：有达标影子 → shadow_switch（SLA=2h）；无达标影子 → observe，reason="无达标影子，等待 AutoResearch 产出"
    - 影子达标判定：`(prod_mape - shadow_mape) / prod_mape * 100 >= switch_margin_pct` 且 `valid_cycle_count >= min_valid_cycles`
    - 多达标影子选最低 rolling_mape，相同则选 valid_cycle_count 较大者
    - RecoveryDecision 必须引用已存在 RCAReport
    - 同 slot 已有 executing 的 shadow_switch 决策 → 返回 observe，不重复触发
    - 依赖不可达 → channel=observe，注明原因
    - 决策后将 alert 状态迁移：shadow_switch → recovering；observe → observing
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1, 5.2, 5.3, 5.4_

  - [ ]* 6.2 Write property test for decision tree correctness
    - **Property: 仲裁决策树正确性**
    - 验证：undetermined/low_confidence → observe；external → observe；有达标影子 → shadow_switch；无达标影子 → observe
    - **Validates: Requirements 4.3, 4.4, 4.5, 4.6**

  - [ ]* 6.3 Write property test for shadow qualification correctness
    - **Property: 影子达标判定正确性**
    - 验证达标公式和最优影子选择逻辑
    - **Validates: Requirements 5.1, 5.2, 5.3**

- [ ] 7. 通道A 执行与回滚集成
  - [ ] 7.1 在 arbitrator.py 中实现通道A 执行逻辑
    - 调用 `switch_engine.execute_switch(slot, target_workflow_id)` 执行切换，更新 RecoveryDecision.status=executing
    - 切换后经评估周期，`switch_engine.evaluate_post_switch` 判定精度未改善 → 调用 `switch_engine.rollback(slot)`，alert 回到 open
    - SLA 超时（2h）且精度未恢复 → 尝试 rollback，告警回到 open 等待人工介入
    - 同 slot 已有 shadow_switch executing → 拒绝重复触发
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 8. 告警生命周期管理
  - [ ] 8.1 在 store.py 中实现告警状态迁移校验
    - 合法路径：open → rca_running → recovering → closed；open → rca_running → observing → closed；失败回退至 open
    - 关闭时 recovery_evidence 必须非空且 type ∈ {passed, manual_close}
    - 状态迁移函数加校验，非法迁移抛 ValueError
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 8.2 Write property test for alert closure requires evidence
    - **Property: 告警关闭必须有 recovery evidence**
    - **Validates: Requirements 7.4, 7.5**

  - [ ]* 8.3 Write property test for alert state transition legality
    - **Property: 告警状态迁移合法性**
    - **Validates: Requirements 7.1, 7.2, 7.3**

- [ ] 9. Checkpoint - 核心编排层完整验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. HTTP API 路由层
  - [ ] 10.1 创建 `backend-service/api/accuracy_operations.py` 路由模块
    - 定义 FastAPI APIRouter，前缀 `/api/accuracy-operations`
    - `GET /overview`：运营总览，必填 query `slot`
    - `GET /alerts`：告警列表，必填 `slot`，可选 `status`，最多 200 条
    - `POST /alerts/{alert_id}/rca`：幂等 RCA 触发
    - `GET /rca/{rca_report_id}`：RCA 报告详情（**包含 error_profile、data_quality_diagnosis、actionable_insights**）
    - `POST /recovery/decide`：仲裁触发，必填 `slot` + `rca_report_id`
    - `POST /recovery/shadow-switch`：手动通道A，接受 `slot`、`shadow_workflow_id`、`decision_id`
    - `GET /monitoring/snapshot`：精度监控快照，必填 `slot`
    - `GET /models/lifecycle`：四形态生命周期视图
    - **移除 POST /recovery/training-adjust（通道B已移除）**
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

  - [ ] 10.2 在 `backend-service/main.py` 中注册精度运营路由
    - 导入 `api.accuracy_operations` 路由并 include_router
    - _Requirements: 9.1_

- [ ] 11. Checkpoint - API 层验证
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. 前端类型与 API 客户端
  - [ ] 12.1 创建前端类型定义 `frontend-sevice/src/types/accuracy-operations.ts`
    - 定义 TypeScript 类型：AccuracyAlert、ErrorProfile、DataQualityDiagnosis、ActionableInsight、RCAReport、RecoveryDecision、MonitoringSnapshot、LifecycleNode、LifecycleEdge、OverviewResponse、AlertsResponse
    - RecoveryDecision.channel 类型为 `'shadow_switch' | 'observe'`（**不包含 training_adjust 和 parallel**）
    - 与后端 Pydantic 模型字段一一对应（camelCase 转换）
    - _Requirements: 12.1, 12.2, 12.3_

  - [ ] 12.2 创建 API 客户端 `frontend-sevice/src/services/accuracyOperationsApi.ts`
    - 封装所有端点：getOverview、getAlerts、triggerRCA、getRCAReport、triggerDecision、executeShadowSwitch、getLifecycle、getMonitoringSnapshot
    - **移除 executeTrainingAdjust**
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

  - [ ] 12.3 创建 Zustand store `frontend-sevice/src/stores/accuracyOperationsStore.ts`
    - 管理状态：currentSlot、overview、alerts、selectedAlert、rcaReport、monitoringSnapshot、lifecycle、loading/error
    - actions：fetchOverview、fetchAlerts、triggerRCA、fetchRCAReport、triggerDecision、fetchMonitoringSnapshot、fetchLifecycle
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 13. 前端精度运营页面组件
  - [ ] 13.1 创建主页面 `frontend-sevice/src/pages/AccuracyOperationsPage.tsx`
    - slot 选择器，默认 default 槽位
    - 组合所有子组件，API 失败时对应面板展示错误+重试，其余不受影响
    - _Requirements: 10.1, 10.7, 10.8_

  - [ ] 13.2 实现 ModelLifecycleCard 组件
    - 展示四形态生命周期卡片（GET /models/lifecycle）
    - _Requirements: 10.2_

  - [ ] 13.3 实现 AccuracyTrendChart 组件（ECharts）
    - 滚动 MAPE 趋势图（多形态对比）
    - PredictionVsActual 子图、ErrorDistribution 子图
    - _Requirements: 10.3_

  - [ ] 13.4 实现 MonitoringPanel 组件
    - GET /monitoring/snapshot，展示所有形态 MAPE/MAE，只读
    - _Requirements: 10.5_

  - [ ] 13.5 实现 AlertPanel 组件
    - GET /alerts，仅展示 production/shadow 告警
    - _Requirements: 10.5_

  - [ ] 13.6 实现 RCAReportViewer 组件（核心新增）
    - 展示根因结论（root_cause）、置信度进度条（confidence）
    - **误差画像面板**：mape_by_hour 柱状图（ECharts 24 bars）、mape_by_weekday 柱状图、worst_windows 列表、error_bias 标签、peak_valley_error_ratio
    - **数据质量诊断面板**：missing_rate/outlier_rate 进度条、feature_drift_detected 状态徽章、feature_drift_details 表格（特征名 + 漂移幅度）、data_freshness_lag_hours
    - **可执行建议列表**：按 priority 排序（high → medium → low），每条含 insight_type 图标标签、description 文本、supporting_evidence 折叠展示
    - _Requirements: 10.4_

  - [ ] 13.7 实现 RecoveryDecisionPanel 和 ShadowSwitchModal 组件
    - RecoveryDecisionPanel：展示 channel（仅 shadow_switch 或 observe）、reason、SLA 倒计时
    - ShadowSwitchModal：确认弹窗展示目标影子 vs 当前生产 MAPE 对比，确认后调 POST /recovery/shadow-switch
    - **移除 TrainingAdjustModal**
    - _Requirements: 10.6_

  - [ ] 13.8 在 App.tsx 中注册 /accuracy-operations 路由
    - 添加路由指向 AccuracyOperationsPage
    - 在 MainLayout 导航中添加精度运营入口
    - _Requirements: 10.1_

- [ ] 14. Checkpoint - 前端构建验证
  - Ensure all tests pass, ask the user if questions arise.
  - 运行 `cd frontend-sevice && npm run build` 确认 TypeScript 类型无误、构建成功

- [ ] 15. 集成与端到端连接
  - [ ] 15.1 调度器集成：注册精度监控定时任务
    - 在 `services/scheduler/engine.py` 注册精度监控 cron job
    - 定时调用 `AccuracyMonitor.evaluate(slot)` 对所有活跃 slot
    - _Requirements: 1.1_

  - [ ] 15.2 RCA → 仲裁 → 切换自动化串联
    - AccuracyMonitor 产出 alert → 自动触发 RCAOrchestrator
    - RCA succeeded → 自动触发 RecoveryArbitrator.decide()
    - 仲裁 channel=shadow_switch → 执行 switch_engine（通道A）
    - 仲裁 channel=observe → 仅更新状态，等人工或下次监控
    - _Requirements: 2.1, 4.1, 6.1_

- [ ] 16. Final checkpoint - 全量验证
  - Ensure all tests pass, ask the user if questions arise.
  - 后端：`cd backend-service && PYTHONPATH=. conda run -n aip_web pytest tests/test_accuracy_operations*.py -q`
  - 前端：`cd frontend-sevice && npm run build`

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 后端所有代码文件顶/底加 `# @AI_GENERATED` 标记
- 前端 TypeScript 文件同样加 `// @AI_GENERATED` 注释标记
- 所有持久化路径必须为相对路径（相对 `backend-service/`），禁止 `os.path.abspath()`
- **通道B（TrainingStrategyAdjuster）已从本次实现范围移除**，留待后续评估
- 无达标影子时 observe 通道是正确行为，依赖 AutoResearch 自然演进
- RCA 诊断输出（ErrorProfile、DataQualityDiagnosis、ActionableInsight）是核心价值，即使不执行切换也应完整呈现

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "4.1"] },
    { "id": 4, "tasks": ["4.2", "4.3"] },
    { "id": 5, "tasks": ["6.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "7.1"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["8.2", "8.3", "10.1"] },
    { "id": 9, "tasks": ["10.2", "12.1"] },
    { "id": 10, "tasks": ["12.2", "12.3"] },
    { "id": 11, "tasks": ["13.1", "13.2", "13.3", "13.4", "13.5"] },
    { "id": 12, "tasks": ["13.6", "13.7", "13.8"] },
    { "id": 13, "tasks": ["15.1", "15.2"] }
  ]
}
```
<!-- @AI_GENERATED: end -->
