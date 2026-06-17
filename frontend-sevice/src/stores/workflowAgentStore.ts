// @AI_GENERATED: Kiro v1.0
/**
 * Workflow Agent Store — 智能编排状态持久化
 * 使用 zustand 保持页面切换时状态不丢失
 */
import { create } from 'zustand';
import type {
  ScenarioMatchResult,
  AlgorithmCombination,
  WorkflowGenerateResponse,
  WorkflowValidateResponse,
} from '../types/workflow-agent';
import type { IndustryTemplate } from '../services/industryApi';
import type { EnhancedWorkflowNode, EnhancedWorkflowEdge } from '../types/workflow-enhanced';

type AgentStep =
  | 'input' | 'matching' | 'select-template'
  | 'composing' | 'generating' | 'validating' | 'done';

/** 单次编排会话的快照 */
export interface AgentSession {
  id: string;
  description: string;
  step: AgentStep;
  selectedScenario: ScenarioMatchResult | null;
  selectedTemplate: (IndustryTemplate & { relevanceScore: number }) | null;
  selectedCombo: AlgorithmCombination | null;
  generatedWorkflow: WorkflowGenerateResponse | null;
  validationResult: WorkflowValidateResponse | null;
  previewNodes: EnhancedWorkflowNode[];
  previewEdges: EnhancedWorkflowEdge[];
  createdAt: string;
}

interface WorkflowAgentStore {
  // 当前会话状态
  description: string;
  step: AgentStep;
  activeKeys: string[];
  matches: ScenarioMatchResult[];
  selectedScenario: ScenarioMatchResult | null;
  rankedTemplates: (IndustryTemplate & { relevanceScore: number })[];
  selectedTemplate: (IndustryTemplate & { relevanceScore: number }) | null;
  combinations: AlgorithmCombination[];
  selectedCombo: AlgorithmCombination | null;
  generatedWorkflow: WorkflowGenerateResponse | null;
  validationResult: WorkflowValidateResponse | null;
  previewNodes: EnhancedWorkflowNode[];
  previewEdges: EnhancedWorkflowEdge[];
  errorInfo: { step: AgentStep; message: string; severity?: 'error' | 'info' } | null;

  // 历史会话
  history: AgentSession[];

  // Actions
  setDescription: (v: string) => void;
  setStep: (v: AgentStep) => void;
  setActiveKeys: (v: string[]) => void;
  setMatches: (v: ScenarioMatchResult[]) => void;
  setSelectedScenario: (v: ScenarioMatchResult | null) => void;
  setRankedTemplates: (v: (IndustryTemplate & { relevanceScore: number })[]) => void;
  setSelectedTemplate: (v: (IndustryTemplate & { relevanceScore: number }) | null) => void;
  setCombinations: (v: AlgorithmCombination[]) => void;
  setSelectedCombo: (v: AlgorithmCombination | null) => void;
  setGeneratedWorkflow: (v: WorkflowGenerateResponse | null) => void;
  setValidationResult: (v: WorkflowValidateResponse | null) => void;
  setPreviewNodes: (v: EnhancedWorkflowNode[]) => void;
  setPreviewEdges: (v: EnhancedWorkflowEdge[]) => void;
  setErrorInfo: (v: { step: AgentStep; message: string; severity?: 'error' | 'info' } | null) => void;

  /** 保存当前会话到历史 */
  saveToHistory: () => void;
  /** 从历史恢复会话 */
  restoreFromHistory: (id: string) => void;
  /** 删除历史记录 */
  deleteHistory: (id: string) => void;
  /** 重置当前会话 */
  resetSession: () => void;
}
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
const INITIAL_STATE = {
  description: '',
  step: 'input' as AgentStep,
  activeKeys: ['step-input'],
  matches: [] as ScenarioMatchResult[],
  selectedScenario: null,
  rankedTemplates: [] as (IndustryTemplate & { relevanceScore: number })[],
  selectedTemplate: null,
  combinations: [] as AlgorithmCombination[],
  selectedCombo: null,
  generatedWorkflow: null,
  validationResult: null,
  previewNodes: [] as EnhancedWorkflowNode[],
  previewEdges: [] as EnhancedWorkflowEdge[],
  errorInfo: null,
};

export const useWorkflowAgentStore = create<WorkflowAgentStore>((set, get) => ({
  ...INITIAL_STATE,
  history: [],

  setDescription: (v) => set({ description: v }),
  setStep: (v) => set({ step: v }),
  setActiveKeys: (v) => set({ activeKeys: v }),
  setMatches: (v) => set({ matches: v }),
  setSelectedScenario: (v) => set({ selectedScenario: v }),
  setRankedTemplates: (v) => set({ rankedTemplates: v }),
  setSelectedTemplate: (v) => set({ selectedTemplate: v }),
  setCombinations: (v) => set({ combinations: v }),
  setSelectedCombo: (v) => set({ selectedCombo: v }),
  setGeneratedWorkflow: (v) => set({ generatedWorkflow: v }),
  setValidationResult: (v) => set({ validationResult: v }),
  setPreviewNodes: (v) => set({ previewNodes: v }),
  setPreviewEdges: (v) => set({ previewEdges: v }),
  setErrorInfo: (v) => set({ errorInfo: v }),

  saveToHistory: () => {
    const s = get();
    if (s.step === 'input' && !s.generatedWorkflow) return; // 没有实质内容不保存
    const session: AgentSession = {
      id: `session-${Date.now()}`,
      description: s.description,
      step: s.step,
      selectedScenario: s.selectedScenario,
      selectedTemplate: s.selectedTemplate,
      selectedCombo: s.selectedCombo,
      generatedWorkflow: s.generatedWorkflow,
      validationResult: s.validationResult,
      previewNodes: s.previewNodes,
      previewEdges: s.previewEdges,
      createdAt: new Date().toISOString(),
    };
    // 去重：如果已有相同描述+场景的记录，替换
    const filtered = s.history.filter(
      (h) => !(h.description === session.description && h.selectedScenario?.scenario_id === session.selectedScenario?.scenario_id),
    );
    set({ history: [session, ...filtered].slice(0, 20) }); // 最多保留20条
  },

  restoreFromHistory: (id) => {
    const session = get().history.find((h) => h.id === id);
    if (!session) return;
    // 重建 activeKeys
    const keys = ['step-input'];
    if (session.selectedScenario) keys.push('step-match');
    if (session.selectedTemplate) keys.push('step-template');
    if (session.selectedCombo) keys.push('step-combo');
    if (session.generatedWorkflow) keys.push('step-generate');
    set({
      description: session.description,
      step: session.step,
      activeKeys: keys,
      matches: session.selectedScenario ? [session.selectedScenario] : [],
      selectedScenario: session.selectedScenario,
      rankedTemplates: session.selectedTemplate ? [session.selectedTemplate] : [],
      selectedTemplate: session.selectedTemplate,
      combinations: session.selectedCombo ? [session.selectedCombo] : [],
      selectedCombo: session.selectedCombo,
      generatedWorkflow: session.generatedWorkflow,
      validationResult: session.validationResult,
      previewNodes: session.previewNodes,
      previewEdges: session.previewEdges,
      errorInfo: null,
    });
  },

  deleteHistory: (id) => {
    set({ history: get().history.filter((h) => h.id !== id) });
  },

  resetSession: () => {
    set({ ...INITIAL_STATE });
  },
}));
// @AI_GENERATED: end
