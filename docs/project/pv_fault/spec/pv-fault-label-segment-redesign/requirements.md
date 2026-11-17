<!-- @AI_GENERATED -->
# 需求文档：光伏故障逐点标签重构（pv-fault-label-segment-redesign）

> 目录名沿用 `pv-fault-label-segment-redesign`（历史命名），但本文档第五轮修订后已放弃「标注段（Label Segment）」这一存储概念，改为**逐点标签**模型。目录未改名以避免破坏 `.config.kiro` 与既有引用。

## 引言（Introduction）

光伏故障诊断链路当前把「训练样本边界」和「标签来源」两件事混在同一批代码里：切分算子 `time_window_split.py`（按时间窗切样本、给每行贴 `time_window` 字符串）既负责产生样本边界，又通过 `time_window` 字符串顺带承担了「这段是人工标的还是系统切的」这一语义；标签则以逐点列的形式散落在两个 parquet、时间切片 CSV、`state.json` 账本和聚类确认结果里，且与测量数据绑在同一行，没有来源、优先级、可撤销性等元信息可挂。结果是重复计数、标签串味、撤销无效、审核页看不到波形等一系列问题。

本次重构建立两个彼此独立的概念：

- **逐点标签（Point Label）** 成为标签的**单一事实来源**：粒度就是采样点，每个点最多有一个生效标签，附带来源、优先级与产生它的标注操作。标签存储与测量数据分表。
- **样本构造策略（Sample Builder）** 是纯函数：读一段连续时序的逐点标签，在**标签形态变化处断开**，输出标签纯一致的样本；策略只决定边界怎么断，不产生也不修改标签。

区间（时间范围）在本模型中只存在于**标注操作日志**里——因为「人在波形图上拖一个框」这个动作天然带区间——但它只是审计与撤销单元，不是标签权威，也不参与样本边界的确定。样本边界完全由逐点标签的形态变化决定，与标注操作当初怎么分块无关。

同时设定一条**架构硬约束：零新增算子**。样本边界的确定被重新定位为「数据准备」而不是「流水线计算」，逐点标签读取、样本构造、`sample_id` 赋值全部在编排层完成，流水线只负责特征与模型。

本阶段交付物仅为本需求文档。本文档不修改任何生产代码，也不预设具体实现结构（实现细节留给设计阶段）。

## 八项已确认的架构决定（K1~K4 第五轮，K5 第六轮，K6 第七轮，K7 第八轮，K8 第九轮）

| 编号 | 决定 | 取代的旧方案 |
|---|---|---|
| K1 | 标签粒度就是**采样点**，不引入「段」这一存储概念；区间只作为标注操作日志存在 | 旧：`label_segments` 段表为标签权威，段是存储实体 |
| K2 | 样本边界由**标签形态变化**决定：一段时序里每一种打过标签的形态就是一条样本，样本内标签纯一致 | 旧：样本必须落在单个段内；混合标签需靠众数或纯度阈值处理 |
| K3 | 标注操作与逐点标签**允许跨天存储**（不强制按自然日断开），使跨天信息不在存储层丢失；但**本 spec 的样本切分只按天**（见 K8），跨天建模由独立的时序 spec 承接 | 旧：第四轮的「需求 4 第 7 条」强制「段不跨自然日」，导致跨天信息在存储层丢失（该条已作废） |
| K4 | 人工框选打标后，**同设备同自然日未被框选的点默认判为正常（`label_id=0`）**，因为人工标注的约定就是「只标有问题的时段」 | 旧：残段默认设为 unknown（`label_id=NULL`）、不继承任何标签 |
| K5 | 白天/夜间**按时钟判定**（`daylight_window`），不按测量值判定 | 旧：沿用 `solar_window._day_night_masks()` 的 `value >= 当天max(value) × 0.05` 值判定 |
| K6 | 切分方式是**单一参数 `split_mode` 的二选一**（扁平、不嵌套）：`by_day`（按天）/ `by_day_night`（白天夜间）；`by_day_night` 是在 `by_day` 基础上再按 `daylight_window` 断开白天与夜间 | 旧（K5 提出时）：`span_mode`（2 选 1）× `split_day_night`（布尔开关）嵌套；（K6 提出时）：三选一含 `by_label_run` |
| K7 | **老的按天建模路径作为一等公民完整保留**，与新的逐点标签路径并存；两条路径在同一评估口径下 A/B 对比精度，胜出者为生产主线、另一条为可回退备选 | 旧：新路径「取代」老路径，老路径仅作迁移期兼容 |
| K8 | **`by_label_run`（跨天时序切分）移出本 spec**，交由独立的 `pv-fault-timeseries-diagnosis` spec 用真正的序列模型承接；本 spec 只保留按天路线（`by_day` / `by_day_night`） | 旧（K3/K6 提出时）：`by_label_run` 作为 RF 路线的一种跨天切分模式留在本 spec |

K5 的成因是一处**循环论证**：按值判定用"出力低"来定义"夜间"，而"出力低"本身往往就是故障症状，导致白天的低出力故障时段被切进夜间样本、再用夜间异常特征（本意抓夜间漏电流）去描述它。实测证据与量化影响见现状与问题第 25、26 项。

K6/K8 的最终形态：切分收敛为 `by_day` / `by_day_night` 两项。K6 提出时曾含第三项 `by_label_run`（跨天时序切分），但 K8 已把它移出本 spec——原因是 `by_label_run` 是个尴尬中间态：既想跨天、又仍走 RF 聚合特征，且预测时无标签只能退化为按天，造成训练/预测特征窗口长度不一致（详见第八轮修订后对该问题的讨论）。跨天/时序建模的真正诉求由独立的 `pv-fault-timeseries-diagnosis` spec 用序列模型承接。两种保留模式在 `pv_cumulative_labeled_merged.parquet` 上的实测样本量分别为 `by_day` 4,457 / `by_day_night` 13,371（见现状与问题第 30 项）。

K7 的动机：本次重构改动面大（标签存储、白天夜间口径、切分方式都变了），不能默认新路径一定更好。老的按天建模路径（现状生产链路）必须保留、可运行、可回退；新旧在同一批数据、同一评估口径下对比精度，用数据而非假设决定谁上生产。落地时复用现有 `backend-service/services/iterative_labeling/split_mode_compare.py`（同一快照上对比多种切分的离线评估）作为对比骨架。详见需求 23。

K2 明确为**单标签**语义：断开后每条样本仍只有一个 `label_id`，不改为多标签分类。该选择使现有单标签 `RandomForestClassifier` 与 `stratified_cv_eval.py` 的单列分层交叉验证保持可用，是「零新增算子」硬约束成立的前提。

## 现状与问题（已实测确认的事实）

以下事实来自在 conda 环境 `cp_web` 中执行的只读探针与对现有代码、数据文件的逐行阅读，作为本文档所有需求的事实依据。为满足项目的相对路径规范，标注工作区文件的完整相对路径前缀为 `backend-service/data/iterative_labeling/`，下文中 `training_workspace/pv_fault/...`、`cumulative_training/pv_fault/...` 均为该前缀下的子路径。

1. 采样间隔为 300 秒（5 分钟），一天理论满值为 288 个采样点。实测该值**不是普遍事实**：对 `pv_cumulative_labeled_merged.parquet` 按 `(site_id, device_id, branch_id, 自然日)` 分组统计，4,457 个设备-天分组的点数分布为 min=144 / median=219 / max=288，多数设备-天存在数据缺失；`dataset_combined.parquet` 的 1,054 个分组则分布为 min=287 / median=288 / max=288，几乎无缺失。武当湖 / 04#箱变_汇流箱01 / 支路1 / 2020-05-08（见第 4 项案例）恰好是满值 288，不能代表通用情况（前置验证探针报告：`docs/specs/pv-fault-label-segment-redesign-preflight-report.md`）。**因此样本必须由时间范围定义、采样点数是结果，不能把「288 点」当作样本定义。**
2. `backend-service/datasets/pv_cumulative_labeled_merged.parquet`（1,056,806 行）与 `backend-service/datasets/dataset_combined.parquet`（303,321 行）**都没有 `time_window` 列**；`label`（故障标签）是天级的，被广播到当天每一行。
3. `cumulative_training/pv_fault/state.json` 现有 4 条 `labeled_imports`（已导入标注批次账本）与 18 条 `verdict_entries`（人工裁决条目）。
4. 真实案例：武当湖 / 04#箱变_汇流箱01 / 支路1 / 2020-05-08。基础数据当天 288 行全带 `label=1`；用户在图上框选 06:00~18:40 打 `label=1`，生成 153 行切片 CSV，切片内 `time_window` 被覆盖成 `2020-05-08T06:00:00__2020-05-08T18:40:00#freeform`。
5. 复现 `cumulative_training._create_snapshot()` 的 concat + drop_duplicates：concat 后 441 行（288 + 153），去重键为 `[time, site_id, device_id, branch_id, time_window]`，**去重后仍是 441 行**——基础侧 `time_window` 为 NaN、自由段侧为字符串，键永不相等，该去重完全失效。
6. 对该快照调用真实 `time_window_split.execute(solar_mode="day_and_night")`，这一天产出 **3 个训练样本**：`2020-05-08`（白天 118 点）、`2020-05-08#night`（夜间 170 点）、`2020-05-08T06:00:00__2020-05-08T18:40:00#freeform`（153 点）。**同一批 153 个点被计入两个样本**，白天样本与自由段样本严重重叠。
7. 自由段的实际语义是「追加一个样本」而非「覆盖修正原样本」；当天未被框选的 135 行照旧带着天级标签被切进白天/夜间样本。
8. 第二个切片：02#箱变_汇流箱07 / 2020-05-07 06:20~17:55，140 行，`label=11`，而基础数据当天 288 行也全是 `label=11`。
9. 夜间判定按自然日计算 `max_power` 阈值：某设备一天 288 点中有 170 点被判为「夜间」（约 14 小时），清晨与黄昏的有效发电时段被吞进夜间样本。
10. 数据库 `training_samples` 表的唯一约束是 `UniqueConstraint(time, site_id, device_id, branch_id)`，`label` 是逐点列——测量数据与标注被强行绑在同一行，导致「测量只增不改、标注可反复修正」这两种截然不同的生命周期无法分开演进，且逐点 `label` 上没有任何位置可挂 `source`、`priority`、`reviewer`、`status` 等元信息。**这是「现状的逐点标签」与本次重构「逐点标签表」的根本区别：前者是测量表上的一个裸列，后者是独立表 + 操作日志。**
11. `sample_id` 语义的四种混用形态并存：`Timestamp('2020-05-08 00:00:00')`（关闭切分模式时 resample 产生的 DatetimeIndex）、`'2020-05-08'`（daylight）、`'2020-05-08#night'`、`'2020-05-08T06:00:00__2020-05-08T18:40:00#freeform'`；`unit_key`（审核单元键）另有三套互不兼容格式：`site|dev|br|{time_window原样}`（from-prediction）、`site|dev|br|{YYYY-MM-DD}`（from-dataset）、`site|dev|br|freeform|{start}|{end}`（freeform）。归一化代码在 `backend-service/services/iterative_labeling/backfill.py` 和 `backend-service/api/iterative_labeling.py` 各存在一份副本。
12. `time_window_split.py` 已内置透传通道：`_is_preserved_time_window()`（判定 `time_window` 是否为需原样保留的显式窗口键，判据是文本中含 `#`）与 `_split_preassigned_windows()`（把这些行整体摘出）；`execute()` 中 `if df_input.empty` 分支位于 `elif solar_mode` 分支之前。该透传行为已由前置探针实跑验证（见第 22 项）。
13. `PVTrainingWorkspaceService.set_workflow_split_parity()` 与 `PVTrainingWorkspaceService._read_workflow_split_parity()`（读写训练/预测模板中 `solar_mode` 以核对切分是否对齐）现被 `backend-service/api/iterative_labeling.py` 的多个路由与 2 个测试引用。
14. 夜间异常特征实际产出 **5 列**，定义在 `backend-service/services/operator_backends/night_anomaly.py` 的 `compute_night_anomaly_features()` 返回值：`night_nonzero_current_ratio`（夜间电流非零点占比）、`night_current_mean`（夜间电流均值）、`night_current_max`（夜间电流绝对值最大值）、`night_over_threshold_duration`（夜间超阈值点数）、`night_power_residual_mean`（夜间功率残差均值）。
15. 标签注册表已存在且是 `label_id` 的分配真源：`backend-service/services/iterative_labeling/label_registry.py` 的 `LabelRegistryService` 提供 `allocate_label(label_name)`（分配单调递增标签 ID）、`reconcile_labels(labels_by_id)`（按数据集中已存在的 `label_id` 补齐业务名称、不重新分配编码）、`get_current()`（只读当前标签空间），持久化在 `backend-service/data/iterative_labeling/label_registry.json`。该文件中 `pv_fault` 槽位当前 `label_space_version`（标签空间版本）为 `ls-v2`，含 13 个标签；`label_id = 0` **已被占用为「正常」**（K4 决定依赖该约定）；`label_id` 存在跳号（缺 5、13、14、15），符合「单调递增、永不复用」的约定；其中 5 个标签名为「待命名-故障码2/3/6/9/10」、`source` 字段为 `snapshot_reconciliation`。
16. `stratified_cv_eval.py` 的 `_build_Xy()` 在构造特征矩阵时先 `drop` 掉 `drop_cols = {target_col, "time", "time_window"} | id_fields`，随后执行 `non_numeric = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]` 并把这些非数值列一并 `drop`。**任何字符串列都进不了特征矩阵。**
17. 时间切片的时间范围是**闭区间**：`training_workspace/pv_fault/time_slices/slice-b0c42870f030.meta.json` 记录 `time_start = 2020-05-08 06:00:00`、`time_end = 2020-05-08 18:40:00`、`row_count = 153`。06:00 到 18:40 按 5 分钟采样共 152 个间隔，152 + 1 = 153，说明 `18:40` 这个采样点被包含在内（`create_confirmed_time_slice()` 的过滤条件是 `df["time"] <= time_end`）。
18. `cumulative_training.py` 中重训阈值默认值 `_DEFAULT_RETRAIN_LABEL_THRESHOLD = 20`，可由环境变量 `PV_RETRAIN_LABEL_THRESHOLD` 覆盖；`admit_verdict()` 对同一裁决重复提交返回 `admitted=False`、`reason="duplicate_verdict"` 且不递增 `pending_change_count`（待处理变更计数）。实测 `state.json` 中一条自由段导入记录的 `change_units` 取值为 `1`——**一次人工操作计一次变更，不按采样点数计**（K4 决定使一次框选影响的点数从 153 涨到约 288，若改为按点计数则一次拖拽即超过阈值 20 并立刻触发重训，故该计数口径必须保持）。
19. `stratified_cv_eval.py` 的 `_merge_feature_frames()`（三路特征表合并函数）以**含 `target_col`（本场景即 `label`）的那一路特征表**为合并基表：`base = next((f for f in frames if target_col in f.columns), None)`，其余各路按共同 id 列 `how="left"` 接入。实测训练模板 `backend-service/data/workflows_enhanced/workflow-pv-fault-diag-quickval-cv-v1.json` 中，只有统计特征节点 `qv-extract_statistical_features-n7` 的 `id_fields` 含 `label`（实测取值 `["site_id","device_id","branch_id","time_window","label"]`），`tsfresh_extract` 与 `ts_comparison_features` 两路均不含。**因此统计特征表就是合并基表，样本级常量列只需从这一路透传即可到达 `stratified_cv_eval`。**
20. `_merge_feature_frames()` 在接入非基表的各路时按 `new_cols = [c for c in f.columns if c not in merged.columns]` 只取新列，**与基表同名的列被静默跳过**（不报错、不加后缀、不覆盖）。若透传列名与 `tsfresh_extract` 或 `ts_comparison_features` 的输出列同名，该冲突在运行期不可见。
21. `time_window_split.py` 的 `attach_night_features`（是否附加夜间异常特征）与 `solar_mode` 一样，在全透传模式下彻底不生效：`execute()` 中 `preassigned, df_input = _split_preassigned_windows(data)` 摘走所有含 `#` 的行后 `df_input` 为空，随后 `if df_input.empty` 分支先于 `elif solar_mode` 分支命中，`solar_window.segment_solar_window()` 与 `attach_night_anomaly_features()` 都进不去。实测该模板 `qv-time_window_split-n4` 节点同时配置了 `solar_mode="day_and_night"`、`power_col="value"`、`irr_threshold=0.05`、`attach_night_features=true` 四个参数，全部只在非透传路径下才被读取。同一函数中 `window` 为空会抛 `ParameterError`、`time_field` 不在列中会抛 `InputError`，这两个参数在透传模式下仍是必需的。
22. `solar_window.segment_solar_window()` **现已按自然日隐式分组**：`group_keys = actual_id_cols + ["_date"]`，其中 `_date` 由 `dt.normalize()` 取整。这意味着「夜间」在现状实现中本来就在 00:00 处被截断成两段，物理连续的一整晚从未被表达过；`_day_night_masks()` 的 `max_power`（判定白天/夜间的功率阈值）也是在该自然日分组内计算的。K3 决定把这个隐式截断从「隐藏在算子内部的强制行为」改为「策略层的显式可选项」。
23. 迁移前置验证探针（Preflight_Probe，需求 15）已在 conda 环境 `cp_web` 实跑，完整报告见 `docs/specs/pv-fault-label-segment-redesign-preflight-report.md`。关键实测结果：
    - **全 `#` 透传断言：通过**（场景 A 全含 `#`、场景 B 半含 `#` 半为 NaN 的混合分流均验证通过），需求 9 的零新增算子方案的透传假设成立。
    - **现状缺陷基线：与文档记录完全一致**（concat 441 行、去重后仍 441 行、产出 3 个样本、点数 118/170/153）。
    - **「同设备同天 label 不唯一分组数」：两个 parquet 均为 0**。两份源数据都是纯天级批量标注，不含任何子天级人工时段信息；人工的精确时段标注只存在于 `time_slices/` 的 2 个自由段切片与 `state.json` 的 18 条 `verdict_entries` 中（合计仅 20 条）。该结论对本次迁移的意义：批量导入的每个设备-天恰好只有一个 `label` 取值，因此可按设备-天生成标注操作（每组一条，共 4,457 条），不存在同组内多标签需要拆分的情形。
    - **两 parquet 重叠**：`dataset_combined.parquet` 的 303,321 行全部与 `pv_cumulative_labeled_merged.parquet` 重叠（即前者是后者的子集），重叠处 0 行标签冲突，故前者判定为完全冗余源、不参与迁移。
    - **按标签变化断开后的样本数**：第四轮探针曾用 `groupby.transform` 得出「473 个连续区间」，**该数字已证伪**（run 跨越了设备边界；识别线索是它算出单个 run 最长覆盖 18 天，而实测单设备支路最多只有 7 天）。用显式分组边界（设备键变化 OR 标签变化）重算的实测值为：仅按标签变化不断天 **2,699** 条（其中 934 条跨天、占 34.6%，单样本点数 144/287/2,015；该口径对应已移出本 spec 的 `by_label_run`，现归属时序 spec），加自然日边界断开 **4,457** 条（`by_day`，单样本点数 144/219/288）。该数据集含 2,226 个 device-branch 组、4,457 个 device-branch-day 组，单设备支路覆盖天数 min/median/max = 1/1/7。
    - **日照阈值口径敏感度**：对 934 条跨天样本（642,574 点）比较「按整段 max_power」与「按自然日 max_power」两种阈值口径，白天/夜间归属在 30,818 点（4.80%）上不一致、630 条样本受影响。结论：跨度可以跨天，但 `max_power` 阈值必须按自然日计算（见需求 7 第 16 条），现有 `solar_window.py` 的按自然日分组行为在这一点上是正确的。
    - **reconcile 范围**：两个 parquet 中出现的 `label_id` 全部已存在于当前 `label_space_version=ls-v2` 标签空间中，本次迁移**不需要**触发 reconcile。
    - **事实基线**：`state.json` 的 `labeled_imports`（4 条）、`verdict_entries`（18 条）、`time_slices/` 两个切片行数（153、140）均与文档记录一致；唯一不一致项已在第 1 项修正（单设备单日点数非恒为 288）。
24. 自由段标注的输入源文件跨多天多设备，「未框选部分」的范围必须显式限定：实测 `backend-service/data/iterative_labeling/prediction_inputs/pv_fault/pred-20260720092117-9348327a.csv`（两条自由段标注的共同来源）含 97,920 行、**189 个设备**，时间跨 **5 个不连续的自然日**（2020-05-06 / 05-07 / 05-08 / 2021-08-22 / 2021-08-29）。若不限定范围，K4 的「未框选部分判为正常」会被误解为覆盖该文件全部 189 个设备与 5 天。

25. **按值判定白天/夜间的实测缺陷**（K5 的直接依据）。对 `pv_cumulative_labeled_merged.parquet` 复用现有 `solar_window._day_night_masks()` 口径（阈值 = 当天 `max(value)` × `irr_threshold=0.05`）逐点判定，结果与「清晨夜间 + 白天 + 傍晚夜间」这一物理直觉严重不符：
    - 全库 1,056,806 点中判为夜间 **534,277 点（50.6%）**。
    - 4,457 个设备-天中，夜间连续段数恰为 2（符合直觉的形态）的只有 **2,234 个（50.1%）**；夜间连续段数 **>2 的有 1,596 个（35.8%）**，最多的一天被切成 **43 段**；白天被中途打断（白天段数 >1）的有 1,663 个（37.3%）；整天全判为夜间的有 365 个。
    - 按小时统计被判为夜间的点占比：00–05 时约 91%、06 时 72.9%、07 时 39.6%、08 时 22.9%、**09–15 时 13%~18%**、16 时 19.7%、17 时 37.8%、18 时 75.7%、19–23 时约 91%。**正午 12 点仍有 12.6% 的点被判为「夜间」**——这些不是夜晚，是云遮、限电或故障本身导致出力掉到当天峰值 5% 以下的点。
    - 该缺陷解释了现状与问题第 9 项记录的「某设备一天 288 点中 170 点被判为夜间（约 14 小时）」：并非真有 14 小时夜晚，而是约 5 小时的白天低出力时段被误归入夜间。
26. **按时钟判定白天/夜间的实测可行性**（K5 的可行性依据）。以固定时钟窗 06:00–18:00 判定：
    - 夜间点 **429,509（40.6%）**，与按值判定的 534,277（50.6%）相比，两口径判定**不一致 189,790 点（18.0%）**；其中「按值=夜间但时钟=白天」147,279 点（白天低出力被误判为夜间）、「按值=白天但时钟=夜间」42,511 点（夜间确有出力，正是要抓的异常）。
    - 「夜间无电流」这一物理先验在时钟口径下成立：夜间点 `value` 零值占比 **75.12%**、`i_cal` 零值占比 **94.47%**、两者中位数均为 0；同口径白天点 `value` 零值占比仅 14.62%、`i_cal` 仅 5.96%、`value` 中位数 1.80。
    - 时钟口径下「夜间非零电流占比」对故障类型有强区分度（按 label 统计）：label 1 = 7.45%、2 = 12.80%、11 = 15.05%、12 = 16.17%、6 = 17.62%、0 = 28.59%、7 = 60.22%、3 = 65.53%、16 = 66.89%、4 = 76.61%、8 = 90.19%、10 = 100.00%。跨度从 7.45% 到 100%，说明 5 个 `night_*` 夜间异常特征在正确的时段口径下是有效特征；而按值判定口径把正午点混入夜间，会污染这组特征。
27. **日照时长有季节与站点差异，固定时钟窗不足以覆盖全部**。`pv_cumulative_labeled_merged.parquet` 实测覆盖 **8 个站点、7 个月份**（2020-05、2021-08、2021-10、2021-11、2022-01、2022-02、2022-03）。按月统计设备-天的「末个有出力时刻」中位数：2021-11 为 16.50 时、2021-08 为 18.25 时、2022-03 为 18.42 时、2020-05 为 19.08 时；「首个有出力时刻」中位数在 6.08~7.08 时之间（部分月份因夜间漏电流导致该统计量被拉到 0，说明不能直接用「首个 `value>0` 时刻」作为日照起点）。因此 `daylight_window` 需按站点与月份取值，固定窗只作兜底。
28. **全项目无站点经纬度数据**。对 `backend-service/` 全量检索 `latitude` / `longitude` / `lat` / `lon` / `lng` / 经度 / 纬度均无命中，也不存在站点元数据表；仅 `backend-service/scripts/generate_kaggle_solar_data.py` 中有「日出约 6 点、日落约 18 点」的硬编码假设（用于生成演示数据）。因此**无法按天文日出日落计算 `daylight_window`**，只能用固定窗或经验推导。
29. **夜间存在异常量级坏值**。按时钟 06:00–18:00 切出的夜间点中，`value` 绝对值最大达到 **1.04e11**（`i_cal` 最大为 1.75，量级正常），明显是坏值而非物理量，需在预处理阶段拦截，否则会污染 `night_current_max` 等夜间特征。
30. **保留的两种切分模式的实测样本量与 `min_points` 影响**（K6/K8 依据）。对 `pv_cumulative_labeled_merged.parquet` 用固定时钟窗 06:00–18:00 判定白天/夜间，`min_points=12` 过滤，实测：
    - `by_day`：4,457 样本，0 被过滤，点数 144/219/288，无跨天。
    - `by_day_night`：**13,371** 样本（= 4,457 白天 + 8,914 夜间），0 被过滤，点数 34/72/144。夜间样本恰好对称拆为清晨段（4,457 条，00:00~06:00）与傍晚段（4,457 条，18:00~24:00）。
    - 两种模式在 `min_points=12` 下均无样本被过滤，最小样本 34 点仍高于阈值。
    - **历史参考（已移出本 spec，归属时序 spec）**：`by_label_run`（仅按标签变化断开、不断天）实测 2,699 样本、点数 144/287/2,015、其中 934 条（34.6%）跨天。该模式按 K8 移出，不再是本 spec 的切分选项。
    - **`by_day_night` 的已知取舍**：夜间样本点数中位数仅 39，夜里发电为零，其统计特征（均值/方差等）近乎常量，区分度几乎完全来自 5 个 `night_*` 夜间异常特征；该模式把样本数从 4,457 撑到 13,371，多出的 8,914 条夜间样本的价值高度依赖 `night_*` 特征质量（因此需求 7 第 16e 条的夜间坏值拦截对该模式尤其关键）。

## 术语表（Glossary）

字段名与标识符统一使用英文，首次出现附中文含义。

- **point_labels** — 逐点标签表；标签的单一事实来源，一行一个采样点。字段定义见需求 2 第 1 条。
- **label_ops** — 标注操作日志表；一行记录一次标注动作（人工框选、审核裁决、聚类确认、批量导入、伪标签），是**撤销与审计的唯一单元**。字段定义见需求 2 第 2 条。
- **Point_Label_Service** — 逐点标签服务；负责标注操作的受理、逐点标签的物化、撤销与重物化，是标签的唯一写入入口。
- **Label_Registry_Service** — 标签注册表服务，即现有 `LabelRegistryService`。
- **Label_Materializer** — 标签物化器；输入某设备某时间范围内的全部 active 标注操作，输出该范围每个采样点的生效标签（逐点取最大 `priority`）。取代旧方案的「段裁剪器」，不做任何区间差集运算。
- **Sample_Builder** — 样本构造器；纯函数集合，读一段连续时序的逐点标签，在标签形态变化处断开，输出标签纯一致的样本。
- **Snapshot_Builder** — 快照构建器；编排层组件，读逐点标签 + 测量数据，预物化出已带 `sample_id` 的训练快照 parquet。
- **Inference_Sample_Generator** — 推理样本生成器；预测场景下按模型持久化的策略生成无标签样本，不写库。
- **Migration_Tool** — 迁移工具；把 4 个历史标签来源一次性迁入 `point_labels` 与 `label_ops`，并产出对账报告。
- **Preflight_Probe** — 前置验证探针；迁移前运行的只读探测程序（已实跑，见现状与问题第 23 项）。
- **Training_Pipeline** — 训练流水线；由工作流模板描述的算子 DAG，本次重构后只负责特征工程与模型训练评估。
- **Labeling_API** — 标注接口层，即 `backend-service/api/iterative_labeling.py` 暴露的 HTTP 路由集合。
- **Review_UI** — 审核前端页面，即 `frontend-sevice/src/pages/IterativeLabelingReviewPage.tsx`。
- **Accuracy_Evaluator** — 精度评估组件，含 `backend-service/services/iterative_labeling/accuracy_evaluator.py` 与运营面板 `frontend-sevice/src/pages/accuracy-operations/PvFaultSplitModeOpsPanel.tsx`。
- **Cumulative_Training_Service** — 累积训练服务，即 `backend-service/services/iterative_labeling/cumulative_training.py`；负责 `state.json` 状态机、`pending_change_count` 计数与重训触发。
- **training_samples** — 测量数据表；重构后退化为纯测量数据表，`label` 列废弃。
- **label_run** — 标签形态连续区间；同一 `(site_id, device_id, branch_id)` 下按时间排序后 `label_id` 取值连续相同的最大采样点区间。它是**运行期计算出的中间结果，不落任何表**，用于确定样本边界。
- **op_id** — 标注操作唯一标识；格式 `op-{hex12}`。
- **source** — 标签来源，取值见需求 3 第 1 条。
- **priority** — 覆盖优先级，由 `source` 唯一决定。
- **rest_of_day_policy** — 未框选时段处置策略；人工框选打标时的取值 ∈ `{normal, untouched}`，默认 `normal`（即 K4）。
- **op_scope** — 标注操作的作用范围；`(site_id, device_id, branch_id, 自然日)` 四元组，界定 `rest_of_day_policy` 生效的边界（依据见现状与问题第 24 项）。
- **max_op_span** — 标注操作最大跨度；操作不变量之一，默认 31 天，用于兜住源数据异常导致的无界长操作（见需求 5 第 12 条）。
- **label_source** — 样本的主标签来源；取该样本内点数最多的 `source` 取值，随快照透传至评估侧（见需求 3 第 17 条）。
- **label_source_purity** — 主来源纯度；主来源点数占样本总采样点数的比例，取值 (0, 1]。
- **label_op_id** — 样本的主标签来源操作标识；用于把样本追溯回产生其标签的标注操作。
- **sample_id** — 训练样本唯一标识；格式见需求 8 第 1 条；训练样本用 `smp-` 命名空间，推理样本用 `inf-` 命名空间。
- **period_role** — 样本在时段维度上承担的角色，取值域为 3 个：`whole`（未启用白天/夜间划分时的整段）、`daylight`（白天）、`night`（夜间）。第六轮删除了原有的 `peak` / `trans` / `sub` 三个取值（见 K5 与第六轮修订表 Q3）。
- **period_is_\*** — `period_role` 的 one-hot 数值列（`period_is_whole` / `period_is_daylight` / `period_is_night`），取值 0/1。
- **daylight_window** — 日照时钟窗；某站点某季节桶（月份 1~12）的白天起止时刻 `[daylight_start, daylight_end)`，**按时钟判定白天/夜间的唯一依据**，与当日测量值无关（见需求 7 第 16 条）。
- **daylight_window_source** — 日照窗来源；取值 `empirical`（按 `(站点, 季节桶)` 从跨天聚合的时段功率中位曲线推导，只用近期回溯窗内数据，默认）或 `fixed`（使用配置的固定时刻，兜底）。
- **daylight_window_lookback_months** — 近期回溯月数；`empirical` 推导只使用数据集最新时间戳向前 N 个月内的数据，默认 24；避免早期衰减/遮挡变化的数据主导当前日照窗（见需求 7 第 16a 条）。
- **季节桶（seasonal bucket）** — 月份序号 1~12；日照窗的分组键之一，跨年份的同一月份共用一个桶，捕捉季节性同时让样本更充足。
- **group_key** — 防泄漏分组键，取值 `{site_id}|{device_id}|{branch_id}|blk{n}`，其中 `blk{n}` 是该设备维度下按自然日连通块（day-block）分配的块序号；口径与不变量见需求 10 第 6 条。该定义不引用单一自然日，因而不限制样本跨天。
- **day-block** — 自然日连通块；同一 `(site_id, device_id, branch_id)` 下，把每个样本映射为它覆盖的自然日集合，再对「日集合有交集」这一关系取连通分量，每个连通分量即一个 day-block。
- **label_space_version** — 标签空间版本；由 Label_Registry_Service 维护（现 `pv_fault` 槽位为 `ls-v2`）。
- **migration_batch_id** — 迁移批次标识；标记一条标注操作由哪次迁移产生，人工新增操作该字段为 NULL。
- **label_snapshot_hash** — 逐点标签内容哈希；定义见需求 21 第 8、9 条。
- **min_points** — 样本最小采样点数；样本构造的后置过滤阈值，默认 12。
- **pending_change_count** — 待处理变更计数；**按标注操作计数，不按采样点计数**（依据见现状与问题第 18 项）。
- **unknown 点** — 在 `point_labels` 中 `label_id` 为 NULL、或未被任何 active 标注操作覆盖的采样点；语义是「该点真实状态未知」。

## 需求（Requirements）

### 需求 1：标签与样本构造的概念分离

**User Story:** 作为算法平台维护者，我希望「标签从哪来」和「样本边界怎么切」是两个互不干涉的概念，以便我能独立修正标注而不影响样本构造逻辑，也能替换样本策略而不动标签。

#### 验收标准（Acceptance Criteria）

1. THE Point_Label_Service SHALL 把标签表达为逐采样点的记录，每条记录包含「设备 + 采样时刻 + 标签 + 来源 + 优先级 + 产生它的 `op_id`」，且不含任何测量数值列。
2. THE Sample_Builder SHALL 以 `build_samples(labeled_rows, strategy)` 形式提供纯函数接口，其输出样本的标签取自入参逐点标签，不查询任何表。
3. THE Sample_Builder SHALL 对入参只读，不写回 `point_labels`、不修改任何 `label_id`。
4. THE point_labels 表与 label_ops 表 SHALL 不包含任何表示日照切分模式的字段（现 `solar_mode` 语义不得进入标签存储）。
5. THE Sample_Builder SHALL 把白天/夜间划分（`split_mode=by_day_night`）归类为样本构造策略的一种，其唯一作用是提供样本边界，且不改变样本标签。
6. THE 本次重构 SHALL 不引入任何以「区间」为标签权威的存储实体；区间仅以 `label_ops` 的 `t_start`/`t_end` 形式存在，且该字段只用于审计、撤销与重物化，不参与样本边界的确定。
7. THE Sample_Builder SHALL 使样本边界只依赖逐点标签的形态变化与所选策略，不依赖标注操作当初的分块方式；WHEN 同一批逐点标签由不同的 `label_ops` 分块方式产生，THE Sample_Builder SHALL 输出相同的样本集合。

### 需求 2：逐点标签表与标注操作日志表

**User Story:** 作为后端开发者，我希望标签有稳定明确的表结构和索引，以便按设备与时间范围高效查询、并能追溯每个点的标签来自哪次人工操作。

#### 验收标准

1. THE point_labels 表 SHALL 包含下列字段：`site_id` — 站点标识、`device_id` — 设备标识、`branch_id` — 支路标识、`time` — 采样时刻、`label_id` — 标签 ID（可为 NULL 表示 unknown）、`source` — 标签来源、`priority` — 覆盖优先级、`op_id` — 产生该生效标签的标注操作标识、`label_space_version` — 写入时的标签空间版本、`updated_at` — 更新时间；主键为 `(site_id, device_id, branch_id, time)`。
2. THE label_ops 表 SHALL 包含下列字段：`op_id` — 操作唯一标识（格式 `op-{hex12}`）、`site_id`、`device_id`、`branch_id`、`t_start` — 区间起点（闭）、`t_end` — 区间终点（开）、`label_id` — 该操作声明的标签、`source` — 标签来源、`priority` — 覆盖优先级、`status` — 操作状态（`active` / `revoked`）、`reviewer` — 标注人、`source_ref` — 溯源引用（`review_id` / `cluster_run_id` / `import_id` / `slice_id`）、`rest_of_day_policy` — 未框选时段处置策略、`parent_op_id` — 伴生操作指向的主操作（见需求 5 第 4 条）、`label_space_version`、`migration_batch_id`、`created_at`、`updated_at`。
3. THE label_ops 表 SHALL 把时间范围解释为左闭右开区间 `[t_start, t_end)`。
4. WHERE `point_labels.label_id` 为 NULL，THE Point_Label_Service SHALL 把该点解释为 unknown（真实状态未知、待标注）。
5. WHERE 某点的 `label_id` 为 NULL 或该点在 `point_labels` 中不存在记录，THE Snapshot_Builder SHALL 把该点排除在训练集之外。
6. THE point_labels 表 SHALL 建立索引 `(site_id, device_id, branch_id, time)`（即主键）与 `(op_id)`；THE label_ops 表 SHALL 建立索引 `(site_id, device_id, branch_id, t_start, t_end)` 与 `(source, status)`。
7. THE training_samples 表 SHALL 退化为纯测量数据表，其 `label` 列 SHALL 标记为废弃并保留以兼容历史数据。
8. THE 重构后的训练集构建路径 SHALL 从 point_labels 表读取标签，不读取 training_samples 表的 `label` 列。
9. THE training_samples 表 SHALL 只接受新增测量行，标注修正不触发该表更新。
10. IF 一条 point_labels 或 label_ops 记录携带测量数值列，THEN THE Point_Label_Service SHALL 拒绝写入并返回校验错误。
11. THE point_labels 表 SHALL 不存储同一采样点的多条并存记录；同一点的历史由 label_ops 表承载（见需求 6）。

### 需求 3：标签来源分级与按来源分口径评估

**User Story:** 作为算法负责人，我希望每个点的标签都标明来源与可信等级，以便冲突时有确定的裁决顺序，并能回答「模型在人工精标点上到底多准」。

#### 验收标准

1. THE Point_Label_Service SHALL 支持且仅支持下列 `source` 取值与对应 `priority`：`human_range` = 100（人工在图上框选的精确时段）、`human_day` = 80（人工对设备-天或时段单元的裁决，含 K4 的伴生「其余时段判正常」操作）、`cluster` = 50（聚类批量命名后二次确认）、`day_label` = 10（历史天级批量标注）、`pseudo` = 0（高置信伪标签）。
2. THE Point_Label_Service SHALL 由 `source` 唯一推导 `priority`。
3. IF 写入请求显式指定 `priority`，THEN THE Point_Label_Service SHALL 拒绝该请求并返回 HTTP 422 状态码。
4. WHERE `source` 取值为 `pseudo`，THE Snapshot_Builder SHALL 默认不把该点纳入训练集，且仅在调用方显式开启伪标签开关时纳入。
5. THE Accuracy_Evaluator SHALL 支持按 `source` 分组输出精度指标，使评估结果能区分人工精标点与天级批量标注点。
6. THE Accuracy_Evaluator SHALL 输出每个 `source` 的点覆盖率（该来源生效的采样点数占该设备总采样点数的比例）。
7. THE 运营面板 `PvFaultSplitModeOpsPanel.tsx` SHALL 由「切分模式对比」改为展示各 `source` 的点覆盖率与精度分布，因重构后不存在可对比的切分模式配置。
8. IF 该运营面板读不到按 `source` 聚合的新数据，THEN THE 运营面板 SHALL 渲染空态提示并保持页面可交互（不白屏、不抛未捕获错误）。
9. WHILE 该运营面板处于数据请求进行中，THE 运营面板 SHALL 渲染加载态。
10. IF 该运营面板的数据请求失败，THEN THE 运营面板 SHALL 渲染错误态与重试入口。
11. THE Point_Label_Service SHALL 把 `inference`（推理标记）排除在 `source` 枚举值之外；推理样本不落库，其约束见需求 12 第 8 至第 12 条。
12. THE Accuracy_Evaluator SHALL 把 unknown 点排除在精度计算之外（unknown 点无真值，不可评估）。
13. THE Accuracy_Evaluator SHALL 在评估报告中输出被排除的 unknown 采样点数与其占本次评估范围总采样点数的比例。
14. WHERE 按 `source` 分口径展示，THE Accuracy_Evaluator SHALL 把 unknown 单独列为一类并只展示覆盖率指标，不参与精度计算。
15. WHILE 某设备某时段的点为 unknown，THE Inference_Sample_Generator SHALL 照常为该时段生成推理样本并产出预测结果（预测不受 unknown 影响）。
16. WHEN 按 `source` 分组输出精度指标（第 5、6 条），THE Accuracy_Evaluator SHALL 从特征表中经 `passthrough_fields`（常量列透传字段，见需求 11 第 8 条）透传的 `label_source` 列读取来源取值，不重新查询 point_labels 表，使评估口径与训练时实际使用的样本严格对应。
17. WHERE 一条样本内的采样点来自多个 `source`（例如框选部分为 `human_range`、其余部分为 `human_day`），THE Snapshot_Builder SHALL 使该样本的 `label_source` 取该样本内点数最多的 `source`，并额外输出 `label_source_purity`（主来源点数占样本总点数的比例）供评估侧过滤；因样本已按标签形态断开（需求 7 第 6 条），该情形只发生在标签相同而来源不同时，不影响标签正确性。

#### 来源与现有写入路径的对应关系（供设计阶段定位改造点）

| `source` | `priority` | 现有写入路径 |
|---|---|---|
| `human_range` | 100 | `backend-service/services/iterative_labeling/freeform_labeling.py` 的 `create_label()` — 图上框选打标 |
| `human_day` | 80 | `backend-service/services/iterative_labeling/review_session.py` 的 `submit_verdict()`（confirm / correct / new_label）→ 写入 `state.json` 的 `verdict_entries`；以及 K4 的伴生「其余时段判正常」操作 |
| `cluster` | 50 | `backend-service/services/iterative_labeling/pv_training_workspace.py` 的 `confirm_clustering_run()` — 聚类批量命名后二次确认 |
| `day_label` | 10 | `backend-service/datasets/pv_cumulative_labeled_merged.parquet` 的逐点 `label` 列（`dataset_combined.parquet` 经探测确认为其完全子集，按需求 14 第 3 条不参与迁移） |
| `pseudo` | 0 | `backend-service/services/iterative_labeling/pseudo_backfill.py` — 高置信伪标签 |

### 需求 4：标签物化规则（取代旧方案的段裁剪算法）

**User Story:** 作为算法平台维护者，我希望多来源标注的冲突能按一条简单确定的规则解决，以便我不需要理解任何区间差集运算就能预测标签结果。

#### 验收标准

1. THE Label_Materializer SHALL 按下列规则确定每个采样点的生效标签：在覆盖该点的所有 `status='active'` 标注操作中，取 `priority` 最大者；`priority` 相同时取 `created_at` 最新者；`created_at` 也相同时取 `op_id` 字典序最大者。
2. THE Label_Materializer SHALL 不执行任何区间差集运算，不产生残段、裂段、父子段等派生实体。
3. THE Label_Materializer SHALL 保证同一采样点在 `point_labels` 中只有一条记录（由需求 2 第 1 条的主键强制）。
4. THE Label_Materializer SHALL 对同一输入操作集合的任意输入顺序产出相同的逐点标签结果（顺序无关性）。
5. WHERE 某采样点未被任何 `status='active'` 标注操作覆盖，THE Label_Materializer SHALL 把该点写为 `label_id=NULL`（unknown）或不写入 `point_labels`，两种表示 SHALL 被下游等价对待。
6. THE Migration_Tool SHALL 依据 `state.json` 中 `labeled_imports` 的 `sequence`（导入登记序号）字段合成迁移产生的 `day_label` 操作的 `created_at`，使第 1 条的同 `priority` 裁决有确定依据（两个源 parquet 本身均无 `created_at`）。
7. WHEN 一条标注操作被新增、撤销或修改，THE Label_Materializer SHALL 只重物化该操作 `[t_start, t_end)` 范围内、该设备维度下的采样点，不全表重算。
8. THE Label_Materializer SHALL 提供可独立运行的一致性校验程序，对给定设备与时间范围重算逐点标签并与 `point_labels` 现有内容比对，输出差异明细。

### 需求 5：标注操作不变量与「未框选即正常」规则

**User Story:** 作为标注人员，我希望「我只标有问题的时段」这一习惯被系统正确理解为「其余时段是正常的」，同时这个假设是显式记录的而不是被系统猜出来的。

#### 验收标准

1. THE Point_Label_Service SHALL 强制 `t_start < t_end`。
2. THE Point_Label_Service SHALL 强制 `t_start` 与 `t_end` 对齐到采样点栅格（实测采样间隔为 300 秒 / 5 分钟）。
3. WHERE `source` 以 `human_` 开头，THE Point_Label_Service SHALL 要求 `reviewer` 与 `source_ref` 均为非空值。
4. WHEN 标注人在波形图上框选打标且 `rest_of_day_policy` 取默认值 `normal`，THE Point_Label_Service SHALL 写入两条标注操作：一条 `source='human_range'`、`priority=100`、范围为框选区间、`label_id` 为所选标签；一条伴生操作 `source='human_day'`、`priority=80`、范围为 `op_scope` 所指自然日的完整区间、`label_id=0`（正常）、`parent_op_id` 指向前者。
5. THE Point_Label_Service SHALL 把第 4 条的 `op_scope` 定义为 `(site_id, device_id, branch_id, 框选起点所属自然日)`，即只覆盖被框选的那一个设备支路的那一个自然日；THE Point_Label_Service SHALL NOT 把该范围扩大到同一输入文件的其他设备或其他自然日（依据见现状与问题第 24 项：实测输入文件含 189 个设备、跨 5 个不连续自然日）。
6. WHERE 一次框选跨越两个自然日，THE Point_Label_Service SHALL 为跨越到的每一个自然日各生成一条伴生 `human_day` 操作，使「其余时段判正常」在每一天内都有明确范围。
7. WHERE `rest_of_day_policy` 取 `untouched`，THE Point_Label_Service SHALL 只写入 `human_range` 操作，不写伴生操作；该自然日其余点的标签由其他已有操作按需求 4 第 1 条决定。
8. THE Review_UI SHALL 在框选打标弹窗中提供 `rest_of_day_policy` 选项，默认选中「本日其余时段判为正常」，并把该选择随打标请求提交，使该假设成为显式声明而非隐含行为。
9. WHEN 第 4 条的两条操作写入后执行物化，THE Label_Materializer SHALL 使框选区间内的点取 `human_range` 的标签（`priority=100` 胜出）、该自然日其余点取 `label_id=0`（`priority=80` 胜出，压过 `day_label` 的 10）。
10. THE 需求文档 SHALL 记录第 9 条在真实案例上的预期效果：对武当湖 / 04#箱变_汇流箱01 / 支路1 / 2020-05-08（该设备当天实测 288 点），框选 06:00~18:40 打 `label=1` 后，框内 153 点生效标签为 1、来源 `human_range`；当天其余 135 点生效标签由批量导入的 1 改写为 0、来源 `human_day`。
11. IF 一条 `human_range` 操作与另一条 `status='active'` 的 `human_range` 操作在同一设备维度下时间重叠，THEN THE Point_Label_Service SHALL 拒绝写入并返回 HTTP 422 状态码，且响应体中包含冲突操作的 `op_id` 与重叠时间范围。
12. THE Point_Label_Service SHALL 强制标注操作的时间跨度不超过 `max_op_span`（操作最大跨度，默认 31 天），使源数据异常不会产生无界长操作。
13. THE Point_Label_Service SHALL 允许标注操作跨自然日，即不对 `t_end` 与 `t_start` 所属自然日的关系施加约束（K3）。
14. THE 校验层 SHALL 为第 1、2、3、11、12 条不变量提供可独立运行的校验程序，对给定操作集合返回违规明细（含 `op_id` 与违反的不变量编号）。

### 需求 6：标注操作生命周期与审计轨迹

**User Story:** 作为审计与复盘人员，我希望每次改判都能查到原值，以便任一历史训练快照都可复现。

#### 验收标准

1. THE label_ops 表 SHALL 支持 `status` 取值 `active` 与 `revoked`。
2. WHEN 标注人改判某时段的标签，THE Point_Label_Service SHALL 新增一条标注操作并把被改判的旧操作 `status` 置为 `revoked`，而不是原地修改旧操作的 `label_id`。
3. WHEN 一条 `human_range` 操作被撤销且它带有伴生 `human_day` 操作（需求 5 第 4 条），THE Point_Label_Service SHALL 同时把该伴生操作置为 `revoked`（按 `parent_op_id` 关联），避免「问题时段的标注被撤了、但『其余时段正常』的声明还留着」这种不一致状态。
4. WHEN 任一操作的 `status` 变化，THE Label_Materializer SHALL 按需求 4 第 7 条重物化受影响范围的逐点标签。
5. THE label_ops 表 SHALL 保留所有 `revoked` 操作记录，使给定时间点的操作集合与逐点标签可被重建。
6. THE Label_Materializer SHALL 只读取 `status='active'` 的操作参与物化。
7. THE Snapshot_Builder SHALL 为每次快照记录 `label_snapshot_hash`（口径见需求 21 第 8、9 条），使同一哈希对应的快照可被重新生成为等价结果。
8. THE label_ops 表 SHALL 不支持物理删除；撤销只通过 `status` 迁移表达。

### 需求 7：样本构造策略与策略不变量

**User Story:** 作为算法工程师，我希望一段时序里每一种打过标签的形态就是一条样本，并且我可以选择按天切还是按标签形态跨天切，以便同一份逐点标签能支撑不同的建模粒度。

#### 验收标准

1. THE Sample_Builder SHALL 提供接口 `build_samples(labeled_rows: DataFrame, strategy: SampleStrategy) -> list[Sample]`，其中 `labeled_rows` 是同一 `(site_id, device_id, branch_id)` 下按时间升序的测量行与其逐点标签。
2. THE Sample_Builder SHALL 提供单一配置项 `split_mode`，取值为下列二者之一，且 SHALL NOT 提供其他切分方式或把它们组合嵌套（K6/K8）：
   - **`by_day`（按天切分）**：在设备边界、标签形态变化处**与**自然日边界断开；一天一条样本，不跨天。
   - **`by_day_night`（白天夜间切分）**：在 `by_day` 的全部断点基础上，再按 `daylight_window` 时钟窗断开白天与夜间；一天最多产出 1 段白天 + 2 段夜间（清晨 `00:00~daylight_start`、傍晚 `daylight_end~24:00`）。
   - 注：跨天时序切分 `by_label_run` 已按 K8 移出本 spec，交由 `pv-fault-timeseries-diagnosis` spec 用序列模型承接，本 spec 不再提供该取值。
3. THE Sample_Builder SHALL 使 `split_mode` 默认取 `by_day_night`（与线上生产模型 `pv_fault_rfc_20260723T080347Z_3a8642` 的 `train_summary.solar_mode="day_and_night"` 口径对齐，使新旧模型精度可比）。
3a. THE Sample_Builder SHALL 使 `period_role` 取值域为 3 个，且由 `split_mode` 唯一决定：`by_day` 下恒为 `whole`；`by_day_night` 下取 `daylight` 或 `night`。THE Sample_Builder SHALL NOT 产生 `peak`、`trans`、`sub` 三种取值（对应删除的 `solar_period` 与 `fixed_window`）。
4. THE Sample_Builder SHALL 满足标签纯一致不变量：每条输出样本内所有采样点的 `label_id` 取值相同，且样本的 `label_id` 等于该取值。
5. THE Sample_Builder SHALL 满足单标签不变量：每条输出样本只有一个 `label_id`，不输出标签集合或标签分布（K2）。
6. THE Sample_Builder SHALL 在标签形态变化处断开，使「一段时序里每一种打过标签的形态就是一条样本」成立；WHERE 一段连续时序里出现 k 种标签形态，THE Sample_Builder SHALL 至少产出 k 条样本。
7. THE Sample_Builder SHALL 把 unknown 点（`label_id` 为 NULL）视为一种独立形态并在其边界处断开，且 SHALL NOT 为 unknown 形态产出训练样本。
8. THE 需求文档 SHALL 记录两种保留模式在实测数据上的样本量级基线（对 `pv_cumulative_labeled_merged.parquet`，按 `(site_id, device_id, branch_id)` 显式分组后统计）：`by_day` 产出 **4,457** 条样本，单样本点数 min/median/max = 144 / 219 / 288；`by_day_night` 产出 **13,371** 条样本（4,457 白天 + 8,914 夜间），点数 min/median/max = 34 / 72 / 144。该数据集含 2,226 个 device-branch 组、4,457 个 device-branch-day 组。（历史参考：已移出的 `by_label_run` 曾实测 2,699 条、其中 934 条跨天，该数字现归属 `pv-fault-timeseries-diagnosis` spec。）
9. THE Sample_Builder SHALL 满足点不重复不变量：输出的任意两条样本所引用的测量行索引集合交集为空。
10. THE Sample_Builder SHALL 不提供下列已删除的切分方式，并 SHALL 在设计文档中记录各自的删除理由：`multiscale`（把同一批数据追加两次，必然违反第 9 条点不重复不变量）、`fixed_window`（切分方式收敛为 2 项，固定子窗不在本次范围内）、`solar_period` 与其 `peak` / `trans` 时段（判定依据是「功率 > 当天峰值 30%」，与被 K5 否决的按值判定同源，存在同一处循环论证）。
11. THE Sample_Builder SHALL 对所有策略应用统一的后置过滤 `min_points`（样本最小采样点数），其默认取值为 12（等于 1 小时 / 5 分钟采样的点数）。
12. THE Sample_Builder SHALL 允许输出为空列表（可为空不变量）。
13. WHEN 输出为空列表或某候选样本被过滤，THE Sample_Builder SHALL 给出结构化丢弃原因，且 THE Snapshot_Builder SHALL 把该原因汇总进重训报告，使丢弃对使用者可见（现 `handle_missing` 的 `keep_threshold=0.75` 会静默丢弃整组）。
14. WHEN 某候选样本因 `min_points` 被过滤，THE Sample_Builder SHALL 在丢弃原因中同时给出该样本实际点数与生效的 `min_points` 取值。
15. THE 测试套件 SHALL 以属性测试（property-based test）覆盖第 4、5、6、7、9、12 条不变量，输入包含：单点形态、跨自然日形态、恰好在 00:00 处发生标签变化的形态、全 unknown 形态、点数少于 `min_points` 的形态、同一天内出现 3 种以上标签形态的情形。
16. THE Sample_Builder SHALL 按 `daylight_window`（日照时钟窗）判定每个采样点属于白天还是夜间：采样时刻落在 `[daylight_start, daylight_end)` 内判为白天，否则判为夜间；THE Sample_Builder SHALL NOT 使用任何依赖当日测量值的判定方式（含现有 `solar_window._day_night_masks()` 的 `value >= 当天max(value) × irr_threshold` 口径）。判定所需的 `daylight_window` 按采样点所属的 `(site_id, 季节桶)` 取值，其中**季节桶 = 月份序号（1~12）**，使跨天样本内每一天各自适用其所属季节的日照窗（S1：由「自然月 `YYYY-MM`」改为「月份序号 1~12」，因为日照的季节性由月份决定、与年份无关，用月份桶才能让不同年份的同一季节共用窗口、样本更充足）。
16a. THE 日照窗解析 SHALL 支持两种 `daylight_window_source`：
   - `empirical`（默认）：对每个 `(site_id, 季节桶)`，用**跨多个设备-天聚合**的时段功率中位曲线（按 time-of-day 取各设备-天功率的中位数）推导日照起止，取中位曲线超过其自身峰值一个可配置比例处的首末时刻；THE 推导 SHALL 基于跨天聚合量，使单个故障设备或单个坏天气日无法改变窗口取值，从而不构成「用症状定义观察窗口」的循环论证。
   - `empirical` 推导 SHALL 只使用**最近 `daylight_window_lookback_months`（近期回溯月数，默认 24）个月**内的测量数据，不使用全部历史（S1：光伏板会随时间衰减、周边遮挡会变化，早期数据的日照形态未必代表现状；只取近期数据推导，避免多年前的形态主导当前窗口）。回溯窗以数据集最新时间戳为锚向前取；WHERE 某季节桶在回溯窗内数据量不足，THE 日照窗解析 SHALL 先放宽回溯窗至全历史该季节桶，仍不足再按第 16b 条回退 `fixed`。
   - `fixed`（兜底）：使用配置的固定时刻，默认 `daylight_start=06:00`、`daylight_end=18:00`。
16b. IF 某 `(site_id, 季节桶)` 的经验推导因数据量不足或推导结果不合理（如窗口时长小于 4 小时或大于 20 小时）而失败，THEN THE 日照窗解析 SHALL 回退到 `fixed` 取值，并在快照元数据与重训报告中记录发生回退的 `(site_id, 季节桶)` 清单。
16c. THE 日照窗解析 SHALL 把生效的 `daylight_window` 取值表（按 `site_id` × 季节桶）、`daylight_window_source` 与 `daylight_window_lookback_months` 随 `sample_strategy` 一起持久化进模型文件（见需求 12 第 3 条），使预测阶段使用与训练时完全相同的时钟窗，不重新推导。
16d. THE 需求文档 SHALL 记录 K5 的实测量化影响：按时钟 06:00–18:00 与按值判定两口径在 **189,790 点（18.0%）** 上判定不一致；时钟口径下夜间点 `i_cal` 零值占比达 **94.47%**（白天点仅 5.96%），「夜间无电流」先验成立；且夜间非零电流占比在各 label 间跨度为 7.45%~100.00%，说明 5 个 `night_*` 特征在时钟口径下具备区分度（完整数据见现状与问题第 25、26 项）。
16e. THE 预处理规约 SHALL 在计算 `night_*` 特征前拦截量级异常坏值：实测夜间点 `value` 绝对值最大达 1.04e11（同批 `i_cal` 最大仅 1.75），若不拦截会污染 `night_current_max` 与 `night_current_mean`（依据见现状与问题第 29 项）。
17. WHERE `split_mode=by_day_night`，因该模式已在 `by_day` 基础上按自然日断开（第 2 条），样本不跨天；同一自然日内白天与夜间各自恒为连续区间，一天最多产出 1 段白天与 2 段夜间（`00:00~daylight_start` 与 `daylight_end~24:00`），不会出现按值判定下「一天被切成最多 43 段」的碎片化（依据见现状与问题第 25 项）。实测该模式在 `pv_cumulative_labeled_merged.parquet` 上产出 4,457 段白天 + 8,914 段夜间 = 13,371 样本（见现状与问题第 30 项）。
18. THE Sample_Builder SHALL 使 `min_points`、`split_mode`、`daylight_window_source` 与生效的 `daylight_windows` 取值表随 `sample_strategy` 一起持久化进模型文件（与需求 12 第 3 条一致），使训练与预测使用同一套策略、同一套时钟窗与同一阈值。
19. THE 过滤规约 SHALL 把 `min_points` 与 `handle_missing` 的 `keep_threshold`（组内有效值占比阈值，现默认 0.75）解释为两个正交过滤器：前者约束采样点绝对数量、后者约束缺失率；两者同时保留、互不替代。
20. THE 需求文档与设计文档 SHALL 显式声明：逐点标签模型消除「重复计数」、「标签冲突」与「标签稀释」三类问题——稀释被消除是因为样本按标签形态断开后不再存在「一条样本内混有不同标签」的情形；但它不消除「标签本身粗糙」，即批量导入的天级标签在物化后仍是整天同一取值，提升标签精细度只能靠人工打更细的标注操作。

### 需求 8：统一样本标识 sample_id

**User Story:** 作为排障人员，我希望样本标识永远是同一种类型、且自带溯源信息，以便回流与审核链路不再依赖时间戳归一化。

#### 验收标准

1. THE Snapshot_Builder SHALL 按 `sample_id = f"smp-{device_hash8}-{t_start:%Y%m%dT%H%M%S}#{period_role}#{seq}"` 生成样本标识（示例 `smp-3f9a1c2b-20200508T060000#whole#0`），其中 `device_hash8` 是 `(site_id, device_id, branch_id)` 拼接后 SHA-256 摘要的前 8 位十六进制、`seq` 为同一起点同一角色下的样本序号。
2. THE Snapshot_Builder SHALL 使 `sample_id` 恒为字符串类型，使读取方无需任何时间戳归一化处理。
3. THE Snapshot_Builder SHALL 使 `sample_id` 恒含 `#` 字符，以满足需求 9 第 5 条的透传要求。
4. THE Snapshot_Builder SHALL 用 `sample_id` 取代现有四种混用标识形态（DatetimeIndex 形态、`YYYY-MM-DD`、`YYYY-MM-DD#night`、`{start}__{end}#freeform`）。
5. THE Labeling_API SHALL 用 `sample_id` 取代现有三套 `unit_key` 格式（from-prediction、from-dataset、freeform 各一套），使审核单元键与训练样本标识一致。
6. THE Labeling_API SHALL 移除 `backfill.py` 与 `api/iterative_labeling.py` 中重复的时间戳归一化实现，使标识匹配只依赖字符串相等比较。
7. WHEN 回流程序按 `sample_id` 匹配真值标签，THE 回流程序 SHALL 对存在对应样本的快照返回非零匹配行数（修复现有「没有任何原始行匹配到真值标签」缺陷）。
8. WHEN Review_UI 按 `sample_id` 请求波形数据，THE Labeling_API SHALL 返回该样本时间范围内的测量行（修复现有审核页看不到波形缺陷）。
9. THE sample_id SHALL 可被解析回 `device_hash8`、`t_start` 与 `period_role`；THE Snapshot_Builder SHALL 另在快照中输出 `label_op_id`（该样本主标签来源操作的 `op_id`）列承载溯源信息，使样本可追溯到产生它标签的标注操作，而不把 `op_id` 编进 `sample_id`（因一条样本的点可能来自多个操作，见需求 3 第 17 条）。
10. WHERE 样本来自推理，THE Inference_Sample_Generator SHALL 使用 `inf-` 前缀生成 `sample_id`（形如 `inf-3f9a1c2b-20200508T060000#whole#0`），使推理样本与训练样本可按前缀区分。
11. THE Snapshot_Builder SHALL 保证同一快照内 `sample_id` 唯一。

### 需求 9：零新增算子架构约束

**User Story:** 作为平台架构负责人，我要求这次重构不新增任何算子，以便算子库与模板 DAG 保持稳定、可回滚。

#### 验收标准

1. THE 本次重构 SHALL 不向 `backend-service/services/operator_backends/` 新增任何算子实现文件。
2. THE 本次重构 SHALL 不改变现有工作流模板的 DAG 结构，节点不增不减。
3. THE Snapshot_Builder SHALL 在编排层完成逐点标签读取、样本构造与 `sample_id` 赋值，产出已带 `sample_id` 的快照 parquet（预物化）。
4. THE Training_Pipeline SHALL 只负责特征工程与模型训练评估，不负责样本边界的确定。
5. THE Snapshot_Builder SHALL 使快照中每一行的 `time_window` 列取值均为含 `#` 的 `sample_id`，使 `time_window_split.py` 成为纯透传节点。
6. THE 下列 5 个算子文件 SHALL 保持零代码改动：`time_window_split.py`、`tsfresh_extract.py`（时序特征批量抽取算子）、`ts_comparison_features.py`（时序对比特征算子）、`handle_missing.py`、`detect_outliers.py`。
7. THE 本次重构 SHALL 把算子层代码改动限定在 `extract_statistical_features.py`（统计特征聚合算子）与 `stratified_cv_eval.py`（分层交叉验证评估算子）两个文件，且改动范围仅为下列三项：`stratified_cv_eval.py` 新增可选参数 `group_col`（分组分层切分列）、`extract_statistical_features.py` 新增可选参数 `passthrough_fields`（常量列透传字段）、`extract_statistical_features.py` 的分位数特征判定口径改为按样本自身采样点数（口径见需求 13 第 1、2、3 条）。
8. THE Sample_Builder 的白天/夜间判定 SHALL 按需求 7 第 16 条以 `daylight_window` 时钟窗实现，**不复用** `solar_window.py` 的 `_day_night_masks()` 按值判定逻辑（该逻辑已被 K5 否决）；THE `solar_window.py` 文件本身 SHALL 保留且零代码改动，以兼容 fault-diag 的 `set_time_window` 旧调用方（现状与问题第 22 项所述的自然日隐式分组与按值判定行为在该旧调用路径下保持不变）。
8a. THE 设计文档 SHALL 显式记录第 8 条造成的口径分叉：本次重构的训练/预测链路使用时钟窗判定，而 fault-diag 的 `set_time_window` 旧路径仍使用按值判定；两条路径的白天/夜间归属实测在 18.0% 的点上不一致（见现状与问题第 26 项），因此两者产出的样本与特征不可混用比较。
9. THE 模板改动 SHALL 仅限于下列三项：统计特征节点（`extract_statistical_features`）增加 `passthrough_fields`、交叉验证节点（`stratified_cv_eval`）增加 `group_col`、`time_window_split` 节点删除 `solar_mode`、`power_col`、`irr_threshold`、`attach_night_features` 四个因透传模式而失效的参数（依据见现状与问题第 21 项，清单见需求 12 第 4 条）。
10. THE 下游一致性论证 SHALL 说明 `handle_missing` 与 `detect_outliers` 的 `id_fields=[site_id, device_id, branch_id, time_window]` 分组与按 `sample_id` 分组等价（`sample_id` 含 `device_hash8`，唯一对应设备三元组），并说明 `stratified_cv_eval._build_Xy()` 的 `drop_cols` 已含 `time_window`、`sample_id` 不会进入特征矩阵。
11. THE Snapshot_Builder SHALL 在写出快照文件前自检 `time_window` 列满足「100% 非空」且「100% 含 `#`」两个条件，使需求 16 第 4 条的下游校验有对应的上游保证。
12. IF 第 11 条自检未通过，THEN THE Snapshot_Builder SHALL 拒绝写出快照并返回错误明细（不满足条件的行数与示例行）。
13. WHERE `group_col` 未配置，THE `stratified_cv_eval.py` SHALL 表现出与改动前等价的行为。
14. WHERE `passthrough_fields` 未配置，THE `extract_statistical_features.py` SHALL 除第 7 条的分位数判定口径修正外表现出与改动前等价的输出列集合。
15. WHERE 模板已按第 9 条移除四个失效参数，THE `time_window_split.py` SHALL 仍保持第 6 条的零代码改动（该算子读取 `solar_mode` 用的是 `params.get("solar_mode")`，参数缺失时取到 `None` 并走透传分支，不抛错）。
16. THE 需求文档与设计文档 SHALL 把「零代码改动清单」（第 6 条的 5 个文件）与「限定范围改动清单」（第 7 条的 2 个文件）表述为互斥的两份清单。

### 需求 10：训练快照的列结构与去重策略

**User Story:** 作为算法工程师，我希望快照 parquet 的列结构明确稳定，以便下游算子无需推断即可消费。

#### 验收标准

1. THE Snapshot_Builder SHALL 产出包含下列列的快照 parquet：`time` — 采样时刻、`site_id`、`device_id`、`branch_id`、`value` — 测量值、`i_cal` — 计算电流、`label` — 故障标签（取自该点的逐点标签）、`time_window` — 填入 `sample_id`、`group_key` — 防泄漏分组键、`period_role` — 时段角色原始字符串（供人读与溯源）、`period_is_whole` / `period_is_daylight` / `period_is_night` — `period_role` 的 one-hot 数值列（3 列，取值 0/1）、`night_nonzero_current_ratio` / `night_current_mean` / `night_current_max` / `night_over_threshold_duration` / `night_power_residual_mean` — 5 列夜间异常特征、`label_source` — 该样本的主标签来源、`label_source_purity` — 主来源点数占比、`label_op_id` — 主标签来源操作标识。
2. THE Snapshot_Builder SHALL 使 `label` 列取值来自 `point_labels` 的逐点标签，而非按自然日广播。
3. THE Snapshot_Builder SHALL 删除 `_create_snapshot()` 中现有的 `drop_duplicates(subset=[time, site_id, device_id, branch_id, time_window])` 整块逻辑，改由「每个采样点在 `point_labels` 中只有一条记录」（需求 2 第 1 条主键）与「样本点不重复」（需求 7 第 9 条）共同保证无重复。
4. WHEN 对现状与问题第 4 项所述案例（武当湖 / 04#箱变_汇流箱01 / 支路1 / 2020-05-08）构建快照，THE Snapshot_Builder SHALL 产出该设备该天的采样点总数不超过 288 行，且任一采样时刻在该天只出现一次。
5. THE Snapshot_Builder SHALL 保证快照中任意两行的 `(time, site_id, device_id, branch_id)` 组合唯一。
6. THE Snapshot_Builder SHALL 按下列口径计算 `group_key`：对每个 `(site_id, device_id, branch_id)`，把每条样本映射为它覆盖的自然日集合，对「日集合有交集」这一关系取连通分量（day-block），同一连通分量内的全部样本共享同一 `group_key`，取值 `{site_id}|{device_id}|{branch_id}|blk{n}`，`n` 按块内最早时间升序分配；THE Snapshot_Builder SHALL 满足不变量：任意两条共享至少一个自然日的样本必属同一 `group_key`。
7. THE 设计文档 SHALL 记录第 6 条替代「按自然日取键」的理由：按自然日取键要求样本不跨天，与 K3（允许跨天建模）冲突；day-block 口径在允许跨天的同时保持了「同一天的数据不会被切到训练集与测试集两侧」这一防泄漏强度。
8. THE Snapshot_Builder SHALL 在快照中同时保留 `period_role` 字符串列与其 one-hot 数值列，且 THE 设计规约 SHALL 明确 `period_role` 字符串列不进入特征矩阵（`stratified_cv_eval._build_Xy()` 会 drop 所有非数值列），进入特征矩阵的是 3 个 `period_is_*` 数值列。
9. THE Snapshot_Builder SHALL 保证同一行的 3 个 `period_is_*` 列取值之和恒为 1（各时段角色互斥且完备）。
9a. WHERE `split_mode` 取 `by_day`，THE Snapshot_Builder SHALL 使 `period_is_whole` 恒为 1、另两列恒为 0；此时这 3 列与 5 个 `night_*` 列均为常量，THE 模板配置 SHALL 把这 8 列从 `passthrough_fields` 中移除，避免向特征矩阵喂入无区分度的常量列（见需求 11 第 8a 条）。
10. WHERE 样本的 `period_role` 取值不为 `night`，THE Snapshot_Builder SHALL 把 5 个 `night_*` 列显式写为 0.0 而不留空值，使特征矩阵不依赖 `extract_statistical_features.py` 末尾 `result.fillna(0)` 的兜底行为（现 `solar_window.attach_night_anomaly_features()` 只对 `period_role='night'` 的行赋值，其余行留 `pd.NA`）。

### 需求 11：分组分层切分与常量列透传

**User Story:** 作为算法工程师，我希望同一天的兄弟样本不会被分到训练集与测试集两侧，也希望样本级常量特征不再被聚合环节丢弃。

#### 验收标准

1. THE `stratified_cv_eval.py` SHALL 新增可选参数 `group_col`；WHERE `group_col` 已配置，THE `stratified_cv_eval.py` SHALL 按该列取值整组分配，使同一 `group_key` 的所有样本整组进入训练集或整组进入测试集。
2. WHERE `group_col` 未配置，THE `stratified_cv_eval.py` SHALL 保持现有行级分层切分行为不变。
3. WHEN 按 `group_col` 分组切分，THE `stratified_cv_eval.py` SHALL 在训练集与测试集之间保持零个共享 `group_key`。
4. THE `extract_statistical_features.py` SHALL 新增可选参数 `passthrough_fields`；WHERE 该参数已配置且算子运行在 `groupby_aggregate` 模式，THE `extract_statistical_features.py` SHALL 对每个分组取该字段的第一个值原样输出为常量列。
5. WHERE `passthrough_fields` 未配置，THE `extract_statistical_features.py` SHALL 保持现有输出列集合不变（该约束不覆盖需求 13 第 1 条的分位数判定口径修正）。
6. WHEN 快照已按需求 10 第 1、10 条写入 5 个 `night_*` 列与 3 个 `period_is_*` 列，且统计特征节点的 `passthrough_fields` 包含这 8 列，THE Training_Pipeline SHALL 在特征矩阵中保留这 8 个数值列（修复缺陷：原 `attach_night_features` 路径产出的列在聚合环节被丢弃、该配置项完全无效；重构后这些列的来源是快照列，`attach_night_features` 不再是这些列的来源，并按需求 12 第 4 条从模板移除）。
7. WHERE `passthrough_fields` 包含 `period_role` 字符串列，THE Training_Pipeline SHALL 把该列透传至聚合结果供溯源使用，且不期望其进入特征矩阵（见需求 10 第 8 条）。
8. WHERE `split_mode=by_day_night`（默认），THE 统计特征节点的 `passthrough_fields` 配置 SHALL 至少包含下列 12 列：`group_key`（供第 1 条的 `group_col` 读取）、`label_source`（供需求 3 第 16 条按来源分口径评估读取）、`label_source_purity`、`label_op_id`（供溯源）、`period_is_whole` / `period_is_daylight` / `period_is_night`（3 列时段角色 one-hot）、`night_nonzero_current_ratio` / `night_current_mean` / `night_current_max` / `night_over_threshold_duration` / `night_power_residual_mean`（5 列夜间异常特征）；`period_role` 字符串列按第 7 条为可选追加项，不计入这 12 列。
8a. WHERE `split_mode` 取 `by_day`，THE 统计特征节点的 `passthrough_fields` SHALL 只包含 4 列：`group_key`、`label_source`、`label_source_purity`、`label_op_id`；THE 配置 SHALL 移除 3 个 `period_is_*` 与 5 个 `night_*` 列（此时它们是常量，见需求 10 第 9a 条）。
9. THE 设计规约 SHALL 记录下列约束依据：`extract_statistical_features.py` 的 `_execute_groupby_aggregate()` 只输出 `id_fields` 与 `value_fields` 的派生特征列，任何样本级常量列若不在 `passthrough_fields` 中即在聚合环节丢失；因需求 9 第 7 条已把该算子的改动限定为新增 `passthrough_fields` 与分位数判定口径修正、且 `id_fields` 保持现状不变，`passthrough_fields` 是第 8 条这 12 列到达 `stratified_cv_eval.py` 的唯一通路。
10. THE Training_Pipeline SHALL 使第 8 条中的 9 个数值列（3 个 `period_is_*`、5 个 `night_*`、1 个 `label_source_purity`）进入特征矩阵。
11. THE Training_Pipeline SHALL 使第 8 条中的 3 个字符串列（`group_key`、`label_source`、`label_op_id`）只供下游组件读取而不进入特征矩阵；该排除由 `_build_Xy()` 丢弃非数值列的现有逻辑（见现状与问题第 16 项）自然完成，不需要额外的手工排除实现。
12. WHEN `group_col` 已配置（第 1 条），THE `stratified_cv_eval.py` SHALL 在 `_build_Xy()` 丢弃非数值列之前从合并后的特征表中读出 `group_col` 指定列的取值，使该字符串列被丢弃后分组信息仍可用于切分。
13. THE 设计规约 SHALL 记录合并基表依据：`_merge_feature_frames()` 以含 `target_col`（本场景即 `label`）的那一路特征表为合并基表，训练模板中只有统计特征节点的 `id_fields` 含 `label`，因此统计特征表即为合并基表（依据见现状与问题第 19 项）。
14. WHERE 第 8 条的 12 个常量列已由统计特征节点透传，THE Training_Pipeline SHALL 使这 12 列随合并基表到达 `stratified_cv_eval.py`，无需为 `tsfresh_extract` 或 `ts_comparison_features` 配置 `passthrough_fields`（这两路算子按需求 9 第 6 条零代码改动，不识别该参数）。
15. THE 第 8 条的 12 个透传列的列名 SHALL 不与 `tsfresh_extract` 或 `ts_comparison_features` 的任何输出列同名，避免 `_merge_feature_frames()` 的 `new_cols` 过滤在合并阶段静默跳过重名列（依据见现状与问题第 20 项）。
16. THE 设计阶段 SHALL 列出三路输出列名的全集并对第 15 条执行冲突检查，且在设计文档中记录检查结论。
17. IF 第 16 条的冲突检查发现重名列，THEN THE 设计方案 SHALL 为冲突的透传列改用带前缀的列名（例如 `lbl_` 前缀）并同步更新第 8 条清单与需求 10 第 1 条的快照列清单。

### 需求 12：训练与预测共用同一份样本策略

**User Story:** 作为运维人员，我希望预测时的样本切分与训练时完全一致，以便不再需要人工核对训练/预测模板是否对齐。

#### 验收标准

1. THE Inference_Sample_Generator SHALL 提供 `generate_inference_samples()`，按模型持久化文件中记录的策略把待预测测量数据切成样本，样本 `label_id` 为 None。
2. WHEN 定时预测任务写出预测输入文件，THE `pv_fault_tasks._write_prediction_input()` SHALL 为每一行打上 `sample_id`。
3. THE `stratified_cv_eval.py` SHALL 在保存模型文件时写入 `sample_strategy`（样本策略，含 `split_mode` — 切分模式取值 `by_day` / `by_day_night`、`daylight_window_source` — 日照窗来源、`daylight_windows` — 按 `site_id` × 季节桶生效的日照窗取值表、`daylight_window_lookback_months`、`min_points`、`version` — 策略版本）与 `label_snapshot_hash`（训练时逐点标签内容哈希，口径见需求 21 第 8、9 条）。
4. THE 工作流模板 JSON 的 `time_window_split` 节点 SHALL 不再包含下列 4 个因透传模式而失效的参数：`solar_mode`（日照切分模式）、`power_col`（功率列名）、`irr_threshold`（日照判定阈值）、`attach_night_features`（是否附加夜间异常特征）；实测训练模板 `workflow-pv-fault-diag-quickval-cv-v1.json` 的 `qv-time_window_split-n4` 节点四者俱在（依据见现状与问题第 21 项）。
5. THE 本次重构 SHALL 删除 `PVTrainingWorkspaceService.set_workflow_split_parity()` 与 `PVTrainingWorkspaceService._read_workflow_split_parity()`，并同步调整 `backend-service/api/iterative_labeling.py` 中引用这两个函数的路由与相关测试，使「训练/预测模板切分是否对齐」这一问题在结构上不再存在。
6. WHEN 预测流程加载模型文件，THE Inference_Sample_Generator SHALL 使用模型文件中的 `sample_strategy` 切分样本，而不读取模板配置。
7. IF 模型文件缺少 `sample_strategy`，THEN THE Inference_Sample_Generator SHALL 返回明确错误并终止预测，不回退到默认策略。
8. THE Inference_Sample_Generator SHALL 把推理样本保持为内存中的临时对象，不写入 `point_labels` 表，也不写入 `label_ops` 表。
9. THE Inference_Sample_Generator SHALL 使推理样本不参与需求 4 的标签物化，也不产生任何落库的 `op_id` 记录。
10. THE Inference_Sample_Generator SHALL 为推理样本使用 `inf-` 前缀命名空间（见需求 8 第 10 条），与训练样本的 `smp-` 前缀可区分。
11. THE Inference_Sample_Generator SHALL 不对推理样本应用需求 2 的表字段约束（推理样本不是落库记录，无 `status`、`priority`、`label_space_version`）。
12. IF 某调用请求以 `source='inference'` 写入 `point_labels` 或 `label_ops` 表，THEN THE Point_Label_Service SHALL 拒绝写入并返回 HTTP 422 状态码（`inference` 不属于需求 3 第 1 条的 `source` 枚举值）。
13. THE 工作流模板 JSON 的 `time_window_split` 节点 SHALL 保留 `window`（窗口长度）、`id_fields`（分组字段列表）、`time_field`（时间列名）三个参数：`window` 为空时抛 `ParameterError`、`time_field` 不在输入列中时抛 `InputError`，这两项校验在全透传模式下仍先于透传分支执行；`id_fields` 保留是为使分组语义与下游 `handle_missing`、`detect_outliers` 的 `id_fields` 口径保持一致。
14. WHEN 第 4 条的 4 个参数被移除后模板被执行，THE Training_Pipeline SHALL 与移除前产出逐行等价的 `time_window_split` 输出（因快照已按需求 9 第 5 条使每行 `time_window` 均含 `#`，该节点恒走透传分支）。
15. WHERE 预测场景下某段测量数据的逐点标签未知（正常情形），THE Inference_Sample_Generator SHALL 按 `sample_strategy` 的 `split_mode`（`by_day` 或 `by_day_night`）直接按自然日（及白天夜间）边界切分，与训练时逐样本对齐；因两种保留模式都按时钟/自然日切分、不依赖标签，预测侧无需任何退化处理（K8 移出 `by_label_run` 后，原「时序模式预测时退化为按天」的问题在本 spec 不再存在）。
16. THE 设计文档 SHALL 记录：`by_day` / `by_day_night` 两种模式训练与预测口径一致（都按自然日/时钟切分、不依赖标签），因此训练/预测样本边界可严格对齐——这是把 `by_label_run` 移出本 spec 后获得的额外好处（该模式预测时无标签、边界无法对齐）。
16a. WHERE `split_mode=by_day_night`，THE Inference_Sample_Generator SHALL 使用模型文件中持久化的 `daylight_windows` 取值表判定白天/夜间（见第 3 条与需求 7 第 16c 条），SHALL NOT 在预测阶段重新推导日照窗；该约束使白天/夜间划分在训练与预测之间严格一致——这是本需求「共用同一份策略」在改为时钟判定后仍然成立的关键（按值判定下预测阶段的阈值依赖当日峰值，天然无法与训练时一致）。
16b. IF 预测数据中某 `(site_id, 季节桶)` 组合不在模型持久化的 `daylight_windows` 表中，THEN THE Inference_Sample_Generator SHALL 使用该模型持久化的 `fixed` 兜底窗口并在预测输出中记录该情形，SHALL NOT 现场推导新窗口。

### 需求 13：特征 schema 稳定性

**User Story:** 作为算法工程师，我希望特征列数由配置决定，以便模型文件里固定的 `feature_list` 不会因数据构成变化而失配。

#### 验收标准

1. THE `extract_statistical_features.py` SHALL 按每个样本自身的采样点数与 `min_points` 判定是否计算分位数特征，不使用全体分组的平均点数（现 `avg_count = groups[value_fields].count().mean().mean()` 且仅当 `avg_count >= 48` 才计算分位数特征）。
2. THE `extract_statistical_features.py` SHALL 使输出特征列集合由配置参数唯一决定，不随输入数据构成变化。
3. WHEN 输入数据中新增一个采样点数少于 48 的短样本，THE `extract_statistical_features.py` SHALL 保持其他样本的特征列集合不变。
4. WHEN 训练与预测使用同一份配置，THE Training_Pipeline SHALL 产出相同的特征列集合与列顺序。
5. WHERE 不同 `split_mode` 导致样本点数不同（实测基线：`by_day` 单样本 144~288 点、`by_day_night` 单样本 34~144 点），THE `extract_statistical_features.py` SHALL 仍按第 1、2 条保持列集合稳定，不因样本时长差异产生列数差异。

### 需求 14：历史标签迁移与对账

**User Story:** 作为数据负责人，我希望 4 个历史标签来源被一次性、可重复、可对账地迁入逐点标签表，以便重构后不丢失任何已有标注。

#### 验收标准

1. THE Migration_Tool SHALL 把历史标签迁为两部分：`label_ops` 中的标注操作记录与 `point_labels` 中的逐点生效标签，后者由前者经需求 4 的物化规则产生，不手工拼装。
2. THE Migration_Tool SHALL 按 `(site_id, device_id, branch_id, 自然日)` 为 `pv_cumulative_labeled_merged.parquet` 生成 `source='day_label'` 标注操作，每个分组一条，实测应产出 **4,457 条**操作、覆盖 **1,056,806** 个采样点；该分组粒度的依据是探测确认「同设备同天 `label` 不唯一的分组数为 0」（每组恰好一个标签取值，见现状与问题第 23 项）。
3. WHERE 前置验证已确认 `dataset_combined.parquet`（303,321 行）的全部行是 `pv_cumulative_labeled_merged.parquet` 的 `(site_id, device_id, branch_id, time)` 四元组子集且 0 行标签冲突，THE Migration_Tool SHALL 不对 `dataset_combined.parquet` 单独执行迁移；THE 对账报告 SHALL 记录该文件被判定为完全冗余源、未参与本次迁移的结论。
4. IF 后续某次迁移前重新执行重叠探测、发现两文件不再是完全子集关系，THEN THE Migration_Tool SHALL 重新评估是否需要对差异部分单独迁移，并在对账报告中说明差异范围。
5. THE 设计文档 SHALL 记录第 2 条的操作分块粒度**不影响样本边界**：样本边界由 Sample_Builder 读逐点标签后按 `split_mode`（自然日/白天夜间）决定，因此按设备-天分块只影响撤销粒度与审计可读性，不影响样本切分结果。
6. THE Migration_Tool SHALL 把 `training_workspace/pv_fault/time_slices/` 下 2 个 `*.meta.json` 的 `time_start` 与 `time_end` 字段逐字段直读，迁为 2 条 `source='human_range'` 操作。
7. WHERE 第 6 条的时间切片迁移，THE Migration_Tool SHALL 按 K4 为每条切片额外生成一条伴生 `source='human_day'`、`label_id=0` 操作，范围为该切片所属设备的该自然日，`parent_op_id` 指向对应的 `human_range` 操作；THE 对账报告 SHALL 单独列出因该规则被改写为「正常」的采样点数（预期：`slice-b0c42870f030` 对应 2020-05-08 的 135 点、`slice-b61b3af30dd5` 对应 2020-05-07 的其余点）。
8. THE Migration_Tool SHALL 把 `cumulative_training/pv_fault/state.json` 中 18 条 `verdict_entries` 直读迁为 18 条 `source='human_day'` 操作，边界由 `unit_key` 中的时间窗解析得到。
9. THE Migration_Tool SHALL 把 `unit_key` 中的时间取值解释为窗口起点，并按该审核单元的窗口长度推算 `t_end`，不把窗口起点直接当作 `t_end`。
10. THE Migration_Tool SHALL 把 `training_workspace/pv_fault/clust-ee66f5a50c28` 的已确认标注结果按 `selected_member_keys` 直读迁为 `source='cluster'` 操作。
11. THE Migration_Tool SHALL 把闭区间源边界转换为半开区间：`t_end = 源 time_end + 一个采样间隔`（本场景为 300 秒），使操作覆盖的采样点包含源数据的末尾采样点。
12. WHEN 迁移一条时间切片，THE Migration_Tool SHALL 用该切片 `meta.json` 的 `row_count` 对账，要求 `human_range` 操作覆盖的采样点数等于 `row_count`（例：`slice-b0c42870f030` 的 06:00~18:40 应对账为 153 点）。
13. IF 第 12 条对账结果不相等，THEN THE Migration_Tool SHALL 拒绝该条迁移、记入对账报告失败明细，并继续处理剩余条目。
14. THE Migration_Tool SHALL 对 `verdict_entries` 迁移结果执行与第 12 条同口径的采样点数对账，并对不一致条目按第 13 条处理。
15. THE Migration_Tool SHALL 是幂等的：对同一份源数据重复执行第二次后，`label_ops` 与 `point_labels` 内容与第一次执行后等价。
16. THE Migration_Tool SHALL 产出对账报告，包含：迁移前带 `label` 的行数、迁移后操作数（按 `source` 分组）、逐点标签覆盖的采样点数（按 `source` 分组）、unknown 采样点数、因 K4 被改写为「正常」的采样点数、失败明细。
17. WHERE 时间切片 CSV 的测量数据已存在于 parquet 中，THE 对账报告 SHALL 把这些 CSV 标注为「数据已被逐点标签覆盖、可安全归档」，且 THE 迁移执行 SHALL 不删除这些文件（与需求 17 第 1 条一致）。
18. THE `state.json` 账本 SHALL 保留，其职责收窄为只管理重训请求状态机（`queued` / `running` / `completed`、`pending_change_count`、生产模型指针），不再记录「训练集由哪些数据组成」。
19. IF 迁移过程中发现无法解析边界的标注条目，THEN THE Migration_Tool SHALL 跳过该条目、记入对账报告的失败明细，并继续处理剩余条目。
20. THE Migration_Tool SHALL 为本次迁移产生的每条标注操作写入同一个 `migration_batch_id`，使迁移操作与迁移后人工新增操作可区分。
21. THE Migration_Tool SHALL 在迁移完成后对账「逐点标签总数」与「源 parquet 带 label 行数」的差异，并解释每一处差异来源（预期差异只来自 K4 改写与人工操作覆盖，不应出现无法解释的缺失）。

### 需求 15：迁移前置验证门禁

**User Story:** 作为迁移执行人，我希望在动手迁移前先拿到几个关键数字，以便判断迁移复杂度和方案可行性。

#### 验收标准

1. THE Preflight_Probe SHALL 以只读方式运行，不修改任何数据文件、数据库表或模板。
2. THE Preflight_Probe SHALL 输出两个 parquet 中「同一设备同一天 `label` 取值不唯一」的分组数量（实测两文件均为 0），用于确定需求 14 第 2 条的操作分块粒度是否成立。
3. THE Preflight_Probe SHALL 输出两个 parquet 之间 `(site_id, device_id, branch_id, time)` 的重叠行数与重叠处 `label` 取值冲突的行数（实测 303,321 行重叠、0 行冲突）。
4. IF 第 3 条输出的冲突行数大于 0，THEN THE 迁移方案 SHALL 提供显式裁决规则，裁决依据为 `state.json` 中 `labeled_imports` 的 `sequence` 字段（见需求 4 第 6 条）。
5. THE Preflight_Probe SHALL 输出按标签变化 + 自然日边界断开的样本数（实测 **4,457**，即 `by_day` 基线），并用**显式分组边界**（设备键变化 OR 标签变化 OR 跨天）计算，不使用 `groupby.transform` 式写法。该要求源于一次真实误算：第四轮探针用 `groupby.transform` 得出 473 这一数字，实为 run 跨越了设备边界所致——识别线索是它算出「单个 run 最长覆盖 18 天」，而实测单设备支路最多只有 7 天数据。（仅按标签变化不断天的样本数 2,699 现归属 `pv-fault-timeseries-diagnosis` spec，本 spec 不再用作基线。）
5a. THE Preflight_Probe SHALL 输出 `by_day` 与 `by_day_night` 的单样本点数分布（实测 `by_day` 144/219/288、`by_day_night` 34/72/144），用于评估切分模式对特征稳定性的影响（见需求 13 第 5 条）。
5b. THE Preflight_Probe SHALL 输出按值判定白天/夜间的形态异常指标，作为 K5 的量化依据：夜间连续段数分布（实测 4,457 个设备-天中段数 >2 的有 1,596 个 / 35.8%，最多 43 段）、各小时被判为夜间的点占比（实测正午 12 点仍有 12.6%）、整天全判夜间的设备-天数（实测 365 个）。
5c. THE Preflight_Probe SHALL 输出按时钟判定与按值判定的差异量与「夜间无电流」先验的成立程度：两口径判定不一致点数（实测 189,790 / 18.0%）、时钟口径下夜间点与白天点的 `value` 与 `i_cal` 零值占比（实测夜间 `i_cal` 零值 94.47%、白天 5.96%）、时钟口径下各 label 的夜间非零电流占比（实测跨度 7.45%~100.00%）。
5d. THE Preflight_Probe SHALL 输出日照窗推导所需的基础统计：数据覆盖的站点数与月份清单（实测 8 站点、7 个月份）、按月的设备-天首末有出力时刻分位数，用于校验 `daylight_window_source='empirical'` 的推导结果是否合理（见需求 7 第 16a、16b 条）。
5e. THE Preflight_Probe SHALL 输出夜间测量值的量级异常检查（实测夜间 `value` 绝对值最大 1.04e11、同批 `i_cal` 最大 1.75），用于确认需求 7 第 16e 条的坏值拦截是否必要。
6. THE Preflight_Probe SHALL 校验输入规模与现状事实一致：`pv_cumulative_labeled_merged.parquet` 为 1,056,806 行、`dataset_combined.parquet` 为 303,321 行、采样间隔为 300 秒、单设备单日**理论满值**为 288 点（实测分布见现状与问题第 1 项，不是恒定值）、`state.json` 含 4 条 `labeled_imports` 与 18 条 `verdict_entries`、`time_slices/` 下 2 个切片分别为 153 行与 140 行。
7. IF 第 6 条中任一数值与实测不符，THEN THE Preflight_Probe SHALL 在报告中标记「事实基线已变化」，并要求重新确认迁移方案。
8. THE Preflight_Probe SHALL 复现现状缺陷作为重构前基线：对武当湖 / 04#箱变_汇流箱01 / 支路1 / 2020-05-08，断言 concat 后为 441 行、按 `[time, site_id, device_id, branch_id, time_window]` 去重后仍为 441 行、`time_window_split.execute(solar_mode="day_and_night")` 产出 3 个样本且点数分别为 118 / 170 / 153。
9. THE Preflight_Probe SHALL 验证 `time_window_split.py` 的全 `#` 透传行为：构造 `time_window` 列每行均含 `#` 的 DataFrame，调用真实 `execute()`，断言输出与输入逐行相等（已实跑通过，见现状与问题第 23 项）。
10. THE 迁移执行 SHALL 以第 9 条断言通过为前置条件。
11. IF 第 9 条断言失败，THEN THE 迁移执行 SHALL 暂停，并把需求 9 的零新增算子方案重新提交设计评审。
12. THE Preflight_Probe SHALL 输出源数据中出现但当前 `label_space_version` 中不存在的 `label_id` 清单（实测为空，本次迁移不需要 reconcile）。
13. THE Preflight_Probe SHALL 输出自由段标注输入源文件的设备数与自然日跨度（实测 `pred-20260720092117-9348327a.csv` 含 189 个设备、跨 5 个不连续自然日），用于确认需求 5 第 5 条 `op_scope` 限定范围的必要性。
14. THE Preflight_Probe SHALL 把上述所有指标写入一份可归档的前置验证报告文件。

### 需求 16：已确认缺陷的修复

**User Story:** 作为标注人员与运维人员，我希望撤销真正生效、跨会话重复打标被拦住、旧模板不会静默降级，以便标注结果可信。

#### 验收标准

1. WHEN 标注人撤销一条自由段标注，THE Point_Label_Service SHALL 把对应 `human_range` 操作及其伴生 `human_day` 操作的 `status` 置为 `revoked`、重物化受影响采样点，且 THE Snapshot_Builder SHALL 在后续所有快照中排除被撤销操作的影响（修复 `freeform_labeling.revoke_label()` 只删会话指针、不删 `labeled_imports` 账本条目导致撤销后标签仍进入快照的缺陷）。
2. WHEN 标注人对某设备某时段提交自由段标注，THE Point_Label_Service SHALL 对 `label_ops` 执行全局重叠检查，检查范围覆盖所有 `review_id`（修复现有仅在单个审核会话内用 `list_labels(review_id)` 检查、跨会话可对同设备同时段重复打标的缺陷）。
3. IF 跨会话的重叠自由段被提交，THEN THE Point_Label_Service SHALL 按需求 5 第 11 条返回 HTTP 422 状态码。
4. WHEN `stratified_cv_eval.py` 读入的数据中 `time_window` 列存在不含 `#` 的取值，THE `stratified_cv_eval.py` SHALL 输出显式告警或错误，禁止静默按旧 resample 逻辑降级（修复把 `load_csv.file_path` 指向无 `sample_id` 旧 parquet 时静默回退且不报错的风险）。
5. THE `stratified_cv_eval.py` SHALL 使第 4 条的行为（告警或错误）可通过配置项选择，且默认取值 SHALL 使问题对使用者可见。

### 需求 17：向后兼容、工作区安全与回滚

**User Story:** 作为项目负责人，我希望重构过程不破坏当前很脏的工作区、旧模板仍可运行、且方案可回滚，以便随时能退回现有链路。

#### 验收标准

1. THE 本次重构 SHALL 不清理、不重置、不删除任何历史产物（含 `__pycache__`、回测输出、日志、数据库文件、未跟踪文件）。
2. THE 本次重构 SHALL 不执行破坏本地改动的版本控制操作（含 `git reset --hard`、`git checkout --`），除非用户显式授权。
3. WHERE 存在未迁移的旧工作流模板，THE Training_Pipeline SHALL 保持这些模板可继续执行（依据需求 11 第 2、5 条与需求 9 第 13、14 条的默认值不变约束）。
4. THE 本次重构 SHALL 保留 `training_samples` 表的 `label` 列与既有唯一约束，使旧读路径在迁移期间仍可运行。
5. THE 迁移方案 SHALL 提供回滚路径，且回滚过程不修改 `backend-service/datasets/` 下的源 parquet 与 `training_workspace/pv_fault/` 下的历史产物。
6. THE 代码与文档中的文件引用 SHALL 使用相对路径（相对项目根或 `backend-service/`），不使用绝对路径。
7. THE 本次重构新增或修改的 Markdown 与代码块 SHALL 按项目规范标注 `@AI_GENERATED` 起止标记。
8. THE label_ops 表 SHALL 通过 `migration_batch_id` 区分「迁移产生的操作」与「迁移后新增的操作」，人工新增操作该字段取值为 NULL。
9. WHEN 执行回滚，THE Migration_Tool SHALL 只把指定 `migration_batch_id` 的操作置为 `revoked` 并重物化受影响采样点，保留 `migration_batch_id` 为 NULL 的操作（迁移后人工新打的标注不被回滚波及）。
10. WHEN 回滚完成，THE Migration_Tool SHALL 产出回滚报告，包含被撤销的操作数、按 `source` 分组的明细、受影响采样点数。
11. IF 回滚请求未指定 `migration_batch_id`，THEN THE Migration_Tool SHALL 拒绝执行并返回错误（禁止整表清空式回滚）。

### 需求 18：逐点标签与标签注册表的一致性

**User Story:** 作为标注与数据治理人员，我希望每个点上的 `label_id` 永远能在标签注册表中找到对应含义，以便标签空间演进时历史标签仍可解释。

#### 验收标准

1. WHERE 标注操作的 `label_id` 非 NULL，THE Point_Label_Service SHALL 在写入前校验该 `label_id` 存在于当前 `label_space_version` 的标签集合中。
2. IF 待写入操作的 `label_id` 不在当前标签空间中，THEN THE Point_Label_Service SHALL 拒绝写入并返回 HTTP 422 状态码，且响应体中包含该 `label_id` 与当前 `label_space_version`。
3. THE Label_Registry_Service SHALL 保持 `label_id = 0` 恒定表示「正常」，不把该编码重新分配给其他标签名称（现 `pv_fault` 槽位已如此，K4 与需求 5 第 4 条依赖该约定）。
4. WHERE 某采样点的 `label_id` 为 NULL（unknown），THE Point_Label_Service SHALL 跳过第 1 条校验并允许该状态存在。
5. WHEN 标注人新增一个故障类型，THE Labeling_API SHALL 先调用 `LabelRegistryService.allocate_label()` 分配 `label_id`，再写入携带该 `label_id` 的标注操作。
6. THE Labeling_API SHALL 把第 5 条的「分配标签」与「写入操作」两步置于同一逻辑事务内。
7. IF 第 5 条中的操作写入失败，THEN THE Labeling_API SHALL 回滚本次标签分配，避免留下没有任何操作引用的孤儿标签。
8. THE label_ops 表与 point_labels 表 SHALL 各自记录写入时的 `label_space_version`。
9. WHEN 迁移遇到当前标签空间中不存在的 `label_id`，THE Migration_Tool SHALL 调用 `LabelRegistryService.reconcile_labels()` 补齐业务名称并生成新的 `label_space_version`（沿用现有「待命名-故障码N」+ `source='snapshot_reconciliation'` 的做法）。
10. THE Migration_Tool SHALL 在 reconcile 过程中保留源数据的原始 `label_id` 取值，不重新编码。
11. IF 某条操作的 `label_id` 无法通过 reconcile 补齐，THEN THE Migration_Tool SHALL 记入对账报告失败明细并保留该操作为待人工处理状态，不静默丢弃。
12. THE Point_Label_Service SHALL 提供按 `label_space_version` 追溯的查询能力，使历史标签可对应到当时的标签空间快照（`label_registry.json` 的 `history` 记录）。

### 需求 19：人工裁决落标的主链路

**User Story:** 作为标注人员，我希望我在审核页上的每一次裁决都确定地变成标注操作并推进重训计数，以便标注动作与训练集之间的关系可追踪。

#### 验收标准

1. THE Labeling_API SHALL 使审核会话的审核单元等同于训练样本，`unit_key` 取值等于该样本的 `sample_id`（见需求 8 第 5 条）。
2. WHEN 人工提交 `confirm`、`correct` 或 `new_label` 裁决，THE Point_Label_Service SHALL 写入一条 `source='human_day'` 标注操作。
3. WHEN 按第 2 条写操作，THE Point_Label_Service SHALL 取该样本的 `[t_start, t_end)` 作为操作边界。
4. WHEN 人工提交 `skip` 裁决，THE Labeling_API SHALL 不写入任何操作（保持现有「skip 不产生真值」语义）。
5. WHEN 标注人在波形图上框选打标，THE Point_Label_Service SHALL 按需求 5 第 4 条写入 `human_range` 操作及其伴生操作。
6. WHEN 裁决成功写入操作，THE Cumulative_Training_Service SHALL 递增 `pending_change_count`。
7. THE Cumulative_Training_Service SHALL 按**标注操作**递增 `pending_change_count`，不按受影响采样点数递增；WHERE 一次框选打标产生 `human_range` 与伴生 `human_day` 两条操作，THE Cumulative_Training_Service SHALL 只计 **1** 次变更（依据见现状与问题第 18 项：一次自由段标注实测 `change_units=1`；K4 使一次框选影响的点数从 153 涨到约 288，若按点计数则单次操作即超过默认阈值 20 并立刻触发重训）。
8. WHILE `pending_change_count` 达到 `retrain_label_threshold`（环境变量 `PV_RETRAIN_LABEL_THRESHOLD`，默认 20），THE Cumulative_Training_Service SHALL 按现有机制触发重训请求。
9. WHEN 同一 `sample_id` 重复提交相同裁决，THE Cumulative_Training_Service SHALL 不递增 `pending_change_count`（沿用 `admit_verdict()` 返回 `reason="duplicate_verdict"` 的去重语义）。
10. WHERE 裁决动作为 `correct` 且该样本时段已存在 active 操作，THE Point_Label_Service SHALL 按需求 6 第 2 条新增操作并把旧操作置为 `revoked`。
11. THE `state.json` 的 `verdict_entries` SHALL 在迁移完成后不再作为标签来源，仅保留为历史对账数据。
12. IF 快照构建路径尝试从 `verdict_entries` 读取标签，THEN THE Snapshot_Builder SHALL 终止构建并报错（标签唯一来源是 `point_labels`）。

### 需求 20：待标注队列

**User Story:** 作为标注人员，我希望仍处于 unknown 的时段有一个明确的待办列表，以便这些时段不会永久停留在「状态未知」。

#### 验收标准

1. THE Point_Label_Service SHALL 把待标注队列定义为 `point_labels` 中 `label_id IS NULL` 的采样点、以及未被任何 active 标注操作覆盖的采样点，按 `(site_id, device_id, branch_id)` 与时间连续性聚合为可读的待办条目。
2. THE 设计文档 SHALL 记录 K4 对该队列规模的影响：旧方案中「人工框选后当天其余时段设为 unknown」会持续制造 unknown 点，K4 生效后这些点直接判为正常，因此待标注队列只包含**从未被任何标注操作覆盖过**的时段，规模显著小于旧方案。
3. THE Labeling_API SHALL 提供待标注队列查询接口，支持按 `site_id`、`device_id`、时间范围、最小采样点数过滤。
4. THE Labeling_API SHALL 对待标注队列查询结果分页返回，响应中包含 `total`（符合条件的条目总数）与当前页条目列表。
5. THE Labeling_API SHALL 使每个队列条目携带其时间范围、采样点数，以及该范围内曾存在但已被撤销的操作的 `label_id` 与 `reviewer`（若有），使标注人知道该时段的历史判断。
6. WHEN 标注人从队列条目进入波形视图，THE Review_UI SHALL 定位到该条目的时间范围。
7. WHEN 标注人对某 unknown 时段完成打标，THE Point_Label_Service SHALL 写入相应标注操作（`human_range` 或 `human_day`）并重物化，使该时段的生效标签由 NULL 变为具体取值。
8. THE 运营面板 SHALL 展示待标注队列规模：unknown 采样点数、其占总采样点数的比例、按设备分布的 Top N。
9. WHERE 待标注队列为空，THE Review_UI SHALL 渲染空态提示而非空白区域。

### 需求 21：规模、性能、并发与可复现

**User Story:** 作为平台运维人员，我希望逐点标签表与快照构建在真实数据规模下可用、并发标注不破坏一致性、同一输入可复现同一快照，以便重构后的链路能长期运行。

#### 验收标准

1. THE point_labels 表 SHALL 支持至少百万级行：实测迁移后初始规模为 **1,056,806** 行逐点标签与 **4,457** 条 `day_label` 标注操作（另加 2 条 `human_range`、2 条伴生 `human_day`、18 条 `verdict` 迁移操作与聚类确认操作），实际生产规模随新增测量数据与标注持续增长。
2. THE 设计文档 SHALL 记录逐点存储相对区间存储的规模代价：同一份标签信息以区间表达约需 2,699~4,457 行、以逐点表达需 1,056,806 行（约 237~392 倍），该代价是 K1 决定的已知取舍，换取的是「无区间差集运算、标签粒度直观可查」。
3. WHEN 按设备与时间范围查询逐点标签，THE Point_Label_Service SHALL 命中需求 2 第 6 条定义的索引，不执行全表扫描。
4. THE Snapshot_Builder SHALL 在 conda 环境 `cp_web` 单机条件下于 30 分钟内完成对 `pv_cumulative_labeled_merged.parquet`（1,056,806 行测量数据）的全量快照构建；因需求 14 第 3 条已确认 `dataset_combined.parquet` 为该文件的完全子集，快照构建的测量数据来源 SHALL 仅为 `pv_cumulative_labeled_merged.parquet`。
5. WHILE 快照构建进行中，THE Snapshot_Builder SHALL 通过现有 `update_retrain_progress()` 机制输出阶段与进度，使前端可轮询查看。
6. THE Point_Label_Service SHALL 支持多个标注人并发提交标注操作。
7. WHEN 同一 `(site_id, device_id, branch_id)` 的时间范围存在并发写入，THE Point_Label_Service SHALL 串行化该设备维度的「写操作 + 重物化」组合，使需求 4 第 3 条的一致性恒成立。
8. THE Snapshot_Builder SHALL 把 `label_snapshot_hash` 定义为：所有 `status='active'` 标注操作按 `op_id` 升序排列后，其规范化序列化内容的 SHA-256 摘要。
9. THE `label_snapshot_hash` 的哈希输入 SHALL 只包含 `op_id`、`site_id`、`device_id`、`branch_id`、`t_start`、`t_end`、`label_id`、`source`、`status`、`label_space_version`，排除 `updated_at` 等易变字段。
10. WHEN 同一 `label_snapshot_hash`、同一 `sample_strategy` 与同一份测量数据被再次构建，THE Snapshot_Builder SHALL 产出与首次构建逐行等价的快照。
11. THE Snapshot_Builder SHALL 把本次构建使用的 `label_snapshot_hash` 写入快照元数据，使需求 12 第 3 条的模型文件记录可与快照对账。
12. WHILE 快照构建进行中发生标注写入，THE Snapshot_Builder SHALL 基于构建开始时确定的标签版本读取，使单次快照内容自洽。

### 需求 22：历史设计文档与本次重构的一致性

**User Story:** 作为后续接手的开发者或 Agent，我希望过期的历史设计文档被明确标注为已被取代，以便我不会照着旧的 `solar_mode` 切分模型或段表模型继续开发。

#### 验收标准

1. WHEN 本次重构落地完成，THE 交付方 SHALL 在 `docs/specs/pv-fault-iterative-labeling-loop/design.md`、`requirements.md`、`design-feature-enhancement.md`、`requirements-feature-enhancement.md` 四个文件顶部标注「已被 `.kiro/specs/pv-fault-label-segment-redesign/` 取代」。
2. THE 标注 SHALL 指明取代范围：与 `solar_mode` 切分模型、`time_window` 字符串语义、逐点 `label` 与测量数据同表相关的章节全部作废。
3. THE 交付方 SHALL 保留这些历史文档文件本身，不删除（依据需求 17 第 1 条）。
4. WHERE 历史文档描述的行为与本文档冲突，THE 后续实现 SHALL 以本文档为准。
5. THE 交付方 SHALL 核对 `docs/specs/pv-fault-iterative-labeling-loop/tasks.md` 与 `tasks-feature-enhancement.md` 中未完成的任务项，并标注哪些任务因本次重构作废。
6. THE 本文档 SHALL 在其自身范围内声明：第五轮修订（K1~K4）取代了本文档第一至第四轮中所有以「标注段 / label_segments / Segment_Resolver / ResolvedSegment / 段裁剪 / 残段」为核心的条目；这些概念在本次重构中不再存在。

### 需求 23：新旧建模路径并存与精度对比（K7）

**User Story:** 作为算法负责人，我希望这次重构落地后，老的按天建模路径不被删除、仍能运行，并且新旧两条路径在同一批数据上用同一把尺子比精度，由数据决定谁上生产、谁当备选，以便我不必赌新路径一定更好。

#### 验收标准

1. THE 本次重构 SHALL 把老的按天建模路径（现状生产链路：`label` 逐点列 + 按值判定白天/夜间 + 天级样本）作为一等公民保留，使其在重构落地后仍可独立运行并产出模型，不因新路径上线而删除或降级为不可运行。
2. THE 新路径（`point_labels` + 时钟窗白天夜间 + `split_mode`）与老路径 SHALL 能在同一批测量数据、同一评估口径（同 `n_repeats` / `test_ratio` / 分层与分组设置）下分别训练并评估，产出可对比的精度指标。
3. THE 对比评估 SHALL 复用现有 `backend-service/services/iterative_labeling/split_mode_compare.py` 作为骨架，不新建一套并行的评估框架。
4. THE 对比评估 SHALL 输出一份对照报告，至少包含：每条路径的 `macro_f1_mean`、`accuracy_mean`、各 label 的 recall、样本量，以及新旧路径的差值。
5. THE 生产模型登记 SHALL 支持标注「当前生产主线路径」与「可回退备选路径」两个指针，使胜出路径为主线、另一条为备选。
6. WHEN 主线路径的模型出现问题（精度回退或运行故障），THE 生产切换机制 SHALL 支持回退到备选路径的最近可用模型，回退动作记入审计。
7. THE 对比口径 SHALL 显式声明新旧不可直接比的前提已被消除：默认 `split_mode=by_day_night` 且白天夜间按时钟判定，与老路径的天级 + 按值判定口径不同，因此对比必须建立在「同一批原始测量数据分别按两条路径完整跑一遍」之上，不能拿历史上用老口径训练的模型指标直接对比。
8. THE 双路径对比 SHALL 覆盖「老按天路径 vs 新逐点标签路径（`by_day` / `by_day_night`）」；WHERE 后续 `pv-fault-timeseries-diagnosis` spec 的时序模型可用，THE 对比框架 SHALL 支持把时序路径作为第三条候选路径接入（该 spec 需求 3 第 3、4 条），使三条路径在同一评估口径下比较。
9. THE 对比评估 SHALL 可重复执行：同一批数据、同一配置重复运行产出一致结论（依赖固定随机种子，与现有 `stratified_cv_eval` 的 `random_state` 一致）。

## 决策到需求映射表（便于评审对照）

| 决策 | 内容摘要 | 对应需求 |
|---|---|---|
| K1 | 标签粒度=采样点；`point_labels` + `label_ops` 两表；不引入段这一存储概念 | 需求 1、2 |
| K2 | 样本按标签形态变化断开，样本内标签纯一致，仍是单标签 | 需求 7 第 4、5、6 条 |
| K3 | 存储层允许跨天（操作/逐点标签不强制按天）；样本切分按天（跨天建模移至时序 spec，见 K8） | 需求 5 第 13 条；需求 10 第 6、7 条 |
| K4 | 人工框选后同设备同日未框选部分默认判为正常 | 需求 5 第 4~10 条；需求 14 第 7 条；需求 19 第 7 条；需求 20 第 2 条 |
| K5 | 白天/夜间按时钟判定（`daylight_window`），不按测量值 | 需求 7 第 16、16a~16e 条；需求 9 第 8、8a 条；需求 12 第 3、16a、16b 条；需求 15 第 5b~5e 条 |
| K6 | 切分方式扁平二选一 `split_mode` ∈ {`by_day`, `by_day_night`}，不嵌套 | 需求 7 第 2、3、3a、5、10、17、18 条；需求 10 第 9a 条；需求 11 第 8、8a 条；需求 12 第 3、15、16a 条 |
| K8 | `by_label_run`（跨天时序切分）移出本 spec，交 `pv-fault-timeseries-diagnosis` spec 用序列模型承接 | 决策 K8；需求 7 第 2、3、8 条；需求 12 第 15、16 条；需求 23 第 8 条；第九轮修订表 |
| D1 | 标签与样本构造彻底分离；日照切分不进标签存储 | 需求 1 |
| D2 | 表结构；`training_samples` 退化为纯测量表 | 需求 2 |
| D3 | `source` 与 `priority` 分级；按 `source` 分口径评估；unknown 排除 | 需求 3 |
| D4 | 物化规则（逐点取最大优先级），取代段裁剪算法 | 需求 4 |
| D5 | 操作不变量与「未框选即正常」；`op_scope` 限定范围 | 需求 5 |
| D6 | 操作生命周期；撤销含伴生操作联动；重物化 | 需求 6 |
| D7 | 策略两维度（跨度 / 时段）；策略不变量；`min_points` | 需求 7 |
| D8 | `sample_id` 统一标识；取代 `unit_key` 三套格式；推理命名空间 | 需求 8 |
| D9 | 零新增算子硬约束；预物化快照；两个可选参数；快照自检 | 需求 9、10、11 |
| D10 | 训练/预测共用策略；策略随模型持久化；预测侧退化与不对称性 | 需求 12 |
| D11 | 特征 schema 稳定性 | 需求 13 |
| D12 | 4 个源迁移；操作分块不影响样本边界；闭开区间换算与对账 | 需求 14 |
| D13 | 前置验证探针与透传门禁 | 需求 15 |
| D14 | 撤销失效、跨会话重复打标、旧模板静默降级 | 需求 16 |
| D15 | 标签注册表一致性；`label_id=0` 恒为正常 | 需求 18 |
| D16 | 人工裁决落标主链路；重训计数按操作计 | 需求 19 |
| D17 | 待标注队列定义与运营可见 | 需求 20 |
| D18 | 规模/耗时/并发/可复现与 `label_snapshot_hash` 口径 | 需求 21 |
| D19 | 历史 spec 文档标注为已被取代 | 需求 22 |
| K7 | 新旧建模路径并存、A/B 精度对比、互为备选与回退 | 需求 23 |
| 通用 | 向后兼容、工作区安全、按批次回滚 | 需求 17 |

## 第五轮修订（P1~P9）：从段模型改为逐点模型

第五轮由用户三项判断驱动：段概念容易误导人、跨天建模必须可实现、人工标注的语义就是「只标有问题的时段」。下表记录被推翻的旧条目与新落点。

| 编号 | 旧方案（第一至第四轮） | 新方案（第五轮） | 落地位置 |
|---|---|---|---|
| P1 | `label_segments` 段表为标签权威，段是存储实体，术语含 Segment_Resolver / ResolvedSegment / `segment_id` | `point_labels` 逐点标签表为唯一权威；区间只以 `label_ops` 形式存在，仅作审计与撤销单元 | 需求 1、2；术语表全部改写 |
| P2 | 旧需求 5「段裁剪算法」：区间差集五种情形（无交集 / 完全覆盖 / 削左头 / 削右尾 / 掏中间裂两段）、`parent_segment_id`、顺序无关性证明 | **整条删除**，改为需求 4「标签物化规则」：逐点取最大 `priority`，无任何区间运算 | 需求 4（新）；旧需求 5 作废 |
| P3 | 旧需求 6「残段语义」：`human_range` 覆盖后残段 `label_id` 置 NULL、加入待标注队列 | 改为 K4：同设备同日未框选部分默认判为正常（`label_id=0`、`source=human_day`、`priority=80`），实现方式是写一条伴生操作而非引入残段概念 | 需求 5 第 4~10 条；旧需求 6 作废 |
| P4 | 旧需求 4 第 7 条强制「段不跨自然日」，理由是保证 `group_key` 的 `date` 分量唯一 | 删除该约束（K3）；`group_key` 改为按自然日连通块（day-block）计算，在允许跨天的同时保持防泄漏强度 | 需求 5 第 13 条；需求 10 第 6、7 条 |
| P5 | 样本必须落在单个段内（旧需求 8 第 8 条「不越界不变量」）；混合标签需靠众数或纯度阈值处理 | 样本边界由标签形态变化决定（K2），标签纯一致成为不变量，混合标签情形在结构上不存在 | 需求 7 第 4、6 条 |
| P6 | 策略清单为 `whole` / `daylight` / `night` / `day_and_night` / `solar_period` / `fixed_window` 平铺，且「按天」是段表层面的强制前置动作 | 拆为跨度维度（`by_label_run` / `by_day` / `fixed_window`）与时段维度（`whole` / `daylight` / `night` / `day_and_night` / `solar_period`）两个正交维度；按天降级为跨度维度的一个取值 | 需求 7 第 2、3 条 |
| P7 | `sample_id = {segment_id}#{period_role}#{seq}`，可解析回 `segment_id` | `sample_id = smp-{device_hash8}-{t_start}#{period_role}#{seq}`，不含 `segment_id`；溯源改由快照的 `label_op_id` 列承载（因一条样本的点可能来自多个操作） | 需求 8 第 1、9 条 |
| P8 | 迁移用 RLE 压缩把逐点 `label` 压成段（4,457 段），压缩比 237:1 是方案优点 | 迁移改为按设备-天生成 4,457 条标注操作 + 物化出 1,056,806 行逐点标签；压缩不再是目标，逐点存储的规模代价被显式记为已知取舍 | 需求 14 第 1、2、5 条；需求 21 第 1、2 条 |
| P9 | 透传列清单 13 列，含 `segment_source` | 改为 15 列，`segment_source` → `label_source`，新增 `label_source_purity`、`label_op_id`；进特征矩阵的数值列由 11 个增为 12 个 | 需求 3 第 16、17 条；需求 10 第 1 条；需求 11 第 8、10、11 条 |

## 第六轮修订（Q1~Q5）：切分方式收敛为 2 项 + 白天夜间改为按时钟判定

第六轮由用户两项判断驱动：切分方式只需要「时序切分」和「按天切分」两种；白天/夜间必须按时间判定而不是按电流值判定，才能让模型学到「夜间无电流」这种形态。

| 编号 | 旧方案（第五轮及以前） | 新方案（第六轮） | 落地位置 |
|---|---|---|---|
| Q1 | 跨度维度 3 种（`by_label_run` / `by_day` / `fixed_window`）× 时段维度 5 种（`whole` / `daylight` / `night` / `day_and_night` / `solar_period`）= 15 种组合 | 收敛为 `span_mode`（2 选 1）+ `split_day_night`（布尔），共 4 种组合；删除 `fixed_window` 与 `solar_period` | 需求 7 第 2、3、3a、10 条 |
| Q2 | 白天/夜间按值判定：`value >= 当天 max(value) × irr_threshold(0.05)`，沿用 `solar_window._day_night_masks()` | 改为按 `daylight_window` 时钟窗判定，完全不依赖当日测量值；支持 `empirical`（按站点-月份从跨天聚合中位曲线推导，默认）与 `fixed`（06:00–18:00 兜底）两种来源 | 需求 7 第 16、16a~16e 条；需求 9 第 8、8a 条 |
| Q3 | `period_role` 取值域 6 个（含 `peak` / `trans` / `sub`），one-hot 6 列 | 取值域 3 个（`whole` / `daylight` / `night`），one-hot 3 列；`peak` / `trans` 随 `solar_period` 删除（其判定依据「功率 > 当天峰值 30%」与被否决的按值判定同源），`sub` 随 `fixed_window` 删除 | 术语表；需求 10 第 1、8、9、9a 条 |
| Q4 | 透传列 15 列、进特征矩阵的数值列 12 个 | `split_day_night=true` 时透传 12 列、数值列 9 个；`split_day_night=false` 时只透传 4 列（3 个 `period_is_*` 与 5 个 `night_*` 此时是常量，须移出以免喂无区分度列） | 需求 11 第 8、8a、9、10、14、15 条；需求 10 第 9a 条 |
| Q5 | 第五轮曾把 `max_power` 阈值口径从「按自然日」改为「按样本范围」，并以 4.80% 差异为据 | 该条已被 Q2 整体取代——阈值本身不再存在，判定改为时钟窗；原 4.80% 的实测结论保留为历史依据，但不再驱动任何需求条目 | 需求 7 第 16 条（重写）；需求 15 第 5b~5e 条 |

Q2 的根因是一处**循环论证**：按值判定用「出力低」定义「夜间」，而「出力低」本身往往就是故障症状。实测后果是正午 12 点有 12.6% 的点被判为夜间、35.8% 的设备-天夜间被切成 3 段以上（最多 43 段），使本意抓夜间漏电流的 5 个 `night_*` 特征被白天低出力点污染。改为时钟判定后，夜间点 `i_cal` 零值占比达 94.47%（白天仅 5.96%），且各 label 的夜间非零电流占比跨度为 7.45%~100.00%，说明这组特征在正确时段口径下具备实际区分度。

## 第七轮修订（R1~R2）：切分参数从嵌套双开关改为扁平三选一

第七轮由用户一项判断驱动：切分不要做成嵌套的，白天/夜间单独算一种切分方式，一共三种。

| 编号 | 旧方案（第六轮 K5 阶段） | 新方案（第七轮 K6） | 落地位置 |
|---|---|---|---|
| R1 | 两个配置项嵌套：`span_mode`（`by_label_run` / `by_day`）× `split_day_night`（布尔），共 4 种组合 | 单一配置项 `split_mode` 三选一：`by_label_run` / `by_day` / `by_day_night`；白天/夜间成为独立的第三种模式而非叠加开关 | 需求 7 第 2、3、3a 条；所有引用 `span_mode` / `split_day_night` 的条目改为 `split_mode` |
| R2 | 无实测样本量对照 | 补三种模式实测样本量：2,699 / 4,457 / 13,371；并记录 `by_day_night` 夜间样本中位数仅 39 点、区分度高度依赖 `night_*` 特征这一已知取舍 | 现状与问题第 30 项；需求 7 第 17 条 |

R1 的动机是 K5 阶段 4 种组合里 `by_label_run + split_day_night=true` 语义含混：跨天样本再按每天的白天夜间断开，断开依据在"标签形态"与"时钟"之间混用。扁平三选一后每种模式断开依据单一：`by_label_run` 只看标签、`by_day` 看标签 + 自然日、`by_day_night` 看标签 + 自然日 + 时钟窗。

## 第八轮修订（S1~S2）：日照窗用近期季节数据 + 新旧路径并存对比

第八轮由用户两项判断驱动：日照窗做中位数不该用全历史（光伏有季节性、且板会衰减），要用最近数据 + 按季节；老的按天建模要保留，和新路径对比精度、互为备选。

| 编号 | 旧方案（第六/七轮） | 新方案（第八轮） | 落地位置 |
|---|---|---|---|
| S1 | 日照窗按 `(site_id, 自然月 YYYY-MM)` 用全历史数据推中位曲线 | 改为按 `(site_id, 季节桶 月份1-12)` + 只用最近 `daylight_window_lookback_months`（默认 24）个月数据推导；数据不足先放宽回溯窗、再回退 fixed | 需求 7 第 16、16a、16b、16c 条；术语表新增 `daylight_window_lookback_months` 与「季节桶」 |
| S2 | 新路径「取代」老路径，老路径仅迁移期兼容 | K7：老按天路径作为一等公民保留、可运行可回退；新旧同口径 A/B 对比精度，胜者为主线、另一条为备选；复用 `split_mode_compare.py` | 决策 K7；需求 23（全部） |

S1 的理由：日照的季节性由「月份」决定、与「年份」无关，用月份桶（1~12）能让不同年份的同一季节共用窗口、样本更充足；同时光伏板随时间衰减、周边遮挡会变，早期数据的日照形态未必代表现状，故只用最近回溯窗内的数据推导。回溯窗的具体月数是任务清单里「日照窗阈值标定」的一部分，默认 24 为初值。

S2 的理由：本次重构改动面大（标签存储、白天夜间口径、切分方式都变），不能默认新路径一定更好；老路径保留 + 同口径对比 + 数据决策，是把「新方案是否真的更好」这个判断交给实测而非假设。注意新旧口径不同（默认 `by_day_night` + 时钟窗 vs 老的天级 + 按值判定），对比必须是「同一批原始数据分别按两条路径完整跑一遍」，不能拿历史老口径的模型指标直接比。

## 第九轮修订（T1）：时序切分 `by_label_run` 移出本 spec

第九轮由用户一项判断驱动：时序场景要单独做，不和逐点标签重构合在一个 spec 里。

| 编号 | 旧方案（第六~八轮） | 新方案（第九轮 K8） | 落地位置 |
|---|---|---|---|
| T1 | `split_mode` 三选一含 `by_label_run`（跨天时序切分，仍走 RF 聚合特征） | `split_mode` 二选一 `by_day` / `by_day_night`；`by_label_run` 移出，跨天/时序建模由独立 spec `pv-fault-timeseries-diagnosis` 用序列模型承接 | 决策 K3（改）、K6（改）、K8（新）；需求 7 第 2、3、3a、8 条；需求 12 第 3、15、16 条；需求 13 第 5 条；需求 14 第 5 条；需求 15 第 5、5a 条；需求 23 第 8 条 |

T1 的动机：`by_label_run` 是个尴尬中间态——既想跨天、又用 RF 聚合特征，且预测时无标签只能退化为按天，造成训练/预测特征窗口长度不一致（第八轮 req 23.8 已记录该偏差）。用户第 8 轮后明确要把时序场景单独做，于是把它整体移出：本 spec 专注按天 RF 路线（`by_day` / `by_day_night`，训练预测口径自洽），跨天时序诉求由新 spec 用真正的序列模型（CNN-LSTM / ROCKET / InceptionTime）实现，两条 spec 通过需求 23 的双路径对比框架接入比较。移出后本 spec 获得一个额外好处：两种保留模式训练/预测样本边界严格对齐，不再有退化处理。

**说明**：`by_label_run` 相关的历史实测数字（2,699 样本、934 条跨天、单样本 144~2,015 点、日照阈值敏感度中的跨天部分）在本 spec 中降级为「历史参考」，其归属转移到 `pv-fault-timeseries-diagnosis` spec；第五~七轮修订表（P6/Q1/R1）中出现的 `by_label_run` 作为历史记录保留，不回改。

## 前四轮修订中仍然有效的结论（未被第五轮推翻）

下列结论建立在对现有代码与真实数据的实测之上，与标签存储形态无关，因此在逐点模型下继续有效：

| 来源 | 结论 | 现落地位置 |
|---|---|---|
| G1 | 夜间特征真实为 5 列（非 2 列） | 现状与问题第 14 项；需求 10 第 1 条 |
| G2 | `period_role` 字符串进不了特征矩阵，须 one-hot 展开为 6 列 | 现状与问题第 16 项；需求 10 第 8、9 条 |
| G3 | `inference` 不属于 `source` 枚举；推理不落库 | 需求 3 第 11 条；需求 12 第 8~12 条 |
| G4 | 设备键统一为 `(site_id, device_id, branch_id)` 三段式 | 需求 2、15 第 3 条 |
| G5 | 标签注册表是 `label_id` 分配真源；`label_id=0` 恒为正常 | 现状与问题第 15 项；需求 18 |
| G9 | 时间切片是闭区间，须转半开区间并按 `row_count` 对账 | 现状与问题第 17 项；需求 14 第 11~14 条 |
| G14 | `min_points` 与 `keep_threshold` 正交，两者都保留 | 需求 7 第 11、19 条 |
| G15 | 快照写出前须自检 `time_window` 全含 `#` | 需求 9 第 11、12 条 |
| G16 | 时间切片 CSV 默认不删除，只标注可归档 | 需求 14 第 17 条 |
| G17 | 运营面板改造期间的空态 / 加载态 / 错误态降级 | 需求 3 第 8~10 条 |
| C1 | 零改动清单（5 个算子文件）与限定范围改动清单（2 个文件）互斥 | 需求 9 第 6、7、16 条 |
| C2 | `passthrough_fields` 只挂统计特征节点，因该路即合并基表 | 现状与问题第 19 项；需求 11 第 8、13、14 条 |
| C3 | `attach_night_features` 在全透传模式下彻底失效，须从模板移除 | 现状与问题第 21 项；需求 12 第 4 条 |
| C4 | 透传列名不得与另两路输出列同名（否则静默跳过） | 现状与问题第 20 项；需求 11 第 15~17 条 |
| E2 | 全 `#` 透传断言已实跑通过，零新增算子方案成立 | 现状与问题第 23 项 |
| E4 | `dataset_combined.parquet` 是完全冗余源，不参与迁移 | 需求 14 第 3、4 条 |
| E6 | 本次迁移不需要触发 reconcile | 需求 15 第 12 条 |
<!-- @AI_GENERATED: end -->
