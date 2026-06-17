---
name: AIP Industrial Research Workbench
description: A restrained, evidence-first design system for industrial AI experimentation.
colors:
  primary: "#1677ff"
  primary-hover: "#4096ff"
  ink: "#1f2937"
  body: "#475569"
  muted: "#64748b"
  canvas: "#f5f7fa"
  surface: "#ffffff"
  surface-subtle: "#f8fafc"
  border: "#e2e8f0"
  border-strong: "#cbd5e1"
  success: "#15803d"
  warning: "#b45309"
  danger: "#b91c1c"
typography:
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "24px"
    fontWeight: 650
    lineHeight: 1.25
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  control: "6px"
  surface: "10px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.surface}"
    padding: "16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 11px"
---

# Design System: AIP Industrial Research Workbench

## 1. Overview

**Creative North Star: "The Evidence Bench"**

界面是一张持续工作的研究台，而不是展示型仪表盘。稳定的中性色承载高密度数据，蓝色只用于主操作、当前选择和运行中状态。层级主要依靠间距、边框、字号和内容顺序，而不是装饰性阴影或颜色块。

系统明确拒绝赛博 HUD、霓虹、紫色渐变、玻璃拟态、营销式大标题和同质卡片墙。

**Key Characteristics:**

- 任务顺序清楚：配置、运行、候选、复验、提升。
- 数据紧凑但保留可扫描间距。
- 证据状态同时使用文字、数字和有限的语义色。
- 桌面优先，窄屏结构化降级。
- 首屏只保留命令栏、实时进度、预测曲线、研究结论和工作区标签；完整配置进入抽屉。

## 2. Colors

冷中性背景配单一工业蓝强调，语义色只表达状态。

### Primary

- **Control Blue** (#1677ff)：主按钮、焦点、当前运行和选中状态。

### Neutral

- **Workbench Canvas** (#f5f7fa)：页面背景。
- **Instrument Surface** (#ffffff)：表单、表格和主要内容表面。
- **Quiet Surface** (#f8fafc)：次级分组和只读信息。
- **Primary Ink** (#1f2937)：标题和关键数据。
- **Body Slate** (#475569)：正文和说明。
- **Rule Line** (#e2e8f0)：边框与分隔线。

### Named Rules

**The One Accent Rule.** 蓝色是唯一视图强调色，不用紫色区分步骤，不用多色装饰卡片。

**The Evidence Color Rule.** 绿色、橙色和红色只表达已确认成功、风险或失败，不能装饰普通信息。

## 3. Typography

**Display Font:** system sans-serif
**Body Font:** system sans-serif
**Label/Mono Font:** Menlo, Monaco, Consolas, monospace

**Character:** 熟悉、精确、适合长时间读取。产品标签不使用展示字体。

### Hierarchy

- **Headline** (650, 24px, 1.25)：页面标题。
- **Title** (600, 15px, 1.4)：主要区块和卡片标题。
- **Body** (400, 14px, 1.6)：说明和业务正文，长文本控制在 75ch 内。
- **Label** (500, 12px, normal case)：字段、状态和辅助信息。
- **Data** (400/600, 12-14px)：数字使用 `tabular-nums`。

### Named Rules

**The Scan First Rule.** 标题短、说明具体；重要数字靠字重和对齐突出，不靠超大字号。

## 4. Elevation

系统以边框和背景层级为主，阴影只帮助悬浮层、抽屉或关键工作表面从画布中分离。普通嵌套分组不叠加阴影。

### Shadow Vocabulary

- **Surface Lift** (`0 1px 2px rgba(15, 23, 42, 0.04)`): 首层工作表面。
- **Overlay Lift** (`0 12px 32px rgba(15, 23, 42, 0.14)`): 弹窗、抽屉和浮层。

### Named Rules

**The Flat-By-Default Rule.** 同一表面内用分隔线和留白分组，不用卡片套卡片制造层级。

## 5. Components

### Buttons

- **Shape:** 6px 圆角。
- **Primary:** Control Blue 背景、白色文字，动词加对象。
- **Hover / Focus:** 使用 Ant Design 标准状态和清晰焦点环，反馈不超过 200ms。
- **Secondary / Ghost:** 白底或透明底，保留边框；危险操作使用明确文字。

### Chips

- **Style:** 低饱和背景、深色文字和完整状态名称。
- **State:** 只用于状态、筛选和短元数据，不承载长句。

### Cards / Containers

- **Corner Style:** 10px。
- **Background:** 白色主表面，#f8fafc 次级表面。
- **Shadow Strategy:** 首层轻阴影，内部区块无阴影。
- **Border:** 1px #e2e8f0。
- **Internal Padding:** 16px，紧凑表格区可降至 12px。

### Inputs / Fields

- **Style:** 标签位于输入上方，6px 圆角，白色背景。
- **Focus:** Control Blue 边框和 Ant Design 默认焦点环。
- **Error / Disabled:** 错误紧邻字段，禁用状态保留可读文字。

### Navigation

保留现有侧边导航。当前项使用单一蓝色；页面内部用阶段条和区块标题表达任务顺序，不再增加第二套复杂导航。

### Research Stage Rail

四阶段固定为：配置实验、观察运行、筛选候选、复验提升。当前阶段由运行状态和数据状态驱动，阶段说明保持一句话。

### Execution Progress

- 单组运行显示 Baseline 预热或当前窗口的完成数与百分比。
- 多组并行时，每组独立显示状态、阶段、当前窗口和百分比。
- 百分比只由后端完成窗口数计算；缺少分母时显示阶段状态，不估算虚假进度。
- 已结束 run 使用“最近执行进度 / 已结束”，不继续显示实时刷新。

### Forecast Comparison

- 主图同时表达实际值、Baseline/历史参考与 Challenger。
- 新 run 使用后端同窗 `baseline_predicted`，图例明确标为 Baseline。
- 历史 run 缺少真实 Baseline 序列时只能标为“首轮参考”，不能冒充 Baseline。
- Actual 使用深色实线，Baseline/参考使用灰色虚线，Challenger 使用蓝色实线。

## 6. Do's and Don'ts

### Do:

- **Do** 使用 24px 页面标题、15px 区块标题和 12-14px 数据字号。
- **Do** 用边框、留白和背景区分信息层级。
- **Do** 同时显示状态文字、进度和下一步动作。
- **Do** 把当前运行、曲线、结论和下一步动作放在首屏，把配置与历史运行放入抽屉。
- **Do** 在 1200px 以下把双栏布局折叠为单栏。

### Don't:

- **Don't** 使用营销落地页式的大标题、口号和装饰性区块。
- **Don't** 使用赛博 HUD、霓虹、紫色渐变、玻璃拟态或无意义动效。
- **Don't** 使用大面积渐变、彩色左边条或多种强调色区分普通步骤。
- **Don't** 用大量同质卡片把所有内容切碎。
- **Don't** 只靠颜色表达成功、失败、证据不足或未复验。
- **Don't** 隐藏失败、证据不足、未复验等关键风险。
