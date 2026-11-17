"""
Iteration_Tracker - 迭代追踪器服务

**职责：**
1. append-only 追加迭代记录（iteration_id / iteration_round / dataset_version / model_version / 
   accuracy_record / label_space_version / label_count / created_at）
2. 经 IterationHistoryRepository 持久化
3. 提供按 iteration_round 排序的可追溯历史视图
4. 提供趋势分析（macro_f1_by_round / label_count_by_round）

**映射需求：**
- 需求 10.1: 关键节点完成时追加迭代历史记录
- 需求 10.2: 保存 iteration_round/dataset_version/model_version/accuracy_record/
             label_space_version/label_count/created_at
- 需求 10.3: 提供按 iteration_round 排序的可追溯历史视图，展示精度指标与标签类别数随轮次的变化趋势
- 需求 10.4: append-only 语义，已记录的历史条目不被覆盖或删除
- 需求 10.5: 经 Storage_Abstraction 接口持久化迭代历史

**数据契约（来自设计文档）：**
```jsonc
{
  "iteration_id": "iter-2026-03-r3",          // 迭代记录主键（便于将来 DB 映射）
  "iteration_round": 3,                       // 迭代轮次（从 1 起）
  "dataset_version": "ds-v3",                 // 数据集版本
  "model_version": "mdl-2026round3-a1b2",     // 模型版本 / model_ref
  "accuracy_record": { /* 见设计 */ },        // 精度指标
  "label_space_version": "ls-v5",             // 标签空间版本
  "label_count": 5,                           // 标签类别数（该轮注册表类别总数）
  "created_at": "2026-06-08T12:10:00"         // 创建时间
}
```

**趋势对象（用于验证「标签越来越多、精度越来越好」）：**
```jsonc
{
  "macro_f1_by_round": [0.75, 0.78, 0.81],    // 各轮 macro_f1 均值数组
  "label_count_by_round": [3, 4, 5]           // 各轮标签类别数数组
}
```

**关键约定：**
- append-only 语义：只追加，已写历史条目不被覆盖或删除（需求 10.4）
- 每条记录有 iteration_id 主键（便于将来 DB 映射）
- 按 iteration_round 排序视图（需求 10.3）
- 趋势提取：macro_f1_by_round / label_count_by_round（验证闭环效果）
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

from .storage.interfaces import IterationHistoryRepository


class IterationTracker:
    """
    迭代追踪器
    
    职责：
    - 记录每一轮迭代的关键节点（训练完成、预测完成、审核完成、回流完成）
    - 提供按轮次排序的历史视图
    - 提供趋势分析（macro_f1_by_round / label_count_by_round）
    
    用途：
    - 供 Loop_Orchestrator 在关键节点调用 append_record() 追加记录
    - 供前端调用 list_history() 展示迭代历史与趋势曲线
    - 供复盘验证「标签越来越多、精度越来越好」
    """
    
    def __init__(self, slot: str = "default", history_repo: Optional[IterationHistoryRepository] = None):
        """
        初始化迭代追踪器
        
        参数：
        - slot: str — 槽位（多环境/多产品线分区键），默认 'default'（默认槽）
        - history_repo: IterationHistoryRepository | None — 迭代历史仓储接口实现；
                                                              若为 None，则从依赖注入或默认实现获取
        """
        self.slot = slot
        self.history_repo = history_repo
        
        # 若未注入 history_repo，从默认 file_backend 获取（延迟导入避免循环依赖）
        if self.history_repo is None:
            from .storage.file_backend import FileIterationHistoryRepository
            self.history_repo = FileIterationHistoryRepository()
    
    def append_record(self, record: Dict[str, Any]) -> None:
        """
        追加一条迭代历史记录（关键节点完成时调用）
        
        参数：
        - record: dict — 迭代记录，必须包含：
            - iteration_id: str — 迭代记录主键（如 'iter-2026-03-r3'）
            - iteration_round: int — 迭代轮次（从 1 起）
            - dataset_version: str — 数据集版本
            - model_version: str — 模型版本 / model_ref
            - accuracy_record: dict — 精度指标（含 macro_f1_mean/macro_f1_std 等）
            - label_space_version: str — 标签空间版本
            - label_count: int — 标签类别数
            - created_at: str — 创建时间（ISO 格式），可选，缺失时自动生成
        
        副作用：
        - 经 IterationHistoryRepository 持久化该记录
        
        语义：
        - append-only（只追加），不修改已有记录
        
        异常：
        - 若 record 缺少必填字段，抛 ValueError
        
        **Validates: Requirements 10.1, 10.2, 10.4, 10.5**
        """
        # 校验必填字段
        required_fields = [
            "iteration_id", "iteration_round", "dataset_version", "model_version",
            "accuracy_record", "label_space_version", "label_count"
        ]
        missing = [f for f in required_fields if f not in record]
        if missing:
            raise ValueError(f"追加迭代记录缺少必填字段: {', '.join(missing)}")
        
        # 自动生成 created_at（若缺失）
        if "created_at" not in record:
            record["created_at"] = datetime.utcnow().isoformat()
        
        # 持久化（委托给 IterationHistoryRepository）
        self.history_repo.append(self.slot, record)
    
    def list_history(self) -> List[Dict[str, Any]]:
        """
        获取按 iteration_round 排序的全部迭代历史
        
        返回：
        - list[dict] — 迭代记录数组（见 append_record 的 record 结构），按 iteration_round 升序排列
        
        用途：
        - 供前端展示迭代历史表格
        - 供 Loop_Orchestrator 定位历史某一轮的数据集版本/模型版本/标签空间快照
        
        **Validates: Requirements 10.3**
        """
        return self.history_repo.list_sorted(self.slot)
    
    def get_trend(self) -> Dict[str, List]:
        """
        获取趋势分析（用于验证「标签越来越多、精度越来越好」）
        
        返回：
        - dict — 趋势对象，包含：
            - macro_f1_by_round: list[float] — 各轮 macro_f1 均值数组（从 accuracy_record 提取）
            - label_count_by_round: list[int] — 各轮标签类别数数组
        
        计算逻辑：
        - 按 iteration_round 升序排列历史记录
        - 从每条记录的 accuracy_record['macro_f1_mean'] 提取宏平均 F1 均值
        - 从每条记录的 label_count 提取标签类别数
        - 若某轮 accuracy_record 缺少 macro_f1_mean，该轮置为 None
        
        用途：
        - 供前端绘制趋势曲线（迭代轮次为 X 轴，macro_f1 / label_count 为 Y 轴）
        - 供复盘验证闭环是否「标签越来越多、精度越来越好」
        
        **Validates: Requirements 10.3**
        """
        history = self.list_history()
        
        macro_f1_by_round = []
        label_count_by_round = []
        
        for record in history:
            # 提取 macro_f1_mean（主精度口径）
            accuracy_record = record.get("accuracy_record", {})
            macro_f1 = accuracy_record.get("macro_f1_mean")
            macro_f1_by_round.append(macro_f1)  # 缺失时为 None
            
            # 提取 label_count
            label_count = record.get("label_count", 0)
            label_count_by_round.append(label_count)
        
        return {
            "macro_f1_by_round": macro_f1_by_round,
            "label_count_by_round": label_count_by_round
        }
    
    def get_record_by_round(self, iteration_round: int) -> Optional[Dict[str, Any]]:
        """
        按迭代轮次查询历史记录（便于定位某一轮的数据集版本/模型版本/标签空间快照）
        
        参数：
        - iteration_round: int — 迭代轮次（从 1 起）
        
        返回：
        - dict | None — 该轮的迭代记录（见 append_record 的 record 结构），若不存在则返回 None
        
        用途：
        - 供 Loop_Orchestrator 复核历史某一轮（需求 12.5）
        - 供前端展示某一轮的详细信息
        
        **Validates: Requirements 12.5（历史轮次定位往返）**
        """
        history = self.list_history()
        for record in history:
            if record.get("iteration_round") == iteration_round:
                return record
        return None

