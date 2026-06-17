from services.experiment_quality import (
    CausalInferenceModule,
    ExperimentQualityScorer,
    InformationGainPruner,
    ParameterInteractionGraph,
    ProactivePredictor,
)


def test_experiment_quality_scores_are_in_range():
    scorer = ExperimentQualityScorer()
    quality = scorer.score(
        {
            "hypothesis": "因为晚高峰误差高，验证增加 lag 特征是否改善",
            "patches": [{"target_function_id": "create_lag_features", "param_key": "lags"}],
            "expected_outcome": {"metric": "mape", "direction": "decrease"},
            "risk": "low",
            "novel_param": True,
        }
    )

    for value in quality.to_dict().values():
        assert 0.0 <= value <= 1.0
    assert quality.single_variable_control == 1.0
    assert quality.expected_outcome_measurable == 1.0


def test_rank_experiments_switches_early_and_late_weights():
    scorer = ExperimentQualityScorer()
    info_rich = {
        "name": "info",
        "hypothesis": "因为未知参数交互，验证新特征是否产生信息增益",
        "patches": [{"target_function_id": "feature", "param_key": "x"}],
        "expected_outcome": {"metric": "mape"},
        "risk": "low",
        "novel_param": True,
        "expected_metric_gain": 0.1,
    }
    metric_rich = {
        "name": "metric",
        "hypothesis": "因为已有方向有效，验证强化该方向是否继续降低 MAPE",
        "patches": [{"target_function_id": "training", "param_key": "depth"}],
        "expected_outcome": {"metric": "mape"},
        "risk": "low",
        "novel_param": False,
        "expected_metric_gain": 0.9,
    }

    early = scorer.rank_experiments([info_rich, metric_rich], iteration=5)
    late = scorer.rank_experiments([info_rich, metric_rich], iteration=25)

    assert early[0]["name"] == "info"
    assert late[0]["name"] == "metric"


def test_information_gain_pruner_marks_three_low_rounds_exhausted():
    pruner = InformationGainPruner()

    result = pruner.prune({"lags": [0.02, 0.005, 0.004, 0.003], "train_days": [0.02, 0.0]})

    assert result["lags"].exhausted is True
    assert result["train_days"].exhausted is False
    assert pruner.space_contraction_log[0]["param_key"] == "lags"


def test_proactive_predictor_suggestions():
    predictor = ProactivePredictor()

    early = predictor.predict([10.0, 9.999, 9.998, 9.997])
    extension = predictor.predict([10.0, 9.8])

    assert early.suggestion == "suggest_early_convergence"
    assert extension.suggestion == "suggest_extension"
    assert extension.predicted_marginal_gain > 0


def test_parameter_interaction_graph_filters_invalid_lags():
    graph = ParameterInteractionGraph()
    valid = {"train_days": 2, "lags": [1, 96]}
    invalid = {"train_days": 2, "lags": [1, 999]}

    assert graph.validate_combination(valid)["valid"] is True
    assert graph.validate_combination(invalid)["valid"] is False
    assert graph.filter_valid_combinations([valid, invalid]) == [valid]


def test_causal_inference_outputs_confidence():
    module = CausalInferenceModule()

    result = module.infer(
        {
            "baseline_mape": 10.0,
            "mape": 9.0,
            "patches": [{"param_key": "lags"}],
            "config": {"lags": [96]},
            "condition": {"seasonality": "high"},
        }
    )

    assert result.confidence > 0
    assert result.effective_config == {"lags": [96]}
