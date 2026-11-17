import React from 'react';
import { Card, List, Tag, Progress, Empty, Descriptions, Collapse } from 'antd';
import {
  ClockCircleOutlined,
  LoadingOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from '@ant-design/icons';
import { useExecutionStore } from '../../stores/executionStore';
import { useUIStore } from '../../stores/uiStore';
import type { NodeResult, WorkflowExecutionStatus } from '../../types/workflow';
import './ExecutionPanel.css';

const { Panel } = Collapse;

const ExecutionPanel: React.FC = () => {
  const { currentExecution, isExecuting } = useExecutionStore();
  const { selectNode } = useUIStore();

  const getStatusIcon = (status: WorkflowExecutionStatus) => {
    switch (status) {
      case 'pending':
        return <ClockCircleOutlined style={{ color: '#9ca3af' }} />;
      case 'running':
        return <LoadingOutlined style={{ color: '#3b82f6' }} />;
      case 'completed':
        return <CheckCircleOutlined style={{ color: '#10b981' }} />;
      case 'failed':
        return <CloseCircleOutlined style={{ color: '#ef4444' }} />;
      default:
        return null;
    }
  };

  const getStatusTag = (status: WorkflowExecutionStatus) => {
    const tagMap = {
      pending: { color: 'default', text: '等待中' },
      running: { color: 'processing', text: '运行中' },
      completed: { color: 'success', text: '已完成' },
      failed: { color: 'error', text: '失败' },
    };
    const config = tagMap[status] || tagMap.pending;
    return <Tag color={config.color}>{config.text}</Tag>;
  };

  const calculateProgress = () => {
    if (!currentExecution) return 0;
    
    const nodeResults = Object.values(currentExecution.nodeResults);
    if (nodeResults.length === 0) return 0;

    const completedCount = nodeResults.filter(
      (r) => r.status === 'completed' || r.status === 'failed'
    ).length;

    return Math.round((completedCount / nodeResults.length) * 100);
  };

  const formatExecutionTime = (ms: number) => {
    if (ms < 1000) {
      return `${ms.toFixed(0)}ms`;
    }
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const handleNodeClick = (nodeId: string) => {
    selectNode(nodeId);
  };

  const renderNodeResult = (nodeId: string, result: NodeResult) => {
    return (
      <List.Item
        key={nodeId}
        className="execution-node-item"
        onClick={() => handleNodeClick(nodeId)}
      >
        <div className="node-result-content">
          <div className="node-result-header">
            {getStatusIcon(result.status)}
            <span className="node-id">{nodeId}</span>
            {getStatusTag(result.status)}
          </div>

          {result.executionTime > 0 && (
            <div className="node-execution-time">
              执行时间: {formatExecutionTime(result.executionTime * 1000)}
            </div>
          )}

          {result.error && (
            <div className="node-error">
              <CloseCircleOutlined /> {result.error}
            </div>
          )}

          {result.output && result.status === 'completed' && (
            <Collapse ghost>
              <Panel header="查看输出" key="output">
                <pre className="node-output">
                  {JSON.stringify(result.output, null, 2)}
                </pre>
              </Panel>
            </Collapse>
          )}
        </div>
      </List.Item>
    );
  };

  if (!currentExecution && !isExecuting) {
    return (
      <Card
        title="执行面板"
        className="execution-panel"
        bordered={false}
      >
        <Empty
          description="尚未执行模板"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    );
  }

  return (
    <Card
      title="执行面板"
      className="execution-panel"
      bordered={false}
    >
      {/* Execution Summary */}
      {currentExecution && (
        <div className="execution-summary">
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="状态">
              {getStatusTag(currentExecution.status)}
            </Descriptions.Item>
            <Descriptions.Item label="开始时间">
              {new Date(currentExecution.startTime).toLocaleString()}
            </Descriptions.Item>
            {currentExecution.endTime && (
              <Descriptions.Item label="结束时间">
                {new Date(currentExecution.endTime).toLocaleString()}
              </Descriptions.Item>
            )}
            {currentExecution.error && (
              <Descriptions.Item label="错误">
                <span style={{ color: '#ef4444' }}>{currentExecution.error}</span>
              </Descriptions.Item>
            )}
          </Descriptions>

          {/* Progress Bar */}
          <div className="execution-progress">
            <Progress
              percent={calculateProgress()}
              status={
                currentExecution.status === 'failed'
                  ? 'exception'
                  : currentExecution.status === 'completed'
                  ? 'success'
                  : 'active'
              }
            />
          </div>
        </div>
      )}

      {/* Node Results */}
      {currentExecution && Object.keys(currentExecution.nodeResults).length > 0 && (
        <div className="node-results-section">
          <h4>节点执行结果</h4>
          <List
            className="node-results-list"
            dataSource={Object.entries(currentExecution.nodeResults)}
            renderItem={([nodeId, result]) => renderNodeResult(nodeId, result)}
          />
        </div>
      )}

      {/* Loading State */}
      {isExecuting && !currentExecution && (
        <div className="execution-loading">
          <LoadingOutlined style={{ fontSize: 24 }} />
          <p>正在执行模板...</p>
        </div>
      )}
    </Card>
  );
};

export default ExecutionPanel;
