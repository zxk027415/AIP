import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { WorkflowNodeData, Port } from '../../types/workflow';
import './ModuleNode.css';

const ModuleNode: React.FC<NodeProps<WorkflowNodeData>> = ({ data, selected }) => {
  const getPortColor = (type: string): string => {
    const colorMap: Record<string, string> = {
      number: '#3b82f6',
      array: '#10b981',
      matrix: '#8b5cf6',
      object: '#f59e0b',
      string: '#ef4444',
      boolean: '#06b6d4',
    };
    return colorMap[type] || '#6b7280';
  };

  // 获取节点图标
  const getNodeIcon = () => {
    if (data.icon) return data.icon;
    // 根据函数类型返回默认图标
    if (data.functionId?.includes('matrix')) return '📊';
    if (data.functionId?.includes('math')) return '🔢';
    if (data.functionId?.includes('plot') || data.functionId?.includes('chart')) return '📈';
    return '⚙️';
  };

  return (
    <div className={`dify-node ${selected ? 'selected' : ''} ${data.error ? 'error' : ''}`}>
      {/* 输入端口 */}
      {data.inputs && data.inputs.length > 0 && data.inputs.map((input: Port, index: number) => (
        <Handle
          key={input.id}
          type="target"
          position={Position.Left}
          id={input.id}
          className="dify-port dify-port-input"
          style={{
            top: `${((index + 1) / (data.inputs.length + 1)) * 100}%`,
            background: getPortColor(input.type),
          }}
          title={`${input.name} (${input.type})${input.required ? ' *' : ''}`}
        />
      ))}

      {/* 节点内容 */}
      <div className="dify-node-content">
        <div className="dify-node-icon">{getNodeIcon()}</div>
        <div className="dify-node-title">{data.label}</div>
      </div>

      {/* 输出端口 */}
      {data.outputs && data.outputs.length > 0 && data.outputs.map((output: Port, index: number) => (
        <Handle
          key={output.id}
          type="source"
          position={Position.Right}
          id={output.id}
          className="dify-port dify-port-output"
          style={{
            top: `${((index + 1) / (data.outputs.length + 1)) * 100}%`,
            background: getPortColor(output.type),
          }}
          title={`${output.name} (${output.type})`}
        />
      ))}

      {/* 错误提示 */}
      {data.error && (
        <div className="dify-node-error">
          <span className="error-icon">⚠️</span>
          <span className="error-text">{data.error}</span>
        </div>
      )}
    </div>
  );
};

// 使用 memo 优化，只在 data 或 selected 变化时重渲染
export default memo(ModuleNode, (prevProps, nextProps) => {
  return (
    prevProps.selected === nextProps.selected &&
    prevProps.data === nextProps.data &&
    prevProps.id === nextProps.id
  );
});
