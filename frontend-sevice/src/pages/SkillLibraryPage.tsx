// @AI_GENERATED: Kiro v1.0
/**
 * Skill 库页面
 * 展示所有已打包的算法模板 Skills，支持查看、训练、部署、删除等操作
 */
import { useState, useEffect, useMemo } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { useNavigate } from 'react-router-dom';
import {
  Card, Table, Space, Typography, Tag, Row, Col, Statistic, Input, Select,
  Button, Tooltip, Empty, Spin, message, Popconfirm,
} from 'antd';
import {
  ThunderboltOutlined, SearchOutlined, CheckCircleOutlined, SyncOutlined,
  ClockCircleOutlined, DeleteOutlined, EyeOutlined,
  PlayCircleOutlined, CodeOutlined,
  RocketOutlined, CloudServerOutlined, ReloadOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { templateSkillApi, type PackagedSkill } from '../services/templateSkillApi';

const { Text, Paragraph } = Typography;

// Skill 状态配置
type SkillStatus = 'packaged' | 'training' | 'ready' | 'deployed' | 'deprecated';

// @AI_GENERATED
const STATUS_CONFIG: Record<SkillStatus, { labelKey: string; color: string; icon: React.ReactNode }> = {
  packaged: { labelKey: 'skillLibrary.packaged', color: 'default', icon: <CodeOutlined /> },
  training: { labelKey: 'skillLibrary.training', color: 'processing', icon: <SyncOutlined spin /> },
  ready: { labelKey: 'skillLibrary.ready', color: 'success', icon: <CheckCircleOutlined /> },
  deployed: { labelKey: 'skillLibrary.deployed', color: 'blue', icon: <CloudServerOutlined /> },
  deprecated: { labelKey: 'skillLibrary.deprecated', color: 'error', icon: <ClockCircleOutlined /> },
};
// @AI_GENERATED: end

const SkillLibraryPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [skills, setSkills] = useState<PackagedSkill[]>([]);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<SkillStatus | 'all'>('all');

  // 加载 Skills 数据
  const loadSkills = async () => {
    setLoading(true);
    try {
      const response = await templateSkillApi.listSkills();
      setSkills(response.skills);
    } catch (error) {
      message.error(t('skillLibrary.loadFailed'));
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSkills();
  }, []);

  // 统计数据
  const stats = useMemo(() => {
    const total = skills.length;
    const packaged = skills.filter(s => s.status === 'packaged').length;
    const ready = skills.filter(s => s.status === 'ready').length;
    const deployed = skills.filter(s => s.status === 'deployed').length;
    const training = skills.filter(s => s.status === 'training').length;
    return { total, packaged, ready, deployed, training };
  }, [skills]);

  // 过滤后的 Skills
  const filteredSkills = useMemo(() => {
    return skills.filter(s => {
      if (keyword && !s.skill_name.toLowerCase().includes(keyword.toLowerCase()) &&
          !s.description?.toLowerCase().includes(keyword.toLowerCase())) {
        return false;
      }
      if (statusFilter !== 'all' && s.status !== statusFilter) return false;
      return true;
    });
  }, [skills, keyword, statusFilter]);

  // 查看详情
  const handleViewDetail = (skill: PackagedSkill) => {
    navigate(`/skill-library/${skill.skill_id}`);
  };

  // 删除 Skill
  const handleDelete = async (skillId: string) => {
    try {
      await templateSkillApi.deleteSkill(skillId);
      message.success(t('skillLibrary.deleteSuccess'));
      loadSkills();
    } catch (error) {
      message.error(t('skillLibrary.deleteFailed'));
    }
  };

  // 开始训练
  const handleStartTraining = (skill: PackagedSkill) => {
    message.info(t('skillLibrary.startTraining', { name: skill.skill_name }));
    // TODO: 实现训练逻辑
  };

  // 部署 Skill
  const handleDeploy = (skill: PackagedSkill) => {
    message.info(t('skillLibrary.deploying', { name: skill.skill_name }));
    // TODO: 实现部署逻辑
  };

  // 查看源模板
  const handleViewTemplate = (templateId: string) => {
    if (templateId === 'tpl-pv-power-001') {
      navigate('/workflow/editor/workflow-pv-power-demo');
    } else {
      navigate(`/algorithm/templates?id=${templateId}`);
    }
  };

  const columns: ColumnsType<PackagedSkill> = [
    {
      title: t('skillLibrary.skillName'),
      dataIndex: 'skill_name',
      key: 'skill_name',
      width: 280,
      render: (name, record) => (
        <Space direction="vertical" size={2}>
          <Space>
            <ThunderboltOutlined style={{ color: '#722ed1' }} />
            <Text strong style={{ cursor: 'pointer' }} onClick={() => handleViewDetail(record)}>
              {name}
            </Text>
          </Space>
          <Text type="secondary" style={{ fontSize: 12 }} ellipsis>
            {record.description || t('skillLibrary.noDescription')}
          </Text>
        </Space>
      ),
    },
    {
      title: t('skillLibrary.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: SkillStatus) => {
        const config = STATUS_CONFIG[status] || STATUS_CONFIG.packaged;
        return (
          <Tag color={config.color} icon={config.icon}>
            {t(config.labelKey)}
          </Tag>
        );
      },
    },
    {
      title: t('skillLibrary.version'),
      dataIndex: 'skill_version',
      key: 'version',
      width: 80,
      render: (v) => <Text code>v{v}</Text>,
    },
    {
      title: t('skillLibrary.sourceTemplate'),
      key: 'source',
      width: 200,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text
            style={{ cursor: 'pointer', color: '#1890ff' }}
            onClick={() => handleViewTemplate(record.source_template_id)}
          >
            {record.source_template_name}
          </Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {record.source_template_version}
          </Text>
        </Space>
      ),
    },
    {
      title: t('skillLibrary.trainingConfig'),
      key: 'training',
      width: 150,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>
            {record.training_config.enabled ? t('skillLibrary.supportsTraining') : t('skillLibrary.inferenceOnly')}
          </Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            Epochs: {record.training_config.default_epochs}
          </Text>
        </Space>
      ),
    },
    {
      title: t('skillLibrary.resourceConfig'),
      key: 'resource',
      width: 120,
      render: (_, record) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>CPU: {record.resource_config.cpu}</Text>
          <Text style={{ fontSize: 12 }}>{t('skillLibrary.memory')}: {record.resource_config.memory}</Text>
        </Space>
      ),
    },
    {
      title: t('skillLibrary.createdAt'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (time) => new Date(time).toLocaleString('zh-CN'),
    },
    {
      title: t('skillLibrary.actions'),
      key: 'actions',
      width: 200,
      render: (_, record) => (
        <Space size={4}>
          <Tooltip title={t('skillLibrary.viewDetail')}>
            <Button type="text" size="small" icon={<EyeOutlined />} onClick={() => handleViewDetail(record)} />
          </Tooltip>
          {record.training_config.enabled && record.status === 'packaged' && (
            <Tooltip title={t('skillLibrary.startTrainingBtn')}>
              <Button type="text" size="small" icon={<PlayCircleOutlined />} onClick={() => handleStartTraining(record)} />
            </Tooltip>
          )}
          {record.status === 'ready' && (
            <Tooltip title={t('skillLibrary.deploy')}>
              <Button type="primary" size="small" icon={<RocketOutlined />} onClick={() => handleDeploy(record)}>
                部署
              </Button>
            </Tooltip>
          )}
          <Popconfirm
            title={t('skillLibrary.confirmDelete')}
            onConfirm={() => handleDelete(record.skill_id)}
            okText={t('common.confirm')}
            cancelText={t('common.cancel')}
          >
            <Tooltip title={t('skillLibrary.delete')}>
              <Button type="text" size="small" danger icon={<DeleteOutlined />} />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <ThunderboltOutlined style={{ fontSize: 24, color: '#722ed1' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>{t('skillLibrary.title')}</Typography.Title>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          管理已打包的算法模板 Skills，支持训练、部署和版本管理
        </Paragraph>
      </div>

      {/* 统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={5}>
          <Card size="small">
            <Statistic title={t('skillLibrary.totalSkills')} value={stats.total} prefix={<ThunderboltOutlined />} />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic
              title={t('skillLibrary.packagedCount')}
              value={stats.packaged}
              prefix={<CodeOutlined style={{ color: '#8c8c8c' }} />}
            />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic
              title={t('skillLibrary.readyCount')}
              value={stats.ready}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col span={5}>
          <Card size="small">
            <Statistic
              title={t('skillLibrary.deployedCount')}
              value={stats.deployed}
              prefix={<CloudServerOutlined style={{ color: '#1890ff' }} />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col span={4}>
          <Card size="small">
            <Statistic
              title={t('skillLibrary.trainingCount')}
              value={stats.training}
              prefix={<SyncOutlined spin style={{ color: '#faad14' }} />}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 筛选栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            prefix={<SearchOutlined />}
            placeholder={t('skillLibrary.searchPlaceholder')}
            allowClear
            style={{ width: 250 }}
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
          />
          <Select
            style={{ width: 120 }}
            placeholder={t('skillLibrary.statusFilter')}
            allowClear
            value={statusFilter === 'all' ? undefined : statusFilter}
            onChange={v => setStatusFilter(v || 'all')}
            options={[
              { value: 'packaged', label: '已打包' },
              { value: 'training', label: '训练中' },
              { value: 'ready', label: '就绪' },
              { value: 'deployed', label: '已部署' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={loadSkills}>
            刷新
          </Button>
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={() => navigate('/template-library')}>
            打包新 Skill
          </Button>
        </Space>
      </Card>

      {/* Skills 列表 */}
      <Card>
        <Spin spinning={loading}>
          {filteredSkills.length > 0 ? (
            <Table
              dataSource={filteredSkills}
              columns={columns}
              rowKey="skill_id"
              size="small"
              pagination={{ pageSize: 10, showTotal: total => t('skillLibrary.totalCount', { count: total }) }}
            />
          ) : (
            <Empty
              description={
                <span>
                  暂无 Skills，
                  <a onClick={() => navigate('/template-library')}>{t('skillLibrary.goPackage')}</a>
                </span>
              }
            />
          )}
        </Spin>
      </Card>
    </div>
  );
};

export default SkillLibraryPage;
// @AI_GENERATED: end
