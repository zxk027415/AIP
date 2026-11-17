<!-- @AI_GENERATED -->
# 实现任务：光伏时序故障诊断（pv-fault-timeseries-diagnosis）

> 任务按依赖顺序编排：先搞定环境依赖，再实现滑窗切分器，接着搭建多模型对比框架和训练 pipeline，最后跑实验验证并接入双路径对比。每项任务只做编码 + 该项测试，均可独立验证。所有代码遵守相对路径、`@AI_GENERATED` 标记约束。运行环境 conda `cp_web`。

## 阶段 0：环境准备与前置验证

- [ ] 1. 安装 `aeon` 库并验证导入
  - 在 conda `cp_web` 下 `pip install aeon[dl]`
  - 验证：`python -c "from aeon.classification.convolution_based import MiniRocketClassifier, MultiRocketClassifier, RocketClassifier; print('Tier1 OK')"`
  - 验证：`python -c "from aeon.classification.deep_learning import InceptionTimeClassifier, ResNetClassifier; print('Tier2 OK')"`
  - 检查 PyTorch/GPU：`python -c "import torch; print(f'torch={torch.__version__}, cuda={torch.cuda.is_available()}')"`
  - 若 aeon 依赖冲突导致装不上，记录冲突包并评估自实现 ROCKET 的成本（~100 行）
  - _需求: 待办 1, 待办 2_

- [ ] 2. 确认标签数据可读取
  - 验证 `point_labels` 表存在且有数据：`SELECT COUNT(*) FROM point_labels WHERE label_id IS NOT NULL`
  - 验证能按设备+时间范围查询逐点标签，输出 DataFrame[time, label_id]
  - 若 `point_labels` 表无数据（逐点标签 spec 尚未完成迁移），准备 fallback 方案：从现有 `training_samples.label` 列临时读取
  - 记录可用设备数、标注覆盖率、类别分布
  - _需求: 1.4, 3.1_

- [ ] 3. 窗口长度初值标定
  - 从真实数据中统计典型故障的持续时长（点数分布：p25/p50/p75/p95）
  - 确认 288（1天）/ 144（半天）/ 576（2天）三个候选 window_length 是否合理
  - 统计数据覆盖率：连续无 NaN 的最长序列长度分布（确认 288 点窗口能切出足够样本）
  - 记录结果到实验日志，作为后续实验的参数依据
  - _需求: 待办 4_

## 阶段 1：滑动窗口切分器

- [ ] 4. 实现 `SlidingWindowSampler` 核心类
  - 新建 `backend-service/services/iterative_labeling/tsc/__init__.py`
  - 新建 `backend-service/services/iterative_labeling/tsc/sliding_window_sampler.py`
  - 实现 `SlidingWindowSampler` 类：
    - `__init__(window_length, stride, min_coverage, label_strategy, purity_threshold, channels, daylight_only)`
    - `transform(device_timeseries: DataFrame, point_labels: DataFrame) -> Tuple[ndarray, ndarray, DataFrame]`
    - `_compute_majority(labels) -> Tuple[int, float]`：取众数 + 计算纯度
    - `get_config() -> dict`：返回当前配置（用于持久化）
  - 输入：设备时序 DataFrame + 逐点标签 DataFrame
  - 输出：X[n_samples, window_length, n_channels], y[n_samples], meta[n_samples]（含 sample_id, t_start, t_end, purity, device_id）
  - _需求: 1.1, 1.2, 1.3_

- [ ] 5. 实现标签聚合策略扩展
  - 在 `sliding_window_sampler.py` 中实现三种策略：
    - `majority`：取众数 + 纯度过滤（默认）
    - `fault_priority`：故障点数 ≥ 阈值（可配置，默认 window_length×0.1）即标为故障
    - `boundary_align`：窗口起点对齐标签变化边界，stride 在此模式下动态调整
  - 通过 `label_strategy` 参数选择
  - _需求: 1.3_

- [ ] 6. 实现多设备批量切分与类别不平衡处理
  - 新建 `backend-service/services/iterative_labeling/tsc/data_loader.py`
  - 实现 `load_and_split_all_devices(dataset_path, sampler_config) -> Tuple[X, y, meta]`：
    - 遍历所有设备，逐设备调用 SlidingWindowSampler
    - 对故障时段使用更小的 stride（`fault_stride_ratio`，默认 stride//6）实现窗口重叠过采样
    - 拼接所有设备的结果
    - 记录 class_distribution、n_discarded_windows、每设备样本数
  - 实现 `split_by_device(X, y, meta, test_ratio, random_state) -> (X_train, y_train, X_test, y_test)`：
    - 按设备 ID 划分 train/test（同设备窗口不跨集）
    - 保证测试集类别分布合理（StratifiedGroupSplit）
  - _需求: 1.1, 1.2_

- [ ] 7. `SlidingWindowSampler` 单元测试
  - 新建 `backend-service/tests/test_sliding_window_sampler.py`
  - 测试用例：
    - 基本切分：288 点序列切出正确数量的窗口
    - 跨天窗口：窗口可横跨自然日边界
    - 纯度过滤：混合标签窗口被正确丢弃
    - 覆盖率过滤：NaN 过多的窗口被丢弃
    - 多策略对比：majority vs fault_priority 输出不同
    - 空数据/全 NaN/全未标注的边界情况
    - 配置持久化：`get_config()` 返回完整配置
  - 在 conda `cp_web` 下 `pytest tests/test_sliding_window_sampler.py -v` 全部 PASSED
  - _需求: 1.1~1.5_

## 阶段 2：模型包装器与注册表

- [ ] 8. 实现 `TSCModelWrapper` 统一接口
  - 新建 `backend-service/services/iterative_labeling/tsc/model_wrapper.py`
  - `TSCModelWrapper` 类：
    - `__init__(model_name: str, **hyperparams)`
    - `fit(X, y) -> self`：训练，记录 `train_time_sec`
    - `predict(X) -> ndarray`：预测类别
    - `predict_proba(X) -> ndarray`：预测概率
    - `save(path: str)`：持久化模型 + window_config（metadata.json + model.pkl/.pt）
    - `load(path: str) -> TSCModelWrapper`：类方法加载
    - `get_metadata() -> dict`：返回模型名、训练时间、参数、窗口配置
  - aeon 模型（Tier 1/2）：直接包装，转换 X 形状为 aeon 要求的 `[n_samples, n_channels, window_length]`
  - 自定义模型（Tier 3）：通过 PyTorch Module 包装
  - _需求: 1.5, 2.1_

- [ ] 9. 实现模型注册表 `MODEL_REGISTRY`
  - 新建 `backend-service/services/iterative_labeling/tsc/model_registry.py`
  - 注册 8 个模型：minirocket / multirocket / rocket / inceptiontime / resnet / cnn_lstm / cnn_bilstm_attention / rocket_rf
  - 每个条目含：class 路径、tier、gpu_required、default_params、description
  - 提供 `get_model(name, **override_params) -> TSCModelWrapper` 工厂函数
  - 提供 `list_models(tier_filter=None, gpu_available=None) -> list[dict]` 查询函数
  - _需求: 2.1_

- [ ] 10. 实现 Tier 3 自定义模型：CNN-LSTM
  - 新建 `backend-service/services/iterative_labeling/tsc/custom_models/__init__.py`
  - 新建 `backend-service/services/iterative_labeling/tsc/custom_models/cnn_lstm.py`
  - PyTorch 实现：Conv1D×2 + BN + ReLU + MaxPool + LSTM + Dense + Softmax
  - 实现 sklearn 兼容接口（fit/predict/predict_proba）
  - 支持 class_weight（按类频率反比加权 CrossEntropyLoss）
  - 支持 early stopping（patience=10）
  - _需求: 2.1_

- [ ] 11. 实现 Tier 3 自定义模型：CNN-BiLSTM-Attention
  - 新建 `backend-service/services/iterative_labeling/tsc/custom_models/cnn_bilstm_attention.py`
  - PyTorch 实现：4 分支多尺度 Conv1D（kernel=3/7/15/31） + MultiHeadAttention 融合 + BiLSTM + TemporalAttention + Dense + Softmax
  - 同样支持 class_weight 和 early stopping
  - _需求: 2.1_

- [ ] 12. 实现两阶段对照模型：ROCKET + RF
  - 新建 `backend-service/services/iterative_labeling/tsc/custom_models/rocket_rf.py`
  - 实现：ROCKET Transform → StandardScaler → RandomForestClassifier(class_weight="balanced")
  - 复用 aeon 的 Rocket transform，只替换分类器为 sklearn RF
  - _需求: 2.1, 2.2_

- [ ] 13. 模型包装器与注册表单元测试
  - 新建 `backend-service/tests/test_tsc_model_wrapper.py`
  - 用合成数据（随机生成 [100, 64, 1] 的 X + 3 类标签）测试：
    - 所有 Tier 1 模型 fit/predict 正常
    - save/load 后预测结果一致
    - metadata 含完整窗口配置
    - 注册表工厂函数正确实例化
  - Tier 2/3 模型只做冒烟测试（1 epoch，验证不报错）
  - _需求: 1.5, 2.1_

## 阶段 3：训练评估 Pipeline

- [ ] 14. 实现 `TSCPipeline` 训练评估主流程
  - 新建 `backend-service/services/iterative_labeling/tsc/tsc_pipeline.py`
  - `TSCPipeline` 类：
    - `__init__(sampler_config, model_name, preprocess_config, cv_config)`
    - `run(dataset_path) -> dict`：完整流程（加载→切分→预处理→交叉验证→输出指标）
    - 预处理：NaN 线性插值 + per-sample z-score 归一化
    - 交叉验证：`RepeatedStratifiedKFold(n_splits=5, n_repeats=n_repeats)`，按设备分组
    - 输出指标格式与 `split_mode_compare.py` 对齐：`macro_f1_mean/std, accuracy_mean/std, macro_precision_mean, macro_recall_mean, n_samples, n_classes`
    - 额外输出：`per_class_f1, confusion_matrix, train_time_sec, predict_time_sec, model_size_mb, window_length, stride, n_discarded_windows`
  - _需求: 2.2_

- [ ] 15. 实现多模型对比运行器 `run_model_comparison`
  - 新建 `backend-service/services/iterative_labeling/tsc/tsc_model_compare.py`
  - `run_model_comparison(dataset_path, window_configs, model_names, n_repeats, test_ratio, random_state, tier_filter) -> dict`
  - 串行跑每个 (model, window_config) 组合
  - 过程写入 status.json（参考 `split_mode_compare.py` 的进度上报模式）
  - 结果写入 `backend-service/data/tsc_experiments/{experiment_id}/results.json`
  - 自动生成 ranking（by_f1 / by_accuracy / by_efficiency）
  - 输出 best_model + best_window_length 推荐
  - _需求: 2.1, 2.2, 2.3_

- [ ] 16. 实现异步任务入口（后台跑对比实验）
  - 新建 `backend-service/services/iterative_labeling/tsc/tsc_compare_job.py`
  - `start_tsc_compare_job(slot, dataset_path, model_names, window_configs, ...) -> job_id`
  - 后台线程执行，状态写入 `data/tsc_experiments/{slot}/status.json`
  - 提供 `load_tsc_compare_status(slot) -> dict` 和 `load_tsc_compare_result(slot) -> dict`
  - 接口设计参考 `split_mode_compare.py` 的 `start_compare_job` / `load_compare_status`
  - _需求: 2.2, 3.3_

- [ ] 17. Pipeline 单元测试
  - 新建 `backend-service/tests/test_tsc_pipeline.py`
  - 用合成数据验证：
    - 完整 pipeline 跑通（切分→训练→评估→输出指标）
    - 输出字段与 split_mode_compare 格式一致
    - 多模型对比输出 ranking 正确
    - 按设备划分不泄漏（同设备窗口不跨 train/test）
  - _需求: 2.2, 3.3_

## 阶段 4：与逐点标签 spec 集成

- [ ] 18. 对接 `split_mode_compare.py` 对比框架
  - 在 `tsc_model_compare.py` 确保输出格式完全兼容 `split_mode_compare` 的 `results` 结构
  - 或在 `split_mode_compare.py` 的 `DEFAULT_COMPARE_MODES` / `MODE_LABELS` 中注册 TSC 模式（如 `tsc_multirocket`）
  - 使前端对比页可以把 RF 路线和 TSC 路线的结果放在同一张表里对比
  - _需求: 3.3_

- [ ] 19. 实现 `production_path` / `fallback_path` 双指针配置
  - 扩展现有生产路径管理（若已在逐点标签 spec 中实现则直接复用）
  - 确保时序路线的最佳模型可作为 `fallback_path` 注册
  - 切换条件：`macro_f1` 差 ≥ 2% 且至少 3 次验证一致
  - _需求: 3.4, 2.4_

- [ ] 20. 预测侧集成
  - 新建 `backend-service/services/iterative_labeling/tsc/tsc_predictor.py`
  - `TSCPredictor` 类：
    - `__init__(model_path: str)`：从持久化文件加载模型 + 窗口配置
    - `predict_device(device_timeseries: DataFrame) -> dict`：取最近 window_length 个点，返回 `{label, confidence, window_start, window_end}`
    - `predict_device_multi_window(device_timeseries, stride) -> dict`：多窗口投票/平均概率
  - 保证预测使用与训练完全相同的 window_length / channels / normalization
  - _需求: 1.5, 2.4_

## 阶段 5：前端接入

- [ ] 21. 后端 TSC 对比 API 端点
  - 在 `backend-service/api/iterative_labeling.py` 新增 4 个端点：
    - `POST /api/iterative-labeling/tsc/compare` — 启动 TSC 多模型对比实验（异步，返回 job_id）
    - `GET /api/iterative-labeling/tsc/compare/status` — 轮询实验进度（进行中/已完成/失败）
    - `GET /api/iterative-labeling/tsc/compare/result` — 获取实验结果（含 ranking、best_model）
    - `GET /api/iterative-labeling/tsc/models` — 列出可用 TSC 模型及其 tier/GPU 要求
  - 端点内部调用 `tsc_compare_job.py` 的 `start_tsc_compare_job` / `load_tsc_compare_status` / `load_tsc_compare_result`
  - _需求: 3.3_

- [ ] 22. 前端 API 层：新增 `tscExperimentApi`
  - 在 `frontend-sevice/src/services/iterativeLabelingApi.ts` 新增 `tscExperimentApi` 对象：
    - `startTscCompare(body, slot)` — 启动对比
    - `getTscCompareStatus(slot)` — 轮询状态
    - `getTscCompareResult(slot)` — 获取结果
    - `listModels(slot)` — 获取模型列表
  - _需求: 3.3_

- [ ] 23. 前端组件：`ModelCompareTab`
  - 新建 `frontend-sevice/src/components/pv-fault/ModelCompareTab.tsx`
  - 功能：
    - 精度对比表（Ant Design Table）：模型名、macro_F1、accuracy、训练耗时、状态 Tag
    - 高亮最佳模型行
    - 若 TSC 最佳 > RF 最佳 + 2%，顶部 Alert 建议切换
    - 「▶ 启动对比」按钮 → 配置弹窗（模型选择 CheckboxGroup、窗口参数、Tier 筛选）
    - 实验进行中时展示进度条（定时轮询 status）
  - 复用 `PvFaultWorkspaceShell` 主题
  - _需求: 2.2, 3.3_

- [ ] 24. 前端组件：`ModelPathManager`
  - 新建 `frontend-sevice/src/components/pv-fault/ModelPathManager.tsx`
  - 功能：
    - 展示当前 production_path 和 fallback_path（调用已有 `getModelingPaths`）
    - 「设为生产路径」按钮 → 二次确认弹窗（显示精度对比 + 风险提示）
    - 「切换到备用路径」按钮 → 输入 reason → 调用 `switchModelingFallback`
    - 切换记录展示（若后端提供）
  - _需求: 3.4, 2.4_

- [ ] 25. 前端组件：`TscExperimentDetail`
  - 新建 `frontend-sevice/src/components/pv-fault/TscExperimentDetail.tsx`
  - 功能：
    - 折叠面板展示 TSC 实验详情
    - 窗口参数展示（window_length、stride、样本量、丢弃窗口数）
    - 类别分布柱状图（ECharts）
    - 混淆矩阵热力图（ECharts heatmap）
    - per_class_f1 雷达图或柱状图
  - _需求: 2.2_

- [ ] 26. 前端组件：`ConfusionMatrixChart`
  - 新建 `frontend-sevice/src/components/pv-fault/ConfusionMatrixChart.tsx`
  - ECharts heatmap 封装：接收 `{ matrix: number[][], labels: string[] }`，渲染带数值标注的混淆矩阵
  - 支持归一化（按行/按列/原始计数）切换
  - _需求: 2.2_

- [ ] 27. 集成到 `IterativeLabelingListPage`
  - 在 `IterativeLabelingListPage.tsx` 的 Tabs 中新增「模型对比」TabPane
  - 引入 `ModelCompareTab` 组件
  - Tab 切换时按需加载数据（不影响其他 Tab 性能）
  - _需求: 3.3_

- [ ] 28. 前端构建验证
  - `cd frontend-sevice && npm run build` 通过
  - 确认无 TypeScript 类型错误
  - 确认新组件不影响现有页面（IterativeLabelingListPage 其他 Tab 正常）
  - _需求: 3.2_

## 阶段 6：实验执行与验证

- [ ] 29. Phase 1 实验：Tier 1 模型 vs RF 路线
  - 用真实数据跑 MiniRocket / MultiRocket / ROCKET / ROCKET+RF 四个模型
  - 窗口参数：window_length=288, stride=72
  - 评估参数：n_repeats=5, test_ratio=0.2, random_state=90
  - 对比 RF 路线（`split_mode_compare` 最新结果）的 macro_f1
  - **决策点**：若 Tier 1 最佳 F1 > RF F1 + 2%，继续 Phase 2；否则结论为「时序形态对该数据帮助有限」
  - 记录完整实验结果到 `data/tsc_experiments/phase1/results.json`
  - _需求: 2.1, 2.2, 2.3_

- [ ] 30. Phase 2 实验：Tier 2 深度模型 + 多窗口参数
  - 仅在 Phase 1 结论为"时序有价值"时执行
  - 跑 InceptionTime + ResNet，window_length=144/288/576 三组
  - 对比 Tier 1 最佳结果
  - **决策点**：深度模型增幅 > 2% 且训练时间可接受？
  - _需求: 2.1, 2.3_

- [ ] 31. Phase 3 实验：Tier 3 精度上限（可选）
  - 仅在 Phase 2 有增益 + GPU 可用时执行
  - 跑 CNN-LSTM / CNN-BiLSTM-Attention
  - 超参搜索（学习率、dropout、kernel_sizes）
  - 确定最终推荐模型
  - _需求: 2.1, 2.3_

- [ ] 32. 最终模型持久化与部署配置
  - 将最优模型（含 metadata）存入 `data/tsc_experiments/production/`
  - 注册为 `fallback_path`（或 `production_path` 如果优于 RF）
  - 编写部署说明：模型文件路径、推理所需环境、预测接口调用方式
  - _需求: 1.5, 2.4, 3.4_

## 阶段 7：文档与收尾

- [ ] 33. 实验报告
  - 汇总 Phase 1/2/3 结果为结构化报告
  - 内容：各模型精度排名表、窗口参数对比表、训练时间/模型大小对比、与 RF 路线精度差异
  - 结论：推荐模型 + 推荐窗口参数 + 是否切换生产路径
  - 存入 `data/tsc_experiments/experiment_report.json`

- [ ] 34. 端到端冒烟验证
  - 从数据加载 → 滑窗切分 → 训练 → 评估 → 持久化 → 加载预测，全流程跑通
  - 验证预测结果与训练指标一致（无 train/predict 不一致 bug）
  - 验证模型 load 后 predict 输出与 save 前一致
<!-- @AI_GENERATED: end -->
