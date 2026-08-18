# AIP 第七代前端重构第一阶段落地说明

## 本阶段目标

第一阶段不直接重写正式业务逻辑，也不改后端接口协议。目标是先把第七代信息架构和可预览 demo 挂起来：

- 左侧导航切到第七代结构
- 新增 `/algorithm-dev/*` 前端路由层
- 算法管理页 demo 作为算法开发默认首页
- 行业场景详情页收敛成第七代入口风格
- 算法部署先放占位页

## 本阶段落地结果

### 1. 左侧导航

主导航现在按三组组织：

- 首页
- 行业服务
  - 行业场景
  - 算法方案库
  - 行业数据管理
- 算法开发
  - 算法管理
  - 工作流编排
  - 基础算法库
  - 自动化回测
  - 算法部署
  - 算法运营
- 系统

同时保留“旧入口”分组，方便兼容和回退。

### 2. 新前端路由

新增：

- `/algorithm-dev`
- `/algorithm-dev/management`
- `/algorithm-dev/workflows`
- `/algorithm-dev/workflow-editor`
- `/algorithm-dev/workflow-editor/:id`
- `/algorithm-dev/operators`
- `/algorithm-dev/autoresearch`
- `/algorithm-dev/ops`
- `/algorithm-dev/deployment`

这些是前端页面路由，不是后端 API 路由。

### 3. 页面关系

第一阶段遵循：

```text
左侧导航
  -> 新路由
    -> demo页 / 包装页 / 复用旧页面
      -> 现有后端接口
```

### 4. 已落地 demo

#### 算法管理页

- 新页面：`AlgorithmManagementPage`
- 默认路由：`/algorithm-dev/management`
- 数据来源：现有 `enhancedWorkflowApi.listWorkflowSummaries()`
- 前端按规则推断：
  - 场景
  - 版本号
  - 生命周期状态
  - 自动化回测状态

#### 算法部署页

- 新页面：`AlgorithmDeploymentPlaceholderPage`
- 路由：`/algorithm-dev/deployment`
- 作用：承接上下文，占位，不触发新部署后端逻辑

#### 行业场景详情页收敛版

- 仍使用现有 `/industry/:scenarioId`
- 视觉和动作入口收敛为第七代风格
- 主要按钮优先进入新算法开发路由

## 与旧页面 / 旧接口的关系

### 当前仍复用的旧页面能力

- `/algorithm-dev/workflows` -> 复用 `WorkflowListPage`
- `/algorithm-dev/workflow-editor` -> 复用 `WorkflowEditorPage`
- `/algorithm-dev/autoresearch` -> 复用 `WorkflowBaselineComparePage`
- `/algorithm-dev/ops` -> 复用 `PrecisionOpsDashboardPage`
- `/algorithm-dev/operators` -> 复用 `FunctionLibraryPage`

### 当前不改的内容

- 后端 API 地址
- 工作流执行协议
- AutoResearch 后端逻辑
- 精度运营后端逻辑
- 部署真实上线流程

## 你接下来预览时应该关注什么

### 先看结构，不急着看像素细节

重点看：

1. 左侧导航分组是否顺
2. 算法管理页是否像“总入口”
3. 行业场景页进入算法开发的动作链路是否合理
4. 新旧入口是否混乱
5. 哪些页面应该继续 demo 化，哪些已经可以转正式落地

### 第二阶段再做高保真收口

等 image2 定稿后，再继续：

- 算法管理页像素级收口
- 工作流编排入口页单独设计
- 行业场景详情页的高保真统一
- 新路由下旧页面包装层的视觉统一

## 构建验证

执行：

```bash
cd frontend-sevice
npm run build
```

结果：

- 构建通过
- 仍有项目既有 Tailwind 警告
- 仍有 Vite chunk 体积 warning
- 这些不是本阶段新增失败
