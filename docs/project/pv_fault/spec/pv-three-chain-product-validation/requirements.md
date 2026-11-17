<!-- @AI_GENERATED -->
# Requirements Document

## Introduction

本需求文档定义 **pv-three-chain-product-validation（光伏三链产品验证）** 的目标产品合同与安全验收边界。需求同时覆盖两条互补主线：

1. **现状验收主线**：继续验证 `pv_day`（设备日 RF）、`pv_point`（真实点 / replay TCN）和 `pv_tsc`（设备日 MultiRocket）三条现有产品链的浏览器故事线、前后端事实映射、证据回查、治理门控与只读 / validation / sandbox 安全行为。
2. **跨数据集产品化主线**：允许用户从浏览器创建项目、接入非内置数据、确认字段映射、查看质量画像、发布不可变数据版本，并让三条兼容路径分别完成预检、experiment / validation、隔离 Sandbox 回放、受控审核和证据归档。

**重心声明：** 本规格的验收重心是**产品故事线完整性、前后端功能对应与用户交互体验**，不是模型精度提升。跨数据集验证是验收手段，用于证明产品可迁移、可操作、可恢复、可追溯与可隔离；模型精度只作为产品证据与安全护栏，不作为交付目标。因此需求不包含调参、换模型、改阈值或新建离线评测基础设施等工作。

本需求描述的是**目标产品行为**，不表示目标能力当前已经全部实现。当前实现事实以 `docs/project/pv_fault/AGENTS.md`（光伏三路径当前实现与验证边界）为准，其中 strict-10 与 `exec-validation-d741dc207593` 相关结论以更晚的 `docs/project/pv_fault/PV_TSC_E2E_VALIDATION_HANDOFF_2026-09-08.md`（TSC 真实 strict-10 与 E2E 验收交接）为准；PVDAQ 已执行离线 benchmark 事实以 `docs/project/pv_fault/PVDAQ_ICAL_LEAKAGE_SAFE_BRIEF_2026-09-07.md`（PVDAQ 无泄漏 `i_cal` 消融事实简报）为准，该简报不构成平台 E2E 或 production 验收；`docs/project/pv_fault/spec/pv-fault-multi-dataset-product-loop/product-design.md`（多项目、多数据集目标产品 Draft）是产品故事线与逐页交互的对齐基准。

本功能的目标是让产品经理、算法工程师、交付人员、运营人员和审核人员能够理解并走读：

```text
创建项目 → 接入数据 → 字段映射 / 质量画像 → 三路径 readiness
→ 工作流绑定 / 预检 → experiment 或 validation
→ 隔离 Sandbox 回放 → 受控审核 → 证据归档
→ 可选人工准入 / freeze / 再训练
→ candidate → 正式 verification → rolling_detect_model → Promote
```

其中，跨数据集产品复验只证明迁移性、交互、执行、lineage 与隔离；产品复验本身不产生生产治理效力。真实准入、freeze、正式重训、candidate 登记、正式 verification、滚动指针和 Promote 均为独立的受控产品写入。

以下事实是本规格不可弱化的验收边界：

- `pv_day` 当前继续使用 quickval predict 图执行检测；产品界面必须如实显示该事实，不能将当前实现表述为已经迁移到专用 day predict 图。
- `pv_point` 当前继续由 `SeqDailyStrategy`（点路径日策略）直连 predictor（预测器）执行；产品界面必须保留真实点 replay 语义，不能伪造冻结 predict workflow execution（工作流执行证据）。
- `pv_tsc` 当前 canonical label workflow（规范模型辅助打标工作流）的完整 UI E2E 尚未完成；KMeans REST shortcut（KMeans REST 快捷路径）不得冒充 canonical TSC 打标成功。
- `exec-validation-d741dc207593`（已有 strict-10 validation 执行 ID）是 validation execution（验证执行），其 `governance_eligible`（是否允许进入模型治理）为 `false`；该执行不能登记 candidate（模型候选）、设置 `rolling_detect_model`（下一轮滚动检测模型）或 Promote（晋升 / 采纳）。
- 仅有 35 个离散可信标签日期是 TSC 数据与评测限制，不阻断三链产品故事线的只读、validation、experiment 或 sandbox 验收；系统不得为通过验收而降低 strict-10（严格 10 次重复评测）合同。
- TSC production（生产）观测保持只读；隔离 Sandbox 可以运行冻结预测图，但不得推进 production 水位、cursor、审核或精度证据。
- validation 与 sandbox 必须保持 candidate、registry（当前模型登记）、proposal（提案）及其他适用 production 真源的 SHA256（安全哈希）零污染。
- 历史 TSC candidate provenance（来源证明）不完整时不得补写来源字段、强制正式复验或强制 Promote。

## Glossary

| 术语 / 字段 | 中文定义与用途 |
|---|---|
| **PV_ThreeChain_Product_Validation_System** | 光伏三链产品验证系统。本需求文档中所有 `THE ... SHALL` 语句的需求主体，覆盖前端页面、API 契约、服务端 scope 校验、持久化隔离、治理门控和验收归档的协同结果。 |
| `project_id` | 客户 / 交付项目硬隔离键。新产品 API、URL、执行上下文和各 scoped 仓储必须显式携带；目标最低隔离范围为 `(project_id, slot)`。 |
| `project_name` | 用户可读的项目名称；用于页面识别，不承担隔离职责。 |
| `legacy` | 历史兼容项目标识。现有仅按 `slot` 分区的状态统一只读映射为 `project_id=legacy`；legacy 不承接新项目产品写入。 |
| `slot` | 项目内产品槽位，也是诊断路径键。有效值为 `pv_day`、`pv_point`、`pv_tsc`；历史 `pv_fault` 仅可只读兼容。`slot` 不再独自承担客户 / 项目隔离职责。 |
| `pv_day` | 设备日 RF 产品槽位；当前 production 日检测使用 quickval predict 图。 |
| `pv_point` | 真实测量点 / replay TCN 产品槽位；当前通过逐点 replay 驱动，仍由 `SeqDailyStrategy` 直连 predictor。 |
| `pv_tsc` | 设备日 MultiRocket 时序分类产品槽位；采用 `[N,288,3]` clock-grid（时钟网格）表示，三个通道为 `value`、`i_cal`、`is_measured`。 |
| **Non_Built_In_Dataset** | 非内置 / 外部数据集。由用户上传、选择平台外部资产或通过 connector 接入，且不是将内置 demo 改名后冒充的新数据。 |
| `dataset_id` | 项目内逻辑数据资产 ID；一个数据资产可以拥有多个不可变版本。 |
| `dataset_profile_id` | 版本化数据画像 ID；保存字段映射、时间语义、实体键、单位、采样、标签粒度和质量策略。 |
| `dataset_version_id` | 发布后的不可变数据版本 ID；用于绑定 workflow、preflight、execution、Sandbox replay、review、snapshot、candidate 和验收证据。 |
| `dataset_version_binding` | execution 与不可变数据版本之间的显式绑定；不得只保存临时文件名或服务器路径而丢失数据 lineage。 |
| `artifact_ref` | 项目内相对工件引用；用于定位数据版本、模型、快照、截图或报告，不得持久化机器绝对路径。 |
| `connector_id` | 已授权数据连接器 ID；页面和证据保存该 ID 与逻辑对象描述，不保存连接口令、token 或私钥。 |
| `site_id` / `device_id` / `branch_id` | 站点、设备和支路实体字段；共同决定去重、设备隔离、游标和审核单位。 |
| `value` / `i_cal` / `is_measured` | 实测值、期望电流参照和实测掩码字段。`i_cal` 是期望电流参照而非 ground truth（人工真值）；字段映射必须说明物理含义、单位、缩放、生成方法、可用时点和缺失策略。 |
| `rated_power_kw` | 设备额定功率字段；只能作为可能的辅助元数据，缺少经验证的转换合同时不得默认用于唯一恢复跨设备电流尺度。 |
| `i_cal_contract` | 期望电流参照校准合同；定义 `i_cal` 的生成或拟合设备、日期、标签使用、因果时点、分类排除范围与允许用途。使用 `i_cal` 的 profile、preflight、execution、评测和证据必须显式绑定该合同。 |
| `calibration_audit_id` | 校准审计记录 ID；把 `i_cal_contract` 绑定到逐 split 的拟合设备、日期、标签使用、选择范围、overlap 和相对审计工件。 |
| `leaky_device_ical` | 标签泄漏上界合同；使用评估期信息或标签辅助拟合，仅允许 diagnostic experiment（诊断实验），永久满足 `leakage_upper_bound=true` 与 `governance_eligible=false`。 |
| `value_only` | 无校准基线合同；固定 `i_cal=0` 并保持相同输入形状，不读取标签，也不因无泄漏自动获得生产治理资格。 |
| `global_train_devices_only` | 全局训练设备合同；每个外层 split 只使用外层训练设备拟合参照，外层测试设备与拟合设备重叠数必须为 0。 |
| `history_past_only` | 仅过去无标签历史合同；每个目标样本只允许使用更早的设备历史，不读取标签或 truth 清洗，并从分类样本中排除校准月。 |
| `leakage_upper_bound` | 结果是否为有意使用泄漏信息构造的诊断上界；该字段为 `true` 时结果不得进入 production 或模型治理。 |
| `outer_test_truth` | 外层测试设备或测试样本的标签 / 事后真值；除 `leaky_device_ical` 的显式诊断上界外，不得参与校准、清洗或模型选择。 |
| `benchmark_evidence_version` | 不可变离线 benchmark 证据版本；既有冻结工件以只读版本登记，新适配、重跑或复验必须创建新版本。 |
| `repeatability_status` | 独立重复性复验状态；同一次运行内的多次重复或多个 fold 不等于第二个独立证据版本。 |
| `metric_applicability` | 指标适用性；记录某个统计范围的指标能否计算、N/A 原因和类别支持度。 |
| `BA` / `PR-AUC` | Balanced Accuracy（平衡准确率）和 Precision-Recall 曲线下面积；两者口径不同，均不得替代人工真值覆盖或生产治理结论。 |
| `abnormal_precision` / `abnormal_recall` / `abnormal_f1` / `FP` / `FN` | 异常类精确率、召回率、F1、假阳性数和假阴性数；必须与样本支持度、折波动和指标适用性一起解释。 |
| **offline_benchmark_evidence** | 离线 benchmark 证据；在冻结 universe、标签顺序与 split manifest 下形成的算法 / 校准比较，不是平台 execution、跨数据集产品复验或正式模型 verification。 |
| `workflow_id` | 冻结工作流或项目内工作流版本 ID，说明训练、预测或打标运行的是哪张画布。 |
| `execution_id` | 单次工作流执行证据 ID，可回查项目、槽位、数据版本、运行模式、运行域、节点状态、图摘要、输入相对路径和输出。 |
| `dataset_version_id` lineage | 数据版本来源链。表示同一 `dataset_version_id` 从 preflight、execution、Sandbox、review 到可选 snapshot / candidate 及验收证据的连续关联。 |
| `run_mode` | 运行目的枚举，仅允许 `experiment`（实验）、`validation`（受控验证）或 `production`（正式产品运行）。 |
| `run_domain` | 状态写入域，仅表示 production 状态根或 sandbox 隔离状态根；`run_domain` 不等同于 `run_mode`。 |
| `sandbox_id` | 隔离 Sandbox 实例 ID；Sandbox 水位、cursor、审核、精度和结果必须按该 ID 分区。 |
| **read-only** | 页面或角色只读状态；read-only 是 UI / 权限状态，不是 `run_mode` 或 `run_domain`。 |
| `PathReadiness` | “数据版本 × 路径”的兼容性评估结果，包含 scope、状态、事实、阻断、允许运行模式和下一步。 |
| `ready` | readiness 状态：满足当前路径输入与预检合同；不自动表示 production 资格。 |
| `experiment_only` | readiness 状态：可形成实验输入，但数据或评测不足以获得 production 资格。 |
| `needs_mapping` | readiness 状态：缺少字段、时间、实体、单位或标签粒度映射。 |
| `needs_labels` | readiness 状态：可形成样本，但缺少满足当前路径粒度的训练或审核标签。 |
| `insufficient_data` | readiness 状态：日期、设备、类别或采样覆盖不足。 |
| `unsupported` | readiness 状态：缺少当前路径不可替代的基础条件。 |
| `facts` | readiness 中的可核查数据质量事实列表，例如离散日期数、设备覆盖或标签分布。 |
| `blockers` | readiness 中阻止某项运行或治理动作的具体条件列表。 |
| `allowed_run_modes` | readiness 中允许启动的 `run_mode` 集合；不替代 production 服务端门禁。 |
| `cross_dataset_product_validation_id` | 跨数据集产品复验批次 ID；聚合一个或多个项目、三路径数据版本分配、浏览器场景和证据包，不是正式 `verification_id`。 |
| **cross_dataset_product_validation** | 跨数据集产品复验。使用非内置数据验证迁移性、交互、执行、lineage 和隔离，治理效力固定为 none。 |
| `dataset_assignments` | 跨数据集产品复验批次中从每个 `slot` 到所选 `dataset_version_id` 的映射；三个路径可以共用一个版本，也可以使用不同兼容版本。 |
| `ValidationEvidenceBundle` | 跨数据集产品复验证据包；保存 scope、路由、截图、网络 / console / page error 摘要、execution、readiness、lineage、SHA256 和结果。 |
| `review_id` | 人工审核会话 ID；必须关联项目、槽位、数据版本以及来源 execution 或检测批次。 |
| `review_slot` | 人工审核队列的槽位筛选参数。由模型状态页跳转审核页时必须传递，例如 TSC 使用 `review_slot=pv_tsc`。 |
| `snapshot_id` | 依据累计入账事件和 `reviewed_at_cutoff`（审核结束时间上界）冻结得到的不可变训练快照 ID。 |
| `reviewed_at_cutoff` | freeze 选择累计输入时使用的审核结束时间上界，不是原始数据事件时间上界。 |
| `model_candidate_id` | 模型候选记录 ID；必须关联项目、槽位、模型工件、来源 workflow、来源 execution、来源 snapshot 和 `evaluation_contract`。 |
| `verification_id` | 与一个正式 `model_candidate_id` 绑定的模型治理复验记录 ID；不得由产品复验批次 ID 替代。 |
| `passed` | verification 的布尔通过字段；只有 `passed=true` 才可作为后续正式治理动作的必要证据。 |
| `rolling_detect_model` | registry 中显式指定给下一轮滚动检测消费的模型或 candidate 引用；不同于 Champion、Challenger、最近训练模型或 candidate 历史。 |
| `registry_version` | registry 乐观并发版本；指针写入以该版本防止后写覆盖其他合法更新。 |
| `governance_eligible` | execution 是否允许进入 candidate、verification 或生产治理。validation execution 必须为 `false`。 |
| `evaluation_contract` | 固定评测量尺，定义表示、切分、隔离、重复次数等；不是被测 workflow 图本身。 |
| `production_contract_valid` | 生产评测合同是否完整有效；不等于业务精度达标，也不等于可以 Promote。 |
| `source_workflow_id` | candidate 的来源冻结工作流 ID，用于证明候选从哪张图产生。 |
| `source_execution_id` | candidate 的来源 execution ID，用于证明候选来自一次成功且可治理的实际执行。 |
| `source_snapshot_id` | candidate 来源训练所消费的不可变 snapshot ID；用于把 candidate 回查到累计事件与数据版本。 |
| `model_artifact_ref` | 模型工件的项目内相对路径引用；不得持久化开发机绝对路径。 |
| `expected_registry_version` | 调用方写入滚动指针或 Promote 前读取的 registry 版本；服务端使用该字段执行乐观并发校验。 |
| `production_writes_authorized` | 是否获得本轮验收 production 写入人工授权的布尔字段；自动验收默认值为 `false`。 |
| `set_as_production` | Promote 请求中的布尔字段；为 `true` 时，除更新 candidate 状态外，还请求把 candidate 自身的 `source_workflow_id` 与 `model_artifact_ref` 写入目标生产登记。 |
| `production_slot` | Promote 或滚动指针写入时的目标产品槽位；缺省时应与 candidate 自身 `slot` 一致，跨项目或跨槽写入必须被服务端拒绝。 |
| `registry.json` | 当前模型登记真源。目标按 `(project_id, slot)` 分区保存 Champion、Challenger、`rolling_detect_model`、`registry_version`、`updated_at`（最后更新时间）和 `note`（人类可读备注）；当前 slot-only 文件只读映射到 legacy。该文件单独保存，使 UI、调度器和治理 API 不必从训练历史猜测当前指针；介质与相对目录由部署配置决定。 |
| `model_candidates.json` | 模型候选历史登记文件。目标按 `(project_id, slot)` 分区保存 candidate 与 provenance；该文件不等价于当前滚动模型。 |
| `promotions_log.json` | 只追加的 Promote 审计日志。每条事件至少记录 `model_candidate_id`（候选 ID）、`verification_id`（正式复验 ID）、`set_as_production`（是否改生产登记）、`production_slot`（目标槽位）、目标 `project_id`、前后 `registry_version`、操作者、原因和时间；该日志不代替 registry 当前指针。 |
| `label_proposals.json` | 真实机器提案索引真源；sandbox 输出不得写入或污染该文件。 |
| **provenance** | 对数据、模型或 candidate 来源的可回查证明，至少包括相应 `project_id`、`slot`、数据版本、工作流、execution、相对工件路径与评测合同。 |
| **Champion / Challenger** | registry 中的生产模型 / 对比模型角色。Champion 或 Challenger 均不自动等于 `rolling_detect_model`。 |
| **validation** | 用于验证冻结图、输入、节点、合同和 execution 的受控 `run_mode`；必须产生 `governance_eligible=false`，不得升级为 candidate 或生产治理。 |
| **sandbox** | 隔离 `run_domain`；状态写入以 `sandbox_id` 分区，结果仅用于实验或验证，不能成为 production 数据或治理证据。 |
| **product write** | 需人工确认的真实准入、freeze、重训、正式 verification、指针写入或 Promote；会影响对应 `(project_id, slot)` 的业务或治理真源。 |
| **quickval predict 图** | `pv_day` 当前实际使用的日检测预测图；本规格只要求如实展示，不要求替换。 |
| `SeqDailyStrategy` | `pv_point` 当前用于真实点 replay 的策略，仍直连 predictor，不能被描述为冻结 predict workflow execution。 |
| `replay_activity` | 点路径逐点喂数调度过程，使用 `pending point`（待处理真实点）、`committed history`（已提交历史）、`cursor`（回放游标）和 `outcome`（处理结果）表达状态。 |
| `workflow-pv-tsc-label-v1` | TSC canonical 模型辅助打标 workflow ID；目标流程包含 `tsc_predict`（TSC 模型预测节点）与 `emit_tsc_label_proposal`（输出 TSC 标签提案节点）。 |
| **KMeans REST shortcut** | 历史 REST 聚类快捷路径；即使可运行，也不等价于 `workflow-pv-tsc-label-v1` 的 canonical TSC 模型辅助打标。 |
| **strict-10** | TSC 评测合同：维持严格日期 × 设备隔离并进行 10 次重复评测。不得因数据稀疏、低分或验收便利降低隔离或重复次数。 |
| `macro_f1_mean` | strict-10 输出的平均 Macro-F1 指标；不得称为“真实准确率”，也不得与旧 3-seed 或不同隔离口径 holdout 直接同比。 |
| `exec-validation-d741dc207593` | 已有 TSC strict-10 validation `execution_id`；必须保持 `governance_eligible=false`，不能被登记 candidate、写入滚动指针或 Promote。 |
| **Trace Evidence** | 页面阶段结论使用的最小证据包，至少包含当前 scope、阶段、关联 ID、证据状态、原因码、中文说明和下一步。 |
| **Action State** | 页面可操作状态：初始空态、加载、只读、可启动、等待人工、门控阻断、数据不足、sandbox-only、可恢复失败、fail-closed 和已完成。 |
| **SHA256 零污染断言** | validation 或 sandbox 前后对 candidate、registry、适用 proposal、production cursor、review、累计或 Promote 审计真源计算 SHA256；无预期 production 写入时前后哈希必须相同。 |
| **相对路径** | 相对于项目根或 `backend-service/` 的可迁移路径。输入、工件、快照、截图、报告和持久化证据不得写入 Windows、macOS 或 Linux 的机器绝对路径。 |

## Requirements

### Functional Requirements

### R1：项目、槽位与页面上下文连续性

**用户故事：** 作为产品经理或运营人员，我希望任意页面都明确显示当前项目和产品槽位并保持跳转上下文，以免误把另一项目或另一条链的数据、模型或审核结果当作当前事实。

#### Acceptance Criteria

1. WHEN 用户在项目工作台、部署、精度运营、标注审核或累计训练页面选择有效 `project_id` 和 `slot`, THE PV_ThreeChain_Product_Validation_System SHALL 在 URL 和可见页面标签中保留相同的 `project_id` 与 `slot`。
2. WHEN 页面以某个有效 `project_id` 和 `slot` 发起读取或写入请求, THE PV_ThreeChain_Product_Validation_System SHALL 在前端 query 或 body、API handler、服务调用、持久化 scope 和后端响应中传递相同的 `project_id` 与 `slot`。
3. IF API 响应缺少 `project_id` 或 `slot`，或响应中的 `project_id` / `slot` 与当前 URL 请求 scope 不一致, THEN THE PV_ThreeChain_Product_Validation_System SHALL 将该 payload 判定为 scope mismatch，拒绝渲染和写操作，并显示缺失或冲突字段、关联值与刷新当前项目的下一步。
4. WHEN 用户从模型状态页进入人工审核, THE PV_ThreeChain_Product_Validation_System SHALL 传递当前 `project_id` 以及与当前 `slot` 相同的 `review_slot`；`pv_tsc` 的跳转 SHALL 使用 `review_slot=pv_tsc`。
5. IF `slot` 缺失、非法或加载失败, THEN THE PV_ThreeChain_Product_Validation_System SHALL 进入明确的安全失败状态，并说明重新选择有效槽位的下一步。
6. IF 新项目请求缺少、携带非法或无法解析的 `project_id`, THEN THE PV_ThreeChain_Product_Validation_System SHALL fail-closed，并且不分配默认项目、不回退任意 `slot` 或 `legacy`。
7. WHEN dataset、execution、review、累计账本、snapshot、candidate、verification、registry、cursor 或结果属于不同 `(project_id, slot)`, THE PV_ThreeChain_Product_Validation_System SHALL 对这些对象维持读写隔离。
8. WHEN 用户切换 `project_id`、`slot` 或 `dataset_version_id`, THE PV_ThreeChain_Product_Validation_System SHALL 在新 scope 请求完成前立即清空旧 scope 的可见状态、请求缓存、错误和可写动作，并丢弃所有由旧 scope 发起的迟到响应。
9. WHEN 数据相关页面或 API 返回结果, THE PV_ThreeChain_Product_Validation_System SHALL 回显当前 `project_id`、`slot` 和 `dataset_version_id`，并把任一字段缺失或与当前页面 scope 不一致的结果判定为 scope mismatch 后拒绝渲染。
10. WHEN 用户显式进入 `project_id=legacy` 的兼容页面, THE PV_ThreeChain_Product_Validation_System SHALL 将现有 slot-only 状态标识为历史只读事实。
11. IF 新项目 scoped 对象不存在, THEN THE PV_ThreeChain_Product_Validation_System SHALL 返回“当前项目未产出”或等价空态，并且不读取 legacy 同槽对象补位。
12. WHEN `project_id=legacy`, THE PV_ThreeChain_Product_Validation_System SHALL 禁用新准入、freeze、candidate、registry、cursor 或其他新产品写入。

### R2：产品故事线与阶段可解释性

**用户故事：** 作为非代码使用者，我希望在每个项目和每条链上知道当前处于闭环的哪一步、当前结果是事实还是目标、为什么不能继续以及下一步应去哪里。

#### Acceptance Criteria

1. WHEN 用户访问项目总览、数据接入、部署、检测 / replay、审核、累计、训练、candidate、verification、滚动指针或精度页面, THE PV_ThreeChain_Product_Validation_System SHALL 展示当前 scope、阶段状态、中文说明、证据摘要和下一步动作。
2. WHEN 页面解析 Trace Evidence, THE PV_ThreeChain_Product_Validation_System SHALL 将页面状态区分为初始空态、加载、只读、可启动、等待人工、门控阻断、数据不足、sandbox-only、可恢复失败、fail-closed 或已完成。
3. WHEN 页面显示阻断或禁用动作, THE PV_ThreeChain_Product_Validation_System SHALL 同时显示准确原因、当前值、门槛和满足前置条件的最短下一步。
4. WHEN 页面存在业务结论、评测口径和原始 JSON, THE PV_ThreeChain_Product_Validation_System SHALL 优先展示中文业务结论、口径和下一步，并将原始 JSON 放置于二级诊断区域。
5. WHEN 页面展示模型或治理阶段, THE PV_ThreeChain_Product_Validation_System SHALL 将“模型已训练”“candidate 已登记”“verification 已通过”“滚动模型已指定”和“Champion 已设置”显示为互不等价的阶段。
6. WHEN 页面展示目标产品能力但当前实现尚未完成, THE PV_ThreeChain_Product_Validation_System SHALL 将目标能力标识为待实施、功能缺口或 sandbox-only，而不表述为当前已验证事实。
7. WHEN 页面展示跨数据集产品复验和正式模型复验, THE PV_ThreeChain_Product_Validation_System SHALL 分别使用“产品复验 / 迁移验证”和“候选正式复验”的中文名称。
8. WHEN 当前 scope 或阶段必需 ID 缺失，或当前 scoped 请求仍在进行, THE PV_ThreeChain_Product_Validation_System SHALL 分别将页面解析为初始空态或加载态，并使页面可观察到缺失前置项或正在读取的 scope。
9. WHEN 启动作业所需的 scope、readiness、权限和前置门控全部通过且当前没有运行中作业, THE PV_ThreeChain_Product_Validation_System SHALL 将页面解析为可启动状态并显示将要创建的运行目的与运行域。
10. WHEN 页面没有写权限、结果只允许写入 Sandbox 或流程正在等待人工确认 / 审核, THE PV_ThreeChain_Product_Validation_System SHALL 分别将页面解析为只读、sandbox-only 或等待人工状态，并显示对应授权、运行域或待办事实。
11. IF 可测量门槛未满足、数据覆盖不足或 scope / 证据发生冲突, THEN THE PV_ThreeChain_Product_Validation_System SHALL 分别将页面解析为门控阻断、数据不足或 fail-closed 状态，并禁用与该状态冲突的动作。
12. IF 失败记录包含同一 scope 下可重新读取或重试的任务 / `execution_id`（执行证据 ID）, THEN THE PV_ThreeChain_Product_Validation_System SHALL 将页面解析为可恢复失败状态并提供该任务或 execution 的恢复入口。
13. WHEN 当前阶段要求的 scoped 产物、lineage 和终态证据全部存在, THE PV_ThreeChain_Product_Validation_System SHALL 将页面解析为已完成状态，并且不以仅有成功提示、前端缓存或目标设计替代完成证据。

### R3：项目化模型登记与滚动检测指针的准确呈现

**用户故事：** 作为交付或运营人员，我希望准确知道当前项目下一轮检测会消费哪个模型，而不是从 candidate 或训练历史猜测。

#### Acceptance Criteria

1. WHEN 用户在 `AlgorithmDeploymentPage` 查看任意有效 `(project_id, slot)`, THE PV_ThreeChain_Product_Validation_System SHALL 分别展示当前 Champion、Challenger、`rolling_detect_model` 和 `registry_version`，并说明四者的不同治理含义。
2. WHEN scoped registry 没有已设置的 `rolling_detect_model`, THE PV_ThreeChain_Product_Validation_System SHALL 展示明确空态、缺少的前置条件和下一步，而不将最近训练模型或 Challenger 表述为当前检测模型。
3. IF candidate 缺少 `project_id`、`slot`、来源 `dataset_version_id`、`source_workflow_id`、`source_execution_id`、`source_snapshot_id`、`model_artifact_ref` 或 `evaluation_contract`, THEN THE PV_ThreeChain_Product_Validation_System SHALL 显示具体 provenance 缺口，并阻止该 candidate 进入正式 verification、滚动指针或 Promote 操作。
4. WHEN 页面展示历史 TSC candidate, THE PV_ThreeChain_Product_Validation_System SHALL 显示该记录为 legacy 历史记录、列出 provenance 缺口，并说明该记录不能直接正式复验、设置滚动指针或 Promote。
5. WHILE candidate 没有与 candidate 自身相同 `(project_id, slot)`、相同 `model_candidate_id` 绑定且 `passed=true` 的正式 verification, THE PV_ThreeChain_Product_Validation_System SHALL 禁用正式滚动指针和 Promote 写操作，并显示缺失或不一致的 verification 前置条件。
6. WHEN 页面读取新项目当前模型选择, THE PV_ThreeChain_Product_Validation_System SHALL 仅将目标 `(project_id, slot)` 分区的 `registry.json` 作为 Champion、Challenger、`rolling_detect_model` 和 `registry_version` 的当前指针真源，而不从 candidate、verification 或训练历史推断当前值。
7. WHEN 页面读取当前 slot-only registry, THE PV_ThreeChain_Product_Validation_System SHALL 将该登记只读映射到 `project_id=legacy`，并且不将该登记自动复制到任何新项目。
8. IF registry 响应的 `project_id`、`slot` 或 `registry_version` 与当前写入确认上下文不一致, THEN THE PV_ThreeChain_Product_Validation_System SHALL 阻止滚动指针或 Promote 确认，并要求重新读取目标 scoped registry。
9. IF 当前 `(project_id, slot)` 的 registry 不存在、不可读取、结构无效或无法确认版本, THEN THE PV_ThreeChain_Product_Validation_System SHALL fail-closed，显示 registry 读取原因，并且不使用最近训练、candidate、Challenger 或 legacy 数据补出当前指针。

### R4：三条链特有的检测与 replay 语义

**用户故事：** 作为算法工程师，我希望产品页面保留三条链真实的执行语义，避免为了界面对称而误导用户。

#### Acceptance Criteria

1. THE PV_ThreeChain_Product_Validation_System SHALL 接受 `pv_day`、`pv_point` 和 `pv_tsc` 使用不同的后端调度与算子实现，并以统一产品解释而非后端同构作为验收标准。
2. WHEN 页面展示 `pv_day` production 检测状态, THE PV_ThreeChain_Product_Validation_System SHALL 标注当前检测使用 quickval predict 图，并提供当前图或回执证据。
3. WHEN 页面展示 `pv_point` 检测状态, THE PV_ThreeChain_Product_Validation_System SHALL 展示 `pending point`、`committed history`、`cursor` 和 `outcome` 的真实点 replay 概念，而不将逐点 replay 包装为日批处理。
4. WHEN 页面展示 `pv_point` replay 证据, THE PV_ThreeChain_Product_Validation_System SHALL 标注 `SeqDailyStrategy` 仍直连 predictor 的事实，并说明每个 replay 结果不具冻结 predict workflow execution provenance。
5. WHEN 页面展示 `pv_tsc` 检测状态, THE PV_ThreeChain_Product_Validation_System SHALL 展示设备日粒度、多窗口证据、日调度回执和失败日不越过 cursor 的语义。
6. WHEN 用户在 TSC production 观测页面查看状态, THE PV_ThreeChain_Product_Validation_System SHALL 提供只读观测，并且不产生推进一天、手工补检、水位、cursor、审核或精度证据写入。
7. WHEN TSC 没有当前日检测回执, THE PV_ThreeChain_Product_Validation_System SHALL 显示“未产出 / 无近期回执”或等价事实说明，而不伪造日检测状态。
8. IF 当前 `(project_id, slot, dataset_version_id, device_id, date)` 缺少检测或 replay 证据, THEN THE PV_ThreeChain_Product_Validation_System SHALL 显示当前对象未产出，并且不使用 legacy、其他项目、其他槽位、其他设备或其他日期的证据补位。

### R5：提案启动与人工审核的真实来源说明

**用户故事：** 作为审核人员，我希望知道审核对象来自聚类 shortcut、canonical workflow，还是已有模型预测，从而正确理解结果的可信边界。

#### Acceptance Criteria

1. WHEN 用户打开任一路径的提案入口或结果, THE PV_ThreeChain_Product_Validation_System SHALL 展示当前 `project_id`、`slot`、`dataset_version_id`、`run_mode`、来源类型、提案粒度，并明确来源是 canonical workflow、REST shortcut 还是已有模型预测，同时说明机器提案不等于人工确认真值。
2. WHEN 页面展示 TSC 打标入口或结果, THE PV_ThreeChain_Product_Validation_System SHALL 将 `workflow-pv-tsc-label-v1` 显示为由 `tsc_predict` 时序分类预测与 `emit_tsc_label_proposal` 设备日提案组成的 canonical 模型辅助打标画布，并与历史 KMeans REST shortcut 明确区分。
3. IF TSC canonical UI 入口尚未接通, THEN THE PV_ThreeChain_Product_Validation_System SHALL 将该状态显示为功能缺口或 sandbox-only 验证路径，并提供可验证的下一步。
4. WHEN TSC canonical UI 入口尚未接通, THE PV_ThreeChain_Product_Validation_System SHALL 不在回退到 KMeans REST shortcut 后声明 canonical TSC 打标成功。
5. WHEN 用户读取人工审核队列或审核详情, THE PV_ThreeChain_Product_Validation_System SHALL 按 `project_id` 与 `review_slot` 筛选，并展示数据版本、预测或提案来源、单位粒度、审核进度和证据链接。
6. WHEN 审核页面提供审核动作, THE PV_ThreeChain_Product_Validation_System SHALL 将“提交 verdict”“审核全部完成”和“完成并准入”显示为三个独立动作。
7. WHEN 用户提交单条 verdict, THE PV_ThreeChain_Product_Validation_System SHALL 保持对应 `(project_id, slot)` 累计账本不变。
8. WHEN 浏览器验收运行人工审核场景, THE PV_ThreeChain_Product_Validation_System SHALL 使用只读历史会话、Sandbox 审核域或负向调用，而不通过 production“确认正确”或其他人工裁决按钮制造生产真值。
9. IF review 的 `project_id`、`slot` 或 `dataset_version_id` 与来源 execution / 检测批次不一致, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝整个 verdict、审核完成或准入请求，并且不写部分审核或累计结果。
10. WHEN 相同 `(project_id, slot, dataset_version_id, review_id)` 和相同已完成 verdict 集合重复调用完成并准入, THE PV_ThreeChain_Product_Validation_System SHALL 返回同一准入结果或明确的已处理结果，并且不追加重复累计 inclusion event。

### R6：项目化累计准入、freeze 与训练快照的阶段隔离

**用户故事：** 作为交付人员，我希望知道当前项目的审核结果是否已入账、是否已冻结、训练到底消费了哪一版快照，避免把相邻步骤或其他项目的数据混为一谈。

#### Acceptance Criteria

1. WHEN `complete-and-admit` 成功, THE PV_ThreeChain_Product_Validation_System SHALL 展示对应 `project_id`、`slot`、`dataset_version_id`、数据版本来源、确认标签版本和累计事件，并说明该动作尚未自动 freeze。
2. WHEN 用户在 `CumulativeTrainingLedgerPage` 查看任意有效 `(project_id, slot)`, THE PV_ThreeChain_Product_Validation_System SHALL 展示入库事件、freeze 版本、`snapshot_id`、输入事件、来源数据版本、快照观测和相对 artifact 路径。
3. WHEN 用户发起 freeze, THE PV_ThreeChain_Product_Validation_System SHALL 使用 `reviewed_at_cutoff` 作为当前 `(project_id, slot)` 的审核完成时间上界选择输入，并展示实际采用的 inclusion event 与数据版本范围，而不把原始数据事件时间解释为 cutoff。
4. WHEN 对相同 `(project_id, slot)`、相同 `reviewed_at_cutoff` 和相同有序输入事件内容摘要重复发起 freeze, THE PV_ThreeChain_Product_Validation_System SHALL 返回同一 `snapshot_id` 或明确的幂等命中结果，并且不物化重复快照。
5. WHEN 页面展示 `pv_point` freeze 证据, THE PV_ThreeChain_Product_Validation_System SHALL 说明 freeze 过滤整日聚类盒子以保护点级真值的规则。
6. WHEN 页面展示 `pv_tsc` freeze 证据, THE PV_ThreeChain_Product_Validation_System SHALL 展示 288×3 网格合格设备日、拒绝数、通道、类别分布和稀疏日期解释。
7. WHEN 页面展示 TSC 累计数据行数, THE PV_ThreeChain_Product_Validation_System SHALL 不将“105 万行”表述为连续日期覆盖。
8. WHEN 自动浏览器 E2E 在未获得明确人工确认的情况下运行, THE PV_ThreeChain_Product_Validation_System SHALL 不调用真实准入或 freeze 写接口。
9. WHEN 后续人工验证真实准入或 freeze 写入, THE PV_ThreeChain_Product_Validation_System SHALL 在动作前显示目标 `project_id`、`slot`、`dataset_version_id`、影响范围和人工确认要求。
10. IF 累计事件、freeze 输入或 snapshot 属于不同 `project_id` 或 `slot`, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝整个合并、freeze 或训练消费请求，并且不产生部分 snapshot、训练输入或账本写入。
11. WHEN snapshot 由已发布数据版本和累计事件生成, THE PV_ThreeChain_Product_Validation_System SHALL 保留 `dataset_version_id`、review 来源与 inclusion event 的 lineage。
12. WHEN 页面展示 `pv_day` freeze 证据, THE PV_ThreeChain_Product_Validation_System SHALL 展示设备日样本数、接受与拒绝事实、来源分布、标签分布、输入事件摘要和相对 artifact 引用。

### R7：训练、评测与 execution 证据的可追溯性

**用户故事：** 作为算法工程师，我希望用户能看清当前项目的一次训练是否真实执行、使用了哪个数据版本、评测合同是什么，以及该 execution 是否有资格进入 candidate 治理。

#### Acceptance Criteria

1. WHEN 页面展示训练结果, THE PV_ThreeChain_Product_Validation_System SHALL 关联并展示 `project_id`、`slot`、`dataset_version_id`、`workflow_id`、`execution_id`、`snapshot_id`、模型工件相对路径、`run_mode`、`run_domain` 和 `evaluation_contract`。
2. IF 训练结果缺少 `project_id`、`slot`、`dataset_version_id`、`workflow_id`、`execution_id`、`snapshot_id`、模型工件相对路径或 `evaluation_contract`, THEN THE PV_ThreeChain_Product_Validation_System SHALL 将该训练结果显示为证据不足。
3. WHEN 训练处于 queued、running、completed、failed 或 cancelled 状态, THE PV_ThreeChain_Product_Validation_System SHALL 持久化并分别展示对应状态，使用户离开页面后仍可按 `project_id`、`slot` 和任务或 `execution_id` 重新读取同一运行。
4. WHEN 页面展示 `pv_tsc` 训练结果, THE PV_ThreeChain_Product_Validation_System SHALL 固定说明 288×3 表示、strict 日期 × 设备隔离、10 repeats、`production_contract_valid` 与业务精度之间的区别。
5. WHEN 页面展示 strict-10 的 `macro_f1_mean`, THE PV_ThreeChain_Product_Validation_System SHALL 将该数值标识为固定标签空间的平均 Macro-F1，而不称为“真实准确率”或与旧 3-seed、不同隔离口径 holdout 直接同比。
6. IF strict 数据的日期、设备或类别不足, THEN THE PV_ThreeChain_Product_Validation_System SHALL 显示数据不足或 split 不可行原因，并保留当前 strict 合同。
7. WHEN strict 数据不足、低分或日期稀疏, THE PV_ThreeChain_Product_Validation_System SHALL 不降低 strict 隔离门槛、关闭隔离或减少重复次数来使验收通过。
8. WHEN 页面回显 validation execution, THE PV_ThreeChain_Product_Validation_System SHALL 显示 `governance_eligible=false` 和“执行成功不能进入 candidate 或生产治理”的中文说明。
9. WHEN 页面或 API 使用 `exec-validation-d741dc207593`, THE PV_ThreeChain_Product_Validation_System SHALL 将该 execution 视为 strict-10 validation，保持 `governance_eligible=false`，并阻止登记 candidate、创建正式 verification、写入 `rolling_detect_model` 或 Promote。
10. WHEN TSC 只有 35 个离散可信标签日期, THE PV_ThreeChain_Product_Validation_System SHALL 将该事实解释为数据与评测限制，而不将该事实作为三链产品故事线只读、experiment、validation 或 sandbox 验收的阻断条件。
11. WHEN execution 消费已发布数据版本, THE PV_ThreeChain_Product_Validation_System SHALL 持久化 `dataset_version_binding`、不可变数据版本内容摘要和可按既有相对路径解析约定定位的输入工件引用。
12. IF execution 响应与 execution 持久化记录在 `project_id`、`slot`、`dataset_version_id`、`workflow_id`、`run_mode`、`run_domain`、状态、模型工件或 `evaluation_contract` 任一字段缺失或不一致, THEN THE PV_ThreeChain_Product_Validation_System SHALL 将 execution 标记为证据冲突，拒绝把响应成功当作持久化成功，并阻止 candidate 或其他治理消费。

### R8：项目化 candidate 与正式 verification 门控

**用户故事：** 作为运营人员，我希望在当前项目的候选到正式复验过程中明确看到门槛和证据，避免错误地把训练完成或产品复验通过当作可上线。

#### Acceptance Criteria

1. WHEN 页面展示 candidate 详情, THE PV_ThreeChain_Product_Validation_System SHALL 展示 `project_id`、`slot`、`model_candidate_id`、来源 `dataset_version_id`、`source_workflow_id`、`source_execution_id`、`source_snapshot_id`、`model_artifact_ref` 和 `evaluation_contract`。
2. WHEN 前端或后端收到 `governance_eligible=false` execution 的 candidate 登记请求, THE PV_ThreeChain_Product_Validation_System SHALL 拒绝登记并返回可读门控原因。
3. WHEN 页面展示正式 verification, THE PV_ThreeChain_Product_Validation_System SHALL 展示候选绑定关系、`verification_id`、`project_id`、`slot`、运行状态、通过或失败状态、`evaluation_contract` 和关联评测 `execution_id`。
4. IF 尚无 candidate 或 candidate 无法正式复验, THEN THE PV_ThreeChain_Product_Validation_System SHALL 显示“无可复验候选”或具体门控原因，而不将空态渲染为成功。
5. WHILE verification 缺失或 `passed` 不为 `true`, THE PV_ThreeChain_Product_Validation_System SHALL 保持滚动指针与 Promote 操作禁用，并说明需满足同一 `(project_id, slot)` 下 `passed=true` 的前置条件。
6. WHEN 本轮验收执行 candidate 或 verification 场景, THE PV_ThreeChain_Product_Validation_System SHALL 仅验证读取、门控、Sandbox、mock 或负向路径，而不要求真实 Promote 或 production registry 写入。
7. IF candidate、verification 或 evaluation execution 的 `project_id`、`slot` 或 candidate 绑定关系不一致, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝创建或完成正式 verification。
8. IF 请求使用 `cross_dataset_product_validation_id` 代替 `model_candidate_id` 或 `verification_id`, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝请求并返回“产品复验不具模型治理效力”的原因。
9. WHEN 正式 verification 返回 `passed=true`, THE PV_ThreeChain_Product_Validation_System SHALL 仅在持久化 verification 与同一 `(project_id, slot, model_candidate_id)`、固定 `evaluation_contract` 和关联评测 `execution_id` 全部一致时启用后续治理动作。

### R9：项目化滚动模型与 Promote 的安全治理

**用户故事：** 作为发布负责人，我希望系统在任何可能影响当前项目下一轮检测或生产模型的动作前明确写入对象、项目、槽位和审计边界。

#### Acceptance Criteria

1. WHEN 用户进入设置 `rolling_detect_model` 的确认流程, THE PV_ThreeChain_Product_Validation_System SHALL 展示 `project_id`、candidate、verification、目标 `slot`、当前 `registry_version`、写入影响和人工确认提示。
2. WHEN 服务端收到正式滚动指针写入请求, THE PV_ThreeChain_Product_Validation_System SHALL 重新读取并验证 candidate、来源 execution、`passed=true` 的正式 verification、目标 `project_id`、目标 `slot` 和 `expected_registry_version` 属于同一确认对象。
3. IF 正式滚动指针写入请求跨 `project_id`、跨 `slot` 或缺少通过的 verification, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝请求并返回具体门控原因。
4. WHEN 页面或 API 说明 Promote 请求, THE PV_ThreeChain_Product_Validation_System SHALL 解释 `model_candidate_id`、`verification_id`、`set_as_production`、`production_slot` 和 `expected_registry_version` 的语义，并说明 production 登记写入 candidate 自身的 `source_workflow_id` 与 `model_artifact_ref`。
5. WHEN `set_as_production=true`, THE PV_ThreeChain_Product_Validation_System SHALL 不将 baseline workflow、无来源 candidate、其他项目或其他 `slot` 的模型工件写入目标 production 登记。
6. WHEN 系统记录 Promote 历史, THE PV_ThreeChain_Product_Validation_System SHALL 将 `(project_id, slot)` 分区的 `promotions_log.json` 保持为 append-only 审计历史，并将日志展示为历史事件而不是当前模型指针。
7. WHEN 自动化验证滚动指针或 Promote 门控, THE PV_ThreeChain_Product_Validation_System SHALL 使用 Sandbox、mock、负向接口或前后 SHA256 对比，并且不写真实 registry、`promotions_log.json` 或 `rolling_detect_model`。
8. WHEN 历史 TSC candidate 缺少 provenance, THE PV_ThreeChain_Product_Validation_System SHALL 保持来源缺口可见，不补写 `source_execution_id`、`source_workflow_id` 或其他来源字段，也不强制正式复验或 Promote。
9. IF `expected_registry_version` 与目标 scoped registry 当前版本不一致, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝写入并返回版本冲突和重新读取 registry 的下一步。
10. WHEN Promote 成功, THE PV_ThreeChain_Product_Validation_System SHALL 记录目标 `project_id`、`production_slot`、candidate 自身来源、正式 `verification_id`、前后 `registry_version`、操作者、原因和时间。

### R10：项目化精度运营与证据口径

**用户故事：** 作为产品经理，我希望看见当前项目精度数字的来源和限制，而不是一个诱导决策的孤立百分比。

#### Acceptance Criteria

1. WHEN 用户在精度运营页查看任意有效 `(project_id, slot)`, THE PV_ThreeChain_Product_Validation_System SHALL 展示 `dataset_version_id`、指标来源、样本量、人工真值覆盖、时间范围或会话范围和当前 scope。
2. IF 当前 scope 没有可统计的人工审核结果, THEN THE PV_ThreeChain_Product_Validation_System SHALL 显示“未产出”或等价事实说明，而不显示 0% 作为精度。
3. WHEN 用户在 TSC 精度运营页查看证据, THE PV_ThreeChain_Product_Validation_System SHALL 并列解释历史人工审核 Accuracy、strict 训练评测、固定标签空间 `macro_f1_mean`、稀疏日期和当前不可直接 Promote 的关系，并明确 Macro-F1 不等于 Accuracy 且两者不可替代。
4. WHEN 指标低分、数据不足或不可直接比较, THE PV_ThreeChain_Product_Validation_System SHALL 展示解释性文案和下一步证据路径。
5. WHEN 指标低分、数据不足或不可直接比较, THE PV_ThreeChain_Product_Validation_System SHALL 不将这些状态作为自动改参数、放宽合同或降低隔离要求的触发器。
6. WHEN 用户查看精度运营页, THE PV_ThreeChain_Product_Validation_System SHALL 保持该页面只读，并且不隐式触发重训、candidate 登记、verification 或 registry 更新。
7. IF 精度证据的 `project_id`、`slot` 或 `dataset_version_id` 与当前 scope 不一致, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝聚合或展示该证据。

### R11：浏览器 E2E、错误可见性与安全演示

**用户故事：** 作为验收人员，我希望能在浏览器中验证现有三链和跨数据集故事线，同时确认没有因为演示而污染 production 数据或治理真源。

#### Acceptance Criteria

1. WHEN 浏览器 E2E 执行 `pv_day`、`pv_point` 或 `pv_tsc` 的现状验收, THE PV_ThreeChain_Product_Validation_System SHALL 至少覆盖部署 / 模型状态、检测 / replay、审核、累计 / freeze 和精度 / 证据五类页面的只读走读。
2. WHEN 浏览器 E2E 保存验收证据, THE PV_ThreeChain_Product_Validation_System SHALL 保存相对路径截图、访问路由、当前 `project_id`、`slot`、`dataset_version_id`、console 错误摘要、page error 摘要以及 401、403 和 5xx 网络请求记录。
3. WHEN 浏览器 E2E 访问每个测试路由, THE PV_ThreeChain_Product_Validation_System SHALL 验证适用的 loading、空、错误、数据不足、scope mismatch 和禁用或只读状态。
4. IF 某测试路由未出现适用状态, THEN THE PV_ThreeChain_Product_Validation_System SHALL 在验收记录中说明该状态未出现的原因，而不省略该状态结论。
5. WHEN TSC canonical label workflow 执行完整验收, THE PV_ThreeChain_Product_Validation_System SHALL 将输出写入 Sandbox 目录，并核验真实 proposal 索引、candidate、registry、production cursor 和训练状态真源未被污染。
6. WHEN validation 或 sandbox 执行读取 `model_candidates.json`、`registry.json`、`label_proposals.json` 或其他适用 production 真源, THE PV_ThreeChain_Product_Validation_System SHALL 记录前后 SHA256；无预期 production 写入时前后哈希 SHALL 相同。
7. WHEN 验收运行保存图片、报告、输入或工件路径, THE PV_ThreeChain_Product_Validation_System SHALL 使用相对路径，并且不在验收产物中写入口令、token、机器绝对路径或业务数据库连接信息。
8. WHEN 浏览器 E2E 在项目 A 与项目 B 之间切换, THE PV_ThreeChain_Product_Validation_System SHALL 验证旧 scope 状态已清空且迟到响应未渲染到新项目。
9. WHEN 浏览器 E2E 未获得明确人工 production 写入授权, THE PV_ThreeChain_Product_Validation_System SHALL 将 `production_writes_authorized` 视为 `false`。
10. WHEN 浏览器 E2E 执行 production 真源零污染检查, THE PV_ThreeChain_Product_Validation_System SHALL 先记录每个适用真源的相对引用、存在性与适用状态，再计算前后 SHA256；真源缺失时必须记录 `MISSING`（真源缺失）或 `NOT_APPLICABLE`（不适用），而不伪造相同哈希。

### R12：构建、回归与交接

**用户故事：** 作为后续接手者，我希望知道本轮具体改了什么、验证了什么、哪些事实未验证，能安全复现而不误改工作区。

#### Acceptance Criteria

1. WHEN 后续实现改动包含应用代码、配置或运行合同, THE PV_ThreeChain_Product_Validation_System SHALL 按受影响范围运行最相关的后端语法检查 / focused pytest、前端 TypeScript 检查或生产构建，并记录未运行的非受影响检查。
2. WHEN 验证命令产生 warning, THE PV_ThreeChain_Product_Validation_System SHALL 将既有 warning 与本轮新增 warning 分别记录。
3. WHEN 验收完成前执行自审, THE PV_ThreeChain_Product_Validation_System SHALL 重读每个变更文件，并检查未使用 import、死代码、状态遗漏、scope、相对路径、路由风险和 AI 标记配对。
4. WHEN 验收完成前执行工作区检查, THE PV_ThreeChain_Product_Validation_System SHALL 使 `git diff --check` 无错误。
5. WHEN 本轮变更在已有脏工作区中执行, THE PV_ThreeChain_Product_Validation_System SHALL 保留无关改动、删除和运行产物，不清理、重置、覆盖或提交既有内容。
6. WHEN 交接材料生成, THE PV_ThreeChain_Product_Validation_System SHALL 分别列出变更文件及职责、已验证事实、未验证事项、未执行 production 写入、风险和下一步。
7. WHEN 交接材料描述 experiment、validation、sandbox 或跨数据集产品复验结果, THE PV_ThreeChain_Product_Validation_System SHALL 将结果表述为实验或验证结果，而不表述为 production 上线、正式 verification passed 或已 Promote。
8. WHEN 交接材料列出文件路径或内部符号, THE PV_ThreeChain_Product_Validation_System SHALL 说明每个文件或符号的职责以及与本次变更的关系。
9. WHERE 本轮变更仅涉及 Markdown 规格或说明文档, THE PV_ThreeChain_Product_Validation_System SHALL 执行文档结构、编号、需求追踪、AI marker、相对路径和 diff 检查，并把未运行应用构建或测试记录为“改动范围不涉及”而不是验证失败。

### R13：多项目、多数据集接入、readiness 与 lineage

**用户故事：** 作为交付实施人员，我希望从浏览器为独立项目接入非内置数据、确认数据语义并获得三条路径各自的兼容性结论，以便无需终端或客户专用代码即可安全复用产品能力。

#### Acceptance Criteria

1. THE PV_ThreeChain_Product_Validation_System SHALL 将新项目 dataset、execution、review、累计、snapshot、candidate、verification、registry、cursor、Sandbox 和结果的最低隔离范围定义为 `(project_id, slot)`。
2. IF 新项目 API 请求缺少有效 `project_id` 或 scoped 对象不存在, THEN THE PV_ThreeChain_Product_Validation_System SHALL fail-closed，并且不 silent fallback 到 `legacy`、其他项目或历史同槽对象。
3. WHEN 用户创建空项目, THE PV_ThreeChain_Product_Validation_System SHALL 返回新的 `project_id` 和空生命周期，并且不继承 legacy 或其他项目的累计、candidate、registry、review、cursor 或结果。
4. WHEN 项目 A 与项目 B 在相同 `slot` 中并存, THE PV_ThreeChain_Product_Validation_System SHALL 使两个项目的 dataset、execution、review、累计、snapshot、candidate、verification、registry、cursor、Sandbox 和结果互不可读写串用。
5. WHEN 用户确认字段映射并发布数据, THE PV_ThreeChain_Product_Validation_System SHALL 创建版本化 `dataset_profile_id` 和不可变 `dataset_version_id`，并保存相对 `artifact_ref`、内容摘要与数据来源说明。
6. WHEN execution、Sandbox result、review、可选 snapshot、可选 candidate 或 `ValidationEvidenceBundle` 来源于已发布数据版本, THE PV_ThreeChain_Product_Validation_System SHALL 保留相同 `project_id`、`slot`、`dataset_version_id` 和 `dataset_profile_id` lineage。
7. WHEN 用户通过浏览器接入数据, THE PV_ThreeChain_Product_Validation_System SHALL 支持上传 CSV / Parquet、选择平台数据资产或选择已授权 connector，并且不要求用户输入服务器文件路径。
8. WHEN 用户配置字段映射, THE PV_ThreeChain_Product_Validation_System SHALL 要求确认时间列、时区、格式、采样频率、重复点策略和迟到点策略。
9. WHEN 用户配置实体与测量映射, THE PV_ThreeChain_Product_Validation_System SHALL 要求确认 `site_id`、`device_id`、`branch_id`、`value`、`i_cal`、单位、缩放和缺失策略。
10. WHEN 用户配置标签映射, THE PV_ThreeChain_Product_Validation_System SHALL 要求确认标签列、标签字典、未知标签策略以及点级、区间级或设备日级标签粒度。
11. IF 用户尝试将设备日标签映射为 `pv_point` 点级真值, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝该映射并说明需要点级或区间级真值。
12. WHEN 已发布映射需要修改, THE PV_ThreeChain_Product_Validation_System SHALL 创建新的 `dataset_profile_id`，并在重新发布后建立新的数据版本关联，而不静默修改原 profile 或原版本。
13. WHEN 数据画像生成, THE PV_ThreeChain_Product_Validation_System SHALL 展示行数、时间范围、实际离散日期、实体覆盖、采样完整性、最大空洞、单位、缺失、异常值、标签粒度、类别分布和各路径表示可形成性。
14. WHEN 页面展示数据画像事实, THE PV_ThreeChain_Product_Validation_System SHALL 同时展示该事实对路径运行或评测的影响以及可执行的修复建议。
15. WHEN 用户查询一个已发布数据版本的路径兼容性, THE PV_ThreeChain_Product_Validation_System SHALL 为 `pv_day`、`pv_point` 和 `pv_tsc` 分别返回 `ready`、`experiment_only`、`needs_mapping`、`needs_labels`、`insufficient_data` 或 `unsupported` 中的一个状态。
16. WHEN 系统返回 `PathReadiness`, THE PV_ThreeChain_Product_Validation_System SHALL 同时返回 `project_id`、`slot`、`dataset_version_id`、`dataset_profile_id`、`facts`、`blockers`、`allowed_run_modes` 和 `next_action`。
17. WHEN `PathReadiness.status=ready`, THE PV_ThreeChain_Product_Validation_System SHALL 将该状态解释为当前路径输入与预检合同可用，而不将该状态解释为 production 资格、candidate 资格或 Promote 资格。
18. WHEN `PathReadiness.status=experiment_only`, THE PV_ThreeChain_Product_Validation_System SHALL 允许 experiment 或适用 Sandbox 动作，并保持 production 动作禁用。
19. WHEN `PathReadiness.status` 为 `needs_mapping`、`needs_labels`、`insufficient_data` 或 `unsupported`, THE PV_ThreeChain_Product_Validation_System SHALL 展示具体事实、阻断动作和最短下一步，而不伪造 `ready`。
20. WHEN 一个不可变数据版本同时满足三条路径合同, THE PV_ThreeChain_Product_Validation_System SHALL 允许同一验收批次将该版本分配给三个 `slot`，并保持每条路径独立的 readiness、workflow、execution 和证据。
21. WHEN 没有单一数据版本同时满足三条路径合同, THE PV_ThreeChain_Product_Validation_System SHALL 允许同一验收批次为每个 `slot` 分别选择兼容的非内置 `dataset_version_id`。
22. IF 验收数据仅是内置 demo 的重命名或复制且没有外部来源证据, THEN THE PV_ThreeChain_Product_Validation_System SHALL 不将该数据计入非内置数据覆盖。
23. WHEN 新项目 API 返回项目级结果, THE PV_ThreeChain_Product_Validation_System SHALL 回显 `project_id`、`slot=null` 和包含具体 `slot` 的路径状态集合。
24. WHEN 新项目 API 返回路径级数据结果, THE PV_ThreeChain_Product_Validation_System SHALL 回显具体 `project_id`、`slot` 和 `dataset_version_id`，而不要求 UI 自行推断 scope。
25. WHEN connector 数据被注册或预览, THE PV_ThreeChain_Product_Validation_System SHALL 持久化 `connector_id` 与逻辑对象描述，并且不在 API、日志或证据中暴露凭据。
26. WHEN workflow preflight、execution、Sandbox replay、review、可选 snapshot、可选 candidate 或产品复验证据引用输入数据, THE PV_ThreeChain_Product_Validation_System SHALL 使用已发布 `dataset_version_id`，而不使用可变临时上传文件替代版本绑定。
27. WHEN 同一数据版本存在多个 readiness 事实或 blocker, THE PV_ThreeChain_Product_Validation_System SHALL 按当前路径的显式输入、标签、数据量和评测合同推导状态、允许运行模式与下一步，并返回全部决定性事实，而不采用未在需求或路径合同中定义的固定全局优先级。

### R14：跨数据集产品复验、隔离 Sandbox 与非升级治理

**用户故事：** 作为验收人员和发布负责人，我希望使用非内置数据在隔离环境中验证三条路径的产品迁移性与项目隔离，同时确保产品复验不会被误当成正式模型复验或 production 资格。

#### Acceptance Criteria

1. WHEN 系统创建跨数据集产品复验批次, THE PV_ThreeChain_Product_Validation_System SHALL 生成 `cross_dataset_product_validation_id`，将治理效力固定为 none，并且不把该 ID 写入 `verification_id` 字段。
2. WHEN `run_domain=sandbox`, THE PV_ThreeChain_Product_Validation_System SHALL 将水位、cursor、review、accuracy 和 result 写入对应 `(project_id, sandbox_id, slot)` 的隔离状态根，而不写入 production scope。
3. WHEN execution 的 `run_mode=validation` 或 `run_domain=sandbox`, THE PV_ThreeChain_Product_Validation_System SHALL 对 candidate、registry、proposal、production cursor、review、累计和 Promote 审计等适用 production 真源执行前后 SHA256 零污染断言。
4. WHEN 跨数据集产品复验完成或通过, THE PV_ThreeChain_Product_Validation_System SHALL 保持 candidate、正式 verification、`rolling_detect_model`、Promote 和 production 资格不变，并拒绝使用产品复验 ID 执行上述治理动作。
5. WHEN Sandbox 执行三条路径或用户查看 TSC production 状态, THE PV_ThreeChain_Product_Validation_System SHALL 保持 day 设备日、point event-time 逐点因果 replay、TSC 设备日冻结预测图以及 TSC production 只读的真实路径语义。
6. THE PV_ThreeChain_Product_Validation_System SHALL 将 `run_mode` 限定为 `experiment`、`validation` 或 `production`，将 `run_domain` 限定为 `production` 或 `sandbox`，并将 read-only 状态作为独立维度处理。
7. WHEN 新数据版本首次启动运行且请求未显式选择 `run_mode`, THE PV_ThreeChain_Product_Validation_System SHALL 使用 `run_mode=experiment` 并在响应中显式回显该默认值。
8. WHEN 用户请求 `run_mode=production`, THE PV_ThreeChain_Product_Validation_System SHALL 要求显式选择，并校验项目、槽位、数据版本、readiness、来源、权限、评测和人工意图门禁。
9. IF `run_domain=sandbox` 请求缺少有效 `sandbox_id`, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝启动或恢复 Sandbox。
10. WHEN 用户重置 Sandbox, THE PV_ThreeChain_Product_Validation_System SHALL 仅重建目标 `sandbox_id` 的隔离状态，并保持项目 production 状态与其他 Sandbox 不变。
11. WHEN `pv_day` 在 Sandbox 中回放, THE PV_ThreeChain_Product_Validation_System SHALL 按完整设备日形成统计表示和日结果，并说明当前 production 仍使用 quickval predict 图。
12. WHEN `pv_point` 在 Sandbox 中回放, THE PV_ThreeChain_Product_Validation_System SHALL 按 event-time 逐真实点推进，并使当前点结果仅依赖当前点之前的 committed history。
13. WHEN `pv_tsc` 在 Sandbox 中回放, THE PV_ThreeChain_Product_Validation_System SHALL 按设备日运行冻结预测图，保存 288×3 合同、多窗口证据和 execution，并保持 production 观测只读。
14. WHEN 系统创建跨数据集产品复验批次, THE PV_ThreeChain_Product_Validation_System SHALL 接受一个共享非内置数据版本覆盖三条路径，或接受每条路径分别分配一个兼容非内置版本。
15. WHEN 跨数据集产品复验判定路径覆盖, THE PV_ThreeChain_Product_Validation_System SHALL 要求 `pv_day`、`pv_point` 和 `pv_tsc` 每条路径至少由一个非内置数据版本完成要求场景。
16. WHEN 黄金验收开始, THE PV_ThreeChain_Product_Validation_System SHALL 从不继承 legacy 状态的空项目创建开始，并依次记录数据接入、字段映射、画像、版本发布、readiness、workflow 绑定、preflight、experiment 或 validation、Sandbox replay、受控 review、lineage 和治理门控证据。
17. WHEN 黄金验收执行 workflow preflight 或 execution, THE PV_ThreeChain_Product_Validation_System SHALL 将当前 `project_id`、`slot`、`dataset_version_id`、`workflow_id`、`run_mode` 和 `run_domain` 写入请求、execution 与响应证据。
18. WHEN 黄金验收执行受控 review, THE PV_ThreeChain_Product_Validation_System SHALL 使用 Sandbox review 或只读历史证据，并且不把 Sandbox verdict 作为 production ground truth。
19. WHERE 人工明确授权 `production_writes_authorized=true`, THE PV_ThreeChain_Product_Validation_System SHALL 将 complete-and-admit、freeze 和再训练作为三个独立确认动作，并在每次动作前显示目标 scope、影响真源和副作用。
20. WHEN 黄金验收未获得明确 production 写入授权, THE PV_ThreeChain_Product_Validation_System SHALL 跳过真实准入、freeze、production 重训、正式 verification、滚动指针和 Promote。
21. WHEN 项目 A 的三路径场景完成后创建项目 B, THE PV_ThreeChain_Product_Validation_System SHALL 在与项目 A 相同 `slot` 下运行项目 B 场景，并验证累计、snapshot、candidate、registry、review、cursor、Sandbox 和 result 零串场。
22. WHEN 跨数据集产品复验汇总结果, THE PV_ThreeChain_Product_Validation_System SHALL 展示三路径数据分配、readiness、execution、Sandbox、lineage、浏览器证据、SHA256 和项目隔离结论。
23. WHEN 模型精度较低但产品流程、证据合同和隔离成立, THE PV_ThreeChain_Product_Validation_System SHALL 将低精度记录为事实与限制，而不将低精度单独判定为产品复验失败。
24. WHEN 某个数据版本不支持某条路径但同批次另一个非内置版本完成该路径覆盖, THE PV_ThreeChain_Product_Validation_System SHALL 将批次记录为分路径版本方案，而不强制伪造单版本三路径兼容。
25. WHEN 数据不足阻止 production 但允许 experiment 或 Sandbox, THE PV_ThreeChain_Product_Validation_System SHALL 保留 experiment / Sandbox 产品复验能力并准确禁用 production 动作。
26. WHEN 跨数据集产品复验证据归档, THE PV_ThreeChain_Product_Validation_System SHALL 使用相对路径保存 `ValidationEvidenceBundle`，并记录未执行的 production 写入与治理动作。

### R15：离线 benchmark 证据的诚实展示护栏

**用户故事：** 作为算法工程师、审核人员或发布负责人，我希望平台在展示已执行的外部数据离线证据（含 PVDAQ `i_cal` 消融）时忠实标注其边界，使离线结果不会被误当成平台闭环验收或生产资格。

**范围说明：** 本需求是**只读证据展示护栏**，不是评测科学建设需求。它不要求平台新建配对比较引擎、逐 split 审计工作台或校准拟合能力；逐 split 指标、配对身份与设备覆盖细节保留在既有只读简报与冻结工件中。

#### Acceptance Criteria

1. WHEN 平台登记或展示外部数据离线结果, THE PV_ThreeChain_Product_Validation_System SHALL 将其类型标识为 `offline_benchmark_evidence` 且治理效力为 none，并且不因该登记创建或推断平台 workflow execution、浏览器 E2E、candidate、正式 verification、production 资格或 Promote 结果。
2. WHEN 既有冻结 benchmark 工件以平台资产登记, THE PV_ThreeChain_Product_Validation_System SHALL 校验并保存每个已声明源文件的内容摘要与相对引用、将其绑定到不可变 `benchmark_evidence_version`，并保持冻结源文件只读，不覆盖、不补写、不替换、不原地修改。
3. IF 任一已声明源文件缺失、不可读取、摘要不匹配或相对引用无法解析, THEN THE PV_ThreeChain_Product_Validation_System SHALL 将该登记 fail-closed 标识为 blocked，不将其计为有效 `benchmark_evidence_version`，不基于该资产形成任何结论，并保持冻结工件、既有证据版本与 production 真源不变。
4. WHEN 离线证据或 execution 使用 `i_cal`, THE PV_ThreeChain_Product_Validation_System SHALL 要求显式声明 `leaky_device_ical`、`value_only`、`global_train_devices_only` 或 `history_past_only` 中的一个 `i_cal_contract` 与可解析的 `calibration_audit_id`，将两者一同持久化到数据版本绑定、execution、`evaluation_contract` 和证据，且不推断或回退到默认合同。
5. WHERE `i_cal_contract=leaky_device_ical`, THE PV_ThreeChain_Product_Validation_System SHALL 固定标记 `leakage_upper_bound=true`、`governance_eligible=false` 与 diagnostic experiment，拒绝 production、candidate、正式 verification、`rolling_detect_model` 与 Promote 消费，并保持相关 production 真源不变。
6. IF `i_cal_contract` 或 `calibration_audit_id` 缺失、不受支持、彼此冲突或无法解析，或声称非泄漏的证据无可核查依据说明 `outer_test_truth` 未参与校准拟合与选择, THEN THE PV_ThreeChain_Product_Validation_System SHALL 将受影响证据标识为 unknown / blocked，不回退到任何默认合同，停止其 leakage-safe 与 production 结论，保持治理动作禁用，并显示缺失或冲突事实及所需下一步。
7. IF 某个统计范围没有正类样本, THEN THE PV_ThreeChain_Product_Validation_System SHALL 将该范围的 PR-AUC 与异常 precision、recall、F1 显示为 N/A 而不是 0，显示 `metric_applicability` 原因与类别支持度，并禁止将这些 N/A 值按 0 纳入均值、门槛判断或胜负结论。
8. WHEN 可用的独立不可变 `benchmark_evidence_version` 少于两个, THE PV_ThreeChain_Product_Validation_System SHALL 将 `repeatability_status` 显示为 `not_reverified`，并且不将同一次运行内的多次重复或多个 fold 表述为独立重复性复验。
9. WHEN 用户映射或查看 `i_cal`, THE PV_ThreeChain_Product_Validation_System SHALL 将 `i_cal` 说明为期望电流参照而非 ground truth，要求确认单位、尺度、生成方法、数据可用时点与缺失策略；IF 数据 profile 仅提供 `rated_power_kw` 而无经验证的电流尺度转换合同, THEN 系统 SHALL 将额定功率标识为辅助元数据并不默认生成任何 `i_cal_contract`。
10. WHEN 外部数据集只有设备日标签而需要在 `pv_point` 上使用, THE PV_ThreeChain_Product_Validation_System SHALL 仅允许按 event-time 执行无标签 Sandbox 因果 replay、将 supervised readiness 显示为 `needs_labels`，并拒绝把设备日标签作为点级 truth、supervised point 精度依据或 production 点路径证据。
11. WHEN `offline_benchmark_evidence`、`cross_dataset_product_validation_id` 或 `verification_id` 被提交给读取、展示或治理流程, THE PV_ThreeChain_Product_Validation_System SHALL 按声明类型分别处理：前两者治理效力均为 none，`verification_id` 仅在其 candidate、scope、`evaluation_contract` 与关联评测 execution 全部通过正式门控后表示候选正式复验；三类标识不得转换、复制或互相替代。
12. IF 证据标识的类型缺失、未知、与持久化类型冲突，或调用方使用 `offline_benchmark_evidence` 或 `cross_dataset_product_validation_id` 替代正式 candidate verification, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝该治理消费或写入请求，不推断默认类型，不创建或更新 candidate、正式 verification、registry、`rolling_detect_model` 或 Promote 审计，并显示已提交类型、所需正式证据类型与下一步。

### Non-Functional Requirements

### NFR1：相对路径、不可变引用与可迁移性

**用户故事：** 作为跨 Windows、macOS 与 Linux 部署的接手者，我希望持久化证据不依赖某台开发机的目录结构，以便安全复现验收和产品行为。

#### Acceptance Criteria

1. THE PV_ThreeChain_Product_Validation_System SHALL 在代码、数据文件以及持久化输入、数据版本、模型工件、snapshot、截图、验收报告、execution、registry 和文档中使用项目内相对路径或 `connector_id`。
2. IF 任意待持久化字段包含机器绝对路径, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝该字段或转换为符合项目根或 `backend-service/` 解析约定的相对路径后再持久化。
3. WHEN 页面、API 或验收产物引用文件, THE PV_ThreeChain_Product_Validation_System SHALL 使该引用可由项目根或 `backend-service/` 的相对路径解析约定定位。
4. WHEN 数据版本发布, THE PV_ThreeChain_Product_Validation_System SHALL 保存不可变内容摘要和相对 `artifact_ref`，并且不在同一 `dataset_version_id` 下静默替换内容。
5. WHEN connector 作为数据来源, THE PV_ThreeChain_Product_Validation_System SHALL 以 `connector_id` 和逻辑对象描述表达来源，而不持久化连接凭据或机器挂载路径。
6. WHEN 后端解析相对输入或工件引用, THE PV_ThreeChain_Product_Validation_System SHALL 沿用项目既有的 `project_root`（项目根）、`backend_dir`（后端服务目录）与 `cwd`（当前工作目录）相对路径搜索约定，并且不把运行时解析得到的机器绝对路径写回持久化结果。

### NFR2：安全默认、scope 校验与最小副作用

**用户故事：** 作为发布负责人，我希望产品默认不会因为浏览器浏览、项目切换或自动验收改变 production 数据或模型治理。

#### Acceptance Criteria

1. THE PV_ThreeChain_Product_Validation_System SHALL 将产品默认交互设为只读，将新数据首次运行默认设为 `experiment`，并将无人值守验收的 `production_writes_authorized` 默认设为 `false`。
2. WHEN 请求可能改变累计数据、candidate、verification、registry、`rolling_detect_model` 或 Promote 审计, THE PV_ThreeChain_Product_Validation_System SHALL 在服务端校验目标 `project_id`、`slot`、数据版本、来源、`run_mode`、`governance_eligible`、前置门控和显式人工意图。
3. WHEN 浏览器自动化未获得明确人工确认, THE PV_ThreeChain_Product_Validation_System SHALL 不调用真实 product write 接口。
4. IF validation、experiment 或 sandbox 请求尝试写入 production candidate、registry、真实 proposal、滚动指针或 Promote 审计, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝请求或将该运行允许的非 production 输出写入对应 Sandbox 隔离真源。
5. IF 新项目请求尝试读取或写入 legacy 或其他项目的 scoped 真源, THEN THE PV_ThreeChain_Product_Validation_System SHALL 拒绝请求并返回 scope 门控原因。
6. WHEN 高风险 product write 进入确认阶段, THE PV_ThreeChain_Product_Validation_System SHALL 展示目标项目、槽位、数据版本、影响对象、可回滚性和操作者意图。

### NFR3：可访问性与可读性

**用户故事：** 作为桌面工作台使用者，我希望不用依赖颜色或内部 JSON 就能理解当前项目、状态、原因和下一步。

#### Acceptance Criteria

1. WHEN 页面展示状态, THE PV_ThreeChain_Product_Validation_System SHALL 同时提供文本、状态标签或图标，而不将颜色作为唯一信息通道。
2. WHEN 页面展示按钮、表格、错误、禁用原因或下一步, THE PV_ThreeChain_Product_Validation_System SHALL 在桌面工作台密度下提供可读文本。
3. WHEN 原始 JSON 可供诊断, THE PV_ThreeChain_Product_Validation_System SHALL 将原始 JSON 保持在次级展开区域，而不以原始 JSON 替代主要中文说明。
4. WHEN 页面展示项目、数据版本、路径、运行模式或运行域, THE PV_ThreeChain_Product_Validation_System SHALL 使用可见文本标识当前上下文，而不要求用户从 URL 或内部 ID 猜测。
5. WHEN 按钮因门控禁用, THE PV_ThreeChain_Product_Validation_System SHALL 使禁用原因和最短下一步可通过键盘聚焦或相邻文本读取。
6. WHEN 页面展示动作状态、横切状态、禁用原因类型、readiness 状态或阶段名, THE PV_ThreeChain_Product_Validation_System SHALL 从单一集中文案模块按键取用展示措辞，使同一状态在所有页面显示相同措辞，而不在各组件内散落字符串字面量。
7. WHEN 系统需要判断状态或分支, THE PV_ThreeChain_Product_Validation_System SHALL 使用稳定的 `reason_code` 或状态枚举名，而不使用中文展示文案作为判断条件。
8. WHERE pv_fault 项目工作台第一阶段为中文界面, THE PV_ThreeChain_Product_Validation_System SHALL 将该范围在切换英文时仍显示中文记录为已声明的已知行为，并且不把该区域表述为已支持多语言。

### NFR4：性能、分页与恢复

**用户故事：** 作为需要处理长时任务和多项目证据的用户，我希望离开页面后仍能恢复读取状态，并在不加载巨大 payload 的情况下理解当前阶段。

#### Acceptance Criteria

1. WHEN profile、freeze、训练、正式 verification 或 connector 物化是长时任务, THE PV_ThreeChain_Product_Validation_System SHALL 持久化任务的 `project_id`、适用 `slot`、适用 `dataset_version_id`、任务 ID、`execution_id` 和状态，使用户离开页面后仍能按相同 scope 重新读取。
2. WHEN 主页面加载阶段证据, THE PV_ThreeChain_Product_Validation_System SHALL 优先加载当前 scope 的状态摘要和关联 ID。
3. WHEN 用户请求详细 execution、画像或原始证据, THE PV_ThreeChain_Product_Validation_System SHALL 按需展开详细内容，以避免大 payload 使状态面板不可用。
4. WHEN TSC execution 或设备日结果数量超过单页容量, THE PV_ThreeChain_Product_Validation_System SHALL 按项目、数据版本、日期和设备提供分页或等价的有界查询。
5. WHEN 用户刷新或返回长任务页面, THE PV_ThreeChain_Product_Validation_System SHALL 从持久化任务状态恢复当前进度，而不依赖前端内存状态。

## Traceability and Completion Criteria

| 需求范围 | 设计章节（`design.md`） | 实施任务（`tasks.md`） | 最小验收产物 |
|---|---|---|---|
| R1 | §7 目标 scope 与 legacy 兼容、§11.3 项目切换与 scope 清空、§26.4 字段全链路 | 任务 1 | `project_id → slot → dataset_version_id` 字段流转、项目切换清空测试、scope mismatch 状态、API 回显断言。 |
| R2 | §22 统一生命周期状态模型、§23 逐页交互与状态合同 | 任务 2、任务 3 | 十类页面的空 / 加载 / 错误 / 禁用 / 成功状态与恢复走读。 |
| R3 | §16 模型与治理、§26.2 REST 合同、§26.3 数据模型 | 任务 1、任务 4 | 项目化 registry 读取证据、legacy 只读说明、指针与候选历史区分。 |
| R4 | §17 检测与回放、§21 pv_point 运行会话、§23.1 会话动作合同 | 任务 5、任务 6、任务 7 | 三链检测事实对照、day quickval 说明、point 因果 replay、TSC production 只读证据。 |
| R5 | §18 审核与精度、§20 pv_tsc canonical 打标 | 任务 4、任务 7 | 提案来源说明、canonical 与 shortcut 区分、`review_slot` 审核走读。 |
| R6 | §19 累计训练集与再训练、§26.3 数据模型 | 任务 4 | 入账、freeze、snapshot lineage 与幂等命中证据。 |
| R7 | §15 工作流与运行、§26.3 数据模型、§26.5 错误响应 | 任务 3 | execution 证据完整性、状态恢复、validation 不可治理断言。 |
| R8 | §16 模型与治理、§22.2 状态转换与并发规则 | 任务 4 | 候选 provenance 门控、正式复验绑定、空态与阻断原因测试。 |
| R9 | §16 模型与治理、§24 权限与高风险动作 | 任务 4 | 滚动指针与 Promote 的 scope、版本冲突和审计负向测试。 |
| R10 | §18 审核与精度、§30.1 证据诚实边界 | 任务 4、任务 8 | 精度口径与“未产出”展示、低分不触发自动调参的证据。 |
| R11 | §27 跨数据集产品复验与黄金验收、§29.2 测试分层 | 任务 8、任务 9 | 浏览器 E2E 的路由 / scope / console / network 记录与 SHA256 零污染。 |
| R12 | §29.2 测试分层、§30.3 交付检查清单 | 任务 9 | 构建与 focused 测试记录、`git diff --check`、自审与交接说明。 |
| R13 | §13 数据接入向导、§25 数据 readiness 合同、§26.3 数据模型 | 任务 2 | 浏览器接入证据、字段映射、profile、不可变版本、三路径 readiness、A/B 隔离测试。 |
| R14 | §8 运行模式与运行域、§17 检测与回放、§27 跨数据集验收 | 任务 6、任务 8 | 三路径非内置数据覆盖、产品复验证据包、Sandbox scoped 状态、非升级治理断言。 |
| R15 | §2 三类证据区分、§30.1 PVDAQ 只读离线证据案例 | 任务 8 | 冻结工件只读登记、合同与审计标注、N/A 展示、三类证据不可互换与治理拒绝测试。 |
| NFR1 | §26.3 最小数据模型、§26.5 统一错误响应、§30.3 交付检查清单 | 任务 1、任务 2 | 相对路径扫描、不可变内容摘要、凭据脱敏、运行时绝对路径不回写持久化。 |
| NFR2 | §8 运行模式与运行域、§24 权限与安全体验、§27.3 零污染证据 | 任务 1、任务 8 | 只读默认、`experiment` 默认、服务端 scope 与门控拒绝、高风险确认区、未授权写入拒绝。 |
| NFR3 | §22.1 通用动作状态、§28.1–28.3 视觉 / 响应式 / 可访问性、§28.4 文案与状态词汇 | 任务 2、任务 9 | 非颜色单通道状态、禁用原因可聚焦、原始 JSON 二级化、对比度与键盘走查、集中状态词汇与中文范围声明。 |
| NFR4 | §26.6 有界查询、分页与长任务恢复、§23 逐页状态合同 | 任务 2、任务 3、任务 9 | 长任务持久化与刷新恢复、execution / 设备日 / 审核队列分页、按需展开明细。 |

### Completion Gate

1. WHEN 需求进入实现验收, THE PV_ThreeChain_Product_Validation_System SHALL 保持 R1–R14 与 NFR1–NFR4 的全部实质边界，并满足 R15 的离线证据诚实展示护栏。
2. WHEN 验收判定产品完成度, THE PV_ThreeChain_Product_Validation_System SHALL 以产品闭环、逐页可操作性、状态可解释性与隔离安全为完成条件，而不以模型精度指标达标或新建离线评测基础设施作为完成条件。
3. WHEN 设计正确性属性映射需求, THE PV_ThreeChain_Product_Validation_System SHALL 使 `design.md` §29.1 的 `P-SCOPE-01`、`P-LEGACY-01`、`P-LINEAGE-01`、`P-SANDBOX-01`、`P-GOV-01`、`P-GOV-02`、`P-PATH-01`、`P-POINT-01`、`P-TSC-01` 与 `P-UX-01` 分别可追踪到本文对应需求，并保持语义一致。
4. WHEN 跨数据集产品复验宣告 PASSED, THE PV_ThreeChain_Product_Validation_System SHALL 同时满足三路径非内置版本覆盖、scope 与 lineage 完整、Sandbox 与 production 隔离、A/B 零串场以及治理效力为 none。
5. WHEN 当前实现尚未完成目标能力, THE PV_ThreeChain_Product_Validation_System SHALL 将未实现项记录为待实施或未验证，而不以设计文档存在作为实现证据。
6. WHEN 已执行离线 benchmark 被用于需求验收或产品说明, THE PV_ThreeChain_Product_Validation_System SHALL 将该证据限定为离线 benchmark 事实，并且不把它表述为平台三路径 E2E、production-ready、正式 verification passed 或已 Promote。

<!-- @AI_GENERATED: end -->