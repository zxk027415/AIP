// @AI_GENERATED
import React from 'react';
import { Card, Row, Col, Statistic, Table, Space, Typography, Tag, Divider, Collapse, Button, Alert } from 'antd';
import { AuditOutlined } from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useTranslation } from 'react-i18next';
import type { PredictionPipelineResult } from '../../types/pipeline';
import { td } from '../../utils/dataTranslation';

interface PredictionResultDashboardProps {
  result: PredictionPipelineResult;
  onExport?: () => void;
  onReviewLabeling?: () => void;
  reviewLabelingLoading?: boolean;
}

// 故障类型中文名映射
const FAULT_LABELS: Record<string, string> = {
  '0': '正常', '1': '组串遮挡', '4': '直流侧异常',
  '7': '汇流箱告警', '8': '汇流箱故障', '11': '组串开路',
  '12': '组串短路', '16': '其他故障',
};

const PredictionResultDashboard: React.FC<PredictionResultDashboardProps> = ({ result, onExport, onReviewLabeling, reviewLabelingLoading }) => {
  const { t } = useTranslation();

  // 算子耗时
  const durationEntries = Object.entries(result.nodeDurations || {});
  const barOption = durationEntries.length > 0 ? {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 120, right: 30, top: 10, bottom: 30 },
    xAxis: { type: 'value' as const, name: '秒' },
    yAxis: { type: 'category' as const, data: durationEntries.map(([k]) => td(k)), inverse: true },
    series: [{ type: 'bar', data: durationEntries.map(([, v]) => Number(v).toFixed(2)), itemStyle: { color: '#52c41a' } }],
  } : null;

  // 故障诊断模式
  const hasFaultPredictions = Array.isArray(result.faultPredictions) && result.faultPredictions.length > 0;
  const hasTimeSeries = Array.isArray(result.forecastValues) && result.forecastValues.length > 0;
  const hasMetrics = result.metrics && (result.metrics.accuracy != null || result.metrics.f1 != null);
  const hasFaultTimeseries = result.faultTimeseries && result.faultTimeseries.timestamps?.length > 0;

  // 故障分布统计
  const faultDistribution = React.useMemo(() => {
    if (!hasFaultPredictions) return null;
    const counts: Record<string, number> = {};
    result.faultPredictions!.forEach(row => {
      const val = String(row.predictions ?? row.predict_label ?? row.predicted_label ?? '未知');
      counts[val] = (counts[val] || 0) + 1;
    });
    return Object.entries(counts)
      .map(([k, v]) => ({ label: k, name: FAULT_LABELS[k] || `故障 ${k}`, count: v }))
      .sort((a, b) => b.count - a.count);
  }, [result.faultPredictions, hasFaultPredictions]);

  const pieOption = faultDistribution ? {
    tooltip: { trigger: 'item', formatter: '{b}: {c} 次 ({d}%)' },
    legend: { orient: 'vertical', right: 10, top: 'center' },
    series: [{
      type: 'pie', radius: ['40%', '70%'],
      center: ['40%', '50%'],
      data: faultDistribution.map(d => ({
        name: `${d.name}(${d.label})`,
        value: d.count,
        itemStyle: d.label === '7' || d.label === '0' ? { color: '#52c41a' } : undefined,
      })),
      label: { show: true, formatter: '{b}\n{d}%', fontSize: 11 },
      emphasis: { itemStyle: { shadowBlur: 10, shadowColor: 'rgba(0,0,0,0.5)' } },
    }],
  } : null;

  // 故障时序曲线
  const timeseriesOption = React.useMemo(() => {
    if (!hasFaultTimeseries) return null;
    const ts = result.faultTimeseries!;
    const seriesEntries = Object.entries(ts.series);
    const seriesNames: Record<string, string> = { value: '实测电流', i_cal: '理论电流', voltage: '实测电流', current: '理论电流' };
    return {
      title: {
        text: `设备 ${ts.device_id.slice(0, 10)}...${ts.branch_id ? ' | 支路 ' + ts.branch_id : ''} | ${ts.time_window.slice(0, 10)} | 故障: ${FAULT_LABELS[ts.fault_type] || '类型' + ts.fault_type}`,
        textStyle: { fontSize: 13 },
        left: 'center',
      },
      tooltip: { trigger: 'axis' as const },
      legend: { data: seriesEntries.map(([k]) => seriesNames[k] || k), bottom: 0 },
      grid: { left: 60, right: 30, top: 50, bottom: 50 },
      xAxis: {
        type: 'category' as const,
        data: ts.timestamps.map(t => t.includes(' ') ? t.split(' ')[1]?.slice(0, 5) : t.slice(11, 16)),
        axisLabel: { rotate: 45, fontSize: 10 },
      },
      yAxis: seriesEntries.length > 1 ? [
        { type: 'value' as const, name: seriesNames[seriesEntries[0][0]] || seriesEntries[0][0], axisLabel: { fontSize: 10 } },
        { type: 'value' as const, name: seriesNames[seriesEntries[1][0]] || seriesEntries[1][0], axisLabel: { fontSize: 10 } },
      ] : [{ type: 'value' as const }],
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 20, bottom: 25 }],
      series: seriesEntries.map(([k, data], idx) => ({
        name: seriesNames[k] || k,
        type: 'line',
        data,
        smooth: true,
        yAxisIndex: idx < 2 ? idx : 0,
        lineStyle: { width: 2 },
        itemStyle: { color: idx === 0 ? '#1890ff' : '#fa8c16' },
      })),
    };
  }, [result.faultTimeseries, hasFaultTimeseries]);

  return (
    <div style={{ padding: 16 }}>
      {/* 人工审查打标入口（仅故障诊断预测且提供回调时显示） */}
      {hasFaultPredictions && onReviewLabeling && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="预测已完成，可进入人工审查打标"
          description="对预测结果逐单元人工核对/纠正/打新标签，确认后将回贴到原始时序，形成可再训练的新真值数据集。"
          action={
            <Button
              type="primary"
              icon={<AuditOutlined />}
              loading={reviewLabelingLoading}
              onClick={onReviewLabeling}
            >
              人工审查打标
            </Button>
          }
        />
      )}

      {/* 顶部统计卡 */}
      <Row gutter={[16, 16]}>
        <Col span={6}><Card size="small"><Statistic title="总耗时" value={result.totalDuration?.toFixed(2)} suffix="秒" /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="模型 ID" value={result.modelId ? result.modelId.slice(0, 18) + '...' : '-'} /></Card></Col>
        <Col span={6}><Card size="small"><Statistic title="预测点数" value={hasFaultPredictions ? result.faultPredictions!.length : result.forecastValues?.length ?? 0} suffix="条" /></Card></Col>
        {faultDistribution && (
          <Col span={6}><Card size="small"><Statistic title="检出故障类别" value={faultDistribution.filter(d => d.label !== '7' && d.label !== '0').length} suffix="类" valueStyle={{ color: '#fa8c16' }} /></Card></Col>
        )}
      </Row>

      {/* 模型质量参考（来自训练时验证集评估，非预测数据实时评估） */}
      {hasMetrics && (
        <>
          <Divider orientation="left" style={{ marginTop: 24, marginBottom: 12 }}>模型质量参考（训练验证集 20%）</Divider>
          <Row gutter={[16, 16]}>
            {result.metrics!.accuracy != null && (
              <Col span={6}><Card size="small"><Statistic title="Accuracy（准确率）" value={(result.metrics!.accuracy * 100).toFixed(2)} suffix="%" valueStyle={{ color: '#52c41a' }} /></Card></Col>
            )}
            {result.metrics!.precision != null && (
              <Col span={6}><Card size="small"><Statistic title="Precision（精确率）" value={(result.metrics!.precision * 100).toFixed(2)} suffix="%" /></Card></Col>
            )}
            {result.metrics!.recall != null && (
              <Col span={6}><Card size="small"><Statistic title="Recall（召回率）" value={(result.metrics!.recall * 100).toFixed(2)} suffix="%" /></Card></Col>
            )}
            {result.metrics!.f1 != null && (
              <Col span={6}><Card size="small"><Statistic title="F1 Score（macro）" value={(result.metrics!.f1 * 100).toFixed(2)} suffix="%" valueStyle={{ color: '#1890ff' }} /></Card></Col>
            )}
          </Row>
          <Typography.Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
            以上指标为该模型在训练数据 20% 验证集上的表现，仅供参考。预测数据无真实标签，无法计算实时精度。
          </Typography.Text>
        </>
      )}

      {/* 故障时序曲线 */}
      {timeseriesOption && (
        <>
          <Divider orientation="left" style={{ marginTop: 24, marginBottom: 12 }}>故障设备时序曲线（单日波形）</Divider>
          <Card size="small">
            <ReactECharts option={timeseriesOption} style={{ height: 320 }} />
          </Card>
        </>
      )}

      {/* 故障分布饼图 */}
      {pieOption && faultDistribution && (
        <>
          <Divider orientation="left" style={{ marginTop: 24, marginBottom: 12 }}>故障类型分布</Divider>
          <Row gutter={16}>
            <Col span={14}>
              <Card title="故障分布" size="small">
                <ReactECharts option={pieOption} style={{ height: 320 }} />
              </Card>
            </Col>
            <Col span={10}>
              <Card title="故障统计明细" size="small">
                <Table
                  size="small"
                  pagination={false}
                  scroll={{ y: 280 }}
                  dataSource={faultDistribution.map((d, i) => ({ key: i, ...d }))}
                  columns={[
                    { title: '故障类型', dataIndex: 'name', render: (v: string, r: any) => (
                      <Space>
                        <Tag color={r.label === '7' || r.label === '0' ? 'green' : 'red'}>{r.label}</Tag>
                        <span>{v}</span>
                      </Space>
                    )},
                    { title: '次数', dataIndex: 'count', width: 70, align: 'right' as const,
                      render: (v: number) => <Typography.Text strong>{v}</Typography.Text> },
                  ]}
                />
              </Card>
            </Col>
          </Row>
        </>
      )}

      {/* 负荷预测模式：时序折线图 */}
      {hasTimeSeries && (
        <Card title="预测曲线" size="small" style={{ marginTop: 16 }}>
          <ReactECharts option={{
            tooltip: { trigger: 'axis' as const },
            xAxis: { type: 'category' as const, data: result.forecastTimestamps, axisLabel: { rotate: 45 } },
            yAxis: { type: 'value' as const },
            dataZoom: [{ type: 'inside' }, { type: 'slider' }],
            series: [{ type: 'line', data: result.forecastValues, smooth: true, itemStyle: { color: '#1890ff' }, areaStyle: { opacity: 0.1 } }],
            grid: { left: 60, right: 30, bottom: 80, top: 30 },
          }} style={{ height: 300 }} />
        </Card>
      )}

      {/* 算子耗时 */}
      {barOption && (
        <Collapse
          items={[{
            key: 'durations',
            label: '算子耗时详情',
            children: <ReactECharts option={barOption} style={{ height: 280 }} />,
          }]}
          style={{ marginTop: 16 }}
        />
      )}
    </div>
  );
};

export default PredictionResultDashboard;
// @AI_GENERATED: end
