# Research Cockpit 信息架构收敛需求设计

日期：2026-05-25

## 1. 背景

当前 AutoResearch 前端已经接入探索健康、证据、研究问题、知识治理等控制面字段，但展示方式偏字段平铺，`研究驾驶舱` 和 `自主研究员产物` 信息重复，导致用户看到的是大量 tag 和英文 key，而不是清晰的研究闭环。

本次目标不是增加后端字段，也不是扩大搜索空间，而是把前端展示和文档表达收敛成五张核心卡片。

## 2. 总目标

将 AutoResearch 控制台的信息架构收敛为五张卡片：

1. Experiment 实验卡
2. Evidence 证据卡
3. Question 问题卡
4. Knowledge 知识卡
5. Strategy 策略卡

第一张卡必须是 Experiment 实验卡，因为用户打开页面第一眼要先判断实验当前状态。

## 3. 用户成功标准

- 用户第一眼能看到当前实验跑到第几轮、是否成功、失败原因。
- 用户能快速判断结果证据是否可靠、是否需要复验。
- 用户能看到系统正在研究的问题，而不是重复模板刷屏。
- 用户能知道系统学到了什么，哪些只是候选知识。
- 用户能在最后看到系统下一步为什么这么跑。
- 英文字段默认不平铺；首次出现必须带中文注释，调试字段放入详情折叠。

## 4. 五卡片定义

### 4.1 Experiment 实验卡

回答：这轮跑了什么？

默认展示字段：

- `iteration`（第几轮）
- `group_idx`（第几组）
- `target_direction`（研究方向）
- `changed_variables`（改了什么）
- `status`（成功/失败）
- `failure_reason`（失败原因）

详情折叠字段：

- `target_layer`（目标层）
- `patch_fingerprint`（补丁指纹）
- batch group JSON（并发组原始记录）

### 4.2 Evidence 证据卡

回答：结果靠不靠谱？

默认展示字段：

- `windows_total`（跑了几个窗口）
- `windows_success`（成功几个窗口）
- `mape_improvement`（MAPE 提升幅度）
- `evidence_strength`（证据强度）
- `needs_confirmation`（是否需要复验）

前端应翻译成自然语言，例如：

- 单窗口正收益，需要复验。
- 多窗口确认，可以作为有效证据。
- 证据不足，不能沉淀为知识。

### 4.3 Question 问题卡

回答：系统现在在研究什么？

默认展示字段：

- `question`（问题）
- `status`（问题状态：open/testing/resolved/stale）
- `evidence_count`（证据数）
- `next_experiment_goal`（下一步验证什么）
- `source`（来源：GLM/规则/回退）

详情折叠字段：

- `candidate_causes`（候选原因）
- `evidence_refs`（证据引用）
- `expected_patch_intent`（预期补丁意图）

### 4.4 Knowledge 知识卡

回答：系统学到了什么？

默认展示字段：

- `claim`（知识声明）
- `status`（知识状态：candidate/active/conflicted/stale/rejected）
- `confidence`（置信度）
- `support_count`（支持证据数）
- `counter_count`（反证数）

前端应翻译成自然语言，例如：

- 候选知识：单窗口支持，等待复验。
- 有效知识：多窗口确认，可优先注入。
- 冲突知识：存在反证，需要转成研究问题。

### 4.5 Strategy 策略卡

回答：下一步为什么这么跑？

默认展示字段：

- `current_state`（当前研究状态）
- `primary_direction`（当前主线方向）
- `recommended_next_direction`（推荐下一方向）
- `reason`（理由）
- `coverage`（方向覆盖）

这张卡放最后，用于解释系统策略，而不是抢占实验状态视线。

## 5. 设计约束

- 不改后端字段结构。
- 不重启或停止当前后端、worker、run。
- 前端只做展示收敛和中文解释。
- 旧 run 字段缺失时必须降级显示，不报错。
- 调试信息保留，但默认折叠。
- 不继续堆更多 tag。

## 6. 验收标准

- AutoResearch 页面出现五张卡片，顺序为 Experiment、Evidence、Question、Knowledge、Strategy。
- 页面不再同时平铺旧的研究驾驶舱和自主研究员产物两套重复区域。
- 关键英文字段首次出现带中文注释。
- 旧 run 或首轮未完成时能显示空状态说明。
- `npm run build` 通过，允许保留既有 Tailwind 和 chunk warning。
