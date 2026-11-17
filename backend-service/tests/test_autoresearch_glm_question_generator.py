import asyncio

from services.autoresearch_glm_question_generator import AutoResearchGLMQuestionGenerator


def _context():
    return {
        "evidence": ["drift_signal=2.0", "midday is worst period in >=3 windows"],
        "active_layers": ["feature", "model", "data", "training"],
        "tri_dataset_diagnosis": {"diagnosis_conclusion": "midday is worst period in >=3 windows"},
        "cross_window_pattern": {"dominant_worst_period": "midday"},
        "dataset_profile": {
            "train_profile": {
                "peak_valley_distribution": {"avg_peak_valley_amplitude": 6329.225},
                "periodicity_strength": {"weekly_autocorr": 0.84},
            }
        },
    }


def test_glm_question_generator_accepts_audited_questions():
    async def fake_glm(*args, **kwargs):
        return {
            "content": """
            {
              "questions": [
                {
                  "question": "是否需要引入 midday 专属滞后特征来降低午间误差？",
                  "target_direction": "feature",
                  "target_layer": "feature",
                  "candidate_causes": ["period_specific_error"],
                  "evidence_refs": ["midday is worst period in >=3 windows"],
                  "next_experiment_goal": "验证 midday 专属 lag/rolling 特征是否降低午间 MAPE",
                  "expected_patch_intent": "add_feature_recipe",
                  "novelty_reason": "从训练窗口切换到特征结构验证",
                  "risk_level": "low"
                }
              ]
            }
            """
        }

    result = asyncio.run(
        AutoResearchGLMQuestionGenerator(fake_glm, enabled=True).generate(
            context=_context(),
            fallback_questions=[],
            recent_questions=[],
        )
    )

    assert result.source == "glm"
    assert result.llm_used is True
    assert result.questions[0]["proposal_source"] == "glm"
    assert result.questions[0]["audit_status"] == "accepted"
    assert result.questions[0]["target_direction"] == "feature"


def test_glm_question_generator_falls_back_when_disabled():
    fallback = [{"question": "当前误差是否已进入参数饱和区间？", "next_experiment_goal": "验证继续微调参数是否仍有收益"}]

    result = asyncio.run(
        AutoResearchGLMQuestionGenerator(enabled=False).generate(
            context=_context(),
            fallback_questions=fallback,
            recent_questions=[],
        )
    )

    assert result.source == "rule"
    assert result.llm_used is False
    assert result.questions[0]["proposal_source"] == "rule"


def test_glm_question_generator_rejects_duplicate_stale_family_and_uses_fallback():
    async def fake_glm(*args, **kwargs):
        return {
            "questions": [
                {
                    "question": "如何应对近期数据漂移导致的误差上升？",
                    "target_direction": "data",
                    "target_layer": "data",
                    "candidate_causes": ["drift_signal"],
                    "evidence_refs": ["drift_signal=2.0"],
                    "next_experiment_goal": "验证缩短训练窗口或提高近期样本权重是否改善泛化",
                    "expected_patch_intent": "adjust_param",
                    "novelty_reason": "重复问题",
                    "risk_level": "medium",
                }
            ]
        }

    recent = [
        {
            "question": "如何应对近期数据漂移导致的误差上升？",
            "candidate_causes": ["drift_signal"],
            "next_experiment_goal": "验证缩短训练窗口或提高近期样本权重是否改善泛化",
            "status": "stale",
        }
    ]
    fallback = [{"question": "已验证无效的问题是否应暂停并切换研究方向？", "next_experiment_goal": "切换方向"}]

    result = asyncio.run(
        AutoResearchGLMQuestionGenerator(fake_glm, enabled=True).generate(
            context=_context(),
            fallback_questions=fallback,
            recent_questions=recent,
        )
    )

    assert result.source == "glm_fallback"
    assert result.rejected[0]["reject_reason"] == "duplicate_stale_or_resolved_question"
    assert result.questions[0]["proposal_source"] == "glm_fallback"


def test_glm_question_generator_rejects_missing_evidence_refs():
    gen = AutoResearchGLMQuestionGenerator(enabled=True)
    accepted, rejected = gen.audit_candidates(
        [
            {
                "question": "是否应该换模型？",
                "target_direction": "model",
                "target_layer": "model",
                "next_experiment_goal": "验证模型族切换是否改善 MAPE",
            }
        ],
        context=_context(),
        recent_questions=[],
    )

    assert accepted == []
    assert rejected[0]["reject_reason"] == "missing_evidence_refs"


def test_glm_question_generator_accepts_profile_evidence_refs():
    gen = AutoResearchGLMQuestionGenerator(enabled=True)
    accepted, rejected = gen.audit_candidates(
        [
            {
                "question": "是否需要针对午间高误差增加特征？",
                "target_direction": "feature",
                "target_layer": "feature",
                "candidate_causes": ["period_specific_error"],
                "evidence_refs": ["cross_window_pattern.dominant_worst_period=midday"],
                "next_experiment_goal": "验证午间特征是否改善 MAPE",
                "expected_patch_intent": "add_midday_feature",
                "novelty_reason": "引用跨窗口画像中的最差时段",
                "risk_level": "low",
            }
        ],
        context=_context(),
        recent_questions=[],
    )

    assert rejected == []
    assert accepted[0]["proposal_source"] == "glm"


def test_glm_question_generator_warns_inactive_layer_instead_of_rejecting():
    gen = AutoResearchGLMQuestionGenerator(enabled=True)
    context = {**_context(), "active_layers": ["training"]}
    accepted, rejected = gen.audit_candidates(
        [
            {
                "question": "是否需要针对午间高误差增加特征？",
                "target_direction": "feature",
                "target_layer": "feature",
                "candidate_causes": ["period_specific_error"],
                "evidence_refs": ["cross_window_pattern.dominant_worst_period=midday"],
                "next_experiment_goal": "验证午间特征是否改善 MAPE",
                "expected_patch_intent": "add_midday_feature",
                "novelty_reason": "研究问题可以指向下一阶段方向",
                "risk_level": "low",
            }
        ],
        context=context,
        recent_questions=[],
    )

    assert rejected == []
    assert accepted[0]["audit_warning"] == "target_layer_not_currently_active"
