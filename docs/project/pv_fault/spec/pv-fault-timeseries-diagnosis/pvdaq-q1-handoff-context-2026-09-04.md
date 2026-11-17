<!-- @AI_GENERATED -->
# PVDAQ Q1 天路径检测验证 · 会话交接上下文（2026-09-04）

## 0. 一句话目标

在 PVDAQ 公开多设备数据上落地天路径 Q1（检测通用性）验证：RF 与 TSC 分别用 (a) predict-only 现有模型 + (b) 方法重拟合两条路，对齐物理功率 PR 真值，首轮不构造 `i_cal`。

## 1. 总体进度

| # | 任务 | 状态 | 核心产出 |
|---|---|---|---|
| 1 | 前置核实 | ✅ | RF 50 特征 smoke、TSC 网格推理 smoke、`i_cal` 缺失时两模型显式拒绝 |
| 2 | 选 Q1 系统 cohort | ✅ | 160 系统全量扫描→11 台 1min 主档 + system34 15min 鲁棒性 |
| 3 | 下载 cohort 多月数据 | ✅ | 12 系统×3 月 = 1,083 daily parquet，209 MB，SHA-256 校验通过 |
| 4 | PVDAQ→pv schema 转换器 | 🔄 **NEXT** | 长表透视→宽表、5min 重采样、sentinel 清洗、实体键注入、RTC DC power 重建 |
| 5 | Q1 物理真值 | ⬚ | 按设备-日算 PR、覆盖门≥90%、相对基线判正常/异常 |
| 6 | Path(b) 方法重拟合 | ⬚ | RF 二分类 + TSC 二分类、device 隔离 CV |
| 7 | Path(a) predict-only | ⬚ | 现有模型跑 PVDAQ、记录 `i_cal` 合同不兼容 |
| 8 | 汇总报告 + 自审 | ⬚ | 《RF vs TSC · Q1 检测验证》 |

## 2. 核心决策（已锁定，不可推翻）

| 决策 | 结论 | 原因 |
|---|---|---|
| Q1 定义 | 验"能跑通 + 能检测异常"，不需要故障类型金标 | 物理 PR 可廉价推出日级二分类 |
| (a) 与 (b) 都做 | Path(b) 为主，Path(a) 诚实报告合同不兼容 | 域差和输入合同会混淆结论 |
| 首轮不构造 `i_cal` | 功率 PR 为真值，模型重拟合不喂 `i_cal` | 半经验 `i_cal` 会污染主结论 |
| 1min 系统统一到 5min | 下采样，`window_length=288`（= 一天 288 个 5min 点） | 与平台天路径口径一致 |
| system 34 保持原生 15min | `window_length=96`，单列鲁棒性，不进入 1min 主 CV | 禁止伪上采样 |
| sentinel 清洗 | `raw ≤ -90000` 视为 NaN | PVDAQ 哨兵值约定 |
| 覆盖门 | 日级五核心通道每个 ≥90% 才计算 PR | 与首轮分析一致 |
| Path(a) 命名 | "当前调度模型直接域外预测"，非 Champion | 实际无 Champion |

## 3. cohort 选定的 12 个系统

### 3.1 11 台 1min 主档（参与 device-isolated CV）

| system_id | 名称 | 额定功率 kW | cohort_tier | DC power 来源 | 关键风险 |
|---:|---|---:|---|---|---|
| 4 | NREL x-Si -1 | 1.0 | main_direct_1min | direct_metric | 额定小；含 2015-06-29 掉电锚点 |
| 10 | NREL CIS -1 | 1.12 | quality_stress_1min | direct_metric | POA 长期 -99999 → 坏日必须被 90% 门排除 |
| 33 | Silicor Materials | 2.4 | main_direct_1min | direct_metric | 额定小 |
| 36 | NREL low-X x-Si -1 | 2.21 | main_direct_1min | direct_metric | 多 POA/温度 metric，转换器须冻结选择 |
| 51 | NREL x-Si 7 | 6.0 | main_cadence_transition_1min | direct_metric | 历史 15min→1min 切换，只准入逐日确认 60s 的 epoch |
| 1284 | NREL CIGS-11 | 1.2 | main_direct_1min | direct_metric | 可用止于 2015-03 |
| 1289 | NREL CIGS-12 | 1.82 | main_direct_1min | direct_metric | 多 POA/温度 metric |
| 1403 | RTC-FSEC-Baseline | 6.0 | main_derived_dc_power_1min | direct_else_V×I | DC power 缺行日用 V×I 重建 |
| 1422 | RTC-VT-Baseline | 6.0 | main_derived_dc_power_1min | V×I_derived | 含 DC 正常而 AC 掉电候选 |
| 1423 | RTC-NV-Baseline | 6.0 | main_derived_dc_power_1min | V×I_derived | 覆盖 2015–2023 |
| 1429 | RTC-SNL-Baseline | 6.0 | main_derived_dc_power_1min | V×I_derived | 可用止于 2017-10 |

### 3.2 单列鲁棒性

| system_id | 名称 | 额定功率 kW | 原生采样 | 说明 |
|---:|---|---:|---|---|
| 34 | Andre Agassi Academy A | 146.64 | 15min | 96 点/日，不混入 5min 主模型 |

### 3.3 每系统已下载的 3 个月份

| system | 月份 1 | 月份 2 | 月份 3 |
|---:|---|---|---|
| 4 | 2012-02 | 2015-06★ | 2019-05 |
| 10 | 2010-10 | 2014-11 | 2015-06★ |
| 33 | 2013-12 | 2016-12 | 2020-02 |
| 36 | 2013-12 | 2015-09 | 2017-07 |
| 51 | 2017-01 | 2017-06 | 2017-09 |
| 1284 | 2013-03 | 2013-11 | 2014-07 |
| 1289 | 2014-07 | 2016-05 | 2018-03 |
| 1403 | 2016-02 | 2017-04 | 2019-03 |
| 1422 | 2015-08 | 2016-06 | 2017-03 |
| 1423 | 2017-06 | 2019-08 | 2021-08 |
| 1429 | 2016-08 | 2017-01 | 2017-06 |
| 34 | 2013-02 | 2015-06★ | 2018-02 |

★ = 首轮分析的固定月份

## 4. 模型与输入合同（Task #1 结论）

### 4.1 pv_day RF

- **resolver**：`resolve_slot_scheduler_model("pv_day")` → `source="rolling_detect_model"`，candidate `mc-51c273d96a65`
- **工件**：`data/models/pv_fault_rfc_20260825T093215Z_2d79bc.pkl`
- **特征**：50 维（25 `value_*` + 25 `i_cal_*`）
- **训练类**：`[0,1,2,3,4,6,7,8,9,10,11,12,16]`（13 类）
- **特征来源函数**：`services/slot_datasets/real_model_detect.py::_extract_rfc_features`
- **缺 `i_cal` 行为**：`tsfresh_extract`/`ts_comparison_features` 抛 InputError；`feature_select` 跳过缺列后 sklearn predict 因特征数不匹配报错
- **Path(a) 结论**：round1 不构造 `i_cal` 时，RF predict-only **不可运行**

### 4.2 pv_tsc TSC (MultiRocket)

- **resolver**：`resolve_slot_scheduler_model("pv_tsc")` → `source="challenger"`，candidate `mc-63aa6730b608`
- **工件目录**：`data/models/tsc/tsc-multirocket-grid-20260904034613-1852f480/`
- **通道**：`[value, i_cal, is_measured]`（3 通道×288 时间点）
- **训练类**：`[0,1,2,3,4,6,7,8,11,12]`（10 类）
- **推理入口**：`TSCPredictor → _predict_grid_target_day → TSCModelWrapper.predict`
- **输入 shape**：`[n, 288, 3]` → wrapper 转成 aeon 的 `[n, 3, 288]`
- **缺 `i_cal` 行为**：`_predict_grid_target_day` 返回 `error="待预测数据缺少列: ['i_cal']"`
- **Path(a) 结论**：round1 不构造 `i_cal` 时，TSC predict-only **不可运行**

## 5. Task #4 设计要点（NEXT：PVDAQ→pv schema 转换器）

### 5.1 原始数据格式

PVDAQ daily parquet 是**长表**：`measured_on | utc_measured_on | metric_id | value`。老系统（4/10/33/34/36/51）`utc_measured_on` 全空，只能用 `measured_on`（站点本地时）。

### 5.2 转换步骤（设计，尚未实现）

1. **读取 cohort 决策表** `q1_cohort_selected.csv` → 获取每系统的 `core_role_metric_ids`（JSON 映射五核心角色→metric_id 列表）、`dc_power_provenance`、`rated_power_kw`
2. **读取 metrics 元数据** → 获取每个 metric_id 的 `calc_scale`/`calc_offset`/`units`/`sensor_name`
3. **逐日长表透视**：
   - 按 metric_id 过滤五核心角色
   - `scaled_value = raw_value × calc_scale + calc_offset`
   - 按 `measured_on` 透视成宽表：`time | ac_power | dc_power | dc_current | poa_irradiance | module_temp`
   - 多 metric 同角色（如多个温度传感器）→ 取均值
4. **Sentinel 清洗**：`raw ≤ -90000` → NaN（在 scale 之前做）
5. **RTC DC power 重建**：当 `dc_power_provenance` 不是 `direct_metric` 时，从 `inv*_dc_voltage × sum(inv*_dc_current*)` 派生 DC power（公式 `sum_i(V_i × sum_j(I_ij))`），仅在直接 metric 缺行时使用
6. **Cadence 门**：逐日检查 `measured_on` 的中位间隔；system 51 需排除非 60s 的日期；system 34 保持 900s
7. **5min 重采样**：1min 系统做 mean 下采样到 5min → 288 点/日；15min 系统保持 96 点/日
8. **实体键注入**：`site_id = <cohort.site_id>`、`device_id = pvdaq-system-<system_id>`、`branch_id = main`（PVDAQ 单逆变器/单阵列，无真实 branch 维度）
9. **输出**：逐系统-月 parquet，列 = `time | site_id | device_id | branch_id | value(=dc_current) | dc_power | ac_power | poa_irradiance | module_temp`。**round1 不含 `i_cal` 列**
10. **路径**：`backend-service/data/benchmark_raw/pvdaq/converted/<system_id>/<year>-<month>.parquet`

### 5.3 RTC 系统 DC voltage metric_id（已核实但未写入决策表）

RTC 四系统的电压+电流 metric_id 结构统一：每系统 2 个逆变器，每逆变器 1 个 `inv*_dc_voltage` + 2 个 `inv*_dc_current*`。

| system | inv1_voltage | inv1_current1 | inv1_current2 | inv2_voltage | inv2_current1 | inv2_current2 |
|---:|---:|---:|---:|---:|---:|---:|
| 1403 | 4202 | 4203 | 4204 | 4208 | 4209 | 4210 |
| 1422 | 4825 | 4826 | 4827 | 4831 | 4832 | 4833 |
| 1423 | 4849 | 4850 | 4851 | 4855 | 4856 | 4857 |
| 1429 | 4912 | 4913 | 4914 | 4918 | 4919 | 4920 |

## 6. Task #5 设计要点（Q1 物理真值）

- `PR = AC日发电量(kWh) / (额定功率(kW) × POA日辐照量(kWh/m²))`
- 只在五核心通道每个覆盖 ≥90% 的日期计算
- 每设备取合格日 PR 中位数作为 baseline
- `relative_pr = PR / baseline_pr`
- `low_performance_candidate = relative_pr < 0.7` → 异常日
- Q1 二分类金标：`normal(relative_pr ≥ 0.7)` / `abnormal(relative_pr < 0.7)`
- **独立于模型输出**，不允许 `truth = pred` 自造 gold

## 7. Task #6/#7 设计要点

### Path(b) 方法重拟合

- **RF 二分类**：从 PVDAQ 转换后数据提取日统计特征（不含 `i_cal_*`，只用 `value_*` 25 维 + 可选 `dc_power_*`/`ac_power_*` 扩展）→ 对齐 Q1 金标 → device-isolated GroupShuffleSplit CV
- **TSC 二分类**：单通道 `value`（dc_current）288 点日波形 → 重新训练 MultiRocket → device-isolated CV
- **指标**：异常 recall/precision、balanced accuracy、PR-AUC、混淆矩阵

### Path(a) predict-only

- 两模型均因缺 `i_cal` 无法直接运行
- 诚实报告**输入合同不兼容**，不以 0/伪值填充
- 可选：单独列一个 compatibility sensitivity 分析（如只喂 `value` 通道、`i_cal` 用 `value` 复制），但必须**明确标注为非诚实直接预测**，不混入主结果

## 8. 文件与数据布局

```
backend-service/data/benchmark_raw/pvdaq/
├─ metrics__system_*__part000.parquet      # 160 个系统 metrics 元数据
├─ systems.parquet / sites.parquet / ...   # 全局设备元数据
├─ system_id=<sid>/year=*/month=*/         # 原始 daily 长表 (×1083)
├─ cohort_scan_samples/                    # Task#2 抽样探测样本 (×75)
├─ analysis/
│   ├─ metrics_inventory.csv               # 160 metrics 下载清单
│   ├─ cohort_candidates.csv               # 160 系统筛选证据
│   ├─ cohort_scan_daily.csv               # 75 抽样日质量审计
│   ├─ derived_dc_power_validation.csv     # RTC V×I 重建验证 (×12)
│   ├─ q1_cohort_selected.csv              # ★ 最终 12 台决策表
│   ├─ multimonth_download_manifest.csv    # 1083 文件下载 manifest
│   ├─ multimonth_scope.csv                # 36 system-month 范围
│   ├─ pvdata_availability.csv             # 25 系统 S3 可用范围
│   ├─ system_summary.csv                  # 首轮 3 系统摘要
│   ├─ channel_summary.csv                 # 首轮 44 metric 审计
│   ├─ daily_quality.csv                   # 首轮 90 天质量
│   └─ equipment_*.csv / .json             # 首轮设备元数据
└─ converted/                              # ← Task#4 产出（待建）
```

## 9. 环境与约束

- **conda 环境**：`cp_web`（aeon/numba/sklearn/pyarrow/pandas 可用，sktime 不可用）
- **工作区极脏**：禁止 reset/clean/commit/切分支
- **全项目相对路径**：不写绝对路径
- **临时脚本用完删除**：Task 1-3 的所有 `_tmp_pvdaq_*` 已删除
- **持久代码加 `@AI_GENERATED`**：Task #4 的转换器是持久模块，需加标记
- **原始 parquet 不改**：转换结果写到 `converted/` 子目录
- **许可**：`local_validation` only，`redistribution_allowed=false`

## 10. 关联文档

| 文档 | 职责 |
|---|---|
| `day-path-external-validation-q1q2-plan-2026-09-04.md` | Q1/Q2 两层验证方案总纲 |
| `pvdaq-data-analysis-2026-09-04.md` | 首轮 3 系统实拉与分析结果 |
| `AGENTS.md` | 仓库全局认知与协作约定 |

## 11. 下一步（按顺序）

1. **Task #4**：写持久转换模块 `backend-service/services/benchmark/pvdaq_converter.py`（或等价位置），逐系统-月处理 1,083 个原始日文件→产出 36 个转换后 parquet
2. **Task #5**：在转换后数据上跑 PR 真值生成，产出日级二分类金标 CSV
3. **Task #6**：RF/TSC 二分类方法重拟合 + device-isolated CV
4. **Task #7**：Path(a) 合同不兼容报告 + 可选 sensitivity
5. **Task #8**：汇总报告 + 自审交付
<!-- @AI_GENERATED: end -->
