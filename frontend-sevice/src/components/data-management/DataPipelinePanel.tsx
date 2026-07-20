import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Collapse,
  List,
  Space,
  Spin,
  Tag,
  message,
} from 'antd';
import { CheckCircleOutlined, StopOutlined, SyncOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { getSchedulerStatus, startPipeline, stopPipeline } from '../../services/schedulerApi';
import type { Pipeline, PipelineStatus, SchedulerStatusResponse, TaskStatus } from '../../services/schedulerApi';

const PIPELINE_LABELS: Record<string, string> = {
  load_forecast: '负荷预测管线',
  pv_fault: '光伏故障诊断管线',
};

const TASK_LABELS: Record<string, string> = {
  mock_data_feed: '模拟喂数据',
  lf_data_pull: '数据拉取',
  lf_daily_rolling: '滚动训练+预测',
  lf_accuracy_backfill: '精度回填',
  lf_accuracy_monitor: '精度监控',
  pv_mock_data_feed: '模拟喂数据',
  pv_prediction: '故障预测',
};

const DEPRECATED_TASK_IDS = new Set(['pv_data_pull']);

function resolvePipelineFilter(storySlot?: string): Pipeline | null {
  if (storySlot === 'pv_fault') return 'pv_fault';
  if (!storySlot || storySlot === 'load_forecast' || storySlot === 'default') return 'load_forecast';
  return null;
}

interface DataPipelinePanelProps {
  /** storySlot — 传入时只展示该槽位对应的一条管线 */
  storySlot?: string;
}

const DataPipelinePanel: React.FC<DataPipelinePanelProps> = ({ storySlot }) => {
  const [messageApi, contextHolder] = message.useMessage();
  const [schedulerStatus, setSchedulerStatus] = useState<SchedulerStatusResponse | null>(null);
  const [schedulerLoading, setSchedulerLoading] = useState(false);
  const [pipelineActionLoading, setPipelineActionLoading] = useState<Record<string, boolean>>({});

  const pipelineFilter = resolvePipelineFilter(storySlot);
  const isPv = pipelineFilter === 'pv_fault';

  const loadSchedulerStatus = useCallback(async () => {
    setSchedulerLoading(true);
    try {
      const data = await getSchedulerStatus();
      setSchedulerStatus(data);
    } catch (error) {
      console.warn('Scheduler status unavailable:', error);
      setSchedulerStatus(null);
    } finally {
      setSchedulerLoading(false);
    }
  }, []);

  const handlePipelineToggle = async (pipeline: Pipeline, currentlyRunning: boolean) => {
    setPipelineActionLoading((prev) => ({ ...prev, [pipeline]: true }));
    try {
      if (currentlyRunning) {
        await stopPipeline(pipeline);
        messageApi.success(`管线 ${PIPELINE_LABELS[pipeline] ?? pipeline} 已停止`);
      } else {
        await startPipeline(pipeline);
        messageApi.success(`管线 ${PIPELINE_LABELS[pipeline] ?? pipeline} 已启动`);
      }
      await loadSchedulerStatus();
    } catch (error: any) {
      messageApi.error(`操作失败: ${error?.message ?? String(error)}`);
    } finally {
      setPipelineActionLoading((prev) => ({ ...prev, [pipeline]: false }));
    }
  };

  useEffect(() => {
    loadSchedulerStatus();
  }, [loadSchedulerStatus]);

  const visiblePipelines = useMemo(() => {
    if (!schedulerStatus) return [];
    return Object.entries(schedulerStatus.pipelines).filter(([pipelineName]) => {
      if (!pipelineFilter) return true;
      return pipelineName === pipelineFilter;
    });
  }, [schedulerStatus, pipelineFilter]);

  return (
    <>
      {contextHolder}
      <Spin spinning={schedulerLoading}>
        <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: '#8c98a8' }}>
            {isPv
              ? '管理光伏故障诊断定时任务：模拟喂数据 → 故障预测。'
              : pipelineFilter
                ? '管理负荷预测定时任务：数据拉取 → 滚动训练+预测 → 精度回填与监控。'
                : '管理两条独立数据管线的定时任务：负荷预测与光伏故障诊断。'}
          </span>
          <Button size="small" icon={<SyncOutlined />} onClick={loadSchedulerStatus}>
            刷新
          </Button>
        </div>

        {!schedulerStatus ? (
          <Alert type="info" message="调度器未初始化或后端不可达，请确认后端已启动且 DB_ENABLED=true。" />
        ) : visiblePipelines.length === 0 ? (
          <Alert type="info" message="当前槽位没有可展示的管线状态。" />
        ) : (
          visiblePipelines.map(([pipelineName, status]) => {
            const pipeline = pipelineName as Pipeline;
            const isRunning = (status as PipelineStatus).running;
            const isActioning = pipelineActionLoading[pipeline] ?? false;
            const tasks = (status as PipelineStatus).tasks.filter(
              (task) => !DEPRECATED_TASK_IDS.has(task.task_id),
            );

            return (
              <div
                key={pipeline}
                style={{ marginBottom: 24, border: '1px solid #f0f0f0', borderRadius: 8, padding: 16, background: '#fff' }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                  <Space>
                    <Badge status={isRunning ? 'processing' : 'default'} />
                    <strong style={{ fontSize: 14 }}>{PIPELINE_LABELS[pipeline] ?? pipeline}</strong>
                    <Tag color={isRunning ? 'success' : 'default'}>{isRunning ? '运行中' : '已停止'}</Tag>
                  </Space>
                  <Button
                    size="small"
                    type={isRunning ? 'default' : 'primary'}
                    danger={isRunning}
                    loading={isActioning}
                    icon={isRunning ? <StopOutlined /> : <CheckCircleOutlined />}
                    onClick={() => handlePipelineToggle(pipeline, isRunning)}
                  >
                    {isRunning ? '停止管线' : '启动管线'}
                  </Button>
                </div>

                <List
                  size="small"
                  dataSource={tasks}
                  renderItem={(task: TaskStatus) => (
                    <List.Item style={{ paddingLeft: 8 }}>
                      <div style={{ width: '100%' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <Space>
                            <Tag>{TASK_LABELS[task.task_id] ?? task.task_id}</Tag>
                            <Tag
                              color={
                                task.last_result === 'success'
                                  ? 'success'
                                  : task.last_result === 'failed'
                                  ? 'error'
                                  : task.last_result === 'skipped'
                                  ? 'warning'
                                  : 'default'
                              }
                            >
                              {task.last_result === 'success'
                                ? '成功'
                                : task.last_result === 'failed'
                                ? '失败'
                                : task.last_result === 'skipped'
                                ? '跳过'
                                : '未执行'}
                            </Tag>
                          </Space>
                          <div style={{ fontSize: 12, color: '#8c98a8' }}>
                            上次:{' '}
                            {task.last_execution_time ? dayjs(task.last_execution_time).format('MM-DD HH:mm:ss') : '—'}
                            &nbsp;|&nbsp;
                            下次:{' '}
                            {task.next_scheduled_time ? dayjs(task.next_scheduled_time).format('MM-DD HH:mm') : '—'}
                          </div>
                        </div>
                        {task.recent_failures.length > 0 && (
                          <Collapse
                            ghost
                            size="small"
                            style={{ marginTop: 4 }}
                            items={[
                              {
                                key: 'failures',
                                label: (
                                  <span style={{ fontSize: 12, color: '#ff4d4f' }}>
                                    最近 {task.recent_failures.length} 次失败记录
                                  </span>
                                ),
                                children: task.recent_failures.slice(0, 3).map((failure, index) => (
                                  <div key={index} style={{ fontSize: 11, color: '#595959', marginBottom: 4 }}>
                                    [{dayjs(failure.trigger_time).format('MM-DD HH:mm:ss')}]
                                    {failure.is_retry ? ' [重试]' : ''} {failure.error_message}
                                  </div>
                                )),
                              },
                            ]}
                          />
                        )}
                      </div>
                    </List.Item>
                  )}
                />
              </div>
            );
          })
        )}

        {!isPv && (
          <Alert
            type="success"
            showIcon
            style={{ marginTop: 16 }}
            message="MySQL 双写验证方法"
            description={
              <div style={{ fontSize: 12 }}>
                <p>1. 在精度运营其他 Tab 做任意操作（注册版本、回填精度等）</p>
                <p>2. 在 MySQL 中查询：<code>SELECT * FROM load_forecast.accuracy_metric LIMIT 5;</code></p>
                <p>3. 或调用：<code>GET /api/scheduler/status</code> 查看调度器状态 JSON</p>
              </div>
            }
          />
        )}
      </Spin>
    </>
  );
};

export default DataPipelinePanel;
