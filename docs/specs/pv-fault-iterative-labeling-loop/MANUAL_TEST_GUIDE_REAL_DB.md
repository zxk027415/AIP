<!-- @AI_GENERATED -->
# pv_fault 光伏故障诊断：真实 DB 人工测试操作手册

> **适用范围**：`pv_fault`（光伏正式槽）光伏故障诊断的“累计训练 → 调度预测 → 人工审核 → 阈值重训”正常链路。
>
> **边界**：本手册不创建、不恢复、不使用 `pv_demo`；所有业务数据路径均使用相对于项目根目录的路径。本文的“当前已准备状态”记录于 2026-07-15，供本机继续验收使用。

## 1. 先读本节：两种测试模式

| 模式 | 适用场景 | 会不会写数据 | 本机当前是否可直接做 |
|---|---|---:|---:|
| A. 当前状态验收 | 检查服务、累计状态、已有预测批次、审核结果，或显式执行已排队重训 | 只读步骤不写；执行重训会新增模型工件 | 是 |
| B. 从零完整回放 | 从带标签导入开始，重新拉取无标签观测、预测、审核并触发阈值 | 会写 MySQL、账本、快照、模型和审核文件 | 需先备份并明确授权重置 |

**不要把 A 模式中的已有预测批次再次拿来创建新审核会话做重复测试。** 新的 `review_id`（审核会话 ID）会使它成为新的人工裁决来源，可能再次消耗 `pending_change_count`（距离下次重训的累计变更数）。

## 2. 当前已准备的测试数据与参数

### 2.1 数据清单

| 数据/产物 | 相对项目根目录路径或介质 | 当前状态 | 用途 |
|---|---|---|---|
| 带真值训练数据 | `backend-service/datasets/dataset_combined.parquet` | 303,321 行、6 类标签 | 已登记到累计训练集；字段含 `time`（时间）、`site_id`（站点）、`device_id`（设备）、`branch_id`（支路）、`value`（测量值）、`i_cal`（计算电流）、`label`（人工/历史标签）。 |
| 原始无标签模拟来源 | `backend-service/datasets/相关数据/train_ori/data_long#dangyang&_&_.csv` | 已选取部分时序写入模拟源 | 文件含 `data_date`（原始时间）、`site_id`、`device_id`、`branch`、`value`、`i_cal`；用于模拟在线新观测，不直接绕过调度预测。 |
| 模拟生产源 | MySQL 的 `station_observations`（模拟源表） | `station_id="pv"` 已有 1,728 条测试观测 | `pv_data_pull`（光伏拉取任务）只读取此表中 `station_id="pv"` 且晚于高水位的记录。 |
| 未标注平台样本 | MySQL 的 `training_samples`（平台训练样本表） | `site_id="pv"` 已有 1,728 条，`label` 为 `NULL` | 调度拉取后的待预测样本；预测任务只筛选 `label IS NULL OR label < 0`。 |
| 已完成模型 | `backend-service/data/models/pv_fault_rfc_1784106546_892c07.pkl` | 已存在，含 20 个推理特征 | 首次累计重训得到的真实模型工件；未发布为生产模型。 |
| 第一预测批次 | `backend-service/data/iterative_labeling/prediction_batches/pv_fault/pred-20260715092402-b308591b.json` | 1 个审核单元 | 用于验证单元级 `confirm`（确认）、重复提交、`correct`（改判）、`skip`（跳过）。 |
| 第二预测批次 | `backend-service/data/iterative_labeling/prediction_batches/pv_fault/pred-20260715093112-fa1d3cdc.json` | 17 个审核单元 | 用于触发 20 次累计变更阈值。 |
| 当前累计账本 | `backend-service/data/iterative_labeling/cumulative_training/pv_fault/state.json` | 17 条有效人工单元、`pending_change_count=0` | 保存人工真值、冻结快照和重训请求；`pv_fault` 是账本分区键。 |
| 最新冻结快照 | `backend-service/data/iterative_labeling/cumulative_training/pv_fault/snapshots/snapshot-20260715093555-d5a9f6.csv` | 304,953 条数据、6 类标签 | 第二次阈值达成后冻结的不可变训练输入。 |
| 已排队重训请求 | `retrain-791f938b63e8` | `queued`（排队待执行） | 绑定最新冻结快照；只能由人工显式调用重训接口执行。 |

### 2.2 参数卡

| 参数 | 当前值 | 含义与要求 |
|---|---:|---|
| `slot`（槽位） | `pv_fault` | 累计账本、审核结果、预测批次的分区键；本手册所有请求都显式传此值。 |
| `PV_RETRAIN_LABEL_THRESHOLD`（重训标签阈值） | `20` | 累计训练变更达到 20 时，系统冻结快照并创建 `queued` 重训请求；不会自动训练或发布。 |
| 后端地址 | `http://127.0.0.1:8080` | 人工验收使用 experiment 模式的固定端口。 |
| 前端地址 | `http://127.0.0.1:3001` | 可用于打开审核页面。 |
| Conda 环境 | `cp_web` | 本机已验证可运行后端、pytest 和 Parquet 读取。 |
| `enable_llm`（是否启用 LLM 审核建议） | 建议 `false` | 正常链路测试不依赖 LLM；关闭后结果更稳定、无外部模型依赖。 |
| `reviewer`（审核人标识） | 建议 `manual-tester` | 审计字段；同一单元改变审核人也会被视作训练标签变更。 |
| 当前 `loop_id`（训练闭环 ID） | `loop-80fa1c05-dd7a-4234-a25d-7bdbccced145` | 当前已完成模型对应的训练闭环；创建已有预测批次的审核会话时使用。 |
| 当前 `model_ref`（模型引用） | `pv_fault_rfc_1784106546_892c07` | 当前完成模型的真实 ID；预测批次 JSON 已记录该值。 |

> **不要在文档、脚本或终端输出中记录数据库密码、API Key 或 `.env.local` 内容。** 数据库连通性只通过健康检查接口确认。

## 3. 启动与只读检查

### 3.1 启动服务

在项目根目录的 PowerShell 中执行：

```powershell
.\aip.ps1 experiment
```

该脚本的职责：启动后端 `8080`（无 reload）、前端 `3001` 和 AutoResearch worker；默认使用 `cp_web` 环境。若 `8080` 已能正常返回健康检查，**不要重复启动第二个后端**。

> `aip.ps1 stop` 会终止所有 Python/Node 进程，可能影响其他实验；人工测试期间不要把它作为常规停止方式。

### 3.2 定义 API 基地址并检查后端

```powershell
$base = "http://127.0.0.1:8080"
Invoke-RestMethod "$base/api/health"
Invoke-RestMethod "$base/api/system/db-health"
Invoke-RestMethod "$base/api/scheduler/status" | ConvertTo-Json -Depth 8
```

通过标准：

- `status`（服务状态）为 `healthy`；
- `engine`（数据库引擎）为可用状态，且 `missing_vars`（缺失配置项）为空；
- `pipelines.pv_fault.running`（光伏调度管线是否运行）为 `true`；
- `pv_data_pull`（光伏数据拉取任务）与 `pv_prediction`（光伏预测任务）均已注册。

### 3.3 读取累计训练状态

```powershell
Invoke-RestMethod "$base/api/iterative-labeling/cumulative-training/state?slot=pv_fault" |
  ConvertTo-Json -Depth 12
```

关键返回字段：

| 字段 | 当前预期 | 中文含义 |
|---|---:|---|
| `effective_labeled_unit_count` | `17` | 当前仍有效的人工审核单元数；被 `skip` 撤销的单元不计入。 |
| `labeled_import_count` | `1` | 已登记的带 `label` 历史导入数。 |
| `pending_change_count` | `0` | 自上一轮冻结后累计的训练变更数。 |
| `retrain_label_threshold` | `20` | 触发下一轮快照与重训请求的阈值。 |
| `latest_snapshot` | `snapshot-20260715093555-d5a9f6` | 最新不可变训练快照元数据。 |
| `latest_retrain_request` | `retrain-791f938b63e8` / `queued` | 最新重训请求及其待执行状态。 |

## 4. 当前已准备环境：建议人工验收步骤

### 4.1 核对已有预测批次

```powershell
$batchId = "pred-20260715093112-fa1d3cdc"
Get-Content "backend-service/data/iterative_labeling/prediction_batches/pv_fault/$batchId.json" -Raw |
  ConvertFrom-Json |
  ConvertTo-Json -Depth 10
```

检查每个 `predictions`（预测单元数组）元素都含：

- `site_id` — 站点标识；
- `device_id` — 设备标识；
- `branch_id` — 支路标识；
- `time_window` — 预测聚合时间窗；
- `predicted_label` — 模型预测故障标签；
- `confidence` — 预测置信度，必须在 `[0, 1]`。

当前批次预期有 17 个单元，`model_ref` 应为 `pv_fault_rfc_1784106546_892c07`。

### 4.2 核对审核会话和审核结果（只读）

```powershell
$reviewId = "rev-2e73a568"
Invoke-RestMethod "$base/api/iterative-labeling/review-sessions/$reviewId?slot=pv_fault" |
  ConvertTo-Json -Depth 16
```

通过标准：

- `status`（审核会话状态）为 `reviewed`；
- `reviewed_count`（已审核数）和 `total_count`（总数）都为 `17`；
- 每个 `unit_key`（诊断单元唯一键）采用 `site_id|device_id|branch_id|time_window` 格式；
- `prediction_context.source_csv_path`（预测原始 CSV 路径）是相对项目根目录路径。

### 4.3 显式执行当前已排队的第二次重训（**写操作，按需执行**）

仅在需要验证“第二个快照也能训练”时执行。它会新增模型工件，但不会自动发布模型：

```powershell
$requestId = "retrain-791f938b63e8"
Invoke-RestMethod -Method Post `
  -Uri "$base/api/iterative-labeling/cumulative-training/retrain-requests/$requestId/run?slot=pv_fault" |
  ConvertTo-Json -Depth 20
```

通过标准：

- `request.status`（重训请求状态）从 `queued` 变为 `completed`；
- `train_result.model_ref`（新训练模型引用）非空；
- `publication`（发布状态）必须为 `not_published`；
- 再次读取 `/cumulative-training/state` 时，`latest_retrain_request.status` 为 `completed`。

**不要重复调用同一 `request_id`。** 请求不处于 `queued` 时会返回冲突错误，这是防止重复训练的预期保护。

### 4.4 前端人工测试流程（当前实际可用界面）

本节仅覆盖当前已核实的“人工标注审核”菜单和审核详情页。它适合人工查看真实预测、判读波形并提交裁决；创建预测批次、创建新审核会话、累计导入和重训仍按本手册的 API/管理员步骤执行。

#### 4.4.1 打开前端并进入会话列表

1. 按 §3.1 启动服务后，在浏览器打开 `http://127.0.0.1:3001`（前端地址）。如系统要求登录，先使用有平台访问权限的账号登录。
2. 在左侧菜单依次选择：**行业服务 → 行业数据管理 → 人工标注审核**。该入口进入 `/iterative-labeling`（审核会话列表路由）。
3. 在会话列表中，对待处理会话选择“继续审核”；对已结束会话选择“查看结果”。页面会跳转到审核详情页。

若需要由管理员提供的会话 ID 直接进入，请使用下列 URL，而不是旧文档里的 `/iterative-labeling/review/{reviewId}` 路径形式：

```text
http://127.0.0.1:3001/iterative-labeling/review?review_id=rev-2e73a568&slot=pv_fault
```

其中：

- `review_id` — 审核会话唯一标识；决定加载哪一批预测单元和已提交裁决。
- `slot` — 审核、标签和累计训练数据的隔离分区；本次正常链路固定为 `pv_fault`（光伏正式槽）。

> 当前 `rev-2e73a568`（审核会话 ID）已经完成 17/17 条审核，**只用于只读界面核验**。不要在它上面重复提交裁决；如需验证写操作，必须由管理员按 §5.3 和 §6.1 生成新的预测批次和新会话。

#### 4.4.2 已完成会话的只读核验

打开前述 `rev-2e73a568` 后，按下面项目逐项检查，不点击裁决按钮：

| 前端区域 | 人工检查动作 | 通过标准 |
|---|---|---|
| 审核进度 | 查看进度条和“当前进度”统计。 | 显示 `17 / 17`，会话已全部审核。 |
| 当前单元 | 查看 `unit_key`（诊断单元唯一键）、`site_id`（站点 ID）、`device_id`（设备 ID）、`time_window`（诊断窗口）。 | 字段非空；`unit_key` 的组成与 §4.2 的 `site_id|device_id|branch_id|time_window` 口径一致。 |
| 分类器建议 | 查看预测标签、标签名称和 `confidence`（预测置信度）。 | 标签可解释；置信度显示为百分比，或明确提示模型未输出概率。 |
| 设备波形 | 检查“设备波形（电压 / 电流）”中的实测电流与理论电流曲线，可拖动缩放条查看局部。 | 波形加载成功；若后端没有可用时序，页面应显示明确的提示而不是空白或崩溃。 |
| 参考波形 | 查看“各类故障典型波形参考（对照用）”。 | 有训练参考数据时显示各标签的参考曲线；无数据时不阻断当前单元审核。 |
| 审核结果 | 在已完成会话中查看“三方精度实时对比”。 | 显示分类器精度、LLM 建议精度（如有）、已审核单元数，以及 `Macro Precision`（宏平均精确率）、`Macro Recall`（宏平均召回率）、`Macro F1`（宏平均 F1）。 |

页面会优先定位第一条未审核单元；已全部审核时仍可用于查看当前单元和指标。中途关闭浏览器后再次打开同一 `review_id`，未审核会话会自动恢复到第一条未裁决单元。

#### 4.4.3 新会话的人工裁决步骤

**前提**：管理员已通过 §5.3 生成新的真实 `pred-...`（预测批次 ID），并通过 §6.1 创建新的 `review_id`。人工测试人员拿到该 ID 后，在浏览器打开：

```text
http://127.0.0.1:3001/iterative-labeling/review?review_id=<新的审核会话ID>&slot=pv_fault
```

每个单元先核对站点、设备、窗口、分类器标签/置信度与波形，再按实际判断选择一种裁决。当前前端将 `reviewer`（审核人标识）固定提交为 `current_user`；这是界面当前实现，不等同于真实登录用户名。需要指定 `manual-tester`（人工测试人）等审计身份时，请使用 §6.2 的管理员/API 测试步骤。

| 裁决动作 | 前端点击步骤 | HTTP/账本副作用与预期 |
|---|---|---|
| `confirm`（确认分类器预测） | 点击“确认分类器”，在确认弹框中确认。 | 前端将该单元的分类器 `predicted_label`（预测标签）作为 `verdict_label`（人工真值标签）提交；成功提示“裁决已提交”，进度前进，累计训练账本首次准入时增加有效真值与 `pending_change_count`（待重训累计变更数）。 |
| `correct`（改判为已有标签） | 点击“修正”，在下拉框选择已有正确标签，再点击确认。 | 提交所选 `verdict_label`；如果该单元此前已有有效真值，则覆盖原标签并计入一次训练变更。 |
| `new_label`（新增标签） | 点击“新标签”，输入新的故障类别名称，再点击确认。 | 页面先创建标签注册表项，再以新 `label_id`（标签数值 ID）提交裁决；仅当确实发现现有标签空间没有覆盖的故障类型时使用。 |
| `skip`（标记存疑并跳过） | 点击“标记存疑跳过”，在确认弹框中确认。 | 不传 `verdict_label`；该单元不计入精度统计、不进入累计训练集。若它已有有效真值，累计账本会撤出该真值。 |

每次提交成功后，页面会重新读取会话，刷新审核进度，并跳转到下一单元；审核完成后会显示三方精度面板。提交失败时保留当前单元，人工应记录页面提示并停止重复点击，交由管理员按 §6.3 查询累计状态和错误原因。

> 对同一个 `unit_key`（诊断单元唯一键）重复提交完全相同的裁决，累计训练服务按幂等规则返回 `duplicate_verdict`（重复裁决），不会再次消耗 `pending_change_count`。该规则应优先用 API 做精确断言；前端页面只会显示“裁决已提交/失败”提示，不展示该内部原因码。

#### 4.4.4 审核完成后的旧版回流 CSV 操作

当至少审核过一条单元时，审核进度卡右上角的“完成 → 生成新真值数据集”按钮可用。此功能将人工标签回贴到该会话关联的原始时序，生成 CSV；它是历史回流能力，**不等同于当前“累计训练账本 → 阈值快照 → queued 重训请求”的主链路**。

1. 点击“完成 → 生成新真值数据集”。
2. 默认不勾选“合并基线 CSV”。需要将历史基线行一并拼接到回流 CSV 时才启用该选项。
3. 启用后，在“基线 CSV 路径”输入 `base_csv_path`（基线 CSV 相对项目根目录路径）；例如管理员提供的带标签基线 CSV。不得输入绝对路径。
4. 点击弹框中的生成/确认按钮，等待成功提示。
5. 核对返回的 `dataset_version`（回流数据集版本）、`csv_path`（生成 CSV 的相对项目根目录路径）、`labeled_rows`（回贴标签后的时序行数）、`labeled_units`（去重后的审核单元数）和 `total_source_rows`（原始预测 CSV 总行数）。

`merge_base`（是否合并基线 CSV）为关闭时，只生成本次已审核单元回贴后的数据；为开启时，后端按 `base_csv_path` 读取基线数据后再合并。`skip`（跳过）单元不会产生可回贴的真值标签。

#### 4.4.5 当前前端边界与交接规则

下表明确区分“可由人工审核页完成”和“仍需管理员/API 完成”的操作，避免把 API 客户端已导出的能力误认为已有界面按钮。

| 能力 | 当前人工审核页 | 正确操作路径 |
|---|---|---|
| 打开会话、看预测/波形、提交四类裁决、查看精度、生成回流 CSV | 支持 | 按本节操作。 |
| 创建真实审核会话 | 当前菜单和审核详情页未提供按钮 | 管理员使用 §6.1 的 `POST /api/iterative-labeling/review-sessions`（创建审核会话）接口；本轮未验证工作流编辑器中的其他入口，不能将其作为人工验收步骤。 |
| 生成预测批次或即时触发光伏调度 | 不支持 | 管理员按 §5.3 触发 `pv_data_pull`（光伏数据拉取任务）和 `pv_prediction`（光伏预测任务）。 |
| 查看累计训练状态、登记带标签导入、查看或执行 `queued`（待执行）重训请求 | 不支持 | 管理员按 §3.3、§4.3、§5.1 和 §7 使用累计训练接口。前端 API 客户端虽有对应方法，但当前审核页面未接入控制台。 |
| 使用已完成会话做写入测试 | 不允许 | `rev-2e73a568` 仅供只读核验；必须建立新的预测批次与审核会话。 |

## 5. 从零完整回放：数据和参数准备

> 本节会新增/修改 MySQL 数据、累计账本、快照和模型。当前 `pv_fault` 环境已经有验收数据，若要从零回放，先备份后由负责人确认重置范围；不要自行删除文件、数据表或模型。

### 5.1 带真值数据准备

训练导入文件必须满足：

| 列 | 约束 |
|---|---|
| `time`（时间） | 可解析为时间；同一设备应有完整时序。 |
| `site_id`（站点） | 非空。 |
| `device_id`（设备） | 非空。 |
| `branch_id`（支路） | 非空。 |
| `value`（测量值） | 数值；允许缺失由工作流处理。 |
| `i_cal`（计算电流） | 数值；允许缺失由工作流处理。 |
| `label`（真值标签） | 非空且至少包含两个类别；无 `label` 的文件会被累计训练导入接口拒绝。 |

登记训练导入：

```powershell
$body = @{
  dataset_path = "backend-service/datasets/dataset_combined.parquet"
  source_name  = "manual-pv-fault-test"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "$base/api/iterative-labeling/cumulative-training/imports?slot=pv_fault" `
  -ContentType "application/json" `
  -Body $body |
  ConvertTo-Json -Depth 16
```

请求字段：

- `dataset_path` — 带 `label` 的 CSV/Parquet 相对项目根目录路径；
- `source_name` — 人工可读的导入来源说明，用于审计；
- `slot` — 查询参数，累计训练分区，使用 `pv_fault`。

通过标准：返回 `imported=true`；`latest_snapshot`（最新快照）非空；`latest_retrain_request.status`（最新重训请求状态）为 `queued`。若标签不足两类，则查看 `retrain_blocker`（阻断原因），不得继续训练。

### 5.2 无标签预测数据准备

正常预测**不直接把 CSV 传给预测接口**。应按生产路径准备模拟源中的新观测：

1. 来源数据使用 `backend-service/datasets/相关数据/train_ori/data_long#dangyang&_&_.csv`；
2. 选择同一设备的连续时序，建议每个设备×日窗口至少 96 个观测点；
3. 写入 MySQL 的 `station_observations`（模拟源表）时，`station_id`（源站点标识）必须为 `pv`；
4. 新观测的 `timestamp_utc`（源时间）必须晚于当前预测游标 `prediction_cursor.json` 中的 `last_predicted_time`（最后成功预测时间），否则正常拉取任务会跳过它；
5. 不要把 `label` 写入无标签预测观测；拉取任务会把它写成平台训练样本中的 `NULL`。

> 写入模拟源表属于管理员数据库操作，当前仓库没有面向人工测试的通用“播种源数据”REST 接口。先检查行数和时间范围，再执行写入；避免写入真实生产源。

### 5.3 正常调度拉取与预测

```powershell
Invoke-RestMethod -Method Post `
  -Uri "$base/api/scheduler/tasks/pv_data_pull/trigger-now"

# 等待任务完成后检查状态；不要连续重复触发。
Invoke-RestMethod "$base/api/scheduler/status" | ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post `
  -Uri "$base/api/scheduler/tasks/pv_prediction/trigger-now"
```

任务职责：

- `pv_data_pull` — 读取 `station_observations` 的新 `pv` 观测，写入 `training_samples`，并设置 `label=NULL`；
- `pv_prediction` — 读取最新完成模型、游标之后的未标注样本，运行预测工作流，写入 `PredictionRecord`（预测审计记录）、预测输入 CSV、预测批次 JSON 和预测游标。

通过标准：

- 调度状态中的 `last_result`（最近执行结果）为 `success`；
- `prediction_batches/pv_fault/` 下新增 `pred-*.json`；
- `prediction_inputs/pv_fault/` 下有同名 CSV；
- 批次 JSON 的 `predictions` 非空；
- `prediction_cursor.json` 的 `batch_id`（最后成功批次）等于新批次 ID。

如果没有完成模型，`pv_prediction` 会记录 `MODEL_PENDING`（模型待就绪）并安全返回：不得产生 `PredictionRecord`、预测批次或游标。该分支应在隔离/新鲜状态下验证，不要为此删除当前已完成模型。

## 6. 人工审核 API 测试步骤

### 6.1 基于真实预测批次创建会话

```powershell
$loopId = "<已完成模型对应的 loop_id>"
$batchId = "<新的 pred- 批次 ID>"
$body = @{
  loop_id             = $loopId
  prediction_batch_id = $batchId
  enable_llm          = $false
  slot                = "pv_fault"
} | ConvertTo-Json

$session = Invoke-RestMethod -Method Post `
  -Uri "$base/api/iterative-labeling/review-sessions" `
  -ContentType "application/json" `
  -Body $body
$session
```

请求字段：

- `loop_id` — 所属训练闭环 ID，用于审计关联；
- `prediction_batch_id` — 真实预测批次 ID，格式为 `pred-...`；
- `enable_llm` — 是否后台生成 LLM 建议；手工稳定验收使用 `false`；
- `slot` — 审核、标签和累计训练分区。

记录响应中的 `review_id`（审核会话 ID）和 `total_count`（待审核单元数）。

### 6.2 读取单元并提交裁决

```powershell
$reviewId = "<review_id>"
$detail = Invoke-RestMethod "$base/api/iterative-labeling/review-sessions/$reviewId?slot=pv_fault"
$detail.units | ConvertTo-Json -Depth 10
```

提交 `confirm`（确认预测）示例：

```powershell
$unit = $detail.units[0]
$body = @{
  unit_key      = $unit.unit_key
  action_type   = "confirm"
  verdict_label = [int]$unit.classifier_prediction.predicted_label
  reviewer      = "manual-tester"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "$base/api/iterative-labeling/review-sessions/$reviewId/verdicts?slot=pv_fault" `
  -ContentType "application/json" `
  -Body $body |
  ConvertTo-Json -Depth 16
```

裁决字段：

- `unit_key` — `site_id|device_id|branch_id|time_window` 组成的诊断单元键；
- `action_type` — 操作类型，只能是 `confirm`（确认）、`correct`（改判）、`new_label`（新增标签）或 `skip`（跳过）；
- `verdict_label` — 人工真值标签；`confirm` 取模型预测标签，`correct` 指定已有正确标签，`skip` 不传；
- `new_label_name` — 新增标签名称，仅 `new_label` 时必填；
- `reviewer` — 审核人标识，用于审计。

### 6.3 四个必须验证的规则

| 操作 | 人工测试动作 | 累计训练预期 |
|---|---|---|
| 首次 `confirm` | 对同一 `unit_key` 提交确认 | `effective_labeled_unit_count` 增加 1，`pending_change_count` 增加 1。 |
| 重复 `confirm` | 完全相同请求再提交一次 | 响应 `reason=duplicate_verdict`；有效单元数和待重训变更数均不增加。 |
| `correct` | 改为另一个已有 `verdict_label` | 同一账本条目被覆盖，`pending_change_count` 增加 1。 |
| `skip` | 对已有有效真值的单元提交跳过 | 真值从账本撤出；`effective_labeled_unit_count` 减少 1；后续快照不应含该单元。 |

每次提交后执行：

```powershell
Invoke-RestMethod "$base/api/iterative-labeling/cumulative-training/state?slot=pv_fault" |
  ConvertTo-Json -Depth 16
```

若审核裁决已接受、但 `cumulative_training.admitted`（是否成功准入）为 `false` 且出现 `admission_error`（准入错误），可以使用**相同的** `unit_key` 和裁决重试。该恢复操作不会重新创建审核单元；成功后才会进入累计账本。

## 7. 阈值、快照和重训请求验收

当 `pending_change_count` 达到 `retrain_label_threshold=20` 时，检查：

1. `latest_snapshot`（最新快照）已更新，且 `sample_count`（样本数）大于旧快照；
2. `latest_snapshot.sources`（快照来源）同时列出历史 `labeled_import`（带标签导入）和 `review`（人工审核物化数据）；
3. `latest_retrain_request.status` 为 `queued`；
4. `latest_retrain_request.dataset_path` 是相对项目根目录的冻结 CSV 路径；
5. `pending_change_count` 已重置为 `0`；
6. 没有自动产生生产发布动作。

推荐检查命令：

```powershell
$state = Invoke-RestMethod "$base/api/iterative-labeling/cumulative-training/state?slot=pv_fault"
$state.latest_snapshot
$state.latest_retrain_request
```

## 8. 字段流转速查表

| 阶段 | 输入字段 | 关键消费位置 | 输出字段/产物 |
|---|---|---|---|
| 历史训练导入 | `dataset_path`、`label` | 累计训练导入 API | 冻结快照、`request_id`（重训请求 ID） |
| 调度拉取 | `station_id="pv"`、`timestamp_utc`、`feature_name`、`value` | `pv_data_pull` | `training_samples.label=NULL` |
| 调度预测 | `model_ref`、游标后的未标注观测 | `pv_prediction` | `PredictionRecord`、`prediction_batch_id`、预测输入 CSV |
| 创建审核 | `loop_id`、`prediction_batch_id` | 审核会话 API | `review_id`、`unit_key`、`prediction_context` |
| 人工裁决 | `unit_key`、`action_type`、`verdict_label` | 裁决 API | `verdict_entries`、物化审核 CSV、`pending_change_count` |
| 阈值重训 | `pending_change_count`、`retrain_label_threshold` | 累计训练服务 | 新 `snapshot_id`、`request_id`，状态 `queued` |

## 9. 交付前人工检查清单

- [ ] 后端、DB 健康检查和 `pv_fault` 调度管线均正常。
- [ ] 所有路径均为相对项目根目录路径；没有写入绝对路径。
- [ ] 训练导入数据含 `label` 且至少两个类别。
- [ ] 预测输入数据不含人工 `label`，并且时间晚于预测游标。
- [ ] 预测批次含非空 `predictions`，每项有设备、窗口、标签和置信度。
- [ ] `confirm`、重复提交、`correct`、`skip` 四条规则均得到预期状态。
- [ ] 阈值触发后仅产生 `queued` 请求；训练和发布必须显式操作。
- [ ] 未创建 `pv_demo` 或 demo 专属账本。

## 10. 当前环境的后续建议

当前 `retrain-791f938b63e8` 仍处于 `queued`。若本轮目标是验证第二份快照可训练，可按 §4.3 显式执行；若目标仅是验证阈值闭环，请保持它为 `queued`，避免额外消耗训练资源。

若要再生成新的预测批次，需要在模拟源表准备**晚于**当前游标的新 `pv` 观测；重复触发同一批已成功预测的数据不会产生新批次，这是游标幂等保护的预期行为。
<!-- @AI_GENERATED: end -->
