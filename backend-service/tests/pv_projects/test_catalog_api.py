# @AI_GENERATED
"""数据集目录 API 的路由层基线（数据集切片第 2b 收尾）。

服务层语义（`inspect` / `publish` / `list` / 幂等 / 适用路径）已由 `test_dataset_catalog.py`
覆盖。本文件只固定**路由层新增行为**：

- 两段固定路径 `/catalog` 不被动态段 `/{project_id}/…` 吃掉（否则会被当成 project_id）；
- `ScopeError` 在 HTTP 层映射成设计 §26.5 的统一错误响应（`reason_code` 可读）；
- 幂等与「检测不落盘」经 HTTP 也成立（不是只有服务层成立）。

`/catalog/entries/{entry_id}` 刻意用三段，避免与两段的 `/catalog/available-sources` 争匹配。
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
from services.pv_projects import repositories as repo  # noqa: E402
from services.pv_projects import source_resolver as src  # noqa: E402

MAPPING = {
    "time_col": "time",
    "device_col": "device_id",
    "value_col": "value",
    "label_col": "label",
}


@contextmanager
def client() -> Iterator[TestClient]:
    """隔离存储 + 隔离来源根 + 挂载聚合 pv_projects 路由的 TestClient。

    目录是平台级的：这里**不**登记项目，正是为了证明 `/catalog` 不需要 project scope。
    """
    tmp = tempfile.mkdtemp(prefix="pvcatalog_api_")
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


def _snapshot(slot: str = "pv_day", rows: int = 72, *, device: str = "dev-0") -> str:
    """在 `data/slot_datasets/<slot>/snapshots/` 下写一个冻结快照，返回其相对引用。

    注意：路径相对于 `src.source_base()`（测试里被重定向到 tmp），不是 backend-service。
    """
    base = src.source_base()
    d = base / "data" / "slot_datasets" / slot / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    name = f"snap-{slot}-v1.csv"
    records = []
    for i in range(rows):
        day = i // 24 + 1
        records.append(
            {
                "time": f"2026-01-{day:02d}T{i % 24:02d}:00:00",
                "site_id": "s1",
                "device_id": device,
                "branch_id": "1",
                "value": 1.0,
                "i_cal": 0.9,
                "label": "normal",
            }
        )
    pd.DataFrame(records).to_csv(d / name, index=False)
    return f"slot_datasets/{slot}/snapshots/{name}"


# ---------------------------------------------------------------------------
# 1. 路由可达性：固定段不被动态段吃掉
# ---------------------------------------------------------------------------

def test_catalog_path_is_not_swallowed_by_dynamic_segment() -> None:
    """`GET /api/pv-projects/catalog` 必须命中目录路由，而不是被解析成 project_id="catalog"。"""
    with client() as c:
        r = c.get("/api/pv-projects/catalog")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"entries": [], "total": 0}

        # 若被动态段吃掉，这里会是 `project_not_found`（404）而非目录响应。
        assert "reason_code" not in r.text or "project_not_found" not in r.text


def test_available_sources_lists_path_cumulative_snapshots() -> None:
    with client() as c:
        _snapshot("pv_day", 72)
        _snapshot("pv_point", 24, device="dev-point")
        _snapshot("pv_tsc", 24, device="dev-tsc")

        r = c.get("/api/pv-projects/catalog/available-sources")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["path_cumulative_count"] == 3
        slots = {item["origin_slot"] for item in body["path_cumulative"]}
        assert slots == {"pv_day", "pv_point", "pv_tsc"}


# ---------------------------------------------------------------------------
# 2. 检测：只读不落盘
# ---------------------------------------------------------------------------

def test_inspect_returns_facts_without_persisting() -> None:
    with client() as c:
        ref = _snapshot("pv_day", 72)
        r = c.post(
            "/api/pv-projects/catalog/inspect",
            json={"dataset_ref": ref, "mapping": MAPPING, "label_policy": {"granularity": "device_day"}},
        )
        assert r.status_code == 200, r.text
        draft = r.json()
        assert draft["facts"]["row_count"] == 72
        assert draft["facts"]["facts_source"] == "computed_from_file"
        assert set(draft["applicable_paths"]) == {"pv_day", "pv_point", "pv_tsc"}

        # 只读：检测不产生任何目录条目。
        assert c.get("/api/pv-projects/catalog").json()["total"] == 0


# ---------------------------------------------------------------------------
# 3. 发布：经 HTTP 也幂等，且可列表 / 取详情
# ---------------------------------------------------------------------------

def test_publish_over_http_is_idempotent_and_listable() -> None:
    with client() as c:
        ref = _snapshot("pv_day", 72)
        payload = {
            "dataset_ref": ref,
            "mapping": MAPPING,
            "label_policy": {"granularity": "device_day"},
            "display_name": "PV Day 累计训练集",
        }

        first = c.post("/api/pv-projects/catalog/publish", json=payload)
        assert first.status_code == 200, first.text
        entry = first.json()
        assert entry["entry_id"].startswith("dsc-")
        assert entry["immutable"] is True
        assert entry["idempotent_hit"] is False

        again = c.post("/api/pv-projects/catalog/publish", json=payload).json()
        assert again["entry_id"] == entry["entry_id"]
        assert again["idempotent_hit"] is True

        listing = c.get("/api/pv-projects/catalog").json()
        assert listing["total"] == 1

        detail = c.get(f"/api/pv-projects/catalog/entries/{entry['entry_id']}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["dataset_ref"] == ref


# ---------------------------------------------------------------------------
# 4. 错误映射：ScopeError → 统一错误响应
# ---------------------------------------------------------------------------

def test_incomplete_mapping_maps_to_400_with_reason_code() -> None:
    with client() as c:
        ref = _snapshot("pv_day", 24)
        r = c.post(
            "/api/pv-projects/catalog/inspect",
            json={"dataset_ref": ref, "mapping": {"time_col": "time", "device_col": "device_id"}},
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["reason_code"] == "incomplete_mapping"


def test_unknown_dataset_ref_maps_to_400_with_reason_code() -> None:
    with client() as c:
        r = c.post(
            "/api/pv-projects/catalog/inspect",
            json={"dataset_ref": "uploads/does-not-exist.csv", "mapping": MAPPING},
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["reason_code"] == "source_not_found"


def test_absolute_path_is_rejected() -> None:
    """红线：目录不接受机器绝对路径（source_resolver 的白名单语义）。"""
    with client() as c:
        r = c.post(
            "/api/pv-projects/catalog/inspect",
            json={"dataset_ref": "/etc/passwd", "mapping": MAPPING},
        )
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["reason_code"] == "absolute_path_forbidden"


def test_unknown_entry_detail_maps_to_400() -> None:
    with client() as c:
        r = c.get("/api/pv-projects/catalog/entries/dsc-nope")
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["reason_code"] == "catalog_entry_not_found"


# @AI_GENERATED: end
