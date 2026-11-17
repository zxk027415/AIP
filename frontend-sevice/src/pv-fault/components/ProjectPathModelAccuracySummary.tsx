// @AI_GENERATED
/**
 * 项目 × 路径 的模型与按日精度摘要。
 *
 * 这块摘要同时放在「检测与回放」「审核与精度」顶部，解决两个页面只有各自业务对象
 * （Sandbox / review session）、却看不到本项目训练模型与按日检测精度的问题。
 *
 * 数据链严格分层：
 * - 项目模型：`GET /pv-projects/{project_id}/slots/{slot}/governance-overview`
 * - 项目执行事实：`GET /pv-projects/{project_id}/executions?slot=...`
 * - 按日精度：`GET /slot-datasets/overview`，再校验
 *   `accuracy_attribution.project.project_id === 当前 project_id`
 *
 * 不把 slot 全局精度冒充项目精度：若最近业务日用的不是当前项目模型，只显示
 * 「路径有精度，但非本项目来源」，数字仅作旁证，不计入本项目。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Descriptions, Skeleton, Space, Tag, Typography } from 'antd';
import { useProjectScope } from '../../contexts/ProjectScopeContext';
import { pvProjectsApi } from '../../services/pvProjectsApi';
import type {
  GovernanceOverview,
  ModelCandidate,
  ScopedExecution,
} from '../../services/pvProjectsApi';
import { slotDatasetsApi } from '../../services/slotDatasetsApi';
import type { PathOverviewRow } from '../../services/slotDatasetsApi';

const { Text } = Typography;

const SLOT_LABEL: Record<string, string> = {
  pv_day: '天路径',
  pv_point: '点路径',
  pv_tsc: 'TSC 路径',
};

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? '未产出' : `${(value * 100).toFixed(2)}%`;
}

function compactRef(value: string | null | undefined): string {
  const text = String(value || '').trim();
  if (!text) return '—';
  return text.length > 54 ? `${text.slice(0, 28)}…${text.slice(-18)}` : text;
}

function newestCandidate(rows: ModelCandidate[]): ModelCandidate | null {
  if (!rows.length) return null;
  return [...rows].sort((a, b) =>
    String(b.registered_at || '').localeCompare(String(a.registered_at || '')),
  )[0] || null;
}

type ModelView = {
  ref: string | null;
  candidateId: string | null;
  role: 'rolling' | 'champion' | 'challenger' | 'candidate' | 'inherited' | 'none';
  /** 模型怎么进入本项目：本项目训练产出，还是随累计训练快照继承。 */
  associationKind: 'trained_in_project' | 'inherited_from_slot' | null;
  /** 继承时原 slot 上的角色（champion / rolling / challenger / latest_candidate）。 */
  sourceRole?: string | null;
  producerProjectId?: string | null;
  producerProjectName?: string | null;
  /** 是否可在本项目走复验 / Promote。继承 baseline 恒为 false。 */
  promotable: boolean;
};

/**
 * 本项目当前路径可用模型。
 *
 * 优先级：项目显式治理指针（rolling / champion / challenger）→ 项目待复验候选
 * → 随累计快照继承的 baseline。继承排在最后，因为它只是对照基线，不代表项目已有产出。
 */
function resolveProjectModel(governance: GovernanceOverview | null): ModelView {
  const current = governance?.current_detection_model;
  const rolling = current?.rolling_detect_model;
  if (rolling?.model_artifact_ref || rolling?.model_candidate_id) {
    return {
      ref: rolling.model_artifact_ref || rolling.model_candidate_id || null,
      candidateId: rolling.model_candidate_id || null,
      role: 'rolling',
      associationKind: 'trained_in_project',
      promotable: true,
    };
  }
  const champion = current?.champion;
  if (champion?.model_artifact_ref || champion?.champion_model_ref) {
    return {
      ref: champion.model_artifact_ref || champion.champion_model_ref || null,
      candidateId: champion.source_model_candidate_id || null,
      role: 'champion',
      associationKind: 'trained_in_project',
      promotable: true,
    };
  }
  const challenger = current?.challenger;
  if (challenger?.challenger_model_ref || challenger?.challenger_model_candidate_id) {
    return {
      ref: challenger.challenger_model_ref || challenger.challenger_model_candidate_id || null,
      candidateId: challenger.challenger_model_candidate_id || null,
      role: 'challenger',
      associationKind: 'trained_in_project',
      promotable: true,
    };
  }
  const candidate = newestCandidate(governance?.pending_candidates || []);
  if (candidate) {
    return {
      ref: candidate.model_artifact_ref || candidate.model_ref || candidate.model_candidate_id,
      candidateId: candidate.model_candidate_id,
      role: 'candidate',
      associationKind: 'trained_in_project',
      promotable: true,
    };
  }
  const inherited = current?.inherited_baseline;
  if (inherited?.model_artifact_ref) {
    return {
      ref: inherited.model_artifact_ref,
      candidateId: inherited.source_model_candidate_id || null,
      role: 'inherited',
      associationKind: 'inherited_from_slot',
      sourceRole: inherited.source_role || null,
      producerProjectId: inherited.producer_project_id || null,
      producerProjectName: inherited.producer_project_name || null,
      promotable: false,
    };
  }
  return { ref: null, candidateId: null, role: 'none', associationKind: null, promotable: false };
}

const SOURCE_ROLE_LABEL: Record<string, string> = {
  champion: '生产 Champion',
  rolling_detect_model: '下轮检测模型',
  challenger: 'Challenger',
  latest_candidate: '最近登记候选',
  registry_fallback: '登记回退',
};

function roleTag(model: ModelView): JSX.Element {
  if (model.role === 'rolling') return <Tag color="processing">下轮检测</Tag>;
  if (model.role === 'champion') return <Tag color="success">Champion</Tag>;
  if (model.role === 'challenger') return <Tag color="purple">Challenger</Tag>;
  if (model.role === 'candidate') return <Tag color="gold">待复验候选</Tag>;
  if (model.role === 'inherited') return <Tag color="cyan">随累计快照继承</Tag>;
  return <Tag>未产出</Tag>;
}

function noModelReason(executions: ScopedExecution[]): string {
  const training = [...executions]
    .filter((item) => item.run_mode === 'training')
    .sort((a, b) =>
      String(b.finished_at || b.started_at || '').localeCompare(String(a.finished_at || a.started_at || '')),
    );
  const latestTraining = training[0];
  if (latestTraining?.status === 'running') {
    return `training 正在运行（${latestTraining.execution_id}），完成并登记工件后才会出现模型。`;
  }
  if (latestTraining?.status === 'failed') {
    return `最近一次 training 失败：${latestTraining.failure_reason || latestTraining.execution_id}。`;
  }
  if (latestTraining?.status === 'cancelled') {
    return `最近一次 training 已取消（${latestTraining.execution_id}），没有产出可部署模型。`;
  }
  if (latestTraining?.status === 'success') {
    const auto = latestTraining.auto_candidate;
    if (auto?.reason === 'missing_model_artifact_ref') {
      return '已有成功 training，但 finalize 没带 model_artifact_ref / node_results，无法登记模型工件。';
    }
    return '已有成功 training，但尚无项目模型候选；这是历史执行或候选登记未完成。';
  }

  const experiments = executions.filter(
    (item) => item.run_mode === 'experiment' && item.status === 'success',
  );
  if (experiments.length > 0) {
    return `当前路径只完成了 ${experiments.length} 次 experiment；实验运行不可治理，不会产出部署模型。请以 training 模式运行训练工作流。`;
  }
  return '当前项目 / 路径还没有 training 执行，因此没有可部署模型。';
}

export interface ProjectPathModelAccuracySummaryProps {
  slot: string;
}

export function ProjectPathModelAccuracySummary({
  slot,
}: ProjectPathModelAccuracySummaryProps): JSX.Element {
  const { scope, generation } = useProjectScope();
  const projectId = scope.projectId;
  const [governance, setGovernance] = useState<GovernanceOverview | null>(null);
  const [executions, setExecutions] = useState<ScopedExecution[]>([]);
  const [pathRow, setPathRow] = useState<PathOverviewRow | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [failedSources, setFailedSources] = useState<string[]>([]);
  const requestSequence = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setLoadError(null);
    setFailedSources([]);
    // 切换项目 / 路径时立即清旧值，避免 skeleton 结束前残留上一 scope 的事实。
    setGovernance(null);
    setExecutions([]);
    setPathRow(null);
    if (!projectId) {
      setLoadError('缺少 project_id，无法读取项目模型与精度');
      setFailedSources(['项目上下文']);
      setLoading(false);
      return;
    }

    const [governanceResult, executionsResult, overviewResult] = await Promise.allSettled([
      pvProjectsApi.getGovernanceOverview(projectId, slot),
      pvProjectsApi.listExecutions(projectId, slot),
      slotDatasetsApi.getPathOverview(),
    ]);
    // 慢请求不能覆盖已经切换后的新 project / slot。
    if (requestId !== requestSequence.current) return;

    const failed: string[] = [];
    if (governanceResult.status === 'rejected') failed.push('模型治理');
    if (executionsResult.status === 'rejected') failed.push('执行历史');
    if (overviewResult.status === 'rejected') failed.push('按日精度');

    setGovernance(governanceResult.status === 'fulfilled' ? governanceResult.value : null);
    setExecutions(executionsResult.status === 'fulfilled' ? executionsResult.value.executions || [] : []);
    setPathRow(
      overviewResult.status === 'fulfilled'
        ? overviewResult.value.paths.find((row) => row.slot === slot) || null
        : null,
    );
    setFailedSources(failed);
    setLoadError(failed.length > 0 ? `${failed.join('、')}读取失败；失败项显示为“未知”，不会冒充业务空态。` : null);
    setLoading(false);
  }, [projectId, slot]);

  useEffect(() => {
    void load();
    return () => {
      requestSequence.current += 1;
    };
  }, [load, generation]);

  const projectContextKnown = !failedSources.includes('项目上下文');
  const governanceKnown = projectContextKnown && !failedSources.includes('模型治理');
  const executionsKnown = projectContextKnown && !failedSources.includes('执行历史');
  const accuracyKnown = projectContextKnown && !failedSources.includes('按日精度');
  const model = useMemo(() => resolveProjectModel(governance), [governance]);
  const accuracy = pathRow?.accuracy_attribution;
  const accuracyProject = accuracy?.project;
  const hasAccuracyValue = Boolean(
    accuracyKnown && accuracy?.latest_accuracy !== null && accuracy?.latest_accuracy !== undefined,
  );
  // 两种都算「本项目的精度」：
  // 1. 产出模型的训练方就是本项目；
  // 2. 产出模型正是本项目继承进来的那个 baseline（同一 mc-*）。
  // 第 2 种要单独判，否则继承模型跑出来的精度会被误报成「非本项目来源」。
  const accuracyFromTrainedHere = Boolean(hasAccuracyValue && accuracyProject?.project_id === projectId);
  const inheritedCandidateId = model.role === 'inherited' ? model.candidateId : null;
  const accuracyFromInherited = Boolean(
    hasAccuracyValue
      && inheritedCandidateId
      && accuracy?.model_id
      && accuracy.model_id === inheritedCandidateId,
  );
  const isProjectAccuracy = accuracyFromTrainedHere || accuracyFromInherited;
  const hasOtherAccuracy = hasAccuracyValue && !isProjectAccuracy;

  if (loading) {
    return <Skeleton active title={{ width: 180 }} paragraph={{ rows: 2 }} />;
  }

  // 只有连继承 baseline 都没有时才解释「没有模型」；有继承但没有本项目产出，
  // 属于另一种状态（可对照、不可 Promote），单独提示，不要说成「没有模型」。
  const reason = governanceKnown && executionsKnown && model.role === 'none'
    ? noModelReason(executions)
    : null;
  const inheritedOnly = model.role === 'inherited';
  const inheritedReason = governanceKnown && executionsKnown && inheritedOnly
    ? noModelReason(executions)
    : null;
  const workflowHref = `/projects/${encodeURIComponent(projectId)}/workflows?slot=${encodeURIComponent(slot)}`;
  const modelHref = `/projects/${encodeURIComponent(projectId)}/models?slot=${encodeURIComponent(slot)}`;

  return (
    <Space direction="vertical" size={10} style={{ width: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 }}>
        <Space size={8} wrap>
          <Text strong>本项目 · 当前路径模型与按日精度</Text>
          <Tag>{SLOT_LABEL[slot] || slot}</Tag>
        </Space>
        <Button type="link" size="small" onClick={() => void load()}>
          刷新
        </Button>
      </div>

      {loadError ? <Alert type="error" showIcon message={loadError} /> : null}

      <Descriptions
        size="small"
        bordered
        column={{ xs: 1, sm: 2, lg: 4 }}
      >
        <Descriptions.Item label="本项目可用模型">
          {!governanceKnown ? (
            <Tag color="red">读取失败，状态未知</Tag>
          ) : (
            <Space direction="vertical" size={2}>
              <Space size={4} wrap>
                {roleTag(model)}
                {model.candidateId ? <Text code>{model.candidateId}</Text> : null}
              </Space>
              {model.ref ? (
                <Text title={model.ref} style={{ fontSize: 12 }}>
                  {compactRef(model.ref)}
                </Text>
              ) : (
                <Text type="secondary">无</Text>
              )}
              {model.role === 'inherited' ? (
                <Text type="secondary" style={{ fontSize: 11 }}>
                  原路径角色：{SOURCE_ROLE_LABEL[String(model.sourceRole)] || model.sourceRole || '—'}
                  {model.producerProjectName ? ` · 训练方 ${model.producerProjectName}` : ''}
                </Text>
              ) : null}
            </Space>
          )}
        </Descriptions.Item>

        <Descriptions.Item label="成功 training">
          {executionsKnown ? (
            <>
              <Text strong>
                {executions.filter((item) => item.run_mode === 'training' && item.status === 'success').length}
              </Text>
              <Text type="secondary"> 次</Text>
            </>
          ) : (
            <Tag color="red">未知</Tag>
          )}
        </Descriptions.Item>

        <Descriptions.Item label="最近业务日精度">
          {!accuracyKnown ? (
            <Tag color="red">读取失败，状态未知</Tag>
          ) : isProjectAccuracy ? (
            <Space direction="vertical" size={0}>
              <Text strong>{pct(accuracy?.latest_accuracy)}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {accuracy?.latest_day || '日期未记录'} · 计入 {accuracy?.latest_counted_units ?? 0} 个评估单元
              </Text>
            </Space>
          ) : (
            <Tag>本项目未产出</Tag>
          )}
        </Descriptions.Item>

        <Descriptions.Item label="精度归属">
          {!accuracyKnown ? (
            <Tag color="red">未知</Tag>
          ) : isProjectAccuracy ? (
            <Space direction="vertical" size={0}>
              <Tag color={accuracyFromInherited ? 'cyan' : 'green'}>
                {accuracyFromInherited ? '本项目继承模型' : '本项目训练模型'}
              </Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {accuracy?.model_id || '—'}
              </Text>
            </Space>
          ) : hasOtherAccuracy ? (
            <Space direction="vertical" size={0}>
              <Tag color="orange">非本项目来源</Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>
                路径最近值 {pct(accuracy?.latest_accuracy)} · {accuracy?.model_id || '模型未记录'}
              </Text>
            </Space>
          ) : (
            <Text type="secondary">尚无带真值的按日检测结果</Text>
          )}
        </Descriptions.Item>
      </Descriptions>

      {reason ? (
        <Alert
          type="warning"
          showIcon
          message="为什么当前路径没有项目模型"
          description={reason}
          action={<Link to={workflowHref}>打开工作流与运行</Link>}
        />
      ) : inheritedReason ? (
        <Alert
          type="info"
          showIcon
          message="当前是随累计训练快照继承的模型，可用于对照，但不能在本项目 Promote"
          description={`${inheritedReason} 继承模型共享原路径工件（未复制二进制），保留原始血缘；要让本项目对模型负责并上岗检测，仍需本项目训练 + 正式复验。`}
          action={<Link to={modelHref}>查看模型与治理</Link>}
        />
      ) : governanceKnown && accuracyKnown && model.role !== 'none' && !isProjectAccuracy ? (
        <Alert
          type="info"
          showIcon
          message="项目模型已可见，但还没有归属于它的按日精度"
          description="需要让该模型进入检测选择，并推进至少一个带真值的业务日。路径里其它模型或内置规则产生的精度不会冒充本项目精度。"
          action={<Link to={modelHref}>查看模型与治理</Link>}
        />
      ) : null}
    </Space>
  );
}

export default ProjectPathModelAccuracySummary;
// @AI_GENERATED: end
