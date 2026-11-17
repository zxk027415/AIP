// @AI_GENERATED
/**
 * 项目 scope 守卫：URL scope、请求代次与缓存生命周期。
 *
 * 设计依据：design.md §9（响应回显 + 前端二次校验）、§11.3（切换即清空 + 丢弃迟到响应）、
 * §26.1 ProjectScopeGuard；requirements.md R1.1、R1.3–R1.5、R1.8–R1.9。
 *
 * 职责：
 * - 从 URL（路由参数优先，其次 query）解析 `projectId` / `slot` / `datasetVersionId`，保留深链接。
 * - 维护单调递增的请求代次 `generation`：scope 变化或手动 refresh 时 +1。
 * - 消费者用 `isCurrentGeneration(gen)` 丢弃由旧 scope 发起的迟到响应；scope 变化即视为
 *   需要清空可见状态、错误、缓存与可写动作（由消费者依赖 `generation` 重新取数实现）。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { ReactNode } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import type { ProjectScope } from '../pv-fault/types/scope';

export interface ProjectScopeContextValue {
  /** 当前已解析的 scope。projectId 缺失时为空串（消费者需判空）。 */
  scope: ProjectScope;
  /** scope 稳定字符串键，用作 effect 依赖与缓存键。 */
  scopeKey: string;
  /** 请求代次；scope 变化或 refresh() 时 +1。 */
  generation: number;
  /** 判断某个代次是否仍是当前代次（用于丢弃迟到响应）。 */
  isCurrentGeneration: (gen: number) => boolean;
  /** 读取当前代次（供发起请求时捕获）。 */
  currentGeneration: () => number;
  /** 手动刷新当前项目：+1 代次，触发重新取数并丢弃在途旧响应。 */
  refresh: () => void;
}

const ProjectScopeContext = createContext<ProjectScopeContextValue | null>(null);

function firstNonEmpty(...values: Array<string | null | undefined>): string {
  for (const value of values) {
    const text = (value ?? '').trim();
    if (text) return text;
  }
  return '';
}

export function ProjectScopeProvider({ children }: { children: ReactNode }): JSX.Element {
  const params = useParams();
  const [searchParams] = useSearchParams();

  // 路由参数优先（/projects/:projectId/...），其次 query（兼容页深链接 ?project_id=）。
  const projectId = firstNonEmpty(params.projectId, searchParams.get('project_id'));
  const slot = firstNonEmpty(params.slot, searchParams.get('slot')) || undefined;
  const datasetVersionId = firstNonEmpty(searchParams.get('dataset_version_id')) || undefined;

  const scope = useMemo<ProjectScope>(
    () => ({ projectId, slot, datasetVersionId }),
    [projectId, slot, datasetVersionId],
  );
  const scopeKey = `${projectId}|${slot ?? ''}|${datasetVersionId ?? ''}`;

  const generationRef = useRef(0);
  const [generation, setGeneration] = useState(0);
  const initialScopeKeyRef = useRef<string | null>(null);

  // scope 变化即视为新代次：清空旧上下文可见状态由消费者依赖 generation 触发。
  // 初次挂载不 bump（初始 generation=0 已有效），仅在 scopeKey **真正变化**后 +1，
  // 避免挂载时的冗余重取风暴（叠加 React.StrictMode 双调用会放大为多次重复请求）。
  useEffect(() => {
    if (initialScopeKeyRef.current === null) {
      initialScopeKeyRef.current = scopeKey;
      return;
    }
    if (initialScopeKeyRef.current === scopeKey) {
      return;
    }
    initialScopeKeyRef.current = scopeKey;
    generationRef.current += 1;
    setGeneration(generationRef.current);
  }, [scopeKey]);

  const isCurrentGeneration = useCallback((gen: number) => gen === generationRef.current, []);
  const currentGeneration = useCallback(() => generationRef.current, []);
  const refresh = useCallback(() => {
    generationRef.current += 1;
    setGeneration(generationRef.current);
  }, []);

  const value = useMemo<ProjectScopeContextValue>(
    () => ({ scope, scopeKey, generation, isCurrentGeneration, currentGeneration, refresh }),
    [scope, scopeKey, generation, isCurrentGeneration, currentGeneration, refresh],
  );

  return <ProjectScopeContext.Provider value={value}>{children}</ProjectScopeContext.Provider>;
}

/** 读取项目 scope 守卫上下文；必须在 ProjectScopeProvider 内使用。 */
export function useProjectScope(): ProjectScopeContextValue {
  const ctx = useContext(ProjectScopeContext);
  if (ctx === null) {
    throw new Error('useProjectScope 必须在 <ProjectScopeProvider> 内使用');
  }
  return ctx;
}

/** 便捷 hook：仅需要当前 scope 时使用。 */
export function useCurrentScope(): ProjectScope {
  return useProjectScope().scope;
}

// @AI_GENERATED: end
