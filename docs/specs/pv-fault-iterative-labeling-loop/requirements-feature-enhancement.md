<!-- @AI_GENERATED -->
# 扩展需求文档：光伏故障诊断窗口切分策略与标签扩充策略增强

> **本文档是对 `requirements.md`（光伏故障人机协同迭代标注闭环）的扩展补充。**
> 聚焦两个独立的优化方向：
> 1. **诊断窗口切分策略增强**（`SolarWindow_Segmentation`）：在现有 `daily` 整天切分基础上，新增 `daylight`、`solar_period`、`multiscale` 三种更精细的切分模式，减少夜间无效数据干扰，提升样本密度与故障识别能力。
> 2. **标签扩充策略增强**（`Label_Expansion_Strategy`）：在现有人工审核触发标签扩充的基础上，增加不确定性采样、聚类新类候选发现、高置信度伪标签回流、分歧优先采样四项系统性机制。
>
> **本文档不修改原有 `requirements.md` 中的任何需求（需求 1～12），需求编号从 13 开始续接。**
> 向后兼容约定见文末「与现有系统的衔接说明」章节。

---

## 扩展术语表

> 以下术语为本文档新增，不重复原有 `requirements.md` 术语表中已定义的条目。

- **SolarWindow_Segmentation（日照窗口切分器）**：`set_time_window()` 的扩展模式，负责在特征工程上游执行基于功率/辐照度的时段识别与切分，向 `FeatureEngineer` 输出已标注 `time_window` 的数据帧。
- **solar_mode（日照切分模式）**：`set_time_window()` 新增参数，枚举值 `None`（默认，退化为原有行为）/ `'daylight'` / `'solar_period'` / `'multiscale'`。
- **irr_threshold（辐照阈值）**：用于识别日出/日落时刻的功率阈值，以当天设备最大功率的百分比表示，默认值 `0.05`（5%）。
- **Daylight_Period（日照时段）**：功率 ≥ `irr_threshold × 当天最大功率` 的连续时间段，对应日出至日落。
- **Peak_Period（峰值段，A 段）**：在 `solar_period` 模式下，功率 > 当天最大功率 × 30% 的时段。
- **Transition_Period（过渡段，S 段）**：在 `solar_period` 模式下，功率介于 5%～30% 之间的时段（即 `irr_threshold × 最大功率` 到 `0.30 × 最大功率`）。
- **Night_Period（夜间段，B 段）**：功率 < `irr_threshold × 当天最大功率`，不产生样本的时段。
- **sub_window（子窗口）**：`multiscale` 模式下在日照时段内进行滑动切分的子窗口时长，pandas 频率字符串，默认 `'4h'`。
- **Pseudo_Label（伪标签）**：由分类器预测产生、未经人工裁决、置信度超过阈值后写入回流数据集的预测标签，以 `is_pseudo: true` 字段区别于 Human_Verdict。
- **pseudo_label_threshold（伪标签置信度阈值）**：触发伪标签回流的最低置信度，默认 `0.92`。
- **pseudo_label_max_ratio（伪标签最大占比）**：单次回流中伪标签数量占当次回流总量的上限比例，默认 `0.5`。
- **Uncertainty_Sampling（不确定性优先采样）**：按 `confidence` 升序排列待审核单元，使低置信度单元优先呈现给审核人。
- **Diversity_Sampling（多样性采样）**：对低置信度样本做 K-means 聚类，从每个 cluster 抽取代表性样本，避免相似低置信度样本重复标注。
- **ClusterDiscovery_Session（聚类发现会话）**：与普通 Review_Session 并列的独立任务，在预测完成后对低置信度特征向量做聚类，发现可能构成新类别的候选 cluster。
- **New_Class_Candidate（新类候选 cluster）**：与已知故障类别中心距离超过配置阈值的 cluster，被提交给审核人批量确认是否构成新标签类别。
- **sampling_strategy（采样策略）**：Review_Session 创建时可指定的排序与采样方式，枚举值 `'random'`（默认，保持当前行为）/ `'uncertainty'` / `'diversity'`。
- **Committee_Disagreement（委员会分歧）**：同一 Diagnosis_Unit 的 `predicted_label`（分类器预测）与 `suggested_label`（LLM 建议）不一致的状态，已有字段 `disagreement=true` 标记。
- **n_clusters（聚类数）**：多样性采样或新类候选发现时 K-means 的目标聚类数，默认 `5`。

---

## 需求

---

### 需求 13：`daylight` 日照时段切分模式

**用户故事：** 作为算法工程师，我想在诊断窗口切分时自动识别日出/日落时刻并仅保留日照时段数据，以便排除夜间零功率数据对特征提取的干扰，提升每个训练样本的信号质量。

#### 验收标准

1. WHEN `set_time_window()` 被调用且 `solar_mode='daylight'` 时，THE SolarWindow_Segmentation SHALL 以 `irr_threshold`（辐照阈值，默认 `0.05`）乘以当天设备最大功率作为识别日出/日落时刻的功率阈值，将连续超过该阈值的时段标记为 Daylight_Period（日照时段）

2. WHEN `solar_mode='daylight'` 时，THE SolarWindow_Segmentation SHALL 仅保留 Daylight_Period 内的数据行参与后续特征提取，夜间段（Night_Period，功率低于阈值的时段）的数据行不产生 `time_window` 标记、不作为训练样本输出

3. WHEN 某设备某天的最大功率为零（全天无日照）时，THE SolarWindow_Segmentation SHALL 将该设备当天的所有数据行均视为夜间段并排除，不产生任何样本，同时产生告警（如 `daylight_no_sample_{device_id}_{date}`）

4. THE SolarWindow_Segmentation SHALL 将 `irr_threshold` 设计为可配置参数，调用方可通过参数覆盖默认值 `0.05`，支持范围为 `(0, 1)` 的浮点数；IF 传入值超出此范围，THEN THE SolarWindow_Segmentation SHALL 拒绝执行并返回参数校验错误

5. WHEN `solar_mode=None`（默认）时，THE SolarWindow_Segmentation SHALL 与现有 `set_time_window()` 行为完全一致，现有调用方无需修改

6. THE SolarWindow_Segmentation SHALL 保证 `daylight` 模式的输出数据帧包含与原有 `daily` 模式相同的 `time_window` 列，使 `FeatureEngineer.transform()` 无需任何修改即可消费切分结果

7. WHEN `diagnosis_window='daylight'` 被传入 `FaultDiagnosis.__init__()` 时，THE FaultDiagnosis SHALL 将 `solar_mode='daylight'` 传递给 `set_time_window()` 调用，并以日照时段作为唯一的 `time_window` 粒度


---

### 需求 14：`solar_period` 三段（A/S/B）特征切分模式

**用户故事：** 作为算法工程师，我想将日照时段进一步细分为峰值段（A 段）和过渡段（S 段）并分段提取特征后拼接，以便让一个训练样本同时包含不同辐照强度下的故障特征，提升对清晨逆变器启停、正午遮挡等特定时段故障的区分能力。

#### 验收标准

1. WHEN `solar_mode='solar_period'` 时，THE SolarWindow_Segmentation SHALL 将日照时段内的数据按功率阈值切分为两个子段：Peak_Period（A 段，功率 > 当天最大功率 × `peak_ratio`，默认 `0.30`）和 Transition_Period（S 段，功率介于 `irr_threshold × 最大功率` 与 `peak_ratio × 最大功率` 之间）

2. WHEN `solar_mode='solar_period'` 时，THE SolarWindow_Segmentation SHALL 将 Night_Period（B 段，功率 < `irr_threshold × 最大功率`）的数据行排除，不产生样本

3. WHEN `solar_mode='solar_period'` 时，THE SolarWindow_Segmentation SHALL 以「设备 × 天」为单位，对 A 段和 S 段分别调用 `FeatureEngineer.transform()` 提取特征向量，再将两段特征向量横向拼接（`pd.concat(axis=1)`）形成一个完整的训练样本特征向量

4. WHEN 某设备某天 A 段或 S 段的数据行数为零时，THE SolarWindow_Segmentation SHALL 对该缺失子段以零向量填充对应特征列，并产生告警（如 `solar_period_empty_A_{device_id}_{date}` 或 `solar_period_empty_S_{device_id}_{date}`），不因空段中断整条样本的生成

5. THE SolarWindow_Segmentation SHALL 将 `peak_ratio`（峰值段功率比阈值）设计为可配置参数，默认 `0.30`；IF `peak_ratio ≤ irr_threshold`，THEN THE SolarWindow_Segmentation SHALL 拒绝执行并返回参数校验错误（两阈值须保持 A 段 > S 段的层次关系）

6. WHEN `diagnosis_window='solar_period'` 被传入 `FaultDiagnosis.__init__()` 时，THE FaultDiagnosis SHALL 将 `solar_mode='solar_period'` 传递给切分与特征提取流程，输出样本数与 `daily` 模式下相同（每个设备 × 天产生一个样本）

7. THE SolarWindow_Segmentation SHALL 保证 `solar_period` 模式下的拼接特征向量的列名在 A 段列名上加前缀 `peak_`、在 S 段列名上加前缀 `trans_`，以区分来源子段并避免列名冲突


---

### 需求 15：`multiscale` 多尺度并行切分模式

**用户故事：** 作为算法工程师，我想在保留整天粒度样本的同时，对日照时段额外做子窗口滑动切分以产生更多训练样本，以便在标注数据稀少的早期迭代轮次中增大样本密度，提升模型收敛速度。

#### 验收标准

1. WHEN `solar_mode='multiscale'` 时，THE SolarWindow_Segmentation SHALL 为每个设备每天同时产生两类样本：一类是整天粒度的原始样本（与 `daily` 模式相同），另一类是对日照时段按 `sub_window`（子窗口时长，默认 `'4h'`）滑动切分后产生的多个子窗口样本

2. WHEN `solar_mode='multiscale'` 且 `window_one_label=1` 时，THE SolarWindow_Segmentation SHALL 将父天的 `label` 字段继承给同一天产生的所有子窗口样本，子窗口样本的 `time_window` 标记为子窗口起始时刻

3. WHEN 日照时段长度不足一个完整 `sub_window` 时，THE SolarWindow_Segmentation SHALL 保留该不足长度的尾部子窗口并产生样本；IF 日照时段长度为零（全天无日照），THEN THE SolarWindow_Segmentation SHALL 只产生整天粒度样本而不产生子窗口样本，并产生告警（如 `multiscale_no_daylight_{device_id}_{date}`）

4. WHEN `solar_mode='multiscale'` 时，THE FaultDiagnosis SHALL 在 `FeatureEngineer.init_data()` 中将 `is_quantile` 的判断阈值调整为 `avg_count < sub_window_points`（`sub_window_points` 为 `sub_window` 对应的数据点数，由采样频率决定），以替代原有硬编码阈值 `48`，避免子窗口样本因点数不足而被错误关闭分位数特征

5. THE SolarWindow_Segmentation SHALL 将 `sub_window` 设计为可配置参数，支持与 `diagnosis_window` 相同的 pandas 频率字符串语法（如 `'4h'`、`'2h'`、`'6h'`）；IF `sub_window` 大于等于整天时长，THEN THE SolarWindow_Segmentation SHALL 拒绝执行并返回参数校验错误

6. WHEN `diagnosis_window='multiscale'` 被传入 `FaultDiagnosis.__init__()` 时，THE FaultDiagnosis SHALL 接受附加参数 `sub_window`（默认 `'4h'`）并传递给 SolarWindow_Segmentation

7. THE SolarWindow_Segmentation SHALL 保证子窗口样本的标识字段（`site_id`、`device_id`、`branch_id`、`time_window`）唯一，不与整天粒度样本或其他子窗口样本产生主键冲突


---

### 需求 16：不确定性优先采样与多样性采样

**用户故事：** 作为审核人员，我想在发起审核会话时选择按预测置信度由低到高排列待审核单元（不确定性优先），或从低置信度样本中按特征空间聚类抽取代表性样本（多样性采样），以便把有限的审核精力集中在模型最不确定的区域，更高效地提升标注质量。

#### 验收标准

1. WHEN 用户创建 Review_Session 时，THE Review_Window SHALL 支持 `sampling_strategy`（采样策略）参数，枚举值为 `'random'`（默认，保持当前行为）/ `'uncertainty'`（不确定性优先）/ `'diversity'`（多样性采样）

2. WHEN `sampling_strategy='uncertainty'` 时，THE Review_Window SHALL 在加载待审核单元时按 `confidence`（置信度）升序排列，使置信度最低的单元优先展示给审核人；若多个单元置信度相同，则按 `unit_key`（诊断单元标识）字典序排列作为稳定次序

3. WHEN `sampling_strategy='diversity'` 时，THE Review_Window SHALL 从当前 Review_Session 的所有低置信度单元（置信度 < `diversity_conf_threshold`，默认 `0.5`）的特征向量中执行 K-means 聚类（`n_clusters`，默认 `5`），再从每个 cluster 中选取距离质心最近的 1 个单元作为该 cluster 的代表性样本，将代表性样本排列在审核队列前部，其余非代表性样本排列在后部

4. WHEN `sampling_strategy='diversity'` 且低置信度单元数量不足 `n_clusters` 时，THE Review_Window SHALL 将所有低置信度单元均视为代表性样本，不执行聚类，并产生信息提示（如 `diversity_cluster_skipped_too_few_samples`）

5. THE Review_Window SHALL 将 `sampling_strategy`、`n_clusters`（聚类数，默认 `5`）、`diversity_conf_threshold`（多样性采样低置信度阈值，默认 `0.5`）设计为 Review_Session 创建时的可选参数；IF 传入非法枚举值，THEN THE Review_Window SHALL 拒绝创建会话并返回参数校验错误

6. THE Review_Window SHALL 在审核界面展示当前 Review_Session 所使用的 `sampling_strategy`，以便审核人知晓当前排列逻辑

7. THE Storage_Abstraction SHALL 为 Review_Session 记录元数据字段 `sampling_strategy`（所用采样策略）、`n_clusters`（若为 diversity 模式）、`diversity_conf_threshold`（若为 diversity 模式），供迭代追踪与可追溯历史使用


---

### 需求 17：基于聚类的新类候选发现

**用户故事：** 作为审核人员，我想在预测完成后触发一个专门的「新类候选发现」任务，让系统自动从低置信度预测池中聚类出与已知故障类别明显不同的样本群，并将每个候选群的代表性样本批量呈现给我确认，以便系统性地发现未登记的新故障类别，而非依赖偶然的人工发现。

#### 验收标准

1. WHEN 一次预测工作流完成后，THE Loop_Orchestrator SHALL 支持触发一个独立的 ClusterDiscovery_Session（聚类发现会话），该会话与普通 Review_Session 并列存在，不占用 Review_Session 的审核队列

2. WHEN ClusterDiscovery_Session 被触发时，THE Loop_Orchestrator SHALL 从本次预测结果中筛选 `confidence`（置信度）< `discovery_conf_threshold`（新类发现置信度阈值，默认 `0.5`）的所有 Diagnosis_Unit，对其特征向量执行 HDBSCAN 或 K-means 聚类（算法可配置，默认 HDBSCAN），产生若干 cluster

3. WHEN 聚类完成后，THE Loop_Orchestrator SHALL 计算每个 cluster 质心与所有已知故障类别（Label_Registry 中当前版本已登记类别）样本均值向量的最小欧氏距离，将最小距离超过 `new_class_dist_threshold`（新类距离阈值，默认值由特征维度归一化后的合理范围决定，应在配置文件中给出推荐值）的 cluster 标记为 New_Class_Candidate（新类候选 cluster）

4. THE Loop_Orchestrator SHALL 从每个 New_Class_Candidate cluster 中选取离质心最近的 3～5 个样本作为代表性样本（代表样本数可配置，范围 `[1, 10]`），批量组织为一个待确认列表呈现给审核人

5. WHEN 审核人对一个 New_Class_Candidate cluster 整体确认为新类别时，THE Review_Window SHALL 触发 `Label_Registry.allocate_label()` 批量为该 cluster 的代表性样本写入新 `label_id` 作为 Human_Verdict，并将该操作记录到 Iteration_Tracker

6. WHEN 审核人对一个 New_Class_Candidate cluster 选择「拒绝（非新类）」时，THE Review_Window SHALL 将该 cluster 标记为 `rejected`，不写入任何 Human_Verdict，并允许审核人附加拒绝原因备注

7. IF ClusterDiscovery_Session 执行时特征向量维度不一致（不同轮次模型的特征列表不同），THEN THE Loop_Orchestrator SHALL 拒绝执行聚类并返回说明（如 `discovery_feature_mismatch`），提示需先统一特征空间

8. THE Storage_Abstraction SHALL 为每个 ClusterDiscovery_Session 记录：`session_id`（会话 ID）、`iteration_round`（所属迭代轮次）、`discovery_conf_threshold`（置信度阈值）、`cluster_count`（总 cluster 数）、`new_class_candidate_count`（新类候选 cluster 数）、`confirmed_count`（已确认新类数）、`rejected_count`（已拒绝数）、`created_at`（创建时间）


---

### 需求 18：高置信度伪标签回流

**用户故事：** 作为平台用户，我想在正式人工审核前可选地触发一次伪标签回流预处理，让置信度足够高的预测结果直接作为弱监督真值写入训练集，以便在人力审核资源有限时加速标注数据积累，同时通过明确的标记字段和占比上限防止伪标签污染。

#### 验收标准

1. THE Loop_Orchestrator SHALL 支持在正式 Review_Session 创建之前触发一次可选的 Pseudo_Label_Backfill（伪标签回流）步骤，该步骤默认不触发（`enable_pseudo_backfill: false`），需由用户显式启用

2. WHEN Pseudo_Label_Backfill 被触发时，THE Loop_Orchestrator SHALL 从当次预测结果中筛选 `confidence ≥ pseudo_label_threshold`（伪标签置信度阈值，默认 `0.92`）的所有 Diagnosis_Unit，将其 `predicted_label` 作为伪真值写入回流数据集

3. THE Loop_Orchestrator SHALL 为每条伪标签回流记录附加字段 `is_pseudo: true`，以明确区分伪标签与 Human_Verdict（人工裁决）；人工裁决记录的对应字段为 `is_pseudo: false`

4. THE Loop_Orchestrator SHALL 检查本次伪标签数量是否超过 `pseudo_label_max_ratio × 本次回流总量`（伪标签最大占比，默认 `0.5`）；IF 超过上限，THEN THE Loop_Orchestrator SHALL 按 `confidence` 降序截断，仅保留最高置信度的 `floor(pseudo_label_max_ratio × 本次回流总量)` 条伪标签，并产生告警（如 `pseudo_backfill_truncated_by_max_ratio`）

5. THE Accuracy_Evaluator SHALL 在计算 `human_verified_accuracy`（人工核对后精度）时排除所有 `is_pseudo: true` 的记录，不将伪标签计入人工精度统计；伪标签可在单独的 `pseudo_label_accuracy`（伪标签精度，以后续轮次人工裁决结果为真值回算）中单独追踪

6. THE Storage_Abstraction SHALL 为 Pseudo_Label_Backfill 步骤记录：`backfill_id`（回流 ID）、`iteration_round`（迭代轮次）、`pseudo_label_threshold`（置信度阈值）、`pseudo_label_max_ratio`（最大占比）、`total_candidates`（满足阈值的候选数）、`final_pseudo_count`（实际写入伪标签数）、`truncated`（是否被截断）、`created_at`（创建时间）

7. WHEN 用户基于包含伪标签的回流数据集发起下一轮训练时，THE Loop_Orchestrator SHALL 在训练配置中注明数据集包含伪标签（`contains_pseudo_labels: true`）及伪标签数量，供下一轮迭代记录参考

8. THE Loop_Orchestrator SHALL 允许用户在任意时刻将伪标签状态升级为 Human_Verdict（通过正式审核确认），升级后对应记录的 `is_pseudo` 字段更新为 `false`，并补充 `reviewer`（审核人）、`reviewed_at`（审核时间）


---

### 需求 19：分歧采样与 LLM 辅助打标增强

**用户故事：** 作为审核人员，我想在审核队列中专门处理分类器与 LLM 意见分歧的单元，并通过「按分歧排列」的排序选项快速定位这些高价值样本，以便在有限时间内优先解决模型与 LLM 都不确定的边界案例，提升审核的质量密度。

#### 验收标准

1. WHEN Review_Session 中存在 `disagreement=true`（分类器预测与 LLM 建议不一致，与需求 4.2 定义的「双来源分歧」单元对应）的 Diagnosis_Unit 时，THE Review_Window SHALL 在审核界面提供「按分歧排列」排序选项，选中后将所有 `disagreement=true` 的单元置于审核队列前部，`disagreement=false` 的单元排列在后部

2. WHILE 「按分歧排列」模式激活时，THE Review_Window SHALL 在分歧单元组内按 `confidence`（置信度）升序二次排序（置信度越低、分歧越大，越优先），非分歧单元组内保持原有排序策略不变

3. WHEN `sampling_strategy='uncertainty'` 与「按分歧排列」同时激活时，THE Review_Window SHALL 优先应用「按分歧排列」的分组逻辑，在各分组内再按不确定性排序；两种排序选项不互斥，但分歧分组优先级高于不确定性排序

4. THE Review_Window SHALL 在审核界面的每个分歧单元（`disagreement=true`）旁显著标注「分类器 vs LLM 分歧」标签，并明确展示 `predicted_label`（分类器预测标签）与 `suggested_label`（LLM 建议标签）的对比，与需求 4.1 的双来源并列展示保持一致

5. THE Review_Window SHALL 在 Review_Session 统计摘要中展示 `disagreement_count`（分歧单元总数）、`disagreement_resolved_count`（已裁决的分歧单元数）、`disagreement_ratio`（分歧占比 = `disagreement_count / total_count`），供审核人评估本轮分类器与 LLM 的一致性

6. WHEN 审核人完成一个分歧单元的裁决（Human_Verdict），THE Accuracy_Evaluator SHALL 分别统计「分歧单元中分类器正确率」与「分歧单元中 LLM 正确率」，作为下一步优化分类器或 LLM Prompt 的参考指标，并在三方精度展示（需求 6）中以分歧子集形式单独展示

7. THE Storage_Abstraction SHALL 为每条 Human_Verdict 记录补充字段 `was_disagreement`（布尔，是否来自分歧单元），以便按「是否为分歧单元」维度做精度分析与追踪


---

## 与现有系统的衔接说明

### 1. 向后兼容约定

| 扩展点 | 向后兼容策略 |
|--------|-------------|
| `set_time_window(data, id_cols, time_col, freq)` | 新增 `solar_mode=None` 参数，默认值 `None` 时行为与现有调用完全一致，不破坏任何已有调用方 |
| `FaultDiagnosis.__init__()` 的 `diagnosis_window` 参数 | 原有 pandas 频率字符串（`'1d'`、`'4h'`、`'1h'` 等）继续有效；新增枚举值 `'daylight'`、`'solar_period'`、`'multiscale'` 作为扩展路径，旧参数值行为不变 |
| `FeatureEngineer.transform()` | 无需任何修改，三种新切分模式均在特征工程上游完成切分，输出符合现有接口规范的数据帧 |
| `FeatureEngineer.init_data()` 的 `is_quantile` 判断 | 仅在 `multiscale` 模式下需调整判断阈值，其他模式保持原有 `avg_count < 48` 逻辑不变 |
| Review_Session 创建接口 | 新增 `sampling_strategy`、`n_clusters`、`diversity_conf_threshold` 为可选参数，不传则默认 `'random'`，与现有行为等价 |
| Human_Verdict 存储结构 | 新增 `was_disagreement` 字段，对现有记录默认回填 `false`，不破坏历史数据格式 |
| 回流数据集格式 | 新增 `is_pseudo`（伪标签标记）字段，对现有 Human_Verdict 回流记录默认为 `false`，不破坏现有回流逻辑 |
| Loop_Orchestrator 阶段状态机（需求 12）| Pseudo_Label_Backfill 作为可选预处理步骤插入 `predicted → reviewing` 之间，不改变主状态机的枚举值；ClusterDiscovery_Session 并列于 Review_Session，不占用主状态机路径 |

### 2. 影响范围分析

**直接需要修改的文件（最小改动原则）：**

- `fault-diag-algo-release-3.1/enos_fault_diag/utils/time.py`
  — `set_time_window()` 函数：新增 `solar_mode` 参数及三个模式的切分逻辑分支。建议以 `solar_mode=None` 作为入参默认值，不修改函数签名已有位置参数。

- `fault-diag-algo-release-3.1/enos_fault_diag/fault_diagnosis.py`
  — `FaultDiagnosis.__init__()`：`diagnosis_window` 参数的文档注释需更新，新增对新枚举值的解析与 `solar_mode` 转发逻辑。
  — `FaultDiagnosis.train()` 和 `FaultDiagnosis.predict()`：在调用 `set_time_window()` 时透传 `solar_mode`。

- `fault-diag-algo-release-3.1/enos_fault_diag/features/feature_engineer.py`
  — `FeatureEngineer.init_data()`：`multiscale` 模式下的 `is_quantile` 阈值调整（接受外部传入的 `sub_window_points` 参数替代硬编码 `48`）。建议增加 `quantile_min_points` 可选参数，不修改现有分支逻辑。

**需要新增的文件/模块：**

- `SolarWindow_Segmentation` 核心切分逻辑建议封装在 `utils/solar_window.py`（新增），由 `time.py` 的 `set_time_window()` 调用，保持关注点分离。
- ClusterDiscovery_Session、Uncertainty_Sampling、Diversity_Sampling 的后端实现建议在 `backend-service/api/iterative_labeling.py` 中扩展，不新增独立路由文件。
- 伪标签回流 `Pseudo_Label_Backfill` 逻辑建议作为 `Loop_Orchestrator` 内的新方法实现，复用现有 `Storage_Abstraction` 接口。

**无需修改的文件：**

- `features/` 目录下的所有特征提取子模块（`correlation.py`、`fluctuation.py`、`statistics.py` 等）
- `models/rnd_fst.py`（随机森林模型）
- `data_cleaning/data_cleaner.py`（数据清洗）
- 现有 `api/upload.py`、`api/llm_config.py`、`api/workflows_enhanced.py` 核心主链路

### 3. 迭代顺序建议

建议按以下顺序实现，每项均可独立交付、独立测试：

1. **需求 13**（`daylight` 模式）：改动最小，优先实现，可作为需求 14、15 的基础。
2. **需求 14**（`solar_period` 模式）：依赖需求 13 的 Daylight_Period 识别逻辑，建议复用。
3. **需求 15**（`multiscale` 模式）：依赖需求 13，需额外处理 `is_quantile` 阈值调整。
4. **需求 16**（采样策略）：独立于切分需求，可与需求 13～15 并行实施。
5. **需求 19**（分歧采样）：依赖需求 4（双来源分歧），逻辑在需求 16 基础上扩展。
6. **需求 18**（伪标签回流）：独立实施，建议在需求 16、19 稳定后再引入，避免早期伪标签污染标注质量评估。
7. **需求 17**（新类候选发现）：依赖特征向量的可访问性与 Label_Registry 接口，建议最后实施，引入 HDBSCAN 依赖前确认部署环境。

---

## 优化方向三：审核期增量训练（`Incremental_Training_During_Review`）

> **本章节新增需求 20～22，描述在审核会话（Review_Session）进行期间周期性触发轻量重训，使模型随标注积累实时更新，提升审核后期的预测质量与效率。**

### 扩展术语（本章节新增）

- **Incremental_Trigger（增量训练触发器）**：在 Review_Session 进行中，当已审核条数达到 `incremental_batch_size` 的整数倍时，自动触发一次轻量重训的机制。
- **incremental_batch_size（增量批次大小）**：触发一次增量训练所需的新增审核条数，默认 `20`（即每审完 20 条触发一次）。
- **Mini_Backfill（迷你回流）**：在 Review_Session 完成前触发的中间回流动作，把当前批次（最近 `incremental_batch_size` 条 `confirm/correct/new_label` 裁决）加入训练集并触发重训，与 Review_Session 结束后的正式 `Backfill` 独立，不改变阶段状态机。
- **incremental_retrain_mode（增量重训模式）**：枚举值 `'disabled'`（关闭，默认保持当前行为）/ `'on_batch'`（每审完 N 条触发）/ `'on_new_label'`（新标签类别出现时立即触发）/ `'on_error_spike'`（最近一批错误率超阈值时触发）。
- **confidence_refresh（置信度刷新）**：增量重训完成后，用新模型对 Review_Session 中尚未审核的 Diagnosis_Unit 重新预测并更新 `confidence` 和 `predicted_label`，使后续审核看到更准确的预测。
- **error_spike_threshold（错误率突增阈值）**：触发 `on_error_spike` 模式增量训练的错误率阈值；在最近一个批次中分类器预测与 Human_Verdict 的不一致率超过此值时触发，默认 `0.4`（40%）。

---

### 需求 20：审核期增量训练触发机制

**用户故事：** 作为平台用户，我想在审核会话进行中，每当新增一批审核结果达到设定条数时自动触发轻量重训并刷新剩余样本的预测置信度，以便审核后期的待审单元预测越来越准，减少需要人工纠正的比例。

#### 验收标准

1. WHEN 创建 Review_Session 时，THE Review_Window SHALL 支持 `incremental_retrain_mode`（增量重训模式）参数，枚举值 `'disabled'`（默认）/ `'on_batch'` / `'on_new_label'` / `'on_error_spike'`；IF 未指定，THEN THE Review_Window SHALL 默认使用 `'disabled'`，与现有行为完全一致

2. WHEN `incremental_retrain_mode='on_batch'` 时，THE Incremental_Trigger SHALL 在每次新增已审核条数达到 `incremental_batch_size`（默认 `20`）的整数倍时，自动触发一次 Mini_Backfill 并发起重训；`incremental_batch_size` 为 Review_Session 创建时的可选参数，支持范围 `[5, 200]` 的整数

3. WHEN `incremental_retrain_mode='on_new_label'` 时，THE Incremental_Trigger SHALL 在任意一条 Human_Verdict 的 `action_type='new_label'`（新标签类别写入 Label_Registry）时立即触发 Mini_Backfill 并发起重训，不等待 `incremental_batch_size` 累积

4. WHEN `incremental_retrain_mode='on_error_spike'` 时，THE Incremental_Trigger SHALL 在每个 `incremental_batch_size` 批次完成后计算该批次分类器错误率（`predicted_label ≠ verdict_label` 的比例）；IF 错误率超过 `error_spike_threshold`（默认 `0.4`），THEN THE Incremental_Trigger SHALL 立即触发 Mini_Backfill 并发起重训

5. THE Incremental_Trigger SHALL 保证同一时刻最多只有一个 Mini_Backfill + 重训任务在运行；IF 上一次增量重训尚未完成，THEN THE Incremental_Trigger SHALL 跳过本次触发并记录日志（如 `incremental_retrain_skipped_busy`），不排队积压

6. THE Loop_Orchestrator SHALL 保证增量重训使用的训练数据 = 原始 Labeled_Dataset（本轮闭环训练所用）+ 当前 Review_Session 中所有已完成 Mini_Backfill 批次的 Human_Verdict；每次增量重训均为全量重训（选项 A），不改变训练算法

7. THE Storage_Abstraction SHALL 为每次 Mini_Backfill 记录：`mini_backfill_id`（迷你回流 ID）、`review_session_id`（所属审核会话）、`batch_index`（第几批，从 1 起）、`verdicts_included`（本批纳入的裁决条数）、`trigger_reason`（触发原因：`batch_size` / `new_label` / `error_spike`）、`retrain_started_at`（重训开始时间）、`retrain_completed_at`（重训完成时间）

---

### 需求 21：置信度实时刷新与审核队列自适应

**用户故事：** 作为审核人员，我想在每次增量重训完成后看到剩余待审核样本的预测标签和置信度自动更新，以便用更准确的预测指导后续审核，并让采样策略（不确定性/分歧采样）基于最新置信度重新排序。

#### 验收标准

1. WHEN 一次 Mini_Backfill 触发的重训完成后，THE Review_Window SHALL 对当前 Review_Session 中所有尚未审核的 Diagnosis_Unit（`current_verdict` 为空的单元）执行一次 confidence_refresh（置信度刷新），用新模型重新预测并更新 `confidence` 和 `predicted_label`

2. WHEN confidence_refresh 完成后，IF Review_Session 的 `sampling_strategy` 为 `'uncertainty'` 或 `'diversity'`，THEN THE Review_Window SHALL 基于刷新后的 `confidence` 重新排序审核队列，使审核人下一条看到的是更新后最不确定的单元

3. THE Review_Window SHALL 在审核界面明确提示置信度刷新事件（如「模型已更新，预测置信度已刷新」），标注刷新时间与本次增量训练新增的样本数，使审核人知晓队列已更新

4. WHEN confidence_refresh 导致某个已排在队列前部的单元的 `confidence` 升高到超过某阈值（`auto_skip_threshold`，可选，默认不启用），THE Review_Window SHALL 可选地将该单元自动标记为预审通过并移出待审队列，减少人工审核量；此功能须显式启用（`enable_auto_skip: false` 为默认）

5. THE Review_Window SHALL 保证 confidence_refresh 为非阻塞操作：刷新期间审核人可继续提交已展示单元的裁决，不因刷新而暂停审核流程；刷新完成后界面自动更新，不影响已提交的裁决

6. THE Storage_Abstraction SHALL 为每次 confidence_refresh 记录：`refresh_id`（刷新 ID）、`review_session_id`（所属审核会话）、`mini_backfill_id`（触发此次刷新的迷你回流 ID）、`units_refreshed`（刷新的未审核单元数）、`avg_confidence_before`（刷新前平均置信度）、`avg_confidence_after`（刷新后平均置信度）、`completed_at`（完成时间）

---

### 需求 22：增量训练过程监控与效果追踪

**用户故事：** 作为平台用户，我想在审核会话界面看到增量训练的进展和效果趋势，验证「审核越多、置信度越高」的规律是否成立，以便评估增量训练是否真正起到作用。

#### 验收标准

1. THE Review_Window SHALL 在审核界面展示增量训练状态面板，实时显示：`retrain_count`（本会话已触发增量重训次数）、`latest_retrain_status`（最近一次重训状态：`running` / `completed` / `skipped`）、`avg_confidence_trend`（各次置信度刷新后未审核单元平均置信度的折线趋势），帮助审核人直观确认模型是否在改善

2. THE Review_Window SHALL 在增量训练状态面板中展示每次 Mini_Backfill 后的精度变化：以最近一个批次的 Human_Verdict 为真值，对比重训前后分类器在该批次上的错误率，展示 `batch_error_rate_before` 和 `batch_error_rate_after`

3. WHEN 一个 Review_Session 全部审核完成时，THE Iteration_Tracker SHALL 在该轮迭代历史记录中额外追加 `incremental_retrain_count`（本会话触发增量重训次数）、`final_avg_confidence`（会话结束时未审核单元平均置信度，若全部审完则为 null）、`incremental_mode`（本会话使用的增量模式），供跨轮趋势分析

4. IF 在审核会话中触发了增量重训，THEN THE Loop_Orchestrator SHALL 在会话结束后的正式 Backfill 中使用最终重训模型（而非闭环开始时的初始模型）作为本轮最终模型工件，并在 `Model_Artifact` 元数据中标注 `incremental_retrain_count`（本轮增量重训次数）

5. THE Iteration_Tracker SHALL 在跨轮趋势视图（需求 10.3）中额外展示 `avg_confidence_trend_by_round`（各轮审核会话中置信度刷新趋势的概要，如首次刷新置信度 vs 末次刷新置信度），供跨轮对比增量训练效果

---

## 与现有系统的衔接说明（更新）

### 增量训练方向的新增约束

| 约束点 | 说明 |
|--------|------|
| 训练算法不变 | 选项 A：增量重训仍为全量重训，只改变触发时机，`stratified_cv_eval` 算子零改动 |
| 阶段状态机不变 | Mini_Backfill 发生在 `reviewing` 阶段内部，不新增状态枚举值，`reviewed → backfilled` 路径不变 |
| `incremental_retrain_mode='disabled'` 为默认 | 不启用时行为与现有系统完全一致，存量会话不受影响 |
| confidence_refresh 为非阻塞 | 刷新期间审核可继续，不引入锁定或等待逻辑，保证审核流程不中断 |
| 增量重训并发保护 | 同一时刻最多一个重训任务，跳过而非排队，防止训练任务堆积 |
| 正式 Backfill 仍为权威回流 | Mini_Backfill 的中间回流仅用于触发重训，不替代 Review_Session 完成后的正式 Backfill；最终进入训练集的是正式 Backfill 的结果 |

### 建议实现顺序（完整更新）

1. 需求 13（`daylight` 切分）
2. 需求 14（`solar_period` 切分）
3. 需求 15（`multiscale` 切分）
4. 需求 16（采样策略）
5. 需求 19（分歧采样）
6. **需求 20（增量训练触发机制）** ← 先实现 `on_batch` 模式
7. **需求 21（置信度刷新）** ← 依赖需求 20
8. **需求 22（增量训练监控）** ← 依赖需求 20、21
9. **需求 23（SHAP 可解释性 + 相似案例检索）** ← 对模型零改动，可与上述并行
10. **需求 24（审核人一致性检测）** ← 字段已有，可独立实施
11. 需求 18（伪标签回流）
12. 需求 17（新类候选发现）

---

## 优化方向四：审核辅助增强（`Review_Assistance_Enhancement`）

> **本章节新增需求 23～24，聚焦提升审核人效率与标注质量：SHAP 可解释性帮助审核人理解预测依据，相似案例检索提供历史参照，审核人一致性检测发现标注偏差。**

### 扩展术语（本章节新增）

- **SHAP_Explanation（SHAP 解释）**：基于 SHAP（SHapley Additive exPlanations）方法为每个 Diagnosis_Unit 的预测结果生成的特征贡献分析，说明哪些特征对当次预测标签贡献最大，以及贡献方向（正向/负向）。
- **Feature_Contribution（特征贡献值）**：单条样本中某特征对预测结果的 SHAP 值，正值表示该特征推动预测向该类别靠近，负值表示反向。
- **Similar_Case（相似案例）**：从已有 Labeled_Dataset 中检索到的特征向量与当前待审核单元最相近的 K 条历史有标注样本，供审核人参照已知案例做裁决。
- **case_similarity_k（相似案例数）**：检索返回的相似历史样本数量，默认 `3`。
- **IAA（Inter-Annotator Agreement，标注者间一致性）**：衡量多名审核人对同一批样本标注结果一致程度的统计指标，本系统采用 Cohen's Kappa（两人）或 Fleiss' Kappa（多人）。
- **Overlap_Batch（重叠标注批次）**：一个 Review_Session 中专门抽取一部分 Diagnosis_Unit 分配给多名审核人标注，用于计算 IAA 的数据集。
- **overlap_ratio（重叠比例）**：Overlap_Batch 占当次 Review_Session 总单元数的比例，默认 `0.1`（10%）。
- **kappa_threshold（Kappa 阈值）**：触发低一致性告警的 Kappa 值下限，低于此值说明审核人之间分歧显著，默认 `0.6`。
- **Annotator_Bias（审核人偏差）**：某审核人的标注标签分布与全体审核人整体分布存在显著偏差的状态，通过标签分布差异检验发现。

---

### 需求 23：SHAP 可解释性与相似案例检索

**用户故事：** 作为审核人员，我想在审核每个诊断单元时同时看到「哪些特征最影响这次预测」的可视化解释，以及历史数据集中最相似的已知案例，以便在不懂模型细节的情况下快速判断预测是否合理，减少纠错时间。

#### 验收标准

1. WHEN 创建 Review_Session 时，THE Review_Window SHALL 支持 `enable_shap`（是否启用 SHAP 解释，默认 `false`）和 `enable_similar_cases`（是否启用相似案例检索，默认 `false`）两个可选参数；两者独立开关，互不依赖

2. WHEN `enable_shap=true` 且一个 Review_Session 被创建时，THE LLM_Labeling_Assistant 所在的后端 SHALL 为每个待审核 Diagnosis_Unit 预先计算 SHAP_Explanation，包含：`top_features`（贡献绝对值最大的前 `shap_top_k` 个特征，默认 `5`）、每个特征的 `feature_value`（该样本的特征值）、`shap_value`（SHAP 贡献值，正负均保留）

3. THE Review_Window SHALL 在每个待审核单元的审核卡片上，以条形图形式展示 SHAP_Explanation 的 `top_features`，正向贡献特征用一种颜色（如蓝色），负向贡献特征用另一种颜色（如红色），使审核人无需了解特征命名规则即可直观判断主要驱动因素

4. WHEN `enable_similar_cases=true` 时，THE Review_Window SHALL 为每个待审核单元从当前 Labeled_Dataset 中检索 `case_similarity_k`（默认 `3`）条特征向量最近邻样本（使用欧氏距离或余弦距离，算法可配置），展示每条相似案例的 `unit_key`（诊断单元标识）、`label_name`（已知标签名）、`similarity_score`（相似度得分，0~1）及其时序曲线摘要

5. THE Review_Window SHALL 明确标注 SHAP 解释和相似案例均为「参考信息」，不作为审核建议，不影响人工裁决的最终权威性（与需求 4.3 的「辅助建议」标注原则一致）

6. WHEN `enable_shap=true` 且模型类型不支持 SHAP 计算时（如未来换用不兼容算法），THE Review_Window SHALL 将该单元的 SHAP_Explanation 置为缺失并标注「模型不支持 SHAP 解释」，不中断审核流程

7. IF SHAP 计算或相似案例检索超时（超过 `review_assist_timeout_seconds`，默认 `10` 秒），THEN THE Review_Window SHALL 将对应信息置为缺失并继续展示审核卡片，不阻塞审核人提交裁决

8. THE Storage_Abstraction SHALL 为 SHAP 解释和相似案例检索结果缓存至 Review_Session 生命周期内，避免每次翻页重复计算；缓存在 Review_Session 结束后自动释放

---

### 需求 24：审核人一致性检测（IAA）

**用户故事：** 作为平台管理员，我想通过重叠标注机制检测多名审核人之间的标注一致性（Cohen's Kappa / Fleiss' Kappa），在一致性过低时收到告警，并识别存在标注偏差的审核人，以便维护标注质量并及时干预。

#### 验收标准

1. WHEN 创建 Review_Session 时，IF `reviewer_count`（参与本次审核的审核人数）≥ 2，THEN THE Review_Window SHALL 支持 `enable_iaa`（是否启用 IAA 检测，默认 `false`）和 `overlap_ratio`（重叠比例，默认 `0.1`）参数；启用后系统从待审核单元中随机抽取 `floor(total_count × overlap_ratio)` 条组成 Overlap_Batch

2. WHEN `enable_iaa=true` 时，THE Review_Window SHALL 将 Overlap_Batch 中的每个单元分配给本 Review_Session 的全部审核人（每人均需对这批单元做裁决），Overlap_Batch 之外的单元按正常分配规则分派

3. WHEN Overlap_Batch 中所有审核人均完成裁决后，THE Review_Window SHALL 自动计算标注者间一致性指标：两名审核人时用 Cohen's Kappa，三名及以上用 Fleiss' Kappa；结果记录在 Review_Session 的 `iaa_score`（IAA 得分）字段

4. IF 计算得到的 `iaa_score` 低于 `kappa_threshold`（默认 `0.6`），THEN THE Review_Window SHALL 在审核界面和平台通知中产生低一致性告警（如 `iaa_low_consistency_kappa_{score}`），提示管理员介入仲裁，并标注哪些 Overlap_Batch 单元存在分歧

5. THE Review_Window SHALL 为每个参与 Review_Session 的审核人计算 `label_distribution`（该审核人在本次 Session 的标签分布，即各类别占其裁决总数的比例），与全体审核人的整体标签分布做对比；IF 某审核人某一标签类别的占比偏差超过 `bias_threshold`（默认 `0.2`，即高出或低于整体 20 个百分点），THEN THE Review_Window SHALL 将该审核人标记为 Annotator_Bias（存在偏差），并在管理视图中高亮显示

6. THE Storage_Abstraction SHALL 为每个 Review_Session 记录 IAA 相关字段：`iaa_enabled`（是否启用）、`overlap_count`（Overlap_Batch 单元数）、`iaa_score`（Kappa 值，未启用时为 null）、`iaa_method`（`cohen` / `fleiss`）、`low_consistency_alert`（是否触发低一致性告警）、`biased_reviewers`（存在偏差的审核人列表）

7. THE Iteration_Tracker SHALL 在每轮迭代历史记录中追加 `iaa_score`（本轮审核的 Kappa 值）和 `biased_reviewer_count`（本轮存在偏差的审核人数），供跨轮标注质量趋势分析

8. WHERE 仅一名审核人参与审核时，THE Review_Window SHALL 跳过 IAA 计算，`iaa_score` 记为 null，不产生低一致性告警；单人审核为当前默认场景，本需求为多人协作场景的增量能力

<!-- @AI_GENERATED: end -->
