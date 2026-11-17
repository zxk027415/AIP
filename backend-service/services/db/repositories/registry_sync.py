# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/db/repositories/registry_sync.py — 静态配置文件 → MySQL 镜像的 sync 工具

B' 类双写：**文件为源 + DB 镜像**。三份 Git-tracked 静态配置文件通过启动钩子或 API
手动触发 sync，文件的 SHA-256 变了才 upsert 到 DB。

覆盖的表：
  - search_space_registry            ← data/autoresearch/registries/*.json
  - feature_recipe                   ← data/autoresearch/recipes/feature_recipes.json
  - production_workflow_registry     ← data/autoresearch/production/production_workflow_registry.json

Sync 入口：
  1. 启动钩子：main.py startup → sync_all_from_files()
  2. API：POST /api/autoresearch/registries/reload 等
  3. 手动：python -c "from services.db.repositories.registry_sync import sync_all_from_files; sync_all_from_files()"

关联文档：docs/specs/autoresearch-mysql-migration/design.md 第 11-13 节
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models.registry import (
    FeatureRecipe,
    ProductionWorkflowRegistry,
    SearchSpaceRegistry,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径常量（相对 backend-service/ 目录，跨机器一致性关键）
# ---------------------------------------------------------------------------
# 本文件位于 backend-service/services/db/repositories/registry_sync.py
# 向上三级到 backend-service/
_THIS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _THIS_DIR.parent.parent.parent
_DATA_DIR = _BACKEND_DIR / "data"

# 三份权威配置文件的位置
SEARCH_SPACE_REGISTRIES_DIR = _DATA_DIR / "autoresearch" / "registries"
FEATURE_RECIPES_FILE = _DATA_DIR / "autoresearch" / "recipes" / "feature_recipes.json"
PRODUCTION_WORKFLOW_REGISTRY_FILE = (
    _DATA_DIR / "autoresearch" / "production" / "production_workflow_registry.json"
)

# Legacy 目录兜底（Phase 3 前保留）
LEGACY_SEARCH_SPACE_REGISTRIES_DIR = _DATA_DIR / "autoresearch_search_registries"


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    """安全读取 JSON 文件，失败返回 None。"""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        return {"data": json.loads(raw.decode("utf-8")), "hash": _sha256(raw)}
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("registry_sync: failed to read %s: %s", path, exc)
        return None


def _relpath_to_backend(path: Path) -> str:
    """把绝对路径转成相对 backend-service/ 的字符串（跨机器一致）。"""
    try:
        return os.path.relpath(str(path), start=str(_BACKEND_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# RegistrySyncRepository — CRUD + Sync
# ---------------------------------------------------------------------------

class RegistrySyncRepository:
    """B' 类静态配置文件与 DB 的 sync 工具。

    构造参数 `adapter` 只需实现 `get_sync_session()` 返回 context manager。
    正式代码走 `services.db.repositories._LightweightAdapter`，避免 DBAdapter
    初始化时的 alembic subprocess 卡住。测试可传 mock。
    """

    def __init__(self, adapter) -> None:
        self._adapter = adapter

    # -------- search_space_registry --------

    def upsert_search_space_registry(self, row_data: Dict[str, Any]) -> SearchSpaceRegistry:
        if "registry_id" not in row_data:
            raise ValueError("row_data must contain 'registry_id'")
        with self._adapter.get_sync_session() as session:
            obj = session.get(SearchSpaceRegistry, row_data["registry_id"])
            if obj is None:
                obj = SearchSpaceRegistry(**row_data)
                session.add(obj)
            else:
                for k, v in row_data.items():
                    setattr(obj, k, v)
            obj.updated_at = datetime.utcnow()
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_search_space_registry(
        self, registry_id: str
    ) -> Optional[SearchSpaceRegistry]:
        with self._adapter.get_sync_session() as session:
            obj = session.get(SearchSpaceRegistry, registry_id)
            if obj is not None:
                session.expunge(obj)
            return obj

    def list_search_space_registries(self) -> List[SearchSpaceRegistry]:
        with self._adapter.get_sync_session() as session:
            rows = (
                session.query(SearchSpaceRegistry)
                .order_by(SearchSpaceRegistry.registry_id.asc())
                .all()
            )
            session.expunge_all()
            return rows

    def sync_search_space_registries(self) -> Dict[str, Any]:
        """扫描 registries/*.json，对比 content_hash，变了就 upsert 到 DB。

        Returns:
            {"scanned": int, "upserted": int, "unchanged": int, "errors": [str]}
        """
        summary = {"scanned": 0, "upserted": 0, "unchanged": 0, "errors": []}
        candidates: List[Path] = []
        for base in (SEARCH_SPACE_REGISTRIES_DIR, LEGACY_SEARCH_SPACE_REGISTRIES_DIR):
            if base.exists():
                candidates.extend(base.glob("*.json"))

        # 按 registry_id 去重（新目录优先）
        seen: Dict[str, Path] = {}
        for p in candidates:
            registry_id = p.stem
            if registry_id not in seen:
                seen[registry_id] = p
            else:
                # 已存在时优先新目录（SEARCH_SPACE_REGISTRIES_DIR 排在前）
                if SEARCH_SPACE_REGISTRIES_DIR in p.parents:
                    seen[registry_id] = p

        for registry_id, path in sorted(seen.items()):
            summary["scanned"] += 1
            payload = _read_json(path)
            if payload is None:
                summary["errors"].append(f"read failed: {path}")
                continue
            data = payload["data"]
            content_hash = payload["hash"]

            existing = self.get_search_space_registry(registry_id)
            if existing and existing.content_hash == content_hash:
                summary["unchanged"] += 1
                continue

            # 提取 description（v1/v2/v3 都有该顶层字段）
            description = data.get("description")
            # v1/v2 用 layers，v3 用 actions
            layers_json = data.get("layers")
            actions_json = data.get("actions")
            # version 优先取顶层数字，否则递增
            file_version = data.get("version")
            if isinstance(file_version, str):
                # 处理 "3.0.0" 这种 semver
                try:
                    file_version = int(file_version.split(".")[0])
                except (ValueError, AttributeError):
                    file_version = (existing.version + 1) if existing else 1
            elif not isinstance(file_version, int):
                file_version = (existing.version + 1) if existing else 1

            self.upsert_search_space_registry(
                {
                    "registry_id": registry_id,
                    "version": file_version,
                    "description": description,
                    "layers_json": layers_json,
                    "actions_json": actions_json,
                    "source_path": _relpath_to_backend(path),
                    "content_hash": content_hash,
                    "synced_at": datetime.utcnow(),
                }
            )
            summary["upserted"] += 1

        logger.info(
            "registry_sync.sync_search_space_registries: scanned=%d upserted=%d unchanged=%d errors=%d",
            summary["scanned"], summary["upserted"], summary["unchanged"], len(summary["errors"]),
        )
        return summary

    # -------- feature_recipe --------

    def upsert_feature_recipe(self, row_data: Dict[str, Any]) -> FeatureRecipe:
        if "recipe_id" not in row_data:
            raise ValueError("row_data must contain 'recipe_id'")
        with self._adapter.get_sync_session() as session:
            obj = session.get(FeatureRecipe, row_data["recipe_id"])
            if obj is None:
                obj = FeatureRecipe(**row_data)
                session.add(obj)
            else:
                for k, v in row_data.items():
                    setattr(obj, k, v)
            obj.updated_at = datetime.utcnow()
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_feature_recipe(self, recipe_id: str) -> Optional[FeatureRecipe]:
        with self._adapter.get_sync_session() as session:
            obj = session.get(FeatureRecipe, recipe_id)
            if obj is not None:
                session.expunge(obj)
            return obj

    def list_feature_recipes(self) -> List[FeatureRecipe]:
        with self._adapter.get_sync_session() as session:
            rows = session.query(FeatureRecipe).all()
            session.expunge_all()
            return rows

    def sync_feature_recipes(self) -> Dict[str, Any]:
        """扫描 feature_recipes.json，把每个 recipe 拆行 upsert。

        兼容两种文件结构：
          A) `{"notes": [...], "recipes": [{"recipe_id": "...", "title": "...", ...}, ...]}` （当前生产结构）
          B) `{"<recipe_id>": {"description": ..., "patch": {...}}, ...}` （早期结构）
        """
        summary = {"scanned": 0, "upserted": 0, "unchanged": 0, "errors": []}
        path = FEATURE_RECIPES_FILE
        if not path.exists():
            logger.info("registry_sync.sync_feature_recipes: file not found: %s", path)
            return summary

        payload = _read_json(path)
        if payload is None:
            summary["errors"].append(f"read failed: {path}")
            return summary

        data = payload["data"]
        source_path = _relpath_to_backend(path)

        if not isinstance(data, dict):
            summary["errors"].append(f"feature_recipes.json top level not a dict: {type(data).__name__}")
            return summary

        # 提取所有 recipe 项，兼容 A/B 两种结构
        recipe_items: List[Dict[str, Any]] = []
        if isinstance(data.get("recipes"), list):
            # 结构 A：list of {recipe_id: ..., ...}
            for item in data["recipes"]:
                if isinstance(item, dict) and item.get("recipe_id"):
                    recipe_items.append(item)
        else:
            # 结构 B：{recipe_id: {...}}
            for rid, val in data.items():
                if isinstance(val, dict):
                    recipe_items.append({"recipe_id": rid, **val})

        for recipe in recipe_items:
            summary["scanned"] += 1
            recipe_id = recipe.get("recipe_id")
            if not recipe_id:
                summary["errors"].append(f"skip entry missing recipe_id: {recipe}")
                continue

            recipe_bytes = json.dumps(recipe, ensure_ascii=False, sort_keys=True).encode("utf-8")
            recipe_hash = _sha256(recipe_bytes)

            existing = self.get_feature_recipe(recipe_id)
            if existing and existing.content_hash == recipe_hash:
                summary["unchanged"] += 1
                continue

            description = recipe.get("description") or recipe.get("desc") or recipe.get("title")
            # 除 metadata 字段外都视作 patch 内容
            patch_json = {
                k: v for k, v in recipe.items()
                if k not in ("recipe_id", "description", "desc", "title")
            }

            self.upsert_feature_recipe(
                {
                    "recipe_id": recipe_id,
                    "description": description,
                    "patch_json": patch_json,
                    "source_path": source_path,
                    "content_hash": recipe_hash,
                    "synced_at": datetime.utcnow(),
                }
            )
            summary["upserted"] += 1

        logger.info(
            "registry_sync.sync_feature_recipes: scanned=%d upserted=%d unchanged=%d errors=%d",
            summary["scanned"], summary["upserted"], summary["unchanged"], len(summary["errors"]),
        )
        return summary

    # -------- production_workflow_registry --------

    def upsert_production_workflow_registry(
        self, row_data: Dict[str, Any]
    ) -> ProductionWorkflowRegistry:
        if "slot" not in row_data:
            raise ValueError("row_data must contain 'slot'")
        with self._adapter.get_sync_session() as session:
            obj = session.get(ProductionWorkflowRegistry, row_data["slot"])
            if obj is None:
                obj = ProductionWorkflowRegistry(**row_data)
                session.add(obj)
            else:
                for k, v in row_data.items():
                    setattr(obj, k, v)
            obj.updated_at = datetime.utcnow()
            session.flush()
            session.refresh(obj)
            session.expunge(obj)
            return obj

    def get_production_workflow_registry(
        self, slot: str
    ) -> Optional[ProductionWorkflowRegistry]:
        with self._adapter.get_sync_session() as session:
            obj = session.get(ProductionWorkflowRegistry, slot)
            if obj is not None:
                session.expunge(obj)
            return obj

    def list_production_workflow_registry(self) -> List[ProductionWorkflowRegistry]:
        with self._adapter.get_sync_session() as session:
            rows = session.query(ProductionWorkflowRegistry).all()
            session.expunge_all()
            return rows

    def sync_production_workflow_registry(self) -> Dict[str, Any]:
        """扫描 production_workflow_registry.json，按 slot 拆行 upsert。

        兼容两种文件结构：
          A) `{"slots": {"<slot>": {"workflow_id": "...", ...}, ...}}` （当前生产结构）
          B) `{"<slot>": {"workflow_id": "...", ...}, ...}` （早期结构）
        """
        summary = {"scanned": 0, "upserted": 0, "unchanged": 0, "errors": []}
        path = PRODUCTION_WORKFLOW_REGISTRY_FILE
        if not path.exists():
            logger.info(
                "registry_sync.sync_production_workflow_registry: file not found: %s", path
            )
            return summary

        payload = _read_json(path)
        if payload is None:
            summary["errors"].append(f"read failed: {path}")
            return summary

        raw = payload["data"]
        source_path = _relpath_to_backend(path)

        if not isinstance(raw, dict):
            summary["errors"].append(
                f"production_workflow_registry.json top level not a dict: {type(raw).__name__}"
            )
            return summary

        # 兼容 A/B 两种结构：优先看 raw["slots"]，否则把顶层当作 {slot: entry}
        if isinstance(raw.get("slots"), dict):
            data = raw["slots"]
        else:
            data = raw

        for slot, entry in data.items():
            summary["scanned"] += 1
            if not isinstance(entry, dict):
                summary["errors"].append(f"slot {slot} entry not a dict")
                continue

            entry_bytes = json.dumps(entry, ensure_ascii=False, sort_keys=True).encode("utf-8")
            entry_hash = _sha256(entry_bytes)

            existing = self.get_production_workflow_registry(slot)
            if existing and existing.content_hash == entry_hash:
                summary["unchanged"] += 1
                continue

            workflow_id = entry.get("workflow_id") or entry.get("production_workflow_id")
            if not workflow_id:
                summary["errors"].append(f"slot {slot} missing workflow_id")
                continue

            version_tag = entry.get("version_tag") or entry.get("version")
            meta = {k: v for k, v in entry.items() if k not in ("workflow_id", "production_workflow_id", "version_tag", "version")}

            self.upsert_production_workflow_registry(
                {
                    "slot": slot,
                    "workflow_id": str(workflow_id),
                    "version_tag": str(version_tag) if version_tag else None,
                    "meta_json": meta,
                    "source_path": source_path,
                    "content_hash": entry_hash,
                    "synced_at": datetime.utcnow(),
                }
            )
            summary["upserted"] += 1

        logger.info(
            "registry_sync.sync_production_workflow_registry: scanned=%d upserted=%d unchanged=%d errors=%d",
            summary["scanned"], summary["upserted"], summary["unchanged"], len(summary["errors"]),
        )
        return summary

    # -------- Sync all --------

    def sync_all_from_files(self) -> Dict[str, Any]:
        """一次性 sync 全部三份配置文件。启动钩子 / API 都调这个。"""
        return {
            "search_space_registry": self.sync_search_space_registries(),
            "feature_recipe": self.sync_feature_recipes(),
            "production_workflow_registry": self.sync_production_workflow_registry(),
        }


# ---------------------------------------------------------------------------
# 模块级便捷入口（供启动钩子直接调用，不需要外部构造 adapter）
# ---------------------------------------------------------------------------

def sync_all_from_files() -> Dict[str, Any]:
    """启动钩子入口：一次同步全部三份配置。异常降级 warning 不阻塞启动。

    复用 `services.db.repositories.get_registry_sync_repo()` 的惰性单例（走轻量 adapter）。
    """
    try:
        from services.db.repositories import get_registry_sync_repo
        repo = get_registry_sync_repo()
        if repo is None:
            return {"error": "RegistrySyncRepository not available"}
        return repo.sync_all_from_files()
    except Exception as exc:
        logger.warning("registry_sync.sync_all_from_files failed (non-fatal): %s", exc)
        return {"error": str(exc)}

# @AI_GENERATED: end
