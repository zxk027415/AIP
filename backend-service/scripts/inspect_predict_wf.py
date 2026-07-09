"""检查预测工作流模板结构"""
import json
from pathlib import Path

wf_path = Path(__file__).resolve().parent.parent / "data/workflows_enhanced/workflow-load-forecast-prediction-v2.json"
wf = json.loads(wf_path.read_text())

print(f"ID: {wf.get('id')}")
print(f"Name: {wf.get('name')}")
print(f"Type: {wf.get('type')}")
print(f"Description: {wf.get('description', '')[:80]}")
print()

print("Nodes:")
for n in wf.get("nodes", []):
    fid = n.get("functionId", "")
    ntype = n.get("type", "")
    nid = n.get("id", "")
    label = n.get("data", {}).get("label", "") if isinstance(n.get("data"), dict) else ""
    print(f"  {nid[:35]:35} type={ntype:12} functionId={fid:30} label={label}")
print()

gc = wf.get("globalConfig", {})
print("Global Config:")
for k, v in gc.items():
    val_str = str(v)[:60]
    print(f"  {k}: {val_str}")
print()

# 查看 backtest 工作流
bt_path = Path(__file__).resolve().parent.parent / "data/workflows_enhanced/workflow-load-forecast-backtest-v2.json"
bt = json.loads(bt_path.read_text())
print(f"\n=== Backtest Workflow ===")
print(f"ID: {bt.get('id')}")
print(f"Name: {bt.get('name')}")
print(f"Type: {bt.get('type')}")
print(f"Nodes ({len(bt.get('nodes', []))}):")
for n in bt.get("nodes", []):
    fid = n.get("functionId", "")
    ntype = n.get("type", "")
    nid = n.get("id", "")
    print(f"  {nid[:35]:35} type={ntype:12} functionId={fid}")
bgc = bt.get("globalConfig", {})
print("Global Config keys:", list(bgc.keys()))
print(f"  dataset_path: {bgc.get('dataset_path')}")
print(f"  model_type: {bgc.get('model_type')}")
