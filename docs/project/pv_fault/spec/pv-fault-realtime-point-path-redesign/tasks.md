<!-- @AI_GENERATED -->
# 实施任务：单 Slot 时序工作流与光伏天/点双链路

> 规格：`pv-fault-realtime-point-path-redesign` — 历史目录名保留；当前任务主线是 `pv_day` / `pv_point` 两条完整产品链（形状对齐负荷预测），不是先造通用时序平台  
> 文档状态：2026-08-25 叠加 G10+ 融合批次；G0–G9 正文保留为已执行/条件阶段  
> 需求真源：`docs/specs/pv-fault-realtime-point-path-redesign/requirements.md`（含 0.F）  
> 设计真源：技术合同 `design.md` A0–A16；**产品接缝** `fusion-design.md`  
> 调研依据：`docs/specs/pv-fault-realtime-point-path-redesign/research.md` — 只提供仓库与外部数据事实，不覆盖当前合同  
> 执行环境：Windows PowerShell；后端 Python 命令优先使用 conda 环境 `cp_web`  
> 路径约定：本文所有仓库路径均相对于项目根目录；代码、配置和持久化数据禁止写绝对路径

## A0. 当前执行权威与顺序

本文件的 A0、G0–G13、A11–A12 是可执行任务真源。后半部附录 H 是原“光伏专用实时点产品”历史草案，保留用于追溯；其中的双层键、固定 5 分钟网格、整日 288 槽、专用入口和先建在线基础设施均不是当前任务，不得直接实施。

固定执行顺序：

```text
P0a 生命周期链（已完成骨架：G0–G3）
P0b 标注回流闭环（已完成骨架：G4–G5）
验证与增强（已完成骨架：G6–G8；G9 仍为条件阶段，采集后置）

产品融合（2026-08-25 起，见 fusion-design.md）
  → G10 确认箱接缝：proposal 门、带 slot 的 LabeledDatasetVersion、纳入累计、快照加载
  → G11 打标工作流化 + load_labeled_dataset / 预测进复核
  → G12 pv_point 日内滚动告警（replay_activity + 状态机；不用 TSC）
  → G13 平台卫生与 pv_fault/TSC 遗产只读
```

**当前可执行下一批是 G10**，不要重开 G0–G8。G9 正式采集仍后置于 G12 告警演示之后（或与 G12 喂数源扩展合并评估）。

G0–G8 批次正文保留作已执行合同；新开发只认 `fusion-design.md` 的 G10–G13 退出门槛。

任何 Batch 未达到退出门槛，不得启动下一 Batch。每批遵守：实施 → 定向验证 → 构建/类型检查 → 重新读取修改文件 → 对照需求自审 → 交付小结。工作区很脏，不清理、不重置、不覆盖无关改动，不修改目标范围外文件。

### A0.1 全局不变量

1. 新合同只使用 `slot` — 模板、配置、执行、快照、模型和运营的唯一分区键；不再持久化或传递 `scenario_key` — 旧场景键。
2. 产品 slot 固定为 `pv_day` — 光伏天路径、`pv_point` — 光伏点路径和 `load_forecast` — 负荷预测；外部数据使用独立 `benchmark_<dataset_key>`，PVDAQ 使用 `benchmark_pvdaq_<system>`。
3. 天、点使用不同模板，不在单模板中用 `modeling_path`、`production_path` 或 `feed_mode` 切换；旧 `(pv_fault,pv_day|pv_point)` 仅由服务端 allowlist 映射到新 slot。
4. 每个 slot 独立维护 `slot_config_ref` — 槽位配置不可变版本；`effective_global_config` — 本次最终配置按“请求覆盖 > 同 slot 模板 > 同 slot defaults > 平台无业务默认”合并。API 省略请求级覆盖时等价于传 `{}`，禁止跨 slot 或最近 execution 回退。
5. 只允许普通算子逐个拖拽、配置和连线；冻结 graph 必须完全展开。`replay_activity` 可按点多次调用同一冻结 graph；admission/cursor 不是隐藏算子。
6. `pv_point` 按真实事件点推进：校验与去重后，只处理已有真实点行，以当前点和此前真实点构建因果窗口并立即预测；禁止 grid、resample、时间取整、虚拟点补齐和整日 288 槽推理。旧 grid POC 权重不得当新合同 Champion。
7. Algorithm Deployment 和 Accuracy Operations 只消费 `status=succeeded` 的 workflow execution 产物；G3 起 Orchestrator/日检必须触发已发布模板，不得旁路评分。
8. 模型候选、评测量约、复验、registry、Champion/Challenger、Promote、Shadow、告警和监控只在同一 slot 内流转；跨 slot 只读诊断不能形成 `eligible_for_pool=true` 或 Promote 证据。
9. 公开标签为 `benchmark_ground_truth`；专家审核为 `reviewed_annotation`；未审核区间为 `annotation_candidate`/`candidate_only`；待复验模型为独立 `model_candidate`，两类 ID 不得混用。
10. 预测模板只消费明确 `model_ref`；训练或重训成功只产生 artifact 与 `model_candidate`，不自动写 registry Challenger、复验、Promote 或修改 Champion。只有通过门禁的 Promote false 写 Challenger，Promote true 切 Champion。
11. Point 因果路径不得读取未来值；先 split 再按真实点切窗；`locked_holdout` — 锁定留出集不得进入训练、阈值或选模。
12. 不修改旧负荷预测和旧光伏算子的默认语义；新点能力使用新的普通 `ts_point_*` ID，但复用现有 Causal TCN trainer/artifact 核。`ts_point_*` **尽量**只认规范点表，不要硬编码光伏列名或按数据集名分支。换 Kaggle/NASA 等表格集**优先**只做新 profile + 复制模板 + 独立 benchmark slot；确需改算子时记录例外。
13. 前端和持久化只使用相对路径或稳定 ID；公开 benchmark execution 强制 `governance_eligible=false` — 禁止进入产品治理。
14. G0 不改写现网 `pv_fault` 生产指针、不迁标签表、不把 `functions.json` 整表生成化。
15. `replay_activity` 是喂数调度器（回放循环），不是算子；**尽量**能驱动任意表格 profile，不要只认光伏水位。
16. G0–G8 已执行完毕，不得重开。新编码从 **Batch G10** 开始；用 Composer 2.5 时一次只开 **G10-S0 → G10-S5** 中的一个切片。未完成当前切片不得做下一切片，更不得进入 G11。

### A0.2 每批交付小结

```markdown
#### Batch Gx 交付小结
- 结论：通过 / 不通过；是否允许进入下一批。
- 改动文件：每条相对路径说明职责和本次变化。
- 关键字段链：UI → HTTP → API Handler → execution/service → storage/artifact → response → UI。
- 默认与兼容：缺字段默认、旧请求行为、最终改变行为的条件分支。
- 已验证：测试、类型检查、构建、dry-run、对账、逐真实点回放和截图。
- 未验证：真实 DB、浏览器、长运行、外部数据或生产环境未覆盖项。
- 自审：复读修改文件、需求逐项、状态完整、无死代码、无绝对路径、无跨 slot 副作用。
- 风险与回滚：开关、旧版本、不可变快照、registry 恢复和剩余风险。
```

### A0.3 Composer 2.5 执行协议（G10 起强制；G0 历史协议已完成）

面向小上下文编码模型。每个切片是一次独立会话；不要把整批丢给一次对话。

**G10 起强制：**

1. **一次只做当前切片标题里的目标。** 切片未写的文件一律不改。
2. **先写测试再改生产代码。** 测试失败时只修本切片范围。测试必须把数据目录打到 `tmp_path`，禁止写入真实 `data/slot_datasets/`。
3. **不要读** `design.md` 全文、不要读附录 H、不要读 `research.md`、不要读 `fusion-design.md` 全文。需要合同以**本切片正文**为准。
4. **禁止：** `git commit` / `git reset` / `git checkout --` / 清理工作区 / 删 `__pycache__` / 改 `.env` / 改现网 `pv_fault` registry / 改标签表 / 跑全量 `pytest` / 新建 `ts_point_*` / 下载 NASA / 实现模板 A / 实现告警状态机 / 给写接口加鉴权（G13，需用户再授权） / 改 AutoResearch 的 `GET /datasets` 与 `POST /datasets/register` 语义。
5. **唯一例外：** G10-S2 可改 `functions.json` 里四个命名孪生 ID（`kmeans_cluster` / `dbscan_cluster` / `agglomerative_cluster` / `pca_reduce`），禁止整表重写或生成化。
6. 后端工作目录 `backend-service`，环境 `cp_web`。Windows PowerShell。路径只用相对路径。
7. `workflows_enhanced.py` 很大：只改本切片点名的函数；不要格式化全文件。新路由必须写在带 `{dataset_id}` 的通配路由之前。
8. 切片完成：指定 pytest 全绿 + `py_compile` + 按模板写交付小结（若切片要求）。然后**停下等用户开下一会话**。
9. 不确定写「未做 / 不确定」，不要猜着扩展范围。

## Batch G0：工作流执行安全、槽位配置与产物追溯

**目标：** 画布节点缺 backend 不能伪成功；执行请求带上 slot/config；execution 能回显配置来源。G0 **不**迁生产 registry、不改标签表、不下载公开数据、不把 `functions.json` 整表生成化、不新建点算子。

**映射：** G0-S0 = 原 G0.1 盘点；G0-S1 = 原 G0.3 的 skipped-success；G0-S2 = 原 G0.4 merge 纯函数；G0-S3 = 原 G0.4 接线 + 前端；G0-S4 = 原 G0.5 字段预留 + 交付。原 G0.2 本批缩小为「确认 `load_csv`/`load_model_artifact` 可被 router 发现 + 只读差异报告」，不做生成流水线。

**本批允许改的文件（超出即停）：**

- `backend-service/api/workflows_enhanced.py` — 增强工作流 HTTP 与 `_execute_pipeline_sync`
- `backend-service/services/operator_execution/router.py` — 算子发现（只读或最小辅助，尽量不改）
- `backend-service/services/operator_execution/slot_config.py` — **新建** slot merge/digest（S2）
- `backend-service/tests/test_g0_pipeline_preflight.py` — **新建** skipped-success 测试（S1）
- `backend-service/tests/test_g0_slot_config.py` — **新建** merge fixtures（S2）
- `frontend-sevice/src/pages/WorkflowEditorPage.tsx` — `handleExecute` 请求体（S3）
- `frontend-sevice/src/services/workflowEnhancedApi.ts` — `executeAsync` 类型（S3，可选）
- `docs/specs/pv-fault-realtime-point-path-redesign/g0-baseline.md` — **新建** 只读盘点（S0）
- `docs/specs/pv-fault-realtime-point-path-redesign/g0-handoff.md` — **新建** G0 交付小结（S4）

---

### G0-S0 只读盘点（第一会话，不改业务代码）

**目标：** 写一份基线报告，让后续切片对着改，不要凭记忆改。

**允许新建唯一文件：** `docs/specs/pv-fault-realtime-point-path-redesign/g0-baseline.md`

**禁止：** 改任何 `.py` / `.ts` / `.tsx` / `functions.json`。

**必须写入报告的事实（用文件+函数名+行号附近行为，不要空话）：**

1. `_execute_pipeline_sync`：未注册 `functionId` 时现在会怎样（当前：打 warning，output 为 skipped，节点仍标 `success`，流水线可 `success=True`）。
2. `SchemaValidator` / `DataAdapter` 是否创建后未使用。
3. `WorkflowEditorPage.handleExecute` 实际 POST body 有哪些键（当前主要是 `{ live_nodes }`）。
4. `execute_workflow_async` 是否读取 `slot` / `global_config`（当前基本不读 slot）。
5. `OperatorRouter.auto_discover` 如何发现 `load_csv`、`load_model_artifact`（二者 backend 已存在）。
6. `functions.json` 里有没有 `load_model_artifact` 目录项（只记录有/无，不改文件）。
7. 列出 Algorithm Deployment / Accuracy Operations 里疑似页面自训/自评分的文件路径（只列，G3 再改）。

**完成标准：** 该 markdown 存在且含以上 7 条；`git status` 里本切片只有这一个新文件。停下。

**会话提示词（复制给 Composer 2.5）：**

```text
只做 G0-S0。读 docs/specs/pv-fault-realtime-point-path-redesign/tasks.md 里「G0-S0」整节，按它写
docs/specs/pv-fault-realtime-point-path-redesign/g0-baseline.md。
禁止改任何代码。禁止 git commit。写完停下。
```

---

### G0-S1 禁止 skipped-success（第二会话，最高杠杆）

**目标：** 未注册算子、缺 `functionId` 的节点必须让**整次 pipeline 失败**；节点状态为 `failed`，不得标 `success`。`enabled=false` 仍可 skip，且 skip 不得把整次 execution 标成功（若图中还有应执行节点因缺 backend 失败则仍失败；若全部是用户禁用则允许 success=false 或单独 `cancelled`——本切片规定：存在任何「缺 backend / 缺 functionId」则 `success=False`）。

**前置：** G0-S0 报告已写。

**允许改：**
- `backend-service/api/workflows_enhanced.py` 仅 `_execute_pipeline_sync` 及相关很小的 helper
- `backend-service/tests/test_g0_pipeline_preflight.py` 新建

**当前错误代码（必须修）：** `_execute_pipeline_sync` 在 `op_router.has_operator(function_id)` 为 false 时：

```python
output = {"status": "skipped", "message": f"算子 {function_id} 未注册"}
# 随后节点仍 status=success，流水线 success=True
```

**改为：**

- 未注册：节点 `status=failed`，`error` 含 operator_id 与 `OperatorNotFound`；函数立刻 `return success=False`（与现有节点 `except` 失败路径一致）。
- 缺 `functionId`：同样 failed + 立刻返回，不要 continue 后整体成功。
- `enabled=false`：保持 skip，不视为失败。
- `SchemaValidator()` / `DataAdapter()` 若仍未使用：删掉这两行实例化，不要假装接入。真正 schema 校验留给以后切片；本切片不重新实现 DataAdapter。

**测试文件必须覆盖（不要 mock 整个 FastAPI 应用除非必要；优先直接调 `_execute_pipeline_sync`）：**

1. 单节点 `functionId=not_a_real_operator` → `success is False`，该节点 status 不是 success。
2. 单节点无 functionId → `success is False`。
3. 单节点 `enabled=false` 且有合法 functionId → 该节点 skipped，不报 OperatorNotFound。
4. 若能构造一个已注册算子的最小图（例如只有 `load_csv` 但缺文件路径），失败应来自算子参数/文件，而不是「未注册却 success」。

构造 workflow 对象：复用现有 `EnhancedWorkflow` / `EnhancedWorkflowNode` 的最小实例；不要连真实 MySQL。

**验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_g0_pipeline_preflight.py -q
conda run -n cp_web python -m py_compile api/workflows_enhanced.py
```

**完成标准：** 上述 pytest 全绿；未注册路径不再把节点写成 success。不改前端。停下。

**会话提示词：**

```text
只做 G0-S1。读 docs/specs/pv-fault-realtime-point-path-redesign/tasks.md 里「G0-S1」整节。
先写 backend-service/tests/test_g0_pipeline_preflight.py，再改
backend-service/api/workflows_enhanced.py 的 _execute_pipeline_sync。
未注册算子必须让 pipeline success=False，节点不得标 success。
不要改 functions.json，不要新建 ts_point 算子，不要 git commit。
用 conda run -n cp_web 在 backend-service 下跑该测试。通过后停下。
```

---

### G0-S2 slot 配置 merge 纯函数（第三会话，不接线）

**目标：** 把 canonical deep-merge 做成可单测模块，避免在巨型 API 文件里手写 merge。

**允许新建/改：**
- `backend-service/services/operator_execution/slot_config.py`
- `backend-service/tests/test_g0_slot_config.py`

**禁止：** 改 `workflows_enhanced.py`、前端、`functions.json`。

**函数合同（必须按这些名字实现，方便后续切片 import）：**

- `deep_merge_layers(platform_default, slot_default, template, request) -> dict`  
  优先级低→高：platform < slot_default < template < request。object 按 key 递归；scalar/array 整体替换不拼接；`null` 是真实值不是删除；禁止隐式类型转换（string `"1"` 不得变 int）。
- `normalize_request_global_config(value) -> dict`：`None` 与缺失当成 `{}`。
- `build_effective_global_config_sources(...)` → 叶子 JSON Pointer → `platform_default|slot_default|template|request`。
- `canonical_digest(obj) -> str`：key 排序后的稳定哈希（sha256 hex 即可）。
- `resolve_legacy_slot(slot, scenario_key, workflow_id, workflow_version) -> dict`：新请求带 `scenario_key` 则 raise/返回 error 结构；缺 `slot` 失败；仅当 `slot==pv_fault` 且 `scenario_key` 为 `pv_day|pv_point` 且 workflow_id 在模块内 **空 allowlist 常量**（先 `LEGACY_SLOT_ALLOWLIST: dict[tuple, str] = {}`）才映射。G0 allowlist 为空意味着旧双键默认失败，这是刻意的；不要猜生产模板 ID 填进去。

**测试 fixtures 至少：** object 递归、array 替换、null 保留、类型冲突（template int vs request string）应失败或 raise、`None` request 等于 `{}`、digest 稳定、空 allowlist 时 `(pv_fault, pv_day)` 不得默默成功。

**验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_g0_slot_config.py -q
conda run -n cp_web python -m py_compile services/operator_execution/slot_config.py
```

**完成标准：** pytest 全绿。不接线 API。停下。

**会话提示词：**

```text
只做 G0-S2。读 docs/specs/pv-fault-realtime-point-path-redesign/tasks.md 里「G0-S2」整节。
新建 slot_config.py 和 test_g0_slot_config.py，按文中函数名实现。
不要改 workflows_enhanced.py 和前端。不要 git commit。测试通过后停下。
```

---

### G0-S3 执行请求接线（第四会话）

**目标：** 前端执行带 `slot`、`live_nodes`、`global_config`；后端校验后写入 execution 摘要。缺 slot 的新请求失败，不创建成功 execution。

**允许改：**
- `frontend-sevice/src/pages/WorkflowEditorPage.tsx` 的 `handleExecute`（普通执行分支，不要改回测/调优早退分支）
- `frontend-sevice/src/services/workflowEnhancedApi.ts` 仅 `executeAsync` 参数类型（可选）
- `backend-service/api/workflows_enhanced.py` 的 `execute_workflow_async` 与把 merge 结果写入 `_execution_store`
- 可小幅扩展 `tests/test_g0_pipeline_preflight.py` 或新建 `tests/test_g0_execute_slot.py`

**请求 JSON 最小形状：**

```json
{
  "live_nodes": [],
  "slot": "pv_day",
  "slot_config_ref": null,
  "global_config": {}
}
```

**行为：**

1. 前端始终发送对象 `global_config`（没有就 `{}`）。`slot` 从当前编辑器已有的 slot/场景选择器读取；若页面还没有选择器，先从 workflow metadata 的 `slot` 读取，再没有则发请求也必须让用户看见失败——**不要静默填 `pv_fault`**。若现有页面只有光伏旧槽位字符串，允许原样传 metadata.slot，后端再判。
2. 后端：`normalize_request_global_config` → `resolve_legacy_slot` → 缺 slot 返回 HTTP 4xx，detail 可读。`scenario_key` 出现在 body 则 4xx。
3. merge：本切片若还没有 slot defaults 存储，`platform_default={}`、`slot_default={}`，template 取 `workflow.metadata.global_config`，request 取 body。把 `effective_global_config`、`sources`、`digest`、`slot` 写入 `_execution_store`。
4. 不要实现完整 slot_config registry 文件；`slot_config_ref` 允许 null。
5. 不要改 Deployment / Accuracy 页面。

**验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_g0_pipeline_preflight.py tests/test_g0_slot_config.py tests/test_g0_execute_slot.py -q
conda run -n cp_web python -m py_compile api/workflows_enhanced.py services/operator_execution/slot_config.py
```

前端：不强制 `npm run build`（易超时）；改完 `handleExecute` 后人工确认 POST body 含 `slot` 与 `global_config`。若新增测试文件不存在，本切片必须创建 `test_g0_execute_slot.py`，至少测「缺 slot → 4xx」和「有 slot + 空 config → store 里有 effective_global_config」。可用 FastAPI TestClient；不要启动真实 uvicorn 去打本机 8080。

**完成标准：** 缺 slot 失败；有 slot 时 execution 记录里能看到 slot 与 digest。停下。

**会话提示词：**

```text
只做 G0-S3。读 docs/specs/pv-fault-realtime-point-path-redesign/tasks.md 里「G0-S3」整节。
把 slot_config.merge 接到 execute-async；前端 handleExecute 发送 slot、live_nodes、global_config。
缺 slot 必须 4xx。不要改回测分支，不要改 functions.json，不要 git commit。测试通过后停下。
```

---

### G0-S4 provenance 预留 + 交付小结（第五会话）

**目标：** execution 记录补齐来源字段；写出 G0 小结；**宣布 G0 结束，不进入 G1。**

**允许改：**
- `backend-service/api/workflows_enhanced.py` 仅 `_execution_store` 初始 dict 与结束时写入
- `docs/specs/pv-fault-realtime-point-path-redesign/g0-handoff.md` 新建

**每个 execution 至少有这些键（没有就填 null，不要删）：**  
`execution_id`、`source_workflow_id`、`source_workflow_version`（没有版本就 null）、`slot`、`slot_config_ref`、`effective_global_config`、`effective_global_config_digest`、`graph_digest`（对 live_nodes 或磁盘 nodes 做 canonical json hash，失败则 null 并在小结说明）、`status`。

**不要：** 改模型表、改 Deployment UI、迁移 registry、发布新工作流版本体系。draft vs immutable 若现有保存逻辑已有版本字段则回显；没有则只在小结写「未做，留给 G3」。

**g0-handoff.md 必须含 A0.2 交付小结模板全部条目。**

**完成标准：** handoff 文件存在；声明「可以 / 不可以进入 G1」。默认：**可以进入 G1 的条件**是 S1–S3 测试仍绿。然后停下等用户。

**会话提示词：**

```text
只做 G0-S4。读 docs/specs/pv-fault-realtime-point-path-redesign/tasks.md 里「G0-S4」整节。
给 execution store 补 source_workflow_id/slot/digest 等键（没有就 null）。
写 docs/specs/pv-fault-realtime-point-path-redesign/g0-handoff.md。
不要开始 G1，不要 git commit。写完停下。
```

---

**G0 总退出（S4 对照，不是 S1 的事）：**

- [ ] 缺 backend / 缺 functionId 不能伪成功。
- [ ] 新请求缺 slot 或带 `scenario_key` 失败。
- [ ] merge fixtures 通过；execution 能回显 slot 与 digest。
- [ ] `functions.json` 未被生成化；无 `ts_point_*`；现网 `pv_fault` 未改。
- [ ] `g0-handoff.md` 已写。

**不要在 G0 做：** 完整 operator contract 平台、Deployment 改接、Orchestrator、profile service、NASA、点回放。

## Batch G1：Dataset/Domain Profile（现有 PV 优先）

**目标：** 现有 PV 冻结快照能以 profile 接入训练/回放；许可证、字段、频率和 split 在运行前可审计。NASA/FHC/PVDAQ **下载不是本批退出条件**。

**前置条件：** G0 通过（`g0-handoff.md` 明确允许进入 G1）。G1 尚未切成 Composer 会话；未切片前不要用 Composer 2.5 一次做完整 G1。

- [ ] G1.1 建立 profile 模型与版本
  - 新建通用 profile service/model；字段至少覆盖 `profile_id` — profile ID、`profile_version` — 不可变版本、`source_kind` — 数据源类型、`source_ref` — 相对数据引用或 connector ID、`path_root_alias` — 允许解析根别名、`format` — 数据格式、`clock_mode` — 时钟模式（`event_time` 表示真实事件时间，`index` 表示单调序号时钟；表格类数据必须使用 `event_time`，仅无真实时间的匿名数组允许使用 `index`）、`time_column` — 事件时间列（`event_time` 模式必填，`index` 模式必须为空）、`entity_keys` — 实体键、`feature_columns` — 特征列、`label_column` — 标签列、`label_semantics` — 标签语义、`sampling_interval` — 事件时间采样间隔或序号时钟模拟步长、`timezone` — 时区、`split_policy` — 划分策略、`license_ref` — 许可引用、`license_status` — 许可状态、`redistribution_allowed` — 是否允许再分发、`allowed_use_purposes` — 允许用途、`adapter_id` — 适配器 ID 和 `quality_rules` — 质量规则。
  - 草稿可编辑，发布产生不可变版本；持久化介质由部署配置决定，只存相对路径或已登记 connector ID。

- [ ] G1.2 Profile preflight API
  - 实现只读 preflight：接收 `use_purpose` — 本次用途，校验列、`clock_mode` — 时钟模式、事件时间或单调索引、实体键、重复点、实际频率/模拟步长、缺测、标签、规模、路径边界和许可用途。
  - `clock_mode=event_time` 时要求可解析的 `time_column`；`clock_mode=index` 只允许无真实时间的匿名数组，要求稳定行序和显式 `sampling_interval`，并禁止伪造墙上时间或时区。
  - 文件类引用必须拒绝绝对路径、`..`、符号链接/重解析点逃逸和未知 scheme；connection 只允许已登记 connector ID，profile 不保存 URL 或 secret。
  - 把 profile/license gate 接入 G0 preflight；错误返回具体字段、样例计数和修复提示，不得静默改列名、时钟模式、时区、解析根或连接类型。
  - execution/activity 保存 profile version、原始相对引用、`source_digest` — 输入内容摘要，以及实际事件时间范围或索引范围。

- [ ] G1.3 建立 domain profile
  - 光伏 profile 仅保存实体映射、标签空间、K4 来源规则、展示文案、候选/告警默认建议和权限。
  - 通用点 core 不得导入 PV domain module。

- [ ] G1.4 建立 acquisition manifest
  - 为现有 PV 冻结快照写完整 manifest（相对本地引用、digest、train/validation/test/replay role）。
  - NASA、FHC、PVDAQ 只允许 unverified 占位条目（URL、许可未知状态、`redistribution_allowed` 未核验）；**不得**把本地下载、NPY adapter 或全量 PVDAQ 作为 G1 退出条件。下载与 adapter 属于 G6。
  - 外部大数据不提交仓库。

- [ ] G1.5 前端 profile 选择与报告
  - Workflow Editor 提供 profile/version 选择、预览和 preflight。
  - loading、empty、error、retry、schema-blocked、disabled 和 ready 状态齐全；失败保留用户配置。许可 blocked 文案可先对 PV 生效，NASA 再分发文案推迟到 G6。

**建议路径：**

- `backend-service/services/timeseries_profiles/` — profile 模型、版本、preflight 和 adapter registry。
- `backend-service/api/timeseries_profiles.py` — profile CRUD/version/preflight API。
- `frontend-sevice/src/types/timeseriesProfile.ts` — profile TypeScript 合同。
- `frontend-sevice/src/services/timeseriesProfileApi.ts` — profile API 客户端。

**定向验证：** 现有 PV CSV/Parquet 的 event-time profile 一个最小 fixture；重复时间点、非单调、缺列、标签越界、绝对路径、`..`/链接逃逸、未知 connector 均有测试。NASA NPY index-clock adapter **不是** G1 必测项。前端运行 build/lint。

**退出门槛：**

- [ ] 现有 PV 冻结快照有可用、可追溯的 dataset/domain profile 与 preflight 报告。
- [ ] 不改业务代码即可在同一模板上切换 PV profile 版本（外部数据集切换属 G6）。
- [ ] 未下载 NASA/FHC/PVDAQ 全量数据也可退出本批。
- [ ] 前端 PV profile 读取/阻断状态可理解。
- [ ] 完成自审和 Batch G1 小结。

## Batch G2：普通点算子与真实点因果核心

**目标：** 把现有点 POC 中可复用的 Causal TCN trainer/artifact、因果窗口思想和审计抽到 wrapper，并以 12 个普通可见 `ts_point_*` 暴露；不创建子图，也不复用 strict-grid builder。**无网格 ≠ 薄封装现有 grid POC**：窗口合同必须重建，并在真实点序列上**重训**；旧 `model.pt` 不得当新 Champion。

**前置条件：** G1 的现有 PV profile 合同冻结；现有 POC 输出仅作只读对照，不是新合同金标。

- [ ] G2.1 新建 `backend-service/services/timeseries_point/`
  - P0 实现 profile map、schema validation、point label join、existing-row causal imputation、temporal/group split、real-point causal windows、Causal TCN training adapter、current-point prediction、metrics 和 annotation candidate intervals。
  - P1 再实现 point cross-validation 与 persistence alarm；P0 用 temporal split 的固定 validation/test 留出评估，正式告警保持关闭。
  - 核心只依赖通用 profile/工件接口，**尽量**不依赖光伏 API、PV registry、页面或硬编码列名。**尽量**不要 `if dataset ==`、`pv_fault`、逆变器、设备日、K4 进入 `timeseries_point`；确需时收到 adapter/domain，并记录例外。
  - 输入序列是按实体和事件时间稳定排序的**真实记录**；核心不得生成规则时间戳、虚拟行、整日 288 槽或重采样聚合。
  - **建议**增加一份非光伏形状最小 CSV fixture（多实体、不规则间隔、点标签，列名尽量不抄光伏字段），用同一 10 个启用算子试跑 map→validate→impute→split→window→train/predict→metrics。跑不过只记差异，不是外部数据验收，也不挡 G2 退出。

- [ ] G2.2 按三档复用实现 12 个普通算子
  - **薄封装：** `ts_point_profile_map` — 画像映射、`ts_point_validate_schema` — schema/重复点校验、`ts_point_train_classifier` — 复用 `RealtimePointTrainer` 与 Causal TCN 核、`ts_point_predict` — 复用 realtime-point artifact loader/forward。
  - **现有核改造：** `ts_point_causal_impute` — 去除 grid 依赖且只改已有行空值、`ts_point_temporal_split` — 泛化 POC 实体/时间隔离、`ts_point_causal_window` — 改成目标点加此前 W-1 个真实点、`ts_point_metrics` — 固化点/事件/延迟/误报/no-decision/coverage。
  - **确需新写：** `ts_point_label_join` — 禁天标签广播、`ts_point_candidate_intervals` — 连续真实点预测投影成候选区间。
  - **P1：** `ts_point_cross_validate` — 实体/时间 fold、`ts_point_persistence_alarm` — 只读当前与过去预测的持续性状态机。
  - 旧 `merge_label` 的天标签广播、`handle_missing` 的未来插值/bfill、`sliding_window` 的无实体/split/gap 感知和 `resample_timeseries` 的网格生成均不得进入目标点模板。

- [ ] G2.3 建立普通 wrapper 与画布合同
  - 新建 `backend-service/services/operator_backends/ts_point_*.py`；每个 wrapper 只有一个 `OPERATOR_ID` 与 `execute(params, inputs) -> dict`，负责合同转换和错误映射，不复制算法。
  - 画布固定展示 12 个一级普通节点：`ts_point_profile_map`、`ts_point_validate_schema`、`ts_point_label_join`、`ts_point_causal_impute`、`ts_point_temporal_split`、`ts_point_causal_window`、`ts_point_train_classifier`、`ts_point_predict`、`ts_point_cross_validate`、`ts_point_metrics`、`ts_point_candidate_intervals`、`ts_point_persistence_alarm`。
  - P0 启用其中 10 个（排除 cross-validate/alarm）；P1 两个若展示必须 disabled 并写延期原因，不能进入 P0 发布模板。
  - `ts_point_profile_map` 必须作为用户手工拖入的可见节点；不得藏进 input contract。不存在 `ts_point_align_grid`，也不得换名实现等价 grid/resample 节点。
  - 长任务返回 activity/artifact ref，不在纯节点里写 registry 或标签。
  - 12 个计数只覆盖新点域 `ts_point_*`。source load 固定使用 G0 冻结的可见普通 `load_csv`，明确 `model_ref` load 固定使用可见普通 `load_model_artifact`，二者都必须手工入图且不计入 12 个；`model artifact` 是 train 节点输出，不是隐藏节点。
  - NPY/RData 等 `load_csv` 不支持的非表格格式，必须在 G1/G6 对应模板入图前登记独立 adapter-backed 普通 source operator，冻结稳定 `operator_id`、端口、schema 和只读副作用；profile 或执行器不得隐藏加载。
  - model candidate registration 是 succeeded execution 后模板声明且单独审计的控制面投影，不扩展 runtime graph；若改建为算子，必须分配 `operator_id` 并在画布可见。

- [ ] G2.4 固化真实点序列、typed window 与唯一 outcome 合同
  - 同实体按 `(event_time, stable_source_order)` 稳定排序；同时间同内容按幂等身份去重，同时间冲突值明确失败。
  - `ts_point_causal_impute` 仅在已有行内使用该实体过去真实点填充空特征，同时输出 missing mask、距上次有效值时长和相邻真实点 time gap；行数和时间戳必须不变。
  - 每个窗口由当前 pending point 和 committed history 中此前最多 W-1 个真实点组成，末端身份必须等于当前点；允许跨日使用已发生历史，不跨实体、split 或未来。
  - `ts_point_causal_window` 只输出 `window_result` — typed 窗口状态，取 `ready` 或带原因的 `not_ready`；它不得持久化业务 no-decision。
  - `ts_point_predict` 是 accepted point 唯一的 `point_outcome` — 点结果 owner：ready 时输出 prediction；历史不足、长间隔、当前必需特征仍缺失、window not-ready 或 artifact 合同不匹配时输出带原因的 `no_decision`，不得伪造正常预测或产生第二份结果。
  - candidate、metrics 和 P1 alarm 只能消费已提交 outcome，不得从 window state 另计或覆盖结果。

- [ ] G2.5 因果、事务、泄漏与逐点测试
  - 修改目标点之后的记录，当前窗口、预测和候选状态不变。
  - 不同实体不互相填值；先 split 再 window；`locked_holdout` 不进入 train/validation。
  - 测试完整状态机：读取 committed history → 当前点仅作为 pending 参与窗口 → `ts_point_predict` 生成唯一 outcome/evidence → 原子提交当前点到 committed history、outcome/evidence 与 cursor。对 history、outcome、evidence、cursor 的每个注入失败点都验证全部回滚；同一稳定身份与 `idempotency_key` 重试不得重复追加历史或 outcome。
  - 对每个通过 schema/幂等校验并被 replay admission 接受的真实点，必须恰好产生一个 `prediction` XOR `no_decision` 及 evidence；`ts_point_causal_window.not_ready` 不得生成第二份持久化 no-decision，输出身份集合不得包含源中不存在的时间戳。
  - candidate/metrics/alarm 使用同事务 outbox 或独立幂等消费者投影已提交 outcome；投影失败不得回滚或重复 point outcome，也不得改变 exact-one 计数。
  - 格式非法或冲突重复必须产生显式 rejection/error，pending point 不进入 committed history，outcome/evidence 与 cursor 均不推进，禁止静默丢点。
  - P0 恢复冲突点只允许修正源记录后以同一稳定身份和幂等键重试；不得自动 skip 后推进 cursor。若未来需要人工 quarantine/skip，必须另立带权限与审计的合同。
  - 非规则间隔、跨日、重复点、冲突重复、长间隔、历史不足和微批顺序均有测试；不得假设固定 5 分钟或整日 288 点。
  - `benchmark_ground_truth`、`reviewed_annotation`、`pseudo_label` 和 `candidate_only` 按合同过滤。

- [ ] G2.6 POC 复用与差异审计
  - 对照 `backend-service/services/iterative_labeling/realtime_point/trainer.py` — Causal TCN 训练核心与 artifact loader，证明模型结构和工件合同被复用而非另写通用 sklearn 分类器冒充等价。
  - 对照历史 `causal_window_builder` 记录其 strict 5 分钟 `_align_causal_grid()` 行为，但目标回归只比较可兼容的样本身份、窗口方向、trainer 输入、指标和拒绝原因；grid 输出不作为新合同金标。
  - 在真实点窗口合同上完成一次最小重训；产物写入相对路径新目录，不得覆盖旧 grid `model.pt`，也不得把旧权重登记为新合同兼容 Champion。
  - 差异必须解释并批准；不覆盖原快照和模型。

**禁止：** 不修改 `handle_missing`、`resample_timeseries`、`sliding_window`、`merge_label` 或 `train_test_split_ts` 默认语义；不把目录登记当实现完成；不创建子图/recipe/组合节点。

**定向验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests -q -k "timeseries_point or causal_window or causal_impute or real_point or point_metrics or candidate_interval"
conda run -n cp_web python -m py_compile services/timeseries_point/*.py services/operator_backends/ts_point_*.py
```

**退出门槛：**

- [ ] P0 10 个 `ts_point_*`、`load_csv` 与 `load_model_artifact` 全部被 `OperatorRouter` 发现且可执行，machine-readable 合同、前端目录、冻结 graph、preflight 与 runtime 端口一致；非表格模板使用的 adapter-backed source operator 也已在入图前冻结。
- [ ] P1 两个节点 disabled 且未进入 P0 graph；子图/recipe/组合节点数量为 0。
- [ ] `ts_point_align_grid` 或等价 grid/resample backend、目录节点和模板引用数量为 0。
- [ ] 非规则真实点序列的一点一结果、因果、实体隔离、split/window、no-decision 和来源过滤测试通过。
- [ ] 已在真实点合同上重训；旧 grid POC `model.pt` 未登记为新合同 Champion，也未标兼容。
- [ ] 非光伏最小 CSV fixture **尽量**与 PV fixture 走同一组 `ts_point_*`；有差异则记录，不挡本批。
- [ ] 通用 core **尽量**无 `pv_fault` 分支，且确认复用了 `RealtimePointTrainer`/artifact 核。
- [ ] POC 差异已记录且旧产物未修改。
- [ ] 完成自审和 Batch G2 小结。

## Batch G3：单 Slot 模板族与天/点端到端链路骨架

**目标：** 形成四个可复制、可执行、可版本化的完全展开模板角色；让 `pv_day` 与 `pv_point` 各自从工作流组建走到部署和精度运营。G3 必须有**最小可点 UI**（选 slot、执行模板、看见本次产物）；完整深链打磨属于 G7。

**前置条件：** G2 通过（含真实点合同重训）；G0 不允许 skipped-success。跨数据集不是前置，先用现有 PV 数据打通两条产品链。G4 完整 verification 公式不是本批退出条件。

- [ ] G3.1 产品化 `pv_day.train_eval`
  - 以现有 quickval CV 模板为等价基线，外置 source/profile/label/evaluation contract。
  - 固定 `slot=pv_day`、`template_role=train_eval` 和同槽位 `slot_config_ref`；不保存 `scenario_key`。
  - 同输入比较旧编排和新模板输出；不得顺带改变 RF、日特征和现有指标。

- [ ] G3.2 产品化 `pv_day.predict`
  - 以现有 quickval predict 为基线；只消费明确 day `model_ref` 和 readiness input。
  - 无合格设备日时输出 empty/no-decision，不调用点模型，也不隐式训练。

- [ ] G3.3 新建完全展开的 `pv_point.train_eval`
  - 用户手工连接 G0/G2 的普通节点；表格 P0 graph 明确包含可见 `load_csv` → profile-map → validate → label-join → existing-row causal-impute → temporal-split → real-point causal-window → train → predict → metrics，并按模板用途显式连接 candidate-interval 投影；非表格源只可替换为 G1 已冻结的 adapter-backed 普通 source operator。
  - 不引用 subgraph/recipe，不含 grid/resample/时间取整节点；P0 不放 cross-validate/persistence-alarm，也不隐藏 source/model loader。
  - 复用 `RealtimePointTrainer`/Causal TCN artifact，输出点/事件/延迟/误报/no-decision/coverage 指标、模型 artifact 和带成功 source execution 的 model candidate。

- [ ] G3.4 新建 `pv_point.predict_replay`
  - **冻结 graph** 只含可见普通算子：source loader、profile-map、validate、existing-row causal-impute、real-point causal-window、`load_model_artifact`、predict，以及模板声明的可选 candidate/metrics。消费显式 point `model_ref`。不得把 admission、committed history、cursor 或事务画成 `operator_id`。
  - **`replay_activity`** 按实体和事件时间暴露下一真实点或确定性小批，批内仍逐点处理；对每个 pending point **调用同一份冻结 graph 一次**，不得为每个点创建互异草稿 graph，也不得另写第二套预测代码。
  - 状态机固定为：activity 从 committed history 读取过去点 → 当前点作为 pending 交给本次 graph → graph 内 `ts_point_causal_window` 产出 typed `window_result` → `ts_point_predict` 生成唯一 `point_outcome`/evidence → activity 原子提交当前点到 committed history、outcome/evidence 与 `replay_cursor`。任一写失败全部回滚，不得先改 buffer 再写结果。
  - `candidate_projection_enabled` — 是否持久化产品标注候选，默认 JSON boolean `false`；false 时只返回由**已提交 outcome**生成的确定性只读区间 artifact。只有产品用途、权限和显式开关通过才可通过 outbox/幂等投影写 annotation candidate；投影失败不得回滚、复制或覆盖 point outcome，benchmark slot 强制关闭。
  - 不生成规则网格、虚拟点或整日 288 点容器；正式告警保持关闭。P0a 不要求完整 verification/Promote true。

- [ ] G3.5 模板发布、复制与 slot 门禁验收
  - 发布不可变版本；从每个模板创建实例，修改实例不改变源模板。
  - 四个角色不能通过参数互换 slot；把 request/template/config/profile/evaluation-contract slot 一致性、完全展开 graph 和 point real-event causal capability 接入 preflight。
  - 新模板显式绑定 `dataset_profile_ref` — 数据集 profile 引用、`domain_profile_ref` — 领域 profile 引用和 `slot_config_ref`，或各自在同 slot 只有一个不可变默认；响应回显最终引用和解析来源。

- [ ] G3.6 打通 `pv_day` 端到端链路骨架
  - Workflow Editor 组建/复制/发布 `pv_day.train_eval` 与 `pv_day.predict` → succeeded train execution 产出可追溯 `model_ref` → predict execution 产出设备日预测/evaluation → Algorithm Deployment `?slot=pv_day` **最小展示**本次产物 → 现有 `LoopOrchestrator`/日检改为触发已发布预测工作流 execution（不得旁路评分）→ Accuracy Operations `?slot=pv_day` **最小展示**本次设备日指标。
  - 每段记录 `source_workflow_id`、`source_workflow_version`、`source_execution_id`、model/evaluation artifact ref；禁止隐式重训和点路径补位。
  - P0a 允许「训练成功 → 同 slot 可追溯 model_ref → 预测消费该 ref」，不强制完整 verification 公式或 Promote true。开始对新 slot 双读，仍不改写现网 `pv_fault` 生产指针。

- [ ] G3.7 打通 `pv_point` POC 产品链骨架
  - Workflow Editor 手工组建/发布 `pv_point.train_eval` 与 `pv_point.predict_replay` → **真实点合同重训** execution 产出新 `model_ref`（旧 grid `model.pt` 不得当 Champion）→ `replay_activity` 按真实点 cursor 喂数并每次调用同一冻结 graph → Algorithm Deployment `?slot=pv_point` 最小展示来源可追溯模型 → Accuracy Operations `?slot=pv_point` 最小展示本次点/事件/延迟/误报/no-decision/coverage。
  - P0 persistence alarm 保持关闭；以原始预测、no-decision 和只读候选区间验证链路。
  - 修改当前 cursor 之后的真实点不影响当前窗口和预测，形成因果证明；输入与输出身份对账证明无虚拟时间戳。

**前端验收（G3 最小集，不是 G7）：** 能选 `pv_day`/`pv_point`、打开对应 Train/Predict 模板、执行、并在 Deployment/Accuracy Operations 看见本次产物。复制、全状态矩阵、深链跳转属于 G7。

**退出门槛：**

- [ ] 四个模板角色都有真实 backend，graph 完全展开，无 slot 切换参数、子图或隐藏计算节点；`replay_activity` 不是 graph 节点。
- [ ] Day 等价回归通过；Point 非规则真实点与未来扰动因果回归通过；点链使用 G2 重训产物，未把旧 grid 权重当 Champion。
- [ ] 训练与预测职责分离；Point replay 的 pending point → unique outcome/evidence → committed history/cursor 原子事务通过故障注入与幂等重试测试，下游投影不改变 exact-one 结果。
- [ ] `pv_day` 已从工作流组建跑到训练、预测、部署入口、Orchestrator/日检触发工作流和同槽位精度运营（最小 UI）。
- [ ] `pv_point` 已从工作流组建跑到真实点合同训练、逐真实点 `replay_activity`、部署入口和同槽位精度检测；grid/resample/虚拟点计数为 0。
- [ ] Deployment/Accuracy Operations 本次展示记录均可追溯到 succeeded workflow execution；Orchestrator 不再旁路评分。
- [ ] 现网 `pv_fault` 生产指针未被本批改写。
- [ ] 模板实例不覆盖源版本。
- [ ] 完成自审和 Batch G3 小结。

## Batch G4：槽位内模型治理与工作流来源门禁

**目标：** 在 P0b 闭环累计前建立单 `slot` 治理硬边界，并保证 model candidate、verification、registry 和 evaluation 全部来自成功的真实工作流 execution。G3 已开始对新 slot 双读；**本批才切写**新 `pv_day`/`pv_point` registry。现网 `pv_fault` 生产 Champion 仍禁止被 P0b 演示 Promote true 改写。

**前置条件：** P0a（G3）两条链路骨架通过。G0 只读映射报告已存在；本批在切写前再生成治理记录差异报告，不在 G0 迁表。

- [ ] G4.1 数据模型、来源字段与兼容映射
  - model candidate、verification、registry、promotion log、alert、monitoring 和 evaluation store 只增加/保留一个 `slot` 分区；删除新合同中的 `scenario_key`。
  - 每条 model candidate/evaluation/prediction batch 保存 `source_workflow_id` — 来源工作流 ID、`source_workflow_version` — 冻结版本、`source_execution_id` — 成功执行 ID 和对应 artifact ref；来源缺失、execution 非 succeeded 或 source slot 不一致时拒绝登记。
  - 旧 `(pv_fault,pv_day)` 映射为 `pv_day`，旧 `(pv_fault,pv_point)` 映射为 `pv_point`；无法可信判断的记录进入 ambiguous 清单，不根据列名或客户端标记猜测。
  - 兼容响应回显 `slot_resolution_source=legacy_mapping`；新 API 必填 slot 且拒绝 `scenario_key`。

- [ ] G4.2 槽位级 evaluation contract
  - `pv_day` 与 `pv_point` 独立维护 `metrics` — 指标、`window_policy` — 窗口策略、`aggregate_method` — 跨窗聚合方式、`score_margin` — 分差门槛、`min_windows_challenger_better` — 最少优胜窗数和 `quality_gates` — 质量门禁。
  - Compare 固定不可变评测尺子，不冻结 Challenger 内部结构；verify 请求只引用已发布 `evaluation_contract_ref` — 评测量约引用，不得临时覆盖门槛。改门槛必须发布新版本。

- [ ] G4.3 Verification queue 与不可变双来源证据
  - 按 slot、`model_candidate_id` — 模型候选 ID、model signature、量约引用和当前 Champion 去重；只与同 slot Champion 比。
  - verify 写请求要求 `verification_workflow_ref` — 同 slot 不可变复验工作流引用、`evaluation_contract_ref` — 评测量约引用和 `idempotency_key` — 幂等键；同键同 payload 返回原 comparison，同键不同 payload 返回 conflict。
  - verify-async 必须创建真实 evaluation workflow execution；`comparison_id` — 比对任务 ID只用于轮询。只有该 execution succeeded 并发布 evaluation artifact 后，才能完成最终 verification；不得用 candidate 训练 execution 冒充复验 producer。
  - 完成后写不可变 record：`verification_id` — 复验记录 ID、`comparison_id`、`model_candidate_id`、`candidate_source_workflow_id` / `candidate_source_workflow_version` / `candidate_source_execution_id` — 候选训练来源三元组、`model_artifact_ref` — 与训练 producer 绑定的候选模型工件、`verification_workflow_ref`、`verification_source_workflow_id` / `verification_source_workflow_version` / `verification_source_execution_id` — 本次复验评测来源三元组、`evaluation_artifact_ref` — 与评测 producer 绑定的复验工件，以及 status/passed/eligible/slot/量约/门禁摘要/Baseline/Challenger/registry version/数据窗口/分项结果/失败原因。
  - `passed=true` 仅当 verification 任务与复验 workflow execution 均 succeeded、candidate/两组 producer/contract/registry 的 slot 一致、两个 artifact 分别匹配各自 producer、`eligible_for_pool=true`、分差/胜窗数/全部阻断质量门禁通过且无 failure；Champion 或 registry version 改变后证据过期。

- [ ] G4.4 Slot model registry
  - 登记存什么：每个 slot 的每个不可变版本分别保存 Champion 与 Challenger 两组 provenance。
    - Champion 组：`champion_model_ref` — 当前生产模型、`source_model_candidate_id` — Champion 来源候选、`source_workflow_id` / `source_workflow_version` / `source_execution_id` — Champion 训练 producer、`model_artifact_ref` — Champion 工件、`verification_id` — Champion 采用的复验。
    - Challenger 组：`challenger_model_ref` — 已采纳未切生产模型、`challenger_model_candidate_id` — Challenger 来源候选、`challenger_source_workflow_id` / `challenger_source_workflow_version` / `challenger_source_execution_id` — Challenger 训练 producer、`challenger_model_artifact_ref` — Challenger 工件、`challenger_verification_id` — Challenger 采用的复验。
    - 共享字段：`registry_version`、`updated_at` 和 `note`。无前缀 `source_*` 只描述 Champion；存在的任一组缺必需来源时不得进入 Deployment/Accuracy Operations 主列表。
  - 为什么单独存：训练成功不等于生产；registry 是预测工作流、Deployment 和调度器获取稳定 model ref 的控制面真源，与 artifact、execution 和预测记录分离，不拥有训练代码。verification 只写证据，不直接写 registry；常规写入者只有 Promote。
  - 按什么分区：只按 slot；`pv_day`、`pv_point`、`load_forecast` 和各 `benchmark_*` 独立。benchmark-local execution/artifact/evaluation/evidence 可以保存，但 benchmark 的 model candidate、registry、Promote 始终禁止且不可通过配置或权限翻转；产品 slot 之间不回退。
  - 路径/介质：由部署配置决定，可为数据库或相对配置目录；只存稳定 ID/相对 artifact ref。
  - GET 只读，不存在返回可诊断空槽；普通 UI 无绕门禁覆盖写。高权限恢复若存在，只能把同一 product slot 已存在的不可变 registry 版本恢复为新的受审计版本，完整保留两组 provenance，并带 expected version/幂等键/原因；来源或目标为 benchmark、跨 slot、来源缺失或手造记录时直接拒绝。

- [ ] G4.5 Promote 与 append-only 审计
  - `POST /api/model-candidates/{model_candidate_id}/promote` 中，`model_candidate_id` — 待采纳模型候选路径参数。
  - 请求必填 `verification_id`、`operator` — 操作人、`reason` — 原因、`expected_registry_version` — 期望登记版本和 `idempotency_key`；`production_slot` — 目标生产槽位默认等于 candidate slot，但显式值仍必须一致。
  - `set_as_production` — 是否同步切换 Champion，默认 JSON boolean `false`。门禁通过后，false 把该 candidate 的 `challenger_model_ref`、训练 provenance 与 verification 写入独立 Challenger 组，Champion 保持不变；true 把同一 candidate 原子写为同 slot Champion，并清理该已晋升 Challenger 组。两者都不得写旧 Champion、workflow ID、模板 ID或另一 slot 模型。
  - candidate 训练 execution、verification 评测 execution、contract 与 registry 的 slot/artifact producer 任一不一致，复验未 passed、Champion/registry version 已变化、benchmark slot、权限不足或幂等冲突时零副作用失败。
  - `promotions_log` — 晋升操作日志只追加、不可编辑/删除；每条保存 model candidate 的训练 provenance、verification 的评测 provenance、`adopted_challenger_model_ref` — 本次采纳挑战者、`previous_champion_model_ref` — 操作前 Champion、nullable `new_champion_model_ref` — 仅生产切换时的新 Champion、`resulting_champion_model_ref` — 操作后实际 Champion、`champion_changed` — 是否切换生产，以及 `production_slot`、`set_as_production`、operator/reason/idempotency/result/time。
  - false 分支固定 `new_champion_model_ref=null`、resulting=previous、`champion_changed=false`；true 分支固定 new=resulting=adopted、`champion_changed=true`。缺成功来源时不得记录成功 Promote，幂等重放不得重复追加。

- [ ] G4.6 Workflow-only evaluation store
  - 每次评估只追加 slot、source workflow/execution、`model_ref`、dataset profile、evaluation contract、时间窗、metrics、drift、quality、status checks 和 artifact ref。
  - Accuracy Operations 只能查询这些记录并做无业务语义展示聚合；不得在页面或专用 service 重新运行评分算法。
  - Drift/alert 只触发调查或已注册工作流，不自动生成无来源 model candidate 或自动 Promote。

**关键条件分支：**

```text
source_execution.status != succeeded or source_execution.slot != model_candidate.slot       → reject provenance
model_candidate.slot != registry.slot or verification.slot != model_candidate.slot           → reject cross-slot
verification.model_candidate_id != model_candidate.id or verification.passed != true          → reject
verification.baseline_model_ref != registry.champion_model_ref                                → reject stale evidence
verification.registry_version_at_start != registry.registry_version                            → reject stale evidence
set_as_production != true                                                                       → register candidate + provenance + verification as Challenger; keep Champion
otherwise                                                                                       → register same candidate as Champion and clear the promoted Challenger group
```

**退出门槛：**

- [ ] model candidate、verification、registry、evaluation 查询和写入只按 slot 分区。
- [ ] 所有治理和运营主记录都可追溯到 succeeded workflow execution/artifact；缺来源写入为 0。
- [ ] 跨 slot compare 只能只读，不能 eligible/Promote；benchmark execution 的产品治理写入为 0。
- [ ] verification 的 candidate training producer 与 verification evaluation producer 两组 provenance、各自 artifact 绑定、passed 公式、不可变字段和 stale evidence 测试通过；`comparison_id` 未被当成 execution 来源。
- [ ] Promote 默认写 Challenger 且不改 Champion，true 写 Champion 并清理已晋升 Challenger；两组 provenance 与 audit 的 adopted/previous/new/resulting/champion_changed 断言通过，slot/来源/Champion/version 任一不匹配均零副作用。
- [ ] verify/Promote 幂等重放、同键冲突、并发冲突和 append-only 审计测试通过。
- [ ] 旧记录迁移有可回滚映射与 ambiguous 清单。
- [ ] 完成自审和 Batch G4 小结。

## Batch G5：天/点累计快照与双闭环

**目标：** `pv_day` 与 `pv_point` 各自完成一轮“预测 → 候选 → 人工审核 → 构建新快照 → 固定版本重训 → 同 slot 复验 → 人工 Promote（本轮显式 `set_as_production=true`）→ 再预测/回放”，证明数据集按槽位越滚越大并确实切换到新 Champion；快照、重训、复验、Promote 四步必须显式分离。**禁止**在现网 `pv_fault` 生产 Champion 上做这次 `set_as_production=true`；必须使用演示数据或非现网指针。

**前置条件：** P0a（G3）两条链路骨架通过；G4 的 provenance、model candidate、verification、registry 与 Promote 合同可用。跨数据集验证不是前置，本批先使用现有 PV 或独立演示数据。

- [ ] G5.1 通用 annotation candidate contract
  - 保存 `annotation_candidate_id` — 标注候选 ID、`slot` — 唯一路径槽位、`source_workflow_id` — 来源工作流 ID、`source_workflow_version` — 冻结版本、`source_execution_id` — 成功执行 ID、`model_ref` — 来源模型、`dataset_profile_ref` — 数据 profile、`entity_key` — 实体标识、真实点/设备日边界、建议标签、置信度、策略版本和 `review_status` — 审核状态。
  - annotation candidate 按稳定 fingerprint 去重；不同 slot 即使边界相同也不合并；不得与 G4 model candidate 共表或共用无类型 ID。
  - 只有产品 slot、来源 execution succeeded、权限和 `candidate_projection_enabled=true` 才可登记；benchmark execution 只产 `candidate_evidence_artifact` 等 benchmark-local evidence artifact，不登记产品 `annotation_candidate` 或 `reviewed_annotation`。可选审核只能形成 G8 定义的 benchmark review artifact。

- [ ] G5.2 审核事务
  - 复用候选队列、ECharts 框选、改边界、改类别、动态标签、拒绝、撤销和断点恢复。
  - 批准生成 `reviewed_annotation`，保留 `source_annotation_candidate_id` — 来源标注候选、`reviewer` — 审核人、审核时间、原/新边界、`label_space_version` — 标签空间版本和 `annotation_role` — 标注用途。
  - candidate 状态与 annotation 写入原子，或通过 `idempotency_key` 可重放；同键不同 payload 返回 conflict。
  - 审核 UI 覆盖 loading、empty、error、retry、disabled、submitting、success、failure、conflict、permission denied、重复提交和撤销恢复。

- [ ] G5.3 `slot_dataset_snapshot` 稳定链与 bootstrap v1
  - 每个产品 slot 恰好保存一个 `snapshot_id` — 快照链稳定 ID；链内 `snapshot_version` 单调递增，后续 build 必须返回同一个 ID，不得每版另造 snapshot ID。
  - 新增 `POST /api/slot-datasets/snapshots/bootstrap-async`：绑定同 slot 不可变 bootstrap/import workflow、dataset profile、幂等键和原因，并创建真实 workflow execution。只有 execution succeeded 且发布基础数据 artifact、`role_partition` — 数据角色分区和 `source_digest` — 来源摘要后，才原子发布 `snapshot_version=1`、`base_snapshot_version=null`；同 slot 已有链时 conflict，失败不留半链。
  - 每个后续版本保存 `slot`、`base_snapshot_version` — 上一版本、`added_annotation_refs` — 新增生效标注、`added_source_candidate_refs` — 来源候选、role partition、label space version、source digest、dataset profile 和创建审计。
  - snapshot builder 只接受同 slot 的 `reviewed_annotation`，并要求请求携带当前 stable `snapshot_id` 和 current latest base version；candidate-only、跨 slot 标注和 role 冲突阻断。成功只在同一链追加版本并原子移动 latest，失败保留上一可用版本。
  - `domain_import` 与 `pseudo_label` 不得借增量 build API 混入；若需进入 learning，必须走独立显式 import/admission workflow 发布不可变 import/base snapshot，或先经领域审核形成新的 `reviewed_annotation`，且不得进入 locked holdout。
  - 快照固定 annotation query、source/role stats、split manifest、profile/workflow/operator digests 和相对 artifact refs；`locked_holdout` 不得进入 learning/validation。

- [ ] G5.4 四个显式动作与 API 边界
  - **动作 1：构建快照。** bootstrap v1 已存在后，用户选择同 slot reviewed annotations，并提交 stable `snapshot_id` 与 current latest `base_snapshot_version`；异步构建成功只在同一 ID 下生成版本 +1，base 过期返回 conflict。
  - **动作 2：固定版本重训。** retrain workflow 只读路径参数 `snapshot_id` — 快照链稳定 ID 与 `snapshot_version` — 不可变版本组成的明确 `snapshot_id@snapshot_version`；任何存在且 ID/version/slot 匹配的历史不可变版本都允许重训，不要求 current latest，也绝不自动替换为 latest。成功生成同 slot `model_candidate_id` 并保存完全相同的 `dataset_snapshot_ref` 与 source execution；缺任一参数、版本不存在或 ID/version 不匹配均失败；不自动复验。
  - **动作 3：发起复验。** verification 绑定固定 model candidate、同 slot `verification_workflow_ref` 与量约，创建真实 evaluation workflow execution；成功/失败均不直接写 registry。
  - **动作 4：人工 Promote。** 一般请求默认 `set_as_production=false`，门禁通过后写 Challenger 而 Champion 不变；本批 Day/Point 闭环验收必须在有效 passed verification 后显式传 `set_as_production=true`，才把同一候选更新为 Champion 并清理已晋升 Challenger。receipt 记录 adopted/previous/new/resulting/champion_changed 与 expected/current registry version。**本批 Promote true 的目标槽位只能是 `pv_day` / `pv_point` 演示指针，禁止写现网 `slot=pv_fault` 生产 Champion。**
  - bootstrap 与上述四类写请求都带独立幂等键；同键同 payload 返回原结果，同键异 payload conflict。任一步成功不得自动触发下一步。

- [ ] G5.5 天/点标注与累计隔离
  - Day 整日裁决只进入 `slot=pv_day`；Point 点/区间只进入 `slot=pv_point`，K4 companion 属于 point。
  - 天快照以设备日为样本单位；点快照以真实点/因果窗口为样本单位。跨 slot 关联只用于只读诊断，无自动广播、聚合或角色转换。
  - 两条快照序列分别维护版本号、标签空间、source digest 和 slot config/profile 引用，不共享 snapshot ID 或训练入口。

- [ ] G5.6 完成 `pv_day` 一轮闭环累计
  - `pv_day.predict` succeeded execution 产生设备日候选 → 人工批准/改类 → 新天级 reviewed annotation → 显式构建天快照 +1 → 从固定版本运行 retrain workflow → Day model candidate → Day verification → 人工 Promote（本轮显式 `set_as_production=true`）→ `pv_day` registry 更新 → 再执行一次 day predict。
  - 对账旧/新快照样本数、来源、角色和摘要；证明新增样本只来自本轮审核且旧版本未变；Promote receipt 记录旧/新 Champion 与 expected/current registry version。

- [ ] G5.7 完成 `pv_point` 一轮闭环累计
  - `pv_point.predict_replay` 逐真实点预测 → `ts_point_candidate_intervals` → 人工批准/改边界/改类 → 新点/区间 reviewed annotation → 显式构建点快照 +1 → 从固定版本运行 point retrain workflow → Point model candidate → Point verification → 人工 Promote（本轮显式 `set_as_production=true`）→ `pv_point` registry 更新 → 继续逐真实点 replay。
  - 对账候选区间、逐点/窗口样本身份与新增快照统计；证明未审核区间、虚拟点、未来点和 locked holdout 均未进入训练；Promote receipt 记录旧/新 Champion 与 expected/current registry version。

**退出门槛：**

- [ ] annotation candidate、reviewed annotation、benchmark ground truth 与 model candidate 使用不同 ID 和状态机。
- [ ] 审核所有成功/失败/冲突/撤销状态可恢复。
- [ ] 天、点各自通过 succeeded bootstrap workflow 建立唯一 stable `snapshot_id` 的 v1（base=null）；后续版本在同一 ID 下只追加，旧版本摘要不变，同 slot 重复 bootstrap 冲突。
- [ ] Snapshot 来源、role 和 locked holdout 泄漏为 0；model candidate 可反查固定训练快照和 succeeded retrain execution。
- [ ] Day 完成 candidate→review→snapshot+1→retrain→verify→`set_as_production=true` Promote→repredict，且只更新 `pv_day`。
- [ ] Point 完成真实点 candidate interval→review→snapshot+1→retrain→verify→`set_as_production=true` Promote→replay，且只更新 `pv_point`。
- [ ] 现网 `pv_fault` 生产 Champion 在本批前后一致，未被 Promote true 改写。
- [ ] 构建只允许 current latest base 且返回同一 snapshot ID；任意显式历史不可变版本均可重训。构建、重训、复验、Promote 是四个独立动作，无自动串行或半写状态。
- [ ] 完成自审和 Batch G5 小结。

## Batch G6：独立 Benchmark Slot 的复用验收

**目标：** 在 P0a 生命周期链通过后，证明同一组普通可见节点和 edges 只换 profile 即可跨数据集运行，同时不污染产品 slot；验证链同样按真实点推进，不使用子图或网格。不强制等 P0b。

**前置条件：** G3（P0a）通过；NASA/FHC 本地下载与许可核验在**本批**发生，不是 G1 退出条件。G6 失败只表示复用验证未通过，不反向抹除已有产品链证据，但阻断“通用复用已验收”的结论。

- [ ] G6.1 通用真实点 replay activity
  - 强制双向不变量：`slot` 以 `benchmark_` 开头 **iff** `execution_purpose=benchmark_reuse`；product slot 不得声明 benchmark_reuse，benchmark slot 也不得声明 product_workflow。服务端无条件计算 `governance_eligible=false`，客户端、配置或权限不能翻转。
  - annotation candidate、snapshot bootstrap/build、model candidate、registry、Promote、正式告警以及高权限 registry 恢复等每个写入口都必须直接按 slot 拒绝 benchmark，不能只信 `governance_eligible` 派生值；逐入口测试零副作用与审计结果。
  - 支持创建、暂停、恢复、取消和查询；持久化 `replay_id` — 回放 ID、`slot` — 独立 benchmark 槽位、profile、source digest、`clock_mode` — 时钟模式、真实事件时间/索引范围、每实体 `replay_cursor`、batch policy、状态和错误。
  - 文件物理存在不表示工作流可见；每次只暴露下一真实记录或确定性小批，批内逐点更新同实体历史并产生 prediction/no-decision。
  - event-time 和 index-clock 使用同一状态机，但不得互转坐标、伪造墙上时间、生成规则网格或虚拟记录。

- [ ] G6.2 NASA SMAP/MSL 泛化
  - 使用 `slot=benchmark_nasa_smap_msl`；NPY adapter 按 channel 输出实体序列，标签区间导入为 `benchmark_ground_truth`。
  - profile 固定 `clock_mode=index`、`time_column=null` 和显式模拟步长；cursor、标签区间和评估都用单调索引，不显示为真实采集时间。
  - train 内切 validation；官方 test 作为 locked holdout。
  - `execution_purpose=benchmark_reuse`，后端强制 `governance_eligible=false`；产品 annotation candidate、slot dataset snapshot、model candidate、registry、Promote 和正式告警节点被 preflight 阻断。
  - 记录 local validation 与 redistribution 两种许可结论，不合并为单一状态。

- [ ] G6.3 FHC Twin-Plant 光伏迁移
  - 使用 `slot=benchmark_fhc_twin_plant`；30 秒原频 profile 保留真实点，不做网格对齐。若另需派生降采样数据，只能作为独立离线数据资产/profile/version，不能进入“真实点链等价”验收。
  - train 只做训练/validation；固定 test 锁定评估并逐真实点模拟 replay。
  - 输出 0–9 多分类与正常/异常聚合指标。
  - 同样以 benchmark reuse 运行且 governance 不可用；不得产生 `pv_day`/`pv_point` 产品候选、快照或 registry 写入。

- [ ] G6.4 补充数据按需要执行
  - NAB 验证单变量流式和异常窗口；small_tep 验证多故障；SKAB 验证多变量点/变化点；GPVS 仅在独立派生数据合同冻结后做压力测试。
  - 每个数据集使用独立 `benchmark_<dataset_key>` slot；均为补充项，不属于 P0 主链退出门槛。

- [ ] G6.5 完全展开 graph 复用证据报告
  - 对比 NASA 与 FHC 的 `workflow_version` — 工作流版本、`operator_ids` — 普通算子 ID 集合、可见节点参数 schema 和 `edges` — 画布连线集合；禁止以 subgraph ID 或隐藏内部图作为复用证据。
  - **优先**只改 `slot`、dataset/domain profile、source ref、label mapping 和合同允许的模型参数；核心节点集合与 edges **尽量**相同，有差异则写入报告。
  - 报告 execution purpose、benchmark-local execution/artifact/evaluation/evidence 写入和产品治理阻断，证明两次 execution 可保存自身复用证据，但均未直接写产品 annotation candidate、slot dataset snapshot、model candidate、registry、Promote 或正式告警。
  - **尽量**不要按 dataset name 写 Python/TypeScript 业务分支；若有，记录原因。输入/输出身份对账仍要求无 grid/resample/虚拟点（这是点路径硬约束，与换数据集无关）。

**验收门槛：**

- [ ] NASA 与 FHC 均完成 load→profile-map→validate→split→real-point-window→train/predict→metrics。
- [ ] 两者**尽量**使用相同普通 operator IDs、可见节点和 edges；无子图。若有节点/算子差异，记录原因，不因此判本批失败。
- [ ] 两次执行均满足 `benchmark_*` slot iff `execution_purpose=benchmark_reuse`，服务端强制 `governance_eligible=false`；annotation candidate/snapshot/model candidate/registry/Promote/formal alarm/high-privilege recovery 各写入口直接拒绝且副作用为 0。
- [ ] test/locked holdout 未参与选模。
- [ ] 逐真实点 replay 因果可见性、非规则间隔和一点一结果测试通过；grid/resample/虚拟点为 0。
- [ ] 报告包含来源、许可、profile、execution、artifact 和 evaluation trace。
- [ ] 完成自审和 Batch G6 小结。

## Batch G7：按 Slot 的前端产品化与工作流产物展示

**目标：** 在现有 Workflow Editor、Iterative Labeling、Accuracy Operations 和 Algorithm Deployment 内形成一致单-slot 信息架构；页面只展示或触发真实工作流/治理 API，不新造业务算法真源。

**前置条件：** G4 治理 API 稳定；G5 双闭环已留证；G6 复用验证完成。

- [ ] G7.1 Workflow Editor
  - 先选择并始终发送 `slot`，展示同槽位 `slot_config_ref`、dataset/domain profile、global config、preflight、模板发布/复制和 execution detail。
  - 画布只展示普通节点；graph 完全展开。不可执行或 P1 节点 disabled；错误定位到节点/字段。
  - 配置合并预览明确从低到高的“平台无业务默认 → 同 slot defaults → 同 slot 模板 → 请求覆盖”顺序；object 递归、scalar/array 整体替换、数组不拼接、schema 允许时 null 为真实值、无隐式类型转换，unknown key 仅 `additionalProperties=true` 时允许。逐字段来源按 JSON Pointer 展示，digest 与后端使用同一 canonical JSON fixtures；不存在 `scenario_key`、subgraph 或自动插入节点 UI。

- [ ] G7.2 Accuracy Operations
  - 使用 `/accuracy-operations?slot=pv_day`、`?slot=pv_point`、`?slot=load_forecast` 或独立 benchmark slot；URL 中 slot 是唯一产品分区。
  - 每个 slot 只显示 succeeded workflow execution 写出的数据质量、prediction/evaluation artifact、模型候选、复验、Champion、evaluation history、告警/监控和累计快照；无来源的记录进入诊断区，不进入主列表。
  - 展示当前 `snapshot_version` — 快照版本、样本总数、本轮新增、来源/role 分布、source digest、对应 retrain execution/model candidate，并支持只读版本对比。
  - “构建下一快照”“从固定版本重训”“发起复验”“Promote”是四个显式动作；失败不自动继续后续步骤。
  - 跨 slot overview 只读，无共同排行榜、Promote 或 winner 文案；页面不得调用专属评分 service。

- [ ] G7.3 Iterative Labeling
  - 显示 annotation candidate ID、slot、source workflow/execution、annotation source/role、benchmark badge、review audit、动态标签、撤销和恢复；不展示或提交 model candidate ID。
  - 审核成功后显示 annotation 所属 slot 和待累计批次；构建下一版前展示 base snapshot version、新增标注数、role 分布、泄漏预检和幂等状态，成功回显新版本但不自动重训。
  - Point 不提供 human day 广播；Day 不把 point range 写成天标签。

- [ ] G7.4 Algorithm Deployment
  - 使用 `/algorithm-deployment?slot=pv_day|pv_point|load_forecast`；每个 slot 独立显示工作流产出的 Champion/Challenger、Shadow、verification 和审计。
  - Promote 默认 `set_as_production=false`；确认区显示 model candidate、source workflow/execution、verification、challenger model ref、production slot、证据新鲜度、门禁、operator 和 reason。
  - 页面不得自训、自预测或重新评分；只触发已注册工作流、verify/Promote API。失败不乐观更新，成功后重新 GET registry；stale verification 提示重新复验。

- [ ] G7.5 全状态、响应式与可访问性
  - loading、empty、error、retry、partial、disabled、submitting、success、failure、conflict、permission denied。
  - 颜色不是唯一状态；URL 保存 slot/filter/object；轮询离开页面即取消。
  - 1440px 与常见笔记本宽度可扫读；窄屏允许只读摘要，不强求复杂审核/Promote。

**验证：**

```powershell
Set-Location frontend-sevice
npm run build
npm run lint
```

另做浏览器手工矩阵：各 slot 深链、刷新、无数据、无 succeeded source execution、后端失败、权限不足、冲突、提交中、成功回执、跨 slot 只读和旧页面回归。

**退出门槛：**

- [ ] UI 始终显式发送一个 slot，不发送 `scenario_key`；URL 刷新恢复同槽位上下文。
- [ ] graph 中无子图/隐藏节点；`pv_point` 模板无 grid/resample 节点。
- [ ] Deployment/Accuracy Operations 主列表中的每条业务结果都能打开 succeeded source workflow/execution 和 artifact/evaluation ref。
- [ ] 不存在页面专属训练、预测或评分业务代码路径。
- [ ] 每个 slot 可查看自己的快照版本、增量、role 和 retrain/model candidate 追溯；四个闭环动作不自动串行。
- [ ] 全状态和 URL 恢复通过；前端 build/type error 为 0，既有 warning 与新增 warning 分开记录。
- [ ] 完成自审和 Batch G7 小结。

## Batch G8：`benchmark_pvdaq_<system>` 无标签复用故事

**目标：** 在不自建公开金标、不污染产品 slot 的前提下，证明同一完全展开点工作流能把真实无标签光伏数据转成预测证据和可选 benchmark-local 审核工件；直接产品治理写入必须为 0，转产品必须走目标 product slot 的显式 import workflow。

**前置条件：** G7 通过；选择一个字段、规模和条款明确的 PVDAQ system。

- [ ] G8.1 选择并冻结独立 benchmark profile/manifest
  - slot 固定为 `benchmark_pvdaq_<system>`，其中 `<system>` 是稳定、可审计的 PVDAQ system key；不同 system 不共享槽位。
  - 请求必须显式 `execution_purpose=benchmark_reuse`；再次验证 `benchmark_*` slot iff benchmark_reuse、服务端强制 `governance_eligible=false`，且配置/客户端/高权限恢复均不能翻转。
  - 对 annotation candidate、snapshot bootstrap/build、model candidate、registry、Promote、正式告警及 registry 恢复逐入口做 benchmark 直接拒绝测试，不得只复用 G6 的派生 flag 测试或遗漏恢复旁路。
  - 明确 system ID、日期、字段、时区、原始事件时间、下载方式、规模、数据条款和相对引用。
  - 数据量先限制在可审计样本，禁止默认拼接多年/数百 GB；profile 不把原数据对齐成规则网格。

- [ ] G8.2 无标签逐真实点 replay
  - 复制 G6 的完全展开 graph，只替换 slot/profile/source 和允许参数；按实体真实点 cursor 逐点或确定性小批运行。
  - 没有真值时只输出 prediction/no-decision、数据质量、candidate evidence artifact 和资源使用，不生成虚假 metrics 或 `benchmark_ground_truth`。
  - `execution_purpose=benchmark_reuse` 强制 `governance_eligible=false`，不得写 `pv_point` annotation candidate、产品快照、model candidate、registry 或正式告警。

- [ ] G8.3 审核验证与产品导入边界
  - 若需要验证人工审核 UX，只能在 benchmark slot 创建明确标记的 `benchmark_review_session` — 基准审核会话和 `benchmark_review_artifact` — 基准审核工件；它们不是产品 `annotation_candidate` 或 `reviewed_annotation`，平台开发者不代替领域专家制造标签。
  - benchmark 审核结果不能直接进入产品 `slot_dataset_snapshot`，也不能直接触发产品 retrain/verification/Promote；该直接写入门禁不可通过配置翻转。
  - 未来若经数据许可、领域归属和产品准入批准用于 `pv_point` 学习，必须通过单独显式 import 工作流生成带来源的新 `reviewed_annotation`；不能靠改 slot 或复制数据库记录绕过。

- [ ] G8.4 复用故事汇总
  - Day：现有 PV 产品数据完成 `pv_day` 独立工作流与闭环。
  - Point：现有 PV 完成 `pv_point` 产品链；FHC 与 PVDAQ 分别证明有标签迁移和无标签真实点 replay 复用。
  - 报告比较普通 operator IDs、edges、profile 差异、source execution/artifact 和副作用计数，不以子图或产品 Promote 作为 benchmark 成功标准。

**退出门槛：**

- [ ] PVDAQ system、数据条款、profile、slot 与相对 source ref 可追溯。
- [ ] 无标签流未伪造 benchmark/人工真值、准确率或规则网格。
- [ ] 与 FHC 使用相同普通节点和 edges，只换 profile/参数；逐真实点 replay 因果对账通过。
- [ ] 满足 `benchmark_*` slot iff benchmark_reuse；产品 annotation candidate/快照/model candidate/registry/Promote/正式告警及高权限恢复逐入口直接拒绝，写入数为 0。
- [ ] 若执行审核 UX，结果明确留在 benchmark 证据域；没有静默跨 slot 导入。
- [ ] 完成自审和 Batch G8 小结。

## Batch G9：正式真实点 Connector、Shadow 与灰度（条件阶段）

**目标：** 在普通工作流和闭环得到真实证据后，把 `pv_point.predict_replay` 的 source 从确定性文件 replay 替换为正式点流 connector；计算合同仍是逐真实点，不引入固定网格或整日容器。

**准入条件：** G0–G8 全通过；业务书面确认 point 指标、误报、延迟、no-decision、Shadow 周期和回滚门槛；已有可用 `pv_point` Champion。

- [ ] G9.1 建立点路径专属 measurement、ingestion/detection cursor、prediction revision、alarm state/event、retry 和 audit；所有对象只按 `slot=pv_point` 与实体分区，不读写 day feeder/游标。
- [ ] G9.2 Connector 按源事件到达顺序或确定性排序暴露真实点；每个真实点复用 G3/G6 的普通节点执行“校验去重 → 已有行 past-only 缺值处理 → 当前点窗口 → 当前点预测”。
- [ ] G9.3 不规定固定 5 分钟微批、不生成规则时间槽、不要求整日 288 点。调度可按吞吐使用小批，但批内逐点更新状态和输出；实际 time gap 进入特征/no-decision。
- [ ] G9.4 迟到数据在允许范围内生成新 revision，超过范围只记录；禁止通过补虚拟点“追平”时间。当前点处理失败不得推进实体 detection cursor。
- [ ] G9.5 服务重启从持久化 measurement/cursor/prediction/alarm 恢复；内存 history buffer 只是缓存，可由已处理真实点重建。
- [ ] G9.6 先 Shadow：不触发正式告警，不改 `pv_day` 结论，不自动 Promote；覆盖跨日、非规则间隔、迟到、已有行缺值、重复、冲突重复、重启和异步设备。
- [ ] G9.7 达标后按站点/设备白名单灰度；默认 `alarm_policy.enabled=false`，回滚只切 `pv_point` Champion 或关告警。

历史附录中的 Causal TCN、跨日窗口和告警状态机可在本批重新对照真实数据评审；固定 5 分钟 grid、整日 288 槽和 strict-grid builder 明确不恢复。

**退出门槛：**

- [ ] Point 不读写 Day feeder、封账、游标、模型指针或结果。
- [ ] 每个通过 schema/幂等校验并被 connector 正式暴露的真实点，恰好一个 `prediction` XOR `no_decision` 及 evidence；格式非法或冲突重复显式失败且 cursor 不推进；无源外时间戳、网格行或重采样结果。
- [ ] 因果、幂等、跨日、非规则间隔、迟到、冲突重复和重启测试通过。
- [ ] Shadow 无正式副作用；灰度有权限、门禁和回滚演练。
- [ ] 前后端运行状态和 evaluation store 都来自同一个 `pv_point` workflow/execution 合同。
- [ ] 完成自审和 Batch G9 最终小结。

## Batch G10：确认箱接缝（Composer 2.5 一次一切片）

**目标：** 当前 slot 的 load 下拉能列出**全部历史+最新确认箱**和**全部历史+最新累计快照**，每一项冻结 `file_path`、都可以直接训练；confirm 先发布确认箱不自动累计。不实现模板 A、不实现告警。

**合同（切片正文即真源，勿读 fusion-design 全文）：**

- 确认箱 `LabeledDatasetVersion`：必填 `dataset_version_id`、`slot`（仅 `pv_day`|`pv_point`）、`status=curated`、相对 `file_path`、`content_sha256`。无 slot 拒绝写入。
- 累计盘点：已有 `slot_dataset_snapshot` 链；每个 `snapshot_version` 一行，ID 形如 `snap-{slot}-v{n}`。
- 画布注册表每条：`dataset_id`、`kind`（`labeled_version`|`cumulative_snapshot`）、`slot`、`ref_id`、`file_path`、`trainable=true`、`created_at`。新版本**新增行**，禁止改写旧行 `file_path`。
- 列表 API：按 `slot` 过滤；返回确认箱组 + 累计组；组内最新在前，带 `is_latest`；历史项不得省略。
- 点工作流请求 `slot=pv_point` 不得看到 `pv_day` 条目。
- confirm 不自动纳入累计、不自动 build、不自动重训。

**本批允许改的文件（超出即停，除非切片点名）：**

- `backend-service/services/slot_datasets/labeled_versions.py` — 新建确认箱存储
- `backend-service/services/slot_datasets/canvas_datasets.py` — 新建画布可训清单
- `backend-service/tests/test_g10_labeled_versions.py`
- `backend-service/tests/test_g10_canvas_datasets.py`
- `backend-service/tests/test_g10_clustering_confirm.py`
- `backend-service/api/iterative_labeling.py` — 仅 confirm / 纳入累计相关 handler
- `backend-service/services/iterative_labeling/pv_training_workspace.py`
- `backend-service/services/slot_datasets/snapshots.py` — 仅 build 成功后登记累计行
- `backend-service/api/workflows_enhanced.py` — 仅 `GET/POST /datasets*` 点名函数
- `backend-service/data/functions.json` — **仅 S2 四个孪生 ID**，禁止整表重写
- `backend-service/services/operator_backends/kmeans.py` 等 — 仅 S2 若采用别名
- `frontend-sevice/src/components/workflow-enhanced/PropertyPanelV2.tsx`
- `frontend-sevice/src/services/workflowEnhancedApi.ts`
- `frontend-sevice/src/pages/WorkflowEditorPage.tsx` — 仅读 query `dataset_id`/`slot` 填 load_csv
- `frontend-sevice/src/pages/DatasetPage.tsx` — 仅确认后跳转按钮
- `docs/specs/pv-fault-realtime-point-path-redesign/g10-handoff.md` — S5 小结

---

### G10-S0 确认箱存储（第一会话）

**目标：** 能写入/列出带 slot 的 curated 确认箱；无 slot 失败；ID 单调不复用。

**允许：** `backend-service/services/slot_datasets/labeled_versions.py`、`backend-service/tests/test_g10_labeled_versions.py`

**禁止：** 改 confirm、改前端、改 `functions.json`、改 `workflows_enhanced.py`。

**行为：**

- 存储目录：`backend-service/data/slot_datasets/{slot}/labeled_versions.json`（JSON 结构对齐同目录已有 `reviewed_annotations.json`：顶层 `{slot, versions: [...]}`）。
- 错误类型复用 `services.slot_datasets.errors.SlotDatasetError`，本切片不改 `errors.py`。
- slot **只允许** `pv_day` | `pv_point`。空 slot、`load_forecast`、`benchmark_*` 一律 `SlotDatasetError`。不要只调用 `assert_product_slot`（它会放过 `load_forecast`）。
- `allocate_dataset_version_id(slot) -> str`：如 `lds-{slot}-{yyyymmddhhmmss}-{6hex}`，永不复用。
- `publish_labeled_version(...)`：校验 slot、源文件存在、计算 `content_sha256`、`status` 仅允许 `curated`；持久化的 `file_path` 必须是相对 `backend-service/` 的相对路径。
- `list_labeled_versions(slot)`：该 slot 全部历史，最新在前。
- 跨 slot `list` 互不可见。
- 测试用 `monkeypatch` 把模块内 `_DATA_DIR` 指到 `tmp_path`，禁止写真实数据目录。

**测试：** 无 slot 抛错；`load_forecast` 抛错；pv_point 列表不含 pv_day；两次 publish 两个 ID；路径为相对路径。

**验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web python -m pytest tests/test_g10_labeled_versions.py -q
conda run -n cp_web python -m py_compile services/slot_datasets/labeled_versions.py
```

**会话提示词：**

```text
只做 G10-S0。读 docs/specs/pv-fault-realtime-point-path-redesign/tasks.md 里「G10-S0」整节并执行。
禁止 git commit。测绿后停下。
```

---

### G10-S1 画布可训清单（第二会话）

**前置：** G10-S0 测绿。

**目标：** 统一登记/列出确认箱行与累计快照行；列表含全部历史+最新。

**允许：** `backend-service/services/slot_datasets/canvas_datasets.py`、`backend-service/tests/test_g10_canvas_datasets.py`、`backend-service/api/workflows_enhanced.py` **仅新增** `GET /datasets/trainable?slot=`（handler 只调 `list_trainable_datasets`）。

**禁止：** 改 `_load_dataset_registry`、`GET /datasets`、`POST /datasets/register`、`GET /datasets/available`（那是 AutoResearch 旧清单）。新路由必须声明在 `/datasets/{dataset_id}` 通配路由之前，否则 `trainable` 会被当成 id。

**行为：**

- 独立 JSON：`backend-service/data/slot_datasets/{slot}/trainable_datasets.json`，不要写入 AutoResearch registry 文件。
- `register_trainable_dataset({dataset_id, kind, slot, ref_id, file_path, name})`：旧 `dataset_id` 若已存在且 `file_path` 不同 → `SlotDatasetError`，不得覆盖。
- `list_trainable_datasets(slot)` 返回 `{ labeled_versions: [...], cumulative_snapshots: [...] }`，每组按时间/版本降序，第一条 `is_latest=true`，历史项全部保留。
- 累计行 `dataset_id` 必须是 `snap-{slot}-v{n}` 这种稳定 ID，v2 不得改 v1 的 path。
- 测试同样 monkeypatch `_DATA_DIR`。

**测试：** 同 slot 两箱+两快照共 4 条；过滤 slot；覆盖 path 冲突。

**验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web python -m pytest tests/test_g10_canvas_datasets.py -q
conda run -n cp_web python -m py_compile services/slot_datasets/canvas_datasets.py
```

**会话提示词：**

```text
只做 G10-S1。读 tasks.md「G10-S1」整节。禁止 git commit。测绿后停下。
```

---

### G10-S2 聚类 confirm 发布确认箱 + 算法两处修复 + 四个孪生（第三会话）

**前置：** G10-S1 测绿。

**目标：** confirm 后有确认箱 + 画布 labeled_version 行；聚类不再用 ID 列、先做 z-score。

**允许：** `pv_training_workspace.py`、`api/iterative_labeling.py`（confirm handler）、`tests/test_g10_clustering_confirm.py`；`functions.json` **仅**把货架 ID `kmeans_cluster`/`dbscan_cluster`/`agglomerative_cluster`/`pca_reduce`（及若存在的 `pca_reduction`）与 backend `OPERATOR_ID` 对齐（改货架 ID 或给 backend 加别名，二选一，优先改货架指向已实现 ID）。

**行为：**

- `confirm_clustering_run` 在写 CSV 后：`publish_labeled_version` + `register_trainable_dataset(kind=labeled_version)`；响应带 `dataset_version_id`、`dataset_id`。不调用 snapshot build。
- `create_clustering_run`：特征列默认 `value`/`i_cal`（或传入 measures）；排除 `site_id`/`device_id`/`branch_id` 及一切 entity key；聚类前对特征做 z-score（0 方差列保持 0）。
- 前端 k=5 本切片不改。

**测试：** confirm 后 list 该 slot 能看到新箱；不出现累计新行；整型 branch_id 不在聚类特征里（可用最小 CSV fixture）。

**验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web python -m pytest tests/test_g10_clustering_confirm.py -q
```

**会话提示词：**

```text
只做 G10-S2。读 tasks.md「G10-S2」整节。禁止 git commit。禁止改 DatasetPage 跳转（那是 S5）。测绿后停下。
```

---

### G10-S3 纳入累计后登记全部快照版本行（第四会话）

**前置：** G10-S2 测绿。

**目标：** 显式纳入 + build 成功后，为**该版本**新增累计行；历史累计行仍在。

**允许：** `snapshots.py`（build 成功挂钩）、`iterative_labeling` 纳入累计 API 若已有则接线、`tests/test_g10_canvas_datasets.py` 或新建 `test_g10_cumulative_register.py`。

**行为：**

- 纳入累计：只把确认箱 ID 记入该 slot 清单，不改确认箱文件。
- snapshot build vN 成功 → `register_trainable_dataset` id=`snap-{slot}-v{n}`，path 为该版本 artifact 相对路径。
- 若 v1 已注册，build v2 只新增 v2 行。

**测试：** v1+v2 列表累计组长度为 2；确认箱组数量不变。

**验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web python -m pytest tests/test_g10_canvas_datasets.py tests/test_g10_cumulative_register.py -q
```

若未新建 `test_g10_cumulative_register.py`，则把用例写进 `test_g10_canvas_datasets.py` 并只跑该文件。

**会话提示词：**

```text
只做 G10-S3。读 tasks.md「G10-S3」整节。禁止 git commit。禁止改前端下拉。测绿后停下。
```

---

### G10-S4 load 下拉（第五会话，前端+列表 API）

**前置：** G10-S3 测绿。

**目标：** 编辑器 `load_csv` 能按当前 slot 分组选择全部确认箱与全部累计版本。

**允许：** `PropertyPanelV2.tsx`、`workflowEnhancedApi.ts`、必要时 `WorkflowEditorPage.tsx` 把执行 context 的 slot 传给属性面板；`GET` 可训列表已在 S1。

**行为：**

- 下拉两组：`确认箱`、`累计训练`；组内最新在上，标「最新」。
- 选中写入该行 `file_path` 与 `dataset_id`；执行仍用相对路径。
- 无 slot 时下拉为空或提示先选 slot，不得把另一槽位数据列出来。

**验证：** 前端 `npx tsc --noEmit` 或项目现有 typecheck；不跑 `npm run build` 全量除非已很快。

**会话提示词：**

```text
只做 G10-S4。读 tasks.md「G10-S4」整节。禁止 git commit。禁止改聚类算法。做完停下。
```

---

### G10-S5 跳转按钮 + 提案门 + 小结（第六会话）

**前置：** G10-S4 完成。

**目标：** DatasetPage 确认后可跳进对应训练模板并带 `dataset_id`；未 confirm 文件不能当可训清单项。

**允许：** `DatasetPage.tsx`、`WorkflowEditorPage.tsx`（读 `?dataset_id=&slot=` 填 load_csv）、`tests/test_g10_clustering_confirm.py` 补提案门、`g10-handoff.md`。

**行为：**

- 点路径确认默认 `workflow-pv-point-train-eval-v1`；天路径 `workflow-pv-day-train-eval-v1`。slot 必须与确认箱一致。
- 提案门：clustering run 未 confirm 的 csv **不得** `register_trainable_dataset`。
- 小结写：改了哪些文件、测了什么、未测浏览器。

**会话提示词：**

```text
只做 G10-S5。读 tasks.md「G10-S5」整节。禁止 git commit。写完 g10-handoff.md 停下，不要开始 G11。
```

**G10 整批退出：** 六切片都绿；下拉合同（历史+最新、两类都可训、slot 隔离）有测试或 handoff 说明；不碰现网 `pv_fault` Champion。

---

## G11. 打标工作流与诊断只吃确认数据

> 见 `fusion-design.md` 第 4、7 节。

- [ ] G11.1 `emit_label_proposal` / `cluster_profile` 算子 + 模板 A（slot 写入提案）。
- [ ] G11.2 `load_labeled_dataset` 按确认箱或快照版本加载并带出 `dataset_contract`。
- [ ] G11.3 天路径 `emit_prediction_batch`；点路径候选投影进入复核队列。
- [ ] G11.4 旧 `create_clustering_run` REST 降为快捷模式，默认仍走确认箱发布。

**退出门槛：** 无标签 → 提案 → 确认箱 → 同 slot 训练，无需手抄路径。

## G12. `pv_point` 日内滚动告警

> 见 `fusion-design.md` 第 5、7 节。禁止 TSC / 288 槽。

- [x] G12.1 告警状态机消费 `replay_activity` 的 point outcome（出现 / 去重 / 连续正常消警）。
- [x] G12.2 喂数源可从文件扩展为「实体未处理真实点」；activity 与冻结 graph 不变。
- [x] G12.3 正式 connector 仍可后置；本批可用文件回放演示告警。

**退出门槛：** 回放上可演示告警生命周期；改未来点不影响当前点窗口；不读写 day feeder。

## G13. 平台卫生与遗产

- [x] G13.1 货架 `implementation_status`、连线类型校验（可分切片）。
- [x] G13.2 生产 simple 切换守卫与相关写接口鉴权（需显式授权实施）。
- [x] G13.3 文档与 UI 标明 `pv_fault` / TSC 为 legacy 只读（`LegacyReadOnlyBanner` + 槽位下拉 legacy 标注）。

## A11. 总体验收矩阵

| 成功标准 | 最早批次 | 最终证据 |
|---|---:|---|
| 确认箱带 slot，训练不混天/点 | G10 | 跨 slot 加载失败测试 |
| 提案不能训练 | G10 | 未 confirm 数据被 train 拒绝 |
| 复核走确认箱→累计→快照版本 | G10 | 无可变累计 CSV 作为训练输入 |
| 打标工作流产出提案 | G11 | 模板 A execution + proposal 工件 |
| 点日内告警走 replay 而非 TSC | G12 | 状态机单测 + 回放演示；无 288 槽 |
| 单 slot 与槽位配置链闭合 | G0 / P0a | UI 请求、template/config 校验、execution context 和摘要一致；新合同无 `scenario_key`；现网 `pv_fault` 未改写 |
| 工作流产物是唯一业务来源 | G3 / P0a | model/evaluation/prediction 可追溯 succeeded source execution；Orchestrator 不再旁路评分 |
| 现有 PV profile 可接入 | G1 / P0a | PV 冻结快照 profile 与 preflight 报告；NASA/FHC 下载非退出 |
| 算子尽量可换数据集 | G2 / P0a | 优先非光伏最小 CSV fixture 走同一 10 个算子；例外记录即可，不挡 P0a |
| 普通点核心无 PV 分支且已重训 | G2 / P0a | 依赖检查、合同测试、Causal TCN 复用证据；旧 grid `model.pt` 未当 Champion |
| 纯手工完全展开 graph | G2/G3 / P0a | 12 个普通节点状态、P0 10 个可执行；subgraph/recipe/隐藏计算节点为 0 |
| 回放循环不进 graph | G3 / P0a | `replay_activity` 多次调用同一冻结 graph；admission/cursor 不是 `operator_id` |
| 真实点逐点因果链 | G2/G3 / P0a | 非规则间隔、一点一结果、未来扰动、no-decision 与无虚拟时间戳测试 |
| P0a 天/点独立产品链 | G3 | 四个不可变模板版本、两条生命周期链记录、最小 UI、跨 slot 阻断测试 |
| 槽位内治理底座 | G4 / P0b | 单 slot 分区、source execution 门禁、不可变复验和 Promote 审计；G4 切写 |
| P0b 天/点双闭环累计 | G5 | 两条 candidate→review→snapshot+1→retrain→verify→`set_as_production=true` Promote→repredict/replay 证据；现网 `pv_fault` Champion 未变 |
| 四个闭环动作显式分离 | G5/G7 | 快照构建、固定版本重训、复验、Promote 无自动串行与半写状态 |
| 同拓扑跨数据集 | G6 | NASA/FHC 普通 operator/edge 对比报告，子图和产品副作用写入均为 0 |
| 按 slot 的前端打磨 | G7 | 深链、全状态、工作流来源跳转、build/lint 和截图矩阵 |
| PVDAQ 无标签复用 | G8 | `benchmark_pvdaq_<system>` 逐真实点证据与产品治理零写入 |
| 正式真实点可灰度 | G9 | 无网格 connector、Shadow、跨日/迟到/重启与回滚报告 |

## A12. 现在可以开工（G10，一次一个切片）

G0–G8 已完成，**不要重开**。现在只开 **G10**，而且一次只开一个切片。用 Composer 2.5：新建对话 → 只粘贴该切片「会话提示词」→ 等它停下 → 你看测试和 diff → 再开下一会话。不要一次把 G10-S0～S5 全贴进去。

六个会话顺序：

| 会话 | 切片 | 做什么 | 你怎么知道它做完了 |
|---|---|---|---|
| 1 | G10-S0 | 确认箱存储 + ID | `pytest tests/test_g10_labeled_versions.py` 绿 |
| 2 | G10-S1 | 画布可训清单 + `GET /datasets/trainable` | `pytest tests/test_g10_canvas_datasets.py` 绿；旧 `GET /datasets` 行为未改 |
| 3 | G10-S2 | confirm 发布确认箱 + z-score + 四个孪生 | `pytest tests/test_g10_clustering_confirm.py` 绿 |
| 4 | G10-S3 | 累计快照 build 后登记全部版本行 | v1+v2 累计组长度=2 |
| 5 | G10-S4 | `load_csv` 下拉（历史+最新，分组） | 类型检查过；无 slot 不串槽 |
| 6 | G10-S5 | 跳转训练 + 提案门 + `g10-handoff.md` | 出现小结，不要开始 G11 |

第一会话直接复制：

```text
只做 G10-S0。读 docs/specs/pv-fault-realtime-point-path-redesign/tasks.md 里「G10-S0」整节并执行。
禁止 git commit。测绿后停下。
```

G10 不做：模板 A、告警状态机、写接口鉴权、改现网 `pv_fault` Champion、改 AutoResearch `GET /datasets`。G11 等 G10 六切片都绿且 `g10-handoff.md` 允许后再开。

---

## 附录 H：原光伏专用实时点实施计划（历史参考，禁止直接执行）

> 从本标题到文件结尾保留原 Batch 0–7，便于追溯已有 POC、标签拆分、TCN、在线水位和 UI 想法。其固定 20 learning + 10 locked holdout、先物理迁表、专用 `pv_fault_realtime` 产品入口和先建在线基础设施的顺序已被 G0–G9 取代。
>
> **非规范解析规则：** 附录中的复选框、命令、验收门槛、“禁止事项”和“下一次实施”均为历史原文，不得更新当前任务状态或直接执行；任何可复用内容必须先迁入上方 G0–G9，并经当前 requirements/design 重新验收。

### H.0 原结论与执行顺序

本计划不是直接把 4457 个设备日的天标签广播成点标签。正确顺序固定为：

1. **先冻结危险写入并明确来源合同**，候选段不能冒充点真值。
2. **先完成天/点标签物理隔离**，生产读写不再依赖旧混合 `label_ops`。
3. **再治理自动定位候选并制作人工金标**，建立 `learning` 与 `locked_holdout` 两个互斥用途。
4. **再重建可信不可变数据集**，锁定训练、验证和验收边界。
5. **再做每 5 分钟稠密评估和因果告警回放**，消除当前 30 分钟抽样评估偏差。
6. **再做多分类模型对照**，保留动态新增故障标签能力；二分类只作为告警分数或消融实验。
7. **再接候选段→人工复核→累计重训→Challenger→验收→晋升闭环**。
8. **指标达标后才建设实时点流、Shadow 和灰度告警**。

任何批次未通过验收和自审，不得开始下一批。每批只提交该批必要的最小改动，不做无关重构，不清理现有脏工作区和历史产物。

### H.1. 已核实基线（执行前不可误读）

- 全量天数据共 4457 个设备日；天标签只说明“这一天是什么类别”，不天然说明故障从几点开始、几点结束。
- `backend-service/data/auto_located_segments_full/report-20260821065229.json` — 自动定位全量 dry-run 报告：472 个设备日定位成功，共 645 个候选段，其中 233 段为 high、412 段为 medium；high 实际覆盖 194 个设备日。它们仍是**候选**，不是人工真值。
- `backend-service/data/realtime_point_poc/snapshots/point-poc-20260821044728-684bf7f6/` — 当前实时点 POC 不可变快照：正常监督点 78,507，其中历史 `cluster + label_id=0`（历史聚类来源、标签 ID 0 表示正常）为 78,224，`point_rest_normal`（K4 伴生框外正常来源）为 283；故障监督点 10,826。因此“正常只有 283 点”不成立，真正短缺的是人工真值、稀有类和可信边界。
- `backend-service/data/models/realtime_point_poc/rtpoint-tcn-last_point-20260821052713-54a68272/metadata.json` — 当前 Causal TCN 冠军 POC 工件：`context_length` — 上下文槽数为 72、感受野 61 点、8 类、仅末点 loss；其测试评估来自 `stride` — 评估滑动步长为 6，即每 30 分钟采样一次，不等于 5 分钟实时表现。
- 当前工件明确 `promotion_eligible` — 是否允许晋升为生产候选为 `false`、`alarm_policy.enabled` — 是否启用正式告警为 `false`；在完成稠密评估、人工验收和 Shadow 前不得改为可晋升或启用正式告警。
- 自动定位失败的故障日不得整天广播为故障点；这会污染边界、制造全天报警，并违反 `pure_day_label_not_allowed_for_seq` — 纯天标签不得进入序列点监督的不变量。

### H.2. 统一字段与来源合同

### 2.1 标签用途字段

- `label_id` — 标签 ID；0 表示正常，其他 ID 来自动态标签注册表，新增故障类别不得要求重建历史 ID。
- `source` — 标签来源；说明标签如何产生，不能代替审核状态。
- `annotation_role` — 标注用途；只允许 `learning`（可进入训练/调参）或 `locked_holdout`（锁定人工验收集，永不进入训练/调参）。
- `source_candidate_id` — 来源候选 ID；人工批准自动候选后写入点标签操作，便于从真值追溯原候选。
- `review_status` — 候选审核状态；候选层取 `pending`、`approved`、`rejected`，不得写进已生效点标签来混淆真值。
- `confidence` — 候选置信度；只用于排序和抽审，不自动等于真值置信度。
- `label_space_version` — 标签空间版本；保证训练工件、预测和后续新增标签可追溯。

### 2.2 天路径允许来源

| `source` — 来源 | 中文语义 | 是否进入点路径 |
|---|---|---|
| `human_day` | 人工对完整设备日作出的天级裁决 | 否 |
| `day_label` | 现有天路径业务标签 | 否 |
| `day_import` | 历史天标签迁移后的规范来源 | 否 |
| `parquet_day_label` | 历史兼容别名；迁移时映射为 `day_import`，新写入禁用 | 否 |

### 2.3 点路径允许来源

| `source` — 来源 | 中文语义 | 准入规则 |
|---|---|---|
| `human_range` | 人工框选的精确故障/正常区间 | 可直接进入人工真值；需记录标注用途 |
| `point_rest_normal` | K4 在人工框选外生成的伴生正常点 | 只属于点路径；随父操作撤销 |
| `peer_residual` | 同期设备残差算法提出、并经人工或独立规则批准的点段 | 未批准时只能留在候选层 |
| `pseudo_point` | 其他点级弱标签 | 必须经过独立准入，按来源单独评估 |
| `cluster` / `cluster_point` | 历史兼容来源 | 只读兼容并迁移映射；新写入禁用 |

`peer_residual` 表示已准入的算法辅助点标签；原始算法输出存候选记录，通过 `source_candidate_id` 追溯。这样候选状态与生效真值不共用一张表，也不再用含义模糊的 `cluster` 作为新来源。

### H.3. 每批统一完成协议

每个批次必须严格按以下顺序执行：

1. 实施本批任务，不夹带下一批功能。
2. 运行本批定向测试、迁移 dry-run、对账或构建；有错误立即修复。
3. 重新读取本批所有修改文件，不凭记忆自审。
4. 对照本批字段链检查默认值、旧请求兼容、最终消费分支、空态/错误态/禁用态。
5. 检查未使用 import、死代码、绝对路径、跨路径读写和历史数据副作用。
6. 填写本批“交付小结”，明确已验证、未验证、风险和下一批准入结论。
7. 只有“验收通过 + 自审通过”后，才把本批总任务勾为 `[x]` 并进入下一批。

### 统一交付小结模板

```markdown
#### Batch N 交付小结

- 结论：通过 / 不通过；是否允许进入 Batch N+1。
- 改动文件：
  - `relative/path` — 该文件在项目中的职责；本次具体改动。
- 关键字段链：UI → HTTP → API Handler → 执行上下文/服务 → 存储/模型 → 响应 → UI。
- 默认与兼容：不传字段时的行为；旧请求/旧数据如何处理；最终改变行为的条件分支。
- 已验证：测试、类型检查、构建、迁移 dry-run、对账、截图或回放及结果。
- 未验证：本批没有覆盖的真实数据库、浏览器、长时间运行或生产数据场景。
- 自审结果：重新读取文件、需求逐项、无死代码、无跨路径污染、无绝对路径、无意外路由/API 变化。
- 风险与回滚：剩余风险、回滚开关/只读旧表/不可变快照。
- 下一批入口：满足的前置条件和明确暂缓事项。
```

### 3.1 前端现状与固定信息架构

现有前端不需要推倒重做，以下能力直接复用：

- `frontend-sevice/src/App.tsx` — 前端路由入口；已有 `/iterative-labeling/review`（人工审核）、`/accuracy-operations`（精度运营）和 `/algorithm-deployment`（算法部署）三个承载入口。
- `frontend-sevice/src/pages/IterativeLabelingReviewPage.tsx` — 人工审核与打标页；已有设备日审核、ECharts 曲线框选、已有/新增标签、撤销、断点恢复，以及逐点预测和分段 overlay。
- `frontend-sevice/src/services/iterativeLabelingApi.ts` — 迭代标注 API 客户端与部分 TypeScript 合同；现有自由窗提交尚未携带 `annotation_role` 和 `source_candidate_id`。
- `frontend-sevice/src/pages/AccuracyOperationsPage.tsx` — 精度运营聚合页；`pv_fault` 分支已有闭环总览、建模路径、双路径 Ledger/Shadow 和预测证据。
- `frontend-sevice/src/pages/AlgorithmDeploymentPage.tsx` — 算法部署与模型治理页；已有后台重训进度、同路径历史、Registry Champion/Challenger 语义和标签体系展示。
- `frontend-sevice/src/pages/PvDualPathConsole.tsx` — 双路径状态与治理组件；可复用其独立 loading/empty/error 状态和门禁展示方式，但实时点路径不能复用天/点日滚的模型指针。
- `frontend-sevice/src/components/pv-fault/PvFaultWorkspaceShell.tsx` — 光伏工作台壳；负责注入 Ant Design 主题和共享样式。
- `frontend-sevice/src/theme/pvFaultTheme.ts` 与 `frontend-sevice/src/styles/pvFaultWorkspace.css` — 光伏黑/橙/白主题和工作台状态样式；新增页面沿用现有令牌，不另建视觉体系。

固定页面分工：

1. **标注入口不变。** `/iterative-labeling/review` 继续负责候选段审核、曲线框选、标签新增和撤销；用 `review_kind` — 审核类型区分现有设备日审核与 `point_candidate` — 实时点候选审核。
2. **精度运营承载实时点研究工作台。** `/accuracy-operations?slot=pv_fault&view=realtime-point` 中，`slot` — 产品槽位/业务线分区键，此处固定为 `pv_fault`；`view` — 光伏运营子视图，新增 `realtime-point` 视图；内部用紧凑 Tabs 分为“标签与数据”“5分钟评估”“模型实验”“实时运行”，避免把更多卡片直接堆到现有长页面。
3. **算法部署只负责模型治理。** `/algorithm-deployment?slot=pv_fault&tab=realtime-point` 中，`tab` — 部署子页，新增实时点 Champion、Challenger、重训水位、Promote 和审计，不承载数据标注或评估详情。
4. **Batch 7 才新增设备详情路由。** `/accuracy-operations/pv-realtime/devices/:deviceKey` — 实时点设备详情页，其中 `deviceKey` — 设备三元组的稳定 URL 编码；仅从实时运行工作台进入，不新增一级侧栏菜单。

前端新增合同集中在：

- `frontend-sevice/src/types/realtimePoint.ts` — 实时点路径 TypeScript 真源；定义来源、标注角色、候选、快照、稠密评估、模型、运行水位、预测和告警类型。
- `frontend-sevice/src/services/realtimePointApi.ts` — 实时点专属 API 客户端；严格区分只读 GET 与候选审核、构建、重训、Promote、retry/cancel 等有副作用写操作。
- `frontend-sevice/src/pages/accuracy-operations/PvRealtimePointWorkbench.tsx` — 精度运营内的实时点工作台编排组件；只负责子视图、共享筛选和刷新，不把全部业务写在一个超大文件中。
- `frontend-sevice/src/pages/deployment/PvRealtimePointGovernancePanel.tsx` — 实时点模型治理面板；展示独立 Champion/Challenger 和人工晋升门禁。

### 3.2 前端统一交付约束

每个涉及前端的 Batch 还必须满足：

- 使用现有 `PvFaultWorkspaceShell`、Ant Design 和 ECharts；保留黑/橙/白品牌令牌，但新增组件采用中性表面、分隔线、表格和明确层级，不复制装饰性渐变、厚侧边强调或宽阴影，也不引入第二套主题、图标或表单组件。
- 页面以表格、分栏、Tabs 和详情抽屉建立信息层级，禁止新增层层嵌套卡片墙；主操作始终靠近当前对象和门禁结果。
- 状态切换动效控制在 150–250ms，只用于反馈和展开；必须支持 `prefers-reduced-motion`，不得用入场动画阻塞内容可见性。
- 所有读取区域具备 skeleton/loading、empty、error、retry；所有写操作具备 disabled、submitting、成功回执、失败原因、重复提交保护和权限不足状态。
- 颜色不作为唯一状态信号；状态同时显示中文文本/图标。危险写操作使用明确确认文案，不把普通 Modal 当所有详情的默认容器。
- 桌面 1440px 和常见笔记本宽度保证表格可扫读；窄屏允许横向表格或切换为只读摘要，复杂框选/Promote 不强求移动端完成。
- URL 中保留 `slot`、`view`、`tab`、筛选和当前对象 ID，刷新后可恢复上下文；未知或无权限 ID 显示可诊断空态，不跳回错误默认页。
- 前端只传项目相对路径；复制路径时明确“相对项目根目录”，不展示或持久化本机绝对路径。
- 每个前端 Batch 至少执行：

```powershell
Set-Location frontend-sevice
npm run build
npm run lint
```

若 `npm run lint` 存在既有告警，交付小结必须区分既有与本次新增；本次新增 error 必须为 0。下文各 Batch 的“定向验证”代码块只列该批增量命令；凡修改前端的 Batch，仍必须叠加执行本节的 `npm run build` 与 `npm run lint`，不能因代码块未重复列出而省略。还需手工核对默认、loading、empty、error、disabled、成功、失败七类状态，并记录未完成的浏览器截图或真实接口联调。

---

### H.Batch 0：只读安全预检、来源合同与可复现基线

**目标：** 在任何代码改动、批量落标或迁表前，先以只读方式确认危险入口、来源合同和可复现基线。Batch 0 不修改生产代码、数据库或生效标签；首个业务实现批次仍是 Batch 1 的物理隔离。

**前置条件：** 只读检查现有数据和代码；不得执行自动定位脚本的 `--write`，不得执行迁移写模式。

- [ ] 0.1 审计来源白名单和路径分类现状
  - 检查 `backend-service/services/iterative_labeling/point_label_service.py` — `PointLabelService` 是点标签写入总入口；列出当前对白名单外来源以及 `human_day`、`day_label`、`day_import`、`parquet_day_label` 的实际处理结果。
  - 检查 `backend-service/services/iterative_labeling/label_path_isolation.py` — `classify_op_path()` 输入历史操作并判断业务路径；输出当前可判定为 `day`、`point`、`ambiguous` 的数量和误分类风险。
  - 把“来源缺失、粒度冲突、仅有全天范围时必须拒绝猜测”冻结为 Batch 1 的实现验收项。

- [ ] 0.2 审计自动定位写入风险
  - 检查 `backend-service/scripts/auto_locate_fault_segments.py` — 全量自动定位 dry-run 和候选导出脚本；确认默认模式、`--write` 分支和当前写入来源。
  - 检查 `backend-service/services/iterative_labeling/peer_residual_locator.py` — `PeerResidualLocator` 输入全天测量和天标签并输出候选段；列出把候选误当生效 `cluster` 真值的全部调用点。
  - 冻结候选合同：`source_candidate_id`、设备三元组、`t_start` — 候选起始事件时间、`t_end` — 候选结束事件时间、`proposed_label_id` — 建议标签、`confidence`、`review_status` 和算法版本。

- [ ] 0.3 固化执行前基线报告
  - 记录天/点操作数、生效标签数、按来源/类别/设备日分布、K4 父子关系、歧义操作清单和当前 POC 快照摘要。
  - 报告写到部署配置决定的相对数据目录，包含输入摘要和生成时间；不得覆盖既有报告。

- [ ] 0.4 完成前端只读盘点和交互基线
  - 记录 `/iterative-labeling`、`/iterative-labeling/review`、`/accuracy-operations?slot=pv_fault`、`/algorithm-deployment?slot=pv_fault` 当前入口、页面截图和字段缺口。
  - 核对 `IterativeLabelingReviewPage` 当前自由窗请求没有 `annotation_role`、`source_candidate_id` 和候选审核状态；核对点审核页面是否仍可能展示或提交 `human_day`。
  - 输出 Batch 1–7 的页面流转图和前端字段映射；本批不修改 TS/TSX/CSS，不创建假数据页面。

**前端验收：** 四个现有入口均可访问或有明确后端不可用提示；页面现状、缺失状态和待新增 API 字段有截图/清单；`git diff` 证明未修改前端源码。

**关键字段链：** 自动定位脚本 → 候选输出 → 当前潜在写入入口；本批只审计链路并形成改动清单，不得写入 `point_label_ops`、`point_labels` 或任何生产表。

**定向验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_label_path_isolation.py tests/test_point_label_service.py -q
conda run -n cp_web python scripts/migrate_label_path_isolation.py --dry-run
```

**验收门槛：**

- [ ] 天/点来源矩阵、历史兼容别名和歧义处理规则已书面冻结。
- [ ] 自动定位所有候选写入入口、默认行为和危险 `--write` 分支已列全。
- [ ] 失败故障日的“全天故障点”风险路径已定位，未执行写入。
- [ ] 基线报告可重复生成且不包含绝对路径。
- [ ] `git diff` 证明本批未修改生产代码；dry-run 日志证明未执行生效数据写入。
- [ ] 完成统一自审和 Batch 0 交付小结。

**禁止事项：** 不改生产代码；不批量写 472 天候选；不处理 577 个正常天的全天点标签；不迁移或删除旧表；不重训模型。

---

### H.Batch 1：天标签与点标签彻底物理隔离

**目标：** 生产天路径只读写 `day_label_ops/day_labels`，生产点路径只读写 `point_label_ops/point_labels`；旧混合 `label_ops` 退出业务读写，只保留只读回滚窗口。

**前置条件：** Batch 0 验收通过；基线报告已冻结；数据库有可恢复备份或迁移回滚方案。

- [ ] 1.0 先落实来源安全闸门和候选只读保护
  - 修改 `backend-service/services/iterative_labeling/point_label_service.py` — 点标签写入总入口；拒绝 `human_day`、`day_label`、`day_import`、`parquet_day_label` 进入点路径。
  - 修改 `backend-service/services/iterative_labeling/label_path_isolation.py` — 历史操作路径分类器；补齐规范来源、兼容别名和 `ambiguous` 拒绝结果，来源缺失或冲突时不得猜测。
  - 修改 `backend-service/scripts/auto_locate_fault_segments.py` — 自动定位候选导出脚本；默认保持只读，未经审核批准不得写 `point_label_ops`。
  - 修改 `backend-service/services/iterative_labeling/peer_residual_locator.py` — 同期残差候选生成器；输出候选语义，不再默认声明为生效 `cluster` 真值。
  - 删除或阻断自动定位失败后把故障日全天广播为点标签的任何降级分支。

- [ ] 1.1 完成 ORM、约束和幂等迁移
  - 修改 `backend-service/services/db/models/pv_fault.py` — 光伏故障 ORM 真源；确认 `DayLabelOp`、`DayLabel`、`PointLabelOp`、`PointLabel` 的主键、来源约束、父子操作和索引完整。
  - 修改 `backend-service/scripts/migrate_label_path_isolation.py` — 标签拆表迁移、回填、对账和回滚脚本；重复执行不得产生重复记录。
  - 歧义历史操作只写失败明细，不自动分类；迁移不删除旧 `label_ops`。

- [ ] 1.2 切换点路径直接读写
  - 修改 `backend-service/services/db/repositories/point_label.py` — 点标签仓储；`insert_op()` 直接写 `point_label_ops`，`query_active_ops()` 和 `query_op_by_id()` 直接读 `point_label_ops`，不再先写或主读旧 `LabelOp`。
  - 修改 `backend-service/services/iterative_labeling/point_label_service.py` — 保持 `human_range → point_rest_normal → point_labels` 的 K4 父子撤销和物化链路。
  - 对旧 `cluster` / `cluster_point` 只做兼容读取和迁移映射，新写入统一使用 `peer_residual`。

- [ ] 1.3 切换天路径直接读写
  - 找出全部天级裁决调用方，统一通过天标签服务写 `day_label_ops` 并物化 `day_labels`；不得调用 `PointLabelService` 写 `human_day`。
  - 天路径训练、预测审核和累计训练只读 `day_labels`；点标签表中的任何记录都不能改变天路径生效真值。

- [ ] 1.4 完成影子双读对账并切断旧表
  - 使用 `compare_path_ledgers()` — 输入旧混合账本与新天/点账本，输出数量、来源、边界、生效标签和 K4 父子关系差异报告。
  - 先对账，再切生产读；切换后连续验证一轮天级裁决、一轮点区间裁决、撤销和重建物化表。
  - 旧 `label_ops` 设为业务只读；保留显式回滚开关和期限，不立即物理删除。

- [ ] 1.5 建立前端标签路径合同
  - 新建 `frontend-sevice/src/types/realtimePoint.ts` — 实时点前端类型真源；定义 `PointLabelSource` — 点标签来源联合类型、`DayLabelSource` — 天标签来源联合类型、`AnnotationRole` — 标注用途和后端可诊断拒绝结果。
  - 修改 `frontend-sevice/src/services/iterativeLabelingApi.ts` — 审核与自由窗 API 客户端；点路径请求不再接受 `human_day/day_label/day_import`，响应明确返回 `path` — 生效路径、`source` — 生效来源和 `op_id` — 操作 ID。
  - 兼容旧响应时只允许展示“历史来源”，不得把旧 `cluster` 映射成可新建选项。

- [ ] 1.6 在审核页显式隔离天/点语义
  - 修改 `frontend-sevice/src/pages/IterativeLabelingReviewPage.tsx` — 现有审核和曲线框选页；当 `prediction_granularity` — 预测粒度为 `point` 时显示“实时点标签”上下文标识，只提供点来源和区间操作，不展示整日 `human_day` 动作。
  - 当后端返回来源冲突、歧义历史记录或旧表只读时，保留当前表单内容并显示具体原因，不自动改成其他来源重试。
  - 撤销后同时刷新父操作、`point_rest_normal` 伴生操作和曲线 overlay；天标签区域不因点操作发生视觉变化。

**前端验收：** 点审核页面无法构造 `human_day` 请求；天审核流程仍可使用 `human_day`；来源冲突显示 error 且表单可恢复；旧 `cluster` 仅作为历史只读标签；`npm run build` 与 `npm run lint` 无本次新增 error。

**关键字段链：**

```text
天级：UI 整日裁决 → HTTP human_day → API Handler → 天标签服务 → day_label_ops → day_labels → 天路径训练/审核
点级：UI 区间框选 → HTTP human_range → PointLabelService → point_label_ops
     → point_rest_normal 伴生操作 → point_labels → 点路径数据集
```

默认行为：请求未明确粒度或来源时拒绝，不用时间范围猜路径；旧数据通过迁移兼容，旧业务读路径不得静默回退 `label_ops`。

**定向验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_label_path_isolation.py tests/db/test_point_label_repository.py tests/test_point_label_service.py tests/test_label_materializer.py -q
conda run -n cp_web python scripts/migrate_label_path_isolation.py --dry-run
conda run -n cp_web python -m py_compile services/db/models/pv_fault.py services/db/repositories/point_label.py services/iterative_labeling/point_label_service.py services/iterative_labeling/label_path_isolation.py services/iterative_labeling/peer_residual_locator.py scripts/auto_locate_fault_segments.py scripts/migrate_label_path_isolation.py
```

**验收门槛：**

- [ ] `human_day/day_label/day_import` 只存在于天路径新表。
- [ ] `human_range/point_rest_normal/peer_residual/pseudo_point` 只存在于点路径新表。
- [ ] 自动定位默认只产候选，未经审核不能修改生效标签；失败故障日不存在全天广播降级。
- [ ] 天、点生产查询不再读取旧 `label_ops`。
- [ ] K4 父操作撤销会同步撤销伴生正常，且不影响 `day_labels`。
- [ ] 迁移前后可判断记录的生效结果一致；歧义记录全部有失败明细。
- [ ] 回滚只切读开关，不删除或覆盖新旧数据。
- [ ] 完成统一自审和 Batch 1 交付小结。

**禁止事项：** 对账不通过不得切读；不得在本批审核 472 天候选；不得重建训练快照或修改模型。

---

### H.Batch 2：自动候选治理与人工金标

**目标：** 把自动定位结果变成可审核候选；制作 20 个 `learning` 设备日和 10 个 `locked_holdout` 设备日的人工点级金标，并保持动态新增故障标签能力。

**前置条件：** Batch 1 通过，点标签唯一真源已切到新表；审核 UI 的读取不会再混入天标签。

- [ ] 2.1 建立独立候选队列
  - 候选登记存什么：算法提出的设备、区间、建议类别、置信度、算法版本和审核状态。
  - 为什么单独存：候选不是训练真值，必须与 `point_label_ops/point_labels` 隔离。
  - 分区维度：设备三元组 + 事件时间范围 + 算法版本；重复运行按稳定候选指纹去重。
  - 路径/介质：由部署配置决定，持久化相对路径或数据库表；不得写死本机目录。

- [ ] 2.2 扩展区间候选审核闭环
  - 修改 `frontend-sevice/src/pages/IterativeLabelingListPage.tsx` — 迭代标注入口与会话列表；增加“实时点候选”队列入口、待审/已审筛选、high/medium 置信等级、类别和设备筛选，不新增一级导航。
  - 修改 `frontend-sevice/src/pages/IterativeLabelingReviewPage.tsx` — 迭代标注审核页；在 `review_kind=point_candidate` 时采用“候选队列 + 主曲线 + 决策区”的桌面布局，展示候选区间、置信度、算法版本、原始曲线、相邻上下文、已有点标签和模型分段 overlay。
  - 复用现有 ECharts 框选、已有/新增标签和撤销能力；支持批准、修边界、改类别、拒绝、撤销，并显示当前候选在队列中的位置。
  - 审核提交必须携带 `source_candidate_id`、最终 `label_id`、`t_start`、`t_end`、`annotation_role` 和审核人；后端批准后才调用 `PointLabelService`。
  - `annotation_role` 默认 `learning`；选择 `locked_holdout` 时显示“永不进入训练/调参”的明确说明并要求二次确认，自动批准和弱标签不得选择它。
  - 提交中锁定当前候选的重复操作；成功后只推进到下一条，失败保留曲线缩放、框选范围、标签和用途。

- [ ] 2.3 分层审核 472 个设备日候选
  - high 233 段先按类别、站点、持续时间分层抽审，不因 high 自动全量准入。
  - medium 412 段进入人工队列，优先覆盖稀有类、边界模糊类和模型高误报设备。
  - 记录批准率、边界修正率、类别修正率和拒绝原因；用结果反校自动定位阈值。

- [ ] 2.4 制作 30 个设备日人工金标
  - 20 个设备日标为 `learning`，用于训练和误差分析。
  - 10 个设备日标为 `locked_holdout`，按设备、日期、类别尽可能隔离；永不进入训练、阈值校准、早停或模型选择。
  - 30 个设备日应包含正常区间、故障起止边界、跨日/缺测样本和当前主要故障类；未覆盖稀有类必须在报告中明确列出，不伪造覆盖。

- [ ] 2.5 条件性处理正常天和弱标签
  - 577 个 `label_id=0` 天只有在业务语义确认“全天逐点正常”且抽检通过后，才能以独立弱来源进入 `learning`；不得伪装成 `cluster` 或人工真值。
  - 自动定位失败的故障日继续保持无点标签，不允许全天广播。

- [ ] 2.6 补齐候选与审核前端合同
  - 扩展 `frontend-sevice/src/types/realtimePoint.ts` — 增加 `PointCandidate` — 点候选记录、`PointCandidatePage` — 候选分页、`PointReviewDecision` — 人工审核决定和 `PointReviewProgress` — 会话进度类型。
  - 扩展 `frontend-sevice/src/services/realtimePointApi.ts` — 增加候选分页、创建/恢复审核会话、批准/修正/拒绝/撤销方法；写方法显式携带幂等键和 `annotation_role`。
  - 候选空态说明“当前筛选无候选”并允许清除筛选；加载失败保留筛选条件；无权限时禁用写操作但允许查看候选证据。

**前端验收：** 可从候选列表进入指定候选并刷新恢复；框选修边界、新增标签、learning、locked_holdout、拒绝和撤销均有成功/失败反馈；颜色之外有文本状态；1440px 与常见笔记本宽度下队列、曲线和决策区可用，窄屏降级为只读摘要和逐步操作。

**关键字段链：** 候选队列 → 审核页 → 审核 HTTP body → API Handler → 候选状态事务 + `PointLabelService.submit_op()` → `point_label_ops/point_labels` → 审核响应和下一条候选。批准写标签与更新候选状态必须原子或可重放，避免“候选已批准但标签未落库”。

**定向验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_point_label_service.py tests/test_point_label_concurrency.py tests/test_iterative_labeling_review_api.py -q
Set-Location ..\frontend-sevice
npm run build
```

如果计划中的 API 测试文件尚不存在，本批必须先创建对应定向测试，再运行；不能用“无此测试”当作通过。

**验收门槛：**

- [ ] 候选不经批准无法出现在生效点标签中。
- [ ] 20 个 learning 与 10 个 locked_holdout 有不可变清单和摘要。
- [ ] 任意训练查询均排除 locked_holdout。
- [ ] 新增标签后旧 `label_id` 映射不变，标签空间版本递增。
- [ ] 失败故障日无全天点标签；正常天弱标签有独立来源和抽检报告。
- [ ] 前端具备 loading、empty、error、disabled 和重复提交保护。
- [ ] 完成统一自审和 Batch 2 交付小结。

**禁止事项：** 不把 high 当金标；不让 locked_holdout 参与任何模型决策；不在本批宣称模型精度提升。

---

### H.Batch 3：可信不可变点数据集

**目标：** 从新点标签真源构建版本化、可追溯、无泄漏的数据集；训练数据和锁定验收数据物理或逻辑强隔离。

**前置条件：** Batch 2 的人工金标清单冻结；候选准入规则和来源映射稳定。

- [ ] 3.1 收紧数据集准入
  - 修改 `backend-service/services/iterative_labeling/seq_annotation/causal_window_builder.py` — 因果窗口构建器；只消费显式点事实和审核通过的弱标签。
  - 拒绝纯天来源、未审核候选和歧义来源；`locked_holdout` 只能输出到验收分区。
  - 缺测只用过去值、缺测掩码或明确无决策，不允许双侧插值和未来信息。

- [ ] 3.2 固化不可变快照与指纹
  - 快照保存输入源摘要、标签快照哈希、标签空间版本、来源白名单、设备日清单、划分清单、窗口参数和构建代码版本。
  - 同一输入与配置生成相同内容摘要；任何标签、边界、来源、角色或划分变化必须生成新版本，不覆盖旧快照。

- [ ] 3.3 输出质量报告
  - 按 `source`、`label_id`、设备日、站点、窗口上下文状态统计监督点和事件数。
  - 单独报告人工金标、K4 伴生正常、审核通过的 `peer_residual` 和其他弱标签。
  - 检查窗口字节级重复、设备泄漏、日期泄漏、增强源泄漏和 locked_holdout 泄漏。

- [ ] 3.4 建设“标签与数据”前端子视图
  - 新建 `frontend-sevice/src/pages/accuracy-operations/PvRealtimePointWorkbench.tsx` — 实时点研究工作台编排组件；读取 URL 的 `view=realtime-point` 和内部 `section` — 工作台子区，默认进入“标签与数据”。
  - 新建 `frontend-sevice/src/pages/accuracy-operations/PvRealtimePointDatasetPanel.tsx` — 数据集与标签质量面板；展示快照版本、标签空间版本、learning/locked_holdout 数量、来源/类别/设备日覆盖、未知点、泄漏检查和构建状态。
  - 修改 `frontend-sevice/src/pages/AccuracyOperationsPage.tsx` — 精度运营聚合页；在 `pv_fault` 分支增加“实时点研究”视图入口，默认仍保留现有闭环运营页面，不改变旧 URL 行为。
  - 扩展 `frontend-sevice/src/types/realtimePoint.ts` 与 `frontend-sevice/src/services/realtimePointApi.ts`，增加 `PointDatasetSnapshot` — 数据集快照、`PointDatasetQualityReport` — 质量报告和只读查询方法。
  - 构建快照是有副作用操作：只有来源合同和泄漏预检通过才启用；构建中显示阶段进度，失败保留上一份可用快照，不用空白覆盖。

**前端验收：** 无快照时解释下一步而非只显示“暂无数据”；有快照时可追溯来源、角色、版本和相对路径；locked_holdout 泄漏大于 0 时显示阻断且禁用后续评估/训练入口；刷新 URL 可恢复实时点研究子视图；原精度运营默认视图不受影响。

**关键字段链：** `point_labels + point_label_ops` → 来源/角色过滤 → 设备与日期划分 → 因果窗口 → 不可变快照 → 训练分区 / locked_holdout 验收分区。

**定向验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_causal_window_builder.py tests/test_realtime_point_snapshot.py -q
conda run -n cp_web python -m py_compile services/iterative_labeling/seq_annotation/causal_window_builder.py
```

**验收门槛：**

- [ ] `pure_day_label_not_allowed_for_seq` 测试通过。
- [ ] locked_holdout 泄漏计数为 0。
- [ ] 修改未来数据不改变当前窗口输入和目标。
- [ ] 每个来源、类别和角色均有设备日/点/事件统计，未知与无决策不被伪装成正常。
- [ ] 快照和报告只记录相对路径，旧快照未被覆盖。
- [ ] 完成统一自审和 Batch 3 交付小结。

**禁止事项：** 不直接用现有双侧插值 NPZ 产出正式因果指标；不为平衡类别复制 locked_holdout；不在本批修改在线服务。

---

### H.Batch 4：5 分钟稠密评估与离线因果告警

**目标：** 对每个可评估 5 分钟槽运行 `serving_stride=1` 的末点预测，离线复现因果告警状态机，得到真实事件、误报和延迟指标。

**前置条件：** Batch 3 快照通过泄漏与因果审计；当前 POC 工件保持不可晋升。

- [ ] 4.1 新增稠密回放评估器
  - 对每台设备按事件时间逐点前进，窗口右端严格等于当前槽；每 5 分钟输出预测或带原因的无决策。
  - 当前 `training_stride=6` 可继续用于训练抽样，但正式评估和服务必须 `serving_stride=1`。
  - 同一个 `event_time` 不得重复计分；设备之间状态独立，午夜不清空上下文。

- [ ] 4.2 实现离线 `CausalAlarmStateMachine`
  - 状态机输入当前及历史预测，输出 `normal → suspected → active_fault → recovering → normal`，不得读取未来预测。
  - 初始候选：`open_consecutive_points` — 开启告警所需连续故障点数为 3（连续 15 分钟）、`label_switch_consecutive_points` — 切换故障类别所需连续点数为 3、`cold_start_alarm_enabled` — 冷启动是否允许正式告警默认为 `false`；`close_consecutive_points` — 关闭告警所需连续正常点数和 `min_confidence` — 正式告警最低置信度只用 learning/validation 校准，不能用 locked_holdout 调参。
  - 原始逐点预测与消抖告警分开保存；状态机不得覆盖模型原始输出。

- [ ] 4.3 输出完整评估合同
  - `point_macro_f1` — 多分类逐点宏 F1。
  - `binary_f1` — 正常/故障 F1，其中 `fault_score` — 故障分数按 `1-P(label_id=0)` 计算，不改变多分类输出头。
  - `fault_mask_iou` — 故障区间重合度。
  - `event_precision` / `event_recall` / `event_f1` — 事件精确率、召回率和 F1。
  - `false_alarms_per_device_day` — 每设备日误报数。
  - `onset_delay_minutes` / `recovery_delay_minutes` — 告警开启和恢复延迟。
  - `no_decision_rate` / `coverage_rate` — 无决策率和正式覆盖率。
  - `metrics_by_source` / `metrics_by_context_status` / `metrics_by_label` — 按来源、上下文状态和类别分层指标。

- [ ] 4.4 在 locked_holdout 上只执行一次正式验收
  - 所有模型、阈值和状态机参数冻结后才打开 locked_holdout。
  - 验收结果只用于是否进入下一阶段，不回流调参；若失败，新增标注或回到 validation，不反复窥视 holdout。

- [ ] 4.5 建设“5分钟评估”前端子视图
  - 新建 `frontend-sevice/src/pages/accuracy-operations/PvRealtimePointEvaluationPanel.tsx` — 稠密评估与告警回放面板；顶部固定展示 `serving_stride=1`、5分钟槽宽、评估数据角色和工件版本，避免把现有 30 分钟结果误读为实时指标。
  - 主要内容使用指标表、逐类表、事件时间轴和上下文状态分布；同时展示原始点预测与状态机告警，不用颜色隐去二者差异。
  - 展示 `point_macro_f1`、`binary_f1`、事件 precision/recall/F1、误报/设备日、开启/恢复延迟、无决策率和覆盖率，并支持按来源、标签、设备和上下文状态筛选。
  - `locked_holdout` 正式评估入口显示参数冻结摘要和“一次性验收”警告，要求输入确认文本；执行后变为只读结果，不提供重复运行按钮。
  - 扩展 `frontend-sevice/src/types/realtimePoint.ts` 与 `frontend-sevice/src/services/realtimePointApi.ts`，增加 `DenseEvaluationRecord` — 稠密评估记录、`AlarmPolicySnapshot` — 告警策略快照、启动评估和轮询状态方法。

**前端验收：** validation 与 locked_holdout 结果视觉和文案明确分离；连续3点显示为15分钟；修改筛选不改变原始评估记录；评估 running/failed/completed、无事件、无逐类覆盖和部分指标 unavailable 均有独立状态；未确认业务阈值时显示“待确认”，不得展示绿色通过。

**关键字段链：** 不可变快照 → 每 5 分钟因果窗口 → 多分类概率 → 原始点预测 → 因果告警状态机 → 事件匹配 → 分层指标报告。

**定向验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_realtime_point_dense_evaluator.py tests/test_causal_alarm_state_machine.py tests/test_realtime_point_causality.py -q
```

**验收门槛：**

- [ ] 所有可评估槽间隔为 5 分钟，不能再以 30 分钟结果冒充实时评估。
- [ ] “连续 3 点”严格等于 15 分钟，不是 90 分钟。
- [ ] 修改当前时刻之后的数据，当前预测和告警状态完全不变。
- [ ] locked_holdout 只运行一次并留不可变评估记录。
- [ ] 业务方尚未确认的 `binary_f1`、事件召回和误报阈值明确标为“待确认”，不得擅自设成晋升通过。
- [ ] 完成统一自审和 Batch 4 交付小结。

**禁止事项：** 不启用正式告警；不修改工件的 `promotion_eligible`；不以 accuracy 单指标选模。

---

### H.Batch 5：保留多分类的模型对照实验

**目标：** 在相同可信快照、相同划分和相同 5 分钟评估合同下，选择可扩展多分类实时模型；二分类不替代业务故障分类。

**前置条件：** Batch 4 评估器和状态机测试通过；业务验收指标已列出，未确认阈值可继续标记待确认，但不得晋升。

- [ ] 5.1 建立同合同基线
  - 当前 Causal TCN W=72 作为主基线，至少运行多个随机种子并报告均值、标准差和最差值。
  - 同 split 运行 BiLSTM-Attention 作为非因果离线上界；必须显著标记“不可生产”，不得参与实时晋升。
  - 可加入简单持久性/规则基线，防止复杂模型只超过随机而未超过业务基线。

- [ ] 5.2 保持多分类主输出
  - 模型输出维度由 `label_space_version` 和类别注册表决定，支持后续新增标签。
  - 告警层继续用 `fault_score=1-P(normal)` 做正常/故障判定，类型层输出多分类结果。
  - 二分类模型只做消融或辅助头，不得删除多分类标签、历史映射或类型指标。

- [ ] 5.3 按条件执行改进实验
  - 类别极不平衡且稀有类召回不足时，再比较 weighted CE 与 Focal Loss。
  - 二分类召回高但类型混淆严重时，再比较“多分类主头 + 二分类辅助头”。
  - 慢故障召回不足且延迟可接受时，再比较 W=120 或多尺度因果 TCN。
  - 每次只改变一个主变量，保持快照、split、状态机和评估合同不变。

- [ ] 5.4 生成可审计模型工件
  - 修改 `backend-service/services/iterative_labeling/realtime_point/artifact.py` — 实时点模型工件读写和严格加载器；写入模型结构、类别映射、上下文、感受野、输入通道、缺测策略、数据集版本、标签哈希和完整评估记录。
  - 未满足全部门禁时保持 `promotion_eligible=false`、`alarm_policy.enabled=false`。

- [ ] 5.5 建设“模型实验”前端子视图
  - 新建 `frontend-sevice/src/pages/accuracy-operations/PvRealtimePointExperimentPanel.tsx` — 多分类模型实验与对照面板；按同一快照和评估合同展示实验运行、模型结构、上下文、loss、随机种子和聚合指标。
  - 主视图使用可排序表格；选择一行后在下方/侧边详情展示逐类指标、事件指标、误报、延迟、覆盖率和与基线差值，避免每个模型一张同构卡片。
  - Causal TCN 标为“实时候选”，BiLSTM-Attention 标为“非因果离线上界，不可生产”，二分类标为“消融/辅助”；任何标签都必须同时显示文字。
  - 增加 `promotion_eligible` — 是否满足进入治理条件和未通过门禁原因列表；业务阈值未确认或 locked_holdout 未验收时，操作区只能“查看证据”，不能“送入治理”。
  - 扩展 `frontend-sevice/src/types/realtimePoint.ts` 与 `frontend-sevice/src/services/realtimePointApi.ts`，增加 `RealtimePointExperiment` — 实验运行、`RealtimePointModelEvaluation` — 模型评估和实验创建/轮询/对比方法。

**前端验收：** 只能比较相同 snapshot/split/evaluation contract 的记录；多 seed 显示均值、标准差和最差值；逐类指标缺失时明确 unavailable；二分类实验不会隐藏多分类主线；失败实验可查看错误但不能送入治理。

**关键字段链：** 冻结快照与 split → 多分类训练 → 5 分钟稠密回放 → 告警指标 → locked_holdout 一次验收 → 不可变模型工件。

**定向验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_realtime_point_model.py tests/test_realtime_point_trainer.py tests/test_realtime_point_artifact.py tests/test_realtime_point_dense_evaluator.py -q
conda run -n cp_web python -m py_compile services/iterative_labeling/realtime_point/model.py services/iterative_labeling/realtime_point/trainer.py services/iterative_labeling/realtime_point/artifact.py
```

**验收门槛：**

- [ ] 所有候选使用同一数据快照、split、稠密评估器和告警参数。
- [ ] 报告多 seed 波动、逐类指标、事件指标、误报、延迟和覆盖率。
- [ ] 新增标签能力仍在，二分类实验未改变生产数据合同。
- [ ] 只有在业务阈值明确且全部达到时，才可把候选标为“可进入闭环验证”；仍不得直接生产晋升。
- [ ] 完成统一自审和 Batch 5 交付小结。

**禁止事项：** 不用 locked_holdout 选超参；不把非因果 BiLSTM 设为实时候选；不因 binary F1 更高而删除故障类型输出。

---

### H.Batch 6：候选段→复核→重训→Challenger 闭环

**目标：** 复用天路径已有的人审和累计训练能力，为实时点路径建立独立可重放闭环，支持后续持续新增故障标签。

**前置条件：** Batch 5 至少有一个通过离线门禁的多分类候选；标签表、数据集和 locked_holdout 边界稳定。

- [ ] 6.1 将实时模型候选段接入审核会话
  - 模型的低置信、误报、漏报和新型模式投影为区间候选，不直接写标签。
  - 审核单元从设备日摘要扩展为故障段，保留上下文曲线、模型概率、告警状态和来源追踪。
  - 人工可以改边界、改类别、新建标签、拒绝和撤销。

- [ ] 6.2 建立实时点路径独立累计水位
  - 修改实时点累计训练编排，使 `pv_fault_realtime` 使用独立消费水位和 `point_model_ref` — 点模型引用，不复用天路径 `production_path` — 当前生产建模路径的二选一状态。
  - 只有 `learning` 新标签计入重训变更数；locked_holdout 和未批准候选计数永远为 0。
  - 重训冻结新的不可变标签快照，失败不推进消费水位。

- [ ] 6.3 注册 Challenger 而非覆盖 Champion
  - Challenger 登记存什么：候选模型引用、训练快照、评估 ID、指标、标签空间版本和登记时间。
  - 为什么单独存：重训成功不等于可以生产，必须经过同合同评估和人工确认。
  - 分区维度：产品槽位 + `pv_fault_realtime` 路径 + 模型版本。
  - 路径/介质：由部署配置决定；只持久化相对工件路径或稳定 ID。
  - 只读 registry 查询供部署 UI、CLI 和其他服务展示/预填，无副作用；返回 `slots` — 槽位字典，每个槽位至少包含 `champion_model_ref` — 当前生产模型引用、`challenger_model_ref` — 待验证挑战者模型引用、`updated_at` — 最后更新时间、`note` — 人类备注和 `source_candidate_id` — 来源候选 ID。不存在登记时返回可诊断空槽位，不猜默认 Champion。

- [ ] 6.4 实现人工 Promote 门禁
  - Promote 写接口使用 `candidate_id` — Challenger 候选记录 ID 标识待晋升模型；语义是更新候选状态，并按请求决定是否覆盖指定实时点生产槽位。
  - `set_as_production` — 是否同步设为实时点路径 Champion；默认 JSON boolean `false`，只有全部门禁通过并由用户显式改为 `true` 才可写生产登记。
  - `production_slot` — 生产登记槽位；默认 `pv_fault_realtime`，与 registry 查询的槽位键一致，不得误写天路径槽位。
  - `note` — 可选的人类备注；不得代替必填的操作人和晋升原因。
  - 写入 registry 的必须是胜出的 `challenger_model_ref`，不是旧 `champion_model_ref`、天路径 `baseline_workflow_id` 或其他工作流模板 ID。
  - 不向普通前端提供可绕过候选门禁的通用 PUT/PATCH registry 接口；若运维恢复必须提供覆盖写接口，则只能全量替换指定 `production_slot` 对象，需独立高权限、幂等键、原因和同等级只追加审计。
  - `promotions_log` — 晋升操作日志是与业务模型登记分离的只追加审计介质，由部署配置决定存储位置且只记录相对引用；每条至少保存 `candidate_id`、旧 `champion_model_ref`、新 `challenger_model_ref`、`set_as_production`、`production_slot`、操作人、原因和时间戳，不允许编辑或删除。

- [ ] 6.5 验证完整字段链和失败恢复
  - 审核裁决、标签准入和候选状态应原子或通过幂等键可重放。
  - 训练失败、评估失败、登记失败和 Promote 失败均不得改变现有 Champion、水位或 locked_holdout。

- [ ] 6.6 建设实时点模型治理前端
  - 新建 `frontend-sevice/src/pages/deployment/PvRealtimePointGovernancePanel.tsx` — 实时点 Champion/Challenger、重训水位、门禁和晋升审计面板；作为 `AlgorithmDeploymentPage` 的 `tab=realtime-point` 子页，不混入现有天级/全天 Seq 路径切换。
  - 修改 `frontend-sevice/src/pages/AlgorithmDeploymentPage.tsx` — 算法部署聚合页；增加实时点治理入口和返回精度运营证据的上下文链接，默认部署页行为不变。
  - Challenger 表展示模型引用、快照、标签空间、稠密评估、locked_holdout 记录和全部门禁；选中候选后才显示 Promote 操作。
  - Promote 确认区逐项展示 `candidate_id`、`challenger_model_ref`、`production_slot=pv_fault_realtime`、`set_as_production` 和失败门禁；默认 `set_as_production=false`，只有用户显式勾选并填写 `operator` — 操作人、`reason` — 晋升原因后才允许提交。
  - 成功后刷新 Champion、Challenger 和只追加审计；失败保留原选择并显示服务端原因，不先乐观改写 Champion。
  - 扩展 `frontend-sevice/src/types/realtimePoint.ts` 与 `frontend-sevice/src/services/realtimePointApi.ts`，增加 `RealtimePointRegistry` — 实时点模型登记、`RealtimePointCandidateModel` — 候选模型、`RealtimePointPromotionEvent` — 晋升审计和对应查询/Promote 方法。

**前端验收：** 重训完成只出现 Challenger，不自动显示为 Champion；Promote 默认不改生产；确认文案明确写入的是 challenger 模型；门禁未通过、权限不足、重复请求和服务端冲突均禁用或阻断写入；刷新后状态以服务端 registry 为准；审计不可编辑或删除。

**关键字段链：** 实时点预测/告警 → 区间候选 → 审核会话 → 人工裁决 → `PointLabelService` → learning 水位 → 不可变快照 → 重训 → Challenger → locked_holdout 验收 → 人工 Promote → 实时点 Champion。

**定向验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_point_label_service.py tests/test_realtime_point_retraining.py tests/test_realtime_point_registry.py tests/test_realtime_point_promotion.py -q
Set-Location ..\frontend-sevice
npm run build
```

**验收门槛：**

- [ ] 审核前候选不进入训练；审核成功后标签与候选状态一致。
- [ ] 只有 learning 推进实时点重训水位，locked_holdout 泄漏为 0。
- [ ] 重训只登记 Challenger，不自动替换 Champion。
- [ ] Promote 显式写入 challenger 模型，失败无部分副作用，审计只追加。
- [ ] 动态新增标签贯通 UI、HTTP、标签注册、快照、模型输出和展示。
- [ ] 完成统一自审和 Batch 6 交付小结。

**禁止事项：** 不复用天路径模型指针；不“训练完成即上线”；不允许撤销或改写历史晋升审计。

---

### H.Batch 7：实时点流、5 分钟微批、Shadow 与灰度

**目标：** 在离线与闭环均通过后，建设点路径专属实时基础设施；先 Shadow，再人工门禁灰度，不影响天路径。

**前置条件：** Batch 6 全链路通过；业务 `binary_f1`、事件召回、误报、延迟和 Shadow 周期门槛已书面确认；有可一键回滚 Champion。

- [ ] 7.1 建设点路径专属存储
  - `point_measurements` — 点路径测量事实，只存点流输入。
  - `point_ingestion_watermarks` — 每设备已入库事件时间水位。
  - `point_detection_watermarks` — 每设备已检测事件时间水位。
  - `point_prediction_events` — 原始逐点预测与修订记录。
  - `point_alarm_states` — 当前告警状态。
  - `point_alarm_events` — 只追加告警状态迁移。
  - `point_replay_session`、`point_mock_release_schedule`、`point_mock_feed_cursor` — 独立虚拟时钟回放、确定性延迟计划和源读取游标。
  - 每种登记/表必须写清存什么、为何独立、分区维度和部署介质；不得与天路径表或游标共用真相。

- [ ] 7.2 实现跨日连续窗口和严格工件加载
  - 在线预测器只读取 `input_watermark` — 本轮允许读取的输入事件时间上界之前的数据；窗口按设备缓存，午夜不清空。
  - 冷启动输出 `cold/warming_up/partial_ready/ready` — 冷启动/热身/部分就绪/完全就绪的上下文状态；默认 `cold_start_alarm_enabled=false`。
  - 工件字段 `causal` — 是否满足因果约束；若它不是 JSON boolean `true`，或通道/类别/上下文不匹配、路径不可解析，加载器必须拒绝工件，不猜默认值。

- [ ] 7.3 实现独立 5 分钟微批任务
  - `pv_realtime_point_prediction` 每 5 分钟扫描新到或被允许修订的点，按设备分组处理；不为每台设备建 cron。
  - 幂等键至少包含模型版本、设备三元组、`event_time` — 测量事件时间和 `revision` — 迟到数据触发的修订号；重试不产生重复正式结果。
  - 迟到数据只在允许窗口内重算并递增修订号；超过上限记录 late data，不自动改历史正式告警。

- [ ] 7.4 先运行 Shadow
  - `is_shadow` — 是否为旁路观察结果为 `true` 的预测可计算指标和生成审核候选，但不触发正式告警、不修改天路径结论、不自动晋升。
  - 覆盖准时、1～2 槽迟到、连续缺测、服务重启、重复点、跨日和多设备异步到达。
  - 连续运行达到约定周期后，汇总误报、漏报、延迟、无决策、资源占用和人工复核结果。

- [ ] 7.5 接 REST 与前端状态展示
  - GET 状态/预测/告警/审计接口只读，无副作用；字段首次出现均提供中文说明。
  - 手动运行、retry、cancel 和 Promote 是写接口，必须有权限、`reason` — 操作原因、幂等和冲突处理。
  - 前端明确区分“实时点结论”和“天级最终结论”，并提供 loading、empty、error、disabled、Shadow 标识和时间轴。

- [ ] 7.6 小范围灰度并保留回滚
  - 只有因果审计、训练/推理对齐、稠密指标、迟到/重启恢复、Shadow 周期和人工回流全部通过，才允许 `alarm_policy.enabled=true`。
  - 先按明确站点/设备白名单灰度；扩大范围必须重新审查误报、漏报和延迟。
  - 回滚只切实时点 Champion 或关闭告警，不删除预测、告警事件、标签或天路径历史。

- [ ] 7.7 建设“实时运行”前端子视图
  - 新建 `frontend-sevice/src/pages/accuracy-operations/PvRealtimePointOperationsPanel.tsx` — 实时点运行总览；展示当前模型、Shadow/正式模式、最近微批、设备 ready 分布、ingestion/detection 水位差、迟到/失败队列、告警数量和资源摘要。
  - 设备主表按站点/设备/支路展示上下文状态、最后入库时刻、最后检测时刻、延迟槽数、最新预测、告警状态和可诊断错误；支持状态、站点、Shadow、告警筛选。
  - retry/cancel 是明确写操作，显示影响时间范围和 `reason`；刷新和轮询期间保留当前筛选/分页，不因部分设备失败清空整表。
  - Shadow 模式使用固定文字标识和只读提示，不显示“正式告警已开启”；只有后端返回正式灰度白名单且告警开关开启时才显示正式状态。

- [ ] 7.8 建设设备级实时详情页和路由
  - 新建 `frontend-sevice/src/pages/PvRealtimePointDevicePage.tsx` — 单设备实时点详情；展示测量、缺测、原始多分类概率、预测标签、告警状态迁移、迟到修订和人工标签 overlay 的同一事件时间轴。
  - 修改 `frontend-sevice/src/App.tsx` — 路由入口；注册 `/accuracy-operations/pv-realtime/devices/:deviceKey`，未知设备、非法编码和无权限分别显示可诊断状态，不重定向到错误默认设备。
  - 扩展 `frontend-sevice/src/types/realtimePoint.ts` 与 `frontend-sevice/src/services/realtimePointApi.ts`，增加 `RealtimePointRuntimeStatus` — 运行总览、`DevicePointStatus` — 设备状态、`PointPredictionEvent` — 原始点预测、`PointAlarmState` — 当前告警和 `PointAlarmEvent` — 状态迁移事件。
  - 详情页默认只读；从候选区间跳转审核时保留设备和事件时间范围，返回后恢复原筛选。

- [ ] 7.9 完成前端响应式、可访问性和受控轮询
  - 1440px 使用总览 + 设备表 + 详情入口；常见笔记本宽度压缩辅助列并保留主状态；窄屏只展示运行摘要和单设备时间轴，不提供复杂 Promote/批量重试。
  - 图表提供文本摘要和 tooltip；键盘可操作筛选、表格行和审核按钮；轮询仅在页面可见时运行，离开页面或切换槽位立即取消旧请求。
  - 所有时间明确事件时间/入库时间/检测时间，禁止把浏览器本地时间混成事件时间。

**前端验收：** URL 深链和刷新可恢复设备；跨午夜时间轴连续；Shadow 与正式告警可被非颜色方式区分；迟到修订不覆盖旧 revision 展示；局部 API 失败只影响对应区域；无设备、无预测、无告警、冷启动、部分就绪、服务停止和权限不足状态均可理解；原天路径运营与部署页面无回归。

**关键字段链：** 点流接入 → `point_measurements` → ingestion watermark → 设备因果缓冲 → 多分类预测 → `point_prediction_events` → detection watermark → 告警状态机 → Shadow/正式告警 → 前端时间轴 → 人工复核闭环。

**定向验证：**

```powershell
Set-Location backend-service
$env:PYTHONPATH='.'
conda run -n cp_web pytest tests/test_realtime_point_ingestion.py tests/test_realtime_point_predictor.py tests/test_realtime_point_scheduler.py tests/test_realtime_point_late_data.py tests/test_realtime_point_restart_recovery.py tests/test_realtime_point_alarm_api.py -q
Set-Location ..\frontend-sevice
npm run build
```

另执行受控 Shadow smoke：至少覆盖两台设备、跨午夜、迟到点、缺测和一次服务重启；不得用已全部入库的整日数据伪装实时到达。

**验收门槛：**

- [ ] 点路径不读取/修改天路径表、游标、封账状态、模型指针或日预测结果。
- [ ] 每设备水位单调；重复微批幂等；午夜上下文连续。
- [ ] Shadow 不触发正式告警，正式开关默认关闭。
- [ ] 服务重启后可恢复水位、窗口、重试和告警状态。
- [ ] 稳态新槽在约定时限内产出预测或明确无决策原因。
- [ ] 灰度前所有业务门槛、权限和回滚步骤已书面确认。
- [ ] 完成统一自审和 Batch 7 最终交付小结。

**禁止事项：** 不把当前整日 Mock 当实时验证；不复用每天 02:30 天路径任务；不在 Shadow 阶段触发正式告警或自动切生产。

---

### H.4. 总体验收矩阵

| 成功标准 | 最早验收批次 | 最终证据 |
|---|---:|---|
| 天/点标签物理真源彻底分离 | Batch 1 | 新表对账报告、读写定向测试、旧表只读证明 |
| `human_day` 不进入点路径 | Batch 1 | 来源拒绝测试和迁移差异报告 |
| 自动定位候选不冒充真值 | Batch 2 | 候选队列、审核审计、批准/拒绝统计 |
| 20 learning + 10 locked_holdout | Batch 2 | 不可变设备日清单和人工标注摘要 |
| locked_holdout 永不进训练 | Batch 3 | 泄漏检查为 0、快照角色统计 |
| 5 分钟稠密评估 | Batch 4 | `serving_stride=1` 报告、因果审计和状态机测试 |
| 保留可扩展多分类 | Batch 5 | 标签空间版本、逐类指标和新增标签测试 |
| 审核→重训→Challenger→Promote 闭环 | Batch 6 | 字段链集成测试、失败恢复和只追加审计 |
| 实时点流与天路径运行隔离 | Batch 7 | 跨日/迟到/重启 Shadow 报告和隔离测试 |
| 正式告警可控启停与回滚 | Batch 7 | 灰度门禁、权限、回滚演练记录 |

### 4.1 前端交付矩阵

| Batch | 用户入口 | 前端交付 | 必须验证 |
|---:|---|---|---|
| 0 | 现有四个入口 | 只读盘点、截图、字段缺口和页面流转图 | 不修改源码；现有入口状态可诊断 |
| 1 | 人工审核页 | 来源类型合同、点路径标识、禁止 `human_day`、撤销联动刷新 | 天/点 UI 不串源；冲突保留表单 |
| 2 | 标注列表 + 审核页 | 候选队列、曲线修边界、用途选择、新增标签、拒绝/撤销 | learning/locked_holdout、重复提交、断点恢复 |
| 3 | 精度运营 → 实时点研究 → 标签与数据 | 快照、来源/类别/角色覆盖、泄漏门禁和构建状态 | 无快照/构建中/失败/可用；旧运营视图无回归 |
| 4 | 精度运营 → 实时点研究 → 5分钟评估 | 稠密指标、事件时间轴、状态机结果、一次性 holdout 验收 | 5分钟与30分钟不混淆；阈值待确认不显示通过 |
| 5 | 精度运营 → 实时点研究 → 模型实验 | 同合同实验表、多 seed、逐类/事件/延迟详情 | 非因果和二分类仅作对照；失败模型不可送治理 |
| 6 | 算法部署 → 实时点模型 | 独立 Champion/Challenger、重训水位、Promote 和只追加审计 | 默认不改生产；写入 challenger；失败不乐观更新 |
| 7 | 精度运营 → 实时运行 → 设备详情 | 水位、微批、设备状态、预测/告警时间轴、迟到修订和灰度 | 深链、跨日、Shadow、部分失败、窄屏只读和旧页回归 |

## H.5 历史首轮执行建议（已废止）

原方案曾建议下一次实施执行 Batch 0 + Batch 1；该建议现已废止，不得作为当前任务入口。G0 也已完成。当前唯一开工指令是上文 A12：**只执行 Batch G10，且一次只开 G10-S0**。未经当前切片测绿不得进入下一切片，未经 G10 退出门槛通过不得进入 G11。
<!-- @AI_GENERATED: end -->