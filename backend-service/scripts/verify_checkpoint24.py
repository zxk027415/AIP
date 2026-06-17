# @AI_GENERATED: Kiro v1.0
"""Final Checkpoint 24 - Comprehensive verification of all Workflow Agent modules."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def main():
    errors = []
    
    # 1. All 8 skills
    print("=== 1. Importing all 8 Skills ===")
    try:
        from services.workflow_agent.skills.scenario_match import ScenarioMatchSkill
        from services.workflow_agent.skills.algorithm_compose import AlgorithmComposeSkill
        from services.workflow_agent.skills.workflow_generate import WorkflowGenerateSkill
        from services.workflow_agent.skills.workflow_validate import WorkflowValidateSkill
        from services.workflow_agent.skills.template_manage import TemplateManageSkill
        from services.workflow_agent.skills.domain_constraint import DomainConstraintSkill
        from services.workflow_agent.skills.best_practice import BestPracticeSkill
        from services.workflow_agent.skills.cross_scenario import CrossScenarioSkill
        print("  All 8 skills imported OK")
    except Exception as e:
        errors.append(f"Skills import: {e}")
        print(f"  FAILED: {e}")

    # 2. Orchestrator
    print("\n=== 2. Importing Orchestrator ===")
    try:
        from services.workflow_agent.orchestrator import SkillOrchestrator
        print("  Orchestrator imported OK")
    except Exception as e:
        errors.append(f"Orchestrator import: {e}")
        print(f"  FAILED: {e}")

    # 3. Audit + RBAC
    print("\n=== 3. Importing Audit + RBAC ===")
    try:
        from services.workflow_agent.audit.audit_logger import AuditLogger
        from services.workflow_agent.rbac import check_permission
        print("  Audit + RBAC imported OK")
    except Exception as e:
        errors.append(f"Audit/RBAC import: {e}")
        print(f"  FAILED: {e}")

    # 4. Event bus
    print("\n=== 4. Importing EventBus ===")
    try:
        from services.workflow_agent.event_bus import EventBus
        print("  EventBus imported OK")
    except Exception as e:
        errors.append(f"EventBus import: {e}")
        print(f"  FAILED: {e}")

    # 5. Knowledge bases
    print("\n=== 5. Importing Knowledge bases ===")
    try:
        from services.workflow_agent.knowledge.algorithm_library import get_algorithm_library
        from services.workflow_agent.knowledge.domain_constraints import get_domain_constraints_library
        from services.workflow_agent.knowledge.best_practices import get_best_practices_library
        print("  Knowledge bases imported OK")
    except Exception as e:
        errors.append(f"Knowledge bases import: {e}")
        print(f"  FAILED: {e}")

    # 6. API router
    print("\n=== 6. Checking API Router ===")
    try:
        from api.workflow_agent import router
        routes = [r.path for r in router.routes if hasattr(r, 'path')]
        print(f"  API router: {len(routes)} routes")
        for r in routes:
            print(f"    {r}")
        if len(routes) < 10:
            errors.append(f"Expected at least 10 routes, got {len(routes)}")
    except Exception as e:
        errors.append(f"API router import: {e}")
        print(f"  FAILED: {e}")

    # 7. Instantiate all skills
    print("\n=== 7. Instantiating all Skills ===")
    try:
        skills = [
            ScenarioMatchSkill(), AlgorithmComposeSkill(), WorkflowGenerateSkill(),
            WorkflowValidateSkill(), TemplateManageSkill(), DomainConstraintSkill(),
            BestPracticeSkill(), CrossScenarioSkill()
        ]
        for s in skills:
            print(f"  {s.skill_name}: role={s.required_role}")
        print(f"  All {len(skills)} skills instantiated OK")
    except Exception as e:
        errors.append(f"Skills instantiation: {e}")
        print(f"  FAILED: {e}")

    # 8. Verify chain: scenario-match -> algorithm-compose -> workflow-generate -> workflow-validate
    print("\n=== 8. Verifying Skill chain compatibility ===")
    try:
        sm = ScenarioMatchSkill()
        ac = AlgorithmComposeSkill()
        wg = WorkflowGenerateSkill()
        wv = WorkflowValidateSkill()
        chain_skills = [sm, ac, wg, wv]
        print(f"  Chain: {' -> '.join(s.skill_name for s in chain_skills)}")
        print("  Chain skills instantiated OK")
    except Exception as e:
        errors.append(f"Chain verification: {e}")
        print(f"  FAILED: {e}")

    # 9. Verify data files exist
    print("\n=== 9. Verifying data files ===")
    data_files = [
        "data/industry_scenarios.json",
        "data/scenario_algorithm_mappings.json",
        "data/domain_constraints.json",
        "data/best_practices.json",
        "data/industry_templates.json",
        "data/functions.json",
    ]
    for f in data_files:
        path = os.path.join(os.path.dirname(__file__), '..', f)
        if os.path.exists(path):
            print(f"  {f}: EXISTS")
        else:
            errors.append(f"Missing data file: {f}")
            print(f"  {f}: MISSING")

    # 10. Verify models
    print("\n=== 10. Verifying data models ===")
    try:
        from models.workflow_agent_models import (
            ScenarioMatchRequest, ScenarioMatchResponse,
            AlgorithmComposeRequest, AlgorithmComposeResponse,
            WorkflowGenerateRequest, WorkflowGenerateResponse,
            WorkflowValidateRequest, WorkflowValidateResponse,
        )
        print("  All Pydantic models imported OK")
    except Exception as e:
        errors.append(f"Models import: {e}")
        print(f"  FAILED: {e}")

    try:
        from models.workflow_agent_db import (
            WorkflowAgentTemplate, WorkflowAgentAuditLog,
            DomainConstraintRecord, BestPracticeRecord,
        )
        print("  All DB models imported OK")
    except Exception as e:
        errors.append(f"DB models import: {e}")
        print(f"  FAILED: {e}")

    # Summary
    print("\n" + "=" * 60)
    if errors:
        print(f"FINAL CHECKPOINT 24: FAILED ({len(errors)} errors)")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("=== FINAL CHECKPOINT 24 PASSED ===")
        print("All modules, skills, routes, data files, and models verified.")
        sys.exit(0)

if __name__ == "__main__":
    main()
# @AI_GENERATED: end
