/**
 * Workflow Editor Store
 * 标准算法模板编辑器状态管理（独立于增强版）
 */

import { create } from 'zustand';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import type { EnhancedWorkflowNode, EnhancedWorkflowEdge } from '../types/workflow-enhanced';

interface WorkflowEditorStore {
  // 算法模板数据
  nodes: EnhancedWorkflowNode[];
  edges: EnhancedWorkflowEdge[];
  selectedNodeId: string | null;
  
  // 算法模板元数据
  workflowId: string | null;
  workflowName: string;
  workflowDescription: string;
  
  // UI 状态
  isExecuting: boolean;
  executionResult: any | null;
  
  // Actions
  setNodes: (nodes: EnhancedWorkflowNode[]) => void;
  setEdges: (edges: EnhancedWorkflowEdge[]) => void;
  setSelectedNodeId: (nodeId: string | null) => void;
  addNode: (node: EnhancedWorkflowNode) => void;
  updateNode: (nodeId: string, data: Partial<EnhancedWorkflowNode['data']>) => void;
  deleteNode: (nodeId: string) => void;
  setWorkflowName: (name: string) => void;
  setWorkflowDescription: (description: string) => void;
  setIsExecuting: (isExecuting: boolean) => void;
  setExecutionResult: (result: any) => void;
  clearWorkflow: () => void;
  loadWorkflow: (workflowId: string, nodes: EnhancedWorkflowNode[], edges: EnhancedWorkflowEdge[], name: string, description: string) => void;
}

export const useWorkflowEditorStore = create<WorkflowEditorStore>((set) => ({
  // Initial state
  nodes: [],
  edges: [],
  selectedNodeId: null,
  workflowId: null,
  // @AI_GENERATED
  workflowName: td('未命名算法模板'),
  // @AI_GENERATED: end
  workflowDescription: '',
  isExecuting: false,
  executionResult: null,
  
  // Actions
  setNodes: (nodes) => set({ nodes }),
  
  setEdges: (edges) => set({ edges }),
  
  setSelectedNodeId: (nodeId) => set({ selectedNodeId: nodeId }),
  
  addNode: (node) => set((state) => ({
    nodes: [...state.nodes, node],
  })),
  
  updateNode: (nodeId, data) => set((state) => ({
    nodes: state.nodes.map((node) =>
      node.id === nodeId
        ? { ...node, data: { ...node.data, ...data } }
        : node
    ),
  })),
  
  deleteNode: (nodeId) => set((state) => ({
    nodes: state.nodes.filter((node) => node.id !== nodeId),
    edges: state.edges.filter(
      (edge) => edge.source !== nodeId && edge.target !== nodeId
    ),
    selectedNodeId: state.selectedNodeId === nodeId ? null : state.selectedNodeId,
  })),
  
  setWorkflowName: (name) => set({ workflowName: name }),
  
  setWorkflowDescription: (description) => set({ workflowDescription: description }),
  
  setIsExecuting: (isExecuting) => set({ isExecuting }),
  
  setExecutionResult: (result) => set({ executionResult: result }),
  
  clearWorkflow: () => set({
    nodes: [],
    edges: [],
    selectedNodeId: null,
    workflowId: null,
    // @AI_GENERATED
    workflowName: td('未命名算法模板'),
    // @AI_GENERATED: end
    workflowDescription: '',
    isExecuting: false,
    executionResult: null,
  }),
  
  loadWorkflow: (workflowId, nodes, edges, name, description) => set({
    workflowId,
    nodes,
    edges,
    workflowName: name,
    workflowDescription: description,
    selectedNodeId: null,
    isExecuting: false,
    executionResult: null,
  }),
}));
