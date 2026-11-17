<!-- @AI_GENERATED -->
# TSC（pv_tsc）平台接入 — 交付说明与验证记录

> 状态：**代码交付 + 后端/构建验证完成**，2026-09-03
>
> 本文承接 `tsc-platform-integration-plan.md`（方案定稿），记录第三条产品路径 `pv_tsc`（MultiRocket 时序分类）在**人工审核、累计训练、精度运营、模型部署、调度观测、工作流编辑器**六个运营入口的落地改动、字段契约、验证结果与风险。

---

## 1. 一句话

`pv_tsc` 作为与 `pv_day`（天路径）/`pv_point`（点路径）完全并列的第三个产品槽接入平台：产出粒度是**设备日**，一级单元是设备日最终标签，二级证据是 MultiRocket **重叠模型窗口**；首发以 **Challenger** 身份由 `pv_tsc_predict` 调度滚动检测，**不直接 Promote 为生产**。

---

## 2. 改了哪些文件（路径 — 职责 — 改动）

### 2.1 后端（5 处定点补丁）

| 文件 | 职责 | 本次改动 |
|---|---|---|
| `backend-service/services/scheduler/slot_workflow_runner.py` | 调度侧模型解析器 `resolve_slot_scheduler_model()`：按 Champion→rolling→Challenger→latest 顺序解析检测模型 | Challenger 分支补写 `source = "challenger"`（此前误报 `registry_fallback`），使调度回执与审核证据能拿到真实模型角色 |
| `backend-service/services/scheduler/tasks/pv_fault_tasks.py` | `_create_prediction_review_session()`：把调度预测批次写入同槽审核队列 | TSC 单元透传逐窗证据；context 补审核元信息；来源缺失时回落 `resolve_slot_scheduler_model` 补齐（详见 §3） |
| `backend-service/services/slot_datasets/annotation_candidate_review.py` | `_candidate_to_unit()`：机器候选 → 审核单元 | 透传 TSC 设备日结论、逐窗证据与模型角色，机器候选不再被裁成裸字段 |
| `backend-service/services/slot_datasets/observability_ledger.py` | `calendar_grid()`：设备日到达完整度日历 | 返回体透传 `readonly` — 只读标记（`pv_tsc=true`，`pv_day/pv_point=false`） |
| `backend-service/api/slot_datasets.py` | `_dataset_http()`：SlotDatasetError → HTTP 状态映射 | `read_only_slot` — 只读槽拒写，映射 HTTP **422**（此前落默认 400） |

### 2.2 前端（六大运营入口）

| 文件 | 职责 | 本次改动 |
|---|---|---|
| `frontend-sevice/src/services/iterativeLabelingApi.ts` | 审核相关 API 客户端 | 三处 `slot` 联合类型加 `pv_tsc` |
| `frontend-sevice/src/pages/IterativeLabelingListPage.tsx` | 迭代标注/审核列表页 | 人工审核场景下拉 `MANUAL_REVIEW_SLOT_OPTIONS` 加 `pv_tsc` |
| `frontend-sevice/src/components/slot/SlotManualReviewQueuePanel.tsx` | 人工审核队列面板 | 重写：session/queue 各自独立 loading/error/empty/retry + `Promise.allSettled`；TSC 隐藏演示推进 |
| `frontend-sevice/src/pages/IterativeLabelingReviewPage.tsx` | 审核工作台 | 加 `tsc_evidence` 类型 + 归一化保留逐窗证据；新增「设备日结论 + 重叠窗口」证据卡（附加式，纯手工会话无证据不渲染） |
| `frontend-sevice/src/components/slot/SlotLabelProposalReviewPanel.tsx` | 聚类提案审核抽屉 | 由 `isDay` 二态改为 day/point/tsc 三态；TSC 走设备日语义 |
| `frontend-sevice/src/pages/CumulativeTrainingLedgerPage.tsx` | 累计训练账本页 | 三槽文案、持久错误态+重试、切槽清旧 cutoff、freeze 独立 loading |
| `frontend-sevice/src/components/slot/PvTscAccuracyOpsPanel.tsx` | **新建** TSC 专用精度运营面板 | 真实 run-status 四态 + 只读日历 + strict 指标去处指引；不复用 day 的 mock/点曲线 |
| `frontend-sevice/src/pages/AccuracyOperationsPage.tsx` | 精度运营页 | `pv_tsc` 改渲染 `PvTscAccuracyOpsPanel`（原为复用 `PvDayAccuracyOpsPanel slot=pv_tsc`） |
| `frontend-sevice/src/components/pv-fault/PvFaultClassificationMetrics.tsx` | 分类指标组件（三槽共用） | 加 `balanced_accuracy_mean/std`、`n_splits_completed/requested`、`evaluation`、`production_contract_valid` |
| `frontend-sevice/src/components/slot/SlotAccuracyMetricsCard.tsx` | 精度主指标卡（三槽共用） | 加 `balancedAccuracy` — balanced accuracy 展示列 |
| `frontend-sevice/src/components/slot/SlotDeployedModelPanel.tsx` | 部署页模型面板 | `pv_tsc:3` 节点数、`pv_tsc_predict` 探测；`isTsc` 禁用 Promote/mock（含 handler 防御）；候选角色显示 Challenger；未 Promote 提示；三槽文案 |
| `frontend-sevice/src/services/deploymentApi.ts` | 部署/调度 API 客户端 | 加 `PvTscPredictRunStatus` 类型与 `getPvTscPredictRunStatus()` |
| `frontend-sevice/src/pages/deployment/SchedulerTab.tsx` | 调度页 | TSC 四态运行状态卡 + 持久 `obsError`；观测台对 TSC 强制 `writable=false` |
| `frontend-sevice/src/services/slotObservabilityApi.ts` | 观测 API 类型 | `ObservabilityStatus.readonly?`、`progress.total_days?: number\|null`、`ObservabilityCalendar.readonly?` |
| `frontend-sevice/src/components/slot/SlotObservabilityCalendar.tsx` | 观测日历（共用） | 持久错误+重试；消费后端 `readonly`；TSC 只读文案；`effectiveWritable` 双重防御手工补检 |
| `frontend-sevice/src/components/slot/SlotOpsClockBar.tsx` | 观测时钟条（共用） | `total_days` 允许为空；TSC 真实调度只读语义；推进/重置/replay handler 层 guard |
| `frontend-sevice/src/pages/WorkflowEditorPage.tsx` | 工作流编辑器 | 复用 `isPvProductSlot()` 放行三槽（原两处 guard 仅 day/point） |
| `frontend-sevice/src/components/workflow-enhanced/PropertyPanelV2.tsx` | 属性面板 | `PV_TRAINABLE_SLOTS` 加 `pv_tsc` |
| `frontend-sevice/src/components/workflow-enhanced/TrainableDatasetPicker.tsx` | 可训数据集选择器 | `PV_TRAINABLE_SLOTS` 加 `pv_tsc`；空态文案三槽化 |
| `frontend-sevice/src/types/workflow-enhanced.ts` | 工作流类型 | `EnhancedWorkflow.metadata?: Record<string, unknown>` |

---

## 3. 新增/变更接口与字段契约

### 3.1 GET `/api/scheduler/tasks/pv_tsc_predict/run-status`（只读，四态）

- **用途**：调度页与精度运营页展示 `pv_tsc_predict` 的运行健康度。**无路径参数**（防任意文件读取风险）。
- **四态** `state`：
  - `no_run_yet` — 模型就绪但还没产出运行回执
  - `model_pending` — 尚未登记可用 Champion/rolling/Challenger 模型工件
  - `success` — 最近一次回执新鲜且模型与 registry 一致
  - `stale` — 回执过期 / 模型已变更 / 调度失败
- **返回体**（逐项 `英文 — 中文`）：
  - `task_id` — 固定 `pv_tsc_predict`（任务 ID）
  - `pipeline` / `slot` — 固定 `pv_tsc`（管线 / 槽位）
  - `state` — 四态之一（运行状态）
  - `reason` — 状态归因（机器可读原因串）
  - `checked_at` — 本次判定时刻（UTC）
  - `status_file` — 固定回执相对路径（项目根相对）
  - `cron_expr` — 该任务 cron 表达式
  - `stale_after_seconds` — 判定过期的秒阈值
  - `model.artifact_registered` — 是否已登记模型工件
  - `model.source` — 模型来源（`champion`/`rolling_detect_model`/`challenger`/`latest_candidate`）
  - `model.model_candidate_id` — 模型候选 ID
  - `model.registry_version` — registry 版本
  - `scheduler_task.last_execution_time` / `last_result` — 调度器登记的上次执行时间 / 结果
  - `freshness.updated_at` / `age_seconds` / `is_stale` / `model_matches_current` — 回执时间 / 距今秒数 / 是否过期 / 模型是否与当前一致
  - `last_run.*` — 上次运行摘要（`outcome`/`devices_processed`/`points_detected`/`batch_ids`/`review_ids`/`model_source`/`model_candidate_id` 等）

### 3.2 审核会话 context 新增字段（`_create_prediction_review_session`，TSC 分支）

- 单元级：`n_windows`（窗口数）、`per_window_predictions`（逐窗标签）、`per_window_details`（逐窗起止/标签/置信度）、`aggregation`（聚合方式）、`model_name`（模型名，MultiRocket）、`model_window_config`（训练窗口/步长契约）、`model_ref`/`model_source`/`model_role`/`model_candidate_id`（模型引用与角色）。
- 会话 `prediction_context`：`review_kind = "tsc_device_day_review"`、`detection_date`（检测业务日）、`model_source`/`model_role`/`model_candidate_id`。
- **粒度约定**：`prediction_granularity` 对 TSC 仍为 `"day"`（槽位与输出粒度是不同概念，不新增 `"tsc"` 粒度）。

### 3.3 观测只读标记

- `GET /api/slot-datasets/observability/status?slot=pv_tsc` 与 `.../calendar?slot=pv_tsc` 返回 `readonly: true`。
- 前端据此在时钟条/日历双重防御，禁用演示推进、重置、手工补检。
- 对只读槽的写操作（如 `manual-detect`）后端返回 **HTTP 422**（`code = read_only_slot`）。

---

## 4. 验证结果

### 4.1 已验证

- 后端 `py_compile`（5 个改动文件）：通过（EXIT=0）。
- 后端 focused pytest（conda `cp_web`），共 **62 passed**：
  - `test_annotation_candidate_review` / `test_review_admission_units` / `test_observability_calendar_window` / `test_slot_product_scheduler` / `test_cumulative_ledger` → 23 passed
  - `test_tsc_pipeline` / `test_g11_labeling_workflow` / `test_g10_clustering_confirm` / `test_train_source` → 22 passed
  - `test_pv_prediction_cursor_fingerprint`（`_create_prediction_review_session` 签名变更回归）→ 17 passed
- 前端 `npm run build`（`tsc && vite build`）：通过（EXIT=0）。仅既有 Tailwind「No utility classes」与 chunk >500kB 警告。

### 4.2 端到端 API 验证（见 §5，随本次交付执行）

### 4.3 未验证 / 需人工确认

- 浏览器 UI 逐控件点击（无浏览器自动化能力）：见 §6 人工点击清单。
- 真实 TSC 模型 + 数据驱动的完整"检测→打标→回流→冻结→重训"闭环（依赖已登记的 MultiRocket 工件与数据水位）。

---

## 5. 端到端（API）验证记录（2026-09-03，后端 8080 + 前端 3001）

环境：`conda cp_web` 起 `uvicorn main:app --port 8080`（DB health = healthy, mysql）；前端 dev server 已在 3001，`/api` 代理到 8080。以下为真实响应要点：

| 检查 | 端点 | 结果 | 判定 |
|---|---|---|---|
| run-status 四态 | `GET /api/scheduler/tasks/pv_tsc_predict/run-status` | `state=model_pending`、`reason=no_registered_model_artifact`、`cron_expr=0 4 * * *`、`model.artifact_registered=false`、`freshness.is_stale=false`、带 `scheduler_task.live_*` | ✓ 四态合同正确（尚无 TSC 模型故为 model_pending） |
| 观测只读 | `GET /api/slot-datasets/observability/status?slot=pv_tsc` | `readonly=true`、`demo=false`、`progress.total_days=null` | ✓ readonly + total_days 可空 |
| 日历只读 | `GET /api/slot-datasets/observability/calendar?slot=pv_tsc` | `readonly=true`；16 设备 × 7 日按 288 点完整度网格 | ✓ readonly 透传 |
| 只读写拒绝 | `POST /api/slot-datasets/observability/advance-day {slot:pv_tsc}` | HTTP **422**（`read_only_slot`） | ✓ |
| 只读写拒绝 | `POST /api/slot-datasets/observability/manual-detect {slot:pv_tsc}` | HTTP **422**（`read_only_slot`） | ✓ |
| 演示拒绝 | `POST /api/slot-datasets/mock-gold-review {slot:pv_tsc}` | HTTP **400**（`invalid_slot`：loop demo 仅支持双槽） | ✓ 合理拒绝 |
| 审核队列三槽 | `GET /api/iterative-labeling/review-sessions/candidate-queue?slot=pv_tsc` | `{groups:[],count:0}` | ✓ 识别 pv_tsc，空队列（尚无检测） |
| 累计账本三槽 | `GET /api/slot-datasets/cumulative-ledger?slot=pv_tsc` | `{events:[],freeze_versions:[]}` | ✓ 识别 pv_tsc，空账本 |
| 浏览器网络路径 | `GET http://127.0.0.1:3001/api/.../run-status` 与 `.../observability/status` | 经前端 `/api` 代理返回同上 `state=model_pending`、`readonly=true` | ✓ UI 实际请求链路可达 |

结论：本次交付的后端契约改动（run-status 四态、readonly、total_days 可空、只读写 422、三槽队列/账本）在真实服务上全部符合预期。`model_pending` 是当前无已登记 MultiRocket 工件的正确状态；登记 Challenger 工件并跑一次 `pv_tsc_predict` 后应转入 `no_run_yet`→`success`。

---

## 6. 人工 UI 点击清单（起环境后逐项确认）

启动：`bash start-dev.sh`（后端 8080 + 前端 5173）。

1. **人工审核**（`/iterative-labeling?tab=review`）：场景下拉可选 `时序分类 pv_tsc`；待审检测组/审核会话两卡各自独立加载，制造后端错误时显示错误+重试而非空态；TSC 无"推进演示下一天"。
2. **审核工作台**（打开一条 pv_tsc 会话）：出现「时序分类诊断（MultiRocket 设备日）」证据卡，含设备日最终标签、目标业务日、模型/角色（Challenger）、window/stride、聚合方式、窗口数、逐窗明细表。
3. **累计训练**（`/datasets/cumulative-training?slot=pv_tsc`）：三槽文案；读取失败显示错误+重试；切槽后 cutoff 清空；冻结按钮有 loading。
4. **精度运营**（`/accuracy-operations` 选 pv_tsc）：显示 run-status 四态卡 + 只读日历 + strict 指标去处指引；无 mock 点曲线。
5. **模型部署**（`/algorithm-deployment?slot=pv_tsc`）：无"设为生产/推进演示/按 mock 精度设为生产"按钮；有"冻结并训练/登记为 Challenger/立即触发检测"；候选角色显示 Challenger；训练评估卡显示 Macro-F1/Balanced Acc/strict 划分/生产合同。
6. **调度观测**（`/algorithm-deployment` 调度 Tab 选 pv_tsc）：四态运行状态卡（状态/原因/模型来源/候选 ID/registry 版本/回执时间/新鲜度）；日历与时钟条只读，无演示推进/补检。
7. **工作流编辑器**（打开 pv_tsc 训练模板）：可训数据集选择器识别 `pv_tsc` slot。

---

## 7. 风险与后续

- annotation-candidate 路径的逐窗证据取决于候选是否携带 `per_window_details`；调度直建会话已带全，纯候选历史批次可能只剩设备日结论（证据卡退化为提示，不报错）。
- `PvFaultClassificationMetrics`/`SlotAccuracyMetricsCard` 为三槽共用，新增 Balanced Acc 列在 day/point 缺字段时显示"—"，非破坏。
- run-status 四态与 readonly 依赖后端固定接口，建议起环境后确认前端真实拿到四态与只读标记。
<!-- @AI_GENERATED: end -->
