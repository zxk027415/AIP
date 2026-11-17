<!-- @AI_GENERATED -->
# Implementation Plan: pv-three-chain-product-validation

## Overview

本计划在现有 Python / FastAPI 后端与 TypeScript / React 前端中实现光伏三链**产品建设**。交付主线是项目工作台（**领域无关的壳 + 仅光伏一个解决方案适配器**，见 design §11 / §11.5）、数据接入、逐页交互体验、共享运行与治理 UX，以及 `pv_day` / `pv_point` / `pv_tsc` 三条路径的产品故事线；跨数据集浏览器验收是验收手段。负荷预测等后续领域只需注册新适配器，不在本计划内实现。

所有产品对象以 `project_id` — 项目 ID、`slot` — 产品路径槽位、`dataset_version_id` — 不可变数据版本 ID 为最小上下文；运行同时显式保存 `run_mode` — 运行目的 与 `run_domain` — 运行域。

**不在本计划范围内**：模型精度优化、超参调优、阈值调整、更换模型、新建配对比较引擎或逐 split 校准评测工作台。使用 `i_cal` — 期望电流参照 时仍需显式提交 `i_cal_contract` — 校准合同 与 `calibration_audit_id` — 校准审计 ID，但这只用于**只读诚实标注**，不构成新建评测能力。

自动化环境固定 `production_writes_authorized=false` — 未授权生产写入；实现只加固服务端门禁并使用 mock、Sandbox 或负向测试，不执行真实 Promote、滚动指针写入、历史 provenance 补写或人工真值制造。

每个任务标注对应 Design ID（见 `design.md` §29.3）与需求编号。

## Tasks

- [ ] 1. Establish project scope, legacy read-only compatibility, and guarded state access
  - _Design: D-SCOPE-01_

  - [ ] 1.1 Implement the shared project scope model and relative-path resolver
    - Create `backend-service/services/pv_projects/scope.py` — 项目上下文模型模块；其中 `ScopeContext` 接收 API path/query/body 中的项目、槽位和数据版本，输出供 handler、service 与 repository 共用的已校验 scope。
    - Create `backend-service/services/pv_projects/paths.py` — scoped 相对路径解析模块；拒绝缺失或非法项目、槽位和机器绝对路径，不把运行时绝对路径写回持久化结果。
    - Preserve `project_id=legacy` as an explicit compatibility value; never assign it as a default for a new request.
    - _Requirements: R1.1, R1.2, R1.5–R1.9, R13.1–R13.4, NFR1.1–NFR1.6, NFR2.5_

  - [ ] 1.2 Migrate storage access to scoped repositories while exposing slot-only data as legacy read-only views
    - Implement project-and-slot repository adapters for dataset, execution, review, cumulative events, snapshot, candidate, verification, registry, cursor, Sandbox and result objects; add an idempotent metadata/index migration without copying legacy records into new projects.
    - Treat `registry.json` — 当前模型指针登记文件 as the separate current-source record for Champion, Challenger, rolling detection pointer and version; partition new records by `(project_id, slot)` under relative configured storage, while slot-only files remain legacy read-only.
    - Keep `model_candidates.json` — 候选历史文件 distinct from current pointers, and keep `promotions_log.json` — 晋升审计日志 append-only; do not rewrite historical provenance or use either file to infer missing registry state.
    - Return an explicit current-project empty result when a scoped object does not exist; never read a same-slot legacy or other-project object as fallback.
    - _Requirements: R1.7, R1.10–R1.12, R3.4, R3.6–R3.9, R6.10, R9.6, R9.8, R13.1–R13.4, NFR1.1–NFR1.6_

  - [ ] 1.3 Add scoped API dependencies, response validation, and production-governance gates
    - Add FastAPI dependencies that re-read object scope server-side, echo project/slot/data-version fields, and return `reason_code` — 机器原因码、`message` — 中文原因、`next_action` — 最短下一步、`retryable` — 是否可原输入重试 and `correlation_id` — 诊断关联 ID on mismatch or blocked access.
    - Make `GET /api/pv-projects/{project_id}/slots/{slot}/registry` read-only and return `champion` — 当前生产模型、`challenger` — 当前挑战模型、`rolling_detect_model` — 下一轮检测模型、`registry_version` — 乐观锁版本、`updated_at` — 最后更新时间 and `note` — 人类备注.
    - Harden existing rolling-pointer and Promote handlers to validate `model_candidate_id` — 模型候选 ID、`verification_id` — 正式复验 ID、`expected_registry_version` — 调用方读取的登记版本、`set_as_production` — 是否同步登记生产模型 and `production_slot` — 生产目标槽位. If an authorized Promote eventually sets production, it must register the candidate's own `source_workflow_id` — 来源工作流 ID and `model_artifact_ref` — 相对模型工件引用, never a baseline template or cross-scope artifact.
    - Classify refusals distinctly as permission denied, business gate blocked, read-only, Sandbox-only or scope mismatch; block legacy writes, non-governable executions, missing provenance, cross-scope requests and non-formal evidence IDs before any registry or append-only audit mutation. Exercise these paths only with mock or negative tests.
    - _Requirements: R3.1–R3.9, R7.8–R7.12, R8.1–R8.9, R9.1–R9.10, R15.11, R15.12, NFR2.1–NFR2.6_

  - [ ] 1.4 Implement the frontend project scope guard and shared stage-state components
    - Create `frontend-sevice/src/contexts/ProjectScopeContext.tsx` — URL scope、请求代次与缓存生命周期组件, and `frontend-sevice/src/services/scopedApi.ts` — 响应 scope 二次校验客户端.
    - Preserve project, slot and data-version deep links; clear visible state, errors, caches and writable actions immediately on scope changes; discard late responses from an older request generation.
    - Implement the ten shared action states from design §22.1 (`initial_empty`, `loading`, `ready`, `waiting_human`, `blocked`, `insufficient_data`, `read_only`, `recoverable_failure`, `fail_closed`, `completed`) with Chinese reason, current value, threshold and next action; keep raw JSON in a secondary diagnostics drawer.
    - Reject rendering and writes when any response scope field is missing or mismatched, and expose a refresh-current-project action rather than retaining stale content.
    - _Requirements: R1.1, R1.3–R1.5, R1.8–R1.9, R2.1–R2.13, R11.3–R11.4, NFR3.1–NFR3.5, NFR4.2–NFR4.3_

  - [ ] 1.5 Write the property test for compound project/slot isolation and no legacy fallback
    - **Property `P-SCOPE-01` / `P-LEGACY-01`**
    - Generate two projects, all three slots and every scoped repository; assert that writes, reads, caches, late responses and API echoes cannot cross scope.
    - Generate missing/invalid/new-project scopes and assert fail-closed responses, no default project assignment and no legacy repository reads or writes.
    - **Validates: Requirements R1.1–R1.3, R1.5–R1.7, R13.1, R13.2, R13.4**
    - _Requirements: R1.1–R1.3, R1.5–R1.7, R13.1, R13.2, R13.4_

- [ ] 2. Build the project workbench, data onboarding, and readiness experience
  - _Design: D-STATE-01, D-DATA-01, D-UX-01_

  - [ ] 2.1 Implement empty-project lifecycle APIs and the domain-agnostic workbench shell
    - Add project create/list/overview services and UI; creation returns a new empty project without inherited review, cumulative, candidate, registry, cursor or result state, and "copy from existing project" copies structure only. The project list is cross-domain; each project stores its own `scenario_id` — 行业场景 and `solution_id` — 算法方案.
    - Implement the workbench shell as **domain-agnostic** per design §11: project context bar, lifecycle stage band, content area, next-step rail and §11.3 scope-clear; register isolated route modules under the domain-neutral `/projects/*` prefix (do not put a domain name in the path) for data, runs, models, operations, reviews, cumulative and validation pages so later tasks do not edit one shared page in parallel.
    - Add a single domain-neutral **"项目工作台"** top-level entry and the `/projects/*` routes to `frontend-sevice/src/components/MainLayout.tsx` — 全局导航与布局壳 without changing existing menu groups or items; do not name it "光伏故障项目" and do not add a per-domain entry.
    - Render each path lifecycle with current scope, computed stage, evidence summary and a single primary next action; keep the project list states for empty, loading, read failure, no-permission, name conflict and duplicate submit.
    - _Requirements: R1.1–R1.12, R2.1–R2.13, R13.2–R13.4, R13.23–R13.24, NFR3.4_

  - [ ] 2.1a Define the `SolutionCapabilityAdapter` interface and register the photovoltaic adapter only
    - Per design §11.5, define a `SolutionCapabilityAdapter` — 按 `solution_id` 提供某业务领域在工作台内差异化配置的适配器 interface exposing `paths`, `lifecycleStages`, `readinessContract`, `stagePanels`, `capabilities` and `stateVocabulary`; the shell must consume only this interface and contain no `if (solution === 'pv_fault')`-style branch.
    - Register exactly one adapter in this spec: the photovoltaic fault-diagnosis adapter with paths `pv_day` / `pv_point` / `pv_tsc` and the six-stage lifecycle. Do not implement a load-forecasting adapter or any load-forecasting business here.
    - When a project's `solution_id` has no registered adapter, the workbench shows "该解决方案尚未接入工作台" instead of falling back to the photovoltaic config or crashing.
    - _Requirements: R1.1, R1.2, R1.4, R2.1, R2.5_

  - [ ] 2.2 Apply the wrap-first component ownership plan from design §11.4
    - Wrap, do not rewrite, the existing working panels: embed `SlotLabelProposalReviewPanel.tsx` — 三槽提案审核 as the review evidence area, `AccuracyOperationsPage.tsx` — 三路径精度面板分发 and `PvTscAccuracyOpsPanel.tsx` — TSC 运行与候选评估 as read-only accuracy/observation blocks, `SlotDeployedModelPanel.tsx` — 已部署模型与治理入口 and `ModelPathManager.tsx` — Champion / Challenger 路径模型管理 inside the governance page, and `CumulativeTrainingLedgerPage.tsx` — 累计入账与 freeze as the cumulative content.
    - Keep `IterativeLabelingListPage.tsx` — 标注工作台与三槽审核 and `AlgorithmDeploymentPage.tsx` — 部署治理总入口 as compatibility pages that accept `project_id` / `slot` / `dataset_version_id` deep links; keep `WorkflowEditorPage.tsx` — 工作流画布编辑 a separate page reached by deep link with scope passthrough.
    - Build new only where no implementation exists: project list/create, data onboarding wizard, overview lifecycle matrix and the shared run center. Treat the `pv_point` session page as a reorganization of existing replay/cursor/outcome/alert data sources, not a new data path.
    - Do not extract a shared component until at least two pages consume the same state contract; do not create a parallel duplicate of any panel listed above.
    - _Requirements: R1.1, R1.4, R2.1–R2.5, R5.5, R10.6_

  - [ ] 2.3 Implement CSV/Parquet upload, platform-asset selection and authorized connector ingestion
    - Create scoped dataset APIs and services returning `dataset_id` — 数据资产 ID and bounded previews; browser requests must not accept server filesystem paths.
    - Persist `asset_id` — 平台资产 ID or `connector_id` — 连接器 ID plus logical object description, never credentials, tokens, connection URLs or machine mount paths.
    - Persist resumable materialization task IDs and status for long connector jobs; cover upload progress, cancel, parse failure, authorization failure and timeout states.
    - _Requirements: R13.5, R13.7, R13.25, NFR1.1–NFR1.5, NFR4.1–NFR4.3_

  - [ ] 2.4 Implement field mapping, dataset profiling and immutable version publication
    - Add profile schemas and wizard UI for time/timezone/frequency/duplicates/late points; site/device/branch/value/`i_cal`; units/scales/missing policy; label dictionary, unknown policy and label granularity.
    - Publish a new `dataset_profile_id` — 数据映射与画像版本 ID and `dataset_version_id` with relative `artifact_ref` — 工件引用 and immutable content digest; mapping changes create a new profile/version rather than mutating the original.
    - Persist profile facts for row/time/entity coverage, actual discrete dates, sampling completeness, maximum gap, units, missing/outliers, class support and path-representation feasibility; present each fact as fact, impact and fix action.
    - Explain `i_cal` as an expected-current reference rather than ground truth, and mark `rated_power_kw` as auxiliary metadata when no verified current-scale contract exists.
    - _Requirements: R13.5–R13.14, R13.26, R15.9, NFR1.1–NFR1.6_

  - [ ] 2.5 Implement three-path readiness evaluation and UI
    - Implement `PathReadinessEvaluator` — 读取不可变版本与画像并分别输出三路径状态、事实、阻断、允许模式和下一步的服务.
    - Return one of `ready`, `experiment_only`, `needs_mapping`, `needs_labels`, `insufficient_data` or `unsupported` per slot, plus `facts`, `blockers`, `allowed_run_modes`, a backend-selected `primary_blocker` — 首要阻断 and `next_action`.
    - Echo project, slot, dataset profile and dataset version; explain that ready is not production/candidate/Promote eligibility and keep production disabled for experiment-only or blocked states; mark readiness stale when profile or path contract changes.
    - _Requirements: R13.13–R13.21, R13.23–R13.27, R14.7–R14.9, R14.14–R14.15, R14.23–R14.25_

  - [ ] 2.6 Apply the visual, responsive, accessibility and copy specification to shared shell components
    - Implement one primary action per region, restrained accent usage, dense tables instead of card walls, skeleton loading, teaching empty states and inline error with retry plus diagnostics.
    - Implement the 1440 / 1280 / 768 / sub-768 behaviors from design §28.2 without hiding scope, blocking reasons or high-risk impact text.
    - Ensure WCAG AA contrast, keyboard reachability, visible focus, focusable disabled reasons, table caption/headers, chart text summaries, `aria-live` for long tasks and `prefers-reduced-motion` support.
    - Create `frontend-sevice/src/pv-fault/copy/stateVocabulary.ts` — 集中状态文案模块 holding the display copy for the ten action states, the cross-cutting `CANCELLED` / `STALE` / `BACKEND_RECORD_MISSING` markers, the five disabled-reason types, the six readiness statuses and the stage names; pages reference keys instead of inline literals, and the key structure mirrors a future `pvFaultProject` i18n namespace.
    - Branch only on `reason_code` or state enum names, never on Chinese display copy. Deliver this surface as Chinese-only per design §28.4 and do not modify `locales/zh.json` or `locales/en.json` in this phase.
    - _Requirements: R2.2–R2.4, NFR3.1–NFR3.8_

  - [ ] 2.7 Write the property test for immutable dataset-version lineage
    - **Property `P-LINEAGE-01`**
    - Generate published versions and downstream execution/Sandbox/review/snapshot/candidate/evidence objects; assert identical scope/profile lineage, relative refs, stable content digests and fail-closed registration on digest mismatch.
    - **Validates: Requirements R6.2, R7.1, R7.2, R11.2, R13.5, R13.6, R15.2, R15.3**
    - _Requirements: R6.2, R7.1, R7.2, R11.2, R13.5, R13.6, R15.2, R15.3_

  - [ ]* 2.8 Add onboarding API/component integration tests
    - Test CSV, Parquet, asset and connector flows through preview, mapping, profile, immutable publication and readiness; include malformed mapping, device-day-to-point truth rejection, republish and task-resume cases.
    - Assert response scope, relative refs, digest immutability, secret exclusion and no legacy fallback.
    - _Requirements: R1.2–R1.9, R13.5–R13.27, NFR1.1–NFR1.6, NFR4.1–NFR4.4_

- [ ] 3. Build the shared preflight and run center
  - _Design: D-RUN-01, D-STATE-01_

  - [ ] 3.1 Implement project workflow creation, data binding and execution preflight
    - Allow creating a project workflow from a canonical template, copying an existing project workflow or starting from a blank canvas; bind a `dataset_version_id` to the load node and save a project workflow version without overwriting the shared template.
    - Implement preflight returning blocked / warning / passed with scope, required fields and representation, label granularity, sample/date/device/class coverage, workflow port and node contract, evaluation contract, resource estimate and whether only `experiment` is allowed.
    - _Requirements: R2.1–R2.4, R7.1, R7.6, R13.15–R13.19, R14.7–R14.8_

  - [ ] 3.2 Implement `ScopedWorkflowRunner` persistence and the run center UI
    - Extend `ScopedWorkflowRunner` — 将 scope、数据版本、运行模式 / 域和评测合同写入持久化 execution 的执行服务 so every run persists project, slot, data version, workflow, run mode, run domain, node status and governance eligibility.
    - Render a node timeline instead of a single running label; cover pending, running, success, failed, cancelled, page-refresh recovery, long silence and backend-record-missing states.
    - On success show the result destination: experiment artifact only, validation execution, governable candidate, labeling proposal, or prediction batch and pending review session.
    - Separate "retry with original input" (new attempt) from "modify and rerun" (new execution); never overwrite prior failure evidence.
    - _Requirements: R2.2–R2.13, R7.1–R7.3, R7.11–R7.12, NFR4.1–NFR4.5_

  - [ ]* 3.3 Add run center API/component tests
    - Test queued-to-terminal transitions, refresh recovery, duplicate submit prevention, cancel confirmation, log read failure, missing record and result-destination rendering.
    - Assert validation executions are rendered as non-governable and no test triggers production writes.
    - _Requirements: R2.2–R2.13, R7.3, R7.8–R7.9, R12.1–R12.2_

- [ ] 4. Build shared governance, review, and cumulative product surfaces
  - _Design: D-GOV-01, D-UX-01_

  - [ ] 4.1 Implement the four-layer model governance page
    - Organize the page as current detection model, pending candidates, experiment results (`governance_eligible=false`) and governance history; never collapse all artifacts into one ambiguous status column.
    - Use explicit action names: register as experiment result, start formal verification, set as next-round detection model, promote to production Champion.
    - Show verification interaction fields, `comparison_id` — 异步复验任务 ID polling, and, for multi-window verification, `eligible_for_pool` — 是否满足入池条件、`meets_score_margin` — 是否达到分差门槛、`meets_win_count` — 是否达到最少优胜窗口数、`score_margin`、`aggregate_method` 与 `min_windows_challenger_better`; non-multi-window verification keeps a summary-plus-sub-threshold structure from its own `evaluation_contract`.
    - Cover registry missing/invalid, empty candidates, polling failure, version conflict, no-permission, missing provenance and validation-not-governable states; after a successful write show the before/after pointer and whether the next detection model changed.
    - _Requirements: R3.1–R3.9, R8.1–R8.9, R9.1–R9.10, R2.5_

  - [ ] 4.2 Implement the unified review queue, review detail and accuracy surfaces
    - Partition the queue by `project_id` and `review_slot`; show source (proposal / detection batch / model-assisted labeling), unit granularity, data version, model, execution, progress and admission readiness.
    - Render path-specific evidence for day device-day curves, point raw points with causal context and TSC 288-grid window voting; keep verdict, review completion and complete-and-admit as three separate actions.
    - Cover queue empty/loading/failure, verdict save failure, concurrent re-judgement conflict, partial completion, admission disabled reasons and no-permission; color must not be the only signal.
    - Show accuracy with statistical scope, human truth count, class support, metric definition, data and model version and non-comparability reasons; render “未产出” instead of 0% when no valid truth exists, and never auto-trigger tuning or Promote from low scores.
    - _Requirements: R5.1–R5.10, R10.1–R10.7, NFR3.1–NFR3.5_

  - [ ] 4.3 Implement the three-layer cumulative and freeze surface
    - Show admitted events, frozen snapshots and training results as three distinct layers with lineage back to data version and review source.
    - Implement the freeze confirmation area with `reviewed_at_cutoff` — 审核时间上界, included/excluded events, label/device/date distribution, output snapshot type and duplicate-input detection; keep path-specific notes for point whole-day boxes, TSC 288×3 qualification and day device-day feasibility.
    - Cover no events, loading failure, freeze queued/running/failed/cancelled, idempotent hit and no-permission; after freeze allow creating a training run that still must pass candidate governance.
    - _Requirements: R6.1–R6.12, R2.5, R2.13_

  - [ ]* 4.4 Add governance/review/cumulative negative and component tests
    - Test candidate provenance gaps, validation execution rejection, verification binding mismatch, registry version conflict, cross-scope refusal, verdict-not-admitting, admission idempotency and freeze idempotency.
    - Assert no test performs real admission, freeze, candidate registration from non-governable evidence, formal verification, rolling-pointer write or Promote.
    - _Requirements: R5.7–R5.10, R6.4, R6.8–R6.10, R8.2–R8.9, R9.3, R9.7–R9.9_

- [ ] 5. Deliver the `pv_day` golden path without changing production quickval
  - _Design: D-PATH-01_

  - [ ] 5.1 Implement project-scoped day execution and Sandbox device-day replay
    - Run day experiment/validation jobs and full-device-day Sandbox results through the shared runner; expose accepted/rejected device-day counts, source/label distributions and relative artifacts.
    - Apply scoped review, inclusion, freeze and snapshot lineage guards; production-capable handlers require explicit authorization while tests use Sandbox/mock/negative paths only.
    - Preserve current production quickval predict as an explicit implementation fact; do not migrate or claim a dedicated day production graph.
    - _Requirements: R4.1–R4.2, R6.1–R6.4, R6.12, R7.1–R7.3, R13.6, R14.5–R14.8, R14.11_

  - [ ] 5.2 Wire the day workbench pages to shared components
    - Connect day routes to scoped APIs and the shared stage/governance/review/cumulative components; show workflow, execution and receipt evidence plus the quickval production fact and next action.
    - Distinguish no output, loading, failed/recoverable, Sandbox-only and completed states; never infer current model pointers from recent training or candidate history.
    - _Requirements: R2.1–R2.13, R3.1–R3.9, R4.2, R6.12, R10.1–R10.7_

  - [ ]* 5.3 Add day API/component/Sandbox tests
    - Test scoped day execution lineage, full-device-day representation, quickval fact rendering, missing receipt, cumulative/freeze guards, absent-truth accuracy and Sandbox/production isolation.
    - _Requirements: R4.2, R6.3–R6.4, R6.8–R6.12, R7.1–R7.3, R10.1–R10.7, R14.2–R14.5_

- [ ] 6. Converge the `pv_point` run session experience
  - _Design: D-PATH-01, D-STATE-01_

  - [ ] 6.1 Implement event-time point replay and isolated Sandbox state
    - Extend `SandboxRuntime` — 按 `(project_id, sandbox_id, slot)` 保存隔离水位、cursor、审核和结果的运行域服务 with pending point, committed history, cursor and outcome state.
    - Process real points in event-time order; each prediction may read only committed history strictly before the current point. Sandbox reset replaces only the selected Sandbox state.
    - Preserve the current `SeqDailyStrategy` — 点路径逐点 replay 策略 direct-predictor fact; do not wrap point replay as a daily batch or claim frozen workflow provenance.
    - _Requirements: R4.1, R4.3–R4.4, R14.2, R14.5, R14.10, R14.12, NFR4.1–NFR4.4_

  - [ ] 6.2 Implement the unified point run session page and action contract
    - Merge replay session, binding, cursor, outcome and alerts into one page: session source (real replay or `loop_demo` demonstration), current cursor, data version and run domain on top; point timeline and causal window in the middle; pending point, outcome and alerts on the right.
    - Implement start, pause, single step, advance 10 points, advance 50 points, auto and stop; expose Sandbox-only reset with target `sandbox_id` — Sandbox 实例 ID, current cursor, deleted isolated results and an explicit "production unaffected" statement.
    - Restore sessions by `project_id + sandbox_id + slot` after refresh; on cursor conflict return the latest cursor and offer refresh-and-continue or a new Sandbox instead of overwriting.
    - Report prediction outcome and alert delivery separately, and label `loop_demo` as demonstration feeding that does not write the cumulative ledger.
    - _Requirements: R2.1–R2.13, R4.3–R4.4, R14.10, R14.12, NFR3.1–NFR3.5, NFR4.5_

  - [ ] 6.3 Enforce point-label readiness and freeze boundaries
    - Return supervised `needs_labels` for device-day-only labels while allowing unlabeled causal Sandbox replay; reject using device-day labels as point/interval truth or supervised point accuracy.
    - Keep point/interval label mappings valid, reject incompatible granularity, and filter whole-day clustering boxes from point freeze inputs.
    - Persist source data version and profile lineage for every point Sandbox result without emitting production evidence.
    - _Requirements: R6.5, R6.10–R6.11, R13.6, R13.10–R13.11, R13.15–R13.19, R14.12, R15.10_

  - [ ] 6.4 Write the property test for point causality
    - **Property `P-POINT-01`**
    - Generate ordered points and arbitrary future mutations; assert the current result depends only on prior committed history, cursor advances only after a committed outcome, reset is Sandbox-local and device-day labels never enter truth or metrics.
    - **Validates: Requirements R4.3, R4.4, R14.10, R14.12, R15.10**
    - _Requirements: R4.3, R4.4, R14.10, R14.12, R15.10_

- [ ] 7. Complete the `pv_tsc` canonical labeling story and read-only production controls
  - _Design: D-PATH-01_

  - [ ] 7.1 Implement the canonical TSC labeling product entry
    - Provide a primary action on the data page for `needs_labels` TSC versions that launches `workflow-pv-tsc-label-v1.json` — TSC 模型辅助打标工作流 directly, without routing users to the day/point labeling tab.
    - Run the canonical canvas through scoped preflight/execution, persisting `tsc_predict → emit_tsc_label_proposal` execution and proposal lineage; a failure produces no proposal (fail-closed).
    - Label the historical KMeans REST path as `labeling_mode=shortcut` — 快捷聚类模式 with an explicit "not canonical TSC model-assisted labeling" note; `preferred_labeling_workflow_id` — 推荐的 canonical 打标工作流 ID stays metadata only.
    - Cover data-selection empty, no available model, preflight blocked, running timeline, execution failure with recovery, empty or partial proposals, lineage conflict and no-permission; until real browser E2E passes, keep the page marked "TSC canonical 打标 UI 待验收".
    - _Requirements: R5.1–R5.10, R11.5–R11.7, R14.2–R14.5, R14.13, R14.18–R14.20_

  - [ ] 7.2 Implement strict-10, cumulative and metric evidence adapters
    - Persist and display the 288×3 value/`i_cal`/measurement-mask contract, strict date × device isolation, 10 repeats, fixed-label-space Macro-F1, the `production_contract_valid` distinction and the 35 discrete trusted dates.
    - Preserve queued/running/completed/failed/cancelled execution history plus dataset/snapshot/artifact/evaluation lineage; data insufficiency must not relax split isolation or repeat count.
    - Keep `exec-validation-d741dc207593` — 已完成 strict-10 的 TSC validation execution and all validation executions non-governable; show TSC freeze qualified/rejected device days, channels and class distribution without describing 1.05M rows as continuous date coverage.
    - _Requirements: R6.2, R6.6–R6.7, R6.10–R6.11, R7.1–R7.12, R10.1–R10.5, R14.7–R14.8, R14.13_

  - [ ] 7.3 Enforce and render TSC production observability as read-only
    - Return read-only production status with device-day, multi-window and scheduler receipt evidence; a missing current receipt stays “未产出”, and a failed day must not advance the production cursor.
    - Reject manual advance/detect and all production observability writes before waterline, cursor, review or accuracy mutation; never borrow evidence from another project, slot, device, date or legacy state.
    - _Requirements: R4.5–R4.8, R10.1–R10.7, R11.1–R11.4, NFR2.1–NFR2.6_

  - [ ] 7.4 Harden TSC candidate, verification, pointer and Promote gates
    - Require complete candidate provenance, a same-scope/same-candidate formal `passed=true` verification and a matching registry version; reject validation executions, offline/product evidence IDs and historical TSC candidates with missing provenance.
    - Keep missing provenance visible and immutable; do not synthesize source workflow/execution/snapshot fields or force a historical candidate through verification.
    - Add only service guards and mock/negative tests for rolling pointer and Promote; do not execute real writes or alter append-only audit history.
    - _Requirements: R3.3–R3.9, R7.8–R7.12, R8.1–R8.9, R9.1–R9.10, R15.5, R15.11, R15.12_

  - [ ]* 7.5 Add canonical TSC Sandbox browser E2E
    - Automate project/slot/data-version selection, canonical workflow preflight and run, proposal review, strict evidence and production read-only states; assert shortcut labeling stays distinct.
    - Capture relative screenshots, route/scope, console/page errors and 401/403/5xx summaries; compare production proposal/cursor/review/accuracy source hashes before and after.
    - _Requirements: R4.5–R4.8, R5.1–R5.10, R7.4–R7.10, R11.1–R11.10, R14.13, R14.17–R14.20_

  - [ ] 7.6 Write the property test for three-path semantics and canonical/shortcut separation
    - **Property `P-PATH-01` / `P-TSC-01`**
    - Assert day quickval fact, point direct causal replay, point device-day-label `needs_labels`, TSC production write rejection, canonical-versus-shortcut distinction and validation execution non-governability.
    - **Validates: Requirements R4.2–R4.6, R5.2–R5.4, R7.9, R14.5, R15.10**
    - _Requirements: R4.2–R4.6, R5.2–R5.4, R7.9, R14.5, R15.10_

- [ ] 8. Automate cross-dataset acceptance, isolation, and read-only offline evidence
  - _Design: D-SANDBOX-01, D-EVIDENCE-01_

  - [ ] 8.1 Implement cross-dataset validation batches and evidence aggregation
    - Implement `CrossDatasetValidationService` — 接受共享版本或每路径独立版本分配并聚合三路径 readiness/execution/Sandbox/lineage 的服务.
    - Create/read batches with a distinct product-validation ID and `governance_effect=none`; require each path to be covered by a non-built-in data version while allowing unsupported paths to use another version in the same batch.
    - Persist `ValidationEvidenceBundle` — 相对路径验收证据包 with project/slot/version assignments, readiness, executions, browser evidence, SHA256 state, isolation conclusion and explicitly skipped production actions; return PASSED / FAILED / BLOCKED per design §27.2, where low accuracy alone must not fail a valid product-flow result.
    - _Requirements: R13.20–R13.22, R14.1, R14.4, R14.14–R14.16, R14.21–R14.26_

  - [ ] 8.2 Implement the SHA256 zero-pollution and A/B scope guard
    - Enumerate each applicable production candidate, registry, proposal, cursor, review, cumulative, snapshot, accuracy and promotion source by relative ref; record hashes or explicit `MISSING` / `NOT_APPLICABLE` status before and after experiment/validation/Sandbox flows.
    - Keep all Sandbox state under `(project_id, sandbox_id, slot)` and prove project B cannot read or write project A at the same slot; shared frozen source refs must not imply shared business state.
    - Reject any unapproved production side effect and any evidence-type or ID substitution before mutation.
    - _Requirements: R1.7–R1.12, R11.5–R11.10, R13.1–R13.4, R14.2–R14.4, R14.10, R14.21–R14.22, R15.11–R15.12, NFR2.1–NFR2.6_

  - [ ] 8.3 Register and explain read-only offline benchmark evidence
    - Add a read-only benchmark evidence registration and read API with `evidence_type=offline_benchmark_evidence` and governance effect none; verify each declared source file's content digest and relative ref, bind them to an immutable `benchmark_evidence_version` — 不可变离线证据版本, and keep frozen artifacts untouched.
    - Fail closed as blocked on missing, unreadable, digest-mismatched or unresolvable sources without creating a valid version or deriving any conclusion.
    - Require an explicit `i_cal_contract` with a resolvable `calibration_audit_id` and persist both; mark `leaky_device_ical` permanently as leakage upper bound, diagnostic experiment and non-governable; block unknown or conflicting contracts without falling back to a default.
    - Render a compact summary panel: evidence type, governance effect none, contract and leakage labels, `metric_applicability` — 指标适用原因 with N/A instead of 0, `repeatability_status` — 重复性状态 as `not_reverified` when fewer than two independent versions exist, and links to the existing frozen report. Do not build a paired-comparison engine, per-split audit workbench or calibration fitting capability.
    - _Requirements: R7.11, R10.1–R10.6, R13.5–R13.6, R15.1–R15.9, R15.11–R15.12, NFR1.1–NFR1.6_

  - [ ]* 8.4 Add the cross-dataset Playwright acceptance suite
    - Start from empty project A, onboard non-built-in shared or per-path versions, profile/publish/readiness/preflight/run the three paths, exercise Sandbox review, then create project B and repeat a same-slot scenario.
    - Assert scope clearing and late-response rejection; cover applicable loading/empty/error/insufficient/mismatch/disabled/read-only states; archive relative screenshots, routes, scope IDs, console/page errors, network failures and SHA256 evidence.
    - Keep production writes unauthorized and test admission, freeze, candidate, formal verification, rolling pointer and Promote only through disabled UI, mock, Sandbox or negative API calls.
    - _Requirements: R11.1–R11.10, R13.3–R13.7, R13.15–R13.24, R14.14–R14.26, NFR2.1–NFR2.6_

  - [ ] 8.5 Write the property tests for zero pollution and non-escalating governance
    - **Property `P-SANDBOX-01` / `P-GOV-01` / `P-GOV-02`**
    - Generate run modes/domains/scopes and assert persistent execution evidence, Sandbox-only state writes, non-governable validation and identical applicable production hashes.
    - Generate offline benchmark, product validation and formal verification identifiers/types; assert immutable type identity, rejected substitutions and no candidate/verification/registry/pointer/Promote mutation without a valid authorized formal path.
    - **Validates: Requirements R4.6, R7.8, R8.2, R8.5–R8.6, R9.7, R11.5–R11.6, R14.1–R14.4, R15.5, R15.11–R15.12**
    - _Requirements: R4.6, R7.8, R8.2, R8.5–R8.6, R9.7, R11.5–R11.6, R14.1–R14.4, R15.5, R15.11–R15.12_

- [ ] 9. Run focused regression, accessibility, build and repository integrity checks
  - _Design: D-UX-01_

  - [ ]* 9.1 Run backend syntax, focused pytest and property suites
    - Use the `cp_web` environment to run `py_compile` on changed Python modules and focused API/service/integration/property tests for scope, onboarding, run center, governance, day, point, TSC, cross-dataset and evidence guards.
    - Require zero errors and separate pre-existing warnings from newly introduced warnings.
    - _Requirements: R12.1–R12.3_

  - [ ] 9.2 Verify page-state completeness, accessibility and TypeScript across the workbench
    - **Property `P-UX-01`**
    - Run the affected Vitest/Playwright suites plus `npx tsc --noEmit --pretty false`; verify route registration, scope changes, the ten action states, disabled-reason classification and evidence-type rendering.
    - Assert every one of the ten pages in design §23 exposes its applicable empty, loading, error, disabled and completed states, that each page state resolves to one of the ten §22.1 enum names rather than a page-invented state, and that long tasks resume from persisted state after refresh rather than frontend memory.
    - Assert state, disabled-reason, readiness and stage copy is read from the central vocabulary module so the same state reads identically across pages, and that no branch depends on Chinese display copy.
    - Run axe or an equivalent automated audit plus keyboard main-journey, focus, `aria-live`, reduced-motion and viewport matrix checks for 1440 / 1280 / 768 widths.
    - Require zero type/test errors and preserve relative screenshot/evidence paths.
    - **Validates: Requirements R2.1–R2.13, R11.3–R11.4, NFR3.1–NFR3.8, NFR4.1, NFR4.5**
    - _Requirements: R2.1–R2.13, R11.1–R11.10, R12.1–R12.3, NFR3.1–NFR3.8, NFR4.1, NFR4.5_

  - [ ] 9.3 Run the frontend production build
    - Run `npm run build` in `frontend-sevice`; require zero build errors and classify known Tailwind/chunk warnings separately from new warnings.
    - _Requirements: R12.1–R12.2_

  - [ ] 9.4 Run automated relative-path, AI-marker and diff integrity checks
    - Check changed authored files for absolute persisted paths, paired non-nested `@AI_GENERATED` markers, unresolved imports/routes and malformed evidence refs; then run `git diff --check`.
    - Fail the task on any new violation without cleaning, resetting, formatting or overwriting unrelated dirty-worktree changes.
    - _Requirements: R11.2, R11.7, R12.3–R12.5, R12.9, NFR1.1–NFR1.6_

- [ ] 10. Unify the platform journey spine and cross-module context continuity
  - _Design: D-JOURNEY-01（design.md §31–39）_
  - **范围提示**：本任务是平台级地基，作用域超出 pv 三链。10.1–10.3 必须在任务 2 的工作台落地前完成，否则 pv-fault 工作台会成为第三条互不相认的旅程。

  - [ ] 10.1 Collapse the two competing "scene" concepts into one four-layer spine
    - Fix the four layers per design §32: `scenario_id` — 行业场景, `solution_id` — 算法方案, `slot` — 诊断路径, `project_id` — 交付实例; `project_id` is orthogonal and selects one `(scenario, solution, slot)` triple.
    - Stop presenting `slot` as "场景" in the UI: change the user-facing wording in `frontend-sevice/src/config/slotProductConfig.ts` — 产品线 slot 值域与工作流映射 to 诊断路径, and update every slot selector label. URL and API keep `slot` unchanged.
    - Establish a data-level solution→workflow link: add `workflow_id` to the solution's `default_workflows`, or make the backend actually read a scenario/solution→workflow mount table. Until the link exists, render the workflow tags on solution cards as non-clickable with an explicit "未关联具体工作流" note instead of decorative clickable-looking tags.
    - Persist `solution_id` on the workflow itself alongside the existing `scenario_id` so ownership stops being inferred.
    - _Requirements: R1.1, R1.2, R2.1, R2.5_

  - [ ] 10.2 Implement the context contract: one name per concept, carry / show / pass through
    - Normalize query parameter names to `scenario_id`, `solution_id`, `slot`, `project_id`, `workflow_id`, `dataset_version_id`; remove the duplicate `?scenario=` vs `?scene=` split and stop using `?template=` to mean a solution id.
    - Enforce the three rules from design §33.2: every navigation carries the resolved spine, every target renders what it received even if unused, and every target preserves unconsumed params for onward links.
    - Fix the parameter-dropping defects: make `/algorithm-dev/ops` preserve search or point directly at the real page; make the deployment page read `workflow_id` and spine params instead of only `slot` / `tab`; route the scene-detail `solution_id` into the solution filter rather than the free-text search box; replace the hardcoded `challenger` constant on the scene detail page with the current solution's own asset.
    - Add a redirect rule test: any compatibility redirect must preserve query string.
    - _Requirements: R1.1–R1.5, R1.8, R1.9, R2.1, R2.3_

  - [ ] 10.3 Add the route metadata table, journey context store and context bar
    - Replace the ~60-line pathname ternary chain in `frontend-sevice/src/components/MainLayout.tsx` with a single route metadata table declaring title, group, breadcrumb parents, required/optional spine params and missing-context behavior; generate both the header title and breadcrumbs from it so pages stop hand-rolling their own.
    - Create `journeyContextStore` following the proven pattern of `frontend-sevice/src/stores/workflowRunNavStore.ts` — 跨页运行上下文与返回入口: hold `scenario_id` / `solution_id` / `project_id` / `slot` plus a recents list, persisted to `localStorage` like the existing sidebar width.
    - Implement the shared context bar rendering `行业场景 › 算法方案 › 项目 › 诊断路径` with per-segment navigate and in-place switch; switching clears downstream visible state per §11.3.
    - Resolve context by the §33.3 priority: URL → in-page selection → store → explicit empty state. Never silently default to a slot.
    - _Requirements: R1.1, R1.3–R1.5, R1.8, R1.9, R2.1, R2.8_

  - [ ] 10.4 Make workflow creation pre-fillable with three explicit modes
    - Extend the create wizard props with `initialScenarioId` / `initialSolutionId` and skip already-determined steps when entered with context from the scene detail page or algorithm management.
    - Offer three modes with distinct copy per design §35.3: create from the solution's recommended template (default), copy an existing workflow, or blank canvas; blank still requires confirming ownership so no unowned asset is produced.
    - Remove the six-scenario truncation in step one and make the list searchable; replace the "该场景下暂无可用模板" dead end with canonical templates, cross-scenario template search and blank creation.
    - Change the scene detail "进入工作流编排" action to open this wizard pre-filled instead of an empty canvas, and make the workflow editor read and display ownership with a one-click assign when missing.
    - _Requirements: R2.1–R2.3, R2.9, R13.2_

  - [ ] 10.5 Replace inferred lifecycle status with evidence-backed status
    - Remove `inferLifecycleStatus()` and `inferAutoresearchStatus()` keyword matching in `frontend-sevice/src/pages/AlgorithmManagementPage.tsx` — 算法资产总表与统计条 as the source of displayed status.
    - Derive lifecycle from the latest successful execution, governable-candidate existence and registry pointer; derive backtest/verification status from the AutoResearch candidate pool and verification queue; derive deployment status from the scoped registry `champion` / `rolling_detect_model`.
    - Until the real status endpoints exist, render `未知` with a reason and exclude those rows from the statistics strip; never display or count a guessed status.
    - Extend the management filters to 行业场景 + 算法方案 + 诊断路径 + 真实状态.
    - _Requirements: R2.5, R2.6, R3.1, R3.2, R10.1, R10.2_

  - [ ] 10.6 Fix reachability and eliminate dead ends
    - Make every journey-stage page reachable from an upstream page, not only the global menu; add entries so `/data-sources` and `/accuracy-operations` are reachable from scene detail, algorithm management or the project workbench.
    - Resolve the unreachable routes `/algorithm-solutions/accuracy` and `/algorithm-solutions/applications` by either adding a real entry or removing the route.
    - Give every empty, failed and read-only state at least one forward action; designate one canonical path per capability and make the duplicates query-preserving redirects.
    - Add cross-module back-references: deployment shows which workflow / execution / solution / scenario the current model came from, and accuracy operations can trace back to model, data version and review session.
    - _Requirements: R2.1, R2.3, R2.12, R3.1, R10.1_

  - [ ] 10.7 Build the efficiency layer: continue-last, recents, command palette
    - Add a home "继续上次" card showing the stored spine and stage with its primary action, plus a recents list; show only the scenario entry with guidance when there is no history.
    - Implement the command palette on `Ctrl+K` / `Cmd+K` for scenarios, solutions, workflows, projects and executions, grouped with their owning spine and including recent items; `Esc` closes and restores focus, arrows move the highlight while text focus stays in the input via `aria-activedescendant`, `Enter` runs the highlighted item.
    - Ensure every journey page URL fully encodes its context so a pasted link reproduces the same view.
    - Extend the existing single-task "返回运行中" float button into an expandable in-progress task list showing each task's spine.
    - _Requirements: R2.1, R2.12, NFR3.1–NFR3.5, NFR4.1, NFR4.5_

  - [ ]* 10.8 Add journey continuity tests
    - Assert parameter naming uniqueness, that every declared navigation carries the spine, that targets render received context, that unconsumed params survive onward navigation, and that every compatibility redirect preserves the query string.
    - Assert the three entry paths (scene-first, asset-first, resume) converge on an identical context bar for the same target object, and that in-place spine switching clears downstream state and discards late responses.
    - Assert no route is unreachable and no journey-stage page is menu-only; assert guessed status never renders when real status is unavailable.
    - _Requirements: R1.1–R1.5, R1.8, R1.9, R2.1–R2.3, R2.5, R2.6_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3", "1.4"] },
    { "id": 3, "tasks": ["1.5", "10.1"] },
    { "id": 4, "tasks": ["10.2"] },
    { "id": 5, "tasks": ["10.3"] },
    { "id": 6, "tasks": ["2.1", "2.1a"] },
    { "id": 7, "tasks": ["2.2", "2.3"] },
    { "id": 8, "tasks": ["2.4"] },
    { "id": 9, "tasks": ["2.5", "2.6"] },
    { "id": 10, "tasks": ["2.7", "2.8", "10.4"] },
    { "id": 11, "tasks": ["3.1"] },
    { "id": 12, "tasks": ["3.2"] },
    { "id": 13, "tasks": ["3.3", "4.1", "4.2", "4.3"] },
    { "id": 14, "tasks": ["4.4", "5.1", "6.1", "7.1", "10.5"] },
    { "id": 15, "tasks": ["5.2", "6.2", "6.3", "7.2", "10.6"] },
    { "id": 16, "tasks": ["5.3", "6.4", "7.3", "7.4", "10.7"] },
    { "id": 17, "tasks": ["7.5", "7.6", "10.8"] },
    { "id": 18, "tasks": ["8.1", "8.3"] },
    { "id": 19, "tasks": ["8.2"] },
    { "id": 20, "tasks": ["8.4", "8.5"] },
    { "id": 21, "tasks": ["9.1", "9.2", "9.4"] },
    { "id": 22, "tasks": ["9.3"] }
  ]
}
```

## Notes

- Tasks marked with `*` are optional automated tests in Kiro. Tasks 1.5, 2.7, 6.4, 7.6, 8.5 and 9.2 are intentionally **not** optional: they validate the isolation, lineage, causality, read-only, non-escalation and page-state red lines.
- Tasks 2.1 and 2.1a deliver a **domain-agnostic** project workbench (single "项目工作台" entry, `/projects/*` routes) plus the `SolutionCapabilityAdapter`; this spec registers only the photovoltaic adapter. Load forecasting is a future adapter and must plug in without editing the shell, routes, context bar or scope rules — do not implement it here, and if a load-forecasting domain is built out, give it its own spec that only adds an adapter.
- Task 2.2 is the wrap-first gate: existing working panels listed in design §11.4 must be embedded rather than reimplemented, and no parallel duplicate page may be created for them.
- Tasks 10.1–10.3 are the platform-spine gate and must land before task 2.1, otherwise the pv-fault workbench becomes a third disconnected journey. Task 10 is platform-wide in scope; if the journey is rolled out to other industry scenarios beyond pv-fault, give it its own spec rather than growing this one.
- Task 10.5 must precede any "recommended next step" feature: while lifecycle and backtest status are keyword guesses, guidance built on them amplifies the error. Showing `未知` is the required behavior until real status endpoints exist.
- Use repository-relative paths only. Runtime resolution may use project root, backend directory and current directory, but persisted contracts and evidence must never contain machine absolute paths.
- Wrap every AI-generated or AI-modified authored code block with the file type's paired `@AI_GENERATED` markers; do not annotate lock, binary, strict-schema or generated runtime files.
- Preserve the dirty worktree: read each target before editing and do not clean, reset, delete, reformat, commit or overwrite unrelated changes and artifacts.
- Validate only the affected backend/frontend scope plus the final type/build/static checks; record known warnings separately from regressions.
- Excluded from this plan: model accuracy optimization, hyperparameter tuning, threshold changes, model replacement, residual/ratio channels, and any new paired-comparison or calibration-fitting infrastructure.
- No task performs real admission/freeze truth creation, candidate registration from non-governable evidence, formal production verification, Promote, rolling-pointer mutation or historical provenance backfill.

<!-- @AI_GENERATED: end -->
