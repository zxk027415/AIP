import React, { useState, useEffect } from 'react';
import { historyManager } from '../../utils/commands';
import { Command } from '../../utils/commands/Command';
import './HistoryPanel.css';

interface HistoryPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export const HistoryPanel: React.FC<HistoryPanelProps> = ({ isOpen, onClose }) => {
  const [undoStack, setUndoStack] = useState<Command[]>([]);
  const [redoStack, setRedoStack] = useState<Command[]>([]);
  const [currentPosition, setCurrentPosition] = useState(0);

  useEffect(() => {
    const updateHistory = () => {
      setUndoStack(historyManager.getUndoStack());
      setRedoStack(historyManager.getRedoStack());
      setCurrentPosition(historyManager.getCurrentPosition());
    };

    updateHistory();
    const unsubscribe = historyManager.addListener(updateHistory);

    return unsubscribe;
  }, []);

  const handleUndo = () => {
    historyManager.undo();
  };

  const handleRedo = () => {
    historyManager.redo();
  };

  const handleClear = () => {
    if (window.confirm('确定要清空历史记录吗？')) {
      historyManager.clear();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="history-panel">
      <div className="history-panel-header">
        <h3>操作历史</h3>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>

      <div className="history-panel-toolbar">
        <button
          className="history-btn"
          onClick={handleUndo}
          disabled={!historyManager.canUndo()}
          title="撤销 (Ctrl+Z)"
        >
          ↶ 撤销
        </button>
        <button
          className="history-btn"
          onClick={handleRedo}
          disabled={!historyManager.canRedo()}
          title="重做 (Ctrl+Y)"
        >
          ↷ 重做
        </button>
        <button
          className="history-btn clear-btn"
          onClick={handleClear}
          disabled={undoStack.length === 0}
        >
          清空
        </button>
      </div>

      <div className="history-panel-content">
        <div className="history-list">
          {/* 重做栈（反向显示） */}
          {[...redoStack].reverse().map((command, index) => (
            <div key={`redo-${index}`} className="history-item redo-item">
              <span className="history-icon">↷</span>
              <span className="history-description">{command.getDescription()}</span>
            </div>
          ))}

          {/* 当前位置指示器 */}
          {undoStack.length > 0 && (
            <div className="history-current-indicator">
              <span>当前位置</span>
            </div>
          )}

          {/* 撤销栈（反向显示） */}
          {[...undoStack].reverse().map((command, index) => (
            <div key={`undo-${index}`} className="history-item undo-item">
              <span className="history-icon">↶</span>
              <span className="history-description">{command.getDescription()}</span>
            </div>
          ))}

          {undoStack.length === 0 && redoStack.length === 0 && (
            <div className="history-empty">
              <p>暂无操作历史</p>
            </div>
          )}
        </div>
      </div>

      <div className="history-panel-footer">
        <span className="history-stats">
          {undoStack.length} 个可撤销操作 | {redoStack.length} 个可重做操作
        </span>
      </div>
    </div>
  );
};
