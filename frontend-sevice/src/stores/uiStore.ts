import { create } from 'zustand';
import type { Workflow } from '../types/workflow';

interface HistoryState {
  workflow: Workflow;
  timestamp: number;
}

interface UIStore {
  // Panel states
  isPropertyPanelCollapsed: boolean;
  isValidationPanelCollapsed: boolean;
  isExecutionPanelCollapsed: boolean;
  isFunctionLibraryCollapsed: boolean;

  // Selection
  selectedNodeId: string | null;
  selectedEdgeId: string | null;

  // History (undo/redo)
  history: HistoryState[];
  historyIndex: number;
  maxHistorySize: number;

  // Panel actions
  togglePropertyPanel: () => void;
  toggleValidationPanel: () => void;
  toggleExecutionPanel: () => void;
  toggleFunctionLibrary: () => void;

  // Selection actions
  selectNode: (nodeId: string | null) => void;
  selectEdge: (edgeId: string | null) => void;
  clearSelection: () => void;

  // History actions
  pushHistory: (workflow: Workflow) => void;
  undo: () => Workflow | null;
  redo: () => Workflow | null;
  canUndo: () => boolean;
  canRedo: () => boolean;
  clearHistory: () => void;
}

export const useUIStore = create<UIStore>((set, get) => ({
  // Initial panel states
  isPropertyPanelCollapsed: false,
  isValidationPanelCollapsed: false,
  isExecutionPanelCollapsed: true,
  isFunctionLibraryCollapsed: false,

  // Initial selection
  selectedNodeId: null,
  selectedEdgeId: null,

  // Initial history
  history: [],
  historyIndex: -1,
  maxHistorySize: 50,

  // Panel toggle actions
  togglePropertyPanel: () => {
    set((state) => ({
      isPropertyPanelCollapsed: !state.isPropertyPanelCollapsed,
    }));
  },

  toggleValidationPanel: () => {
    set((state) => ({
      isValidationPanelCollapsed: !state.isValidationPanelCollapsed,
    }));
  },

  toggleExecutionPanel: () => {
    set((state) => ({
      isExecutionPanelCollapsed: !state.isExecutionPanelCollapsed,
    }));
  },

  toggleFunctionLibrary: () => {
    set((state) => ({
      isFunctionLibraryCollapsed: !state.isFunctionLibraryCollapsed,
    }));
  },

  // Selection actions
  selectNode: (nodeId) => {
    set({
      selectedNodeId: nodeId,
      selectedEdgeId: null,
    });
  },

  selectEdge: (edgeId) => {
    set({
      selectedNodeId: null,
      selectedEdgeId: edgeId,
    });
  },

  clearSelection: () => {
    set({
      selectedNodeId: null,
      selectedEdgeId: null,
    });
  },

  // History actions
  pushHistory: (workflow) => {
    const { history, historyIndex, maxHistorySize } = get();

    // Remove any history after current index (when pushing new state after undo)
    const newHistory = history.slice(0, historyIndex + 1);

    // Add new state
    newHistory.push({
      workflow: JSON.parse(JSON.stringify(workflow)), // Deep clone
      timestamp: Date.now(),
    });

    // Limit history size
    if (newHistory.length > maxHistorySize) {
      newHistory.shift();
    }

    set({
      history: newHistory,
      historyIndex: newHistory.length - 1,
    });
  },

  undo: () => {
    const { history, historyIndex } = get();

    if (historyIndex > 0) {
      const newIndex = historyIndex - 1;
      set({ historyIndex: newIndex });
      return history[newIndex].workflow;
    }

    return null;
  },

  redo: () => {
    const { history, historyIndex } = get();

    if (historyIndex < history.length - 1) {
      const newIndex = historyIndex + 1;
      set({ historyIndex: newIndex });
      return history[newIndex].workflow;
    }

    return null;
  },

  canUndo: () => {
    const { historyIndex } = get();
    return historyIndex > 0;
  },

  canRedo: () => {
    const { history, historyIndex } = get();
    return historyIndex < history.length - 1;
  },

  clearHistory: () => {
    set({
      history: [],
      historyIndex: -1,
    });
  },
}));
