# -*- coding: utf-8 -*-
# @AI_GENERATED: pv-fault-dual-path-serving 任务 1.3 —— 迁移与 ORM 幂等性单元测试
"""
tests/pv_dual_path/test_migration_idempotent.py
    —— 双路径生产接入：ORM 分区维度 + 迁移脚本幂等探测逻辑单元测试

Feature: pv-fault-dual-path-serving
需求：5.1（路径隔离分区键）、5.2（按 modeling_path 分区检索）、10.8（不破坏脏工作区/迁移幂等）

本测试**不连真实 MySQL**：
  1. ORM 层：直接从 SQLAlchemy 表元数据断言主键/列/索引形态（纯内存，无 DB）。
  2. 迁移脚本：用 FakeSession 模拟 information_schema 探测返回值，
     验证「已存在→跳过」的幂等分支，以及 dry_run 只产计划、绝不执行任何
     结构变更 DDL/DML（对应 Req10.8：可重复运行、不破坏既有数据）。

被测对象：
  - services/db/models/pv_fault.py :: DevicePredictionCursor / PredictionRecord
  - scripts/migrations/20260815_add_modeling_path_partition.py（文件名以数字开头，
    经 importlib 按相对路径加载为模块 `migration_mod`）
"""
from __future__ import annotations

import importlib.util
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from services.db.models.pv_fault import DevicePredictionCursor, PredictionRecord


# ---------------------------------------------------------------------------
# 加载迁移脚本（文件名以数字开头，不能按包名 import，用 importlib 按相对路径载入）
# tests/pv_dual_path/xxx.py -> tests -> backend-service
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = _BACKEND / "scripts" / "migrations" / "20260815_add_modeling_path_partition.py"


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migration_mod", _MIGRATION_PATH)
    assert spec and spec.loader, f"无法加载迁移脚本：{_MIGRATION_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


migration_mod = _load_migration_module()


# ---------------------------------------------------------------------------
# FakeResult / FakeSession —— 模拟 SQLAlchemy Session.execute()
# 只解析 SQL 文本 + 参数，返回可配置的探测结果；记录所有执行过的语句，
# 便于断言「哪些是只读探测、哪些是结构变更」。
# ---------------------------------------------------------------------------
class FakeResult:
    def __init__(self, rows, rowcount=None):
        self._rows = list(rows)
        self._rowcount = rowcount if rowcount is not None else len(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    @property
    def rowcount(self):
        return self._rowcount


# 判定「结构/数据变更语句」的前缀（大写归一后）
_MUTATING_PREFIXES = ("ALTER ", "CREATE INDEX", "DROP ", "UPDATE ", "TRUNCATE", "DELETE ")


class FakeSession:
    """内存 fake：模拟 information_schema 探测与 DDL/DML 执行。

    构造参数（均为「当前库已存在什么」的模拟状态）：
      - database        : SELECT DATABASE() 返回的库名
      - existing_columns: set[(table, column)]，命中则 _column_exists 判 True
      - existing_indexes: set[(table, index)]，命中则 _index_exists 判 True
      - pk_map          : {table: [pk_col, ...]}，供 _pk_columns 返回
      - null_counts     : {(table, column): int}，供 _null_count 返回（缺省 0）
    """

    def __init__(self, *, database="aip_algo_platform", existing_columns=None,
                 existing_indexes=None, pk_map=None, null_counts=None):
        self.database = database
        self.existing_columns = set(existing_columns or set())
        self.existing_indexes = set(existing_indexes or set())
        self.pk_map = dict(pk_map or {})
        self.null_counts = dict(null_counts or {})
        # 记录所有执行过的语句：list[(sql_str, params)]
        self.executed = []

    # 便捷视图：仅结构/数据变更语句（去除只读探测 SELECT）
    @property
    def mutating_statements(self):
        out = []
        for sql, _params in self.executed:
            norm = " ".join(sql.split()).upper()
            if any(norm.startswith(p) for p in _MUTATING_PREFIXES):
                out.append(" ".join(sql.split()))
        return out

    def execute(self, statement, params=None):
        sql = str(statement)
        self.executed.append((sql, params))
        norm = " ".join(sql.split())
        upper = norm.upper()

        # --- 只读探测路由 ---
        if upper.startswith("SELECT DATABASE()"):
            return FakeResult([(self.database,)])

        if "INFORMATION_SCHEMA.COLUMNS" in upper:
            key = (params["tbl"], params["col"])
            return FakeResult([(1 if key in self.existing_columns else 0,)])

        if "INFORMATION_SCHEMA.STATISTICS" in upper:
            key = (params["tbl"], params["idx"])
            return FakeResult([(1 if key in self.existing_indexes else 0,)])

        if "INFORMATION_SCHEMA.KEY_COLUMN_USAGE" in upper:
            cols = self.pk_map.get(params["tbl"], [])
            return FakeResult([(c,) for c in cols])

        if upper.startswith("SELECT COUNT(*)") and "IS NULL" in upper:
            # SELECT COUNT(*) FROM `table` WHERE `column` IS NULL
            idents = re.findall(r"`([^`]+)`", sql)
            table, column = idents[0], idents[1]
            n = int(self.null_counts.get((table, column), 0))
            return FakeResult([(n,)], rowcount=n)

        # --- 其余视为变更语句（ALTER/CREATE INDEX/UPDATE/MODIFY 等）---
        # UPDATE 回填需要 rowcount：用 null_counts 的当前值近似（回填影响的正是 NULL 行数）
        if upper.startswith("UPDATE "):
            idents = re.findall(r"`([^`]+)`", sql)
            table, column = idents[0], idents[1]
            n = int(self.null_counts.get((table, column), 0))
            return FakeResult([], rowcount=n)
        return FakeResult([])


# ===========================================================================
# 第一部分：ORM 层形态断言（不连库）
# Validates: Requirements 5.1, 5.2
# ===========================================================================
def test_cursor_primary_key_includes_slot_and_modeling_path():
    """游标 ORM 主键按 slot + modeling_path + 设备三元组分区，与 20260816 迁移一致。"""
    assert list(DevicePredictionCursor.__table__.primary_key.columns.keys()) == [
        "slot", "modeling_path", "site_id", "device_id", "branch_id",
    ]
    assert DevicePredictionCursor.__table__.c.slot.default.arg == "pv_fault"


def test_cursor_primary_key_includes_modeling_path():
    """DevicePredictionCursor 主键必须为含 modeling_path 的复合键（Req5.1 路径分区隔离）。"""
    pk_cols = [c.name for c in DevicePredictionCursor.__table__.primary_key.columns]
    assert "modeling_path" in pk_cols, f"主键缺少 modeling_path：{pk_cols}"
    assert set(pk_cols) >= {"site_id", "device_id", "branch_id", "modeling_path"}, (
        f"主键列不完整：{pk_cols}"
    )


def test_cursor_modeling_path_not_null_with_default():
    """游标 modeling_path 列非空且默认 legacy_day（历史行回填后的分区语义）。"""
    col = DevicePredictionCursor.__table__.columns["modeling_path"]
    assert col.nullable is False
    # server_default 存在且指向 legacy_day
    assert col.server_default is not None
    assert "legacy_day" in str(col.server_default.arg)


def test_prediction_record_modeling_path_not_null():
    """PredictionRecord.modeling_path 必须存在且非空（Req5.2）。"""
    cols = PredictionRecord.__table__.columns
    assert "modeling_path" in cols, "PredictionRecord 缺少 modeling_path 列"
    assert cols["modeling_path"].nullable is False


def test_prediction_record_path_index_present_and_leads_with_path():
    """存在索引 ix_prediction_records_path_device，且以 modeling_path 领衔（按路径分区检索）。"""
    indexes = {idx.name: idx for idx in PredictionRecord.__table__.indexes}
    assert "ix_prediction_records_path_device" in indexes, (
        f"缺少路径分区索引，现有索引：{list(indexes)}"
    )
    idx = indexes["ix_prediction_records_path_device"]
    idx_cols = [c.name for c in idx.columns]
    assert idx_cols[0] == "modeling_path", f"索引应以 modeling_path 领衔：{idx_cols}"
    assert set(idx_cols) >= {
        "modeling_path", "site_id", "device_id", "branch_id", "business_date"
    }, f"索引列不完整：{idx_cols}"


# ===========================================================================
# 第二部分：迁移脚本探测辅助（只读，不改库）
# ===========================================================================
def test_current_database_reads_selected_db():
    session = FakeSession(database="aip_algo_platform")
    assert migration_mod._current_database(session) == "aip_algo_platform"


def test_current_database_raises_when_empty():
    session = FakeSession(database="")
    with pytest.raises(RuntimeError):
        migration_mod._current_database(session)


def test_column_exists_true_and_false():
    session = FakeSession(existing_columns={("prediction_records", "modeling_path")})
    assert migration_mod._column_exists(session, "db", "prediction_records", "modeling_path") is True
    assert migration_mod._column_exists(session, "db", "prediction_records", "other_col") is False


def test_index_exists_true_and_false():
    session = FakeSession(existing_indexes={("prediction_records", "ix_prediction_records_path_device")})
    assert migration_mod._index_exists(
        session, "db", "prediction_records", "ix_prediction_records_path_device"
    ) is True
    assert migration_mod._index_exists(session, "db", "prediction_records", "nope") is False


def test_pk_columns_returns_ordered_list():
    session = FakeSession(pk_map={"device_prediction_cursor": ["site_id", "device_id", "branch_id"]})
    assert migration_mod._pk_columns(session, "db", "device_prediction_cursor") == [
        "site_id", "device_id", "branch_id"
    ]


# ===========================================================================
# 第三部分：幂等分支 —— 「已存在则跳过」
# Validates: Requirements 5.1, 5.2, 10.8
# ===========================================================================
def test_add_column_skipped_when_column_exists():
    """列已存在 → 不再产生 ADD COLUMN，actions 不变、无变更语句执行。"""
    session = FakeSession(existing_columns={("prediction_records", "modeling_path")})
    actions = []
    migration_mod._add_column_if_missing(session, "db", "prediction_records", dry_run=False, actions=actions)
    assert actions == []
    assert session.mutating_statements == []


def test_add_column_planned_when_missing():
    """列缺失 + dry_run → 只产计划，不执行任何变更语句。"""
    session = FakeSession()  # 无既有列
    actions = []
    migration_mod._add_column_if_missing(session, "db", "prediction_records", dry_run=True, actions=actions)
    assert len(actions) == 1
    assert "ADD COLUMN" in actions[0]
    assert session.mutating_statements == []  # dry_run 绝不执行


def test_add_index_skipped_when_index_exists():
    """索引已存在 → 跳过 CREATE INDEX。"""
    session = FakeSession(
        existing_indexes={("prediction_records", "ix_prediction_records_path_device")}
    )
    actions = []
    migration_mod._add_path_index_if_missing(session, "db", dry_run=False, actions=actions)
    assert actions == []
    assert session.mutating_statements == []


def test_rebuild_pk_skipped_when_already_composite():
    """主键已含 modeling_path → 跳过重建（不 DROP/ADD PRIMARY KEY）。"""
    session = FakeSession(
        pk_map={"device_prediction_cursor": ["site_id", "device_id", "branch_id", "modeling_path"]}
    )
    actions = []
    migration_mod._rebuild_cursor_pk_if_needed(session, "db", dry_run=False, actions=actions)
    assert actions == []
    assert session.mutating_statements == []


def test_rebuild_pk_executes_single_atomic_alter_when_missing():
    """主键缺 modeling_path → 单条 DROP+ADD PRIMARY KEY 原子重建。"""
    session = FakeSession(
        pk_map={"device_prediction_cursor": ["site_id", "device_id", "branch_id"]}
    )
    actions = []
    migration_mod._rebuild_cursor_pk_if_needed(session, "db", dry_run=False, actions=actions)
    assert len(actions) == 1
    stmt = actions[0].upper()
    assert "DROP PRIMARY KEY" in stmt and "ADD PRIMARY KEY" in stmt
    # 单条语句内完成，恰好执行一次
    assert len(session.mutating_statements) == 1


# ===========================================================================
# 第四部分：回填只对空值生效
# Validates: Requirements 5.1, 10.8
# ===========================================================================
def test_backfill_updates_only_null_rows_when_present():
    """存在 NULL 行 → 执行一次 UPDATE 回填 legacy_day，再 MODIFY 为 NOT NULL。"""
    session = FakeSession(
        existing_columns={("prediction_records", "modeling_path")},
        null_counts={("prediction_records", "modeling_path"): 7},
    )
    actions = []
    migration_mod._backfill_and_set_not_null(session, "db", "prediction_records", dry_run=False, actions=actions)
    updates = [s for s in session.mutating_statements if s.upper().startswith("UPDATE")]
    modifies = [s for s in session.mutating_statements if "MODIFY COLUMN" in s.upper()]
    assert len(updates) == 1, f"应恰好执行一次回填 UPDATE：{session.mutating_statements}"
    assert len(modifies) == 1, "应执行一次 MODIFY 置非空"
    # 回填参数为 legacy_day
    update_call = next(c for c in session.executed if str(c[0]).upper().strip().startswith("UPDATE"))
    assert update_call[1] == {"p": "legacy_day"}


def test_backfill_skips_update_when_no_null_rows():
    """无 NULL 行 → 不执行 UPDATE（只做等价 MODIFY，回填仅对空值生效）。"""
    session = FakeSession(
        existing_columns={("prediction_records", "modeling_path")},
        null_counts={("prediction_records", "modeling_path"): 0},
    )
    actions = []
    migration_mod._backfill_and_set_not_null(session, "db", "prediction_records", dry_run=False, actions=actions)
    updates = [s for s in session.mutating_statements if s.upper().startswith("UPDATE")]
    assert updates == [], "无 NULL 行时不应执行回填 UPDATE"


# ===========================================================================
# 第五部分：run(dry_run=True) 只产计划、绝不执行结构变更（可重复运行安全，Req10.8）
# ===========================================================================
def _patch_adapter(monkeypatch, session):
    """把迁移模块里的 DBConfig / DBAdapter 换成不连库的 fake，get_sync_session 产出给定 session。"""
    class _FakeAdapter:
        def __init__(self, *_a, **_k):
            pass

        def get_sync_session(self):
            from contextlib import contextmanager

            @contextmanager
            def _cm():
                yield session

            return _cm()

        def dispose(self):
            pass

    monkeypatch.setattr(migration_mod, "DBConfig", lambda *a, **k: object())
    monkeypatch.setattr(migration_mod, "DBAdapter", _FakeAdapter)


def test_run_dry_run_produces_plan_without_mutating(monkeypatch):
    """全新库 + dry_run：产出非空计划，但绝不执行任何 ALTER/CREATE/UPDATE。"""
    session = FakeSession()  # 全新库：无列、无索引、旧复合主键（无 modeling_path）
    session.pk_map = {"device_prediction_cursor": ["site_id", "device_id", "branch_id"]}
    _patch_adapter(monkeypatch, session)

    result = migration_mod.run(dry_run=True)

    assert result["dry_run"] is True
    assert result["action_count"] > 0, "dry_run 应产出迁移计划"
    assert session.mutating_statements == [], (
        f"dry_run 不应执行任何结构变更，却执行了：{session.mutating_statements}"
    )


def test_run_execute_idempotent_when_everything_exists(monkeypatch):
    """所有分区结构已就位 + 无 NULL 行：重复执行不再加列/建索引/重建主键。"""
    session = FakeSession(
        existing_columns={
            ("prediction_records", "modeling_path"),
            ("device_prediction_cursor", "modeling_path"),
        },
        existing_indexes={("prediction_records", "ix_prediction_records_path_device")},
        pk_map={"device_prediction_cursor": [
            "site_id", "device_id", "branch_id", "modeling_path"
        ]},
        null_counts={},  # 全为 0
    )
    _patch_adapter(monkeypatch, session)

    result = migration_mod.run(dry_run=False)

    assert result["dry_run"] is False
    stmts = session.mutating_statements
    # 幂等重跑：不得再出现加列 / 建索引 / 重建主键
    assert not any("ADD COLUMN" in s.upper() for s in stmts), stmts
    assert not any(s.upper().startswith("CREATE INDEX") for s in stmts), stmts
    assert not any("DROP PRIMARY KEY" in s.upper() for s in stmts), stmts
    # 也不应有回填 UPDATE（无 NULL 行）
    assert not any(s.upper().startswith("UPDATE") for s in stmts), stmts


# ===========================================================================
# 第六部分：任务 2.4 新版本迁移 —— 四表、Epoch、旧 Seq 事实确认
# Validates: Requirements 5.6, 10.8, 13.1, 14.1, 14.9, 15.1
# ===========================================================================
_RUNTIME_MIGRATION_PATH = (
    _BACKEND / "scripts" / "migrations" / "20260816_add_dual_path_runtime_schema.py"
)


def _load_runtime_migration_module():
    spec = importlib.util.spec_from_file_location("runtime_migration_mod", _RUNTIME_MIGRATION_PATH)
    assert spec and spec.loader, f"无法加载迁移脚本：{_RUNTIME_MIGRATION_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


runtime_migration_mod = _load_runtime_migration_module()


class RuntimeMigrationSession:
    """任务 2.4 迁移专用 fake；只模拟探测结果并记录潜在 DDL/DML。"""

    def __init__(
        self,
        *,
        tables=None,
        columns=None,
        indexes=None,
        pk_map=None,
        epoch_identity=None,
        scope_counts=None,
        claim_counts=None,
        prediction_rows=None,
        scope_rows=None,
    ):
        self.tables = set(tables or set())
        self.columns = set(columns or set())
        self.indexes = set(indexes or set())
        self.pk_map = dict(pk_map or {})
        self.epoch_identity = epoch_identity
        self.scope_counts = dict(scope_counts or {})
        self.claim_counts = dict(claim_counts or {})
        self.prediction_rows = list(prediction_rows or [])
        self.scope_rows = list(scope_rows or [])
        self.executed = []

    @property
    def mutations(self):
        prefixes = ("ALTER ", "CREATE ", "UPDATE ", "INSERT ", "DELETE ", "DROP ", "TRUNCATE ")
        return [
            " ".join(sql.split())
            for sql, _params in self.executed
            if " ".join(sql.split()).upper().startswith(prefixes)
        ]

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        self.executed.append((sql, params))
        upper = " ".join(sql.split()).upper()
        if upper.startswith("SELECT DATABASE()"):
            return FakeResult([("aip_algo_platform",)])
        if "INFORMATION_SCHEMA.TABLES" in upper:
            return FakeResult([(1 if params["tbl"] in self.tables else 0,)])
        if "INFORMATION_SCHEMA.COLUMNS" in upper:
            return FakeResult([(1 if (params["tbl"], params["col"]) in self.columns else 0,)])
        if "INFORMATION_SCHEMA.STATISTICS" in upper:
            return FakeResult([(1 if (params["tbl"], params["idx"]) in self.indexes else 0,)])
        if "INFORMATION_SCHEMA.KEY_COLUMN_USAGE" in upper:
            return FakeResult([(name,) for name in self.pk_map.get(params["tbl"], [])])
        if "FROM PATH_ACTIVATION_EPOCHS" in upper:
            return FakeResult([self.epoch_identity] if self.epoch_identity else [])
        if "COUNT(*) FROM PATH_ACTIVATION_DEVICE_SCOPES" in upper:
            key = (params["site_id"], params["device_id"], params["branch_id"])
            return FakeResult([(self.scope_counts.get(key, 0),)])
        if "COUNT(*) FROM PATH_ACTIVATION_LANE_CLAIMS" in upper:
            key = (params["site_id"], params["device_id"], params["branch_id"])
            return FakeResult([(self.claim_counts.get(key, 0),)])
        if "JSON_UNQUOTE(JSON_EXTRACT" in upper:
            return FakeResult(self.prediction_rows)
        if "FROM PATH_ACTIVATION_DEVICE_SCOPES WHERE" in upper:
            return FakeResult(self.scope_rows)
        return FakeResult([])


def test_runtime_migration_empty_schema_dry_run_is_safe():
    """空库只规划四张归属表；缺失旧基础表时不猜测建表或执行 ALTER。"""
    session = RuntimeMigrationSession()
    result = runtime_migration_mod.migrate_session(
        session,
        dry_run=True,
        production_path="legacy_day",
        watermarks=[],
        batch_payloads=[],
    )
    create_tables = [action for action in result["actions"] if action.startswith("CREATE TABLE")]
    assert len(create_tables) == 4
    assert any("SKIP missing base table device_prediction_cursor" in action for action in result["actions"])
    assert any("SKIP missing base table prediction_records" in action for action in result["actions"])
    assert session.mutations == []


def test_runtime_migration_partial_schema_only_plans_missing_objects():
    """已有部分表/列时，仅补缺失对象，保留既有表。"""
    session = RuntimeMigrationSession(
        tables={
            "seq_device_day_ledger",
            "device_prediction_cursor",
            "prediction_records",
        },
        columns={
            ("device_prediction_cursor", "slot"),
            ("prediction_records", "slot"),
        },
        indexes={("prediction_records", "ix_prediction_records_slot_path_device")},
        pk_map={
            "device_prediction_cursor": ["slot", "modeling_path", "site_id", "device_id", "branch_id"]
        },
    )
    result = runtime_migration_mod.migrate_session(
        session,
        dry_run=True,
        production_path="seq_annotation",
        watermarks=[],
        batch_payloads=[],
    )
    creates = [action for action in result["actions"] if action.startswith("CREATE TABLE")]
    assert len(creates) == 3
    assert not any("CREATE TABLE `seq_device_day_ledger`" in action for action in creates)
    assert any("ADD COLUMN `cursor_semantics`" in action for action in result["actions"])
    assert not any("CREATE INDEX `ix_prediction_records_slot_path_device`" in action for action in result["actions"])
    assert session.mutations == []


def test_runtime_migration_repeated_schema_does_not_recreate_or_rekey():
    """重复迁移不重复建四表、索引或主键，现有 Epoch 身份一致时复用。"""
    all_tables = set(runtime_migration_mod._NEW_TABLE_DDLS) | {
        "device_prediction_cursor",
        "prediction_records",
    }
    session = RuntimeMigrationSession(
        tables=all_tables,
        columns={
            ("device_prediction_cursor", "slot"),
            ("device_prediction_cursor", "cursor_semantics"),
            ("prediction_records", "slot"),
        },
        indexes={("prediction_records", "ix_prediction_records_slot_path_device")},
        pk_map={
            "device_prediction_cursor": ["slot", "modeling_path", "site_id", "device_id", "branch_id"]
        },
        epoch_identity=("pv_fault", "legacy_day", "cutover_only"),
    )
    result = runtime_migration_mod.migrate_session(
        session,
        dry_run=True,
        production_path="legacy_day",
        watermarks=[],
        batch_payloads=[],
    )
    assert not any(action.startswith("CREATE TABLE") for action in result["actions"])
    assert not any("ADD COLUMN" in action for action in result["actions"])
    assert not any("ADD PRIMARY KEY" in action for action in result["actions"])
    assert not any(action.startswith("CREATE INDEX") for action in result["actions"])
    assert not any("INSERT INTO path_activation_epochs" in action for action in result["actions"])
    assert session.mutations == []


def _valid_legacy_seq_payload():
    return {
        "dataset_version": "data/seq_annotation_datasets/sample.json",
        "model_ref": "seq-model-v1",
        "modeling_path": "seq_annotation",
        "prediction_granularity": "point",
        "predictions": [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b1",
                "time_window": "2026-08-14",
            }
        ],
        "cursor_advance_times": [
            {
                "site_id": "s1",
                "device_id": "d1",
                "branch_id": "b1",
                "last_predicted_time": "2026-08-14T23:55:00",
            }
        ],
        "created_at": "2026-08-15T00:10:00",
    }


def test_legacy_seq_success_requires_batch_record_and_epoch_scope():
    """旧 Seq succeeded 必须同时满足不可变批次、DB 批次引用和 Epoch 日期边界。"""
    candidates = runtime_migration_mod._extract_confirmable_seq_units(
        _valid_legacy_seq_payload(), "pred-seq-confirmed"
    )
    assert len(candidates) == 1
    records = {("s1", "d1", "b1", date(2026, 8, 14), "pred-seq-confirmed")}
    scopes = {("s1", "d1", "b1"): date(2026, 8, 14)}
    assert runtime_migration_mod._filter_confirmed_seq_facts(candidates, records, scopes) == candidates

    assert runtime_migration_mod._filter_confirmed_seq_facts(candidates, set(), scopes) == []
    assert runtime_migration_mod._filter_confirmed_seq_facts(
        candidates, records, {("s1", "d1", "b1"): date(2026, 8, 15)}
    ) == []


def test_legacy_seq_corrupt_or_ambiguous_batch_is_not_guessed():
    """批次缺不可变证据、游标确认或日期时，不生成任何 succeeded 候选。"""
    missing_dataset = _valid_legacy_seq_payload()
    missing_dataset["dataset_version"] = ""
    assert runtime_migration_mod._extract_confirmable_seq_units(missing_dataset, "batch") == []

    missing_advances = _valid_legacy_seq_payload()
    missing_advances["cursor_advance_times"] = []
    assert runtime_migration_mod._extract_confirmable_seq_units(missing_advances, "batch") == []

    invalid_date = _valid_legacy_seq_payload()
    invalid_date["predictions"][0]["time_window"] = "not-a-date"
    assert runtime_migration_mod._extract_confirmable_seq_units(invalid_date, "batch") == []


def test_initial_epoch_uses_latest_closed_day_and_keeps_empty_device_boundary_null():
    """有水位设备取前一已结束日；无数据设备不伪造 effective_from 或 production claim。"""
    watermarks = [
        runtime_migration_mod.DeviceWatermark("s1", "d1", "b1", datetime(2026, 8, 16, 10, 0)),
        runtime_migration_mod.DeviceWatermark("s2", "d2", "b2", None),
    ]
    session = RuntimeMigrationSession()
    actions = []
    runtime_migration_mod._ensure_initial_cutover_epoch(
        session, "legacy_day", watermarks, True, actions
    )
    scope_actions = [action for action in actions if action.startswith("INSERT INTO path_activation_device_scopes")]
    claim_actions = [action for action in actions if action.startswith("INSERT INTO path_activation_lane_claims")]
    assert len(scope_actions) == 2
    assert len(claim_actions) == 1
    assert runtime_migration_mod._latest_closed_day(watermarks[0].watermark) == date(2026, 8, 15)
    assert runtime_migration_mod._latest_closed_day(None) is None


def test_runtime_migration_exposes_deferred_task_5_2_hooks():
    """旧模型/旧审计只暴露可替换调用接口，本迁移不自行分类。"""
    calls = []

    def model_hook(_session, dry_run, actions):
        calls.append(("models", dry_run))
        actions.append("model hook called")

    def audit_hook(_session, dry_run, actions):
        calls.append(("audit", dry_run))
        actions.append("audit hook called")

    session = RuntimeMigrationSession()
    hooks = runtime_migration_mod.CompatibilityHooks(model_hook, audit_hook)
    runtime_migration_mod.migrate_session(
        session,
        dry_run=True,
        production_path="legacy_day",
        watermarks=[],
        batch_payloads=[],
        compatibility_hooks=hooks,
    )
    assert calls == [("models", True), ("audit", True)]
# @AI_GENERATED: end
