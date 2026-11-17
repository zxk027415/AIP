<!-- @AI_GENERATED -->
# AIP 文档中心索引

`docs/` 当前混合了**现行交接、业务事实、目标规格、验收证据、方法论和历史会话**。它们不是同等级真源。

## 真源优先级

1. 当前代码、接口响应和 `backend-service/data/` 对应业务真源。
2. `docs/handoff_2026-09-17.md` 与带日期的现状/专项验收文档。
3. `requirements.md` / `design.md` / `tasks.md` 规格：描述目标合同，不自动代表已实现。
4. `docs/list/`、`docs/docs_zxk/` 的历史/方法资料。
5. `docs/transcript/` 会话导出：只追溯“为什么这样做”，不作当前事实。

## 顶层目录

- `docs/handoff_2026-09-17.md` — 总交接入口，覆盖代码架构、负荷预测、光伏三路径、operation_skill、前端逐步操作、验证与风险。
- `docs/list/` — 早期平台总览、学习指南、能力盘点、页面重构和专项方法论。`PROJECT_BEGINNER_GUIDE.md` 与 `README.md` 使用旧目录名和旧端口，只读概念。
- `docs/docs_zxk/` — 工程备忘：算子 I/O 与六重测试、AutoResearch 演进、前端设计、Git 和服务器排错。旧绝对路径/旧同步命令不可直接复制。
- `docs/project/load_forecast/` — 负荷预测全景、字段链、AutoResearch 代码讲解、迭代历史和 7 组叶子规格。
- `docs/project/pv_fault/` — 光伏架构、三路径喂数、TSC 验收、数据集报告和 8 组叶子规格。
- `docs/project/operator/` — 算子后端、精度运营、自动切换、运营分析 Agent 4 组规格。
- `docs/transcript/` — Kiro/Cursor 会话 zip、摘要、可读导出和解析脚本，属于审计材料。
- `docs/cleanup-archive-index-2026-09-17.md` — 本次代码整理归档清单和恢复说明。
- `docs/root-directory-inventory-2026-09-18.md` — 根目录隐藏目录、AI 工具资产、缓存、output 和根文件的保留/删除判断。

## 推荐阅读顺序

### 接负荷预测

1. `docs/handoff_2026-09-17.md` 第 1、9、10 章。
2. `docs/project/load_forecast/AIP平台负荷预测整体故事线与设计报告.md`。
3. `docs/project/load_forecast/负荷预测正式链路_字段流转与精度运营深度讲解.md`。
4. `docs/project/load_forecast/AutoResearch全面讲解（代码实现版）.md`。
5. 再按任务读 `docs/project/load_forecast/spec/`。

### 接光伏故障诊断

1. `docs/handoff_2026-09-17.md` 第 2、9、10 章。
2. `docs/project/pv_fault/光伏故障诊断-架构讲解-2026-09-14.md`。
3. `docs/project/pv_fault/三路径喂数据与精度运营-改动计划现状-2026-09-14.md`。
4. `docs/project/pv_fault/PV_TSC_E2E_VALIDATION_HANDOFF_2026-09-08.md`。
5. 再进入对应 spec；产品 Draft 不得写成已落地。

### 改算子

先读 `docs/docs_zxk/算子IO契约与六重测试说明_2026-07-23.md`，再读 `docs/project/operator/operator-backend-filling/`。

## 规格阅读方法

标准顺序是：`requirements.md`（需求/验收）→ `design.md`（架构/数据/API）→ `tasks.md`（实施清单）。任务打勾不能替代代码、测试和运行证据。

## 已知文档问题

- `docs/specs/` 当前不存在；旧引用应映射到 `docs/project/.../spec/...`，不要重建第二份副本。
- `docs/list/PROJECT_BEGINNER_GUIDE.md` 仍写 `frontend/`、`backend/`、5173/8000；现状是 `frontend-sevice/`、`backend-service/`、3001/8081。
- `docs/docs_zxk/ENGINEERING_CONTRACT_TRACE_TEMPLATE.md` 当前不存在，但协作规则仍引用它。
- `docs/project/load_forecast/spec/autoresearch/` 有一份文件名编码损坏的 V6 Plan；正文可读，重命名前先核 Git 历史。
- `docs/transcript/` 中部分中文受导出编码影响，且会话中的阶段结论可能已被后续代码覆盖。

更完整的逐文件职责与 19 个规格组清单见总交接文档第 8 章。
<!-- @AI_GENERATED: end -->
