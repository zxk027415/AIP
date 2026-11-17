# @AI_GENERATED: Kiro v1.0
"""验证 functions.json 中所有可选参数是否都有 default 字段"""
import json

import os
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
with open("data/functions.json", "r", encoding="utf-8") as f:
    data = json.load(f)

funcs = data["functions"]
print(f"总函数数: {len(funcs)}")

count = 0
missing = []
for fn in funcs:
    optional_params = [p for p in fn["parameters"] if not p["required"]]
    for p in optional_params:
        if "default" in p:
            count += 1
        else:
            missing.append(f"  {fn['id']}.{p['name']}")

print(f"已添加default的可选参数数: {count}")
if missing:
    print(f"缺少default的参数 ({len(missing)}):")
    for m in missing:
        print(m)
else:
    print("所有可选参数都已有default值 ✓")
# @AI_GENERATED: end
