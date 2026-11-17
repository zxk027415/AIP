from dataclasses import dataclass
from typing import Any, Dict, Optional

from . import autoresearch_paths as arp


@dataclass
class OptunaSuggestion:
    params: Dict[str, Any]
    trial_number: int
    study_name: str


class AutoResearchOptunaSampler:
    def __init__(self, storage_url: Optional[str] = None):
        db_path = arp.as_str(arp.optuna_db_path())
        self.storage_url = storage_url or f"sqlite:///{db_path}"

    def suggest(
        self,
        run_id: str,
        search_space: Dict[str, Any],
        seed: int = 42,
    ) -> OptunaSuggestion:
        optuna = self._optuna()
        study_name = self._study_name(run_id)
        study = optuna.create_study(
            study_name=study_name,
            storage=self.storage_url,
            sampler=optuna.samplers.TPESampler(seed=seed),
            direction="maximize",
            load_if_exists=True,
        )
        trial = study.ask()
        params: Dict[str, Any] = {}
        for key, spec in (search_space or {}).items():
            k = str(key).strip()
            if not k:
                continue
            params[k] = self._suggest_value(trial, k, spec)
        return OptunaSuggestion(params=params, trial_number=int(trial.number), study_name=study_name)

    def report(
        self,
        run_id: str,
        trial_number: int,
        value: Optional[float],
        failed: bool = False,
    ) -> None:
        optuna = self._optuna()
        study = optuna.load_study(study_name=self._study_name(run_id), storage=self.storage_url)
        if failed or value is None:
            study.tell(int(trial_number), state=optuna.trial.TrialState.FAIL)
            return
        study.tell(int(trial_number), float(value))

    def _suggest_value(self, trial: Any, key: str, spec: Any) -> Any:
        if isinstance(spec, list):
            if not spec:
                return None
            if all(self._is_optuna_categorical_value(v) for v in spec):
                return trial.suggest_categorical(key, spec)
            idx = trial.suggest_int(f"{key}.__choice_idx", 0, len(spec) - 1)
            return spec[idx]
        if isinstance(spec, dict):
            choices = spec.get("choices")
            if isinstance(choices, list) and choices:
                return self._suggest_value(trial, key, choices)
            typ = str(spec.get("type") or "").lower()
            low = spec.get("low", spec.get("min"))
            high = spec.get("high", spec.get("max"))
            step = spec.get("step")
            if typ in ("int", "integer") and low is not None and high is not None:
                kwargs = {"step": int(step)} if step is not None else {}
                return trial.suggest_int(key, int(low), int(high), **kwargs)
            if typ in ("float", "number") and low is not None and high is not None:
                kwargs = {"step": float(step)} if step is not None else {}
                return trial.suggest_float(key, float(low), float(high), **kwargs)
        return spec

    def _study_name(self, run_id: str) -> str:
        safe = "".join(ch for ch in str(run_id) if ch.isalnum() or ch in ("-", "_"))
        return f"autoresearch_{safe or 'default'}"

    def _is_optuna_categorical_value(self, value: Any) -> bool:
        return value is None or isinstance(value, (str, int, float, bool))

    def _optuna(self):
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        return optuna
