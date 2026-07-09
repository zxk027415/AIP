# AIP 第七代前端重构设计文档

## 设计目标

第七代前端重构将 AIP 从“功能菜单集合”调整为“算法生命周期工作台”。设计重点是信息架构、导航归并、算法管理首页、工作流创建路径，以及 AutoResearch/精度运营/部署入口的串联。

## 总体架构

```text
MainLayout
  ├─ 首页
  ├─ 行业服务
  │   ├─ 行业场景
  │   ├─ 算法方案库
  │   └─ 行业数据管理
  ├─ 算法开发
  │   ├─ 算法管理
  │   ├─ 工作流编排
  │   ├─ 基础算法库
  │   ├─ 自动化回测
  │   ├─ 算法部署
  │   └─ 算法运营
  └─ 系统
```

## 路由设计

### 新路由

| 路由 | 页面 | 说明 |
|---|---|---|
| `/algorithm-dev` | redirect | 重定向到算法管理 |
| `/algorithm-dev/management` | `AlgorithmManagementPage` | 算法开发默认首页 |
| `/algorithm-dev/workflows` | 复用或包装 `WorkflowListPage` | 工作流列表/编排入口 |
| `/algorithm-dev/workflow-editor` | 复用 `WorkflowEditorPage` | 新建工作流 |
| `/algorithm-dev/workflow-editor/:id` | 复用 `WorkflowEditorPage` | 编辑工作流 |
| `/algorithm-dev/operators` | 复用 `FunctionLibraryPage` | 基础算法库 |
| `/algorithm-dev/autoresearch` | 复用 `WorkflowBaselineComparePage` | 自动化回测 |
| `/algorithm-dev/deployment` | 新增占位页或复用部署页 | 算法部署 |
| `/algorithm-dev/ops` | 复用 `PrecisionOpsDashboardPage` | 算法运营 |

### 旧路由兼容

第一阶段建议旧路由继续可访问，不立即重定向，降低风险。导航只指向新路由或新模块下的包装路由。

| 旧路由 | 处理 |
|---|---|
| `/functions` | 保留，后续可重定向到 `/algorithm-dev/operators` |
| `/workflow/list` | 保留，后续可重定向到 `/algorithm-dev/workflows` |
| `/workflow/editor` | 保留 |
| `/workflow/baseline-compare` | 保留 |
| `/precision-ops` | 保留 |
| `/deployment` | 保留 |
| `/algorithm-agent` 等 Agentic Service | 路由保留，默认导航隐藏 |

## 导航设计

### 行业服务

保留现有业务入口：

- 行业场景：`/industry`
- 算法方案库：`/algorithm-solutions`
- 行业数据管理：
  - 数据源管理：`/data-sources`
  - 数据集管理：`/datasets`
  - 人工标注审核：`/iterative-labeling`

### 算法开发

新增主模块：

- 算法管理：`/algorithm-dev/management`
- 工作流编排：`/algorithm-dev/workflows`
- 基础算法库：`/algorithm-dev/operators`
- 自动化回测：`/algorithm-dev/autoresearch`
- 算法部署：`/algorithm-dev/deployment`
- 算法运营：`/algorithm-dev/ops`

## 页面设计

### 算法管理页

算法管理页是第七代的核心新增页面，负责把分散的工作流、回测、运营、部署入口聚合到“场景-算法-版本”视图。

#### 页面结构

```text
顶部操作区
  ├─ 场景筛选
  ├─ 搜索
  ├─ 状态筛选
  └─ 新建算法工作流

统计区
  ├─ 场景数
  ├─ 工作流数
  ├─ 开发版本数
  ├─ 已运营版本数
  └─ 待部署版本数

主体区
  ├─ 场景分组卡片/表格
  │   ├─ 算法工作流名称
  │   ├─ 开发 v1/v2/v3
  │   ├─ 最近回测结果
  │   ├─ 复验状态
  │   ├─ 运营状态
  │   └─ 操作：编辑/回测/运营/部署
```

#### 数据来源

第一阶段优先读取现有工作流列表能力：

- 增强工作流 API 或工作流 API。
- `data/workflows_enhanced/` 中的模板元数据。
- 通过 `scenario_id`、`industry`、`tags`、`workflow_id` 命名规则做场景归类。

若字段不足，前端使用兜底规则：

```text
workflow_id/name 包含 load-forecast -> 负荷预测
workflow_id/name 包含 pv-fault -> 光伏故障诊断
tags/metadata 命中行业场景 -> 对应场景
否则 -> 未分类
```

### 工作流编排页

第一阶段不重写编辑器，重点是新建入口。

```text
新建工作流
  ├─ 选择行业场景
  ├─ 推荐模板列表
  ├─ 基于模板创建
  └─ 空白创建
```

推荐模板第一阶段使用规则匹配，后续可接入 AI 推荐或 AutoResearch 历史表现。

### 自动化回测页

底层复用现有 `WorkflowBaselineComparePage`。第七代重点是入口上下文：

- 从算法管理页进入时传递 `workflow_id`。
- 从工作流编辑器进入时传递当前工作流。
- 后续在 AutoResearch run 结果中回写候选版本关系。

### 算法运营页

底层复用现有 `PrecisionOpsDashboardPage`。第七代仅改入口和命名：

- 左侧显示为“算法运营”。
- 新路由为 `/algorithm-dev/ops`。
- 旧 `/precision-ops` 保留。

### 算法部署页

第一阶段为占位页，不实现真实部署：

```text
算法部署
  ├─ 当前选择的工作流/版本
  ├─ 部署能力建设中
  ├─ 后续支持：预上线、灰度、回滚、生产登记
  └─ 返回算法管理
```

## 数据流设计

### 算法开发闭环

```text
行业场景
  -> 推荐模板
  -> 工作流编辑器
  -> 保存为开发版本
  -> 算法管理展示
  -> 自动化回测
  -> 候选/复验/Promote
  -> 算法运营
  -> 算法部署
```

### 工作流版本同步

第一阶段不引入新后端模型，算法管理页作为聚合视图：

```text
工作流列表 API / workflows_enhanced JSON
  -> 前端归类
  -> 场景分组
  -> 版本展示
```

后续可演进为后端统一算法资产模型：

```text
AlgorithmAsset
  ├─ scenario_id
  ├─ algorithm_family
  ├─ workflow_id
  ├─ version_tag
  ├─ lifecycle_status
  ├─ autoresearch_source
  ├─ precision_slot
  └─ deployment_status
```

## 视觉设计方向

第七代视觉应采用“工业算法控制台”方向：

- 信息密度高，但层级清楚。
- 页面主体以表格、分组、状态标签、操作按钮为主。
- 使用 Ant Design 组件语义，不做过度装饰。
- 卡片用于场景分组和版本条目，不做页面级套卡片。
- 避免大面积渐变、营销式 hero、过度圆角和一色系视觉。
- 左侧导航保持克制、稳定、高频可扫读。

### 中保真原型结论

当前中保真原型阶段已对 3 个方向做了探索：

- A：平衡型控制台
- B：强表格型工作台
- C：场景驱动型工作台

当前选择：

```text
以 A 为主方向，吸收 B 的高密度版本表格能力
```

原因：

- 与现有 Ant Design 页面结构兼容性最高。
- 能先落算法管理 MVP，再逐步提高密度。
- 保留场景分组能力，适合未来扩展更多行业场景。
- 不会像纯表格工作台那样一上来就把页面做得过重。

对应原型细化结果：

- 算法管理页采用“顶部筛选 + 统计区 + 场景分组 + 紧凑版本表格”。
- 每个场景分组内使用紧凑表格展示算法工作流和开发 v1/v2/v3。
- 新建工作流采用 4 步向导：选择场景 -> 选择推荐模板 -> 选择创建方式 -> 进入编辑器。

## 响应式规则

- 桌面端优先支持 1440px 宽度。
- 窄屏下左侧导航继续使用现有 Drawer 模式。
- 算法管理页在移动端应优先展示搜索、场景筛选和版本列表，不强制展示全部列。
- 表格列需要支持省略、Tooltip 或折叠详情，避免文字溢出。

## 兼容策略

- 第一阶段只新增入口和聚合页，不删除旧代码。
- 旧路由继续可访问。
- 若新页面数据不足，显示空状态和“去工作流编排创建”入口。
- 若后端字段缺失，前端使用兜底归类并明确显示“未分类”。

## 验证策略

- 前端构建：`cd frontend-sevice && npm run build`。
- 视觉验收：使用 Playwright 或浏览器截图检查桌面和移动端。
- 路由验收：访问新旧路由，确认无 404。
- 功能验收：从算法管理进入编辑、自动化回测、算法运营、部署占位。
