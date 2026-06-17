// @AI_GENERATED: Kiro v1.0
/**
 * 数据源管理页面
 * 支持两种数据源类型：数据库（MySQL/PostgreSQL）和 API 接口
 * 新建/编辑表单根据类型动态显示不同配置字段
 */
import { useState } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Table, Button, Tag, Space, Typography, Modal, Form, Input, InputNumber,
  Select, message, Popconfirm, Badge,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, SyncOutlined,
  DatabaseOutlined, ApiOutlined,
} from '@ant-design/icons';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const { Title, Text } = Typography;

type SourceType = 'mysql' | 'postgresql' | 'api';

interface DbConfig {
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
}

interface ApiConfig {
  url: string;
  method: 'GET' | 'POST';
  headers: string;
  authType: 'none' | 'bearer' | 'basic';
  authToken: string;
}

interface DataSource {
  id: string;
  name: string;
  type: SourceType;
  config: Partial<DbConfig & ApiConfig>;
  status: 'connected' | 'disconnected' | 'error';
  description: string;
  createdAt: string;
  lastSync: string | null;
}

const MOCK_SOURCES: DataSource[] = [
  // @AI_GENERATED: Kiro v1.0
  // 光伏电站数据源 - 示例场景
  { id: 'ds-pv-1', name: '宁夏银川光伏电站', type: 'mysql', config: { host: '192.168.10.50', port: 3306, database: 'pv_yinchuan', username: 'pv_reader' }, status: 'connected', description: '10MW光伏电站SCADA数据，包含气象和发电数据，15分钟采集间隔', createdAt: '2025-01-01', lastSync: '2026-03-21 10:00' },
  { id: 'ds-pv-2', name: '气象站数据接口', type: 'api', config: { url: 'https://weather.pv-station.com/api/v1/realtime', method: 'GET', authType: 'bearer' }, status: 'connected', description: '光伏电站配套气象站API，提供辐照度、温度、湿度、风速等实时数据', createdAt: '2025-01-01', lastSync: '2026-03-21 10:05' },
  // @AI_GENERATED: end
  { id: 'ds-1', name: 'MySQL 生产数据库', type: 'mysql', config: { host: '192.168.1.100', port: 3306, database: 'production', username: 'reader' }, status: 'connected', description: '生产环境主数据库，存储设备运行数据', createdAt: '2026-01-15', lastSync: '2026-03-18 10:30' },
  { id: 'ds-2', name: 'PostgreSQL 分析库', type: 'postgresql', config: { host: '192.168.1.101', port: 5432, database: 'analytics', username: 'analyst' }, status: 'connected', description: '数据分析库，存储清洗后的特征数据', createdAt: '2026-01-20', lastSync: '2026-03-18 10:25' },
  { id: 'ds-3', name: 'MySQL 时序数据库', type: 'mysql', config: { host: '192.168.1.102', port: 3306, database: 'timeseries', username: 'ts_reader' }, status: 'connected', description: '时序数据存储，传感器采集数据', createdAt: '2026-02-05', lastSync: '2026-03-18 09:45' },
  { id: 'ds-4', name: '气象数据 API', type: 'api', config: { url: 'https://api.weather.example.com/v2/forecast', method: 'GET', authType: 'bearer' }, status: 'connected', description: '第三方气象数据接口，提供温度、辐照度等', createdAt: '2026-02-01', lastSync: '2026-03-18 09:00' },
  { id: 'ds-5', name: '电网调度 API', type: 'api', config: { url: 'https://grid.example.com/api/dispatch', method: 'POST', authType: 'basic' }, status: 'disconnected', description: '电网调度系统接口，获取负荷和调度数据', createdAt: '2026-03-01', lastSync: null },
];

// @AI_GENERATED: Kiro v1.0
const typeIcon = (t: SourceType) => t === 'api' ? <ApiOutlined /> : <DatabaseOutlined />;
const typeLabel = (t: SourceType) => ({ mysql: 'MySQL', postgresql: 'PostgreSQL', api: 'API' }[t]);
const typeColor = (t: SourceType) => ({ mysql: '#1890ff', postgresql: '#52c41a', api: '#fa8c16' }[t]);

const statusMap: Record<string, { textKey: string; status: 'success' | 'default' | 'error' }> = {
  connected: { textKey: 'dataSource.statusConnected', status: 'success' },
  disconnected: { textKey: 'dataSource.statusDisconnected', status: 'default' },
  error: { textKey: 'dataSource.statusError', status: 'error' },
};

const DataSourcePage: React.FC = () => {
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end
  const [sources, setSources] = useState<DataSource[]>(MOCK_SOURCES);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingRawText, setEditingRawText] = useState<{ name: string; description: string } | null>(null);
  const [form] = Form.useForm();
  const selectedType = Form.useWatch('type', form) as SourceType | undefined;

  const openAdd = () => {
    setEditingId(null);
    setEditingRawText(null);
    form.resetFields();
    form.setFieldsValue({ type: 'mysql', config: { port: 3306, method: 'GET', authType: 'none' } });
    setModalOpen(true);
  };
  const openEdit = (r: DataSource) => {
    setEditingId(r.id);
    setEditingRawText({ name: r.name, description: r.description });
    form.setFieldsValue({ name: td(r.name), type: r.type, description: td(r.description), config: r.config });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const vals = await form.validateFields();
    const nextVals = { ...vals };
    if (editingId && editingRawText && !i18n.language.toLowerCase().startsWith('zh')) {
      // English mode displays translated text; keep original raw value if user did not actually modify it.
      if (nextVals.name === td(editingRawText.name)) nextVals.name = editingRawText.name;
      if (nextVals.description === td(editingRawText.description)) nextVals.description = editingRawText.description;
    }
    if (editingId) {
      setSources(prev => prev.map(s => s.id === editingId ? { ...s, ...nextVals, config: nextVals.config } : s));
      message.success(t('dataSource.updated'));
    } else {
      const newSrc: DataSource = { id: `ds-${Date.now()}`, ...nextVals, config: nextVals.config, status: 'disconnected', createdAt: new Date().toISOString().slice(0, 10), lastSync: null };
      setSources(prev => [...prev, newSrc]);
      message.success(t('dataSource.created'));
    }
    setEditingRawText(null);
    setModalOpen(false);
  };

  const handleDelete = (id: string) => { setSources(prev => prev.filter(s => s.id !== id)); message.success(t('dataSource.deleted')); };
  const handleTest = (r: DataSource) => { message.info(t('dataSource.testing', { name: td(r.name) })); setTimeout(() => { setSources(prev => prev.map(s => s.id === r.id ? { ...s, status: 'connected', lastSync: new Date().toLocaleString() } : s)); message.success(t('dataSource.testSuccess', { name: td(r.name) })); }, 1200); };

  const dbCount = sources.filter(s => s.type === 'mysql' || s.type === 'postgresql').length;
  const apiCount = sources.filter(s => s.type === 'api').length;
  const connectedCount = sources.filter(s => s.status === 'connected').length;

  const columns = [
    { title: t('dataSource.name'), dataIndex: 'name', key: 'name', render: (_: string, r: DataSource) => <Space>{typeIcon(r.type)}<Text strong>{td(r.name)}</Text></Space> },
    { title: t('dataSource.type'), dataIndex: 'type', key: 'type', width: 120, render: (tp: SourceType) => <Tag color={typeColor(tp)}>{typeLabel(tp)}</Tag> },
    { title: t('dataSource.status'), dataIndex: 'status', key: 'status', width: 100, render: (s: string) => { const m = statusMap[s]; return <Badge status={m.status} text={t(m.textKey)} />; } },
    { title: t('dataSource.description'), dataIndex: 'description', key: 'description', ellipsis: true, render: (v: string) => td(v) },
    { title: t('dataSource.lastSync'), dataIndex: 'lastSync', key: 'lastSync', width: 180, render: (v: string | null) => v || <Text type="secondary">—</Text> },
    {
      title: t('dataSource.actions'), key: 'actions', width: 200,
      render: (_: unknown, r: DataSource) => (
        <Space>
          <Button size="small" icon={<SyncOutlined />} onClick={() => handleTest(r)}>{t('dataSource.test')}</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>{t('dataSource.edit')}</Button>
          <Popconfirm title={t('dataSource.confirmDelete')} onConfirm={() => handleDelete(r.id)}><Button size="small" danger icon={<DeleteOutlined />} /></Popconfirm>
        </Space>
      ),
    },
  ];

  const isDb = selectedType === 'mysql' || selectedType === 'postgresql';
  const isApi = selectedType === 'api';

  return (
    <div style={{ padding: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>{t('dataSource.title')}</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>{t('dataSource.addNew')}</Button>
      </div>

      <Space size={16} style={{ marginBottom: 16 }}>
        <Card size="small" style={{ minWidth: 120 }}><Text type="secondary">{t('dataSource.totalSources')}</Text><div style={{ fontSize: 24, fontWeight: 600 }}>{sources.length}</div></Card>
        <Card size="small" style={{ minWidth: 120 }}><Text type="secondary">{t('dataSource.connected')}</Text><div style={{ fontSize: 24, fontWeight: 600, color: '#52c41a' }}>{connectedCount}</div></Card>
        <Card size="small" style={{ minWidth: 120 }}><Text type="secondary">{t('dataSource.database')}</Text><div style={{ fontSize: 24, fontWeight: 600, color: '#1890ff' }}>{dbCount}</div></Card>
        <Card size="small" style={{ minWidth: 120 }}><Text type="secondary">{t('dataSource.api')}</Text><div style={{ fontSize: 24, fontWeight: 600, color: '#fa8c16' }}>{apiCount}</div></Card>
      </Space>

      <Card>
        <Table dataSource={sources} columns={columns} rowKey="id" pagination={false} size="middle" />
      </Card>

      <Modal title={editingId ? t('dataSource.editTitle') : t('dataSource.addTitle')} open={modalOpen} onOk={handleSave} onCancel={() => { setModalOpen(false); setEditingRawText(null); }} width={560} destroyOnClose>
        <Form form={form} layout="vertical" initialValues={{ type: 'mysql', config: { port: 3306, method: 'GET', authType: 'none' } }}>
          <Form.Item name="name" label={t('dataSource.nameLabel')} rules={[{ required: true, message: t('dataSource.nameRequired') }]}><Input placeholder={t('dataSource.namePlaceholder')} /></Form.Item>
          <Form.Item name="type" label={t('dataSource.typeLabel')} rules={[{ required: true }]}>
            <Select options={[{ value: 'mysql', label: 'MySQL' }, { value: 'postgresql', label: 'PostgreSQL' }, { value: 'api', label: t('dataSource.apiType') }]} />
          </Form.Item>
          <Form.Item name="description" label={t('dataSource.descLabel')}><Input.TextArea rows={2} placeholder={t('dataSource.descPlaceholder')} /></Form.Item>

          {isDb && (
            <>
              <Form.Item name={['config', 'host']} label={t('dataSource.host')} rules={[{ required: true, message: t('dataSource.hostRequired') }]}><Input placeholder="192.168.1.100" /></Form.Item>
              <Form.Item name={['config', 'port']} label={t('dataSource.port')} rules={[{ required: true }]}><InputNumber style={{ width: '100%' }} placeholder={selectedType === 'mysql' ? '3306' : '5432'} /></Form.Item>
              <Form.Item name={['config', 'database']} label={t('dataSource.dbName')} rules={[{ required: true, message: t('dataSource.dbNameRequired') }]}><Input placeholder="production" /></Form.Item>
              <Form.Item name={['config', 'username']} label={t('dataSource.username')} rules={[{ required: true, message: t('dataSource.usernameRequired') }]}><Input placeholder="root" /></Form.Item>
              <Form.Item name={['config', 'password']} label={t('dataSource.password')}><Input.Password placeholder={t('dataSource.passwordPlaceholder')} /></Form.Item>
            </>
          )}

          {isApi && (
            <>
              <Form.Item name={['config', 'url']} label={t('dataSource.url')} rules={[{ required: true, message: t('dataSource.urlRequired') }]}><Input placeholder="https://api.example.com/v1/data" /></Form.Item>
              <Form.Item name={['config', 'method']} label={t('dataSource.method')}><Select options={[{ value: 'GET', label: 'GET' }, { value: 'POST', label: 'POST' }]} /></Form.Item>
              <Form.Item name={['config', 'authType']} label={t('dataSource.authType')}><Select options={[{ value: 'none', label: t('dataSource.authNone') }, { value: 'bearer', label: t('dataSource.authBearer') }, { value: 'basic', label: t('dataSource.authBasic') }]} /></Form.Item>
              <Form.Item name={['config', 'authToken']} label={t('dataSource.authToken')}><Input.Password placeholder={t('dataSource.authTokenPlaceholder')} /></Form.Item>
              <Form.Item name={['config', 'headers']} label={t('dataSource.customHeaders')}><Input.TextArea rows={2} placeholder='{"Content-Type": "application/json"}' /></Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default DataSourcePage;
// @AI_GENERATED: end
