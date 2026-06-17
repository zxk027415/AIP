# AGENTS.md

本文档记录当前项目 `/Users/zxk/Desktop/project/AIP-260520` 的仓库认知、第三代/第四代 AutoResearch 迭代状态、P0.7 验收结论和后续 Agent 接手约束。当前版本基于旧版本 `/Users/zxk/Desktop/project/AIP-2026.5.11` 继续修复，已推进到第四代控制面 P0.7 验收后、复验池与自动实验并行能力补强阶段。

## 默认沟通和工作方式

- 默认用中文回复，结论先行，表达简洁、具体。
- 修改代码或文件前先说明会改哪些文件、计划、影响范围。
- 不确定项目结构、接口、配置或命令时，先用 `grep_files` / `file_search` / `list_dir` 搜索，不猜。
- 优先小范围、可验证、容易回滚的改动，保持现有风格。
- 项目运行环境是 conda 环境 `aip_web`；后端运行、Python 脚本、pytest、语法/导入检查优先在该环境下执行。
- 不输出 secrets、tokens、private keys、`.env` 值或凭据；需要密钥时让用户用环境变量提供。
- 当前工作区很脏，不要擅自清理、重置、删除、提交或切换分支。
- 禁止使用 `git reset --hard`、`git checkout --` 等可能破坏本地改动的命令，除非用户明确授权。

## 项目一句话

这是一个"工业 AI 算法平台"全栈项目：前端用 React + TypeScript + Vite + Ant Design，后端用 FastAPI + Python，核心业务是可视化算法模板、函数/算子库、工作流执行、训练/预测/回测/调优闭环，以及正在重点演进的 AutoResearch 自动实验系统。

## 顶层目录

- `backend-service/`：后端服务，FastAPI 入口、API 路由、算法算子、工作流执行、AutoResearch 主循环和数据文件。
- `frontend-sevice/`：前端应用，React/Vite 项目。目录名拼写是 `sevice`，不要改名。
- `load_forecast_refactored/`：负荷预测专项实验工程，包含独立配置驱动回测、威海回测、多模型集成、特征工程和数据穿越审计。
- `design/`：AutoResearch、调优、工作流收敛等设计文档和阶段变更记录。
- `docs/`、`docs_zxk/`：平台说明、学习文档、工程契约模板和个人整理文档。
- `.kiro/specs/`：Kiro 规格文档；`autoresearch-next-gen/requirements.md` 是下一代 AutoResearch 演进需求。
- `output/`、`transcript/`、`catboost_info/`：实验输出、对话记录、训练日志等运行产物。

## 启动方式

根目录有 `start-dev.sh`，会用 macOS Terminal 分别启动后端和前端：

```bash
bash start-dev.sh
```

脚本行为：

- 后端目录：`backend-service`
- 后端环境：`conda activate aip_web`
- 后端会加载：`backend-service/scripts/load_glm_env.sh`
- 后端命令：`uvicorn main:app --reload --port 8080`
- 前端目录：`frontend-sevice`
- 前端命令：`npm run dev`
- 访问地址：后端 `http://localhost:8080`，前端通常是 `http://localhost:5173`

后续由 Agent 代为启动服务或 AutoResearch worker 时，默认使用用户可见的 macOS Terminal 窗口，而不是 Codex 后台 shell 会话：

- 后端：单独 Terminal 窗口，目录 `backend-service`，先加载 `scripts/load_glm_env.sh`，再运行 `uvicorn main:app --port 8080`。
- AutoResearch worker：单独 Terminal 窗口，目录 `backend-service`，先加载 `scripts/load_glm_env.sh`，再运行 `python worker_autoresearch.py --loop`。
- 前端：如需要，单独 Terminal 窗口，目录 `frontend-sevice`，运行 `npm run dev`。
- 如果用户明确要求"用 VSCode 启动"，再改用 VSCode 集成终端；否则优先 Terminal，方便用户看到日志和手动停止。
- 长 run 已经启动后再修改 Python 代码，不会影响正在运行的 worker；要验证新代码必须先安全 cancel 当前 run，再重启后端/worker，最后重新提交 run。
- 停止实验时先调用 AutoResearch cancel 接口，让 run 和当前 compare 子任务有机会落状态；只有进程无法退出时才考虑终止进程，并明确说明影响。
- 长时间 AutoResearch 实验应使用 `bash start-experiment.sh`，它会一次性启动后端（8080，无 reload）、前端（3001）和 AutoResearch Worker（`--loop`），三个 Terminal 窗口均加载 `scripts/load_glm_env.sh`，确保 GLM 可用。

## 后端概览

后端入口是 `backend-service/main.py`。FastAPI 应用标题是"工业AI算法平台 API"，版本 `0.2.0`，注册了认证、系统状态、函数库、普通工作流、增强工作流、行业场景、回测、部署、算法运维、算法 Agent、LLM 配置、负荷预测等路由。CORS 允许 `http://localhost:5173` 和 `http://localhost:3000`。

关键 API 和服务：

- `backend-service/api/workflows_enhanced.py`：增强工作流、Baseline/Challenger 回测、AutoResearch 主循环（proposal、候选池、novelty audit、verification queue、run insight）等核心逻辑。
- `backend-service/services/reference_rolling_backtest/`：标准滚动回测参考实现。
- `backend-service/services/autoresearch_registry_service.py`：AutoResearch 搜索空间注册表加载、分层激活、饱和判断。
- `backend-service/services/feature_recipe_service.py`：特征配方解析，按 functionId 生成结构补丁。
- `backend-service/services/knowledge_layer.py`：AutoResearch 跨 run 知识 claim 的存储、检索、衰减、注入，以及 `normalize_scenario_fingerprint()` 统一指纹。
- `backend-service/services/dataset_profiler.py`、`dataset_profiler_models.py`：数据集画像（含 `profile_quality` 质量标记）。
- `backend-service/services/analyst_agent.py`、`research_question_generator.py`、`periodic_reflection.py`：数据画像归因、研究问题生成、阶段反思。
- `backend-service/services/autoresearch_glm_question_generator.py`：受控 GLM 研究问题生成器。GLM 只能提出 research question / experiment intent，不能直接写 patch；候选必须经过代码侧审计、去重和 evidence 校验。
- `backend-service/services/autoresearch_question_lifecycle.py`：研究问题生命周期和去重合并，维护 `open/testing/resolved/stale` 等状态。
- `backend-service/services/autoresearch_candidate_planner.py`：候选规划器：方向覆盖、scoreboard、exploration_health。
- `backend-service/services/autoresearch_evidence.py`：证据构建器：evidence_strength、patch_fingerprint、failure_reason。
- `backend-service/services/autoresearch_insight_builder.py`：run insight 构建器。
- `backend-service/services/experiment_quality.py`：实验质量评分。
- `backend-service/services/agent_orchestrator.py`：多 Agent 编排器。
- `backend-service/services/operator_backends/`：具体算子实现，如 XGBoost、LightGBM、CatBoost、Ridge、ensemble、滞后特征、滚动统计、节假日和工作日特征。
- `backend-service/services/operator_execution/`：算子执行框架、数据适配、全局配置注入、模型注册。

## 前端概览

前端目录是 `frontend-sevice/`。技术栈为 React 18、TypeScript、Vite、Ant Design 5、React Router、React Flow、ECharts、Zustand、Axios。

关键文件：

- `frontend-sevice/src/App.tsx`：前端路由入口。
- `frontend-sevice/src/components/MainLayout.tsx`：主布局。
- `frontend-sevice/src/pages/WorkflowBaselineComparePage.tsx`：Research Cockpit 主页面：实验卡、证据卡、问题卡、知识卡、策略卡、候选池、复验池。
- `frontend-sevice/src/pages/WorkflowEditorPage.tsx`：工作流编辑页。
- `frontend-sevice/src/pages/AlgorithmAgentPage.tsx`：算法 Agent 页面。
- `frontend-sevice/src/services/workflowEnhancedApi.ts`：增强工作流 API 客户端。
- `frontend-sevice/src/types/workflow-enhanced.ts`：增强工作流相关类型。
- `frontend-sevice/src/config/modelFamilyRegistry.ts`：模型家族参数注册表。
- `frontend-sevice/src/utils/tuningRecommendation.ts`：调优推荐回灌白名单映射。

前端常用命令：

```bash
cd frontend-sevice
npm run dev
npm run build
npm run lint
```

## AutoResearch 当前主链路（第四代 P0.7 之后）

核心循环在 `backend-service/api/workflows_enhanced.py` 的 `_run_autoresearch_task`：

1. 从前端请求和模板配置得到 `compare_config`、`search_space`、`evaluation_contract`、`runtime_patch`。
2. 每轮合并出 `effective_search_space`、`effective_contract`，通过 Candidate Planner 或规则采样参数/结构候选。
3. 调用 Baseline/Challenger 多窗口回测比对，Baseline 缓存使用内容哈希（覆盖 workflow 内容、窗口、契约、配置覆盖）。
4. 评估候选：每个候选写入 `novelty_audit`（基于 patch signature 去重），汇总到 `state["novelty_summary"]`。
5. Evidence 构建：group record 写入 `windows_total`、`windows_challenger_better`；cancelled/failed 补 `failure_reason`。
6. 生成或应用 GLM proposal，proposal 进入执行前走白名单、validator、风险等级判断。GLM 状态记录 `question_source`、`disabled_reason`、`glm_questioner_enabled`。
7. Periodic Reflection 消费 `exploration_health.scoreboard`、`evidence_summary`、`novelty_summary`，输出 coverage、trend、决策建议。
8. 运行结束时生成 `run_insight`，调用 `KnowledgeLayer.ingest_run_insight()`，使用 `normalize_scenario_fingerprint()` 统一指纹。

**新的闭环：候选池 → 复验池 → 多窗口复验 → Promote**

```
候选池 → 复验池 → 多窗口复验 → Promote
```

- 后端复验池 API（5 个端点）：`GET /candidate-verification-queue`、`POST .../from-candidate/{id}`、`POST .../start-next`、`POST .../{item_id}/start`、`POST .../{item_id}/cancel`
- 入池时按 `candidate_id` 和 `patch_signature` 去重，串行执行
- Promote 默认要求候选有复验池 `passed` 记录；人工强制 Promote 需显式 `force=true`
- 前端候选池表格有"入复验"按钮，复验池卡片位于 Pareto 前沿下方
- 复验池现在可与 AutoResearch run 并行启动：复验回测走独立 `_VERIFICATION_BACKTEST_POOL`，默认 `VERIFICATION_BACKTEST_WORKERS=1`，不再占用 `_AUTORESEARCH_BACKTEST_POOL`
- 复验启动有轻量资源水位保护：默认 `VERIFICATION_MIN_AVAILABLE_MEM_MB=1024`，低于阈值返回 `resource_pressure`；`force=true` 可绕过；设为 `0` 可关闭检查

**当前状态（2026-06-08）：**

| 模块 | 状态 | 说明 |
|------|------|------|
| Novelty Audit | ✅ 已实现 | `_build_candidate_novelty_audit` + `_summarize_candidate_novelty`，基于 patch signature 去重 |
| Evidence Contract | ✅ 已实现 | `windows_total`/`windows_challenger_better`/`failure_reason` 写入和读取 |
| Periodic Reflection 消费证据 | ✅ 已实现 | 优先消费 scoreboard/evidence_summary/novelty_summary |
| TrainProfile 画像质量 | ✅ 已实现 | `profile_quality` 含 source/point_count/has_real_load_curve 等字段 |
| KnowledgeLayer 指纹统一 | ✅ 已实现 | `normalize_scenario_fingerprint()` 统一白名单 + 哈希管道 |
| GLM Questioner 状态可解释 | ✅ 已实现 | `question_source`/`disabled_reason`/`glm_questioner_enabled` 等字段 |
| 复验池闭环 | ✅ 已实现 | 5 个 API + 前端 UI，串行执行 + Promote 门控 |
| 复验池与 AutoResearch 并行 | ✅ 已实现 | 复验独立 1-worker 线程池 + 内存水位保护；AutoResearch 活跃时 warning 但不阻断 |
| 复验 passed 证据反写 | ✅ 部分实现 | passed 后向源 run 追加 `multi_window_confirmed` evidence，并同步候选池 evidence；依赖 `source_run_id/source_iteration` |
| Baseline Cache 内容哈希 | ✅ 已实现 | 覆盖 workflow 内容、窗口、契约、配置覆盖 |
| 10 轮 smoke run | 🔄 验证中 | 验证字段/链路是否正常，不等同正式效果验收 |
| 历史强候选多窗口复验 | 🔄 部分完成 | `ver-af738bdd6c81` failed；剩余 2 条 queued 待后端空闲 |

**关键约定：**

- 默认只写运行时补丁，不直接修改模板 JSON。
- 显式 Promote/写回动作才会长期修改模板。
- 当前 run 的累计改动保存在 `runtime_patch`，影响后续轮次。
- Candidate Planner 不应长期固定 group 1 为 parameter；每轮 directions 覆盖如 `parameter/model/risk`、`parameter/feature/data`。
- 研究问题生成优先走受控 GLM Questioner；GLM 不可直接生成可执行 patch，只能输出问题、方向、证据引用、实验目标和 patch 意图。
- 单窗口收益只能作为候选信号；候选需 novelty audit 和复验；复验 passed 才能 Promote；active knowledge 需要多证据和场景匹配。

## 第三代修复记录

修复汇报来源：

- `/Users/zxk/Desktop/Obsidian Vault/AIP AutoResearch 汇报-2026-5-8/AutoResearch 第三代/AutoResearch问题修复汇报.md`

本版本重点修复了 CatBoost 并发训练死锁、训练层永不饱和、僵尸运行、Knowledge 摄入/注入、特征节点搜索空间缺失、Baseline 缓存永不过期、批量分组 `is` 比较等问题。

当前代码中已能看到的主要改动：

- `backend-service/services/reference_rolling_backtest/models.py`
  - 在导入 numpy/pandas/xgboost/catboost 前设置 `OMP_NUM_THREADS`、`OPENBLAS_NUM_THREADS`、`MKL_NUM_THREADS`、`VECLIB_MAXIMUM_THREADS`、`NUMEXPR_NUM_THREADS` 默认值为 `1`。
  - `_BO_LOCK.acquire()` 改为 `acquire(timeout=300)`，超时后记录 warning 并不持锁继续执行。
- `backend-service/api/workflows_enhanced.py`
  - AutoResearch 回测线程池最小并发提升到更高水位。
  - `_ALLOWED_SEARCH_SPACE_PATCH_KEYS` 补充特征/模型节点开关键。
  - 批量模式 best group 选择从 `is` 改为 `==`。
  - Baseline 缓存增加 `_baseline_cache_ts`，超 24h + 内容哈希一致才命中。
  - 单组 compare 增加异常保护，批量模式结束后清理本轮 comparison cancel events。
  - GLM proposal 前注入 `KnowledgeLayer.get_injection_candidates()`。
  - run insight 保存后调用 `KnowledgeLayer().ingest_run_insight(insight)`。
- `backend-service/services/autoresearch_registry_service.py`
  - 新增 `_LAYER_MAX_ITERATIONS`：`training=12`、`feature=16`、`model=20`、`data=20`。
  - `_is_layer_saturated()` 在某层成功采样次数达到上限后强制饱和，避免训练层永久阻塞后续层。

## 第四代 P0.7 验收记录（2026-05-26）

详见 Obsidian 汇总报告：`AutoResearch 第四代/AutoResearch第四代工作汇总报告_2026-05-26.md`

**50 轮复盘（run `ares-9c429d5ed43c`）核心结论：**

| 维度 | 结果 |
|------|------|
| 多方向探索覆盖 | ✅ 通过 |
| group 1 不再固定 parameter | ✅ 通过 |
| Research Question 去重 | ✅ 通过（98 条 → 7 条带生命周期） |
| Evidence 落账 | ✅ 通过（130 条记录） |
| Knowledge 治理 | ✅ 通过 |
| Top 候选是否新突破 | ❌ MAPE 4.2421 是历史重复 |
| 多窗口证据 | ❌ 130 条全是 `insufficient_evidence` |
| Reflection 消费证据 | ❌ coverage 输出 0.0 |
| Knowledge 置信度 | ❌ 单 run confidence 过高（1.0） |

**通俗解释：** 系统学会了"多方向探索"，但最好结果是历史上已发现过的。控制面改善了"过程质量"，还没改善"结论质量"。

**P0.7 复盘后 6 项代码修正（均已完成）：**

1. 候选新颖性审计（`_build_candidate_novelty_audit`，patch signature 去重）
2. Evidence Contract 修正（`windows_total`/`windows_challenger_better`/`failure_reason`）
3. Periodic Reflection 消费真实证据（scoreboard + evidence_summary + novelty_summary）
4. TrainProfile 画像质量标记（`profile_quality` 字段）
5. KnowledgeLayer 指纹统一和置信度收紧（`normalize_scenario_fingerprint`）
6. Research Question / GLM 状态可解释（`question_source`/`disabled_reason` 等字段）

## Review 重点（更新于 2026-05-29）

已修复/部分修复：

- ~~`KnowledgeLayer` fingerprint 不统一~~ → 已通过 `normalize_scenario_fingerprint()` 统一，但需要新 run 验证命中效果。
- ~~Baseline 缓存只按 TTL 过期~~ → 已增加内容哈希，覆盖 workflow 内容/窗口/契约/配置覆盖。
- ~~GLM 研究问题审计过严~~ → 已增加 `question_source`/`disabled_reason` 可解释性，审计逻辑放宽了对 evidence 引用的严格校验。

仍待关注：

- **AnalystAgent / TrainProfile**：当前画像来源是回测窗口 actual 值，不是完整训练集。多数画像字段仍是空对象或 `unknown`，需要在 run 启动时从原始数据计算。
- **_BO_LOCK 超时**：只是避免永久等待，不等同于彻底消除 scipy/BLAS 并发风险。
- **`except Exception: pass`**：仍然存在，特别是知识、特征配方、候选写入等非阻塞链路，排查时要优先打开日志。
- **AutoResearch run 状态**：cancel events、comparison store 仍以纯内存为主，服务重启会丢状态。
- **GLM 候选 != 可执行 patch**：GLM 问题可被接受不代表 patch 可执行，真正执行前仍必须经过 Designer/validator/风险门控。
- **复验池 evidence 反写仍需验证**：代码已补 passed → `multi_window_confirmed` 的桥接同步，但只在复验项有 `source_run_id/source_iteration` 时生效；后续要用真实复验 passed 记录验证源 run、候选池、KnowledgeLayer 是否同步一致。
- **Smoke run ≠ 正式验收**：10 轮 smoke 通过只验证链路是否工作，50 轮正式 run 才验证研究质量是否真正提升。

## 工作流与上线口径

三类工作流边界：

- Train：产出可复用模型工件和训练元数据。
- Predict：消费明确的 `model_ref` 做未来预测，禁止隐式重训。
- Backtest：历史窗口模拟真实运行并统一评分，作为调优评分器。

重要原则：

- 调优是编排层，回测是评分器。
- 上线的是实验结论，不是临时实验脚本。
- 特征、模型、评估口径应尽量保持单一事实来源。
- 实验增益要迁移成标准模板配置或标准算子参数，再复验和灰度。

## 负荷预测专项工程

目录 `load_forecast_refactored/` 是较独立的电力负荷预测实验工程，面向 AESC、蒙西、威海等场景。

关键文件：

- `run.py`：统一离线回测入口，YAML 配置驱动。
- `run_weihai_backtest.py`：威海专项滚动回测。
- `run_weihai_backtest_weather.py`：带天气数据的威海回测。
- `evaluate_and_improve.py`：精度评估和数据穿越审计。
- `features/engine.py`：统一特征工程。
- `models_pkg/trainer.py`：XGBoost 训练和贝叶斯调参。
- `models_pkg/wrapper.py`：模型包装器。
- `evaluation/metrics.py`：评估指标。

负荷预测和回测相关改动必须特别注意数据穿越、评估口径一致、训练/预测/回测职责边界。

## 数据与配置

后端数据主要在：

- `backend-service/data/functions.json`
- `backend-service/data/workflows_enhanced/`
- `backend-service/data/workflows_enhanced/workflow-load-forecast-training-v2.json`
- `backend-service/data/workflows_enhanced/workflow-load-forecast-prediction-v2.json`
- `backend-service/data/workflows_enhanced/workflow-load-forecast-backtest-v2.json`
- `backend-service/data/workflows_enhanced/workflow-load-forecast-tuning-v1.json`
- `backend-service/data/autoresearch_search_registries/load_forecast_v1.json`
- `backend-service/data/autoresearch_run_insights/`
- `backend-service/data/autoresearch_knowledge/`
- `backend-service/data/uploads/`
- `backend-service/data/demo/`
- `backend-service/data/backtest/`
- `backend-service/data/deployment/`
- `backend-service/data/autoresearch/candidate_pool.json`
- `backend-service/data/autoresearch/candidate_verification_queue.json`

很多 JSON、数据库、日志和回测产物已经在工作区里有修改或未跟踪状态，改动前必须看 `git status --short`，不要误删。

## 测试与校验

后端依赖中包含 `pytest` 和 `pytest-asyncio`。常见命令：

```bash
conda activate aip_web
cd backend-service
pytest
```

前端构建校验：

```bash
cd frontend-sevice
npm run build
```

当前仓库没有干净、统一、快速的全量测试信号。做具体改动时，优先选择与改动范围最接近的测试；如果只改文档，不需要跑后端/前端全量测试。

AutoResearch 研究问题/GLM Questioner 的 focused 校验：

```bash
cd backend-service
PYTHONPATH=. conda run -n aip_web pytest tests/test_autoresearch_glm_question_generator.py tests/test_autoresearch_question_lifecycle.py tests/test_analyst_and_research_questions.py -q
PYTHONPATH=. conda run -n aip_web python -m py_compile services/autoresearch_glm_question_generator.py services/research_question_generator.py services/autoresearch_question_lifecycle.py api/workflows_enhanced.py
```

前端涉及 AutoResearch 页面时，再运行：

```bash
cd frontend-sevice
npm run build
```

已知 `npm run build` 可能出现 Tailwind "No utility classes were detected" 和 chunk size warning；这些是当前项目已有警告，不能直接当作本次改动失败。

## 当前工作区注意事项

当前 `git status --short` 显示工作区非常脏，包含大量：

- `__pycache__` 修改/删除。
- 后端 API、服务、算子文件修改。
- 前端页面、服务、类型、国际化文件修改。
- 数据 JSON、SQLite 数据库、CatBoost 日志和回测产物修改。
- `design/`、`docs/`、`.kiro/`、`output/` 等未跟踪文件。

后续 Agent 必须遵守：

- 不要清理、重置或覆盖既有变化，除非用户明确要求。
- 不要因为 `pycache` 或运行产物很多就擅自删除。
- 做代码修改前确认目标文件是否已有用户改动，必要时只做最小补丁。
- 手工改文件优先用 `apply_patch`。
- 不要做无关重构、重命名、目录移动或格式化。

## 下一步路线图（更新于 2026-05-29）

### 近期（10 轮 smoke run 结束后立即做）

| # | 工作 | 说明 |
|---|---|---|
| 1 | 启动复验池剩余 2 条强候选的多窗口复验 | `single_best + train_days=90` 已 failed；剩余 `all_adaptive`、`subset_adaptive` 等后端空闲后逐条跑 |
| 2 | 根据复验结果决定是否 Promote | 只有 `passed` 的候选才能成为新 baseline |
| 3 | 完整 run 内验证 GLM Questioner | 单独调用已通过；下一步看完整 AutoResearch run 中是否持续产生 accepted 问题 |
| 4 | 跑一次 50 轮正式 run | 验证控制面是否真正提升研究质量（方向覆盖、Top 候选新颖性、知识沉淀可信度） |

### 中期（基础设施完善）

| # | 工作 | 说明 |
|---|---|---|
| 5 | Dataset Profiler 对接真实数据源 | 当前 `TrainProfile` 大部分字段为空对象或 `unknown`，需要在 run 启动时从原始数据计算 |
| 6 | Reflection Agent 独立模块 | 把当前人工复盘的逻辑固化为独立服务，输入 run 产物，输出结构化 JSON 报告 |
| 7 | Evidence Agent | 专门审计 evidence contract、failure_reason、单窗口/多窗口知识升级 |
| 8 | Evidence 反写闭环 | verification passed → update evidence → upgrade knowledge → Promote 的全链路同步 |
| 9 | Reporter Agent | 把复盘报告自动写入 Obsidian 和 Kiro tasks |
| 10 | 防偏科 | Planner direction coverage 强制执行，非 parameter 方向最低探索配额 |
| 11 | 多窗口并发优化 | 自适应降并发 + 动态超时 + 单组内分批并发（chunk_size=2） |
| 12 | cv_fold_metrics 回测引擎扩展 | 让回测引擎返回每个 fold 的 train_loss/val_loss/val_mape |
| 13 | 主循环拆分 | 把 `_run_autoresearch_task` 中的采样、回测、GLM、反思、知识写入拆到独立 service |

### 远期（新能力建设）

| # | 工作 | 说明 |
|---|---|---|
| 14 | RAG 内部知识库 | 用 RAGFlow 构建 AIP/AutoResearch 项目知识库，支持项目问答和报告辅助 |
| 15 | ResearchSkill schema | 将多窗口确认 + 场景指纹匹配的结论固化为可复用技能 |
| 16 | Agent Workbench 前端 | 展示只读复盘、Agent 状态、报告写入结果的统一工位界面 |
| 17 | CrewAI 三 Agent 原型 | 快速验证 Analyst → Hypothesis → Designer 流水线 |
| 18 | LangGraph StateGraph 生产化 | 用状态图重写已验证的多 Agent 流程，支持可恢复、可审计、可插入人工审核 |
| 19 | 服务器迁移 smoke run | 复制 repo 到服务器，跑 3-5 轮对比速度和结果一致性 |
| 20 | RAPIDS/GPU 加速 | 只有当算力确认为主瓶颈时才考虑 |

## 关键原则（贯穿始终）

1. **先验收再演进** — 不在没有真实数据反馈的情况下继续堆功能。
2. **单窗口不可信** — 任何候选必须经过多窗口复验才能 Promote 或沉淀为知识。
3. **新颖性优先** — 历史重复的强候选不应继续占据 Top 区域，系统应优先探索新方向。
4. **可解释** — 每个决策（为什么探索这个方向、为什么 stale、为什么 reject）都要有结构化原因。
5. **不破坏现有** — 工作区很脏，不清理、不重置、不删除历史产物。
6. **小步验证** — 每次改动后跑短 run 验证，不直接开长 run。

## 核心概念的置信度层级

| 层级 | 含义 | 当前策略 |
|---|---|---|
| 单窗口正收益 | 某个窗口上变好了 | 只能作为候选信号 |
| 候选池 candidate | 值得关注的配置 | 需要 novelty audit 和复验 |
| 复验池 passed | 多窗口复验通过 | 可以 Promote |
| active knowledge | 可注入的高置信经验 | 需要多证据和场景匹配 |
| promoted baseline | 新主线 baseline | 只应来自复验通过的候选 |

## 2026-05-25/29 AutoResearch 接手重点

### Research Cockpit 信息架构（05-25 完成）

- Research Cockpit 主展示已收敛为五张卡：Experiment 实验卡、Evidence 证据卡、Question 问题卡、Knowledge 知识卡、Strategy 策略卡。
- Evidence 卡里的"不能沉淀为知识"指的是"当前实验结论/候选知识声明"证据不足。
- Experiment 卡的原始 JSON 默认显示中文解释，原始 JSON 放二级折叠。
- Question 卡区分"当前问题"和"历史问题"折叠区。
- Knowledge 卡主统计已改成当前 run 口径。
- 候选池默认只显示来源 run 已完成 ≥10 轮的候选，按 MAPE 改善降序。
- 最近 AutoResearch run 区域改为长期记录视图，支持 interrupted/failed/cancelled recover。
- AutoResearch resume 现在允许 `interrupted`、`failed`、`cancelled` 三类状态恢复。

### 候选池运营（05-25 完成）

相关主文件：`frontend-sevice/src/pages/WorkflowBaselineComparePage.tsx`、`backend-service/api/workflows_enhanced.py`。

下一会话若继续处理候选池，优先检查：

- 候选池是否需要增加"全部候选 / 成熟候选"切换。
- 是否把完成轮数计算下沉到后端候选池 API。
- 是否增加候选去重：按 `diff_from_baseline + effective_parameter_patch + effective_structure_patch` 生成展示层签名。

### 复验池闭环与并行能力（05-26 完成，06-08 补强）

- 前端候选池表格新增"入复验"按钮，打开设置弹窗（复验窗口、聚合方式、最少胜出窗数、最小分差、是否立即启动、备注）。
- 复验池卡片位于 Pareto 前沿下方，展示 Baseline MAPE / Challenge MAPE。
- Promote 弹窗提示默认只能 Promote 复验通过的候选，保留"人工强制 Promote"开关。
- 复验池启动不再因 active AutoResearch run 被 `_has_active_autoresearch_run()` 硬阻断；活跃时写 warning 日志，继续使用独立复验池执行。
- 复验回测通过复验线程的独立 event loop 标记路由到 `_VERIFICATION_BACKTEST_POOL`，默认 `VERIFICATION_BACKTEST_WORKERS=1`，窗口仍按 Baseline → Challenger 串行执行。
- `_run_verification_item_thread` 手动创建的 event loop 已在异常路径关闭，避免反复复验后 loop 泄漏。
- 复验启动前会做 best-effort 内存水位检查：macOS 读 `vm_stat`，Linux 读 `/proc/meminfo`；低于 `VERIFICATION_MIN_AVAILABLE_MEM_MB` 时返回 `resource_pressure`，`force=true` 可绕过。
- 前端复验池 Alert 已更新为 info 口径：可与 AutoResearch 同时执行，但内存压力过高时后端会阻止自动启动。
- 相关文档：`docs/research_cockpit_information_architecture_*_2026-05-25.md`，以及 Obsidian `AutoResearch 第四代/需求设计|实现进度|改动落地|展示汇报` 下的同名整理文档。

验证记录：

```bash
cd frontend-sevice
npm run build

cd backend-service
PYTHONPATH=. /opt/miniconda3/envs/aip_web/bin/python -m py_compile api/workflows_enhanced.py
```

2026-06-08 复验池并行补强验证记录：

```bash
cd backend-service
/opt/miniconda3/envs/aip_web/bin/python -m py_compile api/workflows_enhanced.py

cd frontend-sevice
npm run build
```

已知 `npm run build` 仍会出现 Tailwind "No utility classes were detected" 和 Vite chunk size warning，这是既有警告，不是本阶段改动失败。

## 关键文件索引

| 文件 | 职责 |
|------|------|
| `backend-service/api/workflows_enhanced.py` | AutoResearch 主循环、所有增强工作流 API、复验池路由 |
| `backend-service/services/autoresearch_candidate_planner.py` | 候选规划器：方向覆盖、scoreboard、exploration_health |
| `backend-service/services/autoresearch_evidence.py` | 证据构建器：evidence_strength、patch_fingerprint、failure_reason |
| `backend-service/services/knowledge_layer.py` | 知识层：ingest/inject/decay/conflict、normalize_scenario_fingerprint |
| `backend-service/services/periodic_reflection.py` | 阶段反思：消费 scoreboard/evidence/novelty，输出决策 |
| `backend-service/services/dataset_profiler.py` | 数据集画像：train/validation/test/tri_diagnosis/cross_window |
| `backend-service/services/dataset_profiler_models.py` | 画像数据模型：TrainProfile（含 profile_quality） |
| `backend-service/services/autoresearch_question_lifecycle.py` | 研究问题生命周期：去重、状态迁移、suppression |
| `backend-service/services/autoresearch_glm_question_generator.py` | GLM 研究问题生成器：受控生成、审计、fallback |
| `backend-service/services/autoresearch_insight_builder.py` | run insight 构建器：scenario_fingerprint_inputs、exploration_summary |
| `backend-service/services/experiment_quality.py` | 实验质量评分：单变量控制、信息增益、收益递减预测 |
| `backend-service/services/agent_orchestrator.py` | 多 Agent 编排器：multi_agent/single_agent 模式、hypothesis 去重 |
| `frontend-sevice/src/pages/WorkflowBaselineComparePage.tsx` | Research Cockpit 主页面：实验卡、证据卡、问题卡、知识卡、复验池 |
| `start-experiment.sh` | 一键启动长实验环境（后端 8080 + 前端 3001 + Worker） |
