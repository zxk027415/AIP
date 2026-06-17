import type { WorkflowGlobalConfig } from '../types/pipeline';

const WHITELIST_KEYS = [
  'train_days',
  'daily_horizon',
  'backtest_mode',
  'model_ref',
  'use_reference_engine',
  'strict_alignment_mode',
  'apply_window_filter',
  'mask_target_values',
  'model_family',
  'model_params',
] as const;

type WhitelistKey = (typeof WHITELIST_KEYS)[number];

function pickWhitelisted(params: Record<string, any>): Partial<Record<WhitelistKey, any>> {
  const result: Partial<Record<WhitelistKey, any>> = {};
  WHITELIST_KEYS.forEach((k) => {
    if (params[k] !== undefined) {
      result[k] = params[k];
    }
  });
  return result;
}

export function buildGlobalConfigPatchFromBestRecommendation(
  bestRecommendation: any,
): Partial<WorkflowGlobalConfig> {
  if (!bestRecommendation || typeof bestRecommendation !== 'object') {
    return {};
  }
  const applied = bestRecommendation.applied_params;
  const appliedParams = applied && typeof applied === 'object' ? applied : {};
  const picked = pickWhitelisted(appliedParams);

  const patch: Partial<WorkflowGlobalConfig> = {};
  if (picked.train_days !== undefined) patch.backtest_train_days = Number(picked.train_days);
  if (picked.daily_horizon !== undefined) patch.backtest_daily_horizon = Number(picked.daily_horizon);
  if (picked.backtest_mode !== undefined) patch.backtest_mode = String(picked.backtest_mode);
  if (picked.model_ref !== undefined) patch.backtest_model_ref = String(picked.model_ref);
  if (picked.use_reference_engine !== undefined) patch.use_reference_rolling_engine = Boolean(picked.use_reference_engine);
  if (picked.strict_alignment_mode !== undefined) patch.strict_alignment_mode = Boolean(picked.strict_alignment_mode);
  if (picked.apply_window_filter !== undefined) patch.backtest_apply_window_filter = Boolean(picked.apply_window_filter);
  if (picked.mask_target_values !== undefined) patch.backtest_mask_target_values = Boolean(picked.mask_target_values);
  if (picked.model_family !== undefined) patch.tuning_model_family = String(picked.model_family);
  if (picked.model_params !== undefined && picked.model_params && typeof picked.model_params === 'object') {
    patch.tuning_model_params = picked.model_params as Record<string, any>;
  }
  return patch;
}

