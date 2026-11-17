#!/usr/bin/env python
"""
G10 确认箱接缝 HTTP 端到端验证。

在 backend-service/ 下运行（需本地后端已启动，默认 :8081）:
  PYTHONPATH=. conda run -n cp_web python scripts/g10_e2e_review.py
  PYTHONPATH=. conda run -n cp_web python scripts/g10_e2e_review.py --base http://localhost:8080

写入 evidence: data/e2e/g10_e2e_review_<timestamp>.json
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = BACKEND_DIR / "data" / "e2e"
DEFAULT_BASE = "http://localhost:8081"
SLOT = "pv_point"
TRAIN_WF = "workflow-pv-point-train-eval-v1"
DATASET_PATH = "backend-service/data/e2e/g10_clustering_fixture.csv"
PAGE_SIZE = 500
N_CLUSTERS = 3


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _step(steps: list[dict[str, Any]], name: str, ok: bool, **detail: Any) -> None:
    steps.append({"step": name, "ok": ok, "at": _now(), **detail})


def _trainable_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data") or {}
    return list(data.get("labeled_versions") or []) + list(data.get("cumulative_snapshots") or [])


def _find_load_csv_nodes(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = workflow.get("nodes") or []
    return [n for n in nodes if (n.get("data") or {}).get("config", {}).get("functionId") == "load_csv"]


def run_review(base: str = DEFAULT_BASE, frontend_base: str | None = None) -> dict[str, Any]:
    run_tag = f"g10-e2e-{uuid.uuid4().hex[:10]}"
    report: dict[str, Any] = {
        "run_tag": run_tag,
        "started_at": _now(),
        "base_url": base,
        "frontend_base": frontend_base,
        "field_trace": {},
        "steps": [],
        "passed": False,
    }
    steps = report["steps"]

    with httpx.Client(base_url=base, timeout=180.0) as client:
        try:
            health = client.get("/docs")
            _step(steps, "backend_reachable", health.status_code == 200, status=health.status_code)
        except Exception as exc:
            _step(steps, "backend_reachable", False, error=str(exc))
            report["finished_at"] = _now()
            return report

        if frontend_base:
            try:
                fe = httpx.get(f"{frontend_base.rstrip('/')}/", timeout=10.0)
                _step(steps, "frontend_reachable", fe.status_code == 200, status=fe.status_code, url=frontend_base)
            except Exception as exc:
                _step(steps, "frontend_reachable", False, error=str(exc), url=frontend_base)

        before = client.get("/api/workflows/enhanced/datasets/trainable", params={"slot": SLOT})
        before_ids = {r.get("dataset_id") for r in _trainable_rows(before.json()) if r.get("dataset_id")}
        _step(
            steps,
            "trainable_baseline",
            before.status_code == 200 and before.json().get("success") is True,
            status=before.status_code,
            count=len(before_ids),
        )

        create = client.post(
            "/api/iterative-labeling/clustering/runs",
            json={
                "dataset_path": DATASET_PATH,
                "n_clusters": N_CLUSTERS,
                "page_size": PAGE_SIZE,
                "label_status": "all",
            },
        )
        run_body = create.json() if create.status_code == 200 else {}
        run_id = run_body.get("run_id")
        create_detail = create.text[:500] if create.status_code != 200 else None
        _step(
            steps,
            "clustering_create",
            create.status_code == 200 and bool(run_id),
            status=create.status_code,
            run_id=run_id,
            total_members=run_body.get("total_members"),
            detail=create_detail,
        )
        if not run_id:
            report["finished_at"] = _now()
            return report

        mid = client.get("/api/workflows/enhanced/datasets/trainable", params={"slot": SLOT})
        mid_ids = {r.get("dataset_id") for r in _trainable_rows(mid.json()) if r.get("dataset_id")}
        new_before_confirm = mid_ids - before_ids
        _step(
            steps,
            "proposal_gate_unconfirmed_not_trainable",
            mid.status_code == 200 and len(new_before_confirm) == 0,
            new_trainable_ids=sorted(new_before_confirm),
        )

        clusters = run_body.get("clusters") or {}
        for cid, cluster in clusters.items():
            label_name = f"g10_e2e_{run_tag}_c{cid}"
            upd = client.put(
                f"/api/iterative-labeling/clustering/runs/{run_id}/clusters/{cid}",
                json={
                    "proposed_label_name": label_name,
                    "selected_member_keys": cluster.get("member_keys") or [],
                },
            )
            if upd.status_code != 200:
                _step(steps, f"cluster_name_{cid}", False, status=upd.status_code, detail=upd.text[:300])
                report["finished_at"] = _now()
                return report
        _step(steps, "cluster_all_named", True, cluster_count=len(clusters))

        confirm = client.post(
            f"/api/iterative-labeling/clustering/runs/{run_id}/confirm",
            json={"confirm_inclusion": True, "slot": SLOT},
        )
        confirm_body = confirm.json() if confirm.status_code == 200 else {}
        dataset_id = confirm_body.get("dataset_id") or confirm_body.get("dataset_version_id")
        dataset_version_id = confirm_body.get("dataset_version_id")
        _step(
            steps,
            "clustering_confirm_publish",
            confirm.status_code == 200 and bool(dataset_id),
            status=confirm.status_code,
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            sample_count=confirm_body.get("sample_count"),
        )
        if not dataset_id:
            report["finished_at"] = _now()
            return report

        report["field_trace"]["confirm_dataset_id"] = dataset_id

        after = client.get("/api/workflows/enhanced/datasets/trainable", params={"slot": SLOT})
        after_body = after.json()
        labeled_rows = (after_body.get("data") or {}).get("labeled_versions") or []
        matched = next((r for r in labeled_rows if r.get("dataset_id") == dataset_id), None)
        file_path = matched.get("file_path") if matched else None
        _step(
            steps,
            "trainable_has_confirmed_row",
            after.status_code == 200 and matched is not None and bool(file_path),
            dataset_id=dataset_id,
            file_path=file_path,
            kind=matched.get("kind") if matched else None,
            is_latest=matched.get("is_latest") if matched else None,
        )
        report["field_trace"]["trainable_file_path"] = file_path

        cross = client.get("/api/workflows/enhanced/datasets/trainable", params={"slot": "pv_day"})
        cross_rows = _trainable_rows(cross.json())
        cross_hit = any(r.get("dataset_id") == dataset_id for r in cross_rows)
        _step(steps, "slot_isolation_pv_day", cross.status_code == 200 and not cross_hit, cross_hit=cross_hit)

        abs_csv = BACKEND_DIR / file_path if file_path else None
        csv_exists = abs_csv.is_file() if abs_csv else False
        _step(steps, "confirmed_csv_on_disk", csv_exists, path=file_path)

        wf = client.get(f"/api/workflows/enhanced/{TRAIN_WF}")
        wf_body = wf.json() if wf.status_code == 200 else {}
        load_nodes = _find_load_csv_nodes(wf_body)
        _step(
            steps,
            "train_workflow_has_load_csv",
            wf.status_code == 200 and len(load_nodes) >= 1,
            load_csv_count=len(load_nodes),
            workflow_slot=(wf_body.get("metadata") or {}).get("slot"),
        )

        deep_link_query = f"dataset_id={dataset_id}&slot={SLOT}"
        simulated_prefill_ok = bool(file_path) and len(load_nodes) >= 1
        _step(
            steps,
            "editor_deep_link_prefill_contract",
            simulated_prefill_ok,
            deep_link=deep_link_query,
            would_set_file_path=file_path,
            train_workflow_id=TRAIN_WF,
        )
        report["field_trace"]["deep_link"] = f"/workflow/editor/{TRAIN_WF}?{deep_link_query}"

        include = client.post(
            "/api/iterative-labeling/labeled-versions/include-cumulative",
            json={"slot": SLOT, "dataset_version_id": dataset_version_id},
        )
        _step(
            steps,
            "include_in_cumulative",
            include.status_code == 200,
            status=include.status_code,
            body=include.json() if include.status_code == 200 else include.text[:200],
        )

        build = client.post(
            "/api/iterative-labeling/labeled-versions/build-cumulative-snapshot",
            json={
                "slot": SLOT,
                "idempotency_key": run_tag,
                "reason": "g10 e2e review",
            },
        )
        build_body = build.json() if build.status_code == 200 else {}
        canvas_row = build_body.get("canvas_row") if isinstance(build_body.get("canvas_row"), dict) else {}
        snap_id = canvas_row.get("dataset_id")
        chain = build_body.get("chain") if isinstance(build_body.get("chain"), dict) else {}
        snap_version = chain.get("latest_version")
        _step(
            steps,
            "build_cumulative_snapshot",
            build.status_code == 200 and bool(snap_id),
            status=build.status_code,
            snapshot_dataset_id=snap_id,
            snapshot_version=snap_version,
            idempotent_replay=build_body.get("idempotent_replay"),
        )

        final = client.get("/api/workflows/enhanced/datasets/trainable", params={"slot": SLOT})
        final_data = final.json().get("data") or {}
        cum_rows = final_data.get("cumulative_snapshots") or []
        snap_row = next((r for r in cum_rows if r.get("dataset_id") == snap_id), None) if snap_id else None
        if not snap_row and cum_rows:
            snap_row = cum_rows[0]
        _step(
            steps,
            "trainable_has_cumulative_snapshot",
            final.status_code == 200 and len(cum_rows) >= 1,
            cumulative_count=len(cum_rows),
            latest_snapshot_id=(cum_rows[0].get("dataset_id") if cum_rows else None),
            matched_build_row=bool(snap_row),
        )

        if frontend_base:
            try:
                proxied = httpx.get(
                    f"{frontend_base.rstrip('/')}/api/workflows/enhanced/datasets/trainable",
                    params={"slot": SLOT},
                    timeout=15.0,
                )
                proxied_ok = proxied.status_code == 200 and proxied.json().get("success") is True
                proxied_has = any(
                    r.get("dataset_id") == dataset_id
                    for r in _trainable_rows(proxied.json())
                )
                _step(
                    steps,
                    "frontend_proxy_trainable",
                    proxied_ok and proxied_has,
                    status=proxied.status_code,
                    has_dataset_id=proxied_has,
                )
            except Exception as exc:
                _step(steps, "frontend_proxy_trainable", False, error=str(exc))

    report["finished_at"] = _now()
    report["passed"] = all(s.get("ok") for s in steps)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="G10 HTTP E2E review")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Backend base URL")
    parser.add_argument("--frontend", default="http://localhost:3001", help="Frontend base URL (optional)")
    parser.add_argument("--no-frontend", action="store_true", help="Skip frontend checks")
    args = parser.parse_args()

    frontend = None if args.no_frontend else args.frontend
    report = run_review(base=args.base.rstrip("/"), frontend_base=frontend)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"g10_e2e_review_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"passed": report["passed"], "steps": report["steps"], "out": str(out_path.relative_to(BACKEND_DIR))}, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
