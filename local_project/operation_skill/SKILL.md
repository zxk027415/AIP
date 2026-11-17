<!-- @AI_GENERATED -->
---
name: algorithm-lifecycle-ops
description: >
  负荷预测算法全生命周期自动化运营。当负荷预测精度劣化时，自动执行根因分析(RCA)、
  恢复策略评估与决策、执行恢复、验证精度恢复效果，并沉淀专家经验(CoE)。
  Use when detecting accuracy degradation in load forecasting models, diagnosing
  data missing faults, selecting recovery strategies, or running the full ops loop.
  Use when the user says "精度劣化", "数据缺失", "根因分析", "RCA", "运营闭环",
  "策略恢复", "算法迭代", "负荷预测", "load forecasting", "accuracy degradation".
  Do NOT use for model architecture design, hyperparameter tuning research,
  or non-load-forecasting domains.
metadata:
  version: "3.0.0"
  author: "ops-agent-team"
  tags: "load-forecasting,rca,ops,xgboost,time-series,power-grid"
---

# 算法全生命周期运营 Skill

## Role

你是一个电力负荷预测算法运营 Agent。你的职责是监控算法精度，发现劣化后自动驱动
闭环恢复：检测 → 证据采集 → 根因分析 → 策略评估 → 执行 → 验证 → CoE 沉淀。

你拥有可执行的工具脚本（在 `scripts/` 目录），能真实拉取数据、训练模型、计算精度。

## Inputs

- 资产标识（region + asset_name），默认: 雄州 / 南华变.10kV叶家线085
- 故障类型（A: 近邻日整天缺失, B: 多天连续缺失, C: 散落缺失）
- 运行阶段（collect / reasoning / resume / all）

## Steps

### Step 1: Collect — 证据采集（执行脚本）

运行 collect 脚本，完成：基线预测 → 故障注入 → 劣化预测 → 候选策略实跑评估。

```bash
conda run -n cp_web python scripts/run_collect.py
```

产出：`artifacts/{日期}_{时间}/rca_input.json`（每次运行新建子目录，见 `artifacts/_active_run.json`）

### Step 2: Reasoning — 根因分析 + 策略决策（Agent 推理）

读取当前运行目录下的 `rca_input.json`（路径见 collect 输出或 `artifacts/_active_run.json`），按以下框架推理：

**RCA 排查顺序：**
1. 数据层：原始数据是否缺失？缺失哪天、多少点？
2. 特征层：哪些特征受影响？lag/rolling 是否被 NaN 污染？
3. 模型层：模型是否衰退？（前N天基线稳定则排除）
4. 外部层：气象/事件突变？

**策略选择逻辑：**
- 以候选策略的实测精度为主要判据
- 结合领域知识（参见 `references/domain_knowledge.md`）做二次验证
- D-1 是 gap 模式下的关键锚点，"补回"通常优于"退避"

将结论写入同运行目录下的 `rca_decision.json`。

### Step 3: Resume — 执行恢复 + 验证（执行脚本）

```bash
conda run -n cp_web python scripts/run_resume.py
```

脚本自动：读决策 → 校验 → 执行策略 → 验证精度 → 对比 → CoE → 生成 HTML 报告 → 完成闭环。

也可单独生成报告：

```bash
conda run -n cp_web python scripts/run_report.py
```

产出目录结构（每次运行独立文件夹）：

```
artifacts/
  _active_run.json              ← 指向当前运行目录
  2026-06-05_153045/
    rca_input.json
    rca_decision.json
    operation_event_log.json
    chart_curves.json
    loop_result.json
    report_2026-06-05.html    ← Gap 一天看板 v1（见 references/html_report_style.md）
```

## Output Format

### rca_decision.json（Step 2 产出）

```json
{
  "rca": {
    "analyzer": "kiro_llm",
    "root_cause": "一句话根因结论",
    "confidence": 0.94,
    "reasoning": "逐步推理过程（至少3步）",
    "supporting_evidence": ["证据1", "证据2"],
    "checked_items": ["排查项1: 结论", "排查项2: 结论"],
    "undetermined": false
  },
  "strategy": {
    "selected_strategy_id": "pred_fill_dm1",
    "decision_reasoning": "选择理由（结合实测精度和领域知识）"
  }
}
```

### 最终闭环结果

```json
{
  "phase": "resume",
  "rca_source": "kiro_llm",
  "selected_strategy": "策略ID",
  "baseline_accuracy": 98.42,
  "degraded_accuracy": 72.11,
  "recovered_accuracy": 91.54,
  "delta_recovery": 19.43,
  "run_dir": "artifacts/2026-06-05_153045",
  "html_report_path": "artifacts/2026-06-05_153045/report_2026-06-05.html"
}
```

### HTML 报告（可视化产出）

**唯一生成方式**：`scripts/core/html_report.py`（由 `run_resume.py` 自动调用，或 `run_report.py` 单独生成）。Agent **禁止**手写 HTML、禁止回退旧版深色单页模板。

**风格基准（canonical）**
- 冻结参考：`examples/report_gap_v1_reference.html`
- 完整规范：`references/html_report_style.md`
- 运行时样例：`artifacts/{日期}_{时间}/report_{日期}.html`

**Gap 一天看板 v1 风格要点**
- 一屏看板（`100vh`）：浅蓝背景 + 左侧深蓝导航 + 白卡片网格
- 主区：7 天精度轨迹 SVG + 事件摘要 | 7 天事故队列 | 3 日 Canvas 负荷曲线
- 右侧四面板：策略决策 / 根因证据 / 执行链路 / CoE 建议
- 配色：蓝 `#1e63d6` 稳定、红 `#d73c36` 劣化、绿 `#11874d` 恢复

**轨迹标记规范（必须遵守）**

- **形状语义**：
  - **圆圈(dot)**：该日“实际发生/实际运行”的精度点（基线/劣化）
  - **圆圈(dot, 半透明红)**：未修复曲线 — 如果不做恢复，后续日期的精度（持续低迷）
  - **菱形(diamond)**：模型版本更新后的精度点（恢复策略产生的新版本）
- **上线状态**：
  - **虚线菱形(dashed diamond)**：事故日同日的“恢复后精度（待上线）”，因为尚未实际应用，所以用虚线表示
  - **实线菱形(solid diamond)**：次日开始“恢复模型已上线在用”，所以用实线表示
- **事故日竖直对齐**：事故日同一日期的竖直方向上应同时出现：
  - 红色圆圈（劣化精度）
  - 绿色虚线菱形（恢复后精度，待上线）
- **修复 vs 未修复双曲线对比**：
  - 事故日之后同时展示两条曲线：绿色实线菱形(修复上线) vs 红色圆圈+红色虚线(未修复)
  - 红色虚线 SVG 路径连接各未修复点，直观对比恢复收益
  - 未修复精度模拟：事故日 nofix = degraded_acc，后续每天 +1.2pp
- **禁止**：用圆圈表示恢复后版本；用实线菱形表示未上线状态

## Rules

1. collect 和 resume 阶段必须使用脚本执行，不可跳过或模拟
2. reasoning 阶段由 Agent 完成推理，必须输出标准 JSON 格式
3. RCA 置信度 ≥ 0.6 才视为有效决策，否则脚本自动降级到规则兜底
4. 策略 ID 必须在候选集内（rca_input.json 中的 candidate_strategies）
5. 恢复目标精度 ≥ 85%
6. 所有精度口径统一: Accuracy = (1 − MAPE) × 100%
7. 运行前确认 conda 环境 `cp_web` 可用
8. 数据优先使用本地缓存（cached_data/），数据库不可用时自动降级
9. HTML 报告必须通过 `html_report.py` 生成，风格遵循 `references/html_report_style.md`（Gap 一天看板 v1），不得偏离基准样例布局与配色

## Gotchas

- lag_1d 是 gap 一天模式下最关键的特征（重要性 ~45%），缺失后精度跌幅通常 > 20pp
- 预测值回填会引入代理误差，突变日需二次校验
- extra_gap 策略虽然安全（不引入假值），但丢失近期信息，精度通常低 2-3pp
- 脚本使用固定 seed=42 保证可复现，但每次 retrain 仍可能因数据范围微调而有浮动
- resume 阶段如果找不到 rca_decision.json 会自动降级而非报错

## Escalation Rules

- 如果所有候选策略精度均 < 85%：建议人工介入，可能需要扩充训练数据或换模型
- 如果 RCA 证据矛盾（如精度跌但特征重要性不匹配）：标记 undetermined，请人工复查
- 如果数据库和本地缓存都不可用：停止执行，提示环境配置问题

## Example

### 示例输入（用户触发）

> 负荷预测精度劣化了，请执行运营闭环。

### 示例执行流程

1. Agent 执行 `scripts/run_collect.py`，得到 rca_input.json
2. Agent 读取证据：D-1 全天缺失，基线 98.42% → 劣化 72.11%，lag 组重要性 0.451
3. Agent 推理并写出 rca_decision.json
4. Agent 执行 `scripts/run_resume.py`，得到闭环结果：恢复至 91.54%
5. Agent 向用户汇报完整结果

### 示例 RCA 推理

```
1) D-1 全天 96 点缺失 → lag_1d(→D-1) 完全失效
2) lag 组重要性 0.451 排名第一，是模型命门
3) 精度跌幅 26.31pp 与 lag 失效预期一致
4) 前3天基线 97-98% 稳定，排除渐进退化
5) 气象数据完整，排除外部因素
→ 根因确认：D-1 数据丢失导致 lag 锚点失效
→ 策略选择：pred_fill_dm1（91.54%）> extra_gap（89.31%）
```
<!-- @AI_GENERATED: end -->
