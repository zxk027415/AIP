# 模型训练快速参考

## 🚀 快速开始

### 训练模型（新方式 - 推荐）

```javascript
// 1. 选择场站
currentStationId = "42ApNwtb"

// 2. 选择气象源（在数据展示页面）
selectedSources = ["EC_10D_WS", "ENS_AVG_WS"]

// 3. 选择特征组（在特征工程页面勾选）
selectedFeatureGroups = ["raw_meteorological", "time_features", "statistical_features"]

// 4. 设置训练参数
predictStartDate = "2026-01-01"
predictEndDate = "2026-01-31"
trainDays = 300

// 5. 点击"训练模型"按钮
// 系统自动：
// - 从数据库加载数据
// - 处理数据
// - 生成特征
// - 训练模型
// - 进行预测
```

## 📋 API 参考

### POST /api/model/train

**请求**：
```json
{
  "station_id": "42ApNwtb",
  "model_type": "random_forest",
  "params": {
    "n_estimators": 100,
    "max_depth": 10,
    "test_size": 0.2
  },
  "train_start_date": "2025-03-07",
  "train_end_date": "2025-12-31",
  "predict_start_date": "2026-01-01",
  "predict_end_date": "2026-01-31",
  "resolution": "1H",
  "sources": ["EC_10D_WS", "ENS_AVG_WS"],
  "feature_groups": ["raw_meteorological", "time_features"]
}
```

**响应**：
```json
{
  "status": "success",
  "model_id": "uuid",
  "model_type": "random_forest",
  "metrics": {
    "rmse": 0.5234,
    "mae": 0.4123,
    "r2": 0.8567
  },
  "predictions": [...],
  "actual": [...],
  "timestamps": [...],
  "train_size": 240,
  "test_size": 60
}
```

### POST /api/model/feature_importance

**请求**：
```json
{
  "model_id": "uuid",
  "top_n": 20
}
```

**响应**：
```json
{
  "status": "success",
  "importance": [
    {"feature": "EC_10D_WS", "importance": 0.25},
    {"feature": "ENS_AVG_WS", "importance": 0.18},
    ...
  ],
  "total_features": 20
}
```

## 🔧 参数说明

### 模型类型 (model_type)
- `linear_regression`: 线性回归
- `decision_tree`: 决策树
- `random_forest`: 随机森林（推荐）

### 模型参数 (params)
```javascript
{
  "test_size": 0.2,        // 验证集比例 (0.1-0.5)
  "n_estimators": 100,     // 树的数量 (10-500, 仅随机森林)
  "max_depth": 10          // 最大深度 (3-50, 决策树和随机森林)
}
```

### 时间分辨率 (resolution)
- `15T`: 15分钟
- `30T`: 30分钟
- `1H`: 1小时（推荐）
- `3H`: 3小时

### 特征组 (feature_groups)
- `raw_meteorological`: 原始气象要素
- `time_features`: 时间特征
- `statistical_features`: 统计特征
- `difference_features`: 差值特征
- `interaction_features`: 交互特征

## 📊 数据流程

```
用户输入
  ↓
计算训练范围
  ↓
从数据库加载数据 (训练期 + 预测期)
  ↓
处理数据 (重采样、分离气象源)
  ↓
生成特征 (根据feature_groups)
  ↓
训练模型 (训练集 80% + 验证集 20%)
  ↓
预测 (预测期数据)
  ↓
返回结果 (指标、预测值、特征重要性)
```

## ⚠️ 常见错误

### 1. "请先选择场站"
```javascript
// 解决：在顶部导航栏选择场站
document.getElementById('stationSelect').value = '42ApNwtb'
```

### 2. "请先选择至少一个气象源"
```javascript
// 解决：在数据展示页面选择气象源
selectedSources = ["EC_10D_WS", "ENS_AVG_WS"]
```

### 3. "请至少选择一个特征组"
```javascript
// 解决：在特征工程页面勾选特征组
document.querySelector('#fg_raw').checked = true
document.querySelector('#fg_time').checked = true
```

### 4. "训练数据点太少"
```javascript
// 解决：增加训练天数
trainDays = 300  // 至少30天，推荐300天
```

### 5. "数据文件不存在"
```javascript
// 解决：检查数据库中是否有该时间范围的数据
// 或调整日期范围
```

## 💡 最佳实践

### 1. 训练天数设置
- 最少：30天
- 推荐：300天（约10个月）
- 最多：730天（2年）

### 2. 验证集比例
- 小数据集：0.3 (30%)
- 中等数据集：0.2 (20%) ✅ 推荐
- 大数据集：0.1 (10%)

### 3. 气象源选择
- 至少选择2个气象源
- 推荐：EC_10D, ENS_AVG
- 最多：所有可用气象源

### 4. 特征组选择
- 基础：raw_meteorological + time_features
- 推荐：raw_meteorological + time_features + statistical_features ✅
- 高级：所有特征组

### 5. 模型选择
- 快速测试：linear_regression
- 一般使用：random_forest ✅ 推荐
- 高精度：random_forest (n_estimators=200, max_depth=15)

## 🎯 性能优化

### 减少训练时间
```javascript
// 1. 减少训练天数
trainDays = 100  // 而不是 300

// 2. 减少气象源数量
sources = ["EC_10D_WS"]  // 而不是所有气象源

// 3. 减少特征组
feature_groups = ["raw_meteorological"]  // 而不是所有特征组

// 4. 使用简单模型
model_type = "linear_regression"  // 而不是 random_forest
```

### 提高预测精度
```javascript
// 1. 增加训练天数
trainDays = 365  // 一年数据

// 2. 使用更多气象源
sources = ["EC_10D_WS", "ENS_AVG_WS", "DWD_WS", ...]

// 3. 使用更多特征组
feature_groups = ["raw_meteorological", "time_features", "statistical_features"]

// 4. 优化模型参数
params = {
    n_estimators: 200,  // 增加树的数量
    max_depth: 15,      // 增加深度
    test_size: 0.2
}
```

## 📝 日志查看

### 前端日志
```javascript
// 打开浏览器控制台 (F12)
// 查看训练过程日志
console.log('=== 开始训练模型 ===')
console.log('场站:', currentStationId)
console.log('训练数据范围:', trainStartStr, 'to', trainEndStr)
console.log('预测数据范围:', predictStartDate, 'to', predictEndDate)
```

### 后端日志
```python
# 查看服务器日志
# logs/wind_analysis.log

# 关键日志
logger.info('=== Model Training Request (Direct Load) ===')
logger.info(f'Station: {station_id}')
logger.info(f'Train date range: {train_start_date} to {train_end_date}')
logger.info(f'Loaded raw data shape: {raw_data.shape}')
logger.info(f'Generated feature matrix shape: {feature_matrix.shape}')
logger.info(f'Model trained - Train size: {train_size}, Validation size: {test_size}')
```

## 🔍 调试技巧

### 1. 检查数据加载
```python
# 在后端添加断点
raw_data = loader.load_station_data(...)
print(f"Loaded data shape: {raw_data.shape}")
print(f"Date range: {raw_data.index.min()} to {raw_data.index.max()}")
```

### 2. 检查特征生成
```python
feature_matrix = engineer.create_features(...)
print(f"Feature matrix shape: {feature_matrix.shape}")
print(f"Feature columns: {list(feature_matrix.columns)}")
```

### 3. 检查模型训练
```python
result = trainer.train_random_forest(...)
print(f"Training metrics: {result['metrics']}")
print(f"Train size: {len(trainer.y_train)}")
print(f"Test size: {len(trainer.y_test)}")
```

## 📞 支持

如有问题，请查看：
1. `MODEL_TRAINING_WORKFLOW.md` - 详细工作流程
2. `TRAINING_DIRECT_LOAD_SUMMARY.md` - 更新总结
3. 服务器日志：`logs/wind_analysis.log`
4. 浏览器控制台日志

---
更新日期：2026-02-06
