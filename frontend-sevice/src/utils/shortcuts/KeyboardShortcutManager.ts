/**
 * 快捷键配置
 */
export interface ShortcutConfig {
  id: string;
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  meta?: boolean;
  description: string;
  category: string;
  handler: () => void;
  enabled?: boolean;
}

/**
 * 快捷键类别
 */
export enum ShortcutCategory {
  EDIT = '编辑',
  VIEW = '视图',
  NAVIGATION = '导航',
  SELECTION = '选择',
  FILE = '文件',
  WORKFLOW = '算法模板',
}

/**
 * 键盘快捷键管理器
 */
export class KeyboardShortcutManager {
  private shortcuts: Map<string, ShortcutConfig> = new Map();
  private listeners: Set<() => void> = new Set();
  private isEnabled: boolean = true;

  constructor() {
    this.initializeEventListener();
  }

  /**
   * 注册快捷键
   */
  register(config: ShortcutConfig): void {
    // 检查冲突
    const existingShortcut = this.findConflict(config);
    if (existingShortcut) {
      console.warn(
        `快捷键冲突: ${this.getShortcutString(config)} 已被 "${existingShortcut.description}" 使用`
      );
    }

    this.shortcuts.set(config.id, { ...config, enabled: config.enabled ?? true });
    this.notifyListeners();
  }

  /**
   * 批量注册快捷键
   */
  registerMultiple(configs: ShortcutConfig[]): void {
    configs.forEach(config => this.register(config));
  }

  /**
   * 注销快捷键
   */
  unregister(id: string): void {
    this.shortcuts.delete(id);
    this.notifyListeners();
  }

  /**
   * 启用/禁用快捷键
   */
  setEnabled(id: string, enabled: boolean): void {
    const shortcut = this.shortcuts.get(id);
    if (shortcut) {
      shortcut.enabled = enabled;
      this.notifyListeners();
    }
  }

  /**
   * 启用/禁用所有快捷键
   */
  setGlobalEnabled(enabled: boolean): void {
    this.isEnabled = enabled;
  }

  /**
   * 更新快捷键
   */
  update(id: string, updates: Partial<ShortcutConfig>): void {
    const shortcut = this.shortcuts.get(id);
    if (shortcut) {
      Object.assign(shortcut, updates);
      this.notifyListeners();
    }
  }

  /**
   * 获取所有快捷键
   */
  getAll(): ShortcutConfig[] {
    return Array.from(this.shortcuts.values());
  }

  /**
   * 按类别获取快捷键
   */
  getByCategory(category: string): ShortcutConfig[] {
    return this.getAll().filter(s => s.category === category);
  }

  /**
   * 获取快捷键字符串表示
   */
  getShortcutString(config: ShortcutConfig): string {
    const parts: string[] = [];
    if (config.ctrl) parts.push('Ctrl');
    if (config.shift) parts.push('Shift');
    if (config.alt) parts.push('Alt');
    if (config.meta) parts.push('Meta');
    parts.push(config.key.toUpperCase());
    return parts.join('+');
  }

  /**
   * 查找冲突的快捷键
   */
  private findConflict(config: ShortcutConfig): ShortcutConfig | null {
    for (const shortcut of this.shortcuts.values()) {
      if (
        shortcut.id !== config.id &&
        shortcut.key.toLowerCase() === config.key.toLowerCase() &&
        !!shortcut.ctrl === !!config.ctrl &&
        !!shortcut.shift === !!config.shift &&
        !!shortcut.alt === !!config.alt &&
        !!shortcut.meta === !!config.meta
      ) {
        return shortcut;
      }
    }
    return null;
  }

  /**
   * 初始化事件监听器
   */
  private initializeEventListener(): void {
    window.addEventListener('keydown', this.handleKeyDown.bind(this));
  }

  /**
   * 处理键盘事件
   */
  private handleKeyDown(event: KeyboardEvent): void {
    if (!this.isEnabled) return;

    // 如果焦点在输入框，不触发快捷键
    const target = event.target as HTMLElement;
    if (
      target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.isContentEditable
    ) {
      return;
    }

    // 查找匹配的快捷键
    for (const shortcut of this.shortcuts.values()) {
      if (!shortcut.enabled) continue;

      const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase();
      const ctrlMatch = !!shortcut.ctrl === (event.ctrlKey || event.metaKey);
      const shiftMatch = !!shortcut.shift === event.shiftKey;
      const altMatch = !!shortcut.alt === event.altKey;

      if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
        event.preventDefault();
        shortcut.handler();
        break;
      }
    }
  }

  /**
   * 添加监听器
   */
  addListener(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * 通知监听器
   */
  private notifyListeners(): void {
    this.listeners.forEach(listener => listener());
  }

  /**
   * 导出配置
   */
  exportConfig(): Record<string, any> {
    const config: Record<string, any> = {};
    this.shortcuts.forEach((shortcut, id) => {
      config[id] = {
        key: shortcut.key,
        ctrl: shortcut.ctrl,
        shift: shortcut.shift,
        alt: shortcut.alt,
        meta: shortcut.meta,
        enabled: shortcut.enabled,
      };
    });
    return config;
  }

  /**
   * 导入配置
   */
  importConfig(config: Record<string, any>): void {
    Object.entries(config).forEach(([id, settings]) => {
      const shortcut = this.shortcuts.get(id);
      if (shortcut) {
        Object.assign(shortcut, settings);
      }
    });
    this.notifyListeners();
  }

  /**
   * 重置为默认配置
   */
  reset(): void {
    this.shortcuts.forEach(shortcut => {
      shortcut.enabled = true;
    });
    this.notifyListeners();
  }
}

// 全局快捷键管理器实例
export const shortcutManager = new KeyboardShortcutManager();
