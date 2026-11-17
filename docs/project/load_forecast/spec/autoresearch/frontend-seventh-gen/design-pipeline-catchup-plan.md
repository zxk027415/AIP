# 第七代前端设计流水线补回计划

## 背景

第七代前端重构在代码层面已完成 MVP：导航重构、路由、算法管理首页、部署占位页。但设计流水线被跳过——没有 Design Intelligence、没有 Design System token、没有高保真定稿、没有 skill 质量约束参与。

当前代码视为**功能原型**，后续按设计流水线补回视觉质量。

## 依据

- 设计流水线标准流程：`docs/docs_zxk/frontend-design-workflow.md`
- Stitch 提示词：`docs/specs/frontend-seventh-gen/stitch-prompts.md`
- image2 提示词：`docs/specs/frontend-seventh-gen/image2-prompts.md`
- 设计规约模板：`docs/specs/frontend-seventh-gen/design-spec-template.md`
- 验收清单：`docs/specs/frontend-seventh-gen/review-checklist.md`

## Skill 工具位置

```
/Users/zxk/.agents/skills/
├── ui-ux-pro-max/scripts/search.py   # Design Intelligence 检索
├── impeccable/                        # 产品策略、IA、审计、收口
├── baseline-ui/                       # 可访问性、交互底线
├── taste-skill/                       # anti-slop 审美审查
├── frontend-design/                   # 视觉方向
├── stitch-skill/                      # 中保真原型
├── frontend-app-builder/              # 按稿实现
├── image-to-code-skill/               # 图到代码还原
```

## 需要走流水线的页面

| 页面 | 路由 | 当前状态 | 优先级 |
|------|------|------|------|
| 算法管理首页 | `/algorithm-dev/management` | 功能原型已实现，视觉待收口 | P0 |
| 左侧导航 | 全局 | 结构已对，密度/选中态/分层待打磨 | P0 |
| 新建工作流向导 | Modal/Drawer | 尚未实现 | P1 |
| 算法部署占位页 | `/algorithm-dev/deployment` | 简单占位，视觉跟随主页风格即可 | P2 |
| AutoResearch 衔接视图 | `/algorithm-dev/autoresearch` | 复用旧页面，暂不改 | P3 |

## 补回步骤

### Step 1: Design Read（固定设计判断）

在现有代码基础上重新明确设计参数：

```
设计判断：
这是面向算法工程师的工业算法生命周期管理工作台。
专业、克制、可信，信息密度高，强调版本状态和操作效率。

Design variance: 4/10
Motion intensity: 2/10
Visual density: 7/10
Register: product（不是 brand）
```

产物：写入 `DESIGN.md` 或本文件 §design-read 段落。

### Step 2: Design Intelligence（UI UX Pro Max）

运行检索，建立设计决策表：

```bash
cd /Users/zxk/.agents/skills/ui-ux-pro-max/scripts

# 整体设计系统候选
python3 search.py \
  "industrial algorithm lifecycle management console dashboard" \
  --design-system -p "AIP seventh-gen" -f markdown

# 产品模式
python3 search.py \
  "algorithm version management workflow status table dense" \
  --domain product -n 5

# 图表与数据表达
python3 search.py \
  "version status lifecycle tags table compact operations" \
  --domain chart -n 6

# UX 规则
python3 search.py \
  "dashboard tables forms loading accessibility responsive sidebar" \
  --domain ux -n 10

# React 实现建议
python3 search.py \
  "data dense table sidebar navigation ant design responsive" \
  --stack react
```

产物：设计候选 + 采纳/调整/拒绝决策表，写入本文件 §design-intelligence 段落。

### Step 3: Stitch 中保真验证

当前已有 stitch-prompts.md 和选定方向（A 平衡型 + B 强表格）。

**需要确认：** 是否已经在 Stitch 工具中实际生成过图？如果没有：
1. 用 `stitch-prompts.md` 中的方向 A 提示词生成中保真
2. 截图保存到 `docs/specs/frontend-seventh-gen/artifacts/stitch/`
3. 确认信息架构骨架无问题

如果之前外部生成过但没存仓库：找回图片存入上述目录。

产物：中保真原型截图（2-3 张）。

### Step 4: image2 高保真定稿

用 `image2-prompts.md` 中已准备的提示词，在 image2 工具中生成：

1. 算法管理首页 - 桌面端主视图
2. 算法管理首页 - 有数据 + 空状态
3. 新建工作流向导 - 步骤条
4. 左侧导航细节

产物：高保真截图保存到 `docs/specs/frontend-seventh-gen/artifacts/image2/`

### Step 5: 设计规约提取

基于 image2 定稿，按 `design-spec-template.md` 填写：

- 算法管理页设计规约
- 左侧导航设计规约
- 新建向导设计规约

重点提取：
- 间距（页面外边距、模块间距、表格行高）
- 字号（标题、正文、表格、标签）
- 色彩（主色、状态色、背景层级、边框色）
- 组件状态（hover/selected/empty/loading/disabled）
- 响应式断点行为

产物：填完的设计规约文档。

### Step 6: Codex + Skill 实现

按以下 skill 顺序执行：

1. **frontend-app-builder**：把高保真稿当 spec，禁止自由发挥
2. **frontend-design**：组件和布局细节落地
3. **image-to-code-skill**：对照图还原间距/色彩/字号
4. **baseline-ui**：可访问性、表单、响应式底线检查
5. **taste-skill**：anti-slop 最终审查（不套营销页规则）
6. **impeccable**：最终 audit + harden

实现范围：
- 修改 `AlgorithmManagementPage.tsx` 视觉
- 修改 `MainLayout.tsx` 导航密度和选中态
- 新增新建工作流向导组件
- 修改 `AlgorithmDeploymentPlaceholderPage.tsx` 跟随风格

### Step 7: 浏览器验收

1. `npm run build` 通过
2. 启动 dev server，桌面端 1440px 截图
3. 移动端 390px 截图
4. 对照 image2 定稿逐项检查：
   - 间距 ✓/✗
   - 字号 ✓/✗
   - 颜色 ✓/✗
   - 状态标签 ✓/✗
   - 边框/阴影 ✓/✗
   - 密度 ✓/✗
   - 换行/溢出 ✓/✗
5. 修复差异，循环直到通过

产物：实现截图 + 对照表 + 修复记录。

## 执行顺序和依赖

```
Step 1 (Design Read)          → 无外部依赖，立即可做
Step 2 (Design Intelligence)  → 需要 python3 + ui-ux-pro-max
Step 3 (Stitch)               → 需要 Stitch 工具（外部）
Step 4 (image2)               → 需要 image2 工具（外部），依赖 Step 3
Step 5 (Design Spec)          → 依赖 Step 4 产出
Step 6 (Implementation)       → 依赖 Step 5 产出
Step 7 (Verification)         → 依赖 Step 6 产出
```

**可以立即在本会话做的：** Step 1 和 Step 2。
**需要你在外部工具操作的：** Step 3 和 Step 4。
**需要定稿后再做的：** Step 5-7。

## 时间预估

| 步骤 | 估计 | 谁做 |
|------|------|------|
| Step 1-2 | 30 min | Agent（本会话可做） |
| Step 3 | 15-30 min | 用户在 Stitch |
| Step 4 | 30-60 min | 用户在 image2 |
| Step 5 | 20 min | Agent 基于图提取 |
| Step 6 | 2-3 h | Agent + Skill |
| Step 7 | 30-60 min | Agent + 用户确认 |

## 当前阻塞

无。Step 1-2 已完成，等待 image2 定稿图。

---

## §design-read 设计判断

```
产品定位：面向算法工程师的工业算法生命周期管理工作台。
设计气质：专业、克制、可信，信息密度高，强调版本状态和操作效率。
Register: product（不是 brand / marketing）

Design variance: 4/10（保守，不追求视觉创新）
Motion intensity: 2/10（只有状态反馈，无页面入场动画）
Visual density: 7/10（高密度但层级清晰）
```

---

## §design-intelligence 设计决策表

### 检索来源

- UI UX Pro Max design-system 检索
- UI UX Pro Max product domain 检索
- UI UX Pro Max UX guidelines 检索
- UI UX Pro Max React stack 检索

### 采纳

| 建议 | 来源 | 采纳理由 |
|------|------|------|
| Data-Dense Dashboard 模式 | design-system | 完全匹配：多表格、KPI 卡片、最小 padding、grid 布局 |
| Drill-Down Analytics + Comparative | product #5 | 算法管理就是比较版本状态、drill-down 到详情 |
| 背景色 `#F8FAFC`、前景 `#0F172A`、边框 `#E6E8EA` | design-system colors | 中性 slate 工业色，不花哨 |
| 表格 mobile 降级为卡片列表 | UX #1 | 已在图 5 提示词中采纳 |
| Loading > 300ms 必须有 skeleton/spinner | UX #7 #9 | 算法管理已有 Spin，后续检查是否达标 |
| Heading 层级 h1→h2→h3 | UX #4 | audit 时检查 |
| Container/Presentational 分离 | React #1 | 当前代码已基本做到（page 里 fetch，table 是展示） |
| 状态色：green(pass)/orange(candidate)/gray(default)/blue(ops-ready) | design-system | 已在代码里使用，与 Ant Design Tag 语义色一致 |

### 调整

| 建议 | 来源 | 调整方式 |
|------|------|------|
| 推荐色板 slate+green 作为主强调 | design-system | 不采用 green 作主色；保持项目现有 Ant Design 蓝色 `#1677ff` 作唯一强调色 |
| Fira Code / Fira Sans 字体 | design-system | 不引入新字体；保持 Ant Design 默认（系统字体栈），中文场景不适合 Fira |
| Soft UI / Glassmorphism 作为 secondary | product #1 | 拒绝 Glassmorphism，只在 hover 时使用微弱阴影 |
| Chart zoom on click / smooth filter animations | design-system effects | 只保留 row hover highlight + filter 收起动画，不加 chart zoom |

### 拒绝

| 建议 | 来源 | 拒绝理由 |
|------|------|------|
| Dark Mode (OLED) 默认 | product #2 #5 | 工业后台用户习惯浅色；暗色后续作为选项，不做默认 |
| Glassmorphism | product #1 | 与工程控制台气质冲突 |
| Cool→Hot 渐变色板 | product #5 | 热力渐变用于数据可视化场景；版本管理不需要 |
| Real-Time Monitoring | product #2 | 当前页面不是实时监控，是版本状态管理 |
| Skip Links | UX #3 | 当前项目无 screen reader 用户反馈，后续 P2 补 |

### Pre-Delivery Checklist（从 design-system 提取）

- [ ] 无 emoji 作为图标（使用 Ant Design 图标）
- [ ] 所有可点击元素有 cursor-pointer
- [ ] Hover 状态有 150-300ms 平滑过渡
- [ ] 文本对比度 ≥ 4.5:1
- [ ] 焦点状态可见（keyboard nav）
- [ ] prefers-reduced-motion 被尊重
- [ ] 响应式断点：375px / 768px / 1024px / 1440px
