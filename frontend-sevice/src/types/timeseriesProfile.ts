export type ProfileUsePurpose =
  | 'local_validation'
  | 'product_workflow'
  | 'distribution'
  | 'production'
  | 'benchmark_reuse';

export interface DatasetProfileSummary {
  profile_id: string;
  profile_version: string;
  slot: string;
  status?: string;
  description?: string;
}

export interface ProfilePreflightIssue {
  code: string;
  severity: 'error' | 'warning';
  field?: string;
  message: string;
  sample_count?: number;
  hint?: string;
}

export interface ProfilePreflightReport {
  profile_id: string;
  profile_version: string;
  use_purpose: ProfileUsePurpose;
  ready: boolean;
  blocked_by_license?: boolean;
  resolved_source_ref?: string;
  source_digest?: string;
  row_count?: number;
  entity_count?: number;
  time_range_start?: string;
  time_range_end?: string;
  duplicate_point_count?: number;
  missing_required_columns?: string[];
  issues: ProfilePreflightIssue[];
}

export interface DatasetProfile extends DatasetProfileSummary {
  source_kind: string;
  source_ref: string;
  path_root_alias: string;
  format: string;
  clock_mode: 'event_time' | 'index';
  time_column?: string | null;
  entity_keys: string[];
  feature_columns: string[];
  label_column?: string | null;
  license_status?: string;
  allowed_use_purposes?: string[];
}
