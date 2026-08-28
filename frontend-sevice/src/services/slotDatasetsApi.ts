/** Slot datasets API — G5 annotation / snapshot chain */
import api from './api';

export interface SnapshotChainView {
  slot: string;
  snapshot_id: string | null;
  latest_version: number;
  versions: Record<string, unknown>[];
  empty?: boolean;
}

export const slotDatasetsApi = {
  getSnapshotChain: (slot: string): Promise<SnapshotChainView> =>
    api.get('/slot-datasets/snapshots/chain', { params: { slot } }),

  listAnnotationCandidates: (
    slot: string,
    reviewStatus?: string,
  ): Promise<{ slot: string; candidates: Record<string, unknown>[] }> =>
    api.get('/slot-datasets/annotation-candidates', {
      params: { slot, review_status: reviewStatus },
    }),

  listReviewedAnnotations: (slot: string): Promise<{ slot: string; annotations: Record<string, unknown>[] }> =>
    api.get('/slot-datasets/reviewed-annotations', { params: { slot } }),

  bootstrapSnapshot: (body: {
    slot: string;
    idempotency_key: string;
    source_digest: string;
    base_artifact_ref: string;
    dataset_profile_ref: string;
    reason: string;
  }): Promise<{ chain: SnapshotChainView; bootstrap: Record<string, unknown> }> =>
    api.post('/slot-datasets/snapshots/bootstrap', body),

  buildSnapshot: (body: {
    slot: string;
    snapshot_id: string;
    base_snapshot_version: number;
    reviewed_annotation_ids: string[];
    idempotency_key: string;
    reason: string;
  }): Promise<{ chain: SnapshotChainView; build: Record<string, unknown> }> =>
    api.post('/slot-datasets/snapshots/build', body),

  approveAnnotationCandidate: (
    annotationCandidateId: string,
    body: {
      slot: string;
      reviewer: string;
      idempotency_key: string;
      final_label?: unknown;
      label_space_version?: string;
      annotation_role?: string;
    },
  ): Promise<{ reviewed_annotation: Record<string, unknown> }> =>
    api.post(`/slot-datasets/annotation-candidates/${encodeURIComponent(annotationCandidateId)}/approve`, body),

  rejectAnnotationCandidate: (
    annotationCandidateId: string,
    body: {
      slot: string;
      reviewer: string;
      idempotency_key: string;
      reason: string;
    },
  ): Promise<{ transaction: Record<string, unknown> }> =>
    api.post(`/slot-datasets/annotation-candidates/${encodeURIComponent(annotationCandidateId)}/reject`, body),
};
