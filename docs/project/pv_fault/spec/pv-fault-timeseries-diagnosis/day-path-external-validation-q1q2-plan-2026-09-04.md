<!-- @AI_GENERATED -->
# 光伏天路径 · 外部数据集通用性验证方案（Q1/Q2 两层）

> 文档状态：验证方向已确认，尚未进入代码实现
> 日期：2026-09-04
> 适用槽位：`pv_day` — 光伏天路径（RandomForest 统计特征基线）、`pv_tsc` — TSC 时序分类（MultiRocket 滑窗投票）
> 不适用范围：`pv_point` — 光伏实时点路径（另见点路径标签收敛设计）
> 关联文档：
> - `../pv-fault-realtime-point-path-redesign/point-label-space-convergence-design-2026-09-03.md` — 点路径双层标签与 UTFPR 接入设计（本文件的并列姊妹篇，点路径走"提升"路线 B）。
> - `tsc-platform-integration-plan.md` — TSC 作为第三条 `modeling_path` 接入平台的内部累计训练闭环方案（讲"训练→检测→打标→回流"，不是本文件讲的"外部集验证"）。

---

## 1. 先看结论

1. **天路径当前走"验证通用性"路线 A，不是"提升精度"。** 目标是证明产品设计在陌生电站上成立，不为把 macro-F1 再抬高一点。
2. **验证拆成 Q1、Q2 两层，分层依据是"想证明产品的哪件事"，不是"训练还是预测"，也不是"真值回不回流"。**
   - **Q1 = 检测 / 管道通用性**：搬到陌生电站能跑通全流程，且"这天正常 / 异常"判得准。核对靠物理量（发电量、性能比 PR、`i_cal` 残差），**不需要故障类型金标**。
   - **Q2 = 分类通用性**：不仅说"异常"，还说"短路 / 遮挡 / 开路"，且类型说得对。核对**必须有故障类型金标**。
3. **两层必须用不同数据集，因为"多设备 ⊕ 带类型标注"没有单一公开集能同时满足。** 多设备无标注的真实数据很多（PVDAQ / DKASC），带类型标注的又少又设备单一（UTFPR / Réunion）。
4. **"训练 vs 预测"是与 Q1/Q2 正交的另一根轴。** Q1、Q2 都可以选"直接拿现有天模型预测外部站（不重训）"或"用外部数据重训走一遍流程"。关键在核对对象是"异常与否"还是"故障类型"，不在训练还是预测这个动作。
5. **验证必须外挂独立真值，禁止让管道自造 gold。** 已核实 `real_model_detect.py` 的检测桥在 gold 缺失时会用预测值顶替真值（`truth = int(pred)`），外部无标签数据若走这条桥会得到虚高到假的精度。Q1 的真值来自物理规则，Q2 的真值来自数据集自带标签，任何一层都不允许用模型自己的预测当答案。
6. **外部验证走独立"日级 benchmark 路径"，与产品治理隔离。** 复用 `tsc_sliding_window` 切窗 + `tsc_train_eval` / `pv_day` 统计特征评估，只换数据画像；`execution_purpose=benchmark_reuse`（执行用途：基准复用）、`governance_eligible=false`（不允许写产品治理登记），不写 `label_registry.json`，不 Promote，不污染 `pv_day` / `pv_tsc` 生产模型。

---

## 2. Q1 与 Q2 的本质区别

### 2.1 一句话定义

| 维度 | **Q1：检测 / 管道通用性** | **Q2：分类通用性** |
|---|---|---|
| 证明什么 | 能跑通全流程 + "异常挑得准" | "故障类型分得对" |
| 对应模型输出 | 折叠成二分类：正常(0) / 异常(≠0) | 完整多分类：13 类 / 10 类故障类型 |
| 核对用的真值 | 物理推出（`i_cal` 残差、性能比 PR、发电量、停机记录） | 数据集自带的故障类型标注（金标） |
| 需要类型标注吗 | **不需要** | **必须要** |
| 这类数据多不多 | 多（多设备无标注真实数据到处都是） | 极少，且设备单一 |
| 首选数据集 | NREL PVDAQ / DKASC | UTFPR / Réunion |

### 2.2 为什么必须分开

分开的根因只有一条：**没有一个公开数据集能同时满足"多设备"和"带故障类型标注"。**

- 想验"检测 + 管道通用"，需要**多设备、多站点**来证明不是只在一个电站碰巧能跑；这类数据不需要类型标注，因为"正常 / 异常"能从物理量一眼核对 —— 于是数据很多。
- 想验"分类通用"，需要**故障类型金标**来核对"短路"说得对不对；这类标注要么靠实验台造、要么靠专家标，于是数据又少、覆盖的设备又单一。

因此只能两条腿分头验：Q1 用多设备无标注集，Q2 用带标注但设备少的集。

### 2.3 与两个易混概念的界线（务必澄清）

- **"训练→预测"不是 Q1/Q2 的分轴。** 它是正交的实施选择：
  - *predict-only（不重训）*：直接拿现有 `pv_day` / `pv_tsc` champion 模型去预测外部站，看域外表现。
  - *retrain（重训走流程）*：用外部数据重新切窗训练，验证"换个电站，整条训练链路也能落地"。
  - Q1 和 Q2 都可以任选其一。判定属于 Q1 还是 Q2，只看"核对的是异常与否，还是故障类型"。
- **"真值回流"不属于本方案。** 真值回流 = 闭环打标（把预测结果人工确认后回灌训练集），属于**提升模型**的范畴（点路径路线 B 那条线），与"验证产品能否通用"是两码事，不要混进 Q1/Q2。

---

## 3. 天路径现状（已核实代码事实）

以下是写本方案时逐文件核实的事实，作为 benchmark 路径设计与适配点的依据。

### 3.1 两个天路径模型与其数据契约

| 模型 | 槽位 | 训练算子链（train_eval 模板） | 关键契约 |
|---|---|---|---|
| RandomForest 统计基线 | `pv_day` | `load_csv → time_window_split(1d) → handle_missing → detect_outliers → [extract_statistical_features / tsfresh_extract / ts_comparison_features] → stratified_cv_eval` | 按 `(site_id, device_id, branch_id, date)` 分组，在 `value`+`i_cal` 上算 **50 个**统计特征（每列 25 个）；`stratified_cv_eval` 用 `group_col=group_key` 做无泄漏重复分层留出 |
| MultiRocket 时序分类 | `pv_tsc` | `load_csv → tsc_sliding_window → tsc_train_eval` | 见下 |

TSC 切窗契约（`SamplerConfig` 默认值，来自 `backend-service/services/iterative_labeling/tsc/sliding_window_sampler.py`）：

| 参数 | 中文含义 | 默认值 |
|---|---|---|
| `window_length` | 窗口点数（288 = 1 天 @ 5min 采样） | 288 |
| `stride` | 滑动步长（72 = 6h，75% 重叠） | 72 |
| `channels` | 输入通道列 | `["value", "i_cal"]` |
| `series_keys` | 序列主键（唯一标识一条连续物理时序） | `["site_id", "device_id", "branch_id"]` |
| `label_strategy` | 窗口级标签聚合策略 | `"majority"`（众数） |
| `purity_threshold` | 众数占比低于此值的窗口丢弃 | 0.7 |
| `min_coverage` | 窗口内非 NaN 最低比例 | 0.9 |
| `min_std` | 首通道最小标准差（剔除常数 / 全零窗，防泄漏） | 0.0（模板里评估用 1e-6） |
| `max_gap_multiplier` | 时间缺口检测倍数，超过则断段、只段内滑窗 | 2.0 |
| `normal_label` | 正常类标签值 | 0 |

设备隔离：`data_loader.py::split_by_device` 用 `GroupShuffleSplit` 按 `device_id` 分组切 train/test（`test_ratio=0.2`, `random_state=90`），并有"同设备不得跨集"的泄漏断言。`tsc_train_eval` 走 strict 多重隔离（日期 × 设备 × 重复窗口），`n_repeats=10`、`n_test_days=3`、`held_device_ratio=0.3`。

### 3.2 数据入口与相对路径

- `load_csv` 算子（`backend-service/services/operator_backends/load_csv.py`）：
  - `file_path` — 数据路径。相对路径会依次在 `[workspace_root, aip_dir, backend_dir, cwd]` 搜索，符合项目"相对路径"红线。
  - `rename_columns` — 列改名映射（dict 或 JSON 字符串），只重命名实际存在的列。天路径模板已用它把 `data_date→time`、`branch→branch_id`。**这是外部集对齐 schema 的主要抓手。**
  - 支持 `.parquet` / `.csv` / `.xlsx`。
- TSC 侧 `data_loader.py::_resolve_dataset_path` 也做相对路径搜索（`project_root → backend_dir → cwd`）。
- 天路径 train_eval 模板描述明确："换数据只需改两个 load 节点的 `file_path`。"

### 3.3 现有 benchmark 槽位（点路径拓扑，不是天路径）

前端 `frontend-sevice/src/config/slotProductConfig.ts` 定义了 3 个 benchmark 槽位：`benchmark_nasa_smap_msl`、`benchmark_fhc_twin_plant`、`benchmark_pvdaq_system683`。核实结论：

- 三者 `executionPurpose='benchmark_reuse'`（执行用途：基准复用，非产品工作流）、`governanceEligible=false`（不写产品治理登记），且都走**点路径 `ts_point_*` 拓扑**：`benchmark_fhc_twin_plant` / `benchmark_pvdaq_system683` 的 `trainWorkflowId` 直接指向 `workflow-pv-point-train-eval-v1`；`benchmark_nasa_smap_msl` 用源替换变体 `workflow-benchmark-nasa-point-train-eval-v1`（其描述写明"Same ts_point_* chain as pv_point"，只把数据源换成 `load_nasa_npy_channels`）。后端测试 `test_g6_reuse_report.py` 进一步断言这些 benchmark 槽位解析出的训练模板 / 图签名与 pv_point 点路径一致。
- 数据是**占位 fixture**：如 `data/timeseries_point/test_fixtures/pvdaq_system683_demo.csv` 仅 10 行，列为 `timestamp,system_id,dc_voltage,dc_current,ac_power,module_temp,irradiance` —— **不是 pv schema**（无 `value`/`i_cal`/实体键）。
- `benchmark_pvdaq_system683` 的 `label_space_ref=null`（无标签），正好对应 Q1；`benchmark_fhc_twin_plant` 挂 `fhc_anomaly_class_0_9`，`benchmark_nasa_smap_msl` 挂 `benchmark_anomaly_binary`。

**结论：现有 benchmark 全部是点路径拓扑，天路径（TSC / RF）上还没有对应的 benchmark 路径 —— 这正是本方案要新开的。**

### 3.4 标签登记（只读，禁止改动）

`backend-service/data/iterative_labeling/label_registry.json`：`default` / `pv_fault` / `pv_day` 均为 `ls-v2` 13 类（0,1,2,3,4,6,7,8,9,10,11,12,16）；`pv_tsc` 为 `ls-v2` 但只有 10 类（缺 9/10/16）。本方案**不新增、不修改任何 registry 类别**。

---

## 4. Q1 验证方案（检测 / 管道通用性）

### 4.1 要证明的命题

> 把天路径搬到从未见过的电站，(a) 全流程能吃数据、切窗、评估跑到底不报错；(b) "这天正常 / 异常"的判断，与物理量推出的真值一致。

### 4.2 数据集（多设备、无类型标注）

| 数据集 | 来源 | 为什么适合 Q1 | 备注 |
|---|---|---|---|
| **NREL PVDAQ**（首选） | OEDI 开放，工具 `NREL/pvdaq_access` | 多系统、原生 daily parquet、含辐照度 / 温度，摩擦最低；已有 `benchmark_pvdaq_system683` 槽位占位 | 无故障标签 → 只能验 Q1 |
| **DKASC** | dkasolarcentre.com.au | 22 技术多系统多年、分钟级可选、含气象 | 免费开放，多设备覆盖强 |
| **Ani Kannal**（备选） | Kaggle `anikannal/solar-power-generation-data` | 2 厂 × ~22 逆变器、34 天 15min、DC/AC 功率 + 辐照度 / 温度 | 无故障标签，采样 15min 需重采样或调 `window_length` |

> 上述数据集特征来自既有调研结论（handoff §6），本方案未重新联网核实；下载后须按 §6 复核真实 schema 与采样率。

### 4.3 真值怎么来（物理，不需人工标注）

Q1 的"正常 / 异常"真值从物理量推，候选规则（至少满足一条，多条一致更可信）：

- **性能比 PR（Performance Ratio）**：实际功率 / 理论功率明显偏低且持续 → 异常日。
- **`i_cal` 残差**：`value`（实测电流）显著低于 `i_cal`（理论电流，可由辐照度 + 组件温度推算），持续偏离 → 异常日。
- **发电量骤降**：同设备历史基线或同站兄弟设备横比，单日发电量异常低。
- **停机 / 运营记录**（若数据集附带）：直接作为异常日真值。

这些规则产出的是**日级二分类真值**，与模型输出折叠后的二分类对齐比较。

### 4.4 怎么跑

1. 外部数据经 §6 适配（列映射 + `i_cal` 推算 + 实体键注入 + 重采样）落成 `pv` schema 的 parquet。
2. 二选一：
   - *predict-only*：加载现有 `pv_day` / `pv_tsc` champion，直接对外部站预测。
   - *retrain*：在外部数据上重新切窗训练，验证训练链路可落地。
3. 把模型日级输出折叠为二分类：`normal(0)` vs `abnormal(≠0)`。
4. 与 §4.3 物理真值对齐，算二分类指标。

### 4.5 判据（`evaluation_contract` — 评测量约，固定的"尺子"，独立于被测模型）

以二分类为准，报告：`recall_abnormal`（异常召回，漏报控制）、`precision_abnormal`（异常精确，误报控制）、`balanced_accuracy`、`pr_auc`（对类别不平衡稳健）。管道层还要报：能否读入、切窗后有效窗口数、跑完无异常退出。

**Q1 通过 = 管道在 ≥N 个外部设备上跑通，且二分类关键指标（如 balanced accuracy）达到事先约定阈值。** 具体阈值在实施时按数据集难度设定，不在本文件写死。

---

## 5. Q2 验证方案（分类通用性）

### 5.1 要证明的命题

> 天路径在别人的数据上，不仅能发现异常，还能把"短路 / 遮挡 / 开路"等**类型**分对。

### 5.2 数据集（带类型标注、设备少）

| 数据集 | 来源 | 标注 | 关键限制 |
|---|---|---|---|
| **UTFPR**（锁定评测锚点） | clayton-h-costa / Lazzaretti，5kW 并网，`.mat` | `f_nv`：0 正常 / 1 短路 / 2 退化 / 3 开路 / 4 遮挡 | 缺 `i_cal` 列、`.mat` 格式、采样非 5min、**仅 2 组串** → 只能当域外锚点测试集，不能当训练集 |
| **Réunion 屋顶 PV** | HAL `hal-04126493` | 正常 + 遮挡 + 气象（热带、单站） | 单站，类型只覆盖遮挡 vs 正常 |
| GPVS-Faults（排除） | Mendeley `n76t439f65` | 带标签 | 高频 kHz、实体少，与 5min 天路径口径差太远，暂排除 |

### 5.3 UTFPR 标签 → registry 映射

UTFPR 的 `f_nv` 可映射进 `pv_tsc` 的 10 类空间（**只做评测映射，不改 registry**）：

| UTFPR `f_nv` | 含义 | 映射到 registry ID | 说明 |
|---|---|---|---|
| 0 | 正常 | 0 正常 | — |
| 1 | 短路 | 12 组串短路 | — |
| 2 | 退化 | 4 直流侧异常 | 语义近似，下载后须复核；存疑则暂归审计不计入主指标 |
| 3 | 开路 | 11 组串开路 | 注意：点路径 gold 里 11 的物理 signature 与"开路"矛盾（见点路径设计 §5），但 UTFPR 是实验真值，可作为 11 的独立校验 |
| 4 | 遮挡 | 1 组串遮挡 | — |

> `f_nv` 的具体编码语义须在下载 UTFPR 后核实（见 §6、待办 §8-2）；上表编码顺序来自 handoff，未联网复核。

### 5.4 Q2 的诚实边界（重要）

用这些公开集，Q2 只能**部分**验证，不要声称"分类通用性已全面证明"：

- **UTFPR 仅 2 组串** → 无法做设备隔离交叉验证（`GroupShuffleSplit` 需要多设备）。只能作为**域外锚点测试集**：拿现有模型预测 UTFPR 天窗，看类型混淆矩阵；或做留一故障段外推，不能宣称设备泛化。
- **Réunion 单站** → 只能验"遮挡 vs 正常"，且只在热带单站域。
- 因此 Q2 的结论口径应是"在 UTFPR 短路 / 开路 / 遮挡 / 退化上、在 Réunion 遮挡上的域外类型可分性"，而非"全 13 类通用"。

### 5.5 判据

报告每类 `precision` / `recall` / `F1` + 混淆矩阵 + `macro_F1`；测试集**始终锁定**，不参与阈值 / 早停 / 模型选择（与点路径外部真值门禁一致）。

---

## 6. 外部集适配点（共性改造）

无论 Q1 还是 Q2，外部集进天路径前都要过这几关。核心抓手是 `load_csv.rename_columns` + 一个前置转换脚本（临时脚本，用完即删）。

| 适配项 | 做什么 | 落点 |
|---|---|---|
| **列名对齐** | 把外部列映射到 `time` / `value`（实测电流或功率）/ `i_cal`（理论）/ `site_id` / `device_id` / `branch_id` / `label` | `load_csv.rename_columns`（JSON 字符串） |
| **`i_cal` 推算** | 外部集通常没有 `i_cal`。由辐照度 + 组件温度 + 组件参数推算理论电流 / 理论功率，**记录公式版本与参数来源** | 前置转换脚本；ratio 只作物理证据，不单独定标签 |
| **实体键注入** | 单站 / 单逆变器数据要人工注入 `site_id` / `device_id` / `branch_id`，否则 `series_keys` 分组失败、设备隔离退化 | 前置转换脚本 |
| **重采样 / 改窗** | 采样非 5min（如 PVDAQ daily、Kannal 15min）→ 重采样到 5min，或按数据集实际采样率把 `window_length` 从 288 改成"一天的点数" | `tsc_sliding_window.window_length` 参数化 |
| **格式转换** | UTFPR `.mat` → parquet | 前置转换脚本 |
| **落成 parquet** | 转换结果存到项目相对路径，供 `load_csv` 读取 | 建议 `backend-service/data/slot_datasets/<benchmark_slot>/`（相对路径） |

关键红线：**`i_cal` 推算属于半仿真，存在 sim2real 风险**（外部集缺电压 / 辐照度时更甚）。推算口径必须显式记录，且不能让 ratio 单独决定 Q2 的类型标签（类型金标只来自数据集自带标注）。

---

## 7. 日级 benchmark 路径设计

### 7.1 为什么要单独开一条

现有 benchmark 槽位是**点路径**拓扑（复用 `ts_point_*`），产出粒度是逐点，不是天窗投票。天路径验证要复用的是 `tsc_sliding_window`（288 窗）+ `tsc_train_eval`（或 `pv_day` 的统计特征链），拓扑不同，所以要新开"日级 benchmark 路径"，而不是往现有点路径 benchmark 里塞。

### 7.2 设计（与产品治理隔离）

沿用现有 benchmark 隔离机制，新增指向**天路径 / TSC 工作流**的 benchmark 槽位：

| 字段 | 中文含义 | 取值 |
|---|---|---|
| `slot` | 槽位标识 | 如 `benchmark_pvdaq_day`（Q1）、`benchmark_utfpr_day`（Q2） |
| `trainWorkflowId` | 训练模板 ID | `workflow-pv-tsc-train-eval-v1`（或 `workflow-pv-day-train-eval-v1`） |
| `predictWorkflowId` | 预测模板 ID | `workflow-pv-tsc-predict-v1`（或 `workflow-pv-day-predict-v1`） |
| `executionPurpose` | 执行用途 | `benchmark_reuse`（基准复用，非产品工作流） |
| `governanceEligible` | 是否允许写产品治理登记 | `false` |
| `datasetProfileId` | 数据集画像 ID | 指向新建的天路径 benchmark 画像 |

隔离红线（与现有 benchmark 一致）：

- 不写 `label_registry.json`，不新增类别。
- 不写产品治理登记（不 Promote、不改 `pv_day` / `pv_tsc` 的 champion / registry）。
- 不伪造 `benchmark_ground_truth`：Q1 真值来自物理规则文件，Q2 真值来自数据集标注，都独立于模型输出。

### 7.3 需要落地的触点（实施清单）

> 以下前端配置已核实存在；后端 benchmark 槽位解析（`resolve_train_workflow_id`、`TimeseriesProfileStore`、benchmark 治理门禁）只核实了测试与画像 JSON 的存在，**未逐行读实现**，实施时需先补读再动手。

| # | 触点 | 文件（相对路径） | 动作 |
|---|---|---|---|
| 1 | 前端槽位类型与配置 | `frontend-sevice/src/config/slotProductConfig.ts` | 新增天路径 benchmark 槽位（`BenchmarkSlot` 联合类型 + `BENCHMARK_SLOT_CONFIG`） |
| 2 | 数据集画像三件套 | `backend-service/data/timeseries_profiles/{domain,dataset,manifests}/` | 为新 benchmark 槽位建 domain / dataset / manifest 画像 |
| 3 | 天路径 benchmark 训练模板（可选） | `backend-service/data/workflows_enhanced/` | 若不想直接复用产品 `pv_tsc` 模板，可派生 `workflow-benchmark-*-day-train-eval-v1.json` |
| 4 | 后端 benchmark 槽位解析 | 待核实（`resolve_train_workflow_id` 等） | 让天路径 benchmark 槽位解析到 TSC / 天路径工作流 |
| 5 | 物理真值生成脚本（Q1） | 临时脚本，用完即删 | 由辐照度 / 温度 / PR 推日级二分类真值 |
| 6 | 前置数据转换脚本 | 临时脚本，用完即删 | §6 的列映射 / `i_cal` / 实体键 / 重采样 / `.mat`→parquet |

---

## 8. 实施顺序与门禁

### 8.1 建议顺序

1. **Q1 先行（PVDAQ，摩擦最低）**：适配 PVDAQ → 建 `benchmark_pvdaq_day` 槽位 + 画像 → predict-only 跑 `pv_tsc` → 物理真值核二分类。
2. **Q1 加宽（DKASC）**：多技术多系统，验证不是只在 PVDAQ 碰巧能跑。
3. **Q2 锚点（UTFPR）**：`.mat`→parquet + `i_cal` 推算 → 建 `benchmark_utfpr_day` 槽位 → 类型混淆矩阵（锁定测试集）。
4. **Q2 补充（Réunion）**：验热带单站遮挡。

### 8.2 验收门禁

- [ ] 外部数据转换脚本产物只用项目相对路径。
- [ ] Q1 真值来自物理规则，Q2 真值来自数据集标注；**任何一层都未出现 `truth = pred` 式自造 gold**。
- [ ] benchmark 槽位 `execution_purpose=benchmark_reuse`、`governance_eligible=false`；运行未写 `label_registry.json`、未 Promote、未改产品 champion。
- [ ] Q1 报二分类指标（balanced accuracy / PR-AUC / 异常召回精确）+ 管道跑通证据（有效窗口数、无异常退出）。
- [ ] Q2 报每类 P/R/F1 + 混淆矩阵，测试集全程锁定。
- [ ] 报告显式标注 Q2 的边界（UTFPR 2 组串、Réunion 单站，非全 13 类通用）。
- [ ] `i_cal` 推算口径（公式版本 + 参数来源）在报告中记录。

---

## 9. 风险与遗留

| # | 风险 | 缓解 |
|---|---|---|
| 1 | 检测桥 `truth = int(pred)` 自造 gold（`real_model_detect.py`） | Q1/Q2 一律外挂独立真值；benchmark 评测不走 loop_demo replay 桥的 gold 兜底路径 |
| 2 | `i_cal` 半仿真 sim2real 偏差 | 记录公式版本；ratio 仅作物理证据；Q2 类型金标只来自数据集标注 |
| 3 | UTFPR 仅 2 组串、Réunion 单站 | Q2 定位为"域外锚点"而非"设备泛化"，结论口径收紧 |
| 4 | 采样率不一致（PVDAQ daily / Kannal 15min） | 重采样到 5min 或参数化 `window_length` |
| 5 | 后端 benchmark 槽位解析未逐行核实 | 实施前先补读 `resolve_train_workflow_id` / 治理门禁 / 画像加载 |
| 6 | UTFPR `f_nv` 编码顺序来自 handoff 未联网复核 | 下载后按 §6 核实真实 schema 再定映射 |

---

## 10. 决策记录

| 决策 | 结论 | 原因 |
|---|---|---|
| 天路径当前目标 | 验证通用性（路线 A），不冲精度 | 天路径精度已可，缺的是"换电站是否成立"的证据 |
| Q1/Q2 分层依据 | "证明产品哪件事"（检测 vs 分类），非训练 / 预测 | 两者要的数据根本不是一种东西 |
| Q1 数据 | PVDAQ（首选）/ DKASC | 多设备无标注，物理可核 |
| Q2 数据 | UTFPR（锚点）/ Réunion | 带类型标注但设备单一 |
| 是否共用一个数据集 | 否 | 多设备 ⊕ 类型标注无单一公开集 |
| 是否改 registry / 产品治理 | 否 | benchmark 隔离，`governance_eligible=false` |
| 是否新开日级 benchmark 路径 | 是 | 现有 benchmark 是点路径拓扑，天路径无对应 |
| 是否让管道自造 gold | 否 | 真值必须独立于模型输出 |

---

## 11. 下一步

1. 下载 PVDAQ + 核实 schema / 采样率 → 写前置转换脚本（列映射 + `i_cal` + 实体键）。
2. 新建 `benchmark_pvdaq_day` 槽位 + 画像三件套，predict-only 跑通 `pv_tsc`。
3. 写 Q1 物理真值生成规则（PR / `i_cal` 残差），产出日级二分类真值。
4. 下载 UTFPR + `.mat`→parquet，建 `benchmark_utfpr_day` 锚点测试集，出类型混淆矩阵。
5. 汇总 Q1/Q2 报告，明确通用性结论与边界。
<!-- @AI_GENERATED: end -->
