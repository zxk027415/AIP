/**
 * 参考版算法模板页面 - Dify 样式验证
 * 用于验证 GPU 加速和缩放清晰度
 */

import React, { useCallback, useEffect } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  ReactFlowProvider,
  BackgroundVariant,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  useNodesState,
  useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import './WorkflowReferencePage.css';

// Dify SimpleNode 组件
const DifySimpleNode = ({ data, selected, id }: any) => {
  const [nodeHovered, setNodeHovered] = React.useState(false);
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const showSelectedBorder = selected || data._isBundled || data._isEntering;
  
  // 监听 hover 状态变化，手动激活 GPU（修复 hover 离开时模糊问题）
  React.useEffect(() => {
    const timer = setTimeout(() => {
      const node = document.querySelector(`[data-id="${id}"] .dify-node`);
      if (node) {
        const htmlElement = node as HTMLElement;
        const originalTransform = htmlElement.style.transform;
        htmlElement.style.transform = 'translateZ(0.1px)';
        void htmlElement.offsetHeight;
        htmlElement.style.transform = originalTransform || '';
      }
    }, 50);
    return () => clearTimeout(timer);
  }, [nodeHovered, id]);
  
  return (
    <div 
      className={`dify-node-wrapper ${showSelectedBorder ? 'selected' : ''}`}
      onMouseEnter={() => setNodeHovered(true)}
      onMouseLeave={() => setNodeHovered(false)}
    >
      <div className="dify-node">
        <div className="dify-node-header">
          <div className="dify-node-icon">📊</div>
          <div className="dify-node-title">{data.title || t('workflowRef.nodeTitle')}</div>
        </div>
      </div>
    </div>
  );
};

const nodeTypes = {
  difySimple: DifySimpleNode,
};

const initialNodes: Node[] = [
  { id: '1', type: 'difySimple', position: { x: 250, y: 100 }, data: { title: 'Matrix Add' } },
  { id: '2', type: 'difySimple', position: { x: 250, y: 250 }, data: { title: 'Matrix Multiply' } },
  { id: '3', type: 'difySimple', position: { x: 500, y: 175 }, data: { title: 'Visualization' } },
];

const initialEdges: Edge[] = [
  { id: 'e1-3', source: '1', target: '3' },
  { id: 'e2-3', source: '2', target: '3' },
];

/**
 * GPU 激活辅助函数
 * 通过临时修改 transform 强制浏览器为每个节点创建 GPU 层
 */
const forceGPUActivation = (selector: string) => {
  const elements = document.querySelectorAll(selector);
  elements.forEach((element) => {
    const htmlElement = element as HTMLElement;
    const originalTransform = htmlElement.style.transform;
    htmlElement.style.transform = 'translateZ(0.1px)';
    void htmlElement.offsetHeight; // 触发重排
    htmlElement.style.transform = originalTransform || '';
  });
};

const WorkflowReferencePageContent: React.FC = () => {
  const [nodes, , onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const { setViewport, getZoom } = useReactFlow();
  const [currentZoom, setCurrentZoom] = React.useState(1);
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  // 监听缩放变化
  useEffect(() => {
    const interval = setInterval(() => {
      const zoom = getZoom();
      if (zoom !== currentZoom) {
        setCurrentZoom(zoom);
      }
    }, 100);
    return () => clearInterval(interval);
  }, [getZoom, currentZoom]);

  // 首次加载时激活 GPU 层
  useEffect(() => {
    const activateGPU = async () => {
      setViewport({ x: 0, y: 0, zoom: 2 }, { duration: 0 });
      await new Promise(resolve => setTimeout(resolve, 100));
      forceGPUActivation('.dify-node');
      await new Promise(resolve => setTimeout(resolve, 50));
      setViewport({ x: 0, y: 0, zoom: 1 }, { duration: 0 });
    };
    activateGPU();
  }, [setViewport]);

  // 监听节点变化，为新添加的节点激活 GPU
  useEffect(() => {
    if (nodes.length > 0) {
      // 如果是首次添加节点（从 0 到 1），执行完整的 GPU 激活流程
      if (nodes.length === 1) {
        const activateGPU = async () => {
          setViewport({ x: 0, y: 0, zoom: 2 }, { duration: 0 });
          await new Promise(resolve => setTimeout(resolve, 100));
          forceGPUActivation('.dify-node');
          await new Promise(resolve => setTimeout(resolve, 50));
          setViewport({ x: 0, y: 0, zoom: 1 }, { duration: 0 });
        };
        activateGPU();
      } else {
        // 后续添加节点，使用快速激活
        const timer = setTimeout(() => {
          forceGPUActivation('.dify-node');
        }, 50);
        return () => clearTimeout(timer);
      }
    }
  }, [nodes.length, setViewport]);

  // 监听缩放变化，每次缩放时都重新激活 GPU（防止 hover 后 GPU 层丢失）
  useEffect(() => {
    // 每次缩放变化都激活，确保 hover 后缩放也清晰
    const timer = setTimeout(() => {
      forceGPUActivation('.dify-node');
    }, 100);
    return () => clearTimeout(timer);
  }, [currentZoom]);

  return (
    <div className="workflow-reference-page">
      <div className="workflow-reference-header">
        {/* @AI_GENERATED */}
        <h1>{t('workflowRef.title')}</h1>
        <p>{t('workflowRef.subtitle')}</p>
        {/* @AI_GENERATED: end */}
      </div>
      <div id="workflow-reference-container" className="workflow-reference-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          defaultViewport={{ x: 0, y: 0, zoom: 1 }}
          minZoom={0.25}
          maxZoom={2}
          fitView={false}
          nodesDraggable={true}
          nodesConnectable={true}
          elementsSelectable={true}
          zoomOnScroll={true}
          panOnScroll={false}
          zoomOnDoubleClick={true}
          zoomOnPinch={true}
          preventScrolling={true}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
    </div>
  );
};

const WorkflowReferencePage: React.FC = () => {
  return (
    <ReactFlowProvider>
      <WorkflowReferencePageContent />
    </ReactFlowProvider>
  );
};

export default WorkflowReferencePage;
