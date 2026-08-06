// @AI_GENERATED
/**
 * AlertPanel.tsx — 精度退化告警列表。
 *
 * 用户可从每条 open（待处理）告警发起 RCA，或选择已有 RCA/恢复决策的告警，
 * 继续在精度运营主页面查看根因、仲裁和通道 A 状态。
 */
import React, { useEffect, useState } from 'react';
import { Alert as AntAlert, Badge, Button, Card, Empty, Select, Space, Spin, Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ExperimentOutlined, ReloadOutlined } from '@ant-design/icons';
import { useAccuracyOperationsStore } from '../../stores/accuracyOperationsStore';
import type { AccuracyAlert, AlertSeverity, AlertStatus, ModelForm } from '../../types/accuracy-operations';

interface AlertPanelProps {
  /** slot — 当前精度运营分区槽位。 */
  slot: string;
  /** onSelectAlert — 选择告警后由父级加载 RCA/恢复决策。 */
  onSelectAlert?: (alert: AccuracyAlert) => void;
  /** onTriggerRCA — 对 open 告警启动 RCA 状态机。 */
  onTriggerRCA?: (alert: AccuracyAlert) => Promise<void>;
  /** rcaLoading — RCA 请求中的统一禁用状态。 */
  rcaLoading?: boolean;
}

const STATUS_OPTIONS: Array<{ label: string; value: AlertStatus | '' }> = [
  { label: '全部状态', value: '' },
  { label: '待处理 (open)', value: 'open' },
  { label: 'RCA 进行中 (rca_running)', value: 'rca_running' },
  { label: '恢复中 (recovering)', value: 'recovering' },
  { label: '观察中 (observing)', value: 'observing' },
  { label: '已关闭 (closed)', value: 'closed' },
];

function getModelFormBadge(form: ModelForm): React.ReactNode {
  const map: Record<ModelForm, { color: string; text: string }> = {
    production: { color: 'green', text: '生产' },
    shadow: { color: 'blue', text: '影子' },
  };
  const config = map[form];
  return <Badge color={config.color} text={config.text} />;
}

function getSeverityTag(severity: AlertSeverity): React.ReactNode {
  return <Tag color={severity === 'critical' ? 'red' : 'orange'}>{severity === 'critical' ? '严重' : '警告'}</Tag>;
}

function getStatusTag(status: AlertStatus): React.ReactNode {
  const config: Record<AlertStatus, { color: string; label: string }> = {
    open: { color: 'blue', label: '待处理' },
    rca_running: { color: 'processing', label: 'RCA 中' },
    recovering: { color: 'orange', label: '恢复中' },
    observing: { color: 'purple', label: '观察中' },
    closed: { color: 'default', label: '已关闭' },
  };
  return <Tag color={config[status].color}>{config[status].label}</Tag>;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString('zh-CN', { hour12: false });
}

function displayBaselineMape(alert: AccuracyAlert): number {
  return alert.baseline_metric ?? alert.baseline_mape;
}

function displayCurrentMape(alert: AccuracyAlert): number {
  return alert.current_metric ?? alert.current_rolling_mape;
}

function isExperimentInjectAlert(alert: AccuracyAlert): boolean {
  const evidence = alert.recovery_evidence as { type?: string } | null;
  return evidence?.type === 'experiment_inject';
}

function buildColumns(
  onSelectAlert?: (alert: AccuracyAlert) => void,
  onTriggerRCA?: (alert: AccuracyAlert) => Promise<void>,
  rcaLoading = false,
): ColumnsType<AccuracyAlert> {
  return [
    { title: '告警 ID', dataIndex: 'alert_id', width: 135, render: (value: string) => <code style={{ fontSize: 12 }}>{value}</code> },
    { title: '形态', dataIndex: 'model_form', width: 80, render: getModelFormBadge },
    { title: '版本', dataIndex: 'version_tag', width: 130, render: (value: string) => <code>{value}</code> },
    {
      title: '基线 / 当前',
      key: 'metrics',
      width: 150,
      render: (_, record) => {
        const baseline = displayBaselineMape(record);
        const current = displayCurrentMape(record);
        const experiment = isExperimentInjectAlert(record);
        return (
          <Space direction="vertical" size={0}>
            <span>基线 {baseline.toFixed(2)}%</span>
            <span>当前 {current.toFixed(2)}%</span>
            {experiment ? (
              <span style={{ fontSize: 11, color: '#64748b' }}>
                AR 参考 {record.baseline_mape.toFixed(2)}%
              </span>
            ) : null}
          </Space>
        );
      },
    },
    { title: '退化幅度', dataIndex: 'degradation_pct', align: 'right' as const, width: 95, render: (value: number) => `${value.toFixed(2)}%` },
    {
      title: '趋势 / 冷却',
      key: 'trend',
      width: 150,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Tag color={record.degradation_trend === 'sudden' ? 'red' : record.degradation_trend === 'gradual' ? 'orange' : 'default'}>
            {record.degradation_trend === 'sudden' ? '骤升' : record.degradation_trend === 'gradual' ? '渐升' : '持续高位'}
          </Tag>
          <span style={{ fontSize: 11, color: '#64748b' }}>
            {record.cooldown_until ? `冷却至 ${formatDate(record.cooldown_until)}` : '无冷却期'}
          </span>
        </Space>
      ),
    },
    { title: '严重级别', dataIndex: 'severity', width: 90, render: getSeverityTag },
    { title: '状态', dataIndex: 'status', width: 90, render: getStatusTag },
    {
      title: 'RCA / 仲裁引用',
      key: 'references',
      width: 165,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <code style={{ fontSize: 11 }}>{record.rca_report_id ?? 'RCA 未生成'}</code>
          <code style={{ fontSize: 11 }}>{record.recovery_decision_id ?? '仲裁未生成'}</code>
        </Space>
      ),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 160, render: formatDate },
    {
      title: '操作',
      key: 'action',
      width: 160,
      fixed: 'right',
      render: (_, record) => (
        <Space size={2} wrap>
          {record.status === 'open' && onTriggerRCA ? (
            <Button
              size="small"
              type="primary"
              icon={<ExperimentOutlined />}
              loading={rcaLoading}
              onClick={(event) => { event.stopPropagation(); void onTriggerRCA(record); }}
            >
              {record.rca_report_id ? '重试 RCA' : '触发 RCA'}
            </Button>
          ) : null}
          {onSelectAlert ? (
            <Button size="small" onClick={(event) => { event.stopPropagation(); onSelectAlert(record); }}>
              {record.rca_report_id ? '查看 RCA' : '查看详情'}
            </Button>
          ) : null}
        </Space>
      ),
    },
  ];
}

const AlertPanel: React.FC<AlertPanelProps> = ({ slot, onSelectAlert, onTriggerRCA, rcaLoading = false }) => {
  const { alerts, loading, error, fetchAlerts } = useAccuracyOperationsStore();
  const [statusFilter, setStatusFilter] = useState<AlertStatus | ''>('');

  useEffect(() => { void fetchAlerts(slot); }, [slot, fetchAlerts]);

  const toolbar = (
    <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ fontSize: 13, color: '#666' }}>状态过滤：</span>
      <Select<AlertStatus | ''> value={statusFilter} onChange={setStatusFilter} style={{ width: 180 }} options={STATUS_OPTIONS} aria-label="按告警状态过滤" />
      <Button size="small" icon={<ReloadOutlined />} onClick={() => void fetchAlerts(slot, statusFilter || undefined)}>刷新</Button>
    </div>
  );

  if (loading.alerts) return <Card title="精度告警"><div style={{ textAlign: 'center', padding: '32px 0' }}><Spin tip="加载中…" /></div></Card>;
  if (error.alerts) return <Card title="精度告警"><AntAlert type="error" message="加载失败" description={error.alerts} action={<Button size="small" onClick={() => void fetchAlerts(slot)}>重试</Button>} /></Card>;

  const visibleAlerts = alerts.filter((alert) => (
    (alert.model_form === 'production' || alert.model_form === 'shadow')
    && (!statusFilter || alert.status === statusFilter)
  ));

  return (
    <Card title="精度告警" aria-label="精度告警面板">
      {toolbar}
      {visibleAlerts.length === 0 ? <Empty description="暂无精度退化告警" /> : (
        <Table<AccuracyAlert>
          rowKey="alert_id"
          size="small"
          columns={buildColumns(onSelectAlert, onTriggerRCA, rcaLoading)}
          dataSource={visibleAlerts}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          scroll={{ x: 1440 }}
          onRow={(record) => ({ onClick: () => onSelectAlert?.(record), style: { cursor: onSelectAlert ? 'pointer' : 'default' } })}
        />
      )}
    </Card>
  );
};

export default AlertPanel;
// @AI_GENERATED: end
