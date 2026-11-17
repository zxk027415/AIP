/**
 * schedulerApi.ts — 数据管线调度器 API 客户端
 *
 * Endpoints:
 *   GET  /api/scheduler/status             — 获取所有管线运行状态
 *   POST /api/scheduler/{pipeline}/start   — 启动指定管线
 *   POST /api/scheduler/{pipeline}/stop    — 停止指定管线
 */

import api from './api';

export type Pipeline = 'load_forecast' | 'pv_fault';

export interface FailureRecord {
  task_id: string;        // 任务 ID
  trigger_time: string;   // 触发时间（ISO 8601）
  error_message: string;  // 错误信息
  is_retry: boolean;      // 是否为重试执行
}

export interface TaskStatus {
  task_id: string;                       // 任务标识
  last_execution_time: string | null;    // 上次执行时间
  next_scheduled_time: string | null;    // 下次计划时间
  last_result: 'success' | 'failed' | 'skipped';  // 上次结果
  recent_failures: FailureRecord[];      // 最近失败记录（最多 20 条）
}

export interface PipelineStatus {
  running: boolean;         // 是否运行中
  tasks: TaskStatus[];      // 任务列表
}

export interface SchedulerStatusResponse {
  pipelines: Record<Pipeline, PipelineStatus>;
}

export const getSchedulerStatus = (): Promise<SchedulerStatusResponse> =>
  api.get('/scheduler/status').then((res: any) => res?.data ?? res);

export const startPipeline = (pipeline: Pipeline): Promise<{ status: string; pipeline: string }> =>
  api.post(`/scheduler/${pipeline}/start`).then((res: any) => res?.data ?? res);

export const stopPipeline = (pipeline: Pipeline): Promise<{ status: string; pipeline: string }> =>
  api.post(`/scheduler/${pipeline}/stop`).then((res: any) => res?.data ?? res);
