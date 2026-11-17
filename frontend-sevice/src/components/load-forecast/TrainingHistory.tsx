// @AI_GENERATED
/**
 * 训练历史记录组件
 *
 * 展示当前会话的训练记录列表，点击记录可回填参数到表单。
 */
import React, { useMemo } from 'react';
import { List, Tag, Typography, Empty } from 'antd';
import { useTranslation } from 'react-i18next';
import type { TrainingRecord, TaskStatus } from '../../types/load-forecast';

const { Text } = Typography;

export interface TrainingHistoryProps {
  records: TrainingRecord[];
  onSelect: (record: TrainingRecord) => void;
}

/** 状态对应的 Tag 颜色 */
const STATUS_COLORS: Record<TaskStatus, string> = {
  idle: 'default',
  pending: 'processing',
  running: 'processing',
  success: 'success',
  failed: 'error',
};

const TrainingHistory: React.FC<TrainingHistoryProps> = ({
  records,
  onSelect,
}) => {
  const { t } = useTranslation();

  const statusLabel = useMemo(
    () => (s: TaskStatus) => t(`loadForecast.history.taskStatus.${s}`),
    [t],
  );

  const taskTypeLabel = useMemo(
    () => (code: string) => {
      const k = `loadForecast.taskTypes.${code}`;
      const tr = t(k);
      return tr === k ? code : tr;
    },
    [t],
  );

  if (records.length === 0) {
    return (
      <Empty
        description={t('loadForecast.history.empty')}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  return (
    <List
      size="small"
      dataSource={[...records].reverse()}
      renderItem={(record) => {
        const taskLabel = taskTypeLabel(record.task_type);
        return (
          <List.Item
            onClick={() => onSelect(record)}
            style={{ cursor: 'pointer', padding: '8px 12px' }}
          >
            <List.Item.Meta
              title={
                <span>
                  <Tag color={STATUS_COLORS[record.status]}>
                    {statusLabel(record.status)}
                  </Tag>
                  <Text strong>{taskLabel}</Text>
                </span>
              }
              description={
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {record.task_id}
                  </Text>
                  {record.model_id && (
                    <>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        Model: {record.model_id}
                      </Text>
                    </>
                  )}
                  {record.total_duration != null && (
                    <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                      {t('loadForecast.history.duration', {
                        seconds: record.total_duration.toFixed(2),
                      })}
                    </Text>
                  )}
                </div>
              }
            />
          </List.Item>
        );
      }}
    />
  );
};

export default TrainingHistory;
// @AI_GENERATED: end
