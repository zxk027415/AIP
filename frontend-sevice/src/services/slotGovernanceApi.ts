/**
 * slotGovernanceApi.ts — G4 槽位治理 API（registry / model candidate 骨架）
 */
import api from './api';

export interface SlotRegistryView {
  slot: string;
  registry_version: number;
  updated_at: string | null;
  champion: Record<string, unknown> | null;
  challenger: Record<string, unknown> | null;
  rolling_detect_model?: {
    model_candidate_id?: string | null;
    model_artifact_ref?: string | null;
    set_at?: string | null;
    operator?: string | null;
    reason?: string | null;
  } | null;
  note?: string | null;
  empty?: boolean;
  diagnostic?: string | null;
}

// @AI_GENERATED: Candidate evaluation fields are optional because legacy/3-seed artifacts do not satisfy strict-10.
export interface ModelEvaluationContract {
  evaluation?: string;
  representation?: string;
  channels?: string[];
  metric_name?: string;
  macro_f1_mean?: number;
  macro_f1_std?: number;
  accuracy_mean?: number;
  accuracy_std?: number;
  balanced_accuracy_mean?: number;
  balanced_accuracy_std?: number;
  n_seeds?: number;
  n_splits?: number;
  n_splits_completed?: number;
  n_splits_requested?: number;
  n_samples?: number;
  n_classes?: number;
  production_contract_valid?: boolean;
  [key: string]: unknown;
}

/**
 * 项目归属 — 这个模型（或这条精度）是哪个项目训练产出的。
 *
 * 后端 `services/slot_governance/project_attribution.py` 解析：
 * `resolved_by='explicit_field'` 表示池记录上直接带了 project_id（领域桥新写入的）；
 * `'model_ref_lookup'` 表示按 model_ref(cand-*) 反查项目候选得到（历史记录）。
 * 为 `null` 表示该候选不是项目训练产出的 —— 是正常状态，不是解析失败。
 */
export interface ProjectAttributionView {
  project_id: string;
  project_name?: string | null;
  project_candidate_id?: string | null;
  source_workflow_id?: string | null;
  source_execution_id?: string | null;
  source_dataset_version_id?: string | null;
  governance_eligible?: boolean | null;
  resolved_by: 'explicit_field' | 'model_ref_lookup';
}

export interface ModelCandidateView {
  model_candidate_id: string;
  slot: string;
  source_workflow_id?: string | null;
  /** 项目工作流版本是整数（pv_projects 侧 version 从 1 递增），旧登记来源可能是字符串。 */
  source_workflow_version?: string | number | null;
  source_execution_id?: string | null;
  source_snapshot_id?: string | null;
  source_retrain_request_id?: string | null;
  source_kind?: string | null;
  model_artifact_ref: string;
  model_ref: string | null;
  registered_at: string;
  status: string;
  evaluation_contract?: ModelEvaluationContract | null;
  production_contract_valid?: boolean;
  /** 领域桥写入的项目归属（新记录）；解析结果见 project_attribution。 */
  project_id?: string | null;
  source_project_candidate_id?: string | null;
  /** 后端解析出的项目归属；null = 非项目来源。 */
  project_attribution?: ProjectAttributionView | null;
}
// @AI_GENERATED: end

export interface VerifyAsyncJobView {
  comparison_id: string;
  slot: string;
  model_candidate_id: string;
  verification_workflow_ref?: string;
  status: string;
  verification_id?: string;
  verification_execution_id?: string;
  created_at?: string;
  completed_at?: string;
  metrics_summary?: Record<string, unknown>;
}

export const slotGovernanceApi = {
  getRegistry: (slot: string): Promise<SlotRegistryView> =>
    api.get(`/slot-governance/registry/${encodeURIComponent(slot)}`),

  setRollingDetectModel: (
    slot: string,
    body: {
      model_candidate_id?: string | null;
      model_artifact_ref?: string | null;
      operator?: string;
      reason?: string;
    },
  ): Promise<{ registry: SlotRegistryView; rolling_detect_model: SlotRegistryView['rolling_detect_model'] }> =>
    api.put(`/slot-governance/registry/${encodeURIComponent(slot)}/rolling-detect-model`, body),

  setProductionModel: (
    slot: string,
    body: {
      model_candidate_id?: string | null;
      model_artifact_ref?: string | null;
      operator?: string;
      reason?: string;
    },
  ): Promise<{ registry: SlotRegistryView; champion: Record<string, unknown> | null }> =>
    api.put(`/slot-governance/registry/${encodeURIComponent(slot)}/production-model`, body),

  setCandidateModel: (
    slot: string,
    body: {
      model_candidate_id?: string | null;
      model_artifact_ref?: string | null;
      operator?: string;
      reason?: string;
    },
  ): Promise<{ registry: SlotRegistryView; challenger: Record<string, unknown> | null }> =>
    api.put(`/slot-governance/registry/${encodeURIComponent(slot)}/candidate-model`, body),

  getEvaluationContract: (slot: string): Promise<Record<string, unknown>> =>
    api.get(`/slot-governance/evaluation-contract/${encodeURIComponent(slot)}`),

  listModelCandidates: (slot: string): Promise<{ slot: string; candidates: ModelCandidateView[] }> =>
    api.get('/slot-governance/model-candidates', { params: { slot } }),

  // @AI_GENERATED: Read the exact candidate selected by pv_tsc run status; do not substitute a latest-row guess.
  getModelCandidate: (
    modelCandidateId: string,
  ): Promise<{ slot: string; candidate: ModelCandidateView }> =>
    api.get(`/slot-governance/model-candidates/${encodeURIComponent(modelCandidateId)}`),
  // @AI_GENERATED: end

  registerModelCandidate: (body: {
    slot: string;
    source_workflow_id: string;
    source_workflow_version?: string | null;
    source_execution_id: string;
    model_artifact_ref: string;
    model_ref?: string | null;
  }): Promise<{ candidate: ModelCandidateView }> =>
    api.post('/slot-governance/model-candidates', body),

  promoteModelCandidate: (
    modelCandidateId: string,
    body: {
      verification_id: string;
      operator: string;
      reason: string;
      expected_registry_version: number;
      idempotency_key: string;
      production_slot?: string;
      set_as_production?: boolean;
    },
  ): Promise<{ promotion: Record<string, unknown>; registry: SlotRegistryView }> =>
    api.post(`/slot-governance/model-candidates/${encodeURIComponent(modelCandidateId)}/promote`, body),

  listPromotionsLog: (slot: string): Promise<{ slot: string; events: Record<string, unknown>[] }> =>
    api.get(`/slot-governance/promotions-log/${encodeURIComponent(slot)}`),

  startVerifyAsync: (body: {
    slot: string;
    model_candidate_id: string;
    idempotency_key: string;
    evaluation_contract_ref?: string;
    registry_version_at_start?: number;
  }): Promise<{ job: Record<string, unknown> }> =>
    api.post('/slot-governance/verifications/verify-async', body),

  listVerifyAsyncJobs: (
    slot: string,
    status?: 'pending' | 'completed',
  ): Promise<{ slot: string; jobs: VerifyAsyncJobView[] }> =>
    api.get('/slot-governance/verifications/verify-async', {
      params: { slot, status },
    }),

  getVerifyAsyncJob: (comparisonId: string): Promise<{ slot: string; job: VerifyAsyncJobView }> =>
    api.get(`/slot-governance/verifications/verify-async/${encodeURIComponent(comparisonId)}`),

  completeVerifyAsync: (
    comparisonId: string,
    verificationExecutionId: string,
  ): Promise<{ job: Record<string, unknown>; verification: Record<string, unknown> }> =>
    api.post(`/slot-governance/verifications/verify-async/${encodeURIComponent(comparisonId)}/complete`, {
      verification_execution_id: verificationExecutionId,
    }),

  listVerifications: (slot: string): Promise<{ slot: string; verifications: Record<string, unknown>[] }> =>
    api.get('/slot-governance/verifications', { params: { slot } }),
};
