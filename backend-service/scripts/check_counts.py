# @AI_GENERATED: Kiro v1.0
import json

# 行业场景
with open('data/industry_scenarios.json', 'r', encoding='utf-8') as f:
    scenarios = json.load(f)
print(f'行业场景: {len(scenarios)} 个')

# 场景 function_count 累加
total_func = sum(s.get('function_count', 0) for s in scenarios)
print(f'场景function_count累加: {total_func}')
for s in scenarios:
    print(f"  {s['name']}: {s.get('function_count', 0)}")

# 行业模板 (行业算法方案)
with open('data/industry_templates.json', 'r', encoding='utf-8') as f:
    templates = json.load(f)
total_templates = templates.get('total_templates', len(templates.get('templates', [])))
print(f'\n行业算法方案(industry_templates): {total_templates} 个')

# 基础模块
with open('data/functions.json', 'r', encoding='utf-8') as f:
    functions = json.load(f)
print(f'基础模块分类: {len(functions.get("categories", []))} 个')
print(f'基础模块: {len(functions.get("functions", []))} 个')
# @AI_GENERATED: end
