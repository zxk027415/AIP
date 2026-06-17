# @AI_GENERATED: Kiro v1.0
"""Checkpoint 11 验证脚本 — 确保业务约束和模板管理代码可正常导入和运行"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def main():
    print("=" * 60)
    print("Checkpoint 11: 业务约束 & 模板管理验证")
    print("=" * 60)

    # 1. Import checks
    print("\n[1/5] 导入 DomainConstraintSkill...")
    from services.workflow_agent.skills.domain_constraint import DomainConstraintSkill
    print("  OK")

    print("[2/5] 导入 TemplateManageSkill...")
    from services.workflow_agent.skills.template_manage import TemplateManageSkill
    print("  OK")

    print("[3/5] 导入 domain_constraints 知识库...")
    from services.workflow_agent.knowledge.domain_constraints import get_domain_constraints_library
    print("  OK")

    # 2. Instantiation checks
    print("\n[4/5] 实例化 Skills...")
    skill1 = DomainConstraintSkill()
    skill2 = TemplateManageSkill()
    print(f"  DomainConstraintSkill: name={skill1.skill_name}, role={skill1.required_role}")
    print(f"  TemplateManageSkill:   name={skill2.skill_name}, role={skill2.required_role}")

    assert skill1.skill_name == "domain-constraint", f"Expected 'domain-constraint', got '{skill1.skill_name}'"
    assert skill1.required_role == "engineer", f"Expected 'engineer', got '{skill1.required_role}'"
    assert skill2.skill_name == "template-manage", f"Expected 'template-manage', got '{skill2.skill_name}'"
    assert skill2.required_role == "user", f"Expected 'user', got '{skill2.required_role}'"
    print("  Assertions passed")

    # 3. Domain constraints data loading
    print("\n[5/5] 加载业务约束数据...")
    lib = get_domain_constraints_library()
    scenario_ids = lib.get_all_scenario_ids()
    print(f"  已加载 {len(scenario_ids)} 个场景约束")
    print(f"  场景列表: {scenario_ids}")

    assert len(scenario_ids) >= 14, f"Expected >= 14 scenarios, got {len(scenario_ids)}"

    # Spot check one scenario
    c = lib.get_constraints("renewable-energy")
    assert c is not None, "renewable-energy constraints should exist"
    assert "parameter_constraints" in c, "Missing parameter_constraints"
    assert "evaluation_metrics" in c, "Missing evaluation_metrics"
    assert "business_rules" in c, "Missing business_rules"
    print(f"  renewable-energy: params={list(c['parameter_constraints'].keys())}")
    print(f"  renewable-energy: metrics={c['evaluation_metrics']}")

    print("\n" + "=" * 60)
    print("Checkpoint 11 PASSED")
    print("=" * 60)

if __name__ == "__main__":
    main()
# @AI_GENERATED: end
