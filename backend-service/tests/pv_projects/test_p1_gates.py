# @AI_GENERATED
"""P1 修正回归测试（semantic-review/2026-09-14-102909-pr-0.md 的 P1-1 / P1-2 / P1-3 / P1-7）。

本文件是 Wave 2 的 **RED 基线**：各用例在修复前必须失败，修复后必须通过。

覆盖：
- P1-2：readiness 评估抛异常时 **fail-closed**，不得回落 `DATA_READY`。
- P1-3：stage 投影只消费成功且有业务意义的产物（failed / prediction 不触发 EXPERIMENT_RESULT）；
  已冻结快照优先于未完成审核。
- P1-7：项目级 store（物理路径不含 slot）的写锁必须与物理路径同源，
  否则两条 slot 并发写同一文件会丢写。
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from contextlib import contextmanager
from typing import Any, Iterator

import pytest

from services.pv_projects import ScopeContext, dataset_profiles, dataset_versions, snapshots
from services.pv_projects import projects as project_service
from services.pv_projects import repositories as repo
from services.pv_projects.stores import executions, reviews

_DATASETS_ROOT = "data/slot_datasets"


@contextmanager
def temp_storage() -> Iterator[None]:
    tmp = tempfile.mkdtemp(prefix="pvproj_p1_")
    repo.set_storage_base(tmp)
    try:
        yield
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _new_project() -> str:
    rec = project_service.create_project(project_name="P1 修正测试", solution_id="pv_fault")
    return rec["project_id"]


def _publish_ready_version(pid: str, *, granularity: str = "device_day") -> str:
    """发布一个 readiness=ready 的数据版本 + 画像（项目级；直接写存储）。"""
    scope = ScopeContext.create(pid)
    profile = dataset_profiles.append(
        scope,
        {
            "dataset_profile_id": "dsp-p1-1",
            "mapping": {"time_col": "ts", "device_col": "dev", "value_col": "val"},
            "mapping_digest": "sha256:p1",
            "label_policy": {"granularity": granularity},
            "facts": {"sufficient_coverage": True},
        },
    )
    version = dataset_versions.append(
        scope,
        {
            "dataset_version_id": "dsv-p1-1",
            "dataset_profile_id": profile["dataset_profile_id"],
            "artifact_ref": "data/slot_datasets/projects/x/dsv-p1-1.json",
            "content_digest": "sha256:p1",
            "immutable": True,
        },
    )
    return version["dataset_version_id"]


def _scope(pid: str, slot: str) -> ScopeContext:
    return ScopeContext.create(pid, slot, require_slot=True, allow_legacy=False)


def _path_of(scope: ScopeContext) -> Any:
    return repo._resolve_object_path(
        scope,
        root=_DATASETS_ROOT,
        filename="dataset_versions.json",
        include_slot=False,
        include_version=False,
    )


# ---------------------------------------------------------------------------
# P1-2：readiness 评估失败必须 fail-closed
# ---------------------------------------------------------------------------

def test_readiness_evaluation_failure_is_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """评估器抛异常时不得回落 `DATA_READY`，且必须暴露可诊断的失败态。

    修复前：`_latest_version_readiness` 的 `except Exception: return None`，
    调用方再把 None 当 `"ready"` → 项目明明有数据版本却给出 `DATA_READY`（fail-open）。
    """
    with temp_storage():
        pid = _new_project()
        _publish_ready_version(pid)

        def boom(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("profiler crashed")

        monkeypatch.setattr(project_service, "evaluate_path_readiness", boom)

        ov = project_service.project_overview(pid)
        assert len(ov["paths"]) == 3
        for path in ov["paths"]:
            assert path["stage"] != "DATA_READY", path
            assert path["readiness_status"] == "unavailable", path
            assert path["readiness_primary_blocker"] == "readiness_evaluation_failed", path


def test_readiness_absent_without_versions_is_not_failure() -> None:
    """项目没有任何数据版本时 readiness 为空是正常态，不得被当成评估失败。"""
    with temp_storage():
        pid = _new_project()
        ov = project_service.project_overview(pid)
        for path in ov["paths"]:
            assert path["stage"] == "UNCONFIGURED", path
            assert path["readiness_status"] is None, path


# ---------------------------------------------------------------------------
# P1-3：stage 投影的成功产物优先级
# ---------------------------------------------------------------------------

def test_failed_execution_does_not_advance_stage_to_experiment_result() -> None:
    """失败执行不构成"实验结果"。

    修复前：只要 `executions` 非空且无候选/快照，就判 `EXPERIMENT_RESULT`
    （"登记为可治理候选"），而失败执行根本没有可登记的结果。
    """
    with temp_storage():
        pid = _new_project()
        _publish_ready_version(pid)
        scope = _scope(pid, "pv_tsc")
        executions.append(
            scope,
            {
                "execution_id": "exec-failed-1",
                "project_workflow_id": "pwf-x",
                "workflow_kind": "training",
                "run_mode": "training",
                "run_domain": "project",
                "governance_eligible": True,
                "status": "failed",
                "node_timeline": [],
            },
        )
        path = {p["slot"]: p for p in project_service.project_overview(pid)["paths"]}["pv_tsc"]
        assert path["stage"] != "EXPERIMENT_RESULT", path
        # 无有效下游产物 → 回落到 readiness 决定的数据阶段（readiness=ready）。
        assert path["stage"] == "DATA_READY", path


def test_prediction_execution_does_not_advance_stage() -> None:
    """prediction / replay 执行不是训练产物，不得推进到 `EXPERIMENT_RESULT`。"""
    with temp_storage():
        pid = _new_project()
        _publish_ready_version(pid)
        scope = _scope(pid, "pv_tsc")
        executions.append(
            scope,
            {
                "execution_id": "exec-pred-1",
                "project_workflow_id": "pwf-x",
                "workflow_kind": "training",
                "run_mode": "prediction",
                "run_domain": "project",
                "governance_eligible": False,
                "status": "success",
                "node_timeline": [],
            },
        )
        path = {p["slot"]: p for p in project_service.project_overview(pid)["paths"]}["pv_tsc"]
        assert path["stage"] != "EXPERIMENT_RESULT", path


def test_successful_training_execution_advances_stage() -> None:
    """成功的训练执行才推进到 `EXPERIMENT_RESULT`。"""
    with temp_storage():
        pid = _new_project()
        _publish_ready_version(pid)
        scope = _scope(pid, "pv_tsc")
        executions.append(
            scope,
            {
                "execution_id": "exec-train-1",
                "project_workflow_id": "pwf-x",
                "workflow_kind": "training",
                "run_mode": "training",
                "run_domain": "project",
                "governance_eligible": True,
                "status": "success",
                "node_timeline": [],
            },
        )
        path = {p["slot"]: p for p in project_service.project_overview(pid)["paths"]}["pv_tsc"]
        assert path["stage"] == "EXPERIMENT_RESULT", path


def test_frozen_snapshot_outranks_pending_review() -> None:
    """已冻结快照优先于未完成审核。

    修复前 `pending_reviews > 0` 的判定排在快照之前，会让"已冻结"的路径退回"完成审核"。
    """
    with temp_storage():
        pid = _new_project()
        _publish_ready_version(pid)
        scope = _scope(pid, "pv_tsc")
        reviews.append(scope, {"review_id": "rev-1", "status": "open"})
        snapshots.append(
            scope,
            {"snapshot_id": "snap-1", "snapshot_type": "tsc_288x3_grid", "included_count": 2},
        )
        path = {p["slot"]: p for p in project_service.project_overview(pid)["paths"]}["pv_tsc"]
        assert path["stage"] == "SNAPSHOT_READY", path


# ---------------------------------------------------------------------------
# P1-7：项目级 store 的写锁必须与物理路径同源
# ---------------------------------------------------------------------------

def test_project_level_store_path_is_slot_independent() -> None:
    """前提校验：两条 slot 对项目级 store 解析到**同一个物理文件**。"""
    with temp_storage():
        pid = _new_project()
        day = _scope(pid, "pv_day")
        point = _scope(pid, "pv_point")
        assert _path_of(day) == _path_of(point)


def test_concurrent_append_to_project_level_store_loses_no_write() -> None:
    """两条 slot 并发 append 到同一项目级文件，两条记录都必须存在。

    修复前锁键是 `scope.partition()`（含 slot）→ 两把不同的锁保护同一个文件，
    `append` 的 read-modify-write 互相覆盖，产生丢写。
    """
    with temp_storage():
        pid = _new_project()
        day = _scope(pid, "pv_day")
        point = _scope(pid, "pv_point")
        assert _path_of(day) == _path_of(point)  # 前提：物理同一文件

        orig_read = repo._read_json
        barrier = threading.Barrier(2, timeout=0.6)
        errors: list[BaseException] = []

        def synced_read(path):  # type: ignore[no-untyped-def]
            payload = orig_read(path)
            # 强制两个线程都基于**同一份旧快照**再各自写入：
            # 若锁键同源，第二个线程会被挡在临界区外，此 wait 超时后正常继续；
            # 若锁键不同源，两个线程都会走到这里，随后的写入必然互相覆盖。
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                pass
            return payload

        def append_one(scope: ScopeContext, vid: str) -> None:
            try:
                dataset_versions.append(scope, {"dataset_version_id": vid, "dataset_id": "d1"})
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        original = repo._read_json
        repo._read_json = synced_read
        try:
            t1 = threading.Thread(target=append_one, args=(day, "dsv-day"))
            t2 = threading.Thread(target=append_one, args=(point, "dsv-point"))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)
        finally:
            repo._read_json = original

        assert not errors, errors
        ids = {v["dataset_version_id"] for v in dataset_versions.list(day)}
        assert ids == {"dsv-day", "dsv-point"}, f"丢写：只看到 {ids}"


# @AI_GENERATED: end
