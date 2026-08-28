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
};
