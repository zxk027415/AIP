// @AI_GENERATED: Kiro v1.0
/**
 * 数据集管理页面
 * 管理开源数据集和私有数据集，支持预览、版本管理和标签
 * 开源数据集：各行业公开数据集，用于算法模板精度验证
 * 私有数据集：用户上传的私有数据
 */
import { useState } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Table, Button, Tag, Space, Typography, Modal, Upload, Input, Select, message,
  Popconfirm, Descriptions, Badge, Tabs, Row, Col, Statistic,
} from 'antd';
import {
  DeleteOutlined, EyeOutlined, DownloadOutlined,
  UploadOutlined, SearchOutlined, FileExcelOutlined, FileTextOutlined,
  GlobalOutlined, LockOutlined, CloudDownloadOutlined,
} from '@ant-design/icons';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
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
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [opensourceDatasets] = useState<Dataset[]>(OPENSOURCE_DATASETS);
  const [privateDatasets, setPrivateDatasets] = useState<Dataset[]>(PRIVATE_DATASETS);
  const [activeTab, setActiveTab] = useState<string>('opensource');
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
          <Button type="default" onClick={() => window.location.href = '/iterative-labeling/review?review_id=demo'}>
            迭代标注审核
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

export default DatasetPage;
// @AI_GENERATED: end
