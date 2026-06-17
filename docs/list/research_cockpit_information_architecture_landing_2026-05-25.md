# Research Cockpit 信息架构收敛改动落地说明

日期：2026-05-25

## 结论

本次把 AutoResearch 前端研究控制面从“字段平铺 + 多区域重复”收敛为五张核心卡片：

1. Experiment 实验卡
2. Evidence 证据卡
3. Question 问题卡
4. Knowledge 知识卡
5. Strategy 策略卡

用户第一眼先看实验状态，再看证据是否可靠、系统正在研究什么、学到了什么，以及下一步为什么这么跑。

## 实际改动

### 1. 前端五卡片

修改文件：

- `frontend-sevice/src/pages/WorkflowBaselineComparePage.tsx`

新增展示结构：

- Experiment 实验卡：展示 `iteration`（第几轮）、`group_idx`（第几组）、`target_direction`（研究方向）、`changed_variables`（改了什么）、`status`（成功/失败）、`failure_reason`（失败原因）。
- Evidence 证据卡：展示窗口数、MAPE 改善、证据强度，并翻译为“单窗口正收益，需要复验”等中文判断。
- Question 问题卡：展示当前优先研究问题、问题状态、证据数、下一步实验目标和来源。
- Knowledge 知识卡：展示候选/有效/冲突/过时/拒绝知识数量，并翻译为中文知识状态。
- Strategy 策略卡：展示当前研究状态、主线方向、推荐下一方向、理由和方向覆盖。

### 2. 字段降噪

- `target_layer`（目标层）、`patch_fingerprint`（补丁指纹）等调试字段放入折叠详情。
- `candidate_causes`（候选原因）、`evidence_refs`（证据引用）、`expected_patch_intent`（预期补丁意图）放入问题详情。
- Knowledge 原始治理对象放入详情 JSON。
- 旧“自主研究员产物”区域不再渲染，避免和五卡片重复。

### 3. 浏览器反馈修复

- Evidence 证据卡在宽屏下改为跨两列展示，避免窗口数、MAPE 改善、复验状态等字段挤在窄卡片里。
- 证据卡内的核心字段标签增加自动换行和长文本断行策略，避免中文注释或长字段值超出卡片边界。
- Evidence 证据卡补充“待沉淀对象”和“不足原因”，明确不能沉淀的是当前候选实验结论，而不是某条已有知识。
- Experiment 实验卡的调试字段改为“技术详情”：默认展示中文解释，原始 JSON 放入二级折叠，避免一打开就是后端原始对象。
- Question 问题卡补充“当前问题”标识，并将历史问题移入“查看历史问题”折叠区，避免当前研究焦点和历史问题混在一起。
- Knowledge 知识卡为 `candidate`、`active`、`conflicted`、`stale`、`rejected` 增加中文标签和说明。`active` 解释为已通过证据门控、当前可优先注入后续研究的有效知识；`candidate` 解释为仍需复验的候选知识。
- Knowledge 知识卡主统计改为当前 run 口径：`multi_window_confirmed`（多窗口确认）计为当前 run 有效知识，`single_window_positive`（单窗口正收益）计为当前 run 候选知识。知识库可注入候选统计保留在下方，作为历史知识参考。
- 候选池默认视图改为成熟候选：后端为候选补充 `source_run_completed_iterations`（来源 run 已完成轮数），前端默认只显示来源 run 完成不少于 10 轮的 AutoResearch 候选，并按 `mape_improvement` / `score_advantage`（MAPE 改善）降序排列。原始候选池数据不删除。
- 兼容旧 run 快照：部分旧 snapshot 没有 `progress`，但 `trials.jsonl` 有真实轮次。前端加载候选池时会读取候选涉及的来源 run trial 账本，用完成 trial 的去重轮次数作为过滤依据，避免误显示为 0 条。
- 最近 AutoResearch run 改为长期记录视图：当前活跃 run 始终展示；非活跃 run 只有完成不少于 10 轮才进入主列表。10 轮以下仍可作为短期运行记录存在，但不进入长期主列表，避免噪声。列表不再固定截断为 5 条，支持查看所有符合条件的 run 并恢复查看结果。

### 4. 文档归档

已写入 Obsidian：

- `AutoResearch 第四代/需求设计/Research Cockpit 信息架构收敛需求设计.md`
- `AutoResearch 第四代/实现进度/Research Cockpit 信息架构收敛任务清单.md`

## 未改动内容

- 未改后端字段结构。
- 未重启后端。
- 未停止 worker。
- 未修改 AutoResearch run 状态。
- 未扩大搜索空间。

## 验证结果

命令：

```bash
cd frontend-sevice
npm run build
```

结果：通过。

保留既有 warning：

- Tailwind：No utility classes were detected。
- Vite chunk size warning。

这两个 warning 是项目既有构建提示，不是本次改动引入的失败。

## 风险和注意事项

- 旧的三集画像曲线和阶段反思详情暂时被主展示区降噪处理；后续可以作为“研究详情”折叠面板重新整理。
- 当前只是前端信息架构收敛，不改变后端数据生产逻辑。
- Vite dev server 正在运行时，前端页面可能已热更新。

## 后续建议

1. 打开 AutoResearch 页面人工看一遍五卡片密度。
2. 再决定是否把三集画像曲线作为“证据详情”折叠回 Evidence 卡。
3. 后续如果字段继续变多，统一只进入详情，不再新增主卡片。
