# AIP 界面快速上手指南 - 迭代标注系统

## 前提条件

1. ✅ 系统已启动（运行 `bash start-dev.sh`）
2. ✅ 浏览器访问：`http://localhost:5173`
3. ✅ 后端API运行：`http://localhost:8080`

---

## 第一步：准备数据集

### 1.1 准备有标签的训练数据

您需要准备一个CSV文件，包含：

| 必需列 | 说明 | 示例 |
|--------|------|------|
| `site_id` | 站点ID | "site-001" |
| `device_id` | 设备ID | "inverter-001" |
| 时序特征列 | 电流、电压等 | `current_a`, `voltage_ab` 等 |
| `fault_label` | 故障标签（真值） | 0=正常, 1=逆变器故障, 2=组串故障 |

**示例数据格式**：

```csv
site_id,device_id,timestamp,current_a,voltage_ab,power,fault_label
site-001,inv-001,2026-01-01 10:00:00,5.2,380,1976,0
site-001,inv-001,2026-01-01 10:15:00,0.1,320,32,1
site-001,inv-002,2026-01-01 10:00:00,5.5,385,2117,0
```

### 1.2 上传数据集到AIP平台

目前需要通过API上传（前端数据集管理界面在其他模块）：

```bash
# 上传训练数据集
curl -X POST http://localhost:8080/api/upload/file \
  -F "file=@labeled_train_data.csv" \
  -F "dataset_name=pv_fault_train_v1"

# 记录返回的 file_id
```

---

## 第二步：创建迭代闭环（API调用）

当前版本需要通过API创建闭环（未来版本会有前端创建界面）。

### 2.1 创建闭环

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops \
  -H "Content-Type: application/json" \
  -d '{
    "slot": "default"
  }'
```

**响应示例**：

```json
{
  "loopId": "loop-550e8400-e29b-41d4-a716-446655440000",
  "iterationRound": 1,
  "stage": null
}
```

**重要**：记录 `loopId`，后续所有操作都需要这个ID。

### 2.2 训练模型

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops/{loopId}/train \
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

**响应示例**：

```json
{
  "modelRef": "model-20260615-001",
  "accuracyRecord": {
    "macroF1Mean": 0.85,
    "macroF1Std": 0.02
  },
  "labelSpaceSnapshot": {
    "labelSpaceVersion": "ls-v1",
    "labelIds": [0, 1, 2, 3]
  }
}
```

**重要**：记录 `modelRef`，用于预测。

### 2.3 预测无标签数据

准备一个无标签的CSV文件（不含 `fault_label` 列）：

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops/{loopId}/predict \
  -H "Content-Type: application/json" \
  -d '{
    "modelRef": "model-20260615-001",
    "unlabeledDatasetVersion": "dataset-unlabeled-v1"
  }'
```

**响应示例**：

```json
{
  "predictionBatchId": "pred-batch-001",
  "unitCount": 150
}
```

**重要**：记录 `predictionBatchId`，用于创建审核会话。

---

## 第三步：创建审核会话（API调用）

### 3.1 创建会话（启用GLM辅助）

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/review-sessions \
  -H "Content-Type: application/json" \
  -d '{
    "loopId": "loop-550e8400-e29b-41d4-a716-446655440000",
    "predictionBatchId": "pred-batch-001",
    "enableLlm": true
  }'
```

**响应示例**：

```json
{
  "reviewId": "review-20260615-001",
  "totalCount": 150
}
```

**重要**：记录 `reviewId`，这是访问审核页面的关键。

---

## 第四步：打开审核页面（前端界面）

### 4.1 访问审核页面

在浏览器中访问：

```
http://localhost:5173/iterative-labeling/review/{reviewId}
```

**示例**：

```
http://localhost:5173/iterative-labeling/review/review-20260615-001
```

### 4.2 审核页面说明

页面布局：

```
┌─────────────────────────────────────────────────────────┐
│  迭代标注审核 - Session: review-20260615-001           │
│  [返回列表]                                             │
├─────────────────────────────────────────────────────────┤
│  进度: 0 / 150 (0.00%)                                  │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                         │
│  三方精度对比                                           │
│  ┌─────────────┬─────────────┬─────────────┐          │
│  │ 分类器精度  │ GLM精度     │ 人工基准    │          │
│  │ ---%        │ ---%        │ 100.00%     │          │
│  │ 0/0 正确    │ 0/0 正确    │ 0 已审核    │          │
│  └─────────────┴─────────────┴─────────────┘          │
│                                                         │
│  当前审核单元 (1/150)                                  │
│  ┌───────────────────────────────────────────────┐    │
│  │ 诊断单元: site-001_inv-001_window-1           │    │
│  │                                                 │    │
│  │ 🤖 分类器预测                                  │    │
│  │ 标签: 逆变器故障 (label_id: 1)                │    │
│  │ 置信度: 0.85                                   │    │
│  │                                                 │    │
│  │ 🧠 GLM-5.1 建议                                │    │
│  │ 标签: 组串故障 (label_id: 2)                  │    │
│  │ 理由: 电流曲线异常，疑似组串开路导致...        │    │
│  │                                                 │    │
│  │ ⚠️ 两来源不一致！请仔细审查                   │    │
│  │                                                 │    │
│  │ 您的裁决：                                      │    │
│  │ [✓ 确认分类器] [✎ 修正] [+ 新标签] [⊗ 跳过]   │    │
│  └───────────────────────────────────────────────┘    │
│                                                         │
│  [< 上一个]  [下一个 >]  [完成审核]                   │
└─────────────────────────────────────────────────────────┘
```

### 4.3 四类审核动作

#### ✓ 确认分类器 (confirm)

- **使用场景**：分类器预测正确
- **操作**：点击 `[✓ 确认分类器]` 按钮
- **效果**：
  - 接受分类器预测作为真值标签
  - 自动进入下一个单元
  - 分类器精度 +1

#### ✎ 修正 (correct)

- **使用场景**：分类器预测错误，但正确标签在列表中
- **操作**：
  1. 点击 `[✎ 修正]` 按钮
  2. 从下拉列表选择正确标签
  3. 点击 `[确认]`
- **效果**：
  - 写入正确的真值标签
  - 自动进入下一个单元
  - 分类器精度计算（预测 ≠ 真值）

#### + 新标签 (new_label)

- **使用场景**：发现新的故障类型，当前列表没有
- **操作**：
  1. 点击 `[+ 新标签]` 按钮
  2. 输入新标签名称（如 "组串开路"）
  3. 点击 `[确认]`
- **效果**：
  - 自动分配新 label_id（单调递增）
  - 写入真值标签
  - 更新标签注册表
  - 自动进入下一个单元

#### ⊗ 跳过 (skip)

- **使用场景**：信息不足，无法判断
- **操作**：点击 `[⊗ 跳过]` 按钮
- **效果**：
  - 标记为 `pending`（存疑）
  - **不写入真值标签**
  - **不计入精度统计**
  - **不进入回流数据集**
  - 自动进入下一个单元

### 4.4 实时精度更新

每提交一条裁决，三方精度面板会实时更新：

- **分类器精度** = 分类器预测命中人工裁决的比例
- **GLM精度** = GLM建议命中人工裁决的比例（仅在有GLM建议的单元上计算）
- **人工基准** = 已审核单元的100%一致口径

### 4.5 断点恢复

- 审核过程中可以随时关闭页面
- 下次访问同一 `reviewId` 会自动恢复进度
- 已提交的裁决不会丢失

---

## 第五步：回流新数据集（API调用）

审核完成后（或部分完成），执行回流：

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops/{loopId}/backfill \
  -H "Content-Type: application/json" \
  -d '{
    "reviewId": "review-20260615-001",
    "mergeBase": true
  }'
```

**响应示例**：

```json
{
  "datasetVersion": "dataset-v2",
  "unitCount": 120
}
```

**说明**：
- `unitCount` 排除了 `skip` 单元（pending）
- `mergeBase=true` 会与上一轮数据集累积合并
- 生成新的 `dataset-v2`，可用于下一轮训练

---

## 第六步：下一轮训练

使用回流后的新数据集版本，重复第二步的训练：

```bash
curl -X POST http://localhost:8080/api/iterative-labeling/loops/{loopId}/train \
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

然后继续预测 → 审核 → 回流的闭环。

---

## 查看迭代历史（API调用）

随时查看迭代历史和精度趋势：

```bash
curl http://localhost:8080/api/iterative-labeling/iterations?slot=default
```

**响应示例**：

```json
{
  "iterations": [
    {
      "iterationRound": 1,
      "datasetVersion": "dataset-v1",
      "modelVersion": "model-20260615-001",
      "accuracyRecord": {"macroF1Mean": 0.85},
      "labelCount": 4,
      "createdAt": "2026-06-15T10:00:00"
    },
    {
      "iterationRound": 2,
      "datasetVersion": "dataset-v2",
      "modelVersion": "model-20260615-002",
      "accuracyRecord": {"macroF1Mean": 0.88},
      "labelCount": 5,
      "createdAt": "2026-06-15T12:00:00"
    }
  ],
  "trend": {
    "macroF1ByRound": [0.85, 0.88],
    "labelCountByRound": [4, 5]
  }
}
```

---

## 常见问题

### Q1: 如何找到我的 reviewId？

A: 创建审核会话后，API会返回 `reviewId`。记录下来或从响应中复制。

### Q2: GLM建议不可用怎么办？

A: 
1. 检查 `.env.local` 文件中的 `GLM_API_KEY` 是否配置
2. 确认启动时执行了 `source scripts/load_glm_env.sh`
3. GLM不可用不影响审核，只是没有智能建议

### Q3: 审核中途想暂停怎么办？

A: 直接关闭浏览器即可，下次访问同一URL会自动恢复进度。

### Q4: 如何看到已审核的单元？

A: 当前版本审核页面只显示当前单元。已审核单元的统计在"三方精度对比"面板中。

### Q5: skip的单元会怎样？

A:
- 不写入真值标签
- 不计入精度统计
- 不进入回流数据集
- 不参与下一轮训练

建议只在**信息确实不足**时使用skip。

---

## 完整流程图

```
┌─────────────┐
│ 1. 准备数据 │ (CSV文件 + 上传)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 2. 创建闭环 │ (API: POST /loops)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 3. 训练模型 │ (API: POST /loops/{id}/train)
└──────┬──────┘      → 获得 modelRef
       │
       ▼
┌─────────────┐
│ 4. 预测数据 │ (API: POST /loops/{id}/predict)
└──────┬──────┘      → 获得 predictionBatchId
       │
       ▼
┌─────────────┐
│ 5. 创建会话 │ (API: POST /review-sessions)
└──────┬──────┘      → 获得 reviewId
       │
       ▼
┌─────────────┐
│ 6. 人工审核 │ (前端: /iterative-labeling/review/{reviewId})
└──────┬──────┘      ✓确认 / ✎修正 / +新标签 / ⊗跳过
       │
       ▼
┌─────────────┐
│ 7. 回流数据 │ (API: POST /loops/{id}/backfill)
└──────┬──────┘      → 获得新 datasetVersion
       │
       ▼
┌─────────────┐
│ 8. 下一轮   │ (重复步骤3-7)
└─────────────┘
```

---

## 快速测试脚本

创建一个测试脚本 `test_iterative_labeling.sh`：

```bash
#!/bin/bash
# 迭代标注系统快速测试脚本

API_BASE="http://localhost:8080/api/iterative-labeling"

# 1. 创建闭环
echo "1. 创建迭代闭环..."
LOOP_RESPONSE=$(curl -s -X POST "$API_BASE/loops" \
  -H "Content-Type: application/json" \
  -d '{"slot": "default"}')
echo "$LOOP_RESPONSE"

LOOP_ID=$(echo "$LOOP_RESPONSE" | grep -o '"loopId":"[^"]*' | cut -d'"' -f4)
echo "Loop ID: $LOOP_ID"

# 2. 查看闭环状态
echo -e "\n2. 查看闭环状态..."
curl -s "$API_BASE/loops/$LOOP_ID" | jq .

# 3. 查看标签注册表
echo -e "\n3. 查看标签注册表..."
curl -s "$API_BASE/label-registry" | jq .

echo -e "\n下一步:"
echo "  - 准备数据集并上传"
echo "  - 执行训练: curl -X POST $API_BASE/loops/$LOOP_ID/train -H 'Content-Type: application/json' -d '{...}'"
```

运行：

```bash
chmod +x test_iterative_labeling.sh
./test_iterative_labeling.sh
```

---

## 下一步

1. **准备真实数据集** - 确保包含必需列和真值标签
2. **小批量测试** - 先用10-20个样本测试完整流程
3. **GLM Prompt优化** - 根据实际效果调整LLM建议质量
4. **批量审核** - 正式使用时可100-200个单元一批

---

**需要帮助？**

参考完整文档：
- **用户指南**: `USER_GUIDE.md`
- **交付总结**: `DELIVERY_SUMMARY.md`
- **API文档**: 见交付总结第四节

**最后更新**: 2026-06-15
