<!-- @AI_GENERATED -->
# Implementation Plan: 光伏故障人机协同迭代标注闭环

## Overview

本计划把设计文档拆解为一系列**增量、可串联**的编码任务。核心约束（贯穿全部任务）：

- **本 spec 是编排层，复用既有，不重造。** 训练评估算子 `stratified_cv_eval`、训练评估模板 `workflow-pv-fault-diag-quickval-cv-v1`、预测模板 `workflow-pv-fault-diag-prediction-v1`、标签编解码 `label_encode`、装载 `load_csv`（`rename_columns`）、合并 `merge_label`（单文件模式）、以及 `workflows_enhanced.py` 内 `stratified_cv_eval → 标准指标键` 的映射，全部是**依赖**，任务只触发 / 传参 / 消费其输出，**不重新实现**其内部逻辑。涉及它们的任务一律标注「复用既有，不重造」。
- **落库为后续阶段。** 当前只实现 `Storage_Abstraction` 抽象接口 + 文件/JSON 后端，**不创建任何 DB 任务**。
- **任务自底向上串联**：存储抽象 → 标签注册表 → 编排器（状态机 + 训练/预测接线）→ 审核会话 / LLM 辅助打标 / 精度评估器 → 回流 → 迭代追踪 → 后端 API 装配（含 `main.py` 注册）→ 前端审核页面 + API 客户端 + 路由挂载 → 端到端集成冒烟。每一步都在前一步基础上构建，无悬挂代码。
- **后端验证（conda 环境 `aip_web`）**：`PYTHONPATH=. pytest tests/test_iterative_labeling_*.py -q` 与 `PYTHONPATH=. python -m py_compile api/iterative_labeling.py services/iterative_labeling/*.py services/iterative_labeling/storage/*.py`。
- **前端验证**：`cd frontend-sevice && npm run build`（已知 Tailwind / chunk size warning 为既有警告，非本次失败）。
- **属性测试约定**：用 Hypothesis（不自造框架），每条属性测试单独覆盖**一条** Correctness Property，最少 **100** 次随机迭代，并以注释标注 `# Feature: pv-fault-iterative-labeling-loop, Property {n}: {property_text}`。带 `*` 的子任务为可选测试任务。

## Tasks

- [x] 1. 存储抽象层（Storage_Abstraction）— 四类仓储接口 + 文件后端
  - [x] 1.1 定义四类仓储抽象接口（DB 迁移唯一边界）
    - 创建 `backend-service/services/iterative_labeling/__init__.py` 与 `backend-service/services/iterative_labeling/storage/__init__.py`、`storage/interfaces.py`
    - 在 `interfaces.py` 定义四类抽象接口：`ReviewResultRepository`（审核结果，含 Human_Verdict）、`GroundTruthRepository`（固化真值标签）、`IterationHistoryRepository`（迭代历史，append-only）、`LabelRegistryRepository`（标签注册表，当前版本 + 历史快照）
    - 接口方法签名与设计一致（如 `save_verdict(slot, review_id, verdict)`、`load_session(slot, review_id)`、`append_labels`、`load_labels`、`append`、`list_sorted`、`load_current`、`save_new_version`），全部以 `slot`（槽位，默认 `default`）为分区参数
    - _Requirements: 11.1, 11.4_
  - [x] 1.2 实现文件/JSON 后端（原子写 + 槽位分区 + 可配置根目录）
    - 创建 `backend-service/services/iterative_labeling/storage/file_backend.py`，实现 1.1 全部接口
    - 路径布局：`review_results/{slot}/{review_id}.json`、`ground_truth/{slot}/{dataset_version}.json`、`iterations/{slot}/*.json`、`label_registry.json`（+ 历史快照）；根目录 `data/iterative_labeling/` 由部署配置注入，**不写死绝对路径**
    - 原子写：写临时文件 → `fsync` → `os.replace` 覆盖目标，避免会话中断导致半截记录
    - _Requirements: 11.2, 11.3, 11.5, 11.6_
  - [ ]* 1.3 文件后端持久化往返 + 原子写属性测试
    - **Property 4：审核结果持久化往返**（提交裁决序列经持久化后读回与提交时完全一致）
    - 同时覆盖 **Property 11.5 原子写**：模拟写入中途中断，断言目标文件要么旧完整内容、要么新完整内容，不出现半截
    - **Validates: Requirements 3.4, 5.5, 11.5**
  - [ ]* 1.4 文件后端单元测试
    - 槽位分区隔离、不存在键的读取回退、根目录由配置注入（不写死路径）等边界
    - _Requirements: 11.2, 11.3_

- [x] 2. 标签注册表（Label_Registry）— label_id 稳定分配 + 版本快照 + Label_Map + 落后检测
  - [x] 2.1 实现 Label_Registry 服务
    - 创建 `backend-service/services/iterative_labeling/label_registry.py`
    - `allocate_label(label_name)`：`label_id = max(现有)+1` 单调递增、永不复用 / 重编号；生成新 `label_space_version` 并保留历史快照
    - 维护与 `label_encode` 兼容的 `label_map`（业务名 → 数值类别），保证存量类别 `encode`/`decode` 映射不变（复用 `label_encode` 算子语义，不重造编解码）
    - 标签空间落后检测：比较模型 `label_space_snapshot` 版本与当前 `label_space_version`
    - 持久化经 `LabelRegistryRepository`（来自任务 1）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 6.6 →（持久化）11.1_
  - [ ]* 2.2 label_id 稳定且唯一属性测试
    - **Property 11：label_id 稳定且唯一**（任意扩充序列下既有 `label_id → label_name` 不变、互不重复、新 id 严格大于历史最大值）
    - **Validates: Requirements 8.1, 8.5**
  - [ ]* 2.3 注册表版本 append-only + 存量映射稳定属性测试
    - **Property 12：注册表版本 append-only 且存量映射稳定**（每次扩充生成新 `label_space_version`、历史快照只增不改，存量类别 `decode(encode(label)) == label` 扩充前后一致）
    - **Validates: Requirements 8.2, 8.3**
  - [ ]* 2.4 标签空间落后判定属性测试
    - **Property 13：标签空间落后判定正确**（`label_space_lag` 为真当且仅当模型快照版本落后于注册表当前版本）
    - **Validates: Requirements 8.4**

- [x] 3. 闭环编排器（Loop_Orchestrator）— 阶段状态机 + 训练/预测接线（复用既有工作流）
  - [x] 3.1 实现状态机核心与闭环 CRUD
    - 创建 `backend-service/services/iterative_labeling/orchestrator.py`
    - 维护每轮 `Iteration_Loop` 的阶段状态机 `trained → predicted → reviewing → reviewed → backfilled`（及 `backfilled → trained` 进入下一轮）
    - 内部符号 `_advance_stage(loop_id, target_stage)`：校验目标阶段是当前阶段的合法直接后继且前置完成，满足则迁移并通知 Iteration_Tracker（任务 6）追加记录，不满足则抛阶段不满足错误
    - 闭环创建（含 `slot`、`iteration_round`）与只读状态读取（含 `label_space_lag`，复用任务 2 的落后检测）
    - _Requirements: 12.1, 12.2, 12.3, 12.5_
  - [x] 3.2 训练评估接线（阶段 → trained）— 复用既有，不重造
    - 以 `model_params`（`test_ratio`/`n_repeats`/`random_state`/`k`/`label_map`）触发 `workflow-pv-fault-diag-quickval-cv-v1`（内部走 `stratified_cv_eval`），复用 `workflows_enhanced.py` 既有执行引擎（`_execute_pipeline_sync` 等）与指标映射，**不在本系统重算切分/特征选择/过采样/训练/精度**
    - 读取算子输出逐键搬运组装 `Accuracy_Record`（`macro_f1_mean ± macro_f1_std` 等），登记 `Model_Artifact`（含 `model_ref`/`dataset_version`/`label_space_snapshot`/`iteration_round`）
    - 数据集缺真值标签列时返回 `422` + `missing_columns`，不触发训练
    - _Requirements: 1.1, 1.9, 1.10, 1.11, 12.4_
  - [x] 3.3 预测接线（阶段 trained → predicted）— 复用既有，不重造
    - 以显式 `model_ref` 触发 `workflow-pv-fault-diag-prediction-v1`，为每个 Diagnosis_Unit 产出 `Classifier_Prediction`（`predicted_label`/`confidence`/`unit_key`）
    - `model_ref` 缺失或无效返回 `400`，禁止任何隐式重训；预测结果与 `model_ref`/`dataset_version`/`iteration_round` 关联保存
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_
  - [ ]* 3.4 阶段状态机属性测试
    - **Property 16：阶段状态机只允许相邻且前置完成的迁移**（穷举/随机 `(当前阶段, 目标阶段)`，仅合法直接后继且前置完成被接受）
    - **Validates: Requirements 12.1, 12.2**
  - [ ]* 3.5 登记记录字段完整性属性测试
    - **Property 1：登记记录字段完整性**（装配的 `Model_Artifact`/`Classifier_Prediction`/迭代历史记录含全部必填字段，`accuracy_record` 各键值与算子输出逐键一致，搬运不丢不改）
    - **Validates: Requirements 1.9, 2.3, 10.2**
  - [ ]* 3.6 缺 model_ref 必拒预测属性测试
    - **Property 2：缺有效 model_ref 必拒预测且不触发训练**（缺失/无效 `model_ref` 一律拒绝并报错，绝不触发任何训练/重训）
    - **Validates: Requirements 2.2**
  - [ ]* 3.7 训练/预测触发既有工作流集成冒烟测试
    - 用 1~3 个代表性示例验证 `/train`、`/predict` 确实以正确参数触发既有 `quickval-cv` / `prediction` 工作流，且本系统未自实现切分（mock 既有引擎，断言传参与不重算）
    - 注：`stratified_cv_eval` 内部算法由 `pv-fault-diagnosis-integration` spec 测试，本任务**不**重复测其内部
    - _Requirements: 1.1, 1.11, 2.1, 2.5, 12.4_

- [x] 4. 审核会话 + LLM 辅助打标 + 三方精度评估器
  - [x] 4.1 实现 Review_Session 服务
    - 创建 `backend-service/services/iterative_labeling/review_session.py`
    - 基于预测批次装配待审核单元（逐 Diagnosis_Unit），双来源并列与不一致 `disagreement` 标志，进度统计（`reviewed_count`/`total_count`），断点恢复（经任务 1 持久化）
    - 四类动作处理 `confirm`/`correct`/`new_label`/`skip`：`confirm/correct/new_label` 写真值（`is_ground_truth=true`），`skip` 标 `pending` 不写真值；记录 `unit_key`/`verdict_label`/`action_type`/`reviewer`/`reviewed_at`
    - `new_label` 走任务 2 的 `allocate_label` 标签扩充
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
  - [x] 4.2 实现 LLM_Labeling_Assistant
    - 创建 `backend-service/services/iterative_labeling/llm_labeling_assistant.py`
    - `generate_suggestion(unit, label_registry, llm_config)`：复用 `api/llm_config.py` 默认配置（不新增密钥管理），生成 `suggested_label` + `reason`，记录 `llm_config_ref`/`generated_at`
    - 约束建议标签取自当前注册表；越界标 `out_of_registry=true` 提示人工不自动采纳；禁止写真值；调用失败/超时置 `available=false` 不中断审核
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
  - [x] 4.3 实现 Accuracy_Evaluator（三方精度增量计算）
    - 创建 `backend-service/services/iterative_labeling/accuracy_evaluator.py`
    - 以已固化 Human_Verdict 为真值，计算 `classifier_accuracy`/`llm_accuracy`/`human_verified_accuracy` + macro `precision`/`recall`/`f1` + `llm_coverage`；仅纳入 `confirm/correct/new_label`，排除 `pending`
    - 内部符号 `update_incremental(state, new_verdict)`：每提交一条裁决增量更新而非全量重算；LLM 缺失单元从 LLM 分母剔除并标覆盖率；无已审核单元时返回占位不抛异常
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_
  - [ ]* 4.4 审核会话单元数一致属性测试
    - **Property 3：审核会话单元数与预测单元一致**（`total_count` 等于批次唯一 Diagnosis_Unit 数量，不漏不重）
    - **Validates: Requirements 3.1**
  - [ ]* 4.5 双来源分歧标志属性测试
    - **Property 5：双来源分歧标志正确**（当且仅当两来源都存在且不相等时 `disagreement` 为真）
    - **Validates: Requirements 4.2**
  - [ ]* 4.6 动作类型决定真值固化属性测试
    - **Property 6：动作类型决定真值固化**（`is_ground_truth` 为真当且仅当 `action_type ∈ {confirm, correct, new_label}`；`skip` 标 `pending` 且不产真值）
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**
  - [ ]* 4.7 人工最终权威属性测试
    - **Property 7：人工最终权威（真值仅来自人工裁决）**（每条真值可溯源到一条 Human_Verdict，不存在仅由分类器/LLM 产生的真值）
    - **Validates: Requirements 4.3, 7.4**
  - [ ]* 4.8 LLM 越界标签属性测试
    - **Property 10：LLM 越界标签被标注且不可被直接采纳**（`out_of_registry` 为真当且仅当标签不在注册表，越界建议不进入可一键确认的可选真值集合）
    - **Validates: Requirements 7.3**
  - [ ]* 4.9 三方精度增量==全量等价属性测试
    - **Property 9：三方精度增量更新与全量重算等价**（随机裁决序列逐条增量与末态全量重算结果一致，含 macro precision/recall/f1 与 llm_coverage）
    - **Validates: Requirements 6.1, 6.4, 6.5**

- [x] 5. 打标回流（Backfill）— 人工裁决组装为新数据集版本
  - [x] 5.1 实现 Backfill 服务
    - 创建 `backend-service/services/iterative_labeling/backfill.py`
    - 取 `confirm/correct/new_label` 单元及其 Human_Verdict 组装新 `Labeled_Dataset` 版本，排除 `pending`；分配单调 `dataset_version`，记录 `source_iteration`/`base_dataset_version`；`merge_base=true` 时与基线累积合并
    - 回流标签列与 `label_encode` 的 Label_Map 兼容，使其可经 `load_csv`（`rename_columns`）+ `merge_label`（单文件模式）进入下一轮训练（复用既有装载/合并算子，不重造）
    - 成功后推进阶段 `reviewed → backfilled`（调用任务 3 的 `_advance_stage`）
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - [ ]* 5.2 dataset_version 单调且血缘属性测试
    - **Property 14：dataset_version 单调且血缘正确**（新版本相对 `base_dataset_version` 严格递增，`source_iteration`/`base_dataset_version` 正确指向来源，累积合并规模等于「基线 ∪ 本轮非 pending」去重规模）
    - **Validates: Requirements 9.2, 9.3**
  - [ ]* 5.3 pending 不计精度不进回流属性测试
    - **Property 8：pending 既不计精度也不进回流**（任意比例 pending 的会话，精度分母 `counted_units` 与回流单元集合都不含 pending）
    - **Validates: Requirements 6.2, 9.5**

- [x] 6. 迭代追踪（Iteration_Tracker）— append-only 历史 + 排序趋势
  - [x] 6.1 实现 Iteration_Tracker
    - 创建 `backend-service/services/iterative_labeling/iteration_tracker.py`
    - append-only 追加迭代记录（`iteration_id`/`iteration_round`/`dataset_version`/`model_version`/`accuracy_record`/`label_space_version`/`label_count`/`created_at`），经任务 1 的 `IterationHistoryRepository` 持久化
    - 按 `iteration_round` 排序的可追溯视图 + 趋势（`macro_f1_by_round`/`label_count_by_round`）
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
  - [ ]* 6.2 迭代历史 append-only 且有序属性测试
    - **Property 15：迭代历史 append-only 且按轮次有序**（任意追加序列后历史是前一状态超集，`list_sorted` 按 `iteration_round` 非降序）
    - **Validates: Requirements 10.3, 10.4**
  - [ ]* 6.3 历史轮次定位往返属性测试
    - **Property 17：历史轮次定位往返**（按任一 `iteration_round` 定位返回的 `(dataset_version, model_version, label_space_version)` 与登记时完全一致）
    - **Validates: Requirements 12.5**

- [x] 7. 后端 API 装配（api/iterative_labeling.py + main.py 注册）
  - [x] 7.1 实现全部 HTTP 接口
    - 创建 `backend-service/api/iterative_labeling.py`，前缀统一 `/api/iterative-labeling`
    - 暴露：闭环（`POST /loops`、`POST /loops/{loop_id}/train`、`POST /loops/{loop_id}/predict`、`GET /loops/{loop_id}`、`POST /loops/{loop_id}/backfill`）、审核会话（`POST /review-sessions`、`GET /review-sessions/{review_id}`、`POST /review-sessions/{review_id}/verdicts`、`GET /review-sessions/{review_id}/accuracy`）、标签注册表（`GET /label-registry`、`POST /label-registry/labels`、`GET /label-registry/versions`）、迭代历史（`GET /iterations`）
    - 接线到任务 3~6 的服务，写入类接口经 Storage_Abstraction 落地
    - _Requirements: 3.5, 4.4, 8.4, 12.3_
  - [x] 7.2 在 main.py 注册路由（最小改动）
    - 修改 `backend-service/main.py`，新增一行 `include_router` 注册 `iterative_labeling`，不改动其他路由
    - _Requirements: 12.4_
  - [ ]* 7.3 API 契约 + 错误分支集成测试
    - 验证 `/train` 缺真值列返回 `422` + `missing_columns`、`/predict` 缺/无效 `model_ref` 返回 `400`、`skip` 单元不写真值不计精度，以及审核会话复用 `api/upload.py` 预览通道（不另起数据通道）
    - _Requirements: 1.10, 2.2, 3.5, 5.4_

- [x] 8. 检查点 — 确保后端测试通过
  - 在 conda `aip_web` 下运行 `PYTHONPATH=. pytest tests/test_iterative_labeling_*.py -q` 与 `python -m py_compile`，确保全部后端任务通过；如有疑问询问用户。

- [x] 9. 前端审核窗口（Review_Window）+ API 客户端 + 路由挂载
  - [x] 9.1 实现 API 客户端
    - 创建 `frontend-sevice/src/services/iterativeLabelingApi.ts`，封装审核/编排/标签/迭代相关请求（对齐任务 7 接口契约）
    - _Requirements: 3.1, 4.1, 6.1, 8.1_
  - [x] 9.2 实现人工审核预测准确率页面
    - 创建 `frontend-sevice/src/pages/IterativeLabelingReviewPage.tsx`
    - 双来源并列（分类器 `predicted_label`+`confidence` 与 LLM `suggested_label`+`reason`）、不一致高亮、两来源均标「辅助建议」、LLM 缺失标「LLM 建议不可用」不阻断；四类动作、三方精度面板、进度与断点恢复
    - 复用数据集/上传接口（`GET /api/upload/file/{file_id}/preview`）获取被审核数据集预览与样本，**不另起数据通道**
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 6.1, 3.5_
  - [x] 9.3 路由与数据集模块入口挂载（最小改动）
    - 在 `frontend-sevice/src/App.tsx` 注册该页面路由，并在数据集模块入口挂载跳转
    - _Requirements: 3.1_

- [x] 10. 端到端集成与最终检查点
  - [ ]* 10.1 闭环端到端集成冒烟测试
    - 串联 `train → predict → review → backfill → 下一轮 train`，验证状态机推进、回流排除 pending、迭代历史追加与趋势；既有工作流以 mock/桩替代（不重测其内部算法）
    - _Requirements: 9.4, 10.1, 12.1, 12.3_
  - [x] 10.2 最终检查点 — 确保前后端验证通过
    - 后端：conda `aip_web` 下 `pytest tests/test_iterative_labeling_*.py -q` + `py_compile`；前端：`npm run build`（Tailwind / chunk size warning 为既有警告）。如有疑问询问用户。

## Notes

- 带 `*` 的子任务为可选测试任务（单元 / 属性 / 集成），可为更快 MVP 跳过；顶层任务不标 `*`。
- 每个任务引用具体需求子条款以便追溯；属性测试任务显式引用设计文档的 Correctness Property 编号。
- **复用边界**：任务 3.2 / 3.3 / 5.1 涉及的 `stratified_cv_eval`、`quickval-cv` / `prediction` 模板、`label_encode`、`load_csv`、`merge_label` 与指标映射均为依赖，只触发 / 传参 / 消费，不重造；`stratified_cv_eval` 内部算法（需求 1.2~1.8）由 `pv-fault-diagnosis-integration` spec 测试，本 spec 仅在 3.7 / 10.1 用集成冒烟验证「调用与传参正确」。
- **落库为后续阶段**：当前仅 `Storage_Abstraction` 抽象接口 + 文件/JSON 后端，未包含任何 DB 任务。
- 17 条 Correctness Property 各由单条 Hypothesis 属性测试覆盖（≥100 次迭代），分布在最贴近其实现的任务中以尽早发现错误。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "6.1", "4.3", "1.3"] },
    { "id": 3, "tasks": ["4.2", "5.1", "3.1", "1.4", "2.2", "4.9", "6.2"] },
    { "id": 4, "tasks": ["4.1", "3.2", "3.3", "2.3", "3.4", "4.8", "5.2", "6.3"] },
    { "id": 5, "tasks": ["7.1", "2.4", "3.5", "4.4", "5.3"] },
    { "id": 6, "tasks": ["7.2", "9.1", "3.6", "4.5", "7.3"] },
    { "id": 7, "tasks": ["9.2", "3.7", "4.6"] },
    { "id": 8, "tasks": ["9.3", "4.7"] },
    { "id": 9, "tasks": ["10.1"] }
  ]
}
```
