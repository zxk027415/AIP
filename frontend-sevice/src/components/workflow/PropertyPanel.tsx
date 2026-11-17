import React, { useEffect, useState } from 'react';
import { Card, Form, Input, InputNumber, Switch, Button, Space, Divider, Empty } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import { useWorkflowStore } from '../../stores/workflowStore';
import { useUIStore } from '../../stores/uiStore';
import type { WorkflowNode } from '../../types/workflow';
import './PropertyPanel.css';

const PropertyPanel: React.FC = () => {
  const { currentWorkflow, updateWorkflow, markDirty } = useWorkflowStore();
  const { selectedNodeId, selectNode } = useUIStore();
  const [form] = Form.useForm();
  const [selectedNode, setSelectedNode] = useState<WorkflowNode | null>(null);

  // Find selected node
  useEffect(() => {
    if (selectedNodeId && currentWorkflow) {
      const node = currentWorkflow.nodes.find((n) => n.id === selectedNodeId);
      setSelectedNode(node || null);
      
      if (node) {
        // Set form values
        form.setFieldsValue({
          label: node.data.label,
          ...node.data.parameters,
        });
      }
    } else {
      setSelectedNode(null);
      form.resetFields();
    }
  }, [selectedNodeId, currentWorkflow, form]);

  const handleClose = () => {
    selectNode(null);
  };

  const handleValuesChange = (changedValues: any, allValues: any) => {
    if (!selectedNode || !currentWorkflow) return;

    // Extract label and parameters
    const { label, ...parameters } = allValues;

    // Update node in workflow
    const updatedNodes = currentWorkflow.nodes.map((node) => {
      if (node.id === selectedNodeId) {
        return {
          ...node,
          data: {
            ...node.data,
            label: label || node.data.label,
            parameters,
          },
        };
      }
      return node;
    });

    updateWorkflow({ nodes: updatedNodes });
    markDirty();
  };

  const renderParameterField = (paramName: string, paramValue: any) => {
    const paramType = typeof paramValue;

    if (paramType === 'boolean') {
      return (
        <Form.Item
          key={paramName}
          name={paramName}
          label={paramName}
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      );
    }

    if (paramType === 'number') {
      return (
        <Form.Item
          key={paramName}
          name={paramName}
          label={paramName}
        >
          <InputNumber style={{ width: '100%' }} />
        </Form.Item>
      );
    }

    if (Array.isArray(paramValue)) {
      return (
        <Form.Item
          key={paramName}
          name={paramName}
          label={paramName}
          tooltip="输入JSON数组格式，例如: [1, 2, 3]"
        >
          <Input.TextArea
            rows={3}
            placeholder="[1, 2, 3]"
          />
        </Form.Item>
      );
    }

    // Default to string input
    return (
      <Form.Item
        key={paramName}
        name={paramName}
        label={paramName}
      >
        <Input />
      </Form.Item>
    );
  };

  if (!selectedNode) {
    return (
      <Card
        title="属性面板"
        className="property-panel"
        bordered={false}
      >
        <Empty
          description="请选择一个节点"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </Card>
    );
  }

  return (
    <Card
      title="属性面板"
      className="property-panel"
      bordered={false}
      extra={
        <Button
          type="text"
          icon={<CloseOutlined />}
          onClick={handleClose}
          size="small"
        />
      }
    >
      <Form
        form={form}
        layout="vertical"
        onValuesChange={handleValuesChange}
      >
        {/* Node Label */}
        <Form.Item
          name="label"
          label="节点名称"
        >
          <Input placeholder="输入节点名称" />
        </Form.Item>

        <Divider />

        {/* Node Type Info */}
        <div className="node-info">
          <div className="info-row">
            <span className="info-label">类型:</span>
            <span className="info-value">{selectedNode.type}</span>
          </div>
          {selectedNode.data.functionId && (
            <div className="info-row">
              <span className="info-label">函数ID:</span>
              <span className="info-value">{selectedNode.data.functionId}</span>
            </div>
          )}
        </div>

        <Divider />

        {/* Parameters */}
        <div className="parameters-section">
          <h4>参数</h4>
          {Object.keys(selectedNode.data.parameters).length > 0 ? (
            Object.entries(selectedNode.data.parameters).map(([key, value]) =>
              renderParameterField(key, value)
            )
          ) : (
            <Empty
              description="无参数"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
        </div>

        <Divider />

        {/* Ports Info */}
        <div className="ports-section">
          <h4>输入端口</h4>
          {selectedNode.data.inputs.length > 0 ? (
            <div className="ports-list">
              {selectedNode.data.inputs.map((port) => (
                <div key={port.id} className="port-item">
                  <span className="port-name">
                    {port.name}
                    {port.required && <span className="required">*</span>}
                  </span>
                  <span className="port-type">{port.type}</span>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              description="无输入端口"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              style={{ margin: '8px 0' }}
            />
          )}

          <h4 style={{ marginTop: 16 }}>输出端口</h4>
          {selectedNode.data.outputs.length > 0 ? (
            <div className="ports-list">
              {selectedNode.data.outputs.map((port) => (
                <div key={port.id} className="port-item">
                  <span className="port-name">{port.name}</span>
                  <span className="port-type">{port.type}</span>
                </div>
              ))}
            </div>
          ) : (
            <Empty
              description="无输出端口"
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              style={{ margin: '8px 0' }}
            />
          )}
        </div>
      </Form>
    </Card>
  );
};

export default PropertyPanel;
