<!-- @AI_GENERATED -->
# 光伏天/点双产品链需求

> 规格目录沿用历史名称 `pv-fault-realtime-point-path-redesign`，以保留已有引用；产品主线是 `pv_day` 与 `pv_point` 两条完整产品链（形状对齐负荷预测）。算子、模板、profile 可复用，但换数据集只作验证层，不得挡住主链。
>
> 文档状态：2026-08-25 叠加融合需求 0.F；R1–R19 技术约束仍有效
>
> 配套证据：`docs/specs/pv-fault-realtime-point-path-redesign/research.md` — 记录仓库事实、公开数据、竞品和许可边界。
>
> 路径约定：文中仓库路径均相对于项目根目录；代码、配置和持久化结果不得写入本机绝对路径。

### 文档级关键字段速查

| 字段 | 中文含义 |
|---|---|
| `slot` | 唯一路径槽位；模板、配置、执行、快照、模型和运营的唯一分区键 |
| `scenario_key` | 旧场景键；仅作迁移输入，新合同删除 |
| `slot_config_ref` | 槽位级 global config schema/default 的不可变版本引用 |
| `global_config` / `effective_global_config` | 本次请求覆盖 / 按平台无业务默认、同槽位 defaults、同槽位模板和请求覆盖合并后的最终配置 |
| `workflow_id` / `workflow_version` / `execution_id` | 工作流稳定 ID / 冻结版本 / 单次执行 ID |
| `source_workflow_id` / `source_workflow_version` / `source_execution_id` | 业务产物的来源工作流、冻结版本和成功执行 ID |
| `dataset_profile_ref` / `domain_profile_ref` | 数据集 profile / 领域 profile 的不可变引用 |
| `evaluation_contract_ref` | 同槽位评测量约不可变引用 |
| `dataset_snapshot_ref` / `model_ref` | 训练数据快照 / 模型工件的稳定引用 |
| `annotation_candidate_id` / `model_candidate_id` | 标注候选 ID / 模型候选 ID；两类实体不得混用 |
| `verification_id` / `registry_version` | 不可变复验记录 ID / 模型登记乐观锁版本 |
| `set_as_production` / `production_slot` | 是否同步改生产登记 / 目标生产槽位 |
| `idempotency_key` | 写请求幂等键；同键异 payload 必须冲突 |
| `governance_eligible` | execution 是否允许进入产品模型治理的服务端判定 |
| `slot_dataset_snapshot` | 单一 product slot 内只增不改的累计数据快照版本链 |
| `label_proposal` | 打标提案；禁止作为训练输入 |
| `LabeledDatasetVersion` | 专家确认真值箱；必须带 `slot` |
| `replay_activity` | 点路径逐点循环 activity；不进入冻结 graph；日内告警时钟 |

## 0.F 产品融合增量（2026-08-25）

与 `fusion-design.md` 对齐。本节与 R1–R19 冲突时，**产品接缝与路径取舍以本节为准**，点合同/slot/治理技术规则仍以 R1–R19 为准。

1. 新业务只进 `pv_day` / `pv_point`；`pv_fault` 为 legacy 只读。
2. 四段人机闭环：①③ 为工作流，②④ 为专家工作台，禁止把人工做成画布节点。
3. 真值链路固定为：确认箱（`LabeledDatasetVersion`）→ 同 slot 累计清单 → `slot_dataset_snapshot@version` → 训练。禁止用可变「当前累计 CSV」当训练输入。
4. 确认箱与提案必须带 `slot`；点工作流不得加载天确认箱，反之亦然。
5. 日内滚动告警只通过 `pv_point` + `replay_activity` + 告警状态机实现；禁止用 TSC / `seq_annotation` / 288 槽作为产品路径。
6. 老 `CumulativeTrainingService` 随机 snapshot 不得作为新产品训练真源，应收敛到槽位快照链。
7. 后续实施从 G10 起（见 `tasks.md` / `fusion-design.md`），不重开 G0–G8。

## 0. 结论与修订优先级

平台要交付的不是一个由平台开发者负责生产光伏专业金标的定制系统，也不是先造「通用时序平台」再拿 NASA/FHC 当大门，更不是用一个“万能模板”通过参数切换天/点语义。目标是光伏天、点各一条完整产品链，供算法工程师、数据工程师和领域专家共同使用：

1. 用户通过拖拽**单个算子**组装天级或点级时序工作流；P0 不提供子图、配方、组合块、自动展开或隐藏内部节点。
2. 保存、不可变版本化、复制并复用单个算子、完整工作流模板、dataset profile 和 domain profile；模板中的每个执行节点都必须在画布和冻结 graph 中可见。
3. 通过 `dataset_profile` — 数据集字段与采样合同适配不同来源（含以后从 Kaggle 找的表格集），**尽量**避免为每个数据集修改 Python/TypeScript 业务代码。换数据集的优先成本是「新 profile + 复制模板 + 独立 benchmark slot」；确需改算子时允许，但要记录例外。
4. 通过 `domain_profile` — 领域标签、文案、阈值与权限合同承载光伏知识，不复制通用加载、因果处理、训练、预测和评估实现。
5. 光伏天路径与点路径使用不同模板族：`pv_day` — 光伏天路径槽位负责设备日训练/预测，`pv_point` — 光伏点路径槽位负责真实事件点训练、逐点回放检测和标注候选；禁止在单模板中用 `modeling_path` 或 `production_path` 切换两种任务。
6. 保留标注候选审核、区间打标、标签回流、不可变累计快照、重训、槽位内 Challenger、复验、人工 Promote、Shadow 和部署后监控闭环。
7. **P0a** 首要交付是两条与负荷预测同形状的生命周期链：`pv_day` 从工作流组建走到训练、预测、部署、天级调度和精度运营；`pv_point` 从工作流组建走到训练、每个真实点经 `replay_activity` 喂入、调用冻结 graph 立即预测、部署和点级精度检测。
8. **P0b** 在 P0a 通过后，两个槽位再各自完成一轮“候选 → 审核 → 累计快照版本 +1 → 重训 → 复验 → Promote → 再预测/回放”。P0a 未演示前不得把闭环当退出条件。
9. 使用公开数据证明同一组手工节点和连线只换 profile 即可复用；这是 P0a（建议也等 P0b）通过后的验证层，不得成为产品主链前置。现有光伏数据用于主链验收与兼容回归。
10. 天/点只共享平台执行基础设施和单算子实现；累计快照、global config、模型候选池、评测量约、Champion/Challenger、Promote、告警和监控必须按 slot 隔离。现网 `slot=pv_fault` 在 G0 只读映射，G3 双读，G4 再切写。

本节与下文 R1–R12 共同构成需求真源；若旧表述与本节新增的 R13–R19 冲突，以本节和 R13–R19 为准。尤其是下文 R8 的旧数据优先级由“0.10 数据验收顺序”替代，但其中“不改业务代码、保留许可与可追溯性”的验收原则继续有效。

### 0.1 固定槽位边界（单一分区键）

新合同只使用一个 `slot` — 路径槽位作为模板、配置、执行、模型和运营的唯一分区键；不再同时维护 `slot + scenario_key`。固定槽位：

| `slot` | 中文含义 | 固定用途 |
|---|---|---|
| `pv_day` | 光伏天路径槽位 | 设备日模板、天级 global config、模型、评测、部署、调度、精度运营和累计快照 |
| `pv_point` | 光伏点路径槽位 | 点模板、点级 global config、模型、回放、部署、精度检测和累计快照 |
| `load_forecast` | 负荷预测槽位 | 负荷预测自己的模板、配置、registry、调度与精度运营；不读取光伏槽位数据 |
| `benchmark_nasa_smap_msl` | NASA 复用验证槽位 | 可写本 benchmark slot 的 execution、artifact、evaluation 与 evidence；禁止产品治理副作用 |
| `benchmark_fhc_twin_plant` | FHC 复用验证槽位 | 可写本 benchmark slot 的 execution、artifact、evaluation 与 evidence；禁止产品治理副作用 |
| `benchmark_pvdaq_<system>` | 选定 PVDAQ 系统验证槽位 | 每个具体 system 独立；用于无标签逐真实点复用验证，只写本 benchmark 证据，禁止直接产品治理副作用 |

其他外部数据集使用稳定的 `benchmark_<dataset_key>` 槽位，不得复用 `pv_day`、`pv_point` 或 `load_forecast`。`dataset_profile_ref` 继续描述槽位内“使用哪份数据”，但不能替代槽位隔离。

每个 slot 独立绑定允许的 template family、dataset/domain profile、evaluation contract、global config schema/default/version、candidate pool、registry 和权限。允许同一页面只读并排展示多个槽位，但禁止跨槽位比较、合并候选、复用 Promote 证据或写对方 registry。

`scenario_key` 从所有新 HTTP、模板、execution、annotation/model candidate、verification、registry、audit 和 UI URL 中删除。旧 `(slot=pv_fault, scenario_key=pv_day)` 或 `modeling_path=legacy_day` 映射为 `slot=pv_day`；旧 `(slot=pv_fault, scenario_key=pv_point)` 或点路径 modeling path 映射为 `slot=pv_point`，只作为迁移输入并回显 `slot_resolution_source=legacy_mapping`，不得成为第二个持久化分区键。G0 不得改写现网 `pv_fault` 生产指针。

### 0.2 固定模板族

光伏至少提供四个独立模板角色，每个模板只能绑定一个 slot：

| `slot` | 模板角色 | 输入 | 主输出 |
|---|---|---|---|
| `pv_day` | `train_eval` — 天级训练评估 | 设备日测量、天标签、天级 profile | 日级模型、槽位内评估和模型候选 |
| `pv_day` | `predict` — 天级预测 | 完成或封账设备日、明确 `model_ref` | 设备日诊断记录 |
| `pv_point` | `train_eval` — 点级训练评估 | 按事件时间排序的真实点、点/区间标签、点级 profile | 点模型、点/事件/延迟指标和模型候选 |
| `pv_point` | `predict_replay` — 点级预测回放 | 逐个或确定性微批暴露的真实点、明确 `model_ref` | 每个输入点对应的预测、质量决定和候选区间；P0 不输出正式告警状态 |

模板中的节点由用户逐个拖拽、配置和连线；P0 不允许引用子图或隐藏计算节点。`replay_activity` 的逐点循环不是画布节点。不同模板可以使用相同 `operator_id`，但其 graph、保存、版本、执行、global config、模型候选和生产登记均按 slot 独立。训练模板产出工件；预测模板只消费明确 `model_ref`，不得隐式重训。`pv_point` 不包含网格对齐节点，不生成规则时间网格、补齐缺失时间戳或聚合重采样。

### 0.2.1 P0a 生命周期链与 P0b 双闭环验收

**P0a（先验收，对应 G0–G3）：**

1. `pv_day` 端到端完成：Workflow Editor 组建/发布 `pv_day.train_eval` 与 `pv_day.predict` → 训练产生带 source execution 的 `model_ref` → 设备日预测 → Deployment `?slot=pv_day` 能展示该产物 → 日检/Orchestrator 触发已发布预测工作流 → Accuracy Operations `?slot=pv_day` 能看到本次指标。P0a 不强制完整 verification/Promote true。
2. `pv_point` 端到端完成：Workflow Editor 组建/发布 `pv_point.train_eval` 与 `pv_point.predict_replay` → 在**真实点窗口合同上重训**（旧 grid POC 权重不得当 Champion）→ `replay_activity` 按实体暴露真实点并每次调用同一冻结 graph → Deployment / Accuracy Operations 的 `pv_point` 槽位展示一点一结果及点级指标。链路中不得生成规则网格或虚拟点。
3. 部署和精度运营主列表中的模型、指标和预测批次必须带 `source_workflow_id`、`source_workflow_version`、`source_execution_id` 与 artifact/evaluation ref。
4. P0a 使用现有 PV 数据；NASA/FHC/PVDAQ 不是 P0a 启动或完成的前置。G3 必须有最小可点 UI（选 slot、执行模板、看见产物）；完整深链打磨属于 G7。

**P0b（P0a 通过后，对应 G4–G5）：**

5. 两个槽位分别完成至少一轮：预测 → `annotation_candidate` → 专家审核 → `reviewed_annotation` → `slot_dataset_snapshot` 新版本 → 固定版本重训 → 槽位内 verification → 人工 Promote（本轮闭环必须显式 `set_as_production=true`）→ 再预测/回放。
6. P0b 的 Promote true **禁止**切换现网 `pv_fault` 生产 Champion，必须使用演示数据或非现网指针。
7. 闭环链路还要保存 `dataset_snapshot_ref`、`model_candidate_id`、`verification_id`、`registry_version`。

### 0.3 R13：单算子手工编排与四类复用对象

1. 平台只复用四类对象：通用单算子、完整工作流模板、dataset profile 和 domain profile；P0 不实现 `reusable_subgraph`、recipe、组合节点或自动展开。
2. 用户必须在画布上逐个拖入并连接算子。冻结的 `graph` — 工作流节点图必须完整保存每个节点、端口、参数、位置和 `operator_id`，执行器不得在幕后插入节点。
3. 通用算子**尽量**不包含 `pv_fault`、数据集名、逆变器、设备日等条件分支；光伏特有列名、标签、阈值和文案优先放在 profile 或适配层。`timeseries_point` 核心**尽量**只消费规范表：实体键、事件时间或 index、特征列、可选点/区间标签。
4. 模板必须声明 `template_family` — 模板族、`slot` — 唯一路径槽位、用途、允许的数据粒度、所需 profile contract 和 `evaluation_contract_ref` — 评测量约不可变引用。
5. 修改模板实例不得覆盖源模板；每次执行必须绑定模板内容哈希或不可变版本。
6. 跨数据集复用优先用“相同的可见节点集合、`operator_id` 和连线，仅替换 profile/参数”证明；允许复制完整模板作为草稿起点，但不引入隐藏公共节点链。节点/算子有差异时记录例外，不因此判失败。
7. 换一个新表格数据集（含 Kaggle CSV/Parquet）**优先只改**：`dataset_profile`、必要时 `domain_profile`、相对 `source_ref`、独立 `benchmark_<dataset_key>`、评测量约引用、允许的模型超参数。**尽量不**为该数据集修改 `ts_point_*` 或新增计算算子；源格式不是表格时，优先新增可见 adapter-backed loader。确需改算子时允许，但要写成可复用能力或记下特例。

### 0.4 R14：槽位内精度运营与模型治理

1. 模型候选、复验队列、evaluation store、registry、Champion、Challenger、Promote、Shadow、告警和监控只使用一个 `slot` 分区，不再持久化 `scenario_key`。
2. `slot=pv_day` 的设备日指标只能与 `pv_day` 比较；`slot=pv_point` 的点级、事件级、延迟、误报和无决策指标只能与 `pv_point` 比较；`load_forecast` 和每个 benchmark slot 也各自隔离。
3. Promote 必须验证模型候选、复验记录与目标 registry 的 `slot` 完全一致；不一致返回可诊断 conflict，不允许强制绕过。
4. `verification_id` — 不可变复验记录 ID 必须绑定 `model_candidate_id` — 模型候选 ID、候选训练来源三元组、复验评测来源三元组、slot、当时的 Champion/Challenger、registry 版本、评测量约版本、生效门槛摘要、数据/窗口快照和分项结果；Promote 时必须重新确认当前 Champion 与 registry 版本仍一致，过期记录不得复用。
5. verification 中 `candidate_source_workflow_id` / `candidate_source_workflow_version` / `candidate_source_execution_id` 只描述候选训练执行，`verification_source_workflow_id` / `verification_source_workflow_version` / `verification_source_execution_id` 只描述本次复验评测的真实 workflow execution；`model_artifact_ref` 与前者绑定，`evaluation_artifact_ref` 与后者绑定，禁止用一个 execution 同时冒充两个 producer。
6. `verification.passed` 只有在复验 workflow execution 与 verification 任务均 succeeded、两组来源和 candidate/contract/registry 的 slot 一致、`eligible_for_pool=true`、分差/胜窗数/质量门禁全部通过且没有失败窗阻断时才可为 JSON boolean `true`；公式由评测量约唯一决定，不允许 Promote 请求临时改门槛。
7. `set_as_production` — 是否同步改生产登记默认必须为 JSON boolean `false`。false 在门禁通过后只把该 model candidate 写为 registry 的独立 Challenger 组并保持 Champion 不变；true 可直接把同一候选原子写为新 Champion 并清空已晋升的 Challenger 组。
8. Promote 写入 registry 的候选模型必须是该 model candidate 的 `challenger_model_ref` — 挑战者模型稳定引用，不得写旧 Champion、另一槽位模型或工作流模板 ID。
9. 跨槽位只读诊断不得产生 `eligible_for_pool=true` 或 Promote 证据。
10. model candidate 的 `source_workflow_id` / `source_workflow_version` / `source_execution_id` 与 `model_artifact_ref` 只描述训练 producer；prediction batch 和 evaluation record 的同名字段只描述各自 producer。verification 必须使用第 5 条两组显式前缀字段。缺少来源、execution 非 succeeded、artifact 与 producer 不匹配或 slot 不一致时不得进入治理。
11. Algorithm Deployment 只读取工作流产生的模型工件、候选、复验和 registry，并可发起同一工作流/治理 API；不得包含自己的训练、预测或评测实现。
12. Accuracy Operations 只读取工作流 execution 写出的 evaluation artifact/store、预测证据和质量报告，并可触发注册工作流；页面/专用 service 不得用另一套算法重新计算生产指标。允许做无业务语义的展示聚合，但结果必须保留原 evaluation refs。
13. 每个 registry 版本必须分别保存 Champion 组与 Challenger 组。Champion 组使用 `champion_model_ref`、`source_model_candidate_id`、`source_workflow_id`、`source_workflow_version`、`source_execution_id`、`model_artifact_ref`、`verification_id`；无前缀的 source 字段只描述 Champion。Challenger 组使用 `challenger_model_ref`、`challenger_model_candidate_id`、`challenger_source_workflow_id`、`challenger_source_workflow_version`、`challenger_source_execution_id`、`challenger_model_artifact_ref`、`challenger_verification_id`。缺少任一必需来源的组不得进入部署/精度运营主列表。
14. `promotions_log` — 晋升审计必须 append-only，并直接保存 model candidate 的训练 provenance、verification 的评测 provenance、`adopted_challenger_model_ref` — 本次采纳的挑战者、`previous_champion_model_ref` — 操作前 Champion、`new_champion_model_ref` — 仅生产切换时的新 Champion、`resulting_champion_model_ref` — 操作后实际 Champion、`champion_changed` — 是否切换生产、`production_slot`、`set_as_production`、操作人与结果。false 分支的 `new_champion_model_ref` 固定为 null、`resulting_champion_model_ref` 等于旧 Champion、`champion_changed=false`；缺成功来源时不得记录成功 Promote。
15. verify-async 必须绑定同 slot 不可变 `verification_workflow_ref` 并创建真实 evaluation workflow execution；只有该 execution succeeded 且发布 `evaluation_artifact_ref` 后才能生成最终 verification，`comparison_id` 只用于轮询，不能替代 execution provenance。
16. `slot` 以 `benchmark_` 开头当且仅当 `execution_purpose=benchmark_reuse`；服务端无条件计算 `governance_eligible=false`，客户端、配置和高权限恢复均不得翻转。annotation candidate、snapshot、model candidate、registry、Promote 和正式告警每个写入口都必须直接按 slot 再拒绝 benchmark，不得只信派生 flag。

### 0.5 R15：数据喂入与逐点 replay

1. 天路径 feeder 以设备日或封账批次为单位；点路径 feeder/replay 以**真实测量点**为推进单位，按实体分别维护进度，二者不得共用游标或让一个 slot 推进另一个 slot。
2. P0 文件 replay（回放循环）是喂数调度，不是算子：`replay_activity` 按稳定的事件时间与原始次序逐个或确定性微批暴露尚未处理的点；每暴露一个点，就调用同一份冻结 graph 做一次当前点检测，不能先把整日数据交给预测器再伪装逐行调用。该 activity **尽量**能驱动任意表格 profile，不要只认光伏水位；做不到时记录例外。
3. 点链保留原始事件时间和值，不做 resample、round/floor、规则网格生成、虚拟缺失点补齐或跨点聚合。同一实体同一事件时间的相同记录按幂等键去重；冲突值明确失败。
4. `ts_point_causal_impute` — 点级因果缺值处理只允许修改**已有真实点行中的空特征值**，且只能读取该实体过去真实点；不得创建新时间戳或新行。超过允许历史时长、历史不足或长间隔触发 `no_decision` — 无法判定，而不是伪造观测。
5. feeder/replay 长任务必须返回 `activity_id` — 活动 ID，并提供 queued、running、succeeded、failed、cancelled 状态；状态至少保存每实体最后成功处理事件与失败原因。
6. 每次喂入必须记录 profile 版本、源摘要、相对源引用、`clock_mode` — 时钟模式、实际事件时间/索引范围、真实点数、拒绝点和错误原因。
7. P0 允许确定性文件 replay，不要求先建设生产消息队列、迟到修订和常驻在线消费者；但训练和 replay 必须使用同一“真实点序列 + 当前点终止窗口”合同。
8. 每个通过 schema/幂等校验并被 replay admission 接受的真实点，先作为 pending point 参与本次窗口，必须由 `ts_point_predict` 生成恰好一个 `point_outcome`，其 `kind` 为 `prediction` XOR `no_decision` 并带 evidence。只有“当前点写入 committed history + outcome/evidence + 该实体 `replay_cursor`”同一事务提交成功后，该点才算正式暴露；任一写失败全部回滚，禁止出现 buffer 已前移而 cursor 未前移。
9. 格式非法或冲突重复必须产生显式 rejection/error，pending point 不进入 committed history，outcome、evidence 与 cursor 均不推进，禁止静默跳点。P0 对阻塞点的恢复只允许修正源记录后，以同一稳定身份和 `idempotency_key` 重试；不得自动 skip 后推进 cursor。若未来允许人工 quarantine/skip，必须另立权限、原因和 append-only 审计合同。
10. `ts_point_causal_window` 的 `not_ready` 只是传给 `ts_point_predict` 的 typed window state，不是第二份持久化 no-decision；candidate/metrics/alarm 投影只能消费已提交 outcome，不能另计或覆盖结果。
11. `pv_point.predict_replay` 的冻结 graph 只含可见普通算子（load → map → validate → impute → window → load_model → predict → 可选 candidate/metrics）。逐点循环属于 `replay_activity`：对每个 pending point 调用同一份冻结 graph 一次；admission、committed history、cursor 与事务在 activity 内，不得画成隐藏 `operator_id`，也不得为每个点创建互异草稿 graph。
12. 现有 strict-grid POC 权重不得标为新点合同兼容；P0a 点链必须在真实点窗口上重训，并用「一点一结果 / 修改未来不影响当前预测」验收。

### 0.6 R16：闭环标签来源

1. 公开数据自带标签统一记为 `benchmark_ground_truth`，只用于对应基准训练/验证/测试角色，不得显示为专家审核。
2. 专家确认、改边界或改类别后形成 `reviewed_annotation`；它必须保留审核人、审核时间、来源候选、原/新边界和标签空间版本。
3. 模型或规则输出只记为 `candidate_only`，未经审核不得进入训练真值或 locked holdout。
4. `pseudo_label` 只有通过独立、显式、可审计的 admission/import workflow 才可进入 learning；该流程必须发布独立不可变 import/base snapshot，或先经领域审核形成新的 `reviewed_annotation`。它不得由产品增量 snapshot build API 直接接收，始终不得进入 locked holdout。
5. 天标签不得广播为点标签；点候选也不得自动聚合成天标签。
6. `pv_day` 和 `pv_point` 必须各自维护一条 append-only 的 `slot_dataset_snapshot` — 槽位累计数据快照版本链。每个 product slot 只有一个稳定 `snapshot_id` — 快照链 ID，链内使用单调 `snapshot_version`；后续 build 返回同一个 `snapshot_id` 和版本 +1，不得为每版另造快照 ID。每版还保存 `base_snapshot_version`、slot、新增 reviewed annotation、角色分区、标签空间版本、profile 引用和 source digest。
7. 首版必须通过独立、显式、同 slot 的 bootstrap/import workflow 创建：只有该 workflow execution succeeded、发布不可变基础数据 artifact、角色分区和来源摘要后，才能原子发布 `snapshot_version=1`，其 `base_snapshot_version=null`。同 slot 已存在链时 bootstrap 冲突；产品增量 build API 不负责创建首版。
8. 构建下一快照只接受同 slot 的 `reviewed_annotation`；候选、跨 slot 标注或 locked holdout 角色冲突必须阻断。build 必须引用当前 stable `snapshot_id` 和 current latest `base_snapshot_version`，成功只追加同一链的新版本；旧版本不可覆盖，失败保持上一版本为 latest。
9. 重训必须引用明确 `snapshot_id@snapshot_version`，model candidate 保存该引用并只进入同 slot 治理；任何存在且 ID/version/slot 匹配的不可变历史版本都允许重训，不要求是 current latest，也绝不自动替换为 latest。重训成功不自动 verify、Promote 或改 registry。
10. 天快照以设备日样本累计，点快照以点/窗口样本累计；二者不得共享 snapshot ID、版本号或自动复制标签。
11. bootstrap、build、retrain、verify、Promote 均有独立幂等键和 activity/audit；bootstrap/build 只改变快照链，retrain 只产生工作流 artifact/model candidate，任一步成功不得自动触发下一步。
12. `latest_snapshot_ref` 只表示同 slot 追加 build 的乐观锁基线和 UI 默认展示；它不是 retrain 的隐式输入，也不得阻止用户显式选择历史不可变版本复现实验。

### 0.7 R17：完整故事线

平台必须能用稳定 ID 和审计串起以下链路。其中喂入到精度运营是 **P0a**；审核到再预测是 **P0b**。

```text
外部源
→ dataset_profile
→ day feeder 或 point replay
→ 工作流执行
→ 预测与证据
→ annotation candidate 候选区间
→ 领域专家审核
→ reviewed_annotation
→ 不可变标签/数据快照
→ 同 slot 重训
→ model candidate
→ 同 slot 多窗或锁定集复验
→ 人工 Promote（本轮闭环显式 `set_as_production=true`）
→ Shadow / 生产
→ evaluation store 与运行监控
```

任一失败不得覆盖上一份可用快照、Champion、已审核标签或生产登记；重试必须幂等或产生可审计 revision。

### 0.8 R18：前端信息架构与状态

1. 工作流编辑页必须先选择 `slot`，再加载该槽位允许的 template、dataset/domain profile、`slot_config_ref` 和 `global_config`；执行前展示缺 backend、缺端口、schema 不匹配、配置跨槽位和因果风险。
2. 精度运营使用单一 slot 选择器/路由，例如 `/accuracy-operations?slot=pv_day`、`?slot=pv_point`、`?slot=load_forecast`；每个槽位只显示自己的 workflow executions、指标、候选池、复验池、Champion、告警和累计快照，不再维护 `scenario_key` 或光伏内二级 Day/Point 分区。
3. 标注页复用现有 annotation candidate 队列、曲线框选、动态标签和撤销能力；必须显示 slot、annotation source 与 role，避免把 benchmark、人工、弱标签和候选混淆。
4. 模型部署页按 slot 隔离，例如 `/algorithm-deployment?slot=pv_day|pv_point|load_forecast`；Promote 确认区显示 model candidate、source workflow/execution、verification、Challenger、目标 slot、门禁和审计，不允许 UI 先乐观改写 Champion。
5. 部署和精度运营不得调用页面专属训练/预测/评分逻辑；所有业务结果必须来自真实工作流 execution/artifact/evaluation store，UI 仅查询、展示、做无业务语义聚合或触发已注册工作流。
6. 所有读取区域具备 loading、empty、error、retry；所有写操作具备 disabled、submitting、success、failure、conflict 和重复提交保护。
7. URL 必须保留 `slot`、当前对象与筛选；刷新后恢复上下文，无权限或未知 ID 显示可诊断状态。
8. 每个 product slot 必须展示当前 `snapshot_version`、样本总数、本轮新增数、来源/角色分布、对应 retrain activity 与 model candidate；版本时间线只读，构建下一版、重训、复验和 Promote 是四个分开的显式动作。

### 0.9 R19：兼容、默认与最终行为分支

1. 新 API、模板和 UI 请求必须显式提供 `slot`。`slot` 是唯一分区键；新合同拒绝 `scenario_key`，防止客户端同时发送两个来源不一致的路径标识。
2. 响应必须返回 `slot_resolution_source` — 槽位解析来源，枚举仅允许 `explicit` — 请求/模板显式提供或 `legacy_mapping` — 服务端旧记录映射。新请求缺 slot 直接失败。
3. 旧 `(pv_fault,pv_day)` 只映射为 `pv_day`，旧 `(pv_fault,pv_point)` 只映射为 `pv_point`；映射必须由服务端 legacy workflow/version allowlist 驱动，不根据请求形状、列名或客户端兼容开关猜测。
4. 前端槽位选择器始终发送显式 slot；URL、模板、slot config、profile、execution 和目标 registry 的 slot 必须一致。
5. 后端 API 省略请求级 `global_config` 时先规范化为 `{}`，与显式空对象等价；无论是否有请求覆盖，都按 R4 完整合并平台无业务默认、同 slot defaults 与模板 metadata，并回显 `effective_global_config`、`slot_config_ref` 和来源。前端始终发送对象。
6. 新模板执行必须提供 `dataset_profile_ref` 和 `domain_profile_ref` 的不可变引用，或由已发布模板在同 slot 绑定唯一默认版本；无默认或多候选时失败，并回显 `profile_resolution_source`。
7. 新点算子使用新 `operator_id`，只允许进入 `slot=pv_point` 的模板；不改变负荷预测和旧光伏算子的默认语义。
8. verify、Promote、审核、replay 控制、累计快照构建和固定快照重训等写接口必须接收 `idempotency_key` — 幂等键；同键同请求返回原结果，同键不同请求返回 conflict，不追加重复审计。
9. 最终改变治理行为的条件必须等价于：

```text
if model_candidate.slot != target_registry.slot:
    reject_cross_slot_promotion
elif verification.slot != model_candidate.slot or verification.model_candidate_id != model_candidate.id:
    reject_mismatched_verification
elif verification.passed is not true:
    reject_unverified_candidate
elif verification.baseline_model_ref != target_registry.champion_model_ref or verification.registry_version_at_start != target_registry.registry_version:
    reject_stale_verification
elif set_as_production is not true:
    register_candidate_as_challenger_without_champion_switch
else:
    register_candidate_as_same_slot_champion_and_clear_promoted_challenger
```

10. 最终改变累计数据集的条件必须等价于：

```text
if any(annotation.status != reviewed or annotation.slot != target_snapshot.slot):
    reject_invalid_or_cross_slot_annotation
elif base_snapshot_version != current_latest_snapshot_version:
    reject_stale_snapshot_base
elif role_partition_leaks_locked_holdout:
    reject_role_leakage
else:
    append_reviewed_annotations_and_publish_snapshot_version_plus_one
```

快照发布成功只改变同 slot 的 latest snapshot 指针；不会自动重训、复验或修改 Champion。任何治理记录若缺成功 `source_execution_id` 或其 source workflow slot 不一致，也必须拒绝。

### 0.10 复用验证准备与外部数据顺序（非 P0a 前置）

P0a 的唯一首要验收以 0.2.1 的 1–4 为准：先在现有 PV 数据上打通天/点生命周期链。P0b 闭环是下一刀。下表用于其后的等价回归、跨数据集复用和无标签故事验证，不得阻断 P0a 主链启动或把“跑过很多数据集”替代为场景链路完成。G1 退出不要求下载 NASA/FHC。

本顺序替代下文 R8 的旧优先级：

| 顺序 | 数据 | 验证目标 | 准入条件 |
|---:|---|---|---|
| 1 | 现有光伏冻结快照 | 新 wrapper/模板与现有 POC 等价，不回归 | 只读、不可覆盖现有工件 |
| 2 | NASA SMAP/MSL | 同一核心点工作流跨领域、预切分 train/test 和异常区间 | 本地下载；数据再分发许可未明确时不得提交仓库 |
| 3 | FHC Twin-Plant | 30 秒光伏多变量、正常训练、污染测试和模拟 replay | CC BY 4.0；固定 test 不反复调参 |
| 4 | NREL PVDAQ | 无标签逐真实点 replay → 候选证据 → 可选 benchmark-local 专家审核演示；只保留 benchmark-local 证据 | 直接写产品快照或 Promote 始终禁止；转产品必须走目标 product slot 的显式 import workflow，并先核验 system 数据条款 |
| 补充 | NAB / SKAB / small_tep / GPVS / 其它 Kaggle 表格异常检测集 | 流式、工业多变量、多故障与高频压力；尽量验证 A5.7 优先路径 | 各自许可、规模与派生合同通过预检；优先不为单个 Kaggle 集新写计算算子，例外需记录 |

最低复用证据固定要求 NASA SMAP/MSL 与 FHC Twin-Plant 都使用相同的可见节点集合、连线和 `operator_id`，只改变 profile、相对路径、标签映射和允许的模型超参数，不修改业务代码。外部数据事实、文件结构和许可证据见 `research.md` — 调研证据底稿；规范顺序和准入门槛只以本节为准。

### 0.11 `slot` 全链路追踪

```text
UI 槽位选择器（pv_day / pv_point / load_forecast / benchmark_*）
→ HTTP body/query 的 slot
→ API Handler 校验 slot registry 与权限
→ 解析同 slot 的 template/profile/slot_config_ref
→ execution context 写入 slot 与 effective_global_config
→ 工作流 execution / annotation candidate / snapshot / model candidate / evaluation 按 slot 持久化
→ verification 只查询同 slot evaluation_contract 和 Champion
→ registry 只读取/写入同 slot Champion
→ 响应回显 slot 与 slot_resolution_source
→ UI 刷新原槽位的工作流结果、快照、模型候选、复验和部署状态
```

旧 `modeling_path` 仅作历史审计字段，不得参与 slot 解析。只有旧 `scenario_key` 在服务端 legacy workflow/version allowlist 命中时，才与旧 `slot=pv_fault` 共同映射：`(pv_fault,pv_day)` → `slot=pv_day`，`(pv_fault,pv_point)` → `slot=pv_point`。新 HTTP、模板、execution、治理和 UI 真源统一使用 slot。缺省回退只允许上述服务端 legacy allowlist 映射；新请求缺 slot 必须失败。最终改变行为的是 source workflow、model candidate、verification、snapshot 和目标 registry 的 slot 一致校验。

### 0.12 候选实体命名与 benchmark 槽位隔离

| 实体/字段 | 中文含义 | 固定规则 |
|---|---|---|
| `annotation_candidate_id` | 待领域专家审核的点或区间候选 ID | 审核后才可能形成 annotation，不可用于 Promote |
| `model_candidate_id` | 待复验或晋升的模型候选 ID | 由成功的同 slot 训练/重训工作流 execution 与评估产生，只能进入同 slot verification/registry |
| `source_annotation_candidate_id` | 生效标注追溯的来源候选 ID | 只指向 annotation candidate |
| `source_model_candidate_id` | registry/晋升审计追溯的来源模型候选 ID | 只指向 model candidate |

新 API、存储和审计不得用无类型的 `candidate_id` 同时表示上述两类对象。NASA、FHC、NAB 等公开基准必须各自运行在 `benchmark_<dataset_key>` slot。双向硬约束固定为：`slot` 以 `benchmark_` 开头当且仅当 `execution_purpose=benchmark_reuse` — 执行目的为基准复用证明；服务端无条件计算 `governance_eligible=false` — 禁止进入产品治理，客户端、模板配置和运维恢复均不得置 true。preflight 与 annotation candidate、`slot_dataset_snapshot`、model candidate、registry、Promote、正式告警等每个写入口都必须独立按 benchmark slot 拒绝，不能只依赖上游 flag。benchmark 可以复用相同的普通 `ts_point_*` 节点与手工连线并保存自身 execution/artifact/evaluation/evidence，但不得污染 `pv_day`、`pv_point` 或 `load_forecast` 的标注候选、累计快照、模型候选池或 Champion。

## 1. 用户与职责

| 用户 | 职责 | 平台提供的能力 |
|---|---|---|
| 算法工程师 | 组装和运行工作流、选择模型、分析指标 | 算子库、画布、模板、执行日志、工件和评估 |
| 数据工程师 | 接入数据、配置字段映射和质量规则 | 数据集 profile、预览、schema 校验、相对路径解析 |
| 领域专家 | 审核候选区间、修正边界和类别 | 审核队列、时序曲线、区间标注、撤销和审计 |
| 平台管理员 | 管理算子、权限、版本和生产模型 | 算子注册、模板版本、活动状态、模型 registry 和审计 |
| 平台开发者 | 建设通用能力，不替代领域专家判断 | 扩展算子协议、适配器和运行时，不负责制造专业金标 |

## 2. 范围

### 2.1 本轮必须实现的产品范围

- 通用点级时序数据合同和数据集 profile。
- 可拖拽、可保存、可执行、可版本化的工作流。
- 工作流节点只做逐个手工编排；P0 不提供子图、配方、组合节点或隐藏自动展开。
- 点级二分类和多分类的训练、逐真实点预测、确定性 replay 评估能力；点链不做网格对齐、重采样或虚拟点补齐。
- 已有闭环审核能力的平台化接入。
- 至少两个外部公开数据集在不修改业务代码的前提下运行同一核心工作流。
- 光伏故障作为可选领域 profile 接入同一平台。

### 2.2 非目标

- 平台开发者亲自制作光伏专业金标。
- 首轮即建设正式在线告警、每设备水位、迟到修订和生产微批调度。
- 为每个数据集复制一套算子或专属页面。
- 把 Kaggle Notebook 代码直接复制进平台。
- 把天标签广播成点标签。
- 把公开基准标签伪装为人工审核标签。
- 首轮重写现有负荷预测工作流或删除现有光伏能力。
- 在许可证未核实前把外部数据集提交进仓库或随产品分发。

## 3. 核心术语

| 字段或概念 | 中文含义 |
|---|---|
| `dataset_profile` | 数据集 profile；描述时钟模式、事件时间列或单调索引、实体列、特征列、标签列、采样频率/模拟步长和标签语义 |
| `domain_profile` | 领域 profile；描述光伏、化工、服务器指标等场景的业务标签、展示文案和策略 |
| `operator_id` | 算子唯一标识；画布节点、运行时后端和算子目录必须使用同一个 ID |
| `operator_contract` | 算子合同；定义输入、输出、参数、默认值、错误和副作用 |
| `workflow_template` | 工作流模板；定义完全展开、可执行且每个节点可见的节点图、默认配置和用途 |
| `slot` | 路径槽位；模板、配置、execution、模型、评测、部署与运营的唯一分区键 |
| `slot_config_ref` | 槽位配置不可变版本引用；用于冻结同 slot 的 global config schema/default/version |
| `effective_global_config` | 本次执行最终生效的槽位级工作流配置；由同 slot defaults、模板配置和请求覆盖合并得到 |
| `benchmark_ground_truth` | 公开基准自带真值；用于功能和指标验证，不计为人工标注 |
| `reviewed_annotation` | 领域专家审核后形成的标注；可按准入规则进入训练或锁定验收 |
| `annotation_candidate` | 标注候选；由模型或规则提出的点或区间，未经审核不能成为人工真值，也不能参与 Promote |
| `model_candidate` | 模型候选；由成功的训练工作流 execution 与评估产生，只能进入同 slot 的复验和模型治理 |
| `activity` | 状态型活动；长时间、有副作用、需要轮询或恢复的任务 |
| `model_ref` | 模型稳定引用；训练、预测、评估和治理通过它关联同一模型工件 |

## 4. 功能需求

### R1：工作流画布与手工复用

1. 用户必须能够从算子库逐个拖拽节点、连接端口、编辑参数、保存和执行工作流。
2. 保存后必须保留每个节点的 `operator_id`、端口、参数、节点位置和槽位级工作流配置；画布、冻结 graph 和实际执行节点必须一一对应。
3. 工作流必须支持版本化、复制和从模板创建，修改实例不得覆盖源模板。
4. P0 禁止把多个算子打包成可复用子图、配方或组合节点，也禁止根据 profile 在执行时暗中插入节点。公共链路可以通过复制完整模板复用，但用户必须能看见并修改每个普通节点。
5. 同一个核心点分类工作流**尽量**能通过切换 `dataset_profile` 在不同 benchmark slot 上使用相同节点集合和连线运行，优先不为每个数据集复制 backend。接入新的 Kaggle 表格集**默认优先**不新增 `ts_point_*`；做不到时记录例外。

### R2：数据集 profile

1. profile 至少定义以下字段：

| 字段 | 中文含义 | 缺省规则 |
|---|---|---|
| `profile_id` | profile 唯一标识 | 必填 |
| `source_kind` | 数据源类型 | 必填；仅允许 `file`、`directory`、`manifest` 或 `connection` |
| `source_ref` | 数据源稳定引用 | 必填；文件类使用相对路径，连接类使用已登记 connector ID，禁止 URL、secret 或绝对路径 |
| `path_root_alias` | 相对路径解析根别名 | 文件类必填；只允许项目根或后端数据根等服务端白名单别名，不持久化解析后的绝对路径 |
| `format` | 数据格式，如 csv、parquet、npy 或 rdata adapter | 可由扩展名/adapter 推断，但结果要写入生效配置 |
| `clock_mode` | 时钟模式 | 必填；只允许 `event_time` 或 `index`。CSV/Parquet 等表格数据使用 `event_time`；仅 NASA NPY 等无真实时间的匿名数组允许 `index` |
| `time_column` | 事件时间列 | `clock_mode=event_time` 时必填且必须可解析；`clock_mode=index` 时必须为空，不得伪造墙上时钟 |
| `entity_keys` | 实体分组列 | 可为空；为空时整个文件视为一个实体 |
| `feature_columns` | 模型输入列 | 必填，至少一列 |
| `label_column` | 点级标签列 | 无标签预测场景可为空 |
| `label_semantics` | 标签语义，如 binary、multiclass、anomaly_window | 必填 |
| `sampling_interval` | 期望采样间隔或序号时钟模拟步长 | `event_time` 可自动推断但必须返回结果和置信度；`index` 必须显式提供模拟步长 |
| `timezone` | 时间解释时区 | `event_time` 默认 UTC，不使用浏览器本地时区猜测；`index` 不得映射为真实时区 |
| `split_policy` | 划分策略 | 默认按时间，禁止随机打散重叠窗口 |
| `license_ref` | 数据许可或来源说明 | 外部数据必填 |
| `license_status` | 当前用途的许可核验状态 | 仅允许 `verified`、`unverified` 或 `prohibited` |
| `redistribution_allowed` | 是否允许随仓库、镜像或产品再分发 | 必填布尔值；未知按 false 处理 |
| `allowed_use_purposes` | 允许用途 | 显式列出 local_validation、distribution、production 等用途 |

2. 数据预览必须先校验列存在、时钟模式合法、实体键非空比例、重复时间点或重复索引、采样间隔或模拟步长，以及标签取值。`clock_mode=event_time` 时必须校验事件时间可解析且顺序/时区明确；`clock_mode=index` 时必须校验索引单调、稳定、可重放，并拒绝真实时间列存在却降级为 index clock。
3. 文件类 `source_ref` 规范化后必须仍位于 `path_root_alias` 对应的允许根内；拒绝 `..` 目录逃逸、符号链接/重解析点逃逸和未允许 scheme。`connection` 只能引用服务端 connector registry 中的稳定 ID，不能携带凭据或任意 URL。
4. profile preflight 必须接收 `use_purpose` — 本次用途，并组合 `license_status`、`redistribution_allowed` 与 `allowed_use_purposes` 判断准入；例如 NASA 可允许本地验证但阻断再分发。校验失败时必须返回具体字段和原因，不得静默替换列名、解析根或连接类型。
5. 每次 execution/activity 必须冻结 `source_ref`、profile 版本、实际事件时间范围或索引范围，以及 `source_digest` — 输入内容或 manifest 摘要；profile 指向的文件后续变化时不得复用旧执行证据。
6. 新数据集适配应优先增加 profile；只有数据结构无法通过通用映射表达时才允许新增适配器。

### R3：通用算子合同

1. 算子运行入口保持 `execute(params, inputs) -> dict`，以兼容现有 `OperatorRouter`。
2. 新算子必须同时提供可机器读取的参数、输入、输出、默认值和副作用声明。
3. 算子目录、前端节点和运行时注册不得手工维护三套互相漂移的合同。
4. 未注册算子、缺少必填输入、类型不匹配和不满足因果约束时必须在执行前或节点执行时明确失败，不得伪装为成功跳过。
5. 纯算子不得写标签、修改 registry 或隐式启动训练；有副作用的步骤必须声明为 activity 或显式写操作。
6. 普通画布固定展示 12 个点节点，全部由用户手工配置和连线：`ts_point_profile_map`、`ts_point_validate_schema`、`ts_point_label_join`、`ts_point_causal_impute`、`ts_point_temporal_split`、`ts_point_causal_window`、`ts_point_train_classifier`、`ts_point_predict`、`ts_point_cross_validate`、`ts_point_metrics`、`ts_point_candidate_intervals`、`ts_point_persistence_alarm`。
7. 不提供 `ts_point_align_grid`，也不得用其他名称引入等价的 resample/grid 节点。`ts_point_profile_map` 是普通可见节点，不自动配置、不隐藏在输入组合块内。
8. P0 启用上述 12 个中的 10 个；`ts_point_cross_validate` 与 `ts_point_persistence_alarm` 属于 P1，P0 若展示必须 disabled 并说明延期原因，不得进入发布模板或依赖 skipped-success。
9. 上述 12 个只统计新点域 `ts_point_*` 普通节点。P0 数据源加载固定复用现有 `load_csv` — 表格文件加载普通算子：参数使用相对 `file_path` 和可选时间/列配置，输出 `data`，副作用仅为读取，不得生成规则网格或隐藏业务预处理；明确模型引用加载固定复用现有 `load_model_artifact` — 模型工件加载普通算子：输入/参数为 `model_ref`，输出 `model_ref`、模型对象、特征列表和 metadata，副作用仅为只读查询模型工件。
10. `load_csv` 与 `load_model_artifact` 必须在 machine-readable operator contract、前端目录、冻结 graph、preflight 和 runtime router 中使用同一 `operator_id`、端口与 schema，并由用户手工拖入和连线；二者不计入 12 个 `ts_point_*`。
11. NPY/RData 等 `load_csv` 不支持的非表格格式必须在 G1/G6 前登记独立 adapter-backed 普通 source operator，冻结稳定 ID、端口、schema 和只读副作用后才可入图；不得由 profile 或执行器隐藏加载。
13. `ts_point_*` **尽量**不导入光伏 API、PV registry、设备日或 K4 模块，也尽量不硬编码光伏列名。G2 **建议**用一份非光伏形状的最小 CSV fixture（多实体、不规则间隔、点标签）跑同一 10 个启用算子，用来早发现硬编码；跑不过只记差异，不是 G2/G6 硬失败。
14. 为 Kaggle/NASA/FHC 等公开集改算子或加 loader 时，优先做成通用能力；做成数据集特例可以，但必须在复用报告里写原因。不因此判验收失败。

### R4：槽位级 `global_config` 闭环

1. 每次执行必须显式携带 `slot`；前端执行请求始终发送 `global_config` — 本次槽位内工作流级覆盖配置对象。后端 API 为兼容可接受省略该字段，但必须先规范化为 `{}`，其语义与显式空对象完全相同。
2. 每个 slot 独立维护 `slot_config_ref` — 不可变槽位配置版本，包含该槽位允许的 global config schema、默认值与版本；`pv_day`、`pv_point`、`load_forecast` 和每个 benchmark slot 不得共享可变配置对象。
3. 后端必须先校验 request slot、template slot、slot config ref 一致，再按从低到高“平台无业务默认 → 同槽位 slot defaults → 同槽位模板 metadata → 请求覆盖”生成 `effective_global_config`；等价优先级为“请求覆盖 > 同槽位模板 > 同槽位 defaults > 平台无业务默认”。
4. 四层配置使用同一 canonical deep-merge：JSON object 按 key 递归合并；scalar 和 array 被更高优先级值整体替换，数组不得拼接；`null` 仅在 schema 明确允许时作为真实值覆盖，绝不表示删除；不得做字符串到数字/布尔等隐式类型转换。
5. slot defaults 与模板配置在发布时按完整/模板合同校验；request override 按同一 schema 的 partial patch 规则校验，未知 key 仅在 schema 显式 `additionalProperties=true` 时允许；任一层类型冲突立即失败。完成合并后必须再按完整 schema 校验，校验通过前不得创建 execution。
6. `effective_global_config_sources` — 最终配置逐字段来源映射以 JSON Pointer 叶子路径记录 `platform_default`、`slot_default`、`template` 或 `request`；整体替换的 scalar/array 在其根路径记录胜出来源。digest 使用确定性 key 排序的 canonical JSON 计算，前端预览与后端执行必须使用同一规则。
7. 禁止从另一 slot、最近一次执行、浏览器缓存或同一领域的其他模板回退配置；缺少必需槽位配置时明确失败。
8. `effective_global_config`、`effective_global_config_sources`、`slot_config_ref` 和 digest 必须写入 execution 摘要，供日志、复现、部署和精度运营查看。
9. `global_config` 不得作为普通嵌套参数平铺给所有算子；运行时通过带 slot 的统一 execution context 注入。
10. 请求省略覆盖或显式传 `{}` 时，仍按第 3–6 条执行完整合并：同 slot 模板、同 slot defaults 与平台无业务默认都参与；旧请求的配置只按明确迁移映射进入目标 slot，不允许把旧 `pv_fault` 配置同时复制给天和点。
11. 修改槽位默认配置要产生新 `slot_config_ref`；已提交 execution 和不可变模板继续引用旧版本，不受后来修改影响。

### R5：POC 实时逐点工作流能力

核心工作流由普通节点手工连成，至少支持：

```text
数据加载
→ ts_point_profile_map
→ ts_point_validate_schema
→ ts_point_label_join（仅训练/评估需要）
→ ts_point_causal_impute（只处理已有真实点行）
→ ts_point_temporal_split（训练链）
→ ts_point_causal_window（以当前真实点为终点）
→ ts_point_train_classifier 或加载明确 model_ref
→ ts_point_predict（每个新点立即预测）
→ ts_point_metrics
→ ts_point_candidate_intervals
```

要求：

1. 点源必须保留每条真实记录的实体键、事件时间、原始特征和稳定身份；同实体内按事件时间稳定排序和去重，但不得对时间戳取整、生成规则网格、聚合重采样或补虚拟点。
2. 训练、验证、测试必须先按实体和时间划分，再各自在 split 内按**真实点序列**切窗口，重叠窗口不得跨 split。
3. 每个窗口由“当前目标点 + 同实体此前最多 W-1 个真实点”组成，窗口末端必须等于当前点；允许跨日读取已发生历史，但不得读取当前点之后的记录。
4. `ts_point_causal_impute` 只能在已有点行内做有界 past-only 特征值填充，并保留原始缺失掩码、距上次有效值时长和实际相邻点时间差；不得新增行、backfill 或双侧插值。
5. `ts_point_causal_window` 只产生 `window_result` — 窗口结果，状态为 `ready` 或 `not_ready` 并携带原因；它不得直接持久化业务 `no_decision`。`ts_point_predict` 是 accepted point 唯一的最终 `point_outcome` — 点处理结果 owner：窗口 ready 时输出 prediction，窗口 not-ready、当前必需特征仍缺失或模型合同不匹配时输出带原因的 no-decision，二者必须互斥且不得伪造正常预测。
6. 文件 replay 与未来在线输入必须复用同一个事务合同：从已提交 history 读取过去点 → 把当前点作为 pending point 暂存于本次执行上下文 → 用“已提交 history + pending point”构建当前窗口 → `ts_point_predict` 生成唯一 outcome/evidence → 原子提交当前点到 history、outcome/evidence 和 cursor。提交失败时三者全部不生效，重试不得重复追加历史。
7. 二分类和多分类使用同一工作流合同，由标签映射和 `n_classes` — 类别数量控制。
8. 预测工作流必须消费明确的 `model_ref` — 模型稳定引用，不得隐式重训。
9. 评估必须区分点级指标、事件级指标、检测延迟、误报、无决策率和覆盖率；P0 正式告警状态机不在本链路内。
10. `ts_point_candidate_intervals` 只能消费已提交 `point_outcome`，通过同事务 outbox 或独立幂等投影生成候选区间；候选投影失败不得回滚或重复当前点 outcome，也不得改变 exact-one 结果计数。

### R6：闭环审核与打标保留

1. 工作流结果可把低置信、误报、漏报或代表性区间投影为 `annotation_candidate` — 待审核点/区间候选队列。
2. annotation candidate 必须保留 `annotation_candidate_id` — 标注候选 ID、`source_workflow_id` — 来源工作流 ID、`source_workflow_version` — 来源冻结版本、`source_execution_id` — 来源成功执行 ID、`entity_key` — 实体标识、时间范围、建议标签、置信度和模型引用。
3. 审核用户可以确认、改边界、改类别、新建标签、拒绝和撤销。
4. annotation candidate 状态和生效标签必须分离；未经审核的候选不得成为 `reviewed_annotation`。
5. 公开数据集自带标签以 `benchmark_ground_truth` 导入，可跳过人工审核；它们不能冒充人工裁决。
6. 无专业知识的平台开发者不承担领域金标产出责任。
7. 闭环必须保留 loading、empty、error、disabled、submitting、success 和 conflict 状态。
8. 天、点必须各自维护 `slot_dataset_snapshot` 版本链；审核标注只累计进同 slot 下一版本，历史版本不可修改。
9. 本规格的增量 snapshot builder 只能读取同 slot 的 `reviewed_annotation`，并按 `annotation_role` 排除 locked holdout 泄漏；`domain_import` 与 `pseudo_label` 不得通过该 build API 混入。它们若需进入 learning，必须走独立、显式、可审计的 import/admission workflow，发布单独的不可变 import/base snapshot，或经领域审核后生成新的 `reviewed_annotation`；失败不得覆盖上一可用快照。
10. 重训只消费明确 `snapshot_id@snapshot_version` 并生成同 slot `model_candidate_id`；快照构建、重训、复验和 Promote 必须是四个独立且可审计的动作。
11. **P0b** 验收时 Day 与 Point 各至少完成一次快照版本增长、重训、复验、`set_as_production=true` 的 Promote 和使用新 Champion 的后续预测/回放；这次切换禁止碰现网 `pv_fault` 生产 Champion。P0a 不把本条当退出条件。

### R7：标签来源和准入

| `annotation_source` — 标注来源 | 用途 |
|---|---|
| `benchmark_ground_truth` | 公开基准自带标签，仅用于该基准验证 |
| `reviewed_annotation` | 领域专家审核标签，可按角色进入训练或验收 |
| `pseudo_label` | 模型弱标签；只能经独立显式 admission/import workflow 进入 learning，不由产品增量 snapshot builder 直接接收，禁止进入 locked holdout |
| `candidate_only` | 未审核候选，禁止进入训练真值 |
| `domain_import` | 领域方导入的既有标签；必须走独立显式 import/admission workflow 并记录来源、版本与准入审计，不由产品增量 snapshot builder 直接接收 |

`annotation_role` — 标注用途至少支持 `learning`（训练/调参可用）、`validation`（验证可用）和 `locked_holdout`（只用于最终验收）。任何训练查询都必须排除 `locked_holdout`。

### R8：公开数据集复用验收

公开数据集只用于 P0a 生命周期链通过后的复用验证（建议也等 P0b，但不强制）。规范优先级、用途和准入条件唯一以“0.10 复用验证准备与外部数据顺序”为准；`research.md` — 公开数据集及竞品调研事实记录只提供来源、文件结构和许可证据，不构成第二份实施门槛。NAB、SKAB、`small_tep` 和 GPVS 均为补充验证集，不是 P0a 必选或唯一主线。

最低通过标准：

1. 先按 0.2.1 完成现有 PV 的 P0a 天/点生命周期链，再完成现有光伏冻结快照等价回归，之后才开展外部数据复用验收。P0b 闭环不是 NASA/FHC 下载的前置。
2. NASA SMAP/MSL 与 FHC Twin-Plant 都必须使用相同的普通节点集合、`operator_id` 和手工连线，不允许用隐藏子图或数据集专属组合节点。
3. 数据集之间只修改 profile、相对数据引用、标签映射和允许的模型超参数，不修改 Python/TypeScript 业务代码。
4. 输出可追溯到数据 profile、工作流不可变版本、执行 ID、模型引用和标签来源。
5. 数据许可、下载来源、本地存放策略和是否允许再分发必须有记录；条款未核验的数据不得提交仓库或作为对外交付资产。
6. PVDAQ 只在具体 system 的数据条款核验通过后用于无标签逐真实点 replay 与审核证据演示。若验证审核 UX，只能生成明确位于 benchmark 证据域的 `benchmark_review_session` / `benchmark_review_artifact`，不得直接生成产品 `annotation_candidate` 或 `reviewed_annotation`。benchmark-local execution、artifact、evaluation 和 evidence 可写；由 benchmark execution 直接写产品 `slot_dataset_snapshot`、model candidate、registry、Promote 或正式告警永远禁止，也不得伪装成公开金标准确率验收。未来转产品必须由目标 product slot 的显式 import workflow 新建产品实体。

### R9：ARIMA 与预测型工作流

指定 Kaggle ARIMA 页面只作为预测型工作流参考。平台后续应能用相同的加载、profile、时序划分、评估和工件机制表达：

```text
加载单变量时序
→ 平稳性/差分配置
→ 时间划分
→ ARIMA 训练
→ 未来预测
→ MAE/RMSE/MAPE 评估
```

ARIMA 不是点级故障工作流 P0 的阻塞项，也不能替代异常检测和分类验收。

### R10：领域 profile

光伏 profile 只允许定义：

- `entity_keys` 对 `site_id/device_id/branch_id` 的映射；
- 光伏通道、故障标签字典、K4 来源规则和展示名称；
- 光伏专用阈值、告警策略和权限；
- 现有数据与通用合同之间的适配。

光伏 profile 不得复制通用加载、切窗、训练、预测、评估和审核实现。

### R11：状态、可恢复性和副作用

1. 长时间训练、快照构建、回放评估和重训必须以 activity 运行，状态至少包括 queued、running、succeeded、failed、cancelled。
2. activity 必须返回稳定 `activity_id` — 活动 ID，支持轮询、取消和失败诊断。
3. 失败不得覆盖上一份可用工件、模型 registry 或生效标签。
4. 执行页面刷新后应能恢复最近执行状态；服务重启恢复属于后续增强，但合同必须预留稳定 ID 和持久化摘要。

### R12：路径、安全与兼容

1. 前端只传相对项目根目录的数据路径。
2. 后端持久化模型、快照、执行和审核引用时只存相对路径或稳定 ID。
3. 外部数据默认存放在独立数据目录，不提交到仓库；具体介质由部署配置决定。
4. 旧负荷预测、旧光伏模板和旧审核会话不得因本规格失效。
5. 新合同引入时必须提供旧请求默认和迁移说明，不允许静默改变已有模板语义。

## 5. 竞品启示与产品边界

| 产品 | 可借鉴点 | 本平台采用方式 |
|---|---|---|
| KNIME Components | 组合组件能降低重复，但会隐藏内部节点 | P0 明确不采用子图/组合块；只保留完整模板复制和单节点可见性，后续是否引入另行评审 |
| Azure ML Designer | 注册组件有明确名称、输入、输出和版本，可在拖拽画布复用 | 单个算子合同单一真源、版本化节点、执行产物可追溯 |
| Orange | widget + 示例工作流降低首次使用门槛 | 提供小而完整、节点完全展开的模板和 profile 预设，不为每个行业造页面 |

产品边界是“通用编排与闭环能力”，不是替用户完成领域判断。

## 6. 验收总表

| 成功标准 | 验收证据 |
|---|---|
| 工作流配置链闭合 | UI 请求、API 日志和 execution 摘要中的 `slot_config_ref` 与 `effective_global_config` 一致 |
| 单 slot 隔离 | 模板、配置、execution、snapshot、candidate、verification、registry、部署与精度运营只按一个 slot 分区；跨 slot 写入零副作用失败 |
| 工作流产物唯一来源 | Deployment/Accuracy Operations 的模型和指标都可追溯到 succeeded `source_execution_id` 及 artifact/evaluation ref；页面专属训练/评分实现为 0 |
| 纯手工编排 | 冻结 graph 中每个执行节点都能在画布看见；subgraph/recipe/隐藏自动节点数量为 0 |
| 算子尽量可复用 | 相同 `operator_id` **优先**在两个 benchmark slot 运行；有差异则记录例外 |
| 数据集尽量可替换 | **优先**只切换 profile、slot 和相对路径；确需改算子时记录原因，不因此判失败 |
| POC 逐点语义 | 每个通过 schema/幂等校验并被正式暴露的真实点恰好产生一个 `prediction` XOR `no_decision` 及 evidence；非法/冲突点显式拒绝且 cursor 不推进；没有 grid/resample/虚拟点，未来点扰动不改变当前预测 |
| 审核闭环保留 | 候选可进入通用审核，会话可恢复，审核后才写生效标注 |
| 标签来源可信 | benchmark、人工、弱标签和候选可区分且可追溯 |
| 光伏规则尽量外置 | 通用核心**尽量**无 `pv_fault` 分支；光伏规则优先集中在 adapter/profile |
| 旧能力不回归 | 负荷预测构建通过，现有工作流可加载和执行 |
| 路径可部署 | 持久化结果无本机绝对路径 |

## 7. 外部资料

- [用户指定的 Kaggle ARIMA 页面](https://www.kaggle.com/code/prashant111/arima-model-for-time-series-forecasting) — 动态页面正文未能稳定提取，因此不引用其具体数据集或实现细节。
- [Numenta Anomaly Benchmark](https://github.com/numenta/NAB) — 官方仓库说明其面向流式实时异常检测，并包含带标注异常区间的时序语料。
- [NAB MIT License](https://github.com/numenta/NAB/blob/master/LICENSE.txt) — 首轮基准使用需保留许可与来源记录。
- [Skoltech Anomaly Benchmark](https://github.com/waico/SKAB) — 官方仓库说明其多变量工业传感器字段以及 `anomaly`、`changepoint` 标注。
- [SKAB GPL-3.0 License](https://github.com/waico/SKAB/blob/master/LICENSE) — 使用和分发前需要单独复核合规边界。
- [AIRI FDDBenchmark](https://github.com/AIRI-Institute/fddbenchmark) — 提供 Tennessee Eastman 小型数据入口、dataloader 和检测/诊断指标。
- [KNIME Components](https://docs.knime.com/ap/latest/analytics_platform_components_guide/) — 组件用于隐藏复杂度并在工作流之间复用。
- [Azure ML component pipelines](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-create-component-pipelines-ui?view=azureml-api-2) — 注册组件可在 Designer 中分享和复用。
- [Orange Documentation](https://orangedatamining.com/docs/) — 官方文档提供 visual programming、widget 和 example workflow 入口。

以上外部内容均已按许可合规要求改写和归纳，未复制大段原文。
<!-- @AI_GENERATED: end -->