# -*- coding: utf-8 -*-
"""
Local DB backed mock source for load forecast pipeline.

It simulates the company database locally:
  1. CsvMockCompanyFeeder appends one historical business day from CSV into
     mock_company.station_observations.
  2. LocalDbMockDataSource exposes only rows that have already been appended.

The platform never reads the source CSV directly during prediction. This keeps
 the online path honest: future rows are invisible until the feeder inserts them.
"""

from __future__ import annotations

import csv
import os
# @AI_GENERATED: serialize manual mock-feed state transitions
import threading
# @AI_GENERATED: end
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import text

from services.db.adapter import DBAdapter
from services.db.datasources.base import StationDataSource, StationInfo, StationRecord
from services.db.exceptions import DataSourceError

# @AI_GENERATED: day-bounded mock-feed observability
import logging

logger = logging.getLogger(__name__)
# @AI_GENERATED: end

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


# @AI_GENERATED: day-bounded mock-feed contract
@dataclass(frozen=True)
class MockFeedResult:
    """Result metadata for exactly one source business day made available."""

    business_date: Optional[date]
    source_start_index: Optional[int]
    source_end_index: Optional[int]
    source_row_count: int
    inserted_row_count: int
    expected_points_per_day: int
    is_complete_day: bool
    exhausted: bool

    def as_dict(self) -> dict:
        """Return JSON-safe feed evidence for the manual scheduler endpoint."""
        return {
            "business_date": self.business_date.isoformat() if self.business_date else None,
            "source_start_index": self.source_start_index,
            "source_end_index": self.source_end_index,
            "source_row_count": self.source_row_count,
            "inserted_row_count": self.inserted_row_count,
            "expected_points_per_day": self.expected_points_per_day,
            "is_complete_day": self.is_complete_day,
            "exhausted": self.exhausted,
        }


@dataclass(frozen=True)
class MockFeedCursor:
    """Latest CSV row already exposed by the mock company database."""

    source_row_index: int
    timestamp_utc: datetime
    available_at: datetime


@dataclass(frozen=True)
class MockFeedPreview:
    """Read-only decision returned before a manual feed may advance data."""

    state: str
    current_business_date: Optional[date]
    current_available_at: Optional[datetime]
    next_business_date: Optional[date]
    next_source_row_count: int
    next_is_complete_day: bool
    requires_advance_confirmation: bool
    exhausted: bool

    def as_dict(self) -> dict:
        """Return JSON-safe manual-feed state for the scheduler UI."""
        return {
            "state": self.state,
            "current_business_date": (
                self.current_business_date.isoformat()
                if self.current_business_date
                else None
            ),
            "current_available_at": (
                self.current_available_at.isoformat()
                if self.current_available_at
                else None
            ),
            "next_business_date": (
                self.next_business_date.isoformat()
                if self.next_business_date
                else None
            ),
            "next_source_row_count": self.next_source_row_count,
            "next_is_complete_day": self.next_is_complete_day,
            "requires_advance_confirmation": self.requires_advance_confirmation,
            "exhausted": self.exhausted,
        }


def _resolve_path(path: str) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return _BACKEND_ROOT / p


def _parse_datetime(raw: str) -> datetime:
    value = str(raw).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
    ):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise DataSourceError(f"无法解析时间戳: {raw!r}") from exc


def _read_next_business_day_observations(
    csv_path: Path,
    station_id: str,
    timestamp_column: str,
    value_column: str,
    feature_name: str,
    after_row_index: int,
    station_id_column: Optional[str] = None,
    feature_name_column: Optional[str] = None,
) -> List[MockObservation]:
    """Read all valid rows for the first unseen calendar day without crossing it.

    Source CSV rows must be chronological. Incomplete days are returned as-is
    rather than filled or merged with the next day, so the downstream strict
    history gate can reject them with an auditable reason.
    """
    if not csv_path.exists():
        raise DataSourceError(f"mock 数据文件不存在: {csv_path}")

    observations: List[MockObservation] = []
    business_date: Optional[date] = None
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
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

        for index, row in enumerate(reader):
            if index <= after_row_index:
                continue

            timestamp = _parse_datetime(str(row[timestamp_column]))
            row_business_date = timestamp.date()
            if business_date is None:
                business_date = row_business_date
            elif row_business_date != business_date:
                break

            raw_value = row.get(value_column)
            if raw_value in (None, ""):
                continue
            try:
                value = float(raw_value)
            except ValueError:
                continue

            station_id_value = (
                str(row.get(station_id_column) or station_id)
                if station_id_column
                else station_id
            )
            feature_name_value = (
                str(row.get(feature_name_column) or feature_name)
                if feature_name_column
                else feature_name
            )
            observations.append(
                MockObservation(
                    source_row_index=index,
                    station_id=station_id_value,
                    timestamp_utc=timestamp,
                    feature_name=feature_name_value,
                    value=value,
                )
            )
    return observations
# @AI_GENERATED: end


class CsvMockCompanyFeeder:
    """Append exactly one historical CSV business day into the mock company DB."""

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
        self._expected_points_per_day = rows_per_tick
        self._schema = schema
        self._table = table
        self._last_feed_result: Optional[MockFeedResult] = None
        self._feed_lock = threading.RLock()

    @property
    def station_id(self) -> str:
        return self._station_id

    @property
    def feature_name(self) -> str:
        return self._feature_name

    # @AI_GENERATED: day-bounded mock-feed result access
    @property
    def last_feed_result(self) -> Optional[MockFeedResult]:
        """Expose the latest feeder outcome without advancing the source cursor."""
        return self._last_feed_result
    # @AI_GENERATED: end

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

    # @AI_GENERATED: manual mock-feed confirmation contract
    def _last_feed_cursor(self) -> Optional[MockFeedCursor]:
        """Read the latest exposed source row without modifying company data."""
        self.ensure_tables()
        with self._adapter.get_sync_session() as session:
            row = session.execute(
                text(
                    f"""
                    SELECT source_row_index, timestamp_utc, available_at
                    FROM `{self._schema}`.`{self._table}`
                    ORDER BY source_row_index DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()
        if row is None:
            return None
        return MockFeedCursor(
            source_row_index=int(row["source_row_index"]),
            timestamp_utc=row["timestamp_utc"],
            available_at=row["available_at"],
        )

    def _is_complete_business_day(self, observations: List[MockObservation]) -> bool:
        expected_minutes = {
            slot * (24 * 60 // self._expected_points_per_day)
            for slot in range(self._expected_points_per_day)
        }
        observed_minutes = {
            observation.timestamp_utc.hour * 60 + observation.timestamp_utc.minute
            for observation in observations
            if observation.timestamp_utc.second == 0
            and observation.timestamp_utc.microsecond == 0
        }
        return observed_minutes == expected_minutes

    def _manual_feed_preview_locked(self) -> MockFeedPreview:
        cursor = self._last_feed_cursor()
        next_observations = _read_next_business_day_observations(
            self._csv_path,
            station_id=self._station_id,
            timestamp_column=self._timestamp_column,
            value_column=self._value_column,
            feature_name=self._feature_name,
            after_row_index=cursor.source_row_index if cursor else -1,
            station_id_column=self._station_id_column,
            feature_name_column=self._feature_name_column,
        )
        if not next_observations:
            return MockFeedPreview(
                state="exhausted",
                current_business_date=cursor.timestamp_utc.date() if cursor else None,
                current_available_at=cursor.available_at if cursor else None,
                next_business_date=None,
                next_source_row_count=0,
                next_is_complete_day=False,
                requires_advance_confirmation=False,
                exhausted=True,
            )

        next_business_date = next_observations[0].timestamp_utc.date()
        current_business_date = cursor.timestamp_utc.date() if cursor else None
        continues_legacy_day = current_business_date == next_business_date
        return MockFeedPreview(
            state=(
                "initial_feed"
                if cursor is None
                else "continue_current_business_day"
                if continues_legacy_day
                else "confirmation_required"
            ),
            current_business_date=current_business_date,
            current_available_at=cursor.available_at if cursor else None,
            next_business_date=next_business_date,
            next_source_row_count=len(next_observations),
            next_is_complete_day=self._is_complete_business_day(next_observations),
            requires_advance_confirmation=cursor is not None and not continues_legacy_day,
            exhausted=False,
        )

    def get_manual_feed_preview(self) -> MockFeedPreview:
        """Return the manual-feed decision without exposing a newer business day."""
        with self._feed_lock:
            return self._manual_feed_preview_locked()

    def feed_manually(self, advance: bool = False) -> tuple[MockFeedPreview, Optional[MockFeedResult]]:
        """Feed only after an explicit advance confirmation for a completed day."""
        with self._feed_lock:
            preview = self._manual_feed_preview_locked()
            if preview.exhausted or (
                preview.requires_advance_confirmation and not advance
            ):
                return preview, None
            self._feed_next_batch_locked()
            return self._manual_feed_preview_locked(), self._last_feed_result
    # @AI_GENERATED: end

    # @AI_GENERATED: strict calendar-day replay
    def feed_next_batch(self) -> int:
        """Advance the CSV source for scheduler-driven feeds under the shared lock."""
        with self._feed_lock:
            return self._feed_next_batch_locked()

    def _feed_next_batch_locked(self) -> int:
        """Make one next calendar day available; never blend it with the following day.

        The integer return type remains compatible with the existing scheduler
        registration. Detailed facts are exposed by ``last_feed_result`` and
        emitted to the application log. Incomplete days are inserted unchanged
        so downstream history validation, rather than this feeder, decides
        whether a prediction can be produced.
        """
        last_index = self._last_source_row_index()
        observations = _read_next_business_day_observations(
            self._csv_path,
            station_id=self._station_id,
            timestamp_column=self._timestamp_column,
            value_column=self._value_column,
            feature_name=self._feature_name,
            after_row_index=last_index,
            station_id_column=self._station_id_column,
            feature_name_column=self._feature_name_column,
        )
        if not observations:
            self._last_feed_result = MockFeedResult(
                business_date=None,
                source_start_index=None,
                source_end_index=None,
                source_row_count=0,
                inserted_row_count=0,
                expected_points_per_day=self._expected_points_per_day,
                is_complete_day=False,
                exhausted=True,
            )
            logger.info("mock_data_feed: source exhausted after source_row_index=%d", last_index)
            return 0

        business_date = observations[0].timestamp_utc.date()
        is_complete_day = self._is_complete_business_day(observations)

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
                        "source_row_index": observation.source_row_index,
                        "station_id": observation.station_id,
                        "timestamp_utc": observation.timestamp_utc,
                        "feature_name": observation.feature_name,
                        "value": observation.value,
                        "available_at": now,
                    }
                    for observation in observations
                ],
            )
            inserted_row_count = int(result.rowcount or 0)

        self._last_feed_result = MockFeedResult(
            business_date=business_date,
            source_start_index=observations[0].source_row_index,
            source_end_index=observations[-1].source_row_index,
            source_row_count=len(observations),
            inserted_row_count=inserted_row_count,
            expected_points_per_day=self._expected_points_per_day,
            is_complete_day=is_complete_day,
            exhausted=False,
        )
        logger.info(
            "mock_data_feed: business_date=%s source_rows=%d inserted_rows=%d "
            "expected_points=%d complete=%s source_index=%d~%d",
            business_date.isoformat(),
            len(observations),
            inserted_row_count,
            self._expected_points_per_day,
            is_complete_day,
            observations[0].source_row_index,
            observations[-1].source_row_index,
        )
        return inserted_row_count
    # @AI_GENERATED: end


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
    expected_points_per_day = int(os.environ.get("MOCK_COMPANY_ROWS_PER_TICK", "96"))
    csv_path = os.environ.get("MOCK_COMPANY_CSV_PATH", "datasets/load_true_weihai_260415.csv")
    return CsvMockCompanyFeeder(
        adapter=adapter,
        csv_path=csv_path,
        rows_per_tick=expected_points_per_day,
    )
