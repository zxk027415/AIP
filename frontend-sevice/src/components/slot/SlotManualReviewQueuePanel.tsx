/**
 * SlotManualReviewQueuePanel — 人工打标队列（pv_day / pv_point / pv_tsc）
 * 一次完整检测（按天 / execution）= 一条 rev-* 会话，会话内多 unit 可框选审核。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Empty,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { EditOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  reviewSessionApi,
  type DetectionReviewGroup,
  type ReviewSessionSummary,
} from '../../services/iterativeLabelingApi';
import { slotObservabilityApi } from '../../services/slotObservabilityApi';

const { Text } = Typography;

export type ManualReviewSlot = 'pv_day' | 'pv_point' | 'pv_tsc';

interface Props {
  slot: ManualReviewSlot;
  onChanged?: () => void;
}

// @AI_GENERATED: 统一解析后端错误详情，避免把失败伪装成空态。
function extractErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: string | { message?: string } } }; message?: string })
    ?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (typeof detail === 'object' && detail?.message) return detail.message;
  return (err as Error)?.message || fallback;
}
// @AI_GENERATED: end

const SlotManualReviewQueuePanel: React.FC<Props> = ({ slot, onChanged }) => {
  const navigate = useNavigate();
  // @AI_GENERATED: session 与 queue 各自独立的 loading/error，任一路失败都不静默吞掉。
  const isTsc = slot === 'pv_tsc';
  const [sessionLoading, setSessionLoading] = useState(false);
  const [queueLoading, setQueueLoading] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);
  const [mocking, setMocking] = useState(false);
  const [sessions, setSessions] = useState<ReviewSessionSummary[]>([]);
  const [groups, setGroups] = useState<DetectionReviewGroup[]>([]);

  const loadSessions = useCallback(async () => {
    setSessionLoading(true);
    setSessionError(null);
    try {
      const sessionResp = await reviewSessionApi.listReviewSessions(slot);
      const sessionRows = Array.isArray(sessionResp?.sessions) ? sessionResp.sessions : [];
      setSessions(sessionRows as ReviewSessionSummary[]);
    } catch (err: unknown) {
      setSessionError(extractErrorMessage(err, '加载审核会话失败'));
    } finally {
      setSessionLoading(false);
    }
  }, [slot]);

  const loadQueue = useCallback(async () => {
    setQueueLoading(true);
    setQueueError(null);
    try {
      const queueResp = await reviewSessionApi.listAnnotationCandidateReviewQueue(slot);
      const groupRows = Array.isArray(queueResp?.groups) ? queueResp.groups : [];
      setGroups(groupRows as DetectionReviewGroup[]);
    } catch (err: unknown) {
      setQueueError(extractErrorMessage(err, '加载待审核检测组失败'));
    } finally {
      setQueueLoading(false);
    }
  }, [slot]);

  const refresh = useCallback(async () => {
    await Promise.allSettled([loadSessions(), loadQueue()]);
  }, [loadSessions, loadQueue]);
  // @AI_GENERATED: end

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const handleStartGroupReview = useCallback(async (record: DetectionReviewGroup) => {
    setActingId(record.detection_group_id);
    try {
      const created = await reviewSessionApi.createReviewSessionFromDetectionGroup({
        slot,
        detection_group_id: record.detection_group_id,
      });
      message.success(`已创建审核会话 ${created.review_id}（${record.candidate_count} 个待审单元）`);
      await refresh();
      onChanged?.();
      navigate(`/iterative-labeling/review?review_id=${encodeURIComponent(created.review_id)}&slot=${encodeURIComponent(slot)}`);
    } catch (err: unknown) {
      message.error(extractErrorMessage(err, '创建审核会话失败'));
    } finally {
      setActingId(null);
    }
  }, [navigate, onChanged, refresh, slot]);

  const groupColumns: ColumnsType<DetectionReviewGroup> = useMemo(() => [
    {
      title: '检测日',
      dataIndex: 'detection_date',
      key: 'detection_date',
      width: 120,
    },
    {
      title: '检测组',
      dataIndex: 'detection_group_id',
      key: 'detection_group_id',
      ellipsis: true,
    },
    {
      title: '待审单元',
      dataIndex: 'candidate_count',
      key: 'candidate_count',
      width: 100,
      render: (v: number) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: 'execution',
      dataIndex: 'source_execution_id',
      key: 'source_execution_id',
      ellipsis: true,
      render: (v: string) => <Text code style={{ fontSize: 11 }}>{v || '—'}</Text>,
    },
    {
      title: '操作',
      key: 'actions',
      width: 120,
      render: (_, record) => (
        <Button
          size="small"
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={actingId === record.detection_group_id}
          onClick={() => void handleStartGroupReview(record)}
        >
          开始审核
        </Button>
      ),
    },
  ], [actingId, handleStartGroupReview]);

  const sessionColumns: ColumnsType<ReviewSessionSummary> = useMemo(() => [
    {
      title: '会话 ID',
      dataIndex: 'review_id',
      key: 'review_id',
      render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text>,
    },
    {
      title: '检测日',
      key: 'detection_date',
      width: 110,
      render: (_, r) => r.detection_date || '—',
    },
    {
      title: '来源',
      key: 'origin',
      width: 120,
      render: (_, r) => (
        r.review_kind === 'annotation_candidate_review'
        || r.review_kind === 'tsc_device_day_review'
        || r.annotation_candidate_id
          ? <Tag color="purple">滚动检测</Tag>
          : <Tag>人工</Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string) => (
        v === 'reviewed'
          ? <Tag color="success">已完成</Tag>
          : <Tag color="processing">审核中</Tag>
      ),
    },
    {
      title: '进度',
      key: 'progress',
      width: 120,
      render: (_, r) => `${r.reviewed_count}/${r.total_count}`,
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_, r) => (
        <Button
          size="small"
          type="primary"
          icon={<EditOutlined />}
          onClick={() => navigate(`/iterative-labeling/review?review_id=${encodeURIComponent(r.review_id)}&slot=${encodeURIComponent(slot)}`)}
        >
          {r.status === 'reviewed' ? '查看' : '继续审核'}
        </Button>
      ),
    },
  ], [navigate, slot]);

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* @AI_GENERATED: 三槽通用说明；pv_tsc 单独解释设备日 + 重叠窗口证据与真实调度推进。 */}
      <Alert
        type="info"
        showIcon
        message={`${slot} 人工打标队列`}
        description={
          isTsc
            ? '一次完整滚动检测（同一 pv_tsc_predict 批次）对应一条 rev 会话；一级单元是设备日最终标签，二级证据是 MultiRocket 重叠窗口。待审检测组由真实 pv_tsc_predict Challenger 调度产生，本页不提供演示推进。'
            : '一次完整滚动检测（按天 / 同一 execution）对应一条 rev 会话；会话内按设备日逐条框选，不是每条候选单独一条会话。gold 模拟只打 holdout，纳入角色是 holdout，不会进入训练冻结。'
        }
      />
      {/* @AI_GENERATED: end */}

      <Card
        size="small"
        title={`待审核检测（${groups.length} 组）`}
        extra={(
          <Space>
            {/* @AI_GENERATED: pv_tsc 不接 loop_demo gold，禁用演示推进，仅双槽保留。 */}
            {!isTsc && (
              <Button
                size="small"
                loading={mocking}
                onClick={async () => {
                  setMocking(true);
                  try {
                    const result = await slotObservabilityApi.mockGoldReview(slot);
                    message.success(result.note || `已推进演示日 ${result.review_id || ''}`);
                    onChanged?.();
                    void refresh();
                  } catch (err: unknown) {
                    message.error(extractErrorMessage(err, 'mock 审核失败'));
                  } finally {
                    setMocking(false);
                  }
                }}
              >
                推进演示下一天（不入库）
              </Button>
            )}
            {/* @AI_GENERATED: end */}
            <Button size="small" icon={<ReloadOutlined />} onClick={() => void loadQueue()} loading={queueLoading}>
              刷新
            </Button>
          </Space>
        )}
      >
        {/* @AI_GENERATED: 待审核检测组独立 error/empty；错误绝不伪装成空态。 */}
        {queueError ? (
          <Alert
            type="error"
            showIcon
            message="加载待审核检测组失败"
            description={queueError}
            action={<Button size="small" onClick={() => void loadQueue()}>重试</Button>}
          />
        ) : groups.length === 0 ? (
          <Empty
            description={
              queueLoading
                ? '加载中…'
                : isTsc
                  ? '暂无待审核检测组，等待 pv_tsc_predict 调度产出新的设备日检测'
                  : '暂无待审核检测组'
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Table
            size="small"
            rowKey="detection_group_id"
            loading={queueLoading}
            columns={groupColumns}
            dataSource={groups}
            pagination={{ pageSize: 10, showSizeChanger: false }}
          />
        )}
        {/* @AI_GENERATED: end */}
      </Card>

      <Card size="small" title={`审核会话（${sessions.length}）`}>
        {/* @AI_GENERATED: 审核会话独立 error/empty/retry。 */}
        {sessionError ? (
          <Alert
            type="error"
            showIcon
            message="加载审核会话失败"
            description={sessionError}
            action={<Button size="small" onClick={() => void loadSessions()}>重试</Button>}
          />
        ) : sessions.length === 0 ? (
          <Empty
            description={sessionLoading ? '加载中…' : '暂无审核会话'}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Table
            size="small"
            rowKey="review_id"
            loading={sessionLoading}
            columns={sessionColumns}
            dataSource={sessions}
            pagination={{ pageSize: 10, showSizeChanger: false }}
          />
        )}
        {/* @AI_GENERATED: end */}
      </Card>
    </Space>
  );
};

export default SlotManualReviewQueuePanel;
