// @AI_GENERATED
/**
 * 跨数据集产品复验阶段（design D-GOV-01；任务 8.1–8.3）。
 *
 * 展示跨数据集验证批次（迁移 / 交互 / 隔离）、聚合证据束、SHA256 零污染校验，以及只读离线基准证据。
 * 红线：治理效力固定 none —— 证据束不能作为正式复验、不能设指针 / Promote；离线基准证据只读、无 calibration_audit_id。
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Alert, Button, Descriptions, Divider, Empty, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import StageScaffold from '../../components/StageScaffold';
import { ActionStateView } from '../../components/ActionStateView';
import { useProjectScope } from '../../../contexts/ProjectScopeContext';
import { pvProjectsApi } from '../../../services/pvProjectsApi';
import type {
  OfflineBenchmarkEvidence,
  ValidationBatch,
  ValidationEvidenceBundle,
  ZeroPollutionResult,
} from '../../../services/pvProjectsApi';

const { Text, Title } = Typography;

function extractErr(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
  return detail?.message || fallback;
}

/** 演示数据集：无外部数据源时驱动跨数据集验证批次。 */
function demoDatasets(): Array<Record<string, unknown>> {
  return [
    { dataset_key: 'pvdaq', source_ref: 'data/benchmark_raw/pvdaq/reruns/expansion_6months/analysis.parquet', dataset_version_id: 'dsv-pvdaq', content_digest: 'sha256:aa01' },
    { dataset_key: 'weihai', source_ref: 'data/ext/weihai_6m.parquet', dataset_version_id: 'dsv-weihai', content_digest: 'sha256:bb02' },
  ];
}

function BatchDetail({ validationId }: { validationId: string }): JSX.Element {
  const { scope, generation } = useProjectScope();
  const projectId = scope.projectId;
  const [bundle, setBundle] = useState<ValidationEvidenceBundle | null>(null);
  const [zp, setZp] = useState<ZeroPollutionResult | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    Promise.all([
      pvProjectsApi.getValidationEvidence(projectId, validationId),
      pvProjectsApi.getZeroPollution(projectId, validationId),
    ])
      .then(([b, z]) => {
        setBundle(b);
        setZp(z);
      })
      .catch(() => setBundle(null))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, validationId, generation]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <ActionStateView descriptor={{ state: 'loading', title: '正在读取证据束' }} />;
  if (!bundle) return <Text type="secondary">证据束不可用</Text>;

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Descriptions size="small" column={2} bordered title={`证据束 ${validationId}`}>
        <Descriptions.Item label="治理效力">
          <Tag color="default">{bundle.governance_effect}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="可作正式复验">
          {bundle.can_be_verification_evidence ? <Tag color="red">是（异常）</Tag> : <Tag color="green">否</Tag>}
        </Descriptions.Item>
        <Descriptions.Item label="完成 / 数据集">
          {bundle.completed_count} / {bundle.dataset_count}
        </Descriptions.Item>
        <Descriptions.Item label="零污染（SHA256）">
          {zp ? (zp.zero_pollution ? <Tag color="green">通过</Tag> : <Tag color="red">污染（异常）</Tag>) : '—'}
        </Descriptions.Item>
      </Descriptions>
      <div>
        <Text strong>维度覆盖：</Text>
        <Space wrap style={{ marginLeft: 8 }}>
          {Object.entries(bundle.dimension_summary).map(([dim, keys]) => (
            <Tag key={dim} color={keys.length ? 'blue' : 'default'}>
              {dim}: {keys.length ? keys.join(',') : '—'}
            </Tag>
          ))}
        </Space>
      </div>
      <Alert type="warning" showIcon message="治理效力固定 none" description={bundle.note} />
    </Space>
  );
}

export function ProjectValidationsStagePage(): JSX.Element {
  const { validationId } = useParams();
  const { scope, generation } = useProjectScope();
  const projectId = scope.projectId;
  const [batches, setBatches] = useState<ValidationBatch[]>([]);
  const [benchmarks, setBenchmarks] = useState<OfflineBenchmarkEvidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<string | null>(validationId || null);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    Promise.all([pvProjectsApi.listValidationBatches(projectId), pvProjectsApi.listOfflineBenchmarkEvidence(projectId)])
      .then(([b, ev]) => {
        setBatches(b.batches || []);
        setBenchmarks(ev.evidence || []);
      })
      .catch((e) => setError(extractErr(e, '跨数据集验证列表读取失败')))
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load, generation]);

  const onCreateDemo = async () => {
    setBusy(true);
    try {
      const res = await pvProjectsApi.createValidationBatch(projectId, { datasets: demoDatasets(), note: '演示跨数据集验证批次' });
      const vid = res.batch.validation_id;
      // 逐数据集登记只读结果（迁移 / 交互 / 隔离维度）。
      for (const ds of res.batch.datasets) {
        if (ds.dataset_key) {
          await pvProjectsApi.recordValidationResult(projectId, vid, {
            dataset_key: ds.dataset_key,
            metrics: { macro_f1: 0.5 },
            dimension_findings: { migration: true, isolation: true },
          });
        }
      }
      message.success('已创建演示跨数据集验证批次（治理效力 none）');
      setSelected(vid);
      load();
    } catch (e) {
      message.error(extractErr(e, '创建验证批次失败'));
    } finally {
      setBusy(false);
    }
  };

  const onRegisterBenchmark = async () => {
    setBusy(true);
    try {
      await pvProjectsApi.registerOfflineBenchmarkEvidence(projectId, {
        benchmark_source: 'pvdaq',
        manifest_ref: 'data/benchmark_raw/pvdaq/reruns/expansion_6months_20260907/analysis/ical_leakage_ablation/run_manifest.json',
      });
      message.success('已登记只读离线基准证据（治理效力 none，无 calibration_audit_id）');
      load();
    } catch (e) {
      message.error(extractErr(e, '登记离线基准证据失败'));
    } finally {
      setBusy(false);
    }
  };

  const batchColumns: ColumnsType<ValidationBatch> = [
    { title: '批次', dataIndex: 'validation_id', render: (v: string) => <Text code>{v}</Text> },
    {
      title: '数据集 / 维度',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>{rec.datasets.length} 数据集</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>{rec.dimensions.join(' / ')}</Text>
        </Space>
      ),
    },
    { title: '状态', dataIndex: 'status', render: (s: string) => <Tag>{s}</Tag> },
    { title: '治理效力', dataIndex: 'governance_effect', render: (v: string) => <Tag color="default">{v}</Tag> },
    {
      title: '操作',
      render: (_: unknown, rec) => (
        <Button size="small" onClick={() => setSelected(rec.validation_id)}>
          查看证据
        </Button>
      ),
    },
  ];

  const benchmarkColumns: ColumnsType<OfflineBenchmarkEvidence> = [
    { title: '证据版本', dataIndex: 'benchmark_evidence_version', render: (v: string) => <Text code>{v}</Text> },
    { title: '来源', dataIndex: 'benchmark_source' },
    { title: 'manifest', dataIndex: 'manifest_ref', render: (v?: string | null) => <Text style={{ fontSize: 11 }}>{v || '—'}</Text> },
    {
      title: 'calibration_audit_id',
      dataIndex: 'calibration_audit_id',
      render: (v: string | null) => (v ? <Text code>{v}</Text> : <Tag color="default">无注册表</Tag>),
    },
  ];

  if (loading) {
    return (
      <StageScaffold title="跨数据集产品复验" plannedTask="8.1" pendingNote="加载中…" />
    );
  }
  if (error) {
    return (
      <ActionStateView
        descriptor={{ state: 'recoverable_failure', title: '跨数据集验证加载失败', reason: error, nextAction: '刷新当前项目后重试', scope: { projectId } }}
      />
    );
  }

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="跨数据集产品复验（治理效力 none）"
        description="验证批次只证明迁移 / 交互 / 隔离，SHA256 零污染保证只读输入不被改写；证据束不能作为模型正式复验，也不能设指针 / Promote。离线基准证据只读、无 calibration_audit_id。"
      />

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <Title level={5} style={{ margin: 0 }}>验证批次</Title>
          <Button type="primary" onClick={onCreateDemo} loading={busy}>
            创建演示批次
          </Button>
        </div>
        {batches.length === 0 ? (
          <Empty description="暂无跨数据集验证批次。" />
        ) : (
          <Table rowKey="validation_id" size="small" columns={batchColumns} dataSource={batches} pagination={{ pageSize: 5, size: 'small' }} />
        )}
      </div>

      {selected && (
        <>
          <Divider style={{ margin: 0 }} />
          <BatchDetail validationId={selected} />
        </>
      )}

      <Divider style={{ margin: 0 }} />
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <Title level={5} style={{ margin: 0 }}>只读离线基准证据</Title>
          <Button onClick={onRegisterBenchmark} loading={busy}>
            登记 PVDAQ 基准证据
          </Button>
        </div>
        {benchmarks.length === 0 ? (
          <Text type="secondary">暂无离线基准证据。</Text>
        ) : (
          <Table rowKey="benchmark_evidence_version" size="small" columns={benchmarkColumns} dataSource={benchmarks} pagination={false} />
        )}
      </div>
    </Space>
  );
}

export default ProjectValidationsStagePage;
// @AI_GENERATED: end
