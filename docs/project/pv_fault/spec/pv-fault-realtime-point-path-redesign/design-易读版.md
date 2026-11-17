<!-- @AI_GENERATED -->
# 设计易读版：光伏天/点双产品链

> 这是什么：`design.md` 的通俗对照，并叠加 2026-08-25 产品融合结论。
>
> 权威口径：
>
> - 工作流 / 真实点 / slot / 治理 / replay：`design.md` A0–A16  
> - 四段闭环、确认箱、累计、告警接法：`fusion-design.md`（冲突时以融合设计为准）
>
> 文档状态：2026-08-25  
>
> 读法建议：先读「融合后怎么走」→「六条结论」→「回放循环」→ 需要细节再翻 `fusion-design.md`。

## 融合后怎么走（先看这张）

G0–G8 已经把天/点工作流骨架跑通。接下来不是再开一条 `pv_fault` 产品，而是把蓝图里的人机闭环接到这两条链上。

```text
① 打标工作流 → 提案（不能训练）
② 专家工作台 → 确认箱 LabeledDatasetVersion（必带 slot）
③ 诊断工作流（pv_day 或 pv_point）只吃同槽位确认数据 / 快照版本
④ 复核工作台 → 新确认箱 → 纳入累计 → 快照 +1 → 显式重训
```

①③ 在画布；②④ 不在画布。  
日内滚动告警 = `pv_point` 的 `replay_activity` + 告警状态机，不用老 TSC。  
`pv_fault` 只读遗产。

详细对象、隔离规则、G10–G13 见 `fusion-design.md`。

## 阅读前字段速查

| 字段 | 通俗含义 |
|---|---|
| `slot` | 唯一路径槽位；决定本次使用哪套模板、配置、模型和运营数据 |
| `scenario_key` | 已废止的旧场景键；只在迁移说明中出现 |
| `slot_config_ref` / `effective_global_config` | 槽位配置版本 / 本次执行最终配置 |
| `workflow_id` / `workflow_version` / `execution_id` | 工作流 ID / 冻结版本 / 单次执行 ID |
| `source_workflow_id` / `source_workflow_version` / `source_execution_id` | 模型或指标来自哪条工作流、哪个版本、哪次成功执行 |
| `dataset_profile_ref` / `domain_profile_ref` | 数据长相合同 / 领域知识合同的版本引用 |
| `model_ref` / `model_candidate_id` | 模型工件引用 / 等待复验或晋升的模型候选 ID |
| `verification_id` / `registry_version` | 复验证据 ID / 生产模型登记版本 |
| `set_as_production` / `production_slot` | 是否真的切生产 / 要写入哪个槽位 |
| `slot_dataset_snapshot` | 某个产品槽位的不可变盘点版（id@version） |
| `label_proposal` | 机器打标提案，不能拿去训练 |
| `LabeledDatasetVersion` | 专家确认的一箱真值，必须写明天或点 |
| `replay_activity` | **回放循环 / 喂数调度器**：按真实点逐个推进；也是日内告警的时钟 |

---

## 先记住六条结论

1. **产品主线是 `pv_day` / `pv_point` 两条链。** 人机闭环接在这两条上，不再以 `pv_fault` 为新业务槽。NASA/Kaggle 仍只作 benchmark 验证。
2. **只用一个分区键 `slot`。** 确认箱、提案、快照、模型、告警都按天/点分仓。
3. **G0–G8 骨架已在；下一刀是 G10 接缝。** 不是重做 P0a。闭环真值走「确认箱 → 累计清单 → 快照版本」，不是可变累计 CSV。
4. **P0 仍纯手工编排。** 打标模板化在 G11；人工校验永不进画布。
5. **点路径只处理真实点。** 日内滚动告警复用 `replay_activity`，不用 TSC / 288 槽。
6. **工作流产物是部署和精度运营的真源。** 训练只读 curated + 同 slot 快照版本。

---

## P0a / P0b：到底要交付什么

### P0a（先验收，G0–G3）：两条生命周期链

目标：**能演示**，不是把标注闭环和 NASA 一起做完。

#### 天路径 `pv_day`

```text
Workflow Editor 组建/发布 pv_day.train_eval、pv_day.predict
→ 训练产生带 source execution 的 model_ref
→ 设备日预测
→ Deployment ?slot=pv_day 能看见本次产物
→ 日检/Orchestrator 触发已发布预测工作流（不再旁路评分）
→ Accuracy Operations ?slot=pv_day 能看见本次指标
```

P0a **不要求**完整 verification 公式，也不要求 Promote true。

#### 点路径 `pv_point`

```text
Workflow Editor 组建/发布 pv_point.train_eval、pv_point.predict_replay
→ 在真实点窗口合同上重训（旧 grid 权重不能当 Champion）
→ replay_activity 回放循环：逐点喂入，每点调用同一份冻结 graph
→ 一点一结果的 prediction / no-decision
→ Deployment / Accuracy Operations ?slot=pv_point 能看见本次产物
```

G3 必须有**最小 UI**：能选 slot、跑模板、看见产物。完整深链打磨属于 G7。

### P0b（P0a 通过后，G4–G5）：标注回流闭环

这是光伏比负荷预测**多出来的一环**，两个 slot **各自**完成一轮：

```text
预测 → annotation_candidate → 人工审核 → reviewed_annotation
→ slot_dataset_snapshot 版本 +1 → 固定版本重训 → 同 slot 复验
→ 人工 Promote（本轮显式 set_as_production=true）→ 再预测/回放
```

### P0b 之后：真值怎么进训练（融合）

预测或聚类经人工确认后：

```text
LabeledDatasetVersion（这批货，带 slot）
→ 显式纳入该 slot 累计清单
→ 显式 build slot_dataset_snapshot 版本 +1
→ 重训写死 snap-xxx@vN
→ 同 slot 复验 / Promote（仍四动作拆开）
```

**禁止**在现网 `pv_fault` 生产 Champion 上 Promote true。

### 公开数据集放在哪里

NASA、FHC、Kaggle、PVDAQ 在 **P0a 生命周期链打通之后** 才用来验证「同一组节点和连线，换 profile 也能跑」。它们走独立 `benchmark_*` slot，不写产品候选池、快照或 registry。

换数据集时：**尽量**只换 profile + 复制模板；确需改算子可以，但要记录例外，不因此判验收失败。

---

## 回放循环是什么（重点）

很多人会把「回放循环」理解成画布上的一个 for 循环节点，或者「把整天 CSV 循环读一遍」。**都不是。**

### 一句话

**回放循环 = 文件驱动的喂数调度器 `replay_activity`：模拟「点来一个、判一个」的在线语义，不是算子，也不进冻结 graph。**

### 和画布的关系

| 是什么 | 不是什么 |
|---|---|
| 按实体记住「处理到哪个真实点了」（`replay_cursor`） | 画布上的算子节点 |
| 每次只放出**下一个已发生的真实点** | 先把整日数据倒完再假装逐行 |
| 每放出一点，**调用同一份**冻结 `predict_replay` graph **一次** | 为每个点建一份不同的草稿 graph |
| admission、committed history、cursor、事务在 activity 里 | 画成隐藏的 `ts_point_*` 算子 |

### 一次循环里发生什么

以某个逆变器（实体）为例，源文件里已有按时间排序的真实测量点：

```text
1. replay_activity 读取该实体 committed history（已经判过的点）
2. 从文件/adaptor 取出下一个还没处理的 pending point
3. 调用冻结 graph 一次：
   load → profile-map → validate → impute → window → load_model → predict
4. graph 产出：prediction 或 no-decision（二选一）+ evidence
5. 同一事务提交：pending 点写入 history + outcome + cursor 前进
6. 失败则整点回滚；修正源数据后可幂等重试
7. 回到步骤 2，直到没有新点
```

### 和训练 graph 的区别

- **训练**（`pv_point.train_eval`）：一次性跑完整条 graph，在真实点序列上切窗、训练、评估。
- **回放**（`pv_point.predict_replay`）：graph 只管「给定当前 pending 点，怎么判」；**谁在什么时候把点送进来**，由 `replay_activity` 负责。

### P0 的产品形态

- 第一次喂数用**文件水位回放**，不上正式 5 分钟 cron，也不先建消息队列。
- 但训练和 replay 必须用同一套「真实点序列 + 当前点终止窗口」合同。
- 改当前 cursor **之后**的文件内容，不能改变当前点的窗口和预测（因果验收）。

### 易混概念对照

| 说法 | 含义 |
|---|---|
| 回放循环 | `replay_activity` 的逐点推进 |
| 冻结 graph | 画布上可见、可版本化的 `predict_replay` 算子链 |
| committed history | 该实体已经正式提交过的真实点 |
| pending point | 本次刚 admission、尚未提交的点 |
| replay_cursor | 每实体「处理到哪里了」的持久指针 |

---

## A0. 修订声明与架构结论

A0–A16 是当前方案。附录 H 只是旧专用点系统的历史摘要，**禁止按附录实施**。

明确废止的方向：

- 先造「通用时序平台」，再拿 NASA/FHC 当 P0 大门；
- `slot=pv_fault + scenario_key` 的双层分区（新合同只用 `slot`）；
- 子图、隐藏组合块、grid/resample、整日 288 槽；
- 部署页或精度运营页自训、自评、旁路 Orchestrator；
- 天模型与点模型互相 Promote；
- benchmark 数据直接写产品 registry；
- G0 把 `functions.json` 整表生成化。

当前只复用四类对象：普通单算子、完整工作流模板、dataset profile、domain profile。

---

## A1. 哪些基础能留，哪些断点要先修

### A1.1 可以保留

- 工作流 CRUD、画布和执行框架；
- `OperatorRouter` 动态发现算子 backend；
- 现有光伏天级 quickval 模板 → `pv_day` 迁移基线；
- 标注候选、区间审核、动态标签；
- 离线点 POC 的 Causal TCN trainer/artifact、因果思想（**不含** strict 5 分钟 grid 构建）；
- 部分 model candidate / verification / Promote 基础。

### A1.2 新模板进入前必须修（G0 范围）

1. `handleExecute()` 必须发送 `slot`、`slot_config_ref`、`live_nodes`、`global_config`（当前 mainly 只有 `live_nodes`）。
2. 后端合并同 slot 的 `effective_global_config`，缺 slot 的新请求失败。
3. **未注册算子不能伪成功**（当前：未注册仍标节点 success，整 pipeline 可 success）。
4. execution 绑定 workflow 版本、graph digest、配置 digest；预留 source execution 字段。
5. G0 **不改**现网 registry、标签表；**不**新增 `ts_point_*`；**不**下载 NASA。

**第一次编码：** 按 `tasks.md` 的 **G0-S0 → G0-S4** 五个 Composer 会话执行，不要一次做完整 G0。

---

## A2. 四层架构与完全展开画布

```text
Domain Profile     → 光伏标签、文案、阈值
Dataset Profile    → 列、实体、时间、标签、许可
Workflow Templates → pv_day / pv_point 四个角色，graph 完全展开
Visible Operators  → load_csv、ts_point_*、load_model_artifact 等
        ↓
Shared Execution / Activity / Artifact / Audit
```

**没有子图层。** `replay_activity` 在 Activity 层，可以多次调用同一份冻结 graph，但 itself 不是 graph 节点。

### A2.1 什么共享，什么隔离

| 能力 | 可以共享 | 必须按 slot 隔离 |
|---|---|---|
| 执行基础设施 | 画布、router、execution/activity | 模板、graph、配置、registry |
| 单算子代码 | `ts_point_*` 实现 | 各 slot 的模型指针、快照、候选池 |
| 页面壳 | Deployment、Accuracy Operations UI | URL `?slot=` 下的数据和操作 |

### A2.2 单 slot 列表

| `slot` | 用途 |
|---|---|
| `pv_day` | 设备日训练/预测/调度/运营 |
| `pv_point` | 真实点训练/回放/点级运营 |
| `load_forecast` | 负荷预测自有链，不读光伏数据 |
| `benchmark_*` | NASA/FHC/Kaggle 等验证，禁止产品治理写入 |

### A2.3 闭环属于 P0b，不属于 P0a

见上文「P0b」一节。快照构建、重训、复验、Promote 是四个**独立动作**，前一步成功不自动触发后一步。

---

## A3. 四个模板角色

| 模板 | slot | 干什么 |
|---|---|---|
| `train_eval` | `pv_day` | 设备日训练评估 |
| `predict` | `pv_day` | 消费明确 `model_ref` 做设备日预测 |
| `train_eval` | `pv_point` | 真实点因果窗口上训练 |
| `predict_replay` | `pv_point` | 冻结 graph：给定 pending 点做当前点预测 |

### `pv_point.predict_replay` 的两层结构

**层 1 — 冻结 graph（画布可见）：**

```text
load_csv / adapter source
→ ts_point_profile_map → validate → causal_impute → causal_window
→ load_model_artifact → ts_point_predict
→ 可选 metrics / candidate_intervals
```

**层 2 — replay_activity（回放循环，不在画布）：**

```text
对每个实体：
  取下一个 pending 真实点
  → 调用上面同一份冻结 graph 一次
  → 提交 history + outcome + cursor
  → 下一个点
```

---

## A4. 手工编排边界

- 每个节点用户逐个拖入；profile 不自动插节点；
- 跨数据集复用比较的是「相同 operator_id + 可见 edges」，不是隐藏内部图；
- P0 不做子图/recipe/组合块。

---

## A5. 点算子与换数据集

### A5.1 12 个 `ts_point_*` + 2 个通用 loader

P0 启用 10 个算子；`cross_validate`、`persistence_alarm` 为 P1（disabled）。

通用 loader（也必须在画布可见）：

- `load_csv` — 读表格，输出 `data`；
- `load_model_artifact` — 读明确 `model_ref`。

**明确删除：** `ts_point_align_grid` 及一切 grid/resample 等价物。

### A5.2 旧 POC 与新合同

- **可复用：** Causal TCN trainer/artifact 核、因果窗口思想、未来扰动审计；
- **不可直接复用：** strict 5 分钟 `_align_causal_grid()`、旧 `model.pt` 当 Champion；
- **G2 必须：** 按真实点窗口重训 +「一点一结果 / 改未来不影响当前预测」回归。

### A5.3 换数据集尽量低成本（优先目标，非硬门槛）

**优先路径：**

```text
新 dataset_profile + 必要时 domain_profile
+ 复制模板到 benchmark_<dataset_key>
+ 允许的超参数
→ 尽量复用同一组 ts_point_* / load_csv / load_model_artifact
```

**尽量不改：** 按数据集名写死的分支、为单个 Kaggle 集新增计算算子、grid/resample。

**确需改算子时：** 优先做成通用能力；做不到就记例外，不挡 P0a/G6。

G2 **建议**用一份非光伏形状的最小 CSV 早发现硬编码；跑不过只记差异，不是硬失败。

---

## A6–A7. Profile、配置、执行（摘要）

- **Dataset profile** 描述数据长相：列、实体、时钟、标签、许可；
- **Domain profile** 描述光伏知识：标签空间、文案、阈值；
- **Slot config** 每 slot 独立；合并优先级：平台默认 ← slot defaults ← 模板 ← 请求覆盖；
- **Preflight** 缺 backend、跨 slot、无 grid 因果错误 → 阻断，不能 skipped-success；
- **Execution** 只认 `status=succeeded` 且带来源 workflow/execution 的产物。

---

## A8. 数据喂入（摘要）

### 天路径

以**设备日**为单位；Orchestrator 触发已发布 `pv_day.predict`。

### 点路径

见上文 **「回放循环是什么」** 整节。A8.2 与之一致：P0 是文件 replay，G9 再接正式 connector/Shadow。

---

## A9–A10. 闭环与治理（P0b 才完整验收）

- 三类标注对象分开：`annotation_candidate` / `reviewed_annotation` / `benchmark_ground_truth`；
- `model_candidate` 是模型治理，不是标注候选；
- 每个 slot 一条 `slot_dataset_snapshot` 链（stable `snapshot_id`，版本单调 +1）；
- Verification 有训练 producer 和评测 producer 两套来源；
- Promote 默认 `set_as_production=false`；P0b 闭环验收才显式 true，且不能碰现网 `pv_fault` Champion。

---

## A11–A12. API 与前端（摘要）

- 执行 API 必须带 `slot`；旧双键仅 allowlist 映射；
- Deployment / Accuracy Operations 按 `?slot=` 隔离；
- G3 最小 UI：选 slot、执行、看见产物；G7 再打磨深链和全状态。

---

## A13–A14. 字段链与外部数据（摘要）

关键链：`slot` → 请求 → merge config → execution → artifact → 页面回显。

外部数据顺序：现有 PV 主链 → PV 等价回归 → NASA → FHC → PVDAQ；NAB/SKAB/Kaggle 等为补充。许可未清不得提交仓库。

---

## A15. 实施顺序

| 阶段 | 交付 | 备注 |
|---|---|---|
| **G0–G8** | 双链骨架、治理、benchmark | **已完成骨架**，不要重开 |
| **G9** | 正式点流、Shadow | 后置于告警演示；可与 G12 喂数源一并评估 |
| **G10** | 确认箱接缝 + slot 隔离 | **下一步**；见 `fusion-design.md` |
| **G11** | 打标模板 A + 诊断只吃确认数据 | |
| **G12** | `pv_point` 日内滚动告警 | 保留 replay，接状态机 |
| **G13** | 货架卫生、legacy 只读 | 不挡 G10 故事 |

**下一刀 = G10。** 细节退出门槛写在 `fusion-design.md` 第 7–8 节。

---

## A16. 验收与风险（摘要）

### P0a 必须能回答

- 未注册算子还会不会「节点 skipped 但整体 success」？
- `pv_day` / `pv_point` 能否从组建走到部署/精度页看见产物？
- 点链是否一点一结果、无虚拟时间戳、旧 grid 权重未当 Champion？
- 回放循环是否在 `replay_activity`，而不是画进 graph？

### P0b 额外必须能回答

- 天/点是否各完成一轮 snapshot +1 → 重训 → 复验 → Promote true？
- 现网 `pv_fault` Champion 是否未被误改？

### 主要风险

1. 把 P0a 和 P0b 绑死 → 很久不能演示；
2. 把回放循环画成算子 → graph 和 activity 职责混乱；
3. 旧 grid POC 直接当 Champion → 与新点合同不兼容；
4. G0 范围膨胀 → 一次改太多，Composer 容易跑偏；
5. 为每个 Kaggle 集新写算子 → 复用成本失控（优先 profile，例外要记录）。

---

## 附录 H 易读摘要

旧方案里的 K4 标注、TCN、告警状态机等可作算法参考，但 **5 分钟网格、288 槽、专用实时 API、先迁表再证明复用** 等合同已废止。

真正实施：已落地部分认 A0–A16 与 G0–G8 handoff；**新产品接缝认 `fusion-design.md` 与 G10–G13**。点产品链始终按**真实点 + 回放循环 + 冻结 graph** 推进，告警接在 outcome 之后。

<!-- @AI_GENERATED: end -->
