<!-- @AI_GENERATED -->
# 实施计划：运营分析 Agent（Operations Analysis Agent）

## 概述

基于现有 `algorithm_agent.py` 对话端点和 `AgentToolExecutor` 工具框架，为运营分析 Agent 新增 8 个专用工具函数、运营分析专用 system prompt、工具按 agent_type 隔离机制和多步工具调用支持。实施顺序：框架改造 → 数据获取工具 → 分析工具 → 根因和建议工具 → 前端集成 → 端到端验证。

## Tasks

- [x] 1. 框架改造：工具隔离与多步调用支持
  - [x] 1.1 在 `backend-service/services/agent_tools.py` 中新增 `OPERATION_AGENT_TOOLS` 空列表，改造 `get_tools_definition()` 函数接受 `agent_type` 参数，当 `agent_type="operation"` 时返回 `OPERATION_AGENT_TOOLS`，其他情况返回现有 `AGENT_TOOLS`
    - 在文件顶部 `AGENT_TOOLS` 列表之后新增 `OPERATION_AGENT_TOOLS = []`
    - 修改 `get_tools_definition(agent_type: str = None)` 签名和逻辑
    - _需求：11.1, 11.2_

  - [x] 1.2 在 `backend-service/api/algorithm_agent.py` 中替换 `AGENT_SYSTEM_PROMPTS["operation"]` 为运营分析专用 system prompt
    - 定义 Agent 角色为"负荷预测运营分析专家"
    - 包含能力范围（精度分析、根因分析、改进建议）
    - 包含工具调用规则表（用户意图 → 推荐工具链）
    - 包含回答格式要求（Markdown 表格、指标高亮）
    - _需求：1.1, 1.2_

  - [x] 1.3 改造 `backend-service/api/algorithm_agent.py` 中的 `chat_stream()` 函数，在非 curator 的 LLM 流式路径中传递 `agent_type` 给 `get_tools_definition()`
    - 修改 `from services.agent_tools import get_tools_definition` 调用处，传入 `agent_type`
    - 当 `agent_type="operation"` 时，使用带工具的非流式 `generate_llm_response()` 路径（与 Function Calling 兼容），而非纯流式路径
    - _需求：1.1, 1.8_

  - [x] 1.4 改造 `backend-service/api/algorithm_agent.py` 中的 `generate_llm_response()` 函数，支持多步工具调用循环（最多 5 轮）
    - 将现有的单轮工具调用逻辑改为 `for round in range(5)` 循环
    - 每轮检查 LLM 响应是否包含 `tool_calls`，无则跳出循环
    - 每轮执行所有 tool_calls，结果追加到 messages
    - 传递 `agent_type` 给 `get_tools_definition()`
    - _需求：1.4, 1.5_

  - [ ]* 1.5 编写属性测试：工具定义格式正确性（属性 9）
    - **属性 9：工具定义格式正确性**
    - 验证 `OPERATION_AGENT_TOOLS` 中每个工具包含 `type="function"`、`function.name`（非空字符串）、`function.description`（非空字符串）和 `function.parameters`（合法 JSON Schema）
    - **验证需求：11.1**

  - [ ]* 1.6 编写属性测试：工具按 agent_type 隔离（属性 10）
    - **属性 10：工具按 agent_type 隔离**
    - 验证对于任意 `agent_type` 不等于 `"operation"` 的情况，`get_tools_definition(agent_type)` 返回的工具列表不包含运营分析专用工具名称
    - **验证需求：11.2**

- [x] 2. Checkpoint — 确保框架改造完成
  - 确保所有测试通过，ask the user if questions arise.

- [x] 3. 数据获取工具：get_backtest_results 和 get_training_results
  - [x] 3.1 在 `backend-service/services/agent_tools.py` 的 `OPERATION_AGENT_TOOLS` 列表中添加 `get_backtest_results` 和 `get_training_results` 的 OpenAI Function Calling 格式工具定义
    - 包含 `name`、`description`（中文）、`parameters`（JSON Schema）
    - `get_backtest_results` 参数：`workflow_id`（可选）、`task_id`（可选）
    - `get_training_results` 参数：`workflow_id`（可选）、`task_id`（可选）
    - _需求：2.1, 3.1, 11.1_

  - [x] 3.2 在 `AgentToolExecutor` 中实现 `get_backtest_results` 方法
    - 数据来源优先级：`task_store`（内存）→ `_backtest_artifacts/` 目录（持久化 CSV）→ `workflows_enhanced` 执行结果
    - 返回结构：`task_type`、`date_range`、`total_days`、`success_days`、`avg_metrics`、`daily_results`
    - 未指定参数时返回最近一次回测结果
    - 数据不存在时返回标准错误 JSON + 可用任务列表
    - _需求：2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.3 在 `AgentToolExecutor` 中实现 `get_training_results` 方法
    - 从 `task_store` 中查找 `task_type="train"` 且 `status="success"` 的最近一条
    - 返回结构：`model_id`、`task_type`、`training_duration`、`feature_importance`（Top-20 降序）、`eval_metrics`、`model_params`
    - 数据不存在时返回标准错误 JSON
    - _需求：3.1, 3.2, 3.3, 3.4_

  - [x] 3.4 在 `AgentToolExecutor.execute()` 路由中添加 `get_backtest_results` 和 `get_training_results` 分支
    - _需求：1.4_

  - [ ]* 3.5 编写属性测试：特征重要性排序不变量（属性 12）
    - **属性 12：特征重要性排序不变量**
    - 验证 `get_training_results` 返回的 `feature_importance` 列表按 `score` 降序排列
    - **验证需求：3.3**

  - [ ]* 3.6 编写属性测试：工具错误处理结构一致性（属性 11）
    - **属性 11：工具错误处理结构一致性**
    - 验证工具执行异常时返回的错误结果包含 `error`（True）、`error_type`（字符串）和 `error_message`（字符串）三个字段
    - **验证需求：1.7, 11.4**

- [x] 4. Checkpoint — 确保数据获取工具正常工作
  - 确保所有测试通过，ask the user if questions arise.

- [x] 5. 分析工具：analyze_accuracy_trend、analyze_accuracy_by_period、check_accuracy_compliance
  - [x] 5.1 在 `OPERATION_AGENT_TOOLS` 列表中添加 `analyze_accuracy_trend`、`analyze_accuracy_by_period`、`check_accuracy_compliance` 的工具定义
    - `analyze_accuracy_trend` 参数：`daily_metrics`（可选）、`metric_name`（默认 "smape"）
    - `analyze_accuracy_by_period` 参数：`daily_results`（可选）、`group_by`（"hour"|"weekday"|"month"）
    - `check_accuracy_compliance` 参数：`daily_metrics`（可选）、`task_type`（默认 "D"）、`threshold_override`（可选）
    - _需求：4.1, 5.1, 6.1, 11.1_

  - [x] 5.2 在 `AgentToolExecutor` 中实现 `analyze_accuracy_trend` 方法
    - 使用 `numpy.polyfit(x, y, 1)[0]` 计算线性回归斜率
    - 趋势方向分类：斜率 > 0.1 为"恶化趋势"，< -0.1 为"改善趋势"，其余为"稳定"
    - 异常日检测：SMAPE > mean + 2 * std
    - 移动平均：3 日滑动窗口
    - 返回结构：`overall`（均值/标准差/最大值/最小值及日期）、`trend`（斜率/方向/描述）、`moving_average`、`anomaly_days`
    - _需求：4.1, 4.2, 4.3, 4.4_

  - [x] 5.3 在 `AgentToolExecutor` 中实现 `analyze_accuracy_by_period` 方法
    - `hour` 分组：按 15 分钟间隔的小时分组，计算每小时 SMAPE
    - `weekday` 分组：按工作日/休息日两组
    - `month` 分组：按月份分组
    - 返回结构：`groups`（每组 label/count/mean_smape/std/max/min）、`worst_period`、`best_period`
    - _需求：5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 5.4 在 `AgentToolExecutor` 中实现 `check_accuracy_compliance` 方法
    - 默认阈值：`{"DI": 8.0, "D": 5.0, "WI": 10.0, "W": 10.0, "MI": 15.0, "M": 15.0}`
    - 支持 `threshold_override` 自定义阈值
    - 返回结构：`threshold`、`avg_smape`、`compliant`、`compliance_rate`、`compliant_days`、`non_compliant_days`
    - _需求：6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 5.5 在 `AgentToolExecutor.execute()` 路由中添加三个分析工具的分支
    - _需求：1.4_

  - [ ]* 5.6 编写属性测试：趋势分析统计计算正确性（属性 1）
    - **属性 1：趋势分析统计计算正确性**
    - 生成随机 SMAPE 序列，验证均值、标准差、最大值、最小值与 numpy 计算结果一致；最大值/最小值日期正确；移动平均窗口为 3
    - **验证需求：4.1, 4.2**

  - [ ]* 5.7 编写属性测试：趋势方向分类正确性（属性 2）
    - **属性 2：趋势方向分类正确性**
    - 生成随机斜率值，验证趋势方向分类：斜率 > 0.1 → "恶化趋势"，< -0.1 → "改善趋势"，其余 → "稳定"
    - **验证需求：4.3**

  - [ ]* 5.8 编写属性测试：异常日检测正确性（属性 3）
    - **属性 3：异常日检测正确性**
    - 生成随机 SMAPE 序列，验证检测到的异常日集合恰好等于 SMAPE > mean + 2 * std 的日期集合
    - **验证需求：4.4**

  - [ ]* 5.9 编写属性测试：时段分组完整性与统计正确性（属性 4）
    - **属性 4：时段分组完整性与统计正确性**
    - 生成随机逐日结果数据，验证所有分组样本数之和等于原始数据总量；每组均值、标准差与 numpy 一致
    - **验证需求：5.1, 5.5**

  - [ ]* 5.10 编写属性测试：精度达标判定正确性（属性 5）
    - **属性 5：精度达标判定正确性**
    - 生成随机 SMAPE 值和阈值，验证不达标天数列表恰好等于 SMAPE > threshold 的日期集合；达标率 = compliant_days / total_days × 100
    - **验证需求：6.1, 6.3, 6.5**

- [x] 6. Checkpoint — 确保分析工具正常工作
  - 确保所有测试通过，ask the user if questions arise.

- [x] 7. 根因和建议工具：diagnose_data_quality、perform_root_cause_analysis、generate_improvement_suggestions
  - [x] 7.1 在 `OPERATION_AGENT_TOOLS` 列表中添加 `diagnose_data_quality`、`perform_root_cause_analysis`、`generate_improvement_suggestions` 的工具定义
    - `diagnose_data_quality` 参数：`daily_results`（可选）
    - `perform_root_cause_analysis` 参数：`daily_results`（可选）、`training_info`（可选）
    - `generate_improvement_suggestions` 参数：`root_causes`（可选）
    - _需求：7.1, 8.1, 9.1, 11.1_

  - [x] 7.2 在 `AgentToolExecutor` 中实现 `diagnose_data_quality` 方法
    - 四个维度评分：`missing_ratio`（100 - missing_pct × 10）、`outlier_ratio`（100 - outlier_pct × 5）、`time_continuity`、`value_range`
    - 综合评分：加权平均（权重 0.3, 0.25, 0.25, 0.2）
    - `has_quality_issues` = overall_score < 80
    - 关联分析：异常日与数据质量问题日期重合检查
    - _需求：7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 7.3 在 `AgentToolExecutor` 中实现 `perform_root_cause_analysis` 方法
    - 按优先级检查：data_quality → feature_coverage → model_params → seasonal_change → external_factors
    - 每个根因包含：`cause_type`、`confidence`（0-1）、`evidence`、`impact`
    - _需求：8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 7.4 在 `AgentToolExecutor` 中实现 `generate_improvement_suggestions` 方法
    - 根因到建议的映射规则：data_quality → 数据清洗策略、feature_coverage → 特征工程建议、model_params → 参数调优建议、seasonal_change → 重训策略、external_factors → 外部数据接入建议
    - 每条建议包含：`action`、`priority`、`expected_improvement`、`effort`、`related_cause`
    - 按优先级降序排列（高 > 中 > 低）
    - _需求：9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 7.5 在 `AgentToolExecutor.execute()` 路由中添加三个根因/建议工具的分支
    - _需求：1.4_

  - [ ]* 7.6 编写属性测试：数据质量评分范围与阈值判定（属性 6）
    - **属性 6：数据质量评分范围与阈值判定**
    - 生成随机维度评分（0-100），验证综合评分在 [0, 100] 范围内；`has_quality_issues` 为 true 当且仅当 overall_score < 80
    - **验证需求：7.3, 7.4**

  - [ ]* 7.7 编写属性测试：根因分析输出结构完整性（属性 7）
    - **属性 7：根因分析输出结构完整性**
    - 验证每个根因条目包含 `cause_type`（字符串）、`confidence`（0-1 浮点数）、`evidence`（字符串）和 `impact`（字符串）
    - **验证需求：8.7**

  - [ ]* 7.8 编写属性测试：改进建议完整性与排序（属性 8）
    - **属性 8：改进建议完整性与排序**
    - 生成随机根因列表，验证建议列表非空；每条建议包含 `action`、`priority`、`expected_improvement`、`effort`；按优先级降序排列（高 > 中 > 低）
    - **验证需求：9.1, 9.2, 9.6**

- [x] 8. Checkpoint — 确保根因和建议工具正常工作
  - 确保所有测试通过，ask the user if questions arise.

- [x] 9. 前端集成与端到端验证
  - [x] 9.1 确认前端 Agent 对话界面在选择 `agent_type="operation"` 时正确传递 `context.agent_type: "operation"` 到 `/api/agent/chat/stream` 端点
    - 检查前端代码中 agent_type 选择逻辑
    - 确保 operation 类型在前端选项中可用
    - _需求：10.1_

  - [x] 9.2 在 `backend-service/api/algorithm_agent.py` 的 `chat_stream()` 中，为 `agent_type="operation"` 添加带工具的 Function Calling 流式路径
    - 当 `agent_type="operation"` 时，先执行 `generate_llm_response()`（含多步工具调用），再将最终结果以 SSE 流式输出
    - 确保工具调用阶段非流式执行，最终响应流式输出
    - _需求：1.1, 1.8, 10.1_

  - [ ]* 9.3 编写端到端集成测试（mock LLM）
    - 测试完整对话流程：用户提问 → 工具调用 → 结果生成
    - 测试多步工具调用链：获取数据 → 趋势分析 → 根因分析 → 改进建议
    - 测试 SSE 流式输出格式
    - _需求：1.4, 1.5, 1.8_

- [x] 10. Final checkpoint — 确保所有测试通过
  - 确保所有测试通过，ask the user if questions arise.

## Notes

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号以确保可追溯性
- Checkpoint 任务确保增量验证
- 属性测试验证设计文档中定义的 12 个正确性属性
- 所有工具函数使用统一的 try-except 错误处理，返回标准错误 JSON
- 实现语言为 Python，与现有代码库一致
<!-- @AI_GENERATED: end -->
