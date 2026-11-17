import React from 'react';
import { Node } from 'reactflow';
import { AlignmentType, DistributionType, AlignmentUtils } from '../../utils/layout/AlignmentUtils';
import './AlignmentToolbar.css';

interface AlignmentToolbarProps {
  selectedNodes: Node[];
  onAlign: (alignedNodes: Node[]) => void;
  onAutoLayout: () => void;
}

export const AlignmentToolbar: React.FC<AlignmentToolbarProps> = ({
  selectedNodes,
  onAlign,
  onAutoLayout,
}) => {
  const hasSelection = selectedNodes.length >= 2;
  const canDistribute = selectedNodes.length >= 3;

  const handleAlign = (type: AlignmentType) => {
    if (!hasSelection) return;
    const alignedNodes = AlignmentUtils.align(selectedNodes, type);
    onAlign(alignedNodes);
  };

  const handleDistribute = (type: DistributionType) => {
    if (!canDistribute) return;
    const distributedNodes = AlignmentUtils.distribute(selectedNodes, type);
    onAlign(distributedNodes);
  };

  const handleSnapToGrid = () => {
    if (selectedNodes.length === 0) return;
    const snappedNodes = AlignmentUtils.snapToGrid(selectedNodes, 20);
    onAlign(snappedNodes);
  };

  return (
    <div className="alignment-toolbar">
      <div className="alignment-toolbar-section">
        <span className="alignment-toolbar-label">对齐</span>
        <div className="alignment-toolbar-buttons">
          <button
            className="alignment-btn"
            onClick={() => handleAlign(AlignmentType.LEFT)}
            disabled={!hasSelection}
            title="左对齐"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <rect x="2" y="2" width="8" height="3" fill="currentColor" />
              <rect x="2" y="6" width="12" height="3" fill="currentColor" />
              <rect x="2" y="10" width="6" height="3" fill="currentColor" />
              <line x1="1" y1="0" x2="1" y2="16" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>

          <button
            className="alignment-btn"
            onClick={() => handleAlign(AlignmentType.CENTER_HORIZONTAL)}
            disabled={!hasSelection}
            title="水平居中"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <rect x="4" y="2" width="8" height="3" fill="currentColor" />
              <rect x="2" y="6" width="12" height="3" fill="currentColor" />
              <rect x="5" y="10" width="6" height="3" fill="currentColor" />
              <line x1="8" y1="0" x2="8" y2="16" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>

          <button
            className="alignment-btn"
            onClick={() => handleAlign(AlignmentType.RIGHT)}
            disabled={!hasSelection}
            title="右对齐"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <rect x="6" y="2" width="8" height="3" fill="currentColor" />
              <rect x="2" y="6" width="12" height="3" fill="currentColor" />
              <rect x="8" y="10" width="6" height="3" fill="currentColor" />
              <line x1="15" y1="0" x2="15" y2="16" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>

          <div className="alignment-toolbar-divider" />

          <button
            className="alignment-btn"
            onClick={() => handleAlign(AlignmentType.TOP)}
            disabled={!hasSelection}
            title="顶部对齐"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <rect x="2" y="2" width="3" height="8" fill="currentColor" />
              <rect x="6" y="2" width="3" height="12" fill="currentColor" />
              <rect x="10" y="2" width="3" height="6" fill="currentColor" />
              <line x1="0" y1="1" x2="16" y2="1" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>

          <button
            className="alignment-btn"
            onClick={() => handleAlign(AlignmentType.CENTER_VERTICAL)}
            disabled={!hasSelection}
            title="垂直居中"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <rect x="2" y="4" width="3" height="8" fill="currentColor" />
              <rect x="6" y="2" width="3" height="12" fill="currentColor" />
              <rect x="10" y="5" width="3" height="6" fill="currentColor" />
              <line x1="0" y1="8" x2="16" y2="8" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>

          <button
            className="alignment-btn"
            onClick={() => handleAlign(AlignmentType.BOTTOM)}
            disabled={!hasSelection}
            title="底部对齐"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <rect x="2" y="6" width="3" height="8" fill="currentColor" />
              <rect x="6" y="2" width="3" height="12" fill="currentColor" />
              <rect x="10" y="8" width="3" height="6" fill="currentColor" />
              <line x1="0" y1="15" x2="16" y2="15" stroke="currentColor" strokeWidth="2" />
            </svg>
          </button>
        </div>
      </div>

      <div className="alignment-toolbar-section">
        <span className="alignment-toolbar-label">分布</span>
        <div className="alignment-toolbar-buttons">
          <button
            className="alignment-btn"
            onClick={() => handleDistribute(DistributionType.HORIZONTAL)}
            disabled={!canDistribute}
            title="水平分布"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <rect x="1" y="6" width="3" height="4" fill="currentColor" />
              <rect x="6.5" y="6" width="3" height="4" fill="currentColor" />
              <rect x="12" y="6" width="3" height="4" fill="currentColor" />
            </svg>
          </button>

          <button
            className="alignment-btn"
            onClick={() => handleDistribute(DistributionType.VERTICAL)}
            disabled={!canDistribute}
            title="垂直分布"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <rect x="6" y="1" width="4" height="3" fill="currentColor" />
              <rect x="6" y="6.5" width="4" height="3" fill="currentColor" />
              <rect x="6" y="12" width="4" height="3" fill="currentColor" />
            </svg>
          </button>
        </div>
      </div>

      <div className="alignment-toolbar-section">
        <span className="alignment-toolbar-label">布局</span>
        <div className="alignment-toolbar-buttons">
          <button
            className="alignment-btn"
            onClick={handleSnapToGrid}
            disabled={selectedNodes.length === 0}
            title="对齐到网格"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <circle cx="3" cy="3" r="1" fill="currentColor" />
              <circle cx="8" cy="3" r="1" fill="currentColor" />
              <circle cx="13" cy="3" r="1" fill="currentColor" />
              <circle cx="3" cy="8" r="1" fill="currentColor" />
              <circle cx="8" cy="8" r="1" fill="currentColor" />
              <circle cx="13" cy="8" r="1" fill="currentColor" />
              <circle cx="3" cy="13" r="1" fill="currentColor" />
              <circle cx="8" cy="13" r="1" fill="currentColor" />
              <circle cx="13" cy="13" r="1" fill="currentColor" />
            </svg>
          </button>

          <button
            className="alignment-btn"
            onClick={onAutoLayout}
            title="自动布局"
          >
            <svg width="16" height="16" viewBox="0 0 16 16">
              <path
                d="M8 2 L12 6 L10 6 L10 10 L12 10 L8 14 L4 10 L6 10 L6 6 L4 6 Z"
                fill="currentColor"
              />
            </svg>
          </button>
        </div>
      </div>

      {selectedNodes.length > 0 && (
        <div className="alignment-toolbar-info">
          已选择 {selectedNodes.length} 个节点
        </div>
      )}
    </div>
  );
};
