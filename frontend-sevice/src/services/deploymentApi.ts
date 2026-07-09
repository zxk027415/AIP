// @AI_GENERATED
/**
 * deploymentApi.ts — 算法部署重构 API 客户端
 *
 * 封装以下三组后端接口，供"算法部署页面"（AlgorithmDeploymentPage）及
 * 关联子面板消费。风格与 `workflowEnhancedApi.ts` 一致：复用共享 axios
 * 实例 `./api`（baseURL='/api'，响应拦截器已自动 unwrap `response.data`），
 * 因此每个方法直接返回解析后的响应体。
 *
 * 相关 spec：`.kiro/specs/algorithm-deployment-refactor/`
 *   - Requirements 1.1（统一入口）、2.1（调度任务摘要）、3.1（槽位视图）
 *   - Task 13.2 前端 API 客户端创建
 *
 * 端点一览（相对 baseURL '/api'）：
 *   部署槽位：
 *     GET  /deployment/slots
 *     GET  /deployment/slots/{slot}/versions
 *     POST /deployment/slots/{slot}/switch
 *     POST /deployment/slots/{slot}/rollback
 *     GET  /deployment/slots/{slot}/switch-log
 *     GET  /deployment/slots/{slot}/config
 *     PUT  /deployment/slots/{slot}/config
 *   调度任务：
 *     GET  /scheduler/tasks
 *     POST /scheduler/tasks
 *     GET  /scheduler/tasks/{task_id}
 *     POST /scheduler/tasks/{task_id}/start
 *     POST /scheduler/tasks/{task_id}/stop
 *   数据库健康：
 *     GET  /system/db-health
 */

import api from './api';

// ===========================================================================
// 类型定义 —— 部署槽位（Deployment Slot）
// ===========================================================================

/**
 * ModelVersionView — 模型版本视图（前端展示格式）
 *
 * 与后端 `services/deployment/models.py::ModelVersion` 对齐，但由 API 层
 * 额外补充 `latest_mape` 字段（语义等同 `accuracy_score`），便于 production/
 * shadow 卡片共用渲染逻辑。
 */
export interface ModelVersionView {
  /** workflow_id — 关联的工作流/模板唯一 ID */
  workflow_id: string;
  /** version_tag — 版本标签（人类可读，如 "v2.1"） */
  version_tag: string;
  /** status — 状态：production | shadow | retired */
  status: 'production' | 'shadow' | 'retired';
  /** deployed_at — 部署/注册时间 ISO 8601 */
  deployed_at: string;
  /** accuracy_score — 最新精度评分（本项目为 MAPE，越低越好；None 表示尚未评估） */
  accuracy_score: number | null;
  /** latest_mape — production 展示字段，与 accuracy_score 语义相同 */
  latest_mape: number | null;
  /** consecutive_better_days — 连续优于当前 production 的天数（切换资格判定） */
  consecutive_better_days: number;
  /** source_run_id — 来源实验 run ID（可选，供审计溯源） */
  source_run_id?: string | null;
  /** source_candidate_id — 来源候选 ID（可选，供审计溯源） */
  source_candidate_id?: string | null;
}

/**
 * VersionHistoryItem — 版本历史条目
 *
 * `GET /deployment/slots/{slot}/versions` 返回列表条目，比 ModelVersionView
 * 额外附带 `role` 字段方便前端渲染状态标签。
 */
export interface VersionHistoryItem extends ModelVersionView {
  /** role — 角色标签：production（当前生产）| shadow（在测）| retired（历史退役） */
  role: 'production' | 'shadow' | 'retired';
}

/**
 * DeploymentSlotView — 部署槽位视图
 *
 * `GET /deployment/slots` 返回的 slots 字典值；shadow_models 已由后端按
 * accuracy_score 降序（Requirement 3.4 / Property 3）。
 * prelaunch_models 按入池时间升序，每个独立跟生产比较（安全闸门）。
 */
export interface DeploymentSlotView {
  /** slot — 槽位名称（分区键），如 "load_forecast"、"pv_fault"、"default" */
  slot: string;
  /** production_model — 当前生产模型；None 表示尚未上线任何模型 */
  production_model: ModelVersionView | null;
  /** shadow_models — 在测的影子模型列表（按精度降序，锦标赛竞争）*/
  shadow_models: ModelVersionView[];
  /** prelaunch_models — 预上线池（每个独立安全观察，不互相竞争）*/
  prelaunch_models: PrelaunchModelView[];
  auto_switch_enabled: boolean;
  /** switch_observation_days — 切换观察天数（旧名 evaluation_window_days）*/
  switch_observation_days: number;
  /** evaluation_window_days — 已废弃 alias，值同 switch_observation_days */
  evaluation_window_days: number;
  cooldown_hours: number;
  threshold_mape: number | null;
  /** training_window_days — 训练窗口天数（跟 AutoResearch train_days 一致）*/
  training_window_days: number;
  /** max_shadow_slots — 影子池上限，默认 3 */
  max_shadow_slots: number;
  /** max_prelaunch_slots — 预上线池上限，默认 2 */
  max_prelaunch_slots: number;
  updated_at: string;
}

/**
 * SwitchEventView — 切换事件视图（append-only 审计日志条目）
 *
 * 与后端 `SwitchEvent` 完全一致；`rollback_of` 非空时表示这是一条回滚事件，
 * 值为被回滚的原切换事件 event_id。
 */
export interface SwitchEventView {
  /** event_id — 事件唯一 ID */
  event_id: string;
  /** slot — 槽位 */
  slot: string;
  /** trigger_type — 触发类型：auto（自动切换）| manual（人工切换） */
  trigger_type: 'auto' | 'manual';
  /** switch_time — 切换时间 ISO 8601 */
  switch_time: string;
  /** from_workflow_id — 原 production 的 workflow_id */
  from_workflow_id: string;
  /** from_version_tag — 原 production 的版本标签 */
  from_version_tag: string;
  /** to_workflow_id — 新 production 的 workflow_id */
  to_workflow_id: string;
  /** to_version_tag — 新 production 的版本标签 */
  to_version_tag: string;
  /** pre_switch_mape — 切换前 MAPE（可选） */
  pre_switch_mape: number | null;
  /** post_switch_mape — 切换后 MAPE（可选，后置评估补写） */
  post_switch_mape: number | null;
  /** reason — 切换原因备注（人类可读） */
  reason: string;
  /** rollback_of — 若为回滚事件，指向被回滚的 event_id */
  rollback_of: string | null;
}

/**
 * SlotConfigView — 自动切换配置视图
 *
 * `GET/PUT /deployment/slots/{slot}/config` 返回体（含新增字段）。
 */
export interface SlotConfigView {
  slot: string;
  auto_switch_enabled: boolean;
  switch_observation_days: number;
  evaluation_window_days: number;  // 已废弃 alias，值同 switch_observation_days
  cooldown_hours: number;
  threshold_mape: number | null;
  training_window_days: number;
  max_shadow_slots: number;
  max_prelaunch_slots: number;
  updated_at: string;
}

/**
 * SwitchRequest — POST /deployment/slots/{slot}/switch 请求体
 */
export interface SwitchRequest {
  /** target_workflow_id — 必填，要提升为 production 的影子模型 workflow_id */
  target_workflow_id: string;
  /** trigger_type — 触发类型：manual | auto，默认 manual */
  trigger_type?: 'manual' | 'auto';
  /** reason — 切换原因备注（可选） */
  reason?: string;
  /** pre_switch_mape — 切换前精度覆盖值（可选，未提供则取 production.accuracy_score） */
  pre_switch_mape?: number | null;
  /** force — 是否绕过冷却期检查（人工操作，默认 false） */
  force?: boolean;
}

/**
 * RollbackRequest — POST /deployment/slots/{slot}/rollback 请求体
 */
export interface RollbackRequest {
  /** reason — 回滚原因备注（可选，默认 "manual_rollback"） */
  reason?: string;
}

/**
 * SlotConfigUpdate — PUT /deployment/slots/{slot}/config 请求体（局部更新）
 *
 * 仅设置传入的非 undefined 字段；null 表示"清空"该字段（如清空阈值）。
 * 字段含义说明：
 *   switch_observation_days  — 切换观察天数（旧名 evaluation_window_days，后端 alias 兼容）
 *   training_window_days     — 训练窗口天数，跟 AutoResearch train_days 语义一致
 *   max_shadow_slots         — 影子池上限（每日 cron 最多跑几个 shadow）
 *   max_prelaunch_slots      — 预上线池上限（最多同时观察几个 prelaunch）
 */
export interface SlotConfigUpdate {
  auto_switch_enabled?: boolean;
  /** switch_observation_days — 切换观察天数（shadow 连续多少天优于生产才建议切换）*/
  switch_observation_days?: number;
  /** evaluation_window_days — 已废弃 alias，后端会映射到 switch_observation_days */
  evaluation_window_days?: number;
  cooldown_hours?: number;
  threshold_mape?: number | null;
  /** training_window_days — 训练窗口天数（每天训练用最近 N 天历史数据，默认 30）*/
  training_window_days?: number;
  /** max_shadow_slots — 影子池上限，默认 3 */
  max_shadow_slots?: number;
  /** max_prelaunch_slots — 预上线池上限，默认 2 */
  max_prelaunch_slots?: number;
}

// ===========================================================================
// 类型定义 —— Prelaunch（预上线）
// ===========================================================================

/**
 * PrelaunchMeta — 预上线专属元数据（挂在 ModelVersionView.prelaunch_meta 上）
 *
 * 只有 status="prelaunch" 的模型才有非空的 prelaunch_meta。
 * 预上线语义：每个独立跟生产比较，MAPE ≤ production*(1+tolerance) + 期满 → 毕业为 shadow。
 */
export interface PrelaunchMeta {
  /** candidate_id — 来源候选 ID（从复验池过来的是哪条候选）*/
  candidate_id: string;
  /** started_at — 观察开始时间 ISO 8601 */
  started_at: string;
  /** observation_days — 观察期天数，默认 7 */
  observation_days: number;
  /** graduate_tolerance_pct — 毕业容差百分比，默认 5
   *  预上线 MAPE ≤ production * (1 + tolerance/100) 才能毕业 */
  graduate_tolerance_pct: number;
  /** evaluated_cycles — 已评估天数（每日 backfill 后 +1）*/
  evaluated_cycles: number;
  /** baseline_mape_at_entry — 入池时的生产 MAPE 快照（审计用）*/
  baseline_mape_at_entry: number | null;
  /** current_rolling_mape — 当前预上线滚动 MAPE（每日 backfill 更新）*/
  current_rolling_mape: number | null;
  /** production_rolling_mape — 当前生产滚动 MAPE（每日 backfill 同步）*/
  production_rolling_mape: number | null;
  source_run_id?: string | null;
  note: string;
}

/**
 * PrelaunchModelView — 预上线模型视图（含完整 prelaunch_meta）
 */
export interface PrelaunchModelView {
  workflow_id: string;
  version_tag: string;
  status: 'prelaunch' | 'retired';
  deployed_at: string;
  accuracy_score: number | null;
  source_run_id?: string | null;
  source_candidate_id?: string | null;
  prelaunch_meta: PrelaunchMeta | null;
}

/**
 * PrelaunchEnterRequest — POST /deployment/slots/{slot}/prelaunches 请求体
 */
export interface PrelaunchEnterRequest {
  /** candidate_id — 来源候选 ID（必填）*/
  candidate_id: string;
  /** workflow_id — 要观察的工作流模板 ID（必填）*/
  workflow_id: string;
  /** version_tag — 版本标签（可选，留空则由后端生成）*/
  version_tag?: string;
  /** observation_days — 观察期天数，[1, 90]，默认 7 */
  observation_days?: number;
  /** graduate_tolerance_pct — 毕业容差%，[0, 50]，默认 5 */
  graduate_tolerance_pct?: number;
  source_run_id?: string;
  note?: string;
}

// ===========================================================================
// 类型定义 —— 调度任务（Scheduler Task）
// ===========================================================================

/**
 * ScheduledTaskSummary — 调度任务摘要（GET /scheduler/tasks 列表条目）
 *
 * 只包含前端"定时调度"面板列表需要的核心字段；完整字段需再调用
 * `getScheduledTask(task_id)`。
 */
export interface ScheduledTaskSummary {
  /** task_id — 任务唯一 ID */
  task_id: string;
  /** name — 任务名称（人类可读） */
  name: string;
  /** pipeline — 所属管线，如 'load_forecast' */
  pipeline: string;
  /** schedule_type — 调度策略 */
  schedule_type: 'rolling_daily' | 'cron' | 'interval';
  /** status — 当前运行状态 */
  status: 'running' | 'stopped' | 'failed';
  /** last_execution — 上次执行结果（对应模型的 last_result 字段） */
  last_execution: 'success' | 'failed' | 'skipped' | null;
  /** last_execution_time — 上次执行完成时间 ISO 8601 */
  last_execution_time: string | null;
  /** next_scheduled_time — 下次预计触发时间 ISO 8601 */
  next_scheduled_time: string | null;
  /** max_window_days — 滚动训练窗口最大天数（None 表示不限制） */
  max_window_days: number | null;
}

/**
 * ScheduledTaskDetail — 调度任务完整详情
 *
 * 与后端 `services/deployment/scheduler_models.py::ScheduledTask` 对齐；
 * 用于详情弹窗与编辑表单预填。
 */
export interface ScheduledTaskDetail {
  task_id: string;
  name: string;
  pipeline: string;
  schedule_type: 'rolling_daily' | 'cron' | 'interval';
  cron_expr: string | null;
  /** trigger_time — 每日触发时间 HH:MM，仅 rolling_daily 使用 */
  trigger_time: string;
  max_window_days: number | null;
  slot: string;
  status: 'running' | 'stopped' | 'failed';
  last_execution_time: string | null;
  last_result: 'success' | 'failed' | 'skipped' | null;
  next_scheduled_time: string | null;
  retry_on_failure: boolean;
  max_retries: number;
  created_at: string;
  updated_at: string;
}

/**
 * ScheduledTaskCreate — POST /scheduler/tasks 请求体
 *
 * task_id / created_at / updated_at 由服务端生成，客户端不提交。
 */
export interface ScheduledTaskCreate {
  /** name — 任务名称（必填，人类可读） */
  name: string;
  /** pipeline — 所属管线（必填） */
  pipeline: string;
  /** schedule_type — 调度策略（必填） */
  schedule_type: 'rolling_daily' | 'cron' | 'interval';
  cron_expr?: string | null;
  /** trigger_time — 每日触发时间 HH:MM，默认 "02:00" */
  trigger_time?: string;
  /** max_window_days — 滚动训练窗口最大天数，默认 365，None 表示不限制 */
  max_window_days?: number | null;
  /** slot — 关联的部署槽位，默认 "default" */
  slot?: string;
  /** status — 初始状态，默认 "stopped"（需显式 /start 启动） */
  status?: 'running' | 'stopped' | 'failed';
  retry_on_failure?: boolean;
  max_retries?: number;
}

// ===========================================================================
// 类型定义 —— 数据库健康检查（DB Health）
// ===========================================================================

/**
 * DBHealth — 数据库连通性检查结果（GET /system/db-health）
 *
 * 后端在所有失败分支内部分类，均以 HTTP 200 返回；上层探针应基于 `status`
 * 字段决策，不要依赖 HTTP 状态码判断数据库是否可用。
 */
export interface DBHealth {
  /** status — healthy（正常）| unhealthy（连接失败）| config_error（缺配置）| skipped（DB_ENABLED=false） */
  status: 'healthy' | 'unhealthy' | 'config_error' | 'skipped';
  /** error_type — 错误类型枚举（成功或跳过时为 null） */
  error_type: 'missing_env_vars' | 'connection_timeout' | 'auth_failure' | 'database_not_found' | 'unknown' | null;
  /** message — 面向 UI/日志的可读消息 */
  message: string;
  /** missing_vars — 缺失的必需环境变量名列表（仅 config_error 时非空） */
  missing_vars: string[];
  /** latency_ms — SELECT 1 探测耗时（毫秒），仅 healthy 时填充 */
  latency_ms: number | null;
  /** engine — 数据库引擎（如 "mysql"），非 config_error 时填充 */
  engine: string | null;
  /** connection_url_masked — 已脱敏（密码替换为 ***）的连接串 */
  connection_url_masked: string | null;
}

// ===========================================================================
// 部署槽位 API — 与 `.kiro/.../design.md → 1. 部署槽位管理 API` 对齐
// ===========================================================================

/**
 * 部署槽位 API — 管理生产/影子模型、切换、回滚、切换日志与自动切换配置。
 */
export const deploymentApi = {
  /** 列出所有槽位及其 production/shadow 模型 */
  listSlots: (): Promise<{ slots: Record<string, DeploymentSlotView> }> =>
    api.get('/deployment/slots'),

  /** 获取某槽位的版本历史（含 production/shadow/retired，每条附 role 字段） */
  listVersions: (slot: string): Promise<{ slot: string; versions: VersionHistoryItem[] }> =>
    api.get(`/deployment/slots/${encodeURIComponent(slot)}/versions`),

  /** 执行切换：将目标 shadow 提升为 production，原 production 降级为 retired */
  switchModel: (slot: string, req: SwitchRequest): Promise<{ event: SwitchEventView }> =>
    api.post(`/deployment/slots/${encodeURIComponent(slot)}/switch`, req),

  /** 回滚到前一 production 版本，追加一条 rollback_of 非空的 SwitchEvent */
  rollbackModel: (slot: string, req?: RollbackRequest): Promise<{ event: SwitchEventView }> =>
    api.post(`/deployment/slots/${encodeURIComponent(slot)}/rollback`, req ?? {}),

  /** 获取某槽位的切换事件日志（按追加顺序，最早在前；slot 不存在时返回空列表） */
  getSwitchLog: (slot: string): Promise<{ slot: string; events: SwitchEventView[] }> =>
    api.get(`/deployment/slots/${encodeURIComponent(slot)}/switch-log`),

  /** 获取自动切换配置 */
  getSlotConfig: (slot: string): Promise<SlotConfigView> =>
    api.get(`/deployment/slots/${encodeURIComponent(slot)}/config`),

  /** 局部更新自动切换配置（仅设置传入的非 undefined 字段） */
  updateSlotConfig: (slot: string, cfg: SlotConfigUpdate): Promise<SlotConfigView> =>
    api.put(`/deployment/slots/${encodeURIComponent(slot)}/config`, cfg),
};

// ===========================================================================
// 调度任务 API — 与 `.kiro/.../design.md → 2. 调度任务管理 API` 对齐
// ===========================================================================

/**
 * 调度任务 API —— 定时调度任务的 CRUD 与启停。
 *
 * 备注：
 *  - `startScheduledTask` / `stopScheduledTask` 只更新任务登记的运行状态位
 *    （status="running" / "stopped"），真正的调度触发由后端 SchedulerEngine
 *    依据 status 字段决定，不与管线级 `/scheduler/{pipeline}/start` 混淆。
 *  - 管线级启停请使用 `schedulerApi.ts` 中的 `startPipeline` / `stopPipeline`。
 */
export const schedulerTaskApi = {
  /** 列出所有调度任务（摘要模式） */
  listScheduledTasks: (): Promise<{ tasks: ScheduledTaskSummary[] }> =>
    api.get('/scheduler/tasks'),

  /** 创建新调度任务，服务端生成 task_id / created_at / updated_at */
  createScheduledTask: (payload: ScheduledTaskCreate): Promise<ScheduledTaskDetail> =>
    api.post('/scheduler/tasks', payload),

  /** 获取单个任务的完整字段（详情弹窗 / 编辑表单预填） */
  getScheduledTask: (taskId: string): Promise<ScheduledTaskDetail> =>
    api.get(`/scheduler/tasks/${encodeURIComponent(taskId)}`),

  /** 启动任务：将 status 置为 running */
  startScheduledTask: (taskId: string): Promise<{ task_id: string; status: 'running' }> =>
    api.post(`/scheduler/tasks/${encodeURIComponent(taskId)}/start`),

  /** 停止任务：将 status 置为 stopped */
  stopScheduledTask: (taskId: string): Promise<{ task_id: string; status: 'stopped' }> =>
    api.post(`/scheduler/tasks/${encodeURIComponent(taskId)}/stop`),

  /** 局部更新任务配置（改 cron_expr 后立即热更新 SchedulerEngine）*/
  updateScheduledTask: (
    taskId: string,
    payload: { cron_expr?: string; trigger_time?: string; max_window_days?: number | null; retry_on_failure?: boolean; max_retries?: number },
  ): Promise<ScheduledTaskDetail> =>
    api.patch(`/scheduler/tasks/${encodeURIComponent(taskId)}`, payload),

  /** 立即触发一次（不等下次 cron，不改 status，后台异步执行）*/
  triggerTaskNow: (taskId: string): Promise<{ task_id: string; status: string; message: string }> =>
    api.post(`/scheduler/tasks/${encodeURIComponent(taskId)}/trigger-now`),
};

// ===========================================================================
// 系统健康 API — 数据库连通性运行时探针
// ===========================================================================

/**
 * 系统健康 API —— 数据库连通性等运行时探针。
 *
 * 注意：本探针"永不抛异常"，所有失败分支都以 200 + status 字段返回。
 */
export const systemHealthApi = {
  /** 数据库连通性健康检查 */
  getDBHealth: (): Promise<DBHealth> => api.get('/system/db-health'),
};

// ===========================================================================
// 默认导出：聚合三个分组，方便按需 import
// ===========================================================================

export default {
  deployment: deploymentApi,
  schedulerTask: schedulerTaskApi,
  systemHealth: systemHealthApi,
};
// @AI_GENERATED: end

// @AI_GENERATED: 阶段 2/3 — Prelaunch API
/**
 * Prelaunch API — 预上线池管理（入池 / 列表 / 取消 / 手动毕业）
 *
 * 端点（相对 /api）：
 *   GET  /deployment/slots/{slot}/prelaunches          — 列表
 *   POST /deployment/slots/{slot}/prelaunches          — 入池
 *   POST /deployment/slots/{slot}/prelaunches/{wf}/cancel   — 取消
 *   POST /deployment/slots/{slot}/prelaunches/{wf}/graduate — 手动毕业
 */
export const prelaunchApi = {
  /** 获取预上线列表（可按 status 过滤：prelaunch | graduated | failed）*/
  listPrelaunches: (
    slot: string,
    status?: string,
  ): Promise<{ slot: string; prelaunches: PrelaunchModelView[]; active_count: number }> => {
    const params = status ? `?status=${encodeURIComponent(status)}` : '';
    return api.get(`/deployment/slots/${encodeURIComponent(slot)}/prelaunches${params}`);
  },

  /** 入池：把一个候选加入预上线观察 */
  enterPrelaunch: (
    slot: string,
    body: PrelaunchEnterRequest,
  ): Promise<{ success: boolean; item: PrelaunchModelView; active_count: number }> =>
    api.post(`/deployment/slots/${encodeURIComponent(slot)}/prelaunches`, body),

  /** 手动取消（→ retired）*/
  cancelPrelaunch: (
    slot: string,
    workflowId: string,
    reason?: string,
  ): Promise<{ success: boolean; workflow_id: string; status: string }> =>
    api.post(
      `/deployment/slots/${encodeURIComponent(slot)}/prelaunches/${encodeURIComponent(workflowId)}/cancel`,
      undefined,
      { params: reason ? { reason } : {} },
    ),

  /** 手动毕业（跳过观察期，直接 → shadow）*/
  graduatePrelaunch: (
    slot: string,
    workflowId: string,
  ): Promise<{ success: boolean; workflow_id: string; status: string; slot: DeploymentSlotView | null }> =>
    api.post(
      `/deployment/slots/${encodeURIComponent(slot)}/prelaunches/${encodeURIComponent(workflowId)}/graduate`,
    ),
};
// @AI_GENERATED: end
