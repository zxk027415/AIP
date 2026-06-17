import React, { useState, useEffect } from 'react';
import { autoSaveManager, DraftData } from '../../utils/autosave/AutoSaveManager';
// @AI_GENERATED
import { td } from '../../utils/dataTranslation';
// @AI_GENERATED: end
import './DraftRecoveryDialog.css';

interface DraftRecoveryDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onRestore: (draft: DraftData) => void;
}

export const DraftRecoveryDialog: React.FC<DraftRecoveryDialogProps> = ({
  isOpen,
  onClose,
  onRestore,
}) => {
  const [drafts, setDrafts] = useState<DraftData[]>([]);
  const [selectedDraft, setSelectedDraft] = useState<DraftData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadDrafts();
    }
  }, [isOpen]);

  const loadDrafts = async () => {
    setLoading(true);
    try {
      const draftList = await autoSaveManager.getDrafts();
      setDrafts(draftList);
    } catch (error) {
      console.error('加载草稿失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRestore = () => {
    if (selectedDraft) {
      onRestore(selectedDraft);
      onClose();
    }
  };

  const handleDelete = async (draftId: string, event: React.MouseEvent) => {
    event.stopPropagation();
    
    if (window.confirm('确定要删除这个草稿吗？')) {
      await autoSaveManager.deleteDraft(draftId);
      await loadDrafts();
      if (selectedDraft?.id === draftId) {
        setSelectedDraft(null);
      }
    }
  };

  const formatDate = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    
    if (diff < 60000) {
      return '刚刚';
    } else if (diff < 3600000) {
      return `${Math.floor(diff / 60000)} 分钟前`;
    } else if (diff < 86400000) {
      return `${Math.floor(diff / 3600000)} 小时前`;
    } else {
      return date.toLocaleString('zh-CN');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="draft-recovery-overlay" onClick={onClose}>
      <div className="draft-recovery-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="draft-recovery-header">
          <h2>📂 恢复草稿</h2>
          <button className="draft-recovery-close" onClick={onClose}>×</button>
        </div>

        <div className="draft-recovery-content">
          {loading ? (
            <div className="draft-recovery-loading">
              <p>加载中...</p>
            </div>
          ) : drafts.length === 0 ? (
            <div className="draft-recovery-empty">
              <p>没有可恢复的草稿</p>
            </div>
          ) : (
            <div className="draft-recovery-list">
              {drafts.map(draft => (
                <div
                  key={draft.id}
                  className={`draft-recovery-item ${selectedDraft?.id === draft.id ? 'selected' : ''}`}
                  onClick={() => setSelectedDraft(draft)}
                >
                  <div className="draft-recovery-item-header">
                    <span className="draft-recovery-item-name">
                      {draft.name || td('未命名算法模板')}
                    </span>
                    <button
                      className="draft-recovery-item-delete"
                      onClick={(e) => handleDelete(draft.id, e)}
                      title="删除草稿"
                    >
                      🗑️
                    </button>
                  </div>
                  <div className="draft-recovery-item-meta">
                    <span className="draft-recovery-item-time">
                      {formatDate(draft.timestamp)}
                    </span>
                    <span className="draft-recovery-item-stats">
                      {draft.nodes.length} 个节点 · {draft.edges.length} 条连接
                    </span>
                  </div>
                  {selectedDraft?.id === draft.id && (
                    <div className="draft-recovery-item-preview">
                      <div className="draft-recovery-item-preview-label">预览</div>
                      <div className="draft-recovery-item-preview-content">
                        <div>版本: {draft.version}</div>
                        <div>ID: {draft.id}</div>
                        {draft.originalId && <div>原始ID: {draft.originalId}</div>}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="draft-recovery-footer">
          <button
            className="draft-recovery-btn draft-recovery-btn-cancel"
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="draft-recovery-btn draft-recovery-btn-restore"
            onClick={handleRestore}
            disabled={!selectedDraft}
          >
            恢复选中的草稿
          </button>
        </div>
      </div>
    </div>
  );
};
