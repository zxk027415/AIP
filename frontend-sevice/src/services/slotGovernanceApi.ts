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

export interface ModelCandidateView {
  model_candidate_id: string;
  slot: string;
  source_workflow_id: string;
  source_workflow_version: string | null;
  source_execution_id: string;
  model_artifact_ref: string;
  model_ref: string | null;
  registered_at: string;
  status: string;
}

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
