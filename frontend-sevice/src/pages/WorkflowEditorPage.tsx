// @AI_GENERATED: Kiro v1.0
import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useSearchParams, useNavigate, useLocation } from 'react-router-dom';
import { Layout, Button, Space, Input, message, Modal, List, Drawer, Descriptions, Tag, Collapse, Typography, Tabs, Spin } from 'antd';
import { PlayCircleOutlined, SaveOutlined, FolderOpenOutlined, CheckCircleOutlined, CloseCircleOutlined, BarChartOutlined, SettingOutlined, StopOutlined } from '@ant-design/icons';
// @AI_GENERATED: end
import { useWorkflowEditorStore } from '../stores/workflowEditorStore';
import EnhancedCanvas from '../components/workflow-enhanced/EnhancedCanvas';
import NodeLibraryPanelV2 from '../components/workflow-enhanced/NodeLibraryPanelV2';
import PropertyPanelV2 from '../components/workflow-enhanced/PropertyPanelV2';
import { enhancedWorkflowApi } from '../services/workflowEnhancedApi';
import type { EnhancedWorkflowSummary } from '../types/workflow-enhanced';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { td } from '../utils/dataTranslation';
import OperatorConfigPanel from '../components/workflow-enhanced/OperatorConfigPanel';
import WorkflowGlobalConfigPanel from '../components/workflow-enhanced/WorkflowGlobalConfigPanel';
import PipelineTemplateMenu from '../components/workflow-enhanced/PipelineTemplateMenu';
import PipelineProgressTracker from '../components/workflow-enhanced/PipelineProgressTracker';
import PipelineLogConsole from '../components/workflow-enhanced/PipelineLogConsole';
import TrainingResultDashboard from '../components/workflow-enhanced/TrainingResultDashboard';
import PredictionResultDashboard from '../components/workflow-enhanced/PredictionResultDashboard';
import BacktestResultDashboard from '../components/workflow-enhanced/BacktestResultDashboard';
import ExecutionHistoryPanel from '../components/workflow-enhanced/ExecutionHistoryPanel';
import { usePipelineExecutionStore } from '../stores/pipelineExecutionStore';
import { useWorkflowRunNavStore } from '../stores/workflowRunNavStore';
import { functionLibraryApi, pipelineApi, baselineCompareApi } from '../services/workflowEnhancedApi';
import { startWorkflowExecutionPoll, stopWorkflowExecutionPollAll } from '../services/workflowExecutionPoll';
import { runQuickBacktest, stopQuickBacktest } from '../services/workflowQuickBacktest';
import type { FunctionDefinition } from '../types/function';
import type { PipelineTemplate, NodeExecutionStatus } from '../types/pipeline';
import { buildGlobalConfigPatchFromBestRecommendation } from '../utils/tuningRecommendation';
import { reviewSessionApi } from '../services/iterativeLabelingApi';
// @AI_GENERATED: end
import './WorkflowEditorPage.css';
// @AI_GENERATED
import dayjs from 'dayjs';
// @AI_GENERATED: end

const { Sider, Content, Header } = Layout;

/**
 * 算法模板编辑器页面（标准版）
 * 
 * 集成 Dify 的算法模板编排能力，提供稳定的算法模板编辑功能
 * 使用独立的状态管理，与增强版算法模板页面数据隔离
 */
const WorkflowEditorPage: React.FC = () => {
  const { id: routeId } = useParams<{ id: string }>();
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  // @AI_GENERATED: Kiro v1.0
  // 同时支持路径参数和查询参数
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryId = searchParams.get('id');
  const effectiveId = routeId || queryId;
  const location = useLocation();
  // @AI_GENERATED: end
  const {
    nodes,
    edges,
    workflowId,
    workflowName,
    selectedNodeId,
    isExecuting,
    setNodes,
    setEdges,
    setSelectedNodeId,
    setWorkflowName,
    setIsExecuting,
    setExecutionResult,
    loadWorkflow,
    addNode,
  } = useWorkflowEditorStore();

  const [openModalVisible, setOpenModalVisible] = useState(false);
  const [workflows, setWorkflows] = useState<EnhancedWorkflowSummary[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);
  const [openingWorkflowId, setOpeningWorkflowId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // @AI_GENERATED: Kiro v1.0
  const [resultDrawerVisible, setResultDrawerVisible] = useState(false);
  const [latestResult, setLatestResult] = useState<any>(null);
  const [nodeLibraryReady, setNodeLibraryReady] = useState(false);
  const [reviewLabelingLoading, setReviewLabelingLoading] = useState(false);
  const [slotModalVisible, setSlotModalVisible] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState('default');
  // @AI_GENERATED: end

  // @AI_GENERATED
  // Pipeline integration state
  const [globalConfigVisible, setGlobalConfigVisible] = useState(false);
  const [operatorPanelVisible, setOperatorPanelVisible] = useState(false);
  const [selectedFunctionDef, setSelectedFunctionDef] = useState<FunctionDefinition | null>(null);
  const [bottomPanelVisible, setBottomPanelVisible] = useState(false);
  const [bottomPanelHeight, setBottomPanelHeight] = useState(260);
  const [isResizingBottomPanel, setIsResizingBottomPanel] = useState(false);
  const bottomResizeStartYRef = React.useRef(0);
  const bottomResizeStartHeightRef = React.useRef(260);
  // @AI_GENERATED
  // @AI_GENERATED: end
  const pipelineStore = usePipelineExecutionStore();
  const [productionWorkflowId, setProductionWorkflowId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    baselineCompareApi
      .getProductionWorkflowRef()
      .then((reg) => {
        if (cancelled) return;
        const slot = reg?.slots?.default as { workflow_id?: string } | undefined;
        const wid = slot?.workflow_id ? String(slot.workflow_id) : null;
        setProductionWorkflowId(wid);
      })
      .catch(() => {
        if (!cancelled) setProductionWorkflowId(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const openBaselineComparePage = useCallback(() => {
    const q = new URLSearchParams();
    if (workflowId) q.set('challenger', workflowId);
    if (productionWorkflowId) q.set('baseline', productionWorkflowId);
    navigate(`/workflow/baseline-compare?${q.toString()}`);
  }, [navigate, workflowId, productionWorkflowId]);

  const applyBacktestModeIfNeeded = useCallback((templateIdOrName: string) => {
    const normalized = String(templateIdOrName || '').toLowerCase();
    const isBacktestTemplate =
      normalized.includes('backtest') ||
      String(templateIdOrName || '').includes('回测');
    if (!isBacktestTemplate) return;
    pipelineStore.updateGlobalConfig({
      run_mode: 'backtest',
      operate_status: 'backtest',
      backtest_mode: 'rolling_retrain',
      backtest_apply_window_filter: true,
      backtest_mask_target_values: true,
    });
  }, [pipelineStore]);

  const nodeStatusList: NodeExecutionStatus[] = Object.values(pipelineStore.nodeStatuses);
  const currentNodeId = nodeStatusList.find((n) => n.status === 'running')?.nodeId || null;

  // Sync pipeline node statuses to canvas node visual states
  useEffect(() => {
    if (Object.keys(pipelineStore.nodeStatuses).length === 0) return;
    const updatedNodes = nodes.map((n) => {
      const ns = pipelineStore.nodeStatuses[n.id];
      if (!ns) return n;
      const statusMap: Record<string, 'idle' | 'running' | 'success' | 'error'> = {
        waiting: 'idle', running: 'running', completed: 'success', failed: 'error',
      };
      return {
        ...n,
        data: { ...n.data, status: statusMap[ns.status] || 'idle', error: ns.error },
      };
    });
    // Only update if something actually changed
    const changed = updatedNodes.some((n, i) => n.data.status !== nodes[i]?.data?.status);
    if (changed) setNodes(updatedNodes);
  }, [pipelineStore.nodeStatuses]);
  // @AI_GENERATED: end

  const expandBottomPanelOnNextEditorVisit = useWorkflowRunNavStore((s) => s.expandBottomPanelOnNextEditorVisit);
  useEffect(() => {
    if (!expandBottomPanelOnNextEditorVisit) return;
    useWorkflowRunNavStore.setState({ expandBottomPanelOnNextEditorVisit: false });
    setBottomPanelVisible(true);
  }, [expandBottomPanelOnNextEditorVisit]);

  // @AI_GENERATED: Kiro v1.0
  // 路由参数自动加载算法模板（用 ref 防止重复加载）
  const loadedRouteIdRef = React.useRef<string | null>(null);
  useEffect(() => {
    if (effectiveId && effectiveId !== loadedRouteIdRef.current) {
      loadedRouteIdRef.current = effectiveId;
      enhancedWorkflowApi.loadWorkflow(effectiveId).then((wf) => {
        const fixedNodes = wf.nodes.map((n) => ({
          ...n,
          type: 'enhanced',
        }));
        loadWorkflow(wf.id!, fixedNodes, wf.edges, wf.name, wf.description || '');
        applyBacktestModeIfNeeded(`${wf.id || ''} ${wf.name || ''}`);
        message.success(t('workflow.templateLoaded', { name: td(wf.name) }));
      }).catch(() => {
        loadedRouteIdRef.current = null;
        message.error(t('workflow.templateLoadFailed'));
      });
    }
  }, [effectiveId, loadWorkflow, applyBacktestModeIfNeeded, t]);
  // @AI_GENERATED: end

  // 处理节点变化
  const handleNodesChange = (newNodes: any[]) => {
    setNodes(newNodes);
  };

  // 处理连接线变化
  const handleEdgesChange = (newEdges: any[]) => {
    setEdges(newEdges);
  };

  // 处理节点选择
  const handleNodeSelect = (nodeId: string | null) => {
    setSelectedNodeId(nodeId);
    // @AI_GENERATED
    // Open operator config panel on node click — always reopen for function nodes
    if (nodeId) {
      const node = nodes.find((n) => n.id === nodeId);
      const funcId = node?.data?.config?.functionId;
      if (funcId) {
        // 先设为 true 确保 Drawer 打开（即使是同一节点再次点击）
        setOperatorPanelVisible(true);
        functionLibraryApi.getFunction(funcId).then((def) => {
          setSelectedFunctionDef(def);
        }).catch(() => {
          setSelectedFunctionDef(null);
        });
      } else {
        setOperatorPanelVisible(false);
        setSelectedFunctionDef(null);
      }
    } else {
      setOperatorPanelVisible(false);
      setSelectedFunctionDef(null);
    }
    // @AI_GENERATED: end
  };

  // 处理节点添加
  const handleNodeAdd = (node: any) => {
    addNode(node);
  };

  const applyLocalParityPresetToNodes = useCallback(() => {
    const updated = nodes.map((node) => {
      const cfg = { ...(node.data?.config || {}) };
      const fid = cfg.functionId;
      if (fid === 'xgboost_forecast') {
        cfg.local_parity_mode = false;
        cfg.output_prefix = 'xgb';
        cfg.auto_tune = false;
      } else if (fid === 'lightgbm_forecast') {
        cfg.output_prefix = 'lgb';
        cfg.use_bayesian_tuning = true;
        cfg.bo_init_points = 3;
        cfg.bo_n_iter = 12;
        cfg.allow_missing_dependency = true;
      } else if (fid === 'catboost_forecast') {
        cfg.output_prefix = 'catb';
        cfg.use_bayesian_tuning = true;
        cfg.bo_init_points = 3;
        cfg.bo_n_iter = 12;
        cfg.allow_missing_dependency = true;
      } else if (fid === 'ridge_forecast') {
        cfg.output_prefix = 'ridge';
        cfg.alpha = 1.0;
      } else if (fid === 'ensemble_forecast') {
        cfg.prediction_keys = 'y_pred_xgb,y_pred_lgb,y_pred_catb,y_pred_ridge';
        if (!cfg.weights) {
          cfg.weights = '';
        }
      } else {
        return node;
      }
      return {
        ...node,
        data: {
          ...node.data,
          config: cfg,
        },
      };
    });
    setNodes(updated);
  }, [nodes, setNodes]);

  // 保存算法模板
  const handleSave = async () => {
    if (nodes.length === 0) {
      message.warning(t('workflow.noNodes'));
      return;
    }

    try {
      setSaving(true);
      
      // 添加详细日志
      console.log('=== 保存算法模板 ===');
      console.log('算法模板名称:', workflowName);
      console.log('节点数量:', nodes.length);
      console.log('连接线数量:', edges.length);
      
      // 清理节点数据，移除React Flow添加的额外字段
      const cleanedNodes = nodes.map(node => ({
        id: node.id,
        type: node.type,
        position: node.position,
        data: node.data
      }));
      
      // 清理连接线数据，确保有id字段
      const cleanedEdges = edges.map((edge, index) => ({
        id: edge.id || `edge-${index}`,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle || null,
        targetHandle: edge.targetHandle || null,
        type: edge.type || 'smoothstep',
        data: edge.data || undefined
      }));
      
      console.log('清理后的节点数据:', JSON.stringify(cleanedNodes, null, 2));
      console.log('清理后的连接线数据:', JSON.stringify(cleanedEdges, null, 2));
      
      if (workflowId) {
        // 更新现有算法模板
        await enhancedWorkflowApi.updateWorkflow(workflowId, {
          name: workflowName,
          nodes: cleanedNodes,
          edges: cleanedEdges,
        });
        message.success(t('workflow.templateUpdated'));
      } else {
        // 保存新算法模板
        const savedWorkflow = await enhancedWorkflowApi.saveWorkflow({
          name: workflowName,
          nodes: cleanedNodes,
          edges: cleanedEdges,
        });
        loadWorkflow(
          savedWorkflow.id!,
          savedWorkflow.nodes,
          savedWorkflow.edges,
          savedWorkflow.name,
          savedWorkflow.description || ''
        );
        message.success(t('workflow.templateSaved'));
      }
    } catch (error) {
      console.error('Save workflow error:', error);
      // 显示更详细的错误信息
      if (error instanceof Error) {
        const axiosError = error as any;
        if (axiosError.response) {
          console.error('错误响应:', axiosError.response.data);
          message.error(`${t('workflow.templateSaveFailed')}: ${axiosError.response.data.detail || axiosError.message}`);
        } else {
          message.error(`${t('workflow.templateSaveFailed')}: ${error.message}`);
        }
      } else {
        message.error(t('workflow.templateSaveFailed'));
      }
    } finally {
      setSaving(false);
    }
  };

  // 打开算法模板列表
  const handleOpen = async () => {
    try {
      setLoadingWorkflows(true);
      setOpenModalVisible(true);
      const workflowList = await enhancedWorkflowApi.listWorkflowSummaries();
      setWorkflows(workflowList);
    } catch (error) {
      console.error('Load workflows error:', error);
      message.error(t('workflow.loadListFailed'));
    } finally {
      setLoadingWorkflows(false);
    }
  };

  // 加载选中的算法模板
  const handleLoadWorkflow = async (workflow: EnhancedWorkflowSummary) => {
    try {
      setOpeningWorkflowId(workflow.id);
      const fullWorkflow = await enhancedWorkflowApi.loadWorkflow(workflow.id);
      // @AI_GENERATED: Kiro v1.0
      // 确保所有节点使用 'enhanced' 类型以匹配自定义渲染器
      const fixedNodes = fullWorkflow.nodes.map((n) => ({
        ...n,
        type: 'enhanced',
      }));
      loadWorkflow(
        fullWorkflow.id!,
        fixedNodes,
        fullWorkflow.edges,
        fullWorkflow.name,
        fullWorkflow.description || ''
      );
      applyBacktestModeIfNeeded(`${fullWorkflow.id || ''} ${fullWorkflow.name || ''}`);
      // @AI_GENERATED: end
      setOpenModalVisible(false);
      message.success(t('workflow.templateLoaded', { name: td(workflow.name) }));
    } catch (error) {
      console.error('Load workflow error:', error);
      message.error(t('workflow.templateLoadFailed'));
    } finally {
      setOpeningWorkflowId(null);
    }
  };

  // @AI_GENERATED: Kiro v1.0
  // 执行算法模板
  // @AI_GENERATED
  const setState = usePipelineExecutionStore.setState;
  // @AI_GENERATED: end

  // @AI_GENERATED
  const pendingResultDrawer = usePipelineExecutionStore((s) => s.pendingResultDrawer);
  useEffect(() => {
    if (!pendingResultDrawer) return;
    setLatestResult(pendingResultDrawer.payload as Record<string, unknown>);
    setResultDrawerVisible(true);
    usePipelineExecutionStore.setState({ pendingResultDrawer: null });
  }, [pendingResultDrawer]);

  const handleStopExecution = () => {
    stopWorkflowExecutionPollAll();
    // @AI_GENERATED
    // 通知后端取消执行
    const execId = usePipelineExecutionStore.getState().executionId;
    if (execId && workflowId) {
      fetch(`/api/workflows/enhanced/${workflowId}/cancel/${execId}`, { method: 'POST' }).catch(() => {});
    }
    // @AI_GENERATED: end
    usePipelineExecutionStore.setState({ executionStatus: 'failed', isExecuting: false });
    setIsExecuting(false);
    useWorkflowRunNavStore.getState().clearActiveRun();
    message.warning(t('workflow.trainingStopped'));
  };
  // @AI_GENERATED: end

  const handleExecute = async () => {
    if (nodes.length === 0) {
      message.warning(t('workflow.addNodesFirst'));
      return;
    }

    if (!workflowId) {
      message.warning(t('workflow.saveFirst'));
      return;
    }

    const cfg = pipelineStore.globalConfig || {};
    const runMode = String(cfg.run_mode || cfg.operate_status || '').toLowerCase();
    const isBacktestMode = runMode === 'backtest';
    const isTuningMode = runMode === 'tuning';
    if (isBacktestMode || isTuningMode) {
      const startDate = String(cfg.backtest_start_date || '').trim();
      const endDate = String(cfg.backtest_end_date || '').trim();
      if (!startDate || !endDate) {
        Modal.warning({
          title: t('workflow.workflowSettings'),
          content: t('backtest.selectRangePrompt'),
        });
        return;
      }
      setBottomPanelVisible(true);
      usePipelineExecutionStore.setState((s) => ({
        executionStatus: 'running',
        logs: [
          ...s.logs,
          {
            timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
            message: `▶ 开始回测: ${startDate} ~ ${endDate}`,
            type: 'start',
          },
        ],
      }));
      message.info(t('backtest.startDaysBacktest', { days: '-', start: startDate, end: endDate }));
      runQuickBacktest({
        workflowId,
        returnHref: `${location.pathname}${location.search}`,
        workflowName,
        templateType: isTuningMode ? 'tuning' : 'backtest',
        startDate,
        endDate,
        trainDays: cfg.backtest_train_days,
        dailyHorizon: cfg.backtest_daily_horizon,
        generateArtifacts: isTuningMode ? false : cfg.backtest_generate_artifacts,
        outputDir: cfg.backtest_output_dir,
        applyWindowFilter: cfg.backtest_apply_window_filter,
        maskTargetValues: cfg.backtest_mask_target_values,
        backtestMode: cfg.backtest_mode,
        modelRef: cfg.backtest_model_ref,
        useReferenceEngine: cfg.use_reference_rolling_engine,
        strictAlignmentMode: cfg.strict_alignment_mode,
        tuningCandidates: isTuningMode ? cfg.tuning_candidates : undefined,
      });
      return;
    }

    // @AI_GENERATED
    // 异步执行 + 轮询模式：实时更新日志和节点状态（轮询在全局模块中，离开本页不停止）
    stopWorkflowExecutionPollAll();
    useWorkflowRunNavStore.getState().clearActiveRun();
    setIsExecuting(true);
    setBottomPanelVisible(true);
    pipelineStore.reset();
    setState({
      executionStatus: 'pending',
      isExecuting: true,
      pipelinePlannedNodeCount: Math.max(1, nodes.length),
      logs: [{ timestamp: new Date().toLocaleTimeString('zh-CN', {hour12:false}), message: t('workflow.pipelineStarting'), type: 'config' as const }],
    });

    try {
      const { execution_id } = await pipelineApi.executeAsync(workflowId, { live_nodes: nodes });
      setState({ executionId: execution_id, executionStatus: 'running' });
      useWorkflowRunNavStore.getState().setActiveRun(
        `${location.pathname}${location.search}`,
        workflowName,
        'pipeline',
        workflowId,
      );
      startWorkflowExecutionPoll(workflowId, execution_id);

    } catch (error) {
      console.error('Execute workflow error:', error);
      stopWorkflowExecutionPollAll();
      setState({ executionStatus: 'failed', isExecuting: false });
      setIsExecuting(false);
      useWorkflowRunNavStore.getState().clearActiveRun();
      message.error(t('workflow.executeFailed'));
    }
    // @AI_GENERATED: end
  };
  // @AI_GENERATED: end

  useEffect(() => {
    return () => {
      usePipelineExecutionStore.getState().stopPolling();
    };
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => setNodeLibraryReady(true), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!isResizingBottomPanel) return;

    const previousUserSelect = document.body.style.userSelect;
    const previousCursor = document.body.style.cursor;
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'row-resize';

    const handleMouseMove = (event: MouseEvent) => {
      const deltaY = bottomResizeStartYRef.current - event.clientY;
      const maxHeight = Math.max(320, window.innerHeight - 180);
      const nextHeight = Math.min(
        maxHeight,
        Math.max(180, bottomResizeStartHeightRef.current + deltaY),
      );
      setBottomPanelHeight(nextHeight);
    };

    const handleMouseUp = () => {
      setIsResizingBottomPanel(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = previousUserSelect;
      document.body.style.cursor = previousCursor;
    };
  }, [isResizingBottomPanel]);

  const handleBottomPanelResizeStart = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    bottomResizeStartYRef.current = event.clientY;
    bottomResizeStartHeightRef.current = bottomPanelHeight;
    setIsResizingBottomPanel(true);
  };

  // @AI_GENERATED: Kiro v1.0
  // AI 助手：应用生成的模板（替换当前画布）
  const handleApplyWorkflow = useCallback((newNodes: any[], newEdges: any[], name: string, id?: string) => {
    setNodes(newNodes);
    setEdges(newEdges);
    setWorkflowName(name);
    setSelectedNodeId(null);
    // 如果传入了workflowId，也设置它（用于从模板库加载已保存的模板）
    if (id) {
      loadWorkflow(id, newNodes, newEdges, name, '');
    }
  }, [setNodes, setEdges, setWorkflowName, setSelectedNodeId, loadWorkflow]);
  // @AI_GENERATED: end

  // AI 助手：合并节点到当前画布
  const handleMergeNodes = useCallback((newNodes: any[], newEdges: any[]) => {
    // 计算偏移量，避免节点重叠
    const existingMaxX = nodes.reduce((max, n) => Math.max(max, n.position?.x || 0), 0);
    const offsetX = existingMaxX + 300;
    
    // 为新节点生成唯一 ID 并偏移位置
    const idMap: Record<string, string> = {};
    const mergedNodes = newNodes.map((node, idx) => {
      const newId = `merged-${Date.now()}-${idx}`;
      idMap[node.id] = newId;
      return {
        ...node,
        id: newId,
        position: {
          x: (node.position?.x || 0) + offsetX,
          y: node.position?.y || 0,
        },
      };
    });
    
    // 更新边的引用
    const mergedEdges = newEdges.map((edge, idx) => ({
      ...edge,
      id: `merged-edge-${Date.now()}-${idx}`,
      source: idMap[edge.source] || edge.source,
      target: idMap[edge.target] || edge.target,
    }));
    
    setNodes([...nodes, ...mergedNodes]);
    setEdges([...edges, ...mergedEdges]);
  }, [nodes, edges, setNodes, setEdges]);
  // @AI_GENERATED: end

  // @AI_GENERATED
  // Handle pipeline template selection
  const handleTemplateSelect = useCallback((template: PipelineTemplate) => {
    const newNodes = template.nodes.map((tn, idx) => ({
      id: `tpl-${tn.operatorId}-${idx}`,
      type: 'enhanced',
      position: tn.position,
      data: {
        label: tn.label,
        type: 'function' as const,
        inputs: [{ id: 'input-0', name: 'data', type: 'input' as const, dataType: 'any' as const }],
        outputs: [{ id: 'output-0', name: 'data', type: 'output' as const, dataType: 'any' as const }],
        config: { functionId: tn.operatorId, ...tn.defaultParams, ...tn.advancedParams },
        description: tn.description || null,
      },
    }));
    const newEdges = template.edges.map((te, idx) => {
      const srcIdx = template.nodes.findIndex((n) => n.operatorId === te.sourceOperator);
      const tgtIdx = template.nodes.findIndex((n) => n.operatorId === te.targetOperator);
      return {
        id: `tpl-edge-${idx}`,
        source: `tpl-${te.sourceOperator}-${srcIdx}`,
        target: `tpl-${te.targetOperator}-${tgtIdx}`,
        type: 'smoothstep',
      };
    });
    setNodes(newNodes);
    setEdges(newEdges);
    setWorkflowName(template.name);
    pipelineStore.updateGlobalConfig(template.defaultGlobalConfig);
    if (template.type === 'backtest') {
      pipelineStore.updateGlobalConfig({
        run_mode: 'backtest',
        operate_status: 'backtest',
        backtest_mode: 'rolling_retrain',
        backtest_apply_window_filter: true,
        backtest_mask_target_values: true,
      });
    } else if (template.type === 'prediction') {
      pipelineStore.updateGlobalConfig({
        run_mode: 'prediction',
        operate_status: 'prediction',
      });
    } else if (template.type === 'tuning') {
      pipelineStore.updateGlobalConfig({
        run_mode: 'tuning',
        operate_status: 'tuning',
      });
    } else {
      pipelineStore.updateGlobalConfig({
        run_mode: 'training',
        operate_status: 'training',
      });
    }
    message.success(t('workflow.templateSelected', { name: td(template.name) }));
  }, [setNodes, setEdges, setWorkflowName, pipelineStore, t]);

  // 人工审查打标：从预测结果创建审核会话并跳转打标页（编辑器驱动迭代标注闭环）
  const FAULT_LABEL_NAMES: Record<string, string> = {
    '0': '正常', '1': '组串遮挡', '4': '直流侧异常', '7': '汇流箱告警',
    '8': '汇流箱故障', '11': '组串开路', '12': '组串短路', '16': '其他故障',
  };

  const handleReviewLabelingClick = useCallback(() => {
    const predResult = pipelineStore.predictionResult;
    if (!predResult?.faultPredictions?.length) {
      message.warning('当前没有可用于打标的预测结果');
      return;
    }
    setSlotModalVisible(true);
  }, [pipelineStore.predictionResult]);

  const handleReviewLabelingConfirm = useCallback(async () => {
    setSlotModalVisible(false);
    const predResult = pipelineStore.predictionResult;
    const faultPredictions = predResult?.faultPredictions;
    if (!faultPredictions || faultPredictions.length === 0) return;

    // 从工作流节点提取原始 CSV 路径与算子配置（供回流回贴原始时序）
    const findCfg = (fid: string): any => {
      const node = nodes.find((n: any) => n?.data?.config?.functionId === fid);
      return node?.data?.config || null;
    };
    const loadCfg = findCfg('load_csv');
    const windowCfg = findCfg('time_window_split');
    const labelEncodeCfg = findCfg('label_encode');

    if (!loadCfg?.file_path) {
      message.error('未找到预测工作流的 load_csv 节点 file_path，无法回贴原始时序');
      return;
    }

    // 构造 label_map（业务名→故障码）：优先用 label_encode 节点的 label_map 键，命名走中文映射
    const labelMap: Record<string, number> = {};
    let rawMap: Record<string, any> = {};
    try {
      const lm = labelEncodeCfg?.label_map;
      rawMap = typeof lm === 'string' ? JSON.parse(lm) : (lm || {});
    } catch {
      rawMap = {};
    }
    Object.values(rawMap).forEach((code: any) => {
      const c = Number(code);
      if (!Number.isNaN(c)) {
        const name = FAULT_LABEL_NAMES[String(c)] || `故障${c}`;
        labelMap[name] = c;
      }
    });
    // 兜底：若 label_encode 无 label_map，用预测结果中出现过的标签播种
    if (Object.keys(labelMap).length === 0) {
      faultPredictions.forEach((row: any) => {
        const c = Number(row.predictions ?? row.predicted_label);
        if (!Number.isNaN(c)) {
          const name = FAULT_LABEL_NAMES[String(c)] || `故障${c}`;
          labelMap[name] = c;
        }
      });
    }

    setReviewLabelingLoading(true);
    try {
      const resp = await reviewSessionApi.createReviewSessionFromPrediction({
        predictions: faultPredictions as Array<Record<string, unknown>>,
        sourceCsvPath: loadCfg.file_path,
        loadConfig: {
          rename_columns: loadCfg.rename_columns,
          encoding: loadCfg.encoding,
          delimiter: loadCfg.delimiter,
          id_fields: loadCfg.id_fields,
          time_field: loadCfg.time_field,
        },
        windowConfig: {
          window: windowCfg?.window || '1d',
          id_fields: windowCfg?.id_fields || loadCfg.id_fields,
          time_field: windowCfg?.time_field || loadCfg.time_field || 'time',
        },
        labelMap,
        enableLlm: true,
        slot: selectedSlot,
      });
      message.success(`已创建审核会话（slot: ${selectedSlot}），共 ${resp.total_count} 个待审核单元`);
      navigate(`/iterative-labeling/review?review_id=${encodeURIComponent(resp.review_id)}`);
    } catch (e: any) {
      console.error('创建审核会话失败:', e);
      const detail = e?.response?.data?.detail || e?.message || '未知错误';
      message.error(`创建审核会话失败: ${detail}`);
    } finally {
      setReviewLabelingLoading(false);
    }
  }, [pipelineStore.predictionResult, nodes, navigate, selectedSlot]);

  // Handle pipeline execution
  const handlePipelineExecute = useCallback(async () => {
    if (!workflowId) {
      message.warning(t('workflow.saveFirst'));
      return;
    }
    setBottomPanelVisible(true);
    await pipelineStore.executePipeline(workflowId, Math.max(1, nodes.length), nodes);
  }, [workflowId, pipelineStore, nodes.length]);

  // Handle operator config save
  const handleOperatorConfigSave = useCallback((config: Record<string, any>) => {
    if (selectedNodeId) {
      const node = nodes.find((n) => n.id === selectedNodeId);
      if (node) {
        const updatedNodes = nodes.map((n) =>
          n.id === selectedNodeId
            ? { ...n, data: { ...n.data, config: { ...n.data.config, ...config } } }
            : n
        );
        setNodes(updatedNodes);
        message.success(t('workflow.paramsSaved'));
      }
    }
    setOperatorPanelVisible(false);
  }, [selectedNodeId, nodes, setNodes]);
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  return (
    <Layout className="workflow-editor-page">
      <Layout>
        {/* 左侧节点库 - 固定宽度 460px，顶到最上面 */}
        <Sider width={460} theme="light" className="workflow-editor-sider" style={{ height: '100%' }}>
          {nodeLibraryReady ? (
            <NodeLibraryPanelV2
              onApplyWorkflow={handleApplyWorkflow}
              onMergeNodes={handleMergeNodes}
            />
          ) : (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Spin />
            </div>
          )}
        </Sider>

        <Layout>
          {/* 顶部工具栏 - 模板名称移到右边 */}
          <Header className="workflow-editor-header">
            <div className="workflow-editor-header-left">
              <span style={{ fontSize: 16, fontWeight: 500 }}>{t('workflow.templateEditor')}</span>
            </div>
            <div className="workflow-editor-header-right">
              <Space>
                {/* @AI_GENERATED */}
                {/* 流水线模板和工作流设置仅在非光伏故障诊断模板时显示（光伏模板不需要这些负荷预测配置） */}
                {!workflowName.includes('光伏故障诊断') && !workflowName.includes('pv-fault') && (
                  <>
                    <PipelineTemplateMenu onSelect={handleTemplateSelect} />
                    <Button icon={<SettingOutlined />} onClick={() => setGlobalConfigVisible(true)}>
                      {t('workflow.workflowSettings')}
                    </Button>
                  </>
                )}
                {/* @AI_GENERATED: end */}
                <Input
                  value={td(workflowName)}
                  onChange={(e) => setWorkflowName(e.target.value)}
                  placeholder={t('workflow.templateName')}
                  style={{ width: 200 }}
                />
                <Button icon={<FolderOpenOutlined />} onClick={handleOpen}>
                  {t('workflow.open')}
                </Button>
                <Button 
                  icon={<SaveOutlined />} 
                  onClick={handleSave}
                  loading={saving}
                >
                  {t('workflow.save')}
                </Button>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={handleExecute}
                  loading={isExecuting || pipelineStore.quickBacktestLoading}
                >
                  {t('workflow.execute')}
                </Button>
                {/* @AI_GENERATED */}
                {(isExecuting || pipelineStore.quickBacktestLoading) && (
                  <Button
                    danger
                    icon={<StopOutlined />}
                    onClick={() => {
                      if (pipelineStore.quickBacktestLoading) {
                        stopQuickBacktest();
                        return;
                      }
                      handleStopExecution();
                    }}
                  >
                    {t('workflow.stopTraining')}
                  </Button>
                )}
                {/* @AI_GENERATED */}
                <Button
                  icon={<BarChartOutlined />}
                  onClick={() => setBottomPanelVisible(!bottomPanelVisible)}
                  type={bottomPanelVisible ? 'primary' : 'default'}
                >
                  {bottomPanelVisible ? t('workflow.hideConsole') : t('workflow.showConsole')}
                </Button>
                {/* @AI_GENERATED: end */}
                {/* @AI_GENERATED: end */}
              </Space>
            </div>
          </Header>

          {/* 中间画布 */}
          <Content className="workflow-editor-content">
            <EnhancedCanvas
              nodes={nodes}
              edges={edges}
              onNodesChange={handleNodesChange}
              onEdgesChange={handleEdgesChange}
              onNodeSelect={handleNodeSelect}
              onNodeAdd={handleNodeAdd}
            />
          </Content>
        </Layout>

        {/* @AI_GENERATED */}
        {/* 右侧面板：有 functionId 的节点用新的 OperatorConfigPanel，否则用旧的 PropertyPanelV2 */}
        {selectedNodeId && (() => {
          const selectedNode = nodes.find((n) => n.id === selectedNodeId);
          const hasFunctionId = !!selectedNode?.data?.config?.functionId;
          if (hasFunctionId) {
            // 有 functionId 的算子节点 — 使用内嵌的 OperatorConfigPanel（不用 Drawer）
            return null; // OperatorConfigPanel 以 Drawer 形式在下方渲染
          }
          // 非算子节点 — 使用旧的 PropertyPanelV2
          return (
            <Sider width={320} theme="light" className="workflow-editor-sider-right">
              <PropertyPanelV2 nodeId={selectedNodeId} />
            </Sider>
          );
        })()}
        {/* @AI_GENERATED: end */}
      </Layout>

      {/* 打开算法模板对话框 */}
      <Modal
        title={t('workflow.openTemplate')}
        open={openModalVisible}
        onCancel={() => setOpenModalVisible(false)}
        footer={null}
        width={600}
      >
        <List
          loading={loadingWorkflows}
          dataSource={workflows}
          renderItem={(workflow) => (
            <List.Item
              actions={[
                <Button 
                  type="link" 
                  loading={openingWorkflowId === workflow.id}
                  onClick={() => handleLoadWorkflow(workflow)}
                >
                  {t('workflow.open')}
                </Button>,
              ]}
            >
              <List.Item.Meta
                title={td(workflow.name)}
                description={
                  <>
                    <div>{td(workflow.description) || t('workflow.noDescription')}</div>
                    <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                      {t('workflow.nodeCount')}: {workflow.nodeCount} | 
                      {t('workflow.updateTime')}: {workflow.updatedAt ? new Date(workflow.updatedAt).toLocaleString() : t('workflow.unknown')}
                    </div>
                  </>
                }
              />
            </List.Item>
          )}
          locale={{ emptyText: t('workflow.noTemplates') }}
        />
      </Modal>

      {/* @AI_GENERATED: Kiro v1.0 */}
      {/* Slot 选择弹窗（人工审查打标前选场景/数据集隔离空间） */}
      <Modal
        title="选择标注空间（Slot）"
        open={slotModalVisible}
        onOk={handleReviewLabelingConfirm}
        onCancel={() => setSlotModalVisible(false)}
        okText="确认并创建审核会话"
        width={420}
      >
        <div style={{ marginBottom: 16 }}>
          <Typography.Text>
            不同数据集/场景使用不同的标注空间,标签注册表、审核会话、回流数据集按空间隔离,互不干扰。
          </Typography.Text>
        </div>
        <Input
          addonBefore="Slot"
          value={selectedSlot}
          onChange={(e) => setSelectedSlot(e.target.value.trim() || 'default')}
          placeholder="输入场景标识,如 aesc / mengxi / default"
        />
        <div style={{ marginTop: 8 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            常用值: default（默认）、aesc、mengxi、weihai 等。同一 slot 内标签注册表共享。
          </Typography.Text>
        </div>
      </Modal>

      {/* 执行结果抽屉 */}
      <Drawer
        title={
          <Space>
            <BarChartOutlined />
            {t('execution.result')}
            {latestResult?.success ? (
              <Tag color="success" icon={<CheckCircleOutlined />}>{t('execution.success')}</Tag>
            ) : (
              <Tag color="error" icon={<CloseCircleOutlined />}>{t('execution.failed')}</Tag>
            )}
          </Space>
        }
        placement="right"
        width={500}
        open={resultDrawerVisible}
        onClose={() => setResultDrawerVisible(false)}
      >
        {latestResult && (
          <>
            <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label={t('execution.status')}>
                {latestResult.success ? (
                  <Tag color="success">{t('execution.success')}</Tag>
                ) : (
                  <Tag color="error">{t('execution.failed')}</Tag>
                )}
              </Descriptions.Item>
              <Descriptions.Item label={t('execution.duration')}>
                {latestResult.executionTime?.toFixed(3)}s
              </Descriptions.Item>
              {latestResult.error && (
                <Descriptions.Item label={t('execution.errorInfo')}>
                  <Typography.Text type="danger">{latestResult.error}</Typography.Text>
                </Descriptions.Item>
              )}
              {/* @AI_GENERATED */}
              {latestResult.model_id && (
                <Descriptions.Item label={t('execution.modelId')}>
                  <Typography.Text copyable>{latestResult.model_id}</Typography.Text>
                </Descriptions.Item>
              )}
              {/* @AI_GENERATED: end */}
            </Descriptions>

            {/* @AI_GENERATED */}
            {/* 训练评估指标卡片 */}
            {latestResult.metrics && (
              <div style={{ marginBottom: 16 }}>
                <Typography.Title level={5}>{t('execution.evaluationMetrics')}</Typography.Title>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {latestResult.metrics.smape != null && (
                    <Tag color="blue" style={{ padding: '4px 12px', fontSize: 13 }}>
                      SMAPE: {latestResult.metrics.smape.toFixed(2)}%
                    </Tag>
                  )}
                  {latestResult.metrics.rmse != null && (
                    <Tag color="green" style={{ padding: '4px 12px', fontSize: 13 }}>
                      RMSE: {latestResult.metrics.rmse.toFixed(4)}
                    </Tag>
                  )}
                  {latestResult.metrics.mae != null && (
                    <Tag color="orange" style={{ padding: '4px 12px', fontSize: 13 }}>
                      MAE: {latestResult.metrics.mae.toFixed(4)}
                    </Tag>
                  )}
                  {latestResult.metrics.mse != null && (
                    <Tag color="purple" style={{ padding: '4px 12px', fontSize: 13 }}>
                      MSE: {latestResult.metrics.mse.toFixed(4)}
                    </Tag>
                  )}
                </div>
              </div>
            )}
            {/* @AI_GENERATED: end */}

            <Typography.Title level={5}>{t('execution.nodeDetails')}</Typography.Title>
            <Collapse
              items={Object.entries(latestResult.nodeResults || {}).map(([nodeId, result]: [string, any]) => {
                const node = nodes.find(n => n.id === nodeId);
                const nodeLabel = td(node?.data?.label || nodeId);
                const isSuccess = result.status === 'success';
                
                // @AI_GENERATED
                // 提取关键指标 — 从 outputSummary 中读取
                const summary = result.outputSummary || result.output || {};
                const metrics: { label: string; value: string }[] = [];
                
                // XGBoost 训练结果
                if (summary.model_id) {
                  metrics.push({ label: '模型 ID', value: String(summary.model_id) });
                }
                if (summary.model_path) {
                  metrics.push({ label: '模型保存路径', value: String(summary.model_path) });
                }
                if (summary.predictions) {
                  metrics.push({ label: '预测点数', value: String(summary.predictions) });
                }
                // SMAPE 评估结果
                if (summary.score !== undefined) {
                  metrics.push({ label: 'SMAPE', value: `${Number(summary.score).toFixed(2)}%` });
                }
                // MSE/RMSE/MAE 评估结果
                if (summary.rmse !== undefined) {
                  metrics.push({ label: 'RMSE', value: Number(summary.rmse).toFixed(4) });
                }
                if (summary.mae !== undefined) {
                  metrics.push({ label: 'MAE', value: Number(summary.mae).toFixed(4) });
                }
                if (summary.mse !== undefined) {
                  metrics.push({ label: 'MSE', value: Number(summary.mse).toFixed(2) });
                }
                // 数据类算子 — 显示数据行数
                if (summary.data && typeof summary.data === 'string' && summary.data.startsWith('DataFrame')) {
                  metrics.push({ label: '数据', value: summary.data });
                }
                if (summary.outlier_indices) {
                  metrics.push({ label: '异常点数', value: String(summary.outlier_indices) });
                }
                // @AI_GENERATED: end
                
                return {
                  key: nodeId,
                  label: (
                    <Space>
                      {isSuccess ? (
                        <CheckCircleOutlined style={{ color: '#52c41a' }} />
                      ) : (
                        <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
                      )}
                      {nodeLabel}
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        ({result.executionTime?.toFixed(3)}s)
                      </Typography.Text>
                    </Space>
                  ),
                  children: (
                    <div>
                      {result.error && (
                        <Typography.Text type="danger">{result.error}</Typography.Text>
                      )}
                      {metrics.length > 0 && (
                        <Descriptions column={2} size="small" bordered>
                          {metrics.map((m, idx) => (
                            <Descriptions.Item key={idx} label={m.label}>
                              <Typography.Text strong>{m.value}</Typography.Text>
                            </Descriptions.Item>
                          ))}
                        </Descriptions>
                      )}
                      {metrics.length === 0 && isSuccess && (
                        <Typography.Text type="secondary">{t('execution.successNoMetrics')}</Typography.Text>
                      )}
                    </div>
                  ),
                };
              })}
              defaultActiveKey={Object.keys(latestResult.nodeResults || {}).slice(-3)}
            />
          </>
        )}
      </Drawer>
      {/* @AI_GENERATED: end */}

      {/* @AI_GENERATED */}
      {/* Operator Config Panel */}
      <OperatorConfigPanel
        node={nodes.find((n) => n.id === selectedNodeId) || null}
        functionDef={selectedFunctionDef}
        executionResult={selectedNodeId ? pipelineStore.nodeStatuses[selectedNodeId] as any : undefined}
        onSave={handleOperatorConfigSave}
        onClose={() => setOperatorPanelVisible(false)}
        visible={operatorPanelVisible}
      />

      {/* Global Config Panel */}
      <WorkflowGlobalConfigPanel
        visible={globalConfigVisible}
        globalConfig={pipelineStore.globalConfig}
        onChange={(config) => pipelineStore.updateGlobalConfig(config)}
        onApplyLocalParityPreset={applyLocalParityPresetToNodes}
        onClose={() => setGlobalConfigVisible(false)}
      />

      {/* Bottom execution panel */}
      {bottomPanelVisible && (
        <div
          className="wf-bottom-panel-root"
          style={{
            position: 'fixed', bottom: 0, left: 460, right: 0,
            background: '#fff', borderTop: '1px solid #e8e8e8',
            zIndex: 100, height: bottomPanelHeight,
          }}
        >
          <div
            onMouseDown={handleBottomPanelResizeStart}
            style={{
              height: 8,
              cursor: 'row-resize',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: isResizingBottomPanel ? '#f5f5f5' : 'transparent',
              borderBottom: '1px solid #f0f0f0',
            }}
          >
            <div
              style={{
                width: 56,
                height: 3,
                borderRadius: 999,
                background: '#d9d9d9',
              }}
            />
          </div>
          <Tabs
            className="wf-bottom-panel-tabs"
            defaultActiveKey="progress"
            size="small"
            style={{ padding: '0 16px', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
            tabBarExtraContent={
              <Button size="small" onClick={() => setBottomPanelVisible(false)}>{t('workflow.collapse')}</Button>
            }
            items={[
              {
                key: 'progress',
                label: t('workflow.executionProgress'),
                children: (
                  <PipelineProgressTracker
                    nodes={nodeStatusList}
                    currentNode={currentNodeId}
                    overallStatus={pipelineStore.executionStatus}
                    backtestProgress={pipelineStore.backtestProgress || undefined}
                  />
                ),
              },
              {
                key: 'logs',
                label: t('workflow.executionLogs'),
                children: <PipelineLogConsole logs={pipelineStore.logs} />,
              },
              ...(pipelineStore.trainingResult ? [{
                key: 'training-result',
                label: t('workflow.trainingResult'),
                children: (
                  <TrainingResultDashboard
                    result={pipelineStore.trainingResult}
                    onStartBacktest={(days: number) => {
                      if (!workflowId) return;
                      const cfg = pipelineStore.globalConfig || {};
                      const hasConfiguredRange =
                        Boolean(cfg.backtest_start_date) && Boolean(cfg.backtest_end_date);
                      const endDate = hasConfiguredRange
                        ? String(cfg.backtest_end_date)
                        : dayjs().format('YYYY-MM-DD');
                      const startDate = hasConfiguredRange
                        ? String(cfg.backtest_start_date)
                        : dayjs()
                            .subtract(Math.max(0, days - 1), 'day')
                            .format('YYYY-MM-DD');
                      message.info(t('backtest.startDaysBacktest', { days, start: startDate, end: endDate }));

                      runQuickBacktest({
                        workflowId,
                        returnHref: `${location.pathname}${location.search}`,
                        workflowName,
                        startDate,
                        endDate,
                        trainDays: cfg.backtest_train_days,
                        dailyHorizon: cfg.backtest_daily_horizon,
                        generateArtifacts: cfg.backtest_generate_artifacts,
                        outputDir: cfg.backtest_output_dir,
                        applyWindowFilter: cfg.backtest_apply_window_filter,
                        maskTargetValues: cfg.backtest_mask_target_values,
                      });
                    }}
                    onStopBacktest={() => stopQuickBacktest()}
                    backtestLoading={pipelineStore.quickBacktestLoading}
                  />
                ),
              }] : []),
              ...(pipelineStore.predictionResult ? [{
                key: 'prediction-result',
                label: t('workflow.predictionResult'),
                children: (
                  <PredictionResultDashboard
                    result={pipelineStore.predictionResult}
                    onExport={() => pipelineStore.exportResults('csv')}
                    onReviewLabeling={handleReviewLabelingClick}
                    reviewLabelingLoading={reviewLabelingLoading}
                  />
                ),
              }] : []),
              ...(pipelineStore.backtestResult ? [{
                key: 'backtest-result',
                label: t('workflow.backtestResult'),
                children: (
                  <BacktestResultDashboard
                    result={pipelineStore.backtestResult}
                    onExport={() => pipelineStore.exportResults('csv')}
                    onNavigateBaselineCompare={workflowId ? openBaselineComparePage : undefined}
                    onApplyBestRecommendation={(recommendation) => {
                      const patch = buildGlobalConfigPatchFromBestRecommendation(recommendation);
                      if (Object.keys(patch).length === 0) {
                        message.warning('最佳候选没有可回灌到通用配置的白名单参数');
                        return;
                      }
                      const current = pipelineStore.globalConfig || {};
                      const fieldLabels: Record<string, string> = {
                        backtest_train_days: '回测训练天数',
                        backtest_daily_horizon: '回测预测点数',
                        backtest_mode: '回测模式',
                        backtest_model_ref: '模型引用',
                        use_reference_rolling_engine: '威海参考回测引擎',
                        strict_alignment_mode: '严格对齐模式',
                        backtest_apply_window_filter: '窗口过滤开关',
                        backtest_mask_target_values: '目标值掩码开关',
                        tuning_model_family: '调优模型家族',
                        tuning_model_params: '调优模型参数',
                      };
                      const formatValue = (value: any) => {
                        if (value === undefined) return '未设置';
                        if (typeof value === 'object' && value !== null) {
                          try {
                            return JSON.stringify(value);
                          } catch {
                            return String(value);
                          }
                        }
                        return String(value);
                      };
                      const changedEntries = Object.entries(patch).filter(([key, nextValue]) => {
                        const currentValue = (current as any)[key];
                        return JSON.stringify(currentValue) !== JSON.stringify(nextValue);
                      });
                      if (changedEntries.length === 0) {
                        message.info('最佳候选与当前配置一致，无需回灌');
                        return;
                      }
                      Modal.confirm({
                        title: '确认应用最佳候选到通用配置',
                        width: 760,
                        content: (
                          <div style={{ maxHeight: 320, overflow: 'auto' }}>
                            {changedEntries.map(([key, nextValue]) => (
                              <div key={key} style={{ marginBottom: 8 }}>
                                <Typography.Text strong>{fieldLabels[key] || key}</Typography.Text>
                                <div style={{ color: '#8c8c8c', fontSize: 12 }}>
                                  当前: {formatValue((current as any)[key])}
                                </div>
                                <div style={{ color: '#1677ff', fontSize: 12 }}>
                                  变更为: {formatValue(nextValue)}
                                </div>
                              </div>
                            ))}
                          </div>
                        ),
                        okText: '确认应用',
                        cancelText: '取消',
                        onOk: () => {
                          pipelineStore.updateGlobalConfig({
                            ...patch,
                            run_mode: 'training',
                            operate_status: 'training',
                          });
                          message.success('已将最佳候选参数回灌到通用配置（已切换到训练模式）');
                        },
                      });
                    }}
                  />
                ),
              }] : []),
              {
                key: 'history',
                label: t('workflow.executionHistory'),
                children: (
                  <ExecutionHistoryPanel
                    history={pipelineStore.executionHistory}
                    onLoadConfig={(record) => pipelineStore.loadHistoryConfig(record)}
                    onViewResult={(record) => {
                      const payload = (record as any).resultPayload;
                      if (!payload) {
                        message.info('该记录没有保存执行结果详情');
                        return;
                      }
                      // 根据 templateType 还原到对应的结果面板
                      const ttype = record.templateType;
                      const isPred = ttype === 'prediction' || payload.fault_predictions;
                      if (isPred) {
                        const forecastValues = Array.isArray(payload.forecast_values) ? payload.forecast_values : (Array.isArray(payload.y_pred) ? payload.y_pred : []);
                        const rawTs = Array.isArray(payload.forecast_timestamps) ? payload.forecast_timestamps : [];
                        const forecastTimestamps = rawTs.length === forecastValues.length ? rawTs : forecastValues.map((_: unknown, i: number) => String(i));
                        usePipelineExecutionStore.setState({
                          predictionResult: {
                            executionId: record.executionId,
                            totalDuration: record.totalDuration || 0,
                            completedAt: record.createdAt,
                            modelId: record.modelId || '',
                            forecastTimestamps,
                            forecastValues,
                            nodeDurations: payload.nodeDurations || {},
                            faultPredictions: payload.fault_predictions || undefined,
                            metrics: payload.metrics || undefined,
                            faultTimeseries: payload.fault_timeseries || undefined,
                          } as any,
                        });
                      } else {
                        usePipelineExecutionStore.setState({
                          trainingResult: {
                            executionId: record.executionId,
                            totalDuration: record.totalDuration || 0,
                            completedAt: record.createdAt,
                            templateName: record.templateName,
                            modelId: record.modelId,
                            nodeDurations: payload.nodeDurations || {},
                            metrics: payload.metrics || undefined,
                          } as any,
                        });
                      }
                      setBottomPanelVisible(true);
                      message.success('已加载历史执行结果');
                    }}
                  />
                ),
              },
            ]}
          />
        </div>
      )}
      {/* @AI_GENERATED: end */}
    </Layout>
  );
  // @AI_GENERATED: end
};

export default WorkflowEditorPage;
