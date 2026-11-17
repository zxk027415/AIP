<!-- @AI_GENERATED -->
# AIP 工业 AI 算法平台

这是一个 React + FastAPI 的工业 AI 全栈平台，当前重点业务是**负荷预测**、**光伏故障诊断三路径**与 **AutoResearch**。

## 第一次接手先看什么

1. `docs/handoff_2026-09-17.md` — 当前最完整的离职交接：代码架构、三块业务、页面操作、风险与验证命令。
2. `AGENTS.md` — 仓库认知、AutoResearch 演进史与协作约束。
3. `docs/README.md` — 153 份可读/可审计文档的分类索引，区分现状、设计、验收和历史资料。
4. `docs/root-directory-inventory-2026-09-18.md` — 根目录每个隐藏目录/文件的保留、归档、删除判断。

## 一键启动（Windows）

```powershell
.\aip.ps1 dev          # 启动缺失服务；已有健康 AIP 服务则复用
.\aip.ps1 restart-dev  # 安全重启 8081/3001，加载最新代码
.\aip.ps1 experiment   # 后端 8080 + 前端 3001 + AutoResearch worker
.\aip.ps1 status       # 查看 AIP 端口所有者和 worker
.\aip.ps1 stop         # 只停止 AIP 服务，不误杀其它 Python/Node
```

> 重复执行 `dev` 不会再启动第二套服务。若现有后端不是 reload 模式，脚本会提示使用 `restart-dev`。

环境：conda `cp_web`、Node.js 18+。本地密钥放 `.aip.local.env` 或 `backend-service/.env.local`，两者已被 Git 忽略。

## 仓库地图

- `backend-service/` — FastAPI 后端。`main.py` 是 ASGI 入口；`api/` 是路由；`services/` 是业务逻辑；`data/` 里既有业务 registry 也有运行资产，不能整目录清理。
- `frontend-sevice/` — React 18 + TypeScript + Vite 前端。目录名就是 `sevice`，不要改名；`src/App.tsx` 是路由总表。
- `fault-diag-algo-release-3.1/` — EnOS/AI Suite 光伏故障诊断旧发布包与平台仍在使用的样例/合并标注数据。保留在仓库根以兼容现有相对路径。
- `local_project/` — 负荷预测离线实验工程；其中 `operation_skill/` 是独立运营闭环 Skill。
- `docs/` — 现状、规格、验收和历史材料。以 `docs/README.md` 的真源优先级阅读。
- `aip.ps1` — Windows 唯一推荐启动入口。

## 最小验证

```powershell
cd backend-service
$env:PYTHONPATH="."
python -m pytest tests/pv_projects tests/test_path_overview.py -q --no-header

cd ..\frontend-sevice
npx tsc --noEmit
npm run build
```

不要把“命令退出 0”当成业务验收；光伏完整链路还应跑 `backend-service/scripts/pv_project_full_chain_e2e.py`，具体参数见交接文档。
<!-- @AI_GENERATED: end -->
