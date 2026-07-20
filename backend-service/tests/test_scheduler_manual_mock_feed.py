# @AI_GENERATED: manual mock-feed scheduler API guard
import asyncio

import pytest
from fastapi import HTTPException

from api.scheduler import trigger_task_now


def test_generic_trigger_rejects_mock_data_feed_without_confirmation():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(trigger_task_now("mock_data_feed"))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["code"] == "manual_mock_feed_confirmation_required"
# @AI_GENERATED: end

# @AI_GENERATED: lf_data_pull platform evidence API test
def test_data_pull_evidence_reads_platform_snapshot_without_running_task():
    from datetime import datetime
    from types import SimpleNamespace

    import api.scheduler as scheduler_api

    class StubRepository:
        def __init__(self) -> None:
            self.received_slot = None
            self.received_limit = None

        def get_station_data_evidence(self, slot, sample_limit):
            self.received_slot = slot
            self.received_limit = sample_limit
            row = {
                "station_id": "station-a",
                "timestamp_utc": datetime(2025, 1, 2, 0, 15),
                "feature_name": "load",
                "value": 42.5,
                "ingested_at": datetime(2025, 1, 2, 0, 16),
            }
            return {
                "slot": slot,
                "total_rows": 1,
                "station_count": 1,
                "feature_names": ["load"],
                "time_start": row["timestamp_utc"],
                "time_end": row["timestamp_utc"],
                "latest": row,
                "samples": [row],
            }

    repository = StubRepository()
    original_store = scheduler_api._scheduler_store
    original_repository = scheduler_api._load_forecast_repository
    scheduler_api._scheduler_store = SimpleNamespace(
        get_task=lambda task_id: SimpleNamespace(task_id=task_id, slot="load_forecast")
    )
    scheduler_api.set_load_forecast_repository(repository)
    try:
        response = asyncio.run(scheduler_api.get_task_data_evidence("lf_data_pull", 999))
    finally:
        scheduler_api._scheduler_store = original_store
        scheduler_api._load_forecast_repository = original_repository

    assert repository.received_slot == "load_forecast"
    assert repository.received_limit == 200
    assert response["evidence"]["time_start"] == "2025-01-02T00:15:00"
    assert response["evidence"]["latest"]["value"] == 42.5
    assert response["evidence"]["samples"][0]["ingested_at"] == "2025-01-02T00:16:00"
# @AI_GENERATED: end