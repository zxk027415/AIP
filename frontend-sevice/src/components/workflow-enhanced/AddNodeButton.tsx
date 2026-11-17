/**
 * Add Node Button Component
 * 端口添加节点按钮组件（纯展示组件，点击穿透到 Handle）
 */

import React, { useCallback, useRef, useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { PlusOutlined, RightOutlined } from '@ant-design/icons';
import type { NodeLibraryItem } from '../../utils/nodeLibraryData';
import { useTranslation } from 'react-i18next';
import { td } from '../../utils/dataTranslation';
import './AddNodeButton.css';

interface AddNodeButtonProps {
  onAddNode: (nodeType: string, nodeId: string) => void;
  position: 'left' | 'right';
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  nodeLibrary?: NodeLibraryItem[]; // 节点库数据
}

const AddNodeButton: React.FC<AddNodeButtonProps> = ({ 
  onAddNode, 
  position,
  open = false,
  onOpenChange,
  nodeLibrary = []
}) => {
  const { t } = useTranslation();
  const buttonRef = useRef<HTMLDivElement>(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['function']));

  // 计算菜单位置
  useEffect(() => {
    if (open && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const menuWidth = 280;
      const menuOffset = 10;
      
      if (position === 'left') {
        setMenuPosition({
          top: rect.top + rect.height / 2,
          left: rect.left - menuWidth - menuOffset
        });
      } else {
        setMenuPosition({
          top: rect.top + rect.height / 2,
          left: rect.right + menuOffset
        });
      }
    }
  }, [open, position]);

  const handleSelectNode = useCallback((nodeType: string, nodeId: string) => {
    onAddNode(nodeType, nodeId);
    onOpenChange?.(false);
  }, [onAddNode, onOpenChange]);

  const handleOverlayClick = useCallback(() => {
    onOpenChange?.(false);
  }, [onOpenChange]);

  const toggleCategory = useCallback((categoryId: string) => {
    setExpandedCategories(prev => {
      const newSet = new Set(prev);
      if (newSet.has(categoryId)) {
        newSet.delete(categoryId);
      } else {
        newSet.add(categoryId);
      }
      return newSet;
    });
  }, []);

  // 渲染树节点
  const renderTreeNode = (node: NodeLibraryItem, level: number = 0) => {
    const isExpanded = expandedCategories.has(node.id);
    const hasChildren = node.children && node.children.length > 0;

    if (hasChildren) {
      // 分类节点
      return (
        <div key={node.id} className="add-node-tree-category">
          <div 
            className="add-node-tree-category-header"
            onClick={() => toggleCategory(node.id)}
            style={{ paddingLeft: `${level * 12 + 8}px` }}
          >
            <RightOutlined 
              className={`add-node-tree-arrow ${isExpanded ? 'expanded' : ''}`}
            />
            <span className="add-node-tree-icon">{node.icon}</span>
            <span className="add-node-tree-category-name">{td(node.name)}</span>
          </div>
          {isExpanded && (
            <div className="add-node-tree-children">
              {node.children!.map(child => renderTreeNode(child, level + 1))}
            </div>
          )}
        </div>
      );
    } else {
      // 叶子节点
      return (
        <div
          key={node.id}
          className="add-node-tree-item"
          onClick={() => handleSelectNode(node.type, node.id)}
          style={{ paddingLeft: `${level * 12 + 28}px` }}
        >
          <span className="add-node-tree-icon">{node.icon}</span>
          <span className="add-node-tree-item-name">{td(node.name)}</span>
        </div>
      );
    }
  };

  return (
    <>
      {/* 添加按钮 - pointer-events: none 让点击穿透到 Handle */}
      <div ref={buttonRef} className={`add-node-button add-node-button-${position}`}>
        <PlusOutlined />
      </div>

      {/* 弹出菜单 - 使用 Portal 渲染到 body */}
      {open && createPortal(
        <>
          <div className="add-node-overlay" onClick={handleOverlayClick} />
          <div 
            className="add-node-menu"
            style={{
              top: `${menuPosition.top}px`,
              left: `${menuPosition.left}px`,
              transform: 'translateY(-50%)'
            }}
          >
            <div className="add-node-menu-header">
              <div className="add-node-menu-title">{t('workflowEditor.addNodeMenu.title')}</div>
            </div>
            <div className="add-node-menu-content add-node-tree-content">
              {nodeLibrary.length > 0 ? (
                nodeLibrary.map(node => renderTreeNode(node, 0))
              ) : (
                <div className="add-node-empty">{t('workflowEditor.addNodeMenu.empty')}</div>
              )}
            </div>
          </div>
        </>,
        document.body
      )}
    </>
  );
};

export default AddNodeButton;
