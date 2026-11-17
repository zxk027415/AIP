<!-- @AI_GENERATED -->
# AGENTS.md — 光伏故障诊断（pv_fault）产品现状

> 撰写 / 更新日期：2026-09-07  
> 适用范围：`pv_day`（天路径 / RF）、`pv_point`（点路径 / TCN）、`pv_tsc`（时序分类 / MultiRocket）三条并列检测路径，以及历史只读槽 `pv_fault`。  
> 本文只记录**实际代码、实际持久化数据和已执行验证**。代码能力、历史运行数据和待做治理动作分开描述；凡未验证项均显式标注。

---

## 0. 一句话定位

这是一个“人机协同的光伏故障诊断闭环”产品：**无标签数据 → 提案打标 → 累计训练集 → 冻结快照 → 训练模型 → 候选登记 → 复验 → 指定滚动检测模型 → 按日检测 → 人工审核算精度 → 回流累计训练集**。

三条路径通过 `slot` — 产品槽位/数据与治理分区键隔离：

- `pv_day`：一天时序聚合成统计特征，使用 RF 做设备日分类。
- `pv_point`：一天 288 点逐点建模，使用 TCN/BiLSTM 路径。
- `pv_tsc`：一天 288 点钟表网格 × 3 通道，使用 MultiRocket 做设备日分类。

---

## 1. 三条路径速查

| 维度 | `pv_day`（天/RF） | `pv_point`（点/TCN） | `pv_tsc`（时序分类） |
|---|---|---|---|
| `modeling_path` — 建模路径标识 | `legacy_day` | `seq_annotation` | `tsc` |
| 模型 | RandomForest | BiLSTM+Attention / CausalTCN | MultiRocket |
| 输入表示 | 一天时序 → 50 维统计特征 | 一天 288 点网格 → 逐点 | 一天 288 点钟表网格 × 3 通道 |
| 通道 | `value_*` 25 维 + `i_cal_*` 25 维 | `value` / `i_cal` | `value` / `i_cal` / `is_measured` |
| 产出粒度 | 设备日 1 标签 | 逐点 288 标签 | 设备日 1 标签（多窗口投票） |
| 检测策略 | `LegacyDayStrategy` | `SeqDailyStrategy` | `TscDailyStrategy` |
| 调度 cron | `0 3 * * *` | `*/5 * * * *`（replay） | `0 4 * * *` |
| 当前成熟度 | 🟢 已有存量治理闭环 | 🟢 已有存量治理闭环 | 🟡 代码主链已对齐，运行治理待迁移 |

**结论先行：** `pv_tsc` 的累计重训和按日滚动检测现在都已接到真实冻结画布；新代码要求 execution 证据持久化成功后才能登记候选或推进检测游标。它与另外两条路径的差距已从“缺训练/检测接线”收敛为“还没有跑出新的 strict-10 合格候选，也没有完成复验和滚动指针迁移”。当前磁盘中的 TSC Challenger 仍是历史记录，workflow provenance 为空，不能把新代码能力误写成旧数据已经自动补齐。

---

## 2. 产品故事线 · 阶段 0：数据入库与喂数据

### 2.1 三种喂数据机制

| 机制 | 适用 slot | 入口 | 是否写累计账本 |
|---|---|---|---|
| loop_demo 演示喂数 | `pv_day` / `pv_point` | `POST /api/slot-datasets/observability/advance-day` | ❌ `loop_demo_no_admit` |
| point replay 回放 | `pv_point` | `POST /api/slot-datasets/observability/replay-step` | ❌ |
| 真实数据到达 + 水位推进 | 三槽通用 | 外部数据管线 / `sched_pv_mock_feed_cron` | —（数据入 DB，不经累计账本） |

关键实现：`backend-service/services/slot_datasets/observability_ledger.py` — 管理三槽的观测状态、水位、日历格和演示写入权限。

- `_ALLOWED_SLOTS` — 可读取观测数据的槽位集合，包含 `pv_day`、`pv_point`、`pv_tsc`。
- `_DEMO_WRITE_SLOTS` — 可由观测页写演示水位的槽位集合，只包含 `pv_day`、`pv_point`。
- `advance_watermark_day()` — 演示水位推进函数；对 `pv_tsc` 返回 `read_only_slot`。
- `record_manual_detect()` — 手工补检记录函数；同样拒绝对 TSC 演示写入。

`pv_tsc` 的观测只读是有意设计：检测结果必须来自真实调度，不允许观测页伪造结果污染精度证据。代价是浏览器上不能用“推进一天”按钮演示 TSC。

### 2.2 完整性闸门

| 路径 | 门所在层 | 当前准入条件 |
|---|---|---|
| `pv_day` | 观测账本 `prepare_day_detect_batch()` | `arrived >= 173` |
| `pv_point` | 无同类观测层门 | 日历格直接进入 replay 语义 |
| `pv_tsc` | `grid_day_builder` / `grid_align` | `min_occupied_slots=173`、`min_daytime_occupancy=0.8`、`max_daytime_gap_slots=6` |

公共常量：`EXPECTED_POINTS=288` — 每日理论采样点数；`OCCUPANCY_READY=173` — 可检测最低占用点数；`HOLD_DAYS=3` — 不完整日等待宽限。

### 2.3 调度任务

配置文件 `backend-service/configs/db.yaml` — 保存调度 cron 与后端运行配置。

| 配置键 | cron | 用途 |
|---|---|---|
| `sched_pv_pull_cron` | `0 2 * * *` | PV 数据拉取 |
| `sched_pv_predict_cron` | `30 2 * * *` | 历史 `pv_fault` 预测 |
| `sched_pv_day_predict_cron` | `0 3 * * *` | 天路径检测 |
| `sched_pv_point_replay_cron` | `*/5 * * * *` | 点路径 replay |
| `sched_pv_tsc_predict_cron` | `0 4 * * *` | TSC 日检测 |
| `sched_pv_mock_feed_cron` | `*/12 * * * *` | mock 数据释放 tick |

---

## 3. 阶段 1：无标签数据与提案打标

### 3.1 canonical 画布与 REST 快捷入口

三槽都有冻结画布模板：

| 模板文件 | DAG / 作用 |
|---|---|
| `backend-service/data/workflows_enhanced/workflow-pv-day-label-v1.json` | `load_csv → z_score_scale → kmeans → cluster_profile → emit_label_proposal` |
| `backend-service/data/workflows_enhanced/workflow-pv-point-label-v1.json` | 天/点聚类提案链，使用 `pl-*` 节点前缀 |
| `backend-service/data/workflows_enhanced/workflow-pv-tsc-label-v1.json` | `load_csv → tsc_predict → emit_tsc_label_proposal`，属于模型辅助设备日提案 |

TSC 与天/点路径语义不同：天/点是无监督聚类提案；TSC 先用现有模型预测，再把设备日预测和窗口证据交给人工审核。

当前实际 REST 快捷入口仍是：

```text
POST /api/iterative-labeling/clustering/runs
  → PvTrainingWorkspace.create_clustering_run()
  → 进程内直接执行 KMeans
  → 写 labeling_mode=shortcut 和 preferred_labeling_workflow_id
```

`preferred_labeling_workflow_id` — 推荐的 canonical 打标工作流 ID，目前只是记录性元数据；该 REST 入口不会据此执行画布。`PvTrainingWorkspace.create_clustering_run()` — 接收数据和槽位，按设备/支路/自然日聚合统计特征并返回聚类 run；它仍是天级统计口径，不等于 TSC 的 288×3 模型辅助画布。

### 3.2 本轮已修与仍存缺口

已修：

1. `backend-service/api/iterative_labeling.py` — 创建 clustering run 后按三槽映射 `preferred_labeling_workflow_id`，`pv_tsc` 现在正确指向 `workflow-pv-tsc-label-v1`。
2. `backend-service/services/slot_datasets/label_proposals.py` — `_read_reference_labeled_frame()` 读取标签目录时增加 Parquet/CSV glob。TSC 金标使用内容寻址文件名，重新导出 hash 文件后仍能被发现，不再依赖写死文件名。
3. `frontend-sevice/src/components/slot/SlotDeployedModelPanel.tsx` — TSC 的“去审核”入口改为 `/iterative-labeling?tab=review&review_slot=pv_tsc`，不再误跳天/点打标 tab。

仍未补齐：

- REST clustering shortcut 仍直接执行 KMeans，不会执行 `workflow-pv-tsc-label-v1`。
- shortcut 的默认槽位和聚合表示仍偏向天/点路径，不是 TSC 设备日 288×3 表示。
- 前端已有 TSC 人工审核队列和提案审核组件，但没有一条与天/点同样清晰的“选择无标签数据 → 执行 TSC 模型辅助画布 → 进入提案审核”的 canonical 操作入口。

### 3.3 提案存储、确认与回流

`backend-service/services/slot_datasets/label_proposals.py` — 三槽统一的提案存储与确认服务。

相对路径介质：

- `backend-service/data/slot_datasets/{slot}/label_proposals.json` — 提案索引。
- `backend-service/data/slot_datasets/{slot}/proposal_rows/members-{proposal_id}.csv` — 提案成员明细。
- `backend-service/data/slot_datasets/{slot}/proposals/{proposal_id}.json` — 单提案工件。

确认链路：

```text
提案 + label_id_map
  → 按勾选 member_key 写标签
  → publish_labeled_version(status=curated)
  → register_trainable_dataset(kind=labeled_version)
  → include_path_a_labeled_version(source=path_a)
  → 累计训练账本
```

`pv_point` 的 freeze 额外排除聚类形成的“整日盒子”，避免设备日标签污染逐点真值；`pv_day` 和 `pv_tsc` 本身是设备日粒度，不应用这条过滤。

### 3.4 三路径打标结论

| 路径 | 当前状态 |
|---|---|
| `pv_day` | 🟢 REST 快捷、提案审核、确认入账均存在；canonical 画布资产存在 |
| `pv_point` | 🟢 同上，并有 freeze 层逐点真值保护 |
| `pv_tsc` | 🟡 存储、算子、画布模板、参考金标发现、审核 UI 均存在；preferred 映射已修，但 REST shortcut 尚未真正执行 TSC 画布 |

---

## 4. 阶段 2：累计训练集（入账 + 冻结）

### 4.1 来源优先级与唯一入账点

`backend-service/services/slot_datasets/snapshots.py` — 管理累计 inclusion events、来源优先级、去重与 freeze 物化。

```python
_CUMULATIVE_SOURCE_PRIORITY = {
    "gold_bootstrap": 0,
    "path_a": 10,
    "daily_review": 100,
}
```

高优先级来源覆盖低优先级重复实体时间点。TSC 要求 `site_id`、`device_id`、`branch_id`、`time` 四列完整，否则报 `missing_tsc_dedup_keys`。

单条 verdict 不直接入账。唯一入账入口：

```text
POST /api/iterative-labeling/review-sessions/{review_id}/complete-and-admit
  → complete_review_session_and_admit()
  → 检查全部 unit 已完成
  → learning / holdout 分离
  → admit_labeled_file_to_cumulative(freeze=False)
```

`freeze` — 是否立即冻结累计数据；这里固定为 `false`，所以完成审核只会入账，不会自动产出训练快照。

### 4.2 freeze 语义

`freeze_cumulative_at(slot, reviewed_at_cutoff)` — 以审核时间截断累计账本并物化不可变训练快照。

- `reviewed_at_cutoff` — 审核时间上界，不是原始数据时间上界。
- 幂等键同时包含 slot、cutoff 和输入 digest。
- 产物写到相对目录 `backend-service/data/slot_datasets/{slot}/snapshots/`。
- 大数据或已有 Parquet 源优先输出 Parquet，并附 `dataset_observation` — 行数、设备数、设备日数、标签/来源分布。

### 4.3 当前累计数据实测

| slot | inclusion events | freeze versions |
|---|---:|---:|
| `pv_day` | 3 | 2 |
| `pv_point` | 5 | 5 |
| `pv_tsc` | 2 | 2 |

当前实测 TSC 最新 freeze：1,056,806 行、1,642 台设备、35 个唯一日历日；网格化后 4,429 个设备日样本、13 类。日期跨 2020-05 至 2022-03，但只覆盖离散 35 天。“全量”是已标注样本全量，不是连续历史全量；这种稀疏日期覆盖会直接影响 strict 日期 × 设备双隔离。

---

## 5. 阶段 3：训练、execution 证据与候选登记

### 5.1 候选登记的两种能力

`backend-service/services/slot_governance/model_candidates.py` — 按 `slot` 保存模型候选，并在治理候选入口校验来源 execution。

- `register_model_candidate()` — 输入 slot、来源工作流、来源 execution 和模型工件；先调用 `validate_execution_provenance()`，成功后写入受治理候选。
- `register_retrain_model_candidate()` — 历史兼容入口；只有累计 request/snapshot lineage，没有真实 workflow execution provenance。旧候选继续可读，新 TSC 主链不再调用它。

新候选关键字段：

- `source_workflow_id` — 产出模型的冻结工作流 ID。
- `source_execution_id` — 已持久化且成功的工作流 execution ID。
- `source_workflow_version` — 执行时工作流版本。
- `model_artifact_ref` — 相对于后端目录的模型工件引用。
- `source_kind` — 来源类型；累计重训写 `cumulative_retrain`。
- `source_retrain_request_id` — 发起此次累计重训的 request lineage。
- `source_snapshot_id` — 此次训练消费的冻结快照 lineage。
- `evaluation_contract` — 训练/评估使用的固定量尺，例如 representation、strict split 和重复次数。

request/snapshot lineage 是对 workflow provenance 的补充，不能替代后者。

### 5.2 两种画布执行封装

`_execute_pipeline_sync()` — `backend-service/api/workflows_enhanced.py` 内的纯图执行器：输入内存 workflow，返回节点结果；它自身不持久化 execution。

持久化有两条包装路径：

1. HTTP async wrapper：执行后写 execution history，并按门禁自动登记训练候选。
2. `run_slot_workflow_sync()` — `backend-service/services/scheduler/slot_workflow_runner.py` 中的同步产品画布封装。它接收 `slot`、`workflow_id`、按 `functionId` 的算子参数覆盖和 execution metadata，运行冻结图、计算 graph digest、持久化 execution，并返回完整执行结果。

`require_persisted_execution` — 是否要求 execution 证据必须落盘；为 `true` 时，即使算子执行成功，只要持久化失败也会 fail-closed，不允许调用方推进游标或登记候选。`trigger_source` — 触发来源；实际使用 `scheduler`、`cumulative_retrain`、`validation`，分别生成 `exec-sched-*`、`exec-retrain-*`、`exec-validation-*` 前缀。`governance_eligible` — execution 是否可用于产品治理；validation 默认是 `false`，训练/产品执行默认可治理。

### 5.3 TSC 累计重训现在走真实画布

实际链路位于 `backend-service/api/iterative_labeling.py`：

```text
累计重训 request
  → attach_snapshot
  → 从 NPZ 快照 manifest 回溯内容寻址冻结 CSV/Parquet
  → resolve_train_workflow_id("pv_tsc")
  → workflow-pv-tsc-train-eval-v1
  → load_csv → tsc_sliding_window → tsc_train_eval
  → run_slot_workflow_sync(trigger_source=cumulative_retrain,
                           require_persisted_execution=True)
  → 校验成功 execution 与模型结果
  → register_model_candidate(...真实 provenance + request/snapshot lineage)
```

训练门禁：

- representation 固定为 `clock_grid_288_mask`。
- 输入形状必须是 `[N, 288, 3]`。
- channels 必须是 `value / i_cal / is_measured`。
- evaluation 和 split 均为 strict。
- `n_repeats` 不得低于 10。
- execution 必须持久化成功后才可登记候选。

这里选择 manifest 中的行级冻结 CSV/Parquet，而不是让 `load_csv` 读取 NPZ，因为冻结训练图的首节点就是 `load_csv`；所有传入和持久化路径均保持相对路径。

**当前边界：** 代码和隔离 smoke 已验证，但尚未用当前真实累计数据完整跑完一次新的 strict-10 TSC 训练。因此磁盘 registry 与候选文件不会被追溯改写。

### 5.4 画布资产与 replay 兼容约定

| slot | train_eval | predict | labeling |
|---|---|---|---|
| `pv_day` | `workflow-pv-day-train-eval-v1` | `workflow-pv-day-predict-v1` | `workflow-pv-day-label-v1` |
| `pv_point` | `workflow-pv-point-train-eval-v1` | `workflow-pv-point-predict-replay-v1` | `workflow-pv-point-label-v1` |
| `pv_tsc` | `workflow-pv-tsc-train-eval-v1` | `workflow-pv-tsc-predict-v1` | `workflow-pv-tsc-label-v1` |

TSC 四个核心算子均在 `backend-service/services/operator_backends/`：`tsc_sliding_window.py`、`tsc_train_eval.py`、`tsc_predict.py`、`emit_tsc_label_proposal.py`；`OperatorRouter.auto_discover()` 根据模块导出的 `OPERATOR_ID` 和 `execute` 自动发现。

`backend-service/services/operator_execution/slot_workflows.py` — 维护 slot 到 train/predict/replay 模板的映射。本轮把 `benchmark_*` 和 `pv_point` 的 replay 回退写成显式兼容分支；这是现有 benchmark 复用链和测试依赖的约定，不是误接 TSC。未知产品槽不应据此推断拥有自己的 replay 画布。

---

## 6. 阶段 4：模型治理（registry、复验、Promote、滚动指针）

### 6.1 registry 保存什么，为什么单独存

`backend-service/data/slot_governance/{slot}/registry.json` — 按 `slot` 分区的文件型模型登记真源，供部署页、调度器和治理 API 共享当前选择；它与候选列表、训练 execution 分开存，避免“训练成功”被误等同于“已被采纳生产”。所有工件引用均为相对路径。

主要字段：

- `registry_version` — 乐观并发版本，Promote 时防止覆盖其他人的更新。
- `champion` — 当前正式生产模型登记。
- `challenger` — 已采纳为挑战者、等待或完成比较的模型登记。
- `rolling_detect_model` — 显式钉住的滚动检测候选/工件；设置 Challenger 不会自动改变它。当前调度解析顺序是 Champion → `rolling_detect_model` → Challenger → 最近候选，所以已有 Champion 时以 Champion 为准；TSC 当前无 Champion，复验后设置该指针即可固定下一轮检测模型。
- `updated_at` — 最后更新时间。
- `note` — 人类可读变更原因。

模型候选单独存于 `backend-service/data/slot_governance/{slot}/model_candidates.json`；复验记录和 Promote 审计也按 slot 分区。registry 是“当前指针”，不是全部历史。

### 6.2 治理操作顺序与接口语义

```text
candidate registered
  → POST /api/slot-governance/verifications/verify-async
  → 绑定并完成 evaluation execution
  → verification passed
  → POST /api/slot-governance/model-candidates/{model_candidate_id}/promote
  → 显式设置 rolling_detect_model
```

Promote 请求关键字段：

- `model_candidate_id` — URL 中的候选记录 ID。
- `verification_id` — 与该候选绑定且 `passed=true` 的复验记录 ID。
- `expected_registry_version` — 调用方读取到的 registry 版本，冲突时拒绝写入。
- `set_as_production` — 是否直接把该候选设为 Champion；`false` 时只登记为 Challenger，`true` 时写 Champion 并清空 Challenger。
- `production_slot` — 可选目标槽位；缺省使用候选自身 slot，且服务拒绝跨槽 Promote。
- `operator`、`reason`、`idempotency_key` — 操作者、原因和幂等键。

此处没有 baseline/challenger workflow 二选一：写入的是 `model_candidate_id` 所代表候选自身的 `source_workflow_id` 与模型工件。`set_as_production=false` 进入 Challenger；为 `true` 才进入 Champion。

`backend-service/data/slot_governance/{slot}/promotions_log.json` — Promote 审计日志。服务只通过 append 新 event 写入，不提供修改旧 event 的接口；每条记录包含候选 ID、复验 ID、是否设生产、目标 slot、前后 registry 版本、操作者、原因和时间。它用于审计，不代替 registry 当前指针。

### 6.3 当前 registry 实测状态

| 项 | `pv_day` | `pv_point` | `pv_tsc` |
|---|---|---|---|
| `registry_version` | 1 | 3 | 1 |
| `champion` | `null` | `null` | `null` |
| `challenger` | `mc-e0da38f4e5dd` | `mc-061e1ed64284` | `mc-63aa6730b608` |
| Challenger workflow provenance | ✅ 有 workflow + execution | ✅ 有 workflow + execution | ❌ 历史记录全空 |
| `challenger_verification_id` | ✅ `ver-fba9a32d7de1` | ✅ `ver-940e091dbe3e` | ❌ 无 |
| `rolling_detect_model` | ✅ 有 | ✅ 有 | ❌ 无 |

TSC 当前 Challenger：

- 候选 ID：`mc-63aa6730b608`。
- 工件：`data/models/tsc/tsc-multirocket-grid-20260904034613-1852f480`。
- representation：`clock_grid_288_mask`，channels 为 `value / i_cal / is_measured`。
- 评估：`grid_device_isolated_holdout`，3 seed，不是 strict-10。
- `production_contract_valid=false`。
- provenance 为空，没有 verification，也没有 rolling pointer。

**迁移原则：** 新代码不会反向伪造或补写历史候选。必须等一次真实 strict-10 画布训练成功，生成新的 provenance 候选，再按“复验通过 → 显式设置滚动指针 → 必要时 Promote”的顺序迁移。当前旧 Challenger 不应强制 Promote。

### 6.4 strict-10 的数据约束

当前 freeze 只有 35 个离散日期。strict 评估要求日期隔离与设备隔离交叉成立；实测某些 seed 下会得到 0 个测试样本或类别不足。放宽 isolation 可以跑通实验，但不能据此把生产合同标为有效。解决方向优先是补连续日期和类别覆盖，而不是绕过生产闸门。

---

## 7. 阶段 5：按日滚动检测

### 7.1 三路径当前执行方式

| 路径 | 是否执行画布 | 当前事实 |
|---|---|---|
| `pv_day` | ✅ | 仍使用无 slot 的 quickval predict 模板，而不是专用 `workflow-pv-day-predict-v1` |
| `pv_point` | ❌ | `SeqDailyStrategy` 仍直接调用逐点 predictor |
| `pv_tsc` | ✅ 本轮补齐 | 每设备日执行 `workflow-pv-tsc-predict-v1`，execution 持久化成功且结果唯一有效后才落账 |

### 7.2 TSC 检测真实画布链

`backend-service/services/scheduler/pv_dual_path/tsc_strategy.py` — TSC 日调度策略，负责按设备和日期查询上下文、执行预测、写审核单并推进游标。

每个设备日的链路：

```text
查前一日 + 目标日完整上下文
  → 写相对路径 prediction input 证据
  → resolve_predict_workflow_id("pv_tsc")
  → workflow-pv-tsc-predict-v1
  → run_slot_workflow_sync(trigger_source=scheduler,
                           require_persisted_execution=True)
  → 校验恰好一个目标设备日预测
  → 写检测结果 / review evidence
  → 推进该设备游标
```

持久化 execution 包含 `source_workflow_id`、`source_workflow_version`、graph digest、输入相对路径、模型窗口配置与节点结果。任何以下情况都 fail-closed：画布失败、execution 证据持久化失败、输出缺失、输出不是目标唯一设备日。失败日立即 `break`，该设备后续日期本轮不再执行，游标不越过失败日，下一轮可以幂等重试。

选择“每设备日一次冻结画布”而不是整批执行，是为了保留失败日粒度和原有游标语义；代价是 execution 数量和调度开销更高。

### 7.3 游标与数据窗口

三条策略的游标都以 `(slot, modeling_path)` 分区。TSC 的 `_lazy_init_cursors()` — 首次运行时从历史 `pv_fault/legacy_day` 设备集合初始化当前水位，只检测新数据，不自动回补全部历史。

新到点只决定待检测目标日；真正推理会重新查询“前一日 + 目标日”完整上下文，避免被点路径标签状态截断。

### 7.4 历史业务运行与本轮 validation smoke

历史业务回执仍显示：最后一次成功覆盖 8 台设备 × 7 天，共 56 个设备日；随后调度器曾失败，因此 run-status 为 `stale` / `scheduler_failed_after_last_receipt`。这条历史运行发生在本轮画布改造前，不能作为新执行封装的生产验收。

本轮另做了受控 validation smoke：它只写预测输入与 execution 审计证据，不推进游标、不生成审核单、不修改候选或 registry。

- workflow：`workflow-pv-tsc-predict-v1`。
- execution：`exec-validation-9c5a4206964a`。
- 输入：现有 29,944 行预测输入与当前 Challenger。
- 结果：8/8 设备日成功，0 failed；两个节点均 success；graph digest 已持久化。
- `governance_eligible=false` — validation execution 不可拿去登记模型治理。
- 未推进调度游标、未写人工审核、未修改 registry。

---

## 8. 阶段 6-7：人工审核、精度与回流

### 8.1 精度从持久化事实重建

`_accuracy_from_persisted_session()` — 输入 review session，从最后一条有效 verdict 和 session units 重建 label pairs、混淆矩阵、动作摘要与诊断；它不信任前端缓存指标。

只统计 `confirm / correct / new_label` 且 `is_ground_truth` 不为 `false` 的单位。TSC 的 `metric_scope` 为 `review_session_device_day`，天/点路径使用各自 unit 口径。

### 8.2 已实测 TSC 审核精度

历史 review `rev-tsc-pred-20260904060512-2e7e6c83`：

- counted units：56。
- classifier accuracy：0.892857（89.3%）。
- macro precision / recall / F1：0.446 / 0.500 / 0.4717。
- confirm 50、correct 6。
- 真实只出现标签 1 和 11，模型把 56 个样本都预测成 11。

因此高 Accuracy 来自多数类，Macro-F1 才暴露泛化问题；持久化诊断未发现重复 verdict、预测/真值缺失或 unit 冲突。

### 8.3 回流闭环

```text
提交 verdict（不入账）
  → complete-and-admit（freeze=false）
  → 手动 freeze 或累计服务形成重训 request
  → 后台 cumulative retrain
  → 真实训练画布 + execution provenance
  → 候选 → 复验 → 滚动指针 / Promote
  → 下一轮检测
```

手动重训必须后台执行，因为 freeze 和训练可能远超前端 HTTP 超时。自动重训只有在累计服务写入 pending request ID 后才会启动。

---

## 9. 页面完成度

### 9.1 主要路由

| 路由 | 页面职责 |
|---|---|
| `/iterative-labeling` | 审核、模型对比、天/点打标、TSC 实验 tab |
| `/iterative-labeling?tab=review&review_slot={slot}` | 按槽位打开人工审核队列 |
| `/accuracy-operations` | 三槽精度运营 |
| `/datasets/cumulative-training/{slot}` | 指定槽位的累计训练账本 |
| `/algorithm-deployment?slot={slot}&tab={tab}` | 模型部署、治理与调度 |
| `/workflow/editor/{workflow_id}` | 打开冻结工作流画布 |
| `/workflow/list` | 工作流模板列表 |

### 9.2 页面能力矩阵

| 页面 | `pv_day` | `pv_point` | `pv_tsc` | 说明 |
|---|---|---|---|---|
| 天/点打标 tab | 🟢 | 🟢 | 🔴 | 名称和流程仍只覆盖天/点 |
| 人工审核队列 | 🟢 | 🟢 | 🟢 | 三槽可按 `review_slot` 过滤 |
| 提案审核面板 | 🟢 | 🟢 | 🟢 | TSC 展示设备日时序与重叠窗口证据 |
| 累计训练集 | 🟢 | 🟢 | 🟢 | slot 走路由参数 |
| 模型部署 / 对比 | 🟢 | 🟢 | 🟢 | TSC 有独立管理和对比内容 |
| 精度运营 | 🟢 | 🟢 | 🟢 | 三个专用面板 |
| 观测台 | 🟢 可写 | 🟢 可写 + replay | 🟡 只读 | TSC 只读是产品约束 |
| 工作流编辑器 | 🟢 | 🟢 | 🟢 | 三槽模板与 TSC 算子可见 |

### 9.3 本轮前端修复

`frontend-sevice/src/components/slot/SlotDeployedModelPanel.tsx` — 展示指定槽位已部署模型、治理状态和操作入口。其审核跳转现在按 slot 生成：

- `pv_tsc` → `/iterative-labeling?tab=review&review_slot=pv_tsc`。
- `pv_day` / `pv_point` → 保留天/点打标入口。

编译和生产构建已通过；尚未在浏览器里手工点击验证路由与页面渲染。

### 9.4 过期设计文档

`docs/project/pv_fault/spec/pv-fault-timeseries-diagnosis/tsc-platform-integration-plan.md` — 旧集成计划仍包含 288×2、stride=72 和未实际创建的组件名；当前事实是 288×3 clock-grid，运行界面由 `PvTscAccuracyOpsPanel.tsx` 与 `TscExperimentDetail.tsx` 等现有组件承载。该计划需要后续单独同步，不应当作当前实现真源。

---

## 10. 前后端对齐结论

### 10.1 关键 API 客户端

| 文件 | 职责 |
|---|---|
| `frontend-sevice/src/services/iterativeLabelingApi.ts` | 迭代标注、审核与精度接口 |
| `frontend-sevice/src/services/slotCumulativeApi.ts` | 累计数据、候选与部分观测接口 |
| `frontend-sevice/src/services/slotDatasetsApi.ts` | 槽位数据集与提案接口 |
| `frontend-sevice/src/services/slotGovernanceApi.ts` | 候选、复验、Promote、registry 接口 |
| `frontend-sevice/src/services/slotObservabilityApi.ts` | 日历、水位和检测结果接口 |
| `frontend-sevice/src/services/deploymentApi.ts` | 调度与部署状态接口 |

### 10.2 仍存在的对齐问题

| 问题 | 当前事实 | 影响 |
|---|---|---|
| TSC REST 打标未执行真实画布 | preferred 已正确，但 shortcut 仍直接 KMeans | 无法证明无标签 TSC 故事线走了 `tsc_predict → emit_tsc_label_proposal` |
| TSC canonical 打标前端入口不完整 | 审核 UI 存在，启动模型辅助画布的产品入口不清晰 | 用户无法从一个页面完整走完“选数据 → 执行 → 审核” |
| 历史 TSC registry 未迁移 | 当前 Challenger 仍无 provenance / verification / rolling pointer | 新代码存在，但调度治理仍消费旧历史状态 |
| 三路径检测实现不完全同构 | day 用 quickval 图，point 直连 predictor，TSC 用专用冻结图 | 跨路径审计和执行证据口径仍不一致 |

### 10.3 2026-09-07 已修项

| 项 | 修复结果 |
|---|---|
| 空精度误显示 0% | 后端返回 unavailable，前端显示“未产出”而非 0% |
| 重复裁决改判失真 | 写入按 unit 去旧留新，读取增加冲突诊断并 fail-closed |
| 288×2 绕过表示合同 | strict 门禁、快照构建和候选登记统一为 288×3 `clock_grid_288_mask` |
| TSC 金标文件名写死风险 | 参考标签读取增加内容寻址目录 glob |
| preferred 模板漏 TSC | 三槽显式映射，TSC 指向自己的 label workflow |
| 模型部署页审核跳错 | TSC 进入 `review_slot=pv_tsc` 审核队列 |
| TSC 累计训练绕过画布 | 改为冻结 CSV/Parquet → train workflow → 持久化 execution → provenance 候选 |
| TSC 日检测绕过画布 | 改为每设备日执行 predict workflow，持久化失败则不推进游标 |
| replay 回退语义隐含 | 对 `pv_point` / `benchmark_*` 显式保留兼容约定 |

---

## 11. 剩余差距与正确推进顺序

| # | 优先级 | 剩余工作 | 完成标准 |
|---|---|---|---|
| 1 | **P0** | 用真实累计 freeze 跑一次 strict-10 TSC 训练画布 | execution 成功持久化；新 candidate 同时有 workflow provenance、request/snapshot lineage、`production_contract_valid=true` |
| 2 | **P0** | 对新候选做正式 verification | verification 与候选绑定且 `passed=true`，评估 execution 可审计 |
| 3 | **P0** | 显式设置 `rolling_detect_model` | registry 指向已复验新候选；下一轮调度明确消费该工件 |
| 4 | **P1** | 数据覆盖补强 | 连续日期、设备与类别覆盖足以稳定通过日期 × 设备双隔离，不通过降低 strict 门槛作弊 |
| 5 | **P1** | TSC 无标签打标 REST 接真实画布 | API 实际执行 `workflow-pv-tsc-label-v1`，保存 execution/proposal lineage，失败不产提案 |
| 6 | **P1** | 补全 TSC canonical 打标 UI 故事线 | 浏览器可完成选数据、启动画布、看状态、审核、确认入累计 |
| 7 | **P2** | 统一 day/point 自身画布语义 | day 改专用 predict 图、point 评估是否迁移冻结图；先做回归，不与本轮 TSC 改动混杂 |
| 8 | **P3** | 更新旧集成计划 | 删除 288×2 / stride=72 和不存在组件名 |

**不可颠倒的顺序：** strict-10 真实训练成功 → 新 provenance 候选 → verification passed → 设置 rolling pointer → 再考虑 Promote。当前历史候选 `production_contract_valid=false`，不得用强制 Promote 伪造闭环。

---

## 12. 关键文件索引

### 12.1 后端代码

| 文件 | 在项目中的职责 |
|---|---|
| `backend-service/api/iterative_labeling.py` | 迭代标注 HTTP 入口；精度重建、累计重训、clustering run 和提案 API 都在这里，TSC 重训画布接线也位于此文件 |
| `backend-service/api/workflows_enhanced.py` | 通用画布执行与 async execution 持久化；`_execute_pipeline_sync()` 是底层纯执行器 |
| `backend-service/api/slot_governance.py` | registry、候选、复验、滚动指针与 Promote HTTP API |
| `backend-service/services/scheduler/slot_workflow_runner.py` | 同步执行冻结 slot workflow，按 functionId 覆写算子参数，计算 graph digest 并持久化 execution；训练和 TSC 检测共用 |
| `backend-service/services/scheduler/pv_dual_path/tsc_strategy.py` | TSC 每设备日检测、失败日 break、审核产出与游标推进 |
| `backend-service/services/scheduler/pv_dual_path/legacy_day_strategy.py` | 天路径检测策略，当前仍使用 quickval predict 图 |
| `backend-service/services/scheduler/pv_dual_path/seq_daily_strategy.py` | 点路径逐点/设备日 replay 检测策略 |
| `backend-service/services/operator_execution/slot_workflows.py` | slot 到 train/predict/replay 冻结模板的映射与 benchmark replay 兼容 |
| `backend-service/services/slot_datasets/label_proposals.py` | 三槽提案存储、参考金标发现和 confirm → curated → 累计链路 |
| `backend-service/services/slot_datasets/snapshots.py` | 累计账本、来源优先级、去重和 freeze 物化 |
| `backend-service/services/slot_governance/model_candidates.py` | 候选登记；新入口验证 workflow execution provenance，旧 retrain 入口仅保留兼容 |
| `backend-service/services/slot_governance/provenance.py` | 校验 execution 存在、成功、slot 一致、可治理并包含模型工件 |
| `backend-service/services/slot_governance/registry.py` | 按 slot 持久化 Champion、Challenger 和滚动检测模型指针 |
| `backend-service/services/slot_governance/promote.py` | 验证 passed 复验、乐观锁更新 registry，并追加 Promote 审计日志 |
| `backend-service/services/iterative_labeling/tsc/tsc_pipeline.py` | MultiRocket strict 评估与生产合同门禁 |
| `backend-service/services/iterative_labeling/tsc/grid_day_builder.py` | 288×3 clock-grid 构建和 mask-aware 预处理 |

### 12.2 前端代码

| 文件 | 在项目中的职责 |
|---|---|
| `frontend-sevice/src/pages/IterativeLabelingListPage.tsx` | 标注工作台 tab、三槽审核选择和天/点打标入口 |
| `frontend-sevice/src/pages/AccuracyOperationsPage.tsx` | 按 slot 分发三条路径的精度运营面板 |
| `frontend-sevice/src/pages/CumulativeTrainingLedgerPage.tsx` | 展示累计入账、freeze 和重训状态 |
| `frontend-sevice/src/pages/AlgorithmDeploymentPage.tsx` | 模型部署、治理与调度总入口 |
| `frontend-sevice/src/components/slot/SlotDeployedModelPanel.tsx` | 展示已部署模型和治理操作；本轮修复 TSC 审核跳转 |
| `frontend-sevice/src/components/slot/SlotLabelProposalReviewPanel.tsx` | 三槽提案审核，TSC 展示设备日时序证据 |
| `frontend-sevice/src/components/slot/PvTscAccuracyOpsPanel.tsx` | TSC 运行状态、审核精度、候选评估与观测信息 |
| `frontend-sevice/src/components/pv-fault/ModelPathManager.tsx` | Champion / Challenger 等路径模型管理 |

### 12.3 持久化数据

| 相对路径 | 存什么、为何存在 |
|---|---|
| `backend-service/data/workflows_enhanced/workflow-pv-*.json` | 冻结画布定义，供编辑器和运行时按 ID 加载 |
| `backend-service/data/execution_history/` | 按 workflow 和 execution ID 保存执行证据；provenance 校验从这里读取 |
| `backend-service/data/slot_datasets/{slot}/cumulative_labeled_manifest.json` | 按槽位记录累计入账事件，不与 freeze 产物混淆 |
| `backend-service/data/slot_datasets/{slot}/snapshot_chain.json` | 按槽位记录不可变 freeze 版本链 |
| `backend-service/data/slot_governance/{slot}/model_candidates.json` | 按槽位保存全部候选历史和来源证据 |
| `backend-service/data/slot_governance/{slot}/registry.json` | 按槽位保存当前 Champion/Challenger/滚动指针，供 UI 和调度共享 |
| `backend-service/data/slot_governance/{slot}/promotions_log.json` | 按槽位追加 Promote 审计事件，不作为当前模型指针 |
| `backend-service/data/iterative_labeling/pv_scheduler/pv_tsc/prediction_last_run.json` | TSC 最近业务调度回执和 freshness 依据 |

---

## 13. 本轮验证记录

### 13.1 静态、测试与构建

在 `backend-service/` 运行相关 Python 编译检查，覆盖 10 个相关模块，结果 0 error。

```powershell
conda run --no-capture-output -n cp_web python -m py_compile api/iterative_labeling.py services/operator_execution/slot_workflows.py services/scheduler/pv_dual_path/tsc_strategy.py services/scheduler/slot_workflow_runner.py services/slot_datasets/label_proposals.py services/slot_governance/model_candidates.py services/iterative_labeling/review_session.py services/iterative_labeling/accuracy_evaluator.py services/iterative_labeling/cumulative_training.py services/iterative_labeling/tsc/tsc_pipeline.py
```

focused pytest：31 passed，44 warnings，20.32s。warnings 均为既有 Pydantic/SQLAlchemy deprecation 或 namespace warning。

```powershell
conda run --no-capture-output -n cp_web python -m pytest tests/test_cumulative_ledger.py tests/test_train_source.py tests/test_mock_gold_accuracy.py tests/test_g4_slot_governance.py tests/test_g6_reuse_report.py tests/test_slot_product_scheduler.py -q
```

在 `frontend-sevice/`：

```powershell
npx tsc --noEmit --pretty false
npm run build
```

两者 exit 0。build 只有既有 Tailwind “No utility classes were detected” 与 Vite chunk >500KB warning。

### 13.2 真实冻结图 smoke

`workflow-pv-tsc-predict-v1` 已用现有 29,944 行输入和当前 Challenger 实际执行：

- execution：`exec-validation-9c5a4206964a`。
- 8/8 设备日成功，0 failed。
- 节点结果、graph digest 和 validation metadata 已写 execution history。
- `governance_eligible=false`。
- smoke 未写游标、未生成审核单、未修改候选或 registry。

训练侧只做了两类隔离 smoke：manifest 中冻结 Parquet 的相对路径解析；训练结果合同和 `register_model_candidate()` 的 provenance + request/snapshot metadata 登记。未执行真实 strict-10 模型训练。

---

## 14. 已知坑与红线

### 14.1 已知坑

1. `_execute_pipeline_sync()` 仍是纯执行器；需要 provenance 时，必须由 HTTP async wrapper 或 `run_slot_workflow_sync(require_persisted_execution=True)` 包装。
2. `complete-and-admit` 使用 `freeze=false`，审核完成不等于已有可训练快照。
3. `reviewed_at_cutoff` 是审核时间，不是原始数据时间。
4. freeze 事件部分地方使用 ISO 字符串排序，跨时区 offset 需要谨慎。
5. 当前 35 个离散日期不足以稳定满足 strict 日期 × 设备双隔离。
6. `pv_tsc` 观测只读是产品约束，不应当作 bug 放开演示写入。
7. TSC 每设备日一个 execution 保住了失败粒度，但会增加调度和持久化开销。
8. benchmark/pv_point replay 回退是显式兼容约定；不要在没有迁移 benchmark 调用方和测试前直接改成统一抛错。
9. 旧 TSC candidate/registry 不会自动获得新 provenance；禁止通过手工填字段伪造历史。

### 14.2 红线

- 不修改历史只读槽 `pv_fault` 的产品语义。
- 不把 validation execution 用于模型治理。
- 不在 strict 合同失败时强制 Promote 当前 TSC 候选。
- 不让预测成功但 execution 证据丢失的设备日推进游标。
- 不在代码、JSON 或持久化结果中写绝对文件路径。
- 工作区极脏：禁止 reset、clean、切分支或擅自提交。

---

## 15. 验证边界与下一步

### 15.1 已验证

- 相关后端模块 py_compile 0 error。
- focused pytest 31 passed。
- 前端 TypeScript 检查和生产构建成功。
- TSC predict 冻结 workflow 真实执行成功，execution evidence 和 graph digest 已持久化。
- validation execution 明确不可治理，且 smoke 无游标/审核/registry 副作用。
- TSC 训练输入 manifest 相对路径解析、288×3 结果合同和 provenance 登记在隔离环境通过。
- 当前磁盘 registry、候选、freeze 与历史审核精度均已区分记录。

### 15.2 未验证

- 未用真实累计 freeze 完整执行 `workflow-pv-tsc-train-eval-v1` 的 strict-10 训练。
- 未执行 `workflow-pv-tsc-label-v1`，也未验证 REST/UI 到该画布的完整接线。
- 未在浏览器中手工点击“部署 → 审核 → 精度 → 累计 → 重训”的完整故事线。
- 未跑全量后端 pytest。
- 未跑 `pv_day` / `pv_point` 的完整训练、检测或复验回归。

### 15.3 下一步最小安全动作

先补足或确认可满足 strict-10 的真实训练数据，再发起一次 TSC 累计重训。只有拿到 `production_contract_valid=true` 且带真实 workflow/execution provenance 的新候选后，才进行 verification；复验 passed 后显式设置 `rolling_detect_model`，最后再决定是否 Promote。任何一步失败都保留当前历史 registry，不越级写生产指针。
<!-- @AI_GENERATED: end -->
