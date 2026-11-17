import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Empty, Input, Modal, Select, Space, Spin, Steps, Tag } from 'antd';
import { CheckOutlined } from '@ant-design/icons';
import { enhancedWorkflowApi } from '../services/workflowEnhancedApi';
import { industryApi } from '../services/industryApi';
import type { IndustryTemplate } from '../services/industryApi';
import type { EnhancedWorkflowSummary } from '../types/workflow-enhanced';
import type { IndustryScenario } from '../types/industry';

// @AI_GENERATED
// ─── Public contract ──────────────────────────────────────────────────────────
// 三种显式创建模式（design §35.3）：
//   template — 从方案推荐模板创建（默认）：克隆 canonical 模板为新版本，保留来源与主干归属。
//   copy     — 复制已有工作流：克隆指定 workflow_id，版本递增，归属继承。
//   blank    — 空白画布：空图，但仍要求确认归属（场景 / 方案），不产生"未归属"资产。
export type CreateWorkflowMode = 'template' | 'copy' | 'blank';

/** 向导确认后的结果；由调用方决定克隆 / 跳转编辑器并带上归属。 */
export interface CreateWorkflowResult {
  mode: CreateWorkflowMode;
  /** 作为克隆来源的 workflow_id（template/copy 模式）；blank 模式为 undefined。 */
  workflowId?: string;
  /** 归属：行业场景 ID。 */
  scenarioId?: string;
  /** 归属：算法方案 ID。 */
  solutionId?: string;
}

interface CreateWorkflowWizardProps {
  open: boolean;
  onClose: () => void;
  /** 确认创建时回调；见 CreateWorkflowResult。 */
  onCreated: (result: CreateWorkflowResult) => void;
  /** 预填：行业场景 ID（从场景详情 / 算法管理带参进入时提供）。 */
  initialScenarioId?: string;
  /** 预填：算法方案 ID。 */
  initialSolutionId?: string;
}

const MODE_OPTIONS: Array<{ mode: CreateWorkflowMode; title: string; when: string; result: string }> = [
  {
    mode: 'template',
    title: '从方案推荐模板创建（默认推荐）',
    when: '已知场景与方案，想快速开始',
    result: '克隆方案的 canonical 模板为新版本，保留来源模板与主干归属',
  },
  {
    mode: 'copy',
    title: '复制已有工作流',
    when: '在现有版本上迭代',
    result: '克隆指定工作流，版本号递增，归属继承',
  },
  {
    mode: 'blank',
    title: '空白画布',
    when: '专家自建',
    result: '空图，但仍要求确认归属（场景 / 方案），不允许产生"未归属"资产',
  },
];

// ─── Component ───────────────────────────────────────────────────────────────

const CreateWorkflowWizard: React.FC<CreateWorkflowWizardProps> = ({
  open,
  onClose,
  onCreated,
  initialScenarioId,
  initialSolutionId,
}) => {
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<CreateWorkflowMode>('template');
  const [scenarioId, setScenarioId] = useState<string | undefined>(initialScenarioId);
  const [solutionId, setSolutionId] = useState<string | undefined>(initialSolutionId);

  const [scenarios, setScenarios] = useState<IndustryScenario[]>([]);
  const [solutions, setSolutions] = useState<IndustryTemplate[]>([]);
  const [workflows, setWorkflows] = useState<EnhancedWorkflowSummary[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);

  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [sourceSearch, setSourceSearch] = useState('');
  const [crossScenario, setCrossScenario] = useState(false);

  const needOwnership = mode === 'template' || mode === 'blank';
  const ownershipReady = !!scenarioId && !!solutionId;

  // 每次打开时用最新预填同步归属并回到起点（父级可能在不同入口带入不同 scenario/solution；
  // 组件常驻不卸载，useState 初值不会随 props 变化更新，故需显式同步）。
  useEffect(() => {
    if (!open) return;
    setStep(0);
    setMode('template');
    setScenarioId(initialScenarioId);
    setSolutionId(initialSolutionId);
    setSelectedSource(null);
    setSourceSearch('');
    setCrossScenario(false);
  }, [open, initialScenarioId, initialSolutionId]);

  // 打开时加载场景 + 全部工作流；预填时同步加载该场景的方案。
  useEffect(() => {
    if (!open) return;
    industryApi.getScenarios().then(setScenarios).catch(() => setScenarios([]));
    setLoadingWorkflows(true);
    enhancedWorkflowApi
      .listWorkflowSummaries()
      .then(setWorkflows)
      .catch(() => setWorkflows([]))
      .finally(() => setLoadingWorkflows(false));
  }, [open]);

  // 场景变化时加载其下方案（用于归属选择）。
  useEffect(() => {
    if (!open || !scenarioId) {
      setSolutions([]);
      return;
    }
    industryApi
      .getTemplates(scenarioId)
      .then((list) => {
        setSolutions(list);
        // 若当前所选方案不属于新场景，清空之，避免归属错配。
        setSolutionId((prev) => (prev && list.some((s) => s.id === prev) ? prev : undefined));
      })
      .catch(() => setSolutions([]));
  }, [open, scenarioId]);

  const resetState = () => {
    setStep(0);
    setMode('template');
    setScenarioId(initialScenarioId);
    setSolutionId(initialSolutionId);
    setSelectedSource(null);
    setSourceSearch('');
    setCrossScenario(false);
  };

  const handleClose = () => {
    resetState();
    onClose();
  };

  // step 0（选择方式）→ 若归属已就绪或该模式不强制归属，跳过归属步骤。
  const goFromMode = () => {
    setSelectedSource(null);
    if (needOwnership && !ownershipReady) setStep(1);
    else setStep(2);
  };

  const confirmCreate = () => {
    if (mode === 'blank') {
      if (!scenarioId || !solutionId) return;
      onCreated({ mode, scenarioId, solutionId });
    } else {
      if (!selectedSource) return;
      onCreated({ mode, workflowId: selectedSource, scenarioId, solutionId });
    }
    resetState();
  };

  // 推荐模板：优先按方案 / 场景归属过滤；勾选"跨场景"或无匹配时回退到全部（不做死胡同）。
  const sourceCandidates = useMemo(() => {
    const kw = sourceSearch.trim().toLowerCase();
    let base = workflows;
    if (mode === 'template' && !crossScenario) {
      const scoped = workflows.filter(
        (w) => (solutionId && w.solution_id === solutionId) || (scenarioId && w.scenario_id === scenarioId),
      );
      base = scoped;
    }
    if (kw) {
      base = base.filter(
        (w) => w.name.toLowerCase().includes(kw) || (w.description || '').toLowerCase().includes(kw) || w.id.toLowerCase().includes(kw),
      );
    }
    return base;
  }, [workflows, mode, crossScenario, solutionId, scenarioId, sourceSearch]);

  const steps = [{ title: '选择方式' }, { title: '确认归属' }, { title: mode === 'blank' ? '确认创建' : '选择来源' }];

  return (
    <Modal
      open={open}
      onCancel={handleClose}
      title={<span style={{ fontSize: 18, fontWeight: 600 }}>新建算法工作流</span>}
      width={720}
      footer={null}
      destroyOnClose
      styles={{ body: { padding: '0 24px 24px' } }}
    >
      <Steps current={step} size="small" style={{ marginBottom: 20, padding: '0 24px' }} items={steps} />

      {/* Step 0 — 选择创建方式 */}
      {step === 0 && (
        <>
          <p style={{ fontSize: 14, color: '#8c8c8c', margin: '0 0 16px' }}>选择创建方式，三种方式的产出不同：</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
            {MODE_OPTIONS.map((opt) => (
              <ModeCard
                key={opt.mode}
                title={opt.title}
                when={opt.when}
                result={opt.result}
                selected={mode === opt.mode}
                onClick={() => setMode(opt.mode)}
              />
            ))}
          </div>
          <FooterBar>
            <Button onClick={handleClose}>取消</Button>
            <Button type="primary" onClick={goFromMode}>
              下一步
            </Button>
          </FooterBar>
        </>
      )}

      {/* Step 1 — 确认归属（场景 + 方案） */}
      {step === 1 && (
        <>
          <p style={{ fontSize: 14, color: '#8c8c8c', margin: '0 0 16px' }}>
            确认归属，避免产生"未归属"资产。{mode === 'blank' ? '空白画布必须确认场景与方案。' : '归属用于推荐匹配的模板。'}
          </p>
          <Space direction="vertical" size={14} style={{ width: '100%', marginBottom: 16 }}>
            <div>
              <div style={{ fontSize: 13, marginBottom: 6 }}>行业场景</div>
              <Select
                showSearch
                allowClear
                placeholder="搜索并选择行业场景"
                style={{ width: '100%' }}
                value={scenarioId}
                onChange={(v) => setScenarioId(v)}
                optionFilterProp="label"
                options={scenarios.map((s) => ({ value: s.id, label: s.name }))}
              />
            </div>
            <div>
              <div style={{ fontSize: 13, marginBottom: 6 }}>算法方案</div>
              <Select
                showSearch
                allowClear
                placeholder={scenarioId ? '搜索并选择算法方案' : '请先选择行业场景'}
                style={{ width: '100%' }}
                value={solutionId}
                disabled={!scenarioId}
                onChange={(v) => setSolutionId(v)}
                optionFilterProp="label"
                options={solutions.map((s) => ({ value: s.id, label: s.name }))}
                notFoundContent={scenarioId ? '该场景下暂无方案' : '请先选择行业场景'}
              />
            </div>
          </Space>
          <FooterBar>
            <Button onClick={() => setStep(0)}>上一步</Button>
            <Button
              type="primary"
              disabled={!scenarioId || (mode === 'blank' && !solutionId)}
              onClick={() => setStep(2)}
            >
              下一步
            </Button>
          </FooterBar>
        </>
      )}

      {/* Step 2 — 选择来源（template/copy）或确认创建（blank） */}
      {step === 2 && (
        <>
          {mode === 'blank' ? (
            <>
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
                message="将创建一张空白画布"
                description={
                  <Space direction="vertical" size={2}>
                    <span>已确认归属，保存时写入工作流自身：</span>
                    <span>
                      行业场景：<Tag>{scenarioName(scenarios, scenarioId)}</Tag>
                      算法方案：<Tag>{solutionName(solutions, solutionId)}</Tag>
                    </span>
                  </Space>
                }
              />
              <FooterBar>
                <Button onClick={() => setStep(needOwnership && !ownershipReady ? 1 : 0)}>上一步</Button>
                <Button type="primary" disabled={!scenarioId || !solutionId} onClick={confirmCreate}>
                  创建空白画布
                </Button>
              </FooterBar>
            </>
          ) : (
            <>
              <p style={{ fontSize: 14, color: '#8c8c8c', margin: '0 0 12px' }}>
                {mode === 'template' ? '选择方案推荐的模板作为基础：' : '选择要复制的已有工作流：'}
              </p>
              <Space style={{ width: '100%', marginBottom: 12 }} direction="vertical" size={8}>
                <Input.Search
                  allowClear
                  placeholder="按名称 / ID / 描述搜索"
                  value={sourceSearch}
                  onChange={(e) => setSourceSearch(e.target.value)}
                />
                {mode === 'template' && (
                  <label style={{ fontSize: 13, color: '#595959', cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={crossScenario}
                      onChange={(e) => setCrossScenario(e.target.checked)}
                      style={{ marginRight: 6 }}
                    />
                    跨场景搜索全部模板
                  </label>
                )}
              </Space>

              {loadingWorkflows ? (
                <div style={{ padding: '40px 0', textAlign: 'center' }}>
                  <Spin />
                </div>
              ) : sourceCandidates.length === 0 ? (
                <div style={{ padding: '20px 0', textAlign: 'center' }}>
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={mode === 'template' ? '该方案暂无已标注模板' : '暂无可复制的工作流'}
                  />
                  <Space direction="vertical" size={8} style={{ marginTop: 12 }}>
                    {mode === 'template' && !crossScenario && (
                      <Button size="small" onClick={() => setCrossScenario(true)}>
                        跨场景搜索全部模板
                      </Button>
                    )}
                    <Button
                      size="small"
                      type="link"
                      disabled={!scenarioId || !solutionId}
                      onClick={() => {
                        setMode('blank');
                        setStep(2);
                      }}
                    >
                      改为空白创建（保留已确认归属）
                    </Button>
                    {(!scenarioId || !solutionId) && (
                      <span style={{ fontSize: 12, color: '#8c8c8c' }}>空白创建需先在上一步确认场景与方案</span>
                    )}
                  </Space>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16, maxHeight: 340, overflowY: 'auto' }}>
                  {sourceCandidates.map((wf) => (
                    <SourceCard
                      key={wf.id}
                      name={wf.name}
                      description={wf.description}
                      nodeCount={wf.nodeCount}
                      version={wf.version}
                      selected={selectedSource === wf.id}
                      onClick={() => setSelectedSource(wf.id)}
                    />
                  ))}
                </div>
              )}

              <FooterBar>
                <Button onClick={() => setStep(needOwnership && !ownershipReady ? 1 : 0)}>上一步</Button>
                <Button type="primary" disabled={!selectedSource} onClick={confirmCreate}>
                  {mode === 'template' ? '基于推荐模板创建' : '复制此工作流'}
                </Button>
              </FooterBar>
            </>
          )}
        </>
      )}
    </Modal>
  );
};

// ─── Sub-components ──────────────────────────────────────────────────────────

function FooterBar({ children }: { children: React.ReactNode }) {
  return <div style={{ display: 'flex', justifyContent: 'space-between' }}>{children}</div>;
}

function ModeCard({ title, when, result, selected, onClick }: {
  title: string;
  when: string;
  result: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        position: 'relative',
        border: selected ? '2px solid #1677ff' : '1px solid #e8e8e8',
        borderRadius: 8,
        padding: '12px 16px',
        cursor: 'pointer',
        background: selected ? '#f0f7ff' : '#fff',
        transition: 'border-color 0.2s, background 0.2s',
      }}
    >
      {selected && (
        <span
          style={{
            position: 'absolute',
            top: 10,
            right: 10,
            width: 18,
            height: 18,
            borderRadius: '50%',
            background: '#1677ff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <CheckOutlined style={{ color: '#fff', fontSize: 10 }} />
        </span>
      )}
      <div style={{ fontWeight: 600, fontSize: 14, color: '#1f1f1f', marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 12, color: '#595959' }}>何时用：{when}</div>
      <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 2 }}>结果：{result}</div>
    </div>
  );
}

function SourceCard({ name, description, nodeCount, version, selected, onClick }: {
  name: string;
  description?: string;
  nodeCount: number;
  version?: number;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        border: selected ? '2px solid #1677ff' : '1px solid #e8e8e8',
        borderRadius: 8,
        padding: '12px 16px',
        cursor: 'pointer',
        background: selected ? '#f0f7ff' : '#fff',
        transition: 'border-color 0.2s, background 0.2s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 500, fontSize: 14, color: '#1f1f1f' }}>{name}</span>
        <span style={{ fontSize: 11, color: '#8c8c8c' }}>
          {typeof version === 'number' ? `v${version} · ` : ''}
          {nodeCount} 个节点
        </span>
      </div>
      {description && (
        <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {description}
        </div>
      )}
    </div>
  );
}

function scenarioName(scenarios: IndustryScenario[], id?: string): string {
  return scenarios.find((s) => s.id === id)?.name || id || '（未设置）';
}

function solutionName(solutions: IndustryTemplate[], id?: string): string {
  return solutions.find((s) => s.id === id)?.name || id || '（未设置）';
}

export default CreateWorkflowWizard;
// @AI_GENERATED: end
