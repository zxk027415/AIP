// @AI_GENERATED: Kiro v1.0
/**
 * 算法方案库页面
 * 左侧边栏展示行业场景树（L1行业 → L2分类 → L3方案）
 * 右侧展示选中方案的业务场景详情和挂载功能
 * 树形样式与模板编辑器节点库一致
 */
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Card, Row, Col, Tag, Input, Space, Typography, Spin, Tree, Button, Statistic,
  Empty, Modal, List, message, Popconfirm, Tabs, Descriptions, Badge, Select,
} from 'antd';
import type { TreeDataNode } from 'antd';
import {
  SearchOutlined, AppstoreOutlined, LinkOutlined, PlusOutlined, DeleteOutlined,
  FolderOutlined, FileOutlined, ReloadOutlined,
} from '@ant-design/icons';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import { fetchTemplates, fetchTemplateStats, mountWorkflowToScenario, unmountWorkflowFromScenario } from '../services/algorithmSolutionApi';
import { enhancedWorkflowApi } from '../services/workflowEnhancedApi';
import type { TemplateItem, TemplateStats, BusinessScenario } from '../types/algorithm-solution';
import type { EnhancedWorkflow } from '../types/workflow-enhanced';
import '../components/workflow-enhanced/NodeLibraryPanel.css';

const { Text, Paragraph, Title } = Typography;

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  excellent: { label: 'excellent', color: '#52c41a' },
  good: { label: 'good', color: '#1890ff' },
  fair: { label: 'fair', color: '#fa8c16' },
  needs_improvement: { label: 'needsImprovement', color: '#f5222d' },
};

// @AI_GENERATED: Kiro v1.0
// 场景颜色映射（13个行业场景）
const SCENARIO_COLORS: Record<string, string> = {
  'renewable-energy': '#faad14',
  'thermal-power': '#fa541c',
  'energy-storage': '#52c41a',
  'power-grid': '#1890ff',
  'steel-manufacturing': '#722ed1',
  'pv-manufacturing': '#eb2f96',
  'battery-manufacturing': '#13c2c2',
  'semiconductor': '#2f54eb',
  'chemical-process': '#fadb14',
  'port-logistics': '#fa8c16',
  'building-campus': '#a0d911',
  'carbon-management': '#389e0d',
  'water-environment': '#1890ff',
};
// @AI_GENERATED: end
const ALL_INDUSTRIES_KEY = 'all-industries';
const CHINESE_CHAR_RE = /[\u4e00-\u9fff]/;
const SIDEBAR_MIN_WIDTH = 260;
const SIDEBAR_MAX_WIDTH = 640;
const humanizeIdentifier = (value: string): string =>
  value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b[a-z]/g, (ch) => ch.toUpperCase());

const AlgorithmSolutionLibraryPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [stats, setStats] = useState<TemplateStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateItem | null>(null);
  const [searchText, setSearchText] = useState('');
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [activeScenario, setActiveScenario] = useState<string>(ALL_INDUSTRIES_KEY);
  // @AI_GENERATED: Kiro v1.0
  // 标记是否已处理 URL 参数
  const urlParamProcessedRef = useRef(false);
  // @AI_GENERATED: end

  // 业务场景挂载相关状态
  const [mountModalVisible, setMountModalVisible] = useState(false);
  const [currentBusinessScenario, setCurrentBusinessScenario] = useState<BusinessScenario | null>(null);
  const [savedWorkflows, setSavedWorkflows] = useState<EnhancedWorkflow[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);
  const [workflowSearchText, setWorkflowSearchText] = useState('');
  const [sidebarWidth, setSidebarWidth] = useState(320);
  const [isResizingSidebar, setIsResizingSidebar] = useState(false);
  const [isSidebarResizeHover, setIsSidebarResizeHover] = useState(false);
  const resizeStartRef = useRef<{ startX: number; startWidth: number } | null>(null);

  const displayText = useCallback(
    (text: string | null | undefined, fallbackId?: string) => {
      const original = String(text ?? '');
      const translated = td(original);
      if ((i18n.language || '').toLowerCase().startsWith('zh')) return original;
      if (!translated || CHINESE_CHAR_RE.test(translated)) {
        return humanizeIdentifier(fallbackId || original);
      }
      return translated;
    },
    [i18n.language],
  );

  const handleSidebarResizeStart = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    resizeStartRef.current = { startX: event.clientX, startWidth: sidebarWidth };
    setIsResizingSidebar(true);
  };

  useEffect(() => {
    if (!isResizingSidebar) return;

    const handleMouseMove = (event: MouseEvent) => {
      if (!resizeStartRef.current) return;
      const deltaX = event.clientX - resizeStartRef.current.startX;
      const nextWidth = Math.min(
        SIDEBAR_MAX_WIDTH,
        Math.max(SIDEBAR_MIN_WIDTH, resizeStartRef.current.startWidth + deltaX),
      );
      setSidebarWidth(nextWidth);
    };

    const handleMouseUp = () => {
      setIsResizingSidebar(false);
      resizeStartRef.current = null;
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isResizingSidebar]);

  // @AI_GENERATED: Kiro v1.0
  // 用于存储当前选中的模板ID，避免循环依赖
  const selectedTemplateIdRef = useRef<string | null>(null);
  
  // 更新 ref 当 selectedTemplate 变化时
  useEffect(() => {
    selectedTemplateIdRef.current = selectedTemplate?.id || null;
  }, [selectedTemplate]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { page_size: '300' };
      const [res, st] = await Promise.all([fetchTemplates(params as never), fetchTemplateStats()]);
      setTemplates(res.items);
      setStats(st);
      // 更新 selectedTemplate 以反映最新数据
      if (selectedTemplateIdRef.current) {
        const updated = res.items.find(t => t.id === selectedTemplateIdRef.current);
        if (updated) setSelectedTemplate(updated);
      }
    } catch { /* ignore */ }
    setLoading(false);
  }, []);
  // @AI_GENERATED: end

  useEffect(() => { loadData(); }, [loadData]);

  // @AI_GENERATED: Kiro v1.0
  // 行业分组定义 - 与 industry_scenarios.json 的 industry_tags 保持一致
  const INDUSTRY_GROUPS = [
    { id: 'renewable', nameKey: 'solutionLibrary.industry.renewable', icon: '⚡', tags: ['新能源'] },
    { id: 'traditional-energy', nameKey: 'solutionLibrary.industry.traditionalEnergy', icon: '🔥', tags: ['传统能源'] },
    { id: 'grid-storage', nameKey: 'solutionLibrary.industry.gridStorage', icon: '🔌', tags: ['源网荷储'] },
    { id: 'manufacturing', nameKey: 'solutionLibrary.industry.manufacturing', icon: '🏭', tags: ['工业制造'] },
    { id: 'port', nameKey: 'solutionLibrary.industry.port', icon: '🚢', tags: ['港口运输'] },
    { id: 'building', nameKey: 'solutionLibrary.industry.building', icon: '🏢', tags: ['楼宇园区'] },
    { id: 'carbon', nameKey: 'solutionLibrary.industry.carbon', icon: '🌱', tags: ['碳管理'] },
    { id: 'utility', nameKey: 'solutionLibrary.industry.utility', icon: '💧', tags: ['公用事业'] },
  ];

  // 场景到行业的映射
  const scenarioToIndustryMap = useMemo(() => {
    if (!stats) return new Map<string, string>();
    const map = new Map<string, string>();
    stats.by_scenario.forEach(s => {
      const industry = INDUSTRY_GROUPS.find(g => g.tags.some(t => s.industry_tags?.includes(t)));
      if (industry) map.set(s.scenario_id, industry.id);
    });
    return map;
  }, [stats]);

  // 行业筛选选项
  const industryOptions = useMemo(() => {
    return [
      { value: ALL_INDUSTRIES_KEY, label: t('solutionLibrary.allIndustries') },
      ...INDUSTRY_GROUPS.map(g => ({
        value: g.id,
        label: `${g.icon} ${t(g.nameKey)}`,
      })),
    ];
  }, [t, i18n.language]);
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 构建树形数据：L0行业 → L1场景 → L2分类 → L3方案
  const treeData = useMemo<TreeDataNode[]>(() => {
    if (!stats) return [];
    
    // 按场景和分类分组模板
    const grouped: Record<string, Record<string, TemplateItem[]>> = {};
    templates.forEach(t => {
      const scenarioId = t.scenario_id;
      const category = t.display_category;
      if (!grouped[scenarioId]) grouped[scenarioId] = {};
      if (!grouped[scenarioId][category]) grouped[scenarioId][category] = [];
      grouped[scenarioId][category].push(t);
    });

    // 按行业分组场景
    const scenariosByIndustry: Record<string, typeof stats.by_scenario> = {};
    stats.by_scenario.forEach(scenario => {
      const industryId = scenarioToIndustryMap.get(scenario.scenario_id) || 'general';
      if (!scenariosByIndustry[industryId]) scenariosByIndustry[industryId] = [];
      scenariosByIndustry[industryId].push(scenario);
    });

    // 构建L0行业节点
    return INDUSTRY_GROUPS.map(industry => {
      // 筛选行业
      if (activeScenario !== ALL_INDUSTRIES_KEY && activeScenario !== industry.id) return null;
      
      const scenarios = scenariosByIndustry[industry.id] || [];
      if (scenarios.length === 0) return null;

      // 构建L1场景节点
      const scenarioNodes = scenarios.map(scenario => {
        const color = SCENARIO_COLORS[scenario.scenario_id] || '#999';
        const categories = grouped[scenario.scenario_id] || {};
        
        // 构建L2分类节点
        const categoryNodes = Object.entries(categories)
          .map(([category, items]) => {
            const filteredItems = items.filter(t => 
              !searchText || t.name.toLowerCase().includes(searchText.toLowerCase())
            );
            if (searchText && filteredItems.length === 0) return null;
            
            return {
              key: `${scenario.scenario_id}_${category}`,
              title: (
                <span className="tree-subject-title" style={{ color }}>
                  <FolderOutlined style={{ color }} />
                  {td(category)}
                  <span style={{ fontSize: 11, fontWeight: 400, color: '#999', marginLeft: 6 }}>
                    {filteredItems.length}
                  </span>
                </span>
              ),
              selectable: false,
              // L3方案节点
              children: filteredItems.map(t => ({
                key: t.id,
                title: (
                  <Space size={4}>
                    <span>{td(t.name)}</span>
                    {t.business_scenarios && t.business_scenarios.some(bs => bs.mounted_workflows?.length) && (
                      <Badge status="success" />
                    )}
                  </Space>
                ),
                icon: <FileOutlined style={{ color: '#1890ff' }} />,
                isLeaf: true,
              })),
            };
          })
          .filter(Boolean) as TreeDataNode[];

        if (searchText && categoryNodes.length === 0) return null;

        const scenarioCount = categoryNodes.reduce((sum, node) => sum + ((node.children?.length) || 0), 0);

        return {
          key: scenario.scenario_id,
          title: (
            <span className="tree-category-title" style={{ color }}>
              <FolderOutlined style={{ color }} />
              {scenario.icon} {td(scenario.name)}
              <span style={{ fontSize: 11, fontWeight: 400, color: '#999', marginLeft: 6 }}>
                {scenarioCount}
              </span>
            </span>
          ),
          selectable: false,
          children: categoryNodes,
        };
      }).filter(Boolean) as TreeDataNode[];

      if (scenarioNodes.length === 0) return null;

      const industryCount = scenarioNodes.reduce((sum, node) => {
        return sum + (node.children?.reduce((s, c) => s + ((c.children?.length) || 0), 0) || 0);
      }, 0);

      return {
        key: `industry_${industry.id}`,
        title: (
          <span className="tree-category-title" style={{ fontWeight: 600 }}>
            <FolderOutlined />
            {industry.icon} {t(industry.nameKey)}
            <span style={{ fontSize: 11, fontWeight: 400, color: '#999', marginLeft: 6 }}>
              {industryCount}
            </span>
          </span>
        ),
        selectable: false,
        children: scenarioNodes,
      };
    }).filter(Boolean) as TreeDataNode[];
  }, [stats, templates, searchText, activeScenario, scenarioToIndustryMap, t, i18n.language]);
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 默认只展开第一个分支并选中第一个方案，或根据 URL 参数选中指定方案
  useEffect(() => {
    if (treeData.length === 0 || templates.length === 0) return;
    
    // 检查 URL 参数中是否有指定的 template
    const templateParam = searchParams.get('template');
    
    if (templateParam && !urlParamProcessedRef.current) {
      // 从 URL 参数选中模板
      const targetTemplate = templates.find(t => t.id === templateParam);
      if (targetTemplate) {
        setSelectedTemplate(targetTemplate);
        urlParamProcessedRef.current = true;
        
        // 展开到目标模板的路径
        const keysToExpand: React.Key[] = [];
        const industryId = scenarioToIndustryMap.get(targetTemplate.scenario_id);
        if (industryId) {
          keysToExpand.push(`industry_${industryId}`);
        }
        keysToExpand.push(targetTemplate.scenario_id);
        keysToExpand.push(`${targetTemplate.scenario_id}_${targetTemplate.display_category}`);
        setExpandedKeys(keysToExpand);
        
        // 清除 URL 参数
        setSearchParams({}, { replace: true });
        return;
      }
    }
    
    // 默认行为：展开第一个分支并选中第一个方案
    if (expandedKeys.length === 0 && !searchText && !urlParamProcessedRef.current) {
      const firstBranchKeys: React.Key[] = [];
      let firstLeafKey: string | null = null;
      
      const collectFirstBranch = (nodes: TreeDataNode[], depth: number = 0): boolean => {
        if (nodes.length === 0) return false;
        const firstNode = nodes[0];
        firstBranchKeys.push(firstNode.key);
        
        if ((firstNode as any).isLeaf) {
          firstLeafKey = firstNode.key as string;
          return true;
        }
        
        if (firstNode.children && firstNode.children.length > 0) {
          return collectFirstBranch(firstNode.children, depth + 1);
        }
        return false;
      };
      
      collectFirstBranch(treeData);
      setExpandedKeys(firstBranchKeys);

      if (!selectedTemplate && firstLeafKey) {
        const template = templates.find(t => t.id === firstLeafKey);
        if (template) setSelectedTemplate(template);
      }
    }
  }, [treeData, templates, searchParams, scenarioToIndustryMap, setSearchParams]);
  // @AI_GENERATED: end

  // 处理搜索
  const handleSearch = (value: string) => {
    setSearchText(value);
    if (value) {
      const allKeys: React.Key[] = [];
      const collectKeys = (nodes: TreeDataNode[]) => {
        nodes.forEach((node) => {
          allKeys.push(node.key);
          if (node.children) collectKeys(node.children);
        });
      };
      collectKeys(treeData);
      setExpandedKeys(allKeys);
    } else {
      setExpandedKeys([]);
    }
  };

  // 加载已保存的算法模板
  const loadSavedWorkflows = async () => {
    try {
      setLoadingWorkflows(true);
      const workflows = await enhancedWorkflowApi.listWorkflows();
      setSavedWorkflows(workflows);
    } catch {
      message.error(t('solutionLibrary.loadTemplateFailed'));
    } finally {
      setLoadingWorkflows(false);
    }
  };

  // 打开挂载模态框
  const handleOpenMountModal = (scenario: BusinessScenario) => {
    setCurrentBusinessScenario(scenario);
    setMountModalVisible(true);
    loadSavedWorkflows();
  };

  // 挂载模板到业务场景
  const handleMountWorkflow = async (workflow: EnhancedWorkflow) => {
    if (!selectedTemplate || !currentBusinessScenario) return;
    try {
      await mountWorkflowToScenario(selectedTemplate.id, currentBusinessScenario.id, workflow.id!);
      message.success(t('solutionLibrary.mountSuccess', { workflow: td(workflow.name), scenario: td(currentBusinessScenario.name) }));
      setMountModalVisible(false);
      loadData();
    } catch {
      message.error(t('solutionLibrary.mountFailed'));
    }
  };

  // 卸载模板
  const handleUnmountWorkflow = async (scenarioId: string, workflowId: string) => {
    if (!selectedTemplate) return;
    try {
      await unmountWorkflowFromScenario(selectedTemplate.id, scenarioId, workflowId);
      message.success(t('solutionLibrary.unmountSuccess'));
      loadData();
    } catch {
      message.error(t('solutionLibrary.unmountFailed'));
    }
  };

  // 过滤模板
  const filteredWorkflows = workflowSearchText.trim()
    ? savedWorkflows.filter((wf) =>
        wf.name.toLowerCase().includes(workflowSearchText.toLowerCase()) ||
        (wf.description || '').toLowerCase().includes(workflowSearchText.toLowerCase())
      )
    : savedWorkflows;

  // 树节点选择
  const handleTreeSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length === 0) return;
    const key = selectedKeys[0] as string;
    const template = templates.find(t => t.id === key);
    if (template) {
      setSelectedTemplate(template);
    }
  };

  // 渲染业务场景卡片
  const renderBusinessScenarioCard = (scenario: BusinessScenario) => (
    <Card
      key={scenario.id}
      size="small"
      title={displayText(scenario.name, scenario.id)}
      extra={
        <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => handleOpenMountModal(scenario)}>
          {t('solutionLibrary.mountTemplate')}
        </Button>
      }
      style={{ marginBottom: 12 }}
    >
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>{displayText(scenario.description, scenario.id)}</Paragraph>
      {scenario.mounted_workflows && scenario.mounted_workflows.length > 0 ? (
        <List
          size="small"
          dataSource={scenario.mounted_workflows}
          renderItem={(wf: any) => (
            <List.Item
              actions={[
                // @AI_GENERATED
                ...(wf.name?.includes('负荷预测') || wf.id?.includes('load-forecast') ? [
                  <Button
                    key="train"
                    type="link"
                    size="small"
                    style={{ color: '#52c41a' }}
                    onClick={() => navigate(`/workflow/editor/workflow-load-forecast-training-v2`)}
                  >
                    {t('solutionLibrary.triggerTraining')}
                  </Button>,
                ] : []),
                // @AI_GENERATED: end
                <Button key="edit" type="link" size="small" onClick={() => { window.location.href = `/workflow/editor/${wf.id}`; }}>
                  {t('solutionLibrary.edit')}
                </Button>,
                <Popconfirm
                  key="unmount"
                  title={t('solutionLibrary.confirmUnmount')}
                  onConfirm={() => handleUnmountWorkflow(scenario.id, wf.id)}
                  okText={t('solutionLibrary.unmount')}
                  cancelText={t('solutionLibrary.cancel')}
                >
                  <Button type="link" size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                title={<Text style={{ fontSize: 13 }}>{td(wf.name)}</Text>}
                description={
                  <Space size={4}>
                    <Tag color="blue" style={{ fontSize: 11 }}>{t('solutionLibrary.nodeCount', { count: wf.node_count || 0 })}</Tag>
                    <Tag color="green" style={{ fontSize: 11 }}>{t('solutionLibrary.edgeCount', { count: wf.edge_count || 0 })}</Tag>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      ) : (
        <Empty description={t('solutionLibrary.noMountedTemplates')} image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '8px 0' }} />
      )}
    </Card>
  );

  // 计算已挂载模板总数
  const getMountedCount = (template: TemplateItem) => {
    if (!template.business_scenarios) return 0;
    return template.business_scenarios.reduce((sum, bs) => sum + (bs.mounted_workflows?.length || 0), 0);
  };

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 64px)' }}>
      {/* 左侧边栏 - 使用节点库样式 */}
      <div style={{ width: sidebarWidth, position: 'relative', flexShrink: 0 }}>
        <Card
          className="node-library-panel"
          style={{ width: '100%', borderRadius: 0, borderRight: '1px solid #f0f0f0' }}
          bodyStyle={{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }}
        >
          <div style={{ padding: '12px 8px 0', flexShrink: 0 }}>
            <Title level={5} style={{ margin: '0 0 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
              <AppstoreOutlined />
              {t('solutionLibrary.title')}
            </Title>
            <Input
              placeholder={t('solutionLibrary.searchPlaceholder')}
              prefix={<SearchOutlined />}
              value={searchText}
              onChange={(e) => handleSearch(e.target.value)}
              className="node-library-search"
              allowClear
              style={{ margin: 0, width: '100%' }}
            />
          </div>
          
          <div className="node-library-layer-filter">
            <Select
              size="small"
              value={activeScenario}
              onChange={(val) => {
                setActiveScenario(val);
                setExpandedKeys([]);
              }}
              style={{ width: '100%' }}
              options={industryOptions}
            />
          </div>

          <div className="node-library-tree-container">
            <Spin spinning={loading}>
              {treeData.length > 0 ? (
                <Tree
                  className="node-library-tree"
                  treeData={treeData}
                  expandedKeys={expandedKeys}
                  onExpand={(keys) => setExpandedKeys(keys)}
                  onSelect={handleTreeSelect}
                  selectedKeys={selectedTemplate ? [selectedTemplate.id] : []}
                  showIcon
                  blockNode
                />
              ) : (
                <Empty
                  description={t('solutionLibrary.noMatch')}
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  style={{ marginTop: 40 }}
                />
              )}
            </Spin>
          </div>
        </Card>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label={t('solutionLibrary.title')}
          onMouseDown={handleSidebarResizeStart}
          onMouseEnter={() => setIsSidebarResizeHover(true)}
          onMouseLeave={() => setIsSidebarResizeHover(false)}
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
            transform: 'translateX(50%)',
            width: 10,
            height: '100%',
            cursor: 'col-resize',
            zIndex: 10,
            background: isSidebarResizeHover ? '#e8e8e8' : 'transparent',
            transition: 'background 0.2s',
          }}
        />
      </div>

      {/* 右侧内容区 */}
      <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
        {selectedTemplate ? (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            {/* 方案基本信息 */}
            <Card size="small">
              <Row gutter={16} align="middle">
                <Col flex="auto">
                  <Title level={4} style={{ margin: 0 }}>{td(selectedTemplate.name)}</Title>
                  <Paragraph type="secondary" style={{ margin: '8px 0 0' }}>{td(selectedTemplate.description)}</Paragraph>
                </Col>
                <Col>
                  <Button icon={<ReloadOutlined />} onClick={loadData}>{t('solutionLibrary.refresh')}</Button>
                </Col>
              </Row>
            </Card>

            {/* 统计信息 */}
            <Row gutter={16}>
              <Col span={6}>
                <Card size="small">
                  <Statistic title={t('solutionLibrary.businessScenarios')} value={selectedTemplate.business_scenarios?.length || 0} prefix={<FolderOutlined />} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title={t('solutionLibrary.mountedTemplates')} value={getMountedCount(selectedTemplate)} prefix={<LinkOutlined />} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  <Statistic title={t('solutionLibrary.category')} value={td(selectedTemplate.display_category)} valueStyle={{ fontSize: 16 }} />
                </Card>
              </Col>
              <Col span={6}>
                <Card size="small">
                  {selectedTemplate.accuracy_status ? (
                    <Statistic
                      title={t('solutionLibrary.accuracyStatus')}
                      value={t(`solutionLibrary.${STATUS_MAP[selectedTemplate.accuracy_status]?.label}`) || '-'}
                      valueStyle={{ color: STATUS_MAP[selectedTemplate.accuracy_status]?.color, fontSize: 16 }}
                    />
                  ) : (
                    <Statistic title={t('solutionLibrary.accuracyStatus')} value={t('solutionLibrary.notTested')} valueStyle={{ fontSize: 16, color: '#999' }} />
                  )}
                </Card>
              </Col>
            </Row>

            {/* 业务场景列表 */}
            <Card
              size="small"
              title={<><LinkOutlined style={{ marginRight: 8 }} />{t('solutionLibrary.businessSubScenarios')}</>}
            >
              {selectedTemplate.business_scenarios && selectedTemplate.business_scenarios.length > 0 ? (
                <Tabs
                  tabPosition="left"
                  size="small"
                  items={selectedTemplate.business_scenarios.map(scenario => ({
                    key: scenario.id,
                    label: (
                      <Space>
                        {displayText(scenario.name, scenario.id)}
                        {scenario.mounted_workflows && scenario.mounted_workflows.length > 0 && (
                          <Tag color="green" style={{ fontSize: 10 }}>{scenario.mounted_workflows.length}</Tag>
                        )}
                      </Space>
                    ),
                    children: renderBusinessScenarioCard(scenario),
                  }))}
                />
              ) : (
                <Empty description={t('solutionLibrary.noBusinessScenarios')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              )}
            </Card>

            {/* 方案详情 */}
            <Card size="small" title={t('solutionLibrary.solutionDetails')}>
              <Descriptions column={2} size="small">
                <Descriptions.Item label={t('solutionLibrary.solutionId')}>{selectedTemplate.id}</Descriptions.Item>
                <Descriptions.Item label={t('solutionLibrary.belongsToScenario')}>{selectedTemplate.scenario_id}</Descriptions.Item>
                <Descriptions.Item label={t('solutionLibrary.displayCategory')}>{td(selectedTemplate.display_category)}</Descriptions.Item>
                <Descriptions.Item label={t('solutionLibrary.accuracyStatus')}>
                  {selectedTemplate.accuracy_status ? (
                    <Badge color={STATUS_MAP[selectedTemplate.accuracy_status]?.color} text={t(`solutionLibrary.${STATUS_MAP[selectedTemplate.accuracy_status]?.label}`)} />
                  ) : '-'}
                </Descriptions.Item>
              </Descriptions>
            </Card>
          </Space>
        ) : (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
            <Empty description={t('solutionLibrary.selectSolution')} />
          </div>
        )}
      </div>

      {/* 挂载模板模态框 */}
      <Modal
        title={t('solutionLibrary.mountTemplateToScenario', { name: td(currentBusinessScenario?.name || '') })}
        open={mountModalVisible}
        onCancel={() => setMountModalVisible(false)}
        footer={null}
        width={500}
      >
        <Input
          placeholder={t('solutionLibrary.searchTemplate')}
          prefix={<SearchOutlined />}
          value={workflowSearchText}
          onChange={(e) => setWorkflowSearchText(e.target.value)}
          allowClear
          style={{ marginBottom: 12 }}
        />
        <Spin spinning={loadingWorkflows}>
          {filteredWorkflows.length > 0 ? (
            <List
              size="small"
              dataSource={filteredWorkflows}
              style={{ maxHeight: 400, overflowY: 'auto' }}
              renderItem={(wf) => (
                <List.Item
                  actions={[
                    <Button key="mount" type="primary" size="small" onClick={() => handleMountWorkflow(wf)}>
                      {t('solutionLibrary.mount')}
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={td(wf.name)}
                    description={
                      <Space direction="vertical" size={2}>
                        {wf.description && <Text type="secondary" style={{ fontSize: 12 }}>{td(wf.description)}</Text>}
                        <Space size={4}>
                          <Tag color="blue">{t('solutionLibrary.nodeCount', { count: wf.nodes.length })}</Tag>
                          <Tag color="green">{t('solutionLibrary.edgeCount', { count: wf.edges.length })}</Tag>
                        </Space>
                      </Space>
                    }
                  />
                </List.Item>
              )}
            />
          ) : (
            <Empty description={workflowSearchText ? t('solutionLibrary.noMatchTemplate') : t('solutionLibrary.noTemplates')} image={Empty.PRESENTED_IMAGE_SIMPLE}>
              <Button onClick={() => { window.location.href = '/workflow/editor'; }}>{t('solutionLibrary.createNew')}</Button>
            </Empty>
          )}
        </Spin>
      </Modal>
    </div>
  );
};

export default AlgorithmSolutionLibraryPage;
// @AI_GENERATED: end
