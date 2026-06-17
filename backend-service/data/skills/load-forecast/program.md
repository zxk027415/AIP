# @AI_GENERATED
# 电力负荷预测 AutoResearch Skill

这是一个自主研究实验，让 LLM Agent 优化电力负荷预测模型。

## 目标

**核心指标：SMAPE（对称平均绝对百分比误差）**

目标是在固定时间预算内，通过修改模型架构、超参数、特征工程等方式，获得最低的 SMAPE。

## 设置

开始新实验时，与用户协商：

1. **确定运行标签**：基于日期提议标签（如 `apr26`）。分支 `load-forecast/<tag>` 必须不存在。
2. **创建分支**：`git checkout -b load-forecast/<tag>`
3. **阅读相关文件**：
   - `prepare.py` — 固定的数据准备、评估函数（只读）
   - `train.py` — 你可以修改的训练代码
4. **验证数据**：确认数据文件可用（CSV 或数据库连接）
5. **初始化 results.tsv**：创建仅包含表头的文件
6. **确认并开始**

## 实验规则

**你可以做的：**
- 修改 `train.py` — 这是唯一可编辑的文件
- 修改模型架构（XGBoost、LightGBM、CatBoost、随机森林、LSTM 等）
- 修改超参数（学习率、树深度、正则化参数、贝叶斯优化试验次数等）
- 修改特征工程（时间特征、Lag 特征、滚动统计、日统计、气象交叉特征等）
- 修改训练策略（贝叶斯超参优化、网格搜索、早停、交叉验证等）
- 修改数据预处理（异常值处理阈值、缺失值填充策略等）

**你不能做的：**
- 修改 `prepare.py` — 它是只读的
- 安装新的依赖包
- 修改评估函数 `evaluate_smape`、`evaluate_mae`、`evaluate_rmse`
- 使用未来数据（数据泄露）

**时间预算**：每次实验固定 10 分钟训练时间（负荷预测训练通常比光伏更耗时）

**简洁性原则**：同等效果下，更简单的代码更好。删除代码获得相同效果是胜利。

## 输出格式

训练脚本完成后打印摘要：

```
---
smape:            4.5678
mae:              12.34
rmse:             18.56
training_seconds: 450.2
total_seconds:    480.5
scenario:         D
forecast_horizon: 1
model_type:       xgboost
n_trials:         50
```

## 结果记录

实验完成后，记录到 `results.tsv`（制表符分隔）：

```
commit	smape	mae	rmse	scenario	status	description
```

示例：
```
commit	smape	mae	rmse	scenario	status	description
a1b2c3d	6.7890	15.23	22.45	D	keep	baseline - XGBoost 默认参数
b2c3d4e	4.5678	12.34	18.56	D	keep	XGBoost + 贝叶斯优化 50 trials
c3d4e5f	8.1234	20.00	30.00	D	discard	LightGBM 效果更差
d4e5f6g	0.0000	0.00	0.00	D	crash	CatBoost OOM
```

## 实验循环

在专用分支上运行（如 `load-forecast/apr26`）。

永久循环：

1. 查看当前 git 状态
2. 修改 `train.py` 尝试新想法
3. git commit
4. 运行实验：`python train.py > run.log 2>&1`
5. 读取结果：`grep "^smape:\|^mae:\|^rmse:" run.log`
6. 如果 grep 输出为空，运行崩溃。运行 `tail -n 50 run.log` 查看错误
7. 记录结果到 tsv
8. 如果 SMAPE 改善（更低），保留 commit
9. 如果 SMAPE 相同或更差，git reset 回滚

**超时**：每次实验应在 ~10 分钟内完成。超过 20 分钟则终止并视为失败。

**崩溃处理**：如果是简单错误（拼写、导入），修复后重试。如果想法本身有问题，跳过并记录 "crash"。

**永不停止**：实验循环开始后，不要暂停询问用户。用户可能在睡觉，期望你持续工作直到被手动停止。

## 领域知识

### 电力负荷特点
- 明显的日周期性（白天高、夜间低）
- 工作日与周末/节假日模式差异大
- 受气温影响显著（夏季空调负荷、冬季取暖负荷）
- 存在产业结构影响（工业负荷、商业负荷、居民负荷）
- 特殊事件影响（大型活动、极端天气）

### 六种预测场景
| 场景 | 代码 | 时间范围 | 典型用途 |
|------|------|---------|---------|
| 日内 | DI | 0-4小时 | 实时调度 |
| 日前 | D | 次日24小时 | 日前调度、电力交易 |
| 周内 | WI | 本周剩余 | 检修计划 |
| 周前 | W | 下周7天 | 周度计划 |
| 月内 | MI | 本月剩余 | 月度调整 |
| 月前 | M | 下月整月 | 容量规划 |

### 常用特征
- 时间特征：小时、日期、月份、星期、是否工作日、是否节假日
- Lag 特征：前1小时、前1天同时刻、前1周同时刻
- 滚动统计：过去 N 小时均值、标准差、最大值、最小值
- 日统计：当日累计负荷、当日峰值、当日谷值
- 气象特征：温度、湿度、风速（如有）
- Shift 对齐特征：根据场景类型对齐预测窗口

### 常用模型
- 基线：XGBoost（当前默认）
- 替代：LightGBM、CatBoost、随机森林
- 深度学习：LSTM、GRU（适合长序列）
- 集成：Stacking、Blending

### 超参优化
- 当前使用贝叶斯超参优化（Optuna）
- 关键超参：max_depth、learning_rate、n_estimators、subsample、colsample_bytree
- 建议试验次数：50-200 次
# @AI_GENERATED: end
