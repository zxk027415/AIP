# @AI_GENERATED
"""数据集目录条目**挂载进项目**的基线（数据集切片第 2c 步）。

要固定的语义：

- 挂载把「平台级条目」变成「项目级三件套」：数据资产 + 画像 + 不可变数据版本；
- 真实数据引用必须可核验地落在 `asset.dataset_ref` 与 `profile.facts.source_ref`；
  **不**改 `dataset_version.artifact_ref` —— 它是项目内 scoped 版本元数据引用，
  property test P-LINEAGE-01（test_prop_lineage.py）要求它以
  `data/slot_datasets/projects/<pid>/` 开头，指向真实数据文件会打破那条不变量；
- 幂等键 = 条目 `content_digest`：重复挂载不产生重复资产 / 版本；
- fail-closed：未知条目、条目引用的分片已消失，都不落任何数据。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

import pytest

pd = pytest.importorskip("pandas")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.pv_projects import router as pv_router  # noqa: E402
from services.pv_projects import catalog as catalog_service  # noqa: E402
from services.pv_projects import datasets as dataset_service  # noqa: E402
from services.pv_projects import repositories as repo  # noqa: E402
from services.pv_projects import source_resolver as src  # noqa: E402
from services.pv_projects.errors import ScopeError  # noqa: E402
from services.pv_projects.scope import ScopeContext  # noqa: E402

MAPPING = {
    "time_col": "time",
    "device_col": "device_id",
    "value_col": "value",
    "label_col": "label",
}
PID = "proj-mount-1"
SNAP_NAME = "snap-pv_day-v1.csv"


@contextmanager
def env() -> Iterator[TestClient]:
    """隔离存储 + 隔离来源根（同根）+ 挂载聚合路由的 TestClient。"""
    tmp = tempfile.mkdtemp(prefix="pvmount_")
    repo.set_storage_base(tmp)
    src.set_source_base(tmp)
    app = FastAPI()
    app.include_router(pv_router)
    try:
        yield TestClient(app)
    finally:
        repo.set_storage_base(None)
        src.set_source_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _snapshot(slot: str = "pv_day", rows: int = 72) -> str:
    base = src.source_base()
    d = base / "data" / "slot_datasets" / slot / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "time": f"2026-01-{i // 24 + 1:02d}T{i % 24:02d}:00:00",
            "site_id": "s1",
            "device_id": "dev-0",
            "branch_id": "1",
            "value": 1.0,
            "i_cal": 0.9,
            "label": "normal",
        }
        for i in range(rows)
    ]
    pd.DataFrame(records).to_csv(d / SNAP_NAME, index=False)
    return f"slot_datasets/{slot}/snapshots/{SNAP_NAME}"


def _publish_entry(slot: str = "pv_day") -> tuple[dict, str]:
    """造快照 + 检测 + 发布，返回 (entry, dataset_ref)。"""
    ref = _snapshot(slot)
    draft = catalog_service.inspect_dataset(
        ref, mapping=MAPPING, label_policy={"granularity": "device_day"}
    )
    return catalog_service.publish_dataset(draft), ref


def _seed_project() -> None:
    repo.register_project_in_index(PID, project_name="Mount 测试项目", solution_id="pv_fault")


# ---------------------------------------------------------------------------
# 1. 挂载产出三件套，真实引用可核验
# ---------------------------------------------------------------------------

def test_mount_creates_asset_profile_version_with_real_ref() -> None:
    with env():
        _seed_project()
        entry, ref = _publish_entry("pv_day")
        scope = ScopeContext.create(PID, "pv_day")

        result = catalog_service.mount_into_project(scope, entry["entry_id"])

        assert result["mounted"] is True
        assert result["idempotent_hit"] is False
        asset = result["dataset_asset"]
        assert asset["source_kind"] == "catalog"
        assert asset["dataset_ref"] == ref
        assert asset["catalog_entry_id"] == entry["entry_id"]

        # 真实数据引用链：画像 facts 的 source_ref 就是那条相对引用。
        profile = dataset_service.get_dataset_profile(scope, result["dataset_profile_id"])
        assert profile["facts"]["source_ref"] == ref
        assert profile["mapping"] == entry["mapping"]

        # 版本不可变 + 符合 P-LINEAGE-01 的 scoped 前缀（**不是**数据文件本身）。
        version = dataset_service.get_dataset_version(scope, result["dataset_version_id"])
        assert version["immutable"] is True
        assert version["artifact_ref"].startswith(f"data/slot_datasets/projects/{PID}/")


# ---------------------------------------------------------------------------
# 2. 幂等：同内容重复挂载不产生重复资产 / 版本
# ---------------------------------------------------------------------------

def test_mount_is_idempotent_by_entry_digest() -> None:
    with env():
        _seed_project()
        entry, _ = _publish_entry("pv_day")
        scope = ScopeContext.create(PID, "pv_day")

        first = catalog_service.mount_into_project(scope, entry["entry_id"])
        second = catalog_service.mount_into_project(scope, entry["entry_id"])

        assert second["idempotent_hit"] is True
        assert second["dataset_version_id"] == first["dataset_version_id"]
        assert len(dataset_service.list_dataset_assets(scope)) == 1
        assert len(dataset_service.list_dataset_versions(scope)) == 1


# ---------------------------------------------------------------------------
# 3. fail-closed：未知条目 / 分片消失
# ---------------------------------------------------------------------------

def test_mount_unknown_entry_fails_closed() -> None:
    with env():
        _seed_project()
        scope = ScopeContext.create(PID, "pv_day")

        with pytest.raises(ScopeError) as exc:
            catalog_service.mount_into_project(scope, "dsc-nope")
        assert exc.value.code == "catalog_entry_not_found"
        assert dataset_service.list_dataset_assets(scope) == []


def test_mount_fails_closed_when_shard_is_gone() -> None:
    """目录是平台资产，随时可能被移动 / 删除 —— 挂载前必须确认分片仍在。"""
    with env():
        _seed_project()
        entry, _ = _publish_entry("pv_day")
        scope = ScopeContext.create(PID, "pv_day")

        os.remove(src.source_base() / "data" / "slot_datasets" / "pv_day" / "snapshots" / SNAP_NAME)

        with pytest.raises(ScopeError) as exc:
            catalog_service.mount_into_project(scope, entry["entry_id"])
        assert exc.value.code == "source_not_found"
        assert dataset_service.list_dataset_assets(scope) == []


# ---------------------------------------------------------------------------
# 4. API 层：项目门禁 + 幂等经 HTTP
# ---------------------------------------------------------------------------

def test_mount_endpoint_requires_registered_project() -> None:
    with env() as c:
        entry, _ = _publish_entry("pv_day")
        r = c.post(
            "/api/pv-projects/proj-does-not-exist/datasets/mount",
            json={"slot": "pv_day", "entry_id": entry["entry_id"]},
        )
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["reason_code"] == "project_not_found"


def test_mount_endpoint_rejects_invalid_slot() -> None:
    with env() as c:
        _seed_project()
        entry, _ = _publish_entry("pv_day")
        r = c.post(
            f"/api/pv-projects/{PID}/datasets/mount",
            json={"slot": "pv_bogus", "entry_id": entry["entry_id"]},
        )
        assert r.status_code == 400, r.text


def test_mount_endpoint_happy_path_and_idempotent() -> None:
    with env() as c:
        _seed_project()
        entry, ref = _publish_entry("pv_day")

        r = c.post(
            f"/api/pv-projects/{PID}/datasets/mount",
            json={"slot": "pv_day", "entry_id": entry["entry_id"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["mounted"] is True
        assert body["dataset_ref"] == ref
        assert body["dataset_version_id"].startswith("dsv-")

        r2 = c.post(
            f"/api/pv-projects/{PID}/datasets/mount",
            json={"slot": "pv_day", "entry_id": entry["entry_id"]},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["idempotent_hit"] is True

        # 挂载后资产可经既有列表端点读到（项目级，不按 slot 分区）。
        listed = c.get(f"/api/pv-projects/{PID}/datasets").json()
        assert len(listed["assets"]) == 1
        assert listed["assets"][0]["catalog_entry_id"] == entry["entry_id"]


def test_create_project_mounts_catalog_entry_and_overview_shows_dataset() -> None:
    """创建项目时先选可挂载数据集：不要求用户先选路径。"""
    with env() as c:
        entry, ref = _publish_entry("pv_day")
        r = c.post(
            "/api/pv-projects",
            json={
                "project_name": "先数据集后路径",
                "solution_id": "pv_fault",
                "catalog_entry_id": entry["entry_id"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["empty_lifecycle"] is False
        assert body["mount_slot"] == "pv_day"
        assert body["mounted"]["dataset_ref"] == ref
        pid = body["project_id"]

        ov = c.get(f"/api/pv-projects/{pid}/overview").json()
        assert ov["mounted_datasets"], ov
        assert ov["mounted_datasets"][0]["dataset_ref"] == ref
        assert "pv_day" in ov["mounted_datasets"][0]["applicable_slots"]
        assert "pv_day" in ov["path_templates"]
        assert ov["enabled_slots"] == ["pv_day"]


# @AI_GENERATED: end
