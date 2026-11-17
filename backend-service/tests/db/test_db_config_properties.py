# -*- coding: utf-8 -*-
"""
tests/db/test_db_config_properties.py

Feature: data-pipeline-db-integration

Property 1: 连接池配置验证 (validates Requirements 1.3)
  - max_connections ∈ [1,100]、idle_timeout ∈ [10,3600]、connection_lifetime ∈ [60,86400]
    范围内 => DBConfig 初始化成功
  - 超出范围 => 抛出 ValidationError

Property 3: 环境变量优先级 (validates Requirements 1.5)
  - 同一参数同时存在环境变量与 YAML 文件值时，DBConfig 总是使用环境变量的值
"""

import os
import tempfile
import textwrap
from pathlib import Path
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from services.db.config import DBConfig, ValidationError


# ---------------------------------------------------------------------------
# 辅助：构造一个仅含连接池参数的临时 db.yaml，绕过默认配置文件路径
# ---------------------------------------------------------------------------
def _make_yaml(content: str) -> Path:
    """写入临时 YAML 文件，返回 Path 对象（调用方负责清理）。"""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return Path(f.name)


# ===========================================================================
# Property 1 — 连接池配置验证
# Validates: Requirements 1.3
# ===========================================================================

@given(
    max_conn=st.integers(min_value=1, max_value=100),
    idle=st.integers(min_value=10, max_value=3600),
    lifetime=st.integers(min_value=60, max_value=86400),
)
@settings(max_examples=50)
def test_valid_pool_config_initializes_successfully(max_conn, idle, lifetime):
    """
    **Validates: Requirements 1.3**
    合法范围内的连接池参数 => DBConfig 初始化成功，且字段值与输入一致。
    """
    yaml_path = _make_yaml(
        textwrap.dedent(f"""\
            max_connections: {max_conn}
            idle_timeout: {idle}
            connection_lifetime: {lifetime}
        """)
    )
    try:
        cfg = DBConfig(_config_path=yaml_path)
        assert cfg.max_connections == max_conn
        assert cfg.idle_timeout == idle
        assert cfg.connection_lifetime == lifetime
    finally:
        yaml_path.unlink(missing_ok=True)


@pytest.mark.parametrize("field,env_key,bad_value,lo,hi", [
    ("max_connections",    "DB_POOL_MAX",          0,     1,   100),
    ("max_connections",    "DB_POOL_MAX",          101,   1,   100),
    ("idle_timeout",       "DB_POOL_IDLE_TIMEOUT", 9,     10,  3600),
    ("idle_timeout",       "DB_POOL_IDLE_TIMEOUT", 3601,  10,  3600),
    ("connection_lifetime","DB_POOL_CONN_LIFETIME", 59,   60,  86400),
    ("connection_lifetime","DB_POOL_CONN_LIFETIME", 86401,60,  86400),
])
def test_out_of_range_raises_validation_error(field, env_key, bad_value, lo, hi):
    """
    **Validates: Requirements 1.3**
    超出允许范围的连接池参数 => 抛出 ValidationError。
    """
    # 用一个空 YAML + 环境变量注入越界值，确保路径独立于本地 configs/db.yaml
    yaml_path = _make_yaml("")
    try:
        env_bak = os.environ.pop(env_key, None)
        os.environ[env_key] = str(bad_value)
        with pytest.raises(ValidationError):
            DBConfig(_config_path=yaml_path)
    finally:
        if env_bak is None:
            os.environ.pop(env_key, None)
        else:
            os.environ[env_key] = env_bak
        yaml_path.unlink(missing_ok=True)


@given(
    bad_max=st.one_of(st.integers(max_value=0), st.integers(min_value=101)),
)
@settings(max_examples=30)
def test_invalid_max_connections_raises(bad_max):
    """
    **Validates: Requirements 1.3**
    max_connections 超出 [1,100] => ValidationError（属性版）。
    """
    yaml_path = _make_yaml(f"max_connections: {bad_max}")
    try:
        with pytest.raises(ValidationError):
            DBConfig(_config_path=yaml_path)
    finally:
        yaml_path.unlink(missing_ok=True)


# ===========================================================================
# Property 3 — 环境变量优先级
# Validates: Requirements 1.5
# ===========================================================================

@given(
    yaml_val=st.integers(min_value=1, max_value=50),
    env_val=st.integers(min_value=51, max_value=100),
)
@settings(max_examples=50)
def test_env_overrides_yaml_for_max_connections(yaml_val, env_val):
    """
    **Validates: Requirements 1.5**
    环境变量 DB_POOL_MAX 与 YAML max_connections 同时存在时，DBConfig 使用环境变量的值。
    此处 yaml_val ∈ [1,50]，env_val ∈ [51,100]，两者不相交，断言简单。
    """
    yaml_path = _make_yaml(f"max_connections: {yaml_val}")
    env_bak = os.environ.pop("DB_POOL_MAX", None)
    try:
        os.environ["DB_POOL_MAX"] = str(env_val)
        cfg = DBConfig(_config_path=yaml_path)
        assert cfg.max_connections == env_val, (
            f"期望使用环境变量 {env_val}，实际得到 {cfg.max_connections}"
        )
    finally:
        if env_bak is None:
            os.environ.pop("DB_POOL_MAX", None)
        else:
            os.environ["DB_POOL_MAX"] = env_bak
        yaml_path.unlink(missing_ok=True)


@given(
    yaml_val=st.integers(min_value=10, max_value=1000),
    env_val=st.integers(min_value=1001, max_value=3600),
)
@settings(max_examples=50)
def test_env_overrides_yaml_for_idle_timeout(yaml_val, env_val):
    """
    **Validates: Requirements 1.5**
    环境变量 DB_POOL_IDLE_TIMEOUT 优先于 YAML idle_timeout。
    """
    yaml_path = _make_yaml(f"idle_timeout: {yaml_val}")
    env_bak = os.environ.pop("DB_POOL_IDLE_TIMEOUT", None)
    try:
        os.environ["DB_POOL_IDLE_TIMEOUT"] = str(env_val)
        cfg = DBConfig(_config_path=yaml_path)
        assert cfg.idle_timeout == env_val
    finally:
        if env_bak is None:
            os.environ.pop("DB_POOL_IDLE_TIMEOUT", None)
        else:
            os.environ["DB_POOL_IDLE_TIMEOUT"] = env_bak
        yaml_path.unlink(missing_ok=True)


@given(
    yaml_val=st.integers(min_value=60, max_value=3600),
    env_val=st.integers(min_value=3601, max_value=86400),
)
@settings(max_examples=50)
def test_env_overrides_yaml_for_connection_lifetime(yaml_val, env_val):
    """
    **Validates: Requirements 1.5**
    环境变量 DB_POOL_CONN_LIFETIME 优先于 YAML connection_lifetime。
    """
    yaml_path = _make_yaml(f"connection_lifetime: {yaml_val}")
    env_bak = os.environ.pop("DB_POOL_CONN_LIFETIME", None)
    try:
        os.environ["DB_POOL_CONN_LIFETIME"] = str(env_val)
        cfg = DBConfig(_config_path=yaml_path)
        assert cfg.connection_lifetime == env_val
    finally:
        if env_bak is None:
            os.environ.pop("DB_POOL_CONN_LIFETIME", None)
        else:
            os.environ["DB_POOL_CONN_LIFETIME"] = env_bak
        yaml_path.unlink(missing_ok=True)

# @AI_GENERATED: independent PV product-slot cron configuration
def test_pv_product_slot_crons_load_from_yaml_and_env(monkeypatch):
    for env_key in (
        "SCHED_PV_DAY_PREDICT_CRON",
        "SCHED_PV_POINT_REPLAY_CRON",
        "SCHED_PV_TSC_PREDICT_CRON",
    ):
        monkeypatch.delenv(env_key, raising=False)

    yaml_path = _make_yaml(
        textwrap.dedent(
            """\
            sched_pv_day_predict_cron: "10 3 * * *"
            sched_pv_point_replay_cron: "*/7 * * * *"
            sched_pv_tsc_predict_cron: "20 4 * * *"
            """
        )
    )
    try:
        cfg = DBConfig(_config_path=yaml_path)
        assert cfg.sched_pv_day_predict_cron == "10 3 * * *"
        assert cfg.sched_pv_point_replay_cron == "*/7 * * * *"
        assert cfg.sched_pv_tsc_predict_cron == "20 4 * * *"

        monkeypatch.setenv("SCHED_PV_TSC_PREDICT_CRON", "45 5 * * *")
        overridden = DBConfig(_config_path=yaml_path)
        assert overridden.sched_pv_tsc_predict_cron == "45 5 * * *"
    finally:
        yaml_path.unlink(missing_ok=True)
# @AI_GENERATED: end