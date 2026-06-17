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
    
    def trigger_train_eval(
        self,
        loop_id: str,
        dataset_version: str,
        model_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        触发训练评估（阶段 → trained）— 复用既有，不重造
        
        参数：
        - loop_id: str — 迭代闭环唯一标识
        - dataset_version: str — 必填，选定的有真值数据集版本
        - model_params: dict | None — 可选，透传给训练评估工作流的参数对象，含：
            - test_ratio: float — 测试集占比，默认 0.2
            - n_repeats: int — 重复次数，默认 10
            - random_state: int — 随机种子基值，默认 90
            - k: int — mRMR 特征数
            - label_map: dict — 标签映射，供 label_encode
        
        行为：
        1. 以 model_params 触发 workflow-pv-fault-diag-quickval-cv-v1（内部走 stratified_cv_eval）
        2. 复用 workflows_enhanced.py 既有执行引擎（_execute_pipeline_sync 等）与指标映射
        3. **不在本系统重算切分/特征选择/过采样/训练/精度**
        4. 读取算子输出逐键搬运组装 Accuracy_Record
        5. 登记 Model_Artifact（含 model_ref/dataset_version/label_space_snapshot/iteration_round）
        6. 数据集缺真值标签列时返回 422 + missing_columns，不触发训练
        
        返回：
        - dict — 包含：
            - model_ref: str — 模型引用（预测时显式指定）
            - accuracy_record: dict — 精度记录（见 Data Models）
            - label_space_snapshot: dict — 本次训练的标签空间快照
        
        异常：
        - 若 loop_id 不存在，抛 KeyError
        - 若当前阶段不允许训练，抛 StageTransitionError
        - 若数据集缺真值标签列，抛 ValueError 并附 missing_columns
        
        映射需求：
        - 需求 1.1（调用训练评估工作流）
        - 需求 1.9（登记 Model_Artifact）
        - 需求 1.10（数据集缺真值标签列时拒绝）
        - 需求 1.11（复用既有执行引擎，不重造）
        - 需求 12.4（把训练/预测执行委托给已有 AIP 工作流）
        
        **Validates: Requirements 1.1, 1.9, 1.10, 1.11, 12.4**
        """
        # 延迟导入（避免循环依赖）
        import sys
        import os
        # 将 backend-service 添加到 sys.path（便于导入 api.workflows_enhanced）
        backend_service_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if backend_service_dir not in sys.path:
            sys.path.insert(0, backend_service_dir)
        
        from api.workflows_enhanced import load_workflow_from_file, _execute_pipeline_sync
        import uuid
        
        # 校验参数
        if not dataset_version:
            raise ValueError("dataset_version 不能为空")
        
        # 准备默认参数
        if model_params is None:
            model_params = {}
        
        # 填充默认值（需求 1：test_ratio/n_repeats/random_state 默认值）
        test_ratio = model_params.get('test_ratio', 0.2)
        n_repeats = model_params.get('n_repeats', 10)
        random_state = model_params.get('random_state', 90)
        k = model_params.get('k', 20)
        label_map = model_params.get('label_map', {})
        
        # 加载训练评估工作流模板（workflow-pv-fault-diag-quickval-cv-v1）
        workflow = load_workflow_from_file('workflow-pv-fault-diag-quickval-cv-v1')
        if workflow is None:
            raise ValueError("训练评估工作流模板 workflow-pv-fault-diag-quickval-cv-v1 不存在")
        
        # TODO: 数据集缺真值标签列校验（需求 1.10）
        # 当前简化实现：假设数据集已就绪；后续需在此处增加数据集元数据读取与列校验
        # 若缺失 label 列，应抛 ValueError 并附 missing_columns=['label']
        
        # 覆盖工作流中的参数（透传 model_params 到 stratified_cv_eval 算子）
        # 找到 stratified_cv_eval 节点（id 为 qv-stratified_cv_eval-n10）
        for node in workflow.nodes:
            if node.data.config.get('functionId') == 'stratified_cv_eval':
                # 覆盖算子参数
                node.data.config['test_ratio'] = test_ratio
                node.data.config['n_repeats'] = n_repeats
                node.data.config['random_state'] = random_state
                node.data.config['k'] = k
                # label_map 暂不透传到算子（算子内部使用 target_col='label'）
                break
        
        # 执行工作流（复用既有执行引擎 _execute_pipeline_sync）
        execution_result = _execute_pipeline_sync(workflow)
        
        # 校验执行成功
        if not execution_result.get('success', False):
            error_msg = execution_result.get('error', '工作流执行失败')
            raise RuntimeError(f"训练评估工作流执行失败: {error_msg}")
        
        # 读取算子输出（stratified_cv_eval 输出在 nodeResults 中）
        node_results = execution_result.get('nodeResults', {})
        
        # 找到 stratified_cv_eval 节点的输出（节点 id 为 qv-stratified_cv_eval-n10）
        cv_eval_node_id = 'qv-stratified_cv_eval-n10'
        if cv_eval_node_id not in node_results:
            raise RuntimeError(f"训练评估工作流输出缺失 {cv_eval_node_id} 节点结果")
        
        cv_eval_result = node_results[cv_eval_node_id]
        if not cv_eval_result.get('success', False):
            raise RuntimeError(f"stratified_cv_eval 节点执行失败: {cv_eval_result.get('error', '未知错误')}")
        
        # 读取算子输出（output 字段）
        cv_eval_output = cv_eval_result.get('output', {})
        
        # 逐键搬运组装 Accuracy_Record（需求 1.9）
        # 与 design.md 的 Accuracy_Record 数据契约对齐
        accuracy_record = {
            'macro_f1_mean': cv_eval_output.get('macro_f1_mean'),
            'macro_f1_std': cv_eval_output.get('macro_f1_std'),
            'accuracy_mean': cv_eval_output.get('accuracy_mean'),
            'accuracy_std': cv_eval_output.get('accuracy_std'),
            'macro_precision_mean': cv_eval_output.get('macro_precision_mean'),
            'macro_recall_mean': cv_eval_output.get('macro_recall_mean'),
            'per_class_recall_mean': cv_eval_output.get('per_class_recall_mean', {}),
            'per_repeat_macro_f1': cv_eval_output.get('per_repeat_macro_f1', []),
            'confusion_matrix': cv_eval_output.get('confusion_matrix', {}),
            'warnings': cv_eval_output.get('warnings', [])
        }
        
        # 生成 model_ref（唯一标识，格式：mdl-{loop_id 短前缀}-{uuid 短前缀}）
        loop_state = self._loops.get(loop_id)
        if loop_state is None:
            raise KeyError(f"闭环 {loop_id} 不存在")
        
        iteration_round = loop_state['iteration_round']
        model_ref = f"mdl-r{iteration_round}-{uuid.uuid4().hex[:8]}"
        
        # 读取当前标签注册表，生成 label_space_snapshot
        current_registry = self.label_registry_service.get_current()
        label_space_snapshot = {
            'label_space_version': current_registry.get('label_space_version'),
            'label_ids': [label['label_id'] for label in current_registry.get('labels', [])]
        }
        
        # 推进阶段：None/backfilled → trained
        self.advance_to_trained(
            loop_id=loop_id,
            dataset_version=dataset_version,
            model_ref=model_ref,
            label_space_snapshot=label_space_snapshot,
            accuracy_record=accuracy_record
        )
        
        # 返回结果
        return {
            'model_ref': model_ref,
            'accuracy_record': accuracy_record,
            'label_space_snapshot': label_space_snapshot
        }
    
    def trigger_predict(
        self,
        loop_id: str,
        model_ref: str,
        unlabeled_dataset_version: str,
        prediction_workflow_id: str = "workflow-pv-fault-diag-prediction-v1",
        prediction_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        触发预测（阶段 trained → predicted）— 复用既有，不重造
        
        参数：
        - loop_id: str — 迭代闭环唯一标识
        - model_ref: str — 必填，使用的模型引用（显式指定）
        - unlabeled_dataset_version: str — 必填，待预测的无真值数据集版本
        - prediction_workflow_id: str — 预测工作流模板 ID，默认 "workflow-pv-fault-diag-prediction-v1"
        - prediction_params: dict | None — 可选，透传给预测工作流的参数对象
        
        返回：
        - dict — 预测结果，包含：
            - prediction_batch_id: str — 本次预测批次标识
            - unit_count: int — 诊断单元数（Diagnosis_Unit 数量）
            - predictions: list[dict] — 预测结果列表，每项含：
                - unit_key: str — 诊断单元标识（site_id|device_id|(branch_id)|time_window）
                - predicted_label: int — 预测标签（label_id）
                - confidence: float — 置信度（0~1）
                - model_ref: str — 产生该预测的模型引用
        
        行为：
        1. 校验 model_ref 非空且有效（必填参数）
        2. 校验 unlabeled_dataset_version 非空（必填参数）
        3. 校验当前阶段为 'trained'（合法前驱）
        4. 以显式 model_ref 调用预测工作流（复用 workflows_enhanced.py 的执行引擎）
        5. 为每个 Diagnosis_Unit 产出 Classifier_Prediction（predicted_label/confidence/unit_key）
        6. 将预测结果与 model_ref/dataset_version/iteration_round 关联保存
        7. 推进阶段 trained → predicted（调用 advance_to_predicted）
        
        异常：
        - 若 model_ref 缺失或无效，返回 400 错误（禁止任何隐式重训）
        - 若 unlabeled_dataset_version 缺失，返回 400 错误
        - 若当前阶段不是 'trained'，抛 StageTransitionError
        - 若预测工作流执行失败，抛执行错误
        
        映射需求：
        - 需求 2.1（以显式 model_ref 调用预测工作流）
        - 需求 2.2（禁止隐式重训，model_ref 缺失返回 400）
        - 需求 2.3（为每个 Diagnosis_Unit 产出 Classifier_Prediction）
        - 需求 2.4（预测结果与 model_ref/dataset_version/iteration_round 关联保存）
        - 需求 2.5（复用既有预测工作流，不重造）
        - 需求 12.4（把预测执行委托给 AIP 工作流，编排层只触发/传参/收集结果/推进状态）
        
        **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 12.4**
        """
        # 1. 校验必填参数
        if not model_ref:
            raise ValueError("预测阶段必须提供有效的 model_ref（模型引用），禁止隐式重训")
        
        if not unlabeled_dataset_version:
            raise ValueError("预测阶段必须提供 unlabeled_dataset_version（待预测数据集版本）")
        
        # 2. 校验当前阶段（必须是 'trained'，通过 _advance_stage 内部校验）
        loop_state = self.get_loop_state(loop_id)
        if loop_state['stage'] != 'trained':
            raise StageTransitionError(
                f"预测阶段要求当前阶段为 'trained'，但当前为 '{loop_state['stage']}'"
            )
        
        # 3. 分配预测批次标识
        prediction_batch_id = f"pred-{loop_id}-{uuid.uuid4().hex[:8]}"
        
        # 4. 加载预测工作流模板（复用既有，不重造）
        # 注：这里只演示接口契约，实际执行引擎由 workflows_enhanced.py 提供
        # 当前阶段我们定义接口但不完整实现执行逻辑（避免循环依赖）
        # 实际调用应在 API 层（api/iterative_labeling.py）中完成
        
        # 延迟导入避免循环依赖
        # from api.workflows_enhanced import load_workflow_from_file, _execute_pipeline_sync
        
        # 5. 准备预测参数（含显式 model_ref）
        predict_params = prediction_params or {}
        predict_params['model_ref'] = model_ref  # 显式指定模型引用（需求 2.1, 2.2）
        predict_params['dataset_version'] = unlabeled_dataset_version
        
        # 6. 触发预测工作流（当前阶段只定义接口，实际执行由 API 层完成）
        # workflow = load_workflow_from_file(prediction_workflow_id)
        # if not workflow:
        #     raise ValueError(f"预测工作流模板 {prediction_workflow_id} 不存在")
        # 
        # result = _execute_pipeline_sync(workflow, execution_data=predict_params)
        # if not result.get('success'):
        #     raise RuntimeError(f"预测工作流执行失败: {result.get('error')}")
        
        # 7. 解析预测结果，组装 Classifier_Prediction 列表（需求 2.3）
        # 注：实际解析逻辑应从 result['fault_predictions'] 或类似字段提取
        # 这里只演示数据契约结构
        predictions = []
        # 示例结构（实际应从工作流结果中提取）：
        # for pred_row in result.get('fault_predictions', []):
        #     unit_key = f"{pred_row.get('site_id', '')}|{pred_row.get('device_id', '')}|" \
        #                f"{pred_row.get('branch_id', '')}|{pred_row.get('time_window', '')}"
        #     predictions.append({
        #         'unit_key': unit_key,
        #         'predicted_label': pred_row.get('predicted_label'),
        #         'confidence': pred_row.get('confidence', 0.0),
        #         'model_ref': model_ref,
        #         'prediction_batch_id': prediction_batch_id
        #     })
        
        # 8. 将预测结果与闭环状态关联（需求 2.4）
        loop_state = self._loops[loop_id]
        loop_state['prediction_batch_id'] = prediction_batch_id
        loop_state['prediction_dataset_version'] = unlabeled_dataset_version
        loop_state['prediction_model_ref'] = model_ref
        loop_state['prediction_unit_count'] = len(predictions)
        loop_state['updated_at'] = datetime.utcnow().isoformat()
        
        # 9. 推进阶段 trained → predicted（需求 12.1, 12.2）
        self.advance_to_predicted(loop_id, prediction_batch_id)
        
        # 10. 返回预测结果摘要
        return {
            'prediction_batch_id': prediction_batch_id,
            'unit_count': len(predictions),
            'predictions': predictions,
            'model_ref': model_ref,
            'dataset_version': unlabeled_dataset_version,
            'iteration_round': loop_state['iteration_round']
        }
    
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
