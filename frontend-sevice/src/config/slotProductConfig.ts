/** Product slots for PV day/point redesign (workflow-shaped, aligned with load_forecast). */

export type PvProductSlot = 'pv_day' | 'pv_point';

export type BenchmarkSlot =
  | 'benchmark_nasa_smap_msl'
  | 'benchmark_fhc_twin_plant'
  | 'benchmark_pvdaq_system683';

export type KnownSlot = PvProductSlot | BenchmarkSlot;

export const PV_PRODUCT_SLOTS: readonly PvProductSlot[] = ['pv_day', 'pv_point'];

export const BENCHMARK_SLOTS: readonly BenchmarkSlot[] = [
  'benchmark_nasa_smap_msl',
  'benchmark_fhc_twin_plant',
  'benchmark_pvdaq_system683',
];

export function isPvProductSlot(slot: string): slot is PvProductSlot {
  return (PV_PRODUCT_SLOTS as readonly string[]).includes(slot);
}

export function isBenchmarkSlot(slot: string): slot is BenchmarkSlot {
  return slot.startsWith('benchmark_');
}

export function isKnownWorkflowSlot(slot: string): slot is KnownSlot {
  return isPvProductSlot(slot) || isBenchmarkSlot(slot);
}

/** 用户可见分区名。URL/API/JSON 仍用 slot。 */
export const SCENE_WORD = '场景';

/** load_forecast Arena（生产/影子/预上线/MAPE）只服务这些槽位，禁止 PV/benchmark 回退到它。 */
export function isLoadForecastArenaSlot(slot: string): boolean {
  return slot === 'load_forecast' || slot === 'default' || slot === 'load_forecast_e2e_demo';
}

export type PredictTemplateRole = 'predict' | 'predict_replay';

export type ExecutionPurpose = 'product_workflow' | 'benchmark_reuse';

export interface SlotWorkflowConfig {
  slot: string;
  label: string;
  shortLabel: string;
  description: string;
  trainWorkflowId: string;
  predictWorkflowId: string;
  labelWorkflowId?: string;
  predictTemplateRole: PredictTemplateRole;
  executionPurpose: ExecutionPurpose;
  governanceEligible: boolean;
  datasetProfileId?: string;
}

export type SlotProductConfig = SlotWorkflowConfig & { slot: PvProductSlot };

export const SLOT_PRODUCT_CONFIG: Record<PvProductSlot, SlotProductConfig> = {
  pv_day: {
    slot: 'pv_day',
    label: 'pv_day（光伏天路径）',
    shortLabel: '天路径',
    description: '设备日特征 + 天级 train_eval / predict 工作流；形状对齐负荷预测。',
    trainWorkflowId: 'workflow-pv-day-train-eval-v1',
    predictWorkflowId: 'workflow-pv-day-predict-v1',
    labelWorkflowId: 'workflow-pv-day-label-v1',
    predictTemplateRole: 'predict',
    executionPurpose: 'product_workflow',
    governanceEligible: true,
  },
  pv_point: {
    slot: 'pv_point',
    label: 'pv_point（光伏点路径）',
    shortLabel: '点路径',
    description: '真实事件点 causal window + replay_activity；train_eval / predict_replay 冻结 graph。',
    trainWorkflowId: 'workflow-pv-point-train-eval-v1',
    predictWorkflowId: 'workflow-pv-point-predict-replay-v1',
    labelWorkflowId: 'workflow-pv-point-label-v1',
    predictTemplateRole: 'predict_replay',
    executionPurpose: 'product_workflow',
    governanceEligible: true,
  },
};

export const BENCHMARK_SLOT_CONFIG: Record<BenchmarkSlot, SlotWorkflowConfig> = {
  benchmark_nasa_smap_msl: {
    slot: 'benchmark_nasa_smap_msl',
    label: 'benchmark_nasa_smap_msl（NASA SMAP/MSL）',
    shortLabel: 'NASA',
    description: 'index-clock NPY/CSV demo；复用 pv_point ts_point_* 拓扑；禁止产品治理写入。',
    trainWorkflowId: 'workflow-benchmark-nasa-point-train-eval-v1',
    predictWorkflowId: 'workflow-pv-point-predict-replay-v1',
    predictTemplateRole: 'predict_replay',
    executionPurpose: 'benchmark_reuse',
    governanceEligible: false,
    datasetProfileId: 'benchmark-nasa-smap-msl-demo',
  },
  benchmark_fhc_twin_plant: {
    slot: 'benchmark_fhc_twin_plant',
    label: 'benchmark_fhc_twin_plant（FHC Twin-Plant）',
    shortLabel: 'FHC',
    description: '30s event-time 光伏迁移 demo；复用 pv_point 工作流拓扑；禁止产品治理写入。',
    trainWorkflowId: 'workflow-pv-point-train-eval-v1',
    predictWorkflowId: 'workflow-pv-point-predict-replay-v1',
    predictTemplateRole: 'predict_replay',
    executionPurpose: 'benchmark_reuse',
    governanceEligible: false,
    datasetProfileId: 'benchmark-fhc-twin-plant-demo',
  },
  benchmark_pvdaq_system683: {
    slot: 'benchmark_pvdaq_system683',
    label: 'benchmark_pvdaq_system683（NREL PVDAQ · 无标签）',
    shortLabel: 'PVDAQ',
    description: 'NREL system 683 无标签 demo；原生 event-time 逐点 replay；禁止伪造 benchmark_ground_truth 与产品治理写入。',
    trainWorkflowId: 'workflow-pv-point-train-eval-v1',
    predictWorkflowId: 'workflow-pv-point-predict-replay-v1',
    predictTemplateRole: 'predict_replay',
    executionPurpose: 'benchmark_reuse',
    governanceEligible: false,
    datasetProfileId: 'benchmark-pvdaq-system683-demo',
  },
};

export function getSlotWorkflowConfig(slot: string): SlotWorkflowConfig | null {
  if (isPvProductSlot(slot)) return SLOT_PRODUCT_CONFIG[slot];
  if (isBenchmarkSlot(slot) && slot in BENCHMARK_SLOT_CONFIG) {
    return BENCHMARK_SLOT_CONFIG[slot as BenchmarkSlot];
  }
  return null;
}

export const PV_PRODUCT_SLOT_SELECT_OPTIONS = PV_PRODUCT_SLOTS.map((slot) => ({
  label: SLOT_PRODUCT_CONFIG[slot].label,
  value: slot,
}));

export const BENCHMARK_SLOT_SELECT_OPTIONS = BENCHMARK_SLOTS.map((slot) => ({
  label: BENCHMARK_SLOT_CONFIG[slot].label,
  value: slot,
}));
