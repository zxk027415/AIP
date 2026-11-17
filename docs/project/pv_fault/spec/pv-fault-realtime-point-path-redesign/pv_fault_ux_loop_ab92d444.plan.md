---
name: PV Fault UX Loop
overview: 天/点按场景隔离的打标与快照、生产/候选、gold mock 精度；调度与精度运营做成观测台（日历+水位）；点路径 replay 改为按事件时间跨设备交错。
todos:
  - id: label-flow-ui
    content: 无标签打标改成 Steps 流程（界面共用）；提案/成员/标签空间/累计账本按 pv_day 与 pv_point 严格隔离；簇上显示建议标签；图形化审核提案
    status: completed
  - id: snapshot-preview
    content: 快照 preview API + 累计训练页查看每个快照的行数/类别分布/样本行（天和点）
    status: completed
  - id: slot-to-scene
    content: 前端可见文案槽位→场景；API/URL/字段名 slot 不动
    status: completed
  - id: prod-candidate
    content: 部署页生产/候选角色替代「下次按日检测」；registry 同步 champion + rolling_detect_model
    status: completed
  - id: mock-gold-review
    content: 用 gold 接回一小批审核真值，跑通 AccuracyEvaluator 与 daily_review 回流，供生产/候选展示精度
    status: completed
  - id: calendar-observability
    content: replay 按事件时间交错（旧会话不续跑）；每槽位观测账本；调度可写/精度只读日历；天路径工作流前过滤三天闸门
    status: completed
isProject: false
---

# 光伏故障调整方案（原五点 + 日历观测）

第 3 点按你已选的方案：**只改前端可见文案**，URL `?slot=`、API `/slot-*`、JSON 字段 `slot` 一律不动。

**界面共用、数据按场景隔离（硬约束）**：天路径 (`pv_day`) 和点路径 (`pv_point`) 共用同一套面板组件，但切换场景后只读写当前槽位。提案、成员行、标签注册表、累计账本、训练快照、模型登记互不串仓。负荷预测 Arena（生产/影子/预上线）不改行为，只改页面上的「槽位」二字。

```mermaid
flowchart LR
  upload[选或上传无标签数据] --> runLabel[跑打标模板]
  runLabel --> proposal[产出簇提案]
  proposal --> review[图形化审核纠正]
  review --> admit[确认写入累计账本]
  admit --> freeze[冻结训练快照]
  freeze --> train[训练登记模型]
  train --> roles[生产或候选]
  roles --> detect[按日或按点检测]
  detect --> calendar[日历观测到达与检测]
  calendar --> mockReview[gold mock 审核]
  mockReview --> accuracy[精度]
  accuracy --> roles
```

---

## 1. 无标签打标改成流程页（界面共用，数据按槽位隔离）

**隔离规则（第一步必须满足）**

- 组件共用：`SlotStoryLoopPanel` + 新 `SlotLabelProposalReviewPanel`，用 `slot` prop / `?slot=` 切换
- 数据不共用：所有 list / get / patch / confirm 必须带当前 `slot`，后端按 `data/slot_datasets/{pv_day|pv_point}/` 分区读写
- 切换场景时用 `key={slot}` 重挂载面板，清空另一侧的提案、选中文件、簇命名草稿，禁止跨槽位确认
- 建议标签只对 **当前槽位** 的 Label Registry + 该槽位 gold/快照 做最近邻，点的簇不能提示成天路径类别
- 打标模板按槽位：`workflow-pv-day-label-v1` vs `workflow-pv-point-label-v1`；执行时 `slot` 写入 `_global_config`，提案落盘带 `slot` 字段，confirm 若 `proposal.slot !== 请求 slot` 直接 422
- 不把两套数据合成一张表、不共用 `member_rows_path`、不把确认箱写入对方累计账本

现状：[`frontend-sevice/src/components/slot/SlotStoryLoopPanel.tsx`](frontend-sevice/src/components/slot/SlotStoryLoopPanel.tsx) 是一张扁平卡片——说明文字 + 三个按钮 + 提案表。簇名默认 `cluster_0`，操作只有「确认写入累计集」。人工审核图形化在 [`IterativeLabelingReviewPage.tsx`](frontend-sevice/src/pages/IterativeLabelingReviewPage.tsx)（波形、改判、标签注册表），提案链路没有接上。账本目录已经按槽位分开（`data/slot_datasets/pv_day/` 与 `pv_point/`），本条是把流程 UI 也钉死在这条隔离上，而不是做成混合列表。

目标四步（Ant Design `Steps`，当前步高亮，已完成可回看）：

1. **选数据** — 现有选文件/上传 Modal 收进第 1 步
2. **执行打标** — 跑 `workflow-pv-*-label-v1`，展示 `execution_id`、数据路径、模板 ID
3. **审核簇** — 打开提案审核面板（不是只改表里一个输入框）
4. **写入累计** — 审核通过后才允许确认

**簇上显示「可能是的标签」**

现在 [`emit_label_proposal.py`](backend-service/services/operator_backends/emit_label_proposal.py) 只写 `cluster_{id}`。标签注册表里已有业务名（如「正常」「组串失配」，见 [`label_registry.py`](backend-service/services/iterative_labeling/label_registry.py)）。

做法：用簇的 `representative_stats` 去对 **当前训练快照 / gold** 里各类别的特征均值，取最近 1～3 个已登记标签，写入 `suggested_label_names`。列表里显示：

`簇 0 · cluster_0` + Tag `可能：组串失配`

下拉框选项来自该场景的 Label Registry。**建议标签只是 Tag 提示，不自动写入确认名**；用户没改仍可确认，但文案要写「未改名会按 cluster_N 进注册表」。

新增 `POST /label-proposals/{id}/reject`（或 PATCH `status=rejected`），驳回后不再出现在待确认，不进累计。

**提案准入做成「像人工打标队列」的审核，而不是一个确认键**

新增面板 `SlotLabelProposalReviewPanel`（从 `SlotStoryLoopPanel` 点「审核提案」打开 Drawer/全宽卡，天和点同一组件）：

- 左：簇列表（成员数、建议标签）
- 中：代表样本曲线（点路径用 `time`+`i_cal`/`value`；天路径用日特征柱/表）。数据来自提案已有的 `member_rows_path`
- 右：改标签、剔除成员、看成员表
- 底：确认写入累计 / 驳回提案

后端补 3 个小接口（挂在现有 [`api/iterative_labeling.py`](backend-service/api/iterative_labeling.py) 的 `/label-proposals` 下）：

- `GET /label-proposals/{id}?slot=` — 详情 + 建议标签 + 成员抽样
- `PATCH /label-proposals/{id}` — 改簇名 / 成员
- `POST /label-proposals/{id}/reject` — 驳回
- 确认沿用 `POST .../confirm`

不复用整页 `IterativeLabelingReviewPage`（那是预测单元 `rev-*`，不是聚类提案）。只复用波形和标签下拉的交互习惯。也不把提案改成 `from-dataset` 审核会话——成员 CSV 和 `selected_member_keys` 已够用。`ListPage` 已 import `Steps` 但未渲染，直接用它。孤立组件 `SlotAnnotationReviewPanel` 不接入本条（那是 G5 滚动候选，不是聚类提案）。

主改文件：`SlotStoryLoopPanel.tsx`、新 `SlotLabelProposalReviewPanel.tsx`、`label_proposals.py`、`iterative_labeling.py`、`iterativeLabelingApi.ts`。建议标签计算放 `label_proposals.py`，不改打标模板 JSON。

---

## 2. 训练快照能看出里面有哪些数据

现状：[`CumulativeTrainingLedgerPage.tsx`](frontend-sevice/src/pages/CumulativeTrainingLedgerPage.tsx) 展开快照只看到 `included_events`（来源确认箱 ID、时间、文件路径），看不到行数、类别分布、样本。部署页已有「训练快照标签形态」波形（[`reference-waveforms`](backend-service/api/iterative_labeling.py)），累计页没有入口。

补：

- 后端 **新建** `GET /api/slot-datasets/snapshots/preview?slot=&freeze_id=`：行数、时间范围、设备数、`label` 分布、列名、前 50 行（相对路径读 `artifact_ref`）
- **必须直接读 parquet**。现有 `GET /workflows/enhanced/datasets/{id}/preview` 只支持 CSV/Excel，而 `snap-pv_day-v2`、`snap-pv_point-v5` 已是 parquet，不能复用那条预览
- 累计页快照表增加「查看内容」：Drawer 里放分布图 + 样本表；波形仍复用 `reference-waveforms`（部署页已对最新快照这样做过）
- 天、点同一套，用当前 `slot` 参数。展开行继续显示确认箱来源；Drawer 才展示合并文件里的实际数据

主改：[`snapshots.py`](backend-service/services/slot_datasets/snapshots.py)、[`api/slot_datasets.py`](backend-service/api/slot_datasets.py)、[`slotCumulativeApi.ts`](frontend-sevice/src/services/slotCumulativeApi.ts)、`CumulativeTrainingLedgerPage.tsx`。

---

## 3. 前端「槽位」全部改成「场景」

只改用户看见的中文（按钮、表头、Alert、Form label、aria-label）。标识符 `slot`、`storySlot`、`currentSlot`、路由 query 不动。

加一个展示函数（例如 [`slotProductConfig.ts`](frontend-sevice/src/config/slotProductConfig.ts) 的 `sceneWord = '场景'`），页头选择器统一写成「场景」。

覆盖范围：用户可见的「槽位」二字都改「场景」，含负荷预测页头。**只改字，不改 Arena 生产/影子逻辑**。URL 仍是 `?slot=`。`zh.json` 里「default 槽位」改成「默认场景」。

---

## 4. 部署页：下次按日检测 → 生产 / 候选

现状：[`SlotDeployedModelPanel.tsx`](frontend-sevice/src/components/slot/SlotDeployedModelPanel.tsx) 把登记模型当成「检测指针」；后端 [`set_rolling_detect_model`](backend-service/services/slot_governance/registry.py) 注释写明「不是 Promote Champion」。registry 里其实已有 `champion` / `challenger`，但 UI 没用，按日检测走 `rolling_detect_model`（[`resolve_slot_scheduler_model`](backend-service/services/scheduler/slot_workflow_runner.py)）。

产品语义（先手动切换；第 5 点有精度后再按精度维护）：

| 角色 | 含义 | 落盘 |
|---|---|---|
| **生产** | 当前按日检测实际使用的模型 | `champion` + 同步写入 `rolling_detect_model`（调度兼容） |
| **候选** | 对照模型，不进按日检测 | `challenger` |

UI：

- 表格标注「生产」「候选」Tag，当前生产行高亮
- 按钮改为「设为生产」「设为候选」，去掉「用于下次按日检测」
- 文案不再写「这是检测指针，不是 Promote Champion」
- 「立即触发检测」明确跑**生产**模型

后端：增加 `PUT .../production-model`、`PUT .../candidate-model`。`resolve_slot_scheduler_model`：**champion 优先**，再回退 `rolling_detect_model`。设为生产时双写 `rolling_detect_model`。现网 `champion=null` 且已有检测指针时，第一次打开部署页不切断检测：回退仍走 `rolling_detect_model`，直到用户点「设为生产」再把当前指针升为 champion。

不把未挂载的 [`SlotClosedLoopActionsPanel.tsx`](frontend-sevice/src/components/slot/SlotClosedLoopActionsPanel.tsx) 整块搬上部署页（那是 Verify→Promote Champion 长流程）。生产/候选切换做在现有 `SlotDeployedModelPanel` 表格上，交互更短。

第 5 点精度出来后：表上显示各模型在 mock 真值上的 accuracy；提供「按精度把更优模型设为生产」（需确认，不自动静默切换）。不走负荷预测的 MAPE/`switch_decision`。

---

## 5. Mock 一小批标签，跑通精度和回流

卡点：按日检测精度走人工审核真值（[`AccuracyEvaluator`](backend-service/services/iterative_labeling/accuracy_evaluator.py) + 审核完成回流）。Mock 喂数源把 `label` 置空了（[`build_pv_dataset_splits.py`](backend-service/scripts/build_pv_dataset_splits.py)），所以运营页只有预测条数，没有对照精度。

Gold 还在：

- 天：`data/slot_datasets/pv_day/gold/all_labeled_combined.parquet`
- 点：`data/slot_datasets/pv_point/gold/point-poc-k4-labeled.parquet`

喂数是同一批数据去掉标签，**按 site/device/branch + 时间可以把 gold 标签接回去**。

做法（走真实审核/回流接口，不另造假精度文件）：

1. 新服务 `backend-service/services/slot_datasets/mock_gold_review.py`
2. 从最近一次 `emit_prediction_batch` / `annotation_candidates` 取最多约 30 条
3. 与 gold 按实体键 join；命中则生成 `rev-*` 会话并自动提交 `confirm`/`correct`（`reviewer=mock_gold`）
4. **槽位必须是 `pv_day` / `pv_point`**，走 `POST .../complete-and-admit` 写入累计（`source=daily_review`）。不要写进遗留 `pv_fault` 的 `day_labels` 表，也不走 `GET /accuracy-operations/slot-overview?slot=pv_fault`（那是旧闭环）
5. 会话级读 `GET .../review-sessions/{id}/accuracy`（`classifier_accuracy` / `macro.f1`），把数字写到该场景生产/候选展示字段
6. `PvDayAccuracyOpsPanel` / `PvPointAccuracyOpsPanel` 目前只展示预测分布、不算真值准确率——mock 精度优先出现在部署页模型表和审核完成后的会话页，不假装运营面板已经在算 F1

命中不足时：从 gold 抽一小段已有标签的设备-天补齐。**不要等 3 天闸门**才做 mock：闸门若把当前水位日全跳过，改为对 gold 子集跑一次 predict/replay 再审核，UI 标明「gold 回放 N 条」，不 reset mock 喂数游标。

入口：人工审核 Tab 上按钮「推进演示下一天（不入库）」。天、点各跑一遍。

**收口口径（相对上文原文的有意偏离）**：`POST /mock-gold-review` 实际走 `loop_demo.run_next_demo_day`（喂数 → 检测 → 建 `rev-*` → gold 自动 confirm/correct → 算精度）。**禁止** `complete-and-admit`，不写累计账本。holdout 评分服务 `mock_gold_review.py` 仍在仓库里，但 HTTP 不再挂那条回流。UI 文案统一为「不入库 / 未写入累计」。

主改：新 mock 服务、[`api/slot_datasets.py`](backend-service/api/slot_datasets.py) 一个 POST、[`SlotManualReviewQueuePanel.tsx`](frontend-sevice/src/components/slot/SlotManualReviewQueuePanel.tsx)、`SlotDeployedModelPanel` 精度列。

---

## 6. 日历观测 + 天路径水位 + 三天未到齐策略

现状缺口：

- 定时调度里 [`PvIngestionSiteOverview.tsx`](frontend-sevice/src/components/pv-fault/PvIngestionSiteOverview.tsx) 只是**单业务日**站点表，不是 30 天日历，也看不到故障曲线和标签
- 「推进下一天」只在遗留 `pv_fault` mock 喂数（[`SchedulerTab.tsx`](frontend-sevice/src/pages/deployment/SchedulerTab.tsx) 的 `isPvSlot`），**`pv_day` 产品槽没有水位推进按钮和追踪条**
- 天路径产品检测 [`slot_product_tasks.py`](backend-service/services/scheduler/tasks/slot_product_tasks.py) 整表跑 predict，**没有**「未到齐保留 3 天 → 仍不齐则跳过」
- 点路径 [`PvPointReplayEntityPanel.tsx`](frontend-sevice/src/components/slot/PvPointReplayEntityPanel.tsx) 只有 replay 游标进度，不能按日历选时段看曲线，也不能对某设备手动触发
- 精度运营 [`PvDayAccuracyOpsPanel`](frontend-sevice/src/components/slot/PvDayAccuracyOpsPanel.tsx) / [`PvPointAccuracyOpsPanel`](frontend-sevice/src/components/slot/PvPointAccuracyOpsPanel.tsx) 只展示最近一次执行，没有历史到达/检测网格

**共用日历组件（界面共用、数据按场景隔离）**

新组件 `SlotObservabilityCalendar`，同时嵌进：

- 定时调度 [`SchedulerTab.tsx`](frontend-sevice/src/pages/deployment/SchedulerTab.tsx)
- 精度运营天/点面板

控件：日期范围（默认最近 7 天，**最长 30 天**）、设备筛选。网格：行=设备，列=自然日。点选格子或拖选一段 → 右侧/Drawer 画该设备该时段的故障曲线 + 标签（有预测画预测，有回流真值叠真值）。

格子状态（历史保留，不覆盖丢掉）：

| 状态 | 含义 |
|---|---|
| 已到达/待检测 | 有测量点，尚未出检测结果 |
| 未检测 | 天路径：当天点数未达阈值，仍在 3 天宽限内 |
| 已检测 | 该日（天）或该日范围内（点）已有检测结果 |
| 已过期跳过 | 天路径：宽限 3 天仍未到齐，永久不检该设备-日 |
| 迟到补点 | 已检测或已跳过之后又有新点到达（本轮要做的角标） |
| 无数据 | 当天没有任何到达 |

**格子上必须能读到（本轮）**：到达点数 / 期望点数、完整度%、检测所用 `model_id`（或未检）、跳过原因（未到齐 / 已过期 / 手动跳过）。Tooltip 即可，不必把日历撑爆。

到达与检测记录按 `pv_day` / `pv_point` 分仓长期保存。**不要把遗留 `measurement_ingestion_daily` 当产品日历真源**（那张表主要服务 `pv_fault`，产品槽位的日检工作流目前也不写它）。观测状态写入 `data/slot_datasets/{slot}/` 下的账本（相对路径），曲线/预测引用 replay outcome 或 predict execution。

**天路径「到齐」阈值不要用 288×90%**。现网 CompletenessGate 默认 `expected_point_count=288`、`completeness_ratio=0.9`，光伏白天常常只有约 200 行。宽限判定用占用口径（约 173/288），水位条写明数字。

**迟到补点（本轮）**：已检测或已过期跳过之后点数仍增加，格子打角标，不自动重检；可手动补检。

**天路径滚动（改行为）**

当前 `pv_day_predict_task` 是整次 predict 一把跑，**不会按设备-日做 3 天宽限**。必须在进工作流之前过滤：

1. 水位条：当前业务日、已检 / 宽限中未检测 / 过期跳过 + **「推进下一天」**（只动 `pv_day` 检测水位）
2. 未达占用门槛：标 **未检测**，最多等 3 个自然日
3. 到齐的设备-日才进入本次 predict；满 3 天不齐 → **已过期跳过**，写账本、不调模型
4. 一台失败只红那一格
5. 手动触发可对已过期设备补检（二次确认 + 审计）
6. cron 只处理**当前水位日**的就绪或到期该跳过的设备，**不自动跨日**。跨日只靠按钮。

**点路径 replay（本轮要改推进顺序）**

现状：[`replay_activity.py`](backend-service/services/timeseries_point/replay_activity.py) 把源点按 `entity + 时间` 排成一条队列，全局 `cursor` 从 0 走到完。效果是 **一台设备全部点走完，才轮到下一台**。调度 tick 默认每次 1 点。这和现场「多台设备几乎同时到点」不符，日历也会先铺满 A、B 还是空的。

改为 **按下一笔事件时间跨设备交错**（merge 多路游标，不是 round-robin 各推一点）：

1. 每台设备自己的 `entity_cursors` 成为推进真源；全局 `cursor` 只表示已处理总点数
2. 每次 tick：在所有「还有剩余点」的设备里，选 **下一笔 `event_time` 最早** 的那一条（时间相同则按 `entity_key` 稳定打破平局）
3. 只处理这一条（仍默认 `max_points_per_tick=1`）；因果窗口继续只取该设备历史
4. `pending_feed` 新点插入该设备自己的时间线，禁止再往全局队尾 append
5. 观测水位展示 **当前事件时钟**，不要用「设备完成百分比」当主进度
6. **旧会话兼容**：已按「设备整段队列」推进的 session 不要用新选点器去解释旧 `cursor`（会跳点/重检）。新会话才走交错；已有会话只读或提示重建
7. 调度「推进一步」默认 1 点；可选用 1/10/50（上限 50），方便把日历铺开，但不一次跑完整文件

文件 replay 和线上 pending_feed 用同一套选点器。

**点路径（日历是观测切面，闸门不是「天」）**

- 检测按点到达 + 上面的事件时间交错，不要求整天到齐，不套用 3 天过期
- 日历按自然日聚合：格子 = 当天已到达点数 / 已检点数 / 模型 / 迟到补点
- 可选开始–结束（最长 30 天）看连续曲线
- 支持对某设备手动触发一段 replay（只推该设备时间窗内的点，不挡别的设备）

**定时调度页：天和点都做成同一套「观测台」布局（文案和水位不同）**

现在 [`SchedulerTab.tsx`](frontend-sevice/src/pages/deployment/SchedulerTab.tsx) 是任务表 + 喂数按钮 + 到达表或 replay 进度条，用户看不出「现在走到哪、哪些设备卡着」。本轮主视觉改成：

1. **水位条（最上）**
   - 天：当前业务日、门槛（约 173 点）、已检 / 宽限中未检测 / 过期跳过；按钮「推进下一天」
   - 点：当前事件时钟、本 tick 处理了哪台设备的哪个时间点、待处理点数；按钮「推进一步 / 暂停」
2. **日历（主区域）** — 共用 `SlotObservabilityCalendar`，最长 30 天；点格看曲线+标签；格子带点数、完整度%、模型、跳过原因、迟到补点
3. **选中详情** — 曲线、标签、最近一次检测/失败原因、手动触发
4. **定时任务表** — 收到折叠或页面下部，当作 cron 运维，不当观测主入口

点路径现有 [`PvPointReplayEntityPanel`](frontend-sevice/src/components/slot/PvPointReplayEntityPanel.tsx) 的「回放进度 37/100 + 全局 Progress」降为日历下方的次要「各设备累计点数」，避免用户以为要等一台 100% 才有下一台。天路径现有单日 `PvIngestionSiteOverview` 同样降为次要，主入口换成日历。

**定时调度 vs 精度运营（同一日历，职责分开）**

- **定时调度**：能改水位——推进下一天 / 推进一步、暂停、手动检测
- **精度运营**：同一日历只读（看曲线、标签、格子状态）；需要动手时链到调度页对应场景，避免两个页面都能推进水位对不上

控件：日期范围默认 7 天、最长 30 天。设备行太多时搜索 + 最多先渲染 50 行（可翻页），禁止一次画几千格卡死。曲线按显示宽度抽样，需要再拉明细。

调度页和精度运营嵌同一 `SlotObservabilityCalendar` + 同一 GET。

后端接口（都带 `slot`）：

- `GET .../observability/calendar?slot=&from=&to=` — 设备×日状态网格（含点数、完整度、model_id、skip_reason、late_arrival）
- `GET .../observability/curve?slot=&device=&from=&to=` — 曲线 + 预测标签 + 真值标签
- `POST .../observability/advance-day` — 仅 `pv_day` 水位推进
- `POST .../observability/manual-detect` — 指定设备（+ 可选日期或时间窗）手动检测；迟到补点走同一入口

主改：新日历组件、SchedulerTab、PvDay/PvPointAccuracyOpsPanel、scheduler/slot 观测 API、天路径 3 天宽限判定（接到 `pv_day` 日检任务，不改点路径闸门）。

---

## 7. 生产会踩的问题和观测建议（调研结论）

对照现有到达表、CompletenessGate、replay `no_decision`、双路径 design 的迟到/乱序（G9 未做）、以及精度面板只看最近一次执行。

### 天路径

| 问题 | 为何会发生 | 观测上怎么露出 |
|---|---|---|
| 完整性门槛用错 | 默认 288×90%，白天常常只有 ~200 点 | 格子写完整度%；门槛用占用口径（约 173），水位条写明数字 |
| 迟到补点 | 检完或过期后又来点 | 本轮「迟到补点」角标，不自动重检 |
| 整表预测一锅粥 | 一台失败或数据脏拖死整天 | 日历按设备着色；失败格写 error，不把整天标成全失败 |
| 业务日切错 | 时区、跨日、墙钟 vs 事件时间 | 水位展示的是事件业务日，不是服务器今天 |
| 夜间/低出力污染日特征 | 固定 00–24 聚合成一天 | 曲线上可区分白天段（本轮只画曲线，季节日照窗标注放后续） |
| 标签空间落后 | 审核新增了类，生产模型还是旧空间 | 后续：格子旁 `label_space_lag`；本轮不做 |

### 点路径

| 问题 | 为何会发生 | 观测上怎么露出 |
|---|---|---|
| 窗口未就绪 / 间隔过大 | `causal_window` → `no_decision` | 后续：格子叠 no_decision 率；本轮曲线 Drawer 里能看到该点 kind/reason 即可 |
| 乱序、重复 `(entity,time)` | 采集重放、补传 | 后续 G9 revision；本轮迟到补点至少能看见「检后点数变了」 |
| 游标队头阻塞 | 旧实现按设备整段走完 | 改成事件时间交错后，日历按日同时铺开；某台仍卡住只红那一行 |
| 把日历当成「天闸门」 | UI 按日聚合 | 点路径文案写清：日历是切面，检测仍按点到达 |
| 告警抖动 | 开/关频繁 | 后续告警状态机叠日历；本轮不做 |
| 检测延迟 | 事件时间 vs 真正跑出 outcome 的时间 | 后续；本轮不画延迟直方图 |

### 两条路都会遇到

- 生产指针和 Champion 不一致（第 4 点要收掉）
- 无真值时运营页只有预测分布（第 5 点 mock 补）
- 天/点/遗留 `pv_fault` 看串仓
- 手动触发无审计 → `manual-detect` 必须写 operator、原因、覆盖哪些设备-日

### 本轮纳入日历（已确认）

1. 格子：到达点数、完整度%、检测模型、跳过原因
2. 已检/已跳过后点数增加 → 「迟到补点」
3. 已定：30 天范围、水位推进、三天未到齐跳过、手动触发、历史保留
4. 点路径 replay 按最早下一事件时间跨设备交错；调度页天/点统一观测台布局

### 明确不做（后续）

沉默设备进网格、点路径 no_decision 热力、双模型曲线叠加、延迟分布、告警开闭叠层、乱序 revision 队列、季节日照窗标注、cron 自动跨日、把 `pv_fault` 到达表当产品日历真源。

---

## 8. 复盘后的收口

实现按依赖排：文案「场景」→ 打标+快照预览 → 生产/候选 → replay 交错+观测账本+日历（调度可写、精度只读）→ gold mock。

额外风险：旧 replay 会话不能用新选点器续跑；日历限 50 行并抽样曲线；天路径 3 天闸门必须在 predict 之前过滤，否则 UI 显示跳过、模型仍全检。

---

## 改动范围（按条）

- **1**：打标流程 UI + 提案预览/改簇 API（约 6 个文件）
- **2**：快照 preview API + 累计页 Drawer（约 4 个文件）
- **3**：前端可见「槽位」文案（约 20 个 TSX，无逻辑）
- **4**：registry 生产/候选 + 部署页表格/按钮（约 4 个文件）
- **5**：gold mock 审核 + 精度回写（约 5 个文件）
- **6**：replay 事件时间交错 + 调度/精度观测台日历（水位、格子指标、迟到补点、天路径三天跳过、手动触发）

不改：打标模板 JSON 拓扑、负荷预测 Arena 切换逻辑、git 提交。日历若必须记「等待起始日 / 过期跳过」，允许小范围扩展到达账本，不新建与 `pv_fault` 双路径混用的表。

---

## 验证（实现阶段，conda `cp_web`）

- 提案预览/确认、快照 preview、生产/候选切换、mock 审核：各补 focused pytest
- 手工：`pv_day` / `pv_point` 各走一遍「选数据 → 打标 → 审核簇 → 确认」；切换场景后提案列表、确认箱、快照互不出现对方数据；累计页打开一个快照看样本；部署页标记生产并触发检测；点 mock 审核后精度数字出现且累计流水多 `daily_review`
- 日历：设备行上限/翻页；曲线抽样；调度可推进、精度运营只读；交错 replay 用新会话验证多设备同一自然日都被铺开；天路径未就绪设备不得出现在本次 predict 输入里
- 前端：浏览器过打标页、累计页、部署页、调度日历、精度运营日历（天/点切换）
- 不跑全量 pytest / `npm run build`（除非改动碰到明显类型错误）

风险：gold 与当前检测批次日期对不上时 mock 条数会很少，届时走 gold 子集回退并在 UI 标明实际命中条数。G4 `verify-async` 的 passed 门控过弱，本阶段不用它当生产切换依据，只用 mock 审核算出的 F1。
