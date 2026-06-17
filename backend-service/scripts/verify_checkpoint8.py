# @AI_GENERATED: Kiro v1.0
"""Checkpoint 8 验证脚本 — 验证算法模板生成和验证 Skill"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def verify_imports():
    """验证 Skill 导入"""
    print("=== 1. 验证导入 ===")
    from services.workflow_agent.skills.workflow_generate import WorkflowGenerateSkill
    from services.workflow_agent.skills.workflow_validate import WorkflowValidateSkill
    print("  workflow_generate 导入 OK")
    print("  workflow_validate 导入 OK")

    skill1 = WorkflowGenerateSkill()
    skill2 = WorkflowValidateSkill()
    assert skill1.skill_name == "workflow-generate", f"Expected 'workflow-generate', got '{skill1.skill_name}'"
    assert skill2.skill_name == "workflow-validate", f"Expected 'workflow-validate', got '{skill2.skill_name}'"
    assert skill1.required_role == "user"
    assert skill2.required_role == "user"
    print(f"  WorkflowGenerateSkill: name={skill1.skill_name}, role={skill1.required_role}")
    print(f"  WorkflowValidateSkill: name={skill2.skill_name}, role={skill2.required_role}")
    return True


def verify_domain_constraints():
    """验证 domain_constraints.json 覆盖 14 个场景"""
    print("\n=== 2. 验证 domain_constraints.json ===")
    json_path = os.path.join(os.path.dirname(__file__), "..", "data", "domain_constraints.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 排除 _comment 字段
    scenario_ids = [k for k in data.keys() if not k.startswith("_")]
    print(f"  场景数量: {len(scenario_ids)}")
    assert len(scenario_ids) == 14, f"Expected 14 scenarios, got {len(scenario_ids)}"

    for sid in scenario_ids:
        entry = data[sid]
        assert "scenario_name" in entry, f"{sid} missing scenario_name"
        assert "parameter_constraints" in entry, f"{sid} missing parameter_constraints"
        assert "evaluation_metrics" in entry, f"{sid} missing evaluation_metrics"
        assert "business_rules" in entry, f"{sid} missing business_rules"
        print(f"  {sid}: {entry['scenario_name']} — OK")

    return True


def verify_base_skill():
    """验证 BaseSkill 基类"""
    print("\n=== 3. 验证 BaseSkill 基类 ===")
    from services.workflow_agent.skills.base_skill import BaseSkill
    from services.workflow_agent.skills.workflow_generate import WorkflowGenerateSkill
    from services.workflow_agent.skills.workflow_validate import WorkflowValidateSkill

    assert issubclass(WorkflowGenerateSkill, BaseSkill)
    assert issubclass(WorkflowValidateSkill, BaseSkill)
    print("  WorkflowGenerateSkill 继承 BaseSkill — OK")
    print("  WorkflowValidateSkill 继承 BaseSkill — OK")
    return True


def verify_models():
    """验证相关数据模型"""
    print("\n=== 4. 验证数据模型 ===")
    from models.workflow_agent_models import (
        WorkflowGenerateRequest,
        WorkflowGenerateResponse,
        WorkflowValidateRequest,
        WorkflowValidateResponse,
        ValidationFinding,
        SkillContext,
        AlgorithmCombination,
    )
    print("  WorkflowGenerateRequest — OK")
    print("  WorkflowGenerateResponse — OK")
    print("  WorkflowValidateRequest — OK")
    print("  WorkflowValidateResponse — OK")
    print("  ValidationFinding — OK")
    print("  SkillContext — OK")
    print("  AlgorithmCombination — OK")
    return True


if __name__ == "__main__":
    all_passed = True
    for check in [verify_imports, verify_domain_constraints, verify_base_skill, verify_models]:
        try:
            check()
        except Exception as e:
            print(f"\n  FAILED: {e}")
            all_passed = False

    print("\n" + "=" * 40)
    if all_passed:
        print("Checkpoint 8 PASSED — 所有验证通过")
    else:
        print("Checkpoint 8 FAILED — 存在验证失败")
        sys.exit(1)
# @AI_GENERATED: end
