// @AI_GENERATED
import React, { useState, useMemo } from 'react';
import {
  Drawer, Form, Input, InputNumber, Switch, Select, Slider, Tag,
  Button, Collapse, Tooltip, Tabs, Table, Typography, Space, Divider,
} from 'antd';
import { QuestionCircleOutlined, UndoOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { FunctionDefinition, ParameterDefinition } from '../../types/function';
import type { NodeExecutionResult } from '../../types/pipeline';
import { HUMANIZED_PARAMS, OPERATOR_DESCRIPTIONS, getOperatorDescription } from './operatorParamConfig';
import { td } from '../../utils/dataTranslation';

const { Text, Paragraph } = Typography;

interface OperatorConfigPanelProps {
  node: any;
  functionDef: FunctionDefinition | null;
  executionResult?: NodeExecutionResult;
  onSave: (config: Record<string, any>) => void;
  onClose: () => void;
  visible: boolean;
}

const OperatorConfigPanel: React.FC<OperatorConfigPanelProps> = ({
  node, functionDef, executionResult, onSave, onClose, visible,
}) => {
  const [form] = Form.useForm();
  const [tagInput, setTagInput] = useState('');
  const { t } = useTranslation();

  const operatorId = node?.data?.config?.functionId || '';
  const humanized = HUMANIZED_PARAMS[operatorId] || {};

  const { basicParams, advancedParams } = useMemo(() => {
    if (!functionDef) return { basicParams: [], advancedParams: [] };
    const basic: ParameterDefinition[] = [];
    const advanced: ParameterDefinition[] = [];
    const hasHumanizedConfig = Object.keys(humanized).length > 0;
    // @AI_GENERATED
    // 隐藏通用的内部参数（data, options 等），这些不应该暴露给用户
    const HIDDEN_PARAMS = new Set(['data', 'options', 'source', 'train_data', 'model']);
    // @AI_GENERATED: end
    for (const p of functionDef.parameters) {
      // @AI_GENERATED
      // 如果参数在隐藏列表中，跳过不显示
      if (HIDDEN_PARAMS.has(p.name)) continue;
      // @AI_GENERATED: end
      const h = humanized[p.name];
      if (h?.group === 'advanced') {
        advanced.push(p);
      } else if (h?.group === 'basic') {
        basic.push(p);
      } else if (hasHumanizedConfig) {
        // @AI_GENERATED
        // 有人性化配置但该参数未定义 → 放到高级参数（避免显示看不懂的原始参数）
        advanced.push(p);
        // @AI_GENERATED: end
      } else {
        basic.push(p);
      }
    }
    return { basicParams: basic, advancedParams: advanced };
  }, [functionDef, humanized]);

  const getLabel = (p: ParameterDefinition) => {
    const h = humanized[p.name];
    return td(h?.label || p.name);
  };

  const getDescription = (p: ParameterDefinition) => {
    const h = humanized[p.name];
    return td(h?.description || p.description || '');
  };

  const getDefault = (p: ParameterDefinition) => {
    const h = humanized[p.name];
    return h?.defaultValue ?? p.defaultValue;
  };

  const renderField = (p: ParameterDefinition) => {
    const h = humanized[p.name];
    const controlType = h?.controlType;
    const typeName = (p.type as string).toUpperCase();

    if (controlType === 'select' || typeName === 'SELECT') {
      const opts = h?.options || [];
      return (
        <Select
          options={opts.map((o: any) => ({ label: td(o.label), value: o.value }))}
          allowClear
        />
      );
    }
    if (typeName === 'BOOLEAN') {
      return <Switch />;
    }
    if (typeName === 'NUMBER') {
      const min = h?.min ?? p.constraints?.[0]?.range?.[0];
      const max = h?.max ?? p.constraints?.[0]?.range?.[1];
      if (controlType === 'slider') {
        return <Slider min={min} max={max} step={h?.step || 1} />;
      }
      return <InputNumber min={min} max={max} step={h?.step} style={{ width: '100%' }} />;
    }
    if (typeName === 'ARRAY') {
      return (
        <Select mode="tags" tokenSeparators={[',']} placeholder={t('operator.enterToAdd')} />
      );
    }
    return <Input placeholder={getDescription(p)} />;
  };

  const renderParamGroup = (params: ParameterDefinition[]) =>
    params.map((p) => (
      <Form.Item
        key={p.name}
        name={p.name}
        label={
          <Space size={4}>
            {getLabel(p)}
            {getDescription(p) && (
              <Tooltip title={getDescription(p)}>
                <QuestionCircleOutlined style={{ color: '#999' }} />
              </Tooltip>
            )}
          </Space>
        }
        rules={p.required ? [{ required: true, message: t('operator.required', { name: getLabel(p) }) }] : []}
        valuePropName={(p.type as string).toUpperCase() === 'BOOLEAN' ? 'checked' : 'value'}
        initialValue={node?.data?.config?.[p.name] ?? getDefault(p)}
      >
        {renderField(p)}
      </Form.Item>
    ));

  const handleSave = () => {
    form.validateFields().then((values) => {
      onSave(values);
    });
  };

  const handleReset = () => {
    if (!functionDef) return;
    const defaults: Record<string, any> = {};
    for (const p of functionDef.parameters) {
      defaults[p.name] = getDefault(p);
    }
    form.setFieldsValue(defaults);
  };

  const renderResultPreview = () => {
    if (!executionResult || executionResult.status !== 'success') {
      return <Text type="secondary">{t('operator.noResult')}</Text>;
    }
    const { outputSummary } = executionResult;
    if (outputSummary.dataType === 'MATRIX' && outputSummary.preview) {
      const cols = (outputSummary.columnNames || []).map((c) => ({
        title: c, dataIndex: c, key: c, ellipsis: true,
      }));
      return <Table columns={cols} dataSource={outputSummary.preview.slice(0, 10)} size="small" pagination={false} scroll={{ x: true }} rowKey={(_, i) => String(i)} />;
    }
    if (outputSummary.dataType === 'ARRAY') {
      return <Text code>{JSON.stringify((executionResult.output || []).slice(0, 20))}</Text>;
    }
    if (outputSummary.dataType === 'NUMBER') {
      return <Text strong style={{ fontSize: 24 }}>{outputSummary.value}</Text>;
    }
    return <Text code>{JSON.stringify(executionResult.output, null, 2).slice(0, 500)}</Text>;
  };

  const tabItems = [
    {
      key: 'config',
      label: t('operator.paramConfig'),
      children: (
        <Form form={form} layout="vertical" size="small">
          {/* 基本信息区域 */}
          <div style={{ marginBottom: 12, padding: '8px 12px', background: '#fafafa', borderRadius: 6, border: '1px solid #f0f0f0' }}>
            <Space direction="vertical" size={2} style={{ width: '100%' }}>
              <Space>
                <Text type="secondary" style={{ fontSize: 12 }}>{t('operator.operatorId')}</Text>
                <Text code style={{ fontSize: 12 }}>{operatorId}</Text>
              </Space>
              {functionDef?.category && (
                <Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>{t('operator.category')}</Text>
                  <Text style={{ fontSize: 12 }}>{functionDef.category}</Text>
                </Space>
              )}
            </Space>
          </div>
          {renderParamGroup(basicParams)}
          {advancedParams.length > 0 && (
            <Collapse
              ghost
              items={[{
                key: 'advanced',
                label: <Text type="secondary">{t('operator.advancedParams')}</Text>,
                children: renderParamGroup(advancedParams),
              }]}
            />
          )}
          <Divider />
          <Space>
            <Button type="primary" onClick={handleSave}>{t('operator.save')}</Button>
            <Button icon={<UndoOutlined />} onClick={handleReset}>{t('operator.resetDefault')}</Button>
          </Space>
        </Form>
      ),
    },
    {
      key: 'result',
      label: t('operator.executionResult'),
      children: renderResultPreview(),
    },
  ];

  const operatorDesc = getOperatorDescription(operatorId) || functionDef?.description || '';

  return (
    <Drawer
      title={functionDef?.name || node?.data?.label ? td(String(functionDef?.name || node?.data?.label)) : t('operator.config')}
      placement="right"
      width={400}
      open={visible}
      onClose={onClose}
      destroyOnClose
    >
      {operatorDesc && (
        <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 16, padding: '8px 12px', background: '#f6f8fa', borderRadius: 6 }}>
          {td(operatorDesc)}
        </Paragraph>
      )}
      <Tabs items={tabItems} defaultActiveKey="config" />
    </Drawer>
  );
};

export default OperatorConfigPanel;
// @AI_GENERATED: end
