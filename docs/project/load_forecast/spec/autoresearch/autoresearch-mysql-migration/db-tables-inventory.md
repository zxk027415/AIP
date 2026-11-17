<!-- @AI_GENERATED -->
# AIP 平台 MySQL 数据表全景报告（40 张表）

**MySQL 库**：`aip_algo_platform`
**Alembic 当前 revision**：`2a240e0c2ce6`
**报告生成时间**：2026-07-09（Phase 0 前半段完成后）
**关联文档**：
  - `plan.md` — 迁移整体规划
  - `design.md` — Schema DDL 与技术设计
  - `tasks.md` — 分阶段任务清单

## 图例

- ✅ 已在生产使用
- ⚠️ Phase 1 双写目标（当前 DB 为空表，业务代码尚未接入）
- 📁 B' 类：文件为源 + DB 镜像
- 🆕 本次 AutoResearch MySQL 迁移新建

---

## 一、AutoResearch 主循环（11 张表）

对应 AIP 页面：**Research Cockpit / 工作流基线对比**
（前端 `frontend-sevice/src/pages/WorkflowBaselineComparePage.tsx`）

| # | 表名 | 职责 | 关键字段 | 对应本地文件（双写方向） |
|---|---|---|---|---|
| 1 | `experiment_run` | AutoResearch 单次 run 的主状态记录（已扩展 10 字段） | id / slot / status / previous_status / recoverable / snapshot_state (JSON) / current_iteration / total_iterations / runtime_patch / config / run_insight / baseline_workflow_id / error_message / started_at / finished_at / interrupted_at / resumed_at / updated_at | ⚠️ `data/autoresearch/runs/{run_id}/snapshot.json` |
| 2 | `experiment_trial` 🆕 | 每一轮 iteration 的明细（一个 run 对应 N 行） | run_id / iteration_no / status / override_json / evidence_json / mape_improvement / baseline_mape / challenger_mape | ⚠️ `data/autoresearch/runs/{run_id}/trials.jsonl` |
| 3 | `experiment_decision` 🆕 | 决策事件流（run_started / cancel_requested / proposal_applied 等） | run_id / seq / decision_type / actor / payload_json | ⚠️ `data/autoresearch/runs/{run_id}/decisions.jsonl` |
| 4 | `autoresearch_job` 🆕 | Job 队列（跨机器打通用），支持 worker 心跳、cancel 标记 | run_id / status / pid / **host** / heartbeat_at / cancel_requested / payload_json | ⚠️ `data/autoresearch/jobs.sqlite` |
| 5 | `candidate_pool` | 候选池：每一轮产出的候选配置 | id / slot / run_id / workflow_id / patch_signature / best_mape / evidence / status | ⚠️ `data/autoresearch/candidate_pool/baseline_comparison_candidate_pool.json` |
| 6 | `candidate_verification` 🆕 | 复验队列：候选进入多窗口复验的中间态 | id / candidate_id / slot / source_run_id / source_iteration / status / config_json / evidence_json | ⚠️ `data/autoresearch/candidate_pool/candidate_verification_queue.json` |
| 7 | `candidate_promotion_log` 🆕 | 候选晋升审计（append-only） | slot / candidate_id / action (promoted / rejected / force_promoted) / actor / reason / payload_json | ⚠️ `data/autoresearch/candidate_pool/baseline_comparison_promotions_log.json` |
| 8 | `knowledge_claim` | 知识层四类 claim（patterns / anti_patterns / hypothesis_templates / raw_cases） | id / slot / scenario_fingerprint / claim_type / claim_data / confidence / source_run_id / decayed_at | ⚠️ `data/autoresearch/knowledge/{layer}/*.json` |

**B' 类双写（文件为源 + DB 镜像）**：

| # | 表名 | 职责 | 关键字段 | 对应本地文件（文件权威） |
|---|---|---|---|---|
| 9 | `search_space_registry` 🆕 | AutoResearch 搜索空间注册表（v1 / v2 / v3） | registry_id / version / description / layers_json / actions_json / **source_path / content_hash / synced_at** | 📁 `data/autoresearch/registries/load_forecast_v{1,2,3}.json` |
| 10 | `feature_recipe` 🆕 | 特征配方 | recipe_id / description / patch_json / **source_path / content_hash / synced_at** | 📁 `data/autoresearch/recipes/feature_recipes.json` |
| 11 | `production_workflow_registry` 🆕 | 生产工作流注册表（静态映射） | slot / workflow_id / version_tag / meta_json / **source_path / content_hash / synced_at** | 📁 `data/autoresearch/production/production_workflow_registry.json` |

---

## 二、算法部署链路（4 张表）

对应 AIP 页面：**算法部署**
（前端 `frontend-sevice/src/pages/AlgorithmDeploymentPage.tsx` 及各 Tab 子页面）

| # | 表名 | 职责 | 关键字段 | 对应本地文件（双写方向） |
|---|---|---|---|---|
| 12 | `deployment_slot` 🆕 | 槽位配置：生产 workflow、冷却期、影子/预上线上限 | slot / production_workflow_id / cooldown_days / max_shadow_slots / max_prelaunch_slots / training_window_days / switch_observation_days | ⚠️ `data/deployment/slots.json`（顶层字段） |
| 13 | `deployment_model_version` 🆕 | 每个 slot 下所有版本（生产 + 影子 + 预上线 + 退役）；预上线元数据内嵌 JSON | id / slot / workflow_id / status (production/shadow/prelaunch/retired) / accuracy_score / consecutive_better_days / source_run_id / source_candidate_id / **prelaunch_meta_json** | ⚠️ `data/deployment/slots.json` 里的 `production_model / shadow_models / prelaunch_models` |
| 14 | `switch_event` 🆕 | 切换事件 append-only 审计 | event_id / slot / trigger_type (auto/manual/rollback) / from_workflow_id / to_workflow_id / from_mape / to_mape / actor / reason / ts | ⚠️ `data/deployment/switch_log.json` |
| 15 | `scheduler_task` 🆕 | Cron 定时任务（训练/预测/精度回填/mock 喂数据） | task_id / name / task_type / slot / cron_expression / enabled / payload_json / last_execution_time / last_result_json | ⚠️ `data/scheduler/tasks.json` |

---

## 三、负荷预测数据管线（8 张表，Task 1 已建）

对应 AIP 页面：
  - **算法部署** 的 Cron 任务 Tab、模型版本 Tab
  - **精度运营** (`PrecisionOpsDashboardPage.tsx`)

| # | 表名 | 职责 | 关键字段 | 对应本地文件 |
|---|---|---|---|---|
| 16 | `station_data` | ✅ 站点实测数据（负荷/温度/湿度按 slot 分区） | station_id / timestamp_utc / feature_name / value / slot / ingested_at | 无（唯一存储） |
| 17 | `station_observations` | ✅ Mock 数据源专用表：模拟"公司数据库"，每天 cron 追加新数据 | station_id / timestamp_utc / feature_name / value | 无（mock feeder 直接写） |
| 18 | `prediction_result` | ✅ 每次预测周期的预测值 + 实际值 | slot / workflow_id / version_tag / prediction_cycle_id / forecast_timestamp / predicted_value / actual_value / status / is_shadow / evaluated_at | 部分兼容 `data/precision_ops/predictions.db`（SQLite） |
| 19 | `accuracy_metric` | ✅ 按槽位聚合的滚动 MAPE / MAE | slot / workflow_id / rolling_mape / rolling_mae / valid_cycle_count / total_cycle_count / last_evaluated_at | ✅ 已 Task 1.5 同步 `data/precision_ops/{slot}/accuracy_metrics.json` |
| 20 | `version_registry` | 版本历史注册（含 baseline_mape） | slot / workflow_id / version_tag / status / source_run_id / source_candidate_id / baseline_mape / registered_at | ⚠️ 部分同步 `data/precision_ops/{slot}/version_registry.json` |
| 21 | `prelaunch_queue` | 预上线队列（老 schema，本次迁移后与 `deployment_model_version.prelaunch_meta_json` 语义重叠） | id / slot / candidate_id / workflow_id / version_tag / status / observation_days / graduate_tolerance_pct / current_rolling_mape / production_rolling_mape / evaluated_cycles / graduated_at / failed_at | ⚠️ 与 `data/deployment/slots.json` 的 `prelaunch_models` 双写。Phase 1 后建议以 `deployment_model_version` 为主 |
| 22 | `candidate_pool` | 跨模块复用（见 AutoResearch 章节） | — | — |
| 23 | `experiment_run` | 跨模块复用（见 AutoResearch 章节） | — | — |

---

## 四、光伏故障诊断（4 张表，Task 1 已建）

对应 AIP 页面：**光伏故障诊断迭代标注**（`IterativeLabelingReviewPage.tsx`）、**光伏预测**

| # | 表名 | 职责 | 关键字段 |
|---|---|---|---|
| 24 | `training_samples` | ✅ 标注训练样本：光伏支路时序 + 人工故障标签 | station_id / branch_id / timestamp / features_json / label / label_version |
| 25 | `model_versions` | ✅ 光伏模型版本元信息（tag / 样本量 / 标签空间版本 / 模型路径） | id / version_tag / sample_count / label_version / model_path / registered_at |
| 26 | `prediction_records` | ✅ 故障诊断推理记录 | id / model_version_id / station_id / branch_id / features_json / predicted_label / confidence / created_at |
| 27 | `diagnosis_results` | ✅ 诊断结果（关联 prediction_records） | prediction_id / fault_type / severity |

---

## 五、平台老表（13 张表，历史遗产）

对应 AIP 页面：**登录 / 用户管理**、**函数库**、**工作流编辑**、**Agent 编排** 等

| # | 表名 | 职责 | 定义位置 |
|---|---|---|---|
| 28 | `users` | 用户账号（登录、权限） | `database.py::User`（你的 `zxkhhh` 账号在这里） |
| 29 | `workflows` | 用户创建的算法模板（工作流实例） | `database.py::Workflow` |
| 30 | `workflow_executions` | 工作流执行历史 | `database.py::WorkflowExecution` |
| 31 | `workflow_templates` | 工作流模板库 | `models/algo_template.py::WorkflowTemplate` |
| 32 | `skills` | 打包后的算法模板（Skill 化） | `models/algo_template.py::Skill` |
| 33 | `algorithm_categories` | 算法分类目录 | `models/algorithm.py::AlgorithmCategory` |
| 34 | `algorithm_functions` | 算法函数（算子）注册表（前端函数库页面） | `models/algorithm.py::AlgorithmFunction` |
| 35 | `algorithm_versions` | 算法版本历史 | `models/algorithm.py::AlgorithmVersion` |
| 36 | `algorithm_audit_logs` | 算法审计日志 | `models/algorithm.py::AlgorithmAuditLog` |
| 37 | `workflow_agent_templates` | Workflow Agent 增强模板 | `models/workflow_agent_db.py::WorkflowAgentTemplate` |
| 38 | `workflow_agent_audit_logs` | Workflow Agent 审计 | `models/workflow_agent_db.py::WorkflowAgentAuditLog` |
| 39 | `domain_constraint_overrides` | 业务约束覆盖记录 | `models/workflow_agent_db.py::DomainConstraintRecord` |
| 40 | `best_practices` | 最佳实践记录 | `models/workflow_agent_db.py::BestPracticeRecord` |
| — | `service_status` | 服务健康检查表 | `models/service_status.py::ServiceStatus` |
| — | `alembic_version` | Alembic 版本管理表（自动创建） | Alembic 内部 |

---

## 六、按 AIP 前端页面反查

| 前端页面 | 主要读写的表 |
|---|---|
| **登录页** | `users` |
| **工作流编辑** (`WorkflowEditorPage.tsx`) | `workflows`, `workflow_templates`, `workflow_executions`, `algorithm_functions` |
| **算法 Agent** (`AlgorithmAgentPage.tsx`) | `workflow_agent_templates`, `workflow_agent_audit_logs`, `best_practices`, `domain_constraint_overrides` |
| **Research Cockpit** (`WorkflowBaselineComparePage.tsx`) | `experiment_run`, `experiment_trial`, `experiment_decision`, `autoresearch_job`, `candidate_pool`, `candidate_verification`, `candidate_promotion_log`, `knowledge_claim` + 读 `search_space_registry`, `feature_recipe` |
| **算法部署** 主页 (`AlgorithmDeploymentPage.tsx`) | `deployment_slot`, `deployment_model_version`, `production_workflow_registry` |
| ├─ 模型版本 Tab | `deployment_model_version`, `version_registry` |
| ├─ 预上线 Tab | `deployment_model_version` (status=prelaunch) + `prelaunch_queue` |
| ├─ 影子 Tab | `deployment_model_version` (status=shadow) |
| ├─ Cron 任务 Tab | `scheduler_task` |
| └─ 切换日志 Tab | `switch_event` |
| **精度运营** (`PrecisionOpsDashboardPage.tsx`) | `accuracy_metric`, `prediction_result`, `station_data` |
| **光伏故障诊断** | `training_samples`, `model_versions`, `prediction_records`, `diagnosis_results` |

---

## 七、双写状态总览（Phase 0 完成后的真实情况）

**当前状态**：Phase 0 只是建好了 schema，Phase 1 双写代码尚未接入。所以：

| 表 | 现状（此刻） | Phase 1 之后（1-2 周内） | Phase 3 之后 |
|---|---|---|---|
| `experiment_run` (含 10 个新字段) | 无业务写入，DB 里空 | 双写：`snapshot.json` + DB | 只写 DB，`snapshot.json` 停写只做兜底读 |
| `experiment_trial` / `experiment_decision` / `autoresearch_job` 🆕 | DB 空表 | 双写 | 只写 DB |
| `candidate_pool` / `knowledge_claim` | DB 空表（老 schema 已在） | 双写 | 只写 DB |
| `candidate_verification` / `candidate_promotion_log` 🆕 | DB 空表 | 双写 | 只写 DB |
| `deployment_slot` / `deployment_model_version` / `switch_event` / `scheduler_task` 🆕 | DB 空表 | 双写 `slots.json`/`switch_log.json`/`tasks.json` + DB | 只写 DB |
| `search_space_registry` / `feature_recipe` / `production_workflow_registry` 🆕 (B' 类) | DB 空表 | Startup 钩子 + `/reload` API 从文件 sync 到 DB | 文件仍是权威源，代码读 DB |
| `accuracy_metric` | ✅ Task 1.5 已双写 | 保持不变 | 只写 DB |
| `prediction_result` / `station_data` / `station_observations` | ✅ 已在生产使用 | 保持不变 | — |
| `prelaunch_queue`（老） | 空 | 保留兼容，与 `deployment_model_version.prelaunch_meta_json` 并存 | 建议弃用，语义合并到 `deployment_model_version` |
| pv_fault 4 张表 | ✅ 已在使用 | 不涉及本次迁移 | — |
| 13 张平台老表 | ✅ 使用中 | 不涉及本次迁移 | — |

---

## 八、可能踩的坑（提前提醒）

1. **`prelaunch_queue` vs `deployment_model_version.prelaunch_meta_json` 语义重叠**
   前者是 Task 1 建的独立表，后者是本次新建时把预上线元数据内嵌到部署版本表里。Phase 1 双写要明确以哪个为主，避免两处不同步。**建议**：`prelaunch_queue` 只保留读兜底，新写入统一走 `deployment_model_version`。

2. **`version_registry` 覆盖不完整**
   Task 1 建的表主要记 baseline_mape。本次新增的 `deployment_model_version` 也有版本状态。两个表关系是「版本历史（version_registry） vs 当前部署位（deployment_model_version）」。写入代码要清晰区分职责。

3. **`station_observations` 有两个来源**
   - `services/db/datasources/local_db_mock.py` 里定义的 `_DEFAULT_TABLE = "station_observations"` 是 mock 用
   - MySQL 里同名表也存在
   需要确认这两个是同一张表还是两张（`SHOW CREATE TABLE station_observations` 可以验证）。

4. **`experiment_run.snapshot_state` 大小上限**
   MySQL JSON 类型底层是 LONGTEXT（最大 4GB），但默认 `max_allowed_packet=4MB`。单个 run 的 state 快照通常 30-100KB，安全。极端情况下如果超过 4MB 需要调整 `max_allowed_packet` 或改成外部对象存储。

5. **Alembic 迁移在 Windows 上的执行方式**
   `services/db/adapter.py::run_migrations` 走 subprocess 会被 Windows 权限拒绝（已有 PermissionError 兜底）。手动执行迁移用 `scripts/gen_autoresearch_migration.py`，Linux/WSL 上则用 `alembic upgrade head` 即可。

---

## 附录 A：本次 AutoResearch MySQL 迁移新建的 12 张表清单

按 alembic 迁移文件 `2a240e0c2ce6_autoresearch_mysql_migration_add_tables_.py` 的建表顺序：

1. `autoresearch_job` — Job 队列（跨机器可用）
2. `candidate_promotion_log` — 候选晋升审计
3. `candidate_verification` — 复验队列
4. `experiment_decision` — 决策事件流
5. `experiment_trial` — Trial 明细
6. `deployment_slot` — 部署槽位配置
7. `deployment_model_version` — 部署版本（含 prelaunch/shadow/production/retired）
8. `switch_event` — 切换事件审计
9. `scheduler_task` — Cron 任务
10. `search_space_registry` — 搜索空间注册表（B' 类）
11. `feature_recipe` — 特征配方（B' 类）
12. `production_workflow_registry` — 生产工作流注册表（B' 类）

同时对 `experiment_run` 加了 10 个字段 + 2 个索引：
  - 字段：previous_status / recoverable / baseline_workflow_id / current_iteration / total_iterations / snapshot_state / error_message / interrupted_at / resumed_at / updated_at
  - 索引：ix_experiment_run_slot_status / ix_experiment_run_updated_at

## 附录 B：ORM 模型文件索引

| 文件路径 | 包含的表 |
|---|---|
| `backend-service/services/db/models/load_forecast.py` | station_data, experiment_run, candidate_pool, knowledge_claim, prediction_result, accuracy_metric, version_registry, prelaunch_queue |
| `backend-service/services/db/models/pv_fault.py` | training_samples, model_versions, prediction_records, diagnosis_results |
| `backend-service/services/db/models/autoresearch.py` 🆕 | experiment_trial, experiment_decision, autoresearch_job, candidate_verification, candidate_promotion_log |
| `backend-service/services/db/models/deployment.py` 🆕 | deployment_slot, deployment_model_version, switch_event, scheduler_task |
| `backend-service/services/db/models/registry.py` 🆕 | search_space_registry, feature_recipe, production_workflow_registry |
| `backend-service/database.py` | users, workflows, workflow_executions |
| `backend-service/models/algo_template.py` | workflow_templates, skills |
| `backend-service/models/algorithm.py` | algorithm_categories, algorithm_functions, algorithm_versions, algorithm_audit_logs |
| `backend-service/models/workflow_agent_db.py` | workflow_agent_templates, workflow_agent_audit_logs, domain_constraint_overrides, best_practices |
| `backend-service/models/service_status.py` | service_status |
<!-- @AI_GENERATED: end -->
