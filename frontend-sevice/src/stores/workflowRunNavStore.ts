import { create } from 'zustand';

/**
 * 当算法模板在训练/回测时，用户可切到其他页面；通过 MainLayout 上的入口快速跳回编辑器。
 */
interface WorkflowRunNavStore {
  /** 含 query 的完整路径，如 /workflow/editor 或 /workflow/editor?id=xxx */
  returnHref: string | null;
  workflowLabel: string | null;
  /** 流水线异步执行所属的模板 ID，用于回到编辑器后判断是否恢复轮询 */
  editorWorkflowId: string | null;
  phase: 'idle' | 'pipeline' | 'backtest';
  /** 快速回测请求进行中（离开页面时仍显示闪电入口） */
  backtestInFlight: boolean;
  /** 当前快速回测开始时间戳（ms），用于闪电按钮上显示已进行秒数 */
  backtestStartedAt: number | null;
  /** 从闪电按钮跳回编辑器时，下一次进入编辑器自动展开底部控制台 */
  expandBottomPanelOnNextEditorVisit: boolean;
  setActiveRun: (
    returnHref: string,
    workflowLabel: string,
    phase: 'pipeline' | 'backtest',
    editorWorkflowId?: string | null,
  ) => void;
  setBacktestInFlight: (inFlight: boolean) => void;
  /** 从全局「返回训练」入口跳转前调用 */
  requestExpandEditorBottomPanel: () => void;
  clearActiveRun: () => void;
}

export const useWorkflowRunNavStore = create<WorkflowRunNavStore>((set) => ({
  returnHref: null,
  workflowLabel: null,
  editorWorkflowId: null,
  phase: 'idle',
  backtestInFlight: false,
  backtestStartedAt: null,
  expandBottomPanelOnNextEditorVisit: false,
  setActiveRun: (returnHref, workflowLabel, phase, editorWorkflowId = null) =>
    set({
      returnHref,
      workflowLabel,
      phase,
      editorWorkflowId,
      ...(phase === 'pipeline' ? { backtestInFlight: false, backtestStartedAt: null } : {}),
    }),
  setBacktestInFlight: (inFlight) =>
    set({
      backtestInFlight: inFlight,
      backtestStartedAt: inFlight ? Date.now() : null,
    }),
  requestExpandEditorBottomPanel: () => set({ expandBottomPanelOnNextEditorVisit: true }),
  clearActiveRun: () =>
    set({
      returnHref: null,
      workflowLabel: null,
      editorWorkflowId: null,
      phase: 'idle',
      backtestInFlight: false,
      backtestStartedAt: null,
      expandBottomPanelOnNextEditorVisit: false,
    }),
}));
