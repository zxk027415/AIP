/**
 * UI状态相关类型定义
 */

/**
 * 面板折叠状态
 */
export interface PanelState {
  functionLibrary: boolean;
  properties: boolean;
  validation: boolean;
  execution: boolean;
  miniMap: boolean;
}

/**
 * 选中状态
 */
export interface SelectionState {
  selectedNodes: string[];
  selectedEdges: string[];
}

/**
 * 撤销/重做历史项
 */
export interface HistoryItem {
  timestamp: number;
  action: string;
  data: any;
}

/**
 * 撤销/重做状态
 */
export interface UndoRedoState {
  past: HistoryItem[];
  present: HistoryItem | null;
  future: HistoryItem[];
  canUndo: boolean;
  canRedo: boolean;
}

/**
 * 通知类型
 */
export type NotificationType = 'success' | 'error' | 'warning' | 'info';

/**
 * 通知消息
 */
export interface Notification {
  id: string;
  type: NotificationType;
  message: string;
  description?: string;
  duration?: number;
}

/**
 * 对话框状态
 */
export interface DialogState {
  saveWorkflow: boolean;
  loadWorkflow: boolean;
  exportWorkflow: boolean;
  settings: boolean;
}

/**
 * 工具栏按钮状态
 */
export interface ToolbarState {
  canSave: boolean;
  canUndo: boolean;
  canRedo: boolean;
  canExecute: boolean;
  isExecuting: boolean;
}
