# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
services/db/models/registry.py — 静态配置镜像表 ORM 模型（B' 类：文件为源 + DB 镜像）

这三张表都是「本地 JSON 文件是权威源，MySQL 只做运行时镜像」的双写模式：
  - 文件由 Git 追踪，人工/管理界面编辑
  - 服务启动时 sync 钩子读文件 → 算 content_hash → 变了就 upsert 到 DB
  - 业务代码读 DB（跨机器统一），DB miss 时兜底读文件

对应文件：
  - SearchSpaceRegistry           ← data/autoresearch/registries/{load_forecast_v1/v2/v3}.json
  - FeatureRecipe                 ← data/autoresearch/recipes/feature_recipes.json
  - ProductionWorkflowRegistry    ← data/autoresearch/production/production_workflow_registry.json

关联文档：docs/specs/autoresearch-mysql-migration/design.md 第 11-13 节
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CHAR,
    JSON,
    DateTime,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SearchSpaceRegistry(Base):
    """AutoResearch 搜索空间注册表 — 文件为源 + DB 镜像。

    字段职责：
      - registry_id     — 主键，如 load_forecast_v1 / v2 / v3
      - version         — 内容版本号（每次文件变化自增或按语义版本存）
      - description     — 描述文本（从文件顶层拎出，便于列表页展示）
      - layers_json     — v1/v2 使用的分层结构（training/feature/model/data）
      - actions_json    — v3 使用的 actions 数组（typed research actions）
      - source_path     — 相对路径记录（跨机器一致性）
      - content_hash    — SHA-256（判断文件是否变化）
      - synced_at       — 上次 sync 时间
    """

    __tablename__ = "search_space_registry"

    registry_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str] = mapped_column(String(512), nullable=True)
    layers_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    actions_json: Mapped[list] = mapped_column(JSON, nullable=True)
    source_path: Mapped[str] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class FeatureRecipe(Base):
    """AutoResearch 特征配方 — 文件为源 + DB 镜像。

    feature_recipes.json 结构：{ "<recipe_id>": {...}, ... }
    入库时按 recipe_id 拆行（一个文件多行）。

    字段职责：
      - recipe_id       — 主键（通常是 functionId 或语义 ID）
      - description     — 描述
      - patch_json      — 该配方对应的结构补丁（node_param / structure_switch 等）
      - source_path / content_hash / synced_at / updated_at — 同 SearchSpaceRegistry
    """

    __tablename__ = "feature_recipe"

    recipe_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(String(512), nullable=True)
    patch_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    source_path: Mapped[str] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class ProductionWorkflowRegistry(Base):
    """生产工作流注册表 — 文件为源 + DB 镜像。

    production_workflow_registry.json 结构：{ "<slot>": {...}, ... }
    入库时按 slot 拆行（一个文件多行）。

    与 deployment_slot 表的区别：
      - deployment_slot          — 运行时状态（有 updated_at、accuracy 等动态字段）
      - production_workflow_registry — 静态"哪个 slot 用哪个 workflow"的规约，由文件维护

    字段职责：
      - slot            — 主键
      - workflow_id     — 生产工作流 ID
      - version_tag     — 版本标签
      - meta_json       — 其他元数据（描述、tags 等）
      - source_path / content_hash / synced_at / updated_at — 同上
    """

    __tablename__ = "production_workflow_registry"

    slot: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version_tag: Mapped[str] = mapped_column(String(128), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, nullable=True)
    source_path: Mapped[str] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

# @AI_GENERATED: end
