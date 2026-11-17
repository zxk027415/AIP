<!-- @AI_GENERATED -->
# 电力负荷预测系统 (Load Forecast System)

## 项目概述

这是一个面向电力行业的**时序负荷预测系统**，支持多客户、多场景的电力负荷预测与离线回测验证。系统基于机器学习（XGBoost 为核心，扩展支持 LightGBM、CatBoost、Ridge 集成），结合气象特征、时间特征、历史负荷统计特征，对电力负荷进行高精度预测。

目前已接入的客户包括：
- **AESC**（工业园区，日前预测）
- **蒙西电网**（区域电网，日前预测，62天超长预测窗口）
- **威海**（独立回测验证数据集）

---

## 目录结构

```
.
├── run.py                        # 统一离线回测入口（YAML 配置驱动）
├── run_weihai_backtest.py        # 威海专项滚动回测脚本
├── evaluate_and_improve.py       # 精度评估与数据穿越审计框架
│
├── configs/                      # 客户配置文件
│   ├── aesc.yaml                 # AESC 客户配置
│   ├── mengxi.yaml               # 蒙西电网配置
│   ├── schema.py                 # 配置数据类定义（dataclass）
│   └── __init__.py
│
├── common/                       # 公共工具模块
│   ├── constants.py              # 全局常量、ScenarioConfig 场景配置
│   ├── holidays.py               # 中国工作日/节假日判断
│   └── __init__.py
│
├── data_fetch/                   # 数据获取模块
│   ├── fetcher.py                # 多数据源加载（在线DB / 离线CSV）
│   └── __init__.py
│
├── features/                     # 特征工程模块
│   ├── engine.py                 # 统一特征工程引擎（6种场景）
│   ├── helpers.py                # 特征辅助函数（重导出）
│   └── __init__.py
│
├── models_pkg/                   # 模型训练与推理模块
│   ├── trainer.py                # XGBoost 训练器（贝叶斯超参优化）
│   ├── wrapper.py                # MLflow 模型包装器（统一推理接口）
│   └── __init__.py
│
├── processing/                   # 数据处理流水线
│   ├── pipeline.py               # 数据清洗流水线（重导出）
│   └── __init__.py
│
├── evaluation/                   # 评估指标模块
│   ├── metrics.py                # SMAPE / MAE / RMSE 等指标（重导出）
│   └── __init__.py
│
├── datasets/                     # 本地数据集
│   └── load_true_weihai_260407.xlsx  # 威海负荷真值数据（2025-07 ~ 2026-04）
│
├── catboost_info/                # CatBoost 训练日志（自动生成）
└── output/                       # 预测结果输出目录（自动生成）
```

---

## 核心功能

### 1. 六种预测场景

系统通过 `ScenarioConfig` 统一管理六种预测场景的行为差异，避免大量 if-else 分支：

| 场景 | 含义 | 时间粒度 | 预测窗口 | 是否分开建模 |
|------|------|----------|----------|-------------|
| DI   | 日内预测 | 小时级 | 当日剩余 | 否 |
| D    | 日前预测 | 15min  | 1天      | 是 |
| WI   | 周内预测 | 15min  | 本周剩余 | 是 |
| W    | 周前预测 | 15min  | 1周      | 是 |
| MI   | 月内预测 | 15min  | 本月剩余 | 是 |
| M    | 月前预测 | 日级   | 1个月    | 是 |

### 2. 特征工程

`features/engine.py` 中的 `add_more_features` 函数统一处理所有场景的特征生成：

- **时间特征**：节假日标记、星期、月份、小时、天内序号、周期正余弦编码
- **Lag 特征**：1/2/3/7/14/21/28 天历史同时刻负荷
- **差分特征**：1步差分、日差分、多日差分
- **滚动统计**：均值、标准差、最大值、最小值（`center=False`，无数据穿越）
- **日统计特征**：前一天的日均值、日峰值、日谷值、峰谷差、负荷率
- **气象特征**：温度、风速、风向、气压、云量、降雨量、辐照度（EC 和 ENS_AVG 两套数据源）
- **分开建模**：工作日/节假日分别建模，各自生成独立的 shift 特征

### 3. 模型训练

`models_pkg/trainer.py` 使用 XGBoost + 贝叶斯超参优化：

- 使用 `BayesianOptimization` 自动搜索最优超参数（eta、max_depth、min_child_weight、subsample、lambda）
- 支持 `retrain` 模式：先用非选优集训练，验证精度后再用全量数据重训
- 样本权重：近期数据权重更高（指数衰减）
- 选优验证：用最近 N 个预测长度的数据评估 SMAPE

### 4. 多模型集成（威海回测）

`run_weihai_backtest.py` 实现了四模型自适应加权集成：

- XGBoost + LightGBM + CatBoost + Ridge
- 每个模型均使用 `TimeSeriesSplit` 时序交叉验证 + 贝叶斯优化
- 根据各模型 OOF RMSE 计算逆误差加权，自动确定集成权重
- 输出：预测结果 CSV + 4 张可视化图表（全局对比、逐天详情、SMAPE 柱状图、散点图）

### 5. 数据处理流水线

- **异常检测**：Chebyshev 不等式检测负荷突变异常点，标记后插值修复
- **时间戳补全**：`get_completed_timestamp` 补全缺失时间戳
- **数据填补**：`DataFiller` 支持周期性填补（相邻周同天）
- **数据延迟处理**：`df_recovery_by_self_defined` 处理数据延迟到达的情况
- **春节数据剔除**：自动识别并剔除春节假期数据（避免异常模式污染训练集）

### 6. 精度评估与数据穿越审计

`evaluate_and_improve.py` 提供：

- **数据穿越审计**：识别 pipeline 中 6 个潜在穿越风险点（chebyshev 全局统计、KFold 随机分折、center=True 滚动等）
- **无穿越特征工程**：修复版特征工程，所有 rolling/diff 均基于历史数据
- **无穿越异常检测**：滚动窗口版 Chebyshev 检测
- **时序交叉验证**：用 `TimeSeriesSplit` 替代 `KFold`
- **基线对比**：与已有回测结果对比，生成多维度可视化报告

---

## 配置系统

配置通过 YAML 文件驱动，结构如下：

```yaml
customer:
  name: "aesc"
  task_id: "0515_v21_aesc_d1_15min"
  output_dir: "./output/aesc_dataset"

data_source:
  table_name: "sgms_hbuilding_load_quarter3"
  time_field: "record_time"
  load_field: "load"
  time_granularity: "15min"
  time_zone: "Asia/Shanghai"

forecast:
  task_type: "D"           # 场景类型
  forecast_horizon: 1      # 预测天数
  specify_model: "xgb"
  separate_modeling: "false"

id_lists:
  park_01:
    - device_01            # 支持多 parent/child 批量回测

weather_cols:
  train: [EC.TMP, ENS_AVG.TMP, ...]
  predict: [EC.TMP, ENS_AVG.TMP, ...]

backtest:
  start_date: "2025-03-15"
  end_date: "2025-03-26"
```

---

## 快速开始

### 运行 AESC 离线回测

```bash
python run.py --config configs/aesc.yaml
```

### 运行蒙西电网回测

```bash
python run.py --config configs/mengxi.yaml
```

### 运行威海滚动回测（多模型集成）

```bash
python run_weihai_backtest.py
```

### 运行精度评估与穿越审计

```bash
python evaluate_and_improve.py
```

---

## 主要依赖

| 库 | 用途 |
|----|------|
| xgboost | 核心预测模型 |
| lightgbm | 集成模型（威海回测） |
| catboost | 集成模型（威海回测） |
| scikit-learn | Ridge 回归、TimeSeriesSplit、评估指标 |
| bayesian-optimization | 超参数自动优化 |
| mlflow | 模型包装与序列化接口 |
| pandas / numpy | 数据处理 |
| chinese-calendar | 中国节假日判断 |
| pytz | 时区处理 |
| loguru | 日志记录 |
| matplotlib | 可视化 |

---

## 输出说明

回测结果保存在 `output/` 目录下：

- `tmp_re_<时间>_<parent_id>_<child_id>_<task_type>.csv`：逐日预测结果
- `output/weihai_backtest/weihai_predictions.csv`：威海全量预测结果
- `output/weihai_backtest/weihai_daily_metrics.csv`：逐日评估指标
- `output/weihai_backtest/forecast_vs_true.png`：全局预测对比图
- `output/weihai_backtest/daily_details.png`：逐天预测详情图
- `output/weihai_backtest/daily_smape_bar.png`：逐日 SMAPE 柱状图
- `output/weihai_backtest/scatter.png`：真实值 vs 预测值散点图

---

## 评估指标

- **SMAPE**（对称平均绝对百分比误差）：主要指标，对称处理零值附近的误差
- **MAE**（平均绝对误差）：绝对误差量级参考
- **RMSE**（均方根误差）：对大误差更敏感
- **R²**：拟合优度（散点图中展示）

<!-- @AI_GENERATED: end -->
