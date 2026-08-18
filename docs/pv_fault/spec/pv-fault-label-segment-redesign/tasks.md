<!-- @AI_GENERATED -->
# 实现任务：光伏故障逐点标签重构（pv-fault-label-segment-redesign）

> 任务按依赖顺序编排：先做设计阶段挂起的前置校验（列名冲突、日照窗阈值），再建存储层，再自底向上搭领域服务、编排、算子改动，最后迁移与端到端验证。每项任务只做编码 + 该项测试，均可独立验证。所有代码遵守零新增算子、相对路径、`@AI_GENERATED` 标记约束。运行环境 conda `cp_web`。

## 阶段 0：前置校验（阻塞后续设计假设，须最先完成）

- [x] 1. 三路特征算子输出列名冲突检查
  - 在 conda `cp_web` 下用 quickval 训练模板真实参数运行 `extract_statistical_features`（groupby_aggregate，quantiles=[0.25,0.75]，compute_diff=true）、`tsfresh_extract`、`ts_comparison_features`
  - **结果：无冲突**。63/20/10 列全部以 `value_*`/`i_cal_*`/`diff_value_i_cal_*` 打头，与 12 个透传列（`group_key`/`label_source`/`label_source_purity`/`label_op_id`/3×`period_is_*`/5×`night_*`）零交集，三路互相之间也无同名列
  - 结论已回填 `design.md` 列名冲突检查段；`lbl_` 前缀方案不需要启用
  - _需求: 11.15, 11.16, 11.17_

- [x] 2. 日照窗经验推导阈值标定（含 S1 季节桶 + 近期回溯）
  - 用 `pv_cumulative_labeled_merged.parquet` 按 `(site_id, 季节桶=月份1~12)` 跑中位功率曲线（14 组），试跑 `peak_ratio ∈ {0.03, 0.05, 0.10}`
  - **确定 `peak_ratio=0.05`**（与现有 `irr_threshold` 对齐）；窗口时长 min/median/max = 2.67h/10.33h/23.92h；**4h/20h 回退边界验证合理**：真实触发 3 组回退（1 短窗、2 长窗），均为数据量偏小/异常的组，未误伤正常组
  - `lookback_months=24` 在本数据集（总跨度 22 个月）上暂无裁剪效果，保留为默认初值
  - 标定结果已写入 `design.md` 组件 3 段
  - _需求: 7.16, 7.16a, 7.16b, 7.16c_

## 阶段 1：存储层（point_labels / label_ops）

- [x] 3. 新增 `PointLabel` 与 `LabelOp` ORM 模型
  - 已在 `backend-service/services/db/models/pv_fault.py` 追加两个模型（`_SCHEMA=None`，复用 `Base`）
  - `PointLabel` 主键 `(site_id, device_id, branch_id, time)` + `Index(op_id)`；`LabelOp` 主键 `op_id` + `Index(site,device,branch,t_start,t_end)` + `Index(source,status)`
  - 字段严格按 design 数据模型章节；两表均无测量数值列
  - _需求: 2.1, 2.2, 2.6, 2.10, 2.11_

- [x] 4. 新增 `PointLabelRepository`
  - 已新建 `backend-service/services/db/repositories/point_label.py`，构造签名 `__init__(self, adapter: DBAdapter)`
  - 方法：`upsert_points`/`query_points`/`delete_points_in_range`/`insert_op`/`revoke_op`/`query_op_by_id`/`query_active_ops`/`query_active_human_range_overlap`/`query_ops_by_parent`/`query_ops_by_migration_batch`
  - 所有写走 `get_sync_session()` 事务；`upsert_points` 用 MySQL `ON DUPLICATE KEY UPDATE`
  - **单测已跑通（conda cp_web，真实库 `aip_algo_platform`）**：`backend-service/tests/db/test_point_label_repository.py` 9 个用例全部 PASSED（增删查、重叠检查、伴生操作查询、按批次查询、upsert 覆盖语义、时间范围半开区间）；测试用独立 `TEST-plr-*` 设备前缀，fixture teardown 后确认无残留
  - _需求: 2.5, 2.6, 21.3_

- [x] 5. 确定并实现建表方式
  - 确认项目走 **Alembic** 迁移（`DBAdapter.__init__` 会自动 `alembic upgrade head`），不是 `create_all`
  - 新建迁移脚本 `backend-service/alembic/versions/9f3c1a7b2d4e_create_point_labels_and_label_ops.py`，`down_revision` 接现有 head `2a240e0c2ce6`
  - **已实跑 `alembic upgrade head` 建表成功**（真实库 `aip_algo_platform`）：`point_labels` 10 列 5 索引、`label_ops` 18 列 8 索引，字段与索引均与设计一致；`alembic current` 确认新 head 为 `9f3c1a7b2d4e`
  - 不改动 `training_samples` 现有结构与唯一约束（只在文档标注 `label` 列废弃）
  - _需求: 2.7, 17.4_

## 阶段 2：领域纯函数与服务

- [x] 6. 实现 `DaylightWindowResolver`
  - 已新建 `backend-service/services/iterative_labeling/daylight_window.py`
  - `DaylightWindow`（frozen dataclass，含 `contains()` 半开区间判定）+ `resolve(table, site_id, month)` 与 `build_table(measurements)`；`empirical` 用跨天中位曲线、`fixed` 兜底 06:00–18:00
  - 回退条件与回退清单记录（`logger.warning` 汇总）；用任务 2 标定的阈值（`peak_ratio=0.05`、4h/20h）
  - 按 `(site_id, 季节桶=月份1~12)` 分组；只用最近 `lookback_months`（默认 24）个月数据；不足先放宽回溯窗再回退 fixed
  - **单测已跑通**：`backend-service/tests/test_daylight_window.py` 9 个用例全部 PASSED，覆盖半开区间判定、合成数据窗口推导、单故障日不移动窗口（核心不变量）、跨年同月季节桶归一、数据不足回退、时长异常回退、`resolve()` 缺失组合不现场推导、非法 `peak_ratio` 报错；含一条用真实数据复现 design.md 标定结果（14 组、3 组回退）的回归测试
  - _需求: 7.16, 7.16a, 7.16b, 7.16c_

- [x] 7. 实现 `LabelMaterializer`
  - 已新建 `backend-service/services/iterative_labeling/label_materializer.py`
  - `materialize(site,device,branch,t_start,t_end)`：取覆盖点的 active 操作按 `(priority DESC, created_at DESC, op_id DESC)` 逐点取最大；未覆盖点计入 unknown 不写行；先删范围内旧行再批量 upsert（避免范围收缩遗留过期点）
  - `verify(...)` 只读一致性校验，返回 `{time, expected, actual}` 差异明细
  - 配套在 `PVFaultRepository` 新增 `query_sample_times(site,device,branch,t_start,t_end)`（现有 `query_training_samples` 只过滤 site_id，不足以支撑按设备三元组物化）
  - **单测已跑通**：`backend-service/tests/test_label_materializer.py` 8 个用例全部 PASSED，覆盖优先级裁决（human_range 100 压过 day_label 10）、同优先级 created_at/op_id 三级裁决、**顺序无关性**（打乱输入结果一致）、未覆盖点 unknown 计数、无操作全 unknown、revoked 操作被排除、只重算指定范围（范围外旧数据不受影响）；含一条真实数据库端到端用例验证 `materialize` 后 `verify` 零差异
  - _需求: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

- [x] 8. 实现 `PointLabelService` 不变量校验与写入
  - 已实现 `backend-service/services/iterative_labeling/point_label_service.py` + 设备维度进程内锁
  - **单测 PASSED**：`tests/test_point_label_service.py` 18 用例

- [x] 9. 实现 K4「未框选即正常」双操作机制
  - 已含于 `PointLabelService._write_rest_of_day_companions`
  - **单测 PASSED**：同上

- [x] 10. 实现操作生命周期与撤销联动
  - `revoke_op` / `correct_op` 已实现
  - **单测 PASSED**：同上

- [x] 11. 实现 `SampleBuilder` 纯函数与策略不变量
  - 已新建 `backend-service/services/iterative_labeling/sample_builder.py`
  - **单测 PASSED**：`tests/test_sample_builder.py` 7 用例

- [x] 12. 实现 `sample_id` 生成与解析
  - 已新建 `backend-service/services/iterative_labeling/sample_id.py`
  - **单测 PASSED**：含于 `test_sample_builder.py`

- [x] 13. 改造 `_create_snapshot` 为 `SnapshotBuilder`
  - 已新建 `snapshot_builder.py`；`cumulative_training.py` 新增 `_create_snapshot_point_label` + legacy 分支
  - **合成 E2E PASSED**：`tests/test_pv_point_label_e2e.py::test_synthetic_device_snapshot_pipeline`（55s，真实库）

- [x] 14. 实现 `label_snapshot_hash` 与快照隔离
  - `compute_label_snapshot_hash` + 快照 meta 写入
  - **验证**：合成 E2E 断言 hash 非空

- [x] 15. 实现 `InferenceSampleGenerator`
  - 已新建 `backend-service/services/iterative_labeling/inference_sample.py`
  - **预测 E2E PASSED**（`scripts/e2e_k7_retrain_and_inference.py`）：武当湖 04# 288 点 → 3 个 inf- 样本，`split_mode=by_day_night`

- [x] 16. `extract_statistical_features.py` 新增 `passthrough_fields`
- [x] 17. `extract_statistical_features.py` 分位数判定口径改动（移除全局 avg_count>=48 门控）
- [x] 18. `stratified_cv_eval.py` 新增 `group_col` 分组切分
- [x] 19. `stratified_cv_eval.py` 持久化 `sample_strategy` 与旧快照防降级告警
- [x] 20. 更新工作流模板 JSON `workflow-pv-fault-diag-quickval-cv-v1.json`

- [x] 21. 删除 split parity 机制
  - 已删 `PVTrainingWorkspaceService.set/_read_workflow_split_parity`
  - API `split-config` 返回 410；重训不再接受 `solar_mode`
  - 前端部署页/精度运营面板已切换为逐点标签视图

- [x] 22. 人工裁决落标主链路接线
  - `submit_verdict`（pv_fault）→ `PointLabelService.submit_op(human_day)` + `admit_point_label_op`

- [x] 23. 改造 `freeform_labeling` 跨会话重叠检查与撤销
  - pv_fault 走 `human_range` + `query_active_human_range_overlap`；撤销调用 `revoke_op`

- [x] 24. 待标注队列 API 与运营面板
  - `GET /point-labels/pending-queue`、`GET /point-labels/source-coverage`
  - `PvFaultSplitModeOpsPanel` 改为待标注/来源覆盖面板

- [x] 25. 按 source 分口径评估
  - `AccuracyEvaluator.get_current_accuracy()` 增加 `by_source` 字段

- [x] 26. 实现 `MigrationTool` 四源迁入
  - 已新建 `backend-service/scripts/migrate_point_labels.py`（parquet + verdict/time_slices/cluster + rollback）
  - 全量见任务 27

- [x] 27. 迁移对账报告与失败处理
  - 全量 execute：`mig-20260731-e2e`（4457 day_label + 2 human_range + 20 human_day）
  - 报告：`backend-service/data/iterative_labeling/migration_report_mig-20260731-e2e.json`
  - cluster 源跳过（run 仍为 pending_naming）

- [x] 28. 按 migration_batch_id 回滚（骨架已有 `rollback_batch`）

- [x] 29. 设备维度写入串行化（**review 后补齐**：此条曾从任务清单中缺失）
  - 双层串行化：进程内 `threading.RLock`（`_DEVICE_LOCKS`，挡同进程并发）+ **DB 顾问锁**（`PointLabelRepository.device_advisory_lock()`，MySQL `GET_LOCK`，挡跨进程/多 worker 并发）
  - 只有进程内锁在多进程部署下不足，故补 DB 级锁兜底；非 MySQL 或取锁失败时降级为仅进程内锁并记 warning，不阻断业务
  - 锁名取设备三元组 SHA-256 前 48 位（`GET_LOCK` 名称上限 64 字节）
  - `submit_op` 与 `revoke_op` 两处临界区均已接入
  - **单测已跑通**：`backend-service/tests/test_point_label_concurrency.py` 3 个用例 PASSED —— 同设备顾问锁跨连接互斥、不同设备互不阻塞、4 线程并发写同设备后 `LabelMaterializer.verify()` 零差异
  - _需求: 21.6, 21.7, 22.5, 22.6_

- [x] 30. 端到端集成测试
  - **PASSED**：合成设备 pipeline、武当湖 04# 2020-05-08、split_mode 量级对比

- [x] 31. 标注历史 spec 文档为已取代
  - 已在 `docs/specs/pv-fault-iterative-labeling-loop/` 四份 design/requirements 顶部标注

- [x] 32. 新旧建模路径并存与 A/B 精度对比（K7）
  - `modeling_path_compare.py` + API + 前端面板 + `production_path`/`fallback_path`
  - orchestrator 已从快照 `.meta.json` 注入 `sample_strategy` 到 stratified_cv_eval，并**回传** `sample_strategy`/`label_snapshot_hash` 给调用方（review 后补）

  - **⚠️ 首轮 A/B 结论作废**（`e2e_k7_retrain_report.json`）：当时 legacy_day 用全量 parquet（n=6923），point_label 用 `training_samples`（n=1098/3220），**两条路径数据量差 3.3 倍**，违反需求 23.2「同一批测量数据」，F1 差异不可归因于路径优劣。该报告保留仅作历史留痕。

  - **✅ 范围对齐后重跑（`ab_aligned_report.json`，align_scope=true，197s）——结论反转**：

    | 路径 | n_samples | macro-F1 | accuracy | Δ vs legacy |
    |---|---|---|---|---|
    | legacy_day | 1,778 | 0.8195 | 0.9775 | baseline |
    | **point_label_by_day** | 1,071 | **0.8296** | 0.9953 | **+0.0101（最优）** |
    | point_label_by_day_night | 3,139 | 0.6955 | 0.9341 | −0.1240 |

    - `scope_info`：legacy 4,457 设备-天、point_label 1,103、共同 **1,085**（覆盖 legacy 的 24.3%、覆盖 point_label 的 98.4%）
    - **修正结论**：`point_label_by_day` 略优于老路径，首轮「新路径更差」是数据量差异造成的假象
    - **`by_day_night` 明显最差（−0.1240）**，与设计阶段的已知取舍一致：夜间样本点数中位数仅 39、常规统计特征近乎常量，区分度几乎全押在 5 个 `night_*` 特征上。**建议把默认 `split_mode` 从 `by_day_night` 改为 `by_day`**（此为待用户确认的设计变更，未擅自改动）
    - 共同范围只覆盖 legacy 的 24.3%，根因是 `training_samples` 仅 31 万行 / 1,130 设备-天，而源 parquet 有 105 万行 / 4,457 设备-天；要在全量数据上比，需先把 parquet 灌进 `training_samples`

## 说明

- 工作区安全（需求 17.1, 17.2, 17.3, 17.6, 17.7）为贯穿约束，非独立任务：全程不清理/重置/删除历史产物、用相对路径、AI 生成代码块标注 `@AI_GENERATED`、保留旧模板可运行。
- 每个任务完成后在 conda `cp_web` 下跑该任务对应测试；改到 AutoResearch/负荷预测无关模块时不跑全量。
- 阶段 0 两项是设计假设的前置校验，必须先于阶段 4 的算子改动完成。
<!-- @AI_GENERATED: end -->
