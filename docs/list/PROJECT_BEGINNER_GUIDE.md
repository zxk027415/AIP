<!-- @AI_GENERATED -->
# 工业AI算法平台 — 从零开始的完整指南

> 本文档面向第一次接触本项目的开发者，从"这个项目是干什么的"讲起，逐步深入到每个模块的细节。

---

## 一、这个项目到底是什么？

### 一句话概括

这是一个 **工业AI算法平台**，让工程师可以在浏览器里 **选算法 → 拖拽编排 → 训练模型 → 部署上线 → 监控运维**，全流程不用写代码。

### 用大白话解释

想象你是一个工厂的工程师，老板说："我们的光伏发电站需要一个AI来预测明天的发电量。"

传统做法：你得找数据科学家写 Python 脚本，调 LSTM 模型，调参，部署成 API……

用这个平台：
1. 打开浏览器，进入"行业场景" → 选"光伏发电预测"
2. 平台推荐一套算法方案（数据清洗 → 特征提取 → LSTM 模型 → 评估指标）
3. 你在可视化编辑器里拖拽这些算法模块，连线组成工作流
4. 点"执行"，平台自动跑完整个流程
5. 看结果，满意就一键部署成在线服务

**这就是这个平台做的事情。**

---

## 二、技术栈总览（你需要知道的技术）

### 前端（用户看到的界面）

| 技术 | 作用 | 类比 |
|------|------|------|
 React 18 | UI 框架 | 就像盖房子的框架结构 |
| TypeScript | 带类型的 JavaScript | 让代码更安全，少犯错 |
| Ant Design 5 | UI 组件库 | 现成的按钮、表格、弹窗等 |
| React Flow | 流程图编辑器 | 实现拖拽连线的核心库 |
| ECharts | 图表库 | 画折线图、柱状图等 |
| Zustand | 状态管理 | 各页面之间共享数据 |
| Vite | 构建工具 | 把代码打包成浏览器能运行的文件 |

### 后端（服务器逻辑）

| 技术 | 作用 | 类比 |
|------|------|------|
| Python 3.10 | 编程语言 | 后端的"母语" |
| FastAPI | Web 框架 | 处理 HTTP 请求，类似 Flask 但更快 |
| SQLAlchemy | ORM | 用 Python 代码操作数据库 |
| SQLite | 数据库 | 轻量级数据库，数据存在一个文件里 |
| NumPy / SciPy | 科学计算 | 矩阵运算、数学函数 |
| NetworkX | 图算法 | 工作流的拓扑排序、环检测 |

### 前后端如何通信？

```
浏览器 (React)  ──HTTP请求──>  Vite代理  ──转发──>  FastAPI (Python)
   :5173                        /api/*              :8000
```

前端所有 `/api/*` 的请求，Vite 开发服务器会自动代理到后端的 8000 端口，所以不存在跨域问题。

---

## 三、项目目录结构详解

```
AIP-service/
├── frontend/                # 前端应用（React + TypeScript）
│   ├── src/
│   │   ├── pages/           # 页面组件（每个页面一个文件）
│   │   ├── components/      # 可复用组件
│   │   ├── services/        # API 调用封装
│   │   ├── stores/          # Zustand 状态管理
│   │   ├── types/           # TypeScript 类型定义
│   │   ├── hooks/           # 自定义 React Hooks
│   │   ├── utils/           # 工具函数
│   │   ├── data/            # 前端静态数据
│   │   ├── App.tsx          # 路由配置（所有页面的入口）
│   │   └── main.tsx         # 应用启动入口
│   ├── package.json         # 前端依赖配置
│   └── vite.config.ts       # Vite 构建配置 + API 代理
│
├── backend/                 # 后端服务（Python FastAPI）
│   ├── api/                 # API 路由层（接收请求，返回响应）
│   ├── services/            # 业务逻辑层（核心处理逻辑）
│   ├── models/              # 数据模型层（定义数据结构）
│   ├── nodes/               # 工作流节点执行器
│   ├── utils/               # 工具函数
│   ├── data/                # 数据存储（JSON 文件 + SQLite）
│   │   ├── functions.json   # 780个基础算法模块定义
│   │   ├── industry_scenarios.json    # 行业场景数据
│   │   ├── industry_templates.json    # 行业算法方案
│   │   ├── workflows_enhanced/        # 用户保存的工作流
│   │   ├── backtest/        # 回测任务数据
│   │   ├── deployment/      # 部署任务数据
│   │   ├── skills/          # 算法技能包
│   │   └── users.db         # SQLite 数据库文件
│   ├── main.py              # 后端启动入口
│   ├── database.py          # 数据库配置
│   └── requirements.txt     # Python 依赖
│
├── scripts/                 # 启动脚本
│   ├── start-all.bat        # 一键启动前后端
│   ├── start-backend.bat    # 单独启动后端
│   └── start-frontend.bat   # 单独启动前端
│
└── docs/                    # 项目文档
```

### 后端三层架构

后端采用经典的分层架构，请求从上到下流转：

```
HTTP 请求
    ↓
┌─────────────────────────────┐
│  api/ (路由层)               │  ← 接收请求，参数校验，调用 service
│  例: api/functions.py        │
└─────────────┬───────────────┘
              ↓
┌─────────────────────────────┐
│  services/ (业务逻辑层)      │  ← 核心处理逻辑，不关心 HTTP
│  例: function_library_service│
└─────────────┬───────────────┘
              ↓
┌─────────────────────────────┐
│  models/ (数据模型层)        │  ← 定义数据结构（Pydantic / SQLAlchemy）
│  data/ (持久化层)            │  ← JSON 文件 / SQLite 数据库
└─────────────────────────────┘
```

---

## 四、核心功能模块详解

### 4.1 用户认证系统

**你看到的**：登录页面、注册页面

**它做了什么**：
- 用户注册时，密码用 bcrypt 加密后存入 SQLite 数据库
- 登录成功后，后端生成一个 JWT Token 返回给前端
- 前端把 Token 存在 localStorage 里
- 之后每次访问受保护页面，前端检查 localStorage 里有没有登录标记

**涉及的文件**：
- 前端：`LoginPage.tsx` → `RegisterPage.tsx` → `ProtectedRoute.tsx`
- 后端：`api/auth.py` → `services/auth_service.py` → `database.py`（User 模型）

**数据流**：
```
用户输入账号密码 → POST /api/auth/login → 后端验证 → 返回 JWT Token
                                                    → 前端存 localStorage
                                                    → 跳转到首页
```

---

### 4.2 首页仪表盘

**你看到的**：欢迎卡片 + 核心数据统计 + 行业场景快速入口 + 快速导航

**它做了什么**：
- 展示平台的核心数据：8大行业、13个场景、449个算法方案、780个基础模块
- 提供快速入口，让用户一键跳转到各功能模块

**涉及的文件**：
- 前端：`pages/HomePage.tsx`
- 后端：`api/industry.py`（`/api/industry/stats` 接口提供统计数据）

---

### 4.3 行业场景模块

**你看到的**：行业场景卡片列表，点进去看场景详情和推荐算法方案

**它做了什么**：
这是平台的"入口"——从业务场景出发，而不是从技术出发。

平台覆盖 8 大行业方向：
1. 新能源（光伏发电、风力发电）
2. 传统能源（火力发电）
3. 源网荷储（储能管理、电网调度）
4. 工业制造（钢铁、光伏制造）
5. 港口运输
6. 楼宇园区
7. 碳管理
8. 公用事业（水务环保）

每个行业下有具体场景，每个场景关联了推荐的算法方案。

**涉及的文件**：
- 前端：`pages/IndustryOverviewPage.tsx`（场景列表）、`pages/IndustryScenarioPage.tsx`（场景详情）
- 后端：`api/industry.py`
- 数据：`data/industry_scenarios.json`、`data/industry_templates.json`

---

### 4.4 基础算法库（函数库）

**你看到的**：按分类浏览的算法列表，可以搜索、查看详情、在线测试

**它做了什么**：
这是平台的"零件仓库"。所有算法都被定义为标准化的"函数"，每个函数有：
- 名称和描述
- 输入参数（类型、是否必填、默认值）
- 输出参数（类型）
- 所属分类

780 个基础算法模块分为 19 大类：

| 分类 | 举例 |
|------|------|
| 数据源 | 时序数据加载、CSV读取 |
| 数据清洗 | 缺失值处理、异常检测 |
| 特征工程 | 统计特征、频域特征、滞后特征 |
| 算法模型 | LSTM、ARIMA、XGBoost、随机森林 |
| 评估指标 | MAE、RMSE、R²、F1 |
| ... | ... |

**涉及的文件**：
- 前端：`pages/FunctionLibraryPage.tsx`、`components/FunctionLibrary.tsx`、`components/FunctionExecutor.tsx`
- 后端：`api/functions.py` → `services/function_library_service.py`
- 数据：`data/functions.json`（所有函数定义都在这个 JSON 文件里）

**数据流**：
```
前端页面加载 → GET /api/functions/ → 后端读取 functions.json → 返回函数列表
用户搜索    → GET /api/functions/search/?q=lstm → 后端过滤 → 返回匹配结果
```

---

### 4.5 可视化工作流编辑器（核心功能）

**你看到的**：一个类似 Figma/Draw.io 的画布，左边是算法模块列表，拖到画布上，用线连起来

**它做了什么**：
这是平台最核心的功能。用户通过拖拽的方式把多个算法模块组合成一个完整的工作流（DAG 有向无环图）。

工作流程：
1. 从左侧函数库拖一个"数据加载"模块到画布
2. 再拖一个"特征提取"模块
3. 把"数据加载"的输出端口连到"特征提取"的输入端口
4. 继续添加"LSTM模型"、"评估指标"等模块
5. 点击"执行"，系统按拓扑排序依次执行每个节点

**关键概念**：
- **节点（Node）**：画布上的每个方块，对应一个算法函数
- **边（Edge）**：节点之间的连线，表示数据流向
- **端口（Port）**：节点上的连接点，分输入端口和输出端口，有类型约束
- **拓扑排序**：系统自动计算执行顺序，确保上游节点先执行

**涉及的文件**：
- 前端：
  - `pages/WorkflowEditorPage.tsx`（编辑器主页面）
  - `components/workflow/`（编辑器子组件）
  - `stores/workflowEnhancedStore.ts`（编辑器状态管理）
  - `services/workflowEnhancedApi.ts`（保存/加载 API）
- 后端：
  - `api/workflows_enhanced.py`（工作流 CRUD API）
  - `services/workflow_enhanced_service.py`（工作流持久化，存为 JSON 文件）
  - `services/execution_service.py`（工作流执行引擎）
  - `services/workflow_validator.py`（工作流验证：环检测、类型检查）
  - `nodes/function_node.py`（函数节点执行器）

**数据模型**（`models/workflow.py`）：
```python
Workflow
  ├── modules: List[ModuleInstance]    # 画布上的所有节点
  │     ├── id: str                    # 节点ID
  │     ├── type: str                  # 对应的函数ID
  │     ├── position: {x, y}           # 画布坐标
  │     ├── parameters: Dict           # 用户填的参数值
  │     ├── inputs: List[Port]         # 输入端口
  │     └── outputs: List[Port]        # 输出端口
  ├── connections: List[Connection]    # 所有连线
  │     ├── source: {module_id, port}  # 起点
  │     └── target: {module_id, port}  # 终点
  └── metadata                         # 元数据（作者、版本、标签）
```

---

### 4.6 智能编排（Workflow Agent）

**你看到的**：一个对话界面，你用自然语言描述需求，AI 帮你自动生成工作流

**它做了什么**：
不想手动拖拽？告诉 AI "我要做光伏发电预测"，它会：
1. 理解你的需求
2. 从算法库里选合适的模块
3. 自动组合成工作流
4. 考虑领域约束（比如光伏预测必须用日照数据）
5. 参考最佳实践

**架构设计**（`services/workflow_agent/`）：
```
用户输入
    ↓
SkillOrchestrator（技能编排器）
    ├── knowledge/（知识库）
    │   ├── algorithm_library.py    # 算法库知识
    │   ├── best_practices.py       # 最佳实践
    │   └── domain_constraints.py   # 领域约束
    ├── skills/（技能）
    │   └── algorithm_compose.py    # 算法组合技能
    ├── audit/（审计）
    │   └── audit_logger.py         # 操作审计日志
    ├── event_bus.py                # 事件总线
    └── rbac.py                     # 权限控制
```

**涉及的文件**：
- 前端：`pages/WorkflowAgentPage.tsx`、`stores/workflowAgentStore.ts`
- 后端：`api/workflow_agent.py`、`services/workflow_agent/`（整个目录）

---

### 4.7 Algorithm Agent（AI 对话助手）

**你看到的**：一个聊天界面，可以和 AI 讨论算法选型、参数配置等问题

**它做了什么**：
这是一个更通用的 AI 助手，支持：
- 算法推荐："我的场景适合用什么模型？"
- 参数配置："LSTM 的学习率设多少合适？"
- 训练监控："帮我启动模型训练"
- 漂移检测："模型精度下降了怎么办？"

**技术实现**：
- 支持多种 LLM 后端：OpenAI 兼容接口、Azure OpenAI、Anthropic Claude
- 混合响应策略：简单问题用规则引擎秒回，复杂问题调 LLM
- 支持流式输出（打字机效果）
- 会话历史持久化（Zustand + localStorage）

**涉及的文件**：
- 前端：`pages/AlgorithmAgentPage.tsx`、`stores/algorithmAgentStore.ts`
- 后端：`api/algorithm_agent.py`、`services/llm_service.py`
- 配置：`data/llm_configs.json`（LLM 连接配置）

---

### 4.8 算法方案库

**你看到的**：按行业场景分类的算法方案列表，含精度数据和应用案例

**它做了什么**：
- 展示 449 个行业算法方案
- 每个方案包含：适用场景、算法组合、精度指标、应用实例
- 支持精度管理（跟踪不同方案的准确率）
- 支持应用实例查看（看别人怎么用的）

**涉及的文件**：
- 前端：`pages/AlgorithmSolutionLibraryPage.tsx`、`pages/TemplateAccuracyPage.tsx`、`pages/TemplateApplicationPage.tsx`
- 后端：`api/algorithm_solutions.py`
- 数据：`data/scenario_algorithm_mappings.json`

---

### 4.9 模板库（Skills）

**你看到的**：预置的算法模板列表，可以直接使用或作为起点修改

**它做了什么**：
- 提供开箱即用的算法模板（比如"光伏功率预测 Skill"）
- 每个 Skill 包含完整的训练代码（`prepare.py` + `train.py`）
- 支持 Skill 测试、训练监控、结果查看

**涉及的文件**：
- 前端：`pages/OfficialTemplateLibraryPage.tsx`、`pages/SkillDetailPage.tsx`
- 后端：`api/algo_template_skill.py`
- 数据：`data/skills/`（每个 Skill 一个目录，含代码和数据）

---

### 4.10 回测系统

**你看到的**：回测任务列表、执行监控、结果分析图表

**它做了什么**：
模型训练好了，怎么知道效果好不好？回测系统让你：
1. 创建回测任务（选模型、选数据集、选评估指标）
2. 执行回测（系统自动跑）
3. 监控进度（实时看执行状态）
4. 分析结果（图表展示各指标）
5. 导出报告（CSV 格式）

还支持调度队列、资源配额管理。

**涉及的文件**：
- 前端：`pages/UnifiedBacktestPage.tsx`、`pages/UnifiedBacktestMonitorPage.tsx`、`pages/UnifiedBacktestResultPage.tsx`
- 后端：`api/backtest.py`
- 数据：`data/backtest/`（任务和运行记录的 JSON 文件）

---

### 4.11 部署与服务管理

**你看到的**：部署任务管理、服务列表、监控面板

**它做了什么**：
模型效果满意了，要部署成在线服务：
1. 创建部署任务（选模型版本、配置资源）
2. 执行部署
3. 服务管理（启动/停止/重启/扩缩容）
4. 灰度发布（金丝雀发布，逐步切流量）
5. 版本回滚
6. 服务监控（QPS、延迟、错误率）
7. 告警规则配置

**涉及的文件**：
- 前端：`pages/DeploymentTaskPage.tsx`、`pages/ServiceManagementPage.tsx`、`pages/ServiceMonitorPage.tsx`
- 后端：`api/deployment.py`
- 数据：`data/deployment/`（tasks.json、services.json、alerts.json）

---

### 4.12 算法运维中心（AlgorithmOps）

**你看到的**：漂移监控、A/B 测试、自动重训

**它做了什么**：
模型上线后不是一劳永逸的，需要持续运维：
- **漂移监控**：检测模型输入数据分布是否发生变化（数据漂移）或模型预测精度是否下降（概念漂移）
- **A/B 测试**：同时运行两个模型版本，对比效果
- **自动重训**：当检测到漂移时，自动触发模型重新训练

**涉及的文件**：
- 前端：`pages/AlgorithmOpsPage.tsx`、`pages/DriftMonitorPage.tsx`、`pages/ABTestPage.tsx`、`pages/AutoRetrainPage.tsx`
- 后端：`api/algorithm_ops.py`

---

## 五、数据存储方式

本项目使用两种数据存储方式：

### 5.1 SQLite 数据库（`data/users.db`）

存储需要关系查询的数据：
- 用户表（users）
- 工作流表（workflows）
- 执行记录表（workflow_executions）
- 服务状态表（service_status）
- 算法分类/函数/版本/审计日志表

通过 SQLAlchemy ORM 操作，模型定义在 `models/` 目录下。

### 5.2 JSON 文件（`data/*.json`）

存储配置型、文档型数据：
- `functions.json` — 780 个算法函数定义
- `industry_scenarios.json` — 13 个行业场景
- `industry_templates.json` — 449 个行业算法方案
- `workflows_enhanced/*.json` — 用户保存的工作流（每个工作流一个文件）
- `backtest/*.json` — 回测任务和运行记录
- `deployment/*.json` — 部署任务和服务配置
- `llm_configs.json` — LLM 连接配置

**为什么用 JSON 而不全用数据库？**
- 算法函数定义是静态配置，JSON 更直观易编辑
- 工作流数据结构复杂（嵌套的节点和连线），JSON 比关系表更自然
- 开发阶段方便调试，直接打开文件就能看数据

---

## 六、前端架构详解

### 6.1 路由结构（App.tsx）

所有页面路由都在 `App.tsx` 里配置：

```
/login              → 登录页（公开）
/register           → 注册页（公开）
/home               → 首页仪表盘
/industry           → 行业场景列表
/industry/:id       → 场景详情
/functions          → 基础算法库
/workflow/editor    → 工作流编辑器
/workflow/list      → 我的工作流
/workflow-agent     → 智能编排
/algorithm-agent    → AI 对话助手
/algorithm-solutions → 算法方案库
/template-library   → 模板库
/backtest/unified   → 回测任务
/deployment         → 部署任务
/ops                → 算法运维中心
/system-status      → 系统状态
/settings           → 系统配置
/profile            → 个人信息
```

除了 `/login` 和 `/register`，其他页面都被 `ProtectedRoute` 包裹，未登录会跳转到登录页。

### 6.2 状态管理（Zustand Stores）

| Store 文件 | 管理什么 |
|------------|---------|
| `workflowEnhancedStore.ts` | 工作流编辑器的节点、边、选中状态 |
| `workflowEditorStore.ts` | 编辑器 UI 状态 |
| `algorithmAgentStore.ts` | AI 对话的消息、会话、历史 |
| `workflowAgentStore.ts` | 智能编排的状态 |
| `executionStore.ts` | 工作流执行状态 |
| `uiStore.ts` | 全局 UI 状态 |

### 6.3 API 调用层（services/）

每个后端模块对应一个 API 文件：

| 文件 | 对应后端 |
|------|---------|
| `api.ts` | 基础 axios 实例 + 函数库 API |
| `workflowEnhancedApi.ts` | 工作流 CRUD |
| `algorithmAgentApi.ts` | AI 对话 |
| `industryApi.ts` | 行业场景 |
| `backtestApi.ts` | 回测 |
| `deploymentApi.ts` | 部署 |
| `algorithmOpsApi.ts` | 运维 |

---

## 七、后端 API 路由总览

所有 API 都注册在 `main.py` 中：

| 路由前缀 | 模块 | 说明 |
|----------|------|------|
| `/api/auth` | auth.py | 登录、注册、用户管理 |
| `/api/functions` | functions.py | 算法函数库 CRUD |
| `/api/industry` | industry.py | 行业场景和方案 |
| `/api/workflows-enhanced` | workflows_enhanced.py | 工作流 CRUD |
| `/api/workflow-agent` | workflow_agent.py | 智能编排 |
| `/api/agent/algorithm` | algorithm_agent.py | AI 对话助手 |
| `/api/llm` | llm_config.py | LLM 配置管理 |
| `/api/algorithm-solutions` | algorithm_solutions.py | 算法方案库 |
| `/api/backtest` | backtest.py | 回测系统 |
| `/api/deployment` | deployment.py | 部署管理 |
| `/api/algorithm-ops` | algorithm_ops.py | 算法运维 |
| `/api/system` | system.py | 系统监控 |
| `/api/templates` | templates.py | 模板管理 |
| `/api/upload` | upload.py | 文件上传 |

启动后访问 http://localhost:8000/docs 可以看到完整的 Swagger API 文档。

---

## 八、启动项目

### 环境要求
- Python 3.10+（推荐用 Conda）
- Node.js 18+

### 第一步：安装后端依赖

```bash
# 方式一：用 Conda（推荐）
conda env create -f backend/environment.yml
conda activate cp_web

# 方式二：用 pip
pip install -r backend/requirements.txt
```

### 第二步：安装前端依赖

```bash
cd frontend
npm install
```

### 第三步：启动后端

```bash
cd backend
python -m uvicorn main:app --reload --port 8000
```

看到 `数据库初始化完成` + `Application startup complete` 就成功了。

### 第四步：启动前端（另开一个终端）

```bash
cd frontend
npm run dev
```

### 第五步：访问

- 前端界面：http://localhost:5173
- 后端 API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health

注册一个账号，登录后就能看到完整的平台界面了。

---

## 九、一个完整的使用流程示例

以"光伏发电功率预测"为例，走一遍完整流程：

```
1. 登录系统
   ↓
2. 首页 → 点击"行业场景"
   ↓
3. 选择"光伏发电预测"场景
   ↓
4. 查看推荐的算法方案（数据清洗 → 特征工程 → LSTM → 评估）
   ↓
5. 进入工作流编辑器，拖拽模块组建工作流
   （或者用智能编排，让 AI 自动生成）
   ↓
6. 配置每个模块的参数
   ↓
7. 点击"执行"，查看运行结果
   ↓
8. 满意 → 创建回测任务，验证模型效果
   ↓
9. 回测通过 → 创建部署任务，上线为 API 服务
   ↓
10. 在运维中心监控模型表现，必要时自动重训
```

---

## 十、关键设计决策

### 为什么选 FastAPI 而不是 Django/Flask？
- FastAPI 原生支持 async，适合 AI 推理等 IO 密集场景
- 自动生成 Swagger 文档，前后端协作方便
- Pydantic 模型自带数据校验

### 为什么选 Zustand 而不是 Redux？
- 更轻量，代码量少
- 不需要 action/reducer 样板代码
- 支持 persist 中间件，方便持久化会话历史

### 为什么选 React Flow？
- 专门为节点编辑器设计的库
- 支持自定义节点、边、端口
- 内置缩放、平移、选择等交互

### 为什么用 JSON 文件存储工作流？
- 工作流数据结构是深度嵌套的（节点 → 端口 → 参数），JSON 天然适合
- 开发阶段方便调试，直接看文件
- 未来可以平滑迁移到 MongoDB 等文档数据库

---

## 十一、常见问题

**Q: 后端启动报 `ModuleNotFoundError`**
A: 依赖没装全，执行 `pip install -r requirements.txt`

**Q: 前端 `npm` 命令找不到**
A: Node.js 没装或没加到 PATH，装完重开终端

**Q: 前端页面白屏**
A: 打开浏览器开发者工具（F12）看 Console 报错，通常是后端没启动导致 API 请求失败

**Q: 登录后跳转回登录页**
A: 检查 localStorage 里有没有 `isLoggedIn` 字段，可能是浏览器隐私模式

**Q: 工作流执行失败**
A: 检查节点之间的连线类型是否匹配，以及必填参数是否都填了

---

*本文档最后更新：2026-04-14*
<!-- @AI_GENERATED: end -->
