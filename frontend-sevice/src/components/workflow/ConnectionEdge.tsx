import React from 'react';
import { type EdgeProps, getSmoothStepPath, EdgeLabelRenderer } from 'reactflow';
import './ConnectionEdge.css';

const ConnectionEdge: React.FC<EdgeProps> = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style = {},
  data,
  selected,
  markerEnd,
}) => {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 8,
  });

  const hasError = data?.error;

  return (
    <>
      {/* 主连接线 */}
      <path
        id={id}
        className={`dify-edge ${selected ? 'selected' : ''} ${hasError ? 'error' : ''}`}
        d={edgePath}
        style={style}
        markerEnd={markerEnd}
      />
      
      {/* 选中时的高亮边框 */}
      {selected && (
        <path
          d={edgePath}
          className="dify-edge-selected-bg"
          style={{
            strokeWidth: 6,
            stroke: 'rgba(59, 130, 246, 0.2)',
            fill: 'none',
          }}
        />
      )}

      {/* 动画流动效果 */}
      {selected && (
        <path
          d={edgePath}
          className="dify-edge-animated"
          style={{
            strokeWidth: 2,
            stroke: '#3b82f6',
            fill: 'none',
            strokeDasharray: '5 5',
            animation: 'dashdraw 0.5s linear infinite',
          }}
        />
      )}

      {/* 错误标签 */}
      {hasError && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="dify-edge-error-label"
          >
            <div className="error-badge">
              <span className="error-icon">⚠️</span>
              <span className="error-text">类型不匹配</span>
            </div>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
};

export default ConnectionEdge;
