import { create } from 'zustand';
import type { Workflow, WorkflowNode, WorkflowEdge } from '../types/workflow';
import axios from 'axios';
import { showSuccess, showErrorNotification } from '../utils/errorHandler';
import { td } from '../utils/dataTranslation';

interface WorkflowStore {
  currentWorkflow: Workflow | null;
  isDirty: boolean;
  isLoading: boolean;
  error: string | null;

  // Workflow management
  setWorkflow: (workflow: Workflow) => void;
  updateWorkflow: (updates: Partial<Workflow>) => void;
  clearWorkflow: () => void;
  
  // Dirty state management
  markDirty: () => void;
  markClean: () => void;

  // Node and edge management
  updateNodes: (nodes: WorkflowNode[]) => void;
  updateEdges: (edges: WorkflowEdge[]) => void;

  // API operations
  saveWorkflow: () => Promise<void>;
  loadWorkflow: (id: string) => Promise<void>;
  deleteWorkflow: (id: string) => Promise<void>;
  createNewWorkflow: (name: string, description?: string) => void;
}

export const useWorkflowStore = create<WorkflowStore>((set, get) => ({
  currentWorkflow: null,
  isDirty: false,
  isLoading: false,
  error: null,

  setWorkflow: (workflow) => {
    set({ 
      currentWorkflow: workflow, 
      isDirty: false,
      error: null,
    });
  },

  updateWorkflow: (updates) => {
    const { currentWorkflow } = get();
    if (!currentWorkflow) return;

    set({
      currentWorkflow: { ...currentWorkflow, ...updates },
      isDirty: true,
    });
  },

  clearWorkflow: () => {
    set({
      currentWorkflow: null,
      isDirty: false,
      error: null,
    });
  },

  markDirty: () => {
    set({ isDirty: true });
  },

  markClean: () => {
    set({ isDirty: false });
  },

  updateNodes: (nodes) => {
    const { currentWorkflow } = get();
    if (!currentWorkflow) return;

    set({
      currentWorkflow: { ...currentWorkflow, nodes },
      isDirty: true,
    });
  },

  updateEdges: (edges) => {
    const { currentWorkflow } = get();
    if (!currentWorkflow) return;

    set({
      currentWorkflow: { ...currentWorkflow, edges },
      isDirty: true,
    });
  },

  saveWorkflow: async () => {
    const { currentWorkflow } = get();
    if (!currentWorkflow) {
      showErrorNotification(new Error(td('没有可保存的算法模板')), td('保存失败'));
      return;
    }

    set({ isLoading: true, error: null });

    try {
      const token = localStorage.getItem('token');
      const config = {
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      };

      if (currentWorkflow.id) {
        // Update existing workflow
        await axios.put(
          `/api/workflows/${currentWorkflow.id}`,
          {
            name: currentWorkflow.name,
            description: currentWorkflow.description,
            workflow: {
              nodes: currentWorkflow.nodes,
              edges: currentWorkflow.edges,
              viewport: currentWorkflow.viewport,
            },
          },
          config
        );
        showSuccess(td('算法模板保存成功'));
      } else {
        // Create new workflow
        const response = await axios.post(
          '/api/workflows',
          {
            name: currentWorkflow.name,
            description: currentWorkflow.description,
            workflow: {
              nodes: currentWorkflow.nodes,
              edges: currentWorkflow.edges,
              viewport: currentWorkflow.viewport,
            },
          },
          config
        );
        
        set({
          currentWorkflow: {
            ...currentWorkflow,
            id: response.data.id,
            createdAt: new Date(response.data.createdAt),
            updatedAt: new Date(response.data.updatedAt),
          },
        });
        showSuccess(td('算法模板创建成功'));
      }

      set({ isDirty: false, isLoading: false });
    } catch (error: any) {
      const errorMessage = td(error.response?.data?.detail || '保存算法模板失败');
      set({ error: errorMessage, isLoading: false });
      showErrorNotification(error, td('保存算法模板'));
      throw error;
    }
  },

  loadWorkflow: async (id) => {
    set({ isLoading: true, error: null });

    try {
      const token = localStorage.getItem('token');
      const config = {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      };

      const response = await axios.get(`/api/workflows/${id}`, config);
      const data = response.data;

      const workflow: Workflow = {
        id: data.id,
        name: data.name,
        description: data.description,
        nodes: data.workflow.nodes || [],
        edges: data.workflow.edges || [],
        viewport: data.workflow.viewport || { x: 0, y: 0, zoom: 1 },
        createdAt: new Date(data.createdAt),
        updatedAt: new Date(data.updatedAt),
      };

      set({
        currentWorkflow: workflow,
        isDirty: false,
        isLoading: false,
      });
      showSuccess(td('算法模板加载成功'));
    } catch (error: any) {
      const errorMessage = td(error.response?.data?.detail || '加载算法模板失败');
      set({ error: errorMessage, isLoading: false });
      showErrorNotification(error, td('加载算法模板'));
      throw error;
    }
  },

  deleteWorkflow: async (id) => {
    set({ isLoading: true, error: null });

    try {
      const token = localStorage.getItem('token');
      const config = {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      };

      await axios.delete(`/api/workflows/${id}`, config);
      
      // Clear current workflow if it's the one being deleted
      const { currentWorkflow } = get();
      if (currentWorkflow?.id === id) {
        set({ currentWorkflow: null });
      }

      set({ isLoading: false });
      showSuccess(td('算法模板删除成功'));
    } catch (error: any) {
      const errorMessage = td(error.response?.data?.detail || '删除算法模板失败');
      set({ error: errorMessage, isLoading: false });
      showErrorNotification(error, td('删除算法模板'));
      throw error;
    }
  },

  createNewWorkflow: (name, description) => {
    const newWorkflow: Workflow = {
      id: '',
      name,
      description,
      nodes: [],
      edges: [],
      viewport: { x: 0, y: 0, zoom: 1 },
    };

    set({
      currentWorkflow: newWorkflow,
      isDirty: true,
      error: null,
    });
  },
}));
