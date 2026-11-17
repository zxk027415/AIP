"""检查已有数据，确认预上线流程验证所需的数据是否存在"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# 1. 候选池
pool_path = BASE / "data/autoresearch/candidate_pool.json"
if pool_path.exists():
    pool = json.loads(pool_path.read_text())
    if isinstance(pool, list):
        print(f"候选池: {len(pool)} 条")
        for item in pool[:5]:
            print(f"  id={str(item.get('id',''))[:24]}  status={item.get('status')}"
                  f"  challenger={str(item.get('challenger_workflow_id',''))[:40]}")
    else:
        print("候选池: dict format, keys:", list(pool.keys())[:5])
else:
    print("候选池: 文件不存在")

# 2. 复验池
ver_path = BASE / "data/autoresearch/candidate_verification_queue.json"
if ver_path.exists():
    ver = json.loads(ver_path.read_text())
    if isinstance(ver, list):
        print(f"\n复验池: {len(ver)} 条")
        passed = [v for v in ver if v.get("status") == "passed"]
        failed = [v for v in ver if v.get("status") == "failed"]
        print(f"  passed={len(passed)}  failed={len(failed)}")
        for item in passed[:3]:
            print(f"  [passed] id={str(item.get('id',''))[:24]}"
                  f"  candidate_id={str(item.get('candidate_id',''))[:24]}")
    else:
        print("\n复验池: non-list format")
else:
    print("\n复验池: 文件不存在")

# 3. precision_ops 目录
po_path = BASE / "data/precision_ops"
if po_path.exists():
    print(f"\nprecision_ops 目录:")
    for f in sorted(po_path.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(po_path)} ({f.stat().st_size} bytes)")
else:
    print(f"\nprecision_ops 目录不存在（将在首次使用时自动创建）")

# 4. 候选池中复验通过的
if pool_path.exists() and ver_path.exists():
    pool = json.loads(pool_path.read_text()) if isinstance(json.loads(pool_path.read_text()), list) else []
    ver = json.loads(ver_path.read_text()) if isinstance(json.loads(ver_path.read_text()), list) else []
    passed_candidate_ids = {str(v.get("candidate_id", "")) for v in ver if v.get("status") == "passed"}
    eligible = [p for p in pool if str(p.get("id", "")) in passed_candidate_ids and p.get("status") != "promoted"]
    print(f"\n可入预上线的候选（复验passed且未promoted）: {len(eligible)} 条")
    for item in eligible[:3]:
        print(f"  id={str(item.get('id',''))[:24]}"
              f"  challenger={str(item.get('challenger_workflow_id',''))[:40]}"
              f"  source_run={str(item.get('source_run_id',''))[:20]}")
