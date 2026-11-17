<!-- @AI_GENERATED -->
# `local_project/` 离线专项工程

这里放**不直接由 FastAPI 进程 import 的离线/专项工程**。当前只保留一个正式子工程：

- `local_project/load_forecast_refactored/` — 负荷预测离线实验工程，含统一 YAML 回测、威海专项回测、实验数据/输出，以及唯一的 `operation_skill`。

光伏旧发布包不放在这里。它必须保留在仓库根 `fault-diag-algo-release-3.1/`，因为前端默认值、工作流 JSON、路径解析器、历史审核记录和真实数据测试都使用仓库根相对路径。

## `load_forecast_refactored/` 目录

- `run.py` — YAML 驱动的统一离线回测入口；当前 pandas 2.3.3 下会因 8 处 `closed='left'` 失败，详见交接文档第 1.6 节。
- `configs/` — 客户级配置 schema 与 AESC/蒙西 YAML。
- `data/`、`datasets/` — 园区与威海真实负荷数据，按业务敏感数据交接。
- `data_fetch/` — EAP Dataset、MySQL、本地 CSV 三类取数。
- `features/` — 六类预测场景特征工程。
- `models_pkg/` — XGBoost 训练、贝叶斯调参与模型包装；`KFold(shuffle=True)` 存在时序穿越风险。
- `common/` — 场景常量与节假日规则。
- `processing/`、`evaluation/` — 兼容门面；`evaluation/metrics.py` 当前 import 即失败。
- `output/` — 历史 CSV/PNG/pickle 产物，可外部归档，不是源码真源。
- `operation_skill/` — 唯一 canonical 运营闭环 Skill，入口见下节。

## `operation_skill` 使用

```powershell
cd local_project\load_forecast_refactored\operation_skill
conda run -n cp_web python scripts/check_environment.py
conda run -n cp_web python scripts/run_collect.py --target-day 2026-05-24
# Agent/人工在本次 artifacts/<run>/ 写 rca_decision.json
conda run -n cp_web python scripts/run_resume.py
```

三阶段：collect（采证与候选策略实跑）→ reasoning（Agent 写 RCA 决策）→ resume（执行恢复、验证、CoE 和 HTML 报告）。

⚠️ 当前 `artifacts/_active_run.json` 仍指向旧机器绝对路径；必须先重跑 collect。`fetch_asset_data.py` 还有明文默认数据库凭据，使用前应移除默认值并轮换凭据。

## 与 `backend-service/` 的关系

负荷预测离线工程与后端内嵌 `common/features/models_pkg/processing/evaluation` 是**复制件，不是共享包**。既有 MD5 比对：13 个 Python 文件中 11 个完全相同；`features/engine.py` 与 `models_pkg/trainer.py` 仅 import 名不同（离线 `utils`，后端 `forecast_utils`）。修改任何一侧都不会自动同步另一侧。

## 2026-09-17 去重

原来还存在 `local_project/operation_skill/` 第二份副本。逐文件路径与 SHA-256 对比：41 个文件全部相同，已移入 `_archive_2026-09-17/duplicate-operation-skill/`；正式真源只保留内嵌副本。归档被 Git 忽略，确认不需恢复后可删除。
<!-- @AI_GENERATED: end -->
