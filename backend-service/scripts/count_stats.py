# @AI_GENERATED: Kiro v1.0
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# 统计行业场景数量
with open(DATA_DIR / 'industry_scenarios.json', encoding='utf-8') as f:
    scenarios = json.load(f)
print(f'行业场景: {len(scenarios)}')

# 统计算法方案数量
with open(DATA_DIR / 'industry_templates.json', encoding='utf-8') as f:
    templates_data = json.load(f)
    templates = templates_data.get('templates', [])
print(f'算法方案: {len(templates)}')

# 统计基础模块数量
with open(DATA_DIR / 'functions.json', encoding='utf-8') as f:
    functions = json.load(f)
print(f'基础模块: {len(functions)}')

# 按场景统计模板
scenario_counts = {}
for t in templates:
    sid = t.get('scenario_id', 'unknown')
    scenario_counts[sid] = scenario_counts.get(sid, 0) + 1

print('\n按场景统计:')
for s in scenarios:
    count = scenario_counts.get(s['id'], 0)
    print(f"  {s['name']}: {count}")

# 统计总数
total_templates = sum(scenario_counts.values())
print(f'\n总计: {total_templates} 个算法方案')
# @AI_GENERATED: end
