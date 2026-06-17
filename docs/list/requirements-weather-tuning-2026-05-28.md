# AutoResearch 能力扩展 — 需求文档

日期：2026-05-28
状态：设计中

## 目标

扩展 AutoResearch 的搜索空间，引入天气数据和全模型调参能力，突破当前 MAPE ~4.1% 的天花板。

## 成功标准

1. **天气数据接入**：工作流能读取包含温度、风速、风向、气压、降雨的合并数据集
2. **全模型调参**：LightGBM 和 CatBoost 各自有独立的贝叶斯超参优化节点
3. **搜索空间扩展**：注册表中新增天气特征开关、各模型超参范围
4. **MAPE 突破**：新 baseline（天气+全模型调参）的 MAPE < 3.8%（当前 4.1%）

## 范围

### 做
1. 预处理脚本：合并天气 CSV + 负荷 CSV 为一张宽表
2. 新增 `auto_tune_lightgbm` 算子
3. 新增 `auto_tune_catboost` 算子
4. 放宽 XGBoost 超参搜索范围（eta/depth/subsample 等）
5. 更新注册表：新增 model 层超参、feature 层天气特征开关
6. 更新工作流模板：加入天气数据加载和新调参节点
7. 更新 `functions.json`：注册新算子，前端可见

### 不做
- 不删除或修改 Ridge 预测节点（后续对比实验时再做）
- 不改回测引擎
- 不改前端 UI（新算子自动从 functions.json 加载）
- 不改 AutoResearch 主循环逻辑

## 约束
- 工作区很脏，不清理、不重置现有产物
- 后端当前在 8080 运行，修改 Python 代码需要重启才能生效
- 新算子需与现有 `auto_tune_xgboost` 保持相同的输入/输出接口
- 合并后的数据集需与原负荷数据保持相同的时间覆盖

## 数据
- 天气：`backend-service/datasets/ens_avg_weihai.csv`（19,128 行，小时级，2024-03~2026-05）
- 负荷：`backend-service/datasets/load_true_weihai_260415.csv`（25,438 行，15 分钟级，2025-07~2026-04）
- 重叠区间：287 天（2025-07-02 ~ 2026-04-15）
- 输出：`backend-service/datasets/load_weather_weihai.csv`（合并后的宽表）
