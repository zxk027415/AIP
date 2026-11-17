// @AI_GENERATED
/**
 * 端口类型兼容性校验逻辑
 */
import { PORT_TYPE_COLORS } from '../../types/pipeline';

/** 检查源端口类型与目标端口类型是否兼容 */
export function isPortTypeCompatible(sourceType: string, targetType: string): boolean {
  if (!sourceType || !targetType) return true;
  const src = sourceType.toUpperCase();
  const tgt = targetType.toUpperCase();
  if (src === tgt) return true;
  if (tgt === 'ANY' || src === 'ANY') return true;
  // OBJECT 作为容器与 MATRIX/ARRAY 兼容
  if (src === 'OBJECT' && (tgt === 'MATRIX' || tgt === 'ARRAY')) return true;
  if (tgt === 'OBJECT' && (src === 'MATRIX' || src === 'ARRAY')) return true;
  if (src === 'NUMBER' && tgt === 'ARRAY') return true;
  if (src === 'MATRIX' && tgt === 'ARRAY') return true;
  if (src === 'ARRAY' && tgt === 'MATRIX') return true;
  if (src === 'MATRIX' && tgt === 'VECTOR') return true;
  if (src === 'VECTOR' && tgt === 'ARRAY') return true;
  return false;
}

/** 获取端口类型对应的连线颜色 */
export function getEdgeColorForType(dataType: string): string {
  return PORT_TYPE_COLORS[dataType?.toUpperCase()] || '#999';
}

/** 校验连接并返回错误信息（空字符串表示通过） */
export function validateConnection(
  sourceType: string,
  targetType: string,
): string {
  if (isPortTypeCompatible(sourceType, targetType)) return '';
  return `类型不兼容: ${sourceType} → ${targetType}`;
}
// @AI_GENERATED: end
