// @AI_GENERATED
import React, { useMemo } from 'react';
import { Alert, Col, Descriptions, Empty, Row, Statistic, Tag, Typography } from 'antd';
import type { EChartsOption } from 'echarts';
import ReactECharts from 'echarts-for-react';
import PvFaultClassificationMetrics, { type PvClassificationMetrics } from './PvFaultClassificationMetrics';
import './pvRetrainResultMetrics.css';

const { Text } = Typography;

type ModelingPath = 'legacy_day' | 'seq_annotation';

interface SeqAccuracyMetrics extends PvClassificationMetrics {
  point_macro_f1?: number | null;
  binary_f1?: number | null;
  point_accuracy?: number | null;
  fault_mask_iou?: number | null;
  day_majority_macro_f1?: number | null;
  postprocessing_changed_points?: number | null;
  raw_point_macro_f1?: number | null;
  raw_binary_f1?: number | null;
  raw_point_accuracy?: number | null;
  raw_fault_mask_iou?: number | null;
  n_test_sequences?: number | null;
  n_test_points?: number | null;
}

interface Props {
  modelingPath: ModelingPath;
  trainSummary?: Record<string, any> | null;
  labelNames?: Record<string, string>;
  emptyText: string;
}

const asPercent = (value?: number | null) => (
  value === null || value === undefined || Number.isNaN(value) ? undefined : value * 100
);

const PvRetrainResultMetrics: React.FC<Props> = ({
  modelingPath,
  trainSummary,
  labelNames = {},
  emptyText,
}) => {
  const metrics = trainSummary?.accuracy_record as SeqAccuracyMetrics | undefined;
  const comparisonOption = useMemo<EChartsOption | null>(() => {
    if (!metrics || modelingPath !== 'seq_annotation') return null;
    const categories = ['Point Macro-F1', 'Binary F1', 'Point Accuracy', 'Fault-mask IoU'];
    const rawValues = [
      metrics.raw_point_macro_f1,
      metrics.raw_binary_f1,
      metrics.raw_point_accuracy,
      metrics.raw_fault_mask_iou,
    ];
    const finalValues = [
      metrics.point_macro_f1,
      metrics.binary_f1,
      metrics.point_accuracy,
      metrics.fault_mask_iou,
    ];
    return {
      animationDuration: 200,
      tooltip: {
        trigger: 'axis',
        valueFormatter: (value: any) => `${(Number(value) * 100).toFixed(2)}%`,
      },
      legend: { data: ['原始输出', '生产后处理'] },
      grid: { left: 54, right: 20, top: 42, bottom: 58 },
      xAxis: { type: 'category', data: categories, axisLabel: { interval: 0, rotate: 12 } },
      yAxis: {
        type: 'value',
        min: 0,
        max: 1,
        axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%` },
      },
      series: [
        { name: '原始输出', type: 'bar', data: rawValues, itemStyle: { color: '#64748b' }, barMaxWidth: 30 },
        { name: '生产后处理', type: 'bar', data: finalValues, itemStyle: { color: '#f97316' }, barMaxWidth: 30 },
      ],
    };
  }, [metrics, modelingPath]);

  if (!trainSummary || !metrics) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={emptyText} />;
  }

  if (modelingPath === 'legacy_day') {
    return <PvFaultClassificationMetrics metrics={metrics} labelNames={labelNames} emptyText={emptyText} />;
  }

  const metricItems = [
    ['Point Macro-F1', metrics.point_macro_f1, '多类别逐点识别的宏平均 F1'],
    ['Binary F1', metrics.binary_f1, '正常 / 故障二分类逐点 F1'],
    ['Point Accuracy', metrics.point_accuracy, '有效标注点的逐点准确率'],
    ['Fault-mask IoU', metrics.fault_mask_iou, '故障时间掩码的交并比'],
    ['Day-majority Macro-F1', metrics.day_majority_macro_f1, '逐点结果投影到设备日后的 Macro-F1'],
  ] as const;
  const sequenceContract = (trainSummary.sequence_contract ?? {}) as Record<string, any>;
  const labels = (trainSummary.label_space_snapshot?.labels ?? []) as Array<string | number>;

  return (
    <div className="pv-retrain-result pv-retrain-result--seq">
      <Alert
        type="info"
        showIcon
        message="点级路径按全天 288 点序列口径评估"
        description="以下指标来自设备隔离测试集。Point 指标、故障掩码 IoU 与天级投影指标属于不同粒度，不与传统天级模型的 Macro-F1 直接横向比较。"
      />

      <Row gutter={[12, 12]} className="pv-retrain-result__metric-grid">
        {metricItems.map(([label, value, hint]) => (
          <Col xs={12} md={8} xl={metricItems.length === 5 ? 4 : 6} key={label}>
            <div className="pv-metric-number pv-retrain-result__metric">
              <Statistic title={label} value={asPercent(value)} precision={1} suffix="%" />
              <Text type="secondary">{hint}</Text>
            </div>
          </Col>
        ))}
      </Row>

      <div className="pv-retrain-result__evidence">
        <Descriptions size="small" column={{ xs: 1, sm: 2, lg: 4 }}>
          <Descriptions.Item label="训练序列">{metrics.n_samples ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="测试设备日">{metrics.n_test_sequences ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="测试有效点">{metrics.n_test_points ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="后处理改写点">{metrics.postprocessing_changed_points ?? '—'}</Descriptions.Item>
        </Descriptions>
      </div>

      <Row gutter={[16, 16]} className="pv-retrain-result__details">
        <Col xs={24} xl={15}>
          <div className="pv-metric-chart-title">原始输出与生产后处理对照</div>
          {comparisonOption
            ? <ReactECharts option={comparisonOption} style={{ height: 320 }} />
            : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无后处理对照指标" />}
        </Col>
        <Col xs={24} xl={9}>
          <div className="pv-metric-chart-title">序列生产契约</div>
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="模型架构">{sequenceContract.model_name ?? '—'}</Descriptions.Item>
            <Descriptions.Item label="序列长度">{sequenceContract.seq_len ?? '—'} 点</Descriptions.Item>
            <Descriptions.Item label="采样间隔">{sequenceContract.sampling_interval_minutes ?? '—'} 分钟</Descriptions.Item>
            <Descriptions.Item label="全天工件">
              <Tag color={sequenceContract.trained_full_day ? 'success' : 'error'}>
                {sequenceContract.trained_full_day ? '已验证' : '未验证'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="输入通道">
              {(sequenceContract.channels ?? []).map((channel: string) => <Tag key={channel}>{channel}</Tag>)}
            </Descriptions.Item>
            <Descriptions.Item label="标签空间">
              {labels.length ? labels.map(label => (
                <Tag key={String(label)}>{labelNames[String(label)] ?? `类别 ${label}`}</Tag>
              )) : '—'}
            </Descriptions.Item>
          </Descriptions>
        </Col>
      </Row>

      <Alert
        type="warning"
        showIcon
        className="pv-retrain-result__schema-note"
        message="该点级训练摘要尚未持久化逐类别混淆矩阵"
        description="当前可展示逐点聚合、二元故障、掩码 IoU 和后处理证据；类别级 Precision / Recall / F1 需训练器后续补充 point-level confusion_matrix 后才能生成。"
      />
    </div>
  );
};

export default PvRetrainResultMetrics;
// @AI_GENERATED: end
