# Requirements Document

## Introduction

本文档定义 AIP AutoResearch 系统的下一代演进需求。核心目标是将 AutoResearch 从"自动参数搜索"升级为"自主研究员"——能够自动提出研究问题、设计实验、验证因果关系、积累可复用知识、并主动决策研究方向。

系统背景：滚动回测架构下，每个回测窗口由 N 天训练数据（内部使用 TimeSeriesSplit 5-fold 交叉验证）预测 1 天（96 个 15 分钟点）。实际存在三个数据集——训练集（CV 内部拟合部分）、验证集（CV fold 验证部分）、测试集（预测日）。

**近期定义**："自主研究员"指系统能自动提出研究问题、设计实验、验证假设、积累可复用知识——而非自动编写新算子。

**假设与约束**：
- 首阶段聚焦负荷预测场景，不急于跨领域泛化
- 现有注册表 `load_forecast_v1` 继续作为主搜索空间
- GLM 继续作为研究推理核心，但所有输出必须通过结构化 schema + validator + audit
- 每轮实验仅一次 GLM 调用（Hypothesis Agent），其余环节为纯规则/统计

**实现优先级**：
- P0：三集画像（训练集 + 验证集 + 测试集统计事实）+ 三集对比诊断（实现前置：扩展回测引擎返回 per-fold 指标）
- P0.5：研究问题生成器（独立模块，消费 Analyst_Agent 归因输出）
- P1：知识库分层（L1-L4）+ 阶段性反思
- P2：信息增益 / 搜索空间收缩 + 收益递减预测
- P3：多智能体协作（轻量流水线：Dataset_Profiler → Analyst → RQG → Hypothesis → Designer）

## Glossary

- **AutoResearch_Engine（自动实验引擎）**: `backend-service/api/workflows_enhanced.py` 中 `_run_autoresearch_task` 主循环，负责采样→回测→评估→建议→应用的完整迭代
- **Dataset_Profiler（数据集画像器）**: 新增模块，负责对训练集、验证集（CV fold）和测试集进行统计画像和事实输出（不负责归因推理），输出 `train_profile`、`validation_profile`、`test_profile`、`tri_dataset_diagnosis`、`cross_window_pattern` 供 Analyst_Agent 消费
- **Research_Question_Generator（研究问题生成器）**: 独立模块（P0.5），消费 Analyst_Agent 输出的 `error_attribution`，生成结构化研究问题（`research_question`），注入 GLM prompt 指导假设生成
- **Knowledge_Layer（知识层）**: 分层知识库，包含 L1 原始案例层、L2 规律层、L3 反模式层、L4 假设模板层
- **Knowledge_Claim（知识声明）**: L2/L3/L4 层的基本单元，包含 claim（声明）、condition（适用条件）、evidence（支撑证据）、counter_evidence（反证）、confidence（置信度）
- **Periodic_Reflection（阶段性反思）**: 每 N 轮触发的深度反思机制，输出可执行的策略决策（continue / shift_focus / expand_registry / early_stop）
- **Research_Focus（研究焦点）**: 反思输出的 `current_research_focus` 字段，写入 run_state，偏置后续采样方向（priority_layers 获得 2x 采样概率）
- **Experiment_Quality_Score（实验质量评分）**: 对每个实验设计的质量评估，包含单变量控制度、假设清晰度、预期结果可测量性、风险等级、知识增益估计
- **Agent_Orchestrator（智能体编排器）**: 多智能体架构中的协调组件，编排 Analyst → Hypothesis → Designer 流水线
- **Hypothesis_Agent（假设生成器）**: 唯一调用 GLM 的智能体，接收研究问题和知识声明，输出结构化假设
- **Analyst_Agent（分析师）**: 纯规则/统计的智能体（不调用 GLM），接收 Dataset_Profiler 的统计事实，执行规则归因分析，输出 `error_attribution` 和 `pattern_report`
- **Designer_Agent（设计师）**: 纯规则的智能体（不调用 GLM），负责将假设意图翻译为具体 patch（复用现有 `_translate_intent_to_patches`）
- **Causal_Inference_Module（因果推断模块）**: 分析实验结果背后因果关系的模块，输出"为什么某配置有效"而非仅"某配置有效"
- **Information_Gain_Pruner（信息增益剪枝器）**: 基于每轮实验的信息增益动态收缩搜索空间的模块
- **Proactive_Predictor（主动预判器）**: 基于历史改善曲线预测未来收益的模块，支持实验节奏的主动调整
- **Parameter_Interaction_Graph（参数交互图谱）**: 维护参数间硬约束和交互效应的图结构，指导采样避免无效组合
- **Patch_Fingerprint（补丁指纹）**: 假设的结构化标识，由 `target_function_id` + `param_key` + `direction` 组成，用于结构化去重
- **Meta_Reflection（元反思）**: 对反思机制本身有效性的追踪和评估，监控反思建议的采纳率和实际效果
- **Backtest_Window（回测窗口）**: 单次回测中的一个时间窗口，包含训练期和测试期
- **Search_Registry（搜索注册表）**: `autoresearch_search_registries/load_forecast_v1.json`，定义参数搜索空间
- **Experience_Store（经验库）**: 知识库的物理存储，管理 L1-L4 各层知识的持久化和检索
- **GLM_Prompt（GLM 提示词）**: 发送给大语言模型的上下文提示，包含研究问题、知识声明等结构化信息
- **Run_State（运行状态）**: AutoResearch 单次 run 的全局状态对象，包含迭代数据、反思记录、研究焦点等

## Requirements

### Requirement 1: 训练集/验证集/测试集三集画像（P0）

**User Story:** 作为算法研究员，我想在每轮滚动回测后对训练集（CV 拟合部分）、验证集（CV fold 验证部分）和测试集（预测日）进行充分的统计画像，以便为下游的误差归因和研究问题生成提供高质量的结构化事实。

**职责边界**：Dataset_Profiler 只负责产出统计事实和画像数据，不负责归因推理（归因由 Analyst_Agent 完成，见 Requirement 6）。

**实现前置条件**：验证集画像（AC 1.3）要求回测引擎返回 per-fold 指标。需先扩展 `_execute_backtest` / `_execute_backtest_reference` 的返回结构，新增 `cv_fold_metrics` 字段。此为 P0 的实现依赖，不是需求降级。

#### Acceptance Criteria

##### 1.1 训练集画像

1. WHEN 一轮回测执行完成, THE Dataset_Profiler SHALL 对训练集生成结构化画像（`train_profile`），包含以下字段：`load_curve_stats`（负荷曲线统计：均值、标准差、偏度、峰度）、`peak_valley_distribution`（峰谷分布：日均峰数、日均谷数、峰谷幅度均值）、`data_quality`（数据质量：缺失率、异常点比例、连续缺失最大长度）、`periodicity_strength`（周期性强度：日周期自相关系数、周周期自相关系数）
2. THE Dataset_Profiler SHALL 对训练集计算时段特征分布（`period_distribution`），将每日 96 个点划分为四个时段——早高峰（07:00-11:00）、午间（11:00-14:00）、晚高峰（17:00-21:00）、夜间（21:00-07:00）——并输出各时段的负荷均值、标准差和占全日比例
3. THE Dataset_Profiler SHALL 识别训练集的主导模式（`dominant_pattern`），枚举值为 `weekday_dominant` / `weekend_dominant` / `mixed` / `holiday_affected`，基于工作日与周末负荷均值差异比（`weekday_weekend_gap`）判定
4. THE Dataset_Profiler SHALL 在 `train_profile` 中输出训练集拟合指标（`train_fit_mape`），取自回测引擎返回的训练集上的拟合误差（若回测引擎不返回此值，则从 `candidate_score` 中的 `train_score` 字段提取，或标记为 `null`）

##### 1.2 验证集画像（CV 内部诊断）

5. THE 回测引擎（`_execute_backtest` / `_execute_backtest_reference`）SHALL 扩展返回结构，新增 `cv_fold_metrics` 字段，包含每个 fold 的 `fold_id`、`train_loss`、`val_loss`、`val_mape`
6. WHEN 回测引擎返回 `cv_fold_metrics` 后, THE Dataset_Profiler SHALL 生成验证集画像（`validation_profile`），包含：
   - `cv_fold_losses`（每个 fold 的训练 loss 和验证 loss 列表，含 `fold_id`、`train_loss`、`val_loss`、`gap`）
   - `cv_val_mape`（CV 验证集平均 MAPE，取各 fold `val_mape` 的均值）
   - `overfit_indicator`（过拟合指标）：WHEN 平均 `gap` 超过平均 `train_loss` 的 50%, 标记为 `high`；WHEN 在 20%~50% 之间, 标记为 `moderate`；WHEN 低于 20%, 标记为 `low`
   - `cv_loss_trend`（CV loss 趋势）：枚举值为 `increasing`（后期 fold 验证 loss 更高，暗示数据漂移）/ `stable` / `decreasing`（模型随数据量增加而改善）

##### 1.3 测试集画像（预测日诊断）

7. WHEN 预测日（1 天 96 个点）的预测值生成完成, THE Dataset_Profiler SHALL 生成测试集画像（`test_profile`），包含：`actual_vs_predicted`（真实值与预测值的逐点对比数组）、`overall_mape`（全日 MAPE，即 `test_mape`）、`overall_rmse`（全日 RMSE）、`max_single_point_error`（最大单点误差百分比及其时间戳）
8. THE Dataset_Profiler SHALL 按时段计算误差分布（`period_error_breakdown`），输出早高峰 MAPE、午间 MAPE、晚高峰 MAPE、夜间 MAPE，并标注误差最高的时段（`worst_period`）
9. THE Dataset_Profiler SHALL 对测试集执行波峰波谷检测（`prominence` 默认为数据标准差的 0.5 倍，`distance` 默认 4 个时间步），计算峰区误差比（`peak_error_ratio`）和谷区误差比（`valley_error_ratio`），并标注高误差是否集中在峰谷处（`high_error_at_extremes`，布尔值）

##### 1.4 三集对比诊断（tri_dataset_diagnosis）

10. THE Dataset_Profiler SHALL 生成三集对比诊断报告（`tri_dataset_diagnosis`），基于 `train_profile`、`validation_profile`、`test_profile` 三者的统计事实，包含以下分析维度：
    - `pattern_consistency`（模式一致性）：对比训练集 `dominant_pattern` 与测试集预测日的日类型，WHEN 不一致时标记为 `pattern_mismatch` 并生成描述
    - `overfit_detection`（过拟合检测）：WHEN `validation_profile` 可用, 以 `test_mape` 超过 `cv_val_mape` 的 1.5 倍判定为 `confirmed_overfit`；WHEN `validation_profile` 不可用（回测引擎尚未扩展）, 以 `test_mape` 超过 `train_fit_mape` 的 1.5 倍作为降级判定；WHEN 两者均不可用, 标记为 `overfit_unknown`
    - `generalization_assessment`（泛化能力评估）：基于 `train_fit_mape`、`cv_val_mape`（若可用）、`test_mape` 三者的差异链计算，枚举值为 `good`（相邻差异均 < 20%）/ `moderate`（差异 20%~50%）/ `poor`（差异 > 50%）
    - `diagnosis_conclusion`（诊断结论文本）：综合以上维度生成不超过 200 字的结构化诊断结论
11. WHEN `pattern_consistency` 为 `pattern_mismatch`, THE Dataset_Profiler SHALL 在 `diagnosis_conclusion` 中建议调整训练窗口选择策略
12. WHEN `overfit_detection` 为 `confirmed_overfit`, THE Dataset_Profiler SHALL 在 `diagnosis_conclusion` 中建议降低模型复杂度或增加正则化

##### 1.5 跨回测窗口规律分析

13. WHEN 连续多天滚动回测完成（回测窗口数 ≥ 3）, THE Dataset_Profiler SHALL 分析跨窗口的系统性误差模式（`cross_window_pattern`），包含：`error_trend`（误差趋势）、`periodic_error_pattern`（周期性误差模式）、`drift_signal`（漂移信号）
14. THE Dataset_Profiler SHALL 在跨窗口分析中识别"稳定差"时段（`consistently_bad_periods`）：WHEN 某时段在超过 60% 的回测窗口中 MAPE 均高于全日平均 MAPE 的 1.5 倍, THE Dataset_Profiler SHALL 将该时段标记为稳定高误差时段

##### 1.6 Dataset_Profiler 输出契约

15. THE Dataset_Profiler SHALL 将 `train_profile`、`validation_profile`（若可用）、`test_profile`、`tri_dataset_diagnosis`、`cross_window_pattern` 作为结构化 JSON 输出，供 Analyst_Agent 消费，而非直接注入 GLM_Prompt
16. THE Dataset_Profiler 不负责误差归因推理（`error_attribution`）——归因由 Analyst_Agent 基于 Dataset_Profiler 的事实输出执行（见 Requirement 6）


### Requirement 2: 研究问题生成器（P0.5）

**User Story:** 作为算法研究员，我想让系统在每轮或每阶段自动从诊断事实中提炼出结构化的研究问题，以便 GLM 接收的是"要回答什么问题"而非"一堆原始统计数字"，显著提升假设生成的针对性。

#### Acceptance Criteria

1. THE Research_Question_Generator SHALL 作为独立模块存在，流水线位置为：`Dataset_Profiler (facts) → Analyst_Agent (attribution) → Research_Question_Generator (questions) → GLM_Prompt (inject questions)`
2. WHEN Analyst_Agent 输出 `error_attribution` 后, THE Research_Question_Generator SHALL 生成 1~3 个结构化研究问题（`research_question`），每个包含以下字段：
   - `question`（研究问题文本，如"为什么晚高峰误差持续高于其他时段？"）
   - `evidence`（支撑证据列表，引用 Dataset_Profiler 的具体输出）
   - `candidate_causes`（候选原因列表，从 error_attribution 推导）
   - `next_experiment_goal`（下一步实验目标，明确要验证什么）
3. THE Research_Question_Generator SHALL 基于规则（非 GLM）生成研究问题：WHEN `worst_period` 连续 N 个窗口（N ≥ 3）为同一时段, 生成"为什么该时段误差持续偏高"类问题；WHEN `overfit_detection` 为 `confirmed_overfit`, 生成"如何降低过拟合"类问题；WHEN `drift_signal` 为正, 生成"如何应对数据漂移"类问题
4. THE Research_Question_Generator SHALL 支持从 Knowledge_Layer 的 L3 反模式中检索相关反模式，将其作为 `candidate_causes` 的补充来源
5. WHEN 研究问题生成完成, THE AutoResearch_Engine SHALL 将 `research_question` 列表注入 GLM_Prompt，作为假设生成的核心引导（替代直接注入原始统计数据）
6. THE Research_Question_Generator SHALL 对生成的研究问题进行去重：WHEN 新问题的 `question` 与最近 5 轮已生成问题的语义相似度超过 0.8（基于关键词重叠率）, THE Research_Question_Generator SHALL 标记为 `recurring`（反复出现）并提升其优先级

### Requirement 3: 知识库分层架构与知识声明（P1）

**User Story:** 作为算法研究员，我想让经验库从扁平的 JSON 文件升级为分层结构（原始案例→通用规律→反模式→假设模板），每条知识以"声明 + 条件 + 证据 + 反证"的结构存储，以便不同层级的知识以不同权重和策略注入 GLM prompt，并支持知识的验证、衰减和复活。

#### Acceptance Criteria

##### 3.1 分层结构

1. THE Experience_Store SHALL 重构为四层结构：
   - L1 原始案例层（`raw_cases/`）：每次 run 的原始 `run_insight` JSON 文件，保持现有格式不变
   - L2 规律层（`patterns/`）：从多次 run 中提炼的通用规律
   - L3 反模式层（`anti_patterns/`）：明确"不该做什么"的负面经验
   - L4 假设模板层（`hypothesis_templates/`）：可复用的假设模板

##### 3.2 知识声明格式（Knowledge Claim）

2. THE Experience_Store SHALL 使用统一的知识声明格式存储 L2/L3/L4 层知识，每条 Knowledge_Claim 包含：
   - `claim_key`（结构化标识，由 `target_param` + `recommended_value` + `direction` + `metric` 组成，用于确定性冲突检测，如 `{"target_param": "train_days", "recommended_value": 45, "direction": "increase", "metric": "mape"}`）
   - `claim`（声明文本，如"train_days=45 在高周周期稳定性场景下优于 30"）
   - `condition`（适用条件，结构化 JSON，如 `{"seasonality_strength": ">0.7", "weekend_weekday_gap": "<0.1"}`）
   - `scenario_condition_hash`（condition 的确定性哈希，用于快速匹配和冲突检测）
   - `evidence`（支撑证据，run_id 列表）
   - `counter_evidence`（反证，run_id 列表）
   - `confidence`（置信度 0~1，基于 evidence 和 counter_evidence 的比例计算）
   - `knowledge_type`（知识类型：`causal_candidate` / `correlational` / `anti_pattern` / `hypothesis_template`）
   - `last_validated_at`（最后验证时间）
3. WHEN 一次 AutoResearch run 结束并生成 Run_Insight, THE Experience_Store SHALL 自动将 `learned_rules` 提取为 L2 Knowledge_Claim 候选，将 `ineffective_attempts` 提取为 L3 Knowledge_Claim 候选
4. WHEN L2 Knowledge_Claim 被 3 个以上不同 run 的证据支撑且无反证, THE Experience_Store SHALL 将该声明的 `confidence` 提升至 0.8 以上

##### 3.3 知识注入策略

5. THE AutoResearch_Engine SHALL 在生成 GLM_Prompt 时按以下权重注入不同层级的知识：L4 假设模板（权重最高，直接作为候选假设来源）→ L3 反模式（权重次高，作为"避免"指令）→ L2 规律（中等权重，作为参考信息）→ L1 原始案例（最低权重，仅在高相似度时注入摘要）
6. THE AutoResearch_Engine SHALL 在知识注入时区分"因果知识"和"相关性知识"：`knowledge_type` 为 `causal_candidate` 的知识注入权重 SHALL 为 `correlational` 的 2 倍
7. THE Experience_Store SHALL 仅在场景指纹匹配时注入知识：WHEN 当前 run 的 `scenario_fingerprint` 与 Knowledge_Claim 的 `condition` 不匹配, THE Experience_Store SHALL 降低该知识的注入权重至原始权重的 0.3 倍

##### 3.4 知识衰减与复活

8. THE Experience_Store SHALL 实现知识衰减机制：每条 L2/L4 Knowledge_Claim SHALL 携带 `last_validated_at` 字段，WHEN 知识超过 30 天未被新 run 验证, THE Experience_Store SHALL 将其 `confidence` 按 `decay_rate`（默认每 30 天衰减 0.1）递减
9. WHEN `confidence` 降至 0.3 以下, THE Experience_Store SHALL 将该知识标记为 `stale`（过时）并降低注入 GLM_Prompt 的优先级
10. WHEN 一条 `stale` 状态的 Knowledge_Claim（confidence < 0.3）获得新 run 的支撑证据, THE Experience_Store SHALL 将其 `confidence` 重新计算（基于全部 evidence 和 counter_evidence），并将状态从 `stale` 恢复为 `active`（知识复活）

##### 3.5 知识冲突解决

11. WHEN 两条 Knowledge_Claim 的 `claim_key` 中 `target_param` 相同但 `recommended_value` 或 `direction` 相反（如 claim_key.target_param="train_days" 一条 direction="increase" 另一条 direction="decrease"）, THE Experience_Store SHALL 判定为结构化冲突，并按以下优先级解决：条件特异性（condition 字段数量更多的优先）> 时效性（last_validated_at 更近的优先）> 置信度（confidence 更高的优先）
12. IF 冲突无法通过优先级规则解决, THEN THE Experience_Store SHALL 将冲突本身注入 Research_Question_Generator 作为新的研究问题来源

##### 3.6 知识检索接口

13. THE Experience_Store SHALL 提供知识检索接口（`GET /api/workflows/enhanced/knowledge/search`），支持按 `scenario_condition_hash` 匹配、按层级过滤、按置信度排序、按 knowledge_type 过滤、按 `claim_key.target_param` 精确查询


### Requirement 4: 阶段性反思与策略执行（P1）

**User Story:** 作为算法研究员，我想让系统每 N 轮自动进行一次深度反思，不仅总结过去的趋势和策略有效性，还输出可执行的策略决策（如切换研究焦点、扩展搜索空间），并将决策写入 run_state 实际偏置后续采样方向。

#### Acceptance Criteria

##### 4.1 反思触发与分析

1. WHEN AutoResearch_Engine 的迭代计数达到 `reflection_interval`（默认 20）的整数倍, THE AutoResearch_Engine SHALL 触发一次 Periodic_Reflection
2. THE Periodic_Reflection SHALL 分析过去 N 轮的以下维度：`improvement_trend`（改善趋势：`improving` / `stagnating` / `degrading`）、`effective_directions`（有效方向列表）、`ineffective_directions`（无效方向列表）、`exploration_coverage`（搜索空间覆盖率百分比）
3. THE Periodic_Reflection SHALL 支持通过启动参数 `reflection_interval` 配置反思间隔（最小值 5，最大值 50，默认 20）

##### 4.2 策略决策输出

4. THE Periodic_Reflection SHALL 输出结构化策略决策（`reflection_decision`），包含：
   - `current_strategy`（当前策略描述）
   - `status`（状态：`improving` / `stagnating` / `degrading`）
   - `reason`（判断理由，如"近 8 轮 MAPE 改善低于 0.05%，且同类假设重复否证"）
   - `decision`（决策：`continue_current` / `shift_focus` / `expand_registry` / `early_stop`）
   - `next_focus`（下一步焦点描述，仅 shift_focus 时填写）
   - `reset_type`（重置类型，仅 expand_registry 时填写：`expand_registry` / `redefine_space` / `change_model_family`）

##### 4.3 策略执行机制

5. WHEN `decision` 为 `shift_focus`, THE Periodic_Reflection SHALL 将 `current_research_focus` 写入 `run_state`，包含：
   - `focus`（焦点描述）
   - `set_by`（设置来源，如 `periodic_reflection_iter_20`）
   - `priority_layers`（优先搜索层列表，如 `["feature"]`）
   - `priority_params`（优先参数列表，如 `["create_lag_features.lags", "rolling_statistics.window_sizes"]`）
   - `avoid_layers`（回避层列表，如 `["training"]`）
6. WHILE `current_research_focus` 存在于 run_state 中, THE AutoResearch_Engine SHALL 在采样时按以下规则与分层激活（staged activation）协作：
   - 采样偏置仅在"已激活层"内部生效：`priority_layers` 中的参数获得 2 倍采样概率，`avoid_layers` 中的参数获得 0.5 倍采样概率，但前提是该层已被注册表的 staged activation 机制激活
   - IF `priority_layers` 中包含尚未激活的层, THEN THE Periodic_Reflection SHALL 同时触发该层的提前激活（`force_activate`），并在日志中记录"反思触发提前激活 {layer_name}"
   - `force_activate` 不改变注册表的 `activation_order` 定义，仅在当前 run 的 `run_state` 中标记该层为已激活
7. WHEN `decision` 为 `expand_registry`, THE Periodic_Reflection SHALL 输出 `reset_recommendation`，包含 `reset_type` 和 `rationale`（重置理由），但不自动执行（由用户决定）
8. IF `decision` 为 `early_stop`, THEN THE AutoResearch_Engine SHALL 在日志中提示"深度反思建议提前停止"，但不自动终止 run

##### 4.4 反思注入与存储

9. WHEN Periodic_Reflection 完成, THE AutoResearch_Engine SHALL 将反思结果存入 `run_state["periodic_reflections"]` 列表
10. WHILE 后续轮次生成建议, THE AutoResearch_Engine SHALL 将最近一次 Periodic_Reflection 的 `reflection_decision` 注入 GLM_Prompt，作为策略指导上下文

##### 4.5 前瞻预测

11. WHEN 触发阶段性反思时, THE Periodic_Reflection SHALL 基于当前改善趋势预测"如果继续当前策略，最终能达到什么水平"（`projected_final_performance`），并与目标 MAPE 对比，输出 `gap_to_target` 和 `estimated_rounds_to_target`
12. WHEN `projected_final_performance` 仍高于目标 MAPE 且 `estimated_rounds_to_target` > 50, THE Periodic_Reflection SHALL 在 `reflection_decision` 中建议 `expand_registry` 或 `shift_focus`

##### 4.6 元反思

13. THE AutoResearch_Engine SHALL 实现元反思机制（Meta_Reflection）：追踪反思建议的采纳率（`reflection_adoption_rate`），WHEN 连续 3 次反思后的策略建议均未被后续实验采纳, THE Meta_Reflection SHALL 输出 `meta_warning`
14. THE Meta_Reflection SHALL 维护反思有效性统计（`reflection_effectiveness_stats`），包含 `total_reflections`、`adopted_count`、`adoption_rate`、`post_adoption_improvement_avg`

### Requirement 5: 实验质量评分与信息增益（P2）

**User Story:** 作为算法研究员，我想让系统对每个实验设计进行质量评分，并基于信息增益动态收缩搜索空间，以便优先执行高质量、高信息增益的实验，避免在低价值区域浪费算力。

#### Acceptance Criteria

##### 5.1 实验质量评分

1. WHEN Hypothesis_Agent 或 AutoResearch_Engine 生成一个实验设计（hypothesis + patch）, THE AutoResearch_Engine SHALL 计算该实验的质量评分（`experiment_quality`），包含：
   - `single_variable_control`（单变量控制度 0~1：与上一轮相比改动的参数数量越少越高）
   - `hypothesis_clarity`（假设清晰度 0~1：hypothesis 是否包含明确的 expected_outcome 和 fallback_if_failed）
   - `expected_outcome_measurable`（预期结果可测量性 0~1：expected_outcome 是否包含具体数值阈值）
   - `risk_level`（风险等级：`low` / `medium` / `high`，基于改动参数所在层的 activation_order）
   - `knowledge_gain_estimate`（知识增益估计 0~1：该实验能否验证或否证一条 Knowledge_Claim）
2. THE AutoResearch_Engine SHALL 使用归一化排序公式对实验设计排序：
   ```
   score = w_metric * normalize(expected_metric_gain, history_gains)
         + w_info * normalize(knowledge_gain_estimate, [0, 1])
         - w_risk * risk_penalty_factor
   ```
   其中权重动态调整：早期轮次（前 30%）`w_info > w_metric`（探索优先），后期轮次 `w_metric > w_info`（收敛优先）
3. WHEN 多个实验设计可选时, THE AutoResearch_Engine SHALL 优先执行 `score` 最高的实验

##### 5.2 信息增益与搜索空间收缩

4. WHEN 每轮实验结束后, THE Information_Gain_Pruner SHALL 计算各参数区间的信息增益（`info_gain_per_region`）
5. WHEN 某参数区间连续 3 轮信息增益低于阈值 0.01, THE Information_Gain_Pruner SHALL 将该区间标记为 `exhausted`（已耗尽）并从后续采样中排除，同时记录排除原因供审计
6. THE Information_Gain_Pruner SHALL 维护搜索空间收缩日志（`space_contraction_log`），每条记录包含 `param_key`、`excluded_region`、`reason`、`iteration`、`remaining_coverage`

##### 5.3 收益递减预测

7. WHEN 完成前 5 轮实验后, THE Proactive_Predictor SHALL 基于信息增益曲线的拟合（对数模型或幂律模型）预测 `predicted_marginal_gain`（预测边际增益）和 `rounds_to_diminishing_returns`（到达收益递减的预估轮数）
8. WHEN `predicted_marginal_gain` 连续 3 轮低于 0.05%, THE Proactive_Predictor SHALL 建议提前收敛（`suggest_early_convergence`）
9. WHEN 最近 5 轮改善趋势仍为正且斜率 > 0.1%/轮, THE Proactive_Predictor SHALL 建议延长实验（`suggest_extension`）

##### 5.4 因果推断

10. WHEN 一轮实验结果产生后, THE Causal_Inference_Module SHALL 输出 `causal_attribution`（因果归因），包含 `effective_config`（生效配置）、`enabling_conditions`（使能条件列表）、`confidence`（归因置信度 0~1）
11. THE Causal_Inference_Module SHALL 将因果归因结果反馈给 Knowledge_Layer，作为 L2 Knowledge_Claim 的 evidence 或 counter_evidence

##### 5.5 参数交互图谱

12. THE AutoResearch_Engine SHALL 构建 Parameter_Interaction_Graph，维护 `hard_constraints`（硬约束，如"lags 不能超过 train_days × 96"）和 `interaction_effects`（交互效应），采样时自动排除违反硬约束的组合

### Requirement 5A: 候选规划器与多方向覆盖（第四代 P0.6）

**User Story:** 作为算法研究员，我想让 AutoResearch 每轮并发候选由候选规划器主动分配探索方向，而不是只依赖当前最优参数、GLM proposal 或随机补位，以便系统稳定覆盖参数、特征、模型、数据和风险探索方向。

#### Acceptance Criteria

1. WHEN AutoResearch_Engine 进入 batch 模式且 `batch_size > 1`, THE Candidate_Planner SHALL 为每个 group 生成候选槽位（candidate slot），每个槽位包含 `target_direction`、`target_layer`、`candidate_source`、`exploration_role` 和 `planner_reason`。
2. THE Candidate_Planner SHALL 支持五类探索方向：`parameter`（参数方向）、`feature`（特征方向）、`model`（模型方向）、`data`（数据方向）、`risk`（风险探索方向）。
3. WHEN `batch_size >= 5`, THE Candidate_Planner SHALL 在同一轮内覆盖五类探索方向；WHEN `batch_size < 5`, THE Candidate_Planner SHALL 按历史覆盖缺口轮换方向，保证连续多轮覆盖五类方向，而不是每轮都重复参数方向。
4. WHEN `batch_size = 3`, THE Candidate_Planner SHALL 默认生成三类角色：`exploit`（利用当前最优/主候选）、`diversify`（特征或模型方向）、`explore_risk`（数据或风险方向）。
5. THE Candidate_Planner SHALL 将 GLM proposal 作为候选来源之一；IF GLM proposal 的 `selected_layer` 与当前槽位方向匹配, THEN 可优先使用该 proposal；IF 不匹配, THEN SHALL 使用注册表定向采样或规则采样补齐该槽位。
6. THE Candidate_Planner SHALL 维护 layer scoreboard（层级记分板），至少包含每个方向的 `attempts`、`successes`、`failures`、`timeout_count`、`best_score_advantage`、`last_tried_iteration` 和 `coverage_gap`。
7. WHEN 某个方向长期未被探索, THE Candidate_Planner SHALL 提高该方向的选择优先级；WHEN 某个方向连续超时或失败, THE Candidate_Planner SHALL 降低该方向优先级但不得永久禁用。
8. WHEN group 因 `batch_eval_timeout` 或异常失败, THE AutoResearch_Engine SHALL 将失败方向、失败原因和 patch fingerprint 写回 planner 统计，供后续轮次降权。
9. THE AutoResearch_Engine SHALL 将每个 group 的 `target_direction`、`target_layer`、`exploration_role`、`planner_reason`、`candidate_source` 写入 `batch_groups` 和 trial ledger，保证前端和离线审计能看到“这一组为什么被规划出来”。
10. THE Candidate_Planner SHALL 不直接修改 workflow template；它只生成本轮候选 patch，长期写回仍由现有 proposal apply / promote 机制控制。


### Requirement 5B: 探索策略质量提升与主线去偏（第四代 P0.7）

**User Story:** 作为算法研究员，我想让 AutoResearch 不只是在并行 group 中覆盖多个方向，还要让主候选、知识沉淀和研究问题真正跟随实验结果切换焦点，以便减少参数层惯性、避免重复问题、提升沉淀知识的可信度。

#### Acceptance Criteria

1. WHEN Candidate_Planner 的 scoreboard 显示 `parameter` 方向尝试数明显高于其他方向（例如高出 2 倍以上）且近 N 轮收益进入平台期, THE AutoResearch_Engine SHALL 允许主候选 group 轮换到 `feature`、`model` 或 `data` 方向，而不是固定以参数层作为 group 1。
2. THE AutoResearch_Engine SHALL 将 `active_layers` 与 Candidate_Planner 的 `target_layer` 语义对齐；WHEN planner 选择未激活层但该层已有成功 group 或覆盖缺口过大, THE system SHALL 记录 `force_activate_recommendation` 或直接在当前 run 内标记该层为可定向采样，避免长期出现 `layer_not_active` 但仍实际采样的状态不一致。
3. THE Research_Question_Generator SHALL 对跨轮重复问题维护验证状态，至少包含 `question_key`、`first_seen_iteration`、`last_seen_iteration`、`evidence_count`、`tested_patch_fingerprints`、`status`（open / testing / resolved / stale），避免每轮重复生成“midday 误差偏高”“数据漂移”等同质问题。
4. WHEN `GLM_ENABLE=false` 或 GLM 未实际调用, THE AutoResearch_Engine SHALL 在 proposal、前端状态和 run report 中明确标记 `llm_used=false` 与 `rule_fallback=true`，并将“GLM候选”展示为“规则/记忆候选”，避免误判为真实 LLM 推理。
5. WHEN 某候选在单窗口上取得正收益, THE AutoResearch_Engine SHALL 支持将其标记为 `needs_multi_window_confirmation`，并在后续用更多窗口复验后再提升 Knowledge_Claim 的 confidence；单窗口结果不得直接写成高置信知识。
6. THE Knowledge_Layer SHALL 区分 `single_window_evidence` 与 `multi_window_evidence`；只有跨窗口稳定支撑的 claim 才能提升为高置信 L2 规律，单窗口支撑最多作为低置信候选规律。
7. THE Candidate_Planner SHALL 对失败为 0 但收益长期为负的方向记录 `ineffective_count`，并在后续规划中降低该方向重复采样概率；该降权不得永久禁用该方向。
8. THE frontend SHALL 在 AutoResearch 控制台展示探索健康度摘要，至少包括方向覆盖、主候选偏置、timeout 数、负收益方向、GLM 是否真实启用、单窗口/多窗口证据比例。
9. THE AutoResearch report SHALL 输出“探索策略诊断”段落，说明当前 run 的有效方向、无效方向、主线偏置、搜索空间覆盖缺口和下一阶段建议。


### Requirement 6: 多智能体轻量流水线（P3）

**User Story:** 作为系统架构师，我想将当前单一 GLM 研究员角色拆分为轻量流水线（Analyst → Hypothesis → Designer），其中仅 Hypothesis Agent 调用 GLM，其余为纯规则/统计，以便降低 GLM 调用成本、提升各环节输出的专业性和可审计性。

#### Acceptance Criteria

##### 6.1 流水线结构

1. THE Agent_Orchestrator SHALL 编排以下流水线：`Dataset_Profiler (统计事实) → Analyst_Agent (规则归因, no GLM) → Research_Question_Generator (研究问题) → Hypothesis_Agent (GLM) → Designer_Agent (规则翻译, no GLM) → Validator → Backtest → Reflection`
2. THE Analyst_Agent SHALL 为纯规则/统计模块（不调用 GLM），接收 Dataset_Profiler 的 `train_profile`、`test_profile`、`train_test_diagnosis`、`cross_window_pattern` 输出，执行规则归因分析，输出结构化的 `error_attribution`（包含 `primary_cause`、`contributing_factors`、`evidence`）和 `pattern_report`。职责边界：Dataset_Profiler 只产事实，Analyst_Agent 负责从事实推导归因
3. THE Hypothesis_Agent SHALL 为唯一调用 GLM 的智能体，接收以下输入：Research_Question_Generator 的研究问题列表、Knowledge_Layer 的相关 Knowledge_Claims、最近一次 Periodic_Reflection 的 `reflection_decision`，输出 1~3 个结构化假设
4. THE Designer_Agent SHALL 为纯规则模块（不调用 GLM），复用现有 `_translate_intent_to_patches` 逻辑，将假设意图翻译为具体的参数 patch

##### 6.2 假设结构化去重

5. THE Hypothesis_Agent SHALL 对生成的假设进行结构化去重：WHEN 新假设的 Patch_Fingerprint（`target_function_id` + `param_key` + `direction`）与已否证假设的 Patch_Fingerprint 匹配, THE Hypothesis_Agent SHALL 确定性拒绝该假设（不依赖 GLM 判断）
6. THE Hypothesis_Agent SHALL 维护已否证假设的 Patch_Fingerprint 索引（`disproved_fingerprints`），每条记录包含 `fingerprint`、`disproved_at_iteration`、`reason`

##### 6.3 Agent 间通信

7. THE Agent_Orchestrator SHALL 通过结构化 JSON 消息在各 Agent 之间传递数据，每条消息包含 `from_agent`、`to_agent`、`message_type`、`payload`、`timestamp`
8. THE Agent_Orchestrator SHALL 记录每轮各 Agent 的输入输出和耗时到 `run_state["agent_traces"]`（`agent_trace` 结构），供调试和审计

##### 6.4 降级与配置

9. THE Agent_Orchestrator SHALL 支持降级模式：IF Hypothesis_Agent 的 GLM 调用失败或超时, THEN THE Agent_Orchestrator SHALL 回退到单一 GLM 研究员模式（现有逻辑），确保系统可用性
10. THE AutoResearch_Engine SHALL 支持通过启动参数 `agent_mode` 配置使用多智能体模式（`multi_agent`）或传统单一模式（`single_agent`，默认值），实现平滑过渡

### Requirement 7: 可视化与数据管理

**User Story:** 作为算法研究员和平台用户，我想在前端查看每轮回测的时序对比图、研究问题和反思记录，并通过统一入口管理数据集，以便直观判断模型表现并规范化数据管理流程。

#### Acceptance Criteria

##### 7.1 时序可视化

1. THE AutoResearch_Engine SHALL 在每轮回测完成后将时序数据（训练集、测试集真实值、预测值、时间戳、峰谷标注）存入 `run_state["iteration_plot_data"]`，供前端 API 拉取
2. THE AutoResearch_Engine SHALL 提供研究问题查询接口（`GET /api/workflows/enhanced/auto-research/{run_id}/research-questions`），返回各轮次生成的研究问题列表
3. THE AutoResearch_Engine SHALL 提供反思记录查询接口（`GET /api/workflows/enhanced/auto-research/{run_id}/reflections`），返回所有 Periodic_Reflection 记录

##### 7.2 数据集画像接口

4. THE Dataset_Profiler SHALL 提供数据集画像接口（`GET /api/workflows/enhanced/datasets/{dataset_id}/profile`），返回指定数据集的 `train_profile`、`validation_profile`（若可用）、`test_profile`、`tri_dataset_diagnosis`
5. WHEN 用户启动 AutoResearch run, THE AutoResearch_Engine SHALL 支持通过 `dataset_id` 参数指定数据集来源，替代当前的硬编码文件路径

##### 7.3 数据集管理

6. THE AutoResearch_Engine SHALL 复用现有上传能力（`/api/upload/file`），并在其上新增 Dataset_Manager 封装层，提供数据集注册接口（`POST /api/workflows/enhanced/datasets/register`），接收已上传文件的 `file_path` 或 `upload_id`，返回 `dataset_id`
7. THE AutoResearch_Engine SHALL 提供数据集列表接口（`GET /api/workflows/enhanced/datasets`），返回所有已注册数据集的元数据
8. IF 注册的文件格式无法解析或不包含可识别的时间列, THEN THE AutoResearch_Engine SHALL 返回包含具体错误原因的错误信息

**路由策略说明**：新增接口统一挂载在 `/api/workflows/enhanced/` 前缀下（与现有 `workflows_enhanced.py` 路由一致），避免引入新的顶层 router。知识检索接口（`/api/workflows/enhanced/knowledge/search`）同理。


### Requirement 8: 接口与数据结构稳定化

**User Story:** 作为系统架构师，我想明确定义系统新增的核心数据结构和 API 接口，以便前后端协作和后续扩展有稳定的契约。

#### Acceptance Criteria

##### 8.1 核心数据结构

1. THE AutoResearch_Engine SHALL 稳定以下数据结构的 JSON Schema：
   - `train_profile` — 训练集画像（含 train_fit_mape）
   - `validation_profile` — 验证集画像（含 cv_fold_losses、cv_val_mape、overfit_indicator、cv_loss_trend）
   - `test_profile` — 测试集画像（含 test_mape、period_error_breakdown）
   - `tri_dataset_diagnosis` — 三集对比诊断报告（含 pattern_consistency、overfit_detection、generalization_assessment）
   - `research_question` — 每轮/每阶段研究问题
   - `experiment_quality` — 实验设计质量评分
   - `knowledge_claim` — 可验证知识单元（含 claim_key、condition、scenario_condition_hash、evidence、counter_evidence）
   - `periodic_reflection` — 阶段性策略判断（含 reflection_decision）
   - `agent_trace` — 多智能体模式下各 Agent 的 I/O 审计记录
   - `error_attribution` — 误差归因（由 Analyst_Agent 输出，非 Dataset_Profiler）

##### 8.2 API 接口

2. THE AutoResearch_Engine SHALL 提供以下新增 API 端点（统一挂载在 `/api/workflows/enhanced/` 前缀下）：
   - `GET /api/workflows/enhanced/knowledge/search` — 知识检索，支持场景指纹匹配、层级过滤、置信度排序
   - `GET /api/workflows/enhanced/datasets/{dataset_id}/profile` — 数据集画像查询
   - `GET /api/workflows/enhanced/auto-research/{run_id}/reflections` — 反思记录查询
   - `GET /api/workflows/enhanced/auto-research/{run_id}/research-questions` — 研究问题查询
   - `POST /api/workflows/enhanced/datasets/register` — 数据集注册（复用现有上传能力）
   - `GET /api/workflows/enhanced/datasets` — 数据集列表
3. THE AutoResearch_Engine SHALL 对所有新增 API 端点返回统一的错误格式：`{"error": {"code": "<error_code>", "message": "<human_readable_message>"}}`

## Test Plan

以下为核心测试场景，覆盖各需求的关键行为：

1. **三集画像识别模式不一致**：构造训练集以工作日为主、测试集为周末的场景，验证 `pattern_consistency` 输出 `pattern_mismatch`
2. **过拟合检测（基于 cv_val_mape）**：构造 `test_mape` 超过 `cv_val_mape` 1.5 倍的场景，验证 `overfit_detection` 为 `confirmed_overfit` 且诊断结论被传递给 Analyst_Agent → Research_Question_Generator
3. **过拟合检测降级（cv 不可用时基于 train_fit_mape）**：WHEN 回测引擎未返回 `cv_fold_metrics`, 验证系统降级为 `test_mape` vs `train_fit_mape` 的 1.5 倍判定
4. **研究问题从归因生成**：给定 Analyst_Agent 输出 `worst_period` 连续 3 窗口为晚高峰，验证 Research_Question_Generator 输出包含"晚高峰"相关问题
5. **知识场景匹配注入**：历史知识仅在 `scenario_condition_hash` 匹配时以正常权重注入；不匹配时降权至 0.3 倍
6. **假设结构化去重**：已否证假设的 Patch_Fingerprint 被新假设复用时，确定性拒绝（不依赖 GLM）
7. **阶段性反思输出 shift_focus**：构造连续 8 轮 MAPE 改善 < 0.05% 的场景，验证反思输出 `decision: shift_focus` 且 `current_research_focus` 写入 run_state
8. **Research Focus 偏置采样（已激活层内）**：当 `priority_layers` 为 `["feature"]` 且 feature 层已被 staged activation 激活时，验证 feature 层参数采样概率为其他已激活层的 2 倍
9. **Research Focus 触发提前激活**：当 `priority_layers` 包含尚未激活的层时，验证该层被 `force_activate` 并记录日志
10. **多智能体降级到单 Agent**：模拟 GLM 调用超时，验证系统回退到 single_agent 模式并继续运行
11. **自动应用仅允许 validator 通过且低风险的 patch**：构造 high risk patch，验证不被自动应用
12. **知识复活**：构造一条 confidence < 0.3 的 stale Knowledge_Claim，新 run 产生支撑证据后，验证 confidence 重新计算且状态恢复为 active
13. **知识冲突生成研究问题**：构造两条 `claim_key.target_param` 相同但 `direction` 相反的 Knowledge_Claim 且无法通过优先级规则解决，验证冲突被注入 Research_Question_Generator
14. **实验质量评分动态权重**：验证前 30% 轮次 w_info > w_metric，后期 w_metric > w_info
15. **Dataset_Profiler 与 Analyst_Agent 职责隔离**：验证 Dataset_Profiler 输出中不包含 `error_attribution` 字段，`error_attribution` 仅由 Analyst_Agent 产出
