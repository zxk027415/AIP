<!-- @AI_GENERATED -->
# 实施计划：负荷预测项目融合到 AIP 算法平台

## 概述

按照渐进式策略，将现有电力负荷预测项目融合到 AIP 工业AI算法平台。实施路径为：先创建 REST API 端点包装现有代码，再注册 Agent Tool 和 AutoResearch Skill 包，然后把 6 个预测步骤注册为可视化编辑器中的 Function 节点并实现执行代码。全程不修改现有核心模块，通过 import 直接调用。

## Tasks

- [x] 1. REST API 端点与路由注册
  - [x] 1.1 创建 REST API 路由模块 `AIP-service/backend/api/load_forecast.py`
    - 创建 FastAPI Router，路由前缀为 `/api/load-forecast`
    - 实现内存任务状态存储（`task_store` 字典）和 `TaskStatus` 数据结构（task_id, status, current_step, completed_steps, step_durations, total_duration, error_message, error_step, created_at, updated_at, result）
    - 实现 `POST /api/load-forecast/train` 端点：接收 JSON 请求体，生成唯一 task_id，内部依次 import 调用 `offline_load_data()` → `get_completed_timestamp()` → `chebyshev_detector()` → `get_completed_df()` → `add_more_features()` → `model_prefer_trainer()`，每步更新任务状态和日志，返回 `{task_id, status, model_id, duration_seconds, steps_completed, metrics}`
    - 实现 `POST /api/load-forecast/predict` 端点：接收 JSON 请求体，内部 import 调用数据获取、异常检测、特征工程和 `LoadForecastWrapper.predict()`，返回预测时间戳列表和预测值列表
    - 实现 `POST /api/load-forecast/backtest` 端点：接收 JSON 请求体（含 start_date, end_date），按日期循环调用训练和预测流程（复用 `run.py` 中 `run_backtest()` 的逻辑），返回每日预测结果和评估指标
    - 实现 `GET /api/load-forecast/scenarios` 端点：读取 `SCENARIO_CONFIGS` 返回六种预测场景（DI/D/WI/W/MI/M）的配置信息
    - 实现 `GET /api/load-forecast/status/{task_id}` 端点：从内存任务状态存储中查询执行状态
    - 所有端点使用 `loguru.logger` 在每个关键步骤开始和结束时记录日志（步骤名称、耗时、数据量）
    - 异常处理：捕获异常后返回统一错误响应 `{task_id, status:"failed", error_type, error_message, failed_step, traceback}`，HTTP 状态码 500；参数校验错误返回 400
    - 数据在 Python 进程内以原生对象（DataFrame、dict、模型对象）直接传递，不经过序列化/反序列化
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 6.1, 6.2, 6.3, 6.4_

  - [x] 1.2 在 `AIP-service/backend/main.py` 中注册负荷预测路由
    - 添加 `from api.load_forecast import router as load_forecast_router`
    - 添加 `app.include_router(load_forecast_router)`
    - _Requirements: 3.2, 3.3_

  - [ ] 1.3 编写 REST API 端点的属性测试
    - **Property 1: 错误响应结构一致性** — 对任意无效请求配置，验证错误响应始终包含 `error_type`、`error_message`、`failed_step` 三个字段
    - **Validates: Requirements 1.6**

  - [ ]* 1.4 编写 REST API 端点的单元测试
    - 测试各端点的正常请求/响应格式
    - 测试参数校验（无效 task_type、缺少必填字段）
    - 测试任务状态查询
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. Checkpoint — 确保 REST API 端点可用
  - 确保所有测试通过，ask the user if questions arise.

- [x] 3. Agent Tool 集成
  - [x] 3.1 在 `agent_tools.py` 的 `AGENT_TOOLS` 列表中添加 5 个负荷预测工具定义
    - 添加 `trigger_load_forecast_train`：描述"触发负荷预测模型训练"，参数含 task_type、config_override
    - 添加 `trigger_load_forecast_predict`：描述"触发负荷预测"，参数含 task_type、parent_id、child_id、forecast_horizon
    - 添加 `trigger_load_forecast_backtest`：描述"触发负荷预测回测评估"，参数含 task_type、start_date、end_date
    - 添加 `get_forecast_scenarios`：描述"获取负荷预测支持的场景列表"，无必填参数
    - 添加 `get_forecast_status`：描述"查询负荷预测任务的执行状态"，参数含 task_id
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.2 在 `AgentToolExecutor` 类中实现 5 个工具的执行方法
    - 在 `execute` 方法中添加 5 个工具名的分发逻辑
    - 每个执行方法内部通过 `httpx.AsyncClient` 调用对应的 REST API 端点
    - 将 API 响应转换为适合大模型理解的结构化结果
    - _Requirements: 2.6_

  - [x] 3.3 实现 LLM 降级关键词匹配规则引擎
    - 当 LLM 不可用时，根据关键词匹配分发到正确的工具："训练"/"train" → `trigger_load_forecast_train`，"预测"/"predict"/"forecast" → `trigger_load_forecast_predict`，"回测"/"backtest" → `trigger_load_forecast_backtest`，"场景"/"scenario" → `get_forecast_scenarios`
    - _Requirements: 2.9_

  - [ ] 3.4 编写关键词降级分发的属性测试
    - **Property 2: 关键词降级分发正确性** — 对任意包含负荷预测相关关键词的消息，验证规则引擎分发到正确的工具
    - **Validates: Requirements 2.9**

- [x] 4. System Prompt 与场景知识库更新
  - [x] 4.1 更新 Algorithm Agent 的 System Prompt
    - 在 `algorithm_agent.py` 的 `get_system_prompt` 函数中添加负荷预测领域知识
    - 包括六种场景的适用范围、典型对话示例和推荐的交互流程
    - 设计标准对话流程：用户描述需求 → AI 确认场景类型 → AI 确认关键参数 → AI 触发执行 → AI 返回结果摘要
    - _Requirements: 2.7, 2.10_

  - [x] 4.2 更新 `data/forecast_scenarios.json`
    - 添加负荷预测场景的详细知识库
    - 包括每种场景（DI/D/WI/W/MI/M）的业务描述、数据要求、精度目标和推荐配置
    - _Requirements: 2.8_

- [x] 5. Checkpoint — 确保 Agent Tool 集成完成
  - 确保所有测试通过，ask the user if questions arise.

- [x] 6. AutoResearch Skill 包与平台注册
  - [x] 6.1 创建 `data/skills/load-forecast/program.md`
    - 定义实验目标（最小化 SMAPE）、实验规则（可修改 train.py、不可修改 prepare.py）
    - 定义输出格式、结果记录格式和实验循环流程
    - 参考 `pv-power-forecast/program.md` 的结构，适配负荷预测领域知识（六种场景、XGBoost 模型、贝叶斯超参优化等）
    - _Requirements: 4.1_

  - [x] 6.2 创建 `data/skills/load-forecast/prepare.py`（只读）
    - 实现数据加载函数（从 CSV 或数据库加载负荷数据）
    - 实现数据预处理函数（时间戳补全、异常检测、数据填补）
    - 实现特征工程函数（调用 `add_more_features` 的简化版本）
    - 实现评估函数（计算 SMAPE、MAE、RMSE），SMAPE 计算方式与 `utils.py` 中的 `smape` 函数逻辑一致
    - _Requirements: 4.2, 4.4_

  - [x] 6.3 创建 `data/skills/load-forecast/train.py`（可编辑）
    - 提供基线训练脚本，使用 XGBoost 和贝叶斯超参优化
    - AI 可修改模型架构、超参数、特征选择和训练策略来优化预测效果
    - _Requirements: 4.3_

  - [ ]* 6.4 编写 SMAPE 一致性属性测试
    - **Property 3: SMAPE 计算一致性与数学性质** — 对任意有效的 y_true 和 y_pred 数组，验证 `prepare.py` 和 `utils.py` 的 SMAPE 实现产生相同结果，且满足非负性和 y_pred==y_true 时结果为 0
    - **Validates: Requirements 4.2, 4.4**

  - [x] 6.5 在 `packaged_skills.json` 中注册负荷预测 Skill 条目
    - 添加 skill_id、skill_name（"负荷预测 AutoResearch Skill"）、skill_version（"1.0.0"）、description、source_template_id、training_config、resource_config、status（"ready"）等字段
    - 格式与现有的光伏发电功率预测 Skill 条目一致
    - _Requirements: 3.1_

- [x] 7. 可观测性增强
  - [x] 7.1 完善任务状态管理和日志记录
    - 确保每次训练/预测/回测请求生成唯一 task_id（UUID 格式）
    - 维护任务执行状态（pending/running/success/failed），包含当前步骤、已完成步骤、总耗时和错误信息
    - 失败时在日志中记录完整错误堆栈，在任务状态中标记失败步骤和错误原因
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 7.2 编写任务 ID 唯一性属性测试
    - **Property 4: 任务 ID 唯一性** — 对任意数量的并发或顺序请求，验证所有 task_id 互不相同
    - **Validates: Requirements 6.2**

  - [ ]* 7.3 编写任务状态转换合法性属性测试
    - **Property 5: 任务状态转换合法性** — 验证状态转换遵循合法路径：pending → running → success 或 pending → running → failed，不允许非法回退
    - **Validates: Requirements 6.3**

- [x] 8. 向后兼容性验证
  - [x] 8.1 验证 `run.py` 独立运行能力
    - 确认 `python run.py --config configs/xxx.yaml` 命令在融合后仍能正常执行
    - 确认 REST API 端点通过 import 调用现有函数而非复制代码
    - 确认不修改 `db_data_fetch.py`、`data_process.py`、`features/engine.py`、`models_pkg/trainer.py`、`models_pkg/wrapper.py`、`common/constants.py`、`configs/schema.py` 等现有核心模块的接口签名
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 9. Checkpoint — 确保 Skill 包、可观测性和向后兼容性完成
  - 确保所有测试通过，ask the user if questions arise.

- [x] 10. Function 节点注册与可执行化
  - [x] 10.1 在 `functions.json` 中注册 6 个负荷预测 Function 节点
    - 添加 `load_forecast_data_fetch`（负荷数据获取，category: data_source，return_type: MATRIX）
    - 添加 `load_forecast_anomaly_detection`（负荷异常检测与数据补全，category: data_preprocessing，return_type: MATRIX）
    - 添加 `load_forecast_feature_engineering`（负荷预测特征工程，category: feature_engineering，return_type: MATRIX）
    - 添加 `load_forecast_model_train`（负荷预测模型训练，category: model_training，return_type: OBJECT）
    - 添加 `load_forecast_model_predict`（负荷预测模型推理，category: ts_forecast，return_type: MATRIX）
    - 添加 `load_forecast_evaluate`（负荷预测评估，category: evaluation_metrics，return_type: OBJECT）
    - 每个定义包含 id、name、category、description、parameters（含类型和必填标识）、return_type 和 inputs/outputs 端口定义
    - 确保上游节点的输出端口类型与下游节点对应输入端口类型兼容（MATRIX → MATRIX，OBJECT → OBJECT）
    - _Requirements: 7.1, 7.4, 7.5_

  - [ ]* 10.2 编写 Function 节点端口类型匹配属性测试
    - **Property 6: Function 节点端口类型匹配** — 对负荷预测流水线中相邻的两个 Function 节点，验证上游输出端口类型与下游输入端口类型兼容
    - **Validates: Requirements 7.5**

  - [x] 10.3 在 `ExecutionService._execute_function_node` 中实现 6 个 Function 的执行逻辑
    - 添加 `load_forecast_data_fetch` 分支：import 调用 `db_data_fetch.py` 中的 `offline_load_data`
    - 添加 `load_forecast_anomaly_detection` 分支：import 调用 `data_process.py` 中的 `get_completed_timestamp` → `chebyshev_detector` → `get_completed_df`
    - 添加 `load_forecast_feature_engineering` 分支：import 调用 `features/engine.py` 中的 `add_more_features`
    - 添加 `load_forecast_model_train` 分支：import 调用 `models_pkg/trainer.py` 中的 `model_prefer_trainer`
    - 添加 `load_forecast_model_predict` 分支：import 调用 `models_pkg/wrapper.py` 中的 `LoadForecastWrapper.predict`
    - 添加 `load_forecast_evaluate` 分支：import 调用 `evaluation/metrics.py` 中的评估函数
    - 处理方式与现有的 `matrix_add`、`matrix_multiply` 等一致
    - _Requirements: 7.2, 7.3, 7.6_

  - [ ]* 10.4 编写 ExecutionService 分发的单元测试
    - 测试 6 个 function_id 的正确分发
    - 测试参数提取和函数调用
    - _Requirements: 7.2, 7.6_

- [x] 11. 可视化编辑器验证
  - [x] 11.1 验证 Function 节点在可视化编辑器中的可用性
    - 确认 6 个新注册的 Function 节点出现在函数库中
    - 确认节点可拖拽到画布上
    - 确认上游节点的 MATRIX 输出端口能连接到下游节点的 MATRIX 输入端口
    - 构建 6 节点工作流，通过 ExecutionService 按拓扑排序正确执行
    - _Requirements: 7.4, 7.5, 7.6_

- [x] 12. Final Checkpoint — 确保所有功能完成
  - 确保所有测试通过，ask the user if questions arise.

## Notes

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号，确保需求可追溯
- Checkpoint 任务确保增量验证
- 属性测试使用 Hypothesis 库验证通用正确性属性
- 单元测试验证具体场景和边界条件
- 全程使用 Python 语言，与现有项目技术栈一致
- 不修改现有核心模块（`db_data_fetch.py`、`data_process.py`、`features/engine.py`、`models_pkg/trainer.py`、`models_pkg/wrapper.py`），仅在 API 层做适配
<!-- @AI_GENERATED: end -->
