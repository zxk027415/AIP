# -*- coding: utf-8 -*-
"""
services/db/models/base.py — 共享 declarative base

所有 ORM 模型均从 Base 继承，便于 Alembic 统一管理元数据。
"""

from sqlalchemy.orm import declarative_base

Base = declarative_base()
