import api from './api';

export type ObservabilityCell = {
  date: string;
  arrived_count?: number;
  expected_count?: number;
  completeness?: number | null;
  status?: string;
  model_id?: string | null;
  skip_reason?: string | null;
  late_arrival?: boolean;
};

export type ObservabilityRow = {
  device_key: string;
  site_id?: string;
  device_id?: string;
  branch_id?: string;
  cells: ObservabilityCell[];
};

export type ObservabilityStatus = {
  slot?: string;
  demo?: boolean;
  note?: string;
  // @AI_GENERATED: pv_tsc 只读观测标记；前端据此禁用演示推进/手工补检。
  readonly?: boolean;
  // @AI_GENERATED: end
  clock?: {
    kind?: string;
    day?: string | null;
    timestamp?: string | null;
    source?: string | null;
  };
  progress?: {
    day_index?: number;
    // @AI_GENERATED: pv_tsc 无演示总天数，允许为空。
    total_days?: number | null;
    // @AI_GENERATED: end
    fed_days?: string[];
    exhausted?: boolean;
  };
  window?: { from?: string | null; to?: string | null };
  accuracy?: {
    day?: string;
    classifier_accuracy?: number | null;
    counted_units?: number;
    macro_f1?: number | null;
    macro_precision?: number | null;
    macro_recall?: number | null;
    confirm_count?: number;
    correct_count?: number;
    review_id?: string;
    admitted?: boolean;
  } | null;
  replay?: {
    session_id?: string;
    selection_policy?: string;
    legacy?: boolean;
    cursor?: number;
    total?: number;
    status?: string;
    event_clock?: string | null;
    last_entity?: string | null;
    empty?: boolean;
  };
  feed?: {
    dataset_ref?: string | null;
    point_progress?: Record<string, number>;
    point_totals?: Record<string, number>;
    pending_days?: Record<string, { status?: string; arrived_points?: number }>;
    waiting_days?: number;
    expired_days?: number;
  };
  demo_replay?: ObservabilityStatus;
};

export type ObservabilityCalendar = {
  slot: string;
  from: string;
  to: string;
  watermark_day?: string | null;
  occupancy_ready?: number;
  expected_points?: number;
  page: number;
  page_size: number;
  device_total: number;
  days: string[];
  rows: ObservabilityRow[];
  clock?: ObservabilityStatus['clock'];
  demo_note?: string;
  accuracy?: ObservabilityStatus['accuracy'];
  // @AI_GENERATED: pv_tsc 日历只读标记，透传自后端 calendar_grid。
  readonly?: boolean;
  // @AI_GENERATED: end
};

export const slotObservabilityApi = {
  getStatus: (slot: string): Promise<ObservabilityStatus> =>
    api.get('/slot-datasets/observability/status', { params: { slot } }),

  getCalendar: (slot: string, dayFrom?: string, dayTo?: string, page = 1): Promise<ObservabilityCalendar> =>
    api.get('/slot-datasets/observability/calendar', {
      params: {
        slot,
        page,
        ...(dayFrom && dayTo ? { from: dayFrom, to: dayTo } : {}),
      },
    }),

  getCurve: (slot: string, device: string, dayFrom: string, dayTo: string): Promise<{
    points: Array<{ time: string; value: number | null; label?: unknown; predicted_label?: unknown }>;
  }> =>
    api.get('/slot-datasets/observability/curve', { params: { slot, device, from: dayFrom, to: dayTo } }),

  getOutcomes: (slot: string, dayFrom?: string, dayTo?: string): Promise<{
    slot?: string;
    from?: string | null;
    to?: string | null;
    count?: number;
    source?: string;
    items?: Array<{
      unit_key?: string;
      site_id?: string;
      device_id?: string;
      branch_id?: string;
      date?: string;
      time?: string;
      predicted_label?: number;
      gold_label?: number;
      confidence?: number;
      kind?: string;
      i_cal?: number;
      value?: number;
    }>;
    daily_units?: Array<{
      unit_key?: string;
      site_id?: string;
      device_id?: string;
      branch_id?: string;
      date?: string;
      time?: string;
      predicted_label?: number;
      gold_label?: number;
      confidence?: number;
      kind?: string;
      i_cal?: number;
      point_count?: number;
    }>;
    daily_count?: number;
    // @AI_GENERATED
    label_names?: Record<string, string>;
    // @AI_GENERATED: end
  }> =>
    api.get('/slot-datasets/observability/outcomes', {
      params: {
        slot,
        ...(dayFrom && dayTo ? { from: dayFrom, to: dayTo } : {}),
      },
    }),

  // @AI_GENERATED
  advanceDay: (slot: string, operator = 'ui', useRealModel = false): Promise<{
    watermark_day?: string;
    demo?: boolean;
    note?: string;
    cycle?: {
      fed_day?: string;
      review_id?: string;
      admitted?: boolean;
      accuracy?: { classifier_accuracy?: number; counted_units?: number };
      note?: string;
      use_real_model?: boolean;
      model_id?: string;
    };
  }> =>
    api.post('/slot-datasets/observability/advance-day', { slot, operator, use_real_model: useRealModel }),
  // @AI_GENERATED: end

  resetDemo: (slot: string) =>
    api.post('/slot-datasets/observability/reset-demo', { slot }),

  manualDetect: (body: { slot: string; device_key: string; day?: string; operator?: string; reason?: string }) =>
    api.post('/slot-datasets/observability/manual-detect', body),

  rebuildReplay: (slot: string, operator = 'ui'): Promise<{
    ok?: boolean;
    session_id?: string;
    selection_policy?: string;
    legacy?: boolean;
  }> =>
    api.post('/slot-datasets/observability/rebuild-replay', { slot, operator }),

  replayStep: (slot: string, points: 1 | 10 | 50, operator = 'ui'): Promise<{
    ok?: boolean;
    session_id?: string;
    requested?: number;
    last?: Record<string, unknown>;
  }> =>
    api.post('/slot-datasets/observability/replay-step', { slot, points, operator }),

  // @AI_GENERATED
  mockGoldReview: (slot: string, maxUnits = 30, useRealModel = false): Promise<{
    note?: string;
    review_id?: string;
    fed_day?: string;
    admitted?: boolean;
    accuracy?: { classifier_accuracy?: number; counted_units?: number };
    hit_count?: number;
    origin?: string;
    usable?: boolean;
    promote_eligible?: boolean;
    holdout_unit_count?: number;
    class_support?: Record<string, number>;
    time_wall?: TimeWallView | null;
    by_model?: Record<string, MockModelAccuracy>;
    better_model_candidate_id?: string | null;
    use_real_model?: boolean;
    model_id?: string;
  }> =>
    api.post('/slot-datasets/mock-gold-review', { slot, max_units: maxUnits, use_real_model: useRealModel }),
  // @AI_GENERATED: end

  getMockAccuracy: (slot: string): Promise<MockAccuracyView> =>
    api.get('/slot-datasets/mock-accuracy', { params: { slot } }),

  getTimeWall: (slot: string): Promise<TimeWallView> =>
    api.get('/slot-datasets/time-wall', { params: { slot } }),

  getFeedSources: (limit = 200) =>
    api.get('/slot-datasets/feed-sources', { params: { limit } }) as Promise<{
      candidates: Array<{ dataset_ref: string }>;
      current: Record<string, unknown>;
    }>,

  selectFeedSource: (slot: string, datasetRef: string | null, operator = 'ui') =>
    api.post('/slot-datasets/feed-sources/select', {
      slot,
      dataset_ref: datasetRef,
      operator,
    }),

  replayAdvanceTsc: (operator = 'ui', useRealModel = false): Promise<{
    slot?: string;
    demo?: boolean;
    production_write?: boolean;
    fed_day?: string | null;
    note?: string;
    cycle?: Record<string, unknown>;
  }> =>
    api.post('/slot-datasets/observability/pv-tsc/replay-advance', {
      operator,
      use_real_model: useRealModel,
    }),
};

export type TimeWallView = {
  slot?: string;
  empty?: boolean;
  locked?: boolean;
  fraction?: number;
  holdout_start_day?: string | null;
  holdout_end_day?: string | null;
  train_start_day?: string | null;
  train_end_day?: string | null;
  labeled_day_count?: number;
  holdout_day_count?: number;
  train_day_count?: number;
};

export type MockModelAccuracy = {
  role?: string;
  model_candidate_id?: string;
  classifier_accuracy?: number | null;
  macro_f1?: number | null;
  counted_units?: number;
  origin?: string;
  class_support?: Record<string, number>;
};

export type DailyAccuracyRow = {
  day?: string;
  review_id?: string;
  counted_units?: number;
  classifier_accuracy?: number | null;
  macro_f1?: number | null;
  macro_precision?: number | null;
  macro_recall?: number | null;
  confirm_count?: number;
  correct_count?: number;
  admitted?: boolean;
};

export type MockAccuracyView = {
  slot?: string;
  review_id?: string;
  origin?: string;
  note?: string;
  hit_count?: number;
  empty?: boolean;
  usable?: boolean;
  promote_eligible?: boolean;
  sampled?: boolean;
  evaluation_kind?: string;
  reason?: string | null;
  holdout_unit_count?: number;
  class_support?: Record<string, number>;
  time_wall?: TimeWallView | null;
  by_model?: Record<string, MockModelAccuracy>;
  better_model_candidate_id?: string | null;
  by_day?: DailyAccuracyRow[];
  latest?: DailyAccuracyRow | null;
  cumulative?: {
    day_count?: number;
    counted_units?: number;
    confirm_count?: number;
    correct_count?: number;
    classifier_accuracy?: number | null;
    note?: string;
  };
};
