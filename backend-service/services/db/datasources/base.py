"""
services/db/datasources/base.py — 站点数据源抽象接口

定义 StationRecord（单条站点观测值）、StationInfo（站点元信息）和
StationDataSource（ABC），供本地 mock 数据源与真实 DB 数据源共同继承。

Requirements: 8.1, 8.5
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List

from services.db.exceptions import DataSourceError, DataSourceTimeoutError  # noqa: F401


@dataclass
class StationRecord:
    """单条站点观测记录。

    Attributes:
        station_id:   站点唯一标识（字符串）
        timestamp:    观测时刻（datetime，UTC）
        feature_name: 特征名称（如 'load'、'temperature'）
        value:        特征数值（float）
    """

    station_id: str
    timestamp: datetime
    feature_name: str
    value: float


@dataclass
class StationInfo:
    """站点元信息。

    Attributes:
        station_id:   站点唯一标识
        station_name: 站点显示名称
    """

    station_id: str
    station_name: str


class StationDataSource(ABC):
    """站点数据源抽象基类（ABC）。

    所有具体数据源（本地 CSV/Parquet mock、关系型数据库等）均继承此类，
    实现 pull_latest 和 get_available_stations 两个方法。

    异常约定（需求 8.5）：
      - 底层异常统一封装为 DataSourceError，不透传驱动异常。
      - 查询耗时超过 30s 时抛出 DataSourceTimeoutError（继承自 DataSourceError）。
    """

    @abstractmethod
    def pull_latest(
        self,
        station_id: str,
        since_timestamp: datetime,
    ) -> List[StationRecord]:
        """拉取指定站点在 since_timestamp 之后的最新记录。

        Args:
            station_id:       目标站点 ID。
            since_timestamp:  时间下界（UTC），只返回严格晚于此时刻的记录。

        Returns:
            按时间升序排列的 StationRecord 列表；无新记录时返回空列表。

        Raises:
            DataSourceTimeoutError: 查询耗时超过 30 秒。
            DataSourceError:        其他数据源错误。
        """

    @abstractmethod
    def get_available_stations(self) -> List[StationInfo]:
        """返回当前数据源中所有可用站点的元信息列表。

        Returns:
            StationInfo 列表；数据源为空时返回空列表。

        Raises:
            DataSourceError: 数据源访问失败。
        """
