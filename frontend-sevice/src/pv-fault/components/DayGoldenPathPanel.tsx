// @AI_GENERATED
/**
 * 日路径金路径面板（design D-PATH-01；任务 5.2）。
 *
 * 诚实展示日路径生产事实（LegacyDayStrategy 复用 quickval predict 图，无专用日级生产图），
 * 并提供 Sandbox 全设备日回放（隔离结果、production 不受影响）。
 */

import { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Descriptions, Divider, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ActionStateView } from './ActionStateView';
import { useProjectScope } from '../../contexts/ProjectScopeContext';
import { pvProjectsApi } from '../../services/pvProjectsApi';
import type { DayProductionFact, DaySandboxRun } from '../../services/pvProjectsApi';

const { Text } = Typography;

function extractErr(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
  return detail?.message || fallback;
}

/** 确定性演示设备日：无实时数据源时驱动 Sandbox 全设备日回放。 */
function demoDeviceDays(): Array<Record<string, unknown>> {
  const devices = ['D1', 'D2', 'D3'];
  const dates = ['2026-01-01', '2026-01-02'];
  const out: Array<Record<string, unknown>> = [];
  devices.forEach((d) => dates.forEach((day) => out.push({ device: d, date: day })));
  return out;
}

export function DayGoldenPathPanel({ slot }: { slot: string }): JSX.Element {
  const { scope, generation } = useProjectScope();
  const projectId = scope.projectId;
  const [fact, setFact] = useState<DayProductionFact | null>(null);
  const [runs, setRuns] = useState<DaySandboxRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    Promise.all([
      pvProjectsApi.getDayProductionFact(projectId, slot),
      pvProjectsApi.listDaySandboxRuns(projectId, slot),
    ])
      .then(([f, r]) => {
        setFact(f);
        setRuns(r.sandbox_runs || []);
      })
      .catch(() => setFact(null))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, slot, generation]);

  useEffect(() => {
    load();
  }, [load]);

  const onSandboxReplay = async () => {
    setBusy(true);
    try {
      const res = await pvProjectsApi.runSandboxDeviceDay(projectId, slot, {
        sandbox_id: `sbx-day-${projectId}-${slot}`,
        device_days: demoDeviceDays(),
      });
      message.success(`已回放 ${res.sandbox_run.device_day_count} 个设备日（隔离，production 不受影响）`);
      load();
    } catch (e) {
      message.error(extractErr(e, 'Sandbox 回放失败'));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <ActionStateView descriptor={{ state: 'loading', title: '正在读取日路径事实' }} />;

  const runColumns: ColumnsType<DaySandboxRun> = [
    { title: '回放', dataIndex: 'result_id', render: (v: string) => <Text code>{v}</Text> },
    { title: '设备日数', dataIndex: 'device_day_count' },
    {
      title: '域 / 影响',
      render: (_: unknown, rec) => (
        <Space size={4}>
          <Tag>{rec.run_domain}</Tag>
          {rec.production_unaffected && <Tag color="green">production 不受影响</Tag>}
        </Space>
      ),
    },
    { title: '时间', dataIndex: 'created_at', render: (v?: string) => <Text style={{ fontSize: 11 }}>{v || '—'}</Text> },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {fact && (
        <>
          <Alert
            type="info"
            showIcon
            message="日路径生产事实（只读）"
            description={fact.statement}
          />
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="生产策略">{fact.production_strategy}</Descriptions.Item>
            <Descriptions.Item label="生产工作流">{fact.production_workflow_id}</Descriptions.Item>
            <Descriptions.Item label="是否专用日级生产图" span={2}>
              {fact.dedicated_day_production_graph ? <Tag color="blue">是</Tag> : <Tag color="default">否（复用 quickval）</Tag>}
            </Descriptions.Item>
          </Descriptions>
        </>
      )}

      <Divider style={{ margin: 0 }} />
      <Space>
        <Button type="primary" ghost onClick={onSandboxReplay} loading={busy}>
          Sandbox 全设备日回放（演示）
        </Button>
        <Text type="secondary" style={{ fontSize: 12 }}>
          对每个 (设备, 日) 都产出隔离结果，不写生产指针、不产出可治理证据。
        </Text>
      </Space>

      {runs.length === 0 ? (
        <Text type="secondary">暂无 Sandbox 日级回放记录。</Text>
      ) : (
        <Table rowKey="result_id" size="small" columns={runColumns} dataSource={runs} pagination={{ pageSize: 5, size: 'small' }} />
      )}
    </Space>
  );
}

export default DayGoldenPathPanel;
// @AI_GENERATED: end
