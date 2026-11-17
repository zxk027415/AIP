import api from './api';

export type CumulativeSource = 'path_a' | 'daily_review' | 'unknown' | string;

export type CumulativeLedgerEvent = {
  event_id?: string;
  dataset_version_id: string;
  file_path?: string;
  source?: CumulativeSource;
  reviewed_at?: string;
  reviewer?: string | null;
  included_at?: string;
  sequence?: number;
};

export type CumulativeFreezeIncludedEvent = {
  event_id?: string | null;
  dataset_version_id?: string;
  source?: CumulativeSource;
  reviewed_at?: string | null;
  file_path?: string | null;
  reviewer?: string | null;
};

// @AI_GENERATED: Immutable freeze observation contract shared by the latest-status card and preview drawer.
export type SnapshotSourceComposition = {
  by_event?: Record<string, number>;
  by_row?: Record<string, number>;
  by_device_day?: Record<string, number>;
};

export type TscGridObservation = {
  available: boolean;
  reason?: string;
  device_days_total?: number;
  grid_aligned_device_days?: number;
  train_eligible_device_days?: number;
  rejected_device_days?: number;
  class_distribution?: Record<string, number>;
  skip_reasons?: Record<string, number>;
  channels?: string[];
  grid_contract?: Record<string, unknown>;
  purity_threshold?: number | null;
};

export type DatasetObservation = {
  train_source?: {
    dataset_id?: string;
    file_path?: string;
    kind?: string;
  };
  row_count?: number;
  series_count?: number | null;
  device_id_count?: number | null;
  device_day_count_raw?: number | null;
  row_label_distribution?: Record<string, number>;
  grid?: TscGridObservation | null;
  source_composition?: SnapshotSourceComposition;
  computed_at?: string;
};
// @AI_GENERATED: end

export type CumulativeFreezeVersion = {
  snapshot_version?: number;
  freeze_id?: string | null;
  reviewed_at_cutoff?: string | null;
  artifact_ref?: string;
  included_labeled_version_ids?: string[];
  included_events?: CumulativeFreezeIncludedEvent[];
  included_event_count?: number;
  created_at?: string;
  reason?: string;
  // @AI_GENERATED: Persisted snapshot statistics avoid rescanning the full parquet on every page load.
  dataset_observation?: DatasetObservation | null;
  // @AI_GENERATED: end
};

export type CumulativeLedger = {
  slot: string;
  events: CumulativeLedgerEvent[];
  event_count: number;
  included_count: number;
  freeze_versions: CumulativeFreezeVersion[];
  latest_freeze: CumulativeFreezeVersion | null;
  updated_at?: string;
  priority?: string;
};

export function freezeIdOf(slot: string, freeze?: CumulativeFreezeVersion | null): string | null {
  if (!freeze) return null;
  if (freeze.freeze_id) return freeze.freeze_id;
  if (freeze.snapshot_version != null) return `snap-${slot}-v${freeze.snapshot_version}`;
  return null;
}

export const slotCumulativeApi = {
  getLedger: (slot: string): Promise<CumulativeLedger> =>
    api.get('/slot-datasets/cumulative-ledger', { params: { slot } }),

  freezeAt: (
    slot: string,
    reviewedAtCutoff: string,
    reason?: string,
  ): Promise<{ freeze: Record<string, unknown>; ledger: CumulativeLedger }> =>
    api.post('/slot-datasets/cumulative-ledger/freeze', {
      slot,
      reviewed_at_cutoff: reviewedAtCutoff,
      reason,
    }),

  previewSnapshot: (slot: string, freezeId: string): Promise<SnapshotPreview> =>
    api.get('/slot-datasets/snapshots/preview', { params: { slot, freeze_id: freezeId } }),
};

export type SnapshotPreview = {
  slot: string;
  freeze_id: string;
  artifact_ref?: string;
  row_count: number;
  column_names: string[];
  time_start?: string | null;
  time_end?: string | null;
  device_count?: number | null;
  label_distribution: Record<string, number>;
  sample_rows: Array<Record<string, unknown>>;
  included_event_count?: number;
  // @AI_GENERATED: Full cumulative-source and TSC grid observations for the existing dashboard card.
  dataset_observation?: DatasetObservation | null;
  // @AI_GENERATED: end
};
