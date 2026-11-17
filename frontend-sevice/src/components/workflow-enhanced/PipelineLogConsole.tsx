// @AI_GENERATED
import React, { useRef, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PipelineLogEntry } from '../../types/pipeline';
import { td } from '../../utils/dataTranslation';

interface PipelineLogConsoleProps {
  logs: PipelineLogEntry[];
  configSummary?: string;
  autoScroll?: boolean;
}

const TYPE_COLORS: Record<string, string> = {
  info: '#d9d9d9',
  start: '#1890ff',
  success: '#52c41a',
  error: '#ff4d4f',
  config: '#faad14',
  separator: '#722ed1',
};

const PipelineLogConsole: React.FC<PipelineLogConsoleProps> = ({
  logs, configSummary, autoScroll: autoScrollProp = true,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [userScrolled, setUserScrolled] = useState(false);
  const { t } = useTranslation();

  useEffect(() => {
    if (!userScrolled && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, userScrolled]);

  const handleScroll = () => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const atBottom = scrollHeight - scrollTop - clientHeight < 30;
    setUserScrolled(!atBottom);
  };

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      style={{
        background: '#1e1e1e',
        color: '#d4d4d4',
        fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
        fontSize: 13,
        lineHeight: 1.6,
        padding: '12px 16px',
        height: 260,
        overflowY: 'auto',
        borderRadius: 6,
      }}
    >
      {configSummary && (
        <div style={{ color: TYPE_COLORS.config, marginBottom: 4 }}>
          {td(configSummary)}
        </div>
      )}
      {logs.map((log, i) => {
        if (log.type === 'separator') {
          return (
            <div key={i} style={{ color: TYPE_COLORS.separator, margin: '6px 0' }}>
              {td(log.message)}
            </div>
          );
        }
        return (
          <div key={i} style={{ color: TYPE_COLORS[log.type] || '#d4d4d4' }}>
            <span style={{ color: '#888' }}>[{log.timestamp}]</span> {td(log.message)}
          </div>
        );
      })}
      {logs.length === 0 && (
        <div style={{ color: '#666' }}>{t('log.waiting')}</div>
      )}
    </div>
  );
};

export default PipelineLogConsole;
// @AI_GENERATED: end
