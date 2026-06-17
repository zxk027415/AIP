# @AI_GENERATED: Kiro v1.0
# 光伏发电功率预测 Skill

这是一个自主研究实验，让 LLM Agent 优化光伏发电功率预测模型。

## 目标

**核心指标：MAPE（平均绝对百分比误差）**

目标是在固定时间预算内，通过修改模型架构、超参数、特征工程等方式，获得最低的 MAPE。

## 设置

开始新实验时，与用户协商：

1. **确定运行标签**：基于日期提议标签（如 `mar23`）。分支 `pv-forecast/<tag>` 必须不存在。
2. **创建分支**：`git checkout -b pv-forecast/<tag>`
3. **阅读相关文件**：
   - `README.md` — 项目背景
   - `prepare.py` — 固定的数据准备、评估函数（只读）
   - `train.py` — 你可以修改的训练代码
4. **验证数据**：确认 `data/` 目录包含光伏数据集
5. **初始化 results.tsv**：创建仅包含表头的文件
6. **确认并开始**

## 实验规则

**你可以做的：**
- 修改 `train.py` — 这是唯一可编辑的文件
- 修改模型架构（LSTM、GRU、Transformer、集成模型等）
- 修改超参数（学习率、批次大小、隐藏层维度等）
- 修改特征工程（时间特征、滞后特征、滚动统计等）
- 修改训练策略（早停、学习率调度、正则化等）

**你不能做的：**
- 修改 `prepare.py` — 它是只读的
- 安装新的依赖包
- 修改评估函数 `evaluate_mape`
- 使用未来数据（数据泄露）

**时间预算**：每次实验固定 5 分钟训练时间

**简洁性原则**：同等效果下，更简单的代码更好。删除代码获得相同效果是胜利。

## 输出格式

训练脚本完成后打印摘要：

```
---
mape:             8.5432
rmse:             125.67
r2:               0.9234
training_seconds: 300.1
total_seconds:    325.9
peak_vram_mb:     4096.0
num_epochs:       50
model_params:     125000
```

## 结果记录

实验完成后，记录到 `results.tsv`（制表符分隔）：

```
commit	mape	rmse	memory_gb	status	description
```

示例：
```
commit	mape	rmse	memory_gb	status	description
a1b2c3d	12.3456	156.78	2.0	keep	baseline - 线性回归
b2c3d4e	8.5432	125.67	4.0	keep	LSTM 2层 hidden=64
c3d4e5f	15.0000	200.00	4.0	discard	GRU 效果更差
d4e5f6g	0.0000	0.00	0.0	crash	Transformer OOM
```

## 实验循环

在专用分支上运行（如 `pv-forecast/mar23`）。

永久循环：

1. 查看当前 git 状态
2. 修改 `train.py` 尝试新想法
3. git commit
4. 运行实验：`python train.py > run.log 2>&1`
5. 读取结果：`grep "^mape:\|^rmse:\|^peak_vram_mb:" run.log`
6. 如果 grep 输出为空，运行崩溃。运行 `tail -n 50 run.log` 查看错误
7. 记录结果到 tsv
8. 如果 MAPE 改善（更低），保留 commit
9. 如果 MAPE 相同或更差，git reset 回滚

**超时**：每次实验应在 ~5 分钟内完成。超过 10 分钟则终止并视为失败。

**崩溃处理**：如果是简单错误（拼写、导入），修复后重试。如果想法本身有问题，跳过并记录 "crash"。

**永不停止**：实验循环开始后，不要暂停询问用户。用户可能在睡觉，期望你持续工作直到被手动停止。

## 领域知识

### 光伏发电特点
- 日间发电，夜间为零
- 受天气影响大（云层、温度、湿度）
- 季节性变化明显
- 早晚功率变化快，中午相对稳定

### 常用特征
- 时间特征：小时、日期、月份、星期
- 气象特征：辐照度、温度、湿度、风速
- 滞后特征：前1小时、前1天同时刻
- 滚动统计：过去N小时均值、标准差

### 常用模型
- 基线：线性回归、随机森林
- 时序：LSTM、GRU、TCN
- 高级：Transformer、集成模型
# @AI_GENERATED: end
