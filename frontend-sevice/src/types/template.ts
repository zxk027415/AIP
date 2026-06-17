import type { DataType } from './data';
import type { Workflow } from './workflow';

/**
 * 模板参数
 */
export interface TemplateParameter {
  name: string;
  description: string;
  type: DataType;
  defaultValue: any;
  moduleId: string;
  parameterName: string;
}

/**
 * 算法模板模板
 */
export interface WorkflowTemplate {
  id: string;
  name: string;
  category: string;
  description: string;
  workflow: Workflow;
  documentation: string;
  parameters?: TemplateParameter[];
  previewImage?: string;
  tags?: string[];
  author?: string;
  version?: string;
}

/**
 * 模板分类
 */
export interface TemplateCategory {
  id: string;
  name: string;
  description: string;
  icon?: string;
}

/**
 * 模板列表项（用于列表显示）
 */
export interface TemplateListItem {
  id: string;
  name: string;
  category: string;
  description: string;
  previewImage?: string;
  tags?: string[];
}
