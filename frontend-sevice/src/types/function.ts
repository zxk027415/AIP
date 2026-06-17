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
