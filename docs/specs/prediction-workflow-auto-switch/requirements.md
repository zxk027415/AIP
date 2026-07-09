# 需求文档

## 介绍

本需求描述负荷预测"AIP精度运营"模块中的**预测工作流自动择优切换**机制。核心思路类似预测服务的金丝雀/灰度发布：系统在使用当前最优工作流（生产工作流）对外提供预测结果的同时，让多个历史版本工作流以影子模式在后台并行运行预测，持续积累真实精度数据。当精度监控发现当前生产版本在评估窗口内表现不如某个历史版本时，系统自动将预测服务切换到该表现更优的历史版本，从而保障负荷预测精度的持续稳定，无需人工值守。

该功能与现有 AutoResearch 候选池/复验池闭环互补：AutoResearch 负责"离线搜优"，本功能负责"在线保优"。AutoResearch 产出的 Promoted Baseline 进入本系统后，成为生产版本或影子版本之一，在真实生产数据上接受持续精度考核。

## 术语表

- **Prediction_Switcher**（预测切换引擎）：本功能的核心调度系统，负责管理多版本并行预测、精度评估和自动切换决策
- **Production_Workflow**（生产工作流）：当前被选定为生产基线、实际对外输出预测结果的工作流版本
- **Shadow_Workflow**（影子工作流）：在后台并行运行预测但不对外输出结果的历史版本工作流，仅用于精度对比积累
- **Version_Registry**（版本注册表）：记录所有参与精度运营的工作流版本及其元数据的持久化存储，按 `slot`（槽位）分区
- **Accuracy_Tracker**（精度跟踪器）：持续收集各版本预测结果与实际值的对比数据，计算滚动精度指标
- **Switch_Decision_Engine**（切换决策引擎）：根据精度跟踪数据判断是否需要执行版本切换的决策模块
- **Evaluation_Window**（评估窗口）：用于计算滚动精度指标的最近 N 天时间窗口
- **Switch_Event**（切换事件）：一次自动或手动将生产工作流切换到另一版本的操作记录
- **MAPE**（Mean Absolute Percentage Error，平均绝对百分比误差）：负荷预测的核心精度指标
- **Cooldown_Period**（冷却期）：一次切换完成后系统不再触发自动切换的最短等待时间，防止频繁震荡
- **Slot**（槽位）：精度运营的分区键，支持多场景（如不同区域、不同预测粒度）下的独立管理
- **Prediction_Cycle**（预测周期）：一次完整的预测触发周期，包含数据到达、所有版本执行预测、结果入库
- **Shadow_Budget**（影子预算）：同一槽位内允许同时运行的最大影子版本数量

## 需求

### 需求 1: 工作流版本注册与生命周期管理

**用户故事：** 作为算法工程师，我希望将 AutoResearch 产出的优选工作流注册到精度运营系统并管理其生命周期，以便系统能跟踪多版本并在其间进行精度对比和择优切换。

#### 验收标准

1. 当一个工作流版本被注册时（通过 AutoResearch Promote 或手动 API 调用），版本注册表应当持久化以下元数据：`workflow_id`（工作流模板 ID）、`version_tag`（版本标签，如 `v2026-06-08-ares-abc123`，最大长度 128 字符）、`source_run_id`（来源 AutoResearch run ID，可选）、`source_candidate_id`（来源候选 ID，可选）、`registered_at`（注册时间）、`status`（状态：`production` / `shadow` / `retired`）、以及 `slot`（槽位，默认 `default`）
2. 版本注册表应当对 `workflow_id` 与 `version_tag` 的组合强制唯一性约束，防止同一版本被重复注册。如果注册请求中包含的 `version_tag` 在给定 `workflow_id` 下已存在，则版本注册表应当拒绝该请求并返回表示版本标签重复的错误
3. 当一个新工作流版本以 `status=production` 注册，且同一 `workflow_id`+`slot` 下已有当前生产版本时，预测切换引擎应当在新版本开始接收预测任务之前，原子性地将当前生产版本降级为 `status=shadow`。如果该槽位当前不存在生产版本，则版本注册表应当直接将新版本注册为生产版本，无需执行降级操作
4. 当一个工作流版本的 `status` 被变更为 `retired` 时，预测切换引擎应当立即停止向该版本分发新的预测任务，并在 60 秒内将其已排队（尚未开始执行）的任务重新分配给当前生产版本。已经在该退役版本上执行中的任务应当继续运行至完成
5. 当某个槽位内 `shadow` 状态版本的数量超过配置的 `max_shadow_versions`（最大影子版本数，可配置范围 1–20，默认 5）时，版本注册表应当根据 `registered_at` 自动将最老的影子版本设置为 `retired` 状态（时间相同时按 `version_tag` 字典序排列）
6. 版本注册表应当仅允许以下状态转换：`production` → `shadow`、`production` → `retired`、`shadow` → `production`、`shadow` → `retired`。如果调用方请求不在此集合内的转换（包括任何从 `retired` 状态出发的转换），则版本注册表应当拒绝该请求并返回表示无效状态转换的错误
7. 如果注册请求缺少任何必填字段（`workflow_id`、`version_tag`、`status`、`slot`），则版本注册表应当拒绝该请求并返回表示缺少必填字段的错误，且不持久化任何部分数据

### 需求 2: 多版本影子预测并行执行

**用户故事：** 作为精度运营系统，我希望在每个预测周期内让生产版本和所有活跃影子版本并行执行预测，以便系统能持续积累各版本在真实数据上的预测表现。

#### 验收标准

1. 当一个新的预测周期被触发时（通过定时调度或数据到达事件），预测切换引擎应当在同一槽位内向生产工作流和所有 `status=shadow` 的版本并发分发预测任务，最多同时执行 5 个影子版本；如果活跃影子版本数量超过 5 个，则预测切换引擎应当将超出的版本排队，在同一周期内的后续批次中执行
2. 预测切换引擎应当以最高优先级执行生产工作流的预测任务；影子工作流任务不得使生产工作流的端到端延迟增加超过 5%（与单独运行生产版本相比）；如果检测到资源争用，预测切换引擎应当限流或暂停影子任务以保障生产延迟
3. 如果某个影子工作流预测任务执行失败，则预测切换引擎应当记录失败信息，包含 `workflow_id`（工作流 ID）、`error_type`（错误类型）、`prediction_cycle_id`（周期 ID）和 `timestamp`（时间戳），并继续分发其他影子任务，不中断整体流程
4. 如果某个影子工作流预测任务未在 `shadow_timeout_seconds`（影子预测超时秒数，默认 300）内完成，则预测切换引擎应当取消该任务、记录超时事件，并将该次预测排除在精度计算之外
5. 预测切换引擎应当将所有版本的预测输出持久化到统一的 `prediction_store`（预测结果存储），以 `workflow_id`、`prediction_cycle_id`、`slot` 和 `forecast_timestamp`（预测目标时间戳）为复合键；存储时间超过 `prediction_retention_days`（预测保留天数，默认 90）的记录应当符合删除条件
6. 如果生产工作流预测任务在 `production_timeout_seconds`（生产预测超时秒数，默认 120）内失败或超时，则预测切换引擎应当记录失败信息（包含 `error_type` 和 `prediction_cycle_id`）、发出告警事件，并将该周期标记为 `production_failed`；同一周期内已分发的影子任务应当继续执行至完成

### 需求 3: 精度滚动跟踪

**用户故事：** 作为算法工程师，我希望持续跟踪所有运行版本在评估窗口内的滚动精度指标，以便系统能量化各版本表现并为切换决策提供依据。

#### 验收标准

1. 当某个已完成预测周期的实际负荷值可用时，精度跟踪器应当为该周期内覆盖了至少 90% 预期时间点且未发生超时或执行失败的每个工作流版本计算 MAPE 和 MAE
2. 精度跟踪器应当在配置的 `evaluation_window_days`（评估窗口天数，默认 7，范围 1–90）内维护每个版本的滚动指标：`rolling_mape`（滚动 MAPE）、`rolling_mae`（滚动 MAE）、`valid_cycle_count`（有效周期数）、`total_cycle_count`（总周期数，含超时/失败）、以及 `last_evaluated_at`（最后评估时间）
3. 如果某个工作流版本在评估窗口内的 `valid_cycle_count` 少于 `min_valid_cycles`（最少有效周期数，默认 3），则精度跟踪器应当将该版本标记为 `insufficient_data`（数据不足），并将其排除在排行榜排名和自动切换决策之外
4. 当评估窗口向前滑动时（新一天的实际值到达），精度跟踪器应当为所有在当前评估窗口内至少有一个预测周期记录的版本重新计算滚动指标，并持久化更新后的值以确保服务重启后数据不丢失
5. 精度跟踪器应当暴露 REST 端点 `GET /api/precision-ops/{slot}/leaderboard`，返回指定槽位内所有非 `insufficient_data` 状态的版本，按 `rolling_mape` 升序排列（越低越好），相同值时按 `valid_cycle_count` 降序排列
6. 如果某个预测周期中存在实际值为零的时间点，则精度跟踪器应当将该时间点从该周期的 MAPE 计算中排除并记录警告；MAE 计算仍应包含该零值时间点
7. 如果某个已完成预测周期的实际值在周期完成后 48 小时内仍不可用，则精度跟踪器应当为该周期内所有产出了预测结果的版本递增 `total_cycle_count` 而不递增 `valid_cycle_count`，并将该周期记录为 `actuals_missing`

### 需求 4: 自动择优切换决策

**用户故事：** 作为精度运营系统，我希望当生产版本精度下降且存在明确更优的影子版本时自动执行切换，以便预测服务精度能自我恢复而无需人工干预。

#### 验收标准

1. 当生产工作流的 `rolling_mape`（基于最近 `eval_window_points` 个已产生实际值的预测点计算，默认 168）超出其注册时的历史基线 MAPE 达到 `degradation_threshold_pct`（退化阈值百分比，默认 15，相对比例：(rolling - baseline) / baseline × 100）以上时，切换决策引擎应当评估所有状态为 `active` 且累积评估数据点 ≥ `min_eval_points`（默认 72）的影子工作流，判断是否需要切换
2. 当某个影子工作流的 `rolling_mape` 低于生产工作流的 `rolling_mape` 至少 `switch_margin_pct`（切换分差百分比，默认 10，相对比例：(production_mape - shadow_mape) / production_mape × 100），且该影子工作流已累积 ≥ `min_eval_points` 个评估数据点时，切换决策引擎应当将其识别为切换候选
3. 如果多个影子工作流同时满足切换标准，则切换决策引擎应当选择 `rolling_mape` 最低的作为切换目标；如果两个候选的 `rolling_mape` 相同（差异 < 0.0001），则切换决策引擎应当选择累积评估数据点更多的那个
4. 在同一槽位的上一次切换事件之后的 `cooldown_hours`（冷却期小时数，默认 24）内，切换决策引擎应当抑制自动切换，并记录一条 `switch_suppressed` 事件及抑制原因
5. 当一次自动切换被决策引擎批准时，预测切换引擎应当原子性地交换两个相关版本的 `production` 和 `shadow` 状态，持久化一条切换事件（包含 `switched_at` 时间戳、源和目标工作流 ID、以及决策时的 MAPE 值），并发出通知（webhook 或内部事件）
6. 如果在已批准的切换过程中状态交换或切换事件持久化失败，则预测切换引擎应当将两个版本回滚到交换前的状态，持久化一条 `switch_failed` 事件及失败原因，并保留原生产工作流继续运行
7. 当一条类型为 `automatic` 的切换事件被持久化后，切换决策引擎应当在新生产工作流累积了 `post_switch_observation_points`（切换后观察点数，默认 48）个数据点后重新评估其 `rolling_mape`；如果新生产工作流的 `rolling_mape` 超出决策时记录的切换前目标版本 `rolling_mape` 达到 `degradation_threshold_pct` 以上，则切换决策引擎应当发出 `post_switch_degradation` 告警

### 需求 5: 切换执行与审计日志

**用户故事：** 作为算法工程师，我希望每次切换操作都有完整审计记录，且支持手动干预和回滚，以便我能追溯切换原因并在自动决策失误时快速恢复。

#### 验收标准

1. 当一次切换（自动、手动或回滚）被执行时，预测切换引擎应当向 `switch_log`（切换日志，仅追加）追加一条不可变记录，包含：`event_id`（事件 ID）、`timestamp`（时间戳）、`slot`（槽位）、`trigger_type`（触发类型：`automatic` / `manual` / `rollback`）、`source_workflow_id`（被替换的生产工作流 ID）、`target_workflow_id`（新生产工作流 ID）、`source_rolling_mape`（原生产版本滚动 MAPE）、`target_rolling_mape`（目标版本滚动 MAPE）、以及 `decision_reason`（决策原因文本，最大 500 字符）
2. 预测切换引擎应当提供 `POST /api/precision-ops/{slot}/switch` 端点用于手动触发切换到指定的 `target_workflow_id`，该操作绕过自动决策标准，但仍要求目标工作流存在且属于指定槽位
3. 如果手动或自动切换指定的 `target_workflow_id` 不存在或不属于给定槽位，则预测切换引擎应当拒绝该请求并返回表示目标工作流无效的错误
4. 预测切换引擎应当提供 `POST /api/precision-ops/{slot}/rollback` 端点用于回退最近一次切换（仅支持一级回退），将该次切换中的 `source_workflow_id` 恢复为当前生产工作流
5. 如果请求回滚但该槽位不存在先前的切换记录，则预测切换引擎应当拒绝该回滚并返回表示无切换历史可用的错误
6. 如果请求回滚的时间超出原始切换后的 `rollback_window_hours`（回滚窗口小时数，默认 48），则预测切换引擎应当拒绝该回滚并返回表示回滚窗口已过期的错误
7. `switch_log` 应当为仅追加存储，并通过 `GET /api/precision-ops/{slot}/switch-log` 提供查询，支持分页（默认每页 20 条，最大 100 条）以及按 `trigger_type` 和时间范围过滤

### 需求 6: 运营参数配置与安全约束

**用户故事：** 作为平台管理员，我希望灵活配置精度运营的各项参数和安全开关，以便系统行为可控且不会因误切换造成生产影响。

#### 验收标准

1. 预测切换引擎应当从持久化存储中加载每个槽位的配置，包括：`evaluation_window_days`（评估窗口天数，默认 7）、`degradation_threshold_pct`（退化阈值%，默认 10）、`switch_margin_pct`（切换分差%，默认 5）、`cooldown_hours`（冷却小时数，默认 24）、`min_valid_cycles`（最少有效周期数，默认 3）、`shadow_timeout_seconds`（影子超时秒数，默认 300）、`max_shadow_versions`（最大影子数，默认 5）、`rollback_window_hours`（回滚窗口小时数，默认 48）、以及 `auto_switch_enabled`（是否启用自动切换，布尔值，默认 true）
2. 当 `auto_switch_enabled` 为 `false` 时，切换决策引擎应当仅计算并通过排行榜 API 展示切换建议，不执行任何自动切换操作
3. 当任何配置参数通过配置 API 更新时，预测切换引擎应当从下一个评估周期开始应用新值，无需服务重启
4. 当收到配置更新请求时，预测切换引擎应当按允许范围校验各参数值：`evaluation_window_days` 在 [1, 30]、`degradation_threshold_pct` 在 [5, 50]、`switch_margin_pct` 在 [1, 30]、`cooldown_hours` 在 [1, 168]、`min_valid_cycles` 在 [1, 30]、`shadow_timeout_seconds` 在 [10, 600]、`max_shadow_versions` 在 [2, 20]、`rollback_window_hours` 在 [1, 168]
5. 如果任何配置值校验失败，则预测切换引擎应当拒绝整个更新请求，保持之前的配置不变，并返回指明哪些参数违反了允许范围的错误响应
6. 如果 `auto_switch_enabled` 从 `false` 转为 `true`，则预测切换引擎应当重置冷却计时器以开始全新评估，防止基于禁用期间累积的指标立即触发切换
7. 如果加载槽位配置时持久化存储不可用，则预测切换引擎应当使用标准 1 中定义的默认值，并记录一条表示降级配置模式的警告日志

### 需求 7: 生产登记与外部集成

**用户故事：** 作为负荷预测系统，我希望精度运营切换后能同步更新生产登记，使预测服务下游自动获取当前生产工作流，以便下游消费者无需感知切换细节。

#### 验收标准

1. 预测切换引擎应当为每个槽位维护一份 `production_registry`（生产登记文件），包含：`workflow_id`（当前生产工作流 ID）、`version_tag`（版本标签）、`updated_at`（最后更新时间，ISO 8601 格式）、`source_event_id`（导致本次登记更新的切换事件 ID）
2. 当一次切换（自动、手动或回滚）被执行时，预测切换引擎应当使用新生产工作流的 `workflow_id` 更新受影响槽位的 `production_registry`，确保并发读取方不会观察到部分或中间状态（采用先写后重命名或等效机制）
3. 预测切换引擎应当暴露 `GET /api/precision-ops/{slot}/production` 端点返回当前生产登记条目，使下游预测服务能够解析应使用哪个工作流模板
4. 当 `production_registry` 被更新时，预测切换引擎应当发出一个包含 `slot`（槽位）、`new_workflow_id`（新工作流 ID）和 `event_id`（事件 ID）的事件，以便订阅服务能够响应变更
5. 如果事件发送失败（目标不可达或超时超过 5 秒），则预测切换引擎应当记录一条 `registry_event_delivery_failed` 警告（包含 `slot`、`event_id` 和失败原因），且不得阻塞或回滚登记更新本身
6. 如果 `production_registry` 文件不可读、无法解析，或缺少任何必填字段（`workflow_id`、`version_tag`、`updated_at`、`source_event_id`），则预测切换引擎应当将其视为已损坏，回退到版本注册表中最近注册的 `status=production` 版本，并记录一条 `registry_recovery` 警告
7. 如果 `production_registry` 已损坏且版本注册表中该槽位不存在 `status=production` 的条目，则预测切换引擎应当返回表示该槽位无可用生产工作流的错误，并记录一条 `registry_unrecoverable` 错误日志

### 需求 8: 前端精度运营仪表盘

**用户故事：** 作为算法工程师，我希望在前端界面查看各版本精度趋势、生产状态和切换历史，以便我能直观监控精度运营的运行状况并在需要时手动干预。

#### 验收标准

1. 精度运营仪表盘应当展示一个排行榜表格，包含以下列：`version_tag`（版本标签）、`status`（状态标签）、`rolling_mape`（滚动 MAPE）、`valid_cycle_count`（有效周期数）、`last_evaluated_at`（最后评估时间），默认按 `rolling_mape` 升序排列，当前生产工作流所在行以对比色背景突出显示
2. 精度运营仪表盘应当渲染一个多线时序图，对比所有活跃版本在槽位 `eval_window_days` 参数定义的时间范围内的每日 MAPE，每条线以 `version_tag` 标注；如果具有评估数据的活跃版本少于 2 个，则精度运营仪表盘应当显示一条占位信息，表明数据不足以进行对比
3. 当一次切换事件发生时，精度运营仪表盘应当显示一条通知横幅，包含 `from_version`（源版本）、`to_version`（目标版本）、`trigger_type`（触发类型）和 `switched_at`（切换时间），并提供一键回滚按钮（仅在 `rollback_window_hours` 内启用）；当用户点击回滚按钮时，精度运营仪表盘应当弹出确认对话框，明确展示回滚目标版本后再执行回滚
4. 精度运营仪表盘应当提供一个配置面板，展示当前槽位参数（`eval_window_days`、`rolling_mape_threshold`、`min_valid_cycles`、`rollback_window_hours`、`auto_switch_enabled`），支持行内编辑，编辑权限限制为 operator 角色及以上；当参数编辑被提交时，精度运营仪表盘应当在保存前按参数的数值范围校验输入
5. 精度运营仪表盘应当将 `switch_log` 以分页时间线视图展示（默认每页 20 条），支持按 `trigger_type` 和日期范围过滤，`trigger_type` 标签使用颜色编码（`automatic` = 蓝色、`manual` = 绿色、`rollback` = 橙色）
6. 精度运营仪表盘应当以不超过 60 秒的间隔刷新展示的指标；如果后端数据请求失败，则精度运营仪表盘应当保留最后一次成功加载的数据，并显示一个过期指示器标明距上次成功刷新的时间
7. 如果后端返回空的版本列表或不存在评估记录，则精度运营仪表盘应当展示一个空状态视图，提示当前尚无精度评估数据可用，并引导用户配置和运行评估槽位
