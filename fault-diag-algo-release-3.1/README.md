# fault-diag-algo — 光伏故障诊断算法

## 项目简介

光伏电站设备故障诊断算法系统，基于时序数据特征工程 + 随机森林分类器，实现光伏汇流箱/逆变器等设备的多类别故障自动识别。

**核心能力：**

- 对光伏设备（如汇流箱）的时序运行数据进行清洗、特征提取和故障分类
- 支持多站点（23+ 光伏电站）、多层级（站点/设备/支路）设备的批量诊断
- 可配置诊断时间窗口（如 1 天/1 周），支持标签映射和类别自定义
- 训练产物通过 MLflow 管理，部署为 REST 推理服务

## 目录结构

```
fault-diag-algo-release-3.1/
├── README.md
├── .gitignore
├── .gitlab-ci.yml                   # CI/CD 流水线（precommit + postcommit + sonar）
├── pipelines/
│   ├── faultDig-aiSuite-train.json  # EAP/AI Suite 训练流水线定义
│   └── faultDig-aiSuite-pred.json   # EAP/AI Suite 预测流水线定义
└── enos_fault_diag/                 # 算法核心包
    ├── __init__.py
    ├── config.json                  # 站点配置（站点ID → [站点名, 发电小时数]）
    ├── fault_main.py                # 训练入口（MLflow 模型类 + CLI）
    ├── fault_diagnosis.py           # 核心算法编排（数据初始化 → 特征 → 训练 → 预测）
    ├── fault_output.py              # 预测结果写回数据集
    ├── setup.py                     # 包安装定义
    ├── requirements_fault_main.txt  # 训练依赖
    ├── requirements_fault_output.txt# 输出模块依赖
    ├── data_cleaning/
    │   ├── data_cleaner.py          # 数据清洗：缺失值检测 + 异常值鲁棒处理
    │   └── utils/                   # 清洗工具集
    ├── features/
    │   ├── feature_engineer.py      # 特征工程核心：统计特征 + 差分特征 + 对比特征 + 分位数 + 平坦检测
    │   └── utils/                   # 特征辅助函数
    │       ├── correlation.py       # 自相关、Spearman/Pearson 相关系数
    │       ├── euclidean.py         # 欧氏距离
    │       ├── fluctuation.py       # 波动特征（平坦区间检测）
    │       ├── lin_reg.py           # 线性回归斜率
    │       ├── normalizer.py        # 归一化
    │       ├── statistics.py        # 均值比、极差、CID 等统计量
    │       ├── theoretical_current.py # 理论电流计算
    │       └── variation_coefficient.py # 变异系数
    ├── models/
    │   ├── rnd_fst.py               # 随机森林分类器（含 SMOTE 过采样）
    │   └── utils/
    │       └── smote.py             # SMOTE 少数类过采样
    ├── test/                        # 测试数据和测试脚本
    │   ├── test.py
    │   ├── train_small.parquet
    │   ├── label_small.parquet
    │   ├── predict_small.parquet
    │   ├── result_dataset.parquet
    │   └── ...
    └── utils/
        ├── aggregator.py            # 数据分组聚合
        ├── exception.py             # 自定义异常（ParamException / AlgoException）
        ├── log.py                   # 日志初始化
        ├── log.yaml                 # 日志配置
        └── time.py                  # 时间工具（时区转换、频率解析、时间窗口切分）
```

## 算法流程

### 训练（Train）

```
原始时序数据 + 标签数据
    ↓
1. 参数校验（label_map、diagnosis_window、window_one_label）
    ↓
2. 数据解析（从 EAP Dataset 读取源数据、标签、历史修正结果）
    ↓
3. 训练数据初始化
   - 标签清洗 & 映射（label_map 将业务标签转换为数值类别）
   - 合并标签与源数据（merge_asof 按时间对齐）
   - 诊断时间窗口切分（按 diagnosis_window 分组）
    ↓
4. 数据清洗（DataCleaner）
   - 缺失值检测：丢弃不足 75% 有效值的样本片段
   - 异常值处理：滚动差分后去极值（鲁棒裁剪）
    ↓
5. 特征工程（FeatureEngineer）
   - 基础统计特征：max, min, mean, median, std, kurtosis, skew, max-min
   - 变异系数、均值以上占比、分位数特征（15%/25%/35%/65%/75%/85%/95%）
   - 自相关特征（lag-1/2/3）
   - tsfresh 特征：abs_energy, sum_values, benford_correlation,
     absolute_sum_of_changes, 极值位置特征, CID, 方差>标准差
   - 波动/平坦特征（fluctuation）
   - 差分数据的基础统计特征
   - 多变量对比特征：Spearman/Pearson 相关、欧氏距离、DTW 距离、线性回归斜率
    ↓
6. 特征选择（mRMR，Top-50）
    ↓
7. 模型训练
   - SMOTE 过采样（平衡少数类，上限 500）
   - 随机森林分类器（n_estimators=80, random_state=90）
    ↓
8. 模型保存（MLflow pyfunc 格式，含 conda 环境定义）
```

### 预测（Predict）

```
指定时间范围 + 预测数据集
    ↓
1. 参数解析（predict_dataset, start_time, end_time）
    ↓
2. 数据加载 & 时间窗口切分
    ↓
3. 批量预测（每 10000 对象一批）
   - 数据清洗 → 特征工程 → 模型推理
   - 失败批次单独重试（逐对象级别）
    ↓
4. 结果汇总 & 标签反映射（predict_label → predict_label_id）
    ↓
5. 结果写回数据集（fault_output.py，支持有/无支路两种拓扑）
```

## 核心类和函数

| 类/函数 | 文件 | 职责 |
|---------|------|------|
| `MlflowFaultDiagnosis` | `fault_main.py` | MLflow 模型封装：参数解析、数据集读取、训练/预测入口 |
| `FaultDiagnosis` | `fault_diagnosis.py` | 算法编排：数据初始化 → 特征工程 → 训练 → 预测 |
| `DataCleaner` | `data_cleaning/data_cleaner.py` | 数据清洗：缺失检测 + 异常值鲁棒处理 |
| `FeatureEngineer` | `features/feature_engineer.py` | 特征提取：统计/差分/对比/分位数/平坦 + mRMR 选择 |
| `RandomForest` | `models/rnd_fst.py` | 随机森林训练/预测（含 SMOTE 过采样） |

## 数据层级

系统支持的设备层级结构：

- `site_id` — 光伏电站（如"寿光光伏电站"）
- `device_id` — 设备（如逆变器）
- `branch_id` — 支路（可选，如汇流箱支路）

## 关键参数

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `task_id` | 任务标识 | `"0919"` |
| `diagnosis_window` | 诊断时间窗口 | `"1d"`（支持 m/h/d/w） |
| `window_one_label` | 窗口内是否统一一个标签 | `1`（当前仅支持 1） |
| `label_map` | 标签映射字典 | `{"suite-0": 20, "0": 0, ...}` |
| `time_zone` | 时区 | `"Asia/shanghai"` |
| `scene` | 场景 | `"solar"` |
| `device_type` | 设备类型 | `"combinerbox"` |

## 故障类别

通过 `label_map` 配置支持多类别故障分类，当前已定义 30+ 种故障类型，涵盖：

- 基础类别（0–17）：通用设备状态标签
- AI Suite 类别（suite-0 ~ suite-17）：EnOS AI Suite 平台业务标签

## 部署方式

### EAP/AI Suite 流水线

项目通过 `pipelines/` 下的 JSON 定义部署到 EnOS AI Suite 平台：

- **训练流水线** (`faultDig-aiSuite-train.json`)：
  - PythonEx 算子 → Model 注册 → Mlflow Model Version Register
  - 训练产物保存为 MLflow pyfunc 模型

- **预测流水线** (`faultDig-aiSuite-pred.json`)：
  - ParamParser → Latest Model Version → Mlflow Model Version Prediction → ResultWriter + TopologyNumWriter

### 运行环境

- Python 3.x
- 关键依赖：scikit-learn 0.24.2, tsfresh 0.19.0, tslearn 0.5.2, mrmr-selection 0.2.5, mlflow 1.13.1
- 数据接口：eapdataset (EnOS 数据集 SDK)

## 测试

```bash
cd enos_fault_diag
nosetests -s -x --with-coverage --cover-package=.
```

测试数据位于 `enos_fault_diag/test/`，包含 parquet 格式的小规模训练/标签/预测数据集。

## CI/CD

GitLab CI 流水线（`.gitlab-ci.yml`）：

- **precommit**：依赖安装 + nosetests 单元测试
- **postcommit**（master/release 分支）：测试 + SonarQube 代码扫描 + 版本标签更新 + 安全扫描

## 与 AIP 平台集成方向

本算法适合封装为 AIP 平台的标准算子和流水线模板，复用通用算子框架：

- **数据清洗**：复用 `detect_outliers`、`handle_missing` 等通用算子
- **特征工程**：可封装为 `ts_feature_extraction`（时序统计特征）通用算子
- **模型训练**：封装为 `random_forest_classifier`（随机森林分类器）通用算子
- **故障分类**：封装为 `fault_diagnosis` 场景模板，组合上述算子

详见 AIP 平台集成 spec。


---

## 算法原理详解

### 业务背景

光伏电站包含成百上千个**汇流箱**，每个汇流箱有多条**支路**（branch），每条支路串联若干光伏组件。设备每 5-15 分钟上报一次电流（`i_cal`）和电压（`value`）。

**问题**：设备故障（组串遮挡、开路、短路等）靠人工巡检发现，效率低、延迟高。

**目标**：从时序数据中自动识别每个设备每天的运行状态属于哪种故障类型 —— 实现"每天一个诊断结论"。

### 故障类型说明

| 标签 | 故障名称 | 电气特征 |
|------|---------|---------|
| 0 | 正常/待定 | 电流正常波动，符合光照曲线 |
| 1 | 组串遮挡 | 白天部分时段电流骤降（阴影遮蔽） |
| 4 | 直流侧异常 | 电压异常偏移，不符合预期 V-I 关系 |
| 7 | 汇流箱告警 | 轻微电流异常，接近正常但有波动 |
| 8 | 汇流箱故障 | 电流长时间为 0 或持续异常 |
| 11 | 组串开路 | 电流持续为 0（物理断路） |
| 12 | 组串短路 | 电流异常偏高（超出正常范围） |
| 16 | 其他故障 | 不属于以上模式的异常行为 |

### 流程各步骤详解

#### 步骤 1：数据合并（merge_label）

- **做什么**：把 15 分钟粒度的时序测量数据（57385 行）和日粒度的标签数据（272 行）按 `设备 + 日期` 对齐
- **为什么**：标签是"某设备某天的故障类型"，需要让每条时序记录知道自己属于哪个故障
- **核心逻辑**：`pd.merge(source, label, on=[id_fields, date], how='left')` → 丢弃无标签行
- **输出**：每行新增 `label`（int）列

#### 步骤 2：时间窗口切分（time_window_split）

- **做什么**：按 `1d`（1 天）为一个诊断单元，给每条记录打上 `time_window` 标签
- **为什么**：算法的粒度是"每设备×每天 → 一个诊断结论"。一天约 96 个数据点聚合为一个样本
- **核心逻辑**：`pd.resample('1d', label='left') + merge_asof` — 对齐到当天 00:00
- **输出**：新增 `time_window`（datetime）列

#### 步骤 3：数据质量过滤（handle_missing → drop_insufficient）

- **做什么**：丢弃有效值不足 75% 的设备×窗口组
- **为什么**：如果某设备某天只上报了不到 72 条有效数据（96×75%），特征提取不可靠
- **核心逻辑**：
  ```
  各列非空计数的中位数 × 0.75 = 最低保留阈值
  低于阈值的组 → 整组丢弃
  ```
- **输出**：行数可能减少，剩余的都是高质量诊断窗口

#### 步骤 4：异常值处理（detect_outliers → robust_clip）

- **做什么**：对每组数据按差分排序，去除极端最大值和最小值
- **为什么**：传感器偶发跳变（如通信错误导致 -999）会严重影响统计特征
- **核心逻辑**：
  ```
  diff = value.diff()
  按 diff 排序 → 首行 + 末两行的 value 设为 NaN
  ```
- **条件**：只在组内数据量 > 24 时执行（太少不做）
- **输出**：极端跳跃值被替换为 NaN

#### 步骤 5：特征工程（核心步骤）

将一个设备一天内的 96 条时序记录 → 压缩为一行约 70 个特征值。分三大类：

**5a. 基础统计特征**

| 特征 | 含义 | 区分力 |
|------|------|--------|
| max / min / mean / median / std | 分布描述 | 开路时 max≈0，正常 max>5A |
| kurtosis（峰度） | 分布尖锐程度 | 遮挡时有尖峰 |
| skew（偏度） | 分布对称性 | 故障时分布偏移 |
| max-min（极差） | 波动范围 | 正常日变化大，故障波动小 |
| 变异系数（std/mean） | 相对波动 | 短路时稳定在高位 |
| 均值以上占比 | 高于均值比例 | 遮挡时多数时间偏低 |
| 分位数（15%~95%） | 分布形状 | 捕捉不同故障的分布差异 |
| 自相关 lag-1/2/3 | 时序相关性 | 正常=强自相关，故障打断相关性 |
| 平坦特征（flat_rate/flat_max） | 电流不变时长 | 开路=高平坦率 |
| tsfresh 特征 | 信息论/复杂度 | abs_energy/benford/CID 等 |

**5b. 差分特征**

对 `value.diff()`（变化量）重复计算基础统计。差分反映"变化速率" —— 正常光照渐变（差分小），故障突变（差分大）。

**5c. 多变量对比特征**

`value`（电压）和 `i_cal`（电流）两者的关系：

| 特征 | 含义 | 区分力 |
|------|------|--------|
| Spearman/Pearson 相关 | 电压电流是否同步 | 正常=强正相关，故障相关性下降 |
| 欧氏距离 | 曲线整体差异 | 短路时电流偏高→距离大 |
| DTW 距离 | 形态相似度 | 捕捉非线性形态差异 |
| 线性回归斜率 | V-I 线性关系 | 正常有固定的 V-I 比例 |
| 差值统计 | value-i_cal 的统计量 | 两者偏离程度 |

#### 步骤 6：特征选择（mRMR Top-K）

- **做什么**：从 70+ 特征中选出最有价值的 Top-20（或 50）
- **为什么**：减少过拟合、去除冗余（如 max 和 quantile_95 高度相关）
- **mRMR 原理**：
  ```
  最大化：特征与标签的相关性（Relevance）
  最小化：已选特征之间的冗余（Redundancy）
  贪心迭代：每轮选"与标签最相关 + 与已选最不冗余"的特征
  ```
- **输出**：`feature_list` + 筛选后的特征矩阵

#### 步骤 7：类别平衡（SMOTE 过采样）

- **做什么**：对少数类合成新样本，使每类达到 300 条
- **为什么**：原始数据类别极不平衡（类 7 有 200+，类 12 可能只有 5 条），不平衡会导致模型偏向多数类
- **SMOTE 原理**：
  ```
  1. 找到少数类样本 A
  2. 找 A 的最近邻 B（同类）
  3. 在 A-B 连线上随机取点 → 新合成样本
  ```
- **输出**：每类 300 条，总计平衡数据集

#### 步骤 8：模型训练（随机森林）

- **算法**：80 棵决策树的集成
- **训练过程**：
  ```
  1. 从样本中随机有放回抽样 → 建一棵树
  2. 每次分裂只考虑 √(特征数) 个随机特征 → 降低树之间相关性
  3. 重复 80 次
  4. 预测时 80 棵树投票，多数票胜出
  ```
- **优势**：不需标准化、抗过拟合、可输出特征重要性、训练/推理速度快

### 评估指标说明

| 指标 | 含义 | 怎么看 |
|------|------|--------|
| **Accuracy** | 整体正确率 | 99% = 每 100 个诊断只错 1 个 |
| **Precision（精确率）** | 预测为故障的有多少是真故障 | 低 → 误报多（正常被误判为故障）|
| **Recall（召回率）** | 真故障中有多少被发现 | 低 → 漏报多（故障没被检出）|
| **F1 Score** | Precision 和 Recall 的调和平均 | 综合指标 |
| **macro-F1** | 所有类别 F1 的等权平均 | **最重要** — 不受类别不平衡影响 |
| **混淆矩阵** | 行=真实，列=预测 | 对角线亮=好，非对角线=误分类方向 |

**运维重点关注**：

- **Recall 比 Precision 更重要** — 漏掉故障比误报更严重
- **类别 11（组串开路）的 Recall** — 开路不及时发现导致发电损失
- **类别 0 和 7 的混淆** — "正常"和"告警"容易混淆

### 精度解读

当前测试数据精度 ~99.5%，原因：

1. 光伏设备不同故障的电流模式差异很大（开路=0、短路=超高、正常=光照曲线）
2. 特征工程充分提取了这些差异
3. SMOTE 平衡后各类样本充足

**真实上线精度会下降**的场景：
- 新站点/新设备型号（训练没见过的模式）
- 季节变化（冬夏光照曲线不同）
- 新故障类型（训练集没有的类别）
- 解决方案：持续积累标签数据 + 定期重训练


---

## 本地代码 vs AIP 平台集成：差距与对齐状态

### 已完全对齐的部分 ✅

| 流程步骤 | 本地代码 | AIP 平台算子 | 状态 |
|---------|---------|-------------|------|
| 数据合并 | `MlflowFaultDiagnosis.init_train_data()` — merge_asof 按时间对齐 | `merge_label` 算子 — 按设备+日期 merge | ✅ 等价 |
| 时间窗口切分 | `utils/time.py` → `set_time_window()` | `time_window_split` 算子 | ✅ 完全移植 |
| 缺失值过滤 | `DataCleaner.check_missing()` | `handle_missing(method='drop_insufficient')` | ✅ 完全移植 |
| 异常值裁剪 | `DataCleaner.get_robust_data()` | `detect_outliers(method='robust_clip')` | ✅ 完全移植 |
| 基础统计特征 | `FeatureEngineer.get_basic_features()` | `extract_statistical_features(mode='groupby_aggregate')` | ✅ 等价 |
| 差分特征 | `FeatureEngineer.get_diff_data()` + 统计 | `extract_statistical_features(compute_diff=true)` | ✅ 等价 |
| 分位数特征 | `FeatureEngineer.get_quantile_features()` | `extract_statistical_features(quantiles=[...])` | ✅ 等价 |
| 自相关特征 | `autocorrelation_1/2/3` | `extract_statistical_features` 内置 | ✅ 等价 |
| 平坦/波动特征 | `fluctuation.get_features()` | `extract_statistical_features` 内置 | ✅ 等价 |
| 多变量对比特征 | `FeatureEngineer.get_compare_features()` | `ts_comparison_features` 算子 | ✅ 完全移植 |
| mRMR 特征选择 | `FeatureEngineer.select_features()` | `feature_select(method='mrmr')` | ✅ 等价 |
| SMOTE 过采样 | `models/utils/smote.py` | `smote_oversample` 算子 | ✅ 等价逻辑 |
| 随机森林训练 | `RandomForest.train()` | `random_forest_classifier(mode='train')` | ✅ 等价 |
| 批量预测 | `fault_main.py` predict 循环 | `batch_predict_classifier` 算子 | ✅ 等价（分批+重试） |
| 标签映射/反映射 | `parse_label()` + `label_map` | `label_encode(mode='encode'/'decode')` | ✅ 等价 |
| 模型持久化 | MLflow pyfunc + conda env | pickle 序列化到 `data/models/` | ✅ 功能等价（格式不同） |

### 存在差异的部分 ⚠️

| 差异点 | 本地代码 | AIP 平台当前实现 | 影响 | 后续计划 |
|--------|---------|-----------------|------|---------|
| **tsfresh 特征数量** | 使用 `tsfresh_extract` 计算完整特征集（含 benford_correlation 等） | 同样使用 tsfresh，但计算的特征子集略少（10 个 vs 原始代码更多） | 特征名不完全一致，不能直接加载 sklearn 0.24 训练的旧模型 | 低优先级：已经重新训练，精度一致 |
| **特征命名规则** | `value_nanmax`、`value_i_cal_eu_dist`、`diff_value_i_cal_nanmedian` | `value_max`、`value_i_cal_euclidean`、`value_diff_max` | 旧模型 feature_list 无法直接用于新算子输出 | 不影响：每次训练会产出新 feature_list |
| **sklearn 版本** | 0.24.2 | 1.8.0 | 旧 pickle 模型无法反序列化（Tree 结构不兼容） | 不影响：AIP 上用新版本重新训练 |
| **数据合并逻辑** | `merge_asof` + `result_table`（历史修正标签合并） | 仅 `merge(on=[id_fields, date])` — 没有 result_table 合并 | 若有"人工修正标签"数据，当前会被忽略 | 中优先级：需要加 result_table 支持 |
| **模型保存格式** | MLflow pyfunc + conda env（可注册为 REST 服务） | pickle 直接序列化到磁盘 | AIP 不支持 MLflow 模型注册和在线推理服务 | 中优先级：后续对接 MLflow 或 AIP 模型管理 |
| **预测数据源** | 通过 `eapdataset` SDK 从在线数据集实时拉取 | 从本地文件/CSV 加载 | AIP 暂不对接 EnOS 在线数据服务 | 后续：对接 `load_api` 或 `load_database` 算子 |
| **结果写回** | `fault_output.py` 通过 `eapdataset` 写回 Hive/数据库 | 仅在前端展示，不写回外部存储 | 生产部署需要写回能力 | 后续：对接 `data_output` 类算子 |
| **训练评估方式** | 不做离线评估，依赖线上人工审核 | SMOTE 后 shuffle + 80/20 split 评估 | AIP 精度指标是"同分布验证"，不代表跨时间泛化能力 | 已知局限：生产环境需定期重训 |
| **诊断窗口灵活性** | 支持 `window_one_label=0`（窗口内多标签） | 仅支持 `window_one_label=1`（窗口统一标签） | 当前不影响，原始代码也只跑 =1 | 低优先级 |

### 尚未实现的本地代码功能 ❌

| 功能 | 本地代码位置 | 说明 | 优先级 |
|------|------------|------|--------|
| 时区转换 | `set_time_zone()` | 原始代码中有 TODO 标记，实际被注释未启用 | 低（当前不影响） |
| 理论电流计算 | `features/utils/theoretical_current.py` | 根据辐照度计算理论电流，用于和实际值对比 | 中（需要辐照度数据源） |
| 在线数据集接入 | `eapdataset.Dataset.get_by_name()` | 从 EnOS 平台实时拉取数据 | 高（生产部署需要） |
| 定时调度 | AI Suite 流水线 CRON | 每天自动执行预测 + 写回 | 高（生产部署需要） |
| 拓扑数量写回 | `TopologyNumWriter` | 预测后更新设备拓扑统计到 MySQL | 低 |
| MLflow 模型版本管理 | `Mlflow Model Version Register` | 模型版本注册、灰度发布 | 中 |

### 精度对比

| 维度 | 本地代码 | AIP 平台 |
|------|---------|---------|
| 训练数据 | `train_small.parquet`（57k 行） | 同 |
| 标签数据 | `label_small.parquet`（272 行，8 类） | 同 |
| 预测数据 | `predict_small.parquet`（22k 行） | 同 |
| 评估方式 | 不做离线评估（线上人工审核） | shuffle + 80/20 split → Accuracy ~99.5% |
| 预测结果 | 112 个设备×窗口（需人工验证） | 同：112 条预测，96 正常 + 16 故障 |
| 特征数量 | Top-50（mRMR） | Top-20（mRMR，可调整 k 参数） |
| 模型参数 | n_estimators=80, random_state=90 | 同 |

### 精度计算方法：AIP vs 本地代码差异与替代方案

本节专门说明「精度到底怎么算出来的」，因为这是本地代码和 AIP 平台差异最大、也最容易被误读的一点。

#### 1. AIP 平台当前的精度计算方法

- **做法**：在带标签的训练集上，SMOTE 过采样平衡各类后，做 `shuffle + 80/20 split`（随机打乱后按 80% 训练 / 20% 测试切分），在 20% 测试子集上算 `accuracy`（整体正确率），当前数值约 99.5%。
- **本质**：这是「**同分布验证**」——测试子集和训练子集来自同一批数据、同一时间段、同一批设备。
- **已知局限**：
  - **同分布 → 偏乐观**：不反映跨时间、跨站点、跨新故障类型的真实泛化能力。真实上线精度通常低于此值。
  - **SMOTE 在 split 之前 → 数据泄漏风险**：若过采样发生在切分**之前**，同一条少数类样本插值出的合成点可能同时落入训练集和测试集，测试集不再「干净」，accuracy 被进一步抬高。这是合成过采样评估的经典陷阱，需要确认 AIP 算子里 split 与 SMOTE 的先后顺序。
  - **只看 accuracy 不够**：类别极不平衡场景下，accuracy 会被多数类(如正常)主导，掩盖少数类故障的漏报。

#### 2. 本地 release-3.1 代码的现状

- **训练阶段不算任何精度**：`FaultDiagnosis.train()`（`fault_diagnosis.py`）的链路是 特征工程 → `select_features` 特征选择 → SMOTE → `RandomForest.train()`（`models/rnd_fst.py`）里直接 `RandomForestClassifier.fit(X, Y)` 全量拟合。**没有 train/test split、没有交叉验证、没有 accuracy / macro-F1 / 混淆矩阵的计算与输出。**
- **预测阶段无法算精度**：`predict()` 输出只有 `predict_label`（预测类别）+ 标识列；预测数据集 `predict_small.parquet`（列：`time / site_id / device_id / branch_id / value / i_cal / time_window`）**不含真值标签列**，因此预测结果没有任何真值可比对。
- **真值在哪里**：训练集 `train_dataset.parquet` 带 `label`（真值标签）列；独立标签表 `label_small.parquet` 带 `custom_label_id`（业务标注标签）；结果回写表 `result_dataset.parquet` 设计了 `predict_label_id`（模型预测标签）与 `modified_label_id`（人工修正标签）两列，但当前为空表（0 行）。

> 一句话结论：**训练有真值、本来能算精度，但代码没实现；预测无真值、目前根本算不了精度，要等人工标注回写。**

#### 3. 可行的替代方案

按「改动成本从低到高、可信度从弱到强」排列：

| 方案 | 做什么 | 在哪改 | 产出指标 | 注意事项 |
|------|--------|--------|---------|---------|
| **A. 分层留出评估** | SMOTE **之前**先按标签做 `stratified train/test split`（如 80/20），SMOTE 只对训练折做，测试折保持原始分布 | 在 `FaultDiagnosis.train()` 拆 `X_train/Y_train` 后、调用 `RandomForest.train()` 前插入 split | `accuracy` + `macro_f1`（各类等权 F1）+ `confusion_matrix`（混淆矩阵） | **SMOTE 必须只作用于训练折**，否则重蹈数据泄漏；测试折不做过采样 |
| **B. 分层交叉验证** | `StratifiedKFold`（分层 K 折，如 5 折），每折内部独立做 SMOTE + 训练，折外评估 | 同上，封装一个 `evaluate()` 方法 | 每折 + 平均的 `macro_f1` / `recall_per_class`（各类召回） | 比 A 更稳，少数类样本极少时折数要调小；同样要把 SMOTE 放进折内 |
| **C. 时间外推评估** | 按 `time_window`（诊断时间窗口）切分：用较早日期训练、较晚日期测试，模拟真实上线的「用过去预测未来」 | 在 split 处改成按时间排序切分而非随机 | 跨时间的 `macro_f1` / 各类 `recall` | 最接近真实泛化能力，数值通常明显低于同分布；需要标签覆盖足够长时间跨度 |
| **D. 预测集回写后离线比对** | 预测先出 `predict_label_id`，运维人工标注/修正后写入 `result_dataset` 的 `modified_label_id`，再离线比对两列 | 走线上 `fault_output.py` 回写链路，积累带真值的结果表后离线统计 | 真实生产口径的 `accuracy` / `macro_f1` / 混淆矩阵 | 当前 `result_dataset.parquet` 为空，需先积累标注数据；这是唯一反映**线上真实表现**的方式 |

**运维口径建议**：故障诊断场景下**漏报比误报更严重**，评估应以 `macro_f1`（不受类别不平衡影响）和**关键故障类的 `recall`（召回率，如类 11 组串开路）** 为主，而不是只看整体 `accuracy`。

> 推荐落地顺序：先做 **A/B** 在训练阶段拿到可信的离线精度（注意把 SMOTE 关进折内），中期补 **C** 验证跨时间泛化，长期靠 **D** 拿到真正的生产精度。

### 后续对齐路线图

| 优先级 | 工作 | 预期效果 |
|--------|------|---------|
| P0 | 支持 `result_table`（历史修正标签）合并到 `merge_label` | 与线上一致的标签优先级逻辑 |
| P1 | 对接在线数据源（`load_api` / `load_database`） | 生产环境自动拉取当天数据 |
| P1 | 预测结果写回（`data_output` 算子） | 结果落库，供运维系统消费 |
| P2 | MLflow 模型注册对接 | 模型版本管理和灰度发布 |
| P2 | 定时调度（CRON 触发训练/预测流水线） | 每日自动诊断 |
| P3 | 理论电流特征 | 引入辐照度数据，提升识别精度 |
| P3 | 多窗口模式（window_one_label=0） | 支持更细粒度的故障定位 |
