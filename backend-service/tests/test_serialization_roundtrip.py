from services.agent_orchestrator import AgentTrace
from services.analyst_agent import ErrorAttribution
from services.dataset_profiler_models import (
    CrossWindowPattern,
    TestProfile,
    TrainProfile,
    TriDatasetDiagnosis,
    ValidationProfile,
)
from services.experiment_quality import ExperimentQuality
from services.knowledge_layer import ClaimKey, KnowledgeClaim
from services.periodic_reflection import ReflectionDecision, ReflectionResult
from services.research_question_generator import ResearchQuestion


def test_core_data_structures_round_trip():
    objects = [
        TrainProfile({}, {}, {}, {}, {}, "mixed", 0.0, 1.0),
        ValidationProfile([], 1.0, "low", "stable"),
        TestProfile([], 1.0, 1.0, {}, {"worst_period": "night"}, 0.0, 0.0, False),
        TriDatasetDiagnosis({"status": "consistent"}, "not_confirmed", "good", "ok"),
        CrossWindowPattern("stable", {"worst_periods": []}, 0.0),
        ResearchQuestion("q", ["e"], ["c"], "goal"),
        ExperimentQuality(1.0, 1.0, 1.0, 1.0, 1.0, 1.0),
        KnowledgeClaim(ClaimKey("train_days", 30, "increase", "mape"), "claim", {}),
        ReflectionResult(
            1,
            "improving",
            [],
            [],
            0.1,
            5.0,
            1.0,
            10,
            ReflectionDecision("s", "improving", "r", "continue_current"),
        ),
        AgentTrace("a", "b", "type", {}, "now"),
        ErrorAttribution("parameter_saturation", [], []),
    ]

    for obj in objects:
        data = obj.to_dict()
        cls = obj.__class__
        if hasattr(cls, "from_dict"):
            restored = cls.from_dict(data)
            assert restored.to_dict() == data
        else:
            restored = cls(**data)
            assert restored.to_dict() == data
