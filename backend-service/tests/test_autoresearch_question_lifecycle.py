from services.autoresearch_question_lifecycle import AutoResearchQuestionLifecycle


def test_question_lifecycle_merges_duplicates_and_enters_testing():
    lifecycle = AutoResearchQuestionLifecycle()

    rows = lifecycle.merge_questions(
        [],
        [{"question": "如何降低当前配置的过拟合风险？", "next_experiment_goal": "降低复杂度"}],
        iteration=3,
        patch_fingerprint="fp-1",
        evidence_records=[{"patch_fingerprint": "fp-1", "evidence_strength": "single_window_positive"}],
    )
    rows = lifecycle.merge_questions(
        rows,
        [{"question": "如何降低当前配置的过拟合风险？", "next_experiment_goal": "增加正则"}],
        iteration=4,
        patch_fingerprint="fp-2",
        evidence_records=[{"patch_fingerprint": "fp-2", "evidence_strength": "single_window_positive"}],
    )

    assert len(rows) == 1
    assert rows[0]["status"] == "testing"
    assert rows[0]["recurring"] is True
    assert rows[0]["iteration"] == 4
    assert rows[0]["tested_patch_fingerprints"] == ["fp-1", "fp-2"]


def test_question_lifecycle_preserves_question_source_fields():
    lifecycle = AutoResearchQuestionLifecycle()

    rows = lifecycle.merge_questions(
        [],
        [
            {
                "question": "是否需要引入 midday 专属滞后特征来降低午间误差？",
                "next_experiment_goal": "验证 midday 专属 lag/rolling 特征是否降低午间 MAPE",
                "candidate_causes": ["period_specific_error"],
                "proposal_source": "glm",
                "audit_status": "accepted",
                "target_direction": "feature",
                "target_layer": "feature",
                "evidence_refs": ["midday is worst period in >=3 windows"],
                "expected_patch_intent": "add_feature_recipe",
            }
        ],
        iteration=2,
        patch_fingerprint="fp-glm",
        evidence_records=[],
    )

    assert rows[0]["proposal_source"] == "glm"
    assert rows[0]["audit_status"] == "accepted"
    assert rows[0]["target_direction"] == "feature"
    assert rows[0]["evidence_refs"] == ["midday is worst period in >=3 windows"]


def test_question_lifecycle_merges_semantic_duplicates_by_cause_and_goal():
    lifecycle = AutoResearchQuestionLifecycle()

    rows = lifecycle.merge_questions(
        [],
        [
            {
                "question": "如何应对近期数据漂移导致的误差上升？",
                "next_experiment_goal": "验证缩短训练窗口或提高近期样本权重是否改善泛化",
                "candidate_causes": ["drift_signal"],
            }
        ],
        iteration=10,
        patch_fingerprint="fp-1",
        evidence_records=[],
    )
    rows = lifecycle.merge_questions(
        rows,
        [
            {
                "question": "近期漂移导致误差升高时应该怎么处理？",
                "next_experiment_goal": "验证缩短训练窗口或提高近期样本权重是否改善泛化",
                "candidate_causes": ["drift_signal"],
            }
        ],
        iteration=11,
        patch_fingerprint="fp-2",
        evidence_records=[],
    )

    assert len(rows) == 1
    assert rows[0]["first_seen_iteration"] == 10
    assert rows[0]["last_seen_iteration"] == 11
    assert rows[0]["iteration"] == 11


def test_question_lifecycle_resolves_on_multi_window_confirmation():
    lifecycle = AutoResearchQuestionLifecycle()

    rows = lifecycle.merge_questions(
        [],
        [{"question": "是否应该启用差分特征？"}],
        iteration=8,
        patch_fingerprint="fp-confirmed",
        evidence_records=[{"patch_fingerprint": "fp-confirmed", "evidence_strength": "multi_window_confirmed"}],
    )

    assert rows[0]["status"] == "resolved"


def test_question_lifecycle_marks_stale_after_repeated_negative_evidence():
    lifecycle = AutoResearchQuestionLifecycle()

    rows = lifecycle.merge_questions(
        [],
        [{"question": "继续加大训练窗口是否有效？"}],
        iteration=1,
        patch_fingerprint="fp-1",
        evidence_records=[{"patch_fingerprint": "fp-1", "evidence_strength": "single_window_positive"}],
    )
    rows = lifecycle.merge_questions(
        rows,
        [{"question": "继续加大训练窗口是否有效？"}],
        iteration=5,
        patch_fingerprint="fp-2",
        evidence_records=[{"patch_fingerprint": "fp-2", "evidence_strength": "multi_window_rejected"}],
    )

    assert rows[0]["status"] == "stale"


def test_question_lifecycle_suppresses_repeated_stale_question_updates():
    lifecycle = AutoResearchQuestionLifecycle()

    rows = lifecycle.merge_questions(
        [],
        [{"question": "如何降低当前配置的过拟合风险？", "candidate_causes": ["confirmed_overfit"]}],
        iteration=1,
        patch_fingerprint="fp-1",
        evidence_records=[{"patch_fingerprint": "fp-1", "evidence_strength": "single_window_positive"}],
    )
    rows[0]["status"] = "stale"
    rows = lifecycle.merge_questions(
        rows,
        [{"question": "如何降低当前配置的过拟合风险？", "candidate_causes": ["confirmed_overfit"]}],
        iteration=9,
        patch_fingerprint="fp-2",
        evidence_records=[{"patch_fingerprint": "fp-2", "evidence_strength": "single_window_negative"}],
    )

    assert rows[0]["last_seen_iteration"] == 1
    assert rows[0]["suppressed_seen_count"] == 1
    assert rows[0]["last_suppressed_iteration"] == 9
