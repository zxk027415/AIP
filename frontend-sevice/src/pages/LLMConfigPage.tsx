// @AI_GENERATED: Kiro v1.0
/**
 * LLM API 配置页面
 * 管理大模型 API 服务接入配置
 */
import React, { useState, useEffect } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card,
  Table,
  Button,
  Modal,
  Form,
  Input,
  Select,
  Switch,
  InputNumber,
  Space,
  Tag,
  message,
  Popconfirm,
  Descriptions,
  Spin,
  Alert,
  Typography,
  Divider,
  Row,
  Col,
} from 'antd';
import ReactMarkdown from 'react-markdown';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  StarOutlined,
  StarFilled,
} from '@ant-design/icons';
import type { LLMConfig, LLMProviderInfo, LLMTestResponse } from '../types/llm-config';
import { llmConfigApi } from '../services/llmConfigApi';

const { Text } = Typography;
const { TextArea } = Input;

const LLMConfigPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [configs, setConfigs] = useState<LLMConfig[]>([]);
  const [providers, setProviders] = useState<LLMProviderInfo[]>([]);
  const [, setDefaultConfigId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [editingConfig, setEditingConfig] = useState<LLMConfig | null>(null);
  const [testModalVisible, setTestModalVisible] = useState(false);
  const [testingConfig, setTestingConfig] = useState<LLMConfig | null>(null);
  const [testResult, setTestResult] = useState<LLMTestResponse | null>(null);
  const [testLoading, setTestLoading] = useState(false);
  const [form] = Form.useForm();
  const [testForm] = Form.useForm();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [providersData, configsData] = await Promise.all([
        llmConfigApi.getProviders(),
        llmConfigApi.getConfigs(),
      ]);
      setProviders(providersData);
      setConfigs(configsData.configs);
      setDefaultConfigId(configsData.default_config_id);
    } catch (error) {
      message.error(t('llmConfig.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleAdd = () => {
    setEditingConfig(null);
    form.resetFields();
    form.setFieldsValue({
      completion_mode: 'chat',
      context_length: 64000,
      max_tokens: 64000,
      temperature: 0.7,
      is_enabled: true,
      is_default: false,
    });
    setModalVisible(true);
  };

  const handleEdit = (record: LLMConfig) => {
    setEditingConfig(record);
    form.setFieldsValue({
      credential_name: record.credentialName,
      display_name: record.displayName,
      provider: record.provider,
      api_key: '', // 不回显 API Key
      api_base: record.apiBase,
      model: record.model,
      completion_mode: record.completionMode,
      context_length: record.contextLength,
      max_tokens: record.maxTokens,
      temperature: record.temperature,
      is_default: record.isDefault,
      is_enabled: record.isEnabled,
    });
    setModalVisible(true);
  };

  const handleDelete = async (id: string) => {
    try {
      await llmConfigApi.deleteConfig(id);
      message.success(t('llmConfig.deleteSuccess'));
      loadData();
    } catch (error) {
      message.error(t('llmConfig.deleteFailed'));
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      
      // 确保 model 是字符串
      const modelValue = Array.isArray(values.model) ? values.model[0] : values.model;
      
      if (editingConfig) {
        const updateData = {
          credential_name: values.credential_name,
          display_name: values.display_name,
          provider: values.provider,
          api_base: values.api_base,
          model: modelValue,
          completion_mode: values.completion_mode,
          context_length: values.context_length,
          max_tokens: values.max_tokens,
          temperature: values.temperature,
          is_default: values.is_default,
          is_enabled: values.is_enabled,
        } as any;
        if (values.api_key) {
          updateData.api_key = values.api_key;
        }
        await llmConfigApi.updateConfig(editingConfig.id, updateData);
        message.success(t('llmConfig.updateSuccess'));
      } else {
        const createData = {
          credential_name: values.credential_name,
          display_name: values.display_name,
          provider: values.provider,
          api_key: values.api_key,
          api_base: values.api_base,
          model: modelValue,
          completion_mode: values.completion_mode,
          context_length: values.context_length,
          max_tokens: values.max_tokens,
          temperature: values.temperature,
          is_default: values.is_default || false,
          is_enabled: values.is_enabled !== false,
        };
        await llmConfigApi.createConfig(createData);
        message.success(t('llmConfig.createSuccess'));
      }
      
      setModalVisible(false);
      loadData();
    } catch (error) {
      console.error('Submit error:', error);
      message.error(t('llmConfig.submitFailed'));
    }
  };

  const handleTest = (record: LLMConfig) => {
    setTestingConfig(record);
    setTestResult(null);
    testForm.setFieldsValue({
      prompt: t('llmConfig.testDefaultPrompt'),
    });
    setTestModalVisible(true);
  };

  const runTest = async () => {
    if (!testingConfig) return;
    
    setTestLoading(true);
    setTestResult(null);
    try {
      const prompt = testForm.getFieldValue('prompt');
      const result = await llmConfigApi.testConfig({
        config_id: testingConfig.id,
        prompt,
      });
      setTestResult(result);
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      const errorMsg = axiosError?.response?.data?.detail || t('llmConfig.testRequestFailed');
      setTestResult({
        success: false,
        latencyMs: 0,
        error: errorMsg,
        model: testingConfig.model,
      });
    } finally {
      setTestLoading(false);
    }
  };

  const handleSetDefault = async (record: LLMConfig) => {
    try {
      await llmConfigApi.updateConfig(record.id, { is_default: true });
      message.success(t('llmConfig.setDefaultSuccess'));
      loadData();
    } catch (error) {
      message.error(t('llmConfig.setDefaultFailed'));
    }
  };

  const selectedProvider = Form.useWatch('provider', form);
  const providerInfo = providers.find(p => p.id === selectedProvider);

  const columns = [
    {
      title: t('llmConfig.credentialName'),
      dataIndex: 'credentialName',
      key: 'credentialName',
      render: (text: string, record: LLMConfig) => (
        <Space>
          {text}
          {record.isDefault && <Tag color="gold"><StarFilled /> {t('llmConfig.default')}</Tag>}
        </Space>
      ),
    },
    {
      title: t('llmConfig.displayName'),
      dataIndex: 'displayName',
      key: 'displayName',
      render: (text: string) => <Tag color="blue">{text}</Tag>,
    },
    {
      title: t('llmConfig.provider'),
      dataIndex: 'provider',
      key: 'provider',
      render: (provider: string) => {
        const info = providers.find(p => p.id === provider);
        return info?.name || provider;
      },
    },
    {
      title: t('llmConfig.apiKey'),
      dataIndex: 'apiKey',
      key: 'apiKey',
      render: (key: string) => <Text type="secondary">{key}</Text>,
    },
    {
      title: t('llmConfig.mode'),
      dataIndex: 'completionMode',
      key: 'completionMode',
      render: (mode: string) => (
        <Tag color={mode === 'chat' ? 'green' : 'orange'}>
          {mode === 'chat' ? t('llmConfig.modeChat') : t('llmConfig.modeCompletion')}
        </Tag>
      ),
    },
    {
      title: t('llmConfig.statusCol'),
      dataIndex: 'isEnabled',
      key: 'isEnabled',
      render: (enabled: boolean) => (
        enabled ? (
          <Tag color="success" icon={<CheckCircleOutlined />}>{t('llmConfig.enabled')}</Tag>
        ) : (
          <Tag color="default" icon={<CloseCircleOutlined />}>{t('llmConfig.disabled')}</Tag>
        )
      ),
    },
    {
      title: t('llmConfig.actions'),
      key: 'actions',
      render: (_: unknown, record: LLMConfig) => (
        <Space>
          <Button
            type="link"
            icon={<ThunderboltOutlined />}
            onClick={() => handleTest(record)}
          >
            {t('llmConfig.testBtn')}
          </Button>
          {!record.isDefault && (
            <Button
              type="link"
              icon={<StarOutlined />}
              onClick={() => handleSetDefault(record)}
            >
              {t('llmConfig.setDefault')}
            </Button>
          )}
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            {t('llmConfig.editBtn')}
          </Button>
          <Popconfirm
            title={t('llmConfig.confirmDeleteConfig')}
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              {t('llmConfig.deleteBtn')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Card
        title={
          <Space>
            <ApiOutlined />
            {t('llmConfig.title')}
          </Space>
        }
        extra={
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            {t('llmConfig.addConfig')}
          </Button>
        }
      >
        <Alert
          message={t('llmConfig.configDesc')}
          description={t('llmConfig.configDescDetail')}
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
        
        <Table
          columns={columns}
          dataSource={configs}
          rowKey="id"
          loading={loading}
          pagination={false}
        />
      </Card>

      {/* 添加/编辑配置弹窗 */}
      <Modal
        title={editingConfig ? t('llmConfig.editTitle') : t('llmConfig.addTitle')}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={700}
        okText={t('llmConfig.save')}
        cancelText={t('llmConfig.cancel')}
      >
        <Form form={form} layout="vertical">
          <Divider orientation="left" plain>{t('llmConfig.basicInfo')}</Divider>
          
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                name="credential_name"
                label={t('llmConfig.credentialNameLabel')}
                rules={[{ required: true, message: t('llmConfig.credentialNameRequired') }]}
                tooltip={t('llmConfig.credentialTooltip')}
              >
                <Input placeholder={t('llmConfig.credentialNamePlaceholder')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                name="display_name"
                label={t('llmConfig.displayNameLabel')}
                rules={[{ required: true, message: t('llmConfig.displayNameRequired') }]}
                tooltip={t('llmConfig.displayNameTooltip')}
              >
                <Input placeholder={t('llmConfig.displayNamePlaceholder')} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="provider"
            label={t('llmConfig.providerLabel')}
            rules={[{ required: true, message: t('llmConfig.providerRequired') }]}
          >
            <Select placeholder={t('llmConfig.providerPlaceholder')}>
              {providers.map(p => (
                <Select.Option key={p.id} value={p.id}>
                  {p.name} - {p.description}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          <Divider orientation="left" plain>{t('llmConfig.apiConfig')}</Divider>

          <Form.Item
            name="api_key"
            label={t('llmConfig.apiKeyLabel')}
            rules={[{ required: !editingConfig, message: t('llmConfig.apiKeyRequired') }]}
            extra={editingConfig ? t('llmConfig.apiKeyKeep') : undefined}
          >
            <Input.Password placeholder={t('llmConfig.apiKeyPlaceholder')} />
          </Form.Item>

          <Form.Item
            name="api_base"
            label={t('llmConfig.apiBaseLabel')}
            rules={[{ required: true, message: t('llmConfig.apiBaseRequired') }]}
            extra={providerInfo?.defaultApiBase ? t('llmConfig.apiBaseDefault', { url: providerInfo.defaultApiBase }) : t('llmConfig.apiBaseCustom')}
          >
            <Input placeholder={providerInfo?.defaultApiBase || 'http://10.65.105.21:3000/v1'} />
          </Form.Item>

          <Form.Item
            name="model"
            label={t('llmConfig.modelLabel')}
            rules={[{ required: true, message: t('llmConfig.modelRequired') }]}
            tooltip={t('llmConfig.modelTooltip')}
          >
            <Select 
              placeholder={t('llmConfig.modelPlaceholder')} 
              showSearch 
              allowClear
              mode="tags"
              maxCount={1}
              options={providerInfo?.models?.map(m => ({ label: m, value: m })) || []}
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>

          <Divider orientation="left" plain>{t('llmConfig.modelParams')}</Divider>

          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                name="completion_mode"
                label="Completion mode"
                rules={[{ required: true }]}
              >
                <Select>
                  <Select.Option value="chat">{t('llmConfig.modeChat')}</Select.Option>
                  <Select.Option value="completion">{t('llmConfig.modeCompletion')}</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="context_length"
                label={t('llmConfig.contextLength')}
                rules={[{ required: true, message: t('llmConfig.contextLengthRequired') }]}
              >
                <InputNumber 
                  min={1000} 
                  max={200000} 
                  style={{ width: '100%' }} 
                  formatter={value => `${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="max_tokens"
                label={t('llmConfig.maxTokens')}
                rules={[{ required: true, message: t('llmConfig.maxTokensRequired') }]}
              >
                <InputNumber 
                  min={100} 
                  max={200000} 
                  style={{ width: '100%' }}
                  formatter={value => `${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item
            name="temperature"
            label="Temperature"
            tooltip={t('llmConfig.temperatureTooltip')}
          >
            <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
          </Form.Item>

          <Divider orientation="left" plain>{t('llmConfig.statusSettings')}</Divider>

          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="is_enabled" label={t('llmConfig.enableConfig')} valuePropName="checked">
                <Switch checkedChildren={t('llmConfig.enableSwitch')} unCheckedChildren={t('llmConfig.disableSwitch')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="is_default" label={t('llmConfig.setAsDefault')} valuePropName="checked">
                <Switch checkedChildren={t('llmConfig.yesSwitch')} unCheckedChildren={t('llmConfig.noSwitch')} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* 测试弹窗 */}
      <Modal
        title={t('llmConfig.testTitle', { name: testingConfig?.displayName || testingConfig?.credentialName })}
        open={testModalVisible}
        onCancel={() => setTestModalVisible(false)}
        footer={[
          <Button key="close" onClick={() => setTestModalVisible(false)}>
            {t('llmConfig.close')}
          </Button>,
          <Button
            key="test"
            type="primary"
            loading={testLoading}
            onClick={runTest}
            icon={<ThunderboltOutlined />}
          >
            {t('llmConfig.sendTest')}
          </Button>,
        ]}
        width={700}
      >
        {testingConfig && (
          <Descriptions bordered size="small" column={2} style={{ marginBottom: 16 }}>
            <Descriptions.Item label={t('llmConfig.testCredential')}>{testingConfig.credentialName}</Descriptions.Item>
            <Descriptions.Item label={t('llmConfig.testModel')}>{testingConfig.model}</Descriptions.Item>
            <Descriptions.Item label={t('llmConfig.testApiEndpoint')} span={2}>
              <Text copyable>{testingConfig.apiBase}</Text>
            </Descriptions.Item>
          </Descriptions>
        )}

        <Form form={testForm} layout="vertical">
          <Form.Item name="prompt" label={t('llmConfig.testPromptLabel')}>
            <TextArea rows={3} placeholder={t('llmConfig.testPromptPlaceholder')} />
          </Form.Item>
        </Form>

        {testLoading && (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
            <div style={{ marginTop: 8 }}>{t('llmConfig.testingConnection')}</div>
          </div>
        )}

        {testResult && (
          <Descriptions bordered column={1} style={{ marginTop: 16 }}>
            <Descriptions.Item label={t('llmConfig.testStatus')}>
              {testResult.success ? (
                <Tag color="success" icon={<CheckCircleOutlined />}>{t('llmConfig.testSuccess')}</Tag>
              ) : (
                <Tag color="error" icon={<CloseCircleOutlined />}>{t('llmConfig.testFailed')}</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label={t('llmConfig.testModelLabel')}>{testResult.model}</Descriptions.Item>
            <Descriptions.Item label={t('llmConfig.testLatency')}>{testResult.latencyMs} ms</Descriptions.Item>
            {testResult.tokensUsed !== undefined && (
              <Descriptions.Item label={t('llmConfig.testTokens')}>{testResult.tokensUsed}</Descriptions.Item>
            )}
            {testResult.response && (
              <Descriptions.Item label={t('llmConfig.testResponse')}>
                <div style={{ maxHeight: 200, overflow: 'auto' }}>
                  <ReactMarkdown>{testResult.response}</ReactMarkdown>
                </div>
              </Descriptions.Item>
            )}
            {testResult.error && (
              <Descriptions.Item label={t('llmConfig.testError')}>
                <Text type="danger">{testResult.error}</Text>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>
    </div>
  );
};

export default LLMConfigPage;
// @AI_GENERATED: end
