# AutoResearch 能力扩展 — 设计方案

日期：2026-05-28

## 架构概览

```
                    ┌──────────────────────────┐
                    │  load_weather_weihai.csv  │  ← 预处理脚本合并
                    │  (负荷+天气, 小时级宽表)   │
                    └───────────┬──────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
     ┌────────────┐    ┌────────────┐    ┌────────────┐
     │auto_tune   │    │auto_tune   │    │auto_tune   │
     │_xgboost    │    │_lightgbm   │    │_catboost   │
     └────────────┘    └────────────┘    └────────────┘
              │                 │                  │
              ▼                 ▼                  ▼
     ┌────────────┐    ┌────────────┐    ┌────────────┐
     │xgboost     │    │lightgbm    │    │catboost    │
     │_forecast   │    │_forecast   │    │_forecast   │
     └────────────┘    └────────────┘    └────────────┘
                       │
                       ▼
              ┌────────────────┐
              │ensemble_forecast│
              └────────────────┘
```

## 改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `datasets/load_weather_weihai.csv` | 新建 | 预处理脚本输出 |
| `scripts/preprocess_weather.py` | 新建 | 一次性预处理脚本 |
| `services/operator_backends/auto_tune_lightgbm.py` | 新建 | LightGBM 贝叶斯调参 |
| `services/operator_backends/auto_tune_catboost.py` | 新建 | CatBoost 贝叶斯调参 |
| `data/workflows_enhanced/workflow-load-forecast-backtest-v3.json` | 新建 | V3 工作流模板 |
| `data/autoresearch_search_registries/load_forecast_v2.json` | 新建 | V2 注册表 |
| `data/functions.json` | 修改 | 注册 2 个新算子 + 天气 load_csv |

## 1. 预处理脚本

输入：`ens_avg_weihai.csv` + `load_true_weihai_260415.csv`
输出：`load_weather_weihai.csv`

步骤：
1. 负荷数据 pivot：`feature_name=load` → 宽表（record_time, load_value）
2. 负荷数据重采样：15min → 1h（取均值）
3. 天气数据已为小时级，直接使用
4. 按 timestamp=record_time 合并
5. 前向填充天气缺失值（最多 3 小时）
6. 输出列：`record_time, load, temperature, wind_speed, wind_direction, pressure, rainfall`

## 2. auto_tune_lightgbm 算子

克隆 `auto_tune_xgboost.py` 结构，替换：

- 搜索空间：`num_leaves`(15~255), `learning_rate`(0.01~0.3), `feature_fraction`(0.5~1.0), `min_data_in_leaf`(10~100), `lambda_l1`(0~10)
- 模型创建：`lgb.train()`
- 评估指标：RMSE（与 XGBoost 一致）
- 输入/输出接口：与 auto_tune_xgboost 完全一致

## 3. auto_tune_catboost 算子

克隆 `auto_tune_xgboost.py` 结构，替换：

- 搜索空间：`depth`(3~10), `learning_rate`(0.01~0.3), `l2_leaf_reg`(1~10), `border_count`(32~255), `random_strength`(0~10)
- 模型创建：`CatBoostRegressor().fit()`
- 评估指标：RMSE
- 输入/输出接口：与 auto_tune_xgboost 完全一致

## 4. XGBoost 超参范围放宽

在注册表中新增 XGBoost 专属参数：

| 参数 | 当前 | 放宽后 |
|------|------|--------|
| eta | 0.01~0.15 | 0.01~0.3 |
| max_depth | 3~8 | 3~12 |
| subsample | 未搜索 | 0.6~1.0 |
| colsample_bytree | 未搜索 | 0.6~1.0 |
| min_child_weight | 1~10 | 1~20 |

## 5. 注册表 V2 新增条目

model 层新增：
- `xgb_eta_high`: [0.05, 0.1, 0.15, 0.2, 0.3]
- `xgb_max_depth_high`: [6, 8, 10, 12]
- `xgb_subsample`: [0.6, 0.8, 1.0]
- `auto_tune_n_trials`: [20, 30, 50]（原 [3, 5, 8, 12, 20]）

feature 层新增：
- `weather_features.enabled`: boolean（是否启用天气特征）

## 6. 工作流 V3 变更

相比 V2：
1. `load_csv` 节点 file_path 改为 `datasets/load_weather_weihai.csv`
2. 新增 `auto_tune_lightgbm` 节点（连接在 train_test_split 和 lgb_forecast 之间）
3. 新增 `auto_tune_catboost` 节点（连接在 train_test_split 和 cb_forecast 之间）
4. 新增特征节点 `extract_time_features` 的配置中排除 weather 列的异常检测（防止温度被当成异常值去除）

## 7. functions.json 注册

新增 2 条 operator 注册：
```json
{
  "functionId": "auto_tune_lightgbm",
  "label": "LightGBM贝叶斯调参",
  "category": "模型训练",
  "inputs": ["train_features", "train_target"],
  "outputs": ["best_params", "model"]
}
```
（CatBoost 同理）

## 验证策略

1. `py_compile` 所有新/改 Python 文件
2. 预处理脚本单独运行，验证输出 CSV 的列和时间范围
3. 新算子单元测试：用 100 行合成数据跑调参，确认不报错
4. 重启后端，加载新工作流模板，跑 5 轮 smoke run
5. 比较 V2 baseline vs V3 baseline 的 MAPE
