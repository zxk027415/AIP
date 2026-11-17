import api from './api';

export type PointAlarmSummary = {
  slot: string;
  entity_count: number;
  active_alarm_count: number;
  active_alarms: Array<Record<string, unknown>>;
  recent_events: Array<Record<string, unknown>>;
};

export type ReplayEntityOverview = {
  entity_key: string;
  site_id?: string;
  device_id?: string;
  branch_id?: string;
  source_points: number;
  replayed_points: number;
  last_source_time?: string | null;
  last_replay_time?: string | null;
  last_label?: number | null;
};

export type ReplaySessionView = {
  session_id: string;
  status?: string;
  cursor?: number;
  total?: number;
  total_points?: number;
  model_ref?: string | null;
  error?: string | null;
  dataset_profile_id?: string | null;
  entity_overview?: ReplayEntityOverview[];
  recent_outcomes?: Array<Record<string, unknown>>;
  latest_outcome_days?: string[];
};

export const timeseriesReplayApi = {
  getAlarmSummary: (slot: string, dayFrom?: string, dayTo?: string): Promise<PointAlarmSummary> =>
    api.get(`/timeseries-replay/slots/${encodeURIComponent(slot)}/alarms/summary`, {
      params: { ...(dayFrom && dayTo ? { day_from: dayFrom, day_to: dayTo } : {}) },
    }),

  getAlarmEvents: (
    slot: string,
    limit = 20,
  ): Promise<{ slot: string; events: Array<Record<string, unknown>> }> =>
    api.get(`/timeseries-replay/slots/${encodeURIComponent(slot)}/alarms/events`, {
      params: { limit },
    }),

  getPendingFeedSummary: (slot: string): Promise<PendingFeedSummary> =>
    api.get(`/timeseries-replay/slots/${encodeURIComponent(slot)}/pending-feed/summary`),

  getReplaySession: (sessionId: string, dayFrom?: string, dayTo?: string): Promise<ReplaySessionView> =>
    api.get(`/timeseries-replay/sessions/${encodeURIComponent(sessionId)}`, {
      params: { ...(dayFrom && dayTo ? { day_from: dayFrom, day_to: dayTo } : {}) },
    }),

  getAlarmPolicy: (slot: string): Promise<{
    slot: string;
    open_consecutive_points: number;
    close_consecutive_points: number;
    label_switch_consecutive_points: number;
    cold_start_alarm_enabled: boolean;
    min_confidence: number;
  }> => api.get(`/timeseries-replay/slots/${encodeURIComponent(slot)}/alarms/policy`),

  updateAlarmPolicy: (
    slot: string,
    body: {
      open_consecutive_points: number;
      close_consecutive_points?: number;
      label_switch_consecutive_points?: number;
      cold_start_alarm_enabled?: boolean;
      min_confidence?: number;
    },
  ): Promise<{
    slot: string;
    open_consecutive_points: number;
    close_consecutive_points: number;
    label_switch_consecutive_points: number;
    cold_start_alarm_enabled: boolean;
    min_confidence: number;
  }> => api.put(`/timeseries-replay/slots/${encodeURIComponent(slot)}/alarms/policy`, body),
};
