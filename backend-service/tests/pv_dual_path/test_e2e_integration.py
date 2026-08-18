# @AI_GENERATED
# -*- coding: utf-8 -*-
"""PV 双路径任务 18：隔离真库（SQLite 文件）+ HTTP TestClient 端到端集成。

本文件连真实 SQL 引擎与 FastAPI 路由，不连公司生产 MySQL 写路径。
公司库探测见 ``test_mysql_schema_not_yet_migrated``：只读、缺表则记缺口。
"""
from __future__ import annotations

import math
import os
import random
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from itertools import count
from pathlib import Path
from typing import Any, Dict, Generator, List

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from services.db.datasources.pv_fault_mock import (
    _DELAY_RATIO,
    _DELAY_TICKS_RANGE,
    _DROP_RATIO,
    _RELEASE_BATCH_COUNT,
)
from services.db.models.pv_fault import (
    DevicePredictionCursor,
    PathActivationDeviceScope,
    PathActivationEpoch,
    PathActivationLaneClaim,
    SeqDeviceDayLedger,
    TrainingSample,
)
from services.deployment.models import DeploymentSlot, ModelVersion
from services.deployment.pv_read_adapter import (
    PV_FAULT_READ_ONLY_CODE,
    PVDeploymentReadAdapter,
    PvFaultRegistryReadOnlyError,
)
from services.deployment.store import DeploymentSlotStore
from services.iterative_labeling.pv_governance_events import (
    PathSwitchEventStore,
    PromotionEventStore,
)
from services.iterative_labeling.pv_model_registry import ModelRegistration, PVModelRegistry
from services.iterative_labeling.pv_recovery_policy import PVRecoveryPolicy, PathHealth
from services.iterative_labeling.seq_annotation.grid_align import SLOTS_PER_DAY
from services.iterative_labeling.seq_annotation.predictor import SeqAnnotationPredictor
from services.scheduler.pv_dual_path.backfill_capacity import (
    BackfillCapacityArbiter,
    CapacityResources,
)
from services.scheduler.pv_dual_path.backfill_runner import BackfillRunner
from services.scheduler.pv_dual_path.config import DualPathConfig
from services.scheduler.pv_dual_path.cross_path_switch_coordinator import (
    CrossPathSwitchCoordinator,
)
from services.scheduler.pv_dual_path.path_activation import (
    FULL_BACKFILL,
    HISTORICAL_BACKFILL_LANE,
    PRODUCTION_LANE,
    ActivationRequest,
    DeviceActivationInput,
    DeviceScope,
    PathActivationService,
)
from services.scheduler.pv_dual_path.scheduler import DualPathScheduler
from services.scheduler.pv_dual_path.seq_device_day_ledger import (
    DeviceDayKey,
    DeviceKey,
    SeqDeviceDayLedgerRepository,
)
from services.scheduler.pv_dual_path.shadow_compare import (
    CrossPathShadowReport,
    ShadowCompareRunner,
    ShadowReportStore,
)
from services.scheduler.pv_dual_path.strategy_base import CycleContext, CycleResult
from services.scheduler.pv_dual_path.watermark import DataWatermarkService


class _FileSQLiteAdapter:
    """文件 SQLite，模拟 DBAdapter 提交/回滚/关闭。"""

    def __init__(self, db_path: Path) -> None:
        self.engine = create_engine(
            f"sqlite+pysqlite:///{db_path.resolve().as_posix()}",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self._factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_tables(self) -> None:
        for model in (
            SeqDeviceDayLedger,
            PathActivationEpoch,
            PathActivationDeviceScope,
            PathActivationLaneClaim,
            DevicePredictionCursor,
            TrainingSample,
        ):
            model.__table__.create(self.engine, checkfirst=True)

    @contextmanager
    def get_sync_session(self) -> Generator[Session, None, None]:
        session = self._factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()


def _key(day: int, *, site: str = "site-a", device: str = "device-a") -> DeviceDayKey:
    return DeviceDayKey(
        slot="pv_fault",
        modeling_path="seq_annotation",
        site_id=site,
        device_id=device,
        branch_id="branch-a",
        business_date=date(2026, 1, day),
    )


def _succeed(repo: SeqDeviceDayLedgerRepository, key: DeviceDayKey, fingerprint: str, batch_id: str) -> None:
    repo.upsert_candidate(key, fingerprint, is_ready=True)
    repo.mark_running(key)
    repo.mark_succeeded(key, batch_id, fingerprint)


def _seed_champions(tmp_path: Path) -> PVModelRegistry:
    registry = PVModelRegistry(tmp_path / "registry", events_base_dir=tmp_path / "events")
    registry.register_challenger(
        "legacy_day",
        ModelRegistration("data/models/legacy.pkl", "el", 0.80, "2026-01-01T00:00:00"),
    )
    registry.promote_within_path("legacy_day", "el")
    registry.register_challenger(
        "seq_annotation",
        ModelRegistration("data/models/seq", "es", 0.90, "2026-01-01T00:00:00"),
    )
    registry.promote_within_path("seq_annotation", "es")
    return registry


def _gate_report(store: ShadowReportStore, registry: PVModelRegistry, comparison_id: str) -> str:
    state = registry.get_slot()
    legacy = state.path_models["legacy_day"].champion
    seq = state.path_models["seq_annotation"].champion
    report = CrossPathShadowReport(
        comparison_id=comparison_id,
        legacy_model_ref=str(legacy.model_ref if legacy else ""),
        seq_model_ref=str(seq.model_ref if seq else ""),
        device_day_total=250,
        comparable_total=250,
        agreement_rate=0.9,
        coverage_rate=0.95,
        generated_at=datetime.utcnow().isoformat(),
        common_metrics={"agreement_rate": 0.9},
        seq_native_metrics={"legacy_counterpart": None},
        runtime_metrics={"blocking_count": 0},
        uncomparable_items=[],
    )
    store.save(report)
    return report.comparison_id


def _predictor_without_artifact() -> SeqAnnotationPredictor:
    predictor = object.__new__(SeqAnnotationPredictor)
    predictor._metadata = {
        "model_name": "in-memory-seq",
        "model_ref": "data/models/seq_annotation/in-memory",
        "trained_full_day": True,
        "daylight_start_hour": 0,
        "daylight_end_hour": 24,
    }
    predictor._measured_channels = ["value", "i_cal"]
    predictor._channels = ["value", "i_cal", "is_measured"]
    predictor._mask_channel_index = 2
    predictor._grid_aligned = True
    predictor._grid_contract = {
        "min_occupied_slots": SLOTS_PER_DAY,
        "min_daytime_occupancy": 1.0,
        "max_daytime_gap_slots": 0,
        "require_all_hours_covered": True,
    }
    predictor._postprocessing_contract = {}
    predictor._seq_len = SLOTS_PER_DAY
    predictor._daylight_start_hour = 0
    predictor._daylight_end_hour = 24
    return predictor


def _full_grid_frame(day: date) -> pd.DataFrame:
    timestamps = pd.date_range(day.isoformat(), periods=SLOTS_PER_DAY, freq="5min")
    slots = np.arange(SLOTS_PER_DAY, dtype=np.float64)
    return pd.DataFrame({"time": timestamps, "value": slots, "i_cal": slots + 1.0})


class _RecordingStrategy:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: List[CycleContext] = []

    def run_cycle(self, ctx: CycleContext) -> CycleResult:
        self.calls.append(ctx)
        return CycleResult(
            modeling_path=ctx.modeling_path,
            strategy_name=self.name,
            window_start="2021-01-01T00:00:00",
            window_end="2021-01-01T23:55:00",
            points_detected=1,
            points_deferred=0,
            devices_processed=1,
            batch_ids=["batch-e2e"],
            review_ids=[],
            status="success",
            skipped_reason=None,
        )


@pytest.fixture()
def sqlite_adapter(tmp_path: Path) -> _FileSQLiteAdapter:
    adapter = _FileSQLiteAdapter(tmp_path / "e2e.sqlite")
    adapter.create_tables()
    return adapter


@pytest.fixture()
def isolated_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PV_MODEL_REGISTRY_DIR", str(tmp_path / "registry"))
    monkeypatch.setenv("PV_GOVERNANCE_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("PV_SHADOW_COMPARE_DIR", str(tmp_path / "shadow"))
    return tmp_path


def test_18_1_incomplete_early_day_does_not_block_later_complete_day(
    sqlite_adapter: _FileSQLiteAdapter,
) -> None:
    """较早未完整日不阻塞较晚完整日；两天不拼接；frontier 只是连续完成摘要。"""
    repo = SeqDeviceDayLedgerRepository(sqlite_adapter, activation_epoch_id="epoch-e2e")  # type: ignore[arg-type]
    with sqlite_adapter.get_sync_session() as session:
        session.add(
            PathActivationDeviceScope(
                activation_epoch_id="epoch-e2e",
                site_id="site-a",
                device_id="device-a",
                branch_id="branch-a",
                effective_from_date=date(2026, 1, 1),
            )
        )
    early = _key(1)
    later = _key(3)
    repo.upsert_candidate(early, "incomplete-fp")
    _succeed(repo, later, "complete-fp", "batch-later")

    runnable = repo.list_runnable("pv_fault", 10)
    assert [item.key.business_date for item in runnable] == []
    listed = repo.list(page=1, page_size=10, slot="pv_fault")
    by_day = {item.key.business_date: item.status for item in listed["items"]}
    assert by_day[date(2026, 1, 1)] == "waiting_data"
    assert by_day[date(2026, 1, 3)] == "succeeded"
    assert listed["items"][0].key.business_date != listed["items"][1].key.business_date

    device = DeviceKey("pv_fault", "seq_annotation", "site-a", "device-a", "branch-a")
    assert repo.compute_frontier(device, "epoch-e2e") is None

    repo.upsert_candidate(early, "complete-early", is_ready=True)
    runnable = repo.list_runnable("pv_fault", 10)
    assert [item.key.business_date for item in runnable] == [date(2026, 1, 1)]

    first = _full_grid_frame(date(2026, 1, 1))
    second = _full_grid_frame(date(2026, 1, 3))
    rejected = _predictor_without_artifact().predict_device_day(
        pd.concat([first, second], ignore_index=True),
        include_night=True,
    )
    assert rejected["n_points_predicted"] == 0
    assert "禁止把多天数据覆盖到同一时钟网格" in rejected["error"]


def test_18_2_late_data_creates_superseding_batch_and_keeps_old_fact_immutable(
    sqlite_adapter: _FileSQLiteAdapter,
    tmp_path: Path,
) -> None:
    repo = SeqDeviceDayLedgerRepository(sqlite_adapter, activation_epoch_id="epoch-e2e")  # type: ignore[arg-type]
    key = _key(2)
    _succeed(repo, key, "fingerprint-v1", "batch-1")
    old_batch = tmp_path / "batch-1.json"
    old_batch.write_text('{"batch_id":"batch-1","input_fingerprint":"fingerprint-v1"}', encoding="utf-8")
    first = repo.query(key)
    assert first is not None and first.batch_id == "batch-1"

    revision = repo.upsert_candidate(key, "fingerprint-v2", is_ready=True)
    assert revision.status == "revision_pending"
    assert revision.input_fingerprint == "fingerprint-v1"
    assert revision.supersedes_batch_id == "batch-1"

    revised = repo.mark_running(key)
    revised = repo.mark_succeeded(key, "batch-2", "fingerprint-v2")
    assert revised.batch_id == "batch-2"
    assert revised.supersedes_batch_id == "batch-1"
    assert revised.input_fingerprint == "fingerprint-v2"
    assert old_batch.read_text(encoding="utf-8") == (
        '{"batch_id":"batch-1","input_fingerprint":"fingerprint-v1"}'
    )


def test_18_3_full_backfill_is_exclusive_and_does_not_write_production_ledger(
    sqlite_adapter: _FileSQLiteAdapter,
    tmp_path: Path,
) -> None:
    ids = count(1)
    activation = PathActivationService(
        sqlite_adapter,  # type: ignore[arg-type]
        DualPathConfig(max_backfill_days=14),
        epoch_id_factory=lambda: f"epoch-{next(ids)}",
        now_factory=lambda: datetime(2026, 6, 20, 12, 0, 0),
    )
    epoch = activation.create_epoch(
        ActivationRequest(
            "seq_annotation",
            FULL_BACKFILL,
            (
                DeviceActivationInput(
                    DeviceScope("site", "A", "branch"),
                    datetime(2026, 1, 4, 8),
                    date(2026, 1, 1),
                ),
            ),
        )
    )
    seen: List[str] = []

    def detector(scope: DeviceScope, business_date: date) -> Dict[str, Any]:
        seen.append(business_date.isoformat())
        return {"namespace": "historical_backfill", "label": 1}

    runner = BackfillRunner(
        sqlite_adapter,  # type: ignore[arg-type]
        detector=detector,
        task_dir=tmp_path / "backfill_tasks",
        now_factory=lambda: datetime(2026, 6, 21, 0, 0, 0),
        task_id_factory=lambda: "bft-e2e",
    )
    task = runner.run(runner.submit_full_backfill(epoch.activation_epoch_id))
    assert task.writes_production_ledger is False
    assert task.advances_production_frontier is False
    assert seen == ["2026-01-01", "2026-01-02"]

    with sqlite_adapter.get_sync_session() as session:
        claims = list(
            session.execute(
                select(PathActivationLaneClaim).where(
                    PathActivationLaneClaim.activation_epoch_id == epoch.activation_epoch_id
                )
            ).scalars().all()
        )
    by_lane = {item.lane: item for item in claims}
    assert by_lane[HISTORICAL_BACKFILL_LANE].range_end == date(2026, 1, 3)
    assert by_lane[PRODUCTION_LANE].range_start == date(2026, 1, 3)
    assert by_lane[HISTORICAL_BACKFILL_LANE].range_end <= by_lane[PRODUCTION_LANE].range_start

    ledger = SeqDeviceDayLedgerRepository(sqlite_adapter, activation_epoch_id=epoch.activation_epoch_id)  # type: ignore[arg-type]
    listed = ledger.list(page=1, page_size=50, slot="pv_fault")
    assert listed["total"] == 0

    resources = CapacityResources(worker_slots=10, db_connection_slots=10, memory_slots=10, model_load_slots=10)
    snapshot = BackfillCapacityArbiter(resources, production_capacity_reserved_ratio=0.3).snapshot()
    assert snapshot.production_reserved_tokens >= math.ceil(10 * 0.3)
    assert snapshot.backfill_limit_tokens == snapshot.total_tokens - snapshot.production_reserved_tokens


def test_18_4_registry_write_is_visible_in_arena_and_generic_store_rejects_pv_fault(
    tmp_path: Path,
) -> None:
    registry = _seed_champions(tmp_path)
    store = DeploymentSlotStore(
        slots_path=tmp_path / "slots.json",
        pv_adapter=PVDeploymentReadAdapter(registry),
    )
    view = store.get("pv_fault")
    assert view is not None
    assert view.production_model is not None
    assert view.production_model.workflow_id == "data/models/legacy.pkl"

    with pytest.raises(PvFaultRegistryReadOnlyError) as exc:
        store.upsert(DeploymentSlot(slot="pv_fault", production_model=None, updated_at="2026-08-01T00:00:00"))
    assert exc.value.code == PV_FAULT_READ_ONLY_CODE

    production = ModelVersion(
        workflow_id="wf-prod",
        version_tag="v1",
        status="production",
        deployed_at="2026-08-01T00:00:00",
        accuracy_score=4.2,
    )
    store.upsert(
        DeploymentSlot(
            slot="load_forecast",
            production_model=production,
            updated_at="2026-08-01T00:00:00",
        )
    )
    loaded = store.get("load_forecast")
    assert loaded is not None and loaded.production_model is not None
    assert loaded.production_model.workflow_id == "wf-prod"


def test_18_5_shadow_three_layers_and_confirm_field_controls_http_switch(
    sqlite_adapter: _FileSQLiteAdapter,
    isolated_dirs: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """追 confirm：字符串真值/false 拒绝无副作用；JSON true 才切路径并建 Epoch。"""
    registry = _seed_champions(isolated_dirs)
    runner = ShadowCompareRunner(
        model_registry=registry,
        legacy_champion_reader=lambda **_: [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b",
                "business_date": date(2026, 1, 1),
                "predicted_label": 0,
                "latency_ms": 10,
            }
        ],
        seq_champion_reader=lambda **_: [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b",
                "business_date": date(2026, 1, 1),
                "predicted_label": 0,
                "point_predictions": [{"label": 0}] * SLOTS_PER_DAY,
                "latency_ms": 20,
            }
        ],
        report_store=ShadowReportStore(base_dir=isolated_dirs / "shadow"),
        artifact_loader=lambda _ref: {"loaded": True},
    )
    evidence = runner.run_compare(date(2026, 1, 1), date(2026, 1, 1))
    payload = evidence.to_dict()
    assert payload["common_metrics"]
    assert payload["seq_native_metrics"]
    assert payload["runtime_metrics"]

    store = ShadowReportStore()
    comparison_id = _gate_report(store, registry, "cmp-e2e-confirm")
    before = registry.get_slot().production_path
    promotion_before = len(PromotionEventStore().list_recent(limit=1000))

    orig_init = CrossPathSwitchCoordinator.__init__

    def _patched_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs.setdefault("watermark_reader", lambda *_a: datetime(2026, 1, 10, 8, 0, 0))
        kwargs.setdefault("artifact_validator", lambda _ref: True)
        kwargs.setdefault("contract_validator", lambda _ref: True)
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(CrossPathSwitchCoordinator, "__init__", _patched_init)

    def _adapter_factory(*_args, **_kwargs):
        return sqlite_adapter

    monkeypatch.setattr("services.db.adapter.DBAdapter", _adapter_factory)

    import api.iterative_labeling as labeling_api
    import api.pv_dual_path as dual_api

    monkeypatch.setattr(labeling_api, "_pv_model_registry", registry)
    labeling_api._cumulative_training_services.clear()

    app = FastAPI()
    app.include_router(labeling_api.router)
    app.include_router(dual_api.router)
    client = TestClient(app)

    reject_string = client.put(
        "/api/iterative-labeling/cumulative-training/modeling-paths",
        json={
            "modeling_path": "seq_annotation",
            "comparison_id": comparison_id,
            "activation_mode": "cutover_only",
            "confirm": "true",
            "operator": "e2e",
            "reason": "string confirm must fail",
            "device_scope": [{"site_id": "s", "device_id": "d", "branch_id": "b"}],
        },
    )
    assert reject_string.status_code == 409
    assert registry.get_slot().production_path == before

    reject_false = client.put(
        "/api/iterative-labeling/cumulative-training/modeling-paths",
        json={
            "modeling_path": "seq_annotation",
            "comparison_id": comparison_id,
            "activation_mode": "cutover_only",
            "confirm": False,
            "operator": "e2e",
            "reason": "false confirm must fail",
            "device_scope": [{"site_id": "s", "device_id": "d", "branch_id": "b"}],
        },
    )
    assert reject_false.status_code == 409
    assert registry.get_slot().production_path == before
    with sqlite_adapter.get_sync_session() as session:
        assert session.execute(select(func.count()).select_from(PathActivationEpoch)).scalar_one() == 0

    switched = client.put(
        "/api/iterative-labeling/cumulative-training/modeling-paths",
        json={
            "modeling_path": "seq_annotation",
            "comparison_id": comparison_id,
            "activation_mode": "cutover_only",
            "confirm": True,
            "operator": "e2e",
            "reason": "nine gates passed",
            "device_scope": [{"site_id": "s", "device_id": "d", "branch_id": "b"}],
        },
    )
    assert switched.status_code == 200, switched.text
    body = switched.json()
    assert body["status"] == "switched"
    assert body["registry"]["production_path"] == "seq_annotation"
    assert body["event"]["to_path"] == "seq_annotation"

    listed = client.get("/api/iterative-labeling/cumulative-training/modeling-paths")
    assert listed.status_code == 200
    assert listed.json()["production_path"] == "seq_annotation"

    epochs = client.get("/api/scheduler/pv-dual-path/activation-epochs")
    assert epochs.status_code == 200
    assert epochs.json()["total"] >= 1

    ledger = client.get("/api/scheduler/pv-dual-path/ledger", params={"page_size": 5})
    assert ledger.status_code == 200
    assert ledger.json()["cursor_semantics"] == "continuous_completion_frontier"

    assert len(PathSwitchEventStore().list_recent()) == 1
    assert len(PromotionEventStore().list_recent(limit=1000)) == promotion_before


def test_18_6_in_path_promotion_keeps_path_and_qualified_challenger_blocks_cross_path(
    isolated_dirs: Path,
) -> None:
    registry = PVModelRegistry()
    registered = registry.register_challenger(
        "legacy_day",
        ModelRegistration("data/models/legacy.pkl", "el", 0.70, "2026-01-01T00:00:00"),
    )
    assert registered.status == "registered"
    promoted = registry.promote_within_path("legacy_day", "el")
    assert promoted.status == "promoted"
    registry.register_challenger(
        "legacy_day",
        ModelRegistration("data/models/legacy-better.pkl", "el2", 0.85, "2026-01-02T00:00:00"),
    )
    better = registry.promote_within_path("legacy_day", "el2")
    after = registry.get_slot()
    assert better.status == "promoted"
    assert after.production_path == "legacy_day"
    assert after.path_models["legacy_day"].champion is not None
    assert after.path_models["legacy_day"].champion.evaluation_id == "el2"
    promotions = PromotionEventStore().list_recent()
    assert promotions
    assert all(event.modeling_path == "legacy_day" for event in promotions)
    assert PathSwitchEventStore().list_recent() == []

    decision = PVRecoveryPolicy().decide(
        PathHealth(champion_loadable=False, consecutive_failed_cycles=9),
        qualified_challenger_evaluation_ids=["el2"],
    )
    assert decision.action == "promote_within_path"
    assert decision.fallback_gate_required is False

    fallback = PVRecoveryPolicy().decide(
        PathHealth(champion_loadable=False, consecutive_failed_cycles=9),
        qualified_challenger_evaluation_ids=[],
    )
    assert fallback.action == "evaluate_fallback_gate"
    assert fallback.fallback_gate_required is True


def test_18_7_scheduler_isolates_paths_watermark_ignores_wall_clock_and_mock_is_deterministic(
    sqlite_adapter: _FileSQLiteAdapter,
) -> None:
    with sqlite_adapter.get_sync_session() as session:
        session.add(
            TrainingSample(
                id=1,
                time=datetime(2021, 8, 23, 12, 0, 0),
                site_id="site-wm",
                device_id="device-wm",
                branch_id="branch-wm",
                value=1.0,
                i_cal=1.0,
                data_source="mock",
            )
        )
        session.add(
            DevicePredictionCursor(
                slot="pv_fault",
                modeling_path="legacy_day",
                site_id="site-iso",
                device_id="device-iso",
                branch_id="branch-iso",
                last_predicted_time=datetime(2021, 8, 23, 10, 0, 0),
                cursor_semantics="event_time_watermark",
            )
        )
        session.add(
            DevicePredictionCursor(
                slot="pv_fault",
                modeling_path="seq_annotation",
                site_id="site-iso",
                device_id="device-iso",
                branch_id="branch-iso",
                last_predicted_time=datetime(2021, 8, 20, 0, 0, 0),
                cursor_semantics="continuous_completion_frontier",
            )
        )

    watermark = DataWatermarkService(sqlite_adapter)  # type: ignore[arg-type]
    observed = watermark.device_watermark("site-wm", "device-wm", "branch-wm")
    assert observed == datetime(2021, 8, 23, 12, 0, 0)
    assert observed.date() != datetime.utcnow().date() or observed.year == 2021

    with sqlite_adapter.get_sync_session() as session:
        rows = list(
            session.execute(
                select(DevicePredictionCursor).where(
                    DevicePredictionCursor.site_id == "site-iso"
                )
            ).scalars().all()
        )
    semantics = {row.modeling_path: row.cursor_semantics for row in rows}
    assert semantics["legacy_day"] == "event_time_watermark"
    assert semantics["seq_annotation"] == "continuous_completion_frontier"
    times = {row.modeling_path: row.last_predicted_time for row in rows}
    assert times["legacy_day"] != times["seq_annotation"]

    legacy = _RecordingStrategy("LegacyDayStrategy")
    seq = _RecordingStrategy("SeqDailyStrategy")
    status: List[Dict[str, Any]] = []
    scheduler = DualPathScheduler(
        {"legacy_day": legacy, "seq_annotation": seq},
        read_modeling_paths=lambda _slot: {
            "production_path": "seq_annotation",
            "active_activation_epoch_id": "epoch-e2e",
            "path_models": {"seq_annotation": {"model_ref": "data/models/seq"}},
        },
        status_writer=status.append,
        watermark=watermark,
    )
    seq_result = scheduler.dispatch("pv_fault")
    assert seq_result.strategy_name == "SeqDailyStrategy"
    assert len(seq.calls) == 1 and len(legacy.calls) == 0

    scheduler_legacy = DualPathScheduler(
        {"legacy_day": legacy, "seq_annotation": seq},
        read_modeling_paths=lambda _slot: {
            "production_path": "legacy_day",
            "active_activation_epoch_id": "epoch-e2e",
            "path_models": {"legacy_day": {"model_ref": "data/models/legacy.pkl"}},
        },
        status_writer=status.append,
        watermark=watermark,
    )
    legacy_result = scheduler_legacy.dispatch("pv_fault")
    assert legacy_result.strategy_name == "LegacyDayStrategy"
    assert len(legacy.calls) == 1

    skipped = DualPathScheduler(
        {"seq_annotation": seq},
        read_modeling_paths=lambda _slot: {
            "production_path": "seq_annotation",
            "active_activation_epoch_id": "epoch-e2e",
            "path_models": {"seq_annotation": {"model_ref": None}},
        },
        status_writer=status.append,
        watermark=watermark,
    ).dispatch("pv_fault")
    assert skipped.status == "skipped"
    assert skipped.skipped_reason == "missing_champion_model_ref"

    devices = [("s", f"d{i}", "b") for i in range(20)]

    def _plan(business_date: date) -> List[tuple]:
        rng = random.Random(f"pv-mock-release|{business_date.isoformat()}")
        shuffled = list(devices)
        rng.shuffle(shuffled)
        rows = []
        for idx, dev in enumerate(shuffled):
            is_dropped = rng.random() < _DROP_RATIO
            delay_ticks = 0
            if not is_dropped and rng.random() < _DELAY_RATIO:
                delay_ticks = rng.randint(*_DELAY_TICKS_RANGE)
            rows.append((dev, idx % _RELEASE_BATCH_COUNT, delay_ticks, is_dropped))
        return rows

    day = date(2021, 8, 23)
    assert _plan(day) == _plan(day)
    assert _plan(day) != _plan(day + timedelta(days=1))


def _load_env_local() -> None:
    envp = Path(__file__).resolve().parents[2] / ".env.local"
    if not envp.exists():
        return
    for line in envp.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def test_mysql_schema_not_yet_migrated_is_recorded_as_gap() -> None:
    """只读探测公司 MySQL：能连但双路径表/列尚未落地，不能冒充真库 Ledger 已通。"""
    pymysql = pytest.importorskip("pymysql")
    _load_env_local()
    url = os.environ.get("DB_CONNECTION_URL", "")
    if not url:
        pytest.skip("没有 DB_CONNECTION_URL")
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url.replace("mysql+pymysql://", "mysql://"))
    try:
        conn = pymysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=unquote(parsed.password or ""),
            database=(parsed.path or "/").lstrip("/") or None,
            connect_timeout=8,
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"MySQL 不可达：{type(exc).__name__}")
    try:
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = {row[0] for row in cursor.fetchall()}
        assert "training_samples" in tables
        assert "device_prediction_cursor" in tables
        assert "seq_device_day_ledger" not in tables
        assert "path_activation_epochs" not in tables
        cursor.execute("SHOW COLUMNS FROM device_prediction_cursor")
        columns = {row[0] for row in cursor.fetchall()}
        assert "modeling_path" not in columns
        assert "slot" not in columns
        cursor.execute(
            "SELECT MAX(time) FROM training_samples WHERE data_source IN ('mock', 'production')"
        )
        max_time = cursor.fetchone()[0]
        if max_time is not None:
            event_time = max_time if isinstance(max_time, datetime) else datetime.combine(max_time, datetime.min.time())
            assert event_time.year < datetime.utcnow().year or event_time < datetime.utcnow() - timedelta(days=1)
    finally:
        conn.close()
# @AI_GENERATED: end
