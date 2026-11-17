"""
四类仓储抽象接口 - Storage Abstraction Interfaces

**这个文件是 DB 迁移的唯一边界：未来迁移数据库时只改本 interfaces.py + 新增 db_backend.py，不改服务层代码。**

本文件定义四类数据的读写接口：
1. ReviewResultRepository - 审核结果（含 Human_Verdict 人工裁决）
2. GroundTruthRepository - 固化真值标签
3. IterationHistoryRepository - 迭代历史（append-only 只追加）
4. LabelRegistryRepository - 标签注册表（当前版本 + 历史快照）

设计约定：
- 所有接口以 slot（槽位，默认 'default'）为分区参数，支持多环境/多产品线
- 接口签名设计便于后续新增数据库实现，业务调用方无需修改
- 当前阶段：文件/JSON 实现（见 file_backend.py）
- 后续阶段：新增 db_backend.py，通过依赖注入切换实现

主键字段（便于将来 DB 映射）：
- ReviewResultRepository: review_id（审核会话唯一标识）
- GroundTruthRepository: dataset_version（数据集版本）+ unit_key（诊断单元标识）
- IterationHistoryRepository: iteration_id（迭代记录主键）
- LabelRegistryRepository: label_id（标签编码）+ label_space_version（标签空间版本号）
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class ReviewResultRepository(ABC):
    """
    审核结果仓储接口（含 Human_Verdict 人工裁决）
    
    职责：
    - 保存每个审核会话的人工裁决记录
    - 支持会话中断后恢复（断点续审）
    - 记录每条裁决的 unit_key、verdict_label、action_type、reviewer、reviewed_at
    
    主键：review_id（审核会话唯一标识）
    
    后续 DB 映射建议：
    - 表名：review_results 或 review_verdicts
    - 索引：slot + review_id（唯一）、slot + loop_id（外键）、unit_key（便于按单元查询）
    """
    
    @abstractmethod
    def save_verdict(self, slot: str, review_id: str, verdict: Dict[str, Any]) -> None:
        """
        保存一条人工裁决记录
        
        参数：
        - slot: str — 槽位（多环境/多产品线分区键），默认 'default'
        - review_id: str — 审核会话唯一标识（主键）
        - verdict: dict — 裁决记录，包含：
            - unit_key: str — 诊断单元标识（site_id × device_id ×（可选 branch_id）× time_window）
            - verdict_label: int | None — 裁决标签（label_id），skip 时为 None
            - action_type: str — 动作类型（confirm/correct/new_label/skip）
            - is_ground_truth: bool — 是否写入真值（skip 为 false，其余为 true）
            - reviewer: str — 审核人
            - reviewed_at: str — 审核时间（ISO 格式）
        
        副作用：
        - 持久化该裁决到指定槽位的会话记录中
        - 若会话不存在则创建；若单元已有裁决则覆盖（支持改判）
        
        异常：
        - 若 slot 或 review_id 为空，抛 ValueError
        """
        pass
    
    @abstractmethod
    def load_session(self, slot: str, review_id: str) -> Dict[str, Any]:
        """
        加载审核会话的完整状态（含已提交的全部裁决）
        
        参数：
        - slot: str — 槽位
        - review_id: str — 审核会话唯一标识
        
        返回：
        - dict — 会话状态对象，包含：
            - review_id: str — 审核会话唯一标识
            - loop_id: str — 所属迭代闭环
            - status: str — 会话状态（reviewing/reviewed）
            - verdicts: list[dict] — 已提交的人工裁决数组（见 save_verdict 的 verdict 结构）
            - reviewed_count: int — 已审核单元数
            - total_count: int — 待审核单元总数
        
        异常：
        - 若会话不存在，返回空字典或抛 KeyError（由实现决定）
        """
        pass


class GroundTruthRepository(ABC):
    """
    固化真值标签仓储接口
    
    职责：
    - 保存经人工审核固化后的真值标签（confirm/correct/new_label 单元）
    - 支持按数据集版本追溯真值来源
    - 为回流训练集提供数据源
    
    主键：dataset_version（数据集版本）+ unit_key（诊断单元标识）
    
    后续 DB 映射建议：
    - 表名：ground_truth_labels
    - 索引：slot + dataset_version（便于按版本加载）、unit_key（便于单元级查询）
    - 外键：source_iteration（来源迭代轮次）
    """
    
    @abstractmethod
    def append_labels(self, slot: str, dataset_version: str, labels: List[Dict[str, Any]]) -> None:
        """
        追加一批真值标签到指定数据集版本
        
        参数：
        - slot: str — 槽位
        - dataset_version: str — 数据集版本（回流时新分配，主键一部分）
        - labels: list[dict] — 真值标签数组，每项包含：
            - unit_key: str — 诊断单元标识（主键一部分）
            - label_id: int — 真值标签编码
            - source_review_id: str — 来源审核会话（审计用）
            - action_type: str — 原始动作类型（confirm/correct/new_label）
            - reviewer: str — 审核人
            - labeled_at: str — 打标时间（ISO 格式）
        
        副作用：
        - 持久化真值标签，供后续训练使用
        - 若 dataset_version 不存在则创建；若已存在则追加（支持累积合并）
        
        语义：
        - append-only（只追加），已写入的标签不可修改（保证训练集一致性）
        
        异常：
        - 若 labels 为空，可忽略或抛 ValueError（由实现决定）
        """
        pass
    
    @abstractmethod
    def load_labels(self, slot: str, dataset_version: str) -> List[Dict[str, Any]]:
        """
        加载指定数据集版本的全部真值标签
        
        参数：
        - slot: str — 槽位
        - dataset_version: str — 数据集版本
        
        返回：
        - list[dict] — 真值标签数组（见 append_labels 的 labels 结构）
        
        异常：
        - 若数据集版本不存在，返回空列表或抛 KeyError（由实现决定）
        """
        pass


class IterationHistoryRepository(ABC):
    """
    迭代历史仓储接口（append-only 只追加）
    
    职责：
    - 记录每一轮迭代的数据集版本、模型版本、精度指标、标签空间快照
    - 提供按 iteration_round 排序的历史视图
    - 支持「标签越来越多、精度越来越好」的趋势分析
    
    主键：iteration_id（迭代记录主键）
    
    后续 DB 映射建议：
    - 表名：iteration_history
    - 索引：slot + iteration_round（排序查询）、slot + dataset_version（版本追溯）
    - 约束：append-only，已写记录不可修改/删除
    """
    
    @abstractmethod
    def append(self, slot: str, record: Dict[str, Any]) -> None:
        """
        追加一条迭代历史记录
        
        参数：
        - slot: str — 槽位
        - record: dict — 迭代记录，包含：
            - iteration_id: str — 迭代记录主键（便于将来 DB 映射，如 'iter-2026-03-r3'）
            - iteration_round: int — 迭代轮次（从 1 起，用于排序）
            - dataset_version: str — 数据集版本
            - model_version: str — 模型版本 / model_ref
            - accuracy_record: dict — 精度指标（见设计文档 Accuracy_Record）
            - label_space_version: str — 标签空间版本
            - label_count: int — 标签类别数（该轮注册表类别总数）
            - created_at: str — 创建时间（ISO 格式）
        
        副作用：
        - 持久化迭代记录，供追溯与趋势分析
        
        语义：
        - append-only（只追加），已写记录不可修改（保证历史可信）
        
        异常：
        - 若 record 缺少必填字段，抛 ValueError
        """
        pass
    
    @abstractmethod
    def list_sorted(self, slot: str) -> List[Dict[str, Any]]:
        """
        加载指定槽位的全部迭代历史（按 iteration_round 升序）
        
        参数：
        - slot: str — 槽位
        
        返回：
        - list[dict] — 迭代记录数组（见 append 的 record 结构），按 iteration_round 升序排列
        
        用途：
        - 供前端展示迭代历史与趋势曲线
        - 验证「标签越来越多、精度越来越好」
        """
        pass


class LabelRegistryRepository(ABC):
    """
    标签注册表仓储接口（当前版本 + 历史快照）
    
    职责：
    - 登记全部故障标签类别及其编码
    - 支持标签扩充（new_label），分配唯一且不与现有冲突的 label_id
    - 维护标签空间版本管理（label_space_version），每次扩充递增版本
    - 保留历史版本快照，供审计与模型标签空间落后检测
    - 维护与 label_encode 算子兼容的 Label_Map（业务标签 → 数值类别）
    
    主键：label_id（标签编码，永不重编号）+ label_space_version（标签空间版本号）
    
    设计约定：
    - label_id 单调递增（新分配 = max(现有) + 1），永不复用/重编号
    - 存量类别的 encode/decode 映射在后续版本中保持不变
    - 每次标签扩充生成新 label_space_version 并保留历史快照
    
    后续 DB 映射建议：
    - 表名：label_registry（当前版本）+ label_registry_history（历史快照）
    - 索引：slot + label_id（唯一）、slot + label_name（业务名查询）
    - 外键：label_space_version（版本管理）
    """
    
    @abstractmethod
    def load_current(self, slot: str) -> Dict[str, Any]:
        """
        加载指定槽位的当前标签注册表
        
        参数：
        - slot: str — 槽位
        
        返回：
        - dict — 当前注册表对象，包含：
            - label_space_version: str — 当前标签空间版本号（如 'ls-v5'）
            - labels: list[dict] — 标签数组，每项含：
                - label_id: int — 标签编码（主键，永不重编号）
                - label_name: str — 标签业务名称（如 '正常'、'组串失配'、'suite-0'）
                - created_at: str — 创建时间（ISO 格式）
            - label_map: dict[str, int] — 与 label_encode 兼容的标签映射（业务名 → 数值类别）
            - history: list[dict] — 历史版本快照数组，每项含：
                - label_space_version: str — 历史版本号
                - label_ids: list[int] — 该版本包含的标签编码集合
                - snapshot_at: str — 快照时间
        
        用途：
        - 供 UI 预填审核选择的可选标签
        - 供 LLM_Labeling_Assistant 约束建议标签取值
        - 供编排器检测模型标签空间是否落后
        
        异常：
        - 若槽位不存在或注册表未初始化，返回空字典或默认初始版本（由实现决定）
        """
        pass
    
    @abstractmethod
    def save_new_version(self, slot: str, registry: Dict[str, Any]) -> None:
        """
        保存标签注册表的新版本（标签扩充时调用）
        
        参数：
        - slot: str — 槽位
        - registry: dict — 新版本注册表对象（见 load_current 的返回结构）
        
        副作用：
        - 持久化新版本注册表，覆盖当前版本
        - 将旧版本追加到历史快照（append-only）
        
        语义：
        - 新版本的 label_space_version 应严格递增
        - 新版本的 labels 应包含旧版本全部类别（label_id 不变）+ 新增类别
        - 存量类别的 label_map 映射保持不变（保证历史标注稳定性）
        
        异常：
        - 若 registry 缺少必填字段或 label_id 冲突，抛 ValueError
        """
        pass
