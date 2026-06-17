// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useCallback } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Table, Button, Space, Tag, Modal, Steps, Form, Input, Select,
  InputNumber, Slider, Switch, Row, Col, Statistic, Descriptions, message,
  Popconfirm, Radio, Divider,
} from 'antd';
import {
  PlusOutlined, RocketOutlined, DeleteOutlined, CopyOutlined,
  CloudServerOutlined, StopOutlined, CheckCircleOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import type { DeploymentTask, DeploymentStats, ReleaseStrategyType } from '../types/deployment';
import { TASK_STATUS_CONFIG, RELEASE_STRATEGY_LABELS } from '../types/deployment';
import { deploymentApi } from '../services/deploymentApi';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const { TextArea } = Input;

const SCENARIO_KEYS = [
  { value: 'load-forecasting', labelKey: 'deployment.scenarioLoadForecast' },
  { value: 'pv-power-forecast', labelKey: 'deployment.scenarioPvForecast' },
  { value: 'fault-diagnosis', labelKey: 'deployment.scenarioFaultDiag' },
  { value: 'price-forecasting', labelKey: 'deployment.scenarioPriceForecast' },
  { value: 'energy-storage', labelKey: 'deployment.scenarioEnergyStorage' },
  { value: 'wind-power', labelKey: 'deployment.scenarioWindPower' },
];

const DeploymentTaskPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  const SCENARIO_OPTIONS = SCENARIO_KEYS.map(s => ({ value: s.value, label: t(s.labelKey) }));
  // @AI_GENERATED: end
  const [tasks, setTasks] = useState<DeploymentTask[]>([]);
  const [stats, setStats] = useState<DeploymentStats>({ total_deployments: 0, running_services: 0, stopped_services: 0, avg_health_score: 0 });
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState<{ scenario?: string; status?: string; source_type?: string }>({});
  const [modalOpen, setModalOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [form] = Form.useForm();
  const [releaseType, setReleaseType] = useState<ReleaseStrategyType>('full');
  const [envVars, setEnvVars] = useState<Array<{ key: string; value: string }>>([]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [taskRes, statsRes] = await Promise.all([
        deploymentApi.listTasks(filters),
        deploymentApi.getStats(),
      ]);
      setTasks(taskRes.items);
      setTotal(taskRes.total);
      setStats(statsRes);
    } catch { message.error(t('deployment.loadFailed')); }
    setLoading(false);
  }, [filters]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleDeploy = async (id: string) => {
    try {
      await deploymentApi.deployTask(id);
      message.success(t('deployment.deploySuccess'));
      loadData();
    } catch { message.error(t('deployment.deployFailed')); }
  };

  const handleDelete = async (id: string) => {
    try {
      await deploymentApi.deleteTask(id);
      message.success(t('deployment.deleted'));
      loadData();
    } catch { message.error(t('deployment.deleteFailed')); }
  };

  const handleClone = async (id: string) => {
    try {
      await deploymentApi.cloneTask(id);
      message.success(t('deployment.cloneSuccess'));
      loadData();
    } catch { message.error(t('deployment.cloneFailed')); }
  };

  const handleCreate = async () => {
    try {
      const vals = form.getFieldsValue(true);
      const envObj: Record<string, string> = {};
      envVars.forEach(e => { if (e.key) envObj[e.key] = e.value; });
      await deploymentApi.createTask({
        name: vals.name,
        description: vals.description || '',
        scenario: vals.scenario || '',
        source_type: vals.source_type || 'template',
        source_id: vals.source_id || '',
        source_name: vals.source_name || '',
        backtest_task_id: vals.backtest_task_id,
        backtest_rank: vals.backtest_rank,
        deploy_config: {
          cpu: vals.cpu || '1核',
          memory: vals.memory || '2GB',
          gpu: vals.gpu || '无',
          replicas: vals.replicas || 1,
          endpoint: vals.endpoint || '/api/predict/default',
          timeout_ms: vals.timeout_ms || 5000,
          env_vars: envObj,
        },
        release_strategy: {
          type: releaseType,
          canary_percent: vals.canary_percent || 0,
          auto_promote: vals.auto_promote || false,
          promote_after_minutes: vals.promote_after_minutes || 0,
        },
      });
      message.success(t('deployment.createSuccess'));
      setModalOpen(false);
      setCurrentStep(0);
      form.resetFields();
      setEnvVars([]);
      setReleaseType('full');
      loadData();
    } catch { message.error(t('deployment.createFailed')); }
  };

  const columns = [
    { title: t('deployment.taskName'), dataIndex: 'name', key: 'name', width: 200, ellipsis: true, render: (v: string) => td(v) },
    {
      title: t('deployment.algorithmSource'), key: 'source',
      render: (_: unknown, r: DeploymentTask) => (
        <Space>
          <Tag color={r.source_type === 'template' ? 'purple' : 'blue'}>{r.source_type === 'template' ? t('deployment.template') : t('deployment.workflow')}</Tag>
          <span style={{ fontSize: 12, color: '#666' }}>{td(r.source_name)}</span>
        </Space>
      ),
    },
    {
      title: t('deployment.deployType'), key: 'release',
      render: (_: unknown, r: DeploymentTask) => td(RELEASE_STRATEGY_LABELS[r.release_strategy?.type] || t('deployment.fullRelease')),
    },
    {
      title: t('deployment.resourceConfig'), key: 'resources',
      render: (_: unknown, r: DeploymentTask) => `${r.deploy_config?.cpu || '-'} / ${r.deploy_config?.memory || '-'} × ${r.deploy_config?.replicas || 1}`,
    },
    {
      title: t('deployment.statusCol'), dataIndex: 'status', key: 'status',
      render: (s: string) => {
        const cfg = TASK_STATUS_CONFIG[s as keyof typeof TASK_STATUS_CONFIG];
        return cfg ? <Tag color={cfg.color}>{td(cfg.label)}</Tag> : <Tag>{s}</Tag>;
      },
    },
    {
      title: t('deployment.createdAt'), dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-',
    },
    {
      title: t('deployment.actions'), key: 'actions', width: 230, fixed: 'right' as const,
      render: (_: unknown, r: DeploymentTask) => (
        <Space size="small">
          {(r.status === 'draft' || r.status === 'stopped' || r.status === 'failed') && (
            <Button type="link" size="small" icon={<RocketOutlined />} onClick={() => handleDeploy(r.id)}>{t('deployment.deployBtn')}</Button>
          )}
          <Button type="link" size="small" icon={<CopyOutlined />} onClick={() => handleClone(r.id)}>{t('deployment.clone')}</Button>
          <Popconfirm title={t('deployment.confirmDelete')} onConfirm={() => handleDelete(r.id)}>
            <Button type="link" size="small" danger icon={<DeleteOutlined />}>{t('deployment.delete')}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const stepItems = [
    { title: t('deployment.stepBasicInfo') }, { title: t('deployment.stepAlgorithm') }, { title: t('deployment.stepDeployConfig') },
    { title: t('deployment.stepReleaseStrategy') }, { title: t('deployment.stepPreview') },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title={t('deployment.totalDeployments')} value={stats.total_deployments} prefix={<CloudServerOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title={t('deployment.runningServices')} value={stats.running_services} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title={t('deployment.stoppedServices')} value={stats.stopped_services} valueStyle={{ color: '#999' }} prefix={<StopOutlined />} /></Card></Col>
        <Col span={6}><Card><Statistic title={t('deployment.avgHealthScore')} value={stats.avg_health_score} suffix={t('deployment.points')} prefix={<ExclamationCircleOutlined />} /></Card></Col>
      </Row>

      <Card
        title={t('deployment.taskList')}
        extra={
          <Space>
            <Select allowClear placeholder={t('deployment.scenarioFilter')} style={{ width: 130 }} options={SCENARIO_OPTIONS} onChange={v => setFilters(f => ({ ...f, scenario: v }))} />
            <Select allowClear placeholder={t('deployment.statusFilter')} style={{ width: 110 }} options={Object.entries(TASK_STATUS_CONFIG).map(([k, v]) => ({ value: k, label: td(v.label) }))} onChange={v => setFilters(f => ({ ...f, status: v }))} />
            <Select allowClear placeholder={t('deployment.sourceTypeFilter')} style={{ width: 110 }} options={[{ value: 'template', label: t('deployment.template') }, { value: 'workflow', label: t('deployment.workflow') }]} onChange={v => setFilters(f => ({ ...f, source_type: v }))} />
            <Button type="primary" icon={<PlusOutlined />} onClick={() => { setModalOpen(true); setCurrentStep(0); form.resetFields(); setEnvVars([]); setReleaseType('full'); }}>{t('deployment.createDeploy')}</Button>
          </Space>
        }
      >
        <Table
          dataSource={tasks}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ total, pageSize: 20 }}
          scroll={{ x: 1180 }}
        />
      </Card>

      <Modal title={t('deployment.createDeployTask')} open={modalOpen} onCancel={() => setModalOpen(false)} width={720}
        footer={
          <Space>
            {currentStep > 0 && <Button onClick={() => setCurrentStep(s => s - 1)}>{t('deployment.prevStep')}</Button>}
            {currentStep < 4 && <Button type="primary" onClick={() => setCurrentStep(s => s + 1)}>{t('deployment.nextStep')}</Button>}
            {currentStep === 4 && <Button type="primary" onClick={handleCreate}>{t('deployment.confirmCreate')}</Button>}
          </Space>
        }
      >
        <Steps current={currentStep} items={stepItems} style={{ marginBottom: 24 }} size="small" />
        <Form form={form} layout="vertical">
          {currentStep === 0 && (
            <>
              <Form.Item label={t('deployment.taskNameLabel')} name="name" rules={[{ required: true, message: t('deployment.taskNameRequired') }]}><Input placeholder={t('deployment.taskNamePlaceholder')} /></Form.Item>
              <Form.Item label={t('deployment.description')} name="description"><TextArea rows={2} placeholder={t('deployment.descriptionPlaceholder')} /></Form.Item>
              <Form.Item label={t('deployment.scenarioLabel')} name="scenario"><Select options={SCENARIO_OPTIONS} placeholder={t('deployment.selectScenario')} /></Form.Item>
            </>
          )}
          {currentStep === 1 && (
            <>
              <Form.Item label={t('deployment.sourceType')} name="source_type" initialValue="template">
                <Radio.Group>
                  <Radio.Button value="template">{t('deployment.algorithmSolution')}</Radio.Button>
                  <Radio.Button value="workflow">{t('deployment.workflow')}</Radio.Button>
                </Radio.Group>
              </Form.Item>
              <Form.Item label={t('deployment.algorithmIdLabel')} name="source_id"><Input placeholder={t('deployment.algorithmIdPlaceholder')} /></Form.Item>
              <Form.Item label={t('deployment.algorithmNameLabel')} name="source_name"><Input placeholder={t('deployment.algorithmNamePlaceholder')} /></Form.Item>
              <Form.Item label={t('deployment.backtestTaskId')} name="backtest_task_id"><Input placeholder={t('deployment.backtestTaskIdPlaceholder')} /></Form.Item>
              <Form.Item label={t('deployment.backtestRank')} name="backtest_rank"><InputNumber min={1} placeholder="1" /></Form.Item>
            </>
          )}
          {currentStep === 2 && (
            <>
              <Row gutter={16}>
                <Col span={8}><Form.Item label={t('deployment.cpu')} name="cpu" initialValue="2核"><Select options={[{ value: '1核' }, { value: '2核' }, { value: '4核' }, { value: '8核' }]} /></Form.Item></Col>
                <Col span={8}><Form.Item label={t('deployment.memory')} name="memory" initialValue="4GB"><Select options={[{ value: '2GB' }, { value: '4GB' }, { value: '8GB' }, { value: '16GB' }]} /></Form.Item></Col>
                <Col span={8}><Form.Item label={t('deployment.gpu')} name="gpu" initialValue="无"><Select options={[{ value: '无' }, { value: '1×T4' }, { value: '1×V100' }, { value: '1×A100' }]} /></Form.Item></Col>
              </Row>
              <Row gutter={16}>
                <Col span={8}><Form.Item label={t('deployment.replicas')} name="replicas" initialValue={1}><InputNumber min={1} max={10} style={{ width: '100%' }} /></Form.Item></Col>
                <Col span={8}><Form.Item label={t('deployment.timeout')} name="timeout_ms" initialValue={5000}><InputNumber min={1000} max={60000} style={{ width: '100%' }} /></Form.Item></Col>
                <Col span={8}><Form.Item label={t('deployment.endpointPath')} name="endpoint" initialValue="/api/predict/default"><Input /></Form.Item></Col>
              </Row>
              <Divider orientation="left" plain>{t('deployment.envVars')}</Divider>
              {envVars.map((ev, i) => (
                <Row gutter={8} key={i} style={{ marginBottom: 8 }}>
                  <Col span={10}><Input placeholder="KEY" value={ev.key} onChange={e => { const nv = [...envVars]; nv[i].key = e.target.value; setEnvVars(nv); }} /></Col>
                  <Col span={10}><Input placeholder="VALUE" value={ev.value} onChange={e => { const nv = [...envVars]; nv[i].value = e.target.value; setEnvVars(nv); }} /></Col>
                  <Col span={4}><Button danger onClick={() => setEnvVars(envVars.filter((_, j) => j !== i))}>{t('deployment.delete')}</Button></Col>
                </Row>
              ))}
              <Button type="dashed" block onClick={() => setEnvVars([...envVars, { key: '', value: '' }])}>{t('deployment.addEnvVar')}</Button>
            </>
          )}
          {currentStep === 3 && (
            <>
              <Form.Item label={t('deployment.releaseStrategy')}>
                <Radio.Group value={releaseType} onChange={e => setReleaseType(e.target.value)}>
                  <Radio.Button value="full">{t('deployment.fullRelease')}</Radio.Button>
                  <Radio.Button value="canary">{t('deployment.canaryRelease')}</Radio.Button>
                  <Radio.Button value="blue-green">{t('deployment.blueGreenDeploy')}</Radio.Button>
                </Radio.Group>
              </Form.Item>
              {releaseType === 'canary' && (
                <>
                  <Form.Item label={t('deployment.canaryPercent')} name="canary_percent" initialValue={20}><Slider min={1} max={100} /></Form.Item>
                  <Form.Item label={t('deployment.autoPromote')} name="auto_promote" valuePropName="checked"><Switch /></Form.Item>
                  <Form.Item label={t('deployment.promoteWait')} name="promote_after_minutes" initialValue={30}><InputNumber min={1} max={1440} /></Form.Item>
                </>
              )}
            </>
          )}
          {currentStep === 4 && (
            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label={t('deployment.previewTaskName')}>{form.getFieldValue('name') || '-'}</Descriptions.Item>
              <Descriptions.Item label={t('deployment.previewScenario')}>{form.getFieldValue('scenario') || '-'}</Descriptions.Item>
              <Descriptions.Item label={t('deployment.previewSourceType')}>{form.getFieldValue('source_type') === 'workflow' ? t('deployment.workflow') : t('deployment.template')}</Descriptions.Item>
              <Descriptions.Item label={t('deployment.previewAlgorithmName')}>{form.getFieldValue('source_name') || '-'}</Descriptions.Item>
              <Descriptions.Item label={t('deployment.previewCpuMemory')}>{form.getFieldValue('cpu') || '2核'} / {form.getFieldValue('memory') || '4GB'}</Descriptions.Item>
              <Descriptions.Item label={t('deployment.previewReplicas')}>{form.getFieldValue('replicas') || 1}</Descriptions.Item>
              <Descriptions.Item label={t('deployment.previewStrategy')}>{td(RELEASE_STRATEGY_LABELS[releaseType])}</Descriptions.Item>
              <Descriptions.Item label={t('deployment.previewEndpoint')}>{form.getFieldValue('endpoint') || '-'}</Descriptions.Item>
            </Descriptions>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default DeploymentTaskPage;
// @AI_GENERATED: end
