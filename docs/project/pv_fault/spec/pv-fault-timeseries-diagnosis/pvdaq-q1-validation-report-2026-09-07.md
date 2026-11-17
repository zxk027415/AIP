<!-- @AI_GENERATED -->
# RF vs TSC · Q1 检测验证报告

> **日期**：2026-09-07
> **目标**：在 PVDAQ 公开多设备数据上验证天路径 Q1（检测通用性）——RF 与 TSC 是否"能跑通 + 能检测异常"
> **两条路**：Path(a) predict-only 现有模型 / Path(b) 方法重拟合
> **约束**：首轮不构造 `i_cal`，真值来源为物理功率 PR

---

## 1. 实验概览

| 维度 | 说明 |
|------|------|
| 数据来源 | PVDAQ 公开数据集，12 系统 × 3 月 = 1,083 天 |
| 转换 | 原始 daily 长表 → 5min 宽表（system 34 保持 15min）|
| 金标 | 物理 PR 真值：PR < 0.7 × baseline → abnormal |
| 标注统计 | 1,051 标注日 = 945 normal + 106 abnormal（10.1%）|
| CV 策略 | Device-isolated GroupShuffleSplit，5 折，test_size=30% |

## 2. Path(a)：Predict-Only（现有模型直接域外预测）

### 2.1 结论

**两个模型均因缺少 `i_cal` 通道无法直接运行。**

| 模型 | 输入合同 | 缺 `i_cal` 行为 | 可运行？ |
|------|---------|----------------|---------|
| pv_day RF | 50 维（25 `value_*` + 25 `i_cal_*`）| `feature_select` 后特征数不匹配 → sklearn 报错 | ❌ |
| pv_tsc TSC (MultiRocket) | 3 通道 `[value, i_cal, is_measured]` × 288 点 | `_predict_grid_target_day` 返回 `error="缺少列: ['i_cal']"` | ❌ |

### 2.2 说明

- PVDAQ 数据不包含 `i_cal`（预测电流基线），这是平台自有的半经验计算值
- 交接文档已锁定决策：**首轮不构造 `i_cal`**，因为半经验构造会污染主结论
- 此结论不代表模型"无法工作"，而是**输入合同不兼容**——模型依赖的特征在域外数据中不存在
- 这是 Q1 验证的预期结果之一，诚实记录

### 2.3 不做 sensitivity 分析的原因

- 用 `value` 复制填充 `i_cal` 或用零值填充，产出的结果不是"诚实直接预测"
- 如需此类分析，应在后续 Q2 中明确标注为"合同降级预测"，不混入本报告

## 3. Path(b)：方法重拟合

### 3.1 RF 二分类

| 指标 | 值 |
|------|-----|
| 输入 | 25 维 `value_*` 日统计特征（与平台 `_extract_rfc_features` 对齐，去掉 `i_cal_*`）|
| 模型 | RandomForestClassifier, 200 trees, class_weight=balanced |
| 样本数 | 1,051（12 设备）|
| Balanced Accuracy | **0.663 ± 0.101** |
| PR-AUC | 0.392 |
| Abnormal Precision | 0.587 |
| Abnormal Recall | 0.226 |
| Abnormal F1 | 0.326 |

**混淆矩阵（pooled across 5 folds）**：

|  | 预测 Normal | 预测 Abnormal |
|---|---:|---:|
| 真 Normal | 1523 | 26 |
| 真 Abnormal | 127 | 37 |

**解读**：RF 的误报率很低（precision 0.59），但漏检率高（recall 0.23）——大部分异常日被判为正常。这可能因为仅靠 dc_current 的统计量难以区分"低效运行"与"正常运行"，尤其在跨设备泛化时。

### 3.2 TSC MultiRocket 二分类

| 指标 | 值 |
|------|-----|
| 输入 | 单通道 `value`（dc_current）× 288 点日波形 |
| 模型 | MultiRocketClassifier (aeon) |
| 样本数 | 956（11 设备，排除 system 34 的 15min 数据）|
| Balanced Accuracy | **0.665 ± 0.078** |
| PR-AUC | 0.428 |
| Abnormal Precision | 0.340 |
| Abnormal Recall | 0.324 |
| Abnormal F1 | 0.332 |

**混淆矩阵（pooled across 5 folds）**：

|  | 预测 Normal | 预测 Abnormal |
|---|---:|---:|
| 真 Normal | 1508 | 93 |
| 真 Abnormal | 100 | 48 |

**解读**：TSC 的 abnormal recall 比 RF 高（0.32 vs 0.23），但 precision 更低（0.34 vs 0.59）。波形模式捕捉到了更多异常，但也把更多正常日误判为异常。

### 3.3 RF vs TSC 对比

| 指标 | RF | TSC | 胜出 |
|------|-----|-----|------|
| Balanced Accuracy | 0.663 ± 0.101 | 0.665 ± 0.078 | 持平 |
| PR-AUC | 0.392 | 0.428 | TSC 略优 |
| Abnormal Recall | 0.226 | 0.324 | TSC |
| Abnormal Precision | 0.587 | 0.340 | RF |
| Abnormal F1 | 0.326 | 0.332 | 持平 |
| 跨折稳定性 (std) | 0.101 | 0.078 | TSC 更稳 |

**总结**：两个模型在 device-isolated CV 下表现相当（balanced accuracy ~0.66）。这是**仅用 dc_current 单通道、无 `i_cal`、跨设备泛化**的条件下可预期的结果——PR 真值反映的是 AC/POA 层面的效率变化，而模型只看到 DC 电流波形，信息链路存在天然 gap。

## 4. 数据质量备注

### 4.1 过程中发现并修复的问题

| 问题 | 影响 | 修复 |
|------|------|------|
| system 1289 `poa_irradiance_2`（metric 1058）大量 -7999 坏值 | POA 被污染，覆盖门仅 3/93 天通过 | 增加 PHYSICAL_FLOOR 物理范围门（POA < -10 → NaN），修复后 92/93 天通过 |

### 4.2 已知边界条件

| 系统 | 情况 | 对结果的影响 |
|------|------|------------|
| system 36/1284/1289 | Baseline PR > 1.0 | 额定功率偏大，PR 缩放正确但绝对值偏高 |
| system 1422 | 2016-06 AC power 为负 | 真实 AC 掉电异常日，被正确标为 abnormal |
| system 10 | 2015-06 POA 71.6% NaN | Sentinel 清洗正确，大部分日期被覆盖门排除 |
| system 34 | 15min 原生采样 | RF 参与（96 点日统计特征可算），TSC 排除（不混入 288 点模型）|
| RTC 系统 (1403/1422/1423/1429) | DC power 由 V×I 重建 | PR 偏低 0.2-0.45，反映重建精度和系统效率差异 |

## 5. 产出文件清单

| 路径 | 说明 |
|------|------|
| `backend-service/services/benchmark/pvdaq_converter.py` | PVDAQ→pv schema 转换器（含 sentinel 清洗、PHYSICAL_FLOOR、V×I 重建）|
| `backend-service/services/benchmark/pvdaq_pr_truth.py` | PR 物理真值生成器（日级 PR、覆盖门、二分类金标）|
| `backend-service/services/benchmark/pvdaq_q1_refit.py` | Path(b) 方法重拟合（RF+TSC device-isolated CV）|
| `backend-service/data/benchmark_raw/pvdaq/converted/` | 36 个转换后 parquet（12 系统 × 3 月）|
| `backend-service/data/benchmark_raw/pvdaq/analysis/q1_daily_truth.csv` | 日级 PR 真值 + 二分类金标（1,083 行）|
| `backend-service/data/benchmark_raw/pvdaq/analysis/q1_truth_summary.csv` | 12 系统 PR 统计汇总 |
| `backend-service/data/benchmark_raw/pvdaq/analysis/q1_refit/` | RF/TSC CV 结果（fold CSV + JSON + 特征/meta）|
| 本报告 | Q1 检测验证汇总 |

## 6. 结论与建议

### Q1 验证结论

1. **"能跑通"**：✅ RF 和 TSC 都能在 PVDAQ 转换后数据上完成训练和 CV 评估
2. **"能检测异常"**：⚠️ 有限。Balanced accuracy ~0.66，abnormal recall 0.23-0.32。模型能检出部分异常，但漏检率较高
3. **Path(a) 合同不兼容**：✅ 诚实记录，两模型缺 `i_cal` 无法直接推理
4. **Path(b) 方法重拟合**：✅ 完成，RF 和 TSC 表现相当

### 为什么结果偏中等？

- **信息 gap**：PR 真值用的是 AC/POA 层面的效率比，模型只看 DC 电流——AC 侧效率下降不一定在 DC 电流波形上有明显表现
- **跨设备泛化难**：12 个系统跨技术域（x-Si / CIS / CIGS）、跨额定功率（1-147 kW），波形模式差异大
- **无 `i_cal`**：缺少预期电流基线，模型无法判断"实际 vs 预期"的偏差

### 后续建议

1. **Q2 验证**：构造 `i_cal`（如 clear-sky 模型或历史回归），评估加入 `i_cal` 后检测能力提升幅度
2. **增加通道**：RF 可扩展为包含 `dc_power_*`、`ac_power_*`、`poa_irradiance_*` 的多通道统计特征
3. **TSC 多通道**：从 1 通道扩展到 3-5 通道（value + dc_power + ac_power + poa + module_temp）
4. **增加样本量**：当前每系统仅 3 个月，扩展到更多月份可提升 CV 稳定性
5. **细化金标**：当前 PR < 0.7 × median 是粗粒度阈值，可考虑按季节/天气类型分组设基线

---

*本报告由 AI 生成，所有数据和结论需人工审核确认。*
<!-- @AI_GENERATED: end -->
