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
import { ContextMenu, ContextMenuItem } from './ContextMenu';
import { historyManager } from '../../utils/commands';
import { useUndoRedoShortcuts } from '../../hooks/useKeyboardShortcuts';
import { useClipboardShortcuts } from '../../hooks/useClipboardShortcuts';
import { clipboardManager } from '../../utils/clipboard';

const initialNodes: Node[] = [
  {
    id: '1',
    type: 'default',
    data: { label: '节点 1' },
    position: { x: 250, y: 100 },
  },
  {
    id: '2',
    type: 'default',
    data: { label: '节点 2' },
    position: { x: 250, y: 250 },
  },
];

const initialEdges: Edge[] = [
  { id: 'e1-2', source: '1', target: '2' },
];

export const WorkflowEditorWithClipboard: React.FC = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [historyPanelOpen, setHistoryPanelOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number } | null>(null);

  // 启用撤销/重做快捷键
  useUndoRedoShortcuts();

  // 获取选中的节点和边
  const selectedNodes = nodes.filter(n => n.selected);
  const selectedEdges = edges.filter(e => e.selected);

  // 添加节点和边的回调
  const handleAddNodes = useCallback((newNodes: Node[], newEdges: Edge[]) => {
    setNodes((nds) => {
      // 先取消所有选择
      const deselectedNodes = nds.map(n => ({ ...n, selected: false }));
      return [...deselectedNodes, ...newNodes];
    });
    setEdges((eds) => [...eds, ...newEdges]);
  }, [setNodes, setEdges]);

  // 删除节点和边的回调
  const handleRemoveNodes = useCallback((nodeIds: string[], edgeIds: string[]) => {
    setNodes((nds) => nds.filter(n => !nodeIds.includes(n.id)));
    setEdges((eds) => eds.filter(e => !edgeIds.includes(e.id)));
  }, [setNodes, setEdges]);

  // 取消所有选择
  const handleDeselectAll = useCallback(() => {
    setNodes((nds) => nds.map(n => ({ ...n, selected: false })));
    setEdges((eds) => eds.map(e => ({ ...e, selected: false })));
  }, [setNodes, setEdges]);

  // 启用剪贴板快捷键
  const {
    handleCopy,
    handleCut,
    handlePaste,
    handleDuplicate,
    hasClipboardData,
  } = useClipboardShortcuts({
    selectedNodes,
    selectedEdges,
    allEdges: edges,
    onAddNodes: handleAddNodes,
    onRemoveNodes: handleRemoveNodes,
    onDeselectAll: handleDeselectAll,
  });

  // 处理右键菜单
  const handleContextMenu = useCallback((event: React.MouseEvent) => {
    event.preventDefault();
    setContextMenu({ x: event.clientX, y: event.clientY });
  }, []);

  // 构建右键菜单项
  const contextMenuItems: ContextMenuItem[] = [
    {
      label: '复制',
      icon: '📋',
      shortcut: 'Ctrl+C',
      disabled: selectedNodes.length === 0,
      onClick: handleCopy,
    },
    {
      label: '剪切',
      icon: '✂️',
      shortcut: 'Ctrl+X',
      disabled: selectedNodes.length === 0,
      onClick: handleCut,
    },
    {
      label: '粘贴',
      icon: '📄',
      shortcut: 'Ctrl+V',
      disabled: !hasClipboardData,
      onClick: handlePaste,
    },
    {
      label: '复制',
      icon: '📑',
      shortcut: 'Ctrl+D',
      disabled: selectedNodes.length === 0,
      onClick: handleDuplicate,
    },
    {
      divider: true,
      label: '',
      onClick: () => {},
    },
    {
      label: '删除',
      icon: '🗑️',
      shortcut: 'Delete',
      disabled: selectedNodes.length === 0,
      onClick: () => {
        const nodeIds = selectedNodes.map(n => n.id);
        const edgeIds = edges
          .filter(e => nodeIds.includes(e.source) || nodeIds.includes(e.target))
          .map(e => e.id);
        handleRemoveNodes(nodeIds, edgeIds);
      },
    },
    {
      divider: true,
      label: '',
      onClick: () => {},
    },
    {
      label: '全选',
      icon: '☑️',
      shortcut: 'Ctrl+A',
      onClick: () => {
        setNodes((nds) => nds.map(n => ({ ...n, selected: true })));
      },
    },
  ];

  return (
    <div style={{ width: '100%', height: '100vh' }} onContextMenu={handleContextMenu}>
      <div style={{ position: 'absolute', top: 10, left: 10, zIndex: 10 }}>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
          <button
            onClick={handleCopy}
            disabled={selectedNodes.length === 0}
            style={{
              padding: '8px 16px',
              background: selectedNodes.length === 0 ? '#d1d5db' : '#3b82f6',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: selectedNodes.length === 0 ? 'not-allowed' : 'pointer',
            }}
          >
            📋 复制 (Ctrl+C)
          </button>
          <button
            onClick={handleCut}
            disabled={selectedNodes.length === 0}
            style={{
              padding: '8px 16px',
              background: selectedNodes.length === 0 ? '#d1d5db' : '#ef4444',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: selectedNodes.length === 0 ? 'not-allowed' : 'pointer',
            }}
          >
            ✂️ 剪切 (Ctrl+X)
          </button>
          <button
            onClick={handlePaste}
            disabled={!hasClipboardData}
            style={{
              padding: '8px 16px',
              background: !hasClipboardData ? '#d1d5db' : '#10b981',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: !hasClipboardData ? 'not-allowed' : 'pointer',
            }}
          >
            📄 粘贴 (Ctrl+V)
          </button>
          <button
            onClick={handleDuplicate}
            disabled={selectedNodes.length === 0}
            style={{
              padding: '8px 16px',
              background: selectedNodes.length === 0 ? '#d1d5db' : '#f59e0b',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: selectedNodes.length === 0 ? 'not-allowed' : 'pointer',
            }}
          >
            📑 复制 (Ctrl+D)
          </button>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            onClick={() => historyManager.undo()}
            disabled={!historyManager.canUndo()}
            style={{
              padding: '8px 16px',
              background: '#10b981',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            ↶ 撤销
          </button>
          <button
            onClick={() => historyManager.redo()}
            disabled={!historyManager.canRedo()}
            style={{
              padding: '8px 16px',
              background: '#f59e0b',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
            }}
          >
            ↷ 重做
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
            历史
          </button>
        </div>
      </div>

      <div style={{ position: 'absolute', top: 10, right: 10, zIndex: 10, background: 'white', padding: '12px', borderRadius: '8px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
        <div style={{ fontSize: '14px', color: '#6b7280' }}>
          <div>选中节点: {selectedNodes.length}</div>
          <div>剪贴板: {hasClipboardData ? '有数据' : '空'}</div>
        </div>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
      >
        <Controls />
        <Background />
      </ReactFlow>

      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenuItems}
          onClose={() => setContextMenu(null)}
        />
      )}

      <HistoryPanel
        isOpen={historyPanelOpen}
        onClose={() => setHistoryPanelOpen(false)}
      />
    </div>
  );
};
