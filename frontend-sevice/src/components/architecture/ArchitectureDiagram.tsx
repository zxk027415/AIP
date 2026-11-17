import { useCallback, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import ReactFlow, {
  type Node,
  type Edge,
  Background,
  Controls,
  ReactFlowProvider,
  MiniMap,
  type NodeTypes,
  Position,
  type NodeProps,
} from 'reactflow';
import 'reactflow/dist/style.css';
import './ArchitectureDiagram.css';

type ArchLayer = 'frontend' | 'communication' | 'backend' | 'data' | 'database';

type ArchNodeData = {
  nodeKey: string;
  icon: string;
  layer: ArchLayer;
  auxiliary?: boolean;
  planned?: boolean;
  upgradeInfoKey?: string;
};

const ArchNode = ({ data }: NodeProps<ArchNodeData>) => {
  const { t } = useTranslation();
  const isAuxiliary = data.auxiliary;
  const isPlanned = data.planned;
  const upgradeInfoKey = data.upgradeInfoKey;

  const label = t(`architecture.diagram.nodes.${data.nodeKey}.label`);
  const rawItems = t(`architecture.diagram.nodes.${data.nodeKey}.items`, { returnObjects: true });
  const items = Array.isArray(rawItems) ? (rawItems as string[]) : [];

  return (
    <div className={`arch-node ${data.layer} ${isAuxiliary ? 'auxiliary' : ''} ${isPlanned ? 'planned' : ''}`}>
      <div className="arch-node-header">
        <span className="arch-node-icon">{data.icon}</span>
        <span className="arch-node-title">{label}</span>
      </div>
      {upgradeInfoKey && (
        <div className="arch-node-upgrade">
          <span className="upgrade-badge">{t('architecture.diagram.upgradePending')}</span>
          <span className="upgrade-target">
            → {t(`architecture.diagram.upgrades.${upgradeInfoKey}`)}
          </span>
        </div>
      )}
      {items.length > 0 && (
        <div className="arch-node-items">
          {items.map((item, index) => (
            <div key={index} className="arch-node-item">
              • {item}
            </div>
          ))}
        </div>
      )}
      {isPlanned && (
        <div className="arch-node-status">
          <span className="status-badge">{t('architecture.planned')}</span>
        </div>
      )}
    </div>
  );
};

const nodeTypes: NodeTypes = {
  archNode: ArchNode,
};

const BASE_NODES: Node<ArchNodeData>[] = [
  {
    id: 'frontend-react',
    type: 'archNode',
    position: { x: 40, y: 60 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'frontendReact', icon: '⚛️', layer: 'frontend' },
  },
  {
    id: 'frontend-antd',
    type: 'archNode',
    position: { x: 220, y: 60 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'frontendAntd', icon: '🎨', layer: 'frontend' },
  },
  {
    id: 'frontend-zustand',
    type: 'archNode',
    position: { x: 400, y: 60 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'frontendZustand', icon: '📦', layer: 'frontend' },
  },
  {
    id: 'frontend-axios',
    type: 'archNode',
    position: { x: 580, y: 60 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'frontendAxios', icon: '🌐', layer: 'frontend' },
  },
  {
    id: 'frontend-router',
    type: 'archNode',
    position: { x: 760, y: 60 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'frontendRouter', icon: '🔀', layer: 'frontend', auxiliary: true },
  },
  {
    id: 'frontend-vite',
    type: 'archNode',
    position: { x: 940, y: 60 },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Left,
    data: { nodeKey: 'frontendVite', icon: '⚡', layer: 'frontend', auxiliary: true },
  },
  {
    id: 'frontend-workflow',
    type: 'archNode',
    position: { x: 40, y: 220 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    data: {
      nodeKey: 'frontendWorkflow',
      icon: '🔄',
      layer: 'frontend',
      auxiliary: true,
      upgradeInfoKey: 'virtualizedRendering',
    },
  },
  {
    id: 'frontend-echarts',
    type: 'archNode',
    position: { x: 220, y: 220 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    data: {
      nodeKey: 'frontendEcharts',
      icon: '📊',
      layer: 'frontend',
      auxiliary: true,
      upgradeInfoKey: 'charts3d',
    },
  },
  {
    id: 'frontend-websocket',
    type: 'archNode',
    position: { x: 400, y: 220 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    data: { nodeKey: 'frontendWebsocket', icon: '🔗', layer: 'frontend', auxiliary: true, planned: true },
  },
  {
    id: 'frontend-history',
    type: 'archNode',
    position: { x: 580, y: 220 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    data: { nodeKey: 'frontendHistory', icon: '⏮️', layer: 'frontend', auxiliary: true, planned: true },
  },
  {
    id: 'frontend-clipboard',
    type: 'archNode',
    position: { x: 760, y: 220 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    data: { nodeKey: 'frontendClipboard', icon: '📋', layer: 'frontend', auxiliary: true, planned: true },
  },
  {
    id: 'frontend-shortcuts',
    type: 'archNode',
    position: { x: 940, y: 220 },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    data: { nodeKey: 'frontendShortcuts', icon: '⌨️', layer: 'frontend', auxiliary: true, planned: true },
  },
  {
    id: 'communication',
    type: 'archNode',
    position: { x: 460, y: 390 },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Top,
    data: { nodeKey: 'communication', icon: '🔌', layer: 'communication' },
  },
  {
    id: 'backend-fastapi',
    type: 'archNode',
    position: { x: 40, y: 550 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    data: { nodeKey: 'backendFastapi', icon: '🚀', layer: 'backend' },
  },
  {
    id: 'backend-uvicorn',
    type: 'archNode',
    position: { x: 220, y: 550 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'backendUvicorn', icon: '🦄', layer: 'backend' },
  },
  {
    id: 'backend-workflow',
    type: 'archNode',
    position: { x: 400, y: 550 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: {
      nodeKey: 'backendWorkflow',
      icon: '⚙️',
      layer: 'backend',
      upgradeInfoKey: 'parallelExecution',
    },
  },
  {
    id: 'backend-function',
    type: 'archNode',
    position: { x: 580, y: 550 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'backendFunction', icon: '📚', layer: 'backend' },
  },
  {
    id: 'backend-auth',
    type: 'archNode',
    position: { x: 760, y: 550 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'backendAuth', icon: '🔐', layer: 'backend', auxiliary: true },
  },
  {
    id: 'backend-networkx',
    type: 'archNode',
    position: { x: 940, y: 550 },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Left,
    data: { nodeKey: 'backendNetworkx', icon: '🕸️', layer: 'backend', auxiliary: true },
  },
  {
    id: 'backend-numpy',
    type: 'archNode',
    position: { x: 40, y: 710 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    data: { nodeKey: 'backendNumpy', icon: '🔢', layer: 'backend', auxiliary: true },
  },
  {
    id: 'backend-scipy',
    type: 'archNode',
    position: { x: 220, y: 710 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'backendScipy', icon: '🧮', layer: 'backend', auxiliary: true },
  },
  {
    id: 'backend-version',
    type: 'archNode',
    position: { x: 400, y: 710 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    data: { nodeKey: 'backendVersion', icon: '📝', layer: 'backend', auxiliary: true, planned: true },
  },
  {
    id: 'backend-share',
    type: 'archNode',
    position: { x: 580, y: 710 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'backendShare', icon: '🤝', layer: 'backend', auxiliary: true, planned: true },
  },
  {
    id: 'backend-llm',
    type: 'archNode',
    position: { x: 760, y: 710 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'backendLlm', icon: '🤖', layer: 'backend', auxiliary: true, planned: true },
  },
  {
    id: 'backend-schedule',
    type: 'archNode',
    position: { x: 940, y: 710 },
    sourcePosition: Position.Bottom,
    targetPosition: Position.Left,
    data: { nodeKey: 'backendSchedule', icon: '⏰', layer: 'backend', auxiliary: true, planned: true },
  },
  {
    id: 'data-sqlalchemy',
    type: 'archNode',
    position: { x: 40, y: 880 },
    sourcePosition: Position.Right,
    targetPosition: Position.Top,
    data: { nodeKey: 'dataSqlalchemy', icon: '🔗', layer: 'data', upgradeInfoKey: 'postgres' },
  },
  {
    id: 'data-pydantic',
    type: 'archNode',
    position: { x: 220, y: 880 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'dataPydantic', icon: '✅', layer: 'data' },
  },
  {
    id: 'database',
    type: 'archNode',
    position: { x: 400, y: 880 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'database', icon: '💾', layer: 'database', upgradeInfoKey: 'postgres' },
  },
  {
    id: 'data-redis',
    type: 'archNode',
    position: { x: 580, y: 880 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'dataRedis', icon: '⚡', layer: 'data', planned: true },
  },
  {
    id: 'data-storage',
    type: 'archNode',
    position: { x: 760, y: 880 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'dataStorage', icon: '📦', layer: 'data', planned: true },
  },
  {
    id: 'data-search',
    type: 'archNode',
    position: { x: 940, y: 880 },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
    data: { nodeKey: 'dataSearch', icon: '🔍', layer: 'data', planned: true },
  },
];

const INITIAL_EDGES: Edge[] = [
  { id: 'e1', source: 'frontend-react', target: 'frontend-antd', animated: false, style: { stroke: '#1890ff', strokeWidth: 2 } },
  { id: 'e2', source: 'frontend-antd', target: 'frontend-zustand', animated: true, style: { stroke: '#1890ff', strokeWidth: 3 } },
  { id: 'e3', source: 'frontend-zustand', target: 'frontend-axios', animated: true, style: { stroke: '#1890ff', strokeWidth: 3 } },
  { id: 'e4', source: 'frontend-axios', target: 'frontend-router', animated: false, style: { stroke: '#91d5ff', strokeWidth: 1, strokeDasharray: '5,5' } },
  { id: 'e5', source: 'frontend-router', target: 'frontend-vite', animated: false, style: { stroke: '#91d5ff', strokeWidth: 1, strokeDasharray: '5,5' } },
  { id: 'e6', source: 'frontend-zustand', target: 'frontend-workflow', style: { stroke: '#91d5ff', strokeWidth: 1, strokeDasharray: '5,5' } },
  { id: 'e7', source: 'frontend-zustand', target: 'frontend-echarts', style: { stroke: '#91d5ff', strokeWidth: 1, strokeDasharray: '5,5' } },
  { id: 'e8', source: 'frontend-axios', target: 'frontend-websocket', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e9', source: 'frontend-workflow', target: 'frontend-history', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e10', source: 'frontend-workflow', target: 'frontend-clipboard', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e11', source: 'frontend-workflow', target: 'frontend-shortcuts', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e12', source: 'frontend-axios', target: 'communication', animated: true, style: { stroke: '#52c41a', strokeWidth: 4 } },
  { id: 'e13', source: 'communication', target: 'backend-fastapi', animated: true, style: { stroke: '#faad14', strokeWidth: 4 } },
  { id: 'e14', source: 'backend-fastapi', target: 'backend-uvicorn', animated: false, style: { stroke: '#722ed1', strokeWidth: 2 } },
  { id: 'e15', source: 'backend-uvicorn', target: 'backend-workflow', animated: true, style: { stroke: '#722ed1', strokeWidth: 3 } },
  { id: 'e16', source: 'backend-workflow', target: 'backend-function', animated: true, style: { stroke: '#722ed1', strokeWidth: 3 } },
  { id: 'e17', source: 'backend-function', target: 'backend-auth', animated: false, style: { stroke: '#d3adf7', strokeWidth: 1, strokeDasharray: '5,5' } },
  { id: 'e18', source: 'backend-auth', target: 'backend-networkx', animated: false, style: { stroke: '#d3adf7', strokeWidth: 1, strokeDasharray: '5,5' } },
  { id: 'e19', source: 'backend-workflow', target: 'backend-numpy', style: { stroke: '#d3adf7', strokeWidth: 1, strokeDasharray: '5,5' } },
  { id: 'e20', source: 'backend-numpy', target: 'backend-scipy', animated: false, style: { stroke: '#d3adf7', strokeWidth: 1, strokeDasharray: '5,5' } },
  { id: 'e21', source: 'backend-workflow', target: 'backend-version', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e22', source: 'backend-workflow', target: 'backend-share', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e23', source: 'backend-workflow', target: 'backend-llm', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e24', source: 'backend-workflow', target: 'backend-schedule', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e25', source: 'backend-workflow', target: 'data-sqlalchemy', animated: true, style: { stroke: '#eb2f96', strokeWidth: 3 } },
  { id: 'e26', source: 'backend-function', target: 'data-sqlalchemy', animated: true, style: { stroke: '#eb2f96', strokeWidth: 3 } },
  { id: 'e27', source: 'backend-auth', target: 'data-sqlalchemy', style: { stroke: '#ffadd2', strokeWidth: 1, strokeDasharray: '5,5' } },
  { id: 'e28', source: 'backend-version', target: 'data-sqlalchemy', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e29', source: 'backend-share', target: 'data-sqlalchemy', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e30', source: 'data-sqlalchemy', target: 'data-pydantic', style: { stroke: '#eb2f96', strokeWidth: 2 } },
  { id: 'e31', source: 'data-pydantic', target: 'database', animated: true, style: { stroke: '#13c2c2', strokeWidth: 4 } },
  { id: 'e32', source: 'data-sqlalchemy', target: 'database', animated: true, style: { stroke: '#13c2c2', strokeWidth: 3 } },
  { id: 'e33', source: 'database', target: 'data-redis', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e34', source: 'data-redis', target: 'data-storage', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e35', source: 'data-storage', target: 'data-search', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e36', source: 'backend-workflow', target: 'data-redis', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
  { id: 'e37', source: 'backend-schedule', target: 'data-redis', style: { stroke: '#bfbfbf', strokeWidth: 1, strokeDasharray: '3,3' } },
];

/**
 * 架构图组件：节点文案走 i18n（architecture.diagram.*），切换语言自动更新。
 */
const ArchitectureDiagram: React.FC = () => {
  const { i18n } = useTranslation();

  const nodes = useMemo(
    () => BASE_NODES.map((n) => ({ ...n, data: { ...n.data } })),
    [i18n.language],
  );

  const onInit = useCallback((reactFlowInstance: { fitView: (opts?: { padding?: number }) => void }) => {
    setTimeout(() => {
      reactFlowInstance.fitView({ padding: 0.05 });
    }, 100);
  }, []);

  return (
    <ReactFlowProvider>
      <div
        style={{
          width: '100%',
          height: '1000px',
          border: '1px solid #d9d9d9',
          borderRadius: '8px',
          background: '#fafafa',
        }}
      >
        <ReactFlow
          key={i18n.language}
          nodes={nodes}
          edges={INITIAL_EDGES}
          nodeTypes={nodeTypes}
          onInit={onInit}
          fitView
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
        >
          <Background color="#e0e0e0" gap={20} />
          <Controls showInteractive={false} />
          <MiniMap nodeStrokeWidth={3} zoomable pannable />
        </ReactFlow>
      </div>
    </ReactFlowProvider>
  );
};

export default ArchitectureDiagram;
