// @AI_GENERATED
/**
 * 项目工作台共享类型：scope、动作状态、禁用原因、readiness 与统一错误响应。
 *
 * 设计依据：design.md §22.1（十个动作状态）、§22（横切状态）、§24.2（五类禁用原因）、
 * §25（六个 readiness 状态）、§26.5（统一错误响应）；requirements.md R1、R2。
 *
 * 约束：分支只允许基于 reason_code / 枚举名，禁止基于中文展示文案（design §28.4）。
 * 因 tsconfig 开启 erasableSyntaxOnly，这里用字符串联合类型 + as const 常量，不用 enum。
 */

/** 项目 scope（前端 camelCase；与后端 snake_case 回显互转见 scopedApi）。 */
export interface ProjectScope {
  projectId: string;
  slot?: string;
  datasetVersionId?: string;
}

/** 后端响应回显的 scope 片段（snake_case）。 */
export interface ScopeEcho {
  project_id?: string;
  slot?: string;
  dataset_version_id?: string;
}

/** §22.1 十个通用动作状态。 */
export type ActionState =
  | 'initial_empty'
  | 'loading'
  | 'ready'
  | 'waiting_human'
  | 'blocked'
  | 'insufficient_data'
  | 'read_only'
  | 'recoverable_failure'
  | 'fail_closed'
  | 'completed';

export const ACTION_STATES: readonly ActionState[] = [
  'initial_empty',
  'loading',
  'ready',
  'waiting_human',
  'blocked',
  'insufficient_data',
  'read_only',
  'recoverable_failure',
  'fail_closed',
  'completed',
] as const;

/** §22 横切状态：叠加在任一动作状态之上，不替换枚举本身。 */
export type CrossCuttingMarker = 'CANCELLED' | 'STALE' | 'BACKEND_RECORD_MISSING';

export const CROSS_CUTTING_MARKERS: readonly CrossCuttingMarker[] = [
  'CANCELLED',
  'STALE',
  'BACKEND_RECORD_MISSING',
] as const;

/** §24.2 五类禁用原因（后端门控 category）。 */
export type DisabledReasonType =
  | 'permission_denied'
  | 'business_gate_blocked'
  | 'read_only'
  | 'sandbox_only'
  | 'scope_mismatch';

export const DISABLED_REASON_TYPES: readonly DisabledReasonType[] = [
  'permission_denied',
  'business_gate_blocked',
  'read_only',
  'sandbox_only',
  'scope_mismatch',
] as const;

/** §25 六个 readiness 状态。 */
export type ReadinessStatus =
  | 'ready'
  | 'experiment_only'
  | 'needs_mapping'
  | 'needs_labels'
  | 'insufficient_data'
  | 'unsupported';

export const READINESS_STATUSES: readonly ReadinessStatus[] = [
  'ready',
  'experiment_only',
  'needs_mapping',
  'needs_labels',
  'insufficient_data',
  'unsupported',
] as const;

/** §26.5 统一错误响应体（不含堆栈 / 凭据 / 机器绝对路径）。 */
export interface ScopedErrorPayload {
  reason_code: string;
  message: string;
  next_action?: string;
  scope?: ScopeEcho & Record<string, unknown>;
  retryable?: boolean;
  correlation_id?: string;
  current_value?: unknown;
  required_value?: unknown;
  category?: DisabledReasonType;
}

/**
 * 单页阶段状态描述。页面按 §23「一级结论 → scope 与证据 → 主动作 → 原因/影响/下一步 → 诊断详情」渲染。
 * 每一种页面情形都必须归到 ActionState 十枚举之一（design §23 归类表）。
 */
export interface StageStateDescriptor {
  /** §22.1 十个枚举之一（必填）。 */
  state: ActionState;
  /** 一级中文结论标题。 */
  title?: string;
  /** 中文原因说明。 */
  reason?: string;
  /** 门控当前值（如未满足门槛时的实际值）。 */
  currentValue?: string | number | null;
  /** 门控门槛 / 所需值。 */
  threshold?: string | number | null;
  /** 最短下一步文案。 */
  nextAction?: string;
  /** 下一步目标路由（可选）。 */
  nextActionHref?: string;
  /** 禁用原因分类（当 state=blocked/read_only 时用于区分表现与恢复方式）。 */
  disabledReason?: DisabledReasonType;
  /** 横切标注。 */
  markers?: CrossCuttingMarker[];
  /** 当前 scope（用于二级诊断展示）。 */
  scope?: ProjectScope;
  /** 诊断关联 ID。 */
  correlationId?: string;
  /** 原始 JSON，仅进入二级诊断抽屉，不占一级信息层。 */
  raw?: unknown;
}

// @AI_GENERATED: end
