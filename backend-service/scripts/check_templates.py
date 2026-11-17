# @AI_GENERATED: Kiro v1.0
"""检查行业模板数据完整性"""
import json
import os
from collections import Counter

def main():
    # 加载模板数据
    templates_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'industry_templates.json')
    with open(templates_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    templates = data.get('templates', [])
    print(f"总模板数: {len(templates)}")
    
    # 按场景统计
    scenario_counts = Counter(t['scenario_id'] for t in templates)
    print("\n按场景统计:")
    for scenario_id, count in sorted(scenario_counts.items()):
        print(f"  {scenario_id}: {count}")
    
    # 加载场景数据
    scenarios_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'industry_scenarios.json')
    with open(scenarios_path, 'r', encoding='utf-8') as f:
        scenarios = json.load(f)
    
    print(f"\n场景总数: {len(scenarios)}")
    
    # 检查缺失的场景
    scenario_ids = {s['id'] for s in scenarios}
    template_scenario_ids = set(scenario_counts.keys())
    
    missing = scenario_ids - template_scenario_ids
    if missing:
        print(f"\n缺少模板的场景: {missing}")
    else:
        print("\n所有场景都有模板数据 ✓")

if __name__ == '__main__':
    main()
# @AI_GENERATED: end
