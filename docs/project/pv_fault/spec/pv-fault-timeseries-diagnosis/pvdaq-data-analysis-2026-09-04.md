<!-- @AI_GENERATED -->
# NREL PVDAQ 数据实拉与首轮结构分析

> 文档状态：数据已下载 + 首轮分析完成，供 RF/TSC 验证方案讨论使用
> 日期：2026-09-04
> 关联文档：`day-path-external-validation-q1q2-plan-2026-09-04.md`（天路径 Q1/Q2 验证方案，本分析为其 §11-1「下载 PVDAQ + 核实 schema」的落地结果）
> 数据用途：`local_validation`（本地验证）；许可 `redistribution_allowed=false`（不可再分发），仅本地分析

---

## 1. 先看结论

1. **真实 PVDAQ pvdata 是「长表」，不是宽表。** 每行是 `measured_on / utc_measured_on / metric_id / value`，一个物理通道对应一个 `metric_id`，要靠 `metrics/` 元数据把 `metric_id` 解码成 DC 电流 / POA 辐照度 / 组件温度等。仓库里 `benchmark_pvdaq_system683` 的宽表 fixture（`dc_voltage,dc_current,...` 五列 10 行）是**手造占位**，与真实格式不一致。
2. **`system 683` 在当前 OEDI 数据湖里不存在。** 现有真实系统是 10/2/3/4/33-36/50/51、1199–1433、2045、4901-4903。benchmark 槽位名里的「683」是虚构的，验证要改用真实系统号。
3. **已下载 3 个真实系统 2015-06 全月**（system 4 / 10 / 34，共 90 个 daily parquet，约 12 MB）+ 全套元数据（systems/sites/modules/inverters/mount/metrics）。
4. **system 4 是首选 Q1 样本**：30/30 天核心通道 100% 完整，PR 中位 0.762，且 **6/29 是一个真实异常日**（正午 4 小时掉电，PR 0.284）。
5. **system 10 暴露了一个真实数据质量事件**：POA 辐照度传感器约 6/10 起持续写 `-99999` 缺测哨兵值，导致 30 天里只有 8 天可算 PR。这本身是「传感器故障」类可检测事件，但削弱了它做 PR 基准的能力。
6. **物理 `i_cal`（理论电流）当前无法纯物理推算**：OEDI 元数据只有组件厂商/型号/数量，**没有 Isc 或温度系数**。当前能可靠算的是**功率口径 PR**（只需额定功率 + POA，均有）；电流口径 `i_cal` 只能走「数据驱动期望电流」（用正常日拟合 `k×POA×温度修正`），属半经验，须显式记录。这与验证方案 §6「`i_cal` 推算属半仿真」一致。

---

## 2. 数据来源与下载范围

| 项 | 值 |
|---|---|
| 数据湖 | AWS OEDI 开放数据桶 `oedi-data-lake`（公开、无需凭据） |
| 路径前缀 | `pvdaq/parquet/pvdata/system_id=<sid>/year=<Y>/month=<M>/day=<D>/…snappy.parquet` |
| 官方入口 | OEDI submission 4568；工具 [NREL/pvdaq_access](https://github.com/NREL/pvdaq_access)（BSD-3-Clause） |
| 下载系统 | 4、10、34（各 2015-06 全月 30 天） |
| 元数据 | `systems / sites / modules / inverters / mount` 各一份 + `metrics/metrics__system_<sid>__part000.parquet` |
| 本地落点 | `backend-service/data/benchmark_raw/pvdaq/`（项目相对路径；未跟踪，不提交、不再分发） |
| 总量 | 106 文件，约 12.5 MB |

> 内容依据 NREL/pvdaq_access 官方说明改述以符合许可：公开 PV 站数据经 OEDI 数据湖发布，按系统存为每日 CSV/Parquet。

---

## 3. 真实数据结构（已核实）

### 3.1 pvdata 长表 schema

| 列 | 中文含义 | 说明 |
|---|---|---|
| `measured_on` | 本地测量时刻 | 100% 非空；老系统时区为站点本地时 |
| `utc_measured_on` | UTC 测量时刻 | system 4/10/34 上 **0% 非空**（新系统如 2045/4901 才 100%）→ 老系统只能用本地时 + 站点经纬度推时区 |
| `metric_id` | 通道 ID | 关联 `metrics` 表解码物理含义 |
| `value` | 原始测量值 | 需按 `metrics.calc_scale`/`calc_offset` 缩放（如 system 34 的 `dc_power_hW` scale=100，华氏温度用 scale/offset 转摄氏） |

### 3.2 metric 元数据关键列

`metrics__system_<sid>__part000.parquet`：`system_id, metric_id, sensor_name, common_name, raw_units, units, calc_scale, calc_offset, aggregation_type, standard_name` 等。`common_name` 是稳定的物理角色名（`DC current` / `Irradiance POA` / `Temperature module` / `DC power` / `AC power`…），本分析按它把长表解码成核心通道。

### 3.3 分区与采样

- 分区：`system_id → year → month → day`，每日一个 `snappy.parquet`。
- 采样率**按系统不同**：system 4/10 = 1 分钟；system 34 = 15 分钟。→ 进天路径前需重采样到 5min（1min 下采样）或按原生采样把 `window_length` 从 288 改成「当日点数」（如 15min→96）。禁止把 15min 假上采样成 5min。

---

## 4. 三系统摘要（2015-06，修正 sentinel 后）

| system | 名称 / 类型 | 额定 | 原生采样 | 合格天 | PR 中位 | 电流-辐照度相关(中位) | 备注 |
|---:|---|---:|---:|---:|---:|---:|---|
| 4 | NREL x-Si（单晶硅实验） | 1.0 kW | 1min | 30/30 | 0.762 | 0.998 | 干净；含 6/29 异常日 |
| 10 | NREL CIS（薄膜实验） | 1.12 kW | 1min | 8/30 | 0.759 | 0.998 | POA 传感器 6/10 起失效（-99999） |
| 34 | Andre Agassi 学校 A 楼（商业屋顶） | 146.64 kW | 15min | 30/30 | 0.596 | 0.971 | 商业站，PR 基线偏低但全月稳定 |

字段口径：`quality_eligible`（当日每个核心通道覆盖 ≥90% 才计 PR）；`performance_ratio = AC 日发电量 / (额定功率 × POA 日辐照量)`；`relative_pr = PR / 合格天 PR 中位`；`low_performance_candidate = relative_pr < 0.7`。

---

## 5. 两个关键数据质量发现

### 5.1 system 10：辐照传感器缺测哨兵（-99999）

`poa_irradiance` 原始值 81.8% 是 `-99999`，从约 6/10 起持续。首版分析误当成有效负值 → 完整度虚高、6/9 出现假 PR=1.25。修正口径：`raw ≤ -90000` 视为缺失；PR 仅在核心通道覆盖 ≥90% 时计算。修正后 22 天被正确排除。

**启示**：外部真实数据必带缺测哨兵/坏传感器，Q1 管道必须先做 sentinel 清洗 + 覆盖门，否则「异常检测」会被数据质量噪声污染。这条同样适用于把外部数据喂进 RF/TSC 前。

### 5.2 system 4 · 6/29：教科书级 Q1 异常（正午掉电）

日内小时曲线（本地时，仅白天）：

| 时段 | POA(W/m²) | AC(W) | DC 电流(A) | 状态 |
|---|---:|---:|---:|---|
| 5–7 时 | 37→368 | 16→254 | 正常跟随 | 正常爬升 |
| **9–12 时** | **770–974（正午最强）** | **≈2.58** | **≈0.00** | **持续 4 小时掉电** |
| 13–18 时 | 745→32 | 恢复正常 | 恢复 | 恢复 |

- 全天 PR 0.284（相对基线 0.37），当天「电流 vs 辐照度」相关 -0.087（正常日 ≈0.998）。
- 形态是**部分时段跳闸/掉电**，不是整日均匀降额——这正好区分 RF 与 TSC（见 §7）。

---

## 6. 与平台 pv schema 的差距 + 适配点（对照方案 §6）

平台天路径要 `time / value(实测电流) / i_cal(理论电流) / site_id / device_id / branch_id / label`。PVDAQ 差距与落地：

| 适配项 | PVDAQ 现状 | 落地做法 | 状态 |
|---|---|---|---|
| 时间列 | `measured_on` 本地时，无 UTC（老系统） | 用站点经纬度定时区；天级聚合按本地日即可 | 可做 |
| `value`（实测电流） | `metric common_name = DC current` | 长表按 metric_id 透视取 DC 电流 | 可做 |
| `i_cal`（理论电流） | **无**；只有 POA 辐照度 + 组件温度 + 组件型号（无 Isc/温度系数） | 短期：数据驱动期望电流 `k×POA×温度修正`（正常日拟合 k）；或查组件 datasheet 补 Isc/α。**纯物理 i_cal 不可即得** | 半经验，须记录 |
| 功率 PR（Q1 真值） | 额定功率 + POA 齐全 | `AC 能量 / (额定 × POA 能量)` | **可即得** |
| 实体键 | 只有 `system_id` | 注入 `site_id=站点, device_id=system_id, branch_id`（单串填固定值） | 可做 |
| 采样率 | 1min 或 15min | 重采样到 5min，或参数化 `window_length` | 可做 |
| 标签 | 无 | Q1 用物理真值（PR/残差）；Q2 需另找带标注数据集 | 符合方案 |
| 缺测哨兵 | `-99999` | 清洗为 NaN + 覆盖门 | **必做** |

关键结论：**Q1（检测）现在就能落地**（功率 PR 真值 + 多设备）；`i_cal` 电流口径要么接受半经验拟合、要么补组件参数，不能假装已能纯物理推算。

---

## 7. 对 RF vs TSC 分别验证的启示（讨论铺垫）

以 6/29 正午掉电为例：

- **RF（天路径 `pv_day`）**：把整天 `value`+`i_cal` 压成 50 个统计特征（均值/方差/分位/差分/平台段…）。正午 4 小时归零会拉低均值、抬高方差、产生长零平台和大跌落 → **能判「异常日」**，但统计量把「洞发生在正午」的时间信息抹平了。
- **TSC（天路径 `pv_tsc`）**：MultiRocket 直接吃 288 点日内曲线，「正常爬升→正午骤降归零→恢复」是卷积核天然擅长的波形 → 不仅判异常，还保留了**时间定位与形状**。

由此引出 Q1/Q2 下 RF 与 TSC 的验证侧重点（细节留待讨论）：
- **Q1（检测）**：两者都应能抓到这类日；比的是**检测召回/误报**和对数据质量噪声（sentinel、传感器失效）的鲁棒性。
- **Q2（分类）**：差异主要在这里——「正午跳闸+恢复」vs「整日均匀降额（如积灰）」的**波形区分**是 TSC 的强项；RF 的日统计更容易把不同成因的低 PR 混为一类。但 Q2 需要故障类型金标，PVDAQ 无标签 → 仍要靠 UTFPR/Réunion。

---

## 8. 产出的证据文件（均在 `backend-service/data/benchmark_raw/pvdaq/analysis/`）

| 文件 | 内容 |
|---|---|
| `system_summary.csv` | 3 系统的实体、额定、采样率、完整度、PR 摘要、核心通道 metric_id 映射 |
| `channel_summary.csv` | 每个 metric 的物理名/单位/缩放/覆盖率/范围/sentinel 计数/采样间隔 |
| `daily_quality.csv` | 90 条逐日记录：完整度、各通道有效点、AC 能量、POA 辐照量、PR、相对 PR、低表现标记 |
| `equipment_{sites,modules,inverters,mount}_selected.csv` | 3 系统的站点/组件/逆变器/安装元数据 |
| `equipment_metadata_selected.json` | 上述元数据合并 JSON |

原始 daily parquet 与元数据 parquet 保持不改；分析脚本为临时脚本，已按项目规则删除，方法与参数记录于本文件以便复现。

---

## 9. 没验证 / 待确认

- 只分析了 2015-06 单月 3 系统；跨季节、跨更多系统（尤其新系统 4901 的上百通道、坏传感器）未覆盖。
- 物理 `i_cal` 所需组件 Isc/温度系数未查 datasheet；数据驱动期望电流的拟合稳健性未做。
- system 34 商业站 PR≈0.60 偏低的成因（额定/面积口径 vs 真实低效）未深究。
- `measured_on` 时区仅按经纬度推断，未与官方站点时区表交叉核对。
- 未把数据接入平台 `load_csv → tsc_sliding_window`，尚未跑通端到端切窗（下一步）。

---

## 10. 下一步

1. 与用户讨论定 RF vs TSC 在 Q1/Q2 下各自的验证口径（本文件 §7 为起点）。
2. 写外部→pv schema 的前置转换脚本（列映射 + 实体键 + 5min 重采样 + sentinel 清洗 + 数据驱动 `i_cal`）。
3. Q1 物理真值：把 PR/残差规则固化，产出日级二分类真值。
4. 建日级 benchmark 槽位（指向 `pv_tsc`/`pv_day` 工作流，`benchmark_reuse` + `governance_eligible=false`），predict-only 跑通。
<!-- @AI_GENERATED: end -->
