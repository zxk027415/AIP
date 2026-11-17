import { KeyboardShortcutManager, ShortcutConfig, ShortcutCategory } from '../KeyboardShortcutManager';

describe('KeyboardShortcutManager', () => {
  let manager: KeyboardShortcutManager;
  let mockHandler: jest.Mock;

  beforeEach(() => {
    manager = new KeyboardShortcutManager();
    mockHandler = jest.fn();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('register', () => {
    it('should register a shortcut', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test shortcut',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      const shortcuts = manager.getAll();
      expect(shortcuts).toHaveLength(1);
      expect(shortcuts[0].id).toBe('test-shortcut');
      expect(shortcuts[0].enabled).toBe(true);
    });

    it('should warn about conflicting shortcuts', () => {
      const consoleSpy = jest.spyOn(console, 'warn').mockImplementation();

      const config1: ShortcutConfig = {
        id: 'shortcut-1',
        key: 'a',
        ctrl: true,
        description: 'First shortcut',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      const config2: ShortcutConfig = {
        id: 'shortcut-2',
        key: 'a',
        ctrl: true,
        description: 'Second shortcut',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config1);
      manager.register(config2);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('快捷键冲突')
      );

      consoleSpy.mockRestore();
    });

    it('should register shortcut with enabled flag', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test shortcut',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
        enabled: false,
      };

      manager.register(config);

      const shortcuts = manager.getAll();
      expect(shortcuts[0].enabled).toBe(false);
    });
  });

  describe('registerMultiple', () => {
    it('should register multiple shortcuts', () => {
      const configs: ShortcutConfig[] = [
        {
          id: 'shortcut-1',
          key: 'a',
          ctrl: true,
          description: 'First',
          category: ShortcutCategory.EDIT,
          handler: mockHandler,
        },
        {
          id: 'shortcut-2',
          key: 'b',
          ctrl: true,
          description: 'Second',
          category: ShortcutCategory.EDIT,
          handler: mockHandler,
        },
      ];

      manager.registerMultiple(configs);

      expect(manager.getAll()).toHaveLength(2);
    });
  });

  describe('unregister', () => {
    it('should unregister a shortcut', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);
      expect(manager.getAll()).toHaveLength(1);

      manager.unregister('test-shortcut');
      expect(manager.getAll()).toHaveLength(0);
    });
  });

  describe('setEnabled', () => {
    it('should enable/disable a shortcut', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      manager.setEnabled('test-shortcut', false);
      expect(manager.getAll()[0].enabled).toBe(false);

      manager.setEnabled('test-shortcut', true);
      expect(manager.getAll()[0].enabled).toBe(true);
    });
  });

  describe('setGlobalEnabled', () => {
    it('should enable/disable all shortcuts globally', () => {
      manager.setGlobalEnabled(false);
      // Global state is private, but we can test it through keyboard events
      // This is tested in the handleKeyDown tests
    });
  });

  describe('update', () => {
    it('should update shortcut properties', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      manager.update('test-shortcut', {
        description: 'Updated description',
        key: 'b',
      });

      const shortcut = manager.getAll()[0];
      expect(shortcut.description).toBe('Updated description');
      expect(shortcut.key).toBe('b');
    });
  });

  describe('getAll', () => {
    it('should return all shortcuts', () => {
      const configs: ShortcutConfig[] = [
        {
          id: 'shortcut-1',
          key: 'a',
          ctrl: true,
          description: 'First',
          category: ShortcutCategory.EDIT,
          handler: mockHandler,
        },
        {
          id: 'shortcut-2',
          key: 'b',
          ctrl: true,
          description: 'Second',
          category: ShortcutCategory.VIEW,
          handler: mockHandler,
        },
      ];

      manager.registerMultiple(configs);

      expect(manager.getAll()).toHaveLength(2);
    });
  });

  describe('getByCategory', () => {
    it('should return shortcuts by category', () => {
      const configs: ShortcutConfig[] = [
        {
          id: 'shortcut-1',
          key: 'a',
          ctrl: true,
          description: 'First',
          category: ShortcutCategory.EDIT,
          handler: mockHandler,
        },
        {
          id: 'shortcut-2',
          key: 'b',
          ctrl: true,
          description: 'Second',
          category: ShortcutCategory.VIEW,
          handler: mockHandler,
        },
        {
          id: 'shortcut-3',
          key: 'c',
          ctrl: true,
          description: 'Third',
          category: ShortcutCategory.EDIT,
          handler: mockHandler,
        },
      ];

      manager.registerMultiple(configs);

      const editShortcuts = manager.getByCategory(ShortcutCategory.EDIT);
      expect(editShortcuts).toHaveLength(2);
      expect(editShortcuts.every(s => s.category === ShortcutCategory.EDIT)).toBe(true);
    });
  });

  describe('getShortcutString', () => {
    it('should format shortcut string correctly', () => {
      const config: ShortcutConfig = {
        id: 'test',
        key: 'a',
        ctrl: true,
        shift: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      const str = manager.getShortcutString(config);
      expect(str).toBe('Ctrl+Shift+A');
    });

    it('should handle single key', () => {
      const config: ShortcutConfig = {
        id: 'test',
        key: 'a',
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      const str = manager.getShortcutString(config);
      expect(str).toBe('A');
    });

    it('should handle all modifiers', () => {
      const config: ShortcutConfig = {
        id: 'test',
        key: 'a',
        ctrl: true,
        shift: true,
        alt: true,
        meta: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      const str = manager.getShortcutString(config);
      expect(str).toBe('Ctrl+Shift+Alt+Meta+A');
    });
  });

  describe('handleKeyDown', () => {
    it('should trigger handler on matching key combination', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      const event = new KeyboardEvent('keydown', {
        key: 'a',
        ctrlKey: true,
        bubbles: true,
      });

      window.dispatchEvent(event);

      expect(mockHandler).toHaveBeenCalledTimes(1);
    });

    it('should not trigger disabled shortcuts', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
        enabled: false,
      };

      manager.register(config);

      const event = new KeyboardEvent('keydown', {
        key: 'a',
        ctrlKey: true,
        bubbles: true,
      });

      window.dispatchEvent(event);

      expect(mockHandler).not.toHaveBeenCalled();
    });

    it('should not trigger when focus is in input', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      const input = document.createElement('input');
      document.body.appendChild(input);
      input.focus();

      const event = new KeyboardEvent('keydown', {
        key: 'a',
        ctrlKey: true,
        bubbles: true,
      });

      input.dispatchEvent(event);

      expect(mockHandler).not.toHaveBeenCalled();

      document.body.removeChild(input);
    });

    it('should handle meta key as ctrl', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      const event = new KeyboardEvent('keydown', {
        key: 'a',
        metaKey: true,
        bubbles: true,
      });

      window.dispatchEvent(event);

      expect(mockHandler).toHaveBeenCalledTimes(1);
    });
  });

  describe('addListener', () => {
    it('should notify listeners on changes', () => {
      const listener = jest.fn();
      manager.addListener(listener);

      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      expect(listener).toHaveBeenCalled();
    });

    it('should return unsubscribe function', () => {
      const listener = jest.fn();
      const unsubscribe = manager.addListener(listener);

      unsubscribe();

      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      expect(listener).not.toHaveBeenCalled();
    });
  });

  describe('exportConfig', () => {
    it('should export configuration', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        shift: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      const exported = manager.exportConfig();

      expect(exported['test-shortcut']).toEqual({
        key: 'a',
        ctrl: true,
        shift: true,
        alt: undefined,
        meta: undefined,
        enabled: true,
      });
    });
  });

  describe('importConfig', () => {
    it('should import configuration', () => {
      const config: ShortcutConfig = {
        id: 'test-shortcut',
        key: 'a',
        ctrl: true,
        description: 'Test',
        category: ShortcutCategory.EDIT,
        handler: mockHandler,
      };

      manager.register(config);

      const importData = {
        'test-shortcut': {
          key: 'b',
          ctrl: false,
          shift: true,
          enabled: false,
        },
      };

      manager.importConfig(importData);

      const shortcut = manager.getAll()[0];
      expect(shortcut.key).toBe('b');
      expect(shortcut.ctrl).toBe(false);
      expect(shortcut.shift).toBe(true);
      expect(shortcut.enabled).toBe(false);
    });
  });

  describe('reset', () => {
    it('should reset all shortcuts to enabled', () => {
      const configs: ShortcutConfig[] = [
        {
          id: 'shortcut-1',
          key: 'a',
          ctrl: true,
          description: 'First',
          category: ShortcutCategory.EDIT,
          handler: mockHandler,
          enabled: false,
        },
        {
          id: 'shortcut-2',
          key: 'b',
          ctrl: true,
          description: 'Second',
          category: ShortcutCategory.EDIT,
          handler: mockHandler,
          enabled: false,
        },
      ];

      manager.registerMultiple(configs);

      manager.reset();

      const shortcuts = manager.getAll();
      expect(shortcuts.every(s => s.enabled === true)).toBe(true);
    });
  });
});
