# @AI_GENERATED
"""Property test P-LINEAGE-01：不可变数据版本 lineage。

设计依据：design.md §29.1（P-LINEAGE-01）；requirements.md R6.2、R7.1、R7.2、R11.2、
R13.5、R13.6、R15.2、R15.3。

不变量：
- 发布的数据版本携带稳定内容摘要；相同内容幂等命中（不物化重复版本）。
- 映射变化生成新画像 / 新版本（新摘要），旧版本不被改写（不可变）。
- artifact_ref 为相对引用，绝不是机器绝对路径。
- 下游 execution / review / snapshot / candidate 保留相同 scope 与 dataset_version_id lineage；
  跨项目不可见（隔离）。
- 缺失画像 / 画像与资产不一致时 fail-closed，不产出版本。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from services.pv_projects import ScopeContext, ScopeError, candidates, executions, reviews, snapshots
from services.pv_projects import datasets as ds
from services.pv_projects import repositories as repo
from services.pv_projects.paths import is_machine_absolute
from services.pv_projects.scope import PRODUCT_SLOTS

_project_ids = st.from_regex(r"proj-[a-z0-9]{1,8}", fullmatch=True)
_slots = st.sampled_from(list(PRODUCT_SLOTS))
_mappings = st.fixed_dictionaries(
    {
        "time_col": st.sampled_from(["ts", "time", "dt"]),
        "device_col": st.sampled_from(["device_id", "dev", "sn"]),
        "value_col": st.sampled_from(["value", "current", "i"]),
    }
)


@contextmanager
def temp_storage() -> Iterator[Path]:
    tmp = tempfile.mkdtemp(prefix="pvlineage_")
    repo.set_storage_base(tmp)
    try:
        yield Path(tmp)
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _register_and_publish(scope: ScopeContext, mapping: dict) -> dict:
    asset = ds.register_dataset_asset(
        scope, source_kind="upload", file_name="a.parquet", upload_ref="data/uploads/a.parquet"
    )
    profile = ds.save_dataset_profile(scope, dataset_id=asset["dataset_id"], mapping=mapping)
    version = ds.publish_dataset_version(
        scope, dataset_id=asset["dataset_id"], dataset_profile_id=profile["dataset_profile_id"]
    )
    return {"asset": asset, "profile": profile, "version": version}


@settings(max_examples=40, deadline=None)
@given(pid=_project_ids, mapping=_mappings)
def test_version_digest_stable_and_immutable(pid: str, mapping: dict) -> None:
    """同一资产 + 同一画像重复发布 → 同一内容摘要、幂等命中、不产生重复版本。"""
    with temp_storage():
        scope = ScopeContext.create(pid)
        published = _register_and_publish(scope, mapping)
        v1 = published["version"]
        assert v1["idempotent_hit"] is False
        assert not is_machine_absolute(v1["artifact_ref"])
        assert v1["artifact_ref"].startswith(f"data/slot_datasets/projects/{pid}/")
        assert v1["project_id"] == pid and v1["dataset_id"] == published["asset"]["dataset_id"]
        assert v1["dataset_profile_id"] == published["profile"]["dataset_profile_id"]

        # 再次发布同一资产 + 同一画像 → 幂等命中，同摘要，仍只有一个版本。
        v2 = ds.publish_dataset_version(
            scope,
            dataset_id=published["asset"]["dataset_id"],
            dataset_profile_id=published["profile"]["dataset_profile_id"],
        )
        assert v2["idempotent_hit"] is True
        assert v2["content_digest"] == v1["content_digest"]
        assert v2["dataset_version_id"] == v1["dataset_version_id"]
        assert len(ds.list_dataset_versions(scope)) == 1


@settings(max_examples=40, deadline=None)
@given(pid=_project_ids, m1=_mappings, m2=_mappings)
def test_mapping_change_creates_new_version(pid: str, m1: dict, m2: dict) -> None:
    """映射变化 → 新画像 / 新版本 / 新摘要；旧版本不被改写。"""
    assume(m1 != m2)
    with temp_storage():
        scope = ScopeContext.create(pid)
        asset = ds.register_dataset_asset(
            scope, source_kind="upload", file_name="a.parquet", upload_ref="data/uploads/a.parquet"
        )
        p1 = ds.save_dataset_profile(scope, dataset_id=asset["dataset_id"], mapping=m1)
        p2 = ds.save_dataset_profile(scope, dataset_id=asset["dataset_id"], mapping=m2)
        v1 = ds.publish_dataset_version(scope, dataset_id=asset["dataset_id"], dataset_profile_id=p1["dataset_profile_id"])
        v2 = ds.publish_dataset_version(scope, dataset_id=asset["dataset_id"], dataset_profile_id=p2["dataset_profile_id"])
        assert v1["content_digest"] != v2["content_digest"]
        assert v1["dataset_version_id"] != v2["dataset_version_id"]
        assert len(ds.list_dataset_versions(scope)) == 2


@settings(max_examples=30, deadline=None)
@given(pid_a=_project_ids, pid_b=_project_ids, slot=_slots, mapping=_mappings)
def test_downstream_lineage_preserved_and_isolated(pid_a: str, pid_b: str, slot: str, mapping: dict) -> None:
    """下游 execution/review/snapshot/candidate 保留相同 scope 与版本 lineage；跨项目不可见。"""
    assume(pid_a != pid_b)
    with temp_storage():
        scope_a = ScopeContext.create(pid_a)
        published = _register_and_publish(scope_a, mapping)
        version_id = published["version"]["dataset_version_id"]

        slot_scope = ScopeContext.create(pid_a, slot)
        executions.append(slot_scope, {"execution_id": "exec-1", "dataset_version_id": version_id})
        reviews.append(slot_scope, {"review_id": "rev-1", "dataset_version_id": version_id})
        snapshots.append(slot_scope, {"snapshot_id": "snap-1", "dataset_version_id": version_id})
        candidates.append(slot_scope, {"model_candidate_id": "mc-1", "source_dataset_version_id": version_id})

        # lineage：下游对象都指向同一版本 id，且都在 pid_a scope 下
        assert executions.list(slot_scope)[0]["dataset_version_id"] == version_id
        assert reviews.list(slot_scope)[0]["dataset_version_id"] == version_id
        assert snapshots.list(slot_scope)[0]["dataset_version_id"] == version_id
        assert candidates.list(slot_scope)[0]["source_dataset_version_id"] == version_id

        # 隔离：版本与下游对象在项目 B 不可见
        scope_b_proj = ScopeContext.create(pid_b)
        scope_b_slot = ScopeContext.create(pid_b, slot)
        assert ds.list_dataset_versions(scope_b_proj) == []
        assert executions.list(scope_b_slot) == []
        assert candidates.list(scope_b_slot) == []


def test_publish_fail_closed_on_missing_or_mismatched_profile() -> None:
    """缺失画像 / 画像与资产不一致 → fail-closed，不产出版本。"""
    with temp_storage():
        scope = ScopeContext.create("proj-fc")
        asset1 = ds.register_dataset_asset(scope, source_kind="platform_asset", asset_id="a-1")
        asset2 = ds.register_dataset_asset(scope, source_kind="platform_asset", asset_id="a-2")
        prof1 = ds.save_dataset_profile(scope, dataset_id=asset1["dataset_id"], mapping={"time_col": "ts"})

        with pytest.raises(ScopeError) as e1:
            ds.publish_dataset_version(scope, dataset_id=asset1["dataset_id"], dataset_profile_id="dsp-nope")
        assert e1.value.code == "profile_not_found"

        # 用 asset1 的画像去发布 asset2 → 不一致，拒绝
        with pytest.raises(ScopeError) as e2:
            ds.publish_dataset_version(
                scope, dataset_id=asset2["dataset_id"], dataset_profile_id=prof1["dataset_profile_id"]
            )
        assert e2.value.code == "profile_dataset_mismatch"
        assert ds.list_dataset_versions(scope) == []

# @AI_GENERATED: end
