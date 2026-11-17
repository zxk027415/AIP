// @AI_GENERATED
/**
 * scoped API 客户端：响应 scope 二次校验 + 丢弃迟到响应。
 *
 * 设计依据：design.md §9（UI 渲染前二次校验响应 scope）、§11.3（丢弃旧 scope 迟到响应）、
 * §26.5（统一错误响应）；requirements.md R1.2、R1.3、R1.8、R1.9。
 *
 * 契约：
 * - 每个请求捕获发起时的代次；响应回来若已不是当前代次 → StaleResponseError（丢弃，不渲染）。
 * - 响应必须回显与请求一致的 project_id（及 scope 内的 slot / dataset_version_id），
 *   缺失或不一致 → ScopeMismatchError（fail-closed，不渲染 / 不写入）。
 * - 后端统一错误响应体 → ScopedApiError，保留 reason_code / message / next_action / category 等。
 */

import { useCallback, useMemo } from 'react';
import type { AxiosError } from 'axios';
import api from './api';
import { useProjectScope } from '../contexts/ProjectScopeContext';
import type { ProjectScope, ScopeEcho, ScopedErrorPayload } from '../pv-fault/types/scope';

// 注意：tsconfig 开启 erasableSyntaxOnly，禁止构造器参数属性，字段需显式声明后在构造体内赋值。
export class StaleResponseError extends Error {
  readonly generation: number;
  constructor(generation: number) {
    super('响应对应的 scope 代次已过期，已丢弃');
    this.name = 'StaleResponseError';
    this.generation = generation;
  }
}

export class ScopeMismatchError extends Error {
  readonly mismatchedFields: string[];
  readonly expected: ScopeEcho;
  readonly received: ScopeEcho;
  constructor(mismatchedFields: string[], expected: ScopeEcho, received: ScopeEcho) {
    super(`响应 scope 与当前请求不一致或缺失：${mismatchedFields.join(', ')}`);
    this.name = 'ScopeMismatchError';
    this.mismatchedFields = mismatchedFields;
    this.expected = expected;
    this.received = received;
  }
}

export class ScopedApiError extends Error {
  readonly payload: ScopedErrorPayload | null;
  readonly status?: number;
  constructor(payload: ScopedErrorPayload | null, status?: number) {
    super(payload?.message || '请求失败');
    this.name = 'ScopedApiError';
    this.payload = payload;
    this.status = status;
  }
}

export function scopeToEcho(scope: ProjectScope): ScopeEcho {
  const echo: ScopeEcho = { project_id: scope.projectId };
  if (scope.slot) echo.slot = scope.slot;
  if (scope.datasetVersionId) echo.dataset_version_id = scope.datasetVersionId;
  return echo;
}

/** 返回响应中与期望 scope 不一致或缺失的字段名（空数组表示一致）。 */
export function findScopeMismatches(scope: ProjectScope, data: unknown): string[] {
  if (data === null || typeof data !== 'object' || Array.isArray(data)) {
    // 非对象响应无法校验回显；调用方应对这类接口显式关闭校验。
    return ['project_id'];
  }
  const record = data as Record<string, unknown>;
  const mismatches: string[] = [];
  const check = (field: keyof ScopeEcho, expected?: string) => {
    if (!expected) return;
    const actual = record[field];
    if (actual === undefined || actual === null || String(actual) !== String(expected)) {
      mismatches.push(field);
    }
  };
  check('project_id', scope.projectId || undefined);
  check('slot', scope.slot);
  check('dataset_version_id', scope.datasetVersionId);
  return mismatches;
}

function toScopedApiError(error: unknown): ScopedApiError {
  const axiosError = error as AxiosError<{ detail?: ScopedErrorPayload | string }>;
  const status = axiosError.response?.status;
  const detail = axiosError.response?.data?.detail;
  if (detail && typeof detail === 'object') {
    return new ScopedApiError(detail as ScopedErrorPayload, status);
  }
  if (typeof detail === 'string') {
    return new ScopedApiError({ reason_code: 'error', message: detail }, status);
  }
  return new ScopedApiError({ reason_code: 'network_error', message: '网络或服务异常' }, status);
}

export interface ScopedRequestOptions {
  method: 'get' | 'post' | 'put' | 'delete';
  url: string;
  scope: ProjectScope;
  data?: unknown;
  params?: Record<string, unknown>;
  /** 是否要求响应回显 scope（默认 true）。列表 / 非 scoped 接口可关闭。 */
  expectScopeEcho?: boolean;
  /** 发起时捕获的代次。 */
  capturedGeneration?: number;
  /** 判断代次是否仍为当前（用于丢弃迟到响应）。 */
  isCurrentGeneration?: (gen: number) => boolean;
}

export async function scopedRequest<T = unknown>(opts: ScopedRequestOptions): Promise<T> {
  const { method, url, scope, data, params, expectScopeEcho = true } = opts;
  let result: unknown;
  try {
    // api 的响应拦截器已返回 response.data。
    result = await api.request({ method, url, data, params });
  } catch (error) {
    throw toScopedApiError(error);
  }

  // 丢弃迟到响应：请求发起后 scope 已切换。
  if (
    opts.capturedGeneration !== undefined &&
    opts.isCurrentGeneration &&
    !opts.isCurrentGeneration(opts.capturedGeneration)
  ) {
    throw new StaleResponseError(opts.capturedGeneration);
  }

  if (expectScopeEcho) {
    const mismatches = findScopeMismatches(scope, result);
    if (mismatches.length > 0) {
      const received: ScopeEcho =
        result && typeof result === 'object'
          ? {
              project_id: (result as Record<string, unknown>).project_id as string | undefined,
              slot: (result as Record<string, unknown>).slot as string | undefined,
              dataset_version_id: (result as Record<string, unknown>).dataset_version_id as
                | string
                | undefined,
            }
          : {};
      throw new ScopeMismatchError(mismatches, scopeToEcho(scope), received);
    }
  }

  return result as T;
}

export interface ScopedApiClient {
  scope: ProjectScope;
  get: <T = unknown>(url: string, opts?: Partial<ScopedRequestOptions>) => Promise<T>;
  post: <T = unknown>(url: string, data?: unknown, opts?: Partial<ScopedRequestOptions>) => Promise<T>;
  put: <T = unknown>(url: string, data?: unknown, opts?: Partial<ScopedRequestOptions>) => Promise<T>;
  del: <T = unknown>(url: string, opts?: Partial<ScopedRequestOptions>) => Promise<T>;
}

/**
 * 绑定当前 ProjectScope 守卫的 scoped 客户端 hook。
 * 每次调用捕获当前代次，响应回来自动校验 scope 并丢弃迟到响应。
 */
export function useScopedApi(): ScopedApiClient {
  const { scope, currentGeneration, isCurrentGeneration } = useProjectScope();

  const get = useCallback(
    <T = unknown>(url: string, opts?: Partial<ScopedRequestOptions>) =>
      scopedRequest<T>({
        method: 'get',
        url,
        scope,
        capturedGeneration: currentGeneration(),
        isCurrentGeneration,
        ...opts,
      }),
    [scope, currentGeneration, isCurrentGeneration],
  );

  const post = useCallback(
    <T = unknown>(url: string, data?: unknown, opts?: Partial<ScopedRequestOptions>) =>
      scopedRequest<T>({
        method: 'post',
        url,
        scope,
        data,
        capturedGeneration: currentGeneration(),
        isCurrentGeneration,
        ...opts,
      }),
    [scope, currentGeneration, isCurrentGeneration],
  );

  const put = useCallback(
    <T = unknown>(url: string, data?: unknown, opts?: Partial<ScopedRequestOptions>) =>
      scopedRequest<T>({
        method: 'put',
        url,
        scope,
        data,
        capturedGeneration: currentGeneration(),
        isCurrentGeneration,
        ...opts,
      }),
    [scope, currentGeneration, isCurrentGeneration],
  );

  const del = useCallback(
    <T = unknown>(url: string, opts?: Partial<ScopedRequestOptions>) =>
      scopedRequest<T>({
        method: 'delete',
        url,
        scope,
        capturedGeneration: currentGeneration(),
        isCurrentGeneration,
        ...opts,
      }),
    [scope, currentGeneration, isCurrentGeneration],
  );

  return useMemo<ScopedApiClient>(() => ({ scope, get, post, put, del }), [scope, get, post, put, del]);
}

// @AI_GENERATED: end
