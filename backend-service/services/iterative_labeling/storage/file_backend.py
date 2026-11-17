"""
文件/JSON 后端实现 - File Backend Implementation

**当前阶段：文件/JSON 实现；后续阶段：迁移到数据库（DB）。**

本文件实现 interfaces.py 定义的四类仓储接口：
1. FileReviewResultRepository - 审核结果（含 Human_Verdict）
2. FileGroundTruthRepository - 固化真值标签
3. FileIterationHistoryRepository - 迭代历史（append-only）
4. FileLabelRegistryRepository - 标签注册表（当前版本 + 历史快照）

路径布局（相对于根目录 data/iterative_labeling/）：
- review_results/{slot}/{review_id}.json - 审核会话结果
- ground_truth/{slot}/{dataset_version}.json - 固化真值标签
- iterations/{slot}/*.json - 迭代历史（每条一个文件，以 iteration_id 命名）
- label_registry.json - 标签注册表（含当前版本 + 历史快照）

设计约定：
- 根目录由部署配置注入（环境变量 ITERATIVE_LABELING_DATA_ROOT，默认 'data/iterative_labeling/'）
- **不写死绝对路径**，便于不同克隆仓库和部署环境复用
- 原子写：写临时文件 → fsync → os.replace 覆盖目标，避免会话中断导致半截记录
- 槽位分区：按 slot（默认 'default'）分区，支持多环境/多产品线

后续迁移 DB 时：
- 业务调用方无需修改（只依赖 interfaces.py 抽象接口）
- 新增 db_backend.py 实现相同接口，通过依赖注入切换
- 主键字段已在 interfaces.py 标注，便于建表
"""

import os
import json
import tempfile
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

from .interfaces import (
    ReviewResultRepository,
    GroundTruthRepository,
    IterationHistoryRepository,
    LabelRegistryRepository
)


def _get_data_root() -> Path:
    """
    获取数据根目录
    
    返回：
    - Path — 数据根目录路径（绝对路径）
    
    约定：
    - 优先读取环境变量 ITERATIVE_LABELING_DATA_ROOT
    - 未设置时默认为 'backend-service/data/iterative_labeling/'（相对于当前工作目录）
    - 不写死绝对路径，便于不同环境复用
    """
    root_str = os.environ.get(
        'ITERATIVE_LABELING_DATA_ROOT',
        'data/iterative_labeling/'  # 默认相对路径
    )
    root = Path(root_str)
    # 确保目录存在
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


# @AI_GENERATED: Windows 下 JSON 原子替换遇到瞬时读锁时有限退避重试

def _atomic_write_json(
    target_path: Path,
    data: Any,
    *,
    retries: int = 10,
    retry_delay: float = 0.05,
) -> None:
    """原子写 JSON；仅对 Windows 常见的瞬时 ``PermissionError`` 重试替换。"""
    import time

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        dir=str(target_path.parent),
        suffix='.tmp',
        text=True,
    )
    tmp_path = Path(tmp_path_str)

    try:
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        attempts = max(int(retries), 1)
        last_error = None
        for attempt in range(attempts):
            try:
                tmp_path.replace(target_path)
                return
            except PermissionError as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    time.sleep(retry_delay * (attempt + 1))
        if last_error is not None:
            raise last_error
        raise RuntimeError("原子写 JSON 未完成")
    except Exception as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise IOError(f"原子写 JSON 失败: {target_path}, 错误: {exc}") from exc
# @AI_GENERATED: end


class FileReviewResultRepository(ReviewResultRepository):
    """
    文件实现：审核结果仓储
    
    路径：review_results/{slot}/{review_id}.json
    
    格式示例：
    {
      "review_id": "rev-r3-77",
      "loop_id": "loop-2026-03",
      "status": "reviewing",
      "verdicts": [
        {
          "unit_key": "siteA|dev12|br3|2026-06-01",
          "verdict_label": 1,
          "action_type": "confirm",
          "is_ground_truth": true,
          "reviewer": "operator_zhang",
          "reviewed_at": "2026-06-08T12:06:00"
        }
      ],
      "reviewed_count": 1,
      "total_count": 50
    }
    """
    
    def __init__(self):
        self.data_root = _get_data_root()
    
    def save_verdict(self, slot: str, review_id: str, verdict: Dict[str, Any]) -> None:
        """
        保存审核数据（原子写）。

        兼容两种入参：
        - 完整会话状态（含 'units' 或 'total_count'）：直接整体写入（review_session 的用法）
        - 单条裁决（仅含 unit_key 等）：加载现有会话后按 unit_key 去重追加/改判
        """
        if not slot or not review_id:
            raise ValueError("slot 和 review_id 不能为空")

        target_path = self.data_root / 'review_results' / slot / f'{review_id}.json'

        # 情况一：传入的是完整会话状态，直接整体持久化（保留 units / prediction_context 等）
        if isinstance(verdict, dict) and ('units' in verdict or 'total_count' in verdict):
            _atomic_write_json(target_path, verdict)
            return

        # 情况二：传入的是单条裁决，按 unit_key 合并到现有会话
        session = self.load_session(slot, review_id)
        if not session:
            session = {
                'review_id': review_id,
                'loop_id': verdict.get('loop_id', ''),
                'status': 'reviewing',
                'verdicts': [],
                'reviewed_count': 0,
                'total_count': verdict.get('total_count', 0)
            }
        
        # 更新或追加裁决（按 unit_key 去重，支持改判）
        unit_key = verdict.get('unit_key')
        existing_idx = None
        for i, v in enumerate(session['verdicts']):
            if v.get('unit_key') == unit_key:
                existing_idx = i
                break
        
        if existing_idx is not None:
            # 覆盖已有裁决（改判）
            session['verdicts'][existing_idx] = verdict
        else:
            # 追加新裁决
            session['verdicts'].append(verdict)
        
        # 更新统计
        session['reviewed_count'] = len(session['verdicts'])
        
        # 原子写入
        _atomic_write_json(target_path, session)
    
    def load_session(self, slot: str, review_id: str) -> Dict[str, Any]:
        """加载审核会话的完整状态"""
        target_path = self.data_root / 'review_results' / slot / f'{review_id}.json'
        
        if not target_path.exists():
            return {}  # 会话不存在返回空字典
        
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            raise IOError(f"加载审核会话失败: {target_path}, 错误: {e}") from e


class FileGroundTruthRepository(GroundTruthRepository):
    """
    文件实现：固化真值标签仓储
    
    路径：ground_truth/{slot}/{dataset_version}.json
    
    格式示例：
    {
      "dataset_version": "ds-v4",
      "source_iteration": 3,
      "labels": [
        {
          "unit_key": "siteA|dev12|br3|2026-06-01",
          "label_id": 1,
          "source_review_id": "rev-r3-77",
          "action_type": "confirm",
          "reviewer": "operator_zhang",
          "labeled_at": "2026-06-08T12:06:00"
        }
      ]
    }
    """
    
    def __init__(self):
        self.data_root = _get_data_root()
    
    def append_labels(self, slot: str, dataset_version: str, labels: List[Dict[str, Any]]) -> None:
        """追加一批真值标签到指定数据集版本（原子写）"""
        if not labels:
            return  # 空列表直接返回
        
        # 加载现有标签（不存在则创建）
        existing = self.load_labels(slot, dataset_version)
        if not existing:
            container = {
                'dataset_version': dataset_version,
                'source_iteration': labels[0].get('source_iteration', 0),
                'labels': []
            }
        else:
            container = {
                'dataset_version': dataset_version,
                'source_iteration': existing[0].get('source_iteration', 0) if existing else 0,
                'labels': existing
            }
        
        # 追加新标签（按 unit_key 去重，后来的覆盖已有的）
        existing_keys = {label.get('unit_key') for label in container['labels']}
        for label in labels:
            unit_key = label.get('unit_key')
            if unit_key not in existing_keys:
                container['labels'].append(label)
                existing_keys.add(unit_key)
            else:
                # 覆盖已有标签（支持重新打标）
                for i, existing_label in enumerate(container['labels']):
                    if existing_label.get('unit_key') == unit_key:
                        container['labels'][i] = label
                        break
        
        # 原子写入
        target_path = self.data_root / 'ground_truth' / slot / f'{dataset_version}.json'
        _atomic_write_json(target_path, container)
    
    def load_labels(self, slot: str, dataset_version: str) -> List[Dict[str, Any]]:
        """加载指定数据集版本的全部真值标签"""
        target_path = self.data_root / 'ground_truth' / slot / f'{dataset_version}.json'
        
        if not target_path.exists():
            return []  # 数据集版本不存在返回空列表
        
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                container = json.load(f)
                return container.get('labels', [])
        except (IOError, json.JSONDecodeError) as e:
            raise IOError(f"加载真值标签失败: {target_path}, 错误: {e}") from e


class FileIterationHistoryRepository(IterationHistoryRepository):
    """
    文件实现：迭代历史仓储（append-only）
    
    路径：iterations/{slot}/*.json（每条一个文件，以 iteration_id 命名）
    
    格式示例（单条）：
    {
      "iteration_id": "iter-2026-03-r3",
      "iteration_round": 3,
      "dataset_version": "ds-v3",
      "model_version": "mdl-2026round3-a1b2",
      "accuracy_record": { ... },
      "label_space_version": "ls-v5",
      "label_count": 5,
      "created_at": "2026-06-08T12:10:00"
    }
    """
    
    def __init__(self):
        self.data_root = _get_data_root()
    
    def append(self, slot: str, record: Dict[str, Any]) -> None:
        """追加一条迭代历史记录（原子写）"""
        iteration_id = record.get('iteration_id')
        if not iteration_id:
            raise ValueError("迭代记录缺少 iteration_id 字段")
        
        # 必填字段校验
        required_fields = [
            'iteration_round', 'dataset_version', 'model_version',
            'accuracy_record', 'label_space_version', 'label_count'
        ]
        for field in required_fields:
            if field not in record:
                raise ValueError(f"迭代记录缺少必填字段: {field}")
        
        # 原子写入（以 iteration_id 为文件名）
        target_path = self.data_root / 'iterations' / slot / f'{iteration_id}.json'
        _atomic_write_json(target_path, record)
    
    def list_sorted(self, slot: str) -> List[Dict[str, Any]]:
        """加载指定槽位的全部迭代历史（按 iteration_round 升序）"""
        iterations_dir = self.data_root / 'iterations' / slot
        
        if not iterations_dir.exists():
            return []  # 槽位不存在返回空列表
        
        # 读取全部 JSON 文件
        records = []
        for json_file in iterations_dir.glob('*.json'):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    record = json.load(f)
                    records.append(record)
            except (IOError, json.JSONDecodeError) as e:
                # 单个文件损坏不影响其他记录
                print(f"警告：加载迭代历史记录失败: {json_file}, 错误: {e}")
                continue
        
        # 按 iteration_round 升序排列
        records.sort(key=lambda r: r.get('iteration_round', 0))
        return records


class FileLabelRegistryRepository(LabelRegistryRepository):
    """
    文件实现：标签注册表仓储
    
    路径：label_registry.json（全局单文件，含全部槽位）
    
    格式示例：
    {
      "slots": {
        "default": {
          "label_space_version": "ls-v5",
          "labels": [
            {
              "label_id": 0,
              "label_name": "正常",
              "created_at": "2026-05-01T00:00:00"
            },
            {
              "label_id": 1,
              "label_name": "组串失配",
              "created_at": "2026-05-01T00:00:00"
            }
          ],
          "label_map": {
            "正常": 0,
            "组串失配": 1
          },
          "history": [
            {
              "label_space_version": "ls-v4",
              "label_ids": [0, 1],
              "snapshot_at": "2026-05-20T00:00:00"
            }
          ]
        }
      }
    }
    """
    
    def __init__(self):
        self.data_root = _get_data_root()
        self.registry_path = self.data_root / 'label_registry.json'
    
    def load_current(self, slot: str) -> Dict[str, Any]:
        """加载指定槽位的当前标签注册表"""
        if not self.registry_path.exists():
            # 注册表未初始化，返回默认空版本
            return {
                'label_space_version': 'ls-v1',
                'labels': [],
                'label_map': {},
                'history': []
            }
        
        try:
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                all_slots = json.load(f)
                slots = all_slots.get('slots', {})
                
                # 槽位不存在返回默认空版本
                return slots.get(slot, {
                    'label_space_version': 'ls-v1',
                    'labels': [],
                    'label_map': {},
                    'history': []
                })
        except (IOError, json.JSONDecodeError) as e:
            raise IOError(f"加载标签注册表失败: {self.registry_path}, 错误: {e}") from e
    
    def save_new_version(self, slot: str, registry: Dict[str, Any]) -> None:
        """保存标签注册表的新版本（原子写）"""
        # 必填字段校验
        if 'label_space_version' not in registry:
            raise ValueError("注册表缺少 label_space_version 字段")
        if 'labels' not in registry:
            raise ValueError("注册表缺少 labels 字段")
        if 'label_map' not in registry:
            raise ValueError("注册表缺少 label_map 字段")
        
        # label_id 冲突检查
        label_ids = [label['label_id'] for label in registry['labels']]
        if len(label_ids) != len(set(label_ids)):
            raise ValueError("注册表中存在重复的 label_id")
        
        # 加载全部槽位（不存在则创建）
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r', encoding='utf-8') as f:
                    all_slots = json.load(f)
            except (IOError, json.JSONDecodeError):
                all_slots = {'slots': {}}
        else:
            all_slots = {'slots': {}}
        
        # 更新指定槽位
        all_slots['slots'][slot] = registry
        
        # 原子写入
        _atomic_write_json(self.registry_path, all_slots)


# 导出便利工厂函数（供服务层统一创建实例）
def create_file_storage_backend() -> tuple:
    """
    创建文件存储后端的全部四类仓储实例
    
    返回：
    - tuple — (review_repo, ground_truth_repo, iteration_repo, label_registry_repo)
    
    用途：
    - 供服务层（orchestrator、review_session 等）统一创建存储后端
    - 后续迁移 DB 时只需修改此函数，服务层无需改动
    """
    return (
        FileReviewResultRepository(),
        FileGroundTruthRepository(),
        FileIterationHistoryRepository(),
        FileLabelRegistryRepository()
    )
