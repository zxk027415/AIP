# 实现计划：预测工作流自动择优切换

## 概述

基于精度运营设计文档，将系统拆解为独立服务模块逐步实现。采用自底向上策略：先搭建基础设施和数据层，再实现核心业务逻辑，最后完成 API 层和前端仪表盘。每个模块配套 property-based test 验证正确性属性。

## Tasks

- [x] 1. 搭建项目结构与基础设施
  - [x] 1.1 创建目录结构和基础工具模块
    - 创建 `backend-service/services/precision_ops/` 目录及 `__init__.py`
    - 创建 `backend-service/tests/precision_ops/` 目录及 `conftest.py`（共用 fixtures、hypothesis strategies）
    - 创建 `backend-service/data/precision_ops/` 数据目录
    - 实现 `backend-service/services/precision_ops/utils.py`：封装 `_atomic_write_json`（先写临时文件后 `os.replace`）、`load_json_safe`、`ensure_data_dir`、`generate_event_id` 等公共工具函数
    - 在 `conftest.py` 中定义 `make_version_entry`、`make_prediction_record`、`make_slot_config` 等 hypothesis strategy builders
    - _Requirements: 1.1, 6.7_

  - [x] 1.2 实现配置管理器 `config_manager.py`
    - 实现 `SlotConfig` 数据类（含所有参数及默认值）
    - 实现 `ConfigManager` 类：`load_config(slot)` 从 JSON 加载并校验范围、`save_config(slot, config)` 原子写入、`validate_config(config)` 参数范围校验
    - 当存储不可用时降级到硬编码默认值并记录 `degraded_config` 警告
    - 配置文件路径：`data/precision_ops/{slot}/config.json`
    - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.7_

  - [ ]* 1.3 编写配置管理器 property test
    - **Property 19: 配置参数范围校验（Config Range Validation）**
    - 对任意配置更新请求，若任一参数值超出允许范围，整个更新应被拒绝，所有字段保持更新前的值不变
    - **Validates: Requirements 6.4, 6.5**

  - [ ]* 1.4 编写配置管理器 unit tests
    - 测试存储不可用时降级为默认值
    - 测试 `auto_switch_enabled` 从 false 转 true 时冷却计时器重置
    - 测试部分字段无效时整体拒绝
    - _Requirements: 6.5, 6.6, 6.7_

- [x] 2. 实现版本注册表
  - [x] 2.1 实现 `version_registry.py` 核心逻辑
    - 实现 `VersionEntry` TypedDict 数据结构
    - 实现 `VersionRegistry` 类：
      - `register(entry)` — 注册新版本，强制唯一性约束（workflow_id + version_tag），必填字段校验
      - `get_production(slot)` — 获取当前生产版本
      - `list_shadows(slot)` — 列出所有影子版本
      - `transition_status(workflow_id, version_tag, new_status)` — 状态转换（仅允许合法转换集合）
      - `_enforce_shadow_cap(slot)` — 影子版本超限时自动退役最老版本
    - 注册 `status=production` 时原子性降级当前生产版本为 shadow
    - 存储路径：`data/precision_ops/{slot}/version_registry.json`，使用 `_atomic_write_json`
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7_

  - [ ]* 2.2 编写版本注册表 property tests（Properties 1-6）
    - **Property 1: 版本注册往返一致性（Registration Round-Trip）**
    - **Validates: Requirements 1.1**
    - **Property 2: 版本标签唯一性不变式（Version Tag Uniqueness Invariant）**
    - **Validates: Requirements 1.2**
    - **Property 3: 单一生产版本不变式（Single Production Invariant）**
    - **Validates: Requirements 1.3, 4.5**
    - **Property 4: 影子版本上限不变式（Shadow Cap Invariant）**
    - **Validates: Requirements 1.5**
    - **Property 5: 状态转换合法性（State Transition Legality）**
    - **Validates: Requirements 1.6**
    - **Property 6: 必填字段校验拒绝（Required Field Validation）**
    - **Validates: Requirements 1.7**

- [x] 3. Checkpoint — 确保基础模块测试通过
  - 确保所有测试通过，ask the user if questions arise.

- [x] 4. 实现预测结果存储（Prediction Store）
  - [x] 4.1 实现 `prediction_store.py`（SQLite 存储层）
    - 创建 SQLite 数据库 `data/precision_ops/predictions.db`，WAL 模式，写操作 5s 超时
    - 实现 `PredictionStore` 类：
      - `init_db()` — 建表及索引（predictions 表，含 slot/workflow_id/version_tag/prediction_cycle_id/forecast_timestamp/predicted_value/actual_value/status/created_at/evaluated_at）
      - `record_prediction(slot, workflow_id, version_tag, cycle_id, forecast_timestamp, predicted_value)` — 写入预测记录
      - `fill_actuals(slot, cycle_id, actuals: Dict[str, float])` — 回填实际值
      - `get_predictions_in_window(slot, workflow_id, window_start, window_end)` — 窗口范围查询
      - `mark_actuals_missing(slot, cycle_id)` — 标记 48h 超时未到达实际值的周期
      - `cleanup_expired(retention_days)` — 删除超过保留期的记录
    - 复合唯一键：(slot, workflow_id, prediction_cycle_id, forecast_timestamp)
    - _Requirements: 2.5, 3.7_

  - [ ]* 4.2 编写预测存储 property test
    - **Property 7: 预测存储往返一致性（Prediction Store Round-Trip）**
    - 对任意合法预测记录，写入后通过复合键查询应返回相同的 predicted_value
    - **Validates: Requirements 2.5**

- [x] 5. 实现精度跟踪器
  - [x] 5.1 实现 `accuracy_tracker.py` 核心逻辑
    - 实现 `RollingMetrics` TypedDict 数据结构
    - 实现 `AccuracyTracker` 类：
      - `evaluate_cycle(slot, cycle_id)` — 为覆盖率 ≥ 90% 的版本计算 MAPE 和 MAE
      - `compute_rolling_mape(predictions, window_days)` — 滚动 MAPE 计算（排除 actual=0 的点）
      - `compute_rolling_mae(predictions, window_days)` — 滚动 MAE 计算（包含 actual=0 的点）
      - `get_rolling_metrics(slot, workflow_id)` — 获取版本滚动指标
      - `get_leaderboard(slot)` — 排行榜（按 rolling_mape 升序，排除 insufficient_data）
      - `refresh_all_metrics(slot)` — 窗口滑动时重算所有版本指标
    - 数据充分性判断：valid_cycle_count < min_valid_cycles 时标记 insufficient_data
    - 指标持久化到 `data/precision_ops/{slot}/accuracy_metrics.json`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 5.2 编写精度跟踪器 property tests（Properties 8-11）
    - **Property 8: MAPE 计算正确性（含零值排除）**
    - **Validates: Requirements 3.1, 3.6**
    - **Property 9: 评估窗口边界过滤（Window Boundary Filtering）**
    - **Validates: Requirements 3.2**
    - **Property 10: 数据充分性阈值判定（Sufficiency Threshold）**
    - **Validates: Requirements 3.3**
    - **Property 11: 排行榜排序正确性（Leaderboard Ordering）**
    - **Validates: Requirements 3.5**

- [x] 6. 实现切换日志与生产登记
  - [x] 6.1 实现 `switch_log.py`（仅追加审计日志）
    - 实现 `SwitchLog` 类：
      - `append(event)` — 追加一条不可变切换事件到 `.jsonl` 文件
      - `get_last_event(slot)` — 获取最近一次切换事件
      - `query(slot, page, page_size, trigger_type, time_range)` — 分页查询（默认 20 条，最大 100 条），支持 trigger_type 和时间范围过滤
    - 事件字段：event_id、timestamp、slot、trigger_type（automatic/manual/rollback）、source_workflow_id、target_workflow_id、source_rolling_mape、target_rolling_mape、decision_reason（最大 500 字符）
    - 存储路径：`data/precision_ops/{slot}/switch_log.jsonl`
    - _Requirements: 5.1, 5.7_

  - [x] 6.2 实现 `production_registry.py`（生产登记文件维护）
    - 实现 `ProductionRegistry` 类：
      - `get(slot)` — 读取当前生产登记条目
      - `update(slot, workflow_id, version_tag, event_id)` — 原子更新（先写后重命名）
      - `emit_change_event(slot, new_workflow_id, event_id)` — 发送变更事件（失败不阻塞，5s 超时）
      - `recover_from_corruption(slot, version_registry)` — 损坏恢复：回退到版本注册表中最近的 production 条目
    - 存储路径：`data/precision_ops/{slot}/production_registry.json`
    - 字段：workflow_id（当前生产工作流 ID）、version_tag（版本标签）、updated_at（最后更新时间）、source_event_id（来源切换事件 ID）
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 6.3 编写切换日志 property tests（Properties 15-16）
    - **Property 15: 切换日志仅追加（Append-Only Log）**
    - **Validates: Requirements 5.1**
    - **Property 16: 无效切换目标拒绝（Invalid Target Rejection）**
    - **Validates: Requirements 5.3**

  - [ ]* 6.4 编写生产登记 property test
    - **Property 21: 生产登记与切换同步（Production Registry Sync）**
    - 对任意成功的切换操作，生产登记文件中的 workflow_id 应等于新生产版本的 workflow_id，且 source_event_id 等于该次切换的 event_id
    - **Validates: Requirements 7.1, 7.2**

- [x] 7. Checkpoint — 确保存储层和日志模块测试通过
  - 确保所有测试通过，ask the user if questions arise.

- [x] 8. 实现切换决策引擎
  - [x] 8.1 实现 `switch_engine.py` 核心决策逻辑
    - 实现 `SwitchDecision` TypedDict 数据结构
    - 实现 `SwitchDecisionEngine` 类：
      - `evaluate(slot)` — 切换决策：冷却期检查 → auto_switch_enabled 检查 → 生产退化检测 → 寻找最优候选 → 返回 SwitchDecision
      - `execute_switch(slot, target_workflow_id, trigger_type, reason)` — 执行切换：原子性交换状态 → 更新 production_registry → 追加 switch_log → 发送事件
      - `rollback(slot)` — 回滚：检查回滚窗口 → 恢复上次切换的 source_workflow_id 为生产
    - 切换原子性保证：先写临时文件 → os.replace() 替换 → 失败时回滚到备份
    - Per-slot 文件锁（fcntl.flock）防止并发切换
    - 回滚窗口时效性检查：超过 rollback_window_hours 时拒绝
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 8.2 编写切换决策引擎 property tests（Properties 12-14, 17-18, 20）
    - **Property 12: 切换资格判定（Switch Eligibility）**
    - **Validates: Requirements 4.1, 4.2**
    - **Property 13: 最优候选选择（Best Candidate Selection）**
    - **Validates: Requirements 4.3**
    - **Property 14: 冷却期抑制（Cooldown Suppression）**
    - **Validates: Requirements 4.4**
    - **Property 17: 回滚恢复性（Rollback Restores Previous State）**
    - **Validates: Requirements 5.4**
    - **Property 18: 回滚窗口时效性（Rollback Window Expiry）**
    - **Validates: Requirements 5.6**
    - **Property 20: 自动切换禁用时不执行（Disabled Auto-Switch No-Op）**
    - **Validates: Requirements 6.2**

- [x] 9. 实现影子分发器
  - [x] 9.1 实现 `shadow_dispatcher.py` 并发分发逻辑
    - 实现 `ShadowDispatcher` 类：
      - `dispatch_prediction_cycle(slot, cycle_id, input_data)` — 一个预测周期的完整分发流程
      - `_execute_production(workflow_id, input_data, timeout)` — 最高优先级执行生产工作流
      - `_execute_shadow_batch(shadows, input_data, semaphore, timeout, cycle_id)` — 影子版本并发执行（asyncio.Semaphore(5) 限制）
    - 生产工作流失败 → 发出告警事件，标记 `production_failed`
    - 影子工作流失败/超时 → 记录日志，不中断整体流程
    - 复用现有 `_execute_pipeline_sync` 执行预测
    - 退役版本停止接收任务；已排队任务 60s 内重新分配给生产版本
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 1.4_

  - [ ]* 9.2 编写影子分发器 unit tests
    - 测试生产失败告警、影子超时取消、并发限制
    - 测试影子失败隔离不中断其他任务
    - 测试退役版本不再接收任务
    - _Requirements: 2.3, 2.4, 2.6_

- [x] 10. Checkpoint — 确保核心业务逻辑测试通过
  - 确保所有测试通过，ask the user if questions arise.

- [x] 11. 实现 REST API 层
  - [x] 11.1 实现 `backend-service/api/precision_ops.py` API 路由
    - 创建 FastAPI APIRouter，前缀 `/api/precision-ops`
    - 版本管理端点：
      - `POST /{slot}/versions` — 注册新版本
      - `GET /{slot}/versions` — 列出槽位所有版本
      - `PATCH /{slot}/versions/{version_tag}/status` — 变更版本状态
    - 精度监控端点：
      - `GET /{slot}/leaderboard` — 排行榜
      - `GET /{slot}/metrics-history` — 多版本每日 MAPE 时序数据
      - `GET /{slot}/production` — 当前生产登记条目
    - 切换操作端点：
      - `POST /{slot}/switch` — 手动触发切换
      - `POST /{slot}/rollback` — 回滚最近一次切换
      - `GET /{slot}/switch-log` — 切换日志分页查询（支持 trigger_type 和时间范围过滤）
    - 配置管理端点：
      - `GET /{slot}/config` — 获取槽位配置
      - `PUT /{slot}/config` — 更新槽位配置
    - 错误响应格式统一：`{"error": true, "code": "...", "message": "...", "details": {...}}`
    - _Requirements: 3.5, 5.2, 5.4, 5.7, 6.3, 7.3_

  - [x] 11.2 在 `backend-service/main.py` 注册精度运营路由
    - 导入 `api.precision_ops` 路由模块
    - 注册到 FastAPI app
    - _Requirements: 3.5, 7.3_

  - [ ]* 11.3 编写 API 集成测试
    - 测试完整链路：注册版本 → 触发预测周期 → 填入实际值 → 验证排行榜 → 触发切换 → 验证切换日志
    - 测试错误场景：无效状态转换、无效切换目标、回滚窗口过期
    - _Requirements: 1.6, 5.3, 5.6_

- [x] 12. 实现前端精度运营仪表盘
  - [x] 12.1 创建前端 API 客户端和类型定义
    - 创建 `frontend-sevice/src/services/precisionOpsApi.ts`：封装所有精度运营 REST API 调用
    - 创建 `frontend-sevice/src/types/precision-ops.ts`：定义 `VersionEntry`、`RollingMetrics`、`SwitchEvent`、`SlotConfig`、`LeaderboardEntry` 等 TypeScript 类型
    - _Requirements: 8.1, 8.2, 8.5_

  - [x] 12.2 实现精度运营仪表盘页面主结构
    - 创建 `frontend-sevice/src/pages/PrecisionOpsDashboardPage.tsx`
    - 实现页面布局：排行榜表格 + 多线时序图 + 切换日志时间线 + 配置面板
    - 实现排行榜表格：version_tag、status（状态标签）、rolling_mape、valid_cycle_count、last_evaluated_at；默认按 rolling_mape 升序；生产版本行对比色背景突出
    - 实现多线时序图（ECharts）：对比所有活跃版本在 eval_window_days 内的每日 MAPE；每条线以 version_tag 标注；不足 2 个版本时显示占位信息
    - 实现切换事件通知横幅：from_version、to_version、trigger_type、switched_at；一键回滚按钮（rollback_window_hours 内启用）；回滚确认对话框
    - 实现切换日志时间线视图：分页（默认 20 条），支持 trigger_type 过滤和日期范围过滤；颜色编码（automatic=蓝色、manual=绿色、rollback=橙色）
    - 实现配置面板：展示当前槽位参数，支持行内编辑，提交前按数值范围校验
    - 实现空状态视图：无版本或无评估记录时引导用户配置
    - 实现 60s 自动刷新：失败时保留最后成功数据并显示过期指示器
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 12.3 注册前端路由
    - 在 `frontend-sevice/src/App.tsx` 中添加精度运营仪表盘路由
    - 在侧边栏导航中添加"精度运营"入口
    - _Requirements: 8.1_

- [x] 13. 集成 AutoResearch Promote 与精度运营
  - [x] 13.1 在 AutoResearch Promote 成功后调用 Version Registry 注册新版本
    - 修改 `backend-service/api/workflows_enhanced.py` 中的 `promote_tuning_candidate` 逻辑
    - Promote 成功时调用 `VersionRegistry.register()` 将新 baseline 注册为 production 或 shadow
    - 当 `set_as_production=true` 时注册为 production（原子降级现有 production）
    - 当 `set_as_production=false` 时注册为 shadow
    - _Requirements: 1.1, 1.3_

- [x] 14. Final checkpoint — 确保全部测试通过且前端构建成功
  - 确保所有测试通过，ask the user if questions arise.
  - 运行 `cd backend-service && PYTHONPATH=. conda run -n aip_web pytest tests/precision_ops/ -q --tb=short`
  - 运行 `cd frontend-sevice && npm run build` 确保前端编译无错误

## Notes

- 标记 `*` 的子任务为可选，可在快速 MVP 阶段跳过
- 每个任务引用具体的需求条款，确保可追溯
- Checkpoints 确保增量验证，尽早发现问题
- Property tests 验证设计文档中 21 个正确性属性的核心子集
- Unit tests 覆盖错误路径和边界条件
- 前端构建验证确保 TypeScript 类型正确、组件渲染无误
- 所有 JSON 文件写入使用 `_atomic_write_json`，SQLite 使用 WAL 模式
- 影子分发器复用现有 `_execute_pipeline_sync`，不侵入工作流执行引擎

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "4.1"] },
    { "id": 2, "tasks": ["1.3", "1.4", "2.1", "4.2"] },
    { "id": 3, "tasks": ["2.2", "5.1", "6.1", "6.2"] },
    { "id": 4, "tasks": ["5.2", "6.3", "6.4"] },
    { "id": 5, "tasks": ["8.1", "9.1"] },
    { "id": 6, "tasks": ["8.2", "9.2"] },
    { "id": 7, "tasks": ["11.1", "12.1"] },
    { "id": 8, "tasks": ["11.2", "12.2"] },
    { "id": 9, "tasks": ["11.3", "12.3", "13.1"] }
  ]
}
```
