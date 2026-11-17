/**
 * 数据类型枚举
 */
export enum DataType {
  NUMBER = 'NUMBER',
  MATRIX = 'MATRIX',
  VECTOR = 'VECTOR',
  STRING = 'STRING',
  BOOLEAN = 'BOOLEAN',
  ARRAY = 'ARRAY',
  OBJECT = 'OBJECT',
  ANY = 'ANY',
}

/**
 * 类型约束接口
 */
export interface TypeConstraint {
  type: DataType;
  dimensions?: number[]; // 用于矩阵/向量维度约束
  range?: [number, number]; // 用于数值范围约束
  pattern?: string; // 用于字符串模式约束
}
