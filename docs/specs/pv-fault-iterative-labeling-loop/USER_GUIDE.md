# 光伏故障人机协同迭代标注系统 - 用户操作指南

## 快速开始

### 1. 启动系统

```bash
cd /Users/zxk/Desktop/project/AIP
bash start-dev.sh
```

这会自动启动：
- 后端服务（端口 8080，已加载 GLM 环境变量）
- 前端应用（端口 5173）

访问地址：`http://localhost:5173`

### 2. 第一次迭代

#### Step 1: 准备初始数据集

确保你有一个**带真值标签**的 CSV 文件，包含：
- 设备标识列（如 `site_id`, `device_id`）
- 时序特征列（电流、电压等）
- 真值标签列（如 `fault_label`）

#### Step 2: 创建迭代闭环

**API 调用**:

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops \
  -H "Content-Type: application/json" \
  -d '{
    "slot": "default"
  }'
```

**响应示例**:

```json
{
  "loopId": "loop-001",
  "iterationRound": 1,
  "stage": null
}
```

记录 `loopId`，后续步骤需要使用。

#### Step 3: 训练模型

**API 调用**:

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops/loop-001/train \
  -H "Content-Type: application/json" \
  -d '{
    "datasetVersion": "dataset-v1",
    "modelParams": {
      "testRatio": 0.2,
      "nRepeats": 3,
      "randomState": 42,
      "k": 5
    }
  }'
```

**响应示例**:

```json
{
  "modelRef": "model-20260108-001",
  "accuracyRecord": {
    "macroF1Mean": 0.85,
    "macroF1Std": 0.02,
    "macroPrecisionMean": 0.87,
    "macroRecallMean": 0.83
  },
  "labelSpaceSnapshot": {
    "labelSpaceVersion": "ls-v1",
    "labelIds": [1, 2, 3, 4]
  }
}
```

记录 `modelRef`，用于下一步预测。

#### Step 4: 预测无标签数据

**API 调用**:

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops/loop-001/predict \
  -H "Content-Type: application/json" \
  -d '{
    "modelRef": "model-20260108-001",
    "unlabeledDatasetVersion": "dataset-unlabeled-v1"
  }'
```

**响应示例**:

```json
{
  "predictionBatchId": "pred-batch-001",
  "unitCount": 150
}
```

记录 `predictionBatchId`，用于创建审核会话。

#### Step 5: 创建审核会话

**API 调用**:

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/review-sessions \
  -H "Content-Type: application/json" \
  -d '{
    "loopId": "loop-001",
    "predictionBatchId": "pred-batch-001",
    "enableLlm": true
  }'
```

**响应示例**:

```json
{
  "reviewId": "review-001",
  "totalCount": 150
}
```

#### Step 6: 人工审核（前端页面）

在浏览器中访问：

```
http://localhost:5173/iterative-labeling/review/review-001
```

你会看到审核页面，包含：

##### 页面布局

```
┌─────────────────────────────────────────────────────────┐
│  迭代标注审核 - Review Session: review-001             │
├─────────────────────────────────────────────────────────┤
│  进度: 0 / 150 (0%)                                     │
│                                                         │
│  三方精度对比                                           │
│  ┌─────────────┬─────────────┬─────────────┐          │
│  │ 分类器精度  │ LLM精度     │ 人工基准    │          │
│  │ 0.00%       │ 0.00%       │ 100.00%     │          │
│  └─────────────┴─────────────┴─────────────┘          │
│                                                         │
│  当前审核单元                                           │
│  ┌───────────────────────────────────────────────┐    │
│  │ Unit Key: site-001_dev-123_window-1           │    │
│  │                                                 │    │
│  │ 分类器预测: 逆变器故障 (置信度: 0.85) ⚠️      │    │
│  │ LLM建议:    组串故障 (理由: 电流曲线异常...)   │    │
│  │                                                 │    │
│  │ 动作:                                           │    │
│  │ [确认分类器] [修正] [新标签] [跳过]            │    │
│  └───────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

##### 四类审核动作

1. **确认分类器** (`confirm`)
   - 点击后：接受分类器预测作为真值
   - 使用场景：分类器预测正确

2. **修正** (`correct`)
   - 点击后：弹出标签列表，选择正确标签
   - 使用场景：分类器预测错误，但正确标签在列表中

3. **新标签** (`new_label`)
   - 点击后：输入新标签名称（如 "组串开路"）
   - 使用场景：发现新的故障类型，当前列表没有

4. **跳过** (`skip`)
   - 点击后：标记为 pending，不写入真值
   - 使用场景：信息不足，无法判断

##### 不一致高亮

当分类器预测和 LLM 建议**不一致**时，会显示 ⚠️ 警告图标，提示人工仔细审查。

##### 实时精度更新

每提交一条裁决，三方精度面板会实时更新：

- **分类器精度**: 分类器预测命中人工裁决的比例
- **LLM精度**: LLM 建议命中人工裁决的比例（仅在有 LLM 建议的单元上计算）
- **人工基准**: 已审核单元的 100% 一致口径

#### Step 7: 回流新数据集

审核完成后（或部分完成），执行回流：

**API 调用**:

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops/loop-001/backfill \
  -H "Content-Type: application/json" \
  -d '{
    "reviewId": "review-001",
    "mergeBase": true
  }'
```

**响应示例**:

```json
{
  "datasetVersion": "dataset-v2",
  "unitCount": 120
}
```

注意：
- `unitCount` 排除了 `skip` 单元
- `mergeBase=true` 会与基线数据集累积合并

#### Step 8: 下一轮训练

使用回流后的新数据集版本，重复 Step 3-7：

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops/loop-001/train \
  -H "Content-Type: application/json" \
  -d '{
    "datasetVersion": "dataset-v2",
    "modelParams": {
      "testRatio": 0.2,
      "nRepeats": 3,
      "randomState": 42,
      "k": 5
    }
  }'
```

---

## 高级功能

### 1. 查看迭代历史

**API 调用**:

```bash
curl http://localhost:8080/api/iterative-labeling/iterations?slot=default
```

**响应示例**:

```json
{
  "iterations": [
    {
      "iterationId": "iter-001",
      "iterationRound": 1,
      "datasetVersion": "dataset-v1",
      "modelVersion": "model-20260108-001",
      "accuracyRecord": {
        "macroF1Mean": 0.85
      },
      "labelSpaceVersion": "ls-v1",
      "labelCount": 4,
      "createdAt": "2026-01-08T10:00:00"
    },
    {
      "iterationId": "iter-002",
      "iterationRound": 2,
      "datasetVersion": "dataset-v2",
      "modelVersion": "model-20260108-002",
      "accuracyRecord": {
        "macroF1Mean": 0.88
      },
      "labelSpaceVersion": "ls-v2",
      "labelCount": 5,
      "createdAt": "2026-01-08T12:00:00"
    }
  ],
  "trend": {
    "macroF1ByRound": [0.85, 0.88],
    "labelCountByRound": [4, 5]
  }
}
```

### 2. 查看标签注册表

**API 调用**:

```bash
curl http://localhost:8080/api/iterative-labeling/label-registry
```

**响应示例**:

```json
{
  "labelSpaceVersion": "ls-v2",
  "labels": [
    {
      "labelId": 1,
      "labelName": "正常",
      "createdAt": "2026-01-08T10:00:00"
    },
    {
      "labelId": 2,
      "labelName": "逆变器故障",
      "createdAt": "2026-01-08T10:00:00"
    },
    {
      "labelId": 3,
      "labelName": "组串故障",
      "createdAt": "2026-01-08T10:00:00"
    },
    {
      "labelId": 4,
      "labelName": "并网故障",
      "createdAt": "2026-01-08T10:00:00"
    },
    {
      "labelId": 5,
      "labelName": "组串开路",
      "createdAt": "2026-01-08T11:30:00"
    }
  ],
  "labelMap": {
    "正常": 0,
    "逆变器故障": 1,
    "组串故障": 2,
    "并网故障": 3,
    "组串开路": 4
  }
}
```

### 3. 查看闭环状态

**API 调用**:

```bash
curl http://localhost:8080/api/iterative-labeling/loops/loop-001
```

**响应示例**:

```json
{
  "loopId": "loop-001",
  "iterationRound": 2,
  "stage": "backfilled",
  "datasetVersion": "dataset-v2",
  "modelRef": "model-20260108-002",
  "labelSpaceSnapshot": {
    "labelSpaceVersion": "ls-v2",
    "labelIds": [1, 2, 3, 4, 5]
  },
  "labelSpaceLag": false
}
```

**字段说明**:

- `stage`: 当前阶段（`trained` / `predicted` / `reviewing` / `reviewed` / `backfilled`）
- `labelSpaceLag`: 模型标签空间是否落后于注册表当前版本

### 4. 断点恢复

如果审核过程中关闭了浏览器或中断了会话，可以重新访问审核页面：

```
http://localhost:5173/iterative-labeling/review/review-001
```

系统会自动加载已保存的审核进度，继续未完成的审核。

### 5. 手动添加标签

如果需要在审核之外手动添加新标签：

**API 调用**:

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/label-registry/labels \
  -H "Content-Type: application/json" \
  -d '{
    "labelName": "直流拉弧"
  }'
```

**响应示例**:

```json
{
  "labelId": 6,
  "labelSpaceVersion": "ls-v3"
}
```

---

## 常见问题

### Q1: LLM 建议不可用怎么办？

**可能原因**:
1. GLM API Key 未配置或无效
2. GLM 服务超时
3. 网络连接问题

**解决方法**:
1. 检查 `.env.local` 文件中的 `GLM_API_KEY`
2. 确认已执行 `source scripts/load_glm_env.sh`
3. 审核仍可继续，只是没有 LLM 建议

### Q2: 训练失败，提示缺少标签列怎么办？

**错误示例**:

```json
{
  "error": "Missing required columns",
  "missingColumns": ["fault_label"]
}
```

**解决方法**:
- 确保数据集包含真值标签列
- 如果是预测阶段，应使用**无标签数据集**

### Q3: 预测失败，提示 model_ref 无效怎么办？

**错误示例**:

```json
{
  "error": "Invalid model_ref"
}
```

**解决方法**:
- 检查 `model_ref` 是否来自训练步骤的返回值
- 确认模型文件未被删除

### Q4: 如何查看某个单元的详细信息？

在审核页面，点击单元卡片可展开详情，包含：
- 设备标识（site_id, device_id）
- 时间窗口
- 特征摘要（如果数据集包含）
- 历史标签（如果有）

### Q5: skip 的单元会影响下一轮训练吗？

**不会**。`skip` 单元：
- 不写入真值标签
- 不计入精度统计
- 不进入回流数据集
- 不参与下一轮训练

建议只在**信息不足**时使用 `skip`。

### Q6: 如何切换到不同的槽位（slot）？

**槽位用途**: 多环境/多产品线分区（如 `default` / `production` / `experiment`）

**创建闭环时指定**:

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops \
  -H "Content-Type: application/json" \
  -d '{
    "slot": "production"
  }'
```

**查询迭代历史时指定**:

```bash
curl http://localhost:8080/api/iterative-labeling/iterations?slot=production
```

### Q7: 如何导出标注后的数据集？

目前数据集存储在：

```
backend-service/data/iterative_labeling/ground_truth/default/{dataset_version}.json
```

可以直接读取该文件，或通过未来的导出 API（待开发）。

---

## 性能优化建议

### 小批量审核（<100 单元）

当前配置已优化，无需调整。

### 大批量审核（>500 单元）

1. **分批审核**
   - 将大批次拆分为多个小批次
   - 每批 100-200 单元

2. **关闭 LLM 辅助**（可选）
   - 创建审核会话时设置 `"enableLlm": false`
   - 加快审核创建速度

3. **并发优化**（需代码修改）
   - 使用 `asyncio.gather` 并发生成 LLM 建议
   - 建议并发数: 5-10

---

## 数据备份

### 建议备份文件

```bash
# 进入数据目录
cd backend-service/data/iterative_labeling

# 备份标签注册表
cp label_registry.json label_registry.json.backup

# 备份迭代历史
tar -czf iterations-backup-$(date +%Y%m%d).tar.gz iterations/

# 备份真值标签
tar -czf ground_truth-backup-$(date +%Y%m%d).tar.gz ground_truth/
```

### 定期备份策略

- **每日备份**: 迭代历史、真值标签
- **每周备份**: 标签注册表
- **重要节点**: 审核会话结果

---

## 联系与支持

如有问题，请参考：

- **设计文档**: `docs/specs/pv-fault-iterative-labeling-loop/design.md`
- **交付总结**: `docs/specs/pv-fault-iterative-labeling-loop/DELIVERY_SUMMARY.md`
- **任务追踪**: `docs/specs/pv-fault-iterative-labeling-loop/tasks.md`

或提交 Issue 到项目仓库。

---

**最后更新**: 2026-01-XX
