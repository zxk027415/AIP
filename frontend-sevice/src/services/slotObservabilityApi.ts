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
};

export const slotObservabilityApi = {
  getCalendar: (slot: string, dayFrom: string, dayTo: string, page = 1): Promise<ObservabilityCalendar> =>
    api.get('/slot-datasets/observability/calendar', { params: { slot, from: dayFrom, to: dayTo, page } }),

  getCurve: (slot: string, device: string, dayFrom: string, dayTo: string): Promise<{ points: Array<{ time: string; value: number | null; label?: unknown }> }> =>
    api.get('/slot-datasets/observability/curve', { params: { slot, device, from: dayFrom, to: dayTo } }),

  advanceDay: (slot: string, operator = 'ui'): Promise<{ watermark_day?: string; ledger?: Record<string, unknown> }> =>
    api.post('/slot-datasets/observability/advance-day', { slot, operator }),

  manualDetect: (body: { slot: string; device_key: string; day?: string; operator?: string; reason?: string }) =>
    api.post('/slot-datasets/observability/manual-detect', body),

  mockGoldReview: (slot: string, maxUnits = 30): Promise<{
    hit_count?: number;
    note?: string;
    review_id?: string;
    origin?: string;
    accuracy?: { classifier_accuracy?: number; counted_units?: number; macro?: { f1?: number } };
    by_model?: Record<string, MockModelAccuracy>;
    better_model_candidate_id?: string | null;
  }> =>
    api.post('/slot-datasets/mock-gold-review', { slot, max_units: maxUnits }),

  getMockAccuracy: (slot: string): Promise<MockAccuracyView> =>
    api.get('/slot-datasets/mock-accuracy', { params: { slot } }),
};

export type MockModelAccuracy = {
  role?: string;
  model_candidate_id?: string;
  classifier_accuracy?: number | null;
  macro_f1?: number | null;
  counted_units?: number;
  origin?: string;
};

export type MockAccuracyView = {
  slot?: string;
  review_id?: string;
  origin?: string;
  note?: string;
  hit_count?: number;
  empty?: boolean;
  by_model?: Record<string, MockModelAccuracy>;
  better_model_candidate_id?: string | null;
};
