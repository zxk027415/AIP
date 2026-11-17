// @AI_GENERATED: pv_fault closed-loop control surface with data admission, clustering, and cumulative training
/**
 * IterativeLabelingListPage.tsx — 光伏故障诊断闭环入口
 *
 * 故事线：
 *   1. 数据准入 — 从数据库拉取候选样本，审查后一键加入累计训练集
 *   2. 聚类标注 — 对无真值数据聚类，人工命名后二次确认入账
 *   3. 累计训练 — 展示训练状态、冻结快照、重训请求
 *   4. 审核会话 — 展示定时预测产生的待审核批次
 *
 * 保持 MainLayout 壳子不变；只使用 pv_fault 正式场景。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Pagination,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  ClusterOutlined,
  DatabaseOutlined,
  EditOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  ImportOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  ScissorOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import {
  cumulativeTrainingApi,
  trainingWorkspaceApi,
} from '../services/iterativeLabelingApi';
// @AI_GENERATED: 后端时间戳为不带时区的 UTC 裸字符串，需归一化后再转本地
import { formatBackendDateTime } from '../utils/datetime';
// @AI_GENERATED: end
import PvFaultWorkspaceShell from '../components/pv-fault/PvFaultWorkspaceShell';
// @AI_GENERATED
import ModelCompareTab from '../components/pv-fault/ModelCompareTab';
// @AI_GENERATED
import ModelPathManager from '../components/pv-fault/ModelPathManager';
// @AI_GENERATED: end
import SlotStoryLoopPanel from '../components/slot/SlotStoryLoopPanel';
import SlotManualReviewQueuePanel, { type ManualReviewSlot } from '../components/slot/SlotManualReviewQueuePanel';
import {
  PV_PRODUCT_SLOT_SELECT_OPTIONS,
  isPvProductSlot,
  type PvProductSlot,
} from '../config/slotProductConfig';
// @AI_GENERATED: end
import { PV_FAULT_PRIMARY } from '../theme/pvFaultTheme';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;
const PV_FAULT_SLOT = 'pv_fault';

// @AI_GENERATED: 人工审核场景补齐第三槽 pv_tsc（MultiRocket 设备日诊断）。
const MANUAL_REVIEW_SLOT_OPTIONS: { label: string; value: ManualReviewSlot }[] = [
  { label: '点路径 pv_point', value: 'pv_point' },
  { label: '天路径 pv_day', value: 'pv_day' },
  { label: '时序分类 pv_tsc', value: 'pv_tsc' },
];
// @AI_GENERATED: end

function parseManualReviewSlot(raw: string | null): ManualReviewSlot {
  if (raw === 'pv_day' || raw === 'pv_point' || raw === 'pv_tsc') return raw;
  return 'pv_point';
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ReviewSessionSummary {
  review_id: string;
  status: string;
  reviewed_count: number;
  total_count: number;
  loop_id: string;
  prediction_batch_id: string;
}

interface CumulativeSnapshot {
  snapshot_id?: string;
  dataset_path?: string;
  sample_count?: number;
  label_count?: number;
  created_at?: string;
}

interface RetrainRequest {
  request_id?: string;
  status?: string;
  snapshot_id?: string;
  dataset_path?: string;
  sample_count?: number;
  label_count?: number;
  model_ref?: string;
  created_at?: string;
  finished_at?: string;
}

interface CumulativeTrainingState {
  slot?: string;
  effective_labeled_unit_count?: number;
  labeled_import_count?: number;
  pending_change_count?: number;
  retrain_label_threshold?: number;
  next_retrain_in?: number;
  retrain_blocker?: string | null;
  latest_snapshot?: CumulativeSnapshot | null;
  latest_retrain_request?: RetrainRequest | null;
  latest_completed_model_ref?: string | null;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const textOrDash = (value: unknown): string => {
  const normalized = String(value ?? '').trim();
  return normalized || '—';
};

// @AI_GENERATED: 同 AlgorithmDeploymentPage —— 后端时间戳是不带时区的 UTC 裸字符串，
// 直接 new Date 会少 8 小时（UTC+8）。统一走 formatBackendDateTime。
const formatTimestamp = (value: unknown): string => formatBackendDateTime(value);
// @AI_GENERATED: end

const retrainStatusTag = (status?: string) => {
  switch (status) {
    case 'completed': return <Tag color="success">已完成</Tag>;
    case 'queued': return <Tag color="processing">等待执行</Tag>;
    case 'running': return <Tag color="processing">训练中</Tag>;
    case 'failed': return <Tag color="error">失败</Tag>;
    default: return <Tag>未创建</Tag>;
  }
};

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

const IterativeLabelingListPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const workflowSlotParam = searchParams.get('slot')?.trim() || 'pv_point';
  const workflowSlot: PvProductSlot = isPvProductSlot(workflowSlotParam) ? workflowSlotParam : 'pv_point';
  const reviewSlot = parseManualReviewSlot(searchParams.get('review_slot'));
  const [workflowRefreshKey, setWorkflowRefreshKey] = useState(0);
  const [reviewRefreshKey, setReviewRefreshKey] = useState(0);
  const [activeTab, setActiveTab] = useState<string>(() => {
    const tab = searchParams.get('tab');
    if (tab === 'workflow_slot') return 'pv_label';
    if (tab) return tab;
    return isPvProductSlot(workflowSlotParam) ? 'pv_label' : 'review';
  });

  // --- Cumulative Training State ---
  const [cumulativeState, setCumulativeState] = useState<CumulativeTrainingState | null>(null);
  const [sessions, setSessions] = useState<ReviewSessionSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [retrainRunning, setRetrainRunning] = useState(false);

  // --- Candidates State ---
  const [candidates, setCandidates] = useState<Array<Record<string, unknown>>>([]);
  const [candidatesTotal, setCandidatesTotal] = useState(0);
  const [candidatesPage, setCandidatesPage] = useState(1);
  const [candidatesPageSize] = useState(50);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [labelStatusFilter, setLabelStatusFilter] = useState<string>('unlabeled');

  // --- Clustering State ---
  const [clusteringLoading, setClusteringLoading] = useState(false);
  const [clusteringRunId, setClusteringRunId] = useState<string | null>(null);
  const [clusteringRun, setClusteringRun] = useState<Record<string, any> | null>(null);

  // ---------------------------------------------------------------------------
  // Data Loading
  // ---------------------------------------------------------------------------

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    try {
      const slotForKpi = activeTab === 'review' ? reviewSlot : workflowSlot;
      const [state, response] = await Promise.all([
        cumulativeTrainingApi.getState(slotForKpi),
        fetch(`/api/iterative-labeling/review-sessions?slot=${encodeURIComponent(slotForKpi)}`),
      ]);
      if (!response.ok) throw new Error('加载审核会话失败');
      const sessionPayload = await response.json();
      setCumulativeState(state as CumulativeTrainingState);
      setSessions(Array.isArray(sessionPayload.sessions) ? sessionPayload.sessions : []);
    } catch (error: unknown) {
      message.error(`加载状态失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setLoading(false);
    }
  }, [activeTab, reviewSlot]);

  const loadCandidates = useCallback(async (page = 1) => {
    setCandidatesLoading(true);
    try {
      const result = await trainingWorkspaceApi.getTrainingCandidates({
        page,
        page_size: candidatesPageSize,
        label_status: labelStatusFilter || undefined,
      });
      setCandidates(result.items ?? []);
      setCandidatesTotal(result.total ?? 0);
      setCandidatesPage(result.page ?? 1);
    } catch (error: any) {
      if (error?.response?.status === 503) {
        setCandidates([]);
        setCandidatesTotal(0);
      } else {
        message.error('加载候选数据失败');
      }
    } finally {
      setCandidatesLoading(false);
    }
  }, [candidatesPageSize, labelStatusFilter]);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);
  useEffect(() => { if (activeTab === 'admission') void loadCandidates(1); }, [activeTab, loadCandidates]);

  // ---------------------------------------------------------------------------
  // Actions
  // ---------------------------------------------------------------------------

  const latestRequest = cumulativeState?.latest_retrain_request ?? null;
  const completedModelRef = cumulativeState?.latest_completed_model_ref ?? null;
  const reviewStats = useMemo(() => {
    const completed = sessions.filter((session) => session.status === 'reviewed').length;
    const reviewedUnits = sessions.reduce((sum, session) => sum + Number(session.reviewed_count || 0), 0);
    const totalUnits = sessions.reduce((sum, session) => sum + Number(session.total_count || 0), 0);
    return { completed, inProgress: sessions.length - completed, reviewedUnits, totalUnits };
  }, [sessions]);

  const runQueuedRetrain = useCallback(async () => {
    const requestId = String(latestRequest?.request_id ?? '').trim();
    if (!requestId || latestRequest?.status !== 'queued') return;
    setRetrainRunning(true);
    try {
      // @AI_GENERATED: 改后台执行。训练评估耗时远超 axios 的 120s 超时，
      // 原同步等待会在浏览器侧中断并误报「重训失败」，而后端其实仍在跑。
      // 本页只做看板、不轮询进度，进度请到「算法部署」页查看。
      await cumulativeTrainingApi.runRetrainRequest(requestId, PV_FAULT_SLOT, true);
      message.success('已在后台启动重训，进度可在「算法部署」页查看');
      // @AI_GENERATED: end
      await loadDashboard();
    } catch (error: unknown) {
      const detail = (error as any)?.response?.data?.detail;
      message.error(`启动重训失败：${detail ?? (error instanceof Error ? error.message : String(error))}`);
    } finally {
      setRetrainRunning(false);
    }
  }, [latestRequest, loadDashboard]);

  const handleCreateClustering = async () => {
    setClusteringLoading(true);
    try {
      const result = await trainingWorkspaceApi.createClusteringRun({
        n_clusters: 5,
        label_status: 'unlabeled',
        page_size: 500,
      });
      const runId = (result as any).run_id;
      setClusteringRunId(runId);
      setClusteringRun(result as Record<string, any>);
      message.success(`聚类运行已创建：${runId}`);
      setActiveTab('clustering');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '创建聚类失败');
    } finally {
      setClusteringLoading(false);
    }
  };

  const handleConfirmClustering = async () => {
    if (!clusteringRunId) return;
    setClusteringLoading(true);
    try {
      await trainingWorkspaceApi.confirmClusteringRun(clusteringRunId);
      message.success('聚类确认成功，已登记到累计训练集');
      setClusteringRun(null);
      setClusteringRunId(null);
      await loadDashboard();
      setActiveTab('training');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '确认失败');
    } finally {
      setClusteringLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Columns
  // ---------------------------------------------------------------------------

  const candidateColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 70 },
    { title: '时间', dataIndex: 'time', key: 'time', width: 160, render: (v: any) => formatTimestamp(v) },
    { title: '站点', dataIndex: 'site_id', key: 'site_id', width: 100, ellipsis: true },
    { title: '设备', dataIndex: 'device_id', key: 'device_id', width: 160, ellipsis: true },
    { title: '支路', dataIndex: 'branch_id', key: 'branch_id', width: 100 },
    { title: '电流值', dataIndex: 'value', key: 'value', width: 90, render: (v: any) => v != null ? Number(v).toFixed(2) : '—' },
    { title: '理论电流', dataIndex: 'i_cal', key: 'i_cal', width: 90, render: (v: any) => v != null ? Number(v).toFixed(2) : '—' },
    {
      title: '标签', dataIndex: 'label', key: 'label', width: 80,
      render: (v: any) => v != null && v >= 0 ? <Tag color="blue">label_{v}</Tag> : <Tag>未标注</Tag>,
    },
  ];

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <PvFaultWorkspaceShell className="pv-page-shell">
      {/* Header */}
      <div className="pv-page-header">
        <Space size={12}>
          <ThunderboltOutlined className="pv-accent-icon" style={{ fontSize: 22, color: PV_FAULT_PRIMARY }} />
          <Title level={3} className="pv-page-header-title">人工标注审核</Title>
          <Tag color={activeTab === 'pv_label' ? 'blue' : 'orange'}>
            {activeTab === 'pv_label' ? workflowSlot : reviewSlot}
          </Tag>
        </Space>
        <Space>
          <Button icon={<DatabaseOutlined />} onClick={() => navigate('/datasets?tab=private')}>
            累计训练集扩充
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => { void loadDashboard(); }} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      {/* KPI Strip：旧 pv_fault 队列，不和天/点路径打标混在一起 */}
      {activeTab !== 'pv_label' && (
      <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
        <Col xs={12} sm={6}>
          <Card size="small" className="pv-kpi-card">
            <Statistic title="待处理会话" value={reviewStats.inProgress} suffix="个" valueStyle={{ fontSize: 22, fontWeight: 600, color: reviewStats.inProgress > 0 ? PV_FAULT_PRIMARY : undefined }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className="pv-kpi-card">
            <Statistic title="已完成会话" value={reviewStats.completed} suffix="个" valueStyle={{ fontSize: 22, fontWeight: 600 }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className="pv-kpi-card">
            <Statistic title="已标注单元" value={reviewStats.reviewedUnits} suffix="个" valueStyle={{ fontSize: 22, fontWeight: 600 }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" className="pv-kpi-card">
            <Statistic title="标注总进度" value={reviewStats.totalUnits > 0 ? Math.round((reviewStats.reviewedUnits / reviewStats.totalUnits) * 100) : 0} suffix="%" valueStyle={{ fontSize: 22, fontWeight: 600, color: PV_FAULT_PRIMARY }} />
          </Card>
        </Col>
      </Row>
      )}

      {/* Main Tabs */}
      <Card bordered={false} bodyStyle={{ padding: '8px 0 0' }}>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => {
            const nextKey = key === 'workflow_slot' ? 'pv_label' : key;
            setActiveTab(nextKey);
            const next = new URLSearchParams(searchParams);
            next.set('tab', nextKey);
            setSearchParams(next, { replace: true });
          }}
          style={{ padding: '0 16px' }}
        >
          <TabPane tab={<Space size={4}><EditOutlined />人工打标队列</Space>} key="review" />
          <TabPane tab={<Space size={4}><ExperimentOutlined />模型对比</Space>} key="model_compare" />
          <TabPane tab={<Space size={4}><SafetyCertificateOutlined />天/点路径打标</Space>} key="pv_label" />
          {/* @AI_GENERATED */}
          <TabPane tab={<Space size={4}><ScissorOutlined />TSC 时序分类</Space>} key="tsc" />
          {/* @AI_GENERATED: end */}
        </Tabs>

        <div style={{ padding: '16px' }}>
          {/* ─── Tab: 数据准入 ─── */}
          {activeTab === 'admission' && (
            <div>
              <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space>
                  <Text strong>候选训练样本</Text>
                  <Select
                    value={labelStatusFilter}
                    onChange={(v) => { setLabelStatusFilter(v); }}
                    style={{ width: 140 }}
                    size="small"
                    options={[
                      { label: '未标注', value: 'unlabeled' },
                      { label: '已标注', value: 'labeled' },
                      { label: '全部', value: '' },
                    ]}
                  />
                  <Button size="small" onClick={() => void loadCandidates(1)} loading={candidatesLoading}>查询</Button>
                </Space>
                <Space>
                  <Badge count={candidatesTotal} overflowCount={9999} style={{ backgroundColor: PV_FAULT_PRIMARY }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>总记录</Text>
                  </Badge>
                  <Tooltip title="从未标注样本创建聚类 run，然后人工命名后确认入训练集">
                    <Button type="primary" icon={<ClusterOutlined />} onClick={handleCreateClustering} loading={clusteringLoading}>
                      聚类并标注
                    </Button>
                  </Tooltip>
                </Space>
              </div>

              <Table
                dataSource={candidates}
                columns={candidateColumns}
                rowKey="id"
                size="small"
                loading={candidatesLoading}
                pagination={false}
                scroll={{ x: 900, y: 400 }}
                locale={{ emptyText: candidatesLoading ? '加载中' : '暂无候选数据（数据库未连接或无记录）' }}
              />
              {candidatesTotal > candidatesPageSize && (
                <div style={{ marginTop: 12, textAlign: 'right' }}>
                  <Pagination
                    current={candidatesPage}
                    pageSize={candidatesPageSize}
                    total={candidatesTotal}
                    size="small"
                    showSizeChanger={false}
                    onChange={(p) => void loadCandidates(p)}
                  />
                </div>
              )}

              <Divider style={{ margin: '16px 0 12px' }} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                数据来源：数据库 training_samples 表 | 定时调度任务每日拉取新观测 | 标注状态来自 label 列
              </Text>
            </div>
          )}

          {/* ─── Tab: 聚类标注 ─── */}
          {activeTab === 'clustering' && (
            <div>
              {!clusteringRun ? (
                <Empty
                  description="暂无聚类运行"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                >
                  <Button type="primary" icon={<ClusterOutlined />} onClick={handleCreateClustering} loading={clusteringLoading}>
                    从未标注数据创建聚类
                  </Button>
                </Empty>
              ) : (
                <div>
                  <Alert
                    type="info"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message={`聚类 run: ${clusteringRun.run_id} | 状态: ${clusteringRun.status} | 共 ${clusteringRun.total_members} 个诊断片段`}
                  />

                  <Row gutter={[12, 12]}>
                    {Object.entries(clusteringRun.clusters || {}).map(([cid, cluster]: [string, any]) => (
                      <Col xs={24} sm={12} lg={8} key={cid}>
                        <Card
                          size="small"
                          title={<Space><Tag color="geekblue">簇 {cid}</Tag><Text>{cluster.member_count} 个成员</Text></Space>}
                          style={{ height: '100%' }}
                          extra={cluster.proposed_label_name ? <Tag color="success">{cluster.proposed_label_name}</Tag> : <Tag color="warning">待命名</Tag>}
                        >
                          <div style={{ marginBottom: 8 }}>
                            <Input
                              size="small"
                              placeholder="输入标签名称（如：组串遮挡）"
                              defaultValue={cluster.proposed_label_name || ''}
                              onBlur={async (e) => {
                                const name = e.target.value.trim();
                                if (!name || !clusteringRunId) return;
                                try {
                                  const updated = await trainingWorkspaceApi.updateCluster(clusteringRunId, cid, { proposed_label_name: name });
                                  setClusteringRun(updated as Record<string, any>);
                                } catch (err: any) {
                                  message.error(err?.response?.data?.detail || '命名失败');
                                }
                              }}
                              addonBefore="标签"
                            />
                          </div>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            成员示例：{(cluster.member_keys || []).slice(0, 3).join(', ')}
                            {(cluster.member_keys || []).length > 3 ? '...' : ''}
                          </Text>
                        </Card>
                      </Col>
                    ))}
                  </Row>

                  <div style={{ marginTop: 16, textAlign: 'right' }}>
                    <Space>
                      <Button onClick={() => { setClusteringRun(null); setClusteringRunId(null); }}>取消</Button>
                      <Button
                        type="primary"
                        icon={<CheckCircleOutlined />}
                        loading={clusteringLoading}
                        onClick={() => {
                          Modal.confirm({
                            title: '确认纳入累计训练集？',
                            content: '确认后将生成不可变的标注数据集并登记到累计训练集。所有簇必须已命名。',
                            okText: '确认纳入',
                            onOk: handleConfirmClustering,
                          });
                        }}
                      >
                        确认纳入训练集
                      </Button>
                    </Space>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ─── Tab: 累计训练 ─── */}
          {activeTab === 'training' && (
            <div>
              <Row gutter={[16, 16]}>
                <Col xs={24} lg={12}>
                  <Card size="small" title="累计训练状态">
                    <Descriptions column={1} size="small" labelStyle={{ width: 130, color: '#64748b', fontSize: 12 }}>
                      <Descriptions.Item label="有效真值单元">{cumulativeState?.effective_labeled_unit_count ?? 0}</Descriptions.Item>
                      <Descriptions.Item label="带标签导入">{cumulativeState?.labeled_import_count ?? 0} 份</Descriptions.Item>
                      <Descriptions.Item label="待计入变更">{cumulativeState?.pending_change_count ?? 0}</Descriptions.Item>
                      <Descriptions.Item label="重训阈值">{cumulativeState?.retrain_label_threshold ?? 20}</Descriptions.Item>
                      <Descriptions.Item label="距下次重训">{cumulativeState?.next_retrain_in ?? 0} 次变更</Descriptions.Item>
                      <Descriptions.Item label="当前模型">
                        {completedModelRef ? <Text code copyable>{completedModelRef}</Text> : <Text type="secondary">暂无</Text>}
                      </Descriptions.Item>
                    </Descriptions>
                    {cumulativeState?.retrain_blocker && (
                      <Alert type="warning" showIcon style={{ marginTop: 8 }} message={cumulativeState.retrain_blocker} />
                    )}
                  </Card>
                </Col>
                <Col xs={24} lg={12}>
                  <Card
                    size="small"
                    title="重训请求"
                    extra={latestRequest?.status === 'queued' ? (
                      <Button type="primary" size="small" icon={<PlayCircleOutlined />} loading={retrainRunning} onClick={runQueuedRetrain}>
                        执行重训
                      </Button>
                    ) : null}
                  >
                    <Descriptions column={1} size="small" labelStyle={{ width: 120, color: '#64748b', fontSize: 12 }}>
                      <Descriptions.Item label="请求 ID"><Text code style={{ fontSize: 11 }}>{textOrDash(latestRequest?.request_id)}</Text></Descriptions.Item>
                      <Descriptions.Item label="状态">{retrainStatusTag(latestRequest?.status)}</Descriptions.Item>
                      <Descriptions.Item label="快照样本数">{textOrDash(latestRequest?.sample_count)}</Descriptions.Item>
                      <Descriptions.Item label="标签类别数">{textOrDash(latestRequest?.label_count)}</Descriptions.Item>
                      <Descriptions.Item label="完成时间">{formatTimestamp(latestRequest?.finished_at)}</Descriptions.Item>
                    </Descriptions>
                  </Card>
                </Col>
              </Row>
            </div>
          )}

          {/* ─── Tab: 审核队列 ─── */}
          {activeTab === 'review' && (
            <div>
              <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space wrap>
                  <Text strong>审核场景</Text>
                  <Select<ManualReviewSlot>
                    value={reviewSlot}
                    style={{ width: 220 }}
                    options={MANUAL_REVIEW_SLOT_OPTIONS}
                    onChange={(value) => {
                      const next = new URLSearchParams(searchParams);
                      next.set('review_slot', value);
                      next.set('tab', 'review');
                      setSearchParams(next, { replace: true });
                    }}
                  />
                  <Button icon={<ReloadOutlined />} onClick={() => setReviewRefreshKey((k) => k + 1)}>
                    刷新
                  </Button>
                </Space>
              </div>
              <SlotManualReviewQueuePanel
                key={`${reviewSlot}-${reviewRefreshKey}`}
                slot={reviewSlot}
                onChanged={() => {
                  void loadDashboard();
                  setReviewRefreshKey((k) => k + 1);
                }}
              />
            </div>
          )}

          {/* @AI_GENERATED: TSC 模型对比 Tab */}
          {activeTab === 'model_compare' && (
            <ModelCompareTab slot={PV_FAULT_SLOT} />
          )}

          {activeTab === 'pv_label' && (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Alert
                type="info"
                showIcon
                message="把无标签数据变成可训练样本"
                description="先选场景，再选择或上传无标签数据后执行打标。确认提案写入该场景累计账本；训练快照在对应累计页按时间冻结。"
              />
              <Space wrap>
                <Text>场景</Text>
                <Select<PvProductSlot>
                  value={workflowSlot}
                  style={{ width: 260 }}
                  options={PV_PRODUCT_SLOT_SELECT_OPTIONS}
                  onChange={(value) => {
                    const next = new URLSearchParams(searchParams);
                    next.set('slot', value);
                    next.set('tab', 'pv_label');
                    setSearchParams(next, { replace: true });
                  }}
                />
                <Button icon={<ReloadOutlined />} onClick={() => setWorkflowRefreshKey((k) => k + 1)}>
                  刷新
                </Button>
              </Space>
              <SlotStoryLoopPanel
                key={`${workflowSlot}-${workflowRefreshKey}`}
                slot={workflowSlot}
                onChanged={() => setWorkflowRefreshKey((k) => k + 1)}
              />
            </Space>
          )}
          {/* @AI_GENERATED: end */}

          {/* @AI_GENERATED: TSC 时序分类 Tab 内容区 */}
          {activeTab === 'tsc' && (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              <Alert
                type="info"
                showIcon
                message="TSC 时序分类诊断（MultiRocket）"
                description={
                  <>
                    独立 slot <code>pv_tsc</code>：滑动窗口（window=288, stride=72）切分原始时序 →
                    MultiRocket 多窗口分类 → 多数投票聚合为设备日级别诊断。
                    当前以 Challenger 身份运行，与天路径的 RF 做同口径精度对比。
                  </>
                }
              />

              {/* TSC 模型对比（复用 ModelCompareTab，slot=pv_tsc） */}
              <Card size="small" title="TSC 模型对比实验">
                <ModelCompareTab slot="pv_tsc" />
              </Card>

              {/* TSC 路径模型管理（复用 ModelPathManager，slot=pv_tsc） */}
              <Card size="small" title="TSC 路径模型管理">
                <ModelPathManager slot="pv_tsc" />
              </Card>

              {/* TSC 累计训练快照入口 */}
              <Card size="small" title="TSC 累计训练集">
                <Space>
                  <Text type="secondary">
                    管理 pv_tsc 的累计训练数据、快照和重训请求
                  </Text>
                  <Button
                    type="link"
                    onClick={() => navigate('/datasets/cumulative-training/pv_tsc')}
                  >
                    前往 TSC 累计训练账本 →
                  </Button>
                </Space>
              </Card>

              {/* TSC 检测状态概览 */}
              <Card size="small" title="TSC 检测运行状态">
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Text type="secondary">
                    TSC 定时检测任务状态（cron: 每日 04:00）。
                    首次运行会自动从天路径复制设备列表并初始化游标。
                  </Text>
                  <Alert
                    type="warning"
                    showIcon
                    message="当前 TSC 以 Challenger 身份运行"
                    description="模型尚未 Promote 为 Champion 前，定时检测任务会跳过。请先在上方「TSC 路径模型管理」中注册并 Promote 一个 MultiRocket 模型。"
                  />
                </Space>
              </Card>
            </Space>
          )}
          {/* @AI_GENERATED: end */}
        </div>
      </Card>
    </PvFaultWorkspaceShell>
  );
};

export default IterativeLabelingListPage;
// @AI_GENERATED: end
