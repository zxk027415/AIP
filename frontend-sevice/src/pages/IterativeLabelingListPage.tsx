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
 * 保持 MainLayout 壳子不变；只使用 pv_fault 正式槽位。
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
  type CumulativeRetrainRunResponse,
} from '../services/iterativeLabelingApi';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;
const PV_FAULT_SLOT = 'pv_fault';

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

const formatTimestamp = (value: unknown): string => {
  const raw = String(value ?? '').trim();
  if (!raw) return '—';
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? raw : date.toLocaleString('zh-CN', { hour12: false });
};

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
  const [activeTab, setActiveTab] = useState<string>('admission');

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
      const [state, response] = await Promise.all([
        cumulativeTrainingApi.getState(PV_FAULT_SLOT),
        fetch(`/api/iterative-labeling/review-sessions?slot=${encodeURIComponent(PV_FAULT_SLOT)}`),
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
  }, []);

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

  const runQueuedRetrain = useCallback(async () => {
    const requestId = String(latestRequest?.request_id ?? '').trim();
    if (!requestId || latestRequest?.status !== 'queued') return;
    setRetrainRunning(true);
    try {
      const result: CumulativeRetrainRunResponse = await cumulativeTrainingApi.runRetrainRequest(requestId, PV_FAULT_SLOT);
      message.success(`重训完成，模型 ${textOrDash((result.trainResult as any)?.model_ref)}（未自动发布）`);
      await loadDashboard();
    } catch (error: unknown) {
      message.error(`重训失败：${error instanceof Error ? error.message : String(error)}`);
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

  const sessionColumns = [
    { title: '会话 ID', dataIndex: 'review_id', key: 'review_id', render: (v: string) => <Text code style={{ fontSize: 12 }}>{v}</Text> },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100,
      render: (v: string) => v === 'reviewed' ? <Tag color="success" icon={<CheckCircleOutlined />}>已完成</Tag> : <Tag color="processing" icon={<EditOutlined />}>审核中</Tag>,
    },
    {
      title: '进度', key: 'progress', width: 180,
      render: (_: unknown, r: ReviewSessionSummary) => <Progress percent={r.total_count > 0 ? Math.round((r.reviewed_count / r.total_count) * 100) : 0} size="small" format={() => `${r.reviewed_count}/${r.total_count}`} />,
    },
    { title: '预测批次', dataIndex: 'prediction_batch_id', key: 'batch', render: (v: string) => <Text code style={{ fontSize: 11 }}>{textOrDash(v)}</Text> },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, r: ReviewSessionSummary) => (
        <Button size="small" type="primary" onClick={() => navigate(`/iterative-labeling/review?review_id=${encodeURIComponent(r.review_id)}&slot=${PV_FAULT_SLOT}`)}>
          {r.status === 'reviewed' ? '查看' : '继续审核'}
        </Button>
      ),
    },
  ];

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div style={{ padding: '20px 24px', maxWidth: 1400, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Space size={12}>
          <ThunderboltOutlined style={{ fontSize: 22, color: '#1677ff' }} />
          <Title level={3} style={{ margin: 0 }}>光伏故障诊断</Title>
          <Tag color="blue">{PV_FAULT_SLOT}</Tag>
        </Space>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => { void loadDashboard(); void loadCandidates(1); }} loading={loading}>
            刷新
          </Button>
        </Space>
      </div>

      {/* KPI Strip */}
      <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
        <Col xs={12} sm={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic title="有效真值" value={cumulativeState?.effective_labeled_unit_count ?? 0} suffix="单元" valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic title="距下次快照" value={cumulativeState?.next_retrain_in ?? 0} suffix="次变更" valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic title="当前模型" value={completedModelRef ? '已就绪' : '待训练'} valueStyle={{ fontSize: 16, color: completedModelRef ? '#52c41a' : '#faad14' }} />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Statistic title="审核会话" value={sessions.length} suffix="个" valueStyle={{ fontSize: 20 }} />
          </Card>
        </Col>
      </Row>

      {/* Main Tabs */}
      <Card bordered={false} bodyStyle={{ padding: '8px 0 0' }}>
        <Tabs activeKey={activeTab} onChange={setActiveTab} style={{ padding: '0 16px' }}>
          <TabPane tab={<Space size={4}><DatabaseOutlined />数据准入</Space>} key="admission" />
          <TabPane tab={<Space size={4}><ClusterOutlined />聚类标注</Space>} key="clustering" />
          <TabPane tab={<Space size={4}><SafetyCertificateOutlined />累计训练</Space>} key="training" />
          <TabPane tab={<Space size={4}><EditOutlined />审核队列</Space>} key="review" />
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
                  <Badge count={candidatesTotal} overflowCount={9999} style={{ backgroundColor: '#1677ff' }}>
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
              <div style={{ marginBottom: 12 }}>
                <Text type="secondary">定时预测任务产生的预测批次会自动创建审核会话，在此跳转到打标界面。</Text>
              </div>
              {sessions.length === 0 ? (
                <Empty description="暂无审核会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
              ) : (
                <Table
                  dataSource={sessions}
                  columns={sessionColumns}
                  rowKey="review_id"
                  size="small"
                  pagination={{ pageSize: 10 }}
                />
              )}
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};

export default IterativeLabelingListPage;
// @AI_GENERATED: end
