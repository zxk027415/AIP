"""
Loop_Orchestrator - 闭环编排器核心模块

**职责：**
1. 维护每轮 Iteration_Loop 的阶段状态机：
   trained → predicted → reviewing → reviewed → backfilled（及 backfilled → trained 进入下一轮）
2. 内部符号 _advance_stage(loop_id, target_stage)：
   校验目标阶段是当前阶段的合法直接后继且前置完成，满足则迁移并通知 Iteration_Tracker
   追加记录，不满足则抛阶段不满足错误
3. 闭环创建（含 slot、iteration_round）与只读状态读取（含 label_space_lag，复用任务 2 的落后检测）

**映射需求：**
- 需求 12.1: 维护每一轮 Iteration_Loop 的阶段状态机（trained/predicted/reviewing/reviewed/backfilled）
- 需求 12.2: 阻止跳过前置阶段直接进入后续阶段，并返回阶段不满足说明
- 需求 12.3: 在每个阶段完成时通知 Iteration_Tracker 追加对应记录
- 需求 12.5: 依据 Iteration_Tracker 的记录定位历史某一轮的数据集版本、模型版本与标签空间快照

**阶段状态机约定（来自设计文档）：**
```
[初始] → trained（训练完成）→ predicted（预测完成）→ reviewing（审核中）
        → reviewed（审核完成）→ backfilled（回流完成）→ [下一轮 trained]
```

**阶段合法迁移表：**
- None → trained（首次训练）
- trained → predicted（训练后预测）
- predicted → reviewing（预测后审核）
- reviewing → reviewed（审核完成）
- reviewed → backfilled（回流完成）
- backfilled → trained（下一轮训练）

**Loop 状态契约（来自设计文档）：**
```jsonc
{
  "loop_id": "loop-2026-03",                  // 迭代闭环唯一标识（主键）
  "iteration_round": 3,                       // 迭代轮次（从 1 起）
  "stage": "trained",                         // 当前阶段（见上）
  "slot": "default",                          // 槽位（多环境/多产品线分区键）
  "dataset_version": "ds-v3",                 // 可选，训练所用数据集版本（trained 后填充）
  "model_ref": "mdl-2026round3-a1b2",         // 可选，模型引用（trained 后填充）
  "label_space_snapshot": {                   // 可选，标签空间快照（trained 后填充）
    "label_space_version": "ls-v5",
    "label_ids": [0, 1, 2, 10, 20]
  },
  "label_space_lag": false,                   // 是否标签空间落后（与当前注册表比较）
  "created_at": "2026-06-08T12:00:00",        // 创建时间
  "updated_at": "2026-06-08T12:05:00"         // 最后更新时间
}
```

**关键约定：**
- 严格前置校验：禁止跳阶段（需求 12.2）
- 每个阶段完成时通知 Iteration_Tracker 追加记录（需求 12.3）
- label_space_lag 通过 LabelRegistryService.check_label_space_lag() 检测（需求 8.4）
- 闭环状态以内存 + 文件为主，当前阶段不直接落库（存储抽象层预留 DB 接入点）

**与其他组件的协作：**
- Iteration_Tracker: 阶段完成时调用 append_record() 追加历史记录
- LabelRegistryService: 读取 Loop 时调用 check_label_space_lag() 检测落后
- Review_Session / Backfill: 由编排器在相应阶段触发（见 API 层设计）

**使用示例：**
```python
# 初始化编排器
orchestrator = LoopOrchestrator(slot='default')

# 创建新闭环
loop_state = orchestrator.create_loop()

# 推进阶段（训练完成）
orchestrator.advance_to_trained(
    loop_id=loop_state['loop_id'],
    dataset_version='ds-v1',
    model_ref='mdl-001',
    label_space_snapshot={'label_space_version': 'ls-v1', 'label_ids': [0, 1]}
)

# 读取当前状态（含 label_space_lag）
current_state = orchestrator.get_loop_state(loop_state['loop_id'])
print(f"当前阶段: {current_state['stage']}, 标签空间落后: {current_state['label_space_lag']}")
```
"""

from typing import Dict, Any, Optional
from datetime import datetime
import uuid


class StageTransitionError(Exception):
    """
    阶段迁移错误（前置阶段不满足或目标阶段不合法）
    
    用途：
    - 当尝试跳过前置阶段直接进入后续阶段时抛出
    - 当目标阶段不是当前阶段的合法直接后继时抛出
    
    映射需求：
    - 需求 12.2: 阻止跳过前置阶段并返回阶段不满足说明
    """
    pass


class LoopOrchestrator:
    """
    闭环编排器
    
    职责：
    - 维护每轮 Iteration_Loop 的阶段状态机
    - 严格校验阶段迁移的合法性（禁止跳阶段）
    - 阶段完成时通知 Iteration_Tracker 追加记录
    - 提供只读状态读取（含 label_space_lag 检测）
    
    说明：
    - 当前版本使用内存字典存储闭环状态（简单实现，支持会话内持续）
    - 存储抽象层预留了 DB 接入点，后续可切换为数据库持久化
    - slot 参数支持多环境/多产品线分区
    """
    
    # 合法阶段迁移表（当前阶段 → 合法的下一阶段）
    STAGE_TRANSITIONS = {
        None: 'trained',              # 初始 → 训练完成
        'trained': 'predicted',       # 训练完成 → 预测完成
        'predicted': 'reviewing',     # 预测完成 → 审核中
        'reviewing': 'reviewed',      # 审核中 → 审核完成
        'reviewed': 'backfilled',     # 审核完成 → 回流完成
        'backfilled': 'trained'       # 回流完成 → 下一轮训练完成
    }
    
    def __init__(self, slot: str = 'default'):
        """
        初始化闭环编排器
        
        参数：
        - slot: str — 槽位（多环境/多产品线分区键），默认 'default'（默认槽）
        
        说明：
        - slot 用于多产品线/多环境分区，如 'aesc'、'mengxi' 等
        - 当前实现使用内存字典存储闭环状态，按 slot 分区
        """
        self.slot = slot
        
        # 内存存储：{loop_id: loop_state_dict}
        # 注：后续可替换为文件或数据库存储，调用方代码无需修改
        self._loops: Dict[str, Dict[str, Any]] = {}
        
        # 延迟导入依赖（避免循环依赖）
        self._iteration_tracker = None
        self._label_registry_service = None
    
    @property
    def iteration_tracker(self):
        """延迟加载 Iteration_Tracker（避免循环导入）"""
        if self._iteration_tracker is None:
            from .iteration_tracker import IterationTracker
            self._iteration_tracker = IterationTracker(slot=self.slot)
        return self._iteration_tracker
    
    @property
    def label_registry_service(self):
        """延迟加载 LabelRegistryService（避免循环导入）"""
        if self._label_registry_service is None:
            from .label_registry import LabelRegistryService
            self._label_registry_service = LabelRegistryService(slot=self.slot)
        return self._label_registry_service
    
    def create_loop(self, base_dataset_version: Optional[str] = None) -> Dict[str, Any]:
        """
        创建/开启一轮迭代闭环
        
        参数：
        - base_dataset_version: str | None — 可选，本轮训练所基于的基线数据集版本（首轮可空）
        
        返回：
        - dict — 初始闭环状态，包含：
            - loop_id: str — 迭代闭环唯一标识（主键）
            - iteration_round: int — 迭代轮次（基于历史记录数 + 1）
            - stage: None — 当前阶段（初始为 None，训练后置 'trained'）
            - slot: str — 槽位
            - base_dataset_version: str | None — 基线数据集版本（可选）
            - dataset_version: None — 训练所用数据集版本（trained 后填充）
            - model_ref: None — 模型引用（trained 后填充）
            - label_space_snapshot: None — 标签空间快照（trained 后填充）
            - label_space_lag: False — 是否标签空间落后（初始为 False）
            - created_at: str — 创建时间（ISO 格式）
            - updated_at: str — 最后更新时间（ISO 格式）
        
        行为：
        - 自动计算 iteration_round = 历史记录数 + 1（从 1 起）
        - 分配唯一 loop_id（UUID 格式，如 'loop-550e8400-e29b-41d4-a716-446655440000'）
        - 初始 stage 为 None（尚未开始训练）
        
        用途：
        - 供 HTTP 接口 POST /api/iterative-labeling/loops 调用
        - 用户首次创建闭环或从 backfilled 阶段开始下一轮时调用
        
        映射需求：
        - 需求 12（闭环编排串联）
        
        **Validates: Requirements 12（闭环创建）**
        """
        # 自动计算 iteration_round（基于历史记录数）
        history = self.iteration_tracker.list_history()
        iteration_round = len(history) + 1
        
        # 分配唯一 loop_id
        loop_id = f"loop-{uuid.uuid4()}"
        
        # 组装初始状态
        now = datetime.utcnow().isoformat()
        loop_state = {
            'loop_id': loop_id,
            'iteration_round': iteration_round,
            'stage': None,  # 初始为 None，训练后置 'trained'
            'slot': self.slot,
            'base_dataset_version': base_dataset_version,
            'dataset_version': None,  # trained 后填充
            'model_ref': None,  # trained 后填充
            'label_space_snapshot': None,  # trained 后填充
            'label_space_lag': False,  # 初始为 False
            'created_at': now,
            'updated_at': now
        }
        
        # 存储（内存）
        self._loops[loop_id] = loop_state
        
        return loop_state
    
    def get_loop_state(self, loop_id: str) -> Dict[str, Any]:
        """
        读取某轮闭环状态（只读，供 UI 展示当前处于哪一步）
        
        参数：
        - loop_id: str — 迭代闭环唯一标识
        
        返回：
        - dict — 闭环状态（见 create_loop 的返回体结构）
        
        行为：
        - 从内存/文件/DB 读取闭环状态
        - 实时计算 label_space_lag：调用 LabelRegistryService.check_label_space_lag()
          比较模型快照版本与当前注册表版本
        
        用途：
        - 供 HTTP 接口 GET /api/iterative-labeling/loops/{loop_id} 调用
        - 供 UI 展示当前阶段、数据集版本、模型版本、标签空间落后提示
        
        异常：
        - 若 loop_id 不存在，抛 KeyError
        
        映射需求：
        - 需求 12（只读状态读取）
        - 需求 8.4（label_space_lag 检测）
        
        **Validates: Requirements 12（闭环状态读取）, 8.4（标签空间落后检测）**
        """
        if loop_id not in self._loops:
            raise KeyError(f"闭环 {loop_id} 不存在")
        
        loop_state = self._loops[loop_id].copy()
        
        # 实时计算 label_space_lag（若已有 label_space_snapshot）
        if loop_state.get('label_space_snapshot'):
            model_snapshot_version = loop_state['label_space_snapshot'].get('label_space_version')
            if model_snapshot_version:
                loop_state['label_space_lag'] = self.label_registry_service.check_label_space_lag(
                    model_snapshot_version
                )
        
        return loop_state
    
    def advance_to_trained(
        self,
        loop_id: str,
        dataset_version: str,
        model_ref: str,
        label_space_snapshot: Dict[str, Any],
        accuracy_record: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        推进阶段：None/backfilled → trained（训练完成）
        
        参数：
        - loop_id: str — 迭代闭环唯一标识
        - dataset_version: str — 训练所用数据集版本
        - model_ref: str — 模型引用（预测时显式指定）
        - label_space_snapshot: dict — 标签空间快照，含：
            - label_space_version: str — 标签空间版本号
            - label_ids: list[int] — 该快照包含的标签编码集合
        - accuracy_record: dict | None — 精度记录（可选，用于追加 Iteration_Tracker 记录）
        
        行为：
        1. 校验当前阶段为 None 或 'backfilled'（合法前驱）
        2. 校验 dataset_version、model_ref、label_space_snapshot 非空
        3. 更新闭环状态：stage='trained'，填充 dataset_version/model_ref/label_space_snapshot
        4. 通知 Iteration_Tracker 追加迭代记录（若提供 accuracy_record）
        
        异常：
        - 若当前阶段不是 None 或 'backfilled'，抛 StageTransitionError
        - 若必填参数缺失，抛 ValueError
        
        映射需求：
        - 需求 12.1（阶段状态机迁移）
        - 需求 12.2（前置校验）
        - 需求 12.3（通知 Iteration_Tracker）
        
        **Validates: Requirements 12.1, 12.2, 12.3**
        """
        # 校验参数
        if not dataset_version or not model_ref or not label_space_snapshot:
            raise ValueError("训练完成阶段必须提供 dataset_version、model_ref、label_space_snapshot")
        
        # 推进阶段（内部校验前置）
        self._advance_stage(loop_id, 'trained')
        
        # 更新闭环状态
        loop_state = self._loops[loop_id]
        loop_state['dataset_version'] = dataset_version
        loop_state['model_ref'] = model_ref
        loop_state['label_space_snapshot'] = label_space_snapshot
        loop_state['updated_at'] = datetime.utcnow().isoformat()
        
        # 通知 Iteration_Tracker（若提供 accuracy_record）
        if accuracy_record:
            label_count = len(label_space_snapshot.get('label_ids', []))
            iteration_record = {
                'iteration_id': f"iter-{loop_id}-r{loop_state['iteration_round']}",
                'iteration_round': loop_state['iteration_round'],
                'dataset_version': dataset_version,
                'model_version': model_ref,
                'accuracy_record': accuracy_record,
                'label_space_version': label_space_snapshot.get('label_space_version'),
                'label_count': label_count
            }
            self.iteration_tracker.append_record(iteration_record)
    
    def advance_to_predicted(self, loop_id: str, prediction_batch_id: str) -> None:
        """
        推进阶段：trained → predicted（预测完成）
        
        参数：
        - loop_id: str — 迭代闭环唯一标识
        - prediction_batch_id: str — 本次预测批次标识
        
        行为：
        1. 校验当前阶段为 'trained'（合法前驱）
        2. 更新闭环状态：stage='predicted'，记录 prediction_batch_id
        
        异常：
        - 若当前阶段不是 'trained'，抛 StageTransitionError
        
        映射需求：
        - 需求 12.1（阶段状态机迁移）
        - 需求 12.2（前置校验）
        
        **Validates: Requirements 12.1, 12.2**
        """
        self._advance_stage(loop_id, 'predicted')
        
        loop_state = self._loops[loop_id]
        loop_state['prediction_batch_id'] = prediction_batch_id
        loop_state['updated_at'] = datetime.utcnow().isoformat()
    
    def advance_to_reviewing(self, loop_id: str, review_id: str) -> None:
        """
        推进阶段：predicted → reviewing（审核中）
        
        参数：
        - loop_id: str — 迭代闭环唯一标识
        - review_id: str — 审核会话标识
        
        行为：
        1. 校验当前阶段为 'predicted'（合法前驱）
        2. 更新闭环状态：stage='reviewing'，记录 review_id
        
        异常：
        - 若当前阶段不是 'predicted'，抛 StageTransitionError
        
        映射需求：
        - 需求 12.1（阶段状态机迁移）
        - 需求 12.2（前置校验）
        
        **Validates: Requirements 12.1, 12.2**
        """
        self._advance_stage(loop_id, 'reviewing')
        
        loop_state = self._loops[loop_id]
        loop_state['review_id'] = review_id
        loop_state['updated_at'] = datetime.utcnow().isoformat()
    
    def advance_to_reviewed(self, loop_id: str) -> None:
        """
        推进阶段：reviewing → reviewed（审核完成）
        
        参数：
        - loop_id: str — 迭代闭环唯一标识
        
        行为：
        1. 校验当前阶段为 'reviewing'（合法前驱）
        2. 更新闭环状态：stage='reviewed'
        
        异常：
        - 若当前阶段不是 'reviewing'，抛 StageTransitionError
        
        映射需求：
        - 需求 12.1（阶段状态机迁移）
        - 需求 12.2（前置校验）
        
        **Validates: Requirements 12.1, 12.2**
        """
        self._advance_stage(loop_id, 'reviewed')
        
        loop_state = self._loops[loop_id]
        loop_state['updated_at'] = datetime.utcnow().isoformat()
    
    def advance_to_backfilled(self, loop_id: str, new_dataset_version: str) -> None:
        """
        推进阶段：reviewed → backfilled（回流完成）
        
        参数：
        - loop_id: str — 迭代闭环唯一标识
        - new_dataset_version: str — 回流后的新数据集版本
        
        行为：
        1. 校验当前阶段为 'reviewed'（合法前驱）
        2. 更新闭环状态：stage='backfilled'，记录 new_dataset_version
        
        异常：
        - 若当前阶段不是 'reviewed'，抛 StageTransitionError
        
        映射需求：
        - 需求 12.1（阶段状态机迁移）
        - 需求 12.2（前置校验）
        
        **Validates: Requirements 12.1, 12.2**
        """
        self._advance_stage(loop_id, 'backfilled')
        
        loop_state = self._loops[loop_id]
        loop_state['backfilled_dataset_version'] = new_dataset_version
        loop_state['updated_at'] = datetime.utcnow().isoformat()
    
    # @AI_GENERATED
    @staticmethod
    def _project_roots() -> tuple:
        """Return internal project roots; callers persist only their relative forms."""
        import os

        backend_service_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.dirname(backend_service_dir), backend_service_dir

    @classmethod
    def _resolve_project_dataset(cls, dataset_version: str) -> tuple:
        """Validate a project-root-relative CSV/Parquet path and return its canonical relative form."""
        import os

        if not isinstance(dataset_version, str) or not dataset_version.strip():
            raise ValueError("dataset_version 不能为空")
        if os.path.isabs(dataset_version):
            raise ValueError("dataset_version 必须是相对项目根路径，禁止使用绝对路径")

        project_root, _ = cls._project_roots()
        candidate = os.path.normpath(os.path.join(project_root, dataset_version.strip()))
        try:
            if os.path.commonpath([project_root, candidate]) != project_root:
                raise ValueError("dataset_version 必须位于项目根目录内")
        except ValueError as exc:
            raise ValueError("dataset_version 必须是相对项目根路径") from exc
        if not os.path.isfile(candidate):
            raise ValueError(f"dataset_version 文件不存在: {dataset_version}")

        suffix = os.path.splitext(candidate)[1].lower()
        if suffix not in {".csv", ".parquet"}:
            raise ValueError("dataset_version 仅支持 CSV 或 Parquet 文件")
        return candidate, os.path.relpath(candidate, project_root).replace(os.sep, "/")

    @classmethod
    def _resolve_model_artifact(cls, model_ref: str, requested_model_path: Optional[str] = None) -> tuple:
        """Resolve an existing relative model artifact without exposing an absolute path."""
        import os

        project_root, backend_service_dir = cls._project_roots()
        if requested_model_path:
            if not isinstance(requested_model_path, str) or os.path.isabs(requested_model_path):
                raise ValueError("model_path 必须是相对路径，禁止使用绝对路径")
            candidates = [
                os.path.normpath(os.path.join(project_root, requested_model_path)),
                os.path.normpath(os.path.join(backend_service_dir, requested_model_path)),
            ]
        else:
            if not model_ref or os.path.basename(model_ref) != model_ref:
                raise ValueError("model_ref 必须是有效的模型标识")
            candidates = [os.path.join(backend_service_dir, "data", "models", f"{model_ref}.pkl")]

        for candidate in candidates:
            try:
                if os.path.commonpath([project_root, candidate]) != project_root:
                    continue
            except ValueError:
                continue
            if os.path.isfile(candidate) and candidate.lower().endswith(".pkl"):
                persisted_path = os.path.relpath(candidate, project_root).replace(os.sep, "/")
                execution_path = os.path.relpath(candidate, backend_service_dir).replace(os.sep, "/")
                return candidate, persisted_path, execution_path
        requested = requested_model_path or f"backend-service/data/models/{model_ref}.pkl"
        raise ValueError(f"模型 pkl 不存在: {requested}")

    @staticmethod
    def _workflow_config_get(config: Any, key: str) -> Any:
        """Read a workflow config key from either a mapping or a Pydantic model."""
        return config.get(key) if isinstance(config, dict) else getattr(config, key, None)

    @staticmethod
    def _workflow_config_set(config: Any, key: str, value: Any) -> None:
        """Set a workflow config key on either a mapping or a Pydantic model."""
        if isinstance(config, dict):
            config[key] = value
        else:
            setattr(config, key, value)

    @staticmethod
    def _read_model_feature_list(model_file: str) -> list:
        """Load the persisted feature list from a validated model pickle."""
        import pickle

        with open(model_file, "rb") as handle:
            payload = pickle.load(handle)
        feature_list = payload.get("feature_list") if isinstance(payload, dict) else None
        if not isinstance(feature_list, list) or not feature_list:
            raise ValueError("模型 pkl 缺少非空 feature_list")
        return feature_list

    @staticmethod
    def _normalize_accuracy_record(metrics: Any) -> Dict[str, Any]:
        """Adapt workflow metrics to the existing Accuracy_Record shape."""
        metrics = metrics if isinstance(metrics, dict) else {}
        return {
            'macro_f1_mean': metrics.get('macro_f1_mean', metrics.get('f1')),
            'macro_f1_std': metrics.get('macro_f1_std'),
            'accuracy_mean': metrics.get('accuracy_mean', metrics.get('accuracy')),
            'accuracy_std': metrics.get('accuracy_std'),
            'macro_precision_mean': metrics.get('macro_precision_mean', metrics.get('precision')),
            'macro_recall_mean': metrics.get('macro_recall_mean', metrics.get('recall')),
            'per_class_recall_mean': metrics.get('per_class_recall_mean', {}),
            'per_class_metrics': metrics.get('per_class_metrics', []),
            'per_repeat_macro_f1': metrics.get('per_repeat_macro_f1', []),
            'confusion_matrix': metrics.get('confusion_matrix', {}),
            'class_distribution': metrics.get('class_distribution', {}),
            'n_repeats': metrics.get('n_repeats'),
            'n_samples': metrics.get('n_samples'),
            'n_classes': metrics.get('n_classes'),
            'warnings': metrics.get('warnings', []),
        }

    @staticmethod
    def _json_safe(value: Any) -> Any:
        """Convert workflow values (including NumPy/Pandas scalars) to JSON-safe values."""
        import math

        if isinstance(value, dict):
            return {str(key): LoopOrchestrator._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [LoopOrchestrator._json_safe(item) for item in value]
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        if hasattr(value, 'item'):
            try:
                return LoopOrchestrator._json_safe(value.item())
            except Exception:
                pass
        if hasattr(value, 'isoformat'):
            try:
                return value.isoformat()
            except Exception:
                pass
        return value

    def trigger_train_eval(
        self,
        loop_id: str,
        dataset_version: str,
        model_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute the real PV training workflow and advance this loop once on success."""
        import sys
        import pandas as pd

        dataset_file, dataset_version = self._resolve_project_dataset(dataset_version)
        if loop_id not in self._loops:
            raise KeyError(f"闭环 {loop_id} 不存在")
        if self._loops[loop_id].get('stage') not in (None, 'backfilled'):
            raise StageTransitionError(
                f"训练阶段要求当前阶段为 None 或 'backfilled'，但当前为 '{self._loops[loop_id].get('stage')}'"
            )

        if dataset_file.lower().endswith('.csv'):
            dataset = pd.read_csv(dataset_file)
        else:
            dataset = pd.read_parquet(dataset_file)
        if 'label' not in dataset.columns:
            raise ValueError("训练数据缺少真值标签列: missing_columns=['label']")
        if dataset['label'].dropna().nunique() < 2:
            raise ValueError("训练数据的 label 列至少需要两个非空类别")

        _, backend_service_dir = self._project_roots()
        if backend_service_dir not in sys.path:
            sys.path.insert(0, backend_service_dir)
        from api.workflows_enhanced import load_workflow_from_file, _execute_pipeline_sync

        workflow = load_workflow_from_file('workflow-pv-fault-diag-quickval-cv-v1')
        if workflow is None:
            raise ValueError("训练评估工作流模板 workflow-pv-fault-diag-quickval-cv-v1 不存在")

        params = model_params if isinstance(model_params, dict) else {}
        load_node_found = False
        cv_node_found = False
        for node in workflow.nodes:
            config = node.data.config
            if self._workflow_config_get(config, 'functionId') == 'load_csv':
                self._workflow_config_set(config, 'file_path', dataset_version)
                load_node_found = True
            elif self._workflow_config_get(config, 'functionId') == 'stratified_cv_eval':
                for key, default in {
                    'test_ratio': 0.2,
                    'n_repeats': 10,
                    'random_state': 90,
                    'k': 20,
                }.items():
                    self._workflow_config_set(config, key, params.get(key, default))
                cv_node_found = True
        if not load_node_found or not cv_node_found:
            raise RuntimeError("训练评估工作流缺少 load_csv 或 stratified_cv_eval 节点")

        execution_result = _execute_pipeline_sync(workflow)
        if not execution_result.get('success', False):
            raise RuntimeError(f"训练评估工作流执行失败: {execution_result.get('error', '未知错误')}")

        n10_result = (execution_result.get('nodeResults') or {}).get('qv-stratified_cv_eval-n10')
        if not isinstance(n10_result, dict):
            raise RuntimeError("训练评估工作流输出缺失 n10 节点结果")
        if n10_result.get('success') is False or n10_result.get('status') in {'failed', 'error'}:
            raise RuntimeError("训练评估工作流 n10 节点未成功执行")
        output_summary = n10_result.get('outputSummary')
        if not isinstance(output_summary, dict):
            raise RuntimeError("n10 节点输出缺少 outputSummary")
        model_ref = output_summary.get('model_id')
        model_path_value = output_summary.get('model_path')
        if not model_ref or not model_path_value:
            raise RuntimeError("n10 节点 outputSummary 缺少 model_id 或 model_path")

        model_file, model_path, _ = self._resolve_model_artifact(
            str(model_ref), str(model_path_value)
        )
        feature_list = self._read_model_feature_list(model_file)
        accuracy_record = self._normalize_accuracy_record(execution_result.get('metrics'))
        current_registry = self.label_registry_service.get_current()
        label_space_snapshot = {
            'label_space_version': current_registry.get('label_space_version'),
            'label_ids': [label['label_id'] for label in current_registry.get('labels', [])],
        }

        self.advance_to_trained(
            loop_id=loop_id,
            dataset_version=dataset_version,
            model_ref=str(model_ref),
            label_space_snapshot=label_space_snapshot,
            accuracy_record=accuracy_record,
        )

        return {
            'model_ref': str(model_ref),
            'model_path': model_path,
            'feature_list': feature_list,
            'accuracy_record': accuracy_record,
            'label_space_snapshot': label_space_snapshot,
        }

    def trigger_predict(
        self,
        loop_id: str,
        model_ref: str,
        unlabeled_dataset_version: str,
        prediction_workflow_id: str = "workflow-pv-fault-diag-quickval-predict-v1",
        prediction_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute the PV prediction template, persist a relative-path batch, and advance once."""
        import json
        import os
        import sys
        import tempfile
        import uuid

        if not model_ref:
            raise ValueError("预测阶段必须提供有效的 model_ref（模型引用），禁止隐式重训")
        _dataset_file, dataset_version = self._resolve_project_dataset(unlabeled_dataset_version)
        loop_state = self.get_loop_state(loop_id)
        if loop_state['stage'] != 'trained':
            raise StageTransitionError(
                f"预测阶段要求当前阶段为 'trained'，但当前为 '{loop_state['stage']}'"
            )

        params = prediction_params if isinstance(prediction_params, dict) else {}
        nested_model_params = params.get('model_params')
        requested_model_path = (
            nested_model_params.get('model_path')
            if isinstance(nested_model_params, dict) and nested_model_params.get('model_path')
            else params.get('model_path')
        )
        model_file, model_path, execution_model_path = self._resolve_model_artifact(
            str(model_ref), requested_model_path
        )
        feature_list = self._read_model_feature_list(model_file)

        _, backend_service_dir = self._project_roots()
        if backend_service_dir not in sys.path:
            sys.path.insert(0, backend_service_dir)
        from api.workflows_enhanced import load_workflow_from_file, _execute_pipeline_sync

        workflow = load_workflow_from_file(prediction_workflow_id)
        if workflow is None:
            raise ValueError(f"预测工作流模板 {prediction_workflow_id} 不存在")

        load_node_found = False
        feature_node_found = False
        classifier_node_found = False
        for node in workflow.nodes:
            config = node.data.config
            function_id = self._workflow_config_get(config, 'functionId')
            if function_id == 'load_csv':
                self._workflow_config_set(config, 'file_path', dataset_version)
                load_node_found = True
            elif function_id == 'feature_select':
                self._workflow_config_set(config, 'feature_list', feature_list)
                feature_node_found = True
            elif function_id == 'random_forest_classifier':
                self._workflow_config_set(config, 'model_id', model_ref)
                self._workflow_config_set(config, 'model_path', execution_model_path)
                classifier_node_found = True
        if not (load_node_found and feature_node_found and classifier_node_found):
            raise RuntimeError("预测工作流缺少 load_csv、feature_select 或 random_forest_classifier 节点")

        execution_result = _execute_pipeline_sync(workflow)
        if not execution_result.get('success', False):
            raise RuntimeError(f"预测工作流执行失败: {execution_result.get('error', '未知错误')}")
        raw_predictions = execution_result.get('fault_predictions')
        if not isinstance(raw_predictions, list) or not raw_predictions:
            raise RuntimeError("预测工作流未返回非空 fault_predictions")

        predictions = []
        for index, raw_prediction in enumerate(raw_predictions):
            if not isinstance(raw_prediction, dict):
                raise RuntimeError(f"fault_predictions[{index}] 不是对象")
            predicted_label = raw_prediction.get('predicted_label')
            if predicted_label is None:
                predicted_label = raw_prediction.get('predictions', raw_prediction.get('predict_label'))
            required_fields = ('site_id', 'device_id', 'branch_id', 'time_window', 'confidence')
            missing = [field for field in required_fields if raw_prediction.get(field) is None]
            if predicted_label is None:
                missing.append('predicted_label')
            if missing:
                raise RuntimeError(
                    f"fault_predictions[{index}] 缺少必要字段: {', '.join(missing)}"
                )
            predictions.append(self._json_safe({
                'site_id': raw_prediction['site_id'],
                'device_id': raw_prediction['device_id'],
                'branch_id': raw_prediction['branch_id'],
                'time_window': raw_prediction['time_window'],
                'predicted_label': predicted_label,
                'confidence': raw_prediction['confidence'],
            }))
        if not predictions:
            raise RuntimeError("预测工作流未产生可持久化的预测结果")

        prediction_batch_id = f"pred-{loop_id}-{uuid.uuid4().hex[:8]}"
        slot = str(self.slot or '').strip()
        if (
            not slot
            or os.path.isabs(slot)
            or slot in {'.', '..'}
            or any(part == '..' for part in slot.replace('\\', '/').split('/'))
        ):
            raise ValueError("slot 必须是安全的批次目录名")
        batch_directory = os.path.join(
            backend_service_dir, 'data', 'iterative_labeling', 'prediction_batches', slot
        )
        os.makedirs(batch_directory, exist_ok=True)
        batch_path = os.path.join(batch_directory, f"{prediction_batch_id}.json")
        batch_payload = {
            'dataset_version': dataset_version,
            'model_ref': model_ref,
            'model_path': model_path,
            'predictions': predictions,
            'iteration': loop_state['iteration_round'],
        }
        # 调度或进程中断时，审核 API 只能看到旧完整批次或新完整批次，不能读取半截 JSON。
        temp_fd, temp_path = tempfile.mkstemp(dir=batch_directory, suffix='.tmp', text=True)
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as handle:
                json.dump(batch_payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, batch_path)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise

        self.advance_to_predicted(loop_id, prediction_batch_id)
        updated_loop_state = self._loops[loop_id]
        updated_loop_state['prediction_dataset_version'] = dataset_version
        updated_loop_state['prediction_model_ref'] = model_ref
        updated_loop_state['prediction_model_path'] = model_path
        updated_loop_state['prediction_unit_count'] = len(predictions)
        updated_loop_state['updated_at'] = datetime.utcnow().isoformat()

        return {
            'prediction_batch_id': prediction_batch_id,
            'unit_count': len(predictions),
            'predictions': predictions,
            'model_ref': model_ref,
            'model_path': model_path,
            'dataset_version': dataset_version,
            'iteration_round': updated_loop_state['iteration_round'],
        }
    # @AI_GENERATED: end
    
    def _advance_stage(self, loop_id: str, target_stage: str) -> None:
        """
        内部符号：阶段迁移核心校验与推进
        
        参数：
        - loop_id: str — 迭代闭环唯一标识
        - target_stage: str — 目标阶段（如 'trained', 'predicted' 等）
        
        行为：
        1. 校验 loop_id 存在
        2. 获取当前阶段（current_stage）
        3. 校验 target_stage 是 current_stage 的合法直接后继（查 STAGE_TRANSITIONS 表）
        4. 若合法，更新 loop_state['stage'] = target_stage
        5. 若不合法，抛 StageTransitionError 并返回阶段不满足说明
        
        异常：
        - 若 loop_id 不存在，抛 KeyError
        - 若目标阶段不是当前阶段的合法直接后继，抛 StageTransitionError
        
        映射需求：
        - 需求 12.1（阶段状态机维护）
        - 需求 12.2（禁止跳阶段，返回阶段不满足说明）
        
        **Validates: Requirements 12.1, 12.2（核心阶段校验逻辑）**
        """
        # 校验 loop_id 存在
        if loop_id not in self._loops:
            raise KeyError(f"闭环 {loop_id} 不存在")
        
        loop_state = self._loops[loop_id]
        current_stage = loop_state.get('stage')
        
        # 校验目标阶段是当前阶段的合法直接后继
        expected_next_stage = self.STAGE_TRANSITIONS.get(current_stage)
        
        if target_stage != expected_next_stage:
            # 不合法：抛阶段不满足错误（需求 12.2）
            raise StageTransitionError(
                f"阶段迁移不满足：当前阶段为 '{current_stage}'，"
                f"期望的下一阶段为 '{expected_next_stage}'，"
                f"但尝试迁移到 '{target_stage}'。"
                f"禁止跳过前置阶段直接进入后续阶段。"
            )
        
        # 合法：更新阶段
        loop_state['stage'] = target_stage
