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

  // @AI_GENERATED
  // 「从模板新建」溯源：sourceTemplateId — 来源模板的 workflow_id；
  // sourceTemplateName — 来源模板的名称快照，用于「未改名」保存前置校验（需求 7.6）
  sourceTemplateId: string | null;
  sourceTemplateName: string | null;
  // @AI_GENERATED: end

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
  // @AI_GENERATED
  // 设置模板来源信息（loadWorkflow 后由页面显式调用；两个字段允许分别更新，
  // 例如先设置 id 再异步补齐 name）
  setSourceTemplateInfo: (id: string | null, name: string | null) => void;
  // @AI_GENERATED: end
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
  // @AI_GENERATED
  sourceTemplateId: null,
  sourceTemplateName: null,
  // @AI_GENERATED: end
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
    // @AI_GENERATED
    sourceTemplateId: null,
    sourceTemplateName: null,
    // @AI_GENERATED: end
    isExecuting: false,
    executionResult: null,
  }),
  
  loadWorkflow: (workflowId, nodes, edges, name, description) => set({
    workflowId,
    nodes,
    edges,
    workflowName: name,
    workflowDescription: description,
    // @AI_GENERATED
    // 每次装载工作流都重置模板来源；调用方（编辑器页面）在需要时再显式 setSourceTemplateInfo
    sourceTemplateId: null,
    sourceTemplateName: null,
    // @AI_GENERATED: end
    selectedNodeId: null,
    isExecuting: false,
    executionResult: null,
  }),

  // @AI_GENERATED
  setSourceTemplateInfo: (id, name) => set((state) => ({
    sourceTemplateId: id ?? null,
    // 只有传入非 null 的 name 才覆盖；避免异步补齐 name 时把已存在的 name 清空
    sourceTemplateName: name === null && id !== null ? state.sourceTemplateName : name,
  })),
  // @AI_GENERATED: end
}));
