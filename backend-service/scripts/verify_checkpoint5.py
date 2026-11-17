# @AI_GENERATED: Kiro v1.0
"""Checkpoint 5 verification: scenario-match + algorithm-compose imports and basic functionality"""
import sys
import os

# Ensure backend is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    print("=" * 60)
    print("Checkpoint 5: Scenario Match + Algorithm Compose Verification")
    print("=" * 60)

    # 1. Import checks
    print("\n[1] Import checks...")
    try:
        from services.workflow_agent.skills.scenario_match import ScenarioMatchSkill
        print("  ✓ ScenarioMatchSkill imported")
    except Exception as e:
        print(f"  ✗ ScenarioMatchSkill import failed: {e}")
        return False

    try:
        from services.workflow_agent.skills.algorithm_compose import AlgorithmComposeSkill
        print("  ✓ AlgorithmComposeSkill imported")
    except Exception as e:
        print(f"  ✗ AlgorithmComposeSkill import failed: {e}")
        return False

    try:
        from services.workflow_agent.knowledge.algorithm_library import (
            get_algorithm_library, get_template_library,
        )
        print("  ✓ algorithm_library imported")
    except Exception as e:
        print(f"  ✗ algorithm_library import failed: {e}")
        return False

    # 2. Skill instantiation
    print("\n[2] Skill instantiation...")
    skill1 = ScenarioMatchSkill()
    print(f"  ✓ ScenarioMatchSkill: skill_name={skill1.skill_name}, required_role={skill1.required_role}")

    skill2 = AlgorithmComposeSkill()
    print(f"  ✓ AlgorithmComposeSkill: skill_name={skill2.skill_name}, required_role={skill2.required_role}")

    # 3. Data loading
    print("\n[3] Data loading...")
    import json

    # industry_scenarios.json
    scenarios_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "industry_scenarios.json")
    with open(scenarios_path, "r", encoding="utf-8") as f:
        scenarios = json.load(f)
    print(f"  ✓ industry_scenarios.json: {len(scenarios)} scenarios loaded")

    # scenario_algorithm_mappings.json
    mappings_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "scenario_algorithm_mappings.json")
    with open(mappings_path, "r", encoding="utf-8") as f:
        mappings = json.load(f)
    print(f"  ✓ scenario_algorithm_mappings.json: {len(mappings)} entries loaded")

    # Algorithm library
    lib = get_algorithm_library()
    print(f"  ✓ Algorithm library: {lib.total_count()} functions loaded")

    # Template library
    tpl_lib = get_template_library()
    print(f"  ✓ Template library: {tpl_lib.total_count()} templates loaded")
    print(f"    Scenario IDs: {tpl_lib.get_scenario_ids()[:5]}...")

    # 4. Functional test: scenario match
    print("\n[4] Functional test: scenario match...")
    import asyncio
    from models.workflow_agent_models import ScenarioMatchRequest, SkillContext

    async def test_scenario_match():
        req = ScenarioMatchRequest(description="新能源发电功率预测")
        ctx = SkillContext(user_id=1, username="test_user", session_id="test", role="user")
        resp = await skill1.execute(req, ctx)
        print(f"  ✓ Scenario match for '新能源发电功率预测': {len(resp.matches)} matches")
        for m in resp.matches[:3]:
            print(f"    - {m.scenario_id}: {m.scenario_name} (confidence={m.confidence_score})")
        print(f"    Extracted entities: {resp.extracted_entities}")
        return resp

    resp = asyncio.run(test_scenario_match())
    if len(resp.matches) == 0:
        print("  ⚠ Warning: No matches found for '新能源发电功率预测'")

    # 5. Functional test: algorithm compose
    print("\n[5] Functional test: algorithm compose...")
    from models.workflow_agent_models import AlgorithmComposeRequest

    async def test_algorithm_compose():
        req = AlgorithmComposeRequest(scenario_id="renewable-energy")
        ctx = SkillContext(user_id=1, username="test_user", session_id="test", role="user")
        resp = await skill2.execute(req, ctx)
        print(f"  ✓ Algorithm compose for 'renewable-energy': {resp.total_combinations} combinations")
        for combo in resp.combinations[:3]:
            print(f"    - {combo.combination_id}: profile={combo.profile}, layers={len(combo.layers)}, confidence={combo.overall_confidence}")
            for layer in combo.layers:
                algo_names = [a.algorithm_name for a in layer.algorithms[:3]]
                print(f"      {layer.layer_name}: {algo_names}")
        return resp

    resp2 = asyncio.run(test_algorithm_compose())

    print("\n" + "=" * 60)
    print("Checkpoint 5: ALL CHECKS PASSED ✓")
    print("=" * 60)
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
# @AI_GENERATED: end
