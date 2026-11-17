// @AI_GENERATED
/**
 * DeploymentSwitchLogCard.tsx — 部署切换审计展示卡片。
 *
 * 从部署服务读取指定 `slot`（场景）的 append-only 切换事件，帮助把精度运营
 * 的通道 A 决策与 production/shadow 实际角色变化对应起来。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Empty, Space, Spin, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { HistoryOutlined, ReloadOutlined, RollbackOutlined, SwapOutlined } from '@ant-design/icons';
import { deploymentApi, type SwitchEventView } from '../../services/deploymentApi';

const { Text } = Typography;

interface DeploymentSwitchLogCardProps {
  /** slot — 要展示审计日志的部署场景。 */
  slot: string;
  /** refreshKey — 通道 A 切换后递增，触发重新读取 append-only 日志。 */
  refreshKey?: number;
}

function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString('zh-CN', { hour12: false });
}

const columns: ColumnsType<SwitchEventView> = [
  {
    title: '事件类型',
    key: 'event_type',
    width: 100,
    render: (_, event) => event.rollback_of
      ? <Tag icon={<RollbackOutlined />} color="orange">回滚</Tag>
      : <Tag icon={<SwapOutlined />} color="blue">切换</Tag>,
  },
  {
    title: '生产角色变化',
    key: 'roles',
    render: (_, event) => (
      <Space direction="vertical" size={0}>
        <Text code style={{ fontSize: 12 }}>{event.from_version_tag}</Text>
        <Text type="secondary" style={{ fontSize: 11 }}>↓ production ↓</Text>
        <Text code style={{ fontSize: 12 }}>{event.to_version_tag}</Text>
      </Space>
    ),
  },
  {
    title: '触发方式',
    dataIndex: 'trigger_type',
    width: 90,
    render: (value: SwitchEventView['trigger_type']) => (
      <Tag color={value === 'auto' ? 'purple' : 'default'}>{value === 'auto' ? '通道/自动' : '人工'}</Tag>
    ),
  },
  {
    title: '时间',
    dataIndex: 'switch_time',
    width: 170,
    render: formatDateTime,
  },
  {
    title: '原因',
    dataIndex: 'reason',
    render: (value: string) => <Text ellipsis={{ tooltip: value || '—' }}>{value || '—'}</Text>,
  },
];

const DeploymentSwitchLogCard: React.FC<DeploymentSwitchLogCardProps> = ({ slot, refreshKey = 0 }) => {
  const [events, setEvents] = useState<SwitchEventView[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await deploymentApi.getSwitchLog(slot);
      setEvents(response.events ?? []);
    } catch (err: any) {
      setEvents([]);
      setError(err?.response?.data?.detail?.message || err?.message || '读取切换审计日志失败');
    } finally {
      setLoading(false);
    }
  }, [slot]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return (
    <Card
      title={<Space><HistoryOutlined />部署切换审计</Space>}
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>}
      aria-label="部署切换审计日志"
    >
      {loading ? <div style={{ textAlign: 'center', padding: '28px 0' }}><Spin tip="加载审计日志…" /></div> : null}
      {!loading && error ? <Alert type="error" showIcon message="加载失败" description={error} action={<Button size="small" onClick={load}>重试</Button>} /> : null}
      {!loading && !error && events.length === 0 ? <Empty description="该场景暂无切换或回滚审计事件" /> : null}
      {!loading && !error && events.length > 0 ? (
        <Table<SwitchEventView>
          rowKey="event_id"
          size="small"
          columns={columns}
          dataSource={[...events].reverse()}
          pagination={{ pageSize: 5, showSizeChanger: false }}
          expandable={{
            expandedRowRender: (event) => (
              <Space direction="vertical" size={2}>
                <Text type="secondary">event_id（事件 ID）：<Text code>{event.event_id}</Text></Text>
                {event.rollback_of ? <Text type="secondary">rollback_of（被回滚事件 ID）：<Text code>{event.rollback_of}</Text></Text> : null}
                <Text type="secondary">from_workflow_id（原工作流）：<Text code>{event.from_workflow_id}</Text></Text>
                <Text type="secondary">to_workflow_id（目标工作流）：<Text code>{event.to_workflow_id}</Text></Text>
              </Space>
            ),
          }}
        />
      ) : null}
    </Card>
  );
};

export default DeploymentSwitchLogCard;
// @AI_GENERATED: end
