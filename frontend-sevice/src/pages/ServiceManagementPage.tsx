// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useCallback } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Table, Button, Space, Tag, Badge, Drawer, Tabs, Descriptions,
  Timeline, InputNumber, Modal, Progress, message, Popconfirm, Tooltip,
} from 'antd';
import {
  PlayCircleOutlined, PauseCircleOutlined, ReloadOutlined,
  RollbackOutlined, DashboardOutlined, ExpandOutlined, CopyOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { DeployedService, ServiceVersion, AccessLog } from '../types/deployment';
import { HEALTH_CONFIG } from '../types/deployment';
import { deploymentApi } from '../services/deploymentApi';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const ServiceManagementPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const navigate = useNavigate();
  const [services, setServices] = useState<DeployedService[]>([]);
  const [loading, setLoading] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedService, setSelectedService] = useState<DeployedService | null>(null);
  const [versions, setVersions] = useState<ServiceVersion[]>([]);
  const [logs, setLogs] = useState<AccessLog[]>([]);
  const [scaleModalOpen, setScaleModalOpen] = useState(false);
  const [scaleTarget, setScaleTarget] = useState(1);
  const [scaleServiceId, setScaleServiceId] = useState('');
  const [rollbackModalOpen, setRollbackModalOpen] = useState(false);
  const [rollbackVersion, setRollbackVersion] = useState('');
  const [rollbackServiceId, setRollbackServiceId] = useState('');

  const loadServices = useCallback(async () => {
    setLoading(true);
    try {
      const data = await deploymentApi.listServices();
      setServices(data);
    } catch { message.error(t('serviceManagement.loadFailed')); }
    setLoading(false);
  }, []);

  useEffect(() => { loadServices(); }, [loadServices]);

  const openDrawer = async (svc: DeployedService) => {
    setSelectedService(svc);
    setDrawerOpen(true);
    try {
      const [v, l] = await Promise.all([
        deploymentApi.getServiceVersions(svc.id),
        deploymentApi.getServiceLogs(svc.id, 1, 20),
      ]);
      setVersions(v as ServiceVersion[]);
      setLogs(l.items);
    } catch { /* ignore */ }
  };

  const handleAction = async (action: 'start' | 'stop' | 'restart', id: string) => {
    try {
      if (action === 'start') await deploymentApi.startService(id);
      else if (action === 'stop') await deploymentApi.stopService(id);
      else await deploymentApi.restartService(id);
      message.success(action === 'start' ? t('serviceManagement.startSuccess') : action === 'stop' ? t('serviceManagement.stopSuccess') : t('serviceManagement.restartSuccess'));
      loadServices();
    } catch { message.error(t('serviceManagement.actionFailed')); }
  };

  const handleScale = async () => {
    try {
      await deploymentApi.scaleService(scaleServiceId, scaleTarget);
      message.success(t('serviceManagement.scaleSuccess'));
      setScaleModalOpen(false);
      loadServices();
    } catch { message.error(t('serviceManagement.scaleFailed')); }
  };

  const handleRollback = async () => {
    try {
      await deploymentApi.rollbackService(rollbackServiceId, rollbackVersion);
      message.success(t('serviceManagement.rollbackSuccess'));
      setRollbackModalOpen(false);
      loadServices();
    } catch { message.error(t('serviceManagement.rollbackFailed')); }
  };

  const columns = [
    { title: t('serviceManagement.serviceName'), dataIndex: 'name', key: 'name', width: 180, ellipsis: true, render: (v: string) => td(v) },
    {
      title: t('serviceManagement.endpointUrl'), dataIndex: 'endpoint', key: 'endpoint', width: 280, ellipsis: true,
      render: (v: string) => (
        <Tooltip title={v}>
          <span style={{ fontSize: 12 }}>{v}</span>
          <CopyOutlined style={{ marginLeft: 4, cursor: 'pointer', color: '#1890ff' }} onClick={() => { navigator.clipboard.writeText(v); message.success(t('serviceManagement.copied')); }} />
        </Tooltip>
      ),
    },
    { title: t('serviceManagement.version'), dataIndex: 'version', key: 'version', width: 80 },
    {
      title: t('serviceManagement.replicasCol'), key: 'replicas', width: 140,
      render: (_: unknown, r: DeployedService) => (
        <Space size={4}>
          <Progress percent={r.replicas.desired > 0 ? Math.round(r.replicas.ready / r.replicas.desired * 100) : 0} size="small" style={{ width: 60 }} />
          <span style={{ fontSize: 12 }}>{r.replicas.ready}/{r.replicas.desired}</span>
        </Space>
      ),
    },
    {
      title: t('serviceManagement.healthStatus'), dataIndex: 'health', key: 'health', width: 100,
      render: (h: string) => {
        const cfg = HEALTH_CONFIG[h as keyof typeof HEALTH_CONFIG];
        return cfg ? <Badge color={cfg.color} text={td(cfg.label)} /> : <Badge status="default" text={h} />;
      },
    },
    { title: 'QPS', dataIndex: 'qps', key: 'qps', width: 80, render: (v: number) => v > 0 ? v.toFixed(1) : '-' },
    { title: t('serviceManagement.latencyMs'), dataIndex: 'avg_latency_ms', key: 'latency', width: 90, render: (v: number) => v > 0 ? Math.round(v) : '-' },
    {
      title: t('serviceManagement.actions'), key: 'actions', width: 300,
      render: (_: unknown, r: DeployedService) => (
        <Space size="small" wrap>
          {r.health === 'stopped' ? (
            <Button type="link" size="small" icon={<PlayCircleOutlined />} onClick={() => handleAction('start', r.id)}>{t('serviceManagement.start')}</Button>
          ) : (
            <Popconfirm title={t('serviceManagement.confirmStop')} onConfirm={() => handleAction('stop', r.id)}>
              <Button type="link" size="small" icon={<PauseCircleOutlined />}>{t('serviceManagement.stop')}</Button>
            </Popconfirm>
          )}
          <Button type="link" size="small" icon={<ReloadOutlined />} onClick={() => handleAction('restart', r.id)}>{t('serviceManagement.restart')}</Button>
          <Button type="link" size="small" icon={<ExpandOutlined />} onClick={() => { setScaleServiceId(r.id); setScaleTarget(r.replicas.desired); setScaleModalOpen(true); }}>{t('serviceManagement.scale')}</Button>
          <Button type="link" size="small" icon={<RollbackOutlined />} onClick={() => { setRollbackServiceId(r.id); setRollbackVersion(r.versions?.[0]?.version || ''); setRollbackModalOpen(true); }}>{t('serviceManagement.rollback')}</Button>
          <Button type="link" size="small" icon={<DashboardOutlined />} onClick={() => navigate(`/deployment/monitor?service=${r.id}`)}>{t('serviceManagement.monitor')}</Button>
          <Button type="link" size="small" onClick={() => openDrawer(r)}>{t('serviceManagement.detail')}</Button>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Card title={t('serviceManagement.title')} extra={<Button onClick={loadServices} icon={<ReloadOutlined />}>{t('serviceManagement.refresh')}</Button>}>
        <Table dataSource={services} columns={columns} rowKey="id" loading={loading} pagination={false} scroll={{ x: 1200 }} />
      </Card>

      <Drawer title={selectedService?.name || t('serviceManagement.serviceDetail')} open={drawerOpen} onClose={() => setDrawerOpen(false)} width={600}>
        {selectedService && (
          <Tabs items={[
            {
              key: 'info', label: t('serviceManagement.basicInfo'),
              children: (
                <Descriptions bordered column={1} size="small">
                  <Descriptions.Item label={t('serviceManagement.serviceId')}>{selectedService.id}</Descriptions.Item>
                  <Descriptions.Item label={t('serviceManagement.endpoint')}>{selectedService.endpoint}</Descriptions.Item>
                  <Descriptions.Item label={t('serviceManagement.version')}>{selectedService.version}</Descriptions.Item>
                  <Descriptions.Item label={t('serviceManagement.healthLabel')}><Badge color={HEALTH_CONFIG[selectedService.health]?.color} text={td(HEALTH_CONFIG[selectedService.health]?.label)} /></Descriptions.Item>
                  <Descriptions.Item label={t('serviceManagement.replicasLabel')}>{selectedService.replicas.ready}/{selectedService.replicas.desired}</Descriptions.Item>
                  <Descriptions.Item label="QPS">{selectedService.qps}</Descriptions.Item>
                  <Descriptions.Item label={t('serviceManagement.avgLatency')}>{selectedService.avg_latency_ms}ms</Descriptions.Item>
                  <Descriptions.Item label={t('serviceManagement.errorRate')}>{(selectedService.error_rate * 100).toFixed(2)}%</Descriptions.Item>
                  <Descriptions.Item label={t('serviceManagement.uptime')}>{selectedService.uptime}</Descriptions.Item>
                  <Descriptions.Item label={t('serviceManagement.createdAtLabel')}>{new Date(selectedService.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'versions', label: t('serviceManagement.versionHistory'),
              children: (
                <Timeline items={versions.map(v => ({
                  color: v.status === 'active' ? 'green' : 'gray',
                  children: (
                    <div>
                      <strong>{v.version}</strong> {v.status === 'active' && <Tag color="green">{t('serviceManagement.current')}</Tag>}
                      <div style={{ fontSize: 12, color: '#999' }}>{new Date(v.published_at).toLocaleString('zh-CN')}</div>
                      {v.status !== 'active' && (
                        <Button type="link" size="small" onClick={() => { setRollbackServiceId(selectedService.id); setRollbackVersion(v.version); setRollbackModalOpen(true); }}>{t('serviceManagement.rollbackToVersion')}</Button>
                      )}
                    </div>
                  ),
                }))} />
              ),
            },
            {
              key: 'logs', label: t('serviceManagement.accessLog'),
              children: (
                <Table dataSource={logs} rowKey="request_id" size="small" pagination={{ pageSize: 10 }}
                  columns={[
                    { title: t('serviceManagement.time'), dataIndex: 'timestamp', width: 160, render: (v: string) => new Date(v).toLocaleString('zh-CN') },
                    { title: t('serviceManagement.requestId'), dataIndex: 'request_id', width: 120 },
                    { title: t('serviceManagement.input'), dataIndex: 'input_summary', ellipsis: true },
                    { title: t('serviceManagement.latency'), dataIndex: 'latency_ms', width: 80, render: (v: number) => `${Math.round(v)}ms` },
                    { title: t('serviceManagement.statusCode'), dataIndex: 'status_code', width: 70, render: (v: number) => <Tag color={v === 200 ? 'green' : v >= 500 ? 'red' : 'orange'}>{v}</Tag> },
                  ]}
                />
              ),
            },
          ]} />
        )}
      </Drawer>

      <Modal title={t('serviceManagement.scaleTitle')} open={scaleModalOpen} onCancel={() => setScaleModalOpen(false)} onOk={handleScale}>
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <p>{t('serviceManagement.targetReplicas')}</p>
          <InputNumber min={1} max={10} value={scaleTarget} onChange={v => setScaleTarget(v || 1)} size="large" />
        </div>
      </Modal>

      <Modal title={t('serviceManagement.rollbackTitle')} open={rollbackModalOpen} onCancel={() => setRollbackModalOpen(false)} onOk={handleRollback}>
        <p>{t('serviceManagement.rollbackConfirm')} <strong>{rollbackVersion}</strong>？</p>
        <p style={{ color: '#999', fontSize: 12 }}>{t('serviceManagement.rollbackDesc')}</p>
      </Modal>
    </div>
  );
};

export default ServiceManagementPage;
// @AI_GENERATED: end
