<!-- @AI_GENERATED -->
# PV 三路径真实验收交接（2026-09-08）

> 适用范围：`pv_tsc`（MultiRocket 时序分类）、`pv_day`（设备日 RF）、`pv_point`（逐点序列模型）的真实端到端验收。  
> 文档性质：事实型交接，只写当前仓库中已经执行并有证据的结果；未执行、失败或只有脚本但无报告的事项均单独标明。  
> 安全边界：工作区很脏，禁止 `reset`、`clean`、切分支、擅自提交；所有代码与持久化数据路径必须是项目内相对路径；不得把公司数据库口令写入代码、脚本、报告或本文。

---

## 0. 接手人先看结论

本轮原目标是把此前未验证的五件事全部变成真实验收：真实 `pv_tsc` 累计 freeze strict-10 训练、`workflow-pv-tsc-label-v1` 完整打标链、浏览器“部署 → 审核 → 精度 → 累计 → 重训”、全量后端 pytest，以及 `pv_day` / `pv_point` 完整训练检测回归。

当前已拿到两个关键成果：

1. **真实 `pv_tsc` strict-10 已完整执行成功。** 真实 1,056,806 行累计 freeze 经完整画布生成 4,429 个 `[288,3]` 设备日样本，MultiRocket 与 Rocket-RF 各完成 10 次严格日期 × 设备双隔离评估，最终模型工件和 execution 均已持久化；`production_contract_valid`（生产评估合同是否有效）为 `true`。
2. **公司 MySQL 上的独立测试库已经建好。** `aip_algo_platform_test_kiro_20260908` 已迁移到 Alembic head，共 33 张表；后续全量 pytest 不需要写 `aip_algo_platform` 业务库。

同时发现两个产品问题：

- 正式模板默认的 `held_device_ratio=0.3`（测试设备比例 30%）与 `n_test_days=3`（末尾 3 个离散日期作为测试日期）在当前 freeze 上是 **0/10 可用 split**，原样执行必然无法通过 strict-10 合同。
- 新 strict 口径的 MultiRocket `macro_f1_mean`（十次划分平均 Macro-F1）只有 `0.0782`，且相对 Rocket-RF 的配对差为 `-0.0038`、只赢 `4/10`；旧模型的 `0.9538` 来自非生产口径的 3-seed 设备隔离 holdout，不能与本次 strict 结果直接比较。

---

## 1. 主验收任务状态

| 原任务 | 当前状态 | 已有证据 | 仍缺什么 |
|---|---|---|---|
| 1. 预检入口、数据、资源与隔离方式 | ✅ 完成 | 后端/前端健康预检、真实 freeze 画像、pytest 收集修复、治理文件基线哈希 | 无 |
| 2. 真实 `pv_tsc` strict-10 | 🟡 核心训练完成 | `exec-validation-d741dc207593`、10/10 split、模型目录、零治理污染报告 | 还未在隔离目录模拟“登记候选并核验 provenance”；validation 本身刻意不产生 candidate |
| 3. `workflow-pv-tsc-label-v1` 完整链路 | ⬜ 未执行 | 已确定输入、模型和提案目录隔离方案 | 需跑完整 DAG 并检查 proposal lineage |
| 4. 浏览器故事线 | ⬜ 未执行 | 已确定页面路由与已有完成审核会话 | 需安装 Chromium 并跑只读浏览器验收；不得代替人工确认真值 |
| 5. 全量后端 pytest | 🟡 前置完成 | 1,635 tests 收集 0 error；独立 MySQL 库已建好 | 尚未在独立库执行全量 pytest |
| 6. `pv_day` / `pv_point` 训练检测回归 | ⬜ 未执行 | 已确定 validation workflow 与临时状态目录方案 | 需真实执行并复核 registry/candidate 哈希不变 |
| 7. 更新产品事实文档与最终自审 | ⬜ 未执行 | 本交接文档已创建 | 所有验收完成后更新 `AGENTS.md`，再做全文件自审和构建检查 |

> 进度口径不要简化成“2/7 全完成”：第 2 项的真实训练、execution、合同和零污染已通过，但候选 provenance 的隔离登记子项仍未做。

---

## 2. 本轮实际修改

### 2.1 测试契约修复

`backend-service/tests/test_accuracy_operations_models.py` — 精度运营 Pydantic 模型的序列化与枚举契约测试。

原测试仍导入已经下线的 `TrainingAdjustmentTask` 和 `TrainingTaskStatus`，导致全量 pytest 在 collection 阶段中断。当前生产需求只保留 `shadow_switch`（影子切换）和 `observe`（继续观察）两种恢复通道，因此本轮只改测试，不恢复生产死契约：

- 删除两个悬空 import 和已经没有生产者/消费者的训练调整任务 round-trip。
- `RecoveryDecision`（恢复决策模型）strategy 改用真实字段：
  - `target_workflow_id` — 建议切换到的目标工作流 ID。
  - `target_version_tag` — 建议切换到的目标版本标签。
- 合法 `channel` — 恢复通道只允许 `shadow_switch` / `observe`。
- 增加负向测试，确认 `training_adjust` / `parallel` 会触发 Pydantic `ValidationError`。

验证结果：

```text
5 passed, 2115 warnings in 2.64s
1635 tests collected in 12.61s
```

warnings 均为仓库既有 Pydantic v1 API、SQLAlchemy 2.0 和 protected namespace 兼容告警；本轮没有把 warnings 当成测试通过的替代证据。

### 2.2 一次性验收脚本

以下脚本和报告放在 `output/pv_e2e_validation/`，只用于验收，不是产品运行入口：

| 相对路径 | 职责与当前状态 |
|---|---|
| `output/pv_e2e_validation/preflight_tsc_strict10.py` | 读取真实 freeze、构建 288×3 网格，但不 fit 模型；检查 10 个 strict split 是否满足样本、类别与隔离门槛。已执行。 |
| `output/pv_e2e_validation/tsc_strict10_preflight.json` | 上述预检报告；记录模板默认参数不可行及最小可行 strict 参数。已生成。 |
| `output/pv_e2e_validation/run_tsc_strict10.py` | 调用同步 validation 画布，完整执行真实 strict-10，并把治理文件前后 SHA256 不变作为硬断言。已执行。 |
| `output/pv_e2e_validation/tsc_strict10_run.json` | 训练总报告；包含 execution、模型工件、逐 split 指标、配对基线与治理零污染证据。已生成。 |
| `output/pv_e2e_validation/profile_tsc_freeze.py` | 只读分析 freeze 的日期、设备日、来源与 strict 指标结构上限。已执行。 |
| `output/pv_e2e_validation/tsc_freeze_profile.json` | 数据画像报告；证明是 35 个离散日期而不是连续 35 天。已生成。 |
| `output/pv_e2e_validation/setup_isolated_mysql.py` | 从运行时密钥读取公司 MySQL 连接，只创建独立测试库并执行 Alembic forward migration；不打印或持久化口令。已执行。 |
| `output/pv_e2e_validation/isolated_mysql_setup.json` | 独立测试库建表报告；不含连接口令。已生成。 |
| `output/pv_e2e_validation/diagnose_tsc_seed90.py` | 计划重跑 seed 90，保存预测分布、混淆矩阵及两种 Macro-F1 口径，用于进一步解释低分。脚本已写，但**没有生成报告，结果未验收**。 |

---

## 3. 真实 strict-10 验收事实

### 3.1 输入与完整画布

真实输入：

`backend-service/data/slot_datasets/pv_tsc/snapshots/snap-pv_tsc-20260904-100046-981f.parquet` — 当前 `pv_tsc` 累计账本最新不可变 freeze；包含 1,056,806 行已标注时序数据。

完整工作流：

`backend-service/data/workflows_enhanced/workflow-pv-tsc-train-eval-v1.json` — TSC 训练画布，DAG 为：

```text
load_csv
  → tsc_sliding_window（构建 [N,288,3]）
  → tsc_train_eval（MultiRocket strict 多次评估 + 最终拟合）
```

调用入口 `run_slot_workflow_sync()` 位于 `backend-service/services/scheduler/slot_workflow_runner.py`：输入 `slot`（产品槽位）、`workflow_id`（画布 ID）、按 `functionId`（算子 ID）分组的参数覆盖与 execution metadata；输出同步执行摘要，并把完整 execution 写到 execution history。此次使用：

- `trigger_source="validation"` — 触发来源是受控验证，execution ID 使用 `exec-validation-*` 前缀。
- `execution_purpose="validation"` — 执行目的为验证，不是产品重训。
- `governance_eligible=false` — execution 不允许用于直接登记/晋升生产治理。
- `require_persisted_execution=true` — execution 证据写盘失败时整体 fail-closed。

### 3.2 模板默认参数为什么没直接用

模板默认：

| 字段 | 中文含义 | 值 | 真实预检结果 |
|---|---|---:|---|
| `split_mode` | 划分模式 | `strict` | 保留 |
| `n_repeats` | 重复划分次数 | 10 | 保留 |
| `held_device_ratio` | 每轮完全留给测试集的设备比例 | 0.3 | 不可行 |
| `n_test_days` | 时间排序末尾用作测试的离散日期数 | 3 | 不可行 |
| `min_test_samples` | 每轮最少测试样本数 | 30 | 保留，不降门槛 |
| `require_production_contract` | 是否要求生产合同完整才保存模型 | `true` | 保留 |

模板默认十个 seed 的测试样本只有 6–15 个，且有一轮测试集只有 1 类，因此 `0/10` 可用。这里没有把 `min_test_samples` 从 30 降到 10 来制造通过，而是在继续保持 strict、10 repeats、最少 30 样本的前提下做只读可行性搜索。

最终 validation 使用：

- `held_device_ratio=0.6` — 测试设备比例提高到 60%。
- `n_test_days=5` — 测试日期扩大到最后 5 个离散日期。
- 其余生产门槛全部不变。

这 10 个 split 的测试样本为 37–55，全部满足：

- `device_overlap=0` — 训练/测试设备无交集。
- `date_overlap=0` — 训练/测试日期无交集。
- `identical_windows=0` — 测试窗口没有与训练窗口字节级重复。
- `clean=true` — 当前 split 隔离自检通过。

### 3.3 execution 与模型工件

| 字段 | 中文含义 | 实测值 |
|---|---|---|
| `execution_id` | 本次画布执行唯一 ID | `exec-validation-d741dc207593` |
| `workflow_id` | 来源训练画布 ID | `workflow-pv-tsc-train-eval-v1` |
| `status` | execution 最终状态 | `success` |
| `governance_eligible` | 是否可进入模型治理 | `false` |
| `n_splits_completed` | 完成的 strict 划分数 | 10 |
| `n_splits_requested` | 请求的 strict 划分数 | 10 |
| `production_contract_valid` | 生产评估合同是否有效 | `true` |
| `n_samples` | 288×3 设备日样本数 | 4,429 |
| `n_classes` | 标签类别数 | 13 |
| `macro_f1_mean` | 13 类固定标签空间的平均 Macro-F1 | 0.0782 |
| `balanced_accuracy_mean` | 平衡准确率均值 | 0.3016 |
| `executionTime` | 画布总耗时 | 1,407.189 秒 |

execution 证据：

`backend-service/data/execution_history/by_id/exec-validation-d741dc207593.json` — 按 execution ID 保存的不可变运行证据，记录输入相对路径、图摘要、三个节点结果、时间、指标和 validation metadata。

模型工件：

`backend-service/data/models/tsc/tsc-multirocket-20260907101950-65eb28f6/` — 本次最终 MultiRocket 目录：

- `model.pkl` — 已拟合模型序列化工件。
- `metadata.json` — 模型、窗口与生产合同元数据。
- `evaluation_report.json` — MultiRocket 与 Rocket-RF 的完整 10-split 评估报告。

所有工件引用在 execution 和报告中均为相对于 `backend-service/` 的路径，没有写入 Windows 绝对路径。

### 3.4 与 Rocket-RF 的配对结果

`pairwise_vs_baseline` — 在相同 seed、相同 train/test split 上比较模型，避免不同划分难度混入模型差异：

| 字段 | 中文含义 | 实测值 |
|---|---|---:|
| `vs` | 对照模型 | `rocket_rf` |
| `macro_f1_diff_mean` | MultiRocket 减对照的 Macro-F1 平均差 | -0.0038 |
| `macro_f1_diff_std` | 配对差标准差 | 0.0338 |
| `wins` | MultiRocket 胜出的 split 数 | 4 |
| `n_paired` | 有效配对 split 数 | 10 |

当前不能证明 MultiRocket 优于 Rocket-RF；“合同通过”只说明评估证据完整、隔离干净，不等于业务精度足够或模型显著胜出。

### 3.5 治理零污染

validation 前后以下治理真源 SHA256 完全一致：

| 相对路径 | 文件职责 | SHA256（前后相同） |
|---|---|---|
| `backend-service/data/slot_governance/pv_tsc/registry.json` | 按 `slot` 保存当前 Champion、Challenger 与滚动检测指针；与训练成功分开存，避免模型产出被误当成已采纳生产。 | `D9644EAE749D09A94C52007BC92D93A6723D29591C8496E233B684E6245A6630` |
| `backend-service/data/slot_governance/pv_tsc/model_candidates.json` | 按 `pv_tsc` 槽位保存全部候选及来源 provenance；它是候选历史，不是当前生产指针。 | `46E5FE6E4E78FC966530C4042F8F1211B64FAC3DE49CF61C6CA7C7ECBA00D8B3` |
| `backend-service/data/iterative_labeling/cumulative_training/pv_tsc/state.json` | 保存累计重训 request、snapshot 和进度；与统一累计账本 freeze 分层。 | `A70F14BCB347CA5272420B4FB97C0AD37CB23EB4BD09EA354A379AF9A5946040` |

`backend-service/data/slot_datasets/pv_tsc/label_proposals.json` — TSC 提案索引；训练前不存在，训练后仍不存在。

本次没有执行 Promote（晋升/采纳）：

- 没有 `model_candidate_id` — 候选记录 ID，因为 validation 不应登记 candidate。
- 没有 `set_as_production=true` — 没有把候选设为 Champion。
- 没有 `production_slot` — 没有写入任何目标槽位 registry。
- 没有向 `promotions_log.json` — 只追加的晋升审计日志，写入任何事件。

后续若登记隔离候选，候选的 `source_workflow_id` — 来源画布 ID、`source_execution_id` — 来源 execution ID、`model_artifact_ref` — 相对模型工件路径和 `evaluation_contract` — 固定评测量尺必须同时存在；不得给旧历史候选手工补字段伪造 provenance。

---

## 4. “只有 35 天”到底指什么

### 4.1 不是连续 35 天，也不是原始库只有 35 天

实测 freeze 的物理 `time` 日期为：

- 最早：2020-05-06。
- 最晚：2022-03-07。
- 日历跨度：671 天。
- 真正出现数据的不同日期：35 天。
- 日期覆盖率：`35 / 671 = 5.22%`。

所以“35 天”准确含义是：**当前累计训练 freeze 中只有 35 个离散物理日期有已准入的标签数据**。它不代表公司原始测量表只有 35 天，也不代表 freeze 代码把完整 671 天截成连续 35 天。

35 个日期分布为：

```text
2020-05-06 ~ 2020-05-12（7 天）
2021-08-22 ~ 2021-08-30（9 天）
2021-10-07 ~ 2021-10-08（2 天）
2021-11-18 ~ 2021-11-24（7 天）
2022-01-01、01-02、01-03、01-11（4 天）
2022-02-03、02-04、02-05、02-07（4 天）
2022-03-01、03-07（2 天）
```

### 4.2 “累计全量”的真实定义

`freeze_cumulative_at()` 位于 `backend-service/services/slot_datasets/snapshots.py`：输入 `slot`（槽位）和 `reviewed_at_cutoff`（审核事件时间上界），输出截至该审核时刻已进入累计账本的不可变合并快照。它不会直接扫描 `training_samples` 或原始测量库补齐日期。

当前 `pv_tsc` 累计账本只有两条 inclusion event（准入事件）：

| 来源 | 中文含义 | 行数 | 权威设备日 |
|---|---|---:|---:|
| `gold_bootstrap` | 初始已标注金标准基座 | 1,040,686 | 4,401 |
| `daily_review` | 人工完成设备日审核后准入的覆盖层 | 16,120 | 56 |

合并后为 1,056,806 行、4,457 个原始设备日；网格门槛拒绝 28 个设备日，最终保留 4,429 个可训练设备日。

来源真源：

- `backend-service/data/slot_datasets/pv_tsc/cumulative_labeled_manifest.json` — 按 `pv_tsc` 分区保存“哪些已发布 labeled version 已进入累计训练集、审核时间和来源”；它单独存在是为了让 freeze 可按审核事件重放，不与原始业务测量表混淆。
- `backend-service/data/slot_datasets/pv_tsc/snapshot_chain.json` — 按 `pv_tsc` 分区保存不可变 freeze 版本链、输入事件、物化文件和数据观察摘要；它单独存在是为了审计每次训练到底消费了哪一版数据。

当前没有 `time_wall`（训练/留出固定日期墙）：最新 chain 的 `time_wall` 与 `sample_time_before` 均为 `null`。因此 35 个日期不是被留出墙裁掉的，而是上游金标文件本身就只包含这些离散日期。

### 4.3 为什么 105 万行仍然算日期稀疏

当前有 2,226 个 `site_id + device_id + branch_id` 物理序列键。如果每条序列在 35 个日期都完整存在，理论上应有 77,910 个设备日；实际只有 4,457 个，约 5.7%。

每条物理序列拥有的日期数：

- 中位数：1 天。
- 平均数：2.002 天。
- 最小：1 天。
- 最大：7 天。

105 万“行”主要来自每个设备日约 288 个 5 分钟点；行数大不等于日期 × 设备组合密集。strict 评估同时隔离日期和设备后，交集测试集会迅速缩小。

### 4.4 三个容易误解的字段

- `tsc_target_day` — 该上下文行服务于哪个 TSC 目标预测日，由真实日调度策略写入；不是行自身日期。当前 gold 1,040,686 行为空，只有 16,120 条人工审核覆盖行有值。
- `time_window` — 当前 freeze 中表示人工框选范围，例如 `start__end#freeform`；不是 MultiRocket 内部的重叠预测窗口。
- `_dataset_version_id` — 当前最终权威行来自哪个 labeled version；freeze 在来源合并去重前写入，用于追踪 gold 或人工 review 哪一层最终胜出。

### 4.5 正确扩大覆盖的方法

不能靠把 freeze cutoff 调晚或重复点击 freeze 产生新日期。正确链路是：

```text
真实调度/历史 backfill 产生目标设备日
  → 真实模型检测
  → 生成 review session（审核会话）
  → 人工完成设备日框选与最终标签
  → complete-and-admit（完成并准入）
  → 发布新的 curated labeled version
  → 写入 cumulative inclusion event
  → 再 freeze
```

`TscDailyStrategy.run_cycle()` 位于 `backend-service/services/scheduler/pv_dual_path/tsc_strategy.py`：输入设备游标、水位和当前模型，输出设备日预测、review session 与安全游标推进；它只处理水位之后的新日期，不会自动把数据库全部历史日期回填。

如果目标是补 35 天之外的历史，需新增受控 historical backfill（历史回补）或批准后的批量 gold admission（批量金标准准入），不能把未审核的全历史原始测量直接塞进 freeze。

---

## 5. strict 精度为什么这么低

### 5.1 评测场景比旧模型严格得多

本次每轮测试集必须同时满足：

1. 日期在训练集之后。
2. 设备在训练集从未出现。
3. 窗口没有字节级重复。

可行参数下，每轮训练只使用全部 4,429 样本中的 1,677–1,831 个，即约 37.9%–41.3%；测试集只有 37–55 个设备日，出现 4–6 个类别。这是在测“新日期 + 新设备”的迁移能力，不是随机抽样或只隔设备。

旧模型 `data/models/tsc/tsc-multirocket-grid-20260904034613-1852f480` 的 `macro_f1_mean=0.9538` 来自：

- `evaluation="grid_device_isolated_holdout"` — 只做设备隔离 holdout。
- 3 个 seed，不是 10 次 strict。
- `production_contract_valid=false`。

两者不是同一把尺子，不能用 0.95 减 0.0782 直接解释为模型性能突然跌了 92 个百分点。

### 5.2 当前 Macro-F1 的结构性压低

当前 `_metrics()` 固定以全数据 13 类作为 Macro-F1 标签空间。每轮测试只出现 4–6 类，不出现的类也按 F1=0 进入平均。

即使模型把测试集中实际出现的类别全部预测完美，单轮“13 类固定分母 Macro-F1”的理论上限也只有：

- 出现 4 类：`4 / 13 = 0.3077`。
- 出现 5 类：`5 / 13 = 0.3846`。
- 出现 6 类：`6 / 13 = 0.4615`。

本次十轮平均结构上限约 `0.3846`。因此 `0.0782` 不能与普通“只按测试出现类别计算”的 Macro-F1 直接比较。

但这不是说模型已经足够好：`0.0782` 仍明显低于该结构上限。`balanced_accuracy_mean=0.3016` 相对本批测试类别数对应的平均随机机会水平约 `0.2033`，说明模型有一定信号，但泛化较弱。

### 5.3 类别极不均衡

4,429 个设备日的类别分布中：

- 类 1：2,073 个（46.8%）。
- 类 0：577 个。
- 类 11：420 个。
- 类 9：1 个。
- 类 10：6 个。
- 类 16：4 个。

极少类在日期 × 设备双隔离后很容易只落在训练侧或测试侧，导致某些类根本没有可学习/可评估的跨域证据。单纯增大 `held_device_ratio` 只能凑足测试数量，不能修复类别覆盖。

### 5.4 目前可以下的结论与不能下的结论

可以下的结论：

- strict 评估链路、隔离自检和生产合同机制本身能真实运行。
- 当前数据在新日期 + 新设备场景下泛化较弱。
- MultiRocket 没有显著优于 Rocket-RF。
- 现有模板默认 split 参数与当前稀疏数据不匹配。
- 当前 Macro-F1 口径把测试未出现类也计 0，指标解释必须带口径说明。

不能下的结论：

- 不能说“模型真实准确率就是 7.82%”；0.0782 是固定 13 类 Macro-F1，不是 accuracy。
- 不能说“旧模型 95% 一定造假”；它测的是更容易、且不具生产合同资格的另一种 holdout。
- 不能说“把模板改为 0.6/5 就解决了”；它只解决 split 可执行性，没有解决类别和业务精度。
- 不能只凭一次 strict 报告决定 Promote。

### 5.5 尚缺的低分诊断

`output/pv_e2e_validation/diagnose_tsc_seed90.py` — 重建 seed 90 的真实 split 并保存预测分布、混淆矩阵、固定 13 类 Macro-F1 与测试出现类 Macro-F1。脚本已通过写入，但当前目录没有 `tsc_seed90_diagnostics.json`，说明上一次运行没有形成可验收报告。

接手后优先重跑：

```powershell
$env:PYTHONPATH='.'
conda run --no-capture-output -n cp_web python ../output/pv_e2e_validation/diagnose_tsc_seed90.py
```

运行目录必须是 `backend-service/`。只有报告文件生成、重读并核对模型预测分布后，才能进一步判断是否出现“只预测高频类”。

---

## 6. 独立 MySQL 测试库（方案 B）

### 6.1 已完成事实

已在同一公司 MySQL 实例创建：

```text
aip_algo_platform_test_kiro_20260908
```

它与业务库 `aip_algo_platform` 是不同 database。`output/pv_e2e_validation/isolated_mysql_setup.json` — 独立库创建与迁移报告，记录：

| 字段 | 中文含义 | 值 |
|---|---|---|
| `source_database` | 原业务数据库名，仅用于确认隔离 | `aip_algo_platform` |
| `target_database` | 后端测试使用的独立数据库名 | `aip_algo_platform_test_kiro_20260908` |
| `source_and_target_are_distinct` | 来源与目标是否不同 | `true` |
| `alembic_revision` | 独立库当前迁移版本 | `e7b9c2d4f6a8` |
| `table_count` | 建成的表数量 | 33 |
| `required_tables_present` | 逐点标签相关必需表是否齐全 | `true` |
| `credentials_persisted` | 报告/脚本是否持久化口令 | `false` |
| `business_database_ddl_or_dml` | 是否对业务库执行 DDL/DML | `false` |

`output/pv_e2e_validation/setup_isolated_mysql.py` — 独立库初始化脚本：从环境变量、根目录本地 env 或 `configs/db.yaml` 读取运行时连接；只执行 `CREATE DATABASE IF NOT EXISTS` 和对目标库的 Alembic forward migration；不会打印连接 URL 或口令。

### 6.2 全量 pytest 续跑方式

不要把公司口令写进命令历史、Markdown 或脚本。运行前用本机安全配置构造 `DB_CONNECTION_URL` — 数据库连接 URL，只把 URL 中的 database 部分改为 `aip_algo_platform_test_kiro_20260908`；同时设置：

```powershell
$env:DB_ENGINE='mysql'
$env:DB_ENABLED='true'
$env:DB_DUAL_WRITE='false'
$env:PYTHONPATH='.'
```

正式命令（在 `backend-service/` 运行，单进程，不使用 xdist）：

```powershell
conda run --no-capture-output -n cp_web python -m pytest -c pytest.ini tests -ra --durations=50
```

风险与检查：

- `tests/db/test_point_label_repository.py` — 会在独立库用随机 `TEST-plr-*` 设备号写逐点账本并定向清理。
- `tests/test_point_label_concurrency.py` — 会写 288 条 `TEST-conc-*` 测量点，并真实验证 MySQL `GET_LOCK`；只允许指向独立库。
- `tests/test_label_materializer.py` — 会写 `TEST-lm-*` 测量和标签并定向清理。
- `tests/pv_dual_path/test_e2e_integration.py::test_mysql_schema_not_yet_migrated_is_recorded_as_gap` — 这是一个历史“公司库尚未迁移”的只读缺口断言；独立库已经迁移到 head，该用例可能因前提过期失败。应按当前产品事实更新/skip，不得改回业务库只为让旧断言通过。

全量测试结束后查询独立库中 `site_id='TEST-site'` 的残留；如进程异常中止，先定向清理随机测试设备，不要 DROP 整库，除非用户明确授权。

---

## 7. 余下任务的最小安全执行顺序

### 7.1 任务 3：完整 TSC label workflow

目标画布：

`backend-service/data/workflows_enhanced/workflow-pv-tsc-label-v1.json` — `load_csv → tsc_predict → emit_tsc_label_proposal` 模型辅助设备日提案链。

已确定输入：

- `backend-service/data/iterative_labeling/prediction_inputs/pv_tsc/tsc-pred-20260904060512-2e7e6c83.csv` — 已有真实 TSC 预测输入。
- `backend-service/data/models/tsc/tsc-multirocket-grid-20260904034613-1852f480/` — 当前可加载历史模型；注意它不是 strict-10 合格候选。

必须隔离 proposal 写入：

- monkeypatch `services.operator_backends.emit_tsc_label_proposal._BACKEND_DIR` — 算子解析/输出后端根目录。
- monkeypatch `services.slot_datasets.label_proposals._BACKEND_DIR` — 提案服务后端根目录。
- monkeypatch `services.slot_datasets.label_proposals._DATA_DIR` — 提案索引和成员明细目录。

输出统一指向 `output/pv_e2e_validation/tsc_label_sandbox/`。完成标准：

- 三个节点全部 success，execution 已持久化。
- proposal ID、来源 workflow/execution、模型引用均存在。
- member 按物理设备日唯一。
- `n_windows` — 聚合使用的 TSC 子窗口数与 evidence 明细一致。
- 真实 `backend-service/data/slot_datasets/pv_tsc/label_proposals.json` 跑前不存在、跑后仍不存在。

### 7.2 任务 4：浏览器故事线

上次预检时后端 `8081`、前端 `3001` 健康，但接手时必须重新检查，不能假设进程仍在。Python Playwright 已安装，Chromium 当时未下载。

安装浏览器运行时（不改项目依赖）：

```powershell
conda run --no-capture-output -n cp_web python -m playwright install chromium
```

只读验收路由：

| 路由 | 页面职责 |
|---|---|
| `/algorithm-deployment?slot=pv_tsc&tab=model` | 查看 TSC registry、候选、滚动模型和训练入口。 |
| `/iterative-labeling?tab=review&review_slot=pv_tsc` | 查看 `pv_tsc` 审核队列。 |
| `/iterative-labeling/review?review_id=rev-tsc-pred-20260904060512-2e7e6c83&slot=pv_tsc` | 查看已有完成审核的设备日详情，不新增人工真值。 |
| `/accuracy-operations?slot=pv_tsc` | 查看 TSC 精度和证据口径。 |
| `/datasets/cumulative-training?slot=pv_tsc` | 查看累计 inclusion events、freeze 和重训入口。 |

完成标准：截图写入 `output/pv_e2e_validation/screenshots/`；记录 console/page errors 和 401/403/5xx；不点击“确认正确”、Promote、切换生产或真实重训按钮。

### 7.3 任务 5：全量 pytest

先在独立 MySQL 跑全量；失败按“本轮改动回归 / 既有失败 / 测试前提过期 / 外部依赖”分类。只修本轮契约或明显过期测试，不为绿灯修改生产语义。

### 7.4 任务 6：`pv_day` / `pv_point`

使用 `run_slot_workflow_sync()` 的 validation 入口和显式输入 freeze：

- `workflow-pv-day-train-eval-v1` — `pv_day` 训练评估画布。
- `workflow-pv-day-predict-v1` — `pv_day` 预测画布。
- `workflow-pv-point-train-eval-v1` — `pv_point` 训练评估画布。
- `workflow-pv-point-predict-replay-v1` — `pv_point` 预测/replay 画布。

scheduler/replay 的 session、binding、alarm、execution 状态必须 monkeypatch 到临时目录；不要直接运行 `_poc_freeze_train_detect.py`，它会 freeze、追加 candidate、覆盖 rolling pointer 并推进 day/point 状态。

跑前后复核以下真源 SHA256 不变：

- `backend-service/data/slot_governance/pv_day/registry.json` — `pv_day` 当前模型指针真源。
- `backend-service/data/slot_governance/pv_day/model_candidates.json` — `pv_day` 候选历史。
- `backend-service/data/slot_governance/pv_point/registry.json` — `pv_point` 当前模型指针真源。
- `backend-service/data/slot_governance/pv_point/model_candidates.json` — `pv_point` 候选历史。

### 7.5 任务 7：事实文档与最终自审

`docs/project/pv_fault/AGENTS.md` — 光伏三路径产品事实总览。它当前仍写“未执行真实 strict-10”，已经过期；不要现在只改这一句，应等任务 3–6 全部完成后一次同步“已验证/未验证、execution ID、数据问题和失败边界”。

最终至少执行：

```powershell
# backend-service/
conda run --no-capture-output -n cp_web python -m py_compile <本轮所有改动 Python 文件>
conda run --no-capture-output -n cp_web python -m pytest -c pytest.ini tests -ra --durations=50

# frontend-sevice/
npx tsc --noEmit --pretty false
npm run build

# 项目根目录
git diff --check
```

还要重读每个修改文件，检查：未使用 import、空/加载/错误/禁用状态、相对路径、路由 404 风险、公共组件副作用、AI marker 配对且不嵌套。

---

## 8. 当前证据索引

| 相对路径 | 接手时应看什么 |
|---|---|
| `output/pv_e2e_validation/tsc_strict10_run.json` | strict-10 总报告：execution、模型、10 次 split、配对基线、治理前后不变。 |
| `backend-service/data/execution_history/by_id/exec-validation-d741dc207593.json` | 平台实际落盘的 execution 证据：节点状态、输入、指标、trigger 与 governance 标记。 |
| `backend-service/data/models/tsc/tsc-multirocket-20260907101950-65eb28f6/evaluation_report.json` | 两个模型逐 seed 的原始评估明细。 |
| `backend-service/data/models/tsc/tsc-multirocket-20260907101950-65eb28f6/metadata.json` | 最终模型的 288×3 window contract、split digest 和生产合同。 |
| `output/pv_e2e_validation/tsc_freeze_profile.json` | 35 个离散日期、来源构成、设备日密度、类别分布与指标结构上限。 |
| `backend-service/data/slot_datasets/pv_tsc/cumulative_labeled_manifest.json` | 两条准入事件：gold bootstrap 与 daily review。 |
| `backend-service/data/slot_datasets/pv_tsc/snapshot_chain.json` | 两版 freeze 版本链和最新数据观察摘要。 |
| `output/pv_e2e_validation/isolated_mysql_setup.json` | 独立测试库已创建、迁移版本和必需表检查；无密钥。 |
| `backend-service/tests/test_accuracy_operations_models.py` | 修复后的精度运营模型契约测试；这是当前唯一生产测试文件修改。 |

---

## 9. 不要做的事

1. 不要直接把全量 pytest 指向 `aip_algo_platform` 业务库。
2. 不要把数据库口令复制到文档、脚本、命令示例、测试报告或 git diff。
3. 不要把 35 个离散已标注日期描述成“原始数据库只有 35 天”。
4. 不要把 `production_contract_valid=true` 描述成“模型精度达标”或“应该 Promote”。
5. 不要拿旧 holdout 0.9538 与新 strict 0.0782 直接做同比。
6. 不要降低 `min_test_samples`、关闭 isolation 或减少 repeats 后冒充 strict-10 通过。
7. 不要自动点击人工“确认正确”制造真值。
8. 不要直接运行会改变真实 candidate、registry、rolling pointer 或游标的 POC 脚本。
9. 不要给历史 TSC Challenger 手工补 provenance，也不要强制 Promote 它。
10. 不要清理、重置、删除或格式化工作区中的无关改动。

---

## 10. 交接完成判据

下一位接手者只有在以下各项都有真实报告后，才能把主任务宣布完成：

- TSC label 完整 DAG 成功，且真实 proposal 目录零污染。
- 浏览器五段故事线有截图和网络/console 错误记录。
- 1,635 项后端测试已在独立 MySQL 运行并有最终统计。
- `pv_day` / `pv_point` train + predict/replay 均真实执行，治理文件哈希不变。
- `docs/project/pv_fault/AGENTS.md` 已按最终事实更新。
- 后端 py_compile、前端 TypeScript/build、AI marker、`git diff --check` 和改动文件重读全部完成。

<!-- @AI_GENERATED: end -->
