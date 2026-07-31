/**
 * 光伏故障人机协同迭代标注闭环 API 客户端
 * 
 * 封装四类接口：
 * 1. 闭环编排 (Loop Orchestrator)
 * 2. 审核会话 (Review Session)
 * 3. 标签注册表 (Label Registry)
 * 4. 迭代追踪 (Iteration Tracker)
 * 
 * 映射需求: 3.1, 4.1, 6.1, 8.1
 */

import api from './api';

// ============================================================================
// TypeScript 类型定义
// ============================================================================

// --------- 闭环编排相关类型 ---------

export interface CreateLoopRequest {
  /** 基线数据集版本 — 本轮训练所基于的基线(首轮可空) */
  baseDatasetVersion?: string;
}

export interface CreateLoopResponse {
  /** 迭代闭环唯一标识 — 用于后续操作 */
  loopId: string;
  /** 迭代轮次 — 从1起 */
  iterationRound: number;
  /** 当前阶段 — 初始为空,训练后置trained */
  stage?: string;
}

export interface TrainRequest {
  /** 数据集版本 — 必填,选定的有真值数据集版本 */
  datasetVersion: string;
  /** 模型参数 — 可选,含testRatio/nRepeats/randomState/k/labelMap等 */
  modelParams?: Record<string, unknown>;
}

export interface TrainResponse {
  /** 模型引用 — 预测时显式指定 */
  modelRef: string;
  /** 精度记录 — 含macroF1Mean±std等 */
  accuracyRecord: Record<string, unknown>;
  /** 标签空间快照 — 本次训练的标签空间 */
  labelSpaceSnapshot: Record<string, unknown>;
}

export interface PredictRequest {
  /** 模型引用 — 必填,使用的模型 */
  modelRef: string;
  /** 无标签数据集版本 — 必填,待预测数据集 */
  unlabeledDatasetVersion: string;
}

export interface PredictResponse {
  /** 预测批次标识 — 本次预测批次 */
  predictionBatchId: string;
  /** 诊断单元数 — 预测的单元总数 */
  unitCount: number;
}

export interface GetLoopStateResponse {
  /** 迭代闭环唯一标识 */
  loopId: string;
  /** 迭代轮次 */
  iterationRound: number;
  /** 当前阶段 */
  stage?: string;
  /** 数据集版本 */
  datasetVersion?: string;
  /** 模型引用 */
  modelRef?: string;
  /** 标签空间快照 */
  labelSpaceSnapshot?: Record<string, unknown>;
  /** 标签空间落后 — 模型快照落后于注册表当前版本 */
  labelSpaceLag: boolean;
}

export interface BackfillRequest {
  /** 来源审核会话 — 必填 */
  reviewId: string;
  /** 累积合并 — 是否与基线数据集合并,默认true */
  mergeBase?: boolean;
}

export interface BackfillResponse {
  /** 新数据集版本 — 回流生成的版本号 */
  datasetVersion: string;
  /** 纳入回流单元数 — 排除pending后的单元数 */
  unitCount: number;
}

// --------- 审核会话相关类型 ---------

// @AI_GENERATED: 通用创建审核会话接口也显式透传 slot
export interface CreateReviewSessionRequest {
  /** 所属迭代闭环 — 关联的loop */
  loopId: string;
  /** 预测批次标识 — 基于哪一批预测结果 */
  predictionBatchId: string;
  /** 启用LLM辅助 — 是否生成LLM建议 */
  enableLlm?: boolean;
  /** 槽位 — 审核、标签和回流数据的隔离分区 */
  slot?: string;
}
// @AI_GENERATED: end

export interface CreateReviewSessionResponse {
  /** 审核会话唯一标识 — 用于后续提交裁决 */
  reviewId: string;
  /** 待审核单元总数 — 本次审核需处理的单元数 */
  totalCount: number;
}

export interface GetReviewSessionResponse {
  /** 审核会话唯一标识 */
  reviewId: string;
  /** 会话状态 — reviewing/reviewed */
  status: string;
  /** 已审核数 — 已提交裁决的单元数 */
  reviewedCount: number;
  /** 总数 — 待审核单元总数 */
  totalCount: number;
  /** 待审核单元数组 — 含classifierPrediction/llmSuggestion/disagreement等 */
  units: Array<Record<string, unknown>>;
}

export interface SubmitVerdictRequest {
  /** 诊断单元标识 — siteId×deviceId×(branchId)×timeWindow */
  unitKey: string;
  /** 动作类型 — confirm/correct/new_label/skip */
  actionType: string;
  /** 裁决标签 — confirm取predictedLabel,correct从已有选,newLabel走扩充,skip为null */
  verdictLabel?: number;
  /** 新标签名 — newLabel时必填 */
  newLabelName?: string;
  /** 审核人 — 操作者标识 */
  reviewer: string;
}

// @AI_GENERATED: 审核裁决回传正常累计训练集准入、阈值和重训请求摘要
export interface SubmitVerdictResponse {
  /** 是否接受 — 裁决是否成功提交 */
  accepted: boolean;
  /** 精度快照 — 当前三方精度 */
  accuracySnapshot: Record<string, unknown>;
  /** 累计训练集状态 — 有效人工真值的准入、快照与重训申请 */
  cumulativeTraining: Record<string, unknown>;
}
// @AI_GENERATED: end

export interface GetAccuracyResponse {
  /** 分类器原始预测精度 — 分类器命中人工裁决的比例 */
  classifierAccuracy: number;
  /** LLM建议精度 — 仅在有LLM建议的单元上计算 */
  llmAccuracy: number;
  /** 人工核对后精度基线 — 已审核单元100%一致口径 */
  humanVerifiedAccuracy: number;
  /** LLM覆盖率 — 有LLM建议的已审核单元占比 */
  llmCoverage: number;
  /** 宏平均指标 — 含precision/recall/f1 */
  macro: Record<string, number>;
  /** 纳入统计单元数 — 仅confirm/correct/newLabel,排除pending */
  countedUnits: number;
}

// --------- 编辑器驱动：从预测结果建会话 / 回流原始时序 ---------

// @AI_GENERATED: 编辑器→审核 API 显式携带 slot，防止后端忽略后写入 pv_fault
export interface CreateReviewSessionFromPredictionRequest {
  /** 预测结果数组 — 来自预测工作流 faultPredictions */
  predictions: Array<Record<string, unknown>>;
  /** 原始预测 CSV 路径 — 使用相对于项目根目录的路径 */
  sourceCsvPath: string;
  /** load_csv 配置 — rename_columns/encoding/delimiter,回流复用 */
  loadConfig?: Record<string, unknown>;
  /** time_window_split 配置 — window/id_fields/time_field,回流重算窗口键 */
  windowConfig?: Record<string, unknown>;
  /** 标签映射 — 业务名→故障码,播种标签注册表与展示 */
  labelMap?: Record<string, number>;
  /** 启用GLM辅助 — 后台异步生成建议 */
  enableLlm?: boolean;
  /** 所属迭代闭环 — 编辑器驱动可不传 */
  loopId?: string;
  /** 审核人标识 */
  reviewer?: string;
  /** 槽位 — 审核、标签和回流数据的隔离分区 */
  slot?: string;
}
// @AI_GENERATED: end

export interface BackfillToDatasetRequest {
  /** 累积合并 — 是否拼接基线训练 CSV,默认true */
  mergeBase?: boolean;
  /** 基线训练 CSV 路径 — merge_base=true 时拼接到新数据集前 */
  baseCsvPath?: string;
}

export interface BackfillToDatasetResponse {
  /** 新数据集版本号 */
  dataset_version: string;
  /** 新数据集 CSV 相对项目根目录路径 — 可直接粘贴到训练工作流 load_csv 的 file_path */
  csv_path: string;
  /** 标注后原始行数 */
  labeled_rows: number;
  /** 标注单元数 — 去重后的设备×窗口数 */
  labeled_units: number;
  /** 原始预测 CSV 总行数 */
  total_source_rows: number;
}

// --------- 标签注册表相关类型 ---------

export interface GetLabelRegistryResponse {
  /** 当前标签空间版本号 — 如ls-v5 */
  labelSpaceVersion: string;
  /** 标签数组 — 含labelId/labelName/createdAt */
  labels: Array<Record<string, unknown>>;
  /** 标签映射 — 业务标签→数值类别,供labelEncode消费 */
  labelMap: Record<string, number>;
}

export interface AddLabelRequest {
  /** 标签业务名 — 必填,新标签名称 */
  labelName: string;
}

export interface AddLabelResponse {
  /** 标签编码 — 新分配的唯一ID */
  labelId: number;
  /** 标签空间版本 — 扩充后的新版本号 */
  labelSpaceVersion: string;
}

export interface GetLabelVersionsResponse {
  /** 历史版本快照 — 含labelSpaceVersion/labelIds/snapshotAt */
  history: Array<Record<string, unknown>>;
}

// --------- 迭代追踪相关类型 ---------

export interface GetIterationsResponse {
  /** 迭代记录数组 — 按iterationRound排序 */
  iterations: Array<Record<string, unknown>>;
  /** 趋势对象 — 含macroF1ByRound/labelCountByRound */
  trend: Record<string, unknown[]>;
}

// @AI_GENERATED: 正常累计训练集的状态、带真值导入与显式重训 API 契约
export interface RegisterCumulativeTrainingImportRequest {
  /** 仅允许带 label 列的 CSV/Parquet 相对项目根目录路径 */
  datasetPath: string;
  /** 导入来源说明，仅用于审计展示 */
  sourceName?: string;
}

export interface CumulativeRetrainRunResponse {
  request: Record<string, unknown>;
  loop_id: string;
  train_result: Record<string, unknown>;
  /** 训练成功后自动成为 pv_fault 当前生产模型 */
  publication: 'auto_promoted';
  production_model_ref: string;
}
// @AI_GENERATED: end

// ============================================================================
// API 客户端方法
// ============================================================================

/**
 * 闭环编排 API
 * 
 * 管理迭代闭环的生命周期：创建、训练、预测、查询状态、回流
 */
export const loopOrchestratorApi = {
  /**
   * 创建新迭代闭环
   * 
   * POST /api/iterative-labeling/loops
   * 映射需求: 12.1
   */
  createLoop: (request: CreateLoopRequest): Promise<CreateLoopResponse> =>
    api.post('/iterative-labeling/loops', {
      base_dataset_version: request.baseDatasetVersion,
    }),

  /**
   * 触发训练评估
   * 
   * POST /api/iterative-labeling/loops/{loopId}/train
   * 映射需求: 1.1, 1.9, 1.10, 1.11, 12.4
   */
  train: (loopId: string, request: TrainRequest): Promise<TrainResponse> =>
    api.post(`/iterative-labeling/loops/${loopId}/train`, {
      dataset_version: request.datasetVersion,
      model_params: request.modelParams,
    }),

  /**
   * 触发预测
   * 
   * POST /api/iterative-labeling/loops/{loopId}/predict
   * 映射需求: 2.1, 2.2, 2.3, 2.4, 2.5
   */
  predict: (loopId: string, request: PredictRequest): Promise<PredictResponse> =>
    api.post(`/iterative-labeling/loops/${loopId}/predict`, {
      model_ref: request.modelRef,
      unlabeled_dataset_version: request.unlabeledDatasetVersion,
    }),

  /**
   * 读取闭环状态
   * 
   * GET /api/iterative-labeling/loops/{loopId}
   * 映射需求: 12.5
   */
  getLoopState: (loopId: string): Promise<GetLoopStateResponse> =>
    api.get(`/iterative-labeling/loops/${loopId}`),

  /**
   * 触发回流
   * 
   * POST /api/iterative-labeling/loops/{loopId}/backfill
   * 映射需求: 9.1, 9.2, 9.3, 9.4, 9.5
   */
  backfill: (loopId: string, request: BackfillRequest): Promise<BackfillResponse> =>
    api.post(`/iterative-labeling/loops/${loopId}/backfill`, {
      review_id: request.reviewId,
      merge_base: request.mergeBase,
    }),
};

/**
 * 审核会话 API
 * 
 * 管理人工审核流程：创建会话、查询状态、提交裁决、读取精度
 */
export const reviewSessionApi = {
  /**
   * 创建审核会话
   * 
   * POST /api/iterative-labeling/review-sessions
   * 映射需求: 3.1, 7.1
   */
  createReviewSession: (request: CreateReviewSessionRequest): Promise<CreateReviewSessionResponse> =>
    api.post('/iterative-labeling/review-sessions', {
      loop_id: request.loopId,
      prediction_batch_id: request.predictionBatchId,
      enable_llm: request.enableLlm,
      // @AI_GENERATED: 光伏审核请求未显式传槽位时写入正式 pv_fault 分区。
      slot: request.slot || 'pv_fault',
      // @AI_GENERATED: end
    }),

  /**
   * 读取审核会话状态
   * 
   * GET /api/iterative-labeling/review-sessions/{reviewId}
   * 映射需求: 3.3, 3.4
   */
  getReviewSession: (reviewId: string): Promise<GetReviewSessionResponse> =>
    api.get(`/iterative-labeling/review-sessions/${reviewId}`),

  /**
   * 提交人工裁决
   * 
   * POST /api/iterative-labeling/review-sessions/{reviewId}/verdicts
   * 映射需求: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
   */
  submitVerdict: (reviewId: string, request: SubmitVerdictRequest): Promise<SubmitVerdictResponse> =>
    api.post(`/iterative-labeling/review-sessions/${reviewId}/verdicts`, {
      unit_key: request.unitKey,
      action_type: request.actionType,
      verdict_label: request.verdictLabel,
      new_label_name: request.newLabelName,
      reviewer: request.reviewer,
    }),

  /**
   * 读取三方精度
   * 
   * GET /api/iterative-labeling/review-sessions/{reviewId}/accuracy
   * 映射需求: 6.1, 6.2, 6.3, 6.4, 6.5
   */
  getAccuracy: (reviewId: string): Promise<GetAccuracyResponse> =>
    api.get(`/iterative-labeling/review-sessions/${reviewId}/accuracy`),

  /**
   * 列出本会话自由时间窗标注
   * GET /api/iterative-labeling/review-sessions/{reviewId}/freeform-labels
   */
  listFreeformLabels: (
    reviewId: string,
    slot = 'pv_fault'
  ): Promise<{ review_id: string; labels: Array<Record<string, unknown>> }> =>
    api.get(`/iterative-labeling/review-sessions/${reviewId}/freeform-labels`, {
      params: { slot },
    }),

  /**
   * 框选时间窗打标并写入累计训练集
   * POST /api/iterative-labeling/review-sessions/{reviewId}/freeform-labels
   */
  createFreeformLabel: (
    reviewId: string,
    body: {
      t_start: string;
      t_end: string;
      action_type: 'correct' | 'new_label';
      reviewer?: string;
      verdict_label?: number;
      new_label_name?: string;
      source_unit_key?: string;
      site_id?: string;
      device_id?: string;
      branch_id?: string;
    },
    slot = 'pv_fault'
  ): Promise<Record<string, unknown>> =>
    api.post(`/iterative-labeling/review-sessions/${reviewId}/freeform-labels?slot=${encodeURIComponent(slot)}`, body),

  /**
   * 撤销本会话自由时间窗标注指针
   * DELETE /api/iterative-labeling/review-sessions/{reviewId}/freeform-labels/{unitKey}
   */
  revokeFreeformLabel: (
    reviewId: string,
    unitKey: string,
    slot = 'pv_fault'
  ): Promise<{ revoked: boolean; unit_key: string; remaining: number }> =>
    api.delete(
      `/iterative-labeling/review-sessions/${reviewId}/freeform-labels/${encodeURIComponent(unitKey)}`,
      { params: { slot } }
    ),

  /**
   * 从工作流预测结果创建审核会话（编辑器驱动）
   *
   * POST /api/iterative-labeling/review-sessions/from-prediction
   * 用途：预测工作流执行后,"人工审查打标"按钮携带预测结果与原始 CSV 上下文调用,返回 reviewId 跳转打标页
   */
  createReviewSessionFromPrediction: (
    request: CreateReviewSessionFromPredictionRequest
  ): Promise<CreateReviewSessionResponse> =>
    api.post('/iterative-labeling/review-sessions/from-prediction', {
      predictions: request.predictions,
      source_csv_path: request.sourceCsvPath,
      load_config: request.loadConfig,
      window_config: request.windowConfig,
      label_map: request.labelMap,
      enable_llm: request.enableLlm,
      loop_id: request.loopId,
      reviewer: request.reviewer,
      // @AI_GENERATED: 光伏审核请求未显式传槽位时写入正式 pv_fault 分区。
      slot: request.slot || 'pv_fault',
      // @AI_GENERATED: end
    }),

  /**
   * 从审核会话回流，产出原始时序级训练数据集 CSV（编辑器驱动）
   *
   * POST /api/iterative-labeling/review-sessions/{reviewId}/backfill-to-dataset
   * 返回的 csvPath 可直接粘贴到训练工作流 load_csv 节点的 file_path 开启下一轮
   */
  backfillToDataset: (
    reviewId: string,
    request: BackfillToDatasetRequest
  ): Promise<BackfillToDatasetResponse> =>
    api.post(`/iterative-labeling/review-sessions/${reviewId}/backfill-to-dataset`, {
      merge_base: request.mergeBase,
      base_csv_path: request.baseCsvPath,
    }),
};

// @AI_GENERATED: 正常累计训练集控制面；所有路径由后端校验为项目根相对路径
export const cumulativeTrainingApi = {
  getState: (slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/cumulative-training/state', { params: { slot } }),

  registerImport: (
    request: RegisterCumulativeTrainingImportRequest,
    slot = 'pv_fault'
  ): Promise<Record<string, unknown>> =>
    api.post('/iterative-labeling/cumulative-training/imports', {
      dataset_path: request.datasetPath,
      source_name: request.sourceName,
    }, { params: { slot } }),

  // @AI_GENERATED: getSplitConfig / updateSplitConfig 已随 split parity 机制废弃并移除。
  // 后端 /cumulative-training/split-config 现返回 410；切分策略改为随模型持久化
  // （sample_strategy），不再由前端配置 solar_mode。二者在前端无任何调用方，
  // 保留会诱导调用已废弃接口，故删除。
  // 对齐：docs/specs/pv-fault-label-segment-redesign/tasks.md 任务 21。

  getSplitModeCompare: (slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/cumulative-training/split-mode-compare', { params: { slot } }),

  runSplitModeCompare: (
    body: {
      modes?: Array<string | null>;
      nRepeats?: number;
      testRatio?: number;
      datasetPath?: string;
    } = {},
    slot = 'pv_fault',
  ): Promise<Record<string, unknown>> =>
    api.post('/iterative-labeling/cumulative-training/split-mode-compare', {
      modes: body.modes,
      n_repeats: body.nRepeats ?? 3,
      test_ratio: body.testRatio ?? 0.2,
      dataset_path: body.datasetPath,
    }, { params: { slot }, timeout: 60 * 1000 }),

  getModelingPathCompare: (slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/cumulative-training/modeling-path-compare', { params: { slot } }),

  runModelingPathCompare: (
    body: {
      paths?: string[];
      nRepeats?: number;
      testRatio?: number;
      randomState?: number;
      legacyDatasetPath?: string;
      siteId?: string;
    } = {},
    slot = 'pv_fault',
  ): Promise<Record<string, unknown>> =>
    api.post('/iterative-labeling/cumulative-training/modeling-path-compare', {
      paths: body.paths,
      n_repeats: body.nRepeats ?? 3,
      test_ratio: body.testRatio ?? 0.2,
      random_state: body.randomState ?? 90,
      legacy_dataset_path: body.legacyDatasetPath,
      site_id: body.siteId,
    }, { params: { slot }, timeout: 60 * 1000 }),

  getModelingPaths: (slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/cumulative-training/modeling-paths', { params: { slot } }),

  setModelingPaths: (
    productionPath: string,
    fallbackPath?: string,
    slot = 'pv_fault',
  ): Promise<Record<string, unknown>> =>
    api.put('/iterative-labeling/cumulative-training/modeling-paths', {
      production_path: productionPath,
      fallback_path: fallbackPath,
    }, { params: { slot } }),

  switchModelingFallback: (reason: string, slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.post('/iterative-labeling/cumulative-training/modeling-paths/switch-fallback', {
      reason,
    }, { params: { slot } }),

  createManualRetrainRequest: (slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.post('/iterative-labeling/cumulative-training/retrain-requests/manual', {}, { params: { slot } }),

  runRetrainRequest: (
    requestId: string,
    slot = 'pv_fault',
  ): Promise<CumulativeRetrainRunResponse> =>
    api.post(`/iterative-labeling/cumulative-training/retrain-requests/${requestId}/run`, {}, {
      params: { slot },
    }),
};

export const pointLabelApi = {
  getPendingQueue: (
    params: {
      siteId?: string;
      deviceId?: string;
      timeStart?: string;
      timeEnd?: string;
      minPoints?: number;
      page?: number;
      pageSize?: number;
    } = {},
    slot = 'pv_fault',
  ): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/point-labels/pending-queue', {
      params: {
        slot,
        site_id: params.siteId,
        device_id: params.deviceId,
        time_start: params.timeStart,
        time_end: params.timeEnd,
        min_points: params.minPoints ?? 1,
        page: params.page ?? 1,
        page_size: params.pageSize ?? 50,
      },
    }),

  getSourceCoverage: (slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/point-labels/source-coverage', { params: { slot } }),
};
// @AI_GENERATED: end

/**
 * 标签注册表 API
 * 
 * 管理标签空间：读取当前注册表、新增标签、查询历史版本
 */
export const labelRegistryApi = {
  /**
   * 读取当前标签注册表
   * 
   * GET /api/iterative-labeling/label-registry
   * 映射需求: 8.1, 8.2, 8.3
   */
  getLabelRegistry: (): Promise<GetLabelRegistryResponse> =>
    api.get('/iterative-labeling/label-registry'),

  /**
   * 新增标签类别
   * 
   * POST /api/iterative-labeling/label-registry/labels
   * 映射需求: 8.1, 8.2, 8.5
   */
  addLabel: (request: AddLabelRequest): Promise<AddLabelResponse> =>
    api.post('/iterative-labeling/label-registry/labels', {
      label_name: request.labelName,
    }),

  /**
   * 读取历史版本快照
   * 
   * GET /api/iterative-labeling/label-registry/versions
   * 映射需求: 8.2
   */
  getLabelVersions: (): Promise<GetLabelVersionsResponse> =>
    api.get('/iterative-labeling/label-registry/versions'),
};

/**
 * 迭代追踪 API
 * 
 * 查询迭代历史与趋势
 */
export const iterationTrackerApi = {
  /**
   * 读取迭代历史
   * 
   * GET /api/iterative-labeling/iterations
   * 映射需求: 10.1, 10.2, 10.3, 10.4, 10.5
   */
  getIterations: (): Promise<GetIterationsResponse> => {
    return api.get('/iterative-labeling/iterations');
  },
};

// @AI_GENERATED: 训练数据工作台 API — 候选数据、聚类确认、时间切片、预测批次和槽位运营总览
export const trainingWorkspaceApi = {
  /** 分页读取 pv_fault 候选训练样本 */
  getTrainingCandidates: (params: {
    page?: number;
    page_size?: number;
    label_status?: string;
    site_id?: string;
    time_start?: string;
    time_end?: string;
  } = {}): Promise<{ page: number; page_size: number; total: number; items: Array<Record<string, unknown>> }> =>
    api.get('/iterative-labeling/training-candidates', { params }),

  /** 创建聚类 run */
  createClusteringRun: (body: {
    n_clusters?: number;
    label_status?: string;
    page_size?: number;
    site_id?: string;
    time_start?: string;
    time_end?: string;
    reviewer?: string;
    dataset_path?: string;
  }): Promise<Record<string, unknown>> =>
    api.post('/iterative-labeling/clustering/runs', body),

  /** 从上传的无标签数据集创建旧版逐单元人工打标会话 */
  createManualReviewFromDataset: (body: {
    dataset_path: string;
    slot?: string;
    reviewer?: string;
    max_units?: number;
  }): Promise<{ review_id: string; total_count: number }> =>
    api.post('/iterative-labeling/review-sessions/from-dataset', body),

  /** 读取聚类 run */
  getClusteringRun: (runId: string): Promise<Record<string, unknown>> =>
    api.get(`/iterative-labeling/clustering/runs/${runId}`),

  /** 更新簇（命名 / 选择成员） */
  updateCluster: (
    runId: string,
    clusterId: string,
    body: { proposed_label_name?: string; selected_member_keys?: string[] },
  ): Promise<Record<string, unknown>> =>
    api.put(`/iterative-labeling/clustering/runs/${runId}/clusters/${clusterId}`, body),

  /** 二次确认聚类 run 并登记累计训练集 */
  confirmClusteringRun: (runId: string): Promise<Record<string, unknown>> =>
    api.post(`/iterative-labeling/clustering/runs/${runId}/confirm`, { confirm_inclusion: true }),

  /** 创建时间切片标注并登记累计训练集 */
  createTimeSlice: (body: {
    source_path: string;
    time_start: string;
    time_end: string;
    label_id: number;
    confirm_inclusion: boolean;
    site_id?: string;
    device_id?: string;
    branch_id?: string;
    reviewer?: string;
  }): Promise<Record<string, unknown>> =>
    api.post('/iterative-labeling/training-slices', body),

  /** 列出预测批次 */
  listPredictionBatches: (slot = 'pv_fault'): Promise<{ batches: Array<Record<string, unknown>> }> =>
    api.get('/iterative-labeling/prediction-batches', { params: { slot } }),

  /** 读取单个预测批次 */
  getPredictionBatch: (batchId: string, slot = 'pv_fault'): Promise<Record<string, unknown>> =>
    api.get(`/iterative-labeling/prediction-batches/${batchId}`, { params: { slot } }),

  /** 槽位运营总览 */
  getSlotOverview: (slot: string): Promise<Record<string, unknown>> =>
    api.get('/accuracy-operations/slot-overview', { params: { slot } }),
};
// @AI_GENERATED: end

/**
 * 默认导出：聚合所有 API 模块
 */
export default {
  loopOrchestrator: loopOrchestratorApi,
  reviewSession: reviewSessionApi,
  // @AI_GENERATED: 暴露正常累计训练集控制面
  cumulativeTraining: cumulativeTrainingApi,
  // @AI_GENERATED: end
  labelRegistry: labelRegistryApi,
  iterationTracker: iterationTrackerApi,
  // @AI_GENERATED: 训练工作台和运营聚合
  trainingWorkspace: trainingWorkspaceApi,
  // @AI_GENERATED: end
};
