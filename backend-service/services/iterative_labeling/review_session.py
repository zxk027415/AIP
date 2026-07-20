"""
Review_Session 服务 - 人工审核会话管理

**职责**：
- 基于预测批次创建审核会话，以 Diagnosis_Unit 为最小粒度逐条审核
- 双来源并列展示（分类器预测 + LLM 建议）与不一致标志
- 四类动作处理：confirm（确认正确）、correct（纠正为已有标签）、new_label（打成新标签）、skip（存疑跳过）
- 进度统计（reviewed_count / total_count）与断点恢复（经 Storage_Abstraction 持久化）
- confirm/correct/new_label 写真值（is_ground_truth=true），skip 标 pending 不写真值

**关键约定**（来自设计文档）：

1. **双来源并列**：
   - 分类器预测：predicted_label + confidence
   - LLM 建议：suggested_label + reason（可缺失）
   - 不一致高亮：predicted_label != suggested_label 时 disagreement=true

2. **四类动作**：
   - confirm：以分类器 predicted_label 作为 Human_Verdict，写真值
   - correct：从 Label_Registry 已有类别中选定标签，写真值
   - new_label：调用 LabelRegistry.allocate_label 扩充标签，写真值
   - skip：标记为 pending，不写真值、不计精度、不进回流

3. **真值固化口径**：
   - action_type ∈ {confirm, correct, new_label} → is_ground_truth=true
   - action_type == skip → is_ground_truth=false（pending）

4. **进度与恢复**：
   - reviewed_count / total_count 实时统计
   - 每提交一条裁决经 ReviewResultRepository 持久化
   - 支持会话中断后从 load_session 恢复

**数据模型参考**（来自设计文档）：
```jsonc
{
  "review_id": "rev-r3-77",
  "loop_id": "loop-2026-03",
  "status": "reviewing",  // reviewing / reviewed
  "verdicts": [
    {
      "unit_key": "siteA|dev12|br3|2026-06-01",
      "verdict_label": 1,  // skip 时为 null
      "action_type": "confirm",  // confirm/correct/new_label/skip
      "is_ground_truth": true,  // skip 为 false
      "reviewer": "operator_zhang",
      "reviewed_at": "2026-06-08T12:06:00"
    }
  ]
}
```

**映射需求**：
- 需求 3.1, 3.2, 3.3, 3.4: 审核会话创建、逐单元审核、进度、断点恢复
- 需求 4.1, 4.2, 4.3: 双来源并列、不一致高亮、明确标注辅助建议
- 需求 5.1, 5.2, 5.3, 5.4, 5.5, 5.6: 四类动作与真值固化口径

**使用示例**：
```python
from .storage.file_backend import FileReviewResultRepository
from .label_registry import LabelRegistryService

# 初始化服务
review_repo = FileReviewResultRepository()
registry_service = LabelRegistryService(slot='default')
session_service = ReviewSessionService(
    slot='default',
    review_repo=review_repo,
    registry_service=registry_service
)

# 创建审核会话（基于预测批次）
session = session_service.create_session(
    loop_id='loop-2026-03',
    prediction_batch_id='pred-r3-001',
    prediction_units=[...],  # Classifier_Prediction 数组
    llm_suggestions={...},  # unit_key -> LLM_Suggestion 映射（可选）
)

# 提交一条人工裁决
session_service.submit_verdict(
    review_id='rev-r3-77',
    unit_key='siteA|dev12|br3|2026-06-01',
    action_type='confirm',  # confirm / correct / new_label / skip
    verdict_label=1,  # correct/new_label 时必填；confirm 时取分类器预测；skip 时为 null
    new_label_name='新故障类型',  # new_label 时必填
    reviewer='operator_zhang'
)

# 读取会话状态（支持断点恢复）
session_state = session_service.get_session('rev-r3-77')
```
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import re
import uuid

from .storage.interfaces import ReviewResultRepository
from .label_registry import LabelRegistryService


def _review_id_for_prediction_batch(prediction_batch_id: str) -> str:
    """Build a readable review ID that preserves the prediction timestamp."""
    batch_suffix = str(prediction_batch_id).removeprefix("pred-")
    safe_suffix = re.sub(r"[^A-Za-z0-9_-]+", "-", batch_suffix).strip("-")
    if not safe_suffix:
        raise ValueError("prediction_batch_id 无法生成有效审核会话标识")
    return f"rev-{safe_suffix}"

logger = logging.getLogger(__name__)


class ReviewSessionService:
    """
    审核会话服务
    
    提供审核会话创建、装配待审核单元、四类动作处理、进度统计、断点恢复等功能。
    
    Attributes:
        slot: 槽位（多环境/多产品线分区键），默认 'default'
        review_repo: 审核结果仓储实例
        registry_service: 标签注册表服务实例
    """
    
    def __init__(
        self,
        slot: str = 'default',
        review_repo: Optional[ReviewResultRepository] = None,
        registry_service: Optional[LabelRegistryService] = None
    ):
        """
        初始化审核会话服务
        
        参数：
        - slot: str — 槽位（多环境/多产品线分区键），默认 'default'（默认槽）
        - review_repo: ReviewResultRepository | None — 审核结果仓储实例（可注入用于测试）
        - registry_service: LabelRegistryService | None — 标签注册表服务实例（可注入用于测试）
        
        说明：
        - slot 用于多产品线/多环境分区，如 'aesc'、'mengxi' 等
        - 为 None 时使用默认文件后端
        """
        self.slot = slot
        
        # 依赖注入：允许测试时注入 mock 仓储
        if review_repo is None:
            from .storage.file_backend import FileReviewResultRepository
            review_repo = FileReviewResultRepository()
        self.review_repo = review_repo
        
        # 依赖注入：标签注册表服务
        if registry_service is None:
            registry_service = LabelRegistryService(slot=slot)
        self.registry_service = registry_service
    
    def create_session(
        self,
        loop_id: str,
        prediction_batch_id: str,
        prediction_units: List[Dict[str, Any]],
        llm_suggestions: Optional[Dict[str, Dict[str, Any]]] = None,
        prediction_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        创建审核会话（基于预测批次）
        
        参数：
        - loop_id: str — 所属迭代闭环
        - prediction_batch_id: str — 基于哪一批预测结果
        - prediction_units: list[dict] — Classifier_Prediction 数组，每项包含：
            - unit_key: str — 诊断单元标识
            - predicted_label: int — 预测标签
            - confidence: float — 置信度
        - llm_suggestions: dict[str, dict] | None — unit_key -> LLM_Suggestion 映射（可选），
          LLM_Suggestion 包含：
            - suggested_label: int | None — 建议标签
            - reason: str — 建议理由
            - available: bool — 是否可用
            - out_of_registry: bool — 是否越界
        
        返回：
        - dict — 会话对象，包含：
            - review_id: str — 审核会话唯一标识（主键）
            - loop_id: str — 所属迭代闭环
            - prediction_batch_id: str — 预测批次标识
            - status: str — 会话状态（reviewing / reviewed）
            - total_count: int — 待审核单元总数
            - reviewed_count: int — 已审核单元数（初始为 0）
            - units: list[dict] — 待审核单元数组（装配后，含双来源与 disagreement 标志）
        
        行为：
        1. 装配待审核单元：逐 Diagnosis_Unit 加载分类器预测与 LLM 建议
        2. 计算 disagreement 标志：predicted_label != suggested_label 时为 true
        3. 初始化会话状态并持久化
        
        映射需求：
        - 需求 3.1: 以 Diagnosis_Unit 为最小粒度逐条加载待审核单元
        - 需求 4.1, 4.2: 双来源并列展示、不一致高亮
        """
        if not loop_id or not prediction_batch_id:
            raise ValueError("loop_id 和 prediction_batch_id 不能为空")
        
        if not prediction_units:
            raise ValueError("prediction_units 不能为空")
        
        # 审核 ID 保留预测批次中的时间和短标识，便于从页面直接核对来源。
        review_id = _review_id_for_prediction_batch(prediction_batch_id)
        existing_session = self.review_repo.load_session(self.slot, review_id)
        if existing_session:
            logger.info(
                "复用预测批次 %s 已有审核会话 %s",
                prediction_batch_id,
                review_id,
            )
            return existing_session
        # 兼容此前发布过的 UUID5 命名，历史批次重复创建时仍复用原会话。
        legacy_review_id = (
            f"rev-{uuid.uuid5(uuid.NAMESPACE_URL, f'aip:{self.slot}:{prediction_batch_id}').hex[:12]}"
        )
        legacy_session = self.review_repo.load_session(self.slot, legacy_review_id)
        if legacy_session:
            logger.info(
                "复用预测批次 %s 的历史审核会话 %s",
                prediction_batch_id,
                legacy_review_id,
            )
            return legacy_session
        
        # 装配待审核单元（双来源并列 + disagreement 标志）
        units = []
        for pred_unit in prediction_units:
            unit_key = pred_unit.get('unit_key')
            if not unit_key:
                logger.warning(f"跳过缺少 unit_key 的预测单元: {pred_unit}")
                continue
            
            # 分类器预测
            classifier_prediction = {
                'predicted_label': pred_unit.get('predicted_label'),
                'confidence': pred_unit.get('confidence', 0.0)
            }
            
            # LLM 建议（可缺失）
            llm_suggestion = None
            disagreement = False
            
            if llm_suggestions and unit_key in llm_suggestions:
                llm_sugg = llm_suggestions[unit_key]
                llm_suggestion = {
                    'suggested_label': llm_sugg.get('suggested_label'),
                    'reason': llm_sugg.get('reason', ''),
                    'available': llm_sugg.get('available', True),
                    'out_of_registry': llm_sugg.get('out_of_registry', False)
                }
                
                # 计算 disagreement（需求 4.2）
                pred_label = classifier_prediction['predicted_label']
                sugg_label = llm_suggestion.get('suggested_label')
                
                if (pred_label is not None and sugg_label is not None 
                    and pred_label != sugg_label):
                    disagreement = True
            
            # 装配单元
            unit = {
                'unit_key': unit_key,
                'site_id': pred_unit.get('site_id'),
                'device_id': pred_unit.get('device_id'),
                'branch_id': pred_unit.get('branch_id'),
                'time_window': pred_unit.get('time_window'),
                'classifier_prediction': classifier_prediction,
                'llm_suggestion': llm_suggestion,
                'disagreement': disagreement,
                'current_verdict': None  # 未审核时为 None（断点恢复用）
            }
            units.append(unit)
        
        # 初始化会话状态
        session_state = {
            'review_id': review_id,
            'loop_id': loop_id,
            'prediction_batch_id': prediction_batch_id,
            'status': 'reviewing',
            'total_count': len(units),
            'reviewed_count': 0,
            'units': units,
            'verdicts': [],
            # 编辑器驱动回流所需上下文（原始预测 CSV 路径 + 算子配置 + label_map）
            'prediction_context': prediction_context or {}
        }
        
        # 持久化初始会话状态
        self.review_repo.save_verdict(self.slot, review_id, session_state)
        
        logger.info(f"创建审核会话 {review_id}，共 {len(units)} 个待审核单元")
        
        return session_state
    
    def submit_verdict(
        self,
        review_id: str,
        unit_key: str,
        action_type: str,
        reviewer: str,
        verdict_label: Optional[int] = None,
        new_label_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        提交一条人工裁决
        
        参数：
        - review_id: str — 审核会话唯一标识
        - unit_key: str — 诊断单元标识（site_id × device_id ×（可选 branch_id）× time_window）
        - action_type: str — 动作类型，枚举值：
            - 'confirm'：确认分类器预测正确，以 predicted_label 作为 Human_Verdict
            - 'correct'：纠正为已有标签，verdict_label 必填
            - 'new_label'：打成新标签，new_label_name 必填，调用 allocate_label 扩充
            - 'skip'：存疑跳过，标记为 pending，不写真值
        - reviewer: str — 审核人
        - verdict_label: int | None — 裁决标签：
            - confirm 时自动取分类器 predicted_label（忽略此参数）
            - correct 时必填，从注册表已有类别中选定
            - new_label 时自动分配（忽略此参数）
            - skip 时为 None
        - new_label_name: str | None — 新标签业务名称（new_label 时必填）
        
        返回：
        - dict — 提交结果，包含：
            - accepted: bool — 是否接受（true）
            - verdict: dict — 已固化的裁决记录
            - session_state: dict — 更新后的会话状态（含 reviewed_count）
        
        行为：
        1. 加载会话状态
        2. 查找对应单元的分类器预测
        3. 根据 action_type 确定 verdict_label 与 is_ground_truth：
           - confirm: verdict_label = predicted_label, is_ground_truth = true
           - correct: verdict_label = 入参, is_ground_truth = true
           - new_label: verdict_label = allocate_label(new_label_name), is_ground_truth = true
           - skip: verdict_label = None, is_ground_truth = false（pending）
        4. 记录 unit_key / verdict_label / action_type / reviewer / reviewed_at
        5. 持久化裁决并更新 reviewed_count
        6. 若全部单元已审核，将 status 置为 'reviewed'
        
        映射需求：
        - 需求 5.1: confirm 以分类器 predicted_label 作为 Human_Verdict
        - 需求 5.2: correct 从注册表已有类别中选定
        - 需求 5.3: new_label 调用 allocate_label 扩充标签
        - 需求 5.4: skip 标记为 pending，不写真值
        - 需求 5.5: 记录 unit_key / verdict_label / action_type / reviewer / reviewed_at
        - 需求 5.6: confirm/correct/new_label 写真值，skip 不写
        
        异常：
        - 若 review_id 不存在，抛 KeyError
        - 若 unit_key 在会话中不存在，抛 ValueError
        - 若 action_type 不合法，抛 ValueError
        - 若 correct 时 verdict_label 为 None，抛 ValueError
        - 若 new_label 时 new_label_name 为空，抛 ValueError
        """
        # 校验 action_type
        valid_actions = {'confirm', 'correct', 'new_label', 'skip'}
        if action_type not in valid_actions:
            raise ValueError(f"action_type 必须为 {valid_actions} 之一，当前为 {action_type}")
        
        # 加载会话状态
        session_state = self.review_repo.load_session(self.slot, review_id)
        if not session_state:
            raise KeyError(f"审核会话 {review_id} 不存在")
        
        # 查找对应单元
        unit = None
        for u in session_state.get('units', []):
            if u.get('unit_key') == unit_key:
                unit = u
                break
        
        if unit is None:
            raise ValueError(f"单元 {unit_key} 在会话 {review_id} 中不存在")
        
        # 根据 action_type 确定 verdict_label 与 is_ground_truth
        final_verdict_label = None
        is_ground_truth = False
        
        if action_type == 'confirm':
            # 确认分类器预测正确（需求 5.1）
            classifier_pred = unit.get('classifier_prediction', {})
            final_verdict_label = classifier_pred.get('predicted_label')
            if final_verdict_label is None:
                raise ValueError(f"单元 {unit_key} 缺少分类器预测标签，无法 confirm")
            is_ground_truth = True
        
        elif action_type == 'correct':
            # 纠正为已有标签（需求 5.2）
            if verdict_label is None:
                raise ValueError("correct 动作必须提供 verdict_label")
            
            # 校验 verdict_label 在注册表中存在
            label_record = self.registry_service.get_label_by_id(verdict_label)
            if label_record is None:
                raise ValueError(f"label_id {verdict_label} 在注册表中不存在")
            
            final_verdict_label = verdict_label
            is_ground_truth = True
        
        elif action_type == 'new_label':
            # @AI_GENERATED: 前端可先显式创建标签再提交其 label_id；也兼容一次性名称分配
            if verdict_label is not None:
                label_record = self.registry_service.get_label_by_id(verdict_label)
                if label_record is None:
                    raise ValueError(f"label_id {verdict_label} 在注册表中不存在")
                final_verdict_label = verdict_label
            else:
                if not new_label_name or not new_label_name.strip():
                    raise ValueError("new_label 动作必须提供 new_label_name 或已创建的 verdict_label")
                final_verdict_label = self.registry_service.allocate_label(new_label_name.strip())
                logger.info(f"新增标签：{new_label_name} -> label_id={final_verdict_label}")
            is_ground_truth = True
            # @AI_GENERATED: end
        
        elif action_type == 'skip':
            # 存疑跳过（需求 5.4）
            final_verdict_label = None
            is_ground_truth = False  # pending，不写真值
        
        # 创建裁决记录（需求 5.5）
        verdict = {
            'unit_key': unit_key,
            'verdict_label': final_verdict_label,
            'action_type': action_type,
            'is_ground_truth': is_ground_truth,
            'reviewer': reviewer,
            'reviewed_at': datetime.utcnow().isoformat()
        }
        
        # 更新会话状态：追加裁决 + 更新单元 current_verdict + 递增 reviewed_count
        verdicts = session_state.get('verdicts', [])
        
        # 检查该单元是否已有裁决（支持改判）
        existing_verdict_idx = None
        for idx, v in enumerate(verdicts):
            if v.get('unit_key') == unit_key:
                existing_verdict_idx = idx
                break
        
        if existing_verdict_idx is not None:
            # 改判：替换原裁决
            verdicts[existing_verdict_idx] = verdict
            logger.info(f"改判单元 {unit_key}，新动作 {action_type}")
        else:
            # 新裁决：追加
            verdicts.append(verdict)
            session_state['reviewed_count'] = session_state.get('reviewed_count', 0) + 1
        
        session_state['verdicts'] = verdicts
        
        # 更新对应单元的 current_verdict（断点恢复用）
        unit['current_verdict'] = verdict
        
        # 若全部单元已审核，将 status 置为 'reviewed'
        if session_state['reviewed_count'] >= session_state['total_count']:
            session_state['status'] = 'reviewed'
            logger.info(f"审核会话 {review_id} 已完成全部 {session_state['total_count']} 个单元的审核")
        
        # 持久化更新后的会话状态
        self.review_repo.save_verdict(self.slot, review_id, session_state)
        
        return {
            'accepted': True,
            'verdict': verdict,
            'session_state': session_state
        }
    
    def get_session(self, review_id: str) -> Dict[str, Any]:
        """
        读取审核会话状态（支持断点恢复）
        
        参数：
        - review_id: str — 审核会话唯一标识
        
        返回：
        - dict — 会话状态对象（见 create_session 的返回结构）
        
        用途：
        - 供前端读取会话进度与单元列表
        - 支持会话中断后恢复（load 已持久化的 verdicts 与 current_verdict）
        
        映射需求：
        - 需求 3.3: 显示审核进度（reviewed_count / total_count）
        - 需求 3.4: 会话中断后可恢复继续
        
        异常：
        - 若 review_id 不存在，返回空字典或抛 KeyError（由 review_repo 决定）
        """
        return self.review_repo.load_session(self.slot, review_id)
    
    def get_units_with_verdicts(self, review_id: str) -> List[Dict[str, Any]]:
        """
        读取会话的待审核单元列表（含已提交的裁决）
        
        参数：
        - review_id: str — 审核会话唯一标识
        
        返回：
        - list[dict] — 单元数组，每项包含：
            - unit_key: str — 诊断单元标识
            - classifier_prediction: dict — 分类器预测
            - llm_suggestion: dict | None — LLM 建议（可缺失）
            - disagreement: bool — 是否双来源分歧
            - current_verdict: dict | None — 已提交的裁决（未审核时为 None）
        
        用途：
        - 供前端展示单元列表与已审核状态
        - 支持断点恢复时回显已审核单元
        """
        session_state = self.get_session(review_id)
        return session_state.get('units', [])
    
    def get_progress(self, review_id: str) -> Dict[str, int]:
        """
        读取审核进度
        
        参数：
        - review_id: str — 审核会话唯一标识
        
        返回：
        - dict — 进度对象，包含：
            - reviewed_count: int — 已审核单元数
            - total_count: int — 待审核单元总数
            - progress_pct: float — 完成百分比（0~100）
        
        用途：
        - 供前端展示进度条
        
        映射需求：
        - 需求 3.3: 显示审核进度（reviewed_count / total_count）
        """
        session_state = self.get_session(review_id)
        reviewed_count = session_state.get('reviewed_count', 0)
        total_count = session_state.get('total_count', 0)
        
        progress_pct = 0.0
        if total_count > 0:
            progress_pct = (reviewed_count / total_count) * 100.0
        
        return {
            'reviewed_count': reviewed_count,
            'total_count': total_count,
            'progress_pct': progress_pct
        }
