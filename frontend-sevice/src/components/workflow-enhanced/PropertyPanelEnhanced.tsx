/**
 * Property Panel Enhanced
 * 增强版属性面板
 */

import React from 'react';
import { Card, Form, Input, InputNumber, Select, Switch, Button, Divider, Empty, Space } from 'antd';
import { DeleteOutlined, SaveOutlined, CloseOutlined } from '@ant-design/icons';
import { useWorkflowEnhancedStore } from '../../stores/workflowEnhancedStore';
import type { EnhancedWorkflowNode } from '../../types/workflow-enhanced';
import './PropertyPanelEnhanced.css';

const { TextArea } = Input;
const { Option } = Select;

interface PropertyPanelEnhancedProps {
  nodeId: string | null;
}

const PropertyPanelEnhanced: React.FC<PropertyPanelEnhancedProps> = ({ nodeId }) => {
  const { nodes, updateNode, deleteNode } = useWorkflowEnhancedStore();
  const [form] = Form.useForm();
  const [hasChanges, setHasChanges] = React.useState(false);

  // 查找选中的节点
  const selectedNode = nodes.find((n) => n.id === nodeId) as EnhancedWorkflowNode | undefined;

  // 使用 ref 跟踪上一次的 nodeId 和原始数据
  const prevNodeIdRef = React.useRef<string | null>(null);
  const originalDataRef = React.useRef<any>(null);

  // 当节点ID改变时，更新表单（避免因节点对象引用变化导致表单重置）
  React.useEffect(() => {
    // 只在 nodeId 真正变化时才重置表单
    if (nodeId !== prevNodeIdRef.current) {
      prevNodeIdRef.current = nodeId;
      setHasChanges(false);
      
      if (selectedNode) {
        const formData = {
          label: selectedNode.data.label,
          description: selectedNode.data.description,
          ...selectedNode.data.config,
        };
        form.setFieldsValue(formData);
        originalDataRef.current = formData;
      }
    }
  }, [nodeId, selectedNode, form]);

  // 处理表单值变化
  const handleValuesChange = () => {
    setHasChanges(true);
  };

  // 保存修改
  const handleSave = () => {
    if (!selectedNode) return;

    const allValues = form.getFieldsValue();
    const { label, description, ...config } = allValues;
    
    updateNode(selectedNode.id, {
      label: label || selectedNode.data.label,
      description: description || selectedNode.data.description,
      config: { ...selectedNode.data.config, ...config },
    });

    // 更新原始数据引用
    originalDataRef.current = allValues;
    setHasChanges(false);
  };

  // 取消修改
  const handleCancel = () => {
    if (originalDataRef.current) {
      form.setFieldsValue(originalDataRef.current);
      setHasChanges(false);
    }
  };

  // 处理删除节点
  const handleDelete = () => {
    if (selectedNode) {
      deleteNode(selectedNode.id);
    }
  };

  // 如果没有选中节点
  if (!selectedNode) {
    return (
      <Card title="节点属性" className="property-panel-enhanced">
        <Empty 
          description="请选择一个节点" 
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          style={{ padding: '40px 0' }}
        />
      </Card>
    );
  }

  // 根据节点类型渲染不同的配置表单
  const renderConfigForm = () => {
    const { type, config } = selectedNode.data;

    switch (type) {
      case 'function':
        return (
          <>
            <Form.Item label="学科" name="subject">
              <Select placeholder="选择学科">
                <Option value="linear-algebra">线性代数</Option>
                <Option value="calculus">微积分</Option>
                <Option value="statistics">统计分析</Option>
              </Select>
            </Form.Item>
            <Form.Item label="操作" name="operation">
              <Input placeholder="操作类型" />
            </Form.Item>
            {config.operation === 'integrate' && (
              <>
                <Form.Item label="下限" name="lowerBound">
                  <InputNumber style={{ width: '100%' }} placeholder="积分下限" />
                </Form.Item>
                <Form.Item label="上限" name="upperBound">
                  <InputNumber style={{ width: '100%' }} placeholder="积分上限" />
                </Form.Item>
              </>
            )}
          </>
        );

      case 'visualization':
        return (
          <>
            <Form.Item label="图表类型" name="chartType">
              <Select placeholder="选择图表类型">
                <Option value="line">折线图</Option>
                <Option value="bar">柱状图</Option>
                <Option value="scatter">散点图</Option>
                <Option value="pie">饼图</Option>
              </Select>
            </Form.Item>
            <Form.Item label="标题" name="chartTitle">
              <Input placeholder="图表标题" />
            </Form.Item>
            <Form.Item label="X轴标签" name="xLabel">
              <Input placeholder="X轴标签" />
            </Form.Item>
            <Form.Item label="Y轴标签" name="yLabel">
              <Input placeholder="Y轴标签" />
            </Form.Item>
            <Form.Item label="显示图例" name="showLegend" valuePropName="checked">
              <Switch />
            </Form.Item>
          </>
        );

      case 'control':
        return (
          <>
            <Form.Item label="条件类型" name="conditionType">
              <Select placeholder="选择条件类型">
                <Option value="boolean">布尔值</Option>
                <Option value="comparison">比较</Option>
                <Option value="expression">表达式</Option>
              </Select>
            </Form.Item>
            {config.conditionType === 'comparison' && (
              <>
                <Form.Item label="比较运算符" name="operator">
                  <Select placeholder="选择运算符">
                    <Option value="==">等于 (==)</Option>
                    <Option value="!=">不等于 (!=)</Option>
                    <Option value=">">大于 (&gt;)</Option>
                    <Option value="<">小于 (&lt;)</Option>
                    <Option value=">=">大于等于 (&gt;=)</Option>
                    <Option value="<=">小于等于 (&lt;=)</Option>
                  </Select>
                </Form.Item>
              </>
            )}
          </>
        );

      case 'llm':
        return (
          <>
            <Form.Item label="模型" name="model">
              <Select placeholder="选择模型">
                <Option value="gpt-3.5-turbo">GPT-3.5 Turbo</Option>
                <Option value="gpt-4">GPT-4</Option>
                <Option value="claude-2">Claude 2</Option>
              </Select>
            </Form.Item>
            <Form.Item label="温度" name="temperature">
              <InputNumber 
                min={0} 
                max={2} 
                step={0.1} 
                style={{ width: '100%' }}
                placeholder="0.7"
              />
            </Form.Item>
            <Form.Item label="最大令牌数" name="maxTokens">
              <InputNumber 
                min={1} 
                max={4000} 
                style={{ width: '100%' }}
                placeholder="1000"
              />
            </Form.Item>
            <Form.Item label="系统提示词" name="systemPrompt">
              <TextArea 
                rows={3} 
                placeholder="系统提示词（可选）"
              />
            </Form.Item>
          </>
        );

      default:
        return (
          <Empty 
            description="该节点类型暂无配置项" 
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        );
    }
  };

  return (
    <Card 
      title="节点属性" 
      className="property-panel-enhanced"
      extra={
        <Button 
          type="text" 
          danger 
          size="small"
          icon={<DeleteOutlined />}
          onClick={handleDelete}
        >
          删除
        </Button>
      }
    >
      <div className="property-panel-content">
        <Form
          form={form}
          layout="vertical"
          onValuesChange={handleValuesChange}
          size="small"
        >
          {/* 基本信息 */}
          <div className="property-section">
            <div className="property-section-title">基本信息</div>
            
            <Form.Item label="节点名称" name="label">
              <Input placeholder="节点名称" />
            </Form.Item>

            <Form.Item label="描述" name="description">
              <TextArea 
                rows={2} 
                placeholder="节点描述（可选）"
              />
            </Form.Item>

            <Form.Item label="节点类型">
              <Input value={selectedNode.data.type} disabled />
            </Form.Item>

            <Form.Item label="节点 ID">
              <Input value={selectedNode.id} disabled />
            </Form.Item>
          </div>

          <Divider />

          {/* 配置项 */}
          <div className="property-section">
            <div className="property-section-title">配置项</div>
            {renderConfigForm()}
          </div>

          <Divider />

          {/* 端口信息 */}
          <div className="property-section">
            <div className="property-section-title">端口信息</div>
            
            <div className="property-ports">
              <div className="property-ports-group">
                <div className="property-ports-label">输入端口 ({selectedNode.data.inputs.length})</div>
                {selectedNode.data.inputs.map((input) => (
                  <div key={input.id} className="property-port-item">
                    <span className="property-port-name">{input.name}</span>
                    <span className="property-port-type">{input.dataType}</span>
                  </div>
                ))}
              </div>

              <div className="property-ports-group">
                <div className="property-ports-label">输出端口 ({selectedNode.data.outputs.length})</div>
                {selectedNode.data.outputs.map((output) => (
                  <div key={output.id} className="property-port-item">
                    <span className="property-port-name">{output.name}</span>
                    <span className="property-port-type">{output.dataType}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Form>
      </div>

      {/* 保存/取消按钮 - 固定在底部 */}
      {hasChanges && (
        <div className="property-actions-footer">
          <Space>
            <Button 
              icon={<CloseOutlined />}
              onClick={handleCancel}
              size="small"
            >
              取消
            </Button>
            <Button 
              type="primary" 
              icon={<SaveOutlined />}
              onClick={handleSave}
              size="small"
            >
              保存
            </Button>
          </Space>
        </div>
      )}
    </Card>
  );
};

export default PropertyPanelEnhanced;
