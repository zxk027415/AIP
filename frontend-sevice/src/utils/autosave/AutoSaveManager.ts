import { Node, Edge } from 'reactflow';

/**
 * 算法模板数据
 */
export interface WorkflowData {
  id: string;
  name: string;
  nodes: Node[];
  edges: Edge[];
  timestamp: number;
  version: number;
}

/**
 * 草稿数据
 */
export interface DraftData extends WorkflowData {
  isDraft: true;
  originalId?: string;
}

/**
 * 自动保存配置
 */
export interface AutoSaveConfig {
  enabled: boolean;
  interval: number; // 毫秒
  maxDrafts: number;
  draftExpiry: number; // 天数
}

/**
 * 默认配置
 */
const DEFAULT_CONFIG: AutoSaveConfig = {
  enabled: true,
  interval: 30000, // 30秒
  maxDrafts: 10,
  draftExpiry: 7, // 7天
};

/**
 * 自动保存管理器
 */
export class AutoSaveManager {
  private config: AutoSaveConfig;
  private timerId: number | null = null;
  private lastSaveTime: number = 0;
  private lastData: string = '';
  private listeners: Set<(status: SaveStatus) => void> = new Set();
  private saveStatus: SaveStatus = { state: 'idle', message: '' };

  constructor(config: Partial<AutoSaveConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
    this.loadConfig();
  }

  /**
   * 启动自动保存
   */
  start(workflowId: string, getData: () => WorkflowData): void {
    if (!this.config.enabled) return;

    this.stop();

    this.timerId = window.setInterval(() => {
      this.save(workflowId, getData);
    }, this.config.interval);
  }

  /**
   * 停止自动保存
   */
  stop(): void {
    if (this.timerId !== null) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
  }

  /**
   * 手动保存
   */
  async save(workflowId: string, getData: () => WorkflowData): Promise<boolean> {
    try {
      const data = getData();
      const dataStr = JSON.stringify(data);

      // 检查是否有变更
      if (dataStr === this.lastData) {
        return false;
      }

      this.updateStatus({ state: 'saving', message: '正在保存...' });

      // 保存到IndexedDB
      await this.saveToIndexedDB(workflowId, data);

      this.lastData = dataStr;
      this.lastSaveTime = Date.now();

      this.updateStatus({
        state: 'saved',
        message: '已保存',
        timestamp: this.lastSaveTime,
      });

      return true;
    } catch (error) {
      console.error('自动保存失败:', error);
      this.updateStatus({
        state: 'error',
        message: '保存失败',
        error: error as Error,
      });
      return false;
    }
  }

  /**
   * 保存到IndexedDB
   */
  private async saveToIndexedDB(workflowId: string, data: WorkflowData): Promise<void> {
    const db = await this.openDatabase();
    const transaction = db.transaction(['workflows'], 'readwrite');
    const store = transaction.objectStore('workflows');

    const draftData: DraftData = {
      ...data,
      isDraft: true,
      originalId: workflowId,
      timestamp: Date.now(),
    };

    await new Promise<void>((resolve, reject) => {
      const request = store.put(draftData);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });

    // 清理过期草稿
    await this.cleanupExpiredDrafts(db);
  }

  /**
   * 打开数据库
   */
  private async openDatabase(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open('WorkflowAutosave', 1);

      request.onerror = () => reject(request.error);
      request.onsuccess = () => resolve(request.result);

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;
        if (!db.objectStoreNames.contains('workflows')) {
          db.createObjectStore('workflows', { keyPath: 'id' });
        }
      };
    });
  }

  /**
   * 获取草稿列表
   */
  async getDrafts(): Promise<DraftData[]> {
    try {
      const db = await this.openDatabase();
      const transaction = db.transaction(['workflows'], 'readonly');
      const store = transaction.objectStore('workflows');

      return new Promise((resolve, reject) => {
        const request = store.getAll();
        request.onsuccess = () => {
          const drafts = request.result.filter((d: any) => d.isDraft);
          resolve(drafts.sort((a, b) => b.timestamp - a.timestamp));
        };
        request.onerror = () => reject(request.error);
      });
    } catch (error) {
      console.error('获取草稿列表失败:', error);
      return [];
    }
  }

  /**
   * 恢复草稿
   */
  async restoreDraft(draftId: string): Promise<DraftData | null> {
    try {
      const db = await this.openDatabase();
      const transaction = db.transaction(['workflows'], 'readonly');
      const store = transaction.objectStore('workflows');

      return new Promise((resolve, reject) => {
        const request = store.get(draftId);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => reject(request.error);
      });
    } catch (error) {
      console.error('恢复草稿失败:', error);
      return null;
    }
  }

  /**
   * 删除草稿
   */
  async deleteDraft(draftId: string): Promise<void> {
    try {
      const db = await this.openDatabase();
      const transaction = db.transaction(['workflows'], 'readwrite');
      const store = transaction.objectStore('workflows');

      await new Promise<void>((resolve, reject) => {
        const request = store.delete(draftId);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
      });
    } catch (error) {
      console.error('删除草稿失败:', error);
    }
  }

  /**
   * 清理过期草稿
   */
  private async cleanupExpiredDrafts(db: IDBDatabase): Promise<void> {
    const transaction = db.transaction(['workflows'], 'readwrite');
    const store = transaction.objectStore('workflows');

    const expiryTime = Date.now() - this.config.draftExpiry * 24 * 60 * 60 * 1000;

    const request = store.getAll();
    request.onsuccess = () => {
      const drafts = request.result.filter((d: any) => d.isDraft);

      // 删除过期草稿
      drafts.forEach((draft: DraftData) => {
        if (draft.timestamp < expiryTime) {
          store.delete(draft.id);
        }
      });

      // 限制草稿数量
      if (drafts.length > this.config.maxDrafts) {
        const sorted = drafts.sort((a, b) => b.timestamp - a.timestamp);
        const toDelete = sorted.slice(this.config.maxDrafts);
        toDelete.forEach((draft: DraftData) => {
          store.delete(draft.id);
        });
      }
    };
  }

  /**
   * 更新配置
   */
  updateConfig(config: Partial<AutoSaveConfig>): void {
    this.config = { ...this.config, ...config };
    this.saveConfig();
  }

  /**
   * 获取配置
   */
  getConfig(): AutoSaveConfig {
    return { ...this.config };
  }

  /**
   * 保存配置到localStorage
   */
  private saveConfig(): void {
    localStorage.setItem('autosave_config', JSON.stringify(this.config));
  }

  /**
   * 从localStorage加载配置
   */
  private loadConfig(): void {
    try {
      const stored = localStorage.getItem('autosave_config');
      if (stored) {
        this.config = { ...this.config, ...JSON.parse(stored) };
      }
    } catch (error) {
      console.error('加载自动保存配置失败:', error);
    }
  }

  /**
   * 获取保存状态
   */
  getStatus(): SaveStatus {
    return { ...this.saveStatus };
  }

  /**
   * 获取最后保存时间
   */
  getLastSaveTime(): number {
    return this.lastSaveTime;
  }

  /**
   * 添加状态监听器
   */
  addListener(listener: (status: SaveStatus) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /**
   * 更新状态
   */
  private updateStatus(status: SaveStatus): void {
    this.saveStatus = status;
    this.listeners.forEach(listener => listener(status));
  }
}

/**
 * 保存状态
 */
export interface SaveStatus {
  state: 'idle' | 'saving' | 'saved' | 'error';
  message: string;
  timestamp?: number;
  error?: Error;
}

// 全局自动保存管理器实例
export const autoSaveManager = new AutoSaveManager();
