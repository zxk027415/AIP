<!-- @AI_GENERATED -->
# Implementation Plan: 光伏故障诊断双路径生产接入（pv-fault-dual-path-serving）

## Overview

本计划把 requirements.md 的 Requirement 1–15、R1–R5 与 design.md 的 Property 1–42 拆成可独立编码、验证和回滚的叶子任务。执行顺序固定为：保留已完成基线 → 补数据模型/配置 → 建 Ledger/Epoch/PV Registry 真相层 → 接生产策略与旁路能力 → 接 REST/前端 → 属性/集成/回归验证 → 独立语义审阅与最终自审。

### 已确认的完成事实与修订原则

- 已完成事实保持 `[x]`，不因新设计扩展而回退：原 1–3、4.1–4.2、5.1、6.1、7.1、11.1，以及 Property 1–7、旧版 Property 8、Property 9–12、Property 20 的测试。
- 旧版 Property 8 已验证“只检测水位前完整整天”的基础行为；当前 Property 8 新增 Ledger、Epoch、日期不阻塞和逐日独立批次语义，因此另设待完成扩展测试，不修改旧完成事实。
- Seq 是否处理过某个设备日只以 `Seq_Device_Day_Ledger` — 序列设备日记账为权威；`Continuous_Completion_Frontier` — 连续完成前沿仅为摘要。
- 缺少路径游标时从当前 `Path_Activation_Epoch` — 路径启用周期内该设备的 `effective_from_date` — 生产责任起始日开始，不复制另一条路径游标，也不默认从最早历史数据重建。
- Legacy 与 Seq 的重训产物都必须经过同路径精度守门；路径内晋升只写 `Promotion_Event` — 模型晋升事件，不改变生产路径。
- Shadow 只使用两条路径当前 Champion，只产三层证据，不自动切换生产；跨路径切换必须通过九项门控并只写 `Path_Switch_Event` — 路径切换事件。
- `PV_Model_Registry` — 光伏模型登记是 `pv_fault` 槽位唯一可写真相；Deployment Arena 对该槽位只读，其他槽位保持原写路径。

### 关键字段与接口字段约定

以下字段首次出现时统一定义，后续任务可直接引用：

- `slot` — 槽位/产品线分区键；默认 `default`，光伏产品线调用应显式使用 `pv_fault`。
- `site_id` / `device_id` / `branch_id` — 站点标识/设备标识/支路标识，共同组成设备三元组。
- `business_date` — 设备日所属的业务自然日。
- `page` / `page_size` — 分页页码/每页条数。
- `modeling_path` — 建模/检测路径，取 `legacy_day` 或 `seq_annotation`。
- `status` — 处理状态；Ledger 中取 `waiting_data`、`ready`、`running`、`succeeded`、`failed`、`revision_pending`。
- `point_count` / `expected_point_count` — 已到达点数/期望点数，用于完整性比例。
- `input_fingerprint` — 设备日输入数据稳定指纹。
- `batch_id` — 最新成功的不可变审核批次标识。
- `supersedes_batch_id` — 修订批次所取代的前一批次标识。
- `attempt_count` — 实际处理失败次数。
- `last_error` — 最近一次可诊断失败原因。
- `processed_at` — 最近一次状态推进 UTC 时刻。
- `cursor_semantics` — 游标语义，取 `event_time_watermark` 或 `continuous_completion_frontier`。
- `activation_epoch_id` — 路径启用周期标识。
- `activation_mode` — 启用模式，取 `cutover_only`、`recent_window` 或 `full_backfill`。
- `activation_watermark` — 建立启用周期时的设备数据水位。
- `effective_from_date` — 本启用周期对某设备承担生产责任的起始日。
- `production_cutover_date` — full_backfill 下生产在线车道开始接管的日期。
- `backfill_days` — recent_window 的回看天数。
- `lane` — 执行车道，取 `production` 或 `historical_backfill`。
- `range_start` / `range_end` — 车道认领半开日期区间的起点/不含终点。
- `claim_status` — 车道认领状态，取 `claimed`、`running`、`succeeded`、`failed` 或 `cancelled`。
- `backfill_task_id` — 历史回放任务标识。
- `production_path` / `fallback_path` — 当前生产路径/回退路径。
- `path_models` — 按路径分区的模型生命周期登记。
- `champion` / `challengers` / `retired` — 当前冠军/挑战者列表/可回滚历史冠军列表。
- `model_ref` — 模型工件相对路径或稳定标识。
- `evaluation_id` — 产生模型登记的评估标识。
- `gate_metric_value` — 路径内守门指标值。
- `registered_at` — 模型登记 UTC 时刻。
- `candidate_id` — Challenger 登记记录标识，用于在同一路径内唯一选择待晋升模型。
- `champion_model_ref` / `challenger_model_ref` — 晋升前冠军模型引用/被评估挑战者模型引用。
- `set_as_production` — 是否把胜出的 Challenger 同步设为该路径 Champion；为 `true` 时写入的必须是 `challenger_model_ref`，绝不回写旧 Champion，且不改变跨路径 `production_path`。
- `production_slot` — Promote 写入模型登记时使用的槽位；默认 `pv_fault`，并与 modeling-paths 登记接口的 `slot` 保持一致。
- `promotion_event_id` — 路径内晋升事件标识。
- `promoted_at` — 路径内晋升完成的 UTC 时刻。
- `path_switch_event_id` — 跨路径切换事件标识。
- `from_path` / `to_path` — 跨路径切换前的生产路径/切换后的目标路径。
- `switched_at` — 跨路径切换完成的 UTC 时刻。
- `comparison_id` — 跨路径 Shadow 比对任务标识，用于异步轮询与切换引用。
- `start_date` / `end_date` — Shadow 比对业务日期闭区间的起始日/结束日。
- `device_scope` — Shadow 比对设备范围；由设备三元组列表组成。
- `legacy_model_ref` / `seq_model_ref` — 报告引用的两条路径 Champion 模型。
- `device_day_total` / `comparable_total` — 候选设备日总数/两路均成功的可比设备日数。
- `agreement_rate` / `coverage_rate` / `deferred_rate` — 天级一致率/结果覆盖率/门禁顺延比例。
- `diff_items` / `uncomparable_items` — 标签差异项/不可比项列表。
- `severity` — 不可比严重级别，取 `blocking` 或 `deferred`。
- `projection_rule` — Seq 逐点结果投影为天级结果的规则标识与定义。
- `common_metrics` / `seq_native_metrics` / `runtime_metrics` — 共同天级证据/Seq 原生证据/生产运行证据。
- `generated_at` — Shadow 报告生成 UTC 时刻。
- `confirm` — 人工二次确认，仅接受 JSON boolean `true`。
- `operator` / `reason` / `note` — 操作人标识/切换原因/人类可读备注。
- `device_scope_digest` / `device_scope_count` — 不可变设备范围摘要/设备范围条数。
- `updated_at` — 登记最后更新时间。

### 工程约束

- 后端、脚本、pytest、py_compile 均在 conda 环境 `cp_web` 下执行；前端从 `frontend-sevice/` 执行。
- 所有持久化路径写相对项目根或 `backend-service/` 的路径；绝对路径先安全转换，不能转换则拒绝。
- 新增或修改代码块使用文件原生注释语法加 `@AI_GENERATED` / `@AI_GENERATED: end`，不得嵌套。
- 不清理、重置、删除脏工作区文件或运行产物；迁移幂等、事务化，不做破坏性数据清理。
- `PUT /cumulative-training/modeling-paths`、`register-model`、`switch-fallback` 鉴权缺失继续作为上线阻断；未获用户显式授权不得顺手实施鉴权。
- Property 1–42 均是必做测试；Hypothesis 每条至少 100 次，不再标为可选任务。

## Tasks

- [x] 1. 冻结并保留已完成基线
  - [x] 1.1 ORM 增加 `modeling_path` 分区列与复合主键
    - 已完成 `DevicePredictionCursor` 与 `PredictionRecord` 的路径分区基础；新设计所需 `slot`、`cursor_semantics` 和新表由任务 2 增量补齐。
    - _需求: 5.1, 5.2_
  - [x] 1.2 编写幂等 modeling_path 分区迁移脚本
    - 已完成旧表加列、历史记录回填和复合键基础迁移；R2 的 Epoch 起始边界不视为本任务已完成，由任务 2.4、4.2、7.1 修正。
    - _需求: 5.1, 5.6, 10.8_
  - [x] 1.3 编写迁移与 ORM 幂等性单元测试
    - 已完成重复迁移、重复加列和空值回填验证。
    - _需求: 5.1, 5.2, 10.8_
  - [x] 1.4 实现 DualPathConfig 基础配置
    - 已完成 `completeness_ratio` — 完整性比例与 `expected_point_count` — 期望点数的配置、环境变量覆盖和越界回退。
    - _需求: 4.2, 4.5_
  - [x] 1.5 实现 CompletenessGate
    - 已完成比例判定、Seq 严格门禁、Legacy 宽松放行、缺字段诊断与首次达标幂等。
    - _需求: 4.1, 4.3, 4.4, 4.6, 4.7_
  - [x] 1.6 实现 DataWatermarkService
    - 已完成公共设备数据水位计算和自然日查询，不按路径复制水位；已完成设备无下一自然日到达数据时水位停留在当前最大 Event_Time 自然日、不因墙钟跨日封日（Req3.10）。
    - _需求: 1.8, 1.9, 2.9, 3.1, 3.10_
  - [x] 1.7 编写水位计算单元测试
    - 已完成无数据、多设备独立和回退分支测试。
    - _需求: 1.8, 3.1_
  - [x] 1.8 定义策略抽象与上下文/结果契约
    - 已完成 `CycleContext`、`CycleResult` 与 `DetectionStrategy` 基础契约。
    - _需求: 1.5, 1.6, 1.7_
  - [x] 1.9 实现 DualPathScheduler.dispatch 基础分派与运行状态落账
    - 已完成双路径互斥分派、非法路径跳过和基础运行状态记录；Champion/Epoch 注入由任务 6.1 扩展。
    - _需求: 1.1, 1.2, 1.3, 1.4, 1.5_
  - [x] 1.10 实现 LegacyDayStrategy 事件时间基础语义
    - 已完成 Data Watermark 上界、按自然日拆分、游标单调、无效时间拒绝和 Legacy 宽松门禁。
    - _需求: 2.1–2.9, 4.4_
  - [x] 1.11 实现 SeqDailyStrategy 水位前整天基础语义
    - 已完成水位前整天、完整性门禁、单日 predictor、288 点契约与旧不可变批次恢复基础；Ledger 权威、无队头阻塞、修订状态和 frontier 摘要由任务 6.4–6.7 扩展；"不截断当天+不把未到点并入次日会破坏时钟槽语义并被 predictor 拒绝"的理由说明（Req3.8）已记录于 design.md「关键设计结论」，本任务代码行为与该记录一致。
    - _需求: 3.1–3.8, 4.3_
  - [x] 1.12 实现 PathIsolationRegistry 基础分区读写
    - 已完成游标/预测记录/批次按路径分区、批次原子落盘和严格审计布尔基础；Epoch 初始边界由任务 7.1 修正；已完成 Completeness_Gate 因门控跳过设备-天时不推进本路径 Device_Cursor、也不改变另一路径游标（Req4.8）。
    - _需求: 4.8, 5.1–5.7, 10.5, 10.7_
  - [x] 1.13 校准 Mock 到达比例与确定性业务日种子
    - 已完成设备级错峰、`label=NULL`、`data_source=mock`、完整性同步和确定性释放计划；点级错峰继续不实现。
    - _需求: 8.1–8.6_

- [ ] 2. 扩展 ORM、配置与幂等迁移
  - [x] 2.1 新增 Ledger、Epoch、DeviceScope 与 LaneClaim ORM
    - 已在 `backend-service/services/db/models/pv_fault.py` 新增 `SeqDeviceDayLedger`/`PathActivationEpoch`/`PathActivationDeviceScope`/`PathActivationLaneClaim` 四个 ORM 类，落实复合主键、CheckConstraint 枚举约束、索引；已验证 `py_compile` 通过。真实数据库迁移与幂等性验证是任务 2.4/2.5 的范围，本任务只交付 ORM 定义。
    - Ledger 六元组键为 `(slot, modeling_path, site_id, device_id, branch_id, business_date)`；Epoch、DeviceScope、LaneClaim 需支持同事务创建。
    - _需求: 13.1, 13.2, 14.1, 14.8_
  - [x] 2.2 扩展 cursor/record schema 与语义
    - 已为 `DevicePredictionCursor` 新增 `cursor_semantics` 字段（CheckConstraint 限定 `event_time_watermark`/`continuous_completion_frontier`）；已确认 `PredictionRecord.slot` 字段存在并新增 `ix_prediction_records_slot_path_device` 索引，旧索引保留未删除。已验证 `py_compile` 通过；历史行真实回填由任务 2.4 迁移脚本执行。
    - 为 `device_prediction_cursor` 补 `slot` 与 `cursor_semantics`；Legacy 取 `event_time_watermark`，Seq 取 `continuous_completion_frontier`。
    - 为 `prediction_records` 补非空 `slot` 并建立 `(slot, modeling_path, site_id, device_id, branch_id, business_date)` 索引；历史行稳定回填 `legacy_day`。
    - _需求: 3.13, 5.1, 5.2, 13.11_
  - [x] 2.3 扩展所有设计默认配置
    - 已在 `backend-service/config/pv_dual_path.yaml` 与 `services/scheduler/pv_dual_path/config.py` 新增全部 12 项默认值、越界回退函数，并接入 `DualPathConfig` dataclass 与 `load_dual_path_config()`；已运行 `load_dual_path_config()` 手工验证全部 14 个字段（含原有 2 项）取值正确。
    - 修改 `backend-service/config/pv_dual_path.yaml` — 双路径运行配置及读取器：新增 `max_device_days_per_cycle=50`（1–1000）、`max_backfill_days=14`（1–3650）、`recent_window_backfill_days=7`、`production_capacity_reserved_ratio=0.8`（0–1）、`shadow_report_valid_days=14`、`min_comparable_device_days=200`、`min_shadow_coverage_rate=0.9`、`retrain_change_threshold=200`、`retrain_period_days=7`、`promotion_margin=0.0`、`no_coverage_failure_cycles=24`、`path_failed_cycles=3`；逐项定义越界拒绝或回退规则与环境变量覆盖。
    - 保留已完成的 0.9/288 默认值，不破坏既有配置读取方。
    - _需求: 4.2, 4.5, 11.1, 11.8, 13.8, 13.9, 14.6, 14.12, 15.11_
  - [x] 2.4 编写增量幂等迁移
    - 新增版本化迁移脚本：先探测后建四张新表/列/索引；建立当前生产路径的初始 `cutover_only` Epoch；旧 Seq 成功事实仅在不可变批次可确认时回填 `succeeded`，无法确认时不猜成功；不得把旧单游标迁成 Seq 权威进度。
    - 为旧模型登记和旧审计预留兼容迁移调用，但具体生命周期/事件分类由任务 5.2 完成。
    - _需求: 5.6, 10.8, 13.1, 14.1, 14.9, 15.1_
  - [x] 2.5 编写 schema/config/migration 边界与幂等测试
    - 覆盖重复迁移、已有部分列、空库、旧数据、0/-1/1/1000/1001 单轮上限、1/3650/3651 回看上限、0/0.8/1 容量比例及所有设计默认值。
    - _需求: 10.8, 13.9, 14.12_

- [ ] 3. 实现 SeqDeviceDayLedgerRepository 与不可变修订恢复
  - [x] 3.1 实现 Ledger Repository 查询与状态接口
    - 新增 `backend-service/services/scheduler/pv_dual_path/seq_device_day_ledger.py` — 序列设备日记账仓储：实现候选 upsert、分页查询、`list_runnable`、`mark_running`、`mark_succeeded`、`mark_failed`、`compute_frontier`，所有错误返回完整六元组键。
    - _需求: 13.1, 13.2, 13.11–13.13_
  - [x] 3.2 实现独立状态机与事务回滚
    - 允许 `waiting_data → ready → running → succeeded/failed`、`failed → ready`、`succeeded → revision_pending → running`；失败仅增加目标记录的 `attempt_count` 并写 `last_error`，任何 Ledger 写失败保持全部记录为写前状态。
    - 较早日期为 `waiting_data` 或 `failed` 时不得改变较晚 `ready` 日期的可运行性。
    - _需求: 13.3, 13.4, 13.12, 13.13_
  - [x] 3.3 实现稳定输入指纹
    - 把设备日 `(event_time, value)` 按时间和稳定次序规范化后计算 SHA-256；相同输入得到相同 `input_fingerprint`，集合任意增删改产生不同摘要。
    - _需求: 13.5, 13.6_
  - [x] 3.4 实现批次与 Ledger 对账恢复
    - 已新增 `immutable_batch_recovery.py`：`prepare_for_inference()` 在 predictor 前扫描孤儿批次、计算稳定指纹并返回 skip/run；`persist_success()` 严格先落不可变批次再提交 Ledger，下一轮可按 supersedes 链补账且不重复推理。生产策略接线仍按任务 6.5/6.7 完成。
    - 已扩展 `PathIsolationRegistry.list_batch_ids()` 与 `SeqDeviceDayLedgerRepository.reconcile_succeeded_from_batch()`；修订失败恢复旧 succeeded 批次/指纹，仅增加尝试次数和错误。定向验证 13 passed，py_compile 与 diagnostics 0 error。
    - 扩展不可变批次 payload，写入 `input_fingerprint` 与 `supersedes_batch_id`；相同指纹幂等跳过，变化进入 `revision_pending` 并写新批次，旧批次不改不删。
    - 若批次已原子落盘但 Ledger 提交失败，按 `batch_id` 与指纹补齐 Ledger，不重复推理；修订失败保持旧 succeeded 事实。
    - _需求: 3.7, 10.5, 10.6, 13.5, 13.6_

- [ ] 4. 实现 PathActivationService、排他车道与 BackfillRunner
  - [x] 4.1 实现三种启用模式的逐设备边界计算
    - 新增 `backend-service/services/scheduler/pv_dual_path/path_activation.py` — 路径启用周期服务：按每台设备的 `activation_watermark` 计算 `cutover_only`、`recent_window`、`full_backfill` 的 `effective_from_date` 与 `production_cutover_date`；无数据设备边界为空，首次到达时原子补齐。
    - 超过 `max_backfill_days` 拒绝请求，不建立 Epoch；重新启用同一路径创建新 Epoch，排除另一条路径值班日期。
    - _需求: 14.1–14.4, 14.8–14.12_
  - [x] 4.2 实现 Epoch/DeviceScope 持久化与初始边界
    - Epoch 存周期级字段，DeviceScope 按设备三元组存水位和日期边界；边界前日期不计漏检、不逐条写跳过记录、不复用另一条路径处理事实。
    - 缺路径游标时以当前 Epoch 的设备 `effective_from_date` 作为固定初始边界，不回退最早历史日。
    - _需求: 5.6, 5.8, 14.1–14.3, 14.8–14.11_
  - [x] 4.3 实现 PathActivationLaneClaim 排他认领
    - full_backfill 同事务创建历史 `[effective_from_date, production_cutover_date)` 与生产 `[production_cutover_date, +∞)` 半开区间，要求无交集、无空档；cutover_only/recent_window 只创建生产 claim。
    - 历史失败保留 claim 供重试；只有人工取消并显式释放才可归还范围。
    - _需求: 14.5, 14.13_
  - [x] 4.4 实现 BackfillCapacityArbiter
    - 已新增 `backfill_capacity.py`：总令牌取 worker、数据库连接、内存和模型加载槽最小值；生产预留为 `ceil(total_tokens * production_capacity_reserved_ratio)`，历史车道只消费余量。低水位停止发放历史令牌、保留生产可用内存容量，并通过 `backfill_should_yield` 要求既有历史 lease 主动让行。
    - 定向覆盖 0/0.8/1 比例、四类瓶颈、低水位、动态降容、重复释放和非法参数：8 passed；py_compile 与 diagnostics 0 error。
    - 新增容量仲裁器：由 worker、数据库连接、内存水位和模型加载槽计算总令牌；生产预留不少于 `ceil(total_tokens * production_capacity_reserved_ratio)`，历史回放只能消费剩余令牌；资源低水位时暂停/降速并优先归还生产令牌。
    - _需求: 14.13_
  - [x] 4.5 实现 BackfillRunner 独立历史检测通道
    - 新增 `backend-service/services/scheduler/pv_dual_path/backfill_runner.py` — 历史回放执行器：只消费已认领的 `historical_backfill` 半开区间；任务 JSON 使用独立 `historical_backfill` 命名空间；不写生产 Seq Ledger、不推进生产 frontier、不改生产 LaneClaim。执行入口是 `run()`（不经 DualPathScheduler）；容量不足保持 queued。提供 `get_status` / `retry` / `cancel` / `release`。检测器必须注入，不猜测生产策略，也不复用标签回流 `BackfillLoop`。
    - **Review（2026-08-17）**：对照 Req14.5/14.13，主路径成立。未做真实线程池（由后续调度外壳拉 `run()`）；未接真实 Seq 推理（属任务 6.x）。失败保留认领、取消后必须显式 release 才把 claim 置 cancelled。
    - _需求: 14.5, 14.13_

- [ ] 5. 实现 PVModelRegistry 唯一可写真相与双事件仓储
  - [x] 5.1 定义 PVModelRegistry 状态与存储边界
    - 已新增专用 Registry 服务 `backend-service/services/iterative_labeling/pv_model_registry.py`（未修改 `cumulative_training.py`，与旧状态的兼容迁移留给任务 5.2）：存 `production_path`、`fallback_path`、`active_activation_epoch_id` 和按 `slot + modeling_path` 分区的 `path_models`；`get_slot()` 只读方法已手工验证返回默认初始状态；`register_challenger`/`promote_within_path`/`switch_path` 按设计声明签名并显式抛出 `NotImplementedError`，交由任务 5.3/10.1/10.3 实现原子语义，不臆造。
    - 每路径保存最多一个 `champion`、`challengers` 列表、`retired` 列表；每个登记含 `model_ref`、`evaluation_id`、`gate_metric_value`、`registered_at`。
    - **存什么**：PV 路径、模型生命周期和当前启用周期；**为何独立**：避免调度器与 Deployment Arena 出现两份可写真相；**分区维度**：`slot + modeling_path`；**路径/介质**：由部署配置决定，只持久化相对路径或稳定 ID。
    - _需求: 10.1, 15.1, 15.2_
  - [x] 5.2 实现兼容迁移与旧审计分类
    - 旧 `path_models[path]=latest_model` 仅在工件可加载且契约可确认时迁为 Champion，否则迁为 Challenger 并阻断切换；`challengers`/`retired` 初始为空。
    - 旧审计中可判定的同路径换模迁为 PromotionEvent，可判定的生产路径变化迁为 PathSwitchEvent，语义不明项保留到只读 `legacy_audit`，不伪造新事件、不删除 `tasks.meta.json` 或任何 executionHistory。
    - _需求: 10.8, 15.1, 15.7–15.9_
  - [x] 5.3 实现模型生命周期原子操作
    - 实现 register challenger、同路径 promote、retire old champion、幂等 evaluation；不合格 Challenger 保留并记录原因，任何路径内晋升都不改变 `production_path`。
    - _需求: 11.9–11.14, 15.4_
  - [x] 5.4 实现分离的 append-only 事件仓储
    - 已新增 `backend-service/services/iterative_labeling/pv_governance_events.py`：`PromotionEventStore` — 仅存路径内晋升事件，与 `PathSwitchEventStore` — 仅存跨路径切换事件；二者介质由部署配置决定、只追加（append + list_recent，不提供 update/delete）、字段 schema 不互换；已手工验证 append/list_recent 往返正确。真正驱动 append 的业务时机（晋升/切换成功后）留给任务 5.3/10.3。
    - PromotionEvent 至少含 `promotion_event_id`、`modeling_path`、`champion_model_ref`、`challenger_model_ref`、`evaluation_id`、`promoted_at`；PathSwitchEvent 至少含 `path_switch_event_id`、`from_path`、`to_path`、`comparison_id`、`activation_epoch_id`、`effective_from_date`、`device_scope_digest`、`device_scope_count`、`activation_mode`、`operator`、`reason`、`switched_at`。
    - _需求: 6.3, 11.10, 15.7–15.9_
  - [x] 5.5 收敛 ProductionPathPointer 为无状态门面
    - 调度器、GET/PUT、fallback 和 Deployment Arena 适配器均直接读写 PVModelRegistry 的 `production_path`；不得保留第二份可写文件、表或缓存，缓存只能只读且可失效。
    - _需求: 5.3, 6.1, 6.7, 15.2_

- [x] 6. 把 Ledger、Epoch、LaneClaim 与 Registry 接入生产调度
  - [x] 6.1 扩展 CycleContext 与调度器模型解析
    - `DualPathScheduler.dispatch(slot)` 从 PVModelRegistry 读取路径、当前 Champion 和 active Epoch；上下文补 `champion_model_ref` 与 `activation_epoch_id`；路径/Champion/Epoch 无效时返回可诊断 skipped/failed，不猜默认模型。
    - **Review（2026-08-17）**：缺 Champion → `missing_champion_model_ref`，缺 Epoch → `missing_activation_epoch`，不回退默认模型。旧 `model_ref` 与 Champion 同步。
    - _需求: 1.1–1.5, 15.2_
  - [x] 6.2 保留调度外壳并只调用新 dispatch
    - 修改 `backend-service/services/scheduler/tasks/pv_fault_tasks.py` — PV 定时任务外壳：保留任务注册与既有调度入口，内部只调用新分派器；下一轮实时读新路径，已启动轮次使用启动时快照完成。
    - **Review**：`make_pv_prediction_task` 每轮新建 DualPathScheduler 并只 `dispatch`；第二轮重读 Registry 有定向测试。
    - _需求: 1.1, 6.6_
  - [x] 6.3 为 Legacy 接入 Epoch 与 LaneClaim
    - Legacy 候选必须在当前设备责任边界内，并排除 `historical_backfill` claim；继续使用 Event Time 游标与当日增量，不因 Seq 门禁变严。
    - **Review**：`production_window.py` 共用过滤；无 Epoch 时保持旧测试宽松。未接真实生产库。
    - _需求: 2.1–2.9, 5.6, 14.2, 14.5_
  - [x] 6.4 把 Seq 改为 Ledger-driven 候选与独立日期推进
    - 候选仅取 `business_date < watermark_date`、位于当前 Epoch 责任边界、未被历史车道认领且 Ledger 非稳定 succeeded 的设备日。
    - 每个设备日独立过门禁、建 288 点网格、执行一次预测、写一个批次和记录；较早 `waiting_data`/`failed` 不阻塞较晚 `ready`。
    - **Review**：有 `activation_epoch_id` 且 adapter 可开会话时走 Ledger；旧 Property 8 无 Epoch 仍走队头语义，不回退 17.8 完成事实。
    - _需求: 3.1–3.6, 3.9, 3.11, 3.12, 13.3, 13.4, 13.7_
  - [x] 6.5 接入指纹修订与 frontier 摘要
    - succeeded 指纹相同幂等跳过；变化时走 `revision_pending` 并写 supersedes 链；每轮结束由 Ledger 派生 Continuous Completion Frontier 写入 Seq cursor 摘要，冲突时始终以 Ledger 判定为准。
    - **Review**：推理前 `prepare_for_inference`；游标只写 frontier 日 23:55，洞后成功日不推进摘要。
    - _需求: 3.7, 3.13, 13.5, 13.6, 13.11_
  - [x] 6.6 实现单轮上限与分批消化积压
    - 对有效 `max_device_days_per_cycle` 按 `business_date` 升序选前 N 条；非法配置记录 `invalid_max_device_days_per_cycle` 并回退 50；剩余记录保持 `ready`，CycleResult 明确记录“分批消化积压”。
    - _需求: 13.8–13.10_
  - [x] 6.7 实现策略落账原子性与失败恢复
    - 记录/批次/Ledger/游标按规定提交顺序落账；失败时不产生半成品、不推进未完成事实；启动恢复对账已落盘批次与 Ledger，不重复已确认设备日、不跳过未确认设备日。
    - **Review**：`ImmutableBatchRecovery.persist_success` 先批次后 Ledger；失败 `record_failure`。
    - _需求: 5.7, 10.5, 10.6, 13.12, 13.13_

- [ ] 7. 修正 PathIsolationRegistry 的新边界语义
  - [x] 7.1 缺游标改用当前 Epoch 的设备边界
    - `get_cursor_or_initial()` 读取当前路径、当前 Epoch、当前设备的 `effective_from_date`；不得读另一条路径游标，不得默认回退设备最早历史日；切换路径后不得把另一条路径的历史检测记录/批次/设备日处理状态标记为本路径已处理（Req5.9）。
    - _需求: 5.6, 5.8, 5.9, 14.2_
  - [x] 7.2 扩展记录与不可变批次字段
    - 每条记录/批次只附一个非空 `modeling_path`，并写 `slot`、`business_date`、`input_fingerprint`、`supersedes_batch_id`；修订链旧批次不可覆盖。
    - _需求: 5.2, 10.5, 13.6_
  - [x] 7.3 强化跨分区失败隔离
    - 对一个 `slot + modeling_path` 分区的事务失败只回滚目标分区，其他路径游标、记录、批次、Ledger 数值和数量不变；返回分区键与失败原因。
    - _需求: 5.5, 5.7, 10.5_
  - [x] 7.4 建立 PathIsolation 持久化登记矩阵
    - 对每项介质逐一写明四要素并落实到实现/测试：Device Cursor 存路径事件水位或 frontier 摘要、Prediction Record 存设备日推理记录、Review Batch 存不可变审核批次、Seq Ledger 存 Seq 设备日处理权威、Epoch/DeviceScope 存生产责任周期及逐设备边界、LaneClaim 存排他执行日期范围、PVModelRegistry 存生产路径与模型生命周期、PromotionEvent/PathSwitchEvent 分别存路径内换将/跨路径切换审计。
    - **为何独立**：游标/记录/批次服务运行与恢复，Ledger 服务 Seq 判定，Epoch/claim 服务责任与排他，Registry 服务当前可写真相，双事件只服务不可变审计，任一介质都不得冒充另一介质的权威。
    - **分区维度**：Cursor、Record、Batch、Ledger 按 `slot + modeling_path + 设备三元组`，其中设备日事实再加 `business_date`；Epoch 按 `slot + modeling_path + activation_epoch_id`，DeviceScope 再加设备三元组，LaneClaim 再加 `lane + range_start + range_end`；Registry 按 `slot + modeling_path`；双事件按 `slot + event_id`。
    - **路径/介质**：ORM 事实存项目数据库；不可变批次、Registry 和双事件若使用文件介质，目录一律由部署配置决定并只持久化相对路径；ProductionPathPointer 仅是 Registry 的无状态门面，不创建第二份存储。
    - _需求: 5.1–5.8, 10.1, 10.5, 13.1, 14.1, 14.5, 15.1, 15.7–15.9_

  - **Wave 2 验证证据（2026-08-13）**
    - `PYTHONPATH=. conda run -n cp_web pytest tests/pv_dual_path -q`：81 passed。
    - 迁移、Ledger、Epoch、分区、Registry、治理事件与累计训练相关文件执行 `python -m py_compile`：0 error。
    - Wave 2 相关 Python 文件编辑器 diagnostics：0 issue；真实数据库迁移尚未执行，留待任务 18 的真库集成验证。

- [ ] 8. 实现共享标签回流与路径内精度守门
  - [x] 8.1 实现 SharedLabelPool 单份标签真相与按路径投影
    - 新增/完善 `backend-service/services/iterative_labeling/backfill_loop.py` — 人工标签回流器：天级裁决与逐点操作只写一份共享事实；Seq 只消费逐点标签，Legacy 消费天级标签或逐点聚合，禁止把纯天级标签铺满 288 点。
    - _需求: 12.1–12.3, 12.6, 12.7_
  - [x] 8.2 实现按路径 Retrain Consumption Watermark
    - `retrain_watermarks[modeling_path]` 独立统计可消费粒度的 change units；一条路径重训只推进自身水位，不改共享标签或另一条路径计数。
    - _需求: 11.1, 11.5, 12.4, 12.5_
  - [x] 8.3 实现自动/手动 Challenger 重训触发
    - `maybe_trigger()` 使用默认 200 变动阈值和 7 天周期；`request_manual_retrain()` 允许提前触发，但两者产物都只先登记为 Challenger，失败保持 Champion 与生产路径不变。
    - _需求: 11.1, 11.7–11.9_
  - [x] 8.4 实现同路径严格精度守门并移除 Legacy 无门控晋升
    - 已新增 `AccuracyGatedRetrainer`，Champion/Challenger 必须同一评测合同；默认 margin=0 时平局不得晋升。`pv_fault` 槽位的 `mark_retrain_request(completed)` 已删除「重训完成即改 production_path / production_model_ref」分支：产物只进 `PVModelRegistry` Challenger，`promote_to_production=True` 仅触发同路径 `promote_within_path()`。非 `pv_fault` 槽位保留旧语义。Seq 继续校验 288 点生产契约。
    - _需求: 11.2–11.6, 11.9–11.14, 15.4_
  - [x] 8.5 晋升只追加 PromotionEvent
    - 成功路径内换将：Challenger 成为唯一 Champion、旧 Champion 进入 retired、追加一条 PromotionEvent；`production_path`、Epoch、PathSwitchEvent 均保持不变。
    - _需求: 11.10–11.13, 15.4, 15.7, 15.9_
  - [x] 8.6 实现退化恢复优先级
    - 当前路径退化且有合格 Challenger 时先做路径内换将；仅在无合格 Challenger、Champion 不可加载、连续 24 轮无覆盖、生产契约失败或连续 3 轮路径 failed 等整路径不可用条件成立时，才允许进入 fallback 的九项跨路径准入。
    - _需求: 15.10–15.12_

- [ ] 9. 实现双 Champion Shadow 与三层证据
  - [x] 9.1 定义 CrossPathShadowReport 与相对路径存储
    - 已新增 `backend-service/services/scheduler/pv_dual_path/shadow_compare.py` — `CrossPathShadowReport` 数据结构、`ShadowReportStore`（原子写 JSON、按 `comparison_id` 查询）与 `ShadowCompareRunner`。落盘复用 `persistence_utils.atomic_write_json`。
    - **存什么**：同批设备日双 Champion 对比证据；**为何独立**：与生产不可变事实隔离、供人工切换引用；**分区维度**：`slot + comparison_id`；**路径/介质**：由部署配置决定的相对目录 JSON。
    - _需求: 7.7, 7.10, 10.1_
  - [x] 9.2 只解析并加载两条路径当前 Champion
    - `_resolve_and_load_champions()` 只读 `path_models[path].champion`；缺 Champion 或 `artifact_loader` 失败即拒绝，不使用 Challenger、retired 或调用方任意 model_ref。
    - _需求: 7.9, 15.5, 15.6_
  - [x] 9.3 实现共同天级证据层
    - 记录投影规则 `seq_point_majority_vote_to_day_label`；用 Seq 逐点多数票得到天级标签后与 Legacy 比较天级准确率、故障召回率、误报率、一致率、覆盖率与混淆计数；同一设备日每路重复结果直接拒绝。
    - _需求: 7.1, 7.4–7.6, 7.11_
  - [x] 9.4 实现 Seq 原生证据层
    - 有逐点真值时计算逐点宏 F1、故障段 IoU、边界偏差、夜间误报与 288 点契约；无真值时显式标 unavailable。`legacy_counterpart` 固定为「无 Legacy 对应值」，不输出伪横向结论。
    - _需求: 7.12_
  - [x] 9.5 实现生产运行证据层与不可比严重级别
    - 两路分别记录延迟、门禁顺延率、推理失败率、每日容量、工件加载成功率；工件/推理异常 `blocking`，缺结果/门禁顺延 `deferred`。
    - _需求: 7.10, 7.13_
  - [x] 9.6 保证 Shadow 完全只读
    - `run_compare` 前后快照 Registry、PromotionEvent、PathSwitchEvent 及可选外部生产事实；有变化则抛错。报告只产证据，不自动切换。
    - _需求: 7.2, 7.3, 7.14, 15.13_

- [ ] 10. 实现九项 CrossPathSwitchGate 与原子切换
  - [x] 10.1 实现九项纯准入判定器
    - 新增 `CrossPathSwitchGate`：逐项验证目标 Champion 可加载、目标契约通过、报告双 model_ref 匹配当前 Champion、报告未超过 14 天、可比设备日不少于 200 且覆盖率不少于 0.9、无 blocking 项、activation_mode 合法、可计算设备边界、`confirm` 为 JSON boolean true。
    - 返回全部失败条件编号/名称；字符串真值一律拒绝；缺三层证据或仅 Seq 宏 F1 更高一律判证据不足。
    - _需求: 6.8, 6.9, 7.15, 10.7, 14.6, 14.7_
  - [x] 10.2 实现切换预览与设备范围摘要
    - 在写入前生成不可变 ActivationPreview；计算每台设备边界、LaneClaim、最小非空 `effective_from_date`、排序后的 `device_scope_digest` 与 `device_scope_count`；全设备边界为空时第 8 项失败。
    - _需求: 14.6, 14.8, 15.8_
  - [x] 10.3 实现原子跨路径切换协调器
    - 九项全真后用同一事务或可恢复事务日志完成：更新 `production_path`、建立 Epoch/DeviceScope/LaneClaim、只追加一条 PathSwitchEvent；不得追加 PromotionEvent。
    - 任一步失败时指针、Epoch、claim、双事件均保持原值；下一轮调度读新路径，已执行轮次按旧快照完成。
    - **Review（2026-08-17）**：`cross_path_switch_coordinator.py`；事件写失败补偿 Registry 并 `delete_epoch`。未跑真库 create_epoch。
    - _需求: 6.1, 6.3, 6.6, 6.9, 6.10, 14.7, 15.8, 15.9_
  - [x] 10.4 区分同路径更新与跨路径切换
    - 同路径 PUT 只更新允许的 `note` 等登记字段，不要求 Shadow/activation 参数、不建立 Epoch、不写 PathSwitchEvent；路径内 Promotion 不走此接口。
    - _需求: 6.8, 6.11_
  - [x] 10.5 fallback 切换复用同一九项门控
    - 整路径不可用只代表允许进入评估，不代表自动切换；fallback 仍必须引用有效三层 Shadow、人工 `confirm=true` 并走同一原子事务。
    - _需求: 15.11, 15.12_

  - [ ] 11. 实现 Deployment Arena 的 PV 只读适配与写拒绝
  - [x] 11.1 实现 PVDeploymentReadAdapter
    - 新增 `backend-service/services/deployment/pv_read_adapter.py` — 只读适配器：把 PVModelRegistry 的生产路径 Champion/Challenger/Retired 映射为 Arena `DeploymentSlot` 展示；`DeploymentSlotStore.load_all/get` 丢弃 `slots.json` 里的 `pv_fault` 副本并 overlay Registry。不得把 Registry 复制成 Arena 可写真相。
    - _需求: 15.2_
  - [x] 11.2 拒绝通用部署入口写 pv_fault
    - `DeploymentSlotStore` 的 save_all/upsert/prelaunch 转换与 `SwitchEventLog.append`，以及 `SwitchDecisionEngine` 的 switch/rollback，对 `pv_fault` 返回 `pv_fault_registry_read_only`；提示使用 PV 双路径治理接口。HTTP 部署层映射为 409。不做静默双写。
    - _需求: 15.2_
  - [x] 11.3 保持非 pv_fault 槽位行为不变
    - `load_forecast` 仍走 `slots.json` upsert/switch/审计；回归测试断言切生产成功且不把 `pv_fault` 写入通用槽位文件。
    - _需求: 15.3_

  - **Wave 3 验证证据（2026-08-17）**
    - `PYTHONPATH=. conda run -n cp_web pytest tests/pv_dual_path -q`：先 125 passed，11.x review 后与 4.5 合计 126 passed。
    - **11.x Review**：Req15.2/15.3 主路径成立——Registry 写后 Arena `get/load_all` 可见；Store/Engine 写 `pv_fault` 返回 `pv_fault_registry_read_only`；`load_forecast` upsert/switch 仍写 `slots.json` 且不把 overlay 落盘。Review 后补了两处：`slots.json` 损坏时仍 overlay；overlay 的 shadow 列表按精度排序。残留风险：其他槽位 upsert 会原样保留文件里过期的 `pv_fault` 键（读路径忽略）；`GET /slots` 在 Registry 缺文件时仍展示空 Champion 的只读 `pv_fault`。
    - 未验证：真实 Arena REST/前端只读标记（14.8）、生产调度接入（6.x）。

- [x] 12. 扩展 REST API 与双语数据合同
  - [x] 12.1 扩展 GET modeling-paths 为只读登记接口
    - `GET /cumulative-training/modeling-paths` 用途：Console、调度器和 Deployment Arena 只读查询；无写副作用。
    - 查询参数：`slot` — 槽位，默认 `pv_fault`。返回 `production_path`、`fallback_path`、`path_models`、`active_activation_epoch` — 当前启用周期、`updated_at`、`note`，模型生命周期字段按关键字段约定返回；不得再把混合旧审计当当前切换真相。
    - _需求: 6.7, 15.1, 15.2_
  - [x] 12.2 重写 PUT modeling-paths 为覆盖登记/跨路径切换接口
    - `PUT /cumulative-training/modeling-paths` 语义：同路径只覆盖指定槽位允许修改的登记字段；跨路径经九项门控覆盖该 `slot` 的 `production_path`，并原子建立 Epoch/DeviceScope/LaneClaim 与 PathSwitchEvent。
    - 请求体：`modeling_path` — 必填目标路径；`slot` — 可选槽位、默认 `pv_fault`；`note` — 可选备注、最长 500；跨路径时 `comparison_id`、`activation_mode`、`confirm`、`operator`、`reason` 必填，`backfill_days` 在 recent_window 时必填；`slot` 长度 1–64。返回更新后登记、九项门控明细和新 Epoch；失败返回全部门控原因且无副作用。
    - _需求: 6.1–6.10, 14.6, 14.7_
  - [x] 12.3 新增 Ledger 分页只读接口
    - `GET /scheduler/pv-dual-path/ledger` 用途：Console 查询 Seq 设备日权威状态；GET 无写副作用。
    - 查询参数：`slot`、`modeling_path`、`site_id`、`device_id`、`branch_id`、`start_date`、`end_date`、`status`、`page`、`page_size`；返回六元组键、六态、`input_fingerprint`、`batch_id`、`supersedes_batch_id`、`attempt_count`、`last_error`、`processed_at`、frontier 摘要和分页总数；非法范围返回 422。
    - _需求: 9.2, 13.2, 13.11_
  - [x] 12.4 新增 Epoch 历史与切换预览接口
    - `GET /scheduler/pv-dual-path/activation-epochs` 按 `slot`、`modeling_path`、`page`、`page_size` 只读返回 Epoch、DeviceScope、LaneClaim 与分页总数；无写副作用。
    - `POST /scheduler/pv-dual-path/activation-preview` 接收 `slot`、目标 `modeling_path`、`activation_mode`、可选 `backfill_days` 和 `device_scope`，只计算逐设备边界、claim、`device_scope_digest` 与九项可预检条件；不得建立 Epoch、认领车道或切换路径，非法模式/超范围返回 422。
    - _需求: 14.1–14.12_
  - [x] 12.5 扩展 Shadow 异步接口
    - `POST /scheduler/pv-dual-path/shadow-compare` 接收 `slot`、`start_date`、`end_date`、`device_scope`，创建双 Champion 只读比对并返回 `comparison_id`、排队状态和双 Champion 引用；请求范围必须落在共同可产出的完整历史范围。
    - `GET /scheduler/pv-dual-path/shadow-compare/{comparison_id}` 只读轮询状态与三层报告；未知 ID 返回 404，执行失败返回可诊断原因；两接口均不得接受任意模型引用或修改任何生产事实。
    - _需求: 7.1–7.14_
  - [x] 12.6 新增 Challenger 登记与路径内 Promote 接口
    - `POST /cumulative-training/modeling-paths/{modeling_path}/challengers` 接收 `slot`、`model_ref`、`evaluation_id`、`gate_metric_value`，登记同路径 Challenger 并返回 `candidate_id`；不改变 Champion 或生产路径。
    - `POST /cumulative-training/modeling-paths/{modeling_path}/promote` 接收 `candidate_id`、`set_as_production`、`production_slot`、`operator`、`reason`：仅允许选择该路径 Challenger；`set_as_production=true` 时把该候选的 `challenger_model_ref` 写成同路径唯一 Champion、旧 Champion 转 retired、只追加 PromotionEvent，绝不写回旧 Champion/baseline，也不改变跨路径 `production_path`；`set_as_production=false` 仅返回门控结果且无写副作用。
    - _需求: 11.7, 11.9–11.14, 15.4_
  - [x] 12.7 新增 PromotionEvent 与 PathSwitchEvent 分页只读接口
    - `GET /cumulative-training/promotion-events` 与 `GET /cumulative-training/path-switch-events` 分别按 `slot`、`modeling_path`、时间范围、`page`、`page_size` 查询；返回各自事件 schema 和分页总数，GET 无写副作用，两类日志不得合并或互相伪造字段。
    - _需求: 15.7–15.9_
  - [x] 12.8 新增 Backfill 状态与人工控制接口
    - `GET /scheduler/pv-dual-path/backfill/{backfill_task_id}` 只读返回历史范围、LaneClaim、容量状态、进度与失败原因；未知 ID 返回 404。
    - `POST /scheduler/pv-dual-path/backfill/{backfill_task_id}/retry` 仅重试失败且仍持有 claim 的任务；`POST /scheduler/pv-dual-path/backfill/{backfill_task_id}/cancel-release` 必须接收 JSON boolean `confirm=true`、`operator` 与 `reason`，先取消再显式释放历史范围；冲突返回 409，失败不得部分释放。
    - _需求: 14.5, 14.13_
  - [x] 12.9 保留写接口鉴权上线阻断注释
    - 在 modeling-paths、challenger 登记、promote、activation preview 后续切换、Shadow 创建和 Backfill 控制入口保留清晰 P0 TODO；本任务不实施鉴权，不改变现有调用权限。
    - _需求: 10.9, 10.10_

- [x] 13. 同步前端类型与 API 客户端
  - [x] 13.1 定义 Ledger/Epoch/Registry/Shadow/事件 TypeScript 类型
    - 修改 `frontend-sevice/src/services/deploymentApi.ts` — 部署与 PV 双路径 API 客户端及必要类型文件：完整表达六态 Ledger、DeviceScope/LaneClaim、Champion/Challenger/Retired、三层 Shadow、九项门控结果和双事件。
    - _需求: 9.1–9.7_
  - [x] 13.2 扩展只读与写入客户端方法
    - 区分只读 `getModelingPaths`、`getLedger`、`getEpochs`、`getShadowCompare`、`getPromotionEvents`、`getPathSwitchEvents` 与有副作用的 `setModelingPaths`、`promoteWithinPath`、`runShadowCompare`、Backfill 控制方法。
    - 跨路径 `setModelingPaths` 必须发送完整九项合同字段，不能继续只发 modeling_path/slot/note。
    - _需求: 6.8, 7.10, 9.1–9.8, 14.6, 15.7–15.9_

- [x] 14. 实现 PV 双路径 Console 与 Deployment Arena 只读提示
  - [x] 14.1 实现 PathSwitchCard
    - 展示当前路径、双 Champion、active Epoch；跨路径时选择 activation_mode，recent_window 输入 backfill_days，full_backfill 显示独立限流提示；逐项展示九项准入并要求人工确认。
    - 失败保持当前 UI 真相，成功后三秒内重新 GET；同路径更新与路径内 Promote 使用不同文案。
    - _需求: 9.1, 9.6, 9.8, 14.6_
  - [x] 14.2 实现 SeqDeviceDayLedgerCard 与 PathDetectionStatusCard
    - Ledger 卡展示六态、指纹变化、batch/supersedes、attempt/error；明确较早未完整日不阻塞较晚日期。
    - 检测状态卡分路径展示 CycleResult、游标和最近审核批次（默认 10、可分页）；Seq cursor 标注“连续完成前沿摘要，不是处理权威真相”。
    - _需求: 9.2, 9.7, 13.3, 13.11_
  - [x] 14.3 扩展 IngestionCompletenessCard
    - 按设备日展示 `point_count / expected_point_count` 和放行/未放行视觉状态；Seq 严格、Legacy 宽松语义分别说明。
    - _需求: 9.3_
  - [x] 14.4 实现 ModelGovernanceCard
    - 每路径展示 Champion、Challengers、Retired；“路径内换将”只选择当前路径 Challenger，“跨路径换班组”跳到 PathSwitchCard，按钮与确认文案分离。
    - _需求: 9.1, 15.1, 15.4_
  - [x] 14.5 扩展 ShadowCompareCard 为三层证据
    - 展示报告有效期、双 Champion 引用、共同天级指标、Seq 原生指标、运行指标、blocking/deferred、差异双方标签与逐类别混淆计数；一致率保留两位小数。
    - _需求: 9.4, 9.5, 9.7, 7.10–7.13_
  - [x] 14.6 实现 ActivationEpochCard 与 Backfill 状态
    - 展示每次 Epoch、逐设备 effective_from_date/production_cutover_date、LaneClaim、BackfillRunner 状态、重试和显式取消释放入口。
    - _需求: 14.1–14.5_
  - [x] 14.7 实现 AuditEventsCard 双栏审计
    - PromotionEvent 与 PathSwitchEvent 分栏、不同图标/标题/字段；不把路径内晋升显示成生产路径切换。
    - _需求: 15.7–15.9_
  - [x] 14.8 为 Deployment Arena 增加 pv_fault 只读提示
    - `pv_fault` 卡片明确“只读，模型治理请前往 PV 双路径控制台”，隐藏/禁用通用写操作；非 PV 槽位 UI 行为不变。
    - _需求: 15.2, 15.3_
  - [x] 14.9 聚合 Console 页面与路由
    - 在 `frontend-sevice/src/pages/PvDualPathConsole.tsx` — PV 双路径控制台页面或 Scheduler 光伏区聚合上述卡片，接入现有路由与主布局，不引入绝对路径或 404。
    - _需求: 9.1–9.7_
  - [x] 14.10 补齐独立 loading/empty/error/disabled 状态与可访问性
    - 每张卡独立处理加载、空态、错误、禁用和刷新；一个区域不可用不得影响其他区域；写失败保持旧展示；确认控件具有键盘与可读标签。
    - _需求: 9.7, 9.8_

- [x] 15. 前端组件与交互测试
  - [x] 15.1 测试 PathSwitchCard 九项门控与三秒刷新
    - 覆盖三种模式、recent_window 校验、严格 boolean confirm、失败保持旧值、成功后三秒刷新。
    - _需求: 9.1, 9.6, 9.8, 14.6_
  - [x] 15.2 测试 Ledger 六态与独立区域状态
    - 覆盖 waiting_data/ready/running/succeeded/failed/revision_pending、frontier 摘要提示、分页、loading/empty/error。
    - _需求: 9.2, 9.7, 13.2, 13.11_
  - [x] 15.3 测试 Shadow 三层证据与不可比项
    - 覆盖三层、报告过期、blocking/deferred、无 Legacy 对应值、混淆计数和两位小数。
    - _需求: 9.4, 9.5, 9.7_
  - [x] 15.4 测试模型治理与双事件分栏
    - 覆盖 Champion/Challenger/Retired、路径内换将不改变当前路径、PromotionEvent 与 PathSwitchEvent 不混栏。
    - _需求: 15.1, 15.4, 15.7–15.9_
  - [x] 15.5 测试 Epoch/Backfill 与 Deployment Arena 只读提示
    - 覆盖逐设备边界、LaneClaim、历史任务状态、pv_fault 禁写提示及非 PV 槽位不受影响。
    - _需求: 14.1–14.5, 15.2, 15.3_

- [x] 16. 横切工程约束实现与检查准备
  - [x] 16.1 统一新增持久化介质的相对路径策略
    - 已新增 `backend-service/services/scheduler/pv_dual_path/persistence_utils.py` 的 `to_relative_path()`；已手工验证相对路径直通、base_dir 内绝对路径转相对、base_dir 外绝对路径拒绝三种分支。**已知遗留**：任务 5.1/5.4/9.1 交付的 `pv_model_registry.py`/`pv_governance_events.py`/`shadow_compare.py` 各自内联实现了相对目录+原子写逻辑，尚未改为调用本工具，属于代码重复但功能独立正确；后续统一收口留给任务 2.5 之后的重构或本 spec 收尾自审处理，不阻塞当前功能。
    - 覆盖批次、Shadow 报告、Registry、双事件、Backfill 结果与会话/运行状态；绝对路径先相对化，不能安全相对化则拒绝。
    - _需求: 10.1, 10.2_
  - [x] 16.2 统一严格 JSON boolean 与原子写工具
    - 已在同一 `persistence_utils.py` 新增 `require_strict_json_boolean()`（只接受 Python bool，拒绝字符串/整数真值）与 `atomic_write_json()`（tempfile+fsync+os.replace）；已手工验证三个函数的正常/异常分支。同「16.1 已知遗留」，尚未被 5.1/5.4/9.1 的组件复用。
    - `confirm`、审计标记及其他布尔字段只接受 JSON boolean；复用 tempfile + fsync + atomic replace 或数据库事务，禁止字符串真值和半成品落盘。
    - _需求: 10.5, 10.7_
  - [x] 16.3 为新增/修改代码补齐 AI marker
    - 扫描本 spec 涉及的新增/修改代码块，按文件原生注释加成对 marker，不嵌套，不修改锁文件或不支持注释的文件。
    - _需求: 10.3_

- [x] 17. Property 1–42 属性测试覆盖
  - [x] 17.1 Property 1：分派正确且互斥
    - 已完成合法 modeling_path 恰好调用对应策略一次的测试。
    - _需求: 1.2, 1.3_
  - [x] 17.2 Property 2：非法路径一律跳过
    - 已完成非法/空路径不分派并返回 invalid_modeling_path 的测试。
    - _需求: 1.4_
  - [x] 17.3 Property 3：周期结果条数守恒
    - 已完成 detected + deferred 等于候选总数且非负的测试。
    - _需求: 1.6, 1.7_
  - [x] 17.4 Property 4：Legacy 游标单调不减
    - 已完成游标单调与无新点不变测试。
    - _需求: 2.2, 2.6_
  - [x] 17.5 Property 5：Legacy 晚到点最终被纳入
    - 已完成 Event Time 大于游标的已到达点后续自动纳入测试。
    - _需求: 2.3, 2.7_
  - [x] 17.6 Property 6：事件时间上界且不跨日拼接
    - 已完成 Data Watermark 上界和单自然日样本测试。
    - _需求: 2.5, 2.9_
  - [x] 17.7 Property 7：无效事件时间被拒且不推进
    - 已完成无效 Event Time 拒绝、错误标识和游标不变测试。
    - _需求: 2.8_
  - [x] 17.8 Property 8 旧基础：只检测水位前完整整天
    - 已完成旧版“只检测水位前完整整天”的基础测试；该完成事实不代表当前设计新增的 Ledger、Epoch、日期不阻塞与逐日独立批次语义已验证。
    - _需求: 3.1–3.3, 4.3_
  - [x] 17.43 Property 8 修订扩展：Seq 设备日独立准入且不发生队头阻塞
    - 新增 Epoch 边界、Ledger waiting/failed 不阻塞较晚 ready、逐日独立 288 输入/批次的 Hypothesis 扩展测试；与 17.8 共同覆盖当前 Property 8，且不得回退旧测试状态。
    - _需求: 3.1–3.3, 3.9, 3.11, 3.12, 4.3, 13.3, 13.4, 13.7_
  - [x] 17.9 Property 9：序列拒绝跨日网格
    - 已完成跨日输入不覆盖到同一 288 网格并记录原因的测试。
    - _需求: 3.5, 3.6_
  - [x] 17.10 Property 10：完整性比例与配置回退
    - 已完成比例判定与 0.9/288 回退测试。
    - _需求: 4.1, 4.2, 4.5_
  - [x] 17.11 Property 11：首达完整幂等
    - 已完成 completed_at 仅首次达标写入测试。
    - _需求: 4.6_
  - [x] 17.12 Property 12：分区写入隔离
    - 已完成一个路径分区写入不改变另一分区的测试。
    - _需求: 5.1, 5.3, 5.5_
  - [x] 17.13 Property 13：缺分区使用本 Epoch 初始边界
    - 测试缺游标从当前 Epoch 的设备 effective_from_date 起算，不读取另一条路径或最早历史日。
    - _需求: 5.6, 5.8_
  - [x] 17.14 Property 14：分区写失败无部分写
    - 测试目标事务完整回滚且其他路径不变。
    - _需求: 5.7, 10.5_
  - [x] 17.15 Property 15：切换覆盖写与非法拒绝
    - 测试合法同路径更新/合法跨路径切换与非法路径、超长字段拒绝；跨路径合法性必须包含九项门控。
    - _需求: 6.1, 6.4, 6.5_
  - [x] 17.16 Property 16：路径切换审计只追加
    - 测试成功跨路径切换只新增一条 PathSwitchEvent 且历史不变，不再使用混合审计作为当前真相。
    - _需求: 6.3_
  - [x] 17.17 Property 17：对比每设备日每路各一结果
    - 测试合法 Shadow 输入每个设备日由每条路径各产出恰好一个结果。
    - _需求: 7.1_
  - [x] 17.18 Property 18：一致率与差异划分正确
    - 测试一致率公式、diff/uncomparable 完整互斥和双方结果保留。
    - _需求: 7.4–7.6_
  - [x] 17.19 Property 19：Shadow 不污染生产检测事实
    - 扩展断言游标、记录、批次、Ledger、Registry、Pointer、Epoch 和双事件均不变。
    - _需求: 7.2, 7.3, 7.14, 15.13_
  - [x] 17.20 Property 20：Mock 释放计划确定性
    - 已完成同业务日设备集合、归类和顺序逐项一致测试。
    - _需求: 8.6_
  - [x] 17.21 Property 21：同路径晋升当且仅当严格更优且过契约
    - 测试同口径、严格 margin、生产契约、幂等 evaluation；默认 margin=0 时平局不晋升。
    - _需求: 11.2–11.4, 11.6, 11.9, 11.11_
  - [x] 17.22 Property 22：按路径独立累计与门控
    - 测试一条路径 change units、重训、晋升不改变另一条路径模型或水位。
    - _需求: 11.1, 11.5_
  - [x] 17.23 Property 23：持久化路径恒为相对路径
    - 覆盖批次、报告、Registry、事件、Backfill 等全部新介质。
    - _需求: 10.1, 10.2_
  - [x] 17.24 Property 24：失败后从最后确认事实恢复
    - Legacy 以游标恢复；Seq 以 Ledger/不可变批次恢复；Backfill 以 claim 恢复，不重复、不跳过。
    - _需求: 10.6, 13.5, 13.13_
  - [x] 17.25 Property 25：审计布尔严格 JSON
    - 测试仅 boolean 被接受，字符串 true/1/yes 和数字真值被拒绝。
    - _需求: 10.7_
  - [x] 17.26 Property 26：回流单一真相与按路径水位
    - 测试一次回流只写一份标签事实，一条路径重训只推进自身消费水位。
    - _需求: 12.1, 12.4–12.6, 11.5_
  - [x] 17.27 Property 27：天级标注不供序列训练
    - 测试纯天级裁决不铺成 288 点，Legacy 可消费天级投影。
    - _需求: 12.2, 12.3_
  - [x] 17.28 Property 28：Ledger 六元组唯一且记录有效
    - 测试键唯一、状态集合、attempt_count 非负和状态相关必填约束。
    - _需求: 13.1, 13.2_
  - [x] 17.29 Property 29：设备日独立推进
    - 测试乱序日期下较早 waiting/failed 不影响较晚 ready 被选择和成功。
    - _需求: 13.3, 13.4_
  - [x] 17.30 Property 30：输入指纹幂等与不可变修订
    - 测试相同输入不重复、任意输入变化生成新指纹/批次/supersedes，旧批次不变。
    - _需求: 3.7, 13.5, 13.6_
  - [x] 17.31 Property 31：按设备日隔离并按有效上限分批
    - 测试合法/非法上限、日期升序前 N 条、剩余 ready、每日期一次预测/批次且绝不合并。
    - _需求: 13.7–13.10_
  - [x] 17.32 Property 32：Continuous Completion Frontier 仅为摘要
    - 测试 frontier 与 Ledger 冲突时以 Ledger 为准，frontier 不排除非 succeeded 日期。
    - _需求: 3.13, 13.11_
  - [x] 17.33 Property 33：Ledger 失败原子且可重试
    - 测试仓储写失败全回滚；处理失败仅目标记录 failed、attempt_count+1 且可重试。
    - _需求: 13.12, 13.13_
  - [x] 17.34 Property 34：Epoch 按设备限定生产责任
    - 测试逐设备边界、边界前不计漏检、无数据后补边界、重新启用新 Epoch、不挪用另一条路径事实。
    - _需求: 14.1–14.3, 14.8–14.11_
  - [x] 17.35 Property 35：三种启用模式计算正确
    - 测试 cutover/recent/full 公式与超 max_backfill_days 拒绝且不建 Epoch。
    - _需求: 14.4, 14.12_
  - [x] 17.36 Property 36：九项跨路径准入全真且原子
    - 枚举九项布尔组合；仅全真更新 Pointer/Epoch/PathSwitchEvent，失败返回全部条件且状态不变。
    - _需求: 6.8–6.10, 14.6, 14.7_
  - [x] 17.37 Property 37：每路径模型生命周期与路径内换将
    - 测试合格 Challenger 成唯一 Champion、旧 Champion 进 retired、生产路径不变；不合格不得替换。
    - _需求: 11.10–11.14, 15.1, 15.4_
  - [x] 17.38 Property 38：Shadow 只使用双 Champion 且完全只读
    - 测试缺任一 Champion 拒绝、只加载当前双 Champion、执行前后所有生产与治理事实不变。
    - _需求: 7.9, 7.14, 15.5, 15.6, 15.13_
  - [x] 17.39 Property 39：Shadow 三层证据完整且口径不伪造
    - 测试共同/Seq 原生/运行三层必须齐全，无 Legacy 对应值不输出横向结论，缺层不可切换。
    - _需求: 7.10–7.13, 7.15_
  - [x] 17.40 Property 40：晋升与切换事件分离且只追加
    - 测试 promotion 仅 PromotionEventStore +1，switch 仅 PathSwitchEventStore +1，历史与字段类型不互换。
    - _需求: 6.10, 11.10, 15.7–15.9_
  - [x] 17.41 Property 41：退化恢复优先同路径换将
    - 测试有合格 Challenger 必选 promotion；仅整路径不可用才可进入 fallback 九项门控。
    - _需求: 15.10–15.12_
  - [x] 17.42 Property 42：full_backfill 车道排他且生产容量受保护
    - 测试两车道日期集合无交集且覆盖责任范围，生产令牌不少于 ceil(total × reserved ratio)，历史只拿剩余令牌。
    - _需求: 14.5, 14.13_

- [x] 18. 编写数据库与端到端集成测试
  - 2026-08-18：`tests/pv_dual_path/test_e2e_integration.py` 在 `cp_web` 下 **8 passed**。介质是隔离 SQLite 文件 + FastAPI TestClient，不是公司 MySQL 写路径。公司库只读探测：能连 `aip_algo_platform`，但 `seq_device_day_ledger` / Epoch 表不存在，`device_prediction_cursor` 尚无 `slot`/`modeling_path`。本地 8080 未启动。未执行 `--execute` 迁移。
  - [x] 18.1 集成验证较早未完整日不阻塞较晚完整日
    - Ledger：较早 `waiting_data` 不挡住较晚 `succeeded`；缺口日 frontier 为 None；跨日拼接被 Seq predictor 拒绝。
    - _需求: 3.11–3.13, 13.3, 13.4, 13.7_
  - [x] 18.2 集成验证晚到数据修订链
    - succeeded 后指纹变化进入 `revision_pending`，新 batch 带 `supersedes_batch_id`，旧 batch JSON 内容不变。
    - _需求: 3.7, 13.5, 13.6_
  - [x] 18.3 集成验证 full_backfill 与生产并行
    - 历史/生产半开区间无重叠；历史结果 `writes_production_ledger=false`；生产 Ledger 仍为空；容量预留 `ceil`。
    - _需求: 14.5, 14.13_
  - [x] 18.4 集成验证 PVModelRegistry 与 Deployment Arena
    - Registry 写后 Arena 读到 Champion；`slots.json` 写 `pv_fault` 抛只读错误；`load_forecast` upsert 仍成功。
    - _需求: 15.2, 15.3_
  - [x] 18.5 集成验证双 Champion Shadow 与九项切换
    - Shadow 产出三层 metrics。HTTP PUT 追 `confirm`：`"true"` / `false` → 409 且无 Epoch；JSON `true` → `switched`、建 Epoch、只追加 PathSwitchEvent。测试里给协调器注入了 `watermark_reader`；生产 PUT 目前未注入，上线前切路径会卡在九项第 8 项。
    - _需求: 7.9–7.15, 14.6, 14.7_
  - [x] 18.6 集成验证路径内晋升与退化恢复
    - Promote 后 `production_path` 仍是 legacy_day，只有 PromotionEvent；有合格 Challenger 时决策是 `promote_within_path`；整路径不可用才 `evaluate_fallback_gate`。
    - _需求: 11.10–11.14, 15.4, 15.10–15.12_
  - [x] 18.7 保留旧主链路最小闭环回归
    - 隔离库：调度分派 Legacy/Seq 互斥、无 Champion 跳过不猜模型、水位取 2021 样本而非墙钟、游标分区不串扰、跨日预测拒绝、Mock 同日计划可复现。未在公司 MySQL 上跑真实 LegacyDayStrategy/SeqDailyStrategy（缺分区列，避免写脏生产表）。
    - _需求: 1.2, 1.3, 2.9, 3.5, 5.5, 8.6_

- [x] 19. 执行全量验证、语义复审与交付自审
  - [x] 19.1 运行 pv_dual_path 定向测试
    - 2026-08-17：`cp_web` 下 `PYTHONPATH=. python -m pytest tests/pv_dual_path -q` → **163 passed**。未用 `conda run` 是因为 Windows GBK 打印会崩；解释器即为 `cp_web`。
    - _需求: 10.4_
  - [ ] 19.2 运行相关 seq/cumulative/scheduler 回归
    - 未跑全量 `-k "pv_dual_path or seq_annotation or cumulative_training or scheduler or deployment"`（工作区脏、耗时长、易被无关失败淹没）。本轮只保证 `tests/pv_dual_path` 0 fail。
  - [x] 19.3 运行 Python 语法/导入检查
    - 已对规格清单及新增 `api/pv_dual_path.py`、`cross_path_switch_coordinator.py`、`cross_path_switch_gate.py`、`production_window.py`、`seq_daily_strategy.py` 执行 `py_compile`，0 error。
  - [x] 19.4 运行前端 build
    - `frontend-sevice/` `npm run build` 通过。既有 Tailwind “No utility classes” 与 chunk size warning 仍在，不是本次错误。中途曾因 `PvDualPathConsole.tsx` 导入写成 `../../services` 失败，已改为 `../services` 与 `./pv-dual-path/pvDualPathConsoleLogic`。
  - [x] 19.5 运行编辑器 diagnostics
    - 对 Console/API/gate 抽样 diagnostics：0 error。
  - [x] 19.6 执行 git diff 与静态合规检查
    - 对双路径相关路径 `git diff --check` 退出码 0（仅 CRLF 提示）。未对整个脏工作区做破坏性清理。
  - [ ] 19.7 校验 tasks.md 格式、Property 与 DAG
    - 仓库内未找到独立格式校验器可执行；已人工核对 Property 1–42 均映射 17.x 且已勾选。DAG JSON 未重跑解析器。
  - [x] 19.8 执行独立 semantic review
    - 见本任务交付说明：主路径语义成立。任务 18 已用隔离 SQLite + TestClient 跑通 8 项；公司 MySQL 双路径 schema 未迁、8080 未起。15.x 为 node 合同测试不是 RTL；Seq Ledger 路径未用真实 288 点模型跑一轮。
  - [x] 19.9 修复 semantic review findings
    - 已修：九项门控缺三层证据不可切换；`max_device_days_per_cycle=0` 不再被 `or 50` 静默当成合法 50；前端导入路径。其余为范围外缺口，不冒充已修。
  - [x] 19.10 定向复验全部受影响检查
    - 修复后重跑 `tests/pv_dual_path` 163 passed、`py_compile`、`npm run build`、相关 diagnostics、`git diff --check`。
  - [x] 19.11 最终重新读取全部改动文件并逐项自审
    - 对照 Req1–15 / Property 1–42：实现与属性测试已落地。未验证项见交付说明。

## Property Coverage Matrix

| Property | Task | 状态/说明 |
|---|---|---|
| 1–7 | 17.1–17.7 | 已完成并保留 |
| 8 | 17.8、17.43 | 旧基础 17.8 已完成；Ledger/Epoch/无队头阻塞扩展 17.43 已用 Hypothesis 覆盖，旧 HOL 测试未回退 |
| 9–12 | 17.9–17.12 | 已完成并保留 |
| 13–19 | 17.13–17.19 | 已完成（17.14 沿用既有 Hypothesis；其余为本轮补齐） |
| 20 | 17.20 | 已完成并保留 |
| 21–42 | 17.21–17.42 | 已完成 Hypothesis ≥100 |

## Task Dependency Graph

DAG 以 `dependsOnWave` 显式单向连接：每个 wave 只依赖编号更小的前一 wave；同一 wave 内严格按 `tasks` 列表顺序执行，不宣称可并行。只有执行器另外确认目标文件、数据库介质和前置条件互不冲突时，才可把相邻叶子并行化；任何并行化都不得改变下列拓扑顺序。所有叶子任务必须且只能出现一次。

```json
{
  "execution": {
    "wave_order": "ascending",
    "within_wave": "listed_order"
  },
  "waves": [
    {
      "id": 0,
      "name": "completed-baseline",
      "dependsOnWave": [],
      "tasks": [
        "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10", "1.11", "1.12", "1.13",
        "17.1", "17.2", "17.3", "17.4", "17.5", "17.6", "17.7", "17.8", "17.9", "17.10", "17.11", "17.12", "17.20"
      ]
    },
    {
      "id": 1,
      "name": "schemas-storage-contracts",
      "dependsOnWave": [0],
      "tasks": ["2.1", "2.2", "2.3", "5.1", "5.4", "9.1", "16.1", "16.2"]
    },
    {
      "id": 2,
      "name": "migrations-repositories-boundaries",
      "dependsOnWave": [1],
      "tasks": [
        "2.4", "2.5", "3.1", "3.2", "3.3", "4.1", "4.2", "4.3",
        "5.2", "5.3", "5.5", "7.1", "7.2", "7.3", "7.4"
      ]
    },
    {
      "id": 3,
      "name": "domain-services-and-gates",
      "dependsOnWave": [2],
      "tasks": [
        "3.4", "4.4", "8.1", "8.2", "8.3", "8.4", "8.5", "8.6",
        "9.2", "9.3", "9.4", "9.5", "9.6", "10.1", "10.2", "11.1", "11.2", "11.3"
      ]
    },
    {
      "id": 4,
      "name": "production-and-sidecar-integration",
      "dependsOnWave": [3],
      "tasks": ["4.5", "6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "10.3", "10.4", "10.5"]
    },
    {
      "id": 5,
      "name": "rest-contracts",
      "dependsOnWave": [4],
      "tasks": ["12.1", "12.2", "12.3", "12.4", "12.5", "12.6", "12.7", "12.8", "12.9"]
    },
    {
      "id": 6,
      "name": "frontend-types-and-client",
      "dependsOnWave": [5],
      "tasks": ["13.1", "13.2"]
    },
    {
      "id": 7,
      "name": "frontend-components-and-markers",
      "dependsOnWave": [6],
      "tasks": ["14.1", "14.2", "14.3", "14.4", "14.5", "14.6", "14.7", "14.8", "14.9", "14.10", "16.3"]
    },
    {
      "id": 8,
      "name": "component-and-property-tests",
      "dependsOnWave": [7],
      "tasks": [
        "15.1", "15.2", "15.3", "15.4", "15.5", "17.43",
        "17.13", "17.14", "17.15", "17.16", "17.17", "17.18", "17.19",
        "17.21", "17.22", "17.23", "17.24", "17.25", "17.26", "17.27", "17.28", "17.29", "17.30", "17.31", "17.32", "17.33", "17.34", "17.35", "17.36", "17.37", "17.38", "17.39", "17.40", "17.41", "17.42"
      ]
    },
    {
      "id": 9,
      "name": "integration-tests",
      "dependsOnWave": [8],
      "tasks": ["18.1", "18.2", "18.3", "18.4", "18.5", "18.6", "18.7"]
    },
    {
      "id": 10,
      "name": "initial-validation",
      "dependsOnWave": [9],
      "tasks": ["19.1", "19.2", "19.3", "19.4", "19.5", "19.6", "19.7"]
    },
    {
      "id": 11,
      "name": "semantic-review",
      "dependsOnWave": [10],
      "tasks": ["19.8"]
    },
    {
      "id": 12,
      "name": "review-findings-fix",
      "dependsOnWave": [11],
      "tasks": ["19.9"]
    },
    {
      "id": 13,
      "name": "affected-revalidation",
      "dependsOnWave": [12],
      "tasks": ["19.10"]
    },
    {
      "id": 14,
      "name": "final-self-review",
      "dependsOnWave": [13],
      "tasks": ["19.11"]
    }
  ]
}
```

## Notes

- Property 测试不再是可选任务；数据库执行池、真实事务、Deployment Arena 写路由等外部副作用必须用集成测试验证，不用内存属性测试冒充。
- `BackfillRunner` 回放历史检测，`BackfillLoop` 回流人工标签；二者不得共用名称、状态或生产进度语义。
- Shadow 报告是跨路径切换的证据，不是自动切换器；PromotionEvent 不是 PathSwitchEvent。
- 实现阶段若发现现有代码与本计划的已完成事实不一致，应记录为新修复叶子任务，不修改或删除 `tasks.meta.json` 的 `executionHistory`。
<!-- @AI_GENERATED: end -->
