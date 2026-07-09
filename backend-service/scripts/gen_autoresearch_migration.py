# -*- coding: utf-8 -*-
# @AI_GENERATED
"""
scripts/gen_autoresearch_migration.py — 生成 AutoResearch MySQL 迁移的 alembic revision

在 Windows 上因为 alembic CLI 走 subprocess 会被权限拒绝，改用 Python API 直接调。
用途：
    conda activate cp_web
    python scripts/gen_autoresearch_migration.py --generate   # 只生成 revision 脚本
    python scripts/gen_autoresearch_migration.py --upgrade    # 应用到数据库
    python scripts/gen_autoresearch_migration.py --both       # 先生成再应用

关联 spec：docs/specs/autoresearch-mysql-migration/tasks.md 0.2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 确保 backend-service/ 在 sys.path
_this_file = Path(__file__).resolve()
_backend_dir = _this_file.parent.parent  # scripts/x.py -> scripts/ -> backend-service/
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from services.db.config import DBConfig  # noqa: E402


def _escape_pct(value: str) -> str:
    """
    configparser 的 BasicInterpolation 会把单个 `%` 当作变量占位符前缀，
    连接串里如果含 URL-encoded 字符（比如密码里的 `%40` = `@`）会报 invalid interpolation syntax。
    这里把每个 `%` 转成 `%%` 转义。
    """
    return value.replace("%", "%%")


def _make_config() -> Config:
    """构造 alembic Config，注入真实数据库连接串。"""
    alembic_ini = _backend_dir / "alembic.ini"
    if not alembic_ini.exists():
        raise FileNotFoundError(f"alembic.ini not found at {alembic_ini}")

    cfg = Config(str(alembic_ini))
    db_cfg = DBConfig()
    cfg.set_main_option("sqlalchemy.url", _escape_pct(db_cfg.connection_url))
    # 保证 script_location 指向 backend-service/alembic
    cfg.set_main_option("script_location", str(_backend_dir / "alembic"))
    return cfg


def generate_revision(message: str = "add autoresearch and deployment tables") -> None:
    """基于 ORM metadata 与当前数据库对比，自动生成迁移脚本。"""
    cfg = _make_config()
    print(f"[gen] 生成迁移脚本 message='{message}'")
    command.revision(cfg, message=message, autogenerate=True)
    print("[gen] 完成，检查 alembic/versions/ 下的新文件")


def upgrade_head() -> None:
    """执行 alembic upgrade head，应用所有未执行的迁移。"""
    cfg = _make_config()
    print("[upgrade] 执行 alembic upgrade head")
    command.upgrade(cfg, "head")
    print("[upgrade] 完成")


def show_current() -> None:
    """打印当前数据库的 revision（诊断用）。"""
    cfg = _make_config()
    print("[current] 数据库当前 revision:")
    command.current(cfg, verbose=True)


def stamp(revision: str) -> None:
    """把数据库标记为指定 revision（不执行 SQL），用于把现有表纳入 alembic 管理。"""
    cfg = _make_config()
    print(f"[stamp] 标记数据库为 revision={revision}")
    command.stamp(cfg, revision)
    print("[stamp] 完成，alembic_version 表已建/更新")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成/执行 AutoResearch MySQL 迁移")
    parser.add_argument("--generate", action="store_true", help="生成 revision 脚本")
    parser.add_argument("--upgrade", action="store_true", help="应用到数据库")
    parser.add_argument("--both", action="store_true", help="先生成再应用")
    parser.add_argument("--current", action="store_true", help="显示当前 revision")
    parser.add_argument("--stamp", metavar="REV", help="把 DB 标记为指定 revision（不执行 SQL）")
    parser.add_argument(
        "--message",
        default="add autoresearch and deployment tables",
        help="revision 描述文本",
    )
    args = parser.parse_args()

    if args.current:
        show_current()
        return

    if args.stamp:
        stamp(args.stamp)
        return

    if not (args.generate or args.upgrade or args.both):
        parser.print_help()
        sys.exit(1)

    if args.both or args.generate:
        generate_revision(args.message)
    if args.both or args.upgrade:
        upgrade_head()


if __name__ == "__main__":
    main()
# @AI_GENERATED: end
