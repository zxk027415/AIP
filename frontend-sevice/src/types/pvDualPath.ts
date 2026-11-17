// @AI_GENERATED
/**
 * PV 双路径控制台 TypeScript 合同。
 * Ledger 六态、Epoch/LaneClaim、Champion 生命周期、三层 Shadow、九项门控与双事件。
 */

export type ModelingPath = 'legacy_day' | 'seq_annotation';
export type LedgerStatus =
  | 'waiting_data'
  | 'ready'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'revision_pending';
export type ActivationMode = 'cutover_only' | 'recent_window' | 'full_backfill';

export interface PathModelLifecycle {
  champion?: { model_ref: string; evaluation_id?: string; gate_metric_value?: number; candidate_id?: string } | null;
  challengers?: Array<{ model_ref: string; evaluation_id?: string; gate_metric_value?: number; candidate_id?: string }>;
  retired?: Array<{ model_ref: string; evaluation_id?: string; gate_metric_value?: number }>;
  model_ref?: string | null;
}

export interface ModelingPathsGovernance {
  simple_switch_allowed?: boolean;
  write_auth_required?: boolean;
  environment?: string;
}

export interface ModelingPathsState {
  production_path: ModelingPath | string;
  fallback_path?: string;
  path_models?: Record<string, PathModelLifecycle>;
  active_activation_epoch?: { activation_epoch_id?: string | null };
  active_activation_epoch_id?: string | null;
  updated_at?: string;
  note?: string | null;
  governance?: ModelingPathsGovernance;
}

export interface LedgerItem {
  slot: string;
  modeling_path: string;
  site_id: string;
  device_id: string;
  branch_id: string;
  business_date: string;
  status: LedgerStatus | string;
  input_fingerprint?: string | null;
  batch_id?: string | null;
  supersedes_batch_id?: string | null;
  attempt_count?: number;
  last_error?: string | null;
  processed_at?: string | null;
}

export interface LedgerPage {
  page: number;
  page_size: number;
  total: number;
  items: LedgerItem[];
  frontier_summary?: Record<string, string | null>;
  cursor_semantics?: string;
}

export interface GateCondition {
  number: number;
  name: string;
  passed: boolean;
  reason?: string | null;
}

export interface GateResult {
  all_passed: boolean;
  conditions: GateCondition[];
  failed_conditions: GateCondition[];
}

export interface ShadowReport {
  comparison_id: string;
  legacy_model_ref: string;
  seq_model_ref: string;
  generated_at?: string;
  comparable_total?: number;
  coverage_rate?: number;
  agreement_rate?: number;
  common_metrics?: Record<string, unknown>;
  seq_native_metrics?: Record<string, unknown>;
  runtime_metrics?: Record<string, unknown>;
  uncomparable_items?: Array<{ severity?: string; reason?: string }>;
  diff_items?: Array<{ site_id?: string; legacy_label?: unknown; seq_label?: unknown }>;
}

export interface PromotionEvent {
  promotion_event_id: string;
  modeling_path: string;
  champion_model_ref: string;
  challenger_model_ref: string;
  promoted_at: string;
}

export interface PathSwitchEvent {
  path_switch_event_id: string;
  from_path: string;
  to_path: string;
  activation_epoch_id: string;
  switched_at: string;
  operator?: string;
  reason?: string;
}

export interface SetModelingPathsBody {
  modeling_path: string;
  slot?: string;
  note?: string;
  comparison_id?: string;
  activation_mode?: ActivationMode | string;
  confirm?: boolean;
  operator?: string;
  reason?: string;
  backfill_days?: number;
  device_scope?: Array<{ site_id: string; device_id: string; branch_id: string }>;
  switch_mode?: 'simple' | 'lab' | string;
  is_fallback?: boolean;
}
// @AI_GENERATED: end
