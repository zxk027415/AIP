# -*- coding: utf-8 -*-
"""
Local DB backed mock source for load forecast pipeline.

It simulates the company database locally:
  1. CsvMockCompanyFeeder appends the next slice of historical CSV rows into
     mock_company.station_observations.
  2. LocalDbMockDataSource exposes only rows that have already been appended.

The platform never reads the source CSV directly during prediction. This keeps
the online path honest: future rows are invisible until the feeder inserts them.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text

from services.db.adapter import DBAdapter
from services.db.datasources.base import StationDataSource, StationInfo, StationRecord
from services.db.exceptions import DataSourceError

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_SCHEMA = "aip_algo_platform"
_DEFAULT_TABLE = "station_observations"
_DEFAULT_STATION_ID = "yARGkDuq"
_DEFAULT_FEATURE_NAME = "load"


@dataclass(frozen=True)
class MockObservation:
    source_row_index: int
    station_id: str
    timestamp_utc: datetime
    feature_name: str
    value: float


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return _BACKEND_ROOT / p


def _parse_datetime(raw: str) -> datetime:
    value = str(raw).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise DataSourceError(f"无法解析时间戳: {raw!r}") from exc


def _read_csv_observations(
    csv_path: Path,
    station_id: str,
    timestamp_column: str,
    value_column: str,
    feature_name: str,
    after_row_index: int,
    limit: int,
    station_id_column: Optional[str] = None,
    feature_name_column: Optional[str] = None,
) -> List[MockObservation]:
    if not csv_path.exists():
        raise DataSourceError(f"mock 数据文件不存在: {csv_path}")
    if limit <= 0:
        return []

    rows: List[MockObservation] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise DataSourceError(f"mock 数据文件为空: {csv_path}")
        required = {timestamp_column, value_column}
        if station_id_column is not None:
            required.add(station_id_column)
        if feature_name_column is not None:
            required.add(feature_name_column)
        missing = required - set(reader.fieldnames)
        if missing:
            raise DataSourceError(f"mock 数据文件缺少列 {sorted(missing)}: {csv_path}")

        for idx, row in enumerate(reader):
            if idx <= after_row_index:
                continue
            raw_value = row.get(value_column)
            if raw_value in (None, ""):
                continue
            try:
                value = float(raw_value)
            except ValueError:
                continue
            station_id_value = str(row.get(station_id_column) or station_id) if station_id_column else station_id
            feature_name_value = str(row.get(feature_name_column) or feature_name) if feature_name_column else feature_name
            rows.append(
                MockObservation(
                    source_row_index=idx,
                    station_id=station_id_value,
                    timestamp_utc=_parse_datetime(str(row[timestamp_column])),
                    feature_name=feature_name_value,
                    value=value,
                )
            )
            if len(rows) >= limit:
                break
    return rows


class CsvMockCompanyFeeder:
    """Append historical CSV rows into a local MySQL table in small slices."""

    def __init__(
        self,
        adapter: DBAdapter,
        csv_path: str,
        station_id: str = _DEFAULT_STATION_ID,
        timestamp_column: str = "record_time",
        value_column: str = "value",
        feature_name: str = _DEFAULT_FEATURE_NAME,
        station_id_column: Optional[str] = "child_id",
        feature_name_column: Optional[str] = "feature_name",
        rows_per_tick: int = 96,
        schema: str = _DEFAULT_SCHEMA,
        table: str = _DEFAULT_TABLE,
    ) -> None:
        self._adapter = adapter
        self._csv_path = _resolve_path(csv_path)
        self._station_id = station_id
        self._timestamp_column = timestamp_column
        self._value_column = value_column
        self._feature_name = feature_name
        self._station_id_column = station_id_column
        self._feature_name_column = feature_name_column
        self._rows_per_tick = rows_per_tick
        self._schema = schema
        self._table = table

    @property
    def station_id(self) -> str:
        return self._station_id

    @property
    def feature_name(self) -> str:
        return self._feature_name

    def ensure_tables(self) -> None:
        with self._adapter.get_sync_session() as session:
            session.execute(text(f"CREATE DATABASE IF NOT EXISTS `{self._schema}` DEFAULT CHARSET utf8mb4"))
            session.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS `{self._schema}`.`{self._table}` (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        source_row_index BIGINT NOT NULL,
                        station_id VARCHAR(128) NOT NULL,
                        timestamp_utc DATETIME NOT NULL,
                        feature_name VARCHAR(128) NOT NULL,
                        value DOUBLE NOT NULL,
                        available_at DATETIME NOT NULL,
                        UNIQUE KEY uq_mock_station_time_feature (station_id, timestamp_utc, feature_name),
                        KEY ix_mock_source_row (source_row_index),
                        KEY ix_mock_station_time (station_id, timestamp_utc)
                    )
                    """
                )
            )

    def _last_source_row_index(self) -> int:
        self.ensure_tables()
        with self._adapter.get_sync_session() as session:
            result = session.execute(
                text(f"SELECT COALESCE(MAX(source_row_index), -1) FROM `{self._schema}`.`{self._table}`")
            ).scalar()
        return int(result if result is not None else -1)

    def feed_next_batch(self) -> int:
        """Insert the next unseen CSV slice. Returns number of inserted rows."""
        last_idx = self._last_source_row_index()
        observations = _read_csv_observations(
            self._csv_path,
            station_id=self._station_id,
            timestamp_column=self._timestamp_column,
            value_column=self._value_column,
            feature_name=self._feature_name,
            after_row_index=last_idx,
            limit=self._rows_per_tick,
            station_id_column=self._station_id_column,
            feature_name_column=self._feature_name_column,
        )
        if not observations:
            return 0

        now = datetime.utcnow()
        with self._adapter.get_sync_session() as session:
            result = session.execute(
                text(
                    f"""
                    INSERT IGNORE INTO `{self._schema}`.`{self._table}`
                        (source_row_index, station_id, timestamp_utc, feature_name, value, available_at)
                    VALUES
                        (:source_row_index, :station_id, :timestamp_utc, :feature_name, :value, :available_at)
                    """
                ),
                [
                    {
                        "source_row_index": obs.source_row_index,
                        "station_id": obs.station_id,
                        "timestamp_utc": obs.timestamp_utc,
                        "feature_name": obs.feature_name,
                        "value": obs.value,
                        "available_at": now,
                    }
                    for obs in observations
                ],
            )
            return int(result.rowcount or 0)


class LocalDbMockDataSource(StationDataSource):
    """StationDataSource implementation backed by the local mock company DB."""

    def __init__(
        self,
        adapter: DBAdapter,
        schema: str = _DEFAULT_SCHEMA,
        table: str = _DEFAULT_TABLE,
    ) -> None:
        self._adapter = adapter
        self._schema = schema
        self._table = table

    def pull_latest(self, station_id: str, since_timestamp: datetime) -> List[StationRecord]:
        try:
            with self._adapter.get_sync_session() as session:
                rows = session.execute(
                    text(
                        f"""
                        SELECT station_id, timestamp_utc, feature_name, value
                        FROM `{self._schema}`.`{self._table}`
                        WHERE station_id = :station_id
                          AND timestamp_utc > :since_timestamp
                        ORDER BY timestamp_utc ASC
                        """
                    ),
                    {"station_id": station_id, "since_timestamp": since_timestamp},
                ).mappings().all()
        except Exception as exc:  # noqa: BLE001
            raise DataSourceError(f"LocalDbMockDataSource.pull_latest 失败: {exc}") from exc

        return [
            StationRecord(
                station_id=str(row["station_id"]),
                timestamp=row["timestamp_utc"],
                feature_name=str(row["feature_name"]),
                value=float(row["value"]),
            )
            for row in rows
        ]

    def get_available_stations(self) -> List[StationInfo]:
        try:
            with self._adapter.get_sync_session() as session:
                rows = session.execute(
                    text(
                        f"""
                        SELECT DISTINCT station_id
                        FROM `{self._schema}`.`{self._table}`
                        ORDER BY station_id ASC
                        """
                    )
                ).scalars().all()
        except Exception as exc:  # noqa: BLE001
            raise DataSourceError(f"LocalDbMockDataSource.get_available_stations 失败: {exc}") from exc

        return [StationInfo(station_id=str(station_id), station_name=str(station_id)) for station_id in rows]


def build_default_mock_feeder(adapter: DBAdapter) -> CsvMockCompanyFeeder:
    rows_per_tick = int(os.environ.get("MOCK_COMPANY_ROWS_PER_TICK", "96"))
    csv_path = os.environ.get("MOCK_COMPANY_CSV_PATH", "datasets/load_true_weihai_260415.csv")
    return CsvMockCompanyFeeder(adapter=adapter, csv_path=csv_path, rows_per_tick=rows_per_tick)
