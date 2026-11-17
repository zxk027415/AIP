<!-- @AI_GENERATED -->
# 设计通俗对照版

光伏故障诊断双路径生产接入（pv-fault-dual-path-serving）

> 这份文档是 `design.md` 的大白话对照版。正式验收口径以 `design.md` 为准；本版用同一套比喻解释 Req13–15 与 R1–R5 修订后的设计。

## 1. 一套比喻先记住

- **公共数据日历** = `Data_Watermark` — 每台设备的数据实际上到哪一天、哪一刻。两个班组共用，不看墙上现实时间。
- **两个班组** = `legacy_day` — 传统按天班组与 `seq_annotation` — 全天序列班组。
- **逐日记账** = `Seq_Device_Day_Ledger` — 序列班组按“设备 + 自然日”一格一格记处理状态。
- **主将 / 候补** = 每个班组自己的 `champion` — 当前冠军模型与 `challengers` — 挑战者模型；`retired` — 退役主将可供回滚。
- **演习场** = `Shadow_Compare_Runner` — 两个班组的当前主将在同一批完整历史设备日上对跑，只出证据，不碰生产账。
- **换将** = `Path_Internal_Promotion` — 同一个班组内部用更好的候补替换主将，不换班组。
- **换班组** = `Cross_Path_Switch` — 把生产当班牌从 legacy_day 改成 seq_annotation，或反过来。
- **生效边界** = `Path_Activation_Epoch` — 本次换班后，新班组从哪些设备日开始负责生产。
- **连续完成前沿** = `Continuous_Completion_Frontier` — 给人看的“连续完成到哪天”摘要，不是序列处理的权威账本。

一句话总结：**公共数据日历说明“货到了哪里”，逐日记账说明“序列班组每一天处理成什么状态”，生效边界说明“这次换班从哪里开始负责”，模型登记说明“每个班组现在谁是主将”。四件事不能混成一个游标。**

## 2. 两个班组怎么工作

### 传统按天班组（legacy_day）

它像能随到随检的老师傅：公共数据日历当天来了多少点，它就可以从自己的书签继续检多少点。它按自然日拆开处理，不把两天的数据揉成一份；完成后把自己的书签推进到真正处理过的最晚业务时间。没有新点、时间坏掉、写入失败时，书签都不动。

它给的是**天级判断**。它不产出 288 个逐点结果，不能和序列班组的逐点输出混淆。

### 全天序列班组（seq_annotation）

它像精细质检班组：必须拿到一个独立自然日的数据，放进 288 个五分钟格子，再逐点判断。只处理公共数据日历“今天”之前的历史整天；当天仍可能继续到数据，所以顺延。完整性不足、白天连续空槽太长或 24 小时覆盖不够，就不出该天预测。

它绝不把两天拼成一张 288 格表。一天一个网格、一次预测、一个审核批次。

## 3. 最重要的修订：不再“前一天卡住后面所有天”

旧想法把序列进度当成一根从前往后的书签。它会陷入两难：

- 书签越过一个未完整日，那个日期以后补齐也可能永远捞不回来；
- 为了不越洞而停住，又会让前一天的数据缺口堵住后面所有完整日期，形成队头阻塞。

新设计改成**逐日记账**。账本键由六项组成：`slot` — 槽位、`modeling_path` — 路径、`site_id` — 站点、`device_id` — 设备、`branch_id` — 支路、`business_date` — 业务日。可以理解为“哪个生产槽、哪个班组、哪台设备、哪一天”的独立账页。

每页状态：

- `waiting_data` — 数据还不够；
- `ready` — 已满足条件，等待本轮配额；
- `running` — 正在处理；
- `succeeded` — 已成功并绑定不可变审核批次；
- `failed` — 本次失败，可在后续轮次重试；
- `revision_pending` — 原来成功过，但输入数据后来变了，等待修订。

因此，如果 6 月 1 日还缺数据、6 月 2 日已经完整：6 月 1 日留在 waiting_data，6 月 2 日照常独立预测并成功。**多日积压是逐日独立消化，不拼接，也不因前一天未完整而整体停工。**

单轮有 `max_device_days_per_cycle` — 最多处理设备日数，默认 50、合法范围 1–1000。配置成 0、负数或大于 1000 时，系统拒绝这个配置、记明错误，并把实际生效值回退为 50。超过有效上限时按 business_date 升序取前 50 个，剩余仍是 ready，下一轮继续；这叫“分批消化积压”，不是把 50 天拼成一次模型输入。

## 4. 连续完成前沿只是摘要

为了让看板容易理解，仍保留一个“从本次责任起点开始，连续成功到哪天”的摘要，这就是 Continuous Completion Frontier。它可以帮助缩小查询范围，但不能回答“某个具体设备日到底处理过没有”。

一旦摘要和逐日账本冲突，**永远以逐日账本为准**。序列班组的 Device Cursor 不再是唯一进度真相，也不能用它把某天直接排除在候选之外。

## 5. 晚到数据怎么修订，而不是覆盖

每个序列设备日会计算 `input_fingerprint` — 输入数据指纹：把当天所有业务时间和值按稳定顺序排列后算摘要。

- 已成功日期再次检查时，如果指纹没变，直接跳过，不重复推理。
- 如果晚到点让指纹变化，账页进入 revision_pending，新建一个修订批次。
- 新批次的 `supersedes_batch_id` — 被取代批次 ID 指向旧 `batch_id` — 原批次 ID。
- 原审核批次永远保留，不修改、不删除。

这就像会计发现旧账依据发生变化：不能拿橡皮擦改旧页，而是开一张“修订凭证”，注明替代哪一张。

## 6. 切换班组不等于从最早历史全部重跑

旧说法“新路径没有自己的书签，所以从最早历史重建”已撤销。它会让第一次切换把数月甚至数年历史都塞进生产队列，挤占当天检测。

现在每次启用或重新启用一个班组，都建立一个新的**生效边界（Path Activation Epoch）**。它回答：“这次值班从每台设备的哪一天开始负责？”早于边界的历史日期不属于本周期生产责任，不算漏检，也不逐条制造跳过记录。

三种模式：

1. `cutover_only` — 仅从切换点接管，默认模式。按每台设备自己的公共数据日历，从最近一个已经结束的设备日开始。
2. `recent_window` — 有限回看。可指定 `backfill_days` — 回看天数，但不能超过 `max_backfill_days` — 最大回看天数，默认上限 14。
3. `full_backfill` — 全量历史。只有人明确选择才允许，从该设备最早到达日回放。

不同设备到数进度不同，所以 `activation_watermark` — 启用时设备水位与 `effective_from_date` — 生效日期都按设备分别保存。某设备切换时一条数据都没有，就先不硬设日期；第一次数据到达时，再以那次到达日建立它的边界。

同一路径以后重新当班，会建立新的 Epoch。中间由另一个班组值班的日期不自动变成这次的生产积压，也不把另一班组的结果冒充成自己处理过。

## 7. full_backfill 的“历史回放车道”

全量历史回放不进生产车道，而交给 `Backfill_Runner` — 限流历史回放执行器。切换时会把日期明确分成两段：从最早历史日到 `production_cutover_date` — 在线生产接管日之前，由 `execution_lane=historical_backfill` — 历史车道排他认领；从 production_cutover_date 起，由 `execution_lane=production` — 生产车道认领。两段不能重叠，生产查询必须排除历史已认领日期，所以同一天不会被两条车道各跑一次。

它有自己的队列，但“单独线程池”还不够，因为 CPU、内存和数据库连接仍是共用的。因此再加一个容量仲裁员：先按 `production_capacity_reserved_ratio` — 生产容量预留比例给生产锁定令牌，默认 80%，历史车道只能拿剩余令牌；内存或数据库连接到低水位时，历史任务暂停或降速，先把令牌还给生产。

历史任务失败时仍保留这段日期的认领，等后续重试，不能因为失败又掉回生产积压；只有人工明确取消并释放认领后才能重新分派。历史结果按 backfill_task_id 查询，不推进生产的逐日账本，不推进生产连续完成前沿，也不算进生产责任统计。

名字容易混，必须分清：

- **BackfillRunner**：重跑历史**检测**，解决“我要回看以前的设备日”。
- **BackfillLoop（Req12）**：把人工审核**标签**回流到共享标签池，解决“模型以后重训要学到人工裁决”。

一个是历史检测车道，一个是标签学习闭环，绝不是同一组件。

## 8. 每个班组都有自己的主将和候补

`PV_Model_Registry` — 光伏模型登记是 pv_fault 槽位唯一可写真相。每条路径不是只存“最后一个模型”，而是三层：

- `champion` — 当前主将，真正供这个班组生产检测；
- `challengers` — 候补，重训后等待同口径考核；
- `retired` — 退役主将，保留模型引用和成绩，必要时可回滚。

每个模型登记至少记录 `model_ref` — 模型引用、`evaluation_id` — 评估 ID、`gate_metric_value` — 守门指标、`registered_at` — 登记时间。

### 换将：班组不变

候补和主将必须用同一批合法样本、同一划分、同一随机种子、同一评分指标、同一生产契约考试。候补严格更好才上岗，旧主将进入 retired。Legacy 也必须过这道门，不再“重训完成就自动上生产”。

换将只改变这个班组内部谁是 Champion，**不改变 production_path**。比如当前生产班组还是 legacy_day，只是它的 RF 主将从 v3 换成 v4。

### 换班组：生产思路改变

把 production_path 从 legacy_day 改成 seq_annotation，才叫换班组。它不是模型晋升的另一种叫法，必须经过跨路径演习证据、九项准入、人工确认，并建立新的生效边界。

## 9. 为什么 PV Model Registry 必须是唯一可写真相

项目里还有一个通用 `Deployment Arena` — 部署演习场，它原本有自己的槽位存储和切换引擎。如果 pv_fault 允许两边都写，就可能出现“页面说主将 A，调度器实际加载主将 B”。

因此：

- pv_fault 的模型身份和生产路径只能写 PV Model Registry。
- Production Path Pointer 不是第二本账，只是读取/修改 Registry 里 `production_path` 字段的门面；调度器、切换接口、fallback 和前端最终都看同一个字段。
- Deployment Arena 通过只读适配器展示同一份状态。
- `DeploymentSlotStore` — 通用槽位存储和 `SwitchEngine` — 通用切换引擎尝试写 pv_fault 时必须明确拒绝，不能偷偷双写或绕过登记。
- 其他非 pv_fault 槽位继续照旧可写，不受影响。

## 10. 演习场只比较两边当前主将

Shadow Compare 就像两个班组的主将拿同一批完整历史设备日做演习：

- 只加载 legacy_day Champion 和 seq_annotation Champion；
- 任一边没有合格主将或模型工件打不开，演习报告直接拒绝生成；
- 候补和退役主将不能临时顶替，以免证据和实际生产模型不一致；
- 演习不挪生产书签、不写生产预测/批次、不改模型登记、不改 production_path、不建 Epoch、不记晋升或切换事件。

报告分三层，缺一层都不能作为换班组依据：

1. **共同口径**：把 Seq 的逐点结果按报告写明的投影规则汇总成天级，再和 Legacy 比天级准确率、故障召回率、误报率、一致率、覆盖率。
2. **Seq 原生增益**：逐点 F1、故障段 IoU、边界偏差、夜间误报、288 点契约。Legacy 没有对应值时要老实写“无 Legacy 对应值”，不能硬做横向优劣结论。
3. **生产运行指标**：两边延迟、门禁顺延比例、推理失败率、每日容量、模型加载成功率。

只说“Seq 宏平均 F1 更高”不够，因为两条路径输出粒度不同，而且生产代价也不同。

## 11. 换班组前的九道门

跨路径请求要带 `comparison_id` — Shadow 报告 ID、`activation_mode` — 启用模式、必要时的 `backfill_days`、`confirm` — 人工确认 JSON 布尔 true、`operator` — 操作人、`reason` — 原因。

九项必须全部通过：

1. 目标路径有 Champion，工件可加载；
2. 目标路径生产契约通过；
3. 报告中的两边 model_ref 仍等于当前双 Champion；
4. 报告没有过期，默认有效 14 天；
5. 可比设备日至少默认 200，覆盖率至少默认 90%；
6. 不可比项里没有 blocking；门禁顺延属于 deferred，不和模型执行异常混为一谈；
7. activation_mode 合法；
8. 能算出每台设备的 effective_from_date；
9. confirm 是真正的 JSON `true`，不是字符串 `"true"`。

任一道失败，production_path、Epoch、审计事件全部不动，并一次性告诉用户哪些条件没过。全部通过后，才原子完成三件事：改当班牌、建立新 Epoch、追加 Path Switch Event。

## 12. 两本审计流水绝不混

### Promotion Event：换将流水

记录同一班组内部主将更替，含 `promotion_event_id` — 晋升事件 ID、`modeling_path` — 哪个班组、晋升后主将、被评估候补、评估 ID、晋升时间。它不表示换班组。

### Path Switch Event：换班组流水

记录 production_path 改变，含 `path_switch_event_id` — 切换事件 ID、`from_path` / `to_path` — 原班组/新班组、comparison_id、activation_epoch_id、`effective_from_date` — 所有有数据设备生效日中的最早日期、`device_scope_digest` — 按设备边界清单的稳定摘要、`device_scope_count` — 设备数、生效模式、操作人、原因、切换时间。每台设备的完整日期仍到 activation_epoch_id 对应的不可变明细里查；事件用“最早日期 + 摘要 + 数量”固定口径，不能有人写最小值、有人写最大值、有人写一段随意文字。它不表示模型内部晋升。

两本流水都只追加，不改旧记录、不删旧记录，也不能互相冒充。

## 13. 生产退化时先做便宜的恢复

恢复顺序固定：

1. 如果当前班组只是主将精度退化，但有一个考核合格的候补，先**换将**，班组不变。
2. 只有整条路径不可用时，才考虑换到 fallback 班组。整路径不可用包括：没有合格候补、当前主将工件打不开、门禁连续默认 24 轮覆盖不到任何设备日、生产契约失败、或整路径连续默认 3 轮 failed。
3. 即使要切 fallback，也不能“一键逃生”绕过 Shadow 和九项准入；仍要有匹配当前双 Champion 的证据和人工确认。

所以“模型不好”不自动等于“换建模思路”。先换将，实在整条班组不可用才换班组。

## 14. 数据库和登记怎么变

### 逐日账本表

新增 `seq_device_day_ledger`，六元组做唯一键，保存状态、input_fingerprint、batch_id、attempt_count、last_error、processed_at 和 activation_epoch_id。

### 生效边界表

新增 `path_activation_epochs` 保存每次启用的总记录；新增 `path_activation_device_scopes` 保存每台设备自己的 activation_watermark、effective_from_date 和 production_cutover_date；再新增 `path_activation_lane_claims`，用两行半开日期范围分别保存 historical_backfill 与 production 的排他认领、状态和 backfill_task_id。这样一个设备可以同时拥有“历史范围归历史车道、在线范围归生产车道”两条清晰记录，不会被单个字段说不清，也不会被生产重复拿走。

### 原有书签和预测记录

Device Cursor、Prediction Record 继续按 `slot + modeling_path` 分区。Seq 的 cursor 会加语义标识，明确它是连续完成前沿摘要；具体某天是否成功必须查逐日账本。

### 模型登记迁移

旧的 `path_models[path] = 最新模型` 迁成 `champion/challengers/retired`。能确认正在生产且工件/契约合格的旧模型成为 Champion；无法确认时宁可放 Challengers 并阻止切换，也不猜成合格主将。

旧审计能明确判断为同路径换将的迁到 Promotion Event；明确 production_path 改变的迁到 Path Switch Event；语义不清的留在旧审计只读区，不伪造新历史。

## 15. 几条关键流程走一遍

### 多日积压

调度器先读取当前 Epoch 的设备生效边界，再从逐日账本取本轮最多 50 个设备日。6 月 1 日未完整就记 waiting_data；6 月 2 日完整就独立跑一张 288 网格、写一个批次、记 succeeded。循环继续，不因 6 月 1 日卡住。

### 晚到修订

一个 succeeded 日期重新算指纹；相同就跳过，不同就进入 revision_pending，重跑当天并写新批次，新批次指向旧批次。旧审核事实不覆盖。

### 路径内换将

同一个班组的候补和主将同卷考试；候补严格更好才成为新主将，旧主将进 retired，只追加 Promotion Event，production_path 不变。

### 跨路径换班组

先由双 Champion 在演习场生成三层证据；人工选择启用模式并确认；九项全过后改 production_path、建新 Epoch、追加 Path Switch Event。切换不自动重放最早历史。

### 全量历史回放

人工明确选 full_backfill 后，先把历史日期范围排他标成 historical_backfill，在线接管日之后标成 production，再把历史范围交给独立 BackfillRunner。容量仲裁员先为生产保留至少 80% 令牌，历史任务只用剩余令牌；历史失败保留认领等待重试，不污染生产逐日账本，也不会回流成生产积压。

## 16. 前端应该让用户看懂什么

控制台不能只放一个“切换”按钮，而要把两层治理讲清：

- 当前 production_path、两边 Champion、当前 Epoch；
- 两条路径各自的检测状态、Device Cursor 和最近审核批次，默认最近 10 个并可翻页；
- 每个设备日的 `point_count / expected_point_count` 完整性进度和门禁放行状态；
- 序列逐日账本状态，能看出“前一天等待、后一天成功”；
- Seq Device Cursor 明确标“连续完成前沿摘要”；
- 每条路径的 Champion / Challengers / Retired；
- “换将”和“换班组”两个不同入口；
- Shadow 三层证据、报告有效期、双 Champion 引用、blocking/deferred、差异双方标签和逐类别混淆计数；
- 跨路径切换时选择 cutover_only/recent_window/full_backfill，预览每台设备生效边界，展示九项准入并要求人工确认；
- Promotion Event 与 Path Switch Event 分栏；
- Deployment Arena 的 pv_fault 区域标明“只读，去 PV 双路径控制台治理”。

某一区域数据不可用，只让那块显示空态，不拖垮其他区域；写请求失败时，界面保持原来的生产真相不变。

## 17. 怎么验证设计没有倒退

必须重点测这些故事：

1. 较早日期未完整、较晚日期完整：较晚日期照常成功，两个日期没有拼接。
2. Seq 的 frontier 越过某日期但 Ledger 显示 failed：仍以 Ledger 为准，允许重试。
3. succeeded 日期晚到一个点：产生修订批次，旧批次字节不变。
4. 待处理 51 天、单轮上限 50：本轮恰好 50 个独立预测，剩余 1 个 ready。
5. 从老路径切到新路径用 cutover_only：只从各设备最近已结束日接管，不从最早历史重跑。
6. full_backfill 与生产并行：两条车道日期不重叠，历史失败不掉回生产积压，容量仲裁保证生产预留，生产账不受污染。
7. 候补晋升：只换主将，不换 production_path，只写 Promotion Event。
8. Shadow：只加载双 Champion，报告含三层证据，任何生产事实不变。
9. 九项准入任一失败：指针、Epoch、事件全不变；全过且人工确认才切换。
10. Deployment Arena 尝试写 pv_fault 被拒，但其他槽位仍可按原方式写。
11. 当前路径可通过候补恢复时，系统选择换将而不是换班组；整路径不可用才进入 fallback 流程。

属性测试的正式编号与验收条款映射见 `design.md` Property 1–42。Property 1–27 保留编号，其中 Property 8 已改为“设备日独立准入且不发生队头阻塞”；Property 28 起覆盖 Req13–15，Property 42 专门验证 full_backfill 两车道互斥与生产容量预留。

---

**最后记一句：公共数据日历解决“数据到哪”，逐日记账解决“哪天处理过”，生效边界解决“本次从哪负责”，主将/候补解决“班组内部谁上场”，演习场和九道门解决“能不能换班组”。切换不等于全量重跑，多日积压也不等于多日拼接。**
<!-- @AI_GENERATED: end -->