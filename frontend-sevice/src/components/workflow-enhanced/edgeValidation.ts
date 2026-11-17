// @AI_GENERATED
/**
 * 画布连线校验 — 基于归一化 I/O，与运行时数据传递对齐
 */
import type { CSSProperties, Edge } from 'reactflow';
import type { EnhancedWorkflowNode } from '../../types/workflow-enhanced';
import { getEdgeColorForType } from './portTypeValidation';
import {
  isNormalizedEdgeCompatible,
  getNormalizedEdgeTypes,
  resolveEdgeHandles,
} from './operatorIoProfile';

export interface EdgeValidationResult {
  valid: boolean;
  message: string;
  sourceType: string;
  targetType: string;
}

export function validateEdgeConnection(
  sourceNode: EnhancedWorkflowNode | undefined,
  sourceHandle: string | null | undefined,
  targetNode: EnhancedWorkflowNode | undefined,
  targetHandle: string | null | undefined,
): EdgeValidationResult {
  if (!sourceNode || !targetNode) {
    return {
      valid: false,
      message: '连线节点不存在',
      sourceType: 'UNKNOWN',
      targetType: 'UNKNOWN',
    };
  }

  const srcFuncId = sourceNode.data?.config?.functionId as string | undefined;
  const tgtFuncId = targetNode.data?.config?.functionId as string | undefined;
  const { sourceType, targetType } = getNormalizedEdgeTypes(srcFuncId, tgtFuncId);

  // 无 functionId 的控制节点暂不判错
  if (!srcFuncId || !tgtFuncId) {
    return { valid: true, message: '', sourceType, targetType };
  }

  const handles = resolveEdgeHandles(sourceHandle, targetHandle);
  void handles; // 归一化后不再依赖 handle id 精确匹配

  const check = isNormalizedEdgeCompatible(srcFuncId, tgtFuncId);
  if (!check.valid) {
    return {
      valid: false,
      message: check.message,
      sourceType,
      targetType,
    };
  }

  return {
    valid: true,
    message: '',
    sourceType,
    targetType,
  };
}

const VALID_EDGE_STYLE = { stroke: '#94a3b8', strokeWidth: 2 };
const INVALID_EDGE_STYLE = {
  stroke: '#ff4d4f',
  strokeWidth: 2.5,
  strokeDasharray: '8 4',
};

export function getEdgeVisualStyle(
  valid: boolean,
  sourceType?: string,
): CSSProperties {
  if (!valid) return INVALID_EDGE_STYLE;
  if (sourceType) {
    return {
      stroke: getEdgeColorForType(sourceType),
      strokeWidth: 2,
    };
  }
  return VALID_EDGE_STYLE;
}

export function decorateEdgeWithValidation(
  edge: Edge,
  nodes: EnhancedWorkflowNode[],
): Edge {
  const sourceNode = nodes.find((n) => n.id === edge.source);
  const targetNode = nodes.find((n) => n.id === edge.target);
  const handles = resolveEdgeHandles(edge.sourceHandle, edge.targetHandle);
  const result = validateEdgeConnection(
    sourceNode,
    handles.sourceHandle,
    targetNode,
    handles.targetHandle,
  );

  return {
    ...edge,
    animated: !result.valid,
    style: getEdgeVisualStyle(result.valid, result.sourceType),
    data: {
      ...(edge.data || {}),
      compatible: result.valid,
      validationError: result.valid ? undefined : result.message,
      sourceType: result.sourceType,
      targetType: result.targetType,
    },
    label: result.valid ? undefined : '⚠',
    labelStyle: result.valid ? undefined : { fill: '#ff4d4f', fontWeight: 600, fontSize: 12 },
    labelBgStyle: result.valid ? undefined : { fill: '#fff1f0', fillOpacity: 0.9 },
  };
}
// @AI_GENERATED: end
