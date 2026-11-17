/**
 * SlotAnnotationReviewPanel — G5 最小审核 UI：pending 候选 approve/reject + bootstrap/build
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Button, Card, Empty, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { CheckOutlined, CloseOutlined, DatabaseOutlined } from '@ant-design/icons';
import type { PvProductSlot } from '../../config/slotProductConfig';
import { slotDatasetsApi, type SnapshotChainView } from '../../services/slotDatasetsApi';

const { Text } = Typography;

type AnnotationCandidateRow = {
  annotation_candidate_id: string;
  entity_key?: string;
  boundary_start?: string;
  boundary_end?: string;
  suggested_label?: unknown;
  review_status?: string;
};

interface Props {
  slot: PvProductSlot;
  snapshotChain: SnapshotChainView | null;
  initialRows?: unknown[];
  initialReviewedIds?: string[];
  onChanged?: () => void;
}

const SlotAnnotationReviewPanel: React.FC<Props> = ({
  slot,
  snapshotChain,
  initialRows,
  initialReviewedIds,
  onChanged,
}) => {
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<AnnotationCandidateRow[]>([]);
  const [reviewedIds, setReviewedIds] = useState<string[]>([]);
  const [actingId, setActingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [pending, reviewed] = await Promise.all([
        slotDatasetsApi.listAnnotationCandidates(slot, 'pending'),
        slotDatasetsApi.listReviewedAnnotations(slot),
      ]);
      const pendingRows = Array.isArray(pending?.candidates)
        ? pending.candidates
        : Array.isArray(pending)
          ? pending
          : [];
      const reviewedRows = Array.isArray(reviewed?.annotations)
        ? reviewed.annotations
        : Array.isArray(reviewed)
          ? reviewed
          : [];
      setRows(pendingRows as AnnotationCandidateRow[]);
      setReviewedIds(
        reviewedRows
          .map((item) => String((item as { reviewed_annotation_id?: string }).reviewed_annotation_id || ''))
          .filter(Boolean),
      );
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        || (err as Error)?.message
        || '标注候选读取失败';
      message.error(typeof detail === 'string' ? detail : '标注候选读取失败');
    } finally {
      setLoading(false);
    }
  }, [slot]);

  useEffect(() => {
    if (initialRows) {
      setRows(Array.isArray(initialRows) ? (initialRows as AnnotationCandidateRow[]) : []);
      setReviewedIds(Array.isArray(initialReviewedIds) ? initialReviewedIds : []);
      return;
    }
    void refresh();
  }, [refresh, initialRows, initialReviewedIds]);

  const handleApprove = async (record: AnnotationCandidateRow) => {
    setActingId(record.annotation_candidate_id);
    try {
      await slotDatasetsApi.approveAnnotationCandidate(record.annotation_candidate_id, {
        slot,
        reviewer: 'ui-operator',
        idempotency_key: `ui-approve-${record.annotation_candidate_id}`,
      });
      message.success('已批准标注候选');
      await refresh();
      onChanged?.();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || '批准失败');
    } finally {
      setActingId(null);
    }
  };

  const handleReject = async (record: AnnotationCandidateRow) => {
    setActingId(record.annotation_candidate_id);
    try {
      await slotDatasetsApi.rejectAnnotationCandidate(record.annotation_candidate_id, {
        slot,
        reviewer: 'ui-operator',
        idempotency_key: `ui-reject-${record.annotation_candidate_id}`,
        reason: 'ui reject',
      });
      message.info('已拒绝标注候选');
      await refresh();
      onChanged?.();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || '拒绝失败');
    } finally {
      setActingId(null);
    }
  };

  const handleBootstrap = async () => {
    setLoading(true);
    try {
      await slotDatasetsApi.bootstrapSnapshot({
        slot,
        idempotency_key: `ui-bootstrap-${slot}`,
        source_digest: `ui-bootstrap-${Date.now()}`,
        base_artifact_ref: slot === 'pv_day'
          ? 'fault-diag-algo-release-3.1/relate_data/all_labeled_combined.parquet'
          : 'data/timeseries_point/test_fixtures/labeled_points.parquet',
        dataset_profile_ref: `${slot}-demo@v1`,
        reason: 'ui bootstrap',
      });
      message.success('快照 v1 已 bootstrap');
      onChanged?.();
    } catch (err: any) {
      const code = err?.response?.data?.detail?.code;
      if (code === 'snapshot_chain_exists') {
        message.info('快照链已存在');
      } else {
        message.error(err?.response?.data?.detail?.message || err?.message || 'bootstrap 失败');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleBuild = async () => {
    if (!snapshotChain?.snapshot_id || reviewedIds.length === 0) {
      message.warning('需要先批准标注并确保快照链存在');
      return;
    }
    setLoading(true);
    try {
      await slotDatasetsApi.buildSnapshot({
        slot,
        snapshot_id: snapshotChain.snapshot_id,
        base_snapshot_version: snapshotChain.latest_version,
        reviewed_annotation_ids: reviewedIds.slice(-1),
        idempotency_key: `ui-build-${snapshotChain.latest_version}-${reviewedIds.length}`,
        reason: 'ui build increment',
      });
      message.success('快照已 +1');
      onChanged?.();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || 'build 失败');
    } finally {
      setLoading(false);
    }
  };

  const columns: ColumnsType<AnnotationCandidateRow> = [
    { title: 'candidate_id', dataIndex: 'annotation_candidate_id', key: 'annotation_candidate_id', ellipsis: true },
    { title: 'slot', key: 'slot', render: () => slot },
    { title: '实体', dataIndex: 'entity_key', key: 'entity_key' },
    { title: '边界起', dataIndex: 'boundary_start', key: 'boundary_start' },
    { title: '边界止', dataIndex: 'boundary_end', key: 'boundary_end' },
    {
      title: '建议标签',
      dataIndex: 'suggested_label',
      key: 'suggested_label',
      render: (value) => String(value),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, record) => (
        <Space>
          <Button
            size="small"
            type="primary"
            icon={<CheckOutlined />}
            loading={actingId === record.annotation_candidate_id}
            onClick={() => void handleApprove(record)}
          >
            批准
          </Button>
          <Button
            size="small"
            danger
            icon={<CloseOutlined />}
            loading={actingId === record.annotation_candidate_id}
            onClick={() => void handleReject(record)}
          >
            拒绝
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Card
      size="small"
      title="标注候选审核（G5 最小）"
      extra={(
        <Space>
          {snapshotChain?.empty !== false && (
            <Button size="small" icon={<DatabaseOutlined />} onClick={() => void handleBootstrap()} loading={loading}>
              Bootstrap v1
            </Button>
          )}
          <Button size="small" onClick={() => void handleBuild()} loading={loading} disabled={!snapshotChain?.snapshot_id}>
            构建快照 +1
          </Button>
          <Button size="small" onClick={() => void refresh()} loading={loading}>刷新</Button>
        </Space>
      )}
    >
      {rows.length === 0 ? (
        <Empty description="暂无 pending annotation candidate" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <Table
          size="small"
          rowKey="annotation_candidate_id"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={false}
        />
      )}
      <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
        已审核 {reviewedIds.length} 条；快照链 {snapshotChain?.snapshot_id ?? '未初始化'} v{snapshotChain?.latest_version ?? 0}
      </Text>
    </Card>
  );
};

export default SlotAnnotationReviewPanel;
