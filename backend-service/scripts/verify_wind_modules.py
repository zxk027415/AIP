# @AI_GENERATED: Kiro v1.0
"""验证风电模块JSON文件"""
import json
import os

modules_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'wind_power_modules.json')

with open(modules_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Loaded {len(data)} modules successfully")
print()

validation_count = 0
for m in data:
    params_with_validation = [p['name'] for p in m.get('parameters', []) if 'validation' in p]
    validation_count += len(params_with_validation)
    print(f"  {m['id']}: {len(m.get('parameters', []))} params, {len(params_with_validation)} with validation")

print()
print(f"Total validation rules: {validation_count}")
# @AI_GENERATED: end
