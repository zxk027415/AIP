# 数据管线 DB 集成层接入

本次变更为工业 AI 平台引入了 MySQL 持久化层，覆盖 `load_forecast` 和 `pv_fault_diag` 两条完全隔离的数据管线。核心设计是在过渡期保留文件存储（SQLite/JSON），通过 `DualWriteProxy` 和 precision_ops 各模块内的异步后台线程双写 MySQL，同时引入 APScheduler 管理两条管线的定时任务，以及 `MigrationTool` 将历史数据从 JSON/SQLite/Parquet 一次性迁移到 MySQL。

**Watch for（confirmed）**：`DualWriteProxy.read()` 每次调用都泄漏一个 ThreadPoolExecutor；`_db_helper._get_lf_repo()` 创建独立的第二个 DBAdapter 实例（第二套连接池 + 重复执行 Alembic 迁移）；`pv_data_pull_task` 对 training_samples 全表扫描求高水位，在大数据集上会爆炸；prelaunch/version_registry 的状态变更未同步到 MySQL。

---

## 概览

`DBConfig` 用三层优先级（环境变量 → YAML → 代码默认值）加载数据库配置，支持运行时切换 `DB_ENABLED`，设计合理。`DBAdapter` 管理 pymysql 同步引擎和可选的 aiomysql 异步引擎，启动时验证连接（指数退避）并通过 subprocess 调用 Alembic 升级 schema。

`DualWriteProxy` 封装了三种路由模式（仅文件、双写、仅 DB），读路径有 5 秒超时降级。precision_ops 四个模块（`PredictionStore`、`AccuracyTracker`、`VersionRegistry`、`PrelaunchManager`）在各自的写入路径中通过 `_db_helper._get_lf_repo()` 异步后台线程双写 MySQL，文件侧先写，DB 侧 best-effort。

`SchedulerEngine` 为每条管线维护一个独立 `BackgroundScheduler`，实现重叠保护、单次重试、失败历史、catch-up 逻辑。调度任务与 precision_ops 解耦，通过工厂函数注入依赖。

ORM 模型、Repository CRUD、Alembic env.py 整体结构规范，事务管理集中在 `DBAdapter.get_sync_session()` contextmanager 中，expunge 模式统一。

<details>
<summary>Issues (8)</summary>

1. **DualWriteProxy 读路径线程池泄漏** — 每次 `read()` 调用都新建 ThreadPoolExecutor 并以 `wait=False` 关闭，超时后后台线程仍持有数据库连接运行，长期积累线程和连接。改为模块级或类级复用的固定大小线程池，或用 `concurrent.futures.wait` 配合 cancel。

2. **_db_helper 创建第二个 DBAdapter，触发第二次 Alembic 迁移** — `_get_lf_repo()` 内部 `DBAdapter(DBConfig())` 与 `main.py` 中的 `_db_adapter` 完全独立，导致两套连接池（合计 20 个连接）和启动时两次 `alembic upgrade head` 的竞争。应将 `main.py` 中已初始化的 `LoadForecastRepository` 实例注入给 precision_ops，而非在 helper 中重建。

3. **pv_data_pull_task 全表扫描求高水位** — `pv_repo.query_training_samples()` 全量拉取后在 Python 中 `max(s.time for s in existing)`，百万行时内存和 CPU 均爆炸。改为在 `PVFaultRepository` 中增加 `get_high_watermark()` 方法，内部用 `SELECT MAX(time) FROM training_samples`，与 `load_forecast_tasks._get_high_watermark()` 保持对称。

4. **tempfile.mktemp 不安全** — `pv_data_pull_task` 使用已废弃的 `tempfile.mktemp()`，存在 TOCTOU 竞争条件。改用 `tempfile.NamedTemporaryFile(delete=False)` 或 `tempfile.mkstemp()`。

5. **prelaunch 状态变更未同步到 MySQL** — `PrelaunchManager.graduate()`、`cancel()`、`mark_failed()`、`evaluate_observing()` 均无 DB 双写，只有 `enqueue()` 时写入了初始状态。MySQL 的 `prelaunch_queue` 表中状态永远停留在 `observing`。同理，`VersionRegistry.transition_status()` 也没有 DB 双写，版本状态变更不会同步。需要在这些写路径中补充双写或调用 Repository 对应的更新方法。

6. **PredictionStore.fill_actuals 无 MySQL 双写** — 回填实际值只写了 SQLite，MySQL `prediction_result.actual_value` 永远为 NULL。`accuracy_backfill_task` 直接查 MySQL（`lf_repo._adapter`）计算 MAPE，会因为 actual_value 全 NULL 而算出 0 个有效对，始终跳过，精度指标永远不写入。需要在 `fill_actuals` 中补充 `lf_repo.update_actual_value()` 的异步双写。

7. **迁移工具每行一个 Session，无法原子回滚** — `migrate_precision_ops_json` 对每一行都开一个独立的 `get_sync_session()`（独立事务），单条失败不会回滚已插入行，多次运行依赖 INSERT IGNORE 的幂等性而非事务。性能上每行一次 round-trip，即使 100 行也需 100 次。应将一个文件内的所有行合并为一个批次提交。

8. **accuracy_backfill_task 绕过 Repository 层直接访问 _adapter** — `lf_repo._adapter.get_sync_session()` 暴露了私有属性，且查询逻辑内联在任务函数中。应在 `LoadForecastRepository` 增加 `query_predictions_with_actuals(slot)` 方法，或复用 `query_predictions()` 并在调用侧过滤。

</details>

<details>
<summary>Details</summary>

### DualWriteProxy 读路径的线程泄漏

`DualWriteProxy.read()` 中的实现：

```python
executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
future = executor.submit(db_read_fn)
executor.shutdown(wait=False)

try:
    return future.result(timeout=_DB_READ_TIMEOUT)
except concurrent.futures.TimeoutError:
    ...
```

每次调用都创建一个新的 `ThreadPoolExecutor` 并立即以 `wait=False` 关闭。`wait=False` 意味着 shutdown 不等待已提交的任务完成就返回——线程仍在后台跑，仍持有数据库连接。如果在 5 秒内超时降级，后台线程最终会完成（或卡死），但这段时间内连接没有归还到连接池。高频调用场景下（如调度任务轮询状态），这会产生数十乃至数百个泄漏线程和连接。

写路径（`write()`）没有类似问题，因为它直接同步调用两个 callable。

修复方向：在类级别维护一个固定的 1-worker 线程池，或用更简单的方案——直接 `threading.Thread` + `join(timeout=5)`，无需 Executor 的启停开销。

### _db_helper 第二个 DBAdapter 实例与双重迁移

`_db_helper._get_lf_repo()` 在第一次 precision_ops 写入时（发生在后台线程）构造 `DBAdapter(DBConfig())`。此时 `main.py` 的 startup_event 中已经创建并初始化了另一个 `DBAdapter` 实例，两者完全独立：

```
main.py startup
  ├── DBAdapter(cfg)          ← 连接池 A，max_connections=10
  │     └── run_migrations()  ← alembic upgrade head (进程 1)
  │
  └── (返回，startup 完成)

[后来某次 precision_ops 写入时，后台线程]
  └── _get_lf_repo()
        └── DBAdapter(DBConfig())  ← 连接池 B，max_connections=10
              └── run_migrations() ← alembic upgrade head (进程 2，并发执行)
```

`alembic upgrade head` 在分布式场景下有并发安全问题（Alembic 自身没有分布式锁），两个 subprocess 同时执行可能导致重复应用迁移脚本。即使在单机上，两次几乎同时的 `CREATE TABLE IF NOT EXISTS` 不会失败，但竞争本身是不必要的。

更实际的问题是连接数：两套独立的连接池合计最多 20 个连接，加上 Alembic 各自用 `NullPool` 打开的临时连接，峰值可能远超 MySQL 默认的 max_connections。

正确的做法是将 `main.py` 中初始化好的 `LoadForecastRepository` 实例（已绑定到 `_db_adapter`）在 startup 时注入到 precision_ops 的双写路径中，避免 helper 自己构造第二个 adapter。

### PV 任务高水位的全表扫描

```python
existing = pv_repo.query_training_samples()
if existing:
    since_ts = max(s.time for s in existing)
```

`query_training_samples()` 无条件返回所有训练样本，然后在 Python 中对整个列表求 max。`all_labeled_combined.parquet` 就已经可能有数十万行，实际运行中数据量只会增加。这行代码每次调度都触发全表扫描 + 全量网络传输 + 内存加载，是调度任务中最明显的性能炸弹。

对比 `load_forecast_tasks._get_high_watermark()`，它做的是：

```python
session.query(func.max(StationData.timestamp_utc))...scalar()
```

`PVFaultRepository` 缺少对称的高水位查询方法，直接导致任务函数绕道全表扫描。

### 状态变更未双写到 MySQL（prelaunch、version_registry）

`PrelaunchManager` 的 DB 双写只覆盖了 `enqueue()`（写入初始状态）。当预上线项经历 `graduate()` / `cancel()` / `mark_failed()` / `evaluate_observing()` 时，状态只更新了 JSON 文件，MySQL `prelaunch_queue` 表中的记录永远停留在 `status='observing'`，`graduated_at` / `failed_at` 永远为 NULL。

`VersionRegistry.transition_status()` 同样——`register()` 时双写了初始状态，但后续 production → shadow、shadow → production 的状态转换只写了 JSON 文件。

这两个问题导致 MySQL 中的 `prelaunch_queue` 和 `version_registry` 表仅能体现"历史创建记录"，不能反映当前实际状态，无法用于任何需要从 DB 查询当前状态的逻辑（如将来的调度报告或审计）。

### fill_actuals 的 MySQL 双写缺口与精度指标链路断裂

`PredictionStore.fill_actuals()` 只回填了 SQLite，对应的 `LoadForecastRepository.update_actual_value()` 方法虽已实现但从未被调用。

这个缺口导致 `accuracy_backfill_task` 的整条链路失效：该任务从 MySQL `prediction_result` 表查询 `actual_value IS NOT NULL` 的记录，但实际值从不写入 MySQL，查询结果永远为空，MAPE 永远不更新 `AccuracyMetric`。

如果将来想要在 `DB_ENABLED=true, DUAL=false`（纯 DB 模式）下运行，精度指标系统将完全失效。

### 迁移工具的事务粒度问题

`migrate_precision_ops_json` 对每一行数据独立开一个 `get_sync_session()`（独立事务）。如果迁移中途失败，已提交的行不会回滚，下次运行依靠 INSERT IGNORE 的幂等性"跳过"已有行。这不是真正的原子迁移，是否可以接受取决于业务场景——对于一次性迁移脚本，幂等 skip 通常够用，但批量每行一次 round-trip 在网络延迟下性能会很差。

对比 `migrate_predictions_db`，它先批量过滤再批量 insert，性能和事务粒度都更合理，是更好的范式。

### MySQL CHECK 约束在 MySQL 8.0.16 以下不强制

`PredictionRecord` 中声明了 confidence 的 CHECK 约束，代码注释也说明了 MySQL < 8.0.16 不强制。Python 层的 `insert_prediction_record` 中有范围校验，这是目前唯一有效的防护，符合预期。值得注意的是，如果直接向 MySQL 写入（绕过 Repository），confidence 不会被校验。

### 调度器状态不持久化与 catch-up 行为

`_TaskMeta.last_execution_time` 只存在内存中，服务重启后全部重置为 `None`。`_maybe_catchup` 在检测到 `last_execution_time is None` 时会立刻触发一次执行——对于 `pv_data_pull_task` 来说，这会立即触发全表扫描（见上一节）。两个问题叠加，每次服务重启都会造成一次昂贵的全量扫描。

</details>

---

## 文件清单

<details>
<summary>变更文件</summary>

| 文件 | 变更内容 |
|------|---------|
| `services/db/config.py` | DBConfig 数据类，三层优先级（env→YAML→默认值）加载所有数据库和调度器配置 |
| `services/db/adapter.py` | DBAdapter，管理 pymysql 同步引擎 + 可选 aiomysql 异步引擎，指数退避重试，Alembic 迁移调用 |
| `services/db/exceptions.py` | DB 层异常层次结构（DBAdapterError、MigrationError、IngestionError 等） |
| `services/db/dual_write.py` | DualWriteProxy，三模式读写路由：仅文件 / 双写 / 仅 DB，读路径 5 秒超时降级 |
| `services/db/migration_tool.py` | MigrationTool，历史数据迁移（JSON/SQLite/Parquet → MySQL），幂等 INSERT IGNORE |
| `services/db/models/load_forecast.py` | load_forecast 库 8 张 ORM 表定义 |
| `services/db/models/pv_fault.py` | pv_fault_diag 库 4 张 ORM 表定义，含 CHECK 约束和 FK |
| `services/db/datasources/base.py` | StationDataSource ABC，StationRecord/StationInfo 数据类 |
| `services/db/datasources/local_mock.py` | 本地 CSV/Parquet mock 数据源，30 秒超时保护 |
| `services/db/repositories/load_forecast.py` | LoadForecastRepository，8 张表的 CRUD，事务由 get_sync_session 管理 |
| `services/db/repositories/pv_fault.py` | PVFaultRepository，4 张表的 CRUD，含 Parquet 批量导入（INSERT IGNORE，500 行/批） |
| `services/scheduler/engine.py` | SchedulerEngine，per-pipeline BackgroundScheduler，重叠保护 + 单次重试 + catch-up |
| `services/scheduler/tasks/load_forecast_tasks.py` | 负荷预测三个任务工厂（数据拉取、预测 stub、精度回填） |
| `services/scheduler/tasks/pv_fault_tasks.py` | PV 故障两个任务工厂（数据拉取、预测 stub），含 tempfile.mktemp 问题 |
| `api/scheduler.py` | 调度器状态/启动/停止 API，3 个端点，依赖 SchedulerEngine 注入 |
| `services/precision_ops/_db_helper.py` | precision_ops 内部 DB 双写辅助，懒加载 LoadForecastRepository（问题：创建第二个 DBAdapter） |
| `main.py` | 新增 DB/调度器 startup 初始化（非致命异常包装）和 shutdown dispose |
| `services/precision_ops/prediction_store.py` | 新增 record_prediction 后的异步 DB 双写；fill_actuals 无双写（缺口） |
| `services/precision_ops/accuracy_tracker.py` | 新增 update_metrics 后的异步 DB 双写 |
| `services/precision_ops/version_registry.py` | 新增 register 后的异步 DB 双写；transition_status 无双写（缺口） |
| `services/precision_ops/prelaunch_manager.py` | 新增 enqueue 后的异步 DB 双写；状态变更方法无双写（缺口） |
| `alembic/env.py` | 接入 DBConfig、导入两个库的 ORM 模型、设置 include_schemas + include_name 过滤器 |

