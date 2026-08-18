<!-- @AI_GENERATED -->
# Requirements Document

光伏故障诊断双路径生产接入（pv-fault-dual-path-serving）

## Introduction

本 spec 负责把光伏故障诊断**已训练完成的两条检测路径**做成可隔离、可自由切换、可并排对比的**生产接入能力**，并同步前端。

两条路径：

1. **传统按天路径（legacy_day / by-day）**：RandomForest 按天检测，产出天级标签。可增量拉取当天已到达的测点，未到的点在后续轮次自然补上，不做跨日拼接。**注意**：这条路径不产出逐点结果——真正的逐点(288)输出来自下面的全天序列路径，勿混淆。
2. **全天序列路径（seq_annotation / seq-daily）**：BiLSTM + Attention，288 点全天时钟网格。语义是**整天**——必须等一天（近）完整才检测，缺失槽用网格插值 + `is_measured` 掩码通道处理。

### 与 `pv-fault-timeseries-diagnosis` 的边界

已存在的 spec `.kiro/specs/pv-fault-timeseries-diagnosis/` 负责「**怎么训练序列模型**」（滑动窗口切分、TSC 基线选型、模型训练与评估）。**本 spec 不重复它**，只负责这两条**已训练**路径在生产定时任务里：**怎么跑（检测周期语义）、怎么隔离（游标/记录/批次/指针按路径分区）、怎么切换（生产路径指针）、怎么对比（shadow/离线回放）、前端怎么呈现**。凡涉及模型结构、训练超参、数据集构建的诉求，均归属 `pv-fault-timeseries-diagnosis`，本 spec 只消费其产出的模型工件。

本阶段交付物仅为本需求文档。不修改任何生产代码，不预设实现结构。

## Glossary

- **Dual_Path_Scheduler（双路径调度器）**：定时任务入口，读取生产路径指针后把当轮检测分派到对应检测策略。对应现有 `_run_pv_prediction_cycle()`。
- **Legacy_Day_Strategy（传统按天检测策略）**：对应现有 legacy_day 分支的 RandomForest 按天检测策略实现；按天产出天级标签，可增量拉取当天已到达的测点。区别于序列路径的逐点(288)输出。
- **Seq_Daily_Strategy（全天序列检测策略）**：处理整天序列检测的策略实现。对应现有 `_run_seq_annotation_prediction_cycle()`。
- **modeling_path（建模/检测路径标识）**：取值 `legacy_day` 或 `seq_annotation`，决定分派到哪条策略。
- **Production_Path_Pointer（生产路径指针）**：记录当前生产建模路径的单指针，由 modeling-paths 登记提供。切换 = 改此指针。
- **Device_Cursor（设备预测游标）**：`device_prediction_cursor` 表，字段 `last_predicted_time` 记录某设备三元组已检测到的**业务时间**水位。
- **Event_Time（事件时间/业务时间）**：数据点自身携带的观测时刻（mock 回放场景为 2020/2021 等历史时间）。
- **Processing_Time（处理时间/墙钟时间）**：任务实际运行的 `datetime.utcnow()` 时刻。
- **Completeness_Gate（完整性闸门）**：基于 `measurement_ingestion_daily` 表的设备-天完整性判定（`point_count / expected_point_count ≥ 阈值`）。
- **Path_Isolation_Registry（路径隔离登记）**：按路径维度隔离游标、预测记录、审核批次、模型指针的约定真源。
- **Shadow_Compare_Runner（并排对比器）**：让两条路径对同一批设备日各跑一次并比对的能力，只记录不影响生产事实。
- **Mock_Arrival_Feeder（Mock 到达模拟器）**：`PvFaultMockFeeder`，模拟设备异步到达并写入 `training_samples`。
- **Immutable_Batch_Recovery（不可变批次恢复）**：seq 路径失败重试时从首次落盘批次恢复，不用新推理覆盖旧审核事实的机制。
- **Console（前端控制台）**：调度/部署运维前端页面，含到达看板、调度状态、路径切换与对比展示。
- **Data_Watermark（数据到达水位）**：某设备已入库数据点的最大 Event_Time 所在自然日；用作"数据今天"的判定基准，使历史回放与实时生产统一按数据推进而非墙钟。
- **Accuracy_Gated_Retrainer（精度守门重训器）**：累计确认标注变动达阈值且到周期后自动重训出挑战者模型，按精度门控决定是否晋升为该 `modeling_path` 的生产模型；对应现有 CumulativeTrainingService 的重训/登记/晋升链路的演进。
- **Shared_Label_Pool（共享标签池）**：唯一的累计标签真相——逐点标签为细粒度真相、天级标签为其聚合投影；两条路径共用同一份、不各存一份。对应现有 CumulativeTrainingService 累计状态（verdict_entries 天级 + point_label_ops 逐点）。
- **Retrain_Consumption_Watermark（重训消费水位）**：某 modeling_path 在 Shared_Label_Pool 上「已用于上次重训的位置」；用于按路径独立统计 change_units 与触发重训，类比检测侧 Device_Cursor 的按路径水位。
- **Backfill_Loop（打标闭环回流）**：检测 → 人工审核裁决 → 回流进 Shared_Label_Pool 的链路。对应现有 submit_verdict / BackfillService / CumulativeTrainingService。
- **Device_Day（设备日）**：一个 `(site_id, device_id, branch_id, business_date)` 组合，即「某设备三元组的某一个自然日」，是序列路径检测与落账的最小独立单位。
- **Seq_Device_Day_Ledger（序列设备日记账）**：以 `(slot, modeling_path, site_id, device_id, branch_id, business_date)` 为键的逐设备日处理台账，是「序列路径是否已处理某个独立自然日」的**唯一权威真相**，取代单一时间游标承担该判定。
- **`input_fingerprint`（输入数据指纹）**：某设备日参与检测的输入数据集合的稳定摘要值，用于判定该设备日输入是否在成功检测后发生过变化。
- **`revision_pending`（待修订状态）**：Seq_Device_Day_Ledger 的一种状态，表示该设备日此前已成功，但输入数据指纹已变化，需要新建修订批次重新检测。
- **`supersedes_batch_id`（被取代批次标识）**：修订批次中记录的、被本次修订取代的前一个批次标识；首次审核批次本身保持不可变。
- **Continuous_Completion_Frontier（连续完成前沿）**：某设备在 Seq_Device_Day_Ledger 上从最早责任日起连续 `succeeded` 的最后一个 `business_date`，是**看板与查询优化用的摘要值**，不承担权威判定。
- **Path_Activation_Epoch（路径启用周期）**：某条 `modeling_path` 一次「启用/重新启用」所建立的生产责任边界记录，决定该路径本次只对哪些 `business_date` 承担生产检测责任。
- **`activation_mode`（启用模式）**：Path_Activation_Epoch 的回看策略，取值 `cutover_only`（仅从各设备最近一个已结束设备日开始）、`recent_window`（按 `backfill_days` 有限回看）、`full_backfill`（全量历史回放，仅人工显式选择）。
- **`effective_from_date`（生产责任起始日）**：本次 Path_Activation_Epoch 下该路径承担生产检测责任的最早 `business_date`；早于该日的设备日不属于本次生产责任范围。
- **`activation_watermark`（启用时设备水位）**：建立 Path_Activation_Epoch 时该设备已到达数据的水位，用于按设备各自推算 `effective_from_date`。
- **Backfill_Runner（限流历史回放执行器）**：承载 `full_backfill` 的独立执行通道，独立限流、不占用生产检测容量、不推进生产责任进度。
- **Champion（冠军模型）**：某条 `modeling_path` 内当前用于该路径生产检测的模型。
- **Challenger（挑战者模型）**：某条 `modeling_path` 内本次重训产出、尚未成为该路径 Champion 的候选模型。
- **Path_Internal_Promotion（路径内换将）**：在同一 `modeling_path` 内用 Challenger 替换 Champion 的动作；**不改变 Production_Path_Pointer**。
- **Cross_Path_Switch（跨路径换班组）**：把 Production_Path_Pointer 从一条 `modeling_path` 改为另一条的动作；需两条路径各自已有合格 Champion 并具备跨路径证据。
- **Cross_Path_Shadow_Report（跨路径影子对比报告）**：两条路径的当前 Champion 在同一批完整历史设备日上只读对跑产出的证据报告，只产证据、不改生产路径。
- **Promotion_Event（模型晋升事件）**：记录一次 Path_Internal_Promotion 的审计事件。
- **Path_Switch_Event（路径切换事件）**：记录一次 Cross_Path_Switch 的审计事件；与 Promotion_Event 分开记录，互不冒充。
- **PV_Model_Registry（光伏模型登记）**：`pv_fault` 槽位下模型身份与生产路径的**唯一可写真相**，对应现有 `backend-service/services/iterative_labeling/cumulative_training.py` 的 modeling-paths 状态。
- **Deployment_Arena（通用部署演习场）**：通用部署槽位与切换审计能力，对应现有 `backend-service/services/deployment/store.py`；对 `pv_fault` 只做只读展示适配。
- **Accuracy_Operations_Arbitrator（通用精度运营换将仲裁器）**：通用影子换将建议器，对应现有 `backend-service/services/accuracy_operations/arbitrator.py`；不是本 spec 双层门控的实现载体。

## 现状分析（Current State Analysis）

以下为已读代码确认的事实，需求基于这些事实：

### 分派与切换

- **路由**：`backend-service/services/scheduler/tasks/pv_fault_tasks.py` 的 `_run_pv_prediction_cycle()` 读 `_production_modeling_path()`（来自 modeling-paths 指针）分派：`seq_annotation` 走 `_run_seq_annotation_prediction_cycle()`，否则走 legacy_day 点粒度分支。**切换 = 改生产路径指针，已是单指针切换**。

### 传统按天路径现状（核心缺陷所在）

- 按 `device_prediction_cursor.last_predicted_time`（业务时间）查 `(last_time, cutoff]` 的点。
- 但 `cutoff = datetime.utcnow()`（**墙钟时间**），且把游标推进到 `cutoff = 墙钟 now`。
- **缺陷**：对「历史回放 mock（业务时间是 2020/2021）」，第 2 个 tick 后游标已到墙钟 now，后续 mock 数据（业务时间 < 墙钟 now）会被 `(last_time, cutoff]` 永久漏在窗口外。**legacy 只适配实时生产，不适配历史回放。这是本 spec 必须修复的核心缺陷。**

### 全天序列路径现状

- 只处理 `_date < cutoff.date()` 的整天；对每个候选天用 `PVFaultRepository.query_device_measurements` 重新拉「整天全量」→ `SeqAnnotationPredictor.predict_device_day(include_night=True)`。
- 游标推进到该天业务时间的 max；晚到 / 集合增减由 **不可变批次恢复机制** 处理；未读 `is_complete`，靠「昨天 + predictor 占用率/间隔门控」。

### Predictor 约束

- `backend-service/services/iterative_labeling/seq_annotation/predictor.py` 的 `predict_device_day` **显式拒绝多天输入**（`df['time'].dt.normalize().nunique() != 1` → 空结果，报「禁止把多天数据覆盖到同一时钟网格」）。
- `grid_aligned` 按 288 时钟槽对齐，缺失槽 = 插值 + `is_measured=0` 掩码通道；占用率 / 白天最长空槽 / 24h 覆盖门控不达标则整天拒绝。
- **结论**：seq 路径「截断当天 + 把未到点并入次日」在代码层面被直接拒绝，且违背时钟槽语义，会破坏序列形态与精度；传统按天路径可增量。

### 喂数据与到达模拟

- `backend-service/services/db/datasources/pv_fault_mock.py`（`PvFaultMockFeeder`）做**设备级错峰**（整台设备整天一次性释放，约 5% 延迟、约 1% 当天缺失），写 `training_samples(label=NULL, data_source='mock')`；`release_next_batch_tick()` 由 cron 调。
- `IngestionTrackerRepository.record_arrival()` 更新 `measurement_ingestion_daily` 完整性（阈值比例 0.9、expected=288）。**当前是设备级错峰，非点级错峰**。

### 游标仓储与看板

- `backend-service/services/db/repositories/ingestion_tracker.py` 的 `advance_cursor` 用 `last_predicted_time`（业务时间语义）；`query_pending_predictable` 用 `is_complete` + 游标 date 比较，**但仅供看板/人工列表，不是自动闸门**。
- 已实现的看板：站点到达百分比、设备下钻明细、pending-predictable（前端 `PvIngestionSiteOverview.tsx`、`PvDeviceIngestionDetail.tsx`、`SchedulerTab.tsx`、`deploymentApi.ts`）。

### 模型晋升与路径切换现状（已核实，2026 本轮补充）

以下为逐文件读码核实的事实，是 Requirement 15「双层冠军—挑战者」的现状基线：

- `backend-service/services/deployment/store.py` — 通用部署演习场的持久化层：维护 `slots.json` 中每槽位的 `production_model`（生产模型）/ `shadow_models`（影子模型列表，按 `accuracy_score` 降序）/ `prelaunch_models`（预上线模型），并以 `switch_log.json` 作为只追加的切换事件日志（`SwitchEventLog.append()` 是唯一写入入口）。它主要服务**工作流型部署**，槽位模型真相存在自己的 `slots.json` 里。
- `backend-service/services/accuracy_operations/arbitrator.py` — 通用精度运营换将仲裁器：`CONF_GATE = 0.6` 为 RCA 置信度门槛，低于该值或根因未确定即产出 `observe`（观察）；候选影子需满足多窗口优势与最小样本门槛；比较指标 `_comparison_metric()` 优先 `rolling_wmape`、缺失回退 `rolling_mape`；产出 `shadow_switch`（影子换将建议）或 `observe`，且 `execute_switch()` 只接受已批准的 `shadow_switch` 决策后再交部署切换引擎执行（即需人工二次确认）。
- `backend-service/services/iterative_labeling/cumulative_training.py` — 光伏双路径的模型与路径登记：状态里维护 `production_path`（生产路径）/ `fallback_path`（备选路径）/ `path_models`（各路径模型登记）/ `path_switch_audit`（切换与登记审计，只追加、查询取最近 10 条）。**调度器读的是这一套**（`_production_modeling_path()`），与上面的通用演习场 `slots.json` 未打通。
- `backend-service/services/scheduler/pv_dual_path/shadow_compare.py` — 本 spec 设计中的跨路径 Shadow 对比器，**当前尚不存在**（已确认文件缺失），即跨路径 Shadow 能力尚未实现。
- `PUT /cumulative-training/modeling-paths`（实现于 `backend-service/api/iterative_labeling.py`，写入经 `set_modeling_paths()`）— 现有准入只要求：目标路径在 `path_models` 中有非空 `model_ref`，且 `seq_annotation` 通过 `_assert_seq_production_ready()` 全天契约校验。**不要求任何跨路径 Shadow 证据**即可直接改 `production_path`。
- `backend-service/api/iterative_labeling.py` 重训完成回调 — `promote_to_production = _modeling_path != "seq_annotation"`，即 **legacy_day 重训完成后直接自动晋升为生产模型**（无精度门控）；`seq_annotation` 只登记实验模型。
- `path_models[modeling_path]` 每路径**只存一份最新登记**（`model_ref` / `request_id` / `updated_at` 等），**没有** Champion / Challenger / 已退役历史的完整生命周期结构，因此无法表达「路径内换将」与「可回滚历史冠军」。

### 遗留未完成

- 方案 C「训练数据 vs 预测输入**物理分表**」未落地（当前 mock 与训练数据同表 `training_samples`，靠 `data_source` 逻辑隔离）。
- **点级错峰未做**；`is_complete` 未成自动闸门；真实生产采集入口未接（仅预留 `data_source='production'`）。
- `PUT /cumulative-training/modeling-paths`、`register-model`、`switch-fallback` 三个写接口仍**无鉴权**（P0 未授权风险，本文列为上线阻断项，实施需用户显式授权）。

## 调研结论（Research Summary，含来源）

以下为工业界/竞品做法的调研，**内容为合规改写，非逐字引用**，作为本 spec 的设计依据。

### 1. Champion-Challenger / Shadow 模式

冠军模型对外提供生产服务，挑战者模型接收同样输入但输出只记录、不生效，且必须隔离副作用（不写生产表、不推进生产游标）。这直接支撑本 spec「shadow 对比只记录不影响生产事实」的选型。内容为合规改写。

- [metricgate：champion-challenger 模型测试](https://metricgate.com/blogs/champion-challenger-model-testing/)
- [mljar：shadow mode 监控](https://www.mljar.com/ai-prompts/mlops/model-monitoring/prompt-shadow-mode/)
- [portainer：shadow deployment 六步](https://www.portainer.io/blog/shadow-deployment)

### 2. Split-horizon（流批分工）

流式车道负责「当下 / 近期」，批处理车道负责「完整历史」，两条车道服务不同消费者、覆盖不同时间跨度，协作但绝不竞争产出同一结果。这正映射本 spec「传统按天路径 = 当下增量、整天序列路径 = 完整历史」的分工。内容为合规改写。

- [RisingWave：流批对账](https://risingwave.com/blog/risingwave-streaming-batch-reconciliation/)

### 3. Event-time vs Processing-time + 水位线 + 宽限期

应按**事件发生时间（业务时间）**而非到达/处理时间推进进度，用水位线（watermark）+ 宽限期（allowed lateness）处理晚到数据、可更新已发结果，代价是正确性 vs 延迟 vs 资源的权衡。这正是传统按天路径**墙钟游标缺陷**的对照——应改为事件时间/到达顺序游标。内容为合规改写。

- [Apache Flink：timely stream processing](https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/time/)
- [Conduktor：处理晚到数据](https://www.conduktor.io/glossary/handling-late-arriving-data-in-streaming)
- [streamkap：流式晚到数据](https://streamkap.com/resources-and-guides/late-arriving-data-streaming/)

## Requirements

### Requirement 1: 双路径检测策略抽象与分派

**User Story:** 作为平台维护者，我希望定时任务按建模路径分派到对应的检测策略，以便两条路径各自的「每日拉到的数据怎么算」有明确、可验收、互不干扰的规则。

#### Acceptance Criteria

1. WHEN 检测定时任务被触发，THE Dual_Path_Scheduler SHALL 读取 Production_Path_Pointer 并在 5 秒内取得当前 `modeling_path` 取值（`legacy_day` 或 `seq_annotation`）。
2. WHERE `modeling_path` 为 `seq_annotation`，THE Dual_Path_Scheduler SHALL 把当轮检测分派给 Seq_Daily_Strategy，且不触发 Legacy_Day_Strategy。
3. WHERE `modeling_path` 为 `legacy_day`，THE Dual_Path_Scheduler SHALL 把当轮检测分派给 Legacy_Day_Strategy，且不触发 Seq_Daily_Strategy。
4. IF Production_Path_Pointer 在 5 秒内读取失败，或取值不在 `{legacy_day, seq_annotation}` 集合内，THEN THE Dual_Path_Scheduler SHALL 跳过本轮检测、不分派给任一策略，并以 `status=skipped`、`reason=invalid_modeling_path` 记录运行状态。
5. WHEN 完成分派，THE Dual_Path_Scheduler SHALL 在本轮运行状态中记录实际分派到的 `modeling_path` 取值与目标策略名称，供审计查询与前端展示。
6. WHEN Legacy_Day_Strategy 被分派执行，THE Legacy_Day_Strategy SHALL 输出本轮数据的时间边界（起始时间戳与结束时间戳），以及本轮参与检测的数据条数与顺延到下一轮的数据条数，且三项均为可断言的确定值。
7. WHEN Seq_Daily_Strategy 被分派执行，THE Seq_Daily_Strategy SHALL 输出本轮数据的时间边界（起始时间戳与结束时间戳），以及本轮参与检测的数据条数与顺延到下一轮的数据条数，且三项均为可断言的确定值。
8. THE Dual_Path_Scheduler SHALL 使 Legacy_Day_Strategy 与 Seq_Daily_Strategy 共用 `Data_Watermark` — 公共数据到达水位作为时间进度基准（两条策略均按数据到达推进，不使用 Processing_Time/墙钟）；两条策略的检测窗口粒度差异——传统按天路径可检测至数据水位当天的已到达增量、序列路径仅检测数据水位之前的完整整天——为按模型能力有意为之，不属于需要消除的不一致。
9. THE Data_Watermark SHALL 按设备三元组统一计算并由两条路径只读共用，不按 `modeling_path` — 建模/检测路径复制第二份水位；路径隔离发生在消费游标而非公共数据到达事实。

### Requirement 2: 传统按天路径语义（修复墙钟漏诊）

**User Story:** 作为算法工程师，我希望传统按天路径按事件时间/到达顺序推进游标，以便历史回放 mock 与实时生产都不漏检当天已到达的点。

#### Acceptance Criteria

1. THE Legacy_Day_Strategy SHALL 以数据点的 Event_Time 而非 Processing_Time 作为游标推进与窗口纳入的唯一判定依据。
2. WHEN Legacy_Day_Strategy 完成一轮检测，THE Legacy_Day_Strategy SHALL 将设备游标推进到「本轮实际参与检测的数据点集合中的最大 Event_Time」，其中「本轮实际参与检测的数据点」定义为本轮被纳入检测窗口且完成检测的数据点，且推进后游标值严格不小于推进前游标值。
3. WHILE 存在 Event_Time 严格大于设备当前游标水位的已到达数据点（「已到达」指该点在本轮检测启动时刻之前其 Event_Time 与取值均可读），THE Legacy_Day_Strategy SHALL 在后续轮次将这些点纳入检测窗口。
4. THE Legacy_Day_Strategy SHALL 按设备三元组 `(site_id, device_id, branch_id)` 独立维护游标水位，任一三元组的游标推进不得改变其他三元组的游标水位。
5. WHEN 数据点在其 Event_Time 所属自然日（自然日以 Event_Time 的日期部分划分）当天已到达，THE Legacy_Day_Strategy SHALL 在该点到达后的下一个检测轮次内将其纳入检测，且不得将 Event_Time 尚未到达的数据点纳入检测窗口，也不得跨越其 Event_Time 所属自然日边界与相邻自然日的数据点拼接为同一检测窗口。
6. IF 某设备在本轮不存在 Event_Time 严格大于其游标水位的新数据点，THEN THE Legacy_Day_Strategy SHALL 跳过该设备的本轮检测，并保持其游标水位不变。
7. WHEN 晚到数据点的 Event_Time 落在设备当前游标水位之后（即 Event_Time 严格大于游标水位），THE Legacy_Day_Strategy SHALL 在该点到达后的下一个检测轮次将其自动纳入检测窗口，且不依赖任何人工干预。
8. IF 某数据点的 Event_Time 缺失或无法解析为有效时间值，THEN THE Legacy_Day_Strategy SHALL 拒绝将该点纳入检测窗口、保持相关设备游标水位不变，并输出指示该点因 Event_Time 无效而被跳过的错误标识。
9. THE Legacy_Day_Strategy SHALL 以已到达数据（即 Data_Watermark 所界定的、已入库且 Event_Time 可读的数据）作为检测窗口的上限，不使用 Processing_Time/墙钟时间作为窗口上限。

### Requirement 3: 全天序列路径语义（只检测完整历史整天）

**User Story:** 作为算法工程师，我希望序列路径只对（近）完整的历史整天做检测，以便保持 288 点时钟网格的序列形态不被破坏。

#### Acceptance Criteria

1. THE Seq_Daily_Strategy SHALL 以 Data_Watermark 作为"数据今天"的判定基准，仅检测 Event_Time 自然日严格早于该设备 Data_Watermark 所在自然日的整天数据；该基准在历史回放与实时生产下口径一致，不使用墙钟时间。
2. WHILE 某设备日的自然日等于该设备当前 Data_Watermark 所在自然日（该设备当天可能仍在接收数据），THE Seq_Daily_Strategy SHALL 不检测该设备当天数据，并将其保留至后续轮次重新评估。
3. WHILE 某设备日的时钟网格占用率低于完整性阈值（占用率 = 已测量槽数 / 288，阈值为 90%），THE Seq_Daily_Strategy SHALL 不检测该设备当天数据，并将其保留至后续轮次重新评估。
4. WHEN 某设备日被判定为可检测整天，THE Seq_Daily_Strategy SHALL 将该设备日数据对齐到覆盖 24 小时、槽间隔 5 分钟的 288 点时钟网格，对缺失槽以插值填充，并在 `is_measured` 掩码通道将对应槽标记为 0，对实测槽标记为 1。
5. IF 单批输入包含跨越两个及以上自然日的数据点，THEN THE Seq_Daily_Strategy SHALL 拒绝将其覆盖到同一 288 点时钟网格，仅按自然日分组分别对齐，并以可诊断原因（指明跨日冲突）记录被拒记录。
6. IF 某设备日的时钟网格占用率低于 90%、或白天时段（06:00 至 18:00）最长连续空槽超过 12 个槽（60 分钟）、或 24 小时覆盖门控（要求每个 6 小时时段至少存在 1 个实测槽）不达标，THEN THE Seq_Daily_Strategy SHALL 拒绝该设备日、以可诊断原因（指明未通过的具体门控项及其实测值）记录，并不产出该设备日预测。
7. WHEN 已检测整天在后续轮次出现 Event_Time 属于该整天的晚到数据点，THE Seq_Daily_Strategy SHALL 通过 Immutable_Batch_Recovery 对该整天触发复检，生成新的复检批次，并保留首次批次的审核事实不被覆盖。
8. THE Seq_Daily_Strategy SHALL 在验收文档中记录「不截断当天 + 不把未到点并入次日」的理由，说明截断与跨日并入会改变时钟槽位置语义、使序列形态失真并降低精度，且该行为被 predictor 在代码层直接拒绝。
9. THE Seq_Daily_Strategy SHALL 以 Seq_Device_Day_Ledger 作为「某个 Device_Day 是否已被本路径处理」的唯一权威判定依据，并 SHALL 不把 `Device_Cursor` 单一时间游标作为排除候选 Device_Day 的唯一条件。（本条**修订**上一版「连续成功前沿、首个失败日阻塞更晚日期」的表述，修订理由见「本轮修订记录」条目 R1，详细语义见 Requirement 13。）
10. IF 某设备没有下一自然日的已到达数据，THEN 其 `Data_Watermark` SHALL 保持在当前最大 Event_Time 所在自然日、不因 Processing_Time/墙钟跨日；THE Seq_Daily_Strategy SHALL 不使用墙钟把该日隐式封日。永久离线设备如需处理，必须由未来显式封日信号另行设计，未有该信号时保持该日顺延。
11. WHEN 某设备存在一个较早的、未通过 Completeness_Gate 的候选 Device_Day，同时存在一个较晚的、已通过 Completeness_Gate 的候选 Device_Day，THE Seq_Daily_Strategy SHALL 把较早 Device_Day 在 Seq_Device_Day_Ledger 中置为 `waiting_data`，并独立处理较晚 Device_Day 直至其 ledger 状态为 `succeeded` 或 `failed`，且不因较早 Device_Day 未完整而跳过、延后或阻塞较晚 Device_Day。
12. THE Seq_Daily_Strategy SHALL 为每一个被处理的 Device_Day 独立构造一个覆盖 24 小时、槽间隔 5 分钟的 288 点时钟网格、独立执行一次预测、独立写入一个审核批次；WHILE 单轮内处理两个及以上 Device_Day，THE Seq_Daily_Strategy SHALL 不把属于不同 `business_date` 的数据点合并为同一个模型输入。
13. THE Seq_Daily_Strategy SHALL 把 `Device_Cursor` 在 `seq_annotation` 分区的取值定义为 Continuous_Completion_Frontier（连续完成前沿）摘要，仅用于看板展示与候选查询范围收窄；THE Seq_Daily_Strategy SHALL 在该摘要与 Seq_Device_Day_Ledger 判定冲突时以 Seq_Device_Day_Ledger 为准。

### Requirement 4: 完整性表作为路径相关的显式闸门

**User Story:** 作为平台维护者，我希望完整性表成为路径相关的显式检测闸门，以便序列路径严格等待完整数据、传统按天路径宽松放行，且阈值可配置。

#### Acceptance Criteria

1. THE Completeness_Gate SHALL 基于 `measurement_ingestion_daily` 的比例 `point_count / expected_point_count` 判定设备-天是否达到完整性阈值，当该比例大于或等于完整性阈值比例时判定为达标，否则判定为未达标。
2. THE Completeness_Gate SHALL 暴露可配置的完整性阈值比例，取值范围为 0.0 至 1.0（含端点），默认值为 0.9；WHEN 配置的阈值比例超出该范围，THE Completeness_Gate SHALL 拒绝该配置并回退至默认值 0.9。
3. WHERE 当前路径为 `seq_annotation`，THE Seq_Daily_Strategy SHALL 仅在设备-天通过 Completeness_Gate（比例达标）后检测该设备日，对未达标的设备-天不触发检测。
4. WHERE 当前路径为 `legacy_day`，THE Legacy_Day_Strategy SHALL 不以 Completeness_Gate 为放行前置条件，允许对未完整当天的已到达点（`point_count` 小于 `expected_point_count` 的设备-天中已入库的测点）执行增量检测。
5. THE Completeness_Gate SHALL 允许通过配置调整 `expected_point_count`，取值范围为 1 至 288（含端点），默认值为 288；WHEN 配置的 `expected_point_count` 小于或等于 0，THE Completeness_Gate SHALL 拒绝该配置并回退至默认值 288。
6. WHEN 设备-天的 `point_count` 首次达到完整性阈值，THE Completeness_Gate SHALL 将该设备-天标记为 `is_complete=true` 并以 UTC 记录完成时刻，且对同一设备-天的后续达标事件不重复更新完成时刻。
7. IF 某设备-天在 `measurement_ingestion_daily` 中缺失 `point_count` 或 `expected_point_count`，THEN THE Completeness_Gate SHALL 将该设备-天判定为未达标（`is_complete=false`）并返回指示数据缺失的错误标识，同时保留该设备-天的现有记录不被修改。
8. THE Completeness_Gate SHALL 把设备-天完整性作为两条路径共享的到达事实，不按 `modeling_path` 复制：`seq_annotation` 严格要求达标，`legacy_day` 宽松放行已到达增量；WHEN 任一路径因其门控语义跳过设备-天，THEN 不得推进该路径对应的 Device_Cursor，且不得改变另一条路径的游标。

### Requirement 5: 两条路径的隔离

**User Story:** 作为平台维护者，我希望游标、预测记录、审核批次与模型指针都能按路径维度隔离，以便一条路径的运行永不覆盖另一条路径的事实。

#### Acceptance Criteria

1. THE Path_Isolation_Registry SHALL 以 `slot` 与 `modeling_path` 的组合作为唯一分区键存储 Device_Cursor，且 `modeling_path` 取值限定为系统当前登记的路径之一；不同分区键的 Device_Cursor 写入互不覆盖。
2. THE Path_Isolation_Registry SHALL 为每条预测记录与每个审核批次附加且仅附加一个非空 `modeling_path` 标记，使消费方可据该标记唯一确定记录所属路径。
3. THE Production_Path_Pointer SHALL 独立于模型工件指针存储；WHEN 切换检测路径时，THE Path_Isolation_Registry SHALL 保持各路径的模型工件指针登记不变。
4. THE Path_Isolation_Registry SHALL 在文档中对每类登记说明以下四项：存储内容、单独存储的原因、分区维度（`slot` 槽位 / `modeling_path` 路径）、以及存储路径与介质由部署配置决定。
5. WHEN 一条路径推进其 Device_Cursor 或写入其预测记录、审核批次，THE Path_Isolation_Registry SHALL 保持其他所有 `modeling_path` 分区的 Device_Cursor、预测记录与审核批次在数值与数量上不变。
6. IF 某路径在对应 `slot` 与 `modeling_path` 分区下缺少 Device_Cursor 记录，THEN THE Path_Isolation_Registry SHALL 将该路径游标视为固定初始水位（不指向任何已消费位置），且不读取或复用其他 `modeling_path` 分区的游标值；THE Path_Isolation_Registry SHALL 把该固定初始水位取为该路径当前 Path_Activation_Epoch 中该设备 `effective_from_date` 的起始时刻（见 Requirement 14），且 SHALL 不把该固定初始水位取为该设备最早历史数据所在自然日的起始时刻。（本条**修订**决策 Q2 的实现语义，理由见「本轮修订记录」条目 R2。）
7. IF 对某 `modeling_path` 分区的写入操作失败，THEN THE Path_Isolation_Registry SHALL 保持其他 `modeling_path` 分区不变、不产生部分写入，并向调用方返回指示该分区写入失败的错误。
8. THE Path_Isolation_Registry SHALL 使 `Device_Cursor` — 检测消费水位按设备三元组与 `modeling_path` 分区独立维护；WHEN Production_Path_Pointer 切换路径，THEN 不得复制、对齐或覆盖两条路径的游标，新路径必须从自身分区已有游标恢复，若不存在则按固定初始水位开始。
9. WHEN Production_Path_Pointer 切换到某路径，THE Path_Isolation_Registry SHALL 不把另一条 `modeling_path` 分区的历史检测记录、审核批次或设备日处理状态写入或标记为本路径已处理，理由是两条路径的模型、输入形态与输出粒度均不同，跨路径挪用会使并排对比与审计失真。

### Requirement 6: 自由切换生产路径

**User Story:** 作为平台运维，我希望通过单个生产路径指针自由切换两条路径，以便切换过程语义清晰且可审计。

#### Acceptance Criteria

1. WHEN 运维通过写接口提交合法的新生产路径，THE Production_Path_Pointer SHALL 将指定 `slot` 的当前值覆盖登记为提交的 `modeling_path`，并将该写入结果作为后续查询与分派的唯一生效值。
2. THE Production_Path_Pointer 写接口 SHALL 接受 `modeling_path`（必填，取值仅限 `legacy_day` 或 `seq_annotation`）、`slot`（可选字符串，长度 1 至 64 字符，缺省时取 `default`）与 `note`（可选字符串，长度 0 至 500 字符）。
3. WHEN 生产路径被成功切换，THE Path_Isolation_Registry SHALL 向只追加审计日志追加一条记录，包含 `modeling_path`、`slot`、`updated_at`（切换完成的时间戳）与操作备注，且既有审计记录不被修改或删除。
4. IF 写接口提交的 `modeling_path` 不在 `legacy_day` 或 `seq_annotation` 取值范围内，THEN THE Production_Path_Pointer SHALL 拒绝写入、保持该 `slot` 原有值不变，并返回指明"非法 `modeling_path` 取值"的可诊断错误。
5. IF 写接口提交的 `slot` 或 `note` 超出第 2 条规定的长度范围，THEN THE Production_Path_Pointer SHALL 拒绝写入、保持该 `slot` 原有值不变，并返回指明超长字段的可诊断错误。
6. WHEN 生产路径切换完成，THE Dual_Path_Scheduler SHALL 在紧邻的下一轮检测中按新指针分派，无需重启服务，且切换前已在执行的检测轮次仍按切换前指针完成。
7. THE Production_Path_Pointer SHALL 提供只读查询接口，返回当前各 `slot` 的 `modeling_path`、`updated_at` 与 `note`。
8. WHERE 写请求提交的 `modeling_path` 与该 `slot` 当前值不同（即该请求构成一次 Cross_Path_Switch），THE Production_Path_Pointer 写接口 SHALL 额外要求 `activation_mode`（必填，取值仅限 `cutover_only`、`recent_window`、`full_backfill`）与 `backfill_days`（当 `activation_mode` 为 `recent_window` 时必填，整数，取值范围 1 至 `max_backfill_days`）；WHERE 写请求提交的 `modeling_path` 与该 `slot` 当前值相同，THE Production_Path_Pointer 写接口 SHALL 不要求 `activation_mode` 与 `backfill_days`，且 SHALL 不建立新的 Path_Activation_Epoch。
9. IF Cross_Path_Switch 准入门控（见 Requirement 14 第 6 条列出的全部条件）中存在任一条未满足，THEN THE Production_Path_Pointer SHALL 拒绝写入、保持该 `slot` 的 `modeling_path` 原有值不变，并返回逐项列出未满足条件名称的可诊断错误。
10. WHEN Cross_Path_Switch 写入成功，THE Path_Isolation_Registry SHALL 建立一个新的 Path_Activation_Epoch（见 Requirement 14）并追加一条 Path_Switch_Event（见 Requirement 15），且 SHALL 不追加 Promotion_Event。
11. THE Production_Path_Pointer SHALL 不因 Path_Internal_Promotion（路径内换将）而改变 `modeling_path` 取值。

### Requirement 7: 两条路径的并排对比

**User Story:** 作为算法负责人，我希望对同一批设备日让两条路径各跑一次并比对，以便在不污染生产事实的前提下评估两条路径的差异。

#### Acceptance Criteria

1. WHEN 接收到指定的同一批设备日输入，THE Shadow_Compare_Runner SHALL 对该批中的每一个设备日分别用 Legacy_Day_Strategy 与 Seq_Daily_Strategy 各产出且仅产出一次检测结果。
2. THE Shadow_Compare_Runner SHALL 以离线回放或 shadow 方式运行，且不推进生产的 Device_Cursor。
3. THE Shadow_Compare_Runner SHALL 不写入生产的预测记录与生产审核批次。
4. THE Shadow_Compare_Runner SHALL 产出可对比指标，至少包含：两条路径逐设备日的预测标签一致率（定义为标签相同的设备日数除以两条路径均成功产出结果的设备日总数，取值范围 0% 至 100%）与差异清单（逐条列出标签不一致的设备日及双方标签）。
5. IF 两条路径对同一设备日均成功产出结果且标签不同，THEN THE Shadow_Compare_Runner SHALL 在对比结果中将该设备日标记为差异项并保留双方标签。
6. IF 某一条路径对某设备日未能产出结果，THEN THE Shadow_Compare_Runner SHALL 将该设备日标记为不可对比项、保留另一条路径已产出的结果、继续处理该批中其余设备日，并在对比结果中给出指示该路径产出失败的原因说明。
7. THE Shadow_Compare_Runner SHALL 将对比结果与生产不可变事实分开存储，且对比结果的存储路径由部署配置决定。
8. THE Shadow_Compare_Runner SHALL 仅在两条路径均可产出结果的同一批完整历史设备日（即 Event_Time 自然日早于 Data_Watermark 所在自然日、且分别通过各自可检测判定的设备日）上进行对比，不将任一路径当前尚无法产出结果的当天设备日纳入对比。
9. THE Shadow_Compare_Runner SHALL 仅使用两条路径各自当前的 Champion 模型参与 Cross_Path_Shadow_Report 的生成；IF 任一路径当前无合格 Champion 或其模型工件不可加载，THEN THE Shadow_Compare_Runner SHALL 拒绝生成该报告并返回指明缺失路径与缺失原因的可诊断错误。
10. THE Cross_Path_Shadow_Report SHALL 至少包含以下字段：`comparison_id`（比对任务标识）、`legacy_model_ref`（参与对比的 legacy_day 冠军模型引用）、`seq_model_ref`（参与对比的 seq_annotation 冠军模型引用）、`device_day_total`（纳入对比的设备日总数）、`comparable_total`（两路均成功产出的设备日数）、`agreement_rate`（天级一致率）、`diff_items`（标签不一致设备日清单）、`uncomparable_items`（不可对比设备日清单，每条含失败路径、原因与 `severity`，`severity` 取值仅限 `blocking` 或 `deferred`）、`legacy_metrics`（legacy_day 指标集合）、`seq_metrics`（seq_annotation 指标集合）、`coverage_rate`（覆盖率，已产出结果设备日数除以应产出设备日数）、`deferred_rate`（门禁顺延比例，因门控顺延的设备日数除以候选设备日总数）、`generated_at`（报告生成时刻，UTC）。
11. THE Cross_Path_Shadow_Report SHALL 在共同口径证据层，把 `seq_annotation` 的逐点结果按明确记录的投影规则聚合为天级结果后，与 `legacy_day` 的天级结果比较天级准确率、故障召回率、误报率、天级一致率与覆盖率；THE Cross_Path_Shadow_Report SHALL 在报告内记录所用投影规则的标识与定义。
12. THE Cross_Path_Shadow_Report SHALL 在 Seq 原生增益证据层记录 `seq_annotation` 的逐点 F1、故障段 IoU、故障段边界偏差、夜间误报数与 288 点契约通过结果；IF 某项 Seq 原生指标在 `legacy_day` 上无对应可计算值，THEN THE Cross_Path_Shadow_Report SHALL 把该项标记为「无 Legacy 对应值」，且 SHALL 不在报告中给出该项的跨路径横向比较结论。
13. THE Cross_Path_Shadow_Report SHALL 在生产运行指标证据层记录两条路径各自的单轮检测延迟、门禁顺延比例、推理失败率、每日可处理设备日容量与模型工件加载成功率。
14. THE Shadow_Compare_Runner SHALL 不修改 Production_Path_Pointer、不建立 Path_Activation_Epoch、不追加 Promotion_Event 或 Path_Switch_Event；Cross_Path_Shadow_Report 仅作为 Cross_Path_Switch 的准入证据由人工引用。
15. IF Cross_Path_Switch 请求以「`seq_annotation` 的 Seq 原生宏平均 F1 高于 `legacy_day` 的宏平均 F1」作为唯一依据、且未同时提供第 11、12、13 条要求的三层证据，THEN THE Production_Path_Pointer SHALL 拒绝该请求并返回指明「跨路径证据不足」的可诊断错误。

### Requirement 8: Mock 模拟真实到达

**User Story:** 作为测试工程师，我希望 Mock 到达模拟器能刻画真实到达节奏，以便两条路径在接近真实的到达场景下被验证。

#### Acceptance Criteria

1. THE Mock_Arrival_Feeder SHALL 保留现有设备级错峰能力，在单批模拟中使延迟到达设备占比落在 5%±1%（即 4% 至 6%）区间，当天缺失设备占比落在 1%±0.5%（即 0.5% 至 1.5%）区间，其中「延迟到达」定义为该设备数据在其归属业务日之后、次日之前完成写入。
2. THE Mock_Arrival_Feeder SHALL 在写入 `training_samples` 时把 `label` 置为 NULL、`data_source` 置为 `mock`。
3. WHEN Mock_Arrival_Feeder 写入一批数据，THE Completeness_Gate SHALL 通过 `record_arrival` 同步更新对应设备-天的完整性进度。
4. IF `record_arrival` 更新完整性进度失败，THEN THE Completeness_Gate SHALL 保持该设备-天的完整性进度为更新前状态（不产生部分更新），并返回指示更新失败及所涉设备-天的错误。
5. WHERE 需要点级错峰，THE Mock_Arrival_Feeder SHALL 将点级错峰作为可选的低优先能力，且在文档中说明点级错峰仅对 Legacy_Day_Strategy 有意义、对 Seq_Daily_Strategy 无意义（后者按整天检测）。
6. THE Mock_Arrival_Feeder SHALL 以业务日为种子做确定性随机，保证对同一业务日重复生成的释放计划完全一致，即所涉设备集合、每台设备的延迟/缺失归类以及释放顺序均逐项相同。

### Requirement 9: 前端同步

**User Story:** 作为运维用户，我希望前端呈现路径切换、两条路径各自的检测状态与对比结果，以便直观掌握双路径运行情况。

#### Acceptance Criteria

1. THE Console SHALL 提供生产路径切换入口，展示当前生效的 `modeling_path` 标识，并允许在两条已注册路径之间切换。
2. THE Console SHALL 按路径分别展示各自的检测状态、Device_Cursor 游标水位，以及最近的审核批次列表（默认展示最近 10 个批次，可翻页查看更早批次）。
3. WHEN 用户打开看板视图，THE Console SHALL 展示每个设备-天的完整性进度（以已完成项数/应完成项数表示）与 Completeness_Gate 检测闸门状态（放行/未放行），并对已满足放行条件的设备-天以独立于未放行状态的可视标识区分。
4. THE Console SHALL 并排展示 Shadow_Compare_Runner 的对比结果，包含两条路径的一致率（以百分比表示，保留两位小数）与差异项列表。
5. WHERE 两条路径对同一设备-天产出不同标签，THE Console SHALL 呈现该差异项的双方标签与差异信息（含逐类别的混淆计数）。
6. WHEN 生产路径被切换，THE Console SHALL 在切换操作完成后 3 秒内更新当前路径展示，反映生效的 `modeling_path`。
7. IF 某路径的检测状态、游标水位、审核批次或 Shadow_Compare_Runner 对比结果数据不可用，THEN THE Console SHALL 对相应展示区域呈现指示数据不可用的空状态提示，且不影响其他路径与区域的正常展示。
8. IF 生产路径切换请求失败，THEN THE Console SHALL 保持当前 `modeling_path` 展示不变，并呈现指示切换失败的错误提示。

### Requirement 10: 非功能约束

**User Story:** 作为平台维护者，我希望本 spec 遵守项目工程约束，以便在 macOS 开发机与 Linux 服务器间可迁移、可审计、可恢复。

#### Acceptance Criteria

1. WHEN 系统向持久化字段（模型路径、执行历史、会话数据、源数据路径等）写入任意路径，THE 系统 SHALL 写入相对于项目根目录或 `backend-service/` 的相对路径。
2. IF 待写入持久化字段的路径为绝对路径（以 `/` 或盘符开头），THEN THE 系统 SHALL 拒绝写入该绝对路径，并将其转换为相对路径后写入。
3. WHEN 系统生成或修改任意代码块，THE 系统 SHALL 使用该文件原生注释语法在代码块前后各添加一行独立的 `@AI_GENERATED` 起始标记与 `@AI_GENERATED: end` 结束标记，且不嵌套标记。
4. THE 系统 SHALL 在 conda 环境 `cp_web` 下运行后端服务、Python 脚本与测试。
5. WHEN 检测任务在写入记录、批次或推进游标的中途失败，THE 系统 SHALL 保证失败前已提交落盘的记录不被覆盖或破坏，且未完成的部分写入不产生重复或半成品记录。
6. WHEN 检测任务在上一轮失败后重新启动，THE 系统 SHALL 从最后一条已确认落盘记录对应的游标位置继续处理，不重复处理已完成记录，也不跳过未处理记录。
7. WHEN 系统读取或写入审计相关布尔字段，THE 系统 SHALL 仅接受 JSON boolean 值（`true`/`false`），并拒绝字符串形式的真值（如 `"true"`、`"1"`、`"yes"`）。
8. THE 系统 SHALL 不清理、不重置、不删除既有脏工作区中的任何未跟踪文件、运行产物或既有改动。
9. THE 系统 SHALL 将 modeling-paths 写接口（`PUT /cumulative-training/modeling-paths`、`register-model`、`switch-fallback`）的鉴权缺失列为上线阻断项。
10. IF 未获得用户显式授权，THEN THE 系统 SHALL 不对上述 modeling-paths 写接口实施鉴权变更。

### Requirement 11: 累计变动的精度守门自动重训

**User Story:** 作为算法负责人，我希望累计标注变动达到阈值并到周期后自动重训并按精度守门晋升，以便滚动检测始终使用"不差于上一版"的模型，避免精度回退，同时保留手动重训入口。

#### Acceptance Criteria

1. THE Accuracy_Gated_Retrainer SHALL 在 Shared_Label_Pool 上以该 modeling_path 的 Retrain_Consumption_Watermark 为起点、仅统计该路径可消费粒度的新增标注作为 change_units；WHEN 该路径 change_units 达到可配置阈值（默认 200）且距该路径上次重训已满可配置周期（默认 7 天），THE Accuracy_Gated_Retrainer SHALL 触发一次挑战者重训。
2. THE Accuracy_Gated_Retrainer SHALL 在与当前冠军模型相同的评估口径（相同数据划分方式、相同随机种子、相同守门指标）下评估挑战者模型。
3. WHEN 挑战者的守门指标优于当前冠军至少一个可配置晋升边际（默认 0.0，即严格更优即晋升），THE Accuracy_Gated_Retrainer SHALL 将挑战者晋升为该 `modeling_path` 的生产模型，并向只追加审计日志记录冠军指标、挑战者指标、晋升边际与晋升时刻。
4. IF 挑战者守门指标未达到晋升条件，THEN THE Accuracy_Gated_Retrainer SHALL 保留当前冠军继续用于滚动检测，仅将挑战者登记为实验模型不予晋升，并记录未晋升原因与双方指标。
5. THE Accuracy_Gated_Retrainer SHALL 在共享的 Shared_Label_Pool 之上按 modeling_path 独立维护 Retrain_Consumption_Watermark 与累计、重训、晋升决策，不跨路径混用冠军或挑战者，也不为任一路径复制第二份标签真相。
6. WHERE `modeling_path` 为 `seq_annotation`，THE Accuracy_Gated_Retrainer SHALL 在晋升前复用现有生产契约校验；IF 挑战者未通过生产契约校验，THEN THE Accuracy_Gated_Retrainer SHALL 拒绝晋升并保留当前冠军。
7. THE Accuracy_Gated_Retrainer SHALL 保留手动重训入口，使运维可在不满足自动触发条件时手动发起重训与（经同一精度守门的）晋升。
8. THE Accuracy_Gated_Retrainer SHALL 允许通过配置调整累计变动阈值（默认 200）、重训周期（默认 7 天）与晋升边际（默认 0.0）。
9. THE Accuracy_Gated_Retrainer SHALL 将晋升与保留视为幂等：同一次挑战者评估不重复晋升，重训中途失败时保持当前冠军与生产指针不变。
10. WHEN Accuracy_Gated_Retrainer 执行一次 Path_Internal_Promotion，THE Accuracy_Gated_Retrainer SHALL 使 Production_Path_Pointer 的 `modeling_path` 取值保持不变，并 SHALL 只追加 Promotion_Event、不追加 Path_Switch_Event。
11. THE Accuracy_Gated_Retrainer SHALL 在同一 `modeling_path` 内比较 Champion 与 Challenger 时使用同一批合法样本、同一数据划分、同一随机种子、该路径的同一守门指标与该路径的同一生产契约；IF 上述五项中任一项在 Champion 与 Challenger 之间不一致，THEN THE Accuracy_Gated_Retrainer SHALL 拒绝本次晋升并记录指明不一致项的原因。
12. WHEN Challenger 被晋升为该路径 Champion，THE Accuracy_Gated_Retrainer SHALL 把被替换的前一个 Champion 登记为该路径的可回滚历史冠军，并保留其模型引用与守门指标。
13. WHERE `legacy_day` 路径完成一次重训，THE Accuracy_Gated_Retrainer SHALL 对该重训产物执行与其他路径相同的精度守门评估，且 SHALL 不在未通过守门评估时把该产物登记为该路径 Champion。（本条**修订**现状「legacy_day 重训完成即自动晋升生产模型」，理由见「本轮修订记录」条目 R4。）
14. THE Accuracy_Gated_Retrainer SHALL 不把任一 Path_Internal_Promotion 的结果作为 Cross_Path_Switch 的准入证据，跨路径准入证据仅来自 Cross_Path_Shadow_Report（见 Requirement 7 与 Requirement 15）。

注：本条把现有"累计重训即无条件晋升"（尤其 RF/legacy_day 路径）演进为"精度守门晋升"，冠军=当前生产模型，挑战者=本次重训产物；未晋升不影响正在进行的滚动检测。第 10 至 14 条把该守门明确限定在「路径内换将」这一层，跨路径切换的门控归 Requirement 14 与 Requirement 15。

### Requirement 12: 打标闭环回流按路径进入累计训练集

**User Story:** 作为算法负责人，我希望人工审核裁决回流到单一共享的累计标签集，并按路径以正确粒度供两条路径重训，以便两条路径从同一真相学习、各自独立触发重训，且不重复打标、不互相污染。

#### Acceptance Criteria

1. THE Backfill_Loop SHALL 将人工审核的天级裁决与逐点标注操作回流到唯一的 Shared_Label_Pool，不为任一 `modeling_path` 单独复制或维护第二份标签真相。
2. WHEN 为某 `modeling_path` 构建训练快照，THE Backfill_Loop SHALL 按该路径可消费的粒度对 Shared_Label_Pool 投影：`seq_annotation` 取逐点标签，`legacy_day` 取天级标签（可由逐点标签聚合得到）。
3. WHERE 某标注仅为天级裁决而无逐点粒度，THE Backfill_Loop SHALL 允许其供 `legacy_day` 使用，且不得将其铺满为 288 点标签供 `seq_annotation` 使用，以免把粗标签当逐点真相污染序列训练。
4. THE Backfill_Loop SHALL 在 Shared_Label_Pool 上按 `modeling_path` 维护各自的 Retrain_Consumption_Watermark，使每条路径的 change_units 仅统计其水位之后、且其可消费粒度的新增标注。
5. WHEN 某 `modeling_path` 完成一次重训，THE Backfill_Loop SHALL 仅推进该路径的 Retrain_Consumption_Watermark，不改变另一路径的水位与计数。
6. WHEN 一次回流写入发生，THE Backfill_Loop SHALL 使其对两条路径均可见（各自按粒度投影），而非分别写入两份数据。
7. THE Backfill_Loop SHALL 不负责训练集的特征构建与模型训练本身——逐点标签事实来源、样本切分与模型训练归属 `pv-fault-timeseries-diagnosis`；本 spec 只保证回流路由、粒度投影与按路径水位计数正确，并触发对应路径的精度守门重训。

### Requirement 13: 序列设备日记账（取代单一时间游标作为权威真相）

**User Story:** 作为平台维护者，我希望序列路径以逐设备日的记账作为「是否已处理某个独立自然日」的权威真相，以便日期乱序完成时既不永久漏检、也不产生队头阻塞与多日积压。

#### Acceptance Criteria

1. THE Seq_Device_Day_Ledger SHALL 以 `(slot, modeling_path, site_id, device_id, branch_id, business_date)` 六元组作为唯一键存储每个 Device_Day 的处理状态，并作为「序列路径是否已处理该 Device_Day」的唯一权威真相。
2. THE Seq_Device_Day_Ledger SHALL 为每条记录至少存储以下字段：`status`（处理状态，取值仅限 `waiting_data`、`ready`、`running`、`succeeded`、`failed`、`revision_pending`）、`input_fingerprint`（该设备日输入数据指纹）、`batch_id`（成功时对应的不可变审核批次标识）、`attempt_count`（已尝试处理次数，非负整数）、`last_error`（最近一次失败的可诊断原因，无失败时为空）、`processed_at`（最近一次状态推进时刻，UTC）。
3. WHEN 某设备存在多个候选 Device_Day 且其中较晚日期已通过 Completeness_Gate、较早日期未通过 Completeness_Gate，THE Seq_Device_Day_Ledger SHALL 允许较晚日期的 `status` 独立推进至 `succeeded`，同时把较早日期的 `status` 保持为 `waiting_data`。
4. THE Seq_Device_Day_Ledger SHALL 不因某个 Device_Day 的 `status` 为 `waiting_data` 或 `failed` 而阻止同一设备任何更晚 `business_date` 的 Device_Day 被处理。
5. WHERE 某 Device_Day 的 `status` 为 `succeeded` 且其当前计算出的 `input_fingerprint` 与记录中的 `input_fingerprint` 相同，THE Seq_Daily_Strategy SHALL 不再次检测该 Device_Day。
6. WHEN 某 `status` 为 `succeeded` 的 Device_Day 的当前计算出的 `input_fingerprint` 与记录中的 `input_fingerprint` 不同，THE Seq_Device_Day_Ledger SHALL 把该记录的 `status` 置为 `revision_pending`，并在后续处理中新建一个修订批次、在该修订批次中记录 `supersedes_batch_id` 指向原 `batch_id`，且 SHALL 保持原首次审核批次的内容不被修改或删除。
7. THE Seq_Daily_Strategy SHALL 为每个被处理的 Device_Day 独立构造 288 点时钟网格、独立执行预测、独立写入审核批次与预测记录；WHILE 单轮内处理两个及以上 Device_Day，THE Seq_Daily_Strategy SHALL 不把不同 `business_date` 的数据点合并为同一个模型输入。
8. THE Seq_Daily_Strategy SHALL 暴露可配置的单轮设备日处理上限 `max_device_days_per_cycle`（整数，取值范围 1 至 1000，默认值 50）；WHEN 待处理 Device_Day 数量超过该上限，THE Seq_Daily_Strategy SHALL 按 `business_date` 升序选取前 `max_device_days_per_cycle` 个处理，其余保持 `ready` 状态顺延至后续轮次。
9. WHEN 配置的 `max_device_days_per_cycle` 超出 1 至 1000 范围，THE Seq_Daily_Strategy SHALL 拒绝该配置并回退至默认值 50。
10. THE Seq_Daily_Strategy SHALL 把按 `max_device_days_per_cycle` 分批处理积压 Device_Day 的行为记录为「分批消化积压」，并 SHALL 不把同一批内的多个 Device_Day 合并为一次预测。
11. THE Seq_Device_Day_Ledger SHALL 把 Continuous_Completion_Frontier 作为按设备派生的摘要值提供给看板与候选查询；THE Seq_Daily_Strategy SHALL 不把 Continuous_Completion_Frontier 作为排除候选 Device_Day 的唯一条件。
12. IF 对某 Device_Day 的记账写入失败，THEN THE Seq_Device_Day_Ledger SHALL 保持该 Device_Day 与其他所有 Device_Day 的记录为写入前状态、不产生部分写入，并返回指明该六元组键与失败原因的可诊断错误。
13. WHEN 某 Device_Day 处理失败，THE Seq_Device_Day_Ledger SHALL 把 `status` 置为 `failed`、把 `attempt_count` 增加 1、把失败原因写入 `last_error`，并允许该 Device_Day 在后续轮次被重新处理。

### Requirement 14: 路径启用周期与切换准入范围

**User Story:** 作为平台运维，我希望首次启用或重新启用某条路径时只承担从启用起始日之后的生产检测责任，以便切换路径不触发大量历史回放、不挤占当天生产检测容量。

#### Acceptance Criteria

1. WHEN 某 `modeling_path` 被启用或重新启用为生产路径，THE Path_Activation_Epoch SHALL 新建一条记录，至少包含以下字段：`activation_epoch_id`（启用周期标识）、`modeling_path`（本次启用的路径）、`effective_from_date`（生产责任起始日）、`activation_mode`（启用模式）、`backfill_days`（回看天数，仅 `recent_window` 模式使用）、`activation_watermark`（建立本周期时该设备的数据到达水位）、`activated_at`（建立时刻，UTC）、`note`（人类可读备注）。
2. THE Path_Activation_Epoch SHALL 使该路径只对 `business_date` 大于或等于 `effective_from_date` 的 Device_Day 承担生产检测责任。
3. THE Path_Activation_Epoch SHALL 把 `business_date` 早于 `effective_from_date` 的 Device_Day 判定为「不属于本次生产责任范围」，且 SHALL 不把这些 Device_Day 计入漏检统计，也 SHALL 不为这些 Device_Day 逐条写入跳过记录。
4. THE Path_Activation_Epoch SHALL 支持三种 `activation_mode`：
   - `cutover_only`（默认）：`effective_from_date` 取该设备最近一个已结束 Device_Day 的 `business_date`；
   - `recent_window`：`effective_from_date` 取该设备最近一个已结束 Device_Day 的 `business_date` 减去 `backfill_days` 天，其中 `backfill_days` 取值范围 1 至 `max_backfill_days`、默认值 7；
   - `full_backfill`：`effective_from_date` 取该设备最早已到达数据所在自然日，且仅在人工显式选择该模式时可用。
5. WHERE `activation_mode` 为 `full_backfill`，THE Path_Activation_Epoch SHALL 把对应的历史 Device_Day 交由 Backfill_Runner 以独立限流通道执行，且该执行 SHALL 不占用生产检测容量、SHALL 不推进生产路径的 Continuous_Completion_Frontier、SHALL 不写入生产 Seq_Device_Day_Ledger 的生产责任统计。
6. WHEN 运维提交 Cross_Path_Switch 请求，THE Production_Path_Pointer SHALL 在写入前逐项校验以下全部准入条件，并仅在全部满足时写入：
   1. 目标路径存在 Champion 且其模型工件可加载；
   2. 目标路径通过该路径的生产契约校验；
   3. 请求引用的 Cross_Path_Shadow_Report 中 `legacy_model_ref` 与 `seq_model_ref` 分别等于两条路径当前的 Champion 模型引用；
   4. 该 Cross_Path_Shadow_Report 的 `generated_at` 距请求提交时刻未超过可配置报告有效期（默认 14 天）；
   5. 该报告的 `comparable_total` 达到可配置最小样本量门槛（默认 200 个设备日）且 `coverage_rate` 达到可配置最小覆盖率门槛（默认 0.9）；
   6. 该报告的 `uncomparable_items` 中不存在 `severity` 取值为 `blocking` 的条目，其中 `severity=blocking` 定义为「因模型工件不可加载或推理执行异常导致该设备日无结果」，区别于 `severity=deferred`（因完整性门控顺延导致该设备日无结果）；
   7. 请求显式携带取值合法的 `activation_mode`；
   8. 依据 `activation_mode` 可确定 `effective_from_date`；
   9. 请求携带人工二次确认标记（JSON boolean `true`）。
7. IF 第 6 条中任一准入条件未满足，THEN THE Production_Path_Pointer SHALL 拒绝该 Cross_Path_Switch、保持 `modeling_path` 原值不变、不建立 Path_Activation_Epoch，并返回逐项列出未满足条件编号的可诊断错误。
8. WHERE 不同设备的数据到达进度不同，THE Path_Activation_Epoch SHALL 按设备三元组分别记录 `activation_watermark`，并据各设备的 `activation_watermark` 分别计算该设备的 `effective_from_date`。
9. IF 某设备在建立 Path_Activation_Epoch 时无任何已到达数据，THEN THE Path_Activation_Epoch SHALL 不为该设备设定 `effective_from_date`，并在该设备首次数据到达后以该次到达所在自然日建立其 `effective_from_date`。
10. WHEN 同一 `modeling_path` 被重新启用为生产路径，THE Path_Activation_Epoch SHALL 新建一个 `activation_epoch_id` 的记录；THE Path_Activation_Epoch SHALL 把两次启用之间由另一条路径承担生产检测的 `business_date` 判定为不属于本次周期的生产责任范围，且 SHALL 不把这些日期计入本次周期的待处理积压。
11. THE Path_Activation_Epoch SHALL 不把另一条 `modeling_path` 的历史检测结果标记为本路径已处理，理由是两条路径的模型、输入形态与输出粒度不同，跨路径挪用会使并排对比与审计失真。
12. THE Path_Activation_Epoch SHALL 暴露可配置的 `max_backfill_days`（最大允许回看天数，整数，取值范围 1 至 3650，默认值 14）与 `production_capacity_reserved_ratio`（为生产检测预留的容量比例，取值范围 0.0 至 1.0，默认值 0.8）；WHEN 提交的 `backfill_days` 大于 `max_backfill_days`，THE Path_Activation_Epoch SHALL 拒绝该请求并返回指明超限值与上限值的可诊断错误。
13. WHILE Backfill_Runner 正在执行 `full_backfill`，THE Backfill_Runner SHALL 使生产检测可用容量不低于 `production_capacity_reserved_ratio` 所规定的比例。

### Requirement 15: 双层冠军—挑战者与审计事件分离

**User Story:** 作为算法负责人，我希望模型晋升与路径切换分成两层、分别门控、分别审计，以便「换一个更好的模型」与「换一条建模思路」不被混为一谈，且生产退化时优先用代价更低的手段恢复。

#### Acceptance Criteria

1. THE PV_Model_Registry SHALL 为每条 `modeling_path` 存储 `champion`（当前冠军模型登记）、`challengers`（挑战者模型登记列表）与 `retired`（已退役/可回滚历史冠军登记列表）三部分，且每部分至少含 `model_ref`（模型工件引用，相对路径或标识）、`evaluation_id`（产生该登记的评估标识）、`gate_metric_value`（守门指标取值）与 `registered_at`（登记时刻，UTC）。
2. THE PV_Model_Registry SHALL 作为 `pv_fault` 槽位模型身份与生产路径的唯一可写真相；THE Deployment_Arena SHALL 通过只读适配器读取 PV_Model_Registry 展示 `pv_fault` 槽位，且 SHALL 不为 `pv_fault` 另行维护一份可写的槽位模型真相。
3. WHERE 槽位不是 `pv_fault`，THE Deployment_Arena SHALL 继续以其现有槽位存储作为该槽位的可写真相。
4. WHEN 同一 `modeling_path` 内的 Challenger 在同一批合法样本、同一数据划分、同一随机种子、该路径同一守门指标与该路径同一生产契约下严格优于 Champion，THE Accuracy_Gated_Retrainer SHALL 执行 Path_Internal_Promotion，把该 Challenger 登记为该路径 `champion`，把被替换的 Champion 移入 `retired`，并保持 Production_Path_Pointer 的 `modeling_path` 不变。
5. IF 两条 `modeling_path` 中存在任一条尚无合格 Champion，THEN THE Shadow_Compare_Runner SHALL 拒绝生成 Cross_Path_Shadow_Report，且 THE Production_Path_Pointer SHALL 拒绝 Cross_Path_Switch 请求。
6. WHEN 两条 `modeling_path` 各自已有合格 Champion，THE Shadow_Compare_Runner SHALL 使用两边 Champion 在同一批完整历史设备日上以只读方式生成 Cross_Path_Shadow_Report（字段与三层证据要求见 Requirement 7 第 9 至 13 条）。
7. WHEN 一次 Path_Internal_Promotion 完成，THE PV_Model_Registry SHALL 向只追加审计日志追加一条 Promotion_Event，至少包含 `promotion_event_id`（晋升事件标识）、`modeling_path`（发生晋升的路径）、`champion_model_ref`（晋升后冠军模型引用）、`challenger_model_ref`（本次被评估的挑战者模型引用）、`evaluation_id`（本次评估标识）与 `promoted_at`（晋升时刻，UTC），且既有审计记录不被修改或删除。
8. WHEN 一次 Cross_Path_Switch 完成，THE PV_Model_Registry SHALL 向只追加审计日志追加一条 Path_Switch_Event，至少包含 `path_switch_event_id`（切换事件标识）、`from_path`（切换前路径）、`to_path`（切换后路径）、`comparison_id`（引用的跨路径对比标识）、`activation_epoch_id`（本次建立的启用周期标识）、`effective_from_date`（生产责任起始日）、`activation_mode`（启用模式）、`operator`（操作人标识）、`reason`（切换原因）与 `switched_at`（切换时刻，UTC），且既有审计记录不被修改或删除。
9. THE PV_Model_Registry SHALL 使 Promotion_Event 与 Path_Switch_Event 存储为两类相互独立的审计事件；THE PV_Model_Registry SHALL 不把 Promotion_Event 记录为 Path_Switch_Event，也 SHALL 不把 Path_Switch_Event 记录为 Promotion_Event。
10. WHEN 当前生产路径出现精度退化且该路径存在满足第 4 条晋升条件的 Challenger，THE Accuracy_Gated_Retrainer SHALL 先执行 Path_Internal_Promotion 恢复，并保持 Production_Path_Pointer 的 `modeling_path` 不变。
11. IF 当前生产路径整体不可用——即该路径无满足第 4 条晋升条件的 Challenger、或其 Champion 模型工件不可加载、或其 Completeness_Gate 在可配置连续轮次内持续无法覆盖任何设备日（默认 24 轮）、或其生产契约校验返回不通过、或其整路径检测在可配置连续轮次内持续以 `status=failed` 结束（默认 3 轮）——THEN THE Production_Path_Pointer SHALL 允许执行 Cross_Path_Switch 回退到 `fallback_path`，并按第 8 条追加 Path_Switch_Event。
12. THE Production_Path_Pointer SHALL 不在仅有第 10 条所述路径内可恢复条件成立时执行 Cross_Path_Switch。
13. THE Shadow_Compare_Runner SHALL 不修改 PV_Model_Registry 的 `champion`、不修改 Production_Path_Pointer、不追加 Promotion_Event 或 Path_Switch_Event。

## 本轮修订记录（Revision Log）

本节记录本轮被撤销或改写的既有判断，格式为「原表述 → 新表述 → 修订原因」。既有 Requirement 编号与决策编号一律保留，不删除。

### R1：撤销「首个失败日阻塞更晚日期」（涉及 Req3.9）

- **原表述**：Seq 路径按 Event_Time 升序维护单一 `Device_Cursor` 作为连续成功前沿；遇到第一个未通过完整性闸门/查询为空/被 predictor 拒绝的日期，该日及**全部更晚候选日期**一律顺延，不得检测更晚日期，不得让游标越洞。
- **新表述**：以 Seq_Device_Day_Ledger（键为 `(slot, modeling_path, site_id, device_id, branch_id, business_date)`）作为「是否已处理某个独立自然日」的唯一权威真相；允许日期乱序完成，较早未完整日保持 `waiting_data`、较晚已完整日可独立成功；`Device_Cursor` 降级为 Continuous_Completion_Frontier 摘要，仅供看板与查询优化，不得作为排除候选设备日的唯一条件。详见 Requirement 13 与 Req3.9、Req3.11 至 Req3.13。
- **修订原因**：单一时间游标只能表达「一条线」，与「按日滚动、多设备异步到达」的现实不匹配。若允许游标越过未完整的前一天，该天补齐后会永久落在窗口之外，形成永久漏检；若为保护前一天而阻塞更晚日期，则形成队头阻塞与多日积压，一台设备的数据缺口会拖住其后所有日期。逐设备日记账把「进度」从一维水位改为按设备日的显式状态，两个坏结果都被消除；连续完成前沿保留下来只作为人类可读摘要。

### R2：修订决策 Q2 的实现语义（涉及决策 Q2、Req5.6）

- **原表述**：不迁移旧游标，两条路径分区均从「固定初始水位」重建，首轮各自重新推进。
- **新表述**：保留「不复制另一条路径的游标」这一条不变；但明确「不复制游标 ≠ 必须从最早历史数据开始」。固定初始水位由该路径当前 Path_Activation_Epoch 的 `effective_from_date` 确定，默认 `activation_mode` 为 `cutover_only`（仅从各设备最近一个已结束设备日开始）。详见 Requirement 14 与 Req5.6。
- **修订原因**：原表述未界定「初始水位」的绝对位置，最保守的实现会把它读成「该设备最早历史数据所在自然日」。这样长期运行老路径后首次切到新路径，会一次性重跑数月甚至数年的历史设备日，浪费算力并挤占当天生产检测容量，切换成本被无谓放大。引入路径启用周期后，「不共享进度」与「不回放全部历史」这两件事被分开表达。

### R3：明确 Shadow 只产证据、不自动切换（涉及 Req7、Req6）

- **原表述**：Shadow 对比只记录不影响生产事实，未明确禁止把对比结论自动作用于生产路径，也未规定跨路径准入需要哪些证据层。
- **新表述**：Cross_Path_Shadow_Report 只产证据，不修改 Production_Path_Pointer、不建立 Path_Activation_Epoch、不追加任何审计事件；跨路径准入必须同时具备共同口径、Seq 原生增益、生产运行指标三层证据，且禁止仅用「Seq 宏平均 F1 更高」作为切换依据。详见 Req7.9 至 Req7.15、Req14.6。
- **修订原因**：两条路径的输出粒度不同（天级 vs 逐点），Seq 原生指标在 Legacy 上没有对应值，单拿一个宏平均 F1 横向比较在口径上不成立。同时，「值得切」不只取决于精度，还取决于延迟、门禁顺延比例、推理失败率与每日容量这些运行指标——序列路径要等整天完整，运行侧代价与 Legacy 明显不同。

### R4：把 legacy_day 重训自动晋升纳入精度守门（涉及 Req11.13）

- **原表述（现状代码行为）**：`backend-service/api/iterative_labeling.py` 中 `promote_to_production = _modeling_path != "seq_annotation"`，即 `legacy_day` 重训完成后直接自动晋升为生产模型，无精度门控；`path_models[path]` 每路径只存一份最新登记。
- **新表述**：`legacy_day` 重训产物与其他路径一样必须通过路径内精度守门评估才能成为该路径 Champion；`path_models` 扩展为每路径含 `champion` / `challengers` / `retired`，被替换的冠军进入可回滚历史。详见 Req11.12、Req11.13、Req15.1、Req15.4、Req15.7。
- **修订原因**：无门控自动晋升等价于「最后一次重训一定上生产」，一次数据质量波动就能让生产模型退化，且没有可回滚的历史冠军可用于恢复。

### R5：明确 PV 模型真相唯一可写（涉及 Req15.2、Req15.3）

- **原表述**：通用部署演习场（`backend-service/services/deployment/store.py`）以 `slots.json` 维护槽位模型真相，光伏双路径另以累计训练登记维护 `production_path` / `path_models`，两者未打通，前端可能读到两份不一致的模型身份。
- **新表述**：`pv_fault` 槽位的模型身份与生产路径以 PV_Model_Registry（光伏累计训练登记）为唯一可写真相；通用演习场页面通过只读适配器读取，不为 `pv_fault` 另维护可写 `slots.json` 模型真相；其他业务槽位继续用现有部署槽位存储。
- **修订原因**：两份可写真相会产生「页面显示的生产模型」与「调度器实际加载的生产模型」不一致，审计无法定论。收敛为单一可写真相 + 只读适配是代价最小的一致性方案。

## 设计决策（已确认）

1. **序列路径时间基准（Q1）**：采用 Data_Watermark（数据到达水位），历史回放与实时生产统一按数据推进，不用墙钟。
2. **游标迁移（Q2）**：不迁移旧游标，两条路径分区均从初始水位重建；首轮将按各自分区重新推进。（本轮已修订「初始水位」的实现语义，见决策 11 与修订记录 R2：不复制游标 ≠ 从最早历史开始。）
3. **隔离分区键（Q3）**：为 `device_prediction_cursor`、`prediction_records`、审核批次增加 `modeling_path` 列作为分区维度（与 `slot` 组合）。
4. **Shadow 对比（Q4）**：手动触发一批设备日，结果以相对路径 JSON 存储，不写入生产库。
5. **完整性阈值 / expected_point_count 配置（Q5）**：从配置文件读取，可被环境变量覆盖。
6. **modeling-paths 写接口鉴权（Q6）**：本轮不实施，仅作为上线阻断项记录；实施需用户显式授权。
7. **累计变动精度守门重训（新增）**：见 Requirement 11，冠军-挑战者精度门控、按路径独立、复用生产契约、保留手动重训。
8. **双路径时间基准统一（新增收敛）**：两条路径共用 Data_Watermark 作为时间进度基准、都不看墙钟；检测窗口粒度不同（传统按天=数据水位当天增量、序列=数据水位前完整整天）为按模型能力有意保留；Shadow 对比在两条路径均可产出的同一批完整历史设备日上进行以保证公平。
9. **打标回流按路径落地（新增）**：累计标签为单一共享真相、不拆两份；回流按路径投影粒度（seq=逐点、legacy=天级聚合）；change_units 按路径维护 Retrain_Consumption_Watermark 独立计数；天级裁决不铺满 288 供 seq；训练集构建/模型训练边界归 pv-fault-timeseries-diagnosis。见 Requirement 12。
10. **撤销「首个失败日阻塞更晚日期」（本轮）**：Seq 进度改为 Seq_Device_Day_Ledger 逐设备日记账，作为「是否已处理某个独立自然日」的唯一权威真相；允许日期乱序完成，较早未完整日保持 `waiting_data`、较晚已完整日独立成功；`Device_Cursor` 降级为 Continuous_Completion_Frontier 摘要仅供看板与查询优化。理由：单一游标越洞会永久漏检、阻塞则队头阻塞并积压多日。见 Requirement 13、Req3.9、修订记录 R1。
11. **修订 Q2 语义：不复制游标 ≠ 从最早历史开始（本轮）**：保留「切换不复制另一条路径游标」；固定初始水位改由 Path_Activation_Epoch 的 `effective_from_date` 确定。理由：否则首次切换会重跑全部历史设备日、挤占当天生产检测容量。见 Requirement 14、Req5.6、修订记录 R2。
12. **`activation_mode` 默认 `cutover_only`（本轮）**：默认只从各设备最近一个已结束设备日开始；`recent_window` 按 `backfill_days`（默认 7、上限 `max_backfill_days`）有限回看；`full_backfill` 仅人工显式选择，交由 Backfill_Runner 独立限流执行，不占用生产检测容量、不污染生产进度。配置上限 `max_backfill_days` 默认 14、生产容量预留 `production_capacity_reserved_ratio` 默认 0.8。见 Req14.4、Req14.5、Req14.12。
13. **Shadow 只产证据、绝不自动切换生产路径（本轮）**：Cross_Path_Shadow_Report 不改 Production_Path_Pointer、不建 Path_Activation_Epoch、不追加审计事件；跨路径准入必须三层证据（共同口径投影后的天级对比 / Seq 原生增益 / 生产运行指标），禁止仅用「Seq 宏平均 F1 更高」作为切换依据。见 Req7.9–Req7.15、Req14.6、修订记录 R3。
14. **审计事件分离：Promotion_Event 与 Path_Switch_Event（本轮）**：路径内换将只追加 Promotion_Event 且不改 `production_path`；跨路径换班组只追加 Path_Switch_Event 且必须带 `comparison_id` / `activation_epoch_id` / `effective_from_date` / `activation_mode` / `operator`。两类事件不得互相冒充。生产退化恢复顺序固定为「先路径内换将，仅整路径不可用才跨路径回退 `fallback_path`」。见 Requirement 15、Req11.10–Req11.14。
15. **PV 模型登记为唯一可写真相（本轮）**：`pv_fault` 的模型身份与生产路径以 PV_Model_Registry（光伏累计训练登记）为唯一可写真相，`path_models` 扩展为每路径含 `champion` / `challengers` / `retired`；通用部署演习场页面通过只读适配器读取，不为 PV 另维护可写 `slots.json` 模型真相；其他业务槽位继续用现有部署槽位存储。同时把 `legacy_day` 重训自动晋升纳入路径内精度守门。见 Req15.1–Req15.3、Req11.13、修订记录 R4/R5。
<!-- @AI_GENERATED: end -->
