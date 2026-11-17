# AccuracyEvaluator 使用说明

## 概述

`AccuracyEvaluator` 是光伏故障人机协同迭代标注闭环系统中的三方精度增量计算器。

**职责**：
- 以已固化 `Human_Verdict`（人工裁决）为真值，实时计算三方精度对比
- 支持增量更新，每提交一条裁决即时更新统计，无需重算全量
- 只纳入有效审核单元（`confirm`/`correct`/`new_label`），排除 `pending`（存疑跳过）

**映射需求**：6.1, 6.2, 6.3, 6.4, 6.5

## 三方精度说明

| 精度指标 | 含义 | 计算方式 |
|---------|------|---------|
| `classifier_accuracy` | 分类器原始预测精度 | 已审核单元中分类器预测命中人工裁决的比例 |
| `llm_accuracy` | LLM 建议精度 | 仅在有 LLM 建议的单元上计算，剔除缺失 |
| `human_verified_accuracy` | 人工核对后精度基线 | 已审核单元的 100% 一致口径（恒为 1.0） |
| `llm_coverage` | LLM 覆盖率 | 有 LLM 建议的已审核单元 / 已审核单元总数 |
| `macro.precision` | 宏平均精确率 | 对每个类别计算精确率后取算术平均 |
| `macro.recall` | 宏平均召回率 | 对每个类别计算召回率后取算术平均 |
| `macro.f1` | 宏平均 F1 | 对每个类别计算 F1 后取算术平均 |

## 基本用法

```python
from services.iterative_labeling.accuracy_evaluator import AccuracyEvaluator

# 创建评估器实例
evaluator = AccuracyEvaluator()

# 每次提交人工裁决时，增量更新
evaluator.update(
    verdict={
        "verdict_label": 1,           # 裁决标签（真值）
        "action_type": "confirm"      # 动作类型：confirm/correct/new_label/skip
    },
    classifier_prediction={
        "predicted_label": 1          # 分类器预测标签
    },
    llm_suggestion={                  # LLM 建议（可选）
        "suggested_label": 1,
        "available": True
    }
)

# 获取当前三方精度
accuracy = evaluator.get_current_accuracy()
print(f"分类器精度: {accuracy['classifier_accuracy']:.2%}")
print(f"LLM 精度: {accuracy['llm_accuracy']:.2%}")
print(f"LLM 覆盖率: {accuracy['llm_coverage']:.2%}")
print(f"Macro F1: {accuracy['macro']['f1']:.3f}")
print(f"已审核单元数: {accuracy['counted_units']}")
```

## 返回值结构

```python
{
    "classifier_accuracy": 0.85,        # 分类器原始预测精度（float）
    "llm_accuracy": 0.78,               # LLM 建议精度（float，仅有建议的单元）
    "human_verified_accuracy": 1.0,     # 人工核对后精度基线（float，恒 1.0）
    "llm_coverage": 0.92,               # LLM 覆盖率（float）
    "macro": {                          # macro 口径指标
        "precision": 0.82,              # 宏平均精确率（float）
        "recall": 0.80,                 # 宏平均召回率（float）
        "f1": 0.81                      # 宏平均 F1（float）
    },
    "counted_units": 50                 # 纳入统计的单元数（int）
}
```

## 关键约定

### 1. 只纳入有效审核单元

**只有** `action_type ∈ {confirm, correct, new_label}` 的单元才纳入精度统计。

`action_type == skip`（存疑跳过）的单元标记为 `pending`，**不写真值、不计精度**。

```python
# 这条会被统计
evaluator.update(
    verdict={"verdict_label": 1, "action_type": "confirm"},
    classifier_prediction={"predicted_label": 1}
)

# 这条会被排除（skip 不计入）
evaluator.update(
    verdict={"verdict_label": None, "action_type": "skip"},
    classifier_prediction={"predicted_label": 1}
)
```

### 2. LLM 缺失单元从 LLM 分母中剔除

当某个单元的 `llm_suggestion` 为 `None` 或 `available=False` 时：
- 该单元仍然计入 `counted_units`（已审核单元总数）
- 但从 `llm_accuracy` 的分母中剔除
- `llm_coverage` 反映有 LLM 建议的单元占比

```python
# 无 LLM 建议
evaluator.update(
    verdict={"verdict_label": 1, "action_type": "confirm"},
    classifier_prediction={"predicted_label": 1},
    llm_suggestion=None  # 不影响 classifier_accuracy，但不计入 llm_accuracy
)

# LLM 不可用
evaluator.update(
    verdict={"verdict_label": 2, "action_type": "confirm"},
    classifier_prediction={"predicted_label": 2},
    llm_suggestion={"suggested_label": 2, "available": False}  # 同样不计入 llm_accuracy
)
```

### 3. 增量更新与全量重算等价

每提交一条裁决增量更新得到的精度，等于对同一最终裁决集合做全量重算的结果。

这保证了审核过程中实时展示的精度与最终统计一致。

### 4. 边界情况

当 `counted_units == 0`（无已审核单元）时，返回占位值：
```python
{
    "classifier_accuracy": 0.0,
    "llm_accuracy": 0.0,
    "human_verified_accuracy": 0.0,
    "llm_coverage": 0.0,
    "macro": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
    "counted_units": 0
}
```

**不抛异常**，UI 可以安全调用。

## 完整示例：审核会话中的应用

```python
from services.iterative_labeling.accuracy_evaluator import AccuracyEvaluator

class ReviewSession:
    def __init__(self, review_id: str):
        self.review_id = review_id
        self.evaluator = AccuracyEvaluator()
        self.verdicts = []
    
    def submit_verdict(self, verdict: dict, classifier_pred: dict, llm_sugg: dict = None):
        """提交一条人工裁决"""
        # 存储裁决
        self.verdicts.append({
            "verdict": verdict,
            "classifier_prediction": classifier_pred,
            "llm_suggestion": llm_sugg
        })
        
        # 增量更新三方精度
        self.evaluator.update(verdict, classifier_pred, llm_sugg)
        
        # 返回当前精度快照
        return self.evaluator.get_current_accuracy()
    
    def get_accuracy_summary(self):
        """获取当前三方精度汇总"""
        accuracy = self.evaluator.get_current_accuracy()
        
        return {
            "review_id": self.review_id,
            "progress": f"{accuracy['counted_units']} 单元已审核",
            "classifier_accuracy": f"{accuracy['classifier_accuracy']:.2%}",
            "llm_accuracy": f"{accuracy['llm_accuracy']:.2%}",
            "llm_coverage": f"{accuracy['llm_coverage']:.2%}",
            "macro_f1": f"{accuracy['macro']['f1']:.3f}"
        }

# 使用示例
session = ReviewSession("review-001")

# 审核单元 1: confirm（分类器和 LLM 都对）
session.submit_verdict(
    verdict={"verdict_label": 1, "action_type": "confirm"},
    classifier_pred={"predicted_label": 1},
    llm_sugg={"suggested_label": 1, "available": True}
)

# 审核单元 2: correct（分类器错了，LLM 对了）
session.submit_verdict(
    verdict={"verdict_label": 2, "action_type": "correct"},
    classifier_pred={"predicted_label": 1},
    llm_sugg={"suggested_label": 2, "available": True}
)

# 审核单元 3: skip（存疑跳过，不计入精度）
session.submit_verdict(
    verdict={"verdict_label": None, "action_type": "skip"},
    classifier_pred={"predicted_label": 3}
)

# 获取汇总
print(session.get_accuracy_summary())
# 输出:
# {
#     "review_id": "review-001",
#     "progress": "2 单元已审核",
#     "classifier_accuracy": "50.00%",
#     "llm_accuracy": "100.00%",
#     "llm_coverage": "100.00%",
#     "macro_f1": "0.667"
# }
```

## API 参考

### `AccuracyEvaluator.__init__()`

初始化累计计数状态。

### `AccuracyEvaluator.update(verdict, classifier_prediction, llm_suggestion=None)`

增量更新：提交一条新裁决，更新三方精度。

**参数**：
- `verdict` (dict): 人工裁决字典
  - `verdict_label` (int): 裁决标签（真值）
  - `action_type` (str): 动作类型，枚举 `confirm`/`correct`/`new_label`/`skip`
- `classifier_prediction` (dict): 分类器预测字典
  - `predicted_label` (int): 预测标签
- `llm_suggestion` (dict, optional): LLM 建议字典
  - `suggested_label` (int): 建议标签
  - `available` (bool): 是否可用

### `AccuracyEvaluator.get_current_accuracy() -> dict`

获取当前三方精度。

**返回**：精度字典（见上文"返回值结构"）

### `AccuracyEvaluator.reset()`

重置累计状态（可选，用于开启新会话）。

## 测试验证

运行单元测试：

```bash
cd backend-service
conda run -n aip_web python -m pytest tests/test_accuracy_evaluator.py -v
```

测试覆盖：
- ✅ 边界情况：无已审核单元时返回占位值
- ✅ pending 单元被排除
- ✅ confirm/correct/new_label 动作被纳入统计
- ✅ LLM 覆盖率和精度计算
- ✅ LLM 不可用时从 LLM 分母中剔除
- ✅ 人工核对后精度基线恒为 1.0
- ✅ macro precision/recall/f1 计算
- ✅ 增量更新与全量重算等价

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 精度主口径 | macro F1（宏平均 F1） | 与训练阶段 `Accuracy_Record` 口径一致，跨轮可比 |
| 增量更新 | 维护累计计数状态 | 每提交一条裁决即时更新，无需重算全量，性能友好 |
| LLM 缺失处理 | 从 LLM 分母中剔除 | LLM 不可用不应拉低 LLM 精度，但影响覆盖率 |
| pending 处理 | 排除不计 | 存疑跳过不应污染精度统计与训练集 |
| 边界情况 | 返回占位值不抛异常 | UI 可以安全调用，不需要额外异常处理 |

## 与训练阶段精度口径对齐

训练阶段通过 `stratified_cv_eval` 算子得到的 `Accuracy_Record` 包含：
- `macro_f1_mean` ± `macro_f1_std`（主口径）
- `macro_precision_mean`
- `macro_recall_mean`

审核期三方精度评估器给出的 `macro` 对象与之口径一致，便于跨轮对比：

| 阶段 | 精度来源 | macro 口径 |
|------|---------|-----------|
| 训练 | 测试折评估 | `macro_f1_mean ± std` |
| 审核 | 人工裁决为真值 | `macro.f1`（实时） |

两者都采用宏平均（对每个类别单独计算后取算术平均），不加权，适合类别不平衡场景。
