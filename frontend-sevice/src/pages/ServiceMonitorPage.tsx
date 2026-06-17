// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useCallback, useRef } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Select, Radio, Row, Col, Statistic, Table, Tag, Badge, Tabs,
  Button, Modal, Form, InputNumber, Switch, Space, message, Popconfirm,
} from 'antd';
import {
  DashboardOutlined, ThunderboltOutlined, WarningOutlined, CheckCircleOutlined,
  PlusOutlined, DeleteOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import { useSearchParams } from 'react-router-dom';
import type {
  DeployedService, ServiceMetricPoint, AlertRule, AlertHistoryItem, AccessLog,
} from '../types/deployment';
import { SEVERITY_CONFIG } from '../types/deployment';
import { deploymentApi } from '../services/deploymentApi';
import { td } from '../utils/dataTranslation';

const ServiceMonitorPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [searchParams] = useSearchParams();
  const [services, setServices] = useState<DeployedService[]>([]);
  const [selectedServiceId, setSelectedServiceId] = useState<string>('');
  const [timeRange, setTimeRange] = useState('1h');
  const [metrics, setMetrics] = useState<ServiceMetricPoint[]>([]);
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [alertHistory, setAlertHistory] = useState<AlertHistoryItem[]>([]);
  const [logs, setLogs] = useState<AccessLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [ruleModalOpen, setRuleModalOpen] = useState(false);
  const [ruleForm] = Form.useForm();
  const chartRef = useRef<ReactECharts>(null);

  // Load services list
  useEffect(() => {
    deploymentApi.listServices().then(data => {
      setServices(data);
      const paramSvc = searchParams.get('service');
      if (paramSvc && data.find(s => s.id === paramSvc)) {
        setSelectedServiceId(paramSvc);
      } else if (data.length > 0) {
        setSelectedServiceId(data[0].id);
      }
    }).catch(() => {});
  }, [searchParams]);

  const loadMetrics = useCallback(async () => {
    if (!selectedServiceId) return;
    setLoading(true);
    try {
      const [m, rules, history, logRes] = await Promise.all([
        deploymentApi.getServiceMetrics(selectedServiceId, timeRange),
        deploymentApi.listAlertRules(),
        deploymentApi.listAlertHistory(selectedServiceId),
        deploymentApi.getServiceLogs(selectedServiceId, 1, 30),
      ]);
      setMetrics(m);
      setAlertRules(rules);
      setAlertHistory(history);
      setLogs(logRes.items);
    } catch { message.error(t('serviceMonitor.loadFailed')); }
    setLoading(false);
  }, [selectedServiceId, timeRange]);

  useEffect(() => { loadMetrics(); }, [loadMetrics]);

  // Current stats from latest metric point
  const latest = metrics.length > 0 ? metrics[metrics.length - 1] : null;
  const timestamps = metrics.map(m => {
    const d = new Date(m.timestamp);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  });

  const qpsOption = {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, name: 'QPS' },
    series: [{ name: 'QPS', type: 'line', data: metrics.map(m => m.qps), smooth: true, areaStyle: { opacity: 0.15 }, lineStyle: { width: 2 } }],
    grid: { top: 30, bottom: 30, left: 50, right: 20 },
  };

  const latencyOption = {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['P50', 'P90', 'P95', 'P99'], top: 0, textStyle: { fontSize: 10 } },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, name: 'ms' },
    series: [
      { name: 'P50', type: 'line', data: metrics.map(m => m.latency_p50), smooth: true, lineStyle: { width: 1.5 } },
      { name: 'P90', type: 'line', data: metrics.map(m => m.latency_p90), smooth: true, lineStyle: { width: 1.5 } },
      { name: 'P95', type: 'line', data: metrics.map(m => m.latency_p95), smooth: true, lineStyle: { width: 1.5 } },
      { name: 'P99', type: 'line', data: metrics.map(m => m.latency_p99), smooth: true, lineStyle: { width: 2, type: 'dashed' as const } },
    ],
    grid: { top: 30, bottom: 30, left: 50, right: 20 },
  };

  const errorOption = {
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, name: '%', axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(1)}%` } },
    series: [{ name: t('serviceMonitor.errorRate'), type: 'line', data: metrics.map(m => m.error_rate), smooth: true, areaStyle: { opacity: 0.2, color: '#ff4d4f' }, lineStyle: { width: 2, color: '#ff4d4f' }, itemStyle: { color: '#ff4d4f' } }],
    grid: { top: 30, bottom: 30, left: 60, right: 20 },
  };

  const resourceOption = {
    tooltip: { trigger: 'axis' as const },
    legend: { data: ['CPU', t('serviceMonitor.memoryUsageLabel'), 'GPU'], top: 0, textStyle: { fontSize: 10 } },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { fontSize: 10 } },
    yAxis: { type: 'value' as const, name: '%', max: 100 },
    series: [
      { name: 'CPU', type: 'line', data: metrics.map(m => m.cpu_usage), smooth: true, lineStyle: { width: 1.5 } },
      { name: t('serviceMonitor.memoryUsageLabel'), type: 'line', data: metrics.map(m => m.memory_usage), smooth: true, lineStyle: { width: 1.5 } },
      { name: 'GPU', type: 'line', data: metrics.map(m => m.gpu_usage), smooth: true, lineStyle: { width: 1.5 } },
    ],
    grid: { top: 30, bottom: 30, left: 50, right: 20 },
  };

  const handleCreateRule = async () => {
    try {
      const vals = ruleForm.getFieldsValue();
      await deploymentApi.createAlertRule({
        service_id: selectedServiceId,
        metric_name: vals.metric_name,
        operator: vals.operator || 'gt',
        threshold: vals.threshold,
        severity: vals.severity || 'warning',
        enabled: vals.enabled !== false,
      });
      message.success(t('serviceMonitor.ruleCreated'));
      setRuleModalOpen(false);
      ruleForm.resetFields();
      loadMetrics();
    } catch { message.error(t('serviceMonitor.ruleCreateFailed')); }
  };

  const handleDeleteRule = async (id: string) => {
    try {
      await deploymentApi.deleteAlertRule(id);
      message.success(t('serviceMonitor.ruleDeleted'));
      loadMetrics();
    } catch { message.error(t('serviceMonitor.ruleDeleteFailed')); }
  };

  const handleToggleRule = async (rule: AlertRule) => {
    try {
      await deploymentApi.updateAlertRule(rule.id, { enabled: !rule.enabled });
      loadMetrics();
    } catch { message.error(t('serviceMonitor.ruleUpdateFailed')); }
  };

  return (
    <div style={{ padding: 24 }}>
      <Card style={{ marginBottom: 16 }}>
        <Space size="large" wrap>
          <span>{t('serviceMonitor.service')}</span>
          <Select value={selectedServiceId} onChange={setSelectedServiceId} style={{ width: 260 }}
            options={services.map(s => ({ value: s.id, label: `${td(s.name)} (${s.id})` }))} />
          <span>{t('serviceMonitor.timeRange')}</span>
          <Radio.Group value={timeRange} onChange={e => setTimeRange(e.target.value)}>
            <Radio.Button value="1h">{t('serviceMonitor.hour1')}</Radio.Button>
            <Radio.Button value="6h">{t('serviceMonitor.hour6')}</Radio.Button>
            <Radio.Button value="24h">{t('serviceMonitor.hour24')}</Radio.Button>
            <Radio.Button value="7d">{t('serviceMonitor.day7')}</Radio.Button>
          </Radio.Group>
          <Button onClick={loadMetrics} loading={loading}>{t('serviceMonitor.refreshBtn')}</Button>
        </Space>
      </Card>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title={t('serviceMonitor.currentQps')} value={latest?.qps || 0} precision={1} prefix={<ThunderboltOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title={t('serviceMonitor.avgLatency')} value={latest?.latency_p50 || 0} precision={0} suffix="ms" prefix={<DashboardOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title={t('serviceMonitor.errorRate')} value={latest ? latest.error_rate * 100 : 0} precision={2} suffix="%" prefix={<WarningOutlined />} valueStyle={{ color: latest && latest.error_rate > 0.05 ? '#ff4d4f' : '#52c41a' }} /></Card></Col>
        <Col span={6}><Card><Statistic title={t('serviceMonitor.cpuUsage')} value={latest?.cpu_usage || 0} precision={1} suffix="%" prefix={<CheckCircleOutlined />} /></Card></Col>
      </Row>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title={t('serviceMonitor.qpsTrend')} size="small"><ReactECharts ref={chartRef} option={qpsOption} style={{ height: 250 }} /></Card>
        </Col>
        <Col span={12}>
          <Card title={t('serviceMonitor.latencyDist')} size="small"><ReactECharts option={latencyOption} style={{ height: 250 }} /></Card>
        </Col>
      </Row>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card title={t('serviceMonitor.errorRateTrend')} size="small"><ReactECharts option={errorOption} style={{ height: 250 }} /></Card>
        </Col>
        <Col span={12}>
          <Card title={t('serviceMonitor.resourceUsage')} size="small"><ReactECharts option={resourceOption} style={{ height: 250 }} /></Card>
        </Col>
      </Row>

      <Card>
        <Tabs items={[
          {
            key: 'rules', label: t('serviceMonitor.alertRules'),
            children: (
              <>
                <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 12 }} onClick={() => { setRuleModalOpen(true); ruleForm.resetFields(); }}>{t('serviceMonitor.addRule')}</Button>
                <Table dataSource={alertRules.filter(r => r.service_id === selectedServiceId)} rowKey="id" size="small" pagination={false}
                  columns={[
                    { title: t('serviceMonitor.metric'), dataIndex: 'metric_name', render: (v: string) => v.replace(/_/g, ' ').toUpperCase() },
                    { title: t('serviceMonitor.condition'), key: 'cond', render: (_: unknown, r: AlertRule) => `${r.operator === 'gt' ? '>' : r.operator === 'lt' ? '<' : r.operator} ${r.threshold}` },
                    { title: t('serviceMonitor.level'), dataIndex: 'severity', render: (v: string) => { const c = SEVERITY_CONFIG[v as keyof typeof SEVERITY_CONFIG]; return c ? <Tag color={c.color}>{c.label}</Tag> : v; } },
                    { title: t('serviceMonitor.ruleStatus'), dataIndex: 'enabled', render: (v: boolean) => <Switch size="small" checked={v} /> },
                    {
                      title: t('serviceMonitor.ruleAction'), key: 'act',
                      render: (_: unknown, r: AlertRule) => (
                        <Space>
                          <Button type="link" size="small" onClick={() => handleToggleRule(r)}>{r.enabled ? t('serviceMonitor.disable') : t('serviceMonitor.enable')}</Button>
                          <Popconfirm title={t('serviceMonitor.confirmDeleteRule')} onConfirm={() => handleDeleteRule(r.id)}><Button type="link" size="small" danger icon={<DeleteOutlined />} /></Popconfirm>
                        </Space>
                      ),
                    },
                  ]}
                />
              </>
            ),
          },
          {
            key: 'history', label: t('serviceMonitor.alertHistory'),
            children: (
              <Table dataSource={alertHistory} rowKey="id" size="small" pagination={{ pageSize: 10 }}
                columns={[
                  { title: t('serviceMonitor.alertTime'), dataIndex: 'triggered_at', width: 170, render: (v: string) => new Date(v).toLocaleString('zh-CN') },
                  { title: t('serviceMonitor.alertLevel'), dataIndex: 'severity', width: 80, render: (v: string) => { const c = SEVERITY_CONFIG[v as keyof typeof SEVERITY_CONFIG]; return c ? <Badge color={c.color} text={c.label} /> : v; } },
                  { title: t('serviceMonitor.alertMetric'), dataIndex: 'metric_name', render: (v: string) => v.replace(/_/g, ' ') },
                  { title: t('serviceMonitor.triggerValue'), dataIndex: 'triggered_value', width: 100 },
                  { title: t('serviceMonitor.alertStatus'), dataIndex: 'status', width: 100, render: (v: string) => <Tag color={v === 'triggered' ? 'red' : 'green'}>{v === 'triggered' ? t('serviceMonitor.triggered') : t('serviceMonitor.recovered')}</Tag> },
                  { title: t('serviceMonitor.recoveryTime'), dataIndex: 'recovered_at', width: 170, render: (v: string | null) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
                ]}
              />
            ),
          },
          {
            key: 'logs', label: t('serviceMonitor.accessLogs'),
            children: (
              <Table dataSource={logs} rowKey="request_id" size="small" pagination={{ pageSize: 15 }}
                columns={[
                  { title: t('serviceMonitor.logTime'), dataIndex: 'timestamp', width: 160, render: (v: string) => new Date(v).toLocaleString('zh-CN') },
                  { title: t('serviceMonitor.logRequestId'), dataIndex: 'request_id', width: 130 },
                  { title: t('serviceMonitor.logInput'), dataIndex: 'input_summary', ellipsis: true },
                  { title: t('serviceMonitor.logOutput'), dataIndex: 'output_summary', ellipsis: true },
                  { title: t('serviceMonitor.logLatency'), dataIndex: 'latency_ms', width: 80, render: (v: number) => `${Math.round(v)}ms` },
                  { title: t('serviceMonitor.logStatusCode'), dataIndex: 'status_code', width: 80, render: (v: number) => <Tag color={v === 200 ? 'green' : v >= 500 ? 'red' : 'orange'}>{v}</Tag> },
                ]}
              />
            ),
          },
        ]} />
      </Card>

      <Modal title={t('serviceMonitor.createRuleTitle')} open={ruleModalOpen} onCancel={() => setRuleModalOpen(false)} onOk={handleCreateRule}>
        <Form form={ruleForm} layout="vertical">
          <Form.Item label={t('serviceMonitor.metricLabel')} name="metric_name" rules={[{ required: true }]}>
            <Select options={[
              { value: 'qps', label: t('serviceMonitor.qpsLabel') },
              { value: 'latency_p99', label: t('serviceMonitor.latencyP99') },
              { value: 'error_rate', label: t('serviceMonitor.errorRateLabel') },
              { value: 'cpu_usage', label: t('serviceMonitor.cpuUsageLabel') },
              { value: 'memory_usage', label: t('serviceMonitor.memoryUsageLabel') },
              { value: 'gpu_usage', label: t('serviceMonitor.gpuUsageLabel') },
            ]} />
          </Form.Item>
          <Form.Item label={t('serviceMonitor.conditionLabel')} name="operator" initialValue="gt">
            <Select options={[{ value: 'gt', label: t('serviceMonitor.greaterThan') }, { value: 'lt', label: t('serviceMonitor.lessThan') }, { value: 'gte', label: '≥' }, { value: 'lte', label: '≤' }]} />
          </Form.Item>
          <Form.Item label={t('serviceMonitor.thresholdLabel')} name="threshold" rules={[{ required: true }]}><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item label={t('serviceMonitor.levelLabel')} name="severity" initialValue="warning">
            <Select options={[{ value: 'info', label: t('serviceMonitor.levelInfo') }, { value: 'warning', label: t('serviceMonitor.levelWarning') }, { value: 'critical', label: t('serviceMonitor.levelCritical') }]} />
          </Form.Item>
          <Form.Item label={t('serviceMonitor.enableLabel')} name="enabled" valuePropName="checked" initialValue={true}><Switch /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ServiceMonitorPage;
// @AI_GENERATED: end
