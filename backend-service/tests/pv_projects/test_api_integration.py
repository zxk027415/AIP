# @AI_GENERATED
"""可选 API 集成测试（任务 3.3 / 5.3 / 2.8 的 API 部分）。

用 FastAPI TestClient 走 scoped 路由的 happy path + 关键负向，断言：
- scope 回显一致；相对引用；validation 执行非可治理；无生产写入被触发。
- 组件级（React）测试需要前端测试运行器（vitest/jest），本项目未配置，故此处只覆盖 API 层，
  组件测试如实标注为环境未接入。
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from typing import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.pv_projects import router as pv_router
from services.pv_projects import repositories as repo


PID = "proj-api-1"


@contextmanager
def client(*, seed_project: bool = True) -> Iterator[TestClient]:
    """隔离存储 + 挂载 pv_projects 路由的 TestClient。

    默认先把 `PID` **真实登记进项目索引**：P1-5 后 `build_scope` 默认要求项目已登记，
    夹具必须建模现实——旧夹具直接在未登记项目上写数据，那正是 P1-5 要堵的洞。
    需要验证"未登记项目被拒"时传 `seed_project=False`。
    """
    tmp = tempfile.mkdtemp(prefix="pvproj_api_")
    repo.set_storage_base(tmp)
    app = FastAPI()
    app.include_router(pv_router)
    try:
        if seed_project:
            repo.register_project_in_index(
                PID, project_name="API 测试项目", solution_id="pv_fault"
            )
        yield TestClient(app)
    finally:
        repo.set_storage_base(None)
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 2.8 数据接入（API 部分）
# ---------------------------------------------------------------------------

def test_unknown_project_write_is_rejected() -> None:
    """P1-5：格式合法但**未登记**的 project_id 不得写出孤儿数据。"""
    with client(seed_project=False) as c:
        r = c.post(
            "/api/pv-projects/proj-does-not-exist/datasets",
            json={"source_kind": "platform_asset", "asset_id": "asset-1"},
        )
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["reason_code"] == "project_not_found"

        # 总览同样 404，而不是 200 + 三条空路径（读路径也 fail-closed）。
        r2 = c.get("/api/pv-projects/proj-does-not-exist/overview")
        assert r2.status_code == 404, r2.text

        # 确认没有落任何数据到该孤儿 scope 下。
        from services.pv_projects import ScopeContext as _Scope
        from services.pv_projects.stores import dataset_assets as _assets

        orphan = _Scope.create("proj-does-not-exist", require_slot=False, allow_legacy=False)
        assert _assets.list(orphan) == []


def test_onboarding_register_and_list_dataset_no_secrets() -> None:
    with client() as c:
        r = c.post(
            f"/api/pv-projects/{PID}/datasets",
            json={"source_kind": "connector", "connector_id": "conn-1", "logical_object": "pv.readings",
                  "logical_description": "只读逻辑引用"},
        )
        assert r.status_code == 200, r.text
        asset = r.json()
        assert asset["project_id"] == PID
        # 不落任何凭据字段。
        blob = r.text.lower()
        assert "password" not in blob and "token" not in blob and "secret" not in blob

        lst = c.get(f"/api/pv-projects/{PID}/datasets").json()
        assert lst["project_id"] == PID
        assert any(a["dataset_id"] == asset["dataset_id"] for a in lst["assets"])


def test_onboarding_rejects_machine_absolute_upload_ref() -> None:
    with client() as c:
        r = c.post(
            f"/api/pv-projects/{PID}/datasets",
            json={"source_kind": "upload", "file_name": "x.parquet", "upload_ref": "C:\\\\Users\\\\zxk\\\\x.parquet"},
        )
        # 绝对路径应被拒绝（4xx）。
        assert r.status_code >= 400


# ---------------------------------------------------------------------------
# 3.3 运行中心（API 部分）
# ---------------------------------------------------------------------------

def _create_blank_workflow(c: TestClient, slot: str = "pv_tsc") -> str:
    r = c.post(
        f"/api/pv-projects/{PID}/project-workflows",
        json={"slot": slot, "mode": "blank", "name": "空白工作流"},
    )
    assert r.status_code == 200, r.text
    return r.json()["project_workflow_id"]


def _publish_dataset_version(c: TestClient) -> str:
    """走 API 建数据资产 → 画像 → 发布不可变版本，返回 dataset_version_id。"""
    r = c.post(
        f"/api/pv-projects/{PID}/datasets",
        json={"source_kind": "upload", "file_name": "api-e2e.csv",
              "upload_ref": "data/uploads/api-e2e.csv"},
    )
    assert r.status_code == 200, r.text
    asset_id = r.json()["dataset_id"]

    r = c.post(
        f"/api/pv-projects/{PID}/datasets/{asset_id}/profile",
        json={"mapping": {"time_col": "ts", "device_col": "dev", "value_col": "val"}},
    )
    assert r.status_code == 200, r.text
    profile_id = r.json()["dataset_profile_id"]

    r = c.post(
        f"/api/pv-projects/{PID}/dataset-versions/publish",
        json={"dataset_id": asset_id, "dataset_profile_id": profile_id},
    )
    assert r.status_code == 200, r.text
    return r.json()["dataset_version_id"]


def _create_runnable_workflow(c: TestClient, *, kind: str = "training",
                              dataset_version_id: str = "", slot: str = "pv_tsc") -> str:
    """建一个**能过预检**的项目工作流：带 load 节点 + 绑定数据版本。

    P0-1 后执行前必过 preflight；空画布、未绑数据版本都会 blocked，
    因此执行类用例必须用这个 helper 而不是空白工作流。
    """
    r = c.post(
        f"/api/pv-projects/{PID}/project-workflows",
        json={
            "slot": slot, "mode": "blank", "name": "可运行工作流", "workflow_kind": kind,
            "dataset_version_id": dataset_version_id or None,
            "nodes": [{"id": "n1", "data": {"config": {"functionId": "load_csv"}}}],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["project_workflow_id"]


def test_run_center_validation_execution_is_non_governable() -> None:
    """validation 执行恒非可治理。

    P0-1 后：执行前必须过 preflight（需带 load 节点的、绑定了数据版本的工作流），
    且 run_mode 必须与**工作流用途**合同一致 → validation 只能跑在 labeling 工作流上。
    """
    with client() as c:
        vid = _publish_dataset_version(c)
        wf = _create_runnable_workflow(c, kind="labeling", dataset_version_id=vid)

        pre = c.post(f"/api/pv-projects/{PID}/preflight",
                     json={"slot": "pv_tsc", "project_workflow_id": wf}).json()
        assert pre["overall"] != "blocked", pre  # 夹具前提：确实可运行

        r = c.post(
            f"/api/pv-projects/{PID}/executions",
            json={"slot": "pv_tsc", "project_workflow_id": wf, "run_mode": "validation", "run_domain": "project"},
        )
        assert r.status_code == 200, r.text
        ex = r.json()
        assert ex["project_id"] == PID and ex["slot"] == "pv_tsc"
        assert ex["governance_eligible"] is False  # validation 恒非可治理
        assert ex["workflow_kind"] == "labeling"  # 工作流血缘已固化进执行记录

        lst = c.get(f"/api/pv-projects/{PID}/executions", params={"slot": "pv_tsc"}).json()
        assert any(e["execution_id"] == ex["execution_id"] for e in lst["executions"])


def test_run_center_rejects_execution_for_unknown_workflow() -> None:
    """P0-1 负向（API 层）：不存在的 project_workflow_id 必须 4xx，且不落执行记录。"""
    with client() as c:
        r = c.post(
            f"/api/pv-projects/{PID}/executions",
            json={"slot": "pv_tsc", "project_workflow_id": "pwf-nope",
                  "run_mode": "training", "run_domain": "project"},
        )
        assert r.status_code >= 400, r.text
        assert r.json()["detail"]["reason_code"] == "unknown_project_workflow"
        lst = c.get(f"/api/pv-projects/{PID}/executions", params={"slot": "pv_tsc"}).json()
        assert lst["executions"] == []


def test_run_center_rejects_blocked_preflight() -> None:
    """P0-1 负向（API 层）：预检 blocked 时执行被拒，不落记录。"""
    with client() as c:
        wf = _create_blank_workflow(c)  # 0 节点 → 预检必然 blocked
        r = c.post(
            f"/api/pv-projects/{PID}/executions",
            json={"slot": "pv_tsc", "project_workflow_id": wf,
                  "run_mode": "experiment", "run_domain": "project"},
        )
        assert r.status_code >= 400, r.text
        assert r.json()["detail"]["reason_code"] == "preflight_blocked"
        lst = c.get(f"/api/pv-projects/{PID}/executions", params={"slot": "pv_tsc"}).json()
        assert lst["executions"] == []


def test_run_center_preflight_returns_status() -> None:
    with client() as c:
        wf = _create_blank_workflow(c)
        r = c.post(f"/api/pv-projects/{PID}/preflight", json={"slot": "pv_tsc", "project_workflow_id": wf})
        assert r.status_code == 200, r.text
        assert r.json()["overall"] in {"blocked", "warning", "passed"}


# ---------------------------------------------------------------------------
# 5.3 日与点（API 部分）
# ---------------------------------------------------------------------------

def test_day_production_fact_is_honest() -> None:
    with client() as c:
        r = c.get(f"/api/pv-projects/{PID}/slots/pv_day/day/production-fact")
        assert r.status_code == 200, r.text
        fact = r.json()
        assert fact["dedicated_day_production_graph"] is False
        assert fact["production_workflow_id"] == "workflow-pv-fault-diag-quickval-predict-v1"


def test_day_sandbox_device_day_isolated() -> None:
    with client() as c:
        r = c.post(
            f"/api/pv-projects/{PID}/slots/pv_day/day/sandbox-device-day",
            json={"sandbox_id": "sbx-day-1", "device_days": [{"device": "D1", "date": "2026-01-01"}]},
        )
        assert r.status_code == 200, r.text
        run = r.json()["sandbox_run"]
        assert run["production_unaffected"] is True and run["governance_eligible"] is False


def test_point_sandbox_causal_step_and_metrics() -> None:
    with client() as c:
        base = f"/api/pv-projects/{PID}/slots/pv_point/point/sandboxes"
        r = c.post(base, json={"sandbox_id": "s1", "points": [
            {"event_time": "2026-01-01T00:00:00", "value": 1.0},
            {"event_time": "2026-01-01T00:05:00", "value": 5.0},
        ]})
        assert r.status_code == 200, r.text
        # predict-next 不推进 cursor。
        pn = c.post(f"{base}/s1/predict-next").json()
        assert pn["pending_point"]["prediction"]["n_history"] == 0
        assert c.get(f"{base}/s1").json()["sandbox"]["cursor"] == 0
        # commit 推进。
        assert c.post(f"{base}/s1/commit", json={}).json()["sandbox"]["cursor"] == 1
        # 指标：device-day 标签不进入真值。
        m = c.get(f"{base}/s1/metrics").json()
        assert m["device_day_labels_as_truth"] is False and m["supervised_point_accuracy"] is None


def test_cross_project_point_sandbox_isolation_api() -> None:
    with client() as c:
        # P1-5 后读写都要求项目已登记；本用例需要两个**真实**项目才能验隔离。
        for pid_ in ("proj-a", "proj-b"):
            repo.register_project_in_index(pid_, project_name=pid_)
        base_a = f"/api/pv-projects/proj-a/slots/pv_point/point/sandboxes"
        c.post(base_a, json={"sandbox_id": "s1", "points": [{"event_time": "2026-01-01T00:00:00", "value": 1.0}]})
        # 另一个项目找不到该 sandbox。
        r = c.get(f"/api/pv-projects/proj-b/slots/pv_point/point/sandboxes/s1")
        assert r.status_code == 409, r.text

# @AI_GENERATED: end
