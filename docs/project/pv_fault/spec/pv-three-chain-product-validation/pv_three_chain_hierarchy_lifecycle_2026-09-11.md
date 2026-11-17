<!-- @AI_GENERATED -->
# 光伏三链项目工作台：层级、对应关系与端到端生命周期

> 落地基准：`.kiro/specs/pv-three-chain-product-validation/`（requirements / design / tasks）。
> 本文所有字段名、存储路径、拒绝码均来自**已落地实现**（`backend-service/services/pv_projects/`、
> `backend-service/api/pv_projects/`、`frontend-sevice/src/pv-fault/`），非设想。
> 编写日期：2026-09-11。

---

## 0. 一句话总纲

**数据是项目共用的；真值台账 / 尺子 / 在岗模型指针是路径唯一的；模型和它的分数是工作流各自的。**

再补两句关键区分：

- **模型「出生」绑工作流**（provenance：哪个训练工作流 + 哪个快照跑出来的）。
- **模型「上岗」绑路径**（appointment：这条路径下一轮检测用哪一个，必须唯一）。

---

## 1. 五层层级模型

```
① 项目 project              客户 / 交付隔离硬边界
   └── ② 诊断路径 slot       契约层：预测单元 + 真值粒度 + 评测尺子 + 生产消费语义
        └── ③ 工作流 workflow  实现层：三类（打标 / 训练 / 检测）
             └── ④ 执行 execution  一次运行，带 run_mode 与 run_domain
                  └── ⑤ 产物 / 证据  模型工件、标签提案、候选、快照、检测结果
```

- **最小硬隔离键**：`(project_id, slot)`。数据相关对象再细分到 `dataset_version_id`。
- **路径取值**：`pv_day` / `pv_point` / `pv_tsc`。历史 `pv_fault` 仅在 `project_id=legacy` 下只读兼容。
- **`legacy`** 是显式只读兼容项目，**绝不**作为新请求默认值。

### 为什么路径是契约层而不是标签

| 路径 | 预测单元 | 所需真值粒度 | 快照类型 |
|---|---|---|---|
| `pv_day` | 设备日（天级聚合特征） | 设备日标签 | `device_day_curve_set` |
| `pv_point` | 逐点 / 区间（事件时间） | **点级 / 区间级**标签 | `whole_day_point_box` |
| `pv_tsc` | 设备日（288×3 时钟网格） | 设备日标签（288×3 合格） | `tsc_288x3_grid` |

设备日标签可服务 `pv_day` / `pv_tsc`，但**绝不能**当 `pv_point` 的逐点真值 —— 这是冻结时过滤整日盒的红线依据。

---

## 2. 实体归属对照表（含真实存储）

存储根（相对 `backend-service/`）：

- `data/slot_governance` — 治理类（registry / 候选 / 复验 / Promote 审计）
- `data/slot_datasets` — 数据类（资产 / 画像 / 版本）
- `data/pv_projects` — 项目运行类（执行 / 审核 / 累计 / 快照 / 结果 / 游标 / 工作流 / Sandbox）

路径布局：

- 项目级：`<root>/projects/<project_id>/<filename>`
- 路径级：`<root>/projects/<project_id>/<slot>/<filename>`
- legacy 只读：`<root>/<slot>/<filename>`

### 2.1 项目级（三条路径共用）

| 实体 | 主键（英文 — 中文） | 存储文件 | 关键约束 |
|---|---|---|---|
| 项目 | `project_id` — 项目 ID | `data/pv_projects/projects_index.json` | 自带 `scenario_id` — 行业场景、`solution_id` — 算法方案 |
| 数据资产 | `dataset_id` — 数据资产 ID | `slot_datasets/projects/<pid>/dataset_assets.json` | 只存 `asset_id` / `connector_id` / 相对上传引用；**不存凭据、连接串、机器绝对路径** |
| 字段映射画像 | `dataset_profile_id` — 映射与画像版本 ID | 同目录 `dataset_profiles.json` | 映射变化 → 产**新画像**，不改旧的 |
| **不可变数据版本** | `dataset_version_id` — 不可变数据版本 ID | 同目录 `dataset_versions.json` | 带相对 `artifact_ref` + 稳定 `content_digest`；相同内容幂等命中 |
| 物化任务 | `task_id` — 长连接器物化任务 ID | `pv_projects/projects/<pid>/materialization_tasks.json` | 刷新后可按 ID 恢复进度 |
| 跨数据集复验批次 | `validation_id` — 产品复验批次 ID（`xdpv-` 前缀） | 同目录 `validation_batches.json` | `governance_effect="none"` — 无治理效力 |
| 离线基准证据 | `benchmark_evidence_version` — 离线基准证据版本 | 同目录 `benchmark_evidence.json` | 只读；`calibration_audit_id=null`（无注册表，如实置空） |

### 2.2 路径级（每条路径唯一，该路径下所有工作流共用）

| 实体 | 主键 | 存储文件 | 多重性 / 约束 |
|---|---|---|---|
| **模型指针登记** | —（单文档） | `slot_governance/projects/<pid>/<slot>/registry.json` | **唯一**：`champion` / `challenger` / `rolling_detect_model` / `registry_version` — 乐观锁版本 |
| 检测 / replay 游标 | —（单文档） | `pv_projects/projects/<pid>/<slot>/cursor.json` | 唯一 |
| 审核会话 | `review_id` — 审核会话 ID | 同目录 `reviews.json` | 队列唯一；会话 N 条；`review_version` CAS |
| **累计入账事件** | `event_id` — 准入事件 ID | 同目录 `cumulative_events.json` | **唯一累加池**（`kind="admission"`） |
| **冻结快照** | `snapshot_id` — 冻结快照 ID | 同目录 `snapshots.json` | **N 个**（不同 `reviewed_at_cutoff` / 子集）；`plan_fingerprint` 幂等 |
| 模型候选 | `model_candidate_id` — 模型候选 ID | `slot_governance/.../model_candidates.json` | N 条；各自带 `source_workflow_id` |
| 正式复验 | `verification_id` — 正式复验 ID | 同目录 `verifications.json` | N 条；`passed=true` 才有治理效力 |
| Promote 审计 | `promotion_id` — 晋升事件 ID | 同目录 `promotions_log.json` | **只追加，不改历史** |
| Sandbox 运行域 | `sandbox_id` — Sandbox 实例 ID | `pv_projects/.../sandbox_runs.json` | N 个，互相隔离；reset 只影响本实例 |

### 2.3 工作流级 / 执行级（各自一份）

| 实体 | 主键 | 存储文件 | 归属字段 |
|---|---|---|---|
| 项目工作流版本 | `project_workflow_id` — 项目工作流 ID | `pv_projects/.../project_workflows.json` | 按 slot 分区；`version` / `version_group_id` / `create_mode` / `bound_dataset_version_id` |
| 执行记录 | `execution_id` — 执行 ID | 同目录 `executions.json` | `project_workflow_id` / `run_mode` / `run_domain` / `governance_eligible` / `node_timeline` |
| 训练结果索引 | `result_id` — 训练结果 ID | 同目录 `results.json` | `source_snapshot_id` + `source_execution_id` + `model_artifact_ref` |

---

## 3. 三类工作流对照

| | 打标工作流 | 训练工作流 | 检测工作流 |
|---|---|---|---|
| **每路径数量** | 1（canonical） | **N** | 1（共用） |
| **输入** | 未标注数据版本 + 一个辅助模型 | **冻结快照** | **registry 指针模型** + 生产喂数 |
| **产物** | 标签提案 | **模型工件** | 检测结果批次 |
| **是否产模型** | 否 | **是** | 否 |
| `pv_day` | `workflow-pv-day-label-v1` | 项目自建 | `LegacyDayStrategy` → `workflow-pv-fault-diag-quickval-predict-v1`（**无专用日级生产图**） |
| `pv_point` | `workflow-pv-point-label-v1` | 项目自建 | `SeqDailyStrategy` 直连 predictor；因果内核 `services/timeseries_point/replay_activity.py::_process_one_point()` |
| `pv_tsc` | `workflow-pv-tsc-label-v1`（`tsc_predict → emit_tsc_label_proposal`） | 项目自建 | `TscDailyStrategy` → `tsc_predict`（cron 任务 `pv_tsc_predict`） |

> **诚实标注**：日路径生产检测复用 quickval 预测工作流，本工作台**不新建**日级生产图。
> 历史 KMeans REST 聚类是 `labeling_mode="shortcut"` — 快捷聚类模式，**不是** canonical 模型辅助打标；
> `preferred_labeling_workflow_id` 仅为指向 canonical 的元数据。

---

## 4. 多重性总表

| 关系 | 基数 | 关键约束 |
|---|---|---|
| 项目 : 路径 | 1 : 1~3 | 由**启用意图** × **readiness 可行性**共同决定 |
| 项目 : 数据版本 | 1 : N | 项目级共享 |
| 数据版本 : 路径 | **N : M** | 一份数据可满足多条路径，由 readiness 逐路径判定 |
| 路径 : 打标工作流 | 1 : 1 | canonical 固定 |
| 路径 : 检测工作流 | 1 : 1 | 共用；只消费指针模型 |
| **路径 : 训练工作流** | **1 : N** | 竞争同一个上岗名额 |
| **路径 : 累计台账** | **1 : 1** | 唯一累加池 |
| 路径 : 快照 | 1 : N | 不同 cutoff / 子集 |
| **快照 : 训练工作流** | **1 : N** | **公平擂台**：同输入才可比 |
| 工作流 + 快照 : 执行 | 1 : N | 重试 / 改后重跑都产**新执行**，不覆盖失败证据 |
| 执行 : 候选 | 1 : 0~1 | 仅可治理执行可登记为可治理候选 |
| 候选 : 复验 | 1 : N | 需 `passed=true` |
| **路径 : 在岗模型** | **1 : 1** | 指针唯一，共用检测器才能解析 |

---

## 5. 端到端生命周期

| # | 阶段 | 层级 | 用户动作 | 产物 | 门禁 / 红线 |
|---|---|---|---|---|---|
| 1 | 创建项目 | 项目 | 选场景 + 方案 | `project_id`，空生命周期 | 不继承任何 legacy 审核 / 累计 / 候选 / registry / 游标状态；「从现有项目复制」只复制结构 |
| 2 | 数据接入 | 项目 | 上传 / 平台资产 / 授权连接器 | `dataset_id` | 拒绝服务器绝对路径与凭据；浏览器不得传文件系统路径 |
| 3 | 映射画像 | 项目 | 配时间 / 时区 / 设备 / 值 / `i_cal` / 标签字典与粒度 | `dataset_profile_id` | `i_cal` — 期望电流参照，**不是** ground truth；`rated_power_kw` 仅辅助元数据 |
| 4 | 发布版本 | 项目 | 确认发布 | `dataset_version_id` + `content_digest` | 不可变；改映射 → 新版本，不改原版本 |
| 5 | **路径就绪评估** | 路径 | 查看 readiness | 6 态之一 + `facts` + `blockers` + `primary_blocker` + `allowed_run_modes` | **ready ≠ 生产 / 候选 / Promote 资格**；画像或路径合同变化 → readiness 标记过期 |
| 6 | 确认启用路径 | 路径 | 选 1~3 条 | 启用意图 | 受 readiness 约束，不允许盲选 |
| 7 | 打标（缺标签时） | 路径 | 启动 canonical 打标工作流 | 标签提案 | 失败**不产出任何提案**（fail-closed） |
| 8 | 审核 | 路径 | **裁定 → 完成审核 → 完成并准入**（三个独立动作） | `review_id` → `event_id` | CAS `expected_review_version`；**完成审核不写台账**；准入按 `idempotency_key` 幂等；只有 `accept` 进台账 |
| 9 | 冻结 | 路径 | 选 `reviewed_at_cutoff` 冻结 | `snapshot_id` + `plan_fingerprint` + `content_digest` | 同一批事件幂等命中；`pv_point` 过滤整日盒（`whole_day_box_not_point_truth`） |
| 10 | 建训练工作流 | **工作流** | 模板 / 复制 / 空白，绑定**快照** | `project_workflow_id` | **绝不覆盖共享模板**；blank 也必须带归属 |
| 11 | 预检 | 工作流 | 执行前检查 | `blocked` / `warning` / `passed` + `experiment_only` | 路径契约不匹配应阻断 |
| 12 | 训练执行 | 执行 | 运行 | `execution_id` + 模型工件 + `node_timeline` | `governance_eligible = (run_mode=training ∧ run_domain≠sandbox)`；validation / experiment / sandbox **恒非可治理** |
| 13 | 登记候选 | 工作流 | 登记 | `model_candidate_id` | provenance 8 字段齐全（见 §7） |
| 14 | 正式复验 | 路径 | 发起多窗复验 | `verification_id`（`pending` / `passed=None`） | **不臆造通过**；`xdpv-` / `cdpv-` 前缀 ID 无治理效力 |
| 15 | **上岗** | **路径** | 设下一轮检测模型 / Promote Champion | `registry_version+1` + `promotion_id` | 需同 scope 同候选 `passed=true` 复验 + registry 版本 CAS + **生产写入授权**；写入候选**自身** `source_workflow_id` 与 `model_artifact_ref`，绝不写 baseline 或跨 scope 工件 |
| 16 | 生产检测 | 路径 | （调度自动） | 检测批次 + 调度回执 | **只读观测**；缺当前回执即「未产出」；失败日**不推进游标**；手工推进 / 补检 / 水位 / 游标 / 审核 / 精度写入一律拒绝 |
| 17 | 回流 | 路径 | 检测结果进审核 | 回到 #8 | 闭环 |
| 旁 | 跨数据集复验 | 项目 | 建批次 + 记录逐数据集结果 | `xdpv-` 证据束 | `governance_effect="none"`；`can_be_verification_evidence=false`；SHA256 零污染（输入源哈希跑前 / 跑后一致） |

### 5.1 首轮鸡生蛋（诚实说明）

`#7` 打标工作流需要一个辅助模型。**第一轮没有模型时**，只能：

1. 走 shortcut 聚类（KMeans REST，`labeling_mode="shortcut"`，明确非 canonical），或
2. 人工标注，或
3. 引入外部 bootstrap 模型。

拿到第一个快照并训出首个模型后，才进入 `#7 → #17` 的正常闭环。

### 5.2 运行模式与结果去向

| `run_mode` — 运行目的 | `run_domain` — 运行域 | 可治理 | `result_destination` — 结果去向 |
|---|---|---|---|
| `experiment` | `project` | 否 | `experiment_artifact_only` |
| `validation` | `project` | 否 | `validation_execution` |
| **`training`** | **`project`** | **是** | `governable_candidate` |
| `prediction` | `project` | 否 | `prediction_batch_and_pending_review` |
| `replay` | `sandbox` | 否 | 隔离 Sandbox 结果 |
| 任意 | `sandbox` | 否 | 隔离结果，`production_unaffected=true` |

---

## 6. 血缘链（完整可追溯）

```
dataset_id
  └─> dataset_profile_id
       └─> dataset_version_id ───────────────────────────┐
             └─> (打标 execution_id)                      │
                  └─> review_id                           │  每条准入事件都回指
                       └─> cumulative event_id ───────────┘
                            └─> snapshot_id
                                 │   （含 included_events / reviewed_at_cutoff / content_digest）
                                 └─> (训练 execution_id ← project_workflow_id)
                                      └─> model_candidate_id
                                           │   （含 source_snapshot_id / source_workflow_id
                                           │     / source_execution_id / model_artifact_ref）
                                           └─> verification_id (passed=true)
                                                └─> registry.rolling_detect_model / champion
                                                     └─> promotion_id (append-only)
                                                          └─> 共用检测工作流消费在岗模型
                                                               └─> 检测批次 ─┐
                                                                             │
                            ┌────────────────────────────────────────────────┘
                            └─> 回到 review_id（闭环）
```

**要点**：「累计训练数据与训练强绑定」是通过 `source_snapshot_id` 实现的**可追溯（lineage）**，
而**不是**各工作流独占数据。数据仍是路径级共享池。

---

## 7. 累计台账为什么绑路径（不绑工作流）

| 理由 | 说明 |
|---|---|
| **真值粒度是路径属性** | 设备日标签不能当逐点真值；按路径分区让该约束成为**结构性**保证，而非运行时过滤 |
| **真值必须比实现活得久** | 工作流会被换掉（v2 / v3 / 换算法）；人工审核真值是最贵资产，绑工作流会导致每建新工作流真值归零、同一设备日被审多遍 |
| **可比性要求训练输入共享且冻结** | N 个工作流吃**同一个快照**，分数差异才能归因到实现本身 —— 这就是「公平擂台」 |

**差异化需求怎么满足**：冻结**多个快照**（不同 `reviewed_at_cutoff` / 不同子集）。
台账是唯一累加池，快照是从池里「取一瓢」。同快照的可比；不同快照的必须显式标注不可比原因。

### 精度也分两种

| 精度类型 | 绑定 | 用途 |
|---|---|---|
| **候选评估精度** | 工作流 / 候选（在固定 `evaluation_contract` 上的离线得分） | 横向比较、挑选上岗者 |
| **生产运行精度** | 路径（当前在岗模型 + 真实检测 + 人工真值 + 时间窗） | 运营监控 |

两者都必须声明统计范围、人工真值数、类别支持度、指标定义、数据与模型版本、不可比原因。
**无有效人工真值时渲染「未产出」而非 0%**；低分**不联动**调参 / Promote。

---

## 8. 共用 vs 唯一 速记表

| 层 | 内容 | 性质 |
|---|---|---|
| 项目级 | 数据资产、字段映射画像、**不可变数据版本**、物化任务、跨数据集证据、离线基准证据 | **共用** |
| 路径级 | **真值台账、冻结快照、评测尺子、审核队列、检测游标、在岗模型指针（registry）**、canonical 打标工作流、共用检测工作流 | **唯一** |
| 工作流级 | **模型工件、模型候选、该候选的评估精度**、执行记录、训练结果索引 | **各自** |

---

## 9. 门禁 / 拒绝码对照

| 门禁 | 触发点 | `reason_code` | HTTP |
|---|---|---|---|
| legacy 只读 | 任何新产品写入 | `legacy_read_only` | 403 |
| legacy 不可承接 | 写入路径 `allow_legacy=False` | `legacy_project_not_allowed` | 403 |
| 跨项目 / 跨槽 | 读写他 scope 对象 | `scope_mismatch` | 409 |
| 跨槽写入 | `production_slot` ≠ 当前槽 | `cross_slot_write_forbidden` | 409 |
| 候选非可治理 | validation / experiment / sandbox 来源 | `candidate_not_governable` | 409 |
| provenance 不全 | 缺 8 字段任一 | `candidate_provenance_incomplete` | 409 |
| 复验未通过 | `passed != true` | `verification_not_passed` | 409 |
| 复验绑定不符 | verification 绑的候选 ≠ 目标候选 | `verification_candidate_mismatch` | 409 |
| 产品复验冒充 | `xdpv-` / `cdpv-` 当 `verification_id` | `product_validation_no_governance_effect` | 409 |
| registry 并发 | `expected_registry_version` 不匹配 | `registry_version_conflict` | 409（可重试） |
| 审核并发重判 | `expected_review_version` 不匹配 | `review_version_conflict` | 409（可重试） |
| 审核未完成 | 仍有未裁定条目 | `review_incomplete` | 409 |
| 无可冻结事件 | 该 cutoff 下无准入事件 | `no_admitted_events` | 409 |
| TSC 生产观测只读 | 手工推进 / 补检 / 写水位游标 | `tsc_production_observability_read_only` | 403 |
| **生产写入未授权** | 滚动指针 / Promote | `production_writes_not_authorized` | 403 |

统一错误响应形状：`reason_code` / `message` / `next_action` / `scope` / `retryable` / `correlation_id`
（涉及门槛补 `current_value` / `required_value`；门控附 `category`）。

**必需的候选 provenance 8 字段**：`project_id`、`slot`、`source_dataset_version_id`、
`source_workflow_id`、`source_execution_id`、`source_snapshot_id`、`model_artifact_ref`、`evaluation_contract`。

---

## 10. 生命周期阶段枚举（总览矩阵用）

由 `compute_slot_lifecycle()` 按**真实对象**计算，不额外保存易漂移的「当前步骤」；
每个阶段附 `stage_reason` — 判定依据（证据化状态）。

| `stage` | 判定依据 | 主动作 |
|---|---|---|
| `UNCONFIGURED` | 无已发布数据版本 | 接入数据 |
| `DATA_READY` | 有数据版本、无 execution | 创建工作流并运行 |
| `EXPERIMENT_RESULT` | 有 execution、无可治理候选 / 复验 / 指针 | 登记为可治理候选 |
| `REVIEW_PENDING` | 有未完成审核会话 | 完成审核 |
| `SNAPSHOT_READY` | 已冻结快照 | 基于快照创建训练工作流 |
| `GOVERNANCE_CANDIDATE` | 有**可治理**候选、无 passed 复验 | 发起正式复验 |
| `VERIFIED` | 有 `passed=true` 复验 | 设为下一轮检测模型 |
| `ROLLING_MODEL_SELECTED` | `registry.rolling_detect_model` 已设置 | 查看检测与回放 |

readiness 六态（逐路径，独立于 stage）：
`ready` / `experiment_only` / `needs_mapping` / `needs_labels` / `insufficient_data` / `unsupported`。

---

## 11. 当前实现与本模型的差异（待改清单）

| # | 差异 | 影响 | 优先级 |
|---|---|---|---|
| 1 | **总览 stage 未消费 readiness** | 只要项目有数据版本，三条路径都判「数据就绪」；TSC 口径数据也会让 `pv_day` / `pv_point` 显示可运行 | 高（真 bug） |
| 2 | `project_workflows` **缺 `workflow_kind`** | 打标 / 训练 / 检测混在一个列表，看不出只有训练是 1:N | 高 |
| 3 | **缺「项目启用路径」意图** | 只做 TSC 的项目仍展示三条路径 | 中 |
| 4 | 训练工作流**只绑 `dataset_version_id`，未绑 `source_snapshot_id`** | 训练输入应为冻结快照，血缘链在此断一节 | 高 |
| 5 | 候选**未按 `source_workflow_id` 分组展示** | 「工作流 → 模型 → 精度」对应关系不直观 | 中 |
| 6 | preflight **未硬校验路径契约** | 「属于哪条路径」仍是创建时声明，而非可校验事实 | 中 |

### 待决策项（影响 1 / 3 / 检测工作流设计）

1. **启用路径意图**在项目创建时选，还是在 readiness 出来后确认？（建议后者，避免盲选）
2. **未启用 / 不可用路径**在总览中隐藏，还是标注原因保留？（建议保留 + 标注 + 可选「仅显示可用」开关）
3. **检测工作流**是否允许项目自定义？若允许，需引入「检测工作流也须复验才能上岗」规则。

---

## 12. 关键文件索引

| 文件 | 职责 |
|---|---|
| `backend-service/services/pv_projects/scope.py` | `ScopeContext`：已校验的 `(project_id, slot, dataset_version_id)`，fail-closed |
| `backend-service/services/pv_projects/paths.py` | scoped 相对路径解析，拒绝机器绝对路径 |
| `backend-service/services/pv_projects/repositories.py` | scoped 存储核心：单文档 / 集合 / append-only、原子写、按 scope 写锁、legacy 只读映射 |
| `backend-service/services/pv_projects/stores.py` | 各对象类型的存储配置（分区键、文件名、id 字段） |
| `backend-service/services/pv_projects/projects.py` | 项目 CRUD + `compute_slot_lifecycle()`（阶段 + `stage_reason`） |
| `backend-service/services/pv_projects/workflows.py` | 项目工作流创建（模板 / 复制 / 空白）+ `run_preflight()` |
| `backend-service/services/pv_projects/runner.py` | `ScopedWorkflowRunner`：执行持久化、`governance_eligible`、retry / modify-rerun |
| `backend-service/services/pv_projects/review_service.py` | 审核三动作（裁定 / 完成 / 完成并准入）+ CAS + 精度表面 |
| `backend-service/services/pv_projects/cumulative.py` | 累计三层 + freeze plan / execute（幂等）+ 训练结果登记 |
| `backend-service/services/pv_projects/governance.py` | 四层治理、候选登记、正式复验、滚动指针、Promote 门禁 |
| `backend-service/services/pv_projects/day_adapter.py` | 日路径生产事实（quickval）+ Sandbox 全设备日回放 |
| `backend-service/services/pv_projects/sandbox_runtime.py` | 点路径事件时间因果回放（`SandboxRuntime`） |
| `backend-service/services/pv_projects/tsc_adapter.py` | TSC canonical 打标入口、strict-10 证据、只读生产观测、候选门禁 |
| `backend-service/services/pv_projects/cross_dataset.py` | 跨数据集验证批次 + 零污染 + 离线基准证据 |
| `frontend-sevice/src/pv-fault/pages/ProjectWorkbenchLayout.tsx` | 领域无关工作台壳（上下文栏 + 阶段带 + 内容区） |
| `frontend-sevice/src/pv-fault/adapters/pvFaultAdapter.ts` | 光伏适配器：三路径 + 六阶段生命周期 |
| `frontend-sevice/src/pv-fault/copy/stateVocabulary.ts` | 集中状态文案（十动作态 / 三横切 / 五禁用 / 六 readiness） |
| `frontend-sevice/src/utils/journeyParams.ts` | 四层主干 query 参数契约（规范名 + 别名兼容） |

<!-- @AI_GENERATED: end -->
