import { useCallback } from 'react';
import { Node, Edge } from 'reactflow';
import { useKeyboardShortcuts } from './useKeyboardShortcuts';
import { clipboardManager } from '../utils/clipboard';
import { historyManager } from '../utils/commands';
import { PasteCommand, CutCommand, DuplicateCommand } from '../utils/clipboard/ClipboardCommands';

interface ClipboardShortcutsConfig {
  selectedNodes: Node[];
  selectedEdges: Edge[];
  allEdges: Edge[];
  onAddNodes: (nodes: Node[], edges: Edge[]) => void;
  onRemoveNodes: (nodeIds: string[], edgeIds: string[]) => void;
  onDeselectAll: () => void;
}

/**
 * 剪贴板快捷键 Hook
 */
export const useClipboardShortcuts = ({
  selectedNodes,
  selectedEdges,
  allEdges,
  onAddNodes,
  onRemoveNodes,
  onDeselectAll,
}: ClipboardShortcutsConfig) => {
  
  // 复制
  const handleCopy = useCallback(() => {
    if (selectedNodes.length === 0) return;
    
    // 获取选中节点相关的边
    const nodeIds = new Set(selectedNodes.map(n => n.id));
    const relatedEdges = allEdges.filter(
      e => nodeIds.has(e.source) && nodeIds.has(e.target)
    );
    
    clipboardManager.copy(selectedNodes, relatedEdges);
    console.log(`已复制 ${selectedNodes.length} 个节点`);
  }, [selectedNodes, allEdges]);

  // 剪切
  const handleCut = useCallback(() => {
    if (selectedNodes.length === 0) return;
    
    const nodeIds = new Set(selectedNodes.map(n => n.id));
    const relatedEdges = allEdges.filter(
      e => nodeIds.has(e.source) || nodeIds.has(e.target)
    );
    
    const command = new CutCommand(
      selectedNodes,
      relatedEdges,
      (nodes, edges) => clipboardManager.copy(nodes, edges),
      (nodeIds, edgeIds) => onRemoveNodes(nodeIds, edgeIds),
      (nodes, edges) => onAddNodes(nodes, edges)
    );
    
    historyManager.execute(command);
    console.log(`已剪切 ${selectedNodes.length} 个节点`);
  }, [selectedNodes, allEdges, onAddNodes, onRemoveNodes]);

  // 粘贴
  const handlePaste = useCallback(() => {
    if (!clipboardManager.hasData()) {
      console.log('剪贴板为空');
      return;
    }
    
    const pastedData = clipboardManager.paste();
    if (!pastedData) return;
    
    // 先取消所有选择
    onDeselectAll();
    
    const command = new PasteCommand(
      pastedData.nodes,
      pastedData.edges,
      (nodes, edges) => onAddNodes(nodes, edges),
      (nodeIds, edgeIds) => onRemoveNodes(nodeIds, edgeIds)
    );
    
    historyManager.execute(command);
    console.log(`已粘贴 ${pastedData.nodes.length} 个节点`);
  }, [onAddNodes, onRemoveNodes, onDeselectAll]);

  // 复制（Duplicate）
  const handleDuplicate = useCallback(() => {
    if (selectedNodes.length === 0) return;
    
    const nodeIds = new Set(selectedNodes.map(n => n.id));
    const relatedEdges = allEdges.filter(
      e => nodeIds.has(e.source) && nodeIds.has(e.target)
    );
    
    // 临时复制到剪贴板
    clipboardManager.copy(selectedNodes, relatedEdges);
    const duplicatedData = clipboardManager.paste();
    
    if (!duplicatedData) return;
    
    // 先取消所有选择
    onDeselectAll();
    
    const command = new DuplicateCommand(
      selectedNodes,
      relatedEdges,
      duplicatedData.nodes,
      duplicatedData.edges,
      (nodes, edges) => onAddNodes(nodes, edges),
      (nodeIds, edgeIds) => onRemoveNodes(nodeIds, edgeIds)
    );
    
    historyManager.execute(command);
    console.log(`已复制 ${selectedNodes.length} 个节点`);
  }, [selectedNodes, allEdges, onAddNodes, onRemoveNodes, onDeselectAll]);

  // 注册快捷键
  useKeyboardShortcuts([
    {
      key: 'c',
      ctrl: true,
      handler: handleCopy,
      description: '复制',
    },
    {
      key: 'x',
      ctrl: true,
      handler: handleCut,
      description: '剪切',
    },
    {
      key: 'v',
      ctrl: true,
      handler: handlePaste,
      description: '粘贴',
    },
    {
      key: 'd',
      ctrl: true,
      handler: handleDuplicate,
      description: '复制',
    },
  ]);

  return {
    handleCopy,
    handleCut,
    handlePaste,
    handleDuplicate,
    hasClipboardData: clipboardManager.hasData(),
  };
};
