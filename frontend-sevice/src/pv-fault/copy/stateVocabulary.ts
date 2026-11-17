// @AI_GENERATED
/**
 * 集中状态文案模块（中文优先）。
 *
 * 设计依据：design.md §28.4——§22.1 十个动作状态、§22 横切状态、§24.2 五类禁用原因、
 * §25 六个 readiness 状态、生命周期阶段名，其展示文案集中在此单一模块，页面通过键引用，
 * 不在各组件内散落字符串字面量；同一状态跨页显示同一措辞。
 *
 * 约束：
 * - 分支只允许基于 reason_code / 枚举名，禁止基于这里的中文文案做条件判断。
 * - 本期中文优先，不改动 locales/zh.json / en.json；键结构与未来 `pvFaultProject`
 *   i18n 命名空间同形，迁移时机械搬移即可。
 */

import type {
  ActionState,
  CrossCuttingMarker,
  DisabledReasonType,
  ReadinessStatus,
} from '../types/scope';

/** 动作状态展示文案（label 一级结论，hint 辅助说明）。 */
export const ACTION_STATE_COPY: Record<ActionState, { label: string; hint: string }> = {
  initial_empty: { label: '初始空态', hint: '缺少上游对象，请先补齐前置项。' },
  loading: { label: '加载中', hint: '正在读取当前 scope 的状态，请稍候。' },
  ready: { label: '可开始', hint: '前置条件已满足，可执行主动作。' },
  waiting_human: { label: '等待人工', hint: '流程正在等待人工审核或审批。' },
  blocked: { label: '门控阻断', hint: '存在未满足的门槛或缺失证据，暂不能继续。' },
  insufficient_data: { label: '数据不足', hint: '日期 / 设备 / 类别 / 采样或标签覆盖不足。' },
  read_only: { label: '只读', hint: '当前页面或角色只读；如需写入请前往授权入口。' },
  recoverable_failure: { label: '可恢复失败', hint: '已保留输入与失败证据，可重试或修改后重跑。' },
  fail_closed: { label: '安全失败', hint: 'scope / 证据 / 治理冲突，已拒绝渲染可疑结果。' },
  completed: { label: '已完成', hint: '已产出真实产物，可进入下一阶段。' },
};

/** 动作状态 → Ant Design Alert 类型（表现映射，不用于分支）。 */
export const ACTION_STATE_ALERT_TYPE: Record<ActionState, 'info' | 'success' | 'warning' | 'error'> = {
  initial_empty: 'info',
  loading: 'info',
  ready: 'info',
  waiting_human: 'warning',
  blocked: 'warning',
  insufficient_data: 'warning',
  read_only: 'info',
  recoverable_failure: 'error',
  fail_closed: 'error',
  completed: 'success',
};

/** 横切状态展示文案。 */
export const CROSS_CUTTING_COPY: Record<CrossCuttingMarker, { label: string; hint: string }> = {
  CANCELLED: { label: '已取消', hint: '当前任务 / execution 已被主动终止；部分证据保留并标注取消。' },
  STALE: { label: '结论已过期', hint: '依赖的数据版本 / 画像 / 路径合同 / 回执已更新，勿当作当前事实。' },
  BACKEND_RECORD_MISSING: { label: '后端记录缺失', hint: '前端持有 ID 但读不到对应记录；不猜测、不用相邻对象补位。' },
};

/** 五类禁用原因文案（表现 + 恢复方式）。 */
export const DISABLED_REASON_COPY: Record<DisabledReasonType, { label: string; recovery: string }> = {
  permission_denied: { label: '无权限', recovery: '申请对应角色授权后重试。' },
  business_gate_blocked: { label: '业务门禁', recovery: '补齐映射 / 标签 / 复验或 provenance 后重试。' },
  read_only: { label: '只读', recovery: '转到 Sandbox 或授权写入口。' },
  sandbox_only: { label: '仅 Sandbox', recovery: '可继续实验；production 动作保持禁用。' },
  scope_mismatch: { label: 'scope 冲突', recovery: '清空旧状态并重新读取当前项目。' },
};

/** 六个 readiness 状态文案。 */
export const READINESS_COPY: Record<ReadinessStatus, { label: string; hint: string }> = {
  ready: { label: '可用', hint: '满足当前路径输入与预检合同；不代表生产 / 候选 / Promote 资格。' },
  experiment_only: { label: '仅实验', hint: '可做 experiment 或 Sandbox；production 保持禁用。' },
  needs_mapping: { label: '待映射', hint: '字段 / 时区 / 实体 / 单位或标签粒度尚未确认。' },
  needs_labels: { label: '缺标签', hint: '可形成样本但缺少当前路径粒度真值。' },
  insufficient_data: { label: '数据不足', hint: '日期 / 设备 / 类别或采样覆盖不足；不降低 strict 合同。' },
  unsupported: { label: '不支持', hint: '缺少当前路径不可替代的基础条件；建议换数据或换路径。' },
};

/**
 * readiness 的**评估失败**标记文案。
 *
 * 刻意不并入 `READINESS_COPY` / `ReadinessStatus`：design §25 明确 readiness 只有六态，
 * `unavailable` 不是第七态，而是"评估器不可用"这一独立事实（后端 fail-closed 的产物）。
 * 前端按 **不可推进** 渲染，并给出诊断入口，避免把它显示成"未接入数据"掩盖真实故障。
 */
export const READINESS_UNAVAILABLE = {
  status: 'unavailable',
  label: '可用性未知',
  hint: '数据可用性评估失败（画像 / 路径合同 / 实现异常）。已按不可推进处理，请展开诊断详情。',
} as const;

/** §22 生命周期阶段（计算得出）的中文展示名。 */
export const LIFECYCLE_STAGE_LABEL: Record<string, string> = {
  UNCONFIGURED: '未配置',
  DATA_NEEDS_MAPPING: '待映射',
  DATA_NEEDS_LABELS: '缺标签',
  DATA_INSUFFICIENT: '数据不足',
  /** 该数据不支持这条诊断路径（readiness=unsupported）。 */
  PATH_UNSUPPORTED: '该路径不适用',
  /**
   * 数据可用性**评估失败**（非 §25 六态之一）。
   * 后端在评估器抛异常时给出 `readiness_status="unavailable"`，按不可推进处理（fail-closed）。
   */
  DATA_READINESS_UNKNOWN: '可用性未知',
  DATA_READY: '数据就绪',
  WORKFLOW_DRAFT: '工作流草稿',
  PREFLIGHT_BLOCKED: '预检阻断',
  READY_TO_RUN: '可运行',
  RUNNING: '运行中',
  RUN_FAILED: '运行失败',
  EXPERIMENT_RESULT: '实验结果',
  GOVERNANCE_CANDIDATE: '可治理候选',
  VERIFYING: '复验中',
  VERIFICATION_FAILED: '复验未过',
  VERIFIED: '复验通过',
  ROLLING_MODEL_SELECTED: '已设检测模型',
  DETECTING: '检测中',
  DETECTION_BLOCKED: '检测阻断',
  REVIEW_PENDING: '待审核',
  REVIEW_COMPLETED: '审核完成',
  ADMITTED: '已入账',
  SNAPSHOT_READY: '快照就绪',
  RETRAINING: '再训练中',
};

/** 光伏适配器的生命周期阶段名（design §11）。 */
export const PV_STAGE_NAMES = {
  data: '数据与兼容性',
  workflow: '工作流与运行',
  governance: '模型与治理',
  operations: '检测与回放',
  review: '审核与精度',
  cumulative: '累计训练集',
} as const;

export type PvStageKey = keyof typeof PV_STAGE_NAMES;

// @AI_GENERATED: end
