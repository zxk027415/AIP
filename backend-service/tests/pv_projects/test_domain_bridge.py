# @AI_GENERATED
"""领域桥接线测试（**真实依赖，非 mock**）：项目侧候选 → 对应 slot 的治理存储。

用户意图是「模型部署 / 精度运营 / 工作流模板 / 项目 互通、互相显示」。本组固定其中一根线：
项目候选必须落到「模型部署」页**真正读**的三处，缺一页面就看不到：

1. 统一执行历史（`slot_governance` 的 provenance 校验按它查找）——`data/execution_history/`
2. 候选池（页面「已登记模型（N）— 生产 / 候选」读它）——`data/slot_governance/{slot}/model_candidates.json`
3. 模型登记 challenger ——`data/slot_governance/{slot}/registry.json`

以及边界：非产品 slot 不处理、缺幂等键跳过、桥出错不阻断项目侧登记。
红线：绝不写 champion / production_path。

测试把三处存储都重定向到 tmp，避免污染真实数据。
"""

from __future__ import annotations

import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import services.execution_history.store as eh_store  # noqa: E402
import services.slot_governance.model_candidates as mc_mod  # noqa: E402
import services.slot_governance.registry as registry_mod  # noqa: E402
from services.iterative_labeling.pv_candidate_bridge import PvFaultCandidateBridge  # noqa: E402
from services.pv_projects import ScopeContext  # noqa: E402
from services.pv_projects import domain_bridge as bridge_mod  # noqa: E402
from services.pv_projects import repositories as repo  # noqa: E402
from services.pv_projects.stores import executions as proj_executions  # noqa: E402

PID = "proj-bridge-1"
SLOT = "pv_tsc"
EXEC = "exec-bridge-1"
WF = "pwf-bridge-1"


@contextmanager
def env() -> Iterator[Path]:
    """隔离 pv_projects 存储 + 三处治理存储（均为模块常量，只能 monkeypatch）。"""
    tmp = Path(tempfile.mkdtemp(prefix="pvbridge_"))
    repo.set_storage_base(str(tmp))
    saved = (
        registry_mod._DATA_DIR,
        mc_mod._DATA_DIR,
        eh_store._EXEC_DIR,
        eh_store._BY_ID_DIR,
    )
    registry_mod._DATA_DIR = tmp / "slot_governance"
    mc_mod._DATA_DIR = tmp / "slot_governance"
    eh_store._EXEC_DIR = tmp / "execution_history"
    eh_store._BY_ID_DIR = tmp / "execution_history" / "by_id"
    try:
        repo.register_project_in_index(PID, project_name="桥测试项目", solution_id="pv_fault")
        yield tmp
    finally:
        (
            registry_mod._DATA_DIR,
            mc_mod._DATA_DIR,
            eh_store._EXEC_DIR,
            eh_store._BY_ID_DIR,
        ) = saved
        repo.set_storage_base(None)
        bridge_mod.set_domain_bridge(None)
        shutil.rmtree(tmp, ignore_errors=True)


def _seed_execution(*, governance_eligible: bool = True, status: str = "success") -> None:
    scope = ScopeContext.create(PID, SLOT, require_slot=True, allow_legacy=False)
    proj_executions.append(
        scope,
        {
            "execution_id": EXEC,
            "project_workflow_id": WF,
            "slot": SLOT,
            "status": status,
            "governance_eligible": governance_eligible,
            "run_mode": "training" if governance_eligible else "experiment",
            "run_domain": "project",
            "started_at": "2026-09-14T00:00:00+00:00",
            "finished_at": "2026-09-14T00:01:00+00:00",
        },
    )


def _candidate(**over: Any) -> dict:
    base = {
        "model_candidate_id": "cand-bridge-1",
        "model_artifact_ref": "data/models/tsc/m1",
        "source_execution_id": EXEC,
        "source_workflow_id": WF,
        "governance_eligible": True,
        "provenance_gaps": [],
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# 边界的两侧
# ---------------------------------------------------------------------------

def test_no_bridge_is_noop() -> None:
    with env() as tmp:
        r = bridge_mod.sync_candidate_to_domain(project_id=PID, slot=SLOT, candidate=_candidate())
        assert r == {"synced": False, "reason": "no_bridge"}
        assert not (tmp / "slot_governance").exists()


def test_non_product_slot_is_not_handled() -> None:
    with env() as tmp:
        bridge_mod.set_domain_bridge(PvFaultCandidateBridge())
        for slot in ("load_forecast", "benchmark_nasa_smap_msl"):
            r = bridge_mod.sync_candidate_to_domain(project_id=PID, slot=slot, candidate=_candidate())
            assert r == {"synced": False, "reason": "not_handled"}, (slot, r)
        assert not (tmp / "slot_governance").exists()


def test_missing_id_is_skipped_not_reported_as_synced() -> None:
    with env() as tmp:
        bridge_mod.set_domain_bridge(PvFaultCandidateBridge())
        r = bridge_mod.sync_candidate_to_domain(
            project_id=PID, slot=SLOT, candidate=_candidate(model_candidate_id="")
        )
        assert r["synced"] is False and r["reason"] == "skipped", r
        assert not (tmp / "slot_governance").exists()


def test_bridge_error_does_not_propagate() -> None:
    class Boom:
        def sync_candidate(self, *, project_id: str, slot: str, candidate: dict) -> None:
            raise RuntimeError("registry down")

    with env():
        bridge_mod.set_domain_bridge(Boom())
        r = bridge_mod.sync_candidate_to_domain(project_id=PID, slot=SLOT, candidate=_candidate())
        assert r["synced"] is False and r["reason"] == "error"
        assert "registry down" in r["error"]


# ---------------------------------------------------------------------------
# 完整路径（真实依赖）：三处存储都要落
# ---------------------------------------------------------------------------

def test_full_path_writes_execution_history_pool_and_registry() -> None:
    with env() as tmp:
        _seed_execution()
        bridge_mod.set_domain_bridge(PvFaultCandidateBridge())

        r = bridge_mod.sync_candidate_to_domain(project_id=PID, slot=SLOT, candidate=_candidate())

        assert r["synced"] is True, r
        assert r["registry_slot"] == SLOT
        assert r["pool_registered"] is True, r

        # 1) 统一执行历史（provenance 校验的数据源）
        hist = tmp / "execution_history" / "by_id" / f"{EXEC}.json"
        assert hist.exists(), "执行必须被镜像进统一历史，否则候选进不了池"
        assert json.loads(hist.read_text(encoding="utf-8"))["status"] == "success"

        # 2) 候选池（页面「已登记模型（N）」读它）
        pool_path = tmp / "slot_governance" / SLOT / "model_candidates.json"
        assert pool_path.exists()
        pool = json.loads(pool_path.read_text(encoding="utf-8"))["candidates"]
        assert any(c.get("model_artifact_ref") == "data/models/tsc/m1" for c in pool), pool

        # 3) 候选登记**只进池**，不授予挑战者身份（考察通过才升级 —— 「一套逻辑」的那道门）
        reg_path = tmp / "slot_governance" / SLOT / "registry.json"
        assert (
            not reg_path.exists()
            or not (json.loads(reg_path.read_text(encoding="utf-8")).get("challenger"))
        ), "候选登记阶段不该出现 challenger（只有复验通过才升级）"


def test_non_governable_execution_cannot_enter_pool() -> None:
    """实验（非可治理）执行不得进候选池 —— provenance 校验会拒，桥要如实回显而非假装成功。"""
    with env() as tmp:
        _seed_execution(governance_eligible=False)
        bridge_mod.set_domain_bridge(PvFaultCandidateBridge())

        r = bridge_mod.sync_candidate_to_domain(project_id=PID, slot=SLOT, candidate=_candidate())

        assert r["synced"] is True, r
        assert r.get("pool_registered") is False, r
        assert "governance_not_eligible" in str(r.get("pool_error") or ""), r
        # 池与 registry 都不该被写
        assert not (tmp / "slot_governance" / SLOT / "model_candidates.json").exists()
        assert not (tmp / "slot_governance" / SLOT / "registry.json").exists()


def test_three_paths_never_cross_into_each_other() -> None:
    """三条路径各写自己的 slot —— 串台会让「模型部署」页张冠李戴。"""
    with env() as tmp:
        bridge_mod.set_domain_bridge(PvFaultCandidateBridge())
        for slot in ("pv_day", "pv_point", "pv_tsc"):
            scope = ScopeContext.create(PID, slot, require_slot=True, allow_legacy=False)
            proj_executions.append(
                scope,
                {
                    "execution_id": f"exec-{slot}",
                    "project_workflow_id": f"pwf-{slot}",
                    "slot": slot,
                    "status": "success",
                    "governance_eligible": True,
                    "run_mode": "training",
                    "run_domain": "project",
                },
            )
            r = bridge_mod.sync_candidate_to_domain(
                project_id=PID,
                slot=slot,
                candidate=_candidate(
                    model_candidate_id=f"cand-{slot}",
                    model_artifact_ref=f"data/models/{slot}/m",
                    source_execution_id=f"exec-{slot}",
                    source_workflow_id=f"pwf-{slot}",
                ),
            )
            assert r["synced"] is True and r["registry_slot"] == slot, (slot, r)

        for slot in ("pv_day", "pv_point", "pv_tsc"):
            pool = json.loads(
                (tmp / "slot_governance" / slot / "model_candidates.json").read_text(encoding="utf-8")
            )["candidates"]
            assert any(c.get("model_artifact_ref") == f"data/models/{slot}/m" for c in pool), slot


# ---------------------------------------------------------------------------
# 考察通过 → 升级挑战者（「一套逻辑」的收口）
# ---------------------------------------------------------------------------

def test_verification_passed_upgrades_candidate_to_challenger() -> None:
    """候选只有**考察（复验）通过**后才成为挑战者，去和生产竞争。"""
    with env() as tmp:
        _seed_execution()
        bridge_mod.set_domain_bridge(PvFaultCandidateBridge())

        entry = bridge_mod.sync_candidate_to_domain(project_id=PID, slot=SLOT, candidate=_candidate())
        assert entry["pool_registered"] is True, entry
        pool_id = entry["pool_candidate_id"]

        # 复验通过前：registry 里没有 challenger
        reg_path = tmp / "slot_governance" / SLOT / "registry.json"
        assert not reg_path.exists() or not json.loads(
            reg_path.read_text(encoding="utf-8")
        ).get("challenger")

        cand = _candidate()
        cand["domain_sync"] = {"pool_candidate_id": pool_id}
        up = bridge_mod.sync_verification_passed_to_domain(
            project_id=PID, slot=SLOT, candidate=cand, verification={"verification_id": "ver-x"}
        )
        assert up["synced"] is True, up

        reg = json.loads(reg_path.read_text(encoding="utf-8"))
        ch = reg.get("challenger") or {}
        assert ch.get("challenger_model_candidate_id") == pool_id
        assert ch.get("challenger_model_artifact_ref") == "data/models/tsc/m1"
        # 红线：升级挑战者不得直接改写生产身份
        assert reg.get("champion") is None
        assert not reg.get("production_path")


def test_verification_upgrade_skipped_when_not_in_pool() -> None:
    """复验通过但候选不在槽位池里 → 不臆造 ID，如实跳过。"""
    with env() as tmp:
        bridge_mod.set_domain_bridge(PvFaultCandidateBridge())
        up = bridge_mod.sync_verification_passed_to_domain(
            project_id=PID,
            slot=SLOT,
            candidate=_candidate(model_candidate_id="cand-x"),  # 无 domain_sync
            verification={"verification_id": "ver-x"},
        )
        assert up["synced"] is False and up["reason"] == "skipped", up
        assert not (tmp / "slot_governance").exists()


# @AI_GENERATED: end
