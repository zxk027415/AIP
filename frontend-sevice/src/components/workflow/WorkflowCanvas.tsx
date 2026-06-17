import React, { useCallback, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  ReactFlowProvider,
  BackgroundVariant,
  type Connection,
  type Edge,
  type Node,
  type ReactFlowInstance,
  type NodeChange,
  type EdgeChange,
} from 'reactflow';
import 'reactflow/dist/style.css';
import type { WorkflowNode, WorkflowEdge, Port } from '../../types/workflow';
import type { FunctionDefinition } from '../../types/function';
import { functionApi } from '../../services/api';
import { message } from 'antd';
import ModuleNode from './ModuleNode';
import ConnectionEdge from './ConnectionEdge';

// 将 nodeTypes 和 edgeTypes 移到组件外部，避免每次渲染都重新创建
const nodeTypes = {
  function: ModuleNode,
  matrix: ModuleNode,
  visualization: ModuleNode,
};

const edgeTypes = {
  default: ConnectionEdge,
};

interface WorkflowCanvasProps {
  initialNodes?: WorkflowNode[];
  initialEdges?: WorkflowEdge[];
  onNodesChange?: (nodes: WorkflowNode[]) => void;
  onEdgesChange?: (edges: WorkflowEdge[]) => void;
  onNodeSelect?: (nodeId: string | null) => void;
}

const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({
  initialNodes = [],
  initialEdges = [],
  onNodesChange,
  onEdgesChange,
  onNodeSelect,
}) => {
  const [nodes, setNodes, onNodesChangeInternal] = useNodesState(initialNodes as Node[]);
  const [edges, setEdges, onEdgesChangeInternal] = useEdgesState(initialEdges as Edge[]);
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const reactFlowInstance = useRef<ReactFlowInstance | null>(null);
  
  // 跟踪拖拽状态
  const isDraggingRef = useRef(false);

  // Validate connection type compatibility
  const validateConnection = useCallback((connection: Connection): boolean => {
    if (!connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) {
      return false;
    }

    const sourceNode = nodes.find((n) => n.id === connection.source) as WorkflowNode | undefined;
    const targetNode = nodes.find((n) => n.id === connection.target) as WorkflowNode | undefined;

    if (!sourceNode || !targetNode) {
      return false;
    }

    const sourcePort = sourceNode.data.outputs.find((p: Port) => p.id === connection.sourceHandle);
    const targetPort = targetNode.data.inputs.find((p: Port) => p.id === connection.targetHandle);

    if (!sourcePort || !targetPort) {
      return false;
    }

    // Check type compatibility
    if (!areTypesCompatible(sourcePort.type, targetPort.type)) {
      message.error(`端口类型不兼容: ${sourcePort.type} -> ${targetPort.type}`);
      return false;
    }

    return true;
  }, [nodes]);

  // Type compatibility rules
  const areTypesCompatible = (sourceType: string, targetType: string): boolean => {
    if (sourceType === targetType) {
      return true;
    }
    // number can convert to array
    if (sourceType === 'number' && targetType === 'array') {
      return true;
    }
    // array can convert to matrix
    if (sourceType === 'array' && targetType === 'matrix') {
      return true;
    }
    return false;
  };

  // Handle connection
  const onConnect = useCallback((params: Connection) => {
    if (validateConnection(params)) {
      setEdges((eds) => addEdge(params, eds));
      if (onEdgesChange) {
        const newEdges = [...edges, params] as WorkflowEdge[];
        onEdgesChange(newEdges);
      }
    }
  }, [validateConnection, setEdges, edges, onEdgesChange]);

  // Handle drag over
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    console.log('Drag over canvas');
  }, []);

  // Handle drop - add node from function library
  const onDrop = useCallback(async (event: React.DragEvent) => {
    event.preventDefault();

    const functionId = event.dataTransfer.getData('functionId');
    const functionLabel = event.dataTransfer.getData('functionLabel');
    
    console.log('Drop event:', { functionId, functionLabel });
    
    if (!functionId || !reactFlowInstance.current) {
      console.log('Drop failed:', { functionId, hasInstance: !!reactFlowInstance.current });
      return;
    }

    const position = reactFlowInstance.current.screenToFlowPosition({
      x: event.clientX,
      y: event.clientY,
    });

    try {
      // 获取函数定义以创建正确的输入/输出端口
      const functionDef = await functionApi.getFunction(functionId) as FunctionDefinition;
      
      console.log('Function definition:', functionDef);
      
      // 创建输入端口
      const inputs: Port[] = functionDef.parameters.map((param, index) => ({
        id: `input-${index}`,
        name: param.name,
        type: param.type,
        required: param.required || false,
      }));

      // 创建输出端口
      const outputs: Port[] = [{
        id: 'output-0',
        name: 'result',
        type: functionDef.returnType || functionDef.return_type || 'any',
        required: true,
      }];

      console.log('Created ports:', { inputs, outputs });

      const newNode: WorkflowNode = {
        id: `node-${Date.now()}`,
        type: 'function',
        position,
        data: {
          label: functionLabel || functionDef.name,
          functionId,
          parameters: {},
          inputs,
          outputs,
        },
      };

      console.log('Creating new node with ports:', newNode);
      
      setNodes((nds) => [...nds, newNode as Node]);
      if (onNodesChange) {
        onNodesChange([...nodes as WorkflowNode[], newNode]);
      }
    } catch (error) {
      console.error('Failed to create node:', error);
      message.error('创建节点失败');
    }
  }, [nodes, setNodes, onNodesChange]);

  // Handle node selection
  const onNodeClick = useCallback((_event: React.MouseEvent, node: Node) => {
    if (onNodeSelect) {
      onNodeSelect(node.id);
    }
  }, [onNodeSelect]);

  // Handle pane click (deselect)
  const onPaneClick = useCallback(() => {
    if (onNodeSelect) {
      onNodeSelect(null);
    }
  }, [onNodeSelect]);

  // Handle nodes change - 拖拽时不同步，拖拽结束后才同步
  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    // 立即应用到 React Flow（这个很快，不会卡）
    onNodesChangeInternal(changes);
    
    // 检查变化类型
    const hasSelect = changes.some(c => c.type === 'select');
    const hasDragging = changes.some(c => 
      c.type === 'position' && 
      'dragging' in c && 
      c.dragging === true
    );
    const hasDragEnd = changes.some(c => 
      c.type === 'position' && 
      'dragging' in c && 
      c.dragging === false
    );
    
    // 拖拽中：不同步
    if (hasDragging) {
      isDraggingRef.current = true;
      return;
    }
    
    // 拖拽结束：同步一次
    if (hasDragEnd) {
      isDraggingRef.current = false;
      if (onNodesChange) {
        setNodes((currentNodes) => {
          onNodesChange(currentNodes as WorkflowNode[]);
          return currentNodes;
        });
      }
      return;
    }
    
    // 选择操作：不同步到 store（选择状态由 React Flow 管理）
    if (hasSelect) {
      return;
    }
    
    // 其他变化（删除、添加等）：立即同步
    if (!isDraggingRef.current && onNodesChange) {
      setNodes((currentNodes) => {
        onNodesChange(currentNodes as WorkflowNode[]);
        return currentNodes;
      });
    }
  }, [onNodesChangeInternal, onNodesChange, setNodes]);

  // Handle edges change - 边的变化不频繁，直接同步
  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    onEdgesChangeInternal(changes);
    if (onEdgesChange) {
      setEdges((currentEdges) => {
        onEdgesChange(currentEdges as WorkflowEdge[]);
        return currentEdges;
      });
    }
  }, [onEdgesChangeInternal, onEdgesChange, setEdges]);

  return (
    <div ref={reactFlowWrapper} style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={onConnect}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        onInit={(instance) => {
          reactFlowInstance.current = instance;
        }}
        defaultEdgeOptions={{
          type: 'default',
          animated: false,
          style: { stroke: '#94a3b8', strokeWidth: 2 },
        }}
        connectionLineStyle={{ stroke: '#3b82f6', strokeWidth: 2 }}
        connectionLineType={'smoothstep' as any}
        defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
        minZoom={0.2}
        maxZoom={2}
        snapToGrid={false}
        snapGrid={[10, 10]}
        fitView={false}
        fitViewOptions={{
          padding: 0.2,
          maxZoom: 1,
        }}
        nodesDraggable={true}
        nodesConnectable={true}
        elementsSelectable={true}
        selectNodesOnDrag={false}
      >
        <Background 
          variant={BackgroundVariant.Dots} 
          gap={20} 
          size={1}
          color="#cbd5e1"
        />
        <Controls 
          showZoom={true}
          showFitView={true}
          showInteractive={true}
          position="bottom-right"
        />
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
          style={{
            background: '#f8fafc',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
          }}
        />
      </ReactFlow>
    </div>
  );
};

// Wrap with ReactFlowProvider
const WorkflowCanvasWithProvider: React.FC<WorkflowCanvasProps> = (props) => {
  return (
    <ReactFlowProvider>
      <WorkflowCanvas {...props} />
    </ReactFlowProvider>
  );
};

export default WorkflowCanvasWithProvider;
