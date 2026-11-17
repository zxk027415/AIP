# @AI_GENERATED: Kiro v1.0
"""扫描 industry_templates.json 中引用的所有算法ID，对比 functions.json 找出缺失项"""
import json
import os

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(base, "data", "industry_templates.json"), "r", encoding="utf-8") as f:
    data = json.load(f)
with open(os.path.join(base, "data", "functions.json"), "r", encoding="utf-8") as f:
    fdata = json.load(f)

func_ids = set(fn["id"] for fn in fdata["functions"])

tpl_ids = set()
tpl_usage = {}
layer_usage = {}
for tpl in data["templates"]:
    for wf in tpl.get("default_workflows", []):
        for layer_name, algo_ids in wf.get("layers", {}).items():
            for aid in algo_ids:
                tpl_ids.add(aid)
                tpl_usage.setdefault(aid, set()).add(tpl["name"])
                layer_usage.setdefault(aid, set()).add(layer_name)

missing = sorted(tpl_ids - func_ids)
existing = tpl_ids & func_ids

print(f"=== 统计 ===")
print(f"functions.json 算法总数: {len(func_ids)}")
print(f"模板引用唯一算法ID: {len(tpl_ids)}")
print(f"已命中: {len(existing)}")
print(f"缺失: {len(missing)}")
print()

categories = {}
for mid in missing:
    layers = layer_usage.get(mid, set())
    if "数据管理层" in layers:
        cat = "data_source"
    elif "数据处理层" in layers:
        cat = "data_preprocessing"
    elif "算法模型层" in layers:
        cat = "algorithm_model"
    elif "评估输出层" in layers:
        cat = "evaluation_output"
    else:
        cat = "unknown"
    categories.setdefault(cat, []).append(mid)

for cat in ["data_source", "data_preprocessing", "algorithm_model", "evaluation_output", "unknown"]:
    ids = categories.get(cat, [])
    if not ids:
        continue
    print(f"=== {cat} ({len(ids)}个) ===")
    for mid in ids:
        cnt = len(tpl_usage[mid])
        layers = ", ".join(sorted(layer_usage[mid]))
        samples = ", ".join(sorted(tpl_usage[mid])[:3])
        print(f"  {mid}  | 层:{layers} | 被{cnt}个模板引用 | 如: {samples}")
    print()
# @AI_GENERATED: end
