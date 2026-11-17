# @AI_GENERATED
"""Run the real pv_tsc freeze through the persisted strict-10 canvas workflow.

This script must be run from backend-service with PYTHONPATH=. It deliberately
uses the synchronous validation entry so model/evaluation artifacts and an
execution record are real while slot registry, candidates, cumulative state,
and label proposals must remain byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from pathlib import Path
from typing import Any

from services.scheduler.slot_workflow_runner import run_slot_workflow_sync

WORKFLOW_ID = "workflow-pv-tsc-train-eval-v1"
FREEZE_PATH = Path(
    "data/slot_datasets/pv_tsc/snapshots/"
    "snap-pv_tsc-20260904-100046-981f.parquet"
)
REPORT_PATH = Path("../output/pv_e2e_validation/tsc_strict10_run.json")
GOVERNANCE_PATHS = (
    Path("data/slot_governance/pv_tsc/registry.json"),
    Path("data/slot_governance/pv_tsc/model_candidates.json"),
    Path("data/iterative_labeling/cumulative_training/pv_tsc/state.json"),
    Path("data/slot_datasets/pv_tsc/label_proposals.json"),
)
STRICT_CONFIG: dict[str, Any] = {
    "model_name": "multirocket",
    "evaluation": "strict",
    "split_mode": "strict",
    "n_repeats": 10,
    "n_test_days": 5,
    "held_device_ratio": 0.6,
    "min_test_samples": 30,
    "baseline_model": "rocket_rf",
    "require_production_contract": True,
    "random_state": 90,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot(paths: tuple[Path, ...]) -> dict[str, dict[str, Any]]:
    return {
        path.as_posix(): {
            "exists": path.is_file(),
            "sha256": _sha256(path) if path.is_file() else None,
        }
        for path in paths
    }


def _write_report(payload: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "_comment": "@AI_GENERATED",
        **payload,
        "_comment_end": "@AI_GENERATED: end",
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _assert_relative(path_text: str) -> Path:
    normalized = str(path_text or "").replace("\\", "/").strip()
    assert normalized, "artifact path is empty"
    path = Path(normalized)
    assert not path.is_absolute(), f"artifact path must be relative: {normalized}"
    assert ".." not in path.parts, f"artifact path escapes backend-service: {normalized}"
    assert path.drive == "", f"artifact path must not contain a drive: {normalized}"
    return path


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), path.as_posix()
    return payload


def main() -> None:
    started = time.time()
    assert FREEZE_PATH.is_file(), f"real freeze not found: {FREEZE_PATH.as_posix()}"
    before = _snapshot(GOVERNANCE_PATHS)
    before_execution_ids = {
        path.stem
        for path in Path("data/execution_history/by_id").glob("exec-validation-*.json")
    }
    _write_report(
        {
            "status": "running",
            "workflow_id": WORKFLOW_ID,
            "freeze_path": FREEZE_PATH.as_posix(),
            "freeze_sha256": _sha256(FREEZE_PATH),
            "strict_config": STRICT_CONFIG,
            "governance_before": before,
        }
    )

    result: dict[str, Any] | None = None
    caught_error: Exception | None = None
    caught_traceback: str | None = None
    try:
        result = run_slot_workflow_sync(
            slot="pv_tsc",
            workflow_id=WORKFLOW_ID,
            execution_purpose="validation",
            extra_global_config={
                "input_file_path": FREEZE_PATH.as_posix(),
                "operate_status": "training",
                "run_mode": "train",
            },
            operator_param_overrides={"tsc_train_eval": STRICT_CONFIG},
            execution_metadata={
                "validation_kind": "real_pv_tsc_freeze_strict_10",
                "source_dataset_path": FREEZE_PATH.as_posix(),
                "strict_config": STRICT_CONFIG,
                "template_default_infeasible": {
                    "held_device_ratio": 0.3,
                    "n_test_days": 3,
                    "min_test_samples": 30,
                    "preflight_ready_splits": 0,
                },
            },
            require_persisted_execution=True,
            trigger_source="validation",
            governance_eligible=False,
        )
    except Exception as exc:  # keep side-effect evidence even when the workflow fails
        caught_error = exc
        caught_traceback = traceback.format_exc()

    after = _snapshot(GOVERNANCE_PATHS)
    changed_governance = {
        path: {"before": before[path], "after": after[path]}
        for path in before
        if before[path] != after[path]
    }
    if changed_governance:
        _write_report(
            {
                "status": "failed_governance_side_effect",
                "workflow_id": WORKFLOW_ID,
                "freeze_path": FREEZE_PATH.as_posix(),
                "strict_config": STRICT_CONFIG,
                "governance_before": before,
                "governance_after": after,
                "changed_governance": changed_governance,
                "workflow_error": str(caught_error) if caught_error else None,
                "workflow_traceback": caught_traceback,
                "elapsed_sec": round(time.time() - started, 3),
            }
        )
        raise AssertionError(f"validation changed governance state: {changed_governance}")

    if caught_error is not None or result is None:
        new_execution_files = sorted(
            path.as_posix()
            for path in Path("data/execution_history/by_id").glob("exec-validation-*.json")
            if path.stem not in before_execution_ids
        )
        _write_report(
            {
                "status": "failed_workflow",
                "workflow_id": WORKFLOW_ID,
                "freeze_path": FREEZE_PATH.as_posix(),
                "strict_config": STRICT_CONFIG,
                "governance_before": before,
                "governance_after": after,
                "governance_unchanged": True,
                "new_execution_files": new_execution_files,
                "workflow_error": str(caught_error),
                "workflow_traceback": caught_traceback,
                "elapsed_sec": round(time.time() - started, 3),
            }
        )
        raise RuntimeError(f"strict-10 workflow failed: {caught_error}") from caught_error

    assert result.get("success") is True
    assert result.get("execution_status") == "success"
    execution_id = str(result.get("execution_id") or "")
    assert execution_id.startswith("exec-validation-")

    metrics = dict(result.get("metrics") or {})
    assert metrics.get("n_splits_completed") == 10, metrics
    assert metrics.get("n_splits_requested") == 10, metrics
    assert metrics.get("production_contract_valid") is True, metrics
    assert metrics.get("evaluation") == "strict_multi_split", metrics

    model_ref = str(metrics.get("model_ref") or metrics.get("model_artifact_ref") or "")
    model_dir = _assert_relative(model_ref)
    assert model_dir.is_dir(), model_dir.as_posix()
    required_artifacts = (
        model_dir / "model.pkl",
        model_dir / "metadata.json",
        model_dir / "evaluation_report.json",
    )
    for artifact in required_artifacts:
        assert artifact.is_file(), artifact.as_posix()

    evaluation_report = _read_json(model_dir / "evaluation_report.json")
    model_results = dict(evaluation_report.get("results") or {})
    multirocket = dict(model_results.get("multirocket") or {})
    baseline = dict(model_results.get("rocket_rf") or {})
    for model_name, model_result in (
        ("multirocket", multirocket),
        ("rocket_rf", baseline),
    ):
        assert model_result.get("status") == "ok", {model_name: model_result}
        assert model_result.get("n_splits_completed") == 10, {model_name: model_result}
        assert model_result.get("n_splits_requested") == 10, {model_name: model_result}
        per_split = list(model_result.get("per_split") or [])
        assert len(per_split) == 10, {model_name: len(per_split)}
        assert [row.get("seed") for row in per_split] == list(range(90, 100))
        assert all(int(row.get("n_test") or 0) >= 30 for row in per_split)
        assert all((row.get("isolation") or {}).get("clean") is True for row in per_split)
        assert not model_result.get("skipped_splits"), model_result.get("skipped_splits")

    pairwise = dict(evaluation_report.get("pairwise_vs_baseline") or {})
    assert "multirocket" in pairwise, pairwise
    assert pairwise["multirocket"].get("n_paired") == 10, pairwise

    metadata = _read_json(model_dir / "metadata.json")
    assert metadata.get("model_name") == "multirocket", metadata
    window_config = dict(metadata.get("window_config") or {})
    evaluation_contract = dict(window_config.get("evaluation_contract") or {})
    assert evaluation_contract.get("production_contract_valid") is True
    assert evaluation_contract.get("n_splits_completed") == 10
    assert evaluation_contract.get("n_splits_requested") == 10
    assert evaluation_contract.get("split_mode") == "strict"
    assert evaluation_contract.get("representation") == "clock_grid_288_mask"
    assert evaluation_contract.get("channels") == ["value", "i_cal", "is_measured"]
    training_contract = dict(metadata.get("training_contract") or {})
    assert training_contract.get("production_contract_valid") is True

    execution_path = Path("data/execution_history/by_id") / f"{execution_id}.json"
    assert execution_path.is_file(), execution_path.as_posix()
    execution = _read_json(execution_path)
    assert execution.get("status") == "success"
    assert execution.get("trigger_source") == "validation"
    assert execution.get("execution_purpose") == "validation"
    assert execution.get("governance_eligible") is False
    assert (execution.get("execution_metadata") or {}).get("validation_kind") == (
        "real_pv_tsc_freeze_strict_10"
    )
    execution_metrics = dict(execution.get("metrics") or {})
    assert execution_metrics.get("n_splits_completed") == 10
    assert execution_metrics.get("production_contract_valid") is True
    node = dict((execution.get("nodeResults") or {}).get("tsc-train-eval-n3") or {})
    assert node.get("status") == "success", node
    summary = dict(node.get("outputSummary") or {})
    assert summary.get("n_splits_completed") == 10, summary
    assert summary.get("production_contract_valid") is True, summary

    _write_report(
        {
            "status": "passed",
            "scope": "real_pv_tsc_freeze_full_canvas_strict10_with_paired_baseline",
            "workflow_id": WORKFLOW_ID,
            "execution_id": execution_id,
            "execution_path": execution_path.as_posix(),
            "freeze_path": FREEZE_PATH.as_posix(),
            "freeze_sha256": _sha256(FREEZE_PATH),
            "strict_config": STRICT_CONFIG,
            "metrics": metrics,
            "model_ref": model_ref,
            "artifacts": [artifact.as_posix() for artifact in required_artifacts],
            "evaluation": {
                "multirocket": {
                    "n_splits_completed": multirocket.get("n_splits_completed"),
                    "macro_f1": multirocket.get("macro_f1"),
                    "balanced_accuracy": multirocket.get("balanced_accuracy"),
                    "per_split": multirocket.get("per_split"),
                },
                "rocket_rf": {
                    "n_splits_completed": baseline.get("n_splits_completed"),
                    "macro_f1": baseline.get("macro_f1"),
                    "balanced_accuracy": baseline.get("balanced_accuracy"),
                    "per_split": baseline.get("per_split"),
                },
                "pairwise_vs_baseline": pairwise,
            },
            "production_contract": evaluation_contract,
            "execution_contract": {
                "status": execution.get("status"),
                "trigger_source": execution.get("trigger_source"),
                "execution_purpose": execution.get("execution_purpose"),
                "governance_eligible": execution.get("governance_eligible"),
                "node_status": node.get("status"),
            },
            "governance_before": before,
            "governance_after": after,
            "governance_unchanged": True,
            "elapsed_sec": round(time.time() - started, 3),
        }
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "execution_id": execution_id,
                "model_ref": model_ref,
                "n_splits": metrics.get("n_splits_completed"),
                "production_contract_valid": metrics.get("production_contract_valid"),
                "macro_f1_mean": metrics.get("macro_f1_mean"),
                "elapsed_sec": round(time.time() - started, 3),
                "report": REPORT_PATH.as_posix(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
