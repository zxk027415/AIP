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
  createdAt?: string;
  updatedAt?: string;
}

export interface EnhancedWorkflowSummary {
  id: string;
  name: string;
  description?: string;
  nodeCount: number;
  edgeCount: number;
  createdAt?: string;
  updatedAt?: string;
}
