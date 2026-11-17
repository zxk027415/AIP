<!-- @AI_GENERATED -->
# AutoResearch MySQL 迁移 — 任务清单

## Phase 0 — Schema & 迁移工具（1-2 天）

### 0.1 ORM 模型扩展与新增
- [ ] `services/db/models/load_forecast.py`：扩展 `ExperimentRun` 加字段（baseline_workflow_id / current_iteration / total_iterations / previous_status / recoverable / snapshot_state / error_message / interrupted_at / resumed_at / updated_at）
- [ ] `services/db/models/autoresearch.py`（新文件）：新增 ExperimentTrial / ExperimentDecision / AutoResearchJob / CandidateVerification / CandidatePromotionLog
- [ ] `services/db/models/deployment.py`（新文件）：DeploymentSlot / DeploymentModelVersion / SwitchEvent / SchedulerTask
- [ ] `services/db/models/registry.py`（新文件）：SearchSpaceRegistry / FeatureRecipe / ProductionWorkflowRegistry
- [ ] `alembic/env.py`：import 新模块以便 autogenerate 感知

### 0.2 Alembic 迁移脚本
- [ ] `alembic revision --autogenerate -m "add autoresearch and deployment tables"`
- [ ] 手动核对生成的 SQL（尤其是索引和 JSON 字段）
- [ ] 在 Linux/WSL 或用 python API 执行 `alembic upgrade head`（Windows 权限受阻时）
- [ ] 验证 MySQL 里表结构和索引正确

### 0.3 Repository 层
- [ ] `services/db/repositories/autoresearch.py`：新建 AutoResearchRepository（run/trial/decision/job/candidate/verification/promotion/knowledge CRUD）
- [ ] `services/db/repositories/deployment.py`：新建 DeploymentRepository（slot/model_version/switch_event/scheduler_task CRUD）
- [ ] `services/db/repositories/registry_sync.py`：新建 sync 函数（search_space / feature_recipe / production_registry）

### 0.4 一次性迁移脚本
- [ ] `scripts/migrate_autoresearch_storage_to_db.py`：骨架 + 每个数据源的迁移函数
- [ ] Dry-run 模式（`--dry-run`）：只打印会写入的记录数
- [ ] 失败重试模式：失败的记录写到 `data/migration_failures.jsonl`

### 0.5 验证
- [ ] `pytest tests/test_db_autoresearch_repository.py`：对 Repository 层写 unit test
- [ ] Dry-run 跑一次迁移脚本，检查输出行数是否符合预期

## Phase 1 — 双写模式（1-2 周）

### 1.1 AutoResearch 核心双写
- [ ] `services/autoresearch_run_store.py::AutoResearchRunStore.save()`：追加 DB upsert
- [ ] `services/autoresearch_trial_ledger.py::append_trial()`：追加 DB insert
- [ ] `services/autoresearch_trial_ledger.py::append_decision()`：追加 DB insert
- [ ] `services/knowledge_layer.py::save_claim()`：追加 DB upsert

### 1.2 Job Queue 双 backend
- [ ] `services/autoresearch_job_queue.py`：新增 `_backend_mysql.py` 分支
- [ ] 环境变量 `AUTORESEARCH_JOB_QUEUE_BACKEND` 控制（默认 `sqlite`，Phase 2 切到 `mysql`）
- [ ] `main.py` startup：调用 mysql backend 的 `mark_dead_workers()`

### 1.3 候选池 / 复验池双写
- [ ] `api/workflows_enhanced.py` 候选池 JSON 写入点：追加 DB upsert
- [ ] `api/workflows_enhanced.py` 复验池 JSON 写入点：追加 DB upsert
- [ ] Promotion 日志追加 DB insert

### 1.4 部署链路双写
- [ ] `services/deployment/store.py::DeploymentSlotStore.upsert()`：追加 DB upsert（拆分为 slot + model_version）
- [ ] `services/deployment/store.py::SwitchEventLog.append()`：追加 DB insert
- [ ] `services/deployment/scheduler_store.py::upsert_task()`：追加 DB upsert

### 1.5 B' 静态配置 sync
- [ ] `services/db/repositories/registry_sync.py`：实现 `sync_search_space_registries()` / `sync_feature_recipes()` / `sync_production_workflow_registry()`
- [ ] `main.py` startup：调用 `sync_all_from_files()`
- [ ] 新增 API：
  - `POST /api/autoresearch/registries/reload`
  - `POST /api/autoresearch/recipes/reload`
  - `POST /api/deployment/production-registry/reload`

### 1.6 观察窗口
- [ ] 至少 1 周日志无 DB 写入错误
- [ ] 抽样对比 DB 和 JSON 状态是否一致
- [ ] 出现不一致时记录并修复

## Phase 2 — DB 读优先 & 历史迁移（3-5 天）

### 2.1 历史数据迁移
- [ ] 生产环境备份 `data/autoresearch/` 目录
- [ ] 执行 `python scripts/migrate_autoresearch_storage_to_db.py`
- [ ] 检查失败明细 `data/migration_failures.jsonl`，逐条修复
- [ ] 抽样对比：SQL 查询 vs JSON 文件

### 2.2 读逻辑切换（DB 优先，JSON 兜底）
- [ ] `AutoResearchRunStore.load()` → 先 DB 后 JSON
- [ ] `AutoResearchRunStore.list()` → 先 DB 后 JSON
- [ ] `AutoResearchRunStore.scan_and_mark_interrupted()` → 走 SQL UPDATE
- [ ] `AutoResearchTrialLedger.list_trials/list_decisions()` → 先 DB 后 JSON
- [ ] `KnowledgeLayer.get_injection_candidates()` → 先 DB 后 JSON
- [ ] 候选池 / 复验池 API 读 → 先 DB 后 JSON
- [ ] `DeploymentSlotStore.load_all()` → 先 DB 后 JSON
- [ ] `SwitchEventLog.load_all()` → 先 DB 后 JSON
- [ ] `SchedulerStore.list_tasks()` → 先 DB 后 JSON

### 2.3 断点恢复走 DB
- [ ] `api/workflows_enhanced.py::resume_auto_research`：从 `experiment_run.snapshot_state` 读，从 `experiment_trial` 补 completed_iterations
- [ ] Job Queue 切换 `AUTORESEARCH_JOB_QUEUE_BACKEND=mysql`

### 2.4 静态配置读切 DB
- [ ] `autoresearch_registry_service.py::_load_registry_cached` → 先 DB 后文件
- [ ] `feature_recipe_service.py` → 先 DB 后文件
- [ ] production_workflow_registry 读点 → 先 DB 后文件

## Phase 3 — 停 JSON 写 & 归档（1 天）

### 3.1 关闭双写
- [ ] `AutoResearchRunStore.save()` 移除 JSON 写入（保留读兜底）
- [ ] `AutoResearchTrialLedger.append_*` 移除 JSON 写入
- [ ] `KnowledgeLayer.save_claim` 移除 JSON 写入
- [ ] 候选池 / 复验池 JSON 写入移除
- [ ] `DeploymentSlotStore.upsert()` 移除 JSON 写入
- [ ] `SwitchEventLog.append()` 移除 JSON 写入
- [ ] `SchedulerStore.upsert_task()` 移除 JSON 写入

### 3.2 归档旧数据
- [ ] 移动 `data/autoresearch_dev/` → `data_archive/autoresearch_dev/`
- [ ] 移动 `data/autoresearch_knowledge/` → `data_archive/autoresearch_knowledge/`
- [ ] 移动 `data/autoresearch_run_insights/` → `data_archive/autoresearch_run_insights/`
- [ ] 移动 `data/autoresearch_search_registries/` → `data_archive/autoresearch_search_registries/`
- [ ] 保留（Phase 3 不动）：`registries/`（B' 类源文件）、`recipes/`（B' 类源文件）、`runs/*/artifacts/`

### 3.3 清理兜底代码
- [ ] `autoresearch_paths.py::legacy_*()` 函数标记为 deprecated（保留兼容 1 个月后彻底删除）
- [ ] 各 store 的 `_legacy_root_dir` 兜底代码删除

### 3.4 文档更新
- [ ] `AGENTS.md` 更新：AutoResearch 数据存储改到 MySQL
- [ ] `plan.md` 更新：标记 Phase 0-3 完成时间
<!-- @AI_GENERATED: end -->
