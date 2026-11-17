// @AI_GENERATED
/**
 * 点路径统一运行会话面板（design D-PATH-01 / D-STATE-01；任务 6.2）。
 *
 * 顶部：会话源（real_replay / loop_demo）、当前 cursor、数据版本、运行域。
 * 中部：点时间线 + 因果窗（只展示严格早于当前点的已提交历史 + 当前待定点）。
 * 右侧：待定点、预测结论、告警投递（与预测结论分开报告）。
 * 动作：开始 / 暂停 / 单步 / 进 10 点 / 进 50 点 / 自动 / 停止；Sandbox 局部 reset（production 不受影响）。
 * 刷新后按 project_id + sandbox_id + slot 恢复会话；loop_demo 标注为演示喂点、不写累计台账。
 *
 * 说明：本环境无实时数据源，start 以确定性演示点建立会话（session_source=loop_demo），
 * 明确非生产、不写台账；真实逐点因果内核在后端 SandboxRuntime，UI 只驱动动作与展示。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Button, Descriptions, Divider, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ActionStateView } from './ActionStateView';
import { useProjectScope } from '../../contexts/ProjectScopeContext';
import { pvProjectsApi } from '../../services/pvProjectsApi';
import type { PointCommitted, PointSandbox } from '../../services/pvProjectsApi';

const { Text, Title } = Typography;

function extractErr(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
  return detail?.message || fallback;
}

/** 确定性演示点：仅用于在无实时数据源时驱动逐点因果演示。 */
function demoPoints(n = 24): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = [];
  for (let i = 0; i < n; i += 1) {
    const base = 10 + 5 * Math.sin(i / 3);
    const spike = i === 13 ? 20 : 0;
    out.push({
      event_time: `2026-01-01T${String(Math.floor(i / 12)).padStart(2, '0')}:${String((i * 5) % 60).padStart(2, '0')}:00`,
      value: Number((base + spike).toFixed(3)),
      point_id: `p${i}`,
    });
  }
  return out;
}

export function PointRunSessionPanel({ slot }: { slot: string }): JSX.Element {
  const { scope, generation } = useProjectScope();
  const projectId = scope.projectId;
  const sandboxId = `sbx-${projectId}-${slot}`;
  const [sandbox, setSandbox] = useState<PointSandbox | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [auto, setAuto] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const autoRef = useRef(false);

  const restore = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setNotFound(false);
    pvProjectsApi
      .getPointSandbox(projectId, slot, sandboxId)
      .then((res) => setSandbox(res.sandbox))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, slot, sandboxId, generation]);

  useEffect(() => {
    restore();
  }, [restore]);

  // 自动推进：每 700ms 单步，直到追平 / 暂停 / 停止。
  useEffect(() => {
    autoRef.current = auto;
    if (!auto || !sandbox) return;
    const timer = setInterval(async () => {
      if (!autoRef.current) return;
      const cur = sandbox;
      if (!cur || cur.cursor >= cur.source_points.length) {
        setAuto(false);
        return;
      }
      try {
        const res = await pvProjectsApi.pointStep(projectId, slot, sandboxId);
        setSandbox(res.sandbox);
        if (res.sandbox.cursor >= res.sandbox.source_points.length) setAuto(false);
      } catch {
        setAuto(false);
      }
    }, 700);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, sandbox?.cursor]);

  const onStart = async () => {
    setBusy(true);
    try {
      const res = await pvProjectsApi.createPointSandbox(projectId, slot, {
        sandbox_id: sandboxId,
        points: demoPoints(),
        session_source: 'loop_demo',
        dataset_version_id: scope.datasetVersionId,
      });
      setSandbox(res.sandbox);
      setNotFound(false);
      message.success('已建立演示回放会话（loop_demo，不写累计台账）');
    } catch (e) {
      message.error(extractErr(e, '建立会话失败'));
    } finally {
      setBusy(false);
    }
  };

  const doAction = async (fn: () => Promise<{ sandbox: PointSandbox }>, okMsg?: string) => {
    setBusy(true);
    try {
      const res = await fn();
      setSandbox(res.sandbox);
      if (okMsg) message.success(okMsg);
    } catch (e) {
      message.error(extractErr(e, '操作失败'));
      restore();
    } finally {
      setBusy(false);
    }
  };

  const onStep = () => doAction(() => pvProjectsApi.pointStep(projectId, slot, sandboxId) as unknown as Promise<{ sandbox: PointSandbox }>);
  const onAdvance = (n: number) => doAction(() => pvProjectsApi.pointAdvance(projectId, slot, sandboxId, n));
  const onReset = () =>
    doAction(async () => {
      const res = await pvProjectsApi.pointReset(projectId, slot, sandboxId);
      message.success(res.statement);
      return { sandbox: res.sandbox };
    });

  if (loading) return <ActionStateView descriptor={{ state: 'loading', title: '正在恢复回放会话' }} />;

  if (notFound || !sandbox) {
    return (
      <ActionStateView
        descriptor={{
          state: 'initial_empty',
          title: '尚无逐点回放会话',
          reason: '点路径逐点回放按事件时间因果推进；本环境以演示点建立会话（loop_demo，不写累计台账）。',
          nextAction: '点击“开始演示会话”以逐点观察 pending point / committed history / cursor / outcome',
          scope: { projectId, slot },
        }}
        primaryAction={
          <Button type="primary" onClick={onStart} loading={busy}>
            开始演示会话
          </Button>
        }
      />
    );
  }

  const caughtUp = sandbox.cursor >= sandbox.source_points.length;
  const causalHistory = sandbox.committed_history.slice(-6); // 因果窗：最近已提交历史
  const pending = sandbox.pending_point;

  const historyColumns: ColumnsType<PointCommitted> = [
    { title: '#', dataIndex: 'point_index', width: 48 },
    { title: '事件时间', dataIndex: 'event_time', render: (v?: string) => <Text style={{ fontSize: 11 }}>{v || '—'}</Text> },
    { title: '值', dataIndex: 'value', render: (v?: number) => <Text style={{ fontSize: 12 }}>{v ?? '—'}</Text> },
    {
      title: '异常分（只读历史）',
      render: (_: unknown, rec) => <Text style={{ fontSize: 12 }}>{rec.prediction.anomaly_score}</Text>,
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {/* 顶部：会话元信息 */}
      <Descriptions size="small" column={4} bordered>
        <Descriptions.Item label="会话源">
          <Tag color={sandbox.session_source === 'loop_demo' ? 'purple' : 'blue'}>
            {sandbox.session_source === 'loop_demo' ? '演示喂点 loop_demo' : '真实回放 real_replay'}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="当前 cursor">
          {sandbox.cursor} / {sandbox.source_points.length}
        </Descriptions.Item>
        <Descriptions.Item label="数据版本">{sandbox.dataset_version_id || '—'}</Descriptions.Item>
        <Descriptions.Item label="运行域">
          <Tag>{sandbox.run_domain}</Tag>
        </Descriptions.Item>
      </Descriptions>

      {sandbox.session_source === 'loop_demo' && (
        <Alert
          type="warning"
          showIcon
          message="演示喂点（loop_demo）"
          description="loop_demo 仅用于演示逐点因果，不写累计台账、不产出可治理证据、production 不受影响。"
        />
      )}

      {/* 动作条 */}
      <Space wrap>
        <Button onClick={onStep} loading={busy} disabled={caughtUp || auto}>
          单步
        </Button>
        <Button onClick={() => onAdvance(10)} loading={busy} disabled={caughtUp || auto}>
          进 10 点
        </Button>
        <Button onClick={() => onAdvance(50)} loading={busy} disabled={caughtUp || auto}>
          进 50 点
        </Button>
        {auto ? (
          <Button danger onClick={() => setAuto(false)}>
            暂停 / 停止自动
          </Button>
        ) : (
          <Button type="primary" ghost onClick={() => setAuto(true)} disabled={caughtUp}>
            自动
          </Button>
        )}
        <Button onClick={onReset} loading={busy} disabled={auto}>
          Sandbox 重置
        </Button>
      </Space>
      {caughtUp && <Tag color="green">已追平所有点（cursor 到达末尾）</Tag>}

      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {/* 中部：因果窗（只读历史） */}
        <div style={{ flex: '1 1 420px', minWidth: 320 }}>
          <Title level={5} style={{ marginBottom: 8 }}>
            因果窗：已提交历史（严格早于当前点）
          </Title>
          {causalHistory.length === 0 ? (
            <Text type="secondary">尚无已提交历史；第一点的预测仅基于其自身输入。</Text>
          ) : (
            <Table rowKey="point_index" size="small" columns={historyColumns} dataSource={causalHistory} pagination={false} />
          )}
        </div>

        {/* 右侧：待定点 + 预测 + 告警 */}
        <div style={{ flex: '1 1 320px', minWidth: 280 }}>
          <Title level={5} style={{ marginBottom: 8 }}>
            待定点 / 预测 / 告警
          </Title>
          {pending ? (
            <Descriptions size="small" column={1} bordered>
              <Descriptions.Item label="点序号 / 时间">
                #{pending.point_index} · {pending.event_time || '—'}
              </Descriptions.Item>
              <Descriptions.Item label="历史基线（仅已提交）">
                {pending.prediction.baseline_from_committed}（n={pending.prediction.n_history}）
              </Descriptions.Item>
              <Descriptions.Item label="当前值">{pending.prediction.current_value}</Descriptions.Item>
              <Descriptions.Item label="异常分">{pending.prediction.anomaly_score}</Descriptions.Item>
              <Descriptions.Item label="告警投递（与预测分开）">
                {pending.prediction.anomaly_score >= 8 ? <Tag color="red">触发告警</Tag> : <Tag color="default">无告警</Tag>}
              </Descriptions.Item>
            </Descriptions>
          ) : (
            <Text type="secondary">
              {caughtUp ? '已无待定点。' : '无待定点；单步 / 推进以预测下一点（预测只读严格早于它的已提交历史）。'}
            </Text>
          )}
        </div>
      </div>

      <Divider style={{ margin: 0 }} />
      <Text type="secondary" style={{ fontSize: 12 }}>
        因果保证：对第 i 点的预测只读 committed_history[:i]（严格早于它）+ 当前点输入；cursor 只在 outcome
        提交后推进；重置仅影响本 Sandbox（{sandboxId}），不影响 production 与其他 Sandbox。
      </Text>
    </Space>
  );
}

export default PointRunSessionPanel;
// @AI_GENERATED: end
