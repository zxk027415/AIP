# AutoResearch 代际演进详解

> ⚠️ **本文件是精简摘要版。完整的答辩级文档请直接使用：**
> 
> **`docs/specs/迭代历程详版.md`（900+行，答辩首选）**
> 
> 该文件包含：V1 六阶段的每一步解决什么问题、V2 八大需求对照表、V3 十个服务拆分 + 持久化层完整设计、V4 三链架构总流程大图 + 五层模型 + 50轮诚实复盘（✅/❌表）+ 6项代码修正、V6 五层闭环 + Research Action + Novelty前置门控 + 三级实验调度、V4 vs V6 Planner深入对比（答辩最容易被追问的点，含"action固定性"的完整兜底设计和话术建议），以及9道答辩问答预案。
>
> 本文件保留精简版作为快速回忆参考。

---

## 一、全局主线

AutoResearch 的演进不是一开始设计好的蓝图，而是每代用真实实验数据逼出来的：

```
V1 能跑+会推理 → V2 会提问（规划）→ V3 能稳定+Research OS
    → V4 可观测（控制面重构）→ V6 画像/证据驱动 → V7 平台级集成
```

**一条贯穿始终的认知主线**：从"自动调参器"到"基于证据、由数据画像驱动的研究操作系统"。

| 代际 | 时间 | 一句话定位 |
|------|------|-----------|
| V1 | 2026-04-30 ~ 05-07 | 一周搭出完整能力栈：能跑、会推理、有记忆 |
| V2 | 2026-05 | 规划升级：让系统先提问再实验 |
| V3 | 2026-05-21 ~ 05-22 | 工程稳定 + Research OS 方向 |
| V4 | 2026-05-22 ~ 05-28 | 控制面重构：过程可观测、可控制 |
| V6 | 规划中 | 画像驱动 + Evidence Ledger + 三级实验调度 |
| V7 | 2026-07 | AIP 平台前端重构，AutoResearch 接入算法生命周期 |

> 无第五代，第四代直接跳到第六代规划。

---

## 二、V1 第一代：从零到工业级 AutoML（一周）

### 起点与痛点

业务场景：负荷预测算法工程师手工调参，一天调 5~10 次，靠直觉、结论不可复现、反复踩坑。

为什么不用现成 Grid Search / 贝叶斯优化：场景有**四层可调维度**（参数/特征/模型/数据），很多是离散选择+结构开关，传统方法不够灵活。

### V1 六阶段演进

每一步解决上一步暴露的问题：

```
Stage 1-3（基础设施）→ Stage 4（智能搜索）→ Stage 4B（假设驱动）
    → Stage 4C（实验严格化）→ Stage 5A/5B（跨run学习）→ Stage 5（架构精炼）
```

#### Stage 1-3：让实验可追溯

**Stage 1 — 候选池可追溯**：候选记录新增 `challenger_override`、`effective_structure_patch`、`effective_parameter_patch`、`diff_from_baseline`、`source_run_id+iteration`，前端加"详情抽屉"。解决"跑完不知道用了什么参数"的问题。

**Stage 2 — GLM 建议增强**：回测后自动算 `error_profile`（平均/最大MAPE、偏差方向、高误差天、工作日/节假日差距）和 `data_coverage`，注入 GLM prompt。效果：建议从"拍脑袋改 train_days"升级成"因为周末误差大，建议加强节假日特征"。

**Stage 3 — 饱和检测**：实现 `_is_parameter_saturated`，最近 K=4 轮改善都 < 5% 阈值 → 参数层饱和 → 自动切换结构探索。

#### Stage 4：统一搜索空间注册表（四层架构）

问题：每次只能调 train_days 几个参数，特征/模型动不了；换模板要重写规则。

解法：把"可调什么"写成 JSON 注册表，分四层（训练/特征/模型/数据），每个参数带 `type`/`options`/`patch_target`。

```
注册表四层：
  训练层：train_days / n_trials / cv_folds
  特征层：lags / rolling_window / holiday 开关
  模型层：ensemble_mode / active_models
  数据层：daily_horizon / sliding_window
```

**阶段化激活**：按顺序逐层放开（训练→特征→模型→数据），每层独立判定饱和才解锁下一层，防止系统一开始就跑太宽。

**集成模式搜索**：支持 `single_best` / `all_adaptive` / `subset_adaptive`，权重用 OOF RMSE 逆权重。

#### Stage 4B：假设驱动实验（最关键跃升）

问题：GLM 每次重新推理不积累、建议没"为什么"、改了后没验证有没有改善。

核心改造：GLM 走**观察→假设→设计→预期→回退**五步思维链。

每个 proposal 必须有：`observation` / `hypothesis` / `hypothesis_type` / `expected_outcome` / `fallback_if_failed` / `deepen_if_verified`。

```
实验不再是"试试看"，而是：
  已有观察 → 假设原因 → 预期结果数值 → 跑实验
  → 验证成立(写入有效方向 → 深挖) 或 否证(写入否证集 → 回退)
```

**patch_fingerprint 去重**：最初用文本精确匹配，但 GLM 措辞不同 → 改为按 patch 实际改动内容（结构开关/节点参数/全局配置）提取哈希指纹去重。

#### Stage 4C：实验严格化

四个科学原则：
1. **单变量控制**：每个候选标 `primary_variable`，只改一个维度 +5 分（评分倾斜）。
2. **优先级排序**：`hypothesis_priority = expected_improvement × confidence_weight`（high=1.0/medium=0.7/low=0.4）。
3. **预算管理**：某类型连续 ≥3 轮 → 下一轮 -30 分强制转向，防死磕。
4. **对照组机制**：每 5 轮跑一次"不改任何东西"回测 vs 第 1 轮 baseline，差 >1% 判定数据漂移。

#### Stage 5A/5B：跨 run 学习

问题：单次 run 内聪明，但每次新 run 从零开始。类比：实习生每次从零学 vs 经验员工有笔记本。

**Stage 5A — run_insight（写笔记本）**：run 结束自动生成结构化复盘，含 `learned_rules` / `ineffective_attempts` / `open_questions` / `recommended_starting_config_for_similar`，存到 `autoresearch_run_insights/<run_id>.json`。

**Stage 5B — 跨 run 知识传递**：新 run 启动时按场景指纹匹配历史 insight，注入首轮 GLM prompt。

场景指纹：`granularity_minutes + span_days + weekend_weekday_gap + outlier_ratio + seasonality_strength`。

**关键策略 — 不锁定起点，只加权**：历史推荐 train_days=45 不是 `override=45`（锁定），而是采样时权重 ×2（加权）。锁定会偏离自主探索，加权能加速但保持多样性。

#### Stage 5：架构精炼（解决采样和建议"打架"）

跑起来发现采样和建议是两套系统各自为政，4 个修复：

1. **采样尊重 runtime_patch**：`_build_locked_params_from_runtime_patch` 提取已 apply 锁定参数，采样器跳过，GLM 建议永不被覆盖。
2. **重新采样替代偏移**：旧逻辑随机偏移 ±7 可能产出 train_days=2 极端值，改为从注册表 options 里选不等于当前值的值。
3. **参数约束引擎**：4 条约束（lags ≤ train_days、single_best 不配 active_models 等），最多重试 5 次。
4. **GLM 意图模式**：GLM 不再写 node_id（经常写错），只写 intent（`adjust_param/enable_node/disable_node/change_ensemble`），后端翻译器转成合法 patch。

**批量评估**：`batch_size > 1`，N 组取最优，相同轮数覆盖 3-5 倍搜索空间。

### V1 总结

一周搭出完整能力栈，系统从"能跑"变成"有记忆、会推理、跑完能复盘"。但本质还是**自动调参器**——被动试参数，不知道自己在研究什么问题。

---

## 三、V2 第二代：规划"会思考的研究员"

### 核心理念

V1 反思：**系统还是在被动试参数，它不知道自己在研究什么问题。** GLM 收到一堆原始数字自己猜该关注什么，假设质量不稳定。

V2 核心：让系统**先提出问题，再去做实验**。

### 目标架构：多智能体流水线

```
画像器（纯计算） → 分析师（纯规则归因） → 问题生成器（纯规则）
    → 假设生成器（唯一调 GLM 的角色）→ 设计师（纯规则翻译）→ 验证器 → 回测
```

**核心设计原则——只有假设生成器调 GLM，其余全部确定性规则**：省 token、可审计、可调试。

降级策略：多智能体模式 → GLM 失败 → 单智能体模式 → GLM 仍失败 → 纯随机采样。

### 八大需求（相比 V1 新增）

| # | 需求 | 为什么新增 |
|---|------|-----------|
| 1 | 三集画像（训练/验证/测试集分别画像） | V1 只看总分 MAPE，不知道哪个时段最差、有没有过拟合 |
| 2 | 研究问题生成器 | V1 GLM 自己猜关注什么；V2 系统告诉 GLM"你要回答这个问题" |
| 3 | 知识库 L1-L4 分层 | V1 经验只是平铺；V2 让经验可衰减、可复活、可冲突解决 |
| 4 | 阶段性反思 | V1 饱和检测被动触发；V2 主动反思策略（每 20 轮） |
| 5 | 实验质量评分 | V1 只看预期收益；V2 加知识增益、风险维度 |
| 6 | 多智能体流水线 | V1 逻辑全揉在一个主循环；V2 角色边界清晰 |
| 7 | 可视化（时序对比/研究问题/反思记录） | V1 只有饼图热力图 |
| 8 | 统一 API 接口 | 规范化对外能力 |

### 关键数据结构设计

**知识声明（KnowledgeClaim）— 每条经验带完整证据链：**

```json
{
  "claim": "train_days=45 在高周期性场景下优于 30",
  "condition": {"seasonality_strength": ">0.7"},
  "evidence": ["run-a", "run-b", "run-c"],
  "confidence": 0.85,
  "layer": "L2",
  "status": "active"
}
```

**知识生命周期状态机：**

```
候选 → 活跃（3+个run支持）→ 衰减中（30天未验证，置信度-0.1）
    → 过时（置信度<0.3）→ 活跃（新run又支持，复活）
活跃 → 矛盾（出现方向相反知识）→ 研究问题（无法解决时转化）
```

**注入权重公式：**
```
最终权重 = 层级基础权重(L4=1.0/L3=0.8/L2=0.5/L1=0.2)
         × 类型倍率(因果候选=2.0/相关=1.0)
         × 场景匹配度(匹配=1.0/不匹配=0.3)
```

### V2 定位

V2 是规划代，把"会思考的研究员"的完整设计说清楚了。它产出的需求/设计/任务三篇文档，是后续 V3/V4 工程落地的蓝图。

---

## 四、V3 第三代：工程落地 + Research OS

### 待解决的工程债务

| 问题 | 严重性 |
|------|--------|
| 死锁/僵尸运行 | 系统跑着跑着挂，进程没清干净 |
| 断点恢复缺失 | 中途崩溃，已完成实验全丢 |
| `except Exception: pass` 满天飞 | 出了问题根本找不到原因 |
| 状态丢失 | cancel events / comparison store 没持久化 |

### 工程修复：状态落盘 + 服务拆分

#### 新增三个持久化组件

| 组件 | 存储位置 | 内容 |
|------|---------|------|
| `autoresearch_run_store.py` run快照 | `autoresearch_runs/{run_id}.json` | status/progress/best_candidate/iterations |
| `autoresearch_trial_ledger.py` 账本 | `autoresearch_runs/{run_id}/trials.jsonl` | 每轮候选 override/patch/指标/失败信息 |
| `autoresearch_persister.py` 门面 | 统一读写接口 | 封装上述两者 |

#### 主循环逻辑拆成 10 个独立服务

原来 `workflows_enhanced.py` 把所有逻辑揉在一起，V3 拆出：

```
autoresearch_evaluator      ← 候选评分/Pareto/排序
autoresearch_proposal_manager  ← proposal 构造/打分/应用
autoresearch_batch_selector    ← 并发 batch 选择
autoresearch_hypothesis_tracker  ← 假设验证/连续类型计数
autoresearch_convergence_monitor  ← 收敛/饱和检测
autoresearch_diagnostics   ← 误差画像/诊断
autoresearch_insight_builder  ← run insight 生成
autoresearch_memory_store    ← 相似历史 case
autoresearch_auto_apply_policy  ← GLM 自动应用策略
autoresearch_self_heal      ← 运行时自愈
```

**意义**：以后改某个逻辑只动对应服务文件，不用在超长主文件里硬改。

#### 自愈逻辑（autoresearch_self_heal.py）

三类情况自动处理：
1. 无测试数据 → 自动关闭严格窗口过滤和目标掩码
2. 训练数据不足 → 自动下调 train_days 和 backtest_train_days
3. 连续平台期 → 自动扩大 auto_tune_n_trials 和 train_days 搜索范围

#### 可选扩展点（未设默认）

- **Optuna fallback**：当 `sampler_backend == "optuna"` 走 Optuna 风格采样兜底。
- **ASHA 多保真调度**：先用少窗口粗筛，有希望的候选提升到完整窗口。开关 `multi_fidelity_enabled`，未设默认因改变 batch 执行路径需真实验证。

### Research OS 演进方向

V3 正式提出 **Research OS** 概念——把 AutoResearch 从"工具"升级为"操作系统"：

**核心数据模型**：`Study → Trial → Decision → Artifact → KnowledgeClaim`

**五层路线图**（厨房类比）：
```
P0 可靠运行层（厨房不能着火）
  P1 实验账本层（每道菜有完整记录）
    P2 主循环解耦层（厨师分工明确）
      P3 高效搜索层（菜单有策略创新）
        P4 研究智能层（能自己研发新菜）
```

对标系统：Optuna、Google Vizier、Hyperband/ASHA、auto-sklearn、MLflow，借鉴 Trial/Study 数据模型和分阶段评估设计。

### V3 定位

把"先稳定、再演进"的原则落地，补工程底座：状态持久化、Trial/Decision 账本、组件化、单测覆盖（50 passed, 22 warnings）。这些对短期指标提升不显眼，但对做成真正可用的自动研究系统很关键。

---

## 五、V4 第四代：控制面重构——让过程可观测

### 核心命题

工程稳了之后，真正的问题浮现：**跑了 50 轮之后，产出的结论是否可信、可复验、可沉淀？**

V4 的目标不是"跑更多轮"，而是让系统从"盲目调参"进化为"有方向、有证据、有知识沉淀的研究系统"。

### V4 三链架构

V4 建立三条核心链路，交汇点是 **Evidence Record（证据记录）**：

```
实验执行链路（Planner/Patch/Compare）
        ↓
    Evidence Record（三条链路交汇点）
      /           \
候选晋级链路          研究认知链路
（Candidate/Verify/Promote）  （Question/Hypothesis）
        ↓
知识/反思/下一轮策略
```

如果只看 Top MAPE，会丢掉真正要回答的问题：这个结果是否可信、是否新颖、能否复验、能否迁移。

### 五层模型

| 层级 | 回答的问题 |
|------|-----------|
| 输入层（dataset_profiler） | 基线是谁？搜索空间是什么？窗口怎么设？ |
| 规划层（candidate_planner） | 该试 parameter/feature/model/data 还是 risk？ |
| 执行层（主循环） | 实际 patch 是什么？回测有没有可比结果？ |
| 证据层（autoresearch_evidence） | 是单窗口偶然还是多窗口确认？是否重复？ |
| 沉淀层（knowledge_layer/reflection） | 能否 Promote？能否成为知识？下一阶段怎么跑？ |

### 相比 V3 的六大新增

#### 1. 候选规划器（Candidate Planner）

核心变化：从"并行候选"升级为"先规划方向，再并行验证"。

五种方向类型：parameter / feature / model / data / risk。

Planner 维护 `exploration_health.scoreboard`，判断是否偏科（如 `parameter_overdominance=true`）。

**分配逻辑：按 batch_size 分角色**

- batch_size = 1：不启用多方向规划
- batch_size = 3（默认）：组1 `exploit`（利用主候选）/ 组2 `diversify`（特征/模型）/ 组3 `explore_risk`（数据/风险）
- batch_size ≥ 5：同一轮覆盖全部五类方向

每个 slot 的 `planner_reason` 字段明确写出原因，不黑盒。

#### 2. Research Cockpit（前端五卡视图）

让研究过程第一次变得可观测：

```
Experiment 实验卡（并行组状态/patch/失败原因）
    → Evidence 证据卡（强度分布/复验结果）
    → Question 问题卡（研究问题生命周期）
    → Knowledge 知识卡（分层治理/置信度）
    → Strategy 策略卡（探索健康度/方向分布）
```

复盘一个 run 按此顺序读，比"先看 Top-3 MAPE"更稳。

#### 3. Evidence 统一为晋级链唯一事实来源

候选晋级完整流程：

```
回测正收益
    → 写入候选池（candidate_signature 标识）
    → Novelty Audit（基于 patch 内容哈希的去重）
      → is_novel=true → 进入候选池 Top/Pareto
      → is_novel=false → 标记重复，不当新突破
    → 加入复验池 → 多窗口复验
      → passed → 允许 Promote
      → failed → 不能 Promote
```

**三个最容易混的指纹/签名/哈希：**

| 名称 | 管什么 | 用在哪 |
|------|--------|--------|
| `patch_fingerprint` | 单次实验具体改了什么 | evidence / question lifecycle |
| `candidate_signature` | 候选完整配置 | candidate pool / verification queue 去重 |
| `scenario_condition_hash` | 场景条件 | knowledge ingest/inject 迁移判断 |

#### 4. 复验池闭环（Verification Queue）

把"Top 候选直接 Promote"改成：**候选池 → 复验池 → 多窗口复验 → Promote**。

核心规则：
- 入池按 `candidate_id` 和 `patch_signature` 去重
- 串行执行，同一时间只允许一条 running
- Promote 默认要求至少一条 passed；人工跳过必须显式 `force=true`
- **单窗口不可信原则**：正确顺序 = `干净baseline → AutoResearch → candidate → verification → passed → promote → 新baseline`

#### 5. Baseline Cache 内容哈希

修复：旧 cache 只按 24h TTL，baseline 模板/窗口/契约变了但 key 没变会复用旧结果。

新 cache key 覆盖：`baseline_workflow_id + 完整内容 + windows + baseline_contract + baseline_config_override`。命中条件：cache 存在 + age<24h + 内容 hash 一致。

#### 6. 复验池与 AutoResearch 并行

V4 后期改进：复验池不再因活跃 AutoResearch run 被硬阻断，改为：
- 复验使用独立 `_VERIFICATION_BACKTEST_POOL`（1 worker）
- AutoResearch 活跃时写 warning 但不阻断复验
- 内存水位保护：可用内存 < 1024MB 时拒绝启动复验（`force=true` 可绕过）

### 50 轮诚实复盘（P0.7）

对 run `ares-9c429d5ed43c` 跑满 50 轮：

| 验证维度 | 结果 |
|---------|------|
| 多方向探索覆盖 | ✅ 五类方向都有覆盖 |
| group 1 不再固定 parameter | ✅ 最长连续 parameter streak 只有 3 轮 |
| Research Question 去重 | ✅ 98 条 → 7 条带生命周期 |
| Evidence 落账 | ✅ 130 条按方向记录 |
| Knowledge 治理 | ✅ active/candidate/conflicted 状态统计 |
| Top 候选是否新突破 | ❌ Top-1 MAPE=4.2421 历史已出现 4 次 |
| 多窗口证据 | ❌ 130 条全是 insufficient_evidence |
| Reflection 消费证据 | ❌ exploration_coverage 输出 0.0 |
| Knowledge 置信度 | ❌ 单 run claim confidence 过高（1.0） |

**V4 诚实结论：控制面改善了"过程质量"，但还没改善"结论质量"。**

这个发现直接催生了 V6 的三个核心解法：画像驱动选路 + Novelty 前置门控 + Evidence Ledger。

### 复盘后 6 项代码调整

| # | 调整 | 解决的问题 |
|---|------|-----------|
| 1 | Novelty Audit 增强 | 同 MAPE 反复出现却当新突破 |
| 2 | Evidence Contract 统一 | windows_total=0、缺 failure_reason |
| 3 | Reflection 消费真实 scoreboard+evidence | coverage 一直 0.0 |
| 4 | TrainProfile 新增 `profile_quality` 字段 | 画像 fallback 到空下游不知道 |
| 5 | `normalize_scenario_fingerprint()` 统一指纹 | ingest/inject 指纹不一致 |
| 6 | GLMQuestionResult 新增 `disabled_reason` | 分不清 GLM 生成还是规则 fallback |

---

## 六、V6 第六代：画像驱动的研究系统（规划中）

### V4 数据诊断的根因

V4 50 轮复盘的关键信号：
- `duplicate_count=4 / new_count=1`：重复探索仍偏高
- `parameter_overdominance=true`：feature/model/data 没稳定成为主探索方向
- 画像数据有了但没参与选择研究方向的决策
- Evidence 分散，各模块各存一套，没有统一事实来源
- 探索缺乏语义，只是 flat 参数枚举

**根因**：系统还是在"盲搜"。

### V6 核心：五层闭环

```
Dataset Profile + Error Shape
    → Research Question（从画像直接产生）
    → Research Action Planner（问题→有语义的实验动作）
    → Executable Patch（由 PatchCompiler 确定性编译）
    → Backtest / Verification（三级调度）
    → Evidence Ledger（中心事实表）
    → Knowledge / Anti-pattern
    ↑____________________________↑（反馈回 Planner 和 Research Question）
```

### 六大核心变化

#### 1. Profile 驱动选路

画像信号直接决定探索方向（不再只是展示字段）：

| 画像信号 | 优先 action |
|---------|------------|
| 波动强、峰谷切换明显 | rolling/stat/diff |
| 周末/节假日差异明显 | calendar feature ablation |
| 近期漂移强 | 短训练窗口 + regularization |
| 天气相关强 | weather probe |
| 数据短或噪声大 | 限制高复杂模型 |

#### 2. Research Action（有语义的实验动作）

从 flat 参数列表升级为 typed research action，7 类：

```
short_window_vs_long_window
calendar_feature_ablation
rolling_window_family
ensemble_weight_strategy
model_regularization_profile
weather_sensitivity_probe
horizon_density_probe
```

每个 action 带完整元数据：`action_id / target_direction / applicable_profile / patch_template / max_changed_variables / risk_level / expected_evidence / stop_conditions / fallback_actions / known_anti_patterns`。

#### 3. Novelty 前置门控

从事后审计前移为执行前拦截：
- 同 `patch_signature` 已跑过 → 跳过（不消耗回测资源）
- 同 `changed_variables` 组合重复过多 → 降权
- 近邻 patch 已 `multi_window_rejected` → 默认跳过
- 同 action 连续无效 → cooldown
- 跳过原因写入 `planner_reason`（不黑盒）

#### 4. Evidence Ledger（中心事实表）

不再让 candidate/question/knowledge 各存一套不可对齐结论，统一记录所有维度：`run/iteration/group/action_id/research_question_id/patch_fingerprint/windows_total/windows_challenger_better/evidence_strength/failure_reason/novelty_result/状态`。

**派生关系**：
- `Candidate Pool ← positive evidence`
- `Verification Queue ← 需复验的 candidate evidence`
- `KnowledgeLayer ← multi_window_confirmed 或稳定重复证据`
- `Research Question lifecycle ← evidence 自动推进`

#### 5. 三级实验调度

| Stage | 策略 | 限制 |
|-------|------|------|
| A: cheap probe | 1 窗口、低 trials | 输出不能进 active knowledge |
| B: formal compare | 3 窗口正式比较 | 生成候选证据 |
| C: verification | 5 窗口复验 | 只有 passed 才 Promote |

Stage A positive 只能决定是否进 Stage B，不能升级知识；只有 Stage C passed 才允许 Promote 或 active knowledge。**避免单窗口假阳性**。

#### 6. 4 个明确 Service

```
Analyst（profile+error+evidence→研究问题）
    → ResearchActionPlanner（问题→action，novelty/risk/cost 排序）
    → PatchCompiler（action→runtime patch，白名单+结构合法性）
    → 回测执行
    → EvidenceCritic（评价证据强度/失败原因/入复验/沉淀知识）
    → 回到 Analyst
```

### V4 Planner vs V6 Action Planner 对比

| 维度 | V4 Candidate Planner | V6 ResearchActionPlanner |
|------|---------------------|--------------------------|
| 规划对象 | 方向（5类粗粒度标签） | research action（有语义的实验动作） |
| 决策依据 | layer scoreboard 的 coverage_gap | Profile 信号 + Evidence + novelty/risk/cost 排序 |
| 画像作用 | 只是展示字段，不参与选方向 | **参与选方向**（波动强→rolling；周末敏感→calendar ablation） |
| Novelty | 事后审计（跑完才发现重复） | **前置门控**（执行前拦截） |
| 停止条件 | 无（靠饱和检测被动触发） | 每个 action 自带 `stop_conditions` |
| 实验调度 | 单一窗口 | 三级调度（1/3/5窗口） |
| GLM 角色 | proposal 来源之一 | 只提问题/假设/意图，不写 patch |

**三句话总结区别**：

1. V4 方向是"粗篮子"（`target_direction=feature` 不保证真的只改 feature）；V6 action 是有语义的实验动作（`calendar_feature_ablation` 自带为什么、怎么停、什么反模式）。
2. V4 选方向靠 coverage_gap（试得少就选）；V6 选 action 靠画像（波动强才选 rolling）。
3. V4 Novelty 事后审计浪费资源；V6 前置门控 + 三级调度，最小资源完成去重和分级验证。

### V6 的 action 是固定的吗？

**是的，静态注册在 `load_forecast_v3.json`，设计上显式接受不穷尽（先 15-25 个）。**

出现未覆盖时的三层兜底：
1. action 自带 `applicable_profile` + `fallback_actions`，在已有集合内流转
2. 降级到 conservative planner，回退 v1/v2 flat registry 采样，系统不停摆
3. action 是 JSON 配置不是硬编码，新场景沉淀成 `research_question(open)` 后补一条 JSON 条目即可

**真正没解决的边界**：GLM 动态提议全新 action 维度并直接执行——这是**有意为之的工程边界**，让 GLM 直接写可执行 patch 会破坏确定性和可审计性，这个代价 V6 不接受。

---

## 七、V7：AIP 平台前端重构

V7 是平台级集成，不是 AutoResearch 模块的代际迭代，但它把 AutoResearch 接入了完整的算法生命周期工作台。

### 问题

当前导航像历史功能堆叠：工作流/模板/AutoResearch/精度运营之间没统一入口。

### 新核心路径

```
行业场景 → 推荐方案/模板 → 工作流开发
    → AutoResearch 回测优化 → 精度运营 → 部署上线
```

### AutoResearch 在新工作台中的位置

不再只是独立页面，成为工作流版本的优化工具：

```
算法管理 → 选择工作流版本 → 自动化回测
    → 候选版本 → 多窗口复验 → Promote
    → 回到算法管理形成新版本 → 进入算法运营
```

第一阶段先做入口和参数打通（携带 workflow_id 上下文），明确区分：单窗口候选、复验通过候选、可 Promote 版本、生产版本。

---

## 八、每代"比上一代多解决了什么"

| 代际 | 上一代遗留问题 | 本代核心解法 |
|------|--------------|------------|
| V1 | 纯手工调参 | 自动搜索 + 假设驱动 + 跨 run 学习 |
| V2 | V1 被动试参，不知研究什么 | 先提问再实验，多智能体分工，知识分层 |
| V3 | V2 工程债务：死锁/无断点/状态丢 | 持久化账本 + 服务拆分 + Research OS 蓝图 |
| V4 | V3 能力有了但过程不可观测 | 三链架构 + 控制面五卡 + Evidence 统一 + 复验闭环 |
| V6 | V4 过程质量≠结论质量，盲搜+Evidence 分散 | 画像驱动选路 + Evidence Ledger + Novelty 前置 + 三级调度 |
| V7 | AutoResearch 是独立工具，未接入生命周期 | 平台工作台，自动化回测成为算法开发一环 |

**贯穿始终的认知主线**：这不是一开始设计好的蓝图，而是每一代用真实数据逼出来的演进。每一次"过程质量改善了但结论质量没改善"的发现，都直接催生下一代设计。

---

## 九、答辩预案

**Q: 为什么不用现成的 AutoML（Optuna/贝叶斯优化）？**

A: 场景有四层可调维度，很多是离散选择+结构开关，传统方法不够灵活。V3 也加了 Optuna fallback 作为可选采样后端，借鉴了 Trial/Study 数据模型和分阶段评估。

**Q: V4 跑了 50 轮 Top 候选还是历史重复，是不是失败了？**

A: 不是失败，是诚实复盘。V4 目标是"过程可观测可控制"，这个目标达成了（多方向覆盖✅、问题去重 98→7✅）。Top 重复恰恰是控制面暴露问题的能力——以前根本不知道是重复。这个发现直接催生了 V6 的三个核心解法。

**Q: 单窗口好结果为什么不能直接上线？**

A: 单窗口可能只是偶然收益/特定时间窗过拟合/历史重复。必须走 `candidate → novelty audit → verification queue → 多窗口 passed → promote`，这是 V4 确立、V6 强化的核心原则。

**Q: GLM 在系统里到底干什么？会不会乱来？**

A: 只有假设生成器调 GLM，其余全是确定性规则。GLM 只能提问题/假设/实验意图（intent），不能直接写可执行 patch——intent 由代码侧 PatchCompiler 转成合法 patch，经白名单+风险门控+审计后才能执行。降级链：多智能体→单智能体→纯随机。

**Q: V6 的 action 是固定的吗？出现 action 没覆盖的情况怎么办？**

A: 是静态注册的，设计上显式接受不穷尽。三层兜底：① action 自带 applicable_profile + fallback_actions；② 找不到匹配 action 时降级到 conservative planner，系统不停摆；③ action 是 JSON 配置不是硬编码，新场景补一条 JSON 条目即可覆盖，不改代码。真正没解决的是让 GLM 动态提议全新 action 并直接执行——这是有意为之的边界，用保守性换可审计性。
