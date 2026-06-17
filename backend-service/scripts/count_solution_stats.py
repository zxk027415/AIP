# @AI_GENERATED: Kiro v1.0
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

# 加载模板数据
with open(DATA_DIR / 'industry_templates.json', encoding='utf-8') as f:
    templates_data = json.load(f)
    templates = templates_data.get('templates', [])

# 加载场景数据
with open(DATA_DIR / 'industry_scenarios.json', encoding='utf-8') as f:
    scenarios = json.load(f)

scenario_names = {s['id']: s['name'] for s in scenarios}

# 统计每个场景的模板数和函数数
scenario_stats = {}
for t in templates:
    sid = t.get('scenario_id', 'unknown')
    if sid not in scenario_stats:
        scenario_stats[sid] = {'templates': 0, 'functions': 0}
    scenario_stats[sid]['templates'] += 1
    # 统计竞争算法模板中的函数数
    for algo in t.get('competing_algorithms', []):
        scenario_stats[sid]['functions'] += len(algo.get('workflow_nodes', []))

total_templates = 0
total_functions = 0
print("场景统计:")
for sid, stats in sorted(scenario_stats.items()):
    name = scenario_names.get(sid, sid)
    total_templates += stats['templates']
    total_functions += stats['functions']
    print(f"  {name}: {stats['templates']}个模板, {stats['functions']}个函数")

print(f"\n总计: {total_templates}个模板, {total_functions}个函数")
# @AI_GENERATED: end
