/**
 * Zoom Indicator Component
 * 显示当前画布缩放百分比
 */

import React from 'react';
import { useViewport } from 'reactflow';
import './ZoomIndicator.css';

const ZoomIndicator: React.FC = () => {
  const { zoom } = useViewport();
  
  // 计算百分比
  const percentage = Math.round(zoom * 100);
  
  return (
    <div className="zoom-indicator">
      {percentage}%
    </div>
  );
};

export default ZoomIndicator;
