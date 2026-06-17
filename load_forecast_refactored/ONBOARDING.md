<!-- @AI_GENERATED -->
# 电力负荷预测系统 — 从零上手完全指南

> 本文档面向刚接手项目的开发者，从最基础的概念开始，逐步讲解整个系统的每一个环节。

---

## 目录

1. [项目要解决什么问题？](#1-项目要解决什么问题)
2. [数据集：格式、来源与输入方式](#2-数据集格式来源与输入方式)
3. [配置系统：YAML 如何驱动整个流程](#3-配置系统yaml-如何驱动整个流程)
4. [数据预处理流水线](#4-数据预处理流水线)
5. [特征工程：把原始数据变成模型能理解的输入](#5-特征工程把原始数据变成模型能理解的输入)
6. [XGBoost 原理与使用](#6-xgboost-原理与使用)
7. [贝叶斯超参数优化](#7-贝叶斯超参数优化)
8. [多模型集成（威海回测）](#8-多模型集成威海回测)
9. [模型包装器与推理流程](#9-模型包装器与推理流程)
10. [回测系统：如何验证模型效果](#10-回测系统如何验证模型效果)
11. [评估指标详解](#11-评估指标详解)
12. [数据穿越问题与修复](#12-数据穿越问题与修复)
13. [完整执行流程串讲](#13-完整执行流程串讲)

---

## 1. 项目要解决什么问题？

### 1.1 业务背景

电力系统需要提前知道未来一段时间的用电量（即"负荷"），这样才能：
- 合理安排发电计划（火电机组启停需要时间）
- 保障电网安全稳定运行（供需必须实时平衡）
- 参与电力市场交易（报价需要基于预测）

**负荷预测**就是：给定历史用电数据 + 气象数据，预测未来 N 小时/天/周/月的用电量。

### 1.2 这个项目做了什么

本项目是一个**离线回测验证系统**，核心功能是：

```
历史数据 → 数据清洗 → 特征工程 → 模型训练 → 预测 → 与真实值对比 → 评估精度
```

它不是一个在线服务，而是用来**验证预测算法效果**的工具。你可以理解为：
- 假装"今天是 3 月 15 日"，用 3 月 15 日之前的数据训练模型
- 预测 3 月 16 日的负荷
- 然后拿 3 月 16 日的真实数据来对比，看预测得准不准
- 再假装"今天是 3 月 16 日"，重复上述过程……

这就是**回测（Backtest）**。

### 1.3 六种预测场景

系统支持 6 种预测场景，对应不同的业务需求：

| 缩写 | 全称 | 含义 | 典型用途 |
|------|------|------|----------|
| **DI** | Day Intra | 日内预测 | 当天剩余时段的负荷（实时调度） |
| **D**  | Day Ahead | 日前预测 | 明天全天的负荷（最常用） |
| **WI** | Week Intra | 周内预测 | 本周剩余天数的负荷 |
| **W**  | Week Ahead | 周前预测 | 下周全周的负荷 |
| **MI** | Month Intra | 月内预测 | 本月剩余天数的负荷 |
| **M**  | Month Ahead | 月前预测 | 下月全月的负荷 |

这 6 种场景的核心算法相同，但在数据截取方式、特征构造、训练策略上有差异。项目通过 `ScenarioConfig`（在 `common/constants.py` 中定义）来管理这些差异：

```python
@dataclass(frozen=True)
class ScenarioConfig:
    task_type: str            # "DI" / "D" / "WI" / "W" / "MI" / "M"
    rounding_unit: str        # "hour"（DI）或 "day"（其余）
    look_back_multiplier: int # 回看倍数
    prefer_unit_len: int      # 选优验证长度倍数
    default_retrain: bool     # 是否默认重训
    use_separate_modeling: bool # 是否分开建模
```

---

## 2. 数据集：格式、来源与输入方式

### 2.1 数据长什么样

本项目的数据是**长格式（Long Format）**的时序数据。以威海数据集 `load_true_weihai_260407.xlsx` 为例：

| record_time | feature_name | value | parent_id | child_id |
|-------------|-------------|-------|-----------|----------|
| 2025-07-02 00:00:00 | load | 1523.4 | weihai | WH_LOAD |
| 2025-07-02 00:15:00 | load | 1498.7 | weihai | WH_LOAD |
| 2025-07-02 00:00:00 | EC.TMP | 26.3 | weihai | WH_LOAD |
| ... | ... | ... | ... | ... |

关键字段说明：
- **record_time**：时间戳，通常是 15 分钟间隔（一天 96 个点）
- **feature_name**：特征名称，`load` 是负荷（预测目标），其他如 `EC.TMP`（温度）、`EC.WS`（风速）是气象特征
- **value**：对应的数值
- **parent_id / child_id**：层级标识，一个 parent 下可以有多个 child（比如一个园区下有多个设备）

### 2.2 为什么是长格式

长格式的好处是**灵活**：不同设备、不同特征都存在同一张表里，新增特征只需要加行，不需要改表结构。但在使用前需要**转换为宽格式**：

```
长格式（数据库存储）:
  record_time | feature_name | value
  2025-07-02  | load         | 1523.4
  2025-07-02  | EC.TMP       | 26.3

  ↓ 转换 ↓

宽格式（模型输入）:
  record_time | load   | EC.TMP
  2025-07-02  | 1523.4 | 26.3
```

这个转换在 `data_fetch/fetcher.py` 的 `_pivot_and_extract()` 函数中完成。

### 2.3 三种数据来源

项目支持三种数据加载方式（都在 `data_fetch/fetcher.py` 中）：

| 函数 | 数据来源 | 使用场景 |
|------|---------|---------|
| `extract_load_data()` | 在线数据集服务（Dataset API） | 生产环境 |
| `beta_load_data()` | MySQL 数据库 | 测试环境 |
| `offline_load_data()` | 本地 CSV 文件 | 离线回测（最常用） |

**离线回测时**，数据流是：

```
本地 CSV/Excel → pd.read_csv() → 按 parent_id/child_id 过滤
→ _pivot_and_extract()（长转宽）→ _resample_and_clean()（重采样+清洗）
→ 返回 (load_df, his_min_max)
```

### 2.4 数据重采样

原始数据可能有缺失或不规则，`_resample_and_clean()` 会：

1. **去重**：同一时间戳只保留第一条
2. **排序**：按时间升序
3. **重采样**：用 `df.resample("15min").mean()` 对齐到标准 15 分钟间隔
4. **春节剔除**：非月前预测场景下，自动剔除春节假期数据（因为春节用电模式极端异常）
5. **计算历史极值**：记录 `his_min_max`（历史最小值和最大值），后续用于后处理

---

## 3. 配置系统：YAML 如何驱动整个流程

### 3.1 配置文件结构

以 `configs/aesc.yaml` 为例，一个完整的配置文件包含 5 个部分：

```yaml
# ① 客户基本信息
customer:
  name: "aesc"                          # 客户名称
  task_id: "0515_v21_aesc_d1_15min"     # 任务唯一标识
  output_dir: "./output/aesc_dataset"   # 输出目录

# ② 数据源配置
data_source:
  table_name: "sgms_hbuilding_load_quarter3"  # 数据表名
  time_field: "record_time"                    # 时间列名
  load_field: "load"                           # 负荷列名
  time_granularity: "15min"                    # 数据粒度
  time_zone: "Asia/Shanghai"                   # 时区

# ③ 预测任务配置
forecast:
  task_type: "D"              # 场景类型（D=日前预测）
  forecast_horizon: 1         # 预测天数
  specify_model: "xgb"        # 指定模型
  separate_modeling: "false"   # 是否工作日/节假日分开建模

# ④ 设备列表（支持批量回测）
id_lists:
  park_01:                    # parent_id
    - device_01               # child_id（可以有多个）

# ⑤ 气象特征列
weather_cols:
  train: [EC.TMP, EC.WS, ...]     # 训练时使用的气象列
  predict: [EC.TMP, EC.WS, ...]   # 预测时使用的气象列

# ⑥ 回测时间范围
backtest:
  start_date: "2025-03-15"
  end_date: "2025-03-26"
```

### 3.2 配置如何被加载

在 `run.py` 中，`load_config()` 函数读取 YAML 并映射到 Python dataclass：

```python
# configs/schema.py 中定义了这些 dataclass
@dataclass
class CustomerConfig:
    name: str
    task_id: str
    data_source: DataSourceConfig    # 数据源配置
    forecast: ForecastConfig         # 预测配置
    backtest: BacktestConfig         # 回测配置
    id_lists: Dict[str, List[str]]   # 设备列表
    weather_cols: Dict[str, List[str]] # 气象列
```

使用 dataclass 的好处是**类型安全** + **IDE 自动补全** + **属性访问**（`cfg.forecast.task_type` 比 `cfg['forecast']['task_type']` 更清晰）。

---

## 4. 数据预处理流水线

数据从加载到可以做特征工程，中间要经过一系列清洗步骤。这些步骤在 `data_process.py`（外部依赖）和 `processing/pipeline.py` 中。

### 4.1 训练状态判断 — `get_train_status()`

在训练之前，先检查数据是否满足训练条件：
- 数据量是否足够（至少需要 N 天的数据）
- 数据是否有严重缺失

如果不满足，返回 `'false'`，跳过训练。

### 4.2 时间频率检测 — `get_timestamp_freq()`

自动检测数据的时间间隔：
- 返回 `original_time_freq`（如 `"15min"`）
- 返回 `daily_horizon`（一天有多少个数据点，15 分钟间隔 = 96 个点）

### 4.3 时间戳补全 — `get_completed_timestamp()`

真实数据经常有缺失的时间戳（比如设备故障导致某些时段没有数据）。这个函数：
1. 生成一个完整的时间戳序列（从数据开始到结束，每 15 分钟一个）
2. 将原始数据与完整序列做 merge
3. 缺失的时间戳对应的负荷值为 NaN

### 4.4 异常检测 — `chebyshev_detector()`

**原理：切比雪夫不等式**

切比雪夫不等式告诉我们：对于任意分布的随机变量，落在均值 ± k 倍标准差之外的概率不超过 1/k²。

```
P(|X - μ| ≥ kσ) ≤ 1/k²
```

当 k=3 时，超出 3σ 范围的概率 ≤ 11.1%。

**在本项目中的应用：**

```python
# 计算相邻时刻的负荷变化量
load_delta = load[t] - load[t-1]

# 计算变化量的均值和标准差
mean_delta = load_delta.mean()
std_delta = load_delta.std()

# 超出 3σ 范围的点标记为异常
upper = mean_delta + 3 * std_delta
lower = mean_delta - 3 * std_delta
is_anomaly = (load_delta > upper) | (load_delta < lower)
```

异常点的负荷值被设为 NaN，后续通过插值修复。

> ⚠️ **数据穿越风险**：原始实现用**全局数据**计算 mean 和 std，包含了未来数据。改进版（`evaluate_and_improve.py`）使用**滚动窗口**只看历史数据。

### 4.5 数据补全 — `get_completed_df()`

将异常检测后的 NaN 值进行填补：
- 线性插值（`interpolate()`）
- 前向填充（`ffill`）
- 后向填充（`bfill`）

### 4.6 周期性填补 — `DataFiller`

对于较长的缺失段，简单插值效果不好。`DataFiller` 使用**周期性填补**：
- 找到上一周同一天同一时刻的值来填补
- 例如：本周三 10:00 缺失 → 用上周三 10:00 的值填补

---

## 5. 特征工程：把原始数据变成模型能理解的输入

### 5.1 为什么需要特征工程

XGBoost 等机器学习模型不能直接理解"时间序列"。你不能把一串负荷值丢给它说"预测下一个"。你需要把时序信息**编码成一行一行的表格特征**，让模型学习"什么条件下负荷会高/低"。

举个例子，模型需要知道：
- 现在是几点？（时间特征）
- 昨天同一时刻负荷是多少？（Lag 特征）
- 过去几小时负荷的趋势如何？（滚动统计特征）
- 今天是工作日还是假日？（日历特征）
- 当前温度是多少？（气象特征）

### 5.2 特征工程的入口

特征工程的核心在 `features/engine.py` 的 `add_more_features()` 函数。它接收清洗后的数据，输出一个包含所有特征的 DataFrame。

下面逐类讲解每种特征。

### 5.3 时间特征

```python
feat["is_holiday"]  = 0 或 1          # 是否节假日
feat["day"]         = 1~31            # 月内第几天
feat["yday"]        = 1~365           # 年内第几天
feat["month"]       = 1~12            # 月份
feat["dayofweek"]   = 0~6             # 星期几（0=周一）
feat["hour"]        = 0~23            # 小时
feat["minute"]      = 0/15/30/45      # 分钟
feat["period"]      = 0~95            # 天内第几个时段（15分钟一个）
```

**为什么需要这些？** 因为用电有明显的时间规律：
- 白天用电多，夜间少（hour 特征）
- 工作日用电多，周末少（dayofweek、is_holiday 特征）
- 夏天空调用电多，冬天取暖用电多（month 特征）

### 5.4 周期编码（正余弦编码）

直接用数字表示时间有个问题：23 点和 0 点在数值上差 23，但实际上它们只差 1 小时。

**解决方案：用正弦和余弦把周期性编码到连续空间**

```python
feat["hour_sin"] = sin(2π × hour / 24)
feat["hour_cos"] = cos(2π × hour / 24)
```

这样 23 点和 0 点在 sin/cos 空间中是相邻的：
- 0 点：sin=0, cos=1
- 6 点：sin=1, cos=0
- 12 点：sin=0, cos=-1
- 18 点：sin=-1, cos=0
- 23 点：sin≈-0.26, cos≈0.97（和 0 点很接近！）

同理，星期、年内天数、月份也做了周期编码。

### 5.5 Lag 特征（滞后特征）

**核心思想：用历史同时刻的负荷来预测当前负荷。**

```python
# 以威海回测为例（daily_horizon=96，即一天96个点）
feat["lag_1d"]  = load.shift(96)    # 昨天同时刻的负荷
feat["lag_2d"]  = load.shift(192)   # 前天同时刻的负荷
feat["lag_7d"]  = load.shift(672)   # 上周同时刻的负荷
feat["lag_14d"] = load.shift(1344)  # 两周前同时刻的负荷
feat["lag_28d"] = load.shift(2688)  # 四周前同时刻的负荷
```

**为什么有效？** 因为用电有很强的周期性：
- 今天 10:00 的负荷和昨天 10:00 很像（日周期）
- 这周三和上周三很像（周周期）

还有多周加权平均：
```python
feat["same_time_2w"] = (lag_7d + lag_14d) / 2      # 最近两周同时刻均值
feat["same_time_3w"] = (lag_7d + lag_14d + lag_21d) / 3  # 最近三周同时刻均值
```

### 5.6 差分特征

**核心思想：捕捉负荷的变化趋势。**

```python
load_prev = load.shift(1)  # t-1 时刻的负荷

feat["diff_1"]   = load_prev - load_prev.shift(1)    # 短期变化：load[t-1] - load[t-2]
feat["diff_96"]  = load_prev - load_prev.shift(96)   # 日变化：load[t-1] - load[t-97]
feat["diff_192"] = load_prev - load_prev.shift(192)  # 两日变化
```

> ⚠️ 注意：差分是基于 `load.shift(1)`（即 t-1 时刻）计算的，而不是直接用 `load.diff()`。这是为了**避免数据穿越**——在预测时，t 时刻的真实负荷是未知的，但 t-1 时刻的是已知的。

### 5.7 滚动统计特征

**核心思想：用过去一段时间的统计量描述近期负荷水平。**

这段代码只有两行核心逻辑，但理解起来需要拆开来看。

#### 第一行：`load_yd = load.shift(96)`

`shift(96)` 的意思是把整列数据**向下平移 96 行**。因为数据是 15 分钟一个点，96 个点正好是一天（96 × 15min = 24h）。

用一个具体例子来看：

```
原始 load 列：                    shift(96) 之后的 load_yd 列：
行号  时间              load      行号  时间              load_yd
───────────────────────────      ───────────────────────────────
0     4月1日 00:00      1500      0     4月1日 00:00      NaN        ← 前96行没有"昨天"，所以是空
1     4月1日 00:15      1480      1     4月1日 00:15      NaN
2     4月1日 00:30      1460      2     4月1日 00:30      NaN
...   ...               ...       ...   ...               ...
95    4月1日 23:45      1520      95    4月1日 23:45      NaN
96    4月2日 00:00      1550      96    4月2日 00:00      1500       ← 这里开始有值了！
97    4月2日 00:15      1530      97    4月2日 00:15      1480          值 = 4月1日同时刻的load
98    4月2日 00:30      1510      98    4月2日 00:30      1460
...   ...               ...       ...   ...               ...
192   4月3日 00:00      1600      192   4月3日 00:00      1550       ← 4月2日00:00的load
```

**关键理解**：`load_yd` 的第 N 行存的是**昨天同一时刻**的负荷值。

**为什么要 shift(96) 而不是直接用 load？** 因为在预测时，当前时刻 t 的真实负荷 `load[t]` 是**未知的**（这正是你要预测的东西！），但昨天同时刻 `load[t-96]` 是**已知的**。如果直接对 `load` 做 rolling，在预测时就会用到未来数据（数据穿越）。

#### 第二行：`load_yd.rolling(window, center=False).mean()`

`rolling(window)` 是 pandas 的**滑动窗口**操作。它对每一行，取**往上数 window 行**的数据，计算统计量。

以 `window=4` 为例，逐行展示 `load_yd.rolling(4).mean()` 的计算过程：

```
load_yd 列：                      rolling(4).mean() 的计算过程：
行号  load_yd                     行号  计算                                结果
────────────────                  ──────────────────────────────────────────────
96    1500                        96    只有1个值: mean(1500)               = 1500.0
97    1480                        97    只有2个值: mean(1500, 1480)         = 1490.0
98    1460                        98    只有3个值: mean(1500, 1480, 1460)   = 1480.0
99    1440                        99    凑够4个值: mean(1500, 1480, 1460, 1440) = 1470.0
100   1520                        100   窗口滑动:  mean(1480, 1460, 1440, 1520) = 1475.0
101   1510                        101   继续滑动:  mean(1460, 1440, 1520, 1510) = 1482.5
                                              ↑
                                        窗口永远只看"当前行及之前的3行"
                                        绝不会看"之后的行"（这就是 center=False 的含义）
```

**`center=False` vs `center=True` 的区别**：

```
假设 window=4，当前在第 100 行：

center=False（本项目使用）：
  窗口 = [第97行, 第98行, 第99行, 第100行]   ← 全部是过去的数据 ✓
         ←────── 往回看 ──────→ 当前

center=True（有数据穿越风险）：
  窗口 = [第98行, 第99行, 第100行, 第101行]  ← 第101行是未来数据！❌
                          当前 →→→ 未来
```

#### 四种统计量的含义

对于每个窗口大小，计算 4 种统计量：

```python
rolling(window).mean()  # 均值：过去这段时间的平均负荷水平
rolling(window).std()   # 标准差：过去这段时间负荷的波动程度
rolling(window).max()   # 最大值：过去这段时间的负荷峰值
rolling(window).min()   # 最小值：过去这段时间的负荷谷值
```

#### 不同窗口大小捕捉不同时间尺度的信息

```
window=4  (4×15min = 1小时)  → 捕捉最近1小时的短期趋势
window=8  (8×15min = 2小时)  → 捕捉最近2小时的趋势
window=12 (12×15min = 3小时) → 捕捉最近3小时的趋势
window=24 (24×15min = 6小时) → 捕捉半天的趋势（比如上午整体水平）
window=48 (48×15min = 12小时)→ 捕捉半天到一天的趋势
window=96 (96×15min = 24小时)→ 捕捉完整一天的趋势
```

#### 完整的具体例子

假设我们要预测 4 月 3 日 10:00 的负荷，看看 `roll_4_mean` 这个特征是怎么算出来的：

```
步骤 1：shift(96) 把数据平移到"昨天"
  → load_yd 在 4月3日10:00 这一行的值 = 4月2日10:00 的真实负荷

步骤 2：rolling(4) 取 load_yd 的最近 4 个值
  → 取的是 load_yd 在 [4月3日09:15, 09:30, 09:45, 10:00] 这 4 行
  → 对应的真实含义是 [4月2日09:15, 09:30, 09:45, 10:00] 的负荷

步骤 3：.mean() 求均值
  → roll_4_mean = 这 4 个值的平均

最终含义：
  "昨天 09:15~10:00 这一小时的平均负荷是多少"
  → 这个信息对预测今天 10:00 的负荷很有参考价值
  → 而且完全没有使用任何未来数据 ✓
```

#### 为什么这些特征有用

模型通过这些特征可以学到：
- `roll_4_mean` 高 → 昨天同时段负荷高 → 今天可能也高
- `roll_96_std` 大 → 昨天负荷波动剧烈 → 今天预测不确定性大
- `roll_24_max` - `roll_24_min` 大 → 昨天半天内峰谷差大 → 可能是工作日模式

### 5.8 日统计特征

**核心思想：用前一天的整体负荷水平作为参考。**

```python
# 按天分组计算统计量
daily_stats = df.groupby("date")["load"].agg(["mean", "max", "min", "std"])

# 计算衍生指标
daily_stats["peak_valley"]  = max - min           # 峰谷差
daily_stats["pv_rate"]      = peak_valley / max   # 峰谷差率
daily_stats["load_rate"]    = mean / max           # 负荷率

# 关键：shift(1) 前移一天，只使用前一天的统计量
for col in stats_cols:
    daily_stats[col] = daily_stats[col].shift(1)
```

### 5.9 气象特征

气象数据（温度、风速、气压、云量、降雨、辐照度等）直接作为特征输入。项目使用两套气象数据源：
- **EC**：ECMWF（欧洲中期天气预报中心）的确定性预报
- **ENS_AVG**：ECMWF 集合预报的平均值

```yaml
# configs/aesc.yaml 中的气象列配置
weather_cols:
  train:
    - EC.TMP          # EC 温度
    - ENS_AVG.TMP     # 集合平均温度
    - EC.WS           # EC 风速
    - EC.ghi          # EC 全球水平辐照度
    - EC.poa          # EC 倾斜面辐照度
    ...
```

### 5.10 Shift 对齐

在实际业务中，不同数据的**到达时间不同**：
- 负荷数据：实时采集，但可能有 15 分钟延迟
- 气象预报：提前 1-3 天发布

`add_more_features()` 中的 shift 逻辑会：
1. 检测每列数据的最新可用时间
2. 计算与预测截止时间的差距
3. 对每列数据做相应的 shift，确保所有特征在时间上对齐

### 5.11 工作日/节假日分开建模

当 `separate_modeling='true'` 时，系统会把数据分成两份：
- **工作日数据** → 训练工作日模型
- **节假日数据** → 训练节假日模型

预测时根据预测日是工作日还是节假日，选择对应的模型。

**为什么要分开？** 因为工作日和节假日的用电模式差异很大：
- 工作日：早 8 点开始上升，中午小降，下午继续高位，晚 6 点后下降
- 节假日：整体较低，没有明显的早晚高峰

---

## 6. XGBoost 原理与使用

### 6.1 什么是 XGBoost

XGBoost（eXtreme Gradient Boosting）是一种**梯度提升决策树**算法。要理解它，需要先理解三个概念：

#### 概念 1：决策树

决策树就像一个"20 个问题"游戏：

```
                    温度 > 30°C ?
                   /            \
                 是              否
                /                \
        是工作日?            小时 > 18?
        /      \              /      \
      是        否          是        否
      ↓         ↓           ↓         ↓
   高负荷    中负荷      低负荷    中负荷
```

每个节点是一个"问题"（对某个特征的判断），叶子节点是预测值。

#### 概念 2：集成学习（Ensemble）

一棵决策树容易过拟合。解决方案：训练**很多棵树**，把它们的预测结果加起来。

```
最终预测 = 树1的预测 + 树2的预测 + 树3的预测 + ... + 树N的预测
```

#### 概念 3：梯度提升（Gradient Boosting）

关键思想：**每棵新树学习的是前面所有树的"残差"（预测误差）**。

```
第1棵树：学习原始目标 y
  → 预测值 ŷ₁，残差 r₁ = y - ŷ₁

第2棵树：学习残差 r₁
  → 预测值 ŷ₂，残差 r₂ = r₁ - ŷ₂

第3棵树：学习残差 r₂
  → 预测值 ŷ₃，残差 r₃ = r₂ - ŷ₃

...

最终预测 = ŷ₁ + ŷ₂ + ŷ₃ + ...
```

每棵树都在"修补"前面树的错误，逐步逼近真实值。

#### XGBoost 的特殊之处

XGBoost 在标准梯度提升的基础上做了很多优化：
- **正则化**：在目标函数中加入树的复杂度惩罚（叶子数量、叶子权重），防止过拟合
- **二阶导数**：不仅用一阶梯度，还用二阶梯度（Hessian），收敛更快
- **列采样**：每棵树只用部分特征，增加多样性
- **缺失值处理**：自动学习缺失值应该走左子树还是右子树
- **并行计算**：特征分裂点搜索可以并行

### 6.2 XGBoost 在本项目中的使用

在 `models_pkg/trainer.py` 中：

```python
# 1. 准备数据（XGBoost 使用自己的 DMatrix 格式）
dtrain = xgb.DMatrix(x_train, label=y_train, missing=0, weight=sample_weights)

# 2. 设置参数
params = {
    'objective': 'reg:squarederror',  # 回归任务，目标函数是均方误差
    'booster': 'gbtree',              # 使用树模型
    'eval_metric': 'rmse',            # 评估指标：均方根误差
    'max_depth': 5,                   # 树的最大深度（控制复杂度）
    'eta': 0.05,                      # 学习率（每棵树的贡献权重）
    'min_child_weight': 3,            # 叶子节点最小样本权重和
    'subsample': 0.8,                 # 每棵树使用 80% 的样本
    'lambda': 10,                     # L2 正则化系数
}

# 3. 训练（最多 200 棵树，早停机制）
model = xgb.train(
    params, dtrain, 200,
    evals=[(dtrain, 'train')],
    early_stopping_rounds=10,  # 如果连续 10 轮没有改善就停止
    verbose_eval=50            # 每 50 轮打印一次
)

# 4. 预测
dtest = xgb.DMatrix(x_test)
predictions = model.predict(dtest)
```

### 6.3 样本权重

本项目给近期数据更高的权重：

```python
def sample_weights(train_label, ac=0.99):
    n = len(train_label)
    weights = []
    for i in range(n):
        weights.append(pow(ac, i // forecast_length))
    return np.array(list(reversed(weights)))
```

**原理**：`ac=0.99` 意味着每过一个预测周期（比如 96 个点 = 1 天），权重衰减为原来的 99%。30 天前的数据权重约为 `0.99^30 ≈ 0.74`。

**为什么？** 因为近期的用电模式更能代表未来。一个月前的数据可能因为季节变化、设备变更等原因不太准确。

### 6.4 关键超参数解释

| 参数 | 含义 | 值越大 | 值越小 |
|------|------|--------|--------|
| `max_depth` | 树的最大深度 | 模型更复杂，容易过拟合 | 模型更简单，可能欠拟合 |
| `eta` (learning_rate) | 学习率 | 每棵树贡献大，需要更少的树 | 每棵树贡献小，需要更多的树 |
| `min_child_weight` | 叶子节点最小权重 | 更保守，不容易过拟合 | 更激进，容易过拟合 |
| `subsample` | 样本采样比例 | 用更多数据，方差小 | 用更少数据，增加随机性 |
| `lambda` | L2 正则化 | 惩罚更重，模型更简单 | 惩罚更轻，模型更复杂 |

---

## 7. 贝叶斯超参数优化

### 7.1 为什么需要超参数优化

XGBoost 有很多超参数（max_depth、eta、lambda 等），不同的组合效果差异很大。手动调参效率低，网格搜索（Grid Search）在高维空间计算量爆炸。

### 7.2 贝叶斯优化的核心思想

贝叶斯优化的思路是：**用一个"代理模型"来近似目标函数，然后根据代理模型选择下一个最有希望的参数组合。**

具体步骤：

```
1. 随机选几组参数，训练模型，记录效果
   → 得到几个 (参数, 效果) 的观测点

2. 用高斯过程（Gaussian Process）拟合这些观测点
   → 得到一个"代理模型"，它能预测任意参数组合的效果（均值 + 不确定性）

3. 用"采集函数"（Acquisition Function）选择下一个参数组合
   → 平衡"探索"（不确定性高的区域）和"利用"（预测效果好的区域）

4. 用选出的参数训练模型，记录效果
   → 新增一个观测点

5. 重复 2-4，直到达到预设的迭代次数
```

### 7.3 关键概念图解

```
效果 ↑
     |     ●          ●
     |    / \   ?    / \
     |   /   \ ? ?  /   \     ← 高斯过程拟合的曲线（均值）
     |  /     \???/     \    ← 阴影区域 = 不确定性
     | ●       \/       ●
     |________________________→ 参数空间
           ↑
     下一个要尝试的点
     （不确定性高 且 预测效果可能好）
```

### 7.4 在本项目中的实现

```python
from bayes_opt import BayesianOptimization

# 定义目标函数：输入超参数，输出模型效果（负 RMSE，因为 BO 是最大化）
def xgb_cv(eta, max_depth, min_child_weight, subsample, lambdas):
    # 用这组参数做交叉验证
    tscv = TimeSeriesSplit(n_splits=5)
    oof = np.full(x_train.shape[0], np.nan)
    for _, (ti, vi) in enumerate(tscv.split(x_train)):
        # 训练 + 预测
        ...
        oof[vi] = model.predict(val_data)
    # 返回负 RMSE（BO 最大化，所以取负号）
    return -np.sqrt(mean_squared_error(y_train[mask], oof[mask]))

# 定义参数搜索范围
pbounds = {
    'eta': (0.01, 0.15),           # 学习率：0.01 ~ 0.15
    'max_depth': (2, 8),           # 树深度：2 ~ 8
    'min_child_weight': (0.3, 10), # 最小叶子权重：0.3 ~ 10
    'subsample': (0.5, 1),         # 采样比例：50% ~ 100%
    'lambdas': (0.1, 100),         # 正则化：0.1 ~ 100
}

# 创建优化器并运行
bo = BayesianOptimization(f=xgb_cv, pbounds=pbounds, random_state=42)
bo.maximize(
    init_points=3,   # 先随机试 3 组参数
    n_iter=12         # 再用贝叶斯优化试 12 组参数
)

# 获取最优参数
best_params = bo.max['params']
```

### 7.5 与其他调参方法的对比

| 方法 | 原理 | 优点 | 缺点 |
|------|------|------|------|
| 网格搜索 | 穷举所有组合 | 一定能找到最优 | 计算量爆炸（5个参数×10个值=10万次） |
| 随机搜索 | 随机采样参数 | 简单高效 | 可能错过最优区域 |
| **贝叶斯优化** | 用代理模型指导搜索 | 高效，通常 15-30 次就能找到好参数 | 实现复杂，有额外开销 |

---

## 8. 多模型集成（威海回测）

### 8.1 为什么要集成多个模型

单个模型有自己的偏好和盲区：
- XGBoost 擅长捕捉非线性关系，但可能过拟合
- LightGBM 训练更快，对大数据集友好
- CatBoost 对类别特征处理好，正则化强
- Ridge 是线性模型，简单稳定，不容易过拟合

把多个模型的预测结果加权平均，可以**取长补短，降低单一模型的风险**。

### 8.2 四个模型简介

#### XGBoost
前面已经详细讲过。本项目中使用贝叶斯优化调参 + TimeSeriesSplit 交叉验证。

#### LightGBM
微软开发的梯度提升框架，与 XGBoost 类似但有几个关键区别：
- **直方图算法**：将连续特征离散化为直方图，加速分裂点搜索
- **叶子优先生长**：XGBoost 按层生长，LightGBM 按叶子生长（更深但更精确）
- **训练速度更快**，内存占用更少

```python
params = {
    'objective': 'regression',
    'metric': 'rmse',
    'learning_rate': 0.05,
    'max_depth': 5,
    'num_leaves': 31,          # LightGBM 特有：叶子数量
    'min_child_samples': 20,   # 叶子最少样本数
    'subsample': 0.8,
}
model = lgb.train(params, lgb.Dataset(x_train, label=y_train), 100, ...)
```

#### CatBoost
Yandex 开发的梯度提升框架，特点：
- **有序提升**（Ordered Boosting）：减少预测偏移
- **对称树**：每层使用相同的分裂条件，更规则
- **内置正则化**：`l2_leaf_reg` 和 `bagging_temperature`

```python
model = CatBoostRegressor(
    loss_function='RMSE',
    learning_rate=0.05,
    depth=5,                    # 树深度
    l2_leaf_reg=3.0,           # L2 正则化
    bagging_temperature=0.5,   # 采样温度（越高越随机）
)
model.fit(x_train, y_train, eval_set=(x_val, y_val), early_stopping_rounds=5)
```

#### Ridge 回归
最简单的线性模型，加了 L2 正则化：

```
预测值 = w₁×特征₁ + w₂×特征₂ + ... + wₙ×特征ₙ + b

目标函数 = Σ(y - ŷ)² + α × Σwᵢ²
                ↑              ↑
           均方误差      L2正则化（防止权重过大）
```

Ridge 在这里的作用是**稳定器**：当其他模型都过拟合时，Ridge 的预测相对稳定。

### 8.3 自适应加权集成

不是简单地取平均，而是根据每个模型的**交叉验证表现**自动分配权重：

```python
def _compute_adaptive_weights(oof_scores):
    """
    逆误差加权：RMSE 越小的模型，权重越大
    """
    # 例如：xgb=100, lgb=120, catb=110, ridge=150
    inv_scores = {k: 1.0 / v for k, v in oof_scores.items()}
    # → xgb=0.01, lgb=0.0083, catb=0.0091, ridge=0.0067
    total = sum(inv_scores.values())
    weights = {k: v / total for k, v in inv_scores.items()}
    # → xgb=0.29, lgb=0.24, catb=0.26, ridge=0.19
    return weights
```

**最终预测**：
```
ensemble = w_xgb × pred_xgb + w_lgb × pred_lgb + w_catb × pred_catb + w_ridge × pred_ridge
```

### 8.4 负值处理

负荷不可能为负数，所以最后做一个截断：
```python
ensemble = np.maximum(ensemble, 0)
```

---

## 9. 模型包装器与推理流程

### 9.1 为什么需要包装器

训练完模型后，预测时需要很多上下文信息（特征列表、shift 信息、延迟信息等）。`models_pkg/wrapper.py` 中的 `LoadForecastWrapper` 把这些都打包在一起：

```python
class LoadForecastWrapper(mlflow.pyfunc.PythonModel):
    def __init__(self, ...):
        self.total_model = total_model           # 训练好的模型字典
        self.total_feature_list = total_feature_list  # 特征列表
        self.daily_horizon = daily_horizon       # 日数据点数
        self.scenario = scenario                 # 场景配置
        ...

    def predict(self, context, inputs):
        # 1. 解析输入
        # 2. 确定需要预测的时间段
        # 3. 根据工作日/节假日选择对应模型
        # 4. 构建 XGBoost 输入矩阵
        # 5. 调用模型预测
        # 6. 处理数据超前/延迟情况
        # 7. 返回预测结果
```

### 9.2 MLflow 接口

包装器继承自 `mlflow.pyfunc.PythonModel`，这意味着它可以：
- 用 `pickle` 序列化保存到文件
- 用 MLflow 注册为模型版本
- 通过统一的 `predict()` 接口调用

### 9.3 预测时的特殊处理

#### 数据超前
如果部分预测时段已经有真实数据了（比如预测未来 24 小时，但前 6 小时的数据已经到了），直接用真实值替代预测值。

#### 数据延迟
如果数据有延迟（比如最新数据只到 2 小时前），需要额外预测这 2 小时的"空白期"。

---

## 10. 回测系统：如何验证模型效果

### 10.1 什么是回测

回测（Backtest）就是**用历史数据模拟真实预测过程**，验证模型在"过去"的表现。

核心原则：**不能使用未来数据**（即"数据穿越"）。

### 10.2 统一回测入口 — `run.py`

`run.py` 是配置驱动的回测入口，流程如下：

```
读取 YAML 配置
  ↓
遍历每个 parent_id / child_id 组合
  ↓
遍历回测日期范围内的每一天
  ↓
  ┌─────────────────────────────────────┐
  │ 训练阶段                              │
  │ 1. 加载历史数据（截止到当天）            │
  │ 2. 数据清洗（补全、异常检测、填补）       │
  │ 3. 特征工程                           │
  │ 4. XGBoost 训练（贝叶斯优化）           │
  │ 5. 保存模型（pickle）                  │
  └─────────────────────────────────────┘
  ↓
  ┌─────────────────────────────────────┐
  │ 预测阶段                              │
  │ 1. 加载保存的模型                      │
  │ 2. 加载预测所需数据                     │
  │ 3. 数据清洗 + 特征工程                  │
  │ 4. 调用模型预测                        │
  │ 5. 后处理（格式转换、极值约束）           │
  │ 6. 保存预测结果 CSV                    │
  └─────────────────────────────────────┘
```

### 10.3 滚动回测 — `run_weihai_backtest.py`

威海回测采用**滚动窗口**方式，更加直观：

```
数据时间线：
|←————— 历史数据 ————→|←— 预测期 —→|
2025-07-02          2026-03-31   2026-04-07

滚动回测过程：

Day 1 (预测 4月1日):
  训练数据: 3月2日 ~ 3月31日 (30天)
  预测目标: 4月1日 (96个点)

Day 2 (预测 4月2日):
  训练数据: 3月3日 ~ 4月1日 (30天)  ← 窗口向前滚动1天
  预测目标: 4月2日 (96个点)

Day 3 (预测 4月3日):
  训练数据: 3月4日 ~ 4月2日 (30天)
  预测目标: 4月3日 (96个点)

... 以此类推，直到 4月7日
```

**关键代码逻辑**：

```python
def rolling_backtest(df):
    all_days = pd.date_range("2026-04-01", "2026-04-08", freq='D', inclusive='left')

    for pred_day in all_days:
        # 1. 确定训练窗口
        train_end   = pred_day - timedelta(days=1)    # 训练截止：预测日前一天
        train_start = train_end - timedelta(days=30)  # 训练起始：往前推30天

        # 2. 切分数据
        train_raw = df[(df["record_time"] >= train_start) &
                       (df["record_time"] <= train_end)]
        test_raw  = df[(df["record_time"] >= pred_day) &
                       (df["record_time"] < pred_day + timedelta(days=1))]

        # 3. 合并后做特征工程（lag 特征需要历史数据）
        combined = pd.concat([train_raw, test_raw])
        feat_all = build_features(combined)

        # 4. 再切分回训练集和测试集
        train_feat = feat_all[feat_all["record_time"] <= train_end]
        test_feat  = feat_all[feat_all["record_time"] >= pred_day]

        # 5. 训练 4 个模型
        models, flist, weights = train_all_models(x_tr, y_tr, DAILY_HORIZON)

        # 6. 集成预测
        y_pred, single_preds = ensemble_predict(models, flist, weights, x_te)

        # 7. 评估
        metrics = evaluate(y_te.values, y_pred)
```

### 10.4 为什么要合并后再做特征工程

你可能会问：为什么不分别对训练集和测试集做特征工程？

因为 **Lag 特征需要跨越训练集和测试集的边界**。

举例：预测 4 月 1 日 10:00 的负荷，需要 `lag_1d`（3 月 31 日 10:00 的负荷）。如果单独对测试集做特征工程，就拿不到 3 月 31 日的数据。

所以流程是：
1. 合并训练集 + 测试集
2. 在合并数据上计算所有特征（lag、rolling 等自然使用历史数据）
3. 再按时间切分回训练集和测试集

这样不会造成数据穿越，因为所有特征都是基于 `shift()`（向过去看）计算的。

---

## 11. 评估指标详解

### 11.1 SMAPE（对称平均绝对百分比误差）

```
SMAPE = (2/n) × Σ |yᵢ - ŷᵢ| / (|yᵢ| + |ŷᵢ|) × 100%
```

**特点**：
- 值域 [0%, 200%]
- 对称：高估和低估的惩罚相同
- 当真实值接近 0 时不会爆炸（分母有 |ŷ| 兜底）
- 本项目的**主要评估指标**

**直觉理解**：
- SMAPE = 5% → 预测很准
- SMAPE = 10% → 还行
- SMAPE > 20% → 需要改进

### 11.2 MAE（平均绝对误差）

```
MAE = (1/n) × Σ |yᵢ - ŷᵢ|
```

**特点**：
- 单位与原始数据相同（如 kW）
- 直观：平均每个点偏差多少
- 对所有误差一视同仁

### 11.3 RMSE（均方根误差）

```
RMSE = √[(1/n) × Σ (yᵢ - ŷᵢ)²]
```

**特点**：
- 单位与原始数据相同
- 对大误差更敏感（因为平方放大了大误差）
- RMSE ≥ MAE，差距越大说明存在少数大误差

### 11.4 R²（决定系数）

```
R² = 1 - Σ(yᵢ - ŷᵢ)² / Σ(yᵢ - ȳ)²
```

**特点**：
- R² = 1 → 完美预测
- R² = 0 → 和直接用均值预测一样差
- R² < 0 → 比均值预测还差

---

## 12. 数据穿越问题与修复

### 12.1 什么是数据穿越

数据穿越（Data Leakage）是指在训练或特征构造过程中，**不小心使用了未来的数据**。这会导致回测结果虚高，但实际部署时效果很差。

### 12.2 本项目中发现的穿越问题

`evaluate_and_improve.py` 中的 `audit_data_leakage()` 识别了 6 个风险点：

#### 问题 1：Chebyshev 异常检测用全局统计量 [严重度：高]

```python
# ❌ 原始实现：用全部数据（含未来）计算 mean 和 std
mean_delta = load_delta.mean()  # 包含了未来数据的统计量！
std_delta = load_delta.std()

# ✅ 修复：用滚动窗口只看历史
mean_delta = load_delta.rolling(window, min_periods=96).mean()
std_delta = load_delta.rolling(window, min_periods=96).std()
```

#### 问题 2：KFold 随机交叉验证 [严重度：高]

```python
# ❌ 原始实现：随机分折，验证集可能包含训练集之前的数据
folds = KFold(n_splits=5, shuffle=True)
# 可能出现：训练集 = [3月1日, 3月3日, 3月5日]
#           验证集 = [3月2日, 3月4日]  ← 3月2日在3月3日之前！

# ✅ 修复：时序分折，验证集始终在训练集之后
tscv = TimeSeriesSplit(n_splits=5)
# 保证：fold1 训练[1-60], 验证[61-80]
#       fold2 训练[1-80], 验证[81-100]
#       ...
```

**TimeSeriesSplit 图解**：

```
数据: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]

Fold 1: 训练 [1-3]        验证 [4-6]
Fold 2: 训练 [1-6]        验证 [7-9]
Fold 3: 训练 [1-9]        验证 [10-12]
Fold 4: 训练 [1-12]       验证 [13-15]

vs KFold (随机):
Fold 1: 训练 [2,5,7,10,13,14] 验证 [1,3,6,8,9,11,12,15]  ← 时间混乱！
```

#### 问题 3：rolling(center=True) [严重度：高]

```python
# ❌ center=True：窗口以当前点为中心，包含未来数据
load.rolling(24, center=True).mean()
# 对于 t=12 的点，窗口是 [t-12, t-11, ..., t, ..., t+11, t+12]
#                                              ↑ 未来数据！

# ✅ center=False：窗口只看过去
load.rolling(24, center=False).mean()
# 对于 t=12 的点，窗口是 [t-23, t-22, ..., t-1, t]
#                         全部是历史数据 ✓
```

#### 问题 4：DataFiller 周期性填补 [严重度：中]

填补缺失值时可能用到未来数据。修复方案：只向前（过去）查找填补值。

#### 问题 5：训练阶段 forecast_timestamps 超出范围 [严重度：中]

特征工程中生成的预测时间戳可能超出训练数据范围，导致 shift 操作引入未来数据。

#### 问题 6：get_completed_timestamp 固定窗口 [严重度：低]

训练数据截取时，如果不小心包含了预测日的数据。

### 12.3 修复后的改进

`evaluate_and_improve.py` 提供了完整的修复版实现：
- `chebyshev_detector_no_leakage()`：滚动窗口异常检测
- `build_features_no_leakage()`：无穿越特征工程
- `xgb_train_with_tscv()`：TimeSeriesSplit 交叉验证
- `rolling_backtest()`：严格的滚动回测

---

## 13. 完整执行流程串讲

### 13.1 以威海回测为例的完整流程

下面以 `run_weihai_backtest.py` 为例，串讲从数据到结果的完整流程。

#### 第一步：加载数据

```python
df = load_weihai_data()
# 读取 Excel → 筛选 feature_name=="load" → 重采样到 15min → 插值填补
# 结果：一个 DataFrame，列 = [record_time, load]
# 时间范围：2025-07-02 ~ 2026-04-07，约 27000 行
```

#### 第二步：进入滚动回测循环

```python
# 预测 2026-04-01 这一天
pred_day = "2026-04-01"
train_end = "2026-03-31"
train_start = "2026-03-01"  # 往前 30 天
```

#### 第三步：切分数据

```python
train_raw = df[3月1日 ~ 3月31日]   # 约 2880 行 (30天 × 96点)
test_raw  = df[4月1日]              # 96 行 (1天 × 96点)
combined  = concat(train_raw, test_raw)  # 2976 行
```

#### 第四步：特征工程

```python
feat_all = build_features(combined)
# 输入：2976 行 × 2 列 (record_time, load)
# 输出：2976 行 × ~80 列
#
# 新增的列包括：
# - 时间特征：is_holiday, day, month, hour, period, hour_sin, hour_cos, ...
# - Lag 特征：lag_1d, lag_2d, lag_7d, lag_14d, lag_28d, same_time_2w, ...
# - 差分特征：diff_1, diff_96, diff_192, ...
# - 滚动统计：roll_4_mean, roll_4_std, roll_24_mean, roll_96_max, ...
# - 日统计：day_mean, day_max, day_min, day_std, day_pv, day_rate, ...
```

#### 第五步：切分训练/测试特征

```python
train_feat = feat_all[record_time <= "2026-03-31"]  # 2880 行 × 80 列
test_feat  = feat_all[record_time >= "2026-04-01"]  # 96 行 × 80 列

# 去掉非特征列
drop_cols = ["load", "record_time", "date"]
feature_cols = [剩余的数值列]  # 约 77 个特征

x_tr = train_feat[feature_cols]  # 2880 × 77
y_tr = train_feat["load"]        # 2880 × 1
x_te = test_feat[feature_cols]   # 96 × 77
y_te = test_feat["load"]         # 96 × 1（真实值，用于评估）
```

#### 第六步：训练 4 个模型

```python
models, flist, weights = train_all_models(x_tr, y_tr, forecast_length=96)

# 内部过程：
# 1. XGBoost：贝叶斯优化 (3+12=15 次试验) × TimeSeriesSplit 5折
#    → 最优参数 → 全量训练 → 返回 (model, oof_rmse)
# 2. LightGBM：同上
# 3. CatBoost：同上
# 4. Ridge：TimeSeriesSplit 5折评估 → 全量训练

# 计算自适应权重
# 假设 oof_rmse: xgb=85, lgb=92, catb=88, ridge=120
# → weights: xgb=0.30, lgb=0.28, catb=0.29, ridge=0.13
```

#### 第七步：集成预测

```python
y_pred, single_preds = ensemble_predict(models, flist, weights, x_te)

# 各模型分别预测 96 个点
# pred_xgb  = [1520, 1498, 1475, ...]  (96个值)
# pred_lgb  = [1515, 1502, 1480, ...]
# pred_catb = [1518, 1500, 1478, ...]
# pred_ridge= [1530, 1510, 1490, ...]

# 加权集成
# y_pred = 0.30×pred_xgb + 0.28×pred_lgb + 0.29×pred_catb + 0.13×pred_ridge
# y_pred = [1519.3, 1500.8, 1477.9, ...]

# 负值截断
# y_pred = max(y_pred, 0)
```

#### 第八步：评估

```python
metrics = evaluate(y_te.values, y_pred, label="2026-04-01")
# → SMAPE=3.25%, MAE=45.2, RMSE=62.8
```

#### 第九步：保存结果

```python
# 保存模型
pickle.dump({"models": models, "feature_list": flist, "weights": weights},
            open("output/weihai_backtest/models/ensemble_model_2026-04-01.pkl", "wb"))

# 保存预测结果到 DataFrame
day_res = DataFrame({
    "record_time": [...],
    "true": y_te.values,
    "pred": y_pred,
    "pred_xgb": single_preds['xgb'],
    "pred_lgb": single_preds['lgb'],
    "pred_catb": single_preds['catb'],
    "pred_ridge": single_preds['ridge'],
    "pred_day": "2026-04-01",
})
```

#### 第十步：重复 Day 2 ~ Day 7

训练窗口向前滚动一天，重复上述过程。

#### 第十一步：汇总评估 + 可视化

```python
# 合并 7 天的结果
results = concat(所有天的 day_res)

# 总体评估
overall = evaluate(results["true"], results["pred"])

# 生成 4 张图
plot_results(results, OUTPUT_DIR)
# → forecast_vs_true.png    全局对比图
# → daily_details.png       逐天详情图
# → daily_smape_bar.png     SMAPE 柱状图
# → scatter.png             散点图
```

### 13.2 以 AESC 回测为例的完整流程

`run.py` 的流程与威海类似，但有几个关键区别：

| 维度 | 威海回测 | AESC 回测 |
|------|---------|----------|
| 入口 | `run_weihai_backtest.py` | `run.py --config configs/aesc.yaml` |
| 数据源 | 本地 Excel | 本地 CSV（通过 `offline_load_data`） |
| 模型 | 4 模型集成 | 单 XGBoost |
| 特征 | 纯负荷特征 | 负荷 + 气象特征 |
| 特征工程 | `build_features()`（本地实现） | `add_more_features_d()`（engine.py） |
| 训练 | 每天重训 | 每天重训 |
| 模型保存 | pickle | pickle（MLflow 包装器） |
| 预测 | 直接调用 `model.predict()` | 通过 `LoadForecastWrapper.predict()` |
| 后处理 | 无 | `predict_format_transform()`（极值约束等） |

### 13.3 关键文件调用关系图

```
run.py
  ├── configs/schema.py          → 加载 YAML 配置
  ├── data_fetch/fetcher.py      → offline_load_data() 加载数据
  ├── data_process.py (外部)     → 数据清洗流水线
  │     ├── get_train_status()
  │     ├── get_timestamp_freq()
  │     ├── get_completed_timestamp()
  │     ├── chebyshev_detector()
  │     └── get_completed_df()
  ├── features/engine.py         → add_more_features_d() 特征工程
  │     ├── common/holidays.py   → if_workday() 节假日判断
  │     ├── common/constants.py  → ScenarioConfig 场景配置
  │     └── add_features.py (外部) → 统计/滚动/差分特征函数
  ├── models_pkg/trainer.py      → model_prefer_trainer_d() 模型训练
  │     └── bayes_opt            → 贝叶斯超参数优化
  ├── models_pkg/wrapper.py      → LoadForecastWrapper 模型包装
  └── utils.py (外部)            → 后处理工具函数
```

---

## 附录 A：快速运行指南

### 环境准备

```bash
pip install xgboost lightgbm catboost scikit-learn
pip install bayesian-optimization
pip install pandas numpy openpyxl
pip install chinese-calendar pytz
pip install mlflow loguru
pip install matplotlib
```

### 运行威海回测

```bash
python run_weihai_backtest.py
```

输出在 `output/weihai_backtest/` 目录下。

### 运行 AESC 回测

```bash
python run.py --config configs/aesc.yaml
```

> 注意：AESC 回测依赖外部模块（`data_process.py`、`db_data_fetch.py`、`utils.py`、`add_features.py`），这些文件不在当前仓库中，需要从原始项目获取。

### 运行精度评估

```bash
python evaluate_and_improve.py
```

---

## 附录 B：常见问题

### Q1：为什么有些模块（data_process.py、utils.py）不在仓库里？

这个项目是从一个更大的项目中重构出来的。`processing/pipeline.py`、`evaluation/metrics.py`、`features/helpers.py` 都是对外部模块的**重导出包装**，方便未来逐步迁移。

### Q2：ScenarioConfig 的 `use_separate_modeling` 和 YAML 中的 `separate_modeling` 有什么关系？

`ScenarioConfig.use_separate_modeling` 是场景的**默认值**，YAML 中的 `separate_modeling` 是**用户覆盖值**。实际运行时以 YAML 配置为准。

### Q3：为什么威海回测不用气象数据？

威海数据集只包含负荷数据，没有对应的气象数据。所以 `run_weihai_backtest.py` 只使用纯负荷特征（时间 + Lag + 滚动统计）。

### Q4：`forecast_horizon` 在不同场景下的含义？

- DI（日内）：单位是**小时**（如 `forecast_horizon=6` 表示预测未来 6 小时）
- 其他场景：单位是**天**（如 `forecast_horizon=1` 表示预测未来 1 天）

### Q5：什么是 `prefer_unit_len`？

选优验证的长度倍数。训练完模型后，用最近 `prefer_unit_len × forecast_length` 个数据点来评估模型效果（SMAPE），决定是否需要重训。

---

## 附录 C：术语表

| 术语 | 英文 | 含义 |
|------|------|------|
| 负荷 | Load | 用电量/功率 |
| 回测 | Backtest | 用历史数据模拟预测过程 |
| 数据穿越 | Data Leakage | 训练/特征中使用了未来数据 |
| 特征工程 | Feature Engineering | 从原始数据构造模型输入特征 |
| 滞后特征 | Lag Feature | 历史同时刻的值 |
| 滚动统计 | Rolling Statistics | 滑动窗口内的统计量 |
| 交叉验证 | Cross Validation | 将数据分成多折轮流训练/验证 |
| 超参数 | Hyperparameter | 模型训练前需要设定的参数 |
| 集成学习 | Ensemble Learning | 组合多个模型的预测结果 |
| 梯度提升 | Gradient Boosting | 逐步添加弱学习器修正残差 |
| 正则化 | Regularization | 限制模型复杂度防止过拟合 |
| OOF | Out-of-Fold | 交叉验证中验证集的预测结果 |
| SMAPE | Symmetric MAPE | 对称平均绝对百分比误差 |
| 峰谷差 | Peak-Valley Difference | 日最大负荷与最小负荷之差 |
| 负荷率 | Load Factor | 日平均负荷 / 日最大负荷 |

<!-- @AI_GENERATED: end -->
