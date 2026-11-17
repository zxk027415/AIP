// @AI_GENERATED
/**
 * 项目工作台 API 客户端（pv-three-chain-product-validation）。
 *
 * 设计依据：design.md §12、§14、§26.2；requirements.md R1、R2。
 * 复用基础 axios 实例 `api`（baseURL `/api`，响应拦截器已返回 response.data）。
 */

import api from './api';

export interface ProjectSummary {
  project_id: string;
  project_name?: string;
  owner?: string;
  scenario_id?: string;
  solution_id?: string;
  read_only?: boolean;
  note?: string;
  registered_at?: string;
}

export interface CreateProjectRequest {
  project_name: string;
  owner?: string;
  scenario_id?: string;
  solution_id?: string;
  copy_from_project_id?: string;
  /** 创建时挂载的平台目录条目；先选数据集再推导路径。 */
  catalog_entry_id?: string;
  /** 挂载路径；缺省用条目 origin_slot / 唯一适用路径。 */
  mount_slot?: string;
}

export interface SlotLifecycleFacts {
  dataset_versions: number;
  executions: number;
  candidates: number;
  verifications_passed: number;
  rolling_model_set: boolean;
  reviews_pending: number;
  snapshots: number;
  cumulative_events: number;
}

export interface SlotLifecycle {
  project_id: string;
  slot: string;
  stage: string;
  stage_reason?: string;
  /** 该路径最新数据版本的 readiness（仅在按 readiness 判定阶段时返回）。 */
  readiness_status?: string | null;
  readiness_primary_blocker?: string | null;
  facts: SlotLifecycleFacts;
  primary_next_action: { action: string; href: string };
}

export interface MountedDatasetView {
  dataset_id: string;
  dataset_ref?: string | null;
  file_name?: string | null;
  source_kind?: string;
  catalog_entry_id?: string | null;
  display_name?: string | null;
  origin_slot?: string | null;
  applicable_slots: string[];
  workflows_by_slot: Record<string, Array<{
    project_workflow_id?: string;
    name?: string;
    workflow_kind?: string;
    source_template_id?: string | null;
    version?: number;
  }>>;
  templates_by_slot: Record<string, WorkflowTemplateSummary[]>;
  /** 累计快照随附的既有路径模型关联；普通数据为 null。 */
  model_inheritance?: ModelInheritanceResult | null;
}

export interface ProjectOverview {
  project_id: string;
  project_name?: string;
  scenario_id?: string;
  solution_id?: string;
  read_only: boolean;
  /** 项目启用的诊断路径（intent）；null=尚未确认。总览始终返回三条路径，不隐藏。 */
  enabled_slots?: string[] | null;
  paths: SlotLifecycle[];
  mounted_datasets?: MountedDatasetView[];
  path_templates?: Record<string, WorkflowTemplateSummary[]>;
  computed_at: string;
}

export interface CreateProjectResult extends ProjectSummary {
  empty_lifecycle?: boolean;
  /** 创建时一并挂载的结果；未选择目录条目时为 null。 */
  mounted?: MountCatalogResult | null;
  /** 服务端最终确认的挂载路径；未挂载时为 null。 */
  mount_slot?: string | null;
  next_action?: { action: string; href: string };
}

export interface ProjectListResult {
  projects: ProjectSummary[];
  total: number;
}

export type DatasetSourceKind = 'upload' | 'platform_asset' | 'connector' | 'catalog';

export interface DatasetAsset {
  dataset_id: string;
  project_id?: string;
  source_kind: DatasetSourceKind;
  status: string;
  logical_object?: string | null;
  logical_description?: string | null;
  file_name?: string | null;
  asset_id?: string;
  connector_id?: string;
  /** catalog 来源：真实数据相对引用（如 `slot_datasets/pv_day/snapshots/x.parquet`）。 */
  dataset_ref?: string | null;
  /** catalog 来源：平台数据集目录条目 ID（`dsc-…`）。 */
  catalog_entry_id?: string | null;
  content_digest?: string | null;
  /** 挂载回填：本次挂载产生的画像 / 数据版本 ID。 */
  dataset_profile_id?: string | null;
  dataset_version_id?: string | null;
  registered_at?: string;
}

export interface RegisterDatasetRequest {
  source_kind: DatasetSourceKind;
  file_name?: string;
  upload_ref?: string;
  asset_id?: string;
  connector_id?: string;
  logical_object?: string;
  logical_description?: string;
}

/** `POST /api/upload/file` 的返回（平台上传端点，落盘到 backend-service/data/uploads/）。 */
export interface UploadedFileInfo {
  file_id: string;
  filename: string;
  file_size: number;
  analysis?: Record<string, unknown>;
}

/** 平台上传端点实际接受的扩展名（后端 `api/upload.py` 白名单；**不含** .parquet）。 */
export const UPLOAD_ACCEPT = '.csv,.tsv,.xlsx,.xls';

/**
 * 由上传返回拼出平台相对引用（`registerDataset` 的 `upload_ref`）。
 * 后端保存为 `{file_id}{ext}`（ext 取小写），此处必须与之一致，否则预览 / facts 解析不到文件。
 */
export function uploadRefFromFileId(fileId: string, filename: string): string {
  const dot = filename.lastIndexOf('.');
  const ext = dot >= 0 ? filename.slice(dot).toLowerCase() : '';
  return `data/uploads/${fileId}${ext}`;
}

export interface DatasetPreview {
  project_id: string;
  dataset_id: string;
  source_kind: string;
  row_limit: number;
  columns: string[];
  preview_rows: unknown[];
  preview_available: boolean;
  note: string;
}

export interface DatasetListResult {
  project_id: string;
  assets: DatasetAsset[];
}

// ─── 平台数据集目录（数据集切片第 2b / 2c 步）───────────────────────────────
/** 「适用路径」判定：只看标签粒度口径，不看覆盖（覆盖由 coverage 独立报告）。 */
export interface CatalogApplicablePath {
  applicable: boolean;
  reason: string;
  label_granularity_detected: string;
  truth_granularity: string[];
}

/** 覆盖事实（软约束，不否决适用性）。 */
export interface CatalogCoverage {
  sufficient: boolean;
  gaps: string[];
  hint: string;
  thresholds: Record<string, number>;
}

/** 质量检测算出的覆盖事实（服务端读真实文件算出，非客户端传入）。 */
export interface CatalogFacts {
  source_ref?: string;
  source_extension?: string;
  shard_count?: number;
  facts_source?: string;
  row_count?: number;
  time_min?: string | null;
  time_max?: string | null;
  distinct_dates?: number;
  date_span_days?: number;
  date_coverage_ratio?: number;
  device_count?: number;
  sampling_interval_seconds?: number;
  sampling_completeness?: number;
  value_null_ratio?: number;
  label_distribution?: Record<string, number>;
  label_granularity_detected?: string;
  declared_label_granularity?: string | null;
  sufficient_coverage?: boolean;
  coverage_gaps?: string[];
  coverage_thresholds?: Record<string, number>;
}

/** 不可变的已发布目录条目（平台级，多项目共享）。 */
export interface CatalogEntry {
  entry_id: string;
  dataset_ref: string;
  display_name: string;
  origin: string;
  /** 来源路径：人判定的归属（pv_day / pv_point / pv_tsc），与 applicable_paths 性质不同。 */
  origin_slot?: string | null;
  mapping: Record<string, unknown>;
  label_policy: Record<string, unknown>;
  facts: CatalogFacts;
  applicable_paths: Record<string, CatalogApplicablePath>;
  coverage: CatalogCoverage;
  shard_count: number;
  content_digest: string;
  immutable: boolean;
  published_at?: string;
  idempotent_hit?: boolean;
}

export interface CatalogListResult {
  entries: CatalogEntry[];
  total: number;
}

/** 数据集单元（文件 或 目录分片组）——「数据集」不等于「文件」。 */
export interface DatasetUnitSummary {
  dataset_ref: string;
  unit_kind: 'file' | 'shard_group';
  root_alias: string;
  shard_count: number;
  shard_refs: string[];
  size_bytes: number;
  extensions: string[];
}

/** 三条路径的累计训练数据集（冻结快照）。 */
export interface PathCumulativeSource {
  dataset_ref: string;
  origin: string;
  origin_slot: string;
  display_name: string;
  size_bytes: number;
  modified_at: string;
  candidate_count: number;
}

export interface AvailableSourcesResult {
  path_cumulative: PathCumulativeSource[];
  discoverable: DatasetUnitSummary[];
  path_cumulative_count: number;
  discoverable_count: number;
}

export interface InspectCatalogRequest {
  dataset_ref: string;
  mapping: Record<string, unknown>;
  label_policy?: Record<string, unknown>;
  origin_slot?: string;
  display_name?: string;
  origin?: string;
}

export interface MountCatalogEntryRequest {
  slot: string;
  entry_id: string;
}

export interface MountCatalogResult {
  project_id?: string;
  slot?: string;
  mounted: boolean;
  idempotent_hit: boolean;
  entry_id: string;
  dataset_asset: DatasetAsset;
  dataset_profile_id?: string | null;
  dataset_version_id?: string | null;
  dataset_ref?: string;
  model_inheritance?: ModelInheritanceResult | null;
}

export const pvProjectsApi = {
  // ─── 平台数据集目录（数据集切片第 2b / 2c 步）──────────────────────────
  listCatalog: (): Promise<CatalogListResult> =>
    api.get('/pv-projects/catalog') as unknown as Promise<CatalogListResult>,
  getCatalogEntry: (entryId: string): Promise<CatalogEntry> =>
    api.get(`/pv-projects/catalog/entries/${encodeURIComponent(entryId)}`) as unknown as Promise<CatalogEntry>,
  listAvailableSources: (limit = 200): Promise<AvailableSourcesResult> =>
    api.get('/pv-projects/catalog/available-sources', { params: { limit } }) as unknown as Promise<AvailableSourcesResult>,
  inspectCatalog: (req: InspectCatalogRequest): Promise<CatalogEntry> =>
    api.post('/pv-projects/catalog/inspect', req) as unknown as Promise<CatalogEntry>,
  publishCatalog: (req: InspectCatalogRequest): Promise<CatalogEntry> =>
    api.post('/pv-projects/catalog/publish', req) as unknown as Promise<CatalogEntry>,
  mountCatalogEntry: (projectId: string, req: MountCatalogEntryRequest): Promise<MountCatalogResult> =>
    api.post(`/pv-projects/${encodeURIComponent(projectId)}/datasets/mount`, req) as unknown as Promise<MountCatalogResult>,
  // ─── 项目生命周期 ──────────────────────────────────────────────────────
  listProjects: (includeLegacy = true): Promise<ProjectListResult> =>
    api.get('/pv-projects', { params: { include_legacy: includeLegacy } }) as unknown as Promise<ProjectListResult>,
  createProject: (req: CreateProjectRequest): Promise<CreateProjectResult> =>
    api.post('/pv-projects', req) as unknown as Promise<CreateProjectResult>,
  getOverview: (projectId: string): Promise<ProjectOverview> =>
    api.get(`/pv-projects/${encodeURIComponent(projectId)}/overview`) as unknown as Promise<ProjectOverview>,
  /** 确认项目启用的诊断路径（intent）；传 null 撤销确认。 */
  setEnabledSlots: (projectId: string, enabledSlots: string[] | null): Promise<{ project: ProjectSummary }> =>
    api.put(`/pv-projects/${encodeURIComponent(projectId)}/enabled-slots`, {
      enabled_slots: enabledSlots,
    }) as unknown as Promise<{ project: ProjectSummary }>,
  listDatasets: (projectId: string): Promise<DatasetListResult> =>
    api.get(`/pv-projects/${encodeURIComponent(projectId)}/datasets`) as unknown as Promise<DatasetListResult>,
  registerDataset: (projectId: string, req: RegisterDatasetRequest): Promise<DatasetAsset> =>
    api.post(`/pv-projects/${encodeURIComponent(projectId)}/datasets`, req) as unknown as Promise<DatasetAsset>,
  /**
   * 上传真实文件到平台（`POST /api/upload/file`）。落盘后返回 `file_id`，
   * 用 `uploadRefFromFileId` 拼出 `upload_ref` 即可登记为 upload 类型数据资产。
   */
  uploadFile: (file: File): Promise<UploadedFileInfo> => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/upload/file', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }) as unknown as Promise<UploadedFileInfo>;
  },
  previewDataset: (projectId: string, datasetId: string): Promise<DatasetPreview> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/datasets/${encodeURIComponent(datasetId)}/preview`,
    ) as unknown as Promise<DatasetPreview>,
  saveProfile: (projectId: string, datasetId: string, req: SaveProfileRequest): Promise<DatasetProfile> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/datasets/${encodeURIComponent(datasetId)}/profile`,
      req,
    ) as unknown as Promise<DatasetProfile>,
  publishVersion: (projectId: string, req: PublishVersionRequest): Promise<DatasetVersion> =>
    api.post(`/pv-projects/${encodeURIComponent(projectId)}/dataset-versions/publish`, req) as unknown as Promise<DatasetVersion>,
  listVersions: (projectId: string): Promise<DatasetVersionListResult> =>
    api.get(`/pv-projects/${encodeURIComponent(projectId)}/dataset-versions`) as unknown as Promise<DatasetVersionListResult>,
  getReadiness: (projectId: string, versionId: string): Promise<ReadinessResult> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/dataset-versions/${encodeURIComponent(versionId)}/readiness`,
    ) as unknown as Promise<ReadinessResult>,
  // ─── 运行中心（3.1/3.2）───────────────────────────────────────────────
  /** 该路径下可复用的 canonical 模板（平台级，不带 project_id）。 */
  listWorkflowTemplates: (slot: string): Promise<WorkflowTemplateListResult> =>
    api.get('/pv-projects/workflow-templates', { params: { slot } }) as unknown as Promise<WorkflowTemplateListResult>,
  createProjectWorkflow: (projectId: string, req: CreateProjectWorkflowRequest): Promise<ProjectWorkflow> =>
    api.post(`/pv-projects/${encodeURIComponent(projectId)}/project-workflows`, req) as unknown as Promise<ProjectWorkflow>,
  listProjectWorkflows: (projectId: string, slot: string): Promise<ProjectWorkflowListResult> =>
    api.get(`/pv-projects/${encodeURIComponent(projectId)}/project-workflows`, { params: { slot } }) as unknown as Promise<ProjectWorkflowListResult>,
  runPreflight: (projectId: string, req: PreflightRequest): Promise<PreflightResult> =>
    api.post(`/pv-projects/${encodeURIComponent(projectId)}/preflight`, req) as unknown as Promise<PreflightResult>,
  startExecution: (projectId: string, req: StartExecutionRequest): Promise<ScopedExecution> =>
    api.post(`/pv-projects/${encodeURIComponent(projectId)}/executions`, req) as unknown as Promise<ScopedExecution>,
  listExecutions: (projectId: string, slot: string): Promise<ExecutionListResult> =>
    api.get(`/pv-projects/${encodeURIComponent(projectId)}/executions`, { params: { slot } }) as unknown as Promise<ExecutionListResult>,
  getExecution: (projectId: string, executionId: string, slot: string): Promise<ScopedExecution> =>
    api.get(`/pv-projects/${encodeURIComponent(projectId)}/executions/${encodeURIComponent(executionId)}`, { params: { slot } }) as unknown as Promise<ScopedExecution>,
  retryExecution: (projectId: string, executionId: string, slot: string): Promise<ScopedExecution> =>
    api.post(`/pv-projects/${encodeURIComponent(projectId)}/executions/${encodeURIComponent(executionId)}/retry`, null, { params: { slot } }) as unknown as Promise<ScopedExecution>,
  // ─── 四层模型治理（4.1）────────────────────────────────────────────────
  getGovernanceOverview: (projectId: string, slot: string): Promise<GovernanceOverview> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/governance-overview`,
    ) as unknown as Promise<GovernanceOverview>,
  getRegistry: (projectId: string, slot: string): Promise<RegistryView> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/registry`,
    ) as unknown as Promise<RegistryView>,
  listCandidates: (projectId: string, slot: string): Promise<CandidateListResult> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/candidates`,
    ) as unknown as Promise<CandidateListResult>,
  listVerifications: (projectId: string, slot: string): Promise<VerificationListResult> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/verifications`,
    ) as unknown as Promise<VerificationListResult>,
  listPromotions: (projectId: string, slot: string): Promise<PromotionListResult> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/promotions-log`,
    ) as unknown as Promise<PromotionListResult>,
  registerCandidate: (projectId: string, slot: string, req: RegisterCandidateRequest): Promise<{ candidate: ModelCandidate }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/candidates`,
      req,
    ) as unknown as Promise<{ candidate: ModelCandidate }>,
  startVerification: (
    projectId: string,
    slot: string,
    modelCandidateId: string,
    req: StartVerificationRequest,
  ): Promise<{ verification: Verification }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/candidates/${encodeURIComponent(modelCandidateId)}/verifications`,
      req,
    ) as unknown as Promise<{ verification: Verification }>,
  // ─── 统一审核队列 / 详情 / 精度（4.2）──────────────────────────────────
  getReviewQueue: (projectId: string, slot: string): Promise<ReviewQueueResult> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/reviews`,
    ) as unknown as Promise<ReviewQueueResult>,
  getReviewDetail: (projectId: string, slot: string, reviewId: string): Promise<{ review: ReviewSession }> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/reviews/${encodeURIComponent(reviewId)}`,
    ) as unknown as Promise<{ review: ReviewSession }>,
  getReviewAccuracy: (projectId: string, slot: string, reviewId: string): Promise<ReviewAccuracy> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/reviews/${encodeURIComponent(reviewId)}/accuracy`,
    ) as unknown as Promise<ReviewAccuracy>,
  saveReviewVerdict: (projectId: string, slot: string, reviewId: string, req: SaveVerdictRequest): Promise<{ review: ReviewSession }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/reviews/${encodeURIComponent(reviewId)}/verdict`,
      req,
    ) as unknown as Promise<{ review: ReviewSession }>,
  completeReview: (projectId: string, slot: string, reviewId: string, req: CompleteReviewRequest): Promise<{ review: ReviewSession }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/reviews/${encodeURIComponent(reviewId)}/complete`,
      req,
    ) as unknown as Promise<{ review: ReviewSession }>,
  completeAndAdmitReview: (projectId: string, slot: string, reviewId: string, req: CompleteAndAdmitRequest): Promise<{ review: ReviewSession; admission: AdmissionEvent }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/reviews/${encodeURIComponent(reviewId)}/complete-and-admit`,
      req,
    ) as unknown as Promise<{ review: ReviewSession; admission: AdmissionEvent }>,
  // ─── 累计三层 + 冻结（4.3）─────────────────────────────────────────────
  getCumulative: (projectId: string, slot: string): Promise<CumulativeOverview> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/cumulative`,
    ) as unknown as Promise<CumulativeOverview>,
  getFreezePlan: (projectId: string, slot: string, reviewedAtCutoff?: string): Promise<FreezePlan> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/cumulative/freeze-plan`,
      { reviewed_at_cutoff: reviewedAtCutoff ?? null },
    ) as unknown as Promise<FreezePlan>,
  executeFreeze: (projectId: string, slot: string, req: FreezeRequest): Promise<{ snapshot: FrozenSnapshot; idempotent_replay: boolean }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/cumulative/freeze`,
      req,
    ) as unknown as Promise<{ snapshot: FrozenSnapshot; idempotent_replay: boolean }>,
  // ─── 日路径（5.1 / 5.2）────────────────────────────────────────────────
  getDayProductionFact: (projectId: string, slot: string): Promise<DayProductionFact> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/day/production-fact`,
    ) as unknown as Promise<DayProductionFact>,
  runSandboxDeviceDay: (projectId: string, slot: string, req: SandboxDeviceDayRequest): Promise<{ sandbox_run: DaySandboxRun }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/day/sandbox-device-day`,
      req,
    ) as unknown as Promise<{ sandbox_run: DaySandboxRun }>,
  listDaySandboxRuns: (projectId: string, slot: string): Promise<{ sandbox_runs: DaySandboxRun[] }> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/day/sandbox-runs`,
    ) as unknown as Promise<{ sandbox_runs: DaySandboxRun[] }>,
  // ─── 点路径逐点会话（6.1 / 6.2 / 6.3）─────────────────────────────────
  createPointSandbox: (projectId: string, slot: string, req: CreatePointSandboxRequest): Promise<{ sandbox: PointSandbox }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/point/sandboxes`,
      req,
    ) as unknown as Promise<{ sandbox: PointSandbox }>,
  getPointSandbox: (projectId: string, slot: string, sandboxId: string): Promise<{ sandbox: PointSandbox }> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/point/sandboxes/${encodeURIComponent(sandboxId)}`,
    ) as unknown as Promise<{ sandbox: PointSandbox }>,
  pointPredictNext: (projectId: string, slot: string, sandboxId: string): Promise<PointStepResult> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/point/sandboxes/${encodeURIComponent(sandboxId)}/predict-next`,
    ) as unknown as Promise<PointStepResult>,
  pointStep: (projectId: string, slot: string, sandboxId: string): Promise<PointStepResult> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/point/sandboxes/${encodeURIComponent(sandboxId)}/step`,
    ) as unknown as Promise<PointStepResult>,
  pointAdvance: (projectId: string, slot: string, sandboxId: string, stepSize: number): Promise<{ sandbox: PointSandbox; processed: number }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/point/sandboxes/${encodeURIComponent(sandboxId)}/advance`,
      { step_size: stepSize },
    ) as unknown as Promise<{ sandbox: PointSandbox; processed: number }>,
  pointReset: (projectId: string, slot: string, sandboxId: string): Promise<PointResetResult> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/point/sandboxes/${encodeURIComponent(sandboxId)}/reset`,
    ) as unknown as Promise<PointResetResult>,
  getPointMetrics: (projectId: string, slot: string, sandboxId: string): Promise<PointMetrics> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/point/sandboxes/${encodeURIComponent(sandboxId)}/metrics`,
    ) as unknown as Promise<PointMetrics>,
  // ─── TSC canonical / strict-10 / 只读观测（7.1–7.3）─────────────────────
  getTscCanonicalEntry: (projectId: string, slot: string): Promise<TscCanonicalEntry> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/tsc/canonical-labeling-entry`,
    ) as unknown as Promise<TscCanonicalEntry>,
  getTscShortcutDistinction: (projectId: string, slot: string): Promise<TscShortcutDistinction> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/tsc/shortcut-distinction`,
    ) as unknown as Promise<TscShortcutDistinction>,
  getTscStrict10Evidence: (projectId: string, slot: string): Promise<TscStrict10View> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/tsc/strict10-evidence`,
    ) as unknown as Promise<TscStrict10View>,
  getTscProductionStatus: (projectId: string, slot: string): Promise<TscProductionStatus> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/slots/${encodeURIComponent(slot)}/tsc/production-status`,
    ) as unknown as Promise<TscProductionStatus>,
  // ─── 跨数据集验证 / 离线基准证据（8.1–8.3）────────────────────────────
  createValidationBatch: (projectId: string, req: CreateValidationBatchRequest): Promise<{ batch: ValidationBatch }> =>
    api.post(`/pv-projects/${encodeURIComponent(projectId)}/validation-batches`, req) as unknown as Promise<{ batch: ValidationBatch }>,
  listValidationBatches: (projectId: string): Promise<{ batches: ValidationBatch[] }> =>
    api.get(`/pv-projects/${encodeURIComponent(projectId)}/validation-batches`) as unknown as Promise<{ batches: ValidationBatch[] }>,
  recordValidationResult: (projectId: string, validationId: string, req: RecordValidationResultRequest): Promise<{ batch: ValidationBatch }> =>
    api.post(
      `/pv-projects/${encodeURIComponent(projectId)}/validation-batches/${encodeURIComponent(validationId)}/results`,
      req,
    ) as unknown as Promise<{ batch: ValidationBatch }>,
  getValidationEvidence: (projectId: string, validationId: string): Promise<ValidationEvidenceBundle> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/validation-batches/${encodeURIComponent(validationId)}/evidence`,
    ) as unknown as Promise<ValidationEvidenceBundle>,
  getZeroPollution: (projectId: string, validationId: string): Promise<ZeroPollutionResult> =>
    api.get(
      `/pv-projects/${encodeURIComponent(projectId)}/validation-batches/${encodeURIComponent(validationId)}/zero-pollution`,
    ) as unknown as Promise<ZeroPollutionResult>,
  listOfflineBenchmarkEvidence: (projectId: string): Promise<{ evidence: OfflineBenchmarkEvidence[] }> =>
    api.get(`/pv-projects/${encodeURIComponent(projectId)}/offline-benchmark-evidence`) as unknown as Promise<{ evidence: OfflineBenchmarkEvidence[] }>,
  registerOfflineBenchmarkEvidence: (projectId: string, req: RegisterBenchmarkRequest): Promise<{ evidence: OfflineBenchmarkEvidence }> =>
    api.post(`/pv-projects/${encodeURIComponent(projectId)}/offline-benchmark-evidence`, req) as unknown as Promise<{ evidence: OfflineBenchmarkEvidence }>,
};

/** 工作流用途：training 可 N 个；labeling 每路径 canonical 一个；detection 共用且不可自建。 */
export type WorkflowKind = 'training' | 'labeling' | 'detection';

export interface CreateProjectWorkflowRequest {
  slot: string;
  mode: 'template' | 'copy' | 'blank';
  name: string;
  source_template_id?: string;
  source_project_workflow_id?: string;
  dataset_version_id?: string;
  /** 工作流用途，缺省 training。 */
  workflow_kind?: WorkflowKind;
  /** 训练输入冻结快照 ID；类型须与本路径匹配（禁止跨路径复用）。 */
  source_snapshot_id?: string;
  nodes?: Array<Record<string, unknown>>;
  edges?: Array<Record<string, unknown>>;
  load_node_id?: string;
}

/** 某路径下可复用的 canonical 模板（供「从模板创建」选择）。 */
export interface WorkflowTemplateSummary {
  template_id: string;
  name: string;
  description: string;
  node_count: number;
}

export interface WorkflowTemplateListResult {
  slot: string;
  templates: WorkflowTemplateSummary[];
  total: number;
}

export interface ProjectWorkflow {
  project_workflow_id: string;
  version: number;
  version_group_id: string;
  parent_project_workflow_id?: string | null;
  name: string;
  create_mode: string;
  /** 工作流用途（training / labeling / detection）。 */
  workflow_kind?: WorkflowKind;
  source_template_id?: string | null;
  bound_dataset_version_id?: string | null;
  /** 训练输入冻结快照（血缘：workflow → snapshot → 台账 → 审核 → 数据版本）。 */
  bound_snapshot_id?: string | null;
  bound_snapshot_type?: string | null;
  nodes: Array<Record<string, unknown>>;
  edges: Array<Record<string, unknown>>;
  created_at?: string;
  overwrites_shared_template?: boolean;
}

export interface ProjectWorkflowListResult {
  project_id: string;
  slot: string;
  workflows: ProjectWorkflow[];
  total: number;
}

export interface PreflightRequest {
  slot: string;
  project_workflow_id: string;
  dataset_version_id?: string;
}

export interface PreflightCheck {
  key: string;
  label: string;
  status: 'passed' | 'warning' | 'blocked';
  detail: string;
  current_value?: unknown;
  required_value?: unknown;
  next_action?: string;
  /**
   * 治理影响分级（P0-3）：
   * - `none`：信息性提示，不影响 overall，也不降级治理资格。
   * - `downgrade`：治理降级，使 overall 至多 warning 且 experiment_only=true。
   */
  governance_impact?: 'none' | 'downgrade';
}

export interface PreflightResult {
  project_id: string;
  slot: string;
  project_workflow_id: string;
  dataset_version_id: string | null;
  overall: 'passed' | 'warning' | 'blocked';
  checks: PreflightCheck[];
  /** 信息性提示（governance_impact=none）：展示为"提示"，不参与治理判定。 */
  informational_notes?: Array<{ key: string; label: string; detail: string }>;
  /** 治理降级原因：解释"为什么只能做实验"。 */
  downgrade_reasons?: Array<{ key: string; label: string; detail: string }>;
  experiment_only: boolean;
  allowed_to_run: boolean;
  evaluated_at: string;
}

export type RunMode = 'experiment' | 'validation' | 'training' | 'prediction' | 'replay';

export interface StartExecutionRequest {
  slot: string;
  project_workflow_id: string;
  run_mode: RunMode;
  run_domain?: 'project' | 'sandbox';
  dataset_version_id?: string;
  node_ids?: string[];
  evaluation_contract?: Record<string, unknown>;
  idempotency_key?: string;
}

export interface NodeTimelineEntry {
  node_id: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'cancelled';
  updated_at?: string;
  error?: string;
}

export interface ScopedExecution {
  execution_id: string;
  project_id?: string;
  slot?: string;
  project_workflow_id: string;
  /** 固化的工作流用途（training / labeling / detection）；由服务端从持久化工作流派生。 */
  workflow_kind?: WorkflowKind;
  /** 固化的项目工作流版本号。 */
  workflow_version?: number;
  workflow_version_group_id?: string;
  /** 工作流绑定的不可变数据版本（执行记录自带，不必回查工作流）。 */
  bound_dataset_version_id?: string | null;
  /** 工作流绑定的冻结快照（训练输入血缘）。 */
  bound_snapshot_id?: string | null;
  bound_snapshot_type?: string | null;
  /** 执行时的预检摘要（固化，可回溯"当时依据的是哪份预检"）。 */
  preflight?: {
    overall?: 'passed' | 'warning' | 'blocked';
    experiment_only?: boolean;
    evaluated_at?: string;
    checks_digest?: string;
  } | null;
  dataset_version_id?: string | null;
  run_mode: RunMode;
  run_domain: 'project' | 'sandbox';
  governance_eligible: boolean;
  status: 'running' | 'success' | 'failed' | 'cancelled';
  node_timeline: NodeTimelineEntry[];
  result_destination?: string | null;
  failure_reason?: string | null;
  /** 训练执行 finalize 时自动登记候选的结果；旧执行没有该字段。 */
  auto_candidate?: {
    registered: boolean;
    idempotent_hit?: boolean;
    model_candidate_id?: string | null;
    model_artifact_ref?: string | null;
    pool_registered?: boolean;
    pool_candidate_id?: string | null;
    reason?: string | null;
    domain_sync_reason?: string | null;
    error?: string | null;
    note?: string | null;
  } | null;
  /** 可选节点产出摘要；服务端可从 outputSummary 提取模型工件。 */
  node_results?: Record<string, unknown> | null;
  origin_kind?: string | null;
  started_at?: string;
  finished_at?: string | null;
}

export interface ExecutionListResult {
  project_id: string;
  slot: string;
  executions: ScopedExecution[];
  total: number;
}

export interface SaveProfileRequest {
  mapping: Record<string, unknown>;
  facts?: Record<string, unknown>;
  label_policy?: Record<string, unknown>;
  ical_contract?: Record<string, unknown>;
}

export interface DatasetProfile {
  dataset_profile_id: string;
  dataset_id: string;
  mapping: Record<string, unknown>;
  mapping_digest: string;
}

export interface PublishVersionRequest {
  dataset_id: string;
  dataset_profile_id: string;
}

export interface DatasetVersion {
  project_id?: string;
  dataset_version_id: string;
  dataset_id: string;
  dataset_profile_id: string;
  artifact_ref: string;
  content_digest: string;
  source_kind?: string;
  immutable?: boolean;
  published_at?: string;
  idempotent_hit?: boolean;
}

export interface DatasetVersionListResult {
  project_id: string;
  versions: DatasetVersion[];
}

export interface ReadinessBlocker {
  reason_code: string;
  severity: string;
  current_value?: unknown;
  required_value?: unknown;
}

export interface PathReadiness {
  project_id: string;
  slot: string;
  dataset_version_id: string;
  dataset_profile_id: string;
  status: string;
  facts: Array<Record<string, unknown>>;
  blockers: ReadinessBlocker[];
  allowed_run_modes: string[];
  primary_blocker: string | null;
  next_action: string | null;
  not_production_eligible_note: string;
  computed_from_profile_digest?: string;
}

export interface ReadinessResult {
  project_id: string;
  dataset_version_id: string;
  dataset_profile_id: string;
  paths: PathReadiness[];
}

// ─── 四层模型治理（design §16）─────────────────────────────────────────────
/**
 * 随路径累计训练快照继承的 baseline 指针。
 *
 * 它共享平台 slot 已有模型工件，不复制二进制；`governance_effect='none'`，不能作为
 * project candidate 发起复验、设置 rolling 或 Promote。
 */
export interface InheritedBaselinePointer {
  link_id: string;
  association_kind: 'inherited_from_slot';
  slot: string;
  catalog_entry_id?: string | null;
  dataset_id?: string | null;
  dataset_version_id?: string | null;
  mount_content_digest?: string | null;
  source_slot: string;
  source_slot_registry_version?: number | null;
  source_role?: 'champion' | 'rolling_detect_model' | 'challenger' | 'latest_candidate' | 'registry_fallback' | string;
  source_model_candidate_id?: string | null;
  source_model_id?: string | null;
  model_ref?: string | null;
  model_artifact_ref: string;
  producer_project_id?: string | null;
  producer_project_name?: string | null;
  source_lineage?: Record<string, unknown>;
  governance_effect: 'none';
  governance_eligible: false;
  promotable: false;
  binary_copied: false;
  link_basis: string;
  linked_at?: string;
  backfilled_at?: string;
  supersedes_link_id?: string | null;
}

export interface ModelInheritanceResult {
  status: 'linked' | 'no_model_available' | 'artifact_missing' | 'not_applicable' | 'read_only' | 'error';
  idempotent_hit: boolean;
  inherited_baseline?: InheritedBaselinePointer | null;
  source_role?: string | null;
  source_model_candidate_id?: string | null;
  model_artifact_ref?: string | null;
  reason?: string | null;
}

export interface ModelInventoryView {
  trained_in_project_count: number;
  inherited_from_slot_count: number;
  association_kinds: Array<'trained_in_project' | 'inherited_from_slot'>;
  primary_association_kind?: 'trained_in_project' | 'inherited_from_slot' | null;
}

/** 当前生产 Champion 指针（registry 单独真源）。 */
export interface ChampionPointer {
  champion_model_ref?: string;
  source_model_candidate_id?: string;
  source_workflow_id?: string;
  model_artifact_ref?: string;
  verification_id?: string;
  set_at?: string;
}

/** 当前挑战者指针。 */
export interface ChallengerPointer {
  challenger_model_ref?: string;
  challenger_model_candidate_id?: string;
  challenger_verification_id?: string;
  set_at?: string;
}

/** 下一轮检测消费的滚动模型指针。 */
export interface RollingDetectPointer {
  model_candidate_id?: string;
  model_artifact_ref?: string;
  source_workflow_id?: string;
  verification_id?: string;
  set_at?: string;
  operator?: string;
  reason?: string;
}

/** 只读当前模型登记视图。 */
export interface RegistryView {
  project_id: string;
  slot: string;
  champion: ChampionPointer | null;
  challenger: ChallengerPointer | null;
  rolling_detect_model: RollingDetectPointer | null;
  inherited_baseline?: InheritedBaselinePointer | null;
  model_inheritance?: ModelInheritanceResult | null;
  registry_version: number;
  updated_at?: string | null;
  note?: string | null;
  empty: boolean;
  read_only: boolean;
}

/** 模型候选（候选历史，与当前指针分离）。 */
export interface ModelCandidate {
  model_candidate_id: string;
  project_id?: string;
  slot?: string;
  source_execution_id?: string;
  source_workflow_id?: string | null;
  source_dataset_version_id?: string | null;
  source_snapshot_id?: string | null;
  model_artifact_ref?: string;
  model_ref?: string;
  evaluation_contract?: Record<string, unknown>;
  governance_eligible: boolean;
  provenance_gaps?: string[];
  registered_at?: string;
}

/** 正式复验记录（pending/passed=None 表示未决，不能据此 Promote）。 */
export interface Verification {
  verification_id: string;
  model_candidate_id: string;
  project_id?: string;
  slot?: string;
  comparison_id?: string;
  status: 'pending' | 'passed' | 'failed';
  passed: boolean | null;
  aggregate_method?: string;
  min_windows_challenger_better?: number;
  score_margin?: number;
  evaluation_contract?: Record<string, unknown>;
  started_at?: string;
  engine_note?: string;
}

/** Promote 审计事件（append-only）。 */
export interface PromotionEvent {
  promotion_id: string;
  project_id?: string;
  model_candidate_id: string;
  verification_id: string;
  production_slot: string;
  set_as_production: boolean;
  operator: string;
  reason: string;
  adopted_model_ref?: string;
  previous_champion_model_ref?: string | null;
  new_champion_model_ref?: string | null;
  champion_changed: boolean;
  registry_version_before: number;
  registry_version_after: number;
  promoted_at?: string;
}

/** 四层治理视图：当前检测模型 / 待复验候选 / 实验结果 / 治理历史 + 复验记录。 */
export interface GovernanceOverview {
  project_id: string;
  slot: string;
  current_detection_model: {
    rolling_detect_model: RollingDetectPointer | null;
    champion: ChampionPointer | null;
    challenger: ChallengerPointer | null;
    /** 随累计训练快照继承的只读 baseline；旧后端不返回该字段。 */
    inherited_baseline?: InheritedBaselinePointer | null;
    registry_version: number;
    read_only: boolean;
    empty: boolean;
  };
  pending_candidates: ModelCandidate[];
  experiment_results: ModelCandidate[];
  verifications: Verification[];
  governance_history: PromotionEvent[];
  /** 模型来源构成（本项目训练 / 随累计快照继承）。 */
  model_inventory?: ModelInventoryView | null;
  /** 本次读取时的继承补链结果（历史项目会在 GET 时幂等补链）。 */
  model_inheritance?: ModelInheritanceResult | null;
}

export interface CandidateListResult {
  project_id: string;
  slot: string;
  candidates: ModelCandidate[];
}

export interface VerificationListResult {
  project_id: string;
  slot: string;
  verifications: Verification[];
}

export interface PromotionListResult {
  project_id: string;
  slot: string;
  events: PromotionEvent[];
}

export interface RegisterCandidateRequest {
  source_execution_id: string;
  model_artifact_ref: string;
  /**
   * 以下 `source_*` / `evaluation_contract` 仅为调用方提示字段。
   * **服务端一律从来源 execution 派生血缘**（P0-2），与派生值冲突时被忽略并记入
   * 候选的 `client_supplied_lineage_ignored`。
   */
  source_workflow_id?: string;
  source_workflow_version?: string;
  source_dataset_version_id?: string;
  source_snapshot_id?: string;
  evaluation_contract?: Record<string, unknown>;
  model_ref?: string;
  /** 已移除：治理资格由服务端从执行派生，客户端无法自授（P0-2）。 */
}

export interface StartVerificationRequest {
  evaluation_contract?: Record<string, unknown>;
  aggregate_method?: string;
  min_windows_challenger_better?: number;
  score_margin?: number;
}

// ─── 统一审核（design §17 / §18）─────────────────────────────────────────────
export type ReviewSourceKind = 'label_proposal' | 'detection_batch' | 'model_assisted_label';
export type ReviewStatus = 'open' | 'in_review' | 'completed' | 'admitted';
export type ItemVerdict = 'accept' | 'reject' | 'uncertain';

/** 队列行（列表视图，含进度与准入就绪）。 */
export interface ReviewQueueRow {
  review_id: string;
  review_slot: string;
  source_kind: ReviewSourceKind;
  unit_granularity: string;
  dataset_version_id?: string | null;
  model_ref?: string | null;
  source_execution_id?: string | null;
  status: ReviewStatus;
  review_version: number;
  progress: { judged: number; total: number };
  admission_ready: boolean;
  admitted_event_id?: string | null;
}

export interface ReviewQueueResult {
  project_id: string;
  slot: string;
  reviews: ReviewQueueRow[];
  total: number;
}

/** 审核详情逐条 item。 */
export interface ReviewItem {
  item_id: string;
  unit_ref?: string | null;
  proposed_label?: string | null;
  evidence?: Record<string, unknown>;
  verdict: ItemVerdict | null;
  verdict_label?: string | null;
  verdict_at?: string | null;
}

export interface ReviewSession {
  review_id: string;
  slot: string;
  source_kind: ReviewSourceKind;
  unit_granularity: string;
  dataset_version_id?: string | null;
  model_ref?: string | null;
  source_execution_id?: string | null;
  items: ReviewItem[];
  status: ReviewStatus;
  review_version: number;
  admitted_event_id?: string | null;
  created_at?: string;
  completed_at?: string;
  admitted_at?: string;
}

/** 精度表面（可空；无有效真值时 value=null，前端渲染“未产出”）。 */
export interface ReviewAccuracy {
  project_id: string;
  slot: string;
  review_id: string;
  statistical_scope: {
    review_slot: string;
    unit_granularity: string;
    total_items: number;
    accepted_items: number;
  };
  human_truth_count: number;
  class_support: Record<string, number>;
  metric_definition: string;
  dataset_version_id?: string | null;
  model_ref?: string | null;
  comparable: boolean;
  non_comparability_reasons: string[];
  value: number | null;
  value_display: string;
  auto_action_note: string;
}

export interface AdmissionEvent {
  event_id: string;
  kind: 'admission';
  slot: string;
  review_id: string;
  source_kind: ReviewSourceKind;
  admitted_count: number;
  rejected_count: number;
  uncertain_count: number;
  accepted_unit_refs: Array<string | null>;
  operator: string;
  admitted_at?: string;
}

export interface ItemVerdictInput {
  item_id: string;
  verdict?: ItemVerdict | null;
  verdict_label?: string;
}

export interface SaveVerdictRequest {
  expected_review_version: number;
  item_verdicts: ItemVerdictInput[];
}

export interface CompleteReviewRequest {
  expected_review_version: number;
}

export interface CompleteAndAdmitRequest {
  expected_review_version: number;
  idempotency_key: string;
  operator: string;
}

// ─── 累计三层 + 冻结（design §19）───────────────────────────────────────────
export interface FrozenSnapshot {
  snapshot_id: string;
  slot: string;
  reviewed_at_cutoff?: string | null;
  included_events: string[];
  included_count: number;
  excluded_count: number;
  label_distribution: Record<string, number>;
  device_distribution: Record<string, number>;
  date_distribution: Record<string, number>;
  snapshot_type: string;
  path_note: string;
  plan_fingerprint: string;
  content_digest: string;
  immutable: boolean;
  frozen_at?: string;
}

export interface TrainingResult {
  result_id: string;
  kind: 'training_result';
  slot: string;
  source_snapshot_id: string;
  source_execution_id: string;
  model_artifact_ref: string;
  metrics?: Record<string, unknown>;
  governance_note: string;
  registered_at?: string;
}

export interface CumulativeOverview {
  project_id: string;
  slot: string;
  admitted_events: AdmissionEvent[];
  frozen_snapshots: FrozenSnapshot[];
  training_results: TrainingResult[];
  summary: {
    admission_count: number;
    admitted_units: number;
    snapshot_count: number;
    training_result_count: number;
  };
}

export interface FreezePlan {
  project_id: string;
  slot: string;
  reviewed_at_cutoff?: string | null;
  included_events: string[];
  excluded_events: string[];
  included_count: number;
  excluded_count: number;
  label_distribution: Record<string, number>;
  device_distribution: Record<string, number>;
  date_distribution: Record<string, number>;
  output_snapshot_type: string;
  path_note: string;
  plan_fingerprint: string;
  duplicate_input_detected: boolean;
  duplicate_snapshot_id?: string | null;
  freezable: boolean;
}

export interface FreezeRequest {
  reviewed_at_cutoff?: string | null;
  idempotency_key: string;
  operator: string;
}

// ─── 日路径（design D-PATH-01）─────────────────────────────────────────────
export interface DayProductionFact {
  project_id: string;
  slot: string;
  production_strategy: string;
  production_workflow_id: string;
  dedicated_day_production_graph: boolean;
  statement: string;
}

export interface DayDeviceDayResult {
  device_day_key: string;
  device?: string | null;
  date?: string | null;
  sandbox_outcome: string;
  order: number;
}

export interface DaySandboxRun {
  sandbox_id: string;
  slot: string;
  run_domain: string;
  model_ref?: string | null;
  device_day_count: number;
  device_day_results: DayDeviceDayResult[];
  production_unaffected: boolean;
  result_id: string;
  governance_eligible: boolean;
  note: string;
  created_at?: string;
}

export interface SandboxDeviceDayRequest {
  sandbox_id: string;
  device_days: Array<Record<string, unknown>>;
  model_ref?: string;
}

// ─── 点路径逐点会话（design D-PATH-01 / D-STATE-01）──────────────────────────
export interface PointPrediction {
  n_history: number;
  baseline_from_committed: number;
  current_value: number;
  anomaly_score: number;
  predicted_at: string;
}

export interface PointPending {
  point_index: number;
  event_time?: string | null;
  input_point: Record<string, unknown>;
  prediction: PointPrediction;
  committed: boolean;
}

export interface PointCommitted {
  point_index: number;
  event_time?: string | null;
  value?: number | null;
  prediction: PointPrediction;
  committed_at: string;
}

export interface PointSandbox {
  sandbox_id: string;
  slot: string;
  run_domain: string;
  session_source: string;
  model_ref?: string | null;
  dataset_version_id?: string | null;
  source_points: Array<Record<string, unknown>>;
  committed_history: PointCommitted[];
  cursor: number;
  pending_point: PointPending | null;
  production_unaffected: boolean;
  writes_cumulative_ledger: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface PointStepResult {
  project_id: string;
  slot: string;
  sandbox: PointSandbox;
  pending_point?: PointPending | null;
  committed?: PointCommitted;
  caught_up?: boolean;
  already_pending?: boolean;
  idempotent_replay?: boolean;
}

export interface PointResetResult {
  project_id: string;
  slot: string;
  sandbox: PointSandbox;
  reset_scope: { sandbox_id: string; current_cursor: number };
  production_unaffected: boolean;
  statement: string;
}

export interface PointMetrics {
  project_id: string;
  slot: string;
  sandbox_id: string;
  committed_points: number;
  cursor: number;
  total_points: number;
  device_day_labels_as_truth: boolean;
  supervised_point_accuracy: number | null;
  note: string;
}

export interface CreatePointSandboxRequest {
  sandbox_id: string;
  points: Array<Record<string, unknown>>;
  model_ref?: string;
  session_source?: string;
  dataset_version_id?: string;
}

// ─── TSC canonical / strict-10 / 只读观测（design D-PATH-01）─────────────────
export interface TscCanonicalEntry {
  project_id: string;
  slot: string;
  canonical_workflow_id: string | null;
  lineage: string[];
  launch_hint: string;
  fail_closed: string;
  ui_acceptance_pending: boolean;
}

export interface TscShortcutDistinction {
  project_id: string;
  slot: string;
  labeling_mode: string;
  is_canonical: boolean;
  preferred_labeling_workflow_id: string | null;
  explanation: string;
}

export interface TscStrict10Evidence {
  result_id: string;
  kind: string;
  slot: string;
  source_execution_id: string;
  contract: Record<string, unknown>;
  macro_f1: number | null;
  macro_f1_display: number | string;
  production_contract_valid: boolean;
  production_contract_note: string;
  qualified_device_days?: number | null;
  rejected_device_days?: number | null;
  class_distribution: Record<string, number>;
  governance_eligible: boolean;
  registered_at?: string;
}

export interface TscStrict10View {
  project_id: string;
  slot: string;
  contract: Record<string, unknown>;
  evidence: TscStrict10Evidence[];
  all_validation_non_governable: boolean;
}

export interface TscProductionStatus {
  project_id: string;
  slot: string;
  read_only: boolean;
  has_current_receipt: boolean;
  status_display: string;
  device_day_evidence?: unknown;
  multi_window_evidence?: unknown;
  scheduler_receipt?: unknown;
  cursor_advances_on_failed_day: boolean;
  manual_advance_allowed: boolean;
  note: string;
}

// ─── 跨数据集验证 / 离线基准证据（design D-GOV-01）──────────────────────────
export interface ValidationDatasetEntry {
  dataset_key?: string | null;
  source_ref?: string | null;
  dataset_version_id?: string | null;
  content_digest?: string | null;
  input_source_hash: string;
  result: {
    metrics: Record<string, unknown>;
    dimension_findings: Record<string, unknown>;
    post_run_input_source_hash?: string;
    recorded_at?: string;
  } | null;
}

export interface ValidationBatch {
  validation_id: string;
  governance_effect: string;
  evaluation_contract: Record<string, unknown>;
  datasets: ValidationDatasetEntry[];
  dimensions: string[];
  status: string;
  note?: string | null;
  governance_note: string;
  created_at?: string;
}

export interface ValidationEvidenceBundle {
  project_id: string;
  validation_id: string;
  governance_effect: string;
  dataset_count: number;
  completed_count: number;
  per_dataset: Array<{
    dataset_key?: string | null;
    dataset_version_id?: string | null;
    metrics: Record<string, unknown>;
    dimension_findings: Record<string, unknown>;
  }>;
  dimension_summary: Record<string, Array<string | null>>;
  can_be_verification_evidence: boolean;
  note: string;
}

export interface ZeroPollutionResult {
  project_id: string;
  validation_id: string;
  zero_pollution: boolean;
  checks: Array<{
    dataset_key?: string | null;
    baseline_hash: string;
    recomputed_hash: string;
    post_run_hash?: string | null;
    unchanged: boolean;
  }>;
}

export interface OfflineBenchmarkEvidence {
  benchmark_evidence_version: string;
  governance_effect: string;
  read_only: boolean;
  benchmark_source: string;
  manifest_ref?: string | null;
  metrics: Record<string, unknown>;
  calibration_audit_id: string | null;
  calibration_note: string;
  content_hash: string;
  registered_at?: string;
}

export interface CreateValidationBatchRequest {
  datasets: Array<Record<string, unknown>>;
  evaluation_contract?: Record<string, unknown>;
  note?: string;
}

export interface RecordValidationResultRequest {
  dataset_key: string;
  metrics?: Record<string, unknown>;
  dimension_findings?: Record<string, unknown>;
}

export interface RegisterBenchmarkRequest {
  benchmark_source: string;
  manifest_ref?: string;
  metrics?: Record<string, unknown>;
  calibration_note?: string;
}

// @AI_GENERATED: end
