# @AI_GENERATED
"""Strict MultiRocket training/evaluation workflow adapter for ``slot=pv_tsc``."""

from __future__ import annotations

from typing import Any

from services.iterative_labeling.tsc.sliding_window_sampler import SamplerConfig
from services.iterative_labeling.tsc.tsc_pipeline import TSCPipeline
from services.operator_execution.router import OperatorExecutionError

OPERATOR_ID = "tsc_train_eval"


def _as_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _number(params: dict, key: str, cast, default):
    try:
        return cast(params.get(key) if params.get(key) not in (None, "") else default)
    except (TypeError, ValueError) as exc:
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", f"{key} has an invalid value"
        ) from exc


def execute(params: dict, inputs: dict) -> dict:
    samples = inputs.get("samples")
    if not isinstance(samples, dict):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "Input 'samples' must be the tsc_sliding_window payload"
        )
    missing = [name for name in ("X", "y", "meta") if name not in samples]
    if missing:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", f"samples is missing fields: {missing}"
        )

    sampler_payload = samples.get("sampler_config") or {}
    if not isinstance(sampler_payload, dict):
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", "samples.sampler_config must be an object"
        )
    try:
        sampler_config = SamplerConfig.from_dict(sampler_payload)
    except (TypeError, ValueError) as exc:
        raise OperatorExecutionError(
            OPERATOR_ID, "InputError", f"invalid samples.sampler_config: {exc}"
        ) from exc

    model_params = params.get("model_params") or {}
    if not isinstance(model_params, dict):
        raise OperatorExecutionError(
            OPERATOR_ID, "ParameterError", "model_params must be an object"
        )
    pipeline = TSCPipeline(
        sampler_config=sampler_config,
        model_name=str(params.get("model_name") or "multirocket"),
        model_params=model_params,
        preprocess_method=str(
            params.get("preprocess_method")
            or samples.get("preprocess_method")
            or "per_sample_zscore"
        ),
        n_splits=_number(params, "n_splits", int, 5),
        n_repeats=_number(params, "n_repeats", int, 10),
        test_ratio=_number(params, "test_ratio", float, 0.2),
        random_state=_number(params, "random_state", int, 90),
        fault_oversample=_as_bool(params.get("fault_oversample"), True),
        evaluation=str(params.get("evaluation") or "strict"),
        split_mode=str(params.get("split_mode") or "strict"),
        n_test_days=_number(params, "n_test_days", int, 3),
        held_device_ratio=_number(params, "held_device_ratio", float, 0.3),
        min_test_samples=_number(params, "min_test_samples", int, 30),
        baseline_model=str(params.get("baseline_model") or "").strip() or None,
        require_production_contract=_as_bool(
            params.get("require_production_contract"), True
        ),
    )
    result = pipeline.run_samples(
        samples["X"],
        samples["y"],
        samples["meta"],
        samples.get("load_stats") or {},
        _as_bool(samples.get("preprocessed"), False),
    )
    if result.get("status") != "ok":
        raise OperatorExecutionError(
            OPERATOR_ID,
            "TrainingError",
            str(result.get("error") or "TSC training/evaluation failed"),
        )

    model_ref = str(result.get("model_ref") or "").strip()
    if not model_ref:
        raise OperatorExecutionError(
            OPERATOR_ID, "ArtifactError", "training succeeded without model_ref"
        )
    metrics = dict(result)
    metric_keys = (
        "evaluation",
        "macro_f1_mean",
        "macro_f1_std",
        "accuracy_mean",
        "accuracy_std",
        "balanced_accuracy_mean",
        "balanced_accuracy_std",
        "macro_precision_mean",
        "macro_recall_mean",
        "n_samples",
        "n_classes",
        "n_splits_completed",
        "n_splits_requested",
        "window_length",
        "stride",
        "class_distribution",
        "sample_strategy",
        "evaluation_contract",
        "pairwise_vs_baseline",
        "production_contract_digest",
        "split_digest",
        "label_snapshot_hash",
        "metric_note",
    )
    return {
        "model_ref": model_ref,
        "model_path": model_ref,
        "model_dir": model_ref,
        "model_artifact_ref": model_ref,
        "artifact_format": result.get("artifact_format"),
        "production_contract_valid": result.get("production_contract_valid") is True,
        "evaluation_report_path": result.get("evaluation_report_path"),
        **{key: result.get(key) for key in metric_keys if key in result},
        "metrics": metrics,
    }
# @AI_GENERATED: end
