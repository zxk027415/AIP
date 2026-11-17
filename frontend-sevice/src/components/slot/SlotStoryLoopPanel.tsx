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
import FeedSourceCard from './FeedSourceCard';
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

  const loadPickerOptions = useCallback(async () => {
    if (!config?.labelWorkflowId) return;
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
    } catch (err: any) {
      message.error(err?.response?.data?.detail || err?.message || '读取模板输入失败');
    }
  }, [config?.labelWorkflowId, slot]);

  useEffect(() => {
    void loadPickerOptions();
  }, [loadPickerOptions]);

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

  const goStep = (next: number) => {
    if (next > currentStep) {
      if (next >= 1 && !selectedPath.trim()) {
        message.warning('请先选择或上传无标签数据');
        return;
      }
      if (next >= 2 && !lastExecutionId && pendingProposals.length === 0) {
        message.warning('请先执行打标');
        return;
      }
      if (next >= 3 && currentStep < 3) {
        message.warning('请先在第 3 步审核簇并确认写入');
        return;
      }
    }
    setCurrentStep(next);
  };

  const pickerBody = (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      <Alert
        type="warning"
        showIcon
        message="不会默认使用模板夹具"
        description={(
          <span>
            模板磁盘占位路径：<Text code>{templatePath || '未配置'}</Text>
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
      <Button type="primary" disabled={!selectedPath.trim()} onClick={() => goStep(1)}>
        下一步：执行打标
      </Button>
    </Space>
  );

  return (
    <Card
      size="small"
      data-testid="slot-story-loop"
      title={
        <Space>
          <ExperimentOutlined />
          <span>无标签打标</span>
          <Tag>{config?.shortLabel || slot}</Tag>
        </Space>
      }
      extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading}>刷新</Button>}
    >
      <FeedSourceCard slot={slot} />
      <Steps
        size="small"
        current={currentStep}
        onChange={goStep}
        style={{ marginBottom: 16, marginTop: 12 }}
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
        message="无标签数据 → 聚类提案 → 审核簇 → 才写入累计"
        description={`当前场景 ${config?.shortLabel || slot}。四步按顺序走：第 3 步才打开审核，第 4 步才确认入库。不会读精度运营滚动检测，也不会立刻换生产模型。`}
      />

      {currentStep === 0 ? pickerBody : null}

      {currentStep === 1 ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Descriptions size="small" bordered column={1}>
            <Descriptions.Item label="已选数据"><Text code>{selectedPath || '尚未选择'}</Text></Descriptions.Item>
            <Descriptions.Item label="打标模板">{config?.labelWorkflowId || '未登记'}</Descriptions.Item>
            <Descriptions.Item label="最近执行">{lastExecutionId || '尚未执行'}</Descriptions.Item>
          </Descriptions>
          <Space wrap>
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              data-testid="run-label-template"
              loading={runningLabel}
              disabled={!selectedPath.trim()}
              onClick={() => void handleRunLabelTemplate()}
            >
              执行打标
            </Button>
            <Button onClick={() => setCurrentStep(0)}>上一步</Button>
            {config?.labelWorkflowId ? (
              <Link to={`/algorithm-dev/workflow-editor/${config.labelWorkflowId}?slot=${slot}`}>
                <Button size="small">打开打标画布（改聚类参数）</Button>
              </Link>
            ) : null}
          </Space>
        </Space>
      ) : null}

      {currentStep === 2 ? (
        <Card size="small" type="inner" title="待审核提案">
          {proposals.length === 0 ? (
            <Alert type="info" showIcon message="还没有提案。请回到上一步执行打标。" />
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
            点「审核提案」看每一簇形态、起业务名、剔除不像的成员。确认写入后才会进入第 4 步。
          </Paragraph>
        </Card>
      ) : null}

      {currentStep === 3 ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="success"
            showIcon
            message="提案已确认写入本场景累计账本"
            description="确认只记账。到累计训练页冻结快照后才能训练；不会立刻换生产模型。"
          />
          <Descriptions size="small" bordered column={2}>
            <Descriptions.Item label="待确认提案">{pendingProposals.length}</Descriptions.Item>
            <Descriptions.Item label="已写入累计">{ledger?.event_count ?? 0} 条</Descriptions.Item>
            <Descriptions.Item label="当前训练快照" span={2}>
              {freezeDatasetId || '尚无训练快照。到累计页冻结后再训练。'}
            </Descriptions.Item>
          </Descriptions>
          <Link to={`/datasets/cumulative-training?slot=${slot}`}>
            <Button type="primary">去本场景累计训练数据集</Button>
          </Link>
        </Space>
      ) : null}

      {currentStep !== 2 && pendingProposals.length > 0 ? (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 16 }}
          message={`还有 ${pendingProposals.length} 份提案待审核簇`}
          description="第 3 步那张表才是审核入口，这里不再重复列出。"
          action={(
            <Button
              size="small"
              type="primary"
              onClick={() => {
                setCurrentStep(2);
                if (pendingProposals.length === 1) {
                  setReviewProposalId(pendingProposals[0].proposal_id);
                }
              }}
            >
              去审核簇
            </Button>
          )}
        />
      ) : null}

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
