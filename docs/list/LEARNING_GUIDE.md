# AIP 工业AI算法平台 — 技术学习指南

> 基于项目实际代码，帮你搞懂"数据从哪来、到哪去、中间做了什么变换"

---

## 一、整体架构：一张图看懂全局

```
┌─────────────────────────────────────────────────────────┐
│                    用户浏览器 (React)                      │
│  点击 Execute → workflowEnhancedApi.executeWorkflow()    │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP POST
                       ▼
┌─────────────────────────────────────────────────────────┐
│              FastAPI 后端 (main.py)                       │
│  路由: /api/workflows/enhanced/{id}/execute              │
│  文件: api/workflows_enhanced.py                         │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│           流水线执行引擎 (_execute_pipeline_sync)          │
│                                                          │
│  1. 拓扑排序 → 确定算子执行顺序                            │
│  2. 逐个执行算子:                                         │
│     ├─ 收集上游输出作为当前算子输入                         │
│     ├─ 注入全局配置 (时间基准、预测场景等)                  │
│     ├─ OperatorRouter.execute(算子ID, 参数, 输入)         │
│     ├─ 校验输出是否符合 DataContract                      │
│     └─ 存储结果，传递给下游                                │
│  3. 返回所有节点结果                                      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│          算子后端 (services/operator_backends/)            │
│                                                          │
│  每个 .py 文件 = 一个算子，只需要:                         │
│    OPERATOR_ID = "load_csv"                              │
│    def execute(params, inputs) -> dict                   │
│                                                          │
│  OperatorRouter 启动时自动扫描注册所有算子                  │
└─────────────────────────────────────────────────────────┘
```

**核心理解**: 整个平台就是一个"算子流水线执行器"。前端画布上的每个节点对应一个 Python 函数，节点之间的连线决定数据流向，后端按拓扑排序依次执行。

---

## 二、数据流详解：以负荷预测训练流水线为例

这是你项目中最核心的流水线，包含 17 个算子。下面是完整的数据流转过程：

### 阶段 1: 数据加载与清洗

```
CSV文件 (load_true_weihai_260415.csv)
  │
  ▼
[load_csv] ──→ DataFrame(record_time, load, parent_id, child_id, ...)
  │              输出: {"data": DataFrame}
  ▼
[row_filter] ──→ 按 parent_id/child_id 过滤出目标测量点
  │              输入: {"data": DataFrame}
  │              输出: {"data": 过滤后的 DataFrame}
  ▼
[resample_timeseries] ──→ 重采样到 15 分钟粒度，补全缺失时间戳
  │              输入: {"data": DataFrame}
  │              参数: frequency="15min", method="mean"
  │              输出: {"data": 连续时间索引的 DataFrame}
  ▼
[detect_outliers] ──→ Z-Score 检测异常值，标记为 NaN
  │              输入: {"data": DataFrame}
  │              参数: method="zscore", threshold=6.0
  │              输出: {"data": DataFrame, "outlier_indices": [...]}
  ▼
[handle_missing] ──→ 线性插值填充 NaN
                 输入: {"data": DataFrame}
                 参数: method="linear"
                 输出: {"data": 无 NaN 的 DataFrame}
```

**关键理解**: 每个算子的输出是一个 dict，key 是端口名（通常是 "data"），value 是 DataFrame。下游算子通过连线自动获取上游的输出。

### 阶段 2: 特征工程

```
[清洗后的 DataFrame]
  │
  ├──→ [extract_time_features] ──→ 添加 hour, dayofweek, month 等列
  │
  ├──→ [holiday_features] ──→ 添加 is_holiday, holiday_name 列
  │
  ├──→ [workday_features] ──→ 添加 is_workday 列
  │
  ├──→ [rolling_statistics] ──→ 添加 load_mean_24, load_std_24 等滚动统计列
  │         参数: window_sizes=[24, 48, 96, 168]
  │
  └──→ [create_lag_features] ──→ 添加 load_lag_1, load_lag_24, load_lag_168 列
              参数: lags=[1, 24, 168]
```

**关键理解**: 特征工程算子都是在原始 DataFrame 上"加列"。输入一个 DataFrame，输出一个列更多的 DataFrame。这些新列就是模型的输入特征。

### 阶段 3: 数据准备

```
[特征丰富的 DataFrame]
  │
  ▼
[sliding_window] ──→ 按 96 点窗口切片，生成 X (特征矩阵) 和 y (目标向量)
  │         参数: window_size=96, target_column="load"
  │         输出: {"X": ndarray, "y": ndarray}
  ▼
[train_test_split_ts] ──→ 按时间顺序 80/10/10 切分
  │         输出: {"train_features": DataFrame,
  │                "train_target": ndarray,
  │                "val_features": DataFrame,
  │                "val_target": ndarray,
  │                "test_features": DataFrame,
  │                "test_target": ndarray}
  ▼
[multi_step_forecast] ──→ 配置预测 96 步 (未来 24 小时)
              参数: forecast_steps=96, strategy="recursive"
              输出: 传递配置给下游模型
```

**关键理解**: `sliding_window` 是从时序数据到机器学习输入的关键转换。它把一维时间序列变成了二维特征矩阵（每行是一个窗口的特征，标签是窗口后的值）。

### 阶段 4: 模型训练与评估

```
[切分好的训练/测试数据]
  │
  ├──→ [auto_tune_xgboost] ──→ 贝叶斯优化搜索最优超参数
  │         参数: n_trials=30, cv_folds=5
  │         输出: {"best_params": {...}, "best_score": float}
  │
  ▼
[xgboost_forecast] ──→ 用最优参数训练 XGBoost，返回预测结果
  │         参数: mode="train", n_estimators=200
  │         核心逻辑:
  │           1. 构建 DMatrix (XGBoost 专用数据格式)
  │           2. 设置样本权重 (近期数据权重更高)
  │           3. xgb.train() 训练模型
  │           4. model.predict() 生成预测
  │           5. 存储模型到内存 (_MODEL_STORE)
  │         输出: {"predictions": ndarray,
  │                "model_id": "uuid-xxx",
  │                "train_metrics": {...}}
  │
  ├──→ [smape_score] ──→ 计算 SMAPE 对称百分比误差
  │         输出: {"smape": float}
  │
  └──→ [mse_rmse_mae] ──→ 计算 MSE, RMSE, MAE
              输出: {"mse": float, "rmse": float, "mae": float}
```

**关键理解**: XGBoost 训练后模型存在内存里（`_MODEL_STORE[model_id]`），推理流水线通过 `model_id` 加载模型执行预测。

---

## 三、核心框架详解

### 3.1 OperatorRouter — 算子路由器

```python
# 文件: services/operator_execution/router.py

class OperatorRouter:
    def __init__(self):
        self._registry = {}  # {"load_csv": execute_fn, "xgboost_forecast": execute_fn, ...}

    def auto_discover(self, backends_dir):
        """启动时扫描 operator_backends/ 目录，自动注册所有算子"""
        for filename in os.listdir(backends_dir):
            module = importlib.import_module(f"operator_backends.{filename}")
            op_id = module.OPERATOR_ID      # 例如 "load_csv"
            execute_fn = module.execute      # 例如 load_csv.execute
            self._registry[op_id] = execute_fn

    def execute(self, operator_id, params, inputs):
        """根据算子ID找到对应函数并执行"""
        execute_fn = self._registry[operator_id]
        return execute_fn(params, inputs)
```

**你需要理解的**: 这就是一个"函数注册表"。每个算子是一个独立的 Python 文件，只要导出 `OPERATOR_ID` 和 `execute()` 就能被自动发现和调用。这种设计叫"插件架构"，新增算子不需要改任何已有代码。

### 3.2 算子接口规范

```python
# 文件: services/operator_backends/base.py

# 每个算子文件必须有:
OPERATOR_ID: str = "your_operator_id"

def execute(params: dict, inputs: dict) -> dict:
    """
    params: 算子参数 (来自节点配置 + 全局配置)
            例如 {"file_path": "data.csv", "delimiter": ","}

    inputs: 上游算子的输出 (通过连线传递)
            例如 {"data": DataFrame}

    returns: 执行结果 (传递给下游算子)
             例如 {"data": 处理后的 DataFrame}
    """
```

**你需要理解的**: 所有算子的接口完全统一 — 输入是 `(params, inputs)`，输出是 `dict`。这就是为什么它们能自由组合。

### 3.3 DataContract — 数据契约

```python
# 文件: services/operator_execution/data_contracts.py

LOAD_FORECAST_CONTRACTS = {
    "load_csv_output": DataContract(
        required_columns=["record_time", "load"],
        column_types={"record_time": "datetime64", "load": "float64"},
        constraints=["time_ordered", "no_duplicates"],
    ),
    "handle_missing_output": DataContract(
        required_columns=["record_time", "load"],
        constraints=["no_nan", "time_ordered"],  # 必须无 NaN
    ),
}
```

**你需要理解的**: DataContract 定义了算子之间传递数据的"格式规范"。比如 `handle_missing` 的输出必须无 NaN，如果有 NaN 就会校验失败。这保证了流水线的数据质量。

### 3.4 流水线执行引擎

```python
# 文件: api/workflows_enhanced.py → _execute_pipeline_sync()

def _execute_pipeline_sync(workflow):
    # 1. 拓扑排序: 确定执行顺序 (Kahn 算法)
    execution_order = _topological_sort_nodes(nodes, edges)
    # 例如: [load_csv, row_filter, resample, ..., xgboost, smape]

    # 2. 逐个执行
    node_outputs = {}
    for node_id in execution_order:
        node = find_node(node_id)

        # 收集上游输出作为输入
        inputs = _collect_upstream_inputs(node_id, edges, node_outputs)

        # 构建参数 (节点配置 + 全局配置)
        params = merge(node.data.config, global_config)

        # 执行算子
        operator_id = node.data.config.functionId  # 例如 "load_csv"
        result = op_router.execute(operator_id, params, inputs)

        # 存储输出，供下游使用
        node_outputs[node_id] = result

    return node_outputs
```

**你需要理解的**: 这是整个平台最核心的 50 行代码。拓扑排序保证了"先执行上游，再执行下游"。每个节点执行完后，输出存到 `node_outputs` 里，下游节点通过连线关系从中取数据。

---

## 四、前后端通信：接口是怎么连起来的

### 4.1 前端发起请求

```typescript
// 文件: frontend/src/services/workflowEnhancedApi.ts

// 用户点击 "Execute" 按钮
const result = await axios.post(
  `/api/workflows/enhanced/${workflowId}/execute`,
  { execution_data: { global_config: {...} } }
);
```

### 4.2 后端处理请求

```python
# 文件: backend/api/workflows_enhanced.py

@router.post("/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, request: ExecuteRequest):
    workflow = load_workflow_from_file(workflow_id)  # 从 JSON 文件加载
    result = _execute_pipeline_sync(workflow, request.execution_data)
    return result
```

### 4.3 异步执行 + 轮询

```
前端                              后端
  │                                │
  ├─ POST /execute-async ────────→ │ 返回 execution_id
  │                                │ 启动后台线程执行
  │                                │
  ├─ GET /execution-status ──────→ │ 返回当前进度 (哪个节点在跑)
  ├─ GET /execution-status ──────→ │ 返回当前进度
  ├─ GET /execution-status ──────→ │ 返回完成结果
  │                                │
  └─ 显示结果                       │
```

**你需要理解的**: 短流水线用同步执行（等着返回），长流水线用异步执行（先返回 ID，前端轮询进度）。这是 Web 开发中处理耗时任务的标准模式。

---

## 五、你需要掌握的核心知识点

### 必须掌握 (能说清楚原理)

| 知识点 | 在项目中的位置 | 为什么重要 |
|--------|--------------|-----------|
| **XGBoost 时序预测** | `operator_backends/xgboost_forecast.py` | 你的核心算法，面试必问 |
| **特征工程** (滞后、滚动、时间特征) | `operator_backends/create_lag_features.py` 等 | 时序预测的关键，决定模型精度 |
| **滑动窗口切分** | `operator_backends/sliding_window.py` | 时序→监督学习的桥梁 |
| **算子接口设计** (params/inputs/outputs) | `operator_backends/base.py` | 理解插件架构，以后写 Agent Tool 同理 |
| **拓扑排序** | `_topological_sort_nodes()` | DAG 执行的基础，LangGraph 也用这个 |
| **数据契约** | `data_contracts.py` | 保证数据质量，工程化的关键 |

### 深入研究 (提升竞争力)

| 知识点 | 学习方向 | 和大模型的关系 |
|--------|---------|--------------|
| **算子 → Function Calling Tool** | 把 `execute(params, inputs)` 包装成 OpenAI Tool Schema | 直接对接大模型 Agent |
| **工作流 → LangGraph StateGraph** | 把拓扑排序执行改成 LangGraph 的状态机 | Agent 编排的核心 |
| **DataContract → JSON Schema** | 把数据契约转成 Tool 的参数描述 | 让大模型知道每个 Tool 需要什么输入 |
| **贝叶斯超参优化** | `auto_tune_xgboost.py` | AutoML 的基础 |
| **回测框架** | `_execute_pipeline_sync` 的 backtest 模式 | 模型评估的工程化实践 |

---

## 六、一句话总结每个核心文件

```
main.py                          → FastAPI 入口，注册所有路由
api/workflows_enhanced.py        → 工作流 CRUD + 执行的 API 层
services/operator_execution/
  ├── router.py                  → 算子注册表，自动发现 + 路由执行
  ├── schema_validator.py        → 数据契约校验器
  ├── data_adapter.py            → 算子间数据格式适配
  ├── global_config_injector.py  → 全局配置注入 (时间基准等)
  └── data_contracts.py          → 负荷预测流水线的数据契约定义
services/operator_backends/
  ├── base.py                    → 算子接口规范 (OPERATOR_ID + execute)
  ├── load_csv.py                → 数据加载算子
  ├── detect_outliers.py         → 异常值检测算子
  ├── handle_missing.py          → 缺失值处理算子
  ├── extract_time_features.py   → 时间特征提取算子
  ├── sliding_window.py          → 滑动窗口切分算子
  ├── train_test_split_ts.py     → 时序数据切分算子
  ├── xgboost_forecast.py        → XGBoost 训练/预测算子
  ├── auto_tune_xgboost.py       → 贝叶斯超参优化算子
  ├── smape_score.py             → SMAPE 评估算子
  └── mse_rmse_mae.py            → MSE/RMSE/MAE 评估算子
```

---

## 七、从当前项目到大模型 Agent 的桥梁

```
现在你做的                          未来接入大模型后
─────────────                      ──────────────
算子 execute(params, inputs)   →   OpenAI Function Calling Tool
DataContract                   →   Tool 的 parameters JSON Schema
OperatorRouter                 →   Agent 的 ToolRouter
拓扑排序执行                    →   LangGraph StateGraph
工作流 JSON                    →   Agent 的 Plan (执行计划)
用户在画布上拖拽编排             →   用户用自然语言描述需求，Agent 自动编排
```

你现在写的每一个算子，未来都会变成大模型的"手"。
