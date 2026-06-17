# AutoResearch 能力扩展 — 交付文档

日期：2026-05-28
状态：代码修复完成，待后端重启后做 smoke run / 端到端验证

## 结论

完成了天气数据接入和全模型调参能力扩展。新增 2 个算子、V2 注册表、V3 工作流模板、合并数据集。

2026-05-28 review 后已补修：

- V3 工作流文件内部 `id` 已改为 `workflow-load-forecast-backtest-v3`，避免被前端/API 识别成 V2。
- LightGBM/CatBoost forecast 已优先使用上游 `auto_tune_lightgbm` / `auto_tune_catboost` 输出的预调模型和 `oof_rmse`。
- V3 工作流中新调参节点的描述已从 XGBoost 修正为对应模型。

## 改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/preprocess_weather.py` | 新建 | 天气+负荷合并脚本（一次性） |
| `datasets/load_weather_weihai.csv` | 新建 | 合并后数据集（6,349行, 7列） |
| `services/operator_backends/auto_tune_lightgbm.py` | 新建 | LightGBM 贝叶斯调参算子 |
| `services/operator_backends/auto_tune_catboost.py` | 新建 | CatBoost 贝叶斯调参算子 |
| `data/autoresearch_search_registries/load_forecast_v2.json` | 新建 | V2 注册表（23 参数） |
| `data/workflows_enhanced/workflow-load-forecast-backtest-v3.json` | 新建 | V3 工作流（26 节点, 32 边） |
| `data/functions.json` | 修改 | +2 算子注册 |
| `api/workflows_enhanced.py` | 修改 | A1/A3/B1/B2 修复（6 处） |
| `services/autoresearch_glm_question_generator.py` | 修改 | A4 NoneType 保护 |
| `services/operator_backends/lightgbm_forecast.py` | 修改 | 使用上游 LightGBM 调参结果 |
| `services/operator_backends/catboost_forecast.py` | 修改 | 使用上游 CatBoost 调参结果 |

## 验证结果

- ✅ py_compile 全部文件通过
- ✅ 14 个 focused tests 通过
- ✅ 注册表 V2 JSON 合法（4 层 23 参数）
- ✅ 工作流 V3 JSON 合法（26 节点 32 边）
- ✅ functions.json 注册成功（811 个函数）
- ✅ 合并数据集 6,349 行 0 缺失值
- ✅ review 抽查已确认 V3 文件路径、内部 ID、启动示例 ID 三者一致

## 没验证的

- 新算子的端到端运行（需要重启后端后在真实工作流中测试）
- V3 工作流 1 轮 smoke run（确认天气列加载、LightGBM/CatBoost 调参、预测、评估全链路）
- LightGBM/CatBoost 调参对 MAPE 的实际改善（需要跑 AutoResearch run）
- 天气数据对 MAPE 的实际改善（同上）

## 重启要求

重启前先确认没有正在执行的 AutoResearch run。不要在长 run 进行中直接 kill worker。

推荐用两个终端分别启动后端和 worker。`uvicorn` 是前台进程，不能和 worker 写在同一个顺序脚本里。

```bash
# 终端 1：后端
cd backend-service
conda activate cp_web
source scripts/load_glm_env.sh
uvicorn main:app --port 8080
```

```bash
# 终端 2：worker（跑 AutoResearch 时才需要）
cd backend-service
conda activate cp_web
source scripts/load_glm_env.sh
python worker_autoresearch.py --loop
```

如果已有旧后端或旧 worker，先用只读命令确认进程，再按当前 run 状态决定是否停止：

```bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
pgrep -afil "worker_autoresearch|uvicorn"
```

如果存在 active run，应先走 AutoResearch cancel 接口，让 run 和 compare 子任务落状态；只有确认不需要保留运行状态时再停进程。

## 下一步：启动 50 轮测试

使用 V3 工作流 + V2 注册表 + 默认配置启动 AutoResearch：

```json
{
  "baseline_workflow_id": "workflow-load-forecast-backtest-v3",
  "windows": [
    {
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD"
    }
  ],
  "search_space": {},
  "evaluation_contract": {},
  "compare_config": {
    "force_activate": ["feature", "model", "data"],
    "auto_full_automation": true,
    "memory_top_k": 5
  },
  "registry_id": "load_forecast_v2",
  "max_iterations": 50
}
```

建议顺序：

1. 先跑 1 轮 smoke run，确认 V3 工作流端到端可执行。
2. 再跑 3-5 轮小样本，确认非 parameter 方向能被激活且没有明显失败。
3. 最后再启动 50 轮正式验收。
