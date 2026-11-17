<!-- @AI_GENERATED -->
# 光伏故障诊断产品蓝图：现状、目标形态与调整清单

> 记录日期：2026-08-25
> 适用范围：`agentic_algo_platform` 仓库中的光伏故障诊断产品线（`pv_fault` 槽位），兼及负荷预测线的公共基础设施。
> 文档性质：**静态读码得出的现状盘点 + 产品设计建议**。所有「现状」结论均标注了代码位置；未经运行验证的部分在第 6 节统一列出。

---

## 0. 一页结论

产品目标链路是四段：

```
无标签数据 →①聚类初标→ 标签提案 →②专家校验→ 专家校验数据集 →③画布诊断→ 诊断结果
                                                  ↑                              ↓
                                                  └──────④人工复核回流────────┘
```

现状判断：

| 结论 | 说明 |
|---|---|
| 链路已存在约 70% | ①②③ 三段都有可用实现，④ 也有大部分接口 |
| 但 ① 是「硬编码 REST 流程」，不是「模板」 | 分组键、特征、聚类算法全部焊死在一个 Python 方法里，用户无法在画布上改 |
| ② 到 ③ 之间**是断的** | 专家校验产出的数据集没有注册进画布可见的数据集表，画布上搜不到 |
| 平台层有两个大洞 | 算子货架 85% 是空壳；画布无连线类型校验 |
| 「实时诊断」场景**不存在** | 现有两条路径都是日级批处理，不是流式 |

---

## 1. 仓库结构与关键路径

### 1.1 顶层目录

| 路径 | 职责 |
|---|---|
| `backend-service/` | FastAPI 后端。API 路由、算子实现、工作流执行引擎、光伏标注与调度服务 |
| `frontend-sevice/` | React + Vite + Ant Design 前端（目录名拼写为 `sevice`，不要改名） |
| `fault-diag-algo-release-3.1/` | 光伏故障诊断**原始算法工程**（外部交付物）。平台算子由此迁移而来 |
| `load_forecast_refactored/` | 负荷预测专项实验工程，与平台相对独立 |
| `docs/` | 设计文档与规格。含 `docs/specs/`、`docs/pv_fault/spec/` 两处 spec 副本 |
| `.kiro/specs/` | 第三处 spec 副本（与 `docs/specs/` 存在完全相同的文件） |

### 1.2 光伏故障诊断相关的核心文件

**后端 API 层**

| 路径 | 职责 |
|---|---|
| `backend-service/api/iterative_labeling.py` | 迭代标注全部接口（58 个端点，3438 行）。聚类 run、审核会话、标签注册表、累计训练、双路径模型登记都在这里 |
| `backend-service/api/pv_dual_path.py` | 光伏双路径生产调度只读接口（8 个端点）。逐日账本、启用周期、影子对比、历史回放 |
| `backend-service/api/workflows_enhanced.py` | 增强工作流的一切（71 个端点，**13970 行**）。数据集管理、模板实例化、执行、回测、AutoResearch |
| `backend-service/api/scheduler.py` | 定时任务与到达看板（23 个端点） |

**后端服务层**

| 路径 | 职责 |
|---|---|
| `backend-service/services/iterative_labeling/pv_training_workspace.py` | **聚类打标的核心实现**。`create_clustering_run()` / `update_cluster()` / `confirm_clustering_run()` 三段生命周期 |
| `backend-service/services/iterative_labeling/label_registry.py` | 标签空间注册表。`label_id` 单调递增永不复用、`label_space_version` 版本快照只追加、支持模型标签空间落后检测 |
| `backend-service/services/iterative_labeling/backfill.py` | 审核真值回流。`backfill_to_raw_dataset()` 把人工裁决回贴成可再训练的 CSV，`_allocate_dataset_version()` 分配版本号 |
| `backend-service/services/iterative_labeling/cumulative_training.py` | 累计训练集与双路径模型登记（`production_path` / `path_models` / `path_switch_audit`） |
| `backend-service/services/iterative_labeling/seq_annotation/` | 全天 288 点序列标注模型（BiLSTM+Attention / UNet1D）。含 `predictor.py`、`trainer.py`、`grid_align.py`、`postprocessing.py` |
| `backend-service/services/iterative_labeling/tsc/` | 时序分类模型库。滑窗切分器、8 模型注册表、CNN-LSTM / CNN-BiLSTM-Attention / ROCKET-RF |
| `backend-service/services/scheduler/pv_dual_path/` | 双路径生产调度（21 个文件）。策略分派、逐日账本、启用周期、影子对比、切换门控 |
| `backend-service/services/operator_backends/` | 算子实现目录。142 个非下划线开头的 `.py`，其中 **139 个导出模块级 `OPERATOR_ID` + `execute(params, inputs)`**；`solar_window.py`、`night_anomaly.py` 是被其他算子复用的工具模块，不是算子 |
| `backend-service/services/operator_execution/` | 算子执行框架。`router.py` 自动发现算子、`global_config_injector.py` 下发全局配置、`schema_validator.py` + `data_contracts.py` 数据契约 |

**前端**

| 路径 | 职责 |
|---|---|
| `frontend-sevice/src/pages/DatasetPage.tsx` | 数据集页。**含聚类打标交互**：上传 → 聚类 → 逐簇命名 → 确认 |
| `frontend-sevice/src/pages/IterativeLabelingListPage.tsx` | 迭代标注列表页。也含一套聚类打标交互（与上面重复） |
| `frontend-sevice/src/pages/IterativeLabelingReviewPage.tsx` | **专家校验主界面**（68030 字节）。逐单元改判、SHAP、相似案例、参考波形 |
| `frontend-sevice/src/pages/WorkflowEditorPage.tsx` | 画布编辑器页面外壳 |
| `frontend-sevice/src/components/workflow-enhanced/` | 画布实现（50 个文件）。`EnhancedCanvas.tsx` 画布本体、`NodeLibraryPanelV2.tsx` 算子面板、`PropertyPanelV2.tsx` 参数面板 |
| `frontend-sevice/src/pages/PvDualPathConsole.tsx` | 双路径控制台。以 `PvDualPathGovernancePanel` / `PvDualPathOperationsPanel` 两个变体嵌入部署页与精度运营页 |
| `frontend-sevice/src/services/iterativeLabelingApi.ts` | 迭代标注 API 客户端，含 `trainingWorkspaceApi.createClusteringRun()` 等 |

**数据与模板**

| 路径 | 职责 |
|---|---|
| `backend-service/data/functions.json` | 算子货架注册表。`categories`（19 类）+ `functions`（**817 条定义**） |
| `backend-service/data/workflows_enhanced/workflow-pv-fault-diag-quickval-cv-v1.json` | 光伏故障诊断**训练/评估模板**（8 节点） |
| `backend-service/data/workflows_enhanced/workflow-pv-fault-diag-quickval-predict-v1.json` | 光伏故障诊断**预测模板**（10 节点） |
| `backend-service/data/iterative_labeling/training_workspace/pv_fault/{run_id}/` | 聚类 run 工作区。`run.json` 状态、`features.csv` 特征表、`source_data.csv` 源数据、`confirmed/labeled-{run_id}.csv` 确认产出 |
| `fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet` | 已标注的光伏训练数据（模板默认输入） |

---

## 2. 现状：聚类打标 → 专家校验 → 画布诊断

### 2.1 ① 聚类初标（已有，但是硬编码）

**接口**：`POST /api/iterative-labeling/clustering/runs`
**实现**：`services/iterative_labeling/pv_training_workspace.py` 的 `create_clustering_run(samples, n_clusters, reviewer)`

实际做的事，按顺序：

1. 输入来源二选一：`dataset_path`（项目根相对路径的 CSV/Parquet）或 PV 数据库候选样本查询
2. 按 `site_id + device_id + branch_id + date` 分组，一组 = 一个诊断片段
3. 对 `value` / `i_cal` 两列各算 `mean` / `std` / `min` / `max`，得 8 维特征
4. 生成 `member_key`（`site|device|branch|date` 拼接）
5. 调 `services/operator_backends/kmeans.py` 的 `execute()`，`random_state=42`
6. 落盘：`features.csv`、`source_data.csv`、`run.json`（状态 `pending_naming`）

**硬编码点**（这些是「不是模板」的具体含义）：

| 项 | 现状 | 用户无法改 |
|---|---|---|
| 分组键 | 固定 `site_id/device_id/branch_id/date` | 换成 12h 粒度、换成按逆变器分组都不行 |
| 特征 | 固定 `value`/`i_cal` × 4 个统计量；缺这两列直接抛 `ValueError` | 想加频域特征、tsfresh 特征都不行 |
| 聚类算法 | 只有 KMeans | 仓库里另外 5 个聚类算子用不上 |
| `k` 值 | 调用方传，前端两处均硬编码 `n_clusters: 5` | 没有选 k 的依据 |
| 随机种子 | 固定 42 | — |

### 2.2 ② 专家校验（已有，簇级）

| 能力 | 接口 | 实现位置 |
|---|---|---|
| 簇级命名 + 成员筛选 | `PUT /clustering/runs/{run_id}/clusters/{cluster_id}` | `update_cluster()` |
| 二次确认 | `POST /clustering/runs/{run_id}/confirm` | `confirm_clustering_run()` |
| 单元级改判 | `POST /review-sessions/{review_id}/verdicts` | `services/iterative_labeling/review_session.py` |
| 自由窗打标 | `POST /review-sessions/{review_id}/freeform-labels`、`POST /training-slices` | `freeform_labeling.py`、`create_confirmed_time_slice()` |
| 判断辅助 | `GET .../shap/{unit_key}`、`.../similar/{unit_key}`、`GET /reference-waveforms` | `shap_explainer.py`、`similar_case_retriever.py` |
| 标注者间一致性 | `GET/POST /review-sessions/{review_id}/iaa` | `iaa_evaluator.py` |

状态机（在 `run.json` 的 `status` 字段）：

```
pending_naming ──全部簇已命名──> pending_confirmation ──confirm──> confirmed
```

`confirm_clustering_run()` 的准入检查是硬的：每个簇必须有 `proposed_label_name`（专家给的故障名）**且**必须有非空 `selected_member_keys`（专家挑的成员），否则 422。这个「机器标的东西不确认就不能用」的门是对的，只是没被抽成显式概念。

### 2.3 ③ 沉淀数据集（已有，但没有版本概念）

`confirm_clustering_run()` 做两件事：

1. 写不可变 CSV 到 `data/iterative_labeling/training_workspace/pv_fault/{run_id}/confirmed/labeled-{run_id}.csv`
2. 调 `CumulativeTrainingService.register_labeled_dataset()` 登记进**光伏累计训练集**

`api/iterative_labeling.py` 的路由层在这之前还会做一步：对每个簇的 `proposed_label_name`，若标签注册表里没有则调 `LabelRegistryService.allocate_label()` 新建，得到 `label_id_map`（标签名 → 数值 ID）。

**问题**：这条路**不分配 `dataset_version`**，只返回 `dataset_path`。而另一条路（预测复核回流）的 `BackfillService._allocate_dataset_version()` 会分配 `ds-r{iteration}-{timestamp}` 格式的版本号。同一个概念两种待遇。

### 2.4 ④ 画布诊断（模板已有，但接不上 ③）

**两个现成模板**

`workflow-pv-fault-diag-quickval-cv-v1.json`（训练/评估）：

```
load_csv → time_window_split(1d) → handle_missing → detect_outliers
        → extract_statistical_features → tsfresh_extract
        → ts_comparison_features → stratified_cv_eval
```

`workflow-pv-fault-diag-quickval-predict-v1.json`（预测）：

```
load_csv → time_window_split → handle_missing → detect_outliers
        → extract_statistical_features → tsfresh_extract → ts_comparison_features
        → feature_select → random_forest_classifier → label_encode(反映射)
```

模板质量不错：`stratified_cv_eval` 把 SMOTE 放在数据切分之后，避开了过采样泄漏。模板 `metadata.global_config` 里有 `scene: solar`、`device_type: combinerbox`、`run_mode: train` 等场景标识。

**断点**：画布读的数据集注册表是 `api/workflows_enhanced.py` 里的 `_load_dataset_registry()` / `POST /api/workflows-enhanced/datasets/register`，与 `CumulativeTrainingService` 那套**互不知道对方存在**。核实依据：

- `DatasetPage.tsx` 全文 `registerDataset` 出现 **0 次**、`workflow` 出现 **0 次**
- `confirm_clustering_run()` 只调 `CumulativeTrainingService`，没有触碰画布侧注册表

结果：专家校验完的数据集在画布 `load_csv` 的数据集下拉里搜不到，只能人肉抄路径。

---

## 3. 现状：平台层的洞

### 3.1 算子货架 85% 是空壳

| 指标 | 数值 | 依据 |
|---|---|---|
| `functions.json` 注册的算子 | **817** | `d['functions']` 长度 |
| `operator_backends/` 导出模块级 `OPERATOR_ID` 的模块 | **139** | 逐文件正则提取（行首 `OPERATOR_ID =`） |
| 两边对得上号的 | **124** | 集合交集 |
| **注册了但无后端实现** | **693** | 集合差 |
| **实现了但未注册** | **15** | 见下方「命名孪生」 |

`services/operator_execution/router.py` 的 `execute()` 在算子未注册时直接抛 `OperatorExecutionError(operator_id, "OperatorNotFoundError", …)`。**用户在画布上拖那 693 个中的任何一个，运行必然失败**，而 UI 上它们和可用算子长得一样。

其中包含实时场景刚好需要的：`load_mqtt`、`load_kafka`、`load_opcua`、`load_modbus`、`load_timeseries_db`、`model_serve_stream`；以及诊断可能需要的 `lstm_classifier`、`transformer_classifier`、`rocket_classifier`、`shap_explain`。

#### 命名孪生：15 个能跑的算子被埋，货架上摆的是它们的空壳双胞胎

这 15 个模块**有 `OPERATOR_ID` 也有 `execute()`，能跑**，但 `functions.json` 用了另一个 ID 注册，导致画布上看不到它们；而货架上那个同义 ID 反而没有实现。逐项核对：

| 实现侧 `OPERATOR_ID`（能跑，画布看不到） | 货架侧注册 ID（画布能拖，跑必失败） |
|---|---|
| `kmeans` | `kmeans_cluster` |
| `dbscan` | `dbscan_cluster` |
| `agglomerative_clustering` | `agglomerative_cluster` |
| `pca` | `pca_reduce` / `pca_reduction` |
| `lof_detector` | `lof_anomaly` |
| `elliptic_envelope` | `elliptic_envelope_anomaly` |
| `one_class_svm` | `ocsvm_anomaly` |
| `arima` | `arima_forecast` |
| `prophet` | `prophet_forecast` |
| `elastic_net` | `elastic_net_regression` / `elastic_net_forecast` |
| `roc_auc` | `roc_auc_score` |
| `classification_report` | `confusion_matrix_eval`（语义相近，需确认） |
| `histogram` | `histogram_chart` |
| `save_model_artifact` | `save_model` |
| `load_model_artifact` | `load_model` |

**这一条直接卡住打标签模板**：模板 A 需要的 `kmeans`、`dbscan`、`agglomerative_clustering`、`pca` 四个算子全在这份被埋名单里。反倒是 `gmm_cluster`、`hdbscan_cluster`、`optics_cluster`、`silhouette_score` 四个是 ID 对齐的，画布上能正常用。

### 3.2 画布没有连线类型校验

- `frontend-sevice/src/components/workflow-enhanced/portTypeValidation.ts` 导出了 `isPortTypeCompatible()` / `validateConnection()` / `getEdgeColorForType()`
- `frontend-sevice/src/components/workflow-enhanced/DataContractTooltip.tsx` 是数据契约悬浮提示组件
- **两个文件在全仓库范围内从未被任何文件 import** —— 是死代码
- `EnhancedCanvas.tsx` 的 `onConnect` 直接 `addEdge`，没有传 `isValidConnection`

后果：可以把标量指标连到模型训练的数据口上，画布不拦，跑到那一步才炸。

`services/operator_execution/data_contracts.py` 只有 16 条契约，**全部是负荷预测的**（`load_csv_output`、`xgboost_train_output`、`smape_output` 等），光伏故障诊断一条没有。`schema_validator.py` 有能力但没有 PV 契约喂给它。

### 3.3 模板换数据集要手改 7 个节点

`POST /api/workflows-enhanced/datasets/switch` 只做一件事：把 `load_csv` 节点的 `file_path` 改掉。

但 quickval 模板里字段角色散在每个节点各写一遍（逐节点核对 `workflow-pv-fault-diag-quickval-cv-v1.json` 得到）：

```
load_csv:                     time_field=time, id_fields=[site_id,device_id,branch_id],
                              rename_columns={"data_date":"time","branch":"branch_id"}
time_window_split:            id_fields=[site_id,device_id,branch_id], time_field=time
handle_missing:               id_fields=[...,time_window], value_fields=[value,i_cal]
detect_outliers:              id_fields=[...,time_window], value_fields=[value,i_cal]
extract_statistical_features: id_fields=[...,time_window,label], value_fields=[value,i_cal]
tsfresh_extract:              id_fields=[...,time_window], value_fields=[value,i_cal]
ts_comparison_features:       id_fields=[...,time_window], value_fields=[value,i_cal]
```

`services/operator_execution/global_config_injector.py` 的 `_PROMOTED_FIELDS` 只有三项：`time_zone`、`nowtime`、`operate_status`。**字段映射不在其中**，所以只能逐节点填。

### 3.4 「实时诊断」不存在

现有两条路径的真实语义：

| 路径标识 | 输入 | 输出粒度 | 时效 |
|---|---|---|---|
| `legacy_day` | 当天已到达的增量测点 | **天级**标签 | 日内可增量跑 |
| `seq_annotation` | 整天 288 点，占用率必须 ≥ 90% | **逐点**标签 + 故障段 | 必须等一天基本完整 |

`services/iterative_labeling/seq_annotation/predictor.py` 的 `predict_device_day()` 显式拒绝多天输入（`df['time'].dt.normalize().nunique() != 1` 直接返回空结果，报「禁止把多天数据覆盖到同一时钟网格」），也没有「部分日」入口。

调度侧 `services/scheduler/engine.py` 是 APScheduler cron 微批，全文无 `websocket` / `kafka` / `mqtt` / `stream`。全仓库搜 `realtime|streaming|online_infer`，后端业务代码零命中。

**所以 `seq_annotation` 不是实时诊断，是「事后逐点复盘」。真正的实时（滚动滑窗 + 部分日 + 点级告警 + 告警去重）是空白。**

### 3.5 生产治理可被绕过

`services/scheduler/pv_dual_path/cross_path_switch_coordinator.py`：`switch_mode ∈ {simple, lab}` 时走 `_switch_simple()`，只检查目标 Champion 存在 + `confirm=true`，**跳过九项跨路径准入、跳过影子对比证据、跳过生产启用周期建立**。

前端两个入口全部硬编码走它：

- `frontend-sevice/src/pages/PvDualPathConsole.tsx`：`switch_mode:'simple', operator:'lab', confirm:true, activation_mode:'cutover_only'`
- `frontend-sevice/src/pages/accuracy-operations/PvFaultModelingPathOpsPanel.tsx`：同样

叠加另一条：`PUT /cumulative-training/modeling-paths`、`register-model`、`switch-fallback` 三个写接口**无鉴权**（`docs/specs/pv-fault-dual-path-serving/requirements.md` 的 Requirement 10.9 已把它列为上线阻断项）。

### 3.6 其他

- **`workflows_enhanced.py` 是 13970 行 / 71 端点的上帝模块**。数据集、模板、执行、回测、AutoResearch、候选池全在一个文件
- **前端 IA 膨胀**：74 条路由 / 57 个页面组件，其中 9 个页面**未接任何路由**（`BacktestTaskPage`、`BacktestMonitorPage`、`BacktestResultPage`、`SkillLibraryPage`、`BasicModuleOverviewPage`、`BasicModuleCategoryPage`、`LoginPageNew`、`AlgorithmDeploymentPlaceholderPage`）；成对重复页：`TemplateGalleryPage` / `OfficialTemplateLibraryPage`、`WorkflowV2Page` / `DifyReplicaPage` / `WorkflowReferencePage`
- **spec 有三份副本**：`.kiro/specs/`、`docs/specs/`、`docs/pv_fault/spec/`。已校验 `pv-fault-timeseries-diagnosis/tasks.md` 在前两处 md5 完全相同
- **`precision_ops` 与 `accuracy_operations` 两套同义模块并存**，`api/precision_ops.py` 未在 `main.py` 注册
- **聚类打标交互在前端出现两份**：`DatasetPage.tsx` 和 `IterativeLabelingListPage.tsx` 各有一套

---

## 4. 需要的产品形态

### 4.1 主链路定义

```
[无标签数据集]
     │
     │  模板 A：labeling_pipeline（打标签模板）—— 画布世界，无状态 DAG
     ▼  load → 切单元 → 清洗 → 特征 → 标准化 → 降维 → 聚类 → 簇画像
[label_proposal 标签提案]  ← 关键：产出的不是数据集
     │
     │  ══════ 专家校验工作台（有状态交互会话，不进画布）══════
     │  簇级：命名 / 剔除成员      单元级：逐条改判 / 自由窗打标
     │  二次确认（不可绕过的状态门）
     ▼
[LabeledDatasetVersion 专家校验数据集]  ← 三块之间唯一的接缝
     │
     │  模板 B：fault_diagnosis_pipeline（故障诊断模板）—— 画布世界，无状态 DAG
     ▼  load_labeled_dataset → 切单元 → 清洗 → 特征 → 训练/评估 或 预测
[诊断结果 / prediction_batch]
     │
     │  ══════ 专家复核（已有 from-prediction 会话）══════
     ▼
[LabeledDatasetVersion v2] ──┐
                             └──> 回到模板 B 重训（闭环）
```

**已有标签的数据集**：跳过 ①②，直接注册成 `LabeledDatasetVersion`（`status=curated`），进模板 B。

### 4.2 三个核心抽象

#### 抽象 1：`label_proposal`（标签提案）—— 模板 A 的产出物

**这是最重要的设计决策。** 聚类模板跑完，产出的**不能叫数据集**，只能叫标签提案。

理由：一旦机器标的东西叫了「数据集」，它就会被当真值拿去训练。产品里必须存在一个不可绕过的状态门：`proposal` 状态的东西**永远不能进训练**，只有经过专家二次确认才能升级为数据集版本。

```jsonc
{
  "proposal_id": "prop-a3f2c8d19b40",       // 提案标识
  "source": {                                // 血缘：这份提案怎么来的
    "workflow_id": "workflow-pv-labeling-cluster-v1",  // 产出它的画布模板 ID
    "execution_id": "exec-…",                          // 哪一次执行
    "input_dataset_ref": "backend-service/data/uploads/xxx.parquet"  // 输入的无标签数据（项目根相对路径）
  },
  "unit_key_fields": ["site_id","device_id","branch_id","time_window"],  // 诊断单元主键字段
  "clusters": [
    {
      "cluster_id": 0,                       // 簇编号
      "member_count": 143,                   // 成员数
      "member_keys": ["…"],                  // 全部成员键
      "representative_keys": ["…"],          // 代表成员（供专家优先看）
      "feature_profile": { },                // 簇特征画像：各特征均值/分位数
      "waveform_samples": [ ],               // 代表波形（专家判断故障类型主要靠这个）
      "silhouette": 0.62,                    // 该簇轮廓系数，越低越可疑，用于排优先级
      "proposed_label_name": null,           // 专家填：这个簇是什么故障
      "selected_member_keys": null           // 专家填：这个簇里哪些成员算
    }
  ],
  "status": "pending_naming",                // pending_naming → pending_confirmation → confirmed
  "label_space_version": "ls-v5"             // 引用 label_registry 的标签空间版本
}
```

#### 抽象 2：`LabeledDatasetVersion`（数据集版本）—— 唯一的接缝

现在有**三套互不相通的数据集概念**（见 2.3、2.4），必须收敛成一个工件 + 一张注册表：

```jsonc
{
  "dataset_version_id": "lds-pv-0007",        // 数据集版本标识，单调递增、永不复用
  "name": "寿光电站-组串故障-专家校验v1",
  "status": "curated",                        // curated（专家校验过）| proposal（未确认，禁止训练）
  "file_path": "backend-service/data/labeled_datasets/lds-pv-0007.parquet",  // 项目根相对路径
  "content_sha256": "…",                      // 内容指纹，保证不可变
  "row_count": 41280,                         // 原始时序行数
  "unit_count": 287,                          // 诊断单元数（不是行数）
  "label_space_version": "ls-v5",             // 引用 label_registry，保证 label_id 语义稳定
  "label_distribution": { "正常": 201, "组串遮挡": 52, "二极管击穿": 34 },
  "dataset_contract": {                       // 字段角色映射，模板复用靠它
    "entity_keys": ["site_id","device_id","branch_id"],  // 实体主键角色
    "time": "time",                                      // 时间列角色
    "measures": ["value","i_cal"],                       // 数值测点角色
    "label": "label",                                    // 标签列角色
    "window_key": "time_window",                         // 诊断窗口键角色
    "expected_freq": "5min",                             // 期望采样频率
    "expected_points_per_day": 288                       // 单日期望点数
  },
  "provenance": {                             // 血缘：这份真值是谁定的
    "proposal_id": "prop-a3f2c8d19b40",       // 来自哪个标签提案（聚类路径）
    "review_session_ids": ["rev-…"],          // 经过哪些专家校验会话
    "reviewers": ["zhangsan"],
    "confirmed_at": "2026-08-25T…",
    "parent_dataset_version_id": "lds-pv-0006"  // 上一版，形成版本链
  }
}
```

三块的边界因此变干净：

- 模板 A 只写 `proposal`，**不允许写 `curated`**
- 专家工作台是**唯一**能把 `proposal` → `curated` 的地方
- 模板 B 只读 `curated`，**读不到 `proposal`**

#### 抽象 3：人工环节不进画布

写进产品定义。画布是**无状态 DAG 批处理**，专家校验是**有状态长会话**（可中断、可多人、可回退、要 IAA 一致性）。硬塞进画布会同时毁掉两边。

画布只负责两个接口点：**产出提案** 和 **消费数据集**。中间那段用独立工作台，两边靠 `proposal_id` / `dataset_version_id` 握手。

### 4.3 模板 A 的算子清单

**只需**新增 3 个算子（`cluster_k_search` / `cluster_profile` / `emit_label_proposal`）+ 修 4 个命名孪生（`kmeans` / `dbscan` / `agglomerative_clustering` / `pca`），其余全用现货。

| 环节 | 算子 | 状态 |
|---|---|---|
| 加载 | `load_csv` / `load_parquet` | ✅ 现货 |
| 切诊断单元 | `time_window_split`（`window` 参数决定粒度：`1d` / `12h` / `1w`） | ✅ 现货 |
| 清洗 | `handle_missing` / `detect_outliers` | ✅ 现货 |
| 特征 | `extract_statistical_features` / `tsfresh_extract` / `ts_comparison_features` | ✅ 现货 |
| **标准化** | `z_score_scale` / `min_max_scale` | ✅ 现货（**现有硬编码流程缺这步**，见 5.2 问题 1） |
| 降维 | `pca` | ⚠️ 已实现但**被命名孪生埋掉**，需先修 ID 对齐（见 3.1） |
| **k 选择** | `cluster_k_search` | 🆕 新增：扫 k 范围、调 `silhouette_score` 打分选优 |
| 聚类 | `gmm_cluster` / `hdbscan_cluster` / `optics_cluster` | ✅ 现货，ID 已对齐，画布可直接用 |
| 聚类 | `kmeans` / `dbscan` / `agglomerative_clustering` | ⚠️ 已实现但**被命名孪生埋掉**，需先修 ID 对齐（见 3.1） |
| **簇画像** | `cluster_profile` | 🆕 新增：每簇代表成员 + 代表波形 + 特征分布，给专家看 |
| **产出提案** | `emit_label_proposal` | 🆕 新增：**核心**，落成 `label_proposal` 工件，是画布到工作台的出口 |

收益正是「通用化」：用户能自己换聚类算法、自己选特征、自己决定诊断单元粒度，而不是被 `create_clustering_run()` 里焊死的那套绑住。

### 4.4 模板 B 的补充算子

模板本身已有（见 2.4），需要补两个接口算子：

| 新增算子 | 作用 | 为什么必要 |
|---|---|---|
| `load_labeled_dataset` | 按 `dataset_version_id` 加载专家校验数据集，自动带出 `dataset_contract` | 现在换数据集要在 **7 个节点**手改字段映射（见 3.3）。有了它，换数据集只换一个 ID |
| `emit_prediction_batch` | 把画布预测结果落成 `prediction_batch`，进人工复核队列 | 现在预测批次是 `iterative_labeling` 侧单独写的（`data/iterative_labeling/prediction_batches/{slot}/*.json`），画布跑出来的预测**进不了复核队列**，闭环断在这里 |

补上之后闭环通路：

```
模板 B 预测 → emit_prediction_batch
  → POST /review-sessions/from-prediction（已有）
  → 专家复核（已有 SHAP / 相似案例 / 参考波形 / IAA）
  → POST /review-sessions/{id}/backfill-to-dataset（已有）
  → LabeledDatasetVersion v2 → 回模板 B 重训
```

### 4.5 诊断路径三分（而非二分）

现有 `modeling_path ∈ {legacy_day, seq_annotation}` 表达不了「实时」场景。建议按**时效语义**命名，用户一眼能选对：

| 建议路径名 | 语义 | 输出粒度 | 触发时机 | 现状 |
|---|---|---|---|---|
| `daily_batch`（日级批诊断） | 一天一条记录的诊断单元 | 天级标签 | 每日封日后 | ✅ 已有（原 `legacy_day`）+ 已上画布 |
| `daily_pointwise`（全天逐点复盘） | 288 点整天，出故障段 | 逐点 + 故障段 | 数据水位跨日、占用率 ≥ 90% | ✅ 已有（原 `seq_annotation`）❌ 未上画布 |
| `intraday_rolling`（日内滚动告警） | 最近 N 点滑窗增量推理 | 逐点告警 + 段合并 | 每 5 / 15 分钟 | ❌ **全新** |

第三条**不必新训模型**——直接复用 `services/iterative_labeling/tsc/` 里的 `SlidingWindowSampler` + `TSCModelWrapper`，它本来就是滑窗分类范式。需要新写的是三件事：

1. **部分日推理入口**：`predict_device_window(df, window_length, stride)`，绕开 `predict_device_day()` 的「单自然日 + 288 完整」硬约束
2. **告警状态机**：`alarm_state`（设备当前告警态）、`alarm_dedup_key`（同一故障段不重复告警）、`clear_confirm_points`（连续 N 点正常才消警）。这是实时场景真正的难点，不是模型
3. **与 `daily_pointwise` 的对账**：日内告警「快而可能错」，全天复盘「慢而准」。产品上明确复盘结论**覆盖**日内告警并留修订记录——这套机制 `seq_device_day_ledger` 的 `revision_pending`（待修订状态）+ `supersedes_batch_id`（被取代批次标识）已实现，直接复用

---

## 5. 后续需要调整修改的清单

### 5.1 P0 —— 接上断掉的桥（改动最小、体感最强）

不需要新抽象，三件事：

| # | 改什么 | 文件 |
|---|---|---|
| 1 | `confirm_clustering_run()` 追加一次画布侧数据集注册，让专家校验产出在画布 `load_csv` 数据集下拉里能选到 | `backend-service/services/iterative_labeling/pv_training_workspace.py` + `backend-service/api/iterative_labeling.py` |
| 2 | 确认成功后加「用这份数据集去画布诊断」按钮，跳 `/workflow/editor?template=…&dataset_version_id=…` | `frontend-sevice/src/pages/DatasetPage.tsx` |
| 3 | 顺手修聚类的两个算法问题（见 5.2 问题 1、2） | `pv_training_workspace.py` 的 `create_clustering_run()` |

做完这一步，四步链路**当天能端到端跑通**，只是打标那段还是硬编码。

### 5.2 P0 —— 聚类初标的算法缺陷

| # | 问题 | 位置 | 修法 |
|---|---|---|---|
| 1 | **聚类前不做标准化**。`numeric_cols` 直接喂 `kmeans_execute()`。特征是 `value_mean` / `value_std` / `value_min` / `value_max` / `i_cal_*`，量级差一到两个数量级，KMeans 欧氏距离**被最大尺度列主导**，`std` 这类小量级特征基本不起作用 | `create_clustering_run()` | 插 `z_score_scale`；拆成画布模板后由用户自选 |
| 2 | **ID 列可能被当特征聚类**。`numeric_cols` 按 `dtype in (np.float64, np.int64, float, int)` 筛。若 `branch_id` 在数据里是整数，它会被当聚类特征 —— 等于按支路编号聚类 | 同上 | 改成从 `dataset_contract.measures` 显式取列 |
| 3 | **k 靠人手填，没有选择依据**。前端两处硬编码 `n_clusters: 5`；`silhouette_score` 算子已实现但没被用上 | `DatasetPage.tsx`、`IterativeLabelingListPage.tsx` | 新增 `cluster_k_search` 算子 |
| 4 | **给专家看的信息不够**。只有 `representative_stats`（各数值列簇内均值），没有波形。专家判断「这个簇是什么故障」主要靠波形 | `create_clustering_run()` | 新增 `cluster_profile` 算子；复用 `GET /reference-waveforms` 的呈现方式 |

### 5.3 P0 —— 生产安全

| # | 改什么 | 文件 |
|---|---|---|
| 5 | 给 `_switch_simple()` 加环境守卫（仅非生产环境可用），前端两处 `switch_mode:'simple'` 改走完整九项门控 | `services/scheduler/pv_dual_path/cross_path_switch_coordinator.py`、`pages/PvDualPathConsole.tsx`、`pages/accuracy-operations/PvFaultModelingPathOpsPanel.tsx` |
| 6 | `modeling-paths` / `register-model` / `switch-fallback` 三个写接口加鉴权（**spec 已列为上线阻断项；实施需显式授权**） | `backend-service/api/iterative_labeling.py` |

### 5.4 P0 —— 算子货架诚实度

| # | 改什么 | 文件 |
|---|---|---|
| 7 | `functions.json` 加 `implementation_status` 字段（`available` / `planned`）；由 `OperatorRouter.list_operators()` 动态标注，不手维护 817 条。前端对 `planned` 置灰 + 不可拖 + 悬浮说明 | `backend-service/api/functions.py`、`frontend-sevice/src/components/workflow-enhanced/NodeLibraryPanelV2.tsx` |
| 8 | **修 15 个命名孪生**（见 3.1 表格）。两种改法二选一：把 `functions.json` 的 ID 改成实现侧的名字，或在实现侧补 `OPERATOR_ID` 别名注册。优先 `kmeans` / `dbscan` / `agglomerative_clustering` / `pca` —— **打标签模板直接依赖这四个** | `backend-service/data/functions.json` 或 `services/operator_backends/{kmeans,dbscan,agglomerative_clustering,pca}.py` |
| 9 | 启用已写好的 `portTypeValidation.ts`：给 `EnhancedCanvas` 的 `ReactFlow` 传 `isValidConnection`。死代码变活代码 | `frontend-sevice/src/components/workflow-enhanced/EnhancedCanvas.tsx` |

### 5.5 P1 —— `LabeledDatasetVersion` 统一

| # | 改什么 |
|---|---|
| 10 | 把三套数据集概念收敛成一个工件 + 一张注册表（schema 见 4.2 抽象 2） |
| 11 | `confirm_clustering_run()` 也分配 `dataset_version_id`，与 `BackfillService._allocate_dataset_version()` 统一格式 |
| 12 | 扩 `GlobalConfigInjector._PROMOTED_FIELDS`，把 `entity_keys` / `time_field` / `measure_fields` / `label_field` / `window_key` 下发给每个算子。算子保留节点级覆盖（现有 `setdefault` 语义是对的），但**默认不用填** |
| 13 | 改 `POST /datasets/switch`：从「只改 `file_path`」升级为「改 `file_path` + 校验新数据集列是否满足 `dataset_contract`，缺哪个角色报哪个角色」 |
| 14 | 给 PV 补 `data_contracts.py` 条目：至少 `pv_raw_measurement`（原始测点）、`pv_windowed`（切窗后）、`pv_feature_matrix`（特征矩阵）、`pv_diagnosis_result`（诊断结果）四条 |

### 5.6 P1 —— 打标签变成真模板

| # | 改什么 |
|---|---|
| 15 | 新增 `cluster_k_search` / `cluster_profile` / `emit_label_proposal` 三个算子 |
| 16 | 用它们拼出模板 A（`workflow-pv-labeling-cluster-v1.json`），把 `create_clustering_run()` 的逻辑搬到画布 |
| 17 | `pv_training_workspace.py` 那条 REST 路径保留为「快捷模式」，兼容现有前端，不破坏已有交互 |

### 5.7 P1 —— 闭环 + 两段式校验

| # | 改什么 |
|---|---|
| 18 | 新增 `load_labeled_dataset` / `emit_prediction_batch` 两个算子 |
| 19 | 补 `backfill_to_raw_dataset()` 的非预测入口。现在它强制要求 `prediction_context.source_csv_path`，缺了就抛 `ValueError` 提示「请通过 from-prediction 接口创建会话」——**首次聚类打标这条路走不了这个回流接口** |
| 20 | 加「簇级 → 单元级」两段式衔接：对 silhouette 低 / 成员数异常 / 专家标记可疑的簇，自动开单元级 review session 精修，两级结果合并后才升级为 `curated`。现在簇级只能「选/不选成员」，改不了单个成员的标签，而一个簇里必然有杂质 |
| 21 | 合并前端两份重复的聚类打标交互（`DatasetPage.tsx` / `IterativeLabelingListPage.tsx`） |

### 5.8 P2 —— 第三条路径（实时）

| # | 改什么 |
|---|---|
| 22 | `predict_device_window()` 部分日推理入口（`seq_annotation/predictor.py`） |
| 23 | 告警状态机：`alarm_state` / `alarm_dedup_key` / `clear_confirm_points` |
| 24 | 日内告警与全天复盘的修订对账（复用 `seq_device_day_ledger` 的 `revision_pending` + `supersedes_batch_id`） |
| 25 | 真实生产采集入口。现在只预留了 `data_source='production'`，实际采集未接；`load_mqtt` / `load_kafka` / `load_opcua` 都是空壳 |

### 5.9 P2 —— 工程收敛

| # | 改什么 |
|---|---|
| 26 | 拆 `api/workflows_enhanced.py`（13970 行 / 71 端点），至少把数据集管理、AutoResearch、回测拆出去 |
| 27 | spec 三份副本收敛到一处（建议 `.kiro/specs/` 为真源，`docs/specs/` 与 `docs/pv_fault/spec/` 改为引用） |
| 28 | 前端 IA 瘦身：清理 9 个未接路由的页面组件，合并成对重复页 |
| 29 | `precision_ops` 与 `accuracy_operations` 二选一 |
| 30 | 对齐 spec 勾选状态与实际代码。`pv-fault-timeseries-diagnosis/tasks.md` 34 项全未勾选，但 `services/iterative_labeling/tsc/` 下 14 个文件已实现；`accuracy-operations/tasks.md` 50 项全未勾选，但 `services/accuracy_operations/` 已存在 |

---

## 6. 本文档的验证边界

以下内容**必须**在实施前自行确认，本文档未做运行验证：

- 全部结论来自**静态读码**。未启动后端或前端，未跑 `pytest`，未跑 `npm run build`，未执行过任何一次真实的聚类 run 或画布执行
- **「693 个空壳算子」**是 `functions.json` 的 `id` 集合与 `operator_backends/` 各模块行首 `OPERATOR_ID` 集合做差得出。如果存在本次未发现的第二套算子注册途径（如运行时别名映射），这个数字会偏大
- **3.1 的「命名孪生」对应关系是按 ID 字符串相似度推断的**，逐对语义等价性未逐个读码确认。特别是 `classification_report` ↔ `confusion_matrix_eval` 这一对相似度较低，实施前需读两侧代码确认是否真的同义；其余 14 对（如 `kmeans` ↔ `kmeans_cluster`）语义应无争议
- **「两套数据集注册表不通」**是从 `DatasetPage.tsx` 无 `registerDataset` 调用 + `confirm_clustering_run()` 只调 `CumulativeTrainingService` 推出的。如果存在未发现的第三条同步路径，结论会变
- **「`portTypeValidation.ts` 是死代码」**基于全仓库 grep `portTypeValidation|isPortTypeCompatible|DataContractTooltip`，仅命中定义处
- `docs/specs/pv-fault-dual-path-serving/tasks.md` 显示 161 项已勾选 / 11 项未勾选，未勾选的是 Task 2~11（ORM 迁移、逐日账本仓储、启用周期服务、PV 模型登记唯一可写真相、九项切换门控、部署演习场只读适配）。**这批正好是治理收敛部分，也就是 5.3 问题的根因**——实施 5.3 时需先确认这些任务的真实完成度

---

## 7. 建议的实施顺序

```
第 1 步（止血 + 打通）：5.1 全部 + 5.2 问题1/2 + 5.3 问题5 + 5.4 问题7/8/9
                        → 四步链路端到端可跑，画布不再骗人，生产不再能被一键改
                        （问题 8 修命名孪生，同时为第 3 步的打标签模板解锁 kmeans/dbscan/pca）

第 2 步（地基）：5.5 全部
                → LabeledDatasetVersion 统一，模板复用换数据集只换一个 ID

第 3 步（打标成模板）：5.6 全部 + 5.2 问题3/4
                → 用户能在画布上自建打标方法

第 4 步（闭环）：5.7 全部
                → 诊断结果能回流成下一版数据集

第 5 步（实时）：5.8 全部

第 6 步（收敛）：5.9 全部
```
<!-- @AI_GENERATED: end -->
