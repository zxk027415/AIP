"""
services/db/datasources/local_mock.py — 本地 CSV/Parquet mock 数据源

从本地文件（CSV 或 Parquet）读取站点观测数据，实现 StationDataSource ABC。
文件列约定：station_id, timestamp, feature_name, value

Requirements: 8.2
"""

from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import List

import pandas as pd

from services.db.datasources.base import StationDataSource, StationInfo, StationRecord
from services.db.exceptions import DataSourceError, DataSourceTimeoutError

# 项目根目录（backend-service/ 的父目录）
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_BACKEND_ROOT = os.path.dirname(os.path.abspath(__file__))
for _ in range(3):
    _BACKEND_ROOT = os.path.dirname(_BACKEND_ROOT)

_REQUIRED_COLUMNS = {"station_id", "timestamp", "feature_name", "value"}
_TIMEOUT_SECONDS = 30


def _resolve_path(data_path: str) -> str:
    """将相对路径解析为绝对路径。优先相对项目根目录，其次 backend-service 目录。"""
    if os.path.isabs(data_path):
        return data_path
    # 相对于项目根目录
    candidate = os.path.join(_PROJECT_ROOT, data_path)
    if os.path.exists(candidate):
        return candidate
    # 相对于 backend-service 目录
    candidate2 = os.path.join(_BACKEND_ROOT, data_path)
    if os.path.exists(candidate2):
        return candidate2
    # 返回项目根下的路径，让后续统一抛错
    return candidate


def _load_file(abs_path: str) -> pd.DataFrame:
    """读取 CSV 或 Parquet 文件，校验列，返回 DataFrame。"""
    if not os.path.exists(abs_path):
        raise DataSourceError(f"文件不存在: {abs_path}")

    ext = os.path.splitext(abs_path)[1].lower()
    try:
        if ext == ".parquet":
            df = pd.read_parquet(abs_path)
        elif ext == ".csv":
            df = pd.read_csv(abs_path)
        else:
            raise DataSourceError(f"不支持的文件格式: {ext}，仅支持 .csv 和 .parquet")
    except DataSourceError:
        raise
    except Exception as e:
        raise DataSourceError(f"文件解析失败 ({abs_path}): {e}") from e

    missing = _REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise DataSourceError(f"文件缺少必需列 {sorted(missing)}: {abs_path}")

    # 统一 timestamp 列为 datetime
    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        # 转为 tz-aware datetime（UTC），便于与 since_timestamp 比较
    except Exception as e:
        raise DataSourceError(f"timestamp 列解析失败: {e}") from e

    return df


class LocalMockDataSource(StationDataSource):
    """从本地 CSV 或 Parquet 文件读取站点数据的 mock 数据源。

    Args:
        data_path: 数据文件路径，相对于项目根目录（或绝对路径）。
                   支持 .csv 和 .parquet，文件需包含列：
                   station_id, timestamp, feature_name, value
    """

    def __init__(self, data_path: str) -> None:
        self._data_path = data_path

    def _load_with_timeout(self) -> pd.DataFrame:
        """带 30s 超时的文件加载。"""
        abs_path = _resolve_path(self._data_path)
        result: List = []
        error: List = []

        def _task():
            try:
                result.append(_load_file(abs_path))
            except Exception as e:
                error.append(e)

        t = threading.Thread(target=_task, daemon=True)
        t.start()
        t.join(timeout=_TIMEOUT_SECONDS)

        if t.is_alive():
            raise DataSourceTimeoutError(
                f"读取文件超时（>{_TIMEOUT_SECONDS}s）: {self._data_path}"
            )
        if error:
            raise error[0]
        return result[0]

    def pull_latest(
        self,
        station_id: str,
        since_timestamp: datetime,
    ) -> List[StationRecord]:
        """返回指定站点在 since_timestamp 之后的记录，按 timestamp 升序。

        Args:
            station_id:      目标站点 ID。
            since_timestamp: 时间下界（strict gt）。

        Returns:
            StationRecord 列表，无新记录时返回 []。

        Raises:
            DataSourceTimeoutError: 读取超时（>30s）。
            DataSourceError:        文件不存在、解析失败等。
        """
        try:
            df = self._load_with_timeout()
        except (DataSourceError, DataSourceTimeoutError):
            raise
        except Exception as e:
            raise DataSourceError(f"pull_latest 失败: {e}") from e

        # 统一 since_timestamp 为 tz-aware（UTC）
        if since_timestamp.tzinfo is None:
            since_ts = pd.Timestamp(since_timestamp, tz="UTC")
        else:
            since_ts = pd.Timestamp(since_timestamp).tz_convert("UTC")

        mask = (df["station_id"] == station_id) & (df["timestamp"] > since_ts)
        subset = df[mask].sort_values("timestamp")

        records: List[StationRecord] = []
        for row in subset.itertuples(index=False):
            records.append(
                StationRecord(
                    station_id=str(row.station_id),
                    timestamp=row.timestamp.to_pydatetime(),
                    feature_name=str(row.feature_name),
                    value=float(row.value),
                )
            )
        return records

    def get_available_stations(self) -> List[StationInfo]:
        """返回文件中所有唯一 station_id 对应的 StationInfo 列表。

        Returns:
            StationInfo 列表；文件为空时返回 []。

        Raises:
            DataSourceTimeoutError: 读取超时（>30s）。
            DataSourceError:        文件不存在、解析失败等。
        """
        try:
            df = self._load_with_timeout()
        except (DataSourceError, DataSourceTimeoutError):
            raise
        except Exception as e:
            raise DataSourceError(f"get_available_stations 失败: {e}") from e

        station_ids = df["station_id"].dropna().unique()
        return [
            StationInfo(station_id=str(sid), station_name=str(sid))
            for sid in sorted(station_ids)
        ]
