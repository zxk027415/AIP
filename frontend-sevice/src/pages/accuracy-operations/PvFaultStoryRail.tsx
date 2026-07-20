// @AI_GENERATED: pv-fault-story-rail
/**
 * PvFaultStoryRail.tsx
 *
 * 光伏故障诊断运行证据状态带。形态对齐负荷预测 StoryRail，阶段内容映射光伏闭环：
 * Mock 喂数 → 定时预测 → 预测批次 → 人工审核 → 累计训练 → 模型工件。
 * 只解释已读取的真实接口数据，不伪造运行结果。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Button, Skeleton, Space, Tag, Tooltip, Typography } from 'antd';
import {
  ClusterOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import {
  schedulerTaskApi,
  type PvMockFeedPreview,
  type ScheduledTaskSummary,
} from '../../services/deploymentApi';
import {
  cumulativeTrainingApi,
  trainingWorkspaceApi,
} from '../../services/iterativeLabelingApi';

const { Text } = Typography;

type EvidenceTone = 'neutral' | 'pending' | 'healthy' | 'warning' | 'critical';

interface EvidenceStage {
  key: string;
  label: string;
  detail: string;
  tone: EvidenceTone;
  icon: React.ReactNode;
}

interface SlotOverviewPayload {
  model_ref?: string | null;
  latest_prediction_batch?: {
    batch_id?: string;
    prediction_count?: number;
    created_at?: string | null;
  } | null;
  prediction_summary?: {
    total_batches?: number;
    total_predictions?: number;
  };
  review_progress?: {
    total_sessions?: number;
    reviewed_sessions?: number;
    total_units?: number;
    reviewed_units?: number;
  };
  quality_metrics?: {
    accuracy?: number;
    macro_f1?: number;
    counted_units?: number;
  } | null;
  cumulative_training?: {
    effective_labeled_unit_count?: number;
    pending_change_count?: number;
    retrain_label_threshold?: number;
    next_retrain_in?: number;
    latest_snapshot_id?: string | null;
    latest_retrain_status?: string | null;
    latest_retrain_request_id?: string | null;
    latest_completed_model_ref?: string | null;
  };
}

interface PvFaultStoryRailProps {
  /** slot — 当前光伏运营槽位，正式主线为 pv_fault。 */
  slot: string;
  /** refreshing — 父页面统一刷新中。 */
  refreshing?: boolean;
  /** onRefresh — 父页面刷新回调（调度/总览等）。 */
  onRefresh?: () => void;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '暂无';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false });
}

function toneLabel(tone: EvidenceTone): string {
  if (tone === 'healthy') return '正常';
  if (tone === 'critical') return '需要处理';
  if (tone === 'warning') return '请留意';
  if (tone === 'pending') return '进行中';
  return '还没开始';
}

function findTask(tasks: ScheduledTaskSummary[], taskId: string): ScheduledTaskSummary | null {
  return tasks.find((task) => task.task_id === taskId) ?? null;
}

function buildStages({
  feedPreview,
  feedError,
  predictionTask,
  overview,
}: {
  feedPreview: PvMockFeedPreview | null;
  feedError: string | null;
  predictionTask: ScheduledTaskSummary | null;
  overview: SlotOverviewPayload | null;
}): EvidenceStage[] {
  const feedStage: EvidenceStage = feedError
    ? {
      key: 'feed',
      label: '新数据到达',
      detail: feedError,
      tone: 'warning',
      icon: <DatabaseOutlined />,
    }
    : !feedPreview
      ? {
        key: 'feed',
        label: '新数据到达',
        detail: '暂无喂数记录',
        tone: 'neutral',
        icon: <DatabaseOutlined />,
      }
      : feedPreview.exhausted
        ? {
          key: 'feed',
          label: '新数据到达',
          detail: `模拟源已喂完，最近日 ${feedPreview.current_business_date ?? '无'}`,
          tone: 'healthy',
          icon: <DatabaseOutlined />,
        }
        : feedPreview.requires_advance_confirmation
          ? {
            key: 'feed',
            label: '新数据到达',
            detail: `当前日 ${feedPreview.current_business_date} 已完成；下一日 ${feedPreview.next_business_date} 待确认（${feedPreview.next_source_row_count} 条）`,
            tone: 'pending',
            icon: <DatabaseOutlined />,
          }
          : {
            key: 'feed',
            label: '新数据到达',
            detail: `待喂 ${feedPreview.next_business_date}，约 ${feedPreview.next_source_row_count} 条 / ${feedPreview.next_device_count} 设备`,
            tone: feedPreview.current_business_date ? 'healthy' : 'pending',
            icon: <DatabaseOutlined />,
          };

  const predictionStage: EvidenceStage = !predictionTask
    ? {
      key: 'prediction',
      label: '自动预测',
      detail: '未找到预测任务',
      tone: 'neutral',
      icon: <ThunderboltOutlined />,
    }
    : predictionTask.status === 'failed'
      ? {
        key: 'prediction',
        label: '自动预测',
        detail: `任务失败，最近 ${formatDateTime(predictionTask.last_execution_time)}`,
        tone: 'critical',
        icon: <ThunderboltOutlined />,
      }
      : predictionTask.last_execution === 'failed'
        ? {
          key: 'prediction',
          label: '自动预测',
          detail: `最近失败于 ${formatDateTime(predictionTask.last_execution_time)}`,
          tone: 'critical',
          icon: <ThunderboltOutlined />,
        }
        : predictionTask.status === 'running'
          ? {
            key: 'prediction',
            label: '自动预测',
            detail: predictionTask.last_execution === 'success'
              ? `已启用，最近完成于 ${formatDateTime(predictionTask.last_execution_time)}`
              : '已启用，暂无成功记录',
            tone: predictionTask.last_execution === 'success' ? 'healthy' : 'pending',
            icon: <ThunderboltOutlined />,
          }
          : {
            key: 'prediction',
            label: '自动预测',
            detail: '任务已停止',
            tone: 'neutral',
            icon: <ThunderboltOutlined />,
          };

  const batchSummary = overview?.prediction_summary;
  const latestBatch = overview?.latest_prediction_batch;
  const batchStage: EvidenceStage = !overview
    ? {
      key: 'batches',
      label: '预测结果',
      detail: '暂无总览',
      tone: 'neutral',
      icon: <ClusterOutlined />,
    }
    : (batchSummary?.total_batches ?? 0) > 0
      ? {
        key: 'batches',
        label: '预测结果',
        detail: `已保存 ${batchSummary?.total_batches} 份 / ${batchSummary?.total_predictions ?? 0} 条；最新 ${latestBatch?.batch_id ?? '未知'}`,
        tone: 'healthy',
        icon: <ClusterOutlined />,
      }
      : {
        key: 'batches',
        label: '预测结果',
        detail: '暂无已保存结果',
        tone: 'pending',
        icon: <ClusterOutlined />,
      };

  const review = overview?.review_progress;
  const reviewedUnits = review?.reviewed_units ?? 0;
  const totalUnits = review?.total_units ?? 0;
  const reviewStage: EvidenceStage = !overview
    ? {
      key: 'review',
      label: '人工核对',
      detail: '暂无审核进度',
      tone: 'neutral',
      icon: <FileSearchOutlined />,
    }
    : totalUnits > 0 && reviewedUnits >= totalUnits
      ? {
        key: 'review',
        label: '人工核对',
        detail: `已完成 ${reviewedUnits}/${totalUnits}`,
        tone: 'healthy',
        icon: <FileSearchOutlined />,
      }
      : totalUnits > 0
        ? {
          key: 'review',
          label: '人工核对',
          detail: `进行中 ${reviewedUnits}/${totalUnits}，会话 ${review?.total_sessions ?? 0}`,
          tone: 'pending',
          icon: <FileSearchOutlined />,
        }
        : {
          key: 'review',
          label: '人工核对',
          detail: '暂无审核会话',
          tone: 'neutral',
          icon: <FileSearchOutlined />,
        };

  const cumulative = overview?.cumulative_training;
  const pending = cumulative?.pending_change_count ?? 0;
  const threshold = cumulative?.retrain_label_threshold ?? 20;
  const nextIn = cumulative?.next_retrain_in ?? Math.max(0, threshold - pending);
  const cumulativeStage: EvidenceStage = !cumulative
    ? {
      key: 'cumulative',
      label: '训练集积累',
      detail: '暂无累计记录',
      tone: 'neutral',
      icon: <ExperimentOutlined />,
    }
    : cumulative.latest_retrain_status === 'queued'
      ? {
        key: 'cumulative',
        label: '训练集积累',
        detail: '已达阈值，重训待执行',
        tone: 'warning',
        icon: <ExperimentOutlined />,
      }
      : pending > 0
        ? {
          key: 'cumulative',
          label: '训练集积累',
          detail: `有效真值 ${cumulative.effective_labeled_unit_count ?? 0}，距重训 ${nextIn} 次`,
          tone: 'pending',
          icon: <ExperimentOutlined />,
        }
        : cumulative.latest_snapshot_id
          ? {
            key: 'cumulative',
            label: '训练集积累',
            detail: '最新快照已就绪',
            tone: 'healthy',
            icon: <ExperimentOutlined />,
          }
          : {
            key: 'cumulative',
            label: '训练集积累',
            detail: `有效真值 ${cumulative.effective_labeled_unit_count ?? 0}，暂无快照`,
            tone: 'pending',
            icon: <ExperimentOutlined />,
          };

  const modelRef = overview?.model_ref
    ?? cumulative?.latest_completed_model_ref
    ?? null;
  const qm = overview?.quality_metrics;
  const modelStage: EvidenceStage = !modelRef
    ? {
      key: 'model',
      label: '可用模型',
      detail: cumulative?.latest_retrain_status === 'queued'
        ? '重训排队中，暂无新模型'
        : '暂无已完成模型',
      tone: cumulative?.latest_retrain_status === 'queued' ? 'pending' : 'neutral',
      icon: <ExperimentOutlined />,
    }
    : {
      key: 'model',
      label: '可用模型',
      detail: qm
        ? `${modelRef}；正确率 ${(qm.accuracy! * 100).toFixed(1)}%`
        : `${modelRef}（当前生产，等待预测真值回流）`,
      tone: 'healthy',
      icon: <ExperimentOutlined />,
    };

  return [feedStage, predictionStage, batchStage, reviewStage, cumulativeStage, modelStage];
}

const PvFaultStoryRail: React.FC<PvFaultStoryRailProps> = ({ slot, refreshing, onRefresh }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState<SlotOverviewPayload | null>(null);
  const [feedPreview, setFeedPreview] = useState<PvMockFeedPreview | null>(null);
  const [feedError, setFeedError] = useState<string | null>(null);
  const [predictionTask, setPredictionTask] = useState<ScheduledTaskSummary | null>(null);

  const loadRail = useCallback(async () => {
    setLoading(true);
    setFeedError(null);
    try {
      const [overviewResp, feedResp, tasksResp, cumulativeResp] = await Promise.all([
        trainingWorkspaceApi.getSlotOverview(slot).catch(() => null),
        schedulerTaskApi.getPvMockFeedStatus().catch((err: any) => {
          const detail = err?.response?.data?.detail || err?.message || '喂数状态读取失败';
          setFeedError(typeof detail === 'string' ? detail : '喂数状态读取失败');
          return null;
        }),
        schedulerTaskApi.listScheduledTasks().catch(() => ({ tasks: [] as ScheduledTaskSummary[] })),
        cumulativeTrainingApi.getState(slot).catch(() => null),
      ]);

      const merged: SlotOverviewPayload | null = overviewResp
        ? { ...(overviewResp as SlotOverviewPayload) }
        : null;
      if (merged && cumulativeResp && !merged.cumulative_training) {
        const latestSnapshot = (cumulativeResp as any).latest_snapshot || {};
        const latestRetrain = (cumulativeResp as any).latest_retrain_request || {};
        merged.cumulative_training = {
          effective_labeled_unit_count: (cumulativeResp as any).effective_labeled_unit_count,
          pending_change_count: (cumulativeResp as any).pending_change_count,
          retrain_label_threshold: (cumulativeResp as any).retrain_label_threshold,
          next_retrain_in: (cumulativeResp as any).next_retrain_in,
          latest_snapshot_id: latestSnapshot.snapshot_id || latestSnapshot.id || null,
          latest_retrain_status: latestRetrain.status || null,
          latest_retrain_request_id: latestRetrain.request_id || null,
          latest_completed_model_ref: (cumulativeResp as any).latest_completed_model_ref || null,
        };
        if (!merged.model_ref) {
          merged.model_ref = (cumulativeResp as any).latest_completed_model_ref || null;
        }
      }

      setOverview(merged);
      setFeedPreview(feedResp?.preview ?? null);
      setPredictionTask(findTask(tasksResp.tasks ?? [], 'pv_prediction'));
    } finally {
      setLoading(false);
    }
  }, [slot]);

  useEffect(() => {
    void loadRail();
  }, [loadRail]);

  useEffect(() => {
    if (refreshing) void loadRail();
  }, [refreshing, loadRail]);

  const stages = buildStages({ feedPreview, feedError, predictionTask, overview });

  const handleRefresh = () => {
    void loadRail();
    onRefresh?.();
  };

  return (
    <section className="load-forecast-story-rail" aria-label="光伏故障诊断运行证据状态带">
      <div className="story-rail-heading">
        <div>
          <Text className="story-rail-caption">光伏故障诊断进度</Text>
          <Text className="story-rail-description">
            槽位 <Text code>{slot}</Text>：新数据 → 自动预测 → 预测结果 → 人工核对 → 训练集积累 → 可用模型。仅展示已读取状态。
          </Text>
        </div>
        <Space size={4} wrap>
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/algorithm-deployment?tab=scheduler&slot=${encodeURIComponent(slot)}`)}
          >
            查看调度
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => navigate('/iterative-labeling')}
          >
            进入审核
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/algorithm-deployment?tab=model&slot=${encodeURIComponent(slot)}`)}
          >
            查看模型
          </Button>
          <Tooltip title="重新读取各阶段状态">
            <Button
              type="text"
              size="small"
              icon={<ReloadOutlined />}
              loading={loading || refreshing}
              onClick={handleRefresh}
              aria-label="刷新光伏进度"
            />
          </Tooltip>
        </Space>
      </div>

      {loading && !overview && !feedPreview ? (
        <div className="story-rail-loading story-rail-cols-6" aria-label="加载光伏运行证据">
          {Array.from({ length: 6 }, (_, index) => (
            <Skeleton.Button key={index} active size="small" block />
          ))}
        </div>
      ) : (
        <div className="story-rail-stages story-rail-cols-6">
          {stages.map((stage) => (
            <article key={stage.key} className="story-stage" data-tone={stage.tone}>
              <div className="story-stage-title">
                <span className="story-stage-icon" aria-hidden="true">{stage.icon}</span>
                <Text strong>{stage.label}</Text>
              </div>
              <Text className="story-stage-detail">{stage.detail}</Text>
              <Tag className="story-stage-tag" bordered={false}>{toneLabel(stage.tone)}</Tag>
            </article>
          ))}
        </div>
      )}
    </section>
  );
};

export default PvFaultStoryRail;
// @AI_GENERATED: end
