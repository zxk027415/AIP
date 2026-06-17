// @AI_GENERATED: Kiro v1.0
/**
 * Node Library Panel V2
 * 节点库面板 — 按6层技术层级/技术分类两层组织 + 算法方案入口
 */

import React, { useState, useEffect, useMemo } from 'react';
import {
  Card, Tree, Input, Empty, Spin, message, Select, Tabs,
  Tag, Space, Typography, Collapse, Dropdown, Tooltip, Progress, Divider, Button, Popconfirm,
} from 'antd';
import type { DataNode } from 'antd/es/tree';
import {
  SearchOutlined,
  BranchesOutlined,
  RobotOutlined,
  FolderOutlined,
  FileOutlined,
  AppstoreOutlined,
  ThunderboltOutlined,
  SendOutlined,
  BulbOutlined,
  CopyOutlined,
  WarningOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  SyncOutlined,
  HistoryOutlined,
  DeleteOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import { functionLibraryApi, enhancedWorkflowApi } from '../../services/workflowEnhancedApi';
import { industryApi } from '../../services/industryApi';
import workflowAgentApi from '../../services/workflowAgentApi';
import type { IndustryTemplate } from '../../services/industryApi';
import type { EnhancedNodeData, EnhancedWorkflow } from '../../types/workflow-enhanced';
import type { FunctionDefinition, Category } from '../../types/function';
import { useWorkflowAgentStore } from '../../stores/workflowAgentStore';
import type { AgentSession } from '../../stores/workflowAgentStore';
import './NodeLibraryPanel.css';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { td } from '../../utils/dataTranslation';
// @AI_GENERATED: end

const { Text } = Typography;
const { TextArea } = Input;

// AI 助手示例 Prompts
const AI_EXAMPLE_PROMPTS = [
  '光伏发电功率预测，基于气象数据和历史发电量',
  '锂电池SOC估计与SOH健康状态评估',
  '电网负荷预测与调度优化',
  '钢铁连铸坯质量预测与工艺参数优化',
  '光伏组件EL缺陷检测与良率分析',
  '动力电池一致性分选与容量预测',
  '工厂设备OEE分析与排程优化',
  '港口AGV路径规划与泊位调度优化',
  '楼宇暖通空调能耗优化与舒适度控制',
  '企业碳排放核算与碳足迹追踪',
  '工业SCADA大屏数据可视化与趋势分析',
  '基于LLM的工业设备日志智能解析',
  '产线产品表面缺陷视觉检测',
  '旋转设备振动信号故障诊断与RUL预测',
];
const AI_PROMPT_TEMPLATE = '【行业】___  【目标】___  【数据】___  【约束】___';

// AI 助手：模板相关性评分
function scoreTemplateRelevance(tpl: IndustryTemplate, query: string): number {
  if (!query.trim()) return 0;
  const q = query.toLowerCase();
  const tokens = q.split(/[\s,，、;；]+/).filter(Boolean);
  let score = 0;
  const name = tpl.name.toLowerCase();
  const desc = (tpl.description || '').toLowerCase();
  const cat = (tpl.display_category || '').toLowerCase();
  if (name.includes(q)) score += 50;
  if (q.includes(name)) score += 40;
  for (const tok of tokens) {
    if (tok.length < 2) continue;
    if (name.includes(tok)) score += 20;
    if (desc.includes(tok)) score += 10;
    if (cat.includes(tok)) score += 5;
  }
  return score;
}

function rankTemplates(tpls: IndustryTemplate[], query: string, topN = 5) {
  const scored = tpls.map((tpl) => ({ ...tpl, relevanceScore: scoreTemplateRelevance(tpl, query) }));
  scored.sort((a, b) => b.relevanceScore - a.relevanceScore);
  return scored.slice(0, topN);
}

// AI 助手：转换节点格式
function transformToEnhancedNodes(rawNodes: any[]) {
  return rawNodes.map((node: any) => ({
    id: node.id,
    type: 'enhanced' as const,
    position: node.position,
    data: {
      label: node.data.label,
      description: node.data.description || null,
      type: 'function' as const,
      inputs: (node.data.inputs || []).map((inp: any) => ({ ...inp, type: 'input' as const, dataType: (inp.type || 'any').toLowerCase() })),
      outputs: (node.data.outputs || []).map((out: any) => ({ ...out, type: 'output' as const, dataType: (out.type || 'any').toLowerCase() })),
      config: { functionId: node.data.functionId, ...node.data.parameters },
      status: 'idle' as const,
    },
  }));
}

function transformToEnhancedEdges(rawEdges: any[]) {
  return rawEdges.map((edge: any) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle || undefined,
    targetHandle: edge.targetHandle || undefined,
    type: 'smoothstep' as const,
  }));
}

type AIStep = 'input' | 'matching' | 'select-template' | 'composing' | 'generating' | 'validating' | 'done';

interface AIErrorInfo {
  step: string;
  message: string;
  severity?: 'error' | 'info';
}

interface ExtendedTreeDataNode extends DataNode {
  data?: EnhancedNodeData;
  children?: ExtendedTreeDataNode[];
}

interface NodeLibraryPanelV2Props {
  onNodeDragStart?: (event: React.DragEvent, nodeData: EnhancedNodeData) => void;
  // @AI_GENERATED: Kiro v1.0
  onApplyWorkflow?: (nodes: any[], edges: any[], name: string, id?: string) => void;
  // @AI_GENERATED: end
  onMergeNodes?: (nodes: any[], edges: any[]) => void;
}

/** 6层技术层级 → category 映射（与 basicModuleCategories.ts 一致） */
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

/** 层级颜色（与算法列表页一致） */
const LAYER_COLORS: Record<string, string> = {
  '数据管理层': '#1890ff',
  '数据处理层': '#52c41a',
  '算法模型层': '#722ed1',
  '基础计算层': '#fa8c16',
  'MLOps层': '#eb2f96',
  '输出展示层': '#13c2c2',
  '控制流节点': '#cf1322',
  'Agent节点': '#2f54eb',
};

const LAYER_ORDER = Object.keys(LAYER_CATEGORY_MAP);

/** 所有已映射的 category id */
const MAPPED_CATEGORIES = new Set(Object.values(LAYER_CATEGORY_MAP).flat());

/** 层级筛选内部值（与语言无关，避免切换语言后筛选失效） */
const ALL_LAYERS_KEY = '__all_layers__';
const CONTROL_FLOW_KEY = '__control_flow__';
const AGENT_NODES_KEY = '__agent_nodes__';

const CHINESE_CHAR_RE = /[\u4e00-\u9fff]/;
const humanizeIdentifier = (value: string): string =>
  value
    .replace(/[_-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b[a-z]/g, (ch) => ch.toUpperCase());

const NodeLibraryPanelV2: React.FC<NodeLibraryPanelV2Props> = ({ onNodeDragStart, onApplyWorkflow, onMergeNodes }) => {
  const { t, i18n } = useTranslation();
  const aiPromptTemplate = td(AI_PROMPT_TEMPLATE);
  const [searchText, setSearchText] = useState('');
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  const [loading, setLoading] = useState(true);
  const [functions, setFunctions] = useState<FunctionDefinition[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [activeLayer, setActiveLayer] = useState<string>(ALL_LAYERS_KEY);

  const layerFilterOptions = useMemo(
    () => [
      { value: ALL_LAYERS_KEY, label: t('workflowEditor.layerFilter.all') },
      ...LAYER_ORDER.map((layer) => ({ value: layer, label: td(layer) })),
      { value: CONTROL_FLOW_KEY, label: t('workflowEditor.layerFilter.controlFlow') },
      { value: AGENT_NODES_KEY, label: t('workflowEditor.layerFilter.agent') },
    ],
    [t, i18n.language],
  );

  // 算法模板（已保存的模板）
  const [savedWorkflows, setSavedWorkflows] = useState<EnhancedWorkflow[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);
  const [workflowSearchText, setWorkflowSearchText] = useState('');
  const [activeTab, setActiveTab] = useState<string>('nodes');

  // AI 助手状态
  const [aiDescription, setAiDescription] = useState('');
  const [aiStep, setAiStep] = useState<AIStep>('input');
  const [aiLoading, setAiLoading] = useState(false);
  const [aiErrorInfo, setAiErrorInfo] = useState<AIErrorInfo | null>(null);
  const [aiActiveKeys, setAiActiveKeys] = useState<string[]>(['step-input']);
  const [aiMatches, setAiMatches] = useState<any[]>([]);
  const [aiSelectedScenario, setAiSelectedScenario] = useState<any>(null);
  const [aiRankedTemplates, setAiRankedTemplates] = useState<any[]>([]);
  const [aiSelectedTemplate, setAiSelectedTemplate] = useState<any>(null);
  const [aiCombinations, setAiCombinations] = useState<any[]>([]);
  const [aiSelectedCombo, setAiSelectedCombo] = useState<any>(null);
  const [aiGeneratedWorkflow, setAiGeneratedWorkflow] = useState<any>(null);
  const [aiValidationResult, setAiValidationResult] = useState<any>(null);

  const displayText = React.useCallback(
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

  useEffect(() => { loadFunctionLibrary(); }, []);

  const loadFunctionLibrary = async () => {
    try {
      setLoading(true);
      const [functionsData, categoriesData] = await Promise.all([
        functionLibraryApi.getAllFunctions(),
        functionLibraryApi.getCategories(),
      ]);
      setFunctions(functionsData);
      setCategories(categoriesData);
    } catch {
      message.error(td('加载AI算法库失败'));
    } finally {
      setLoading(false);
    }
  };

  // @AI_GENERATED: Kiro v1.0
  const loadSavedWorkflows = async () => {
    try {
      setLoadingWorkflows(true);
      const workflows = await enhancedWorkflowApi.listWorkflows();
      setSavedWorkflows(workflows);
    } catch {
      message.error(td('加载算法模板失败'));
    } finally {
      setLoadingWorkflows(false);
    }
  };

  const handleTabChange = (key: string) => {
    setActiveTab(key);
    if (key === 'templates') loadSavedWorkflows();
  };
  // @AI_GENERATED: end

  // 将函数转换为节点数据
  const functionToNodeData = (func: FunctionDefinition): EnhancedNodeData => ({
    label: displayText(func.name, func.id),
    type: 'function',
    description: displayText(func.description, func.id),
    inputs: func.parameters.map((param, index) => ({
      id: `input-${index}`,
      name: displayText(param.name, `input-${index + 1}`),
      type: 'input' as const,
      dataType: param.type.toLowerCase() as any,
      required: param.required,
      description: displayText(param.description, param.name),
    })),
    outputs: [{
      id: 'output-0',
      name: displayText('结果', 'result'),
      type: 'output' as const,
      dataType: (func.return_type || 'any').toLowerCase() as any,
    }],
    config: { functionId: func.id, category: func.category },
  });

  /** category id → Category 对象 */
  const categoryById = useMemo(() => {
    const map = new Map<string, Category>();
    categories.forEach((c) => map.set(c.id, c));
    return map;
  }, [categories]);

  /** 按 category 分组的函数 */
  const funcsByCategory = useMemo(() => {
    const map = new Map<string, FunctionDefinition[]>();
    functions.forEach((fn) => {
      const list = map.get(fn.category) || [];
      list.push(fn);
      map.set(fn.category, list);
    });
    return map;
  }, [functions]);

  /** 构建树：层级(L1) → 分类(L2) → 函数(叶子) */
  const buildTreeData = (searchOverride?: string): ExtendedTreeDataNode[] => {
    const searchLower = (searchOverride ?? searchText).trim().toLowerCase();
    const isSpecialFilter = activeLayer === CONTROL_FLOW_KEY || activeLayer === AGENT_NODES_KEY;
    const layers = activeLayer === ALL_LAYERS_KEY ? LAYER_ORDER : (isSpecialFilter ? [] : [activeLayer]);
    const tree: ExtendedTreeDataNode[] = [];

    for (const layerName of layers) {
      const color = LAYER_COLORS[layerName] || '#999';
      const catIds = LAYER_CATEGORY_MAP[layerName] || [];
      const catChildren: ExtendedTreeDataNode[] = [];

      for (const catId of catIds) {
        const cat = categoryById.get(catId);
        if (!cat) continue;
        const funcs = funcsByCategory.get(catId) || [];

        // 搜索过滤
        const filtered = searchLower
          ? funcs.filter((fn) =>
              fn.name.toLowerCase().includes(searchLower) ||
              (fn.description || '').toLowerCase().includes(searchLower) ||
              fn.id.toLowerCase().includes(searchLower) ||
              displayText(fn.name, fn.id).toLowerCase().includes(searchLower) ||
              displayText(fn.description, fn.id).toLowerCase().includes(searchLower))
          : funcs;

        if (filtered.length === 0) continue;

        const funcNodes: ExtendedTreeDataNode[] = filtered.map((fn) => ({
          title: <span>{displayText(fn.name, fn.id)}</span>,
          key: `fn-${catId}-${fn.id}`,
          icon: <FileOutlined />,
          isLeaf: true,
          data: functionToNodeData(fn),
        }));

        catChildren.push({
          title: (
            <span className="tree-subject-title" style={{ color }}>
              <FolderOutlined style={{ color }} />
              {displayText(cat.name, cat.id)}
              <span style={{ fontSize: 11, fontWeight: 400, color: '#999', marginLeft: 6 }}>
                {funcNodes.length}
              </span>
            </span>
          ),
          key: `cat-${catId}`,
          selectable: false,
          children: funcNodes,
        });
      }

      if (catChildren.length === 0) continue;

      const totalFuncs = catChildren.reduce((s, n) => s + (n.children?.length || 0), 0);
      tree.push({
        title: (
          <span className="tree-category-title" style={{ color }}>
            <FolderOutlined style={{ color }} />
            {displayText(layerName, layerName)}
            <span style={{ fontSize: 11, fontWeight: 400, color: '#999', marginLeft: 6 }}>
              {totalFuncs}
            </span>
          </span>
        ),
        key: `layer-${layerName}`,
        selectable: false,
        children: catChildren,
      });
    }

    // 未映射的分类（如果有）
    if (activeLayer === ALL_LAYERS_KEY) {
      const unmappedCats = categories.filter((c) => !MAPPED_CATEGORIES.has(c.id));
      const unmappedChildren: ExtendedTreeDataNode[] = [];
      for (const cat of unmappedCats) {
        const funcs = funcsByCategory.get(cat.id) || [];
        const filtered = searchLower
          ? funcs.filter((fn) =>
              fn.name.toLowerCase().includes(searchLower) ||
              (fn.description || '').toLowerCase().includes(searchLower) ||
              fn.id.toLowerCase().includes(searchLower) ||
              displayText(fn.name, fn.id).toLowerCase().includes(searchLower) ||
              displayText(fn.description, fn.id).toLowerCase().includes(searchLower))
          : funcs;
        if (filtered.length === 0) continue;
        unmappedChildren.push({
          title: (
            <span className="tree-subject-title" style={{ color: '#999' }}>
              <FolderOutlined style={{ color: '#999' }} />
              {displayText(cat.name, cat.id)}
              <span style={{ fontSize: 11, fontWeight: 400, color: '#999', marginLeft: 6 }}>
                {filtered.length}
              </span>
            </span>
          ),
          key: `cat-${cat.id}`,
          selectable: false,
          children: filtered.map((fn) => ({
            title: <span>{displayText(fn.name, fn.id)}</span>,
            key: `fn-${cat.id}-${fn.id}`,
            icon: <FileOutlined />,
            isLeaf: true,
            data: functionToNodeData(fn),
          })),
        });
      }
      if (unmappedChildren.length > 0) {
        tree.push({
          title: (
            <span className="tree-category-title" style={{ color: '#999' }}>
              <FolderOutlined style={{ color: '#999' }} /> {td('其他')}
            </span>
          ),
          key: 'layer-other',
          selectable: false,
          children: unmappedChildren,
        });
      }

    }

    // 控制流 & Agent 特殊节点
    if (activeLayer === ALL_LAYERS_KEY || activeLayer === CONTROL_FLOW_KEY) {
      tree.push(
        {
          title: <span className="tree-category-title" style={{ color: '#cf1322' }}><BranchesOutlined style={{ color: '#cf1322' }} /> {td('控制流节点')}</span>,
          key: 'special-ctrl',
          selectable: false,
          children: [
            { title: td('开始'), key: 'ctrl-start', icon: <FileOutlined />, isLeaf: true, data: { label: '开始', type: 'start' as const, description: '算法模板起始节点', inputs: [], outputs: [{ id: 'output-0', name: '触发', type: 'output' as const, dataType: 'any' as const }], config: {} } },
            { title: td('结束'), key: 'ctrl-end', icon: <FileOutlined />, isLeaf: true, data: { label: '结束', type: 'end' as const, description: '算法模板终止节点', inputs: [{ id: 'input-0', name: '结果', type: 'input' as const, dataType: 'any' as const, required: true }], outputs: [], config: {} } },
            { title: td('条件判断'), key: 'ctrl-if', icon: <FileOutlined />, isLeaf: true, data: { label: '条件判断', type: 'control' as const, description: '根据条件选择分支', inputs: [{ id: 'input-0', name: '条件', type: 'input' as const, dataType: 'boolean' as const, required: true }], outputs: [{ id: 'output-0', name: '真分支', type: 'output' as const, dataType: 'any' as const }, { id: 'output-1', name: '假分支', type: 'output' as const, dataType: 'any' as const }], config: { conditionType: 'boolean' } } },
            { title: td('循环'), key: 'ctrl-loop', icon: <FileOutlined />, isLeaf: true, data: { label: '循环', type: 'control' as const, description: '对数据集逐项迭代执行', inputs: [{ id: 'input-0', name: '数据集', type: 'input' as const, dataType: 'array' as const, required: true }], outputs: [{ id: 'output-0', name: '当前项', type: 'output' as const, dataType: 'any' as const }], config: { loopType: 'forEach' } } },
            { title: td('并行分支'), key: 'ctrl-parallel', icon: <FileOutlined />, isLeaf: true, data: { label: '并行分支', type: 'control' as const, description: '同时执行多个分支并汇聚', inputs: [{ id: 'input-0', name: '输入', type: 'input' as const, dataType: 'any' as const, required: true }], outputs: [{ id: 'output-0', name: '分支1', type: 'output' as const, dataType: 'any' as const }, { id: 'output-1', name: '分支2', type: 'output' as const, dataType: 'any' as const }], config: { branches: 2 } } },
            { title: td('等待/延时'), key: 'ctrl-delay', icon: <FileOutlined />, isLeaf: true, data: { label: '等待/延时', type: 'control' as const, description: '暂停执行指定时间', inputs: [{ id: 'input-0', name: '触发', type: 'input' as const, dataType: 'any' as const, required: true }], outputs: [{ id: 'output-0', name: '继续', type: 'output' as const, dataType: 'any' as const }], config: { delayMs: 1000 } } },
            { title: td('异常捕获'), key: 'ctrl-trycatch', icon: <FileOutlined />, isLeaf: true, data: { label: '异常捕获', type: 'control' as const, description: '捕获子流程异常并处理', inputs: [{ id: 'input-0', name: '输入', type: 'input' as const, dataType: 'any' as const, required: true }], outputs: [{ id: 'output-0', name: '正常', type: 'output' as const, dataType: 'any' as const }, { id: 'output-1', name: '异常', type: 'output' as const, dataType: 'string' as const }], config: {} } },
            { title: td('变量赋值'), key: 'ctrl-assign', icon: <FileOutlined />, isLeaf: true, data: { label: '变量赋值', type: 'control' as const, description: '设置或更新算法模板变量', inputs: [{ id: 'input-0', name: '值', type: 'input' as const, dataType: 'any' as const, required: true }], outputs: [{ id: 'output-0', name: '变量', type: 'output' as const, dataType: 'any' as const }], config: { variableName: '' } } },
            { title: td('子模板'), key: 'ctrl-subflow', icon: <FileOutlined />, isLeaf: true, data: { label: '子模板', type: 'control' as const, description: '调用另一个算法模板作为子流程', inputs: [{ id: 'input-0', name: '参数', type: 'input' as const, dataType: 'any' as const, required: true }], outputs: [{ id: 'output-0', name: '结果', type: 'output' as const, dataType: 'any' as const }], config: { workflowId: '' } } },
          ],
        },
      );
    }
    if (activeLayer === ALL_LAYERS_KEY || activeLayer === AGENT_NODES_KEY) {
      tree.push(
        {
          title: <span className="tree-category-title" style={{ color: '#2f54eb' }}><RobotOutlined style={{ color: '#2f54eb' }} /> {td('Agent节点')}</span>,
          key: 'special-llm',
          selectable: false,
          children: [
            { title: td('文本生成'), key: 'llm-gen', icon: <FileOutlined />, isLeaf: true, data: { label: '文本生成', type: 'llm' as const, description: '调用LLM生成文本', inputs: [{ id: 'input-0', name: '提示词', type: 'input' as const, dataType: 'string' as const, required: true }], outputs: [{ id: 'output-0', name: '生成文本', type: 'output' as const, dataType: 'string' as const }], config: { model: 'gpt-4', temperature: 0.7 } } },
            { title: td('对话补全'), key: 'llm-chat', icon: <FileOutlined />, isLeaf: true, data: { label: '对话补全', type: 'llm' as const, description: '多轮对话消息补全', inputs: [{ id: 'input-0', name: '消息列表', type: 'input' as const, dataType: 'array' as const, required: true }, { id: 'input-1', name: '系统提示', type: 'input' as const, dataType: 'string' as const, required: false }], outputs: [{ id: 'output-0', name: '回复', type: 'output' as const, dataType: 'string' as const }], config: { model: 'gpt-4', temperature: 0.7, maxTokens: 2048 } } },
            { title: td('文本分类'), key: 'llm-classify', icon: <FileOutlined />, isLeaf: true, data: { label: '文本分类', type: 'llm' as const, description: 'LLM驱动的文本意图/类别分类', inputs: [{ id: 'input-0', name: '文本', type: 'input' as const, dataType: 'string' as const, required: true }, { id: 'input-1', name: '类别列表', type: 'input' as const, dataType: 'array' as const, required: true }], outputs: [{ id: 'output-0', name: '分类结果', type: 'output' as const, dataType: 'string' as const }], config: { model: 'gpt-4' } } },
            { title: td('结构化提取'), key: 'llm-extract', icon: <FileOutlined />, isLeaf: true, data: { label: '结构化提取', type: 'llm' as const, description: '从非结构化文本提取JSON结构', inputs: [{ id: 'input-0', name: '文本', type: 'input' as const, dataType: 'string' as const, required: true }, { id: 'input-1', name: 'JSON Schema', type: 'input' as const, dataType: 'string' as const, required: true }], outputs: [{ id: 'output-0', name: 'JSON结果', type: 'output' as const, dataType: 'string' as const }], config: { model: 'gpt-4' } } },
            { title: td('Embedding向量化'), key: 'llm-embed', icon: <FileOutlined />, isLeaf: true, data: { label: 'Embedding向量化', type: 'llm' as const, description: '文本转向量表示', inputs: [{ id: 'input-0', name: '文本', type: 'input' as const, dataType: 'string' as const, required: true }], outputs: [{ id: 'output-0', name: '向量', type: 'output' as const, dataType: 'array' as const }], config: { model: 'text-embedding-3-small' } } },
            { title: td('知识库检索'), key: 'llm-rag', icon: <FileOutlined />, isLeaf: true, data: { label: '知识库检索', type: 'llm' as const, description: 'RAG检索增强生成', inputs: [{ id: 'input-0', name: '查询', type: 'input' as const, dataType: 'string' as const, required: true }, { id: 'input-1', name: '知识库ID', type: 'input' as const, dataType: 'string' as const, required: true }], outputs: [{ id: 'output-0', name: '检索结果', type: 'output' as const, dataType: 'array' as const }, { id: 'output-1', name: '生成回答', type: 'output' as const, dataType: 'string' as const }], config: { topK: 5 } } },
            { title: td('Agent智能体'), key: 'llm-agent', icon: <FileOutlined />, isLeaf: true, data: { label: 'Agent智能体', type: 'llm' as const, description: '自主规划与工具调用的AI Agent', inputs: [{ id: 'input-0', name: '任务描述', type: 'input' as const, dataType: 'string' as const, required: true }, { id: 'input-1', name: '可用工具', type: 'input' as const, dataType: 'array' as const, required: false }], outputs: [{ id: 'output-0', name: '执行结果', type: 'output' as const, dataType: 'string' as const }, { id: 'output-1', name: '执行日志', type: 'output' as const, dataType: 'array' as const }], config: { model: 'gpt-4', maxIterations: 10, tools: [] } } },
            { title: td('Skill技能调用'), key: 'llm-skill', icon: <FileOutlined />, isLeaf: true, data: { label: 'Skill技能调用', type: 'llm' as const, description: '调用预定义的Agent Skill', inputs: [{ id: 'input-0', name: '技能ID', type: 'input' as const, dataType: 'string' as const, required: true }, { id: 'input-1', name: '参数', type: 'input' as const, dataType: 'string' as const, required: true }], outputs: [{ id: 'output-0', name: '结果', type: 'output' as const, dataType: 'string' as const }], config: { skillId: '' } } },
            { title: td('工具调用'), key: 'llm-tool', icon: <FileOutlined />, isLeaf: true, data: { label: '工具调用', type: 'llm' as const, description: 'Function Calling外部工具', inputs: [{ id: 'input-0', name: '工具名', type: 'input' as const, dataType: 'string' as const, required: true }, { id: 'input-1', name: '参数JSON', type: 'input' as const, dataType: 'string' as const, required: true }], outputs: [{ id: 'output-0', name: '调用结果', type: 'output' as const, dataType: 'string' as const }], config: {} } },
            { title: td('提示词模板'), key: 'llm-prompt', icon: <FileOutlined />, isLeaf: true, data: { label: '提示词模板', type: 'llm' as const, description: '可复用的Prompt模板渲染', inputs: [{ id: 'input-0', name: '模板', type: 'input' as const, dataType: 'string' as const, required: true }, { id: 'input-1', name: '变量', type: 'input' as const, dataType: 'string' as const, required: false }], outputs: [{ id: 'output-0', name: '渲染结果', type: 'output' as const, dataType: 'string' as const }], config: {} } },
          ],
        },
      );
    }

    return tree;
  };

  // 处理搜索
  const handleSearch = (value: string) => {
    setSearchText(value);
    if (value) {
      const allKeys: React.Key[] = [];
      const collectKeys = (nodes: ExtendedTreeDataNode[]) => {
        nodes.forEach((node) => {
          allKeys.push(node.key);
          if (node.children) collectKeys(node.children);
        });
      };
      collectKeys(buildTreeData(value));
      setExpandedKeys(allKeys);
    } else {
      setExpandedKeys([]);
    }
  };

  // 处理拖拽开始
  const handleDragStart = (info: any) => {
    const node = info.node;
    if (node.isLeaf && node.data) {
      const event = info.event as React.DragEvent;
      event.dataTransfer.effectAllowed = 'copy';
      event.dataTransfer.setData('application/reactflow', JSON.stringify(node.data));

      const dragImage = document.createElement('div');
      dragImage.style.position = 'absolute';
      dragImage.style.top = '-9999px';
      dragImage.style.width = '240px';
      dragImage.style.padding = '12px';
      dragImage.style.backgroundColor = 'white';
      dragImage.style.border = '1px solid #e5e7eb';
      dragImage.style.borderRadius = '12px';
      dragImage.style.boxShadow = '0 1px 2px 0 rgba(0, 0, 0, 0.05)';
      const labelText = displayText(String(node.data.label ?? ''));
      dragImage.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="width: 32px; height: 32px; border-radius: 8px; background-color: rgba(41, 112, 255, 0.1); display: flex; align-items: center; justify-content: center; color: #2970ff; font-size: 16px;">fx</div>
          <div style="font-size: 14px; font-weight: 500; color: #1f2937;"></div>
        </div>
      `;
      const labelDiv = dragImage.querySelector('div > div:last-child') as HTMLDivElement | null;
      if (labelDiv) labelDiv.textContent = labelText;
      document.body.appendChild(dragImage);
      event.dataTransfer.setDragImage(dragImage, 120, 20);
      setTimeout(() => document.body.removeChild(dragImage), 0);

      if (onNodeDragStart) onNodeDragStart(event, node.data);
    }
  };

  const treeData = useMemo(
    () => buildTreeData(),
    [searchText, activeLayer, functions, categories, categoryById, funcsByCategory, t, i18n.language, displayText],
  );

  // ---- 节点库 Tab ----
  const renderNodesTab = () => {
    if (loading) {
      return (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip={td('加载AI算法库...')} />
        </div>
      );
    }

    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        <Input
          placeholder={td('搜索算法函数...')}
          prefix={<SearchOutlined />}
          value={searchText}
          onChange={(e) => handleSearch(e.target.value)}
          className="node-library-search"
          allowClear
        />

        <div className="node-library-layer-filter">
          <Select
            size="small"
            value={activeLayer}
            onChange={(val) => {
              setActiveLayer(val);
              setExpandedKeys([]);
            }}
            style={{ width: '100%' }}
            options={layerFilterOptions.map((opt) => ({
              label: (
                <span style={{
                  color: opt.value === ALL_LAYERS_KEY ? '#333' : (LAYER_COLORS[opt.value] || '#333'),
                  fontWeight: 500,
                }}>
                  {opt.label}
                </span>
              ),
              value: opt.value,
            }))}
          />
        </div>

        <div className="node-library-tree-container">
          {treeData.length > 0 ? (
            <Tree
              className="node-library-tree"
              treeData={treeData}
              expandedKeys={expandedKeys}
              onExpand={(keys) => setExpandedKeys(keys)}
              draggable={{ icon: false, nodeDraggable: (node) => node.isLeaf === true }}
              onDragStart={handleDragStart}
              showIcon
              blockNode
            />
          ) : (
            <Empty
              description={td('没有找到匹配的节点')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              style={{ marginTop: 40 }}
            />
          )}
        </div>
      </div>
    );
  };

  // @AI_GENERATED: Kiro v1.0
  // ---- 算法模板 Tab（已保存的模板） ----
  const renderTemplatesTab = () => {
    if (loadingWorkflows) {
      return (
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip={td('加载算法模板...')} />
        </div>
      );
    }

    // 搜索过滤
    const keyword = workflowSearchText.toLowerCase();
    const filteredWorkflows = workflowSearchText.trim()
      ? savedWorkflows.filter((wf) =>
          wf.name.toLowerCase().includes(keyword) ||
          (wf.description || '').toLowerCase().includes(keyword) ||
          td(wf.name).toLowerCase().includes(keyword) ||
          td(wf.description || '').toLowerCase().includes(keyword)
        )
      : savedWorkflows;

    // 加载模板到编辑器
    // @AI_GENERATED: Kiro v1.0
    const handleLoadWorkflow = (wf: EnhancedWorkflow) => {
      if (onApplyWorkflow) {
        const fixedNodes = wf.nodes.map((n) => ({ ...n, type: 'enhanced' }));
        // 传递workflowId以支持直接执行
        onApplyWorkflow(fixedNodes, wf.edges, wf.name, wf.id);
        message.success(`${td('已加载模板')}: ${td(wf.name)}`);
      }
    };
    // @AI_GENERATED: end

    // 删除模板
    const handleDeleteWorkflow = async (wfId: string, e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        await enhancedWorkflowApi.deleteWorkflow(wfId);
        setSavedWorkflows((prev) => prev.filter((w) => w.id !== wfId));
        message.success(td('模板已删除'));
      } catch {
        message.error(td('删除失败'));
      }
    };

    return (
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
        <Input
          placeholder={td('搜索算法模板...')}
          prefix={<SearchOutlined />}
          value={workflowSearchText}
          onChange={(e) => setWorkflowSearchText(e.target.value)}
          allowClear
          style={{ margin: '8px', marginBottom: 0 }}
        />
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
          {filteredWorkflows.length > 0 ? (
            filteredWorkflows.map((wf) => (
              <Card
                key={wf.id}
                size="small"
                hoverable
                style={{ marginBottom: 8, cursor: 'pointer' }}
                bodyStyle={{ padding: '12px' }}
                onClick={() => handleLoadWorkflow(wf)}
              >
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Space>
                      <ThunderboltOutlined style={{ color: '#722ed1' }} />
                      <Text strong>{td(wf.name)}</Text>
                    </Space>
                    <Popconfirm
                      title={td('确定删除此模板？')}
                      onConfirm={(e) => handleDeleteWorkflow(wf.id!, e as any)}
                      onCancel={(e) => e?.stopPropagation()}
                      okText={td('删除')}
                      cancelText={td('取消')}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Popconfirm>
                  </Space>
                  {wf.description && (
                    <Text type="secondary" style={{ fontSize: 12 }}>{td(wf.description)}</Text>
                  )}
                  <Space size={4}>
                    <Tag color="blue">{td('节点')}: {wf.nodes.length}</Tag>
                    <Tag color="green">{td('连接')}: {wf.edges.length}</Tag>
                    {wf.updatedAt && (
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {new Date(wf.updatedAt).toLocaleDateString()}
                      </Text>
                    )}
                  </Space>
                </Space>
              </Card>
            ))
          ) : (
            <Empty
              description={workflowSearchText ? td('没有匹配的模板') : td('暂无算法模板')}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              style={{ marginTop: 40 }}
            >
              {!workflowSearchText && (
                <Button type="primary" size="small" onClick={() => setActiveTab('ai')}>
                  {td('使用 AI 助手创建')}
                </Button>
              )}
            </Empty>
          )}
        </div>
        <div style={{ padding: '8px', borderTop: '1px solid #f0f0f0' }}>
          <Button
            block
            icon={<SyncOutlined />}
            onClick={loadSavedWorkflows}
            loading={loadingWorkflows}
          >
            {td('刷新列表')}
          </Button>
        </div>
      </div>
    );
  };
  // @AI_GENERATED: end

  // ---- AI 助手 Tab ----
  const aiExpandPanel = (key: string) => {
    setAiActiveKeys(prev => prev.includes(key) ? prev : [...prev, key]);
  };

  const handleAiReset = () => {
    setAiDescription('');
    setAiStep('input');
    setAiErrorInfo(null);
    setAiActiveKeys(['step-input']);
    setAiMatches([]);
    setAiSelectedScenario(null);
    setAiRankedTemplates([]);
    setAiSelectedTemplate(null);
    setAiCombinations([]);
    setAiSelectedCombo(null);
    setAiGeneratedWorkflow(null);
    setAiValidationResult(null);
  };

  const handleAiMatch = async () => {
    if (!aiDescription.trim()) {
      setAiErrorInfo({ step: 'input', message: td('请输入业务需求描述'), severity: 'info' });
      return;
    }
    setAiLoading(true);
    setAiStep('matching');
    setAiErrorInfo(null);
    try {
      const res = await workflowAgentApi.matchScenario({ description: aiDescription });
      setAiMatches(res.matches || []);
      if ((res.matches || []).length === 0) {
        setAiErrorInfo({ step: 'matching', message: td('未找到匹配场景，请尝试更详细的描述'), severity: 'info' });
        setAiStep('input');
      } else {
        aiExpandPanel('step-match');
      }
    } catch (e: any) {
      setAiErrorInfo({ step: 'matching', message: td(e?.response?.data?.detail || e?.message || '场景匹配失败') });
    } finally {
      setAiLoading(false);
    }
  };

  const handleAiSelectScenario = async (match: any) => {
    setAiSelectedScenario(match);
    setAiLoading(true);
    setAiStep('select-template');
    setAiErrorInfo(null);
    try {
      const tpls = await industryApi.getTemplates(match.scenario_id);
      if (!tpls || tpls.length === 0) {
        setAiRankedTemplates([]);
        setAiErrorInfo({ step: 'select-template', message: td('该场景暂无业务模板'), severity: 'info' });
      } else {
        setAiRankedTemplates(rankTemplates(tpls, aiDescription, 5));
        aiExpandPanel('step-template');
      }
    } catch (e: any) {
      setAiErrorInfo({ step: 'select-template', message: td(e?.response?.data?.detail || e?.message || '加载模板失败') });
    } finally {
      setAiLoading(false);
    }
  };

  const handleAiSelectTemplate = async (tpl: any) => {
    setAiSelectedTemplate(tpl);
    if (!aiSelectedScenario) return;
    setAiLoading(true);
    setAiStep('composing');
    setAiErrorInfo(null);
    try {
      const res = await workflowAgentApi.composeAlgorithms({
        scenario_id: aiSelectedScenario.scenario_id,
        template_id: tpl.id,
      });
      setAiCombinations(res.combinations || []);
      aiExpandPanel('step-combo');
    } catch (e: any) {
      setAiErrorInfo({ step: 'composing', message: td(e?.response?.data?.detail || e?.message || '算法组合推荐失败') });
    } finally {
      setAiLoading(false);
    }
  };

  const handleAiSelectCombo = async (combo: any) => {
    setAiSelectedCombo(combo);
    if (!aiSelectedScenario) return;
    setAiLoading(true);
    setAiStep('generating');
    setAiErrorInfo(null);
    try {
      const res = await workflowAgentApi.generateWorkflow({
        combination: combo,
        scenario_id: aiSelectedScenario.scenario_id,
      });
      setAiGeneratedWorkflow(res);
      aiExpandPanel('step-generate');
      setAiStep('validating');
      try {
        const vRes = await workflowAgentApi.validateWorkflow({
          workflow: res.workflow,
          scenario_id: aiSelectedScenario.scenario_id,
        });
        setAiValidationResult(vRes);
        setAiStep('done');
      } catch (ve: any) {
        setAiErrorInfo({ step: 'validating', message: td(ve?.response?.data?.detail || ve?.message || '验证失败') });
        setAiStep('done');
      }
    } catch (e: any) {
      setAiErrorInfo({ step: 'generating', message: td(e?.response?.data?.detail || e?.message || '生成失败') });
    } finally {
      setAiLoading(false);
    }
  };

  const handleAiApply = () => {
    if (!aiGeneratedWorkflow?.workflow || !onApplyWorkflow) return;
    const wf = aiGeneratedWorkflow.workflow as any;
    const nodes = transformToEnhancedNodes(wf.nodes || []);
    const edges = transformToEnhancedEdges(wf.edges || []);
    const name = aiSelectedTemplate
      ? `${td(aiSelectedTemplate.name)} - ${td(aiSelectedCombo?.profile || '模板')}`
      : td('智能编排模板');
    onApplyWorkflow(nodes, edges, name);
    message.success(td('已应用到画布'));
  };

  const handleAiMerge = () => {
    if (!aiGeneratedWorkflow?.workflow || !onMergeNodes) return;
    const wf = aiGeneratedWorkflow.workflow as any;
    const nodes = transformToEnhancedNodes(wf.nodes || []);
    const edges = transformToEnhancedEdges(wf.edges || []);
    onMergeNodes(nodes, edges);
    message.success(td('已合并到画布'));
  };

  const handleAiRetry = () => {
    if (!aiErrorInfo) return;
    setAiErrorInfo(null);
    switch (aiErrorInfo.step) {
      case 'matching': handleAiMatch(); break;
      case 'select-template': if (aiSelectedScenario) handleAiSelectScenario(aiSelectedScenario); break;
      case 'composing': if (aiSelectedTemplate) handleAiSelectTemplate(aiSelectedTemplate); break;
      case 'generating':
      case 'validating': if (aiSelectedCombo) handleAiSelectCombo(aiSelectedCombo); break;
    }
  };

  // @AI_GENERATED: Kiro v1.0
  // 获取历史记录
  const { history: aiHistory, deleteHistory: deleteAiHistory } = useWorkflowAgentStore();
  const [showAiHistory, setShowAiHistory] = useState(false);

  // 从历史恢复会话
  const handleAiRestoreFromHistory = (session: AgentSession) => {
    setAiDescription(session.description);
    setAiStep(session.step);
    setAiMatches(session.selectedScenario ? [session.selectedScenario] : []);
    setAiSelectedScenario(session.selectedScenario);
    setAiRankedTemplates(session.selectedTemplate ? [session.selectedTemplate] : []);
    setAiSelectedTemplate(session.selectedTemplate);
    setAiCombinations(session.selectedCombo ? [session.selectedCombo] : []);
    setAiSelectedCombo(session.selectedCombo);
    setAiGeneratedWorkflow(session.generatedWorkflow);
    setAiValidationResult(session.validationResult);
    // 重建 activeKeys
    const keys = ['step-input'];
    if (session.selectedScenario) keys.push('step-match');
    if (session.selectedTemplate) keys.push('step-template');
    if (session.selectedCombo) keys.push('step-combo');
    if (session.generatedWorkflow) keys.push('step-generate');
    setAiActiveKeys(keys);
    setAiErrorInfo(null);
    setShowAiHistory(false);
    message.success(td('已恢复历史会话'));
  };

  // 渲染历史记录列表
  const renderAiHistoryList = () => (
    <div style={{ padding: 16, overflowY: 'auto', flex: 1 }}>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <Space>
          <HistoryOutlined style={{ fontSize: 18, color: '#1890ff' }} />
          <Text strong style={{ fontSize: 16 }}>{td('编排历史')}</Text>
          <Text type="secondary" style={{ fontSize: 13 }}>{td('共')} {aiHistory.length} {td('条记录')}</Text>
        </Space>
        <Button size="small" icon={<ArrowLeftOutlined />} onClick={() => setShowAiHistory(false)}>{td('返回')}</Button>
      </Space>
      {aiHistory.length === 0 ? (
        <Empty description={td('暂无历史记录')} image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ marginTop: 60 }}>
          <Button type="primary" onClick={() => setShowAiHistory(false)}>{td('开始新的编排')}</Button>
        </Empty>
      ) : (
        <div>
          {aiHistory.slice(0, 20).map((session) => (
            <Card
              key={session.id}
              size="small"
              hoverable
              style={{ marginBottom: 8, cursor: 'pointer' }}
              bodyStyle={{ padding: '12px' }}
              onClick={() => handleAiRestoreFromHistory(session)}
            >
              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space>
                    <Text strong>{td(session.description || '未命名编排')}</Text>
                    <Tag color={session.step === 'done' ? 'green' : 'blue'}>
                      {session.step === 'done' ? td('已完成') : td('进行中')}
                    </Tag>
                  </Space>
                  <Popconfirm
                    title={td('确定删除此记录？')}
                    onConfirm={(e) => { e?.stopPropagation(); deleteAiHistory(session.id); }}
                    onCancel={(e) => e?.stopPropagation()}
                    okText={td('删除')}
                    cancelText={td('取消')}
                  >
                    <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={(e) => e.stopPropagation()} />
                  </Popconfirm>
                </Space>
                {session.selectedScenario && (
                  <Text type="secondary" style={{ fontSize: 12 }}>{td('场景')}：{td(session.selectedScenario.scenario_name)}</Text>
                )}
                {session.selectedTemplate && (
                  <Text type="secondary" style={{ fontSize: 12 }}>{td('模板')}：{td(session.selectedTemplate.name)}</Text>
                )}
                {session.generatedWorkflow && (
                  <Space size={4}>
                    <Tag color="blue">{td('节点')}: {session.generatedWorkflow.node_count}</Tag>
                    <Tag color="green">{td('连接')}: {session.generatedWorkflow.edge_count}</Tag>
                    {session.generatedWorkflow.processing_time_ms && (
                      <Text type="secondary" style={{ fontSize: 11 }}>{td('耗时')} {session.generatedWorkflow.processing_time_ms}ms</Text>
                    )}
                  </Space>
                )}
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {new Date(session.createdAt).toLocaleString()}
                </Text>
              </Space>
            </Card>
          ))}
        </div>
      )}
    </div>
  );

  const renderAiTab = () => {
    // 如果显示历史记录列表
    if (showAiHistory) {
      return renderAiHistoryList();
    }

    const conversationItems: { key: string; label: React.ReactNode; children: React.ReactNode }[] = [];

    // 步骤1：需求描述
    conversationItems.push({
      key: 'step-input',
      label: (
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Text strong>{td('① 需求描述')}</Text>
          <Dropdown menu={{
            items: [
              { key: 'tpl', label: <Text type="secondary" style={{ fontSize: 12 }}>{td('📋 Prompt 框架（点击复制）')}</Text>,
                onClick: (e: any) => { e.domEvent?.stopPropagation(); navigator.clipboard.writeText(aiPromptTemplate); message.success(td('已复制 Prompt 框架')); } },
              { type: 'divider' as const },
              ...AI_EXAMPLE_PROMPTS.map((p, i) => ({
                key: `ex-${i}`, label: <Text style={{ fontSize: 12 }}>{td(p)}</Text>,
                onClick: (e: any) => { e.domEvent?.stopPropagation(); setAiDescription(td(p)); message.success(td('已填入示例需求')); },
              })),
            ],
          }} trigger={['click']} placement="bottomRight">
            <Button size="small" type="text" icon={<BulbOutlined />} onClick={(e) => e.stopPropagation()}>
              {td('示例')}
            </Button>
          </Dropdown>
        </Space>
      ),
      children: (
        <div>
          <Tooltip title={td('点击复制 Prompt 框架')} placement="topRight">
            <Tag color="geekblue" style={{ cursor: 'pointer', marginBottom: 8, fontSize: 11 }}
              onClick={() => { navigator.clipboard.writeText(aiPromptTemplate); message.success(td('已复制 Prompt 框架')); }}>
              <CopyOutlined /> {aiPromptTemplate}
            </Tag>
          </Tooltip>
          <TextArea rows={3} placeholder={td('请描述您的业务需求，例如：光伏功率预测')}
            value={aiDescription} onChange={(e) => setAiDescription(e.target.value)}
            disabled={aiStep !== 'input'} style={{ marginBottom: 12 }} />
          <Space>
            <Button type="primary" icon={<SendOutlined />} onClick={handleAiMatch}
              loading={aiLoading && aiStep === 'matching'}
              disabled={aiStep !== 'input' && aiStep !== 'matching'}>
              {td('开始匹配')}
            </Button>
            {aiStep !== 'input' && <Button onClick={handleAiReset}>{td('重新开始')}</Button>}
          </Space>
        </div>
      ),
    });

    // 步骤2：场景匹配
    if (aiMatches.length > 0) {
      conversationItems.push({
        key: 'step-match',
        label: <Space><Text strong>{td('② 场景匹配')}</Text>{aiSelectedScenario && <Tag color="blue">{td(aiSelectedScenario.scenario_name)}</Tag>}</Space>,
        children: aiSelectedScenario ? (
          <Text type="secondary">{td('已选择')}：{td(aiSelectedScenario.scenario_name)}（{aiSelectedScenario.confidence_score}%）</Text>
        ) : (
          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>{td('匹配到')} {aiMatches.length} {td('个行业场景')}：</Text>
            {aiMatches.map((m) => (
              <Card key={m.scenario_id} size="small" hoverable style={{ marginBottom: 8, cursor: 'pointer' }} bodyStyle={{ padding: '12px' }} onClick={() => handleAiSelectScenario(m)}>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space><Text strong>{td(m.scenario_name)}</Text><Tag color="blue">{m.confidence_score}%</Tag></Space>
                  <Progress percent={m.confidence_score} size="small" showInfo={false} />
                  <Text type="secondary" style={{ fontSize: 12 }}>{m.rationale}</Text>
                </Space>
              </Card>
            ))}
          </div>
        ),
      });
    }

    // @AI_GENERATED: Kiro v1.0
    // 步骤3：选择模板 - 样式与原版 WorkflowAgentPage 完全一致
    if (aiSelectedScenario && aiRankedTemplates.length > 0) {
      conversationItems.push({
        key: 'step-template',
        label: <Space><Text strong>{td('③ 选择模板')}</Text>{aiSelectedTemplate && <Tag color="purple">{td(aiSelectedTemplate.name)}</Tag>}</Space>,
        children: aiSelectedTemplate ? (
          <Text type="secondary">{td('已选择')}：{td(aiSelectedTemplate.name)}</Text>
        ) : (
          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>{td('推荐前')} {aiRankedTemplates.length} {td('个模板')}：</Text>
            {aiRankedTemplates.map((tpl, idx) => (
              <Card key={tpl.id} size="small" hoverable style={{ cursor: 'pointer', marginBottom: 8 }} bodyStyle={{ padding: '12px' }} onClick={() => handleAiSelectTemplate(tpl)}>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space>
                    {idx === 0 && <Tag color="red">{td('最佳匹配')}</Tag>}
                    {idx > 0 && idx < 3 && <Tag color="orange">{td('推荐')}</Tag>}
                    <Text strong>{td(tpl.name)}</Text>
                    <Tag color="purple">{td(tpl.display_category)}</Tag>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>{td(tpl.description || '暂无描述')}</Text>
                  {tpl.relevanceScore > 0 && <Progress percent={Math.min(tpl.relevanceScore, 100)} size="small" showInfo={false}
                    strokeColor={idx === 0 ? '#ff4d4f' : idx < 3 ? '#faad14' : '#1890ff'} />}
                </Space>
              </Card>
            ))}
          </div>
        ),
      });
    }
    // @AI_GENERATED: end

    // 步骤4：方案推荐
    if (aiSelectedTemplate && aiCombinations.length > 0) {
      conversationItems.push({
        key: 'step-combo',
        label: (
          <Space><Text strong>{td('④ 方案推荐')}</Text>
            {aiSelectedCombo && <Tag color={aiSelectedCombo.profile === 'high-accuracy' ? 'green' : aiSelectedCombo.profile === 'balanced' ? 'blue' : 'orange'}>
              {aiSelectedCombo.profile === 'high-accuracy' ? td('高精度') : aiSelectedCombo.profile === 'balanced' ? td('均衡') : td('低延迟')}
            </Tag>}
          </Space>
        ),
        children: aiSelectedCombo ? (
          <Text type="secondary">{td('已选择')}：{aiSelectedCombo.profile === 'high-accuracy' ? td('高精度方案') : aiSelectedCombo.profile === 'balanced' ? td('均衡方案') : td('低延迟方案')}（{aiSelectedCombo.overall_confidence}%）</Text>
        ) : (
          <div>
            {aiCombinations.map((c, idx) => {
              const color = c.profile === 'high-accuracy' ? '#52c41a' : c.profile === 'balanced' ? '#1890ff' : '#fa8c16';
              const label = c.profile === 'high-accuracy' ? td('高精度方案') : c.profile === 'balanced' ? td('均衡方案') : td('低延迟方案');
              return (
                <Card key={c.combination_id} size="small" style={{ marginBottom: 8, borderLeft: `3px solid ${color}` }}
                  bodyStyle={{ padding: '12px' }}
                  title={<Space><Tag color={c.profile === 'high-accuracy' ? 'green' : c.profile === 'balanced' ? 'blue' : 'orange'}>{label}</Tag>
                    {idx === 0 && <Tag color="red">{td('推荐')}</Tag>}
                    <Text type="secondary" style={{ fontSize: 12 }}>{td('置信度')} {c.overall_confidence}%</Text></Space>}
                  extra={<Button type="primary" size="small" onClick={() => handleAiSelectCombo(c)}>{td('选择')}</Button>}>
                  {c.layers.map((layer: any) => (
                    <div key={layer.layer_name} style={{ marginBottom: 4 }}>
                      <Text strong style={{ fontSize: 12 }}>{td(layer.layer_name)}：</Text>
                      {layer.algorithms.map((a: any) => <Tag key={a.algorithm_id} style={{ marginBottom: 2 }}>{td(a.algorithm_name)}</Tag>)}
                    </div>
                  ))}
                </Card>
              );
            })}
          </div>
        ),
      });
    }

    // 步骤5：生成结果
    if (aiGeneratedWorkflow) {
      const vr = aiValidationResult;
      conversationItems.push({
        key: 'step-generate',
        label: (
          <Space>
            <Text strong>{td('⑤ 生成算法模板')}</Text>
            <Tag color="blue">{td('节点')}: {aiGeneratedWorkflow.node_count}</Tag>
            <Tag color="green">{td('连接')}: {aiGeneratedWorkflow.edge_count}</Tag>
            {vr && <Tag color={vr.readiness_score >= 80 ? 'green' : vr.readiness_score >= 50 ? 'orange' : 'red'}>{td('就绪度')}: {vr.readiness_score}%</Tag>}
          </Space>
        ),
        children: (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text style={{ fontSize: 13 }}>{td(aiGeneratedWorkflow.generation_summary)}</Text>
            <Space>
              <Tag color="blue">{td('节点')}: {aiGeneratedWorkflow.node_count}</Tag>
              <Tag color="green">{td('连接')}: {aiGeneratedWorkflow.edge_count}</Tag>
              <Tag>{td('耗时')}: {aiGeneratedWorkflow.processing_time_ms}ms</Tag>
            </Space>
            <Divider style={{ margin: '8px 0' }} />
            <Space>
              <Tooltip title={td('替换当前画布')}>
                <Button type="primary" icon={<SyncOutlined />} onClick={handleAiApply} disabled={!onApplyWorkflow}>
                  {td('应用')}
                </Button>
              </Tooltip>
              <Tooltip title={td('合并到画布')}>
                <Button icon={<PlusOutlined />} onClick={handleAiMerge} disabled={!onMergeNodes}>
                  {td('合并')}
                </Button>
              </Tooltip>
            </Space>
          </Space>
        ),
      });
    }

    return (
      <div style={{ padding: 16, overflowY: 'auto', flex: 1 }}>
        {/* 顶部标题栏 */}
        <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <Space>
            <RobotOutlined style={{ fontSize: 18 }} />
            <Text strong style={{ fontSize: 16 }}>{td('智能编排助手')}</Text>
          </Space>
          <Space size={8}>
            <Button size="small" icon={<PlusOutlined />} onClick={() => { handleAiReset(); message.success(td('已开启新对话')); }}>
              {td('新对话')}
            </Button>
            <Button size="small" onClick={() => setShowAiHistory(true)}>
              {td('历史记录')}
            </Button>
          </Space>
        </Space>

        {/* Collapse 面板 */}
        <Collapse
          activeKey={aiActiveKeys}
          onChange={(keys) => setAiActiveKeys(keys as string[])}
          items={conversationItems}
          size="small"
          style={{ background: '#fff' }}
        />

        {aiLoading && <Spin style={{ display: 'block', marginTop: 16 }} />}

        {aiErrorInfo && !aiLoading && (() => {
          const isInfo = aiErrorInfo.severity === 'info';
          const borderColor = isInfo ? '#1890ff' : '#ff4d4f';
          return (
            <Card size="small" style={{ marginTop: 12, borderLeft: `3px solid ${borderColor}` }}
              bodyStyle={{ padding: '12px 16px' }}
              title={<Space>{isInfo ? <InfoCircleOutlined style={{ color: '#1890ff' }} /> : <WarningOutlined style={{ color: '#ff4d4f' }} />}
                <Text type={isInfo ? 'secondary' : 'danger'}>{isInfo ? td('提示') : td('操作失败')}</Text></Space>}>
              <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>{aiErrorInfo.message}</Text>
              <Space>
                <Button type="primary" size="small" onClick={handleAiRetry}>{td('重试')}</Button>
                <Button size="small" onClick={handleAiReset}>{td('重新开始')}</Button>
              </Space>
            </Card>
          );
        })()}
      </div>
    );
  };
  // @AI_GENERATED: end

  return (
    <Card
      className="node-library-panel"
      title={null}
      bodyStyle={{ padding: 0, display: 'flex', flexDirection: 'column', height: '100%' }}
    >
      <Tabs
        activeKey={activeTab}
        onChange={handleTabChange}
        size="small"
        style={{ padding: '0 8px', flex: 1, display: 'flex', flexDirection: 'column' }}
        destroyInactiveTabPane={false}
        items={[
          {
            key: 'nodes',
            label: <span><AppstoreOutlined /> {td('节点库')}</span>,
            children: renderNodesTab(),
          },
          {
            key: 'ai',
            label: <span><RobotOutlined /> {td('AI助手')}</span>,
            children: renderAiTab(),
          },
          {
            key: 'templates',
            label: <span><ThunderboltOutlined /> {td('算法模板')}</span>,
            children: renderTemplatesTab(),
          },
        ]}
      />
    </Card>
  );
};

export default NodeLibraryPanelV2;
// @AI_GENERATED: end
