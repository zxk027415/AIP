// @AI_GENERATED
/**
 * 训练日志控制台组件
 *
 * 深色背景、等宽字体的终端风格面板，
 * 日志条目根据类型着色，自动滚动到最新日志。
 */
import React, { useEffect, useRef } from 'react';
import { Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import type { LogEntry } from '../../types/load-forecast';

export interface LogConsoleProps {
  logs: LogEntry[];
  configSummary?: string;
}

/** 日志类型对应的颜色 */
const LOG_COLORS: Record<LogEntry['type'], string> = {
  start: '#58a6ff',   // 高亮蓝色
  success: '#3fb950', // 绿色
  error: '#f85149',   // 红色
  info: '#e6edf3',    // 白色
  config: '#8b949e',  // 灰色
};

const LogConsole: React.FC<LogConsoleProps> = ({ logs, configSummary }) => {
  const { t } = useTranslation();
  const bottomRef = useRef<HTMLDivElement>(null);

  // 自动滚动到最新日志
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  if (logs.length === 0) {
    return (
      <div
        style={{
          backgroundColor: '#1e1e1e',
          borderRadius: 6,
          padding: 24,
          minHeight: 200,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Empty
          description={<span style={{ color: '#8b949e' }}>{t('loadForecast.log.empty')}</span>}
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        backgroundColor: '#1e1e1e',
        borderRadius: 6,
        padding: '12px 16px',
        maxHeight: 400,
        overflowY: 'auto',
        fontFamily: "'Cascadia Code', 'Fira Code', 'Consolas', monospace",
        fontSize: 13,
        lineHeight: 1.7,
      }}
    >
      {logs.map((log, index) => (
        <div
          key={index}
          style={{
            color: LOG_COLORS[log.type] || LOG_COLORS.info,
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
          }}
        >
          <span style={{ color: '#6e7681', marginRight: 8 }}>
            [{log.timestamp}]
          </span>
          {log.message}
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
};

export default LogConsole;
// @AI_GENERATED: end
