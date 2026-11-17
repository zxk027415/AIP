<!-- @AI_GENERATED -->
# `backend-service/scripts/` 脚本索引与约定

本目录同时包含正式迁移、数据构建、E2E 验收、审计与历史实验脚本。**不能按文件名批量删除。**

## 命名约定

- 不带 `_` 前缀：可复用/正式脚本，应提交 Git，并在本页登记主要入口。
- `_*.py`：一次性探针，已由 `.gitignore` 排除；任务结束后移到 `_archive_YYYY-MM-DD/` 或删除。
- `*.log`：运行输出，不进 Git。结论应写 JSON/Markdown 报告，而不是保留大日志。

## 关键正式入口

- `pv_project_full_chain_e2e.py` — 光伏项目九步 E2E：发布快照→建项目→继承 baseline→数据发版→审核准入→冻结→training→候选→喂数精度。默认会写真实 slot 回放目录；不想动回放用 `--skip-feed`。
- `pv_three_chain_checks.py` — 三路径检查集合。
- `build_pv_unseen_feed_source.py` — 构建训练未见的光伏盲测喂数源，`aip.ps1` 默认使用其产物。
- `e2e_tsc_288x3_verify.py` — TSC 288×3 网格验证。
- `pv_redesign_e2e_story.py` — 光伏重设计故事线 E2E。
- `align_pv_point_label_registry.py`、`migrate_label_path_isolation.py`、`migrate_k4_point_rest_normal.py` — 点路径标签/隔离迁移。运行前必须备份数据。
- `compact_replay_sessions.py` — replay session 压缩维护。
- `export_pv_point_rare_class_review_queue.py` — 导出点路径稀有类审核队列。
- `run_realtime_point_param_search.py`、`train_realtime_point_poc.py` — 实时点 POC/参数搜索，不是生产启动入口。
- `load_glm_env.ps1` / `load_glm_env.sh` — 加载 GLM 环境变量；只报告是否存在，不打印密钥值。

## 执行前检查

1. 在 `backend-service/` 下运行，设置 `$env:PYTHONPATH='.'`。
2. 先读脚本顶部 docstring，确认是否写 `data/`、是否需数据库、是否会改游标/registry。
3. 生产 registry、冻结、迁移脚本运行前备份对应 JSON/数据库。
4. E2E 的 PASS 证据写 `data/e2e/`；截图与日志不提交。
5. 长任务不要用临时后台终端悄悄跑；让接手人能看到日志并能安全停止。

## Legacy 脚本

- `legacy/test_iterative_labeling.sh` — 旧 curl 黑盒 smoke，已标 deprecated。它仍使用 `loopId` 等 camelCase 旧字段和 8080/5173 旧端口，不能作为当前验收；在补齐等价 TestClient API smoke 前暂留历史意图。

## 已归档内容

2026-09-17 将 11 个 `scripts/_*.py` 探针及 4 个历史 `.log` 移入 `_archive_2026-09-17/`。清单和恢复说明见 `docs/cleanup-archive-index-2026-09-17.md`。
<!-- @AI_GENERATED: end -->
