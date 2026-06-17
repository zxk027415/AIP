// @AI_GENERATED: Kiro v1.0
/**
 * Skill 训练监控页面
 * 实时监控 Skill 训练过程，展示训练曲线、日志和资源使用情况
 */
import { useState } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Space, Typography, Tag, Row, Col, Progress, List, Alert,
  Button, Spin, Empty, Tabs, Timeline,
} from 'antd';
import {
  ThunderboltOutlined, SyncOutlined, CheckCircleOutlined,
  ReloadOutlined, PauseCircleOutlined,
  LineChartOutlined, FileTextOutlined,
} from '@ant-design/icons';

const { Text, Paragraph } = Typography;

// 训练任务类型
interface TrainingJob {
  job_id: string;
  skill_id: string;
  skill_name: string;
  status: 'running' | 'paused' | 'completed' | 'failed';
  progress: number;
  current_epoch: number;
  total_epochs: number;
  current_loss: number;
  best_mape: number;
  started_at: string;
  elapsed_seconds: number;
  logs: string[];
  metrics_history: { epoch: number; loss: number; mape: number }[];
}

// 模拟训练任务
const MOCK_JOBS: TrainingJob[] = [
  {
    job_id: 'train-001',
    skill_id: 'skill-5a1b8c4d',
    skill_name: '锂电池SOC估计 Skill',
    status: 'running',
    progress: 45,
    current_epoch: 27,
    total_epochs: 60,
    current_loss: 0.0234,
    best_mape: 8.54,
    started_at: '2026-03-23T10:00:00',
    elapsed_seconds: 1245,
    logs: [
      '[10:00:00] 开始训练...',
      '[10:00:05] 加载数据集: 5000 样本',
      '[10:00:10] 模型初始化完成',
      '[10:05:00] Epoch 10/60 - Loss: 0.0456, MAPE: 12.34%',
      '[10:10:00] Epoch 20/60 - Loss: 0.0312, MAPE: 9.87%',
      '[10:15:00] Epoch 27/60 - Loss: 0.0234, MAPE: 8.54% (best)',
    ],
    metrics_history: [
      { epoch: 1, loss: 0.1234, mape: 25.6 },
      { epoch: 5, loss: 0.0876, mape: 18.2 },
      { epoch: 10, loss: 0.0456, mape: 12.34 },
      { epoch: 15, loss: 0.0389, mape: 10.5 },
      { epoch: 20, loss: 0.0312, mape: 9.87 },
      { epoch: 25, loss: 0.0256, mape: 8.9 },
      { epoch: 27, loss: 0.0234, mape: 8.54 },
    ],
  },
  {
    job_id: 'train-002',
    skill_id: 'skill-2365da5d',
    skill_name: '光伏发电功率预测 Skill',
    status: 'completed',
    progress: 100,
    current_epoch: 80,
    total_epochs: 80,
    current_loss: 0.0156,
    best_mape: 6.95,
    started_at: '2026-03-23T08:00:00',
    elapsed_seconds: 3600,
    logs: [
      '[08:00:00] 开始训练...',
      '[09:00:00] 训练完成',
      '[09:00:05] 最佳 MAPE: 6.95%',
    ],
    metrics_history: [],
  },
];

const SkillTrainingMonitorPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [loading, setLoading] = useState(false);
  const [jobs, setJobs] = useState<TrainingJob[]>(MOCK_JOBS);
  const [selectedJob, setSelectedJob] = useState<TrainingJob | null>(MOCK_JOBS[0]);

  // 模拟刷新
  const handleRefresh = () => {
    setLoading(true);
    setTimeout(() => setLoading(false), 500);
  };

  // 暂停/继续训练
  const handleTogglePause = (job: TrainingJob) => {
    setJobs(jobs.map(j => 
      j.job_id === job.job_id 
        ? { ...j, status: j.status === 'running' ? 'paused' : 'running' }
        : j
    ));
  };

  const formatDuration = (seconds: number) => {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h}h ${m}m ${s}s`;
  };

  return (
    <div style={{ padding: 24 }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <SyncOutlined style={{ fontSize: 24, color: '#1890ff' }} />
          <Typography.Title level={4} style={{ margin: 0 }}>{t('skillTrainingMonitor.title')}</Typography.Title>
        </Space>
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          实时监控 Skill 训练过程，查看训练曲线和日志
        </Paragraph>
      </div>

      <Row gutter={16}>
        {/* 左侧：训练任务列表 */}
        <Col span={8}>
          <Card 
            title={t('skillTrainingMonitor.trainingTasks')} 
            size="small"
            extra={<Button icon={<ReloadOutlined />} size="small" onClick={handleRefresh}>{t('skillTrainingMonitor.refresh')}</Button>}
          >
            <Spin spinning={loading}>
              <List
                dataSource={jobs}
                renderItem={job => (
                  <List.Item
                    style={{
                      cursor: 'pointer',
                      background: selectedJob?.job_id === job.job_id ? '#e6f7ff' : 'transparent',
                      padding: '12px',
                      borderRadius: 4,
                    }}
                    onClick={() => setSelectedJob(job)}
                  >
                    <List.Item.Meta
                      avatar={<ThunderboltOutlined style={{ fontSize: 20, color: '#722ed1' }} />}
                      title={
                        <Space>
                          <Text strong>{job.skill_name}</Text>
                          <Tag color={job.status === 'running' ? 'processing' : job.status === 'completed' ? 'success' : 'default'}>
                            {job.status === 'running' ? t('skillTrainingMonitor.statusTraining') : job.status === 'completed' ? t('skillTrainingMonitor.statusCompleted') : t('skillTrainingMonitor.statusPaused')}
                          </Tag>
                        </Space>
                      }
                      description={
                        <Space direction="vertical" size={4}>
                          <Progress percent={job.progress} size="small" status={job.status === 'running' ? 'active' : undefined} />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            Epoch {job.current_epoch}/{job.total_epochs} | MAPE: {job.best_mape}%
                          </Text>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            </Spin>
          </Card>
        </Col>

        {/* 右侧：详情 */}
        <Col span={16}>
          {selectedJob ? (
            <Card>
              {/* 任务信息 */}
              <div style={{ marginBottom: 16 }}>
                <Space>
                  <ThunderboltOutlined style={{ fontSize: 20, color: '#722ed1' }} />
                  <Typography.Title level={5} style={{ margin: 0 }}>{selectedJob.skill_name}</Typography.Title>
                  <Tag color={selectedJob.status === 'running' ? 'processing' : 'success'} icon={selectedJob.status === 'running' ? <SyncOutlined spin /> : <CheckCircleOutlined />}>
                    {selectedJob.status === 'running' ? t('skillTrainingMonitor.statusTraining') : t('skillTrainingMonitor.statusCompleted')}
                  </Tag>
                </Space>
              </div>

              {/* 进度和指标 */}
              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={6}>
                  <Card size="small">
                    <Text type="secondary">{t('skillTrainingMonitor.trainingProgress')}</Text>
                    <div style={{ marginTop: 8 }}>
                      <Progress type="circle" percent={selectedJob.progress} size={80} />
                    </div>
                  </Card>
                </Col>
                <Col span={6}>
                  <Card size="small">
                    <Text type="secondary">{t('skillTrainingMonitor.currentEpoch')}</Text>
                    <div style={{ fontSize: 24, fontWeight: 'bold', marginTop: 8 }}>
                      {selectedJob.current_epoch} / {selectedJob.total_epochs}
                    </div>
                  </Card>
                </Col>
                <Col span={6}>
                  <Card size="small">
                    <Text type="secondary">{t('skillTrainingMonitor.bestMape')}</Text>
                    <div style={{ fontSize: 24, fontWeight: 'bold', marginTop: 8, color: '#52c41a' }}>
                      {selectedJob.best_mape}%
                    </div>
                  </Card>
                </Col>
                <Col span={6}>
                  <Card size="small">
                    <Text type="secondary">{t('skillTrainingMonitor.elapsedTime')}</Text>
                    <div style={{ fontSize: 24, fontWeight: 'bold', marginTop: 8 }}>
                      {formatDuration(selectedJob.elapsed_seconds)}
                    </div>
                  </Card>
                </Col>
              </Row>

              {/* 操作按钮 */}
              {selectedJob.status === 'running' && (
                <Alert
                  message={t('skillTrainingMonitor.trainingInProgress')}
                  description={t('skillTrainingMonitor.trainingDesc')}
                  type="info"
                  showIcon
                  style={{ marginBottom: 16 }}
                  action={
                    <Button size="small" icon={<PauseCircleOutlined />} onClick={() => handleTogglePause(selectedJob)}>
                      暂停
                    </Button>
                  }
                />
              )}

              {/* Tabs: 曲线 / 日志 */}
              <Tabs defaultActiveKey="logs">
                <Tabs.TabPane tab={<><LineChartOutlined /> {t('skillTrainingMonitor.trainingCurve')}</>} key="curve">
                  <Card size="small">
                    {selectedJob.metrics_history.length > 0 ? (
                      <div style={{ padding: 16 }}>
                        <Text type="secondary">{t('skillTrainingMonitor.metricsChange')}</Text>
                        <div style={{ marginTop: 16 }}>
                          {selectedJob.metrics_history.map((m, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', marginBottom: 8 }}>
                              <Text style={{ width: 80 }}>Epoch {m.epoch}</Text>
                              <Progress 
                                percent={100 - m.mape * 2} 
                                size="small" 
                                style={{ flex: 1, marginRight: 16 }}
                                format={() => `MAPE: ${m.mape}%`}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <Empty description={t('skillTrainingMonitor.noCurveData')} />
                    )}
                  </Card>
                </Tabs.TabPane>
                <Tabs.TabPane tab={<><FileTextOutlined /> {t('skillTrainingMonitor.trainingLog')}</>} key="logs">
                  <Card size="small" style={{ background: '#1e1e1e', maxHeight: 300, overflow: 'auto' }}>
                    <Timeline style={{ padding: 16 }}>
                      {selectedJob.logs.map((log, i) => (
                        <Timeline.Item key={i} color={log.includes('best') ? 'green' : 'blue'}>
                          <Text style={{ color: '#d4d4d4', fontFamily: 'monospace', fontSize: 12 }}>{log}</Text>
                        </Timeline.Item>
                      ))}
                    </Timeline>
                  </Card>
                </Tabs.TabPane>
              </Tabs>
            </Card>
          ) : (
            <Card>
              <Empty description={t('skillTrainingMonitor.selectTask')} />
            </Card>
          )}
        </Col>
      </Row>
    </div>
  );
};

export default SkillTrainingMonitorPage;
// @AI_GENERATED: end
