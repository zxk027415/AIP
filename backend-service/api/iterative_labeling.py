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

# @AI_GENERATED: 正常光伏审核链路的 API 基础依赖
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import logging
import re
# @AI_GENERATED: end

# 导入服务层
from services.iterative_labeling.orchestrator import LoopOrchestrator, StageTransitionError
from services.iterative_labeling.review_session import ReviewSessionService
from services.iterative_labeling.label_registry import LabelRegistryService
from services.iterative_labeling.accuracy_evaluator import AccuracyEvaluator
from services.iterative_labeling.backfill import BackfillService
# @AI_GENERATED: 正常光伏累计训练集、不可变快照与重训请求服务
from services.iterative_labeling.cumulative_training import CumulativeTrainingService
# @AI_GENERATED: end
from services.iterative_labeling.iteration_tracker import IterationTracker
from services.iterative_labeling.storage.file_backend import (
    FileReviewResultRepository,
    FileLabelRegistryRepository,
    FileIterationHistoryRepository,
    FileGroundTruthRepository,
)

router = APIRouter(prefix="/api/iterative-labeling", tags=["iterative-labeling"])
logger = logging.getLogger(__name__)

# @AI_GENERATED: PV 仓储注入与训练工作台惰性初始化
from services.iterative_labeling.pv_training_workspace import PVTrainingWorkspaceService

_pv_repo_instance = None
_pv_workspace_instance: Optional[PVTrainingWorkspaceService] = None


def set_pv_fault_repository(repo) -> None:
    """由 main.py 在启动时注入 PVFaultRepository。"""
    global _pv_repo_instance
    _pv_repo_instance = repo


def _get_pv_workspace() -> PVTrainingWorkspaceService:
    global _pv_workspace_instance
    if _pv_workspace_instance is None:
        _pv_workspace_instance = PVTrainingWorkspaceService()
    return _pv_workspace_instance
# @AI_GENERATED: end

# ============================================================================
# 路径解析工具：所有文件路径统一相对项目根目录解析
# ============================================================================

import os as _os

# 项目根目录（backend-service 的父目录）
# __file__ = backend-service/api/iterative_labeling.py
# dirname x3 → AIP/ (项目根)
_PROJECT_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))


# 兼容旧中文路径：老 session 里可能存了 '相关数据'（现在目录名是 'relate_data'）
_LEGACY_PATH_ALIASES = {
    '/相关数据/': '/relate_data/',
    '\\相关数据\\': '\\relate_data\\',
}


def _apply_legacy_alias(path: str) -> str:
    """把老 session 里的中文目录名替换为当前实际目录名。"""
    if not path:
        return path
    for old, new in _LEGACY_PATH_ALIASES.items():
        if old in path:
            return path.replace(old, new)
    return path


def _resolve_data_path(path: str) -> str:
    """
    将前端传入的文件路径解析为可访问的绝对路径。

    路径约定（跨环境安全）：
      - 相对路径：相对于项目根 AIP/ 解析（如 `fault-diag-algo-release-3.1/xxx.parquet`）
      - `../` 前缀相对路径：相对于 backend-service/ 解析（如 `../fault-diag-algo-release-3.1/xxx.parquet`）
        —— 这是 load_csv 算子历史约定：工作流里 file_path 相对 CWD=backend-service
      - 绝对路径：优先直接使用；失效时尝试提取相对部分回退到项目根

    修复：老 session 可能存了 `../fault-diag-algo-release-3.1/...`，
    这里统一映射到 _PROJECT_ROOT 下的对应文件。
    """
    if not path:
        return path

    # 兼容旧中文目录名：'相关数据' → 'relate_data'
    path = _apply_legacy_alias(path)

    # 1. 相对路径：分两类处理
    if not _os.path.isabs(path):
        # 1a. `../` 前缀 → 相对 backend-service（load_csv 算子约定）
        if path.startswith('../') or path.startswith('..\\'):
            # backend-service = AIP/backend-service, 其父目录就是 _PROJECT_ROOT (AIP/)
            # 所以 ../fault-diag-algo-release-3.1/x == AIP/fault-diag-algo-release-3.1/x
            # 直接去掉 `../` 前缀，接到 _PROJECT_ROOT 后
            stripped = path[3:] if path.startswith('../') else path[3:]
            candidate = _os.path.join(_PROJECT_ROOT, stripped)
            if _os.path.exists(candidate):
                return candidate
            # 兜底：还是按原样拼接（供其他 backend-service/xxx 场景）
            backend_dir = _os.path.join(_PROJECT_ROOT, 'backend-service')
            return _os.path.normpath(_os.path.join(backend_dir, path))
        # 1b. 普通相对路径 → 相对项目根 AIP/
        return _os.path.join(_PROJECT_ROOT, path)

    # 2. 绝对路径：优先直接使用
    if _os.path.exists(path):
        return path

    # 3. 绝对路径但不存在（部署到新机器路径失效）：尝试提取相对部分回退到项目根
    for marker in ('backend-service/', 'fault-diag-algo-release', 'data/'):
        idx = path.find(marker)
        if idx != -1:
            relative = path[idx:]
            candidate = _os.path.join(_PROJECT_ROOT, relative)
            if _os.path.exists(candidate):
                return candidate
    return path


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

# @AI_GENERATED: 审核会话契约显式携带 slot，光伏正式链路缺省为 pv_fault，避免前端传值被 Pydantic 忽略后串入其他分区。
class CreateReviewSessionRequest(BaseModel):
    """创建审核会话请求"""
    loop_id: str = Field(..., description="所属迭代闭环 — 关联的loop")
    prediction_batch_id: str = Field(..., description="预测批次标识 — 基于哪一批预测结果")
    enable_llm: Optional[bool] = Field(True, description="启用LLM辅助 — 是否生成LLM建议")
    slot: str = Field("pv_fault", description="槽位 — 审核、标签和回流数据的隔离分区")
# @AI_GENERATED: end

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

# @AI_GENERATED: 人工裁决响应回传累计训练集准入、快照与重训申请状态
class SubmitVerdictResponse(BaseModel):
    """提交人工裁决响应"""
    accepted: bool = Field(..., description="是否接受 — 裁决是否成功提交")
    accuracy_snapshot: Dict[str, Any] = Field(..., description="精度快照 — 当前三方精度")
    cumulative_training: Dict[str, Any] = Field(
        default_factory=dict,
        description="累计训练集状态 — 有效人工真值的准入、阈值与重训请求信息",
    )


class RegisterCumulativeTrainingImportRequest(BaseModel):
    """登记带真值导入数据到正常累计训练集。"""
    dataset_path: str = Field(..., description="带 label 列的 CSV/Parquet 相对项目根目录路径")
    source_name: Optional[str] = Field(None, description="导入来源说明 — 仅用于审计展示")
# @AI_GENERATED: end

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


class ReconcileLabelItem(BaseModel):
    """按训练数据中的既有编码补登记业务名称。"""
    label_id: int = Field(..., ge=0, description="训练快照中已存在的标签编码")
    label_name: str = Field(..., min_length=1, description="人工确认的业务名称")


class ReconcileLabelsRequest(BaseModel):
    """批量补齐快照标签到注册表。"""
    labels: List[ReconcileLabelItem] = Field(..., min_length=1)


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

# @AI_GENERATED: 编辑器预测→审核契约中的 slot 和相对路径输出
class CreateReviewSessionFromPredictionRequest(BaseModel):
    """从工作流预测结果创建审核会话（编辑器驱动）"""
    predictions: List[Dict[str, Any]] = Field(..., description="预测结果数组 — 来自预测工作流 faultPredictions,每项含 site_id/device_id/branch_id/time_window/predictions")
    source_csv_path: str = Field(..., description="原始预测 CSV 路径 — 必须相对项目根目录，回流时回贴原始时序用")
    load_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="load_csv 配置 — rename_columns/encoding/delimiter,回流时复用")
    window_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="time_window_split 配置 — window/id_fields/time_field,回流重算窗口键用")
    label_map: Optional[Dict[str, int]] = Field(default_factory=dict, description="标签映射 — 业务名→故障码,用于播种标签注册表与展示")
    enable_llm: Optional[bool] = Field(False, description="启用GLM辅助 — 后台异步生成建议,完成后刷新可见")
    loop_id: Optional[str] = Field(None, description="所属迭代闭环 — 可选,编辑器驱动可不传")
    reviewer: Optional[str] = Field("operator", description="审核人标识")
    slot: str = Field("default", description="槽位 — 审核、标签和累计训练集的隔离分区")


class CreateManualReviewFromDatasetRequest(BaseModel):
    """从无标签数据集创建逐单元人工标注会话。"""
    dataset_path: str = Field(..., description="相对项目根目录的数据集路径")
    slot: str = Field("pv_fault", description="审核槽位")
    reviewer: str = Field("operator", description="审核人")
    max_units: int = Field(500, ge=1, le=5000, description="单次人工标注单元上限")


class BackfillToDatasetRequest(BaseModel):
    """从审核会话回流产出原始时序数据集"""
    merge_base: Optional[bool] = Field(True, description="累积合并 — 是否拼接基线训练 CSV,默认true")
    base_csv_path: Optional[str] = Field(None, description="基线训练 CSV 相对路径 — merge_base=true 时拼接到新数据集前")

class BackfillToDatasetResponse(BaseModel):
    """回流产出数据集响应"""
    dataset_version: str = Field(..., description="新数据集版本号")
    csv_path: str = Field(..., description="新数据集 CSV 相对项目根目录路径，可直接填写到训练工作流 load_csv.file_path")
    labeled_rows: int = Field(..., description="标注后原始行数 — 回贴标签后的总行数")
    labeled_units: int = Field(..., description="标注单元数 — 去重后的设备×窗口数")
    total_source_rows: int = Field(..., description="原始预测 CSV 总行数")
# @AI_GENERATED: end


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

# 三方精度评估器（按 slot + review_id 隔离）
_accuracy_evaluators: Dict[Tuple[str, str], AccuracyEvaluator] = {}

# @AI_GENERATED: 默认累计训练账本、重训编排和 slot 隔离服务
_cumulative_training_services: Dict[str, CumulativeTrainingService] = {}
_orchestrators_by_slot: Dict[str, LoopOrchestrator] = {"default": _orchestrator}
_SLOT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _normalize_slot(slot: Optional[str]) -> str:
    normalized = str(slot or "default").strip()
    if not _SLOT_NAME_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=422,
            detail="slot 只能包含字母、数字、下划线和连字符，长度为 1 到 64",
        )
    return normalized


def _registry_for_slot(slot: str) -> LabelRegistryService:
    return LabelRegistryService(slot=slot, registry_repo=_registry_repo)


def _review_service_for_slot(slot: str) -> ReviewSessionService:
    return ReviewSessionService(
        slot=slot,
        review_repo=_review_repo,
        registry_service=_registry_for_slot(slot),
    )


def _cumulative_training_for_slot(slot: str) -> CumulativeTrainingService:
    service = _cumulative_training_services.get(slot)
    if service is None:
        service = CumulativeTrainingService(slot=slot, review_repo=_review_repo)
        _cumulative_training_services[slot] = service
    return service


def _orchestrator_for_slot(slot: str) -> LoopOrchestrator:
    orchestrator = _orchestrators_by_slot.get(slot)
    if orchestrator is None:
        orchestrator = LoopOrchestrator(slot=slot)
        _orchestrators_by_slot[slot] = orchestrator
    return orchestrator


def _accuracy_key(slot: str, review_id: str) -> Tuple[str, str]:
    return slot, review_id
# @AI_GENERATED: end

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
        
        # @AI_GENERATED: 编排器内部已完成一次状态迁移，API 层不得重复推进
        # trigger_train_eval 已在真实工作流成功后完成唯一一次阶段推进。
        # @AI_GENERATED: end
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
        
        # @AI_GENERATED: 编排器内部已完成一次状态迁移，API 层不得重复推进
        # trigger_predict 已在真实工作流成功后完成唯一一次阶段推进。
        # @AI_GENERATED: end
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
        # @AI_GENERATED: 回流必须带来源轮次，并使用正确的新数据集版本参数推进状态
        loop_state = _orchestrator.get_loop_state(loop_id)
        result = _backfill_service.backfill_from_review(
            review_id=request.review_id,
            loop_id=loop_id,
            source_iteration=loop_state["iteration_round"],
            base_dataset_version=loop_state.get("dataset_version"),
            merge_base=request.merge_base,
        )
        # 推进阶段 reviewed → backfilled
        _orchestrator.advance_to_backfilled(
            loop_id=loop_id,
            new_dataset_version=result["dataset_version"],
        )
        # @AI_GENERATED: end
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
async def list_review_sessions(slot: str = "default"):
    """
    列出所有审核会话（供会话列表页展示,支持断点恢复入口）

    返回所有会话的摘要信息（review_id / status / reviewed_count / total_count / created_at）,
    按创建时间倒序。
    """
    try:
        import os, json
        from pathlib import Path
        resolved_slot = _normalize_slot(slot)
        data_root = os.environ.get('ITERATIVE_LABELING_DATA_ROOT', 'data/iterative_labeling')
        sessions_dir = Path(data_root) / 'review_results' / resolved_slot
        sessions = []
        if sessions_dir.exists():
            for f in sessions_dir.glob('*.json'):
                try:
                    d = json.loads(f.read_text(encoding='utf-8'))
                    sessions.append({
                        'review_id': d.get('review_id', f.stem),
                        'status': d.get('status', 'unknown'),
                        'reviewed_count': d.get('reviewed_count', 0),
                        'total_count': d.get('total_count', 0),
                        'loop_id': d.get('loop_id', ''),
                        'prediction_batch_id': d.get('prediction_batch_id', ''),
                        '_updated_timestamp': f.stat().st_mtime,
                    })
                except Exception:
                    pass
        sessions.sort(key=lambda item: item.get('_updated_timestamp', 0), reverse=True)
        for session in sessions:
            session.pop('_updated_timestamp', None)
        return {'sessions': sessions}
    except Exception as e:
        logger.error(f"Failed to list review sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"列出审核会话失败: {str(e)}")


# @AI_GENERATED: 正常 loop 预测批次持久化后可直接建立审核会话，避免空 prediction_units
@router.post("/review-sessions", response_model=CreateReviewSessionResponse)
async def create_review_session(request: CreateReviewSessionRequest):
    """从已持久化的真实预测批次创建审核会话。"""
    try:
        import json
        from pathlib import Path

        slot = _normalize_slot(request.slot)
        batch_id = str(request.prediction_batch_id or "").strip()
        if not re.fullmatch(r"pred-[A-Za-z0-9-]+", batch_id):
            raise HTTPException(status_code=422, detail="prediction_batch_id 格式不合法")
        batch_path = (
            Path(_PROJECT_ROOT)
            / "backend-service"
            / "data"
            / "iterative_labeling"
            / "prediction_batches"
            / slot
            / f"{batch_id}.json"
        )
        if not batch_path.exists():
            raise HTTPException(status_code=404, detail=f"预测批次不存在: {batch_id}")
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        source_csv_path = batch.get("dataset_version")
        if not isinstance(source_csv_path, str) or not source_csv_path or _os.path.isabs(source_csv_path):
            raise HTTPException(status_code=422, detail="预测批次缺少相对 source dataset 路径")

        prediction_units = []
        for row in batch.get("predictions") or []:
            site = row.get("site_id")
            device = row.get("device_id")
            branch = row.get("branch_id")
            time_window = row.get("time_window")
            if device is None or time_window is None:
                continue
            prediction_units.append(
                {
                    "unit_key": f"{_norm_id_str(site)}|{_norm_id_str(device)}|{_norm_id_str(branch)}|{time_window}",
                    "site_id": site,
                    "device_id": device,
                    "branch_id": branch,
                    "time_window": time_window,
                    "predicted_label": row.get("predicted_label"),
                    "confidence": row.get("confidence", 0.0),
                }
            )
        if not prediction_units:
            raise HTTPException(status_code=422, detail="预测批次没有可审核的诊断单元")

        registry_service = _registry_for_slot(slot)
        session = _review_service_for_slot(slot).create_session(
            loop_id=request.loop_id,
            prediction_batch_id=batch_id,
            prediction_units=prediction_units,
            llm_suggestions={},
            prediction_context={
                "source_csv_path": source_csv_path,
                "load_config": {},
                "window_config": {},
                "label_map": registry_service.get_current().get("label_map", {}),
            },
        )
        _accuracy_evaluators[_accuracy_key(slot, session["review_id"])] = AccuracyEvaluator()
        if request.enable_llm:
            import asyncio
            asyncio.create_task(_generate_llm_suggestions_bg(slot, session["review_id"], registry_service))
        return CreateReviewSessionResponse(
            review_id=session["review_id"],
            total_count=session["total_count"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to create review session from prediction batch: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建审核会话失败: {exc}")
# @AI_GENERATED: end


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


# @AI_GENERATED: 从工作流预测创建会话时持久化请求 slot，而非写死 default
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
        slot = _normalize_slot(request.slot)
        if _os.path.isabs(request.source_csv_path):
            raise HTTPException(status_code=422, detail="source_csv_path 必须使用相对项目根目录路径")
        registry_service = _registry_for_slot(slot)
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
        _accuracy_evaluators[_accuracy_key(slot, session["review_id"])] = AccuracyEvaluator()

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


@router.post("/review-sessions/from-dataset", response_model=CreateReviewSessionResponse)
async def create_manual_review_from_dataset(request: CreateManualReviewFromDatasetRequest):
    """把上传的无标签 CSV/Parquet 按设备×日期聚合为人工标注会话。"""
    try:
        import pandas as pd

        slot = _normalize_slot(request.slot)
        if _os.path.isabs(request.dataset_path):
            raise HTTPException(status_code=422, detail="dataset_path 必须使用相对项目根目录路径")
        resolved = _resolve_data_path(request.dataset_path)
        if not _os.path.exists(resolved):
            raise HTTPException(status_code=404, detail=f"数据集不存在: {request.dataset_path}")
        extension = _os.path.splitext(resolved)[1].lower()
        frame = pd.read_parquet(resolved) if extension == ".parquet" else pd.read_csv(resolved)
        if frame.empty:
            raise HTTPException(status_code=422, detail="数据集为空，无法创建人工标注会话")
        if "device_id" not in frame.columns:
            raise HTTPException(status_code=422, detail="手工标注数据集缺少 device_id 列")

        if "time_window" in frame.columns:
            time_windows = frame["time_window"].astype(str)
        elif "time" in frame.columns:
            time_windows = pd.to_datetime(frame["time"], errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            raise HTTPException(status_code=422, detail="手工标注数据集缺少 time 或 time_window 列")

        working = frame.copy()
        working["_manual_time_window"] = time_windows
        working = working[working["_manual_time_window"].notna()]
        unit_fields = [
            field
            for field in ("site_id", "device_id", "branch_id", "_manual_time_window")
            if field in working.columns
        ]
        units_frame = working.drop_duplicates(subset=unit_fields).head(request.max_units)
        prediction_units = []
        for _, row in units_frame.iterrows():
            site = row.get("site_id")
            device = row.get("device_id")
            branch = row.get("branch_id")
            time_window = row.get("_manual_time_window")
            raw_label = row.get("label")
            try:
                predicted_label = int(raw_label) if pd.notna(raw_label) else None
            except (TypeError, ValueError):
                predicted_label = None
            prediction_units.append(
                {
                    "unit_key": (
                        f"{_norm_id_str(site)}|{_norm_id_str(device)}|"
                        f"{_norm_id_str(branch)}|{time_window}"
                    ),
                    "site_id": site,
                    "device_id": device,
                    "branch_id": branch,
                    "time_window": time_window,
                    "predicted_label": predicted_label,
                    "confidence": 1.0 if predicted_label is not None else 0.0,
                }
            )
        if not prediction_units:
            raise HTTPException(status_code=422, detail="未生成可标注的设备×日期单元")

        session = _review_service_for_slot(slot).create_session(
            loop_id=f"manual-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            prediction_batch_id=f"manual-dataset-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            prediction_units=prediction_units,
            llm_suggestions={},
            prediction_context={
                "source_csv_path": request.dataset_path,
                "manual_labeling": True,
                "reviewer": request.reviewer,
                "window_config": {"time_field": "time", "window": "1D"},
            },
        )
        _accuracy_evaluators[_accuracy_key(slot, session["review_id"])] = AccuracyEvaluator()
        return CreateReviewSessionResponse(
            review_id=session["review_id"],
            total_count=session["total_count"],
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("create_manual_review_from_dataset failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建人工标注会话失败: {exc}")


# @AI_GENERATED: end

# @AI_GENERATED: 回流数据集按 slot 隔离，并保持 API 返回相对路径
@router.post("/review-sessions/{review_id}/backfill-to-dataset", response_model=BackfillToDatasetResponse)
async def backfill_to_dataset(
    review_id: str,
    request: BackfillToDatasetRequest,
    slot: str = "default",
):
    """将审核真值回贴为指定槽位的原始时序训练数据集。"""
    try:
        resolved_slot = _normalize_slot(slot)
        service = BackfillService(
            slot=resolved_slot,
            review_repo=_review_repo,
            ground_truth_repo=_ground_truth_repo,
        )
        result = service.backfill_to_raw_dataset(
            review_id=review_id,
            merge_base=request.merge_base if request.merge_base is not None else True,
            base_csv_path=_resolve_data_path(request.base_csv_path) if request.base_csv_path else None,
        )
        return BackfillToDatasetResponse(**result)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"审核会话 {review_id} 不存在")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to backfill to dataset: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"回流产出数据集失败: {str(e)}")
# @AI_GENERATED: end


@router.get("/data-preview")
async def data_preview(file_path: str, rows: int = 20):
    """
    读取 CSV/Parquet 文件前 N 行用于前端数据预览

    参数：
    - file_path: 文件路径（相对于项目根目录，或绝对路径兼容旧调用）
    - rows: 返回行数,默认 20

    返回：{columns: [列名], rows: [{col:val}]}
    """
    try:
        import pandas as pd
        import os
        resolved = _resolve_data_path(file_path)
        if not os.path.exists(resolved):
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}")
        ext = os.path.splitext(resolved)[1].lower()
        if ext == '.parquet':
            df = pd.read_parquet(resolved).head(rows)
        else:
            df = pd.read_csv(resolved, nrows=rows)
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


# @AI_GENERATED: 参考波形标签名按 slot 解析，缓存键包含 slot
@router.get("/reference-waveforms")
def get_reference_waveforms(
    train_csv_path: str,
    label_csv_path: Optional[str] = None,
    slot: str = "default",
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

        # 解析相对路径
        resolved_train = _resolve_data_path(train_csv_path)
        resolved_label = _resolve_data_path(label_csv_path) if label_csv_path else None

        resolved_slot = _normalize_slot(slot)
        cache_key = f"{resolved_slot}|{resolved_train}|{resolved_label or ''}"
        if cache_key in _reference_waveform_cache:
            cats = _reference_waveform_cache[cache_key]
            registry = _registry_for_slot(resolved_slot).get_current()
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
        df = load_csv_op.execute({'file_path': resolved_train}, {}).get('data')
        if df is None or len(df) == 0:
            return {'categories': []}

        # 两文件模式:需要 merge_label
        if resolved_label and 'label' not in df.columns:
            from services.operator_backends import merge_label as ml_op
            lbl = load_csv_op.execute({'file_path': resolved_label}, {}).get('data')
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
        registry = _registry_for_slot(resolved_slot).get_current()
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


# @AI_GENERATED: end

# 单元时序缓存：source_csv_path -> 已重算 time_window 的 DataFrame（避免每次翻页重复加载）
_unit_timeseries_cache: Dict[str, Any] = {}


# @AI_GENERATED: 单元波形按 slot 读取审核上下文
@router.get("/review-sessions/{review_id}/unit-timeseries")
async def get_unit_timeseries(review_id: str, unit_key: str, slot: str = "default"):
    """
    读取某个待审核单元的原始时序波形（供打标页展示电压/电流曲线辅助人工判断）

    用途：打标时审核员需要看该 设备×支路×当天 的原始波形，而非只看预测标签。
    从会话 prediction_context.source_csv_path 加载原始 CSV，重算 time_window，
    过滤出该单元对应的原始行，返回时间戳 + 各测量序列。

    返回：{unit_key, time_window, timestamps, series:{value:[...], i_cal:[...]}, point_count}
    """
    try:
        resolved_slot = _normalize_slot(slot)
        review_repo = _review_repo
        session = review_repo.load_session(resolved_slot, review_id)
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
        # 解析相对路径
        source_csv_path = _resolve_data_path(source_csv_path)
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


# @AI_GENERATED: end

# @AI_GENERATED: 审核会话按 query slot 读取，避免同名 review_id 跨槽位串数据
@router.get("/review-sessions/{review_id}", response_model=GetReviewSessionResponse)
async def get_review_session(review_id: str, slot: str = "default"):
    """读取会话与进度（支持中断后恢复）。"""
    try:
        resolved_slot = _normalize_slot(slot)
        session_state = _review_service_for_slot(resolved_slot).get_session(review_id)
        if not session_state:
            raise KeyError(review_id)
        return GetReviewSessionResponse(**session_state)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"审核会话 {review_id} 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get review session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取审核会话失败: {str(e)}")
# @AI_GENERATED: end


# @AI_GENERATED: 裁决持久化后立即同步正常累计训练集；账本异常结构化回传，避免已保存裁决被错误回滚
@router.post("/review-sessions/{review_id}/verdicts", response_model=SubmitVerdictResponse)
async def submit_verdict(review_id: str, request: SubmitVerdictRequest, slot: str = "default"):
    """提交人工裁决、更新精度，并把有效真值写入唯一累计训练集。"""
    try:
        resolved_slot = _normalize_slot(slot)
        review_service = _review_service_for_slot(resolved_slot)
        result = review_service.submit_verdict(
            review_id=review_id,
            unit_key=request.unit_key,
            action_type=request.action_type,
            verdict_label=request.verdict_label,
            new_label_name=request.new_label_name,
            reviewer=request.reviewer,
        )

        evaluator_key = _accuracy_key(resolved_slot, review_id)
        if evaluator_key in _accuracy_evaluators:
            evaluator = _accuracy_evaluators[evaluator_key]
            classifier_prediction: Dict[str, Any] = {}
            llm_suggestion = None
            for unit in result.get("session_state", {}).get("units", []):
                if unit.get("unit_key") == request.unit_key:
                    classifier_prediction = unit.get("classifier_prediction", {}) or {}
                    llm_suggestion = unit.get("llm_suggestion")
                    break
            evaluator.update(
                verdict=result["verdict"],
                classifier_prediction=classifier_prediction,
                llm_suggestion=llm_suggestion,
            )
            accuracy_snapshot = evaluator.get_current_accuracy()
        else:
            accuracy_snapshot = {}

        try:
            cumulative_training = _cumulative_training_for_slot(resolved_slot).admit_verdict(
                review_id=review_id,
                session=result["session_state"],
                verdict=result["verdict"],
            )
        except Exception as admission_error:  # 审核裁决已原子持久化，不能为账本失败而伪装为未提交。
            logger.error(
                "Cumulative training admission failed review_id=%s unit_key=%s: %s",
                review_id,
                request.unit_key,
                admission_error,
                exc_info=True,
            )
            cumulative_training = {
                "admitted": False,
                "admission_error": str(admission_error),
                "action_required": "修复累计训练集准入错误后，重新提交同一裁决以重试",
            }

        return SubmitVerdictResponse(
            accepted=result["accepted"],
            accuracy_snapshot=accuracy_snapshot,
            cumulative_training=cumulative_training,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to submit verdict: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"提交裁决失败: {str(e)}")
# @AI_GENERATED: end


# @AI_GENERATED: 三方精度评估器按 slot + review_id 分区
@router.get("/review-sessions/{review_id}/accuracy", response_model=GetAccuracyResponse)
async def get_accuracy(review_id: str, slot: str = "default"):
    """读取当前审核会话的三方精度。"""
    try:
        evaluator = _accuracy_evaluators.get(_accuracy_key(_normalize_slot(slot), review_id))
        if evaluator is None:
            return GetAccuracyResponse(
                classifier_accuracy=0.0,
                llm_accuracy=0.0,
                human_verified_accuracy=0.0,
                llm_coverage=0.0,
                macro={"precision": 0.0, "recall": 0.0, "f1": 0.0},
                counted_units=0,
            )
        return GetAccuracyResponse(**evaluator.get_current_accuracy())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get accuracy: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取精度失败: {str(e)}")
# @AI_GENERATED: end


# @AI_GENERATED: 正常累计训练集 API（状态、带真值导入、阈值请求的显式训练）
@router.get("/cumulative-training/state")
async def get_cumulative_training_state(slot: str = "default"):
    """读取指定槽位唯一累计训练集的准入、快照和重训申请状态。"""
    try:
        return _cumulative_training_for_slot(_normalize_slot(slot)).get_state()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to get cumulative training state: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取累计训练集状态失败: {exc}")


@router.post("/cumulative-training/imports")
async def register_cumulative_training_import(
    request: RegisterCumulativeTrainingImportRequest,
    slot: str = "default",
):
    """登记带 label 的历史/数据库导入数据；无真值数据不会被当作训练样本。"""
    try:
        return _cumulative_training_for_slot(_normalize_slot(slot)).register_labeled_dataset(
            dataset_path=request.dataset_path,
            source_name=request.source_name,
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to register cumulative training import: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"登记累计训练导入失败: {exc}")


@router.post("/cumulative-training/retrain-requests/{request_id}/run")
async def run_cumulative_retrain_request(request_id: str, slot: str = "default"):
    """使用不可变累计快照训练；成功后原子切换为该槽位生产模型。"""
    import asyncio

    resolved_slot = _normalize_slot(slot)
    service = _cumulative_training_for_slot(resolved_slot)
    try:
        retrain_request = service.get_retrain_request(request_id)
        if retrain_request.get("status") != "queued":
            raise HTTPException(
                status_code=409,
                detail=f"重训请求当前状态为 {retrain_request.get('status')}，仅 queued 状态可执行",
            )
        service.mark_retrain_request(request_id, "running")
        service.update_retrain_progress(
            request_id,
            stage="preparing_snapshot",
            percent=10,
            message="正在校验不可变训练快照",
        )
        try:
            orchestrator = _orchestrator_for_slot(resolved_slot)
            loop = orchestrator.create_loop(base_dataset_version=retrain_request["dataset_path"])
            service.update_retrain_progress(
                request_id,
                stage="training_and_evaluation",
                percent=25,
                message="正在训练模型并执行分层交叉验证",
            )
            train_result = await asyncio.to_thread(
                orchestrator.trigger_train_eval,
                loop_id=loop["loop_id"],
                dataset_version=retrain_request["dataset_path"],
            )
            service.update_retrain_progress(
                request_id,
                stage="registering_model",
                percent=82,
                message="训练评估完成，正在登记模型版本",
            )
            if resolved_slot == "pv_fault":
                if _pv_repo_instance is None:
                    raise RuntimeError("PVFaultRepository 未注入，模型版本无法登记，生产模型未切换")
                label_space = train_result.get("label_space_snapshot") or {}
                _pv_repo_instance.save_model_version(
                    {
                        "id": train_result["model_ref"],
                        "version_tag": train_result["model_ref"],
                        "training_sample_count": retrain_request.get("sample_count"),
                        "label_space_version": label_space.get("label_space_version"),
                        "artifact_path": train_result.get("model_path"),
                    }
                )
            service.update_retrain_progress(
                request_id,
                stage="promoting_model",
                percent=94,
                message="正在原子切换生产模型",
            )
            completed = service.mark_retrain_request(
                request_id,
                "completed",
                model_ref=train_result["model_ref"],
                train_summary={
                    "model_ref": train_result.get("model_ref"),
                    "model_path": train_result.get("model_path"),
                    "accuracy_record": train_result.get("accuracy_record"),
                    "label_space_snapshot": train_result.get("label_space_snapshot"),
                },
            )
        except Exception as training_error:
            service.mark_retrain_request(request_id, "failed", error=str(training_error))
            raise
        return {
            "request": completed,
            "loop_id": loop["loop_id"],
            "train_result": train_result,
            "publication": "auto_promoted",
            "production_model_ref": completed.get("model_ref"),
        }
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"重训请求不存在: {request_id}")
    except Exception as exc:
        logger.error("Failed to run cumulative retrain request %s: %s", request_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"累计训练重训失败: {exc}")
# @AI_GENERATED: end


# ============================================================================
# 标签注册表接口（Label_Registry）
# ============================================================================

# @AI_GENERATED: 标签注册表按 slot 读取，避免不同业务场景混用标签空间
@router.get("/label-registry", response_model=GetLabelRegistryResponse)
async def get_label_registry(slot: str = "default"):
    """读取指定槽位的当前标签注册表。"""
    try:
        registry = _registry_for_slot(_normalize_slot(slot)).get_current()
        return GetLabelRegistryResponse(
            label_space_version=registry["label_space_version"],
            labels=registry["labels"],
            label_map=registry["label_map"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get label registry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取标签注册表失败: {str(e)}")
# @AI_GENERATED: end


# @AI_GENERATED: 新标签写入请求指定的 slot，避免跨场景扩充标签
@router.post("/label-registry/labels", response_model=AddLabelResponse)
async def add_label(request: AddLabelRequest, slot: str = "default"):
    """在指定槽位新增标签类别。"""
    try:
        registry_service = _registry_for_slot(_normalize_slot(slot))
        label_id = registry_service.allocate_label(request.label_name)
        registry = registry_service.get_current()
        return AddLabelResponse(
            label_id=label_id,
            label_space_version=registry["label_space_version"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add label: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"新增标签失败: {str(e)}")
# @AI_GENERATED: end


@router.post("/label-registry/reconcile", response_model=GetLabelRegistryResponse)
async def reconcile_label_registry(request: ReconcileLabelsRequest, slot: str = "default"):
    """保留训练快照中的原始 label_id，补齐业务名称并生成注册表新版本。"""
    try:
        labels_by_id: Dict[int, str] = {}
        for item in request.labels:
            if item.label_id in labels_by_id:
                raise ValueError(f"标签 ID {item.label_id} 重复提交")
            labels_by_id[item.label_id] = item.label_name
        registry = _registry_for_slot(_normalize_slot(slot)).reconcile_labels(labels_by_id)
        return GetLabelRegistryResponse(
            label_space_version=registry["label_space_version"],
            labels=registry["labels"],
            label_map=registry["label_map"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("Failed to reconcile label registry: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"标签注册表对账失败: {exc}")


@router.get("/label-registry/versions", response_model=GetLabelVersionsResponse)
async def get_label_versions(slot: str = "default"):
    """
    读取历史版本快照列表（只读,审计/追溯）
    
    映射需求: 8.2
    """
    try:
        registry = _registry_for_slot(_normalize_slot(slot)).get_current()
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


# @AI_GENERATED: 训练候选数据审查、聚类运行/确认、时间切片标注和预测批次读取
# ============================================================================
# 训练数据准入（Training Candidates + Clustering + Time Slices）
# ============================================================================


class CreateClusteringRunRequest(BaseModel):
    """创建聚类 run 请求"""
    n_clusters: int = Field(5, ge=2, le=30, description="聚类数")
    label_status: str = Field("unlabeled", description="候选筛选：unlabeled/labeled/all")
    page_size: int = Field(500, ge=10, le=500, description="候选样本最大数量")
    site_id: Optional[str] = Field(None, description="站点过滤")
    time_start: Optional[str] = Field(None, description="起始时间 ISO")
    time_end: Optional[str] = Field(None, description="结束时间 ISO")
    reviewer: str = Field("operator", description="操作者")
    dataset_path: Optional[str] = Field(None, description="可选：相对项目根目录的数据集路径")


class UpdateClusterRequest(BaseModel):
    """更新簇信息请求"""
    proposed_label_name: Optional[str] = Field(None, description="人工命名")
    selected_member_keys: Optional[List[str]] = Field(None, description="选中成员键列表")


class ConfirmClusteringRunRequest(BaseModel):
    """二次确认聚类 run 请求"""
    confirm_inclusion: bool = Field(..., description="必须为 true 才执行确认")


class CreateTimeSliceRequest(BaseModel):
    """时间切片标注请求"""
    source_path: str = Field(..., description="源 CSV/Parquet 相对项目根路径")
    time_start: str = Field(..., description="起始时间 ISO")
    time_end: str = Field(..., description="结束时间 ISO")
    label_id: int = Field(..., description="标注标签 ID")
    confirm_inclusion: bool = Field(..., description="必须为 true 才登记累计训练集")
    site_id: Optional[str] = Field(None)
    device_id: Optional[str] = Field(None)
    branch_id: Optional[str] = Field(None)
    reviewer: str = Field("operator")


@router.get("/training-candidates")
async def get_training_candidates(
    page: int = 1,
    page_size: int = 100,
    label_status: Optional[str] = None,
    site_id: Optional[str] = None,
    time_start: Optional[str] = None,
    time_end: Optional[str] = None,
):
    """分页读取 pv_fault 数据库中的候选训练样本。

    需要 main.py 启动时注入 PVFaultRepository，否则返回 503。
    """
    if _pv_repo_instance is None:
        raise HTTPException(status_code=503, detail="PV 数据源未连接（PVFaultRepository 未注入）")
    try:
        from datetime import datetime as _dt
        ts = _dt.fromisoformat(time_start) if time_start else None
        te = _dt.fromisoformat(time_end) if time_end else None
        result = _pv_repo_instance.query_training_sample_page(
            page=page,
            page_size=page_size,
            label_status=label_status,
            site_id=site_id,
            time_start=ts,
            time_end=te,
        )
        # datetime 序列化
        for item in result.get("items", []):
            if "time" in item and item["time"] is not None:
                item["time"] = str(item["time"])
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("training-candidates failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取训练候选失败: {exc}")


@router.post("/clustering/runs")
async def create_clustering_run(request: CreateClusteringRunRequest):
    """从上传数据集或数据库候选样本创建聚类 run。"""
    try:
        if request.dataset_path:
            import pandas as pd

            if _os.path.isabs(request.dataset_path):
                raise HTTPException(status_code=422, detail="dataset_path 必须使用相对项目根目录路径")
            resolved = _resolve_data_path(request.dataset_path)
            if not _os.path.exists(resolved):
                raise HTTPException(status_code=404, detail=f"数据集不存在: {request.dataset_path}")
            extension = _os.path.splitext(resolved)[1].lower()
            frame = pd.read_parquet(resolved) if extension == ".parquet" else pd.read_csv(resolved)
            samples = frame.head(request.page_size).where(frame.notna(), None).to_dict(orient="records")
        else:
            if _pv_repo_instance is None:
                raise HTTPException(status_code=503, detail="PV 数据源未连接")
            from datetime import datetime as _dt
            ts = _dt.fromisoformat(request.time_start) if request.time_start else None
            te = _dt.fromisoformat(request.time_end) if request.time_end else None
            result = _pv_repo_instance.query_training_sample_page(
                page=1,
                page_size=request.page_size,
                label_status=request.label_status if request.label_status != "all" else None,
                site_id=request.site_id,
                time_start=ts,
                time_end=te,
            )
            samples = result.get("items", [])
        if not samples:
            raise HTTPException(status_code=422, detail="筛选条件下无候选样本")
        workspace = _get_pv_workspace()
        run = workspace.create_clustering_run(
            samples=samples,
            n_clusters=request.n_clusters,
            reviewer=request.reviewer,
        )
        return run
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("create_clustering_run failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建聚类 run 失败: {exc}")


@router.get("/clustering/runs/{run_id}")
async def get_clustering_run(run_id: str):
    """读取聚类 run 状态。"""
    workspace = _get_pv_workspace()
    run = workspace.get_clustering_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"聚类 run {run_id} 不存在")
    return run


@router.put("/clustering/runs/{run_id}/clusters/{cluster_id}")
async def update_cluster(run_id: str, cluster_id: str, request: UpdateClusterRequest):
    """给聚类簇设置人工名称或筛选成员。"""
    workspace = _get_pv_workspace()
    try:
        run = workspace.update_cluster(
            run_id=run_id,
            cluster_id=cluster_id,
            proposed_label_name=request.proposed_label_name,
            selected_member_keys=request.selected_member_keys,
        )
        return run
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("update_cluster failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/clustering/runs/{run_id}/confirm")
async def confirm_clustering_run(run_id: str, request: ConfirmClusteringRunRequest):
    """二次确认聚类 run：生成 labeled CSV 并登记到累计训练集。"""
    if not request.confirm_inclusion:
        raise HTTPException(status_code=422, detail="confirm_inclusion 必须为 true")
    workspace = _get_pv_workspace()
    try:
        run = workspace.get_clustering_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"聚类 run {run_id} 不存在")

        # 构建 label_id_map：对不存在标签自动新增
        registry = _registry_for_slot("pv_fault")
        current = registry.get_current()
        existing_map: Dict[str, int] = current.get("label_map", {})
        label_id_map: Dict[str, int] = {}
        for cid, cluster in run.get("clusters", {}).items():
            name = cluster.get("proposed_label_name")
            if not name:
                raise HTTPException(status_code=422, detail=f"簇 {cid} 缺少 proposed_label_name")
            if name in existing_map:
                label_id_map[name] = existing_map[name]
            else:
                new_id = registry.allocate_label(name)
                label_id_map[name] = new_id
                existing_map[name] = new_id

        result = workspace.confirm_clustering_run(run_id=run_id, label_id_map=label_id_map)

        # 登记到累计训练集
        ct = _cumulative_training_for_slot("pv_fault")
        import_result = ct.register_labeled_dataset(
            dataset_path=result["dataset_path"],
            source_name=f"clustering-confirm-{run_id}",
        )
        result["cumulative_training"] = import_result
        return result
    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("confirm_clustering_run failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"确认聚类 run 失败: {exc}")


@router.post("/training-slices")
async def create_training_slice(request: CreateTimeSliceRequest):
    """从源文件切取时间段标注并登记到 pv_fault 累计训练集。"""
    if not request.confirm_inclusion:
        raise HTTPException(status_code=422, detail="confirm_inclusion 必须为 true")
    workspace = _get_pv_workspace()
    try:
        meta = workspace.create_confirmed_time_slice(
            source_path=request.source_path,
            time_start=request.time_start,
            time_end=request.time_end,
            label_id=request.label_id,
            reviewer=request.reviewer,
            site_id=request.site_id,
            device_id=request.device_id,
            branch_id=request.branch_id,
        )
        ct = _cumulative_training_for_slot("pv_fault")
        import_result = ct.register_labeled_dataset(
            dataset_path=meta["dataset_path"],
            source_name=f"time-slice-{meta['slice_id']}",
        )
        meta["cumulative_training"] = import_result
        return meta
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("create_training_slice failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"创建时间切片失败: {exc}")


@router.get("/prediction-batches")
async def list_prediction_batches(slot: str = "pv_fault"):
    """列出指定槽位的预测批次。"""
    workspace = _get_pv_workspace()
    return {"batches": workspace.list_prediction_batches(_normalize_slot(slot))}


@router.get("/prediction-batches/{batch_id}")
async def get_prediction_batch(batch_id: str, slot: str = "pv_fault"):
    """读取单个预测批次详情。"""
    workspace = _get_pv_workspace()
    batch = workspace.get_prediction_batch(batch_id, _normalize_slot(slot))
    if batch is None:
        raise HTTPException(status_code=404, detail=f"预测批次 {batch_id} 不存在")
    return batch
# @AI_GENERATED: end
