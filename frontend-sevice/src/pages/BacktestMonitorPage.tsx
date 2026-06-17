// @AI_GENERATED: Kiro v1.0
import { useState, useEffect, useCallback } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import {
  Card, Select, Progress, Row, Col, Statistic, Tooltip, Tag, Timeline, Button,
  Space, message, Spin, Popconfirm, Badge,
} from 'antd';
import {
  PauseCircleOutlined, CaretRightOutlined, StopOutlined, ReloadOutlined,
  ClockCircleOutlined, CheckCircleOutlined, CloseCircleOutlined, SyncOutlined,
} from '@ant-design/icons';
import { backtestApi } from '../services/backtestApi';
import type { BacktestTask, BacktestRun } from '../types/backtest';
import { RUN_STATUS_CONFIG } from '../types/backtest';
import { td } from '../utils/dataTranslation';

const BacktestMonitorPage: React.FC = () => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const [tasks, setTasks] = useState<BacktestTask[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | undefined>();
  const [task, setTask] = useState<BacktestTask | null>(null);
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    backtestApi.listTasks({ page_size: 100 }).then(res => {
      setTasks(res.items);
      const active = res.items.find(t => t.status === 'running') || res.items[0];
      if (active) setSelectedTaskId(active.id);
    }).catch(() => message.error(t('backtestMonitor.loadFailed')));
  }, []);

  const fetchTaskData = useCallback(async () => {
    if (!selectedTaskId) return;
    setLoading(true);
    try {
      const [t, r] = await Promise.all([
        backtestApi.getTask(selectedTaskId),
        backtestApi.listRuns(selectedTaskId),
      ]);
      setTask(t);
      setRuns(r.runs || []);
    } catch {
      message.error(t('backtestMonitor.loadDataFailed'));
    } finally {
      setLoading(false);
    }
  }, [selectedTaskId]);

  useEffect(() => { fetchTaskData(); }, [fetchTaskData]);

  const handlePause = async () => {
    if (!selectedTaskId) return;
    await backtestApi.pauseTask(selectedTaskId);
    message.success(t('backtestMonitor.paused'));
    fetchTaskData();
  };

  const handleCancel = async () => {
    if (!selectedTaskId) return;
    await backtestApi.cancelTask(selectedTaskId);
    message.success(t('backtestMonitor.cancelled'));
    fetchTaskData();
  };

  const handleRetry = async (runId: string) => {
    if (!selectedTaskId) return;
    await backtestApi.retryRun(selectedTaskId, runId);
    message.success(t('backtestMonitor.retried'));
    fetchTaskData();
  };

  // Build matrix grid
  const dsIds = [...new Set(runs.map(r => r.dataset_id))];
  const algIds = [...new Set(runs.map(r => r.algorithm_id))];
  const dsNames: Record<string, string> = {};
  const algNames: Record<string, string> = {};
  const runMap: Record<string, BacktestRun> = {};
  runs.forEach(r => {
    dsNames[r.dataset_id] = r.dataset_name;
    algNames[r.algorithm_id] = r.algorithm_name;
    runMap[`${r.dataset_id}-${r.algorithm_id}`] = r;
  });

  const pending = runs.filter(r => r.status === 'pending').length;
  const running = runs.filter(r => r.status === 'running').length;
  const completed = runs.filter(r => r.status === 'completed').length;
  const failed = runs.filter(r => r.status === 'failed').length;
  const total = runs.length;
  const pct = total > 0 ? Math.round(((completed + failed) / total) * 100) : 0;

  // Timeline logs from runs
  const logs = runs
    .filter(r => r.started_at)
    .sort((a, b) => (b.started_at || '').localeCompare(a.started_at || ''))
    .slice(0, 30)
    .map(r => ({
      id: r.id,
      time: r.completed_at || r.started_at || '',
      status: r.status,
      text: `${td(r.dataset_name)} × ${td(r.algorithm_name)}`,
    }));

  const statusIcon = (s: string) => {
    if (s === 'completed') return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    if (s === 'failed') return <CloseCircleOutlined style={{ color: '#f5222d' }} />;
    if (s === 'running') return <SyncOutlined spin style={{ color: '#1890ff' }} />;
    return <ClockCircleOutlined style={{ color: '#d9d9d9' }} />;
  };

  return (
    <div style={{ padding: 24 }}>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space>
          <span>{t('backtestMonitor.selectTask')}</span>
          <Select
            value={selectedTaskId}
            onChange={setSelectedTaskId}
            style={{ width: 350 }}
            options={tasks.map(t => ({ value: t.id, label: `${td(t.name)} (${td(RUN_STATUS_CONFIG[t.status]?.label || t.status)})` }))}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchTaskData}>{t('backtestMonitor.refresh')}</Button>
          {task?.status === 'running' && (
            <>
              <Button icon={<PauseCircleOutlined />} onClick={handlePause}>{t('backtestMonitor.pause')}</Button>
              <Popconfirm title={t('backtestMonitor.confirmCancel')} onConfirm={handleCancel}>
                <Button danger icon={<StopOutlined />}>{t('backtestMonitor.cancel')}</Button>
              </Popconfirm>
            </>
          )}
          {task?.status === 'paused' && (
            <Button type="primary" icon={<CaretRightOutlined />}
              onClick={async () => { if (selectedTaskId) { await backtestApi.executeTask(selectedTaskId); fetchTaskData(); } }}>
              {td('恢复')}
            </Button>
          )}
        </Space>
      </Card>

      <Spin spinning={loading}>
        {/* Progress overview */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={12}>
            <Card size="small" title={t('backtestMonitor.overallProgress')}>
              <Progress percent={pct} status={task?.status === 'failed' ? 'exception' : task?.status === 'completed' ? 'success' : 'active'} />
              <Row gutter={16} style={{ marginTop: 12 }}>
                <Col span={6}><Statistic title={t('backtestMonitor.pending')} value={pending} valueStyle={{ fontSize: 20, color: '#d9d9d9' }} /></Col>
                <Col span={6}><Statistic title={t('backtestMonitor.executing')} value={running} valueStyle={{ fontSize: 20, color: '#1890ff' }} /></Col>
                <Col span={6}><Statistic title={t('backtestMonitor.completed')} value={completed} valueStyle={{ fontSize: 20, color: '#52c41a' }} /></Col>
                <Col span={6}><Statistic title={t('backtestMonitor.failed')} value={failed} valueStyle={{ fontSize: 20, color: '#f5222d' }} /></Col>
              </Row>
            </Card>
          </Col>
          <Col span={12}>
            <Card size="small" title={t('backtestMonitor.executionLog')} style={{ maxHeight: 220, overflow: 'auto' }}>
              {logs.length === 0 ? <span style={{ color: '#999' }}>{t('backtestMonitor.noLogs')}</span> : (
                <Timeline items={logs.map(l => ({
                  dot: statusIcon(l.status),
                  children: (
                    <span style={{ fontSize: 12 }}>
                      <Tag style={{ fontSize: 11 }}>{new Date(l.time).toLocaleTimeString('zh-CN')}</Tag>
                      {l.text}
                      <Badge status={RUN_STATUS_CONFIG[l.status as keyof typeof RUN_STATUS_CONFIG]?.color as any}
                        text={RUN_STATUS_CONFIG[l.status as keyof typeof RUN_STATUS_CONFIG]?.label} style={{ marginLeft: 8, fontSize: 11 }} />
                    </span>
                  ),
                }))} />
              )}
            </Card>
          </Col>
        </Row>

        {/* Matrix grid */}
        <Card size="small" title={`回测矩阵 (${dsIds.length}×${algIds.length})`}>
          {dsIds.length === 0 ? <span style={{ color: '#999' }}>{t('backtestMonitor.noRunData')}</span> : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13 }}>
                <thead>
                  <tr>
                    <th style={{ padding: '8px 12px', borderBottom: '2px solid #f0f0f0', textAlign: 'left', minWidth: 140 }}>数据集 \ 算法</th>
                    {algIds.map(aid => (
                      <th key={aid} style={{ padding: '8px 12px', borderBottom: '2px solid #f0f0f0', textAlign: 'center', minWidth: 120 }}>
                        {td(algNames[aid])}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {dsIds.map(did => (
                    <tr key={did}>
                      <td style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0', fontWeight: 500 }}>{td(dsNames[did])}</td>
                      {algIds.map(aid => {
                        const run = runMap[`${did}-${aid}`];
                        const cfg = run ? RUN_STATUS_CONFIG[run.status] : { color: '#d9d9d9', label: '无' };
                        return (
                          <td key={aid} style={{ padding: '6px 8px', borderBottom: '1px solid #f0f0f0', textAlign: 'center' }}>
                            <Tooltip title={run ? `${td(cfg.label)}${run.result ? ` | ${Object.entries(run.result).map(([k, v]) => `${k}: ${v}`).join(', ')}` : ''}` : td('无数据')}>
                              <div style={{
                                width: 36, height: 36, borderRadius: 6, margin: '0 auto',
                                backgroundColor: cfg.color, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                cursor: run?.status === 'failed' ? 'pointer' : 'default',
                              }}
                                onClick={() => { if (run?.status === 'failed') handleRetry(run.id); }}
                              >
                                {run?.status === 'running' && <SyncOutlined spin style={{ color: '#fff', fontSize: 14 }} />}
                                {run?.status === 'completed' && <CheckCircleOutlined style={{ color: '#fff', fontSize: 14 }} />}
                                {run?.status === 'failed' && <Tooltip title={td('点击重试')}><CloseCircleOutlined style={{ color: '#fff', fontSize: 14 }} /></Tooltip>}
                              </div>
                            </Tooltip>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </Spin>
    </div>
  );
};

export default BacktestMonitorPage;
// @AI_GENERATED: end
