// @AI_GENERATED
import React from 'react';
import { Steps, Progress, Space, Typography, Tag } from 'antd';
import { LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { NodeExecutionStatus, ExecutionStatus } from '../../types/pipeline';
import { td } from '../../utils/dataTranslation';

const { Text } = Typography;

interface PipelineProgressTrackerProps {
  nodes: NodeExecutionStatus[];
  currentNode: string | null;
  overallStatus: ExecutionStatus;
  backtestProgress?: { currentDay: number; totalDays: number; currentDate: string };
}

const STATUS_MAP: Record<string, 'wait' | 'process' | 'finish' | 'error'> = {
  waiting: 'wait',
  running: 'process',
  completed: 'finish',
  failed: 'error',
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  waiting: <ClockCircleOutlined />,
  running: <LoadingOutlined />,
  completed: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
  failed: <CloseCircleOutlined style={{ color: '#ff4d4f' }} />,
};

const PipelineProgressTracker: React.FC<PipelineProgressTrackerProps> = ({
  nodes, currentNode, overallStatus, backtestProgress,
}) => {
  const currentIdx = nodes.findIndex((n) => n.nodeId === currentNode);
  const { t } = useTranslation();

  return (
    <div style={{ padding: '12px 16px' }}>
      {backtestProgress && (
        <div style={{ marginBottom: 12 }}>
          <Space>
            <Text strong>{t('backtest.progress')}</Text>
            <Text>{backtestProgress.currentDate}</Text>
            <Tag color="blue">{t('backtest.dayProgress', { current: backtestProgress.currentDay, total: backtestProgress.totalDays })}</Tag>
          </Space>
          <Progress
            percent={Math.round((backtestProgress.currentDay / backtestProgress.totalDays) * 100)}
            size="small"
            style={{ marginTop: 4 }}
          />
        </div>
      )}
      <Steps
        size="small"
        current={currentIdx >= 0 ? currentIdx : 0}
        items={nodes.map((n) => ({
          title: td(n.label),
          status: STATUS_MAP[n.status] || 'wait',
          icon: STATUS_ICONS[n.status],
          description: n.status === 'completed' && n.duration != null
            ? `${n.duration.toFixed(2)}s`
            : n.status === 'failed' && n.error
              ? <Text type="danger" style={{ fontSize: 11 }}>{td(n.error).slice(0, 60)}</Text>
              : undefined,
        }))}
        style={{ overflowX: 'auto' }}
      />
    </div>
  );
};

export default PipelineProgressTracker;
// @AI_GENERATED: end
