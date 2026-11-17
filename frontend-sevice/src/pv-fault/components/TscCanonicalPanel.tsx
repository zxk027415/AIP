// @AI_GENERATED
/**
 * TSC canonical 打标 / strict-10 证据 / 只读生产观测面板（design D-PATH-01；任务 7.1–7.3）。
 *
 * - canonical 入口：workflow-pv-tsc-label-v1（tsc_predict→emit_tsc_label_proposal），
 *   提供“启动 canonical 打标”深链接到工作流编辑器（携 scope + canonical workflow id）。
 * - shortcut 区分：明确 KMeans REST 快捷聚类不是 canonical，preferred 仅为元数据。
 * - strict-10 证据：288×3 / 10 splits / 固定标签空间；validation 恒非可治理；
 *   production_contract_valid 仅表示合同完整；macro_f1 缺失渲染“未产出”。
 * - 生产观测只读：缺回执“未产出”，失败日不推进游标，手工写入被拒。
 * - 真实浏览器 E2E 通过前，页面标注“TSC canonical 打标 UI 待验收”。
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Descriptions, Divider, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ActionStateView } from './ActionStateView';
import { useProjectScope } from '../../contexts/ProjectScopeContext';
import { buildJourneyHref } from '../../utils/journeyParams';
import { pvProjectsApi } from '../../services/pvProjectsApi';
import type {
  TscCanonicalEntry,
  TscProductionStatus,
  TscShortcutDistinction,
  TscStrict10Evidence,
  TscStrict10View,
} from '../../services/pvProjectsApi';

const { Text, Title } = Typography;

export function TscCanonicalPanel({ slot }: { slot: string }): JSX.Element {
  const navigate = useNavigate();
  const { scope, generation } = useProjectScope();
  const projectId = scope.projectId;
  const [entry, setEntry] = useState<TscCanonicalEntry | null>(null);
  const [shortcut, setShortcut] = useState<TscShortcutDistinction | null>(null);
  const [strict10, setStrict10] = useState<TscStrict10View | null>(null);
  const [prod, setProd] = useState<TscProductionStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    Promise.all([
      pvProjectsApi.getTscCanonicalEntry(projectId, slot),
      pvProjectsApi.getTscShortcutDistinction(projectId, slot),
      pvProjectsApi.getTscStrict10Evidence(projectId, slot),
      pvProjectsApi.getTscProductionStatus(projectId, slot),
    ])
      .then(([e, s, st10, p]) => {
        setEntry(e);
        setShortcut(s);
        setStrict10(st10);
        setProd(p);
      })
      .catch(() => setEntry(null))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, slot, generation]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <ActionStateView descriptor={{ state: 'loading', title: '正在读取 TSC canonical 信息' }} />;

  const launchCanonical = () => {
    if (!entry?.canonical_workflow_id) return;
    navigate(
      buildJourneyHref(
        '/workflow-editor',
        { projectId, slot, datasetVersionId: scope.datasetVersionId },
        { workflow_id: entry.canonical_workflow_id, launch: 'canonical_labeling' },
      ),
    );
  };

  const evidenceColumns: ColumnsType<TscStrict10Evidence> = [
    { title: '证据', dataIndex: 'result_id', render: (v: string) => <Text code>{v}</Text> },
    { title: '来源执行', dataIndex: 'source_execution_id', render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text> },
    {
      title: 'Macro-F1',
      render: (_: unknown, rec) =>
        rec.macro_f1 === null ? <Tag color="default">{String(rec.macro_f1_display)}</Tag> : <Text>{String(rec.macro_f1_display)}</Text>,
    },
    {
      title: '合同 / 治理',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={0}>
          <Tag color={rec.production_contract_valid ? 'blue' : 'default'}>
            合同{rec.production_contract_valid ? '完整' : '不完整'}
          </Tag>
          <Tag color="default">非可治理</Tag>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {entry?.ui_acceptance_pending && (
        <Alert type="warning" showIcon message="TSC canonical 打标 UI 待验收" description="真实浏览器 E2E 通过前，此入口标注为待验收。" />
      )}

      {/* canonical 入口 */}
      {entry && (
        <div>
          <Title level={5} style={{ marginBottom: 8 }}>
            canonical 模型辅助打标
          </Title>
          <Descriptions size="small" column={1} bordered>
            <Descriptions.Item label="canonical 工作流">{entry.canonical_workflow_id || '—'}</Descriptions.Item>
            <Descriptions.Item label="画布链路">{entry.lineage.length ? entry.lineage.join(' → ') : '—'}</Descriptions.Item>
            <Descriptions.Item label="启动方式">{entry.launch_hint}</Descriptions.Item>
            <Descriptions.Item label="失败语义">{entry.fail_closed}</Descriptions.Item>
          </Descriptions>
          <div style={{ marginTop: 8 }}>
            <Button type="primary" onClick={launchCanonical} disabled={!entry.canonical_workflow_id}>
              启动 canonical 打标工作流
            </Button>
          </div>
        </div>
      )}

      {/* shortcut 区分 */}
      {shortcut && (
        <Alert
          type="info"
          showIcon
          message="shortcut ≠ canonical"
          description={
            <Space direction="vertical" size={2}>
              <span>{shortcut.explanation}</span>
              <Text type="secondary" style={{ fontSize: 12 }}>
                labeling_mode={shortcut.labeling_mode} · is_canonical={String(shortcut.is_canonical)} · preferred=
                {shortcut.preferred_labeling_workflow_id || '—'}
              </Text>
            </Space>
          }
        />
      )}

      <Divider style={{ margin: 0 }} />

      {/* strict-10 证据 */}
      {strict10 && (
        <div>
          <Title level={5} style={{ marginBottom: 8 }}>
            strict-10 证据（288×3 / 10 splits / 固定标签空间）
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            production_contract_valid 仅表示合同完整，不代表精度达标或可治理；所有 validation 证据恒非可治理。
          </Text>
          {strict10.evidence.length === 0 ? (
            <div style={{ marginTop: 8 }}>
              <Text type="secondary">暂无 strict-10 证据登记。</Text>
            </div>
          ) : (
            <Table
              style={{ marginTop: 8 }}
              rowKey="result_id"
              size="small"
              columns={evidenceColumns}
              dataSource={strict10.evidence}
              pagination={false}
            />
          )}
        </div>
      )}

      <Divider style={{ margin: 0 }} />

      {/* 只读生产观测 */}
      {prod && (
        <div>
          <Title level={5} style={{ marginBottom: 8 }}>
            生产观测（只读）
          </Title>
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="当前回执">
              {prod.has_current_receipt ? <Tag color="green">有</Tag> : <Tag color="default">{prod.status_display}</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="失败日推进游标">
              {prod.cursor_advances_on_failed_day ? <Tag color="red">是（异常）</Tag> : <Tag color="green">否</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="手工推进" span={2}>
              {prod.manual_advance_allowed ? <Tag color="red">允许（异常）</Tag> : <Tag color="default">不允许（只读）</Tag>}
            </Descriptions.Item>
          </Descriptions>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {prod.note}
          </Text>
        </div>
      )}
    </Space>
  );
}

export default TscCanonicalPanel;
// @AI_GENERATED: end
