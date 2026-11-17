# @AI_GENERATED
"""Create and migrate an isolated MySQL database for the backend test suite.

Security properties:
- credentials are loaded at runtime from environment/.aip.local.env/config YAML;
- the connection URL and password are never printed or persisted;
- the source business database is never selected for DDL or DML;
- this script only creates the named test database and runs forward migrations.

Run from backend-service with the cp_web environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

TARGET_DATABASE = "aip_algo_platform_test_kiro_20260908"
ENV_PATH = Path("../.aip.local.env")
CONFIG_PATH = Path("configs/db.yaml")
REPORT_PATH = Path("../output/pv_e2e_validation/isolated_mysql_setup.json")


def _dotenv_values() -> dict[str, str]:
    if not ENV_PATH.is_file():
        return {}
    try:
        from dotenv import dotenv_values

        return {
            str(key): str(value)
            for key, value in dotenv_values(ENV_PATH).items()
            if key and value is not None
        }
    except ImportError:
        values: dict[str, str] = {}
        for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"").strip("'")
        return values


def _config_yaml() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return {}
    import yaml

    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return payload if isinstance(payload, dict) else {}


def _source_url() -> URL:
    env_file = _dotenv_values()
    yaml_config = _config_yaml()
    raw_url = str(
        os.environ.get("DB_CONNECTION_URL")
        or env_file.get("DB_CONNECTION_URL")
        or yaml_config.get("connection_url")
        or ""
    ).strip()
    if raw_url:
        url = make_url(raw_url)
    else:
        def value(*keys: str, default: str = "") -> str:
            for key in keys:
                raw = os.environ.get(key) or env_file.get(key) or yaml_config.get(key.lower())
                if raw not in (None, ""):
                    return str(raw)
            return default

        host = value("DB_HOST", "MYSQL_HOST")
        user = value("DB_USER", "MYSQL_USER")
        password = value("DB_PASSWORD", "MYSQL_PASSWORD")
        port = int(value("DB_PORT", "MYSQL_PORT", default="3306"))
        database = value("DB_NAME", "MYSQL_DATABASE", default="aip_algo_platform")
        if not host or not user or not password:
            raise RuntimeError(
                "No DB_CONNECTION_URL or complete DB_HOST/DB_USER/DB_PASSWORD runtime configuration"
            )
        url = URL.create(
            "mysql+pymysql",
            username=user,
            password=password,
            host=host,
            port=port,
            database=database,
        )

    if not str(url.drivername).startswith("mysql"):
        raise RuntimeError("Isolated integration database requires a MySQL source URL")
    if not url.host or not url.username:
        raise RuntimeError("MySQL source URL is missing host or username")
    return url.set(drivername="mysql+pymysql")


def _safe_report(payload: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(
            {
                "_comment": "@AI_GENERATED",
                **payload,
                "_comment_end": "@AI_GENERATED: end",
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


def main() -> None:
    source_url = _source_url()
    source_database = str(source_url.database or "")
    if source_database == TARGET_DATABASE:
        raise RuntimeError("Source and target database must differ")

    server_url = source_url.set(database=None)
    server_engine = create_engine(server_url, pool_pre_ping=True)
    try:
        with server_engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{TARGET_DATABASE}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            exists = connection.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.schemata "
                    "WHERE schema_name = :name"
                ),
                {"name": TARGET_DATABASE},
            ).scalar_one()
            if int(exists) != 1:
                raise RuntimeError("Target database creation could not be verified")
    finally:
        server_engine.dispose()

    target_url = source_url.set(database=TARGET_DATABASE)
    child_env = os.environ.copy()
    child_env.update(
        {
            "DB_CONNECTION_URL": target_url.render_as_string(hide_password=False),
            "DB_ENGINE": "mysql",
            "DB_ENABLED": "true",
            "DB_DUAL_WRITE": "false",
        }
    )
    migration = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        env=child_env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if migration.returncode != 0:
        _safe_report(
            {
                "status": "migration_failed",
                "source_database": source_database,
                "target_database": TARGET_DATABASE,
                "migration_returncode": migration.returncode,
                "migration_stderr_tail": migration.stderr[-4000:],
            }
        )
        raise RuntimeError("Alembic migration failed; see redacted setup report")

    target_engine = create_engine(target_url, pool_pre_ping=True)
    try:
        with target_engine.connect() as connection:
            selected_database = str(connection.execute(text("SELECT DATABASE()"))).strip()
            selected_database = str(connection.execute(text("SELECT DATABASE()"), {}).scalar_one())
            table_names = [
                str(row[0])
                for row in connection.execute(text("SHOW TABLES")).fetchall()
            ]
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            required_tables = {
                "training_samples",
                "point_labels",
                "point_label_ops",
                "label_ops",
                "day_labels",
                "day_label_ops",
            }
            missing_tables = sorted(required_tables - set(table_names))
            if selected_database != TARGET_DATABASE or missing_tables:
                raise RuntimeError(
                    f"Isolated schema verification failed: selected={selected_database!r}, "
                    f"missing_tables={missing_tables!r}"
                )
    finally:
        target_engine.dispose()

    _safe_report(
        {
            "status": "passed",
            "source_database": source_database,
            "target_database": TARGET_DATABASE,
            "source_and_target_are_distinct": source_database != TARGET_DATABASE,
            "selected_database": selected_database,
            "alembic_revision": str(revision),
            "table_count": len(table_names),
            "required_tables_present": True,
            "required_tables": sorted(required_tables),
            "credentials_persisted": False,
            "business_database_ddl_or_dml": False,
        }
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "target_database": TARGET_DATABASE,
                "alembic_revision": str(revision),
                "table_count": len(table_names),
                "report": REPORT_PATH.as_posix(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
