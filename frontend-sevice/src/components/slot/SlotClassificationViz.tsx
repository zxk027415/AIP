/**
 * SlotClassificationViz — 分类对照：混淆矩阵、逐日 Acc、跳转审核。
 */
import React, { useMemo } from 'react';
import { Button, Card, Col, Row, Space, Table, Tag, Typography } from 'antd';
import { AuditOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import type { DailyAccuracyRow } from '../../services/slotObservabilityApi';

const { Text } = Typography;

const LABEL_ORDER = [0, 1, 3] as const;
const LABEL_NAME: Record<number, string> = {
  0: '正常',
  1: '组串失配',
  3: '其他故障',
};

export type ClassPair = {
  goldLabel?: number | null;
  label?: number | null;
};

function pct(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function cellColor(count: number, max: number): string {
  if (!count || max <= 0) return 'transparent';
  const t = Math.min(1, count / max);
  return `rgba(22, 119, 255, ${0.12 + t * 0.55})`;
}

const SlotClassificationViz: React.FC<{
  slot: string;
  pairs: ClassPair[];
  byDay?: DailyAccuracyRow[];
  latestReviewId?: string | null;
}> = ({ slot, pairs, byDay = [], latestReviewId }) => {
  const matrix = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const gold of LABEL_ORDER) {
      for (const pred of LABEL_ORDER) {
        counts[`${gold}-${pred}`] = 0;
      }
    }
    for (const item of pairs) {
      if (item.goldLabel == null || item.label == null) continue;
      const key = `${item.goldLabel}-${item.label}`;
      if (counts[key] == null) counts[key] = 0;
      counts[key] += 1;
    }
    const max = Math.max(1, ...Object.values(counts));
    return { counts, max };
  }, [pairs]);

  const perClass = useMemo(() => {
    return LABEL_ORDER.map((cls) => {
      const tp = matrix.counts[`${cls}-${cls}`] || 0;
      const support = LABEL_ORDER.reduce((sum, pred) => sum + (matrix.counts[`${cls}-${pred}`] || 0), 0);
      const predicted = LABEL_ORDER.reduce((sum, gold) => sum + (matrix.counts[`${gold}-${cls}`] || 0), 0);
      const precision = predicted ? tp / predicted : null;
      const recall = support ? tp / support : null;
      return { cls, name: LABEL_NAME[cls], support, predicted, precision, recall };
    });
  }, [matrix]);

  const trendOption = useMemo(() => {
    if (!byDay.length) return null;
    return {
      animationDuration: 200,
      tooltip: { trigger: 'axis' },
      grid: { left: 48, right: 16, top: 28, bottom: 32 },
      xAxis: { type: 'category', data: byDay.map((row) => row.day) },
      yAxis: { type: 'value', min: 0, max: 1, axisLabel: { formatter: (value: number) => `${Math.round(value * 100)}%` } },
      series: [{
        name: '当日 Acc',
        type: 'line',
        data: byDay.map((row) => row.classifier_accuracy),
        showSymbol: true,
        lineStyle: { color: '#1677ff' },
        itemStyle: { color: '#1677ff' },
      }],
    };
  }, [byDay]);

  const reviewHref = latestReviewId
    ? `/iterative-labeling/review?review_id=${encodeURIComponent(latestReviewId)}&slot=${encodeURIComponent(slot)}`
    : `/iterative-labeling?tab=pv_label&slot=${encodeURIComponent(slot)}`;

  return (
    <Card
      size="small"
      title="分类可视化"
      extra={(
        <Space>
          <Link to={reviewHref}>
            <Button size="small" type="primary" icon={<AuditOutlined />}>
              {latestReviewId ? '打开当天审核' : '去审核工作台'}
            </Button>
          </Link>
          <Link to={`/iterative-labeling?tab=pv_label&slot=${encodeURIComponent(slot)}`}>
            <Button size="small">审核列表</Button>
          </Link>
        </Space>
      )}
    >
      <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
        混淆矩阵行是真值、列是预测。对角线是命中。逐日 Acc 是每天单独算；喂了几天后的「窗口累计」是把这些天的样本加在一起再除，不是把每天 Acc 再平均。
      </Text>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Text strong>混淆矩阵（当前日历窗口）</Text>
          <table style={{ width: '100%', marginTop: 8, borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                <th style={{ textAlign: 'left', padding: 6 }}>真值 \ 预测</th>
                {LABEL_ORDER.map((pred) => (
                  <th key={pred} style={{ padding: 6 }}>{LABEL_NAME[pred]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {LABEL_ORDER.map((gold) => (
                <tr key={gold}>
                  <td style={{ padding: 6 }}>{LABEL_NAME[gold]}</td>
                  {LABEL_ORDER.map((pred) => {
                    const count = matrix.counts[`${gold}-${pred}`] || 0;
                    return (
                      <td
                        key={pred}
                        style={{
                          padding: 8,
                          textAlign: 'center',
                          background: cellColor(count, matrix.max),
                          fontWeight: gold === pred ? 600 : 400,
                        }}
                      >
                        {count}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <Table
            style={{ marginTop: 12 }}
            size="small"
            pagination={false}
            rowKey="cls"
            dataSource={perClass}
            columns={[
              { title: '类别', dataIndex: 'name' },
              { title: '真值条数', dataIndex: 'support', width: 88 },
              { title: 'Recall', dataIndex: 'recall', width: 88, render: (value: number | null) => pct(value) },
              { title: 'Precision', dataIndex: 'precision', width: 96, render: (value: number | null) => pct(value) },
            ]}
          />
        </Col>
        <Col xs={24} lg={12}>
          <Text strong>逐日 Acc（每天单独算）</Text>
          {trendOption ? (
            <ReactECharts option={trendOption} style={{ height: 200, marginTop: 8 }} />
          ) : (
            <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>还没有按日精度。推进下一天后会出现。</Text>
          )}
          <Table
            style={{ marginTop: 8 }}
            size="small"
            pagination={false}
            rowKey={(row) => String(row.day || row.review_id)}
            dataSource={byDay}
            locale={{ emptyText: '尚无逐日记录' }}
            columns={[
              { title: '业务日', dataIndex: 'day', width: 110 },
              {
                title: '当日 Acc',
                dataIndex: 'classifier_accuracy',
                width: 96,
                render: (value: number | null) => pct(value),
              },
              { title: '样本', dataIndex: 'counted_units', width: 72 },
              {
                title: '审核',
                key: 'review',
                render: (_: unknown, row: DailyAccuracyRow) => (
                  row.review_id ? (
                    <Link to={`/iterative-labeling/review?review_id=${encodeURIComponent(row.review_id)}&slot=${encodeURIComponent(slot)}`}>
                      打开
                    </Link>
                  ) : '—'
                ),
              },
            ]}
          />
        </Col>
      </Row>
      {latestReviewId ? <Tag style={{ marginTop: 8 }}>最近会话 {latestReviewId}</Tag> : null}
    </Card>
  );
};

export default SlotClassificationViz;
