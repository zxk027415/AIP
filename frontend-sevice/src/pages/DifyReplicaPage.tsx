/**
 * Dify 节点复刻测试页面
 * 复刻图片中的三个节点：开始、代码执行、结束
 */

import React, { useCallback, useState } from 'react';
import ReactFlow, {
  Controls,
  Background,
  BackgroundVariant,
  addEdge,
  ReactFlowProvider,
  type Connection,
  type Edge,
  type Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import type { EnhancedNodeData } from '../types/workflow-enhanced';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import './DifyReplicaPage.css';

// 极简节点组件 - 和V2测试版一样
const SimpleNode = ({ data }: any) => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  return (
    <div className="simple-node">
      <div className="simple-node-header">
        <div className="simple-node-icon">
          {data.type === 'start' && '🏠'}
          {data.type === 'code' && '</>'}
          {data.type === 'end' && '⬇️'}
        </div>
        <div className="simple-node-title">{data.label}</div>
      </div>
      {data.outputs && data.outputs.length > 0 && (
        <div className="simple-node-fields">
          {data.outputs.map((output: any) => (
            <div key={output.id} className="simple-node-field">
              <span className="simple-node-field-icon">✕</span>
              <span className="simple-node-field-name">{output.name}</span>
              {/* @AI_GENERATED */}
              {data.type === 'start' && <span className="simple-node-field-label">{t('difyReplica.required')} #</span>}
              {/* @AI_GENERATED: end */}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// 节点类型映射 - 使用SimpleNode
const nodeTypes = {
  difyNode: SimpleNode,
};

// 初始节点 - 复刻图片中的三个节点
const initialNodes: Node<EnhancedNodeData>[] = [
  {
    id: 'start-1',
    type: 'difyNode',
    position: { x: 50, y: 150 },
    data: {
      label: '开始',
      type: 'start',
      description: '',
      inputs: [],
      outputs: [
        { id: 'groupid', name: 'groupid', type: 'string' },
        { id: 'areaid', name: 'areaid', type: 'string' },
        { id: 'moduleid', name: 'moduleid', type: 'string' },
      ],
      config: {},
    },
  },
  {
    id: 'code-1',
    type: 'difyNode',
    position: { x: 400, y: 150 },
    data: {
      label: '代码执行',
      type: 'code',
      description: '',
      inputs: [
        { id: 'input', name: 'input', type: 'any' },
      ],
      outputs: [
        { id: 'output', name: 'output', type: 'any' },
      ],
      config: {},
    },
  },
  {
    id: 'end-1',
    type: 'difyNode',
    position: { x: 750, y: 150 },
    data: {
      label: '结束',
      type: 'end',
      description: '',
      inputs: [
        { id: 'input', name: 'input', type: 'any' },
      ],
      outputs: [
        { id: 'resultNumber', name: 'resultNumber', type: 'number' },
      ],
      config: {},
    },
  },
];

// 初始连线
const initialEdges: Edge[] = [
  {
    id: 'e1-2',
    source: 'start-1',
    target: 'code-1',
    sourceHandle: 'output',
    targetHandle: 'input',
    type: 'smoothstep',
  },
  {
    id: 'e2-3',
    source: 'code-1',
    target: 'end-1',
    sourceHandle: 'output',
    targetHandle: 'input',
    type: 'smoothstep',
  },
];

const DifyReplicaPageContent: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end

  // @AI_GENERATED
  const translatedNodes: Node<EnhancedNodeData>[] = [
    {
      id: 'start-1',
      type: 'difyNode',
      position: { x: 50, y: 150 },
      data: {
        label: t('difyReplica.startNode'),
        type: 'start',
        description: '',
        inputs: [],
        outputs: [
          { id: 'groupid', name: 'groupid', type: 'string' },
          { id: 'areaid', name: 'areaid', type: 'string' },
          { id: 'moduleid', name: 'moduleid', type: 'string' },
        ],
        config: {},
      },
    },
    {
      id: 'code-1',
      type: 'difyNode',
      position: { x: 400, y: 150 },
      data: {
        label: t('difyReplica.codeExecution'),
        type: 'code',
        description: '',
        inputs: [
          { id: 'input', name: 'input', type: 'any' },
        ],
        outputs: [
          { id: 'output', name: 'output', type: 'any' },
        ],
        config: {},
      },
    },
    {
      id: 'end-1',
      type: 'difyNode',
      position: { x: 750, y: 150 },
      data: {
        label: t('difyReplica.endNode'),
        type: 'end',
        description: '',
        inputs: [
          { id: 'input', name: 'input', type: 'any' },
        ],
        outputs: [
          { id: 'resultNumber', name: 'resultNumber', type: 'number' },
        ],
        config: {},
      },
    },
  ];
  // @AI_GENERATED: end

  const [nodes, setNodes] = useState<Node<EnhancedNodeData>[]>(translatedNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    []
  );

  return (
    <div className="dify-replica-page">
      <div className="dify-replica-header">
        {/* @AI_GENERATED */}
        <h1>{t('difyReplica.title')}</h1>
        <p>{t('difyReplica.subtitle')}</p>
        {/* @AI_GENERATED: end */}
      </div>

      <div className="dify-replica-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={(changes) => {
            // 简单的节点更新 - 和V2测试版一样
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
            // 简单的边更新 - 和V2测试版一样
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
          minZoom={0.5}
          maxZoom={2}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#e5e5e5" />
          <Controls />
        </ReactFlow>
      </div>

      <div className="dify-replica-info">
        {/* @AI_GENERATED */}
        <h3>{t('difyReplica.nodeDescription')}</h3>
        <ul>
          <li><strong>{t('difyReplica.startNodeLabel')}</strong>{t('difyReplica.startNodeDesc')}</li>
          <li><strong>{t('difyReplica.codeNodeLabel')}</strong>{t('difyReplica.codeNodeDesc')}</li>
          <li><strong>{t('difyReplica.endNodeLabel')}</strong>{t('difyReplica.endNodeDesc')}</li>
        </ul>
        
        <div className="test-info">
          <strong>{t('difyReplica.testPoints')}</strong>
          <ul>
            <li>{t('difyReplica.testPoint1')}</li>
            <li>{t('difyReplica.testPoint2')}</li>
            <li>{t('difyReplica.testPoint3')}</li>
            <li>{t('difyReplica.testPoint4')}</li>
          </ul>
        </div>
        {/* @AI_GENERATED: end */}
      </div>
    </div>
  );
};

const DifyReplicaPage: React.FC = () => {
  return (
    <ReactFlowProvider>
      <DifyReplicaPageContent />
    </ReactFlowProvider>
  );
};

export default DifyReplicaPage;
