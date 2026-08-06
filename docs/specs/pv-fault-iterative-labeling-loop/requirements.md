<!-- @AI_GENERATED -->
> **⚠️ 已被取代（2026-07-30）**：见 [`docs/specs/pv-fault-label-segment-redesign/`](../pv-fault-label-segment-redesign/)。`solar_mode` / 旧 `time_window` 语义 / 逐点 label 列相关需求已作废。

# 需求文档：光伏故障人机协同迭代标注闭环

## 简介

本文档定义一个**建立在已有光伏故障诊断工作流之上**的人机协同闭环迭代标注与重训练系统。该系统不重新定义任何算子或流水线，而是作为**编排层（orchestration layer）**，把已交付的训练/预测工作流模板串成一个可迭代的闭环：

```
有真值数据集 → 切测试集训练 → 得到带精度的模型工件
        ↓
用该模型预测无真值数据集 → 得到预测标签 + 置信度
        ↓
人工审核窗口（分类器预测 + LLM 建议 双来源并列，人工最终裁决）
        ↓
固化真值标签（含新增标签类别）→ 回流为新训练集
        ↓
再切分训练出更优模型 → 进入下一轮（标签越来越多、精度越来越高）
```

**与已有 `pv-fault-diagnosis-integration` spec 的关系（依赖，不重复）：**

- 训练能力复用 `workflow-pv-fault-diag-training-v1`（光伏故障诊断训练模板，产出模型工件 + 评估指标）。
- **切分训练 + 测试集精度复用已实现的平台算子 `stratified_cv_eval`（分层重复留出评估算子）**，由训练评估工作流（如 `workflow-pv-fault-diag-quickval-cv-v1`，光伏故障诊断快速验证 / 重复分层交叉评估模板）调用。该算子在内部完成「无泄漏的重复分层留出切分 → mRMR 特征选择 → SMOTE 过采样 → 随机森林训练 → 测试折评分」，本 spec 直接复用其切分与评估算法，**不**重新定义。
- 预测能力复用 `workflow-pv-fault-diag-prediction-v1`（光伏故障诊断预测模板，消费明确的模型引用做批量预测）。
- 标签编解码复用已移植算子 `label_encode`（`encode`/`decode` 模式）。
- 本 spec **不**再定义上述算子的内部逻辑、特征工程、切分算法、模型参数；只定义闭环编排、人工审核窗口、标签扩充、迭代追踪、存储抽象。

**遵守的平台边界（来自 AGENTS.md）：**

| 边界 | 约束 |
|------|------|
| Train（训练） | 产出可复用模型工件 + 训练元数据；本系统在此基础上附加精度记录与数据集版本引用 |
| Predict（预测） | 消费明确的 `model_ref`（模型引用），禁止隐式重训 |
| Backtest（回测） | 历史窗口评分器；本系统的"精度"指测试集评估，不混淆为回测 |
| 编排 vs 评分 | 迭代闭环是编排层，训练/预测仍以 AIP 工作流方式执行 |

**前后端落点（来自 AGENTS.md）：**

- 后端：FastAPI + Python，conda 环境 `aip_web`；增强工作流接口集中在 `backend-service/api/workflows_enhanced.py`；数据集/上传接口在 `backend-service/api/upload.py`；LLM 配置复用 `backend-service/api/llm_config.py`。
- 前端：React 18 + TypeScript + Vite + Ant Design 5，目录 `frontend-sevice/`（拼写保持 `sevice`，不改名）。

**存储口径（重要约定）：**

审核结果、固化真值标签、迭代历史、标签注册表的持久化**当前阶段只定义抽象存取接口（storage abstraction）**，实现期先用轻量方式（文件 / JSON）落地，并预留后续接入数据库（DB）的接入点。**落库为后续阶段，当前仅定义抽象接口。**

## 术语表

- **Iteration_Loop（迭代闭环）**：训练 → 预测 → 人工审核 → 标签回流 → 重训练 的完整人机协同循环，每执行一遍称为一轮迭代（iteration round）。
- **Loop_Orchestrator（闭环编排器）**：负责按顺序触发训练工作流、预测工作流、审核会话、标签回流的编排层服务，本身不实现模型逻辑。
- **Labeled_Dataset（有真值数据集）**：包含真值标签列（如 `custom_label_id`）的数据集，可用于训练与测试集评估。
- **Unlabeled_Dataset（无真值数据集）**：不含真值标签列、只有时序测量列的数据集，作为预测对象。
- **Model_Artifact（模型工件）**：训练工作流产出的可复用模型，本系统为其附加精度记录与数据集版本引用。
- **Accuracy_Record（精度记录）**：模型经重复分层留出评估在测试折上得到的指标集合，**以 `macro_f1`（宏平均 F1）为主口径，并以「均值 ± 标准差 (mean ± std)」形式给出**（即 `macro_f1_mean` ± `macro_f1_std`，跨 `n_repeats` 次重复）；同时包含 `accuracy`（整体正确率，仅参考）、各类别 `recall`（召回率）、代表性 `confusion_matrix`（混淆矩阵，跨重复累计的测试折矩阵）、`per_repeat_macro_f1`（每次重复的宏 F1）与告警列表。
- **Repeated_Stratified_Holdout（重复分层留出）**：一种无泄漏评估方法，重复 `n_repeats`（重复次数，默认 `10`）次，每次以不同随机种子（`random_state + i`）独立做「逐类分层切分 → 仅训练折特征选择/过采样 → 训练 → 测试折评分」，最终以跨重复的均值 ± 标准差报告精度。
- **Stratified_CV_Eval（分层重复留出评估算子）**：平台已实现的算子 `stratified_cv_eval`，封装 Repeated_Stratified_Holdout 的完整切分与评估算法，由训练评估工作流（如 `workflow-pv-fault-diag-quickval-cv-v1`）调用；本闭环复用它作为「切分训练 + 测试集精度」的实现依赖，不重新定义其内部算法。
- **Diagnosis_Unit（诊断单元）**：一个「设备 × 诊断窗口」组合（`site_id` × `device_id` ×（可选 `branch_id`）× `time_window`），是预测与审核的最小粒度。
- **Review_Window（人工审核窗口）**：数据集模块新增的前端审核界面，对每个 Diagnosis_Unit 逐条审核预测准确率并打真值标签。
- **Review_Session（审核会话）**：针对某一轮预测结果发起的一次人工审核过程，包含若干待审核 Diagnosis_Unit。
- **Classifier_Prediction（分类器预测）**：预测工作流对一个 Diagnosis_Unit 输出的预测标签 + 置信度。
- **LLM_Suggestion（LLM 建议标签）**：LLM 辅助打标对一个 Diagnosis_Unit 给出的建议标签 + 理由，仅作建议。
- **Human_Verdict（人工裁决）**：审核人员对一个 Diagnosis_Unit 给出的最终真值标签，是真值的唯一来源。
- **Label_Registry（标签注册表）**：登记当前系统已认定的全部故障标签类别及其编码的注册表，支持新增类别（标签扩充）与版本管理。
- **Label_Map（标签映射）**：业务标签（如 `"suite-0"`）到数值类别（如 `20`）的字典，被 `label_encode` 算子的 `encode`/`decode` 模式消费。
- **Label_Expansion（标签扩充）**：审核中发现现有类别之外的新故障类型时，向 Label_Registry 新增标签类别的动作。
- **Iteration_Tracker（迭代追踪）**：记录每一轮迭代的数据集版本、模型版本、精度指标、标签空间快照，形成可追溯历史的服务。
- **Storage_Abstraction（存储抽象层）**：定义审核结果、真值标签、迭代历史、标签注册表的存取接口，当前用文件/JSON 实现，预留 DB 接入点。
- **LLM_Labeling_Assistant（LLM 辅助打标）**：调用平台已配置 LLM 为待审核单元生成 LLM_Suggestion 的服务，复用 `api/llm_config.py`。

## 需求

### 需求 1：训练集切分评估，产出带精度的模型工件

**用户故事：** 作为平台用户，我想用已实现的「重复分层留出」评估算子（`stratified_cv_eval`）对有真值标签的数据集做无泄漏的切分训练与测试折评分，得到以宏平均 F1（均值 ± 标准差）为主口径的精度记录与模型工件，以便用一个有据可查、精度不虚高的模型去预测无标签数据。

#### 验收标准

1. WHEN 用户在某一轮迭代选定一个 Labeled_Dataset 并发起训练评估, THE Loop_Orchestrator SHALL 通过既有训练评估工作流（如 `workflow-pv-fault-diag-quickval-cv-v1`）调用 Stratified_CV_Eval 算子（`stratified_cv_eval`）执行 Repeated_Stratified_Holdout（重复分层留出）评估，并复用该算子内部的切分、特征选择、过采样与训练算法，不在本系统内重新实现切分逻辑
2. THE Stratified_CV_Eval 算子 SHALL 重复执行 `n_repeats`（重复次数，默认 `10`）次评估，第 i 次（i 自 0 起）使用随机种子 `random_state + i`（`random_state` 为随机种子基值，默认 `90`，即 90~99），且每次独立完整执行「分层切分 → mRMR 特征选择 → SMOTE 过采样 → 随机森林训练 → 在测试折预测评分」
3. WHEN 执行每一次重复的分层切分, THE Stratified_CV_Eval 算子 SHALL 对每个类别单独打乱后，按 `test_ratio`（测试集占比，默认 `0.2`）取 `n_test = max(1, min(round(该类样本数 × test_ratio), 该类样本数 − 1))` 条样本进入测试折、其余进入训练折，以保证样本数 ≥2 的类别在训练折与测试折两侧各至少保留 1 条
4. THE Stratified_CV_Eval 算子 SHALL 保证每一次重复的测试折类别集合是训练折类别集合的子集（训练 / 测试类别对应），使测试折出现的每个类别在训练折中均有样本
5. WHEN 执行每一次重复, THE Stratified_CV_Eval 算子 SHALL 先完成分层切分，再仅在训练折上执行 mRMR 特征选择（fit）与 SMOTE 过采样；测试折仅使用训练折选出的 `feature_list`（训练折选出的特征列表，供测试折 transform 复用）做特征变换，绝不参与特征选择 fit、绝不被 SMOTE 过采样，以避免数据泄漏与精度虚高
6. IF 某类别在整个数据集中仅有 1 条样本而无法两侧覆盖, THEN THE Stratified_CV_Eval 算子 SHALL 将该类别样本归入训练折（标记为「仅训练 train-only」）并产生告警（如 `class_{label}_only_1_sample_train_only`）
7. IF 某类别在某次重复的训练折内样本数 <2 而无法用于 SMOTE 合成, THEN THE Stratified_CV_Eval 算子 SHALL 跳过该类别的 SMOTE 过采样并产生告警（如 `smote_skipped_class_{label}`）
8. WHEN 全部重复完成, THE Stratified_CV_Eval 算子 SHALL 以 `macro_f1`（宏平均 F1）为主口径，按「均值 ± 标准差 (mean ± std)」（即 `macro_f1_mean` ± `macro_f1_std`，跨 `n_repeats` 次重复）输出主精度，并同时输出 `accuracy`（整体正确率，仅参考）、各类别 `recall`（召回率）、代表性 `confusion_matrix`（混淆矩阵）、`per_repeat_macro_f1`（每次重复的宏 F1）与告警列表，共同组成 Accuracy_Record
9. THE Loop_Orchestrator SHALL 将训练产出登记为一个 Model_Artifact，其元数据至少包含：`model_ref`（模型引用，用于预测时显式指定）、`accuracy_record`（精度记录，以 macro_f1 均值 ± 标准差为主口径）、`dataset_version`（训练所用数据集版本引用）、`label_space_snapshot`（本次训练的标签空间快照）、`iteration_round`（所属迭代轮次）
10. IF 选定的 Labeled_Dataset 缺少真值标签列, THEN THE Loop_Orchestrator SHALL 拒绝发起训练评估并返回缺列说明
11. THE Loop_Orchestrator SHALL 复用既有训练评估工作流与 Stratified_CV_Eval 算子执行切分训练与精度评估，不在本系统内重新实现切分、特征选择、过采样、模型训练或精度计算逻辑

### 需求 2：用带精度模型预测无标签数据

**用户故事：** 作为平台用户，我想用上一步得到的模型工件去预测一个无真值标签的数据集，得到每个诊断单元的预测标签和置信度，以便交给人工审核。

#### 验收标准

1. WHEN 用户选定一个 Model_Artifact 和一个 Unlabeled_Dataset 并发起预测, THE Loop_Orchestrator SHALL 以该工件的 `model_ref`（模型引用）作为显式参数调用 `workflow-pv-fault-diag-prediction-v1` 预测工作流
2. THE Loop_Orchestrator SHALL 禁止在预测阶段触发任何隐式重训；IF 缺少有效 `model_ref`, THEN THE Loop_Orchestrator SHALL 拒绝预测并返回错误
3. WHEN 预测工作流完成, THE Loop_Orchestrator SHALL 为每个 Diagnosis_Unit 产出一条 Classifier_Prediction，包含 `predicted_label`（预测标签）、`confidence`（置信度，0~1）、`unit_key`（诊断单元标识：site_id × device_id ×（可选 branch_id）× time_window）
4. THE Loop_Orchestrator SHALL 将本次预测结果与所用 `model_ref`、`dataset_version`、`iteration_round` 关联保存，供审核与追踪使用
5. THE Loop_Orchestrator SHALL 复用已有预测工作流模板执行预测，不在本系统内重新实现预测逻辑

### 需求 3：人工审核窗口 — 逐诊断单元审核

**用户故事：** 作为审核人员，我想在数据集模块新增的审核窗口中按「设备 × 诊断窗口」逐条审核预测结果，以便核对预测是否准确并为新数据打真值标签。

#### 验收标准

1. WHEN 用户基于某次预测结果发起审核, THE Review_Window SHALL 创建一个 Review_Session，并以 Diagnosis_Unit 为最小粒度逐条加载待审核单元
2. THE Review_Window SHALL 为每个待审核单元展示其 `unit_key`（诊断单元标识）与可供判断的时序上下文（如该单元的电流/电压曲线或摘要）
3. THE Review_Window SHALL 显示当前 Review_Session 的审核进度（`reviewed_count`（已审核数）/ `total_count`（总数））
4. WHILE 一个 Review_Session 处于进行中状态, THE Storage_Abstraction SHALL 持久化每条已提交的审核结果，使会话中断后可恢复继续
5. THE Review_Window SHALL 复用已有数据集/上传接口（`api/upload.py`）获取被审核数据集的预览与样本，不另起独立数据通道

### 需求 4：双来源并列展示与不一致高亮

**用户故事：** 作为审核人员，我想同时看到分类器的预测标签和 LLM 的建议标签并排展示，并在两者不一致时被提醒，以便更快做出判断，同时由我做最终裁决。

#### 验收标准

1. THE Review_Window SHALL 为每个待审核单元并列展示两个来源：Classifier_Prediction（`predicted_label` + `confidence`）与 LLM_Suggestion（`suggested_label` + `reason`（建议理由））
2. IF 同一单元的 `predicted_label`（分类器预测标签）与 `suggested_label`（LLM 建议标签）不一致, THEN THE Review_Window SHALL 高亮提醒该单元为「双来源分歧」
3. THE Review_Window SHALL 明确标注两来源均为「辅助建议」，且只有 Human_Verdict（人工裁决）写入真值标签
4. WHERE LLM_Suggestion 因调用失败或未启用而缺失, THE Review_Window SHALL 正常展示分类器单来源并标注「LLM 建议不可用」，不阻断审核

### 需求 5：审核动作与真值固化

**用户故事：** 作为审核人员，我想对每个单元执行确认、纠正、打新标签或标记存疑跳过的操作，以便把审核结论固化为可回流的真值标签。

#### 验收标准

1. WHEN 审核人员对一个单元选择「确认正确」, THE Review_Window SHALL 以分类器 `predicted_label` 作为该单元的 Human_Verdict 并固化为真值标签
2. WHEN 审核人员对一个单元选择「纠正为其他已有标签」, THE Review_Window SHALL 要求从 Label_Registry 现有类别中选定一个标签作为 Human_Verdict
3. WHEN 审核人员对一个单元选择「打成新标签」, THE Review_Window SHALL 进入标签扩充入口（见需求 8），并以新增类别作为该单元的 Human_Verdict
4. WHEN 审核人员对一个单元选择「标记存疑跳过」, THE Review_Window SHALL 将该单元标记为 `pending`（存疑），不写入真值标签且不计入精度统计
5. THE Storage_Abstraction SHALL 为每条 Human_Verdict 记录 `unit_key`（诊断单元标识）、`verdict_label`（裁决标签）、`action_type`（动作类型：confirm/correct/new_label/skip）、`reviewer`（审核人）、`reviewed_at`（审核时间）
6. THE Review_Window SHALL 仅在状态为 `confirm`/`correct`/`new_label` 的单元上写入真值标签；`skip` 单元不产生真值标签

### 需求 6：三方精度实时对比

**用户故事：** 作为审核人员，我想在审核过程中实时看到「分类器原始预测精度 vs LLM 建议精度 vs 人工核对后精度」的对比，以便判断预测到底准不准、模型这一轮表现如何。

#### 验收标准

1. WHILE 审核进行中, THE Accuracy_Evaluator SHALL 以已固化的 Human_Verdict 为真值，实时计算并展示三项精度：`classifier_accuracy`（分类器原始预测精度）、`llm_accuracy`（LLM 建议精度）、`human_verified_accuracy`（人工核对后精度基线，恒为已审核单元的 100% 一致口径）
2. THE Accuracy_Evaluator SHALL 在计算三方精度时仅纳入状态为 `confirm`/`correct`/`new_label` 的单元，排除 `pending`（存疑跳过）单元
3. THE Accuracy_Evaluator SHALL 同时给出 macro 口径下的 `precision`/`recall`/`f1`，与训练阶段 Accuracy_Record 的口径一致，以便跨轮对比
4. WHEN 一条新的 Human_Verdict 被提交, THE Accuracy_Evaluator SHALL 增量更新三方精度而非重算全量
5. WHERE 某单元缺少 LLM_Suggestion, THE Accuracy_Evaluator SHALL 在计算 `llm_accuracy` 时将其从 LLM 分母中剔除，并标注 LLM 覆盖率

### 需求 7：LLM 辅助打标

**用户故事：** 作为审核人员，我想让 LLM 为每个待审核单元生成建议标签和理由，以便在人工裁决前获得参考，但 LLM 不能直接写入真值。

#### 验收标准

1. WHEN 一个 Review_Session 被创建, THE LLM_Labeling_Assistant SHALL 为每个待审核单元生成一条 LLM_Suggestion，包含 `suggested_label`（建议标签）与 `reason`（建议理由）
2. THE LLM_Labeling_Assistant SHALL 复用平台已有 LLM 配置（`api/llm_config.py` 的默认配置），不新增独立密钥管理
3. THE LLM_Labeling_Assistant SHALL 限定 `suggested_label` 取值来自当前 Label_Registry 的已有类别；IF LLM 给出注册表外的标签, THEN THE LLM_Labeling_Assistant SHALL 将其标注为 `out_of_registry`（疑似新类别）提示人工，而非直接采纳
4. THE LLM_Labeling_Assistant SHALL 禁止将 LLM_Suggestion 直接写入真值标签；真值标签只能来自 Human_Verdict
5. IF LLM 调用失败或超时, THEN THE LLM_Labeling_Assistant SHALL 记录失败原因并将该单元的 LLM_Suggestion 置为缺失，不中断审核流程
6. THE Storage_Abstraction SHALL 为每条 LLM_Suggestion 记录 `unit_key`、`suggested_label`、`reason`、`llm_config_ref`（所用 LLM 配置引用）、`generated_at`（生成时间）

### 需求 8：标签扩充与标签注册表版本管理

**用户故事：** 作为审核人员，我想在发现现有故障类别之外的新类别时新增一个标签类别，以便后续训练能纳入这个新类别，让标签随迭代越来越丰富。

#### 验收标准

1. WHEN 审核人员在审核中新增一个标签类别, THE Label_Registry SHALL 为该类别分配唯一且不与现有类别冲突的 `label_id`（标签编码）与 `label_name`（标签业务名称）
2. THE Label_Registry SHALL 为每次标签空间变更生成一个新的 `label_space_version`（标签空间版本号），并保留历史版本快照
3. THE Label_Registry SHALL 维护与 `label_encode` 算子兼容的 Label_Map（标签映射），保证新增类别后 `encode`/`decode` 双向映射对存量类别保持不变
4. IF 某个 Model_Artifact 的 `label_space_snapshot`（标签空间快照）与当前 Label_Registry 版本不一致, THEN THE Loop_Orchestrator SHALL 标注该模型为「标签空间落后」并提示新类别需经下一轮重训练才会被模型识别
5. THE Label_Registry SHALL 保证已固化真值标签所引用的 `label_id` 在后续版本中保持稳定（不重新编号），以免历史标注失真
6. THE Storage_Abstraction SHALL 以 Storage_Abstraction 接口持久化 Label_Registry 的当前版本与历史版本快照

### 需求 9：打标数据回流为新训练集

**用户故事：** 作为平台用户，我想把人工审核固化后的真值标签数据回流成为新的训练集，以便再次切分训练出更优的模型，形成闭环。

#### 验收标准

1. WHEN 一个 Review_Session 完成, THE Loop_Orchestrator SHALL 将状态为 `confirm`/`correct`/`new_label` 的单元及其 Human_Verdict 组装为一个新的 Labeled_Dataset 版本
2. THE Loop_Orchestrator SHALL 为回流数据集分配新的 `dataset_version`（数据集版本），并记录其来源（`source_iteration`（来源迭代轮次）、`base_dataset_version`（基线数据集版本））
3. THE Loop_Orchestrator SHALL 支持将回流真值与上一轮 Labeled_Dataset 合并形成累积训练集，使标签样本随迭代累积增多
4. THE Loop_Orchestrator SHALL 允许用户基于回流后的新数据集版本直接发起需求 1 的训练，进入下一轮迭代
5. THE Loop_Orchestrator SHALL 排除 `pending`（存疑跳过）单元，不将其纳入回流训练集

### 需求 10：迭代追踪与可追溯历史

**用户故事：** 作为平台用户，我想记录每一轮迭代的数据集版本、模型版本、精度指标和标签空间快照，以便追溯整个闭环并验证「标签越来越多、精度越来越好」。

#### 验收标准

1. WHEN 一轮迭代的训练、预测、审核、回流任一关键节点完成, THE Iteration_Tracker SHALL 追加一条迭代历史记录
2. THE Iteration_Tracker SHALL 为每条迭代记录保存：`iteration_round`（迭代轮次）、`dataset_version`（数据集版本）、`model_version`（模型版本 / model_ref）、`accuracy_record`（精度指标）、`label_space_version`（标签空间版本）、`label_count`（标签类别数）、`created_at`（创建时间）
3. THE Iteration_Tracker SHALL 提供按 `iteration_round` 排序的可追溯历史视图，展示精度指标与标签类别数随轮次的变化趋势
4. THE Iteration_Tracker SHALL 为只追加（append-only）语义，已记录的历史条目不被覆盖或删除
5. THE Storage_Abstraction SHALL 以 Storage_Abstraction 接口持久化迭代历史

### 需求 11：存储抽象层（当前文件实现，预留落库）

**用户故事：** 作为平台开发者，我想为审核结果、真值标签、迭代历史和标签注册表定义清晰的存取接口，当前用轻量文件方式实现并预留数据库接入点，以便后续平滑切换到数据库而不改业务逻辑。

#### 验收标准

1. THE Storage_Abstraction SHALL 为以下四类数据各定义读写接口：审核结果（含 Human_Verdict）、固化真值标签、迭代历史、标签注册表
2. THE Storage_Abstraction SHALL 在当前阶段提供一个文件 / JSON 实现，作为这些接口的默认后端
3. THE Storage_Abstraction SHALL 将存储介质与路径设计为由部署配置决定，不在业务代码中写死绝对路径
4. THE Storage_Abstraction SHALL 设计接口签名以便后续新增数据库实现，业务调用方无需修改即可切换后端
5. THE Storage_Abstraction 文件实现 SHALL 对写操作保证基本一致性（如写入完整后再替换），避免会话中断导致记录损坏
6. THE Storage_Abstraction SHALL 在文档中明确标注「落库为后续阶段，当前为抽象接口 + 文件实现」

### 需求 12：闭环编排串联

**用户故事：** 作为平台用户，我想由一个编排层把训练、预测、审核、回流、重训练串成一个可推进的闭环，以便我能清楚当前处于哪一步并推进到下一步。

#### 验收标准

1. THE Loop_Orchestrator SHALL 维护每一轮 Iteration_Loop 的阶段状态机：`trained`（已训练）→ `predicted`（已预测）→ `reviewing`（审核中）→ `reviewed`（审核完成）→ `backfilled`（已回流）
2. WHEN 当前阶段未完成, THE Loop_Orchestrator SHALL 阻止跳过前置阶段直接进入后续阶段，并返回阶段不满足的说明
3. THE Loop_Orchestrator SHALL 在每个阶段完成时通知 Iteration_Tracker 追加对应记录（见需求 10）
4. THE Loop_Orchestrator SHALL 把训练与预测的实际执行委托给已有 AIP 工作流，本编排层只负责触发、传参（含显式 `model_ref`）、收集结果与推进状态
5. WHERE 用户希望复核历史某一轮, THE Loop_Orchestrator SHALL 依据 Iteration_Tracker 的记录定位该轮的数据集版本、模型版本与标签空间快照
