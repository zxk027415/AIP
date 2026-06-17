<!-- @AI_GENERATED -->
# 需求文档：负荷预测项目融合到 AIP 算法平台（简化版）

## 简介

将现有的电力负荷预测项目融合到 AIP 工业AI算法平台上。

经过深入分析平台架构，我们采用**两阶段渐进式策略**：

1. **当前阶段（先跑通 + Function 节点化）**：通过 REST API 端点直接调用现有负荷预测代码（`run.py` 里的流程），同时注册 Agent Tool 让大模型能通过对话触发预测。此外，把负荷预测的 6 个步骤注册为 `functions.json` 中的可执行 Function 节点，让它们在可视化编辑器里可拖拽、可执行。不封装 BaseSkill 子类，不走 SkillOrchestrator。
2. **未来阶段（灵活编排）**：给更多通用 Function 补充执行代码，让 Agent 能自主从算法库里挑选模块组装工作流，实现 WorkflowDefinition 自动生成。

> **通俗理解**：想象你有一套手工操作的预测流程（取数据→清洗→提特征→训练→预测→评估），现在要把它搬到一个"自动化工厂"（AIP平台）里。当前阶段的策略是：**先把整条流水线搬进去（REST API），同时把每个步骤都登记到工厂的"零件目录"里（Function 节点），让用户能在可视化编辑器里看到、拖拽、执行这些步骤**。等跑通了、验证了，再考虑让 AI 自主挑选零件组装新的流水线。

## 概念澄清：四种概念的区别

在 AIP 平台中，有四种容易混淆的概念。理解它们的区别是正确集成的前提：

### Function（可视化编辑器里的"方块"）

- **是什么**：`functions.json` 里定义的约 780 个模块，是可视化编辑器里的"方块"
- **本质**：大部分只有 JSON 描述（名称、输入输出端口定义），没有真正的执行代码
- **用途**：在可视化工作流编辑器中拖拽组合，描述算法流程的"蓝图"
- **类比**：乐高积木的说明书上画的方块——告诉你有哪些零件、怎么拼，但方块本身不会动

### BaseSkill（Workflow Agent 的内部编排能力）

- **是什么**：`services/workflow_agent/skills/` 下的 Python 类，继承自 `BaseSkill` 抽象基类
- **本质**：Workflow Agent 内部的编排能力模块，用于场景匹配（`scenario-match`）、算法组合（`algorithm-compose`）、工作流生成（`workflow-generate`）等
- **用途**：帮助 Agent 理解用户需求、推荐算法方案、生成工作流定义
- **关键认知**：BaseSkill 是给 Workflow Agent 的内部编排用的，**不是**给负荷预测执行用的。我们不需要把负荷预测的每个步骤封装成 BaseSkill 子类

### Agent Tool（给大模型的工具描述）

- **是什么**：`agent_tools.py` 里的 `AGENT_TOOLS` 列表中定义的工具
- **本质**：OpenAI Function Calling 格式的工具描述，大模型通过 Function Calling 自动选择调用
- **用途**：让大模型在对话中能够触发具体操作（如"帮我跑一下负荷预测"）
- **执行方式**：`AgentToolExecutor` 类中实现具体的执行逻辑，内部调用 REST API

### Packaged Skill（AutoResearch 风格的实验室套件）

- **是什么**：`data/skills/` 下的文件夹，如 `pv-power-forecast/`
- **本质**：由 `program.md`（实验手册）+ `prepare.py`（只读数据准备）+ `train.py`（可编辑训练脚本）组成的实验套件
- **用途**：让 LLM Agent 自主尝试不同的模型和参数来优化预测效果
- **注册方式**：在 `packaged_skills.json` 中登记元数据

### 四者的关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                     AIP 平台架构中的四种概念                      │
│                                                                 │
│  ┌─────────────────┐     ┌─────────────────────────────────┐   │
│  │   Function       │     │   BaseSkill                     │   │
│  │   (780个方块)    │     │   (Workflow Agent 内部能力)      │   │
│  │                  │     │                                 │   │
│  │  可视化编辑器里   │     │  场景匹配、算法组合、            │   │
│  │  的拖拽方块      │     │  工作流生成等编排能力            │   │
│  │  大部分没有      │     │                                 │   │
│  │  执行代码        │     │  ≠ 负荷预测执行模块             │   │
│  └─────────────────┘     └─────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────┐     ┌─────────────────────────────────┐   │
│  │   Agent Tool     │     │   Packaged Skill                │   │
│  │   (LLM工具)     │     │   (实验室套件)                   │   │
│  │                  │     │                                 │   │
│  │  给大模型看的    │     │  program.md + prepare.py        │   │
│  │  工具描述        │     │  + train.py                     │   │
│  │  通过 Function   │     │                                 │   │
│  │  Calling 调用    │     │  让 AI 自主实验优化              │   │
│  └─────────────────┘     └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

重要：Agent Tool 和 BaseSkill 是两条独立的路径，不是上下游关系！
```

### 当前阶段的调用路径

```
Agent Tool（trigger_load_forecast_prediction）
    │
    │  不经过 BaseSkill / SkillOrchestrator
    │  直接调用
    ▼
REST API（/api/load-forecast/predict）
    │
    │  直接 import 并调用
    ▼
现有代码（run.py 的流程：数据获取 → 异常检测 → 特征工程 → 训练/推理）
```

## 两阶段演进策略

### 当前阶段：先跑通 + Function 节点化（本文档的实施范围）

| 做什么 | 不做什么 |
|--------|----------|
| REST API 端点包装现有代码 | ~~封装 BaseSkill 子类~~ |
| Agent Tool 让大模型能调度 | ~~走 SkillOrchestrator 编排~~ |
| AutoResearch Skill 包 | ~~定义 Pydantic 请求/响应模型~~ |
| 注册到平台（packaged_skills.json、路由） | ~~步骤间数据序列化/反序列化~~ |
| 保持 run.py 独立运行能力 | ~~WorkflowNode / WorkflowDefinition 生成~~ |
| 在 functions.json 中注册 6 个负荷预测 Function 节点 | ~~给其他通用 Function 补执行代码~~ |
| 在 ExecutionService 中实现执行代码 | |
| 可视化编辑器中验证拖拽和执行 | |

### 未来阶段：灵活编排（预留不实施）

| 做什么 | 目的 |
|--------|------|
| 给 functions.json 中其他通用 Function 补充执行代码 | 让更多方块不只是"蓝图"，能真正运行 |
| 让 Agent 能自主挑选 Function 组装工作流 | 实现智能编排 |
| WorkflowDefinition 自动生成 | 灵活定制预测流程 |

## 术语表

### 平台核心概念

- **REST API**（应用程序接口）
  - **技术定义**：基于 HTTP 协议的接口规范，外部系统通过发送 HTTP 请求来调用平台功能
  - **通俗理解**：类似于"服务窗口"。就像银行有不同的窗口办理不同业务，平台也有不同的 API 端点处理不同请求

- **Agent Tool**（大模型工具）
  - **技术定义**：OpenAI Function Calling 格式的工具定义（位于 `services/agent_tools.py` 的 `AGENT_TOOLS` 列表），大模型在对话中自动选择调用
  - **通俗理解**：给 AI 助手配的"遥控器按钮"。每个按钮对应一个操作（如"触发预测"、"查看场景"），AI 根据用户的对话内容自动按下合适的按钮

- **AgentToolExecutor**（工具执行器）
  - **技术定义**：`services/agent_tools.py` 中的工具执行器类，根据工具名称分发到对应的执行方法
  - **通俗理解**：遥控器的"信号接收器"。AI 按下按钮后，执行器负责把信号翻译成实际操作（比如调用 REST API）

- **Function**（可视化方块）
  - **技术定义**：`data/functions.json` 中定义的算法模块，包含名称、分类、输入输出端口等元数据
  - **通俗理解**：可视化编辑器里的"积木块"，大部分只有描述没有执行代码

- **BaseSkill**（基础技能类）
  - **技术定义**：Workflow Agent 的 Skill 抽象基类（位于 `services/workflow_agent/skills/base_skill.py`），用于平台内部的编排能力（场景匹配、算法组合等）
  - **通俗理解**：平台内部的"智能助手模块"，帮助 Agent 理解需求和推荐方案。**当前阶段负荷预测不需要用到它**

- **AutoResearch_Skill**（自主实验型 Skill 包）
  - **技术定义**：`data/skills/` 目录下的实验套件，由 `program.md` + `prepare.py` + `train.py` 组成
  - **通俗理解**：给 AI 助手准备的"实验室"。`program.md` 是实验手册，`prepare.py` 是固定的实验器材（只读），`train.py` 是可调整的实验方案（AI 可以反复修改）

- **packaged_skills_json**（Skill 注册表）
  - **技术定义**：`data/skills/packaged_skills.json`，记录所有已打包 Skill 的元数据
  - **通俗理解**：平台的"技能目录册"，登记所有可用技能的信息

### 负荷预测项目概念

- **ScenarioConfig**（场景配置）
  - **技术定义**：`common/constants.py` 中的数据类，定义 DI/D/WI/W/MI/M 六种预测场景的行为差异参数
  - **通俗理解**：六种"预测模式说明书"。DI=日内（几小时内）、D=日前（明天）、WI=周内、W=周前、MI=月内、M=月前

- **CustomerConfig**（客户配置）
  - **技术定义**：`configs/schema.py` 中的数据类，从 YAML 文件加载完整配置
  - **通俗理解**：不同客户的"定制单"，包含数据源、预测需求、模型参数等个性化设置


## 概念速查

### 整体架构：当前阶段的简化方案

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AIP 工业AI算法平台                            │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐   │
│  │   前端界面    │    │              后端服务 (FastAPI)            │   │
│  │              │    │                                          │   │
│  │  ┌────────┐  │    │  ┌─────────────────────────────────┐    │   │
│  │  │对话界面 │  │───▶│  │  Agent Tool（大模型工具）        │    │   │
│  │  │(AI助手) │  │    │  │  trigger_load_forecast_train    │    │   │
│  │  └────────┘  │◀───│  │  trigger_load_forecast_predict  │    │   │
│  │              │    │  │  trigger_load_forecast_backtest  │    │   │
│  │  ┌────────┐  │    │  │  get_forecast_scenarios         │    │   │
│  │  │API调用  │  │    │  │  get_forecast_status            │    │   │
│  │  │(程序化) │  │    │  └──────────┬──────────────────────┘    │   │
│  │  └────────┘  │    │             │ 内部调用                   │   │
│  └──────────────┘    │             ▼                            │   │
│                      │  ┌─────────────────────────────────┐    │   │
│                      │  │  REST API 端点                   │    │   │
│                      │  │  POST /api/load-forecast/train   │    │   │
│                      │  │  POST /api/load-forecast/predict │    │   │
│                      │  │  POST /api/load-forecast/backtest│    │   │
│                      │  │  GET  /api/load-forecast/scenarios│   │   │
│                      │  └──────────┬──────────────────────┘    │   │
│                      │             │ 直接 import 调用           │   │
│                      │             ▼                            │   │
│                      │  ┌─────────────────────────────────┐    │   │
│                      │  │  现有负荷预测代码（原封不动）     │    │   │
│                      │  │                                  │    │   │
│                      │  │  db_data_fetch.py → 数据获取     │    │   │
│                      │  │  data_process.py  → 异常检测     │    │   │
│                      │  │  features/engine.py → 特征工程   │    │   │
│                      │  │  models_pkg/trainer.py → 训练    │    │   │
│                      │  │  models_pkg/wrapper.py → 推理    │    │   │
│                      │  └─────────────────────────────────┘    │   │
│                      │                                          │   │
│                      │  ┌─────────────────────────────────┐    │   │
│                      │  │  AutoResearch 实验室              │    │   │
│                      │  │  data/skills/load-forecast/      │    │   │
│                      │  │  ┌──────────┐ ┌────────┐        │    │   │
│                      │  │  │program.md│ │prepare │        │    │   │
│                      │  │  │(实验手册)│ │.py(只读)│        │    │   │
│                      │  │  └──────────┘ └────────┘        │    │   │
│                      │  │  ┌──────────┐                    │    │   │
│                      │  │  │train.py  │                    │    │   │
│                      │  │  │(可编辑)  │                    │    │   │
│                      │  │  └──────────┘                    │    │   │
│                      │  └─────────────────────────────────┘    │   │
│                      └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘

注意：没有 SkillOrchestrator、没有 BaseSkill 子类、没有步骤间数据序列化。
REST API 内部直接 import 现有代码的函数，数据在 Python 进程内以原生对象传递。
```

### 数据流：一次预测请求的完整旅程（简化版）

```
用户/前端/AI助手
    │
    │  发送 HTTP 请求（包含客户配置信息）
    ▼
┌─────────────────────┐
│ REST API 端点         │  接收请求，解析参数
│ POST /api/load-      │
│ forecast/predict     │
└────────┬────────────┘
         │  直接 import 调用现有函数（Python 进程内）
         ▼
┌─────────────────────────────────────────────────────┐
│              现有代码流程（原封不动）                   │
│                                                     │
│  ① offline_load_data()     → 从数据库/CSV获取数据   │
│       ↓ (Python DataFrame，内存中直接传递)           │
│  ② get_completed_timestamp() → 补全时间戳           │
│  ③ chebyshev_detector()      → 异常检测             │
│  ④ get_completed_df()        → 数据填补             │
│       ↓                                             │
│  ⑤ add_more_features()      → 特征工程             │
│       ↓                                             │
│  ⑥ model_prefer_trainer()   → 模型训练（训练时）    │
│     或 LoadForecastWrapper.predict() → 推理（预测时）│
│       ↓                                             │
│  ⑦ predict_format_transform() → 结果后处理          │
└────────┬────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  返回 JSON 结果  │  → 给用户/前端/AI助手
└─────────────────┘

关键区别：步骤之间的数据（DataFrame、模型对象）在 Python 进程内以原生对象
直接传递，不需要序列化/反序列化，不需要 Pydantic 模型包装。
```

## 需求

### 需求 1：REST API 端点

> **为什么需要这个？** 这是当前阶段的核心。通过 REST API 把现有的负荷预测代码暴露为 HTTP 接口，让前端、AI 助手、外部系统都能调用。API 内部直接 import 现有代码的函数，不需要额外的封装层。
>
> **通俗理解**：给现有的预测流程装一个"服务窗口"。窗口接收请求，内部直接调用已有的代码完成工作，然后把结果返回。

**用户故事：** 作为平台开发者，我希望通过 REST API 端点暴露负荷预测的训练、预测和回测功能，以便前端界面和 AI 助手能够通过 HTTP 请求触发预测流程。

#### 验收标准

1. THE 系统 SHALL 提供 `POST /api/load-forecast/train` 端点，接收包含客户配置信息的 JSON 请求体（task_type、数据源配置、预测参数等），内部直接调用 `offline_load_data()`、`get_completed_timestamp()`、`chebyshev_detector()`、`get_completed_df()`、`add_more_features()`、`model_prefer_trainer()` 等现有函数完成训练流程，返回包含训练状态、模型标识和训练耗时的 JSON 响应
2. THE 系统 SHALL 提供 `POST /api/load-forecast/predict` 端点，接收包含客户配置信息和模型标识的 JSON 请求体，内部直接调用现有的数据获取、异常检测、特征工程和 `LoadForecastWrapper.predict()` 函数完成预测流程，返回包含预测时间戳列表和预测值列表的 JSON 响应
3. THE 系统 SHALL 提供 `POST /api/load-forecast/backtest` 端点，接收包含客户配置信息和回测日期范围的 JSON 请求体，内部按日期循环调用训练和预测流程（复用 `run.py` 中 `run_backtest()` 的逻辑），返回包含每日预测结果和评估指标的 JSON 响应
4. THE 系统 SHALL 提供 `GET /api/load-forecast/scenarios` 端点，返回六种预测场景（DI/D/WI/W/MI/M）的配置信息，包括场景名称、中文描述、适用范围和关键参数差异
5. WHEN REST API 端点接收到请求时，THE 系统 SHALL 直接 import 并调用 `db_data_fetch.py`、`data_process.py`、`features/engine.py`、`models_pkg/trainer.py`、`models_pkg/wrapper.py` 中的函数，数据在 Python 进程内以原生对象（DataFrame、dict、模型对象）直接传递，不经过序列化/反序列化
6. IF REST API 端点执行过程中发生异常，THEN THE 系统 SHALL 返回包含错误类型、错误信息和失败步骤标识的 JSON 错误响应，HTTP 状态码为 500
7. THE REST API 端点 SHALL 在 `AIP-service/backend/api/` 目录下创建 `load_forecast.py` 路由模块，使用 FastAPI Router，路由前缀为 `/api/load-forecast`

### 需求 2：Agent Tool 集成

> **为什么需要这个？** Agent Tool 是让大模型能通过对话触发预测的关键。用户在 AI 助手界面说"帮我跑一下明天的负荷预测"，大模型通过 Function Calling 自动选择合适的工具，工具内部调用 REST API 完成操作。
>
> **通俗理解**：给 AI 助手配一组"遥控器按钮"。用户说话，AI 自动按下合适的按钮，按钮背后连接的是 REST API。

**用户故事：** 作为平台用户，我希望能通过 AI 助手的对话界面触发负荷预测的训练、预测和回测操作，以便用自然语言完成预测任务而不需要手动调用 API。

#### 验收标准

1. THE 系统 SHALL 在 `agent_tools.py` 的 `AGENT_TOOLS` 列表中添加 `trigger_load_forecast_train` 工具定义，描述为"触发负荷预测模型训练"，参数包含 task_type（预测场景类型）、config_override（可选的配置覆盖项）
2. THE 系统 SHALL 在 `agent_tools.py` 的 `AGENT_TOOLS` 列表中添加 `trigger_load_forecast_predict` 工具定义，描述为"触发负荷预测"，参数包含 task_type、parent_id、child_id、forecast_horizon（预测步长）
3. THE 系统 SHALL 在 `agent_tools.py` 的 `AGENT_TOOLS` 列表中添加 `trigger_load_forecast_backtest` 工具定义，描述为"触发负荷预测回测评估"，参数包含 task_type、start_date、end_date
4. THE 系统 SHALL 在 `agent_tools.py` 的 `AGENT_TOOLS` 列表中添加 `get_forecast_scenarios` 工具定义，描述为"获取负荷预测支持的场景列表"，无必填参数
5. THE 系统 SHALL 在 `agent_tools.py` 的 `AGENT_TOOLS` 列表中添加 `get_forecast_status` 工具定义，描述为"查询负荷预测任务的执行状态"，参数包含 task_id
6. THE AgentToolExecutor 类 SHALL 为上述 5 个工具实现对应的执行方法，每个方法内部通过 HTTP 请求调用对应的 REST API 端点（需求 1 中定义的端点），并将 API 响应转换为适合大模型理解的结构化结果
7. THE 系统 SHALL 更新 Algorithm Agent 的 System Prompt（系统提示词），添加负荷预测相关的领域知识，包括六种场景的适用范围、典型对话示例和推荐的交互流程
8. THE 系统 SHALL 更新 `data/forecast_scenarios.json`，添加负荷预测场景的详细知识库，包括每种场景的业务描述、数据要求、精度目标和推荐配置
9. WHEN 大模型不可用时（LLM 服务连接失败或超时），THE AgentToolExecutor SHALL 降级为基于关键词匹配的规则引擎，识别用户意图中的场景类型和操作类型，直接调用对应的 REST API 端点
10. THE 系统 SHALL 设计标准的对话流程：用户描述需求 → AI 确认场景类型 → AI 确认关键参数 → AI 触发执行 → AI 返回结果摘要，每个步骤提供 suggested_actions（建议操作按钮）引导用户

### 需求 3：注册到 AIP 平台

> **为什么需要这个？** 平台需要知道负荷预测这个能力的存在。通过注册，平台的技能目录、路由系统都能发现和管理负荷预测功能。
>
> **通俗理解**：给新搬进来的"预测工坊"办理"营业执照"，让工厂的管理系统知道有这个工坊、能做什么、怎么联系。

**用户故事：** 作为平台管理员，我希望负荷预测功能在 AIP 平台中正式注册，以便平台能够发现、管理和展示该功能。

#### 验收标准

1. THE 系统 SHALL 在 `data/skills/packaged_skills.json` 中添加负荷预测 Skill 的注册条目，包含 skill_id、skill_name（"负荷预测 Skill"）、skill_version（"1.0.0"）、description（功能描述）、source_template_id、training_config（训练配置）、resource_config（资源配置）、status（"ready"）等字段，格式与现有的光伏发电功率预测 Skill 条目一致
2. THE 系统 SHALL 在 `AIP-service/backend/main.py` 中导入并注册负荷预测的 FastAPI Router（`from api.load_forecast import router as load_forecast_router`），通过 `app.include_router(load_forecast_router)` 将路由挂载到应用
3. WHEN 平台启动时，THE 系统 SHALL 能够通过 `GET /api/load-forecast/scenarios` 端点验证负荷预测功能已正确注册和可用

### 需求 4：AutoResearch Skill 包

> **为什么需要这个？** AutoResearch Skill 包让 AI 助手能在"实验室"里自主尝试不同的模型架构和超参数来优化预测效果。这是 AIP 平台的特色功能，参考现有的 `pv-power-forecast` Skill 包的模式。
>
> **通俗理解**：给 AI 助手准备一个"实验室"，里面有固定的实验器材（数据加载和评估函数）和一份可以反复修改的实验方案（训练脚本）。AI 可以不断尝试新方法来提升预测精度。

**用户故事：** 作为数据科学家，我希望有一个 AutoResearch 风格的 Skill 包，让 AI 助手能够自主探索和优化负荷预测模型。

#### 验收标准

1. THE 系统 SHALL 在 `data/skills/load-forecast/` 目录下创建 `program.md` 文件，定义实验目标（最小化 SMAPE）、实验规则（可修改 train.py、不可修改 prepare.py）、输出格式、结果记录格式和实验循环流程，参考 `pv-power-forecast/program.md` 的结构但适配负荷预测的领域知识（六种场景、XGBoost 模型、贝叶斯超参优化等）
2. THE 系统 SHALL 在 `data/skills/load-forecast/` 目录下创建 `prepare.py` 文件（只读），实现数据加载函数（从 CSV 或数据库加载负荷数据）、数据预处理函数（时间戳补全、异常检测、数据填补）、特征工程函数（调用 `add_more_features` 的简化版本）和评估函数（计算 SMAPE、MAE、RMSE），该文件 AI 不可修改
3. THE 系统 SHALL 在 `data/skills/load-forecast/` 目录下创建 `train.py` 文件（可编辑），提供基线训练脚本（使用 XGBoost 和贝叶斯超参优化），AI 可以修改模型架构、超参数、特征选择和训练策略来优化预测效果
4. THE `prepare.py` 中的评估函数 SHALL 使用与现有代码一致的 SMAPE 计算方式（`utils.py` 中的 `smape` 函数逻辑），确保实验结果与生产环境的评估标准一致

### 需求 5：向后兼容性

> **为什么需要这个？** 现有的 `run.py` 回测脚本是经过验证的生产代码，必须确保融合到平台后它仍然能独立运行。这是安全网——如果平台集成出了问题，还能回退到原来的方式。
>
> **通俗理解**：搬进新工厂后，原来的手工作坊也要保留。万一工厂的流水线出了问题，还能回到手工作坊继续干活。

**用户故事：** 作为开发者，我希望融合到 AIP 平台后，现有的 `run.py` 回测脚本仍然能独立运行，以便保留原有的工作方式作为备选。

#### 验收标准

1. THE 现有的 `python run.py --config configs/xxx.yaml` 命令 SHALL 在融合到平台后仍然能正常执行，产生与融合前完全一致的预测结果
2. THE REST API 端点 SHALL 通过 import 调用现有函数而非复制代码，确保 API 路径和 run.py 路径使用同一套核心逻辑
3. THE 系统 SHALL 不修改 `db_data_fetch.py`、`data_process.py`、`features/engine.py`、`models_pkg/trainer.py`、`models_pkg/wrapper.py`、`common/constants.py`、`configs/schema.py` 等现有核心模块的接口签名，仅在 API 层做适配

### 需求 6：可观测性

> **为什么需要这个？** 负荷预测流程可能运行几分钟到几十分钟（特别是训练和回测），需要让用户和运维人员能看到执行进度、排查问题。
>
> **通俗理解**：给预测流程装上"仪表盘"和"行车记录仪"，随时能看到跑到哪一步了、有没有出问题。

**用户故事：** 作为平台运维人员，我希望负荷预测的执行过程有完善的日志记录和状态跟踪，以便监控运行状态和排查问题。

#### 验收标准

1. THE REST API 端点 SHALL 在每个关键步骤（数据获取、异常检测、特征工程、模型训练、模型推理、结果后处理）开始和结束时记录日志，包含步骤名称、耗时和数据量信息，使用 `loguru.logger` 与现有代码的日志风格一致
2. THE 系统 SHALL 为每次训练/预测/回测请求生成唯一的 task_id，REST API 响应中包含该 task_id，后续可通过 `GET /api/load-forecast/status/{task_id}` 查询执行状态
3. THE 系统 SHALL 维护任务执行状态（pending/running/success/failed），包含当前步骤、已完成步骤、总耗时和错误信息（如有），状态信息存储在内存中（当前阶段不需要持久化）
4. IF 执行过程中某个步骤失败，THEN THE 系统 SHALL 在日志中记录完整的错误堆栈，并在任务状态中标记失败步骤和错误原因

### 需求 7：负荷预测 Function 节点注册与可执行化

> **为什么需要这个？** 当前阶段我们已经通过 REST API 把负荷预测"整条流水线"搬进了平台，但这些步骤在可视化编辑器里还看不到、拖不动。把 6 个步骤注册为 `functions.json` 中的 Function 节点，并在 `ExecutionService` 中补充真正的执行代码，用户就能在可视化编辑器里像拼积木一样拖拽这些步骤，自由组合预测流程。
>
> **通俗理解**：之前我们把整条流水线搬进了工厂（REST API），但流水线上的每个"工位"还没有在工厂的"零件目录"里登记。现在要给每个工位办理登记，让它们出现在可视化编辑器的零件库里，用户可以拖出来拼装。

**用户故事：** 作为平台开发者，我希望把负荷预测的 6 个步骤注册为 `functions.json` 中的可执行 Function 节点，并在 `ExecutionService` 中实现执行代码，以便这些步骤能在可视化编辑器中拖拽使用、通过端口连线、按拓扑排序执行。

#### 6 个 Function 节点定义

##### ① load_forecast_data_fetch（负荷数据获取）

| 属性 | 值 |
|------|-----|
| id | `load_forecast_data_fetch` |
| name | 负荷数据获取 |
| category | `data_source` |
| description | 从数据库获取历史负荷数据，支持多数据源切换（offline/beta/extract），自动提取历史极值信息 |
| return_type | `MATRIX` |

**参数：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| task_type | STRING | ✅ | 预测场景类型 DI/D/WI/W/MI/M |
| table_name | STRING | ✅ | 数据表名 |
| parent_field | STRING | ✅ | 父级字段名 |
| child_field | STRING | ✅ | 子级字段名 |
| time_field | STRING | ✅ | 时间字段名 |
| load_field | STRING | ✅ | 负荷字段名 |
| parent_id | STRING | ✅ | 父级ID |
| child_id | STRING | ✅ | 子级ID |
| time_granularity | NUMBER | ❌ | 时间粒度（分钟），默认15 |
| is_training | STRING | ❌ | 是否训练模式，默认"true" |
| data_source | STRING | ❌ | 数据源类型 offline/beta/extract，默认"offline" |

**执行代码：** 调用 `db_data_fetch.py` 中的 `offline_load_data` / `beta_load_data` / `extract_load_data`

##### ② load_forecast_anomaly_detection（负荷异常检测与数据补全）

| 属性 | 值 |
|------|-----|
| id | `load_forecast_anomaly_detection` |
| name | 负荷异常检测与数据补全 |
| category | `data_preprocessing` |
| description | 对负荷数据执行时间戳补全、Chebyshev不等式异常检测和数据填补的组合流程 |
| return_type | `MATRIX` |

**参数：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| load_df | MATRIX | ✅ | 原始负荷数据（DataFrame） |
| original_time_freq | NUMBER | ✅ | 原始时间频率（分钟） |
| daily_horizon | NUMBER | ✅ | 日预测步长 |
| is_training | STRING | ❌ | 是否训练模式，默认"true" |
| time_field | STRING | ❌ | 时间字段名，默认"time" |
| load_field | STRING | ❌ | 负荷字段名，默认"load" |

**执行代码：** 调用 `data_process.py` 中的 `get_completed_timestamp` → `chebyshev_detector` → `get_completed_df`

##### ③ load_forecast_feature_engineering（负荷预测特征工程）

| 属性 | 值 |
|------|-----|
| id | `load_forecast_feature_engineering` |
| name | 负荷预测特征工程 |
| category | `feature_engineering` |
| description | 根据预测场景生成负荷预测所需的特征，包括时间特征、Lag特征、滚动统计、日统计、气象特征和Shift对齐 |
| return_type | `MATRIX` |

**参数：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| completed_df | MATRIX | ✅ | 清洗后的负荷数据 |
| scenario_type | STRING | ✅ | 预测场景 DI/D/WI/W/MI/M |
| task_id | STRING | ✅ | 任务ID |
| parent_id | STRING | ✅ | 父级ID |
| child_id | STRING | ✅ | 子级ID |
| original_time_freq | NUMBER | ✅ | 原始时间频率 |
| daily_horizon | NUMBER | ✅ | 日预测步长 |
| forecast_horizon | NUMBER | ✅ | 预测步长 |
| forecast_start_time | STRING | ❌ | 预测起始时间 |
| is_training | STRING | ❌ | 是否训练模式，默认"true" |
| separate_modeling | STRING | ❌ | 是否分开建模，默认"true" |

**执行代码：** 调用 `features/engine.py` 中的 `add_more_features`

##### ④ load_forecast_model_train（负荷预测模型训练）

| 属性 | 值 |
|------|-----|
| id | `load_forecast_model_train` |
| name | 负荷预测模型训练 |
| category | `model_training` |
| description | 使用XGBoost和贝叶斯超参优化训练负荷预测模型，支持工作日/节假日分开建模 |
| return_type | `OBJECT` |

**参数：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| feat_df | MATRIX | ✅ | 特征数据 |
| daily_horizon | NUMBER | ✅ | 日预测步长 |
| forecast_horizon | NUMBER | ✅ | 预测步长 |
| scenario_type | STRING | ✅ | 预测场景 |
| separate_modeling | STRING | ❌ | 是否分开建模，默认"true" |
| n_trials | NUMBER | ❌ | 贝叶斯优化试验次数，默认50 |

**执行代码：** 调用 `models_pkg/trainer.py` 中的 `model_prefer_trainer`

##### ⑤ load_forecast_model_predict（负荷预测模型推理）

| 属性 | 值 |
|------|-----|
| id | `load_forecast_model_predict` |
| name | 负荷预测模型推理 |
| category | `ts_forecast` |
| description | 使用已训练的模型执行负荷预测，包含预测后处理（rounding、极值裁剪、延迟补偿） |
| return_type | `MATRIX` |

**参数：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| model_dict | OBJECT | ✅ | 训练好的模型字典 |
| feature_list | ARRAY | ✅ | 特征列表 |
| feat_df | MATRIX | ✅ | 预测用特征数据 |
| his_min_max | MATRIX | ❌ | 历史极值信息 |
| rounding_unit | NUMBER | ❌ | 四舍五入单位 |

**执行代码：** 调用 `models_pkg/wrapper.py` 中的 `LoadForecastWrapper.predict`

##### ⑥ load_forecast_evaluate（负荷预测评估）

| 属性 | 值 |
|------|-----|
| id | `load_forecast_evaluate` |
| name | 负荷预测评估 |
| category | `evaluation_metrics` |
| description | 计算负荷预测的评估指标（SMAPE、MAE、RMSE），支持按场景分段评估 |
| return_type | `OBJECT` |

**参数：**

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| y_true | ARRAY | ✅ | 真实值 |
| y_pred | ARRAY | ✅ | 预测值 |
| scenario_type | STRING | ❌ | 预测场景，用于分段评估 |
| time_granularity | NUMBER | ❌ | 时间粒度（分钟），默认15 |

**执行代码：** 调用 `evaluation/metrics.py` 中的评估函数

#### 验收标准

1. THE 系统 SHALL 在 `data/functions.json` 中添加上述 6 个 Function 的 JSON 定义，每个定义包含 id、name、category、description、parameters（含类型和必填标识）、return_type 和 inputs/outputs 端口定义
2. THE 系统 SHALL 在 `ExecutionService._execute_function_node` 方法中添加对 `load_forecast_data_fetch`、`load_forecast_anomaly_detection`、`load_forecast_feature_engineering`、`load_forecast_model_train`、`load_forecast_model_predict`、`load_forecast_evaluate` 这 6 个 function_id 的执行逻辑分发，处理方式与现有的 `matrix_add`、`matrix_multiply` 等一致
3. THE 每个 Function 的执行代码 SHALL 通过 import 调用现有的负荷预测模块函数（`db_data_fetch.py`、`data_process.py`、`features/engine.py`、`models_pkg/trainer.py`、`models_pkg/wrapper.py`、`evaluation/metrics.py`），不复制代码
4. WHEN 用户在可视化编辑器中打开函数库时，THE 系统 SHALL 显示这 6 个新注册的负荷预测 Function 节点，用户能将它们拖拽到画布上
5. THE 系统 SHALL 为每个 Function 定义正确的输入/输出端口类型，确保上游节点的 MATRIX 输出端口能连接到下游节点的 MATRIX 输入端口（如 `load_forecast_data_fetch` 的 MATRIX 输出连到 `load_forecast_anomaly_detection` 的 `load_df` 输入）
6. WHEN 用户执行包含这些节点的工作流时，THE ExecutionService SHALL 按拓扑排序正确执行这些节点，上游节点的输出自动传递为下游节点的输入

## 未来阶段需求（预留，不在当前实施）

以下需求记录未来阶段的演进方向，当前阶段不实施。

### 未来需求 A：补全更多通用 Function 的执行代码

**用户故事：** 作为平台开发者，我希望给 `functions.json` 中其他 Function（非负荷预测的通用模块）也补上真正的执行代码，以便更多的可视化方块能真正运行而不只是"蓝图"。

**预期范围：**
- 给 `functions.json` 中现有的约 780 个 Function 中尚无执行代码的模块逐步补充实现
- 让 Agent 能自主从算法库里挑选 Function 组装工作流
- 实现 WorkflowDefinition 自动生成

### 未来需求 B：可视化工作流集成

**用户故事：** 作为平台用户，我希望在可视化工作流编辑器中看到负荷预测的完整流程图，并能拖拽调整步骤顺序和参数。

**预期范围：**
- 为每个步骤生成 WorkflowNode（流程图方块）
- 生成 WorkflowEdge（连线）连接相邻步骤
- 生成完整的 WorkflowDefinition（流程图定义）
- 支持在编辑器中替换节点（如用平台通用模块替换某个步骤）

## 路线图

```
Phase 1（当前）：先跑通 + Function 节点化
├── 1.1 创建 REST API 端点（api/load_forecast.py）
├── 1.2 注册路由到 main.py
├── 1.3 添加 Agent Tool 定义和执行方法
├── 1.4 更新 System Prompt 和 forecast_scenarios.json
├── 1.5 创建 AutoResearch Skill 包（data/skills/load-forecast/）
├── 1.6 注册到 packaged_skills.json
├── 1.7 添加可观测性（日志、状态跟踪）
├── 1.8 验证向后兼容性（run.py 仍能独立运行）
├── 1.9 在 functions.json 中注册 6 个负荷预测 Function 节点
├── 1.10 在 ExecutionService 中实现执行代码
└── 1.11 可视化编辑器中验证拖拽和执行

Phase 2（未来）：灵活编排
├── 2.1 让 Agent 能自主挑选 Function 组装工作流
├── 2.2 补全更多通用 Function 的执行代码
└── 2.3 WorkflowDefinition 自动生成
```
<!-- @AI_GENERATED: end -->
