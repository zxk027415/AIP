<!-- @AI_GENERATED -->
# 算法部署 + AutoResearch 联动 完整落地计划

> 文档目的：记录本次部署模块重构、Cron 流水线重建、Shadow/Prelaunch 流水线打通的完整决策和实施规划。
> 状态：阶段 1 已完成（批次 1）；阶段 2～6 待执行。

---

## 一、总目标

打通「数据库模拟每日灌数据 → 每日训练+预测（严格 gap-1-day，预测 T+1）→ 次日精度回填 → Shadow 锦标赛 + Prelaunch 安全闸门 → 自动切换/毕业」的完整闭环。

---

## 二、最终架构

```
数据源                    Cron                                Slot 模型池
─────────────────────────────────────────────────────────────────────
                        ┌──────────────┐
mock_company            │ lf_data_pull │ 每天 01:00
station_observations ──▶│  (拉数据)     │
                        └──────────────┘
                                ↓
                        ┌────────────────────┐
                        │  lf_daily_rolling  │ 每天 02:00
                        │  (训练 + 预测)      │
                        │  ≤T-1 数据训练      │──▶ Production (1)
                        │  预测 T+1           │──▶ Shadow ×N (≤3)
                        │  写 PredictionResult│──▶ Prelaunch ×M (≤2)
                        └────────────────────┘
                                ↓ (T+1 真值到达)
                        ┌───────────────────────┐
                        │ lf_accuracy_backfill  │ 每天 04:00
                        │ 补 actual_value        │
                        │ 更新滚动 MAPE          │
                        │ 检查 Prelaunch 毕业    │──▶ 达标 → Shadow
                        │ 检查 Shadow 切换资格   │──▶ 排第一 → 建议切换
                        └───────────────────────┘

Slot 决策流水线：
  candidate (AutoResearch)
      ↓ 复验通过
  verification_queue
      ↓ 用户/自动入池
  prelaunch（独立闸门，MAPE ≤ prod×(1+tol) + 期满 → 达标毕业）
      ↓ 毕业
  shadow（锦标赛，排第一 + 连续 switch_observation_days 天优于生产 → 切换）
      ↓
  production
```

---

## 三、核心概念与字段

### Slot 字段对照表

| 字段 | 含义 | 默认值 | 谁改 |
|---|---|---|---|
| `training_window_days` | 训练用最近多少天数据 | 30 | 人工调（=AutoResearch `train_days`，不自动 Promote）|
| `switch_observation_days` | Shadow 连续多少天优于生产才建议切换（旧名 `evaluation_window_days`）| 7 | 人工调 |
| `max_shadow_slots` | 影子池上限（锦标赛并发数）| 3 | 人工调 |
| `max_prelaunch_slots` | 预上线池上限（安全闸门并发数）| 2 | 人工调 |
| `auto_switch_enabled` | 是否启用自动切换 | false | 人工调 |
| `cooldown_hours` | 切换后冷却期（小时）| 48 | 人工调 |
| `threshold_mape` | 精度阈值（低于此值触发回滚建议）| 无 | 人工调 |

### ModelVersion.status 四个值

| status | 含义 | 参与什么 |
|---|---|---|
| `production` | 当前线上生产模型 | 每日 cron 必跑 |
| `shadow` | 影子模型（锦标赛）| 每日 cron 跑，限 max_shadow_slots |
| `prelaunch` | 预上线观察中（安全闸门）| 每日 cron 跑，限 max_prelaunch_slots |
| `retired` | 历史退役 | 不跑，保留审计 |

### Shadow vs Prelaunch 语义差异

| 维度 | Shadow（影子）| Prelaunch（预上线）|
|---|---|---|
| 目的 | 竞争替代生产 | 上线前安全闸门 |
| 选择方式 | 锦标赛：N 个 shadow 排序取最好 | 独立闸门：只跟生产比 |
| 通过条件 | 严格优于生产 + 连续 N 天 + 排第一 | MAPE ≤ production×(1+tolerance) + 期满 |
| 期限 | 无期限 | 有观察期（默认 7 天）|
| 数量语义 | 「谁最好」= 1 个赢家 | 「够不够安全」= 可以并存多个 |

多个 Prelaunch 并存无冲突——它们不互相比较，只跟生产比。毕业后进入 shadow 池参加锦标赛。

### train_days 字段族对照

| 字段名 | 所在位置 | 含义 |
|---|---|---|
| `training_window_days` | Slot config（部署侧）| 生产 cron 每天训练用最近 N 天数据 |
| `evaluation_contract.train_days` | AutoResearch run state | AutoResearch 评估用的训练窗口（回测内每天重训时用）|
| 两者关系 | — | 语义完全等价，部署侧和 AutoResearch 侧应保持一致，才能"回测≈上线" |

AutoResearch 的 `train_days` 改动策略：**策略 C（默认不探索 + 可选高级探索 + 建议不自动 Promote）**：
- plateau 时只扩展 `n_trials`，不自动扩展 `train_days`
- plateau 建议写入 `state["latest_suggestions"]`，前端展示给用户决定
- `slot.training_window_days` 由人工在算法部署页面调，Promote 不自动改

---

## 四、分阶段任务

### 阶段 1：后端数据模型 + 训练窗口打通 ✅ 已完成（批次 1）

**已改动文件：**

| 文件 | 改了什么 |
|---|---|
| `services/deployment/models.py` | 新增 `PrelaunchMeta`；`ModelVersion` 加 `prelaunch_meta`、status 支持 prelaunch；`DeploymentSlot` 加 `prelaunch_models`、`max_shadow_slots`、`max_prelaunch_slots`、`training_window_days`；`evaluation_window_days` 重命名为 `switch_observation_days`，AliasChoices 向后兼容读旧 JSON |
| `services/deployment/switch_decision.py` | `evaluation_window_days` → `switch_observation_days` |
| `api/deployment.py` | `SlotConfigUpdate` 加 5 个新字段；`_slot_view` 带 prelaunch_models、training_window_days、max_* 字段；GET/PUT /config 返回完整新字段 |
| `services/autoresearch_self_heal.py` | plateau 不再自动扩展 train_days；改为只扩展 n_trials + 向 state["latest_suggestions"] 追加建议 |
| `services/operator_backends/train_test_split_ts.py` | 加 mode 参数（split/all_train）；all_train 模式直接返回全量训练集 |
| `services/scheduler/tasks/load_forecast_tasks.py` | 新增 make_daily_rolling_task（严格 gap-1-day + slot 读 training_window_days）；_run_single_prediction 加 operator_param_overrides；旧 make_prediction_task 降级为 alias |
| `services/scheduler/tasks/workflow_predictor.py` | run_prediction 加 operator_param_overrides，节点 params 合并覆盖 |
| `main.py` | 注册 lf_daily_rolling（替代 lf_prediction）；传入 slot_store |
| `configs/db.yaml` | backfill cron 改为 0 4 * * *；加注释说明每日流程 |

**阶段 1 验收：** 所有 8 个文件 `py_compile` 通过，无 diagnostics 报错。

---

### 阶段 2：Prelaunch 毕业 + Shadow 切换判定接进 backfill cron

**目标**：把「Prelaunch 观察期毕业」和「Shadow 锦标赛切换资格」都放到 backfill cron 里跑，退掉 DailyPredictionWorker 对生产的依赖。

**动作：**

1. 新建 `services/deployment/prelaunch_lifecycle.py`：
   - `check_graduation(prelaunch: ModelVersion, production: ModelVersion) → GraduationDecision`
   - 输入：prelaunch 模型（含 prelaunch_meta 和 current_rolling_mape）+ 生产模型（含 accuracy_score）
   - 逻辑：elapsed_days >= observation_days → 比较 MAPE vs threshold → graduated / fail / continue
2. `services/deployment/store.py` 加两个操作方法：
   - `promote_prelaunch_to_shadow(slot, workflow_id)` — 清 prelaunch_meta，模型从 prelaunch_models 移到 shadow_models
   - `fail_prelaunch(slot, workflow_id, reason)` — status → retired
3. 改造 `services/scheduler/tasks/load_forecast_tasks.py::make_accuracy_backfill_task`：
   - 原有：补 actual_value + 算 MAPE + 写 accuracy_metrics
   - 追加：更新 shadow.consecutive_better_days；对每个 prelaunch 调 check_graduation；检查 shadow 切换资格
4. `services/precision_ops/daily_prediction_worker.py`：加 `mode: "dev_only"` 标注，前端入口加「仅开发环境」标签

**验收：**
- 单元测试：prelaunch 观察期满 + MAPE 达标 → 毕业为 shadow
- 单元测试：shadow 连续 7 天优于生产 + auto_switch_enabled → 自动切换触发
- 手动流程：入池一个 prelaunch → 把 observation_days 改成 1（快速验证）→ 1 次 backfill 后自动毕业为 shadow

---

### 阶段 3：API 层 + Cron 可编辑可触发

**目标**：前端能操纵调度任务和预上线池，保持旧 API 兼容。

**动作（后端）：**

1. `api/deployment.py` 加接口：
   - `GET /api/deployment/slots/{slot}/prelaunches` — 列表
   - `POST /api/deployment/slots/{slot}/prelaunches` — 入池（candidate_id、workflow_id、observation_days、graduate_tolerance_pct）
   - `POST /api/deployment/slots/{slot}/prelaunches/{workflow_id}/cancel` — 取消
   - `POST /api/deployment/slots/{slot}/prelaunches/{workflow_id}/graduate` — 强制手动毕业
2. `api/precision_ops.py` 的 `/prelaunch*` 端点改成 alias（内部调 deployment 端点，保持响应体格式向后兼容）
3. `api/scheduler.py` 补齐：
   - `PATCH /api/scheduler/tasks/{task_id}` — 改 cron_expr 后立即调 SchedulerEngine.register_task 热更新
   - `POST /api/scheduler/tasks/{task_id}/trigger-now` — 同步跑一次
   - `POST /tasks/{task_id}/start` — 真正调 SchedulerEngine（不只是改 JSON）
   - `POST /tasks/{task_id}/stop` — 真正调 SchedulerEngine.remove_job
4. `main.py` 启动时预置 3 条负荷预测 + 2 条光伏 cron 到 tasks.json（幂等，已存在则不覆盖，以 tasks.json 为运行时唯一真源）

---

### 阶段 4：前端算法部署页面改造

**目标**：UI 上把生产/影子/预上线三段展示清楚；cron 可编辑可触发。

**动作：**

1. `AlgorithmDeploymentPage.tsx` 加第 4 个 Tab「预上线」（?tab=prelaunch 深链）
2. `deployment/ModelManagementTab.tsx` 三区布局：
   ```
   ┌─ Slot: default ──────────────────────────┐
   │ 🟢 生产模型  MAPE 4.21%                   │
   │─────────────────────────────────────────│
   │ 影子池 (N/max_shadow_slots)              │
   │   • wf-A  MAPE 3.89%  连续优于 5 天 ⚡  │
   │─────────────────────────────────────────│
   │ 预上线池 (M/max_prelaunch_slots)         │
   │   • wf-X  观察 4/7 天  4.05% ✓ 达标    │
   └─────────────────────────────────────────┘
   ```
3. 自动切换配置弹窗加三个新字段输入框：training_window_days（7~730）、max_shadow_slots（1~10）、max_prelaunch_slots（1~5）
4. `deployment/SchedulerTab.tsx`：
   - 表格加 cron_expr 列
   - 操作列加「编辑」（改 cron_expr）+ 「立即触发」按钮
   - 顶部说明卡：「本 slot 每日流程：01:00 拉数据 → 02:00 训练+预测（≤T-1，预测 T+1）→ 04:00 回填精度」
5. 新增 `deployment/PrelaunchTab.tsx`：预上线队列 + 手动毕业/取消/入池
6. `services/deploymentApi.ts` 加封装：updateScheduledTask、triggerNow、enterPrelaunch、cancelPrelaunch、graduatePrelaunch

---

### 阶段 5：精度运营页面瘦身 + 引导

**目标**：精度运营收敛为「只读健康中心」，为根因分析预留位置。

**动作：**

1. `PrecisionOpsDashboardPage.tsx`：
   - 标题改：「模型健康中心（只读）」+ 副标题引导到算法部署
   - **保留**：精度排行榜、切换历史、精度趋势图
   - **移除**：预上线 Tab（已迁到算法部署）、加速演示 worker 按钮（下沉到开发者工具）
   - **预留**：「根因分析」占位 Tab（未来加数据漂移检测、概念漂移检测、归因分析）
2. 加速演示 worker 入口标注「仅开发环境可用」

---

### 阶段 6：端到端验证

**步骤：**

1. 环境：aip_web conda，bash aip.ps1
2. 定时调度 Tab 把 3 条 cron 改成 `* * * * *`（每分钟）全部 Start
3. 观察每分钟循环：station_data 新增 → lf_daily_rolling 跑 1+N+M 次 workflow → lf_accuracy_backfill 补精度 + 检查毕业/切换
4. 入池一个 prelaunch（observation_days=3）→ 等 3 分钟自动毕业为 shadow → 出现在影子池
5. 影子 MAPE 连续 3 分钟优于生产 + auto_switch_enabled → 自动切换到 shadow
6. 切换历史 Tab 记录此事件

**预期结果：** 全程无手动干预，数据从灌入到模型切换全流程走通。

---

## 五、时间估算

| 阶段 | 工作量 |
|---|---|
| 阶段 1（已完成）| 0.5 天 |
| 阶段 2 | 0.5 天 |
| 阶段 3 | 0.5 天 |
| 阶段 4 | 1 天 |
| 阶段 5 | 0.5 天 |
| 阶段 6 | 1 小时 |
| **合计** | **≈ 3 天** |

---

## 六、暂不纳入本次的后续工作

| # | 工作 | 说明 |
|---|---|---|
| 1 | 训练/预测模板拆分（bundle 契约）| 已讨论，决定暂不拆；用回测模板直接上线 |
| 2 | AutoResearch 结构参数自动 Promote | train_days 等结构参数留给人工决策 |
| 3 | 根因分析（数据漂移/概念漂移检测）| 精度运营页面预留 Tab |
| 4 | 多 slot 并行前端切换器 | 架构上支持，前端暂不做 |
| 5 | 候选自动入预上线（无人工触发）| 目前是人工触发，后续可加规则自动化 |

---

## 七、涉及文件索引

### 后端

| 文件 | 职责 |
|---|---|
| `services/deployment/models.py` | 部署槽位数据模型：PrelaunchMeta、ModelVersion、DeploymentSlot、SwitchEvent |
| `services/deployment/store.py` | JSON 持久化：slots.json（槽位快照）+ switch_log.json（切换日志 append-only）|
| `services/deployment/switch_decision.py` | 切换决策引擎：check_switch_eligibility、execute_switch、execute_rollback |
| `services/deployment/prelaunch_lifecycle.py` | 预上线毕业判定逻辑（阶段 2 新增）|
| `services/deployment/rolling_window.py` | 训练窗口计算：compute_training_window（gap-1-day + max_window_days 截断）|
| `services/scheduler/tasks/load_forecast_tasks.py` | 负荷预测 cron 任务工厂：make_data_pull_task、make_daily_rolling_task、make_accuracy_backfill_task |
| `services/scheduler/tasks/workflow_predictor.py` | 工作流执行器：run_prediction（支持 operator_param_overrides）|
| `services/operator_backends/train_test_split_ts.py` | 时序数据切分算子（支持 mode="all_train"）|
| `services/autoresearch_self_heal.py` | AutoResearch 自愈规则（plateau 只扩展 n_trials，不扩展 train_days）|
| `api/deployment.py` | 部署 HTTP 端点：slots、versions、switch、rollback、config、prelaunches |
| `api/scheduler.py` | 调度器 HTTP 端点：tasks CRUD + PATCH cron + trigger-now + start/stop |
| `configs/db.yaml` | 数据库配置 + cron 默认表达式种子 |
| `main.py` | FastAPI 启动、任务注册、slot_store 注入 |

### 前端

| 文件 | 职责 |
|---|---|
| `pages/AlgorithmDeploymentPage.tsx` | 算法部署一级页面（4 个 Tab）|
| `pages/deployment/ModelManagementTab.tsx` | 模型管理 Tab（三区布局：生产/影子/预上线）|
| `pages/deployment/SchedulerTab.tsx` | 定时调度 Tab（可编辑 cron + 立即触发）|
| `pages/deployment/PrelaunchTab.tsx` | 预上线 Tab（入池/观察进度/手动毕业）新增 |
| `pages/deployment/PipelineTab.tsx` | 数据管线 Tab（已有）|
| `pages/PrecisionOpsDashboardPage.tsx` | 精度运营「只读健康中心」（移除预上线 Tab，预留根因分析 Tab）|
| `services/deploymentApi.ts` | 部署相关 API 封装（加 prelaunch + cron 操作方法）|

<!-- @AI_GENERATED: end -->
