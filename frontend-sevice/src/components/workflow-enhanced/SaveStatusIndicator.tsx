import React, { useState, useEffect } from 'react';
import { autoSaveManager, SaveStatus } from '../../utils/autosave/AutoSaveManager';
import './SaveStatusIndicator.css';

export const SaveStatusIndicator: React.FC = () => {
  const [status, setStatus] = useState<SaveStatus>(autoSaveManager.getStatus());
  const [lastSaveTime, setLastSaveTime] = useState<number>(autoSaveManager.getLastSaveTime());

  useEffect(() => {
    const unsubscribe = autoSaveManager.addListener((newStatus) => {
      setStatus(newStatus);
      if (newStatus.state === 'saved') {
        setLastSaveTime(Date.now());
      }
    });

    return unsubscribe;
  }, []);

  const getStatusIcon = () => {
    switch (status.state) {
      case 'saving':
        return '⏳';
      case 'saved':
        return '✓';
      case 'error':
        return '⚠️';
      default:
        return '○';
    }
  };

  const getStatusClass = () => {
    switch (status.state) {
      case 'saving':
        return 'saving';
      case 'saved':
        return 'saved';
      case 'error':
        return 'error';
      default:
        return 'idle';
    }
  };

  const formatLastSaveTime = () => {
    if (!lastSaveTime) return '';
    
    const now = Date.now();
    const diff = now - lastSaveTime;
    
    if (diff < 60000) {
      return '刚刚保存';
    } else if (diff < 3600000) {
      return `${Math.floor(diff / 60000)} 分钟前保存`;
    } else {
      return new Date(lastSaveTime).toLocaleTimeString('zh-CN');
    }
  };

  return (
    <div className={`save-status-indicator ${getStatusClass()}`}>
      <span className="save-status-icon">{getStatusIcon()}</span>
      <span className="save-status-text">
        {status.message}
        {status.state === 'saved' && lastSaveTime && (
          <span className="save-status-time"> · {formatLastSaveTime()}</span>
        )}
      </span>
    </div>
  );
};
