# AIP 全栈开发与 AI Agent 系统化教程

> 写给你（zxk）的个人定制教程。基于你的 AIP 项目代码和四份对话记录，分析你的知识缺口，用你项目里的真实代码做例子。
>
> 阅读建议：不要一次读完，按章节来，每章配合你项目里的对应文件边看边练。

---

## 目录

- [第一部分：知识缺口分析（你现在在哪里）](#第一部分知识缺口分析)
- [第二部分：Python 后端基础](#第二部分python-后端基础)
- [第三部分：HTTP 与 REST API](#第三部分http-与-rest-api)
- [第四部分：FastAPI 框架](#第四部分fastapi-框架)
- [第五部分：前端基础（React + TypeScript）](#第五部分前端基础)
- [第六部分：前后端通信全链路](#第六部分前后端通信全链路)
- [第七部分：异步编程](#第七部分异步编程)
- [第八部分：AI Agent 架构](#第八部分ai-agent-架构)
- [第九部分：大模型集成（LLM Integration）](#第九部分大模型集成)
- [第十部分：LangGraph 与状态机编排](#第十部分langgraph-与状态机编排)
- [第十一部分：工程实践与调试](#第十一部分工程实践与调试)
- [第十二部分：学习路线图](#第十二部分学习路线图)

---


## 第一部分：知识缺口分析

### 你现在的水平（从对话记录判断）

**强项（已经具备的）：**
- 业务理解深：负荷预测、回测、调优的业务逻辑你比大多数开发者都清楚
- 产品直觉好：你提出的"先弹 Diff 再自动"、"固定主干 + 按功能分槽"、"上线整份模板"都是成熟的产品决策
- 学习意愿强：你会主动问"这是什么"、"为什么这样"，而不是只要结果

**需要补的（按优先级排序）：**

| 优先级 | 知识领域 | 你在对话里暴露的信号 | 影响 |
|--------|----------|---------------------|------|
| P0 | Python 基础语法 | 问 `async def` 是什么 | 看不懂后端代码 |
| P0 | HTTP 协议 | 问 `POST/GET` 是固定结构吗 | 不理解前后端怎么通信 |
| P0 | 前后端分层 | 问"这条指令是前端还是后端" | 改代码时不知道改哪里 |
| P1 | FastAPI 路由 | 遇到 404 不知道是路由顺序问题 | 调试效率低 |
| P1 | React 组件 | 问 `.tsx` 是什么文件 | 前端改动看不懂 |
| P1 | 异步编程 | 不理解为什么"停止"按钮没反应 | 无法排查并发问题 |
| P2 | Agent 架构 | 问 runtime 是什么 | 无法独立设计 Agent 系统 |
| P2 | LLM 集成 | 问"怎么让建议更智能" | 无法优化 Agent 输出质量 |
| P2 | LangGraph | 你说想学但还没开始 | 后续编排升级的前置知识 |

---

## 第二部分：Python 后端基础

### 2.1 函数定义

Python 里定义函数用 `def`，这是你后端代码里最常见的结构。

```python
# 你项目里的真实例子：backend-service/services/operation_agent/router.py
def _rule_scores(self, message: str) -> Dict[str, float]:
    msg = (message or "").lower()
    result: Dict[str, float] = {}
    for name, keywords in RULE_KEYWORDS.items():
        hit = sum(1 for kw in keywords if kw.lower() in msg)
        result[name] = min(1.0, hit / 2.0)
    return result
```

逐行解释：
- `def` — 定义函数的关键字
- `self` — 表示"这个对象自己"（因为这个函数属于 `OperationRouter` 类）
- `message: str` — 参数名是 `message`，类型是字符串（`str`）。冒号后面的是**类型注解**，不是强制的，但能帮你和 IDE 理解代码
- `-> Dict[str, float]` — 返回值类型：一个字典，key 是字符串，value 是浮点数
- `(message or "").lower()` — 如果 message 是 None 就用空字符串，然后转小写
- `return result` — 把结果返回给调用者

### 2.2 类（Class）

类是"把数据和操作数据的函数打包在一起"的方式。

```python
# 你项目里的真实例子：backend-service/services/operation_agent/sub_agents.py
class DriftSubAgent:
    def __init__(self, executor: AgentToolExecutor) -> None:
        self.executor = executor          # 把工具执行器存到自己身上

    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # ... 执行漂移分析
        drift = await self.executor.detect_drift(...)
        return drift
```

关键概念：
- `class DriftSubAgent:` — 定义一个类，名字叫 DriftSubAgent
- `__init__` — 构造函数，创建对象时自动调用。`self` 是对象自己
- `self.executor = executor` — 把传进来的 executor 存到对象的属性上，后面其他方法可以用 `self.executor` 访问
- `async def run(...)` — 异步方法（后面第七部分详细讲）

**类比理解**：类像一个"岗位说明书"，`DriftSubAgent` 说明了"漂移分析员"这个岗位需要什么工具（`executor`）、能做什么事（`run`）。每次 `DriftSubAgent(executor)` 就是"招了一个人上岗"。

### 2.3 字典（Dict）— 你项目里最常用的数据结构

```python
# 你项目里到处都是这种结构
context = {
    "workflow_id": "workflow-load-forecast-backtest-v2",
    "preload": { "nodes": 24, "edges": 23 },
    "artifacts": {}
}

# 读取
wf_id = context.get("workflow_id")           # 安全读取，不存在返回 None
wf_id = context.get("workflow_id", "default") # 不存在返回 "default"
wf_id = context["workflow_id"]                # 直接读取，不存在会报错

# 写入
context["new_field"] = "value"

# 判断是否存在
if "workflow_id" in context:
    print("有这个字段")
```

### 2.4 列表推导式

```python
# 你项目里的真实例子：router.py 里的关键词匹配
hit = sum(1 for kw in keywords if kw.lower() in msg)

# 等价于：
hit = 0
for kw in keywords:
    if kw.lower() in msg:
        hit = hit + 1
```

推导式是 Python 的"简写循环"，一行搞定。你项目里大量使用。

### 2.5 模块导入

```python
# 你项目里的真实例子
from typing import Any, Dict, List, Tuple    # 类型注解用的
from services.llm_service import get_llm_service  # 从另一个文件导入函数
import json                                    # 导入标准库
```

- `from X import Y` — 从模块 X 里只拿 Y
- `import X` — 导入整个模块，用 `X.something` 访问

### 对应你项目的文件

| 概念 | 去看哪个文件 | 重点看什么 |
|------|-------------|-----------|
| 函数定义 | `backend-service/services/operation_agent/router.py` | `_rule_scores` 和 `route` |
| 类 | `backend-service/services/operation_agent/sub_agents.py` | 四个 SubAgent 类 |
| 字典操作 | `backend-service/services/operation_agent/preloader.py` | `load` 方法里的 context 组装 |

---

## 第三部分：HTTP 与 REST API

### 3.1 HTTP 是什么

HTTP 是前端和后端"说话"的协议。你每次在浏览器里看到数据，都是通过 HTTP 请求/响应传输的。

一次 HTTP 通信就两步：
1. **请求（Request）**：前端发给后端，说"我要什么"
2. **响应（Response）**：后端返回给前端，说"给你结果"

### 3.2 HTTP 方法（你问过的 GET/POST）

| 方法 | 语义 | 你项目里的例子 |
|------|------|---------------|
| `GET` | 只读查询，不改数据 | `GET /api/workflows/enhanced/summaries` — 查模板列表 |
| `POST` | 创建/触发动作 | `POST /api/workflows/enhanced/auto-research-async` — 启动自动实验 |
| `PUT` | 整体替换/更新 | `PUT /api/workflows/enhanced/production-workflow-ref` — 更新生产登记 |
| `DELETE` | 删除 | `DELETE /api/agent/algorithm/sessions/{id}` — 删除会话 |

**记忆口诀**：GET 看、POST 做、PUT 改、DELETE 删。

### 3.3 URL 的结构

```
POST /api/workflows/enhanced/{workflow_id}/backtest-cancel/{execution_id}
 │         │                    │                              │
 方法    固定前缀           路径参数（变量）              路径参数（变量）
```

`{workflow_id}` 和 `{execution_id}` 是**占位符**，实际请求时会被替换成真实值：
```
POST /api/workflows/enhanced/workflow-abc123/backtest-cancel/exec-xyz789
```

### 3.4 请求体（Request Body）

POST 请求通常带一个 JSON 格式的"包裹"，告诉后端具体要做什么：

```json
{
  "baseline_workflow_id": "workflow-load-forecast-backtest-v2",
  "windows": [
    { "start_date": "2026-02-01", "end_date": "2026-02-03" }
  ],
  "evaluation_contract": {
    "backtest_mode": "rolling_retrain",
    "train_days": 30,
    "daily_horizon": 96
  }
}
```

### 3.5 响应体（Response Body）

后端处理完后返回 JSON：

```json
{
  "run_id": "ares-99fd045e647e",
  "status": "running",
  "message": "自动实验已启动"
}
```

### 3.6 状态码（Status Code）

| 状态码 | 含义 | 你遇到过的场景 |
|--------|------|---------------|
| 200 | 成功 | 正常返回数据 |
| 400 | 请求有误 | 参数校验失败（如预检不通过） |
| 404 | 找不到 | 路由顺序错误导致 `model-operators-available` 被当成 `{workflow_id}` |
| 500 | 服务器内部错误 | `EnhancedNodeData` 没有 `.get()` 方法 |

**你遇到过的 404 问题**：FastAPI 按注册顺序匹配路由，`GET /{workflow_id}` 写在 `GET /model-operators-available` 前面，导致后者被当成 workflow_id 去查文件。这就是为什么固定路径要放在动态路径前面。

---

## 第四部分：FastAPI 框架

### 4.1 FastAPI 是什么

FastAPI 是 Python 的 Web 框架，用来写后端 API。你项目的整个后端都建在它上面。

### 4.2 路由（Router）— 把 URL 和函数绑定

```python
# 你项目里的真实例子：backend-service/api/workflows_enhanced.py

# 定义一个路由组，所有路由都以 /api/workflows/enhanced 开头
router = APIRouter(prefix="/api/workflows/enhanced", tags=["workflows-enhanced"])

# GET 请求：查询模板列表
@router.get("/summaries")
async def list_workflow_summaries():
    # ... 返回模板列表
    return {"summaries": [...]}

# POST 请求：启动自动实验
@router.post("/auto-research-async")
async def start_auto_research(request: Request):
    body = await request.json()
    # ... 启动实验
    return {"run_id": "ares-xxx", "status": "started"}
```

`@router.get("/summaries")` 的意思是：当有人发 `GET /api/workflows/enhanced/summaries` 请求时，执行下面这个函数。

### 4.3 路径参数

```python
# 你项目里的真实例子
@router.get("/{workflow_id}/params-summary")
async def get_workflow_params_summary(workflow_id: str):
    # workflow_id 会自动从 URL 里提取
    # 比如请求 /api/workflows/enhanced/workflow-abc/params-summary
    # 这里 workflow_id = "workflow-abc"
    workflow = load_workflow_from_file(workflow_id)
    return {"global_config": ..., "node_params": ...}
```

### 4.4 路由顺序（你踩过的坑）

```python
# ❌ 错误顺序：动态路由在前，会"吃掉"后面的固定路由
@router.get("/{workflow_id}")           # 第 786 行
async def get_workflow(workflow_id: str): ...

@router.get("/model-operators-available")  # 第 900 行
async def list_model_operators(): ...
# 请求 /model-operators-available 时，FastAPI 会把它匹配到第一个路由
# workflow_id = "model-operators-available"，然后找不到这个模板 → 404

# ✅ 正确顺序：固定路由在前
@router.get("/model-operators-available")  # 先注册
async def list_model_operators(): ...

@router.get("/{workflow_id}")              # 后注册
async def get_workflow(workflow_id: str): ...
```

**规则**：固定路径永远放在动态路径（`{xxx}`）前面。

### 4.5 Pydantic 模型（请求/响应的"形状定义"）

```python
# 你项目里的真实例子：backend-service/api/algorithm_agent.py
from pydantic import BaseModel

class SessionContext(BaseModel):
    workflow_id: str = None                    # 可选，默认 None
    template_id: str = None
    last_executed_workflow_id: str = None
    trigger_backtest_after_retrain: bool = False
    trigger_backtest_after_tuning: bool = False
    backtest_start_date: str = None
    backtest_end_date: str = None

class ChatRequest(BaseModel):
    session_id: str
    message: str
    agent_type: str = None                     # 可选
    language: str = None
    context: SessionContext = SessionContext()   # 默认空上下文
```

Pydantic 做两件事：
1. **自动校验**：前端传的 JSON 如果字段类型不对，直接返回 422 错误
2. **自动文档**：打开 `http://localhost:8080/docs` 能看到所有接口的参数说明

### 对应你项目的文件

| 概念 | 去看哪个文件 | 重点看什么 |
|------|-------------|-----------|
| 路由定义 | `backend-service/api/workflows_enhanced.py` | 文件开头的 `@router.get/post` |
| 路径参数 | 同上 | `/{workflow_id}/...` 系列路由 |
| Pydantic 模型 | `backend-service/api/algorithm_agent.py` | `SessionContext`、`ChatRequest` |
| 路由注册 | `backend-service/main.py`（如果有）| `app.include_router(...)` |

---

## 第五部分：前端基础（React + TypeScript）

### 5.1 文件后缀

| 后缀 | 含义 |
|------|------|
| `.ts` | TypeScript 文件（带类型的 JavaScript），不含界面标签 |
| `.tsx` | TypeScript + JSX 文件（可以写 `<div />` 这种界面标签） |
| `.json` | 数据/配置文件 |

### 5.2 React 组件 — 前端的"积木块"

```tsx
// 你项目里的简化例子
// 一个 React 组件就是一个"返回界面的函数"
const MyButton: React.FC = () => {
  const [loading, setLoading] = useState(false);  // 状态：是否加载中

  const handleClick = () => {
    setLoading(true);
    // ... 做一些事
    setLoading(false);
  };

  return (
    <Button loading={loading} onClick={handleClick}>
      点击我
    </Button>
  );
};
```

关键概念：
- `useState` — React 的"状态钩子"，让组件能记住数据。`loading` 是当前值，`setLoading` 是修改它的函数
- `<Button>` — Ant Design 的按钮组件（你项目用的 UI 库）
- `onClick={handleClick}` — 点击时执行 `handleClick` 函数

### 5.3 useEffect — "副作用钩子"

```tsx
// 你项目里的真实模式：选好两个模板后自动加载参数
useEffect(() => {
  // 这个函数会在 baselineId 或 challengerId 变化时自动执行
  if (baselineId && challengerId) {
    loadParamsComparison(baselineId, challengerId);
  }
}, [baselineId, challengerId]);  // ← 依赖数组：只有这两个值变了才重新执行
```

**你踩过的坑**：`onStart` 的 `useCallback` 依赖只写了 `[form]`，但 `form` 引用不变，导致回调一直用初始的空 `challOverride`。修复方法是把 `challOverride` 也加进依赖数组。

### 5.4 TypeScript 类型

```typescript
// 你项目里的真实例子：frontend-sevice/src/types/algorithm-agent.ts
interface OperationObservability {
  preloading?: {
    workflow_id?: string;
    workflow_id_source?: string;
    template_nodes?: number;
    template_edges?: number;
  };
  routing?: {
    rule_scores?: Record<string, number>;
    llm_scores?: Record<string, number>;
    execution_plan?: string[];
  };
  execution?: {
    stages?: Array<{
      agent: string;
      status: string;
      summary?: string;
      details?: Record<string, any>;
    }>;
  };
}
```

TypeScript 的类型系统帮你在**写代码时**就发现错误，而不是等到运行时才崩。

### 5.5 前端项目结构（你项目的实际布局）

```
frontend-sevice/src/
├── pages/          ← 页面级组件（每个页面一个文件）
│   ├── AlgorithmAgentPage.tsx      ← 运营 Agent 对话页
│   ├── WorkflowBaselineComparePage.tsx  ← 基线比对页
│   └── WorkflowEditorPage.tsx      ← 工作流编辑器
├── services/       ← API 调用封装（前端怎么发请求）
│   ├── workflowEnhancedApi.ts      ← 增强工作流相关 API
│   └── algorithmAgentApi.ts        ← Agent 对话 API
├── stores/         ← 状态管理（跨组件共享数据）
├── types/          ← TypeScript 类型定义
├── components/     ← 可复用的小组件
├── config/         ← 配置（如 modelFamilyRegistry.ts）
└── utils/          ← 工具函数
```

### 对应你项目的文件

| 概念 | 去看哪个文件 | 重点看什么 |
|------|-------------|-----------|
| 页面组件 | `frontend-sevice/src/pages/AlgorithmAgentPage.tsx` | 整体结构、useState、useEffect |
| API 封装 | `frontend-sevice/src/services/workflowEnhancedApi.ts` | 怎么调后端接口 |
| 类型定义 | `frontend-sevice/src/types/algorithm-agent.ts` | OperationObservability |

---


## 第六部分：前后端通信全链路

### 6.1 一次完整请求的旅程

用你项目里"停止回测"这个真实例子，走一遍完整链路：

```
用户点击"停止"按钮
    ↓
前端 onClick 事件触发
    ↓
前端函数 stopQuickBacktest() 被调用
    ↓
前端组装 URL 并发 HTTP 请求：
  fetch(`/api/workflows/enhanced/${wfId}/backtest-cancel/${execId}`, { method: 'POST' })
    ↓
Vite 开发服务器把 /api 转发到 http://localhost:8080（见 vite.config.ts）
    ↓
FastAPI 路由匹配：
  @router.post("/{workflow_id}/backtest-cancel/{execution_id}")
    ↓
后端函数 cancel_backtest_workflow_async() 执行：
  找到任务 → event.set() 发送取消信号
    ↓
后端返回 JSON：{"success": true, "message": "已发送异步回测中止信号"}
    ↓
前端收到响应 → 更新界面状态
```

### 6.2 前端怎么发请求（你项目的实际写法）

你项目里有两种写法：

**写法一：直接用 fetch（简单场景）**

```typescript
// frontend-sevice/src/services/workflowQuickBacktest.ts
export function stopQuickBacktest() {
  const wfId = currentWorkflowId;
  const execId = currentExecutionId;
  if (wfId && execId) {
    fetch(`/api/workflows/enhanced/${wfId}/backtest-cancel/${execId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    }).catch(() => {});
  }
}
```

**写法二：用 axios 封装（大多数场景）**

```typescript
// frontend-sevice/src/services/workflowEnhancedApi.ts
export const baselineCompareApi = {
  startCompareAsync: (body: any) =>
    api.post('/api/workflows/enhanced/compare-backtest-batch-async', body),
  getCompareStatus: (comparisonId: string) =>
    api.get(`/api/workflows/enhanced/compare-backtest-status/${comparisonId}`),
};
```

`api` 是 axios 实例，自动处理了 JSON 序列化、错误拦截、响应解包等。

### 6.3 后端怎么接请求

```python
# backend-service/api/workflows_enhanced.py
@router.post("/{workflow_id}/backtest-cancel/{execution_id}", summary="取消异步回测")
async def cancel_backtest_workflow_async(workflow_id: str, execution_id: str):
    # workflow_id 和 execution_id 从 URL 自动提取
    state = _execution_store.get(execution_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"执行记录不存在: {execution_id}")
    event = _backtest_async_cancel_events.get(execution_id)
    if event is None:
        return {"success": False, "message": "没有正在运行的异步回测任务"}
    event.set()  # 发送取消信号
    return {"success": True, "message": "已发送异步回测中止信号"}
```

### 6.4 字段命名转换（前后端常见坑）

| 层 | 命名风格 | 例子 |
|----|---------|------|
| 前端 TypeScript | camelCase | `workflowId`, `startDate` |
| HTTP JSON | snake_case | `workflow_id`, `start_date` |
| 后端 Python | snake_case | `workflow_id`, `start_date` |
| 数据库 | snake_case | `workflow_id`, `start_date` |

前端和 HTTP 之间有时需要转换。你项目里大部分直接用 snake_case 统一了。

### 6.5 用浏览器 Network 面板调试（你问过怎么用）

1. 按 **F12** 打开开发者工具
2. 点顶部 **Network（网络）** 标签
3. 在页面上操作（比如点"启动自动实验"）
4. Network 列表里会出现请求，点击某一条：
   - **Headers（标头）**：看请求方法、URL、状态码
   - **Payload（负载）**：看你发了什么 JSON
   - **Response（响应）**：看后端返回了什么 JSON
5. 用 **Ctrl+F** 在 Response 里搜索字段名

---

## 第七部分：异步编程

### 7.1 为什么需要异步

你的回测任务可能跑几分钟。如果后端"等它跑完再回复"，这段时间其他用户的请求全部卡住。

异步的意思是：**启动任务后立刻回复"已启动"，任务在后台跑，前端定期来问"跑完没"。**

### 7.2 Python 的 async/await

```python
# 普通函数：一步一步做，做完才返回
def sync_function():
    result = do_something()      # 卡在这里等
    return result

# 异步函数：可以在等待时"让出"，去处理别的请求
async def async_function():
    result = await do_something()  # 等待时可以处理其他请求
    return result
```

- `async def` — 声明这是一个异步函数
- `await` — "等这个操作完成，但等待期间可以去做别的事"

**类比**：你去餐厅点菜，`sync` 是站在厨房门口等菜做好；`await` 是回座位玩手机，菜好了服务员叫你。

### 7.3 你项目里的异步任务模式

你的 AutoResearch、回测、比对都用同一套模式：

```
步骤1：POST 启动任务 → 后端立刻返回 run_id
步骤2：GET 轮询状态 → 前端每隔几秒问一次"跑完没"
步骤3：POST 取消任务 → 前端发信号让后端停下来
```

后端实现：

```python
# 步骤1：启动（立刻返回）
@router.post("/auto-research-async")
async def start_auto_research(request: Request):
    run_id = f"ares-{uuid4().hex[:12]}"
    cancel_event = threading.Event()
    # 在后台线程里跑，不阻塞当前请求
    thread = threading.Thread(target=_run_autoresearch_thread, args=(run_id, ...))
    thread.start()
    return {"run_id": run_id, "status": "started"}

# 步骤2：查状态（只读）
@router.get("/auto-research-status/{run_id}")
async def get_auto_research_status(run_id: str):
    state = _auto_research_store.get(run_id)
    return state  # 包含 status, progress, iterations, best_candidate 等

# 步骤3：取消
@router.post("/auto-research-cancel/{run_id}")
async def cancel_auto_research(run_id: str):
    event = _auto_research_cancel_events.get(run_id)
    event.set()  # 通知后台线程停下来
    return {"success": True}
```

前端轮询：

```typescript
// 前端每 3 秒问一次
const pollTimer = setInterval(async () => {
  const status = await getAutoResearchStatus(runId);
  updateUI(status);  // 更新界面
  if (status.status === 'success' || status.status === 'failed') {
    clearInterval(pollTimer);  // 完成了就停止轮询
  }
}, 3000);
```

### 7.4 threading.Event — 取消信号（你遇到过"停不下来"的问题）

```python
import threading

cancel_event = threading.Event()

# 后台线程里检查是否被取消
def background_task():
    for i in range(100):
        if cancel_event.is_set():  # 有人叫我停？
            print("收到取消信号，停止")
            return
        do_one_iteration(i)

# 前端点"停止"时
cancel_event.set()  # 发信号
```

你之前遇到"点停止没反应"，是因为 `cancel_event.set()` 只通知了外层循环，没有传到内层的贝叶斯调参循环里。修复方法是把 `cancel_event` 也传给算子内部，让它在每轮 trial 之间检查。

---

## 第八部分：AI Agent 架构

### 8.1 什么是 Agent

Agent 不是"聊天机器人"。Agent 是**能理解意图、做决策、调用工具、产出结果的自动化系统**。

你项目里的运营 Agent 就是一个典型例子：

```
用户输入："帮我做根因分析，再给重训建议"
    ↓
Master Agent 理解意图
    ↓
路由器打分：root_cause=0.85, retrain=0.72
    ↓
依赖补全：root_cause 依赖 drift → 执行计划 = [drift, root_cause, retrain]
    ↓
按顺序执行子 Agent
    ↓
汇总报告返回给用户
```

### 8.2 你项目的 Agent 架构（Master + Sub-Agent）

```
OperationMasterAgent（总控）
├── OperationContextPreloader（强制预读取）
│   └── 读模板结构、算子参数、最近执行结果
├── OperationRouter（混合打分路由）
│   ├── 规则分（关键词匹配）× 0.55
│   └── LLM 分（语义理解）× 0.45
└── 四个子 Agent（按依赖顺序执行）
    ├── DriftSubAgent（漂移分析）
    ├── RootCauseSubAgent（根因分析）
    ├── RetrainSubAgent（自动重训策略）
    └── TuningSubAgent（模板调优建议）
```

### 8.3 路由器的工作原理（你项目的真实代码）

```python
# backend-service/services/operation_agent/router.py

# 第一步：规则打分（关键词匹配）
RULE_KEYWORDS = {
    "drift": ["漂移", "drift", "分布变化"],
    "root_cause": ["根因", "原因", "为什么", "特征重要性"],
    "retrain": ["重训", "重新训练", "自动重训"],
    "tuning": ["调优", "调参", "优化参数"],
}

# 第二步：LLM 打分（让大模型判断意图）
# 给 LLM 一个 prompt："把用户需求分别打分到 drift/root_cause/retrain/tuning"
# LLM 返回 JSON：{"scores": {"drift": 0.3, "root_cause": 0.9, ...}}

# 第三步：混合打分
final_score = 0.55 * rule_score + 0.45 * llm_score

# 第四步：阈值判定
# >= 0.65 → 直接命中
# 0.45~0.65 → 需要确认
# < 0.45 → 不触发
```

### 8.4 依赖补全（你确认过的规则）

```python
DEPENDENCIES = {
    "drift": [],                          # 独立
    "root_cause": ["drift"],              # 依赖 drift（可参考）
    "retrain": ["drift", "root_cause"],   # 依赖 drift + root_cause
    "tuning": ["drift", "root_cause"],    # 依赖 drift + root_cause
}

# 用户说"做重训" → 自动补全为 [drift, root_cause, retrain]
```

### 8.5 子 Agent 的统一接口

```python
class DriftSubAgent:
    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        # 输入：context（包含预读取数据、上游 Agent 的产物）
        # 输出：字典（包含分析结果、详细报告）
        drift = await self.executor.detect_drift(...)
        return {
            "drift_report": drift,
            "detailed_report": { "conclusion": "...", "evidence": [...] }
        }
```

所有子 Agent 都遵循同一个接口：`run(context) -> dict`。这样 Master 不需要知道每个子 Agent 内部怎么实现，只管按顺序调用。

### 8.6 Agent 和普通 API 的区别

| 维度 | 普通 API | Agent |
|------|---------|-------|
| 输入 | 结构化参数 | 自然语言 + 上下文 |
| 决策 | 固定逻辑 | 动态路由 + 依赖补全 |
| 输出 | 固定格式 | 结构化报告 + 建议动作 |
| 工具 | 不调用外部 | 调用多个工具/服务 |
| 记忆 | 无状态 | 有会话上下文 |

---


## 第九部分：大模型集成（LLM Integration）

### 9.1 你项目里 LLM 在哪些地方被用到

| 用途 | 文件 | 怎么用的 |
|------|------|---------|
| Agent 对话回复 | `api/algorithm_agent.py` | 用户消息 → system prompt + 历史 → LLM 生成回复 |
| 路由意图识别 | `services/operation_agent/router.py` | 用户消息 → LLM 打分 → JSON 输出 |
| AutoResearch 提案 | `api/workflows_enhanced.py` | 实验报告 → LLM 生成参数建议 → JSON schema |
| 根因分析增强 | `services/agent_tools.py` | 指标数据 → LLM 生成改进建议 |

### 9.2 调用 LLM 的基本模式

```python
# 你项目里的 LLM 调用模式（简化版）
from services.llm_service import get_llm_service

async def ask_llm(question: str) -> str:
    llm = await get_llm_service()
    if not llm:
        return "LLM 不可用"

    response = await llm.chat(
        messages=[
            {"role": "system", "content": "你是一个负荷预测专家"},  # 系统提示
            {"role": "user", "content": question},                   # 用户问题
        ],
        temperature=0.0,    # 0 = 确定性输出，1 = 随机性高
        max_tokens=300,     # 最多生成多少 token
    )
    return response.get("content", "")
```

三个关键参数：
- `messages` — 对话历史，包含 system（角色设定）、user（用户输入）、assistant（之前的回复）
- `temperature` — 控制随机性。路由打分用 0（要稳定），创意建议可以用 0.3~0.7
- `max_tokens` — 限制输出长度，避免 LLM 说太多

### 9.3 让 LLM 输出结构化 JSON（你项目的核心技巧）

LLM 默认输出自然语言，但你需要它输出可解析的 JSON。方法是在 prompt 里明确要求：

```python
# 你项目里路由器的做法
prompt = (
    "你是意图路由器。请把用户需求分别打分到 drift/root_cause/retrain/tuning，"
    "每项 0~1，只返回 JSON。"
)
user_content = json.dumps({
    "message": user_message,
    "targets": ["drift", "root_cause", "retrain", "tuning"],
    "format": {
        "scores": {"drift": 0.0, "root_cause": 0.0, "retrain": 0.0, "tuning": 0.0},
        "reason": "text"
    },
})
```

关键技巧：
1. **在 prompt 里说"只返回 JSON"** — 减少废话
2. **给出 format 示例** — LLM 会模仿这个结构
3. **解析时做容错** — LLM 可能返回 ```json 包裹的内容，要先去掉

```python
raw = response.get("content", "").strip()
if raw.startswith("```"):
    raw = raw.strip("`")
    if raw.lower().startswith("json"):
        raw = raw[4:].strip()
data = json.loads(raw)
```

### 9.4 提升 LLM 建议质量的五个层次

这是你问过的"怎么让 Agent 更智能"的系统化回答：

**第一层：Prompt 工程（最快见效）**
- 给 LLM 更好的上下文：不只给"MAPE=9.5"，还给"最近 7 天趋势、失败天数、特征重要性变化"
- 给 LLM 约束：输出必须是 JSON schema，字段有白名单
- 给 LLM 角色：不是"你是 AI 助手"，而是"你是负荷预测运维专家，有 10 年经验"

**第二层：检索增强（RAG）**
- 建经验库：每次实验结果沉淀为 case（你已经做了 `auto_research_memory_cases.json`）
- 新问题先检索相似 case，把历史经验塞进 prompt
- 效果：LLM 不再"从零思考"，而是"参考历史经验"

**第三层：多候选 + 投票**
- 一次生成 3 份建议（A/B/C），用规则评分器选最优
- 你已经实现了这个（`_score_proposal_candidate`）

**第四层：验证闭环**
- 建议生成后，自动跑一次短窗回测验证
- 只有通过阈值的才标记为"可执行建议"

**第五层：持续学习**
- 记录建议是否被采纳、执行后效果如何
- 把结果回写经验库，下一次建议更准

### 9.5 System Prompt 的设计原则

```python
# 你项目里的 system prompt 结构（简化）
def get_system_prompt(agent_type: str) -> str:
    base = "你是 AIP 工业 AI 算法平台的智能助手。"

    if agent_type == "operation":
        return base + """
        你负责运营分析，包括：
        - 漂移检测与根因分析
        - 自动重训策略建议
        - 模板调优方案

        规则：
        1. 先分析数据，再给建议
        2. 建议必须包含具体参数值，不能只说"建议调整"
        3. 每条建议附风险评估
        """
```

好的 system prompt 三要素：
1. **角色定义** — 你是谁、擅长什么
2. **行为规则** — 必须做什么、禁止做什么
3. **输出格式** — 用什么结构回复

---

## 第十部分：LangGraph 与状态机编排

### 10.1 为什么你需要了解 LangGraph

你现在的运营 Agent 是"自研轻量 runtime"：用 Python 代码手写状态流转。这能跑，但随着子 Agent 增多、分支变复杂，维护成本会上升。

LangGraph 是 LangChain 团队做的"Agent 编排框架"，核心思想是**把 Agent 流程画成一张图（Graph）**。

### 10.2 核心概念对照（你的代码 vs LangGraph）

| 你现在的实现 | LangGraph 对应概念 | 说明 |
|-------------|-------------------|------|
| `OperationMasterAgent.process()` | `StateGraph` | 整个执行流程 |
| `preload → route → execute → summarize` | `Node`（节点） | 图里的每一步 |
| `DEPENDENCIES` 字典 | `Edge`（边） | 节点之间的连接 |
| `operation_context` | `State`（状态） | 在节点之间传递的数据 |
| `_auto_research_store` | `Checkpoint`（检查点） | 保存中间状态，可恢复 |
| `confirmation_needed` | `Conditional Edge`（条件边） | 根据条件走不同分支 |

### 10.3 用 LangGraph 思维理解你现在的代码

你的 `OperationMasterAgent.process()` 本质上就是一个状态图：

```
[START]
   ↓
[Preload] ← 强制预读取模板/参数/结果
   ↓
[Route] ← 混合打分 → 生成执行计划
   ↓ (confirmation_needed?)
   ├── Yes → [Ask User] → 等用户确认 → 回到 [Route]
   └── No  → [Execute]
              ↓
         按 plan 顺序执行子 Agent
         drift → root_cause → retrain → tuning
              ↓
         [Summarize] ← 汇总报告
              ↓
           [END]
```

### 10.4 如果用 LangGraph 重写会长什么样（概念代码）

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any

# 定义状态（在节点之间传递的数据）
class OperationState(TypedDict):
    user_message: str
    preload: Dict[str, Any]
    route_result: Dict[str, Any]
    execution_plan: List[str]
    artifacts: Dict[str, Any]
    final_report: str

# 定义节点（每一步做什么）
def preload_node(state: OperationState) -> OperationState:
    state["preload"] = load_template_and_results(state["user_message"])
    return state

def route_node(state: OperationState) -> OperationState:
    state["route_result"] = router.route(state["user_message"], state["preload"])
    state["execution_plan"] = state["route_result"]["execution_plan"]
    return state

def execute_node(state: OperationState) -> OperationState:
    for agent_name in state["execution_plan"]:
        result = run_sub_agent(agent_name, state)
        state["artifacts"][agent_name] = result
    return state

def summarize_node(state: OperationState) -> OperationState:
    state["final_report"] = build_report(state["artifacts"])
    return state

# 构建图
graph = StateGraph(OperationState)
graph.add_node("preload", preload_node)
graph.add_node("route", route_node)
graph.add_node("execute", execute_node)
graph.add_node("summarize", summarize_node)

graph.set_entry_point("preload")
graph.add_edge("preload", "route")
graph.add_edge("route", "execute")
graph.add_edge("execute", "summarize")
graph.add_edge("summarize", END)

app = graph.compile()
```

### 10.5 你现在不需要急着迁移

你的自研 runtime 已经能跑业务了。迁移到 LangGraph 的最佳时机是：
- 子 Agent 超过 6~8 个，手写状态流转开始混乱
- 需要"人在回路"的复杂分支（LangGraph 原生支持 `interrupt_before`）
- 需要持久化检查点（任务中断后可恢复）

现在你要做的是：**理解 LangGraph 的思维模型**（状态图），这样你现在写的代码结构就天然兼容未来迁移。

---

## 第十一部分：工程实践与调试

### 11.1 你遇到过的典型 Bug 和排查方法

**Bug 1：分差为 0（Challenger 覆盖没生效）**
- 现象：比对结果 baseline 和 challenger 分数一样
- 根因：`onStart` 的 `useCallback` 依赖只有 `[form]`，`form` 引用不变，回调锁住了初始的空 `challOverride`
- 排查方法：Network 面板看请求 body 里有没有 `challenger_config_override`
- 修复：把 `challOverride` 加进 `useCallback` 依赖数组
- **教训**：React 的 `useCallback`/`useMemo` 依赖数组漏了变量，是最常见的前端 bug 之一

**Bug 2：404 错误（路由顺序）**
- 现象：`/model-operators-available` 返回 404
- 根因：`GET /{workflow_id}` 在前面，把固定路径当成了动态参数
- 排查方法：看后端日志里实际匹配到了哪个路由
- 修复：把固定路径路由移到动态路径前面
- **教训**：FastAPI 路由按注册顺序匹配，固定路径永远放前面

**Bug 3：停止按钮没反应**
- 现象：点"停止自动实验"后端还在跑
- 根因：`cancel_event.set()` 只通知了外层循环，内层贝叶斯调参没检查
- 排查方法：看后端日志，取消后是否还在打印"第 X/30 轮"
- 修复：把 `cancel_event` 传给算子内部，每轮 trial 之间检查
- **教训**：取消信号必须传到最内层的循环

**Bug 4：`source` 命令报错**
- 现象：PowerShell 里执行 `source scripts/load_glm_env.sh` 报错
- 根因：`source` 是 Bash 命令，PowerShell 里没有
- 修复：写一个 `.ps1` 版本，或用 Git Bash
- **教训**：注意你当前用的是什么 shell

### 11.2 调试三板斧

**第一板斧：看 Network（前端问题）**
- 请求发了没？→ 看 Network 列表
- 参数对不对？→ 看 Payload
- 后端返回了什么？→ 看 Response
- 状态码是什么？→ 200/400/404/500

**第二板斧：看后端日志（后端问题）**
- 请求到了没？→ 看 `INFO: 127.0.0.1 - "GET /api/..." 200 OK`
- 报了什么错？→ 看 `异常类型` 和 `异常信息`
- 堆栈在哪一行？→ 看 `File "...py", line XXX`

**第三板斧：加 print/console.log（万能但低效）**
- 后端：`print(f"DEBUG: workflow_id={workflow_id}, config={config}")`
- 前端：`console.log('DEBUG:', response.data)`

### 11.3 前端构建验证

```bash
# 在 frontend-sevice 目录下
npm run build    # TypeScript 编译 + 打包，有错会报出来
```

### 11.4 后端语法验证

```bash
# 在 backend-service 目录下
python -m py_compile api/workflows_enhanced.py   # 只检查语法，不运行
```

---

## 第十二部分：学习路线图

### 30 天学习计划（每天 30~60 分钟）

**第 1 周：Python + HTTP 基础（对应第二、三、四部分）**

| 天 | 内容 | 练习 |
|----|------|------|
| 1 | Python 函数、类、字典 | 读 `router.py` 全文，标注每个函数的输入输出 |
| 2 | Python 模块导入、列表推导式 | 读 `sub_agents.py`，画出四个子 Agent 的调用关系 |
| 3 | HTTP 方法、URL 结构、状态码 | 用浏览器 Network 面板抓 3 个请求，记录方法/URL/状态码 |
| 4 | FastAPI 路由、路径参数 | 在 `workflows_enhanced.py` 里找 5 个路由，写出完整 URL |
| 5 | Pydantic 模型 | 读 `algorithm_agent.py` 里的 `ChatRequest`，理解每个字段 |
| 6 | JSON 请求体和响应体 | 用 Swagger（`/docs`）手动调用 3 个接口 |
| 7 | 复习 + 填一份工程模板 | 用 `ENGINEERING_CONTRACT_TRACE_TEMPLATE.md` 记录本周学到的一个接口 |

**第 2 周：前端 + 前后端通信（对应第五、六部分）**

| 天 | 内容 | 练习 |
|----|------|------|
| 8 | React 组件、useState | 读 `AlgorithmAgentPage.tsx` 的前 100 行，标注所有 useState |
| 9 | useEffect、依赖数组 | 找到页面里的 useEffect，画出"什么变了会触发什么" |
| 10 | TypeScript 类型、interface | 读 `types/algorithm-agent.ts`，理解 OperationObservability |
| 11 | 前端 API 封装 | 读 `workflowEnhancedApi.ts`，对照后端路由 |
| 12 | 前后端全链路追踪 | 选一个按钮，从 onClick 追到后端函数再追回前端展示 |
| 13 | Network 面板实战 | 启动一次自动实验，在 Network 里找到所有相关请求 |
| 14 | 复习 + 填工程模板 | 记录"启动自动实验"的完整字段流转 |

**第 3 周：异步 + Agent（对应第七、八部分）**

| 天 | 内容 | 练习 |
|----|------|------|
| 15 | async/await 基础 | 读 `master_agent.py` 的 `process()` 方法 |
| 16 | 异步任务模式（启动/轮询/取消） | 在代码里找到 AutoResearch 的三个接口 |
| 17 | threading.Event 取消机制 | 追踪"停止自动实验"的信号传递链 |
| 18 | Agent 架构（Master + Sub） | 画出运营 Agent 的完整流程图 |
| 19 | 路由器（规则分 + LLM 分） | 读 `router.py` 全文，手算一个例子 |
| 20 | 依赖补全 | 用 DEPENDENCIES 字典，手动推导"用户说调优"时的执行计划 |
| 21 | 复习 + 填工程模板 | 记录运营 Agent 的一次完整执行链路 |

**第 4 周：LLM + LangGraph + 综合（对应第九、十部分）**

| 天 | 内容 | 练习 |
|----|------|------|
| 22 | LLM 调用模式 | 读 `llm_service.py`，理解 chat 方法 |
| 23 | Prompt 工程 | 读 `get_system_prompt()`，分析 prompt 结构 |
| 24 | 结构化 JSON 输出 | 读路由器里的 LLM 调用，理解 JSON 解析容错 |
| 25 | 经验库 + RAG | 读 `auto_research_memory_cases.json` 的结构 |
| 26 | LangGraph 概念 | 把你的 `process()` 方法画成状态图 |
| 27 | 对照 LangGraph 文档 | 读 LangGraph 官方 quickstart，和你的代码对比 |
| 28 | 综合实战 | 选一个你想加的小功能，从设计到实现走一遍 |
| 29 | 复习所有工程模板 | 回顾 4 份模板，看自己的理解是否加深 |
| 30 | 写一份"我学到了什么" | 用自己的话总结，不看教程 |

### 推荐学习资源

| 领域 | 资源 | 为什么推荐 |
|------|------|-----------|
| Python 基础 | [Python 官方教程](https://docs.python.org/3/tutorial/) | 权威、系统 |
| FastAPI | [FastAPI 官方文档](https://fastapi.tiangolo.com/) | 有中文，例子多 |
| React | [React 官方教程](https://react.dev/learn) | 2024 新版，概念清晰 |
| TypeScript | [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/) | 官方手册 |
| HTTP | [MDN HTTP 指南](https://developer.mozilla.org/zh-CN/docs/Web/HTTP) | 有中文 |
| LangGraph | [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/) | 概念 + 代码示例 |
| Agent 设计 | [LangChain Agent 文档](https://python.langchain.com/docs/modules/agents/) | 理解 Agent 范式 |

### 学习原则（从你的对话记录总结）

1. **先跑通再理解** — 你的风格是"先让它能用，再搞懂为什么"，这很好，但要补上"搞懂"这一步
2. **一次只追一条线** — 不要同时学 React + FastAPI + LangGraph，一周聚焦一个主题
3. **用你自己的项目练** — 不要去做无关的 todo-list 教程，直接在 AIP 里练
4. **每次改动填一份工程模板** — 这是你沉淀知识最有效的方式
5. **问"为什么"比问"怎么做"更重要** — 你已经在这样做了，继续保持

---

## 附录：术语速查表

| 英文 | 中文 | 在你项目里的含义 |
|------|------|-----------------|
| `async def` | 异步函数定义 | 后端接口函数，可以在等待 IO 时处理其他请求 |
| `await` | 等待（异步） | 等一个异步操作完成 |
| `router` | 路由器 | 把 URL 和处理函数绑定在一起 |
| `endpoint` | 端点/接口 | 一个具体的 API 地址 |
| `middleware` | 中间件 | 请求到达处理函数之前/之后的拦截层 |
| `state` | 状态 | React 组件里的可变数据 |
| `hook` | 钩子 | React 的 useState/useEffect 等 |
| `component` | 组件 | React 里的 UI 积木块 |
| `props` | 属性 | 父组件传给子组件的数据 |
| `callback` | 回调函数 | 事件发生时被调用的函数 |
| `polling` | 轮询 | 前端定期向后端查询状态 |
| `SSE` | Server-Sent Events | 服务器主动推送事件（你的流式对话用的） |
| `runtime` | 运行时 | 让一堆逻辑按顺序跑起来的执行引擎 |
| `schema` | 模式/结构定义 | 数据的"形状"描述 |
| `prompt` | 提示词 | 给 LLM 的指令 |
| `RAG` | 检索增强生成 | 先检索相关文档，再让 LLM 生成回答 |
| `checkpoint` | 检查点 | 保存中间状态，可恢复 |
| `evaluation_contract` | 评测量约 | 回测时两边必须一样的"尺子" |
| `structure_patch` | 结构补丁 | 对工作流图的节点开关改动 |
| `candidate_pool` | 候选池 | 存放优于 baseline 的实验结果 |
| `promote` | 晋升/上线 | 把候选模板设为生产模板 |

---

> 这份教程会随着你的学习持续更新。每次你问我一个新概念，我会建议你把它补到对应章节里。
