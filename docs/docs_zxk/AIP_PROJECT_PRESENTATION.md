# 工业AI算法平台（AIP）项目全面介绍

> 答辩版本 · 2026年7月
> 涵盖：项目定位 · 整体架构 · 核心模块详解 · 算法部署全流程 · AutoResearch系统

---

## 目录

1. [项目定位与价值](#一项目定位与价值)
2. [整体架构图](#二整体架构图)
3. [技术栈总览](#三技术栈总览)
4. [核心模块详解](#四核心模块详解)
5. [算法部署全流程精讲](#五算法部署全流程精讲)
6. [AutoResearch自主研究系统](#六autoresearch自主研究系统)
7. [关键数据模型字段流转](#七关键数据模型字段流转)
8. [Slot槽位概念详解](#八slot槽位概念详解)
9. [Scheduler调度系统详解](#九scheduler调度系统详解)
10. [Prelaunch预上线机制详解](#十prelaunch预上线机制详解)
11. [前后端交互链路](#十一前后端交互链路)
12. [我的贡献与成长](#十二我的贡献与成长)

---

---

## 一、项目定位与价值

### 一句话定义

**工业AI算法平台（AIP）** 是一个面向工业场景（电力预测、光伏故障诊断、负荷预测等）的 **全栈AI应用开发与运营平台**，让工程师可以在浏览器中完成：

> 选算法 → 拖拽编排工作流 → 自动调参 → 训练部署 → 精度监控 → 自动择优切换

### 核心解决的问题

| 传统痛点 | AIP解决方案 |
|---------|------------|
| AI算法需要懂代码才能用 | 可视化拖拽工作流，零代码上手 |
| 调参靠经验靠运气 | AutoResearch自动实验系统，系统化搜索最优配置 |
| 模型上线后精度下降无感知 | 自动精度监控 + 影子模型 + 自动择优切换 |
| 多个版本管理混乱 | Slot槽位 + 生产/影子/预上线三层状态机 |
| 每天需要手动触发训练 | Cron调度器自动滚动训练，严格Gap-One-Day约束 |

### 业务场景覆盖

```
新能源         电力负荷预测、光伏功率预测、风力发电预测
故障诊断       光伏组件故障分类（迭代标注闭环）
工业制造       设备预测性维护、质量控制
港口/楼宇      能耗预测、调度优化
```

---

---

## 二、整体架构图

### 系统层次图

```
┌──────────────────────────────────────────────────────────────┐
│                        用户浏览器                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │ 工作流   │ │ 算法部署 │ │ 精度运营 │ │  Research Cockpit│ │
│  │ 编辑器   │ │ 管理页面 │ │ 仪表盘   │ │  (AutoResearch)  │ │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘ │
└───────┼─────────────┼────────────┼─────────────────┼──────────┘
        │  HTTP/REST  │            │                 │
        ▼             ▼            ▼                 ▼
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI 后端 (port 8080)                   │
│  /api/workflows-enhanced  /api/deployment  /api/precision-ops│
│  /api/scheduler           /api/precision-ops/{slot}/prelaunch│
├──────────────────────────────────────────────────────────────┤
│                     Service 业务逻辑层                         │
│  SchedulerEngine  DeploymentSlotStore  KnowledgeLayer        │
│  AutoResearchCandidatePlanner  PeriodicReflection            │
│  operator_backends (XGBoost/LightGBM/CatBoost/Ridge/...)     │
├──────────────────────────────────────────────────────────────┤
│                       数据持久化层                             │
│  JSON文件(slots.json / tasks.json / candidate_pool.json)     │
│  SQLite (station_data / prediction_result / accuracy_metric) │
└──────────────────────────────────────────────────────────────┘
        │                          │
        ▼                          ▼
  APScheduler Cron         MockCompanyFeeder
  (每日自动训练/预测/回填)   (模拟生产数据入库)
```

### 模块关系图（Mermaid）

```mermaid
graph TB
    subgraph 前端页面
        WE[工作流编辑器]
        AD[算法部署页面]
        PO[精度运营页面]
        RC[Research Cockpit]
    end

    subgraph 后端API层
        WF_API[/workflows-enhanced/]
        DEPLOY_API[/deployment/]
        SCHED_API[/scheduler/]
        PO_API[/precision-ops/]
    end

    subgraph 核心Service层
        SE[SchedulerEngine<br/>APScheduler调度器]
        DSS[DeploymentSlotStore<br/>槽位持久化]
        SDE[SwitchDecisionEngine<br/>切换决策引擎]
        PLC[PrelaunchLifecycle<br/>预上线毕业判定]
        AR[AutoResearch主循环<br/>_run_autoresearch_task]
        KL[KnowledgeLayer<br/>知识层]
    end

    subgraph 算子层
        OPS[operator_backends<br/>XGBoost/LightGBM/CatBoost...]
    end

    WE --> WF_API
    AD --> DEPLOY_API
    AD --> SCHED_API
    PO --> PO_API

    DEPLOY_API --> DSS
    SCHED_API --> SE
    SE --> OPS
    DSS --> SDE
    PO_API --> PLC
    AR --> KL
    AR --> OPS
```

---

---

## 三、技术栈总览

### 前端技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| React | 18 | UI框架 |
| TypeScript | 5.x | 类型安全 |
| Ant Design | 5.x | UI组件库（按钮/表格/弹窗等） |
| React Flow | - | 工作流可视化画布（节点拖拽连线） |
| ECharts | - | 数据图表（折线图/散点图/精度曲线） |
| Zustand | - | 轻量状态管理 |
| Vite | - | 构建工具，开发时代理 `/api/*` 到后端 |

### 后端技术栈

| 技术 | 用途 |
|------|------|
| FastAPI | Web框架，自动生成Swagger文档 |
| Pydantic v2 | 数据模型定义与校验（BaseModel） |
| APScheduler | Cron定时任务调度 |
| SQLAlchemy | ORM，操作SQLite/MySQL |
| XGBoost / LightGBM / CatBoost | 主力预测模型 |
| scikit-learn | 特征工程、评估指标 |
| NetworkX | 工作流DAG拓扑排序、环检测 |
| hypothesis | 属性测试（PBT），100次迭代验证核心属性 |

### 项目目录结构

```
AIP/
├── backend-service/          ← 后端服务
│   ├── main.py               ← FastAPI入口，注册所有路由
│   ├── api/                  ← HTTP路由层（deployment/scheduler/precision_ops等）
│   ├── services/             ← 业务逻辑层
│   │   ├── deployment/       ← 部署核心（models/store/scheduler_engine/prelaunch等）
│   │   ├── scheduler/        ← APScheduler封装
│   │   ├── operator_backends/← 具体算子实现（xgboost_forecast/create_lag_features等）
│   │   ├── operator_execution/← 算子执行框架（data_adapter/global_config_injector等）
│   │   └── precision_ops/    ← 精度运营（accuracy_tracker/switch_engine/version_registry等）
│   ├── data/                 ← JSON持久化数据
│   │   ├── deployment/       ← slots.json / switch_log.json
│   │   ├── scheduler/        ← tasks.json
│   │   ├── autoresearch/     ← candidate_pool.json / candidate_verification_queue.json
│   │   └── workflows_enhanced/← 工作流模板JSON
│   └── configs/db.yaml       ← 数据库连接配置 + Cron表达式默认值
│
├── frontend-sevice/          ← 前端应用（注意：目录名是sevice，保持原样）
│   └── src/
│       ├── pages/            ← 页面组件
│       ├── components/       ← 可复用组件
│       ├── services/         ← API调用封装
│       └── types/            ← TypeScript类型定义
│
└── docs/specs/               ← 设计规范文档（每个spec一个子目录）
    ├── algorithm-deployment-refactor/
    ├── autoresearch-next-gen/
    └── prediction-workflow-auto-switch/
```

---

---

## 四、核心模块详解

### 4.1 可视化工作流编辑器

这是平台最核心的功能，用户通过拖拽把算法算子组合成 DAG（有向无环图）工作流。

**关键概念：**

```
节点（Node）     ← 画布上每个方块，对应一个算子（如xgboost_forecast）
边（Edge）       ← 节点之间的连线，表示数据流向
端口（Port）     ← 节点上的连接点，有类型约束（DataFrame/Model/Float等）
拓扑排序         ← 后端用NetworkX计算执行顺序，确保上游先执行
```

**工作流执行流程：**

```
用户点击"执行"
      │
      ▼
前端 POST /api/workflows-enhanced/{id}/execute
      │
      ▼
后端 WorkflowExecutor.execute(workflow_json)
      │
      ├── 1. 用NetworkX做拓扑排序（Kahn算法）
      ├── 2. 检测环路（有向环 = 非法）
      ├── 3. 按拓扑序逐节点执行
      │         ├── operator_execution/router.py 路由到对应算子后端
      │         ├── global_config_injector.py 注入全局配置（train_days等）
      │         └── data_adapter.py 处理跨节点数据格式转换
      └── 4. 返回每个节点的输出结果
```

**工作流JSON结构（简化版）：**

```json
{
  "id": "workflow-load-forecast-backtest-v3",
  "name": "负荷预测回测工作流",
  "nodes": [
    {
      "id": "node-load-csv",
      "functionId": "load_csv",
      "parameters": { "file_path": "../data/uploads/load_data.csv" }
    },
    {
      "id": "node-xgb-model",
      "functionId": "xgboost_forecast",
      "parameters": {
        "n_estimators": 300,
        "max_depth": 6,
        "learning_rate": 0.05
      }
    }
  ],
  "edges": [
    { "source": "node-load-csv", "target": "node-xgb-model" }
  ]
}
```

---

### 4.2 算子库（Operator Backends）

系统内置40+个算子，分布在 `backend-service/services/operator_backends/` 下，每个算子一个Python文件：

**数据类算子：**

| 算子 | functionId | 作用 |
|------|-----------|------|
| 数据加载 | `load_csv` | 读取CSV，支持相对路径自动搜索 |
| 数据库加载 | `load_database` | 从MySQL读取时序数据 |
| 异常检测 | `detect_outliers` | 标记异常值 |
| 缺失处理 | `handle_missing` | 插值填充 |
| 时间重采样 | `resample_timeseries` | 15min/1h等粒度转换 |

**特征工程算子：**

| 算子 | functionId | 作用 |
|------|-----------|------|
| 时间特征 | `extract_time_features` | 小时/星期/月份等 |
| 节假日特征 | `holiday_features` | 中国节假日标记 |
| 工作日特征 | `workday_features` | 工作日/休息日 |
| 滞后特征 | `create_lag_features` | lag-1/lag-96等 |
| 滚动统计 | `rolling_statistics` | 滚动均值/方差 |
| 差分特征 | `diff_features` | 一阶/二阶差分 |

**模型算子：**

| 算子 | functionId | 作用 |
|------|-----------|------|
| XGBoost预测 | `xgboost_forecast` | 训练+预测一体 |
| LightGBM预测 | `lightgbm_forecast` | 大数据集更快 |
| CatBoost预测 | `catboost_forecast` | 类别特征友好 |
| Ridge回归 | `ridge_forecast` | 线性基线 |
| 集成预测 | `ensemble_forecast` | 多模型加权融合 |
| 自动调参XGB | `auto_tune_xgboost` | 贝叶斯优化超参 |

**每个算子的标准接口：**

```python
class BaseOperator:
    def execute(self, inputs: Dict, parameters: Dict, context: Dict) -> Dict:
        """
        inputs     — 上游节点传入的数据（DataFrame/Model等）
        parameters — 用户在工作流编辑器里配置的参数
        context    — 全局执行上下文（训练窗口/slot/模型注册表等）
        """
        ...
```

---

---

## 五、算法部署全流程精讲

这是本次答辩的重点模块。完整链路：**模型训练 → 候选实验 → 复验 → 预上线 → 影子模型 → 生产切换**。

### 5.1 完整生命周期流程图

```
                    ┌─────────────────────────────┐
                    │     AutoResearch Run          │
                    │  (自动实验 N 轮)               │
                    └──────────────┬──────────────┘
                                   │ 每轮对比 Baseline/Challenger
                                   │ 精度更优 → 进入候选池
                                   ▼
                    ┌─────────────────────────────┐
                    │       候选池 Candidate Pool   │
                    │  candidate_pool.json         │
                    │  按MAPE改善降序排列            │
                    └──────────────┬──────────────┘
                                   │ 人工/自动选择强候选
                                   │ 点击"入复验"
                                   ▼
                    ┌─────────────────────────────┐
                    │  复验池 Verification Queue    │
                    │  多窗口回测验证（独立线程池）   │
                    │  结果：passed / failed        │
                    └──────────────┬──────────────┘
                                   │ passed → 可Promote
                                   ▼
                    ┌─────────────────────────────┐
                    │  预上线 Prelaunch             │
                    │  注册到DeploymentSlot         │
                    │  status="prelaunch"          │
                    │  观察期 N 天                  │
                    └──────────────┬──────────────┘
                                   │ 每日Cron回填精度
                                   │ evaluated_cycles++
                                   ▼
                         ┌─────────────────┐
                    ┌────┤  毕业条件检查    ├──────┐
                    │    │ prelaunch_mape  │      │
                    │    │ ≤ prod_mape×    │      │
                    │    │ (1+tolerance%)  │      │
                    │    └─────────────────┘      │
                    │ 达标(graduate)               │ 未达标(fail)
                    ▼                              ▼
         ┌─────────────────┐           ┌──────────────────┐
         │  影子模型 Shadow │           │  归档 retired     │
         │  status="shadow"│           │  status="retired" │
         │  精度评分降序排列│           └──────────────────┘
         └────────┬────────┘
                  │ 连续 switch_observation_days 天
                  │ MAPE优于生产模型
                  ▼
         ┌─────────────────┐
         │  生产模型 Prod   │ ◄── SwitchDecisionEngine决策
         │  status=         │     auto / manual 触发
         │  "production"    │     切换事件写入switch_log.json
         └─────────────────┘
                  │
                  │ 冷却期内精度下降
                  ▼
         ┌─────────────────┐
         │    一键回滚      │
         │ (rollback_of)   │
         └─────────────────┘
```

---

### 5.2 核心数据模型详解：models.py

文件位置：`backend-service/services/deployment/models.py`

这个文件定义了整个部署模块的数据骨架，共4个核心Pydantic模型：

#### PrelaunchMeta — 预上线专属元数据

```python
class PrelaunchMeta(BaseModel):
    candidate_id: str              # 来源候选ID，追溯AutoResearch候选池
    started_at: str                # 观察开始时间 ISO 8601
    observation_days: int          # 观察期天数 [1,90]，默认7天
    graduate_tolerance_pct: float  # 毕业容差%，默认5.0
                                   # 意思：允许prelaunch MAPE比生产高5%以内仍毕业
    evaluated_cycles: int          # 已评估天数（每日backfill后+1）
    baseline_mape_at_entry: float  # 入池时生产MAPE快照（审计用）
    current_rolling_mape: float    # 预上线当前滚动MAPE（每日更新）
    production_rolling_mape: float # 对应时期的生产滚动MAPE（对比基准）
    source_run_id: str             # 来源AutoResearch run ID（溯源）
    note: str                      # 人工备注
```

**关键字段流转**：`evaluated_cycles` 每天被 backfill cron 递增，当它达到 `observation_days` 时触发毕业判定。

#### ModelVersion — 模型版本

```python
class ModelVersion(BaseModel):
    workflow_id: str               # 对应的工作流模板ID（工作流JSON的id字段）
    version_tag: str               # 版本标签，人类可读，如"v2.1"
    status: str                    # "production"|"shadow"|"prelaunch"|"retired"
    deployed_at: str               # 部署/注册时间
    accuracy_score: float          # 最新精度评分（MAPE，越低越好）
    consecutive_better_days: int   # 连续优于production的天数（shadow专用）
    prelaunch_meta: PrelaunchMeta  # 预上线元数据（仅status=prelaunch时非空）
    source_run_id: str             # 来源实验run ID
    source_candidate_id: str       # 来源候选ID
```

**状态转换规则：**

```
status只能按以下路径转换：
  prelaunch → shadow    （毕业，promote_prelaunch_to_shadow）
  prelaunch → retired   （失败，fail_prelaunch）
  shadow    → production（切换，execute_switch）
  shadow    → retired   （手动退役或超出影子池上限）
  production→ shadow    （被新版本取代后降级）
  production→ retired   （手动退役）
  retired   → 终态（不可恢复）
```

---

#### DeploymentSlot — 部署槽位（最核心的模型）

```python
class DeploymentSlot(BaseModel):
    slot: str                        # 槽位名称（分区键），如"load_forecast"/"default"
    production_model: ModelVersion   # 唯一生产模型（可选）
    shadow_models: List[ModelVersion]   # 影子池，按accuracy_score降序排列
    prelaunch_models: List[ModelVersion] # 预上线池，每个独立与生产比
    
    # 资源上限
    max_shadow_slots: int = 3        # 影子池最大容量 [1,10]
    max_prelaunch_slots: int = 2     # 预上线池最大容量 [1,5]
    
    # 切换决策参数
    auto_switch_enabled: bool        # 是否启用自动切换（shadow→production）
    switch_observation_days: int = 7 # 切换观察天数：shadow连续多少天优于生产才切换
                                     # 旧字段名evaluation_window_days，兼容读取
    cooldown_hours: int = 48         # 切换后冷却期（小时内不允许再切）
    threshold_mape: float            # 精度阈值（低于此值触发回滚，可选）
    
    # 训练参数（新增）
    training_window_days: int = 30   # 训练窗口天数，与AutoResearch evaluation_contract.train_days对齐
    
    updated_at: str                  # 最后更新时间 ISO 8601
```

**Shadow vs Prelaunch 语义区分（重要）：**

```
Shadow（影子）：
  - 多个shadow之间互相竞争（锦标赛）
  - 需要连续switch_observation_days天MAPE优于生产，才建议切换
  - 同一时刻只有一个shadow最有机会升为production

Prelaunch（预上线）：
  - 每个prelaunch只跟生产模型独立比（不互相比）
  - 观察期满 + MAPE ≤ production_mape × (1 + tolerance%) → 毕业为shadow
  - 多个prelaunch可以同时并存，不互相影响
```

#### SwitchEvent — 切换事件日志（append-only）

```python
class SwitchEvent(BaseModel):
    event_id: str             # 事件唯一ID
    slot: str                 # 槽位名称
    trigger_type: str         # "auto"（自动）| "manual"（人工）
    switch_time: str          # 切换时间
    from_workflow_id: str     # 原生产workflow_id（被替换方）
    from_version_tag: str     # 原生产版本标签
    to_workflow_id: str       # 新生产workflow_id（替换方）
    to_version_tag: str       # 新生产版本标签
    pre_switch_mape: float    # 切换前生产MAPE（精度快照）
    post_switch_mape: float   # 切换后MAPE（后置评估时补写）
    reason: str               # 切换原因（人类可读）
    rollback_of: str          # 若为回滚，指向被回滚的event_id
```

**append-only语义**：`switch_log.json` 只追加，永不修改已有条目，是审计的"事实来源"。

---

### 5.3 数据持久化文件结构

```
backend-service/data/deployment/
├── slots.json          ← 所有槽位的当前状态快照
│                          结构: { "load_forecast": DeploymentSlot, "default": ... }
│                          每次切换/更新后原子覆写
└── switch_log.json     ← 切换事件审计日志（append-only列表）
                           结构: [SwitchEvent, SwitchEvent, ...]
```

**slots.json 内容示例：**

```json
{
  "load_forecast": {
    "slot": "load_forecast",
    "production_model": {
      "workflow_id": "workflow-load-forecast-training-v1",
      "version_tag": "v2.1",
      "status": "production",
      "accuracy_score": 4.21,
      "deployed_at": "2026-06-01T10:00:00"
    },
    "shadow_models": [
      {
        "workflow_id": "workflow-load-forecast-training-v2",
        "version_tag": "v2.2-shadow",
        "status": "shadow",
        "accuracy_score": 3.98,
        "consecutive_better_days": 5
      }
    ],
    "prelaunch_models": [
      {
        "workflow_id": "workflow-load-forecast-training-v3",
        "status": "prelaunch",
        "prelaunch_meta": {
          "candidate_id": "cand-abc123",
          "observation_days": 7,
          "graduate_tolerance_pct": 5.0,
          "evaluated_cycles": 3,
          "current_rolling_mape": 4.05,
          "production_rolling_mape": 4.21
        }
      }
    ],
    "auto_switch_enabled": true,
    "switch_observation_days": 7,
    "training_window_days": 30,
    "updated_at": "2026-07-06T10:00:00"
  }
}
```

---

---

## 六、AutoResearch自主研究系统

AutoResearch 是平台最复杂、最有技术深度的部分，经历了四代演进。

### 6.1 第四代架构概览（当前版本）

**核心思想**：把"人工调参"变成"AI自动实验"，系统像一个研究员一样：提出假设 → 实验验证 → 积累知识 → 反思迭代。

```
┌─────────────────────────────────────────────────────┐
│              AutoResearch 主循环                      │
│           _run_autoresearch_task (每轮)               │
│                                                       │
│  ① CandidatePlanner → 决定本轮探索方向                │
│     (parameter/feature/model/data/risk 五类方向)      │
│                                                       │
│  ② 生成参数/结构补丁(patch)                           │
│     规则候选 / GLM受控生成                            │
│                                                       │
│  ③ Baseline vs Challenger 多窗口回测对比              │
│     Baseline缓存(内容哈希) + 并行回测线程池            │
│                                                       │
│  ④ novelty_audit 新颖性审计                           │
│     基于patch_signature去重，防止重复实验              │
│                                                       │
│  ⑤ Evidence构建                                       │
│     windows_total / windows_challenger_better         │
│     failure_reason                                    │
│                                                       │
│  ⑥ KnowledgeLayer.ingest → 知识积累                   │
│                                                       │
│  ⑦ PeriodicReflection（每N轮）                        │
│     消费scoreboard+evidence+novelty → 策略决策        │
│                                                       │
│  ⑧ 候选池 → 复验池 → Promote                         │
└─────────────────────────────────────────────────────┘
```

### 6.2 候选规划器（CandidatePlanner）

**文件**：`backend-service/services/autoresearch_candidate_planner.py`

这个组件决定"每轮实验探索什么方向"：

```
batch_size >= 5 时：同一轮覆盖 parameter/feature/model/data/risk 五个方向
batch_size = 3 时：第一组parameter，第二组feature/model轮换，第三组data/risk轮换
batch_size = 2 时：第一组parameter，第二组选coverage_gap最大的方向
```

**PlannerScoreboardRow** — 每个方向的探索统计：

```python
{
    "attempts": int,         # 尝试次数
    "successes": int,        # 成功次数
    "failures": int,         # 失败次数
    "timeout_count": int,    # 超时次数
    "best_score_advantage": float,  # 最佳收益（MAPE改善）
    "negative_score_count": int,    # 负收益次数
    "ineffective_count": int,       # 无效尝试次数
    "coverage_gap": int,    # 与目标探索次数的差距
}
```

### 6.3 知识层（KnowledgeLayer）

**文件**：`backend-service/services/knowledge_layer.py`

**分层结构：**

```
L1 原始案例层  ← 单次实验结果原始记录，置信度0.2
L2 规律层      ← 多次实验支持的稳定规律，置信度0.5
L3 反模式层    ← 已被否证的配置模式，置信度0.8（负向知识）
L4 假设模板层  ← 高置信度的可复用实验模板，置信度1.0
```

**知识声明（KnowledgeClaim）字段：**

```python
{
    "claim_key": {
        "target_param": "train_days",      # 目标参数名
        "recommended_value": 45,           # 推荐值
        "direction": "increase",           # 方向：increase/decrease
        "metric": "mape"                   # 影响的评估指标
    },
    "claim": "train_days=45在高周期稳定性场景下优于30",
    "condition": { "seasonality_strength": ">0.7" },  # 生效条件
    "scenario_condition_hash": "a3f7c2d1e8b4",        # 场景指纹哈希
    "evidence": ["ares-008f5ad201c9", "ares-659af6a4"], # 支撑证据（run ID）
    "counter_evidence": [],                             # 反证
    "confidence": 0.85,  # 置信度（多证据支撑时>0.8，30天未验证衰减0.1）
    "knowledge_type": "causal_candidate",
    "status": "active",  # active/stale
    "layer": "L2"
}
```

### 6.4 证据强度与置信度层级（面试重点）

```
单窗口正收益    → 候选信号（不能直接沉淀为知识）
候选池候选      → 需要novelty_audit审计 + 复验通过
复验池passed    → 可以Promote进入prelaunch
active知识      → 需要多证据 + 场景匹配（多次跨run的多窗口确认）
promoted生产    → 只应来自复验通过的候选
```

> **📄 完整代际演进详见配套文档：`docs/specs/迭代历程详版.md`（900+行，含完整Mermaid流程图）**
> 涵盖 V1 六阶段详细过程（Stage 1-3 基础设施 → Stage 4 智能搜索 → Stage 4B 假设驱动 → Stage 4C 实验严格化 → Stage 5A/5B 跨run学习 → Stage 5 架构精炼）、V2 八大需求规划、V3 工程修复（10个独立服务拆分 + 持久化层）、V4 三链架构 + 50轮诚实复盘 + 6项代码修正、V6 画像驱动的五层闭环 + Research Action + 三级实验调度，以及 V4 vs V6 Planner 深入对比（答辩最容易被追问的点）。
> 
> **答辩时建议按"迭代历程详版"的第 7/8/9 章直接讲：代际演进对比表 + Planner 决策机制 + 答辩预案。**

### 6.5 AutoResearch状态字段说明

`run_state` 中关键字段（字段流转示意）：

```
iteration            当前轮次
best_mape            当前已知最优MAPE
baseline_mape        基线MAPE（固定参照）
latest_batch_groups  本轮batch的各组结果
  └── target_direction  探索方向
  └── patch_applied     应用的补丁
  └── challenger_mape   挑战者MAPE
  └── baseline_mape     基线MAPE（本窗口）
novelty_summary      本次run的新颖性审计摘要
exploration_health   
  └── scoreboard      各方向探索统计
  └── coverage_gap    方向覆盖缺口
evidence_summary     证据摘要
  └── windows_total             总评估窗口数
  └── windows_challenger_better 挑战者优于基线的窗口数
glm_meta
  └── glm_questioner_enabled   GLM是否启用
  └── question_source           问题来源
  └── disabled_reason           禁用原因（如无足够证据）
```

---

### 6.6 代际演进一句话总结

| 代际 | 一句话 | 关键问题 |
|------|--------|---------|
| **V1** | 自动调参器：能跑+会推理+有记忆 | 手工调参 → 系统自动搜索 |
| **V2** | 规划"会提问的研究员" | 被动试参 → 先提问再实验 |
| **V3** | 工程落地+Research OS方向 | 死锁/无断点/状态丢 → 持久化+服务化 |
| **V4** | 控制面重构：过程可观测 | 能力有了但过程是黑盒 → 五卡视图+三链架构 |
| **V6** | 画像/证据驱动：结论可信 | 过程质量≠结论质量 → Profile驱动+Evidence Ledger |
| **V7** | 平台级集成：算法生命周期工作台 | 独立工具 → 接入完整生命周期 |

贯穿始终的认知主线：**从"自动调参器"到"基于证据、由数据画像驱动的研究操作系统"。** 这不是一开始画好的蓝图，而是每一代用真实实验数据（尤其V4的50轮诚实复盘）逼出来的演进。

---

## 七、关键数据模型字段流转

这里用一个完整的"负荷预测模型从实验到上线"场景追踪所有字段的流向。

### 场景：AutoResearch发现更好配置 → 最终上线

**阶段1：实验产生候选**

```
AutoResearch Run (run_id="ares-9c429d5ed43c")
    │
    │  challenger_mape=3.98 优于 baseline_mape=4.21
    │  
    ▼
candidate_pool.json 新增一条：
{
    "candidate_id": "cand-af738bdd6c81",     ← 候选唯一ID
    "source_run_id": "ares-9c429d5ed43c",    ← 来源run
    "source_iteration": 23,                  ← 来源轮次
    "workflow_id": "workflow-...-backtest-v3",← 对应的回测模板
    "parameter_patch": {                      ← 参数补丁
        "node-xgb-model.n_estimators": 500,
        "node-xgb-model.max_depth": 8
    },
    "challenger_mape": 3.98,                 ← 挑战者精度
    "baseline_mape": 4.21,                   ← 基线精度
    "mape_improvement": 0.23,               ← MAPE改善值
    "status": "active"                       ← 候选状态
}
```

**阶段2：进入复验池**

```
用户点击"入复验"
    │
    ▼
candidate_verification_queue.json 新增：
{
    "item_id": "ver-af738bdd6c81",           ← 复验任务ID
    "candidate_id": "cand-af738bdd6c81",     ← 关联候选ID
    "source_run_id": "ares-9c429d5ed43c",    ← 溯源
    "source_iteration": 23,
    "verification_windows": 5,              ← 多窗口验证数
    "aggregate_method": "mean",             ← 聚合方式
    "status": "queued",                     ← queued→running→passed/failed
    "result": null
}
    │
    │  独立验证线程池（VERIFICATION_BACKTEST_WORKERS=1）
    │  与AutoResearch并行运行（不占用回测线程池）
    │
    ▼
completed_at记录，result更新为：
{
    "windows_total": 5,
    "windows_challenger_better": 4,    ← 4/5窗口挑战者更好
    "aggregate_mape_improvement": 0.19,
    "status": "passed"
}
```

**阶段3：Promote进预上线**

```
用户点击"Promote"（需status=passed，否则要force=true）
    │
    ▼
POST /api/deployment/slots/load_forecast/prelaunch
    │
    ▼
slots.json 的 load_forecast.prelaunch_models 新增：
{
    "workflow_id": "workflow-load-forecast-training-v2",  ← 新生成的训练模板
    "version_tag": "v2.2-from-cand-af738bdd",
    "status": "prelaunch",
    "prelaunch_meta": {
        "candidate_id": "cand-af738bdd6c81",
        "started_at": "2026-07-06T10:00:00",
        "observation_days": 7,           ← 观察7天
        "graduate_tolerance_pct": 5.0,   ← 允许MAPE比生产高5%以内
        "evaluated_cycles": 0,           ← 初始为0
        "baseline_mape_at_entry": 4.21,  ← 入池时生产MAPE快照
        "current_rolling_mape": null,    ← 待第一次回填后更新
        "production_rolling_mape": null,
        "source_run_id": "ares-9c429d5ed43c"
    }
}
```

**阶段4：每日Cron回填精度**

```
每天04:00触发 lf_accuracy_backfill Cron
    │
    │  计算所有模型（生产+影子+预上线）的滚动MAPE
    │
    ▼
调用 prelaunch_lifecycle.update_prelaunch_accuracy(slot_obj, accuracy_dict)
    │
    ├── current_rolling_mape = 4.05   ← 更新为最新MAPE
    ├── production_rolling_mape = 4.21 ← 同步更新生产MAPE
    └── evaluated_cycles += 1          ← 3→4→...→7（达到observation_days）
    │
    │  当 evaluated_cycles >= observation_days (7天)
    │
    ▼
check_graduation(prelaunch, production) 毕业判定：
    threshold = 4.21 × (1 + 5%/100) = 4.4205
    current_rolling_mape = 4.05 ≤ 4.4205
    → decision = "graduate" ✓
```

**阶段5：毕业为影子模型**

```
graduation decision="graduate"
    │
    ▼
store.promote_prelaunch_to_shadow("load_forecast", workflow_id)
    │
    ├── prelaunch_models 移除该条目
    ├── status 改为 "shadow"，清空 prelaunch_meta
    └── shadow_models 新增，按accuracy_score降序排列
    
slots.json 更新：
shadow_models[0] = { workflow_id: "...-v2", accuracy_score: 4.05, status: "shadow" }
```

**阶段6：影子模型积累 → 自动切换**

```
每日 backfill Cron 后调用 SwitchDecisionEngine.evaluate()
    │
    │ 检查 consecutive_better_days >= switch_observation_days (7)
    │
    ▼ 7天后
switch_log.json 追加：
{
    "event_id": "sw-evt-20260713-abc",
    "slot": "load_forecast",
    "trigger_type": "auto",
    "switch_time": "2026-07-13T04:30:00",
    "from_workflow_id": "workflow-...-training-v1",  ← 原生产
    "to_workflow_id": "workflow-...-training-v2",    ← 新生产
    "pre_switch_mape": 4.21,
    "reason": "影子v2连续7天MAPE(4.05)优于生产(4.21)"
}

slots.json 更新：
    原production → status="retired"
    shadow → status="production"
```

---

---

## 八、Slot槽位概念详解

Slot 是贯穿整个系统的核心分区概念，**不是本次新引入的**，而是复用系统已有的基础设施。

### 8.1 Slot在各模块的体现

```
数据库表：
  station_observations.slot = "load_forecast"  ← 数据源分区
  prediction_result.slot = "load_forecast"     ← 预测结果分区
  accuracy_metric.slot = "load_forecast"       ← 精度指标分区
  candidate_pool.slot = "load_forecast"        ← 候选池分区
  version_registry.slot = "load_forecast"      ← 版本注册表分区

JSON文件：
  data/deployment/slots.json → { "load_forecast": DeploymentSlot }
  data/scheduler/tasks.json → ScheduledTask.slot = "load_forecast"
  data/precision_ops/load_forecast/ ← 以slot命名的子目录

API路径：
  /api/deployment/slots/{slot}/switch
  /api/precision-ops/{slot}/versions
  /api/precision-ops/{slot}/leaderboard
```

### 8.2 Slot分区示例

```
系统中可以同时存在多个slot：

slot="load_forecast"    ← 负荷预测的独立模型管理
slot="pv_fault"         ← 光伏故障诊断的独立模型管理
slot="default"          ← 通用默认槽位
```

### 8.3 为什么用Slot

```
1. 多业务场景隔离：负荷预测的影子模型不会影响光伏预测的生产模型
2. 多区域/站点分区：不同地区的电力负荷模型独立管理
3. A/B测试基础：同一slot下生产+影子天然实现A/B
4. 调度任务绑定：ScheduledTask.slot决定训练哪个slot的模型
```

---

## 九、Scheduler调度系统详解

### 9.1 两套调度系统并存（历史原因）

```
老调度器（当前生产使用）：
  backend-service/services/scheduler/engine.py
  └── SchedulerEngine（基于APScheduler）
      ├── 每pipeline一个BackgroundScheduler实例
      ├── CronTrigger.from_crontab(cron_expr)
      ├── 防重叠保护：task运行中跳过新触发
      └── 失败重试：retry_delay秒后重试一次

新调度器（待接入生产）：
  backend-service/services/deployment/scheduler_engine.py
  └── SchedulerEngine（纯编排，依赖注入SchedulerPipeline协议）
      ├── 更严格的Gap-One-Day + compute_training_window
      ├── 结构化的TriggerResult返回
      └── 失败重试状态机（max_retries次后status="failed"）
```

### 9.2 老SchedulerEngine工作流程

```
start_pipeline("load_forecast")
    │
    │  注册所有属于此pipeline的task到BackgroundScheduler
    │  SchedulerEngine.start_pipeline → 启动APScheduler
    │
    ▼
每日 01:00 触发（configs/db.yaml: sched_lf_pull_cron="0 1 * * *"）
    │
    │  lf_data_pull task：
    │    1. MockCompanyFeeder.feed_next_batch() → 往station_observations写96行
    │    2. 或从生产MySQL拉取最新数据
    │
    ▼
每日 01:30 触发（sched_lf_predict_cron="30 1 * * *"）
    │
    │  lf_prediction task（当前训练+预测合并）：
    │    1. 取生产workflow + 最多3个影子workflow
    │    2. 各自跑完整workflow（含训练节点）
    │    3. 预测目标：last_ts + interval（T+1）
    │    4. 写PredictionResult到数据库
    │
    ▼
次日 03:00 触发（sched_lf_backfill_cron="0 3 * * *"）
    │
    │  lf_accuracy_backfill task：
    │    1. 读取昨天预测的T+1值（PredictionResult）
    │    2. 等待T+1实际值到达（station_observations）
    │    3. 计算MAPE/RMSE，写accuracy_metric
    │    4. 更新prelaunch_meta.current_rolling_mape
    │    5. 触发prelaunch毕业判定
    │    6. 触发shadow切换判定
```

### 9.3 ScheduledTask数据模型

文件：`backend-service/services/deployment/scheduler_models.py`

```python
class ScheduledTask(BaseModel):
    task_id: str          # 任务唯一ID，如"sched-lf-training-001"
    name: str             # 任务名称，人类可读
    pipeline: str         # 所属管线，如"load_forecast"
    schedule_type: str    # "rolling_daily"|"cron"|"interval"
    cron_expr: str        # Cron表达式，如"0 1 * * *"（每天01:00）
    trigger_time: str     # HH:MM格式，rolling_daily类型使用
    max_window_days: int  # 滚动训练窗口最大天数（None=不限）
    slot: str             # 关联的部署槽位名称
    status: str           # "running"|"stopped"|"failed"
    last_execution_time: str  # 上次执行完成时间
    last_result: str      # "success"|"failed"|"skipped"
    next_scheduled_time: str  # 下次预计触发时间
    retry_on_failure: bool    # 失败后是否重试
    max_retries: int          # 最大重试次数
    created_at: str
    updated_at: str
```

### 9.4 新SchedulerEngine：Gap-One-Day约束

这是防止数据穿越的核心设计：

```
T日触发调度：
  - 训练数据窗口：[ T - max_window_days, T-1 ] （严格截止前一天23:59:59）
  - 绝不使用T日任何数据（当天数据还在生成中）
  - 预测目标：T+1日（明天的值）
  - 精度评估：T+1日实际值到达后，回填T日触发的那次预测精度

时间链路：
  T-1日数据录入 → T日训练（用[T-max_window_days, T-1]数据）
              → 预测T+1值 → 保存到PredictionResult
              → T+1日实际值入库 → backfill计算精度

rolling_window.compute_training_window()函数：
  输入：trigger_date=T, max_window_days=365, available_dates=[...]
  输出：TrainingWindow {
      training_end = T - 1 day          # Gap-One-Day核心约束
      training_start = T - 365 days     # 最多用365天历史
      included_dates = [过滤后的日期列表]
      predict_target = T + 1 day        # 预测目标
      window_days = 实际使用天数
  }
```

---

---

## 十、Prelaunch预上线机制详解

### 10.1 为什么需要预上线层

```
传统流程：实验→直接上生产  （风险高，回滚成本大）

AIP三层缓冲：
  实验候选池 → 多窗口复验 → 预上线（真实数据观察期）→ 影子 → 生产

预上线的特点：
  - 使用真实每日生产数据（不是回测模拟数据）
  - 有独立的观察窗口（默认7天）
  - 毕业标准可配置（容差百分比）
  - 多个预上线并存互不干扰（各自只和生产比）
```

### 10.2 毕业判定逻辑

文件：`backend-service/services/deployment/prelaunch_lifecycle.py`

```python
def check_graduation(prelaunch, production) -> GraduationDecision:
    """
    三种判定结果：
    
    1. "continue" — 观察期未满，或精度数据不足
    2. "graduate" — 观察期满 + MAPE达标
       条件：prelaunch_mape ≤ production_mape × (1 + graduate_tolerance_pct/100)
       例：production=4.21%, tolerance=5% → threshold=4.4205%
           prelaunch=4.05% ≤ 4.4205% → graduate ✓
    3. "fail"    — 观察期满 + MAPE超标
       例：prelaunch=4.60% > 4.4205% → fail
    """
```

### 10.3 预上线观察期时序图

```
Day 0（Promote）:
  evaluated_cycles=0
  current_rolling_mape=null（还没数据）
  production_rolling_mape=null

Day 1（首次backfill后）:
  evaluated_cycles=1
  current_rolling_mape=4.18  ← 第一天真实数据
  production_rolling_mape=4.21

Day 3:
  evaluated_cycles=3
  current_rolling_mape=4.07  ← 滚动均值下降（模型更好）

Day 7（到达observation_days）:
  elapsed_days = 7 = observation_days
  threshold = 4.21 × 1.05 = 4.4205
  current_rolling_mape=4.05 ≤ 4.4205
  → decision="graduate" 🎓

调用 store.promote_prelaunch_to_shadow()
  → status从"prelaunch"变"shadow"
  → prelaunch_meta清空
  → 进入shadow_models，按accuracy_score降序排列
```

---

## 十一、前后端交互链路

### 11.1 典型API调用链路（以"触发切换"为例）

```
前端 AlgorithmDeploymentPage → ModelManagementTab
  用户点击"切换" → 弹窗确认
  │
  ▼ POST /api/deployment/slots/load_forecast/switch
  请求体：{
    "target_workflow_id": "workflow-load-forecast-training-v2",
    "trigger_type": "manual",
    "reason": "影子模型连续7天MAPE优于生产"
  }
  │
  ▼ api/deployment.py 路由处理
    validate slot 存在
    validate target_workflow_id 在 shadow_models 中
    检查冷却期（cooldown_hours）
  │
  ▼ SwitchDecisionEngine.execute_switch()
    1. 读取 slots.json
    2. 将影子模型 status 改为 "production"
    3. 将原生产模型 status 改为 "retired"
    4. 清空 consecutive_better_days
    5. 原子写回 slots.json
    6. SwitchEventLog.append(SwitchEvent) → 写 switch_log.json
  │
  ▼ 返回 200 OK + 更新后的 DeploymentSlot
  │
  ▼ 前端刷新模型管理卡片
```

### 11.2 前端API调用封装

文件：`frontend-sevice/src/services/deploymentApi.ts`

```typescript
// 部署API封装（与workflowEnhancedApi.ts风格一致）

export const deploymentApi = {
  // 获取所有槽位
  getSlots: () => api.get('/api/deployment/slots'),
  
  // 获取版本历史
  getVersions: (slot: string) => 
    api.get(`/api/deployment/slots/${slot}/versions`),
  
  // 执行切换
  switchModel: (slot: string, data: SwitchRequest) =>
    api.post(`/api/deployment/slots/${slot}/switch`, data),
  
  // 回滚
  rollback: (slot: string) =>
    api.post(`/api/deployment/slots/${slot}/rollback`),
  
  // 获取切换日志
  getSwitchLog: (slot: string) =>
    api.get(`/api/deployment/slots/${slot}/switch-log`),
  
  // 获取/更新配置
  getConfig: (slot: string) =>
    api.get(`/api/deployment/slots/${slot}/config`),
  updateConfig: (slot: string, config: SlotConfig) =>
    api.put(`/api/deployment/slots/${slot}/config`, config),
};
```

### 11.3 前端页面与后端路由对应关系

| 前端页面 | 组件文件 | 调用的后端API |
|---------|---------|--------------|
| 算法部署 - 模型管理 | `ModelManagementTab.tsx` | `/api/deployment/slots/*` |
| 算法部署 - 定时调度 | `SchedulerTab.tsx` | `/api/scheduler/tasks/*` |
| 算法部署 - 预上线 | `PrelaunchPanel.tsx` | `/api/precision-ops/{slot}/prelaunch*` |
| Research Cockpit | `WorkflowBaselineComparePage.tsx` | `/api/workflows-enhanced/auto-research/*` |
| 精度运营仪表盘 | `PrecisionOpsDashboardPage.tsx` | `/api/precision-ops/{slot}/*` |
| 工作流编辑器 | `WorkflowEditorPage.tsx` | `/api/workflows-enhanced/*` |

---

---

## 十二、我的贡献与成长

### 12.1 主导设计与实现的模块

#### 算法部署重构（算法部署 Spec）

**我解决的核心问题：** 原有系统中"生产模型"、"影子模型"、"调度任务"分散在不同页面，操作闭环不通。我主导设计并实现了完整的模型生命周期管理系统：

- **设计了PrelaunchMeta + ModelVersion + DeploymentSlot三层数据模型**，明确了prelaunch/shadow/production三个状态的语义边界
- **实现了Switch_observation_days切换观察机制**，避免单日异常触发切换
- **实现了原子写入（临时文件+os.replace）**，确保并发读取安全
- **解决了旧字段evaluation_window_days兼容问题**，用Pydantic AliasChoices实现向后兼容

**核心代码文件：**
- `services/deployment/models.py` — 部署数据模型全套定义
- `services/deployment/store.py` — 原子写入 + append-only日志
- `services/deployment/prelaunch_lifecycle.py` — 毕业判定逻辑
- `services/deployment/scheduler_engine.py` — 新调度引擎（Gap-One-Day）
- `services/deployment/scheduler_models.py` — 调度任务数据模型

#### AutoResearch系统演进（第三、四代）

**我参与的关键改进：**
- 修复CatBoost并发训练死锁（OMP_NUM_THREADS等线程数设为1）
- 实现Baseline缓存内容哈希（覆盖workflow内容/窗口/契约/配置）
- 实现`_build_candidate_novelty_audit`基于patch_signature去重
- 实现Evidence Contract字段：`windows_total`/`windows_challenger_better`/`failure_reason`
- 实现复验池与AutoResearch并行（独立`_VERIFICATION_BACKTEST_POOL`）
- 实现内存水位保护（macOS读`vm_stat`，Linux读`/proc/meminfo`）

#### 预上线迁移到算法部署

**背景问题：** 预上线功能原来埋在精度运营页面，和操作入口不在一起。

**解决方案：** 将`PrelaunchPanel`抽为独立组件，在算法部署页面新增预上线Tab，精度运营页面保留为"只读健康中心"（为后续根因分析留位置）。

### 12.2 技术成长点

```
1. Pydantic v2 的字段兼容迁移
   → 学会了AliasChoices、field_validator、model_copy等高级用法

2. 并发安全的文件写入
   → 理解了原子替换（临时文件+os.replace）的原理和必要性
   → 掌握了threading.Lock在Python多线程中的正确用法

3. APScheduler的生产级使用
   → 防重叠保护、失败重试、catch-up追赶
   → 每pipeline独立BackgroundScheduler实例

4. FastAPI路由设计
   → Pydantic请求/响应体定义
   → 错误处理（404/400/409 + 结构化错误码）
   → 依赖注入的使用

5. React + TypeScript 全栈开发
   → Ant Design 5组件的实际工程使用
   → Zustand状态管理
   → 与后端API的TypeScript类型对齐

6. 数据工程思维
   → Gap-One-Day数据穿越防护
   → 滚动训练窗口语义
   → MAPE/RMSE精度指标计算

7. 工程规范
   → 相对路径强制规范（跨Mac/Linux部署）
   → AI生成代码注解规范（@AI_GENERATED）
   → 交付前自审流程
```

### 12.3 项目整体规模

| 维度 | 数据 |
|------|------|
| 后端API端点 | 80+ |
| 算子后端 | 40+ |
| 前端页面 | 20+ |
| Spec设计文档 | 11个子系统 |
| 属性测试覆盖 | 10个核心Property |
| Pydantic数据模型 | 30+ |
| 代码行数（估计） | 50,000+ 行 |

---

## 附录：快速概念速查表

| 概念 | 一句话定义 | 所在文件 |
|------|-----------|---------|
| `Slot`（槽位） | 多业务/多场景分区键，如"load_forecast" | 贯穿全系统 |
| `PrelaunchMeta` | 预上线模型的观察期元数据 | `deployment/models.py` |
| `ModelVersion` | 一个工作流在slot中的状态实体 | `deployment/models.py` |
| `DeploymentSlot` | 一个slot的完整状态（prod+shadow+prelaunch） | `deployment/models.py` |
| `SwitchEvent` | append-only切换审计日志条目 | `deployment/models.py` |
| `ScheduledTask` | Cron调度任务配置 | `deployment/scheduler_models.py` |
| `SchedulerEngine` | APScheduler封装，per-pipeline独立实例 | `scheduler/engine.py` |
| `Gap-One-Day` | 训练数据严格截止T-1，不使用T日数据 | `deployment/rolling_window.py` |
| `CandidatePlanner` | 决定本轮AutoResearch探索方向 | `autoresearch_candidate_planner.py` |
| `KnowledgeClaim` | L1-L4分层知识声明 | `knowledge_layer.py` |
| `novelty_audit` | 基于patch_signature的候选去重 | `api/workflows_enhanced.py` |
| `consecutive_better_days` | shadow连续优于production的天数 | `deployment/models.py` |
| `switch_observation_days` | 切换决策需要的连续观察天数 | `deployment/models.py` |
| `graduate_tolerance_pct` | 预上线毕业时允许的MAPE容差% | `deployment/models.py` |
| `training_window_days` | 每日训练使用的历史数据天数 | `deployment/models.py` |

---

*文档生成时间：2026年7月6日*  
*基于：AIP项目代码库 + 设计规范 + 对话记录全面梳理*

---

## 十三、AutoResearch 并发设计详解

### 13.1 整体并发模型一览

AutoResearch 同时用了三层并发抽象，每层职责不同：

```
层级              抽象工具                   职责
─────────────────────────────────────────────────────────────────
进程层（最外层）   独立 Worker 进程            AutoResearch 主循环从 FastAPI 进程隔离出去
                  + SQLite job queue          FastAPI 只写队列/读快照，Worker 真正执行
─────────────────────────────────────────────────────────────────
线程层（中层）    asyncio.run() 在 daemon     每个 Worker 进程内，asyncio 主循环占主线程
                  线程里跑异步主循环          心跳线程 / 取消轮询线程独立运行
─────────────────────────────────────────────────────────────────
协程 + 线程池     asyncio.gather +            每一轮内多组 Challenger 并发对比
（最内层）        asyncio.Semaphore +         CPU 密集型回测（训练/评估）提交到 ThreadPoolExecutor
                  ThreadPoolExecutor          异步事件循环不阻塞，主循环状态机不卡住
─────────────────────────────────────────────────────────────────
```

---

### 13.2 进程层：FastAPI 进程 vs Worker 进程

**为什么要独立进程？**

AutoResearch 单次 run 可能跑数小时、消耗大量内存（多个 XGBoost/CatBoost 模型并训）。如果在 FastAPI 进程内直接跑，会：
- 阻塞 FastAPI 的 async event loop（即使用线程也会抢 CPU）
- FastAPI 重启/崩溃时 run 状态丢失
- 无法独立 kill 一个 run 而不影响其他 API 请求

**解决方案：SQLite Job Queue + 独立 Worker 进程**

```
┌───────────────────────────────────┐     ┌────────────────────────────────────┐
│  FastAPI 进程（uvicorn）           │     │  Worker 进程（python worker_autoresearch.py）│
│                                   │     │                                    │
│  POST /auto-research-async        │     │  while not shutdown:               │
│    → 生成 run_id                  │     │    job = jq.claim_job()            │
│    → jq.submit_job(run_id, payload)──SQLite──→ 领取 pending job               │
│    → 立即返回 {"run_id": ...}     │     │    _execute_job(job)               │
│                                   │     │      asyncio.run(_run_autoresearch) │
│  GET /auto-research-status/run_id │     │      每轮写 _snapshot → 磁盘       │
│    → 读磁盘 snapshot ←────────────────────── _snapshot_autoresearch_state()  │
│                                   │     │                                    │
│  POST /cancel run_id              │     │   每15秒：jq.heartbeat(run_id)     │
│    → jq.request_cancel(run_id) ──────→  │   每2秒检查：jq.is_cancel_requested│
└───────────────────────────────────┘     └────────────────────────────────────┘
```

**SQLite jobs 表关键字段：**

```
jobs 表
├── run_id TEXT PK                ← AutoResearch run 唯一标识
├── status TEXT                  ← pending / running / success / failed / cancelled / interrupted
├── pid INTEGER                  ← Worker 进程 PID（供 kill 用）
├── payload TEXT                 ← JSON：baseline_workflow_id/windows/search_space等
├── created_at / started_at / finished_at TEXT
├── heartbeat_at TEXT            ← Worker 每15秒更新；超过120秒未更新 = Worker 已死
└── cancel_requested INTEGER     ← FastAPI 写1；Worker 轮询检查后设置 cancel_event
```

**Worker 进程崩溃恢复：**

FastAPI 启动时调用 `jq.mark_dead_workers()`，把 `heartbeat_at < now - 120s` 的 running job 改为 `interrupted`。前端轮询到 interrupted 后可以触发 resume。

---

### 13.3 线程层：Worker 进程内的线程结构

`worker_autoresearch.py` 的 `_execute_job()` 函数启动后，进程内有以下线程：

```
Worker 进程（python worker_autoresearch.py）
│
├── 主线程
│     asyncio.run(_run_autoresearch_task(...))
│     └── asyncio event loop 在主线程独占运行
│           每一轮：生成 patch → 提交回测 → 等待结果 → 更新状态 → 快照
│
├── 心跳线程（daemon）
│     _heartbeat_loop(run_id, hb_stop_event)
│     每 15 秒：jq.heartbeat(run_id) 写 SQLite
│     作用：证明 Worker 还活着，防止 FastAPI 误判为 interrupted
│
└── 取消轮询线程（daemon）
      _cancel_checker()
      每 2 秒：jq.is_cancel_requested(run_id) 查 SQLite
      一旦发现 cancel_requested=1 → cancel_event.set()
      asyncio 主循环每轮检查 cancel_event → 安全退出
```

**线程间通信只通过两个机制：**
- `threading.Event` (`cancel_event`, `hb_stop`)：零数据竞争的轻量信号
- SQLite + `_lock`（threading.Lock）：跨进程的 job 状态同步

---

### 13.4 协程层：每轮内的并发回测

这是最复杂的一层，决定"一轮实验里多组 Challenger 如何并发执行"。

**核心代码流程：**

```python
# 1. 每轮启动时确定并发度
_batch_size = compare_config.get("batch_size", 1)  # 几组候选
_max_concurrent = min(_batch_size, compare_config.get("max_concurrent_batches", _batch_size))

# 2. 创建 asyncio 信号量（per-iteration，控制当前轮并发数）
_sem = asyncio.Semaphore(_max_concurrent)

# 3. 每组 Challenger 用一个 async 函数包裹
async def _run_one_batch(group_idx, cmp_id, ...):
    async with _sem:            # ← 拿到信号量才开始
        await asyncio.wait_for(
            _run_compare_backtest_batch_task(...),
            timeout=_group_timeout,   # ← 超时保护
        )

# 4. 所有组并发启动
await asyncio.gather(*[
    _run_one_batch(i, cid, bov, ...)
    for i, (cid, bov) in enumerate(_all_cmp_ids)
])
```

**两级信号量叠加（防止死锁）：**

```
全局信号量 _AUTORESEARCH_BACKTEST_ACTIVE_LIMIT（默认4）
  → 所有 run 共享，防止多个 run 同时跑时线程池耗尽

轮内信号量 _sem（= min(batch_size, max_concurrent_batches)）
  → 单个 run 单轮内，控制同时运行的 Challenger 组数
```

这两级形成漏斗：轮内并发受 `_sem` 限制，全局并发受 `_AUTORESEARCH_BACKTEST_ACTIVE_LIMIT` 限制。

---

### 13.5 线程池设计：两个独立的 ThreadPoolExecutor

```python
# AutoResearch 主回测线程池
_AUTORESEARCH_BACKTEST_ACTIVE_LIMIT = int(os.getenv("AUTORESEARCH_BACKTEST_ACTIVE_LIMIT", "4"))
_AUTORESEARCH_BACKTEST_POOL = ThreadPoolExecutor(
    max_workers=max(
        _AUTORESEARCH_BACKTEST_ACTIVE_LIMIT * 2,        # 至少是活跃限制的2倍
        int(os.getenv("AUTORESEARCH_BACKTEST_MAX_WORKERS", str(max(8, ... * 3))))
    ),
    thread_name_prefix="autoresearch-backtest",         # 线程名前缀，方便 htop 识别
)

# 复验池独立线程池（与 AutoResearch 完全资源分区）
_VERIFICATION_BACKTEST_WORKERS = int(os.getenv("VERIFICATION_BACKTEST_WORKERS", "1"))
_VERIFICATION_BACKTEST_POOL = ThreadPoolExecutor(
    max_workers=_VERIFICATION_BACKTEST_WORKERS,         # 默认1，不和 AutoResearch 抢
    thread_name_prefix="verification-backtest",
)
```

**为什么 max_workers 是 active_limit 的 2~3 倍？**

回测任务分两种状态：
- **running**：正在执行 XGBoost fit/predict（CPU 密集，活跃占用线程）
- **waiting**：等待 asyncio 信号量（已提交到线程池但在队列里等）

如果 max_workers == active_limit，所有 waiting 任务都会被拒绝提交（线程池满），导致 asyncio 的 `run_in_executor` 阻塞 event loop。多出来的线程数作为缓冲，让 waiting 任务能进队列等待信号量释放。

**复验池路由机制：**

复验回测任务需要走独立线程池。通过在 event loop 上打标记实现：

```python
# 复验线程启动时手动创建 event loop，并挂载标记
loop = asyncio.new_event_loop()
loop._verification_pool = _VERIFICATION_BACKTEST_POOL  # ← 自定义属性

# _run_limited_backtest 路由逻辑
async def _run_limited_backtest(fn, *args):
    async with sem:
        loop = asyncio.get_running_loop()
        pool = getattr(loop, "_verification_pool", None) or _AUTORESEARCH_BACKTEST_POOL
        #      ↑ 有标记 → 走复验池；无标记 → 走主回测池
        return await loop.run_in_executor(pool, fn, *args)
```

---

### 13.6 CPU 密集型任务的 async 化

Python 的 asyncio event loop 是单线程的——如果直接在协程里调 `model.fit()`，整个 event loop 会卡住，所有其他协程（包括状态快照、cancel 检查）都无法运行。

**解决方式：`asyncio.to_thread()` 和 `loop.run_in_executor()`**

```python
# 方式 A：asyncio.to_thread（Python 3.9+）
candidate_result = await asyncio.to_thread(
    _execute_backtest_reference,    # ← 同步函数（真正跑回测）
    workflow,
    backtest_params,
    global_config,
    cancel_event,
)

# 方式 B：run_in_executor（指定线程池）
result = await loop.run_in_executor(
    _AUTORESEARCH_BACKTEST_POOL,    # ← 自定义线程池
    _execute_backtest,              # ← 同步函数
    workflow, params, ...
)
```

两者都把同步的 CPU 密集函数投入线程池，主协程只是 `await` 等结果，event loop 期间可以继续运行其他协程。

---

### 13.7 CatBoost 并发死锁修复

**问题根因：**

macOS 的 libomp（OpenMP 运行时）在 ThreadPoolExecutor 里被多个线程同时 `import catboost` 或初始化训练时，会发生 OMP lock 死锁——内部互斥量争抢导致所有训练线程永久挂起。

**修复方案：** 在 `reference_rolling_backtest/models.py` 模块顶层（import numpy 之前）强制设置所有 BLAS/OpenMP 线程数为 1：

```python
# models.py 模块顶部（在任何 import numpy/xgboost/catboost 之前）
import os as _osb
for _k, _v in [
    ("OMP_NUM_THREADS",       "1"),
    ("OPENBLAS_NUM_THREADS",  "1"),
    ("MKL_NUM_THREADS",       "1"),
    ("VECLIB_MAXIMUM_THREADS","1"),
    ("NUMEXPR_NUM_THREADS",   "1"),
]:
    _osb.environ.setdefault(_k, _v)
```

**为什么 setdefault 而不是直接赋值？**

`setdefault` 只在环境变量不存在时才设置，不覆盖用户可能通过环境变量显式指定的值（如生产环境上 `OMP_NUM_THREADS=4`）。

**贝叶斯优化也需要加锁：**

`bayes_opt` 的 `BayesianOptimization.maximize()` 内部调用 scipy 的优化器，也不是线程安全的。修复方案是加一把进程内锁，并设置超时防止永久等待：

```python
_BO_LOCK = threading.Lock()

def _bo_maximize_safe(bo, init_points, n_iter):
    acquired = _BO_LOCK.acquire(timeout=300)  # 最多等300秒
    if not acquired:
        logger.warning("_BO_LOCK timeout 300s - running unprotected")
    try:
        bo.maximize(init_points=init_points, n_iter=n_iter)
    finally:
        if acquired:
            _BO_LOCK.release()
```

---

### 13.8 内存水位保护

复验池与 AutoResearch 并行时，系统内存可能被多个模型训练同时耗尽。启动复验前做 best-effort 内存检查：

```python
_VERIFICATION_MIN_AVAILABLE_MEM_MB = int(os.getenv("VERIFICATION_MIN_AVAILABLE_MEM_MB", "1024"))

def _read_available_memory_mb() -> Optional[int]:
    if sys.platform.startswith("linux"):
        # 读 /proc/meminfo 的 MemAvailable 字段
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(int(line.split()[1]) / 1024)

    if sys.platform == "darwin":
        # macOS: vm_stat 输出解析空闲页数
        output = subprocess.check_output(["vm_stat"], text=True, timeout=2)
        # 计算 Pages free + Pages speculative + Pages purgeable
        available_pages = ...
        return int(available_pages * page_size / 1024 / 1024)
```

触发逻辑：若可用内存 < `VERIFICATION_MIN_AVAILABLE_MEM_MB`（默认1024MB），返回 `resource_pressure`，拒绝启动新复验任务。`force=true` 可绕过，`VERIFICATION_MIN_AVAILABLE_MEM_MB=0` 可禁用检查。

---

### 13.9 完整并发架构图（综合）

```
用户点击"开始AutoResearch"
        │
        ▼
FastAPI async 路由（uvicorn event loop，主进程）
  start_auto_research()
  ├── 预检 workflow preflight
  ├── 初始化 _auto_research_store[run_id] 内存状态
  ├── jq.submit_job(run_id, payload) → 写 SQLite jobs 表
  └── 返回 {"run_id": "ares-xxx", "status": "pending"}
        │
        │（FastAPI 进程不再参与实际计算）
        │
        ▼
Worker 进程（python worker_autoresearch.py --loop）
        │
        ├── jq.claim_job() → 从 SQLite 领取 pending job
        │
        ├── 主线程：asyncio.run(_run_autoresearch_task)
        │     │
        │     │  for iteration in range(max_iterations):
        │     │
        │     │    ① CandidatePlanner.build_slots(batch_size=N)
        │     │       → 确定本轮 N 组各自的探索方向
        │     │
        │     │    ② 生成各组参数/结构补丁
        │     │
        │     │    ③ 先跑 Baseline（缓存命中则跳过）
        │     │       await loop.run_in_executor(
        │     │           _AUTORESEARCH_BACKTEST_POOL,
        │     │           _execute_backtest_reference, ...
        │     │       )
        │     │
        │     │    ④ 并发跑 N 组 Challenger
        │     │       _sem = asyncio.Semaphore(max_concurrent)
        │     │       await asyncio.gather(*[
        │     │           _run_one_batch(i, ...)  # 各组
        │     │           for i in range(N)
        │     │       ])
        │     │       每个 _run_one_batch：
        │     │         async with _sem  ← 限流
        │     │           await _run_limited_backtest(fn, ...)
        │     │             async with global_sem  ← 全局限流
        │     │               await loop.run_in_executor(
        │     │                   _AUTORESEARCH_BACKTEST_POOL,  ← 线程池
        │     │                   _execute_backtest_reference, ...
        │     │               )
        │     │         每个回测函数内：
        │     │           ├── _bo_maximize_safe()（加 _BO_LOCK）
        │     │           └── model.fit()（BLAS 线程数已设1，不死锁）
        │     │
        │     │    ⑤ 评估结果 → novelty_audit → evidence_build
        │     │    ⑥ KnowledgeLayer.ingest_run_insight()
        │     │    ⑦ _snapshot_autoresearch_state(run_id) → 写磁盘
        │     │    ⑧ cancel_event 检查（Worker 取消轮询线程每2秒触发）
        │     │
        │
        ├── 心跳线程（daemon，每15秒）
        │     jq.heartbeat(run_id) → 更新 SQLite heartbeat_at
        │
        └── 取消轮询线程（daemon，每2秒）
              jq.is_cancel_requested(run_id)
              → 若收到取消信号：cancel_event.set()
              → 主循环检测后安全退出，写最终状态

复验池（与上述并行，不共享线程池）
        ├── threading.Thread(target=_run_verification_item_thread, daemon=True)
        │     ├── 手动创建独立 event loop
        │     │     loop = asyncio.new_event_loop()
        │     │     loop._verification_pool = _VERIFICATION_BACKTEST_POOL ← 路由标记
        │     └── loop.run_until_complete(_run_compare_backtest_batch_task)
        │           内部 _run_limited_backtest 检测到标记 → 走 _VERIFICATION_BACKTEST_POOL
        │
        └── 内存水位检查（启动前）
              _read_available_memory_mb() < 1024MB → 返回 resource_pressure 拒绝启动
```

---

### 13.10 关键参数速查（全部可通过环境变量调整）

| 环境变量 | 默认值 | 含义 |
|---------|--------|------|
| `AUTORESEARCH_BACKTEST_ACTIVE_LIMIT` | `4` | 全局最大并发回测数（asyncio 信号量上限） |
| `AUTORESEARCH_BACKTEST_MAX_WORKERS` | `max(8, limit×3)` | 主回测线程池 max_workers |
| `VERIFICATION_BACKTEST_WORKERS` | `1` | 复验线程池 max_workers（独立，不和主池共享） |
| `VERIFICATION_MIN_AVAILABLE_MEM_MB` | `1024` | 启动复验前最低可用内存(MB)；设0禁用检查 |
| `compare_config.batch_size` | `1` | 每轮并发 Challenger 组数 |
| `compare_config.max_concurrent_batches` | `= batch_size` | 每轮内真正同时运行的组数上限（轮内信号量） |
| `_HEARTBEAT_INTERVAL`（代码常量） | `15` 秒 | Worker 心跳写入间隔 |
| `_HEARTBEAT_TIMEOUT_SECONDS`（代码常量） | `120` 秒 | 超时多久判 Worker 死亡 |
| `_POLL_INTERVAL`（代码常量） | `3` 秒 | Worker 轮询 job queue 的间隔（--loop 模式） |

---

## 十四、光伏故障诊断流水线（pv-fault-diagnosis-integration）

### 14.1 背景与设计思路

这个模块解决的问题是：把现有的光伏故障诊断算法（`fault-diag-algo-release-3.1`，一套独立的Python脚本）**移植进AIP平台的通用算子体系**，让它可以像搭积木一样在工作流编辑器里运行。

核心设计理念：**复用优先 + 最小扩展**

```
814个已有算子中能复用 9 个
  → 5 个只需填充后端实现（已注册但后端为空）
  → 4 个已有算子需扩展新方法

真正新增注册的算子只有 3 个：
  time_window_split    ← 原算法独有的诊断窗口切分逻辑
  ts_comparison_features ← 多变量对比特征（Spearman/DTW等）
  batch_predict_classifier ← 批量分批预测+失败重试编排
```

**与负荷预测集成的关键差异：**

| 维度 | 负荷预测 | 光伏故障诊断 |
|------|---------|-------------|
| 任务类型 | 回归（连续值） | 分类（多类别故障） |
| 数据粒度 | 单时间序列 | 多设备/多支路批量时序 |
| 特征工程 | 滚动统计+滞后特征 | 窗口聚合统计+多变量对比+tsfresh |
| 特征选择 | 无（全量） | mRMR Top-K |
| 类别平衡 | 不需要 | SMOTE 过采样 |
| 模型 | XGBoost 回归 | 随机森林分类 |
| 评估指标 | SMAPE/MAE/RMSE | Accuracy/Precision/Recall/F1 |

---

### 14.2 光伏设备层级与诊断单元

```
设备层级（Device_Hierarchy）：
  site_id（电站）→ device_id（汇流箱/逆变器）→ branch_id（支路，可选）

诊断单元（Diagnosis_Unit）：
  一个「设备 × 时间窗口」的组合
  如：site_A / device_12 / branch_3 / 2026-06-01（周一整天）

诊断窗口（Diagnosis_Window）：
  将连续时序数据按固定周期切分的粒度
  默认 1d（每天诊断一次），也支持 1w / 12h
```

---

### 14.3 训练流水线详解（13节点）

```
load_csv（源数据）  +  load_csv（标签数据）
        │
        ▼
label_encode（mode='encode'）
  ← 业务标签"suite-0" → 整数20，维护 label_map
        │
        ▼
time_window_split（window='1d'）    ← 新算子 ①
  ← 每条记录分配 time_window 列
  ← 按设备分组，resampling 分配窗口
        │
        ▼
handle_missing（method='drop_insufficient', keep_threshold=0.75）
  ← 扩展方法：有效数据不足75%的设备×窗口组直接丢弃
  ← 移植自原算法 DataCleaner.check_missing()
        │
        ▼
detect_outliers（method='robust_clip'）
  ← 扩展方法：按差分排序后去除首尾极值
  ← 仅在组内数据量 > 24 时执行
  ← 移植自原算法 DataCleaner.get_robust_data()
        │
        ├──────────────────────────────┐──────────────────────────┐
        ▼                              ▼                          ▼
extract_statistical_features    tsfresh_extract          ts_comparison_features   ← 新算子 ②
（mode='groupby_aggregate'）    （分组模式扩展）          多变量两两对比特征
max/min/mean/std/kurtosis/skew  abs_energy/benford等     Spearman/Pearson/DTW
量化/自相关/差分统计              tsfresh 特征            欧氏距离/回归斜率/差值统计
        └──────────────────────────────┘──────────────────────────┘
                                       │
                                       ▼（三路特征合并）
                              feature_select（method='mrmr', k=50, mode='fit'）
                              ← 扩展方法：mRMR最小冗余最大相关
                              ← 从高维特征中选Top-50个最有价值特征
                              ← 返回 feature_list 供预测时复用
                                       │
                                       ▼
                              smote_oversample（limit=500）
                              ← 填充后端：解决类别不平衡
                              ← 少数类最多合成500个样本
                                       │
                                       ▼
                              random_forest_classifier（n_estimators=80, mode='train'）
                              ← 填充后端：sklearn RandomForestClassifier
                                       │
                          ┌────────────┴────────────┐
                          ▼                         ▼
                   precision_recall_f1          confusion_matrix
                   ← 填充后端：macro P/R/F1     ← 填充后端：混淆矩阵
```

---

### 14.4 三个新增算子的技术细节

#### ① time_window_split — 时间窗口切分

```python
# 核心逻辑（移植自原算法 utils/time.py 的 set_time_window）
def execute(params, inputs):
    window = params["window"]  # 如 "1d", "1w", "12h"
    id_fields = params.get("id_fields", ["site_id", "device_id", "branch_id"])
    
    # 自动检测实际存在的 id_fields（无 branch_id 时忽略）
    actual_fields = [f for f in id_fields if f in df.columns]
    
    # 按设备分组，用 pandas resample 分配时间窗口标签
    for key, group in df.groupby(actual_fields):
        resampled = group.resample(freq, label='left').asfreq()
        resampled['time_window'] = resampled.index
        # merge_asof 将每条记录关联到其所属窗口
        ...
    
    # 输出：原始 DataFrame + 新增 time_window 列
```

**与已有 sliding_window 的区别：**
- `sliding_window`：滑动窗口，用于生成样本序列（重叠窗口）
- `time_window_split`：固定周期分组，用于诊断单元切分（无重叠）

#### ② ts_comparison_features — 多变量对比特征

```python
# 核心逻辑（移植自 features/feature_engineer.py 的 get_compare_features）
def execute(params, inputs):
    value_fields = params["value_fields"]  # 如 ["current_1","current_2","current_3"]
    
    # 对所有变量两两组合（n*(n-1)/2 对）
    for col1, col2 in itertools.combinations(value_fields, 2):
        row[f'{col1}_{col2}_spearman'] = spearmanr(g[col1], g[col2])[0]
        row[f'{col1}_{col2}_pearson']  = pearsonr(g[col1], g[col2])[0]
        row[f'{col1}_{col2}_euclidean']= np.linalg.norm(g[col1] - g[col2])
        row[f'{col1}_{col2}_dtw']      = dtw(g[col1].values, g[col2].values)
        row[f'{col1}_{col2}_slope']    = _linear_slope(g[col1], g[col2])
        diff = g[col1] - g[col2]
        row[f'diff_{col1}_{col2}_max/std/median'] = diff统计
    
    # 输出：每行一个设备×窗口，列为对比特征
```

**工程价值**：多路光伏支路的电流本应高度相关，异常设备表现为相关性骤降或距离异常增大，这些特征直接捕捉了故障的物理信号。

#### ③ batch_predict_classifier — 批量分类预测

```python
# 核心逻辑（移植自 fault_main.py 批量预测循环）
def execute(params, inputs):
    batch_size = params.get("batch_size", 10000)
    
    # 分批处理所有设备
    for start in range(0, total, batch_size):
        batch_ids = unique_ids[start:start+batch_size]
        try:
            preds = model.predict(batch_df)
            results.append(batch_result)
        except Exception:
            failed_ids.extend(batch_ids)
    
    # 失败批次：退回逐条重试
    for obj_id in failed_ids:
        try:
            pred = model.predict(features_df.loc[[obj_id]])
            results.append(...)
        except Exception:
            failure_count += 1
    
    # 返回 predictions（id_fields + predict_label）+ failure_count
```

---

### 14.5 数据流契约（算子间Schema）

```
阶段                          输出格式
────────────────────────────────────────────────────────────
load_csv → label_encode       MATRIX: time/site_id/device_id/[branch_id]/custom_label_id/values
label_encode → time_window    MATRIX: 同上 + label(int)，去除原始标签列
time_window → handle_missing  MATRIX: 同上 + time_window(datetime)
handle_missing → detect       MATRIX: 已丢弃不足组的行
detect → 特征算子（3路）      MATRIX: 极值已替换为NaN的时序数据
特征算子 → feature_select     MATRIX: index=MultiIndex(id_fields), cols=特征名, +label列
feature_select → smote        OBJECT: {selected_features(MATRIX), target(ARRAY,int), feature_list(LIST)}
smote → random_forest         OBJECT: {features(MATRIX), target(ARRAY,int)}
random_forest → 评估算子      OBJECT: {model, predictions(ARRAY,int), y_true(ARRAY,int), feature_importances}
```

---

### 14.6 预测流水线（7节点，利用训练产物）

```
load_csv → time_window_split → handle_missing → detect_outliers
         → [3路特征提取（复用训练时相同算子）]
         → feature_select（mode='transform', feature_list=[...]）
           ← 不重新fit，直接用训练时保存的 feature_list
         → batch_predict_classifier（model=已训练模型）
         → label_encode（mode='decode'）
           ← 整数20 → 业务标签"suite-0"
```

**关键设计**：`feature_select` 的 `fit/transform` 两种 mode 确保预测时特征空间与训练完全对齐，不会因为数据分布不同而产生特征不一致。

---

---

## 十五、光伏故障人机协同迭代标注闭环（pv-fault-iterative-labeling-loop）

这个模块建立在光伏故障诊断流水线之上，是一个**编排层**，解决的核心问题是：**标注数据不足 + 新故障类型不断涌现** 时，如何通过人机协同让模型越来越好。

### 15.1 系统定位

```
不做的事（复用已有）：
  - 模型训练、特征工程、切分算法 ← 全部委托给光伏故障诊断流水线
  - 数据加载、标签编解码           ← 复用 load_csv / label_encode 算子
  - LLM 配置管理                  ← 复用 api/llm_config.py

做的事（新增编排层）：
  - 闭环状态机（trained→predicted→reviewing→reviewed→backfilled）
  - 人工审核窗口（前端页面）
  - LLM辅助打标（建议，不写真值）
  - 三方精度实时对比
  - 标签注册表版本管理
  - 打标数据回流为新训练集
  - 迭代历史追踪
  - 存储抽象层（文件/JSON实现，预留DB）
```

---

### 15.2 完整闭环流程图

```
有真值数据集
     │
     ▼  POST /loops/{id}/train
┌──────────────────────────────────────┐
│  Loop_Orchestrator 触发              │
│  workflow-pv-fault-diag-quickval-cv  │  ← 调用已有训练评估工作流
│  内部跑 stratified_cv_eval 算子      │  ← 重复分层留出（n_repeats=10）
│  输出：macro_f1_mean ± std           │
│  登记 Model_Artifact（model_ref）    │
│  stage: trained                     │
└──────────────────────────────────────┘
     │
     ▼  POST /loops/{id}/predict（显式 model_ref，禁止隐式重训）
┌──────────────────────────────────────┐
│  触发 workflow-pv-fault-diag-pred    │  ← 调用已有预测工作流
│  每个设备×窗口 → Classifier_Prediction│
│  stage: predicted                   │
└──────────────────────────────────────┘
     │
     ▼  POST /review-sessions
┌──────────────────────────────────────┐
│  Review_Session 装配                 │
│  ├── 逐诊断单元加载待审核条目         │
│  └── 异步生成 LLM_Suggestion         │  ← 复用 api/llm_config.py 默认LLM
│  stage: reviewing                   │
└──────────────────────────────────────┘
     │  用户逐条审核（前端 IterativeLabelingReviewPage.tsx）
     │  四类动作：confirm / correct / new_label / skip
     │  每条 Human_Verdict 触发 Accuracy_Evaluator 增量更新
     │
     ▼  POST /loops/{id}/backfill
┌──────────────────────────────────────┐
│  Backfill 服务                       │
│  ← 取 confirm/correct/new_label 单元 │
│  ← 排除 pending（skip的不进回流）     │
│  ← 可选与上轮数据集累积合并           │
│  分配新 dataset_version              │
│  stage: backfilled                  │
└──────────────────────────────────────┘
     │
     ▼（进入下一轮，标签更多 + 样本更多 + 精度更高）
```

---

### 15.3 核心概念精讲

#### Diagnosis_Unit（诊断单元）

```
unit_key = "siteA|dev12|br3|2026-06-01"
           = site_id | device_id | branch_id | time_window
这是整个系统最小操作粒度：预测/审核/真值固化都以此为单位
```

#### 审核四类动作

| 动作 | 含义 | 写入真值 | 进入回流 |
|------|------|---------|---------|
| `confirm` | 确认分类器预测正确 | ✅ is_ground_truth=true | ✅ |
| `correct` | 纠正为注册表已有标签 | ✅ is_ground_truth=true | ✅ |
| `new_label` | 发现新故障类型，扩充标签 | ✅ is_ground_truth=true | ✅ |
| `skip` | 存疑，本次跳过 | ❌ pending | ❌ |

**核心设计原则**：真值唯一来源是 `Human_Verdict`，LLM和分类器都只是建议。

#### LLM_Suggestion — 双来源并列

```
前端展示（每个诊断单元）：
┌─────────────────────┬──────────────────────────────┐
│  分类器预测          │  LLM 建议                    │
│  predicted_label: 1 │  suggested_label: 1          │
│  confidence: 0.87   │  reason: "电流曲线在午后骤降  │
│  [辅助建议]         │   且与相邻支路背离，疑似组串失配│
│                     │  [辅助建议]                  │
└─────────────────────┴──────────────────────────────┘
                 ↓ 双来源一致 → 正常展示
                 ↓ 双来源分歧 → 高亮提醒 ← disagreement=true

审核人点击其中一个或手动输入 → Human_Verdict
```

**LLM越界处理**：若LLM给出的标签不在Label_Registry中，标记 `out_of_registry=true`，不自动采纳，提示人工是否扩充注册表。

---

### 15.4 Label_Registry — 标签注册表设计

**设计难点**：历史已标注的真值依赖 `label_id` 编码，一旦重编号历史数据就失真。

```python
# label_id 分配规则：单调递增，永不复用
def allocate_label(label_name):
    new_id = max(现有 label_id) + 1  # 永远是最大值+1
    生成新 label_space_version
    保留历史快照（append-only）
    不改变任何已有 label_id 的映射

# 典型演进
ls-v1: {0:"正常", 1:"组串失配"}
ls-v2: {0:"正常", 1:"组串失配", 20:"suite-0"}  ← 新增label_id=20（跳号是允许的）
ls-v3: {0:"正常", 1:"组串失配", 20:"suite-0", 21:"逆变器过热"}
```

**与 label_encode 算子的兼容**：Label_Registry 维护的 `label_map` 格式与 `label_encode` 完全对齐：
```json
{
  "label_map": {"正常": 0, "组串失配": 1, "suite-0": 20}
}
```

**标签空间落后检测**：若已训练模型的 `label_space_snapshot` 落后于注册表当前版本（中间有新增标签），则标记 `label_space_lag=true`，提示：**该模型不认识新类别，需下一轮重训才生效**。

---

### 15.5 三方精度实时对比

```
Accuracy_Evaluator 维护三个指标（仅计 confirm/correct/new_label，排除 pending）：

classifier_accuracy  = 分类器预测命中人工裁决的比率
llm_accuracy         = LLM建议命中人工裁决的比率（仅有LLM建议的单元）
human_verified_accuracy = 100%（人工裁决本身，恒为参照基准）

同时输出 macro 口径：precision/recall/f1
（与训练阶段 stratified_cv_eval 的输出口径完全对齐，跨轮可比）

llm_coverage = 有LLM建议的已审核单元 / 已审核单元总数
```

**增量更新**：每提交一条 Human_Verdict，`update_incremental(state, new_verdict)` 在 O(1) 时间内更新，不重算全量。且增量结果与全量重算数学等价（Correctness Property 9）。

---

### 15.6 存储抽象层设计（为后续落库预留接口）

```python
# 四类数据各自的仓储接口（DB迁移的唯一边界）
class ReviewResultRepository:
    def save_verdict(slot, review_id, verdict): ...
    def load_session(slot, review_id): ...

class GroundTruthRepository:
    def append_labels(slot, dataset_version, labels): ...
    def load_labels(slot, dataset_version): ...

class IterationHistoryRepository:
    def append(slot, record): ...   # append-only，永不修改历史
    def list_sorted(slot): ...

class LabelRegistryRepository:
    def load_current(slot): ...
    def save_new_version(slot, registry): ...
```

**当前实现**：文件/JSON，写-then-replace 原子写（防止中断导致数据损坏）。

**后续迁移**：只需新增 DB 实现类，业务调用方（orchestrator/review_session等）**零改动**，因为它们只依赖接口，不依赖具体实现。

```
数据文件位置（全部相对路径）：
  data/iterative_labeling/
  ├── label_registry.json           ← 标签注册表（含历史快照）
  ├── iterations/{slot}/*.json      ← 迭代历史（append-only）
  ├── review_results/{slot}/        ← 审核会话与裁决
  └── ground_truth/{slot}/          ← 固化真值标签
```

---

### 15.7 关键数据模型字段

**Model_Artifact（模型工件）：**

```json
{
  "model_ref": "mdl-2026round3-a1b2",
  "iteration_round": 3,
  "dataset_version": "ds-v3",
  "accuracy_record": {
    "macro_f1_mean": 0.8123,
    "macro_f1_std": 0.0214,
    "accuracy_mean": 0.8556,
    "per_class_recall_mean": {"0": 0.91, "1": 0.74, "20": 0.66},
    "confusion_matrix": {"labels": ["0","1","20"], "data": [[10,1,0],[2,8,1],[0,1,9]]}
  },
  "label_space_snapshot": {
    "label_space_version": "ls-v5",
    "label_ids": [0, 1, 20]
  }
}
```

**Human_Verdict（人工裁决）：**

```json
{
  "unit_key": "siteA|dev12|br3|2026-06-01",
  "verdict_label": 1,
  "action_type": "confirm",
  "is_ground_truth": true,
  "reviewer": "operator_zhang",
  "reviewed_at": "2026-06-08T12:06:00"
}
```

---

### 15.8 迭代收敛验证

每轮迭代后，Iteration_Tracker 可以看到趋势：

```
轮次  dataset_version  label_count  macro_f1_mean  macro_f1_std
1     ds-v1            2            0.71           0.031
2     ds-v2            3            0.79           0.025    ← 新增标签+更多样本
3     ds-v3            5            0.81           0.021    ← 精度提升，方差收窄
...

「标签越来越多、精度越来越好」= 迭代成功的核心验证指标
```

---

---

## 十六、负荷预测算法运营闭环 Skill（operation_skill）

### 16.1 这个Skill是什么

`operation_skill` 是一个**算法运营自动化闭环**，解决的问题是：当负荷预测模型精度劣化时，如何自动完成从发现问题到恢复正常的全流程，并生成可视化运营报告。

```
触发场景：精度劣化（Accuracy < 90%）

自动执行：
  检测劣化
    → 采集证据（基线/劣化/候选策略的真实精度）
    → LLM Agent 推理根因 + 选择恢复策略
    → 执行恢复（替换D-1数据）
    → 验证精度恢复效果
    → 生成HTML看板报告
    → 沉淀 CoE 专家经验
```

**真实运行结果（真实XGB模型实算，非模拟）：**

| 阶段 | 精度 | 说明 |
|------|------|------|
| 事故日基线 | 94.24% | 数据完整时正常预测 |
| 事故日劣化 | 86.03% | D-1缺失后精度跌落 |
| 恢复后（pred_fill_dm1策略） | 97.08% | 超越基线，恢复成功 |

---

### 16.2 技术背景：Gap一天预测模式

这是理解所有问题和策略的基础：

```
时间线：
  D+1 = 预测目标（明天的负荷）
  D   = 今天（不可用，Gap的来源）
  D-1 = 昨天（gap一天模式下可用的最近真值）

关键特征分组及重要性：
  lag 组（lag_1d/lag_2d...）   ≈ 40-50%   ← 量级锚点，最关键
  rolling 组（滑动统计）        ≈ 25-35%   ← 依赖lag，间接受影响
  calendar 组（时间特征）       ≈ 10-15%   ← 独立，不受数据缺失影响
  weather 组（气象）            ≈ 5-10%    ← 本资产不敏感

核心认知：
  lag_1d 在 gap 模式下实际取 D-1 的真实负荷值
  D-1 整天缺失 → lag_1d 全 NaN → rolling 短窗也被污染
  → 模型丧失量级锚点 → 精度骤跌 20-28pp
```

---

### 16.3 三阶段执行流程

**Phase 1：collect — 证据采集（脚本执行）**

```bash
conda run -n cp_web python scripts/run_collect.py
```

内部执行：
```
读取 cached_data/merged_20260201_20260527.csv
    ← 真实负荷+气象数据（南华变.10kV叶家线085）

① 训练基线模型（seed=42，XGBoost）
② 注入故障：置 D-1（2026-05-22）整天96点为 NaN
③ 用劣化数据重新训练，得到劣化精度
④ 逐候选策略实跑：
   - extra_gap：跳过D-1，从D-2起算 → 71.38%
   - pred_fill_dm1：预测D-1值回填 → 97.08%
⑤ 计算特征重要性分组
⑥ 产出 rca_input.json
```

**rca_input.json 关键结构：**

```json
{
  "evidence": {
    "fault_type": "A",
    "missing_start": "2026-05-22T00:00:00",
    "accuracy_drop": 8.21,
    "group_importance_baseline": {
      "lag": 0.4462,      ← lag组最高，是模型命门
      "rolling": 0.17261,
      "calendar": 0.37168,
      "weather": 0.00951
    }
  },
  "candidate_strategies": [
    {"strategy_id": "pred_fill_dm1", "expected_accuracy": 97.08},
    {"strategy_id": "extra_gap",     "expected_accuracy": 71.38}
  ]
}
```

---

**Phase 2：reasoning — LLM 根因分析（Agent推理）**

读取 `rca_input.json`，按四层 RCA 框架推理：

```
排查顺序：
1. 数据层：D-1 全天96点 load=NaN → 确认
2. 特征层：lag_1d失效 → rolling短窗污染 → 确认
3. 模型层：前3天基线稳定在88-94% → 排除渐进退化
4. 外部层：气象组重要性0.00951，气象数据完整 → 排除

置信度评估：
  跌幅8.21pp + 证据链完整 + 因果一致 → confidence=0.91

策略选择：
  pred_fill_dm1 精度97.08% >> extra_gap精度71.38%
  → 选 pred_fill_dm1
```

**真实 rca_decision.json：**

```json
{
  "rca": {
    "root_cause": "D-1(2026-05-22)整天96点负荷数据丢失，lag_1d(→D-1)全NaN，模型丧失负荷量级锚点，精度从94.24%跌至86.03%",
    "confidence": 0.91,
    "reasoning": "1) D-1全天96点load=NaN→lag_1d失效；2) lag组重要性0.4606排名第一；3) 精度跌幅8.21pp与lag锚点失效一致；4) 前3天基线稳定，排除模型衰退；5) 气象完整，排除外部因素",
    "undetermined": false
  },
  "strategy": {
    "selected_strategy_id": "pred_fill_dm1",
    "decision_reasoning": "pred_fill_dm1实测97.08%远超extra_gap的71.38%（高25.7pp），甚至超过基线94.24%"
  }
}
```

---

**Phase 3：resume — 执行恢复 + 生成报告（脚本执行）**

```bash
conda run -n cp_web python scripts/run_resume.py
```

内部执行：
```
读取 rca_decision.json（selected_strategy="pred_fill_dm1"）
    → 执行恢复策略（用预测值回填D-1）
    → 验证恢复后精度：97.08% ✓（超过85%目标）
    → 计算7天真实精度时间线（每天XGB实算，无插值）
    → 生成 CoE 专家经验摘要
    → 调用 html_report.py 渲染 HTML 看板
```

---

### 16.4 HTML报告看板设计（Gap一天看板 v1）

这是整个Skill最可视化的输出，遵循严格的 `references/html_report_style.md` 规范：

```
布局（一屏 100vh）：
  左侧深蓝导航栏
  主区：7天精度轨迹 SVG + 事件摘要
  中区：7天事故队列
  下区：3日负荷曲线 Canvas
  右侧四面板：策略决策/根因证据/执行链路/CoE建议
```

**精度轨迹标记语义（重要设计决策）：**

```
圆圈(dot)           = 实际运行的精度点（基线/劣化）
圆圈(半透明红)      = 未修复曲线 — 如果不做恢复的后续走势
菱形(diamond)       = 模型版本更新后的精度点（恢复策略）

虚线菱形(dashed)    = 事故日的"恢复后精度（待上线）"
实线菱形(solid)     = 次日开始"恢复模型已上线在用"

事故日竖直位置同时出现：
  红圈（劣化86.03%）
  绿色虚线菱形（恢复97.08%，待上线）

修复 vs 未修复双曲线对比（核心价值呈现）：
  绿实线菱形（修复上线）vs 红圈+红虚线（未修复持续低迷）
```

**配色方案：**

```
蓝 #1e63d6 → 稳定基线点
红 #d73c36 → 劣化/未修复点  
绿 #11874d → 恢复/修复后点
```

---

### 16.5 故障模式图谱

领域知识（`references/domain_knowledge.md`）定义了三类故障：

| 故障类型 | 触发条件 | 级联影响 | 精度跌幅 |
|---------|---------|---------|---------|
| **故障A** | D-1整天96点缺失 | lag_1d全NaN，rolling短窗污染 | 20-28pp |
| **故障B** | D-1+D-2连续缺失 | lag_1d/lag_2d均NaN，rolling全窗污染 | 30-40pp |
| **故障C** | 某天部分点缺失 | 对应lag部分NaN，rolling轻度影响 | 5-15pp |

**故障A恢复策略对比：**

| 策略 | 做法 | 优势 | 劣势 | 典型精度 |
|------|------|------|------|---------|
| `pred_fill_dm1` | 用gap模型预测D-1作为代理真值回填 | 保住lag_1d锚点 | 代理误差 | 91-93% |
| `extra_gap` | 跳过D-1，从D-2起算 | 安全不引入假值 | 丢失近期信息 | 88-91% |

**选择逻辑**：实测精度优先；`pred_fill` 精度通常高2-3pp，但若D-1是节假日/极端天气，预测值不可靠时选 `extra_gap`。

---

### 16.6 Skill架构设计亮点

**数据优先离线缓存：**
```python
# 数据加载优先级（real_data.py）
try:
    data = fetch_from_database(asset_name, date_range)
except:
    data = load_from_cache("cached_data/merged_*.csv")
    # 数据库不可用时自动降级，不中断运营闭环
```

**每次运行独立目录：**
```
artifacts/
  _active_run.json          ← 指向当前运行目录（{ "run_dir": "2026-06-05_173923" }）
  2026-06-05_173923/        ← 本次运行所有产物
    rca_input.json
    rca_decision.json
    real_timeline.json      ← 7天真实精度（每天XGB实算）
    loop_result.json        ← 闭环最终结果
    report_2026-06-05.html  ← HTML可视化报告
```

**seed=42保证可复现**：每次相同输入产生完全相同的训练结果，便于对比验证。

---

### 16.7 运营闭环的CoE沉淀

CoE（Center of Excellence）是系统级专家经验积累，每次成功恢复后自动追加：

```json
{
  "fault_type": "A",
  "root_cause": "D-1整天数据丢失，lag_1d锚点失效",
  "strategy_applied": "pred_fill_dm1",
  "baseline": 94.24,
  "degraded": 86.03,
  "recovered": 97.08,
  "delta_recovery": 11.05,
  "key_insight": "lag_1d是gap模式命门特征，重要性0.45，D-1缺失导致精度跌8pp以上",
  "prevention": "建立采集多通道冗余，设置入库超时告警"
}
```

这些经验可在下次同类故障时作为 Agent 推理的参考，让系统越运营越智能。

---

### 16.8 三个模块的整体关系

```
pv-fault-diagnosis-integration（光伏故障诊断集成）
  ↓ 提供训练/预测工作流
pv-fault-iterative-labeling-loop（迭代标注闭环）
  ↓ 编排工作流 + 人机协同打标
operation_skill（算法运营Skill）
  ← 独立于上述两个，面向负荷预测运营
     但共享相同的设计理念：
     ① 算法+工程结合（真实XGB/RF模型实算）
     ② 闭环可追溯（每次运行保留完整产物）
     ③ 人机协同（LLM推理 + 人工最终裁决/确认）
     ④ 知识沉淀（CoE + Iteration_Tracker）
```

---

## 附录（更新）：我的贡献——光伏故障诊断与运营Skill

| 模块 | 主要工作内容 |
|------|------------|
| **算子移植（pv-fault-diagnosis-integration）** | 设计3新算子架构（time_window_split/ts_comparison_features/batch_predict_classifier）；扩展4个已有算子（mRMR/robust_clip/drop_insufficient/groupby_aggregate）；定义训练+预测双流水线模板；设计算子间数据契约Schema |
| **标注闭环（pv-fault-iterative-labeling-loop）** | 设计5阶段闭环状态机；定义8组件架构（Orchestrator/ReviewSession/LLM/AccuracyEvaluator/LabelRegistry/Backfill/Tracker/Storage）；设计存储抽象接口（预留DB）；定义所有REST接口（英文字段+中文注解）；设计label_id稳定分配机制；设计三方精度增量更新算法 |
| **运营Skill（operation_skill）** | 设计三阶段运营闭环（collect/reasoning/resume）；实现真实XGB模型计算引擎（real_data.py）；设计HTML看板规范（Gap一天看板v1，精度轨迹标记语义）；领域知识库（故障图谱/特征工程/决策原则）；完整跑通真实运营场景：基线94.24% → 劣化86.03% → 恢复97.08% |

---

## 十七、数据管线数据库集成（data-pipeline-db-integration）

### 17.1 背景与动机

平台早期所有数据全部依赖本地文件：`predictions.db`（SQLite）、`slots.json`/`candidate_pool.json` 等 JSON 文件、光伏标注数据 `all_labeled_combined.parquet`。这带来三个问题：

1. **无法多进程并发安全写入**：SQLite 在 FastAPI + Worker 双进程下会锁冲突
2. **查询能力弱**：JSON 文件无法做时间范围过滤、槽位隔离、精度汇聚等 SQL 查询
3. **无法对接公司生产数据库**：公司 MySQL（`10.65.101.249`）里有每天实时更新的站点传感器数据，平台需要定时拉取才能做真正的滚动预测闭环

本模块把两条独立数据管线（负荷预测 + 光伏故障诊断）迁移到 MySQL，并实现"拉数据 → 滚动预测 → 精度回填"的定时任务闭环。

---

### 17.2 整体架构

两条管线在数据库层面**完全隔离**，各自独立的 MySQL Database：

```
负荷预测管线                          光伏故障诊断管线
──────────────────                   ──────────────────
MySQL: load_forecast                 MySQL: pv_fault_diag
  station_data                         training_samples
  experiment_runs                      model_versions
  candidate_pool                       prediction_records
  knowledge_claims                     diagnosis_results
  prediction_results
  accuracy_metrics
  version_registry
  prelaunch_queue
```

**核心组件层次：**

```
FastAPI 路由层
    │
    ▼
Service 层（precision_ops / pv_fault）
    │
    ▼
DB Adapter 层
  ├── DBAdapter         ← SQLAlchemy 连接池 + 健康检查 + Alembic 迁移
  ├── LoadForecastRepository  ← 负荷预测 CRUD
  ├── PVFaultRepository       ← 光伏故障 CRUD
  ├── StationDataSource       ← 站点数据源抽象（本地Mock/公司MySQL）
  └── DualWriteProxy          ← 过渡期双写（DB + 文件同步）
    │
    ▼
MySQL（本地开发: localhost:3306 / 生产: 10.65.101.249）
```

---

### 17.3 DBConfig — 三级配置优先级

文件：`services/db/config.py`

所有配置从三个来源加载，优先级高→低：

```
1. 环境变量（最高优先级）
2. configs/db.yaml（配置文件）
3. 代码默认值（兜底）
```

**关键配置字段：**

| 环境变量 | 含义 | 默认值 | 范围约束 |
|---------|------|--------|---------|
| `DB_ENABLED` | 数据库总开关，false=退化到文件存储 | `true` | bool |
| `DB_ENGINE` | 引擎类型 | `mysql` | — |
| `DB_CONNECTION_URL` | 完整连接串 | `mysql+pymysql://root@localhost:3306/aip_algo_platform` | — |
| `DB_POOL_MAX` | 连接池最大连接数 | `10` | [1, 100] |
| `DB_POOL_IDLE_TIMEOUT` | 空闲连接超时（秒） | `300` | [10, 3600] |
| `DB_POOL_CONN_LIFETIME` | 连接最大生存期（秒） | `3600` | [60, 86400] |
| `DB_POOL_WAIT_TIMEOUT` | 池满排队等待超时（秒） | `30` | [1, 120] |
| `DB_DUAL_WRITE` | 双写模式开关 | `true` | bool |
| `SCHED_LF_PULL_CRON` | 负荷数据拉取 cron | `0 1 * * *` | — |
| `SCHED_LF_PREDICT_CRON` | 负荷预测 cron | `30 1 * * *` | — |
| `SCHED_LF_BACKFILL_CRON` | 精度回填 cron | `0 3 * * *` | — |
| `SCHED_PV_PULL_CRON` | 光伏数据拉取 cron | `0 2 * * *` | — |

整型字段超出范围时 `DBConfig.__post_init__` 抛 `ValidationError`，阻止启动。

**切换到公司数据库只需改一行：**

```bash
export DB_CONNECTION_URL="mysql+pymysql://user:pass@10.65.101.249:3306/load_forecast"
```

引擎一致（都是 MySQL），`pymysql` 驱动已是项目既有依赖，无需安装新包。

---

### 17.4 DBAdapter — 连接池 + 指数退避重试

文件：`services/db/adapter.py`

**初始化流程：**

```
DBAdapter.__init__(config)
    │
    ├── 1. 创建同步引擎 (SQLAlchemy + pymysql)
    │      pool_size=max_connections
    │      pool_recycle=connection_lifetime（自动回收老连接）
    │      pool_pre_ping=True（每次取连接前先 SELECT 1 验证存活）
    │
    ├── 2. 尝试创建异步引擎 (aiomysql，可选)
    │      aiomysql 未安装时跳过，只记 warning，不阻断启动
    │
    ├── 3. 验证连接（指数退避重试）
    │      第1次失败 → 等1s → 第2次
    │      第2次失败 → 等2s → 第3次
    │      第3次失败 → 等4s → 第4次
    │      第4次失败 → 抛 DBAdapterError（共尝试4次）
    │
    └── 4. run_migrations()
           alembic upgrade head（自动执行所有待迁移）
           失败 → 抛 MigrationError（含失败的 revision ID）→ 阻止启动
```

**Session 使用方式：**

```python
# 同步（FastAPI 后台任务、Cron 任务）
with adapter.get_sync_session() as session:
    session.add(station_data_obj)
    # 正常退出自动 commit，异常自动 rollback

# 异步（FastAPI async 路由）
async with adapter.get_async_session() as session:
    await session.execute(text("SELECT ..."))
```

---

### 17.5 双写代理（DualWriteProxy）— 平滑迁移

文件：`services/db/dual_write.py`

过渡期不能一刀切换到数据库，需要 DB 和文件并存验证。`DualWriteProxy` 根据配置透明路由：

```
写入路由：
  DB_ENABLED=false          → 只写文件（完全透明，无 error log）
  DB_ENABLED=true, DUAL=true → 先写 DB，再写文件；一侧失败只 WARNING，不回滚另一侧
  DB_ENABLED=true, DUAL=false → 只写 DB

读取路由：
  DB_ENABLED=false          → 只读文件
  DB_ENABLED=true           → 先读 DB（5秒超时）
                               DB 连接失败/超时 → WARNING + 降级读文件
                               两者都不可用   → 抛 RuntimeError（返回 503）
```

**关键设计**：`_db_enabled()` 和 `_dual_write()` 每次调用都重读环境变量，支持**运行时热切换**，无需重启进程。

**精度运营模块接入**：`precision_ops` 下的四个服务（`prediction_store`/`accuracy_tracker`/`version_registry`/`prelaunch_manager`）均通过 `DualWriteProxy` 写入/读取，现有 API 响应 JSON 结构完全不变。

---

### 17.6 数据库 Schema 设计

#### 负荷预测（`load_forecast` database）

核心表及用途：

| 表名 | 作用 | 关键字段 |
|------|------|---------|
| `station_data` | 从站点/公司数据库拉取的原始传感器数据 | `slot, station_id, timestamp_utc, feature_name, value` |
| `experiment_runs` | AutoResearch run 的完整状态快照 | `id, slot, status, config, runtime_patch, run_insight` |
| `candidate_pool` | 候选配置池（含 patch_signature 去重） | `id, slot, run_id, patch_signature, best_mape, evidence` |
| `knowledge_claims` | 知识层声明 | `id, slot, scenario_fingerprint, claim_data, confidence` |
| `prediction_results` | 每日预测结果（含 shadow 模型） | `slot, workflow_id, forecast_timestamp, predicted_value, actual_value, is_shadow` |
| `accuracy_metrics` | 滚动精度指标 | `slot, workflow_id, rolling_mape, valid_cycle_count` |
| `version_registry` | 工作流版本注册表 | `slot, workflow_id, version_tag, status, baseline_mape` |
| `prelaunch_queue` | 预上线观察队列 | `slot, candidate_id, observation_days, graduate_tolerance_pct, evaluated_cycles` |

**`slot` 分区设计**：所有表都有 `slot` 字段作为逻辑分区键，查询时必须带 `slot` 条件。新增槽位（如 `load_forecast_pv`）只需插入带新 `slot` 值的行，**不需要任何 DDL 变更**。

**关键索引：**

```sql
-- 按站点时间范围查询（数据拉取高水位）
INDEX (slot, station_id, timestamp_utc)

-- 按预测周期回填实际值
INDEX (slot, prediction_cycle_id)
INDEX (slot, workflow_id, forecast_timestamp)

-- 候选去重
INDEX (slot, patch_signature)

-- 版本唯一约束
UNIQUE (slot, workflow_id, version_tag)
```

#### 光伏故障诊断（`pv_fault_diag` database）

| 表名 | 作用 | 关键约束 |
|------|------|---------|
| `training_samples` | 带标签的训练样本（来自 Parquet） | 复合唯一键 `(time, site_id, device_id, branch_id)` 防重复导入 |
| `model_versions` | 模型版本元数据 | `version_tag, label_space_version, artifact_path` |
| `prediction_records` | 每条设备的故障预测 | `confidence CHECK [0.0, 1.0]` |
| `diagnosis_results` | 诊断结论 | `fault_type_name, severity` |

---

### 17.7 Alembic 迁移管理

`DBAdapter.__init__` 启动时自动执行 `alembic upgrade head`，确保 Schema 始终是最新版本。迁移脚本按顺序编号：

```
alembic/versions/
  001_create_load_forecast_schema.py   ← 创建 load_forecast database + 全表
  002_create_pv_fault_diag_schema.py   ← 创建 pv_fault_diag database + 全表
  003_add_station_data_table.py        ← 后续新增
  ...
```

迁移失败时：回滚当前 revision → 记录 `MigrationError`（含 revision ID）→ 抛异常阻止 FastAPI 启动。**数据库 Schema 不完整时服务不上线**，是有意的强约束。

---

### 17.8 定时任务三 Cron 闭环

**负荷预测三个 Cron（每天）：**

```
01:00  lf_data_pull
  └─ StationDataSource.pull_latest(since=上次高水位)
  └─ 写入 station_data 表（INSERT IGNORE 防重）
  └─ 高水位 = 本次拉到的最大 timestamp_utc

01:30  lf_prediction
  └─ 加载当前 production 工作流（从 version_registry 查）
  └─ 取最近数据窗口（符合 Gap-One-Day 约束：训练数据截止 T-1）
  └─ 预测 T+1
  └─ 写入 prediction_results（is_shadow=false）
  └─ 同时对 prelaunch_queue 里所有 observing 状态的模型执行 shadow 预测
     └─ 写入 prediction_results（is_shadow=true）

03:00  lf_accuracy_backfill
  └─ 查找 T 日已有实际值的记录
  └─ 计算 MAPE = mean(|predicted - actual| / |actual|) × 100
  └─ 更新 accuracy_metrics.rolling_mape（滚动 30 天窗口）
  └─ 同时回填 prelaunch_queue 里每个候选的 current_rolling_mape
  └─ 触发 prelaunch 毕业判定（见第十章）
```

**高水位拉取语义**：每次 pull 只请求 `timestamp_utc > 上次成功拉取的最大时间戳`，确保无重复无遗漏。

**任务重叠保护**：同类型 Cron 同时只允许一个实例运行（APScheduler `max_instances=1`）。触发时已有实例跑着 → 本次跳过 + 记 warning，在 `/api/scheduler/status` 里可见。

**失败重试**：失败后等 60s 重试一次，重试也失败则标 `last_result="failed"`，保留最近 20 条 `FailureRecord`（`task_id/trigger_time/error_message/is_retry`）。

**停机追赶（catch-up）**：服务重启后每个任务最多补跑 1 次最近漏跑的调度，不重跑所有遗漏次数。

---

### 17.9 数据源抽象（StationDataSource）

文件：`services/db/datasources/base.py`

定义了一个 ABC，隔离"数据从哪来"和"数据如何存储"：

```python
class StationDataSource(ABC):
    def pull_latest(
        self,
        station_id: str,
        since_timestamp: datetime,    # 高水位时间戳
    ) -> List[StationRecord]: ...     # 空列表=无新数据，30s超时抛 DataSourceTimeoutError

    def get_available_stations(self) -> List[StationInfo]: ...
```

目前有两个实现：

| 实现类 | 文件 | 用途 |
|--------|------|------|
| `LocalMockDataSource` | `datasources/local_mock.py` | 读本地 CSV/Parquet 文件，开发/测试用 |
| `CsvMockCompanyFeeder` | `datasources/local_db_mock.py` | 模拟公司数据库每日新增数据写入 `station_observations` 表 |

**未来接入公司数据库**只需新增 `CompanyDBDataSource(StationDataSource)`，改一行配置，调度器和 Repository 层零改动。底层异常全部封装为 `DataSourceError`，不向上层暴露 `pymysql` 原始异常。

---

### 17.10 现有数据迁移工具

文件：`services/db/migration_tool.py`

一次性把历史文件数据导入 MySQL：

```
精度运营 JSON 文件（accuracy_metrics/prelaunch_queue/version_registry）
    → load_forecast 对应表，按自然键去重

predictions.db SQLite
    → load_forecast.prediction_results，验证迁移前后行数一致

all_labeled_combined.parquet
    → pv_fault_diag.training_samples，按复合键 (time,site_id,device_id,branch_id) 去重
```

**幂等设计**：同一份源数据多次运行结果相同，不产生重复行。源文件损坏时跳过该文件继续处理其余，完成后输出摘要（总迁移行数/跳过行数/处理文件数/耗时）。

---

### 17.11 与算法部署模块的关联

数据库集成与算法部署（第五章）深度联动：

```
station_data 表              ← Cron 每天写入
    │ 喂给
    ▼
lf_prediction Cron           ← 读取最新数据 → 训练 → 预测 T+1
    │ 写入
    ▼
prediction_results 表         ← is_shadow=false(生产) / is_shadow=true(预上线/影子)
    │
    ▼
lf_accuracy_backfill Cron    ← T+1实际到达后，计算MAPE
    │ 写入
    ▼
accuracy_metrics 表           ← rolling_mape 实时更新
    │ 触发
    ▼
prelaunch_lifecycle.check_graduation()   ← 毕业判定（预上线模型）
SwitchDecisionEngine.evaluate()          ← 切换判定（影子模型）
    │ 写入
    ▼
version_registry + slots.json            ← 模型状态更新 + switch_log 追加
```

这条链路串通了：**数据入库 → 模型预测 → 精度评估 → 模型晋升**的完整生产闭环。

---

---

## 十八、AutoResearch 中断恢复机制

### 18.1 为什么需要断点恢复

AutoResearch 单次 run 可能跑几小时、几十轮回测。中间出现以下情况都会导致中断：

- 手动 kill FastAPI 进程（部署更新）
- 服务器重启/OOM
- Worker 进程崩溃（内存耗尽、段错误）
- 用户手动 cancel
- 网络断开导致 Worker 心跳超时

**没有断点恢复就意味着**：已跑 40 轮的结果全部丢失，下次从第 1 轮重跑，浪费几小时算力。

### 18.2 两级持久化：snapshot + trial 账本

断点恢复的根基是持续写磁盘。每轮回测完成后有两个独立写入：

#### 1. Snapshot（全量状态快照）

文件：`data/autoresearch/runs/{run_id}/snapshot.json`

内容：run 的完整内存状态，包括：
- `status`（running/cancelled/success）
- `progress`（当前轮次/总轮次）
- `iterations`（所有轮次的结果列表）
- `runtime_patch`（已应用的参数补丁）
- `best_candidate`、`top_candidates`（候选池当前最优）
- `exploration_health.scoreboard`（方向覆盖记分板）
- `baseline_mape`、`search_space`、`windows` 等所有运行参数

写入由 `_snapshot_autoresearch_state(run_id)` 触发，时机非常密集：
- 每轮开始时
- 每个 batch group 开始/完成/失败时
- GLM proposal 生成/应用后
- 每 1.5 秒一次实时进度快照（并发回测期间）
- 轮次结束时
- `finally` 块兜底

写入用**原子替换**（先写临时 `.tmp` 文件，再 `os.replace` 覆盖），磁盘上永远是完整 JSON，不会读到半截文件。

#### 2. Trial 账本（追加日志）

文件：`data/autoresearch/runs/{run_id}/trials.jsonl`

每轮结束后 `record_trial_from_candidate()` 追加一行 JSON，包含：

```json
{
  "iteration_no": 8,
  "comparison_id": "cmp-abc123",
  "status": "success",
  "override": {"train_days": 45},
  "structure_patch": {},
  "mape_improvement": 0.18,
  "challenger_mape": 4.03,
  "baseline_mape": 4.21,
  "batch_groups": [...],
  "evidence": {...}
}
```

账本是 **append-only，永不修改历史行**。它是确定 resume 起点的依据，比 snapshot 的 `progress` 字段更可靠（snapshot 可能在第 8 轮写完但 trial 还没落账）。

---

### 18.3 进程崩溃后的状态标记

Worker 进程用心跳机制证明自己还活着：每 15 秒写一次 `jq.heartbeat(run_id)` → SQLite `jobs` 表的 `heartbeat_at` 字段更新。

FastAPI 启动时调 `jq.mark_dead_workers()`：把 `heartbeat_at < now - 120s` 的 running job 标为 `interrupted`。

同时 `AutoResearchRunStore.scan_and_mark_interrupted()` 扫描磁盘快照，把 status 还是 `running/waiting_review` 的 run 全部改成 `interrupted` 并写回磁盘：

```python
loaded["status"] = "interrupted"
loaded["recoverable"] = True
loaded["interrupted_at"] = datetime.now().isoformat()
loaded["error"] = "服务重启或内存状态丢失，运行已中断"
```

前端轮询到 `interrupted + recoverable=True` 时显示"可恢复"提示和 Resume 按钮。

---

### 18.4 Resume 接口：确定从哪轮重跑

`POST /api/workflows-enhanced/auto-research-resume/{run_id}` 的完整流程：

```python
# 1. 只允许三种状态可恢复
if status not in ("interrupted", "failed", "cancelled"):
    raise 400

# 2. 从磁盘加载 snapshot（恢复完整状态）
snapshot = _auto_research_persister.load_snapshot(run_id)

# 3. 从 trials.jsonl 读取已完成轮次
#    只有 status in ("success", "failed", "pruned") 的 trial 算"完成"
trials = _auto_research_persister.list_trials(run_id, limit=10000)
completed_iterations = {
    int(t["iteration_no"])
    for t in trials
    if t.get("status") in ("success", "failed", "pruned")
}

max_completed = max(completed_iterations)  # 例：7
resume_from_iteration = max_completed + 1   # 从第 8 轮开始

# 4. 恢复内存状态（保留已有的 runtime_patch / top_candidates / best_candidate）
_auto_research_store[run_id] = snapshot
_auto_research_store[run_id]["status"] = "running"
_auto_research_store[run_id]["resume_from_iteration"] = resume_from_iteration

# 5. 提交 resume job 到 SQLite 队列
_jq.submit_job(run_id, {
    "start_iteration": resume_from_iteration,
    "total_iterations": original_total,
    "resume": True,
    ...所有原始参数从 snapshot 里读回
})
```

**为什么用 Trial 账本而不是 `progress.iteration` 确定起点？**

快照里 `progress.iteration=8` 但 Trial 账本只有到第 7 轮落账的情况是存在的（第 8 轮的 trial 还没写完就崩了）。用 Trial 账本算 `max_completed=7`，从第 8 轮重跑，是**宁可重跑一轮也不跳过**的保守设计，保证状态一致性。

---

### 18.5 Worker 执行 resume job

Worker `_execute_job()` 拿到 resume job 后：

```python
# 从磁盘恢复完整内存状态
existing_snapshot = _auto_research_persister.load_snapshot(run_id)
if existing_snapshot:
    _auto_research_store[run_id] = existing_snapshot
    _auto_research_store[run_id]["status"] = "running"

# 执行主循环，从 resume_from_iteration 开始
asyncio.run(
    _run_autoresearch_task(
        ...
        start_iteration=resume_from_iteration,   # 例：8
        total_iterations=original_total,          # 例：50
    )
)
```

主循环：`for iteration in range(start_iteration, total_iterations + 1):`，第 1-7 轮直接跳过。

恢复后哪些状态是完整的：

| 状态 | 是否恢复 | 说明 |
|------|---------|------|
| `runtime_patch` | ✅ | 已应用的参数补丁，后续轮次继续叠加 |
| `best_candidate / top_candidates` | ✅ | 候选池排名不丢失 |
| `exploration_health.scoreboard` | ✅ | 方向覆盖记分板，Planner 继续按此分配方向 |
| `iterations` 历史列表 | ✅ | 已跑轮次的完整记录 |
| `knowledge_layer` 知识 | ✅ | 已沉淀的知识声明（写在独立 JSON 文件里） |
| `_AUTORESEARCH_BACKTEST_POOL` 线程池 | ✅ | Worker 重启时重新创建，但 Baseline Cache 需重建 |
| GLM `avoid_set`（已否证集） | ✅ | 从 snapshot 的 `ineffective_directions` 恢复 |
| Baseline Cache | ⚠️ | 内存缓存，重启后清空，下一轮会重跑 Baseline（不影响正确性，只多消耗一次回测） |

---

### 18.6 完整流程一图

```
正常运行中（每轮）
  │─── _snapshot_autoresearch_state() ──→ snapshot.json（原子写）
  └─── record_trial_from_candidate() ──→ trials.jsonl（append-only）

Worker 进程被 kill：
  FastAPI 启动时检测到心跳超时（120s）
    │─── jq.mark_dead_workers()   ──→ SQLite: job.status=interrupted
    └─── scan_and_mark_interrupted() ──→ snapshot.json: status=interrupted, recoverable=True

用户在前端点击"恢复"：
  POST /auto-research-resume/{run_id}
    │─── 读 snapshot.json 拿回所有状态
    │─── 读 trials.jsonl → completed_iterations={1,2,...,7}
    │─── resume_from_iteration = 8
    └─── jq.submit_job(..., start_iteration=8, resume=True)

Worker 领取 resume job：
  _execute_job()
    │─── load_snapshot() → 恢复完整内存状态
    └─── asyncio.run(_run_autoresearch_task(start_iteration=8))
           for iteration in range(8, 51):
             # 直接从第8轮开始，前7轮跳过
             # runtime_patch/top_candidates/scoreboard 全都在
```

---

### 18.7 边界情况：轮次中途崩溃

第 8 轮跑到一半（比如 batch group 2 完成，group 3 还没完成）时崩溃：

- Trial 账本里第 8 轮的 status 可能是 `failed`，也可能压根没写进去
- Resume 后 `max_completed = 7`，第 8 轮**整轮重跑**
- group 1-2 的回测资源被重复消耗，但这是**宁可重跑也不跳过**的保守设计
- 重复跑同样的配置不会产生错误结果（回测是确定性的），只是多消耗算力

**这个 trade-off 是有意为之的**：正确性 > 算力节省。

---

---

## 十九、算子间数据契约详解

### 19.1 MATRIX 和 OBJECT 是什么

这两个类型在 `DataContract` 里是**语义标签**，不是 Python 类型约束。实际在内存里流转的对象是：

| 契约类型 | 实际 Python 对象 | 何时使用 |
|---------|----------------|---------|
| `MATRIX` | `pd.DataFrame` | 数据还是"表格"形式，行有统一语义 |
| `OBJECT` | Python `dict`，里面装多个东西 | 需要同时传模型、数组、DataFrame 等多种结构时 |
| `NUMBER` | `float` | 单个评估指标，如 SMAPE 值 |
| `ARRAY`  | `np.ndarray` 或 `list` | 一维序列，如标签数组 |

典型 OBJECT 示例：

```python
# feature_select 输出
{
    "selected_features": pd.DataFrame,   # 还是 DataFrame，被包在 dict 里
    "feature_list":      list,           # 训练时选出的列名，预测时复用
    "target":            np.ndarray,     # 标签数组
}

# random_forest_classifier 输出
{
    "model":               训练好的 sklearn 模型对象,
    "predictions":         np.ndarray (int),
    "y_true":              np.ndarray (int),
    "feature_importances": np.ndarray (float),
}
```

---

### 19.2 算子间数据是怎么传递的

执行引擎（`OperatorRouter`）按拓扑排序逐节点调用 `execute(params, inputs)`：

```
inputs = {
    "data": 上游节点输出的 DataFrame 或 dict 的对应 value
}
```

每个算子接收 `inputs`，返回 `dict`。执行框架把返回值的 value 作为下游节点的 `inputs["data"]`（或对应端口名的 key）传入。**算子之间没有共享内存，每一步都是显式传递。**

---

### 19.3 负荷预测：同一个 DataFrame 一路加列

负荷预测流水线里，**所有特征算子都遵循同一个模式**：

```python
def execute(params, inputs):
    df = inputs.get("data").copy()   # 接收上游传来的 DataFrame
    df["新列名"] = df["load"].shift(1)  # 在原 DataFrame 上新增列
    return {"data": df}              # 传出去，行数不变，列变多了
```

特征算子的契约约定就是"原地加列，行语义不变"：

```
load_csv 之后：
  record_time(datetime) | load(float)
  [每行 = 一个15min时间点]

+ 时间特征：
  record_time | load | hour | dayofweek | month | is_holiday | is_workday

+ 滞后特征 (create_lag_features, lags=[1,24,168])：
  ... | load_lag_1 | load_lag_24 | load_lag_168

+ 滚动统计 (rolling_statistics, windows=[24,48,96,168])：
  ... | load_rolling_mean_24 | load_rolling_std_24 | load_rolling_mean_48 | ...

+ 滑动窗口 (sliding_window)：
  [行语义变成"一个窗口切片的样本"]
  每行 = 拍平的 N 个时间步的所有特征值

→ OBJECT (train_test_split)：
  {"train_features": DataFrame, "train_target": array,
   "test_features":  DataFrame, "test_target":  array}
```

**下游算子不关心有多少列**，只要它 `required_columns` 里声明的列存在即可。多出来的特征列不影响。这就是为什么特征算子可以独立添加而不需要改其他算子——约定的是"列名"，不是"完整的列集合"。

---

### 19.4 光伏故障诊断：两段截然不同的形态，一次关键转换

光伏流水线有一个明确的**形态切换点**，把数据从"时序点"变成"诊断单元"：

#### 第一段：时序点形态（切换前）

每行 = 一个设备在一个时刻的传感器读数：

```
time(datetime) | site_id | device_id | branch_id | I_a | I_b | I_c | label(int)
2026-06-01 00:00  site1    dev12       br1          5.1   5.0   4.9    1
2026-06-01 00:15  site1    dev12       br1          5.2   5.1   4.8    1
...（每天96条）
```

这一段的算子都是"改行/改列"但不改行语义：

```
load_csv × 2 → label_encode（合并两CSV，"suite-0"→20，+label列）
  → time_window_split（+time_window列，每条打上所属窗口）
  → handle_missing（按分组丢弃数据不足的整组）
  → detect_outliers（按差分去极值，极值→NaN）
```

`time_window_split` 后数据变为：

```
time | site_id | device_id | branch_id | I_a | I_b | I_c | label | time_window
...   site1    dev12       br1          5.1   5.0   4.9    1       2026-06-01  ← 新增列
...   site1    dev12       br1          5.2   5.1   4.8    1       2026-06-01
...（一天 96 条，time_window 都是 2026-06-01）
```

行数没变，只是每行多知道"自己属于哪个窗口"。

---

#### 第二段：形态切换（96行 → 1行）

三路特征算子各自做**窗口内聚合**，把同一设备+同一窗口的96条时序点**压缩成1行特征向量**：

```python
# extract_statistical_features（分组聚合统计特征）
result = df.groupby(["site_id", "device_id", "branch_id", "time_window"]).agg(...)
# 输出：index = (site_id, device_id, branch_id, time_window) 的 MultiIndex
# 列 = I_a_max, I_a_min, I_a_mean, I_a_std, I_a_kurtosis, I_b_max, ...

# tsfresh_extract（分组tsfresh特征）
# 输出：同样的 MultiIndex，列 = abs_energy, benford_correlation, ...

# ts_comparison_features（分组两两对比特征）
# 输出：同样的 MultiIndex，列 = I_a_I_b_spearman, I_a_I_b_dtw, ...
```

三路输出的**行索引（MultiIndex）完全相同**，这是能合并的关键：

```python
# feature_select 里收到三路输入后合并
pd.concat([stat_features, tsfresh_features, comparison_features], axis=1)
#          ↑ MultiIndex相同 → 按行自动对齐，横向拼接
```

切换后每行代表一个**诊断单元**（一个设备在一天内所有数据的聚合）：

```
index: (site1, dev12, br1, 2026-06-01)

列：I_a_max | I_a_mean | I_a_std | ... | I_a_I_b_spearman | I_a_I_b_dtw | ... | label
值：5.3      | 5.1      | 0.12    | ... | 0.98             | 0.03        | ... | 1
```

---

#### 第三段：分类训练（切换后到输出）

```
feature_select(mrmr, k=50, mode='fit')
  输入：宽表 DataFrame（MultiIndex，几百列特征 + label）
  输出：OBJECT {
    "selected_features": DataFrame(50列),  # mRMR选出的最有价值50列
    "feature_list":      ["I_a_max", "I_a_I_b_spearman", ...],  # 列名列表，预测时复用
    "target":            array([1, 20, 0, 1, ...])              # 标签数组
  }

smote_oversample(limit=500)
  输入：OBJECT（selected_features + target）
  输出：OBJECT {
    "features": DataFrame（过采样后，少数类样本数增加），
    "target":   array（对应标签）
  }

random_forest_classifier(mode='train')
  输入：OBJECT（features + target）
  输出：OBJECT {
    "model":               sklearn RandomForestClassifier,
    "predictions":         array([1, 20, 0, ...]),
    "y_true":              array([1, 20, 1, ...]),
    "feature_importances": array([0.05, 0.03, ...])
  }
```

---

### 19.5 预测流水线的契约复用

预测流水线和训练流水线的差异只在两处：

**差异1：`feature_select` 用 `mode='transform'`（不重新fit，用训练时保存的 `feature_list`）**

```python
# 训练时
feature_select(mode='fit', k=50)     → 返回 feature_list = ["I_a_max", ...]
# 这个 feature_list 被序列化存进模型 pkl 文件

# 预测时
feature_select(mode='transform', feature_list=["I_a_max", ...])
# 或 feature_list='latest'（自动读最新的 pkl 文件里的 feature_list）
→ 只做列筛选，不重新计算 mRMR，确保特征空间与训练完全对齐
```

**差异2：`batch_predict_classifier` 替换 `smote + random_forest`**

```python
batch_predict_classifier(batch_size=10000)
  输入：OBJECT（model + selected_features）
  输出：OBJECT {
    "predictions": DataFrame（id_fields + predict_label列），
    "failure_count": int
  }

label_encode(mode='decode')
  输入：DataFrame（含 predict_label 列，值为整数 20）
  输出：DataFrame（predict_label_id 列，值为 "suite-0"）
```

---

### 19.6 两条流水线契约对比总结

| 维度 | 负荷预测 | 光伏故障诊断 |
|------|---------|------------|
| 行语义变化点 | `sliding_window`（时间点→窗口样本） | 三路特征算子聚合（时间点→诊断单元） |
| 特征叠加方式 | 同一 DataFrame 上原地加列 | 三路独立 DataFrame 靠 MultiIndex 横向拼接 |
| 中间数据的 key | 始终是 `inputs["data"]` | 先是 `inputs["data"]`，特征阶段产生多路 `inputs` |
| 契约核心约定 | 列名约定（required_columns） | 列名 + MultiIndex 联合主键约定 |
| OBJECT 出现时机 | 从 `train_test_split` 开始 | 从 `feature_select` 开始 |
| 预测/训练差异 | 同一工作流 mode 参数控制 | `feature_select fit/transform` + `batch_predict` 替换 |

---

### 19.7 一个容易混淆的问题：特征算子输出的 index 是什么

**负荷预测**：特征算子输出的 DataFrame 保持原始的 `RangeIndex`（0, 1, 2, ...），列名就是契约的核心，不依赖行索引做任何对齐。

**光伏故障诊断**：特征提取后的 DataFrame 使用 **`MultiIndex`（设备×窗口的联合主键）** 作为行索引。`(site_id, device_id, branch_id, time_window)` 这个四元组唯一标识一个诊断单元，三路特征算子必须产生相同的 MultiIndex 才能被 `feature_select` 正确横向拼接。这是光伏流水线契约中最重要的隐含约定，也是代码里为什么要在特征算子里 `df.groupby(id_fields)` 并把结果设为 index 的原因。
