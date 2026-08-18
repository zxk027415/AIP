<!-- @AI_GENERATED -->
# 需求文档：运营分析 Agent（Operations Analysis Agent）

## 简介

本文档定义了 AIP 平台"运营分析 Agent"的功能需求。运营分析 Agent 是平台四个 Agent 之一，专注于对已完成的负荷预测训练/回测结果进行精度分析和根因分析。

当前系统已具备完整的负荷预测工作流基础设施（训练流水线、推理流水线、回测流水线），回测结果包含逐日的 SMAPE、MAE、RMSE 指标和预测值/真实值序列。运营分析 Agent 的核心目标是：基于这些已有数据，提供智能化的精度分析能力（趋势识别、时段对比、异常日检测）和根因分析能力（数据质量诊断、特征覆盖度评估、模型参数适配性分析），帮助用户快速定位精度问题并获得改进建议。

运营分析 Agent 采用 LLM + Function Calling 架构：不设独立的意图分类或路由层，而是将所有分析能力封装为标准工具函数（tools），注册到现有的 `AgentToolExecutor` 框架中。当 `agent_type` 为 `operation` 时，使用运营分析专用的 system prompt 和工具集调用 LLM，由 LLM 自主决定调用哪些工具、以什么顺序编排分析链，最终整合工具结果生成自然语言响应。这种方式复用现有的 `algorithm_agent.py` 对话端点和 `llm_service` 流式输出能力，无需新建独立的 API 路由。

## 术语表

- **Operations_Analysis_Agent（运营分析 Agent）**: AIP 平台的运营分析智能体，负责对负荷预测结果进行精度分析和根因分析
- **Accuracy_Analysis（精度分析）**: 对训练/回测结果的精度指标（SMAPE、MAE、RMSE）进行多维度统计分析，包括趋势识别、时段对比、异常日检测
- **Root_Cause_Analysis（根因分析）**: 当精度不达标时，自动诊断可能的原因并给出改进建议
- **Accuracy_Threshold（精度阈值）**: 判定精度是否达标的标准值，不同预测场景有不同阈值（如日前预测 SMAPE ≤ 5%）
- **Backtest_Result（回测结果）**: 回测流水线执行后产生的结果数据，包含逐日的预测值、真实值和评估指标
- **Training_Result（训练结果）**: 训练流水线执行后产生的结果数据，包含模型信息、评估指标、特征重要性
- **Anomaly_Day（异常日）**: 精度指标显著偏离整体均值的日期，通常 SMAPE 超过均值 + 2 倍标准差
- **Time_Period_Analysis（时段分析）**: 按时间维度（小时、工作日/休息日、月份）对精度进行分组统计
- **Feature_Importance（特征重要性）**: XGBoost 模型训练后输出的各特征对预测结果的贡献度排名
- **Data_Quality_Score（数据质量评分）**: 对输入数据的完整性、连续性、异常比例等维度的综合评分
- **Improvement_Suggestion（改进建议）**: 根因分析后给出的具体改进措施，包含优先级和预期效果
- **Operations_System_Prompt（运营分析系统提示词）**: 运营分析 Agent 专用的 LLM system prompt，定义 Agent 角色、能力范围和工具使用指引
- **Operations_Tools（运营分析工具集）**: 运营分析 Agent 专用的 Function Calling 工具定义列表，注册在 `AgentToolExecutor` 中

## 需求

### 需求 1：运营分析 Agent 后端服务架构（LLM + Function Calling）

**用户故事：** 作为平台开发者，我想基于现有的 `algorithm_agent.py` 对话端点和 `AgentToolExecutor` 工具框架，为运营分析 Agent 接入 LLM + Function Calling 能力，以便 LLM 自主编排分析工具链处理用户的精度分析和根因分析请求。

#### 验收标准

1. WHEN 用户在 Agent 对话界面选择 `agent_type` 为 `operation`, THE `algorithm_agent.py` 中的 `chat_stream` 端点 SHALL 使用 Operations_System_Prompt 和 Operations_Tools 调用 LLM，而非通用的 system prompt
2. THE Operations_System_Prompt SHALL 定义 Agent 角色为"负荷预测运营分析专家"，明确其能力范围（精度分析、根因分析、改进建议），并指引 LLM 在需要数据时主动调用工具函数
3. THE Operations_Tools SHALL 作为独立的工具定义列表注册在 `AgentToolExecutor` 中，包含本文档需求 2-9 定义的所有工具函数
4. WHEN LLM 返回 `tool_calls` 响应, THE `generate_llm_response` 函数 SHALL 解析工具调用参数、通过 `AgentToolExecutor.execute()` 执行对应工具、将结果作为 `tool` 角色消息回传给 LLM 生成最终自然语言响应
5. THE Operations_Analysis_Agent SHALL 支持多步工具调用：LLM 可在一次对话中依次调用多个工具（如先获取回测数据 → 再做趋势分析 → 再做根因分析），每步工具结果回传后 LLM 决定是否继续调用下一个工具
6. THE Operations_Analysis_Agent SHALL 维护会话上下文（复用现有 `sessions` 字典），在多轮对话中保持分析状态，LLM 可基于历史消息理解上下文
7. WHEN LLM 调用工具过程中发生异常, THE `AgentToolExecutor` SHALL 返回包含错误类型和错误信息的 JSON 结果，LLM 基于错误信息生成用户友好的错误提示
8. THE Operations_Analysis_Agent SHALL 支持流式响应（SSE 格式），复用现有 `chat_stream` 的流式输出机制；工具调用阶段以非流式方式执行，工具结果回传后 LLM 的最终响应以流式方式输出

### 需求 2：回测结果数据获取工具

**用户故事：** 作为运营分析 Agent 的用户，我想让 Agent 能够自动获取最近的回测结果数据，以便基于真实数据进行精度分析。

#### 验收标准

1. THE Operations_Analysis_Agent SHALL 在 `AgentToolExecutor` 中注册 `get_backtest_results` 工具函数，从 `data/workflows_enhanced/_backtest_artifacts/` 目录和工作流执行结果中读取回测数据
2. WHEN `get_backtest_results` 工具被调用且指定 `workflow_id` 参数, THE 工具 SHALL 返回该工作流最近一次回测的逐日结果（日期、SMAPE、MAE、RMSE、预测值数组、真实值数组）
3. WHEN `get_backtest_results` 工具被调用且未指定 `workflow_id`, THE 工具 SHALL 返回系统中最近一次回测任务的结果
4. THE `get_backtest_results` 工具 SHALL 返回的数据结构包含：`task_type`（预测场景）、`date_range`（回测日期范围）、`total_days`（总天数）、`success_days`（成功天数）、`avg_metrics`（平均指标）、`daily_results`（逐日明细）
5. IF 指定的回测结果不存在, THEN THE 工具 SHALL 返回错误信息并列出可用的回测任务列表

### 需求 3：训练结果数据获取工具

**用户故事：** 作为运营分析 Agent 的用户，我想让 Agent 能够获取训练结果数据（模型信息、特征重要性、评估指标），以便进行模型层面的分析。

#### 验收标准

1. THE Operations_Analysis_Agent SHALL 在 `AgentToolExecutor` 中注册 `get_training_results` 工具函数，从工作流执行结果中读取训练数据
2. WHEN `get_training_results` 工具被调用, THE 工具 SHALL 返回最近一次训练的结果，包含：`model_id`、`task_type`、`training_duration`、`feature_importance`（特征重要性 Top-20）、`eval_metrics`（训练集/验证集指标）、`model_params`（模型超参数）
3. THE `get_training_results` 工具 SHALL 返回的 `feature_importance` 为按重要性降序排列的特征名称和分数列表
4. IF 训练结果不存在, THEN THE 工具 SHALL 返回错误信息

### 需求 4：精度趋势分析工具

**用户故事：** 作为运营分析 Agent 的用户，我想分析回测精度的时间趋势，以便识别精度是否在恶化或改善。

#### 验收标准

1. THE Operations_Analysis_Agent SHALL 在 `AgentToolExecutor` 中注册 `analyze_accuracy_trend` 工具函数，对回测逐日指标进行趋势分析
2. WHEN `analyze_accuracy_trend` 工具被调用, THE 工具 SHALL 计算以下趋势指标：整体均值、标准差、最大值日期、最小值日期、线性趋势斜率（正值表示精度恶化）、移动平均线（3 日窗口）
3. THE `analyze_accuracy_trend` 工具 SHALL 基于线性趋势斜率判定趋势方向：斜率 > 0.1 为"恶化趋势"，斜率 < -0.1 为"改善趋势"，其余为"稳定"
4. THE `analyze_accuracy_trend` 工具 SHALL 检测异常日：SMAPE 超过均值 + 2 倍标准差的日期标记为 Anomaly_Day，返回异常日列表及其指标值

### 需求 5：时段精度对比分析工具

**用户故事：** 作为运营分析 Agent 的用户，我想对比不同时段（小时、工作日/休息日、月份）的精度表现，以便识别精度薄弱的时段。

#### 验收标准

1. THE Operations_Analysis_Agent SHALL 在 `AgentToolExecutor` 中注册 `analyze_accuracy_by_period` 工具函数，按时间维度对精度进行分组统计
2. WHEN `analyze_accuracy_by_period` 工具被调用且 `group_by` 参数为 `hour`, THE 工具 SHALL 按 24 小时分组计算每个小时的平均 SMAPE/MAE/RMSE，识别精度最差和最好的时段
3. WHEN `analyze_accuracy_by_period` 工具被调用且 `group_by` 参数为 `weekday`, THE 工具 SHALL 按工作日/休息日分组计算精度指标，对比两组的差异
4. WHEN `analyze_accuracy_by_period` 工具被调用且 `group_by` 参数为 `month`, THE 工具 SHALL 按月份分组计算精度指标，识别季节性精度变化
5. THE `analyze_accuracy_by_period` 工具 SHALL 返回每组的样本数、均值、标准差、最大值和最小值

### 需求 6：精度达标判定工具

**用户故事：** 作为运营分析 Agent 的用户，我想让 Agent 自动判定当前精度是否达标，以便快速了解模型状态。

#### 验收标准

1. THE Operations_Analysis_Agent SHALL 在 `AgentToolExecutor` 中注册 `check_accuracy_compliance` 工具函数，根据预测场景的精度阈值判定是否达标
2. THE `check_accuracy_compliance` 工具 SHALL 使用以下默认精度阈值：日内（DI）SMAPE ≤ 8%、日前（D）SMAPE ≤ 5%、周前（W）SMAPE ≤ 10%、月前（M）SMAPE ≤ 15%
3. WHEN 整体平均 SMAPE 超过对应场景的阈值, THE 工具 SHALL 返回 `compliant: false` 并标记不达标的具体天数和指标值
4. THE `check_accuracy_compliance` 工具 SHALL 支持通过 `threshold_override` 参数自定义精度阈值
5. THE `check_accuracy_compliance` 工具 SHALL 返回达标率（达标天数 / 总天数 × 100%）

### 需求 7：数据质量诊断工具

**用户故事：** 作为运营分析 Agent 的用户，我想让 Agent 诊断输入数据的质量问题，以便确定精度不达标是否由数据质量引起。

#### 验收标准

1. THE Operations_Analysis_Agent SHALL 在 `AgentToolExecutor` 中注册 `diagnose_data_quality` 工具函数，对回测期间的输入数据进行质量评估
2. THE `diagnose_data_quality` 工具 SHALL 检测以下数据质量维度：缺失值比例、异常值比例、时间连续性（是否有时间断点）、数值范围合理性（是否有负值或极端值）
3. THE `diagnose_data_quality` 工具 SHALL 为每个维度给出 0-100 的评分，并计算综合 Data_Quality_Score
4. WHEN Data_Quality_Score 低于 80, THE 工具 SHALL 标记为"数据质量问题"并列出具体问题点
5. THE `diagnose_data_quality` 工具 SHALL 将数据质量问题与精度异常日进行关联分析：检查异常日是否与数据质量问题日期重合

### 需求 8：根因分析引擎

**用户故事：** 作为运营分析 Agent 的用户，我想让 Agent 在精度不达标时自动进行根因分析，以便快速定位问题原因。

#### 验收标准

1. THE Operations_Analysis_Agent SHALL 在 `AgentToolExecutor` 中注册 `perform_root_cause_analysis` 工具函数，综合多维度信息进行根因诊断
2. THE `perform_root_cause_analysis` 工具 SHALL 按以下优先级顺序检查根因：数据质量问题 → 特征覆盖不足 → 模型参数不优 → 季节性/趋势变化 → 外部因素
3. WHEN 根因为"数据质量问题", THE 工具 SHALL 返回具体的数据问题描述（如"2025-03-20 缺失率 15%，导致该日 SMAPE 达 12%"）
4. WHEN 根因为"特征覆盖不足", THE 工具 SHALL 分析特征重要性排名，识别缺失的关键特征类型（如"缺少气象特征导致极端天气日预测偏差大"）
5. WHEN 根因为"模型参数不优", THE 工具 SHALL 分析模型超参数并与推荐值对比，识别可能的过拟合或欠拟合信号
6. WHEN 根因为"季节性变化", THE 工具 SHALL 检测训练数据是否覆盖当前季节的模式，识别分布偏移
7. THE `perform_root_cause_analysis` 工具 SHALL 返回根因列表，每个根因包含：`cause_type`（原因类型）、`confidence`（置信度 0-1）、`evidence`（证据描述）、`impact`（影响程度）

### 需求 9：改进建议生成工具

**用户故事：** 作为运营分析 Agent 的用户，我想在根因分析后获得具体的改进建议，以便知道下一步该如何优化模型。

#### 验收标准

1. THE Operations_Analysis_Agent SHALL 在 `AgentToolExecutor` 中注册 `generate_improvement_suggestions` 工具函数，基于根因分析结果生成改进建议
2. THE `generate_improvement_suggestions` 工具 SHALL 为每个根因生成对应的改进措施，每条建议包含：`action`（具体操作）、`priority`（优先级：高/中/低）、`expected_improvement`（预期改善幅度）、`effort`（实施难度：简单/中等/复杂）
3. WHEN 根因为"数据质量问题", THE 工具 SHALL 建议具体的数据清洗策略（如"对缺失率 > 10% 的日期使用前向填充 + 周期性插值"）
4. WHEN 根因为"特征覆盖不足", THE 工具 SHALL 建议添加的特征类型和数据源（如"接入气象预报数据，添加温度、湿度特征"）
5. WHEN 根因为"模型参数不优", THE 工具 SHALL 建议具体的参数调整方向（如"增大 max_depth 至 8，减小 learning_rate 至 0.01"）
6. THE `generate_improvement_suggestions` 工具 SHALL 按优先级降序排列建议列表

### 需求 10：运营分析 Agent 前端对话界面集成

**用户故事：** 作为平台用户，我想在 Agent 对话界面中选择"运营分析"Agent 类型后，通过自然语言与 Agent 交互进行精度分析和根因分析。

#### 验收标准

1. WHEN 用户在 Agent 对话界面选择 `agent_type` 为 `operation`, THE 前端 SHALL 复用现有的 `/api/agent/chat/stream` 端点，在请求 context 中传递 `agent_type: "operation"`
2. THE 前端 SHALL 为运营分析 Agent 提供以下快捷指令：「分析最近回测精度」、「精度是否达标」、「为什么精度不好」、「给出改进建议」
3. THE Operations_Analysis_Agent SHALL 在响应中使用 Markdown 格式展示分析结果，包含表格、列表和重点标记
4. WHEN Agent 响应包含精度指标数据, THE 前端 SHALL 以 Markdown 表格形式展示逐日指标（复用现有的 Markdown 渲染组件）
5. WHEN Agent 响应包含改进建议, THE 前端 SHALL 以优先级标记的列表形式展示建议

### 需求 11：运营分析工具的 Function Calling 定义

**用户故事：** 作为平台开发者，我想确保运营分析工具的 Function Calling 定义标准化，以便 LLM 能正确理解工具能力并生成合法的调用参数。

#### 验收标准

1. THE Operations_Analysis_Agent 的所有工具函数 SHALL 在 `get_tools_definition()` 中注册标准的 OpenAI Function Calling 格式定义，包含 `name`、`description`（中文描述，帮助 LLM 理解工具用途）、`parameters`（JSON Schema，定义参数类型和约束）
2. THE 工具定义 SHALL 仅在 `agent_type` 为 `operation` 时包含在传给 LLM 的 tools 列表中，避免其他 Agent 类型误调用运营分析工具
3. THE Operations_Analysis_Agent 的所有工具函数 SHALL 接收 JSON 可序列化的参数并返回 JSON 可序列化的结果
4. IF 工具执行过程中发生异常, THEN THE `AgentToolExecutor` SHALL 返回包含 `error: true`、`error_type` 和 `error_message` 的 JSON 结果，LLM 基于错误信息生成用户友好的错误提示
<!-- @AI_GENERATED: end -->
