<!-- @AI_GENERATED -->
---
name: PV Replay Pipeline Alignment
overview: 把点路径 loop_demo 对接 replay_activity 逐点推进；天路径接入 3 天闸门；前端设备到达看台；模拟异步延迟到达。
todos:
  - id: point-replay-bridge
    content: loop_demo pv_point 模式对接 replay_activity，不再按天批灌，而是逐点推进 + 因果窗口 + 真实 TCN
    status: pending
  - id: day-gate-bridge
    content: loop_demo pv_day 模式接入 prepare_day_detect_batch 闸门，3 天未到齐自动 skip
    status: pending
  - id: arrival-simulator
    content: 模拟异步延迟到达：多设备交错、随机延迟、中断续传
    status: pending
  - id: device-arrival-observatory
    content: 前端设备到达看台：点路径每台设备到达/检测/pending 实时面板
    status: pending
  - id: alarm-backend-real
    content: 告警从后端 alarm_state_machine 真实触发，前端不再模拟 computeAlarmEvents
    status: pending
  - id: e2e-verify
    content: 端到端验证：多设备交错推进 + 告警生命周期 + 3 天过期 + 前端看台
    status: pending
isProject: false
---

# 光伏 Replay 管道对齐方案

## 背景

当前 `loop_demo` 的点路径（pv_point）是**按天批灌**的——`run_next_demo_day` 把一天几百个点一次性灌入、一次性对每个点调 TCN forward。这和 design 文档里「`replay_activity` 逐点推进、一点一判」的设计不一致。天路径的 3 天未到齐闸门虽然代码已实现，但没接入 `run_next_demo_day`。

### 已有但没接通的模块

| 模块 | 位置 | 状态 |
|---|---|---|
| `replay_activity.py` — 跨设备交错选点（`earliest_event_time`） | `services/timeseries_point/replay_activity.py` | ✅ 代码+测试有，loop_demo 没接 |
| `point_alarm_state_machine.py` — 告警状态机 | `services/timeseries_point/point_alarm_state_machine.py` | ✅ 代码+测试有，告警由前端模拟 |
| `point_alarm_store.py` — 告警存储+摘要 | `services/timeseries_point/point_alarm_store.py` | ✅ 有 HTTP 端点 |
| `prepare_day_detect_batch()` — 天路径占用闸门+3 天过期 | `services/slot_datasets/observability_ledger.py` | ✅ 代码+测试有，loop_demo 没接 |
| `SlotObservabilityCalendar` — 设备×日网格 | `frontend-sevice/src/components/slot/SlotObservabilityCalendar.tsx` | ⚠️ 天路径在用，点路径只显示 replay 进度 |

### 要解决的问题

1. 点路径 loop_demo 说是「逐点实时检测」但实际按天批灌
2. 多台设备总是一台跑完再跑下一台，不是现场的并行到达
3. 没有模拟「某台设备延迟 / 中断 / 补传」
4. 天路径 3 天闸门没接入演示流程
5. 告警是前端事后模拟（`computeAlarmEvents`），不是后端实时触发
6. 点路径没有设备到达看台

---

## 1. 点路径 loop_demo 对接 replay_activity

**核心改动**：`run_next_demo_day("pv_point", use_real_model=True)` 不再自己调 `_detect_chunk`，而是：

```
1. feed_next_day → 当天点追加到 arrived.parquet（不变）
2. 把当天新到达的点 enqueue 到 replay_activity 的 pending_feed
3. 不立刻检测——由「推进 N 点」按钮驱动 replay_next_point()
4. 每推一点：
   a. _pick_next_source_index → 选最早事件时间的下一个点（跨设备）
   b. 构建因果窗口（当前实体 committed_history[-ctx:] + pending）
   c. 调 TCN forward → outcome
   d. outcome 送 alarm_state_machine → 产生或不产生告警事件
   e. cursor 推进、outcome 写入
5. outcomes.json 和 daily_accuracy.json 由推进过程增量写入
```

**不改什么**：
- `realistic_mock_builder` 采样逻辑不变
- `real_model_detect.py` 的 TCN 推理逻辑可复用（提取成共享函数）
- `feed_next_day` 的按天喂数不变（现实中也是按天到达的数据批次）
- 天路径 pv_day 的 `run_next_demo_day` 不变（天路径不需要逐点）

**新增**：
- `loop_demo.py` 新函数 `enqueue_day_to_replay(slot, day)` — 把当天 arrived 点插入 replay session 的 source_rows / pending_feed
- `loop_demo.py` 新函数 `step_replay_with_real_model(slot, points=1)` — 包装 `replay_next_point`，用真实 TCN，逐点写 outcome + 调 alarm_state_machine
- `run_next_demo_day("pv_point", use_real_model=True)` 改为只做 feed + enqueue，不做检测

**前端变化**：
- SchedulerTab 点路径「推进一步 / 推 10 点 / 推 50 点」按钮在真实模型模式下走 `step_replay_with_real_model`
- 「推进下一天」在点路径只做喂数 + enqueue，不做检测

### 文件清单

| 文件 | 改动 |
|---|---|
| `backend-service/services/slot_datasets/loop_demo.py` | 新增 `enqueue_day_to_replay` / `step_replay_with_real_model`；`run_next_demo_day` pv_point 模式分离 |
| `backend-service/services/timeseries_point/replay_activity.py` | 可能需要小改：支持 `pending_feed` 动态追加到 session |
| `backend-service/api/slot_datasets.py` | `replay-step` 端点透传 `use_real_model` |
| `frontend-sevice/src/pages/deployment/SchedulerTab.tsx` | 点路径推进按钮在真实模型模式下调 replay-step 而不是 advance-day |
| `frontend-sevice/src/services/slotObservabilityApi.ts` | `replayStep` 加 `useRealModel` 参数 |

---

## 2. 天路径接入 3 天闸门

**核心改动**：`run_next_demo_day("pv_day")` 在检测前调 `prepare_day_detect_batch()`，只对 ready 的设备-日跑 RFC，waiting 的留着、expired 的标 skipped。

```
当前：feed → 对全部到达数据 _detect_chunk → review
改后：feed → prepare_day_detect_batch → 只对 ready 设备 _detect_chunk → waiting/skipped 写入日历
```

**前端变化**：日历格子已经支持 `waiting` / `skipped` 状态显示，只需要后端正确写入 ledger cells。

### 文件清单

| 文件 | 改动 |
|---|---|
| `backend-service/services/slot_datasets/loop_demo.py` | `run_next_demo_day` pv_day 模式在检测前调 `prepare_day_detect_batch` |
| `backend-service/services/slot_datasets/observability_ledger.py` | 可能无改动（`prepare_day_detect_batch` 已就绪） |

---

## 3. 模拟异步延迟到达

**目标**：让多台设备的点不是完美同步到达，而是有随机延迟和交错。

**方案**：在 `enqueue_day_to_replay` 时给每个点加一个 `arrival_offset_minutes` 字段：

```python
# 每台设备一个随机基准延迟（0~30 分钟）
# 每个点在基准上再加 ±2 分钟抖动
# 某台设备有 5% 概率在某个时间段「断连」（连续 3~10 个点延迟 60 分钟）
```

`_pick_next_source_index` 选点时按 `event_time + arrival_offset` 排序，这样：
- 设备 A 的 08:00 点可能在 08:02 到达
- 设备 B 的 08:00 点可能在 08:15 才到达
- 设备 C 的 08:00~08:30 段可能整段延迟到 09:00 才到

**不影响因果性**：窗口仍然按事件时间构建，到达时间只影响推进顺序。

### 文件清单

| 文件 | 改动 |
|---|---|
| `backend-service/services/slot_datasets/loop_demo.py` | `enqueue_day_to_replay` 给点加 `arrival_offset` |
| `backend-service/services/timeseries_point/replay_activity.py` | `_pick_next_source_index` 排序时考虑 `arrival_offset` |

---

## 4. 前端设备到达看台

**目标**：点路径也有一个类似天路径日历的面板，但粒度是「设备 × 时间段」而不是「设备 × 天」。

**设计**：在点路径 SchedulerTab 的 `SlotOpsClockBar` 下方增加一个 `PointDeviceArrivalPanel`：

```
┌──────────────────────────────────────────────────────┐
│ 设备到达看台          事件时钟 2021-08-23 09:35       │
├──────────────────────────────────────────────────────┤
│ 设备 A  ████████░░░░░░░░  到达 48/218  检测 48      │
│ 设备 B  ████░░░░░░░░░░░░  到达 24/220  检测 24      │
│ 设备 C  ██████████░░░░░░  到达 72/251  检测 65      │
│ 设备 D  ░░░░░░░░░░░░░░░░  到达 0/220   延迟中       │
├──────────────────────────────────────────────────────┤
│ 待处理: 156 点  已处理: 137 点  无判定: 7 点         │
└──────────────────────────────────────────────────────┘
```

数据来源：`replay_activity.session_entity_overview()` 已经返回每台设备的 `source_points / replayed_points / last_source_time / last_replay_time`。前端只需要调 `GET /timeseries-replay/session/{id}` 然后渲染。

### 文件清单

| 文件 | 改动 |
|---|---|
| `frontend-sevice/src/components/slot/PointDeviceArrivalPanel.tsx` | **新建** — 设备到达进度条面板 |
| `frontend-sevice/src/pages/deployment/SchedulerTab.tsx` | 点路径区域嵌入 `PointDeviceArrivalPanel` |
| `frontend-sevice/src/components/slot/PvPointAccuracyOpsPanel.tsx` | 精度运营页嵌入（只读模式） |

---

## 5. 告警从后端真实触发

**核心改动**：点路径每推一个点，outcome 直接送 `point_alarm_store.ingest_point_outcome()`。前端不再用 `computeAlarmEvents` 前端模拟。

```
当前：
  outcomes → 前端 computeAlarmEvents() → 前端渲染告警时间线

改后：
  每个 replay_next_point → outcome → ingest_point_outcome → alarm_state_machine
  前端从 GET /timeseries-replay/alarm-summary 读取后端告警
```

**前端变化**：
- `PvPointAccuracyOpsPanel` 的 `demoAlarmSummary` 改为从后端告警 API 读
- 删除或降级 `computeAlarmEvents`（可保留为 fallback）
- 告警时间线和告警表都从 `alarm_summary.events` 渲染

### 文件清单

| 文件 | 改动 |
|---|---|
| `backend-service/services/slot_datasets/loop_demo.py` | `step_replay_with_real_model` 里调 `ingest_point_outcome` |
| `frontend-sevice/src/components/slot/PvPointAccuracyOpsPanel.tsx` | 告警数据源从前端模拟改为后端 API |

---

## 6. 执行顺序

```
第 1 步：点路径 loop_demo 对接 replay_activity（§1）
        — 最核心，其他都依赖这个
        — 验证：推 10 点，outcome 逐个产生，多设备交错

第 2 步：告警从后端触发（§5）
        — 紧接第 1 步，每个 outcome 触发状态机
        — 验证：推进到连续故障段，后端产生 alarm_open

第 3 步：天路径 3 天闸门（§2）
        — 独立改动，不依赖第 1 步
        — 验证：喂 3 天数据，某设备点不够，第 3 天标 skipped

第 4 步：设备到达看台（§4）
        — 依赖第 1 步的 entity_overview 数据
        — 验证：前端看到每台设备进度条

第 5 步：异步延迟到达（§3）
        — 锦上添花，放最后
        — 验证：同一时刻设备 A 已到、设备 B 延迟中
```

---

## 7. 不改什么

- `realistic_mock_builder.py` 采样逻辑不改
- `real_model_detect.py` RFC 推理逻辑不改（天路径继续用）
- `real_model_detect.py` TCN 推理逻辑提取为共享函数但不改签名
- 天路径的 `run_next_demo_day` 批检测逻辑不改（天路径不需要逐点）
- 现有 19 个测试不能红
- 不碰 `pv_fault` 遗留数据
- 不写入累计账本

---

## 8. 验收口径

1. 点路径「推 1 点」按钮：每次只处理一个点，outcome 里能看到不同设备交错出现
2. 连续推进 50 点后：至少 2 台设备都有 outcome，不是一台跑完再换下一台
3. 告警事件从后端 API 返回，不是前端 `computeAlarmEvents` 模拟
4. 天路径推进 3 天：某设备点不够 173 → 第 3 天日历格子显示「已过期跳过」
5. 设备到达看台：能看到每台设备的到达进度和检测进度
6. 所有 19+ 个现有测试仍然通过

---

## 9. 会话交接上下文

**可直接贴给下一会话**：

本会话做了 mock 真实模型推理管道（`realistic_mock_builder` + `real_model_detect` + `loop_demo` 的 `use_real_model` 开关），天路径 RFC 和点路径 TCN 都能跑通精度。前端标签名、置信度、scatter tooltip 都已修复。

本 plan 的目标是把点路径 loop_demo **从按天批灌改成走 replay_activity 逐点推进**，同时接入告警状态机和天路径 3 天闸门。

关键文件：
- `backend-service/services/slot_datasets/loop_demo.py` — 演示主循环，需要分离 pv_point 的检测逻辑
- `backend-service/services/timeseries_point/replay_activity.py` — 逐点推进引擎，已有跨设备交错
- `backend-service/services/timeseries_point/point_alarm_state_machine.py` — 告警状态机，已有单测
- `backend-service/services/slot_datasets/observability_ledger.py` — 天路径闸门，已有 3 天过期
- `backend-service/services/slot_datasets/real_model_detect.py` — TCN 推理，需提取共享函数
- `frontend-sevice/src/pages/deployment/SchedulerTab.tsx` — 调度页，需改推进按钮行为
- `frontend-sevice/src/components/slot/PvPointAccuracyOpsPanel.tsx` — 点精度运营，告警数据源要改

后端 conda `cp_web`；Windows PowerShell；路径只用相对路径；工作区很脏不要 git commit/reset。
<!-- @AI_GENERATED: end -->
