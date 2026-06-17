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
  Spin
} from 'antd';
import { 
  PlusOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  PlayCircleOutlined,
  FolderOpenOutlined
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
  // 创建新算法模板
  const handleCreate = () => {
    navigate('/workflow/editor');
  };

  // 打开算法模板
  const handleOpen = (workflow: EnhancedWorkflowSummary) => {
    navigate(`/workflow/editor/${workflow.id}`);
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
          <Button 
            type="primary" 
            icon={<PlusOutlined />}
            onClick={handleCreate}
          >
            {t('workflowList.createTemplate')}
          </Button>
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
    </div>
  );
};

export default WorkflowListPage;
