// @AI_GENERATED: Kiro v1.0
/**
 * Agent & Skill 开发状态页面
 * 三层结构：Master Agent → Sub Agent → Skills
 */
import { useState } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end
import {
  Card, Table, Tag, Progress, Tabs, Typography, Space, Row, Col,
  Statistic, Badge, Tooltip, Collapse,
} from 'antd';
import {
  RobotOutlined, ThunderboltOutlined, CheckCircleOutlined,
  ClockCircleOutlined, ExperimentOutlined, CodeOutlined,
  ApiOutlined, DatabaseOutlined, SearchOutlined,
  CloudUploadOutlined, SettingOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;
const { Panel } = Collapse;

type Status = 'completed' | 'dev-verified' | 'in-progress' | 'planned';

interface SkillInfo {
  id: string; name: string; description: string; endpoint: string;
  status: Status; progress: number; priority: 'P0' | 'P1' | 'P2'; estimatedWeeks: number;
}

interface SubAgentInfo {
  id: string; name: string; description: string; phase: string;
  skills: SkillInfo[]; overallProgress: number; status: Status; color?: string;
}

interface MasterAgentInfo {
  id: string; name: string; description: string;
  subAgents: SubAgentInfo[]; overallProgress: number; status: Status; color: string;
}

const MASTER_AGENTS: MasterAgentInfo[] = [
  {
    id: 'workflow-agent', name: 'Workflow Agent', color: '#1890ff',
    description: '算法模板智能编排智能体，负责行业场景匹配、算法组合、模板生成和业务验证',
    overallProgress: 85, status: 'in-progress',
    subAgents: [{
      id: 'workflow-core', name: 'Workflow Core Agent', phase: '编排 + 行业知识',
      description: '核心编排能力', overallProgress: 85, status: 'in-progress', color: '#1890ff',
      skills: [
        { id: 'scenario-match', name: '行业场景匹配', description: '根据业务描述匹配14个行业场景', endpoint: '/api/agent/workflow/scenario-match', status: 'dev-verified', progress: 100, priority: 'P0', estimatedWeeks: 1.5 },
        { id: 'algorithm-compose', name: '算法组合推荐', description: '根据场景推荐算法模块组合', endpoint: '/api/agent/workflow/algorithm-compose', status: 'dev-verified', progress: 100, priority: 'P0', estimatedWeeks: 2 },
        { id: 'workflow-generate', name: '工作流自动生成', description: '根据算法组合生成完整工作流', endpoint: '/api/agent/workflow/workflow-generate', status: 'dev-verified', progress: 100, priority: 'P0', estimatedWeeks: 2 },
        { id: 'workflow-validate', name: '工作流合理性验证', description: '结构验证+业务验证', endpoint: '/api/agent/workflow/workflow-validate', status: 'dev-verified', progress: 100, priority: 'P0', estimatedWeeks: 1 },
        { id: 'template-manage', name: '模板管理', description: '保存、版本控制、分享模板', endpoint: '/api/agent/workflow/template-manage', status: 'dev-verified', progress: 100, priority: 'P1', estimatedWeeks: 1.5 },
        { id: 'domain-constraint', name: '业务约束注入', description: '自动注入行业特定约束', endpoint: '/api/agent/workflow/domain-constraint', status: 'dev-verified', progress: 100, priority: 'P0', estimatedWeeks: 1.5 },
        { id: 'best-practice', name: '最佳实践推荐', description: '推荐同行业成功案例', endpoint: '/api/agent/workflow/best-practice', status: 'dev-verified', progress: 100, priority: 'P1', estimatedWeeks: 1.5 },
        { id: 'cross-scenario', name: '跨场景迁移', description: '将方案迁移到其他场景', endpoint: '/api/agent/workflow/cross-scenario', status: 'in-progress', progress: 60, priority: 'P2', estimatedWeeks: 2 },
      ],
    }],
  },
  {
    id: 'algorithm-agent', name: 'Algorithm Agent', color: '#4f46e5',
    description: '算法全生命周期管理，通过四种专业子 Agent 分阶段协作：策划→回测→上线→运营',
    overallProgress: 33, status: 'in-progress',
    subAgents: [
      {
        id: 'curator-agent', name: 'Curator Agent (算法策划)', phase: '策划阶段',
        description: '搜索AI解决方案库、推荐算法模板、分析数据需求、方案对比评估',
        overallProgress: 45, status: 'in-progress', color: '#4f46e5',
        skills: [
          { id: 'solution-search', name: '搜索解决方案', description: '根据业务场景搜索匹配的AI解决方案', endpoint: '/api/agent/algorithm/skills/solution-search', status: 'in-progress', progress: 70, priority: 'P0', estimatedWeeks: 2 },
          { id: 'template-recommend', name: '推荐算法模板', description: '基于场景关联性推荐最合适的算法模板', endpoint: '/api/agent/algorithm/skills/template-recommend', status: 'in-progress', progress: 60, priority: 'P0', estimatedWeeks: 1.5 },
          { id: 'data-requirement-analysis', name: '分析数据需求', description: '明确实现方案所需的数据集和特征', endpoint: '/api/agent/algorithm/skills/data-requirement', status: 'planned', progress: 0, priority: 'P1', estimatedWeeks: 1.5 },
          { id: 'solution-compare', name: '方案对比', description: '对比多种可行方案的优劣', endpoint: '/api/agent/algorithm/skills/solution-compare', status: 'planned', progress: 0, priority: 'P1', estimatedWeeks: 1.5 },
        ],
      },
      {
        id: 'sandbox-agent', name: 'Sandbox Agent (算法回测)', phase: '研发阶段',
        description: '引导数据集挂载、自动适配算法、执行模型训练、评估精度指标',
        overallProgress: 40, status: 'in-progress', color: '#059669',
        skills: [
          { id: 'data-mount', name: '引导数据挂载', description: '帮助用户正确挂载和配置数据集', endpoint: '/api/agent/algorithm/skills/data-mount', status: 'in-progress', progress: 50, priority: 'P0', estimatedWeeks: 1.5 },
          { id: 'algorithm-adapt', name: '自动适配算法', description: '根据数据特征自动适配算法模板', endpoint: '/api/agent/algorithm/skills/algorithm-adapt', status: 'in-progress', progress: 60, priority: 'P0', estimatedWeeks: 2 },
          { id: 'model-training', name: '执行模型训练', description: '配置参数并执行训练流程', endpoint: '/api/agent/algorithm/skills/training-pipeline', status: 'in-progress', progress: 80, priority: 'P0', estimatedWeeks: 2 },
          { id: 'accuracy-evaluate', name: '评估精度指标', description: '展示训练集、验证集、测试集的精度', endpoint: '/api/agent/algorithm/skills/accuracy-evaluate', status: 'planned', progress: 0, priority: 'P0', estimatedWeeks: 1.5 },
        ],
      },
      {
        id: 'onboarding-agent', name: 'Onboarding Agent (算法上线)', phase: '上线阶段',
        description: '算法服务上线、配置定期训练、部署推理API、监控服务状态',
        overallProgress: 10, status: 'in-progress', color: '#d97706',
        skills: [
          { id: 'service-deploy', name: '算法服务上线', description: '将模型部署为生产级推理服务', endpoint: '/api/agent/algorithm/skills/service-deploy', status: 'planned', progress: 0, priority: 'P0', estimatedWeeks: 2 },
          { id: 'periodic-training-config', name: '配置定期训练', description: '设置自动重训计划', endpoint: '/api/agent/algorithm/skills/periodic-training', status: 'planned', progress: 0, priority: 'P1', estimatedWeeks: 1.5 },
          { id: 'inference-api-deploy', name: '部署推理API', description: '提供REST API或批量预测服务', endpoint: '/api/agent/algorithm/skills/inference-api', status: 'planned', progress: 0, priority: 'P0', estimatedWeeks: 2 },
          { id: 'service-monitor', name: '监控服务状态', description: '跟踪服务健康和性能', endpoint: '/api/agent/algorithm/skills/service-monitor', status: 'in-progress', progress: 40, priority: 'P1', estimatedWeeks: 1.5 },
        ],
      },
      {
        id: 'operation-agent', name: 'Operation Master (算法运营)', phase: '运营阶段',
        description: '精度漂移检测、根因分析、自动模型选择、重训和调优',
        overallProgress: 35, status: 'in-progress', color: '#dc2626',
        skills: [
          { id: 'drift-detect', name: '精度漂移检测', description: '数据漂移+概念漂移监控 (PSI/KS检验)', endpoint: '/api/agent/algorithm/skills/drift-detect', status: 'in-progress', progress: 50, priority: 'P0', estimatedWeeks: 2 },
          { id: 'root-cause-analysis', name: '根因分析', description: '定位精度下降的根本原因', endpoint: '/api/agent/algorithm/skills/root-cause', status: 'planned', progress: 0, priority: 'P0', estimatedWeeks: 2 },
          { id: 'auto-model-select', name: '自动模型选择', description: '评估并选择最优模型', endpoint: '/api/agent/algorithm/skills/auto-model-select', status: 'in-progress', progress: 40, priority: 'P1', estimatedWeeks: 2 },
          { id: 'retrain-optimize', name: '重训和调优', description: '自动触发重训并优化参数', endpoint: '/api/agent/algorithm/skills/retrain-optimize', status: 'in-progress', progress: 30, priority: 'P0', estimatedWeeks: 1.5 },
        ],
      },
    ],
  },
];

const TEMPLATE_SKILLS: SkillInfo[] = [
  { id: 'pv-power-forecast', name: '光伏发电功率预测', description: '基于LSTM的日前光伏发电功率预测', endpoint: '/api/skills/pv-power-forecast', status: 'dev-verified', progress: 100, priority: 'P0', estimatedWeeks: 2 },
  { id: 'wind-power-forecast', name: '风电功率预测', description: '基于XGBoost Stacking的风电预测', endpoint: '/api/skills/wind-power-forecast', status: 'in-progress', progress: 40, priority: 'P1', estimatedWeeks: 2 },
  { id: 'load-forecast', name: '电网负荷预测', description: '考虑天气、节假日的负荷预测', endpoint: '/api/skills/load-forecast', status: 'planned', progress: 0, priority: 'P1', estimatedWeeks: 2 },
  { id: 'battery-soh', name: '电池健康度评估', description: '储能电池SOH预测', endpoint: '/api/skills/battery-soh', status: 'planned', progress: 0, priority: 'P2', estimatedWeeks: 2.5 },
  { id: 'fault-diagnosis', name: '设备故障诊断', description: '基于振动信号的故障诊断', endpoint: '/api/skills/fault-diagnosis', status: 'planned', progress: 0, priority: 'P2', estimatedWeeks: 2.5 },
];

const AGENT_ICONS: Record<string, React.ReactNode> = {
  'workflow-agent': <ApiOutlined />, 'algorithm-agent': <ExperimentOutlined />,
  'workflow-core': <ApiOutlined />,
  'curator-agent': <SearchOutlined />, 'sandbox-agent': <ExperimentOutlined />,
  'onboarding-agent': <CloudUploadOutlined />, 'operation-agent': <SettingOutlined />,
};

const AgentSkillStatusPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [activeTab, setActiveTab] = useState('overview');

  const getMasterName = (id: string, fallback: string) =>
    t(`agentSkillStatus.masterNames.${id}`, { defaultValue: fallback });
  const getSubAgentName = (id: string, fallback: string) =>
    t(`agentSkillStatus.subAgentNames.${id}`, { defaultValue: fallback });
  const getSubAgentPhase = (id: string, fallback: string) =>
    t(`agentSkillStatus.subAgentPhases.${id}`, { defaultValue: fallback });

  const allSubAgents = MASTER_AGENTS.flatMap(m => m.subAgents);
  const allSkills = [...allSubAgents.flatMap(s => s.skills), ...TEMPLATE_SKILLS];
  const totalSkills = allSkills.length;
  const devVerified = allSkills.filter(s => s.status === 'dev-verified').length;
  const inProgress = allSkills.filter(s => s.status === 'in-progress').length;

  const getStatusTag = (status: string) => {
    switch (status) {
      case 'completed': return <Tag color="success" icon={<CheckCircleOutlined />}>{t('agentSkillStatus.statusCompleted')}</Tag>;
      case 'dev-verified': return <Tag color="cyan" icon={<CheckCircleOutlined />}>{t('agentSkillStatus.statusDevVerified')}</Tag>;
      case 'in-progress': return <Tag color="processing" icon={<ClockCircleOutlined />}>{t('agentSkillStatus.statusInProgress')}</Tag>;
      case 'planned': return <Tag color="default" icon={<ExperimentOutlined />}>{t('agentSkillStatus.statusPlanned')}</Tag>;
      default: return <Tag>{status}</Tag>;
    }
  };

  const getPriorityTag = (p: string) => {
    const c: Record<string, string> = { P0: 'red', P1: 'orange', P2: 'blue' };
    return <Tag color={c[p]}>{p}</Tag>;
  };

  const skillCols: ColumnsType<SkillInfo> = [
    { title: t('agentSkillStatus.skillId'), dataIndex: 'id', key: 'id', width: 180, render: (id: string) => <Text code style={{ fontSize: 12 }}>{id}</Text> },
    // @AI_GENERATED
    { title: t('agentSkillStatus.name'), dataIndex: 'name', key: 'name', width: 150, render: (name: string) => td(name) },
    { title: t('agentSkillStatus.descriptionCol'), dataIndex: 'description', key: 'description', ellipsis: true, render: (desc: string) => td(desc) },
    // @AI_GENERATED: end
    { title: t('agentSkillStatus.apiCol'), dataIndex: 'endpoint', key: 'endpoint', width: 300, render: (e: string) => <Text code style={{ fontSize: 11 }}>{e}</Text> },
    { title: t('agentSkillStatus.priority'), dataIndex: 'priority', key: 'priority', width: 80, render: (p: string) => getPriorityTag(p) },
    { title: t('agentSkillStatus.statusCol'), dataIndex: 'status', key: 'status', width: 110, render: (s: string) => getStatusTag(s) },
    { title: t('agentSkillStatus.progressCol'), dataIndex: 'progress', key: 'progress', width: 120, render: (p: number, r: SkillInfo) => (
      <Progress percent={p} size="small" status={p === 100 ? 'success' : 'active'} strokeColor={r.status === 'completed' ? '#52c41a' : r.status === 'dev-verified' ? '#13c2c2' : '#1890ff'} />
    )},
    { title: t('agentSkillStatus.estimate'), dataIndex: 'estimatedWeeks', key: 'estimatedWeeks', width: 70, render: (w: number) => <Text type="secondary">{w}{t('agentSkillStatus.weeks')}</Text> },
  ];

  return (
    <div style={{ padding: 24, background: '#f5f5f5', minHeight: '100%' }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0 }}>{t('agentSkillStatus.title')}</Title>
        <Text type="secondary">{t('agentSkillStatus.subtitle')}</Text>
      </div>

      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={4}><Card><Statistic title={t('agentSkillStatus.masterAgent')} value={MASTER_AGENTS.length} prefix={<RobotOutlined style={{ color: '#1890ff' }} />} suffix={t('agentSkillStatus.unit')} /></Card></Col>
        <Col span={4}><Card><Statistic title={t('agentSkillStatus.subAgent')} value={allSubAgents.length} prefix={<RobotOutlined style={{ color: '#722ed1' }} />} suffix={t('agentSkillStatus.unit')} /></Card></Col>
        <Col span={4}><Card><Statistic title={t('agentSkillStatus.skillTotal')} value={totalSkills} prefix={<ThunderboltOutlined style={{ color: '#722ed1' }} />} suffix={t('agentSkillStatus.unit')} /></Card></Col>
        <Col span={4}><Card><Statistic title={t('agentSkillStatus.devVerified')} value={devVerified} prefix={<CheckCircleOutlined style={{ color: '#13c2c2' }} />} suffix={t('agentSkillStatus.unit')} /></Card></Col>
        <Col span={4}><Card><Statistic title={t('agentSkillStatus.inProgress')} value={inProgress} prefix={<ClockCircleOutlined style={{ color: '#faad14' }} />} suffix={t('agentSkillStatus.unit')} /></Card></Col>
        <Col span={4}><Card><Statistic title={t('agentSkillStatus.algorithmOverall')} value={MASTER_AGENTS.find(m=>m.id==='algorithm-agent')?.overallProgress||0} prefix={<DatabaseOutlined style={{ color: '#4f46e5' }} />} suffix="%" /></Card></Col>
      </Row>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<span><RobotOutlined /> {t('agentSkillStatus.overview')}</span>} key="overview">
          {MASTER_AGENTS.map(master => (
            <Card key={master.id} style={{ marginBottom: 16, borderLeft: `4px solid ${master.color}` }}
              title={<Space><Badge status={master.status === 'completed' ? 'success' : 'processing'} /><span style={{ fontSize: 16, fontWeight: 600 }}>{getMasterName(master.id, master.name)}</span>{getStatusTag(master.status)}<Tag color="purple">{t('agentSkillStatus.subAgentsCount', { count: master.subAgents.length })}</Tag></Space>}>
              <Paragraph type="secondary">{td(master.description)}</Paragraph>
              <Progress percent={master.overallProgress} strokeColor={master.color} style={{ marginBottom: 16 }} />
              <Row gutter={16}>
                {master.subAgents.map(sub => (
                  <Col span={6} key={sub.id}>
                    <Card size="small" style={{ borderTop: `3px solid ${sub.color}` }}
                      title={<Space size={4}>{AGENT_ICONS[sub.id]}<span style={{ fontSize: 13 }}>{getSubAgentName(sub.id, sub.name)}</span></Space>}>
                      <div style={{ marginBottom: 8 }}><Tag color="blue">{getSubAgentPhase(sub.id, sub.phase)}</Tag>{getStatusTag(sub.status)}</div>
                      <Progress percent={sub.overallProgress} size="small" strokeColor={sub.color} />
                      <Text type="secondary" style={{ fontSize: 12 }}>{t('agentSkillStatus.skillsCount', { count: sub.skills.length })}</Text>
                      <div style={{ marginTop: 4 }}>
                        <Space wrap size={4}>
                          {sub.skills.map(sk => (
                            <Tooltip key={sk.id} title={`${td(sk.name)}: ${sk.progress}%`}>
                              <Tag color={sk.status === 'dev-verified' ? 'cyan' : sk.status === 'in-progress' ? 'processing' : sk.status === 'completed' ? 'success' : 'default'} style={{ cursor: 'pointer', fontSize: 11 }}>{sk.id}</Tag>
                            </Tooltip>
                          ))}
                        </Space>
                      </div>
                    </Card>
                  </Col>
                ))}
              </Row>
            </Card>
          ))}
          {/* @AI_GENERATED */}
          <Card title={<Space><CodeOutlined /><span>{t('agentSkillStatus.templateSkills')}</span><Tag color="purple">{t('agentSkillStatus.templateSkillsCount', { count: TEMPLATE_SKILLS.length })}</Tag></Space>}>
            {/* @AI_GENERATED: end */}            <Space wrap>
              {TEMPLATE_SKILLS.map(sk => (
                <Card key={sk.id} size="small" style={{ width: 200 }}>
                  <Text strong>{td(sk.name)}</Text>
                  <div style={{ margin: '8px 0' }}>{getStatusTag(sk.status)}{getPriorityTag(sk.priority)}</div>
                  <Progress percent={sk.progress} size="small" />
                </Card>
              ))}
            </Space>
          </Card>
        </TabPane>

        {MASTER_AGENTS.map(master => (
          <TabPane key={master.id} tab={<span>{AGENT_ICONS[master.id]} {getMasterName(master.id, master.name)}</span>}>
            <Card>
              <Title level={4}>{getMasterName(master.id, master.name)}</Title>
              {/* @AI_GENERATED */}
              <Paragraph type="secondary">
                {t('agentSkillStatus.masterSummary', {
                  description: td(master.description),
                  subAgents: master.subAgents.length,
                  skills: master.subAgents.reduce((s,a)=>s+a.skills.length,0),
                })}
              </Paragraph>
              {/* @AI_GENERATED: end */}
              <Collapse defaultActiveKey={master.subAgents.map(s=>s.id)}>
                {master.subAgents.map(sub => (
                  <Panel key={sub.id} header={
                    <Space>{AGENT_ICONS[sub.id]}<span style={{ color: sub.color, fontWeight: 600 }}>{getSubAgentName(sub.id, sub.name)}</span><Tag color="blue">{getSubAgentPhase(sub.id, sub.phase)}</Tag><Text type="secondary">({t('agentSkillStatus.skillsCountCompact', { count: sub.skills.length })})</Text><Progress percent={sub.overallProgress} size="small" style={{ width: 100 }} strokeColor={sub.color} /></Space>
                  }>
                    <Table columns={skillCols} dataSource={sub.skills} rowKey="id" pagination={false} size="small" />
                  </Panel>
                ))}
              </Collapse>
            </Card>
          </TabPane>
        ))}

        <TabPane tab={<span><ThunderboltOutlined /> {t('agentSkillStatus.templateSkills')}</span>} key="template-skills">
          <Card>
            <Title level={4}>{t('agentSkillStatus.templateSkills')}</Title>
            <Paragraph type="secondary">{t('agentSkillStatus.templateSkillsDesc')}</Paragraph>
            <Table columns={skillCols} dataSource={TEMPLATE_SKILLS} rowKey="id" pagination={false} size="small" />
          </Card>
        </TabPane>
      </Tabs>
    </div>
  );
};

export default AgentSkillStatusPage;
// @AI_GENERATED: end
