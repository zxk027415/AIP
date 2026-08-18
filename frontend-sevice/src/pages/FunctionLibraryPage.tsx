// @AI_GENERATED: Kiro v1.0
import { useState, useMemo, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Typography, Tag, Space, Row, Col, Input, Grid, Statistic,
  Empty, Button, Collapse, Tooltip, Badge, Modal, message, Segmented,
} from 'antd';
import {
  SearchOutlined,
  FunctionOutlined,
  AppstoreOutlined,
  RightOutlined,
  RocketOutlined,
  FilterOutlined,
  FolderOutlined,
  ApartmentOutlined,
  PlayCircleOutlined,
} from '@ant-design/icons';
import { BASIC_MODULE_CATEGORIES, LAYERS } from '../data/basicModuleCategories';
import BASIC_MODULE_FUNCTIONS from '../data/basicModuleFunctions';
import type { BasicModuleSubCategory, BasicModuleFunction } from '../data/basicModuleFunctions';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import FunctionExecutor from '../components/FunctionExecutor';
import type { FunctionDefinition } from '../types/function';
// @AI_GENERATED
import useBackendReadyOperators from '../hooks/useBackendReadyOperators';
// @AI_GENERATED: end
// @AI_GENERATED: operator detail modal
import OperatorDetailModal from '../components/OperatorDetailModal';
import { FileSearchOutlined } from '@ant-design/icons';
// @AI_GENERATED: end

const { Text, Paragraph } = Typography;
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
const catById = new Map(BASIC_MODULE_CATEGORIES.map(c => [c.id, c]));
const ALL_LAYERS_KEY = '__all_layers__';
const CHINESE_CHAR_RE = /[\u4e00-\u9fff]/;

const humanizeIdentifier = (value: string): string =>
  value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b[a-z]/g, (ch) => ch.toUpperCase());

const normalizeLayerParam = (layerParam: string | null, allLayersLabel: string): string => {
  if (!layerParam || layerParam === allLayersLabel || layerParam === '全部' || layerParam === ALL_LAYERS_KEY) {
    return ALL_LAYERS_KEY;
  }
  return layerParam;
};

// @AI_GENERATED: Kiro v1.0
import { DataType } from '../types/data';

// 将 BasicModuleFunction 转换为 FunctionDefinition 以供 FunctionExecutor 使用
const convertToFunctionDefinition = (fn: BasicModuleFunction): FunctionDefinition => ({
  id: fn.id,
  name: fn.name,
  description: fn.description,
  category: '',
  parameters: [],
  returnType: DataType.ANY,
  return_type: DataType.ANY,
  examples: [],
});
// @AI_GENERATED: end

const FunctionLibraryPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end

  // 从 URL 参数初始化状态
  const initialLayer = normalizeLayerParam(searchParams.get('layer'), t('functions.allLayers'));
  const initialCategory = searchParams.get('category') || null;
  const initialSearch = searchParams.get('q') || '';
  const executeMode = searchParams.get('execute') === 'true';

  const [searchText, setSearchText] = useState(initialSearch);
  const [selectedLayer, setSelectedLayer] = useState<string>(initialLayer);
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(initialCategory);
  
  // @AI_GENERATED: Kiro v1.0
  // 执行模态框状态
  const [executeModalVisible, setExecuteModalVisible] = useState(false);
  const [selectedFunction, setSelectedFunction] = useState<BasicModuleFunction | null>(null);
  // @AI_GENERATED: end

  // @AI_GENERATED: operator detail modal
  // 详情模态框状态
  const [detailModalVisible, setDetailModalVisible] = useState(false);
  const [detailFunction, setDetailFunction] = useState<BasicModuleFunction | null>(null);
  // @AI_GENERATED: end

  // @AI_GENERATED
  // 后端可执行 / 已验证状态 — readySet / verifiedSet 为空表示 API 未返回（加载中或出错）
  const {
    readySet,
    verifiedSet,
    loading: backendLoading,
    error: backendError,
  } = useBackendReadyOperators();
  // 筛选：全部 | 已验证 | 可执行未验证 | 仅定义
  const [backendFilter, setBackendFilter] = useState<
    'all' | 'verified' | 'ready-unverified' | 'definition-only'
  >('all');
  // @AI_GENERATED: end

  const displayText = (text: string | null | undefined, fallbackId?: string): string => {
    const original = String(text ?? '');
    const translated = td(original);
    if ((i18n.language || '').toLowerCase().startsWith('zh')) return original;
    if (!translated || CHINESE_CHAR_RE.test(translated)) {
      return humanizeIdentifier(fallbackId || original);
    }
    return translated;
  };

  const displayFunctionName = (fn: BasicModuleFunction): string => displayText(fn.name, fn.id);
  const displayFunctionDesc = (fn: BasicModuleFunction): string => displayText(fn.description, `${fn.id}_desc`);

  // 同步 URL 参数
  useEffect(() => {
    const params = new URLSearchParams();
    if (selectedLayer !== ALL_LAYERS_KEY) params.set('layer', selectedLayer);
    if (selectedCategoryId) params.set('category', selectedCategoryId);
    if (searchText.trim()) params.set('q', searchText.trim());
    setSearchParams(params, { replace: true });
  }, [selectedLayer, selectedCategoryId, searchText, setSearchParams]);

  // 语言切换后，确保“全部层级”保持稳定 key，不受翻译文案变化影响
  useEffect(() => {
    if (selectedLayer === t('functions.allLayers') || selectedLayer === '全部') {
      setSelectedLayer(ALL_LAYERS_KEY);
    }
  }, [selectedLayer, t]);
  
  // @AI_GENERATED: Kiro v1.0
  // 处理 execute=true 参数，自动打开第一个匹配函数的执行模态框
  useEffect(() => {
    if (executeMode && initialSearch) {
      // 搜索匹配的函数
      const kw = initialSearch.toLowerCase();
      for (const catId of Object.keys(BASIC_MODULE_FUNCTIONS)) {
        const subs = BASIC_MODULE_FUNCTIONS[catId];
        if (!subs) continue;
        for (const sc of subs) {
          const matched = sc.functions.find(
            fn => fn.name.toLowerCase().includes(kw) ||
              fn.id.toLowerCase().includes(kw) ||
              fn.description.toLowerCase().includes(kw) ||
              displayFunctionName(fn).toLowerCase().includes(kw) ||
              displayFunctionDesc(fn).toLowerCase().includes(kw)
          );
          if (matched) {
            setSelectedFunction(matched);
            setExecuteModalVisible(true);
            message.info(t('functions.foundFunction', { name: displayFunctionName(matched) }));
            return;
          }
        }
      }
      message.warning(t('functions.notFound', { keyword: initialSearch }));
    }
  }, [executeMode, initialSearch]);
  // @AI_GENERATED: end

  const allLayers = useMemo(() => [ALL_LAYERS_KEY, ...LAYERS.map(l => l.name)], []);

  const visibleLayers = selectedLayer === ALL_LAYERS_KEY ? LAYER_ORDER : [selectedLayer];

  const selectedCategory = useMemo(
    () => BASIC_MODULE_CATEGORIES.find(c => c.id === selectedCategoryId),
    [selectedCategoryId],
  );

  const activeColor = selectedCategory?.layerColor || '#1890ff';

  // 当前分类下的子分类和函数（带搜索过滤）
  const displaySubCategories = useMemo((): BasicModuleSubCategory[] => {
    if (searchText.trim() && !selectedCategoryId) {
      const kw = searchText.trim().toLowerCase();
      const results: BasicModuleSubCategory[] = [];
      for (const catId of Object.keys(BASIC_MODULE_FUNCTIONS)) {
        const cat = catById.get(catId);
        if (selectedLayer !== ALL_LAYERS_KEY && cat && cat.layer !== selectedLayer) continue;
        const subs = BASIC_MODULE_FUNCTIONS[catId];
        if (!subs) continue;
        for (const sc of subs) {
          const matched = sc.functions.filter(
            fn => fn.name.toLowerCase().includes(kw) ||
              fn.id.toLowerCase().includes(kw) ||
              fn.description.toLowerCase().includes(kw),
          ).filter(
            fn =>
              displayFunctionName(fn).toLowerCase().includes(kw) ||
              displayFunctionDesc(fn).toLowerCase().includes(kw) ||
              fn.name.toLowerCase().includes(kw) ||
              fn.id.toLowerCase().includes(kw) ||
              fn.description.toLowerCase().includes(kw),
          );
          if (matched.length > 0) {
            results.push({
              subCategory: `${displayText(cat?.name || '', cat?.id)} › ${displayText(sc.subCategory)}`,
              functions: matched,
            });
          }
        }
      }
      return results;
    }
    if (!selectedCategoryId) return [];
    const subs = BASIC_MODULE_FUNCTIONS[selectedCategoryId];
    if (!subs) return [];
    if (!searchText.trim()) return subs;
    const kw = searchText.trim().toLowerCase();
    return subs
      .map(sc => ({
        ...sc,
        functions: sc.functions.filter(
          fn => fn.name.toLowerCase().includes(kw) ||
            fn.id.toLowerCase().includes(kw) ||
            fn.description.toLowerCase().includes(kw) ||
            displayFunctionName(fn).toLowerCase().includes(kw) ||
            displayFunctionDesc(fn).toLowerCase().includes(kw),
        ),
      }))
      .filter(sc => sc.functions.length > 0);
  }, [selectedCategoryId, searchText, selectedLayer]);

  const displayFunctionCount = useMemo(
    () => displaySubCategories.reduce((s, sc) => s + sc.functions.length, 0),
    [displaySubCategories],
  );

  // @AI_GENERATED
  // filteredSubCategories — applies backend-filter on top of search/category filtering
  const filteredSubCategories = useMemo(() => {
    if (backendFilter === 'all' || backendLoading || backendError) {
      return displaySubCategories;
    }
    return displaySubCategories
      .map(sc => ({
        ...sc,
        functions: sc.functions.filter(fn => {
          if (backendFilter === 'verified') return verifiedSet.has(fn.id);
          if (backendFilter === 'ready-unverified') {
            return readySet.has(fn.id) && !verifiedSet.has(fn.id);
          }
          return !readySet.has(fn.id);
        }),
      }))
      .filter(sc => sc.functions.length > 0);
  }, [displaySubCategories, backendFilter, readySet, verifiedSet, backendLoading, backendError]);

  const filteredFunctionCount = useMemo(
    () => filteredSubCategories.reduce((s, sc) => s + sc.functions.length, 0),
    [filteredSubCategories],
  );
  // @AI_GENERATED: end

  const totalFunctions = useMemo(
    () => BASIC_MODULE_CATEGORIES.reduce((s, c) => s + c.functionCount, 0),
    [],
  );

  // L1→L2 层级侧边栏
  const renderCategorySidebar = () => (
    <div style={{
      width: isMobile ? '100%' : 260,
      minWidth: isMobile ? undefined : 260,
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
    }}>
      {/* 层级筛选 */}
      <Card size="small" style={{ marginBottom: 8 }} styles={{ body: { padding: '8px' } }}>
        <div style={{ marginBottom: 6 }}>
          <Text type="secondary" style={{ fontSize: 12 }}><FilterOutlined /> {t('functions.techLayerFilter')}</Text>
        </div>
        <Space wrap size={[4, 4]}>
          {allLayers.map(layer => {
            const layerInfo = LAYERS.find(l => l.name === layer);
            const isSelected = selectedLayer === layer;
            return (
              <Tag.CheckableTag
                key={layer}
                checked={isSelected}
                onChange={() => { setSelectedLayer(layer); setSelectedCategoryId(null); }}
                style={{
                  fontSize: 11, padding: '2px 8px', borderRadius: 4,
                  border: `1px solid ${isSelected ? (layerInfo?.color || '#1890ff') : '#d9d9d9'}`,
                }}
              >
                {layer === ALL_LAYERS_KEY ? t('functions.allLayers') : td(layer)}
              </Tag.CheckableTag>
            );
          })}
        </Space>
      </Card>

      {/* L1→L2 层级树 */}
      <Card
        size="small"
        title={
          <Space>
            <AppstoreOutlined />
            <span style={{ fontSize: 13 }}>{t('functions.algorithmCategories')}</span>
          </Space>
        }
        style={{ flex: 1, display: 'flex', flexDirection: 'column' }}
        styles={{ body: { flex: 1, overflow: 'auto', padding: '4px 0' } }}
      >
        {visibleLayers.map(layerName => {
          const color = LAYER_COLORS[layerName] || '#999';
          const catIds = LAYER_CATEGORY_MAP[layerName] || [];
          const cats = catIds.map(id => catById.get(id)).filter(Boolean) as typeof BASIC_MODULE_CATEGORIES;
          const layerTotal = cats.reduce((s, c) => s + c.functionCount, 0);

          return (
            <div key={layerName} style={{ marginBottom: 4 }}>
              {/* L1 层级标题 */}
              <div style={{
                padding: '6px 12px',
                display: 'flex', alignItems: 'center', gap: 6,
                background: '#fafafa',
                borderBottom: '1px solid #f0f0f0',
              }}>
                <FolderOutlined style={{ color, fontSize: 15 }} />
                <span style={{ fontWeight: 600, fontSize: 14, color, flex: 1 }}>{td(layerName)}</span>
                <span style={{ fontSize: 11, color: '#999' }}>{layerTotal}</span>
              </div>
              {/* L2 分类列表 */}
              {cats.map(cat => {
                const isSelected = selectedCategoryId === cat.id;
                return (
                  <div
                    key={cat.id}
                    onClick={() => setSelectedCategoryId(isSelected ? null : cat.id)}
                    style={{
                      padding: '6px 12px 6px 28px',
                      cursor: 'pointer',
                      display: 'flex', alignItems: 'center', gap: 6,
                      background: isSelected ? `${color}10` : 'transparent',
                      borderLeft: isSelected ? `3px solid ${color}` : '3px solid transparent',
                      transition: 'all 0.15s',
                    }}
                    onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = '#fafafa'; }}
                    onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
                  >
                    <span style={{ fontSize: 16 }}>{cat.icon}</span>
                    <span style={{ flex: 1, fontSize: 13, fontWeight: isSelected ? 600 : 400, color }}>
                      {td(cat.name)}
                    </span>
                    <span style={{ fontSize: 11, color: '#999' }}>{cat.functionCount}</span>
                    <RightOutlined style={{ fontSize: 10, color: '#ccc' }} />
                  </div>
                );
              })}
            </div>
          );
        })}
      </Card>
    </div>
  );

  // 右侧内容区
  const renderFunctionContent = () => {
    if (!selectedCategoryId && !searchText.trim()) {
      return (
        <div style={{ padding: isMobile ? 12 : 24 }}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Row gutter={[12, 12]}>
              <Col xs={8}>
                <Card size="small">
                  <Statistic title={t('functions.basicModules')} value={totalFunctions} suffix={t('common.unit')} valueStyle={{ color: '#722ed1', fontSize: 20 }} prefix={<FunctionOutlined />} />
                </Card>
              </Col>
              <Col xs={8}>
                <Card size="small">
                  <Statistic title={t('functions.techCategories')} value={BASIC_MODULE_CATEGORIES.length} suffix={t('common.unit')} valueStyle={{ color: '#1890ff', fontSize: 20 }} prefix={<AppstoreOutlined />} />
                </Card>
              </Col>
              <Col xs={8}>
                <Card size="small">
                  <Statistic title={t('functions.techLayers')} value={6} suffix={t('functions.layers')} valueStyle={{ color: '#52c41a', fontSize: 20 }} />
                </Card>
              </Col>
            </Row>
            <Card size="small" title={t('functions.techLayerArchitecture')}>
              {LAYERS.map(layer => {
                const layerCats = BASIC_MODULE_CATEGORIES.filter(c => c.layer === layer.name);
                return (
                  <div key={layer.name} style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <Tag color={layer.color}>{displayText(layer.name, layer.name)}</Tag>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {t('functions.functionsCount', { count: layer.functionCount })} · {layerCats.length} {t('common.unit')}{t('functions.algorithmCategories')}
                      </Text>
                    </div>
                    <Space wrap size={[6, 6]}>
                      {layerCats.map(cat => (
                        <Tooltip key={cat.id} title={td(cat.description)}>
                          <Tag
                            style={{ cursor: 'pointer', padding: '2px 10px', fontSize: 12 }}
                            onClick={() => { setSelectedLayer(cat.layer); setSelectedCategoryId(cat.id); }}
                          >
                            {cat.icon} {displayText(cat.name, cat.id)}
                            <Badge count={cat.functionCount} size="small" style={{ marginLeft: 4, backgroundColor: layer.color }} />
                          </Tag>
                        </Tooltip>
                      ))}
                    </Space>
                  </div>
                );
              })}
            </Card>
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <Text type="secondary">← {t('functions.selectCategory')}</Text>
            </div>
          </Space>
        </div>
      );
    }

    const color = activeColor;

    return (
      <div style={{ padding: isMobile ? 12 : 16 }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          {selectedCategory && (
            <div style={{
              padding: '12px 16px',
              background: `${color}08`,
              borderLeft: `4px solid ${color}`,
              borderRadius: 4,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <Text strong style={{ fontSize: 16 }}>{selectedCategory.icon} {displayText(selectedCategory.name, selectedCategory.id)}</Text>
                  <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 0, marginTop: 4 }}>
                    {displayText(selectedCategory.description, `${selectedCategory.id}_desc`)}
                  </Paragraph>
                </div>
                <Space>
                  <Tag color={color}>{displayText(selectedCategory.layer, selectedCategory.layer)}</Tag>
                  <Tag color={color}>{t('functions.functionsCount', { count: displayFunctionCount })}</Tag>
                </Space>
              </div>
            </div>
          )}
          {!selectedCategory && searchText.trim() && (
            <Text type="secondary">{t('functions.searchResult', { keyword: searchText, count: filteredFunctionCount })}</Text>
          )}
          {filteredSubCategories.length > 0 ? (
            <Collapse
              defaultActiveKey={filteredSubCategories.map((_, i) => String(i))}
              ghost
              size="small"
              items={filteredSubCategories.map((sc, idx) => ({
                key: String(idx),
                label: (
                  <Space>
                    <Text strong style={{ fontSize: 14, color }}>{displayText(sc.subCategory)}</Text>
                    <Tag color={color} style={{ fontSize: 11 }}>{sc.functions.length} {t('common.unit')}</Tag>
                  </Space>
                ),
                children: (
                  <Row gutter={[8, 8]}>
                    {sc.functions.map(fn => (
                      <Col xs={24} sm={12} lg={8} key={fn.id}>
                        <Card size="small" hoverable style={{ borderLeft: `3px solid ${color}` }} styles={{ body: { padding: '10px 12px' } }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                            <div style={{ flex: 1, minWidth: 0 }}>
                              <Space size={4} wrap>
                                <Text strong style={{ fontSize: 13 }}>{displayFunctionName(fn)}</Text>
                                {/* @AI_GENERATED */}
                                {!backendLoading && !backendError && (
                                  verifiedSet.has(fn.id)
                                    ? <Tag color="success" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>{t('functions.badgeVerified')}</Tag>
                                    : readySet.has(fn.id)
                                      ? <Tag color="warning" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>{t('functions.badgeReadyUnverified')}</Tag>
                                      : <Tag color="default" style={{ fontSize: 10, lineHeight: '16px', padding: '0 4px' }}>{t('functions.badgeDefinitionOnly')}</Tag>
                                )}
                                {/* @AI_GENERATED: end */}
                              </Space>
                              <br />
                              <Text type="secondary" style={{ fontSize: 11 }}>{fn.id}</Text>
                              <Paragraph type="secondary" ellipsis={{ rows: 1 }} style={{ fontSize: 12, marginBottom: 0, marginTop: 2 }}>
                                {displayFunctionDesc(fn)}
                              </Paragraph>
                            </div>
                          </div>
                          <div style={{ marginTop: 8 }}>
                            <Space size={4}>
                              <Button size="small" type="primary" icon={<RocketOutlined />} onClick={e => { e.stopPropagation(); navigate('/workflow/editor'); }}>
                                {t('functions.algorithmTemplate')}
                              </Button>
                              {/* @AI_GENERATED: Kiro v1.0 */}
                              <Button size="small" icon={<PlayCircleOutlined />} onClick={e => { e.stopPropagation(); setSelectedFunction(fn); setExecuteModalVisible(true); }}>
                                {t('functions.execute')}
                              </Button>
                              {/* @AI_GENERATED: end */}
                              {/* @AI_GENERATED: operator detail modal */}
                              <Button
                                size="small"
                                icon={<FileSearchOutlined />}
                                onClick={e => { e.stopPropagation(); setDetailFunction(fn); setDetailModalVisible(true); }}
                              >
                                详情
                              </Button>
                              {/* @AI_GENERATED: end */}
                            </Space>
                          </div>
                        </Card>
                      </Col>
                    ))}
                  </Row>
                ),
              }))}
            />
          ) : (
            <Empty description={searchText.trim() ? t('functions.noMatch') : t('functions.noData')} />
          )}
        </Space>
      </div>
    );
  };

  // 移动端
  if (isMobile) {
    return (
      <div style={{ padding: 8, height: '100%', overflow: 'auto' }}>
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Input placeholder={t('functions.searchPlaceholder')} prefix={<SearchOutlined />} allowClear value={searchText} onChange={e => setSearchText(e.target.value)} />
          <Space wrap size={[4, 4]}>
            {allLayers.map(layer => {
              const layerInfo = LAYERS.find(l => l.name === layer);
              return (
                <Tag.CheckableTag key={layer} checked={selectedLayer === layer} onChange={() => { setSelectedLayer(layer); setSelectedCategoryId(null); }}
                  style={{ fontSize: 11, padding: '2px 8px', borderRadius: 4, border: `1px solid ${selectedLayer === layer ? (layerInfo?.color || '#1890ff') : '#d9d9d9'}` }}>
                  {layer === ALL_LAYERS_KEY ? t('functions.allLayers') : td(layer)}
                </Tag.CheckableTag>
              );
            })}
          </Space>
          <div style={{ overflowX: 'auto', whiteSpace: 'nowrap', paddingBottom: 4 }}>
            <Space>
              {BASIC_MODULE_CATEGORIES.filter(c => selectedLayer === ALL_LAYERS_KEY || c.layer === selectedLayer).map(cat => (
                <Tag key={cat.id} color={selectedCategoryId === cat.id ? cat.layerColor : undefined}
                  style={{ cursor: 'pointer', padding: '4px 10px', fontSize: 12 }}
                  onClick={() => setSelectedCategoryId(selectedCategoryId === cat.id ? null : cat.id)}>
                  {cat.icon} {displayText(cat.name, cat.id)} ({cat.functionCount})
                </Tag>
              ))}
            </Space>
          </div>
          {renderFunctionContent()}
        </Space>
      </div>
    );
  }

  // 桌面端
  return (
    <div style={{ display: 'flex', height: '100%', gap: 12, padding: 12 }}>
      {renderCategorySidebar()}
      <Card
        size="small"
        title={
          <Space>
            <FunctionOutlined style={{ color: activeColor }} />
            <span style={{ fontSize: 14, fontWeight: 600 }}>
              {selectedCategory ? `${selectedCategory.icon} ${displayText(selectedCategory.name, selectedCategory.id)}` : t('functions.basicAlgorithmList')}
            </span>
            {selectedLayer !== ALL_LAYERS_KEY && (
              <Tag color={LAYERS.find(l => l.name === selectedLayer)?.color}>{displayText(selectedLayer, selectedLayer)}</Tag>
            )}
            <Text type="secondary" style={{ fontSize: 12 }}>
              {selectedCategoryId ? t('functions.functionsCount', { count: filteredFunctionCount }) : t('functions.functionsCount', { count: totalFunctions })}
            </Text>
          </Space>
        }
        extra={
          <Space>
            {/* @AI_GENERATED: Kiro v1.0 */}
            <Button
              icon={<ApartmentOutlined />}
              onClick={() => navigate('/knowledge-graph')}
              size="small"
            >
              {t('functions.knowledgeGraph')}
            </Button>
            {/* @AI_GENERATED: end */}
            {/* @AI_GENERATED */}
            <Segmented
              size="small"
              value={backendFilter}
              onChange={v => setBackendFilter(v as 'all' | 'verified' | 'ready-unverified' | 'definition-only')}
              options={[
                { label: t('functions.filterAll'), value: 'all' },
                { label: t('functions.filterVerified'), value: 'verified' },
                { label: t('functions.filterReadyUnverified'), value: 'ready-unverified' },
                { label: t('functions.filterDefinitionOnly'), value: 'definition-only' },
              ]}
            />
            {/* @AI_GENERATED: end */}
            <Input placeholder={t('functions.searchShort')} prefix={<SearchOutlined />} allowClear value={searchText}
              onChange={e => setSearchText(e.target.value)} style={{ width: 240 }} size="small" />
          </Space>
        }
        style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
        styles={{ body: { flex: 1, overflow: 'auto', padding: 0 } }}
      >
        {renderFunctionContent()}
      </Card>
      
      {/* @AI_GENERATED: Kiro v1.0 */}
      {/* 函数执行模态框 */}
      <Modal
        title={selectedFunction ? `${t('functions.executeFunction')}: ${displayFunctionName(selectedFunction)}` : t('functions.executeFunction')}
        open={executeModalVisible}
        onCancel={() => { setExecuteModalVisible(false); setSelectedFunction(null); }}
        footer={null}
        width={700}
        destroyOnClose
      >
        {selectedFunction && (
          <FunctionExecutor
            functionDef={convertToFunctionDefinition(selectedFunction)}
            isMobile={isMobile}
          />
        )}
      </Modal>
      {/* @AI_GENERATED: end */}

      {/* @AI_GENERATED: operator detail modal */}
      {/* 算子详情模态框 */}
      {detailFunction && (
        <OperatorDetailModal
          operatorId={detailFunction.id}
          operatorName={displayFunctionName(detailFunction)}
          open={detailModalVisible}
          onClose={() => { setDetailModalVisible(false); setDetailFunction(null); }}
        />
      )}
      {/* @AI_GENERATED: end */}
    </div>
  );
};

export default FunctionLibraryPage;
// @AI_GENERATED: end
