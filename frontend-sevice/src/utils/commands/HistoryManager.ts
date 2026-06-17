import { Command } from './Command';

/**
 * 历史管理器 - 管理命令历史栈
 */
export class HistoryManager {
  private undoStack: Command[] = [];
  private redoStack: Command[] = [];
  private maxStackSize: number;
  private listeners: Set<() => void> = new Set();

  constructor(maxStackSize: number = 50) {
    this.maxStackSize = maxStackSize;
  }

  /**
   * 执行命令并添加到历史栈
   */
  execute(command: Command): void {
    // 尝试与上一个命令合并
    const lastCommand = this.undoStack[this.undoStack.length - 1];
    if (lastCommand && lastCommand.canMergeWith(command)) {
      lastCommand.mergeWith(command);
      command.execute();
      this.notifyListeners();
      return;
    }

    // 执行命令
    command.execute();

    // 添加到撤销栈
    this.undoStack.push(command);

    // 清空重做栈
    this.redoStack = [];

    // 限制栈大小
    if (this.undoStack.length > this.maxStackSize) {
      this.undoStack.shift();
    }

    this.notifyListeners();
  }

  /**
   * 撤销上一个命令
   */
  undo(): boolean {
    if (!this.canUndo()) {
      return false;
    }

    const command = this.undoStack.pop()!;
    command.undo();
    this.redoStack.push(command);

    this.notifyListeners();
    return true;
  }

  /**
   * 重做上一个撤销的命令
   */
  redo(): boolean {
    if (!this.canRedo()) {
      return false;
    }

    const command = this.redoStack.pop()!;
    command.redo();
    this.undoStack.push(command);

    this.notifyListeners();
    return true;
  }

  /**
   * 是否可以撤销
   */
  canUndo(): boolean {
    return this.undoStack.length > 0;
  }

  /**
   * 是否可以重做
   */
  canRedo(): boolean {
    return this.redoStack.length > 0;
  }

  /**
   * 获取撤销栈
   */
  getUndoStack(): Command[] {
    return [...this.undoStack];
  }

  /**
   * 获取重做栈
   */
  getRedoStack(): Command[] {
    return [...this.redoStack];
  }

  /**
   * 获取当前位置（撤销栈的长度）
   */
  getCurrentPosition(): number {
    return this.undoStack.length;
  }

  /**
   * 清空历史
   */
  clear(): void {
    this.undoStack = [];
    this.redoStack = [];
    this.notifyListeners();
  }

  /**
   * 添加监听器
   */
  addListener(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * 通知所有监听器
   */
  private notifyListeners(): void {
    this.listeners.forEach(listener => listener());
  }
}

// 全局历史管理器实例
export const historyManager = new HistoryManager();
