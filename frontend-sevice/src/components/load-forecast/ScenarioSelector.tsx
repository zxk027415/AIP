// @AI_GENERATED
/**
 * 场景选择器组件
 *
 * 以卡片网格形式展示 6 种负荷预测场景（DI/D/WI/W/MI/M），
 * 选中卡片高亮显示，支持 loading 和错误状态。
 */
import React, { useMemo } from 'react';
import { Row, Col, Card, Skeleton, Alert, Button, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { ScenarioConfig } from '../../types/load-forecast';
import { td } from '../../utils/dataTranslation';

const { Text, Paragraph } = Typography;

export interface ScenarioSelectorProps {
  scenarios: ScenarioConfig[];
  selectedTaskType: string | null;
  loading: boolean;
  error?: string | null;
  onSelect: (taskType: string) => void;
  onRetry?: () => void;
}

const ScenarioSelector: React.FC<ScenarioSelectorProps> = ({
  scenarios,
  selectedTaskType,
  loading,
  error,
  onSelect,
  onRetry,
}) => {
  const { t } = useTranslation();

  const taskTitle = useMemo(
    () => (code: string, fallback: string) => {
      const k = `loadForecast.taskTypes.${code}`;
      const tr = t(k);
      return tr === k ? fallback : tr;
    },
    [t],
  );

  // 加载中：展示 Skeleton 占位
  if (loading) {
    return (
      <Row gutter={[16, 16]}>
        {Array.from({ length: 6 }).map((_, index) => (
          <Col xs={24} sm={12} md={8} key={index}>
            <Card>
              <Skeleton active paragraph={{ rows: 2 }} />
            </Card>
          </Col>
        ))}
      </Row>
    );
  }

  // 加载失败：展示错误提示 + 重试按钮
  if (error) {
    return (
      <Alert
        type="error"
        message={t('loadForecast.scenario.loadFailed')}
        description={error}
        showIcon
        action={
          onRetry ? (
            <Button size="small" icon={<ReloadOutlined />} onClick={onRetry}>
              {t('loadForecast.scenario.retry')}
            </Button>
          ) : undefined
        }
      />
    );
  }

  return (
    <Row gutter={[16, 16]}>
      {scenarios.map((scenario) => {
        const isSelected = selectedTaskType === scenario.task_type;
        return (
          <Col xs={24} sm={12} md={8} key={scenario.task_type}>
            <Card
              hoverable
              onClick={() => onSelect(scenario.task_type)}
              style={{
                borderColor: isSelected ? '#1890ff' : undefined,
                borderWidth: isSelected ? 2 : 1,
                backgroundColor: isSelected ? '#e6f7ff' : undefined,
                cursor: 'pointer',
              }}
              styles={{
                body: { padding: '16px' },
              }}
            >
              <div style={{ marginBottom: 8 }}>
                <Tag color={isSelected ? 'blue' : 'default'}>
                  {scenario.task_type}
                </Tag>
                <Text strong>
                  {taskTitle(scenario.task_type, scenario.name)}
                </Text>
              </div>
              <Paragraph
                type="secondary"
                ellipsis={{ rows: 2 }}
                style={{ marginBottom: 0 }}
              >
                {td(scenario.description || scenario.name)}
              </Paragraph>
            </Card>
          </Col>
        );
      })}
    </Row>
  );
};

export default ScenarioSelector;
// @AI_GENERATED: end
