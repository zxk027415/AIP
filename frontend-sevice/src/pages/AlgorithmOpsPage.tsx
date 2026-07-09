// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useRef, useCallback } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
// @AI_GENERATED: end
import {
  Card, Row, Col, Statistic, Table, Tag, Space, Input, Button, Tabs,
  Select, Typography, message, Spin, Badge, Avatar, List, Tooltip, Popover, Switch,
} from 'antd';
import {
  PlusOutlined,
  CheckCircleOutlined,
  RobotOutlined, ThunderboltOutlined,
  LineChartOutlined, WarningOutlined, ExclamationCircleOutlined,
  UserOutlined, ReloadOutlined,
  AppstoreOutlined, PaperClipOutlined,
  CalendarOutlined, AimOutlined, SettingOutlined, BulbOutlined,
  DatabaseOutlined, FileTextOutlined, RocketOutlined, SendOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type {
  ModelDriftInfo, DriftMonitorStats, QuickCommand,
} from '../types/algorithm-ops';
import { DRIFT_STATUS_CONFIG } from '../types/algorithm-ops';
import { opsPromptApi } from '../services/algorithmOpsApi';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
import i18n from '../i18n';
// @AI_GENERATED: end

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

// @AI_GENERATED
// ============ Mock 数据（仅漂移监控 + 归因分析）============
// 说明：算法运营页面本轮改造后，仅承担「精度指标时序图」与「归因分析结果展示」两类只读视图，
// 调度任务管理、A/B 测试配置、自动重训触发入口已全部迁往「算法部署」页面。
const MOCK_DRIFT_STATS: DriftMonitorStats = {
  total_models: 45,
  normal_count: 32,
  mild_drift_count: 8,
  severe_drift_count: 5,
  retrain_triggered: 0, // 保留字段以兼容类型，页面不再展示重训计数
};

const MOCK_MODELS: ModelDriftInfo[] = [
  { model_id: 'pv-power-001', model_name: '光伏功率预测-LSTM', scenario_id: 'renewable-energy', scenario_name: '新能源发电', status: 'severe', drift_type: 'both', psi_score: 0.35, accuracy_change: -12.5, last_check_time: '2026-03-21 10:30:00', alert_triggered: true },
  { model_id: 'wind-power-001', model_name: '风电功率预测-XGBoost', scenario_id: 'renewable-energy', scenario_name: '新能源发电', status: 'mild', drift_type: 'data', psi_score: 0.18, accuracy_change: -5.2, last_check_time: '2026-03-21 10:25:00', alert_triggered: false },
  { model_id: 'load-forecast-001', model_name: '负荷预测-Transformer', scenario_id: 'power-grid', scenario_name: '电网与微网', status: 'severe', drift_type: 'concept', psi_score: 0.28, accuracy_change: -15.8, last_check_time: '2026-03-21 10:15:00', alert_triggered: true },
  { model_id: 'defect-detect-001', model_name: '晶圆缺陷检测-YOLO', scenario_id: 'semiconductor', scenario_name: '半导体制造', status: 'mild', drift_type: 'data', psi_score: 0.15, accuracy_change: -3.8, last_check_time: '2026-03-21 10:10:00', alert_triggered: false },
  { model_id: 'quality-pred-001', model_name: '质量预测-RF', scenario_id: 'steel-manufacturing', scenario_name: '钢铁制造', status: 'normal', drift_type: 'data', psi_score: 0.05, accuracy_change: 0.5, last_check_time: '2026-03-21 10:05:00', alert_triggered: false },
];

// AI 助手快捷指令 — 仅保留精度诊断与运营报告类，移除 A/B、重训相关指令
const QUICK_COMMANDS: QuickCommand[] = [
  { label: 'algorithmOps.quickDiagnoseAll', prompt: 'algorithmOps.quickPromptDiagnoseAll' },
  { label: 'algorithmOps.quickWeeklyReport', prompt: 'algorithmOps.quickPromptWeeklyReport' },
];

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface ChatSession {
  id: string;
  title: string;
  timestamp: string;
  messageCount: number;
}

interface Skill {
  id: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  enabled: boolean;
}

// 可用技能列表 — 仅保留漂移诊断/归因分析/数据质量/报告生成，移除 A/B 与重训评估技能
const AVAILABLE_SKILLS_DATA = [
  { id: 'drift-detect', nameKey: 'algorithmOps.driftDetect', descKey: 'algorithmOps.driftDetectDesc', icon: <WarningOutlined />, enabled: true },
  { id: 'root-cause', nameKey: 'algorithmOps.rootCauseAnalysis', descKey: 'algorithmOps.rootCauseDesc', icon: <BulbOutlined />, enabled: true },
  { id: 'data-quality', nameKey: 'algorithmOps.dataQuality', descKey: 'algorithmOps.dataQualityDesc', icon: <DatabaseOutlined />, enabled: false },
  { id: 'report-gen', nameKey: 'algorithmOps.reportGen', descKey: 'algorithmOps.reportGenDesc', icon: <FileTextOutlined />, enabled: true },
];

// 历史会话 Mock — 仅保留漂移诊断与运营周报相关会话
const MOCK_SESSIONS: ChatSession[] = [
  { id: 's1', title: '光伏模型漂移诊断', timestamp: '今天 10:30', messageCount: 8 },
  { id: 's2', title: '本周运营周报', timestamp: '昨天 17:00', messageCount: 12 },
];
// @AI_GENERATED: end

// @AI_GENERATED
const AlgorithmOpsPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);
  const [promptText, setPromptText] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { id: '1', role: 'assistant', content: t('algorithmOps.greeting'), timestamp: '10:00' },
  ]);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [showHistoryList, setShowHistoryList] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [showAIPanel, setShowAIPanel] = useState(true);
  const [skills, setSkills] = useState<Skill[]>(() =>
    AVAILABLE_SKILLS_DATA.map(s => ({ ...s, name: s.nameKey, description: s.descKey })),
  );
  const [selectedModel, setSelectedModel] = useState<string | undefined>();
  const [selectedTimeRange, setSelectedTimeRange] = useState<string>('7d');
  const [selectedScenario, setSelectedScenario] = useState<string | undefined>();
  const [rightPanelWidth, setRightPanelWidth] = useState(480);
  const [isResizing, setIsResizing] = useState(false);
  const [examplePopoverOpen, setExamplePopoverOpen] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const formatChatTime = useCallback(
    (date: Date = new Date()) => date.toLocaleTimeString(
      (i18n.language || '').toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN',
      { hour: '2-digit', minute: '2-digit' },
    ),
    [],
  );

  // 拖拽调整 AI 面板宽度
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      const newWidth = window.innerWidth - e.clientX;
      setRightPanelWidth(Math.min(800, Math.max(320, newWidth)));
    };
    const handleMouseUp = () => setIsResizing(false);

    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isResizing]);

  useEffect(() => {
    setLoading(true);
    const timer = window.setTimeout(() => setLoading(false), 300);
    return () => window.clearTimeout(timer);
  }, [statusFilter]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, promptText]);

  useEffect(() => {
    setChatMessages(prev => {
      const hasUserMessages = prev.some(msg => msg.role === 'user');
      if (hasUserMessages || prev.length === 0) return prev;

      const firstAssistantIndex = prev.findIndex(msg => msg.role === 'assistant');
      if (firstAssistantIndex < 0) return prev;

      const next = [...prev];
      next[firstAssistantIndex] = {
        ...next[firstAssistantIndex],
        content: t('algorithmOps.greeting'),
      };
      return next;
    });
  }, [t, i18n.language]);

  const generateAIResponse = (prompt: string): string => {
    const lowerPrompt = prompt.toLowerCase();
    const isDriftPrompt = prompt.includes('漂移')
      || prompt.includes('诊断')
      || lowerPrompt.includes('drift')
      || lowerPrompt.includes('diagnos');
    const isWeeklyReportPrompt = prompt.includes('周报')
      || prompt.includes('报告')
      || lowerPrompt.includes('report')
      || lowerPrompt.includes('weekly');

    if (isDriftPrompt) {
      return td('已完成模型漂移诊断：\n\n🔴 严重漂移 (2个):\n- 光伏功率预测-LSTM: PSI=0.35, 精度下降12.5%\n- 负荷预测-Transformer: PSI=0.28, 精度下降15.8%\n\n🟡 轻度漂移 (2个):\n- 风电功率预测-XGBoost\n- 缺陷检测-YOLO\n\n建议：前往「算法部署」页面进行影子模型切换或触发新一轮训练。');
    }
    if (isWeeklyReportPrompt) {
      const weeklyReport = i18n.language === 'en'
        ? '📊 Weekly Algorithm Operations Report\n\n【Drift Monitoring】\n- Monitored models: 45\n- New drift: 5 (2 severe, 3 mild)\n- Fixed: 3\n\nRecommendation: Handle drift issues on PV and load forecast models via the Algorithm Deployment page.'
        : '📊 本周算法运营周报\n\n【漂移监控】\n- 监控模型: 45个\n- 新增漂移: 5个 (严重2, 轻度3)\n- 已修复: 3个\n\n建议：前往「算法部署」页面处理光伏和负荷预测模型的漂移问题。';
      return weeklyReport;
    }
    return td('收到您的请求，正在分析中...\n\n我可以帮您：\n1. 诊断模型漂移状态\n2. 生成运营/精度分析报告\n\n如需切换模型、调度重训或配置数据管线，请前往「算法部署」页面。');
  };

  const handlePromptSubmit = async () => {
    if (!promptText.trim()) return;
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: promptText,
      timestamp: formatChatTime(),
    };
    setChatMessages(prev => [...prev, userMsg]);
    const currentPrompt = promptText;
    setPromptText('');
    setPromptLoading(true);

    try {
      const response = await opsPromptApi.executePrompt({
        prompt: currentPrompt,
        context: { language: i18n.language },
        model_id: selectedModel,
        scenario_id: selectedScenario,
        time_range: selectedTimeRange,
        enabled_skills: skills.filter(s => s.enabled).map(s => s.id),
      });

      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: td(response.response),
        timestamp: formatChatTime(),
      };
      setChatMessages(prev => [...prev, aiMsg]);
    } catch (error) {
      console.error('Prompt execution failed:', error);
      const fallbackResponse = generateAIResponse(currentPrompt);
      const aiMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: fallbackResponse,
        timestamp: formatChatTime(),
      };
      setChatMessages(prev => [...prev, aiMsg]);
      message.warning(t('algorithmOps.aiServiceUnavailable'));
    } finally {
      setPromptLoading(false);
    }
  };

  const handleNewSession = () => {
    setChatMessages([
      { id: Date.now().toString(), role: 'assistant', content: t('algorithmOps.newSessionMsg'), timestamp: formatChatTime() },
    ]);
    setCurrentSessionId(null);
    setShowHistoryList(false);
    message.success(t('algorithmOps.newSessionCreated'));
  };

  const handleLoadSession = (session: ChatSession) => {
    const mockMessages: ChatMessage[] = [
      { id: '1', role: 'user', content: td(session.title), timestamp: session.timestamp.split(' ')[1] || '10:00' },
      {
        id: '2',
        role: 'assistant',
        content: t('algorithmOps.sessionHistoryMock', {
          title: td(session.title),
          count: session.messageCount,
        }),
        timestamp: session.timestamp.split(' ')[1] || '10:01',
      },
    ];
    setChatMessages(mockMessages);
    setCurrentSessionId(session.id);
    setShowHistoryList(false);
    message.success(t('algorithmOps.sessionLoaded', { title: td(session.title) }));
  };

  const toggleSkill = (skillId: string) => {
    setSkills(prev => prev.map(s => (s.id === skillId ? { ...s, enabled: !s.enabled } : s)));
  };

  const enabledSkillCount = skills.filter(s => s.enabled).length;

  const skillSelectorContent = (
    <div style={{ width: 280 }}>
      <div style={{ marginBottom: 8 }}>
        <Text strong>{t('algorithmOps.mountSkills')}</Text>{' '}
        <Text type="secondary">({enabledSkillCount}/{skills.length})</Text>
      </div>
      {skills.map(skill => (
        <div key={skill.id} style={{ display: 'flex', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid #f0f0f0' }}>
          <span style={{ marginRight: 8, color: skill.enabled ? '#1890ff' : '#999' }}>{skill.icon}</span>
          <div style={{ flex: 1 }}>
            <Text style={{ fontSize: 13 }}>{t(skill.name)}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 11 }}>{t(skill.description)}</Text>
          </div>
          <Switch size="small" checked={skill.enabled} onChange={() => toggleSkill(skill.id)} />
        </div>
      ))}
    </div>
  );

  const modelOptions = MOCK_MODELS.map(m => ({ value: m.model_id, label: td(m.model_name) }));
  const scenarioOptions = [
    { value: 'renewable-energy', label: t('algorithmOps.scenarioRenewable') },
    { value: 'power-grid', label: t('algorithmOps.scenarioPowerGrid') },
    { value: 'energy-storage', label: t('algorithmOps.scenarioStorage') },
    { value: 'semiconductor', label: t('algorithmOps.scenarioSemiconductor') },
    { value: 'steel-manufacturing', label: t('algorithmOps.scenarioSteel') },
  ];

  // 漂移监控表格列（保留：精度诊断只读视图）
  const driftColumns = [
    {
      title: t('algorithmOps.detail'),
      dataIndex: 'model_name',
      key: 'model_name',
      render: (text: string, record: ModelDriftInfo) => (
        <Space>
          <Text strong>{td(text)}</Text>
          {record.alert_triggered && <Badge status="error" />}
        </Space>
      ),
    },
    { title: t('algorithmOps.detail'), dataIndex: 'scenario_name', key: 'scenario_name', render: (text: string) => <Tag>{td(text)}</Tag> },
    {
      title: t('algorithmOps.detail'),
      dataIndex: 'status',
      key: 'status',
      render: (status: keyof typeof DRIFT_STATUS_CONFIG) => (
        <Tag color={DRIFT_STATUS_CONFIG[status].color}>{td(DRIFT_STATUS_CONFIG[status].text)}</Tag>
      ),
    },
    { title: 'PSI', dataIndex: 'psi_score', key: 'psi_score', render: (psi: number) => <Text type={psi > 0.2 ? 'danger' : undefined}>{psi.toFixed(2)}</Text> },
    {
      title: t('algorithmOps.accuracyChange'),
      dataIndex: 'accuracy_change',
      key: 'accuracy_change',
      render: (change: number) => (
        <Text type={change < -5 ? 'danger' : change < 0 ? 'warning' : 'success'}>
          {change > 0 ? '+' : ''}
          {change.toFixed(1)}%
        </Text>
      ),
    },
    {
      title: t('algorithmOps.actions'),
      key: 'action',
      render: () => (
        <Space>
          <Button size="small">{t('algorithmOps.detail')}</Button>
          <Button size="small" icon={<ReloadOutlined />}>{t('algorithmOps.detect')}</Button>
        </Space>
      ),
    },
  ];

  // 归因分析：特征漂移热力图（PSI/KS/JS × 各特征）
  const driftHeatmapOption = {
    tooltip: { trigger: 'item' },
    xAxis: { type: 'category', data: [td('辐照度'), td('温度'), td('湿度'), td('风速'), td('云量')] },
    yAxis: { type: 'category', data: ['PSI', 'KS', 'JS'] },
    visualMap: {
      min: 0,
      max: 0.5,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: ['#52c41a', '#faad14', '#f5222d'] },
    },
    series: [{
      type: 'heatmap',
      data: [
        [0, 0, 0.42], [0, 1, 0.18], [0, 2, 0.15],
        [1, 0, 0.25], [1, 1, 0.12], [1, 2, 0.09],
        [2, 0, 0.08], [2, 1, 0.05], [2, 2, 0.03],
        [3, 0, 0.12], [3, 1, 0.08], [3, 2, 0.05],
        [4, 0, 0.32], [4, 1, 0.15], [4, 2, 0.12],
      ],
      label: { show: true, formatter: (p: { value: [number, number, number] }) => p.value[2].toFixed(2) },
    }],
  };

  // 精度指标时序图（MAPE 随时间变化）
  const accuracyTrendOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: [td('光伏预测'), td('风电预测'), td('负荷预测')] },
    xAxis: { type: 'category', data: ['3/15', '3/16', '3/17', '3/18', '3/19', '3/20', '3/21'] },
    yAxis: { type: 'value', name: 'MAPE (%)', min: 0, max: 15 },
    series: [
      { name: td('光伏预测'), type: 'line', data: [5.2, 5.5, 6.0, 6.8, 7.5, 8.2, 9.0], smooth: true },
      { name: td('风电预测'), type: 'line', data: [4.8, 4.9, 5.1, 5.3, 5.5, 5.8, 6.0], smooth: true },
      { name: td('负荷预测'), type: 'line', data: [3.2, 3.5, 4.0, 5.5, 7.2, 9.5, 12.0], smooth: true },
    ],
  };

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* 左侧：只读精度监控 + 归因分析 */}
      <div style={{ flex: 1, padding: 16, overflow: 'auto' }}>
        <Card
          size="small"
          title={t('algorithmOps.title')}
          extra={
            <Space>
              <Select
                value={statusFilter}
                onChange={setStatusFilter}
                style={{ width: 100 }}
                size="small"
                options={[
                  { value: 'all', label: t('algorithmOps.all') },
                  { value: 'normal', label: t('algorithmOps.normal') },
                  { value: 'mild', label: t('algorithmOps.mild') },
                  { value: 'severe', label: t('algorithmOps.severe') },
                ]}
              />
              {/* 「操作类」入口：所有切换/调度/重训均需跳转到「算法部署」页面完成 */}
              <Button
                type="primary"
                size="small"
                icon={<RocketOutlined />}
                onClick={() => navigate('/algorithm-dev/deployment')}
              >
                {t('algorithmOps.goToDeployment', { defaultValue: '前往算法部署' })}
              </Button>
              <Tooltip title={showAIPanel ? t('algorithmOps.hideAIAssistant') : t('algorithmOps.showAIAssistant')}>
                <Button
                  size="small"
                  onClick={() => setShowAIPanel(!showAIPanel)}
                  style={{
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                    borderColor: '#667eea',
                    color: '#fff',
                  }}
                >
                  <ThunderboltOutlined style={{ marginRight: 4 }} />
                  {showAIPanel ? t('algorithmOps.hideAI') : t('algorithmOps.showAI')}
                </Button>
              </Tooltip>
            </Space>
          }
        >
          <Spin spinning={loading}>
            <Tabs
              defaultActiveKey="drift"
              items={[{
                key: 'drift',
                label: <span><WarningOutlined /> {t('algorithmOps.driftMonitor')}</span>,
                children: (
                  <Row gutter={[16, 16]}>
                    <Col span={24}>
                      <Row gutter={16}>
                        <Col span={6}>
                          <Card size="small">
                            <Statistic
                              title={t('algorithmOps.monitorModels')}
                              value={MOCK_DRIFT_STATS.total_models}
                              prefix={<LineChartOutlined />}
                            />
                          </Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small">
                            <Statistic
                              title={t('algorithmOps.normalCount')}
                              value={MOCK_DRIFT_STATS.normal_count}
                              valueStyle={{ color: '#52c41a' }}
                              prefix={<CheckCircleOutlined />}
                            />
                          </Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small">
                            <Statistic
                              title={t('algorithmOps.mildDrift')}
                              value={MOCK_DRIFT_STATS.mild_drift_count}
                              valueStyle={{ color: '#faad14' }}
                              prefix={<ExclamationCircleOutlined />}
                            />
                          </Card>
                        </Col>
                        <Col span={6}>
                          <Card size="small">
                            <Statistic
                              title={t('algorithmOps.severeDrift')}
                              value={MOCK_DRIFT_STATS.severe_drift_count}
                              valueStyle={{ color: '#f5222d' }}
                              prefix={<WarningOutlined />}
                            />
                          </Card>
                        </Col>
                      </Row>
                    </Col>
                    <Col span={24}>
                      <Table
                        dataSource={MOCK_MODELS.filter(m => statusFilter === 'all' || m.status === statusFilter)}
                        columns={driftColumns}
                        rowKey="model_id"
                        size="small"
                        pagination={{ pageSize: 5 }}
                      />
                    </Col>
                    <Col span={12}>
                      {/* 归因分析：特征漂移热力图 */}
                      <Card title={t('algorithmOps.featureHeatmap')} size="small">
                        <ReactECharts option={driftHeatmapOption} style={{ height: 200 }} />
                      </Card>
                    </Col>
                    <Col span={12}>
                      {/* 精度指标时序图 */}
                      <Card title={t('algorithmOps.accuracyTrend')} size="small">
                        <ReactECharts option={accuracyTrendOption} style={{ height: 200 }} />
                      </Card>
                    </Col>
                    <Col span={24}>
                      {/* 底部引导：所有操作类入口统一跳转「算法部署」 */}
                      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
                        {t(
                          'algorithmOps.deploymentRedirectHint',
                          { defaultValue: '需要切换生产/影子模型、编排定时调度或触发重训？请前往「算法部署」页面完成。' },
                        )}
                      </Paragraph>
                    </Col>
                  </Row>
                ),
              }]}
            />
          </Spin>
        </Card>
      </div>

      {showAIPanel && (
        <>
          {/* 可拖拽分隔条 */}
          <div
            onMouseDown={handleMouseDown}
            style={{
              width: 4,
              height: 'calc(100vh - 64px)',
              position: 'sticky',
              top: 0,
              background: isResizing ? '#1890ff' : 'transparent',
              cursor: 'col-resize',
              flexShrink: 0,
              transition: isResizing ? 'none' : 'background 0.2s',
            }}
            onMouseEnter={e => { if (!isResizing) e.currentTarget.style.background = '#e8e8e8'; }}
            onMouseLeave={e => { if (!isResizing) e.currentTarget.style.background = 'transparent'; }}
          />

          {/* AI 助手面板 */}
          <div style={{
            width: rightPanelWidth,
            height: 'calc(100vh - 64px)',
            position: 'sticky',
            top: 0,
            borderLeft: '1px solid #f0f0f0',
            display: 'flex',
            flexDirection: 'column',
            background: '#fafafa',
            overflow: 'hidden',
          }}>
            <div style={{
              padding: '12px 16px',
              borderBottom: '1px solid #f0f0f0',
              background: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0,
            }}>
              <Space>
                <Avatar icon={<RobotOutlined />} style={{ background: '#1890ff' }} />
                <Text strong>{t('algorithmOps.aiOpsAssistant')}</Text>
              </Space>
              <Space size={8}>
                <Button
                  size="small"
                  icon={<PlusOutlined />}
                  onClick={handleNewSession}
                  style={{ borderRadius: 6 }}
                >
                  {t('algorithmOps.newConversation')}
                </Button>
                <Button
                  size="small"
                  onClick={() => setShowHistoryList(!showHistoryList)}
                  style={{ borderRadius: 6, fontWeight: showHistoryList ? 500 : 400 }}
                  type={showHistoryList ? 'primary' : 'default'}
                  ghost={showHistoryList}
                >
                  {t('algorithmOps.historyRecords')}
                </Button>
              </Space>
            </div>

            <div style={{
              flex: 1,
              overflow: 'auto',
              padding: 12,
              minHeight: 0,
              display: 'flex',
              flexDirection: 'column',
              scrollbarWidth: 'thin',
              scrollbarColor: '#d9d9d9 transparent',
            }}>
              {showHistoryList ? (
                <div style={{ padding: '8px 0' }}>
                  <List
                    dataSource={MOCK_SESSIONS}
                    renderItem={session => (
                      <div
                        key={session.id}
                        onClick={() => handleLoadSession(session)}
                        style={{
                          padding: '12px 16px',
                          marginBottom: 8,
                          background: currentSessionId === session.id ? '#e6f7ff' : '#fff',
                          borderRadius: 8,
                          cursor: 'pointer',
                          border: currentSessionId === session.id ? '1px solid #1890ff' : '1px solid #f0f0f0',
                          transition: 'all 0.2s',
                        }}
                        onMouseEnter={e => {
                          if (currentSessionId !== session.id) e.currentTarget.style.background = '#fafafa';
                        }}
                        onMouseLeave={e => {
                          if (currentSessionId !== session.id) e.currentTarget.style.background = '#fff';
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Text strong style={{ fontSize: 14 }}>{td(session.title)}</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {session.messageCount}{t('algorithmOps.messages')}
                          </Text>
                        </div>
                        <Text type="secondary" style={{ fontSize: 12 }}>{td(session.timestamp)}</Text>
                      </div>
                    )}
                  />
                </div>
              ) : (
                <div style={{ marginTop: 'auto' }}>
                  <List
                    dataSource={chatMessages}
                    renderItem={msg => (
                      <div style={{
                        marginBottom: 12,
                        display: 'flex',
                        justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                      }}>
                        <div style={{ maxWidth: '85%' }}>
                          {msg.role === 'assistant' && (
                            <Avatar size="small" icon={<RobotOutlined />} style={{ background: '#1890ff', marginRight: 8 }} />
                          )}
                          <div style={{
                            display: 'inline-block',
                            padding: '8px 12px',
                            borderRadius: 8,
                            background: msg.role === 'user' ? '#1890ff' : '#fff',
                            color: msg.role === 'user' ? '#fff' : '#000',
                            boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            fontSize: 13,
                          }}>
                            {msg.content}
                          </div>
                          {msg.role === 'user' && (
                            <Avatar size="small" icon={<UserOutlined />} style={{ marginLeft: 8 }} />
                          )}
                          <div style={{
                            fontSize: 11,
                            color: '#999',
                            marginTop: 2,
                            textAlign: msg.role === 'user' ? 'right' : 'left',
                          }}>
                            {msg.timestamp}
                          </div>
                        </div>
                      </div>
                    )}
                  />
                  {promptLoading && (
                    <div style={{ textAlign: 'center', padding: 8 }}>
                      <Spin size="small" /> <Text type="secondary">{t('algorithmOps.aiAnalyzing')}</Text>
                    </div>
                  )}
                  <div ref={chatEndRef} />
                </div>
              )}
            </div>

            <div style={{
              flexShrink: 0,
              borderTop: '1px solid #f0f0f0',
              background: '#fff',
            }}>
              <div style={{
                padding: '8px 12px',
                borderBottom: '1px solid #f5f5f5',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <Select
                    size="small"
                    placeholder={t('algorithmOps.selectModel')}
                    allowClear
                    value={selectedModel}
                    onChange={setSelectedModel}
                    style={{ width: 130 }}
                    options={modelOptions}
                    suffixIcon={<AimOutlined />}
                  />
                  <Select
                    size="small"
                    placeholder={t('algorithmOps.timeRange')}
                    value={selectedTimeRange}
                    onChange={setSelectedTimeRange}
                    style={{ width: 90 }}
                    options={[
                      { value: '1d', label: t('algorithmOps.last1d') },
                      { value: '7d', label: t('algorithmOps.last7d') },
                      { value: '30d', label: t('algorithmOps.last30d') },
                      { value: '90d', label: t('algorithmOps.last90d') },
                    ]}
                    suffixIcon={<CalendarOutlined />}
                  />
                  <Select
                    size="small"
                    placeholder={t('algorithmOps.selectScenario')}
                    allowClear
                    value={selectedScenario}
                    onChange={setSelectedScenario}
                    style={{ width: 110 }}
                    options={scenarioOptions}
                  />
                </div>
                <Popover
                  content={
                    <div style={{ width: 200 }}>
                      {QUICK_COMMANDS.map(cmd => (
                        <div
                          key={cmd.label}
                          style={{ padding: '8px 12px', cursor: 'pointer', borderRadius: 4 }}
                          onClick={() => {
                            setPromptText(t(cmd.prompt));
                            setExamplePopoverOpen(false);
                          }}
                          onMouseEnter={e => (e.currentTarget.style.background = '#f5f5f5')}
                          onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                        >
                          <Text style={{ fontSize: 13 }}>{t(cmd.label)}</Text>
                        </div>
                      ))}
                    </div>
                  }
                  trigger="click"
                  placement="topRight"
                  open={examplePopoverOpen}
                  onOpenChange={setExamplePopoverOpen}
                >
                  <Button type="text" size="small" icon={<ThunderboltOutlined />}>
                    {t('algorithmOps.example')}
                  </Button>
                </Popover>
              </div>

              <div style={{ padding: '8px 12px' }}>
                <div style={{ position: 'relative' }}>
                  <TextArea
                    placeholder={t('algorithmOps.inputPlaceholder')}
                    value={promptText}
                    onChange={e => setPromptText(e.target.value)}
                    onPressEnter={e => {
                      if (!e.shiftKey) {
                        e.preventDefault();
                        handlePromptSubmit();
                      }
                    }}
                    autoSize={{ minRows: 3, maxRows: 8 }}
                    style={{ fontSize: 13, borderRadius: 8, paddingRight: 50 }}
                  />
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    loading={promptLoading}
                    onClick={handlePromptSubmit}
                    disabled={!promptText.trim()}
                    style={{
                      position: 'absolute',
                      right: 8,
                      bottom: 8,
                      borderRadius: 6,
                      width: 36,
                      height: 36,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  />
                </div>
              </div>

              <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center' }}>
                <Space size={8}>
                  <Tooltip title={t('algorithmOps.uploadData')}>
                    <Button type="text" icon={<PaperClipOutlined style={{ fontSize: 16 }} />} style={{ padding: '4px 8px' }} />
                  </Tooltip>
                  <Popover content={skillSelectorContent} trigger="click" placement="topLeft">
                    <Button type="text" style={{ padding: '4px 8px' }}>
                      <AppstoreOutlined style={{ fontSize: 16 }} />{' '}
                      <span style={{ marginLeft: 4 }}>{t('algorithmOps.skills')}</span>{' '}
                      <Badge count={enabledSkillCount} size="small" style={{ marginLeft: 4 }} />
                    </Button>
                  </Popover>
                  <Tooltip title={t('algorithmOps.advancedSettings')}>
                    <Button type="text" icon={<SettingOutlined style={{ fontSize: 16 }} />} style={{ padding: '4px 8px' }} />
                  </Tooltip>
                </Space>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default AlgorithmOpsPage;
// @AI_GENERATED: end
