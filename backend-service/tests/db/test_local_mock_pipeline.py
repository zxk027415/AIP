from datetime import datetime
from types import SimpleNamespace

from services.db.datasources.local_db_mock import _read_csv_observations
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


def test_csv_mock_feeder_reads_only_next_unseen_slice(tmp_path):
    csv_path = tmp_path / "mock.csv"
    csv_path.write_text(
        "\n".join(
            [
                "id,record_time,parent_id,child_id,feature_name,value,create_time",
                "1,2025-01-01 00:00:00,park_01,yARGkDuq,load,10,2025-01-02 00:00:00",
                "2,2025-01-01 00:15:00,park_01,yARGkDuq,load,11,2025-01-02 00:00:00",
                "3,2025-01-01 00:30:00,park_01,yARGkDuq,load,12,2025-01-02 00:00:00",
            ]
        ),
        encoding="utf-8",
    )

    rows = _read_csv_observations(
        csv_path,
        station_id="fallback_station",
        timestamp_column="record_time",
        value_column="value",
        feature_name="load",
        after_row_index=0,
        limit=1,
        station_id_column="child_id",
        feature_name_column="feature_name",
    )

    assert len(rows) == 1
    assert rows[0].source_row_index == 1
    assert rows[0].station_id == "yARGkDuq"
    assert rows[0].feature_name == "load"
    assert rows[0].timestamp_utc == datetime(2025, 1, 1, 0, 15)
    assert rows[0].value == 11.0
