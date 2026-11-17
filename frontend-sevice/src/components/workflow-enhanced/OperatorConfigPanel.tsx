// @AI_GENERATED
import React, { useState, useMemo, useEffect, useCallback } from 'react';
import {
  Drawer, Form, Input, InputNumber, Switch, Select, Slider, Tag,
  Button, Collapse, Tooltip, Tabs, Table, Typography, Space, Divider,
  Spin, Alert, message,
} from 'antd';
import { QuestionCircleOutlined, UndoOutlined, CodeOutlined, CopyOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { FunctionDefinition, ParameterDefinition } from '../../types/function';
import type { NodeExecutionResult } from '../../types/pipeline';
import { HUMANIZED_PARAMS, OPERATOR_DESCRIPTIONS, getOperatorDescription } from './operatorParamConfig';
import { td } from '../../utils/dataTranslation';
import TrainableDatasetPicker from './TrainableDatasetPicker';
import OperatorCodeBlock from '../OperatorCodeBlock';
import api from '../../services/api';

const { Text, Paragraph } = Typography;

interface OperatorSourceInfo {
  operator_id: string;
  source_code: string;
  key_snippet: string;
  file_path: string;
  available: boolean;
}

interface OperatorConfigPanelProps {
  node: any;
  functionDef: FunctionDefinition | null;
  executionResult?: NodeExecutionResult;
  onSave: (config: Record<string, any>) => void;
  onClose: () => void;
  visible: boolean;
  /** PV slot 工作流：load_csv 可展示可训数据下拉 */
  workflowSlot?: string;
}

const OperatorConfigPanel: React.FC<OperatorConfigPanelProps> = ({
  node, functionDef, executionResult, onSave, onClose, visible, workflowSlot,
}) => {
  const [form] = Form.useForm();
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('config');
  const [sourceInfo, setSourceInfo] = useState<OperatorSourceInfo | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [showFullSource, setShowFullSource] = useState(false);

  const operatorId = node?.data?.config?.functionId || '';
  const humanized = HUMANIZED_PARAMS[operatorId] || {};

  const hasTrainableFilePath = useMemo(
    () => Object.values(humanized).some((h) => h.controlType === 'trainable_file_path'),
    [humanized],
  );

  const { basicParams, advancedParams } = useMemo(() => {
    if (!functionDef) return { basicParams: [], advancedParams: [] };
    const basic: ParameterDefinition[] = [];
    const advanced: ParameterDefinition[] = [];
    const hasHumanizedConfig = Object.keys(humanized).length > 0;
    const HIDDEN_PARAMS = new Set(['data', 'options', 'source', 'train_data', 'model']);
    for (const p of functionDef.parameters) {
      if (HIDDEN_PARAMS.has(p.name)) continue;
      const h = humanized[p.name];
      if (h?.controlType === 'trainable_file_path') continue;
      if (h?.group === 'advanced') {
        advanced.push(p);
      } else if (h?.group === 'basic') {
        basic.push(p);
      } else if (hasHumanizedConfig) {
        advanced.push(p);
      } else {
        basic.push(p);
      }
    }
    return { basicParams: basic, advancedParams: advanced };
  }, [functionDef, humanized]);

  useEffect(() => {
    if (!visible || !node) return;
    const config = node.data?.config || {};
    const values: Record<string, any> = {};
    if (functionDef) {
      for (const p of functionDef.parameters) {
        values[p.name] = config[p.name] ?? humanized[p.name]?.defaultValue ?? p.defaultValue;
      }
    }
    if (config.dataset_id) values.dataset_id = config.dataset_id;
    form.setFieldsValue(values);
    setActiveTab('config');
    setShowFullSource(false);
  }, [visible, node?.id, functionDef, form, humanized, node]);

  const fetchSource = useCallback(async (id: string) => {
    setSourceLoading(true);
    setSourceError(null);
    try {
      const src = await (api as any).get(`/functions/${id}/source`) as OperatorSourceInfo;
      setSourceInfo(src);
    } catch (e: any) {
      setSourceError(e?.message || '获取源码失败');
      setSourceInfo(null);
    } finally {
      setSourceLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!visible || !operatorId) {
      setSourceInfo(null);
      setSourceError(null);
      return;
    }
    if (activeTab === 'source') {
      fetchSource(operatorId);
    }
  }, [visible, operatorId, activeTab, fetchSource]);

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
    if (typeName === 'ARRAY' || controlType === 'tags') {
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

  const copyCode = (code: string) => {
    navigator.clipboard.writeText(code).then(
      () => message.success('已复制到剪贴板'),
      () => message.error('复制失败'),
    );
  };

  const renderSourceTab = () => {
    if (sourceLoading) {
      return (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin tip="加载源码..." />
        </div>
      );
    }
    if (sourceError) {
      return <Alert type="error" message={sourceError} showIcon />;
    }
    if (!sourceInfo?.available) {
      return (
        <Alert
          type="warning"
          showIcon
          message="暂无后端实现"
          description={sourceInfo?.file_path ? `预期路径：${sourceInfo.file_path}` : '该算子尚未提供 Python 实现文件'}
        />
      );
    }
    const displayCode = showFullSource ? sourceInfo.source_code : sourceInfo.key_snippet;
    return (
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space wrap>
          <Tag color="success">已实现</Tag>
          <Text type="secondary" style={{ fontSize: 12 }}>{sourceInfo.file_path}</Text>
        </Space>
        <Space>
          <Button
            size="small"
            type={showFullSource ? 'default' : 'primary'}
            onClick={() => setShowFullSource(false)}
          >
            execute 片段
          </Button>
          <Button
            size="small"
            type={showFullSource ? 'primary' : 'default'}
            onClick={() => setShowFullSource(true)}
          >
            完整源码
          </Button>
          <Button
            size="small"
            icon={<CopyOutlined />}
            onClick={() => copyCode(displayCode)}
          >
            复制
          </Button>
        </Space>
        <OperatorCodeBlock code={displayCode} maxHeight={520} />
      </Space>
    );
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
          {hasTrainableFilePath && (
            <TrainableDatasetPicker workflowSlot={workflowSlot} form={form} />
          )}
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
      key: 'source',
      label: (
        <Space size={4}>
          <CodeOutlined />
          {t('operator.sourceCode')}
        </Space>
      ),
      children: renderSourceTab(),
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
      width={420}
      open={visible}
      onClose={onClose}
      destroyOnClose
    >
      {operatorDesc && (
        <Paragraph type="secondary" style={{ fontSize: 13, marginBottom: 16, padding: '8px 12px', background: '#f6f8fa', borderRadius: 6 }}>
          {td(operatorDesc)}
        </Paragraph>
      )}
      <Tabs items={tabItems} activeKey={activeTab} onChange={setActiveTab} />
    </Drawer>
  );
};

export default OperatorConfigPanel;
// @AI_GENERATED: end
