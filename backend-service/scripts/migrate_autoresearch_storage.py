#!/usr/bin/env python3
"""
AutoResearch 存储迁移脚本：将旧路径数据复制到新统一目录。

用法：
    python scripts/migrate_autoresearch_storage.py --dry-run   # 只打印，不写入
    python scripts/migrate_autoresearch_storage.py             # 实际复制

规则：
    - 只复制，不删除旧文件。
    - 目标已存在则跳过（不覆盖）。
    - JSON/JSONL 复制前验证可解析。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# 让 import services.autoresearch_paths 能工作
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services import autoresearch_paths as arp


def _is_valid_json(path: Path) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            json.load(f)
        return True
    except Exception:
        return False


def _is_valid_jsonl(path: Path) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    json.loads(line)
        return True
    except Exception:
        return False


def _copy_file(src: Path, dst: Path, dry_run: bool) -> str:
    """复制单个文件，返回状态描述。"""
    if dst.exists():
        return f"  SKIP (exists): {dst}"
    if not src.exists():
        return f"  SKIP (missing): {src}"
    if dry_run:
        return f"  COPY: {src} -> {dst}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    return f"  COPIED: {src} -> {dst}"


def migrate_run_snapshots(dry_run: bool) -> list[str]:
    """迁移旧 run 快照：{run_id}.json -> runs/{run_id}/snapshot.json"""
    results = []
    legacy_dir = arp.legacy_runs_dir()
    if not legacy_dir.exists():
        return ["  旧 runs 目录不存在，跳过"]
    for item in legacy_dir.iterdir():
        if item.is_file() and item.suffix == ".json":
            run_id = item.stem
            if not _is_valid_json(item):
                results.append(f"  SKIP (invalid JSON): {item}")
                continue
            dst = arp.snapshot_path(run_id)
            results.append(_copy_file(item, dst, dry_run))
        elif item.is_dir():
            run_id = item.name
            # trials.jsonl
            trials_src = item / "trials.jsonl"
            if trials_src.exists():
                trials_dst = arp.trial_ledger_path(run_id)
                if not _is_valid_jsonl(trials_src):
                    results.append(f"  SKIP (invalid JSONL): {trials_src}")
                else:
                    results.append(_copy_file(trials_src, trials_dst, dry_run))
            # decisions.jsonl
            decisions_src = item / "decisions.jsonl"
            if decisions_src.exists():
                decisions_dst = arp.decision_ledger_path(run_id)
                if not _is_valid_jsonl(decisions_src):
                    results.append(f"  SKIP (invalid JSONL): {decisions_src}")
                else:
                    results.append(_copy_file(decisions_src, decisions_dst, dry_run))
    return results


def migrate_insights(dry_run: bool) -> list[str]:
    """迁移 run insights"""
    results = []
    legacy_dir = arp.legacy_insights_dir()
    if not legacy_dir.exists():
        return ["  旧 insights 目录不存在，跳过"]
    for item in legacy_dir.iterdir():
        if not item.is_file() or not item.suffix == ".json":
            continue
        if item.name == "_index.json":
            dst = arp.insight_index_path()
        else:
            run_id = item.stem
            dst = arp.insight_path(run_id)
        if not _is_valid_json(item):
            results.append(f"  SKIP (invalid JSON): {item}")
            continue
        results.append(_copy_file(item, dst, dry_run))
    return results


def migrate_knowledge(dry_run: bool) -> list[str]:
    """迁移 knowledge claims（四层子目录）"""
    results = []
    legacy_dir = arp.legacy_knowledge_dir()
    if not legacy_dir.exists():
        return ["  旧 knowledge 目录不存在，跳过"]
    new_dir = arp.knowledge_dir()
    for subdir in legacy_dir.iterdir():
        if not subdir.is_dir():
            continue
        for item in subdir.iterdir():
            if not item.is_file() or not item.suffix == ".json":
                continue
            dst = new_dir / subdir.name / item.name
            if not _is_valid_json(item):
                results.append(f"  SKIP (invalid JSON): {item}")
                continue
            results.append(_copy_file(item, dst, dry_run))
    return results


def migrate_registries(dry_run: bool) -> list[str]:
    """迁移搜索空间注册表"""
    results = []
    legacy_dir = arp.legacy_registries_dir()
    if not legacy_dir.exists():
        return ["  旧 registries 目录不存在，跳过"]
    new_dir = arp.registries_dir()
    for item in legacy_dir.iterdir():
        if not item.is_file() or not item.suffix == ".json":
            continue
        dst = new_dir / item.name
        results.append(_copy_file(item, dst, dry_run))
    return results


def migrate_single_files(dry_run: bool) -> list[str]:
    """迁移单文件：memory、feature_recipes、slot_profiles、candidate_pool、promotions、production"""
    pairs = [
        (arp.legacy_memory_cases_path(), arp.memory_cases_path()),
        (arp.legacy_feature_recipes_path(), arp.feature_recipes_path()),
        (arp.legacy_workflow_slot_profiles_path(), arp.workflow_slot_profiles_path()),
        (arp.legacy_candidate_pool_path(), arp.candidate_pool_path()),
        (arp.legacy_promotions_log_path(), arp.promotions_log_path()),
        (arp.legacy_production_registry_path(), arp.production_registry_path()),
        (arp.legacy_dataset_registry_path(), arp.dataset_registry_path()),
    ]
    results = []
    for src, dst in pairs:
        if not src.exists():
            continue
        results.append(_copy_file(src, dst, dry_run))
    return results


def main():
    parser = argparse.ArgumentParser(description="迁移 AutoResearch 存储到统一目录")
    parser.add_argument("--dry-run", action="store_true", help="只打印将迁移的文件，不实际写入")
    args = parser.parse_args()

    dry_run = args.dry_run
    mode = "DRY-RUN" if dry_run else "MIGRATE"
    print(f"=== AutoResearch 存储迁移 [{mode}] ===")
    print(f"目标目录: {arp.AUTORESEARCH_DIR}")
    print()

    sections = [
        ("Run Snapshots & Trials", migrate_run_snapshots),
        ("Insights", migrate_insights),
        ("Knowledge", migrate_knowledge),
        ("Registries", migrate_registries),
        ("Single Files", migrate_single_files),
    ]

    total_copy = 0
    total_skip = 0
    for title, fn in sections:
        print(f"[{title}]")
        results = fn(dry_run)
        for line in results:
            print(line)
            if "COPY" in line and "SKIP" not in line:
                total_copy += 1
            elif "SKIP" in line:
                total_skip += 1
        print()

    print(f"--- 汇总：将复制 {total_copy} 个文件，跳过 {total_skip} 个 ---")
    if dry_run:
        print("（dry-run 模式，未实际写入）")


if __name__ == "__main__":
    main()
