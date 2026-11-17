# @AI_GENERATED: Kiro v1.0
"""
校验 scenario_algorithm_mappings.json 中引用的算法ID
是否存在于 functions.json 和 industry_templates.json 中
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# 1. 加载 functions.json 中的所有 ID
with open(os.path.join(DATA_DIR, 'functions.json'), 'r', encoding='utf-8') as f:
    funcs_data = json.load(f)
func_ids = set(fn['id'] for fn in funcs_data.get('functions', []))
print(f"functions.json: {len(func_ids)} 个基础模块")

# 2. 加载 industry_templates.json 中的所有 ID
tpl_path = os.path.join(DATA_DIR, 'industry_templates.json')
tpl_ids = set()
if os.path.exists(tpl_path):
    with open(tpl_path, 'r', encoding='utf-8') as f:
        tpl_data = json.load(f)
    tpl_ids = set(t['id'] for t in tpl_data.get('templates', []))
    print(f"industry_templates.json: {len(tpl_ids)} 个场景模板")
else:
    print("industry_templates.json: 不存在")

all_known_ids = func_ids | tpl_ids
print(f"合计已知算法ID: {len(all_known_ids)}")

# 3. 加载 scenario_algorithm_mappings.json 中引用的所有 ID
with open(os.path.join(DATA_DIR, 'scenario_algorithm_mappings.json'), 'r', encoding='utf-8') as f:
    mappings = json.load(f)

referenced_ids = set()
for scenario_id, profiles in mappings.items():
    if scenario_id.startswith('_'):
        continue
    for profile, layers in profiles.items():
        for layer_name, algo_ids in layers.items():
            for aid in algo_ids:
                referenced_ids.add(aid)

print(f"\nscenario_algorithm_mappings.json 引用的算法ID: {len(referenced_ids)}")

# 4. 找出不存在的 ID
missing = referenced_ids - all_known_ids
in_funcs = referenced_ids & func_ids
in_tpls = referenced_ids & tpl_ids

print(f"  在 functions.json 中找到: {len(in_funcs)}")
print(f"  在 industry_templates.json 中找到: {len(in_tpls)}")
print(f"  缺失（两个文件都没有）: {len(missing)}")

if missing:
    print(f"\n=== 缺失的算法ID ===")
    for mid in sorted(missing):
        # 找出哪些场景引用了它
        refs = []
        for scenario_id, profiles in mappings.items():
            if scenario_id.startswith('_'):
                continue
            for profile, layers in profiles.items():
                for layer_name, algo_ids in layers.items():
                    if mid in algo_ids:
                        refs.append(f"{scenario_id}/{profile}/{layer_name}")
        print(f"  {mid} <- 被引用于: {', '.join(refs)}")

# 5. 同时检查 industry_templates.json 中 default_workflows 引用的 L4 ID
if os.path.exists(tpl_path):
    print(f"\n=== 检查 industry_templates.json 中算法模板引用的 L4 基础模块ID ===")
    wf_referenced = set()
    for tpl in tpl_data.get('templates', []):
        for wf in tpl.get('default_workflows', []):
            for layer_name, algo_ids in wf.get('layers', {}).items():
                for aid in algo_ids:
                    wf_referenced.add(aid)
    wf_missing = wf_referenced - func_ids
    print(f"算法模板引用的L4 ID总数: {len(wf_referenced)}")
    print(f"在 functions.json 中找到: {len(wf_referenced - wf_missing)}")
    print(f"缺失: {len(wf_missing)}")
    if wf_missing:
        print("缺失的L4 ID:")
        for mid in sorted(wf_missing):
            print(f"  {mid}")

print("\n=== 完成 ===")
# @AI_GENERATED: end
