import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card,
  Row,
  Col,
  Button,
  Input,
  Tag,
  Modal,
  Form,
  message,
  Empty,
  Spin,
} from 'antd';
import {
  SearchOutlined,
  AppstoreOutlined,
  FileTextOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { templates } from '../services/workflowApi';
import type { WorkflowTemplate } from '../types/template';
import './TemplateGalleryPage.css';

const { Search } = Input;
const { Meta } = Card;

const TemplateGalleryPage: React.FC = () => {
  const navigate = useNavigate();
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [loading, setLoading] = useState(false);
  const [templateList, setTemplateList] = useState<WorkflowTemplate[]>([]);
  const [filteredList, setFilteredList] = useState<WorkflowTemplate[]>([]);
  const [searchText, setSearchText] = useState('');
  const [selectedTemplate, setSelectedTemplate] = useState<WorkflowTemplate | null>(null);
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [form] = Form.useForm();

  // 加载模板列表
  const loadTemplates = async () => {
    setLoading(true);
    try {
      const data = await templates.list();
      setTemplateList(data);
      setFilteredList(data);
    } catch (error: any) {
      // 如果是 404 错误，说明模板 API 还未实现
      if (error.response?.status === 404) {
        message.info(t('templateGallery.comingSoon'));
        // 设置空列表，避免显示错误
        setTemplateList([]);
        setFilteredList([]);
      } else {
        message.error(t('templateGallery.loadFailed'));
        console.error(error);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  // 搜索过滤
  useEffect(() => {
    if (searchText) {
      const filtered = templateList.filter(
        (item) =>
          item.name.toLowerCase().includes(searchText.toLowerCase()) ||
          item.description.toLowerCase().includes(searchText.toLowerCase()) ||
          item.category.toLowerCase().includes(searchText.toLowerCase())
      );
      setFilteredList(filtered);
    } else {
      setFilteredList(templateList);
    }
  }, [searchText, templateList]);

  // 查看模板详情
  const handleViewTemplate = (template: WorkflowTemplate) => {
    setSelectedTemplate(template);
  };

  // 使用模板创建算法模板
  const handleUseTemplate = (template: WorkflowTemplate) => {
    setSelectedTemplate(template);
    setCreateModalVisible(true);
    form.setFieldsValue({
      name: `${template.name} - ${t('templateGallery.copy')}`,
      description: template.description,
    });
  };

  // 确认创建算法模板
  const handleCreateFromTemplate = async () => {
    try {
      const values = await form.validateFields();
      const workflow = await templates.createFromTemplate(
        selectedTemplate!.id,
        values
      );
      message.success(t('templateGallery.createSuccess'));
      setCreateModalVisible(false);
      form.resetFields();
      navigate(`/workflow/editor/${workflow.id}`);
    } catch (error) {
      message.error(t('templateGallery.createFailed'));
      console.error(error);
    }
  };

  // 获取分类图标
  const getCategoryIcon = (category: string) => {
    switch (category.toLowerCase()) {
      case 'machine-learning':
      case '机器学习':
        return <RocketOutlined />;
      case 'data-analysis':
      case '数据分析':
        return <AppstoreOutlined />;
      default:
        return <FileTextOutlined />;
    }
  };

  // 获取分类颜色
  const getCategoryColor = (category: string) => {
    switch (category.toLowerCase()) {
      case 'machine-learning':
      case '机器学习':
        return 'blue';
      case 'data-analysis':
      case '数据分析':
        return 'green';
      case 'signal-processing':
      case '信号处理':
        return 'orange';
      default:
        return 'default';
    }
  };

  return (
    <div className="template-gallery-page">
      <Card
        title={
          <div className="page-header">
            <h2>{t('templateGallery.title')}</h2>
            <p>{t('templateGallery.subtitle')}</p>
          </div>
        }
      >
        <div className="template-toolbar">
          <Search
            placeholder={t('templateGallery.searchPlaceholder')}
            allowClear
            enterButton={<SearchOutlined />}
            size="large"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 400 }}
          />
        </div>

        <Spin spinning={loading}>
          {filteredList.length === 0 && !loading ? (
            <Empty 
              description={
                templateList.length === 0 
                  ? t('templateGallery.comingSoon')
                  : t('templateGallery.noMatch')
              } 
            />
          ) : (
            <Row gutter={[16, 16]}>
              {filteredList.map((template) => (
                <Col xs={24} sm={12} md={8} lg={6} key={template.id}>
                  <Card
                    hoverable
                    className="template-card"
                    cover={
                      template.previewImage ? (
                        <img
                          alt={template.name}
                          src={template.previewImage}
                          className="template-preview"
                        />
                      ) : (
                        <div className="template-preview-placeholder">
                          {getCategoryIcon(template.category)}
                        </div>
                      )
                    }
                    actions={[
                      <Button
                        type="link"
                        onClick={() => handleViewTemplate(template)}
                      >
                        {t('templateGallery.viewDetail')}
                      </Button>,
                      <Button
                        type="primary"
                        onClick={() => handleUseTemplate(template)}
                      >
                        {t('templateGallery.useTemplate')}
                      </Button>,
                    ]}
                  >
                    <Meta
                      title={template.name}
                      description={
                        <div className="template-meta">
                          <p className="template-description">
                            {template.description}
                          </p>
                          <Tag color={getCategoryColor(template.category)}>
                            {template.category}
                          </Tag>
                        </div>
                      }
                    />
                  </Card>
                </Col>
              ))}
            </Row>
          )}
        </Spin>
      </Card>

      {/* 模板详情模态框 */}
      <Modal
        title={selectedTemplate?.name}
        open={selectedTemplate !== null && !createModalVisible}
        onCancel={() => setSelectedTemplate(null)}
        footer={[
          <Button key="cancel" onClick={() => setSelectedTemplate(null)}>
            {t('common.close')}
          </Button>,
          <Button
            key="use"
            type="primary"
            onClick={() => handleUseTemplate(selectedTemplate!)}
          >
            {t('templateGallery.useThisTemplate')}
          </Button>,
        ]}
        width={700}
      >
        {selectedTemplate && (
          <div className="template-detail">
            <div className="template-detail-section">
              <h4>{t('templateGallery.description')}</h4>
              <p>{selectedTemplate.description}</p>
            </div>
            <div className="template-detail-section">
              <h4>{t('templateGallery.category')}</h4>
              <Tag color={getCategoryColor(selectedTemplate.category)}>
                {selectedTemplate.category}
              </Tag>
            </div>
            {selectedTemplate.documentation && (
              <div className="template-detail-section">
                <h4>{t('templateGallery.usageGuide')}</h4>
                <div
                  className="template-documentation"
                  dangerouslySetInnerHTML={{
                    __html: selectedTemplate.documentation,
                  }}
                />
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* 创建算法模板模态框 */}
      <Modal
        title={t('templateGallery.createFromTemplate')}
        open={createModalVisible}
        onOk={handleCreateFromTemplate}
        onCancel={() => {
          setCreateModalVisible(false);
          form.resetFields();
        }}
        okText={t('templateGallery.create')}
        cancelText={t('common.cancel')}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label={t('templateGallery.templateName')}
            rules={[{ required: true, message: t('templateGallery.templateNameRequired') }]}
          >
            <Input placeholder={t('templateGallery.templateNamePlaceholder')} />
          </Form.Item>
          <Form.Item name="description" label={t('templateGallery.description')}>
            <Input.TextArea
              rows={4}
              placeholder={t('templateGallery.descriptionPlaceholder')}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default TemplateGalleryPage;
