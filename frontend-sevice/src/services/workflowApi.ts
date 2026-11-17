import axios from 'axios';
import type {
  Workflow,
  WorkflowListItem,
  WorkflowExecution,
  ExecutionResult,
} from '../types/workflow';
import type { ValidationResult } from '../types/validation';
import type { WorkflowTemplate } from '../types/template';

// 创建 axios 实例
const workflowApi = axios.create({
  baseURL: '/api',
  timeout: 30000, // 算法模板执行可能需要更长时间
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
workflowApi.interceptors.request.use(
  (config) => {
    // 可以在这里添加 token 等认证信息
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
workflowApi.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    console.error('Workflow API Error:', error);
    
    // 统一错误处理
    if (error.response) {
      const { status, data } = error.response;
      
      switch (status) {
        case 401:
          // 未授权，可能需要重新登录
          console.error('未授权访问');
          break;
        case 404:
          console.error('资源不存在');
          break;
        case 500:
          console.error('服务器错误');
          break;
        default:
          console.error('请求失败:', data?.message || error.message);
      }
    }
    
    return Promise.reject(error);
  }
);

// 算法模板 CRUD API
export const workflows = {
  /**
   * 创建算法模板
   */
  create: (data: {
    name: string;
    description?: string;
    workflow: Partial<Workflow>;
  }): Promise<Workflow> => {
    return workflowApi.post('/workflows', data);
  },

  /**
   * 获取算法模板列表
   */
  list: (params?: {
    page?: number;
    pageSize?: number;
    search?: string;
  }): Promise<WorkflowListItem[]> => {
    return workflowApi.get('/workflows', { params });
  },

  /**
   * 获取算法模板详情
   */
  get: (id: number): Promise<Workflow> => {
    return workflowApi.get(`/workflows/${id}`);
  },

  /**
   * 更新算法模板
   */
  update: (
    id: number,
    data: {
      name?: string;
      description?: string;
      workflow?: Partial<Workflow>;
    }
  ): Promise<Workflow> => {
    return workflowApi.put(`/workflows/${id}`, data);
  },

  /**
   * 删除算法模板
   */
  delete: (id: number): Promise<{ message: string }> => {
    return workflowApi.delete(`/workflows/${id}`);
  },
};

// 算法模板验证 API
export const validation = {
  /**
   * 验证算法模板
   */
  validate: (id: number): Promise<ValidationResult> => {
    return workflowApi.post(`/workflows/${id}/validate`);
  },

  /**
   * 验证算法模板定义（不需要保存）
   */
  validateDefinition: (workflow: Partial<Workflow>): Promise<ValidationResult> => {
    return workflowApi.post('/workflows/validate', { workflow });
  },
};

// 算法模板执行 API
export const execution = {
  /**
   * 执行算法模板
   */
  execute: (id: number): Promise<{
    executionId: number;
    result: ExecutionResult;
  }> => {
    return workflowApi.post(`/workflows/${id}/execute`);
  },

  /**
   * 获取执行历史列表
   */
  listExecutions: (params?: {
    workflowId?: number;
    status?: string;
    page?: number;
    pageSize?: number;
  }): Promise<WorkflowExecution[]> => {
    return workflowApi.get('/workflows/executions/', { params });
  },

  /**
   * 获取执行详情
   */
  getExecution: (id: number): Promise<WorkflowExecution> => {
    return workflowApi.get(`/workflows/executions/${id}`);
  },

  /**
   * 取消执行（如果支持）
   */
  cancelExecution: (id: number): Promise<{ message: string }> => {
    return workflowApi.post(`/workflows/executions/${id}/cancel`);
  },
};

// 模板 API
export const templates = {
  /**
   * 获取模板列表
   */
  list: (params?: {
    category?: string;
  }): Promise<WorkflowTemplate[]> => {
    return workflowApi.get('/templates', { params });
  },

  /**
   * 获取模板详情
   */
  get: (id: string): Promise<WorkflowTemplate> => {
    return workflowApi.get(`/templates/${id}`);
  },

  /**
   * 从模板创建算法模板
   */
  createFromTemplate: (
    templateId: string,
    data: {
      name: string;
      description?: string;
    }
  ): Promise<Workflow> => {
    return workflowApi.post(`/templates/${templateId}/create`, data);
  },
};

// 导出统一的 API 对象
export default {
  workflows,
  validation,
  execution,
  templates,
};

// 导出 axios 实例，以便在其他地方使用
export { workflowApi };
