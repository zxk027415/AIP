from services.analyst_agent import AnalystAgent, ErrorAttribution
from services.dataset_profiler_models import CrossWindowPattern, TestProfile, TrainProfile, TriDatasetDiagnosis
from services.research_question_generator import ResearchQuestion, ResearchQuestionGenerator


def _train():
    return TrainProfile({}, {}, {}, {}, {}, "weekday_dominant", 0.2, 4.0)


def _test(high_extremes=False):
    return TestProfile(
        actual_vs_predicted=[],
        overall_mape=10.0,
        overall_rmse=1.0,
        max_single_point_error={},
        period_error_breakdown={
            "morning_peak": 20.0,
            "midday": 5.0,
            "evening_peak": 6.0,
            "night": 4.0,
            "worst_period": "morning_peak",
        },
        peak_error_ratio=2.0 if high_extremes else 0.0,
        valley_error_ratio=0.0,
        high_error_at_extremes=high_extremes,
        day_type="weekday",
    )


def test_analyst_agent_priority_chain_prefers_pattern_mismatch():
    diagnosis = TriDatasetDiagnosis(
        pattern_consistency={"status": "pattern_mismatch"},
        overfit_detection="confirmed_overfit",
        generalization_assessment="poor",
        diagnosis_conclusion="x",
    )
    cross = CrossWindowPattern("increasing", {"worst_periods": ["morning_peak"] * 3}, 3.0)

    output = AnalystAgent().analyze(_train(), _test(high_extremes=True), diagnosis, cross)

    attr = output.error_attribution
    assert set(attr.to_dict()) == {"primary_cause", "contributing_factors", "evidence"}
    assert attr.primary_cause == "pattern_mismatch"
    assert "confirmed_overfit" in attr.contributing_factors
    assert "drift_signal" in attr.contributing_factors


def test_analyst_agent_falls_back_to_parameter_saturation():
    diagnosis = TriDatasetDiagnosis(
        pattern_consistency={"status": "consistent"},
        overfit_detection="not_confirmed",
        generalization_assessment="good",
        diagnosis_conclusion="x",
    )

    output = AnalystAgent().analyze(_train(), _test(), diagnosis)

    assert output.error_attribution.primary_cause == "period_specific_error"


def test_research_question_generation_rules_and_shape():
    generator = ResearchQuestionGenerator()
    attr = ErrorAttribution(
        primary_cause="confirmed_overfit",
        contributing_factors=["period_specific_error"],
        evidence=["test_mape > cv_val_mape * 1.5"],
    )
    cross = CrossWindowPattern(
        error_trend="increasing",
        periodic_error_pattern={"worst_periods": ["night", "night", "night"]},
        drift_signal=2.0,
    )

    questions = generator.generate(attr, cross_window_pattern=cross)

    assert 1 <= len(questions) <= 3
    for question in questions:
        assert set(question.to_dict()) == {
            "question",
            "evidence",
            "candidate_causes",
            "next_experiment_goal",
            "recurring",
            "priority",
        }
    assert any("night" in q.question for q in questions)
    assert any("过拟合" in q.question for q in questions)
    assert any("漂移" in q.question for q in questions)


def test_research_question_dedup_marks_recurring():
    generator = ResearchQuestionGenerator()
    attr = ErrorAttribution("confirmed_overfit", [], ["e"])
    recent = [ResearchQuestion("如何降低当前配置的过拟合风险？", [], [], "x")]

    questions = generator.generate(attr, recent_questions=recent)

    assert questions[0].recurring is True
    assert questions[0].priority > 1.0


def test_research_question_generation_suppresses_stale_family():
    generator = ResearchQuestionGenerator()
    attr = ErrorAttribution("confirmed_overfit", [], ["e"])
    recent = [
        {
            "question": "如何降低当前配置的过拟合风险？",
            "next_experiment_goal": "验证降低模型复杂度或增加正则化是否缩小验证-测试误差差距",
            "candidate_causes": ["confirmed_overfit"],
            "status": "stale",
        }
    ]

    questions = generator.generate(attr, recent_questions=recent)

    assert all("过拟合" not in q.question for q in questions)
    assert questions[0].candidate_causes == ["stale_question_saturation"]
