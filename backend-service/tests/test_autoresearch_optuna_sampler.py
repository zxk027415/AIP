from services.autoresearch_optuna_sampler import AutoResearchOptunaSampler


def test_optuna_sampler_suggests_and_reports_trial(tmp_path):
    db_path = tmp_path / "optuna.db"
    sampler = AutoResearchOptunaSampler(storage_url=f"sqlite:///{db_path}")

    suggestion = sampler.suggest(
        "ares-optuna-1",
        {
            "train_days": [30, 45, 60],
            "max_depth": {"type": "int", "low": 3, "high": 6},
            "learning_rate": {"type": "float", "low": 0.01, "high": 0.2},
        },
        seed=123,
    )
    sampler.report("ares-optuna-1", suggestion.trial_number, 0.03)

    assert suggestion.params["train_days"] in [30, 45, 60]
    assert 3 <= suggestion.params["max_depth"] <= 6
    assert 0.01 <= suggestion.params["learning_rate"] <= 0.2


def test_optuna_sampler_handles_non_scalar_choices(tmp_path):
    db_path = tmp_path / "optuna.db"
    sampler = AutoResearchOptunaSampler(storage_url=f"sqlite:///{db_path}")

    suggestion = sampler.suggest(
        "ares-optuna-2",
        {"feature_recipe": [{"id": "a"}, {"id": "b"}]},
        seed=123,
    )
    sampler.report("ares-optuna-2", suggestion.trial_number, None, failed=True)

    assert suggestion.params["feature_recipe"] in [{"id": "a"}, {"id": "b"}]

