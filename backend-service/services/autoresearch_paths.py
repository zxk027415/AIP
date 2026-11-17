from __future__ import annotations

import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
_PROFILE = str(os.getenv("AUTORESEARCH_STORAGE_PROFILE") or "experiment").strip().lower()
if _PROFILE in ("dev", "development"):
    AUTORESEARCH_DIR = DATA_DIR / "autoresearch_dev"
else:
    AUTORESEARCH_DIR = DATA_DIR / "autoresearch"
LEGACY_WORKFLOWS_DIR = DATA_DIR / "workflows_enhanced"


def safe_id(value: str) -> str:
    cleaned = "".join(ch for ch in str(value) if ch.isalnum() or ch in ("-", "_"))
    if not cleaned:
        raise ValueError("id has no safe characters")
    return cleaned


def ensure_parent(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_dir() -> Path:
    return ensure_dir(AUTORESEARCH_DIR / "runs")


def run_dir(run_id: str) -> Path:
    return ensure_dir(runs_dir() / safe_id(run_id))


def snapshot_path(run_id: str) -> Path:
    return run_dir(run_id) / "snapshot.json"


def trial_ledger_path(run_id: str) -> Path:
    return run_dir(run_id) / "trials.jsonl"


def decision_ledger_path(run_id: str) -> Path:
    return run_dir(run_id) / "decisions.jsonl"


def run_artifacts_dir(run_id: str) -> Path:
    return ensure_dir(run_dir(run_id) / "artifacts")


def optuna_db_path() -> Path:
    return ensure_parent(AUTORESEARCH_DIR / "runs" / "optuna_studies.db")


def insights_dir() -> Path:
    return ensure_dir(AUTORESEARCH_DIR / "insights")


def insight_path(run_id: str) -> Path:
    return insights_dir() / f"{safe_id(run_id)}.json"


def insight_index_path() -> Path:
    return insights_dir() / "_index.json"


def knowledge_dir() -> Path:
    return ensure_dir(AUTORESEARCH_DIR / "knowledge")


def registries_dir() -> Path:
    return ensure_dir(AUTORESEARCH_DIR / "registries")


def memory_cases_path() -> Path:
    return ensure_parent(AUTORESEARCH_DIR / "memory" / "cases.json")


def dataset_registry_path() -> Path:
    return ensure_parent(AUTORESEARCH_DIR / "datasets" / "registry.json")


def feature_recipes_path() -> Path:
    return ensure_parent(AUTORESEARCH_DIR / "recipes" / "feature_recipes.json")


def workflow_slot_profiles_path() -> Path:
    return ensure_parent(AUTORESEARCH_DIR / "profiles" / "workflow_slot_profiles.json")


def candidate_pool_path() -> Path:
    return ensure_parent(AUTORESEARCH_DIR / "candidate_pool" / "baseline_comparison_candidate_pool.json")


def promotions_log_path() -> Path:
    return ensure_parent(AUTORESEARCH_DIR / "candidate_pool" / "baseline_comparison_promotions_log.json")


def production_registry_path() -> Path:
    return ensure_parent(AUTORESEARCH_DIR / "production" / "production_workflow_registry.json")


def legacy_runs_dir() -> Path:
    return LEGACY_WORKFLOWS_DIR / "autoresearch_runs"


def legacy_snapshot_path(run_id: str) -> Path:
    return legacy_runs_dir() / f"{safe_id(run_id)}.json"


def legacy_trial_ledger_path(run_id: str) -> Path:
    return legacy_runs_dir() / safe_id(run_id) / "trials.jsonl"


def legacy_decision_ledger_path(run_id: str) -> Path:
    return legacy_runs_dir() / safe_id(run_id) / "decisions.jsonl"


def legacy_insights_dir() -> Path:
    return DATA_DIR / "autoresearch_run_insights"


def legacy_insight_path(run_id: str) -> Path:
    return legacy_insights_dir() / f"{safe_id(run_id)}.json"


def legacy_insight_index_path() -> Path:
    return legacy_insights_dir() / "_index.json"


def legacy_knowledge_dir() -> Path:
    return DATA_DIR / "autoresearch_knowledge"


def legacy_registries_dir() -> Path:
    return DATA_DIR / "autoresearch_search_registries"


def legacy_memory_cases_path() -> Path:
    return LEGACY_WORKFLOWS_DIR / "auto_research_memory_cases.json"


def legacy_dataset_registry_path() -> Path:
    return LEGACY_WORKFLOWS_DIR / "autoresearch_datasets.json"


def legacy_feature_recipes_path() -> Path:
    return DATA_DIR / "feature_recipes.json"


def legacy_workflow_slot_profiles_path() -> Path:
    return DATA_DIR / "workflow_slot_profiles.json"


def legacy_candidate_pool_path() -> Path:
    return LEGACY_WORKFLOWS_DIR / "baseline_comparison_candidate_pool.json"


def legacy_promotions_log_path() -> Path:
    return LEGACY_WORKFLOWS_DIR / "baseline_comparison_promotions_log.json"


def legacy_production_registry_path() -> Path:
    return LEGACY_WORKFLOWS_DIR / "production_workflow_registry.json"


def first_existing(*paths: Path) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def as_str(path: Path) -> str:
    return os.fspath(path)
