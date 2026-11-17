<!-- @AI_GENERATED -->
# 光伏产品融合设计（蓝图 × 天/点双链）

> 文档状态：2026-08-25  
> 适用范围：在 G0–G8 骨架已落地之后，把「四段人机闭环」接到 `pv_day` / `pv_point` 两条产品链上。  
> 权威关系：
>
> - **工作流、点合同、slot、治理、benchmark、replay_activity**：仍以 `design.md` A0–A16 为准。  
> - **产品怎么把打标、确认集、累计训练、日内告警接上双链**：以**本文**为准。若与 `docs/transcript/pv-fault-product-blueprint-2026-08-25.md` 冲突，以本文为准。  
>
> 路径约定：文中仓库路径均相对于项目根目录。

配套文件：

| 路径 | 职责 |
|---|---|
| `docs/specs/pv-fault-realtime-point-path-redesign/design.md` | 天/点双链、算子、回放、快照治理的技术设计 |
| `docs/specs/pv-fault-realtime-point-path-redesign/design-易读版.md` | 上述设计的通俗对照，已叠加本文结论 |
| `docs/specs/pv-fault-realtime-point-path-redesign/requirements.md` | 功能与验收约束；融合增量见文首 0.F |
| `docs/specs/pv-fault-realtime-point-path-redesign/tasks.md` | 可执行任务；G10 起按本文分期 |
| `docs/transcript/pv-fault-product-blueprint-2026-08-25.md` | 静态读码蓝图，只作问题来源，不再当实施真源 |

---

## 1. 一页结论

产品主线是 **`pv_day` 与 `pv_point` 两条槽位链**，不是再做一条 `pv_fault` 语义。  
蓝图里的四段人机闭环要接在这两条链上，但 **只有 ① 打标和 ③ 诊断是工作流**；②④ 仍是专家工作台。

```text
无标签数据
  │ ① 打标工作流（模板 A，按 slot）
  ▼
label_proposal（提案，不能训练）
  │ ② 专家校验工作台
  ▼
LabeledDatasetVersion（确认箱，必带 slot，status=curated）
  │ 纳入该 slot 累计库存
  ▼
slot_dataset_snapshot（盘点版 id@version）
  │ ③ 诊断工作流
  │    pv_day：日级批诊断
  │    pv_point：真实点 train_eval / predict_replay
  ▼
预测批次 / 点 outcome
  │ ④ 专家复核工作台
  └─ 再发布确认箱 → 累计 → 快照 +1 → 显式重训
```

已拍板：

1. **`pv_fault` 降为 legacy**：现网 Champion 只读；新标注、新训练、新告警只进 `pv_day` / `pv_point`。  
2. **日内滚动告警只用 `pv_point`**（真实点 POC + `replay_activity`）。老 TSC / `seq_annotation` 不作为产品路径。  
3. **确认箱必须带 `slot`**；没有 slot 的版本不允许存在。  
4. **不废掉 `slot_dataset_snapshot`**：确认箱是货，快照链是车间库存。

G0–G8 已交付的骨架（slot 执行、`ts_point_*`、治理四动作、benchmark 隔离、点路径中文显示名）继续有效，本文不推倒重来。

---

## 2. 四段闭环：哪些是工作流

| 段 | 名称 | 形态 | 产出 | 禁止 |
|---|---|---|---|---|
| ① | 打标 | **工作流**模板 A | `label_proposal` | 不得写出 `curated` 数据集 |
| ② | 专家校验 | **工作台**（有状态会话） | `LabeledDatasetVersion`（curated） | 机器不得自行升级提案 |
| ③ | 诊断 | **工作流**模板 B（天/点各自己的 train/predict） | 预测批次或点 outcome | 不得读取 `proposal` 或跨 slot 确认箱 |
| ④ | 预测复核 | **工作台** | 新的确认箱 | 不得覆盖历史确认箱或历史快照 |

人工不进画布。画布只负责两个接口：产出提案、消费已确认数据（按版本 ID 或 `snapshot_id@version`）。

现有硬编码 `create_clustering_run()` 在 P0 可保留为快捷模式；P1 用模板 A 替换为可编排打标，REST 只作兼容入口。

---

## 3. 数据对象：确认箱、累计库存、快照

仓库里曾有三套「训练集」并列（老 `CumulativeTrainingService` 袋子、G5 `slot_dataset_snapshot`、蓝图确认箱）。融合后只保留下面两层加一个逻辑库存：

### 3.1 `label_proposal` — 标签提案

- ① 的唯一合法产出。  
- 创建时必须写 `slot`（`pv_day` 或 `pv_point`）。  
- `status`: `pending_naming` → `pending_confirmation` → `confirmed`（confirmed 只表示「可以发布确认箱」，本身仍不是训练输入）。  
- 训练工作流、`load_labeled_dataset`、snapshot builder **读不到**未发布为 curated 的提案。

### 3.2 `LabeledDatasetVersion` — 确认箱

一次专家认账封存的一批真值（聚类确认或预测复核都可以）。

必填：

| 字段 | 含义 |
|---|---|
| `dataset_version_id` | 单调、不复用 |
| `slot` | `pv_day` 或 `pv_point`；隔离真源 |
| `status` | 仅 `curated` 可被 ③ 加载；禁止用 `proposal` 冒充 |
| `file_path` | 项目根相对路径 |
| `content_sha256` | 不可变指纹 |
| `dataset_contract` | 实体键、时间列、测点、标签、窗口键、期望频率 |
| `label_space_version` | 标签空间版本 |
| `provenance` | `proposal_id` 或 `review_session_ids`、parent 版本、确认人/时间 |

隔离规则：

- 登记时 slot 已写死，禁止一箱货同时写两个 slot。  
- `pv_point` 工作流只能加载 `slot=pv_point` 且 `curated`。  
- contract 第二道保险：点是事件点合同，天是设备日合同，对不上预检失败。  
- 跨 slot 只读证据，禁止当天真值、禁止当训练输入。

已有标签、跳过 ①② 的导入：注册时必须选手选 slot，直接 `curated`，再 import 进对应快照链。

### 3.3 累计库存（逻辑概念，不再单独立册表）

该 slot **已采纳的确认箱列表**。不是一份边写边变、直接拿去训练的 CSV。

- 按 slot 分仓。  
- 「纳入累计」是显式动作；复核成功 ≠ 自动入库。  
- 老 `CumulativeTrainingService` 的 `labeled_imports` 袋子，产品上收敛为这份清单；随机 `snapshot-{timestamp}` 不再当训练真源。

### 3.4 `slot_dataset_snapshot` — 盘点版

每个产品 slot 一条稳定链（如 `snap-pv-point`），链内 `snapshot_version` 只增不改。

```text
确认箱 → 纳入累计 → 显式 build → snap-xxx@vN
重训必须写明 snapshot_id@version，禁止隐式 latest
```

四动作仍拆开：build / retrain / verify / Promote。纳入累计、拍快照、重训互不自动触发。

**预测 + 人工校验完走哪？** 先出确认箱，再纳入该 slot 累计，再拍快照。不是二选一。

---

## 4. 模板怎么接

### 4.1 模板 A（打标，P1）

画布 DAG，按 slot 各一张或一张图换 profile：

```text
load → 切单元 → 清洗 → 特征 → 标准化 → 降维 → 聚类 → 簇画像 → emit_label_proposal
```

- 点打标产出 `proposal.slot=pv_point`；天打标产出 `pv_day`。  
- 需要补的算子：`emit_label_proposal`、`cluster_profile`；`cluster_k_search` 可后补。  
- 打标会用到的命名孪生（`kmeans` / `pca` 等）在 P0 货架对齐里修掉。  
- 蓝图所列 `gmm_cluster` 等现货优先用；不要把分组键焊死在 Python 里。

### 4.2 模板 B（诊断，已有）

| slot | 训练 | 预测 |
|---|---|---|
| `pv_day` | `workflow-pv-day-train-eval-v1` | `workflow-pv-day-predict-v1` |
| `pv_point` | `workflow-pv-point-train-eval-v1` | `workflow-pv-point-predict-replay-v1` |

P1 补两个接口算子：

- `load_labeled_dataset`：按 `dataset_version_id` 或 `snapshot_id@version` 加载，带出 `dataset_contract`，换数据不再改 7 个节点。  
- `emit_prediction_batch`（天）/ 点路径投影 `annotation_candidate`：让 ③ 的预测进入 ④。

③ 只读 curated + 同 slot。

---

## 5. 点路径喂数与日内滚动告警

保留并升级 `replay_activity`，不要另做一套「告警喂数」。

| 层 | 职责 | 现状 |
|---|---|---|
| 喂数时钟 | 下一个真实点何时进入、cursor 在哪 | `replay_activity`（文件水位） |
| 冻结 graph | 当前点怎么判 | `predict_replay` |
| 告警状态机 | 一串 outcome 如何告警/去重/消警 | **未建**，P2 新建 |

```text
点到达（文件回放 → 日后日内 tick / 采集）
  → replay_activity 放出 pending 点
  → 同一张 predict_replay
  → outcome
  → 告警状态机（P2）
```

- P0/P1：文件回放必须保留，作为因果验收和告警状态机的压缩时间现场。  
- P2：同一套 activity，源改为库内「该实体未处理的新真实点」（5/15 分钟）。  
- 真采集（原 G9）再换源，不换图、不换 cursor 语义。

**不要用的喂数：** `pv_fault` Mock 按业务日整设备释放（`services/db/datasources/pv_fault_mock.py`）只服务天路径到达/遗产，不给点告警用。

**不要用的模型路径：** `seq_annotation` / TSC 滑窗 / 整日 288 槽。可只读对照，禁止新产品开发和日内告警复用。

天路径继续以设备日到达/封账驱动 `pv_day.predict`，与点告警分槽。

---

## 6. 与蓝图清单的映射

蓝图 5.x 编号不直接当任务号。采纳与否：

| 蓝图项 | 融合后 |
|---|---|
| 聚类确认后画布能选数据集 | **P0**，做成带 slot 的确认箱 + 画布可选 |
| 聚类标准化 / 禁止 ID 列当特征 | **P0** 快捷路径先修；模板 A 后由用户选算子 |
| 打标模板化、k 选择、簇波形 | **P1** |
| `LabeledDatasetVersion` 统一 | **P0 最小对象 + slot**；P1 补 contract 下发 |
| 累计训练随机 snapshot | **收敛到 `slot_dataset_snapshot`** |
| `load_labeled_dataset` / `emit_prediction_batch` | **P1** |
| 货架空壳、命名孪生、连线校验 | P0 只修打标依赖的孪生；其余 P3 |
| 生产 simple 切换 / 写接口鉴权 | **P3**（安全），不挡 P0 故事 |
| 第三条路径用 TSC | **否**，改 `pv_point` |
| 拆 `workflows_enhanced.py`、清重复页 | **P3** |

---

## 7. 分期（G10 起）

G0–G8 已完成骨架，不再重开。后续：

### G10 — 接缝（P0 故事）

目标：专家确认过的数据能进对的槽位；画布能**分别**选确认箱和累计盘点版去训练。

1. 最小 `LabeledDatasetVersion`（必带 `slot`、`curated`、路径、指纹、血缘）。  
2. 聚类 `confirm` 发布确认箱，并注册画布 `kind=labeled_version`（不自动纳入累计）。  
3. 「纳入累计」+ snapshot build 后再注册 `kind=cumulative_snapshot`（`snap-{slot}-v{n}`）；确认箱行保留。  
4. `load_csv` 下拉列出当前 slot 的**全部**确认箱和**全部**累计版本（历史+最新，均可训）；选中写入该项冻结 `file_path`。  
5. 提案门最小集：未 confirm 不得训练。  
6. 命名孪生优先四个聚类/降维算子。  
7. 快捷聚类：z-score + 禁止 ID 列当特征。  
8. 确认后跳转训练模板并带 `dataset_id`。

退出：下拉里能分别选「这一箱」和「累计 vN」；点训练读不到天条目；现有 `pv_point` execute-async 不被破坏。

### G11 — 打标工作流 + 诊断只吃确认数据（P1）

1. 模板 A + `emit_label_proposal` / `cluster_profile`。  
2. `load_labeled_dataset` + contract 下发（减少逐节点改列）。  
3. 天：`emit_prediction_batch`；点：候选投影进 ④。  
4. 旧聚类 REST 降为快捷模式。

退出：无标签 → 模板 A → 提案 → 确认箱 → `pv_point` 或 `pv_day` 训练，全程不手抄路径。

### G12 — 点路径日内滚动告警（P2）

1. 告警状态机接在 `replay_activity` 的 outcome 后。  
2. 喂数源从文件扩展为日内未处理真实点。  
3. 正式采集仍可后置，不挡告警演示。

退出：文件回放上能演示告起来/去重/消警；改未来点不影响当前点窗口。

### G13 — 平台卫生与遗产（P3）

货架 `implementation_status`、连线类型校验、simple 切换守卫、鉴权、`pv_fault` 只读说明、TSC 只读、重复页面。不与 G10 故事绑死。

---

## 8. 验收口径（融合后新增）

在原 P0a/P0b 之上，G10 起必须还能回答：

1. 提案能否被训练工作流加载？（必须不能）  
2. 确认箱有没有 `slot`？点图能否加载天确认箱？（必须不能）  
3. 复核完是直接改一份可变累计 CSV，还是确认箱 → 累计清单 → 快照版本？（必须是后者）  
4. 重训是否写死 `snapshot_id@version`？  
5. 点告警是否另做 TSC/288 网格？（必须不是）  
6. `replay_activity` 是否仍是点时钟，告警是否只消费 outcome？

---

## 9. 明确不做

- 把 ②④ 做成画布节点。  
- 天模型与点模型互相 Promote。  
- 日标签广播到点、点框选写回天。  
- benchmark 写入产品确认箱 / 快照 / registry。  
- 为融合推倒 G0–G8 的 slot 执行与 `ts_point_*`。  
- 用 `pv_fault` Mock 整日喂数冒充点实时。  
- 只往画布注册「当前累计 CSV」、训练时隐式读 latest。  
- 用 TSC / `predict_device_window` / 288 槽实现日内告警（蓝图 5.8 第 22 条作废）。

---

## 10. 确认箱和累计集如何同时拿去训练

蓝图 5.1 说「confirm 时注册进画布下拉」。这只对了一半：画布 `load_csv` 现在主要吃 `file_path`，注册表是 `POST /api/workflows-enhanced/datasets/register` 那份 AutoResearch 清单，和累计训练互不通信。融合后的目标是：**确认箱、累计盘点版各是一条可选训练输入，都带 slot，都是不可变文件。**

### 10.1 下拉列出当前槽位的全部历史 + 最新（两类都可训）

`load_csv`（以及日后的 `load_labeled_dataset`）在**当前工作流 `slot`** 下必须同时列出：

1. **该槽位全部确认箱**：每一个 `status=curated` 的 `LabeledDatasetVersion`（历史每一箱 + 最新一箱）。  
2. **该槽位全部累计盘点版**：`slot_dataset_snapshot` 链上每一个已发布版本（v1…vN，含最新）。

每一行都是冻结文件，**都可以直接拿去训练**。没有「只能训最新」的限制。

| 分组（下拉里用分组，不要混成一堆无标签路径） | 展示名示例 | 选中后训练什么 |
|---|---|---|
| 确认箱 | `确认箱 · lds-… · 2026-08-25 聚类确认`（最新打标） | **仅这一批**真值 |
| 确认箱 | `确认箱 · lds-… · 2026-08-20 复核回流` | 历史某一批，可复现实验 |
| 累计训练 | `累计 · snap-pv-point@v3（最新）` | 纳入到 v3 为止的全部真值 |
| 累计训练 | `累计 · snap-pv-point@v2` | 历史盘点，复现当时重训 |

排序：组内**最新在上**；最新项加「最新」标记，但历史项不得隐藏、不得灰掉、不得改指向最新文件。

禁止：

- 只展示 latest 确认箱或 latest 累计。  
- 一个「当前累计」别名，选完读可变拼盘。  
- 新版本覆盖旧注册行的 `file_path`。  
- 点槽位下拉里出现天槽位的箱/快照（反之亦然）。

### 10.2 两类输入都能训，职责不同

| 用户选什么 | 本质 | 画布 `dataset_id` | 文件 |
|---|---|---|---|
| 任意一版确认箱 | `LabeledDatasetVersion` | `lds-{slot}-{dataset_version_id}` | 该箱相对路径，永不改 |
| 任意一版累计 | `snapshot_id@version` | `snap-{slot}-v{n}` | 该版本快照相对路径，永不改 |

- 选确认箱 = 只用那一批（冷启动、对照某次审核）。  
- 选累计 vN = 该槽位累计到 vN 的全集（正式重训/复现）。  

刚 confirm、尚未纳入累计时：下拉里已有确认箱，可以立刻训；累计组可能仍只有更早的 v1 或为空。纳入并 build 出 vN 后，累计组**多一行**，历史确认箱和历史累计行全部保留。

### 10.2 confirm 时做三件事（不是只 register 一次）

`confirm_clustering_run()`（以及日后预测复核成功）顺序固定：

```text
1. 写不可变 labeled CSV（已有）
2. 发布 LabeledDatasetVersion（slot 必填，status=curated）
3. 画布注册确认箱一行（kind=labeled_version）
4. 不自动纳入累计、不自动拍快照、不自动重训
```

「纳入累计」是独立按钮/API：把该确认箱加入该 slot 累计清单 → 用户再显式 build `slot_dataset_snapshot` vN → **再**往画布注册/更新一行 `kind=cumulative_snapshot`（新版本新 ID，旧 vN-1 行保留）。

这样：刚确认就能选确认箱训练；点了纳入并拍盘后，下拉里**多出**累计 vN，确认箱那一行还在。

### 10.3 画布怎么选（G10 最小实现）

现状：`PropertyPanelV2` 的 `load_csv` 是手填 `file_path`；`GET /datasets` 是另一张注册表，DatasetPage 确认后并不调用 `register`。

G10 做法：

1. 扩展注册表条目字段（相对路径）：`kind`、`slot`、`ref_id`（确认箱 ID 或 `snapshot_id@version`）、`trainable=true`。  
2. `load_csv`「训练数据」下拉：当前 `slot` 下 **全部历史 + 最新** 确认箱，以及 **全部历史 + 最新** 累计快照版本；分组展示，最新在上并标「最新」；每一项 `trainable=true`，选中写入该项自己的冻结 `file_path` + `dataset_id`。  
3. 点工作流下拉看不到 `slot=pv_day` 的确认箱/快照。  
4. 跳转：确认成功后按钮  
   ` /algorithm-dev/workflow-editor/{trainWorkflowId}?slot=pv_point&dataset_id=lds-pv_point-… `  
   编辑器打开时把该 `dataset_id` 填进 `load_csv`。累计训练入口同理带 `dataset_id=snap-pv_point-v2`。

G11 再换成 `load_labeled_dataset`（按 ID 加载 + contract）。G10 不阻塞：确认箱文件已是带 `label` 的表，现有 `load_csv` 能训。

### 10.4 和老累计袋子的关系

`CumulativeTrainingService.register_labeled_dataset` 继续可写，但**不再作为画布训练真源**。画布只认确认箱行和 `slot_dataset_snapshot` 行。老 `snapshot-{timestamp}-{uuid}` 不进下拉。

---

## 11. 蓝图 5.1–5.9 逐条裁决

来源：`pv-fault-product-blueprint-2026-08-25.md` 第 5–6 节。静态读码结论实施前仍须按该文档第 6 节自验（空壳数量、孪生是否同义、是否另有同步路径、portTypeValidation 是否仍未被 import、双路径 Task 2–11 完成度）。

| # | 蓝图项 | 裁决 | 落在 |
|---|---|---|---|
| 1 | confirm 后画布能选 | **做**。按 §10：先确认箱行，累计另开一行 | G10 |
| 2 | 「去画布诊断」按钮 | **做**。跳训练模板 + `dataset_id`；默认 `pv_day` 天模板 / 点确认箱走 `pv_point` 训练模板 | G10 |
| 3 | 聚类标准化 + 禁止 ID 列当特征 | **做**（快捷路径） | G10 |
| 4 | `cluster_k_search`；前端去掉写死 k=5 | **做**，但是算子+模板，不是继续焊在 REST 里 | G11 |
| 5 | 簇波形 / `cluster_profile` | **做** | G11；G10 快捷路径可先复用 `GET /reference-waveforms` 挂代表成员 | 
| 6 | `_switch_simple` 环境守卫 + 前端改走九项门控 | **做** | G13；实施前先核对 `pv-fault-dual-path-serving` Task 2–11 真实完成度 |
| 7 | modeling-paths / register-model / switch-fallback 鉴权 | **做，需你显式授权后再改写接口** | G13 |
| 8 | 货架 `implementation_status` 动态标注 | **做** | G13；G10 只保证孪生那几个能拖 |
| 9 | 15 个命名孪生 | **做**。优先 `kmeans`/`dbscan`/`agglomerative_clustering`/`pca`。`classification_report`↔`confusion_matrix_eval` 先读码再决定是否对齐 | G10 四个优先；其余 G13 |
| 10 | 启用 `portTypeValidation` | **做** | G13 |
| 11 | 三套数据集收成确认箱+快照链 | **做**。不是收成「只有一张表一个 ID」；见 §3 与 §10 | G10–G11 |
| 12 | confirm 也分配 `dataset_version_id` | **做**。格式与 backfill 对齐（如 `lds-r{seq}-{timestamp}` 或统一 `lds-{slot}-{hex}`，两路同一分配器） | G10 |
| 13 | `_PROMOTED_FIELDS` 下发实体/时间/测点/标签 | **做** | G11（与 `dataset_contract` 一起） |
| 14 | `datasets/switch` 校验 contract | **做** | G11 |
| 15 | PV `data_contracts` 四条 | **做** | G11 |
| 16 | `cluster_k_search` / `cluster_profile` / `emit_label_proposal` | **做** | G11 |
| 17 | 模板 A | **做** | G11 |
| 18 | REST 快捷模式保留 | **做** | G10 修算法；G11 默认仍可走 REST |
| 19 | `load_labeled_dataset` / `emit_prediction_batch` | **做** | G11 |
| 20 | backfill 非预测入口 | **做** | G11（聚类确认箱回流不必再要求 from-prediction） |
| 21 | 簇级→单元级精修 | **做** | G11；G10 不挡「先整簇确认就能训」 |
| 22 | 合并 DatasetPage / IterativeLabeling 两套聚类 UI | **做** | G11 |
| 23 | `predict_device_window`（seq_annotation） | **不做**。日内滚动用 `replay_activity` | G12 |
| 24 | 告警状态机 | **做**，接在点 outcome 后 | G12 |
| 25 | 与全天复盘对账（seq ledger） | **改**。不复用 TSC 账本当产品真源；点告警修订记在 `pv_point` evidence。老 ledger 只读对照 | G12 |
| 26 | 生产采集 / MQTT 空壳 | **后置** | G12 可用文件回放演示；真采集并入原 G9 |
| 27 | 拆 `workflows_enhanced.py` | **做** | G13 |
| 28 | spec 三份副本 | **做** | G13；当前真源是本目录 `fusion-design.md` + `design.md` |
| 29 | 前端 IA 瘦身 | **做** | G13 |
| 30 | precision_ops vs accuracy_operations | **做** | G13 |
| 31 | 对齐历史 spec 勾选 | **做** | G13；TSC 标 legacy，不把它勾成点路径完成 |

蓝图第 6 节验证边界：G10 开工前用一次实机聚类 confirm + 画布 `GET /datasets` 核对「两套注册表不通」是否仍成立；货架孪生先对 `kmeans` 读两侧代码再改 ID。

<!-- @AI_GENERATED: end -->

