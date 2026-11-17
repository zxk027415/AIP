// @AI_GENERATED
/**
 * PvIngestionSiteOverview — 数据到达总览（站点级）
 *
 * 展示每个站点的数据到达完整性：设备总数、已完整设备数、完成度进度条、
 * 最近一次完整性记录更新时间。点击某站点展开 `PvDeviceIngestionDetail` 下钻表格。
 *
 * 数据来源：GET /api/scheduler/pv-ingestion/site-overview（只读，不触发预测）。
 * 对应设计讨论：.kiro/specs/pv-fault-timeseries-diagnosis/ 按日滚动预测数据到达仪表盘。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Progress, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined } from '@ant-design/icons';
import { pvIngestionApi, type PvSiteIngestionOverview } from '../../services/deploymentApi';
import PvDeviceIngestionDetail from './PvDeviceIngestionDetail';

const { Text } = Typography;

interface PvIngestionSiteOverviewProps {
  /** businessDate — 可选，指定业务日；不传时展示每个站点各自最新业务日的总览。 */
  businessDate?: string;
  /** modelingPath — 天路径 legacy_day / 点路径 seq_annotation；不传则后端按 slot 回退。 */
  modelingPath?: string;
  /** slot — pv_day / pv_point / pv_fault，决定默认门槛和待预测游标分区。 */
  slot?: string;
}

const PvIngestionSiteOverview: React.FC<PvIngestionSiteOverviewProps> = ({
  businessDate,
  modelingPath: requestedModelingPath,
  slot,
}) => {
  const [sites, setSites] = useState<PvSiteIngestionOverview[]>([]);
  const [resolvedModelingPath, setResolvedModelingPath] = useState<string | undefined>(undefined);
  const [readyCriterion, setReadyCriterion] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSiteId, setExpandedSiteId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await pvIngestionApi.getSiteOverview(businessDate, {
        modelingPath: requestedModelingPath,
        slot,
      });
      setSites(resp.sites);
      setResolvedModelingPath(resp.modeling_path);
      setReadyCriterion(resp.ready_criterion);
      setExpandedSiteId((current) => current ?? resp.sites[0]?.site_id ?? null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || '加载数据到达总览失败');
      setSites([]);
    } finally {
      setLoading(false);
    }
  }, [businessDate, requestedModelingPath, slot]);

  useEffect(() => { void load(); }, [load]);

  const columns: ColumnsType<PvSiteIngestionOverview> = [
    { title: '站点', dataIndex: 'site_id', width: 200, ellipsis: true },
    { title: '业务日', dataIndex: 'business_date', width: 120 },
    { title: '设备总数', dataIndex: 'device_total', width: 100, align: 'right' },
    {
      // @AI_GENERATED: TSC 共用占用闸门列标题
      title: resolvedModelingPath === 'seq_annotation' || resolvedModelingPath === 'tsc' ? '网格/点级可检' : '已到达设备数',
      // @AI_GENERATED: end
      dataIndex: 'device_complete',
      width: 120,
      align: 'right',
    },
    {
      title: '完成度',
      dataIndex: 'completion_ratio',
      width: 220,
      render: (ratio: number, row) => (
        <Space>
          <Progress
            percent={Math.round(ratio * 100)}
            size="small"
            style={{ width: 140 }}
            status={ratio >= 1 ? 'success' : 'active'}
          />
          {ratio >= 1 ? <Tag color="green">已全部到齐</Tag> : null}
        </Space>
      ),
    },
    {
      title: '最近更新',
      dataIndex: 'latest_updated_at',
      width: 180,
      render: (t: string | null) => (t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '—'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: unknown, row) => (
        <Button
          size="small"
          onClick={() => setExpandedSiteId(expandedSiteId === row.site_id ? null : row.site_id)}
        >
          {expandedSiteId === row.site_id ? '收起明细' : '设备明细'}
        </Button>
      ),
    },
  ];

  return (
    <Card
      size="small"
      title={(
        <Space>
          <span>数据到达总览（站点级）</span>
          {/* @AI_GENERATED: TSC 使用网格预检候选 */}
          {resolvedModelingPath === 'seq_annotation' || resolvedModelingPath === 'tsc' || readyCriterion === 'seq_occupied_173' ? (
            <Tag color="blue">{resolvedModelingPath === 'tsc' ? '网格预检 · ≥173/288' : '点级占用闸门 · ≥173/288'}</Tag>
          ) : (
            <Tag>天级 · 无完整等待闸门</Tag>
          )}
          {/* @AI_GENERATED: end */}
        </Space>
      )}
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>}
      style={{ marginBottom: 16 }}
    >
      {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 12 }} /> : null}
      {!error && sites.length === 0 && !loading ? (
        <Text type="secondary">暂无数据到达记录（尚未有测量数据写入或完整性表为空）。</Text>
      ) : (
        <Table<PvSiteIngestionOverview>
          rowKey="site_id"
          size="small"
          loading={loading}
          columns={columns}
          dataSource={sites}
          pagination={false}
        />
      )}
      {expandedSiteId ? (
        <div style={{ marginTop: 16 }}>
          <PvDeviceIngestionDetail siteId={expandedSiteId} businessDate={businessDate} modelingPath={resolvedModelingPath} />
        </div>
      ) : null}
    </Card>
  );
};

export default PvIngestionSiteOverview;
// @AI_GENERATED: end
