# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
scripts/migrate_autoresearch_storage_to_db.py — Phase 2 一次性历史数据迁移

把 data/autoresearch/ 和 data/deployment/ 目录下所有 JSON/JSONL 文件一次性
迁移到 MySQL 对应表，供后续 Phase 2 读切换使用。

用法：
    conda activate cp_web
    # 先看预计会迁移多少条（不真正写入）
    python scripts/migrate_autoresearch_storage_to_db.py --dry-run

    # 正式迁移
    python scripts/migrate_autoresearch_storage_to_db.py

    # 只迁移某些数据源（逗号分隔）
    python scripts/migrate_autoresearch_storage_to_db.py --only runs,insights,candidates

关联文档：docs/specs/autoresearch-mysql-migration/tasks.md Phase 2.1
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

DATA_DIR = _backend_dir / "data"
AR_DIR = DATA_DIR / "autoresearch"
DEPLOY_DIR = DATA_DIR / "deployment"
SCHED_DIR = DATA_DIR / "scheduler"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return None


def _read_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            lines.append(json.loads(line))
        except Exception:
            continue
    return lines


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _trunc(value: Any, maxlen: int) -> Optional[str]:
    if value is None:
        return None
    s = str(value)
    return s[:maxlen]


# ---------------------------------------------------------------------------
# Migrator 主类
# ---------------------------------------------------------------------------

class AutoresearchMigrator:
    """把 autoresearch JSON 文件迁移到 MySQL。"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.repo = None
        self.deploy_repo = None
        self.failures: List[str] = []
        self.summary: Dict[str, Dict[str, int]] = {}

        if not dry_run:
            from services.db.repositories import get_autoresearch_repo, get_deployment_repo
            self.repo = get_autoresearch_repo()
            self.deploy_repo = get_deployment_repo()
            if self.repo is None:
                raise RuntimeError("AutoResearchRepository not available — check DB connection")

    def _stat(self, key: str) -> Dict[str, int]:
        if key not in self.summary:
            self.summary[key] = {"migrated": 0, "skipped": 0, "failed": 0}
        return self.summary[key]

    def _inc(self, key: str, field: str, n: int = 1):
        self._stat(key)[field] += n

    # ------------------------------------------------------------------
    # 1. Run 快照 → experiment_run
    # ------------------------------------------------------------------
    def migrate_runs(self) -> None:
        runs_dir = AR_DIR / "runs"
        if not runs_dir.exists():
            print("  [runs] 目录不存在，跳过")
            return

        run_dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir())
        print(f"  [runs] 发现 {len(run_dirs)} 个 run 目录")

        for run_dir in run_dirs:
            run_id = run_dir.name
            snapshot_file = run_dir / "snapshot.json"
            if not snapshot_file.exists():
                self._inc("runs", "skipped")
                continue

            raw = _read_json(snapshot_file)
            if raw is None:
                self._inc("runs", "failed")
                self.failures.append(f"runs/{run_id}: read failed")
                continue

            state = raw.get("state") if isinstance(raw.get("state"), dict) else raw
            if not isinstance(state, dict):
                self._inc("runs", "failed")
                self.failures.append(f"runs/{run_id}: state not dict")
                continue

            progress = state.get("progress") if isinstance(state.get("progress"), dict) else {}
            current_iter = progress.get("iteration") or state.get("iteration")
            total_iter = progress.get("total_iterations") or state.get("total_iterations")
            status = str(state.get("status") or "interrupted")

            error_msg = state.get("error")
            if isinstance(error_msg, str) and len(error_msg) > 2048:
                error_msg = error_msg[:2048]

            run_data = {
                "id": run_id,
                "slot": _trunc(state.get("slot") or "default", 64),
                "status": _trunc(status, 32),
                "previous_status": _trunc(state.get("previous_status"), 32),
                "recoverable": bool(state.get("recoverable", False)),
                "baseline_workflow_id": _trunc(state.get("baseline_workflow_id"), 128),
                "current_iteration": int(current_iter) if isinstance(current_iter, (int, float)) else None,
                "total_iterations": int(total_iter) if isinstance(total_iter, (int, float)) else None,
                "config": state.get("compare_config") if isinstance(state.get("compare_config"), dict) else None,
                "runtime_patch": state.get("runtime_patch") if isinstance(state.get("runtime_patch"), dict) else None,
                "snapshot_state": state,
                "run_insight": state.get("run_insight") if isinstance(state.get("run_insight"), dict) else None,
                "terminal_status": _trunc(state.get("terminal_status"), 32),
                "error_message": error_msg,
                "started_at": _parse_dt(state.get("started_at") or state.get("created_at")) or datetime.utcnow(),
                "finished_at": _parse_dt(state.get("finished_at")),
                "interrupted_at": _parse_dt(state.get("interrupted_at")),
                "resumed_at": _parse_dt(state.get("resumed_at")),
            }

            print(f"    run {run_id}: status={status} iter={current_iter}/{total_iter}", end=" ")
            if self.dry_run:
                print("[DRY RUN]")
                self._inc("runs", "migrated")
                continue

            try:
                self.repo.upsert_run(run_data)
                print("OK")
                self._inc("runs", "migrated")
            except Exception as e:
                print(f"FAIL: {e}")
                self._inc("runs", "failed")
                self.failures.append(f"runs/{run_id}: {e}")


    # ------------------------------------------------------------------
    # 2. Trials → experiment_trial
    # ------------------------------------------------------------------
    def migrate_trials(self) -> None:
        runs_dir = AR_DIR / "runs"
        if not runs_dir.exists():
            return

        run_dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir())
        total = 0
        for run_dir in run_dirs:
            run_id = run_dir.name
            trials = _read_jsonl(run_dir / "trials.jsonl")
            if not trials:
                continue

            for row in trials:
                iter_no = row.get("iteration_no")
                status = str(row.get("status") or "success")
                override = row.get("override") or row.get("global_config_patch") or {}
                evidence = {
                    k: row.get(k)
                    for k in ("windows_total", "windows_comparable", "windows_challenger_better",
                               "failure_reason", "score_advantage", "hypothesis_verification")
                    if row.get(k) is not None
                }
                mape_imp = row.get("mape_improvement")
                bl_mape = row.get("baseline_mape")
                ch_mape = row.get("challenger_mape")

                trial_data = {
                    "run_id": run_id,
                    "iteration_no": int(iter_no) if iter_no is not None else 0,
                    "status": _trunc(status, 32),
                    "override_json": override if isinstance(override, dict) else {},
                    "evidence_json": evidence,
                    "mape_improvement": float(mape_imp) if isinstance(mape_imp, (int, float)) else None,
                    "baseline_mape": float(bl_mape) if isinstance(bl_mape, (int, float)) else None,
                    "challenger_mape": float(ch_mape) if isinstance(ch_mape, (int, float)) else None,
                    "started_at": _parse_dt(row.get("created_at")),
                    "finished_at": _parse_dt(row.get("finished_at")),
                }

                if self.dry_run:
                    self._inc("trials", "migrated")
                    total += 1
                    continue
                try:
                    self.repo.append_trial(run_id, trial_data)
                    self._inc("trials", "migrated")
                    total += 1
                except Exception as e:
                    self._inc("trials", "failed")
                    self.failures.append(f"trials/{run_id}/iter={iter_no}: {e}")

        print(f"  [trials] 迁移 {total} 条")

    # ------------------------------------------------------------------
    # 3. Decisions → experiment_decision
    # ------------------------------------------------------------------
    def migrate_decisions(self) -> None:
        runs_dir = AR_DIR / "runs"
        if not runs_dir.exists():
            return

        run_dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir())
        total = 0
        for run_dir in run_dirs:
            run_id = run_dir.name
            decisions = _read_jsonl(run_dir / "decisions.jsonl")
            if not decisions:
                continue

            for seq, row in enumerate(decisions, start=1):
                decision_type = str(row.get("decision_type") or "unknown")
                actor = str(row.get("actor") or "system")
                payload = {k: v for k, v in row.items()
                           if k not in ("decision_type", "actor", "created_at", "id", "study_id")}

                if self.dry_run:
                    self._inc("decisions", "migrated")
                    total += 1
                    continue
                try:
                    self.repo.append_decision(run_id, decision_type, payload, actor=actor)
                    self._inc("decisions", "migrated")
                    total += 1
                except Exception as e:
                    self._inc("decisions", "failed")
                    self.failures.append(f"decisions/{run_id}/seq={seq}: {e}")

        print(f"  [decisions] 迁移 {total} 条")


    # ------------------------------------------------------------------
    # 4. Run insights → experiment_run.run_insight (patch)
    # ------------------------------------------------------------------
    def migrate_insights(self) -> None:
        insights_dir = AR_DIR / "insights"
        if not insights_dir.exists():
            print("  [insights] 目录不存在，跳过")
            return

        insight_files = sorted(insights_dir.glob("ares-*.json"))
        print(f"  [insights] 发现 {len(insight_files)} 个 insight 文件")

        for f in insight_files:
            data = _read_json(f)
            if not isinstance(data, dict):
                self._inc("insights", "failed")
                continue

            run_id = data.get("run_id") or f.stem
            print(f"    insight {run_id}", end=" ")

            if self.dry_run:
                print("[DRY RUN]")
                self._inc("insights", "migrated")
                continue

            try:
                # 直接 upsert run（仅更新 run_insight 字段，其他字段保持已有值）
                self.repo.upsert_run({
                    "id": run_id,
                    "slot": _trunc(data.get("slot") or data.get("baseline_workflow_id") or "default", 64),
                    "status": "success",
                    "run_insight": data,
                    "started_at": _parse_dt(data.get("created_at")) or datetime.utcnow(),
                })
                print("OK")
                self._inc("insights", "migrated")
            except Exception as e:
                print(f"FAIL: {e}")
                self._inc("insights", "failed")
                self.failures.append(f"insights/{run_id}: {e}")

    # ------------------------------------------------------------------
    # 5. Knowledge claims → knowledge_claim
    # ------------------------------------------------------------------
    def migrate_knowledge(self) -> None:
        know_dir = AR_DIR / "knowledge"
        if not know_dir.exists():
            # 尝试 legacy
            know_dir = DATA_DIR / "autoresearch_knowledge"
        if not know_dir.exists():
            print("  [knowledge] 目录不存在，跳过")
            return

        layer_dirs = {
            "raw_cases": "L1", "patterns": "L2",
            "anti_patterns": "L3", "hypothesis_templates": "L4",
        }
        total = 0
        for subdir_name, layer_tag in layer_dirs.items():
            subdir = know_dir / subdir_name
            if not subdir.exists():
                continue
            files = list(subdir.glob("*.json"))
            for f in files:
                data = _read_json(f)
                if not isinstance(data, dict):
                    self._inc("knowledge", "failed")
                    continue

                condition = data.get("condition") or {}
                slot = str(condition.get("slot") or condition.get("baseline_workflow_id") or "default")[:64]
                claim_id = f.stem  # 文件名即 claim 的 hash id
                source_run_id = None
                evidence = data.get("evidence") or []
                if evidence:
                    source_run_id = str(evidence[0])[:64]

                status = str(data.get("status") or "candidate")
                decayed_at = datetime.utcnow() if status == "stale" else None

                claim_data = {
                    "id": claim_id,
                    "slot": slot,
                    "scenario_fingerprint": _trunc(data.get("scenario_condition_hash") or "", 256),
                    "claim_type": _trunc(data.get("knowledge_type") or "correlational", 64),
                    "claim_data": data,
                    "confidence": float(data.get("confidence") or 0.0),
                    "source_run_id": source_run_id,
                    "decayed_at": decayed_at,
                }

                if self.dry_run:
                    self._inc("knowledge", "migrated")
                    total += 1
                    continue
                try:
                    self.repo.upsert_claim(claim_data)
                    self._inc("knowledge", "migrated")
                    total += 1
                except Exception as e:
                    self._inc("knowledge", "failed")
                    self.failures.append(f"knowledge/{subdir_name}/{f.name}: {e}")

        print(f"  [knowledge] 迁移 {total} 条")


    # ------------------------------------------------------------------
    # 6. Candidate pool → candidate_pool
    # ------------------------------------------------------------------
    def migrate_candidates(self) -> None:
        pool_file = AR_DIR / "candidate_pool" / "baseline_comparison_candidate_pool.json"
        if not pool_file.exists():
            print("  [candidates] 文件不存在，跳过")
            return

        data = _read_json(pool_file)
        candidates = (data or {}).get("candidates") or []
        print(f"  [candidates] 发现 {len(candidates)} 条")

        for c in candidates:
            cid = c.get("id") or c.get("candidate_id")
            if not cid:
                self._inc("candidates", "failed")
                continue

            best_mape = None
            summary = c.get("summary") or {}
            for key in ("aggregate_baseline_score", "challenger_score", "mape_improvement"):
                v = summary.get(key) or c.get(key)
                if isinstance(v, (int, float)):
                    best_mape = float(v)
                    break

            cdata = {
                "id": _trunc(cid, 64),
                "slot": _trunc(c.get("slot") or "default", 64),
                "run_id": _trunc(c.get("run_id") or c.get("comparison_id") or "", 64),
                "workflow_id": _trunc(c.get("baseline_workflow_id") or c.get("challenger_workflow_id") or "", 128),
                "patch_signature": _trunc(c.get("applied_patch_fingerprint") or c.get("patch_signature") or "", 256),
                "best_mape": best_mape,
                "evidence": c.get("evidence_records") or c.get("evidence") or {},
                "status": _trunc(c.get("status") or "candidate", 32),
            }

            if self.dry_run:
                self._inc("candidates", "migrated")
                continue
            try:
                self.repo.upsert_candidate(cdata)
                self._inc("candidates", "migrated")
            except Exception as e:
                self._inc("candidates", "failed")
                self.failures.append(f"candidates/{cid}: {e}")

        # Promotions log
        promo_file = AR_DIR / "candidate_pool" / "baseline_comparison_promotions_log.json"
        promos = _read_json(promo_file)
        if isinstance(promos, list):
            for p in promos:
                cid = p.get("candidate_id") or p.get("id")
                if not cid:
                    continue
                if self.dry_run:
                    self._inc("promotions", "migrated")
                    continue
                try:
                    self.repo.append_promotion(
                        slot=_trunc(p.get("slot") or p.get("production_slot") or "default", 64),
                        candidate_id=_trunc(cid, 64),
                        action="promoted",
                        actor="system",
                        reason=p.get("note") or "",
                        payload=p,
                    )
                    self._inc("promotions", "migrated")
                except Exception as e:
                    self._inc("promotions", "failed")

        # Verification queue
        ver_file = AR_DIR / "candidate_pool" / "candidate_verification_queue.json"
        ver_data = _read_json(ver_file)
        items = (ver_data or {}).get("items") or []
        for item in items:
            iid = item.get("id")
            if not iid:
                continue
            if self.dry_run:
                self._inc("verifications", "migrated")
                continue
            try:
                self.repo.upsert_verification({
                    "id": _trunc(iid, 64),
                    "candidate_id": _trunc(item.get("candidate_id") or "", 64),
                    "slot": _trunc(item.get("slot") or "default", 64),
                    "source_run_id": _trunc(item.get("source_run_id"), 64),
                    "source_iteration": item.get("source_iteration"),
                    "status": _trunc(item.get("status") or "queued", 32),
                    "config_json": item.get("config") or item.get("verification_config") or {},
                    "evidence_json": item.get("evidence") or {},
                    "started_at": _parse_dt(item.get("started_at")),
                    "finished_at": _parse_dt(item.get("finished_at")),
                })
                self._inc("verifications", "migrated")
            except Exception as e:
                self._inc("verifications", "failed")
                self.failures.append(f"verifications/{iid}: {e}")

        print(f"  [promotions] {self._stat('promotions')}")
        print(f"  [verifications] {self._stat('verifications')}")


    # ------------------------------------------------------------------
    # 7. slots.json → deployment_slot + deployment_model_version
    # ------------------------------------------------------------------
    def migrate_deployment_slots(self) -> None:
        slots_file = DEPLOY_DIR / "slots.json"
        if not slots_file.exists():
            print("  [deployment_slots] 文件不存在，跳过")
            return

        slots = _read_json(slots_file)
        if not isinstance(slots, dict):
            print("  [deployment_slots] 文件格式异常，跳过")
            return

        print(f"  [deployment_slots] 发现 {len(slots)} 个 slot")

        for slot_name, slot_data in slots.items():
            if not isinstance(slot_data, dict):
                continue

            slot_row = {
                "slot": _trunc(slot_name, 64),
                "production_workflow_id": _trunc(
                    (slot_data.get("production_model") or {}).get("workflow_id"), 128
                ),
                "cooldown_days": int(slot_data.get("cooldown_days") or 3),
                "max_shadow_slots": int(slot_data.get("max_shadow_slots") or 3),
                "max_prelaunch_slots": int(slot_data.get("max_prelaunch_slots") or 3),
                "training_window_days": slot_data.get("training_window_days"),
                "switch_observation_days": slot_data.get("switch_observation_days") or slot_data.get("evaluation_window_days"),
            }

            if self.dry_run:
                self._inc("deployment_slots", "migrated")
            else:
                try:
                    self.deploy_repo.upsert_slot(slot_row)
                    self._inc("deployment_slots", "migrated")
                except Exception as e:
                    self._inc("deployment_slots", "failed")
                    self.failures.append(f"deployment_slots/{slot_name}: {e}")

            # 各版本（production + shadow + prelaunch）
            all_versions = []
            prod = slot_data.get("production_model")
            if isinstance(prod, dict) and prod.get("workflow_id"):
                prod = dict(prod)
                prod["status"] = "production"
                all_versions.append(prod)

            for m in (slot_data.get("shadow_models") or []):
                if isinstance(m, dict) and m.get("workflow_id"):
                    m = dict(m)
                    if "status" not in m:
                        m["status"] = "shadow"
                    all_versions.append(m)

            for m in (slot_data.get("prelaunch_models") or []):
                if isinstance(m, dict) and m.get("workflow_id"):
                    m = dict(m)
                    if "status" not in m:
                        m["status"] = "prelaunch"
                    all_versions.append(m)

            for mv in all_versions:
                vdata = {
                    "slot": _trunc(slot_name, 64),
                    "workflow_id": _trunc(mv.get("workflow_id"), 128),
                    "version_tag": _trunc(mv.get("version_tag"), 128),
                    "status": _trunc(mv.get("status") or "shadow", 32),
                    "accuracy_score": mv.get("accuracy_score"),
                    "consecutive_better_days": int(mv.get("consecutive_better_days") or 0),
                    "source_run_id": _trunc(mv.get("source_run_id"), 64),
                    "source_candidate_id": _trunc(mv.get("source_candidate_id"), 64),
                    "prelaunch_meta_json": mv.get("prelaunch_meta") if isinstance(mv.get("prelaunch_meta"), dict) else None,
                }
                if self.dry_run:
                    self._inc("deployment_versions", "migrated")
                else:
                    try:
                        self.deploy_repo.upsert_model_version(vdata)
                        self._inc("deployment_versions", "migrated")
                    except Exception as e:
                        self._inc("deployment_versions", "failed")
                        self.failures.append(f"deployment_versions/{slot_name}/{mv.get('workflow_id')}: {e}")

        print(f"  [deployment_versions] {self._stat('deployment_versions')}")

    # ------------------------------------------------------------------
    # 8. tasks.json → scheduler_task
    # ------------------------------------------------------------------
    def migrate_scheduler_tasks(self) -> None:
        tasks_file = SCHED_DIR / "tasks.json"
        if not tasks_file.exists():
            print("  [scheduler_tasks] 文件不存在，跳过")
            return

        data = _read_json(tasks_file)
        tasks = (data or {}).get("tasks") or []
        if not tasks and isinstance(data, list):
            tasks = data
        print(f"  [scheduler_tasks] 发现 {len(tasks)} 条")

        for task in tasks:
            tid = task.get("task_id") or task.get("id")
            if not tid:
                self._inc("scheduler_tasks", "skipped")
                continue

            tdata = {
                "task_id": _trunc(tid, 64),
                "name": _trunc(task.get("name") or tid, 128),
                "task_type": _trunc(task.get("task_type") or task.get("pipeline") or "unknown", 64),
                "slot": _trunc(task.get("slot") or task.get("pipeline") or "load_forecast", 64),
                "cron_expression": _trunc(task.get("cron_expression") or task.get("cron") or "0 1 * * *", 64),
                "enabled": bool(task.get("enabled", True)),
                "payload_json": {k: v for k, v in task.items()
                                 if k not in ("task_id", "id", "name", "task_type", "pipeline",
                                              "slot", "cron_expression", "cron", "enabled",
                                              "last_execution_time", "last_result")},
                "last_execution_time": _parse_dt(task.get("last_execution_time")),
                "last_result_json": task.get("last_result") if isinstance(task.get("last_result"), dict) else None,
            }

            if self.dry_run:
                self._inc("scheduler_tasks", "migrated")
                continue
            try:
                self.deploy_repo.upsert_task(tdata)
                self._inc("scheduler_tasks", "migrated")
            except Exception as e:
                self._inc("scheduler_tasks", "failed")
                self.failures.append(f"scheduler_tasks/{tid}: {e}")


    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def run(self, only: Optional[Set[str]] = None) -> None:
        def _should(name: str) -> bool:
            return only is None or name in only

        print(f"\n{'='*60}")
        print(f"AutoResearch 历史数据迁移 ({'DRY RUN — 不写入' if self.dry_run else '正式写入'})")
        print(f"{'='*60}\n")

        if _should("runs"):
            print("1. Run 快照 → experiment_run")
            self.migrate_runs()
        if _should("trials"):
            print("2. Trial 明细 → experiment_trial")
            self.migrate_trials()
        if _should("decisions"):
            print("3. 决策事件 → experiment_decision")
            self.migrate_decisions()
        if _should("insights"):
            print("4. Run Insights → experiment_run.run_insight")
            self.migrate_insights()
        if _should("knowledge"):
            print("5. Knowledge Claims → knowledge_claim")
            self.migrate_knowledge()
        if _should("candidates"):
            print("6. 候选池 + 复验队列 + Promotion → candidate_*")
            self.migrate_candidates()
        if _should("deployment"):
            print("7. 部署槽位 → deployment_slot + deployment_model_version")
            self.migrate_deployment_slots()
        if _should("scheduler"):
            print("8. Cron 任务 → scheduler_task")
            self.migrate_scheduler_tasks()

        # B' 类静态配置 sync（不受 --only 控制，每次都跑）
        print("9. 静态配置 B' 类 sync（registries/recipes/production_registry）")
        try:
            from services.db.repositories.registry_sync import sync_all_from_files
            s = sync_all_from_files()
            for table, stats in (s or {}).items():
                if isinstance(stats, dict):
                    print(f"   [{table}] scanned={stats.get('scanned',0)} upserted={stats.get('upserted',0)} unchanged={stats.get('unchanged',0)}")
        except Exception as e:
            print(f"   sync 失败（非致命）: {e}")

        # 汇总
        print(f"\n{'='*60}")
        print("迁移摘要")
        print(f"{'='*60}")
        total_migrated = total_failed = 0
        for key, stats in sorted(self.summary.items()):
            print(f"  {key:25s} migrated={stats['migrated']:4d} skipped={stats['skipped']:3d} failed={stats['failed']:3d}")
            total_migrated += stats["migrated"]
            total_failed += stats["failed"]
        print(f"  {'TOTAL':25s} migrated={total_migrated:4d} failed={total_failed:3d}")

        if self.failures:
            print(f"\n失败明细（前 20 条）:")
            for f in self.failures[:20]:
                print(f"  ✗ {f}")
        else:
            print("\n✅ 无失败")

        if total_failed > 0:
            print(f"\n⚠️  有 {total_failed} 条失败，详情见上。失败记录不影响已成功迁移的数据。")
        else:
            print(f"\n✅ 迁移完成，共迁移 {total_migrated} 条记录。")


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AutoResearch 历史 JSON → MySQL 一次性迁移"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="只统计，不真正写入 DB"
    )
    parser.add_argument(
        "--only", default=None,
        help="只迁移指定数据源（逗号分隔，可选值：runs,trials,decisions,insights,knowledge,candidates,deployment,scheduler）"
    )
    args = parser.parse_args()

    only: Optional[Set[str]] = None
    if args.only:
        only = {s.strip() for s in args.only.split(",") if s.strip()}

    migrator = AutoresearchMigrator(dry_run=args.dry_run)
    migrator.run(only=only)


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
