<!-- @AI_GENERATED -->
# Requirements Document

## Introduction

精度运营（Accuracy Operations）是负荷预测算法平台的**上层运营编排层**，叠加在已有的部署/调度/精度基础设施之上。本模块新增两项核心能力：

1. **预测结果可视化**：多形态预测曲线 vs 真值、误差分布、滚动 MAPE 趋势、异常窗口标注、精度监控面板；
2. **精度劣化闭环**：退化监控 → 根因分析（含误差画像与可执行建议）→ 影子切换恢复（通道A）。

**关键范围约束**：
- RCA + 恢复动作仅作用于 `production`（生产）和 `shadow`（影子）两种形态；
- `prelaunch`（预上线）和 `AutoResearch` 仅做精度监控，不做 RCA 和恢复仲裁；
- 恢复仲裁器（RecoveryArbitrator）只执行通道A（影子切换），**不做训练重训（通道B已移除）**；
- 无达标影子时走 observe 通道，等待 AutoResearch 自然产出更好的影子；
- 所有持久化路径一律使用相对路径。

## Glossary

- **Accuracy_Operations_System**：精度运营编排层，包含 AccuracyMonitor、RCAOrchestrator、RecoveryArbitrator 三个核心组件
- **AccuracyMonitor**：精度监控组件，消费 accuracy_tracker 滚动指标，判定退化并生成告警
- **RCAOrchestrator**：根因分析编排组件，子进程调用 operation_skill，产出含误差画像与建议的 RCAReport
- **RecoveryArbitrator**：恢复仲裁组件，基于 RCA 结论和影子池状态走决策树，仅输出 shadow_switch 或 observe
- **AccuracyAlert**：精度告警实体，仅由 production/shadow 退化触发
- **RCAReport**：根因分析报告实体，包含根因结论、置信度、误差画像分析、数据质量诊断、可执行建议
- **RecoveryDecision**：恢复决策实体，记录仲裁选定的通道（shadow_switch 或 observe）及执行状态
- **ErrorProfile**：误差画像，包含时序误差分布、异常窗口标注、峰谷误差对比等统计信息
- **ActionableInsight**：可执行建议，包含建议类型、优先级、具体描述和数据支撑依据
- **Channel_A**：通道A，影子切换恢复通道，复用已有 switch_engine
- **switch_engine**：已有的影子切换引擎，提供 evaluate/execute_switch/rollback 能力
- **accuracy_tracker**：已有的精度跟踪模块，提供 get_rolling_metrics 等接口
- **version_registry**：已有的版本注册表，管理 production/shadow/retired 状态
- **config_manager**：已有的槽位配置模块，提供 degradation_threshold_pct/switch_margin_pct/cooldown_hours 等参数
- **operation_skill**：独立的 RCA 能力模块（conda 环境 cp_web），通过子进程调用
- **slot**：槽位，精度运营的分区键，对应一个部署环境/产品线
- **degradation_threshold_pct**：退化阈值百分比，滚动 MAPE 相对基线涨幅超此值触发告警
- **switch_margin_pct**：切换分差百分比，影子 MAPE 比生产低超此值视为达标
- **min_valid_cycles**：最小有效周期数，影子需积累足够周期才可参与切换
- **cooldown_hours**：冷却时间（小时），同一告警冷却期内不重复触发 RCA
- **confidence_gate**：置信度门控阈值（默认 0.6），RCA 置信度低于此值走观察通道

## Requirements

### Requirement 1: 精度退化监控

**User Story:** 作为运营人员，我希望系统自动监控生产和影子模型的精度退化情况，以便在精度下降时及时发现问题。

#### Acceptance Criteria

1. WHEN scheduler（调度器）定时触发 evaluate(slot), THE AccuracyMonitor SHALL 从 accuracy_tracker 获取 production 和 shadow 形态中 status 为 active 的滚动 MAPE 指标
2. WHEN production 或 shadow 形态的滚动 MAPE 满足退化公式 (current_rolling_mape - baseline_mape) / baseline_mape × 100 >= config_manager 中的 degradation_threshold_pct, THE AccuracyMonitor SHALL 生成一条 AccuracyAlert（status=open），其中 baseline_mape 取自 version_registry 中该版本的注册基线值，若注册基线值不存在则回退使用 accuracy_tracker 当前的 rolling_mape
3. WHILE slot 下已存在同一 model_form 加 workflow_id 的 open 状态 AccuracyAlert, THE AccuracyMonitor SHALL 不重复生成新告警（告警去重）
4. WHEN 监控到 prelaunch 或 AutoResearch 形态的精度数据, THE AccuracyMonitor SHALL 仅输出监控快照到 monitoring/snapshot 响应，不生成 AccuracyAlert
5. THE AccuracyAlert SHALL 仅包含 model_form 为 production 或 shadow 的告警记录
6. IF accuracy_tracker 对某一形态返回空数据或该形态的 status 不为 active, THEN THE AccuracyMonitor SHALL 跳过该形态的退化判定，不生成告警且不抛出异常

### Requirement 2: 根因分析编排

**User Story:** 作为运营人员，我希望系统在检测到生产/影子精度退化后自动触发根因分析，以便了解退化原因并获得可执行的改善建议。

#### Acceptance Criteria

1. WHEN AccuracyMonitor 生成 production 或 shadow 退化告警, THE RCAOrchestrator SHALL 将该 alert 状态置为 rca_running 并触发根因分析流程
2. WHILE 同一 alert 处于 cooldown_until 冷却期内, THE RCAOrchestrator SHALL 幂等返回既有 RCAReport，不重复执行 RCA
3. WHEN RCAOrchestrator 执行分析, THE RCAOrchestrator SHALL 通过子进程（conda run -n cp_web）依次调用 operation_skill 的 run_collect 和 run_report 脚本，工作目录为项目根下的 operation_skill/
4. WHEN operation_skill 子进程执行成功, THE RCAOrchestrator SHALL 产出 RCAReport，包含 root_cause（根因结论）、confidence（置信度 0.0~1.0）、error_profile（误差画像）、data_quality_diagnosis（数据质量诊断）、actionable_insights（可执行建议列表）以及 status 为 succeeded
5. IF operation_skill 子进程执行超时（900 秒）, THEN THE RCAOrchestrator SHALL 设置 RCAReport.status 为 timeout，不触发恢复仲裁，告警回退为 open
6. IF operation_skill 子进程执行失败且以 5 秒、15 秒退避间隔重试共 2 次仍失败, THEN THE RCAOrchestrator SHALL 设置 RCAReport.status 为 failed，不触发恢复仲裁
7. WHEN RCA 触发方式为 manual（手动）, THE RCAOrchestrator SHALL 忽略 cooldown_until 冷却期限制，对指定 alert 执行根因分析流程并产出新的 RCAReport

### Requirement 3: RCA 诊断输出——误差画像与可执行建议

**User Story:** 作为算法工程师，我希望 RCA 报告包含详细的误差画像分析和具体可执行的改善建议，以便不需要重训也能从报告中获取有价值的信息指导后续 AutoResearch 方向。

#### Acceptance Criteria

1. THE RCAReport.error_profile SHALL 包含以下误差统计信息：mape_by_hour（按小时分组的平均 MAPE，24 个时段）、mape_by_weekday（按星期分组，7 天）、worst_windows（MAPE 最高的前 5 个时间窗口，含起止时间和误差值）、error_bias（预测偏差方向，over_forecast/under_forecast/balanced）、peak_valley_error_ratio（峰时段误差 vs 谷时段误差比值）
2. THE RCAReport.data_quality_diagnosis SHALL 包含以下诊断信息：missing_rate（缺失率）、outlier_rate（异常值率）、feature_drift_detected（特征漂移是否检测到，bool）、feature_drift_details（漂移特征名和漂移幅度列表，可为空）、data_freshness_lag_hours（数据时效滞后小时数，用于诊断数据延迟问题）
3. THE RCAReport.actionable_insights SHALL 包含至少 1 条可执行建议，每条建议含：insight_type（建议类型，枚举 feature_engineering/data_sourcing/model_retraining_signal/observation/hyperparameter_hint）、priority（优先级，枚举 high/medium/low）、description（具体建议文本，中文）、supporting_evidence（支撑数据依据，字符串列表）
4. WHEN root_cause 为 data_gap 或 feature_broken, THE RCAReport.actionable_insights SHALL 包含至少 1 条 insight_type 为 data_sourcing 或 feature_engineering 的建议
5. WHEN error_profile 显示 mape_by_hour 中某时段误差显著高于均值（超过 1.5 倍均值）, THE RCAReport.actionable_insights SHALL 包含针对该时段的 hyperparameter_hint 或 feature_engineering 类型建议
6. WHEN data_quality_diagnosis.feature_drift_detected 为 true, THE RCAReport.actionable_insights SHALL 包含至少 1 条 insight_type 为 feature_engineering 的建议，描述中必须点名漂移特征

### Requirement 4: 恢复仲裁决策（仅通道A）

**User Story:** 作为运营人员，我希望系统根据 RCA 结论和影子池状态自动做出切换决策，有达标影子就切换，没有就等待 AutoResearch 自然产出更好的影子。

#### Acceptance Criteria

1. WHEN RCAOrchestrator 产出 succeeded 状态的 RCAReport, THE RecoveryArbitrator SHALL 读取 version_registry 的影子池状态和 accuracy_tracker 的影子精度并执行仲裁决策
2. THE RecoveryArbitrator SHALL 仅读取 version_registry（影子池）和 accuracy_tracker（精度），不读取 AutoResearch 候选池或复验池或知识层
3. IF RCAReport.confidence 低于 confidence_gate（0.6）或 undetermined 为 true, THEN THE RecoveryArbitrator SHALL 输出 channel 为 observe 的 RecoveryDecision（观察加人工），SLA 为 12 小时
4. WHEN RCA 根因分类为 external（外部因素或事件突变）, THE RecoveryArbitrator SHALL 输出 channel 为 observe 的 RecoveryDecision，SLA 为 12 小时
5. WHEN 存在达标影子（无论根因类型，external 和 undetermined 除外）, THE RecoveryArbitrator SHALL 输出 channel 为 shadow_switch 的 RecoveryDecision，SLA 为 2 小时
6. WHEN 不存在达标影子（无论根因类型，external 和 undetermined 除外）, THE RecoveryArbitrator SHALL 输出 channel 为 observe 的 RecoveryDecision，decision_reason 注明"无达标影子，等待 AutoResearch 产出"，SLA 为 12 小时
7. THE RecoveryDecision SHALL 必须引用一个已存在的 RCAReport（rca_report_id 对应的记录必须存在）
8. IF version_registry 或 accuracy_tracker 服务不可达, THEN THE RecoveryArbitrator SHALL 输出 channel 为 observe 的 RecoveryDecision 并在 decision_reason 中注明依赖不可用

### Requirement 5: 影子达标判定

**User Story:** 作为运营人员，我希望系统基于客观指标判定影子是否达标可切换，以便仲裁器做出可靠决策。

#### Acceptance Criteria

1. WHEN RecoveryArbitrator 评估影子是否达标, THE RecoveryArbitrator SHALL 以相对百分比公式 (prod_rolling_mape - shadow_rolling_mape) / prod_rolling_mape × 100 计算影子优于生产的幅度，并判定该幅度是否大于等于 config_manager 中的 switch_margin_pct（默认 10%）
2. WHEN RecoveryArbitrator 评估影子是否达标, THE RecoveryArbitrator SHALL 判定该影子在 accuracy_tracker 中记录的 valid_cycle_count 是否大于等于 config_manager 中的 min_valid_cycles（默认 3）
3. WHEN 存在多个达标影子, THE RecoveryArbitrator SHALL 选择 rolling_mape 最低的影子作为切换目标；若多个影子 rolling_mape 相同，则选择 valid_cycle_count 较大者
4. IF 生产模型在 accuracy_tracker 中无 active 状态的滚动指标, THEN THE RecoveryArbitrator SHALL 判定无达标影子并返回 observe 决策

### Requirement 6: 通道A 影子切换执行与回滚

**User Story:** 作为运营人员，我希望通道A 复用已有的 switch_engine 执行影子切换，切换后自动观察精度是否改善，未改善则回滚。

#### Acceptance Criteria

1. WHEN RecoveryDecision.channel 为 shadow_switch, THE Accuracy_Operations_System SHALL 调用 switch_engine.execute_switch(slot, target_workflow_id) 执行切换，切换成功后将 AccuracyAlert.status 迁移为 recovering
2. IF 切换后经过至少 1 个完整评估周期，switch_engine.evaluate_post_switch 判定精度未改善或更差, THEN THE Accuracy_Operations_System SHALL 调用 switch_engine.rollback(slot) 回滚，AccuracyAlert.status 回退为 open
3. IF RecoveryDecision 超过 SLA 截止时间（2 小时）且精度未恢复, THEN THE Accuracy_Operations_System SHALL 尝试 rollback，回滚成功后告警回到 open 状态等待人工介入或重新触发 RCA
4. WHILE 同一 slot 已有通道A 正在执行（RecoveryDecision.status 为 executing）且未达 SLA, THE RecoveryArbitrator SHALL 禁止对该 slot 再次触发通道A，直接返回 observe 决策

### Requirement 7: 告警生命周期管理

**User Story:** 作为运营人员，我希望告警有清晰的生命周期，以便追踪从检测到恢复的完整过程。

#### Acceptance Criteria

1. WHEN RCAOrchestrator 接受 AccuracyAlert 并启动 RCA 子进程, THE Accuracy_Operations_System SHALL 将该 AccuracyAlert.status 从 open 更新为 rca_running
2. WHEN RecoveryDecision 产出且 channel 为 shadow_switch 并开始执行, THE Accuracy_Operations_System SHALL 将 AccuracyAlert.status 从 rca_running 更新为 recovering
3. WHEN RecoveryDecision.channel 为 observe, THE Accuracy_Operations_System SHALL 将 AccuracyAlert.status 从 rca_running 更新为 observing
4. WHEN 恢复后精度复核判定滚动 MAPE 回落至退化阈值以下（passed）或运营人员手动关闭, THE Accuracy_Operations_System SHALL 将 AccuracyAlert.status 更新为 closed，且 recovery_evidence 字段必须包含 type 为 passed 或 manual_close 的证据
5. THE AccuracyAlert SHALL 不可在 recovery_evidence 为空时被设置为 closed 状态
6. IF RCA 执行失败或超时或切换后回滚, THEN THE Accuracy_Operations_System SHALL 将 AccuracyAlert.status 回退为 open，允许重新触发 RCA 或人工介入
7. THE AccuracyAlert.status 迁移 SHALL 仅允许以下合法路径：open → rca_running → recovering → closed；open → rca_running → observing → closed；失败回退至 open 除外，不允许跳跃或逆向迁移

### Requirement 8: 持久化路径规范

**User Story:** 作为开发人员，我希望所有精度运营的持久化数据使用相对路径存储，以便项目在不同环境间可迁移。

#### Acceptance Criteria

1. THE Accuracy_Operations_System SHALL 将所有持久化路径存储为相对于 backend-service 目录的相对路径
2. THE Accuracy_Operations_System SHALL 不使用 os.path.abspath() 写入持久化字段；所有路径字段在写入前必须通过 os.path.relpath(path, start=backend_service_dir) 转换
3. WHEN 存储 RCAReport.artifacts_dir 等文件路径字段, THE Accuracy_Operations_System SHALL 验证 not os.path.isabs(path)，验证失败则抛出 ValueError
4. THE Accuracy_Operations_System SHALL 将精度运营数据落在 data/precision_ops/{slot}/accuracy_ops/ 目录下，slot 名称仅允许包含小写字母、数字、下划线和连字符

### Requirement 9: HTTP API 接口

**User Story:** 作为前端开发人员，我希望精度运营提供完整的 REST API，以便前端页面获取数据和触发操作。

#### Acceptance Criteria

1. THE Accuracy_Operations_System SHALL 在 /api/accuracy-operations/overview 提供运营总览接口（GET），接受必填 query `slot`，返回四形态节点、精度快照、open 告警数、活跃恢复决策数
2. THE Accuracy_Operations_System SHALL 在 /api/accuracy-operations/alerts 提供告警列表接口（GET），接受必填 `slot` 和可选 `status`，单次最多 200 条
3. THE Accuracy_Operations_System SHALL 在 /api/accuracy-operations/alerts/{alert_id}/rca 提供幂等 RCA 触发接口（POST），冷却期内返回既有报告；alert_id 不存在或非 production/shadow 返回错误
4. THE Accuracy_Operations_System SHALL 在 /api/accuracy-operations/rca/{rca_report_id} 提供 RCA 报告详情接口（GET），返回完整 RCAReport（含 error_profile、data_quality_diagnosis、actionable_insights）
5. THE Accuracy_Operations_System SHALL 在 /api/accuracy-operations/recovery/decide 提供仲裁触发接口（POST），接受 slot + rca_report_id，返回 RecoveryDecision；RCAReport 不存在或非 succeeded 返回错误
6. THE Accuracy_Operations_System SHALL 在 /api/accuracy-operations/recovery/shadow-switch 提供手动通道A 接口（POST），接受 slot、shadow_workflow_id、decision_id
7. THE Accuracy_Operations_System SHALL 在 /api/accuracy-operations/monitoring/snapshot 提供精度监控快照接口（GET），返回所有形态滚动 MAPE 与 valid_cycle_count
8. THE Accuracy_Operations_System SHALL 在 /api/accuracy-operations/models/lifecycle 提供四形态生命周期视图接口（GET），返回 nodes[] + edges[]

### Requirement 10: 前端精度运营可视化页面

**User Story:** 作为运营人员，我希望有一个集中的可视化页面查看精度状态、告警、RCA 诊断报告和恢复决策，以便高效完成日常运营工作。

#### Acceptance Criteria

1. THE Accuracy_Operations_System SHALL 在 /accuracy-operations 路由提供精度运营页面，页面顶部提供 slot 选择器，默认加载 default 槽位数据
2. WHEN 用户打开页面, THE Accuracy_Operations_System SHALL 展示四形态生命周期卡片（ModelLifecycleCard）
3. WHEN 用户查看精度趋势, THE Accuracy_Operations_System SHALL 展示滚动 MAPE 趋势图（多形态对比）、预测值 vs 真值曲线、误差分布图
4. WHEN 用户查看 RCA 报告, THE Accuracy_Operations_System SHALL 展示完整诊断内容：根因结论、置信度、误差画像（按小时/星期分布热力图/柱图）、数据质量诊断、可执行建议列表（含优先级标签）
5. WHEN 用户查看告警面板, THE Accuracy_Operations_System SHALL 仅展示 model_form 为 production 或 shadow 的告警
6. WHEN 用户触发手动影子切换, THE Accuracy_Operations_System SHALL 弹出 ShadowSwitchModal 确认弹窗，展示目标影子 vs 当前生产的 MAPE 对比
7. IF 页面加载失败, THE Accuracy_Operations_System SHALL 在对应面板展示错误提示 + 重试入口，其余面板不受影响
8. IF 当前槽位无数据, THE Accuracy_Operations_System SHALL 展示空态占位提示

### Requirement 11: RCA skill 调用契约

**User Story:** 作为后端开发人员，我希望 RCA skill 调用有明确的契约规范。

#### Acceptance Criteria

1. WHEN RCAOrchestrator 调用 operation_skill, THE Accuracy_Operations_System SHALL 按 examples/rca_input_sample.json schema 拼接输入 JSON 写入 operation_skill/ 工作目录
2. WHEN run_collect 和 run_report 均返回退出码 0, THE Accuracy_Operations_System SHALL 将产出的 rca_decision.json 和 .html 报告拷回 data/precision_ops/{slot}/accuracy_ops/rca/{rca_report_id}/ 目录
3. THE Accuracy_Operations_System SHALL 设置每个子进程独立超时 900 秒，任一超时则整个 RCA 标记 timeout
4. IF 子进程返回非零退出码, THEN THE Accuracy_Operations_System SHALL 按 5s/15s 退避重试 2 次
5. THE Accuracy_Operations_System SHALL 在 conda 环境 cp_web 下以 operation_skill/ 为工作目录执行子进程

### Requirement 12: 数据模型完整性

**User Story:** 作为开发人员，我希望精度运营的数据模型有明确的结构和约束。

#### Acceptance Criteria

1. THE AccuracyAlert SHALL 包含 alert_id（格式 alert-{8hex}）、slot、model_form（仅 production/shadow）、workflow_id、baseline_mape、current_rolling_mape、degradation_pct、status（open/rca_running/recovering/observing/closed）、created_at 字段
2. THE RCAReport SHALL 包含 rca_report_id（格式 rca-{8hex}）、alert_id、root_cause、confidence（0.0~1.0）、error_profile（误差画像 dict）、data_quality_diagnosis（数据质量诊断 dict）、actionable_insights（可执行建议列表）、status（running/succeeded/failed/timeout）字段
3. THE RecoveryDecision SHALL 包含 decision_id（格式 rec-{8hex}）、alert_id、rca_report_id、channel（shadow_switch 或 observe）、status（pending/executing/succeeded/failed/rolled_back）、sla_deadline 字段
4. THE RecoveryDecision.channel SHALL 仅取值 shadow_switch（通道A）或 observe（观察）之一；**不再支持 training_adjust 和 parallel 通道**
<!-- @AI_GENERATED: end -->
