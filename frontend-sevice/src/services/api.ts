import axios from 'axios';
import i18n from '../i18n';
import type { FunctionDefinition, Category } from '../types/function';

// 创建 axios 实例
const api = axios.create({
  baseURL: '/api',
  timeout: 120000,  // 增加到 120 秒，支持 LLM 调用
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const lang = (localStorage.getItem('lang') || i18n.language || 'zh').toLowerCase().startsWith('en')
      ? 'en'
      : 'zh';
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>)['X-App-Lang'] = lang;
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    console.error('API Error:', error);
    return Promise.reject(error);
  }
);

// API 方法
export const healthCheck = (): Promise<any> => api.get('/health');

// 系统监控 API
export const systemApi = {
  // 获取系统性能指标
  getMetrics: (): Promise<any> => api.get('/system/metrics'),
  
  // 获取系统统计数据
  getStatistics: (): Promise<any> => api.get('/system/statistics'),
  
  // 获取数据库信息
  getDatabaseInfo: (): Promise<any> => api.get('/system/database-info'),
  
  // 获取所有服务状态
  getAllServiceStatus: (): Promise<any> => api.get('/system/service-status'),
  
  // 获取指定服务状态
  getServiceStatus: (serviceName: string): Promise<any> => api.get(`/system/service-status/${serviceName}`),
};

// AI算法库 API
export const functionApi = {
  // 获取所有函数
  getAllFunctions: (): Promise<FunctionDefinition[]> => api.get('/functions/'),
  
  // 获取函数定义
  getFunction: (functionId: string): Promise<FunctionDefinition> => api.get(`/functions/${functionId}`),
  
  // 搜索函数
  searchFunctions: (query?: string, category?: string): Promise<FunctionDefinition[]> => {
    const params = new URLSearchParams();
    if (query) params.append('q', query);
    if (category) params.append('category', category);
    return api.get(`/functions/search/?${params.toString()}`);
  },
  
  // 获取分类下的函数
  getFunctionsByCategory: (categoryId: string): Promise<FunctionDefinition[]> => api.get(`/functions/category/${categoryId}`),
  
  // 获取所有分类
  getCategories: (): Promise<Category[]> => api.get('/functions/categories/'),
  
  // 获取分类信息
  getCategory: (categoryId: string): Promise<Category> => api.get(`/functions/categories/${categoryId}`),
};

// 导出算法模板 API
export { default as workflowApiClient, workflows, validation, execution, templates } from './workflowApi';

// 导出 LLM 配置 API
export { llmConfigApi, GLM_PRESET } from './llmConfigApi';
export type {
  LLMProvider,
  LLMConfig,
  LLMConfigCreateRequest,
  LLMConfigUpdateRequest,
  LLMTestRequest,
  LLMTestResponse,
  LLMConfigsResponse,
} from './llmConfigApi';

export default api;
