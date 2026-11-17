// @AI_GENERATED
/**
 * 跨页旅程上下文 store（四层主干 + 最近访问）。
 *
 * 设计依据：design.md §33.3（上下文解析优先级 URL → 页内选择 → store → 显式空态）、
 * §11.3（切换即清空下游）、§35（继续上次 + 最近列表）；requirements.md R1.1、R1.3–R1.5、R2.1、R2.8。
 *
 * 参照既有 `workflowRunNavStore` 与使用 persist 的 store（pipelineExecutionStore），
 * 用 zustand + persist 落地到 localStorage（与侧栏宽度一致的持久化习惯）。
 * 本 store 是「兜底」层级：URL 与页内选择优先，store 仅在两者缺失时补默认，且绝不静默默认 slot。
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type JourneyRecentKind = 'scenario' | 'solution' | 'workflow' | 'project' | 'execution';

export interface JourneyRecent {
  kind: JourneyRecentKind;
  id: string;
  label: string;
  href: string;
  scenarioId?: string;
  solutionId?: string;
  projectId?: string;
  slot?: string;
  workflowId?: string;
  at: number;
}

/** 四层主干的切换层级（用于切换时清空下游）。 */
export type SpineLevel = 'scenario' | 'solution' | 'project' | 'slot';

export interface JourneyContextState {
  scenarioId?: string;
  solutionId?: string;
  projectId?: string;
  slot?: string;
  /** 最近打开的场景 / 方案 / 工作流 / 项目 / execution（去重、倒序）。 */
  recents: JourneyRecent[];
  /** 最近一次所在的阶段路由，用于「继续上次」。 */
  lastHref?: string;

  /** 合并设置主干（仅覆盖传入字段）。 */
  setContext: (partial: Partial<Pick<JourneyContextState, 'scenarioId' | 'solutionId' | 'projectId' | 'slot' | 'lastHref'>>) => void;
  /** 在某层就地切换：设置该层并清空其下游（§11.3）。 */
  switchLevel: (level: SpineLevel, value: string | undefined) => void;
  /** 追加一条最近访问（按 kind+id 去重，保留最新，最多 20 条）。 */
  pushRecent: (recent: Omit<JourneyRecent, 'at'>) => void;
  /** 清空全部主干与最近（登出等）。 */
  reset: () => void;
}

const MAX_RECENTS = 20;

export const useJourneyContextStore = create<JourneyContextState>()(
  persist(
    (set) => ({
      scenarioId: undefined,
      solutionId: undefined,
      projectId: undefined,
      slot: undefined,
      recents: [],
      lastHref: undefined,

      setContext: (partial) => set((state) => ({ ...state, ...partial })),

      switchLevel: (level, value) =>
        set((state) => {
          const next: Partial<JourneyContextState> = {};
          if (level === 'scenario') {
            next.scenarioId = value;
            next.solutionId = undefined;
            next.projectId = undefined;
            next.slot = undefined;
          } else if (level === 'solution') {
            next.solutionId = value;
            next.projectId = undefined;
            next.slot = undefined;
          } else if (level === 'project') {
            next.projectId = value;
            next.slot = undefined;
          } else {
            next.slot = value;
          }
          return { ...state, ...next };
        }),

      pushRecent: (recent) =>
        set((state) => {
          const deduped = state.recents.filter(
            (item) => !(item.kind === recent.kind && item.id === recent.id),
          );
          const entry: JourneyRecent = { ...recent, at: Date.now() };
          return { recents: [entry, ...deduped].slice(0, MAX_RECENTS) };
        }),

      reset: () =>
        set({
          scenarioId: undefined,
          solutionId: undefined,
          projectId: undefined,
          slot: undefined,
          recents: [],
          lastHref: undefined,
        }),
    }),
    {
      name: 'journeyContext',
      // 只持久化上下文与最近列表；方法不入库。
      partialize: (state) => ({
        scenarioId: state.scenarioId,
        solutionId: state.solutionId,
        projectId: state.projectId,
        slot: state.slot,
        recents: state.recents,
        lastHref: state.lastHref,
      }),
    },
  ),
);

// @AI_GENERATED: end
