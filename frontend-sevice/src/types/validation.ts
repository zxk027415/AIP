/**
 * 错误类型枚举
 */
export enum ErrorType {
  MISSING_INPUT = 'MISSING_INPUT',
  TYPE_MISMATCH = 'TYPE_MISMATCH',
  CIRCULAR_DEPENDENCY = 'CIRCULAR_DEPENDENCY',
  INVALID_PARAMETER = 'INVALID_PARAMETER',
  DIMENSION_MISMATCH = 'DIMENSION_MISMATCH',
  INVALID_OPERATION = 'INVALID_OPERATION',
  DISCONNECTED_NODE = 'DISCONNECTED_NODE',
}

/**
 * 验证问题严重程度
 */
export type ValidationSeverity = 'error' | 'warning' | 'info';

/**
 * 验证错误
 */
export interface ValidationError {
  type: string;
  message: string;
  severity: ValidationSeverity;
  nodeId?: string;
  edgeId?: string;
  port?: string;
  moduleId?: string;
  connectionId?: string;
  suggestion?: string;
}

/**
 * 验证警告
 */
export interface ValidationWarning {
  type: string;
  message: string;
  severity: ValidationSeverity;
  nodeId?: string;
  nodes?: string[];
  moduleId?: string;
  connectionId?: string;
}

/**
 * 验证问题（错误或警告）
 */
export type ValidationIssue = ValidationError | ValidationWarning;

/**
 * 验证结果
 */
export interface ValidationResult {
  valid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
  issues?: ValidationIssue[];
}
