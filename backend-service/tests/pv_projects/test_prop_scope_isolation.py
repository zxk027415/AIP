# @AI_GENERATED
"""Property tests P-SCOPE-01 / P-LEGACY-01：项目/路径复合隔离与新项目无 legacy 回退。

设计依据：design.md §29.1（P-SCOPE-01 / P-LEGACY-01）；requirements.md R1.1–R1.3、R1.5–R1.7、
R13.1、R13.2、R13.4。

覆盖不变量：
- P-SCOPE-01：两个项目在相同 slot、同一项目在不同 slot，其写、读、API 回显互不串用。
- P-LEGACY-01：缺失 / 非法 / 新项目 scope fail-closed；不分配默认项目；
  新项目缺失对象返回空态且不读取 / 不写入 legacy 同槽真源。

说明：迟到响应与前端缓存丢弃属于前端 generation 守卫（scopedApi / ProjectScopeContext），
由前端 P-UX-01（任务 9.2）覆盖；本文件覆盖后端可验证的写 / 读 / API 回显与 fail-closed。
"""

from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from api.pv_projects import router as pv_router
from services.pv_projects import (
    ScopeContext,
    ScopeError,
    candidates,
    cumulative_events,
    cursors,
    dataset_versions,
    executions,
    get_scoped_registry_store,
    results,
    reviews,
    snapshots,
    verifications,
)
from services.pv_projects import repositories as repo
from services.pv_projects.scope import PRODUCT_SLOTS

# 参与隔离断言的全部集合类 scoped 仓储（design 任务 1.2 列举的对象类型）。
_COLLECTION_STORES = [
    candidates,
    verifications,
    dataset_versions,
    executions,
    reviews,
    cumulative_events,
    snapshots,
    results,
]

_project_ids = st.from_regex(r"proj-[a-z0-9]{1,8}", fullmatch=True)
_slots = st.sampled_from(list(PRODUCT_SLOTS))


@contextmanager
def temp_storage() -> Iterator[Path]:
    """把 scoped 存储根重定向到临时目录，用完清理（不触碰真实 data/）。"""
    tmp = tempfile.mkdtemp(prefix="pvproj_prop_")
    repo.set_storage_base(tmp)
    try:
        yield Path(tmp)
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


# ===========================================================================
# P-SCOPE-01：项目 / 路径复合隔离
# ===========================================================================

@settings(max_examples=40, deadline=None)
@given(pid_a=_project_ids, pid_b=_project_ids, slot=_slots)
def test_registry_isolated_across_projects(pid_a: str, pid_b: str, slot: str) -> None:
    """同一 slot 下，两个项目的 registry 写入互不可见。"""
    assume(pid_a != pid_b)
    with temp_storage():
        a = ScopeContext.create(pid_a, slot)
        b = ScopeContext.create(pid_b, slot)
        reg = get_scoped_registry_store()
        reg.save(a, {"registry_version": 1, "champion": {"champion_model_ref": pid_a}})

        assert reg.get(a)["registry_version"] == 1
        view_b = reg.get(b)
        assert view_b["registry_version"] == 0
        assert view_b["champion"] is None  # 不跨项目读


@settings(max_examples=60, deadline=None)
@given(
    pid_a=_project_ids,
    pid_b=_project_ids,
    slot=_slots,
    store_idx=st.integers(min_value=0, max_value=len(_COLLECTION_STORES) - 1),
)
def test_collections_isolated_across_projects(pid_a: str, pid_b: str, slot: str, store_idx: int) -> None:
    """每个集合类 scoped 仓储在两个项目间读写隔离。"""
    assume(pid_a != pid_b)
    store = _COLLECTION_STORES[store_idx]
    with temp_storage():
        a = ScopeContext.create(pid_a, slot)
        b = ScopeContext.create(pid_b, slot)
        record_id = "rec-A-1"
        store.append(a, {store.id_field: record_id})

        listed_a = store.list(a)
        assert [item.get(store.id_field) for item in listed_a] == [record_id]
        assert store.list(b) == []  # 不跨项目读
        assert store.find(a, record_id) is not None
        assert store.find(b, record_id) is None  # 不跨项目查


@settings(max_examples=40, deadline=None)
@given(pid=_project_ids, slot_a=_slots, slot_b=_slots)
def test_no_cross_slot_within_project(pid: str, slot_a: str, slot_b: str) -> None:
    """同一项目下，不同 slot 的候选与游标互不串用。"""
    assume(slot_a != slot_b)
    with temp_storage():
        a = ScopeContext.create(pid, slot_a)
        b = ScopeContext.create(pid, slot_b)
        candidates.append(a, {"model_candidate_id": "mc-1"})
        cursors.write(a, {"cursor_key": "2026-01-01"})

        assert candidates.list(b) == []
        assert cursors.read(b) is None


def test_api_echo_matches_scope_and_no_cross_project() -> None:
    """API 回显与请求 scope 一致；请求项目 B 绝不返回项目 A 的 registry。"""
    with temp_storage():
        app = FastAPI()
        app.include_router(pv_router)
        client = TestClient(app)

        # P1-5 后读写都要求项目已登记（旧夹具直接操作未登记项目，正是被堵的洞）。
        for pid_ in ("proj-a", "proj-b"):
            repo.register_project_in_index(pid_, project_name=pid_)

        a = ScopeContext.create("proj-a", "pv_tsc")
        get_scoped_registry_store().save(
            a, {"registry_version": 3, "champion": {"champion_model_ref": "A"}}
        )

        ra = client.get("/api/pv-projects/proj-a/slots/pv_tsc/registry").json()
        assert ra["project_id"] == "proj-a" and ra["slot"] == "pv_tsc"
        assert ra["registry_version"] == 3

        rb = client.get("/api/pv-projects/proj-b/slots/pv_tsc/registry").json()
        assert rb["project_id"] == "proj-b"
        assert rb["registry_version"] == 0 and rb["champion"] is None


@settings(max_examples=60, deadline=None)
@given(
    pid=_project_ids,
    slot=_slots,
    payload=st.fixed_dictionaries(
        {
            "project_id": st.from_regex(r"other-[a-z0-9]{1,6}", fullmatch=True),
        }
    ),
)
def test_response_scope_mismatch_always_detected(pid: str, slot: str, payload: dict) -> None:
    """任何回显了不同 project_id 的响应都被判为 scope mismatch。"""
    assume(payload["project_id"] != pid)
    scope = ScopeContext.create(pid, slot)
    mismatches = scope.mismatches({**payload, "slot": slot})
    assert "project_id" in mismatches


# ===========================================================================
# P-LEGACY-01：新项目无 legacy 回退，fail-closed
# ===========================================================================

@given(
    bad=st.sampled_from(
        ["", "   ", "..", "../evil", "a/b", "a\\b", "a..b", "/abs", "C:\\x", "proj/../x"]
    )
)
@settings(max_examples=20, deadline=None)
def test_missing_or_invalid_project_fail_closed(bad: str) -> None:
    """缺失 / 非法 project_id → fail-closed，不分配默认项目。"""
    with pytest.raises(ScopeError):
        ScopeContext.create(bad)


def test_missing_project_is_none_fail_closed() -> None:
    with pytest.raises(ScopeError):
        ScopeContext.create(None)


@settings(max_examples=30, deadline=None)
@given(pid=_project_ids, slot=_slots)
def test_new_project_never_reads_slot_only_legacy_file(pid: str, slot: str) -> None:
    """即使 slot-only（legacy 布局）文件存在，新项目也只读自己的 scoped 路径，返回空态。"""
    with temp_storage() as base:
        slot_only = base / "data" / "slot_governance" / slot / "registry.json"
        slot_only.parent.mkdir(parents=True, exist_ok=True)
        slot_only.write_text(
            json.dumps({"registry_version": 9, "champion": {"champion_model_ref": "LEGACY"}}),
            encoding="utf-8",
        )
        new = ScopeContext.create(pid, slot)
        view = get_scoped_registry_store().get(new)
        assert view["registry_version"] == 0
        assert view["champion"] is None  # 不读 legacy 同槽补位


@settings(max_examples=30, deadline=None)
@given(pid=_project_ids, slot=_slots)
def test_new_project_write_does_not_touch_slot_only_file(pid: str, slot: str) -> None:
    """新项目写入落到 projects/<pid>/<slot>，不创建 / 不修改 slot-only 真源。"""
    with temp_storage() as base:
        new = ScopeContext.create(pid, slot)
        get_scoped_registry_store().save(new, {"registry_version": 1})

        slot_only = base / "data" / "slot_governance" / slot / "registry.json"
        assert not slot_only.exists()
        scoped = base / "data" / "slot_governance" / "projects" / pid / slot / "registry.json"
        assert scoped.exists()


@settings(max_examples=30, deadline=None)
@given(slot=_slots)
def test_legacy_scope_is_read_only(slot: str) -> None:
    """legacy 项目只读：registry / candidate 等写入被拒绝。"""
    with temp_storage():
        leg = ScopeContext.create("legacy", slot)
        assert leg.is_legacy and leg.read_only
        with pytest.raises(ScopeError):
            get_scoped_registry_store().save(leg, {"registry_version": 1})
        with pytest.raises(ScopeError):
            candidates.append(leg, {"model_candidate_id": "x"})


def test_new_product_write_path_refuses_legacy_at_source() -> None:
    """新产品写入路径 allow_legacy=False，从源头拒绝把 legacy 当默认。"""
    with pytest.raises(ScopeError):
        ScopeContext.create("legacy", "pv_day", allow_legacy=False)

# @AI_GENERATED: end
