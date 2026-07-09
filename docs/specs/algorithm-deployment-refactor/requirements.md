<!-- @AI_GENERATED -->
# 需求文档：算法部署重构与工作流版本管理修复

## 简介

本次重构涉及两大模块改造：

1. **算法部署重构**：将"数据管线"从"行业数据管理"迁移至"算法部署"，将定时调度任务（拉数据、跑预测）从"算法运营"迁移至"算法部署"，并引入生产模型/影子模型管理、滚动训练调度策略、精度维护切换逻辑。原"算法运营"简化为纯精度展示+归因分析视图。

2. **工作流版本管理修复**：修复从场景模板创建新工作流时版本号错误递增的问题，以及"创建空白工作流"错误跳转到已有模板工作流的问题。统一"新建"行为：任何"创建新"操作（无论从模板还是空白）均产生独立的新工作流实体。

## 术语表

- **Algorithm_Deployment（算法部署）**：负责模型上线、生产/影子模型管理、定时调度、数据管线和精度维护切换的模块
- **Algorithm_Operations（算法运营）**：重构后仅负责精度展示和归因分析的模块
- **Production_Model（生产模型）**：当前正在线上承载预测服务的模型
- **Shadow_Model（影子模型）**：在后台并行运行但不对外提供预测的候选模型，用于与生产模型精度对比
- **Slot（槽位）**：系统中已有的多环境/多产品线分区概念。数据库表 `version_registry`、`candidate_pool`、`prediction_result`、`accuracy_metric`、`station_data` 等均包含 `slot` 列（默认值 `"default"`）；前端 `PrecisionOpsDashboardPage.tsx` 提供槽位选择器；后端 `precision_ops` API 使用 `/{slot}/` 路径参数。本需求复用该已有概念，不引入新定义
- **Rolling_Training_Schedule（滚动训练调度策略）**：每日调度时，训练窗口自动纳入截至 T-1 日的所有最新可用数据，窗口随时间持续滚动前移，确保模型始终使用最新数据训练；训练完成后预测 T+1 日目标值，待 T+1 实际数据到达后进行精度评估
- **Data_Pipeline（数据管线）**：从外部数据库定时拉取数据并进行预处理的管线
- **Precision_Maintenance（精度维护）**：通过对比生产模型与影子模型精度，决定是否切换主力模型的过程
- **Workflow_Version（工作流版本）**：工作流的迭代版本号，记录每次变更
- **Scenario_Template（场景模板）**：平台预置的场景工作流模板，可作为创建新工作流的起点
- **Scheduler_Engine（调度引擎）**：后端定时任务调度器，管理数据拉取和模型训练/预测的自动执行

## 需求

### 需求 1：数据管线迁入算法部署

**用户故事：** 作为算法运维工程师，我希望数据管线管理入口从"行业数据管理"迁移到"算法部署"模块内，以便在同一个页面完成从数据拉取到模型部署的全链路操作。

#### 验收标准

1. WHEN 用户进入"算法部署"页面，THE Algorithm_Deployment SHALL 在页面内展示数据管线管理面板
2. WHEN 数据管线面板迁入算法部署后，THE Algorithm_Deployment SHALL 保持与原有 scheduler API 相同的启动、停止和状态查看功能
3. WHEN 用户通过旧路径 `/industry-data/pipelines` 访问时，THE Algorithm_Deployment SHALL 通过路由重定向将用户导航到算法部署中的数据管线入口

### 需求 2：定时调度任务迁入算法部署

**用户故事：** 作为算法工程师，我希望定时调度任务（定时从数据库拉数据、跑训练/预测）从"算法运营"迁移到"算法部署"，以便在部署模块统一管理模型全生命周期。

#### 验收标准

1. WHEN 用户进入"算法部署"页面，THE Algorithm_Deployment SHALL 展示当前已配置的定时调度任务列表
2. THE Algorithm_Deployment SHALL 支持创建、启动、停止和查看定时调度任务
3. WHEN 定时调度任务配置完成后，THE Scheduler_Engine SHALL 按照 Rolling_Training_Schedule 策略自动执行数据拉取、模型训练和预测
4. WHILE 定时调度任务运行中，THE Algorithm_Deployment SHALL 在前端隐藏具体调度执行细节，仅展示任务状态摘要（运行中/已停止/上次执行结果）

### 需求 3：生产模型与影子模型管理

**用户故事：** 作为算法工程师，我希望在算法部署页面能看到每个部署槽位（Slot）的生产模型和影子模型，以便了解当前线上运行状况和候选替换方案。

#### 验收标准

1. WHEN 用户进入"算法部署"页面，THE Algorithm_Deployment SHALL 展示每个 Slot 的当前 Production_Model 和关联的 Shadow_Model 列表
2. WHEN 用户点击某个模型卡片时，THE Algorithm_Deployment SHALL 展示该模型的版本历史列表，包含每个版本的状态标签（production / shadow / retired）
3. THE Algorithm_Deployment SHALL 对每个 Slot 标注当前 Production_Model 的版本号和上线时间
4. WHEN 存在多个 Shadow_Model 时，THE Algorithm_Deployment SHALL 按精度评分降序排列影子模型列表

### 需求 4：滚动训练调度策略实现

**用户故事：** 作为算法工程师，我希望系统按照滚动训练策略自动运行训练和预测，使训练窗口持续纳入最新数据，模型始终基于最新可用信息进行优化。

#### 验收标准

1. THE Scheduler_Engine SHALL 每日按配置时间触发调度任务
2. WHEN 调度任务触发时，THE Scheduler_Engine SHALL 以滚动窗口方式纳入截至 T-1 日的所有最新可用历史数据进行模型训练，训练窗口随新数据到达持续向前滚动
3. WHEN 新的历史数据入库后，THE Scheduler_Engine SHALL 在下一次调度触发时自动将新数据纳入训练窗口，无需人工干预或重新配置截止日期
4. WHEN 模型训练完成后，THE Scheduler_Engine SHALL 使用训练后的模型预测 T+1 日的目标值
5. WHEN T+1 日实际数据到达时，THE Scheduler_Engine SHALL 自动计算预测值与实际值的精度指标（MAPE、RMSE 等）
6. IF 调度任务执行失败，THEN THE Scheduler_Engine SHALL 记录失败原因并在下一个调度周期重试
7. THE Scheduler_Engine SHALL 支持配置滚动窗口的最大长度（天数），超出最大长度的历史数据自动从训练窗口中移除

### 需求 5：精度维护切换迁入算法部署

**用户故事：** 作为算法工程师，我希望 Shadow_Model 与 Production_Model 之间的精度维护切换操作在"算法部署"中完成，以便在部署模块统一管理模型上下线。

#### 验收标准

1. WHEN Shadow_Model 的精度指标连续优于 Production_Model 超过配置的评估窗口天数时，THE Algorithm_Deployment SHALL 在界面上高亮提示可切换
2. WHEN 用户确认执行切换操作时，THE Algorithm_Deployment SHALL 将 Shadow_Model 提升为 Production_Model，并将原 Production_Model 降级为 retired 状态
3. THE Algorithm_Deployment SHALL 记录每次切换事件，包括触发类型（自动/手动）、切换时间和切换前后的精度指标
4. WHERE 自动切换功能启用时，THE Algorithm_Deployment SHALL 在满足切换条件后自动完成 Shadow_Model 到 Production_Model 的提升
5. IF 切换后新 Production_Model 精度在冷却期内低于阈值，THEN THE Algorithm_Deployment SHALL 支持一键回滚到前一版本

### 需求 6：算法运营简化为精度展示和归因分析

**用户故事：** 作为算法运维工程师，我希望"算法运营"页面仅展示精度监控和归因分析信息，以便专注于模型表现诊断而非操作管理。

#### 验收标准

1. THE Algorithm_Operations SHALL 展示所有已部署模型的精度指标时序图
2. THE Algorithm_Operations SHALL 展示模型精度下降时的归因分析结果（数据漂移、概念漂移等）
3. WHEN 用户从"算法运营"点击需要进行切换或调度操作时，THE Algorithm_Operations SHALL 引导用户跳转至"算法部署"页面完成操作
4. THE Algorithm_Operations SHALL 移除原有的调度任务管理、A/B 测试配置和自动重训触发入口

### 需求 7：工作流版本管理——新建操作统一产生新工作流实体

**用户故事：** 作为算法开发者，我希望任何"新建"操作（无论从场景模板创建还是创建空白工作流）均产生独立的新工作流实体，与"打开并编辑已有工作流"行为严格区分，避免版本号错误递增或误跳转到已有工作流。

#### 验收标准

1. WHEN 用户通过任何"新建"入口（从 Scenario_Template 创建、创建空白工作流）触发创建操作时，THE Workflow_Version SHALL 生成一个全新的独立 workflow_id 并设置初始版本号为 1
2. WHEN 新工作流基于 Scenario_Template 创建时，THE Workflow_Version SHALL 在新工作流元数据中记录源模板 ID 作为 `source_template_id`（来源模板标识，便于溯源）
3. WHEN 用户点击"创建空白工作流"按钮时，THE Workflow_Version SHALL 导航到工作流编辑器页面，展示空白画布，不携带任何已有工作流 ID 参数且不加载任何已有节点和连线
4. WHEN 用户对已创建的工作流进行后续修改并保存时，THE Workflow_Version SHALL 递增该工作流自身的版本号，不影响源模板或其他工作流的版本号
5. WHEN 用户打开一个已有工作流并保存修改时，THE Workflow_Version SHALL 递增该已有工作流的版本号（即"编辑已有"操作）
6. IF 用户从模板新建时未修改工作流名称就尝试保存，THEN THE Workflow_Version SHALL 提示用户输入新的工作流名称以区分模板
7. IF 导航 URL 中包含已有工作流 ID 参数，THEN THE Workflow_Version SHALL 加载该 ID 对应的工作流内容（即"编辑已有"模式），不触发新建行为

### 需求 8：数据库连接可移植性

**用户故事：** 作为算法工程师，我希望数据管线的 MySQL 数据库连接配置通过环境变量或配置文件管理，以便在不同开发机器（如从 macOS 迁移到 Windows）之间无需修改代码即可完成数据库重连。

#### 验收标准

1. THE Data_Pipeline SHALL 通过环境变量或外部配置文件读取 MySQL 连接参数（`DB_HOST`（数据库主机地址）、`DB_PORT`（端口号）、`DB_USER`（用户名）、`DB_PASSWORD`（密码）、`DB_NAME`（数据库名称）），不在代码中硬编码任何连接地址或端口
2. WHEN 开发者将项目从一台机器迁移到另一台机器时，THE Data_Pipeline SHALL 仅通过修改环境变量或配置文件即可完成数据库连接切换，无需改动任何源代码
3. THE Data_Pipeline SHALL 在项目中提供 `.env.example` 或等效文档，明确列出所有必需的 MySQL 连接环境变量及其含义和默认值示例
4. WHEN 系统首次启动或数据管线初始化时，THE Data_Pipeline SHALL 主动验证数据库连通性（执行连接测试）
5. IF MySQL 数据库不可达或连接参数缺失，THEN THE Data_Pipeline SHALL 返回结构化的错误信息，明确指出失败原因（如"连接超时：无法连接到 DB_HOST:DB_PORT"或"缺少必需环境变量 DB_PASSWORD"）
6. IF 任何必需的数据库连接环境变量未设置，THEN THE Data_Pipeline SHALL 在启动阶段立即报错并列出所有缺失的变量名称，不尝试使用空值连接
<!-- @AI_GENERATED: end -->
