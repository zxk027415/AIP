/**
 * SlotManualReviewQueuePanel — 人工打标队列（pv_day / pv_point）
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

export type ManualReviewSlot = 'pv_day' | 'pv_point';

interface Props {
  slot: ManualReviewSlot;
  onChanged?: () => void;
}

const SlotManualReviewQueuePanel: React.FC<Props> = ({ slot, onChanged }) => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null);
  const [mocking, setMocking] = useState(false);
  const [sessions, setSessions] = useState<ReviewSessionSummary[]>([]);
  const [groups, setGroups] = useState<DetectionReviewGroup[]>([]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [sessionResp, queueResp] = await Promise.all([
        reviewSessionApi.listReviewSessions(slot),
        reviewSessionApi.listAnnotationCandidateReviewQueue(slot),
      ]);
      const sessionRows = Array.isArray(sessionResp?.sessions) ? sessionResp.sessions : [];
      setSessions(sessionRows as ReviewSessionSummary[]);
      const groupRows = Array.isArray(queueResp?.groups) ? queueResp.groups : [];
      setGroups(groupRows as DetectionReviewGroup[]);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string | { message?: string } } }; message?: string })
        ?.response?.data?.detail;
      const msg = typeof detail === 'string'
        ? detail
        : typeof detail === 'object' && detail?.message
          ? detail.message
          : (err as Error)?.message || '加载人工打标队列失败';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [slot]);

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
      const detail = (err as { response?: { data?: { detail?: string | { message?: string } } }; message?: string })
        ?.response?.data?.detail;
      const msg = typeof detail === 'string'
        ? detail
        : typeof detail === 'object' && detail?.message
          ? detail.message
          : (err as Error)?.message || '创建审核会话失败';
      message.error(msg);
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
        r.review_kind === 'annotation_candidate_review' || r.annotation_candidate_id
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
      <Alert
        type="info"
        showIcon
        message={`${slot} 人工打标队列`}
        description="一次完整滚动检测（按天 / 同一 execution）对应一条 rev 会话；会话内按设备日逐条框选，不是每条候选单独一条会话。gold 模拟会走 complete-and-admit，来源标成 daily_review，不是专家标注。"
      />

      <Card
        size="small"
        title={`待审核检测（${groups.length} 组）`}
        extra={(
          <Space>
            <Button
              size="small"
              loading={mocking}
              onClick={async () => {
                setMocking(true);
                try {
                  const result = await slotObservabilityApi.mockGoldReview(slot);
                  message.success(result.note || `gold 回放 ${result.hit_count || 0} 条`);
                  onChanged?.();
                  void refresh();
                } catch (err: unknown) {
                  const detail = (err as { response?: { data?: { detail?: { message?: string } } }; message?: string })?.response?.data?.detail;
                  message.error((typeof detail === 'object' && detail?.message) || (err as Error).message || 'mock 审核失败');
                } finally {
                  setMocking(false);
                }
              }}
            >
              用 gold 模拟一小批审核
            </Button>
            <Button size="small" icon={<ReloadOutlined />} onClick={() => void refresh()} loading={loading}>
              刷新
            </Button>
          </Space>
        )}
      >
        {groups.length === 0 ? (
          <Empty description="暂无待审核检测组" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Table
            size="small"
            rowKey="detection_group_id"
            loading={loading}
            columns={groupColumns}
            dataSource={groups}
            pagination={{ pageSize: 10, showSizeChanger: false }}
          />
        )}
      </Card>

      <Card size="small" title={`审核会话（${sessions.length}）`}>
        {sessions.length === 0 ? (
          <Empty description="暂无审核会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Table
            size="small"
            rowKey="review_id"
            loading={loading}
            columns={sessionColumns}
            dataSource={sessions}
            pagination={{ pageSize: 10, showSizeChanger: false }}
          />
        )}
      </Card>
    </Space>
  );
};

export default SlotManualReviewQueuePanel;
