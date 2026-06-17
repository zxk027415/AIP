from datetime import datetime, timedelta

from services.knowledge_layer import ClaimKey, KnowledgeClaim, KnowledgeLayer, condition_hash


def _claim(**kwargs):
    data = {
        "claim_key": ClaimKey("train_days", 45, "increase", "mape"),
        "claim": "increase train_days",
        "condition": {"seasonality": "high"},
        "evidence": ["r1"],
        "confidence": 0.5,
        "knowledge_type": "correlational",
        "layer": "L2",
        "last_validated_at": datetime.utcnow().isoformat(),
    }
    data.update(kwargs)
    return KnowledgeClaim(**data)


def test_knowledge_injection_weight_order_and_multipliers(tmp_path):
    layer = KnowledgeLayer(str(tmp_path))
    cond = {"seasonality": "high"}
    layer.save_claim(_claim(layer="L2", knowledge_type="correlational", condition=cond))
    layer.save_claim(
        _claim(
            claim_key=ClaimKey("regularization", 1.0, "increase", "mape"),
            layer="L4",
            knowledge_type="causal_candidate",
            condition=cond,
        )
    )

    candidates = layer.get_injection_candidates(cond)

    assert candidates[0]["layer"] == "L4"
    assert candidates[0]["injection_weight"] > candidates[1]["injection_weight"]

    mismatched = layer.get_injection_candidates({"seasonality": "low"})
    matched_weight = candidates[1]["injection_weight"]
    mismatch_weight = next(x for x in mismatched if x["layer"] == "L2")["injection_weight"]
    assert mismatch_weight == round(matched_weight * 0.3, 6)


def test_knowledge_confidence_lifecycle_decay_and_revival(tmp_path):
    layer = KnowledgeLayer(str(tmp_path))
    old = datetime.utcnow() - timedelta(days=90)
    claim = _claim(
        evidence=["r1", "r2", "r3"],
        counter_evidence=[],
        confidence=0.85,
        last_validated_at=old.isoformat(),
    )
    layer.save_claim(claim)

    saved = layer.search(target_param="train_days")[0]
    assert saved["confidence"] >= 0.8

    layer.apply_decay(now=datetime.utcnow(), decay_rate=0.2)
    stale = layer.search(target_param="train_days")[0]
    assert stale["confidence"] < 0.3
    assert stale["status"] == "stale"

    revived = layer.update_evidence(KnowledgeClaim.from_dict(stale), "r4", supports=True)
    assert revived.confidence >= 0.3
    assert revived.status == "active"


def test_knowledge_conflict_resolution_priority(tmp_path):
    layer = KnowledgeLayer(str(tmp_path))
    base_time = datetime.utcnow()
    layer.save_claim(
        _claim(
            claim_key=ClaimKey("train_days", 45, "increase", "mape"),
            condition={"a": 1, "b": 2},
            confidence=0.4,
            last_validated_at=(base_time - timedelta(days=10)).isoformat(),
        )
    )
    layer.save_claim(
        _claim(
            claim_key=ClaimKey("train_days", 20, "decrease", "mape"),
            condition={"a": 1},
            confidence=0.9,
            last_validated_at=base_time.isoformat(),
        )
    )

    conflicts = layer.resolve_conflicts()

    assert len(conflicts) == 1
    assert conflicts[0].reason == "condition_specificity"
    assert conflicts[0].winner.claim_key.direction == "increase"


def test_search_filters_by_hash_type_and_param(tmp_path):
    layer = KnowledgeLayer(str(tmp_path))
    cond = {"gap": "low"}
    layer.save_claim(_claim(condition=cond, knowledge_type="causal_candidate"))

    rows = layer.search(
        scenario_condition_hash=condition_hash(cond),
        knowledge_type="causal_candidate",
        target_param="train_days",
        min_confidence=0.1,
    )

    assert len(rows) == 1


def test_ingest_run_insight_accepts_string_rules(tmp_path):
    layer = KnowledgeLayer(str(tmp_path))

    claims = layer.ingest_run_insight(
        {
            "run_id": "run-1",
            "scenario_fingerprint": {"baseline_workflow_id": "wf-1", "registry_id": "reg-1"},
            "learned_rules": ["增加 train_days 在当前窗口改善 MAPE"],
            "ineffective_attempts": ["继续增大 auto_tune_n_trials 没有收益"],
        }
    )

    assert len(claims) == 2
    rows = layer.get_injection_candidates({"baseline_workflow_id": "wf-1", "registry_id": "reg-1"})
    assert len(rows) == 2
    assert {row["layer"] for row in rows} == {"L2", "L3"}
    assert {row["claim_key"]["target_param"] for row in rows} == {"correlational_text", "anti_pattern_text"}
    assert all(row["claim_key"]["recommended_value"] for row in rows)


def test_ingest_evidence_keeps_single_window_candidate_and_multi_window_active(tmp_path):
    layer = KnowledgeLayer(str(tmp_path))

    one = layer.ingest_evidence(
        {
            "run_id": "r1",
            "iteration": 1,
            "group_idx": 0,
            "target_direction": "feature",
            "target_layer": "feature",
            "patch_fingerprint": "fp1",
            "changed_variables": ["diff_features"],
            "evidence_strength": "single_window_positive",
            "mape_improvement": 0.1,
        }
    )
    two = layer.ingest_evidence(
        {
            "run_id": "r1",
            "iteration": 2,
            "group_idx": 0,
            "target_direction": "feature",
            "target_layer": "feature",
            "patch_fingerprint": "fp2",
            "changed_variables": ["holiday_features"],
            "evidence_strength": "multi_window_confirmed",
            "mape_improvement": 0.3,
        }
    )

    assert one.status == "candidate"
    assert two.status == "active"
    rows = layer.get_injection_candidates({"target_direction": "feature", "target_layer": "feature"})
    assert {row["status"] for row in rows} == {"candidate", "active"}


def test_counter_evidence_marks_conflicted_or_rejected(tmp_path):
    layer = KnowledgeLayer(str(tmp_path))
    claim = _claim(evidence=["r1"], counter_evidence=[], status="candidate")
    layer.save_claim(claim)

    updated = layer.update_evidence(claim, "r2", supports=False)

    assert updated.status in {"conflicted", "rejected"}
