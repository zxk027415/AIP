import type { DataType, TypeConstraint } from './data';

/**
 * 参数定义
 */
export interface ParameterDefinition {
  name: string;
  type: DataType;
  required: boolean;
  defaultValue?: any;
  constraints?: TypeConstraint[];
  description?: string;
}

/**
 * 函数定义
 */
export interface FunctionDefinition {
  id: string;
  name: string;
  category: string;
  description: string;
  parameters: ParameterDefinition[];
  returnType: DataType;
  return_type?: DataType; // 兼容后端返回的字段名
  examples: string[];
  implementation?: string; // 函数实现代码（可选）
  /** G13.1: available=有后端可执行，planned=仅目录定义 */
  implementation_status?: 'available' | 'planned';
  /** 六层 + e2e 验证通过（仅 available 时有意义） */
  implementation_verified?: boolean;
}

/**
 * 分类
 */
export interface Category {
  id: string;
  name: string;
  description: string;
  subcategories?: Category[];
}
