# Implementation Plan: 数据管线数据库集成

## Overview

将 AIP 平台两条独立数据管线（负荷预测、光伏故障诊断）从文件存储迁移到 MySQL，并实现定时任务闭环。技术栈：Python + FastAPI + SQLAlchemy + APScheduler + Alembic。实现路径按自底向上组织：先基础设施（DB 适配、ORM 模型、迁移），再业务层（Repository、数据源、调度器），最后集成层（双写代理、API 端点、任务接入主应用）。

## Tasks

- [x] 1. 搭建数据库基础设施
  - [x] 1.1 创建目录结构和配置模块
    - 创建 `services/db/` 目录及 `__init__.py`
    - 创建 `services/db/config.py`：实现 `DBConfig` 数据类，从环境变量 / `configs/db.yaml` 加载配置，环境变量优先
    - 字段包括 `engine`、`connection_url`、`max_connections`（1–100）、`idle_timeout`（10–3600）、`connection_lifetime`（60–86400）、`pool_wait_timeout`（1–120）等
    - 配置项超出范围时抛出 `ValidationError`
    - _Requirements: 1.3, 1.5_

  - [x] 1.2 实现 DBAdapter 核心类
    - 创建 `services/db/adapter.py`
    - 初始化 SQLAlchemy `create_engine`（同步，`pymysql` 驱动）和 `create_async_engine`（异步，`aiomysql` 驱动）
    - 连接池参数映射：`pool_size=max_connections`、`pool_recycle=connection_lifetime`、`pool_timeout=pool_wait_timeout`
    - 实现 `health_check()`：执行 `SELECT 1`
    - 实现连接失败重试：最多 3 次，指数退避 1s → 2s → 4s，max 8s
    - 实现 `get_sync_session()` 和 `get_async_session()` 工厂方法
    - 实现 `dispose()` 关闭引擎和连接池
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.9_

  - [x] 1.3 集成 Alembic 迁移框架
    - 创建 `backend-service/alembic/` 目录、`alembic.ini`、`env.py`
    - `env.py` 中读取 `DBConfig` 连接串
    - 在 `DBAdapter.__init__()` 中调用 `alembic upgrade head`
    - 迁移失败时回滚当前 revision、记录 `MigrationError`（含 revision ID）、阻止启动
    - _Requirements: 1.7, 1.8_

  - [x] 1.4 定义异常类型
    - 创建 `services/db/exceptions.py`
    - 实现 `DBAdapterError`、`ConnectionExhaustedError`、`MigrationError`、`DataSourceError`、`DataSourceTimeoutError`、`IngestionError`
    - _Requirements: 1.4, 1.9, 8.5_

  - [x]* 1.5 属性测试：连接池配置验证
    - **Property 1: 连接池配置验证**
    - 使用 hypothesis 生成合法/非法配置组合，验证 DBConfig 初始化行为
    - **Validates: Requirements 1.3**

  - [x]* 1.6 属性测试：环境变量优先级
    - **Property 3: 环境变量优先级**
    - 同时设置环境变量和配置文件值，验证 DBConfig 始终取环境变量
    - **Validates: Requirements 1.5**

- [x] 2. Checkpoint — 确认基础设施可用
  - 确保 DBAdapter 能连接本地 MySQL、健康检查通过、Alembic 空迁移不报错。如有疑问，询问用户。

- [x] 3. 创建 ORM 模型和 Schema 迁移
  - [x] 3.1 定义负荷预测 ORM 模型
    - 创建 `services/db/models/load_forecast.py`
    - 定义 `StationData`、`ExperimentRun`、`CandidatePool`、`KnowledgeClaim`、`PredictionResult`、`AccuracyMetric`、`VersionRegistry`、`PrelaunchQueue` 模型
    - 所有表包含 `slot` 字段作为逻辑分区键
    - 定义索引：`(slot, station_id, timestamp_utc)`、`(slot, workflow_id, forecast_timestamp)` 等
    - _Requirements: 2.1, 2.2, 2.4, 2.5_

  - [x] 3.2 定义光伏故障诊断 ORM 模型
    - 创建 `services/db/models/pv_fault.py`
    - 定义 `TrainingSample`、`ModelVersion`、`PredictionRecord`、`DiagnosisResult` 模型
    - 复合唯一键 `(time, site_id, device_id, branch_id)` on `TrainingSample`
    - `confidence` CHECK 约束 `[0.0, 1.0]`
    - 组合索引 `(site_id, time, label)`
    - _Requirements: 3.1, 3.2, 3.4, 3.5_

  - [x] 3.3 编写 Alembic 迁移脚本
    - `001_create_load_forecast_schema.py`：创建 `load_forecast` DATABASE 及全部表
    - `002_create_pv_fault_diag_schema.py`：创建 `pv_fault_diag` DATABASE 及全部表
    - 使用 `alembic revision --autogenerate` 生成初始迁移，手动校验
    - _Requirements: 2.1, 3.1_

  - [ ]* 3.4 属性测试：管线 Schema 隔离
    - **Property 5: 管线 Schema 隔离**
    - 验证两个 database 之间无 FK 引用，跨库查询返回空结果
    - **Validates: Requirements 2.1, 3.1**

  - [ ]* 3.5 属性测试：槽位数据分区隔离
    - **Property 6: 槽位数据分区隔离**
    - 向不同 slot 插入数据，按 slot 查询验证只返回当前 slot 的行
    - **Validates: Requirements 2.5**

- [x] 4. 实现 Repository 层
  - [x] 4.1 实现 LoadForecastRepository
    - 创建 `services/db/repositories/load_forecast.py`
    - 实现 `insert_station_data()`、`query_station_data(slot, station_id, time_range)`
    - 实现 `save_experiment_run()`、`get_experiment_run()`
    - 实现 `upsert_candidate()`、`query_candidates(slot)`
    - 实现 `save_prediction_result()`、`query_predictions(slot, time_range)`
    - 实现 `upsert_accuracy_metrics()`、`get_accuracy_metrics(slot, workflow_id)`
    - 实现 `save_version_registry()`、`get_active_version(slot)`
    - 实现 `save_prelaunch()`、`get_prelaunch_queue(slot)`
    - 所有写入操作使用事务，失败整体 rollback
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 4.2 实现 PVFaultRepository
    - 创建 `services/db/repositories/pv_fault.py`
    - 实现 `ingest_parquet(file_path)`：读取 Parquet，按复合键去重 `INSERT IGNORE`，文件缺列时整体拒绝
    - 实现 `insert_prediction_record()`：含 `confidence` 范围校验
    - 实现 `insert_diagnosis_result()`
    - 实现 `query_training_samples(site_id, time_start, time_end, labels)` 带索引查询
    - 实现 `save_model_version()`、`get_model_version(id)`
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 4.3 属性测试：数据记录存取往返保持
    - **Property 7: 数据记录存取往返保持**
    - 使用 hypothesis 生成随机 station_data / prediction_result / training_sample，存入后读出验证字段一致
    - **Validates: Requirements 2.4, 2.6, 3.4**

  - [ ]* 4.4 属性测试：写入原子性
    - **Property 8: 写入原子性**
    - 模拟事务中途异常，验证数据库无部分提交状态
    - **Validates: Requirements 2.7, 3.6**

  - [ ]* 4.5 属性测试：Parquet 导入幂等性
    - **Property 9: Parquet 导入幂等性**
    - 同一份 Parquet 多次导入，验证行数不变
    - **Validates: Requirements 3.3**

  - [ ]* 4.6 属性测试：训练样本组合查询正确性
    - **Property 10: 训练样本组合查询正确性**
    - 验证 site_id + time range + label 组合过滤结果精确匹配预期子集
    - **Validates: Requirements 3.5**

- [x] 5. Checkpoint — Repository 层验证
  - 确保所有 Repository CRUD 在本地 MySQL 正常工作、属性测试通过。如有疑问，询问用户。

- [x] 6. 实现数据源接口
  - [x] 6.1 实现 StationDataSource 抽象接口
    - 创建 `services/db/datasources/base.py`
    - 定义 `StationRecord`、`StationInfo` 数据类
    - 定义 `StationDataSource` ABC（`pull_latest`、`get_available_stations`）
    - 定义 `DataSourceError` / `DataSourceTimeoutError`
    - _Requirements: 8.1, 8.5_

  - [x] 6.2 实现 LocalMockDataSource
    - 创建 `services/db/datasources/local_mock.py`
    - 读取 CSV / Parquet 文件模拟站点数据
    - `pull_latest` 按 `since_timestamp` 过滤行，30s 超时
    - 返回空列表表示无新记录
    - _Requirements: 8.2_

  - [ ]* 6.3 属性测试：DataSourceError 封装
    - **Property 22: DataSourceError 封装**
    - Mock 底层驱动抛出各类异常，验证 StationDataSource 只暴露 DataSourceError
    - **Validates: Requirements 8.5**

- [x] 7. 实现调度器引擎
  - [x] 7.1 实现 SchedulerEngine 核心
    - 创建 `services/scheduler/engine.py`
    - 封装 APScheduler，按 cron 表达式注册任务（最小粒度 1 分钟）
    - 实现任务重叠保护：同类型任务同时只允许一个实例（使用 APScheduler `max_instances=1` + 自定义 skip log）
    - 实现失败重试：1 次，可配置延迟（默认 60s，范围 10–600）
    - 维护最近 20 条 `FailureRecord`（task_id、trigger_time、error_message、is_retry）
    - 实现 catch-up：启动时检测漏跑，每任务最多补跑 1 次
    - 实现 `start_pipeline()` / `stop_pipeline()`：两条管线完全独立
    - _Requirements: 4.1, 4.6, 4.8, 4.9, 5.1, 5.4_

  - [x] 7.2 实现调度任务模块（负荷预测）
    - 创建 `services/scheduler/tasks/load_forecast_tasks.py`
    - `data_pull_task`：调用 StationDataSource.pull_latest，按高水位拉取，写入 LoadForecastRepository，120s 超时
    - `prediction_task`：加载生产模型，生成 24h 预测，写入 prediction_results；prelaunch 观察中的模型同步执行 shadow prediction
    - `accuracy_backfill_task`：对有实际值的预测做 MAPE 计算，更新 rolling 30 天指标
    - _Requirements: 4.2, 4.3, 4.4, 4.5_

  - [x] 7.3 实现调度任务模块（光伏故障诊断）
    - 创建 `services/scheduler/tasks/pv_fault_tasks.py`
    - `pv_data_pull_task`：按高水位拉取 PV 传感器数据，每次最多处理 10,000 条
    - `pv_prediction_task`：加载故障诊断模型，对无诊断结果的记录执行预测，写入 diagnosis_results
    - 模型文件缺失时记录失败、跳过、emit 通知事件
    - _Requirements: 5.2, 5.3, 5.5, 5.6_

  - [ ]* 7.4 属性测试：高水位拉取语义
    - **Property 11: 高水位拉取语义**
    - 验证每次 pull 只请求 > last_pull_timestamp 的记录，无重复无遗漏
    - **Validates: Requirements 4.2**

  - [ ]* 7.5 属性测试：MAPE 计算正确性
    - **Property 12: MAPE 计算正确性**
    - 使用 hypothesis 生成 (predicted, actual) 对，验证 MAPE = mean(|p-a|/|a|) × 100
    - **Validates: Requirements 4.4**

  - [ ]* 7.6 属性测试：调度任务重叠保护
    - **Property 13: 调度任务重叠保护**
    - 模拟慢任务 + 快速触发，验证同类型永远只有 1 个并发实例
    - **Validates: Requirements 4.8**

  - [ ]* 7.7 属性测试：停机后最多一次 catch-up
    - **Property 14: 停机后最多一次 catch-up**
    - 模拟 N 次漏跑后启动，验证每个 task 只补跑 1 次
    - **Validates: Requirements 4.9**

  - [ ]* 7.8 属性测试：管线调度独立性
    - **Property 15: 管线调度独立性**
    - stop 一条管线不影响另一条管线的 running 状态和失败计数
    - **Validates: Requirements 5.1, 5.4**

  - [ ]* 7.9 属性测试：PV 拉取批量上限
    - **Property 16: PV 拉取批量上限**
    - 数据源返回 > 10000 条时，验证本次只处理 10000 条
    - **Validates: Requirements 5.2**

- [x] 8. Checkpoint — 调度器与任务验证
  - 确保 SchedulerEngine 注册任务、重叠保护、失败重试、独立启停均正常工作。如有疑问，询问用户。

- [x] 9. 实现双写代理与兼容层
  - [x] 9.1 实现 DualWriteProxy
    - 创建 `services/db/dual_write.py`
    - 读取 `DB_ENABLED` 和 `DB_DUAL_WRITE` 配置（支持运行时变更，无需重启）
    - 写入逻辑：dual-write 时先写 DB 再写文件，一侧失败只 log warning 不回滚另一侧
    - 读取逻辑：DB_ENABLED=true 时优先读 DB，5s 连接超时则降级到文件
    - DB_ENABLED=false 时透明使用文件存储，无错误日志
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 9.2 适配 precision_ops 模块接入 DualWriteProxy
    - 修改 `services/precision_ops/prediction_store.py`：通过 DualWriteProxy 写入/读取
    - 修改 `services/precision_ops/accuracy_tracker.py`：同上
    - 修改 `services/precision_ops/version_registry.py`：同上
    - 修改 `services/precision_ops/prelaunch_manager.py`：同上
    - 确保现有 API 响应 JSON 结构不变
    - _Requirements: 7.1, 7.4_

  - [ ]* 9.3 属性测试：双写一致性
    - **Property 19: 双写一致性**
    - dual-write 模式写入后验证 DB 和文件均有数据；模拟一侧失败验证另一侧成功
    - **Validates: Requirements 7.1**

  - [ ]* 9.4 属性测试：读取降级回退
    - **Property 20: 读取降级回退**
    - 模拟 DB 不可达，验证自动回退到文件读取且不抛异常
    - **Validates: Requirements 7.3**

  - [ ]* 9.5 属性测试：API 响应格式不变性
    - **Property 21: API 响应格式不变性**
    - 对比 DB 模式和文件模式下同一 API 端点返回的 JSON 结构是否一致
    - **Validates: Requirements 7.4**

- [x] 10. 实现数据迁移工具
  - [x] 10.1 实现 MigrationTool 主体
    - 创建 `services/db/migration_tool.py`
    - 实现 `migrate_precision_ops_json()`：读取 precision_ops 各 slot 下的 JSON 文件，按自然键去重写入 `load_forecast` 表
    - 实现 `migrate_predictions_db()`：读取 `predictions.db` SQLite，逐表迁移到 `load_forecast.prediction_results`，验证迁移后行数一致
    - 实现 `migrate_parquet()`：读取 `all_labeled_combined.parquet` 写入 `pv_fault_diag.training_samples`
    - 幂等设计：使用自然键检测重复，多次运行结果一致
    - 源文件损坏时跳过并记录错误，继续处理其余文件
    - 目标 schema 不存在时报错退出
    - 完成后输出摘要：总迁移行数、跳过行数、处理文件数、耗时
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 10.2 属性测试：迁移幂等性
    - **Property 17: 迁移幂等性**
    - 同一数据源连续迁移 N 次，验证目标表行数和数据不变
    - **Validates: Requirements 6.4**

  - [ ]* 10.3 属性测试：迁移完整性
    - **Property 18: 迁移完整性**
    - 验证源 SQLite M 行迁移后目标表恰好 M 行，列值完整保持
    - **Validates: Requirements 6.2, 6.3**

- [x] 11. 实现 API 端点和接入主应用
  - [x] 11.1 实现 Scheduler Status API
    - 创建 `api/scheduler.py`（或在已有路由文件中新增）
    - `GET /api/scheduler/status`：返回各管线状态、各任务最后执行时间、下次计划、最近 20 条失败
    - `POST /api/scheduler/{pipeline}/start`：启动指定管线调度
    - `POST /api/scheduler/{pipeline}/stop`：停止指定管线调度
    - _Requirements: 4.7_

  - [x] 11.2 将 DBAdapter 和 SchedulerEngine 接入 FastAPI 生命周期
    - 在 `main.py` 中注册 startup/shutdown 事件
    - startup：初始化 DBAdapter（含健康检查 + 迁移）→ 初始化 SchedulerEngine → 注册所有任务
    - shutdown：停止 SchedulerEngine → 调用 DBAdapter.dispose()
    - 注册 `api/scheduler.py` 路由
    - _Requirements: 1.7, 4.1_

  - [ ]* 11.3 单元测试：API 端点
    - 使用 pytest + httpx AsyncClient 测试 scheduler status / start / stop 端点
    - _Requirements: 4.7_

- [ ] 12. 属性测试补充（连接重试）
  - [ ]* 12.1 属性测试：连接重试指数退避
    - **Property 2: 连接重试指数退避**
    - Mock 连接函数，验证 N 次失败后重试延迟分别为 1s、2s、4s；第 4 次失败抛出异常
    - **Validates: Requirements 1.4**

- [x] 13. Final Checkpoint — 全链路验证
  - 确保所有测试通过：属性测试（hypothesis）、单元测试（pytest）、集成测试（连接本地 MySQL）。如有疑问，询问用户。

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 每个任务引用了具体的 requirements 子条款以确保可追溯
- Checkpoints 确保增量验证，避免到最后才发现问题
- 属性测试使用 `hypothesis` 库，每个属性至少 100 次迭代（`@settings(max_examples=100)`）
- 集成测试依赖本地 MySQL 9.6.0（`root@localhost` 无密码），无需额外 Docker
- 双写代理是过渡期设计，验证 DB 正确性后可关闭文件写入
- `pymysql` 已是项目依赖；`aiomysql`、`sqlalchemy[asyncio]`、`apscheduler`、`alembic` 需新增安装
- 所有文件路径相对于 `backend-service/`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.4"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.5", "1.6", "3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "6.1"] },
    { "id": 4, "tasks": ["3.4", "3.5", "4.1", "4.2", "6.2"] },
    { "id": 5, "tasks": ["4.3", "4.4", "4.5", "4.6", "6.3"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["7.2", "7.3"] },
    { "id": 8, "tasks": ["7.4", "7.5", "7.6", "7.7", "7.8", "7.9"] },
    { "id": 9, "tasks": ["9.1", "10.1"] },
    { "id": 10, "tasks": ["9.2", "10.2", "10.3"] },
    { "id": 11, "tasks": ["9.3", "9.4", "9.5", "11.1"] },
    { "id": 12, "tasks": ["11.2", "11.3", "12.1"] }
  ]
}
```
