// @AI_GENERATED: Kiro v1.0
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card, Typography, Tag, Space, Row, Col, Statistic, Grid, Input, Collapse,
} from 'antd';
import {
  SearchOutlined,
  RightOutlined,
  FunctionOutlined,
  AppstoreOutlined,
  FolderOutlined,
} from '@ant-design/icons';
import { BASIC_MODULE_CATEGORIES, LAYERS } from '../data/basicModuleCategories';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const { Text } = Typography;
const { useBreakpoint } = Grid;

/** 层级 → 分类映射 */
const LAYER_CATEGORY_MAP: Record<string, string[]> = {
  '数据管理层': ['data_source', 'dataset_management'],
  '数据处理层': ['data_preprocessing', 'feature_engineering'],
  '算法模型层': [
    'ts_forecast', 'anomaly_detection', 'classification', 'regression',
    'clustering', 'deep_learning', 'industrial_vision', 'signal_processing', 'optimization',
  ],
  '基础计算层': ['math_statistics'],
  'MLOps层': ['model_training', 'model_deployment', 'evaluation_metrics'],
  '输出展示层': ['visualization', 'data_output'],
};

const LAYER_COLORS: Record<string, string> = {
  '数据管理层': '#1890ff',
  '数据处理层': '#52c41a',
  '算法模型层': '#722ed1',
  '基础计算层': '#fa8c16',
  'MLOps层': '#eb2f96',
  '输出展示层': '#13c2c2',
};

const LAYER_ORDER = Object.keys(LAYER_CATEGORY_MAP);
const ALL_LAYERS_KEY = '__all_layers__';
const CHINESE_CHAR_RE = /[\u4e00-\u9fff]/;

const humanizeIdentifier = (value: string): string =>
  value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b[a-z]/g, (ch) => ch.toUpperCase());

/** category id → Category 对象 */
const catById = new Map(BASIC_MODULE_CATEGORIES.map(c => [c.id, c]));

const BasicModuleOverviewPage: React.FC = () => {
  const navigate = useNavigate();
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end

  const [selectedLayer, setSelectedLayer] = useState<string>(ALL_LAYERS_KEY);
  const [searchText, setSearchText] = useState('');

  const displayText = (text: string | null | undefined, fallbackId?: string): string => {
    const original = String(text ?? '');
    const translated = td(original);
    if ((i18n.language || '').toLowerCase().startsWith('zh')) return original;
    if (!translated || CHINESE_CHAR_RE.test(translated)) {
      return humanizeIdentifier(fallbackId || original);
    }
    return translated;
  };

  const allLayers = useMemo(() => [ALL_LAYERS_KEY, ...LAYERS.map(l => l.name)], []);

  /** 按搜索词过滤后的分类 */
  const filteredCatIds = useMemo(() => {
    if (!searchText.trim()) return null; // null = 不过滤
    const kw = searchText.trim().toLowerCase();
    return new Set(
      BASIC_MODULE_CATEGORIES
        .filter(c =>
          c.name.toLowerCase().includes(kw) ||
          c.description.toLowerCase().includes(kw) ||
          c.subCategories.some(s => s.toLowerCase().includes(kw)) ||
          displayText(c.name, c.id).toLowerCase().includes(kw) ||
          displayText(c.description, `${c.id}_desc`).toLowerCase().includes(kw) ||
          c.subCategories.some(s => displayText(s).toLowerCase().includes(kw))
        )
        .map(c => c.id)
    );
  }, [searchText]);

  const totalFunctions = useMemo(
    () => BASIC_MODULE_CATEGORIES.reduce((s, c) => s + c.functionCount, 0),
    [],
  );

  /** 构建要显示的层级列表 */
  const visibleLayers = selectedLayer === ALL_LAYERS_KEY ? LAYER_ORDER : [selectedLayer];

  /** 默认展开的层级 key */
  const defaultActiveKeys = visibleLayers;

  return (
    <div style={{ padding: isMobile ? '12px' : '24px', height: '100%', overflow: 'auto' }}>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {/* 统计栏 */}
        <Row gutter={[16, 16]}>
          <Col xs={8} sm={6} md={4}>
            <Card size="small">
              <Statistic title={t('basicModule.basicModules')} value={totalFunctions} suffix={t('basicModule.unit')} valueStyle={{ color: '#722ed1' }} prefix={<FunctionOutlined />} />
            </Card>
          </Col>
          <Col xs={8} sm={6} md={4}>
            <Card size="small">
              <Statistic title={t('basicModule.techCategories')} value={BASIC_MODULE_CATEGORIES.length} suffix={t('basicModule.unit')} valueStyle={{ color: '#1890ff' }} prefix={<AppstoreOutlined />} />
            </Card>
          </Col>
          <Col xs={8} sm={6} md={4}>
            <Card size="small">
              <Statistic title={t('basicModule.techLayers')} value={6} suffix={t('basicModule.layerUnit')} valueStyle={{ color: '#52c41a' }} />
            </Card>
          </Col>
        </Row>

        {/* 搜索和层级筛选 */}
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Input
            placeholder={t('basicModule.searchCategoryPlaceholder')}
            prefix={<SearchOutlined />}
            allowClear
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            style={{ maxWidth: 400 }}
          />
          <Space wrap>
            {allLayers.map(layer => {
              const layerInfo = LAYERS.find(l => l.name === layer);
              const isSelected = selectedLayer === layer;
              return (
                <Tag.CheckableTag
                  key={layer}
                  checked={isSelected}
                  onChange={() => setSelectedLayer(layer)}
                  style={{
                    padding: '4px 12px',
                    fontSize: '13px',
                    borderRadius: 4,
                    border: `1px solid ${isSelected ? (layerInfo?.color || '#1890ff') : '#d9d9d9'}`,
                  }}
                >
                  {layer === ALL_LAYERS_KEY ? t('basicModule.allLayers') : displayText(layer, layer)}
                  {layer !== ALL_LAYERS_KEY && layerInfo && ` (${layerInfo.functionCount})`}
                </Tag.CheckableTag>
              );
            })}
          </Space>
        </Space>

        {/* L1 → L2 → L3 层级展示 */}
        <Collapse
          defaultActiveKey={defaultActiveKeys}
          style={{ background: '#fff' }}
          items={visibleLayers.map(layerName => {
            const color = LAYER_COLORS[layerName] || '#999';
            const catIds = LAYER_CATEGORY_MAP[layerName] || [];
            const cats = catIds
              .map(id => catById.get(id))
              .filter((c): c is NonNullable<typeof c> => !!c)
              .filter(c => !filteredCatIds || filteredCatIds.has(c.id));

            if (cats.length === 0) return null;

            const layerTotal = cats.reduce((s, c) => s + c.functionCount, 0);

            return {
              key: layerName,
              label: (
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <FolderOutlined style={{ color, fontSize: 17 }} />
                  <span style={{ fontWeight: 600, fontSize: 15, color }}>
                    {displayText(layerName, layerName)}
                  </span>
                  <span style={{ fontSize: 12, fontWeight: 400, color: '#999' }}>
                    {cats.length} {t('basicModule.categoriesCount')} · {layerTotal} {t('basicModule.functionsCount')}
                  </span>
                </span>
              ),
              children: (
                <Row gutter={[12, 12]}>
                  {cats.map(cat => (
                    <Col xs={24} sm={12} md={8} lg={6} key={cat.id}>
                      <Card
                        hoverable
                        size="small"
                        onClick={() => navigate(`/basic-modules/${cat.id}`)}
                        style={{ borderLeft: `3px solid ${color}`, height: '100%' }}
                        styles={{ body: { padding: '12px 16px' } }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                          <span style={{ fontSize: 24 }}>{cat.icon}</span>
                          <div style={{ flex: 1 }}>
                            <Text strong style={{ fontSize: 14, color }}>{displayText(cat.name, cat.id)}</Text>
                            <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                              {cat.functionCount} {t('basicModule.functionsUnit')}
                            </Text>
                          </div>
                          <RightOutlined style={{ color: '#ccc', fontSize: 12 }} />
                        </div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {cat.subCategories.slice(0, 4).map(sc => displayText(sc)).join(' · ')}
                          {cat.subCategories.length > 4 ? ' ...' : ''}
                        </Text>
                      </Card>
                    </Col>
                  ))}
                </Row>
              ),
            };
          }).filter(Boolean) as any[]}
        />
      </Space>
    </div>
  );
};

export default BasicModuleOverviewPage;
// @AI_GENERATED: end
