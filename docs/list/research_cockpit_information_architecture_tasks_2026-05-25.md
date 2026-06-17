# Research Cockpit 信息架构收敛任务清单

日期：2026-05-25

## 约束

- [x] 不停止当前 worker。
- [x] 不重启后端。
- [x] 不改后端数据结构。
- [x] 不扩大 AutoResearch 搜索空间。
- [x] 前端以五卡片信息架构收敛为主。

## 任务清单

- [x] T1 确认五卡片顺序：Experiment、Evidence、Question、Knowledge、Strategy。
- [x] T2 写入需求设计文档。
- [x] T3 重构前端 AutoResearch 控制台展示为五卡片。
- [x] T4 将调试字段放入详情折叠，默认不平铺。
- [x] T5 为关键英文字段补中文注释。
- [x] T6 处理旧 run / 首轮未完成 / 字段缺失的空状态。
- [x] T7 运行前端 build 验证。
- [x] T8 自审 UI 信息密度、重复区域和字段可读性。
- [x] T9 写入改动落地说明。
- [x] T10 写入展示汇报文档。

## 当前状态

当前状态：10 项任务已完成。

## 浏览器反馈修复记录

- [x] F1 证据卡宽度不足：已将 Evidence 证据卡在宽屏下调整为跨两列展示。
- [x] F2 证据字段文字溢出：已为证据卡核心字段增加自动换行和长文本断行策略。
- [x] F3 修复后验证：已重新运行前端 build，结果通过。
- [x] F4 证据不足主语不清：已在 Evidence 卡补充“待沉淀对象”，明确是当前候选实验结论，而不是某条已有知识。
- [x] F5 证据不足原因不清：已补充缺少窗口统计、无成功窗口、仍需复验等原因说明。
- [x] F6 实验调试字段过于原始：已改为“技术详情”中文解释，原始 JSON 放入二级折叠。
- [x] F7 问题卡当前/历史混杂：已标明“当前问题”，并将历史问题放入可展开列表。
- [x] F8 知识卡英文字段不清：已为 candidate、active、conflicted、stale、rejected 增加中文标签和状态解释。
- [x] F9 知识卡统计范围不清：已将主统计改为当前 run 口径，并把知识库可注入统计降为次要说明。
- [x] F10 候选池排序和成熟度口径混乱：已改为默认只显示来源 run 完成不少于 10 轮的候选，并按 MAPE 改善降序排列。
- [x] F11 旧 run 快照缺少 progress 导致候选池误空：已改为读取候选来源 run 的 trials 账本计算真实完成轮数。
- [x] F12 最近 run 长期记录口径不清：已改为显示当前活跃 run + 已完成不少于 10 轮的 run，支持查看结果和恢复查看。

## 文件范围

预计修改：

- `frontend-sevice/src/pages/WorkflowBaselineComparePage.tsx`
- `AutoResearch 第四代/改动落地/Research Cockpit 信息架构收敛落地说明.md`
- `AutoResearch 第四代/展示汇报/Research Cockpit 信息架构收敛展示汇报.md`

## 验证计划

- 前端构建：`cd frontend-sevice && npm run build`。
  - 结果：通过。
- 人工检查：页面只出现一套五卡片驾驶舱，字段不再大面积平铺。
