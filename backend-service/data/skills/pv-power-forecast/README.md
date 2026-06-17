# @AI_GENERATED: Kiro v1.0
# 光伏发电功率预测 Skill

基于 [autoresearch](https://github.com/karpathy/autoresearch) 模式的光伏发电功率预测自主研究 Skill。

## 概述

这个 Skill 允许 AI Agent 自主优化光伏发电功率预测模型。Agent 可以修改模型架构、超参数、特征工程等，目标是最小化 MAPE（平均绝对百分比误差）。

## 文件结构

```
pv-power-forecast/
├── README.md           # 本文件
├── program.md          # Agent 指令（定义实验规则和流程）
├── prepare.py          # 数据准备和评估（只读）
├── train.py            # 训练脚本（Agent 可编辑）
├── data/               # 数据目录
│   └── pv_power_sample.csv
└── results.tsv         # 实验结果记录（运行时生成）
```

## 快速开始

### 1. 准备数据

```bash
# 生成模拟数据（90天）
python prepare.py --download --days 90
```

### 2. 运行基线实验

```bash
python train.py
```

### 3. 查看结果

```bash
grep "^mape:" run.log
```

## 核心指标

- **MAPE**（主要指标）：平均绝对百分比误差，越低越好
- **RMSE**：均方根误差
- **R²**：决定系数

## Agent 可修改内容

在 `train.py` 中，Agent 可以修改：

1. **模型类型**：`MODEL_TYPE = "linear" | "mlp" | "lstm" | "gru"`
2. **超参数**：`HIDDEN_SIZE`, `NUM_LAYERS`, `DROPOUT`, `LEARNING_RATE`, `BATCH_SIZE`
3. **特征选择**：`FEATURE_COLUMNS` 列表
4. **训练策略**：早停、学习率调度等

## 约束

- 时间预算：5 分钟
- 不能修改 `prepare.py`
- 不能安装新依赖
- 不能使用未来数据（数据泄露）

## 实验循环

1. 修改 `train.py`
2. `git commit`
3. `python train.py > run.log 2>&1`
4. 检查结果：`grep "^mape:" run.log`
5. 如果改善，保留；否则回滚

## 参考

- [autoresearch](https://github.com/karpathy/autoresearch) - 原始灵感来源
- [光伏发电功率预测模板](../../../data/workflows_enhanced/workflow-pv-power-demo.json)
# @AI_GENERATED: end
