/** Slot datasets API — G5 annotation / snapshot chain */
import api from './api';
// @AI_GENERATED
import type { ProjectAttributionView } from './slotGovernanceApi';
// @AI_GENERATED: end

export interface SnapshotChainView {
  slot: string;
  snapshot_id: string | null;
  latest_version: number;
  versions: Record<string, unknown>[];
  empty?: boolean;
}

export interface PathOverviewDataset {
  selected: boolean;
  dataset_ref?: string | null;
  row_count?: number | null;
  has_gold?: boolean | null;
  fingerprint?: string | null;
  note?: string | null;
}

export interface PathOverviewAvailableDataset {
  entry_id?: string | null;
  dataset_ref: string;
  display_name: string;
  origin_slot?: string | null;
  applicable: boolean;
  mountable: boolean;
}

// @AI_GENERATED
/**
 * 按日精度的产出模型与项目归属。
 *
 * `model_id` 为 `loop_demo_rule` 时是内置规则回放，没有真实模型，`project` 为 null。
 * `multi_model=true` 表示累计区间里换过模型 —— 累计精度是跨天按样本加权的，
 * 此时**不可**把这个数字归给单一项目，前端应收起归属展示。
 */
export interface PathOverviewAccuracyAttribution {
  model_id?: string | null;
  model_count: number;
  multi_model: boolean;
  latest_day?: string | null;
  /** 最近一个业务日的分类精度；与 classifier_accuracy（跨日累计）区分。 */
  latest_accuracy?: number | null;
  /** 最近业务日真正计入评估的设备日 / 点数。 */
  latest_counted_units?: number | null;
  project?: ProjectAttributionView | null;
}
// @AI_GENERATED: end

export interface PathOverviewRow {
  slot: string;
  label: string;
  granularity: string;
  semantics: Record<string, unknown>;
  champion?: string | null;
  challenger?: string | null;
  current_model?: string | null;
  classifier_accuracy?: number | null;
  counted_units?: number | null;
  accuracy_source?: string | null;
  // @AI_GENERATED
  accuracy_attribution?: PathOverviewAccuracyAttribution | null;
  // @AI_GENERATED: end
  dataset: PathOverviewDataset;
  available_datasets: PathOverviewAvailableDataset[];
  available_dataset_count: number;
}

export interface PathOverviewResult {
  paths: PathOverviewRow[];
  total: number;
}

export interface FeedSourceFacts {
  dataset_ref: string;
  root_alias?: string;
  exists?: boolean;
  row_count?: number | null;
  date_min?: string | null;
  date_max?: string | null;
  fingerprint?: string | null;
  has_gold?: boolean | null;
  gold_column?: string | null;
  error?: string | null;
}

export interface FeedSourceCurrent {
  slot: string;
  selected: boolean;
  selection?: { dataset_ref?: string | null } | null;
  source?: FeedSourceFacts | null;
  semantics?: {
    granularity?: string;
    arrival_gate?: Record<string, unknown>;
    missing_policy?: string;
  };
  note?: string | null;
}

export interface FeedSourcesResult {
  candidates: Array<{ dataset_ref: string; root_alias?: string; unit_kind?: string; shard_count?: number }>;
  current: Record<string, FeedSourceCurrent>;
}

export const slotDatasetsApi = {
  getPathOverview: (): Promise<PathOverviewResult> =>
    api.get('/slot-datasets/overview') as unknown as Promise<PathOverviewResult>,

  getFeedSources: (limit = 200): Promise<FeedSourcesResult> =>
    api.get('/slot-datasets/feed-sources', { params: { limit } }) as unknown as Promise<FeedSourcesResult>,

  selectFeedSource: (
    slot: string,
    datasetRef: string | null,
    operator = 'ui',
  ): Promise<{ slot: string; selection: Record<string, unknown>; current: FeedSourceCurrent }> =>
    api.post('/slot-datasets/feed-sources/select', {
      slot,
      dataset_ref: datasetRef,
      operator,
    }) as unknown as Promise<{ slot: string; selection: Record<string, unknown>; current: FeedSourceCurrent }>,

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
