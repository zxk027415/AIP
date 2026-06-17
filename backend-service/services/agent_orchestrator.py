from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from .analyst_agent import AnalystAgent
from .dataset_profiler import DatasetProfiler
from .research_question_generator import ResearchQuestionGenerator


@dataclass(frozen=True)
class PatchFingerprint:
    target_function_id: str
    param_key: str
    direction: str

    def to_key(self) -> str:
        return f"{self.target_function_id}:{self.param_key}:{self.direction}"

    @classmethod
    def from_patch(cls, patch: Dict[str, Any]) -> "PatchFingerprint":
        return cls(
            str(patch.get("target_function_id") or patch.get("function_id") or ""),
            str(patch.get("param_key") or patch.get("key") or ""),
            str(patch.get("direction") or patch.get("op") or "set"),
        )


@dataclass
class AgentTrace:
    from_agent: str
    to_agent: str
    message_type: str
    payload: Dict[str, Any]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HypothesisDeduplicator:
    def __init__(self, disproved_fingerprints: Optional[List[str]] = None):
        self.disproved_fingerprints: Set[str] = set(disproved_fingerprints or [])

    def is_disproved(self, patch: Dict[str, Any]) -> bool:
        return PatchFingerprint.from_patch(patch).to_key() in self.disproved_fingerprints

    def filter_patches(self, patches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [patch for patch in patches if not self.is_disproved(patch)]


class DesignerAgent:
    def translate(self, intent: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(intent, dict):
            return []
        if isinstance(intent.get("patches"), list):
            return intent["patches"]
        proposal_keys = (
            "search_space_patch",
            "evaluation_contract_patch",
            "structure_patch",
            "global_config_patch",
            "node_param_patches",
        )
        if any(k in intent for k in proposal_keys):
            patches: List[Dict[str, Any]] = []
            for key in ("search_space_patch", "evaluation_contract_patch", "global_config_patch"):
                value = intent.get(key)
                if isinstance(value, dict):
                    patches.extend(
                        {
                            "target_function_id": key,
                            "param_key": str(param_key),
                            "direction": "set",
                            "value": param_value,
                        }
                        for param_key, param_value in value.items()
                    )
            for item in intent.get("node_param_patches") or []:
                if not isinstance(item, dict):
                    continue
                for param_key, param_value in (item.get("param_patch") or {}).items():
                    patches.append(
                        {
                            "target_function_id": str(item.get("functionId") or item.get("node_id") or "node_param"),
                            "param_key": str(param_key),
                            "direction": "set",
                            "value": param_value,
                        }
                    )
            structure_patch = intent.get("structure_patch")
            if isinstance(structure_patch, dict) and structure_patch:
                patches.append(
                    {
                        "target_function_id": "structure_patch",
                        "param_key": "structure",
                        "direction": "set",
                        "value": structure_patch,
                    }
                )
            return patches
        target = intent.get("target_function_id") or intent.get("function_id")
        param = intent.get("param_key") or intent.get("param")
        if not target or not param:
            return []
        patch = {
            "target_function_id": target,
            "param_key": param,
            "direction": intent.get("direction") or "set",
        }
        if "value" in intent:
            patch["value"] = intent["value"]
        return [patch]


class AgentOrchestrator:
    def __init__(
        self,
        agent_mode: str = "single_agent",
        glm_generate: Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = None,
    ):
        self.agent_mode = agent_mode if agent_mode in ("single_agent", "multi_agent") else "single_agent"
        self.glm_generate = glm_generate
        self.profiler = DatasetProfiler()
        self.analyst = AnalystAgent()
        self.question_generator = ResearchQuestionGenerator()
        self.designer = DesignerAgent()

    def run_pipeline(self, context: Dict[str, Any], run_state: Dict[str, Any]) -> Dict[str, Any]:
        if self.agent_mode == "single_agent":
            return self._single_agent(context, run_state)
        try:
            return self._multi_agent(context, run_state)
        except Exception as exc:
            self._trace(run_state, "orchestrator", "single_agent", "fallback", {"error": str(exc)})
            return self._single_agent(context, run_state)

    def _multi_agent(self, context: Dict[str, Any], run_state: Dict[str, Any]) -> Dict[str, Any]:
        train_profile = context["train_profile"]
        test_profile = context["test_profile"]
        diagnosis = context["tri_dataset_diagnosis"]
        cross = context.get("cross_window_pattern")
        self._trace(run_state, "dataset_profiler", "analyst", "facts", {})
        analyst_output = self.analyst.analyze(train_profile, test_profile, diagnosis, cross)
        self._trace(run_state, "analyst", "research_question_generator", "attribution", analyst_output.to_dict())
        questions = self.question_generator.generate(analyst_output.error_attribution, cross)
        payload = {"research_questions": [q.to_dict() for q in questions]}
        self._trace(run_state, "research_question_generator", "hypothesis", "questions", payload)
        intents = self._call_glm(payload)
        patches = []
        for intent in intents:
            patches.extend(self.designer.translate(intent))
        dedup = HypothesisDeduplicator(run_state.get("disproved_fingerprints"))
        patches = dedup.filter_patches(patches)
        self._trace(run_state, "designer", "autoresearch_engine", "patches", {"patches": patches})
        return {"mode": "multi_agent", "research_questions": payload["research_questions"], "patches": patches}

    def _single_agent(self, context: Dict[str, Any], run_state: Dict[str, Any]) -> Dict[str, Any]:
        intents = self._call_glm(context)
        patches = []
        for intent in intents:
            patches.extend(self.designer.translate(intent))
        dedup = HypothesisDeduplicator(run_state.get("disproved_fingerprints"))
        patches = dedup.filter_patches(patches)
        return {"mode": "single_agent", "patches": patches}

    def _call_glm(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        if self.glm_generate is None:
            return []
        result = self.glm_generate(payload)
        return result if isinstance(result, list) else []

    def _trace(
        self,
        run_state: Dict[str, Any],
        from_agent: str,
        to_agent: str,
        message_type: str,
        payload: Dict[str, Any],
    ) -> None:
        trace = AgentTrace(
            from_agent=from_agent,
            to_agent=to_agent,
            message_type=message_type,
            payload=payload,
            timestamp=datetime.utcnow().isoformat(),
        )
        run_state.setdefault("agent_traces", []).append(trace.to_dict())
