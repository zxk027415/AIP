"""检查预测工作流详细配置"""
import json
from pathlib import Path

wf = json.loads(Path("data/workflows_enhanced/workflow-load-forecast-prediction-v2.json").read_text())
gc = wf.get("globalConfig", {})
print("globalConfig:")
print(json.dumps(gc, indent=2, ensure_ascii=False)[:2000])
print()

nodes = wf.get("nodes", [])
if nodes:
    print(f"First node ({nodes[0].get('id')}) config:")
    cfg = nodes[0].get("data", {}).get("config", {})
    print(json.dumps(cfg, indent=2, ensure_ascii=False)[:600])
    print()
    print(f"Last node ({nodes[-1].get('id')}) config:")
    cfg = nodes[-1].get("data", {}).get("config", {})
    print(json.dumps(cfg, indent=2, ensure_ascii=False)[:600])

# 检查回测工作流 globalConfig
print("\n\n=== Backtest v2 globalConfig ===")
bt = json.loads(Path("data/workflows_enhanced/workflow-load-forecast-backtest-v2.json").read_text())
bgc = bt.get("globalConfig", {})
print(json.dumps(bgc, indent=2, ensure_ascii=False)[:2000])
