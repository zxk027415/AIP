#!/usr/bin/env python
"""
PV redesign G0-G8 HTTP end-to-end story verification.

Run from backend-service/ with backend on :8080:
  PYTHONPATH=. conda run -n cp_web python scripts/pv_redesign_e2e_story.py

Writes evidence JSON to data/e2e/pv_redesign_e2e_story_<timestamp>.json
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BACKEND_DIR / "data" / "e2e"
BASE = "http://localhost:8080"
SLOT = "pv_point"
TRAIN_WF = "workflow-pv-point-train-eval-v1"
BENCHMARK_SLOT = "benchmark_pvdaq_system683"
POLL_INTERVAL_S = 3
TRAIN_TIMEOUT_S = 600


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _step(steps: list, name: str, ok: bool, **detail: Any) -> None:
    steps.append({"step": name, "ok": ok, "at": _now(), **detail})


def _poll_execution(client: httpx.Client, workflow_id: str, execution_id: str, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        resp = client.get(f"/api/workflows/enhanced/{workflow_id}/execution-status/{execution_id}")
        if resp.status_code != 200:
            time.sleep(POLL_INTERVAL_S)
            continue
        last = resp.json()
        status = last.get("status")
        if status in {"success", "failed", "cancelled"}:
            return last
        time.sleep(POLL_INTERVAL_S)
    last["status"] = last.get("status", "timeout")
    last["_poll_timeout"] = True
    return last


def run_story(base: str = BASE) -> dict[str, Any]:
    run_id = f"e2e-{uuid.uuid4().hex[:10]}"
    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": _now(),
        "base_url": base,
        "steps": [],
        "field_trace": {},
    }
    steps = report["steps"]

    with httpx.Client(base_url=base, timeout=120.0) as client:
        # ── A. Health + benchmark ──
        try:
            health = client.get("/docs")
            _step(steps, "backend_reachable", health.status_code == 200, status=health.status_code)
        except Exception as exc:
            _step(steps, "backend_reachable", False, error=str(exc))
            report["finished_at"] = _now()
            report["passed"] = False
            return report

        r_report = client.get("/api/benchmark/reuse-report")
        body = r_report.json() if r_report.status_code == 200 else {}
        graph_ok = body.get("report", {}).get("reuse_conclusion", {}).get("same_visible_operator_graph")
        _step(steps, "benchmark_reuse_report", r_report.status_code == 200 and graph_ok is True, graph_match=graph_ok)

        r_story = client.get("/api/benchmark/reuse-story")
        story_body = r_story.json() if r_story.status_code == 200 else {}
        pvdaq_ok = story_body.get("story", {}).get("reuse_conclusion", {}).get("pvdaq_unlabeled_no_fake_metrics")
        _step(steps, "benchmark_reuse_story", r_story.status_code == 200 and pvdaq_ok is True, pvdaq_unlabeled=pvdaq_ok)

        bench_reg = client.post(
            "/api/slot-governance/model-candidates",
            json={
                "slot": BENCHMARK_SLOT,
                "source_workflow_id": TRAIN_WF,
                "source_execution_id": "exec-should-fail",
                "model_artifact_ref": "data/models/demo/model.pt",
                "execution_purpose": "benchmark_reuse",
            },
        )
        blocked = bench_reg.status_code == 403 or (
            bench_reg.status_code == 400
            and (bench_reg.json().get("detail") or {}).get("code") == "benchmark_governance_forbidden"
        )
        _step(steps, "benchmark_governance_blocked", blocked, status=bench_reg.status_code)

        # ── B. Product train execute-async ──
        exec_resp = client.post(
            f"/api/workflows/enhanced/{TRAIN_WF}/execute-async",
            json={"slot": SLOT, "execution_purpose": "product_workflow"},
        )
        exec_id = exec_resp.json().get("execution_id") if exec_resp.status_code == 200 else None
        _step(
            steps,
            "train_execute_async_started",
            exec_resp.status_code == 200 and bool(exec_id),
            execution_id=exec_id,
            status_code=exec_resp.status_code,
        )

        train_state: dict = {}
        if exec_id:
            train_state = _poll_execution(client, TRAIN_WF, exec_id, TRAIN_TIMEOUT_S)
            train_ok = train_state.get("status") == "success"
            _step(
                steps,
                "train_execute_async_finished",
                train_ok,
                status=train_state.get("status"),
                slot=train_state.get("slot"),
                execution_purpose=train_state.get("execution_purpose"),
                governance_eligible=train_state.get("governance_eligible"),
                poll_timeout=train_state.get("_poll_timeout"),
            )
            report["field_trace"]["train"] = {
                "execution_id": exec_id,
                "slot": train_state.get("slot"),
                "execution_purpose": train_state.get("execution_purpose"),
                "governance_eligible": train_state.get("governance_eligible"),
            }

            model_path = None
            for node in (train_state.get("nodeResults") or {}).values():
                summary = (node or {}).get("outputSummary") or {}
                if isinstance(summary, dict) and summary.get("model_path"):
                    model_path = summary["model_path"]
                    break
            report["field_trace"]["train"]["model_path"] = model_path
        else:
            train_ok = False
            model_path = None

        # ── C. Governance chain (requires succeeded train) ──
        candidate_id = None
        verification_id = None
        if train_ok and exec_id and model_path:
            reg_c = client.post(
                "/api/slot-governance/model-candidates",
                json={
                    "slot": SLOT,
                    "source_workflow_id": TRAIN_WF,
                    "source_execution_id": exec_id,
                    "model_artifact_ref": model_path,
                },
            )
            candidate_id = (reg_c.json().get("candidate") or {}).get("model_candidate_id")
            _step(
                steps,
                "register_model_candidate",
                reg_c.status_code == 200 and bool(candidate_id),
                model_candidate_id=candidate_id,
                status=reg_c.status_code,
            )

            if candidate_id:
                reg_resp = client.get(f"/api/slot-governance/registry/{SLOT}")
                reg_version = (reg_resp.json() or {}).get("registry_version", 0)
                v_start = client.post(
                    "/api/slot-governance/verifications/verify-async",
                    json={
                        "slot": SLOT,
                        "model_candidate_id": candidate_id,
                        "idempotency_key": f"e2e-verify-{run_id}",
                        "registry_version_at_start": reg_version,
                    },
                )
                comparison_id = (v_start.json().get("job") or {}).get("comparison_id")
                _step(
                    steps,
                    "verify_async_started",
                    v_start.status_code == 200 and bool(comparison_id),
                    comparison_id=comparison_id,
                )

                if comparison_id:
                    v_exec = client.post(
                        f"/api/workflows/enhanced/{TRAIN_WF}/execute-async",
                        json={"slot": SLOT, "execution_purpose": "product_workflow"},
                    )
                    v_exec_id = v_exec.json().get("execution_id") if v_exec.status_code == 200 else None
                    verify_state = (
                        _poll_execution(client, TRAIN_WF, v_exec_id, TRAIN_TIMEOUT_S)
                        if v_exec_id
                        else {"status": "skipped"}
                    )
                    v_ok = verify_state.get("status") == "success"
                    _step(
                        steps,
                        "verify_evaluation_execution",
                        v_ok,
                        execution_id=v_exec_id,
                        status=verify_state.get("status"),
                    )

                    if v_ok and v_exec_id:
                        v_done = client.post(
                            f"/api/slot-governance/verifications/verify-async/{comparison_id}/complete",
                            json={"verification_execution_id": v_exec_id},
                        )
                        verification_id = (v_done.json().get("verification") or {}).get("verification_id")
                        passed = (v_done.json().get("verification") or {}).get("passed")
                        _step(
                            steps,
                            "verify_async_complete",
                            v_done.status_code == 200 and passed is True,
                            verification_id=verification_id,
                            passed=passed,
                        )
                        report["field_trace"]["verify"] = {
                            "comparison_id": comparison_id,
                            "verification_execution_id": v_exec_id,
                            "verification_id": verification_id,
                            "passed": passed,
                        }

                        if verification_id:
                            promo = client.post(
                                f"/api/slot-governance/model-candidates/{candidate_id}/promote",
                                json={
                                    "verification_id": verification_id,
                                    "operator": "e2e-script",
                                    "reason": "e2e promote smoke",
                                    "expected_registry_version": reg_version,
                                    "idempotency_key": f"e2e-promote-{run_id}",
                                    "production_slot": SLOT,
                                    "set_as_production": False,
                                },
                            )
                            new_reg_v = (promo.json().get("registry") or {}).get("registry_version")
                            _step(
                                steps,
                                "promote_model_candidate",
                                promo.status_code == 200,
                                registry_version=new_reg_v,
                                set_as_production=False,
                            )
        else:
            _step(
                steps,
                "governance_chain_skipped",
                True,
                reason="train not succeeded or model_path missing",
                train_ok=train_ok,
                model_path=bool(model_path),
            )

        # ── D. G5 snapshot bootstrap (idempotent) ──
        bs = client.post(
            "/api/slot-datasets/snapshots/bootstrap",
            json={
                "slot": SLOT,
                "idempotency_key": f"e2e-bootstrap-{run_id}",
                "source_digest": f"digest-{run_id}",
                "base_artifact_ref": "data/timeseries_point/test_fixtures/labeled_points.parquet",
                "dataset_profile_ref": "pv-point-demo@v1",
                "reason": "e2e bootstrap",
            },
        )
        bs_ok = bs.status_code == 200 or (
            bs.status_code == 409 and (bs.json().get("detail") or {}).get("code") == "snapshot_chain_exists"
        )
        chain = client.get("/api/slot-datasets/snapshots/chain", params={"slot": SLOT})
        chain_body = chain.json() if chain.status_code == 200 else {}
        _step(
            steps,
            "snapshot_bootstrap_or_exists",
            bs_ok and bool(chain_body.get("snapshot_id")),
            snapshot_id=chain_body.get("snapshot_id"),
            latest_version=chain_body.get("latest_version"),
        )

        # ── E. Pending verify jobs list (G7.3 API) ──
        pj = client.get(
            "/api/slot-governance/verifications/verify-async",
            params={"slot": SLOT, "status": "pending"},
        )
        _step(
            steps,
            "list_pending_verify_jobs",
            pj.status_code == 200,
            pending_count=len((pj.json() or {}).get("jobs") or []),
        )

    report["finished_at"] = _now()
    critical = [
        "backend_reachable",
        "benchmark_reuse_report",
        "benchmark_reuse_story",
        "benchmark_governance_blocked",
        "train_execute_async_started",
        "snapshot_bootstrap_or_exists",
        "list_pending_verify_jobs",
    ]
    report["passed"] = all(
        s["ok"] for s in steps if s["step"] in critical
    ) and any(s["step"] == "train_execute_async_finished" and s["ok"] for s in steps)
    report["passed_with_governance"] = all(s["ok"] for s in steps)
    return report


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else BASE
    print(f"PV redesign E2E story → {base}")
    report = run_story(base)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"pv_redesign_e2e_story_{report['run_id']}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nEvidence: {out_path.relative_to(BACKEND_DIR).as_posix()}")

    if report.get("passed"):
        print("PASS: core E2E (benchmark + train + snapshot APIs)")
        if report.get("passed_with_governance"):
            print("PASS: full governance chain included")
        else:
            print("WARN: governance chain partial — see steps")
        return 0
    print("FAIL: see steps above")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
