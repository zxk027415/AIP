// @AI_GENERATED
/**
 * 负荷预测训练 API 服务层
 *
 * 封装后端 /api/load-forecast/* 端点的调用方法。
 * 使用项目共享的 axios 实例，响应拦截器已自动解包 response.data。
 */
import api from './api';
import type {
  TrainingParams,
  BacktestParams,
  ScenariosResponse,
  TrainResponse,
  TaskStatusResponse,
  BacktestResult,
} from '../types/load-forecast';

export const loadForecastApi = {
  /** 获取所有预测场景配置 GET /load-forecast/scenarios */
  getScenarios: (): Promise<ScenariosResponse> =>
    api.get('/load-forecast/scenarios'),

  /** 启动模型训练 POST /load-forecast/train */
  startTraining: (params: TrainingParams): Promise<TrainResponse> =>
    api.post('/load-forecast/train', params),

  /** 查询训练任务状态 GET /load-forecast/status/{task_id} */
  getTaskStatus: (taskId: string): Promise<TaskStatusResponse> =>
    api.get(`/load-forecast/status/${taskId}`),

  /** 启动回测评估 POST /load-forecast/backtest */
  startBacktest: (params: BacktestParams): Promise<BacktestResult> =>
    api.post('/load-forecast/backtest', params),
};
// @AI_GENERATED: end
