#!/usr/bin/env python
"""G0-G8 end-to-end review script (API + pytest gate). Run from backend-service/."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "http://localhost:8081"

G_TESTS = [
    "tests/test_g0_pipeline_preflight.py",
    "tests/test_g0_slot_config.py",
    "tests/test_g0_execute_slot.py",
    "tests/test_g1_timeseries_profiles.py",
    "tests/test_g2_timeseries_point.py",
    "tests/test_g2_pv_point_workflow.py",
    "tests/test_g3_replay_graph_runner.py",
    "tests/test_g3_point_causal_regression.py",
    "tests/test_g3_replay_activity.py",
    "tests/test_g3_pv_day_equivalence.py",
    "tests/test_g4_slot_governance.py",
    "tests/test_g4_verify_async.py",
    "tests/test_g4_promote.py",
    "tests/test_g5_slot_datasets.py",
    "tests/test_g6_replay_activity.py",
    "tests/test_g6_fhc_profile.py",
    "tests/test_g6_nasa_profile.py",
    "tests/test_g6_nasa_npy_adapter.py",
    "tests/test_g6_reuse_report.py",
    "tests/test_g6_benchmark_governance.py",
    "tests/test_g8_pvdaq_profile.py",
    "tests/test_execution_history_index.py",
]


def run_pytest() -> int:
    env = {**os.environ, "PYTHONPATH": "."}
    cmd = [sys.executable, "-m", "pytest", *G_TESTS, "-q", "--tb=line"]
    print("== pytest ==")
    proc = subprocess.run(cmd, cwd=BACKEND_DIR, env=env)
    return proc.returncode


def check_api(base: str) -> dict:
    out: dict = {"base_url": base, "checks": []}
    with httpx.Client(base_url=base, timeout=30.0) as client:
        for path, key in [
            ("/api/benchmark/reuse-report", "reuse_report"),
            ("/api/benchmark/reuse-story", "reuse_story"),
        ]:
            try:
                resp = client.get(path)
                body = resp.json()
                ok = resp.status_code == 200 and body.get("success") is True
                out["checks"].append({"path": path, "ok": ok, "status": resp.status_code})
                if key == "reuse_report":
                    out["graph_match"] = body.get("report", {}).get("reuse_conclusion", {}).get(
                        "same_visible_operator_graph"
                    )
                if key == "reuse_story":
                    out["pvdaq_unlabeled"] = body.get("story", {}).get("reuse_conclusion", {}).get(
                        "pvdaq_unlabeled_no_fake_metrics"
                    )
            except Exception as exc:
                out["checks"].append({"path": path, "ok": False, "error": str(exc)})
    return out


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE
    pytest_rc = run_pytest()
    api_evidence = check_api(base)
    print("== API ==")
    print(json.dumps(api_evidence, ensure_ascii=False, indent=2))

    api_ok = all(c.get("ok") for c in api_evidence.get("checks", []))
    if pytest_rc != 0:
        print("FAIL: pytest")
        return pytest_rc
    if not api_ok:
        print(f"FAIL: API (is backend running on {base}?)")
        return 2
    print("PASS: G0-G8 review gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
