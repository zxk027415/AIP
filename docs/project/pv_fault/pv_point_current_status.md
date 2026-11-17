<!-- @AI_GENERATED -->
# 光伏点路径（pv_point）现状：从数据到前端的完整故事线

> 记录日期：2026-09-01
> 用途：下一会话 replay 管道对齐的上下文。基于代码实际读取，不是设计文档。

---

## 一句话现状

点路径从数据采样、模型训练、模型推理到前端精度展示的**技术组件全部存在**，但它们**没有按设计串成一条线**——loop_demo 的点路径实际走的是「按天批灌 + 一次性全检测」，不是「replay_activity 逐点推进 + 因果窗口 + 告警状态机」。replay_activity 和告警状态机都已实现并有单测，但在演示流程中是死代码。

---

## 1. 数据：从哪来、长什么样

### 1.1 Gold 真值数据

| 项 | 值 |
|---|---|
| 路径 | `data/slot_datasets/pv_point/gold/point-poc-k4-labeled.parquet` |
| 行数 | 92,388 |
| 列 | `time`（UTC datetime）、`site_id`、`device_id`、`branch_id`、`value`、`i_cal`、`label`（float，含 NaN）、`source` |
| 设备数 | 297 台（大部分只有 1-2 天数据） |
| 标签分布 | {0: 78507, 1: 2137, 3: 3394, 7: 3899, 11: 332, 12: 952, 6: 62, 8: 50} |
| 时间范围 | 分散在 2021-08、2021-10、2022-01 等多个时段 |

来源：从 `data/realtime_point_poc/snapshots/point-poc-20260821044728-684bf7f6` 的测量数据 + K4 聚类标注合并而来（`gold_bootstrap.py`）。

### 1.2 Realistic Mock 数据（当前会话新建）

`realistic_mock_builder.py` 从 gold 中按设备覆盖度采样，写入 `data/slot_datasets/pv_point/loop_demo/`：

| 文件 | 说明 |
|---|---|
| `unlabeled.parquet` | 去掉 label 列，用于喂数 |
| `mock_truth.parquet` / `gold.parquet` | 带 label，用于自动审核比对 |
| `manifest.json` | 采样元信息：设备列表、日期列表、标签分布、label_names 映射 |
| `feed_cursor.json` | 喂数游标：哪些天已喂、下一天是哪天 |

当前 v2 采样参数：8 台设备（优先选多天+多类设备），按设备覆盖密度选 7 天。实际采出 3432 行，4 类标签（0/1/3/7），16 个故障设备-日。

### 1.3 数据稀疏问题

pv_point gold 的设备天然稀疏：297 台设备中最多的也只有 5 天数据，大部分 1 天。采样 8 台后在 7 天窗口内，某些天会有 0 条到达（比如 2021-08-26 所有 8 台都没数据）。这是真实数据的自然特征，不是 bug。

---

## 2. 模型：TCN 怎么训、长什么样

### 2.1 架构

`CausalTCNRealtime`（`services/iterative_labeling/realtime_point/model.py`）：

- 严格因果时序卷积网络。输入 `[B, W, C]`，输出 `[B, W, K]`（每个时间步的类别 logits）
- 7 个输入通道：`value, i_cal, is_measured, time_since_measured, tod_sin, tod_cos, is_daylight`
- 默认超参：hidden_channels=32, kernel_size=3, dilations=(1,2,4,8), dropout=0.1
- 感受野：61 个点（约 5 小时的 5 分钟数据）
- 3 类输出：class_index_to_label = [0, 1, 2]

### 2.2 训练

`RealtimePointTrainer.train()`（`services/iterative_labeling/realtime_point/trainer.py`）：

- 加载数据集 → `FixedRobustScaler` 归一化（per-channel median/IQR）→ temporal split → balanced class weights → CrossEntropyLoss + AdamW + CosineAnnealingLR → early stopping
- target_mode = `last_point`（只监督窗口最后一个时间步）
- 因果审计：训练前后检查无未来信息泄漏
- 产出：`metadata.json` + `model.pt`（state_dict + scaler state + label mapping）

### 2.3 已注册模型

`data/slot_governance/pv_point/model_candidates.json`：

| ID | artifact | 来源执行 |
|---|---|---|
| mc-8c103f4d30cf | rtpoint-tcn-…-20260824093918-2a2e056e | exec-3e0a6201c505 |
| mc-c97422720b93 | rtpoint-tcn-…-20260824094039-31361f0e | exec-ae288472a36e |
| mc-061e1ed64284 | rtpoint-tcn-…-20260824094727-a4dbc573 | exec-5807a321946d |
| **mc-83ab32849bd6** | rtpoint-tcn-…-20260827073808-a3d1d118 | exec-befb1324bfc7 |

`data/slot_governance/pv_point/registry.json`：

- **champion = null**（没有晋升过）
- challenger = mc-061e1ed64284
- **rolling_detect_model = mc-83ab32849bd6**（当前检测实际使用的模型）

### 2.4 模型加载链路

```
resolve_slot_scheduler_model("pv_point")
  → champion null → rolling_detect_model mc-83ab32849bd6
  → artifact_ref = "backend-service/data/models/timeseries_point/rtpoint-tcn-last_point-20260827073808-a3d1d118"

_load_tcn_artifact(artifact_ref)
  → load_realtime_point_artifact(ref, device="cpu")
  → 验证 metadata.json 20+ 项契约
  → 加载 model.pt → CausalTCNRealtime + FixedRobustScaler
  → 返回 LoadedRealtimePointArtifact（.forward() 接受 raw [B,W,C] ndarray，内部归一化+推理）
```

---

## 3. 推理：两条完全独立的路

### 3.1 路径 A：loop_demo 按天批灌（当前实际走的）

```
用户点「推进下一天」(SchedulerTab)
  → POST /observability/advance-day {slot:"pv_point", use_real_model:true}
  → observability_ledger.advance_watermark_day
  → loop_demo.run_next_demo_day("pv_point", use_real_model=True)
     1. build_realistic_mock → 确保 mock 数据存在（幂等）
     2. feed_next_day → 按天从 unlabeled.parquet 切一天追加到 arrived.parquet
     3. _detect_chunk(use_real_model=True)
        → detect_point_with_tcn(chunk, gold)
        → 对 chunk 中每台设备的每个点，构建因果窗口，调 TCN forward
        → 返回 (outcomes, model_id)
     4. 写 outcomes.json（全量替换当天的点）
     5. _auto_review_session → 逐点比对 pred vs gold → AccuracyEvaluator → 建 rev-* 会话
     6. 写 daily_accuracy.json
     7. 写 observability_ledger（水位推进 + 设备检测标记）
```

**问题**：这条路把一天几百个点一次性全检测完，不是逐点推进。因果窗口是在 `detect_point_with_tcn` 内部自己按实体分组构建的，不走 `replay_activity` 的 session/cursor 机制。告警也是前端事后模拟（`computeAlarmEvents`），不是后端状态机触发。

### 3.2 路径 B：replay_activity 逐点推进（代码存在但没接入 loop_demo）

```
用户点「推 1 点 / 推 10 点 / 推 50 点」(SlotOpsClockBar)
  → POST /observability/replay-step {slot:"pv_point", points:1}
  → observability_ledger.replay_observatory_step
  → _ensure_replay_session（如果不存在则创建）
  → replay_activity.replay_next_point(session_id)
     1. _pick_next_source_index → earliest_event_time 跨设备选点
     2. 构建当前实体的因果窗口（committed_history + pending）
     3. 通过冻结 graph runner 调模型推理
     4. outcome + cursor 推进 + save session
```

**问题**：这条路的数据源是 `_ensure_replay_session` 从调度绑定（`_binding_for_slot`）加载的数据集，**不是 loop_demo 的 mock 数据**。两条路的数据源、session 管理、outcome 存储完全独立。

### 3.3 两条路的对比

| | 路径 A（loop_demo 批灌） | 路径 B（replay_activity 逐点） |
|---|---|---|
| 触发 | 「推进下一天」按钮 | 「推 N 点」按钮 |
| 数据源 | loop_demo/arrived.parquet | replay session 的 source_rows |
| 推进粒度 | 一天几百点一次性 | 一次一点（最多 50） |
| 因果窗口 | detect_point_with_tcn 内部自建 | replay_activity 从 committed_history 构建 |
| 模型调用 | _load_tcn_artifact → artifact.forward | 冻结 graph runner → ts_point_predict → predict_point_outcome |
| 跨设备交错 | ❌ 按实体分组顺序处理 | ✅ earliest_event_time 选最早点 |
| outcome 存储 | loop_demo/outcomes.json | replay session JSON 的 outcomes 数组 |
| 告警 | 前端 computeAlarmEvents 模拟 | 代码存在但没接（point_alarm_store.ingest_point_outcome） |
| 精度计算 | _auto_review_session + AccuracyEvaluator | 不算精度 |
| 前端展示 | PvPointAccuracyOpsPanel 读 outcomes.json | SlotOpsClockBar 显示 session 状态 |

---

## 4. 告警状态机：完整但断线

### 4.1 后端实现

`point_alarm_state_machine.py`：

```python
AlarmPolicy(
    open_consecutive_points=3,   # 连续 3 个故障点开告警
    close_consecutive_points=3,  # 连续 3 个正常点关告警
    fault_labels={1,3,6,7,8,11,12},
    normal_labels={0},
)

EntityAlarmState → 状态机：
  normal → suspected_open → active（alarm_open 事件）
  active → suspected_close → normal（alarm_close 事件）
  active + 相同标签 → alarm_dedupe
  active + 不同标签连续 N 个 → alarm_label_switch
```

`point_alarm_store.py`：

- `ingest_point_outcome(slot, outcome)` → 加载状态 → apply_point_outcome → 保存状态 + 追加事件
- `alarm_summary(slot)` → 活跃告警数、活跃告警列表、最近事件
- 存储位置：`data/timeseries_point/alarms/{slot}/entity_states.json` + `events.jsonl`

### 4.2 断线位置

- `loop_demo.run_next_demo_day` 不调 `ingest_point_outcome`
- `replay_activity.replay_next_point` 的 `_process_one_point` 也不调 `ingest_point_outcome`
- 前端 `PvPointAccuracyOpsPanel` 的告警数据来自 `deriveDemoAlarms()`（客户端模拟），不是后端 `GET /timeseries-replay/alarm-summary`

### 4.3 验证覆盖

- `test_g12_point_alarm_state_machine.py`：单测覆盖了 open/close/dedupe/label_switch/cold_start
- `g12_e2e_review_20260825165418.json`：6 步 e2e 全 passed（alarm open/close lifecycle、HTTP alarm_summary、pending_enqueue/summary、latest_predict_replay）
- 但这些测试是直接调后端函数，不经过 loop_demo

---

## 5. 观测台和日历

### 5.1 observability_ledger 对 pv_point 的处理

`observability_status("pv_point")` 返回：

```json
{
  "slot": "pv_point",
  "demo": true,
  "clock": {"kind": "event_time", "day": "2021-08-28", ...},
  "progress": {"day_index": 3, "total_days": 7, "fed_days": [...]},
  "window": {"from": "2021-08-23", "to": "2021-08-28"},
  "accuracy": {...},
  "replay": {
    "session_id": "sched-pv_point-default",
    "selection_policy": "earliest_event_time" 或 "legacy_entity_then_time",
    "legacy": true/false,
    "cursor": 37, "total": 100, "status": "running",
    "event_clock": "2021-08-23T09:35:00+00:00",
    "last_entity": "1e374992a6802000|rkVGXrr9|1"
  }
}
```

`replay` 字段是从 `sched-pv_point-default` session 读的。如果 session 不存在则返回 `{"empty": true}`。

### 5.2 日历

`SlotObservabilityCalendar` 对点路径：按天聚合显示到达点数和检测点数。但**点路径的日历格子没有 ready/waiting/skipped 状态**——天路径的 3 天闸门只在 `prepare_day_detect_batch("pv_day")` 里触发，点路径不走这个闸门。

### 5.3 设备到达看台

`replay_activity.session_entity_overview()` 能返回每台设备的 `source_points / replayed_points / last_source_time / last_replay_time`。但前端 `PvPointReplayEntityPanel` 被 `showPointReplay=false` 门控（`SchedulerTab.tsx` line 151），**从未渲染**。

---

## 6. 前端展示

### 6.1 精度运营面板（PvPointAccuracyOpsPanel）

数据来源：

| 数据 | API | 来源 |
|---|---|---|
| 检测结果曲线 | `GET /slot-datasets/observability/outcomes?slot=pv_point` | loop_demo/outcomes.json |
| 精度指标 | `GET /slot-datasets/mock-accuracy?slot=pv_point` | loop_demo/daily_accuracy.json |
| 观测状态 | `GET /slot-datasets/observability/status?slot=pv_point` | observability_ledger + replay session |
| 告警事件 | 前端 `deriveDemoAlarms()` 客户端计算 | 从 outcomes 序列推导 |

Acc 计算：前端在日历窗口内逐点比 `predicted_label == gold_label`。

### 6.2 调度页（SchedulerTab）

点路径区域：

- 水位条（`SlotOpsClockBar`）：当前事件时钟 / 演示进度 / Acc / 推进按钮
- Switch：「真实模型」/「规则」— 控制 `use_real_model` 参数
- 「推进下一天」→ 调 `advance-day`（走 loop_demo 路径 A）
- 「推 1/10/50 点」→ 调 `replay-step`（走 replay_activity 路径 B）
- 「重置演示游标」→ 调 `reset-demo`
- 「重建交错会话」→ 调 `rebuild-replay`（取消旧 session，新建 earliest_event_time）
- 日历（`SlotObservabilityCalendar`）：只读

### 6.3 标签名映射

后端 `outcomes_for_window` 返回 `label_names` 字段（从 manifest 或默认值）：
```json
{"0": "正常", "1": "组串失配", "3": "组串遮挡", "7": "热斑效应", "12": "组串断路", ...}
```

前端 tooltip、表格列、分布图、告警表都用 `labelName()` 做映射。

---

## 7. 什么已经通了、什么是断的

### ✅ 已通（当前可演示）

1. **Mock 数据采样 → 喂数 → 真实 TCN 推理 → 精度**：`build_realistic_mock` → `feed_next_day` → `detect_point_with_tcn` → `_auto_review_session` → 前端 Acc 卡 / 曲线 / 混淆矩阵。E2E 验证：3 天推进，TCN mc-83ab32849bd6，累计 Acc 53.8%。
2. **review session 和 accuracy 存储**：每推一天自动建 `rev-loop-demo-pv_point-*` 会话，写 `daily_accuracy.json`。不写入累计账本。
3. **前端标签名**：tooltip 显示「组串失配」而不是 `1`，表格列和分布图同理。
4. **replay_activity 跨设备交错选点**：`earliest_event_time` 策略已实现，有单测 `test_replay_picks_earliest_event_across_devices` 验证。
5. **告警状态机**：`apply_point_outcome` 有完整的 open/close/dedupe/label_switch 逻辑，有单测和 e2e review。
6. **3 天未到齐舍弃**（天路径）：`prepare_day_detect_batch` + `_expire_waiting_cells` 已实现+测试。

### ❌ 断线（代码存在但没串起来）

1. **loop_demo 点路径不走 replay_activity**：按天批灌，不逐点推进，因果窗口在 `detect_point_with_tcn` 内部自建。
2. **告警状态机不被调用**：`ingest_point_outcome` 在演示流程中没有调用方。前端告警是客户端模拟。
3. **「推 N 点」走的是独立 replay session**，数据源不是 loop_demo 的 mock 数据。两条路的 outcome 分别存储，互不关联。
4. **天路径 3 天闸门没接入 loop_demo**：`run_next_demo_day("pv_day")` 直接对到达数据全检测，不走 `prepare_day_detect_batch` 过滤。
5. **设备到达看台**：`PvPointReplayEntityPanel` 被 `showPointReplay=false` 门控，从未渲染。
6. **异步延迟到达**：所有点按时间排好序一次灌入，没有模拟设备间的到达延迟。

---

## 8. 关键文件索引

| 文件 | 职责 |
|---|---|
| `backend-service/services/slot_datasets/loop_demo.py` | 演示主循环：`run_next_demo_day` 喂数 → 检测 → 审核 → 精度 → 观测台 |
| `backend-service/services/slot_datasets/real_model_detect.py` | 真实模型推理入口：`detect_point_with_tcn` TCN 批检测，`detect_day_with_rfc` RFC 天检测 |
| `backend-service/services/slot_datasets/realistic_mock_builder.py` | 从真实训练数据采样 mock 数据集 |
| `backend-service/services/timeseries_point/replay_activity.py` | 逐点推进引擎：session 管理、`earliest_event_time` 选点、entity_cursors |
| `backend-service/services/timeseries_point/point_alarm_state_machine.py` | 告警状态机：open/close/dedupe/label_switch 的纯函数实现 |
| `backend-service/services/timeseries_point/point_alarm_store.py` | 告警持久化：entity_states.json + events.jsonl |
| `backend-service/services/timeseries_point/predict.py` | 单点推理：`predict_point_outcome` 接受 WindowResult 调 artifact |
| `backend-service/services/iterative_labeling/realtime_point/artifact.py` | TCN artifact 加载器：20+ 项校验 + FixedRobustScaler + forward |
| `backend-service/services/iterative_labeling/realtime_point/trainer.py` | TCN 训练器：temporal split + 因果审计 + early stopping |
| `backend-service/services/slot_datasets/observability_ledger.py` | 观测台：status / calendar / replay_observatory_step / rebuild / 3 天闸门 |
| `backend-service/api/slot_datasets.py` | HTTP 端点：advance-day / replay-step / mock-gold-review / observability |
| `frontend-sevice/src/components/slot/PvPointAccuracyOpsPanel.tsx` | 点精度运营面板：曲线+Acc+告警（客户端模拟） |
| `frontend-sevice/src/components/slot/SlotOpsClockBar.tsx` | 水位条：推进按钮+Switch+事件时钟 |
| `frontend-sevice/src/pages/deployment/SchedulerTab.tsx` | 调度页：嵌入水位条+日历+观测台 |
| `frontend-sevice/src/services/slotObservabilityApi.ts` | 前端 API 客户端：advanceDay / replayStep / getOutcomes / getMockAccuracy |

---

## 9. 下一步需要对齐的（见 pv_replay_pipeline_alignment.plan.md）

1. loop_demo 点路径对接 replay_activity → 真正逐点推进
2. 告警从后端 alarm_state_machine 真实触发
3. 天路径接入 3 天闸门
4. 设备到达看台
5. 异步延迟到达模拟
<!-- @AI_GENERATED: end -->
