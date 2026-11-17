// @AI_GENERATED
/**
 * 模型与治理阶段：四层治理页（design §11.4 / §16；任务 4.1）。
 *
 * 四层（数据取自 GET .../governance-overview）：
 *  1) 当前检测模型 current_detection_model — 下一轮检测滚动指针 + Champion / Challenger + registry_version（只读真源）。
 *  2) 待复验候选 pending_candidates — governance_eligible=true 的候选；可发起正式复验（scoped 证据写入）。
 *  3) 实验结果 experiment_results — governance_eligible=false（validation / experiment / sandbox）；显式标注不可进入正式治理。
 *  4) 治理历史 governance_history + 复验记录 verifications — Promote 审计（append-only）与复验 pending/passed 状态。
 *
 * 红线：滚动指针 / Promote 会改动生产真源，本环境 production_writes_authorized=false，页面对这两类动作
 * 显式禁用并解释，仅在获得人工授权的兼容页（AlgorithmDeploymentPage）执行。发起复验只落 pending，不臆造通过。
 * wrap-first：底部保留既有 SlotDeployedModelPanel / ModelPathManager，不重写工作面板。
 */

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Collapse, Divider, Space, Table, Tag, Tooltip, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import StageSlotGate from '../../components/StageSlotGate';
import { ActionStateView } from '../../components/ActionStateView';
import SlotDeployedModelPanel from '../../../components/slot/SlotDeployedModelPanel';
import ModelPathManager from '../../../components/pv-fault/ModelPathManager';
import { useProjectScope } from '../../../contexts/ProjectScopeContext';
import { buildJourneyHref } from '../../../utils/journeyParams';
import { pvProjectsApi } from '../../../services/pvProjectsApi';
import type {
  GovernanceOverview,
  ModelCandidate,
  PromotionEvent,
  Verification,
} from '../../../services/pvProjectsApi';

const { Title, Text, Paragraph } = Typography;

const VERIFICATION_TAG: Record<string, { color: string; label: string }> = {
  pending: { color: 'processing', label: '复验进行中（未决）' },
  passed: { color: 'success', label: '复验通过' },
  failed: { color: 'error', label: '复验未通过' },
};

/** 找到某候选最新一条复验记录（同 scope 内）。 */
function latestVerification(candidateId: string, verifications: Verification[]): Verification | undefined {
  const mine = verifications.filter((v) => v.model_candidate_id === candidateId);
  if (mine.length === 0) return undefined;
  return mine[mine.length - 1];
}

function CurrentDetectionModel({ data }: { data: GovernanceOverview['current_detection_model'] }): JSX.Element {
  const {
    rolling_detect_model: rolling,
    champion,
    challenger,
    inherited_baseline: inherited,
    registry_version,
    empty,
  } = data;
  // 有继承 baseline 时 registry_version 已 > 0，不会走这个空态；这里仍保留双重判断，
  // 避免旧后端（无该字段）时把继承状态误显示成有内容。
  if (empty && !inherited) {
    return (
      <ActionStateView
        descriptor={{
          state: 'initial_empty',
          title: '当前路径尚无生产模型登记',
          reason: '该项目 / 路径下 registry 版本为 0，未设置滚动检测模型或 Champion。',
          nextAction: '在获得授权的部署治理页登记生产模型，或先复验候选',
        }}
      />
    );
  }
  return (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Space wrap size={12}>
        <Text strong>registry 版本：</Text>
        <Tag color="blue">v{registry_version}</Tag>
      </Space>
      <Space direction="vertical" size={2}>
        <Text type="secondary">下一轮检测模型（rolling_detect_model）</Text>
        {rolling ? (
          <Text code>{rolling.model_artifact_ref || rolling.model_candidate_id || '—'}</Text>
        ) : (
          <Text type="secondary">未设置</Text>
        )}
      </Space>
      <Space direction="vertical" size={2}>
        <Text type="secondary">当前生产 Champion</Text>
        {champion ? (
          <Text code>{champion.champion_model_ref || champion.source_model_candidate_id || '—'}</Text>
        ) : (
          <Text type="secondary">未设置</Text>
        )}
      </Space>
      <Space direction="vertical" size={2}>
        <Text type="secondary">当前 Challenger</Text>
        {challenger ? (
          <Text code>{challenger.challenger_model_ref || challenger.challenger_model_candidate_id || '—'}</Text>
        ) : (
          <Text type="secondary">未设置</Text>
        )}
      </Space>
      {/* @AI_GENERATED: 随累计训练快照继承的 baseline —— 与上面三个治理指针并列但无治理效力。 */}
      <Space direction="vertical" size={2}>
        <Space size={6} wrap>
          <Text type="secondary">随累计快照继承的 baseline</Text>
          {inherited ? <Tag color="cyan">仅对照，不可 Promote</Tag> : null}
        </Space>
        {inherited ? (
          <Space direction="vertical" size={0}>
            <Text code>{inherited.source_model_candidate_id || inherited.model_artifact_ref}</Text>
            <Text type="secondary" style={{ fontSize: 11 }}>
              工件 {inherited.model_artifact_ref} · 原路径角色 {inherited.source_role || '—'}
              {inherited.producer_project_name ? ` · 训练方 ${inherited.producer_project_name}` : ''}
            </Text>
            <Text type="secondary" style={{ fontSize: 11 }}>
              共享原工件未复制二进制；不进候选池、不能发起复验或设滚动指针。
            </Text>
          </Space>
        ) : (
          <Text type="secondary">未继承</Text>
        )}
      </Space>
      {/* @AI_GENERATED: end */}
    </Space>
  );
}

function FourLayerGovernance({ slot }: { slot: string }): JSX.Element {
  const navigate = useNavigate();
  const { scope, generation, refresh } = useProjectScope();
  const projectId = scope.projectId;
  const [overview, setOverview] = useState<GovernanceOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [verifyingId, setVerifyingId] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    pvProjectsApi
      .getGovernanceOverview(projectId, slot)
      .then((res) => setOverview(res))
      .catch(() => setError('治理视图读取失败'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, slot, generation]);

  useEffect(() => {
    load();
  }, [load]);

  const onStartVerification = async (candidate: ModelCandidate) => {
    if (!projectId) return;
    const gaps = candidate.provenance_gaps ?? [];
    if (gaps.length > 0) {
      message.warning(`候选 provenance 不完整（缺 ${gaps.join(', ')}），无法发起正式复验`);
      return;
    }
    setVerifyingId(candidate.model_candidate_id);
    try {
      await pvProjectsApi.startVerification(projectId, slot, candidate.model_candidate_id, {});
      message.success('已发起正式复验（落 pending，真实多窗引擎接入后才可判定通过）');
      load();
    } catch {
      message.error('发起复验失败');
    } finally {
      setVerifyingId(null);
    }
  };

  const goDeployment = () =>
    navigate(
      buildJourneyHref('/algorithm-deployment', {
        projectId,
        slot,
        datasetVersionId: scope.datasetVersionId,
      }),
    );

  if (loading) {
    return <ActionStateView descriptor={{ state: 'loading', title: '正在读取治理视图' }} />;
  }
  if (error || !overview) {
    return (
      <ActionStateView
        descriptor={{
          state: 'recoverable_failure',
          title: '治理视图加载失败',
          reason: error || '空响应',
          nextAction: '刷新当前项目后重试',
          scope: { projectId, slot },
        }}
        onRefresh={refresh}
      />
    );
  }

  const pendingColumns: ColumnsType<ModelCandidate> = [
    {
      // 「模型出生绑工作流」：候选按来源工作流归组，让 工作流 → 模型 → 精度 一眼可见。
      title: '来源工作流',
      dataIndex: 'source_workflow_id',
      render: (wfId: string | null, rec) => (
        <Space direction="vertical" size={0}>
          <Text strong style={{ fontSize: 12 }}>{wfId || '（未记录工作流）'}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            快照：{rec.source_snapshot_id || '—'}
          </Text>
        </Space>
      ),
    },
    {
      title: '候选',
      dataIndex: 'model_candidate_id',
      render: (id: string, rec) => (
        <Space direction="vertical" size={0}>
          <Text code>{id}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            来源执行：{rec.source_execution_id || '—'}
          </Text>
        </Space>
      ),
    },
    {
      title: '模型工件',
      dataIndex: 'model_artifact_ref',
      render: (ref?: string) => <Text style={{ fontSize: 12 }}>{ref || '—'}</Text>,
    },
    {
      title: '复验状态',
      render: (_: unknown, rec) => {
        const gaps = rec.provenance_gaps ?? [];
        if (gaps.length > 0) {
          return (
            <Tooltip title={`缺失：${gaps.join(', ')}`}>
              <Tag color="warning">provenance 不完整</Tag>
            </Tooltip>
          );
        }
        const ver = latestVerification(rec.model_candidate_id, overview.verifications);
        if (!ver) return <Text type="secondary">未复验</Text>;
        const t = VERIFICATION_TAG[ver.status] || { color: 'default', label: ver.status };
        return <Tag color={t.color}>{t.label}</Tag>;
      },
    },
    {
      title: '操作',
      render: (_: unknown, rec) => {
        const gaps = rec.provenance_gaps ?? [];
        const ver = latestVerification(rec.model_candidate_id, overview.verifications);
        const alreadyPending = ver?.status === 'pending';
        return (
          <Button
            size="small"
            disabled={gaps.length > 0 || alreadyPending}
            loading={verifyingId === rec.model_candidate_id}
            onClick={() => onStartVerification(rec)}
          >
            {alreadyPending ? '复验进行中' : '发起正式复验'}
          </Button>
        );
      },
    },
  ];

  const experimentColumns: ColumnsType<ModelCandidate> = [
    {
      title: '实验结果候选',
      dataIndex: 'model_candidate_id',
      render: (id: string, rec) => (
        <Space direction="vertical" size={0}>
          <Text code>{id}</Text>
          <Text type="secondary" style={{ fontSize: 11 }}>
            来源执行：{rec.source_execution_id || '—'}
          </Text>
        </Space>
      ),
    },
    {
      title: '模型工件',
      dataIndex: 'model_artifact_ref',
      render: (ref?: string) => <Text style={{ fontSize: 12 }}>{ref || '—'}</Text>,
    },
    {
      title: '治理资格',
      render: () => <Tag color="default">非可治理（不能复验 / Promote）</Tag>,
    },
  ];

  const historyColumns: ColumnsType<PromotionEvent> = [
    {
      title: '事件',
      dataIndex: 'promotion_id',
      render: (id: string) => <Text code>{id}</Text>,
    },
    {
      title: '候选 / 复验',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>候选：{rec.model_candidate_id}</Text>
          <Text style={{ fontSize: 12 }} type="secondary">
            复验：{rec.verification_id}
          </Text>
        </Space>
      ),
    },
    {
      title: '动作',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={0}>
          <Tag color={rec.set_as_production ? 'red' : 'gold'}>
            {rec.set_as_production ? '同步写生产 Champion' : '仅登记 Challenger'}
          </Tag>
          {rec.champion_changed && <Text style={{ fontSize: 11 }}>Champion 已变更</Text>}
        </Space>
      ),
    },
    {
      title: '版本 / 操作者',
      render: (_: unknown, rec) => (
        <Space direction="vertical" size={0}>
          <Text style={{ fontSize: 12 }}>
            v{rec.registry_version_before} → v{rec.registry_version_after}
          </Text>
          <Text style={{ fontSize: 11 }} type="secondary">
            {rec.operator || '—'}
          </Text>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={20} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message="四层模型治理"
        description="当前检测模型（真源）/ 待复验候选 / 实验结果（非可治理）/ 治理历史。滚动指针与 Promote 会改动生产真源，本环境未授权，按只读展示并引导到授权部署页；发起复验只落 pending，不臆造通过。"
      />

      {/* 第 1 层：当前检测模型 */}
      <div>
        <Title level={5} style={{ marginBottom: 8 }}>
          ① 当前检测模型（生产真源，只读）
        </Title>
        <CurrentDetectionModel data={overview.current_detection_model} />
      </div>
      <Divider style={{ margin: 0 }} />

      {/* 第 2 层：待复验候选 */}
      <div>
        <Title level={5} style={{ marginBottom: 8 }}>
          ② 待复验候选（可治理）
        </Title>
        {overview.pending_candidates.length === 0 ? (
          <ActionStateView
            descriptor={{
              state: 'initial_empty',
              title: '暂无可治理候选',
              reason: '尚无来自成功且可治理 production 执行的候选。',
              nextAction: '在运行中心以 training 模式（非 sandbox）产出可治理候选',
            }}
          />
        ) : (
          <>
            <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
              候选按**来源工作流**归组：模型与其分数绑工作流（谁训出来的），而"上岗"绑路径（本路径只有一个在岗模型）。
              绑定同一冻结快照的候选之间可公平比较。
            </Paragraph>
            <Table
              rowKey="model_candidate_id"
              size="small"
              columns={pendingColumns}
              dataSource={[...overview.pending_candidates].sort((a, b) =>
                String(a.source_workflow_id || '').localeCompare(String(b.source_workflow_id || '')),
              )}
              pagination={false}
            />
          </>
        )}
      </div>
      <Divider style={{ margin: 0 }} />

      {/* 第 3 层：实验结果（非可治理） */}
      <div>
        <Title level={5} style={{ marginBottom: 8 }}>
          ③ 实验结果（非可治理）
        </Title>
        <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
          来自 validation / experiment / sandbox 的模型工件仅作实验证据，不能进入正式复验或 Promote。
        </Paragraph>
        {overview.experiment_results.length === 0 ? (
          <Text type="secondary">暂无实验结果候选。</Text>
        ) : (
          <Table
            rowKey="model_candidate_id"
            size="small"
            columns={experimentColumns}
            dataSource={overview.experiment_results}
            pagination={false}
          />
        )}
      </div>
      <Divider style={{ margin: 0 }} />

      {/* 第 4 层：治理历史 */}
      <div>
        <Title level={5} style={{ marginBottom: 8 }}>
          ④ 治理历史（Promote 审计，append-only）
        </Title>
        {overview.governance_history.length === 0 ? (
          <Text type="secondary">暂无 Promote 记录。生产写入需人工授权，本环境未授权。</Text>
        ) : (
          <Table
            rowKey="promotion_id"
            size="small"
            columns={historyColumns}
            dataSource={overview.governance_history}
            pagination={{ pageSize: 5, size: 'small' }}
          />
        )}
      </div>

      {/* 生产写入引导（受授权门控，本环境只读） */}
      <Alert
        type="warning"
        showIcon
        message="滚动指针 / Promote 受生产授权门控"
        description="本环境 production_writes_authorized=false，设下一轮检测模型与 Promote 均被服务端阻止。请在获得人工授权后于部署治理页执行。"
        action={
          <Button size="small" onClick={goDeployment}>
            打开授权部署页（兼容页）
          </Button>
        }
      />

      {/* wrap-first：保留既有工作面板 */}
      <Collapse
        ghost
        size="small"
        items={[
          {
            key: 'legacy-panels',
            label: '现有部署 / 路径模型面板（wrap-first）',
            children: (
              <Space direction="vertical" size={12} style={{ width: '100%' }}>
                <SlotDeployedModelPanel slot={slot} embedded />
                <Divider style={{ margin: '8px 0' }} />
                <ModelPathManager slot={slot} />
              </Space>
            ),
          },
        ]}
      />
    </Space>
  );
}

export function ProjectModelsStagePage(): JSX.Element {
  return (
    <StageSlotGate prompt="选择一条诊断路径以查看其四层模型治理状态。">
      {(slot) => <FourLayerGovernance slot={slot} />}
    </StageSlotGate>
  );
}

export default ProjectModelsStagePage;
// @AI_GENERATED: end
