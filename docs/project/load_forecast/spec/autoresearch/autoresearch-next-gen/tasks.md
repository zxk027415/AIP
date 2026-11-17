# Implementation Plan: AutoResearch Next-Gen（自主研究员）

## Overview

按优先级 P0 → P0.5 → P1 → P2 → P3 渐进实现。每个模块作为独立 Python 文件放在 `backend-service/services/` 下，通过明确接口与主循环 `_run_autoresearch_task` 集成。测试使用 `pytest` + `hypothesis` 双轨策略。

## Tasks

- [ ] 1. P0 前置：扩展回测引擎返回 cv_fold_metrics
  - [ ] 1.1 扩展 `_execute_backtest` 返回 `cv_fold_metrics`
    - 修改 `backend-service/api/workflows_enhanced.py` 中 `_execute_backtest` / `_execute_backtest_reference` 函数
    - 在内部 TimeSeriesSplit 5-fold 交叉验证循环中，收集每个 fold 的 `fold_id`、`train_loss`、`val_loss`、`val_mape`
    - 将 `cv_fold_metrics` 作为新字段添加到回测返回结构中
    - 确保向后兼容：旧调用方不受影响
    - _Requirements: 1.5_

  - [ ]* 1.2 编写 `cv_fold_metrics` 返回结构的单元测试
    - 在 `backend-service/tests/test_backtest_cv_fold.py` 中验证返回结构正确性
    - 测试 fold 数量、字段完整性、数值合理性
    - _Requirements: 1.5_

- [ ] 2. P0：Dataset_Profiler 核心实现
  - [ ] 2.1 创建数据模型定义文件
    - 创建 `backend-service/services/dataset_profiler_models.py`
    - 定义 `TrainProfile`、`ValidationProfile`、`TestProfile`、`TriDatasetDiagnosis`、`CrossWindowPattern`、`CVFoldMetric` 等 dataclass / TypedDict
    - 所有模型支持 JSON 序列化/反序列化
    - _Requirements: 8.1, 1.1, 1.5, 1.7, 1.10, 1.13_

  - [ ] 2.2 实现 `compute_train_profile`
    - 创建 `backend-service/services/dataset_profiler.py`，实现 `DatasetProfiler` 类
    - 实现 `compute_train_profile` 方法：计算 `load_curve_stats`（均值/标准差/偏度/峰度）、`peak_valley_distribution`、`data_quality`、`periodicity_strength`、`period_distribution`（四时段划分）、`dominant_pattern`、`weekday_weekend_gap`、`train_fit_mape`
    - 四时段 ratio 之和必须等于 1.0（误差 < 0.01）
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 2.3 编写 Property 1 属性测试：训练集画像完整性与正确性
    - **Property 1: 训练集画像完整性与正确性**
    - 在 `backend-service/tests/test_dataset_profiler.py` 中使用 hypothesis 库
    - 验证所有必需字段存在、四时段 ratio 之和 = 1.0、dominant_pattern 与 weekday_weekend_gap 阈值一致
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [ ] 2.4 实现 `compute_validation_profile`
    - 实现基于 `cv_fold_metrics` 的验证集画像生成
    - 计算 `cv_fold_losses`、`cv_val_mape`、`overfit_indicator`（high/moderate/low 阈值判定）、`cv_loss_trend`
    - _Requirements: 1.5, 1.6_

  - [ ]* 2.5 编写 Property 2 属性测试：验证集画像过拟合判定规则
    - **Property 2: 验证集画像过拟合判定规则**
    - 验证 overfit_indicator 阈值判定逻辑、cv_loss_trend 方向与后期 fold 单调性一致
    - **Validates: Requirements 1.5, 1.6**

  - [ ] 2.6 实现 `compute_test_profile`
    - 实现测试集画像：`actual_vs_predicted`、`overall_mape`、`overall_rmse`、`max_single_point_error`、`period_error_breakdown`（四时段 MAPE + worst_period）、峰谷检测（`peak_error_ratio`、`valley_error_ratio`、`high_error_at_extremes`）
    - 使用 scipy.signal.find_peaks 进行峰谷检测
    - _Requirements: 1.7, 1.8, 1.9_

  - [ ]* 2.7 编写 Property 3 属性测试：测试集画像误差计算正确性
    - **Property 3: 测试集画像误差计算正确性**
    - 验证 overall_mape 等于逐点绝对百分误差均值、worst_period 为最大 MAPE 时段、peak_error_ratio 计算正确
    - **Validates: Requirements 1.7, 1.8, 1.9**

  - [ ] 2.8 实现 `compute_tri_dataset_diagnosis`
    - 实现三集对比诊断：`pattern_consistency`、`overfit_detection`（含降级逻辑）、`generalization_assessment`、`diagnosis_conclusion`
    - 当 validation_profile 不可用时降级为 train_fit_mape 判定
    - diagnosis_conclusion 不超过 200 字
    - _Requirements: 1.10, 1.11, 1.12_

  - [ ]* 2.9 编写 Property 4 属性测试：三集对比诊断规则一致性
    - **Property 4: 三集对比诊断规则一致性**
    - 验证 overfit_detection 判定规则、generalization_assessment 阈值
    - **Validates: Requirements 1.10, 1.11, 1.12**

  - [ ] 2.10 实现 `compute_cross_window_pattern`
    - 实现跨窗口分析：`error_trend`、`periodic_error_pattern`、`drift_signal`、`consistently_bad_periods`
    - consistently_bad_periods 判定：超过 60% 窗口中 MAPE > 全日平均 1.5 倍
    - _Requirements: 1.13, 1.14_

  - [ ]* 2.11 编写 Property 5 属性测试：跨窗口稳定差时段识别
    - **Property 5: 跨窗口稳定差时段识别**
    - 验证 consistently_bad_periods 仅包含满足条件的时段
    - **Validates: Requirements 1.13, 1.14**

- [ ] 3. Checkpoint — 确保 Dataset_Profiler 所有测试通过
  - Ensure all tests pass, ask the user if questions arise.


- [ ] 4. P0：Dataset_Profiler 集成主循环
  - [ ] 4.1 将 Dataset_Profiler 集成到 `_run_autoresearch_task`
    - 在 `backend-service/api/workflows_enhanced.py` 的 `_run_autoresearch_task` 每轮回测完成后调用 Dataset_Profiler
    - 将输出存入 `run_state["dataset_profiles"]`
    - 确保 validation_profile 在 cv_fold_metrics 不可用时优雅降级
    - _Requirements: 1.15, 1.16_

  - [ ]* 4.2 编写 Dataset_Profiler 集成测试
    - 模拟一轮回测完成后 Dataset_Profiler 被正确调用
    - 验证 run_state 中 dataset_profiles 结构正确
    - 验证 Dataset_Profiler 输出中不包含 error_attribution 字段（职责隔离）
    - _Requirements: 1.15, 1.16_

- [ ] 5. P0.5：Analyst_Agent 实现
  - [ ] 5.1 实现 Analyst_Agent 纯规则归因模块
    - 创建 `backend-service/services/analyst_agent.py`
    - 实现 `AnalystAgent.analyze()` 方法
    - 定义 `ErrorAttribution` 数据模型（`primary_cause`、`contributing_factors`、`evidence`）
    - 实现归因规则优先级链：pattern_mismatch > confirmed_overfit > drift_signal > peak_valley_concentration > period_specific_error > model_divergence > parameter_saturation
    - 兜底返回 `parameter_saturation`
    - _Requirements: 6.2_

  - [ ]* 5.2 编写 Property 18 属性测试：Analyst_Agent 纯规则归因
    - **Property 18: Analyst_Agent 纯规则归因**
    - 验证 error_attribution 包含三个必需字段、primary_cause 选择与优先级一致
    - **Validates: Requirements 6.2**

- [ ] 6. P0.5：Research_Question_Generator 实现
  - [ ] 6.1 实现 Research_Question_Generator
    - 创建 `backend-service/services/research_question_generator.py`
    - 实现 `ResearchQuestionGenerator.generate()` 方法
    - 定义 `ResearchQuestion` 数据模型
    - 实现规则生成逻辑：worst_period 连续 ≥3 窗口 → 时段问题；confirmed_overfit → 过拟合问题；drift_signal > 0 → 漂移问题
    - 实现去重逻辑：关键词重叠率 > 0.8 标记为 recurring
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_

  - [ ]* 6.2 编写 Property 6 属性测试：研究问题规则生成正确性
    - **Property 6: 研究问题规则生成正确性**
    - 验证各规则触发条件正确、每个问题包含四个必需字段
    - **Validates: Requirements 2.2, 2.3**

  - [ ]* 6.3 编写 Property 7 属性测试：研究问题去重
    - **Property 7: 研究问题去重**
    - 验证关键词重叠率 > 0.8 时标记 recurring: true，否则 false
    - **Validates: Requirements 2.6**

  - [ ] 6.4 将 Analyst_Agent + Research_Question_Generator 集成到主循环
    - 在 `_run_autoresearch_task` 中 Dataset_Profiler 之后调用 Analyst_Agent
    - Analyst_Agent 输出传入 Research_Question_Generator
    - 将 research_questions 注入 GLM_Prompt
    - _Requirements: 2.1, 2.5_

- [ ] 7. Checkpoint — 确保 P0 + P0.5 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. P1：Knowledge_Layer 分层知识库
  - [ ] 8.1 实现 Knowledge_Layer 核心
    - 创建 `backend-service/services/knowledge_layer.py`
    - 创建存储目录 `backend-service/data/autoresearch_knowledge/`（含 `raw_cases/`、`patterns/`、`anti_patterns/`、`hypothesis_templates/`）
    - 定义 `KnowledgeClaim`、`ClaimKey`、`KnowledgeConflict` 数据模型
    - 实现 `ingest_run_insight()`：从 run_insight 提取 L2/L3 候选知识
    - 实现 `search()`：支持 scenario_condition_hash、layer、knowledge_type、target_param、min_confidence 过滤
    - 实现 `get_injection_candidates()`：按注入权重公式计算（layer_weight × type_multiplier × scenario_multiplier）
    - 实现 `update_evidence()`：更新 evidence/counter_evidence
    - 实现 atomic write（写临时文件 → rename）
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7_

  - [ ]* 8.2 编写 Property 9 属性测试：知识注入权重计算
    - **Property 9: 知识注入权重计算**
    - 验证 L4 > L3 > L2 > L1 权重、causal_candidate 为 correlational 的 2 倍、不匹配时降至 0.3 倍
    - **Validates: Requirements 3.5, 3.6, 3.7**

  - [ ] 8.3 实现知识衰减与复活机制
    - 实现 `apply_decay()`：超过 30 天未验证 confidence 衰减 0.1，低于 0.3 标记 stale
    - 实现知识复活：stale 状态获得新支撑证据后重新计算 confidence，≥ 0.3 恢复 active
    - _Requirements: 3.8, 3.9, 3.10_

  - [ ]* 8.4 编写 Property 8 属性测试：知识置信度生命周期
    - **Property 8: 知识置信度生命周期**
    - 验证 evidence ≥ 3 且无反证时 confidence ≥ 0.8、衰减规则、stale 判定、复活逻辑
    - **Validates: Requirements 3.4, 3.8, 3.9, 3.10**

  - [ ] 8.5 实现知识冲突解决
    - 实现 `resolve_conflicts()`：检测 target_param 相同但 direction 相反的冲突
    - 按优先级解决：condition 字段数量 > last_validated_at > confidence
    - 无法解决的冲突注入 Research_Question_Generator
    - _Requirements: 3.11, 3.12_

  - [ ]* 8.6 编写 Property 10 属性测试：知识冲突解决优先级
    - **Property 10: 知识冲突解决优先级**
    - 验证冲突解决按 condition 字段数 > 时效性 > 置信度 优先级
    - **Validates: Requirements 3.11**


- [ ] 9. P1：Periodic_Reflection 阶段性反思
  - [ ] 9.1 实现 Periodic_Reflection 核心
    - 创建 `backend-service/services/periodic_reflection.py`
    - 定义 `ReflectionResult`、`ReflectionDecision` 数据模型
    - 实现 `should_trigger()`：n % interval == 0 时触发
    - 实现 `reflect()`：分析 improvement_trend、effective/ineffective_directions、exploration_coverage，输出 reflection_decision
    - 实现 `apply_decision()`：shift_focus 时写入 run_state["current_research_focus"]
    - 支持 reflection_interval 配置（5~50，默认 20）
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 9.2 编写 Property 11 属性测试：反思触发与决策输出
    - **Property 11: 反思触发与决策输出**
    - 验证触发条件 n % interval == 0、decision 字段完整、stagnating 判定规则
    - **Validates: Requirements 4.1, 4.2, 4.4**

  - [ ] 9.3 实现 Research Focus 采样偏置
    - 在主循环采样逻辑中集成 current_research_focus
    - priority_layers 中已激活层参数采样概率 2 倍
    - avoid_layers 中参数采样概率 0.5 倍
    - priority_layers 包含未激活层时触发 force_activate
    - _Requirements: 4.5, 4.6_

  - [ ]* 9.4 编写 Property 12 属性测试：Research Focus 采样偏置
    - **Property 12: Research Focus 采样偏置**
    - 验证 priority_layers 2 倍概率、avoid_layers 0.5 倍概率、force_activate 逻辑
    - **Validates: Requirements 4.5, 4.6**

  - [ ] 9.5 实现前瞻预测与元反思
    - 实现 `projected_final_performance` 基于对数/幂律模型拟合
    - 实现 gap_to_target、estimated_rounds_to_target 计算
    - 实现 Meta_Reflection：追踪 adoption_rate，连续 3 次未采纳输出 meta_warning
    - _Requirements: 4.11, 4.12, 4.13, 4.14_

  - [ ]* 9.6 编写 Property 13 + 14 属性测试
    - **Property 13: 前瞻预测与建议触发**
    - **Property 14: 元反思警告触发**
    - 验证预测模型拟合、建议触发条件、adoption_rate 计算
    - **Validates: Requirements 4.11, 4.12, 4.13, 4.14**

  - [ ] 9.7 将 Periodic_Reflection 集成到主循环
    - 在 `_run_autoresearch_task` 中按 reflection_interval 触发反思
    - 反思结果存入 run_state["periodic_reflections"]
    - 最近一次 reflection_decision 注入 GLM_Prompt
    - _Requirements: 4.9, 4.10_

- [ ] 10. Checkpoint — 确保 P1 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. P2：Experiment_Quality 实验质量评分
  - [ ] 11.1 实现 ExperimentQualityScorer
    - 创建 `backend-service/services/experiment_quality.py`
    - 定义 `ExperimentQuality` 数据模型
    - 实现 `score()` 方法：计算 single_variable_control、hypothesis_clarity、expected_outcome_measurable、risk_level、knowledge_gain_estimate、composite_score
    - 实现 `rank_experiments()`：归一化排序公式，早期 w_info > w_metric，后期 w_metric > w_info
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 11.2 编写 Property 15 属性测试：实验质量评分与动态权重排序
    - **Property 15: 实验质量评分与动态权重排序**
    - 验证各维度评分在 [0,1] 范围、早期/后期权重切换、排序一致性
    - **Validates: Requirements 5.1, 5.2**

  - [ ] 11.3 实现 InformationGainPruner
    - 实现 `compute_info_gain()`：计算各参数区间信息增益
    - 实现 `prune()`：连续 3 轮 < 0.01 标记 exhausted 并排除
    - 维护 space_contraction_log
    - _Requirements: 5.4, 5.5, 5.6_

  - [ ]* 11.4 编写 Property 16 属性测试：信息增益与搜索空间收缩
    - **Property 16: 信息增益与搜索空间收缩**
    - 验证连续 3 轮 < 0.01 标记 exhausted、未满足条件不排除
    - **Validates: Requirements 5.4, 5.5**

  - [ ] 11.5 实现 ProactivePredictor
    - 实现 `predict()`：基于对数/幂律模型拟合预测 predicted_marginal_gain 和 rounds_to_diminishing_returns
    - 连续 3 轮 < 0.05% 建议 suggest_early_convergence
    - 斜率 > 0.1%/轮建议 suggest_extension
    - _Requirements: 5.7, 5.8, 5.9_

  - [ ]* 11.6 编写 Property 17 属性测试：收益递减预测与建议
    - **Property 17: 收益递减预测与建议**
    - 验证预测输出、early_convergence 和 extension 建议触发条件
    - **Validates: Requirements 5.7, 5.8, 5.9**

  - [ ] 11.7 实现 ParameterInteractionGraph
    - 实现 `validate_combination()`：验证参数组合是否违反硬约束
    - 实现 `filter_valid_combinations()`：过滤违反硬约束的组合
    - 定义硬约束规则（如 lags 不能超过 train_days × 96）
    - _Requirements: 5.12_

  - [ ]* 11.8 编写 Property 20 属性测试：参数交互约束执行
    - **Property 20: 参数交互约束执行**
    - 验证正确排除违反硬约束的组合、不排除合法组合
    - **Validates: Requirements 5.12**

  - [ ] 11.9 实现因果推断模块并集成 Knowledge_Layer
    - 实现 Causal_Inference_Module：输出 causal_attribution（effective_config、enabling_conditions、confidence）
    - 将因果归因结果反馈给 Knowledge_Layer 作为 evidence/counter_evidence
    - _Requirements: 5.10, 5.11_

- [ ] 12. Checkpoint — 确保 P2 全部测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12A. 第四代 P0.6：Candidate_Planner 候选规划器
  - [x] 12A.1 实现 AutoResearchCandidatePlanner
    - 创建 `backend-service/services/autoresearch_candidate_planner.py`
    - 实现 `build_scoreboard()`：从历史 `iterations` 和 `latest_batch_groups` 汇总方向 attempts/successes/failures/timeout_count/best_score_advantage/last_tried_iteration/coverage_gap
    - 实现 `build_slots()`：按 batch_size 生成参数、特征、模型、数据、风险方向槽位
    - `batch_size >= 5` 时同轮覆盖五类方向；`batch_size < 5` 时按覆盖缺口轮换
    - _Requirements: 5A.1, 5A.2, 5A.3, 5A.4, 5A.6, 5A.7_

  - [x]* 12A.2 编写候选规划器单元测试
    - 创建 `backend-service/tests/test_autoresearch_candidate_planner.py`
    - 验证 batch_size=3 时生成 exploit/diversify/explore_risk 三类角色
    - 验证 batch_size=5 时覆盖 parameter/feature/model/data/risk 五类方向
    - 验证历史覆盖缺口会提高未探索方向优先级
    - 验证 timeout 不会永久禁用某方向
    - _Requirements: 5A.1, 5A.3, 5A.4, 5A.6, 5A.7_

  - [x] 12A.3 将 Candidate_Planner 接入 AutoResearch batch group 生成
    - 修改 `backend-service/api/workflows_enhanced.py`
    - batch 模式中先调用 planner 生成 slots
    - group 1 保留主候选，补充规划元数据
    - group 2+ 优先使用方向匹配的 GLM proposal；无匹配时用注册表目标层采样补齐
    - _Requirements: 5A.1, 5A.5, 5A.10_

  - [x] 12A.4 将规划元数据写入 batch_groups 和 trial ledger
    - 每个 group 写入 `target_direction`、`target_layer`、`exploration_role`、`planner_reason`
    - 失败/超时时保留方向元数据和错误原因
    - _Requirements: 5A.8, 5A.9_

  - [x] 12A.5 最小验证
    - 运行候选规划器单测、batch selection/persister 相关测试和语法检查
    - 不要求启动完整长 run；完整 run 作为人工体验验证项
    - 已验证：`py_compile`、`tabnanny`、全部 `tests/test_autoresearch*.py` 和 `tests/test_api_endpoints.py` 通过
    - _Requirements: 5A.1-5A.10_

- [ ] 12B. 第四代 P0.7：探索策略质量提升与主线去偏
  - [ ] 12B.1 实现探索健康诊断
    - 扩展 Candidate_Planner scoreboard，记录 `primary_direction_ratio`、`direction_coverage`、`negative_score_count`、`ineffective_count`、`timeout_recovered_count`、`evidence_strength`
    - 输出当前 run 的探索健康摘要：主线是否偏向参数、哪些方向只在并发组出现、哪些方向成功但无收益
    - 将诊断写入 run status / run insight，供前端和汇报文档展示
    - _Requirements: 5B.1, 5B.7, 5B.8, 5B.9_

  - [ ] 12B.2 实现主候选轮换策略
    - 当主候选连续偏向 `parameter` 且收益平台期出现时，按 scoreboard 推荐 `feature` / `model` / `data` / `risk` 作为下一轮主候选方向
    - group 1 不再长期固定为参数探索；并发组的有效方向可以晋升到下一轮主线
    - 保留可解释字段：`recommended_primary_direction`、`primary_rotation_reason`、`previous_primary_direction`
    - _Requirements: 5B.1, 5B.2_

  - [ ] 12B.3 对齐 `active_layers` 与 planner 目标层语义
    - 当 planner 推荐未激活层时，生成 `force_activate_recommendation` 或 runtime activation 记录
    - 明确区分“目标层已激活”“目标层未激活但允许注册表定向采样”“目标层被拒绝”三种状态
    - 前端展示 `layer_activation_status`，避免出现实际执行了 model/data/risk 但状态仍显示未激活的歧义
    - _Requirements: 5B.2, 5B.8_

  - [ ] 12B.4 实现研究问题生命周期与去重
    - 为 research question 增加 `question_key`、`first_seen_iteration`、`last_seen_iteration`、`evidence_count`、`tested_patch_fingerprints`、`status`
    - 状态包括 `open`、`testing`、`resolved`、`stale`，同一问题重复出现时更新证据而不是生成新问题
    - 已验证或长期无收益的问题降低后续注入权重
    - _Requirements: 5B.3_

  - [ ] 12B.5 实现单窗口/多窗口证据强度门控
    - 为每个候选、batch group、knowledge claim 标注 `evidence_strength`
    - 单窗口正收益标记为 `needs_multi_window_confirmation`，不得直接升级为高置信知识
    - 多窗口复验通过后才允许进入高置信 claim 或成为默认策略
    - _Requirements: 5B.5, 5B.6_

  - [ ] 12B.6 显式标识规则/记忆 fallback
    - 当 GLM 未启用时，proposal 和 batch group 写入 `llm_used=false`、`rule_fallback=true`、`proposal_source=rule_memory`
    - 前端不再把规则/记忆候选显示为“GLM 候选”
    - run insight 记录本轮是否真正调用 LLM，避免误判模型智能化程度
    - _Requirements: 5B.4, 5B.8_

  - [ ] 12B.7 编写回归测试与端到端验证清单
    - 补充 Candidate_Planner 单测：主线去偏、未激活层推荐、失败方向降权但不永久禁用
    - 补充 ResearchQuestionState 单测：去重、状态迁移、已测试 fingerprint 追踪
    - 补充 Knowledge_Layer 单测：单窗口证据不得变成高置信 claim，多窗口复验后可提升
    - 前端构建验证展示字段不破坏现有页面；长 run 人工验证 10~20 轮观察探索健康摘要
    - _Requirements: 5B.1-5B.9_


- [ ] 13. P3：多智能体轻量流水线
  - [ ] 13.1 实现 Agent_Orchestrator 编排器
    - 创建 `backend-service/services/agent_orchestrator.py`
    - 实现 `AgentOrchestrator` 类，支持 `multi_agent` 和 `single_agent` 两种模式
    - 实现 `run_pipeline()`：编排 Dataset_Profiler → Analyst → RQG → Hypothesis(GLM) → Designer 流水线
    - 实现降级逻辑：GLM 调用失败自动回退到 single_agent 模式
    - 实现 Agent 间结构化 JSON 消息传递（from_agent、to_agent、message_type、payload、timestamp）
    - 记录 agent_traces 到 run_state["agent_traces"]
    - _Requirements: 6.1, 6.7, 6.8, 6.9, 6.10_

  - [ ] 13.2 实现假设结构化去重（Patch_Fingerprint）
    - 在 Hypothesis_Agent 中实现 Patch_Fingerprint 索引（target_function_id + param_key + direction）
    - 新假设与已否证 fingerprint 匹配时确定性拒绝
    - 维护 disproved_fingerprints 索引
    - _Requirements: 6.5, 6.6_

  - [ ]* 13.3 编写 Property 19 属性测试：假设结构化去重
    - **Property 19: 假设结构化去重**
    - 验证匹配时确定性拒绝、不匹配时通过
    - **Validates: Requirements 6.5**

  - [ ] 13.4 实现 Designer_Agent 纯规则翻译
    - 复用现有 `_translate_intent_to_patches` 逻辑
    - 封装为独立的 Designer_Agent 类
    - 意图无法翻译时返回空 patch
    - _Requirements: 6.4_

  - [ ] 13.5 将 Agent_Orchestrator 集成到主循环
    - 在 `_run_autoresearch_task` 中根据 `agent_mode` 参数选择模式
    - multi_agent 模式走完整流水线
    - single_agent 模式回退到现有 `_glm_generate_proposal_candidates` 逻辑
    - 支持启动参数 `agent_mode`（默认 `single_agent`）
    - _Requirements: 6.9, 6.10_

- [ ] 14. P3：API 接口新增与数据管理
  - [ ] 14.1 实现知识检索 API
    - 在 `backend-service/api/workflows_enhanced.py` 中新增 `GET /api/workflows/enhanced/knowledge/search`
    - 支持 scenario_condition_hash、layer、min_confidence、knowledge_type、target_param 过滤
    - 返回统一错误格式
    - _Requirements: 3.13, 8.2, 8.3_

  - [ ] 14.2 实现数据集画像与管理 API
    - 新增 `GET /api/workflows/enhanced/datasets/{dataset_id}/profile` — 数据集画像查询
    - 新增 `POST /api/workflows/enhanced/datasets/register` — 数据集注册（接收 file_path 或 upload_id，返回 dataset_id）
    - 新增 `GET /api/workflows/enhanced/datasets` — 数据集列表
    - 文件格式无法解析时返回具体错误信息
    - _Requirements: 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ] 14.3 实现研究问题与反思记录查询 API
    - 新增 `GET /api/workflows/enhanced/auto-research/{run_id}/research-questions` — 研究问题查询
    - 新增 `GET /api/workflows/enhanced/auto-research/{run_id}/reflections` — 反思记录查询
    - _Requirements: 7.2, 7.3, 8.2_

  - [ ] 14.4 实现时序可视化数据存储
    - 每轮回测完成后将时序数据（训练集、测试集真实值、预测值、时间戳、峰谷标注）存入 run_state["iteration_plot_data"]
    - _Requirements: 7.1_

  - [ ]* 14.5 编写 API 集成测试
    - 在 `backend-service/tests/test_api_endpoints.py` 中使用 httpx + FastAPI TestClient
    - 测试所有新增 API 端点可访问性、返回格式正确性、错误格式统一性
    - _Requirements: 8.2, 8.3_

- [ ] 15. 数据结构序列化 Round-Trip 验证
  - [ ]* 15.1 编写 Property 21 属性测试：核心数据结构序列化 Round-Trip
    - **Property 21: 核心数据结构序列化 Round-Trip**
    - 验证所有核心数据结构 JSON 序列化后再反序列化产生等价对象
    - 覆盖 train_profile、validation_profile、test_profile、tri_dataset_diagnosis、research_question、experiment_quality、knowledge_claim、periodic_reflection、agent_trace、error_attribution
    - **Validates: Requirements 8.1**

- [ ] 16. Final Checkpoint — 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标记 `*` 的子任务为可选测试任务，可跳过以加速 MVP 交付
- 每个任务引用具体需求编号，确保可追溯性
- Checkpoint 确保增量验证，避免问题累积
- 属性测试验证设计文档中定义的 Correctness Properties
- 单元测试验证具体场景和边界条件
- 所有新模块作为独立 Python 文件存在于 `backend-service/services/`，通过明确接口与主循环集成
- 测试文件统一放在 `backend-service/tests/` 目录下
- 降级链路：multi_agent → single_agent → 注册表随机采样

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1"] },
    { "id": 1, "tasks": ["1.2", "2.2"] },
    { "id": 2, "tasks": ["2.3", "2.4", "2.6"] },
    { "id": 3, "tasks": ["2.5", "2.7", "2.8"] },
    { "id": 4, "tasks": ["2.9", "2.10"] },
    { "id": 5, "tasks": ["2.11", "4.1"] },
    { "id": 6, "tasks": ["4.2", "5.1"] },
    { "id": 7, "tasks": ["5.2", "6.1"] },
    { "id": 8, "tasks": ["6.2", "6.3", "6.4"] },
    { "id": 9, "tasks": ["8.1"] },
    { "id": 10, "tasks": ["8.2", "8.3"] },
    { "id": 11, "tasks": ["8.4", "8.5"] },
    { "id": 12, "tasks": ["8.6", "9.1"] },
    { "id": 13, "tasks": ["9.2", "9.3"] },
    { "id": 14, "tasks": ["9.4", "9.5"] },
    { "id": 15, "tasks": ["9.6", "9.7"] },
    { "id": 16, "tasks": ["11.1", "11.3", "11.5", "11.7"] },
    { "id": 17, "tasks": ["11.2", "11.4", "11.6", "11.8", "11.9"] },
    { "id": 18, "tasks": ["13.1", "13.2"] },
    { "id": 19, "tasks": ["13.3", "13.4"] },
    { "id": 20, "tasks": ["13.5", "14.1", "14.2", "14.3", "14.4"] },
    { "id": 21, "tasks": ["14.5", "15.1"] }
  ]
}
```
