<!-- @AI_GENERATED -->
# 需求文档：基于 AIP 通用算子填充实现光伏故障诊断流水线

## 简介

本文档定义了将光伏故障诊断算法（`fault-diag-algo-release-3.1`）的各步骤逻辑**映射并填充到 AIP 平台通用算子**中的功能需求。核心思路与负荷预测集成一致：**复用已有通用算子 + 新增分类场景专用算子**，为每个算子实现真实的后端执行逻辑，使光伏故障诊断流水线可以通过组合通用算子来运行。

**与负荷预测集成的关键差异：**

| 维度 | 负荷预测 | 光伏故障诊断 |
|------|----------|-------------|
| 任务类型 | 回归（预测连续值） | 分类（多类别故障识别） |
| 数据粒度 | 单时间序列 | 多设备/多支路批量时序 |
| 特征工程 | 滚动统计 + 滞后特征 | 窗口聚合统计 + 多变量对比 + tsfresh |
| 特征选择 | 无（全量输入） | mRMR Top-K |
| 类别平衡 | 不需要 | SMOTE 过采样 |
| 模型 | XGBoost 回归 | 随机森林分类 |
| 评估指标 | SMAPE/MAE/RMSE | Accuracy/Precision/Recall/F1 |

**可直接复用的已有算子（5 个，仅需填充后端执行逻辑）：**
- `load_csv` — 数据加载（已在负荷预测中填充）
- `random_forest_classifier`（id: `random_forest_classifier`，category: classification）— 随机森林分类，已注册，支持自动调参
- `smote_oversample`（id: `smote_oversample`，category: data_preprocessing）— SMOTE 过采样，已注册
- `label_encode`（id: `label_encode`，category: data_preprocessing）— 标签编码，已注册
- `precision_recall_f1` / `confusion_matrix` / `f1_score`（category: evaluation_metrics）— 分类评估指标，已注册

**需扩展已有算子的（4 个，新增方法或模式）：**
- `detect_outliers` — 需新增 `robust_clip` 方法（鲁棒裁剪）
- `handle_missing` — 需新增 `drop_insufficient` 方法（丢弃不足组）
- `feature_select`（id: `feature_select`，已支持 `mutual_info`/`f_test`/`importance`）— 需新增 `mrmr` 方法
- `extract_statistical_features` / `tsfresh_extract` — 需扩展"按设备分组+窗口聚合"模式

**真正需要新增注册的算子（3 个）：**
- `time_window_split` — 时间窗口切分（按诊断窗口分组，与已有 `sliding_window` 语义不同：后者是滑动窗口生成样本，前者是固定周期分组）
- `ts_comparison_features` — 多变量对比特征（Spearman/Pearson 相关、欧氏距离、DTW 距离、线性回归斜率）
- `batch_predict_classifier` — 批量分类预测（分批执行+失败重试编排逻辑）

## 术语表

- **Generic_Operator（通用算子）**: AIP 平台 `functions.json` 中已注册的通用功能算子，可被任意工作流复用
- **Operator_Backend（算子后端）**: 通用算子对应的 Python 执行逻辑
- **Pipeline_Template（流水线模板）**: 由多个通用算子按特定顺序组合而成的工作流模板
- **Diagnosis_Window（诊断窗口）**: 将连续时序数据按固定时间长度（如 1d/1w）切分为独立诊断单元的配置参数
- **Device_Hierarchy（设备层级）**: 光伏电站的设备拓扑结构 `site_id` → `device_id` → `branch_id`（支路可选）
- **Label_Map（标签映射）**: 将业务标签（如 `"suite-0"`）映射为数值类别（如 `20`）的字典，支持训练时编码和预测时反映射
- **Window_Aggregation（窗口聚合）**: 将一个诊断窗口内的多条时序记录聚合为单条特征向量的过程（每个设备×窗口产出一行特征）
- **mRMR（最小冗余最大相关）**: 特征选择算法，从高维特征空间中选择与目标最相关且彼此最不冗余的 Top-K 特征
- **SMOTE（合成少数过采样技术）**: 对少数类样本进行合成过采样，解决分类任务中类别不平衡问题
- **Data_Contract（数据契约）**: 算子间传递数据的格式规范

## 需求

### 需求 1：数据加载与标签合并 — load_csv + label_encode

**用户故事：** 作为平台用户，我想使用已有的 `load_csv` 算子加载光伏设备时序数据和标签数据，并通过已有的 `label_encode` 算子完成标签清洗和映射，以便为后续故障诊断流水线提供带标签的训练数据。

#### 验收标准

1. WHEN 用户配置 `load_csv` 算子加载光伏设备数据, THE Operator_Backend SHALL 读取包含 `time`、`site_id`、`device_id`（可选 `branch_id`）和多个数值测量列的 CSV/Parquet 文件，返回 MATRIX 类型 DataFrame
2. WHEN 用户配置 `label_encode` 算子并通过 `options` 提供 `label_map` JSON, THE Operator_Backend SHALL 将标签列中的业务标签按映射字典转换为数值类别（如 `"suite-0"` → `20`）
3. THE `label_encode` Operator_Backend SHALL 扩展支持 `mode` 参数：`encode`（训练时标签编码）和 `decode`（预测时标签反映射），原有行为保持不变
4. THE `label_encode` Operator_Backend SHALL 校验 `label_map` 无重复值；IF 存在重复映射, THEN 返回参数校验错误
5. THE `label_encode` Operator_Backend SHALL 将无法映射的标签标记为 `-1`，并在仅剩 `-1` 类别时报错

### 需求 2：时间窗口切分算子 — time_window_split

**用户故事：** 作为平台用户，我想使用 `time_window_split` 算子将连续时序数据按可配置的诊断窗口（如 1 天、1 周）切分为独立的诊断单元，以便每个设备在每个时间窗口内作为一个独立样本进行特征提取和分类。

#### 验收标准

1. WHEN 用户配置 `time_window_split` 算子并指定 `window` 参数（如 `"1d"`、`"1w"`）, THE Operator_Backend SHALL 为每条记录分配一个 `time_window` 标识，与原始算法 `set_time_window` 等价
2. THE `time_window_split` Operator_Backend SHALL 支持 `m`（分钟）、`h`（小时）、`d`（天）、`w`（周）四种时间单位
3. THE `time_window_split` Operator_Backend SHALL 通过 `id_fields` 参数配置分组维度（默认 `["site_id", "device_id", "branch_id"]`），按设备层级独立切分
4. THE `time_window_split` Operator_Backend SHALL 自动检测数据中存在的层级列（如无 `branch_id` 则忽略），与原始算法 `__get_structure` 逻辑等价
5. THE `time_window_split` Operator_Backend SHALL 在输入 DataFrame 上新增 `time_window`（datetime）列并返回

### 需求 3：数据清洗算子扩展 — detect_outliers（鲁棒裁剪模式）

**用户故事：** 作为平台用户，我想在通用 `detect_outliers` 算子中使用"鲁棒裁剪"模式，即通过滚动差分去除每组数据的极端最大值和最小值，以便复用负荷预测已有的异常检测算子同时适配光伏场景的需求。

#### 验收标准

1. WHEN 用户配置 `detect_outliers` 算子并指定 `method` 为 `robust_clip`, THE Operator_Backend SHALL 对每组数据按差分排序后去除首尾极值，与 `DataCleaner.get_robust_data` 等价
2. THE `detect_outliers` Operator_Backend 的 `robust_clip` 模式 SHALL 按 `id_fields` 分组独立处理每组数据
3. THE `detect_outliers` Operator_Backend 的 `robust_clip` 模式 SHALL 仅在组内数据量 > 24 时执行裁剪（与原始算法条件一致）
4. 已有的 `zscore`、`iqr`、`isolation_forest` 方法不受影响

### 需求 4：缺失值处理算子扩展 — handle_missing（丢弃模式）

**用户故事：** 作为平台用户，我想在通用 `handle_missing` 算子中使用"丢弃不足"模式，即丢弃有效值不足指定比例的数据组，以便适配光伏故障诊断中数据质量过滤的需求。

#### 验收标准

1. WHEN 用户配置 `handle_missing` 算子并指定 `method` 为 `drop_insufficient`, THE Operator_Backend SHALL 丢弃各特征有效值比例低于 `keep_threshold`（默认 0.75）的数据组，与 `DataCleaner.check_missing` 等价
2. THE `handle_missing` Operator_Backend 的 `drop_insufficient` 模式 SHALL 按 `id_fields` 分组，以各特征非空计数的中位数为参考长度
3. THE `handle_missing` Operator_Backend 的 `drop_insufficient` 模式 SHALL 通过 `keep_threshold` 参数控制保留阈值（默认 0.75）
4. 已有的 `linear`、`ffill`、`bfill`、`mean` 方法不受影响

### 需求 5：时序统计特征提取 — extract_statistical_features + tsfresh_extract（扩展分组聚合模式）

**用户故事：** 作为平台用户，我想使用已有的 `extract_statistical_features` 和 `tsfresh_extract` 算子从分组时序数据中提取丰富的统计特征，需要扩展它们支持"按设备×窗口分组聚合"的模式，以便在故障诊断等分类场景中复用。

#### 验收标准

1. WHEN 用户配置 `extract_statistical_features` 算子并在 `options` 中指定 `mode` 为 `"groupby_aggregate"`, THE Operator_Backend SHALL 按 `id_fields` 分组，对每组的 `value_fields` 计算以下统计特征：max、min、mean、median、std、kurtosis、skew、max-min（极差）、变异系数、均值以上占比
2. THE `extract_statistical_features` Operator_Backend 的 `groupby_aggregate` 模式 SHALL 支持 `quantiles` 参数（默认 `[0.15, 0.25, 0.35, 0.65, 0.75, 0.85, 0.95]`），计算各分位数特征
3. THE `extract_statistical_features` Operator_Backend 的 `groupby_aggregate` 模式 SHALL 计算自相关特征（lag-1/2/3），与原始算法 `autocorrelation_1/2/3` 等价
4. WHEN 用户配置 `tsfresh_extract` 算子并在 `options` 中指定 `id_fields`, THE Operator_Backend SHALL 按分组计算 tsfresh 特征：`abs_energy`、`sum_values`、`benford_correlation`、`absolute_sum_of_changes`、`first/last_location_of_maximum/minimum`、`CID`、`variance_larger_than_standard_deviation`
5. THE `extract_statistical_features` Operator_Backend 的 `groupby_aggregate` 模式 SHALL 计算波动/平坦特征（flatness detection），与原始算法 `get_features` 等价
6. THE `extract_statistical_features` Operator_Backend 的 `groupby_aggregate` 模式 SHALL 支持 `compute_diff`（默认 `true`）参数，启用时对差分数据重复计算基础统计特征
7. THE Operator_Backend SHALL 仅在组内平均数据量 ≥ 48 时计算分位数特征（与原始算法条件一致）
8. THE Operator_Backend SHALL 输出 MATRIX，每行对应一个分组（设备×窗口），列为所有提取的特征
9. 已有的 `extract_statistical_features` 非 `groupby_aggregate` 模式行为不受影响

### 需求 6：多变量对比特征算子 — ts_comparison_features

**用户故事：** 作为平台用户，我想使用 `ts_comparison_features` 算子计算多个数值变量之间的相关性和距离特征（Spearman/Pearson 相关、欧氏距离、DTW 距离、线性回归斜率），以便在多传感器设备的故障诊断中捕捉变量间的异常关系。

#### 验收标准

1. WHEN 用户配置 `ts_comparison_features` 算子且输入数据包含多个 `value_fields`, THE Operator_Backend SHALL 对所有变量两两组合计算对比特征，与 `FeatureEngineer.get_compare_features` 等价
2. THE `ts_comparison_features` Operator_Backend SHALL 计算以下对比特征：
   - Spearman 相关系数
   - Pearson 相关系数
   - 欧氏距离
   - DTW（动态时间规整）距离
   - 线性回归斜率
   - 差值序列的 max、std、median、absolute_sum_of_changes、sum_values
3. THE `ts_comparison_features` Operator_Backend SHALL 按 `id_fields` 分组独立计算
4. IF 输入数据仅有单个 `value_field`, THEN THE Operator_Backend SHALL 跳过对比特征计算并返回空 DataFrame（不报错）
5. THE `ts_comparison_features` Operator_Backend SHALL 输出 MATRIX，与 `ts_statistical_features` 的输出行索引对齐，可直接合并

### 需求 7：特征选择 — feature_select（扩展 mRMR 方法）

**用户故事：** 作为平台用户，我想在已有的 `feature_select` 算子中使用 mRMR 方法从高维特征空间中选择最有价值的 Top-K 特征，以便降低模型复杂度、提升泛化性能。

#### 验收标准

1. WHEN 用户配置 `feature_select` 算子并指定 `method` 为 `mrmr`、`k` 参数（默认 50）, THE Operator_Backend SHALL 使用 mRMR（最小冗余最大相关）算法从输入特征中选择 Top-K 特征，与 `FeatureEngineer.select_features` 等价
2. THE `feature_select` Operator_Backend SHALL 接收 `features`（MATRIX）和 `target`（ARRAY，分类标签）作为输入
3. THE `feature_select` Operator_Backend SHALL 返回 OBJECT，包含：
   - `selected_features`（MATRIX）：筛选后的特征矩阵
   - `feature_list`（ARRAY）：选中的特征名列表，供预测时复用
4. IF 选择结果为空（如所有特征与目标无相关性）, THEN THE Operator_Backend SHALL 返回错误信息
5. THE `feature_select` Operator_Backend SHALL 支持 `mode` 参数：`fit`（训练时计算并返回 feature_list）和 `transform`（预测时按已有 feature_list 筛选）
6. 已有的 `mutual_info`、`f_test`、`importance` 方法不受影响

### 需求 8：SMOTE 类别平衡 — smote_oversample（填充后端逻辑）

**用户故事：** 作为平台用户，我想使用已有的 `smote_oversample` 算子对训练数据进行少数类过采样，以便解决光伏故障诊断中正常样本远多于故障样本的类别不平衡问题。

#### 验收标准

1. WHEN 用户配置 `smote_oversample` 算子, THE Operator_Backend SHALL 对输入的训练特征和标签执行 SMOTE 过采样，与原始算法 `smote` 函数等价
2. THE `smote_oversample` Operator_Backend SHALL 支持 `limit` 参数（默认 500），限制每个少数类的最大合成样本数
3. THE `smote_oversample` Operator_Backend SHALL 返回平衡后的 `features`（MATRIX）和 `target`（ARRAY）
4. IF SMOTE 执行失败（如某类样本数过少）, THEN THE Operator_Backend SHALL 退回原始数据并记录 warning 日志（不中断流水线）

### 需求 9：随机森林分类器 — random_forest_classifier（填充后端逻辑）

**用户故事：** 作为平台用户，我想使用已有的 `random_forest_classifier` 算子训练随机森林分类模型，以便在光伏故障诊断、设备状态识别等多类别分类场景中复用。

#### 验收标准

1. WHEN 用户配置 `random_forest_classifier` 算子并提供 `train_features`（MATRIX）和 `train_target`（ARRAY）, THE Operator_Backend SHALL 训练 sklearn RandomForestClassifier 模型
2. THE `random_forest_classifier` Operator_Backend SHALL 支持以下参数：`n_estimators`（默认 80）、`random_state`（默认 90）、`n_jobs`（默认 -1）
3. THE `random_forest_classifier` Operator_Backend SHALL 返回 OBJECT，包含：
   - `model`（OBJECT）：训练好的模型对象
   - `feature_importances`（ARRAY）：特征重要性数组
4. WHEN 用户指定 `mode` 为 `predict` 并提供 `model` 和 `predict_features`, THE Operator_Backend SHALL 使用模型预测并返回 `predictions`（ARRAY，int 类型类别标签）
5. THE `random_forest_classifier` Operator_Backend SHALL 在训练前自动将标签转换为一维数组（`ravel()`）

### 需求 10：分类评估指标 — precision_recall_f1 + confusion_matrix（填充后端逻辑）

**用户故事：** 作为平台用户，我想使用已有的 `precision_recall_f1` 和 `confusion_matrix` 算子计算分类任务的精度指标，以便评估故障诊断模型的分类性能。

#### 验收标准

1. WHEN 用户配置 `precision_recall_f1` 算子并提供 `y_true`（ARRAY）和 `y_pred`（ARRAY）, THE Operator_Backend SHALL 计算 Accuracy、macro-Precision、macro-Recall、macro-F1 四个指标
2. THE `precision_recall_f1` Operator_Backend SHALL 返回 OBJECT，包含 `accuracy`、`precision`、`recall`、`f1` 四个 float 值
3. THE `precision_recall_f1` Operator_Backend SHALL 支持 `average` 参数（默认 `macro`），可选 `micro`、`weighted`
4. WHEN 用户配置 `confusion_matrix` 算子, THE Operator_Backend SHALL 返回混淆矩阵（MATRIX）和分类报告（STRING）供详细分析
5. IF `y_true` 和 `y_pred` 长度不一致, THEN THE Operator_Backend SHALL 返回参数校验错误

### 需求 11：批量分类预测算子 — batch_predict_classifier

**用户故事：** 作为平台用户，我想使用 `batch_predict_classifier` 算子对大量设备进行分批故障预测，支持失败重试机制，以便在生产环境中稳健地完成大规模批量诊断。

#### 验收标准

1. WHEN 用户配置 `batch_predict_classifier` 算子并提供模型和预测数据, THE Operator_Backend SHALL 按 `batch_size`（默认 10000 个对象）分批执行预测，与原始算法批量预测逻辑等价
2. THE `batch_predict_classifier` Operator_Backend SHALL 对失败批次自动拆分为单对象逐条重试
3. THE `batch_predict_classifier` Operator_Backend SHALL 返回 OBJECT，包含：
   - `predictions`（MATRIX）：包含 id_fields + `predict_label` 列的结果
   - `failure_count`（NUMBER）：失败对象数量
4. THE `batch_predict_classifier` Operator_Backend SHALL 在日志中记录每批的处理数量和耗时

### 需求 12：光伏故障诊断训练流水线模板

**用户故事：** 作为平台用户，我想在工作流编辑器中一键加载"光伏故障诊断训练"流水线模板，以便快速搭建完整的故障诊断训练工作流。

#### 验收标准

1. THE Workflow_Editor SHALL 在模板列表中提供"光伏故障诊断训练"模板，由以下算子按顺序组成：
   `load_csv`（源数据） + `load_csv`（标签数据） → `label_encode`（encode） → `time_window_split` → `handle_missing`（drop_insufficient） → `detect_outliers`（robust_clip） → `extract_statistical_features`（groupby_aggregate） + `tsfresh_extract` + `ts_comparison_features` → `feature_select`（mrmr, fit） → `smote_oversample` → `random_forest_classifier`（train） → `precision_recall_f1` + `confusion_matrix`
2. WHEN 用户选择该模板, THE Workflow_Editor SHALL 自动创建所有算子节点并建立数据流连线
3. THE Pipeline_Template SHALL 为每个算子预填充光伏故障诊断场景的推荐默认参数：
   - `time_window_split`：`window` = `"1d"`，`id_fields` = `["site_id", "device_id", "branch_id"]`
   - `handle_missing`：`method` = `"drop_insufficient"`，`keep_threshold` = `0.75`
   - `detect_outliers`：`method` = `"robust_clip"`
   - `extract_statistical_features`：`mode` = `"groupby_aggregate"`，`compute_diff` = `true`，`quantiles` = `[0.15, 0.25, 0.35, 0.65, 0.75, 0.85, 0.95]`
   - `feature_select`：`method` = `"mrmr"`，`k` = `50`，`mode` = `"fit"`
   - `smote_oversample`：`limit` = `500`
   - `random_forest_classifier`：`n_estimators` = `80`，`mode` = `"train"`
4. WHEN 模板加载完成, THE Workflow_Editor SHALL 允许用户修改任意算子参数后再执行

### 需求 13：光伏故障诊断预测流水线模板

**用户故事：** 作为平台用户，我想在工作流编辑器中加载"光伏故障诊断预测"流水线模板，以便使用已训练的模型对新数据进行批量故障诊断。

#### 验收标准

1. THE Workflow_Editor SHALL 在模板列表中提供"光伏故障诊断预测"模板，由以下算子组成：
   `load_csv`（预测数据） → `time_window_split` → `handle_missing`（drop_insufficient） → `detect_outliers`（robust_clip） → `extract_statistical_features`（groupby_aggregate） + `tsfresh_extract` + `ts_comparison_features` → `feature_select`（mrmr, transform） → `batch_predict_classifier` → `label_encode`（decode）
2. THE 预测流水线模板 SHALL 要求用户指定 `model_id` 参数以加载已训练的模型
3. THE 预测流水线模板 SHALL 要求用户指定 `feature_list` 参数（从训练流水线的 `feature_select` 输出获取）
4. THE `label_encode`（decode 模式）SHALL 将数值预测标签反映射为业务标签 ID

### 需求 14：算子间数据契约规范

**用户故事：** 作为平台用户，我想保证光伏故障诊断流水线中每个算子的输出格式与下游算子的输入格式完全匹配，以便流水线能够端到端运行。

#### 验收标准

1. THE Pipeline_Template SHALL 为每对相邻算子定义 Data_Contract：
   - **load_csv → label_encode**：输出 MATRIX，必含 `time`（datetime）、`site_id`（str）、`device_id`（str）列 + 标签列
   - **label_encode → time_window_split**：输出 MATRIX，标签列已转为 int，新增 `label`（int）列
   - **time_window_split → handle_missing**：输出 MATRIX，新增 `time_window`（datetime）列
   - **handle_missing → detect_outliers**：输出 MATRIX，已丢弃不足组，数值列类型为 float
   - **detect_outliers → extract_statistical_features**：输出 MATRIX，极值已裁剪为 NaN
   - **extract_statistical_features → feature_select**：输出 MATRIX，每行一个分组，列为特征名，附带 `label`（int）列
   - **feature_select → smote_oversample**：输出 OBJECT，含 `selected_features`（MATRIX，float）和 `target`（ARRAY，int）
   - **smote_oversample → random_forest_classifier**：输出 OBJECT，含 `features`（MATRIX，float）和 `target`（ARRAY，int）
   - **random_forest_classifier → precision_recall_f1**：输出 OBJECT，含 `predictions`（ARRAY，int）；评估算子接收 `y_true`（ARRAY）和 `y_pred`（ARRAY）
2. THE Schema_Validator SHALL 在每个算子执行完成后校验输出是否符合 Data_Contract

### 需求 15：光伏故障诊断业务参数（options 扩展）

**用户故事：** 作为平台用户，我想在通用算子上配置光伏故障诊断特有的业务参数（如诊断窗口、设备类型、标签映射等），以便在不修改通用算子定义的前提下适配光伏场景。

#### 验收标准

1. WHEN 用户从光伏故障诊断模板加载工作流, THE Pipeline_Template SHALL 为算子的 `options` 字段预填充以下默认值：
   - **load_csv** options：`{"time_field": "time", "id_fields": ["site_id", "device_id", "branch_id"], "scene": "solar", "device_type": "combinerbox"}`
   - **time_window_split** options：`{"diagnosis_window": "1d", "window_one_label": 1, "time_zone": "Asia/Shanghai"}`
   - **ts_statistical_features** options：`{"compute_diff": true, "compute_quantile": true, "compute_autocorrelation": true, "compute_tsfresh": true, "compute_flatness": true}`
   - **ts_comparison_features** options：`{"compute_correlation": true, "compute_distance": true, "compute_regression": true}`
   - **random_forest_classifier** options：`{"n_estimators": 80, "random_state": 90}`
2. THE Operator_Config_Panel SHALL 为 Domain_Options 中的每个字段提供中文标签：
   - `diagnosis_window`：标签"诊断窗口"，文本输入框，默认 `"1d"`
   - `window_one_label`：标签"窗口统一标签"，开关，默认开启
   - `scene`：标签"场景"，下拉选择 `solar`（光伏）/ `wind`（风电），默认 `solar`
   - `device_type`：标签"设备类型"，下拉选择 `combinerbox`（汇流箱）/ `inverter`（逆变器），默认 `combinerbox`
   - `time_zone`：标签"时区"，下拉选择，默认 `Asia/Shanghai`
   - `compute_diff`：标签"计算差分特征"，开关，默认开启
   - `compute_quantile`：标签"计算分位数特征"，开关，默认开启

### 需求 16：算子注册（functions.json 新增 3 个算子）

**用户故事：** 作为平台开发者，我想将光伏故障诊断所需的 3 个新算子注册到 `functions.json`，以便它们出现在工作流编辑器的函数库面板中，用户可拖拽使用。

#### 验收标准

1. THE Operator_Registry SHALL 新增以下 3 个算子定义到 `functions.json`，归属相应 `category`：
   - `time_window_split`（category: `data_preprocessing`）— 按诊断窗口将时序数据分组，每个设备×窗口为一个独立诊断单元
   - `ts_comparison_features`（category: `feature_engineering`）— 多变量对比特征：Spearman/Pearson/DTW/欧氏距离/回归斜率
   - `batch_predict_classifier`（category: `model_training`）— 批量分类预测：分批执行+失败重试
2. 每个新算子定义 SHALL 包含完整的 `parameters`、`return_type`、`description`（中英文）和 `category`
3. THE Workflow_Editor SHALL 在刷新后自动展示新注册的算子，无需修改前端代码
4. 以下已有算子无需新增注册，仅需填充或扩展后端执行逻辑：
   - `random_forest_classifier`（已有，category: classification）
   - `smote_oversample`（已有，category: data_preprocessing）
   - `label_encode`（已有，category: data_preprocessing）— 扩展 decode 模式
   - `precision_recall_f1` + `confusion_matrix`（已有，category: evaluation_metrics）
   - `feature_select`（已有，category: data_preprocessing）— 扩展 mrmr 方法
   - `extract_statistical_features`（已有，category: feature_engineering）— 扩展 groupby_aggregate 模式
   - `tsfresh_extract`（已有，category: feature_engineering）— 扩展分组模式
   - `detect_outliers`（已有）— 扩展 robust_clip 方法
   - `handle_missing`（已有）— 扩展 drop_insufficient 方法
