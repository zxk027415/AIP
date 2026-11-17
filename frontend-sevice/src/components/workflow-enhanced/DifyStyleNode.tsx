/**
 * Dify Style Node Component
 * 完全按照 Dify 设计的节点组件
 */

import React, { memo, useMemo, useState, useCallback, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import type { NodeProps } from 'reactflow';
import { 
  FunctionOutlined, 
  CalculatorOutlined, 
  BarChartOutlined, 
  BranchesOutlined, 
  RobotOutlined,
  LoadingOutlined,
  CheckCircleFilled,
  CloseCircleFilled,
  WarningFilled,
  HomeOutlined,
  CodeOutlined,
  DownloadOutlined,
  CloseOutlined
} from '@ant-design/icons';
import type { EnhancedNodeData } from '../../types/workflow-enhanced';
import { useNodeLibraryData } from '../../hooks/useNodeLibraryData';
import { useTranslation } from 'react-i18next';
import { td } from '../../utils/dataTranslation';
import AddNodeButton from './AddNodeButton';
import './DifyStyleNode.css';

const DifyStyleNode: React.FC<NodeProps<EnhancedNodeData>> = ({ data, selected, id }) => {
  const { i18n } = useTranslation();
  void i18n.language;
  // 节点 hover 状态
  const [nodeHovered, setNodeHovered] = useState(false);
  // 端口 hover 状态
  const [hoveredHandle, setHoveredHandle] = useState<string | null>(null);
  // 菜单状态 - 记录哪个端口的菜单是打开的
  const [openMenuHandle, setOpenMenuHandle] = useState<string | null>(null);

  // 使用共享的节点库数据 Hook
  const { nodeLibraryData } = useNodeLibraryData();

  // 处理添加节点
  const handleAddNode = useCallback((nodeType: string, nodeId: string) => {
    console.log('Add node:', nodeType, nodeId, 'from handle:', openMenuHandle);
    // TODO: 实现添加节点逻辑
  }, [openMenuHandle]);

  // Handle 点击处理 - 切换菜单显示
  const handleHandleClick = useCallback((e: React.MouseEvent, handleId: string) => {
    e.stopPropagation();
    setOpenMenuHandle(prev => prev === handleId ? null : handleId);
  }, []);

  // 菜单打开状态改变
  const handleMenuOpenChange = useCallback((handleId: string, open: boolean) => {
    setOpenMenuHandle(open ? handleId : null);
  }, []);

  // 根据节点类型选择图标
  const getIcon = () => {
    switch (data.type) {
      case 'start':
        return <HomeOutlined />;
      case 'code':
        return <CodeOutlined />;
      case 'end':
        return <DownloadOutlined />;
      case 'function':
        return <FunctionOutlined />;
      case 'matrix':
        return <CalculatorOutlined />;
      case 'visualization':
        return <BarChartOutlined />;
      case 'control':
        return <BranchesOutlined />;
      case 'llm':
        return <RobotOutlined />;
      default:
        return <FunctionOutlined />;
    }
  };

  // 根据节点类型选择颜色
  const getColor = () => {
    switch (data.type) {
      case 'start':
        return '#2970ff'; // Dify blue
      case 'code':
        return '#2970ff'; // Dify blue
      case 'end':
        return '#f79009'; // Dify orange
      case 'function':
        return '#2970ff'; // Dify blue
      case 'matrix':
        return '#7839ee'; // Dify violet
      case 'visualization':
        return '#17b26a'; // Dify green
      case 'control':
        return '#0ba5ec'; // Dify cyan
      case 'llm':
        return '#444ce7'; // Dify indigo
      default:
        return '#667085'; // Dify gray
    }
  };

  // 状态边框样式
  const {
    showSelectedBorder,
    showRunningBorder,
    showSuccessBorder,
    showFailedBorder,
  } = useMemo(() => {
    return {
      showSelectedBorder: selected,
      showRunningBorder: data.status === 'running' && !selected,
      showSuccessBorder: data.status === 'success' && !selected,
      showFailedBorder: data.status === 'error' && !selected,
    };
  }, [data.status, selected]);

  // 状态图标
  const getStatusIcon = () => {
    if (data.status === 'running') {
      return <LoadingOutlined className="dify-node-status-icon dify-node-status-running" />;
    }
    if (data.status === 'success') {
      return <CheckCircleFilled className="dify-node-status-icon dify-node-status-success" />;
    }
    if (data.status === 'error') {
      return <CloseCircleFilled className="dify-node-status-icon dify-node-status-error" />;
    }
    return null;
  };

  const color = getColor();

  return (
    <div
      className={`dify-node-wrapper ${showSelectedBorder ? 'dify-node-selected' : ''}`}
      onMouseEnter={() => setNodeHovered(true)}
      onMouseLeave={() => setNodeHovered(false)}
    >
      <div
        className={`dify-node ${showRunningBorder ? 'dify-node-running' : ''} ${showSuccessBorder ? 'dify-node-success' : ''} ${showFailedBorder ? 'dify-node-failed' : ''}`}
      >
        {/* 输入端口 - 单个端口，对齐到节点标题 */}
        {data.inputs.length > 0 && (
          <div
            className="dify-handle-wrapper dify-handle-wrapper-target"
            onMouseEnter={() => setHoveredHandle('input')}
            onMouseLeave={() => setHoveredHandle(null)}
          >
            <Handle
              type="target"
              position={Position.Left}
              id="input"
              className="dify-handle dify-handle-target"
              title={data.inputs.map(i => td(i.name)).join(', ')}
              onClick={(e) => handleHandleClick(e, 'input')}
            />
            {/* 加号按钮 - 始终渲染，用 CSS 控制可见性 */}
            <div className={`add-node-button-container ${(nodeHovered || selected || hoveredHandle === 'input') ? 'visible' : ''}`}>
              <AddNodeButton
                onAddNode={handleAddNode}
                position="left"
                open={openMenuHandle === 'input'}
                onOpenChange={(open) => handleMenuOpenChange('input', open)}
                nodeLibrary={nodeLibraryData}
              />
            </div>
          </div>
        )}

        {/* 节点头部 */}
        <div className="dify-node-header">
          {/* 图标 */}
          <div className="dify-node-icon-container">
            <div className="dify-node-icon" style={{ color }}>
              {getIcon()}
            </div>
          </div>

          {/* 标题 */}
          <div className="dify-node-title" title={td(data.label)}>
            {td(data.label)}
          </div>

          {/* 状态图标 */}
          {getStatusIcon()}
        </div>

        {/* 描述 */}
        {data.description && (
          <div className="dify-node-description">
            {td(data.description)}
          </div>
        )}

        {/* 字段列表 - 显示输入或输出字段 */}
        {(data.type === 'start' || data.type === 'end') && (
          <div className="dify-node-fields">
            {data.type === 'start' && data.outputs.map((output) => (
              <div key={output.id} className="dify-node-field">
                <CloseOutlined className="dify-node-field-icon" />
                <span className="dify-node-field-name">{td(output.name)}</span>
                <span className="dify-node-field-label">{td('必填')} #</span>
              </div>
            ))}
            {data.type === 'end' && data.outputs.map((output) => (
              <div key={output.id} className="dify-node-field">
                <CloseOutlined className="dify-node-field-icon" />
                <span className="dify-node-field-name">
                  {'{'}x{'}'} {td(output.name)}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* 错误信息 */}
        {data.error && (
          <div className="dify-node-error">
            <WarningFilled style={{ marginRight: 4 }} />
            {td(data.error)}
          </div>
        )}

        {/* 输出端口 - 单个端口，对齐到节点标题 */}
        {data.outputs.length > 0 && (
          <div
            className="dify-handle-wrapper dify-handle-wrapper-source"
            onMouseEnter={() => setHoveredHandle('output')}
            onMouseLeave={() => setHoveredHandle(null)}
          >
            <Handle
              type="source"
              position={Position.Right}
              id="output"
              className="dify-handle dify-handle-source"
              title={data.outputs.map(o => td(o.name)).join(', ')}
              onClick={(e) => handleHandleClick(e, 'output')}
            />
            {/* 加号按钮 - 始终渲染，用 CSS 控制可见性 */}
            <div className={`add-node-button-container ${(nodeHovered || selected || hoveredHandle === 'output') ? 'visible' : ''}`}>
              <AddNodeButton
                onAddNode={handleAddNode}
                position="right"
                open={openMenuHandle === 'output'}
                onOpenChange={(open) => handleMenuOpenChange('output', open)}
                nodeLibrary={nodeLibraryData}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default memo(DifyStyleNode);
