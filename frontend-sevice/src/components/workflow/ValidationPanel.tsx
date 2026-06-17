import React, { useState, useEffect } from 'react';
import { Card, List, Tag, Button, Empty, Alert } from 'antd';
import {
  WarningOutlined,
  CloseCircleOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { useWorkflowStore } from '../../stores/workflowStore';
import { useUIStore } from '../../stores/uiStore';
import axios from 'axios';
import './ValidationPanel.css';

interface ValidationError {
  type: string;
  message: string;
  severity: 'error' | 'warning';
  nodeId?: string;
  edgeId?: string;
  port?: string;
  suggestion?: string;
}

const ValidationPanel: React.FC = () => {
  const { currentWorkflow } = useWorkflowStore();
  const { selectNode } = useUIStore();
  const [validationResults, setValidationResults] = useState<ValidationError[]>([]);
  const [isValidating, setIsValidating] = useState(false);
  const [isValid, setIsValid] = useState<boolean | null>(null);

  const validateWorkflow = async () => {
    if (!currentWorkflow?.id) {
      return;
    }

    setIsValidating(true);

    try {
      const token = localStorage.getItem('token');
      const config = {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      };

      const response = await axios.post(
        `/api/workflows/${currentWorkflow.id}/validate`,
        {},
        config
      );

      const { isValid: valid, errors = [], warnings = [] } = response.data;
      const allIssues = [...errors, ...warnings];

      setIsValid(valid);
      setValidationResults(allIssues);
    } catch (error: any) {
      console.error('Validation failed:', error);
      setIsValid(false);
      setValidationResults([
        {
          type: 'error',
          message: error.response?.data?.detail || '验证失败',
          severity: 'error',
        },
      ]);
    } finally {
      setIsValidating(false);
    }
  };

  // Auto-validate when workflow changes
  useEffect(() => {
    if (currentWorkflow) {
      validateWorkflow();
    }
  }, [currentWorkflow?.nodes, currentWorkflow?.edges]);

  const handleItemClick = (item: ValidationError) => {
    if (item.nodeId) {
      selectNode(item.nodeId);
    }
  };

  const getSeverityIcon = (severity: string) => {
    if (severity === 'error') {
      return <CloseCircleOutlined style={{ color: '#ef4444' }} />;
    }
    return <WarningOutlined style={{ color: '#f59e0b' }} />;
  };

  const getSeverityTag = (severity: string) => {
    if (severity === 'error') {
      return <Tag color="error">错误</Tag>;
    }
    return <Tag color="warning">警告</Tag>;
  };

  const errorCount = validationResults.filter((r) => r.severity === 'error').length;
  const warningCount = validationResults.filter((r) => r.severity === 'warning').length;

  return (
    <Card
      title="验证面板"
      className="validation-panel"
      bordered={false}
      extra={
        <Button
          icon={<ReloadOutlined />}
          onClick={validateWorkflow}
          loading={isValidating}
          size="small"
        >
          重新验证
        </Button>
      }
    >
      {/* Validation Summary */}
      {isValid !== null && (
        <div className="validation-summary">
          {isValid ? (
            <Alert
              message="验证通过"
              description="算法模板没有错误，可以执行"
              type="success"
              icon={<CheckCircleOutlined />}
              showIcon
            />
          ) : (
            <Alert
              message="验证失败"
              description={`发现 ${errorCount} 个错误和 ${warningCount} 个警告`}
              type="error"
              icon={<CloseCircleOutlined />}
              showIcon
            />
          )}
        </div>
      )}

      {/* Validation Results */}
      {validationResults.length > 0 ? (
        <List
          className="validation-list"
          dataSource={validationResults}
          renderItem={(item) => (
            <List.Item
              className={`validation-item ${item.nodeId ? 'clickable' : ''}`}
              onClick={() => handleItemClick(item)}
            >
              <div className="validation-item-content">
                <div className="validation-header">
                  {getSeverityIcon(item.severity)}
                  <span className="validation-type">{item.type}</span>
                  {getSeverityTag(item.severity)}
                </div>
                <div className="validation-message">{item.message}</div>
                {item.nodeId && (
                  <div className="validation-location">
                    节点: {item.nodeId}
                    {item.port && ` | 端口: ${item.port}`}
                  </div>
                )}
                {item.suggestion && (
                  <div className="validation-suggestion">
                    💡 建议: {item.suggestion}
                  </div>
                )}
              </div>
            </List.Item>
          )}
        />
      ) : (
        !isValidating && (
          <Empty
            description={isValid === null ? '点击验证按钮开始验证' : '没有发现问题'}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        )
      )}
    </Card>
  );
};

export default ValidationPanel;
