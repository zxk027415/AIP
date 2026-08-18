# Implementation Plan: 光伏故障诊断算法 AIP 平台集成

## Overview

将 `fault-diag-algo-release-3.1` 光伏故障诊断算法封装到 AIP 平台通用算子框架中。包括：新增 3 个算子注册（`time_window_split`、`ts_comparison_features`、`batch_predict_classifier`），扩展 4 个已有算子新方法，填充 5 个已有算子后端逻辑，以及创建训练和预测两套流水线模板。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "tasks": [1, 6]
    },
    {
      "wave": 2,
      "tasks": [2, 3, 4, 7, 8, 9]
    },
    {
      "wave": 3,
      "tasks": [5, 10]
    },
    {
      "wave": 4,
      "tasks": [11, 12]
    },
    {
      "wave": 5,
      "tasks": [13]
    },
    {
      "wave": 6,
      "tasks": [14]
    }
  ]
}
```

## Tasks

- [x] 1. 注册 3 个新算子到 functions.json
  - 在 `functions.json` 中追加 `time_window_split` 算子定义（category: data_preprocessing），包含 window、id_fields、time_field 三个参数
  - 在 `functions.json` 中追加 `ts_comparison_features` 算子定义（category: feature_engineering），包含 id_fields、value_fields、options 三个参数
  - 在 `functions.json` 中追加 `batch_predict_classifier` 算子定义（category: model_training），包含 batch_size、id_fields 两个参数
  - 每个定义包含完整的 name、name_en、description、parameters、return_type、examples 字段
  - **Files:** `backend-service/data/functions.json`
  - **Requirements:** 需求 16

- [x] 2. 实现 time_window_split 算子后端
  - 依赖: task 1
  - 创建 `time_window_split.py`，实现 `execute(params, inputs)` 标准接口
  - 实现 `_parse_freq()` 频率字符串解析（m→t, w→w-mon 映射），支持 m/h/d/w 四种单位
  - 实现自动检测实际存在的 id_fields（过滤掉 DataFrame 中不存在的列）
  - 实现按设备分组 + resample + merge_asof 分配 time_window 核心逻辑（移植 `fault-diag-algo-release-3.1/enos_fault_diag/utils/time.py` 的 `set_time_window`）
  - 在 operator_execution 框架中注册 `time_window_split` 路由
  - **Files:** `backend-service/services/operator_backends/time_window_split.py`
  - **Requirements:** 需求 2

- [x] 3. 实现 ts_comparison_features 算子后端
  - 依赖: task 1
  - 创建 `ts_comparison_features.py`，实现 `execute(params, inputs)` 标准接口
  - 实现 Spearman/Pearson 相关系数计算（使用 scipy.stats）
  - 实现欧氏距离和 DTW 距离计算（使用 numpy 和 tslearn.metrics.dtw）
  - 实现线性回归斜率计算
  - 实现差值序列统计（max, std, median, absolute_sum_of_changes, sum_values）
  - 实现按 id_fields 分组 + itertools.combinations 两两配对编排逻辑（移植 `fault-diag-algo-release-3.1/enos_fault_diag/features/feature_engineer.py` 的 `get_compare_features`）
  - 处理单变量情况（跳过对比特征，返回空 DataFrame，不报错）
  - **Files:** `backend-service/services/operator_backends/ts_comparison_features.py`
  - **Requirements:** 需求 6

- [x] 4. 实现 batch_predict_classifier 算子后端
  - 依赖: task 1
  - 创建 `batch_predict_classifier.py`，实现 `execute(params, inputs)` 标准接口
  - 实现按 batch_size（默认 10000）分批预测逻辑
  - 实现失败批次自动拆分为单对象逐条重试的容错机制
  - 返回 OBJECT（predictions DataFrame 含 id_fields + predict_label，以及 failure_count）
  - 添加每批处理数量和耗时的日志记录
  - **Files:** `backend-service/services/operator_backends/batch_predict_classifier.py`
  - **Requirements:** 需求 11

- [x] 5. 扩展已有算子 — detect_outliers 新增 robust_clip + handle_missing 新增 drop_insufficient
  - 依赖: task 2
  - 在 `detect_outliers.py` 中新增 `robust_clip` method 分支：按差分排序去首尾极值（移植 `DataCleaner.get_robust_data`），仅在组内数据量 > 24 时执行
  - 在 `handle_missing.py` 中新增 `drop_insufficient` method 分支：丢弃非空比例低于 keep_threshold（默认 0.75）的数据组（移植 `DataCleaner.check_missing`）
  - 确保已有方法（zscore/iqr/isolation_forest 和 linear/ffill/bfill/mean）不受影响，不修改原有逻辑分支
  - **Files:** `backend-service/services/operator_backends/detect_outliers.py`, `backend-service/services/operator_backends/handle_missing.py`
  - **Requirements:** 需求 3, 需求 4

- [x] 6. 扩展 feature_select — 新增 mRMR 方法
  - 在 `feature_select.py` 中新增 `mrmr` method 分支
  - 实现 fit 模式：调用 `mrmr_classif(X, y, K=k)` 计算特征，返回 selected_features + feature_list + target
  - 实现 transform 模式：按已有 feature_list 筛选 DataFrame 列，不重新计算
  - 处理 K > 可用特征数的边界情况（取 min(k, len(columns))）
  - 处理选择结果为空的错误（抛出 ValueError）
  - 确保已有的 mutual_info、f_test、importance 方法不受影响
  - **Files:** `backend-service/services/operator_backends/feature_select.py`
  - **Requirements:** 需求 7

- [x] 7. 扩展 extract_statistical_features — 新增 groupby_aggregate 模式
  - 依赖: task 6
  - 在 `extract_statistical_features.py` 中新增 `groupby_aggregate` mode 分支
  - 实现基础统计分组聚合（max/min/mean/median/std/kurtosis/skew/极差/变异系数/均值以上占比）
  - 实现分位数特征（条件：avg_count ≥ 48，quantiles 参数默认 [0.15, 0.25, 0.35, 0.65, 0.75, 0.85, 0.95]）
  - 实现自相关特征 lag-1/2/3
  - 实现波动/平坦特征（flatness detection，移植 `features/utils/fluctuation.py` 的 `get_features`）
  - 实现 compute_diff 开关（默认 true）：对差分数据重复计算基础统计
  - 输出 MATRIX：每行对应一个分组（设备×窗口），列为所有提取特征，fillna(0) 处理空值
  - **Files:** `backend-service/services/operator_backends/extract_statistical_features.py`
  - **Requirements:** 需求 5

- [x] 8. 扩展 tsfresh_extract — 新增分组聚合模式
  - 依赖: task 6
  - 在 `tsfresh_extract.py` 中支持 id_fields 参数，按分组计算 tsfresh 特征
  - 实现 abs_energy、sum_values、benford_correlation、absolute_sum_of_changes 计算（使用 tsfresh.feature_extraction.feature_calculators）
  - 实现 first/last_location_of_maximum/minimum 计算
  - 实现 CID 和 variance_larger_than_standard_deviation 计算
  - 确保输出 MATRIX 的行索引（MultiIndex by id_fields）与 extract_statistical_features 输出对齐，可直接 pd.concat
  - **Files:** `backend-service/services/operator_backends/tsfresh_extract.py`
  - **Requirements:** 需求 5

- [x] 9. 填充已有算子后端 — smote_oversample + label_encode
  - 依赖: task 6
  - 创建/填充 `smote_oversample.py`：实现 SMOTE 过采样，支持 limit 参数（默认 500）限制少数类最大合成数
  - 实现 SMOTE 失败时 fallback 到原始数据并记录 warning 日志（不中断流水线）
  - 创建/填充 `label_encode.py`：实现 encode 模式（label_map 字符串→int 正向映射，不可映射设为 -1）
  - 实现 decode 模式（int→字符串反向映射，通过 label_map 取反）
  - 实现 label_map 重复值校验（重复映射值时报 ValueError）
  - 实现全 -1 类别检测（全部映射失败时报错）
  - **Files:** `backend-service/services/operator_backends/smote_oversample.py`, `backend-service/services/operator_backends/label_encode.py`
  - **Requirements:** 需求 1, 需求 8

- [x] 10. 填充已有算子后端 — random_forest_classifier + precision_recall_f1 + confusion_matrix
  - 依赖: task 7, task 8, task 9
  - 创建/填充 `random_forest_classifier.py`：实现 train 模式（fit sklearn RandomForestClassifier，返回 model + feature_importances）
  - 实现 predict 模式（model.predict 返回 predictions ARRAY，int 类型）
  - 支持 n_estimators（默认 80）、random_state（默认 90）、n_jobs（默认 -1）参数
  - 创建/填充 `precision_recall_f1.py`：计算 accuracy、precision、recall、f1，支持 average 参数（默认 macro）
  - 创建/填充 `confusion_matrix.py`：返回混淆矩阵 MATRIX 和 classification_report STRING
  - 实现 y_true/y_pred 长度不一致时的参数校验错误
  - **Files:** `backend-service/services/operator_backends/random_forest_classifier.py`, `backend-service/services/operator_backends/precision_recall_f1.py`, `backend-service/services/operator_backends/confusion_matrix.py`
  - **Requirements:** 需求 9, 需求 10

- [x] 11. 创建训练流水线模板 JSON
  - 依赖: task 5, task 10
  - 创建 `workflow-pv-fault-diag-training-v1.json`，包含 14 个节点（load_csv×2、label_encode、time_window_split、handle_missing、detect_outliers、extract_statistical_features、tsfresh_extract、ts_comparison_features、feature_select、smote_oversample、random_forest_classifier、precision_recall_f1、confusion_matrix）
  - 定义完整的 edges 连线（含并行特征提取分支汇聚到 feature_select 的连线）
  - 为每个节点预填充推荐默认参数（time_window_split: window=1d，handle_missing: drop_insufficient，detect_outliers: robust_clip，feature_select: method=mrmr k=50，random_forest_classifier: n_estimators=80）
  - 定义 metadata.global_config（time_zone: Asia/Shanghai，scene: solar，device_type: combinerbox）
  - **Files:** `backend-service/data/workflows_enhanced/workflow-pv-fault-diag-training-v1.json`
  - **Requirements:** 需求 12

- [x] 12. 创建预测流水线模板 JSON
  - 依赖: task 5, task 10
  - 创建 `workflow-pv-fault-diag-prediction-v1.json`，包含完整的预测流水线节点和 edges
  - 预留 model_id 参数位置（random_forest_classifier 的模型输入）
  - 预留 feature_list 参数位置（feature_select transform 模式的输入）
  - 最后一步使用 label_encode decode 模式反映射数值标签为业务标签
  - **Files:** `backend-service/data/workflows_enhanced/workflow-pv-fault-diag-prediction-v1.json`
  - **Requirements:** 需求 13

- [x] 13. 为两套模板定义算子间数据契约
  - 依赖: task 11, task 12
  - 为训练模板每条 edge 在 JSON 中添加 data_contract 字段（required_columns、column_types、constraints）
  - 为预测模板每条 edge 添加 data_contract 字段
  - 覆盖 9 对相邻算子的契约（参见 design.md Data Models 中的 Schema 表格）
  - **Files:** `backend-service/data/workflows_enhanced/workflow-pv-fault-diag-training-v1.json`, `backend-service/data/workflows_enhanced/workflow-pv-fault-diag-prediction-v1.json`
  - **Requirements:** 需求 14

- [x] 14. 端到端集成测试
  - 依赖: task 13
  - 创建 `test_pv_fault_diag_operators.py`，使用 `fault-diag-algo-release-3.1/enos_fault_diag/test/` 下的 parquet 测试数据
  - 验证训练流水线端到端：load_csv 读取数据 → label_encode → time_window_split → handle_missing → detect_outliers → 特征提取 → feature_select → smote_oversample → random_forest_classifier → precision_recall_f1 完整跑通，无报错
  - 验证预测流水线端到端：load_csv → 清洗 → 特征提取 → feature_select transform → batch_predict_classifier → label_encode decode 完整跑通
  - 验证正确性属性：标签 encode→decode 双向一致、特征行数等于唯一分组数、批量预测 |predictions|+failure_count==|inputs|、SMOTE 后少数类样本数单调递增
  - 运行 pytest 确认所有测试通过
  - **Files:** `backend-service/tests/test_pv_fault_diag_operators.py`
  - **Requirements:** 需求 12, 需求 13

## Notes

- 所有算子后端实现均遵循 `execute(params: dict, inputs: dict) -> dict` 统一接口
- 扩展已有算子时只追加新 method/mode 分支，不修改原有逻辑，保证向后兼容
- tsfresh、tslearn、mrmr-selection、scipy 等依赖在 `conda env aip_web` 中已有，无需新增
- 测试数据来自 `fault-diag-algo-release-3.1/enos_fault_diag/test/` 下的 parquet 文件（train_small.parquet、label_small.parquet、predict_small.parquet）
