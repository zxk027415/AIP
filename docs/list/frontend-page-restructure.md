# 前端页面功能分拆与重构方案

> 目标：用户从行业场景出发 → 逐步深入到算法模板 → 基础计算模块
> 每个模块可单独使用，也可通过算法模板组装使用
> 基于当前架构分析 + algorithm-library-split.md（721基础 + 291模板）

---

## 一、当前页面清单与问题分析

### 现有页面（14 个）

| 页面 | 路由 | 定位 | 状态 |
|------|------|------|------|
| HomePage | /home | 平台首页/仪表盘 | ✅ 正常 |
| FunctionLibraryPage | /functions | AI算法库浏览 | ✅ 正常（仅6分类36函数） |
| AlgorithmKnowledgeGraphPage | /knowledge-graph | 算法知识图谱 | ✅ 正常 |
| WorkflowEditorPage | /workflow/editor | 模板编辑器 | ✅ 核心功能 |
| WorkflowListPage | /workflow/list | 我的模板列表 | ✅ 正常 |
| TemplateGalleryPage | /templates | 算法模板库 | ⚠️ 仅3个模板，无行业分类 |
| SystemStatusPage | /system-status | 系统状态监控 | ✅ 正常 |
| ArchitecturePage | /architecture | 开发架构图 | ✅ 开发用 |
| SettingsPage | /settings | 系统配置 | ✅ 正常 |
| AlgorithmDbTestPage | /algorithm-db-test | 功能测试 | ✅ 开发用 |
| ProfilePage | /profile | 个人信息 | ✅ 正常 |
| DifyReplicaPage | /dify-replica | Dify风格测试 | 🔧 实验性 |
| WorkflowReferencePage | /workflow-reference | 模板参考 | 🔧 实验性 |
| WorkflowV2Page | /workflow-v2 | 模板V2测试 | 🔧 实验性 |

### 核心问题

1. **缺少行业入口**：用户无法从行业场景出发，只能从技术分类浏览算法
2. **模板系统薄弱**：仅3个通用模板，无行业场景分类，无场景→模板的引导
3. **导航扁平**：所有页面平铺在侧边栏，无"行业→模板→模块"的层级引导
4. **实验页面混杂**：DifyReplica/WorkflowReference/WorkflowV2 混在正式导航中

---

## 二、重构后页面架构（推荐方案）

### 页面总览

```
用户旅程：行业场景 → 场景详情 → 模板编排 → 基础模块

┌─────────────────────────────────────────────────────┐
│                    首页 (HomePage)                    │
│  平台概览 + 行业场景入口卡片 + 快速导航 + 统计数据    │
└──────────┬──────────────────────────────┬────────────┘
           │                              │
           ▼                              ▼
┌────────────────────
──┐  ┌──────────────────────┐
│  行业场景总览页(新)    │  │   基础算法库(已有)     │
│  IndustryOverviewPage  │  │   FunctionLibraryPage  │
│  14个行业场景卡片      │  │   721个基础模块        │
│  按行业标签筛选        │  │   18个技术分类         │
└──────────┬─────────────┘  └──────────┬─────────────┘
           │                           │
           ▼                           │ 可单独使用
┌──────────────────────┐               │
│  场景详情页(新)       │               │
│  IndustryScenarioPage│               │
│  场景描述+推荐模板    │               │
│  相关模板+基础模块    │               │
└──────────┬───────────┘               │
           │                           │
           ▼                           ▼
┌──────────────────────┐  ┌──────────────────────┐
│  模板编辑器(已有)     │←→│  模块执行器(已有)     │
│  WorkflowEditorPage  │  │  FunctionExecutor    │
│  拖拽编排+执行        │  │  单函数测试执行       │
└──────────────────────┘  └──────────────────────┘
```

### 新增页面清单

| 序号 | 页面 | 路由 | 功能 |
|------|------|------|------|
| 1 | IndustryOverviewPage | /industry | 行业场景总览，14个场景卡片 |
| 2 | IndustryScenarioPage | /industry/:scenarioId | 场景详情，展示该场景下的模板函数+推荐算法模板 |

### 改造页面清单

| 页面 | 改造内容 |
|------|---------|
| HomePage | 增加行业场景入口区域，替换现有"应用场景"静态文字 |
| FunctionLibraryPage | 增加"层级"标签筛选（6层），支持从场景页跳转并高亮 |
| TemplateGalleryPage | 增加行业场景分类筛选，与IndustryScenarioPage联动 |
| MainLayout | 重构导航菜单，增加"行业场景"一级入口 |

---

## 三、重构后导航菜单结构

### 新导航（左侧边栏）

```
工业AI算法平台
├── 🏠 首页                          /home
├── 🏭 行业场景（新）                  /industry
│   └── 场景详情（动态路由）           /industry/:scenarioId
├── 🧩 基础算法库                     /functions
│   └── 算法知识图谱                  /knowledge-graph
├── ⚡ 算法模板
│   ├── 模板编辑器                    /workflow/editor
│   ├── 我的模板                      /workflow/list
│   └── 模板库                       /templates
├── 📊 系统管理
│   ├── 系统状态                     /system-status
│   └── 系统配置                     /settings
└── 👤 个人信息                       /profile
```

### 导航变更说明

| 变更 | 说明 |
|------|------|
| 新增"行业场景" | 一级菜单，排在首页之后，作为核心入口 |
| "AI算法库"改为"基础算法库" | 明确定位为基础模块，与行业模板区分 |
| 知识图谱归入算法库子菜单 | 逻辑上属于算法库的可视化视图 |
| 新增"系统管理"分组 | 系统状态+系统配置合并为一组 |
| 移除实验性页面 | DifyReplica/WorkflowReference/WorkflowV2 从导航移除（路由保留，开发用） |
| 移除"功能测试" | 从正式导航移除（路由保留，开发用） |
| 移除"开发架构" | 从正式导航移除（路由保留，开发用） |

---

## 四、新增页面详细设计

### 4.1 行业场景总览页 (IndustryOverviewPage)

**路由**: `/industry`
**定位**: 用户进入平台后的核心入口，从行业视角浏览可用的AI解决方案

**页面结构**:

```
┌─────────────────────────────────────────────────┐
│  页面标题：行业AI解决方案                         │
│  副标题：从行业场景出发，快速构建AI应用            │
├─────────────────────────────────────────────────┤
│  行业标签筛选栏：                                │
│  [全部] [新能源] [工业制造] [源网荷储]            │
│  [碳管理] [楼宇园区] [港口运输] [通用工业]        │
├─────────────────────────────────────────────────┤
│  场景卡片网格（3~4列）：                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ 🔆 新能源 │ │ 🔋 储能   │ │ ⚡ 电网   │        │
│  │ 发电      │ │ 管理     │ │ 与微网    │        │
│  │ 模板: 24  │ │ 模板: 18 │ │ 模板: 22 │        │
│  │ [进入场景]│ │ [进入场景]│ │ [进入场景]│        │
│  └──────────┘ └──────────┘ └──────────┘        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ 🏭 钢铁   │ │ ☀️ 光伏   │ │ 🔌 动力   │        │
│  │ 制造      │ │ 制造     │ │ 电池      │        │
│  │ ...       │ │ ...      │ │ ...       │        │
│  └──────────┘ └──────────┘ └──────────┘        │
│  ... (共14个场景)                                │
├─────────────────────────────────────────────────┤
│  底部统计：291个行业模板 | 14个行业场景 | 7大行业  │
└─────────────────────────────────────────────────┘
```

**14个行业场景数据定义**:

| scenarioId | 图标 | 场景名称 | 行业标签 | 涉及模板分类 | 核心能力关键词 |
|------------|------|---------|---------|-------------|--------------|
| renewable-energy | 🔆 | 新能源发电 | 新能源 | A+C部分+D部分+G部分+K1 | 功率预测、故障诊断、资源评估 |
| energy-storage | 🔋 | 储能管理 | 新能源 | A部分+B部分+C部分+H部分+K2 | SOC/SOH估计、调度优化、寿命预测 |
| power-grid | ⚡ | 电网与微网 | 源网荷储 | G+H部分+K3+B部分 | 潮流计算、调度优化、电能质量 |
| steel-manufacturing | 🏭 | 钢铁制造 | 工业制造 | I部分+L2+C部分+F部分 | 质量预测、工艺优化、缺陷检测 |
| pv-manufacturing | ☀️ | 光伏制造 | 工业制造 | L3+F部分+C部分 | 缺陷检测、效率预测、良率优化 |
| battery-manufacturing | 🔌 | 动力电池 | 工业制造 | L4+C部分+B部分 | 一致性分析、安全预测、工艺优化 |
| general-manufacturing | 🏗️ | 工业制造(通用) | 工业制造 | I+C部分+B部分+L7 | 排程优化、故障诊断、SPC控制 |
| port-logistics | 🚢 | 港口运输 | 港口运输 | L5+I部分 | 泊位调度、AGV路径、能耗优化 |
| building-campus | 🏢 | 楼宇园区 | 楼宇园区 | L6+I部分+K4部分 | 暖通优化、能源审计、照明控制 |
| carbon-management | 🌱 | 碳管理 | 碳管理 | K5+H部分 | 碳核算、碳交易、碳足迹追踪 |
| industrial-visualization | 📊 | 工业可视化 | 通用工业 | J | SCADA、能流图、状态看板 |
| industrial-llm | 🤖 | 工业智能(LLM) | 通用工业 | E | RAG问答、日志解析、OCR识别 |
| industrial-vision | 👁️ | 工业视觉 | 通用工业 | F | 缺陷检测、目标检测、语义分割 |
| equipment-health | 🔧 | 设备健康管理 | 通用工业 | L1+C部分 | 预测性维护、RUL预测、FMEA |

### 4.2 场景详情页 (IndustryScenarioPage)

**路由**: `/industry/:scenarioId`
**定位**: 展示单个行业场景的完整解决方案，引导用户进入算法模板或基础模块

**页面结构**:

```
┌─────────────────────────────────────────────────┐
│  面包屑：行业场景 > 新能源发电                     │
├─────────────────────────────────────────────────┤
│  场景头部卡片：                                   │
│  🔆 新能源发电                                    │
│  功率预测、故障诊断、资源评估                       │
│  标签：[新能源] [预测] [诊断]                      │
├─────────────────────────────────────────────────┤
│  Tab 1: 推荐模板函数                              │
│  ┌─────────────────────────────────────────┐    │
│  │ 按子分类分组展示：                        │    │
│  │ ▸ 能源预测 (6个)                         │    │
│  │   - 光伏发电功率预测                      │    │
│  │   - 风电功率预测                          │    │
│  │   - ...                                  │    │
│  │ ▸ 设备故障诊断 (4个)                      │    │
│  │   - 逆变器故障诊断                        │    │
│  │   - 光伏组件故障分类                      │    │
│  │   - ...                                  │    │
│  │ ▸ 发电侧管理 (12个)                      │    │
│  │   - ...                                  │    │
│  └─────────────────────────────────────────┘    │
├─────────────────────────────────────────────────┤
│  Tab 2: 推荐算法模板                              │
│  从模板库中筛选与该场景相关的算法模板                │
│  [使用模板] → 跳转到 WorkflowEditorPage           │
├─────────────────────────────────────────────────┤
│  Tab 3: 相关基础模块                              │
│  展示该场景常用的基础算法模块（按层级分组）          │
│  [查看详情] → 跳转到 FunctionLibraryPage          │
└─────────────────────────────────────────────────┘
```

**交互要点**:
- 模板函数列表中每个函数可展开查看参数定义和说明
- "添加到模板"按钮：跳转到模板编辑器并预加载该函数节点
- "单独执行"按钮：跳转到函数执行器页面
- 面包屑导航支持返回行业场景总览

---

## 五、已有页面改造方案

### 5.1 HomePage 改造

**改造目标**: 增加行业场景入口，替换静态"应用场景"区域

**改造内容**:
1. 将"典型应用场景"卡片替换为"行业场景快速入口"（取前6~8个热门场景）
2. 统计数据增加"行业场景 14个"、"行业模板 291个"
3. 快速导航增加"行业场景"入口
4. 欢迎卡片副标题更新为体现1012函数规模

### 5.2 FunctionLibraryPage 改造

**改造目标**: 支持按层级筛选，支持从场景页跳转

**改造内容**:
1. 增加"层级"标签筛选栏：数据接入层 / 数据处理层 / 算法模型层 / 基础计算层 / MLOps层 / 输出展示层
2. 支持 URL 参数 `?category=xxx&layer=xxx` 从场景页跳转并自动筛选
3. 函数卡片增加"层级"标签显示
4. 页面标题从"AI算法库总览"改为"基础算法库"

### 5.3 TemplateGalleryPage 改造

**改造目标**: 增加行业场景分类维度

**改造内容**:
1. 增加行业场景标签筛选（与IndustryOverviewPage一致的14个场景）
2. 支持 URL 参数 `?scenario=xxx` 从场景详情页跳转
3. 模板卡片增加行业场景标签
4. 与后端模板数据结构对齐（增加 scenario 字段）

### 5.4 MainLayout 改造

**改造目标**: 重构导航菜单结构

**改造内容**:
1. 按第三节的导航结构重新组织菜单项
2. 增加"行业场景"一级菜单（带工厂图标）
3. 将知识图谱移入"基础算法库"子菜单
4. 新增"系统管理"分组
5. 实验性页面从导航移除
6. Header 标题映射增加新页面

---

## 六、后端 API 新增/改造

### 6.1 新增 API

| API | 方法 | 路径 | 说明 |
|-----|------|------|------|
| 获取行业场景列表 | GET | /api/industry/scenarios | 返回14个场景的元数据（id/名称/图标/标签/描述/模板数量） |
| 获取场景详情 | GET | /api/industry/scenarios/:id | 返回场景详情+关联的模板函数列表+推荐算法模板 |
| 获取场景统计 | GET | /api/industry/stats | 返回行业场景统计摘要 |

### 6.2 改造 API

| API | 改造内容 |
|-----|---------|
| GET /api/templates/ | 增加 `scenario` 查询参数，支持按行业场景筛选 |
| GET /api/functions/ | 增加 `layer` 查询参数，支持按层级筛选 |
| GET /api/functions/stats/summary | 增加行业模板统计数据 |

### 6.3 后端新增文件

| 文件 | 说明 |
|------|------|
| backend/api/industry.py | 行业场景 API 路由 |
| backend/services/industry_service.py | 行业场景服务（场景元数据+函数映射） |
| backend/data/industry_scenarios.json | 14个行业场景的静态配置数据 |

### 6.4 行业场景数据结构

```json
{
  "id": "renewable-energy",
  "name": "新能源发电",
  "icon": "🔆",
  "description": "光伏/风电功率预测、设备故障诊断、发电资源评估",
  "industry_tags": ["新能源"],
  "capabilities": ["功率预测", "故障诊断", "资源评估"],
  "template_categories": ["A", "C", "D", "G", "K1"],
  "function_ids": [243, 244, 245, 338, 339, 340, 418, 419, 586, 598, 893, 894, ...],
  "recommended_workflows": [],
  "related_basic_categories": ["ts_forecast", "anomaly_detection", "signal_processing"],
  "color": "#faad14",
  "sort_order": 1
}
```

---

## 七、前端新增文件清单

| 文件 | 说明 |
|------|------|
| frontend/src/pages/IndustryOverviewPage.tsx | 行业场景总览页 |
| frontend/src/pages/IndustryOverviewPage.css | 总览页样式 |
| frontend/src/pages/IndustryScenarioPage.tsx | 场景详情页 |
| frontend/src/pages/IndustryScenarioPage.css | 详情页样式 |
| frontend/src/services/industryApi.ts | 行业场景 API 调用封装 |
| frontend/src/types/industry.ts | 行业场景 TypeScript 类型定义 |
| frontend/src/data/industryScenarios.ts | 前端场景静态数据（图标/颜色/描述，与后端同步） |

---

## 八、实施优先级

### Phase 1：行业场景入口（核心）

1. 创建 `industry_scenarios.json` 静态数据
2. 实现 `IndustryOverviewPage` 行业场景总览页
3. 实现 `IndustryScenarioPage` 场景详情页
4. 改造 `MainLayout` 导航菜单
5. 改造 `HomePage` 增加行业入口
6. 新增 `backend/api/industry.py` + `industry_service.py`

### Phase 2：算法库增强

7. 改造 `FunctionLibraryPage` 增加层级筛选
8. 改造 `TemplateGalleryPage` 增加场景筛选
9. 改造后端 API 增加筛选参数

### Phase 3：联动打通

10. 场景详情页 → 模板编辑器的跳转联动
11. 场景详情页 → 基础算法库的跳转联动
12. 模板函数 → 单独执行的跳转联动

### Phase 4：数据填充

13. 补充 291 个行业模板函数到 functions.json / 数据库
14. 补充行业算法模板到 templates 目录
15. 完善场景描述和推荐内容

---

## 九、页面间跳转关系图

```
HomePage
  ├──→ IndustryOverviewPage（行业场景入口卡片）
  ├──→ FunctionLibraryPage（快速导航）
  └──→ WorkflowEditorPage（快速导航）

IndustryOverviewPage
  └──→ IndustryScenarioPage（点击场景卡片）

IndustryScenarioPage
  ├──→ WorkflowEditorPage（使用模板创建算法模板）
  ├──→ FunctionLibraryPage（查看相关基础模块，带筛选参数）
  ├──→ TemplateGalleryPage（查看更多模板，带场景参数）
  └──→ FunctionExecutor（单独执行某个模板函数）

FunctionLibraryPage
  ├──→ FunctionExecutor（选中函数后执行）
  └──→ WorkflowEditorPage（拖拽函数到模板）

TemplateGalleryPage
  └──→ WorkflowEditorPage（从模板创建算法模板）

WorkflowEditorPage
  └──→ FunctionLibraryPage（侧边栏浏览函数）
```

---

## 十、技术实现要点

### 10.1 路由配置变更 (App.tsx)

新增路由：
```
/industry                    → IndustryOverviewPage
/industry/:scenarioId        → IndustryScenarioPage
```

### 10.2 状态管理

行业场景数据可使用以下方案之一：
- **方案A（推荐）**: 前端静态数据 + 后端 API 补充动态数据（模板数量、算法模板数量）
- **方案B**: 完全后端 API 驱动

推荐方案A，因为14个场景的元数据（图标/名称/描述/颜色）变化频率低，前端静态定义更高效。动态数据（该场景下有多少模板函数已实现、有多少算法模板）通过 API 获取。

### 10.3 行业标签筛选

使用 Ant Design 的 `Tag.CheckableTag` 组件实现标签筛选栏：
- 标签列表：全部 / 新能源 / 工业制造 / 源网荷储 / 碳管理 / 楼宇园区 / 港口运输 / 通用工业
- 支持多选
- 筛选结果实时更新场景卡片

### 10.4 场景卡片组件

使用 Ant Design 的 `Card` + `Row/Col` 网格布局：
- 响应式：xs=24 sm=12 md=8 lg=6
- 卡片内容：图标 + 场景名 + 简要描述 + 模板数量标签 + 核心能力标签
- hover 效果 + 点击跳转

---

> 版本：V1.0
> 更新日期：2026-03-13
> 基于：algorithm-library-split.md V1.0（721基础 + 291模板 = 1012函数）
> 当前前端：React 18 + TypeScript + Ant Design 5 + React Flow + Zustand
> 当前后端：FastAPI + SQLAlchemy + SQLite
