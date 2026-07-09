# AIP 前端设计工作流

## 目标

把多个前端设计 skill 组合成一条可重复、可审查的产品界面流程。每个 skill 只承担它擅长的阶段，避免规则互相冲突。

## Skill 分工

| Skill | 角色 | 在 AIP 中的用法 |
|---|---|---|
| CodeGraph | 代码结构与影响分析 | 先定位页面、依赖、调用和影响范围 |
| Impeccable | 产品策略、信息架构、设计系统、完整状态 | 主流程，负责 PRODUCT/DESIGN、audit、polish、harden |
| UI UX Pro Max | 设计智能检索与方案证据 | 查询产品模式、风格、配色、字体、图表、UX 和 React 实现规则，形成可比较的设计候选 |
| Baseline UI | 工程底线 | 检查可访问性、表单、动效、响应式和交互状态 |
| Taste Skill | 反模板化审美审查 | 只借用 anti-slop 检查，不套用其营销页布局规则 |
| Frontend Design | 视觉方向 | 用于确定有辨识度但符合业务的视觉语言 |

## Skill 协作关系

这几个 Skill 不是投票关系，而是一条有先后顺序的决策链：

1. **CodeGraph 回答“现在有什么，改动会影响什么”。**
2. **Impeccable 回答“为谁设计，用户要完成什么任务”。**
3. **UI UX Pro Max 回答“有哪些成熟模式、风格和图表可选”。**
4. **Frontend Design 回答“如何形成清晰、有辨识度的视觉方向”。**
5. **Taste Skill 回答“是否又落入常见 AI 模板”。**
6. **Baseline UI 回答“是否达到可访问、可交互、可交付底线”。**

UI UX Pro Max 的输出是**设计候选和检查证据**，不是最终决策。所有建议必须经过产品任务、现有 Ant Design、数据语义和可访问性筛选。

## 标准流程

### 1. Context

- 用 CodeGraph 读取入口组件、路由、API、类型和影响范围。
- 检查 Git 状态，区分用户已有改动和本次改动。
- 读取 `PRODUCT.md`、`DESIGN.md` 和现有组件库。
- 明确页面属于 `product` 还是 `brand` register。

产物：改动范围、约束、风险。

### 2. Design Read

用一句话固定设计判断：

> 这是面向算法工程师的工业研究工作台，专业、克制、可信，信息密度高，强调实验进度、证据和决策。

设置三个工作参数：

- Design variance: 4/10
- Motion intensity: 2/10
- Visual density: 7/10

### 3. Design Intelligence

每个新页面或明显重构，在画页面前先运行 UI UX Pro Max。

#### 3.1 生成整体设计系统候选

```bash
python3 /Users/zxk/Desktop/skills/ui-ux-pro-max/scripts/search.py \
  "industrial AI experimentation research analytics dashboard" \
  --design-system -p "AIP AutoResearch" -f markdown
```

重点读取：

- `Pattern`：页面属于仪表盘、工作台、控制台还是营销页。
- `Style`：数据密度、视觉模式和适用场景。
- `Colors`：候选色彩角色，不直接复制颜色值。
- `Typography`：字体气质和数据阅读适配性。
- `Avoid`：该模式下的反模式。
- `Pre-Delivery Checklist`：交付检查项。

#### 3.2 按不确定项深入查询

```bash
# 产品和仪表盘模式
python3 /Users/zxk/Desktop/skills/ui-ux-pro-max/scripts/search.py \
  "industrial AI experimentation research analytics dashboard" \
  --domain product -n 5

# 图表与数据表达
python3 /Users/zxk/Desktop/skills/ui-ux-pro-max/scripts/search.py \
  "experiment progress evidence comparison candidate verification" \
  --domain chart -n 6

# 可访问性、表单、加载和响应式规则
python3 /Users/zxk/Desktop/skills/ui-ux-pro-max/scripts/search.py \
  "dashboard forms tables loading accessibility responsive" \
  --domain ux -n 10

# React 实现建议
python3 /Users/zxk/Desktop/skills/ui-ux-pro-max/scripts/search.py \
  "data dense dashboard responsive forms tables accessibility" \
  --stack react
```

#### 3.3 建立设计决策表

每条重要建议必须归入以下一种：

| 处理 | 含义 | AutoResearch 示例 |
|---|---|---|
| 采纳 | 与产品任务和现有技术栈一致 | `Data-Dense Dashboard`、Comparative、时间趋势折线图 |
| 调整 | 原则正确，但表现形式需要收敛 | 冷色数据配色调整为现有 Ant Design 蓝色体系 |
| 拒绝 | 与产品任务、证据语义或项目约束冲突 | AI Landing、OLED 暗色默认、玻璃拟态、雷达图作为精确比较主图 |

当前 AutoResearch 的检索结论：

- 采纳：`Analytics Dashboard`、`Data-Dense`、`Drill-Down Analytics + Comparative`。
- 采纳：运行趋势使用折线图，候选精确比较优先条形图或表格。
- 调整：推荐色板只作为角色参考，保持项目现有单一蓝色强调。
- 拒绝：营销 Landing 结构、默认暗色 OLED、装饰性热力渐变。
- 拒绝：需要精确数值比较时使用雷达图；雷达图最多只能作为次级探索视图。

产物：设计候选、采纳/调整/拒绝记录、图表选择依据。

### 4. Information Architecture

先画任务顺序，再画页面：

1. 配置实验
2. 观察运行
3. 筛选候选
4. 复验并提升

AutoResearch 页面采用渐进披露：

- 顶部命令栏保留运行身份、总进度、配置入口和启动/停止动作。
- 配置表单与历史 run 放入抽屉，避免与研究结果竞争首屏注意力。
- 主视图只保留预测曲线、研究结论和候选/复验/日志工作区。
- 深度控制台作为“高级诊断”按需显示。

每个区块必须回答：

- 用户为什么现在需要看它？
- 最重要的一个动作是什么？
- 空、加载、失败和只读状态是什么？
- 是否能延后到折叠、抽屉或详情页？

### 5. Design System

- 复用现有 Ant Design，不混入第二套组件库。
- 将 UI UX Pro Max 推荐的颜色、字体和风格转换成项目现有 token，不在组件里散落原始色值。
- 使用一个强调色和完整语义色。
- 固定字号、间距、圆角、边框和阴影词汇。
- 表格数字使用 tabular numerals。
- 卡片只表达真实层级，禁止无意义嵌套。
- 图表必须同时考虑精确读取、无障碍替代和原始数据表。
- 预测对比必须使用真实同窗 Baseline；历史数据缺字段时明确标记为参考序列。

产物：`DESIGN.md` 和页面级 CSS。

### 6. Implementation

- 先改结构和语义，再改视觉细节。
- 保持 API、状态和业务逻辑不变，除非需求明确要求。
- 标准控件保留标准行为，不手写键盘或焦点逻辑。
- 动效只表达状态，默认不添加页面入场动画。
- 使用 UI UX Pro Max 的 React 规则检查容器/展示职责、表单状态和长列表性能，但优先保持项目现有实现模式。

### 7. Audit

按固定顺序检查：

1. 任务顺序和主操作是否清楚。
2. 1440px、1024px、768px、375px 是否可用。
3. 加载、空、失败、禁用、运行中状态是否完整。
4. 文本和控件对比度是否达到 WCAG AA。
5. 危险操作是否有确认，图标按钮是否有可访问名称。
6. 是否出现渐变文字、玻璃拟态、彩色边条、emoji 图标、同质卡片墙。
7. UI UX Pro Max 的优先级检查是否通过：Accessibility → Interaction → Performance → Style → Layout → Typography → Animation → Forms → Navigation → Charts。
8. 图表是否有可见数值、图例、非颜色区分和表格替代。

### 8. Verification

- 运行 `npm run build`。
- 在真实浏览器打开目标路由。
- 验收首屏、运行中、空候选、候选详情和窄屏布局。
- 对照截图检查视觉层级，而不只检查 DOM。
- 对照 UI UX Pro Max 的 `Pre-Delivery Checklist` 逐项复核。

### 9. Delivery

交付必须包含：

- 结论和页面定位。
- 实际改动文件。
- 构建与浏览器验证结果。
- 未验证状态和原因。
- 需要重启或刷新才能生效的说明。

## 冲突处理

规则冲突时按以下优先级：

1. 业务正确性和证据边界
2. 可访问性和标准交互
3. 现有项目设计系统
4. 产品信息架构
5. UI UX Pro Max 检索出的成熟模式
6. 视觉辨识度
7. 装饰和动效

例如：Frontend Design 鼓励强视觉表现，但 AutoResearch 是高密度产品工作台，因此采用“明确视觉方向”，不采用大字号展示字体、非对称营销布局和大面积动效。

另一个例子：UI UX Pro Max 可能根据关键词返回 Dark Mode、Glassmorphism 或 AI Landing。它们只是数据库匹配结果；当它们与 `PRODUCT.md`、现有 Ant Design 和用户任务冲突时，应明确记录为“拒绝”，而不是为了使用 Skill 强行套用。
