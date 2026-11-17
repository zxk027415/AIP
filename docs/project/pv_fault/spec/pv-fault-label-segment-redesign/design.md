<!-- @AI_GENERATED -->
# 设计文档：光伏故障逐点标签重构（pv-fault-label-segment-redesign）

## 概览（Overview）

本设计把光伏故障诊断链路的标签存储从「测量表上的一个裸 `label` 列」改为「独立的逐点标签表 + 标注操作日志」，并把样本边界的确定从流水线算子内部上移到编排层的纯函数。落地遵循需求文档 22 条需求与 6 项架构决定（K1~K6）。

三条贯穿全设计的硬约束：

1. **零新增算子**（需求 9）：不新增 `operator_backends/` 下任何文件，不改 DAG 结构；算子层代码改动仅限 `extract_statistical_features.py` 与 `stratified_cv_eval.py` 两个文件、三处改动。
2. **标签唯一事实来源**（K1）：标签只存 `point_labels`（逐点）+ `label_ops`（操作日志），测量数据留在 `training_samples`；两者分表、分生命周期。
3. **样本边界只由标签形态与策略决定**（K2/K6）：编排层的 `Snapshot_Builder` 读逐点标签、按 `split_mode` 切样本、预物化出带 `sample_id`（含 `#`）的快照，使 `time_window_split.py` 退化为纯透传节点。

### 现状链路与目标链路对比

现状（标签散落，样本边界在算子内算）：

```
training_samples(含label裸列) ─┐
time_slices/*.csv ────────────┼→ _create_snapshot: concat+drop_duplicates(失效)
state.json.verdict_entries ───┘        │
                                       ▼
                        快照CSV → time_window_split(solar_mode按值切) → 特征 → cv_eval
```

目标（标签集中，样本边界在编排层算）：

```
label_ops(操作日志) ──materialize──→ point_labels(逐点真值)
                                          │
training_samples(纯测量) ─────────────────┤
                                          ▼
                     Snapshot_Builder(读逐点标签 + split_mode 切样本 + 赋 sample_id)
                                          │  每行 time_window = sample_id(含#)
                                          ▼
              快照parquet → time_window_split(纯透传) → 特征(+passthrough) → cv_eval(+group_col)
```

### 设计目标与非目标

- 目标：消除重复计数、标签冲突、标签稀释、撤销失效、跨会话重复打标、审核页无波形；支持跨天建模；白天/夜间按时钟判定。
- 非目标：不改多标签分类（保持单标签 `RandomForestClassifier`）；不引入天文日出日落（无经纬度数据）；不重写工作流引擎；不迁移 `dataset_combined.parquet`（完全冗余源）。

## 架构（Architecture）

### 组件分层与职责

| 层 | 组件 | 落点（新增/改造现有） | 职责 |
|---|---|---|---|
| 存储 | `PointLabel` / `LabelOp` ORM | 新增于 `backend-service/services/db/models/pv_fault.py` | 逐点标签表与操作日志表，`aip_algo_platform` 库 |
| 存储访问 | `PointLabelRepository` | 新增 `backend-service/services/db/repositories/point_label.py` | 两表的 CRUD、按设备+时间范围查询、重物化 |
| 领域服务 | `PointLabelService` | 新增 `backend-service/services/iterative_labeling/point_label_service.py` | 标注操作受理、不变量校验、K4 伴生操作、撤销联动 |
| 领域服务 | `LabelMaterializer` | 新增 `backend-service/services/iterative_labeling/label_materializer.py` | 按 `priority` 逐点物化，取代旧段裁剪 |
| 纯函数 | `SampleBuilder` | 新增 `backend-service/services/iterative_labeling/sample_builder.py` | 读逐点标签、按 `split_mode` 切样本、`daylight_window` 时钟判定 |
| 纯函数 | `DaylightWindowResolver` | 新增 `backend-service/services/iterative_labeling/daylight_window.py` | 按 `(site_id, 月份)` 推导/兜底日照时钟窗 |
| 编排 | `SnapshotBuilder` | 改造 `cumulative_training.py::_create_snapshot()` | 读逐点标签+测量→切样本→赋 `sample_id`→写快照 parquet |
| 编排 | `InferenceSampleGenerator` | 新增 `backend-service/services/iterative_labeling/inference_sample.py` | 预测侧按持久化策略切样本，不落库 |
| 迁移 | `MigrationTool` | 新增 `backend-service/scripts/migrate_point_labels.py` | 4 源迁入 `label_ops`+物化，产对账报告 |
| 算子 | `extract_statistical_features.py` | 改造（+`passthrough_fields`、分位数口径） | 见「算子改动」 |
| 算子 | `stratified_cv_eval.py` | 改造（+`group_col`、持久化 `sample_strategy`） | 见「算子改动」 |

### 关键设计取舍

- **逐点物化 vs 区间存储**（K1）：选逐点存储（1,056,806 行）而非区间（473~4,457 行），代价约 237~392 倍行数，换取「无区间差集运算、标签可逐点直查、冲突规则仅为一次 max(priority) 比较」。这是需求 21 第 2 条记录的已知取舍。
- **`label_ops` 承载区间**：区间不消失，只是从「标签权威」降级为「审计+撤销单元」。撤销 = `label_ops.status='revoked'` + 重物化受影响点，不物理删行。
- **物化范围最小化**：任一操作增删改只重算该操作 `[t_start,t_end)` × 该设备维度的点（需求 4 第 7 条），不全表重算。

### 存储载体决策

`point_labels` / `label_ops` 作为两张新 ORM 表加入现有 `aip_algo_platform` 库（复用 `services/db/models/base.py` 的 `Base`、`DBAdapter.get_sync_session()`），与现有 `TrainingSample` 同库同 adapter，不新起数据库、不用文件/JSON（需区间查询与并发串行化）。`state.json` 保留但职责收窄为只管重训状态机（需求 14 第 18 条）。

## 数据模型（Data Model）

### `point_labels` 表（逐点标签，需求 2 第 1 条）

新增 ORM 模型 `PointLabel`，`aip_algo_platform` 库（`_SCHEMA=None`），字段：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `site_id` | String(128) | PK 组成 | 站点标识 |
| `device_id` | String(128) | PK 组成 | 设备标识 |
| `branch_id` | String(128) | PK 组成 | 支路标识 |
| `time` | DateTime | PK 组成 | 采样时刻 |
| `label_id` | Integer | nullable | 生效标签，NULL=unknown |
| `source` | String(32) | not null | 来源枚举（见需求 3 第 1 条） |
| `priority` | Integer | not null | 由 source 唯一推导 |
| `op_id` | String(16) | not null, index | 产生该生效标签的操作 |
| `label_space_version` | String(64) | not null | 写入时标签空间版本 |
| `updated_at` | DateTime | default utcnow | |

- 主键 `(site_id, device_id, branch_id, time)` 天然满足需求 2 第 11 条（同点唯一）与需求 4 第 3 条。
- 索引：主键 + `Index(op_id)`（供撤销时按操作反查受影响点）。
- 无任何测量数值列（需求 2 第 10 条），`value`/`i_cal` 只在 `training_samples`。

### `label_ops` 表（标注操作日志，需求 2 第 2 条）

新增 ORM 模型 `LabelOp`，字段：

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `op_id` | String(16) | PK | 格式 `op-{hex12}` |
| `site_id`/`device_id`/`branch_id` | String(128) | not null, 复合 index | 设备三元组 |
| `t_start` | DateTime | not null | 区间起点（闭） |
| `t_end` | DateTime | not null | 区间终点（开） |
| `label_id` | Integer | nullable | 操作声明的标签 |
| `source` | String(32) | not null, index | 来源枚举 |
| `priority` | Integer | not null | 由 source 推导 |
| `status` | String(16) | not null, index | `active` / `revoked` |
| `reviewer` | String(128) | nullable | 标注人 |
| `source_ref` | String(256) | nullable | review_id/cluster_run_id/import_id/slice_id |
| `rest_of_day_policy` | String(16) | nullable | `normal` / `untouched`（K4） |
| `parent_op_id` | String(16) | nullable | 伴生操作指向主操作 |
| `label_space_version` | String(64) | not null | |
| `migration_batch_id` | String(64) | nullable | 迁移批次，人工新增为 NULL |
| `created_at` / `updated_at` | DateTime | | |

- 索引：`Index(site_id, device_id, branch_id, t_start, t_end)` + `Index(source, status)`（需求 2 第 6 条）。
- 不支持物理删除（需求 6 第 8 条），撤销仅 `status` 迁移。

### `source` → `priority` 映射（需求 3 第 1 条，由服务层强制）

`human_range`=100 · `human_day`=80 · `cluster`=50 · `day_label`=10 · `pseudo`=0。写入请求显式带 `priority` → HTTP 422（需求 3 第 3 条）。`inference` 不属枚举，写入即 422（需求 12 第 12 条）。

## 组件设计（Components）

### 1. `LabelMaterializer` — 标签物化器（需求 4）

取代旧方案的段裁剪算法。**没有任何区间差集运算**，只有一次排序取最大。

```python
# backend-service/services/iterative_labeling/label_materializer.py
def materialize(
    self,
    site_id: str, device_id: str, branch_id: str,
    t_start: datetime, t_end: datetime,
) -> dict:
    """重物化指定设备维度、指定时间范围的逐点标签。

    输入：设备三元组 + 半开区间。
    输出：{"points_written": int, "points_unknown": int, "ops_considered": int}
    调用方：PointLabelService（写入/撤销后）、MigrationTool。
    """
```

物化算法（需求 4 第 1 条）：

1. 查该设备维度下 `status='active'` 且与 `[t_start, t_end)` 有交集的全部 `label_ops`。
2. 查该范围内 `training_samples` 的采样时刻集合（标签只能落在真实存在的采样点上）。
3. 对每个采样点，从覆盖它的 active 操作中按 `(priority DESC, created_at DESC, op_id DESC)` 取第一条——三级排序保证结果对输入顺序无关（需求 4 第 4 条、需求 4 第 6 条的 `created_at` 由迁移用 `labeled_imports.sequence` 合成）。
4. 未被任何操作覆盖的点写 `label_id=NULL`（需求 4 第 5 条）。
5. 按主键 upsert 进 `point_labels`。

实现要点：不逐点循环查库。做法是把 ops 与采样点都拉进内存，用 `pandas.IntervalIndex` 或按时间排序的双指针求覆盖关系，一次批量 upsert。区间数量级极小（迁移后约 4,479 条 ops），采样点按设备维度分批，内存可控。

一致性校验（需求 4 第 8 条）：`verify(site_id, device_id, branch_id, t_start, t_end)` 重算并与库中现有 `point_labels` 比对，返回差异明细，供运维独立运行。

### 2. `PointLabelService` — 标注操作受理（需求 5、6、18、19）

唯一写入入口。所有写操作都是「校验 → 写 `label_ops` → 调 `LabelMaterializer` 重物化」三步，在同一事务内。

```python
def submit_op(
    self, *, site_id, device_id, branch_id,
    t_start: datetime, t_end: datetime,
    label_id: int | None, source: str, reviewer: str | None,
    source_ref: str | None, rest_of_day_policy: str = "normal",
) -> dict:
    """受理一次标注操作。返回 {"op_id", "companion_op_id", "materialized"}。"""
```

写入前不变量校验（需求 5 第 1、2、3、11、12 条）：

| 校验 | 失败行为 |
|---|---|
| `t_start < t_end` | ValueError |
| 边界对齐 300 秒栅格 | ValueError |
| `source` 以 `human_` 开头时 `reviewer` 与 `source_ref` 非空 | ValueError |
| 跨度 ≤ `max_op_span`（默认 31 天） | ValueError |
| `source='human_range'` 与另一条 active `human_range` 在同设备维度重叠 | HTTP 422，响应体含冲突 `op_id` 与重叠范围 |
| `label_id` 非 NULL 且不在当前 `label_space_version` | HTTP 422（需求 18 第 1、2 条） |
| 请求显式带 `priority` | HTTP 422 |
| `source='inference'` | HTTP 422 |

**K4「未框选即正常」的实现**（需求 5 第 4~10 条）：不引入残段概念，而是写**两条操作**，让既有的 `priority` 规则自然分出胜负。

```
标注人框选 2020-05-08 06:00~18:40，label=1，rest_of_day_policy=normal
        │
        ├─ 操作 A：source=human_range, priority=100, [06:00, 18:45), label_id=1
        └─ 操作 B：source=human_day,   priority=80,  [00:00, 次日00:00), label_id=0,
                   parent_op_id=A
        │
        ▼ LabelMaterializer 物化该设备该日
   06:00~18:40 的 153 点 → label=1（A 的 100 胜）
   当日其余 135 点        → label=0（B 的 80 胜，压过 day_label 的 10）
```

- `op_scope` 定义为 `(site_id, device_id, branch_id, 框选起点所属自然日)`（需求 5 第 5 条）。实测依据：自由段输入源 `pred-20260720092117-9348327a.csv` 含 189 个设备、跨 5 个不连续自然日，不限定范围会误判为覆盖全文件。
- 一次框选跨两个自然日 → 每个自然日各生成一条伴生操作（需求 5 第 6 条）。
- `rest_of_day_policy='untouched'` → 只写操作 A（需求 5 第 7 条）。
- 前端在框选弹窗提供该选项，默认勾选「本日其余时段判为正常」（需求 5 第 8 条）。

**撤销联动**（需求 6 第 3 条）：撤销操作 A 时按 `parent_op_id` 一并把 B 置 `revoked`，避免「问题时段撤了但『其余正常』还留着」。这直接修掉现状缺陷——`freeform_labeling.revoke_label()` 现在只删 session 指针、不动 `labeled_imports`，代码注释自认是 phase-2 遗留。

**跨会话重叠检查**（需求 16 第 2 条）：现状 `create_label()` 只用 `list_labels(review_id)` 在单会话内查重叠，跨会话可对同设备同时段重复打标。改为查 `label_ops` 全表（走 `Index(site_id, device_id, branch_id, t_start, t_end)`），检查范围覆盖所有 `review_id`。

**重训计数口径**（需求 19 第 7 条）：`pending_change_count` 按**操作**递增，一次框选产生的 A+B 两条操作只计 1 次。依据是现状 `state.json` 中自由段导入记的 `change_units=1`；K4 使一次框选影响点数从 153 涨到约 288，若按点计数则单次操作即超过默认阈值 20 并立刻触发重训。

### 3. `DaylightWindowResolver` — 日照时钟窗（需求 7 第 16、16a~16c 条；S1 修订）

```python
def resolve(self, site_id: str, month_of_year: int) -> dict:
    """按 (站点, 季节桶=月份1~12) 返回 {"daylight_start": time, "daylight_end": time, "source": "empirical"|"fixed"}。"""

def build_table(self, measurements: pd.DataFrame, lookback_months: int = 24) -> dict:
    """产出 {(site_id, month_of_year): window} 全表，随模型持久化。"""
```

**分组键是 `(site_id, 季节桶)`，季节桶 = 月份序号 1~12**（不是 `YYYY-MM`）。理由：日照的季节性由月份决定、与年份无关，用月份桶能让不同年份的同一季节共用窗口、样本更充足。

`empirical`（默认）推导算法——两条防线，**跨天聚合避免循环论证 + 只用近期数据避免衰减污染**：

1. 先按 `lookback_months`（`daylight_window_lookback_months`，默认 24）**只保留数据集最新时间戳向前 N 个月内的测量数据**——光伏板会随时间衰减、周边遮挡会变，早期形态未必代表现状。
2. 对每个 `(site_id, 季节桶)`，把该桶内所有设备-天的功率按 time-of-day 对齐。
3. 每个 time-of-day 取**跨设备-天的中位数**，得该站该季节的中位功率曲线。
4. 取该曲线超过自身峰值一个可配置比例处的首末时刻作为 `[daylight_start, daylight_end)`。

两处「防偏」：第 1 步用近期数据，避免几年前的衰减/遮挡形态主导（S1）；第 3 步用跨多天多设备中位数，单个故障设备或坏天气日撼动不了窗口（这是与被 K5 否决的按值判定的本质区别——后者用当日自身峰值，故障症状直接影响窗口）。

数据不足时的降级顺序（需求 7 第 16a、16b 条）：某季节桶在回溯窗内数据不足 → 先**放宽回溯窗到全历史该季节桶** → 仍不足 → 回退 `fixed`（`06:00–18:00`），并在快照元数据与重训报告记录回退的 `(site_id, 季节桶)` 清单。

实测约束依据：数据覆盖 8 站点、7 个月份，设备-天「末个有出力时刻」中位数从 2021-11 的 16.50 时到 2020-05 的 19.08 时，固定窗会在夏季砍掉傍晚发电；「首个 `value>0` 时刻」被夜间漏电流污染（部分月份分位数落到 0 点），故推导用中位曲线而非首个非零时刻。注意本数据集只跨 2020-05~2022-03，`lookback_months=24` 基本覆盖全量；回溯窗的实际收益要在数据更长的生产环境才显现，具体月数由任务清单的「日照窗阈值标定」确定。

**✅ 阈值标定已实跑（2026-07-30，conda cp_web，真实数据 `pv_cumulative_labeled_merged.parquet`）**：

- 按 `(site_id, 月份)` 分组共 14 组，跨 `peak_ratio ∈ {0.03, 0.05, 0.10}` 试跑，**采用 `peak_ratio=0.05`**（与现有 `irr_threshold` 默认值一致，便于对比）。该口径下窗口时长 min/median/max = 2.67h / 10.33h / 23.92h。
- **回退条件（<4h 或 >20h）在真实数据上确实会触发，且触发的组是合理的异常**：1 组（某站点 10 月，样本仅 14,965 行、时长 2.67h）判定为短窗回退；2 组（另两站点 10 月，时长分别 23.83h、23.92h）判定为长窗回退——这两组的中位曲线接近全天有出力，大概率是数据本身稀疏/异常（10 月是数据量最小的月份之一），不是真实日照。**4h/20h 这两个边界值经真实数据验证是合理的初值，能筛出确实异常的组，不误伤正常组**（其余 11 组时长落在 7.2h~16.7h 的合理区间）。
- **回溯窗验证**：数据集总跨度 22 个月（2020-05~2022-03），`lookback_months=24` 覆盖全部数据，本数据集上该参数暂不产生裁剪效果；其实际收益（避免早期衰减数据主导）需在跨度更长的生产数据上才能体现，24 作为默认初值保留。
- **数据量充分性**：14 个 `(site_id, 月份)` 组的行数 min=652（远超 1 天 288 点），无一组因数据量不足触发回退，说明当前数据规模下"数据不足回退"分支在这批数据上不会命中，该分支的测试需靠构造数据补充覆盖。

### 4. `SampleBuilder` — 样本构造纯函数（需求 7）

```python
@dataclass(frozen=True)
class SampleStrategy:
    split_mode: str            # by_day | by_day_night（by_label_run 已按 K8 移出本 spec）
    min_points: int = 12
    daylight_window_source: str = "empirical"
    daylight_window_lookback_months: int = 24   # S1：empirical 推导只用最近 N 个月数据
    daylight_windows: dict = field(default_factory=dict)  # {(site_id, 月份1~12): window}
    version: str = "sb-v1"

@dataclass(frozen=True)
class Sample:
    sample_id: str
    label_id: int
    period_role: str           # whole | daylight | night
    t_start: datetime
    t_end: datetime
    row_index: np.ndarray      # 引用的测量行索引
    label_source: str
    label_source_purity: float
    label_op_id: str

def build_samples(labeled_rows: pd.DataFrame, strategy: SampleStrategy) -> tuple[list[Sample], list[dict]]:
    """纯函数。labeled_rows 为同一设备三元组下按时间升序的测量行 + 逐点标签。
    返回 (样本列表, 丢弃原因列表)。对入参只读。"""
```

断开依据按 `split_mode` 二选一（需求 7 第 2 条，K8），实现为「构造布尔断点掩码 → `cumsum()` 分组」，与探针验证过的算法一致：

```python
lab_chg = labeled_rows["label_id"].ne(labeled_rows["label_id"].shift())
day_chg = labeled_rows["day"].ne(labeled_rows["day"].shift())
dn_chg  = labeled_rows["is_night"].ne(labeled_rows["is_night"].shift())

if   split_mode == "by_day":        start = lab_chg | day_chg          # 标签变 或 跨天
elif split_mode == "by_day_night":  start = lab_chg | day_chg | dn_chg # 再加白天夜间切换
sample_id_group = start.cumsum()
# 注：跨天时序切分 by_label_run（仅 start = lab_chg、不断天）已按 K8 移出本 spec，
#     交 pv-fault-timeseries-diagnosis spec 用序列模型承接。
```

`is_night` 由 `DaylightWindowResolver` 按该点所属 `(site_id, 季节桶=月份1~12)` 的时钟窗判定，**完全不看测量值**（需求 7 第 16 条）。注意实现上必须显式检测设备边界（`dev_chg`）；上游按设备三元组分组调用时该项恒为首行 True。

策略不变量（需求 7 第 4、5、6、7、9、12 条），全部由「按标签形态断开」这一机制天然保证：

| 不变量 | 保证方式 |
|---|---|
| 标签纯一致 | `lab_chg` 在标签变化处必断开 |
| 单标签 | 每样本取其点的唯一 `label_id`，不输出标签集合 |
| k 种形态至少 k 条样本 | 同上 |
| unknown 独立成形态且不产训练样本 | `label_id` NULL 参与 `lab_chg`，随后过滤掉 |
| 点不重复 | `cumsum()` 分组天然互斥 |
| 可为空 | 允许返回空列表 + 丢弃原因 |

后置过滤 `min_points`（默认 12）：丢弃原因需带该样本实际点数与生效阈值（需求 7 第 14 条）。实测三种模式在该阈值下均 0 样本被过滤（最小样本 34 点）。

已删除的切分方式与理由（需求 7 第 10 条）：`multiscale`（同批数据追加两次，违反点不重复）、`fixed_window`（收敛为 3 种）、`solar_period`/`peak`/`trans`（判定依据「功率 > 当天峰值 30%」与被 K5 否决的按值判定同源）。

### 5. `sample_id` 生成与解析（需求 8）

```python
def make_sample_id(site_id, device_id, branch_id, t_start, period_role, seq, namespace="smp") -> str:
    dev_hash8 = hashlib.sha256(f"{site_id}|{device_id}|{branch_id}".encode()).hexdigest()[:8]
    return f"{namespace}-{dev_hash8}-{t_start:%Y%m%dT%H%M%S}#{period_role}#{seq}"
```

示例 `smp-3f9a1c2b-20200508T060000#whole#0`。恒为字符串、恒含 `#`（透传前提）、可解析回 `(dev_hash8, t_start, period_role)`。推理侧用 `inf-` 前缀。`op_id` **不编进** `sample_id`，改由快照的 `label_op_id` 列承载溯源——因为一条样本的点可能来自多个操作（K4 场景下白天来自 `human_range`、其余来自伴生 `human_day`）。

`sample_id` 同时取代现有三套 `unit_key` 格式与四种混用标识形态，并移除 `backfill.py` 与 `api/iterative_labeling.py` 中重复的时间戳归一化实现（需求 8 第 4、5、6 条）。

### 6. `SnapshotBuilder` — 快照预物化（需求 9、10）

改造落点是 `cumulative_training.py::_create_snapshot(state)`。现状实现是「读 `labeled_imports` 各文件 + `BackfillService` 回贴 → `concat` → 5 列 `drop_duplicates`」；新实现改为：

```
1. 读 point_labels（active 逐点标签） ⨝ training_samples（测量）  按 (site,device,branch,time) 内连接
2. 按设备三元组分组，逐组调 SampleBuilder.build_samples(rows, strategy)
3. 为每条样本赋 sample_id，写入 time_window 列
4. 计算 group_key（day-block 连通块）
5. 写 period_role + 3 个 period_is_* + 5 个 night_* + label_source/purity/op_id
6. 写出前自检：time_window 列 100% 非空且 100% 含 '#'
7. 写 parquet + 快照元数据（含 label_snapshot_hash、日照窗回退清单、丢弃原因汇总）
```

**删除现状的 `drop_duplicates`**（需求 10 第 3 条）：不再需要，因为「同点唯一」由 `point_labels` 主键保证、「样本点不重复」由 `cumsum()` 分组保证。现状那次去重本就失效（基础侧 `time_window` 为 NaN、自由段侧为字符串，键永不相等，441 行去重后仍 441 行）。

**`group_key` 的 day-block 算法**（需求 10 第 6、7 条）：

```
对每个 (site_id, device_id, branch_id)：
  把每条样本映射为它覆盖的自然日集合
  对「日集合有交集」这一关系取连通分量（并查集）
  同一分量内全部样本共享 group_key = "{site}|{device}|{branch}|blk{n}"
  n 按分量内最早时间升序分配
不变量：任意两条共享至少一个自然日的样本必属同一 group_key
```

选它而非「按自然日取键」的理由：后者要求样本不跨天，与 K3（允许跨天建模）冲突；day-block 在允许跨天的同时保住了「同一天数据不会被切到训练集与测试集两侧」的防泄漏强度。注意 `by_day` 与 `by_day_night` 模式下样本本就不跨天，此时 day-block 退化为按自然日分组，与旧口径等价。

**`night_*` 列的写入规则**（需求 10 第 10 条）：只有 `period_role='night'` 的样本调 `night_anomaly.compute_night_anomaly_features()` 求值，其余样本 5 列**显式写 0.0** 而非留空——不依赖 `extract_statistical_features.py` 末尾 `result.fillna(0)` 的兜底。计算前须拦截量级坏值（实测夜间 `value` 绝对值最大 1.04e11，而同批 `i_cal` 最大仅 1.75），否则污染 `night_current_max`/`night_current_mean`（需求 7 第 16e 条）。

**`period_is_*` 与 `passthrough_fields` 随 `split_mode` 变化**（需求 10 第 9a、需求 11 第 8、8a 条）：

| `split_mode` | `period_role` | 透传列数 | 进特征矩阵的数值列 |
|---|---|---|---|
| `by_day_night` | `daylight` / `night` | 12 | 9（3 个 `period_is_*` + 5 个 `night_*` + `label_source_purity`） |
| `by_day` | 恒 `whole` | 4 | 1（`label_source_purity`） |

后者把 3 个 `period_is_*` 与 5 个 `night_*` 移出 `passthrough_fields`，因为此时它们是常量，喂进去是无区分度的列。

**快照隔离与可复现**（需求 21 第 7、10、12 条）：构建开始时先算 `label_snapshot_hash` 并固定读取版本，构建期间的标注写入不影响本次快照。同一 `(label_snapshot_hash, sample_strategy, 测量数据)` 三元组再次构建产出逐行等价快照。

`label_snapshot_hash` 口径（需求 21 第 8、9 条）：全部 `status='active'` 的 `label_ops` 按 `op_id` 升序，取 `(op_id, site_id, device_id, branch_id, t_start, t_end, label_id, source, status, label_space_version)` 十字段规范化序列化后的 SHA-256；排除 `updated_at` 等易变字段。

进度上报复用现有 `update_retrain_progress()`（需求 21 第 5 条）。

### 7. `InferenceSampleGenerator` — 预测侧样本（需求 12）

```python
def generate_inference_samples(measurements: pd.DataFrame, model_path: str) -> tuple[pd.DataFrame, dict]:
    """按模型持久化的 sample_strategy 切分待预测数据。返回 (带 sample_id 的行, 审计信息)。"""
```

- 从模型文件读 `sample_strategy`，**缺失即报错终止**，不回退默认策略（需求 12 第 7 条）。
- 推理样本只在内存，不写 `point_labels`、不写 `label_ops`、不产生落库 `op_id`（需求 12 第 8、9 条）。
- `sample_id` 用 `inf-` 前缀（需求 12 第 10 条）。
- 定时任务侧：`pv_fault_tasks._write_prediction_input()` 为每行打 `sample_id`（需求 12 第 2 条）。

**训练/预测口径一致**（需求 12 第 15、16 条）——K8 移出 `by_label_run` 后，两种保留模式训练与预测的样本边界都严格对齐：

| | 训练 | 预测 |
|---|---|---|
| 标签 | 有 | 无 |
| `by_day` / `by_day_night` | 按自然日（+时钟窗） | 同口径，逐样本对齐 |

两种模式都按自然日/时钟切分、不依赖标签,所以预测侧无需任何退化处理（这正是把跨天时序模式 `by_label_run` 移出本 spec 换来的好处——那个模式预测时无标签、边界无法对齐）。白天/夜间预测侧用模型持久化的 `daylight_windows` 表判定，不现场推导（需求 12 第 16a 条）；表中缺该 `(site_id, 季节桶)` 组合时用持久化的 `fixed` 兜底窗并记录（需求 12 第 16b 条）。按值判定下预测阶段阈值依赖当日峰值，天然无法与训练时一致——这是 K5 的一个附带收益。

**删除 split parity 机制**（需求 12 第 5 条）：`PVTrainingWorkspaceService.set_workflow_split_parity()` 与 `_read_workflow_split_parity()` 一并删除，同步调整 `api/iterative_labeling.py` 中引用它们的路由（含 `_execute_cumulative_retrain()` 的 `solar_mode` 入参与返回体的 `split_config`）与 2 个测试。策略随模型持久化后，「训练/预测模板切分是否对齐」这个问题在结构上不再存在。

### 8. 人工裁决落标主链路（需求 19）

```
Review_UI 提交裁决 (unit_key = sample_id)
        │
        ├─ skip                → 不写任何操作（保持现状语义）
        ├─ confirm/correct/new_label → PointLabelService.submit_op(source='human_day',
        │                              边界取该样本 [t_start, t_end))
        │      └─ correct 且该时段已有 active 操作 → 新增操作 + 旧操作置 revoked
        └─ 波形图框选           → submit_op(source='human_range') + K4 伴生操作
        │
        ▼ 写入成功 → CumulativeTrainingService.pending_change_count += 1（按操作计）
        ▼ 达到 retrain_label_threshold(默认20) → 触发重训请求（沿用现有机制）
```

`new_label` 场景下「分配标签」与「写操作」须在同一逻辑事务内，写操作失败则回滚标签分配，避免孤儿标签（需求 18 第 5、6、7 条）。现有 `LabelRegistryService.allocate_label()` 保持不变。

同一 `sample_id` 重复提交相同裁决不递增计数，沿用 `admit_verdict()` 的 `reason="duplicate_verdict"` 去重语义（需求 19 第 9 条）。

`state.json` 的 `verdict_entries` 迁移后不再作为标签来源，仅保留历史对账；`SnapshotBuilder` 若尝试从它读标签则终止并报错（需求 19 第 11、12 条）。

### 9. 待标注队列（需求 20）

定义为 `point_labels` 中 `label_id IS NULL` 的点、以及未被任何 active 操作覆盖的点，按设备三元组与时间连续性聚合成可读条目。

K4 对队列规模的影响（需求 20 第 2 条）：旧方案「框选后当天其余时段设为 unknown」会持续制造 unknown 点；K4 生效后这些点直接判正常，队列只剩**从未被任何标注操作覆盖过**的时段，规模显著变小。

条目携带时间范围、采样点数，以及该范围内曾存在但已被撤销的操作的 `label_id` 与 `reviewer`（需求 20 第 5 条）。空队列渲染空态而非空白（需求 20 第 9 条）。

### 10. 新旧路径并存与精度对比（需求 23，K7）

这次改动面大（标签存储、白天夜间口径、切分方式都变了），不能默认新路径一定更好。所以老的按天建模路径作为一等公民保留、可运行可回退，新旧同口径 A/B 对比，用数据决定谁上生产。

**两条路径**：

| | 老路径（保留） | 新路径（本次重构） |
|---|---|---|
| 标签来源 | `training_samples.label` 逐点列 | `point_labels`（物化自 `label_ops`） |
| 白天/夜间 | 按值判定（`solar_window._day_night_masks`） | 时钟窗（`DaylightWindowResolver`） |
| 样本粒度 | 天级 | `split_mode` 二选一（`by_day` / `by_day_night`） |
| 快照构建 | 现状 `_create_snapshot`（保留一份旧行为分支） | `SnapshotBuilder` |

**对比骨架复用 `backend-service/services/iterative_labeling/split_mode_compare.py`**（现有：同一快照上对比多种切分的离线评估），扩展成"同一批原始测量数据，分别按老/新两条路径完整跑一遍 → 同口径评估"。评估口径固定：同 `n_repeats`、`test_ratio`、随机种子（复用 `stratified_cv_eval` 的 `random_state`），保证可重复。

**对照报告**（需求 23 第 4 条）：每条路径的 `macro_f1_mean`、`accuracy_mean`、各 label recall、样本量，以及新旧差值。

**生产登记加两个指针**（需求 23 第 5、6 条）：`production_path`（当前主线：`legacy_day` 或 `point_label`）与 `fallback_path`（可回退备选）。落点是 `state.json`（复用现有 `production_model_ref` 机制，扩展成按 path 各记一个）。主线出问题（精度回退或运行故障）时切到备选路径最近可用模型，回退动作记入审计。

**必须显式声明的对比前提**（需求 23 第 7、8 条）：新旧口径不同，对比只能建立在"同一批原始数据分别跑两条路径"上，**不能拿历史老口径训练的模型指标直接比**。默认 `by_day_night`。第三条候选路径——`pv-fault-timeseries-diagnosis` spec 的时序模型（序列模型 + 滑动窗口）——待其可用后按需求 23 第 8 条接入同一对比框架，届时三条路径同口径比较。

## 算子改动（严格受限于需求 9）

### 零代码改动清单（5 个文件）

`time_window_split.py` · `tsfresh_extract.py` · `ts_comparison_features.py` · `handle_missing.py` · `detect_outliers.py`

`time_window_split.py` 为何能零改动：它的 `execute()` 里 `preassigned, df_input = _split_preassigned_windows(data)` 按 `_is_preserved_time_window()`（判据是文本含 `#`）摘走所有预置窗口行；快照使每行 `time_window` 都是含 `#` 的 `sample_id`，`df_input` 遂为空，而 `if df_input.empty` 分支位于 `elif solar_mode` 之前，因此该节点退化为纯透传。此行为已由前置探针实跑验证（全 `#` 与半 `#` 半 NaN 两个场景均通过）。模板移除 4 个失效参数后该算子仍不抛错，因为它用 `params.get("solar_mode")`，取到 `None` 即走透传分支。

`handle_missing` / `detect_outliers` 的 `id_fields=[site_id, device_id, branch_id, time_window]` 分组与按 `sample_id` 分组等价：`sample_id` 内含 `device_hash8`，唯一对应设备三元组（需求 9 第 10 条）。

`solar_window.py` 保留且零改动，以兼容 fault-diag 的 `set_time_window` 旧调用路径。**但须显式记录口径分叉**（需求 9 第 8a 条）：本次重构的训练/预测链路用时钟窗判定，旧路径仍用按值判定，两者白天/夜间归属实测在 18.0% 的点上不一致，产出的样本与特征不可混用比较。

### 限定范围改动清单（2 个文件、3 处改动）

两份清单互斥，`extract_statistical_features.py` 不同时出现在两处（需求 9 第 16 条）。

#### 改动 1：`extract_statistical_features.py` 新增 `passthrough_fields`

落点是 `_execute_groupby_aggregate(params, options, df, operator_id)`。现状该函数只输出 `id_fields` + `value_fields` 的派生特征列，任何样本级常量列都在聚合环节丢失。新增：

```python
passthrough_fields = _parse_list(
    params.get("passthrough_fields") or options.get("passthrough_fields"), []
)
actual_passthrough = [f for f in passthrough_fields if f in df.columns]
# 在 merge_list 合并完成、fillna(0) 之前接入
if actual_passthrough:
    pass_fe = groups[actual_passthrough].first().reset_index()
    new_cols = actual_id_fields + [c for c in pass_fe.columns if c not in result.columns]
    result = result.merge(pass_fe[new_cols], on=actual_id_fields, how="left")
```

- 每个分组取该字段第一个值（`groups[...].first()`）原样输出为常量列（需求 11 第 4 条）。
- 未配置时输出列集合不变（需求 11 第 5 条）。
- **注意 `fillna(0)` 的位置**：现状末尾 `result = result.fillna(0)` 会把透传的字符串列 NaN 也填 0。透传列接入须在 `fillna(0)` 之前完成，且实现时需确认字符串列被填 0 不影响下游——`group_key`/`label_source`/`label_op_id` 三列在正常路径下不会为 NaN（快照阶段必填），但设计上应显式只对数值列 `fillna(0)`，避免字符串列被污染。

#### 改动 2：`extract_statistical_features.py` 分位数判定口径

现状：`avg_count = groups[value_fields].count().mean().mean()`，仅当 `avg_count >= 48` 才计算分位数特征——这使特征列集合随输入数据构成漂移，模型文件里固定的 `feature_list` 会失配。

改为按每个样本自身采样点数与 `min_points` 判定（需求 13 第 1、2、3 条），使输出列集合由配置唯一决定、不随数据构成变化。两种保留模式的单样本点数不同（`by_day` 144~288、`by_day_night` 34~144），该口径保证列集合仍稳定。

#### 改动 3：`stratified_cv_eval.py` 新增 `group_col` 并持久化策略

**`group_col` 的读取时机是关键**（需求 11 第 12 条）：`_build_Xy()` 会 drop 所有非数值列，`group_key` 是字符串列，必须在 drop 之前读出。

```python
merged = _merge_feature_frames(inputs, id_fields, target_col)
group_col = str(params.get("group_col") or "").strip() or None
groups_arr = None
if group_col and group_col in merged.columns:
    y_raw = pd.to_numeric(merged[target_col], errors="coerce")
    groups_arr = merged.loc[y_raw.notna(), group_col].to_numpy()   # 与 _build_Xy 的 mask 对齐
X, y = _build_Xy(merged, id_fields, target_col)
```

`groups_arr` 的行过滤必须与 `_build_Xy()` 内 `mask = y.notna()` 完全一致，否则索引错位。随后把 `_stratified_split()` 换成分组感知版本：整组分配，保证训练集与测试集零共享 `group_key`（需求 11 第 3 条）；`group_col` 未配置时保持现有逐类行级分层行为不变（需求 11 第 2 条）。

模型持久化扩展（需求 12 第 3 条）：现状 `execute()` 只 `pickle.dump({"model": final_clf, "feature_list": final_feat_list})`。改为追加 `sample_strategy`（含 `split_mode`、`daylight_window_source`、`daylight_windows`、`min_points`、`version`）与 `label_snapshot_hash`。这两项由编排层通过算子参数传入。

旧快照防降级（需求 16 第 4、5 条）：`time_window` 列出现不含 `#` 的取值时输出显式告警或错误，禁止静默按旧 resample 逻辑降级；行为可配置，默认取值使问题对使用者可见。

### 模板改动（需求 9 第 9 条、需求 12 第 4、13 条）

`workflow-pv-fault-diag-quickval-cv-v1.json`：

| 节点 | 改动 |
|---|---|
| `qv-extract_statistical_features-n7` | 增 `passthrough_fields`（12 列或 4 列，随 `split_mode`） |
| `qv-stratified_cv_eval-*` | 增 `group_col: "group_key"` |
| `qv-time_window_split-n4` | **删** `solar_mode`、`power_col`、`irr_threshold`、`attach_night_features`；**保留** `window`、`id_fields`、`time_field` |

保留那 3 个参数的原因：`window` 为空会抛 `ParameterError`、`time_field` 不在列中会抛 `InputError`，这两项校验在全透传模式下仍先于透传分支执行；`id_fields` 保留是为与下游 `handle_missing`/`detect_outliers` 的 `id_fields` 口径一致。

`passthrough_fields` 只挂统计特征节点，不挂另两路——因为 `_merge_feature_frames()` 以含 `target_col` 的那一路为合并基表，实测只有统计特征节点的 `id_fields` 含 `label`，故统计特征表即基表，一路透传即可到达 `stratified_cv_eval`；另两路按零改动清单不识别该参数（需求 11 第 13、14 条）。

**列名冲突检查**（需求 11 第 15、16、17 条）：`_merge_feature_frames()` 用 `new_cols = [c for c in f.columns if c not in merged.columns]` 只取新列，同名列被**静默跳过**、无任何运行期信号。因此需先列出三路输出列名全集，与 12 个透传列名做冲突检查。

**✅ 已实跑验证（2026-07-30，conda cp_web，用 quickval 模板真实参数）——无冲突，12 个透传列名安全，无需加前缀**：

- `extract_statistical_features`（groupby_aggregate，quantiles=[0.25,0.75]，compute_diff=true）：63 列，全部是 `value_*` / `i_cal_*` / `{col}_diff_*` 派生统计特征。
- `tsfresh_extract`：20 列，全部 `value_*` / `i_cal_*` 前缀（如 `value_abs_energy`、`i_cal_cid`）。
- `ts_comparison_features`（相关/距离/回归全开）：10 列，全部 `diff_value_i_cal_*` 或 `value_i_cal_*` 前缀（如 `value_i_cal_spearman`、`value_i_cal_dtw`）。
- 12 个透传列（`group_key` / `label_source` / `label_source_purity` / `label_op_id` / 3×`period_is_*` / 5×`night_*`）与上述三路输出**零交集**；三路特征列之间也无非 id 同名列。

原因很直观：三路特征列名都以被测量字段名（`value` / `i_cal`）打头，而透传列是标签治理与时段角色元数据，命名空间天然不重叠。因此需求 11 第 17 条的 `lbl_` 前缀方案**不需要启用**，透传清单与快照列清单保持原样。

## 迁移设计（需求 14）

### `MigrationTool` 流程

落点 `backend-service/scripts/migrate_point_labels.py`，可重复执行、幂等。产出两部分：`label_ops` 操作记录 + 经 `LabelMaterializer` 物化的 `point_labels`（不手工拼装逐点标签，需求 14 第 1 条）。

```
1. 前置探测复核（复用 Preflight_Probe 口径）→ 若事实基线变化则中止
2. day_label 源：pv_cumulative_labeled_merged.parquet
     按 (site,device,branch,自然日) 分组 → 每组 1 条 source=day_label 操作
     created_at 由该导入的 labeled_imports.sequence 合成
     实测应产出 4,457 条操作、覆盖 1,056,806 点
3. human_range 源：time_slices/*.meta.json（2 条）
     time_start/time_end 逐字段直读 → source=human_range 操作
     闭区间转半开：t_end = 源 time_end + 300 秒
     每条额外生成 K4 伴生 human_day(label_id=0) 操作，parent_op_id 指向它
4. human_day 源：state.json.verdict_entries（18 条）
     unit_key 内时间为窗口起点，按窗口长度推 t_end（不把起点当 t_end）
5. cluster 源：clust-ee66f5a50c28 的 selected_member_keys → source=cluster 操作
6. 全部操作写同一 migration_batch_id
7. LabelMaterializer 物化受影响的全部设备维度
8. 产对账报告
```

### 对账口径（需求 14 第 12~16、21 条）

- 时间切片：段覆盖采样点数须 == `meta.json` 的 `row_count`（`slice-b0c42870f030` 应对账 153 点），不等则拒绝该条、记失败明细、继续（需求 14 第 13 条）。
- `verdict_entries` 同口径对账（需求 14 第 14 条）。
- 报告含：迁移前带 `label` 行数、迁移后操作数（按 `source`）、逐点标签覆盖点数（按 `source`）、unknown 点数、**因 K4 被改写为正常的点数**（预期 `slice-b0c42870f030` 对应 2020-05-08 的 135 点）、失败明细。
- 总量对账：逐点标签总数与源 parquet 带 label 行数的差异须逐处可解释（预期差异只来自 K4 改写与人工操作覆盖）。

### 幂等与冗余源

- 幂等（需求 14 第 15 条）：`op_id` 由 `(source, site, device, branch, t_start, t_end, label_id)` 内容哈希生成，重复执行同源第二次不产生新操作，物化结果等价。
- `dataset_combined.parquet` 判定为完全冗余源（303,321 行全部是 `pv_cumulative_labeled_merged.parquet` 的四元组子集、0 冲突），**不参与迁移**（需求 14 第 3 条）。兜底：迁移前重新探测，若不再是子集关系则重新评估差异部分（需求 14 第 4 条）。
- 时间切片 CSV 默认不删除，只在报告标注「可安全归档」（需求 14 第 17 条）。

### reconcile（需求 18 第 9~11 条）

实测两 parquet 的 `label_id` 全在当前 `ls-v2` 内，本次**不触发** reconcile。设计保留通路：遇到标签空间外的 `label_id` 时调 `LabelRegistryService.reconcile_labels()` 补「待命名-故障码N」、保留原码、生成新 `label_space_version`；无法补齐则记失败明细、保留待人工处理，不静默丢弃。

## 错误处理与降级（Error Handling）

| 场景 | 处理 | 需求 |
|---|---|---|
| 写操作违反不变量 | ValueError / HTTP 422（含冲突明细） | 5, 18 |
| `source='inference'` 或显式 `priority` 写入 | HTTP 422 | 3, 12 |
| 快照 `time_window` 存在非 `#` 值 | 拒绝写出，返回不满足行数与示例 | 9 第 11、12 条 |
| `stratified_cv_eval` 读到不含 `#` 的 `time_window` | 显式告警/错误，禁止静默降级；可配置，默认可见 | 16 第 4、5 条 |
| 模型文件缺 `sample_strategy` | 预测报错终止，不回退默认 | 12 第 7 条 |
| 样本被 `min_points` 过滤 / 输出为空 | 结构化丢弃原因（含实际点数+阈值），汇总进重训报告 | 7 第 13、14 条 |
| 日照窗经验推导失败/不合理 | 回退 `fixed`，记录回退 `(site,月)` 清单 | 7 第 16b 条 |
| 夜间量级坏值（如 1.04e11） | 计算 `night_*` 前拦截 | 7 第 16e 条 |
| 迁移单条对账不符 | 拒绝该条、记失败明细、继续 | 14 第 13、19 条 |
| 并发同设备写入 | 按设备维度串行化「写操作+重物化」 | 21 第 6、7 条 |
| `SnapshotBuilder` 尝试从 `verdict_entries` 读标签 | 终止并报错 | 19 第 12 条 |

现状代码里散布的 `except Exception: pass`（知识/特征/候选写入链路）不在本次范围，但迁移与物化的失败路径一律记入报告、不静默吞。

## 并发与事务（需求 21、22）

- 写路径「校验 → 写 `label_ops` → 重物化 `point_labels`」在同一 `DBAdapter.get_sync_session()` 事务内完成，失败整体回滚。
- 同一 `(site_id, device_id, branch_id)` 的并发写入按设备维度串行化。首选实现：对 `label_ops` 该设备维度取行级锁（`SELECT ... FOR UPDATE`）；数据库不支持时退化为应用层按设备键的进程内锁（`threading.RLock` 字典，与 `cumulative_training._STATE_LOCKS` 同风格）。设计文档标注该退化在多进程部署下不足，需 DB 行锁兜底。
- `new_label` 的「分配标签 + 写操作」同事务，写失败回滚标签分配（需求 18 第 6、7 条）。
- 查询命中索引不全表扫描（需求 21 第 3 条）。
- 快照 30 分钟内完成 1,056,806 行（需求 21 第 4 条），测量数据只读 `pv_cumulative_labeled_merged.parquet`（`dataset_combined` 是子集）。

## 测试策略（Testing Strategy）

按 conda 环境 `cp_web`、`pytest` 组织。测试文件放 `backend-service/tests/`。

### 单元测试

| 组件 | 用例要点 |
|---|---|
| `LabelMaterializer` | 优先级裁决（100>80>10）；同 priority 按 created_at/op_id；顺序无关性（打乱输入操作顺序结果一致）；未覆盖点为 NULL；只重算受影响范围 |
| `PointLabelService` | 7 类不变量校验各自触发；K4 写两条操作 + 伴生 parent_op_id；跨自然日框选生成多条伴生；`untouched` 只写一条；跨会话重叠 422；撤销联动伴生操作 |
| `DaylightWindowResolver` | 经验推导用中位曲线；单故障设备不移动窗口；回退条件（<4h/>20h）；持久化表可复现 |
| `SampleBuilder`（属性测试，需求 7 第 15 条） | 标签纯一致、单标签、k 形态≥k 样本、unknown 不产样本、点不重复、可为空；输入含单点/跨天/00:00 处标签变化/全 unknown/点数<min_points/一天≥3 种形态 |
| `sample_id` | 恒字符串、恒含 `#`、可解析回三元组；`smp-`/`inf-` 前缀区分 |

### 算子改动测试（守住零改动约束）

| 用例 | 断言 |
|---|---|
| `extract_statistical_features` 未配 `passthrough_fields` | 输出列集合与改动前一致（除分位数口径） |
| 配 `passthrough_fields` | 常量列按分组首值透传，不进数值特征聚合 |
| 分位数口径 | 新增少于 48 点的短样本不改变其他样本列集合 |
| `stratified_cv_eval` 配 `group_col` | 训练/测试零共享 `group_key` |
| 未配 `group_col` | 与改动前逐类行级分层等价 |
| 模型 pickle | 含 `sample_strategy` 与 `label_snapshot_hash` |
| `time_window_split` 全 `#` 输入 | 逐行透传（回归前置探针场景 A/B） |

### 集成测试（真实数据，端到端）

1. 迁移 → 物化 → 快照 → 训练一条龙，用武当湖 04#箱变_汇流箱01 / 2020-05-08 断言：该设备该天 ≤288 行、任一采样时刻只出现一次（需求 10 第 4、5 条）——直接验证「重复计数」被消除（现状是 441 行 3 样本）。
2. 两种 `split_mode` 分别产出 `by_day` 4,457 / `by_day_night` 13,371 量级样本（现状与问题第 30 项基线）。
3. K4 端到端：框选后当天其余点物化为 label=0，不再是 unknown。
4. 撤销端到端：撤销 `human_range` 后该时段回到框选前的物化状态，伴生 `human_day` 同步失效。
5. 白天/夜间：`by_day_night` 下夜间样本 `i_cal` 近零、`night_*` 特征非零；对照按时钟口径的 label 区分度（现状与问题第 26 项）。

### 迁移对账测试

幂等（跑两次结果等价）；对账数字与 Preflight 基线一致（4,457 操作 / 1,056,806 点 / K4 改写 135 点）；单条对账失败被正确记入失败明细而不中断整体。

### 回滚测试（需求 17）

按 `migration_batch_id` 回滚只置该批操作为 revoked + 重物化，保留 `migration_batch_id` 为 NULL 的人工操作；未指定 batch_id 的回滚请求被拒绝（禁止整表清空）。

## 历史文档标注（需求 22）

落地完成后在 `docs/specs/pv-fault-iterative-labeling-loop/` 的 `design.md`、`requirements.md`、`design-feature-enhancement.md`、`requirements-feature-enhancement.md` 顶部标注「已被 `.kiro/specs/pv-fault-label-segment-redesign/` 取代」，指明与 `solar_mode` 切分模型、`time_window` 字符串语义、逐点 `label` 同表相关的章节作废；保留文件不删除；核对两个 `tasks*.md` 标注因本次重构作废的任务项。

## 需求覆盖对照表（Requirements Traceability）

| 需求 | 设计落点 |
|---|---|
| 1 标签与样本构造分离 | 架构分层；`SampleBuilder` 纯函数只读 |
| 2 两表结构与职责 | 数据模型（`point_labels` / `label_ops`） |
| 3 来源分级与分口径评估 | source→priority 映射；`label_source`/`label_source_purity` 透传列 |
| 4 标签物化规则 | `LabelMaterializer`（取最大 priority，无区间运算） |
| 5 操作不变量与 K4 | `PointLabelService.submit_op` + 伴生操作 + `op_scope` |
| 6 操作生命周期与审计 | `label_ops.status` 迁移 + 撤销联动 + 不物理删除 |
| 7 样本构造策略 | `SampleBuilder` + `split_mode` 二选一（K8） + 时钟窗 |
| 8 统一 sample_id | `make_sample_id` + `label_op_id` 溯源列 |
| 9 零新增算子 | 5 文件零改动 + 2 文件 3 处改动 + 模板改动 |
| 10 快照列结构 | `SnapshotBuilder` + day-block group_key + night 列规则 |
| 11 分组切分与透传 | `group_col` 改动 + `passthrough_fields` 改动 + 列名冲突检查待办 |
| 12 训练/预测共用策略 | `InferenceSampleGenerator` + 策略持久化 + 不对称性 + 删 split parity |
| 13 特征 schema 稳定 | 分位数口径改动 |
| 14 迁移对账 | `MigrationTool` + 对账报告 |
| 15 前置验证门禁 | 复用 Preflight_Probe（已实跑，报告在 docs/specs/…preflight-report.md） |
| 16 已确认缺陷修复 | 撤销联动、跨会话重叠、旧快照防降级 |
| 17 兼容/安全/回滚 | 按 batch_id 回滚 + 相对路径 + 不删历史产物 |
| 18 标签注册表一致性 | 写入前校验 + 同事务分配 + reconcile 通路 |
| 19 人工裁决落标主链路 | 落标流程图 + 按操作计数 |
| 20 待标注队列 | NULL/未覆盖点聚合 + K4 缩小规模 |
| 21 规模/并发/可复现 | 索引 + 设备维度串行化 + `label_snapshot_hash` |
| 22 历史文档标注 | 历史文档标注章节 |
| 23 新旧路径并存与对比 | 组件 10（复用 `split_mode_compare.py` + 生产双指针 + 回退） |

## 本设计阶段的显式待办（进入实现前须完成）

1. ~~三路特征算子输出列名全集冲突检查~~ **已完成**（见上方列名冲突检查段，2026-07-30 实跑验证：无冲突）。
2. ~~`daylight_window` 经验推导阈值标定~~ **已完成**（见组件 3 段内标定结果：`peak_ratio=0.05`、4h/20h 回退边界在真实数据上验证合理、`lookback_months=24` 在本数据集上暂无裁剪效果）。
3. **并发串行化的最终实现**：确认目标 DB 是否支持 `SELECT ... FOR UPDATE`；不支持则需评估应用层锁在多进程部署下的充分性。
4. **`label_ops` 与 `point_labels` 建表方式**：走 SQLAlchemy `Base.metadata.create_all` 还是显式迁移脚本，取决于现有部署惯例（现有表如何建的需确认）。

## 未在本设计中解决 / 明确排除

- 多标签分类：明确排除（K2），保持单标签。
- 天文日出日落：无经纬度数据，排除，用经验/固定时钟窗。
- `by_day_night` 夜间样本的实际建模价值：只有单变量区分度证据（各 label 夜间非零电流占比 7.45%~100%），未经训练对比验证；这 8,914 条夜间样本的价值高度依赖 `night_*` 特征质量。
- `dataset_combined.parquet` 迁移：排除（完全冗余源）。
<!-- @AI_GENERATED: end -->
