/**
 * Workflow V2 Page - 极简测试版
 * 目标：测试 Dify 极简设计的清晰度
 */

import React, { useCallback, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  ReactFlowProvider,
  BackgroundVariant,
  type Connection,
  type Edge,
  type Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import './WorkflowV2Page.css';

// 极简节点组件
const SimpleNode = ({ data }: any) => {
  return (
    <div className="simple-node">
      <div className="simple-node-header">
        <div className="simple-node-icon">📦</div>
        <div className="simple-node-title">{data.label}</div>
      </div>
      <div className="simple-node-description">{data.description}</div>
    </div>
  );
};

const nodeTypes = {
  simple: SimpleNode,
};

// 初始节点
const initialNodes: Node[] = [
  {
    id: '1',
    type: 'simple',
    position: { x: 100, y: 100 },
    data: { label: 'Matrix Add', description: '矩阵加法运算' },
  },
  {
    id: '2',
    type: 'simple',
    position: { x: 400, y: 100 },
    data: { label: 'Function', description: '自定义函数执行' },
  },
  {
    id: '3',
    type: 'simple',
    position: { x: 250, y: 300 },
    data: { label: 'Visualize', description: '数据可视化输出' },
  },
];

const initialEdges: Edge[] = [
  { id: 'e1-2', source: '1', target: '2', animated: false },
  { id: 'e2-3', source: '2', target: '3', animated: false },
];

const WorkflowV2Page: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end

  // @AI_GENERATED
  const translatedNodes: Node[] = [
    {
      id: '1',
      type: 'simple',
      position: { x: 100, y: 100 },
      data: { label: 'Matrix Add', description: t('workflowV2.matrixAdd') },
    },
    {
      id: '2',
      type: 'simple',
      position: { x: 400, y: 100 },
      data: { label: 'Function', description: t('workflowV2.customFunction') },
    },
    {
      id: '3',
      type: 'simple',
      position: { x: 250, y: 300 },
      data: { label: 'Visualize', description: t('workflowV2.dataVisualize') },
    },
  ];
  // @AI_GENERATED: end

  const [nodes, setNodes] = useState<Node[]>(translatedNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    []
  );

  return (
    <div className="workflow-v2-page">
      <div className="workflow-v2-header">
        {/* @AI_GENERATED */}
        <h1>{t('workflowV2.title')}</h1>
        <p>{t('workflowV2.subtitle')}</p>
        {/* @AI_GENERATED: end */}
      </div>
      
      <div className="workflow-v2-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={(changes) => {
            // 简单的节点更新
            setNodes((nds) => {
              const newNodes = [...nds];
              changes.forEach((change) => {
                if (change.type === 'position' && 'position' in change) {
                  const node = newNodes.find((n) => n.id === change.id);
                  if (node && change.position) {
                    node.position = change.position;
                  }
                }
              });
              return newNodes;
            });
          }}
          onEdgesChange={(changes) => {
            // 简单的边更新
            setEdges((eds) => {
              return eds.filter((edge) => {
                const removeChange = changes.find(
                  (c) => c.type === 'remove' && 'id' in c && c.id === edge.id
                );
                return !removeChange;
              });
            });
          }}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          defaultViewport={{ x: 0, y: 0, zoom: 1 }}
          minZoom={0.2}
          maxZoom={2}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>

      <div className="workflow-v2-instructions">
        {/* @AI_GENERATED */}
        <h3>📝 {t('workflowV2.testInstructions')}</h3>
        <ol>
          <li>{t('workflowV2.instruction1')}</li>
          <li>{t('workflowV2.instruction2')}</li>
          <li>{t('workflowV2.instruction3')}</li>
          <li>{t('workflowV2.instruction4')}</li>
        </ol>
        <div className="test-info">
          <strong>{t('workflowV2.designFeatures')}</strong>
          <ul>
            <li>✅ {t('workflowV2.feature1')}</li>
            <li>✅ {t('workflowV2.feature2')}</li>
            <li>✅ {t('workflowV2.feature3')}</li>
            <li>✅ {t('workflowV2.feature4')}</li>
          </ul>
        </div>
        {/* @AI_GENERATED: end */}
      </div>
    </div>
  );
};

// 使用 Provider 包装
const WorkflowV2PageWithProvider: React.FC = () => {
  return (
    <ReactFlowProvider>
      <WorkflowV2Page />
    </ReactFlowProvider>
  );
};

export default WorkflowV2PageWithProvider;
