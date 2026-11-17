# @AI_GENERATED: Kiro v1.0
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

with open(DATA_DIR / 'industry_templates.json', encoding='utf-8') as f:
    data = json.load(f)
    solutions = data.get('templates', [])

total_algo_templates = 0
print(f"解决方案总数: {len(solutions)}\n")

# 统计每个解决方案下的算法模板数
for sol in solutions[:5]:  # 先看前5个
    algos = sol.get('competing_algorithms', [])
    total_algo_templates += len(algos)
    print(f"解决方案: {sol['name']}")
    print(f"  算法模板数: {len(algos)}")
    for algo in algos[:3]:  # 每个解决方案显示前3个算法
        print(f"    - {algo.get('name', algo.get('id', 'N/A'))}")
    if len(algos) > 3:
        print(f"    ... 还有 {len(algos)-3} 个")
    print()

# 统计总数
total = sum(len(sol.get('competing_algorithms', [])) for sol in solutions)
print(f"\n算法模板总数: {total}")
# @AI_GENERATED: end
