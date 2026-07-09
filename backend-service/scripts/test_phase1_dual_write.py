# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
scripts/test_phase1_dual_write.py — Phase 1 双写端到端验证

模拟 AutoResearch 主循环调用两个入口，验证：
  1. AutoResearchRunStore.save() 同时写 snapshot.json + experiment_run 表
  2. KnowledgeLayer.save_claim() 同时写 knowledge/*/*.json + knowledge_claim 表

用法：
    conda activate cp_web
    python scripts/test_phase1_dual_write.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

# 用临时目录避免污染真实的 data/autoresearch/
tmpdir = Path(tempfile.mkdtemp(prefix="aip_dual_write_test_"))
print(f"临时 JSON 目录: {tmpdir}")

from services.autoresearch_run_store import AutoResearchRunStore
from services.knowledge_layer import ClaimKey, KnowledgeClaim, KnowledgeLayer
from services.db.repositories import get_autoresearch_repo


def test_run_store():
    print("\n=== [Test 1] AutoResearchRunStore.save 双写 ===")
    store = AutoResearchRunStore(root_dir=str(tmpdir / "runs"))
    run_id = "ares-phase1-test-001"
    state = {
        "run_id": run_id,
        "slot": "load_forecast",
        "status": "running",
        "baseline_workflow_id": "workflow-load-forecast-backtest-v3",
        "recoverable": True,
        "progress": {"iteration": 3, "total_iterations": 10},
        "compare_config": {"total_iterations": 10, "batch_size": 2},
        "runtime_patch": {"train_days": 30},
        "started_at": datetime.now().isoformat(),
    }

    path = store.save(run_id, state)
    print(f"  ✓ JSON 已写入: {path}")

    # 从 DB 里查
    repo = get_autoresearch_repo()
    if repo is None:
        print("  ✗ Repository 不可用（DBAdapter 初始化失败？）")
        return False

    row = repo.get_run(run_id)
    if row is None:
        print(f"  ✗ DB 里查不到 run_id={run_id}")
        return False

    print(f"  ✓ DB 里查到:")
    print(f"     id                    = {row.id}")
    print(f"     slot                  = {row.slot}")
    print(f"     status                = {row.status}")
    print(f"     baseline_workflow_id  = {row.baseline_workflow_id}")
    print(f"     current_iteration     = {row.current_iteration}")
    print(f"     total_iterations      = {row.total_iterations}")
    print(f"     recoverable           = {row.recoverable}")
    print(f"     snapshot_state keys   = {sorted((row.snapshot_state or {}).keys())}")
    return True


def test_knowledge_layer():
    print("\n=== [Test 2] KnowledgeLayer.save_claim 双写 ===")
    kl = KnowledgeLayer(root_dir=str(tmpdir / "knowledge"))
    claim = KnowledgeClaim(
        claim_key=ClaimKey(target_param="train_days", recommended_value=30),
        claim="30 天训练窗口在 drift 场景下 MAPE 更好",
        condition={"baseline_workflow_id": "workflow-load-forecast-backtest-v3", "drift_strength": 0.4},
        evidence=["ares-phase1-test-001"],
        knowledge_type="correlational",
        layer="L2",
        status="active",
    )
    kl.save_claim(claim)
    print(f"  ✓ JSON 已写入（scenario_condition_hash={claim.scenario_condition_hash}）")

    # 从 DB 里查
    repo = get_autoresearch_repo()
    if repo is None:
        print("  ✗ Repository 不可用")
        return False

    rows = repo.query_claims_by_scenario(claim.scenario_condition_hash)
    if not rows:
        print(f"  ✗ DB 里查不到 scenario_fingerprint={claim.scenario_condition_hash}")
        return False

    row = rows[0]
    print(f"  ✓ DB 里查到:")
    print(f"     id                   = {row.id}")
    print(f"     slot                 = {row.slot}")
    print(f"     scenario_fingerprint = {row.scenario_fingerprint}")
    print(f"     claim_type           = {row.claim_type}")
    print(f"     confidence           = {row.confidence}")
    print(f"     source_run_id        = {row.source_run_id}")
    return True


def cleanup_test_data():
    """清理 DB 里的测试记录，避免污染。"""
    print("\n=== 清理测试数据 ===")
    repo = get_autoresearch_repo()
    if repo is None:
        return
    adapter = repo._adapter
    from sqlalchemy import text
    with adapter.get_sync_session() as session:
        session.execute(
            text("DELETE FROM experiment_run WHERE id = 'ares-phase1-test-001'")
        )
        session.execute(
            text("DELETE FROM knowledge_claim WHERE source_run_id = 'ares-phase1-test-001'")
        )
    print("  ✓ 已删除 experiment_run 和 knowledge_claim 里的测试记录")


def main():
    ok1 = test_run_store()
    ok2 = test_knowledge_layer()
    cleanup_test_data()

    # 清理临时 JSON 目录
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n=== 结果 ===")
    print(f"  Test 1 (AutoResearchRunStore): {'PASS' if ok1 else 'FAIL'}")
    print(f"  Test 2 (KnowledgeLayer):        {'PASS' if ok2 else 'FAIL'}")
    if ok1 and ok2:
        print("\n✅ Phase 1 双写端到端验证通过")
    else:
        print("\n❌ Phase 1 双写有失败项")
        sys.exit(1)


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
