// @AI_GENERATED
/**
 * PvDeviceIngestionDetail — 设备到达明细（下钻）
 *
 * 展示某站点下所有设备在指定业务日（或各自最新业务日）的到达完整性明细：
 * 设备 ID、首次收到数据时间、判定完整的时间、已到点数/理论点数、状态。
 *
 * 数据来源：GET /api/scheduler/pv-ingestion/device-detail（只读）。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Progress, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { pvIngestionApi, type PvDeviceIngestionDetail as PvDeviceIngestionDetailRow } from '../../services/deploymentApi';

const { Text } = Typography;

interface PvDeviceIngestionDetailProps {
  siteId: string;
  /** businessDate — 可选，指定业务日；不传时每个设备取其最新业务日的一行。 */
  businessDate?: string;
  /** modelingPath — 当前日滚路径，用来隔离明细状态：点级才显示占用闸门。 */
  modelingPath?: string;
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return iso;
  }
}

const PvDeviceIngestionDetail: React.FC<PvDeviceIngestionDetailProps> = ({ siteId, businessDate, modelingPath }) => {
  const [devices, setDevices] = useState<PvDeviceIngestionDetailRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await pvIngestionApi.getDeviceDetail(siteId, businessDate);
      setDevices(resp.devices);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || '加载设备到达明细失败');
      setDevices([]);
    } finally {
      setLoading(false);
    }
  }, [siteId, businessDate]);

  useEffect(() => { void load(); }, [load]);

  const columns: ColumnsType<PvDeviceIngestionDetailRow> = [
    { title: '设备 ID', dataIndex: 'device_id', width: 180, ellipsis: true },
    { title: '支路', dataIndex: 'branch_id', width: 80 },
    { title: '业务日', dataIndex: 'business_date', width: 120 },
    {
      title: '到达进度',
      key: 'progress',
      width: 220,
      render: (_: unknown, row) => {
        const ratio = row.expected_point_count > 0 ? row.point_count / row.expected_point_count : 0;
        return (
          <Progress
            percent={Math.min(100, Math.round(ratio * 100))}
            size="small"
            style={{ width: 140 }}
            status={
              modelingPath === 'seq_annotation'
                ? (row.is_seq_ready ? 'success' : 'active')
                : (row.point_count > 0 ? 'success' : 'active')
            }
            format={() => `${row.point_count}/${row.expected_point_count}`}
          />
        );
      },
    },
    {
      title: '状态',
      dataIndex: 'is_complete',
      width: 220,
      render: (_isComplete: boolean, row) => (
        modelingPath === 'seq_annotation' ? (
          row.is_seq_ready ? <Tag color="blue">点级可检 ≥173</Tag> : <Tag>未达占用门槛</Tag>
        ) : (
          row.point_count > 0 ? <Tag color="green">已到达</Tag> : <Tag>无数据</Tag>
        )
      ),
    },
    { title: '首次收到', dataIndex: 'first_seen_at', width: 170, render: formatDateTime },
    { title: '判定完整时间', dataIndex: 'completed_at', width: 170, render: formatDateTime },
    { title: '最近更新', dataIndex: 'updated_at', width: 170, render: formatDateTime },
  ];

  return (
    <div>
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      {!error && devices.length === 0 && !loading ? (
        <Text type="secondary">该站点暂无设备到达记录。</Text>
      ) : (
        <Table<PvDeviceIngestionDetailRow>
          rowKey={(row) => `${row.device_id}|${row.branch_id}|${row.business_date ?? ''}`}
          size="small"
          loading={loading}
          columns={columns}
          dataSource={devices}
          pagination={{ pageSize: 10, size: 'small' }}
        />
      )}
    </div>
  );
};

export default PvDeviceIngestionDetail;
// @AI_GENERATED: end
