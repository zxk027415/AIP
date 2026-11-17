<!-- @AI_GENERATED -->
# 光伏点路径标签空间收敛与外部真值接入设计

> 文档状态：设计方向已确认，尚未进入代码实现  
> 日期：2026-09-03  
> 适用槽位：`pv_point` — 光伏实时点路径槽位  
> 不适用范围：`pv_day` — 光伏天路径、TSC/MultiRocket、天路径 RFC  
> 关联文档：  
> - `design-易读版.md` — 天/点双产品链的通俗总览，说明 slot、replay 与两条路径边界。  
> - `fusion-design.md` — 点/天路径与确认箱、累计快照、复核闭环的融合设计。  
> - `../pv-fault-timeseries-diagnosis/tsc-platform-integration-plan.md` — 天路径 TSC 接入计划，用于核对本设计的隔离边界。

## 1. 先看结论

本设计**不再采用“把 13 类永久压成一个 5 类标签、细类全部消失”的单层硬映射**，而采用双层标签合同：

1. **粗粒度产品视图**：把当前证据不足或无法从单支路电流可靠区分的类收敛为 5 个稳定分组，用于训练低风险的点路径粗分类模型。
2. **细粒度研究视图**：继续保留有足够样本、且在局部时序中显示出可学习信号的细类，专门验证时序形态是否能区分它们；细类暂不直接作为可信生产故障结论。
3. **原始 13 类来源标签永久保留**：只新增派生列和不可变数据集快照，不覆盖原始测量值、K4 标签、人工标签、累计账本或共享 label registry。
4. **不把 `ratio=value/i_cal` 当成模型输入或唯一打标规则**：ratio 只用于数据审计。模型仍消费完整严格因果窗口，学习电流水平、趋势、突变、持续时间和恢复形态。
5. **窗口口径澄清（重要更正）**：点路径**训练**工作流 `workflow-pv-point-train-eval-v1.json` 实际使用 `context_length=24`（约 2 小时）；只有**预测/回放**节点和代码兜底默认是 8。本次实测 W8 相对当前点几乎无增益（+0.00095），W24 才体现时序价值，而 W24 正是训练已在使用的窗口。训练用 24、回放用 8 属于 **train/serve 窗口不一致**，需单独修复。天路径 TSC 的 `window=288, stride=72` 与点路径窗口无关，不要混用。总精度仍低，必须在 UTFPR 物理真值上复验后再谈产品晋升。
6. **天路径与 TSC 零影响**：派生标签只写点路径新快照，不写共享 `point_labels`，不改天级 parquet，不改 `label_registry.json`。

---

## 2. 为什么不能直接保留 13 类，也不能简单合成 5 类

### 2.1 当前点数据的已知限制

当前点 gold 数据位于：

- `backend-service/data/slot_datasets/pv_point/gold/point-poc-k4-labeled.parquet` — 点路径现有 gold 表；保存逐点测量、理论电流、K4/人工范围标签及来源。

它共有 92,388 行。当前标签主要来自 K4 聚类及少量人工范围操作，不是独立光伏专家真值。主要类别分布如下：

| 来源标签 ID | 当前名称 | 点数 | 独立设备数 | 当前判断 |
|---:|---|---:|---:|---|
| 0 | 正常 | 78,507 | 217 | 数量充分，但仍受伪标签口径影响 |
| 1 | 组串遮挡 | 2,137 | 97 | 有数据支撑，可继续研究 |
| 3 | 待命名-故障码3 | 3,394 | 45 | 信号可学，但业务语义未知，禁止擅自命名 |
| 6 | 待命名-故障码6 | 62 | 4 | 样本不足 |
| 7 | 汇流箱告警 | 3,899 | 47 | 有数据支撑；单点与 12 重叠，但存在部分时序信号 |
| 8 | 汇流箱故障 | 50 | 2 | 样本和设备均不足 |
| 11 | 组串开路 | 332 | 20（仅 1 个站点） | 物理 signature 与名称矛盾，暂不作为可信细类监督 |
| 12 | 组串短路 | 952 | 13 | 样本偏少，但 W24 显示明显时序增益 |

其余 registry 类在当前点 gold 中没有有效样本，不能仅靠 class weight 变成可学习类别。

### 2.2 两个错误极端

**错误极端 A：继续让点模型硬学 13 类。** 结果会是多个零样本/极少样本类占据输出空间，指标被类别不平衡和标签噪声主导。

**错误极端 B：只按单点 ratio 把所有故障压成 5 类。** 这样虽然容易提高粗分类指标，却会抹掉 7 与 12 等类别可能存在的局部时序区别，模型不再有动力学习这些形态。

双层标签合同就是在两者之间取中间路线：产品输出先求稳，研究输出保留可验证的细节。

---

## 3. 字段与数据合同

### 3.1 新增派生字段

以下字段只存在于新的点路径派生快照中，不反写原始 gold：

| 字段 | 中文含义 | 规则 |
|---|---|---|
| `source_label_id` | 原始来源标签 ID | 原样复制当前 `label`；允许空值，不修改 |
| `source_label_name` | 原始来源标签名称 | 来自现有 label registry 的只读展示名 |
| `coarse_label_id` | 粗粒度产品标签 ID | 按 `point_coarse_signal_v1` 确定性映射 |
| `coarse_label_name` | 粗粒度产品标签名称 | 使用不夸大物理因果的名称 |
| `fine_label_id` | 细粒度研究标签 ID | 保留可研究来源类；不满足准入时为空 |
| `fine_label_mask` | 是否允许该点参与细类监督 | JSON boolean；`false` 时细类 loss 必须忽略 |
| `label_view` | 本次训练选择的标签视图 | `source` / `coarse` / `fine`；旧请求缺省为 `source` |
| `label_mapping_version` | 标签映射版本 | coarse 使用 `point_coarse_signal_v1`；fine 使用 `point_fine_research_v1` |
| `label_provenance` | 标签来源与派生说明 | 记录来源快照、原标签、映射版本，不存绝对路径 |

### 3.2 默认值与兼容性

三个默认必须固定：

1. 不传 `label_view` — 标签视图时，默认 `source`，保持旧训练请求行为。
2. 不传 `label_mapping_version` — 映射版本时，仅当 `label_view=coarse` 时由点路径模板显式补 `point_coarse_signal_v1`；平台层不猜最近版本。
3. 标签映射功能默认关闭；只有点路径模板显式选择 `coarse` 或 `fine` 才启用。

因此旧工作流、旧模型工件和旧数据集快照不需要迁移。

---

## 4. Phase 1 双层标签空间

### 4.1 粗粒度产品视图：`point_coarse_signal_v1`

粗视图只表达“当前电流信号家族”，不冒充已经获得专家确认的具体设备故障原因。

| `coarse_label_id` | 稳定 key | 中文名称 | 来源标签集合 | 说明 |
|---:|---|---|---|---|
| 0 | `normal` | 正常 | {0} | 当前正常来源类 |
| 1 | `shading_like` | 遮挡型欠流 | {1} | 保留遮挡型信号，但最终语义仍需 UTFPR 真值验证 |
| 2 | `unknown_pattern_3` | 未知模式3 | {3} | 当前信号可学但业务含义未知；禁止改名为开路 |
| 3 | `severe_undercurrent_family` | 重度欠流家族 | {7, 8, 12} | 粗输出合并；细视图仍保留 7 与 12 的差异 |
| 4 | `other_or_unverified` | 其他或未验证异常 | {2, 4, 6, 9, 10, 11, 16} | 样本不足、无样本或语义与物理信号冲突的兜底类 |

未标注点继续使用 `IGNORE_LABEL=-1` — 忽略监督标签，不得自动归为正常或其他。

### 4.2 细粒度研究视图：`point_fine_research_v1`

细视图不是生产承诺，用来回答“局部时序是否还包含值得保留的细类信号”。

| 来源标签 | 是否进入 fine loss | 展示口径 | 原因 |
|---:|---|---|---|
| 0 | 是 | 正常 | 作为共同基准 |
| 1 | 是 | 遮挡（待外部真值确认） | 97 个设备，样本充分 |
| 3 | 是 | 未知模式3 | F1 尚可，但语义未知 |
| 7 | 是 | 来源类7（暂沿用“汇流箱告警”作来源名） | W24 历史消融证明存在时序贡献 |
| 12 | 是 | 来源类12（暂沿用“组串短路”作来源名） | W24 时序增益显著，不能立即与 7 永久合并 |
| 11 | 否 | 来源类11，仅审计 | 仅 1 个站点；W24 F1 低；单点物理 signature 与“开路”相反 |
| 6 / 8 | 否 | 仅审计 | 分别只有 62 / 50 点 |
| 2 / 4 / 9 / 10 / 16 | 否 | 仅审计 | 当前点 gold 无足够样本 |

`fine_label_mask=false` 不删除来源记录，只是不让不可信标签参与细类 loss。

### 4.3 为什么粗视图合并、细视图仍拆分不矛盾

粗视图回答：“实时告警最稳妥地能说到什么程度？”  
细视图回答：“历史窗口是否含有更细的可学习信号，值得以后用真值验证？”

同一条记录可以同时拥有 coarse 与 fine 标签。粗模型避免过度声明；细模型防止时序形态被映射埋没。

---

## 5. 细标签时序可分性实验

### 5.1 实验目的

本实验只判断：**在当前 K4 来源标签口径下，历史窗口相对当前点是否增加了类别可分信息。**

它不是生产精度，也不能证明来源标签名称在物理上正确。

### 5.2 防泄漏合同

- 数据源：现有 point gold，只读。
- 目标点：白天有标签点；每个目标必须具备同一自然日内连续 24 点历史；相邻点最大间隔不超过 20 分钟。
- 最终目标点：59,675。
- 序列实体：`site_id + device_id + branch_id` — 站点、设备、支路联合实体。
- 切分分组：`site_id + device_id` — 同一设备所有支路必须在同一折，防止兄弟支路泄漏。
- 切分方式：3 折 `StratifiedGroupKFold` — 分层设备组交叉验证。
- 训练准入：至少 100 点且至少 3 个独立设备。
- 准入细类：0 / 1 / 3 / 7 / 11 / 12；6 和 8 仅作证据不足记录。

### 5.3 模型输入

三个模型使用相同目标点和相同 7 通道：

- `value` — 实测电流。
- `i_cal` — 理论电流。
- `is_measured` — 是否实测。
- `time_since_measured` — 距上次实测的时间状态。
- `tod_sin` / `tod_cos` — 日内时刻周期编码。
- `is_daylight` — 是否白天。

`ratio=value/i_cal` **没有进入模型输入**。

对照模型：

- W1：只看当前点，作为非时序基线。
- W8：预测/回放节点窗口与代码兜底默认。
- W24：点路径训练工作流 `workflow-pv-point-train-eval-v1.json` 实际使用的窗口。
- W24 flat history：保留当前点，但把前 23 点展平为当前点，作为历史形态消融。

### 5.4 总体结果

| 模型 | macro-F1 | balanced accuracy | accuracy | 相对 W1 macro-F1 |
|---|---:|---:|---:|---:|
| W1 当前点 | 0.3363 | 0.5052 | 0.5614 | — |
| W8 因果窗口 | 0.3373 | 0.5173 | 0.5608 | +0.00095 |
| W24 因果窗口 | 0.3602 | 0.5893 | 0.5905 | +0.02385 |
| W24 历史展平 | 0.2989 | 0.5053 | 0.5129 | -0.03741（相对 W1） |

W24 原始历史相对展平历史的 macro-F1 增益为 0.0613，说明模型确实利用了历史形态，而不只是读取当前 ratio。

### 5.5 逐类结果

| 来源类 | W1 F1 | W8 F1 | W24 F1 | W24 展平 F1 | W24 相对 W1 | W24 相对展平 |
|---:|---:|---:|---:|---:|---:|---:|
| 0 正常 | 0.726 | 0.714 | 0.740 | 0.681 | +0.014 | +0.060 |
| 1 遮挡 | 0.149 | 0.145 | 0.168 | 0.148 | +0.019 | +0.020 |
| 3 未知模式 | 0.541 | 0.514 | 0.471 | 0.474 | -0.070 | -0.003 |
| 7 汇流箱告警来源类 | 0.411 | 0.449 | 0.423 | 0.289 | +0.012 | +0.134 |
| 11 开路来源类 | 0.065 | 0.063 | 0.101 | 0.070 | +0.036 | +0.031 |
| 12 短路来源类 | 0.126 | 0.138 | 0.258 | 0.132 | +0.132 | +0.126 |

关键解释：

1. W8 几乎没有总体时序收益，不能据此声称当前生产窗口已经充分学习故障形态。
2. W24 对来源类 12 的收益明显；把历史展平后，7 和 12 的 F1 都显著下降。因此二者不能在所有监督目标里永久合并。
3. 7 与 12 的绝对 F1 仍低，尤其 precision 较低。当前证据只支持“有细分信号”，不支持“已经能可靠诊断汇流箱告警和短路”。
4. 类 3 主要依赖当前电流水平，增加历史反而下降；它可保留为未知信号模式，但不能擅自命名。
5. 类 11 仅来自一个站点且与开路物理方向冲突，不应因为 W24 有小幅增益就直接保留“开路”语义。

### 5.6 实验限制

- 真值仍是 K4/人工范围来源，不是独立专家真值。
- 这是 6 epoch 的可分性 smoke，不是完整调参或生产验收。
- W24 只覆盖模型 61 点理论感受野的一部分；后续应增加 W61 对照。
- 类别权重提高了少数类 recall，但造成较低 precision；不能只看 recall。
- 结果不能用于修改原始标签，只能指导下一阶段设计。

---

## 6. 训练链路与字段流转

固定链路如下：

```text
point gold（source_label 只读）
  → 点路径派生快照（新增 coarse/fine 字段）
  → ts_point_train_classifier（点分类训练算子）
  → train_real_point_classifier（选择 label_view）
  → build_real_point_dataset（按实体切严格因果窗口）
  → RealtimePointTrainer（训练 TCN）
  → 新模型工件与评测证据
```

内部符号职责：

- `ts_point_train_classifier` — 点路径工作流训练算子；接收 DataFrame 和训练 contract，调用真实点训练适配器并返回模型工件。
- `train_real_point_classifier` — 点训练适配入口；根据 `label_view` 选择目标标签列，再构建窗口并启动 TCN trainer。
- `build_real_point_dataset` — 把规范点表转换成不可变窗口数据集，按实体隔离 train/val/test，输出 NPZ、metadata 和 build report。
- `RealtimePointTrainer` — 使用 train-only scaler、balanced class weights 和严格因果 TCN 训练模型，输出模型与评测记录。

关键字段流：

| 层 | 字段 | 缺省行为 | 最终消费位置 |
|---|---|---|---|
| 工作流 contract | `label_view` — 标签视图 | `source` | `train_real_point_classifier` 分支选择 |
| 工作流 contract | `label_mapping_version` — 映射版本 | coarse/fine 必须显式传 | 派生快照校验 |
| 工作流 contract | `context_length` — 因果历史点数 | 旧请求为 8 | `build_real_point_dataset` 切窗 |
| 派生快照 | `coarse_label_id` — 粗标签 | 无隐式生成 | 粗模型目标列 |
| 派生快照 | `fine_label_id` — 细标签 | 可空 | 细模型目标列 |
| 派生快照 | `fine_label_mask` — 细类监督掩码 | `false` | 过滤不可信监督点 |

行为改变的最终条件分支必须是：

```text
label_view == source → 使用原 label（兼容旧行为）
label_view == coarse → 使用 coarse_label_id
label_view == fine   → 仅使用 fine_label_mask=true 的 fine_label_id
```

不得通过“最近一次训练”“最近一个快照”或跨 slot 回退猜标签视图。

---

## 7. Phase 1 实施顺序

### P1.1 派生映射模块

计划新增：

- `backend-service/services/timeseries_point/label_space_map.py` — 点路径标签视图的纯函数映射；输入来源标签表，输出 coarse/fine 派生字段与审计摘要。

要求：

- 不原地修改输入 DataFrame。
- 映射表穷举现有 registry ID；未知 ID fail closed。
- NaN 保持未监督，不自动归类。
- 输出每个来源类到 coarse/fine 的行数统计。
- 映射版本写入 build report。

### P1.2 训练入口显式选择视图

计划修改：

- `backend-service/services/timeseries_point/train_adapter.py` — 点表转因果窗口及启动 trainer 的适配层；加入 `label_view` 显式选择，默认保持 source。
- `backend-service/services/operator_backends/ts_point_train_classifier.py` — 点分类训练算子；只负责透传并校验标签视图 contract，不内置业务映射。

第一阶段分别训练两个模型，而不是立即改成多头网络：

1. coarse 模型：用于判断粗粒度输出是否稳定。
2. fine 研究模型：只用于验证细类时序可分性，不进入产品 registry。

只有两模型方案验证有收益后，才考虑共享 TCN encoder + coarse/fine 双 head，避免第一阶段同时引入标签和架构两种变量。

### P1.3 窗口实验

必须保留 W8 作为兼容基线，同时对齐并验证 W24、W61：

- W8 — 预测/回放节点与代码兜底默认；冷启动短，但本次未显示明显时序增益。
- W24 — 训练工作流已在使用的窗口；已显示时序信号；不会读取未来点，但冷启动需积累更多历史。
- W61 — 覆盖默认 TCN 理论感受野；尚未验证。

**必须先修复 train/serve 窗口不一致**：训练用 `context_length=24`，而预测/回放节点用 8，会触发 `predict.py` 的 `artifact_window_mismatch` 判定。对齐方式是让回放节点的 `context_length` 跟随所选模型工件 `metadata.context_length`，不要在模板里写死 8。增大窗口不会让在线预测等待未来数据，但会增加服务重启或新设备接入后的 warm-up 点数和内存占用。

---

## 8. Phase 2：UTFPR 外部物理真值

### 8.1 使用顺序

UTFPR 不直接裸合并进当前累计训练表。顺序固定为：

1. 独立数据 profile + 独立不可变快照。
2. 先作为点模型域外真值测试集，得到可信混淆矩阵。
3. 再做 UTFPR 预训练、自有数据微调的迁移学习对照。
4. 最后才评估受控增强：故障窗口优先，正常窗口降采样；自有站点 val/test 不变。

### 8.2 UTFPR 标签接法

| UTFPR 标签 | 第一阶段用途 | 映射原则 |
|---|---|---|
| 正常 | 外部真值正常类 | 对应 coarse normal / fine 0 |
| 遮挡 | 外部真值遮挡 | 对应 coarse shading_like / fine 1 |
| 短路 | 外部真值短路 | 对应 coarse severe_undercurrent_family / fine 12 |
| 开路 | 外部真值开路 | 不硬塞进 v1 的来源类11；用于设计 `point_coarse_signal_v2` 的 verified disconnect/open 类 |
| 退化 | 外部真值异常 | 暂归 other_or_unverified，除非有单独可验证定义 |

`i_cal` — 理论电流可由辐照度、组件温度和组件参数推算，但必须记录公式版本和参数来源。ratio 只能作为一个物理证据，不能单独决定最终标签。

### 8.3 无专家条件下的弱监督

只有同时满足以下证据中的至少两类，派生标签才可进入高置信训练集：

1. 外部真值模型高置信预测。
2. 物理约束一致，例如电流与理论电流关系合理。
3. 时序形态一致，例如突变、持续、恢复过程与已验证样本相似。

K4 只作为额外弱票，不再被视为真值。冲突点保留为未监督或审计队列，不自动强行改标签。

---

## 9. 对天路径、TSC 和共享资产的影响

### 9.1 明确零影响的资产

以下资产不修改：

- `backend-service/data/iterative_labeling/label_registry.json` — 全局/槽位标签登记；仍保留现有 13 类来源空间。
- `backend-service/data/slot_datasets/pv_point/gold/point-poc-k4-labeled.parquet` — 点 gold 原始来源。
- `backend-service/datasets/pv_cumulative_labeled_merged.parquet` — 天路径序列标注累计数据源。
- `backend-service/data/slot_datasets/pv_day/gold/all_labeled_combined.parquet` — 天路径 gold。
- TSC/MultiRocket 的 288 点窗口、天标签和模型工件。

### 9.2 必须守住的隔离规则

新的 coarse/fine 派生标签：

- 不写共享 DB `point_labels`。
- 不使用 `human_range`、`point_rest_normal`、`peer_residual`、`pseudo_point` 等共享点标签来源名伪装写入。
- 不进入 `seq_annotation/dataset_builder.py` 的输入。
- 不修改 `pv_day` 的累计 ledger、snapshot 或模型 registry。

这样天路径、RFC 和 TSC 不会看到派生标签。

---

## 10. 验收门禁

### 10.1 Phase 1 数据安全门禁

- [ ] 原始 point gold 文件 hash 在构建前后不变。
- [ ] DB `point_labels` 行数、更新时间和来源分布不变。
- [ ] label registry 内容不变。
- [ ] 新快照同时保存 `source_label_id`、coarse/fine 派生列和映射版本。
- [ ] 旧请求不传 `label_view` 时与改造前结果等价。
- [ ] coarse/fine 快照均只使用项目相对路径。

### 10.2 模型证据门禁

- [ ] coarse 与 fine 使用同一设备隔离 split 进行可比实验。
- [ ] 报告 accuracy、macro-F1、balanced accuracy、每类 precision/recall/F1 和混淆矩阵。
- [ ] W8/W24/W61 使用同一目标点集比较。
- [ ] 对历史做消融，证明收益来自历史而非数据切分变化。
- [ ] K4 指标明确标注“可分性诊断”，不命名为真实精度。
- [ ] fine 模型不得进入产品 registry 或 Promote。

### 10.3 外部真值门禁

- [ ] UTFPR 下载来源、许可、本地使用和再分发结论分别记录。
- [ ] train/validation/test 按设备或实验日隔离，禁止窗口随机切分泄漏。
- [ ] 开路/短路/遮挡只按实验真值映射，不按模型预测反向制造测试标签。
- [ ] 外部测试集始终锁定，不参与阈值、早停或模型选择。
- [ ] 只有外部真值评测通过后，才讨论 coarse 模型产品晋升或 fine 类生产展示。

### 10.4 回归门禁

- [ ] 点路径 targeted tests 通过。
- [ ] seq annotation 数据集构建测试通过。
- [ ] 天路径 TSC targeted tests 通过。
- [ ] 前端如未修改则无需前端构建；若增加标签视图配置，再运行前端 build。

---

## 11. 回滚策略

1. 工作流去掉 `label_view=coarse|fine`，立即回到旧 source 标签行为。
2. 新派生快照和新模型工件均有独立版本，不覆盖旧快照/模型。
3. 不发生 DB schema 或原始标签迁移，因此无需数据回滚脚本。
4. 若 W24/W61 不满足性能或 warm-up 要求，恢复 `context_length=8` 即可；历史工件仍可读取。
5. coarse 映射升级必须新建 `point_coarse_signal_v2`，禁止原地改写 v1 语义。

---

## 12. 当前决策记录

| 决策 | 结论 | 原因 |
|---|---|---|
| 是否继续点路径 13 类硬分类 | 否 | 多个类无样本或只有几十点，且标签缺乏独立真值 |
| 是否只保留单层 5 类映射 | 否 | W24 证明 7/12 存在可利用时序信号，永久合并会埋没差异 |
| 是否删除或覆盖原始标签 | 否 | 必须保留审计、回放和未来重映射能力 |
| 是否将 ratio 输入模型 | 否 | 防止模型退化为单一阈值分类器 |
| 是否保留 7/12 细分研究 | 是 | W24 历史消融后两类 F1 明显下降，说明历史含信息 |
| 是否保留 11 为可信开路 | 暂否 | 仅 1 站点、F1 低、物理 signature 与名称冲突 |
| 是否立即改多头网络 | 否 | 先分别训练 coarse/fine，控制实验变量 |
| 是否影响天路径/TSC | 否 | 只写点路径派生快照，不写共享标签 DB 和天路径数据源 |
| 是否直接把 UTFPR 裸合并累计集 | 否 | 先做独立真值评测，再迁移学习，最后才受控增强 |

## 13. 下一步

1. 实现 `point_coarse_signal_v1` 和 `point_fine_research_v1` 的纯函数派生模块。
2. 为点训练 contract 增加显式 `label_view`，保持默认 source。
3. 生成新的不可变点数据集快照，验证原始 hash 与 DB 均未变化。
4. 在同一 split 上训练 coarse W8/W24/W61 与 fine W8/W24/W61。
5. 下载并审计 UTFPR，先完成锁定外部真值评测。
6. 根据 UTFPR 混淆矩阵决定是否建立 v2 的 verified open/disconnect 类，以及 7/12 是否值得进入生产细分。

<!-- @AI_GENERATED: end -->