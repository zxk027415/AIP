<!-- @AI_GENERATED -->
# Implementation Plan: 算法部署重构与工作流版本管理修复

## Overview

本实现计划将设计文档中的架构拆解为可逐步执行的编码任务。实现顺序为：后端数据模型与核心逻辑 → 后端 API 层 → 前端页面改造 → 工作流版本修复 → 数据库连接验证 → 集成联调。每个阶段配有属性测试和单元测试子任务，确保增量交付质量。

## Tasks

- [x] 1. 后端数据模型与持久化层
  - [x] 1.1 创建部署槽位数据模型和存储服务
    - 新建 `backend-service/services/deployment/` 目录
    - 创建 `backend-service/services/deployment/__init__.py`
    - 创建 `backend-service/services/deployment/models.py`，定义 `DeploymentSlot`、`ModelVersion`、`SwitchEvent` Pydantic 模型
    - 创建 `backend-service/services/deployment/store.py`，实现 JSON 文件读写（`data/deployment/slots.json`、`data/deployment/switch_log.json`）
    - 影子模型列表按 `accuracy_score`（精度评分）降序排列
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.3_

  - [x] 1.2 创建定时调度任务数据模型和存储服务
    - 创建 `backend-service/services/deployment/scheduler_models.py`，定义 `ScheduledTask` Pydantic 模型
    - 创建 `backend-service/services/deployment/scheduler_store.py`，实现 JSON 文件读写（`data/scheduler/tasks.json`）
    - 支持 `rolling_daily`、`cron`、`interval` 三种调度类型
    - `max_window_days`（最大窗口天数）控制滚动训练窗口截断
    - _Requirements: 2.1, 2.2, 4.1, 4.7_

  - [x] 1.3 扩展工作流元数据模型
    - 在现有 `EnhancedWorkflow` 模型中新增 `source_template_id`（来源模板 ID）、`version_group_id`（版本组 ID）、`version`（版本号）、`parent_version_id`（父版本 ID）字段
    - 确保向后兼容：新字段均为 Optional 或有默认值
    - _Requirements: 7.1, 7.2, 7.4, 7.5_

  - [ ]* 1.4 写属性测试：影子模型列表排序（Property 3）
    - **Property 3: 影子模型列表排序**
    - 创建 `backend-service/tests/test_shadow_model_sorting.py`
    - 生成随机 shadow 模型列表，验证返回结果按 `accuracy_score` 降序
    - **Validates: Requirements 3.4**

- [x] 2. 滚动训练调度引擎核心逻辑
  - [x] 2.1 实现滚动训练窗口计算器
    - 创建 `backend-service/services/deployment/rolling_window.py`
    - 实现 `compute_training_window(trigger_date, max_window_days, available_data)` 函数
    - 强制 Gap-One-Day 约束：训练数据截止 T-1，绝不使用 T 日数据
    - 窗口截断逻辑：超出 `max_window_days` 时从最早端截断
    - 预测目标为 T+1 日
    - _Requirements: 4.2, 4.3, 4.4, 4.7_

  - [ ]* 2.2 写属性测试：滚动训练窗口正确性（Property 1）
    - **Property 1: 滚动训练窗口正确性（含 Gap-One-Day 约束）**
    - 创建 `backend-service/tests/test_rolling_training_window.py`
    - 使用 hypothesis 生成随机 trigger_date、max_window_days、available_data_days
    - 验证：(a) 训练结束日期 = T-1, (b) 含所有 ≤T-1 的数据, (c) 超出 M 天则截断, (d) 预测目标 = T+1, (f) 无 ≥T 的记录
    - **Validates: Requirements 2.3, 4.2, 4.3, 4.4, 4.7**

  - [x] 2.3 实现精度指标计算模块
    - 创建 `backend-service/services/deployment/metrics.py`
    - 实现 `compute_mape(actual, predicted)` 和 `compute_rmse(actual, predicted)`
    - MAPE = mean(|actual - predicted| / |actual|) × 100
    - RMSE = sqrt(mean((actual - predicted)²))
    - _Requirements: 4.5_

  - [ ]* 2.4 写属性测试：精度指标计算正确性（Property 2）
    - **Property 2: 精度指标计算正确性**
    - 创建 `backend-service/tests/test_precision_metrics.py`
    - 使用 hypothesis 生成随机预测/实际值数组，验证 MAPE/RMSE 与标准公式一致
    - **Validates: Requirements 4.5**

  - [x] 2.5 实现调度引擎主循环
    - 创建 `backend-service/services/deployment/scheduler_engine.py`
    - 实现每日触发逻辑：数据拉取 → 滚动窗口选取 → 模型训练 → 预测 T+1 → 精度评估
    - 失败重试机制：记录失败原因，下一周期重试，超过 `max_retries` 后标记 `status="failed"`
    - 新数据自动纳入下次训练窗口，无需人工干预
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 3. Checkpoint - 确认核心逻辑测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 精度维护与切换决策引擎
  - [x] 4.1 实现切换资格检测逻辑
    - 创建 `backend-service/services/deployment/switch_decision.py`
    - 实现 `check_switch_eligibility(slot)` — 检查影子模型是否连续优于生产模型超过 `evaluation_window_days` 天
    - 返回切换建议：eligible 标志 + 待切换的影子模型 ID
    - _Requirements: 5.1, 5.4_

  - [ ]* 4.2 写属性测试：切换资格检测（Property 4）
    - **Property 4: 切换资格检测**
    - 创建 `backend-service/tests/test_switch_eligibility.py`
    - 使用 hypothesis 生成随机指标序列和窗口大小，验证切换判定逻辑
    - **Validates: Requirements 5.1, 5.4**

  - [x] 4.3 实现模型切换执行逻辑
    - 在 `switch_decision.py` 中实现 `execute_switch(slot, target_workflow_id, trigger_type, reason)`
    - 将目标 shadow 提升为 production，原 production 降级为 retired
    - 记录 `SwitchEvent` 到 `switch_log.json`（append-only）
    - 支持 `auto` 和 `manual` 两种触发类型
    - _Requirements: 5.2, 5.3_

  - [ ]* 4.4 写属性测试：模型切换状态转换（Property 5）
    - **Property 5: 模型切换状态转换正确性**
    - 创建 `backend-service/tests/test_model_switch.py`
    - 生成随机 slot 状态，验证切换后 production/retired 状态正确
    - **Validates: Requirements 5.2**

  - [ ]* 4.5 写属性测试：切换事件日志完整性（Property 6）
    - **Property 6: 切换事件日志完整性**
    - 创建 `backend-service/tests/test_switch_log.py`
    - 验证每次切换事件日志包含所有必需非空字段
    - **Validates: Requirements 5.3**

  - [x] 4.6 实现回滚逻辑
    - 在 `switch_decision.py` 中实现 `execute_rollback(slot)`
    - 恢复前一 production 模型为 production 状态，当前 production 降级为 retired
    - 仅在冷却期（`cooldown_hours`）内且精度低于阈值时触发
    - 记录回滚事件（`rollback_of` 指向被回滚的 event_id）
    - _Requirements: 5.5_

  - [ ]* 4.7 写属性测试：回滚恢复正确性（Property 7）
    - **Property 7: 回滚恢复正确性**
    - 创建 `backend-service/tests/test_rollback.py`
    - 生成随机切换历史，验证回滚后前 production 恢复为 production，当前降级为 retired
    - **Validates: Requirements 5.5**

- [x] 5. Checkpoint - 确认切换引擎测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 后端 API 层——部署与调度
  - [x] 6.1 创建部署槽位管理 API
    - 创建 `backend-service/api/deployment.py`（替换或重构现有文件）
    - 实现 `GET /api/deployment/slots` — 获取所有槽位及 production/shadow 模型
    - 实现 `GET /api/deployment/slots/{slot}/versions` — 获取版本历史
    - 实现 `POST /api/deployment/slots/{slot}/switch` — 执行切换
    - 实现 `POST /api/deployment/slots/{slot}/rollback` — 执行回滚
    - 实现 `GET /api/deployment/slots/{slot}/switch-log` — 获取切换日志
    - 实现 `GET/PUT /api/deployment/slots/{slot}/config` — 获取/更新自动切换配置
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.5_

  - [x] 6.2 扩展调度器 API
    - 修改 `backend-service/api/scheduler.py`，新增任务管理端点
    - 实现 `GET /api/scheduler/tasks` — 列出所有调度任务（摘要模式）
    - 实现 `POST /api/scheduler/tasks` — 创建新调度任务
    - 实现 `GET /api/scheduler/tasks/{task_id}` — 获取单个任务详情
    - 实现 `POST /api/scheduler/tasks/{task_id}/start` — 启动任务
    - 实现 `POST /api/scheduler/tasks/{task_id}/stop` — 停止任务
    - 保持现有 `/api/scheduler/{pipeline}/start`、`/stop`、`/status` 向后兼容
    - _Requirements: 2.1, 2.2, 2.4_

  - [x] 6.3 创建数据库连通性健康检查 API
    - 在 `backend-service/api/system.py` 中新增 `GET /api/system/db-health` 端点
    - 复用 `services/db/config.py` 的 `DBConfig`
    - 实现启动时验证：检查必需环境变量 → 尝试连接 → 返回结构化结果
    - 错误类型分类：`missing_env_vars` / `connection_timeout` / `auth_failure` / `database_not_found`
    - `DB_ENABLED=false` 时跳过连接验证
    - _Requirements: 8.4, 8.5, 8.6_

  - [ ]* 6.4 写属性测试：数据库连接验证正确性（Property 10）
    - **Property 10: 数据库连接验证正确性**
    - 创建 `backend-service/tests/test_db_connection_validation.py`
    - 使用 hypothesis 生成随机配置状态（缺失变量/无效连接），验证错误报告
    - **Validates: Requirements 8.4, 8.5, 8.6**

- [x] 7. 后端 API 层——工作流版本管理修复
  - [x] 7.1 修复工作流统一新建行为
    - 修改 `backend-service/api/workflows_enhanced.py`
    - 新增 `POST /api/workflows-enhanced/create-from-template` 端点
    - 从模板创建时：生成全新 `workflow_id` + 全新 `version_group_id`，`version=1`，记录 `source_template_id`
    - 创建空白工作流时：同样生成全新 `workflow_id` + `version_group_id`，`version=1`，`source_template_id=null`
    - 名称校验：从模板新建时名称不能与模板相同，否则返回 400
    - _Requirements: 7.1, 7.2, 7.6_

  - [x] 7.2 修复工作流编辑已有版本递增
    - 修改 `POST /api/workflows-enhanced/{workflow_id}/save` 逻辑
    - 保存时递增该工作流自身的版本号
    - `parent_version_id` 指向前一版本的 ID
    - 不影响其他工作流或源模板的版本号
    - URL 带已有 ID 时加载对应内容（"编辑已有"模式）
    - _Requirements: 7.4, 7.5, 7.7_

  - [ ]* 7.3 写属性测试：统一新建工作流元数据正确性（Property 8）
    - **Property 8: 统一新建工作流元数据正确性**
    - 创建 `backend-service/tests/test_workflow_unified_creation.py`
    - 使用 hypothesis 生成随机模板/空白创建请求，验证新 workflow_id 唯一、version=1、version_group_id 独立
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 7.4 写属性测试：工作流版本隔离（Property 9）
    - **Property 9: 工作流版本隔离**
    - 创建 `backend-service/tests/test_workflow_version_isolation.py`
    - 使用 hypothesis 生成随机保存序列，验证版本隔离（版本递增只影响本工作流）
    - **Validates: Requirements 7.4, 7.5**

- [x] 8. Checkpoint - 确认所有后端 API 测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 前端页面改造——算法部署
  - [x] 9.1 创建算法部署页面（替换占位页）
    - 新建 `frontend-sevice/src/pages/AlgorithmDeploymentPage.tsx` 替代 `AlgorithmDeploymentPlaceholderPage.tsx`
    - 实现三个 Tab 切换：模型管理 / 数据管线 / 定时调度
    - 模型管理 Tab：Slot 列表 + 每个 slot 的 production/shadow 模型卡片
    - 模型卡片点击展示版本历史列表（含 production/shadow/retired 状态标签）
    - 精度维护切换高亮提示 + 切换确认弹窗
    - _Requirements: 1.1, 2.1, 3.1, 3.2, 3.3, 3.4, 5.1, 5.2_

  - [x] 9.2 迁入数据管线面板
    - 在算法部署页面的"数据管线" Tab 内集成 `DataPipelineManagementPage` 的核心功能
    - 保持与原有 scheduler API 相同的启动、停止和状态查看功能
    - _Requirements: 1.1, 1.2_

  - [x] 9.3 实现定时调度摘要面板
    - 在算法部署页面的"定时调度" Tab 内展示调度任务列表
    - 仅展示摘要信息：任务名称、状态（运行中/已停止/失败）、上次执行结果、下次调度时间
    - 隐藏具体调度执行细节
    - 提供创建、启动、停止调度任务的操作按钮
    - _Requirements: 2.1, 2.2, 2.4_

- [x] 10. 前端页面改造——算法运营瘦身与路由
  - [x] 10.1 简化算法运营页面
    - 修改 `frontend-sevice/src/pages/AlgorithmOpsPage.tsx`
    - 保留精度指标时序图和归因分析结果展示
    - 移除调度任务管理、A/B 测试配置和自动重训触发入口
    - 新增操作类按钮跳转到"算法部署"页面
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 10.2 配置路由重定向
    - 修改前端路由配置（`App.tsx` 或路由文件）
    - `/industry-data/pipelines` → `/algorithm-deployment?tab=pipeline` 重定向
    - `/algorithm-ops/scheduler` → `/algorithm-deployment?tab=scheduler` 重定向
    - _Requirements: 1.3_

  - [ ]* 10.3 写单元测试：路由重定向和页面功能验证
    - 验证旧路由正确重定向到新路径
    - 验证算法运营页面无调度/A/B/重训入口
    - _Requirements: 1.3, 6.4_

- [x] 11. 前端页面改造——工作流版本修复
  - [x] 11.1 修复工作流列表页新建逻辑
    - 修改 `frontend-sevice/src/pages/WorkflowListPage.tsx`
    - "创建空白工作流"导航到 `/workflow/editor`（无 ID 参数）
    - 从模板创建调用 `POST /api/workflows-enhanced/create-from-template` API
    - 打开已有工作流导航到 `/workflow/editor/{id}`
    - _Requirements: 7.1, 7.3_

  - [x] 11.2 修复工作流编辑器页面模式区分
    - 修改 `frontend-sevice/src/pages/WorkflowEditorPage.tsx`
    - 无 ID 参数时：展示空白画布（"新建"模式），不携带已有 ID、不加载已有节点
    - 有 ID 参数时：加载对应工作流内容（"编辑已有"模式）
    - 首次保存新工作流调用 `POST /api/workflows-enhanced` 生成新 ID + version=1
    - 后续保存调用 `POST /api/workflows-enhanced/{workflow_id}/save` 递增版本
    - 从模板新建未改名时保存前提示输入新名称
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 12. 数据库连接可移植性
  - [x] 12.1 扩展数据库连通性验证器
    - 创建 `backend-service/services/db/connectivity_validator.py`
    - 实现 `DBConnectivityValidator` 类
    - `validate_config()` 方法：检查必需环境变量 → 尝试连接 → 返回结构化 `ValidationResult`
    - 启动阶段如缺失必需变量立即报错并列出所有缺失变量名
    - _Requirements: 8.4, 8.5, 8.6_

  - [x] 12.2 补充 `.env.example` 文件
    - 更新 `backend-service/.env.example`，确保包含所有必需的 MySQL 连接环境变量
    - 列出 `DB_CONNECTION_URL`、`DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD`、`DB_NAME`、`DB_ENGINE`、`DB_POOL_MAX`、`DB_ENABLED` 及其含义和默认值示例
    - _Requirements: 8.1, 8.2, 8.3_

- [x] 13. 注册路由和主入口集成
  - [x] 13.1 注册新 API 路由到 FastAPI 主入口
    - 修改 `backend-service/main.py`
    - 注册部署 API router（`/api/deployment`）
    - 确认调度器扩展的路由正确挂载
    - 确认 `/api/system/db-health` 端点可用
    - 在应用启动时调用 `DBConnectivityValidator` 执行连通性验证
    - _Requirements: 1.1, 2.1, 8.4_

  - [x] 13.2 前端 API 客户端创建
    - 新建 `frontend-sevice/src/services/deploymentApi.ts`
    - 封装部署槽位、调度任务、数据库健康检查的 API 调用方法
    - 与现有 `workflowEnhancedApi.ts` 风格保持一致
    - _Requirements: 1.1, 2.1, 3.1_

- [x] 14. Final Checkpoint - 确认所有测试通过、前端构建成功
  - Ensure all tests pass, ask the user if questions arise.
  - 后端：`cd backend-service && PYTHONPATH=. conda run -n aip_web pytest tests/test_rolling_training_window.py tests/test_precision_metrics.py tests/test_shadow_model_sorting.py tests/test_switch_eligibility.py tests/test_model_switch.py tests/test_switch_log.py tests/test_rollback.py tests/test_workflow_unified_creation.py tests/test_workflow_version_isolation.py tests/test_db_connection_validation.py -v`
  - 前端：`cd frontend-sevice && npm run build`

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from design document
- Unit tests validate specific examples and edge cases
- 后端使用 Python（FastAPI + Pydantic），前端使用 TypeScript（React + Ant Design）
- 数据持久化遵循项目现有 JSON 文件存储模式（`backend-service/data/`）
- 所有路径使用相对路径，不硬编码绝对路径
- 数据库连接配置复用现有 `services/db/config.py` 的三级优先级机制

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4", "2.1", "2.3"] },
    { "id": 2, "tasks": ["2.2", "2.4", "2.5"] },
    { "id": 3, "tasks": ["4.1", "4.3", "4.6"] },
    { "id": 4, "tasks": ["4.2", "4.4", "4.5", "4.7"] },
    { "id": 5, "tasks": ["6.1", "6.2", "6.3", "7.1", "7.2", "12.1", "12.2"] },
    { "id": 6, "tasks": ["6.4", "7.3", "7.4", "13.1"] },
    { "id": 7, "tasks": ["9.1", "9.2", "9.3", "10.1", "10.2", "13.2"] },
    { "id": 8, "tasks": ["10.3", "11.1", "11.2"] }
  ]
}
```
<!-- @AI_GENERATED: end -->
