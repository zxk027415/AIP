/**
 * Dify Style Node Component - High Definition Version
 * 高清版本：使用反向缩放技术保持文字清晰
 */

import React, { memo, useMemo, useState, useCallback } from 'react';
import { Handle, Position, useViewport } from 'reactflow';
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
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { td } from '../../utils/dataTranslation';
// @AI_GENERATED: end
import { useNodeLibraryData } from '../../hooks/useNodeLibraryData';
import AddNodeButton from './AddNodeButton';
import './DifyStyleNode.css';

const DifyStyleNodeHD: React.FC<NodeProps<EnhancedNodeData>> = ({ data, selected, id }) => {
  const { i18n } = useTranslation();
  void i18n.language;
  // 获取当前视口缩放级别
  const { zoom } = useViewport();
  
  // 节点 hover 状态
  const [nodeHovered, setNodeHovered] = useState(false);
  // 端口 hover 状态
  const [hoveredHandle, setHoveredHandle] = useState<string | null>(null);
  // 菜单状态
  const [openMenuHandle, setOpenMenuHandle] = useState<string | null>(null);

  // 使用共享的节点库数据 Hook
  const { nodeLibraryData } = useNodeLibraryData();

  // V12 强制重新渲染方案：使用 key 强制 React 在缩放变化时重新创建节点
  // 将 zoom 四舍五入到 0.1，避免过于频繁的重新渲染
  const zoomKey = Math.round(zoom * 10) / 10;

  // 处理添加节点
  const handleAddNode = useCallback((nodeType: string, nodeId: string) => {
    console.log('Add node:', nodeType, nodeId, 'from handle:', openMenuHandle);
  }, [openMenuHandle]);

  // Handle 点击处理
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
        return '#2970ff';
      case 'code':
        return '#2970ff';
      case 'end':
        return '#f79009';
      case 'function':
        return '#2970ff';
      case 'matrix':
        return '#7839ee';
      case 'visualization':
        return '#17b26a';
      case 'control':
        return '#0ba5ec';
      case 'llm':
        return '#444ce7';
      default:
        return '#667085';
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
      key={`${id}-${zoomKey}`}
      className={`dify-node-wrapper ${showSelectedBorder ? 'dify-node-selected' : ''}`}
      onMouseEnter={() => setNodeHovered(true)}
      onMouseLeave={() => setNodeHovered(false)}
      style={{
        // V12: 使用 key 强制重新渲染（解决缩放模糊）
        width: '240px',
        height: 'auto',
        // 拖动时保持清晰的关键优化
        willChange: 'transform',
        transform: 'translate3d(0, 0, 0)',
        backfaceVisibility: 'hidden',
        WebkitBackfaceVisibility: 'hidden',
        WebkitFontSmoothing: 'subpixel-antialiased',
        MozOsxFontSmoothing: 'auto',
        // 强制像素对齐
        imageRendering: '-webkit-optimize-contrast' as any,
      }}
    >
      <div
        className={`dify-node ${showRunningBorder ? 'dify-node-running' : ''} ${showSuccessBorder ? 'dify-node-success' : ''} ${showFailedBorder ? 'dify-node-failed' : ''}`}
        style={{
          width: '240px',
        }}
      >
        {/* 输入端口 */}
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
              title={data.inputs.map((i) => td(i.name)).join(', ')}
              onClick={(e) => handleHandleClick(e, 'input')}
            />
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
          <div className="dify-node-icon-container">
            <div className="dify-node-icon" style={{ color }}>
              {getIcon()}
            </div>
          </div>
          <div className="dify-node-title" title={td(data.label)}>
            {td(data.label)}
          </div>
          {getStatusIcon()}
        </div>

        {/* 描述 */}
        {data.description && (
          <div className="dify-node-description">
            {td(data.description)}
          </div>
        )}

        {/* 字段列表 */}
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

        {/* 输出端口 */}
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
              title={data.outputs.map((o) => td(o.name)).join(', ')}
              onClick={(e) => handleHandleClick(e, 'output')}
            />
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

export default memo(DifyStyleNodeHD);
