# @AI_GENERATED: Kiro v1.0
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"

with open(DATA_DIR / 'industry_templates.json', encoding='utf-8') as f:
    data = json.load(f)
    templates = data.get('templates', [])

print(f"算法模板总数: {len(templates)}\n")
print("前10个算法模板:")
for i, t in enumerate(templates[:10], 1):
    print(f"{i}. {t['id']} - {t['name']} ({t.get('scenario_id', 'N/A')})")
# @AI_GENERATED: end
