/**
 * 命令接口 - 撤销/重做系统的核心
 */
export interface Command {
  /**
   * 执行命令
   */
  execute(): void;

  /**
   * 撤销命令
   */
  undo(): void;

  /**
   * 重做命令（默认调用execute）
   */
  redo(): void;

  /**
   * 命令描述（用于历史记录显示）
   */
  getDescription(): string;

  /**
   * 是否可以与下一个命令合并（用于连续移动等操作）
   */
  canMergeWith(command: Command): boolean;

  /**
   * 合并命令
   */
  mergeWith(command: Command): void;
}

/**
 * 抽象命令基类
 */
export abstract class BaseCommand implements Command {
  abstract execute(): void;
  abstract undo(): void;
  abstract getDescription(): string;

  redo(): void {
    this.execute();
  }

  canMergeWith(_command: Command): boolean {
    return false;
  }

  mergeWith(_command: Command): void {
    throw new Error('Cannot merge commands');
  }
}
