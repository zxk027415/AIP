/**
 * SlotAccuracyMetricsCard — 精度运营主指标：Acc / 样本 / Macro F1 / P / R / 命中 / 纠错。
 */
import React from 'react';
import { Card, Col, Row, Statistic, Tag, Typography } from 'antd';

const { Text } = Typography;

export type AccuracyMetrics = {
  day?: string | null;
  countedUnits?: number;
  classifierAccuracy?: number | null;
  macroF1?: number | null;
  // @AI_GENERATED: balanced accuracy（类不均衡下的核心指标，TSC 精度运营要求展示）。
  balancedAccuracy?: number | null;
  // @AI_GENERATED: end
  precision?: number | null;
  recall?: number | null;
  confirmCount?: number;
  correctCount?: number;
  note?: string;
};

function pct(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function num(value?: number | null, digits = 3): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toFixed(digits);
}

const SlotAccuracyMetricsCard: React.FC<{
  metrics: AccuracyMetrics | null;
  extra?: React.ReactNode;
  latestDayAcc?: number | null;
  cumulativeAcc?: number | null;
  cumulativeDays?: number;
}> = ({ metrics, extra, latestDayAcc, cumulativeAcc, cumulativeDays }) => {
  return (
    <Card
      size="small"
      title={
        <span>
          精度对照
          {metrics?.day ? <Tag style={{ marginLeft: 8 }}>{metrics.day}</Tag> : null}
        </span>
      }
      extra={extra}
    >
      <Row gutter={[16, 16]}>
        <Col xs={12} md={6} lg={4}>
          <Statistic title="窗口累计 Acc" value={pct(metrics?.classifierAccuracy)} />
        </Col>
        <Col xs={12} md={6} lg={4}>
          <Statistic title="最近一天 Acc" value={pct(latestDayAcc)} />
        </Col>
        <Col xs={12} md={6} lg={4}>
          <Statistic title={cumulativeDays ? `已喂 ${cumulativeDays} 日累计` : '已喂累计 Acc'} value={pct(cumulativeAcc)} />
        </Col>
        <Col xs={12} md={6} lg={3}>
          <Statistic title="对照样本" value={metrics?.countedUnits ?? 0} />
        </Col>
        <Col xs={12} md={6} lg={3}>
          <Statistic title="Macro F1" value={num(metrics?.macroF1)} />
        </Col>
        {/* @AI_GENERATED: Balanced Accuracy 展示（缺失时显示占位）。 */}
        <Col xs={12} md={6} lg={3}>
          <Statistic title="Balanced Acc" value={pct(metrics?.balancedAccuracy)} />
        </Col>
        {/* @AI_GENERATED: end */}
        <Col xs={12} md={6} lg={3}>
          <Statistic title="命中 / 纠错" value={`${metrics?.confirmCount ?? 0} / ${metrics?.correctCount ?? 0}`} />
        </Col>
      </Row>
      <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
        {metrics?.note
          || '窗口累计=日历范围内所有点加总再除。最近一天=last fed day。已喂累计=所有已推进日按样本加权，不是把每天 Acc 再平均。7 天喂完后，已喂累计就是这 7 天的加权 Acc。'}
      </Text>
    </Card>
  );
};

export default SlotAccuracyMetricsCard;
