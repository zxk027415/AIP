// @AI_GENERATED
import React from 'react';
import { List, Tag, Typography, Button, Space, Empty } from 'antd';
import { HistoryOutlined, ReloadOutlined, EyeOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ExecutionRecord, ExecutionStatus } from '../../types/pipeline';
import { td } from '../../utils/dataTranslation';

const { Text } = Typography;

interface ExecutionHistoryPanelProps {
  history: ExecutionRecord[];
  onLoadConfig: (record: ExecutionRecord) => void;
  onViewResult?: (record: ExecutionRecord) => void;
}

const STATUS_COLORS: Record<ExecutionStatus, string> = {
  idle: 'default',
  pending: 'processing',
  running: 'processing',
  success: 'success',
  failed: 'error',
};

const ExecutionHistoryPanel: React.FC<ExecutionHistoryPanelProps> = ({ history, onLoadConfig, onViewResult }) => {
  const { t, i18n } = useTranslation();

  const TYPE_LABELS: Record<string, string> = {
    training: t('history.training'),
    prediction: t('history.prediction'),
    backtest: t('history.backtest'),
  };

  const STATUS_LABELS: Record<ExecutionStatus, string> = {
    idle: t('execution.status'),
    pending: t('log.waiting'),
    running: t('backtestMonitor.executing'),
    success: t('execution.success'),
    failed: t('execution.failed'),
  };

  if (history.length === 0) {
    return <Empty description={t('history.noRecords')} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <List
      size="small"
      dataSource={[...history].reverse()}
      renderItem={(record) => (
        <List.Item
          actions={[
            onViewResult && (record as any).resultPayload ? (
              <Button
                size="small"
                type="primary"
                icon={<EyeOutlined />}
                onClick={() => onViewResult(record)}
              >
                {t('history.viewResult') || '查看结果'}
              </Button>
            ) : null,
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => onLoadConfig(record)}
            >
              {t('history.loadConfig')}
            </Button>,
          ].filter(Boolean)}
        >
          <List.Item.Meta
            avatar={<HistoryOutlined />}
            title={
              <Space size={4}>
                <Text>{td(record.templateName)}</Text>
                <Tag>{TYPE_LABELS[record.templateType] || record.templateType}</Tag>
                <Tag color={STATUS_COLORS[record.status]}>{STATUS_LABELS[record.status] || record.status}</Tag>
              </Space>
            }
            description={
              <Space size={8}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {record.executionId.slice(0, 8)}
                </Text>
                {record.modelId && <Text type="secondary" style={{ fontSize: 12 }}>{t('history.model')}: {record.modelId.slice(0, 12)}</Text>}
                {record.totalDuration != null && <Text type="secondary" style={{ fontSize: 12 }}>{record.totalDuration.toFixed(1)}s</Text>}
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {new Date(record.createdAt).toLocaleString((i18n.language || '').toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN')}
                </Text>
              </Space>
            }
          />
        </List.Item>
      )}
    />
  );
};

export default ExecutionHistoryPanel;
// @AI_GENERATED: end
