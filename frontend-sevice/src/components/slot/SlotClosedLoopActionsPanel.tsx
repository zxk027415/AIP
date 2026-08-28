/**
 * SlotClosedLoopActionsPanel — G7.3 四动作显式闭环：快照 build / 重训 / 复验 / Promote（不自动串行）。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  AuditOutlined,
  CloudUploadOutlined,
  RocketOutlined,
  SafetyCertificateOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import {
  getSlotWorkflowConfig,
  type PvProductSlot,
} from '../../config/slotProductConfig';
import { slotDatasetsApi, type SnapshotChainView } from '../../services/slotDatasetsApi';
import {
  slotGovernanceApi,
  type ModelCandidateView,
  type SlotRegistryView,
  type VerifyAsyncJobView,
} from '../../services/slotGovernanceApi';
import { pipelineApi } from '../../services/workflowEnhancedApi';
import { freezeIdOf, slotCumulativeApi } from '../../services/slotCumulativeApi';

const { Text, Paragraph } = Typography;

function pickList<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[];
  if (payload && typeof payload === 'object') {
    const nested = (payload as Record<string, unknown>)[key];
    if (Array.isArray(nested)) return nested as T[];
  }
  return [];
}

type ActionKey = 'build' | 'retrain' | 'verify' | 'promote' | 'register' | 'complete';

interface Props {
  slot: PvProductSlot;
  snapshotChain: SnapshotChainView | null;
  reviewedAnnotationIds: string[];
  registry?: SlotRegistryView | null;
  candidates?: ModelCandidateView[];
  latestTrainExecution?: {
    workflowId?: string;
    executionId?: string;
    modelPath?: string;
  } | null;
  onChanged?: () => void;
}

async function pollExecution(workflowId: string, executionId: string) {
  const deadline = Date.now() + 15 * 60 * 1000;
  while (Date.now() < deadline) {
    const resp = await pipelineApi.getExecutionStatus(workflowId, executionId);
    const status = resp?.status;
    if (status === 'success' || status === 'failed' || status === 'cancelled') {
      return resp;
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error('执行超时（15 分钟）');
}

const SlotClosedLoopActionsPanel: React.FC<Props> = ({
  slot,
  snapshotChain,
  reviewedAnnotationIds,
  registry: seededRegistry,
  candidates: seededCandidates,
  latestTrainExecution,
  onChanged,
}) => {
  const config = getSlotWorkflowConfig(slot);
  const [registry, setRegistry] = useState<SlotRegistryView | null>(null);
  const [candidates, setCandidates] = useState<ModelCandidateView[]>([]);
  const [verifications, setVerifications] = useState<Record<string, unknown>[]>([]);
  const [pendingVerifyJobs, setPendingVerifyJobs] = useState<VerifyAsyncJobView[]>([]);
  const [completingJobId, setCompletingJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeAction, setActiveAction] = useState<ActionKey | null>(null);
  const [completeTargetJob, setCompleteTargetJob] = useState<VerifyAsyncJobView | null>(null);

  const [buildForm] = Form.useForm();
  const [promoteForm] = Form.useForm();
  const [verifyForm] = Form.useForm();
  const [registerForm] = Form.useForm();
  const [completeForm] = Form.useForm();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [reg, cand, ver, pendingJobs] = await Promise.all([
        seededRegistry !== undefined
          ? Promise.resolve(seededRegistry)
          : slotGovernanceApi.getRegistry(slot).catch(() => null),
        seededCandidates !== undefined
          ? Promise.resolve({ candidates: seededCandidates })
          : slotGovernanceApi.listModelCandidates(slot).catch(() => ({ candidates: [] as ModelCandidateView[] })),
        slotGovernanceApi.listVerifications(slot).catch(() => ({ verifications: [] as Record<string, unknown>[] })),
        slotGovernanceApi.listVerifyAsyncJobs(slot, 'pending').catch(() => ({ jobs: [] as VerifyAsyncJobView[] })),
      ]);
      setRegistry(reg ?? null);
      setCandidates(pickList<ModelCandidateView>(cand, 'candidates'));
      setVerifications(pickList<Record<string, unknown>>(ver, 'verifications'));
      setPendingVerifyJobs(pickList<VerifyAsyncJobView>(pendingJobs, 'jobs'));
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        || (err as Error)?.message
        || '治理数据读取失败';
      message.error(typeof detail === 'string' ? detail : '治理数据读取失败');
    } finally {
      setLoading(false);
    }
  }, [slot, seededRegistry, seededCandidates]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const passedVerifications = useMemo(
    () => verifications.filter((v) => v.passed === true || v.status === 'passed'),
    [verifications],
  );

  const openBuildModal = () => {
    buildForm.setFieldsValue({
      reason: 'ui build next snapshot',
      reviewed_count: reviewedAnnotationIds.length,
    });
    setActiveAction('build');
  };

  const handleBuild = async () => {
    if (!snapshotChain?.snapshot_id) {
      message.warning('请先 bootstrap 快照链');
      return;
    }
    const values = await buildForm.validateFields();
    setLoading(true);
    try {
      await slotDatasetsApi.buildSnapshot({
        slot,
        snapshot_id: snapshotChain.snapshot_id,
        base_snapshot_version: snapshotChain.latest_version,
        reviewed_annotation_ids: reviewedAnnotationIds.slice(-Math.max(1, values.reviewed_count || 1)),
        idempotency_key: `ui-build-${snapshotChain.latest_version}-${Date.now()}`,
        reason: values.reason,
      });
      message.success('快照构建成功（未自动重训）');
      setActiveAction(null);
      onChanged?.();
      await refresh();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || '构建失败');
    } finally {
      setLoading(false);
    }
  };

  const handleRetrain = async () => {
    if (!config) return;
    setLoading(true);
    try {
      let datasetId: string | undefined;
      if (slot === 'pv_point') {
        try {
          const ledger = await slotCumulativeApi.getLedger(slot);
          datasetId = freezeIdOf(slot, ledger.latest_freeze) || undefined;
        } catch {
          datasetId = undefined;
        }
      }
      const { execution_id: executionId } = await pipelineApi.executeAsync(config.trainWorkflowId, {
        slot,
        execution_purpose: 'product_workflow',
        ...(datasetId ? { dataset_id: datasetId } : {}),
      });
      message.info(`重训已启动：${executionId}${datasetId ? ` · ${datasetId}` : ''}`);
      const result = await pollExecution(config.trainWorkflowId, executionId);
      if (result?.status === 'success') {
        message.success('重训 execution 成功（请手动登记 model candidate，未自动复验）');
      } else {
        message.error(`重训结束：${result?.status || 'unknown'}`);
      }
      onChanged?.();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err?.message || '重训失败');
    } finally {
      setLoading(false);
    }
  };

  const openRegisterModal = () => {
    registerForm.setFieldsValue({
      source_workflow_id: latestTrainExecution?.workflowId || config?.trainWorkflowId,
      source_execution_id: latestTrainExecution?.executionId || '',
      model_artifact_ref: latestTrainExecution?.modelPath || '',
    });
    setActiveAction('register');
  };

  const handleRegister = async () => {
    const values = await registerForm.validateFields();
    setLoading(true);
    try {
      await slotGovernanceApi.registerModelCandidate({
        slot,
        source_workflow_id: values.source_workflow_id,
        source_execution_id: values.source_execution_id,
        model_artifact_ref: values.model_artifact_ref,
      });
      message.success('model candidate 已登记（未自动复验）');
      setActiveAction(null);
      await refresh();
      onChanged?.();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || '登记失败');
    } finally {
      setLoading(false);
    }
  };

  const openVerifyModal = () => {
    verifyForm.setFieldsValue({
      model_candidate_id: candidates[candidates.length - 1]?.model_candidate_id,
      registry_version_at_start: registry?.registry_version ?? 0,
    });
    setActiveAction('verify');
  };

  const handleVerify = async () => {
    const values = await verifyForm.validateFields();
    setLoading(true);
    try {
      const resp = await slotGovernanceApi.startVerifyAsync({
        slot,
        model_candidate_id: values.model_candidate_id,
        idempotency_key: `ui-verify-${values.model_candidate_id}-${Date.now()}`,
        registry_version_at_start: values.registry_version_at_start,
      });
      message.success(`复验任务已创建：${resp.job?.comparison_id || '—'}（请在下表执行 evaluation 并 complete）`);
      setActiveAction(null);
      await refresh();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || '复验启动失败');
    } finally {
      setLoading(false);
    }
  };

  const runEvaluationAndComplete = async (job: VerifyAsyncJobView) => {
    const workflowId = job.verification_workflow_ref || config?.trainWorkflowId;
    if (!workflowId) {
      message.error('缺少 verification_workflow_ref');
      return;
    }
    setCompletingJobId(job.comparison_id);
    setLoading(true);
    try {
      const { execution_id: executionId } = await pipelineApi.executeAsync(workflowId, {
        slot,
        execution_purpose: 'product_workflow',
      });
      message.info(`evaluation 已启动：${executionId}`);
      const result = await pollExecution(workflowId, executionId);
      if (result?.status !== 'success') {
        message.error(`evaluation 未成功：${result?.status || 'unknown'}（未 complete）`);
        return;
      }
      const done = await slotGovernanceApi.completeVerifyAsync(job.comparison_id, executionId);
      const passed = done.verification?.passed;
      message.success(
        `复验 complete：verification_id=${String(done.verification?.verification_id || '—')} · passed=${String(passed)}（未自动 Promote）`,
      );
      await refresh();
      onChanged?.();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || '复验 complete 失败');
    } finally {
      setCompletingJobId(null);
      setLoading(false);
    }
  };

  const openCompleteModal = (job: VerifyAsyncJobView) => {
    setCompleteTargetJob(job);
    completeForm.setFieldsValue({
      verification_execution_id: '',
    });
    setActiveAction('complete');
  };

  const handleManualComplete = async () => {
    if (!completeTargetJob) return;
    const values = await completeForm.validateFields();
    setLoading(true);
    try {
      const done = await slotGovernanceApi.completeVerifyAsync(
        completeTargetJob.comparison_id,
        values.verification_execution_id,
      );
      message.success(`已绑定 execution 并完成复验：${String(done.verification?.verification_id || '—')}`);
      setActiveAction(null);
      setCompleteTargetJob(null);
      await refresh();
      onChanged?.();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || 'complete 失败');
    } finally {
      setLoading(false);
    }
  };

  const pendingJobColumns: ColumnsType<VerifyAsyncJobView> = [
    { title: 'comparison_id', dataIndex: 'comparison_id', key: 'comparison_id', ellipsis: true },
    { title: 'candidate', dataIndex: 'model_candidate_id', key: 'model_candidate_id', ellipsis: true },
    {
      title: 'workflow',
      dataIndex: 'verification_workflow_ref',
      key: 'verification_workflow_ref',
      ellipsis: true,
      render: (value: string | undefined) => value || config?.trainWorkflowId || '—',
    },
    {
      title: '操作',
      key: 'actions',
      render: (_, job) => (
        <Space wrap>
          <Button
            size="small"
            type="primary"
            loading={completingJobId === job.comparison_id}
            onClick={() => void runEvaluationAndComplete(job)}
          >
            执行 evaluation + complete
          </Button>
          <Button size="small" onClick={() => openCompleteModal(job)}>
            绑定已有 execution
          </Button>
        </Space>
      ),
    },
  ];

  const openPromoteModal = () => {
    const latestPassed = passedVerifications[passedVerifications.length - 1];
    promoteForm.setFieldsValue({
      verification_id: latestPassed?.verification_id || '',
      model_candidate_id: candidates[candidates.length - 1]?.model_candidate_id || '',
      expected_registry_version: registry?.registry_version ?? 0,
      operator: 'ui-operator',
      reason: 'ui promote after verification',
      set_as_production: false,
    });
    setActiveAction('promote');
  };

  const handlePromote = async () => {
    const values = await promoteForm.validateFields();
    setLoading(true);
    try {
      const resp = await slotGovernanceApi.promoteModelCandidate(values.model_candidate_id, {
        verification_id: values.verification_id,
        operator: values.operator,
        reason: values.reason,
        expected_registry_version: values.expected_registry_version,
        idempotency_key: `ui-promote-${values.model_candidate_id}-${Date.now()}`,
        production_slot: slot,
        set_as_production: values.set_as_production === true,
      });
      message.success(`Promote 完成 · registry v${resp.registry?.registry_version ?? '?'}`);
      setActiveAction(null);
      await refresh();
      onChanged?.();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || 'Promote 失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card
      size="small"
      title={
        <Space>
          <AuditOutlined />
          <span>闭环四动作（G7.3）</span>
          <Tag>{slot}</Tag>
        </Space>
      }
      extra={<Button size="small" onClick={() => void refresh()} loading={loading}>刷新治理</Button>}
    >
      <Paragraph type="secondary" style={{ marginBottom: 12 }}>
        构建快照、重训、复验、Promote 为<strong>四个独立动作</strong>；任一步失败不自动继续。
        点路径「从固定版本重训」默认绑定累计冻结版；Promote 打开 Champion 才会写入生产。
      </Paragraph>

      <Descriptions size="small" bordered column={2} style={{ marginBottom: 12 }}>
        <Descriptions.Item label="registry">{registry?.empty ? '空' : `v${registry?.registry_version ?? 0}`}</Descriptions.Item>
        <Descriptions.Item label="快照链（G5）">{snapshotChain?.snapshot_id ? `v${snapshotChain.latest_version}` : '未初始化'}</Descriptions.Item>
        <Descriptions.Item label="待累计审核">{reviewedAnnotationIds.length} 条</Descriptions.Item>
        <Descriptions.Item label="model candidates">{candidates.length}</Descriptions.Item>
        <Descriptions.Item label="pending 复验 job">{pendingVerifyJobs.length}</Descriptions.Item>
        <Descriptions.Item label="passed 复验">{passedVerifications.length}</Descriptions.Item>
        <Descriptions.Item label="最近 train" span={2}>
          {latestTrainExecution?.executionId ? (
            <Link to={`/algorithm-dev/workflow-editor/${latestTrainExecution.workflowId}`}>
              {latestTrainExecution.executionId}
            </Link>
          ) : '—'}
        </Descriptions.Item>
      </Descriptions>

      <Space wrap style={{ marginBottom: 12 }}>
        <Button icon={<CloudUploadOutlined />} onClick={openBuildModal} disabled={!snapshotChain?.snapshot_id}>
          1. 构建下一快照
        </Button>
        <Button icon={<ThunderboltOutlined />} onClick={() => void handleRetrain()} loading={loading}>
          2. 从固定版本重训
        </Button>
        <Button onClick={openRegisterModal} disabled={!latestTrainExecution?.executionId && candidates.length === 0}>
          登记 model candidate
        </Button>
        <Button icon={<SafetyCertificateOutlined />} onClick={openVerifyModal} disabled={candidates.length === 0}>
          3. 发起复验
        </Button>
        <Button icon={<RocketOutlined />} type="primary" onClick={openPromoteModal} disabled={passedVerifications.length === 0}>
          4. Promote
        </Button>
      </Space>

      {pendingVerifyJobs.length > 0 && (
        <>
          <Paragraph type="secondary" style={{ marginBottom: 8 }}>
            pending 复验任务：可「执行 evaluation + complete」（仍不自动 Promote），或绑定已有 execution_id。
          </Paragraph>
          <Table
            size="small"
            rowKey="comparison_id"
            columns={pendingJobColumns}
            dataSource={pendingVerifyJobs}
            pagination={false}
            style={{ marginBottom: 12 }}
          />
        </>
      )}

      <Modal
        title="构建下一版快照"
        open={activeAction === 'build'}
        onCancel={() => setActiveAction(null)}
        onOk={() => void handleBuild()}
        confirmLoading={loading}
        okText="确认构建"
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="不会自动触发重训或复验"
        />
        <Form form={buildForm} layout="vertical">
          <Form.Item label="base_snapshot_version">
            <Input value={String(snapshotChain?.latest_version ?? 0)} disabled />
          </Form.Item>
          <Form.Item name="reviewed_count" label="纳入 reviewed 条数（从最近 N 条）" rules={[{ required: true }]}>
            <Input type="number" min={1} />
          </Form.Item>
          <Form.Item name="reason" label="reason" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="登记 model candidate"
        open={activeAction === 'register'}
        onCancel={() => setActiveAction(null)}
        onOk={() => void handleRegister()}
        confirmLoading={loading}
      >
        <Form form={registerForm} layout="vertical">
          <Form.Item name="source_workflow_id" label="source_workflow_id" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="source_execution_id" label="source_execution_id" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="model_artifact_ref" label="model_artifact_ref" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="发起复验（verify-async）"
        open={activeAction === 'verify'}
        onCancel={() => setActiveAction(null)}
        onOk={() => void handleVerify()}
        confirmLoading={loading}
      >
        <Alert type="warning" showIcon style={{ marginBottom: 12 }} message="创建 job 后需 complete 绑定真实 evaluation execution" />
        <Form form={verifyForm} layout="vertical">
          <Form.Item name="model_candidate_id" label="model_candidate_id" rules={[{ required: true }]}>
            <Select
              options={candidates.map((c) => ({
                label: `${c.model_candidate_id} · ${c.status}`,
                value: c.model_candidate_id,
              }))}
            />
          </Form.Item>
          <Form.Item name="registry_version_at_start" label="registry_version_at_start">
            <Input type="number" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Promote model candidate"
        open={activeAction === 'promote'}
        onCancel={() => setActiveAction(null)}
        onOk={() => void handlePromote()}
        confirmLoading={loading}
        okText="确认 Promote"
      >
        <Form form={promoteForm} layout="vertical">
          <Form.Item name="model_candidate_id" label="model_candidate_id" rules={[{ required: true }]}>
            <Select
              options={candidates.map((c) => ({
                label: c.model_candidate_id,
                value: c.model_candidate_id,
              }))}
            />
          </Form.Item>
          <Form.Item name="verification_id" label="verification_id（须 passed）" rules={[{ required: true }]}>
            <Select
              options={passedVerifications.map((v) => ({
                label: String(v.verification_id || v.comparison_id || ''),
                value: String(v.verification_id || ''),
              }))}
            />
          </Form.Item>
          <Form.Item name="expected_registry_version" label="expected_registry_version" rules={[{ required: true }]}>
            <Input type="number" />
          </Form.Item>
          <Form.Item name="operator" label="operator" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="reason" label="reason" rules={[{ required: true }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="set_as_production" label="写入 Champion / 生产" valuePropName="checked">
            <Switch checkedChildren="Champion" unCheckedChildren="仅 Challenger" />
          </Form.Item>
        </Form>
        <Alert
          type="warning"
          showIcon
          message="打开 Champion 才会 set_as_production=true"
          description="默认只登记 Challenger。点路径和天路径要各有一条 Champion，才能从部署页切生产流量。"
        />
      </Modal>

      <Modal
        title="绑定已有 evaluation execution"
        open={activeAction === 'complete'}
        onCancel={() => {
          setActiveAction(null);
          setCompleteTargetJob(null);
        }}
        onOk={() => void handleManualComplete()}
        confirmLoading={loading}
        okText="complete 复验"
      >
        {completeTargetJob && (
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message={`comparison_id: ${completeTargetJob.comparison_id}`}
          />
        )}
        <Form form={completeForm} layout="vertical">
          <Form.Item
            name="verification_execution_id"
            label="verification_execution_id（须 succeeded）"
            rules={[{ required: true }]}
          >
            <Input placeholder="exec-..." />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default SlotClosedLoopActionsPanel;
