<!-- @AI_GENERATED -->
# AutoResearch MySQL 迁移 — Schema 与技术设计

## 一、Schema 设计

### 1. 扩展现有表 `experiment_run`

已有字段：`id, slot, status, config, runtime_patch, run_insight, terminal_status, started_at, finished_at`

**新增字段**：
```sql
ALTER TABLE experiment_run ADD COLUMN baseline_workflow_id VARCHAR(128);
ALTER TABLE experiment_run ADD COLUMN current_iteration    INT;
ALTER TABLE experiment_run ADD COLUMN total_iterations     INT;
ALTER TABLE experiment_run ADD COLUMN previous_status      VARCHAR(32);
ALTER TABLE experiment_run ADD COLUMN recoverable          BOOLEAN DEFAULT TRUE;
ALTER TABLE experiment_run ADD COLUMN snapshot_state       JSON;          -- 整个 state 压进来
ALTER TABLE experiment_run ADD COLUMN error_message        TEXT;
ALTER TABLE experiment_run ADD COLUMN interrupted_at       DATETIME;
ALTER TABLE experiment_run ADD COLUMN resumed_at           DATETIME;
ALTER TABLE experiment_run ADD COLUMN updated_at           DATETIME;
CREATE INDEX ix_experiment_run_slot_status ON experiment_run(slot, status);
CREATE INDEX ix_experiment_run_updated_at  ON experiment_run(updated_at);
```

### 2. 新建表 `experiment_trial`（每轮明细）

```sql
CREATE TABLE experiment_trial (
    id             BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    run_id         VARCHAR(64) NOT NULL,
    iteration_no   INT NOT NULL,
    status         VARCHAR(32) NOT NULL,       -- pending/running/success/failed/skipped
    override_json  JSON,                        -- 该 trial 应用的 override
    evidence_json  JSON,                        -- windows_total, mape_improvement 等
    mape_improvement  FLOAT,
    baseline_mape     FLOAT,
    challenger_mape   FLOAT,
    started_at        DATETIME,
    finished_at       DATETIME,
    created_at        DATETIME NOT NULL,
    KEY ix_trial_run_iter (run_id, iteration_no),
    KEY ix_trial_run_status (run_id, status),
    UNIQUE KEY uq_trial_run_iter (run_id, iteration_no)
);
```

### 3. 新建表 `experiment_decision`（事件流）

```sql
CREATE TABLE experiment_decision (
    id              BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    run_id          VARCHAR(64) NOT NULL,
    seq             INT NOT NULL,               -- run 内递增序号
    decision_type   VARCHAR(64) NOT NULL,       -- run_started/cancel_requested/proposal_applied/...
    actor           VARCHAR(64),                -- user/system
    payload_json    JSON,
    created_at      DATETIME NOT NULL,
    KEY ix_decision_run_seq (run_id, seq),
    KEY ix_decision_run_type (run_id, decision_type)
);
```

### 4. 新建表 `autoresearch_job`（替代 jobs.sqlite）

```sql
CREATE TABLE autoresearch_job (
    run_id            VARCHAR(64) NOT NULL PRIMARY KEY,
    status            VARCHAR(32) NOT NULL DEFAULT 'pending',  -- pending/running/success/failed/cancelled/interrupted
    pid               INT,
    host              VARCHAR(128),               -- 支持跨机器：worker 领任务时写入自己的 hostname
    payload_json      JSON,
    created_at        DATETIME NOT NULL,
    started_at        DATETIME,
    finished_at       DATETIME,
    heartbeat_at      DATETIME,
    cancel_requested  BOOLEAN NOT NULL DEFAULT FALSE,
    KEY ix_job_status_hb (status, heartbeat_at),
    KEY ix_job_created (created_at)
);
```

**并发抢占**：worker 领 job 走 `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1`（MySQL 8.0+），支持多 worker 并行。

### 5. 新建表 `candidate_verification`（复验队列）

```sql
CREATE TABLE candidate_verification (
    id                  VARCHAR(64) NOT NULL PRIMARY KEY,
    candidate_id        VARCHAR(64) NOT NULL,
    slot                VARCHAR(64) NOT NULL,
    source_run_id       VARCHAR(64),
    source_iteration    INT,
    status              VARCHAR(32) NOT NULL,      -- queued/running/passed/failed/cancelled
    config_json         JSON,                       -- 复验参数（windows, aggregation, ...）
    evidence_json       JSON,                       -- 复验产出的 evidence
    created_at          DATETIME NOT NULL,
    started_at          DATETIME,
    finished_at         DATETIME,
    KEY ix_ver_slot_status (slot, status),
    KEY ix_ver_candidate (candidate_id)
);
```

### 6. 新建表 `candidate_promotion_log`

```sql
CREATE TABLE candidate_promotion_log (
    id              BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    slot            VARCHAR(64) NOT NULL,
    candidate_id    VARCHAR(64) NOT NULL,
    action          VARCHAR(32) NOT NULL,       -- promoted/rejected/force_promoted
    actor           VARCHAR(64),
    reason          TEXT,
    payload_json    JSON,
    created_at      DATETIME NOT NULL,
    KEY ix_promo_slot_created (slot, created_at)
);
```

### 7. 新建表 `deployment_slot`（拆分 slots.json）

```sql
CREATE TABLE deployment_slot (
    slot                    VARCHAR(64) NOT NULL PRIMARY KEY,
    production_workflow_id  VARCHAR(128),
    cooldown_days           INT NOT NULL DEFAULT 3,
    max_shadow_slots        INT NOT NULL DEFAULT 3,
    max_prelaunch_slots     INT NOT NULL DEFAULT 3,
    training_window_days    INT,
    switch_observation_days INT,
    updated_at              DATETIME NOT NULL
);
```

### 8. 新建表 `deployment_model_version`

```sql
CREATE TABLE deployment_model_version (
    id                        BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    slot                      VARCHAR(64) NOT NULL,
    workflow_id               VARCHAR(128) NOT NULL,
    version_tag               VARCHAR(128),
    status                    VARCHAR(32) NOT NULL,   -- production/shadow/prelaunch/retired
    accuracy_score            FLOAT,
    consecutive_better_days   INT NOT NULL DEFAULT 0,
    source_run_id             VARCHAR(64),
    source_candidate_id       VARCHAR(64),
    prelaunch_meta_json       JSON,                    -- 内嵌 PrelaunchMeta
    created_at                DATETIME NOT NULL,
    updated_at                DATETIME NOT NULL,
    UNIQUE KEY uq_dmv_slot_wf (slot, workflow_id),
    KEY ix_dmv_slot_status (slot, status)
);
```

### 9. 新建表 `switch_event`

```sql
CREATE TABLE switch_event (
    event_id            VARCHAR(64) NOT NULL PRIMARY KEY,
    slot                VARCHAR(64) NOT NULL,
    trigger_type        VARCHAR(32) NOT NULL,       -- auto/manual/rollback
    from_workflow_id    VARCHAR(128),
    to_workflow_id      VARCHAR(128) NOT NULL,
    from_mape           FLOAT,
    to_mape             FLOAT,
    actor               VARCHAR(64),
    reason              TEXT,
    ts                  DATETIME NOT NULL,
    KEY ix_switch_slot_ts (slot, ts)
);
```

### 10. 新建表 `scheduler_task`

```sql
CREATE TABLE scheduler_task (
    task_id                 VARCHAR(64) NOT NULL PRIMARY KEY,
    name                    VARCHAR(128) NOT NULL,
    task_type               VARCHAR(64) NOT NULL,
    slot                    VARCHAR(64),
    cron_expression         VARCHAR(64) NOT NULL,
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    payload_json            JSON,
    last_execution_time     DATETIME,
    last_result_json        JSON,
    updated_at              DATETIME NOT NULL,
    KEY ix_task_slot_enabled (slot, enabled)
);
```

### 11. B' 类：`search_space_registry`（文件为源 + DB 镜像）

```sql
CREATE TABLE search_space_registry (
    registry_id     VARCHAR(64) NOT NULL PRIMARY KEY,   -- load_forecast_v1/v2/v3
    version         INT NOT NULL DEFAULT 1,
    description     VARCHAR(512),
    layers_json     JSON,                                -- v1/v2 结构
    actions_json    JSON,                                -- v3 结构
    source_path     VARCHAR(512),                        -- 相对路径
    content_hash    CHAR(64),                            -- SHA-256
    synced_at       DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL
);
```

### 12. B' 类：`feature_recipe`

```sql
CREATE TABLE feature_recipe (
    recipe_id       VARCHAR(64) NOT NULL PRIMARY KEY,
    description     VARCHAR(512),
    patch_json      JSON,
    source_path     VARCHAR(512),
    content_hash    CHAR(64),
    synced_at       DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL
);
```

### 13. B' 类：`production_workflow_registry`

```sql
CREATE TABLE production_workflow_registry (
    slot            VARCHAR(64) NOT NULL PRIMARY KEY,
    workflow_id     VARCHAR(128) NOT NULL,
    version_tag     VARCHAR(128),
    meta_json       JSON,
    source_path     VARCHAR(512),
    content_hash    CHAR(64),
    synced_at       DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL
);
```

## 二、双写方向与失败降级

### A 类 — DB 为源 + JSON 兜底

```
业务写入
  ↓
try:
    DB upsert（权威）
except:
    log.warning + 记录到失败队列（后台重试）
  ↓
JSON 写入（过渡期保留，Phase 3 移除）
```

读逻辑：
```
try:
    DB read
except:
    log.warning
    JSON read（兜底）
```

### B' 类 — 文件为源 + DB 镜像

```
文件保存（Git-tracked）
  ↓
触发 sync（启动钩子 / API / 定时）
  ↓
计算 content_hash
  ↓
if hash 变了:
    DB upsert
```

读逻辑：
```
DB read
if miss:
    file read → sync → DB read
```

## 三、断点恢复流程

### 服务重启（自动）
```
main.py 启动
  ↓
scan_and_mark_interrupted():
    UPDATE experiment_run
    SET previous_status = status,
        status = 'interrupted',
        recoverable = TRUE,
        interrupted_at = NOW(),
        error_message = '服务重启，进程状态丢失'
    WHERE status IN ('running', 'pending', 'waiting_review', 'cancelling');
  ↓
mark_dead_workers():
    UPDATE autoresearch_job
    SET status = 'interrupted', finished_at = NOW()
    WHERE status = 'running'
      AND heartbeat_at < NOW() - INTERVAL 2 MINUTE;
```

### 用户点 Resume
```
POST /api/workflows-enhanced/auto-research-resume/{run_id}
  ↓
run_state = SELECT snapshot_state FROM experiment_run WHERE id = %s
completed = SELECT iteration_no FROM experiment_trial
            WHERE run_id = %s AND status = 'success'
  ↓
resume_from = max(completed) + 1
  ↓
INSERT INTO experiment_decision (run_id, decision_type, payload_json)
VALUES (%s, 'run_resumed', {resume_from, completed, remaining})
  ↓
INSERT INTO autoresearch_job (run_id, status, payload_json)
VALUES (%s, 'pending', {resume:true, start_iteration:resume_from, ...})
  ↓
任意 worker 通过 SELECT FOR UPDATE SKIP LOCKED 领走
```

## 四、跨机器 Job Queue

### Worker 领任务
```sql
BEGIN;
SELECT run_id, payload_json
  FROM autoresearch_job
 WHERE status = 'pending'
 ORDER BY created_at ASC
 LIMIT 1
 FOR UPDATE SKIP LOCKED;

UPDATE autoresearch_job
   SET status = 'running',
       pid = %s,
       host = %s,           -- 关键：写入自己的 hostname
       started_at = NOW(),
       heartbeat_at = NOW()
 WHERE run_id = %s;
COMMIT;
```

### 心跳
```sql
UPDATE autoresearch_job
   SET heartbeat_at = NOW()
 WHERE run_id = %s AND host = %s;
```

### 完成
```sql
UPDATE autoresearch_job
   SET status = %s, finished_at = NOW()
 WHERE run_id = %s;
```

### 环境变量切换 backend
```
AUTORESEARCH_JOB_QUEUE_BACKEND=mysql   # 新（默认，Phase 2 后）
AUTORESEARCH_JOB_QUEUE_BACKEND=sqlite  # 旧（Phase 1 内可切回）
```

## 五、Repository 层组织

新增文件：

```
backend-service/services/db/repositories/
├── load_forecast.py         # 已有：station_data / prediction_result / accuracy_metric
├── pv_fault.py              # 已有：光伏故障
├── autoresearch.py          # 新增：experiment_run / trial / decision / job / candidate / knowledge
├── deployment.py            # 新增：deployment_slot / model_version / switch_event / scheduler_task
└── registry_sync.py         # 新增：search_space_registry / feature_recipe / production_registry
```

## 六、Sync 触发点（B' 类）

### 启动同步
```python
# main.py startup hook
from services.db.repositories.registry_sync import sync_all_from_files
sync_all_from_files()  # 扫描三份文件，按 content_hash 决定是否 upsert
```

### API 手动触发
```
POST /api/autoresearch/registries/reload
POST /api/autoresearch/recipes/reload
POST /api/deployment/production-registry/reload
```

## 七、迁移脚本骨架

```python
# scripts/migrate_autoresearch_storage_to_db.py

def main():
    # 1. Run 状态
    for run_dir in Path("data/autoresearch/runs").iterdir():
        snapshot = load_snapshot(run_dir / "snapshot.json")
        upsert_experiment_run(snapshot)
        for line in read_jsonl(run_dir / "trials.jsonl"):
            insert_experiment_trial(line)
        for line in read_jsonl(run_dir / "decisions.jsonl"):
            insert_experiment_decision(line)

    # 2. Insight
    for insight_file in Path("data/autoresearch/insights").glob("ares-*.json"):
        update_run_insight(insight_file)

    # 3. 知识层
    for layer in ["patterns", "anti_patterns", "hypothesis_templates", "raw_cases"]:
        for claim_file in Path(f"data/autoresearch/knowledge/{layer}").glob("*.json"):
            upsert_knowledge_claim(claim_file, layer)

    # 4. 候选池
    upsert_candidate_pool(Path("data/autoresearch/candidate_pool/baseline_comparison_candidate_pool.json"))
    upsert_candidate_verification(Path("data/autoresearch/candidate_pool/candidate_verification_queue.json"))
    insert_promotion_log(Path("data/autoresearch/candidate_pool/baseline_comparison_promotions_log.json"))

    # 5. 部署
    upsert_deployment_slots(Path("data/deployment/slots.json"))
    insert_switch_events(Path("data/deployment/switch_log.json"))

    # 6. Scheduler
    upsert_scheduler_tasks(Path("data/scheduler/tasks.json"))

    # 7. B' 静态配置
    sync_search_space_registries()
    sync_feature_recipes()
    sync_production_workflow_registry()

    print_summary()
```

## 八、Repository 接口约定

以 `autoresearch.py` 为例：

```python
class AutoResearchRepository:
    def __init__(self, adapter: DBAdapter) -> None: ...

    # experiment_run
    def upsert_run(self, run_data: dict) -> ExperimentRun: ...
    def get_run(self, run_id: str) -> Optional[ExperimentRun]: ...
    def list_runs(self, slot: str, limit: int = 50) -> List[ExperimentRun]: ...
    def mark_interrupted_running_runs(self) -> List[str]: ...   # 返回被标记的 run_id

    # experiment_trial
    def append_trial(self, run_id: str, trial: dict) -> None: ...
    def list_trials(self, run_id: str) -> List[ExperimentTrial]: ...
    def get_completed_iterations(self, run_id: str) -> Set[int]: ...

    # experiment_decision
    def append_decision(self, run_id: str, decision: dict) -> None: ...
    def list_decisions(self, run_id: str) -> List[ExperimentDecision]: ...

    # autoresearch_job
    def submit_job(self, run_id: str, payload: dict) -> None: ...
    def claim_job(self, host: str, pid: int) -> Optional[dict]: ...
    def heartbeat(self, run_id: str, host: str) -> None: ...
    def request_cancel(self, run_id: str) -> bool: ...
    def is_cancel_requested(self, run_id: str) -> bool: ...
    def finish_job(self, run_id: str, status: str) -> None: ...
    def mark_dead_workers(self, timeout_seconds: int = 120) -> List[str]: ...

    # candidate_pool（复用现有表 candidate_pool）
    def upsert_candidate(self, candidate_data: dict) -> None: ...
    def list_candidates(self, slot: str, status: Optional[str] = None) -> List[CandidatePool]: ...

    # candidate_verification
    def upsert_verification(self, item: dict) -> None: ...
    def list_verifications(self, slot: str, status: Optional[str] = None) -> List[CandidateVerification]: ...

    # candidate_promotion_log
    def append_promotion(self, entry: dict) -> None: ...

    # knowledge_claim（复用现有表）
    def upsert_claim(self, claim_data: dict) -> None: ...
    def query_claims_by_scenario(self, scenario_fingerprint: str, layer: Optional[str] = None) -> List[KnowledgeClaim]: ...
```
<!-- @AI_GENERATED: end -->
