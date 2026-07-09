<!-- @AI_GENERATED -->
# 负荷预测算法运营闭环 Skill

电力负荷预测算法全生命周期自动化运营。当负荷预测精度劣化时，自动执行根因分析（RCA）、恢复策略评估与决策、执行恢复、验证精度恢复效果，并生成可视化运营报告。

## 核心能力

- **真实数据驱动**：基于南华变.10kV叶家线085的真实负荷+气象数据，XGBoost 实跑计算精度
- **全闭环自动化**：检测 → 证据采集 → 根因分析 → 策略选择 → 执行恢复 → 验证 → 报告
- **逐日真实时间线**：7天精度轨迹全部由模型实算，无任何插值或造假
- **修复 vs 未修复对比**：HTML报告中双曲线真实对比，直观呈现恢复价值

## 默认场景

| 要素 | 值 |
|------|-----|
| 资产 | 雄州 / 南华变.10kV叶家线085 |
| 预测模式 | 次日预测 · Gap一天（lag_1d → D-1） |
| 缺失源日 | 2026-05-22（D-1 整天96点数据丢失） |
| 事故日 | 2026-05-24（D+1，精度劣化爆发） |
| 展示窗口 | 2026-05-21 ~ 2026-05-27（7天） |
| 选中策略 | pred_fill_dm1（预测值回填D-1，精度97.08%） |

## 快速开始

### 环境要求

- Python ≥ 3.9，conda 环境 `cp_web`
- 依赖：numpy, pandas, xgboost（见 `requirements.txt`）
- 数据：`cached_data/merged_20260201_20260527.csv`（离线缓存，已包含）

### 检查环境

```bash
conda run -n cp_web python scripts/check_environment.py
```

### 执行闭环（三步）

```bash
# Step 1: 证据采集（基线 → 故障注入 → 劣化 → 候选策略实跑评估）
conda run -n cp_web python scripts/run_collect.py

# Step 2: Agent 推理（读 rca_input.json → 写 rca_decision.json）
# 由 Kiro Agent 自动完成

# Step 3: 恢复执行 + 7天真实时间线计算 + HTML报告生成
conda run -n cp_web python scripts/run_resume.py
```

### 自定义事故日

```bash
conda run -n cp_web python scripts/run_collect.py --target-day 2026-05-26
```

### 单独重新生成报告

```bash
conda run -n cp_web python scripts/run_report.py
```

## 目录结构

```
operation_skill/
├── SKILL.md                     ← Agent Skill 入口（元数据 + 执行指令）
├── README.md                    ← 本文件（人类阅读）
├── requirements.txt             ← Python 依赖
├── fetch_asset_data.py          ← 数据库在线拉取模块（离线可忽略）
├── cached_data/                 ← 离线数据缓存（真实负荷+气象）
│   ├── merged_20260201_20260527.csv
│   └── meta.json
├── scripts/                     ← 可执行脚本
│   ├── check_environment.py     ← 环境检查
│   ├── run_collect.py           ← Phase 1: 证据采集
│   ├── run_resume.py            ← Phase 3: 恢复执行 + 报告
│   ├── run_report.py            ← 单独生成 HTML 报告
│   └── core/                    ← 核心计算引擎
│       ├── real_data.py         ← 数据加载/特征工程/模型训练/故障注入/策略/逐日计算
│       ├── html_report.py       ← HTML 看板渲染器（Gap一天看板 v1）
│       ├── metrics.py           ← 精度计算（MAPE → Accuracy）
│       ├── event_log.py         ← 运营事件日志
│       ├── comparison.py        ← 基线/劣化/恢复对比
│       ├── models.py            ← 数据模型定义
│       └── run_workspace.py     ← 运行目录管理
├── references/                  ← 领域知识 & 报告规范
│   ├── domain_knowledge.md      ← 特征工程/精度基准/故障图谱/决策原则
│   └── html_report_style.md    ← HTML 报告风格规范
├── examples/                    ← 示例 IO
│   ├── rca_input_sample.json
│   ├── rca_decision_sample.json
│   └── report_gap_v1_reference.html
└── artifacts/                   ← 运行产出（每次运行独立子目录）
    ├── _active_run.json         ← 指向当前运行目录
    └── 2026-06-05_173923/       ← 最新运行结果
        ├── rca_input.json
        ├── rca_decision.json
        ├── operation_event_log.json
        ├── real_timeline.json   ← 逐日真实精度（XGB实算）
        ├── chart_curves.json
        ├── loop_result.json
        └── report_2026-06-05.html
```

## 精度口径

所有精度统一为：**Accuracy = (1 − MAPE) × 100%**

| 场景 | 精度 | 说明 |
|------|------|------|
| 事故日基线 | 94.24% | 数据完整时真实预测 |
| 事故日劣化 | 86.03% | D-1缺失后真实预测（跌8.21pp） |
| pred_fill_dm1 恢复 | 97.08% | 回填D-1后真实预测（超越基线） |
| extra_gap 候选 | 71.38% | 退避到D-2后真实预测（本场景不适用） |

## 报告风格

HTML 报告遵循 **Gap一天看板 v1** 规范（详见 `references/html_report_style.md`）：

- 一屏看板 · 浅蓝背景 + 深蓝导航 + 白卡片网格
- 7天精度轨迹 SVG：修复(◇实线菱形) vs 未修复(○红色圆圈) 双曲线对比
- 事故日竖直对齐：红圈劣化 ↕ 绿虚线菱形恢复待上线
- 标签方向分离：同列高点标签朝上、低点朝下，避免重叠
- 3日 Canvas 负荷曲线 + 右侧四面板（策略/根因/执行/CoE）

## 技术要点

- **seed=42** 确保可复现
- **逐日计算逻辑**：事故日用选定策略真实重跑；后续日回填缺失后用基线模型正常运营
- **数据优先离线缓存**：`cached_data/`，数据库不可用时自动降级
- **每次运行独立目录**：通过 `_active_run.json` 追踪当前运行
<!-- @AI_GENERATED: end -->
