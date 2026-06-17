// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useRef, useCallback } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Row, Col, Statistic, Table, Tag, Space, Input, Button, Tabs,
  Select, Typography, Progress, message, Spin, Modal, Form,
  InputNumber, Switch, Badge, Timeline, Avatar, List, Tooltip, Popover,
} from 'antd';
import {
  SyncOutlined, SendOutlined, PlusOutlined,
  CheckCircleOutlined, PauseCircleOutlined,
  PlayCircleOutlined, RobotOutlined, ThunderboltOutlined,
  ClockCircleOutlined, ExperimentOutlined,
  LineChartOutlined, WarningOutlined, ExclamationCircleOutlined,
  TrophyOutlined, UserOutlined, ReloadOutlined,
  AppstoreOutlined, PaperClipOutlined,
  CalendarOutlined, AimOutlined, SettingOutlined, BulbOutlined,
  DatabaseOutlined, FileTextOutlined,
} from '@ant-design/icons';
import ReactECharts from 'echarts-for-react';
import type {
  ModelDriftInfo, DriftMonitorStats, ABTestConfig, ABTestStats,
  RetrainTask, RetrainStats, QuickCommand,
} from '../types/algorithm-ops';
import { DRIFT_STATUS_CONFIG, ABTEST_STATUS_CONFIG, RETRAIN_STATUS_CONFIG } from '../types/algorithm-ops';
import { opsPromptApi } from '../services/algorithmOpsApi';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
import i18n from '../i18n';
// @AI_GENERATED: end

const { Text, Paragraph } = Typography;
const { TextArea } = Input;
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
// ============ Mock 数据 ============
const MOCK_DRIFT_STATS: DriftMonitorStats = { total_models: 45, normal_count: 32, mild_drift_count: 8, severe_drift_count: 5, retrain_triggered: 3 };
const MOCK_ABTEST_STATS: ABTestStats = { total_tests: 22, running_count: 5, completed_count: 12, a_wins_count: 4, b_wins_count: 8 };
const MOCK_RETRAIN_STATS: RetrainStats = { total_tasks: 29, queued_count: 8, training_count: 2, completed_count: 15, failed_count: 1, avg_improvement: 3.2 };

const MOCK_MODELS: ModelDriftInfo[] = [
  { model_id: 'pv-power-001', model_name: '光伏功率预测-LSTM', scenario_id: 'renewable-energy', scenario_name: '新能源发电', status: 'severe', drift_type: 'both', psi_score: 0.35, accuracy_change: -12.5, last_check_time: '2026-03-21 10:30:00', alert_triggered: true },
  { model_id: 'wind-power-001', model_name: '风电功率预测-XGBoost', scenario_id: 'renewable-energy', scenario_name: '新能源发电', status: 'mild', drift_type: 'data', psi_score: 0.18, accuracy_change: -5.2, last_check_time: '2026-03-21 10:25:00', alert_triggered: false },
  { model_id: 'load-forecast-001', model_name: '负荷预测-Transformer', scenario_id: 'power-grid', scenario_name: '电网与微网', status: 'severe', drift_type: 'concept', psi_score: 0.28, accuracy_change: -15.8, last_check_time: '2026-03-21 10:15:00', alert_triggered: true },
  { model_id: 'defect-detect-001', model_name: '晶圆缺陷检测-YOLO', scenario_id: 'semiconductor', scenario_name: '半导体制造', status: 'mild', drift_type: 'data', psi_score: 0.15, accuracy_change: -3.8, last_check_time: '2026-03-21 10:10:00', alert_triggered: false },
  { model_id: 'quality-pred-001', model_name: '质量预测-RF', scenario_id: 'steel-manufacturing', scenario_name: '钢铁制造', status: 'normal', drift_type: 'data', psi_score: 0.05, accuracy_change: 0.5, last_check_time: '2026-03-21 10:05:00', alert_triggered: false },
];

const MOCK_TESTS: ABTestConfig[] = [
  { test_id: 'ab-001', test_name: '光伏预测 v2.1 vs v2.0', model_a_id: 'pv-v2.0', model_a_name: '光伏预测-LSTM v2.0', model_b_id: 'pv-v2.1', model_b_name: '光伏预测-LSTM v2.1', traffic_split: 30, start_time: '2026-03-18 10:00:00', status: 'running', result: 'pending', scenario_id: 'renewable-energy', scenario_name: '新能源发电' },
  { test_id: 'ab-002', test_name: '风电预测 v3.0 vs v2.5', model_a_id: 'wind-v2.5', model_a_name: '风电预测-XGBoost v2.5', model_b_id: 'wind-v3.0', model_b_name: '风电预测-XGBoost v3.0', traffic_split: 50, start_time: '2026-03-15 08:00:00', status: 'running', result: 'pending', scenario_id: 'renewable-energy', scenario_name: '新能源发电' },
  { test_id: 'ab-003', test_name: '负荷预测 Transformer vs LSTM', model_a_id: 'load-lstm', model_a_name: '负荷预测-LSTM', model_b_id: 'load-trans', model_b_name: '负荷预测-Transformer', traffic_split: 20, start_time: '2026-03-10 00:00:00', end_time: '2026-03-17 00:00:00', status: 'completed', result: 'b_wins', scenario_id: 'power-grid', scenario_name: '电网与微网' },
];

const MOCK_TASKS: RetrainTask[] = [
  { task_id: 'rt-001', model_id: 'pv-power-001', model_name: '光伏功率预测-LSTM', scenario_id: 'renewable-energy', scenario_name: '新能源发电', retrain_type: 'incremental', trigger: 'drift_detected', status: 'training', created_at: '2026-03-21 09:00:00', started_at: '2026-03-21 09:05:00', progress: 65, old_accuracy: 92.5 },
  { task_id: 'rt-002', model_id: 'load-forecast-001', model_name: '负荷预测-Transformer', scenario_id: 'power-grid', scenario_name: '电网与微网', retrain_type: 'full', trigger: 'drift_detected', status: 'validating', created_at: '2026-03-21 08:00:00', started_at: '2026-03-21 08:10:00', progress: 90, old_accuracy: 88.2, new_accuracy: 93.5, improvement: 5.3 },
  { task_id: 'rt-003', model_id: 'wind-power-001', model_name: '风电功率预测-XGBoost', scenario_id: 'renewable-energy', scenario_name: '新能源发电', retrain_type: 'incremental', trigger: 'scheduled', status: 'queued', created_at: '2026-03-21 10:00:00', progress: 0, old_accuracy: 91.8 },
];

const QUICK_COMMANDS: QuickCommand[] = [
  { label: 'algorithmOps.quickDiagnoseAll', prompt: 'algorithmOps.quickPromptDiagnoseAll' },
  { label: 'algorithmOps.quickAnalyzeWeek', prompt: 'algorithmOps.quickPromptAnalyzeWeek' },
  { label: 'algorithmOps.quickFindEndable', prompt: 'algorithmOps.quickPromptFindEndable' },
  { label: 'algorithmOps.quickAutoRetrain', prompt: 'algorithmOps.quickPromptAutoRetrain' },
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

// 可用技能列表 - 使用 key 而非直接 t()，在组件内部翻译
const AVAILABLE_SKILLS_DATA = [
  { id: 'drift-detect', nameKey: 'algorithmOps.driftDetect', descKey: 'algorithmOps.driftDetectDesc', icon: <WarningOutlined />, enabled: true },
  { id: 'root-cause', nameKey: 'algorithmOps.rootCauseAnalysis', descKey: 'algorithmOps.rootCauseDesc', icon: <BulbOutlined />, enabled: true },
  { id: 'ab-analyze', nameKey: 'algorithmOps.abAnalysis', descKey: 'algorithmOps.abAnalysisDesc', icon: <ExperimentOutlined />, enabled: true },
  { id: 'retrain-eval', nameKey: 'algorithmOps.retrainEval', descKey: 'algorithmOps.retrainEvalDesc', icon: <SyncOutlined />, enabled: false },
  { id: 'data-quality', nameKey: 'algorithmOps.dataQuality', descKey: 'algorithmOps.dataQualityDesc', icon: <DatabaseOutlined />, enabled: false },
  { id: 'report-gen', nameKey: 'algorithmOps.reportGen', descKey: 'algorithmOps.reportGenDesc', icon: <FileTextOutlined />, enabled: true },
];

// 历史会话 Mock
const MOCK_SESSIONS: ChatSession[] = [
  { id: 's1', title: '光伏模型漂移诊断', timestamp: '今天 10:30', messageCount: 8 },
  { id: 's2', title: 'A/B测试结果分析', timestamp: '今天 09:15', messageCount: 5 },
  { id: 's3', title: '本周运营周报', timestamp: '昨天 17:00', messageCount: 12 },
  { id: 's4', title: '负荷预测重训评估', timestamp: '3/19 14:20', messageCount: 6 },
];
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
const AlgorithmOpsPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [activeTab, setActiveTab] = useState('drift');
  const [loading, setLoading] = useState(false);
  const [promptText, setPromptText] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { id: '1', role: 'assistant', content: t('algorithmOps.greeting'), timestamp: '10:00' },
  ]);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [createModalVisible, setCreateModalVisible] = useState(false);
  const [createType, setCreateType] = useState<'abtest' | 'retrain'>('abtest');
  // @AI_GENERATED: Kiro v1.0
  const [showHistoryList, setShowHistoryList] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [showAIPanel, setShowAIPanel] = useState(true);
  // @AI_GENERATED: end
  const [skills, setSkills] = useState<Skill[]>(() => AVAILABLE_SKILLS_DATA.map(s => ({ ...s, name: s.nameKey, description: s.descKey })));
  const [selectedModel, setSelectedModel] = useState<string | undefined>();
  const [selectedTimeRange, setSelectedTimeRange] = useState<string>('7d');
  const [selectedScenario, setSelectedScenario] = useState<string | undefined>();
  const [rightPanelWidth, setRightPanelWidth] = useState(480);
  const [isResizing, setIsResizing] = useState(false);
  const [examplePopoverOpen, setExamplePopoverOpen] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const [form] = Form.useForm();
  const formatChatTime = useCallback(
    (date: Date = new Date()) => date.toLocaleTimeString(
      (i18n.language || '').toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN',
      { hour: '2-digit', minute: '2-digit' },
    ),
    [],
  );

  // 拖拽调整宽度
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isResizing) return;
      const newWidth = window.innerWidth - e.clientX;
      // 限制宽度范围：最小 320px，最大 800px
      setRightPanelWidth(Math.min(800, Math.max(320, newWidth)));
    };

    const handleMouseUp = () => {
      setIsResizing(false);
    };

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
    setTimeout(() => setLoading(false), 300);
  }, [activeTab]);

  // 当消息变化或输入框内容变化时，滚动到底部
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

  // @AI_GENERATED: Kiro v1.0
  const handlePromptSubmit = async () => {
    if (!promptText.trim()) return;
    const userMsg: ChatMessage = { id: Date.now().toString(), role: 'user', content: promptText, timestamp: formatChatTime() };
    setChatMessages(prev => [...prev, userMsg]);
    const currentPrompt = promptText;
    setPromptText('');
    setPromptLoading(true);
    
    try {
      // 调用后端 API
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
    } catch (error: any) {
      console.error('Prompt execution failed:', error);
      // 如果 API 调用失败，使用本地 mock 响应作为降级
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
  // @AI_GENERATED: end

  const generateAIResponse = (prompt: string): string => {
    const lowerPrompt = prompt.toLowerCase();
    const isDriftPrompt = prompt.includes('漂移')
      || prompt.includes('诊断')
      || lowerPrompt.includes('drift')
      || lowerPrompt.includes('diagnos');
    const isABPrompt = prompt.includes('A/B')
      || prompt.includes('测试')
      || lowerPrompt.includes('a/b')
      || lowerPrompt.includes('ab test')
      || lowerPrompt.includes('test');
    const isRetrainPrompt = prompt.includes('重训')
      || prompt.includes('训练')
      || lowerPrompt.includes('retrain')
      || lowerPrompt.includes('re-train')
      || lowerPrompt.includes('train');
    const isWeeklyReportPrompt = prompt.includes('周报')
      || prompt.includes('报告')
      || lowerPrompt.includes('report')
      || lowerPrompt.includes('weekly');

    if (isDriftPrompt) {
      return td('已完成模型漂移诊断：\n\n🔴 严重漂移 (2个):\n- 光伏功率预测-LSTM: PSI=0.35, 精度下降12.5%\n- 负荷预测-Transformer: PSI=0.28, 精度下降15.8%\n\n🟡 轻度漂移 (2个):\n- 风电功率预测-XGBoost\n- 缺陷检测-YOLO\n\n建议：对严重漂移模型触发自动重训。');
    }
    if (isABPrompt) {
      return td('当前 A/B 测试状态：\n\n✅ 可结束测试:\n- 光伏预测 v2.1 vs v2.0: 已达95%置信度，B模型精度提升2.3%，建议采纳\n\n⏳ 继续观察:\n- 风电预测 v3.0 vs v2.5: 样本量不足，建议继续运行3天');
    }
    if (isRetrainPrompt) {
      return td('重训任务执行中：\n\n🔄 训练中 (1个):\n- 光伏功率预测-LSTM: 进度65%，预计30分钟完成\n\n✅ 待验证 (1个):\n- 负荷预测-Transformer: 精度提升5.3%，建议创建A/B测试验证\n\n⏳ 排队中 (1个):\n- 风电功率预测-XGBoost');
    }
    if (isWeeklyReportPrompt) {
      // @AI_GENERATED
      const weeklyReport = i18n.language === 'en'
        ? '📊 Weekly Algorithm Operations Report\n\n【Drift Monitoring】\n- Monitored models: 45\n- New drift: 5 (2 severe, 3 mild)\n- Fixed: 3\n\n【A/B Testing】\n- Completed tests: 3\n- New version wins: 2\n- Avg improvement: 3.8%\n\n【Auto Retrain】\n- Completed retrains: 5\n- Avg accuracy improvement: 3.2%\n\nRecommendation: Prioritize PV and load forecast model drift issues.'
        : '📊 本周算法运营周报\n\n【漂移监控】\n- 监控模型: 45个\n- 新增漂移: 5个 (严重2, 轻度3)\n- 已修复: 3个\n\n【A/B测试】\n- 完成测试: 3个\n- 新版胜出: 2个\n- 平均提升: 3.8%\n\n【自动重训】\n- 完成重训: 5个\n- 平均精度提升: 3.2%\n\n建议：优先处理光伏和负荷预测模型的漂移问题。';
      return weeklyReport;
      // @AI_GENERATED: end
    }
    return td('收到您的请求，正在分析中...\n\n我可以帮您：\n1. 诊断模型漂移状态\n2. 分析 A/B 测试结果\n3. 管理自动重训任务\n4. 生成运营报告\n\n请告诉我具体需要什么帮助？');
  };

  const handleCreate = () => {
    form.validateFields().then(() => {
      message.success(createType === 'abtest' ? t('algorithmOps.abtestCreated') : t('algorithmOps.retrainCreated'));
      setCreateModalVisible(false);
      form.resetFields();
    });
  };

  // 新会话
  // @AI_GENERATED: Kiro v1.0
  const handleNewSession = () => {
    setChatMessages([
      { id: Date.now().toString(), role: 'assistant', content: t('algorithmOps.newSessionMsg'), timestamp: formatChatTime() },
    ]);
    setCurrentSessionId(null);
    setShowHistoryList(false);
    message.success(t('algorithmOps.newSessionCreated'));
  };

  // 加载历史会话
  const handleLoadSession = (session: ChatSession) => {
    // Mock: 加载该会话的消息
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
  // @AI_GENERATED: end

  // 切换技能
  const toggleSkill = (skillId: string) => {
    setSkills(prev => prev.map(s => s.id === skillId ? { ...s, enabled: !s.enabled } : s));
  };

  // 获取启用的技能数量
  const enabledSkillCount = skills.filter(s => s.enabled).length;

  // Skill 选择器内容
  const skillSelectorContent = (
    <div style={{ width: 280 }}>
      <div style={{ marginBottom: 8 }}><Text strong>{t('algorithmOps.mountSkills')}</Text> <Text type="secondary">({enabledSkillCount}/{skills.length})</Text></div>
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

  // 模型选择选项
  const modelOptions = MOCK_MODELS.map(m => ({ value: m.model_id, label: td(m.model_name) }));
  
  // 场景选择选项
  const scenarioOptions = [
    { value: 'renewable-energy', label: t('algorithmOps.scenarioRenewable') },
    { value: 'power-grid', label: t('algorithmOps.scenarioPowerGrid') },
    { value: 'energy-storage', label: t('algorithmOps.scenarioStorage') },
    { value: 'semiconductor', label: t('algorithmOps.scenarioSemiconductor') },
    { value: 'steel-manufacturing', label: t('algorithmOps.scenarioSteel') },
  ];
// @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 漂移监控表格列
  const driftColumns = [
    { title: t('algorithmOps.detail'), dataIndex: 'model_name', key: 'model_name', render: (text: string, record: ModelDriftInfo) => <Space><Text strong>{td(text)}</Text>{record.alert_triggered && <Badge status="error" />}</Space> },
    { title: t('algorithmOps.detail'), dataIndex: 'scenario_name', key: 'scenario_name', render: (text: string) => <Tag>{td(text)}</Tag> },
    { title: t('algorithmOps.detail'), dataIndex: 'status', key: 'status', render: (status: keyof typeof DRIFT_STATUS_CONFIG) => <Tag color={DRIFT_STATUS_CONFIG[status].color}>{td(DRIFT_STATUS_CONFIG[status].text)}</Tag> },
    { title: 'PSI', dataIndex: 'psi_score', key: 'psi_score', render: (psi: number) => <Text type={psi > 0.2 ? 'danger' : undefined}>{psi.toFixed(2)}</Text> },
    { title: t('algorithmOps.accuracyChange'), dataIndex: 'accuracy_change', key: 'accuracy_change', render: (change: number) => <Text type={change < -5 ? 'danger' : change < 0 ? 'warning' : 'success'}>{change > 0 ? '+' : ''}{change.toFixed(1)}%</Text> },
    { title: t('algorithmOps.actions'), key: 'action', render: () => <Space><Button size="small">{t('algorithmOps.detail')}</Button><Button size="small" icon={<ReloadOutlined />}>{t('algorithmOps.detect')}</Button></Space> },
  ];

  // A/B测试表格列
  const abtestColumns = [
    { title: t('algorithmOps.testName'), dataIndex: 'test_name', key: 'test_name', render: (text: string, record: ABTestConfig) => <Space><Text strong>{td(text)}</Text>{record.status === 'running' && <Badge status="processing" />}</Space> },
    { title: t('algorithmOps.detail'), dataIndex: 'scenario_name', key: 'scenario_name', render: (text: string) => <Tag>{td(text)}</Tag> },
    { title: t('algorithmOps.detail'), dataIndex: 'status', key: 'status', render: (status: keyof typeof ABTEST_STATUS_CONFIG) => <Tag color={ABTEST_STATUS_CONFIG[status].color}>{td(ABTEST_STATUS_CONFIG[status].text)}</Tag> },
    { title: t('algorithmOps.detail'), dataIndex: 'traffic_split', key: 'traffic_split', render: (split: number) => <Progress percent={split} size="small" style={{ width: 60 }} format={p => `${p}%`} /> },
    { title: t('algorithmOps.detail'), dataIndex: 'result', key: 'result', render: (result: string) => result === 'pending' ? <Tag>{t('algorithmOps.detail')}</Tag> : result === 'b_wins' ? <Tag color="green" icon={<TrophyOutlined />}>{t('algorithmOps.bWins')}</Tag> : <Tag color="blue" icon={<TrophyOutlined />}>{t('algorithmOps.aWins')}</Tag> },
    { title: t('algorithmOps.actions'), key: 'action', render: (_: unknown, record: ABTestConfig) => <Space><Button size="small">{t('algorithmOps.detail')}</Button>{record.status === 'running' && <Button size="small" icon={<PauseCircleOutlined />} />}</Space> },
  ];

  // 重训任务表格列
  const retrainColumns = [
    { title: t('algorithmOps.detail'), dataIndex: 'model_name', key: 'model_name', render: (text: string, record: RetrainTask) => <Space><Text strong>{td(text)}</Text>{record.status === 'training' && <Badge status="processing" />}</Space> },
    { title: t('algorithmOps.detail'), dataIndex: 'scenario_name', key: 'scenario_name', render: (text: string) => <Tag>{td(text)}</Tag> },
    { title: t('algorithmOps.detail'), dataIndex: 'status', key: 'status', render: (status: keyof typeof RETRAIN_STATUS_CONFIG) => <Tag color={RETRAIN_STATUS_CONFIG[status].color}>{td(RETRAIN_STATUS_CONFIG[status].text)}</Tag> },
    { title: t('algorithmOps.detail'), dataIndex: 'retrain_type', key: 'retrain_type', render: (type: string) => <Tag color={type === 'full' ? 'orange' : 'blue'}>{type === 'full' ? t('algorithmOps.fullTrain') : t('algorithmOps.incrementalTrain')}</Tag> },
    { title: t('algorithmOps.detail'), dataIndex: 'progress', key: 'progress', render: (progress: number, record: RetrainTask) => <Progress percent={progress} size="small" status={record.status === 'failed' ? 'exception' : 'active'} style={{ width: 80 }} /> },
    { title: t('algorithmOps.detail'), key: 'improvement', render: (_: unknown, record: RetrainTask) => record.improvement ? <Text type="success">+{record.improvement.toFixed(1)}%</Text> : <Text type="secondary">-</Text> },
    { title: t('algorithmOps.actions'), key: 'action', render: (_: unknown, record: RetrainTask) => <Space><Button size="small">{t('algorithmOps.detail')}</Button>{record.status === 'validating' && <Button size="small" type="primary">{t('algorithmOps.deploy')}</Button>}</Space> },
  ];
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // 图表配置
  const driftHeatmapOption = {
    tooltip: { trigger: 'item' },
    xAxis: { type: 'category', data: [td('辐照度'), td('温度'), td('湿度'), td('风速'), td('云量')] },
    yAxis: { type: 'category', data: ['PSI', 'KS', 'JS'] },
    visualMap: { min: 0, max: 0.5, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, inRange: { color: ['#52c41a', '#faad14', '#f5222d'] } },
    series: [{ type: 'heatmap', data: [[0,0,0.42],[0,1,0.18],[0,2,0.15],[1,0,0.25],[1,1,0.12],[1,2,0.09],[2,0,0.08],[2,1,0.05],[2,2,0.03],[3,0,0.12],[3,1,0.08],[3,2,0.05],[4,0,0.32],[4,1,0.15],[4,2,0.12]], label: { show: true, formatter: (p: any) => p.value[2].toFixed(2) } }],
  };

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

  const abtestCompareOption = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { data: [td('模型 A'), td('模型 B')] },
    xAxis: { type: 'category', data: [td('精度(%)'), td('延迟P50(ms)'), td('延迟P99(ms)'), td('错误率(%)')] },
    yAxis: { type: 'value' },
    series: [
      { name: td('模型 A'), type: 'bar', data: [92.5, 45, 120, 0.5], itemStyle: { color: '#1890ff' } },
      { name: td('模型 B'), type: 'bar', data: [94.8, 42, 105, 0.3], itemStyle: { color: '#52c41a' } },
    ],
  };

  const trainingLossOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: [td('训练Loss'), td('验证Loss')] },
    xAxis: { type: 'category', data: Array.from({ length: 30 }, (_, i) => `${i + 1}`) },
    yAxis: { type: 'value', name: 'Loss' },
    series: [
      { name: td('训练Loss'), type: 'line', data: Array.from({ length: 30 }, (_, i) => 0.5 * Math.exp(-i / 10) + 0.02), smooth: true },
      { name: td('验证Loss'), type: 'line', data: Array.from({ length: 30 }, (_, i) => 0.55 * Math.exp(-i / 12) + 0.025), smooth: true },
    ],
  };
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  // Tab 内容
  const tabItems = [
    {
      key: 'drift',
      label: <span><WarningOutlined /> {t('algorithmOps.driftMonitor')}</span>,
      children: (
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Row gutter={16}>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.monitorModels')} value={MOCK_DRIFT_STATS.total_models} prefix={<LineChartOutlined />} /></Card></Col>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.normalCount')} value={MOCK_DRIFT_STATS.normal_count} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.mildDrift')} value={MOCK_DRIFT_STATS.mild_drift_count} valueStyle={{ color: '#faad14' }} prefix={<ExclamationCircleOutlined />} /></Card></Col>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.severeDrift')} value={MOCK_DRIFT_STATS.severe_drift_count} valueStyle={{ color: '#f5222d' }} prefix={<WarningOutlined />} /></Card></Col>
              <Col span={4}><Card size="small"><Statistic title={t('algorithmOps.retrainTriggered')} value={MOCK_DRIFT_STATS.retrain_triggered} valueStyle={{ color: '#722ed1' }} prefix={<ThunderboltOutlined />} /></Card></Col>
            </Row>
          </Col>
          <Col span={24}><Table dataSource={MOCK_MODELS.filter(m => statusFilter === 'all' || m.status === statusFilter)} columns={driftColumns} rowKey="model_id" size="small" pagination={{ pageSize: 5 }} /></Col>
          <Col span={12}><Card title={t('algorithmOps.featureHeatmap')} size="small"><ReactECharts option={driftHeatmapOption} style={{ height: 200 }} /></Card></Col>
          <Col span={12}><Card title={t('algorithmOps.accuracyTrend')} size="small"><ReactECharts option={accuracyTrendOption} style={{ height: 200 }} /></Card></Col>
        </Row>
      ),
    },
    {
      key: 'abtest',
      label: <span><ExperimentOutlined /> {t('algorithmOps.abTest')}</span>,
      children: (
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Row gutter={16}>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.totalTests')} value={MOCK_ABTEST_STATS.total_tests} prefix={<ExperimentOutlined />} /></Card></Col>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.running')} value={MOCK_ABTEST_STATS.running_count} valueStyle={{ color: '#1890ff' }} prefix={<PlayCircleOutlined />} /></Card></Col>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.completed')} value={MOCK_ABTEST_STATS.completed_count} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.aWins')} value={MOCK_ABTEST_STATS.a_wins_count} prefix={<TrophyOutlined />} /></Card></Col>
              <Col span={4}><Card size="small"><Statistic title={t('algorithmOps.bWins')} value={MOCK_ABTEST_STATS.b_wins_count} valueStyle={{ color: '#52c41a' }} prefix={<TrophyOutlined />} /></Card></Col>
            </Row>
          </Col>
          <Col span={24}><Table dataSource={MOCK_TESTS} columns={abtestColumns} rowKey="test_id" size="small" pagination={{ pageSize: 5 }} /></Col>
          <Col span={12}><Card title={t('algorithmOps.metricsCompare')} size="small"><ReactECharts option={abtestCompareOption} style={{ height: 200 }} /></Card></Col>
          <Col span={12}>
            <Card title={t('algorithmOps.aiDecisionAdvice')} size="small" extra={<RobotOutlined style={{ color: '#1890ff' }} />}>
              <Paragraph><Text strong>{td('光伏预测 v2.1 vs v2.0')}</Text></Paragraph>
              <Paragraph type="secondary">{td('置信度95%，B模型精度提升2.3%，延迟降低12.5%。建议采纳B模型。')}</Paragraph>
              <Space><Button type="primary" size="small" icon={<CheckCircleOutlined />}>{t('algorithmOps.adoptB')}</Button><Button size="small">{t('algorithmOps.extendTest')}</Button></Space>
            </Card>
          </Col>
        </Row>
      ),
    },
    {
      key: 'retrain',
      label: <span><SyncOutlined /> {t('algorithmOps.autoRetrain')}</span>,
      children: (
        <Row gutter={[16, 16]}>
          <Col span={24}>
            <Row gutter={16}>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.totalTasks')} value={MOCK_RETRAIN_STATS.total_tasks} prefix={<SyncOutlined />} /></Card></Col>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.queued')} value={MOCK_RETRAIN_STATS.queued_count} prefix={<ClockCircleOutlined />} /></Card></Col>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.training')} value={MOCK_RETRAIN_STATS.training_count} valueStyle={{ color: '#1890ff' }} prefix={<PlayCircleOutlined />} /></Card></Col>
              <Col span={5}><Card size="small"><Statistic title={t('algorithmOps.completed')} value={MOCK_RETRAIN_STATS.completed_count} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} /></Card></Col>
              <Col span={4}><Card size="small"><Statistic title={t('algorithmOps.avgImprovement')} value={MOCK_RETRAIN_STATS.avg_improvement} suffix="%" valueStyle={{ color: '#52c41a' }} prefix={<ThunderboltOutlined />} /></Card></Col>
            </Row>
          </Col>
          <Col span={24}><Table dataSource={MOCK_TASKS} columns={retrainColumns} rowKey="task_id" size="small" pagination={{ pageSize: 5 }} /></Col>
          <Col span={12}><Card title={t('algorithmOps.trainingLoss')} size="small"><ReactECharts option={trainingLossOption} style={{ height: 200 }} /></Card></Col>
          <Col span={12}>
            <Card title={t('algorithmOps.trainingLog')} size="small" style={{ height: 248, overflow: 'auto' }}>
              <Timeline items={[
                { color: 'green', children: td('[09:05] 开始训练 光伏功率预测-LSTM') },
                { color: 'blue', children: td('[09:05] 加载数据: 15,000样本') },
                { color: 'blue', children: '[09:10] Epoch 10/50, Loss: 0.125' },
                { color: 'blue', children: '[09:20] Epoch 30/50, Loss: 0.052' },
                { color: 'gray', children: td('[09:30] 训练中... Epoch 45/50') },
              ]} />
            </Card>
          </Col>
        </Row>
      ),
    },
  ];
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* 左侧：功能区域 */}
      <div style={{ flex: 1, padding: 16, overflow: 'auto' }}>
        <Card
          size="small"
          title={t('algorithmOps.title')}
          extra={
            <Space>
              <Select value={statusFilter} onChange={setStatusFilter} style={{ width: 100 }} size="small"
                options={[{ value: 'all', label: t('algorithmOps.all') }, { value: 'normal', label: t('algorithmOps.normal') }, { value: 'mild', label: t('algorithmOps.mild') }, { value: 'severe', label: t('algorithmOps.severe') }]}
              />
              <Button size="small" icon={<PlusOutlined />} onClick={() => { setCreateType('abtest'); setCreateModalVisible(true); }}>{t('algorithmOps.abtestBtn')}</Button>
              <Button size="small" icon={<PlusOutlined />} onClick={() => { setCreateType('retrain'); setCreateModalVisible(true); }}>{t('algorithmOps.retrainBtn')}</Button>
              {/* @AI_GENERATED: Kiro v1.0 */}
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
              {/* @AI_GENERATED: end */}
            </Space>
          }
        >
          <Spin spinning={loading}>
            <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
          </Spin>
        </Card>
      </div>

      {/* @AI_GENERATED: Kiro v1.0 */}
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

          {/* 右侧：AI 助手面板 - 高度固定为视口高度减去头部 */}
          <div style={{ width: rightPanelWidth, height: 'calc(100vh - 64px)', position: 'sticky', top: 0, borderLeft: '1px solid #f0f0f0', display: 'flex', flexDirection: 'column', background: '#fafafa', overflow: 'hidden' }}>
        {/* 头部 - 固定高度 */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #f0f0f0', background: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
          <Space>
            <Avatar icon={<RobotOutlined />} style={{ background: '#1890ff' }} />
            <Text strong>{t('algorithmOps.aiOpsAssistant')}</Text>
          </Space>
          {/* @AI_GENERATED: Kiro v1.0 */}
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
          {/* @AI_GENERATED: end */}
        </div>

        {/* 对话区域 - flex:1 自动填充，内容从底部向上增长 */}
        {/* @AI_GENERATED: Kiro v1.0 */}
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
            // 历史会话列表
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
                    onMouseEnter={e => { if (currentSessionId !== session.id) e.currentTarget.style.background = '#fafafa'; }}
                    onMouseLeave={e => { if (currentSessionId !== session.id) e.currentTarget.style.background = '#fff'; }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Text strong style={{ fontSize: 14 }}>{td(session.title)}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>{session.messageCount}{t('algorithmOps.messages')}</Text>
                    </div>
                    <Text type="secondary" style={{ fontSize: 12 }}>{td(session.timestamp)}</Text>
                  </div>
                )}
              />
            </div>
          ) : (
            // 对话消息列表
            <div style={{ marginTop: 'auto' }}>
              <List
                dataSource={chatMessages}
                renderItem={msg => (
                  <div style={{ marginBottom: 12, display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start' }}>
                    <div style={{ maxWidth: '85%' }}>
                      {msg.role === 'assistant' && <Avatar size="small" icon={<RobotOutlined />} style={{ background: '#1890ff', marginRight: 8 }} />}
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
                      {msg.role === 'user' && <Avatar size="small" icon={<UserOutlined />} style={{ marginLeft: 8 }} />}
                      <div style={{ fontSize: 11, color: '#999', marginTop: 2, textAlign: msg.role === 'user' ? 'right' : 'left' }}>{msg.timestamp}</div>
                    </div>
                  </div>
                )}
              />
              {promptLoading && <div style={{ textAlign: 'center', padding: 8 }}><Spin size="small" /> <Text type="secondary">{t('algorithmOps.aiAnalyzing')}</Text></div>}
              <div ref={chatEndRef} />
            </div>
          )}
        </div>
        {/* @AI_GENERATED: end */}

        {/* 输入区域 - 固定在底部，不随内容滚动 */}
        <div style={{ 
          flexShrink: 0,
          borderTop: '1px solid #f0f0f0', 
          background: '#fff'
        }}>
          {/* 上下文选择栏 */}
          {/* @AI_GENERATED: Kiro v1.0 */}
          <div style={{ padding: '8px 12px', borderBottom: '1px solid #f5f5f5', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
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
                      onClick={() => { setPromptText(t(cmd.prompt)); setExamplePopoverOpen(false); }}
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
              <Button type="text" size="small" icon={<ThunderboltOutlined />}>{t('algorithmOps.example')}</Button>
            </Popover>
          </div>
          {/* @AI_GENERATED: end */}

          {/* 输入框 + 发送按钮 */}
          <div style={{ padding: '8px 12px' }}>
            <div style={{ position: 'relative' }}>
              <TextArea
                placeholder={t('algorithmOps.inputPlaceholder')}
                value={promptText}
                onChange={e => setPromptText(e.target.value)}
                onPressEnter={e => { if (!e.shiftKey) { e.preventDefault(); handlePromptSubmit(); } }}
                autoSize={{ minRows: 3, maxRows: 8 }}
                style={{ fontSize: 13, borderRadius: 8, paddingRight: 50 }}
              />
              {/* @AI_GENERATED: Kiro v1.0 */}
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
              {/* @AI_GENERATED: end */}
            </div>
          </div>
          
          {/* 功能按钮栏 */}
          <div style={{ padding: '8px 12px', display: 'flex', alignItems: 'center' }}>
            <Space size={8}>
              <Tooltip title={t('algorithmOps.uploadData')}>
                <Button type="text" icon={<PaperClipOutlined style={{ fontSize: 16 }} />} style={{ padding: '4px 8px' }} />
              </Tooltip>
              <Popover content={skillSelectorContent} trigger="click" placement="topLeft">
                <Button type="text" style={{ padding: '4px 8px' }}>
                  <AppstoreOutlined style={{ fontSize: 16 }} /> <span style={{ marginLeft: 4 }}>{t('algorithmOps.skills')}</span> <Badge count={enabledSkillCount} size="small" style={{ marginLeft: 4 }} />
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
      {/* @AI_GENERATED: end */}

      {/* 创建 Modal */}
      <Modal title={createType === 'abtest' ? t('algorithmOps.createABTest') : t('algorithmOps.createRetrainTask')} open={createModalVisible} onOk={handleCreate} onCancel={() => setCreateModalVisible(false)} width={500}>
        <Form form={form} layout="vertical">
          {createType === 'abtest' ? (
            <>
              <Form.Item name="test_name" label={t('algorithmOps.testName')} rules={[{ required: true }]}><Input placeholder={t('algorithmOps.testNamePlaceholder')} /></Form.Item>
              <Row gutter={16}>
                <Col span={12}><Form.Item name="model_a" label={t('algorithmOps.modelALabel')} rules={[{ required: true }]}><Select placeholder={t('algorithmOps.select')} options={[{ value: 'pv-v2.0', label: td('光伏预测 v2.0') }]} /></Form.Item></Col>
                <Col span={12}><Form.Item name="model_b" label={t('algorithmOps.modelBLabel')} rules={[{ required: true }]}><Select placeholder={t('algorithmOps.select')} options={[{ value: 'pv-v2.1', label: td('光伏预测 v2.1') }]} /></Form.Item></Col>
              </Row>
              <Form.Item name="traffic_split" label={t('algorithmOps.trafficSplitLabel')} initialValue={30}><InputNumber min={5} max={95} style={{ width: '100%' }} /></Form.Item>
            </>
          ) : (
            <>
              <Form.Item name="model_id" label={t('algorithmOps.selectModelLabel')} rules={[{ required: true }]}><Select placeholder={t('algorithmOps.select')} options={[{ value: 'pv-power-001', label: td('光伏功率预测-LSTM') }]} /></Form.Item>
              <Form.Item name="retrain_type" label={t('algorithmOps.trainType')} initialValue="incremental"><Select options={[{ value: 'incremental', label: t('algorithmOps.incrementalTrainOption') }, { value: 'full', label: t('algorithmOps.fullTrainOption') }]} /></Form.Item>
              <Form.Item name="auto_deploy" label={t('algorithmOps.autoDeployLabel')} valuePropName="checked"><Switch /></Form.Item>
            </>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default AlgorithmOpsPage;
// @AI_GENERATED: end
