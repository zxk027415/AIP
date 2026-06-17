import type { DataType } from './data';

/**
 * 位置坐标
 */
export interface Position {
  x: number;
  y: number;
}

/**
 * 视口配置
 */
export interface Viewport {
  x: number;
  y: number;
  zoom: number;
}

/**
 * 端口定义
 */
export interface Port {
  id: string;
  name: string;
  type: DataType;
  required: boolean;
}

/**
 * 端口ID（用于连接）
 */
export interface PortId {
  moduleId: string;
  portName: string;
}

/**
 * 算法模板节点数据
 */
export interface WorkflowNodeData {
  label: string;
  functionId?: string;
  operation?: string;
  chartType?: string;
  parameters: Record<string, any>;
  inputs: Port[];
  outputs: Port[];
  icon?: string;
  error?: string;
  config?: Record<string, any>;
}

/**
 * 算法模板节点（React Flow格式）
 */
export interface WorkflowNode {
  id: string;
  type: 'function' | 'matrix' | 'visualization';
  position: Position;
  data: WorkflowNodeData;
}

/**
 * 算法模板边（React Flow格式）
 */
export interface WorkflowEdge {
  id: string;
  source: string;
  sourceHandle: string;
  target: string;
  targetHandle: string;
}

/**
 * 模块实例（旧格式，保持向后兼容）
 */
export interface ModuleInstance {
  id: string;
  type: string;
  position: Position;
  parameters: Record<string, any>;
  inputs: Port[];
  outputs: Port[];
}

/**
 * 连接（旧格式，保持向后兼容）
 */
export interface Connection {
  id: string;
  source: PortId;
  target: PortId;
}

/**
 * 算法模板元数据
 */
export interface WorkflowMetadata {
  author?: string;
  version: string;
  tags: string[];
  isTemplate: boolean;
}

/**
 * 算法模板
 */
export interface Workflow {
  id: string;
  name: string;
  description?: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  viewport?: Viewport;
  metadata?: WorkflowMetadata;
  createdAt?: Date;
  updatedAt?: Date;
  // 保持向后兼容
  modules?: ModuleInstance[];
  connections?: Connection[];
}

/**
 * 节点执行状态
 */
export type NodeExecutionStatus = 'pending' | 'running' | 'completed' | 'failed';

/**
 * 节点执行结果
 */
export interface NodeResult {
  nodeId: string;
  status: NodeExecutionStatus;
  output?: any;
  error?: string;
  executionTime: number;
  startTime?: string;
}

/**
 * 算法模板执行状态
 */
export type WorkflowExecutionStatus = 'pending' | 'running' | 'completed' | 'failed';

/**
 * 算法模板执行结果
 */
export interface ExecutionResult {
  workflowId: string;
  executionId: string;
  status: WorkflowExecutionStatus;
  startTime: string;
  endTime?: string;
  nodeResults: Record<string, NodeResult>;
  error?: string;
}

/**
 * 算法模板执行历史记录
 */
export interface WorkflowExecution {
  id: string;
  workflowId: string;
  userId: string;
  status: WorkflowExecutionStatus;
  startTime: string;
  endTime?: string;
  executionData?: ExecutionResult;
  errorMessage?: string;
}

/**
 * 算法模板列表项（用于列表展示）
 */
export interface WorkflowListItem {
  id: number;
  name: string;
  description?: string;
  createdAt: string;
  updatedAt: string;
}
