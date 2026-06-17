/**
 * Enhanced Node Component
 * 增强版节点组件
 */

import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import type { NodeProps } from 'reactflow';
import { FunctionOutlined, CalculatorOutlined, BarChartOutlined, BranchesOutlined, RobotOutlined } from '@ant-design/icons';
import type { EnhancedNodeData } from '../../types/workflow-enhanced';
// @AI_GENERATED
import { td } from '../../utils/dataTranslation';
// @AI_GENERATED: end
import './EnhancedNode.css';

const EnhancedNode: React.FC<NodeProps<EnhancedNodeData>> = ({ data, selected }) => {
  // 根据节点类型选择图标
  const getIcon = () => {
    switch (data.type) {
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
      case 'function':
        return '#3b82f6'; // blue
      case 'matrix':
        return '#8b5cf6'; // purple
      case 'visualization':
        return '#10b981'; // green
      case 'control':
        return '#f59e0b'; // amber
      case 'llm':
        return '#ec4899'; // pink
      default:
        return '#6b7280'; // gray
    }
  };

  // 根据状态选择边框颜色
  const getBorderColor = () => {
    if (selected) return '#3b82f6';
    switch (data.status) {
      case 'running':
        return '#f59e0b';
      case 'success':
        return '#10b981';
      case 'error':
        return '#ef4444';
      default:
        return '#e5e7eb';
    }
  };

  const color = getColor();
  const borderColor = getBorderColor();

  return (
    <div
      className="enhanced-node"
      style={{
        borderColor,
        boxShadow: selected ? `0 0 0 2px ${borderColor}` : undefined,
      }}
    >
      {/* 输入端口 */}
      {data.inputs.map((input, index) => (
        <Handle
          key={input.id}
          type="target"
          position={Position.Left}
          id={input.id}
          className="react-flow__handle-left"
          style={{
            top: `${((index + 1) / (data.inputs.length + 1)) * 100}%`,
          }}
          title={`${td(input.name)} (${input.dataType})`}
        />
      ))}

      {/* 节点内容 */}
      <div className="enhanced-node-header" style={{ background: color }}>
        <div className="enhanced-node-icon">{getIcon()}</div>
        <div className="enhanced-node-title">{td(data.label)}</div>
      </div>

      {data.description && (
        <div className="enhanced-node-description">{td(data.description)}</div>
      )}

      {/* 状态指示器 */}
      {data.status && data.status !== 'idle' && (
        <div className={`enhanced-node-status enhanced-node-status-${data.status}`}>
          {data.status === 'running' && td('运行中...')}
          {data.status === 'success' && td('✓ 成功')}
          {data.status === 'error' && td('✗ 错误')}
        </div>
      )}

      {/* 错误信息 */}
      {data.error && (
        <div className="enhanced-node-error" title={data.error}>
          {data.error}
        </div>
      )}

      {/* 输出端口 */}
      {data.outputs.map((output, index) => (
        <Handle
          key={output.id}
          type="source"
          position={Position.Right}
          id={output.id}
          className="react-flow__handle-right"
          style={{
            top: `${((index + 1) / (data.outputs.length + 1)) * 100}%`,
          }}
          title={`${td(output.name)} (${output.dataType})`}
        />
      ))}
    </div>
  );
};

export default memo(EnhancedNode);
