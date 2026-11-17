// @AI_GENERATED
/**
 * 算子 I/O 归一化 — 画布连线校验与运行时 _collect_upstream_inputs 对齐
 *
 * 货架 functions.json 把「配置参数」标成 input 端口，但画布边实际传的是流水线 data/object。
 * 校验必须基于归一化后的 I/O，不能直接用 param ports。
 */
import type { NodePort } from '../../types/workflow-enhanced';

export type OperatorIoKind = 'source' | 'pipeline' | 'train' | 'metric' | 'ensemble' | 'control';

export interface NormalizedOperatorIo {
  kind: OperatorIoKind;
  /** 画布连线语义上的输入（单 handle: input） */
  inputs: NodePort[];
  /** 画布连线语义上的输出（单 handle: output） */
  outputs: NodePort[];
}

const SOURCE_OPERATORS = new Set([
  'load_csv',
  'load_parquet',
  'load_json',
  'load_excel',
  'load_labeled_dataset',
  'load_dataset',
  'load_pv_demo',
  'load_model_artifact',
]);

const METRIC_OPERATORS = new Set([
  'smape_score',
  'mse_rmse_mae',
  'mape_score',
  'rmse_score',
  'mae_score',
  'r2_score',
  'precision_recall_f1',
  'confusion_matrix',
  'confusion_matrix_eval',
  'classification_report',
]);

const TRAIN_FORECAST_OPERATORS = new Set([
  'xgboost_forecast',
  'lightgbm_forecast',
  'catboost_forecast',
  'ridge_forecast',
  'prophet',
  'arima',
  'auto_tune_xgboost',
  'auto_tune_lightgbm',
  'auto_tune_catboost',
  'random_forest_classifier',
  'decision_tree_classifier',
  'svm_classifier',
  'logistic_regression',
  'linear_regression',
  'lasso_regression',
  'elastic_net',
  'ts_point_train_classifier',
]);

const ENSEMBLE_OPERATORS = new Set([
  'ensemble_forecast',
]);

const MULTI_INPUT_OPERATORS = new Set([
  'merge_label',
  'emit_label_proposal',
  'cluster_profile',
  'ks_test',
]);

function pipelinePort(id: 'input' | 'output', dataType: NodePort['dataType'] = 'matrix'): NodePort {
  return {
    id,
    name: 'data',
    type: id === 'input' ? 'input' : 'output',
    dataType,
  };
}

/** 按 functionId 归一化算子画布 I/O */
export function normalizeOperatorIo(functionId: string | undefined): NormalizedOperatorIo | null {
  if (!functionId) return null;

  if (SOURCE_OPERATORS.has(functionId)) {
    return {
      kind: 'source',
      inputs: [],
      outputs: [pipelinePort('output', 'matrix')],
    };
  }

  if (METRIC_OPERATORS.has(functionId)) {
    return {
      kind: 'metric',
      inputs: [{
        id: 'input',
        name: 'predictions',
        type: 'input',
        dataType: 'object',
      }],
      outputs: [{
        id: 'output',
        name: 'score',
        type: 'output',
        dataType: 'number',
      }],
    };
  }

  if (ENSEMBLE_OPERATORS.has(functionId)) {
    return {
      kind: 'ensemble',
      inputs: [{
        id: 'input',
        name: 'predictions',
        type: 'input',
        dataType: 'object',
      }],
      outputs: [{
        id: 'output',
        name: 'forecast',
        type: 'output',
        dataType: 'object',
      }],
    };
  }

  if (TRAIN_FORECAST_OPERATORS.has(functionId)) {
    return {
      kind: 'train',
      inputs: [{
        id: 'input',
        name: 'features',
        type: 'input',
        dataType: 'object',
      }],
      outputs: [{
        id: 'output',
        name: 'result',
        type: 'output',
        dataType: 'object',
      }],
    };
  }

  if (MULTI_INPUT_OPERATORS.has(functionId)) {
    return {
      kind: 'pipeline',
      inputs: [{
        id: 'input',
        name: 'data',
        type: 'input',
        dataType: 'matrix',
      }],
      outputs: [pipelinePort('output', 'matrix')],
    };
  }

  // 默认：时序预处理 / 特征 / 切分等 — 单 data 进、data 出
  return {
    kind: 'pipeline',
    inputs: [pipelinePort('input', 'matrix')],
    outputs: [pipelinePort('output', 'matrix')],
  };
}

/** 归一化后的源/目标类型（用于连线校验） */
export function getNormalizedEdgeTypes(
  sourceFunctionId: string | undefined,
  targetFunctionId: string | undefined,
): { sourceKind: OperatorIoKind | null; targetKind: OperatorIoKind | null; sourceType: string; targetType: string } {
  const src = normalizeOperatorIo(sourceFunctionId);
  const tgt = normalizeOperatorIo(targetFunctionId);
  return {
    sourceKind: src?.kind ?? null,
    targetKind: tgt?.kind ?? null,
    sourceType: String(src?.outputs[0]?.dataType || 'any').toUpperCase(),
    targetType: String(tgt?.inputs[0]?.dataType || 'any').toUpperCase(),
  };
}

/**
 * 基于归一化 I/O 的连线兼容性 — 对齐运行时 dict/data 传递，避免误报
 */
export function isNormalizedEdgeCompatible(
  sourceFunctionId: string | undefined,
  targetFunctionId: string | undefined,
): { valid: boolean; message: string } {
  const { sourceKind, targetKind, sourceType, targetType } = getNormalizedEdgeTypes(
    sourceFunctionId,
    targetFunctionId,
  );

  if (!sourceKind || !targetKind) {
    return { valid: true, message: '' };
  }

  // 数据源不应有上游流水线边（允许 0 入边，不在这里判错）
  if (targetKind === 'source') {
    return { valid: false, message: '数据加载算子不需要上游数据输入' };
  }

  // 运行时 _collect_upstream_inputs 把上游 dict 合并传入，object/matrix 互通
  const compatibleKinds: Record<OperatorIoKind, Set<OperatorIoKind>> = {
    source: new Set(['pipeline', 'train', 'ensemble', 'metric']),
    pipeline: new Set(['pipeline', 'train', 'ensemble', 'metric']),
    train: new Set(['metric', 'ensemble', 'train']),
    ensemble: new Set(['metric']),
    metric: new Set([]),
    control: new Set(['pipeline', 'train', 'ensemble', 'metric']),
  };

  if (compatibleKinds[sourceKind]?.has(targetKind)) {
    return { valid: true, message: '' };
  }

  // 兜底：端口类型层（object ↔ matrix）
  const src = sourceType;
  const tgt = targetType;
  if (src === tgt || src === 'ANY' || tgt === 'ANY') {
    return { valid: true, message: '' };
  }
  if (src === 'OBJECT' && (tgt === 'MATRIX' || tgt === 'ARRAY')) {
    return { valid: true, message: '' };
  }
  if (src === 'MATRIX' && tgt === 'OBJECT') {
    return { valid: true, message: '' };
  }

  return {
    valid: false,
    message: `类型不兼容: ${src} → ${tgt}（${sourceKind} → ${targetKind}）`,
  };
}

/** 将节点 data.inputs/outputs 覆写为归一化端口（拖拽新算子 / 加载模板后调用） */
export function applyNormalizedPortsToNodeData(
  functionId: string | undefined,
  data: { inputs?: NodePort[]; outputs?: NodePort[] },
): { inputs: NodePort[]; outputs: NodePort[] } {
  const profile = normalizeOperatorIo(functionId);
  if (!profile) {
    return {
      inputs: data.inputs || [],
      outputs: data.outputs || [],
    };
  }
  return {
    inputs: profile.inputs,
    outputs: profile.outputs,
  };
}

/** 画布 handle 默认值 — 与 DifyStyleNodeHD 的 id="input"|"output" 一致 */
export const DEFAULT_SOURCE_HANDLE = 'output';
export const DEFAULT_TARGET_HANDLE = 'input';

export function resolveEdgeHandles(
  sourceHandle: string | null | undefined,
  targetHandle: string | null | undefined,
): { sourceHandle: string; targetHandle: string } {
  return {
    sourceHandle: sourceHandle || DEFAULT_SOURCE_HANDLE,
    targetHandle: targetHandle || DEFAULT_TARGET_HANDLE,
  };
}

/** 加载/应用模板时归一化单个节点 */
export function normalizeWorkflowNode<T extends { data: { config?: { functionId?: string }; inputs?: NodePort[]; outputs?: NodePort[] } }>(
  node: T,
): T {
  const functionId = node.data?.config?.functionId;
  const ports = applyNormalizedPortsToNodeData(functionId, node.data);
  return {
    ...node,
    data: {
      ...node.data,
      inputs: ports.inputs,
      outputs: ports.outputs,
    },
  };
}

/** 加载模板时补全 null handle（与 DifyStyleNodeHD 一致） */
export function normalizeWorkflowEdge<T extends { sourceHandle?: string | null; targetHandle?: string | null }>(
  edge: T,
): T {
  const handles = resolveEdgeHandles(edge.sourceHandle, edge.targetHandle);
  return {
    ...edge,
    sourceHandle: handles.sourceHandle,
    targetHandle: handles.targetHandle,
  };
}
// @AI_GENERATED: end
