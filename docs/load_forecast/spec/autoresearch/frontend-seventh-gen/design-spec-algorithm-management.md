# 算法管理页设计规约（基于 image2 定稿提取）

> 本文件是实现 spec，不是讨论文档。Codex/Agent 按此实现，不得自由发挥。

## 页面基本信息

- 页面名称：算法管理
- 路由：`/algorithm-dev/management`
- 页面目标：按行业场景管理算法工作流版本，连接编排、回测、运营和部署
- 面向用户：算法工程师、算法运维
- Register：product

---

## 全局色彩

| 角色 | 色值 | 用途 |
|------|------|------|
| Primary | `#1677ff` | 选中态、主按钮、链接 |
| Primary Hover | `#4096ff` | 按钮 hover |
| Primary BG | `#e6f7ff` | 导航选中背景、场景卡片选中背景 |
| Text Primary | `#1f1f1f` | 标题、表格正文 |
| Text Secondary | `#8c8c8c` | 描述、时间、ID |
| Text Placeholder | `#bfbfbf` | 输入框 placeholder |
| Background Page | `#f7f8fa` | 主内容区底色 |
| Background Card | `#ffffff` | 卡片、表格、Modal |
| Border | `#f0f0f0` | 卡片边框、分隔线、输入框边框 |
| Border Hover | `#d9d9d9` | 输入框 hover |
| Status Green | `#52c41a` | 开发中 dot |
| Status Blue | `#1677ff` | 待运营 dot |
| Status Orange | `#fa8c16` | 待部署 dot、候选中 tag |
| Status Green Tag | `#52c41a` | 已复验 tag |
| Status Gray Tag | `#d9d9d9` | 未回测 tag bg |
| Shadow Card | `0 1px 4px rgba(0,0,0,0.06)` | 指标条、表格卡片 |

---

## 全局字号

| 元素 | 字号 | 字重 | 颜色 |
|------|------|------|------|
| 页面标题 | 22px | 600 | Text Primary |
| 页面描述 | 13px | 400 | Text Secondary |
| 面包屑 | 13px | 400 | Text Secondary |
| 指标数字 | 24px | 600 | Text Primary |
| 指标标签 | 12px | 400 | Text Secondary |
| 表格表头 | 13px | 500 | Text Secondary |
| 表格正文 | 14px | 400 | Text Primary |
| 表格 ID | 12px | 400 (monospace) | Text Secondary |
| 表格描述 | 12px | 400 | Text Secondary |
| 按钮正文 | 13px | 400 | — |
| 导航菜单项 | 14px | 400 | Text Primary |
| 导航分组标题 | 11px | 400 | Text Secondary |
| Tag 文字 | 12px | 400 | — |

---

## 全局间距

| 位置 | 数值 |
|------|------|
| 主内容区 padding | 24px |
| 模块间垂直间距 | 16px |
| 指标条内 padding | 16px 24px |
| 指标项之间 | 竖线分隔，等分宽度 |
| 筛选栏内控件间距 | 12px |
| 表格行高 | ~64px（三行内容：名称+描述+ID） |
| 表格单元格水平 padding | 12px |
| 卡片圆角 | 8px |
| 按钮圆角 | 6px |
| Tag 圆角 | 4px |
| 导航项高度 | 40px |
| 导航项左缩进 | 24px（含图标） |
| 导航图标-文字间距 | 10px |

---

## 左侧导航

### 结构

```
工业AI平台 (header, 56px height, 15px semibold, centered, border-bottom)
─────────────
行业服务 (group label)
  行业场景
  算法方案库
  行业数据管理 (可展开 ›)

算法开发 (group label)
  算法管理 ← active
  工作流编排
  基础算法库
  自动化回测
  算法部署
  算法运营

系统 (group label)
  系统管理 (›)
  个人信息
  旧入口 (›)
─────────────
« 收起菜单 (bottom, 12px gray)
```

### 状态

| 状态 | 样式 |
|------|------|
| Default | text #262626, bg transparent |
| Hover | bg #f5f5f5 |
| Active/Selected | text #1677ff, bg #e6f7ff, left-border 3px solid #1677ff |
| Group label | 11px, #8c8c8c, margin-top 24px |
| Submenu arrow | › 小箭头右对齐 |

### 尺寸
- 宽度：~160-200px（从图看约 160px 内容区 + padding）
- 背景：white
- 右边框：1px solid #f0f0f0

---

## 页面头部

### 面包屑行
- 内容：`算法开发 / 算法管理`
- 字号：13px，颜色 #8c8c8c
- margin-bottom: 8px

### 标题行
- 左侧：`算法管理` 22px semibold
- 下方：`管理工作流版本的开发、回测和部署状态` 13px #8c8c8c
- 右侧（与标题垂直居中）：主按钮 `+ 新建算法工作流`
  - 样式：Ant Design primary button, medium size
  - 图标：PlusOutlined
- margin-bottom: 16px

---

## 指标条

### 布局
- 一个白色卡片条，4 个指标等分，竖线分隔
- 卡片高度：~72px
- 圆角：8px
- 阴影：card shadow
- 每个指标：数字 24px semibold 上方，标签 12px #8c8c8c 下方
- 指标内容：`行业场景 12` | `工作流 86` | `开发版本 243` | `待运营/待部署 18`
- 每个指标区域有一个小图标在右侧（monochrome blue，opacity 0.6）

### 响应式
- 窄屏可改为 2×2

---

## 筛选栏

### 布局
- 与表格在同一白色卡片内，位于表头上方
- 一行：搜索框 + 所属场景 dropdown + 生命周期 dropdown + 右对齐"重置"文字链接
- 控件高度：32px
- 搜索框宽度：~280px，placeholder `搜索算法名称或ID`
- Dropdown 宽度：~140px
- margin-bottom: 0（紧贴表头）

---

## 主表格

### 卡片容器
- 白色背景，圆角 8px，阴影 card shadow
- 内含筛选栏 + 表格 + 分页

### 表格列

| 列 | 宽度占比 | 内容 |
|------|------|------|
| 算法资产 | ~35% | 三行：名称(14px medium,蓝色链接) + 版本 tag + 描述(12px gray) + ID(12px monospace gray) |
| 所属场景 | ~10% | 纯文字，14px，如"负荷预测"、"光伏故障" |
| 生命周期 | ~10% | 小圆点(6px) + 文字(13px)："● 开发中"、"● 待运营"、"● 待部署" |
| 自动化回测 | ~10% | Ant Tag：`未回测`(gray) / `候选中`(orange) / `已复验`(green) |
| 更新时间 | ~15% | 13px gray: `2026-06-28 14:32` |
| 操作 | ~20% | 2 个 ghost 按钮 `编排` `回测` + 1 个 `⋯` more dropdown (含：算法运营、算法部署) |

### 行为
- 行高：~64px
- Hover：行背景 #fafbfc
- 名称列点击：跳转 `/algorithm-dev/workflow-editor/:id`
- 分页：底部右对齐，`共 86 条` + 页码 + 每页条数选择

### 生命周期圆点颜色

| 状态 | 圆点颜色 | 文字 |
|------|------|------|
| 开发中 | #52c41a (green) | 开发中 |
| 待运营 | #1677ff (blue) | 待运营 |
| 待部署 | #fa8c16 (orange) | 待部署 |

### 自动化回测 Tag

| 状态 | Tag 样式 |
|------|------|
| 未回测 | Ant Tag default (gray border, gray text) |
| 候选中 | Ant Tag color="orange" |
| 已复验 | Ant Tag color="green" |

---

## 空状态（图 2）

当表格数据为空时，表格区域替换为居中空态：

- 插图：Ant Design 风格线描文件/信封图标（约 80px 高）
- 主文字：`暂无算法工作流` 16px semibold
- 副文字：`从行业场景选择推荐模板开始，或直接创建空白工作流` 13px gray
- CTA 1：`+ 新建算法工作流` primary button
- CTA 2：`浏览行业场景推荐 →` 蓝色文字链接
- 垂直居中在表格卡片区域
- 指标条显示全 0
- 筛选栏仍可见但可置灰

---

## 新建工作流向导（图 4）

### 触发
- 点击 `+ 新建算法工作流` 按钮

### 容器
- Ant Design Modal，居中
- 宽度：~640px
- 圆角：12px
- 背景 dimmer：rgba(0,0,0,0.45)

### Modal 头部
- 标题：`新建算法工作流` 18px semibold
- 关闭按钮：× 右上角
- 步骤条（Ant Steps）：
  - Step 1 `选择场景` (active, blue circle with "1")
  - Step 2 `选择模板` (gray)
  - Step 3 `开始创建` (gray)

### Step 1 内容
- 指引文字：`选择业务场景，系统将推荐适用的算法模板` 14px gray
- 场景卡片网格：2 列 × 3 行
- 每张卡片：
  - 尺寸：~280px × 64px
  - 左侧：行业图标（单色线描，32px）
  - 右侧：场景名(14px medium) + 一行描述(12px gray)
  - 边框：1px solid #e8e8e8
  - 圆角：8px
  - 选中态：border 2px #1677ff, bg #f0f7ff, 右上角蓝色 ✓ badge
  - Hover：border #d9d9d9, 微阴影

### 场景列表

| 场景 | 描述 |
|------|------|
| 新能源预测 | 面向光伏、风电等新能源出力预测 |
| 火电设备诊断 | 锅炉、汽机等关键设备异常识别 |
| 储能运营 | 储能调度与运行优化分析 |
| 电网调度 | 负荷预测与调度策略辅助 |
| 碳管理 | 碳排监测、核算与减排优化 |
| 园区能效 | 园区综合能源效率分析与优化 |

### Modal 底栏
- 左：`取消` 默认按钮
- 右：`下一步` primary 按钮（场景未选时 disabled）
- 中间偏左：`跳过场景选择，直接空白创建 →` 13px gray 文字链接

---

## 操作列 More Dropdown

- 触发：点击 `⋯` 按钮
- 下拉菜单项：
  - 算法运营
  - 算法部署
- 样式：Ant Dropdown，白色卡片，圆角 6px，阴影

---

## 组件清单

| 组件 | Ant Design 对应 | 备注 |
|------|------|------|
| 主表格 | `Table` | rowKey="id", scroll.x 支持 |
| 指标条 | `Statistic` in `Card` | 4 个等分 |
| 筛选搜索 | `Input` prefix SearchOutlined | 32px height |
| 筛选下拉 | `Select` | 32px height |
| 状态 Tag | `Tag` | color prop |
| 生命周期圆点 | 自定义 CSS dot + text | 6px border-radius 50% |
| 主按钮 | `Button type="primary"` | icon PlusOutlined |
| 操作按钮 | `Button size="small"` | ghost/default |
| More 下拉 | `Dropdown` + `Button` icon MoreOutlined | — |
| 新建 Modal | `Modal` | width 640 |
| 步骤条 | `Steps` | size default |
| 场景卡片 | 自定义 div | Radio.Group 语义包裹 |
| 空态 | `Empty` 自定义 | — |
| 分页 | `Table` 内置 pagination | showTotal, showSizeChanger |
| 面包屑 | `Breadcrumb` | — |

---

## 不做

- 不做移动端适配（本阶段）
- 不做暗色模式
- 不做页面入场动画
- 不做骨架屏（用 Spin 即可）
- 不做表格行拖拽排序
- 不做表格列自定义显隐
- 不改后端 API

---

## 实现验收对照

实现完成后，逐项对照：

- [ ] 导航选中态：蓝色文字 + #e6f7ff 背景 + 左蓝条
- [ ] 导航分组标题 11px gray
- [ ] 面包屑 13px gray
- [ ] 页面标题 22px semibold
- [ ] 指标条：一卡四项、竖线分隔、数字 24px
- [ ] 筛选栏在表格卡片内
- [ ] 表格列顺序和宽度比
- [ ] 算法资产列三行布局
- [ ] 生命周期列：圆点 + 文字（非 Tag）
- [ ] 自动化回测列：Ant Tag 带 color
- [ ] 操作列：2 按钮 + ⋯ dropdown
- [ ] 空状态：插图 + 文字 + 双 CTA
- [ ] 新建 Modal：Steps + 场景卡片网格 + 选中态蓝边
- [ ] 主按钮样式一致（primary blue, + icon）
- [ ] 页面背景 #f7f8fa，卡片白色
- [ ] 无嵌套卡片、无渐变、无装饰
