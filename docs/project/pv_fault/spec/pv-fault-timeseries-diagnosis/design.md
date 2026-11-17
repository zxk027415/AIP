<!-- @AI_GENERATED -->
# 设计文档：光伏时序故障诊断（pv-fault-timeseries-diagnosis）

## 概览（Overview）

本设计文档为时序路线提供完整的技术方案：从原始功率时序出发，经滑动窗口切分产生等长样本，喂入多种时序分类（TSC）模型进行训练与评估，最终与 RF 路线在统一评估口径下对比精度，选出最优模型。

设计原则：

1. **多模型竞赛、数据说话** — 不预设哪个模型最好，用统一 pipeline 跑 5+ 种模型，按精度和效率两个维度排序选型。
2. **与 RF 路线公平对比** — 共享同一标签源（`point_labels`）、同一 train/test 划分种子、同一评估指标（macro_f1 / accuracy），只换「样本切分 + 模型」。
3. **渐进式投入** — 先跑轻量模型（秒级训练），验证时序形态信息有价值后，再投入重型深度模型。
4. **工具库优先** — 优先使用 `aeon-toolkit`（sktime 的继承者）统一 API，减少自实现成本。

### 与 RF 路线（逐点标签 spec）的关系

```
                    point_labels（逐点标签，共享事实来源）
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
   RF 路线（逐点标签 spec）      时序路线（本 spec）
   ● 按天/白天切段               ● 滑动窗口切段
   ● 统计特征聚合                ● 原始序列直接输入
   ● RandomForest               ● ROCKET/InceptionTime/CNN-LSTM/...
              │                         │
              └────────────┬────────────┘
                           ▼
              split_mode_compare 统一对比框架
              production_path / fallback_path 双指针
```

## 一、滑动窗口切分器设计（Sliding Window Sampler）

### 1.1 核心参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `window_length` | int | 288 | 窗口包含的时间点数（288 = 5min采样 × 24h = 1天） |
| `stride` | int | 72 | 窗口滑动步长（72 = 6小时，即 75% 重叠） |
| `min_coverage` | float | 0.9 | 窗口内非 NaN 点的最低比例，低于则丢弃 |
| `label_strategy` | str | "majority" | 窗口级标签聚合策略 |
| `purity_threshold` | float | 0.7 | 众数占比低于此阈值的窗口标记为 mixed 并丢弃 |
| `channels` | list[str] | ["power"] | 输入通道列表，可扩展为多变量 |
| `daylight_only` | bool | False | 是否只在白天时段切窗口 |

### 1.2 切分算法

```python
# 伪代码：SlidingWindowSampler.transform()
def transform(self, device_timeseries, point_labels):
    """
    输入:
      - device_timeseries: DataFrame[time, power, ...], 按 time 排序的连续时序
      - point_labels: DataFrame[time, label_id], 逐点标签（来自 point_labels 表）

    输出:
      - X: ndarray[n_samples, window_length, n_channels]  # 样本矩阵
      - y: ndarray[n_samples]                              # 窗口级标签
      - meta: DataFrame[sample_id, t_start, t_end, purity, device_id]  # 元数据
    """
    samples, labels, metas = [], [], []
    merged = device_timeseries.merge(point_labels, on="time", how="left")

    for start in range(0, len(merged) - window_length + 1, stride):
        window = merged.iloc[start : start + window_length]

        # 覆盖率检查
        coverage = window[channels[0]].notna().mean()
        if coverage < min_coverage:
            continue

        # 白天过滤（可选）
        if daylight_only and not _is_daylight_window(window):
            continue

        # 标签聚合
        window_labels = window["label_id"].dropna()
        if len(window_labels) == 0:
            continue  # 全部未标注，跳过

        majority_label, purity = _compute_majority(window_labels)
        if purity < purity_threshold:
            continue  # 混合窗口，丢弃

        # 提取数值矩阵
        x = window[channels].values  # shape: [window_length, n_channels]
        samples.append(x)
        labels.append(majority_label)
        metas.append({...})

    return np.array(samples), np.array(labels), pd.DataFrame(metas)
```

### 1.3 标签聚合策略

| 策略名 | 逻辑 | 适用场景 |
|--------|------|----------|
| `majority` | 取众数，若纯度 < threshold 则丢弃 | 默认基线，简单可靠 |
| `fault_priority` | 只要故障点数 ≥ N 就标为故障 | 召回优先场景 |
| `boundary_align` | 窗口起点对齐标签变化边界 | 减少混合窗口数量 |

初期统一使用 `majority` 策略，后续可扩展。

### 1.4 窗口长度选择依据

| 窗口长度 | 对应时长（5min采样） | 适用场景 |
|----------|---------------------|----------|
| 144 | 12小时（半天） | 快速故障（遮挡、短路），形态在半天内完整 |
| 288 | 24小时（1天） | 默认基线，覆盖完整日变化周期 |
| 576 | 48小时（2天） | 慢性衰退、跨天故障 |

设计阶段默认 `window_length=288`，实验时同时跑 144/288/576 三组对比。

### 1.5 预测侧切分一致性

训练与预测**必须使用相同的** `window_length` 和 `channels`。预测时：

- 取目标设备最近 `window_length` 个连续数据点作为一个窗口。
- 或按 stride 滑动产生多个窗口，取众数/平均概率作为最终预测。
- 窗口参数随模型一起持久化到模型产物（`.pkl` / `.pt`）的 `metadata` 字段。

## 二、模型选型与多模型对比框架

### 2.1 候选模型深度调研

基于 UCR/UEA 时序分类 benchmark（112+ 数据集）、光伏故障诊断文献和实际工程约束，选定以下 6 类模型进行对比实验：

#### Tier 1：轻量基线（秒级训练，无 GPU 依赖）

| 模型 | 原理 | UCR 精度排名 | 训练速度 | 适合场景 |
|------|------|-------------|----------|----------|
| **MiniRocket** | 固定 84 个卷积核（9996 个变体） + PPV 特征 + Ridge | 与 ROCKET 持平，显著快于 ROCKET | 极快（<1s/千样本） | 快速基线验证 |
| **MultiRocket** | MiniRocket + 多池化算子（PPV + 均值 + 中位数…） | 接近 HC2，显著优于 MiniRocket | 快（<5s/千样本） | 最佳性价比轻量方案 |
| **ROCKET** | 10000 随机卷积核 + max pooling + PPV + Ridge | 与 InceptionTime 持平 | 快（<3s/千样本） | 经典基线 |

**选型理由**：ROCKET 家族是 TSC 领域公认的"强基线"。在 UCR 92 数据集 30-resample 实验中，最新 RocketPFN 与 HC2 持平（均 0.900 mean accuracy）。MiniRocket 更快且几乎确定性（无随机性），适合快速验证。MultiRocket 在精度和速度之间取得最佳平衡。

**工具库**：`aeon.classification.convolution_based.{RocketClassifier, MiniRocketClassifier, MultiRocketClassifier}`，sklearn 兼容 API（`fit/predict/predict_proba`）。

#### Tier 2：中量级深度模型（分钟级训练，GPU 可选）

| 模型 | 原理 | UCR 精度排名 | 训练速度 | 适合场景 |
|------|------|-------------|----------|----------|
| **InceptionTime** | 6 层 Inception 模块（多尺度并行 1D 卷积） + 全局池化 + softmax；5 模型集成 | 与 ROCKET/HC1 持平，略低于 HC2 | 中等（GPU 下 1-5min/千样本） | 深度学习最强通用基线 |
| **ResNet-1D** | 3 组残差块（1D 卷积 + BN + ReLU + shortcut） + 全局平均池化 | 略低于 InceptionTime | 中等 | 简单深度结构 |

**选型理由**：InceptionTime 是深度学习 TSC 的"AlexNet 时刻"——在可接受训练时间内达到接近 SOTA 精度。其多尺度卷积核（kernel_size=10/20/40）天然适合捕捉光伏故障的不同时间尺度（分钟级骤降 vs 小时级衰退）。ResNet-1D 作为更简单的深度对照组。

**工具库**：`aeon.classification.deep_learning.{InceptionTimeClassifier, ResNetClassifier}`，基于 PyTorch。

#### Tier 3：重型/领域特化模型（需 GPU，精度上限探索）

| 模型 | 原理 | 光伏文献支撑 | 训练速度 | 适合场景 |
|------|------|-------------|----------|----------|
| **CNN-LSTM** | 1D-CNN 提局部形态 → LSTM 抓时间依赖 → FC 分类 | 光伏 DC 子模块开路故障检测（2025）、多尺度 CNN-BiLSTM + 时间注意力（2025） | 慢（10-30min/千样本） | 精度上限探索 |
| **CNN-BiLSTM-Attention** | 多尺度 CNN + 双向 LSTM + 时间注意力 | Advanced CNN-BiLSTM for PV Fault Detection（2025），在 GPVS-Faults 数据集上 SOTA | 慢 | 光伏场景最优候选 |

**选型理由**：光伏故障诊断最新文献（2025）反复证实 CNN-LSTM 架构在该场景下的有效性。CNN 负责提取"骤降"、"振荡"等局部形态，LSTM/BiLSTM 负责捕捉故障的时间演化过程。注意力机制进一步帮助模型聚焦关键时段。但训练成本高，只在 Tier 1/2 验证时序路线有价值后才投入。

**工具库**：需自实现（PyTorch），不在 aeon 标准库中。

#### 补充对照：两阶段混合（时序特征提取 + RF 分类）

| 模型 | 原理 | 特点 |
|------|------|------|
| **ROCKET + RF** | ROCKET 特征提取 + RandomForest（替换默认 Ridge） | 与 RF 路线最大程度对比：只换特征提取、不换分类器 |
| **TSFresh + RF** | TSFresh 自动特征提取 + RandomForest | 自动化统计特征，比手工更全面 |

**选型理由**：这组对照能回答「如果只升级特征提取（从手工统计→卷积核自动提取），不换分类器，能提升多少？」，帮助归因精度提升来源。

### 2.2 模型对比框架设计

#### 2.2.1 统一接口

所有模型统一实现以下接口（sklearn 兼容）：

```python
class TSCModelWrapper:
    """时序分类模型的统一包装器。"""

    def __init__(self, model_name: str, **hyperparams):
        self.model_name = model_name
        self.model = self._build_model(**hyperparams)
        self.window_config = None  # 训练时绑定的窗口配置

    def fit(self, X: np.ndarray, y: np.ndarray) -> "TSCModelWrapper":
        """训练。X shape: [n_samples, window_length, n_channels]"""
        ...

    def predict(self, X: np.ndarray) -> np.ndarray:
        """预测类别。"""
        ...

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率（如果支持）。"""
        ...

    def save(self, path: str) -> None:
        """持久化模型 + 窗口配置。"""
        ...

    @classmethod
    def load(cls, path: str) -> "TSCModelWrapper":
        """加载持久化模型。"""
        ...
```

#### 2.2.2 模型注册表

```python
MODEL_REGISTRY = {
    # Tier 1: 轻量基线
    "minirocket": {
        "class": "aeon.classification.convolution_based.MiniRocketClassifier",
        "tier": 1,
        "gpu_required": False,
        "default_params": {},
        "description": "MiniRocket: 固定卷积核 + Ridge 线性分类",
    },
    "multirocket": {
        "class": "aeon.classification.convolution_based.MultiRocketClassifier",
        "tier": 1,
        "gpu_required": False,
        "default_params": {},
        "description": "MultiRocket: 多池化算子扩展，精度接近 HC2",
    },
    "rocket": {
        "class": "aeon.classification.convolution_based.RocketClassifier",
        "tier": 1,
        "gpu_required": False,
        "default_params": {"n_kernels": 10000},
        "description": "ROCKET: 10000 随机卷积核 + Ridge",
    },
    # Tier 2: 中量级深度模型
    "inceptiontime": {
        "class": "aeon.classification.deep_learning.InceptionTimeClassifier",
        "tier": 2,
        "gpu_required": False,  # CPU 可跑但慢
        "default_params": {"n_epochs": 100, "batch_size": 64},
        "description": "InceptionTime: 多尺度 Inception 模块集成",
    },
    "resnet": {
        "class": "aeon.classification.deep_learning.ResNetClassifier",
        "tier": 2,
        "gpu_required": False,
        "default_params": {"n_epochs": 100, "batch_size": 64},
        "description": "ResNet-1D: 残差卷积网络",
    },
    # Tier 3: 重型领域模型
    "cnn_lstm": {
        "class": "custom.models.CnnLstmClassifier",
        "tier": 3,
        "gpu_required": True,
        "default_params": {
            "cnn_filters": [64, 128],
            "lstm_units": 64,
            "dropout": 0.3,
            "n_epochs": 200,
            "batch_size": 32,
        },
        "description": "CNN-LSTM: 卷积提形态 + LSTM 抓时序依赖",
    },
    "cnn_bilstm_attention": {
        "class": "custom.models.CnnBiLstmAttentionClassifier",
        "tier": 3,
        "gpu_required": True,
        "default_params": {
            "cnn_filters": [64, 128, 256],
            "kernel_sizes": [3, 7, 15],
            "lstm_units": 128,
            "attention_heads": 4,
            "dropout": 0.3,
            "n_epochs": 200,
            "batch_size": 32,
        },
        "description": "CNN-BiLSTM-Attention: 多尺度卷积 + 双向 LSTM + 时间注意力",
    },
    # 补充对照: 两阶段混合
    "rocket_rf": {
        "class": "custom.models.RocketRFClassifier",
        "tier": 1,
        "gpu_required": False,
        "default_params": {"n_kernels": 10000, "n_estimators": 200},
        "description": "ROCKET 特征提取 + RandomForest 分类（与 RF 路线对照）",
    },
}
```

#### 2.2.3 对比实验运行器

```python
def run_model_comparison(
    *,
    dataset_path: str,
    window_configs: list[dict],       # 多组窗口参数
    model_names: list[str],           # 要对比的模型列表
    n_repeats: int = 5,               # 重复随机划分次数
    test_ratio: float = 0.2,
    random_state: int = 90,
    tier_filter: Optional[int] = None,  # 只跑某个 tier
) -> dict:
    """
    运行多模型 × 多窗口参数的全对比实验。

    返回结构:
    {
        "experiment_id": "tsc-cmp-20260803-xxxx",
        "results": [
            {
                "model_name": "multirocket",
                "window_length": 288,
                "stride": 72,
                "n_samples": 1200,
                "n_classes": 5,
                "macro_f1_mean": 0.87,
                "macro_f1_std": 0.02,
                "accuracy_mean": 0.89,
                "accuracy_std": 0.01,
                "macro_precision_mean": 0.86,
                "macro_recall_mean": 0.88,
                "train_time_sec": 2.3,
                "predict_time_sec": 0.1,
                "model_size_mb": 1.2,
            },
            ...
        ],
        "ranking": {
            "by_f1": [...],
            "by_accuracy": [...],
            "by_efficiency": [...],  # f1 / train_time
        },
        "best_model": "multirocket",
        "best_window_length": 288,
    }
    """
```

### 2.3 模型间精度排名 — 实测结果（v2，2026-08-03 修复数据 bug 后重跑）

> 本节原为"基于 benchmark 的预期排名"，现已被真实实验数据替代。
> 完整报告见 `backend-service/data/tsc_experiments/experiment_report.json`。

#### ⚠️ v1 结果已作废

首轮实验（200 设备 / 617 窗口）得出「MultiRocket 0.9579 断层第一」的结论，
**该结论及其全部数值已作废**，因为滑窗切分器当时有两个数据正确性 bug：

1. **跨支路混合**：`transform_multi_device` 只按 `device_id` 分组，但数据真正的时序主键是
   `(site_id, device_id, branch_id)`。实测 1642 台设备对应 **2226 条序列**，250 台（15.2%）
   有 2~16 条支路。混在一起排序切窗，样本会在不同物理支路间跳变。
   证据：`(device_id, time)` 重复行 86,124 条，`(site,device,branch,time)` 重复行 0 条。
2. **merge 笛卡尔积**：`transform()` 内 `merge(point_labels, on="time")` 在时间戳跨支路重复时
   产生笛卡尔积（2 支路→4 行/时间戳，16 支路→256 行）。同参数下修复前切出 19,050 窗口，
   修复后 6,852（理论 7,353，差额为纯度/覆盖率过滤）。

修复见 `sliding_window_sampler.py` 的 `series_keys` / `resolve_series_keys()`，
回归测试见 `tests/test_sliding_window_sampler.py::TestMultiBranchSeriesKey`。

#### ⚠️ v2 结果也已作废（指标口径错误 + 退化窗口泄漏）

v2（数据 bug 修复后）报出 MiniRocket macroF1=0.8945 / Acc=97.65%。经数据穿越审计发现
仍有两处问题，**v2 数值同样不可用**：

1. **macro F1 口径错误**：`f1_score(average="macro")` 未指定 `labels=`，sklearn 只在
   「test 中出现的类」上平均，缺席的稀有类被静默排除。同一次预测：默认口径 0.8841，
   全 12 类口径 **0.7367**，差 0.147。
2. **退化窗口泄漏**：4.42% 的窗口是常数序列（多为夜间全零），302/303 属同一类。
   不同设备的全零窗口内容**完全相同**，导致 train/test 出现 46 个字节级重复窗口
   （占 test 3.73%）。已新增 `SamplerConfig.min_std` 过滤，设 1e-6 后重复窗口 46 → 0。

#### v3 诚实结果（当前有效，2026-08-03）

**实验条件**：全量 1642 设备 / 2226 序列 / 8 站点 / **35 个日期** / 6,533 窗口
（5,279 训练 + 1,254 测试，train/test 零重复窗口）/ 12 类 / window=288 / stride=72 /
`min_std=1e-6` / 按 `device_id` 划分 / random_state=90 / **macro 指标固定在全 12 类上计算**。

| 模型 | Accuracy | Balanced Acc | **macro F1(全12类)** | Weighted F1 |
|---|---|---|---|---|
| 多数类基线 | 0.4665 | 0.0833 | 0.0530 | 0.2968 |
| 聚合特征+决策树基线 | 0.9083 | 0.6404 | 0.6132 | 0.9037 |
| ROCKET | 0.9402 | 0.6917 | 0.6930 | 0.9365 |
| MiniRocket | 0.9490 | 0.7304 | 0.7283 | 0.9471 |
| **MultiRocket** | **0.9601** | **0.7348** | **0.7349** | **0.9569** |
| MiniRocket（时间打乱对照） | 0.7863 | 0.4018 | 0.4122 | 0.7501 |

**关键读数**：

- **不要用 accuracy 作主指标**。多数类基线 accuracy 已达 0.4665（label 1 占 test 46.6%，
  label 1+11 合计约 68%）。模型 accuracy 0.96 看着漂亮，但 balanced accuracy 只有 0.735。
- **时序形态确实有效**：把窗口内 288 个点随机重排后，macroF1 从 0.7283 崩到 0.4122、
  accuracy 从 0.9490 掉到 0.7863。这是反驳「结果全靠泄漏/任务平凡」的最强证据。
- **TSC 相对聚合特征基线提升 macroF1 +0.12**（0.7349 vs 0.6132）、balanced_acc +0.09。
  这正是本 spec 要验证的核心命题——增益真实，但幅度有限，远非 v1 暗示的断层领先。
- MultiRocket 与 MiniRocket 差 0.0066，统计上无法区分；MiniRocket 快约 3 倍，工程上更优。

**数字演变**：v1 `0.9579`（脏数据+200设备）→ v2 `0.8945`（口径错误+退化窗口）
→ **v3 `0.7349`（诚实值）**。

#### 排查中已排除的泄漏假设

- **标签规则泄漏**：排除。`value`/`i_cal` 是原始测量值，非由 label 推导。
- **日期查表泄漏**：排除。仅按日期查表只有 Acc=0.6924/F1=0.3062，
  按 (site,date) 查表 Acc=0.7094/F1=0.4229，远低于模型，说明模型不是靠「认日期」作答。

#### ✅ 时间切分验证已实现（换数据源，2026-08-03）

上面说的「无法做时间划分验证」只针对主数据集 `pv_cumulative_labeled_merged.parquet`
（35 个日期散落 10 个不连续簇，密度 0.052）。**换数据源后已经做成了**：

`backend-service/datasets/dataset_combined.parquet` —— 2020-05-06 ~ 05-12，
**7 天全连续**（密度 1.0），241 设备，6 类，2,918 窗口。

| 口径 | MiniRocket F1 | MultiRocket F1 | 聚合特征基线 F1 |
|---|---|---|---|
| A 按设备划分（原口径，同期跨设备） | 0.7623 | 0.7303 | 0.7747 |
| B 按日期划分（末 3 天，训练未见） | 0.7147 | 0.7542 | 0.5993 |
| **C 双隔离（末 3 天未见日期 × 未见过的 30% 设备）** | 0.6940 | **0.7635** | **0.4316** |

> 注：这里的「日期隔离」是**评估协议**（test 用训练未出现过的日期），任务仍是
> 故障诊断（回看已发生的时序），**不是** Prognosis / 故障预测。详见
> `docs/docs_zxk/时序故障诊断完整入门.md` §9.2。

口径 C 已验证 设备重叠=0、日期重叠=0、字节级相同窗口=0。

> ⚠️ 上表是**单次划分**结果。后续方差量化发现单次数字不可信（见下节 v4），
> 请以 v4 的 mean ± std 为准。

完整调研记录见 `backend-service/data/tsc_experiments/time_split_report.json`。

#### v4 最终数字：方差量化后（当前唯一应引用的口径）

**触发**：同一协议（口径 C, window=288/stride=72）两次运行得到 0.7635 与 0.6495，差 0.11。
之前所有数字都是单次划分，必须量化方差。

**协议**：`dataset_combined`，口径 C 三隔离，固定时间切点 2020-05-09，
对「保留哪 30% 设备」跑 **10 个种子**。10/10 种子隔离自检全部通过
（设备重叠=0、日期重叠=0、字节级相同窗口=0）。

| 模型 | macro F1(全类) | balanced accuracy | accuracy |
|---|---|---|---|
| **MultiRocket** | **0.6315 ± 0.0750** [0.517, 0.719] | 0.7747 ± 0.1181 | 0.8881 ± 0.0420 |
| MiniRocket | 0.5534 ± 0.0789 [0.446, 0.685] | 0.7348 ± 0.1021 | 0.8501 ± 0.0464 |
| 聚合特征基线 | 0.5222 ± 0.0520 [0.449, 0.627] | 0.6335 ± 0.0879 | 0.8561 ± 0.0389 |

**配对差 MultiRocket − 聚合特征 = +0.1094 ± 0.0669，9/10 种子胜出。**

**结论**：

1. **TSC 路线的真实价值 = 相对聚合特征 +0.11 macro F1**，9/10 划分下成立。
   不是单次划分看到的 +0.33（那是运气好的划分），但是稳定、可辩护的结论。
2. **选型见下方「选型结论」**（原先「差 0.078 大于两者标准差」的推理不成立，已用配对差替代）。
3. **单次划分不可引用**：std=0.075、极差 0.20。所有对外数字必须给 mean ± std（≥10 次划分）。

#### 选型结论（2026-08-03，基于逐划分配对差）

**统计方法更正**：判断两个模型谁更好，应看**逐划分配对差**（同一划分上比较），
不能拿差值跟各自的标准差比 —— 后者忽略了两个模型在同一划分上的相关性。
原先「0.6315 vs 0.5534，差 0.078 大于两者标准差」的推理**不成立**，已重做。

口径 C 三隔离 / 10 次划分 / baseline = MiniRocket：

| 模型 | macro F1 | balanced accuracy | 相对 MiniRocket 配对差 | 胜出 |
|---|---|---|---|---|
| **MultiRocket** | **0.6031 ± 0.0596** | 0.7564 ± 0.0991 | **+0.0782 ± 0.0665** | **9/10** |
| MiniRocket | 0.5249 ± 0.0606 | 0.7122 ± 0.0760 | 基线 | — |
| ROCKET+RF | 0.5105 ± 0.0190 | 0.6269 ± 0.0571 | −0.0145 ± 0.0564 | 4/10 |
| ROCKET | 0.4680 ± 0.0538 | 0.5874 ± 0.0708 | −0.0569 ± 0.0703 | 2/10 |

**结论：选 MultiRocket**。配对差 +0.0782 ± 0.0665，9/10 划分胜出，
均值略大于标准差 —— 属「较可靠」而非「压倒性」（有 1 次划分它输了 0.0547）。
Tier 2/3 已于 GPU 服务器补测完毕并全部落败（见下方「Tier 2/3 GPU 服务器补测结果」），
**选型至此定论**。

**注意 ROCKET 的反转**：它在全量数据集按设备划分时排第一（0.8987），
在严格口径下垫底（0.4680）。这说明**排名对评估协议高度敏感**，
只有严格口径的排名有参考价值。

#### Tier 2/3 GPU 服务器补测结果（2026-08-04，选型定论）

在 GPU 服务器上以**同一严格口径**（strict 三隔离 / 10 折 / `epochs=200`）补测完 Tier 2/3。
`epochs=200` 与 GPU 双双给足，不存在"训练不充分"的辩解空间。

| 模型 | macro F1 | balanced Acc | vs MultiRocket（配对差） | 胜出 |
|---|---|---|---|---|
| **multirocket** | **0.6162 ± 0.0710** | **0.7650 ± 0.1053** | baseline | — |
| inception_single | 0.5097 ± 0.0845 | 0.6022 ± 0.1055 | −0.1065 | 2/10 |
| inceptiontime（ensemble） | 0.4967 ± 0.0564 | 0.6045 ± 0.0778 | −0.1195 | **0/10** |
| cnn_bilstm_attention | 0.4546 ± 0.0592 | 0.5878 ± 0.0687 | −0.1616 | 1/10 |
| resnet | 0.4256 ± 0.0470 | 0.5638 ± 0.0766 | −0.1906 | **0/10** |
| cnn_lstm | 0.4242 ± 0.0470 | 0.5556 ± 0.0654 | −0.1920 | **0/10** |

**★ 跨环境复现验证（意外收获，价值很高）**

| 环境 | MultiRocket macro F1 | balanced Acc |
|---|---|---|
| 本机 Windows / CPU / numpy 2.2.6 / tensorflow-cpu | 0.6176 ± 0.0631 | 0.7649 ± 0.0947 |
| 服务器 Linux / GPU / torch 2.13+cu126 / TF 2.21 GPU | 0.6162 ± 0.0710 | 0.7650 ± 0.1053 |

**差 0.0014**。不同 OS、不同 CUDA/依赖栈、CPU vs GPU 下 baseline 复现到小数点后三位，
说明整条链路（切分 → 预处理 → 严格划分 → 指标）**无环境依赖的隐藏问题**。

**结论**

1. **选型确定：MultiRocket**。三个深度模型 0/10 胜出，配对差 −0.11 ~ −0.19，量级远超噪声。
2. **v1「深度模型垫底」的结论成立，但原因归属要改**：
   - v1 的推理链（脏数据 + 只取 200 设备）作废，这点不变；
   - 但用干净数据 + 严格口径 + 充分训练**独立重验后结论相同**。
   - 真实原因不是"我取样太少"，而是**可用数据本身就只有这么多**——严格口径下
     训练集约 870 窗口，对深度网络仍然过小。
   - **推论**：若将来窗口量上到数万级，深度模型值得重新评估；当前数据规模下可关闭该线。
3. **ensemble 未带来收益**：`inceptiontime`(0.4967) 略低于 `inception_single`(0.5097)，
   但差 0.013 在两者 std（0.056~0.085）之内，**不能断言 ensemble 更差**，
   只能说小样本下 5 个成员各自欠拟合，集成救不回来。
4. **Windows 文件锁诊断已证实**：InceptionTime ensemble 在 Linux 上正常跑通，
   `.keras` PermissionError 不复现。

**服务器侧处理的三个环境问题**（迁移到其他机器时会再遇到）：

| 问题 | 解法 |
|---|---|
| TF 缺 `ptxas` / `LD_LIBRARY_PATH` | 装 `nvidia-cuda-nvcc-cu12` 并设置库路径 |
| **TF 与 PyTorch 同进程抢 GPU 导致 segfault** | Tier 3 用独立进程跑（`scripts/eval_tsc_tier3_continue.py`） |
| GPU0 上有 vLLM 占用 | 实验绑 `CUDA_VISIBLE_DEVICES=1` |

**服务器交付物**：
- 主结果 `backend-service/data/tsc_experiments/tier23_strict/results.json`
- Ensemble `backend-service/data/tsc_experiments/tier23_inception_ensemble/results.json`
- 汇总 `backend-service/data/tsc_experiments/SERVER_GPU_DELIVERY.json`
- 单测 83 passed（本机 97）。差 14 个，等于 `test_pv_2021_11_labeling_batch.py` 的用例数，
  应为 `datasets/pv_labeling_batch_2021_11.parquet` 未传到服务器而 **skip**（非失败）。
  若要在服务器做标注工作，需传该文件或重跑 `scripts/build_pv_2021_11_labeling_batch.py`。

#### 仍未解决的唯一开放项

**只在一个数据块上验证过**：`dataset_combined`，241 设备、**单站点**、7 天，
训练集约 870 窗口。跨站点、跨季节泛化**仍未验证**。

这也是 2021-11 待标注批次（5 站点 / 304 设备 / 7 天连续 / 731 个待标注单元）
要解决的问题 —— 见上文「已落地：2021-11 待标注批次」。

**当前状态**：MultiRocket 选型已定，可注册为 `fallback_path`。
提升为 `production_path` 前建议补齐跨站点验证。

**次要遗留**：`get_model()` 未给 aeon 模型传 `random_state`，故报告的 std 同时包含
「划分差异」与「模型内部随机性」。这反映真实部署波动，但若要单独量化划分方差，
需固定模型随机种子重测。

**数字演变（务必只引用 v4）**：
`v1 0.9579`（脏数据+200设备）→ `v2 0.8945`（口径错误+退化窗口）
→ `v3 0.7349`（全类口径+剔除退化窗口，但仍宽松口径+单次）
→ **`v4 0.6315 ± 0.0750`（严格三隔离+10种子）**

完整记录见 `backend-service/data/tsc_experiments/variance_quantification/results.json`。

#### 已落地：严格口径多次划分评估（2026-08-03）

方差量化结论已固化为代码，**对外数字必须走这条路径**。

新增 `services/iterative_labeling/tsc/tsc_strict_eval.py`：

| 能力 | 说明 |
|---|---|
| 三种划分口径 | `strict`（时间+设备双隔离，默认）/ `time` / `device`，严格程度递增 |
| 多次划分 | 默认 10 次，输出每个指标的 `{mean, std, min, max, n}` |
| 隔离自检 | 每次划分校验 设备重叠 / 日期重叠 / 字节级相同窗口，不通过则跳过该划分 |
| 全类口径 | 所有 macro 指标固定 `labels=完整标签空间`，杜绝稀有类缺席导致的虚高 |
| 逐划分配对差 | 同一划分上与基线比较，消除划分难度影响，比各自 mean±std 更可靠 |
| 不足 10 次告警 | `n_repeats < 10` 时结果里带 `warning`，提示标准差不可靠 |

配套改动：

- `tsc_model_compare.py` 新增 `run_strict_comparison()`；旧的 `run_model_comparison()`
  docstring 加了显著警告（单次划分不可对外引用）。
- `tsc_compare_job.py` / `POST /api/iterative-labeling/tsc/compare` 新增
  `evaluation`（`strict` 默认 / `legacy`）、`split_mode`、`n_test_days`、
  `held_device_ratio`、`baseline_model` 参数；启动时若 `n_repeats < 10`
  或选了 `legacy`，响应里返回 `warning`。
- 前端 `ModelCompareTab.tsx`：指标列改为 `mean ± std` 展示，新增 balanced accuracy 列
  与「划分数」列（<10 标橙色），legacy 口径顶部显示黄色警告条，
  并新增「相对基线的逐划分配对差」表格。
- 测试 `tests/test_tsc_strict_eval.py`（15 用例）覆盖三口径隔离性质、mean±std 结构、
  全类口径、配对差、日期不足守卫。

#### 已落地：2021-11 待标注批次（2026-08-03）

`scripts/build_pv_2021_11_labeling_batch.py` 已生成
`backend-service/datasets/pv_labeling_batch_2021_11.parquet`：

| 指标 | 值 | 对比现有唯一可用块 |
|---|---|---|
| 行数 | 157,872 | — |
| 站点 | **5** | dataset_combined 只有 1 |
| 设备 | **304** | dataset_combined 241 |
| 序列 | 601 | — |
| 日期 | **7 天全连续**（2021-11-18~24） | 同为 7 天 |
| 待标注单元（设备×日期） | **731** | — |
| value/i_cal 缺失率 | 0.0 | — |

脚本已剔除 88,985 行（36%）已存在于主数据集的数据，并按主键去重。
`tests/test_pv_2021_11_labeling_batch.py`（14 用例）验证了 `from-dataset` 端点契约、
与主数据集零重叠、7 天连续性、多站点、可被切分器正常切窗。

**启动标注**：
```
POST /api/iterative-labeling/review-sessions/from-dataset
{
  "dataset_path": "backend-service/datasets/pv_labeling_batch_2021_11.parquet",
  "slot": "pv_fault",
  "reviewer": "<标注人>",
  "max_units": 731
}
```

标注完成后可得**第二个连续多站点评估块** → 支撑跨站点泛化验证，并把当前 0.075 的方差降下来。

#### 服务器迁移（Tier 2/3 实验，2026-08-04）

**动机**：Tier 2/3 深度模型在本机跑不动。日志确认
`TensorFlow GPU support is not available on native Windows for TF >= 2.11`，
全靠 CPU：ResNet 单次划分 3~4 分钟，4 个深度模型 × 10 次划分预计 **2.5~3 小时**。
Linux + CUDA 下可获数量级加速。

**本机已完成的部分**（不必在服务器重跑，但建议重跑以保证同批划分可比）：
`multirocket` 基线 10 次划分 macroF1 = 0.6176 ± 0.0631，balAcc = 0.7649 ± 0.0947。
结果在 `data/tsc_experiments/tier23_strict/results.json`（脚本逐模型增量落盘）。

**需要传到服务器的文件**

| 类别 | 路径 |
|---|---|
| 评估脚本 | `backend-service/scripts/eval_tsc_tier23_strict.py` |
| TSC 模块 | `backend-service/services/iterative_labeling/tsc/`（整个目录） |
| 依赖清单 | `backend-service/requirements-tsc.txt` |
| 评估数据 | `backend-service/datasets/dataset_combined.parquet`（唯一能做时间切分的块） |
| 待标注批次 | `backend-service/datasets/pv_labeling_batch_2021_11.parquet` |
| 测试 | `backend-service/tests/test_tsc_*.py`、`test_sliding_window_sampler.py` |

**⚠️ 依赖冲突必须先决策**：`requirements.txt` 钉 `numpy==1.24.3`，
TensorFlow 2.21 要求 `numpy>=2`，无法共存。三个方案见 `requirements-tsc.txt` 头部注释。
**建议用独立 conda 环境跑 TSC 实验**，与后端服务环境分开。
本机实测漂移仅 numpy(1.24.3→2.2.6) 与 scipy(1.11.4→1.15.3) 两个包。

**Linux 上应重新验证的 Windows 特有问题**

| 问题 | 本机表现 | Linux 预期 | 动作 |
|---|---|---|---|
| `InceptionTimeClassifier`（5 模型 ensemble） | 写 `.keras` 检查点报 `PermissionError`，只能退化用 `inception_single` | Windows 文件锁特有，Linux 很可能正常 | **重新启用 ensemble 版本**测一次；若通过，把 `inception_single` 降为备选 |
| `_atomic_write_json` 的 `os.replace` | 目标被读取时报 `PermissionError [WinError 5]`，已加重试 | Linux 的 replace 对已打开文件不失败 | 重试逻辑保留（无害），但根因是 Windows-only |
| TensorFlow GPU | 官方不支持 Windows | CUDA 可用 | `tensorflow-cpu` 换成 `tensorflow`，`torch` 换 cu121 版 |
| `aip.ps1` 的 `Stop-AIP` | 无差别 kill 所有 python/node，会杀掉实验进程 | Linux 需另写 | 服务器上按端口或 PID 文件精确匹配，别用广播 kill |

**迁移后的执行顺序**

```bash
# 1. 先验证环境（必须先跑测试，别直接开实验）
cd backend-service
python -m pytest tests/test_sliding_window_sampler.py tests/test_tsc_data_loader.py \
                 tests/test_tsc_model_wrapper.py tests/test_tsc_pipeline.py \
                 tests/test_tsc_strict_eval.py -q          # 期望 96 passed

# 2. 确认 GPU 生效（否则跟本机一样慢，白迁）
python -c "import torch; print('torch cuda:', torch.cuda.is_available())"
python -c "import tensorflow as tf; print('tf gpu:', tf.config.list_physical_devices('GPU'))"

# 3. 跑 Tier 2/3 补测（逐模型增量落盘，中断不丢已完成结果）
python scripts/eval_tsc_tier23_strict.py --n-repeats 10 --epochs 60

# 4. 可选：重试 InceptionTime ensemble（本机因 Windows 文件锁失败）
python scripts/eval_tsc_tier23_strict.py --models inceptiontime --n-repeats 10
```

**注意**：`--epochs 60` 是本机为控时长选的折中值。服务器有 GPU 后应提到
150~200 并依赖 early stopping，否则深度模型欠拟合、对比不公平——
这正是 v1「深度模型垫底」结论作废的原因之一。

#### 数据集扩充可行性（2026-08-03 调研）

**结论：简单拼接零增量；缩短窗口有害；真正空间是标注未标注数据。**

1. **拼接无用**。按 `site|device|branch|time` 主键验证，所有**带标签**源已 100% 在
   主数据集内：`dataset_combined` 100%、`xiangyin` 100%、`yuncheng` 100%、
   `zhongqi` 100%、`huarong&1008` 100%。主数据集就是它们的并集。

2. **缩短窗口反而变差**（严格口径实测，MultiRocket）：

   | window/stride | 窗口数 | macro F1 | 变化 | 隔离 |
   |---|---|---|---|---|
   | 288/72 | 2,918 | 0.6495 | 基线 | OK |
   | 288/36 | 5,613 | 0.5730 | -0.077 | OK |
   | 144/36 | 6,902 | 0.5164 | -0.133 | OK |
   | 144/18 | 13,612 | 0.5256 | -0.124 | OK |
   | 96/24 | 9,978 | 0.5217 | -0.128 | **BAD** |
   | 72/18 | 12,469 | 0.4892 | -0.160 | **BAD** |

   原因：**当前标签存量** 99.96% 是天级粒度，整天窗口（288）恰好匹配；更短窗口只看到
   一天的一部分，无法判定当天标签。且窗口越短越容易在不同设备间字节级相同，反而引入新泄漏。
   **保持 288/72，不要缩短。**

   注意这是**存量结论而非架构结论**：标注系统支持子天 `human_range` 框选，
   若子天标签大量积累（当前仅 2 条操作 / 293 点），该论证需重新评估。

3. **未标注数据可扩 +52%**：`相关数据/train_ori/` 下有 **552,664 行**未标注数据，
   覆盖 **9 站点 / 1180 设备 / 18 个日期**，完全不在主数据集内。

   **最高价值目标：标注 2021-11-18~24 块（7 天全连续）的 5 个未标注站点**
   （huarong 98 设备、peixian 64、laobagang 33、zhongqi 18、qiyang 7，约 220 设备）。
   标注后可得**第二个 7 天连续多站点评估块** → 能做跨站点/跨季节泛化验证，
   并把当前 0.075 的方差降下来。走现有迭代标注闭环（`point_labels`）即可。

   次优目标：`dangyang`（229K 行 / 650 设备 / 最长连续 9 天），单文件体量最大。

4. **硬限制**：现有所有数据源最长连续段只有 **9 天**。要验证跨季/跨月漂移
   必须采集连续 ≥ 30 天的数据，**这个无法靠拼接解决**。

完整记录见 `backend-service/data/tsc_experiments/expansion_and_variance_report.json`。

#### 仍然无法用当前数据解决的遗留风险

- **时间外推距离很短**：`dataset_combined` 只有 6 个可切窗日期，test 最多覆盖 2~3 天，
  无法验证跨季/跨月漂移。若要更长外推，需采集**连续 ≥ 30 天且类别较均衡**的数据——
  现有全部数据源都不满足。
- **单站点**（241 设备）→ 无法验证跨站点泛化。
- `xiangyin` 块虽有 9 天连续 / 1078 设备（拼 yuncheng 后），但切窗后 **90% 属单一类**
  （label 1 占 2706/3007），macro F1 无统计意义；只适合做「正常 vs 异常」二分类验证。
- 单日 test 集不可信：口径 B「后 2 天」实际只覆盖 1 个日期，聚合特征基线拿到 0.9630
  的异常值。**任何 test 覆盖 < 2 个日期的结果都不应采信。**
- 结论基于单次划分，未做 rolling-origin 多切点验证，方差未量化。
- **标签存量 99.96% 是天级粒度**（(site,device,branch,date) 内 label 唯一比例 99.96%，
  已直接查 `point_labels` 原表确认，非快照拍平所致），本质是「给一天分类」。
  spec 原本的「跨天建模」卖点在此数据上无法体现。
  **这是存量限制不是架构限制**：`label_ops` 实测 active 4,479 条中 `day_label`（整天）
  4,457 条、`human_day`（整天）20 条、`human_range`（子天）仅 2 条；`point_labels`
  1,058,438 点中 `human_range` 仅 293 点。子天能力已具备且已验证落地，缺的是标注量。
- **有效独立单元 4,457 个 device-day**，6,533 窗口是 1.54x 重叠虚增，
  统计效力低于窗口数暗示的水平。
- 稀有类 label 9(1 个)/10(9 个)/12(17 个) 使 macro F1 方差大，0.73 的置信区间较宽。

#### 尚未完成

- Tier 2/3 未在修复后的数据 + 正确口径下重跑（v1 的「深度模型垫底」结论同样作废）。
- 未跑交叉验证，方差未量化（当前仅单次 holdout）。
- 未与 RF 路线在统一口径（同数据集/同 min_std/同 labels 全集）下对比。

**已知环境问题**：aeon 1.3.0 的 `InceptionTimeClassifier`（5 模型 ensemble）在
Windows + Keras 3.12 下写 `.keras` 检查点报 `PermissionError`（同家族 ResNet 用同一目录正常）。
已注册 `inception_single`（`IndividualInceptionClassifier`）替代评估 Inception 架构本身；
Linux 服务器上可重试 ensemble 版本。

### 2.4 模型选择决策树

```
START
  │
  ├─ 跑 Tier 1（MiniRocket / MultiRocket / ROCKET）
  │     │
  │     ├─ 时序路线 Tier 1 最佳 F1 > RF 路线 F1 + 2%？
  │     │     │
  │     │     ├─ YES → 时序形态有价值，继续 Tier 2
  │     │     │         │
  │     │     │         ├─ InceptionTime > Tier 1 最佳 + 2%？
  │     │     │         │     ├─ YES → 深度模型有增益，考虑 Tier 3
  │     │     │         │     └─ NO  → 选 Tier 1 最佳（性价比最优）
  │     │     │         │
  │     │     │         └─ ...
  │     │     │
  │     │     └─ NO  → 时序形态对该数据集帮助不大，维持 RF 路线
  │     │
  │     └─ （同时跑 ROCKET+RF 对照，归因精度来源）
  │
  └─ END: 产出最终推荐模型 + 部署配置
```

## 三、训练与评估 Pipeline

### 3.1 Pipeline 全流程

```
┌─────────────────────────────────────────────────────────────────┐
│                     TSC Training Pipeline                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. 数据加载                                                      │
│     ├─ 从 training_samples 读取功率时序                            │
│     └─ 从 point_labels 读取逐点标签                               │
│                                                                   │
│  2. 滑动窗口切分                                                   │
│     ├─ SlidingWindowSampler.transform()                           │
│     ├─ 产出: X[n, window_length, channels], y[n], meta[n]        │
│     └─ 记录: n_samples, class_distribution, purity_stats          │
│                                                                   │
│  3. 数据预处理                                                     │
│     ├─ NaN 插值（线性插值 / 前值填充）                              │
│     ├─ 归一化（per-sample z-score 或 min-max，可配置）              │
│     └─ 类别不平衡处理（见 3.3）                                    │
│                                                                   │
│  4. 交叉验证训练与评估                                              │
│     ├─ StratifiedKFold（n_splits=5）× n_repeats                   │
│     ├─ 每个 fold: fit → predict → 收集指标                         │
│     └─ 汇总: macro_f1_mean/std, accuracy_mean/std, per-class F1   │
│                                                                   │
│  5. 模型持久化                                                     │
│     ├─ 最佳模型 → .pkl / .pt                                      │
│     ├─ 窗口配置 → metadata.json                                   │
│     └─ 评估报告 → evaluation_report.json                          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 评估指标体系

与 RF 路线（`split_mode_compare.py`）保持完全一致的指标输出：

| 指标 | 计算方式 | 对应 RF 路线字段 |
|------|----------|-----------------|
| `macro_f1_mean` | 各 fold macro-F1 的均值 | `macro_f1_mean` |
| `macro_f1_std` | 各 fold macro-F1 的标准差 | `macro_f1_std` |
| `accuracy_mean` | 各 fold accuracy 的均值 | `accuracy_mean` |
| `accuracy_std` | 各 fold accuracy 的标准差 | `accuracy_std` |
| `macro_precision_mean` | 各 fold macro-precision 的均值 | `macro_precision_mean` |
| `macro_recall_mean` | 各 fold macro-recall 的均值 | `macro_recall_mean` |
| `n_samples` | 窗口样本总数 | `n_samples` |
| `n_classes` | 类别数 | `n_classes` |

额外输出（时序路线特有）：

| 指标 | 说明 |
|------|------|
| `per_class_f1` | 每个故障类型的 F1 |
| `confusion_matrix` | 混淆矩阵 |
| `train_time_sec` | 训练耗时 |
| `predict_time_sec` | 预测耗时（每样本） |
| `model_size_mb` | 模型文件大小 |
| `window_length` | 使用的窗口长度 |
| `stride` | 使用的步长 |
| `n_discarded_windows` | 因纯度不足丢弃的窗口数 |

### 3.3 类别不平衡处理

光伏数据中正常窗口远多于故障窗口（预估 10:1 ~ 50:1），需处理不平衡：

| 策略 | 实现 | 优先级 |
|------|------|--------|
| **窗口重叠过采样** | 故障时段用更小的 stride（如 stride=12 而非 72），自然增加故障样本 | 默认启用 |
| **class_weight** | 训练时按类频率反比加权损失 | 默认启用（深度模型） |
| **SMOTE-TS** | 对时序窗口做 SMOTE 插值 | 可选，Tier 1 不用 |
| **欠采样** | 随机丢弃多数类窗口 | 备用 |

默认组合：`窗口重叠过采样` + `class_weight`。

### 3.4 数据划分策略

关键约束：**同一设备的相邻窗口不能同时出现在训练集和测试集**（数据泄漏风险）。

划分方案：

1. **按设备划分**（推荐）：随机选 80% 设备做训练、20% 做测试。同设备的所有窗口要么全在训练、要么全在测试。
2. **按日期划分**（备选）：所有设备的前 80% 时间做训练，后 20% 做测试。隔离的是**日期**，任务仍是诊断（回看已发生的时序），**不是** Prognosis / 故障预测。
3. **交叉验证内层**：在训练设备上做 StratifiedKFold 选超参。

与 RF 路线对比时，使用**相同的 `random_state=90`** 和**相同的 `test_ratio=0.2`**。

### 3.5 ★ 时间连续性保障（2026-08-04 修复）

**Bug 描述**：原实现 `SlidingWindowSampler.transform()` 按行号滑窗，不检查相邻点时间间隔。
当同一序列来自多个不连续时间段（如累计训练快照把多批次数据 concat 在一起），窗口会
跨过时间缺口，前后半段来自不同月份，产出物理上不存在的假样本。

**实测影响**：

| 数据集 | 跨缝窗口占比 | 最大缺口 |
|---|---|---|
| `dataset_combined`（7 天单块，验证集） | 30.7% | 3 天 |
| `pv_cumulative_labeled_merged`（真实累计产物） | **67.0%** | **92.4 天** |

**修复方案**：`SlidingWindowSampler._split_by_time_gap()` — 扫描相邻点时间差，
超过「中位采样间隔 × `max_gap_multiplier`（默认 2.0）」时断开，只在段内滑窗。
推理侧 `TSCPredictor.predict_device()` 和 `predict_device_multi_window()` 同步修复。

**选型结论影响**：修复前后 `dataset_combined` 上 macro F1 差异 +0.0114（std 噪声内），
MultiRocket ~0.62 的选型结论不受影响（因验证集本身是单块连续数据，缺口极少）。
接入累计训练闭环时影响显著（降低 67% 的假窗口），**接闭环前必须用修复后的版本**。

**配置参数**：`SamplerConfig.max_gap_multiplier`（默认 2.0，设为 0 可关闭检测以向后兼容）。

**修复后严格评估结果**（2026-08-04，dataset_combined，strict 10 折）：

| 模型 | macro F1 | balanced accuracy | 完成折数 |
|---|---|---|---|
| **MultiRocket** | **0.6162 ± 0.0548** | 0.7672 ± 0.1007 | 10/10 |
| MiniRocket | 0.5594 ± 0.0753 | 0.7376 ± 0.0913 | 10/10 |
| MultiRocket vs MiniRocket 配对差 | +0.0568 ± 0.0728 | — | 8/10 胜出 |

与修复前（0.6162 ± 0.0710）完全一致，选型结论不变。窗口数从 2918 降至 2427（−17%），
来自严重跨缝窗口（横跨 2 日及以上）被正确剔除；仅剩 405 个「缺 1~3 个点」的轻微不连续
窗口（最大超出 5 分钟 = 1 个采样点），属正常缺测，不影响信号完整性。


## 四、自定义模型详细设计（Tier 3）

### 4.1 CNN-LSTM 架构

```
输入: [batch, window_length, n_channels]
  │
  ├─ Conv1D(filters=64, kernel=7, padding=same) + BN + ReLU
  ├─ Conv1D(filters=128, kernel=5, padding=same) + BN + ReLU
  ├─ MaxPool1D(pool_size=2)
  ├─ Dropout(0.2)
  │
  ├─ LSTM(units=64, return_sequences=False)
  ├─ Dropout(0.3)
  │
  ├─ Dense(64) + ReLU
  ├─ Dropout(0.3)
  ├─ Dense(n_classes) + Softmax
  │
  └─ 输出: [batch, n_classes] 概率分布
```

### 4.2 CNN-BiLSTM-Attention 架构

```
输入: [batch, window_length, n_channels]
  │
  ├─ 多尺度并行卷积分支:
  │   ├─ Branch A: Conv1D(64, kernel=3) + BN + ReLU
  │   ├─ Branch B: Conv1D(64, kernel=7) + BN + ReLU
  │   ├─ Branch C: Conv1D(64, kernel=15) + BN + ReLU
  │   └─ Branch D: Conv1D(64, kernel=31) + BN + ReLU
  │
  ├─ AdaptiveFeatureFusion: MultiHeadAttention(heads=4) 融合四分支
  │   → [batch, seq_len, 256]
  │
  ├─ BiLSTM(units=128, return_sequences=True)
  ├─ TemporalAttention: 学习每个时间步的重要性权重
  │   → [batch, 256] 加权上下文向量
  │
  ├─ Dense(128) + ReLU + Dropout(0.3)
  ├─ Dense(n_classes) + Softmax
  │
  └─ 输出: [batch, n_classes]
```

### 4.3 ROCKET + RF 两阶段

```
输入: [n_samples, window_length, n_channels]
  │
  ├─ ROCKET Transform (10000 kernels)
  │   → [n_samples, 20000] 特征矩阵
  │
  ├─ StandardScaler
  │
  ├─ RandomForestClassifier(n_estimators=200, class_weight="balanced")
  │
  └─ 输出: 分类标签
```

## 五、与逐点标签 spec 的集成

### 5.1 标签读取

时序路线从 `point_labels` 表读取标签，调用方式：

```python
from services.db.repositories.point_label import PointLabelRepository

repo = PointLabelRepository(session)
labels = repo.query_by_device_and_range(
    site_id=site_id,
    device_id=device_id,
    branch_id=branch_id,
    t_start=t_start,
    t_end=t_end,
)
# 返回 DataFrame[time, label_id]
```

不新建标签表，不自管标签（需求 3 第 1~2 条）。

### 5.2 接入 split_mode_compare 对比框架

在 `split_mode_compare.py` 中扩展，注册时序路线为一个特殊的 "mode"：

```python
# 新增 mode
TSC_MODES = [
    "tsc_minirocket",
    "tsc_multirocket",
    "tsc_inceptiontime",
    # ...
]

MODE_LABELS.update({
    "tsc_minirocket": "时序-MiniRocket",
    "tsc_multirocket": "时序-MultiRocket",
    "tsc_inceptiontime": "时序-InceptionTime",
})
```

或者更合理的方式——新建独立的 `tsc_model_compare.py`，但输出格式与 `split_mode_compare.py` 完全对齐（相同的 `macro_f1_mean`/`accuracy_mean` 等字段），使前端对比页可以直接把两条路线的结果放在一张表里。

### 5.3 production_path / fallback_path 双指针

逐点标签 spec 需求 23 定义了双路径生产管理：

```json
{
  "production_path": "rf",           // 当前生产模型路径
  "fallback_path": "tsc_multirocket", // 备用路径
  "switch_condition": {
    "metric": "macro_f1",
    "threshold_diff": 0.02,           // 时序路线超过 RF 2% 才切换
    "min_validation_windows": 3       // 至少在 3 个验证窗口上优于 RF
  }
}
```

切换逻辑：
- 默认 `production_path = "rf"`（RF 路线已验证可用）。
- 当时序路线在多次验证中稳定优于 RF 路线（macro_f1 差 ≥ 2%），人工确认后切换。
- `fallback_path` 始终保留另一条路线，异常时可快速回退。

## 六、前端接入设计

### 6.1 现有前端入口分析

当前光伏故障诊断前端入口为 `/iterative-labeling`（`IterativeLabelingListPage.tsx`），包含四个 Tab：

| Tab | 功能 | 对应后端 |
|-----|------|----------|
| 审核会话 | 展示待审核批次，入口进入审核页 | review-sessions API |
| 数据准入 | 从数据库拉取候选样本 | training-workspace API |
| 聚类标注 | 对无标签数据聚类标注 | clustering API |
| 累计训练 | 训练状态、重训请求 | cumulative-training API |

前端已定义（但尚无 UI 消费）的相关 API：
- `getSplitModeCompare` / `runSplitModeCompare` — 切分模式对比
- `getModelingPathCompare` / `runModelingPathCompare` — 建模路径对比（RF vs TSC）
- `getModelingPaths` / `setModelingPaths` / `switchModelingFallback` — 生产/备用路径管理

### 6.2 TSC 前端接入方案

#### 方案：在 IterativeLabelingListPage 新增「模型对比」Tab

```
IterativeLabelingListPage
├── Tab: 审核会话（现有）
├── Tab: 数据准入（现有）
├── Tab: 聚类标注（现有）
├── Tab: 累计训练（现有）
└── Tab: 模型对比（新增）← TSC 前端入口
         ├── 区域 1: 切分模式对比（RF 路线各 solar_mode 互比）
         ├── 区域 2: 建模路径对比（RF vs TSC 各模型跨路线比）
         ├── 区域 3: 生产/备用路径管理（当前生产模型、切换按钮）
         └── 区域 4: TSC 实验详情（窗口参数、训练曲线、混淆矩阵）
```

#### 6.2.1 模型对比 Tab 布局

```
┌─────────────────────────────────────────────────────────────────┐
│  模型对比                                              [刷新] [▶ 启动对比]  │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─── 建模路径对比 ────────────────────────────────────────────┐  │
│  │  当前生产路径: [RF - daylight]     备用路径: [TSC - MultiRocket]  │  │
│  │  [切换到备用路径]  [历史切换记录]                              │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─── 精度对比表 ──────────────────────────────────────────────┐  │
│  │  模型          │ macro_F1 │ accuracy │ 训练耗时 │ 状态       │  │
│  │  RF-daylight   │ 0.82     │ 0.85     │ 12s     │ 生产中     │  │
│  │  RF-multiscale │ 0.80     │ 0.83     │ 15s     │ —          │  │
│  │  TSC-MultiRocket│ 0.87    │ 0.89     │ 3s      │ 备用       │  │
│  │  TSC-InceptionTime│ 0.88  │ 0.90     │ 180s    │ —          │  │
│  │  TSC-CNN-LSTM  │ 0.89     │ 0.91     │ 600s    │ —          │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌─── TSC 实验详情（折叠区）──────────────────────────────────┐  │
│  │  窗口参数: window_length=288, stride=72                      │  │
│  │  样本量: 1200 窗口（normal:800, shadow:200, degrade:150...）  │  │
│  │  混淆矩阵: [可视化]   训练曲线: [loss/acc 折线图]            │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

#### 6.2.2 前端新增组件

| 组件 | 路径 | 职责 |
|------|------|------|
| `ModelCompareTab` | `frontend-sevice/src/components/pv-fault/ModelCompareTab.tsx` | 模型对比 Tab 主组件：精度表 + 路径管理 + 启动对比 |
| `TscExperimentDetail` | `frontend-sevice/src/components/pv-fault/TscExperimentDetail.tsx` | TSC 实验详情：窗口配置、混淆矩阵、class 分布、训练曲线 |
| `ModelPathManager` | `frontend-sevice/src/components/pv-fault/ModelPathManager.tsx` | 生产/备用路径展示与切换操作 |
| `ConfusionMatrixChart` | `frontend-sevice/src/components/pv-fault/ConfusionMatrixChart.tsx` | ECharts 热力图展示混淆矩阵 |

#### 6.2.3 前端 API 调用（已有，补齐调用）

```typescript
// iterativeLabelingApi.ts 中已定义的方法（当前无 UI 消费，本次接入）：

// 1. 建模路径对比 — 跑 RF vs TSC 多模型对比
cumulativeTrainingApi.runModelingPathCompare({
  paths: ['rf_daylight', 'tsc_multirocket', 'tsc_inceptiontime'],
  nRepeats: 5,
  testRatio: 0.2,
  randomState: 90,
})

// 2. 获取对比结果
cumulativeTrainingApi.getModelingPathCompare(slot)

// 3. 获取/设置生产路径
cumulativeTrainingApi.getModelingPaths(slot)
cumulativeTrainingApi.setModelingPaths('tsc_multirocket', 'rf_daylight', slot)

// 4. 切换到备用路径
cumulativeTrainingApi.switchModelingFallback('TSC 精度持续优于 RF 2%+', slot)
```

需要**新增**的前端 API 方法（对应后端 TSC 实验接口）：

```typescript
// iterativeLabelingApi.ts 新增

export const tscExperimentApi = {
  // 启动 TSC 模型对比实验
  startTscCompare: (
    body: {
      modelNames?: string[];
      windowConfigs?: Array<{ window_length: number; stride: number }>;
      nRepeats?: number;
      testRatio?: number;
      tierFilter?: number;
    },
    slot = 'pv_fault',
  ): Promise<Record<string, unknown>> =>
    api.post('/iterative-labeling/tsc/compare', body, { params: { slot } }),

  // 获取 TSC 对比状态（轮询）
  getTscCompareStatus: (slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/tsc/compare/status', { params: { slot } }),

  // 获取 TSC 对比结果
  getTscCompareResult: (slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/tsc/compare/result', { params: { slot } }),

  // 获取可用模型列表
  listModels: (slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/tsc/models', { params: { slot } }),
};
```

#### 6.2.4 后端 API 端点规划

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/iterative-labeling/tsc/compare` | 启动 TSC 多模型对比实验（异步） |
| GET | `/api/iterative-labeling/tsc/compare/status` | 轮询实验进度 |
| GET | `/api/iterative-labeling/tsc/compare/result` | 获取实验结果（含 ranking） |
| GET | `/api/iterative-labeling/tsc/models` | 列出可用 TSC 模型及其 tier/GPU 要求 |

这些端点接入现有 `backend-service/api/iterative_labeling.py` 路由文件，使用 `tsc_model_compare.py` 中的 `start_tsc_compare_job` / `load_tsc_compare_status` / `load_tsc_compare_result`。

### 6.3 用户交互流程

```
用户打开 /iterative-labeling → 点击「模型对比」Tab
  │
  ├─ 首次加载：展示空态或上次实验结果
  │
  ├─ 点击「▶ 启动对比」
  │     ├─ 弹出配置弹窗：选择模型（Tier 1/2/3 复选）、窗口参数、重复次数
  │     ├─ 确认后调用 POST /tsc/compare → 返回 job_id
  │     └─ 前端轮询 GET /tsc/compare/status 展示进度条
  │
  ├─ 实验完成：
  │     ├─ 精度对比表自动刷新
  │     ├─ 高亮最佳模型（按 macro_F1 排序第一）
  │     └─ 若 TSC 最佳 > RF 最佳 + 2%，弹出建议 Alert
  │
  └─ 切换生产路径：
        ├─ 点击「设为生产路径」
        ├─ 二次确认弹窗：显示精度对比 + 风险提示
        └─ 确认后调用 PUT /modeling-paths → 刷新状态
```

### 6.4 路由规划

无需新增路由。TSC 前端入口以 Tab 形式嵌入现有 `/iterative-labeling` 页面，不新开页面。

如果后续内容过多需要独立页面，可以在 `/iterative-labeling/tsc-compare` 新增路由，但初期不需要。

## 七、文件结构规划（含前端）

```
backend-service/
├── api/
│   └── iterative_labeling.py                 ← 现有，新增 TSC 对比 4 个端点
├── services/
│   └── iterative_labeling/
│       ├── tsc/                              ← 新增：时序分类模块
│       │   ├── __init__.py
│       │   ├── sliding_window_sampler.py     ← 滑动窗口切分器
│       │   ├── data_loader.py               ← 多设备批量加载与划分
│       │   ├── model_registry.py            ← 模型注册表
│       │   ├── model_wrapper.py             ← 统一模型包装器
│       │   ├── tsc_pipeline.py              ← 训练评估 pipeline
│       │   ├── tsc_model_compare.py         ← 多模型对比运行器
│       │   ├── tsc_compare_job.py           ← 异步任务入口
│       │   ├── tsc_predictor.py             ← 预测侧接口
│       │   └── custom_models/               ← 自实现的 Tier 3 模型
│       │       ├── __init__.py
│       │       ├── cnn_lstm.py
│       │       └── cnn_bilstm_attention.py
│       └── split_mode_compare.py            ← 现有，扩展 TSC 模式（或由 tsc_model_compare 独立输出）
├── data/
│   └── tsc_experiments/                      ← 实验结果存储
│       └── {experiment_id}/
│           ├── config.json                   ← 实验配置
│           ├── results.json                  ← 全量结果
│           └── models/                       ← 持久化的最佳模型
│               └── {model_name}_{window_length}.pkl
└── tests/
    ├── test_sliding_window_sampler.py        ← 切分器单测
    ├── test_tsc_model_wrapper.py             ← 模型包装器单测
    └── test_tsc_pipeline.py                  ← Pipeline 单测

frontend-sevice/
├── src/
│   ├── components/
│   │   └── pv-fault/
│   │       ├── ModelCompareTab.tsx            ← 新增：模型对比 Tab 主组件
│   │       ├── TscExperimentDetail.tsx        ← 新增：TSC 实验详情（窗口、混淆矩阵、曲线）
│   │       ├── ModelPathManager.tsx           ← 新增：生产/备用路径管理
│   │       └── ConfusionMatrixChart.tsx       ← 新增：混淆矩阵热力图
│   ├── pages/
│   │   └── IterativeLabelingListPage.tsx      ← 改造：新增「模型对比」Tab
│   └── services/
│       └── iterativeLabelingApi.ts            ← 改造：新增 tscExperimentApi
```

## 八、依赖与环境

### 8.1 新增 Python 依赖

| 包 | 版本 | 用途 | 体积 |
|---|---|---|---|
| `aeon` | >=0.9.0 | TSC 模型统一框架（ROCKET/InceptionTime/ResNet） | ~50MB |
| `torch` | >=2.0 | 深度学习后端（InceptionTime/ResNet/自定义模型） | ~2GB（已有则不新增） |
| `scikit-learn` | >=1.3 | 交叉验证、指标计算 | 已有 |
| `numpy` / `pandas` | 已有 | 数据处理 | 已有 |

`aeon` 是 `sktime` 的社区分支/继承者，专注于时序分类/聚类/回归，维护更活跃、API 更干净。安装：`pip install aeon[dl]`（含深度学习支持）。

### 8.2 环境检查清单

- [ ] `conda activate cp_web && pip install aeon[dl]` 是否成功
- [ ] `python -c "from aeon.classification.convolution_based import MiniRocketClassifier"` 可导入
- [ ] `python -c "import torch; print(torch.cuda.is_available())"` 检查 GPU
- [ ] 若无 GPU：Tier 1 + Tier 2 仍可 CPU 跑（慢一些），Tier 3 建议跳过或迁移到服务器

## 九、实验计划（分阶段）

### Phase 1：验证假设（1-2 天）

- 只跑 Tier 1（MiniRocket / MultiRocket / ROCKET）+ ROCKET+RF 对照
- 窗口长度固定 288，stride=72
- 与 RF 路线在同一数据上对比 macro_f1
- **决策点**：时序路线 F1 > RF 路线 F1？差多少？

### Phase 2：深度模型探索（2-3 天）

- 仅在 Phase 1 结论为「时序有价值」时继续
- 跑 InceptionTime + ResNet
- 尝试 window_length=144/288/576 三组
- **决策点**：深度模型 > Tier 1 最佳？增幅值得 GPU 投入？

### Phase 3：精度上限 + 工程化（3-5 天）

- 跑 CNN-LSTM / CNN-BiLSTM-Attention
- 超参调优（学习率、dropout、kernel_sizes）
- 确定最终推荐模型
- 接入 production_path / fallback_path

## 十、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 窗口重叠导致 train/test 泄漏 | 精度虚高 | 按设备划分 + 同设备窗口不跨集 |
| 故障样本过少（<50 窗口） | 模型学不到 | 减小 stride 增加样本 + class_weight |
| aeon 装不上（依赖冲突） | 无法跑 Tier 1/2 | 退化为自实现 ROCKET（~100 行） |
| GPU 不可用 | Tier 3 跑不了 | 只用 Tier 1/2 结论做决策 |
| 时序路线不优于 RF | 投入浪费 | Phase 1 即判断，快速止损 |
| 窗口长度不合适 | 形态截断/稀释 | 多组窗口参数对比实验 |

## 十一、决策记录

| 编号 | 决策 | 理由 |
|------|------|------|
| D1 | 使用 `aeon-toolkit` 而非 `sktime` | aeon 是 sktime TSC 模块的继承者，维护更活跃，API 更统一 |
| D2 | 默认 window_length=288（1天） | 覆盖完整日变化周期，保证故障形态在窗口内完整呈现 |
| D3 | 默认 label_strategy="majority" | 简单可靠，与文献主流做法一致 |
| D4 | 按设备划分 train/test | 避免同设备相邻窗口跨集泄漏 |
| D5 | Tier 分级渐进投入 | 先验证假设再投入重型模型，避免沉没成本 |
| D6 | 自定义模型统一 sklearn 接口 | 与 aeon 兼容、便于 pipeline 编排 |
| D7 | 评估指标与 RF 路线完全对齐 | 公平对比的前提 |
| D8 | 模型产物持久化窗口配置 | 保证预测时切分策略与训练一致（需求 1 第 5 条） |
<!-- @AI_GENERATED: end -->
