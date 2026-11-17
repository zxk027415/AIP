"""检查回测工作流节点 functionId 和关键配置"""
import json
from pathlib import Path

wf = json.loads(Path("data/workflows_enhanced/workflow-load-forecast-backtest-v2.json").read_text())
nodes = wf["nodes"]
print("Backtest v2 节点列表 (functionId + 关键配置):")
for n in nodes:
    c = n.get("data", {}).get("config", {})
    fid = c.get("functionId", "")
    extras = ""
    if c.get("model_type"):
        extras += f" model_type={c['model_type']}"
    if c.get("mode"):
        extras += f" mode={c['mode']}"
    if c.get("n_estimators"):
        extras += f" n_est={c['n_estimators']}"
    if c.get("train_days"):
        extras += f" train_days={c['train_days']}"
    print(f"  {n['id']:42} {fid:30}{extras}")

# 看 XGBoost 节点的完整配置
print("\n\nXGBoost forecast node config:")
for n in nodes:
    c = n.get("data", {}).get("config", {})
    if c.get("functionId") == "xgboost_forecast":
        print(json.dumps(c, indent=2, ensure_ascii=False))
        break

# 看 sliding_window 节点
print("\n\nSliding window node config:")
for n in nodes:
    c = n.get("data", {}).get("config", {})
    if c.get("functionId") == "sliding_window":
        print(json.dumps(c, indent=2, ensure_ascii=False))
        break
