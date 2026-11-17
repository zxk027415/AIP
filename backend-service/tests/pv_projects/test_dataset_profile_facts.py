# @AI_GENERATED
"""画像 facts 的服务端计算（P4：把 facts 接进主链路）。

要固定的语义（这是「readiness 恒为 experiment_only」的病根）：

- `save_dataset_profile(facts=None)` 时**服务端从真实文件算** facts —— 此前 facts 完全由客户端
  传入、后端从不计算，而生产路径没有任何代码会写 `sufficient_coverage`，于是质量检测在服务端
  实际不存在，每份数据都停在 experiment_only；
- 算不出（连接器 / 平台资产 / 文件缺失）**降级而非抛错**，且降级原因如实落进
  `facts_unavailable_reason`（不静默吞）；
- 显式传入的 facts 仍作为覆盖（向后兼容）；
- 覆盖足够时 readiness 能真正到达 `ready` —— 修复前这条路径不可达。

source_ref 形式差异是本组的重点：资产里存的是**存储相对引用**（`data/uploads/x.csv`），
而 `compute_dataset_facts` 只认**来源根别名**（`uploads/x.csv`），靠 `to_source_alias_ref` 桥接。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

import pytest

pd = pytest.importorskip("pandas")

from services.pv_projects import ScopeContext  # noqa: E402
from services.pv_projects import datasets as ds  # noqa: E402
from services.pv_projects import readiness as readiness_service  # noqa: E402
from services.pv_projects import repositories as repo  # noqa: E402
from services.pv_projects import source_resolver as src  # noqa: E402

MAPPING = {
    "time_col": "time",
    "device_col": "device_id",
    "value_col": "value",
    "label_col": "label",
}
PID = "proj-facts-1"
OK_REF = "data/uploads/pv_ok.csv"  # 资产里存的形态（存储相对引用）


@contextmanager
def env() -> Iterator[str]:
    tmp = tempfile.mkdtemp(prefix="pvfacts_")
    repo.set_storage_base(tmp)
    src.set_source_base(tmp)
    try:
        yield tmp
    finally:
        repo.set_storage_base(None)
        src.set_source_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _write_ok_csv(tmp: str, *, days: int = 3, devices: int = 2) -> None:
    """写一份**覆盖足够**的数据：连续 days 天、devices 台设备、5 分钟采样。

    预期：date_coverage_ratio=1.0（连续）、device_count=devices、sampling_completeness=1.0。
    """
    import os

    d = os.path.join(tmp, "data", "uploads")
    os.makedirs(d, exist_ok=True)
    rows = []
    for dev in range(devices):
        ts = pd.date_range("2026-01-01", periods=days * 288, freq="300s")
        for t in ts:
            rows.append(
                {
                    "time": t.isoformat(),
                    "site_id": "s1",
                    "device_id": f"dev-{dev}",
                    "branch_id": "1",
                    "value": 1.0,
                    "i_cal": 0.9,
                    "label": f"l-{t.date()}",
                }
            )
    pd.DataFrame(rows).to_csv(os.path.join(d, "pv_ok.csv"), index=False)


def _register_upload(scope: ScopeContext, ref: str = OK_REF) -> dict:
    return ds.register_dataset_asset(
        scope, source_kind="upload", file_name="pv_ok.csv", upload_ref=ref
    )


# ---------------------------------------------------------------------------
# 1. 服务端计算 facts
# ---------------------------------------------------------------------------

def test_profile_computes_facts_server_side_from_real_file() -> None:
    with env() as tmp:
        _write_ok_csv(tmp)
        scope = ScopeContext.create(PID)
        asset = _register_upload(scope)

        profile = ds.save_dataset_profile(
            scope, dataset_id=asset["dataset_id"], mapping=MAPPING, label_policy={"granularity": "device_day"}
        )

        assert profile["facts_origin"] == "computed_from_file"
        assert profile["facts_unavailable_reason"] is None
        assert profile["facts"]["row_count"] == 3 * 288 * 2
        assert profile["facts"]["device_count"] == 2
        assert profile["facts"]["distinct_dates"] == 3
        assert profile["facts"]["sufficient_coverage"] is True
        # 桥接证据：fact 里的 source_ref 是归一化后的别名形式
        assert profile["facts"]["source_ref"] == "uploads/pv_ok.csv"


def test_explicit_facts_still_override() -> None:
    with env() as tmp:
        _write_ok_csv(tmp)
        scope = ScopeContext.create(PID)
        asset = _register_upload(scope)

        profile = ds.save_dataset_profile(
            scope,
            dataset_id=asset["dataset_id"],
            mapping=MAPPING,
            facts={"row_count": 42, "sufficient_coverage": False},
        )
        assert profile["facts_origin"] == "client_provided"
        assert profile["facts"] == {"row_count": 42, "sufficient_coverage": False}


# ---------------------------------------------------------------------------
# 2. 算不出时降级而非抛错
# ---------------------------------------------------------------------------

def test_profile_degrades_when_source_is_not_a_local_dataset() -> None:
    with env():
        scope = ScopeContext.create(PID)
        asset = ds.register_dataset_asset(scope, source_kind="platform_asset", asset_id="asset-1")

        profile = ds.save_dataset_profile(scope, dataset_id=asset["dataset_id"], mapping=MAPPING)

        assert profile["facts"] == {}
        assert profile["facts_origin"] == "unavailable"
        assert profile["facts_unavailable_reason"] == "source_not_a_local_dataset"


def test_profile_degrades_when_file_is_missing() -> None:
    with env():
        scope = ScopeContext.create(PID)
        asset = _register_upload(scope, "data/uploads/does-not-exist.csv")

        profile = ds.save_dataset_profile(scope, dataset_id=asset["dataset_id"], mapping=MAPPING)

        assert profile["facts"] == {}
        assert profile["facts_unavailable_reason"] == "source_not_found"


# ---------------------------------------------------------------------------
# 3. 病根修复：readiness 能真正到达 ready
# ---------------------------------------------------------------------------

def test_readiness_reaches_ready_with_sufficient_coverage() -> None:
    """**核心用例**：修复前这条路径不可达（facts 永远为空 → 永远 experiment_only）。"""
    with env() as tmp:
        _write_ok_csv(tmp)
        scope = ScopeContext.create(PID)
        asset = _register_upload(scope)
        profile = ds.save_dataset_profile(
            scope, dataset_id=asset["dataset_id"], mapping=MAPPING, label_policy={"granularity": "device_day"}
        )
        version = ds.publish_dataset_version(
            scope, dataset_id=asset["dataset_id"], dataset_profile_id=profile["dataset_profile_id"]
        )

        result = readiness_service.evaluate_all_paths(scope, version["dataset_version_id"])
        by_slot = {p["slot"]: p for p in result["paths"]}

        # 覆盖足够 + 设备日粒度 → pv_day 应判 ready（不再被 coverage_facts_unconfirmed 卡住）
        assert by_slot["pv_day"]["status"] == "ready", by_slot["pv_day"]
        assert by_slot["pv_day"]["primary_blocker"] is None
        assert "validation" in by_slot["pv_day"]["allowed_run_modes"]
        # 粒度不符的路径仍按口径拒绝（覆盖足够≠口径适用）
        assert by_slot["pv_point"]["status"] == "needs_labels"


def test_readiness_stays_experiment_only_without_local_file() -> None:
    """没有本地文件 → 诚实降级为 experiment_only，并给出可解释的 blocker。"""
    with env():
        scope = ScopeContext.create(PID)
        asset = ds.register_dataset_asset(scope, source_kind="connector", connector_id="conn-1")
        profile = ds.save_dataset_profile(
            scope, dataset_id=asset["dataset_id"], mapping=MAPPING, label_policy={"granularity": "device_day"}
        )
        version = ds.publish_dataset_version(
            scope, dataset_id=asset["dataset_id"], dataset_profile_id=profile["dataset_profile_id"]
        )

        result = readiness_service.evaluate_all_paths(scope, version["dataset_version_id"])
        by_slot = {p["slot"]: p for p in result["paths"]}
        assert by_slot["pv_day"]["status"] == "experiment_only"
        assert by_slot["pv_day"]["primary_blocker"] == "coverage_facts_unconfirmed"


# ---------------------------------------------------------------------------
# 4. 真实预览
# ---------------------------------------------------------------------------

def test_preview_returns_real_columns_and_rows() -> None:
    with env() as tmp:
        _write_ok_csv(tmp, days=1)
        scope = ScopeContext.create(PID)
        asset = _register_upload(scope)

        preview = ds.get_preview(scope, asset["dataset_id"], row_limit=5)

        assert preview["preview_available"] is True
        assert [c["name"] for c in preview["columns"]][:3] == ["time", "site_id", "device_id"]
        assert len(preview["preview_rows"]) == 5
        assert preview["previewed_from"] == "pv_ok.csv"
        assert preview["row_limit"] == 5


def test_preview_unavailable_for_connector() -> None:
    with env():
        scope = ScopeContext.create(PID)
        asset = ds.register_dataset_asset(scope, source_kind="connector", connector_id="conn-1")

        preview = ds.get_preview(scope, asset["dataset_id"])

        assert preview["preview_available"] is False
        assert preview["preview_rows"] == []
        assert "物化" in preview["note"]


def test_readiness_insufficient_data_when_facts_show_no_rows() -> None:
    """facts 已算出且显示零可用数据 → insufficient_data。

    此前 readiness 只会产出 needs_mapping / needs_labels / experiment_only / ready 四态，
    `insufficient_data` 与 `unsupported` 在 `_ALLOWED_RUN_MODES` / `_NEXT_ACTION` 里有定义却
    **从不被赋值**（死状态）——这条用例固定前者已可达。
    """
    with env() as tmp:
        # 只有表头的 CSV：服务端能解析但零行 → facts 算出 row_count=0
        import os

        d = os.path.join(tmp, "data", "uploads")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "pv_empty.csv"), "w", encoding="utf-8") as fh:
            fh.write("time,site_id,device_id,branch_id,value,i_cal,label\n")

        scope = ScopeContext.create(PID)
        asset = _register_upload(scope, "data/uploads/pv_empty.csv")
        profile = ds.save_dataset_profile(
            scope, dataset_id=asset["dataset_id"], mapping=MAPPING, label_policy={"granularity": "device_day"}
        )
        assert profile["facts"]["facts_source"] == "computed_from_file"
        assert profile["facts"]["row_count"] == 0

        version = ds.publish_dataset_version(
            scope, dataset_id=asset["dataset_id"], dataset_profile_id=profile["dataset_profile_id"]
        )
        result = readiness_service.evaluate_all_paths(scope, version["dataset_version_id"])
        by_slot = {p["slot"]: p for p in result["paths"]}

        assert by_slot["pv_day"]["status"] == "insufficient_data", by_slot["pv_day"]
        assert by_slot["pv_day"]["primary_blocker"] == "no_usable_rows"
        assert by_slot["pv_day"]["next_action"] == "补充数据覆盖（日期 / 设备 / 类别 / 采样）"


def test_missing_facts_is_not_mistaken_for_insufficient_data() -> None:
    """没检测过（facts 为空）≠ 数据不足 —— 不能把「没检测」误报成「数据不足」。"""
    with env():
        scope = ScopeContext.create(PID)
        asset = ds.register_dataset_asset(scope, source_kind="connector", connector_id="conn-1")
        profile = ds.save_dataset_profile(
            scope, dataset_id=asset["dataset_id"], mapping=MAPPING, label_policy={"granularity": "device_day"}
        )
        version = ds.publish_dataset_version(
            scope, dataset_id=asset["dataset_id"], dataset_profile_id=profile["dataset_profile_id"]
        )

        result = readiness_service.evaluate_all_paths(scope, version["dataset_version_id"])
        by_slot = {p["slot"]: p for p in result["paths"]}
        assert by_slot["pv_day"]["status"] == "experiment_only"


# @AI_GENERATED: end
