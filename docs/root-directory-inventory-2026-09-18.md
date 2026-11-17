<!-- @AI_GENERATED -->
# 仓库根目录清理判断（2026-09-18）

本文回答“根目录这些隐藏目录/文件哪些还需要”。判断原则：业务运行不消费 ≠ 可直接删除；Git 忽略也不等于缓存。先保护唯一证据与协作规则，再清可重建缓存。

## 1. 结论表

| 路径 | 负责什么 | 结论 | 删除后果/处理方式 |
|---|---|---|---|
| `.agents/` | 15 个共享 Agent Skill 的实体真源；`.claude` 与部分 `.kiro` skill 都链接到这里 | **必须保留** | 删除会同时破坏 Claude/Kiro 的共享 skill；121 文件已跟踪 |
| `.claude/` | 指向 `.agents/skills/*` 的 15 个 Junction，供 Claude 发现 skill | 可重建、按需保留 | 不使用 Claude 可删；会暂时失去 Claude skill 入口，但实体不丢 |
| `.codegraph/` | 本机代码图数据库和 daemon 日志，约 28 MB | **可安全删除** | 只损失本地索引速度，可重新建图 |
| `.cursor/` | 8 条 Cursor 工作区规则 | **必须保留并跟踪 rules** | 其中 3 条规则在 Kiro 没有等价副本；本轮已纳入 Git |
| `.hypothesis/` | property-based 测试 examples/unicode cache | **可安全删除** | 测试会重建，首次运行略慢 |
| `.kiro/` | Kiro rules、steering、skills（含独有 pptx） | **必须保留** | 删除会破坏当前 Kiro 协作行为和技能；逻辑路径已跟踪 |
| `.pids/` | 空 PID 目录 | **可安全删除** | 当前无引用、无文件 |
| `.pycache/` | Python 字节码镜像和 OS 元数据 | **可安全删除** | Python 会重建 |
| `.rivet/` | HANDOFF、三份 PV 计划、两个正式 skill、自动 knowledge、数据库/备份/探针 | **保留核心文本，缓存可删** | 本轮跟踪 plans 和两个正式 skill；knowledge JSONL/drafts/DB/tmp 保持本地忽略 |
| `.superpowers/` | 第七代前端 brainstorm 原型 HTML/PID 状态 | 建议保留或归档 | 不影响运行；是独有设计过程资产，6 文件已跟踪 |
| `.vscode/` | 空 `{}` settings.json | **可安全删除** | 无有效工作区设置 |
| `_archive_2026-09-17/` | 上轮整理归档 | **不能整删** | `misplaced-nested-data` 有 293 个唯一文件、42 个 dataset ID 被历史 lineage 引用；其它子目录可在确认后删 |
| `backend-service/` | FastAPI、算子、调度、registry 和运行数据 | **必须保留** | 平台后端；截图里的根 `_*.py/_*.out` 当前磁盘为 0 个，Explorer 是旧缓存 |
| `docs/` | 现状、规格、验收、会话和总交接 | **必须保留** | 阅读顺序见 `docs/README.md` |
| `fault-diag-algo-release-3.1/` | EnOS 光伏旧发布包及平台仍用的数据 | **必须保留在根** | 工作流/前端/历史记录按该相对路径读取 |
| `frontend-sevice/` | React/Vite 前端（目录拼写就是 sevice） | **必须保留** | 页面和 API 客户端 |
| `local_project/` | 离线负荷预测与唯一 operation_skill | **必须保留** | 不被 FastAPI import，但属于三块交接范围 |
| `logs/` | 2026-06-24 的 backend/frontend/worker 历史日志 | **已清文件，可删空目录** | 无引用、Git 可恢复；本轮加入 ignore |
| `output/` | 9 个 PV TSC strict-10/画像/隔离 MySQL 验收脚本与报告 | **必须保护** | 9 个文件均无仓内哈希副本；本轮从“整目录忽略”改为只跟踪该证据集 |

## 2. 根文件

| 文件 | 职责 | 结论 |
|---|---|---|
| `.aip.local.env` | 本机 conda 环境名与 DB 连接配置；值不进 Git | **必须保留或先安全迁移凭据**；`aip.ps1` 不会自动加载它，需调用方设置进程环境 |
| `.gitignore` | secrets、构建物、模型/运行资产、AI 工具缓存的边界 | **必须保留** |
| `AGENTS.md` | 仓库架构、AutoResearch 历史与协作约束 | **必须保留**；部分旧 macOS 路径/5 月状态由新 handoff 覆盖 |
| `aip.ps1` | Windows 正式 dev/experiment/restart/stop/status 入口 | **必须保留** |
| `PRODUCT.md` | 产品用户、品牌性格与 UX 原则；设计 skill 会读取 | **必须保留** |
| `README.md` | 新 clone 的第一入口、启动和最小验证 | **必须保留** |
| `skills-lock.json` | 15 个外部 skill 的来源、upstream 路径和 computedHash | **必须保留**；名称与 `.agents` 15 个目录完全一致，供未来重装/完整性核对 |
| `backend-service/scripts/legacy/test_iterative_labeling.sh` | 旧 curl 黑盒 smoke（从仓库根移入 legacy） | **暂留但已标 deprecated**；当前仍解析 camelCase `loopId`、固定 8080/5173、slot 参数失配，不能当验收；补等价 TestClient 后再删 |

## 3. `_archive_2026-09-17/` 如何拆

### 必须保留

`misplaced-nested-data/` — 原错误路径 `backend-service/backend-service/data/timeseries_point/` 的历史资产。当前代码不再写该路径，但：

- 335 文件约 13.17 MB；
- 293 文件约 13.13 MB 无仓内精确副本；
- 42 个 dataset ID 被 49 份历史 execution/model metadata 引用。

应生成 SHA-256 manifest、复制到外部交接介质，并保留旧 lineage 的兼容说明。不能因为路径错就认定数据无价值。

### 低风险、可确认后删除

- `backend-probes/`、`scripts-probes/`、`frontend-probes/` — 一次性探针。
- `backend-probe-logs/`、`backend-script-logs/` — 运行日志/中间 JSON。
- `frontend-e2e-shots/` — 可重拍截图。
- `duplicate-datasets/` — 与正牌威海数据 MD5 完全相同。
- `duplicate-operation-skill/` — 与 canonical 41 文件 SHA-256 全相同。

## 4. 本轮实际处理

1. `.cursor/rules/*.mdc` 从整体 ignore 中释放，作为当前 Cursor 协作规则纳入 Git。
2. `.rivet/plans/*.md` 与 `.rivet/skills/{brainstorming,visual-acceptance}/SKILL.md` 纳入 Git；自动 knowledge JSONL、数据库、tmp 和 raw drafts 继续忽略。
3. `output/pv_e2e_validation/*.py/*.json` 从整目录忽略中释放，保护 9 个唯一 PV 验收资产；其 `__pycache__` 始终忽略，语法验证时可重生成。
4. 删除 Git 中 3 个 2026-06-24 历史 logs，并加入 `logs/` ignore；空目录可手工移除。
5. `test_iterative_labeling.sh` 顶部新增 deprecated 警告，但暂不删除唯一黑盒测试意图。
6. 旧根脚本 `test_iterative_labeling.sh` 已移到 `backend-service/scripts/legacy/` 并标 deprecated，保留黑盒测试意图但不再占根目录。
7. 修正 `docs/cleanup-archive-index-2026-09-17.md` 中“misplaced 数据可删”的旧判断。

## 5. 仍可随时清理的本机缓存

这些目录不影响平台，可在关闭相关工具/测试后手动删除：

```powershell
Remove-Item -Recurse -Force .codegraph, .hypothesis, .pycache, .vscode
Remove-Item -Force .pids -ErrorAction SilentlyContinue
```

`.claude/` 只含 Junction；不使用 Claude 时也可删除。`.agents/`、`.cursor/`、`.kiro/`、整个 `_archive_2026-09-17/`、整个 `output/` 不要照此删除。
<!-- @AI_GENERATED: end -->
