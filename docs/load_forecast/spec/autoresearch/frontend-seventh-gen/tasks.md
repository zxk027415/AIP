# AIP 第七代前端重构任务清单

## 当前状态

- 当前阶段：阶段 2/3/5 代码落地完成，阶段 1 视觉线卡在 image2 高保真。
- 当前目标：更新进度记录，补齐阶段 4（工作流新建向导），决定是否补做 image2 高保真。
- 本清单只覆盖第七代第一阶段和后续分期，不代表一次性全部实现。
- 最后更新：2026-07-01

## Definition of Done

- [ ] 左侧导航按第七代信息架构重构完成。
- [ ] 算法开发模块可进入算法管理默认首页。
- [ ] 算法管理页能按场景展示现有工作流和版本。
- [ ] 工作流新建入口支持推荐模板创建和空白创建。
- [ ] AutoResearch、算法运营、算法部署入口与算法管理打通。
- [ ] 旧路由保留可访问，不删除旧页面代码。
- [ ] 前端构建通过或记录明确失败原因。
- [ ] 桌面和移动端主要页面截图无明显遮挡、错位、文字溢出。

## 文件地图

| 文件/目录 | 动作 | 说明 |
|---|---|---|
| `frontend-sevice/src/components/MainLayout.tsx` | 修改 | 重构左侧导航 |
| `frontend-sevice/src/App.tsx` | 修改 | 增加 `/algorithm-dev/*` 路由 |
| `frontend-sevice/src/pages/AlgorithmManagementPage.tsx` | 新增 | 算法管理首页 |
| `frontend-sevice/src/pages/AlgorithmDeploymentPlaceholderPage.tsx` | 新增或复用 | 算法部署占位 |
| `frontend-sevice/src/services/workflowEnhancedApi.ts` | 读取/可能修改 | 工作流列表和版本数据来源 |
| `frontend-sevice/src/types/workflow-enhanced.ts` | 读取/可能修改 | 工作流元数据类型 |
| `frontend-sevice/src/i18n` 或相关语言文件 | 可能修改 | 导航命名，如需要国际化 |
| `docs/specs/frontend-seventh-gen/` | 新增 | 第七代需求、设计、任务、视觉流程 |
| `docs/specs/frontend-seventh-gen/image2-prompts.md` | 新增 | image2 高保真提示词 |
| `docs/specs/frontend-seventh-gen/design-spec-template.md` | 新增 | 设计规约模板 |
| `docs/specs/frontend-seventh-gen/review-checklist.md` | 新增 | 实现后 review 与验收清单 |

## 阶段 0：规划文档

- [x] 读取项目说明和现有前端重构文档。
- [x] 确认第七代目标和范围。
- [x] 编写 `requirements.md`。
- [x] 编写 `design.md`。
- [x] 编写 `tasks.md`。
- [x] 编写 `visual-workflow.md`。
- [x] 自审文档一致性。
- [x] 编写 `report.md`。

## 阶段 1：视觉原型

- [x] 基于 `visual-workflow.md` 准备 Stitch 提示词。
- [x] 产出 2-3 个中保真信息架构原型。
- [x] 选择一个主方向。
- [x] 补齐 image2 高保真输入提示词。
- [ ] 使用 image2 打磨高保真视觉稿。
- [ ] 从高保真稿提取设计规约。
- [ ] 明确桌面端和移动端验收截图目标。

## 阶段 2：导航和路由重构

- [x] 修改 `MainLayout.tsx`，隐藏 Agentic Service 默认导航。
- [x] 修改 `MainLayout.tsx`，保留行业服务分组。
- [x] 修改 `MainLayout.tsx`，新增算法开发分组。
- [x] 修改 `App.tsx`，增加 `/algorithm-dev` 新路由。
- [x] 保留旧路由可访问。
- [x] 检查导航选中态和页面标题。

## 阶段 3：算法管理首页 MVP

- [x] 新增 `AlgorithmManagementPage.tsx`。
- [x] 读取现有工作流列表数据。
- [x] 实现场景归类规则。
- [x] 展示工作流版本卡片或表格。
- [x] 增加编辑、自动化回测、算法运营、算法部署操作入口。
- [x] 增加空状态、加载状态和错误状态。

## 阶段 4：工作流新建入口

- [ ] 在算法管理页增加“新建算法工作流”按钮。
- [ ] 在工作流编排页增加或复用“新建工作流”入口。
- [ ] 实现创建向导：选择场景、推荐模板、空白创建。
- [ ] 基于推荐模板跳转工作流编辑器。
- [ ] 空白创建跳转工作流编辑器。

## 阶段 5：AutoResearch / 算法运营 / 部署打通

- [ ] 自动化回测入口携带 `workflow_id` 上下文。
- [ ] 算法运营入口携带工作流或槽位上下文。
- [ ] 新增或复用算法部署占位页。
- [ ] 在算法管理页标识候选、复验、Promote、生产等状态。

## 阶段 6：视觉实现和像素验收

- [ ] 根据设计规约调整算法管理页视觉。
- [ ] 根据设计规约调整左侧导航密度和选中态。
- [ ] 使用 Playwright 或浏览器截图检查 1440px 桌面视图。
- [ ] 使用 Playwright 或浏览器截图检查 390px 移动视图。
- [ ] 修复文字溢出、控件重叠、状态不清晰问题。

## 阶段 7：验证和交付

- [ ] 运行 `cd frontend-sevice && npm run build`。
- [ ] 记录构建结果和既有警告。
- [ ] 检查旧路由可访问。
- [ ] 检查新路由可访问。
- [ ] 更新落地文档。
- [ ] 更新展示汇报文档。

## 风险清单

- [ ] 工作流元数据缺少统一 `scenario_id`，需要前端兜底归类。
- [ ] 新旧路由并存可能导致页面标题和选中态复杂。
- [ ] AutoResearch 与算法管理的候选/复验状态暂未统一建模。
- [ ] 精度运营已有页面较复杂，第一阶段只改入口不改内部结构。
- [ ] 当前工作区很脏，实施时必须小补丁、逐文件检查。
