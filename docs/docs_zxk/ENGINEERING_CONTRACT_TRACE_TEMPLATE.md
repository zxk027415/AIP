# 工程改动教学模板（字段流转 + 数据契约 + 前后端通信）

> 适用场景：每次做平台改动（尤其是工作流、算子、回测、预测、Agent 工具化）后，沉淀一份“我到底改了什么、字段怎么流动、为什么这么设计、如何验证”的记录。  
> 目标：避免“代码跑通了但自己没学到”，把每次改动都变成可复用方法论。

---

## 0. 使用说明（每次改动先复制这份模板）

- **Cursor 学习向规则**（与本模板配套）：项目根目录 `.cursor/rules/beginner-fullstack-field-trace.mdc`（常驻：全栈字段链 + 复盘习惯）、`.cursor/rules/engineering-contract-trace-template-companion.mdc`（打开 `docs_zxk` / `design` 时：按章节讲解模板怎么填）。
- 一次改动写一份（不要把多个需求揉在一份里）。
- 先写**事实**（字段、接口、文件），再写观点（设计权衡）。
- 每一层至少写出 1 个“输入字段”和 1 个“输出字段”。
- 能画链路就画链路，至少保证“字段名可追踪”。

---

## 1. 改动摘要（What Changed）

### 1.1 需求背景
- 需求标题：
- 提出人/来源：
- 业务目标（1-2句）：
- 非功能目标（复用性/兼容性/性能/安全）：

### 1.2 变更范围
- 前端文件：
  - ``
  - ``
- 后端文件：
  - ``
  - ``
- 算子文件：
  - ``
  - ``
- 配置/文档：
  - ``

### 1.3 行为变化（用户视角）
- 改前：
- 改后：

---

## 2. 字段流转链（Data Flow Trace）

> 固定链路：`UI Form -> HTTP body -> API handler -> Service/Workflow -> global_config -> Operator params -> Output`

### 2.1 字段总览（核心字段清单）

| 字段语义 | UI字段 | HTTP字段 | API内部字段 | `_global_config` 字段 | 算子读取点 | 最终影响 |
|---|---|---|---|---|---|---|
| 示例：预测窗掩码开关 | `backtest_mask_target_values` | `mask_target_values` | `backtest_params["mask_target_values"]` | `backtest_mask_target_values` | `row_filter/handle_missing` | 防止测试窗真实值泄漏 |
|  |  |  |  |  |  |  |

### 2.2 逐层追踪（按顺序填写）

#### A) UI Form 层
- 文件：
- 组件：
- 关键字段：
- 默认值：
- 可选/必选：

#### B) HTTP 请求层
- 文件：
- 请求方法/URL：
- body 字段：
- 命名转换（camelCase -> snake_case）：

#### C) API Handler 层
- 文件：
- 函数：
- 如何读取字段：
- 缺省回退策略：

#### D) 执行上下文层（`global_config` 注入）
- 注入点函数：
- 注入字段：
- 注入时机（每次执行/每个回测日）：

#### E) 算子消费层
- 算子1：
  - 读取字段：
  - 分支条件（`if`）：
  - 变更行为：
- 算子2：
  - 读取字段：
  - 分支条件（`if`）：
  - 变更行为：

#### F) 输出层（结果回传）
- 后端响应新增字段：
- 前端消费位置：
- 页面表现：

---

## 3. 数据契约（Data Contract）

### 3.1 API 契约

#### 请求契约（Request Schema）
- Endpoint：
- Method：
- Body:
```json
{
  "field_a": "string | optional",
  "field_b": "number | optional | default=...",
  "field_c": "boolean | optional"
}
```

#### 响应契约（Response Schema）
```json
{
  "success": true,
  "result_x": [],
  "artifact_urls": [],
  "error": null
}
```

### 3.2 执行上下文契约（`_global_config`）

| 字段 | 类型 | 可选 | 默认值 | 生产者 | 消费者 |
|---|---|---|---|---|---|
| `operate_status` | string | 否 | `training` | API/workflow | 多个算子 |
|  |  |  |  |  |  |

### 3.3 算子 I/O 契约

#### 算子：`<operator_id>`
- 输入契约（必须字段/可选字段）：
- 输出契约：
- 临时辅助字段（如 `__backtest_true_target`）生命周期：
  - 生成者：
  - 消费者：
  - 清理点：

---

## 4. 设计权衡（Why This Design）

### 4.1 复用性策略（必填）
- 专属行为是否默认开启：`是/否`
- 如果否，开关字段：
- 为什么这样不会污染其他场景：

### 4.2 向后兼容策略（必填）
- 旧请求是否可继续使用：
- 旧字段是否仍有效：
- 没传新字段时系统行为：

### 4.3 风险与防护
- 风险1：
  - 触发条件：
  - 防护措施：
- 风险2：
  - 触发条件：
  - 防护措施：

---

## 5. 验证清单（Validation Checklist）

### 5.1 功能验证
- [ ] UI 字段可编辑、默认值正确
- [ ] 请求体字段正确发送
- [ ] 后端正确读取并注入
- [ ] 算子分支按开关变化
- [ ] 页面结果正确显示

### 5.2 兼容性验证
- [ ] 不传新字段时行为与旧版一致
- [ ] 非回测模式不受影响
- [ ] 其他模板/算子复用未被破坏

### 5.3 工程验证
- [ ] 前端 `tsc` 通过
- [ ] 后端 `py_compile` 通过
- [ ] lints 无新增错误

---

## 6. 最小学习闭环（你真正学到什么）

### 6.1 今日关键词（最多3个）
- 关键词1：
- 关键词2：
- 关键词3：

### 6.2 5分钟复盘问题
- 这个字段是在哪一层改名的？
- 如果不传这个字段，系统默认是什么？
- 哪个 `if` 决定了最终行为变化？

### 6.3 下次可复用结论
- 结论1：
- 结论2：

---

## 7. 填写示例（可参考后删除）

### 示例字段：`mask_target_values`
- UI：`backtest_mask_target_values`
- HTTP：`mask_target_values`
- API：`backtest_params["mask_target_values"]`
- global config：`backtest_mask_target_values`
- operator：`row_filter/handle_missing`
- 行为：预测窗目标值是否置空
- 结果：是否避免时序泄漏

---

## 8. 附录：排错速查（Debug Cheatsheet）

- UI里改了值，但后端没收到  
  - 检查：前端请求 body 是否包含字段（network 面板）
- 后端收到了值，但算子没生效  
  - 检查：是否写入 `_global_config`
- `_global_config` 有值，行为还是不变  
  - 检查：算子分支条件是否命中（布尔默认值/字段名拼写）
- 看起来像泄漏  
  - 检查：预测窗目标值是否被掩码，测试标签是否来自辅助真值列

