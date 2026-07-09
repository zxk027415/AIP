import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card,
  List,
  Button,
  Space,
  message,
  Modal,
  Typography,
  Tag,
  Empty,
  Spin,
  // @AI_GENERATED
  Form,
  Input,
  Select,
  // @AI_GENERATED: end
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
  // @AI_GENERATED
  CopyOutlined,
  // @AI_GENERATED: end
} from '@ant-design/icons';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import { enhancedWorkflowApi } from '../services/workflowEnhancedApi';
import type { EnhancedWorkflowSummary } from '../types/workflow-enhanced';
import './WorkflowListPage.css';

const { Title, Text } = Typography;

/**
 * 算法模板列表页面
 * 显示所有保存的算法模板，支持查看、编辑、删除操作
 */
const WorkflowListPage: React.FC = () => {
  const navigate = useNavigate();
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [workflows, setWorkflows] = useState<EnhancedWorkflowSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [deleteModalVisible, setDeleteModalVisible] = useState(false);
  const [workflowToDelete, setWorkflowToDelete] = useState<EnhancedWorkflowSummary | null>(null);

  // @AI_GENERATED
  // 从模板创建弹窗状态（spec: algorithm-deployment-refactor, task 11.1）
  const [templateModalVisible, setTemplateModalVisible] = useState(false);
  const [creatingFromTemplate, setCreatingFromTemplate] = useState(false);
  const [templateForm] = Form.useForm<{ template_id: string; name: string }>();
  // @AI_GENERATED: end

  // 加载算法模板列表
  const loadWorkflows = async () => {
    try {
      setLoading(true);
      const list = await enhancedWorkflowApi.listWorkflowSummaries();
      setWorkflows(list);
    } catch (error) {
      console.error('Load workflows error:', error);
      message.error(t('workflowList.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWorkflows();
  }, []);

  // @AI_GENERATED: Kiro v1.0
  // 创建空白工作流：导航到编辑器（无 id 参数 → "新建"模式）
  // spec: algorithm-deployment-refactor requirement 7.1/7.3
  const handleCreate = () => {
    navigate('/workflow/editor');
  };

  // 打开已有工作流：带 id 参数（"编辑已有"模式）
  const handleOpen = (workflow: EnhancedWorkflowSummary) => {
    navigate(`/workflow/editor/${workflow.id}`);
  };
  // @AI_GENERATED: end

  // @AI_GENERATED
  // ------- 从模板创建流程（spec: algorithm-deployment-refactor, task 11.1）-------
  // 打开"从模板创建"弹窗；不预选模板，交由用户在 Select 中选择
  const handleOpenTemplateModal = () => {
    templateForm.resetFields();
    setTemplateModalVisible(true);
  };

  // 关闭并清理表单
  const handleCloseTemplateModal = () => {
    setTemplateModalVisible(false);
    templateForm.resetFields();
  };

  /**
   * 从模板创建工作流：调用 POST /api/workflows/enhanced/create-from-template
   *
   * 关键行为（对齐后端契约）：
   * - 请求体 { template_id, name }，两者均必填
   * - 成功：跳转到 /workflow/editor/{new_id}，即新工作流的编辑页
   * - 400 name_conflict：新名称与源模板同名 → 提示需要新名称
   * - 404：template_id 不存在 → 提示源模板不存在
   */
  const handleCreateFromTemplate = async () => {
    let values: { template_id: string; name: string };
    try {
      values = await templateForm.validateFields();
    } catch {
      return; // 表单校验失败，不发起请求
    }

    setCreatingFromTemplate(true);
    try {
      const newWorkflow = await enhancedWorkflowApi.createFromTemplate({
        template_id: values.template_id,
        name: values.name.trim(),
      });
      message.success(t('workflowList.createFromTemplateSuccess'));
      setTemplateModalVisible(false);
      templateForm.resetFields();
      // 跳转到新工作流编辑页（编辑已有模式，id 为新生成的 workflow_id）
      navigate(`/workflow/editor/${newWorkflow.id}`);
    } catch (error: unknown) {
      console.error('Create from template error:', error);
      // 尝试解析 axios 错误响应中的业务错误码
      const axiosError = error as {
        response?: { status?: number; data?: { detail?: unknown } };
      };
      const status = axiosError?.response?.status;
      const detail = axiosError?.response?.data?.detail;

      if (status === 404) {
        message.error(t('workflowList.templateNotFound'));
      } else if (
        status === 400 &&
        detail &&
        typeof detail === 'object' &&
        (detail as { code?: string }).code === 'name_conflict'
      ) {
        message.error(t('workflowList.nameConflict'));
      } else {
        const fallback =
          typeof detail === 'string'
            ? detail
            : (detail as { message?: string } | undefined)?.message;
        message.error(fallback || t('workflowList.createFromTemplateFailed'));
      }
    } finally {
      setCreatingFromTemplate(false);
    }
  };
  // @AI_GENERATED: end

  // 删除算法模板
  const handleDelete = async () => {
    if (!workflowToDelete) return;

    try {
      await enhancedWorkflowApi.deleteWorkflow(workflowToDelete.id!);
      message.success(t('workflowList.deleted'));
      setDeleteModalVisible(false);
      setWorkflowToDelete(null);
      loadWorkflows(); // 重新加载列表
    } catch (error) {
      console.error('Delete workflow error:', error);
      message.error(t('workflowList.deleteFailed'));
    }
  };

  // 显示删除确认对话框
  const showDeleteConfirm = (workflow: EnhancedWorkflowSummary) => {
    setWorkflowToDelete(workflow);
    setDeleteModalVisible(true);
  };

  // 格式化日期
  const formatDate = (dateString?: string) => {
    if (!dateString) return t('workflowList.unknown');
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div style={{ 
      padding: '16px',
      height: '100%',
      overflow: 'hidden'
    }}>
      <Card style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div className="workflow-list-header">
          <Title level={3}>
            <FolderOpenOutlined /> {t('workflowList.myTemplates')}
          </Title>
          {/* @AI_GENERATED */}
          <Space size="small">
            <Button
              icon={<CopyOutlined />}
              onClick={handleOpenTemplateModal}
              disabled={workflows.length === 0}
            >
              {t('workflowList.createFromTemplate')}
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={handleCreate}
            >
              {t('workflowList.createBlank')}
            </Button>
          </Space>
          {/* @AI_GENERATED: end */}
        </div>

        <div style={{ flex: 1, overflow: 'auto', marginTop: '16px' }}>
          <Spin spinning={loading}>
            {workflows.length === 0 && !loading ? (
              <Empty
                description={t('workflowList.noTemplates')}
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              >
                <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
                  {t('workflowList.createFirst')}
                </Button>
              </Empty>
            ) : (
              <List
                className="workflow-list"
                dataSource={workflows}
                renderItem={(workflow) => (
                  <List.Item
                    className="workflow-list-item"
                    actions={[
                      <Button
                        type="link"
                        icon={<EditOutlined />}
                        onClick={() => handleOpen(workflow)}
                      >
                        {t('workflowList.edit')}
                      </Button>,
                      <Button
                        type="link"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={() => showDeleteConfirm(workflow)}
                      >
                        {t('workflowList.delete')}
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <div className="workflow-title">
                          <span 
                            className="workflow-name"
                            onClick={() => handleOpen(workflow)}
                          >
                            {td(workflow.name)}
                          </span>
                          <Space size="small">
                            <Tag color="blue">{workflow.nodeCount} {t('workflowList.nodes')}</Tag>
                            <Tag color="green">{workflow.edgeCount} {t('workflowList.connections')}</Tag>
                          </Space>
                        </div>
                      }
                      description={
                        <div className="workflow-description">
                          <Text type="secondary">
                            {td(workflow.description) || t('workflowList.noDescription')}
                          </Text>
                          <div className="workflow-meta">
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {t('workflowList.createdAt')} {formatDate(workflow.createdAt)}
                            </Text>
                            {workflow.updatedAt && workflow.updatedAt !== workflow.createdAt && (
                              <Text type="secondary" style={{ fontSize: 12, marginLeft: 16 }}>
                                {t('workflowList.updatedAt')} {formatDate(workflow.updatedAt)}
                              </Text>
                            )}
                          </div>
                        </div>
                      }
                    />
                  </List.Item>
                )}
              />
            )}
          </Spin>
        </div>
      </Card>

      {/* 删除确认对话框 */}
      <Modal
        title={t('workflowList.confirmDelete')}
        open={deleteModalVisible}
        onOk={handleDelete}
        onCancel={() => {
          setDeleteModalVisible(false);
          setWorkflowToDelete(null);
        }}
        okText={t('workflowList.delete')}
        cancelText={t('workflowList.cancel')}
        okButtonProps={{ danger: true }}
      >
        <p>{t('workflowList.confirmDeleteMessage')} "{workflowToDelete?.name}" ?</p>
        <p style={{ color: '#999', fontSize: 12 }}>{t('workflowList.irreversible')}</p>
      </Modal>

      {/* @AI_GENERATED */}
      {/* 从模板创建工作流对话框 —— spec: algorithm-deployment-refactor, task 11.1 */}
      <Modal
        title={t('workflowList.createFromTemplateTitle')}
        open={templateModalVisible}
        onOk={handleCreateFromTemplate}
        onCancel={handleCloseTemplateModal}
        okText={t('workflowList.confirm')}
        cancelText={t('workflowList.cancel')}
        confirmLoading={creatingFromTemplate}
        destroyOnClose
      >
        <Form
          form={templateForm}
          layout="vertical"
          preserve={false}
          initialValues={{ template_id: undefined, name: '' }}
        >
          <Form.Item
            name="template_id"
            label={t('workflowList.selectTemplate')}
            rules={[
              { required: true, message: t('workflowList.templateRequired') },
            ]}
          >
            <Select
              placeholder={t('workflowList.selectTemplatePlaceholder')}
              showSearch
              optionFilterProp="label"
              options={workflows.map((w) => ({
                label: `${td(w.name)}${w.version ? ` (v${w.version})` : ''}`,
                value: w.id,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="name"
            label={t('workflowList.newWorkflowName')}
            rules={[
              { required: true, message: t('workflowList.nameRequired') },
              {
                validator: async (_rule, value) => {
                  const trimmed = (value || '').trim();
                  if (!trimmed) return; // required 已经处理空
                  const tplId = templateForm.getFieldValue('template_id');
                  const tpl = workflows.find((w) => w.id === tplId);
                  if (tpl && td(tpl.name).trim() === trimmed) {
                    throw new Error(t('workflowList.nameConflict'));
                  }
                },
              },
            ]}
          >
            <Input
              placeholder={t('workflowList.newWorkflowNamePlaceholder')}
              maxLength={100}
            />
          </Form.Item>
        </Form>
      </Modal>
      {/* @AI_GENERATED: end */}
    </div>
  );
};

export default WorkflowListPage;
