"""
services/db/exceptions.py — DB 适配器及数据管线异常类型定义

Requirements: 1.4, 1.9, 8.5
"""

from __future__ import annotations

from typing import List, Optional


class DBAdapterError(Exception):
    """DB 适配器基础异常。所有 DB 适配层异常均继承自此类。"""


class ConnectionExhaustedError(DBAdapterError):
    """连接池耗尽 — 排队等待超时后抛出。

    对应需求 1.9：池满时排队等待超时（默认 30s）后触发。
    """


class MigrationError(DBAdapterError):
    """Schema 迁移失败 — 含失败的 revision ID 和原始异常。

    对应需求 1.8：迁移失败时记录 revision 标识并阻止应用启动。

    Attributes:
        revision: 失败的 Alembic migration revision 标识
        cause: 触发失败的底层异常
    """

    def __init__(self, revision: str, cause: Exception) -> None:
        self.revision = revision
        self.cause = cause
        super().__init__(f"Migration failed at revision '{revision}': {cause}")


class DataSourceError(Exception):
    """数据源操作异常 — 封装底层驱动异常，隐藏实现细节。

    对应需求 8.5：StationDataSource 实现只向调用方暴露此类异常，
    不透传原始数据库驱动异常。
    """


class DataSourceTimeoutError(DataSourceError):
    """数据源查询超时（> 30s）。

    对应需求 8.5：查询耗时超过 30 秒时抛出。
    """


class IngestionError(Exception):
    """数据导入异常 — Parquet 缺列或类型不匹配时抛出。

    对应需求 3.6：导入失败时拒绝整个文件，不产生部分写入。

    Attributes:
        file_path: 导入失败的文件路径
        missing_columns: 缺少的必需列名列表
        type_errors: 类型转换失败的描述列表
    """

    def __init__(
        self,
        file_path: str,
        missing_columns: Optional[List[str]] = None,
        type_errors: Optional[List[str]] = None,
    ) -> None:
        self.file_path = file_path
        self.missing_columns: List[str] = missing_columns or []
        self.type_errors: List[str] = type_errors or []

        parts: List[str] = [f"Ingestion failed for '{file_path}'"]
        if self.missing_columns:
            parts.append(f"missing columns: {self.missing_columns}")
        if self.type_errors:
            parts.append(f"type errors: {self.type_errors}")
        super().__init__("; ".join(parts))
