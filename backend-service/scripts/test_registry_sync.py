# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
scripts/test_registry_sync.py — 手动触发 B' 类静态配置 sync 到 MySQL 测试

用法：
    conda activate cp_web
    python scripts/test_registry_sync.py

作用：
    - sync 一次 registries + feature_recipes + production_workflow_registry
    - 打印 sync 摘要
    - 打印 DB 里各表当前的行数（验证入库效果）
"""
from __future__ import annotations

import sys
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from services.db.adapter import DBAdapter
from services.db.config import DBConfig
from services.db.repositories.registry_sync import RegistrySyncRepository


def main() -> None:
    adapter = DBAdapter(DBConfig())
    repo = RegistrySyncRepository(adapter)

    print("=" * 60)
    print("Sync 前的 DB 状态：")
    print(f"  search_space_registry rows        = {len(repo.list_search_space_registries())}")
    print(f"  feature_recipe rows               = {len(repo.list_feature_recipes())}")
    print(f"  production_workflow_registry rows = {len(repo.list_production_workflow_registry())}")

    print("=" * 60)
    print("执行 sync_all_from_files()...")
    summary = repo.sync_all_from_files()
    for table, s in summary.items():
        print(f"  [{table}] scanned={s['scanned']} upserted={s['upserted']} unchanged={s['unchanged']} errors={len(s['errors'])}")
        for err in s["errors"][:5]:
            print(f"    ERROR: {err}")

    print("=" * 60)
    print("Sync 后的 DB 状态：")
    for row in repo.list_search_space_registries():
        print(f"  search_space_registry: {row.registry_id} v{row.version} hash={row.content_hash[:12]}... src={row.source_path}")
    for row in repo.list_feature_recipes():
        print(f"  feature_recipe: {row.recipe_id} hash={row.content_hash[:12]}...")
    for row in repo.list_production_workflow_registry():
        print(f"  production_workflow_registry: slot={row.slot} workflow_id={row.workflow_id} version_tag={row.version_tag}")

    print("=" * 60)
    print("再次 sync（验证 content_hash 命中，upserted 应全为 0，unchanged 才对）：")
    summary2 = repo.sync_all_from_files()
    for table, s in summary2.items():
        print(f"  [{table}] scanned={s['scanned']} upserted={s['upserted']} unchanged={s['unchanged']} errors={len(s['errors'])}")


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
