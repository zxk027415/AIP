// @AI_GENERATED
import React from 'react';
import { Card, Row, Col, Statistic, Button, Space, Typography, Tag, message, DatePicker, InputNumber, Spin } from 'antd';
import { CopyOutlined, ExperimentOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type { TrainingPipelineResult } from '../../types/pipeline';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import { td } from '../../utils/dataTranslation';
import { usePipelineExecutionStore } from '../../stores/pipelineExecutionStore';

const { Text } = Typography;

interface TrainingResultDashboardProps {
  result: TrainingPipelineResult;
  onStartBacktest?: (days: number) => void;
  onStopBacktest?: () => void;
  backtestLoading?: boolean;
}

const TrainingResultDashboard: React.FC<TrainingResultDashboardProps> = ({ result, onStartBacktest, onStopBacktest, backtestLoading }) => {
  const quickBacktestDays = usePipelineExecutionStore((s) => s.quickBacktestDays);
  const setQuickBacktestDays = usePipelineExecutionStore((s) => s.setQuickBacktestDays);
  const { t, i18n } = useTranslation();
  const handleCopyModelId = () => {
    if (result.modelId) {
      navigator.clipboard.writeText(result.modelId);
      message.success(t('training.modelIdCopied'));
    }
  };

  const durationEntries = Object.entries(result.nodeDurations || {});
  const durationChartData = durationEntries.map(([k, v]) => ({
    name: td(k),
    value: Number(v).toFixed(2),
  }));
  const barOption = {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 120, right: 30, top: 10, bottom: 30 },
    xAxis: { type: 'value' as const, name: t('training.seconds') },
    yAxis: { type: 'category' as const, data: durationChartData.map((d) => d.name), inverse: true },
    series: [{ type: 'bar', data: durationChartData.map((d) => d.value), itemStyle: { color: '#1890ff' } }],
  };

  const pieOption = {
    tooltip: { trigger: 'item' as const },
    series: [{
      type: 'pie', radius: ['40%', '70%'],
      data: durationChartData,
      label: { show: true, formatter: '{b}: {d}%' },
    }],
  };

  return (
    <div style={{ padding: 16 }}>
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card size="small"><Statistic title={t('training.totalDuration')} value={result.totalDuration?.toFixed(2)} suffix={t('training.seconds')} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title={t('training.template')} value={td(result.templateName)} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title={t('training.completionTime')} value={result.completedAt ? new Date(result.completedAt).toLocaleString((i18n.language || '').toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN') : '-'} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Space direction="vertical" size={0}>
              <Text type="secondary">{t('execution.modelId')}</Text>
              <Space>
                <Text copyable={false} style={{ fontSize: 13 }}>{result.modelId || '-'}</Text>
                {result.modelId && <Button size="small" icon={<CopyOutlined />} onClick={handleCopyModelId} />}
              </Space>
            </Space>
          </Card>
        </Col>
      </Row>

      {result.metrics && (
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          {result.metrics.smape != null && (
            <Col span={6}><Card size="small"><Statistic title="SMAPE" value={result.metrics.smape.toFixed(2)} suffix="%" precision={2} /></Card></Col>
          )}
          {result.metrics.mae != null && (
            <Col span={6}><Card size="small"><Statistic title="MAE" value={result.metrics.mae.toFixed(4)} precision={4} /></Card></Col>
          )}
          {result.metrics.rmse != null && (
            <Col span={6}><Card size="small"><Statistic title="RMSE" value={result.metrics.rmse.toFixed(4)} precision={4} /></Card></Col>
          )}
          {result.metrics.mse != null && (
            <Col span={6}><Card size="small"><Statistic title="MSE" value={result.metrics.mse.toFixed(4)} precision={4} /></Card></Col>
          )}
          {/* 分类指标（光伏故障诊断） */}
          {result.metrics.accuracy != null && (
            <Col span={6}><Card size="small"><Statistic title="Accuracy（准确率）" value={(result.metrics.accuracy * 100).toFixed(2)} suffix="%" valueStyle={{ color: '#52c41a' }} /></Card></Col>
          )}
          {result.metrics.precision != null && (
            <Col span={6}><Card size="small"><Statistic title="Precision（精确率）" value={(result.metrics.precision * 100).toFixed(2)} suffix="%" /></Card></Col>
          )}
          {result.metrics.recall != null && (
            <Col span={6}><Card size="small"><Statistic title="Recall（召回率）" value={(result.metrics.recall * 100).toFixed(2)} suffix="%" /></Card></Col>
          )}
          {result.metrics.f1 != null && (
            <Col span={6}><Card size="small"><Statistic title="F1 Score（macro）" value={(result.metrics.f1 * 100).toFixed(2)} suffix="%" valueStyle={{ color: '#1890ff' }} /></Card></Col>
          )}
        </Row>
      )}

      {/* 混淆矩阵热图 */}
      {result.metrics?.confusion_matrix && (() => {
        const cm = result.metrics.confusion_matrix!;
        const labels = cm.labels;
        const n = labels.length;
        // 构建 ECharts heatmap data: [col, row, value]
        const heatData: [number, number, number][] = [];
        for (let row = 0; row < n; row++) {
          for (let col = 0; col < n; col++) {
            heatData.push([col, row, cm.data[row][col]]);
          }
        }
        const maxVal = Math.max(...cm.data.flat());
        const cmOption = {
          tooltip: {
            position: 'top',
            formatter: (p: any) => `真实: ${labels[p.data[1]]}<br/>预测: ${labels[p.data[0]]}<br/>数量: ${p.data[2]}`,
          },
          grid: { top: 40, bottom: 60, left: 60, right: 20 },
          xAxis: { type: 'category', data: labels, name: '预测类别', axisLabel: { fontSize: 11 } },
          yAxis: { type: 'category', data: labels, name: '真实类别', inverse: true, axisLabel: { fontSize: 11 } },
          visualMap: {
            min: 0, max: maxVal,
            calculable: true,
            orient: 'horizontal',
            left: 'center',
            bottom: 0,
            inRange: { color: ['#f0f9e8', '#41ab5d', '#005a32'] },
          },
          series: [{
            type: 'heatmap',
            data: heatData,
            label: { show: true, fontSize: 12, fontWeight: 'bold' as const },
            emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
          }],
        };
        return (
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={14}>
              <Card title="混淆矩阵" size="small" extra={<Tag color="blue">{`${n} 类故障`}</Tag>}>
                <ReactECharts option={cmOption} style={{ height: Math.max(280, n * 40 + 100) }} />
              </Card>
            </Col>
            {result.metrics?.classification_report && (
              <Col span={10}>
                <Card title="分类报告" size="small" style={{ height: '100%' }}>
                  <pre style={{ fontSize: 11, margin: 0, overflow: 'auto', maxHeight: 320, background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                    {result.metrics.classification_report}
                  </pre>
                </Card>
              </Col>
            )}
          </Row>
        );
      })()}

      {durationEntries.length > 0 && (
        <Row gutter={16} style={{ marginTop: 16 }}>
          <Col span={14}>
            <Card title={t('training.operatorDuration')} size="small">
              <ReactECharts option={barOption} style={{ height: 300 }} />
            </Card>
          </Col>
          <Col span={10}>
            <Card title={t('training.durationRatio')} size="small">
              <ReactECharts option={pieOption} style={{ height: 300 }} />
            </Card>
          </Col>
        </Row>
      )}

      {/* 快速回测 — 仅负荷预测场景展示，分类模型（光伏故障诊断）不需要时间序列回测 */}
      {onStartBacktest && !(result.metrics?.accuracy != null || result.metrics?.confusion_matrix) && (
        <Card size="small" title={t('training.quickBacktest')} style={{ marginTop: 16 }}>
          <Space align="center">
            <Text>{t('training.backtestDays')}</Text>
            <InputNumber
              min={1}
              max={30}
              value={quickBacktestDays}
              onChange={(v) => setQuickBacktestDays(typeof v === 'number' && v >= 1 ? v : 1)}
              style={{ width: 80 }}
              disabled={backtestLoading}
            />
            <Text type="secondary">{t('training.days')}</Text>
            {!backtestLoading ? (
              <Button type="primary" icon={<ExperimentOutlined />} onClick={() => onStartBacktest(quickBacktestDays)}>
                {t('training.startBacktest')}
              </Button>
            ) : (
              <Button danger onClick={() => onStopBacktest?.()}>
                {t('training.stopBacktest')}
              </Button>
            )}
          </Space>
        </Card>
      )}

      {/* @AI_GENERATED */}
      {backtestLoading && !(result.metrics?.accuracy != null || result.metrics?.confusion_matrix) && (
        <Card size="small" style={{ marginTop: 8 }}>
          <Space>
            <Spin size="small" />
            <Text>{t('training.backtestInProgress')}</Text>
          </Space>
        </Card>
      )}
      {/* @AI_GENERATED: end */}
    </div>
  );
};

export default TrainingResultDashboard;
// @AI_GENERATED: end
