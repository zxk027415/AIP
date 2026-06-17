"""
存储抽象层 - Storage Abstraction Layer

本包定义四类数据的仓储接口（interfaces.py）并提供文件/JSON 实现（file_backend.py）。

设计原则：
1. 接口签名稳定，便于后续切换到数据库实现而不改业务代码
2. 所有接口以 slot（槽位）为分区参数，支持多环境/多产品线
3. 当前阶段：文件/JSON 实现 + 原子写保证一致性
4. 后续阶段：新增数据库实现，调用方零改动

**这个文件是 DB 迁移的唯一边界：未来迁移数据库时只改本 interfaces.py + 新增 db_backend.py，不改服务层代码。**
"""

from .interfaces import (
    ReviewResultRepository,
    GroundTruthRepository,
    IterationHistoryRepository,
    LabelRegistryRepository,
)

from .file_backend import (
    FileReviewResultRepository,
    FileGroundTruthRepository,
    FileIterationHistoryRepository,
    FileLabelRegistryRepository,
    create_file_storage_backend,
)

__all__ = [
    # 抽象接口（DB 迁移边界）
    "ReviewResultRepository",
    "GroundTruthRepository",
    "IterationHistoryRepository",
    "LabelRegistryRepository",
    
    # 文件实现（当前阶段）
    "FileReviewResultRepository",
    "FileGroundTruthRepository",
    "FileIterationHistoryRepository",
    "FileLabelRegistryRepository",
    "create_file_storage_backend",
]
