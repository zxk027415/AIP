export type ParamInputType = 'number' | 'boolean' | 'string';

export interface ModelParamSchemaItem {
  key: string;
  label: string;
  type: ParamInputType;
  defaultValue: number | boolean | string;
  min?: number;
  max?: number;
  step?: number;
}

export interface ModelFamilySpec {
  id: string;
  label: string;
  operatorId: string;
  params: ModelParamSchemaItem[];
}

export const MODEL_FAMILY_REGISTRY: Record<string, ModelFamilySpec> = {
  xgboost: {
    id: 'xgboost',
    label: 'XGBoost',
    operatorId: 'xgboost_forecast',
    params: [
      { key: 'n_estimators', label: '树数量 (n_estimators)', type: 'number', defaultValue: 200, min: 10, max: 2000, step: 10 },
      { key: 'eta', label: '学习率 (eta)', type: 'number', defaultValue: 0.05, min: 0.001, max: 1, step: 0.001 },
      { key: 'max_depth', label: '最大深度 (max_depth)', type: 'number', defaultValue: 5, min: 1, max: 20, step: 1 },
      { key: 'subsample', label: '样本采样率 (subsample)', type: 'number', defaultValue: 0.8, min: 0.1, max: 1, step: 0.01 },
      { key: 'sample_weight_decay', label: '样本衰减 (sample_weight_decay)', type: 'number', defaultValue: 0.99, min: 0.8, max: 1, step: 0.001 },
    ],
  },
  lightgbm: {
    id: 'lightgbm',
    label: 'LightGBM',
    operatorId: 'lightgbm_forecast',
    params: [
      { key: 'n_estimators', label: '树数量 (n_estimators)', type: 'number', defaultValue: 500, min: 10, max: 3000, step: 10 },
      { key: 'learning_rate', label: '学习率 (learning_rate)', type: 'number', defaultValue: 0.05, min: 0.001, max: 1, step: 0.001 },
      { key: 'num_leaves', label: '叶子数 (num_leaves)', type: 'number', defaultValue: 31, min: 2, max: 512, step: 1 },
      { key: 'max_depth', label: '最大深度 (max_depth)', type: 'number', defaultValue: -1, min: -1, max: 30, step: 1 },
      { key: 'feature_fraction', label: '特征采样率 (feature_fraction)', type: 'number', defaultValue: 0.8, min: 0.1, max: 1, step: 0.01 },
    ],
  },
  catboost: {
    id: 'catboost',
    label: 'CatBoost',
    operatorId: 'catboost_forecast',
    params: [
      { key: 'iterations', label: '迭代次数 (iterations)', type: 'number', defaultValue: 600, min: 20, max: 5000, step: 10 },
      { key: 'learning_rate', label: '学习率 (learning_rate)', type: 'number', defaultValue: 0.05, min: 0.001, max: 1, step: 0.001 },
      { key: 'depth', label: '深度 (depth)', type: 'number', defaultValue: 8, min: 1, max: 16, step: 1 },
      { key: 'l2_leaf_reg', label: 'L2 正则 (l2_leaf_reg)', type: 'number', defaultValue: 3, min: 0, max: 50, step: 0.5 },
      { key: 'verbose', label: '训练日志 (verbose)', type: 'boolean', defaultValue: false },
    ],
  },
  ridge: {
    id: 'ridge',
    label: 'Ridge',
    operatorId: 'ridge_forecast',
    params: [
      { key: 'alpha', label: '正则强度 (alpha)', type: 'number', defaultValue: 1, min: 0, max: 100, step: 0.1 },
      { key: 'fit_intercept', label: '拟合截距 (fit_intercept)', type: 'boolean', defaultValue: true },
      { key: 'solver', label: '求解器 (solver)', type: 'string', defaultValue: 'auto' },
    ],
  },
};

export const DEFAULT_MODEL_FAMILY = 'xgboost';

export function getDefaultModelParams(modelFamily: string): Record<string, number | boolean | string> {
  const spec = MODEL_FAMILY_REGISTRY[modelFamily] || MODEL_FAMILY_REGISTRY[DEFAULT_MODEL_FAMILY];
  const params: Record<string, number | boolean | string> = {};
  spec.params.forEach((item) => {
    params[item.key] = item.defaultValue;
  });
  return params;
}

