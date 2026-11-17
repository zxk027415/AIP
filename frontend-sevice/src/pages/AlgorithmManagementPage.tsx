import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Breadcrumb,
  Button,
  Card,
  Dropdown,
  Empty,
  Input,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  MoreOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import { enhancedWorkflowApi } from '../services/workflowEnhancedApi';
import { industryApi } from '../services/industryApi';
import type { EnhancedWorkflowSummary } from '../types/workflow-enhanced';
import type { IndustryScenario } from '../types/industry';
import CreateWorkflowWizard from '../components/CreateWorkflowWizard';
// @AI_GENERATED: 旅程上下文合同——按规范名（兼容历史别名）解析主干，不把 id 塞进自由搜索框
import { readParam, JOURNEY_PARAM, buildJourneyHref } from '../utils/journeyParams';
// @AI_GENERATED: end

// ─── Types ───────────────────────────────────────────────────────────────────

type WorkflowRecord = EnhancedWorkflowSummary & {
  scenarioId: string;
  scenarioName: string;
  versionTag: string;
  lifecycleStatus: 'draft' | 'ops-ready' | 'deployment-ready';
  autoresearchStatus: 'not-started' | 'candidate' | 'verified';
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Resolve scenario name from scenario_id using loaded scenarios list */
function resolveScenarioName(scenarioId: string | undefined | null, scenarios: IndustryScenario[]): { scenarioId: string; scenarioName: string } {
  if (!scenarioId) return { scenarioId: 'unclassified', scenarioName: '未分类' };
  const matched = scenarios.find((s) => s.id === scenarioId);
  return { scenarioId, scenarioName: matched?.name || scenarioId };
}

/** Extract version display from backend version field or fallback to name regex */
function resolveVersionTag(summary: EnhancedWorkflowSummary): string {
  if (summary.version) return `v${summary.version}`;
  const match = `${summary.id} ${summary.name}`.match(/(?:^|[\s_-])(v\d+(?:\.\d+)*)(?:$|[\s_-])/i);
  return match?.[1]?.toLowerCase() || 'v1';
}

function inferLifecycleStatus(summary: EnhancedWorkflowSummary): WorkflowRecord['lifecycleStatus'] {
  const text = `${summary.id} ${summary.name} ${summary.description || ''}`.toLowerCase();
  if (text.includes('prod') || text.includes('production') || text.includes('deploy')) return 'deployment-ready';
  if (text.includes('ops') || text.includes('operate') || text.includes('运营')) return 'ops-ready';
  return 'draft';
}

function inferAutoresearchStatus(summary: EnhancedWorkflowSummary): WorkflowRecord['autoresearchStatus'] {
  const text = `${summary.id} ${summary.name} ${summary.description || ''}`.toLowerCase();
  if (text.includes('verified') || text.includes('promote') || text.includes('复验')) return 'verified';
  if (text.includes('candidate') || text.includes('challenger') || text.includes('autoresearch')) return 'candidate';
  return 'not-started';
}

// ─── Status renderers (per design spec) ──────────────────────────────────────

const LIFECYCLE_DOT_COLOR: Record<WorkflowRecord['lifecycleStatus'], string> = {
  draft: '#52c41a',
  'ops-ready': '#1677ff',
  'deployment-ready': '#fa8c16',
};
const LIFECYCLE_LABEL: Record<WorkflowRecord['lifecycleStatus'], string> = {
  draft: '开发中',
  'ops-ready': '待运营',
  'deployment-ready': '待部署',
};

const AUTORESEARCH_TAG: Record<WorkflowRecord['autoresearchStatus'], { color: string; label: string }> = {
  'not-started': { color: 'default', label: '未回测' },
  candidate: { color: 'orange', label: '候选中' },
  verified: { color: 'green', label: '已复验' },
};

// ─── Component ───────────────────────────────────────────────────────────────

const AlgorithmManagementPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  // @AI_GENERATED: solution/template id 不再污染自由搜索框；按四层主干规范名解析（别名兼容）
  const [search, setSearch] = useState('');
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>(
    readParam(searchParams, JOURNEY_PARAM.scenarioId) || 'all',
  );
  // 从场景详情带入的 solution_id 作为算法方案过滤上下文（真实过滤 UI 由 10.5 完善）
  const [selectedSolutionId] = useState<string>(readParam(searchParams, JOURNEY_PARAM.solutionId) || 'all');
  // @AI_GENERATED: end
  const [lifecycleFilter, setLifecycleFilter] = useState<string>('all');
  const [records, setRecords] = useState<WorkflowRecord[]>([]);
  const [scenarios, setScenarios] = useState<IndustryScenario[]>([]);
  const [wizardOpen, setWizardOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      enhancedWorkflowApi.listWorkflowSummaries(),
      industryApi.getScenarios().catch(() => [] as IndustryScenario[]),
    ])
      .then(([workflowSummaries, scenarioList]) => {
        if (cancelled) return;
        setScenarios(scenarioList);
        setRecords(
          workflowSummaries.map((summary) => {
            const scenarioInfo = resolveScenarioName(summary.scenario_id, scenarioList);
            return {
              ...summary,
              ...scenarioInfo,
              versionTag: resolveVersionTag(summary),
              lifecycleStatus: inferLifecycleStatus(summary),
              autoresearchStatus: inferAutoresearchStatus(summary),
            };
          }),
        );
      })
      .catch((err) => {
        console.error('load algorithm management records failed', err);
        message.error('算法管理页加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  // ─── Filtering ─────────────────────────────────────────────────────────────

  // @AI_GENERATED: 仅当数据集中确有工作流带 solution_id 时才启用算法方案过滤，避免迁移期误清空
  const anySolutionTagged = useMemo(() => records.some((r) => !!r.solution_id), [records]);
  // @AI_GENERATED: end
  const filteredRecords = useMemo(() => {
    const q = search.trim().toLowerCase();
    return records.filter((r) => {
      if (selectedScenarioId !== 'all' && r.scenarioId !== selectedScenarioId) return false;
      // @AI_GENERATED: solution_id 上下文过滤（守卫见 anySolutionTagged）
      if (anySolutionTagged && selectedSolutionId !== 'all' && r.solution_id !== selectedSolutionId) return false;
      // @AI_GENERATED: end
      if (lifecycleFilter !== 'all' && r.lifecycleStatus !== lifecycleFilter) return false;
      if (q && !`${r.id} ${r.name} ${r.description || ''} ${r.scenarioName}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [records, search, selectedScenarioId, selectedSolutionId, anySolutionTagged, lifecycleFilter]);

  const scenarioOptions = useMemo(() => {
    const counts = new Map<string, { name: string; count: number }>();
    for (const r of records) {
      const cur = counts.get(r.scenarioId);
      if (cur) cur.count += 1;
      else counts.set(r.scenarioId, { name: r.scenarioName, count: 1 });
    }
    return [
      { value: 'all', label: `全部场景` },
      ...Array.from(counts.entries()).map(([id, item]) => ({ value: id, label: item.name })),
    ];
  }, [records]);

  const handleReset = () => {
    setSearch('');
    setSelectedScenarioId('all');
    setLifecycleFilter('all');
  };

  // ─── Stats ─────────────────────────────────────────────────────────────────

  const scenarioCount = new Set(records.map((r) => r.scenarioId)).size;
  const versionCount = new Set(records.map((r) => `${r.scenarioId}:${r.name}:${r.versionTag}`)).size;
  const pendingCount =
    records.filter((r) => r.lifecycleStatus === 'ops-ready').length +
    records.filter((r) => r.lifecycleStatus === 'deployment-ready').length;

  // ─── Table columns (per design spec) ───────────────────────────────────────

  const columns: ColumnsType<WorkflowRecord> = [
    {
      title: '算法资产',
      key: 'workflow',
      width: '35%',
      render: (_, record) => (
        <div style={{ lineHeight: 1.6 }}>
          <div>
            <a
              onClick={() => navigate(`/algorithm-dev/workflow-editor/${record.id}`)}
              style={{ fontWeight: 500, fontSize: 14 }}
            >
              {record.name}
            </a>
            <Tag
              style={{ marginLeft: 8, fontSize: 11, lineHeight: '18px', borderRadius: 10, padding: '0 6px' }}
              color="default"
            >
              {record.versionTag}
            </Tag>
          </div>
          <div style={{ fontSize: 12, color: '#8c8c8c' }}>
            {record.description || '暂无描述'}
          </div>
          <div style={{ fontSize: 12, color: '#8c8c8c', fontFamily: 'monospace' }}>
            ID: {record.id}
          </div>
        </div>
      ),
    },
    {
      title: '所属场景',
      dataIndex: 'scenarioName',
      width: '10%',
      render: (value: string) => <span style={{ fontSize: 13 }}>{value}</span>,
    },
    {
      title: '生命周期',
      dataIndex: 'lifecycleStatus',
      width: '10%',
      render: (value: WorkflowRecord['lifecycleStatus']) => (
        <span style={{ fontSize: 13, whiteSpace: 'nowrap' }}>
          <span
            style={{
              display: 'inline-block',
              width: 6,
              height: 6,
              borderRadius: '50%',
              backgroundColor: LIFECYCLE_DOT_COLOR[value],
              marginRight: 6,
              verticalAlign: 'middle',
            }}
          />
          {LIFECYCLE_LABEL[value]}
        </span>
      ),
    },
    {
      title: '自动化回测',
      dataIndex: 'autoresearchStatus',
      width: '10%',
      render: (value: WorkflowRecord['autoresearchStatus']) => {
        const cfg = AUTORESEARCH_TAG[value];
        return <Tag color={cfg.color} style={{ fontSize: 12 }}>{cfg.label}</Tag>;
      },
    },
    {
      title: '更新时间',
      dataIndex: 'updatedAt',
      width: '15%',
      render: (value?: string, record?: WorkflowRecord) => {
        const source = value || record?.createdAt;
        if (!source) return <span style={{ color: '#8c8c8c' }}>-</span>;
        return (
          <span style={{ fontSize: 13, color: '#8c8c8c' }}>
            {new Date(source).toLocaleString('zh-CN', {
              year: 'numeric',
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        );
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: '20%',
      render: (_, record) => (
        <Space size={8}>
          <Button size="small" onClick={() => navigate(`/algorithm-dev/workflow-editor/${record.id}`)}>
            编排
          </Button>
          <Button
            size="small"
            onClick={() => navigate(`/algorithm-dev/autoresearch?challenger=${encodeURIComponent(record.id)}`)}
          >
            回测
          </Button>
          <Dropdown
            menu={{
              items: [
                {
                  key: 'ops',
                  label: '算法运营',
                  onClick: () =>
                    navigate(`/algorithm-dev/ops?workflowId=${encodeURIComponent(record.id)}&workflowName=${encodeURIComponent(record.name)}`),
                },
                {
                  key: 'deploy',
                  label: '算法部署',
                  onClick: () =>
                    navigate(
                      `/algorithm-dev/deployment?workflowId=${encodeURIComponent(record.id)}&workflowName=${encodeURIComponent(record.name)}&scenarioName=${encodeURIComponent(record.scenarioName)}&version=${encodeURIComponent(record.versionTag)}`,
                    ),
                },
              ],
            }}
            trigger={['click']}
          >
            <Button size="small" icon={<MoreOutlined />} />
          </Dropdown>
        </Space>
      ),
    },
  ];

  // ─── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ padding: 24, minHeight: '100%', background: '#f7f8fa' }}>
      <div style={{ maxWidth: 1440, margin: '0 auto' }}>
        {/* Breadcrumb */}
        <Breadcrumb
          style={{ marginBottom: 8, fontSize: 13, color: '#8c8c8c' }}
          items={[{ title: '算法开发' }, { title: '算法管理' }]}
        />

        {/* Page header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0, color: '#1f1f1f' }}>算法管理</h1>
            <p style={{ fontSize: 13, color: '#8c8c8c', margin: '4px 0 0' }}>
              管理工作流版本的开发、回测和部署状态
            </p>
          </div>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setWizardOpen(true)}>
            新建算法工作流
          </Button>
        </div>

        {/* Statistics strip */}
        <Card
          bordered={false}
          bodyStyle={{ padding: '16px 24px', display: 'flex', alignItems: 'center' }}
          style={{ borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.06)', marginBottom: 16 }}
        >
          <StatItem value={scenarioCount} label="行业场景" />
          <Divider />
          <StatItem value={records.length} label="工作流" />
          <Divider />
          <StatItem value={versionCount} label="开发版本" />
          <Divider />
          <StatItem value={pendingCount} label="待运营/待部署" />
        </Card>

        {/* Table card with integrated filter */}
        <Card
          bordered={false}
          bodyStyle={{ padding: 0 }}
          style={{ borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.06)' }}
        >
          {/* Filter bar */}
          <div
            style={{
              padding: '12px 16px',
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              borderBottom: '1px solid #f0f0f0',
            }}
          >
            <Input
              allowClear
              prefix={<SearchOutlined style={{ color: '#bfbfbf' }} />}
              placeholder="搜索算法名称或ID"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: 280, height: 32 }}
            />
            <Select
              value={selectedScenarioId}
              options={scenarioOptions}
              onChange={setSelectedScenarioId}
              style={{ width: 140, height: 32 }}
              placeholder="所属场景"
            />
            <Select
              value={lifecycleFilter}
              onChange={setLifecycleFilter}
              style={{ width: 120, height: 32 }}
              options={[
                { value: 'all', label: '生命周期' },
                { value: 'draft', label: '开发中' },
                { value: 'ops-ready', label: '待运营' },
                { value: 'deployment-ready', label: '待部署' },
              ]}
            />
            <div style={{ flex: 1 }} />
            <a onClick={handleReset} style={{ fontSize: 13, whiteSpace: 'nowrap' }}>重置</a>
          </div>

          {/* Table or empty state */}
          {loading ? (
            <div style={{ padding: '80px 0', textAlign: 'center' }}>
              <Spin size="large" />
            </div>
          ) : filteredRecords.length === 0 ? (
            <div style={{ padding: '80px 24px', textAlign: 'center' }}>
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                imageStyle={{ height: 80 }}
                description={null}
              />
              <h3 style={{ fontSize: 16, fontWeight: 600, margin: '16px 0 8px', color: '#1f1f1f' }}>
                暂无算法工作流
              </h3>
              <p style={{ fontSize: 13, color: '#8c8c8c', margin: '0 0 20px' }}>
                从行业场景选择推荐模板开始，或直接创建空白工作流
              </p>
              <Space direction="vertical" size={12} align="center">
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setWizardOpen(true)}>
                  新建算法工作流
                </Button>
                <a
                  onClick={() => navigate('/industry')}
                  style={{ fontSize: 13 }}
                >
                  浏览行业场景推荐 →
                </a>
              </Space>
            </div>
          ) : (
            <Table
              rowKey="id"
              columns={columns}
              dataSource={filteredRecords}
              pagination={{
                pageSize: 10,
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 条`,
                size: 'small',
              }}
              scroll={{ x: 1000 }}
              style={{ fontSize: 13 }}
            />
          )}
        </Card>
      </div>

      {/* Create workflow wizard modal */}
      <CreateWorkflowWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onCreated={async (result) => {
          // @AI_GENERATED: 三模式创建（design §35.3）——blank 带归属跳转、template/copy 克隆来源
          setWizardOpen(false);
          if (result.mode === 'blank') {
            // 空白画布：携带已确认归属，编辑器据此显示 / 写入归属，避免"未归属"资产
            navigate(
              buildJourneyHref('/algorithm-dev/workflow-editor', {
                scenarioId: result.scenarioId,
                solutionId: result.solutionId,
              }),
            );
            return;
          }
          const sourceId = result.workflowId;
          if (!sourceId) {
            navigate('/algorithm-dev/workflow-editor');
            return;
          }
          try {
            const cloned = await enhancedWorkflowApi.cloneWorkflow(sourceId);
            message.success(
              result.mode === 'copy'
                ? `已复制为新版本 v${cloned.version || '?'}`
                : `已基于推荐模板创建新版本 v${cloned.version || '?'}`,
            );
            navigate(`/algorithm-dev/workflow-editor/${cloned.id}`);
          } catch {
            message.error('创建失败，将打开原工作流');
            navigate(`/algorithm-dev/workflow-editor/${sourceId}`);
          }
        }}
      />
    </div>
  );
};

// ─── Sub-components ──────────────────────────────────────────────────────────

function StatItem({ value, label }: { value: number; label: string }) {
  return (
    <div style={{ flex: 1, textAlign: 'center' }}>
      <div style={{ fontSize: 24, fontWeight: 600, color: '#1f1f1f', lineHeight: 1.2 }}>{value}</div>
      <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4 }}>{label}</div>
    </div>
  );
}

function Divider() {
  return <div style={{ width: 1, height: 32, background: '#f0f0f0', flexShrink: 0 }} />;
}

export default AlgorithmManagementPage;
