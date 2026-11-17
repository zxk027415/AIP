<!-- @AI_GENERATED -->
# AutoResearch 数据迁移到 MySQL 的整体规划

**版本**：v1.0
**创建时间**：2026-07-09
**关联 spec**：`algorithm-deployment-refactor/`（部署重构）

## 一、背景与目标

### 背景
AutoResearch 主循环及部署链路的数据当前**大部分存于本地 JSON / SQLite 文件**，MySQL 里 `ExperimentRun` / `CandidatePool` / `KnowledgeClaim` 等表虽已建 schema 但**没有任何业务代码写入**（见 `services/db/repositories/load_forecast.py::save_experiment_run` 无调用者）。

带来的问题：
1. **不能跨机器**：job 队列走 `data/autoresearch/jobs.sqlite`，worker 只能跑在同一台机器上
2. **不能真正断点恢复**：状态、trial 明细、决策事件分散在 `snapshot.json` / `trials.jsonl` / `decisions.jsonl`，没有事务
3. **不能全链路 trace**：候选池 → 复验池 → prelaunch → shadow → production 链路无法用 SQL 一次 join 查出
4. **备份/审计困难**：JSON 文件散在各处，`data/autoresearch/*`、`data/deployment/*`、`data/precision_ops/*` 三个目录都是运行时状态

### 目标
1. **AutoResearch 全链路数据入 MySQL**：run 状态、trial 明细、决策事件、候选池、复验池、知识层、部署槽位、预上线队列、切换事件、定时任务
2. **支持跨机器打通**：worker 可跑在任意机器上通过 MySQL 领任务、更新心跳
3. **真正的断点恢复**：从 `experiment_run.snapshot_state` 恢复整个 run，从 `experiment_trial` 补 completed_iterations
4. **保留 Git-tracked 静态配置**：搜索空间 registry、feature_recipes、production_workflow_registry 三份文件保持文件为源，DB 做运行时镜像
5. **零停机迁移**：分阶段推进（双写 → DB 读优先 → 停 JSON 写）

## 二、数据分类

### A. **DB 为源 + JSON 兜底**（运行时状态，高频写）

| 数据 | 当前存储 | 目标表 |
|---|---|---|
| Run 状态（含 snapshot_state） | `runs/{run_id}/snapshot.json` | `experiment_run`（扩展字段） |
| Trial 明细 | `runs/{run_id}/trials.jsonl` | `experiment_trial`（新建） |
| 决策事件 | `runs/{run_id}/decisions.jsonl` | `experiment_decision`（新建） |
| Job 队列 | `autoresearch/jobs.sqlite` | `autoresearch_job`（新建） |
| Run insight | `insights/{run_id}.json` | `experiment_run.run_insight`（复用 JSON 字段） |
| Insight 索引 | `insights/_index.json` | 由 `experiment_run` 表查询构造 |
| 候选池 | `candidate_pool/baseline_comparison_candidate_pool.json` | `candidate_pool`（复用现有表） |
| 复验队列 | `candidate_pool/candidate_verification_queue.json` | `candidate_verification`（新建） |
| Promotion 日志 | `candidate_pool/baseline_comparison_promotions_log.json` | `candidate_promotion_log`（新建） |
| 知识层 | `knowledge/{layer}/*.json` | `knowledge_claim`（复用现有表） |
| 部署槽位 | `data/deployment/slots.json` | `deployment_slot` + `deployment_model_version`（新建） |
| 切换事件 | `data/deployment/switch_log.json` | `switch_event`（新建） |
| 预上线队列 | `slots.json` 的 `prelaunch_models` 字段 | `prelaunch_queue`（复用现有表） |
| Cron 任务 | `data/scheduler/tasks.json` | `scheduler_task`（新建） |

### B'. **文件为源 + DB 镜像**（低频改的静态配置，跨机器需要一致读）

| 数据 | 当前存储 | 目标表 |
|---|---|---|
| 搜索空间注册表 | `registries/{v1,v2,v3}.json` | `search_space_registry`（新建） |
| 特征配方 | `recipes/feature_recipes.json` | `feature_recipe`（新建） |
| 生产工作流注册表 | `production/production_workflow_registry.json` | `production_workflow_registry`（新建） |

**同步机制**：文件保存 → 服务启动或 `POST /api/autoresearch/registries/reload` 触发 → 计算 SHA-256 → 变了就 upsert 到 DB。所有代码 **读 DB**，DB miss 时兜底读文件。

### C. **保留本地**（大对象/中间产物，不适合 DB）

- `runs/{run_id}/artifacts/`：模型 pkl、日志、图 → 走本地磁盘，DB 只存路径引用
- `runs/{run_id}/optuna_studies.db`：optuna 内部有自己的存储抽象，改造成本高
- `data/models/`：已训练模型文件
- `data/precision_ops/predictions.db`（SQLite）：过渡期保留，最终目标是走 MySQL `prediction_result`

### D. **归档删除**（历史遗留）

迁移完成后可归档 `data_archive/`：
- `data/autoresearch_dev/` — Windows 上从未写入
- `data/autoresearch_knowledge/` — legacy 只读
- `data/autoresearch_run_insights/` — legacy 只读
- `data/autoresearch_search_registries/` — 迁移到 registries 后
- `data/autoresearch/memory/cases.json` — 若确认已废弃
- `data/autoresearch/profiles/workflow_slot_profiles.json` — 若确认已废弃

## 三、关键决策点（用户已确认）

| # | 决策 | 结论 |
|---|---|---|
| A | `jobs.sqlite` 是否搬 MySQL | ✅ 搬（跨机器打通关键） |
| B | 静态配置是否入库 | ✅ 双写（文件为源 + DB 镜像） |
| C | Snapshot 内嵌 vs 拆表 | ✅ 内嵌 `experiment_run.snapshot_state` JSON |
| D | Trial 拆表 vs 内嵌 | ✅ 拆表 `experiment_trial`（便于聚合查询） |
| E | 双写窗口 | ✅ 1-2 周过渡期 |

## 四、分阶段推进

### Phase 0 — Schema & 迁移工具（1-2 天）

**产出**：
- Alembic 迁移脚本：扩展 `experiment_run` + 新建 12 张表
- `services/db/repositories/autoresearch.py`：AutoResearch 相关 CRUD
- `services/db/repositories/deployment.py`：部署链路 CRUD
- `services/db/repositories/registry_sync.py`：静态配置 sync 工具
- `scripts/migrate_autoresearch_storage_to_db.py`：一次性历史数据迁移工具
- 执行 `alembic upgrade head`（Windows 权限受阻的话在 Linux/WSL 或用 python API 直接跑）

### Phase 1 — 双写模式（1-2 周）

**改动点**（都是"追加 DB 写入，JSON 写入不变"）：
- `AutoResearchRunStore.save()` → 同时 upsert `experiment_run`
- `AutoResearchTrialLedger.append_trial()` → 同时 insert `experiment_trial`
- `AutoResearchTrialLedger.append_decision()` → 同时 insert `experiment_decision`
- `autoresearch_job_queue` 所有函数 → 加 MySQL 分支（环境变量 `AUTORESEARCH_JOB_QUEUE_BACKEND=mysql\|sqlite` 切换）
- `KnowledgeLayer.save_claim()` → 同时 upsert `knowledge_claim`
- 候选池 / 复验池 JSON 写入点 → 同时 upsert
- `DeploymentSlotStore.upsert()` → 同时 upsert `deployment_slot` + `deployment_model_version`
- `SwitchEventLog.append()` → 同时 insert `switch_event`
- `SchedulerStore.upsert_task()` → 同时 upsert `scheduler_task`
- 静态配置 sync：main.py 启动钩子 → 扫描文件 → 变了就 upsert

**原则**：DB 写失败降级 warning，不阻塞主流程；观察 1 周日志无错误后进入 Phase 2

### Phase 2 — DB 读优先 + 历史迁移（3-5 天）

**产出**：
- 跑 `migrate_autoresearch_storage_to_db.py`，把当前 40 个 run + 22 个 insight + patterns/anti_patterns claim + slots.json + switch_log.json 一次性搬进 MySQL
- 所有 `load()` / `get()` 方法改成 **DB 优先，miss 兜底 JSON**
- `resume_auto_research` 从 `experiment_run.snapshot_state` 读，从 `experiment_trial` 补 completed_iterations
- `mark_dead_workers()` 走 SQL：`UPDATE autoresearch_job SET status='interrupted' WHERE status='running' AND heartbeat_at < NOW() - INTERVAL 2 MINUTE`
- 前端不改（API 契约不变）

### Phase 3 — 停 JSON 写 & 归档（1 天）

- 关闭 JSON 双写（保留只读兜底 1 个月）
- 旧目录移到 `data_archive/`
- 移除 legacy 目录的读取兜底代码（`autoresearch_paths.py` 里的 `legacy_*` 函数保留但停用）

## 五、非目标（Out of Scope）

- **不改造 `optuna_studies.db`**：optuna 有自己的 storage 抽象，成本高收益低
- **不改造 `artifacts/`**：模型文件等大对象继续走本地磁盘
- **不改前端**：Phase 1/2 内 API 契约保持不变
- **不改搜索空间的加载语义**：v1/v2/v3 registry 文件为准，只是加了 DB 镜像
- **不做实时同步**：静态配置文件改动后需要手动或启动时触发 sync（不做 inotify/文件监听）

## 六、风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| Alembic 在 Windows 上 subprocess 权限拒绝 | 无法自动跑迁移 | 用 `python -c "from alembic.config import ...; command.upgrade(...)"` 直接调 API，或在 Linux/WSL 跑 |
| 大 JSON blob（snapshot_state）超过 max_allowed_packet | 写入失败 | 快照通常 30-100KB，MySQL 默认 4MB 足够；实测超限再拆表 |
| 双写窗口内 DB 与 JSON 状态不一致 | 断点恢复读到旧数据 | Phase 1 内断点恢复仍从 JSON 读，DB 只写不读；Phase 2 之后才切 DB 读 |
| 40 个历史 run 迁移失败 | 无法查旧数据 | 迁移脚本记录失败明细，失败的 run 保留 JSON 只读兜底 |
| 静态配置文件被手动编辑但没 sync | DB 里是旧内容 | 启动钩子必扫；API `/registries/reload` 手动触发；每次读 DB 之前对比 content_hash |
| MySQL 连接不稳定 | 主流程被阻塞 | 所有 DB 写入 try/except 降级 warning；核心状态双写期间 JSON 仍是权威 |

## 七、关键文件索引

| 文件 | 职责 |
|---|---|
| `plan.md` | 本文件，全景规划 |
| `design.md` | Schema 定义、双写方向图、断点恢复流程、跨机器 job queue 时序图 |
| `tasks.md` | Phase 0/1/2/3 每一步的可执行任务清单 |
| `backend-service/services/db/models/load_forecast.py` | 已有 ORM 模型（含 ExperimentRun 等，本次会扩展） |
| `backend-service/services/db/repositories/load_forecast.py` | 已有 CRUD（本次会新增 autoresearch.py / deployment.py） |
| `backend-service/services/autoresearch_paths.py` | 路径真源（保留，legacy 兜底代码 Phase 3 停用） |
| `backend-service/services/autoresearch_run_store.py` | Run 快照读写（Phase 1 改造为双写） |
| `backend-service/services/autoresearch_job_queue.py` | Job 队列（Phase 1 加 MySQL backend） |
| `backend-service/services/knowledge_layer.py` | 知识层（Phase 1 改造为双写） |
| `backend-service/services/deployment/store.py` | 部署槽位（Phase 1 改造为双写） |
| `backend-service/services/deployment/scheduler_store.py` | Cron 任务（Phase 1 改造为双写） |
<!-- @AI_GENERATED: end -->
