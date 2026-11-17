// @AI_GENERATED: Kiro v1.0
/**
 * Algorithm Agent 状态管理
 * 使用 Zustand 管理对话状态
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type {
  AgentMessage,
  AgentPhase,
  AgentType,
  SessionContext,
  SuggestedAction,
} from '../types/algorithm-agent';

interface SessionHistoryItem {
  id: string;
  title: string;
  updatedAt: string;
  agentType?: AgentType;
  messages: AgentMessage[];  // 保存消息内容
  context: SessionContext;   // 保存上下文
}

interface AlgorithmAgentState {
  // 会话状态
  sessionId: string | null;
  messages: AgentMessage[];
  context: SessionContext;
  phase: AgentPhase;
  agentType: AgentType;  // 当前 Agent 类型
  
  // UI 状态
  isLoading: boolean;
  inputValue: string;
  showHistory: boolean;
  selectedSkill: string | null;
  suggestedActions: SuggestedAction[];
  
  // 历史会话
  sessionHistory: SessionHistoryItem[];
  
  // Actions
  setSessionId: (id: string | null) => void;
  addMessage: (message: AgentMessage) => void;
  setMessages: (messages: AgentMessage[]) => void;
  updateContext: (update: Partial<SessionContext>) => void;
  setPhase: (phase: AgentPhase) => void;
  setAgentType: (agentType: AgentType) => void;
  setLoading: (loading: boolean) => void;
  setInputValue: (value: string) => void;
  setShowHistory: (show: boolean) => void;
  setSelectedSkill: (skill: string | null) => void;
  setSuggestedActions: (actions: SuggestedAction[]) => void;
  
  // 会话管理
  startNewSession: () => void;
  loadSession: (sessionId: string, messages: AgentMessage[], context: SessionContext) => void;
  loadSessionFromHistory: (sessionId: string) => boolean;  // 从本地历史加载
  saveToHistory: () => void;
  clearHistory: () => void;
  
  // 重置
  reset: () => void;
}

const initialState = {
  sessionId: null,
  messages: [],
  context: {},
  phase: 'research' as AgentPhase,
  agentType: 'curator' as AgentType,
  isLoading: false,
  inputValue: '',
  showHistory: false,
  selectedSkill: null,
  suggestedActions: [],
  sessionHistory: [],
};

export const useAlgorithmAgentStore = create<AlgorithmAgentState>()(
  persist(
    (set, get) => ({
      ...initialState,

      setSessionId: (id) => set({ sessionId: id }),
      
      addMessage: (message) => set((state) => ({
        messages: [...state.messages, message],
      })),
      
      setMessages: (messages) => set({ messages }),
      
      updateContext: (update) => set((state) => ({
        context: { ...state.context, ...update },
      })),
      
      setPhase: (phase) => set({ phase }),
      
      setAgentType: (agentType) => set({ agentType }),
      
      setLoading: (loading) => set({ isLoading: loading }),
      
      setInputValue: (value) => set({ inputValue: value }),
      
      setShowHistory: (show) => set({ showHistory: show }),
      
      setSelectedSkill: (skill) => set({ selectedSkill: skill }),
      
      setSuggestedActions: (actions) => set({ suggestedActions: actions }),

      startNewSession: () => {
        const state = get();
        // 保存当前会话到历史
        if (state.messages.length > 0) {
          state.saveToHistory();
        }
        // 重置为新会话
        set({
          sessionId: null,
          messages: [],
          context: {},
          phase: 'research',
          inputValue: '',
          selectedSkill: null,
          suggestedActions: [],
        });
      },

      loadSession: (sessionId, messages, context) => {
        set({
          sessionId,
          messages,
          context,
          inputValue: '',
          selectedSkill: null,
          suggestedActions: [],
        });
      },

      // 从本地历史加载会话
      loadSessionFromHistory: (sessionId) => {
        const state = get();
        const historyItem = state.sessionHistory.find(h => h.id === sessionId);
        if (historyItem && historyItem.messages && historyItem.messages.length > 0) {
          set({
            sessionId: historyItem.id,
            messages: historyItem.messages,
            context: historyItem.context || {},
            agentType: historyItem.agentType || 'curator',
            inputValue: '',
            selectedSkill: null,
            suggestedActions: [],
          });
          return true;
        }
        return false;
      },

      saveToHistory: () => {
        const state = get();
        // 只保存有用户消息的会话
        const userMessages = state.messages.filter(m => m.role === 'user');
        if (userMessages.length === 0) return;
        
        // 生成会话 ID（如果没有）
        const sessionId = state.sessionId || `local-${Date.now()}`;
        
        const firstUserMsg = userMessages[0];
        const title = firstUserMsg?.content.slice(0, 50) || '新会话';
        
        const newEntry: SessionHistoryItem = {
          id: sessionId,
          title,
          updatedAt: new Date().toISOString(),
          agentType: state.agentType,
          messages: state.messages,
          context: state.context,
        };
        
        set((s) => ({
          sessionId,  // 更新 sessionId
          sessionHistory: [
            newEntry,
            ...s.sessionHistory.filter(h => h.id !== sessionId),
          ].slice(0, 20), // 保留最近 20 条
        }));
      },

      clearHistory: () => set({ sessionHistory: [] }),

      reset: () => set(initialState),
    }),
    {
      name: 'algorithm-agent-storage',
      partialize: (state) => ({
        sessionHistory: state.sessionHistory,
        agentType: state.agentType,
        // 离开页面再返回时需恢复当前对话（此前未持久化导致消息丢失）
        sessionId: state.sessionId,
        messages: state.messages,
        context: state.context,
        phase: state.phase,
        selectedSkill: state.selectedSkill,
        suggestedActions: state.suggestedActions,
      }),
      // 数据迁移：清理旧格式的历史记录
      onRehydrateStorage: () => (state) => {
        if (!state) {
          return;
        }
        if (!Array.isArray(state.messages)) {
          state.messages = [];
        }
        if (state.context == null) {
          state.context = {};
        }
        if (state?.sessionHistory) {
          // 过滤掉没有 messages 的旧格式记录
          const validHistory = state.sessionHistory.filter(
            (h: SessionHistoryItem) => h.messages && h.messages.length > 0
          );
          if (validHistory.length !== state.sessionHistory.length) {
            state.sessionHistory = validHistory;
          }
        }
      },
    }
  )
);
// @AI_GENERATED: end
