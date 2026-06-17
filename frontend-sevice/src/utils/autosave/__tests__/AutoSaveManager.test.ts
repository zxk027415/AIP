import { AutoSaveManager, WorkflowData, DraftData, AutoSaveConfig } from '../AutoSaveManager';

// Mock IndexedDB
class MockIDBDatabase {
  objectStoreNames = { contains: jest.fn(() => true) };
  transaction = jest.fn();
  createObjectStore = jest.fn();
}

class MockIDBTransaction {
  objectStore = jest.fn();
}

class MockIDBObjectStore {
  put = jest.fn();
  get = jest.fn();
  getAll = jest.fn();
  delete = jest.fn();
}

describe('AutoSaveManager', () => {
  let manager: AutoSaveManager;
  let mockWorkflowData: WorkflowData;

  beforeEach(() => {
    jest.useFakeTimers();
    localStorage.clear();

    manager = new AutoSaveManager({
      enabled: true,
      interval: 1000,
      maxDrafts: 5,
      draftExpiry: 7,
    });

    mockWorkflowData = {
      id: 'workflow-1',
      name: 'Test Workflow',
      nodes: [],
      edges: [],
      timestamp: Date.now(),
      version: 1,
    };

    // Mock IndexedDB
    const mockStore = new MockIDBObjectStore();
    const mockTransaction = new MockIDBTransaction();
    const mockDB = new MockIDBDatabase();

    mockTransaction.objectStore.mockReturnValue(mockStore);
    mockDB.transaction.mockReturnValue(mockTransaction);

    const mockRequest: any = {
      result: mockDB,
      onsuccess: null,
      onerror: null,
    };

    global.indexedDB = {
      open: jest.fn(() => {
        setTimeout(() => mockRequest.onsuccess?.(), 0);
        return mockRequest;
      }),
    } as any;
  });

  afterEach(() => {
    jest.useRealTimers();
    manager.stop();
  });

  describe('constructor', () => {
    it('should initialize with default config', () => {
      const defaultManager = new AutoSaveManager();
      const config = defaultManager.getConfig();

      expect(config.enabled).toBe(true);
      expect(config.interval).toBe(30000);
      expect(config.maxDrafts).toBe(10);
      expect(config.draftExpiry).toBe(7);
    });

    it('should initialize with custom config', () => {
      const customManager = new AutoSaveManager({
        enabled: false,
        interval: 5000,
        maxDrafts: 3,
        draftExpiry: 14,
      });

      const config = customManager.getConfig();

      expect(config.enabled).toBe(false);
      expect(config.interval).toBe(5000);
      expect(config.maxDrafts).toBe(3);
      expect(config.draftExpiry).toBe(14);
    });

    it('should load config from localStorage', () => {
      const savedConfig: AutoSaveConfig = {
        enabled: false,
        interval: 15000,
        maxDrafts: 8,
        draftExpiry: 30,
      };

      localStorage.setItem('autosave_config', JSON.stringify(savedConfig));

      const loadedManager = new AutoSaveManager();
      const config = loadedManager.getConfig();

      expect(config.enabled).toBe(false);
      expect(config.interval).toBe(15000);
    });
  });

  describe('start', () => {
    it('should start auto-save timer', () => {
      const getData = jest.fn(() => mockWorkflowData);

      manager.start('workflow-1', getData);

      jest.advanceTimersByTime(1000);

      expect(getData).toHaveBeenCalled();
    });

    it('should not start if disabled', () => {
      const disabledManager = new AutoSaveManager({ enabled: false });
      const getData = jest.fn(() => mockWorkflowData);

      disabledManager.start('workflow-1', getData);

      jest.advanceTimersByTime(1000);

      expect(getData).not.toHaveBeenCalled();
    });

    it('should call save at specified interval', () => {
      const getData = jest.fn(() => ({
        ...mockWorkflowData,
        timestamp: Date.now(),
      }));

      manager.start('workflow-1', getData);

      jest.advanceTimersByTime(1000);
      expect(getData).toHaveBeenCalledTimes(1);

      jest.advanceTimersByTime(1000);
      expect(getData).toHaveBeenCalledTimes(2);

      jest.advanceTimersByTime(1000);
      expect(getData).toHaveBeenCalledTimes(3);
    });

    it('should stop previous timer when starting new one', () => {
      const getData1 = jest.fn(() => mockWorkflowData);
      const getData2 = jest.fn(() => mockWorkflowData);

      manager.start('workflow-1', getData1);
      manager.start('workflow-2', getData2);

      jest.advanceTimersByTime(1000);

      expect(getData1).not.toHaveBeenCalled();
      expect(getData2).toHaveBeenCalled();
    });
  });

  describe('stop', () => {
    it('should stop auto-save timer', () => {
      const getData = jest.fn(() => mockWorkflowData);

      manager.start('workflow-1', getData);
      manager.stop();

      jest.advanceTimersByTime(1000);

      expect(getData).not.toHaveBeenCalled();
    });

    it('should handle stopping when not started', () => {
      expect(() => manager.stop()).not.toThrow();
    });
  });

  describe('save', () => {
    it('should save workflow data', async () => {
      const getData = jest.fn(() => mockWorkflowData);

      const result = await manager.save('workflow-1', getData);

      expect(result).toBe(true);
      expect(getData).toHaveBeenCalled();
    });

    it('should not save if data unchanged', async () => {
      const getData = jest.fn(() => mockWorkflowData);

      await manager.save('workflow-1', getData);
      const result = await manager.save('workflow-1', getData);

      expect(result).toBe(false);
    });

    it('should save if data changed', async () => {
      let counter = 0;
      const getData = jest.fn(() => ({
        ...mockWorkflowData,
        version: ++counter,
      }));

      const result1 = await manager.save('workflow-1', getData);
      const result2 = await manager.save('workflow-1', getData);

      expect(result1).toBe(true);
      expect(result2).toBe(true);
    });

    it('should update save status', async () => {
      const getData = jest.fn(() => mockWorkflowData);
      const listener = jest.fn();

      manager.addListener(listener);

      await manager.save('workflow-1', getData);

      expect(listener).toHaveBeenCalled();
      const status = manager.getStatus();
      expect(status.state).toBe('saved');
    });

    it('should handle save errors', async () => {
      const getData = jest.fn(() => {
        throw new Error('Save failed');
      });

      const result = await manager.save('workflow-1', getData);

      expect(result).toBe(false);
      const status = manager.getStatus();
      expect(status.state).toBe('error');
    });

    it('should update last save time', async () => {
      const getData = jest.fn(() => mockWorkflowData);

      const timeBefore = manager.getLastSaveTime();
      await manager.save('workflow-1', getData);
      const timeAfter = manager.getLastSaveTime();

      expect(timeAfter).toBeGreaterThan(timeBefore);
    });
  });

  describe('getDrafts', () => {
    it('should return empty array when no drafts', async () => {
      const mockStore = new MockIDBObjectStore();
      mockStore.getAll.mockImplementation(function(this: any) {
        const request: any = { result: [] };
        setTimeout(() => request.onsuccess?.(), 0);
        return request;
      });

      const drafts = await manager.getDrafts();

      expect(drafts).toEqual([]);
    });

    it('should return sorted drafts by timestamp', async () => {
      const mockDrafts: DraftData[] = [
        { ...mockWorkflowData, isDraft: true, timestamp: 1000 },
        { ...mockWorkflowData, isDraft: true, timestamp: 3000 },
        { ...mockWorkflowData, isDraft: true, timestamp: 2000 },
      ];

      const mockStore = new MockIDBObjectStore();
      mockStore.getAll.mockImplementation(function(this: any) {
        const request: any = { result: mockDrafts };
        setTimeout(() => request.onsuccess?.(), 0);
        return request;
      });

      const drafts = await manager.getDrafts();

      expect(drafts[0].timestamp).toBe(3000);
      expect(drafts[1].timestamp).toBe(2000);
      expect(drafts[2].timestamp).toBe(1000);
    });

    it('should filter out non-draft items', async () => {
      const mockData = [
        { ...mockWorkflowData, isDraft: true },
        { ...mockWorkflowData, isDraft: false },
        { ...mockWorkflowData },
      ];

      const mockStore = new MockIDBObjectStore();
      mockStore.getAll.mockImplementation(function(this: any) {
        const request: any = { result: mockData };
        setTimeout(() => request.onsuccess?.(), 0);
        return request;
      });

      const drafts = await manager.getDrafts();

      expect(drafts.every(d => d.isDraft)).toBe(true);
    });

    it('should handle database errors', async () => {
      const mockStore = new MockIDBObjectStore();
      mockStore.getAll.mockImplementation(function(this: any) {
        const request: any = { error: new Error('DB error') };
        setTimeout(() => request.onerror?.(), 0);
        return request;
      });

      const drafts = await manager.getDrafts();

      expect(drafts).toEqual([]);
    });
  });

  describe('restoreDraft', () => {
    it('should restore draft by ID', async () => {
      const mockDraft: DraftData = {
        ...mockWorkflowData,
        isDraft: true,
      };

      const mockStore = new MockIDBObjectStore();
      mockStore.get.mockImplementation(function(this: any) {
        const request: any = { result: mockDraft };
        setTimeout(() => request.onsuccess?.(), 0);
        return request;
      });

      const draft = await manager.restoreDraft('workflow-1');

      expect(draft).toEqual(mockDraft);
    });

    it('should return null if draft not found', async () => {
      const mockStore = new MockIDBObjectStore();
      mockStore.get.mockImplementation(function(this: any) {
        const request: any = { result: undefined };
        setTimeout(() => request.onsuccess?.(), 0);
        return request;
      });

      const draft = await manager.restoreDraft('non-existent');

      expect(draft).toBeNull();
    });

    it('should handle restore errors', async () => {
      const mockStore = new MockIDBObjectStore();
      mockStore.get.mockImplementation(function(this: any) {
        const request: any = { error: new Error('Restore failed') };
        setTimeout(() => request.onerror?.(), 0);
        return request;
      });

      const draft = await manager.restoreDraft('workflow-1');

      expect(draft).toBeNull();
    });
  });

  describe('deleteDraft', () => {
    it('should delete draft by ID', async () => {
      const mockStore = new MockIDBObjectStore();
      mockStore.delete.mockImplementation(function(this: any) {
        const request: any = {};
        setTimeout(() => request.onsuccess?.(), 0);
        return request;
      });

      await expect(manager.deleteDraft('workflow-1')).resolves.not.toThrow();
    });

    it('should handle delete errors', async () => {
      const mockStore = new MockIDBObjectStore();
      mockStore.delete.mockImplementation(function(this: any) {
        const request: any = { error: new Error('Delete failed') };
        setTimeout(() => request.onerror?.(), 0);
        return request;
      });

      await expect(manager.deleteDraft('workflow-1')).resolves.not.toThrow();
    });
  });

  describe('updateConfig', () => {
    it('should update configuration', () => {
      manager.updateConfig({ interval: 5000 });

      const config = manager.getConfig();
      expect(config.interval).toBe(5000);
    });

    it('should save config to localStorage', () => {
      manager.updateConfig({ maxDrafts: 15 });

      const stored = localStorage.getItem('autosave_config');
      expect(stored).toBeTruthy();

      const config = JSON.parse(stored!);
      expect(config.maxDrafts).toBe(15);
    });

    it('should merge with existing config', () => {
      const originalConfig = manager.getConfig();

      manager.updateConfig({ interval: 2000 });

      const newConfig = manager.getConfig();
      expect(newConfig.enabled).toBe(originalConfig.enabled);
      expect(newConfig.interval).toBe(2000);
    });
  });

  describe('getConfig', () => {
    it('should return current configuration', () => {
      const config = manager.getConfig();

      expect(config).toHaveProperty('enabled');
      expect(config).toHaveProperty('interval');
      expect(config).toHaveProperty('maxDrafts');
      expect(config).toHaveProperty('draftExpiry');
    });

    it('should return a copy of config', () => {
      const config1 = manager.getConfig();
      config1.interval = 99999;

      const config2 = manager.getConfig();
      expect(config2.interval).not.toBe(99999);
    });
  });

  describe('getStatus', () => {
    it('should return current save status', () => {
      const status = manager.getStatus();

      expect(status).toHaveProperty('state');
      expect(status).toHaveProperty('message');
    });

    it('should return idle status initially', () => {
      const status = manager.getStatus();

      expect(status.state).toBe('idle');
    });
  });

  describe('getLastSaveTime', () => {
    it('should return 0 initially', () => {
      const time = manager.getLastSaveTime();

      expect(time).toBe(0);
    });

    it('should return timestamp after save', async () => {
      const getData = jest.fn(() => mockWorkflowData);

      await manager.save('workflow-1', getData);

      const time = manager.getLastSaveTime();
      expect(time).toBeGreaterThan(0);
    });
  });

  describe('addListener', () => {
    it('should add status listener', async () => {
      const listener = jest.fn();
      manager.addListener(listener);

      const getData = jest.fn(() => mockWorkflowData);
      await manager.save('workflow-1', getData);

      expect(listener).toHaveBeenCalled();
    });

    it('should return unsubscribe function', async () => {
      const listener = jest.fn();
      const unsubscribe = manager.addListener(listener);

      unsubscribe();

      const getData = jest.fn(() => mockWorkflowData);
      await manager.save('workflow-1', getData);

      expect(listener).not.toHaveBeenCalled();
    });

    it('should support multiple listeners', async () => {
      const listener1 = jest.fn();
      const listener2 = jest.fn();

      manager.addListener(listener1);
      manager.addListener(listener2);

      const getData = jest.fn(() => mockWorkflowData);
      await manager.save('workflow-1', getData);

      expect(listener1).toHaveBeenCalled();
      expect(listener2).toHaveBeenCalled();
    });
  });

  describe('edge cases', () => {
    it('should handle corrupted localStorage config', () => {
      localStorage.setItem('autosave_config', 'invalid json');

      expect(() => new AutoSaveManager()).not.toThrow();
    });

    it('should handle very large workflow data', async () => {
      const largeData = {
        ...mockWorkflowData,
        nodes: Array(1000).fill(null).map((_, i) => ({
          id: `node-${i}`,
          type: 'default',
          position: { x: i * 100, y: i * 100 },
          data: { label: `Node ${i}` },
        })),
      };

      const getData = jest.fn(() => largeData);

      await expect(manager.save('workflow-1', getData)).resolves.not.toThrow();
    });

    it('should handle rapid consecutive saves', async () => {
      let counter = 0;
      const getData = jest.fn(() => ({
        ...mockWorkflowData,
        version: ++counter,
      }));

      const promises = [
        manager.save('workflow-1', getData),
        manager.save('workflow-1', getData),
        manager.save('workflow-1', getData),
      ];

      await expect(Promise.all(promises)).resolves.not.toThrow();
    });
  });
});
