// @AI_GENERATED
/**
 * 工作流阶段（design §11.4 / §15；任务 3.1）。
 *
 * 项目工作流创建（从 canonical 模板 / 复制项目工作流 / 空白），绑定不可变数据版本，
 * 执行前预检（阻断 / 警告 / 通过 + 是否仅允许 experiment）。画布编辑仍按 scope 深链接进入独立编辑器。
 * 项目工作流与共享模板分离，绝不覆盖共享模板。
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert, Button, Input, Modal, Segmented, Select, Space, Table, Tag, Tooltip, Typography, message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import StageSlotGate from '../../components/StageSlotGate';
import { ActionStateView } from '../../components/ActionStateView';
import { useProjectScope } from '../../../contexts/ProjectScopeContext';
import { buildJourneyHref } from '../../../utils/journeyParams';
import { pvProjectsApi } from '../../../services/pvProjectsApi';
import type {
  ProjectWorkflow, DatasetVersion, PreflightResult, CreateProjectWorkflowRequest,
  FrozenSnapshot, WorkflowKind, WorkflowTemplateSummary, RunMode,
} from '../../../services/pvProjectsApi';

const { Text } = Typography;

/** 工作流用途文案（三类工作流；detection 共用且不可自建）。 */
const KIND_META: Record<WorkflowKind, { label: string; color: string; hint: string }> = {
  training: { label: '训练', color: 'blue', hint: '消费冻结快照 → 产模型工件；每条路径可有多个，竞争同一上岗名额' },
  labeling: { label: '打标', color: 'purple', hint: '消费未标注数据 + 辅助模型 → 产标签提案；每路径 canonical 一个' },
  detection: { label: '检测', color: 'default', hint: '共用且只读：消费 registry 指针模型；不可在项目内自建' },
};

/** 可选运行模式由工作流用途决定（对齐后端 RUN_MODE_CONTRACT_BY_KIND）。 */
const RUN_MODES_BY_KIND: Record<string, RunMode[]> = {
  training: ['experiment', 'training'],
  labeling: ['experiment', 'validation'],
  detection: ['prediction'],
};

const OVERALL_TAG: Record<string, { color: string; label: string }> = {
  passed: { color: 'success', label: '通过' },
  warning: { color: 'warning', label: '警告' },
  blocked: { color: 'error', label: '阻断' },
};
const CHECK_TAG: Record<string, string> = { passed: 'success', warning: 'warning', blocked: 'error' };

function WorkflowsStage({ slot }: { slot: string }): JSX.Element {
  const navigate = useNavigate();
  const { scope, generation, refresh } = useProjectScope();
  const projectId = scope.projectId;

  const [rows, setRows] = useState<ProjectWorkflow[]>([]);
  const [versions, setVersions] = useState<DatasetVersion[]>([]);
  const [snapshots, setSnapshots] = useState<FrozenSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [mode, setMode] = useState<CreateProjectWorkflowRequest['mode']>('template');
  const [kind, setKind] = useState<WorkflowKind>('training');
  const [name, setName] = useState('');
  const [versionId, setVersionId] = useState<string | undefined>(undefined);
  const [snapshotId, setSnapshotId] = useState<string | undefined>(undefined);
  const [copySourceId, setCopySourceId] = useState<string | undefined>(undefined);
  const [templates, setTemplates] = useState<WorkflowTemplateSummary[]>([]);
  const [templateId, setTemplateId] = useState<string | undefined>(undefined);
  const [creating, setCreating] = useState(false);
  // 发起执行（此前 startExecution 在本目录零调用方，链路在预检后就断了）
  const [executeTarget, setExecuteTarget] = useState<ProjectWorkflow | null>(null);
  const [runMode, setRunMode] = useState<RunMode>('experiment');
  const [executing, setExecuting] = useState(false);

  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [preflightOpen, setPreflightOpen] = useState(false);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    Promise.all([
      pvProjectsApi.listProjectWorkflows(projectId, slot),
      pvProjectsApi.listVersions(projectId).catch(() => ({ project_id: projectId, versions: [] })),
      pvProjectsApi.getCumulative(projectId, slot).catch(() => null),
      pvProjectsApi.listWorkflowTemplates(slot).catch(() => ({ slot, templates: [], total: 0 })),
    ])
      .then(([wf, ver, cum, tpl]) => {
        setRows(wf.workflows || []);
        setVersions(ver.versions || []);
        setSnapshots(cum?.frozen_snapshots || []);
        setTemplates(tpl.templates || []);
      })
      .catch(() => setError('项目工作流读取失败'))
      .finally(() => setLoading(false));
  }, [projectId, slot, generation]);

  useEffect(() => {
    load();
  }, [load]);

  const submitCreate = async () => {
    if (!projectId || !name.trim()) return;
    setCreating(true);
    try {
      await pvProjectsApi.createProjectWorkflow(projectId, {
        slot,
        mode,
        name: name.trim(),
        workflow_kind: kind,
        dataset_version_id: versionId,
        source_snapshot_id: kind === 'training' ? snapshotId : undefined,
        source_template_id: mode === 'template' ? templateId : undefined,
        source_project_workflow_id: mode === 'copy' ? copySourceId : undefined,
      });
      message.success('已创建项目工作流版本（未覆盖共享模板）');
      setCreateOpen(false);
      setName('');
      setVersionId(undefined);
      setSnapshotId(undefined);
      setCopySourceId(undefined);
      setTemplateId(undefined);
      load();
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail;
      message.error(detail?.message || '创建失败');
    } finally {
      setCreating(false);
    }
  };

  const doPreflight = async (workflowId: string) => {
    if (!projectId) return;
    try {
      const res = await pvProjectsApi.runPreflight(projectId, { slot, project_workflow_id: workflowId });
      setPreflight(res);
      setPreflightOpen(true);
    } catch {
      message.error('预检失败');
    }
  };

  /** 发起执行：把「预检 → 执行 → 运行中心」这条链路接上（此前 startExecution 零调用方）。 */
  const doExecute = async () => {
    if (!projectId || !executeTarget) return;
    setExecuting(true);
    try {
      const exec = await pvProjectsApi.startExecution(projectId, {
        slot,
        project_workflow_id: executeTarget.project_workflow_id,
        run_mode: runMode,
        run_domain: 'project',
        dataset_version_id: executeTarget.bound_dataset_version_id || undefined,
      });
      message.success(`已登记执行 ${exec.execution_id}（${exec.status}）`);
      setExecuteTarget(null);
      navigate(`/projects/${projectId}/runs?slot=${slot}`);
    } catch (e) {
      const detail =
        (e as { payload?: { message?: string } })?.payload?.message ||
        (e as { response?: { data?: { detail?: { message?: string } } } })?.response?.data?.detail?.message;
      message.error(detail || '发起执行失败（若预检 blocked 会先被拦下）');
    } finally {
      setExecuting(false);
    }
  };

  const columns: ColumnsType<ProjectWorkflow> = [
    {
      title: '项目工作流',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={0}>
          <Text strong>{rec.name}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {rec.project_workflow_id} · v{rec.version} · {rec.create_mode}
          </Text>
        </Space>
      ),
    },
    {
      title: '用途',
      dataIndex: 'workflow_kind',
      render: (k?: WorkflowKind) => {
        const meta = KIND_META[k || 'training'];
        return (
          <Tooltip title={meta.hint}>
            <Tag color={meta.color}>{meta.label}</Tag>
          </Tooltip>
        );
      },
    },
    {
      title: '训练输入（冻结快照）',
      render: (_: unknown, rec) =>
        rec.workflow_kind && rec.workflow_kind !== 'training' ? (
          <Text type="secondary">不适用</Text>
        ) : rec.bound_snapshot_id ? (
          <Space direction="vertical" size={0}>
            <Text code style={{ fontSize: 11 }}>{rec.bound_snapshot_id}</Text>
            <Text type="secondary" style={{ fontSize: 11 }}>{rec.bound_snapshot_type}</Text>
          </Space>
        ) : (
          <Tooltip title="未绑定快照可做实验，但产出无法成为可治理候选">
            <Tag color="warning">未绑定</Tag>
          </Tooltip>
        ),
    },
    {
      title: '绑定数据版本',
      dataIndex: 'bound_dataset_version_id',
      render: (v: string | null) => (v ? <Text code style={{ fontSize: 11 }}>{v}</Text> : <Text type="secondary">未绑定</Text>),
    },
    {
      title: '操作',
      render: (_: unknown, rec) => (
        <Space>
          <Button size="small" onClick={() => doPreflight(rec.project_workflow_id)}>
            执行前预检
          </Button>
          <Button
            size="small"
            type="primary"
            ghost
            onClick={() => {
              setExecuteTarget(rec);
              setRunMode((RUN_MODES_BY_KIND[rec.workflow_kind || 'training'] || ['experiment'])[0]);
            }}
          >
            发起执行
          </Button>
          <Button
            size="small"
            type="link"
            onClick={() =>
              navigate(
                buildJourneyHref('/algorithm-dev/workflows', {
                  projectId,
                  slot,
                  datasetVersionId: rec.bound_dataset_version_id || undefined,
                }),
              )
            }
          >
            画布编辑
          </Button>
        </Space>
      ),
    },
  ];

  if (loading) {
    return <ActionStateView descriptor={{ state: 'loading', title: '正在读取项目工作流' }} />;
  }
  if (error) {
    return (
      <ActionStateView
        descriptor={{ state: 'recoverable_failure', title: '工作流阶段加载失败', reason: error, nextAction: '刷新当前项目后重试', scope: { projectId, slot } }}
        onRefresh={refresh}
      />
    );
  }

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="项目工作流（与共享模板分离）"
        description="创建项目工作流版本、绑定不可变数据版本、执行前预检；创建不会覆盖共享模板。画布编辑按当前项目 / 路径深链接进入独立编辑器。"
      />
      <Space>
        <Button type="primary" onClick={() => setCreateOpen(true)}>
          新建项目工作流
        </Button>
        <Button
          onClick={() =>
            navigate(buildJourneyHref('/algorithm-dev/workflows', { projectId, slot, datasetVersionId: scope.datasetVersionId }))
          }
        >
          打开工作流编排（携当前项目 / 路径）
        </Button>
      </Space>

      {rows.length === 0 ? (
        <ActionStateView
          descriptor={{
            state: 'initial_empty',
            title: '当前路径暂无项目工作流',
            reason: '尚未在该项目 / 路径下创建项目工作流。',
            nextAction: '点击"新建项目工作流"，从模板 / 复制 / 空白创建并绑定数据版本',
            scope: { projectId, slot },
          }}
        />
      ) : (
        <Table rowKey="project_workflow_id" size="small" columns={columns} dataSource={rows} pagination={{ pageSize: 10, size: 'small' }} />
      )}

      <Modal
        open={createOpen}
        title="新建项目工作流"
        okText="创建"
        confirmLoading={creating}
        okButtonProps={{
          disabled:
            !name.trim() ||
            (mode === 'copy' && !copySourceId) ||
            (mode === 'template' && !templateId),
        }}
        onOk={submitCreate}
        onCancel={() => setCreateOpen(false)}
        destroyOnHidden
      >
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>用途</div>
            <Segmented
              value={kind}
              onChange={(v) => setKind(v as WorkflowKind)}
              options={[
                { label: '训练（可多个）', value: 'training' },
                { label: '打标（canonical）', value: 'labeling' },
              ]}
            />
            <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 6 }}>
              {KIND_META[kind].hint}；检测工作流共用且只读，不可在项目内自建。
            </div>
          </div>
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>创建方式</div>
            <Segmented
              value={mode}
              onChange={(v) => setMode(v as CreateProjectWorkflowRequest['mode'])}
              options={[
                { label: '从模板', value: 'template' },
                { label: '复制项目工作流', value: 'copy' },
                { label: '空白', value: 'blank' },
              ]}
            />
          </div>
          {mode === 'template' && (
            <div>
              <div style={{ fontSize: 13, marginBottom: 6 }}>复用模板（本路径）</div>
              <Select
                style={{ width: '100%' }}
                placeholder={templates.length ? '选择要复用的 canonical 模板' : '本路径暂无可用模板'}
                value={templateId}
                onChange={setTemplateId}
                options={templates.map((t) => ({
                  value: t.template_id,
                  label: `${t.name}（${t.node_count} 节点）`,
                }))}
              />
              <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 6 }}>
                模板来自平台已有的同路径工作流；创建出的是项目内副本，不会覆盖共享模板。
              </div>
            </div>
          )}
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>名称</div>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="项目工作流名称" />
          </div>
          {mode === 'copy' && (
            <div>
              <div style={{ fontSize: 13, marginBottom: 6 }}>复制来源</div>
              <Select
                style={{ width: '100%' }}
                placeholder="选择要复制的项目工作流"
                value={copySourceId}
                onChange={setCopySourceId}
                options={rows.map((r) => ({ value: r.project_workflow_id, label: `${r.name} (v${r.version})` }))}
              />
            </div>
          )}
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>绑定数据版本（load 节点）</div>
            <Select
              allowClear
              style={{ width: '100%' }}
              placeholder={versions.length ? '选择不可变数据版本' : '当前项目暂无已发布数据版本'}
              value={versionId}
              onChange={setVersionId}
              options={versions.map((v) => ({ value: v.dataset_version_id, label: `${v.dataset_version_id}（${v.content_digest.slice(0, 12)}…）` }))}
            />
          </div>
          {kind === 'training' && (
            <div>
              <div style={{ fontSize: 13, marginBottom: 6 }}>训练输入：冻结快照</div>
              <Select
                allowClear
                style={{ width: '100%' }}
                placeholder={snapshots.length ? '选择本路径的冻结快照' : '当前路径暂无冻结快照（先在累计阶段冻结）'}
                value={snapshotId}
                onChange={setSnapshotId}
                options={snapshots.map((s) => ({
                  value: s.snapshot_id,
                  label: `${s.snapshot_id} · ${s.snapshot_type} · 纳入 ${s.included_count} 事件`,
                }))}
              />
              <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 6 }}>
                绑定同一个快照的多个训练工作流可公平比较；未绑定只能做实验，产出无法成为可治理候选。
              </div>
            </div>
          )}
        </Space>
      </Modal>

      <Modal
        open={!!executeTarget}
        title="发起执行"
        okText="发起执行"
        confirmLoading={executing}
        onOk={doExecute}
        onCancel={() => setExecuteTarget(null)}
        destroyOnHidden
      >
        {executeTarget && (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <div>
              <Text strong>{executeTarget.name}</Text>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {executeTarget.project_workflow_id} · v{executeTarget.version} ·{' '}
                  {executeTarget.workflow_kind || 'training'}
                </Text>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 13, marginBottom: 6 }}>运行模式</div>
              <Segmented
                value={runMode}
                onChange={(v) => setRunMode(v as RunMode)}
                options={(RUN_MODES_BY_KIND[executeTarget.workflow_kind || 'training'] || ['experiment']).map((m) => ({
                  label: m,
                  value: m,
                }))}
              />
              <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 6 }}>
                可选模式由工作流用途决定；experiment 不产生可治理候选，预检 blocked 会被服务端拒绝。
              </div>
            </div>
          </Space>
        )}
      </Modal>

      <Modal
        open={preflightOpen}
        title="执行前预检"
        footer={<Button onClick={() => setPreflightOpen(false)}>关闭</Button>}
        onCancel={() => setPreflightOpen(false)}
        width={640}
        destroyOnHidden
      >
        {preflight && (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Space>
              <Text strong>总体：</Text>
              <Tag color={OVERALL_TAG[preflight.overall]?.color}>{OVERALL_TAG[preflight.overall]?.label || preflight.overall}</Tag>
              {preflight.experiment_only && <Tag color="orange">仅允许 experiment</Tag>}
            </Space>
            <Table
              rowKey="key"
              size="small"
              pagination={false}
              dataSource={preflight.checks}
              columns={[
                { title: '检查项', dataIndex: 'label' },
                {
                  title: '状态',
                  dataIndex: 'status',
                  render: (s: string) => <Tag color={CHECK_TAG[s]}>{OVERALL_TAG[s]?.label || s}</Tag>,
                },
                { title: '说明', dataIndex: 'detail' },
              ]}
            />
          </Space>
        )}
      </Modal>
    </Space>
  );
}

export function ProjectWorkflowsStagePage(): JSX.Element {
  return (
    <StageSlotGate prompt="选择一条诊断路径以创建 / 查看其项目工作流。">
      {(slot) => <WorkflowsStage slot={slot} />}
    </StageSlotGate>
  );
}

export default ProjectWorkflowsStagePage;
// @AI_GENERATED: end
