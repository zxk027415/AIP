<!-- @AI_GENERATED -->
# AIP 后端服务

FastAPI + Python 3.10 后端。**正式启动入口是仓库根 `aip.ps1`，不是本目录的旧 `start-kiro.bat`。**

## 启动

```powershell
# 在仓库根
.\aip.ps1 dev          # 启动缺失服务；健康的 8081/3001 会被复用
.\aip.ps1 restart-dev  # 安全重启 AIP dev 服务并加载最新代码
.\aip.ps1 experiment   # 后端 8080 + 前端 3001 + AutoResearch worker
.\aip.ps1 stop         # 只停止 AIP 端口与 worker
```

单独启动后端（调试时）：

```powershell
cd backend-service
conda run --no-capture-output -n cp_web uvicorn main:app --host 0.0.0.0 --reload --port 8081
```

- 健康检查：`http://localhost:8081/api/health`
- Swagger：`http://localhost:8081/docs`
- 本地环境变量：`.env.local`（已忽略，不提交密钥）

## 真实目录结构

```text
backend-service/
├── main.py                    # ASGI 入口；注册路由、初始化 DB、装配领域桥并启动 5 条调度管线
├── api/                       # HTTP 路由层（参数校验、错误映射、调用 service）
├── services/                  # 业务逻辑层
│   ├── operator_backends/     # 169 个算子后端
│   ├── operator_execution/    # 算子执行、数据适配、global_config 注入
│   ├── pv_projects/           # 项目工作台业务壳
│   ├── slot_datasets/         # 快照、喂数、回放、观测台账
│   ├── slot_governance/       # 候选、复验、Promote、生产 registry
│   ├── scheduler/             # APScheduler 与业务任务
│   ├── iterative_labeling/    # 光伏标注/审核/累计训练
│   └── reference_rolling_backtest/ # 标准滚动回测评分器
├── models/                    # Pydantic / SQLAlchemy 模型
├── data/                      # 配置、registry、模型、快照和运行资产（见 data/README.md）
├── tests/                     # pytest 测试
├── scripts/                   # 迁移、E2E、审计与构建脚本（见 scripts/README.md）
├── alembic/                   # 数据库迁移
├── config/                    # PV/TSC 等配置
├── worker_autoresearch.py     # AutoResearch worker 正式入口
├── database.py                # SQLAlchemy 引擎 / Session
├── requirements.txt           # 主依赖
└── pytest.ini
```

## 根目录中不能误删的负荷预测模块

这些文件看似是旧专项代码，但正式 API 仍直接 import：

- `data_process.py` — 时序补齐、异常检测和清洗。
- `db_data_fetch.py` — 离线 CSV 取数。
- `forecast_utils.py` — 负荷预测公共工具。
- `add_features.py` — `features/engine.py` 仍复用的特征函数。
- `features/`、`models_pkg/`、`common/`、`processing/` — 负荷预测内嵌副本。

`debug_pipeline.py`、`test_operator_backtest.py`、`test_operator_backtest_weather.py` 是手工诊断/对照 runner，不被 pytest 自动收集（`pytest.ini` 只收 `tests/`），但保留了负荷预测口径与防穿越说明，交接阶段保留。

## 启动副作用

导入 `main.py` 会注册全部 API；真正启动时 `startup_event()` 还会：

1. 初始化 SQLite/数据库连通性。
2. 把中断的 AutoResearch run/job 收敛状态。
3. 初始化 DBAdapter、仓库和 mock feeder。
4. 注册并启动 `load_forecast`、`pv_fault`、`pv_day`、`pv_point`、`pv_tsc` 五条调度管线。
5. 装配项目候选到 PV 模型登记的领域桥。

因此不要把 `import main` 当作完全无副作用的普通库导入，也不要在共享数据库环境随意启动多份后端。

## 测试

```powershell
cd backend-service
$env:PYTHONPATH="."
python -m pytest tests/pv_projects tests/test_path_overview.py -q --no-header
python -m py_compile main.py scripts/pv_project_full_chain_e2e.py
```

全量 `pytest` 不一定是快速干净信号；优先跑改动范围附近的测试。光伏完整链路：

```powershell
python scripts/pv_project_full_chain_e2e.py --slot pv_day --days 2 --use-real-model
```

该 E2E 即使隔离项目存储，第 9 步仍可能写真实 `data/slot_datasets/<slot>/`；不想改变回放进度加 `--skip-feed`。

## 旧入口

- `run.py` — 有效的 uvicorn CLI 包装，保留兼容。
- `create_db.py` — 手工初始化数据库，保留维护用途。
- `start-kiro.bat` — 使用旧环境名，**deprecated**；不要作为交接推荐入口。

更完整架构、三块业务与页面操作见 `../docs/handoff_2026-09-17.md`。
<!-- @AI_GENERATED: end -->
