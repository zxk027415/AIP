// @AI_GENERATED
/**
 * 训练结果仪表盘组件
 *
 * 训练成功时展示 model_id（带复制按钮）、总耗时、场景类型、训练时间。
 * 提供"快速回测"（默认2天）和自定义日期范围回测。
 */
import React, { useMemo, useState } from 'react';
import {
  Card,
  Descriptions,
  Button,
  Space,
  Tag,
  Typography,
  message,
  Spin,
  DatePicker,
  Divider,
} from 'antd';
import {
  CopyOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import { useTranslation } from 'react-i18next';
import type { TrainingResult, BacktestResult } from '../../types/load-forecast';
import MetricsChart from './MetricsChart';

const { Text } = Typography;
const { RangePicker } = DatePicker;

export interface ResultDashboardProps {
  result: TrainingResult;
  stepDurations: Record<string, number>;
  onCopyModelId: () => void;
  onStartBacktest: (startDate?: string, endDate?: string) => void;
  backtestResult?: BacktestResult;
  backtestLoading: boolean;
}

const ResultDashboard: React.FC<ResultDashboardProps> = ({
  result,
  stepDurations,
  onCopyModelId,
  onStartBacktest,
  backtestResult,
  backtestLoading,
}) => {
  const { t, i18n } = useTranslation();
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);

  const dateLocale = i18n.language?.toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN';

  const taskLabel = useMemo(() => {
    const k = `loadForecast.taskTypes.${result.task_type}`;
    const tr = t(k);
    return tr === k ? result.task_type : tr;
  }, [t, result.task_type]);

  const handleCopy = () => {
    if (result.model_id) {
      navigator.clipboard.writeText(result.model_id).then(() => {
        message.success(t('loadForecast.result.copySuccess'));
        onCopyModelId();
      }).catch(() => {
        message.error(t('loadForecast.result.copyFailed'));
      });
    }
  };

  const handleQuickBacktest = () => {
    onStartBacktest(); // 不传日期，使用页面默认的 2 天
  };

  const handleCustomBacktest = () => {
    if (!dateRange) {
      message.warning(t('loadForecast.result.selectBacktestRange'));
      return;
    }
    const startDate = dateRange[0].format('YYYY-MM-DD');
    const endDate = dateRange[1].format('YYYY-MM-DD');
    onStartBacktest(startDate, endDate);
  };

  return (
    <div>
      {/* 基本信息 */}
      <Descriptions column={{ xs: 1, sm: 2 }} bordered size="small">
        <Descriptions.Item label={t('loadForecast.result.modelId')}>
          <Space>
            <Text code copyable={false}>{result.model_id}</Text>
            <Button
              type="link"
              size="small"
              icon={<CopyOutlined />}
              onClick={handleCopy}
            >
              {t('loadForecast.result.copy')}
            </Button>
          </Space>
        </Descriptions.Item>
        <Descriptions.Item label={t('loadForecast.result.totalDuration')}>
          {result.total_duration.toFixed(2)}s
        </Descriptions.Item>
        <Descriptions.Item label={t('loadForecast.result.trainingScenario')}>
          <Tag color="blue">{taskLabel}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label={t('loadForecast.result.trainingTime')}>
          {result.created_at ? new Date(result.created_at).toLocaleString(dateLocale) : '-'}
        </Descriptions.Item>
      </Descriptions>

      {/* 步骤耗时图表 */}
      {Object.keys(stepDurations).length > 0 && (
        <div style={{ marginTop: 16 }}>
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <MetricsChart
              type="step-duration-bar"
              data={stepDurations}
              title={t('loadForecast.result.stepDurationBarTitle')}
            />
            <MetricsChart
              type="step-duration-pie"
              data={stepDurations}
              title={t('loadForecast.result.stepDurationPieTitle')}
            />
          </Space>
        </div>
      )}

      {/* 回测区域 */}
      <Divider style={{ margin: '16px 0 12px' }}>{t('loadForecast.result.backtestDivider')}</Divider>

      <Space direction="vertical" style={{ width: '100%' }} size="small">
        {/* 快速回测 */}
        <Space>
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={handleQuickBacktest}
            loading={backtestLoading}
          >
            {t('loadForecast.result.quickBacktest')}
          </Button>
        </Space>

        {/* 自定义日期范围回测 */}
        <Space wrap>
          <RangePicker
            size="small"
            format="YYYY-MM-DD"
            value={dateRange}
            onChange={(dates) => setDateRange(dates as [Dayjs, Dayjs] | null)}
            placeholder={[t('loadForecast.result.startDate'), t('loadForecast.result.endDate')]}
            disabled={backtestLoading}
          />
          <Button
            icon={<ExperimentOutlined />}
            onClick={handleCustomBacktest}
            loading={backtestLoading}
            disabled={!dateRange}
          >
            {t('loadForecast.result.customBacktest')}
          </Button>
        </Space>
      </Space>

      {/* 回测进行中 */}
      {backtestLoading && (
        <div style={{ marginTop: 16, textAlign: 'center' }}>
          <Spin tip={t('loadForecast.result.backtestRunning')} />
        </div>
      )}

      {/* 回测结果 */}
      {backtestResult && (
        <div style={{ marginTop: 16 }}>
          <Card title={t('loadForecast.result.backtestResultTitle')} size="small">
            <Descriptions column={{ xs: 1, sm: 2, md: 4 }} size="small">
              <Descriptions.Item label={t('loadForecast.result.successDays')}>
                <Tag color="green">{backtestResult.success_days}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('loadForecast.result.skippedDays')}>
                <Tag color="orange">{backtestResult.skipped_days}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('loadForecast.result.failedDays')}>
                <Tag color="red">{backtestResult.failed_days}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('loadForecast.result.totalDurationShort')}>
                {backtestResult.duration_seconds?.toFixed(2) ?? '-'}s
              </Descriptions.Item>
            </Descriptions>

            {backtestResult.daily_results && backtestResult.daily_results.length > 0 && (
              <Space direction="vertical" style={{ width: '100%', marginTop: 12 }} size="middle">
                <MetricsChart
                  type="backtest-line"
                  data={backtestResult.daily_results}
                  title={t('loadForecast.result.chartCompareTitle')}
                />
                <MetricsChart
                  type="backtest-bar"
                  data={backtestResult.daily_results}
                  title={t('loadForecast.result.chartPointsTitle')}
                />
              </Space>
            )}
          </Card>
        </div>
      )}
    </div>
  );
};

export default ResultDashboard;
// @AI_GENERATED: end
