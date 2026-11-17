// @AI_GENERATED: Kiro v1.0
import { useState, useMemo, useRef } from 'react';
import { Card, Space, Typography, Tag, Tooltip, Select, Button } from 'antd';
import ReactECharts from 'echarts-for-react';
import {
  ApartmentOutlined,
  NodeIndexOutlined,
  FunctionOutlined,
  FullscreenOutlined,
  FullscreenExitOutlined,
} from '@ant-design/icons';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { BASIC_MODULE_CATEGORIES, LAYERS } from '../data/basicModuleCategories';
import BASIC_MODULE_FUNCTIONS from '../data/basicModuleFunctions';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const { Title, Text } = Typography;
const { Option } = Select;

/** 层级颜色 */
const LAYER_COLORS: Record<string, string> = {
  '数据管理层': '#1890ff',
  '数据处理层': '#52c41a',
  '算法模型层': '#722ed1',
  '基础计算层': '#fa8c16',
  'MLOps层': '#eb2f96',
  '输出展示层': '#13c2c2',
};

/**
 * AI算法知识图谱页面（优化版）
 *
 * 使用前端静态数据，展示 层级→分类→子分类 三层结构。
 * 不加载后端 API，不做 O(n²) 数据流匹配，不使用 3D。
 */
const AlgorithmKnowledgeGraphPage: React.FC = () => {
  const [selectedLayer, setSelectedLayer] = useState<string>('all');
  const [isFullscreen, setIsFullscreen] = useState(false);
  const chartRef = useRef<any>(null);
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end

  /** 是否为详细模式（选择了具体层级） */
  const isDetailMode = selectedLayer !== 'all';

  /** 构建图谱数据 */
  const graphOption = useMemo(() => {
    const nodes: any[] = [];
    const links: any[] = [];

    if (!isDetailMode) {
      // === 总览模式：平台 → 层级 → 分类 → 子分类 ===
      const categories = [
        { name: t('knowledgeGraph.platform') }, { name: t('knowledgeGraph.techLayer') }, { name: t('knowledgeGraph.algorithmCategory') }, { name: t('knowledgeGraph.subCategory') },
      ];

      nodes.push({
        id: 'center', name: t('app.title'), symbolSize: 60, category: 0,
        itemStyle: { color: '#1890ff' }, label: { fontSize: 14, fontWeight: 'bold' },
      });

      LAYERS.forEach(layer => {
        const c = LAYER_COLORS[layer.name] || '#999';
        nodes.push({
          id: `layer_${layer.name}`, name: `${td(layer.name)}\n(${layer.functionCount})`,
          symbolSize: 45, category: 1, itemStyle: { color: c }, label: { fontSize: 12, fontWeight: 'bold' },
        });
        links.push({ source: 'center', target: `layer_${layer.name}`, lineStyle: { width: 2.5, curveness: 0.1 } });
      });

      BASIC_MODULE_CATEGORIES.forEach(cat => {
        const c = LAYER_COLORS[cat.layer] || '#999';
        nodes.push({
          id: `cat_${cat.id}`, name: `${cat.icon} ${td(cat.name)}\n(${cat.functionCount})`,
          symbolSize: 32, category: 2, itemStyle: { color: c, opacity: 0.85 }, label: { fontSize: 11 },
          tooltip: { formatter: `<b>${td(cat.name)}</b><br/>${td(cat.description)}<br/>${cat.functionCount} ${t('knowledgeGraph.functions')}` },
        });
        links.push({ source: `layer_${cat.layer}`, target: `cat_${cat.id}`, lineStyle: { width: 1.5, curveness: 0.2 } });

        const subs = BASIC_MODULE_FUNCTIONS[cat.id];
        if (subs) {
          subs.forEach(sc => {
            const subId = `sub_${cat.id}_${sc.subCategory}`;
            nodes.push({
              id: subId, name: td(sc.subCategory), symbolSize: 18, category: 3,
              itemStyle: { color: c, opacity: 0.6 }, label: { fontSize: 9 },
              tooltip: { formatter: `<b>${td(sc.subCategory)}</b><br/>${td(cat.name)}<br/>${sc.functions.length} ${t('knowledgeGraph.functions')}` },
            });
            links.push({ source: `cat_${cat.id}`, target: subId, lineStyle: { width: 0.8, curveness: 0.3 } });
          });
        }
      });

      return buildChartOption(nodes, links, categories, 180, 100);
    }

    // === 详细模式：层级中心 → 分类 → 子分类 → 具体函数 ===
    const layerColor = LAYER_COLORS[selectedLayer] || '#999';
    const layerCats = BASIC_MODULE_CATEGORIES.filter(c => c.layer === selectedLayer);
    const categories = [
      { name: selectedLayer }, { name: t('knowledgeGraph.algorithmCategory') }, { name: t('knowledgeGraph.subCategory') }, { name: t('knowledgeGraph.function') },
    ];

    // 层级中心节点
    const layerInfo = LAYERS.find(l => l.name === selectedLayer);
    nodes.push({
      id: 'layer_center', name: `${td(selectedLayer)}\n(${layerInfo?.functionCount ?? 0} ${t('knowledgeGraph.functions')})`,
      symbolSize: 55, category: 0, itemStyle: { color: layerColor },
      label: { fontSize: 14, fontWeight: 'bold' },
    });

    layerCats.forEach(cat => {
      // 分类节点
      nodes.push({
        id: `cat_${cat.id}`, name: `${cat.icon} ${td(cat.name)}\n(${cat.functionCount})`,
        symbolSize: 38, category: 1, itemStyle: { color: layerColor, opacity: 0.9 },
        label: { fontSize: 12, fontWeight: 'bold' },
        tooltip: { formatter: `<b>${td(cat.name)}</b><br/>${td(cat.description)}<br/>${cat.functionCount} ${t('knowledgeGraph.functions')}` },
      });
      links.push({ source: 'layer_center', target: `cat_${cat.id}`, lineStyle: { width: 2, curveness: 0.15 } });

      // 子分类 + 函数
      const subs = BASIC_MODULE_FUNCTIONS[cat.id];
      if (subs) {
        subs.forEach(sc => {
          const subId = `sub_${cat.id}_${sc.subCategory}`;
          nodes.push({
            id: subId, name: `${td(sc.subCategory)}\n(${sc.functions.length})`,
            symbolSize: 24, category: 2, itemStyle: { color: layerColor, opacity: 0.7 },
            label: { fontSize: 10 },
            tooltip: { formatter: `<b>${td(sc.subCategory)}</b><br/>${td(cat.name)}<br/>${sc.functions.length} ${t('knowledgeGraph.functions')}` },
          });
          links.push({ source: `cat_${cat.id}`, target: subId, lineStyle: { width: 1.2, curveness: 0.25 } });

          // 具体函数节点
          sc.functions.forEach(fn => {
            const fnId = `fn_${fn.id}`;
            nodes.push({
              id: fnId, name: td(fn.name), symbolSize: 12, category: 3,
              itemStyle: { color: layerColor, opacity: 0.45 },
              label: { fontSize: 8, show: false },
              tooltip: { formatter: `<b>${td(fn.name)}</b><br/><code>${fn.id}</code><br/>${td(fn.description)}` },
            });
            links.push({ source: subId, target: fnId, lineStyle: { width: 0.5, curveness: 0.3 } });
          });
        });
      }
    });

    return buildChartOption(nodes, links, categories, 80, 55);
  }, [selectedLayer, isDetailMode]);

  /** 构建 ECharts option */
  function buildChartOption(nodes: any[], links: any[], categories: any[], repulsion: number, edgeLen: number) {
    return {
      tooltip: {
        trigger: 'item' as const,
        backgroundColor: 'rgba(255,255,255,0.95)',
        borderColor: '#1890ff',
        borderWidth: 1,
        textStyle: { color: '#333' },
      },
      legend: {
        data: categories.map(c => c.name),
        orient: 'vertical' as const,
        left: 10,
        top: 10,
        textStyle: { fontSize: 11 },
      },
      series: [{
        type: 'graph',
        layout: 'force',
        data: nodes,
        links,
        categories,
        roam: true,
        draggable: true,
        label: { show: true, position: 'bottom', formatter: '{b}' },
        labelLayout: { hideOverlap: true },
        scaleLimit: { min: 0.2, max: 4 },
        lineStyle: { color: 'source', curveness: 0.2 },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3 },
          label: { show: true, fontSize: 13, fontWeight: 'bold' },
        },
        blur: {
          itemStyle: { opacity: 0.15 },
          lineStyle: { opacity: 0.08 },
          label: { show: false },
        },
        force: {
          repulsion,
          gravity: 0.06,
          edgeLength: edgeLen,
          layoutAnimation: true,
          friction: 0.6,
        },
      }],
    };
  }

  const stats = useMemo(() => {
    const cats = selectedLayer === 'all'
      ? BASIC_MODULE_CATEGORIES
      : BASIC_MODULE_CATEGORIES.filter(c => c.layer === selectedLayer);
    return {
      layers: selectedLayer === 'all' ? LAYERS.length : 1,
      categories: cats.length,
      functions: cats.reduce((s, c) => s + c.functionCount, 0),
    };
  }, [selectedLayer]);

  const toggleFullscreen = () => setIsFullscreen(f => !f);

  const containerStyle = isFullscreen
    ? { position: 'fixed' as const, inset: 0, zIndex: 9999, background: '#fff', display: 'flex', flexDirection: 'column' as const }
    : { padding: '16px', height: '100%', display: 'flex', flexDirection: 'column' as const };

  return (
    <div style={containerStyle}>
      {/* 头部 */}
      <Card size="small" style={{ marginBottom: 12, flexShrink: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <Space>
            <ApartmentOutlined style={{ fontSize: 20, color: '#1890ff' }} />
            <Title level={4} style={{ margin: 0 }}>{t('knowledgeGraph.title')}</Title>
          </Space>
          <Space wrap>
            <Space size="middle">
              <Tooltip title={t('knowledgeGraph.techLayerCount')}>
                <Tag icon={<NodeIndexOutlined />} color="blue">{stats.layers} {t('knowledgeGraph.layerUnit')}</Tag>
              </Tooltip>
              <Tooltip title={t('knowledgeGraph.categoryCount')}>
                <Tag icon={<ApartmentOutlined />} color="purple">{stats.categories} {t('knowledgeGraph.categoryUnit')}</Tag>
              </Tooltip>
              <Tooltip title={t('knowledgeGraph.functionCount')}>
                <Tag icon={<FunctionOutlined />} color="green">{stats.functions} {t('knowledgeGraph.functions')}</Tag>
              </Tooltip>
            </Space>
            <Select value={selectedLayer} onChange={setSelectedLayer} style={{ width: 160 }} size="small">
              <Option value="all">{t('knowledgeGraph.allLayers')}</Option>
              {LAYERS.map(l => (
                <Option key={l.name} value={l.name}>{td(l.name)} ({l.functionCount})</Option>
              ))}
            </Select>
            <Button
              size="small"
              icon={isFullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
              onClick={toggleFullscreen}
            >
              {isFullscreen ? t('knowledgeGraph.exitFullscreen') : t('knowledgeGraph.fullscreen')}
            </Button>
          </Space>
        </div>
        <div style={{ marginTop: 8, padding: '8px 12px', background: '#f6f8fa', borderRadius: 4, borderLeft: '3px solid #1890ff' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {isDetailMode
              ? t('knowledgeGraph.detailModeHint', { layer: selectedLayer })
              : t('knowledgeGraph.overviewModeHint')}
          </Text>
        </div>
      </Card>

      {/* 图谱 */}
      <Card
        size="small"
        style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
        styles={{ body: { flex: 1, padding: 0, minHeight: 400 } }}
      >
        <ReactECharts
          ref={chartRef}
          option={graphOption}
          style={{ height: '100%', width: '100%' }}
          opts={{ renderer: 'canvas' }}
          notMerge
        />
      </Card>
    </div>
  );
};

export default AlgorithmKnowledgeGraphPage;
// @AI_GENERATED: end
