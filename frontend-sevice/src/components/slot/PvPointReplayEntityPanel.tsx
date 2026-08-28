/**
 * PvPointReplayEntityPanel — 点路径调度页：replay_activity 会话与实体进度。
 * 不读 measurement_ingestion_daily（那是天路径日预测到达表）。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Progress, Space, Table, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import {
  timeseriesReplayApi,
  type PendingFeedSummary,
  type ReplayEntityOverview,
  type ReplaySessionView,
} from '../../services/timeseriesReplayApi';

const { Text } = Typography;

const DEFAULT_REPLAY_SESSION_ID = 'sched-pv_point-default';

function formatTime(value?: string | null): string {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return String(value);
  }
}

const PvPointReplayEntityPanel: React.FC = () => {
  const [session, setSession] = useState<ReplaySessionView | null>(null);
  const [feed, setFeed] = useState<PendingFeedSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sessionResp, feedResp] = await Promise.allSettled([
        timeseriesReplayApi.getReplaySession(DEFAULT_REPLAY_SESSION_ID),
        timeseriesReplayApi.getPendingFeedSummary('pv_point'),
      ]);
      if (sessionResp.status === 'fulfilled') {
        setSession(sessionResp.value);
      } else {
        setSession(null);
        const detail = (sessionResp.reason as { response?: { data?: { detail?: string } }; message?: string })
          ?.response?.data?.detail
          || (sessionResp.reason as Error)?.message
          || 'replay 会话读取失败';
        setError(String(detail));
      }
      if (feedResp.status === 'fulfilled') {
        setFeed(feedResp.value);
      } else {
        setFeed(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const entities = session?.entity_overview || [];
  const total = Number(session?.total || session?.total_points || 0);
  const cursor = Number(session?.cursor || 0);
  const percent = total > 0 ? Math.min(100, Math.round((cursor / total) * 10000) / 100) : 0;
  const replayedEntities = useMemo(
    () => entities.filter((row) => Number(row.replayed_points) > 0).length,
    [entities],
  );

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="点路径看的是 replay_activity，不是天路径到达表"
        description={(
          <Text>
            <Text code>pv_point_replay_tick</Text> 推进会话
            {' '}<Text code>{DEFAULT_REPLAY_SESSION_ID}</Text>
            里的事件点。下面站点/设备来自该会话的 source 行和 entity_cursors。
            天路径的「数据到达总览」读的是 <Text code>measurement_ingestion_daily</Text>，
            默认不进入 replay；只有打开 pending_feed 才会把新点灌进会话。
          </Text>
        )}
      />
      <Card
        size="small"
        title="Replay 会话"
        extra={<Button size="small" icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>刷新</Button>}
      >
        {error ? (
          <Alert type="warning" showIcon message={error} description="先在本页触发 pv_point_replay_tick，调度会创建默认会话。" />
        ) : session ? (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Space wrap>
              <Tag color={session.status === 'running' ? 'processing' : session.status === 'completed' ? 'success' : 'default'}>
                {session.status || '未知'}
              </Tag>
              <Text>进度 {cursor} / {total}</Text>
              <Text type="secondary">已回放实体 {replayedEntities} / {entities.length}</Text>
            </Space>
            <Progress percent={percent} size="small" status={session.status === 'completed' ? 'success' : 'active'} />
            <Text type="secondary">
              模型 {session.model_ref || '—'}
              {session.dataset_profile_id ? ` · profile ${session.dataset_profile_id}` : ''}
            </Text>
            {feed ? (
              <Text type="secondary">
                pending_feed：待灌入 {feed.pending} / 已处理 {feed.processed}（共 {feed.total}）
              </Text>
            ) : null}
          </Space>
        ) : null}
      </Card>
      <Card size="small" title="Replay 实体进度（站点 / 设备 / 支路）">
        <Table<ReplayEntityOverview>
          size="small"
          rowKey="entity_key"
          loading={loading}
          dataSource={entities}
          pagination={{ pageSize: 10, size: 'small' }}
          locale={{ emptyText: '会话里还没有实体点' }}
          columns={[
            { title: '站点', dataIndex: 'site_id', width: 160, ellipsis: true },
            { title: '设备', dataIndex: 'device_id', width: 160, ellipsis: true },
            { title: '支路', dataIndex: 'branch_id', width: 72 },
            {
              title: '回放进度',
              key: 'progress',
              width: 180,
              render: (_: unknown, row) => {
                const source = Number(row.source_points || 0);
                const done = Number(row.replayed_points || 0);
                const ratio = source > 0 ? done / source : 0;
                return (
                  <Progress
                    percent={Math.min(100, Math.round(ratio * 100))}
                    size="small"
                    style={{ width: 120 }}
                    status={done >= source && source > 0 ? 'success' : 'active'}
                    format={() => `${done}/${source}`}
                  />
                );
              },
            },
            {
              title: '最近回放时间',
              dataIndex: 'last_replay_time',
              width: 170,
              render: (value: string | null) => formatTime(value),
            },
            {
              title: '最近标签',
              dataIndex: 'last_label',
              width: 88,
              render: (value: number | null) => (value == null ? '—' : <Tag>{value}</Tag>),
            },
          ]}
        />
      </Card>
    </Space>
  );
};

export default PvPointReplayEntityPanel;
