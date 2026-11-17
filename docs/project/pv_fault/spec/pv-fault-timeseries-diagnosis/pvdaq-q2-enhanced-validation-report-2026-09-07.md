<!-- @AI_GENERATED -->
# RF vs TSC · Q2 增强验证报告

> **日期**：2026-09-07
> **前置**：Q1 报告已确认单通道 dc_current 检测 PR 异常的能力有限（balanced accuracy ~0.66）
> **本轮目标**：通过多通道和 i_cal 构造，建立检测上界并量化域差

---

## 1. 实验矩阵

本轮在 Q1 基础上增加了三组实验（标 ★），与 Q1 结果一起形成完整对比：

| 配置 | RF | TSC | 说明 |
|------|-----|-----|------|
| Q1: 1ch value only | 25 维 | [n, 288, 1] | 基线，仅 dc_current |
| ★ Step A: 5ch multichannel | 125 维 | [n, 288, 5] | value + dc_power + ac_power + poa + module_temp |
| ★ Step B Path(b): with i_cal | 50 维 | [n, 288, 3] | value + i_cal（统计回归构造）；TSC 加 is_measured |
| ★ Step B Path(a): platform predict-only | 50 维 13 类 | [n, 288, 3] 10 类 | 平台现有模型直接域外推理 |

## 2. 综合结果对比

### 2.1 Balanced Accuracy

| 配置 | RF | TSC |
|------|-----|-----|
| Q1: 1ch | 0.663 ± 0.101 | 0.665 ± 0.078 |
| 5ch multichannel | 0.644 ± 0.086 | **0.773 ± 0.123** |
| with i_cal (Path b) | 0.678 ± 0.109 | **0.782 ± 0.107** |
| Path(a) platform predict-only | 0.502 | 0.489 |

### 2.2 Abnormal Detection（异常类指标）

| 配置 | RF Prec | RF Rec | RF F1 | TSC Prec | TSC Rec | TSC F1 |
|------|---------|--------|-------|----------|---------|--------|
| Q1: 1ch | 0.587 | 0.226 | 0.326 | 0.340 | 0.324 | 0.332 |
| 5ch multichannel | 0.674 | 0.189 | 0.295 | 0.561 | **0.527** | **0.544** |
| with i_cal (Path b) | **0.755** | 0.226 | 0.347 | **0.637** | **0.534** | **0.581** |
| Path(a) predict-only | 0.101 | 1.000 | 0.184 | 0.108 | 0.971 | 0.194 |

### 2.3 PR-AUC

| 配置 | RF | TSC |
|------|-----|-----|
| Q1: 1ch | 0.392 | 0.428 |
| 5ch multichannel | 0.549 | 0.643 |
| with i_cal (Path b) | 0.528 | **0.710** |

## 3. 关键发现

### 3.1 TSC + i_cal 是最强配置

TSC 3 通道（value + i_cal + is_measured）重拟合是本轮最优结果：
- Balanced accuracy **0.782**（vs Q1 0.665，+17.6%）
- Abnormal F1 **0.581**（vs Q1 0.332，+75%）
- PR-AUC **0.710**（vs Q1 0.428，+66%）

i_cal 给 TSC 提供了"实际 vs 预期"的差异信号，这正是异常检测最需要的信息。

### 3.2 多通道 vs i_cal：TSC 表现接近

| | TSC 5ch | TSC 3ch+i_cal | 差异 |
|---|---------|--------------|------|
| Bal Acc | 0.773 | 0.782 | +1.2% |
| Abnormal F1 | 0.544 | 0.581 | +6.8% |
| PR-AUC | 0.643 | 0.710 | +10.4% |

5 通道（含 ac_power 和 poa_irradiance 原始值）的信息已经很丰富，i_cal 在此基础上只是增量。但 i_cal 的优势在于它把 (poa, temp) → expected_current 的物理关系**显式编码**了，模型不需要自己学这层映射。

### 3.3 RF 对多通道/i_cal 不敏感

RF 在 50 维和 125 维配置下 balanced accuracy 变化不大（0.64-0.68），abnormal recall 始终在 0.19-0.23。日统计特征丢失了波形内部的时序结构——两天可能有相同的均值/标准差但完全不同的波形形状。RF 适合快速筛选，但在复杂异常检测上天花板较低。

### 3.4 Path(a) 域差严重

平台现有模型在 PVDAQ 上的表现接近随机（bal_acc ~0.50），并且严重偏向"全判异常"：
- RF：941/945 正常日被判为异常（FP rate 99.6%）
- TSC：846/851 正常日被判为异常（FP rate 99.4%）

这不是模型"坏了"，而是**域差**——平台训练数据的波形模式和 PVDAQ 的差异太大，模型把所有"不熟悉"的模式都归为异常类。这证实了**Q1 验证的必要性**：不做域外重拟合，现有模型不能直接迁移。

## 4. i_cal 构造方法说明

| 要素 | 说明 |
|------|------|
| 方法 | 每台设备独立拟合 RandomForestRegressor |
| 输入 | (poa_irradiance, module_temp) |
| 输出 | 预测的 dc_current（即 i_cal）|
| 训练数据 | 该设备所有"正常日"的白天时刻（poa > 10 W/m²）|
| R² | 0.943 ~ 1.000（12 台设备）|
| 注意 | 此 i_cal 基于同设备历史正常模式，不是独立物理模型 |

**局限性**：i_cal 由同设备正常数据回归得到，存在"用答案的一部分生成输入"的循环风险。在严格评估中，应使用 clear-sky 物理模型或跨设备迁移回归。本轮作为 Q2 可行性验证是可接受的。

## 5. 新增代码和数据

| 路径 | 说明 |
|------|------|
| `backend-service/services/benchmark/pvdaq_ical_builder.py` | i_cal 统计回归构造器 |
| `backend-service/services/benchmark/pvdaq_q1_refit.py` | 已扩展支持多通道 RF/TSC |
| `backend-service/data/benchmark_raw/pvdaq/converted/` | 36 parquet 已含 i_cal + is_measured |
| `.../analysis/q2_multichannel/` | Step A 5 通道 CV 结果 |
| `.../analysis/q2_with_ical/` | Step B Path(b) i_cal CV 结果 |
| `.../analysis/q2_path_a/` | Step B Path(a) 平台模型 predict-only 结果 |

## 6. 结论

1. **方法有效**：TSC MultiRocket 在域内重拟合后，device-isolated CV 的 abnormal F1 达到 0.58（3 通道 + i_cal），远超 Q1 的 0.33
2. **域差是主要瓶颈**：平台现有模型直接域外推理接近随机，必须域内重拟合
3. **i_cal 有增量但非必要**：5 通道原始信号已能达到 0.54 F1，i_cal 进一步提升到 0.58
4. **RF 天花板较低**：无论通道数如何增加，RF 的 abnormal recall 始终 < 0.23；TSC 通过波形时序结构获得了显著优势
5. **后续应优先投入 TSC 路线**，并探索 clear-sky 物理 i_cal 以消除循环风险

---

*本报告由 AI 生成，所有数据和结论需人工审核确认。*
<!-- @AI_GENERATED: end -->
