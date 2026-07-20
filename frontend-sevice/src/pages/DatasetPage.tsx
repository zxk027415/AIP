// @AI_GENERATED: Kiro v1.0
/**
 * 数据集管理页面
 * 管理开源数据集和私有数据集，支持预览、版本管理和标签
 * 开源数据集：各行业公开数据集，用于算法模板精度验证
 * 私有数据集：用户上传的私有数据
 */
import { useCallback, useEffect, useState } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Table, Button, Tag, Space, Typography, Modal, Upload, Input, Select, message,
  Popconfirm, Descriptions, Badge, Tabs, Row, Col, Statistic,
  Alert, Divider, Progress,
} from 'antd';
import {
  DeleteOutlined, EyeOutlined, DownloadOutlined,
  UploadOutlined, SearchOutlined, FileExcelOutlined, FileTextOutlined,
  GlobalOutlined, LockOutlined, CloudDownloadOutlined,
  DatabaseOutlined, ExperimentOutlined, ThunderboltOutlined,
  ClusterOutlined, EditOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
// @AI_GENERATED: 光伏训练集卡片需要路由跳转和真实 API
import { useNavigate } from 'react-router-dom';
import { cumulativeTrainingApi, trainingWorkspaceApi } from '../services/iterativeLabelingApi';
// @AI_GENERATED: end

const { Title, Text } = Typography;

interface Dataset {
  id: string;
  name: string;
  format: 'csv' | 'excel' | 'json' | 'parquet';
  size: string;
  rows: number;
  columns: number;
  tags: string[];
  source: string;
  status: 'ready' | 'processing' | 'error';
  version: number;
  createdAt: string;
  updatedAt: string;
  description: string;
  type: 'opensource' | 'private';
  industry?: string;
  license?: string;
  downloadUrl?: string;
}

// 开源数据集 - 各行业公开数据
const OPENSOURCE_DATASETS: Dataset[] = [
  { id: 'os-1', name: 'NREL Solar Radiation Dataset', format: 'csv', size: '2.3 GB', rows: 8760000, columns: 15, tags: ['光伏', '辐照度', '气象'], source: 'NREL (美国国家可再生能源实验室)', status: 'ready', version: 1, createdAt: '2024-01-01', updatedAt: '2024-12-01', description: '美国各地太阳辐照度数据，包含DNI、DHI、GHI等指标，适用于光伏功率预测模型训练', type: 'opensource', industry: '新能源', license: 'Public Domain', downloadUrl: 'https://nsrdb.nrel.gov/' },
  { id: 'os-2', name: 'Kaggle Wind Turbine SCADA', format: 'csv', size: '156 MB', rows: 50530, columns: 21, tags: ['风电', 'SCADA', '功率'], source: 'Kaggle', status: 'ready', version: 1, createdAt: '2023-06-15', updatedAt: '2023-06-15', description: '土耳其风电场SCADA数据，包含风速、功率、桨距角等参数，适用于风电功率预测', type: 'opensource', industry: '新能源', license: 'CC BY 4.0', downloadUrl: 'https://www.kaggle.com/datasets/berkerisen/wind-turbine-scada-dataset' },
  { id: 'os-3', name: 'NASA Battery Aging Dataset', format: 'csv', size: '890 MB', rows: 2500000, columns: 12, tags: ['储能', '电池', 'SOH'], source: 'NASA PCoE', status: 'ready', version: 2, createdAt: '2022-03-01', updatedAt: '2024-06-01', description: 'NASA锂电池老化实验数据，包含充放电循环、容量衰减等，适用于SOH预测', type: 'opensource', industry: '新能源', license: 'Public Domain', downloadUrl: 'https://www.nasa.gov/content/prognostics-center-of-excellence-data-set-repository' },
  { id: 'os-4', name: 'UCI Steel Plates Faults', format: 'csv', size: '1.2 MB', rows: 1941, columns: 34, tags: ['钢铁', '缺陷', '质量'], source: 'UCI Machine Learning', status: 'ready', version: 1, createdAt: '2010-10-01', updatedAt: '2010-10-01', description: '钢板表面缺陷分类数据集，7种缺陷类型，适用于钢铁质量检测模型', type: 'opensource', industry: '工业制造', license: 'CC BY 4.0', downloadUrl: 'https://archive.ics.uci.edu/dataset/198/steel+plates+faults' },
  { id: 'os-5', name: 'CWRU Bearing Dataset', format: 'csv', size: '245 MB', rows: 3000000, columns: 4, tags: ['轴承', '振动', '故障诊断'], source: 'Case Western Reserve University', status: 'ready', version: 1, createdAt: '2000-01-01', updatedAt: '2020-01-01', description: '轴承振动信号数据集，包含正常和多种故障状态，是设备故障诊断的经典数据集', type: 'opensource', industry: '通用工业', license: 'Public Domain', downloadUrl: 'https://engineering.case.edu/bearingdatacenter' },
  { id: 'os-6', name: 'Pecan Street Dataport', format: 'csv', size: '5.6 GB', rows: 15000000, columns: 25, tags: ['电网', '负荷', '智能电表'], source: 'Pecan Street Inc.', status: 'ready', version: 3, createdAt: '2023-01-01', updatedAt: '2025-01-01', description: '美国家庭用电数据，分钟级粒度，适用于负荷预测和需求响应研究', type: 'opensource', industry: '源网荷储', license: 'Academic Use', downloadUrl: 'https://www.pecanstreet.org/dataport/' },
  { id: 'os-7', name: 'SEAI Building Energy', format: 'csv', size: '78 MB', rows: 525600, columns: 18, tags: ['楼宇', '能耗', 'HVAC'], source: 'SEAI (爱尔兰可持续能源局)', status: 'ready', version: 1, createdAt: '2024-03-01', updatedAt: '2024-03-01', description: '商业建筑能耗数据，包含暖通空调、照明等分项能耗，适用于楼宇能效优化', type: 'opensource', industry: '楼宇园区', license: 'Open Data', downloadUrl: 'https://www.seai.ie/data-and-insights/' },
  { id: 'os-8', name: 'Port of Rotterdam AIS', format: 'parquet', size: '3.2 GB', rows: 25000000, columns: 12, tags: ['港口', 'AIS', '船舶'], source: 'Port of Rotterdam', status: 'ready', version: 1, createdAt: '2024-06-01', updatedAt: '2024-06-01', description: '鹿特丹港船舶AIS轨迹数据，适用于泊位调度和船舶到港预测', type: 'opensource', industry: '港口运输', license: 'CC BY-NC 4.0', downloadUrl: 'https://www.portofrotterdam.com/en/doing-business/port-of-the-future/open-data' },
  { id: 'os-9', name: 'Carbon Footprint Dataset', format: 'csv', size: '45 MB', rows: 120000, columns: 22, tags: ['碳排放', '碳足迹', 'LCA'], source: 'Our World in Data', status: 'ready', version: 2, createdAt: '2024-01-01', updatedAt: '2025-01-01', description: '全球碳排放数据，按国家、行业、产品分类，适用于碳核算和碳足迹分析', type: 'opensource', industry: '碳管理', license: 'CC BY 4.0', downloadUrl: 'https://ourworldindata.org/co2-emissions' },
  { id: 'os-10', name: 'MVTec Anomaly Detection', format: 'json', size: '4.9 GB', rows: 5354, columns: 3, tags: ['视觉', '缺陷检测', '异常'], source: 'MVTec Software GmbH', status: 'ready', version: 1, createdAt: '2019-06-01', updatedAt: '2021-01-01', description: '工业缺陷检测图像数据集，15个类别，适用于工业视觉异常检测模型', type: 'opensource', industry: '通用工业', license: 'CC BY-NC-SA 4.0', downloadUrl: 'https://www.mvtec.com/company/research/datasets/mvtec-ad' },
];

// 私有数据集 - 用户上传
const PRIVATE_DATASETS: Dataset[] = [
  // @AI_GENERATED: Kiro v1.0
  // 光伏电站示例数据集 - 完整示例场景
  { id: 'pv-demo-1', name: '宁夏银川光伏电站_2025年数据', format: 'csv', size: '8.5 MB', rows: 35040, columns: 7, tags: ['光伏', '功率预测', '气象', '示例'], source: '宁夏银川光伏电站', status: 'ready', version: 1, createdAt: '2025-01-01', updatedAt: '2026-03-21', description: '10MW光伏电站2025年全年数据，15分钟间隔，包含辐照度、温度、湿度、风速、云量和实际发电功率，用于光伏功率预测模型训练和验证', type: 'private' },
  // @AI_GENERATED: end
  { id: 'dat-1', name: '光伏发电历史数据_2025', format: 'csv', size: '45.2 MB', rows: 525600, columns: 12, tags: ['光伏', '时序', '发电量'], source: 'MySQL 生产数据库', status: 'ready', version: 3, createdAt: '2026-01-10', updatedAt: '2026-03-15', description: '2025年全年光伏电站15分钟粒度发电数据', type: 'private' },
  { id: 'dat-2', name: '气象站观测数据', format: 'csv', size: '28.7 MB', rows: 350400, columns: 8, tags: ['气象', '温度', '辐照度'], source: '气象数据 API', status: 'ready', version: 5, createdAt: '2026-01-15', updatedAt: '2026-03-18', description: '气象站温度、湿度、风速、辐照度等观测数据', type: 'private' },
  { id: 'dat-3', name: '储能电池SOC数据', format: 'excel', size: '12.3 MB', rows: 86400, columns: 15, tags: ['储能', 'SOC', '电池'], source: 'InfluxDB 时序库', status: 'ready', version: 2, createdAt: '2026-02-01', updatedAt: '2026-03-10', description: '储能电池组SOC、SOH、电压、电流等运行数据', type: 'private' },
  { id: 'dat-4', name: '钢铁连铸工艺参数', format: 'csv', size: '67.8 MB', rows: 1200000, columns: 25, tags: ['钢铁', '工艺', '质量'], source: 'NFS 文件共享', status: 'ready', version: 1, createdAt: '2026-02-20', updatedAt: '2026-02-20', description: '连铸生产线工艺参数与质量检测数据', type: 'private' },
  { id: 'dat-5', name: '设备振动信号采集', format: 'parquet', size: '156.4 MB', rows: 5000000, columns: 6, tags: ['振动', '设备', '故障诊断'], source: 'SCADA OPC-UA', status: 'ready', version: 4, createdAt: '2026-03-01', updatedAt: '2026-03-17', description: '旋转设备三轴振动加速度信号，采样率10kHz', type: 'private' },
  { id: 'dat-6', name: '电网负荷数据_华东', format: 'csv', size: '33.1 MB', rows: 420000, columns: 10, tags: ['电网', '负荷', '预测'], source: 'MySQL 生产数据库', status: 'processing', version: 1, createdAt: '2026-03-18', updatedAt: '2026-03-18', description: '华东区域电网小时级负荷数据，正在导入中', type: 'private' },
  { id: 'dat-7', name: '光伏组件EL图像标注', format: 'json', size: '8.5 MB', rows: 15000, columns: 4, tags: ['光伏', '缺陷', '图像'], source: 'MinIO 对象存储', status: 'ready', version: 2, createdAt: '2026-03-05', updatedAt: '2026-03-16', description: 'EL图像缺陷标注数据（裂纹、黑斑、断栅）', type: 'private' },
];

const formatIcon = (f: string) => {
  if (f === 'excel') return <FileExcelOutlined style={{ color: '#52c41a' }} />;
  return <FileTextOutlined style={{ color: '#1890ff' }} />;
};

const formatColor = (f: string) => {
  const map: Record<string, string> = { csv: 'blue', excel: 'green', json: 'orange', parquet: 'purple' };
  return map[f] || 'default';
};

const industryColor = (industry: string) => {
  const map: Record<string, string> = {
    '新能源': '#faad14', '工业制造': '#722ed1', '源网荷储': '#1890ff',
    '碳管理': '#389e0d', '楼宇园区': '#a0d911', '港口运输': '#fa8c16', '通用工业': '#2f54eb',
  };
  return map[industry] || '#999';
};

const DatasetPage: React.FC = () => {
  const navigate = useNavigate();
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [opensourceDatasets] = useState<Dataset[]>(OPENSOURCE_DATASETS);
  const [privateDatasets, setPrivateDatasets] = useState<Dataset[]>(PRIVATE_DATASETS);
  const [activeTab, setActiveTab] = useState<string>(() => (
    new URLSearchParams(window.location.search).get('tab') === 'private' ? 'private' : 'opensource'
  ));
  const [search, setSearch] = useState('');
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [industryFilter, setIndustryFilter] = useState<string | null>(null);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  const currentDatasets = activeTab === 'opensource' ? opensourceDatasets : privateDatasets;
  const allTags = Array.from(new Set(currentDatasets.flatMap((d) => d.tags)));
  const allIndustries = Array.from(new Set(opensourceDatasets.map((d) => d.industry).filter(Boolean)));

  const filtered = currentDatasets.filter((d) => {
    const matchSearch = !search || d.name.toLowerCase().includes(search.toLowerCase()) || d.description.toLowerCase().includes(search.toLowerCase());
    const matchTag = !tagFilter || d.tags.includes(tagFilter);
    const matchIndustry = !industryFilter || d.industry === industryFilter;
    return matchSearch && matchTag && matchIndustry;
  });

  const handleDelete = (id: string) => {
    setPrivateDatasets((prev) => prev.filter((d) => d.id !== id));
    message.success(t('dataset.deleted'));
  };

  const previewDataset = currentDatasets.find((d) => d.id === previewId);

  const opensourceColumns = [
    {
      title: t('dataset.datasetName'), dataIndex: 'name', key: 'name', width: 280,
      render: (name: string) => (
        <Space><GlobalOutlined style={{ color: '#1890ff' }} /><Text strong>{name}</Text></Space>
      ),
    },
    {
      title: t('dataset.industry'), dataIndex: 'industry', key: 'industry', width: 100,
      render: (industry: string) => <Tag color={industryColor(industry)}>{td(industry)}</Tag>,
    },
    {
      title: t('dataset.format'), dataIndex: 'format', key: 'format', width: 80,
      render: (f: string) => <Tag color={formatColor(f)}>{f.toUpperCase()}</Tag>,
    },
    { title: t('dataset.size'), dataIndex: 'size', key: 'size', width: 100 },
    {
      title: t('dataset.dataScale'), key: 'shape', width: 120,
      render: (_: unknown, r: Dataset) => <Text type="secondary">{r.rows.toLocaleString()} {t('dataset.rows')}</Text>,
    },
    {
      title: t('dataset.tags'), dataIndex: 'tags', key: 'tags', width: 200,
      render: (tags: string[]) => tags.slice(0, 3).map((tg) => <Tag key={tg} style={{ fontSize: 11 }}>{td(tg)}</Tag>),
    },
    {
      title: t('dataset.license'), dataIndex: 'license', key: 'license', width: 120,
      render: (license: string) => <Text type="secondary" style={{ fontSize: 12 }}>{license}</Text>,
    },
    {
      title: t('dataset.actions'), key: 'action', width: 150,
      render: (_: unknown, record: Dataset) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => setPreviewId(record.id)}>{t('dataset.detailBtn')}</Button>
          <Button size="small" type="primary" icon={<CloudDownloadOutlined />} onClick={() => window.open(record.downloadUrl, '_blank')}>{t('dataset.getBtn')}</Button>
        </Space>
      ),
    },
  ];

  const privateColumns = [
    {
      title: t('dataset.datasetName'), dataIndex: 'name', key: 'name',
      render: (name: string, record: Dataset) => (
        <Space><LockOutlined style={{ color: '#722ed1' }} />{formatIcon(record.format)}<Text strong>{td(name)}</Text></Space>
      ),
    },
    {
      title: t('dataset.format'), dataIndex: 'format', key: 'format',
      render: (f: string) => <Tag color={formatColor(f)}>{f.toUpperCase()}</Tag>,
    },
    { title: t('dataset.size'), dataIndex: 'size', key: 'size' },
    {
      title: t('dataset.rows') + '/' + t('dataset.detailColumns'), key: 'shape',
      render: (_: unknown, r: Dataset) => <Text type="secondary">{r.rows.toLocaleString()} × {r.columns}</Text>,
    },
    {
      title: t('dataset.tags'), dataIndex: 'tags', key: 'tags',
      render: (tags: string[]) => tags.map((tg) => <Tag key={tg} style={{ fontSize: 11 }}>{td(tg)}</Tag>),
    },
    {
      title: t('dataset.statusReady'), dataIndex: 'status', key: 'status',
      render: (s: string) => (
        <Badge status={s === 'ready' ? 'success' : s === 'processing' ? 'processing' : 'error'}
          text={s === 'ready' ? t('dataset.statusReady') : s === 'processing' ? t('dataset.statusProcessing') : t('dataset.statusError')} />
      ),
    },
    {
      title: t('dataset.versionCol'), dataIndex: 'version', key: 'version',
      render: (v: number) => <Tag>v{v}</Tag>,
    },
    {
      title: t('dataset.actions'), key: 'action',
      render: (_: unknown, record: Dataset) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => setPreviewId(record.id)}>{t('dataset.detailBtn')}</Button>
          <Button size="small" icon={<DownloadOutlined />} onClick={() => message.info(t('dataset.downloadDev'))}>{t('dataset.downloadBtn')}</Button>
          <Popconfirm title={t('dataset.confirmDelete')} onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const opensourceStats = {
    total: opensourceDatasets.length,
    industries: allIndustries.length,
    totalSize: '17.5 GB',
  };

  const privateStats = {
    total: privateDatasets.length,
    ready: privateDatasets.filter((d) => d.status === 'ready').length,
    totalRows: privateDatasets.reduce((sum, d) => sum + d.rows, 0),
  };

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={4} style={{ margin: 0 }}>{t('dataset.title')}</Title>
        <Space>
          <Button type="default" onClick={() => navigate('/iterative-labeling')}>
            人工标注工作台
          </Button>
          <Button type="primary" icon={<UploadOutlined />} onClick={() => setUploadOpen(true)}>{t('dataset.upload')}</Button>
        </Space>
      </Space>

      <Tabs
        activeKey={activeTab}
        onChange={(key) => { setActiveTab(key); setSearch(''); setTagFilter(null); setIndustryFilter(null); }}
        items={[
          {
            key: 'opensource',
            label: <Space><GlobalOutlined />{t('dataset.opensourceTab')}</Space>,
            children: (
              <>
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={6}><Card size="small"><Statistic title={t('dataset.opensourceDatasets')} value={opensourceStats.total} prefix={<GlobalOutlined />} /></Card></Col>
                  <Col span={6}><Card size="small"><Statistic title={t('dataset.coveredIndustries')} value={opensourceStats.industries} suffix={t('common.unit')} /></Card></Col>
                  <Col span={6}><Card size="small"><Statistic title={t('dataset.totalDataSize')} value={opensourceStats.totalSize} /></Card></Col>
                  <Col span={6}><Card size="small"><Statistic title={t('dataset.availableForValidation')} value={opensourceStats.total} suffix={t('common.unit')} valueStyle={{ color: '#52c41a' }} /></Card></Col>
                </Row>
                <Space style={{ marginBottom: 12 }}>
                  <Input prefix={<SearchOutlined />} placeholder={t('dataset.searchPlaceholder')} value={search}
                    onChange={(e) => setSearch(e.target.value)} style={{ width: 240 }} allowClear />
                  <Select placeholder={t('dataset.filterByIndustry')} value={industryFilter} onChange={setIndustryFilter}
                    allowClear style={{ width: 140 }}
                    options={allIndustries.map((i) => ({ value: i, label: td(i!) }))} />
                  <Select placeholder={t('dataset.filterByTag')} value={tagFilter} onChange={setTagFilter}
                    allowClear style={{ width: 140 }}
                    options={allTags.map((tg) => ({ value: tg, label: td(tg) }))} />
                </Space>
                <Table dataSource={filtered} columns={opensourceColumns} rowKey="id" size="small"
                  pagination={{ pageSize: 10, showTotal: (total) => t('dataset.opensourceTotal', { count: total }) }} />
              </>
            ),
          },
          {
            key: 'private',
            label: <Space><LockOutlined />{t('dataset.privateTab')}</Space>,
            children: (
              <>
                {/* @AI_GENERATED: 光伏累计训练数据集 — 真实 API 驱动的训练集扩充入口 */}
                <PvTrainingDatasetCard />
                {/* @AI_GENERATED: end */}
                <Row gutter={16} style={{ marginBottom: 16 }}>
                  <Col span={6}><Card size="small"><Statistic title={t('dataset.privateDatasets')} value={privateStats.total} prefix={<LockOutlined />} /></Card></Col>
                  <Col span={6}><Card size="small"><Statistic title={t('dataset.ready')} value={privateStats.ready} valueStyle={{ color: '#52c41a' }} /></Card></Col>
                  <Col span={6}><Card size="small"><Statistic title={t('dataset.totalRows')} value={(privateStats.totalRows / 1000000).toFixed(1)} suffix="M" valueStyle={{ color: '#1890ff' }} /></Card></Col>
                  <Col span={6}><Card size="small"><Statistic title={t('dataset.processing')} value={privateStats.total - privateStats.ready} valueStyle={{ color: '#faad14' }} /></Card></Col>
                </Row>
                <Space style={{ marginBottom: 12 }}>
                  <Input prefix={<SearchOutlined />} placeholder={t('dataset.searchPlaceholder')} value={search}
                    onChange={(e) => setSearch(e.target.value)} style={{ width: 240 }} allowClear />
                  <Select placeholder={t('dataset.filterByTag')} value={tagFilter} onChange={setTagFilter}
                    allowClear style={{ width: 160 }}
                    options={allTags.map((tg) => ({ value: tg, label: td(tg) }))} />
                </Space>
                <Table dataSource={filtered} columns={privateColumns} rowKey="id" size="small"
                  pagination={{ pageSize: 10, showTotal: (total) => t('dataset.privateTotal', { count: total }) }} />
              </>
            ),
          },
        ]}
      />

      <Modal title={t('dataset.detailTitle')} open={!!previewId} onCancel={() => setPreviewId(null)} footer={null} width={650}>
        {previewDataset && (
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label={t('dataset.detailName')} span={2}>{previewDataset.name}</Descriptions.Item>
            <Descriptions.Item label={t('dataset.detailType')}>
              {previewDataset.type === 'opensource' 
                ? <Tag icon={<GlobalOutlined />} color="blue">{t('dataset.opensourceType')}</Tag>
                : <Tag icon={<LockOutlined />} color="purple">{t('dataset.privateType')}</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label={t('dataset.detailFormat')}><Tag color={formatColor(previewDataset.format)}>{previewDataset.format.toUpperCase()}</Tag></Descriptions.Item>
            {previewDataset.industry && <Descriptions.Item label={t('dataset.detailIndustry')}><Tag color={industryColor(previewDataset.industry)}>{td(previewDataset.industry)}</Tag></Descriptions.Item>}
            <Descriptions.Item label={t('dataset.detailSize')}>{previewDataset.size}</Descriptions.Item>
            <Descriptions.Item label={t('dataset.detailRows')}>{previewDataset.rows.toLocaleString()}</Descriptions.Item>
            <Descriptions.Item label={t('dataset.detailColumns')}>{previewDataset.columns}</Descriptions.Item>
            <Descriptions.Item label={t('dataset.detailSource')} span={2}>{td(previewDataset.source)}</Descriptions.Item>
            {previewDataset.license && <Descriptions.Item label={t('dataset.detailLicense')}>{previewDataset.license}</Descriptions.Item>}
            <Descriptions.Item label={t('dataset.detailVersion')}>v{previewDataset.version}</Descriptions.Item>
            <Descriptions.Item label={t('dataset.detailTags')} span={2}>{previewDataset.tags.map((tg) => <Tag key={tg}>{td(tg)}</Tag>)}</Descriptions.Item>
            <Descriptions.Item label={t('dataset.detailDesc')} span={2}>{td(previewDataset.description)}</Descriptions.Item>
            <Descriptions.Item label={t('dataset.detailCreatedAt')}>{previewDataset.createdAt}</Descriptions.Item>
            <Descriptions.Item label={t('dataset.detailUpdatedAt')}>{previewDataset.updatedAt}</Descriptions.Item>
            {previewDataset.downloadUrl && (
              <Descriptions.Item label={t('dataset.detailDownloadUrl')} span={2}>
                <a href={previewDataset.downloadUrl} target="_blank" rel="noopener noreferrer">{previewDataset.downloadUrl}</a>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>

      <Modal title={t('dataset.uploadTitle')} open={uploadOpen} onCancel={() => setUploadOpen(false)}
        onOk={() => { setUploadOpen(false); message.success(t('dataset.uploadDev')); }} okText={t('dataset.uploadOk')} cancelText={t('dataset.uploadCancel')}>
        <Upload.Dragger accept=".csv,.xlsx,.xls,.json,.parquet"
          beforeUpload={() => { message.info(t('dataset.uploadDev')); return false; }}>
          <p style={{ fontSize: 32, color: '#1890ff' }}><UploadOutlined /></p>
          <p>{t('dataset.uploadHint')}</p>
          <p style={{ color: '#999', fontSize: 12 }}>{t('dataset.uploadFormats')}</p>
        </Upload.Dragger>
      </Modal>
    </div>
  );
};

// @AI_GENERATED: 光伏累计训练数据集卡片 — 真实 API 驱动，提供训练集扩充入口
const PvTrainingDatasetCard: React.FC = () => {
  const navigate = useNavigate();
  const [state, setState] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [uploadPath, setUploadPath] = useState('');
  const [uploadSourceName, setUploadSourceName] = useState('');
  const [importing, setImporting] = useState(false);
  const [dbPullModalOpen, setDbPullModalOpen] = useState(false);
  const [dbPulling, setDbPulling] = useState(false);
  const [pulledData, setPulledData] = useState<{ hasLabel: boolean; total: number; items: any[] } | null>(null);
  const [admissionPreview, setAdmissionPreview] = useState<{
    columns: string[];
    rows: Array<Record<string, unknown>>;
    hasLabel: boolean;
  } | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [manualReviewLoading, setManualReviewLoading] = useState(false);
  const [clusteringLoading, setClusteringLoading] = useState(false);
  const [clusteringRun, setClusteringRun] = useState<Record<string, any> | null>(null);

  const loadState = useCallback(async () => {
    setLoading(true);
    try {
      const result = await cumulativeTrainingApi.getState('pv_fault');
      setState(result as Record<string, any>);
    } catch {
      setState(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadState(); }, [loadState]);

  const handleAnalyzeUpload = async () => {
    if (!uploadPath.trim()) { message.warning('请输入数据集路径'); return; }
    setAnalyzing(true);
    setClusteringRun(null);
    try {
      const response = await fetch(
        `/api/iterative-labeling/data-preview?file_path=${encodeURIComponent(uploadPath.trim())}&rows=20`,
      );
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || '数据集分析失败');
      }
      const result = await response.json();
      const columns = Array.isArray(result.columns) ? result.columns : [];
      setAdmissionPreview({
        columns,
        rows: Array.isArray(result.rows) ? result.rows : [],
        hasLabel: columns.includes('label'),
      });
    } catch (error: any) {
      setAdmissionPreview(null);
      message.error(error?.message || '数据集分析失败');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleImport = async () => {
    if (!uploadPath.trim()) { message.warning('请输入数据集路径'); return; }
    setImporting(true);
    try {
      const result = await cumulativeTrainingApi.registerImport(
        { datasetPath: uploadPath.trim(), sourceName: uploadSourceName.trim() || undefined },
        'pv_fault',
      );
      if ((result as any).imported === false) {
        message.info('该数据集已存在于累计训练集中（内容哈希相同）');
      } else {
        message.success('数据集已登记到累计训练集');
      }
      setUploadModalOpen(false);
      setUploadPath('');
      setUploadSourceName('');
      setAdmissionPreview(null);
      setClusteringRun(null);
      await loadState();
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.message || '导入失败';
      message.error(detail);
    } finally {
      setImporting(false);
    }
  };

  const handleManualReview = async () => {
    if (!uploadPath.trim()) return;
    setManualReviewLoading(true);
    try {
      const result = await trainingWorkspaceApi.createManualReviewFromDataset({
        dataset_path: uploadPath.trim(),
        slot: 'pv_fault',
        max_units: 500,
      });
      message.success(`已创建 ${result.total_count} 个待标注单元`);
      navigate(`/iterative-labeling/review?review_id=${encodeURIComponent(result.review_id)}&slot=pv_fault`);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '创建手工标注会话失败');
    } finally {
      setManualReviewLoading(false);
    }
  };

  const handleDatasetClustering = async () => {
    if (!uploadPath.trim()) return;
    setClusteringLoading(true);
    try {
      const result = await trainingWorkspaceApi.createClusteringRun({
        dataset_path: uploadPath.trim(),
        n_clusters: 5,
        label_status: 'all',
        page_size: 500,
      });
      setClusteringRun(result as Record<string, any>);
      message.success('聚类分析完成，请为各簇确认标签名称');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '聚类分析失败');
    } finally {
      setClusteringLoading(false);
    }
  };

  const handleConfirmClustering = async () => {
    const runId = String(clusteringRun?.run_id || '');
    if (!runId) return;
    setClusteringLoading(true);
    try {
      await trainingWorkspaceApi.confirmClusteringRun(runId);
      message.success('聚类标注结果已纳入累计训练集');
      setUploadModalOpen(false);
      setAdmissionPreview(null);
      setClusteringRun(null);
      setUploadPath('');
      await loadState();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '确认聚类结果失败');
    } finally {
      setClusteringLoading(false);
    }
  };

  const handleDbPull = async () => {
    setDbPulling(true);
    try {
      const result = await trainingWorkspaceApi.getTrainingCandidates({ page: 1, page_size: 50 });
      const items = result.items ?? [];
      const total = result.total ?? 0;
      // 判断有无 label
      const hasLabel = items.some((item: any) => item.label != null && item.label >= 0);
      setPulledData({ hasLabel, total, items });
      setDbPullModalOpen(true);
    } catch (err: any) {
      if (err?.response?.status === 503) {
        message.warning('PV 数据库未连接，无法从数据库拉取');
      } else {
        message.error('拉取失败');
      }
    } finally {
      setDbPulling(false);
    }
  };

  const handlePullDecision = () => {
    if (!pulledData) return;
    if (pulledData.hasLabel) {
      // 有真值，跳转到人工标注审核页面的"数据准入"Tab（可直接加入训练集）
      navigate('/iterative-labeling');
      message.info('已拉取到有标签数据，请在"数据准入"Tab 中确认加入训练集');
    } else {
      // 无真值，跳转到打标界面
      navigate('/iterative-labeling');
      message.info('拉取的数据无真值标签，请在"聚类标注"或"审核队列"中标注后加入训练集');
    }
    setDbPullModalOpen(false);
  };

  const snapshot = state?.latest_snapshot;
  const modelRef = state?.latest_completed_model_ref;
  const pendingCount = state?.pending_change_count ?? 0;
  const threshold = state?.retrain_label_threshold ?? 20;
  const progressPct = threshold > 0 ? Math.min(100, Math.round((pendingCount / threshold) * 100)) : 0;

  return (
    <Card
      size="small"
      style={{ marginBottom: 16, border: '1px solid #d9e8ff', background: '#f6faff' }}
      title={
        <Space>
          <ThunderboltOutlined style={{ color: '#1677ff' }} />
          <span style={{ fontWeight: 600 }}>光伏累计训练数据集</span>
          <Tag color="blue">pv_fault</Tag>
        </Space>
      }
      extra={
        <Space size={8}>
          <Button
            size="small"
            icon={<UploadOutlined />}
            onClick={() => {
              setAdmissionPreview(null);
              setClusteringRun(null);
              setUploadModalOpen(true);
            }}
          >
            上传扩充
          </Button>
          <Button size="small" type="primary" icon={<DatabaseOutlined />} loading={dbPulling} onClick={handleDbPull}>
            从数据库拉取
          </Button>
        </Space>
      }
      loading={loading && !state}
    >
      <Row gutter={[16, 8]}>
        <Col xs={12} sm={6}>
          <div style={{ fontSize: 12, color: '#64748b' }}>当前模型</div>
          <div style={{ fontWeight: 500, fontSize: 13 }}>{modelRef ? <Tag color="success" style={{ margin: 0 }}>{modelRef}</Tag> : <Tag>待训练</Tag>}</div>
        </Col>
        <Col xs={12} sm={6}>
          <div style={{ fontSize: 12, color: '#64748b' }}>有效真值</div>
          <div style={{ fontWeight: 500 }}>{state?.effective_labeled_unit_count ?? 0} 单元</div>
        </Col>
        <Col xs={12} sm={6}>
          <div style={{ fontSize: 12, color: '#64748b' }}>快照样本</div>
          <div style={{ fontWeight: 500 }}>{snapshot?.sample_count?.toLocaleString() ?? '—'}</div>
        </Col>
        <Col xs={12} sm={6}>
          <div style={{ fontSize: 12, color: '#64748b' }}>重训进度</div>
          <Progress percent={progressPct} size="small" format={() => `${pendingCount}/${threshold}`} style={{ marginBottom: 0 }} />
        </Col>
      </Row>
      {state?.retrain_blocker && (
        <Alert type="warning" showIcon style={{ marginTop: 8 }} message={state.retrain_blocker} />
      )}
      <Alert
        type="info"
        showIcon
        style={{ marginTop: 12 }}
        message="累计训练集扩充流程"
        description="上传或选择数据集 → 数据准入预览与字段分析 → 有标签数据直接入账；无标签数据选择聚类标注或进入人工打标工作台。"
      />

      {/* 上传扩充弹窗 */}
      <Modal
        title="数据准入与累计训练集扩充"
        open={uploadModalOpen}
        width={960}
        onCancel={() => setUploadModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setUploadModalOpen(false)}>取消</Button>,
          <Button key="analyze" loading={analyzing} onClick={handleAnalyzeUpload}>分析数据集</Button>,
          ...(admissionPreview?.hasLabel ? [
            <Button key="import" type="primary" loading={importing} onClick={handleImport}>
              确认纳入累计训练集
            </Button>,
          ] : admissionPreview ? [
            <Button key="cluster" icon={<ClusterOutlined />} loading={clusteringLoading} onClick={handleDatasetClustering}>
              聚类标注
            </Button>,
            <Button key="manual" type="primary" icon={<EditOutlined />} loading={manualReviewLoading} onClick={handleManualReview}>
              手工标注
            </Button>,
          ] : []),
        ]}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <div style={{ marginBottom: 4, fontSize: 13 }}>数据集路径（相对于项目根目录）</div>
            <Input
              placeholder="例如：backend-service/datasets/dataset_combined.parquet"
              value={uploadPath}
              onChange={(e) => {
                setUploadPath(e.target.value);
                setAdmissionPreview(null);
                setClusteringRun(null);
              }}
            />
          </div>
          <div>
            <div style={{ marginBottom: 4, fontSize: 13 }}>来源说明（可选）</div>
            <Input
              placeholder="例如：2026年7月数据库导出"
              value={uploadSourceName}
              onChange={(e) => setUploadSourceName(e.target.value)}
            />
          </div>
          <Alert
            type="info"
            showIcon
            message="先分析，后决定准入方式"
            description="系统会展示前 20 行、识别字段及 label 列。有真值可直接纳入；无真值可聚类批量标注，或进入原有逐单元人工打标界面。"
          />
          {admissionPreview && (
            <>
              <Alert
                type={admissionPreview.hasLabel ? 'success' : 'warning'}
                showIcon
                message={admissionPreview.hasLabel ? '检测到 label 列，可直接准入' : '未检测到 label 列，需要先完成标注'}
                description={`识别到 ${admissionPreview.columns.length} 个字段，当前展示 ${admissionPreview.rows.length} 行样本。`}
              />
              <Table
                dataSource={admissionPreview.rows.map((row, index) => ({ ...row, __key: index }))}
                columns={admissionPreview.columns.map((column) => ({
                  title: column,
                  dataIndex: column,
                  key: column,
                  width: 130,
                  ellipsis: true,
                  render: (value: unknown) => value === null || value === undefined || value === '' ? '—' : String(value),
                }))}
                rowKey="__key"
                size="small"
                pagination={false}
                scroll={{ x: 'max-content', y: 260 }}
              />
            </>
          )}
          {clusteringRun && (
            <Card size="small" title={`聚类结果 · ${clusteringRun.total_members ?? 0} 个诊断片段`}>
              <Row gutter={[12, 12]}>
                {Object.entries(clusteringRun.clusters || {}).map(([clusterId, cluster]: [string, any]) => (
                  <Col xs={24} md={12} key={clusterId}>
                    <Card
                      size="small"
                      title={<Space><Tag color="geekblue">簇 {clusterId}</Tag><Text>{cluster.member_count} 个成员</Text></Space>}
                    >
                      <Input
                        size="small"
                        placeholder="输入标签名称，如：组串遮挡"
                        defaultValue={cluster.proposed_label_name || ''}
                        onBlur={async (event) => {
                          const labelName = event.target.value.trim();
                          if (!labelName) return;
                          try {
                            const updated = await trainingWorkspaceApi.updateCluster(
                              String(clusteringRun.run_id),
                              clusterId,
                              { proposed_label_name: labelName },
                            );
                            setClusteringRun(updated as Record<string, any>);
                          } catch (error: any) {
                            message.error(error?.response?.data?.detail || '簇命名失败');
                          }
                        }}
                        addonBefore="标签"
                      />
                    </Card>
                  </Col>
                ))}
              </Row>
              <div style={{ marginTop: 12, textAlign: 'right' }}>
                <Button
                  type="primary"
                  icon={<CheckCircleOutlined />}
                  loading={clusteringLoading}
                  onClick={handleConfirmClustering}
                >
                  确认标注并纳入训练集
                </Button>
              </div>
            </Card>
          )}
        </Space>
      </Modal>

      {/* 数据库拉取结果判断弹窗 */}
      <Modal
        title="数据库拉取结果"
        open={dbPullModalOpen}
        onCancel={() => setDbPullModalOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setDbPullModalOpen(false)}>取消</Button>,
          <Button key="go" type="primary" onClick={handlePullDecision}>
            {pulledData?.hasLabel ? '确认加入训练集' : '去标注'}
          </Button>,
        ]}
      >
        {pulledData && (
          <Space direction="vertical" size={8}>
            <div>共拉取到 <strong>{pulledData.total}</strong> 条候选观测</div>
            {pulledData.hasLabel ? (
              <Alert type="success" showIcon message="检测到部分数据已有标签，可直接确认加入累计训练集" />
            ) : (
              <Alert type="warning" showIcon message="拉取的数据均无真值标签（label=NULL），需要先标注" description="将跳转到人工标注审核页面，您可以选择聚类批量标注或逐条审核标注。" />
            )}
          </Space>
        )}
      </Modal>
    </Card>
  );
};
// @AI_GENERATED: end

export default DatasetPage;
// @AI_GENERATED: end
