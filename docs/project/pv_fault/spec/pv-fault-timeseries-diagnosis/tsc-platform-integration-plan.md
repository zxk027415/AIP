<!-- @AI_GENERATED -->
# TSC 时序分类诊断 — 平台接入方案（定稿）

> 状态：**方案定稿**，2026-09-01
>
> 目标：把 TSC（MultiRocket 时序分类）作为第三条 `modeling_path` 接入平台，与"天"（`legacy_day`）和"点"（`seq_annotation`）完全并列——相同的工作流骨架、相同的累计训练闭环、相同的滚动检测 → 打标 → 回流链路。
>
> 前置：TSC 模型选型已完成（MultiRocket，macro F1 = 0.6162±0.0710，严格三隔离 10 折），代码在 `services/iterative_labeling/tsc/`，有 97 个测试。本文档只讲**接入**，不重复选型结论。

---

## 设计决策（已确认）

| # | 问题 | 决定 | 理由 |
|---|---|---|---|
| D1 | slot 选择 | **独立 `pv_tsc`** | 隔离更彻底，前端按 slot 切换即可；标签数据通过导入/共享标签池跨 slot 复用 |
| D2 | 游标初始化 | **从当前水位开始（只检测新数据）** | TSC 先以 challenger 跑，目的是验证链路；历史回补通过 BackfillRunner 按需进行 |
| D3 | 初始角色 | **challenger，不动 production_path** | 跑一段时间确认稳定后再人工 promote |
| D4 | Shadow 跨路径对比 | **本轮跳过** | 先跑通检测→打标→回流闭环，Shadow 后续扩展 |
| D5 | 实施节奏 | **后端+前端一起做** | 在设计中一次考虑完整 |

---

## 一句话总结

TSC 路径的产出粒度是**设备日**（和天路径一样），区别在于"怎么从一天数据得到诊断标签"：

| | 天路径 `legacy_day` | 点路径 `seq_annotation` | **TSC 路径 `tsc`** |
|---|---|---|---|
| slot | `pv_day` | `pv_point` | **`pv_tsc`** |
| 输入 | 一天时序 → 聚合统计特征向量 | 一天时序 → 288 点网格 | 一天时序 → 288 点滑动窗口切片 |
| 模型 | RandomForest | BiLSTM+Attention | **MultiRocket** |
| 输出粒度 | 设备日 1 标签 | 逐点 288 标签 | **设备日 1 标签**（多窗口投票） |
| 窗口参数 | 无 | seq_len=288 | **window=288, stride=72** |
| 288 点的含义 | 不用（聚合成统计特征） | 逐点标注（每点一个 label） | **整窗分类**（288 点→1 个 label，滑动多窗投票） |
| 训练耗时 | 秒级 | 分钟级 | **秒~分钟级，无 GPU** |

因为 TSC 的最终产出是设备日级别，它的调度策略、游标语义、审核批次结构**都和天路径保持一致**，不需要像点路径那样引入 `SeqDeviceDayLedger` 或 `replay_activity`。

三条路径各自独立 slot（`pv_day` / `pv_point` / `pv_tsc`），模式完全一致：
- `CumulativeTrainingService(slot="pv_tsc")` 独立实例，有自己的 `state.json`
- 工作流模板的 `metadata.slot = "pv_tsc"`
- 前端通过 `?slot=pv_tsc` 访问
- `device_prediction_cursor` 表中 `slot="pv_tsc"` 的行和 `pv_day` / `pv_point` 完全隔离
- 标签数据通过导入端点 `POST /cumulative-training/imports` 从共享标签池导入

---

## 改动总览

### 哪些改、哪些不改

| 层 | 要改 | 不改 |
|---|---|---|
| 路径白名单 | 6 处加入 `"tsc"` | — |
| 累计训练 | `_create_snapshot` 新增 `tsc` 分支（滑窗切分→NPZ） | 准入逻辑不变 |
| 调度策略 | 新建 `TscDailyStrategy` | `DualPathScheduler` 主框架不改，只加注册 |
| 工作流模板 | 新建 3 个 JSON（train_eval / predict / label） | 算子 backend 不改 |
| 任务注册 | `pv_fault_tasks.py` 加 TSC 定时任务 | 天/点的定时任务不改 |
| API | `available_paths` 自动含 tsc；`/run` 加 tsc 训练分支 | 端点签名不改 |
| 前端 | 新增 TSC 页面/Tab，复用组件 | 天/点的页面不改 |
| PVModelRegistry | 白名单已含 tsc | 数据结构不改 |
| DB | 新增 `slot="pv_tsc"` 的游标行 | 表结构不改 |
| 配置 | 新建 `config/pv_tsc.yaml` | `pv_dual_path.yaml` 不改 |

### 不碰的红线

- 不改 `pv_fault` 遗产只读策略
- 不动天/点路径的任何已有行为
- 不引入新数据库表
- 不碰 `SeqDeviceDayLedger`（点路径专用）
- 不改 Shadow 对比逻辑

---

## 详细设计

### 1. 路径白名单（Phase 0）— ✅ 已完成

7 个文件的白名单常量中已加入 `"tsc"`。

### 2. 累计训练快照（Phase 1）— ✅ 已完成

`_create_snapshot_tsc(state)` 已实现：
```
SlidingWindowSampler(window=288, stride=72, channels=[value,i_cal], min_std=1e-6)
→ load_and_split_all_devices（含故障过采样）
→ preprocess_X(method="per_sample_zscore")
→ NPZ（X + y + sample_ids）+ meta.csv
```

### 3. TSC 调度策略 — `TscDailyStrategy`

`services/scheduler/pv_dual_path/tsc_strategy.py`

```
run_cycle(ctx):
  1. 加载 TSCPredictor（champion_model_ref → 模型目录）
  2. 读 slot="pv_tsc", modeling_path="tsc" 的游标
  3. 按设备取 (cursor, watermark] 有效点
  4. 按自然日分组
  5. 每设备日 → predict_device_multi_window → 多窗口投票 → (label, confidence)
  6. 写 prediction_records + batch JSON + review_session
  7. 推进游标
  8. 返回 CycleResult
```

游标语义和天路径一致（`event_time_watermark`），不用 Ledger。`prediction_granularity = "day"`。

### 4. 工作流模板

#### `workflow-pv-tsc-train-eval-v1.json`
```
slot: "pv_tsc"
template_role: "train_eval"

DAG:
  load_csv（累积标签数据 parquet）
  → tsc_sliding_window_split（SlidingWindowSampler 切窗）
  → tsc_train_eval（MultiRocket fit + strict 10-fold 评估）
  → 产出: 模型工件（model.pkl + metadata.json）+ evaluation_report
```

#### `workflow-pv-tsc-predict-v1.json`
```
slot: "pv_tsc"
template_role: "predict"

DAG:
  load_csv（待预测设备日数据）
  → tsc_predict（加载 MultiRocket → predict_device_multi_window → 日级标签）
```

#### `workflow-pv-tsc-label-v1.json`
```
slot: "pv_tsc"
template_role: "labeling"

DAG:
  load_csv → merge_label → 标签分发（结构与天路径 label 模板一致）
```

### 5. 任务注册与调度

由于 `pv_tsc` 是独立 slot，需要独立的定时任务入口（不是塞进 `pv_fault` 的 `DualPathScheduler`）：

```python
# pv_fault_tasks.py 或新建 pv_tsc_tasks.py

def make_pv_tsc_prediction_task(pv_repo):
    def pv_tsc_prediction_task():
        scheduler = DualPathScheduler(
            strategies={"tsc": TscDailyStrategy(pv_repo)}
        )
        scheduler.dispatch(slot="pv_tsc")
    return pv_tsc_prediction_task
```

对应的 `CumulativeTrainingService(slot="pv_tsc")` 实例在 API 层通过 `_cumulative_training_for_slot("pv_tsc")` 惰性创建。

### 6. 游标初始化（Lazy）

`TscDailyStrategy.run_cycle` 首次执行发现 `device_prediction_cursor` 中无 `slot="pv_tsc"` 的行时：

1. 从 `DataWatermarkService` 读取全部设备的当前水位
2. 为每台设备创建 `(slot="pv_tsc", modeling_path="tsc", site_id, device_id, branch_id)` 行
3. `last_predicted_time` 设为**当前水位时间**（= 只检测新数据；历史数据不回溯）
4. 首轮结束后，后续轮次正常走 `(cursor, watermark]` 增量

### 7. 后端 API

| 端点 | 改动说明 |
|---|---|
| `GET /cumulative-training/state?slot=pv_tsc` | 无需改；`_cumulative_training_for_slot` 自动按 slot 创建实例 |
| `POST /cumulative-training/imports?slot=pv_tsc` | 无需改；登记带标签数据集到 `pv_tsc` 的累计训练集 |
| `GET /cumulative-training/modeling-paths?slot=pv_tsc` | 无需改；返回 `pv_tsc` 的 path_models |
| `POST /cumulative-training/retrain?slot=pv_tsc` | 需要加 `tsc` 训练分支：构建快照 → 训练 MultiRocket → 登记 Challenger |
| `POST .../challengers?slot=pv_tsc` | 无需改 |
| `POST .../promote?slot=pv_tsc` | 无需改 |
| TSC 实验端点 `/tsc/compare?slot=pv_tsc` | 无需改（已有） |

重训分支的核心逻辑：
```python
if target_modeling_path == "tsc":
    snapshot = svc._create_snapshot_tsc(state)
    # 用 tsc_pipeline 训练 MultiRocket
    from services.iterative_labeling.tsc.tsc_pipeline import train_and_evaluate
    result = train_and_evaluate(
        dataset_path=snapshot["dataset_path"],
        model_name="multirocket",
        window_config=snapshot["sample_strategy"],
    )
    # 持久化模型到 data/models/tsc/{model_id}/
    # register_challenger 到 PVModelRegistry(slot="pv_tsc")
```

### 8. 前端设计

#### 8.1 路由

在 `App.tsx` 中新增 route：
```tsx
<Route path="/pv-tsc" element={<PvTscPage />} />
```

或者复用现有 `IterativeLabelingListPage`，通过 URL 参数 `?slot=pv_tsc&tab=tsc` 切换。

**推荐方案**：在 `IterativeLabelingListPage` 中新增 `slot` 切换器（顶部 Segmented 或 Tabs），用户选择 `pv_tsc` 后展示 TSC 相关的 Tab 组。这样不需要新建独立页面，复用现有布局。

#### 8.2 Tab 结构（slot=pv_tsc 时）

```
┌──────────────────────────────────────────────────────┐
│  [pv_fault ▾]  ← slot 选择器（Segmented）            │
│   ├─ pv_fault（天/点路径）                            │
│   └─ pv_tsc（时序分类诊断）← 新增                     │
├──────────────────────────────────────────────────────┤
│  Tab: 检测状态 | 模型管理 | 人工打标 | 累计训练         │
│                                                       │
│  ┌─ 检测状态 ─────────────────────────────────────┐   │
│  │ TSC 检测运行状态卡片                            │   │
│  │  - 上次运行时间 / 状态 / 检测设备数 / 批次数     │   │
│  │  - 游标进度（最新/最旧设备水位）                 │   │
│  │  - 最近 10 个预测批次列表                        │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌─ 模型管理 ─────────────────────────────────────┐   │
│  │ 复用 ModelPathManager（slot=pv_tsc）            │   │
│  │  - Champion / Challengers / Retired             │   │
│  │  - 训练按钮 → 触发重训                          │   │
│  │  - Promote 按钮 → 晋升                          │   │
│  │                                                 │   │
│  │ 复用 ModelCompareTab（slot=pv_tsc）             │   │
│  │  - TSC 多模型对比实验                           │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌─ 人工打标 ─────────────────────────────────────┐   │
│  │ 复用现有审核队列组件（slot=pv_tsc）              │   │
│  │  - 展示 TSC 检测产出的审核会话                   │   │
│  │  - 操作界面和 pv_fault 的打标一致                │   │
│  └────────────────────────────────────────────────┘   │
│                                                       │
│  ┌─ 累计训练 ─────────────────────────────────────┐   │
│  │ 复用 CumulativeTrainingLedger（slot=pv_tsc）    │   │
│  │  - 快照列表 / 导入数据集列表                     │   │
│  │  - 手动触发快照构建                              │   │
│  │  - 重训请求队列                                  │   │
│  └────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────┘
```

#### 8.3 新增/修改的前端文件

| 文件 | 职责 | 新建/修改 |
|---|---|---|
| `IterativeLabelingListPage.tsx` | 顶部加 slot 选择器（pv_fault / pv_tsc） | 修改 |
| `TscDetectionStatusCard.tsx` | TSC 检测运行状态卡片 | 新建 |
| `TscTrainingPanel.tsx` | TSC 训练触发面板（构建快照→训练→注册） | 新建 |
| `ModelCompareTab.tsx` | 已有，无需改（slot 参数传入即可） | 不改 |
| `ModelPathManager.tsx` | 已有，无需改（slot 参数传入即可） | 不改 |
| `iterativeLabelingApi.ts` | 确认 API 调用传 slot 参数 | 检查 |

#### 8.4 配置

新建 `backend-service/config/pv_tsc.yaml`：与 `pv_dual_path.yaml` 类似的配置结构，但只需 TSC 路径相关的配置项。

---

## 完整链路走读

```
  标签数据源（point_labels / labeled parquet）
       │
       │  POST /cumulative-training/imports?slot=pv_tsc
       ▼
  CumulativeTrainingService(slot="pv_tsc")
       │
       │  _create_snapshot_tsc
       ▼
  TSC NPZ 快照（X[n,288,2] + y[n] + meta）
       │
       │  POST /cumulative-training/retrain?slot=pv_tsc&modeling_path=tsc
       ▼
  MultiRocket 训练 → 模型工件（model.pkl + metadata.json）
       │
       │  register_challenger(slot="pv_tsc", modeling_path="tsc")
       ▼
  PVModelRegistry(slot="pv_tsc").path_models["tsc"].challengers
       │
       │  人工 promote（确认稳定后）
       ▼
  PVModelRegistry(slot="pv_tsc").path_models["tsc"].champion
       │
       │  定时任务 → DualPathScheduler.dispatch(slot="pv_tsc")
       ▼
  TscDailyStrategy.run_cycle
       │  读游标 → 取增量数据 → 按设备日分组
       │  → predict_device_multi_window → 多窗口投票
       ▼
  prediction_records（slot="pv_tsc", modeling_path="tsc"）
  prediction_batch JSON
  review_session
       │
       │  人工打标（前端审核队列）
       ▼
  确认标签 → admit 到累计训练集 → 快照 +1 → 重训 → 循环
```

---

## 实施清单

| # | Phase | 涉及文件 | 状态 |
|---|---|---|---|
| 0 | 路径白名单 | 7 个 `_ALLOWED_*` | ✅ 已完成 |
| 1 | TSC 快照 | `cumulative_training.py` | ✅ 已完成 |
| 2 | TSC 调度策略 | `tsc_strategy.py`（新建） | ⚠️ 初版已写，需 review |
| 3 | 工作流模板 | `workflow-pv-tsc-*.json`（×3） | ❌ |
| 4 | 任务注册 | `pv_fault_tasks.py` 或新 `pv_tsc_tasks.py` | ❌ |
| 5 | 后端 API | `iterative_labeling.py`（retrain 分支） | ❌ |
| 6 | 配置 | `config/pv_tsc.yaml` | ❌ |
| 7 | 前端 slot 选择器 | `IterativeLabelingListPage.tsx` | ❌ |
| 8 | 前端 TSC 卡片 | `TscDetectionStatusCard.tsx`（新建） | ❌ |
| 9 | 前端 TSC 训练面板 | `TscTrainingPanel.tsx`（新建） | ❌ |
| 10 | 构建验证 | py_compile + npm run build | ❌ |

---

## 风险与遗留

| # | 风险 | 缓解 |
|---|---|---|
| 1 | TSC 训练需要 `aeon` 库 | `pip install aeon` 无 GPU 依赖，`cp_web` 下一次安装 |
| 2 | 独立 slot 需要手动导入标签数据到 `pv_tsc` | 通过 `POST /cumulative-training/imports` 导入同一份 parquet |
| 3 | TSC macro F1 = 0.62 低于天路径 RF | 先以 challenger 跑，不影响生产 |
| 4 | 游标初始化时设备列表可能与 `pv_fault` 不同步 | lazy 初始化从水位服务读全量设备 |
| 5 | Shadow 对比暂不支持 TSC | 先积累数据，后续扩展 |
<!-- @AI_GENERATED: end -->
