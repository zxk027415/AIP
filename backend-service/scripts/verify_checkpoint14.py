# @AI_GENERATED: Kiro v1.0
"""Checkpoint 14 验证脚本：最佳实践和跨场景迁移"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def main():
    errors = []

    # 1. Import checks
    try:
        from services.workflow_agent.skills.best_practice import BestPracticeSkill
        print("[OK] BestPracticeSkill imported")
    except Exception as e:
        errors.append(f"BestPracticeSkill import failed: {e}")
        print(f"[FAIL] BestPracticeSkill import: {e}")

    try:
        from services.workflow_agent.skills.cross_scenario import CrossScenarioSkill
        print("[OK] CrossScenarioSkill imported")
    except Exception as e:
        errors.append(f"CrossScenarioSkill import failed: {e}")
        print(f"[FAIL] CrossScenarioSkill import: {e}")

    try:
        from services.workflow_agent.knowledge.best_practices import get_best_practices_library
        print("[OK] get_best_practices_library imported")
    except Exception as e:
        errors.append(f"best_practices knowledge import failed: {e}")
        print(f"[FAIL] best_practices knowledge import: {e}")

    # 2. Instantiation checks
    try:
        skill1 = BestPracticeSkill()
        assert skill1.skill_name == "best-practice", f"Expected 'best-practice', got '{skill1.skill_name}'"
        assert skill1.required_role == "engineer", f"Expected 'engineer', got '{skill1.required_role}'"
        print(f"[OK] BestPracticeSkill: name={skill1.skill_name}, role={skill1.required_role}")
    except Exception as e:
        errors.append(f"BestPracticeSkill instantiation failed: {e}")
        print(f"[FAIL] BestPracticeSkill instantiation: {e}")

    try:
        skill2 = CrossScenarioSkill()
        assert skill2.skill_name == "cross-scenario", f"Expected 'cross-scenario', got '{skill2.skill_name}'"
        assert skill2.required_role == "engineer", f"Expected 'engineer', got '{skill2.required_role}'"
        print(f"[OK] CrossScenarioSkill: name={skill2.skill_name}, role={skill2.required_role}")
    except Exception as e:
        errors.append(f"CrossScenarioSkill instantiation failed: {e}")
        print(f"[FAIL] CrossScenarioSkill instantiation: {e}")

    # 3. Best practices data loading
    try:
        lib = get_best_practices_library()
        all_practices = lib.get_all()
        assert len(all_practices) > 0, "No practices loaded"
        print(f"[OK] Best practices loaded: {len(all_practices)} entries")

        # Check at least 2 scenarios have practices
        scenarios = set(p.get("scenario_id") for p in all_practices)
        assert len(scenarios) >= 2, f"Expected >=2 scenarios, got {len(scenarios)}"
        print(f"[OK] Practices cover {len(scenarios)} scenarios: {sorted(scenarios)}")
    except Exception as e:
        errors.append(f"Best practices data loading failed: {e}")
        print(f"[FAIL] Best practices data: {e}")

    # 4. Data file existence
    data_file = os.path.join(os.path.dirname(__file__), "..", "data", "best_practices.json")
    if os.path.exists(data_file):
        print(f"[OK] best_practices.json exists")
    else:
        errors.append("best_practices.json not found")
        print(f"[FAIL] best_practices.json not found")

    # Summary
    print()
    if errors:
        print(f"Checkpoint 14 FAILED with {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("Checkpoint 14 PASSED - All best-practice and cross-scenario checks OK")
        sys.exit(0)

if __name__ == "__main__":
    main()
# @AI_GENERATED: end
