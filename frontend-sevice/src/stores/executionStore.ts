import { create } from 'zustand';
import type { ExecutionResult, NodeResult, WorkflowExecutionStatus } from '../types/workflow';
import axios from 'axios';
import { showSuccess, showErrorNotification } from '../utils/errorHandler';
import { td } from '../utils/dataTranslation';

interface ExecutionStore {
  currentExecution: ExecutionResult | null;
  isExecuting: boolean;
  error: string | null;

  // Execution management
  executeWorkflow: (workflowId: string) => Promise<void>;
  clearExecution: () => void;
  
  // Node status helpers
  getNodeStatus: (nodeId: string) => WorkflowExecutionStatus;
  getNodeResult: (nodeId: string) => NodeResult | null;
}

export const useExecutionStore = create<ExecutionStore>((set, get) => ({
  currentExecution: null,
  isExecuting: false,
  error: null,

  executeWorkflow: async (workflowId) => {
    set({ isExecuting: true, error: null, currentExecution: null });

    try {
      const token = localStorage.getItem('token');
      const config = {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      };

      // Execute workflow
      const response = await axios.post(
        `/api/workflows/${workflowId}/execute`,
        {},
        config
      );

      const executionResult: ExecutionResult = response.data.result;

      set({
        currentExecution: executionResult,
        isExecuting: false,
      });

      if (executionResult.status === 'completed') {
        showSuccess(td('算法模板执行成功'));
      } else if (executionResult.status === 'failed') {
        showErrorNotification(
          new Error(td(executionResult.error || '未知错误')),
          td('算法模板执行失败')
        );
      }
    } catch (error: any) {
      const errorMessage = td(error.response?.data?.detail || '执行算法模板失败');
      set({ 
        error: errorMessage, 
        isExecuting: false,
        currentExecution: null,
      });
      showErrorNotification(error, td('执行算法模板'));
      throw error;
    }
  },

  clearExecution: () => {
    set({
      currentExecution: null,
      isExecuting: false,
      error: null,
    });
  },

  getNodeStatus: (nodeId) => {
    const { currentExecution } = get();
    if (!currentExecution || !currentExecution.nodeResults[nodeId]) {
      return 'pending';
    }
    return currentExecution.nodeResults[nodeId].status;
  },

  getNodeResult: (nodeId) => {
    const { currentExecution } = get();
    if (!currentExecution || !currentExecution.nodeResults[nodeId]) {
      return null;
    }
    return currentExecution.nodeResults[nodeId];
  },
}));
