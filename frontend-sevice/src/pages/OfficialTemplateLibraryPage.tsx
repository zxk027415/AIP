// @AI_GENERATED: Kiro v1.0
/**
 * 算法模板库页面
 * 展示工作流模板和Skills两种形态，统一列表视图
 */
import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card, Table, Space, Typography, Tag, Row, Col, Statistic, Input, Select,
  Button, Tooltip, Empty, Spin, Badge, Modal, Descriptions, Form, InputNumber,
  Divider, Alert, Steps, message, Popconfirm, Segmented,
} from 'antd';
import {
  AppstoreOutlined, SearchOutlined, RocketOutlined, CheckCircleOutlined,
  ClockCircleOutlined, ExperimentOutlined, EditOutlined, EyeOutlined,
  CopyOutlined, StarOutlined, StarFilled, FilterOutlined, CodeOutlined,
  SettingOutlined, ThunderboltOutlined, SyncOutlined, ApartmentOutlined,
  CloudServerOutlined, DeleteOutlined, PlayCircleOutlined, ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { templateSkillApi, type PackagedSkill } from '../services/templateSkillApi';
import { workflowTemplateApi } from '../services/algoTemplateApi';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const { TextArea } = Input;

const { Text, Paragraph } = Typography;

// 模板状态枚举
export type TemplateStatus = 'draft' | 'developing' | 'testing' | 'published' | 'deprecated';

// 官方模板数据类型（从后端 API 获取）
interface OfficialTemplate {
  id: string;
  name: string;
  description: string;
  scenario_id: string;
  scenario_name: string;
  category: string;
  status: TemplateStatus;
  version: string;
  author: string;
  created_at: string;
  updated_at: string;
  published_at?: string;
  node_count: number;
  edge_count: number;
  usage_count: number;
  star_count: number;
  tags: string[];
  is_starred?: boolean;
}

// Skill 打包配置类型
// 统一数据类型：工作流模板和Skill合并
interface UnifiedTemplateItem {
  id: string;
  name: string;
  description: string;
  type: 'workflow' | 'skill';
  status: string;
  version: string;
  category?: string;
  scenario_name?: string;
  created_at: string;
  updated_at: string;
  // 工作流特有
  node_count?: number;
  edge_count?: number;
  usage_count?: number;
  star_count?: number;
  tags?: string[];
  is_starred?: boolean;
  author?: string;
  // Skill 特有
  source_template_name?: string;
  training_enabled?: boolean;
  skill_id?: string;
}
// @AI_GENERATED: end

const OfficialTemplateLibraryPage: React.FC = () => {
  const navigate = useNavigate();
  // @AI_GENERATED
  const { t, i18n } = useTranslation();

  const workflowStatusConfig = useMemo(
    (): Record<TemplateStatus, { label: string; color: string; icon: React.ReactNode }> => ({
      draft: { label: t('templateLibrary.draft'), color: 'default', icon: <EditOutlined /> },
      developing: { label: t('templateLibrary.developing'), color: 'processing', icon: <ClockCircleOutlined /> },
      testing: { label: t('templateLibrary.testing'), color: 'warning', icon: <ExperimentOutlined /> },
      published: { label: t('templateLibrary.published'), color: 'success', icon: <CheckCircleOutlined /> },
      deprecated: { label: t('templateLibrary.deprecated'), color: 'error', icon: <ClockCircleOutlined /> },
    }),
    [t],
  );

  const dateLocale = i18n.language?.toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN';
  // @AI_GENERATED: end
  // @AI_GENERATED: Kiro v1.0
  const [typeFilter, setTypeFilter] = useState<'all' | 'workflow' | 'skill'>('all');
  // @AI_GENERATED: end
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<OfficialTemplate[]>([]);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<TemplateStatus | 'all'>('all');
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>(undefined);
  const [selectedTemplate, setSelectedTemplate] = useState<OfficialTemplate | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  // @AI_GENERATED: Kiro v1.0
  // 打包 Skill 相关状态
  const [packageVisible, setPackageVisible] = useState(false);
  const [packageTemplate, setPackageTemplate] = useState<OfficialTemplate | null>(null);
  const [packageStep, setPackageStep] = useState(0);
  const [packaging, setPackaging] = useState(false);
  const [packageForm] = Form.useForm();
  // Skills 相关状态
  const [skills, setSkills] = useState<PackagedSkill[]>([]);
  const [skillsLoading, setSkillsLoading] = useState(false);
  // 编辑模板相关状态
  const [editVisible, setEditVisible] = useState(false);
  const [editTemplate, setEditTemplate] = useState<OfficialTemplate | null>(null);
  const [editForm] = Form.useForm();
  const [editing, setEditing] = useState(false);
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 加载工作流模板数据
  const loadTemplates = async () => {
    setLoading(true);
    try {
      const response = await workflowTemplateApi.listTemplates();
      setTemplates(response.templates as OfficialTemplate[]);
    } catch (error) {
      message.error(t('templateLibrary.loadWorkflowFailed'));
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, []);
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 加载 Skills 数据
  const loadSkills = async () => {
    setSkillsLoading(true);
    try {
      const response = await templateSkillApi.listSkills();
      setSkills(response.skills);
    } catch (error) {
      message.error(t('templateLibrary.loadSkillsFailed'));
      console.error(error);
    } finally {
      setSkillsLoading(false);
    }
  };

  useEffect(() => {
    loadSkills();
  }, []);
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 统一数据：合并工作流模板和Skills
  const unifiedData = useMemo((): UnifiedTemplateItem[] => {
    const templateById = new Map(templates.map(t => [t.id, t]));

    const workflowItems: UnifiedTemplateItem[] = templates.map(t => ({
      id: t.id,
      name: t.name,
      description: t.description,
      type: 'workflow' as const,
      status: t.status,
      version: t.version,
      category: t.category,
      scenario_name: t.scenario_name,
      created_at: t.created_at,
      updated_at: t.updated_at,
      node_count: t.node_count,
      edge_count: t.edge_count,
      usage_count: t.usage_count,
      star_count: t.star_count,
      tags: t.tags,
      is_starred: t.is_starred,
      author: t.author,
    }));
    
    const skillItems: UnifiedTemplateItem[] = skills.map(s => {
      const sourceTemplate = templateById.get(s.source_template_id);
      return {
      id: s.skill_id,
      name: s.skill_name,
      description: s.description || '',
      type: 'skill' as const,
      status: s.status,
      version: s.skill_version,
      scenario_name: sourceTemplate?.scenario_name,
      created_at: s.created_at,
      updated_at: s.updated_at || s.created_at,
      source_template_name: s.source_template_name,
      training_enabled: s.training_config?.enabled,
      skill_id: s.skill_id,
      };
    });
    
    return [...workflowItems, ...skillItems];
  }, [templates, skills]);

  // 统计数据（合并统计）
  const stats = useMemo(() => {
    const totalWorkflows = templates.length;
    const totalSkills = skills.length;
    const publishedWorkflows = templates.filter(t => t.status === 'published').length;
    const readySkills = skills.filter(s => s.status === 'ready').length;
    const deployedSkills = skills.filter(s => s.status === 'deployed').length;
    const totalUsage = templates.reduce((sum, t) => sum + t.usage_count, 0);
    return { totalWorkflows, totalSkills, publishedWorkflows, readySkills, deployedSkills, totalUsage };
  }, [templates, skills]);
  // @AI_GENERATED: end

  // 分类列表
  const categories = useMemo(() => {
    const cats = new Set(templates.map(t => t.category));
    return Array.from(cats);
  }, [templates]);

  // @AI_GENERATED: Kiro v1.0
  // 过滤后的统一数据
  const filteredData = useMemo(() => {
    return unifiedData.filter(item => {
      // 类型筛选
      if (typeFilter !== 'all' && item.type !== typeFilter) return false;
      // 关键词搜索
      if (keyword && !item.name.toLowerCase().includes(keyword.toLowerCase()) &&
          !item.description.toLowerCase().includes(keyword.toLowerCase())) {
        return false;
      }
      // 状态筛选（工作流和Skill状态不同，需要分别处理）
      if (statusFilter !== 'all') {
        if (item.type === 'workflow' && item.status !== statusFilter) return false;
        // Skill 状态映射
        if (item.type === 'skill') {
          const skillStatusMap: Record<string, string[]> = {
            published: ['ready', 'deployed'],
            testing: ['training'],
            developing: ['packaged'],
          };
          if (!skillStatusMap[statusFilter]?.includes(item.status)) return false;
        }
      }
      // 分类筛选（仅工作流有分类）
      if (categoryFilter && item.type === 'workflow' && item.category !== categoryFilter) return false;
      return true;
    });
  }, [unifiedData, typeFilter, keyword, statusFilter, categoryFilter]);
  // @AI_GENERATED: end

  const handleViewDetail = (template: OfficialTemplate) => {
    setSelectedTemplate(template);
    setDetailVisible(true);
  };

  // @AI_GENERATED: Kiro v1.0
  const handleUseTemplate = (template: OfficialTemplate) => {
    // 如果是光伏发电功率预测模板，直接跳转到已保存的demo工作流
    if (template.id === 'tpl-pv-power-001') {
      navigate('/workflow/editor/workflow-pv-power-demo');
    } else {
      // 其他模板跳转到模板编辑器，基于此模板创建新模板
      navigate(`/workflow/editor?from=${template.id}`);
    }
  };
  // @AI_GENERATED: end

  const handleToggleStar = (templateId: string) => {
    setTemplates(prev => prev.map(t => 
      t.id === templateId ? { ...t, is_starred: !t.is_starred, star_count: t.is_starred ? t.star_count - 1 : t.star_count + 1 } : t
    ));
  };

  // @AI_GENERATED: Kiro v1.0
  // 打开编辑模板弹窗
  const handleEditTemplate = (template: OfficialTemplate) => {
    setEditTemplate(template);
    editForm.setFieldsValue({
      name: template.name,
      description: template.description,
      scenario_id: template.scenario_id,
      scenario_name: template.scenario_name,
      category: template.category,
      status: template.status,
      version: template.version,
      tags: template.tags?.join(', ') || '',
    });
    setEditVisible(true);
  };

  // 提交编辑
  const handleSubmitEdit = async () => {
    try {
      const values = await editForm.validateFields();
      setEditing(true);
      
      const request = {
        name: values.name,
        description: values.description,
        scenario_id: values.scenario_id,
        scenario_name: values.scenario_name,
        category: values.category,
        status: values.status,
        version: values.version,
        tags: values.tags ? values.tags.split(',').map((t: string) => t.trim()).filter(Boolean) : [],
      };
      
      await workflowTemplateApi.updateTemplate(editTemplate!.id, request);
      message.success(t('templateLibrary.templateUpdateSuccess'));
      setEditVisible(false);
      setEditTemplate(null);
      editForm.resetFields();
      loadTemplates();
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return;
      }
      message.error(t('templateLibrary.updateFailed'));
    } finally {
      setEditing(false);
    }
  };

  // 打开打包 Skill 弹窗
  const handlePackageSkill = (template: OfficialTemplate) => {
    setPackageTemplate(template);
    setPackageStep(0);
    packageForm.setFieldsValue({
      skill_name: `${template.name} Skill`,
      skill_version: '1.0.0',
      description: template.description,
      training_enabled: true,
      min_samples: 30,
      default_epochs: 80,
      default_batch_size: 32,
      cpu: '2',
      memory: '4Gi',
      gpu: 'optional',
      timeout_seconds: 300,
    });
    setPackageVisible(true);
  };

  // 提交打包请求
  const handleSubmitPackage = async () => {
    try {
      const values = await packageForm.validateFields();
      setPackaging(true);
      
      // 调用真实 API
      const request = {
        template_id: packageTemplate!.id,
        template_name: packageTemplate!.name,
        template_version: packageTemplate!.version,
        skill_name: values.skill_name || `${packageTemplate!.name} Skill`,
        skill_version: values.skill_version || '1.0.0',
        description: values.description || '',
        training_config: {
          enabled: Boolean(values.training_enabled ?? true),
          min_samples: Number(values.min_samples ?? 30),
          default_epochs: Number(values.default_epochs ?? 80),
          default_batch_size: Number(values.default_batch_size ?? 32),
        },
        resource_config: {
          cpu: String(values.cpu ?? '2'),
          memory: String(values.memory ?? '4Gi'),
          gpu: String(values.gpu ?? 'optional'),
          timeout_seconds: Number(values.timeout_seconds ?? 300),
        },
      };
      
      // 调试日志
      console.log('Package request:', JSON.stringify(request, null, 2));
      
      const result = await templateSkillApi.packageTemplate(request);
      message.success(result.message || t('templateLibrary.packageSuccess', { name: request.skill_name }));
      setPackageVisible(false);
      setPackageTemplate(null);
      setPackageStep(0);
      packageForm.resetFields();
    } catch (error: unknown) {
      // 表单验证错误 - 不显示错误消息，让用户修正表单
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return;
      }
      // Axios 错误 - 打印详细信息
      if (error && typeof error === 'object' && 'response' in error) {
        const axiosError = error as { response?: { data?: unknown; status?: number } };
        console.error('API Error:', axiosError.response?.status, axiosError.response?.data);
        const detail = (axiosError.response?.data as { detail?: string })?.detail;
        message.error(`${t('templateLibrary.packageFailed')}: ${detail || t('templateLibrary.serverError')}`);
      } else if (error instanceof Error) {
        message.error(`${t('templateLibrary.packageFailed')}: ${error.message}`);
      } else {
        message.error(`${t('templateLibrary.packageFailed')}: ${t('templateLibrary.unknownError')}`);
      }
    } finally {
      setPackaging(false);
    }
  };
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 统一列表的列定义
  const unifiedColumns: ColumnsType<UnifiedTemplateItem> = [
    {
      title: t('templateLibrary.colType'),
      dataIndex: 'type',
      key: 'type',
      width: 90,
      render: (type: 'workflow' | 'skill') => (
        type === 'workflow' 
          ? <Tag color="blue" icon={<ApartmentOutlined />}>{t('templateLibrary.workflow')}</Tag>
          : <Tag color="purple" icon={<ThunderboltOutlined />}>{t('templateLibrary.skillTag')}</Tag>
      ),
    },
    {
      title: t('templateLibrary.colName'),
      dataIndex: 'name',
      key: 'name',
      width: 260,
      render: (name, record) => (
        <Space direction="vertical" size={2}>
          <Space>
            {record.type === 'workflow' 
              ? <ApartmentOutlined style={{ color: '#1890ff' }} />
              : <ThunderboltOutlined style={{ color: '#722ed1' }} />
            }
            <Text strong style={{ cursor: 'pointer' }} onClick={() => {
              if (record.type === 'workflow') {
                const tpl = templates.find(t => t.id === record.id);
                if (tpl) handleViewDetail(tpl);
              } else {
                navigate(`/skill-library/${record.skill_id}`);
              }
            }}>
              {td(name)}
            </Text>
            {record.is_starred && <StarFilled style={{ color: '#faad14', fontSize: 12 }} />}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
            {td(record.description) || t('templateLibrary.noDescription')}
          </Text>
        </Space>
      ),
    },
    {
      title: t('templateLibrary.colStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status, record) => {
        if (record.type === 'workflow') {
          const config = workflowStatusConfig[status as TemplateStatus];
          return config ? <Tag color={config.color} icon={config.icon}>{config.label}</Tag> : <Tag>{status}</Tag>;
        } else {
          const skillStatusMap: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
            packaged: { label: t('templateLibrary.statusPackaged'), color: 'default', icon: <CodeOutlined /> },
            training: { label: t('templateLibrary.statusTraining'), color: 'processing', icon: <SyncOutlined spin /> },
            ready: { label: t('templateLibrary.statusReady'), color: 'success', icon: <CheckCircleOutlined /> },
            deployed: { label: t('templateLibrary.statusDeployed'), color: 'blue', icon: <CloudServerOutlined /> },
          };
          const config = skillStatusMap[status] || skillStatusMap.packaged;
          return <Tag color={config.color} icon={config.icon}>{config.label}</Tag>;
        }
      },
    },
    {
      title: t('templateLibrary.colVersion'),
      dataIndex: 'version',
      key: 'version',
      width: 80,
      render: (v) => <Text code>{v?.startsWith('v') ? v : `v${v}`}</Text>,
    },
    {
      title: t('templateLibrary.colSource'),
      key: 'source',
      width: 140,
      render: (_, record) => (
        record.type === 'workflow' 
          ? <Tag color="blue">{td(record.scenario_name)}</Tag>
          : (
            <Space direction="vertical" size={0}>
              <Text type="secondary" style={{ fontSize: 12 }}>{td(record.source_template_name)}</Text>
              {record.scenario_name && <Text type="secondary" style={{ fontSize: 11 }}>{td(record.scenario_name)}</Text>}
            </Space>
          )
      ),
    },
    {
      title: t('templateLibrary.colCategoryTraining'),
      key: 'category',
      width: 100,
      render: (_, record) => (
        record.type === 'workflow'
          ? <Tag>{td(record.category)}</Tag>
          : <Text style={{ fontSize: 12 }}>{record.training_enabled ? `✅ ${t('templateLibrary.trainable')}` : `❌ ${t('templateLibrary.inferenceOnly')}`}</Text>
      ),
    },
    {
      title: t('templateLibrary.colUsage'),
      width: 80,
      render: (_, record) => (
        record.type === 'workflow' && record.usage_count !== undefined
          ? <Badge count={record.usage_count} showZero color="#1890ff" overflowCount={999} />
          : <Text type="secondary">-</Text>
      ),
    },
    {
      title: t('templateLibrary.colUpdateTime'),
      dataIndex: 'updated_at',
      key: 'updated_at',
      width: 140,
      render: (time) => new Date(time).toLocaleDateString(dateLocale),
    },
    {
      title: t('templateLibrary.colActions'),
      key: 'actions',
      width: 180,
      render: (_, record) => {
        if (record.type === 'workflow') {
          const tpl = templates.find(t => t.id === record.id);
          return (
            <Space size={4}>
              <Tooltip title={t('templateLibrary.viewDetails')}>
                <Button type="text" size="small" icon={<EyeOutlined />} onClick={() => tpl && handleViewDetail(tpl)} />
              </Tooltip>
              <Tooltip title={record.is_starred ? t('templateLibrary.unstar') : t('templateLibrary.star')}>
                <Button
                  type="text"
                  size="small"
                  icon={record.is_starred ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
                  onClick={() => handleToggleStar(record.id)}
                />
              </Tooltip>
              {/* @AI_GENERATED: Kiro v1.0 */}
              <Tooltip title={t('common.edit')}>
                <Button type="text" size="small" icon={<EditOutlined />} onClick={() => tpl && handleEditTemplate(tpl)} />
              </Tooltip>
              <Popconfirm
                title={t('templateLibrary.confirmDeleteWorkflow')}
                onConfirm={async () => {
                  try {
                    await workflowTemplateApi.deleteTemplate(record.id);
                    message.success(t('templateLibrary.deleteSuccess'));
                    loadTemplates();
                  } catch {
                    message.error(t('templateLibrary.deleteFailed'));
                  }
                }}
              >
                <Tooltip title={t('common.delete')}>
                  <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                </Tooltip>
              </Popconfirm>
              {/* @AI_GENERATED: end */}
              {record.status === 'published' && (
                <>
                  <Tooltip title={t('templateLibrary.useThisTemplate')}>
                    <Button type="primary" size="small" icon={<CopyOutlined />} onClick={() => tpl && handleUseTemplate(tpl)}>
                      {t('templateLibrary.use')}
                    </Button>
                  </Tooltip>
                  <Tooltip title={t('templateLibrary.packageAsSkill')}>
                    <Button size="small" icon={<ThunderboltOutlined />} onClick={() => tpl && handlePackageSkill(tpl)}>
                      {t('templateLibrary.package')}
                    </Button>
                  </Tooltip>
                </>
              )}
            </Space>
          );
        } else {
          // Skill 操作
          return (
            <Space size={4}>
              <Tooltip title={t('templateLibrary.viewDetails')}>
                <Button type="text" size="small" icon={<EyeOutlined />} onClick={() => navigate(`/skill-library/${record.skill_id}`)} />
              </Tooltip>
              {record.status === 'packaged' && (
                <Tooltip title={t('templateLibrary.startTraining')}>
                  <Button type="text" size="small" icon={<PlayCircleOutlined />} onClick={() => message.info(t('templateLibrary.startTraining'))} />
                </Tooltip>
              )}
              {record.status === 'ready' && (
                <Tooltip title={t('templateLibrary.deploy')}>
                  <Button type="primary" size="small" icon={<RocketOutlined />} onClick={() => message.info(t('templateLibrary.deploy'))}>
                    {t('templateLibrary.deploy')}
                  </Button>
                </Tooltip>
              )}
              <Popconfirm
                title={t('templateLibrary.confirmDeleteSkill')}
                onConfirm={async () => {
                  try {
                    await templateSkillApi.deleteSkill(record.skill_id!);
                    message.success(t('templateLibrary.deleteSuccess'));
                    loadSkills();
                  } catch {
                    message.error(t('templateLibrary.deleteFailed'));
                  }
                }}
              >
                <Tooltip title={t('common.delete')}>
                  <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                </Tooltip>
              </Popconfirm>
            </Space>
          );
        }
      },
    },
  ];
  // @AI_GENERATED: end

  const columns: ColumnsType<OfficialTemplate> = [
    {
      title: t('templateLibrary.templateName'),
      dataIndex: 'name',
      key: 'name',
      width: 280,
      render: (name, record) => (
        <Space direction="vertical" size={2}>
          <Space>
            <Text strong style={{ cursor: 'pointer' }} onClick={() => handleViewDetail(record)}>
              {name}
            </Text>
            {record.is_starred && <StarFilled style={{ color: '#faad14', fontSize: 12 }} />}
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
            {td(record.description) || t('templateLibrary.noDescription')}
          </Text>
        </Space>
      ),
    },
    {
      title: t('templateLibrary.colStatus'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: TemplateStatus) => {
        const config = workflowStatusConfig[status];
        return (
          <Tag color={config.color} icon={config.icon}>
            {td(config.label)}
          </Tag>
        );
      },
    },
    {
      title: t('templateLibrary.scenario'),
      dataIndex: 'scenario_name',
      key: 'scenario',
      width: 120,
      render: (name) => <Tag color="blue">{name}</Tag>,
    },
    {
      title: t('templateLibrary.category'),
      dataIndex: 'category',
      key: 'category',
      width: 100,
      render: (cat) => <Tag>{cat}</Tag>,
    },
    {
      title: t('templateLibrary.colVersion'),
      dataIndex: 'version',
      key: 'version',
      width: 80,
      render: (v) => <Text code>{v}</Text>,
    },
    {
      title: t('templateLibrary.nodesConnections'),
      key: 'structure',
      width: 100,
      render: (_, record) => (
        <Space size={4}>
          <Tag color="cyan">{t('templateLibrary.nodesUnit', { count: record.node_count })}</Tag>
          <Tag color="green">{t('templateLibrary.edgesUnit', { count: record.edge_count })}</Tag>
        </Space>
      ),
    },
    {
      title: t('templateLibrary.colUsage'),
      dataIndex: 'usage_count',
      key: 'usage',
      width: 80,
      sorter: (a, b) => a.usage_count - b.usage_count,
      render: (count) => <Badge count={count} showZero color="#1890ff" overflowCount={999} />,
    },
    {
      title: t('templateLibrary.starCount'),
      dataIndex: 'star_count',
      key: 'star',
      width: 70,
      sorter: (a, b) => a.star_count - b.star_count,
      render: (count) => (
        <Space size={2}>
          <StarOutlined style={{ color: '#faad14' }} />
          <Text>{count}</Text>
        </Space>
      ),
    },
    {
      title: t('templateLibrary.colActions'),
      key: 'actions',
      width: 200,
      render: (_, record) => (
        <Space size={4}>
          <Tooltip title={t('templateLibrary.viewDetails')}>
            <Button type="text" size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)} />
          </Tooltip>
          <Tooltip title={record.is_starred ? t('templateLibrary.unstar') : t('templateLibrary.star')}>
            <Button
              type="text"
              size="small"
              icon={record.is_starred ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
              onClick={() => handleToggleStar(record.id)}
            />
          </Tooltip>
          {record.status === 'published' && (
            <>
              <Tooltip title={t('templateLibrary.useThisTemplate')}>
                <Button type="primary" size="small" icon={<CopyOutlined />} onClick={() => handleUseTemplate(record)}>
                  {t('templateLibrary.use')}
                </Button>
              </Tooltip>
              {/* @AI_GENERATED: Kiro v1.0 */}
              <Tooltip title={t('templateLibrary.packageAsSkill')}>
                <Button size="small" icon={<ThunderboltOutlined />} onClick={() => handlePackageSkill(record)}>
                  {t('templateLibrary.package')}
                </Button>
              </Tooltip>
              {/* @AI_GENERATED: end */}
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* @AI_GENERATED: Kiro v1.0 */}
      {/* 页面标题 */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <AppstoreOutlined style={{ fontSize: 24, color: '#1890ff' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>{t('templateLibrary.title')}</Typography.Title>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          {t('templateLibrary.subtitle')}
        </Paragraph>
      </div>

      {/* 统计卡片 - 合并展示 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}>
          <Card size="small">
            <Statistic title={t('templateLibrary.workflowTemplates')} value={stats.totalWorkflows} prefix={<ApartmentOutlined style={{ color: '#1890ff' }} />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title={t('templateLibrary.totalSkillsTitle')} value={stats.totalSkills} prefix={<ThunderboltOutlined style={{ color: '#722ed1' }} />} />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title={t('templateLibrary.publishedTemplates')}
              value={stats.publishedWorkflows}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title={t('templateLibrary.readySkills')}
              value={stats.readySkills}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title={t('templateLibrary.deployedSkills')}
              value={stats.deployedSkills}
              prefix={<CloudServerOutlined style={{ color: '#1890ff' }} />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic title={t('templateLibrary.totalUsage')} value={stats.totalUsage} prefix={<RocketOutlined />} />
          </Card>
        </Col>
      </Row>

      {/* 筛选栏 - 统一筛选 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Segmented
            value={typeFilter}
            onChange={(v) => setTypeFilter(v as 'all' | 'workflow' | 'skill')}
            options={[
              { value: 'all', label: t('templateLibrary.all') },
              { value: 'workflow', label: <><ApartmentOutlined /> {t('templateLibrary.workflow')}</> },
              { value: 'skill', label: <><ThunderboltOutlined /> {t('templateLibrary.totalSkillsTitle')}</> },
            ]}
          />
          <Input
            prefix={<SearchOutlined />}
            placeholder={t('templateLibrary.searchPlaceholder')}
            allowClear
            style={{ width: 220 }}
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
          />
          <Select
            style={{ width: 120 }}
            placeholder={t('templateLibrary.statusFilter')}
            allowClear
            value={statusFilter === 'all' ? undefined : statusFilter}
            onChange={v => setStatusFilter(v || 'all')}
            options={[
              { value: 'published', label: t('templateLibrary.publishedReady') },
              { value: 'testing', label: t('templateLibrary.testingTraining') },
              { value: 'developing', label: t('templateLibrary.developingPackaged') },
              { value: 'draft', label: t('templateLibrary.draft') },
            ]}
          />
          {typeFilter !== 'skill' && (
            <Select
              style={{ width: 140 }}
              placeholder={t('templateLibrary.categoryFilter')}
              allowClear
              value={categoryFilter}
              onChange={setCategoryFilter}
              options={categories.map(c => ({ value: c, label: td(c) }))}
            />
          )}
          <Button icon={<FilterOutlined />} onClick={() => { setKeyword(''); setStatusFilter('all'); setCategoryFilter(undefined); setTypeFilter('all'); }}>
            {t('settings.reset')}
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadSkills}>{t('templateLibrary.refresh')}</Button>
        </Space>
      </Card>

      {/* 统一列表 */}
      <Card>
        <Spin spinning={loading || skillsLoading}>
          {filteredData.length > 0 ? (
            <Table
              dataSource={filteredData}
              columns={unifiedColumns}
              rowKey="id"
              size="small"
              pagination={{
                pageSize: 10,
                showTotal: (total) =>
                  t('templateLibrary.paginationTotal', {
                    total,
                    workflows: filteredData.filter((d) => d.type === 'workflow').length,
                    skills: filteredData.filter((d) => d.type === 'skill').length,
                  }),
              }}
            />
          ) : (
            <Empty description={t('templateLibrary.noMatch')} />
          )}
        </Spin>
      </Card>
      {/* @AI_GENERATED: end */}

      {/* 详情弹窗 */}
      <Modal
        title={td(selectedTemplate?.name)}
        open={detailVisible}
        onCancel={() => setDetailVisible(false)}
        width={700}
        footer={[
          <Button key="close" onClick={() => setDetailVisible(false)}>{t('common.close')}</Button>,
          // @AI_GENERATED: Kiro v1.0
          selectedTemplate?.status === 'published' && (
            <Button key="package" icon={<ThunderboltOutlined />} onClick={() => {
              setDetailVisible(false);
              handlePackageSkill(selectedTemplate!);
            }}>
              {t('templateLibrary.packageAsSkill')}
            </Button>
          ),
          // @AI_GENERATED: end
          selectedTemplate?.status === 'published' && (
            <Button key="use" type="primary" icon={<CopyOutlined />} onClick={() => {
              setDetailVisible(false);
              handleUseTemplate(selectedTemplate!);
            }}>
              {t('templateLibrary.useThisTemplate')}
            </Button>
          ),
        ]}
      >
        {selectedTemplate && (
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label={t('templateLibrary.templateId')}>{selectedTemplate.id}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.colVersion')}>{selectedTemplate.version}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.colStatus')}>
              <Tag color={workflowStatusConfig[selectedTemplate.status].color}>
                {workflowStatusConfig[selectedTemplate.status].label}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.scenario')}>{td(selectedTemplate.scenario_name)}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.category')}>{td(selectedTemplate.category)}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.author')}>{td(selectedTemplate.author)}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.nodeCount')}>{selectedTemplate.node_count}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.edgeCount')}>{selectedTemplate.edge_count}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.colUsage')}>{selectedTemplate.usage_count}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.starCount')}>{selectedTemplate.star_count}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.createdAt')}>{new Date(selectedTemplate.created_at).toLocaleString(dateLocale)}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.updatedAt')}>{new Date(selectedTemplate.updated_at).toLocaleString(dateLocale)}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.descriptionLabel')} span={2}>{td(selectedTemplate.description)}</Descriptions.Item>
            <Descriptions.Item label={t('templateLibrary.tags')} span={2}>
              <Space wrap>
                {selectedTemplate.tags.map(tag => <Tag key={tag} color="blue">{td(tag)}</Tag>)}
              </Space>
            </Descriptions.Item>
          </Descriptions>
        )}
      </Modal>

      {/* @AI_GENERATED: Kiro v1.0 */}
      {/* 编辑模板弹窗 */}
      <Modal
        title={
          <Space>
            <EditOutlined />
            <span>{t('templateLibrary.editTemplate')} - {editTemplate?.name}</span>
          </Space>
        }
        open={editVisible}
        onCancel={() => {
          setEditVisible(false);
          setEditTemplate(null);
          editForm.resetFields();
        }}
        width={600}
        footer={[
          <Button key="cancel" onClick={() => setEditVisible(false)}>{t('common.cancel')}</Button>,
          <Button key="submit" type="primary" loading={editing} onClick={handleSubmitEdit}>
            {t('common.save')}
          </Button>,
        ]}
      >
        <Form form={editForm} layout="vertical">
          <Form.Item
            name="name"
            label={t('templateLibrary.templateName')}
            rules={[{ required: true, message: t('templateLibrary.templateNameRequired') }]}
          >
            <Input placeholder={t('templateLibrary.templateName')} />
          </Form.Item>
          <Form.Item name="description" label={t('templateLibrary.descriptionLabel')}>
            <TextArea rows={3} placeholder={t('templateLibrary.templateDescription')} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="scenario_name" label={t('templateLibrary.scenarioName')}>
                <Input placeholder={t('templateLibrary.scenarioName')} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="category" label={t('templateLibrary.category')}>
                <Input placeholder={t('templateLibrary.category')} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="status" label={t('templateLibrary.colStatus')}>
                <Select
                  options={[
                    { value: 'draft', label: t('templateLibrary.draft') },
                    { value: 'developing', label: t('templateLibrary.developing') },
                    { value: 'testing', label: t('templateLibrary.testing') },
                    { value: 'published', label: t('templateLibrary.published') },
                    { value: 'deprecated', label: t('templateLibrary.deprecated') },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="version" label={t('templateLibrary.colVersion')}>
                <Input placeholder={t('templateLibrary.versionPlaceholder')} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="tags" label={t('templateLibrary.tagsCommaSeparated')}>
            <Input placeholder={t('templateLibrary.tagsPlaceholder')} />
          </Form.Item>
        </Form>
      </Modal>
      {/* @AI_GENERATED: end */}

      {/* @AI_GENERATED: Kiro v1.0 */}
      {/* 打包 Skill 弹窗 */}
      <Modal
        title={
          <Space>
            <ThunderboltOutlined />
            <span>{t('templateLibrary.packageModalTitle', { name: td(packageTemplate?.name) })}</span>
          </Space>
        }
        open={packageVisible}
        onCancel={() => {
          setPackageVisible(false);
          setPackageTemplate(null);
          setPackageStep(0);
        }}
        width={700}
        footer={[
          <Button key="cancel" onClick={() => setPackageVisible(false)}>{t('common.cancel')}</Button>,
          packageStep > 0 && (
            <Button key="prev" onClick={() => setPackageStep(s => s - 1)}>{t('templateLibrary.prevStep')}</Button>
          ),
          packageStep < 3 ? (
            <Button key="next" type="primary" onClick={() => setPackageStep(s => s + 1)}>{t('templateLibrary.nextStep')}</Button>
          ) : (
            <Button key="submit" type="primary" loading={packaging} onClick={handleSubmitPackage}>
              {t('templateLibrary.confirmPackage')}
            </Button>
          ),
        ]}
      >
        <Steps
          current={packageStep}
          size="small"
          style={{ marginBottom: 24 }}
          items={[
            { title: t('templateLibrary.packageStepBasic'), icon: <CodeOutlined /> },
            { title: t('templateLibrary.packageStepTrain'), icon: <ExperimentOutlined /> },
            { title: t('templateLibrary.packageStepResource'), icon: <SettingOutlined /> },
            { title: t('templateLibrary.packageStepConfirm'), icon: <CheckCircleOutlined /> },
          ]}
        />

        <Form form={packageForm} layout="vertical">
          {/* 步骤1: 基本信息 */}
          {packageStep === 0 && (
            <>
              <Alert
                message={t('templateLibrary.packageIntroAlert')}
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />
              <Form.Item
                name="skill_name"
                label={t('templateLibrary.skillName')}
                rules={[{ required: true, message: t('templateLibrary.skillNameRequired') }]}
              >
                <Input placeholder={t('templateLibrary.skillNamePlaceholder')} />
              </Form.Item>
              <Form.Item
                name="skill_version"
                label={t('templateLibrary.versionNumber')}
                rules={[{ required: true, message: t('templateLibrary.versionNumberRequired') }]}
              >
                <Input placeholder={t('templateLibrary.versionPlaceholder')} />
              </Form.Item>
              <Form.Item name="description" label={t('templateLibrary.descriptionLabel')}>
                <TextArea rows={3} placeholder={t('templateLibrary.skillDescriptionPlaceholder')} />
              </Form.Item>
            </>
          )}

          {/* 步骤2: 训练配置 */}
          {packageStep === 1 && (
            <>
              <Form.Item name="training_enabled" label={t('templateLibrary.enableTraining')}>
                <Select
                  options={[
                    { value: true, label: t('templateLibrary.trainingEnabledUserData') },
                    { value: false, label: t('templateLibrary.trainingEnabledInferenceOnly') },
                  ]}
                />
              </Form.Item>
              <Divider orientation="left">{t('templateLibrary.dividerTrainingParams')}</Divider>
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item name="min_samples" label={t('templateLibrary.minSamples')}>
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="default_epochs" label={t('templateLibrary.defaultEpochs')}>
                    <InputNumber min={1} max={1000} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="default_batch_size" label={t('templateLibrary.defaultBatchSize')}>
                    <InputNumber min={1} max={512} style={{ width: '100%' }} />
                  </Form.Item>
                </Col>
              </Row>
            </>
          )}

          {/* 步骤3: 资源配置 */}
          {packageStep === 2 && (
            <>
              <Divider orientation="left">{t('templateLibrary.dividerComputeResources')}</Divider>
              <Row gutter={16}>
                <Col span={8}>
                  <Form.Item name="cpu" label={t('templateLibrary.cpuCores')}>
                    <Select
                      options={['1', '2', '4', '8'].map((n) => ({
                        value: n,
                        label: t('templateLibrary.cpuCoreN', { n }),
                      }))}
                    />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="memory" label={t('templateLibrary.memory')}>
                    <Select
                      options={[
                        { value: '2Gi', label: '2 GB' },
                        { value: '4Gi', label: '4 GB' },
                        { value: '8Gi', label: '8 GB' },
                        { value: '16Gi', label: '16 GB' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col span={8}>
                  <Form.Item name="gpu" label={t('templateLibrary.gpuField')}>
                    <Select
                      options={[
                        { value: 'none', label: t('templateLibrary.gpuNone') },
                        { value: 'optional', label: t('templateLibrary.gpuOptional') },
                        { value: 'required', label: t('templateLibrary.gpuRequired') },
                      ]}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="timeout_seconds" label={t('templateLibrary.timeoutSeconds')}>
                <InputNumber min={60} max={3600} style={{ width: '100%' }} />
              </Form.Item>
            </>
          )}

          {/* 步骤4: 确认 */}
          {packageStep === 3 && (
            <>
              <Alert
                message={t('templateLibrary.confirmPackageSummary')}
                type="success"
                showIcon
                style={{ marginBottom: 16 }}
              />
              <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label={t('templateLibrary.skillName')}>
                  {packageForm.getFieldValue('skill_name')}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.colVersion')}>
                  {packageForm.getFieldValue('skill_version')}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.sourceTemplate')}>
                  {td(packageTemplate?.name)}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.templateVersion')}>
                  {packageTemplate?.version}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.enableTraining')}>
                  {packageForm.getFieldValue('training_enabled') ? t('templateLibrary.yes') : t('templateLibrary.no')}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.minSamples')}>
                  {packageForm.getFieldValue('min_samples')}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.cpuField')}>
                  {packageForm.getFieldValue('cpu')} {t('templateLibrary.cores')}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.memory')}>
                  {packageForm.getFieldValue('memory')}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.gpuField')}>
                  {(() => {
                    const g = packageForm.getFieldValue('gpu');
                    if (g === 'none') return t('templateLibrary.gpuValueNone');
                    if (g === 'optional') return t('templateLibrary.gpuValueOptional');
                    if (g === 'required') return t('templateLibrary.gpuValueRequired');
                    return g;
                  })()}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.timeoutSeconds')}>
                  {packageForm.getFieldValue('timeout_seconds')} {t('common.seconds')}
                </Descriptions.Item>
                <Descriptions.Item label={t('templateLibrary.descriptionLabel')} span={2}>
                  {td(packageForm.getFieldValue('description'))}
                </Descriptions.Item>
              </Descriptions>
            </>
          )}
        </Form>
      </Modal>
      {/* @AI_GENERATED: end */}
    </div>
  );
};

export default OfficialTemplateLibraryPage;
// @AI_GENERATED: end
