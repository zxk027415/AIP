"""
services/db/datasources — 站点数据源抽象层

导出核心抽象接口和数据类，供具体实现（本地 mock、真实数据库等）继承。
"""

from services.db.datasources.base import (
    StationDataSource,
    StationInfo,
    StationRecord,
)
from services.db.exceptions import DataSourceError, DataSourceTimeoutError

__all__ = [
    "StationDataSource",
    "StationInfo",
    "StationRecord",
    "DataSourceError",
    "DataSourceTimeoutError",
]
