/**
 * Enhanced Canvas Component
 * 增强版算法模板画布组件
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  ControlButton,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  ReactFlowProvider,
  BackgroundVariant,
  ConnectionLineType,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type ReactFlowInstance,
  type NodeChange,
  type EdgeChange,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { message } from 'antd';
import { OneToOneOutlined, LockOutlined, UnlockOutlined } from '@ant-design/icons';
import { td } from '../../utils/dataTranslation';
import {
  validateEdgeConnection,
  decorateEdgeWithValidation,
} from './edgeValidation';
import { resolveEdgeHandles } from './operatorIoProfile';
import DifyStyleNodeHD from './DifyStyleNodeHD';
import ZoomIndicator from './ZoomIndicator';
import type { EnhancedWorkflowNode, EnhancedWorkflowEdge } from '../../types/workflow-enhanced';
import './DifyStyleCanvas.css';

// 节点类型映射 - 使用高清版本
const nodeTypes = {
  enhanced: DifyStyleNodeHD,
};

// 所有复杂的 GPU 优化函数已删除
// 采用 Dify 的极简设计哲学：让浏览器自然处理，不过度优化

// @AI_GENERATED: Kiro v1.0
interface EnhancedCanvasProps {
  nodes: EnhancedWorkflowNode[];
  edges: EnhancedWorkflowEdge[];
  onNodesChange: (nodes: EnhancedWorkflowNode[]) => void;
  onEdgesChange: (edges: EnhancedWorkflowEdge[]) => void;
  onNodeSelect: (nodeId: string | null) => void;
  onNodeAdd?: (node: EnhancedWorkflowNode) => void;
  readOnly?: boolean;
}
// @AI_GENERATED: end

const EnhancedCanvas: React.FC<EnhancedCanvasProps> = ({
  nodes: initialNodes,
  edges: initialEdges,
  onNodesChange,
  onEdgesChange,
  onNodeSelect,
  onNodeAdd,
  readOnly = false,
}) => {
  const [nodes, setNodes, onNodesChangeInternal] = useNodesState(initialNodes as Node[]);
  const [edges, setEdges, onEdgesChangeInternal] = useEdgesState(initialEdges as Edge[]);
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const reactFlowInstance = useRef<ReactFlowInstance | null>(null);
  const isDraggingRef = useRef(false);
  const { setViewport } = useReactFlow();
  const [isInteractive, setIsInteractive] = useState(true);

  // @AI_GENERATED: Kiro v1.0
  // 同步外部 props 到内部 React Flow 状态
  // useNodesState/useEdgesState 只在首次挂载时使用 initialNodes/initialEdges，
  // 后续 props 变化（如异步加载算法模板）需要手动同步
  useEffect(() => {
    setNodes(initialNodes as Node[]);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setEdges(initialEdges as Edge[]);
  }, [initialEdges, setEdges]);

  const workflowNodes = useMemo(
    () => nodes as EnhancedWorkflowNode[],
    [nodes],
  );

  const validatedEdges = useMemo(
    () => edges.map((edge) => decorateEdgeWithValidation(edge, workflowNodes)),
    [edges, workflowNodes],
  );

  // 验证连接：允许连线，但会在 onConnect 中标记不兼容
  const canConnect = useCallback((connection: Connection): boolean => {
    if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) {
      return false;
    }
    const sourceNode = workflowNodes.find((n) => n.id === connection.source);
    const targetNode = workflowNodes.find((n) => n.id === connection.target);
    return Boolean(sourceNode && targetNode);
  }, [workflowNodes]);

  // 当节点从空变为非空时（异步加载完成），自动适应视图
  const prevNodeCountRef = useRef(0);
  useEffect(() => {
    if (prevNodeCountRef.current === 0 && initialNodes.length > 0 && reactFlowInstance.current) {
      setTimeout(() => {
        reactFlowInstance.current?.fitView({ padding: 0.1, maxZoom: 1.2 });
      }, 100);
    }
    prevNodeCountRef.current = initialNodes.length;
  }, [initialNodes]);
  // @AI_GENERATED: end
  
  // Dify 极简设计：不需要任何 GPU 优化，让浏览器自然处理

  // 重置缩放到100%
  const handleResetZoom = useCallback(() => {
    setViewport({ x: 0, y: 0, zoom: 1 }, { duration: 300 });
  }, [setViewport]);

  // 切换交互模式
  const toggleInteractive = useCallback(() => {
    setIsInteractive((prev) => !prev);
  }, []);

  // 处理连接
  const onConnect = useCallback((params: Connection) => {
    if (!canConnect(params)) return;

    const sourceNode = workflowNodes.find((n) => n.id === params.source);
    const targetNode = workflowNodes.find((n) => n.id === params.target);
    const handles = resolveEdgeHandles(params.sourceHandle, params.targetHandle);
    const check = validateEdgeConnection(
      sourceNode,
      handles.sourceHandle,
      targetNode,
      handles.targetHandle,
    );

    const newEdge = decorateEdgeWithValidation(
      {
        ...params,
        ...handles,
        id: `edge-${params.source}-${params.target}-${Date.now()}`,
        type: 'default',
      } as Edge,
      workflowNodes,
    );

    setEdges((eds) => addEdge(newEdge, eds));

    if (!check.valid) {
      const srcLabel = td(String(sourceNode?.data?.label || params.source));
      const tgtLabel = td(String(targetNode?.data?.label || params.target));
      message.warning(`${srcLabel} → ${tgtLabel}：${check.message}（${check.sourceType} → ${check.targetType}）`);
    }

    if (onEdgesChange) {
      const newEdges = [...edges, newEdge] as EnhancedWorkflowEdge[];
      onEdgesChange(newEdges);
    }
  }, [canConnect, workflowNodes, setEdges, edges, onEdgesChange]);

  // 处理拖拽
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  }, []);

  // 处理放置
  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    // @AI_GENERATED: Kiro v1.0
    if (readOnly) return;
    // @AI_GENERATED: end

    const nodeData = event.dataTransfer.getData('application/reactflow');
    if (!nodeData || !reactFlowInstance.current) {
      return;
    }

    // 获取当前缩放级别
    const currentZoom = reactFlowInstance.current.getZoom();
    
    // 如果缩放不在最佳范围，提示用户
    if (currentZoom < 0.8 || currentZoom > 1.5) {
      message.info(td('💡 建议在 80%-150% 缩放范围内添加节点，以获得最佳清晰度'), 3);
    }

    const position = reactFlowInstance.current.screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });

    try {
      const parsedData = JSON.parse(nodeData);
      
      // 确保节点数据结构完整，符合后端验证要求
      const completeNodeData = {
        label: parsedData.label || '未命名节点',
        type: parsedData.type || 'function',
        icon: parsedData.icon || null,
        inputs: Array.isArray(parsedData.inputs) ? parsedData.inputs : [],
        outputs: Array.isArray(parsedData.outputs) ? parsedData.outputs : [],
        config: parsedData.config || {},
        status: parsedData.status || 'idle',
        error: parsedData.error || null,
        description: parsedData.description || null,
      };
      
      const newNode: EnhancedWorkflowNode = {
        id: `node-${Date.now()}`,
        type: 'enhanced',
        position,
        data: completeNodeData,
      };

      setNodes((nds) => [...nds, newNode as Node]);
      if (onNodeAdd) {
        onNodeAdd(newNode);
      }
      if (onNodesChange) {
        onNodesChange([...nodes as EnhancedWorkflowNode[], newNode]);
      }
    } catch (error) {
      console.error('Failed to parse node data:', error);
      message.error(td('创建节点失败'));
    }
  }, [nodes, setNodes, onNodeAdd, onNodesChange]);

  // 处理节点点击
  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    if (onNodeSelect) {
      onNodeSelect(node.id);
    }
  }, [onNodeSelect]);

  // 处理画布点击
  const onPaneClick = useCallback(() => {
    if (onNodeSelect) {
      onNodeSelect(null);
    }
  }, [onNodeSelect]);

  // @AI_GENERATED
  // 选中节点的 ID（用于 Delete 键删除）
  const selectedNodeIdRef = useRef<string | null>(null);

  const handleNodeClickWithRef = useCallback((_event: React.MouseEvent, node: Node) => {
    selectedNodeIdRef.current = node.id;
    if (onNodeSelect) {
      onNodeSelect(node.id);
    }
  }, [onNodeSelect]);

  const handlePaneClickWithRef = useCallback(() => {
    selectedNodeIdRef.current = null;
    if (onNodeSelect) {
      onNodeSelect(null);
    }
  }, [onNodeSelect]);

  // Delete / Backspace 键删除选中节点
  useEffect(() => {
    if (readOnly) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return;
      }

      if (event.key === 'Delete' || event.key === 'Backspace') {
        const nodeId = selectedNodeIdRef.current;
        if (!nodeId) return;
        event.preventDefault();

        // 删除节点和相关连线
        setNodes((nds) => nds.filter((n) => n.id !== nodeId));
        setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));

        // 通知父组件
        const remainingNodes = nodes.filter((n) => n.id !== nodeId);
        const remainingEdges = edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
        onNodesChange(remainingNodes as EnhancedWorkflowNode[]);
        onEdgesChange(remainingEdges as EnhancedWorkflowEdge[]);

        selectedNodeIdRef.current = null;
        if (onNodeSelect) {
          onNodeSelect(null);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [readOnly, nodes, edges, setNodes, setEdges, onNodesChange, onEdgesChange, onNodeSelect]);
  // @AI_GENERATED: end

  // 处理节点变化
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    onNodesChangeInternal(changes);
    
    const hasDragging = changes.some(c => 
      c.type === 'position' && 'dragging' in c && c.dragging === true
    );
    const hasDragEnd = changes.some(c => 
      c.type === 'position' && 'dragging' in c && c.dragging === false
    );
    const hasSelect = changes.some(c => c.type === 'select');
    
    if (hasDragging) {
      isDraggingRef.current = true;
      return;
    }
    
    if (hasDragEnd) {
      isDraggingRef.current = false;
      if (onNodesChange) {
        setNodes((currentNodes) => {
          onNodesChange(currentNodes as EnhancedWorkflowNode[]);
          return currentNodes;
        });
      }
      return;
    }
    
    if (hasSelect) {
      return;
    }
    
    if (!isDraggingRef.current && onNodesChange) {
      setNodes((currentNodes) => {
        onNodesChange(currentNodes as EnhancedWorkflowNode[]);
        return currentNodes;
      });
    }
  }, [onNodesChangeInternal, onNodesChange, setNodes]);

  // 处理连接线变化
  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    onEdgesChangeInternal(changes);
    if (onEdgesChange) {
      setEdges((currentEdges) => {
        onEdgesChange(currentEdges as EnhancedWorkflowEdge[]);
        return currentEdges;
      });
    }
  }, [onEdgesChangeInternal, onEdgesChange, setEdges]);

  return (
    <div ref={reactFlowWrapper} className="dify-canvas">
      <ReactFlow
        nodes={nodes}
        edges={validatedEdges}
        nodeTypes={nodeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        isValidConnection={canConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={handleNodeClickWithRef}
        onPaneClick={handlePaneClickWithRef}
        onInit={(instance) => {
          reactFlowInstance.current = instance;
          // 强制设置初始缩放为 100%
          setTimeout(() => {
            instance.setViewport({ x: 0, y: 0, zoom: 1 });
          }, 0);
        }}
        defaultEdgeOptions={{
          type: 'default', // 使用贝塞尔曲线
          animated: false,
          style: { stroke: '#94a3b8', strokeWidth: 2 },
        }}
        connectionLineStyle={{
          stroke: '#3b82f6',
          strokeWidth: 2,
        }}
        connectionLineType={ConnectionLineType.Bezier}
        defaultViewport={{ x: 0, y: 0, zoom: 1 }}
        minZoom={0.5}
        maxZoom={2}
        fitView={false}
        fitViewOptions={{
          padding: 0.1,
          minZoom: 0.8,
          maxZoom: 1.2,
        }}
        nodesDraggable={isInteractive && !readOnly}
        nodesConnectable={isInteractive && !readOnly}
        elementsSelectable={isInteractive && !readOnly}
        zoomOnScroll={true}
        panOnScroll={false}
        zoomOnDoubleClick={true}
        zoomOnPinch={true}
        preventScrolling={true}
      >
        <Background 
          variant={BackgroundVariant.Dots} 
          gap={20} 
          size={1}
          color="#cbd5e1"
        />
        <Controls 
          showZoom={false}
          showFitView={false}
          showInteractive={false}
          position="bottom-right"
        >
          <ControlButton onClick={handleResetZoom} title={td('重置缩放到100%')}>
            <OneToOneOutlined style={{ fontSize: '16px' }} />
          </ControlButton>
          <ControlButton 
            onClick={() => reactFlowInstance.current?.zoomIn()} 
            title={td('放大')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
              <path d="M16 4v24M4 16h24" stroke="currentColor" strokeWidth="2" fill="none" />
            </svg>
          </ControlButton>
          <ControlButton 
            onClick={() => reactFlowInstance.current?.zoomOut()} 
            title={td('缩小')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
              <path d="M4 16h24" stroke="currentColor" strokeWidth="2" fill="none" />
            </svg>
          </ControlButton>
          <ControlButton 
            onClick={() => reactFlowInstance.current?.fitView()} 
            title={td('适应视图')}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
              <path d="M4 8h6M4 8v6M28 8h-6M28 8v6M4 24h6M4 24v-6M28 24h-6M28 24v-6" stroke="currentColor" strokeWidth="2" fill="none" />
            </svg>
          </ControlButton>
          <ControlButton 
            onClick={toggleInteractive} 
            title={isInteractive ? td('锁定画布') : td('解锁画布')}
          >
            {isInteractive ? (
              <UnlockOutlined style={{ fontSize: '16px' }} />
            ) : (
              <LockOutlined style={{ fontSize: '16px' }} />
            )}
          </ControlButton>
        </Controls>
        <MiniMap
          nodeStrokeWidth={3}
          nodeColor={(node) => {
            if (node.selected) return '#3b82f6';
            return '#e2e8f0';
          }}
          nodeBorderRadius={12}
          zoomable
          pannable
          position="bottom-left"
        />
        <ZoomIndicator />
      </ReactFlow>
    </div>
  );
};

// 使用 ReactFlowProvider 包装
const EnhancedCanvasWithProvider: React.FC<EnhancedCanvasProps> = (props) => {
  return (
    <ReactFlowProvider>
      <EnhancedCanvas {...props} />
    </ReactFlowProvider>
  );
};

export default EnhancedCanvasWithProvider;
