// @AI_GENERATED: load-forecast-evidence-rail
/**
 * LoadForecastStoryRail.tsx
 *
 * 输入当前场景、调度摘要、精度快照、告警与恢复决策，输出负荷预测从调度到部署审计的
 * 证据状态带。它只解释已存在的后端数据，不把静态流程说明伪装成一次已完成的真实运行。
 */
import React from 'react';
import { Button, Skeleton, Space, Tag, Tooltip, Typography } from 'antd';
import {
  AuditOutlined,
  BarChartOutlined,
  ClockCircleOutlined,
  DeploymentUnitOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { ScheduledTaskSummary } from '../../services/deploymentApi';
import type {
  AccuracyAlert,
  MonitoringSnapshot,
  OverviewResponse,
  RecoveryDecision,
} from '../../types/accuracy-operations';

const { Text } = Typography;

type EvidenceTone = 'neutral' | 'pending' | 'healthy' | 'warning' | 'critical';

interface EvidenceStage {
  key: string;
  label: string;
  detail: string;
  tone: EvidenceTone;
  icon: React.ReactNode;
}

interface LoadForecastStoryRailProps {
  /** slot — 当前演示的部署与精度运营分区场景。 */
  slot: string;
  /** schedulerTask — 与当前场景匹配的负荷预测调度任务摘要。 */
  schedulerTask: ScheduledTaskSummary | null;
  /** schedulerLoading — 调度摘要是否正在读取。 */
  schedulerLoading: boolean;
  /** schedulerError — 调度摘要无法读取时的可读错误。 */
  schedulerError: string | null;
  /** overview — 当前场景的生产模型和事件计数总览。 */
  overview: OverviewResponse | null;
  /** monitoringSnapshot — 当前场景的生产、影子与预上线指标快照。 */
  monitoringSnapshot: MonitoringSnapshot | null;
  /** alerts — 当前场景已读取的精度告警集合。 */
  alerts: AccuracyAlert[];
  /** selectedAlert — 用户当前正在处置的告警。 */
  selectedAlert: AccuracyAlert | null;
  /** decision — 当前告警对应的恢复仲裁结果。 */
  decision: RecoveryDecision | null;
  /** refreshing — 统一刷新操作进行中。 */
  refreshing?: boolean;
  /** onRefresh — 重新读取调度、总览、监控、告警和生命周期。 */
  onRefresh: () => void;
}

function formatMetric(value: number | null | undefined, suffix = ''): string {
  return value === null || value === undefined ? '暂无数据' : `${value.toFixed(2)}${suffix}`;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '未计划';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('zh-CN', { hour12: false });
}

function buildEvidenceStages({
  schedulerTask,
  schedulerError,
  overview,
  monitoringSnapshot,
  alerts,
  selectedAlert,
  decision,
}: Omit<LoadForecastStoryRailProps, 'slot' | 'schedulerLoading' | 'refreshing' | 'onRefresh'>): EvidenceStage[] {
  const production = overview?.production ?? monitoringSnapshot?.production ?? null;
  const activeAlert = selectedAlert ?? alerts.find((item) => item.status !== 'closed') ?? null;
  const coverageRate = production?.coverage_rate ?? null;
  const validCycles = production?.valid_cycle_count ?? null;
  const hasSufficientEvidence = coverageRate !== null
    && coverageRate >= 0.9
    && validCycles !== null
    && validCycles >= 3;

  const schedulingStage: EvidenceStage = !schedulerTask
    ? {
      key: 'schedule',
      label: '定时调度',
      detail: schedulerError || '当前场景尚未找到负荷预测调度任务',
      tone: schedulerError ? 'warning' : 'neutral',
      icon: <ClockCircleOutlined />,
    }
    : schedulerTask.status === 'failed'
      ? {
        key: 'schedule',
        label: '定时调度',
        detail: `任务失败，最近计划 ${formatDateTime(schedulerTask.next_scheduled_time)}`,
        tone: 'critical',
        icon: <ClockCircleOutlined />,
      }
      : schedulerTask.status === 'running'
        ? {
          key: 'schedule',
          label: '定时调度',
          detail: `已启用，下次 ${formatDateTime(schedulerTask.next_scheduled_time)}`,
          tone: 'healthy',
          icon: <ClockCircleOutlined />,
        }
        : {
          key: 'schedule',
          label: '定时调度',
          detail: '任务已停止，尚不会产生新的预测周期',
          tone: 'neutral',
          icon: <ClockCircleOutlined />,
        };

  const executionStage: EvidenceStage = !schedulerTask || !schedulerTask.last_execution
    ? {
      key: 'execution',
      label: '运行回执',
      detail: '尚无可读取的最近执行结果',
      tone: 'neutral',
      icon: <DeploymentUnitOutlined />,
    }
    : schedulerTask.last_execution === 'success'
      ? {
        key: 'execution',
        label: '运行回执',
        detail: `最近任务成功于 ${formatDateTime(schedulerTask.last_execution_time)}`,
        tone: 'healthy',
        icon: <DeploymentUnitOutlined />,
      }
      : schedulerTask.last_execution === 'skipped'
        ? {
          key: 'execution',
          label: '运行回执',
          detail: '本周期跳过，通常等待真实值或历史预测补齐',
          tone: 'pending',
          icon: <DeploymentUnitOutlined />,
        }
        : {
          key: 'execution',
          label: '运行回执',
          detail: `最近任务失败于 ${formatDateTime(schedulerTask.last_execution_time)}`,
          tone: 'critical',
          icon: <DeploymentUnitOutlined />,
        };

  const backfillStage: EvidenceStage = !production
    ? {
      key: 'backfill',
      label: '真值回填',
      detail: '尚无生产模型指标，无法确认回填进度',
      tone: 'neutral',
      icon: <AuditOutlined />,
    }
    : hasSufficientEvidence
      ? {
        key: 'backfill',
        label: '真值回填',
        detail: `有效周期 ${validCycles}，覆盖率 ${formatMetric((coverageRate ?? 0) * 100, '%')}`,
        tone: 'healthy',
        icon: <AuditOutlined />,
      }
      : {
        key: 'backfill',
        label: '真值回填',
        detail: `指标预热中，有效周期 ${validCycles ?? 0}，覆盖率 ${formatMetric(coverageRate === null ? null : coverageRate * 100, '%')}`,
        tone: 'pending',
        icon: <AuditOutlined />,
      };

  const monitoringStage: EvidenceStage = !production
    ? {
      key: 'monitoring',
      label: '精度监控',
      detail: '尚无生产模型监控快照',
      tone: 'neutral',
      icon: <BarChartOutlined />,
    }
    : {
      key: 'monitoring',
      label: '精度监控',
      detail: `滚动 WMAPE ${formatMetric(production.rolling_wmape ?? production.rolling_mape, '%')}`,
      tone: production.status === 'degraded' ? 'critical' : production.status === 'warning' ? 'warning' : hasSufficientEvidence ? 'healthy' : 'pending',
      icon: <BarChartOutlined />,
    };

  const alertStage: EvidenceStage = !activeAlert
    ? {
      key: 'alert',
      label: '退化告警',
      detail: hasSufficientEvidence ? '当前没有未关闭的精度退化告警' : '指标证据不足，尚不评价退化状态',
      tone: hasSufficientEvidence ? 'healthy' : 'pending',
      icon: <WarningOutlined />,
    }
    : {
      key: 'alert',
      label: '退化告警',
      detail: `${activeAlert.severity === 'critical' ? '严重' : '警告'}，退化 ${activeAlert.degradation_pct.toFixed(2)}%`,
      tone: activeAlert.severity === 'critical' ? 'critical' : 'warning',
      icon: <WarningOutlined />,
    };

  const diagnosisStage: EvidenceStage = !activeAlert
    ? {
      key: 'diagnosis',
      label: '根因与仲裁',
      detail: '无待处置告警',
      tone: 'neutral',
      icon: <FileSearchOutlined />,
    }
    : !activeAlert.rca_report_id
      ? {
        key: 'diagnosis',
        label: '根因与仲裁',
        detail: '等待触发 RCA 根因分析',
        tone: 'pending',
        icon: <FileSearchOutlined />,
      }
      : !decision
        ? {
          key: 'diagnosis',
          label: '根因与仲裁',
          detail: 'RCA 已就绪，等待生成恢复建议',
          tone: 'pending',
          icon: <FileSearchOutlined />,
        }
        : {
          key: 'diagnosis',
          label: '根因与仲裁',
          detail: decision.channel === 'shadow_switch' ? '已建议通道 A 影子切换' : '仲裁要求继续观察',
          tone: decision.channel === 'shadow_switch' ? 'warning' : 'pending',
          icon: <FileSearchOutlined />,
        };

  const recoveryStage: EvidenceStage = !decision
    ? {
      key: 'recovery',
      label: '恢复与审计',
      detail: '尚无恢复决策或部署切换事件',
      tone: 'neutral',
      icon: <SafetyCertificateOutlined />,
    }
    : decision.status === 'succeeded' && decision.switch_event_id
      ? {
        key: 'recovery',
        label: '恢复与审计',
        detail: `通道 A 已执行，审计 ${decision.switch_event_id}`,
        tone: 'healthy',
        icon: <SafetyCertificateOutlined />,
      }
      : decision.status === 'failed'
        ? {
          key: 'recovery',
          label: '恢复与审计',
          detail: '恢复操作失败，请检查决策原因和部署状态',
          tone: 'critical',
          icon: <SafetyCertificateOutlined />,
        }
        : decision.status === 'rolled_back'
          ? {
            key: 'recovery',
            label: '恢复与审计',
            detail: '恢复决策已回滚，请查看部署审计',
            tone: 'warning',
            icon: <SafetyCertificateOutlined />,
          }
          : {
            key: 'recovery',
            label: '恢复与审计',
            detail: decision.channel === 'shadow_switch' ? '通道 A 等待人工二次确认' : '观察通道执行中',
            tone: 'pending',
            icon: <SafetyCertificateOutlined />,
          };

  return [schedulingStage, executionStage, backfillStage, monitoringStage, alertStage, diagnosisStage, recoveryStage];
}

const LoadForecastStoryRail: React.FC<LoadForecastStoryRailProps> = (props) => {
  const navigate = useNavigate();
  const stages = buildEvidenceStages(props);

  return (
    <section className="load-forecast-story-rail" aria-label="负荷预测运行证据状态带">
      <div className="story-rail-heading">
        <div>
          <Text className="story-rail-caption">负荷预测运行证据</Text>
          <Text className="story-rail-description">
            场景 <Text code>{props.slot}</Text> 的当前证据链。状态带只反映已读取的数据，不替代实际运行审计。
          </Text>
        </div>
        <Space size={4} wrap>
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/algorithm-deployment?tab=scheduler&slot=${encodeURIComponent(props.slot)}`)}
          >
            查看调度
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => navigate(`/algorithm-deployment?tab=model&slot=${encodeURIComponent(props.slot)}`)}
          >
            查看部署
          </Button>
          <Tooltip title="重新读取调度、指标、告警、RCA 和部署审计">
            <Button type="text" size="small" icon={<ReloadOutlined />} loading={props.refreshing} onClick={props.onRefresh} aria-label="刷新运行证据" />
          </Tooltip>
        </Space>
      </div>

      {props.schedulerLoading ? (
        <div className="story-rail-loading" aria-label="加载运行证据">
          {Array.from({ length: 7 }, (_, index) => <Skeleton.Button key={index} active size="small" block />)}
        </div>
      ) : (
        <div className="story-rail-stages">
          {stages.map((stage) => (
            <article key={stage.key} className="story-stage" data-tone={stage.tone}>
              <div className="story-stage-title">
                <span className="story-stage-icon" aria-hidden="true">{stage.icon}</span>
                <Text strong>{stage.label}</Text>
              </div>
              <Text className="story-stage-detail">{stage.detail}</Text>
              <Tag className="story-stage-tag" bordered={false}>{stage.tone === 'healthy' ? '已证实' : stage.tone === 'critical' ? '需处理' : stage.tone === 'warning' ? '需关注' : stage.tone === 'pending' ? '等待证据' : '未就绪'}</Tag>
            </article>
          ))}
        </div>
      )}
    </section>
  );
};

export default LoadForecastStoryRail;
// @AI_GENERATED: end
