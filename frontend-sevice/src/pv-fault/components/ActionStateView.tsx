// @AI_GENERATED
/**
 * 共享阶段 / 动作状态视图：渲染 §22.1 十个动作状态。
 *
 * 设计依据：design.md §22.1、§23（一级结论 → scope 与证据 → 主动作 → 原因/影响/下一步 → 诊断详情）、
 * §28.1（结构化 Skeleton、教学空态、内联 Alert + 诊断抽屉）；requirements.md R2.1–R2.4、R2.8–R2.13。
 *
 * 约束：分支只基于 descriptor.state / disabledReason 枚举名，中文文案统一取自 stateVocabulary。
 * 原始 JSON、correlation_id、scope 明细放入二级「诊断详情」折叠区，不占一级信息层。
 */

import type { ReactNode } from 'react';
import { Alert, Button, Collapse, Empty, Skeleton, Space, Tag, Tooltip } from 'antd';
import type { StageStateDescriptor } from '../types/scope';
import {
  ACTION_STATE_ALERT_TYPE,
  ACTION_STATE_COPY,
  CROSS_CUTTING_COPY,
  DISABLED_REASON_COPY,
} from '../copy/stateVocabulary';

export interface ActionStateViewProps {
  descriptor: StageStateDescriptor;
  /** 该状态下的唯一主动作（可选）。 */
  primaryAction?: ReactNode;
  /** 刷新当前项目回调：scope 冲突 / 安全失败 / 记录缺失时提供“刷新当前项目”入口。 */
  onRefresh?: () => void;
}

function Markers({ descriptor }: { descriptor: StageStateDescriptor }): JSX.Element | null {
  const markers = descriptor.markers ?? [];
  if (markers.length === 0) return null;
  return (
    <Space size={4} wrap style={{ marginBottom: 8 }}>
      {markers.map((marker) => (
        <Tooltip key={marker} title={CROSS_CUTTING_COPY[marker].hint}>
          <Tag color={marker === 'CANCELLED' ? 'default' : 'orange'}>{CROSS_CUTTING_COPY[marker].label}</Tag>
        </Tooltip>
      ))}
    </Space>
  );
}

function DiagnosticsDrawer({ descriptor }: { descriptor: StageStateDescriptor }): JSX.Element | null {
  const hasRaw = descriptor.raw !== undefined && descriptor.raw !== null;
  if (!hasRaw && !descriptor.correlationId && !descriptor.scope) return null;
  const scopeText = descriptor.scope
    ? `project_id=${descriptor.scope.projectId || '-'}` +
      (descriptor.scope.slot ? ` slot=${descriptor.scope.slot}` : '') +
      (descriptor.scope.datasetVersionId ? ` dataset_version_id=${descriptor.scope.datasetVersionId}` : '')
    : null;
  return (
    <Collapse
      ghost
      size="small"
      style={{ marginTop: 8 }}
      items={[
        {
          key: 'diagnostics',
          label: '诊断详情',
          children: (
            <div style={{ fontSize: 12, color: '#666' }}>
              {scopeText && (
                <div style={{ marginBottom: 4 }}>
                  <b>scope：</b>
                  {scopeText}
                </div>
              )}
              {descriptor.correlationId && (
                <div style={{ marginBottom: 4 }}>
                  <b>correlation_id：</b>
                  {descriptor.correlationId}
                </div>
              )}
              {hasRaw && (
                <pre style={{ maxHeight: 240, overflow: 'auto', background: '#f5f5f5', padding: 8, borderRadius: 4 }}>
                  {typeof descriptor.raw === 'string' ? descriptor.raw : JSON.stringify(descriptor.raw, null, 2)}
                </pre>
              )}
            </div>
          ),
        },
      ]}
    />
  );
}

function ReasonBlock({ descriptor }: { descriptor: StageStateDescriptor }): JSX.Element {
  const { reason, currentValue, threshold, nextAction, disabledReason } = descriptor;
  const fallbackHint = ACTION_STATE_COPY[descriptor.state].hint;
  return (
    <div>
      <div>{reason || fallbackHint}</div>
      {(currentValue !== undefined && currentValue !== null) || (threshold !== undefined && threshold !== null) ? (
        <div style={{ marginTop: 4, fontSize: 12 }}>
          {currentValue !== undefined && currentValue !== null && <span>当前值：{String(currentValue)}　</span>}
          {threshold !== undefined && threshold !== null && <span>门槛：{String(threshold)}</span>}
        </div>
      ) : null}
      {disabledReason && (
        <div style={{ marginTop: 4, fontSize: 12 }}>
          <b>{DISABLED_REASON_COPY[disabledReason].label}：</b>
          {DISABLED_REASON_COPY[disabledReason].recovery}
        </div>
      )}
      {nextAction && (
        <div style={{ marginTop: 4, fontSize: 12 }}>
          <b>下一步：</b>
          {nextAction}
        </div>
      )}
    </div>
  );
}

/** 是否为需要“刷新当前项目”的状态。 */
function shouldOfferRefresh(descriptor: StageStateDescriptor): boolean {
  if (descriptor.state === 'fail_closed' || descriptor.state === 'recoverable_failure') return true;
  if (descriptor.disabledReason === 'scope_mismatch') return true;
  const markers = descriptor.markers ?? [];
  return markers.includes('STALE') || markers.includes('BACKEND_RECORD_MISSING');
}

export function ActionStateView({ descriptor, primaryAction, onRefresh }: ActionStateViewProps): JSX.Element {
  const copy = ACTION_STATE_COPY[descriptor.state];
  const title = descriptor.title || copy.label;

  // 加载态：结构化 Skeleton。
  if (descriptor.state === 'loading') {
    return (
      <div>
        <Markers descriptor={descriptor} />
        <Skeleton active paragraph={{ rows: 3 }} />
      </div>
    );
  }

  // 初始空态：教学空态 + 唯一主动作。
  if (descriptor.state === 'initial_empty') {
    return (
      <div>
        <Markers descriptor={descriptor} />
        <Empty description={<div>{descriptor.reason || copy.hint}</div>}>
          {primaryAction}
        </Empty>
        <DiagnosticsDrawer descriptor={descriptor} />
      </div>
    );
  }

  const refreshButton =
    onRefresh && shouldOfferRefresh(descriptor) ? (
      <Button size="small" onClick={onRefresh}>
        刷新当前项目
      </Button>
    ) : null;

  return (
    <div>
      <Markers descriptor={descriptor} />
      <Alert
        type={ACTION_STATE_ALERT_TYPE[descriptor.state]}
        showIcon
        message={title}
        description={<ReasonBlock descriptor={descriptor} />}
        action={
          primaryAction || refreshButton ? (
            <Space direction="vertical" size={4}>
              {primaryAction}
              {refreshButton}
            </Space>
          ) : undefined
        }
      />
      <DiagnosticsDrawer descriptor={descriptor} />
    </div>
  );
}

export default ActionStateView;

// @AI_GENERATED: end
