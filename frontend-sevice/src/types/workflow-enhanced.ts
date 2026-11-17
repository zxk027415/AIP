/**
 * Enhanced Workflow Types
 * 增强版算法模板类型定义
 */

import type { Node, Edge } from 'reactflow';

/**
 * 节点端口定义
 */
export interface NodePort {
  id: string;
  name: string;
  type: 'input' | 'output';
  dataType: 'number' | 'string' | 'matrix' | 'array' | 'any' | 'boolean';
  required?: boolean;
  description?: string;
}

/**
 * 节点配置
 */
export interface NodeConfig {
  functionId?: string;
  operation?: string;
  chartType?: string;
  [key: string]: any;
}

/**
 * 增强版节点数据
 */
export interface EnhancedNodeData {
  label: string;
  type: 'function' | 'matrix' | 'visualization' | 'control' | 'llm' | 'start' | 'code' | 'end';
  icon?: string;
  inputs: NodePort[];
  outputs: NodePort[];
  config: NodeConfig;
  status?: 'idle' | 'running' | 'success' | 'error';
  error?: string;
  description?: string;
}

/**
 * 增强版节点
 */
export type EnhancedWorkflowNode = Node<EnhancedNodeData>;

/**
 * 增强版连接线数据
 */
export interface EnhancedEdgeData {
  sourcePort?: string;
  targetPort?: string;
  dataType?: string;
}

/**
 * 增强版连接线
 */
export type EnhancedWorkflowEdge = Edge<EnhancedEdgeData>;

/**
 * 节点类型定义
 */
export interface NodeTypeDefinition {
  type: string;
  label: string;
  description: string;
  icon: string;
  category: 'function' | 'matrix' | 'visualization' | 'control' | 'llm';
  defaultInputs: Omit<NodePort, 'id'>[];
  defaultOutputs: Omit<NodePort, 'id'>[];
  defaultConfig: NodeConfig;
}

/**
 * 算法模板执行结果
 */
export interface WorkflowExecutionResult {
  success: boolean;
  nodeResults: Record<string, any>;
  error?: string;
  executionTime?: number;
}

/**
 * 增强版算法模板数据
 */
export interface EnhancedWorkflow {
  id: string;
  name: string;
  description?: string;
  nodes: EnhancedWorkflowNode[];
  edges: EnhancedWorkflowEdge[];
  scenario_id?: string;
  // @AI_GENERATED: 四层主干 solution_id（算法方案）归属
  solution_id?: string;
  // @AI_GENERATED: end
  version?: number;
  version_group_id?: string;
  parent_version_id?: string;
  createdAt?: string;
  updatedAt?: string;
  // @AI_GENERATED
  // 创建来源模板 ID（"从模板新建"时记录溯源；"空白新建"或"编辑已有"时可为 null）
  source_template_id?: string | null;
  // 模板元数据（含 slot / dataset_profile_ref 等）；编辑器读取 wf.metadata 需要此字段。
  metadata?: Record<string, unknown>;
  // @AI_GENERATED: end
}

export interface EnhancedWorkflowSummary {
  id: string;
  name: string;
  description?: string;
  scenario_id?: string;
  // @AI_GENERATED: 四层主干 solution_id（算法方案）归属；历史工作流可为空
  solution_id?: string;
  // @AI_GENERATED: end
  slot?: string;
  version?: number;
  version_group_id?: string;
  nodeCount: number;
  edgeCount: number;
  createdAt?: string;
  updatedAt?: string;
}
