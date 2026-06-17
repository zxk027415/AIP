import React, { useState, useEffect } from 'react';
import { shortcutManager, ShortcutConfig } from '../../utils/shortcuts/KeyboardShortcutManager';
import './KeyboardShortcutsHelp.css';

interface KeyboardShortcutsHelpProps {
  isOpen: boolean;
  onClose: () => void;
}

export const KeyboardShortcutsHelp: React.FC<KeyboardShortcutsHelpProps> = ({ isOpen, onClose }) => {
  const [shortcuts, setShortcuts] = useState<ShortcutConfig[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  useEffect(() => {
    const updateShortcuts = () => {
      setShortcuts(shortcutManager.getAll());
    };

    updateShortcuts();
    const unsubscribe = shortcutManager.addListener(updateShortcuts);

    return unsubscribe;
  }, []);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // 获取所有类别
  const categories = ['all', ...new Set(shortcuts.map(s => s.category))];

  // 过滤快捷键
  const filteredShortcuts = shortcuts.filter(shortcut => {
    const matchesSearch = 
      shortcut.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
      shortcutManager.getShortcutString(shortcut).toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesCategory = selectedCategory === 'all' || shortcut.category === selectedCategory;

    return matchesSearch && matchesCategory;
  });

  // 按类别分组
  const groupedShortcuts = filteredShortcuts.reduce((acc, shortcut) => {
    if (!acc[shortcut.category]) {
      acc[shortcut.category] = [];
    }
    acc[shortcut.category].push(shortcut);
    return acc;
  }, {} as Record<string, ShortcutConfig[]>);

  return (
    <div className="shortcuts-help-overlay" onClick={onClose}>
      <div className="shortcuts-help-modal" onClick={(e) => e.stopPropagation()}>
        <div className="shortcuts-help-header">
          <h2>⌨️ 键盘快捷键</h2>
          <button className="shortcuts-help-close" onClick={onClose}>×</button>
        </div>

        <div className="shortcuts-help-toolbar">
          <input
            type="text"
            className="shortcuts-help-search"
            placeholder="搜索快捷键..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />

          <div className="shortcuts-help-categories">
            {categories.map(category => (
              <button
                key={category}
                className={`shortcuts-help-category-btn ${selectedCategory === category ? 'active' : ''}`}
                onClick={() => setSelectedCategory(category)}
              >
                {category === 'all' ? '全部' : category}
              </button>
            ))}
          </div>
        </div>

        <div className="shortcuts-help-content">
          {Object.entries(groupedShortcuts).map(([category, categoryShortcuts]) => (
            <div key={category} className="shortcuts-help-group">
              <h3 className="shortcuts-help-group-title">{category}</h3>
              <div className="shortcuts-help-list">
                {categoryShortcuts.map(shortcut => (
                  <div key={shortcut.id} className="shortcuts-help-item">
                    <span className="shortcuts-help-description">
                      {shortcut.description}
                    </span>
                    <kbd className="shortcuts-help-keys">
                      {shortcutManager.getShortcutString(shortcut)}
                    </kbd>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {filteredShortcuts.length === 0 && (
            <div className="shortcuts-help-empty">
              <p>未找到匹配的快捷键</p>
            </div>
          )}
        </div>

        <div className="shortcuts-help-footer">
          <p>按 <kbd>?</kbd> 或 <kbd>Esc</kbd> 关闭此窗口</p>
        </div>
      </div>
    </div>
  );
};
