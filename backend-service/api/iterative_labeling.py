"""
光伏故障人机协同迭代标注闭环 API

本模块暴露迭代标注闭环的全部 HTTP 接口,统一前缀 `/api/iterative-labeling`。

**接口分类:**
1. 闭环编排 (Loop_Orchestrator):
   - POST /loops - 创建新闭环
   - POST /loops/{loop_id}/train - 触发训练评估
   - POST /loops/{loop_id}/predict - 触发预测
   - GET /loops/{loop_id} - 读取闭环状态
   - POST /loops/{loop_id}/backfill - 触发回流

2. 审核会话 (Review_Session):
   - POST /review-sessions - 创建审核会话
   - GET /review-sessions/{review_id} - 读取会话状态
   - POST /review-sessions/{review_id}/verdicts - 提交人工裁决
   - GET /review-sessions/{review_id}/accuracy - 读取三方精度

3. 标签注册表 (Label_Registry):
   - GET /label-registry - 读取当前标签注册表
   - POST /label-registry/labels - 新增标签类别
   - GET /label-registry/versions - 读取历史版本快照

4. 迭代追踪 (Iteration_Tracker):
   - GET /iterations - 读取迭代历史与趋势

**关键约定:**
- 所有字段采用 `field_name` — 中文含义 注解格式
- 写入类接口经 Storage_Abstraction 落地
- 复用既有工作流(quickval-cv/prediction),不重造
- 错误返回标准 HTTPException + 详细说明

**映射需求:** 3.5, 4.4, 8.4, 12.3
"""

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

# 导入服务层
from services.iterative_labeling.orchestrator import LoopOrchestrator, StageTransitionError
from services.iterative_labeling.review_session import ReviewSessionService
from services.iterative_labeling.label_registry import LabelRegistryService
from services.iterative_labeling.accuracy_evaluator import AccuracyEvaluator
from services.iterative_labeling.backfill import BackfillService
from services.iterative_labeling.iteration_tracker import IterationTracker
from services.iterative_labeling.storage.file_backend import (
    FileReviewResultRepository,
    FileLabelRegistryRepository,
    FileIterationHistoryRepository,
    FileGroundTruthRepository,
)

router = APIRouter(prefix="/api/iterative-labeling", tags=["iterative-labeling"])
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic 模型定义（请求/响应体）
# ============================================================================

# --------- 闭环编排相关 ---------

class CreateLoopRequest(BaseModel):
    """创建迭代闭环请求"""
    base_dataset_version: Optional[str] = Field(None, description="基线数据集版本 — 本轮训练所基于的基线(首轮可空)")

class CreateLoopResponse(BaseModel):
    """创建迭代闭环响应"""
    loop_id: str = Field(..., description="迭代闭环唯一标识 — 用于后续操作")
    iteration_round: int = Field(..., description="迭代轮次 — 从1起")
    stage: Optional[str] = Field(None, description="当前阶段 — 初始为空,训练后置trained")

class TrainRequest(BaseModel):
    """触发训练评估请求"""
    dataset_version: str = Field(..., description="数据集版本 — 必填,选定的有真值数据集版本")
    model_params: Optional[Dict[str, Any]] = Field(
        None,
        description="模型参数 — 可选,含test_ratio/n_repeats/random_state/k/label_map等"
    )

class TrainResponse(BaseModel):
    """触发训练评估响应"""
    model_ref: str = Field(..., description="模型引用 — 预测时显式指定")
    accuracy_record: Dict[str, Any] = Field(..., description="精度记录 — 含macro_f1_mean±std等")
    label_space_snapshot: Dict[str, Any] = Field(..., description="标签空间快照 — 本次训练的标签空间")

class PredictRequest(BaseModel):
    """触发预测请求"""
    model_ref: str = Field(..., description="模型引用 — 必填,使用的模型")
    unlabeled_dataset_version: str = Field(..., description="无标签数据集版本 — 必填,待预测数据集")

class PredictResponse(BaseModel):
    """触发预测响应"""
    prediction_batch_id: str = Field(..., description="预测批次标识 — 本次预测批次")
    unit_count: int = Field(..., description="诊断单元数 — 预测的单元总数")

class GetLoopStateResponse(BaseModel):
    """读取闭环状态响应"""
    loop_id: str
    iteration_round: int
    stage: Optional[str]
    dataset_version: Optional[str]
    model_ref: Optional[str]
    label_space_snapshot: Optional[Dict[str, Any]]
    label_space_lag: bool = Field(..., description="标签空间落后 — 模型快照落后于注册表当前版本")


# --------- 审核会话相关 ---------

class CreateReviewSessionRequest(BaseModel):
    """创建审核会话请求"""
    loop_id: str = Field(..., description="所属迭代闭环 — 关联的loop")
    prediction_batch_id: str = Field(..., description="预测批次标识 — 基于哪一批预测结果")
    enable_llm: Optional[bool] = Field(True, description="启用LLM辅助 — 是否生成LLM建议")

class CreateReviewSessionResponse(BaseModel):
    """创建审核会话响应"""
    review_id: str = Field(..., description="审核会话唯一标识 — 用于后续提交裁决")
    total_count: int = Field(..., description="待审核单元总数 — 本次审核需处理的单元数")

class GetReviewSessionResponse(BaseModel):
    """读取审核会话响应"""
    review_id: str
    status: str = Field(..., description="会话状态 — reviewing/reviewed")
    reviewed_count: int = Field(..., description="已审核数 — 已提交裁决的单元数")
    total_count: int = Field(..., description="总数 — 待审核单元总数")
    units: List[Dict[str, Any]] = Field(..., description="待审核单元数组 — 含classifier_prediction/llm_suggestion/disagreement等")
    prediction_context: Optional[Dict[str, Any]] = Field(None, description="预测上下文 — 含source_csv_path/load_config/window_config/label_map")

class SubmitVerdictRequest(BaseModel):
    """提交人工裁决请求"""
    unit_key: str = Field(..., description="诊断单元标识 — site_id×device_id×(branch_id)×time_window")
    action_type: str = Field(..., description="动作类型 — confirm/correct/new_label/skip")
    verdict_label: Optional[int] = Field(None, description="裁决标签 — confirm取predicted_label,correct从已有选,new_label走扩充,skip为null")
    new_label_name: Optional[str] = Field(None, description="新标签名 — new_label时必填")
    reviewer: str = Field(..., description="审核人 — 操作者标识")

class SubmitVerdictResponse(BaseModel):
    """提交人工裁决响应"""
    accepted: bool = Field(..., description="是否接受 — 裁决是否成功提交")
    accuracy_snapshot: Dict[str, Any] = Field(..., description="精度快照 — 当前三方精度")

class GetAccuracyResponse(BaseModel):
    """读取三方精度响应"""
    classifier_accuracy: float = Field(..., description="分类器原始预测精度 — 分类器命中人工裁决的比例")
    llm_accuracy: float = Field(..., description="LLM建议精度 — 仅在有LLM建议的单元上计算")
    human_verified_accuracy: float = Field(..., description="人工核对后精度基线 — 已审核单元100%一致口径")
    llm_coverage: float = Field(..., description="LLM覆盖率 — 有LLM建议的已审核单元占比")
    macro: Dict[str, float] = Field(..., description="宏平均指标 — 含precision/recall/f1")
    counted_units: int = Field(..., description="纳入统计单元数 — 仅confirm/correct/new_label,排除pending")


# --------- 标签注册表相关 ---------

class GetLabelRegistryResponse(BaseModel):
    """读取当前标签注册表响应"""
    label_space_version: str = Field(..., description="当前标签空间版本号 — 如ls-v5")
    labels: List[Dict[str, Any]] = Field(..., description="标签数组 — 含label_id/label_name/created_at")
    label_map: Dict[str, int] = Field(..., description="标签映射 — 业务标签→数值类别,供label_encode消费")

class AddLabelRequest(BaseModel):
    """新增标签类别请求"""
    label_name: str = Field(..., description="标签业务名 — 必填,新标签名称")

class AddLabelResponse(BaseModel):
    """新增标签类别响应"""
    label_id: int = Field(..., description="标签编码 — 新分配的唯一ID")
    label_space_version: str = Field(..., description="标签空间版本 — 扩充后的新版本号")

class GetLabelVersionsResponse(BaseModel):
    """读取历史版本快照响应"""
    history: List[Dict[str, Any]] = Field(..., description="历史版本快照 — 含label_space_version/label_ids/snapshot_at")

# --------- 迭代追踪相关 ---------

class GetIterationsResponse(BaseModel):
    """读取迭代历史响应"""
    iterations: List[Dict[str, Any]] = Field(..., description="迭代记录数组 — 按iteration_round排序")
    trend: Dict[str, List] = Field(..., description="趋势对象 — 含macro_f1_by_round/label_count_by_round")

# --------- 回流相关 ---------

class BackfillRequest(BaseModel):
    """触发回流请求"""
    review_id: str = Field(..., description="来源审核会话 — 必填")
    merge_base: Optional[bool] = Field(True, description="累积合并 — 是否与基线数据集合并,默认true")

class BackfillResponse(BaseModel):
    """触发回流响应"""
    dataset_version: str = Field(..., description="新数据集版本 — 回流生成的版本号")
    unit_count: int = Field(..., description="纳入回流单元数 — 排除pending后的单元数")


# --------- 编辑器驱动：从预测结果建会话 / 回流原始时序 ---------

class CreateReviewSessionFromPredictionRequest(BaseModel):
    """从工作流预测结果创建审核会话（编辑器驱动）"""
    predictions: List[Dict[str, Any]] = Field(..., description="预测结果数组 — 来自预测工作流 faultPredictions,每项含 site_id/device_id/branch_id/time_window/predictions")
    source_csv_path: str = Field(..., description="原始预测 CSV 路径 — 来自预测工作流 load_csv 节点 file_path,回流时回贴原始时序用")
    load_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="load_csv 配置 — rename_columns/encoding/delimiter,回流时复用")
    window_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="time_window_split 配置 — window/id_fields/time_field,回流重算窗口键用")
    label_map: Optional[Dict[str, int]] = Field(default_factory=dict, description="标签映射 — 业务名→故障码,用于播种标签注册表与展示")
    enable_llm: Optional[bool] = Field(False, description="启用GLM辅助 — 后台异步生成建议,完成后刷新可见")
    loop_id: Optional[str] = Field(None, description="所属迭代闭环 — 可选,编辑器驱动可不传")
    reviewer: Optional[str] = Field("operator", description="审核人标识")

class BackfillToDatasetRequest(BaseModel):
    """从审核会话回流产出原始时序数据集"""
    merge_base: Optional[bool] = Field(True, description="累积合并 — 是否拼接基线训练 CSV,默认true")
    base_csv_path: Optional[str] = Field(None, description="基线训练 CSV 路径 — merge_base=true 时拼接到新数据集前(如上一轮训练用的 CSV)")

class BackfillToDatasetResponse(BaseModel):
    """回流产出数据集响应"""
    dataset_version: str = Field(..., description="新数据集版本号")
    csv_path: str = Field(..., description="新数据集 CSV 绝对路径 — 可直接粘贴到训练工作流 load_csv 的 file_path")
    labeled_rows: int = Field(..., description="标注后原始行数 — 回贴标签后的总行数")
    labeled_units: int = Field(..., description="标注单元数 — 去重后的设备×窗口数")
    total_source_rows: int = Field(..., description="原始预测 CSV 总行数")


# ============================================================================
# 服务实例初始化（单例模式）
# ============================================================================

# 初始化仓储后端
_review_repo = FileReviewResultRepository()
_registry_repo = FileLabelRegistryRepository()
_iteration_repo = FileIterationHistoryRepository()
_ground_truth_repo = FileGroundTruthRepository()

# 初始化服务（使用默认槽位'default'）
_label_registry_service = LabelRegistryService(slot="default", registry_repo=_registry_repo)
_iteration_tracker = IterationTracker(slot="default", history_repo=_iteration_repo)
_orchestrator = LoopOrchestrator(slot="default")
_review_session_service = ReviewSessionService(
    slot="default",
    review_repo=_review_repo,
    registry_service=_label_registry_service
)
_backfill_service = BackfillService(
    slot="default",
    review_repo=_review_repo,
    ground_truth_repo=_ground_truth_repo
)

# 三方精度评估器（per review_id）
_accuracy_evaluators: Dict[str, AccuracyEvaluator] = {}


# ============================================================================
# 闭环编排接口（Loop_Orchestrator）
# ============================================================================

@router.post("/loops", response_model=CreateLoopResponse)
async def create_loop(request: CreateLoopRequest):
    """
    创建/开启一轮迭代闭环
    
    映射需求: 12.1
    """
    try:
        loop_state = _orchestrator.create_loop(
            base_dataset_version=request.base_dataset_version
        )
        return CreateLoopResponse(
            loop_id=loop_state["loop_id"],
            iteration_round=loop_state["iteration_round"],
            stage=loop_state.get("stage")
        )
    except Exception as e:
        logger.error(f"Failed to create loop: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建迭代闭环失败: {str(e)}")


@router.post("/loops/{loop_id}/train", response_model=TrainResponse)
async def train(loop_id: str, request: TrainRequest):
    """
    触发训练评估（阶段 → trained）
    
    复用既有 workflow-pv-fault-diag-quickval-cv-v1 + stratified_cv_eval
    
    映射需求: 1.1, 1.9, 1.10, 1.11, 12.4
    """
    try:
        # 1. 触发训练评估工作流（复用既有）
        train_result = _orchestrator.trigger_train_eval(
            loop_id=loop_id,
            dataset_version=request.dataset_version,
            model_params=request.model_params or {}
        )
        
        # 2. 推进阶段并登记模型工件
        _orchestrator.advance_to_trained(
            loop_id=loop_id,
            dataset_version=request.dataset_version,
            model_ref=train_result["model_ref"],
            accuracy_record=train_result["accuracy_record"],
            label_space_snapshot=train_result["label_space_snapshot"]
        )
        
        return TrainResponse(
            model_ref=train_result["model_ref"],
            accuracy_record=train_result["accuracy_record"],
            label_space_snapshot=train_result["label_space_snapshot"]
        )
    except StageTransitionError as e:
        raise HTTPException(status_code=400, detail=f"阶段迁移错误: {str(e)}")
    except ValueError as e:
        # 捕获数据集缺列等错误
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to train: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"训练失败: {str(e)}")


@router.post("/loops/{loop_id}/predict", response_model=PredictResponse)
async def predict(loop_id: str, request: PredictRequest):
    """
    触发预测（阶段 trained → predicted）
    
    复用既有 workflow-pv-fault-diag-prediction-v1,禁止隐式重训
    
    映射需求: 2.1, 2.2, 2.3, 2.4, 2.5
    """
    try:
        if not request.model_ref:
            raise HTTPException(status_code=400, detail="model_ref 缺失,禁止隐式重训")
        
        # 1. 触发预测工作流（复用既有）
        predict_result = _orchestrator.trigger_predict(
            loop_id=loop_id,
            model_ref=request.model_ref,
            unlabeled_dataset_version=request.unlabeled_dataset_version
        )
        
        # 2. 推进阶段
        _orchestrator.advance_to_predicted(
            loop_id=loop_id,
            prediction_batch_id=predict_result["prediction_batch_id"]
        )
        
        return PredictResponse(
            prediction_batch_id=predict_result["prediction_batch_id"],
            unit_count=predict_result["unit_count"]
        )
    except StageTransitionError as e:
        raise HTTPException(status_code=400, detail=f"阶段迁移错误: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to predict: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"预测失败: {str(e)}")


@router.get("/loops/{loop_id}", response_model=GetLoopStateResponse)
async def get_loop_state(loop_id: str):
    """
    读取某轮闭环状态（只读,供 UI 展示当前处于哪一步）
    
    映射需求: 12.5
    """
    try:
        state = _orchestrator.get_loop_state(loop_id)
        return GetLoopStateResponse(**state)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"闭环 {loop_id} 不存在")
    except Exception as e:
        logger.error(f"Failed to get loop state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取闭环状态失败: {str(e)}")


@router.post("/loops/{loop_id}/backfill", response_model=BackfillResponse)
async def backfill(loop_id: str, request: BackfillRequest):
    """
    触发回流（阶段 reviewed → backfilled）
    
    排除 pending,组装为新数据集版本,可累积合并
    
    映射需求: 9.1, 9.2, 9.3, 9.4, 9.5
    """
    try:
        result = _backfill_service.backfill_from_review(
            review_id=request.review_id,
            loop_id=loop_id,
            merge_base=request.merge_base
        )
        # 推进阶段 reviewed → backfilled
        _orchestrator.advance_to_backfilled(
            loop_id=loop_id,
            dataset_version=result["dataset_version"]
        )
        return BackfillResponse(
            dataset_version=result["dataset_version"],
            unit_count=result["unit_count"]
        )
    except StageTransitionError as e:
        raise HTTPException(status_code=400, detail=f"阶段迁移错误: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to backfill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"回流失败: {str(e)}")


# ============================================================================
# 审核会话接口（Review_Session + Accuracy_Evaluator）
# ============================================================================

@router.get("/review-sessions", response_model=None)
async def list_review_sessions():
    """
    列出所有审核会话（供会话列表页展示,支持断点恢复入口）

    返回所有会话的摘要信息（review_id / status / reviewed_count / total_count / created_at）,
    按创建时间倒序。
    """
    try:
        import os, json
        from pathlib import Path
        data_root = os.environ.get('ITERATIVE_LABELING_DATA_ROOT', 'data/iterative_labeling')
        sessions_dir = Path(data_root) / 'review_results' / 'default'
        sessions = []
        if sessions_dir.exists():
            for f in sorted(sessions_dir.glob('*.json'), reverse=True):
                try:
                    d = json.loads(f.read_text(encoding='utf-8'))
                    sessions.append({
                        'review_id': d.get('review_id', f.stem),
                        'status': d.get('status', 'unknown'),
                        'reviewed_count': d.get('reviewed_count', 0),
                        'total_count': d.get('total_count', 0),
                        'loop_id': d.get('loop_id', ''),
                        'prediction_batch_id': d.get('prediction_batch_id', ''),
                    })
                except Exception:
                    pass
        return {'sessions': sessions}
    except Exception as e:
        logger.error(f"Failed to list review sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"列出审核会话失败: {str(e)}")


@router.post("/review-sessions", response_model=CreateReviewSessionResponse)
async def create_review_session(request: CreateReviewSessionRequest):
    """
    创建审核会话
    
    基于预测批次装配待审核单元,可选启用LLM辅助打标
    
    映射需求: 3.1, 7.1
    """
    try:
        # TODO: 从预测批次加载 prediction_units 和 llm_suggestions
        # 当前简化实现,实际需从 orchestrator 或预测结果存储中读取
        prediction_units = []  # 应从 prediction_batch_id 加载
        llm_suggestions = {} if not request.enable_llm else {}  # 应调用 LLM_Labeling_Assistant
        
        session = _review_session_service.create_session(
            loop_id=request.loop_id,
            prediction_batch_id=request.prediction_batch_id,
            prediction_units=prediction_units,
            llm_suggestions=llm_suggestions
        )
        
        # 初始化该会话的精度评估器
        _accuracy_evaluators[session["review_id"]] = AccuracyEvaluator()
        
        return CreateReviewSessionResponse(
            review_id=session["review_id"],
            total_count=session["total_count"]
        )
    except Exception as e:
        logger.error(f"Failed to create review session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建审核会话失败: {str(e)}")


def _norm_id_str(x: Any) -> str:
    """归一化标识符：浮点整数去小数，去空白。与 backfill 侧保持一致。"""
    if x is None:
        return ''
    if isinstance(x, float) and x.is_integer():
        return str(int(x))
    return str(x).strip()


async def _generate_llm_suggestions_bg(slot: str, review_id: str, registry_service: LabelRegistryService):
    """后台异步生成 GLM 建议，全部完成后一次性合并回会话（编辑器驱动，enable_llm=true 时触发）。"""
    try:
        from services.iterative_labeling.llm_labeling_assistant import generate_suggestion
        session = _review_repo.load_session(slot, review_id)
        if not session:
            return
        registry = registry_service.get_current()
        suggestions_by_key: Dict[str, Dict[str, Any]] = {}
        for unit in session.get('units', []):
            try:
                sugg = await generate_suggestion(unit, registry)
                suggestions_by_key[unit.get('unit_key')] = sugg
            except Exception as e:
                logger.warning(f"GLM 建议生成失败 unit={unit.get('unit_key')}: {e}")
        # 一次性合并回会话（重载最新状态，避免覆盖期间提交的裁决）
        fresh = _review_repo.load_session(slot, review_id)
        if not fresh:
            return
        for unit in fresh.get('units', []):
            sugg = suggestions_by_key.get(unit.get('unit_key'))
            if not sugg:
                continue
            unit['llm_suggestion'] = {
                'suggested_label': sugg.get('suggested_label'),
                'reason': sugg.get('reason', ''),
                'available': sugg.get('available', False),
                'out_of_registry': sugg.get('out_of_registry', False),
            }
            cp = unit.get('classifier_prediction') or {}
            pred = cp.get('predicted_label')
            sl = unit['llm_suggestion'].get('suggested_label')
            unit['disagreement'] = bool(pred is not None and sl is not None and pred != sl)
        _review_repo.save_verdict(slot, review_id, fresh)
        logger.info(f"GLM 建议已合并回会话 {review_id}（{len(suggestions_by_key)} 条）")
    except Exception as e:
        logger.error(f"后台 GLM 建议任务异常 review_id={review_id}: {e}", exc_info=True)


@router.post("/review-sessions/from-prediction", response_model=CreateReviewSessionResponse)
async def create_review_session_from_prediction(request: CreateReviewSessionFromPredictionRequest):
    """
    从工作流预测结果创建审核会话（编辑器驱动）

    用途：预测工作流执行完后，前端"人工审查打标"按钮携带预测结果与原始 CSV 上下文调用本接口，
    返回 review_id 后跳转打标页。不依赖 loop orchestrator。

    副作用：
    - 若标签注册表为空，用 label_map 播种（label_id = 故障码，保留跳号）
    - 在会话中存 prediction_context（原始 CSV 路径 + load/window 配置），供回流回贴原始时序
    - enable_llm=true 时后台异步生成 GLM 建议
    """
    try:
        slot = "default"
        registry_service = LabelRegistryService(slot=slot, registry_repo=_registry_repo)
        if request.label_map:
            registry_service.seed_labels(request.label_map)

        prediction_units = []
        for row in request.predictions:
            site = row.get('site_id')
            dev = row.get('device_id')
            br = row.get('branch_id')
            tw = row.get('time_window')
            pred = row.get('predictions', row.get('predicted_label'))
            if tw is None or dev is None:
                continue
            unit_key = f"{_norm_id_str(site)}|{_norm_id_str(dev)}|{_norm_id_str(br)}|{tw}"
            try:
                predicted_label = int(pred) if pred is not None and str(pred) != '' else None
            except (ValueError, TypeError):
                predicted_label = None
            prediction_units.append({
                'unit_key': unit_key,
                'site_id': site,
                'device_id': dev,
                'branch_id': br,
                'time_window': tw,
                'predicted_label': predicted_label,
                'confidence': row.get('confidence', 0.0),
            })

        if not prediction_units:
            raise HTTPException(status_code=422, detail="预测结果为空或缺少 device_id/time_window，无法建立审核单元")

        review_service = ReviewSessionService(
            slot=slot, review_repo=_review_repo, registry_service=registry_service
        )
        session = review_service.create_session(
            loop_id=request.loop_id or "editor",
            prediction_batch_id=f"editor-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            prediction_units=prediction_units,
            llm_suggestions={},
            prediction_context={
                'source_csv_path': request.source_csv_path,
                'load_config': request.load_config or {},
                'window_config': request.window_config or {},
                'label_map': request.label_map or {},
            }
        )
        _accuracy_evaluators[session["review_id"]] = AccuracyEvaluator()

        if request.enable_llm:
            import asyncio
            asyncio.create_task(_generate_llm_suggestions_bg(slot, session["review_id"], registry_service))

        return CreateReviewSessionResponse(
            review_id=session["review_id"],
            total_count=session["total_count"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create review session from prediction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"从预测结果创建审核会话失败: {str(e)}")


@router.post("/review-sessions/{review_id}/backfill-to-dataset", response_model=BackfillToDatasetResponse)
async def backfill_to_dataset(review_id: str, request: BackfillToDatasetRequest):
    """
    从审核会话回流，产出原始时序级训练数据集 CSV（编辑器驱动）

    把人工确认的窗口级标签回贴到原始预测时序的每一行，写出可直接喂回训练工作流的 CSV。
    返回的 csv_path 可直接粘贴到训练工作流 load_csv 节点的 file_path 开启下一轮。
    """
    try:
        bf = BackfillService(
            slot="default",
            review_repo=_review_repo,
            ground_truth_repo=_ground_truth_repo
        )
        result = bf.backfill_to_raw_dataset(
            review_id=review_id,
            merge_base=request.merge_base if request.merge_base is not None else True,
            base_csv_path=request.base_csv_path
        )
        return BackfillToDatasetResponse(**result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"审核会话 {review_id} 不存在")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to backfill to dataset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"回流产出数据集失败: {str(e)}")


@router.get("/data-preview")
async def data_preview(file_path: str, rows: int = 20):
    """
    读取 CSV/Parquet 文件前 N 行用于前端数据预览

    参数：
    - file_path: 文件绝对路径
    - rows: 返回行数,默认 20

    返回：{columns: [列名], rows: [{col:val}]}
    """
    try:
        import pandas as pd
        import os
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.parquet':
            df = pd.read_parquet(file_path).head(rows)
        else:
            df = pd.read_csv(file_path, nrows=rows)
        # 转 datetime 为字符串
        for col in df.select_dtypes(include=['datetime64']).columns:
            df[col] = df[col].astype(str)
        return {
            'columns': list(df.columns),
            'rows': df.fillna('').to_dict(orient='records'),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"data-preview failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据预览失败: {str(e)}")


# 参考波形缓存：label_map_key -> { label_id: {timestamps, series} }
_reference_waveform_cache: Dict[str, Dict[int, Dict[str, Any]]] = {}


@router.get("/reference-waveforms")
async def get_reference_waveforms(
    train_csv_path: str,
    label_csv_path: Optional[str] = None,
):
    """
    获取各故障类别的典型参考波形（供打标页对照）

    从训练数据中为每个故障类别各取一个典型窗口的时序波形。
    打标人员可以将当前待审单元曲线与各类参考曲线进行对比,辅助判断。

    参数：
    - train_csv_path: 带标签训练 CSV/parquet 路径（或两文件时的源文件路径）
    - label_csv_path: 可选,两文件模式时的标签文件路径

    返回：{categories: [{label_id, label_name, timestamps, series, point_count}]}
    """
    try:
        import pandas as pd
        from services.operator_backends import load_csv as load_csv_op
        from services.operator_backends import time_window_split as tws_op

        cache_key = f"{train_csv_path}|{label_csv_path or ''}"
        if cache_key in _reference_waveform_cache:
            cats = _reference_waveform_cache[cache_key]
            registry = _label_registry_service.get_current()
            label_names = {l['label_id']: l['label_name'] for l in registry.get('labels', [])}
            result = []
            for lid, data in sorted(cats.items()):
                result.append({
                    'label_id': lid,
                    'label_name': label_names.get(lid, f'故障{lid}'),
                    **data
                })
            return {'categories': result}

        # 加载训练数据
        df = load_csv_op.execute({'file_path': train_csv_path}, {}).get('data')
        if df is None or len(df) == 0:
            return {'categories': []}

        # 两文件模式:需要 merge_label
        if label_csv_path and 'label' not in df.columns:
            from services.operator_backends import merge_label as ml_op
            lbl = load_csv_op.execute({'file_path': label_csv_path}, {}).get('data')
            if lbl is not None:
                merged = ml_op.execute(
                    {'id_fields': ['site_id', 'device_id', 'branch_id'], 'time_field': 'time',
                     'label_col': 'custom_label_id', 'output_label_col': 'label'},
                    {'source_data': df, 'label_data': lbl}
                ).get('data')
                if merged is not None:
                    df = merged

        if 'label' not in df.columns:
            return {'categories': []}

        # 重算 time_window
        id_fields = [c for c in ['site_id', 'device_id', 'branch_id'] if c in df.columns]
        time_field = 'time' if 'time' in df.columns else df.columns[0]
        df = tws_op.execute(
            {'window': '1d', 'id_fields': id_fields, 'time_field': time_field},
            {'data': df}
        ).get('data')

        # 每类取一个最具代表性的窗口（i_cal 方差最大的窗口,白天有波动更有诊断意义）
        cats: Dict[int, Dict[str, Any]] = {}
        for label_id in sorted(df['label'].dropna().astype(int).unique()):
            sub = df[df['label'] == label_id]
            # 按 (device_id, time_window) 分组,取 i_cal 方差最大的组（波形最有特征）
            grp_cols = [c for c in ['device_id', 'time_window'] if c in sub.columns]
            if not grp_cols:
                continue
            # 计算每组的 i_cal 标准差（无 i_cal 时退回 value 标准差）
            var_col = 'i_cal' if 'i_cal' in sub.columns else ('value' if 'value' in sub.columns else None)
            if var_col:
                grp_var = sub.groupby(grp_cols)[var_col].std().reset_index(name='_var')
                grp_var = grp_var[grp_var['_var'] > 0]  # 排除全为 0 的窗口
                if len(grp_var) == 0:
                    # 退回行数最多
                    grp_var = sub.groupby(grp_cols).size().reset_index(name='_var')
                best = grp_var.loc[grp_var['_var'].idxmax()]
            else:
                counts = sub.groupby(grp_cols).size().reset_index(name='cnt')
                if len(counts) == 0:
                    continue
                best = counts.loc[counts['cnt'].idxmax()]
            mask = pd.Series([True] * len(sub), index=sub.index)
            for col in grp_cols:
                mask = mask & (sub[col] == best[col])
            window_df = sub[mask].sort_values(time_field).head(300)

            timestamps = [str(t) for t in window_df[time_field].tolist()] if time_field in window_df.columns else []
            series = {}
            for col in ['value', 'i_cal']:
                if col in window_df.columns:
                    series[col] = [None if pd.isna(v) else round(float(v), 4) for v in window_df[col].tolist()]
            cats[int(label_id)] = {
                'timestamps': timestamps,
                'series': series,
                'point_count': len(window_df),
            }

        # 限缓存大小
        if len(_reference_waveform_cache) >= 3:
            _reference_waveform_cache.clear()
        _reference_waveform_cache[cache_key] = cats

        # 附标签名称
        registry = _label_registry_service.get_current()
        label_names = {l['label_id']: l['label_name'] for l in registry.get('labels', [])}
        result = []
        for lid, data in sorted(cats.items()):
            result.append({
                'label_id': lid,
                'label_name': label_names.get(lid, f'故障{lid}'),
                **data
            })
        return {'categories': result}
    except Exception as e:
        logger.error(f"Failed to get reference waveforms: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取参考波形失败: {str(e)}")


# 单元时序缓存：source_csv_path -> 已重算 time_window 的 DataFrame（避免每次翻页重复加载）
_unit_timeseries_cache: Dict[str, Any] = {}


@router.get("/review-sessions/{review_id}/unit-timeseries")
async def get_unit_timeseries(review_id: str, unit_key: str):
    """
    读取某个待审核单元的原始时序波形（供打标页展示电压/电流曲线辅助人工判断）

    用途：打标时审核员需要看该 设备×支路×当天 的原始波形，而非只看预测标签。
    从会话 prediction_context.source_csv_path 加载原始 CSV，重算 time_window，
    过滤出该单元对应的原始行，返回时间戳 + 各测量序列。

    返回：{unit_key, time_window, timestamps, series:{value:[...], i_cal:[...]}, point_count}
    """
    try:
        review_repo = _review_repo
        session = review_repo.load_session("default", review_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"审核会话 {review_id} 不存在")

        # 定位单元组件
        unit = None
        for u in session.get('units', []):
            if u.get('unit_key') == unit_key:
                unit = u
                break
        if unit is None:
            raise HTTPException(status_code=404, detail=f"单元 {unit_key} 不存在")

        ctx = session.get('prediction_context') or {}
        source_csv_path = ctx.get('source_csv_path')
        if not source_csv_path:
            raise HTTPException(status_code=422, detail="会话缺少原始 CSV 路径，无法展示波形")
        load_config = ctx.get('load_config') or {}
        window_config = ctx.get('window_config') or {}

        import pandas as pd
        from services.operator_backends import load_csv as load_csv_op
        from services.operator_backends import time_window_split as tws_op

        # 缓存命中：直接用已重算 time_window 的 DataFrame
        df = _unit_timeseries_cache.get(source_csv_path)
        if df is None:
            df = load_csv_op.execute({
                'file_path': source_csv_path,
                'rename_columns': load_config.get('rename_columns'),
                'encoding': load_config.get('encoding', 'utf-8'),
                'delimiter': load_config.get('delimiter', ','),
            }, {}).get('data')
            id_fields = window_config.get('id_fields') or ['site_id', 'device_id', 'branch_id']
            time_field = window_config.get('time_field') or 'time'
            window = window_config.get('window') or '1d'
            df = tws_op.execute(
                {'window': window, 'id_fields': id_fields, 'time_field': time_field},
                {'data': df}
            ).get('data')
            # 简单限缓存大小，仅保留最近 2 个数据源
            if len(_unit_timeseries_cache) >= 2:
                _unit_timeseries_cache.clear()
            _unit_timeseries_cache[source_csv_path] = df

        time_field = (window_config.get('time_field') or 'time')

        def _nid(x):
            if x is None:
                return ''
            if isinstance(x, float) and x.is_integer():
                return str(int(x))
            return str(x).strip()

        def _ntw(x):
            try:
                return pd.to_datetime(x).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                return str(x)

        target = f"{_nid(unit.get('site_id'))}|{_nid(unit.get('device_id'))}|{_nid(unit.get('branch_id'))}|{_ntw(unit.get('time_window'))}"

        # 逐行构造键并过滤
        sub_idx = []
        site_col = df['site_id'] if 'site_id' in df.columns else None
        dev_col = df['device_id'] if 'device_id' in df.columns else None
        br_col = df['branch_id'] if 'branch_id' in df.columns else None
        tw_col = df['time_window'] if 'time_window' in df.columns else None
        for i in range(len(df)):
            k = f"{_nid(site_col.iloc[i]) if site_col is not None else ''}|" \
                f"{_nid(dev_col.iloc[i]) if dev_col is not None else ''}|" \
                f"{_nid(br_col.iloc[i]) if br_col is not None else ''}|" \
                f"{_ntw(tw_col.iloc[i]) if tw_col is not None else ''}"
            if k == target:
                sub_idx.append(i)

        sub = df.iloc[sub_idx].copy() if sub_idx else df.iloc[0:0].copy()
        if time_field in sub.columns:
            sub = sub.sort_values(time_field)

        timestamps = [str(t) for t in sub[time_field].tolist()] if time_field in sub.columns else []
        series = {}
        for col in ['value', 'i_cal']:
            if col in sub.columns:
                series[col] = [None if pd.isna(v) else float(v) for v in sub[col].tolist()]

        return {
            'unit_key': unit_key,
            'time_window': str(unit.get('time_window')),
            'timestamps': timestamps,
            'series': series,
            'point_count': len(sub),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get unit timeseries: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取单元时序失败: {str(e)}")


@router.get("/review-sessions/{review_id}", response_model=GetReviewSessionResponse)
async def get_review_session(review_id: str):
    """
    读取会话与进度（支持中断后恢复）
    
    映射需求: 3.3, 3.4
    """
    try:
        session_state = _review_session_service.get_session(review_id)
        return GetReviewSessionResponse(**session_state)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"审核会话 {review_id} 不存在")
    except Exception as e:
        logger.error(f"Failed to get review session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取审核会话失败: {str(e)}")


@router.post("/review-sessions/{review_id}/verdicts", response_model=SubmitVerdictResponse)
async def submit_verdict(review_id: str, request: SubmitVerdictRequest):
    """
    提交一条人工裁决
    
    confirm/correct/new_label 写真值,skip 标 pending 不写真值
    
    映射需求: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
    """
    try:
        result = _review_session_service.submit_verdict(
            review_id=review_id,
            unit_key=request.unit_key,
            action_type=request.action_type,
            verdict_label=request.verdict_label,
            new_label_name=request.new_label_name,
            reviewer=request.reviewer
        )
        
        # 增量更新三方精度
        if review_id in _accuracy_evaluators:
            evaluator = _accuracy_evaluators[review_id]
            # 从更新后的会话状态读取该单元的分类器预测与 LLM 建议
            classifier_prediction = {}
            llm_suggestion = None
            for u in result.get("session_state", {}).get("units", []):
                if u.get("unit_key") == request.unit_key:
                    classifier_prediction = u.get("classifier_prediction", {}) or {}
                    llm_suggestion = u.get("llm_suggestion")
                    break
            evaluator.update(
                verdict=result["verdict"],
                classifier_prediction=classifier_prediction,
                llm_suggestion=llm_suggestion
            )
            accuracy_snapshot = evaluator.get_current_accuracy()
        else:
            accuracy_snapshot = {}
        
        return SubmitVerdictResponse(
            accepted=result["accepted"],
            accuracy_snapshot=accuracy_snapshot
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to submit verdict: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"提交裁决失败: {str(e)}")


@router.get("/review-sessions/{review_id}/accuracy", response_model=GetAccuracyResponse)
async def get_accuracy(review_id: str):
    """
    读取当前三方精度
    
    映射需求: 6.1, 6.2, 6.3, 6.4, 6.5
    """
    try:
        if review_id not in _accuracy_evaluators:
            # 如果评估器不存在,返回占位
            return GetAccuracyResponse(
                classifier_accuracy=0.0,
                llm_accuracy=0.0,
                human_verified_accuracy=0.0,
                llm_coverage=0.0,
                macro={"precision": 0.0, "recall": 0.0, "f1": 0.0},
                counted_units=0
            )
        
        evaluator = _accuracy_evaluators[review_id]
        accuracy = evaluator.get_current_accuracy()
        return GetAccuracyResponse(**accuracy)
    except Exception as e:
        logger.error(f"Failed to get accuracy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取精度失败: {str(e)}")


# ============================================================================
# 标签注册表接口（Label_Registry）
# ============================================================================

@router.get("/label-registry", response_model=GetLabelRegistryResponse)
async def get_label_registry():
    """
    读取当前标签注册表（只读,供 UI 预填与审核选择）
    
    映射需求: 8.1, 8.2, 8.3
    """
    try:
        registry = _label_registry_service.get_current()
        return GetLabelRegistryResponse(
            label_space_version=registry["label_space_version"],
            labels=registry["labels"],
            label_map=registry["label_map"]
        )
    except Exception as e:
        logger.error(f"Failed to get label registry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取标签注册表失败: {str(e)}")


@router.post("/label-registry/labels", response_model=AddLabelResponse)
async def add_label(request: AddLabelRequest):
    """
    新增标签类别（标签扩充）
    
    分配唯一 label_id,生成新 label_space_version,保留历史快照
    
    映射需求: 8.1, 8.2, 8.5
    """
    try:
        label_id = _label_registry_service.allocate_label(request.label_name)
        registry = _label_registry_service.get_current()
        return AddLabelResponse(
            label_id=label_id,
            label_space_version=registry["label_space_version"]
        )
    except Exception as e:
        logger.error(f"Failed to add label: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"新增标签失败: {str(e)}")


@router.get("/label-registry/versions", response_model=GetLabelVersionsResponse)
async def get_label_versions():
    """
    读取历史版本快照列表（只读,审计/追溯）
    
    映射需求: 8.2
    """
    try:
        registry = _label_registry_service.get_current()
        return GetLabelVersionsResponse(
            history=registry.get("history", [])
        )
    except Exception as e:
        logger.error(f"Failed to get label versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取历史版本失败: {str(e)}")


# ============================================================================
# 迭代追踪接口（Iteration_Tracker）
# ============================================================================

@router.get("/iterations", response_model=GetIterationsResponse)
async def get_iterations():
    """
    读取迭代历史（按 iteration_round 排序,含趋势）
    
    映射需求: 10.1, 10.2, 10.3, 10.4, 10.5
    """
    try:
        iterations = _iteration_tracker.list_history()
        trend = _iteration_tracker.get_trend()
        return GetIterationsResponse(
            iterations=iterations,
            trend=trend
        )
    except Exception as e:
        logger.error(f"Failed to get iterations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取迭代历史失败: {str(e)}")
