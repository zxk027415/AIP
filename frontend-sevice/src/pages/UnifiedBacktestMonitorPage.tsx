// @AI_GENERATED: Kiro v1.0
/**
 * 统一回测监控页面
 * 整合工作流回测监控和 Skill 训练监控，统一展示内容
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Card, Select, Progress, Row, Col, Statistic, Tag, Button,
  Space, message, Spin, Popconfirm, Badge, Segmented, Typography, Empty, Table, Collapse,
} from 'antd';
import {
  PauseCircleOutlined, StopOutlined, ReloadOutlined,
  ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
  ApartmentOutlined, ThunderboltOutlined, DashboardOutlined, EyeOutlined,
  FieldTimeOutlined,
} from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { backtestApi } from '../services/backtestApi';
import type { BacktestTask, BacktestRun } from '../types/backtest';
import { td } from '../utils/dataTranslation';

const { Text, Paragraph } = Typography;

// 统一的运行项类型
interface UnifiedRunItem {
  id: string;
  name: string;
  target_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  metrics?: Record<string, number>;
  error_message?: string;
}

// Skill 训练任务类型
interface SkillTrainingTask {
  task_id: string;
  skill_id: string;
  skill_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  current_epoch: number;
  total_epochs: number;
  current_loss: number;
  best_loss: number;
  eta_seconds: number;
  started_at?: string;
  completed_at?: string;
  logs: string[];
}

// 模拟 Skill 训练任务
const MOCK_SKILL_TRAINING: SkillTrainingTask[] = [
  {
    task_id: 'train-001',
    skill_id: 'skill-2365da5d',
    skill_name: '光伏发电功率预测 Skill',
    status: 'running',
    progress: 65,
    current_epoch: 52,
    total_epochs: 80,
    current_loss: 0.0234,
    best_loss: 0.0198,
    eta_seconds: 180,
    started_at: '2026-03-23T10:00:00',
    logs: [
      '[10:00:05] 开始训练...',
      '[10:00:10] Epoch 1/80, Loss: 0.1523',
      '[10:01:30] Epoch 20/80, Loss: 0.0456',
      '[10:02:45] Epoch 40/80, Loss: 0.0298',
      '[10:03:50] Epoch 52/80, Loss: 0.0234',
    ],
  },
  {
    task_id: 'train-002',
    skill_id: 'skill-8f4a2b1c',
    skill_name: '电网负荷预测 Skill',
    status: 'running',
    progress: 30,
    current_epoch: 30,
    total_epochs: 100,
    current_loss: 0.0512,
    best_loss: 0.0489,
    eta_seconds: 420,
    started_at: '2026-03-23T11:00:00',
    logs: [
      '[11:00:10] 开始训练...',
      '[11:01:00] Epoch 10/100, Loss: 0.0823',
      '[11:02:30] Epoch 30/100, Loss: 0.0512',
    ],
  },
  {
    task_id: 'train-003',
    skill_id: 'skill-3c7d9e2f',
    skill_name: '设备故障诊断 Skill',
    status: 'completed',
    progress: 100,
    current_epoch: 50,
    total_epochs: 50,
    current_loss: 0.0089,
    best_loss: 0.0089,
    eta_seconds: 0,
    started_at: '2026-03-23T08:00:00',
    completed_at: '2026-03-23T08:45:00',
    logs: [
      '[08:00:05] 开始训练...',
      '[08:45:00] 训练完成, 最终 Loss: 0.0089',
    ],
  },
];

const UnifiedBacktestMonitorPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialType = searchParams.get('type') === 'skill' ? 'skill' : 'workflow';
  
  const [monitorType, setMonitorType] = useState<'workflow' | 'skill'>(initialType);
  
  // 工作流回测监控状态
  const [tasks, setTasks] = useState<BacktestTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>();
  const [task, setTask] = useState<BacktestTask | null>(null);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [loading, setLoading] = useState(false);

  // Skill 训练监控状态
  const [skillTrainingTasks] = useState<SkillTrainingTask[]>(MOCK_SKILL_TRAINING);
  const [selectedSkillTaskId, setSelectedSkillTaskId] = useState<string>(MOCK_SKILL_TRAINING[0].task_id);

  // @AI_GENERATED: Kiro v1.0
  // 资源监控状态（GPU/CPU/内存/能耗）
  const [resourceMetrics, setResourceMetrics] = useState({
    gpu: { usage: 78, memory: 6.2, memoryTotal: 8, temperature: 72 },
    cpu: { usage: 45, cores: 8, frequency: 3.6 },
    memory: { used: 12.4, total: 32, percentage: 38.75 },
    energy: { power: 185, accumulated: 2.4, estimatedCost: 0.36 },
  });

  // 模拟资源监控数据实时更新
  useEffect(() => {
    const interval = setInterval(() => {
      setResourceMetrics(prev => ({
        gpu: {
          ...prev.gpu,
          usage: Math.min(100, Math.max(50, prev.gpu.usage + (Math.random() - 0.5) * 10)),
          memory: Math.min(prev.gpu.memoryTotal, Math.max(4, prev.gpu.memory + (Math.random() - 0.5) * 0.5)),
          temperature: Math.min(85, Math.max(60, prev.gpu.temperature + (Math.random() - 0.5) * 3)),
        },
        cpu: {
          ...prev.cpu,
          usage: Math.min(100, Math.max(20, prev.cpu.usage + (Math.random() - 0.5) * 15)),
        },
        memory: {
          ...prev.memory,
          used: Math.min(prev.memory.total, Math.max(8, prev.memory.used + (Math.random() - 0.5) * 1)),
          percentage: 0, // 将在下面重新计算
        },
        energy: {
          ...prev.energy,
          power: Math.min(250, Math.max(120, prev.energy.power + (Math.random() - 0.5) * 20)),
          accumulated: prev.energy.accumulated + 0.01,
          estimatedCost: (prev.energy.accumulated + 0.01) * 0.15,
        },
      }));
      // 重新计算内存百分比
      setResourceMetrics(prev => ({
        ...prev,
        memory: { ...prev.memory, percentage: (prev.memory.used / prev.memory.total) * 100 },
      }));
    }, 2000);
    return () => clearInterval(interval);
  }, []);
  // @AI_GENERATED: end

  const selectedSkillTask = useMemo(() => 
    skillTrainingTasks.find(t => t.task_id === selectedSkillTaskId) || null,
    [skillTrainingTasks, selectedSkillTaskId]
  );

  const handleTypeChange = (type: 'workflow' | 'skill') => {
    setMonitorType(type);
    setSearchParams({ type });
  };

  // 加载工作流回测任务
  useEffect(() => {
    if (monitorType === 'workflow') {
      backtestApi.listTasks({ page_size: 100 }).then(res => {
        setTasks(res.items);
        const active = res.items.find(t => t.status === 'running') || res.items[0];
        if (active) setSelectedTaskId(active.id);
      }).catch(() => message.error(t('unifiedBacktestMonitor.loadFailed')));
    }
  }, [monitorType]);

  const fetchTaskData = useCallback(async () => {
    if (!selectedTaskId || monitorType !== 'workflow') return;
    setLoading(true);
    try {
      const [t, r] = await Promise.all([
        backtestApi.getTask(selectedTaskId),
        backtestApi.listRuns(selectedTaskId),
      ]);
      setTask(t);
      setRuns(r.runs || []);
    } catch {
      message.error(t('unifiedBacktestMonitor.loadDataFailed'));
    } finally {
      setLoading(false);
    }
  }, [selectedTaskId, monitorType]);

  useEffect(() => { fetchTaskData(); }, [fetchTaskData]);

  const handlePause = async () => {
    if (!selectedTaskId) return;
    await backtestApi.pauseTask(selectedTaskId);
    message.success(t('unifiedBacktestMonitor.paused'));
    fetchTaskData();
  };

  const handleCancel = async () => {
    if (!selectedTaskId) return;
    await backtestApi.cancelTask(selectedTaskId);
    message.success(t('unifiedBacktestMonitor.cancelled'));
    fetchTaskData();
  };

  // @AI_GENERATED: Kiro v1.0
  // 转换为统一的运行项列表，按时间倒排（最新的在上面）
  const unifiedRuns: UnifiedRunItem[] = useMemo(() => {
    let items: UnifiedRunItem[];
    if (monitorType === 'workflow') {
      items = runs.map(r => ({
        id: r.id,
        name: td(r.dataset_name),
        target_name: td(r.algorithm_name),
        status: r.status as UnifiedRunItem['status'],
        progress: r.status === 'completed' ? 100 : r.status === 'running' ? 50 : 0,
        started_at: r.started_at,
        completed_at: r.completed_at,
        duration_seconds: r.execution_time_ms ? r.execution_time_ms / 1000 : undefined,
        metrics: r.result || undefined,
        error_message: r.error_message || undefined,
      }));
    } else {
      // Skill 训练转换为统一格式
      items = skillTrainingTasks.map(t => ({
        id: t.task_id,
        name: td(t.skill_name),
        target_name: `${t.current_epoch}/${t.total_epochs} Epochs`,
        status: t.status,
        progress: t.progress,
        started_at: t.started_at,
        completed_at: t.completed_at,
        duration_seconds: t.eta_seconds > 0 ? undefined : 
          (t.started_at && t.completed_at ? 
            (new Date(t.completed_at).getTime() - new Date(t.started_at).getTime()) / 1000 : undefined),
        metrics: { loss: t.current_loss, best_loss: t.best_loss },
        error_message: undefined,
      }));
    }
    // 按 started_at 时间倒排，最新的在上面
    return items.sort((a, b) => {
      const timeA = a.started_at ? new Date(a.started_at).getTime() : 0;
      const timeB = b.started_at ? new Date(b.started_at).getTime() : 0;
      return timeB - timeA; // 降序排列
    });
  }, [monitorType, runs, skillTrainingTasks]);
  // @AI_GENERATED: end

  // 统计数据
  const stats = useMemo(() => {
    const total = unifiedRuns.length;
    const running = unifiedRuns.filter(r => r.status === 'running').length;
    const completed = unifiedRuns.filter(r => r.status === 'completed').length;
    const failed = unifiedRuns.filter(r => r.status === 'failed').length;
    const avgProgress = total > 0 ? unifiedRuns.reduce((s, r) => s + r.progress, 0) / total : 0;
    return { total, running, completed, failed, avgProgress };
  }, [unifiedRuns]);

  // 统一的列定义
  const columns: ColumnsType<UnifiedRunItem> = [
    {
      title: monitorType === 'workflow' ? t('unifiedBacktestMonitor.dataset') : t('unifiedBacktestMonitor.skillName'),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name) => <Text strong>{name}</Text>,
    },
    {
      title: monitorType === 'workflow' ? t('unifiedBacktestMonitor.algorithm') : t('unifiedBacktestMonitor.trainingProgress'),
      dataIndex: 'target_name',
      key: 'target_name',
      width: 150,
    },
    {
      title: t('unifiedBacktestMonitor.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: UnifiedRunItem['status']) => {
        const statusMap = {
          pending: { label: t('unifiedBacktestMonitor.statusPending'), color: 'default', icon: <ClockCircleOutlined /> },
          running: { label: t('unifiedBacktestMonitor.statusRunning'), color: 'processing', icon: <SyncOutlined spin /> },
          completed: { label: t('unifiedBacktestMonitor.statusCompleted'), color: 'success', icon: <CheckCircleOutlined /> },
          failed: { label: t('unifiedBacktestMonitor.statusFailed'), color: 'error', icon: <CloseCircleOutlined /> },
        };
        const cfg = statusMap[status];
        return <Tag color={cfg.color} icon={cfg.icon}>{cfg.label}</Tag>;
      },
    },
    {
      title: t('unifiedBacktestMonitor.progress'),
      dataIndex: 'progress',
      key: 'progress',
      width: 150,
      render: (progress, record) => (
        <Progress 
          percent={progress} 
          size="small" 
          status={record.status === 'failed' ? 'exception' : record.status === 'running' ? 'active' : 'normal'}
        />
      ),
    },
    {
      title: t('unifiedBacktestMonitor.duration'),
      key: 'duration',
      width: 100,
      render: (_, record) => {
        if (record.duration_seconds) {
          const mins = Math.floor(record.duration_seconds / 60);
          const secs = Math.round(record.duration_seconds % 60);
          return <Text>{mins}{t('unifiedBacktestMonitor.min')}{secs}{t('unifiedBacktestMonitor.sec')}</Text>;
        }
        if (record.status === 'running' && record.started_at) {
          return <Tag color="blue" icon={<SyncOutlined spin />}>{t('unifiedBacktestMonitor.inProgress')}</Tag>;
        }
        return <Text type="secondary">-</Text>;
      },
    },
    {
      title: t('unifiedBacktestMonitor.metrics'),
      key: 'metrics',
      width: 150,
      render: (_, record) => {
        if (!record.metrics) return <Text type="secondary">-</Text>;
        if (monitorType === 'workflow') {
          const rmse = record.metrics.rmse;
          const r2 = record.metrics.r2;
          return (
            <Space direction="vertical" size={0}>
              {rmse !== undefined && <Text style={{ fontSize: 12 }}>RMSE: {rmse.toFixed(4)}</Text>}
              {r2 !== undefined && <Text style={{ fontSize: 12 }}>R²: {r2.toFixed(4)}</Text>}
            </Space>
          );
        } else {
          return (
            <Space direction="vertical" size={0}>
              <Text style={{ fontSize: 12 }}>Loss: {record.metrics.loss?.toFixed(4)}</Text>
              <Text style={{ fontSize: 12, color: '#52c41a' }}>Best: {record.metrics.best_loss?.toFixed(4)}</Text>
            </Space>
          );
        }
      },
    },
  ];

  // 当前训练对象名称
  const currentTrainingTarget = useMemo(() => {
    if (monitorType === 'skill') {
      const runningTask = skillTrainingTasks.find(t => t.status === 'running');
      return runningTask ? td(runningTask.skill_name) : (selectedSkillTask?.skill_name ? td(selectedSkillTask.skill_name) : t('unifiedBacktestMonitor.none'));
    } else {
      const runningRun = runs.find(r => r.status === 'running');
      return runningRun
        ? `${td(runningRun.dataset_name)} + ${td(runningRun.algorithm_name)}`
        : (task?.name ? td(task.name) : t('unifiedBacktestMonitor.none'));
    }
  }, [monitorType, skillTrainingTasks, selectedSkillTask, runs, task]);

  return (
    <div style={{ padding: 24 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <DashboardOutlined style={{ fontSize: 24, color: '#1890ff' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>{t('unifiedBacktestMonitor.title')}</Typography.Title>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          {t('unifiedBacktestMonitor.subtitle')}
        </Paragraph>
      </div>

      {/* 类型切换和筛选 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Segmented
            value={monitorType}
            onChange={(v) => handleTypeChange(v as 'workflow' | 'skill')}
            options={[
              { value: 'workflow', label: <><ApartmentOutlined /> {t('unifiedBacktestMonitor.workflowBacktest')}</> },
              { value: 'skill', label: <><ThunderboltOutlined /> {t('unifiedBacktestMonitor.skillTraining')}</> },
            ]}
          />
          {monitorType === 'workflow' ? (
            <>
              <Select
                style={{ width: 280 }}
                placeholder={t('unifiedBacktestMonitor.selectBacktestTask')}
                value={selectedTaskId}
                onChange={setSelectedTaskId}
                options={tasks.map(t => ({
                  value: t.id,
                  label: (
                    <Space>
                      <Badge status={t.status === 'running' ? 'processing' : t.status === 'completed' ? 'success' : 'default'} />
                      {td(t.name)}
                    </Space>
                  ),
                }))}
              />
              <Button icon={<ReloadOutlined />} onClick={fetchTaskData}>{t('unifiedBacktestMonitor.refresh')}</Button>
              {task?.status === 'running' && (
                <>
                  <Button icon={<PauseCircleOutlined />} onClick={handlePause}>{t('unifiedBacktestMonitor.pause')}</Button>
                  <Popconfirm title={t('unifiedBacktestMonitor.confirmCancel')} onConfirm={handleCancel}>
                    <Button danger icon={<StopOutlined />}>{t('unifiedBacktestMonitor.cancel')}</Button>
                  </Popconfirm>
                </>
              )}
            </>
          ) : (
            <>
              <Select
                style={{ width: 280 }}
                placeholder={t('unifiedBacktestMonitor.selectTrainingTask')}
                value={selectedSkillTaskId}
                onChange={setSelectedSkillTaskId}
                options={skillTrainingTasks.map(t => ({
                  value: t.task_id,
                  label: (
                    <Space>
                      <Badge status={t.status === 'running' ? 'processing' : t.status === 'completed' ? 'success' : 'default'} />
                      {td(t.skill_name)}
                    </Space>
                  ),
                }))}
              />
              <Button icon={<ReloadOutlined />}>{t('unifiedBacktestMonitor.refresh')}</Button>
              {/* @AI_GENERATED: Kiro v1.0 */}
              {selectedSkillTask?.status === 'running' && (
                <>
                  <Button icon={<PauseCircleOutlined />} onClick={() => message.info(t('unifiedBacktestMonitor.skillPaused'))}>{t('unifiedBacktestMonitor.pause')}</Button>
                  <Popconfirm title={t('unifiedBacktestMonitor.confirmCancelTraining')} onConfirm={() => message.success(t('unifiedBacktestMonitor.skillCancelled'))}>
                    <Button danger icon={<StopOutlined />}>{t('unifiedBacktestMonitor.cancel')}</Button>
                  </Popconfirm>
                </>
              )}
              {/* @AI_GENERATED: end */}
            </>
          )}
          <Button 
            type="link" 
            icon={<EyeOutlined />} 
            onClick={() => navigate(`/backtest/unified/results?type=${monitorType}`)}
          >
            {t('unifiedBacktestMonitor.viewResults')}
          </Button>
        </Space>
      </Card>

      {/* 统一的统计卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small">
            <Statistic 
              title={t('unifiedBacktestMonitor.totalTasks')} 
              value={stats.total} 
              prefix={<FieldTimeOutlined />} 
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic 
              title={t('unifiedBacktestMonitor.executing')} 
              value={stats.running} 
              prefix={<SyncOutlined spin={stats.running > 0} />} 
              valueStyle={{ color: '#1890ff' }} 
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic 
              title={t('unifiedBacktestMonitor.completed')} 
              value={stats.completed} 
              prefix={<CheckCircleOutlined />} 
              valueStyle={{ color: '#52c41a' }} 
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small">
            <Statistic 
              title={t('unifiedBacktestMonitor.overallProgress')} 
              value={Math.round(stats.avgProgress)} 
              suffix="%" 
              prefix={<DashboardOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* @AI_GENERATED: Kiro v1.0 */}
      {/* 资源监控卡片 (GPU/CPU/内存/能耗) */}
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Card size="small" styles={{ body: { padding: '8px 12px' } }} style={{ background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }}>
            <div style={{ color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 12 }}>GPU</Text>
                <div style={{ fontSize: 20, fontWeight: 600 }}>{resourceMetrics.gpu.usage.toFixed(1)}%</div>
              </div>
              <Progress type="circle" size={40} percent={resourceMetrics.gpu.usage} strokeColor="#fff" trailColor="rgba(255,255,255,0.3)" format={() => <span style={{ color: '#fff', fontSize: 10 }}>{resourceMetrics.gpu.temperature}°</span>} />
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" styles={{ body: { padding: '8px 12px' } }} style={{ background: 'linear-gradient(135deg, #11998e 0%, #38ef7d 100%)' }}>
            <div style={{ color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 12 }}>CPU</Text>
                <div style={{ fontSize: 20, fontWeight: 600 }}>{resourceMetrics.cpu.usage.toFixed(1)}%</div>
              </div>
              <Progress type="circle" size={40} percent={resourceMetrics.cpu.usage} strokeColor="#fff" trailColor="rgba(255,255,255,0.3)" format={() => <span style={{ color: '#fff', fontSize: 10 }}>{resourceMetrics.cpu.cores}{t('unifiedBacktestMonitor.cores')}</span>} />
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" styles={{ body: { padding: '8px 12px' } }} style={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)' }}>
            <div style={{ color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 12 }}>{t('unifiedBacktestMonitor.memory')}</Text>
                <div style={{ fontSize: 20, fontWeight: 600 }}>{resourceMetrics.memory.percentage.toFixed(1)}%</div>
              </div>
              <Progress type="circle" size={40} percent={resourceMetrics.memory.percentage} strokeColor="#fff" trailColor="rgba(255,255,255,0.3)" format={() => <span style={{ color: '#fff', fontSize: 10 }}>{resourceMetrics.memory.used.toFixed(0)}G</span>} />
            </div>
          </Card>
        </Col>
        <Col span={6}>
          <Card size="small" styles={{ body: { padding: '8px 12px' } }} style={{ background: 'linear-gradient(135deg, #fa709a 0%, #fee140 100%)' }}>
            <div style={{ color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <Text style={{ color: 'rgba(255,255,255,0.85)', fontSize: 12 }}>{t('unifiedBacktestMonitor.energy')}</Text>
                <div style={{ fontSize: 20, fontWeight: 600 }}>{resourceMetrics.energy.power.toFixed(0)}W</div>
              </div>
              <Progress type="circle" size={40} percent={(resourceMetrics.energy.power / 250) * 100} strokeColor="#fff" trailColor="rgba(255,255,255,0.3)" format={() => <span style={{ color: '#fff', fontSize: 9 }}>{resourceMetrics.energy.accumulated.toFixed(1)}kWh</span>} />
            </div>
          </Card>
        </Col>
      </Row>
      {/* @AI_GENERATED: end */}

      {/* 监控内容 */}
      <Spin spinning={loading}>
        <Row gutter={16}>
          {/* 左侧：任务列表 */}
          <Col span={16}>
            <Card 
              title={monitorType === 'workflow' ? t('unifiedBacktestMonitor.backtestRunList') : t('unifiedBacktestMonitor.skillTrainingList')} 
              size="small"
              extra={
                <Space>
                  <Tag color="blue">{stats.running} {t('unifiedBacktestMonitor.statusRunning')}</Tag>
                  <Tag color="green">{stats.completed} {t('unifiedBacktestMonitor.statusCompleted')}</Tag>
                  {stats.failed > 0 && <Tag color="red">{stats.failed} {t('unifiedBacktestMonitor.statusFailed')}</Tag>}
                </Space>
              }
            >
              {unifiedRuns.length > 0 ? (
                <Table
                  dataSource={unifiedRuns}
                  columns={columns}
                  rowKey="id"
                  size="small"
                  pagination={false}
                  scroll={{ y: 350 }}
                />
              ) : (
                <Empty description={monitorType === 'workflow' ? t('unifiedBacktestMonitor.selectBacktestTask') : t('unifiedBacktestMonitor.noTrainingTasks')} />
              )}
            </Card>
          </Col>

          {/* 右侧：执行日志（按任务折叠） */}
          <Col span={8}>
            <Card 
              title={
                <Space>
                  <span>{t('unifiedBacktestMonitor.executionLog')}</span>
                  {stats.running > 0 && <Tag color="processing" icon={<SyncOutlined spin />}>{t('unifiedBacktestMonitor.statusTraining')}</Tag>}
                </Space>
              } 
              size="small"
              extra={
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {monitorType === 'skill' ? skillTrainingTasks.length : (task ? 1 : 0)} {t('unifiedBacktestMonitor.tasks')}
                </Text>
              }
              styles={{ body: { maxHeight: 500, overflow: 'auto', padding: '12px' } }}
            >
              {/* 当前训练对象标注 */}
              <div style={{ 
                background: '#f6ffed', 
                border: '1px solid #b7eb8f', 
                borderRadius: 6, 
                padding: '8px 12px', 
                marginBottom: 12 
              }}>
                <Text type="secondary" style={{ fontSize: 12 }}>{t('unifiedBacktestMonitor.currentTarget')}</Text>
                <div style={{ marginTop: 4 }}>
                  <Text strong style={{ color: '#52c41a', fontSize: 14 }}>
                    <ThunderboltOutlined style={{ marginRight: 6 }} />
                    {currentTrainingTarget}
                  </Text>
                </div>
              </div>

              {/* 按任务/测试批次折叠的日志 */}
              {monitorType === 'skill' ? (
                <Collapse 
                  size="small" 
                  defaultActiveKey={skillTrainingTasks.filter(t => t.status === 'running').map(t => t.task_id)}
                  items={skillTrainingTasks.map((taskItem) => ({
                    key: taskItem.task_id,
                    label: (
                      <Space>
                        <Badge status={taskItem.status === 'running' ? 'processing' : taskItem.status === 'completed' ? 'success' : 'default'} />
                        <Text style={{ fontSize: 13 }}>{td(taskItem.skill_name)}</Text>
                        <Tag color={taskItem.status === 'running' ? 'blue' : taskItem.status === 'completed' ? 'green' : 'default'}>
                          {taskItem.current_epoch}/{taskItem.total_epochs}
                        </Tag>
                      </Space>
                    ),
                    children: (
                      <div style={{ fontSize: 12 }}>
                        {taskItem.logs.map((log, idx) => (
                          <div key={idx} style={{ 
                            padding: '4px 0', 
                            borderBottom: idx < taskItem.logs.length - 1 ? '1px dashed #f0f0f0' : 'none',
                            color: log.includes('完成') ? '#52c41a' : log.includes('开始') ? '#1890ff' : '#666'
                          }}>
                            {td(log)}
                          </div>
                        ))}
                        {taskItem.status === 'running' && (
                          <div style={{ marginTop: 8, padding: '6px 8px', background: '#e6f7ff', borderRadius: 4 }}>
                            <Space size={16}>
                              <Text style={{ fontSize: 12 }}>Loss: <Text strong>{taskItem.current_loss.toFixed(4)}</Text></Text>
                              <Text style={{ fontSize: 12 }}>Best: <Text strong style={{ color: '#52c41a' }}>{taskItem.best_loss.toFixed(4)}</Text></Text>
                              {taskItem.eta_seconds > 0 && <Text style={{ fontSize: 12 }} type="secondary">{t('unifiedBacktestMonitor.remaining', { minutes: Math.round(taskItem.eta_seconds / 60) })}</Text>}
                            </Space>
                          </div>
                        )}
                      </div>
                    ),
                  }))}
                />
              ) : (
                task ? (
                  <Collapse 
                    size="small" 
                    defaultActiveKey={['current-task']}
                    items={[
                      {
                        key: 'current-task',
                        label: (
                          <Space>
                            <Badge status={task.status === 'running' ? 'processing' : task.status === 'completed' ? 'success' : 'default'} />
                            <Text style={{ fontSize: 13 }}>{td(task.name)}</Text>
                            <Tag color={task.status === 'running' ? 'blue' : task.status === 'completed' ? 'green' : 'default'}>
                              {task.completed_runs}/{task.total_runs}
                            </Tag>
                          </Space>
                        ),
                        children: (
                          <div style={{ fontSize: 12 }}>
                            {runs.filter(r => r.status === 'completed' || r.status === 'running').slice(0, 8).map((r, idx) => (
                              <div key={r.id} style={{ 
                                padding: '4px 0', 
                                borderBottom: idx < 7 ? '1px dashed #f0f0f0' : 'none',
                                color: r.status === 'completed' ? '#52c41a' : r.status === 'running' ? '#1890ff' : '#666'
                              }}>
                                <Space>
                                  {r.status === 'running' ? <SyncOutlined spin style={{ color: '#1890ff' }} /> : <CheckCircleOutlined style={{ color: '#52c41a' }} />}
                                  <Text style={{ fontSize: 12 }}>{td(r.algorithm_name)}</Text>
                                  <Text type="secondary" style={{ fontSize: 11 }}>{td(r.dataset_name)}</Text>
                                  {r.status === 'completed' && r.result && (
                                    <Text style={{ fontSize: 11, color: '#52c41a' }}>RMSE: {r.result.rmse?.toFixed(4)}</Text>
                                  )}
                                </Space>
                              </div>
                            ))}
                          </div>
                        ),
                      },
                    ]}
                  />
                ) : (
                  <Empty description={t('unifiedBacktestMonitor.selectBacktestTask')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )
              )}
            </Card>
          </Col>
        </Row>
      </Spin>
    </div>
  );
};

export default UnifiedBacktestMonitorPage;
// @AI_GENERATED: end
