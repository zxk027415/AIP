import React, { useState, useCallback } from 'react';
import ReactFlow, {
  Node,
  Edge,
  addEdge,
  Connection,
  useNodesState,
  useEdgesState,
  Controls,
  Background,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { HistoryPanel } from './HistoryPanel';
import { historyManager } from '../../utils/commands';
import {
  AddNodeCommand,
  DeleteNodeCommand,
  MoveNodeCommand,
  AddEdgeCommand,
  DeleteEdgeCommand,
  BatchCommand,
} from '../../utils/commands/NodeCommands';
import { useUndoRedoShortcuts } from '../../hooks/useKeyboardShortcuts';

const initialNodes: Node[] = [
  {
    id: '1',
    type: 'default',
    data: { label: '开始节点' },
    position: { x: 250, y: 5 },
  },
];

export const WorkflowEditorWithHistory: React.FC = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false);
  const [nodeIdCounter, setNodeIdCounter] = useState(2);

  // 启用撤销/重做快捷键
  useUndoRedoShortcuts();

  // 添加节点的回调
  const addNode = useCallback((node: Node) => {
    setNodes((nds) => [...nds, node]);
  }, [setNodes]);

  // 删除节点的回调
  const removeNode = useCallback((nodeId: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== nodeId));
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
  }, [setNodes, setEdges]);

  // 移动节点的回调
  const moveNode = useCallback((nodeId: string, position: { x: number; y: number }) => {
    setNodes((nds) =>
      nds.map((n) => (n.id === nodeId ? { ...n, position } : n))
    );
  }, [setNodes]);

  // 添加边的回调
  const addEdgeCallback = useCallback((edge: Edge) => {
    setEdges((eds) => [...eds, edge]);
  }, [setEdges]);

  // 删除边的回调
  const removeEdge = useCallback((edgeId: string) => {
    setEdges((eds) => eds.filter((e) => e.id !== edgeId));
  }, [setEdges]);

  // 处理添加新节点（使用命令模式）
  const handleAddNode = () => {
    const newNode: Node = {
      id: `${nodeIdCounter}`,
      type: 'default',
      data: { label: `节点 ${nodeIdCounter}` },
      position: {
        x: Math.random() * 400 + 100,
        y: Math.random() * 400 + 100,
      },
    };

    const command = new AddNodeCommand(newNode, addNode, removeNode);
    historyManager.execute(command);
    setNodeIdCounter(nodeIdCounter + 1);
  };

  // 处理删除节点（使用命令模式）
  const handleNodesDelete = useCallback((deletedNodes: Node[]) => {
    const commands = deletedNodes.map((node) => {
      const relatedEdges = edges.filter(
        (e) => e.source === node.id || e.target === node.id
      );
      return new DeleteNodeCommand(node, relatedEdges, addNode, removeNode, addEdgeCallback);
    });

    if (commands.length === 1) {
      historyManager.execute(commands[0]);
    } else if (commands.length > 1) {
      const batchCommand = new BatchCommand(commands, '删除多个节点');
      historyManager.execute(batchCommand);
    }
  }, [edges, addNode, removeNode, addEdgeCallback]);

  // 处理节点移动结束（使用命令模式）
  const handleNodeDragStop = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      const oldNode = nodes.find((n) => n.id === node.id);
      if (oldNode && (oldNode.position.x !== node.position.x || oldNode.position.y !== node.position.y)) {
        const command = new MoveNodeCommand(
          node.id,
          oldNode.position,
          node.position,
          moveNode
        );
        historyManager.execute(command);
      }
    },
    [nodes, moveNode]
  );

  // 处理连接（使用命令模式）
  const onConnect = useCallback(
    (connection: Connection) => {
      const newEdge: Edge = {
        id: `e${connection.source}-${connection.target}`,
        source: connection.source!,
        target: connection.target!,
      };

      const command = new AddEdgeCommand(newEdge, addEdgeCallback, removeEdge);
      historyManager.execute(command);
    },
    [addEdgeCallback, removeEdge]
  );

  // 处理删除边（使用命令模式）
  const handleEdgesDelete = useCallback((deletedEdges: Edge[]) => {
    const commands = deletedEdges.map(
      (edge) => new DeleteEdgeCommand(edge, addEdgeCallback, removeEdge)
    );

    if (commands.length === 1) {
      historyManager.execute(commands[0]);
    } else if (commands.length > 1) {
      const batchCommand = new BatchCommand(commands, '删除多条连接');
      historyManager.execute(batchCommand);
    }
  }, [addEdgeCallback, removeEdge]);

  return (
    <div style={{ width: '100%', height: '100vh' }}>
      <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 10 }}>
        <button
          onClick={handleAddNode}
          style={{
            padding: '8px 16px',
            marginRight: '8px',
            background: '#3b82f6',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          添加节点
        </button>
        <button
          onClick={() => historyManager.undo()}
          disabled={!historyManager.canUndo()}
          style={{
            padding: '8px 16px',
            marginRight: '8px',
            background: '#10b981',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          ↶ 撤销 (Ctrl+Z)
        </button>
        <button
          onClick={() => historyManager.redo()}
          disabled={!historyManager.canRedo()}
          style={{
            padding: '8px 16px',
            marginRight: '8px',
            background: '#f59e0b',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          ↷ 重做 (Ctrl+Y)
        </button>
        <button
          onClick={() => setHistoryPanelOpen(!historyPanelOpen)}
          style={{
            padding: '8px 16px',
            background: '#6366f1',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
          }}
        >
          {historyPanelOpen ? '关闭' : '打开'}历史面板
        </button>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodesDelete={handleNodesDelete}
        onEdgesDelete={handleEdgesDelete}
        onNodeDragStop={handleNodeDragStop}
        fitView
      >
        <Controls />
        <Background />
      </ReactFlow>

      <HistoryPanel
        isOpen={historyPanelOpen}
        onClose={() => setHistoryPanelOpen(false)}
      />
    </div>
  );
};
