from datetime import datetime
from types import SimpleNamespace

from services.db.datasources.local_db_mock import _read_next_business_day_observations
from services.scheduler.tasks.load_forecast_tasks import _build_naive_forecast_point


def test_naive_forecast_uses_only_latest_observed_point():
    rows = [
        SimpleNamespace(timestamp_utc=datetime(2025, 1, 1, 0, 0), value=10.0),
        SimpleNamespace(timestamp_utc=datetime(2025, 1, 1, 0, 15), value=12.0),
    ]

    forecast_ts, predicted_value = _build_naive_forecast_point(rows)

    assert forecast_ts == datetime(2025, 1, 1, 0, 30)
    assert predicted_value == 12.0


def test_naive_forecast_requires_two_distinct_timestamps():
    rows = [
        SimpleNamespace(timestamp_utc=datetime(2025, 1, 1, 0, 0), value=10.0),
        SimpleNamespace(timestamp_utc=datetime(2025, 1, 1, 0, 0), value=12.0),
    ]

    assert _build_naive_forecast_point(rows) is None


# @AI_GENERATED: day-bounded CSV mock feeder tests
def test_csv_mock_feeder_reads_only_the_current_business_day(tmp_path):
    csv_path = tmp_path / "mock.csv"
    csv_path.write_text(
        "\n".join(
            [
                "id,record_time,parent_id,child_id,feature_name,value,create_time",
                "1,2025-01-01 00:00:00,park_01,yARGkDuq,load,10,2025-01-02 00:00:00",
                "2,2025-01-01 00:15:00,park_01,yARGkDuq,load,11,2025-01-02 00:00:00",
                "3,2025-01-01 00:30:00,park_01,yARGkDuq,load,12,2025-01-02 00:00:00",
                "4,2025-01-02 00:00:00,park_01,yARGkDuq,load,13,2025-01-03 00:00:00",
                "5,2025-01-02 00:15:00,park_01,yARGkDuq,load,14,2025-01-03 00:00:00",
            ]
        ),
        encoding="utf-8",
    )

    first_day = _read_next_business_day_observations(
        csv_path,
        station_id="fallback_station",
        timestamp_column="record_time",
        value_column="value",
        feature_name="load",
        after_row_index=-1,
        station_id_column="child_id",
        feature_name_column="feature_name",
    )
    second_day = _read_next_business_day_observations(
        csv_path,
        station_id="fallback_station",
        timestamp_column="record_time",
        value_column="value",
        feature_name="load",
        after_row_index=first_day[-1].source_row_index,
        station_id_column="child_id",
        feature_name_column="feature_name",
    )

    assert [row.source_row_index for row in first_day] == [0, 1, 2]
    assert {row.timestamp_utc.date() for row in first_day} == {datetime(2025, 1, 1).date()}
    assert [row.source_row_index for row in second_day] == [3, 4]
    assert {row.timestamp_utc.date() for row in second_day} == {datetime(2025, 1, 2).date()}
    assert first_day[0].station_id == "yARGkDuq"
    assert first_day[0].feature_name == "load"
# @AI_GENERATED: end

# @AI_GENERATED: manual mock-feed confirmation guard tests
def test_manual_feed_requires_explicit_advance_after_current_business_day():
    from threading import RLock

    from services.db.datasources.local_db_mock import MockFeedPreview, MockFeedResult, CsvMockCompanyFeeder

    class StubManualFeed(CsvMockCompanyFeeder):
        def __init__(self) -> None:
            self._feed_lock = RLock()
            self._last_feed_result = None
            self.write_calls = 0
            self.preview = MockFeedPreview(
                state="confirmation_required",
                current_business_date=datetime(2025, 1, 1).date(),
                current_available_at=datetime(2025, 1, 1, 23, 45),
                next_business_date=datetime(2025, 1, 2).date(),
                next_source_row_count=96,
                next_is_complete_day=True,
                requires_advance_confirmation=True,
                exhausted=False,
            )

        def _manual_feed_preview_locked(self):
            return self.preview

        def _feed_next_batch_locked(self) -> int:
            self.write_calls += 1
            self._last_feed_result = MockFeedResult(
                business_date=datetime(2025, 1, 2).date(),
                source_start_index=96,
                source_end_index=191,
                source_row_count=96,
                inserted_row_count=96,
                expected_points_per_day=96,
                is_complete_day=True,
                exhausted=False,
            )
            return 96

    feeder = StubManualFeed()

    preview, result = feeder.feed_manually(advance=False)

    assert preview.requires_advance_confirmation is True
    assert result is None
    assert feeder.write_calls == 0

    _, result = feeder.feed_manually(advance=True)

    assert result is not None
    assert result.inserted_row_count == 96
    assert feeder.write_calls == 1
# @AI_GENERATED: end