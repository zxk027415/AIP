// @AI_GENERATED
/**
 * MonitoringPanel.tsx — 精度监控面板。
 *
 * 展示 production/shadow/prelaunch 的版本级 MAPE、WMAPE、真值覆盖率和有效周期数；
 * WMAPE 是退化告警优先比较的指标，缺失时后端才回退 MAPE。
 */
import React, { useEffect } from 'react';
import { Alert, Badge, Button, Card, Empty, Spin, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined } from '@ant-design/icons';
import { useAccuracyOperationsStore } from '../../stores/accuracyOperationsStore';
import type { MonitoringMetrics } from '../../types/accuracy-operations';

interface MonitoringPanelProps {
  /** slot — 当前精度运营分区场景。 */
  slot: string;
}

interface MetricsRow extends MonitoringMetrics {
  /** model_form — 展示用模型形态。 */
  model_form: 'production' | 'shadow' | 'prelaunch';
  /** _rowKey — 同一 workflow 多版本时仍保持唯一。 */
  _rowKey: string;
}

function getFormBadge(form: MetricsRow['model_form']): React.ReactNode {
  const map: Record<MetricsRow['model_form'], { color: string; text: string }> = {
    production: { color: 'green', text: '生产' },
    shadow: { color: 'blue', text: '影子' },
    prelaunch: { color: 'orange', text: '预上线' },
  };
  return <Badge color={map[form].color} text={map[form].text} />;
}

function formatMetric(value: number | null | undefined, decimals = 4): string {
  return value === null || value === undefined ? '—' : value.toFixed(decimals);
}

function formatRate(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(1)}%`;
}

const columns: ColumnsType<MetricsRow> = [
  { title: '版本', dataIndex: 'version_tag', render: (value: string) => <code>{value}</code> },
  { title: '形态', dataIndex: 'model_form', width: 80, render: getFormBadge },
  { title: '滚动 MAPE', dataIndex: 'rolling_mape', align: 'right' as const, render: (value: number | null) => formatMetric(value) },
  {
    title: '滚动 WMAPE',
    dataIndex: 'rolling_wmape',
    align: 'right' as const,
    render: (value: number | null | undefined) => formatMetric(value),
  },
  { title: '滚动 MAE', dataIndex: 'rolling_mae', align: 'right' as const, render: (value: number | null) => formatMetric(value) },
  { title: '有效周期', dataIndex: 'valid_cycle_count', align: 'right' as const, render: (value: number | null) => value ?? '—' },
  {
    title: '真值覆盖率',
    dataIndex: 'coverage_rate',
    align: 'right' as const,
    render: (value: number | null | undefined) => formatRate(value),
  },
  {
    title: '状态',
    dataIndex: 'status',
    width: 100,
    render: (value: string | null) => {
      if (!value) return '—';
      const color: Record<string, string> = { active: 'green', insufficient_data: 'default', degraded: 'red', warning: 'orange' };
      return <Tag color={color[value] ?? 'default'}>{value}</Tag>;
    },
  },
];

const MonitoringPanel: React.FC<MonitoringPanelProps> = ({ slot }) => {
  const { monitoringSnapshot, loading, error, fetchMonitoringSnapshot } = useAccuracyOperationsStore();

  useEffect(() => { void fetchMonitoringSnapshot(slot); }, [slot, fetchMonitoringSnapshot]);

  if (loading.snapshot) return <Card title="精度监控"><div style={{ textAlign: 'center', padding: '32px 0' }}><Spin tip="加载中…" /></div></Card>;
  if (error.snapshot) return <Card title="精度监控"><Alert type="error" message="加载失败" description={error.snapshot} action={<Button size="small" icon={<ReloadOutlined />} onClick={() => void fetchMonitoringSnapshot(slot)}>重试</Button>} /></Card>;
  if (!monitoringSnapshot) return <Card title="精度监控"><Empty description="暂无监控快照" /></Card>;

  const productionRows: MetricsRow[] = monitoringSnapshot.production ? [{ ...monitoringSnapshot.production, model_form: 'production', _rowKey: `production:${monitoringSnapshot.production.workflow_id}:${monitoringSnapshot.production.version_tag}` }] : [];
  const shadowRows: MetricsRow[] = monitoringSnapshot.shadows.map((metrics) => ({ ...metrics, model_form: 'shadow', _rowKey: `shadow:${metrics.workflow_id}:${metrics.version_tag}` }));
  const prelaunchRows: MetricsRow[] = monitoringSnapshot.prelaunches.map((metrics) => ({ ...metrics, model_form: 'prelaunch', _rowKey: `prelaunch:${metrics.workflow_id}:${metrics.version_tag}` }));

  const renderSection = (title: string, rows: MetricsRow[]) => rows.length ? (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontWeight: 600, fontSize: 13, color: '#666', marginBottom: 8 }}>{title}</div>
      <Table<MetricsRow> rowKey="_rowKey" columns={columns} dataSource={rows} pagination={false} size="small" scroll={{ x: 820 }} />
    </div>
  ) : null;

  if (!productionRows.length && !shadowRows.length && !prelaunchRows.length) return <Card title="精度监控"><Empty description="该场景尚无已部署模型的指标" /></Card>;

  return (
    <Card title="精度监控" extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => void fetchMonitoringSnapshot(slot)}>刷新</Button>}>
      {renderSection('生产模型', productionRows)}
      {renderSection('影子模型', shadowRows)}
      {renderSection('预上线模型', prelaunchRows)}
    </Card>
  );
};

export default MonitoringPanel;
// @AI_GENERATED: end
