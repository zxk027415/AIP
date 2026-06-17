import React, { useState, useEffect } from 'react';
import './VersionPanel.css';

interface WorkflowVersion {
  id: string;
  workflow_id: string;
  version: number;
  name: string;
  description?: string;
  created_by: string;
  created_at: string;
  is_current: boolean;
  tags: string[];
}

interface VersionPanelProps {
  isOpen: boolean;
  onClose: () => void;
  workflowId: string;
  onRestore: (version: number) => void;
  onCompare: (fromVersion: number, toVersion: number) => void;
}

export const VersionPanel: React.FC<VersionPanelProps> = ({
  isOpen,
  onClose,
  workflowId,
  onRestore,
  onCompare,
}) => {
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedVersions, setSelectedVersions] = useState<number[]>([]);

  useEffect(() => {
    if (isOpen && workflowId) {
      loadVersions();
    }
  }, [isOpen, workflowId]);

  const loadVersions = async () => {
    setLoading(true);
    try {
      // 模拟API调用
      const mockVersions: WorkflowVersion[] = [
        {
          id: '1',
          workflow_id: workflowId,
          version: 3,
          name: '添加数据处理节点',
          description: '增加了数据清洗和转换功能',
          created_by: 'user1',
          created_at: new Date().toISOString(),
          is_current: true,
          tags: ['feature'],
        },
        {
          id: '2',
          workflow_id: workflowId,
          version: 2,
          name: '优化算法模板结构',
          description: '重新组织节点布局',
          created_by: 'user1',
          created_at: new Date(Date.now() - 3600000).toISOString(),
          is_current: false,
          tags: [],
        },
        {
          id: '3',
          workflow_id: workflowId,
          version: 1,
          name: '初始版本',
          description: '创建基础算法模板',
          created_by: 'user1',
          created_at: new Date(Date.now() - 7200000).toISOString(),
          is_current: false,
          tags: ['initial'],
        },
      ];
      setVersions(mockVersions);
    } catch (error) {
      console.error('加载版本失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleVersionClick = (version: number) => {
    if (selectedVersions.includes(version)) {
      setSelectedVersions(selectedVersions.filter(v => v !== version));
    } else {
      if (selectedVersions.length < 2) {
        setSelectedVersions([...selectedVersions, version]);
      } else {
        setSelectedVersions([selectedVersions[1], version]);
      }
    }
  };

  const handleRestore = (version: number) => {
    if (window.confirm(`确定要恢复到版本 ${version} 吗？`)) {
      onRestore(version);
    }
  };

  const handleCompare = () => {
    if (selectedVersions.length === 2) {
      const [v1, v2] = selectedVersions.sort((a, b) => a - b);
      onCompare(v1, v2);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
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
    <div className="version-panel">
      <div className="version-panel-header">
        <h3>📚 版本历史</h3>
        <button className="version-panel-close" onClick={onClose}>×</button>
      </div>

      {selectedVersions.length === 2 && (
        <div className="version-panel-compare-bar">
          <span>已选择 {selectedVersions.length} 个版本</span>
          <button className="version-compare-btn" onClick={handleCompare}>
            比较版本
          </button>
        </div>
      )}

      <div className="version-panel-content">
        {loading ? (
          <div className="version-panel-loading">
            <p>加载中...</p>
          </div>
        ) : versions.length === 0 ? (
          <div className="version-panel-empty">
            <p>暂无版本历史</p>
          </div>
        ) : (
          <div className="version-list">
            {versions.map(version => (
              <div
                key={version.id}
                className={`version-item ${version.is_current ? 'current' : ''} ${
                  selectedVersions.includes(version.version) ? 'selected' : ''
                }`}
                onClick={() => handleVersionClick(version.version)}
              >
                <div className="version-item-header">
                  <div className="version-item-title">
                    <span className="version-number">v{version.version}</span>
                    <span className="version-name">{version.name}</span>
                    {version.is_current && (
                      <span className="version-current-badge">当前</span>
                    )}
                  </div>
                  {!version.is_current && (
                    <button
                      className="version-restore-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRestore(version.version);
                      }}
                    >
                      恢复
                    </button>
                  )}
                </div>

                {version.description && (
                  <div className="version-item-description">
                    {version.description}
                  </div>
                )}

                <div className="version-item-meta">
                  <span className="version-item-author">
                    👤 {version.created_by}
                  </span>
                  <span className="version-item-time">
                    🕐 {formatDate(version.created_at)}
                  </span>
                </div>

                {version.tags.length > 0 && (
                  <div className="version-item-tags">
                    {version.tags.map(tag => (
                      <span key={tag} className="version-tag">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="version-panel-footer">
        <p className="version-panel-hint">
          点击版本可选择，最多选择2个版本进行比较
        </p>
      </div>
    </div>
  );
};
