import { useEffect } from 'react';
import { historyManager } from '../utils/commands';

interface ShortcutConfig {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  handler: () => void;
  description: string;
}

/**
 * 键盘快捷键 Hook
 */
export const useKeyboardShortcuts = (shortcuts: ShortcutConfig[]) => {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // 如果焦点在输入框，不触发快捷键
      const target = event.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return;
      }

      for (const shortcut of shortcuts) {
        const keyMatch = event.key.toLowerCase() === shortcut.key.toLowerCase();
        const ctrlMatch = shortcut.ctrl ? event.ctrlKey || event.metaKey : !event.ctrlKey && !event.metaKey;
        const shiftMatch = shortcut.shift ? event.shiftKey : !event.shiftKey;
        const altMatch = shortcut.alt ? event.altKey : !event.altKey;

        if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
          event.preventDefault();
          shortcut.handler();
          break;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts]);
};

/**
 * 撤销/重做快捷键 Hook
 */
export const useUndoRedoShortcuts = () => {
  useKeyboardShortcuts([
    {
      key: 'z',
      ctrl: true,
      handler: () => historyManager.undo(),
      description: '撤销',
    },
    {
      key: 'y',
      ctrl: true,
      handler: () => historyManager.redo(),
      description: '重做',
    },
    {
      key: 'z',
      ctrl: true,
      shift: true,
      handler: () => historyManager.redo(),
      description: '重做（备选）',
    },
  ]);
};
