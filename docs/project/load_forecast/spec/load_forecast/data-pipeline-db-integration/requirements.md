# Requirements Document

## Introduction

本特性将 AIP 平台中两条独立的数据管线（负荷预测 AutoResearch 和光伏故障诊断）从当前的文件存储（JSON/SQLite/Parquet）迁移到正式的关系型数据库，并实现定时任务拉取实际站点数据、执行滚动预测、回填精度指标的生产级闭环。

两条管线在数据库层面完全独立（不同 schema 或不同数据库实例），可独立部署和运维。初期使用本地 MySQL 开发验证（用户本地已有 Homebrew MySQL 9.6.0 运行，root 无密码，已有 `aip_algo_platform` 库），通过抽象层设计使后续可无缝对接公司 MySQL 或其他数据库引擎。

## Glossary

- **DB_Adapter**: 数据库抽象层，定义统一的连接、查询、事务接口，隐藏底层数据库差异；本地开发主用 MySQL，未来可扩展支持公司 MySQL（远程）及 PostgreSQL
- **Load_Forecast_Pipeline**: 负荷预测数据管线，对应 AutoResearch 实验结果、精度运营（precision_ops）和预上线模块的数据流
- **PV_Fault_Pipeline**: 光伏故障诊断数据管线，对应 `fault-diag-algo-release-3.1` 模块的训练/预测数据流
- **Scheduler**: 定时任务调度器，按配置周期触发数据拉取和预测执行
- **Station_Data_Source**: 电站实测数据源，即公司数据库中每日更新的传感器/电表数据
- **Rolling_Prediction**: 滚动预测，使用当前生产模型对最新数据做前向预测
- **Accuracy_Backfill**: 精度回填，当实际值到达后与预测值对比计算 MAPE 等指标
- **Migration_Tool**: 数据迁移工具，将现有 JSON/SQLite/Parquet 数据一次性导入新数据库
- **Connection_Pool**: 数据库连接池，管理和复用数据库连接以提升并发性能
- **Precision_Ops_Module**: 精度运营模块，即 `backend-service/services/precision_ops/` 下的版本管理、精度跟踪、预上线观察等服务

## Requirements

### Requirement 1: 数据库抽象层

**User Story:** As a developer, I want a database abstraction layer that hides the underlying database engine, so that I can switch between local MySQL and company database without changing business logic.

#### Acceptance Criteria

1. THE DB_Adapter SHALL expose a unified interface for connection management, query execution, and transaction control independent of the underlying database engine
2. THE DB_Adapter SHALL support MySQL as the primary backend for local development, and SHALL be designed to support additional database engines (company MySQL at remote hosts, PostgreSQL) via the abstraction layer without changes to business logic
3. THE DB_Adapter SHALL use a Connection_Pool with configurable maximum connections (default: 10, range: 1–100), idle timeout (default: 300 seconds, range: 10–3600 seconds), and connection lifetime (default: 3600 seconds, range: 60–86400 seconds)
4. IF a database connection attempt fails, THEN THE DB_Adapter SHALL retry up to 3 times with exponential backoff starting at 1 second (base delay 1s, multiplier 2×, maximum delay 8 seconds) before raising an error indicating the failure reason
5. THE DB_Adapter SHALL read all connection parameters (host, port, database name, credentials) from environment variables or a configuration file, with environment variables taking precedence over configuration file values, and with no hardcoded connection strings
6. THE DB_Adapter SHALL support both synchronous and asynchronous query execution to accommodate FastAPI async handlers and background worker threads
7. WHEN the DB_Adapter is initialized, THE DB_Adapter SHALL validate the connection by executing a health-check query and run pending schema migrations automatically
8. IF a schema migration fails during initialization, THEN THE DB_Adapter SHALL roll back the failed migration, log the migration error with the failing migration identifier, and raise an error preventing application startup
9. IF all connections in the Connection_Pool are in use and a new connection is requested, THEN THE DB_Adapter SHALL queue the request and wait up to 30 seconds (configurable, range: 1–120 seconds) before raising a pool-exhaustion error

### Requirement 2: 负荷预测数据库 Schema

**User Story:** As a developer, I want a dedicated database schema for load forecast data, so that AutoResearch experiment results and precision_ops operational data are stored in a structured, queryable format.

#### Acceptance Criteria

1. THE Load_Forecast_Pipeline SHALL use a dedicated database schema (or database instance) named `load_forecast` where no table shares a namespace or foreign-key reference with PV_Fault_Pipeline tables, and cross-pipeline queries return zero rows from the other pipeline's data
2. THE Load_Forecast_Pipeline schema SHALL include tables for: experiment runs, candidate pool, knowledge claims, prediction results, accuracy metrics, version registry, and prelaunch queue
3. WHEN an experiment run reaches a terminal state (completed, failed, or cancelled), THE Load_Forecast_Pipeline SHALL persist the run insight, candidate evidence, and novelty audit records accumulated up to that point to the database, with a `terminal_status` field indicating the final state
4. THE Load_Forecast_Pipeline schema SHALL preserve the existing data semantics of `prediction_store.py` (slot, workflow_id, version_tag, prediction_cycle_id, forecast_timestamp, predicted_value, actual_value, status)
5. THE Load_Forecast_Pipeline schema SHALL partition data by slot identifier such that queries scoped to one slot never return rows belonging to another slot, and adding a new slot requires no migration or schema change
6. WHEN a station data record is ingested, THE Load_Forecast_Pipeline SHALL store the record with station_id, timestamp, feature_name, and value fields
7. IF a database write fails during experiment run persistence or station data ingestion, THEN THE Load_Forecast_Pipeline SHALL return an error response indicating the failure reason and SHALL NOT leave partially written run records in a committed state

### Requirement 3: 光伏故障诊断数据库 Schema

**User Story:** As a developer, I want a dedicated database schema for PV fault diagnosis data, so that labeled training data, prediction inputs, and diagnosis results are managed independently from the load forecast pipeline.

#### Acceptance Criteria

1. THE PV_Fault_Pipeline SHALL use a dedicated database file or schema named `pv_fault_diag` that is fully isolated from Load_Forecast_Pipeline data, with no shared tables or foreign-key references
2. THE PV_Fault_Pipeline schema SHALL include at minimum: (a) a `training_samples` table with columns `id`, `time`, `site_id`, `device_id`, `branch_id`, `value`, `i_cal`, `label`, `ingested_at`; (b) a `prediction_records` table with columns `id`, `model_version_id`, `site_id`, `device_id`, `branch_id`, `input_feature_json`, `predicted_label`, `confidence`, `executed_at`; (c) a `diagnosis_results` table with columns `id`, `prediction_record_id`, `fault_type_name`, `severity`, `created_at`; (d) a `model_versions` table with columns `id`, `version_tag`, `training_sample_count`, `label_space_version`, `created_at`, `artifact_path`
3. THE PV_Fault_Pipeline schema SHALL support ingestion of Parquet-format labeled data matching the `all_labeled_combined.parquet` column schema (`time`, `site_id`, `device_id`, `branch_id`, `value`, `i_cal`, `label`), deduplicating rows by the composite key (`time`, `site_id`, `device_id`, `branch_id`) so that re-ingestion of the same file does not create duplicate records
4. WHEN a diagnosis prediction is executed, THE PV_Fault_Pipeline SHALL store a `prediction_records` row containing the serialized input feature vector as JSON, the integer predicted fault label, a confidence score in the range [0.0, 1.0], the reference `model_version_id` of the model used, and the UTC execution timestamp
5. THE PV_Fault_Pipeline schema SHALL provide indexed query capability to filter `training_samples` by any combination of `site_id` (exact match), time range (inclusive start, exclusive end), and `label` (exact match or set membership), returning results ordered by `time` ascending
6. IF a Parquet ingestion operation fails due to missing required columns or data type mismatch, THEN THE PV_Fault_Pipeline SHALL reject the entire file without partial writes and return an error indication specifying which columns are missing or which type conversions failed

### Requirement 4: 负荷预测定时任务

**User Story:** As a platform operator, I want scheduled tasks that automatically pull station data, run rolling predictions, and update accuracy metrics, so that the platform operates in a production-like cadence without manual intervention.

#### Acceptance Criteria

1. THE Scheduler SHALL support configurable cron-style schedules with a minimum granularity of 1 minute for each task (data pull, prediction execution, accuracy backfill)
2. WHEN the data pull task triggers, THE Load_Forecast_Pipeline SHALL query the Station_Data_Source for new records since the last successful pull timestamp and insert them into the local database within a timeout of 120 seconds per query batch
3. WHEN the prediction task triggers, THE Load_Forecast_Pipeline SHALL load the current production model, generate predictions for the configured forecast horizon (default 24 hours ahead) using the most recent contiguous data window required by the model, and store prediction results with timestamps in the database
4. WHEN actual values become available for a previously predicted time slot, THE Load_Forecast_Pipeline SHALL compare predictions against actuals, compute MAPE, and update rolling accuracy metrics over the configured evaluation window (default last 30 days) in the database
5. WHILE a prelaunch model is in observing status, THE Scheduler SHALL execute shadow predictions alongside the production model on each prediction cycle and store shadow results separately from production results
6. IF a scheduled task fails, THEN THE Scheduler SHALL log the error with context (task name, trigger time, error details), retry once after a configurable delay (default 60 seconds, range 10–600 seconds), and mark the cycle as failed if the retry also fails
7. THE Scheduler SHALL expose a status API endpoint showing the last execution time, next scheduled time, and the last 20 failure records for each task
8. IF a task trigger fires while the same task type is still executing from a previous trigger, THEN THE Scheduler SHALL skip the new trigger, log a warning indicating schedule overlap, and report the skip in the status API
9. WHEN the Scheduler starts after a period of downtime, THE Scheduler SHALL execute at most one catch-up run per task for the most recent missed schedule rather than replaying all missed intervals

### Requirement 5: 光伏故障诊断定时任务

**User Story:** As a platform operator, I want scheduled tasks for the PV fault diagnosis pipeline that pull sensor data and run fault predictions independently from the load forecast pipeline.

#### Acceptance Criteria

1. THE Scheduler SHALL manage PV_Fault_Pipeline tasks independently from Load_Forecast_Pipeline tasks, with separate configurable schedule intervals and a separate failure counter per task type
2. WHEN the PV data pull task triggers, THE PV_Fault_Pipeline SHALL query the Station_Data_Source for PV sensor records inserted after the last successful pull timestamp (high-water mark) and insert them into the `pv_fault_diag` schema, processing at most 10 000 records per execution
3. WHEN the PV prediction task triggers, THE PV_Fault_Pipeline SHALL load the fault diagnosis model identified by the configured model reference, run predictions on records in `pv_fault_diag` that have no diagnosis result, and store diagnosis results (fault type, confidence score, diagnosed timestamp) in the database
4. THE PV_Fault_Pipeline scheduled tasks SHALL be independently startable and stoppable without interrupting, pausing, or altering the schedule state of Load_Forecast_Pipeline scheduled tasks
5. IF the Station_Data_Source is unreachable or returns an error during a PV data pull execution, THEN THE PV_Fault_Pipeline SHALL record the failure in its failure tracker, skip the current pull cycle, and retry at the next scheduled interval without affecting subsequent prediction task scheduling
6. IF the configured fault diagnosis model file is missing or fails to load, THEN THE PV_Fault_Pipeline SHALL record the failure, skip the current prediction cycle, and emit a notification event indicating model unavailability

### Requirement 6: 现有数据迁移

**User Story:** As a developer, I want a migration tool that moves existing JSON/SQLite/Parquet data into the new database, so that historical experiment results and operational state are preserved.

#### Acceptance Criteria

1. THE Migration_Tool SHALL migrate existing `precision_ops` JSON files (accuracy_metrics, prelaunch_queue, version_registry per slot) into the `load_forecast` schema, mapping each JSON key to the corresponding database column as defined by the target schema
2. THE Migration_Tool SHALL migrate existing `predictions.db` SQLite records into the `load_forecast` prediction results table, preserving all source columns and all source rows; after migration the target table row count SHALL equal the source table row count for each migrated table
3. THE Migration_Tool SHALL migrate `all_labeled_combined.parquet` into the `pv_fault_diag` training samples table
4. THE Migration_Tool SHALL be idempotent: it SHALL use source-record natural keys (e.g., slot_id + timestamp for precision_ops, primary key for predictions.db rows, composite key for parquet) to detect duplicates, and running the migration multiple times on the same source data SHALL produce the same database state without inserting duplicate records
5. IF a source file is corrupt, unreadable, or fails to parse, THEN THE Migration_Tool SHALL log an error message indicating the file path and failure reason, skip that file, and continue migrating remaining files
6. WHEN migration completes, THE Migration_Tool SHALL report a summary containing: total records migrated, total records skipped (with per-file skip counts), total source files processed, and elapsed time in seconds
7. IF the target database schema does not exist when the Migration_Tool is invoked, THEN THE Migration_Tool SHALL exit with an error indicating the missing schema, without modifying any data

### Requirement 7: 兼容性与回退

**User Story:** As a developer, I want the new database layer to coexist with the existing file-based storage during transition, so that I can validate correctness before fully switching over.

#### Acceptance Criteria

1. WHILE the system is in dual-write mode, THE Load_Forecast_Pipeline SHALL write data to both the database and the existing JSON/SQLite files; IF the database write succeeds but the file write fails (or vice versa), THEN THE system SHALL log a warning with the failed target and continue operating without rolling back the successful write
2. THE system SHALL support a configuration flag (`DB_ENABLED`) that controls whether database writes are active; WHEN `DB_ENABLED` is changed, THE system SHALL apply the new value on the next request without requiring a process restart; WHEN `DB_ENABLED` is false, THE system SHALL use the existing file-based storage transparently, producing no error logs and no changes to caller-visible behavior
3. WHEN `DB_ENABLED` is true, THE system SHALL read from the database as the primary source; IF the database connection cannot be established within 5 seconds or a query fails with a connection error, THEN THE system SHALL log a warning containing the failure reason and fall back to file-based reads; IF file-based reads are also unavailable, THEN THE system SHALL return an error response indicating that no data source is reachable
4. THE DB_Adapter SHALL not require any changes to existing API response formats; existing REST endpoints SHALL return identical JSON structures regardless of the backing storage

### Requirement 8: 连接公司数据库的扩展接口

**User Story:** As a developer, I want a well-defined interface for connecting to the company's production database, so that future integration requires only configuration changes and a thin adapter implementation.

#### Acceptance Criteria

1. THE DB_Adapter SHALL define an abstract data source interface for Station_Data_Source with methods: `pull_latest(station_id: str, since_timestamp: datetime_utc) -> List[Record]` and `get_available_stations() -> List[StationInfo]`, where Record contains at minimum (station_id, timestamp, measurement_value) and StationInfo contains at minimum (station_id, station_name). WHEN `pull_latest` finds no records matching the query, THE DB_Adapter SHALL return an empty list.
2. THE DB_Adapter SHALL include a local mock implementation of Station_Data_Source that reads from CSV/Parquet files, enabling development and testing without a live database connection
3. WHEN switching to the company database, THE system SHALL require only a new Station_Data_Source implementation and a configuration change, with no modifications to the Scheduler or pipeline business logic
4. THE DB_Adapter configuration SHALL support specifying the database engine (MySQL as primary, PostgreSQL as secondary option) via a `DB_ENGINE` environment variable and connection parameters (host, port, database name, credentials reference) via additional environment variables or a single `DB_CONNECTION_URL` environment variable; the company database is MySQL (remote at 10.65.101.249, using pymysql driver)
5. IF the data source connection fails or a query exceeds 30 seconds, THEN THE DB_Adapter SHALL raise a DataSourceError indicating the failure cause, and SHALL NOT expose raw database driver exceptions to the caller

