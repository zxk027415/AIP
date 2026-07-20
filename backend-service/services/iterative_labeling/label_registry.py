"""
标签注册表服务 - Label Registry Service

**职责**：
- 登记全部故障标签类别及其编码
- 支持标签扩充（new_label），分配唯一且不与现有冲突的 label_id
- 维护标签空间版本管理（label_space_version），每次扩充递增版本
- 保留历史版本快照，供审计与模型标签空间落后检测
- 维护与 label_encode 算子兼容的 Label_Map（业务标签 → 数值类别）

**关键约定**（来自设计文档）：

1. **label_id 分配规则**：
   - 单调递增：label_id = max(现有 label_id) + 1
   - 永不复用/重编号：已分配的 label_id 在后续版本中保持稳定
   - 这保证历史标注引用的编码不会失真

2. **label_space_version 规则**：
   - 每次标签扩充生成新版本号（如 ls-v1 → ls-v2）
   - 历史版本快照只追加不修改（append-only）
   - 存量类别的 encode/decode 映射保持不变

3. **标签空间落后检测**：
   - 比较模型的 label_space_snapshot 版本与当前注册表 label_space_version
   - 不一致则标记 label_space_lag = True，提示新类别需下一轮重训才被模型识别

4. **与 label_encode 算子的关系**：
   - label_encode 是已交付的算子（来自 pv-fault-diagnosis-integration spec）
   - 本服务维护 Label_Map，供 label_encode 的 encode/decode 模式消费
   - **不重新实现**编解码逻辑，只维护映射字典

**数据模型参考**（来自设计文档）：
```jsonc
{
  "label_space_version": "ls-v5",
  "labels": [
    { "label_id": 0,  "label_name": "正常", "created_at": "2026-05-01T00:00:00" },
    { "label_id": 1,  "label_name": "组串失配", "created_at": "2026-05-01T00:00:00" },
    { "label_id": 20, "label_name": "suite-0", "created_at": "2026-06-01T00:00:00" }
  ],
  "label_map": {
    "正常": 0,
    "组串失配": 1,
    "suite-0": 20
  },
  "history": [
    { "label_space_version": "ls-v4", "label_ids": [0, 1], "snapshot_at": "2026-05-20T00:00:00" }
  ]
}
```

**映射需求**：
- 需求 8.1: 为新标签分配唯一且不与现有冲突的 label_id
- 需求 8.2: 每次标签空间变更生成新 label_space_version，保留历史版本快照
- 需求 8.3: 维护与 label_encode 兼容的 Label_Map，保证新增类别后存量类别映射不变
- 需求 8.4: 标注模型为「标签空间落后」并提示新类别需下一轮重训才会被模型识别
- 需求 8.5: 保证已固化真值标签所引用的 label_id 在后续版本中保持稳定
- 需求 11.1: 持久化经 LabelRegistryRepository（来自 Task 1）
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

from .storage.interfaces import LabelRegistryRepository


class LabelRegistryService:
    """
    标签注册表服务
    
    提供标签扩充、版本管理、Label_Map 维护、标签空间落后检测等功能。
    
    示例用法：
    ```python
    # 初始化服务（注入仓储）
    from .storage.file_backend import FileLabelRegistryRepository
    registry_repo = FileLabelRegistryRepository()
    service = LabelRegistryService(slot='default', registry_repo=registry_repo)
    
    # 分配新标签
    new_label_id = service.allocate_label('新故障类型')
    
    # 获取当前注册表
    current_registry = service.get_current()
    
    # 检测模型标签空间是否落后
    is_lagging = service.check_label_space_lag('ls-v3')
    
    # 获取 Label_Map（供 label_encode 消费）
    label_map = service.get_label_map()
    ```
    """
    
    def __init__(
        self,
        slot: str = 'default',
        registry_repo: Optional[LabelRegistryRepository] = None
    ):
        """
        初始化标签注册表服务
        
        参数：
        - slot: str — 槽位（多环境/多产品线分区键），默认 'default'（默认槽）
        - registry_repo: LabelRegistryRepository | None — 仓储实例（可注入用于测试）；
          为 None 时使用默认文件后端
        
        说明：
        - slot 用于多产品线/多环境分区，如 'aesc'、'mengxi' 等
        - 默认槽位为 'default'，适用于单产品线场景
        """
        self.slot = slot
        
        # 依赖注入：允许测试时注入 mock 仓储
        if registry_repo is None:
            from .storage.file_backend import FileLabelRegistryRepository
            registry_repo = FileLabelRegistryRepository()
        
        self.registry_repo = registry_repo
    
    def allocate_label(self, label_name: str) -> int:
        """
        分配新标签 ID（标签扩充）
        
        参数：
        - label_name: str — 新标签业务名称（如 '新故障类型'、'suite-5'）
        
        返回：
        - int — 新分配的 label_id（主键，永不重编号）
        
        行为：
        1. 加载当前注册表
        2. 检查 label_name 是否已存在（已存在则直接返回其 label_id，不重复分配）
        3. 计算新 label_id = max(现有 label_id) + 1（单调递增）
        4. 生成新 label_space_version（版本号递增）
        5. 将旧版本追加到历史快照（append-only）
        6. 更新 label_map（业务名 → 数值类别）
        7. 持久化新版本注册表
        
        保证：
        - label_id 单调递增，永不复用/重编号（需求 8.1, 8.5）
        - 存量类别的 label_map 映射保持不变（需求 8.3）
        - 历史快照只追加不修改（需求 8.2）
        
        异常：
        - 若 label_name 为空，抛 ValueError
        """
        if not label_name or not label_name.strip():
            raise ValueError("标签名称不能为空")
        
        label_name = label_name.strip()
        
        # 加载当前注册表
        current = self.registry_repo.load_current(self.slot)
        
        # 检查标签名是否已存在
        existing_label = None
        for label in current.get('labels', []):
            if label.get('label_name') == label_name:
                existing_label = label
                break
        
        if existing_label is not None:
            # 标签已存在，直接返回其 label_id（幂等）
            return existing_label['label_id']
        
        # 分配新 label_id = max(现有) + 1（单调递增，永不复用）
        existing_label_ids = [label['label_id'] for label in current.get('labels', [])]
        new_label_id = max(existing_label_ids) + 1 if existing_label_ids else 0
        
        # 生成新 label_space_version（版本号递增）
        old_version = current.get('label_space_version', 'ls-v1')
        new_version = self._increment_version(old_version)
        
        # 保存旧版本快照到历史（append-only）
        old_label_ids = [label['label_id'] for label in current.get('labels', [])]
        new_history = current.get('history', [])
        if old_label_ids:  # 只有存在旧标签时才保存快照
            new_history.append({
                'label_space_version': old_version,
                'label_ids': old_label_ids,
                'snapshot_at': datetime.utcnow().isoformat()
            })
        
        # 创建新标签记录
        new_label = {
            'label_id': new_label_id,
            'label_name': label_name,
            'created_at': datetime.utcnow().isoformat()
        }
        
        # 组装新版本注册表（存量 + 新增）
        new_labels = current.get('labels', []) + [new_label]
        
        # 更新 label_map（业务名 → 数值类别，存量映射保持不变）
        new_label_map = current.get('label_map', {}).copy()
        new_label_map[label_name] = new_label_id
        
        # 组装完整注册表
        new_registry = {
            'label_space_version': new_version,
            'labels': new_labels,
            'label_map': new_label_map,
            'history': new_history
        }
        
        # 持久化新版本
        self.registry_repo.save_new_version(self.slot, new_registry)
        
        return new_label_id

    def reconcile_labels(self, labels_by_id: Dict[int, str]) -> Dict[str, Any]:
        """按数据集中已经存在的 label_id 补齐业务名称，不重新分配编码。"""
        if not labels_by_id:
            raise ValueError("至少需要登记一个标签")

        normalized: Dict[int, str] = {}
        for raw_id, raw_name in labels_by_id.items():
            try:
                label_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"标签 ID 无效: {raw_id}") from exc
            if label_id < 0:
                raise ValueError(f"标签 ID 不能为负数: {label_id}")
            label_name = str(raw_name or "").strip()
            if not label_name:
                raise ValueError(f"标签 {label_id} 的业务名称不能为空")
            normalized[label_id] = label_name

        if len(set(normalized.values())) != len(normalized):
            raise ValueError("本次登记的业务名称不能重复")

        current = self.registry_repo.load_current(self.slot)
        current_labels = list(current.get("labels", []))
        id_to_name = {
            int(item["label_id"]): str(item["label_name"])
            for item in current_labels
        }
        name_to_id = {
            str(item["label_name"]): int(item["label_id"])
            for item in current_labels
        }

        additions = []
        now = datetime.utcnow().isoformat()
        for label_id, label_name in normalized.items():
            existing_name = id_to_name.get(label_id)
            if existing_name is not None:
                if existing_name != label_name:
                    raise ValueError(
                        f"标签 ID {label_id} 已登记为“{existing_name}”，不能改为“{label_name}”"
                    )
                continue
            existing_id = name_to_id.get(label_name)
            if existing_id is not None and existing_id != label_id:
                raise ValueError(
                    f"业务名称“{label_name}”已绑定标签 ID {existing_id}，不能重复绑定 {label_id}"
                )
            additions.append(
                {
                    "label_id": label_id,
                    "label_name": label_name,
                    "created_at": now,
                    "source": "snapshot_reconciliation",
                }
            )

        if not additions:
            return current

        old_version = current.get("label_space_version", "ls-v1")
        old_label_ids = sorted(id_to_name)
        history = list(current.get("history", []))
        if old_label_ids:
            history.append(
                {
                    "label_space_version": old_version,
                    "label_ids": old_label_ids,
                    "snapshot_at": now,
                }
            )

        merged_labels = sorted(
            current_labels + additions,
            key=lambda item: int(item["label_id"]),
        )
        label_map = dict(current.get("label_map", {}))
        for item in additions:
            label_map[item["label_name"]] = item["label_id"]

        reconciled = {
            "label_space_version": self._increment_version(old_version),
            "labels": merged_labels,
            "label_map": label_map,
            "history": history,
        }
        self.registry_repo.save_new_version(self.slot, reconciled)
        return reconciled
    
    def seed_labels(
        self,
        label_map: Dict[str, int],
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        用给定 label_map 初始化标签注册表（仅当注册表为空时生效）

        参数：
        - label_map: dict[str, int] — 业务名 → 数值类别（如 {"正常":0,"组串遮挡":1,"组串开路":11}）。
          数值类别直接作为 label_id（保留故障码的跳号，如 0/1/4/7/8/11/12/16），不重编号。
        - overwrite: bool — 为 True 时即使注册表已有标签也强制重置；默认 False（幂等，不覆盖既有）

        返回：
        - dict — 初始化后的注册表（label_space_version / labels / label_map / history）

        说明：
        - 用于编辑器驱动场景：从预测工作流 label_encode 的 label_map 播种初始标签空间，
          使审核页的 confirm/correct 能直接引用故障码对应的 label_id。
        - 与 allocate_label 互补：seed 负责"开局"，allocate_label 负责后续单调扩充。
        - 非空且 overwrite=False 时直接返回现有注册表，保证幂等、不破坏已有 label_id。
        """
        current = self.registry_repo.load_current(self.slot)
        if current.get('labels') and not overwrite:
            # 已有标签，幂等返回，避免覆盖既有 label_id
            return current

        now = datetime.utcnow().isoformat()
        labels = []
        normalized_map: Dict[str, int] = {}
        for name, code in label_map.items():
            try:
                label_id = int(code)
            except (TypeError, ValueError):
                continue
            labels.append({
                'label_id': label_id,
                'label_name': str(name),
                'created_at': now
            })
            normalized_map[str(name)] = label_id

        # 按 label_id 升序，便于展示与审计
        labels.sort(key=lambda x: x['label_id'])

        new_registry = {
            'label_space_version': 'ls-v1',
            'labels': labels,
            'label_map': normalized_map,
            'history': []
        }
        self.registry_repo.save_new_version(self.slot, new_registry)
        return new_registry

    def get_current(self) -> Dict[str, Any]:
        """
        获取当前标签注册表（只读）
        
        返回：
        - dict — 当前注册表对象，包含：
            - label_space_version: str — 当前标签空间版本号
            - labels: list[dict] — 标签数组，每项含 label_id、label_name、created_at
            - label_map: dict[str, int] — 与 label_encode 兼容的标签映射
            - history: list[dict] — 历史版本快照数组
        
        用途：
        - 供 UI 预填审核选择的可选标签
        - 供 LLM_Labeling_Assistant 约束建议标签取值
        - 供编排器获取当前标签空间版本
        """
        return self.registry_repo.load_current(self.slot)
    
    def check_label_space_lag(self, model_snapshot_version: str) -> bool:
        """
        检测模型标签空间是否落后
        
        参数：
        - model_snapshot_version: str — 模型训练时的标签空间快照版本号（如 'ls-v3'）
        
        返回：
        - bool — True 表示模型标签空间落后（需要重训才能识别新类别），False 表示同步
        
        行为：
        - 比较 model_snapshot_version 与当前注册表的 label_space_version
        - 不一致则返回 True，提示新类别需下一轮重训才会被模型识别
        
        用途：
        - 供编排器在读取 Model_Artifact 时标注 label_space_lag 字段
        - 供 UI 展示模型是否需要重训的提示
        
        映射需求：
        - 需求 8.4: 标注模型为「标签空间落后」并提示新类别需下一轮重训
        """
        current = self.get_current()
        current_version = current.get('label_space_version', 'ls-v1')
        
        # 简单版本号比较（假设格式为 'ls-vN'）
        # 注：实际生产可能需要更复杂的版本比较逻辑
        return model_snapshot_version != current_version
    
    def get_label_map(self) -> Dict[str, int]:
        """
        获取当前 Label_Map（供 label_encode 消费）
        
        返回：
        - dict[str, int] — 业务标签名 → 数值类别编码的映射
        
        用途：
        - 供 label_encode 算子的 encode/decode 模式消费
        - 供训练评估工作流构建 model_params 的 label_map 参数
        
        说明：
        - 本服务只维护映射字典，**不重新实现** encode/decode 逻辑
        - encode/decode 由已交付的 label_encode 算子完成（来自 pv-fault-diagnosis-integration spec）
        
        映射需求：
        - 需求 8.3: 维护与 label_encode 兼容的 Label_Map
        """
        current = self.get_current()
        return current.get('label_map', {})
    
    def get_label_by_id(self, label_id: int) -> Optional[Dict[str, Any]]:
        """
        按 label_id 查询标签记录（只读）
        
        参数：
        - label_id: int — 标签编码（主键）
        
        返回：
        - dict | None — 标签记录（含 label_id、label_name、created_at），不存在返回 None
        
        用途：
        - 供审核页面展示标签详情
        - 供回流时验证 label_id 有效性
        """
        current = self.get_current()
        for label in current.get('labels', []):
            if label.get('label_id') == label_id:
                return label
        return None
    
    def get_label_by_name(self, label_name: str) -> Optional[Dict[str, Any]]:
        """
        按 label_name 查询标签记录（只读）
        
        参数：
        - label_name: str — 标签业务名称
        
        返回：
        - dict | None — 标签记录（含 label_id、label_name、created_at），不存在返回 None
        
        用途：
        - 供 LLM_Labeling_Assistant 检查建议标签是否在注册表内
        - 供审核页面预填
        """
        current = self.get_current()
        for label in current.get('labels', []):
            if label.get('label_name') == label_name:
                return label
        return None
    
    def _increment_version(self, current_version: str) -> str:
        """
        递增版本号（内部辅助方法）
        
        参数：
        - current_version: str — 当前版本号（如 'ls-v5'）
        
        返回：
        - str — 新版本号（如 'ls-v6'）
        
        逻辑：
        - 假设版本格式为 'ls-vN'（N 为整数）
        - 提取 N，递增 1，返回 'ls-v{N+1}'
        - 若格式不匹配，默认返回 'ls-v1'
        
        示例：
        - 'ls-v5' → 'ls-v6'
        - 'ls-v1' → 'ls-v2'
        - 'invalid' → 'ls-v1'（容错）
        """
        try:
            # 提取版本号（格式：'ls-vN'）
            if current_version.startswith('ls-v'):
                version_num = int(current_version.split('ls-v')[1])
                return f'ls-v{version_num + 1}'
            else:
                # 格式不匹配，默认从 v1 开始
                return 'ls-v1'
        except (IndexError, ValueError):
            # 解析失败，容错返回 v1
            return 'ls-v1'

