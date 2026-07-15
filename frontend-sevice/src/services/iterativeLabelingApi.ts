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

// @AI_GENERATED: 编辑器→审核 API 显式携带 slot，防止后端忽略后写入 default
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
  loopId: string;
  trainResult: Record<string, unknown>;
  /** 模型训练完成后仍需走发布流程，API 不会自动发布 */
  publication: 'not_published';
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
      slot: request.slot || 'default',
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
      slot: request.slot || 'default',
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
  getState: (slot = 'default'): Promise<Record<string, unknown>> =>
    api.get('/iterative-labeling/cumulative-training/state', { params: { slot } }),

  registerImport: (
    request: RegisterCumulativeTrainingImportRequest,
    slot = 'default'
  ): Promise<Record<string, unknown>> =>
    api.post('/iterative-labeling/cumulative-training/imports', {
      dataset_path: request.datasetPath,
      source_name: request.sourceName,
    }, { params: { slot } }),

  runRetrainRequest: (
    requestId: string,
    slot = 'default'
  ): Promise<CumulativeRetrainRunResponse> =>
    api.post(`/iterative-labeling/cumulative-training/retrain-requests/${requestId}/run`, {}, {
      params: { slot },
    }),
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
};
