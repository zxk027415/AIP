#!/usr/bin/env python
"""G11 HTTP end-to-end review: Template A → proposal → confirm → trainable → prediction batch."""

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
DEFAULT_BASE = "http://localhost:8081"
LABEL_WF = "workflow-pv-point-label-v1"
SLOT = "pv_point"
POLL_S = 2
TIMEOUT_S = 120


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _step(steps: list[dict[str, Any]], name: str, ok: bool, **detail: Any) -> None:
    steps.append({"step": name, "ok": ok, "at": _now(), **detail})


def _poll_execution(client: httpx.Client, workflow_id: str, execution_id: str) -> dict[str, Any]:
    deadline = time.time() + TIMEOUT_S
    last: dict[str, Any] = {}
    while time.time() < deadline:
        resp = client.get(f"/api/workflows/enhanced/{workflow_id}/execution-status/{execution_id}")
        if resp.status_code == 200:
            last = resp.json()
            if last.get("status") in {"success", "failed", "cancelled"}:
                return last
        time.sleep(POLL_S)
    last["status"] = last.get("status", "timeout")
    return last


def run_review(base: str = DEFAULT_BASE) -> dict[str, Any]:
    run_tag = f"g11-e2e-{uuid.uuid4().hex[:8]}"
    report: dict[str, Any] = {
        "run_tag": run_tag,
        "started_at": _now(),
        "base_url": base,
        "steps": [],
        "field_trace": {},
        "passed": False,
    }
    steps = report["steps"]

    with httpx.Client(base_url=base, timeout=180.0) as client:
        try:
            _step(steps, "backend_reachable", client.get("/docs").status_code == 200)
        except Exception as exc:
            _step(steps, "backend_reachable", False, error=str(exc))
            report["finished_at"] = _now()
            return report

        wf = client.get(f"/api/workflows/enhanced/{LABEL_WF}")
        wf_body = wf.json() if wf.status_code == 200 else {}
        emit_node = next(
            (n for n in wf_body.get("nodes", []) if n.get("data", {}).get("config", {}).get("functionId") == "emit_label_proposal"),
            None,
        )
        _step(
            steps,
            "template_a_exists",
            wf.status_code == 200 and emit_node is not None,
            workflow_id=LABEL_WF,
            slot=(wf_body.get("metadata") or {}).get("slot"),
        )

        exec_resp = client.post(
            f"/api/workflows/enhanced/{LABEL_WF}/execute-async",
            json={"slot": SLOT, "execution_purpose": "product_workflow"},
        )
        exec_id = exec_resp.json().get("execution_id") if exec_resp.status_code == 200 else None
        _step(steps, "template_a_execute_started", exec_resp.status_code == 200 and bool(exec_id), execution_id=exec_id)
        if not exec_id:
            report["finished_at"] = _now()
            return report

        final = _poll_execution(client, LABEL_WF, exec_id)
        _step(
            steps,
            "template_a_execute_success",
            final.get("status") == "success",
            status=final.get("status"),
            error=final.get("error"),
        )

        proposals_before = client.get("/api/iterative-labeling/label-proposals", params={"slot": SLOT})
        prop_list = proposals_before.json().get("proposals") if proposals_before.status_code == 200 else []
        proposal_id = None
        for row in prop_list:
            if row.get("status") == "proposal":
                proposal_id = row.get("proposal_id")
                break
        _step(
            steps,
            "emit_label_proposal_persisted",
            bool(proposal_id),
            proposal_id=proposal_id,
            proposal_count=len(prop_list),
        )
        if not proposal_id:
            report["finished_at"] = _now()
            return report

        report["field_trace"]["proposal_id"] = proposal_id

        trainable_mid = client.get("/api/workflows/enhanced/datasets/trainable", params={"slot": SLOT})
        mid_ids = [r.get("dataset_id") for r in (trainable_mid.json().get("data", {}).get("labeled_versions") or [])]
        _step(steps, "proposal_not_trainable_before_confirm", proposal_id not in mid_ids)

        confirm = client.post(
            f"/api/iterative-labeling/label-proposals/{proposal_id}/confirm",
            json={"slot": SLOT},
        )
        confirm_body = confirm.json() if confirm.status_code == 200 else {}
        dataset_id = confirm_body.get("dataset_id") or confirm_body.get("dataset_version_id")
        _step(
            steps,
            "confirm_proposal_to_curated",
            confirm.status_code == 200 and bool(dataset_id),
            dataset_id=dataset_id,
            sample_count=confirm_body.get("sample_count"),
        )
        report["field_trace"]["dataset_id"] = dataset_id

        trainable = client.get("/api/workflows/enhanced/datasets/trainable", params={"slot": SLOT})
        rows = trainable.json().get("data", {}).get("labeled_versions") or []
        matched = next((r for r in rows if r.get("dataset_id") == dataset_id), None)
        _step(
            steps,
            "trainable_has_confirmed_dataset",
            trainable.status_code == 200 and matched is not None,
            file_path=(matched or {}).get("file_path"),
        )

        cluster = client.post(
            "/api/iterative-labeling/clustering/runs",
            json={
                "dataset_path": "backend-service/data/e2e/g10_clustering_fixture.csv",
                "n_clusters": 3,
                "page_size": 500,
                "slot": SLOT,
            },
        )
        cluster_body = cluster.json() if cluster.status_code == 200 else {}
        _step(
            steps,
            "rest_clustering_shortcut_mode",
            cluster.status_code == 200 and cluster_body.get("labeling_mode") == "shortcut",
            preferred_workflow=cluster_body.get("preferred_labeling_workflow_id"),
        )

        from services.operator_backends.emit_prediction_batch import execute as emit_batch

        batch_result = emit_batch(
            {
                "slot": "pv_day",
                "prediction_granularity": "day",
                "project_to_review_queue": False,
                "source_workflow_id": "wf-e2e",
                "source_execution_id": run_tag,
            },
            {
                "data": [
                    {"site_id": "s1", "device_id": "d1", "branch_id": 1, "time_window": "2024-03-01", "predicted_label": 1}
                ]
            },
        )
        batch_path = BACKEND_DIR / batch_result["batch_path"]
        _step(steps, "emit_prediction_batch_artifact", batch_path.is_file(), batch_id=batch_result.get("prediction_batch_id"))

    report["finished_at"] = _now()
    report["passed"] = all(s.get("ok") for s in steps)
    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=DEFAULT_BASE)
    args = parser.parse_args()
    report = run_review(args.base.rstrip("/"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"g11_e2e_review_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "steps": report["steps"], "out": str(out.relative_to(BACKEND_DIR))}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
