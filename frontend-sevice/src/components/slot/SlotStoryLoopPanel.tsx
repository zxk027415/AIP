/**
 * SlotStoryLoopPanel — 对打标模板里的无标签输入执行打标，确认提案写入累计集。
 * 执行前必须选择/上传数据集；不改模板磁盘上的默认 file_path。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Input,
  Modal,
  Select,
  Space,
  Steps,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  ExperimentOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import {
  getSlotWorkflowConfig,
  type PvProductSlot,
} from '../../config/slotProductConfig';
import { datasetApi, enhancedWorkflowApi, pipelineApi } from '../../services/workflowEnhancedApi';
import { trainingWorkspaceApi } from '../../services/iterativeLabelingApi';
import {
  freezeIdOf,
  slotCumulativeApi,
  type CumulativeLedger,
} from '../../services/slotCumulativeApi';
import SlotLabelProposalReviewPanel from './SlotLabelProposalReviewPanel';

const { Paragraph, Text } = Typography;

type ProposalRow = {
  proposal_id: string;
  status?: string;
  created_at?: string;
  clusters?: Record<string, {
    proposed_label_name?: string;
    member_count?: number;
    suggested_label_names?: string[];
  }>;
};

interface Props {
  slot: PvProductSlot;
  onChanged?: () => void;
}

function toBackendRelative(path: string): string {
  const normalized = String(path || '').replace(/\\/g, '/').trim();
  if (!normalized) return '';
  const uploads = normalized.split('/data/uploads/');
  if (uploads.length > 1) return `data/uploads/${uploads[uploads.length - 1]}`;
  if (normalized.startsWith('backend-service/')) return normalized;
  return normalized;
}

function isLabelingFixture(path: string): boolean {
  return /g10_clustering_fixture/i.test(toBackendRelative(path));
}

async function pollExecution(workflowId: string, executionId: string) {
  const deadline = Date.now() + 10 * 60 * 1000;
  while (Date.now() < deadline) {
    const resp = await pipelineApi.getExecutionStatus(workflowId, executionId);
    const status = resp?.status;
    if (status === 'success' || status === 'failed' || status === 'cancelled') {
      return resp;
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error('执行超时');
}

const SlotStoryLoopPanel: React.FC<Props> = ({ slot, onChanged }) => {
  const config = getSlotWorkflowConfig(slot);
  const [loading, setLoading] = useState(false);
  const [runningLabel, setRunningLabel] = useState(false);
  const [proposals, setProposals] = useState<ProposalRow[]>([]);
  const [ledger, setLedger] = useState<CumulativeLedger | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [templatePath, setTemplatePath] = useState('');
  const [selectedPath, setSelectedPath] = useState('');
  const [availablePaths, setAvailablePaths] = useState<Array<{ label: string; value: string }>>([]);
  const [currentStep, setCurrentStep] = useState(0);
  const [lastExecutionId, setLastExecutionId] = useState('');
  const [reviewProposalId, setReviewProposalId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [proposalBody, ledgerBody] = await Promise.all([
        trainingWorkspaceApi.listLabelProposals(slot).catch(() => ({ proposals: [] as ProposalRow[] })),
        slotCumulativeApi.getLedger(slot).catch(() => null),
      ]);
      const proposalRows = Array.isArray(proposalBody?.proposals)
        ? proposalBody.proposals
        : Array.isArray(proposalBody)
          ? proposalBody
          : [];
      setProposals(proposalRows as ProposalRow[]);
      setLedger(ledgerBody);
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
        || (err as Error)?.message
        || '故事线数据读取失败';
      message.error(typeof detail === 'string' ? detail : '故事线数据读取失败');
    } finally {
      setLoading(false);
    }
  }, [slot]);

  useEffect(() => {
    void load();
  }, [load]);

  const pendingProposals = useMemo(
    () => proposals.filter((item) => {
      const status = String(item.status || 'proposal');
      return status !== 'confirmed' && status !== 'rejected';
    }),
    [proposals],
  );
  const freezeDatasetId = freezeIdOf(slot, ledger?.latest_freeze);

  const openPicker = async () => {
    if (!config?.labelWorkflowId) {
      message.warning('该场景尚未登记打标模板');
      return;
    }
    try {
      const [current, available] = await Promise.all([
        datasetApi.getCurrentForWorkflow(config.labelWorkflowId).catch(() => ({ data: [] })),
        datasetApi.listAvailable({ slot }).catch(() => ({ data: [] })),
      ]);
      const currentPath = toBackendRelative(String(current?.data?.[0]?.file_path || ''));
      setTemplatePath(currentPath);
      const options = (available?.data || []).map((item) => {
        const value = toBackendRelative(item.file_path);
        return {
          value,
          label: `${item.file_name} · ${item.source}`,
        };
      }).filter((item) => item.value && !isLabelingFixture(item.value));
      setAvailablePaths(options);
      setSelectedPath('');
      setPickerOpen(true);
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err?.message || '读取模板输入失败');
    }
  };

  const handleRunLabelTemplate = async () => {
    if (!config?.labelWorkflowId) {
      message.warning('该场景尚未登记打标模板');
      return;
    }
    const filePath = toBackendRelative(selectedPath);
    if (!filePath) {
      message.warning('请先选择或上传无标签数据集');
      return;
    }
    if (isLabelingFixture(filePath)) {
      message.warning('这是模板占位夹具，请选择或上传真实无标签数据');
      return;
    }
    setRunningLabel(true);
    try {
      const workflow = await enhancedWorkflowApi.loadWorkflow(config.labelWorkflowId);
      const nodes = JSON.parse(JSON.stringify(workflow?.nodes || []));
      let patched = 0;
      for (const node of nodes) {
        const functionId = String(node?.data?.config?.functionId || '');
        if (functionId === 'load_csv' || functionId === 'load_parquet' || functionId === 'load_labeled_dataset') {
          node.data = node.data || {};
          node.data.config = { ...(node.data.config || {}), file_path: filePath };
          patched += 1;
        }
      }
      if (!patched) {
        message.error('打标模板没有 load_csv 节点，无法覆盖输入路径');
        return;
      }
      const { execution_id: executionId } = await pipelineApi.executeAsync(config.labelWorkflowId, {
        slot,
        execution_purpose: 'product_workflow',
        live_nodes: nodes,
      });
      message.info(`打标模板已启动：${executionId}`);
      setLastExecutionId(executionId);
      setPickerOpen(false);
      setCurrentStep(1);
      const result = await pollExecution(config.labelWorkflowId, executionId);
      if (result?.status !== 'success') {
        message.error(`打标结束：${result?.status || 'unknown'}`);
        return;
      }
      message.success('提案已产出，请审核簇后再写入累计');
      setCurrentStep(2);
      await load();
      onChanged?.();
    } catch (err: any) {
      message.error(err?.response?.data?.detail?.message || err?.message || '打标失败');
    } finally {
      setRunningLabel(false);
    }
  };

  const proposalColumns = [
    { title: '提案 ID', dataIndex: 'proposal_id', key: 'proposal_id', ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value: string) => (
        <Tag color={value === 'confirmed' ? 'success' : value === 'rejected' ? 'default' : 'gold'}>{value || 'proposal'}</Tag>
      ),
    },
    {
      title: '簇 / 建议',
      key: 'clusters',
      render: (_: unknown, record: ProposalRow) => (
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          {Object.entries(record.clusters || {}).map(([cid, cluster]) => (
            <Space key={`${record.proposal_id}-${cid}`} wrap size={4}>
              <Text>簇 {cid} · {cluster.proposed_label_name || `cluster_${cid}`}</Text>
              {(cluster.suggested_label_names || []).slice(0, 3).map((name) => (
                <Tag key={name}>可能：{name}</Tag>
              ))}
            </Space>
          ))}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: unknown, record: ProposalRow) => (
        <Button
          size="small"
          type="primary"
          disabled={record.status === 'confirmed' || record.status === 'rejected'}
          data-testid={`review-proposal-${record.proposal_id}`}
          onClick={() => {
            setReviewProposalId(record.proposal_id);
            setCurrentStep(2);
          }}
        >
          审核提案
        </Button>
      ),
    },
  ];

  return (
    <Card
      size="small"
      data-testid="slot-story-loop"
      title={
        <Space>
          <ExperimentOutlined />
          <span>无标签打标</span>
          <Tag>{slot}</Tag>
        </Space>
      }
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>}
    >
      <Steps
        size="small"
        current={currentStep}
        onChange={setCurrentStep}
        style={{ marginBottom: 16 }}
        items={[
          { title: '选数据' },
          { title: '执行打标', description: lastExecutionId || config?.labelWorkflowId },
          { title: '审核簇' },
          { title: '写入累计' },
        ]}
      />
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="打标作用在哪份数据？"
        description={(
          <span>
            点执行后先选/上传无标签数据集，再跑打标模板 A（{config?.labelWorkflowId || '未登记'}）。
            不会读取精度运营滚动检测，也不会改累计冻结集。确认提案只写入本场景账本，训练时再冻结。
          </span>
        )}
      />

      <Space wrap style={{ marginBottom: 12 }}>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          data-testid="run-label-template"
          onClick={() => void openPicker()}
        >
          对无标签数据执行打标
        </Button>
        {config?.labelWorkflowId ? (
          <Link to={`/algorithm-dev/workflow-editor/${config.labelWorkflowId}?slot=${slot}`}>
            <Button size="small">打开打标画布（改聚类参数）</Button>
          </Link>
        ) : null}
        <Link to={`/datasets/cumulative-training?slot=${slot}`}>
          <Button size="small">去本场景累计训练数据集</Button>
        </Link>
      </Space>

      <Descriptions size="small" bordered column={2} style={{ marginBottom: 12 }}>
        <Descriptions.Item label="待确认提案">{pendingProposals.length}</Descriptions.Item>
        <Descriptions.Item label="已写入累计">{ledger?.event_count ?? 0} 条</Descriptions.Item>
        <Descriptions.Item label="当前训练快照" span={2}>
          {freezeDatasetId || '尚无训练快照。确认提案只记账，到累计页冻结后再训练。'}
        </Descriptions.Item>
      </Descriptions>

      <Card size="small" type="inner" title="待审核提案">
        {proposals.length === 0 ? (
          <Alert type="info" showIcon message="还没有提案。选择无标签数据后执行打标。" />
        ) : (
          <Table
            size="small"
            rowKey="proposal_id"
            loading={loading}
            columns={proposalColumns}
            dataSource={proposals}
            pagination={{ pageSize: 5 }}
          />
        )}
        <Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0, maxWidth: '72ch' }}>
          未确认的提案不会进入训练集。确认后到本场景「累计训练数据集」查看入库流水。
        </Paragraph>
      </Card>

      <Modal
        title={`选择无标签数据 · ${slot}`}
        open={pickerOpen}
        onCancel={() => setPickerOpen(false)}
        okText="用这份数据执行打标"
        confirmLoading={runningLabel}
        okButtonProps={{ disabled: !selectedPath.trim() }}
        onOk={() => void handleRunLabelTemplate()}
        destroyOnClose
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="warning"
            showIcon
            message="不会默认使用模板夹具"
            description={(
              <span>
                模板 A 磁盘占位路径：<Text code>{templatePath || '未配置'}</Text>
                。请从下面选择场景数据、已有文件，或上传 CSV。本次执行只覆盖 load 节点，不改模板 JSON。
              </span>
            )}
          />
          <Select
            showSearch
            style={{ width: '100%' }}
            placeholder="从已有数据集选择"
            value={selectedPath || undefined}
            options={availablePaths}
            onChange={setSelectedPath}
            filterOption={(input, option) =>
              String(option?.label || '').toLowerCase().includes(input.toLowerCase())
              || String(option?.value || '').toLowerCase().includes(input.toLowerCase())
            }
          />
          <Upload
            accept=".csv,.tsv"
            maxCount={1}
            showUploadList={false}
            customRequest={async (options) => {
              const file = options.file as File;
              try {
                const uploaded = await datasetApi.upload(file);
                const ext = file.name.includes('.') ? file.name.slice(file.name.lastIndexOf('.')) : '.csv';
                const rel = `data/uploads/${uploaded.file_id}${ext}`;
                setSelectedPath(rel);
                setAvailablePaths((prev) => [{ value: rel, label: `${file.name} · 刚上传` }, ...prev]);
                message.success(`已上传：${rel}`);
                options.onSuccess?.(uploaded);
              } catch (err: any) {
                message.error(err?.response?.data?.detail || err?.message || '上传失败');
                options.onError?.(err);
              }
            }}
          >
            <Button icon={<UploadOutlined />}>上传 CSV</Button>
          </Upload>
          <Input
            value={selectedPath}
            onChange={(event) => setSelectedPath(event.target.value)}
            placeholder="或粘贴相对路径，例如 data/uploads/xxx.csv"
          />
        </Space>
      </Modal>
      <SlotLabelProposalReviewPanel
        slot={slot}
        proposalId={reviewProposalId}
        open={Boolean(reviewProposalId)}
        onClose={() => setReviewProposalId(null)}
        onChanged={() => {
          setCurrentStep(3);
          void load();
          onChanged?.();
        }}
      />
    </Card>
  );
};

export default SlotStoryLoopPanel;
