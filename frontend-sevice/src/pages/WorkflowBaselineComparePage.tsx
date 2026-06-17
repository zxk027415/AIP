import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Alert, Button, Card, Checkbox, Descriptions, Drawer, Form, Input, InputNumber,
  Modal, Select, Space, Spin, Table, Tabs, Tag, Tooltip, Typography, Switch, Collapse, Progress, message,
} from 'antd';
import { useTranslation } from 'react-i18next';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import { enhancedWorkflowApi, baselineCompareApi, cloneWorkflowApi } from '../services/workflowEnhancedApi';
import type { WorkflowParamsSummary, ParamField, NodeParamGroup } from '../services/workflowEnhancedApi';
import type { EnhancedWorkflow, EnhancedWorkflowSummary } from '../types/workflow-enhanced';
import DatasetPanel from '../components/DatasetPanel';
import './WorkflowBaselineComparePage.css';

const { Text } = Typography;

const autoResearchPanelStyle: React.CSSProperties = {
  marginBottom: 16,
  border: '1px solid #d6e7ff',
  boxShadow: '0 6px 18px rgba(22, 119, 255, 0.08)',
};

const autoResearchOverviewStyle: React.CSSProperties = {
  marginBottom: 10,
  background: 'linear-gradient(135deg, #f7fbff 0%, #f8fffb 100%)',
  border: '1px solid #dcecff',
  borderRadius: 8,
};

const autoResearchMutedCardStyle: React.CSSProperties = {
  marginBottom: 16,
  borderRadius: 12,
  background: '#f8fafb',
  border: '1px solid #e8eef5',
};

// ── impeccable product register: 全局语义 token ──
const uiInk = '#1f2d3d';
const uiLabel = '#8c98a8';
const uiMuted = '#5a6776';
const uiGood = '#16a34a';
const uiBad = '#dc2626';
const uiWarn = '#d97706';
const uiAccent = '#1677ff';
const kvLabelStyle: React.CSSProperties = { fontSize: 11, color: uiLabel, letterSpacing: 0.3 };
const sectionLabelStyle: React.CSSProperties = { fontSize: 11, color: uiLabel, letterSpacing: 0.3, marginBottom: 8 };
const kvGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'auto 1fr',
  rowGap: 6,
  columnGap: 14,
  fontSize: 12,
  alignItems: 'baseline',
};
const statusDotColor: Record<string, string> = {
  success: uiGood, running: uiAccent, failed: uiBad, error: uiBad,
  cancelled: uiWarn, interrupted: uiWarn,
  open: uiAccent, testing: uiWarn, resolved: uiGood, stale: uiLabel, rejected: uiBad,
};
const StatusPill = ({ value }: { value: string }) => {
  const v = String(value || '').trim();
  const c = statusDotColor[v] || uiLabel;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: uiInk }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: c, display: 'inline-block' }} />
      {v || '-'}
    </span>
  );
};

const experimentSetupCardStyle: React.CSSProperties = {
  marginBottom: 16,
  border: '1px solid #e8eef5',
  borderRadius: 12,
  boxShadow: '0 2px 8px rgba(22, 119, 255, 0.06)',
};

const experimentSectionStyle: React.CSSProperties = {
  marginBottom: 12,
  border: '1px solid #edf1f7',
  borderRadius: 10,
  overflow: 'hidden',
};

const experimentSectionHeaderStyle: React.CSSProperties = {
  background: '#fbfdff',
  borderBottom: '1px solid #edf1f7',
  fontWeight: 600,
};

function formatGlmSkipReason(reason: unknown): string {
  const value = String(reason || '').trim();
  if (!value) return '';
  const labels: Record<string, string> = {
    no_recommended_proposal: '没有推荐 proposal',
    auto_apply_disabled: '自动应用未开启',
    validator_failed: 'validator 未通过',
    risk_exceeds_threshold: '风险超过阈值',
  };
  return labels[value] || value;
}

function getAutoResearchTrainingProgress(source: Record<string, unknown> | null | undefined) {
  const liveWrap = (source?.current_iteration_live as Record<string, unknown> | undefined) || {};
  const live = (liveWrap.live_summary as Record<string, unknown> | undefined) || {};
  const liveProgress = (liveWrap.progress as Record<string, unknown> | undefined) || {};
  const batchStatus = (source?.batch_eval_status as Record<string, unknown> | undefined) || {};

  const windowsDone = Number(live.windows_done);
  const windowsTotal = Number(live.windows_total);
  if (Number.isFinite(windowsDone) && Number.isFinite(windowsTotal) && windowsTotal > 0) {
    const currentWindow = live.current_window ? String(live.current_window) : '';
    const currentPhase = String(live.current_phase || '');
    const phaseLabel: Record<string, string> = {
      preparing: '准备训练',
      baseline_warmup: '预热 Baseline',
      baseline_running: 'Baseline 训练中',
      challenger_running: 'Challenger 训练中',
    };
    return {
      current: Math.max(0, windowsDone),
      total: Math.max(1, windowsTotal),
      label: '训练进度',
      detail: currentWindow
        ? `${phaseLabel[currentPhase] || '窗口回测训练中'} · ${currentWindow}`
        : (phaseLabel[currentPhase] || '窗口回测训练中'),
    };
  }

  const windowIndex = Number(liveProgress.window_index);
  const windowTotal = Number(liveProgress.window_total);
  if (Number.isFinite(windowIndex) && Number.isFinite(windowTotal) && windowTotal > 0) {
    return {
      current: Math.max(0, windowIndex),
      total: Math.max(1, windowTotal),
      label: '训练进度',
      detail: `窗口 ${windowIndex}/${windowTotal}`,
    };
  }

  const groups = (batchStatus.groups as Record<string, unknown>[] | undefined) || [];
  const totalGroups = Number(batchStatus.total_groups || groups.length || 0);
  if (Number.isFinite(totalGroups) && totalGroups > 1) {
    const doneGroups = groups.filter((g) => {
      const s = String(g.status || '').toLowerCase();
      return ['success', 'failed', 'error', 'cancelled', 'pruned'].includes(s);
    }).length;
    return {
      current: doneGroups,
      total: totalGroups,
      label: '并发训练进度',
      detail: `第 ${String(batchStatus.iteration ?? '-')} 轮 · ${totalGroups} 组`,
    };
  }

  return null;
}

function isAutoResearchRunningStatus(status: unknown) {
  return ['running', 'pending', 'cancelling'].includes(String(status || '').toLowerCase());
}

type AutoResearchCurvePoint = {
  timestamp: string;
  actual: number;
  predicted: number;
  baseline_predicted?: number;
  is_peak?: boolean;
  is_valley?: boolean;
  date?: string;
};

type AutoResearchCurveRow = {
  iteration: number;
  created_at?: string;
  points: AutoResearchCurvePoint[];
  source?: string;
};

function finiteNumberOrNull(value: unknown): number | null {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function normalizeAutoResearchCurvePoints(raw: unknown): AutoResearchCurvePoint[] {
  const rows = Array.isArray(raw) ? raw : [];
  return rows
    .map((item, idx) => {
      if (!item || typeof item !== 'object') return null;
      const row = item as Record<string, unknown>;
      const actual = finiteNumberOrNull(row.actual ?? row.y_true ?? row.true ?? row.observed);
      const predicted = finiteNumberOrNull(row.predicted ?? row.prediction ?? row.y_pred ?? row.forecast);
      if (actual === null || predicted === null) return null;
      const timestamp = String(row.timestamp ?? row.datetime ?? row.time ?? row.date ?? idx);
      return {
        timestamp,
        actual,
        predicted,
        baseline_predicted: finiteNumberOrNull(row.baseline_predicted) ?? undefined,
        is_peak: Boolean(row.is_peak),
        is_valley: Boolean(row.is_valley),
        date: row.date != null ? String(row.date) : undefined,
      };
    })
    .filter(Boolean) as AutoResearchCurvePoint[];
}

function normalizeAutoResearchCurveRow(
  raw: unknown,
  fallbackIteration: unknown,
  source: string,
): AutoResearchCurveRow | null {
  if (!raw || typeof raw !== 'object') return null;
  const row = raw as Record<string, unknown>;
  const iteration = finiteNumberOrNull(row.iteration ?? row.iteration_no ?? fallbackIteration);
  if (iteration === null || iteration <= 0) return null;
  const points = normalizeAutoResearchCurvePoints(row.points ?? row.actual_vs_predicted);
  if (points.length === 0) return null;
  return {
    iteration,
    created_at: row.created_at != null ? String(row.created_at) : undefined,
    points,
    source,
  };
}

function normalizeAutoResearchProfileCurve(
  raw: unknown,
  fallbackIteration: unknown,
  source: string,
): AutoResearchCurveRow | null {
  if (!raw || typeof raw !== 'object') return null;
  const row = raw as Record<string, unknown>;
  const iteration = finiteNumberOrNull(row.iteration ?? row.iteration_no ?? fallbackIteration);
  if (iteration === null || iteration <= 0) return null;

  const profilePoints: AutoResearchCurvePoint[] = [];
  const testProfiles = Array.isArray(row.test_profiles) ? row.test_profiles : [];
  testProfiles.forEach((profile) => {
    if (!profile || typeof profile !== 'object') return;
    profilePoints.push(...normalizeAutoResearchCurvePoints((profile as Record<string, unknown>).actual_vs_predicted));
  });
  if (profilePoints.length === 0 && row.test_profile && typeof row.test_profile === 'object') {
    profilePoints.push(...normalizeAutoResearchCurvePoints((row.test_profile as Record<string, unknown>).actual_vs_predicted));
  }
  if (profilePoints.length === 0) {
    profilePoints.push(...normalizeAutoResearchCurvePoints(row.actual_vs_predicted));
  }
  if (profilePoints.length === 0) return null;
  return {
    iteration,
    created_at: row.created_at != null ? String(row.created_at) : undefined,
    points: profilePoints,
    source,
  };
}

function collectAutoResearchCurveRows(
  status: Record<string, unknown> | null | undefined,
  trials: Record<string, unknown>[] = [],
): AutoResearchCurveRow[] {
  const byIteration = new Map<number, AutoResearchCurveRow>();
  const add = (row: AutoResearchCurveRow | null) => {
    if (!row) return;
    const existing = byIteration.get(row.iteration);
    if (!existing || row.points.length > existing.points.length) {
      byIteration.set(row.iteration, row);
    }
  };

  const statusPlotRows = Array.isArray(status?.iteration_plot_data) ? status?.iteration_plot_data : [];
  statusPlotRows.forEach((row, idx) => add(normalizeAutoResearchCurveRow(row, idx + 1, 'iteration_plot_data')));

  const datasetProfiles = Array.isArray(status?.dataset_profiles) ? status?.dataset_profiles : [];
  datasetProfiles.forEach((row, idx) => add(normalizeAutoResearchProfileCurve(row, idx + 1, 'dataset_profiles')));
  add(normalizeAutoResearchProfileCurve(status?.dataset_profile, undefined, 'dataset_profile'));

  const iterations = Array.isArray(status?.iterations) ? status?.iterations : [];
  [...iterations, ...trials].forEach((item, idx) => {
    if (!item || typeof item !== 'object') return;
    const row = item as Record<string, unknown>;
    const iteration = row.iteration ?? row.iteration_no ?? idx + 1;
    add(normalizeAutoResearchCurveRow(row.iteration_plot_data, iteration, 'trial_iteration_plot_data'));
    add(normalizeAutoResearchCurveRow(row.plot_data ?? row.curve_profile, iteration, 'trial_plot_data'));
    add(normalizeAutoResearchProfileCurve(row.dataset_profile, iteration, 'trial_dataset_profile'));
    add(normalizeAutoResearchProfileCurve(row, iteration, 'trial_profile'));
  });

  return Array.from(byIteration.values()).sort((a, b) => a.iteration - b.iteration);
}

function renderAutoResearchCurveSection(
  status: Record<string, unknown> | null | undefined,
  trials: Record<string, unknown>[],
  selectedIteration: number | null,
  onSelectedIterationChange: (value: number) => void,
) {
  const plotRows = collectAutoResearchCurveRows(status, trials);
  const plotOptions = plotRows
    .map((row, idx) => {
      const iteration = Number(row.iteration ?? idx + 1);
      return Number.isFinite(iteration)
        ? { label: `第 ${iteration} 轮`, value: iteration }
        : null;
    })
    .filter(Boolean) as { label: string; value: number }[];
  const selectedExists = selectedIteration != null
    && plotRows.some((row) => Number(row.iteration) === selectedIteration);
  const activePlot = selectedExists
    ? plotRows.find((row) => Number(row.iteration) === selectedIteration)
    : (plotRows.length > 0 ? plotRows[plotRows.length - 1] : null);
  const activeIteration = Number(activePlot?.iteration ?? 0);
  const selectedDatasetProfile = (((status as Record<string, unknown> | undefined)?.dataset_profiles as unknown[] | undefined || []) as Record<string, unknown>[])
    .find((row) => Number(row.iteration) === activeIteration);
  const activeValidationProfile = (selectedDatasetProfile?.validation_profile as Record<string, unknown> | undefined)
    || ((status?.dataset_profile as Record<string, unknown> | undefined)?.validation_profile as Record<string, unknown> | undefined)
    || {};
  const rawPoints = activePlot?.points || [];
  const step = Math.max(1, Math.ceil(rawPoints.length / 480));
  const points = rawPoints.filter((_, idx) => idx % step === 0);
  const xLabels = points.map((p) => {
    const raw = String(p.timestamp || '');
    return raw.length > 16 ? raw.slice(5, 16) : raw;
  });
  const actual = points.map((p) => Number(p.actual));
  const predicted = points.map((p) => Number(p.predicted));
  const ape = points.map((p) => {
    const a = Number(p.actual);
    const y = Number(p.predicted);
    if (!Number.isFinite(a) || !Number.isFinite(y) || Math.abs(a) <= 1e-8) return null;
    return Number((Math.abs((a - y) / a) * 100).toFixed(4));
  });
  const peakScatter = points
    .map((p, idx) => p.is_peak ? [xLabels[idx], Number(p.actual)] : null)
    .filter(Boolean);
  const valleyScatter = points
    .map((p, idx) => p.is_valley ? [xLabels[idx], Number(p.actual)] : null)
    .filter(Boolean);
  const cvLosses = ((activeValidationProfile.cv_fold_losses as unknown[] | undefined) || []) as Record<string, unknown>[];
  const foldLabels = cvLosses.map((f) => `F${String(f.fold_id ?? '-')}`);
  const trainLoss = cvLosses.map((f) => Number(f.train_loss));
  const valLoss = cvLosses.map((f) => Number(f.val_loss));
  const hasCurve = points.length > 0;
  const hasCv = cvLosses.length > 0;
  if (!hasCurve && !hasCv) return null;
  const curveOption = {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['实际负荷', '预测负荷', '峰点', '谷点'] },
    grid: { left: 42, right: 18, top: 42, bottom: 34 },
    xAxis: { type: 'category', data: xLabels, boundaryGap: false },
    yAxis: { type: 'value', scale: true },
    series: [
      { name: '实际负荷', type: 'line', data: actual, smooth: true, showSymbol: false, lineStyle: { width: 2 } },
      { name: '预测负荷', type: 'line', data: predicted, smooth: true, showSymbol: false, lineStyle: { width: 2 } },
      { name: '峰点', type: 'scatter', data: peakScatter, symbolSize: 7 },
      { name: '谷点', type: 'scatter', data: valleyScatter, symbolSize: 7 },
    ],
  };
  const errorOption = {
    tooltip: { trigger: 'axis' },
    grid: { left: 42, right: 18, top: 28, bottom: 34 },
    xAxis: { type: 'category', data: xLabels, boundaryGap: false },
    yAxis: { type: 'value', name: 'APE %', min: 0 },
    series: [
      {
        name: '绝对百分误差',
        type: 'line',
        data: ape,
        smooth: true,
        showSymbol: false,
        areaStyle: { opacity: 0.12 },
        markLine: {
          symbol: 'none',
          lineStyle: { type: 'dashed' },
          data: [{ yAxis: 10, name: '10%' }],
        },
      },
    ],
  };
  const cvOption = {
    tooltip: { trigger: 'axis' },
    legend: { top: 0, data: ['训练损失', '验证损失'] },
    grid: { left: 42, right: 18, top: 42, bottom: 34 },
    xAxis: { type: 'category', data: foldLabels },
    yAxis: { type: 'value', scale: true },
    series: [
      { name: '训练损失', type: 'bar', data: trainLoss, barMaxWidth: 28 },
      { name: '验证损失', type: 'line', data: valLoss, smooth: true, symbolSize: 7 },
    ],
  };
  return (
    <div style={{ marginTop: 12 }}>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 6 }} wrap>
        <Text strong>三集画像曲线</Text>
        {plotOptions.length > 0 && (
          <Select
            size="small"
            style={{ width: 140 }}
            value={activeIteration || undefined}
            options={plotOptions.slice().reverse()}
            onChange={(value) => onSelectedIterationChange(Number(value))}
          />
        )}
      </Space>
      <div style={{ marginTop: 6, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 10 }}>
        {hasCurve && (
          <Card size="small" title={`测试集曲线画像（第 ${String(activeIteration || '-')} 轮）`}>
            <ReactECharts option={curveOption} style={{ height: 260 }} />
          </Card>
        )}
        {hasCurve && (
          <Card size="small" title="测试集误差画像">
            <ReactECharts option={errorOption} style={{ height: 260 }} />
          </Card>
        )}
        {hasCv && (
          <Card size="small" title="验证集 CV 画像">
            <ReactECharts option={cvOption} style={{ height: 260 }} />
          </Card>
        )}
      </div>
      <Text type="secondary" style={{ fontSize: 12 }}>
        可切换查看已完成轮次；长序列会自动抽样，避免页面卡顿。
      </Text>
    </div>
  );
}

function renderAutoResearchTrainingProgress(
  source: Record<string, unknown> | null | undefined,
  options: { width?: number | string; size?: 'small' | 'default'; showText?: boolean } = {},
) {
  const item = getAutoResearchTrainingProgress(source);
  const fallbackRunning = !item && isAutoResearchRunningStatus(source?.status);
  if (!item && !fallbackRunning) return null;
  const current = item?.current ?? 0;
  const total = item?.total ?? 1;
  const percent = Math.min(100, Math.max(0, Math.round((current / total) * 100)));
  const normalizedStatus = String(source?.status || '').toLowerCase();
  const progressStatus =
    normalizedStatus === 'failed' || normalizedStatus === 'error'
      ? 'exception'
      : normalizedStatus === 'success' || normalizedStatus === 'completed'
        ? 'success'
        : 'active';
  return (
    <div style={{ width: options.width ?? 180, minWidth: 160 }}>
      <Progress
        percent={percent}
        size={options.size ?? 'small'}
        status={progressStatus}
        format={() => `${current}/${total}`}
      />
      {options.showText !== false && (
        <Text type="secondary" style={{ fontSize: 11 }}>
          {item
            ? `${item.label}：${current}/${total}${item.detail ? ` · ${item.detail}` : ''}`
            : '训练进度：等待后端训练进度...'}
        </Text>
      )}
    </div>
  );
}

function renderAutoResearchIterationProgress(
  source: Record<string, unknown> | null | undefined,
  options: { width?: number | string; size?: 'small' | 'default'; showText?: boolean } = {},
) {
  const p = (source?.progress as Record<string, unknown> | undefined) || {};
  const current = Math.max(0, Number(p.iteration ?? 0) || 0);
  const total = Math.max(0, Number(p.total_iterations ?? 0) || 0);
  if (total <= 0) return null;
  const percent = Math.min(100, Math.max(0, Math.round((current / total) * 100)));
  const normalizedStatus = String(source?.status || '').toLowerCase();
  const progressStatus =
    normalizedStatus === 'failed' || normalizedStatus === 'error'
      ? 'exception'
      : normalizedStatus === 'success' || normalizedStatus === 'completed'
        ? 'success'
        : 'active';
  return (
    <div style={{ width: options.width ?? 180, minWidth: 160 }}>
      <Progress
        percent={percent}
        size={options.size ?? 'small'}
        status={progressStatus}
        format={() => `${current}/${total}`}
      />
      {options.showText !== false && (
        <Text type="secondary" style={{ fontSize: 11 }}>
          轮次进度：{current}/{total}
        </Text>
      )}
    </div>
  );
}

// ─── helpers ────────────────────────────────────────────────────────────────

function toMonthWindows(n: number) {
  const windows = [];
  for (let i = n - 1; i >= 0; i--) {
    const start = dayjs().subtract(i + 1, 'month').startOf('month').format('YYYY-MM-DD');
    const end = dayjs().subtract(i + 1, 'month').endOf('month').format('YYYY-MM-DD');
    windows.push({ start_date: start, end_date: end });
  }
  return windows;
}

function windowsToText(windows: { start_date: string; end_date: string }[]) {
  return windows.map(w => `${w.start_date}~${w.end_date}`).join('\n');
}

function parseNumberList(raw: unknown): number[] {
  const txt = String(raw ?? '').trim();
  if (!txt) return [];
  return txt
    .split(',')
    .map(x => Number(x.trim()))
    .filter(v => Number.isFinite(v));
}

function parseStringList(raw: unknown, sep = ','): string[] {
  const txt = String(raw ?? '').trim();
  if (!txt) return [];
  return txt
    .split(sep)
    .map(x => x.trim())
    .filter(Boolean);
}

/** 不参与「可选预报模型」多选的 functionId（集成/编排类） */
const PREFERRED_MODEL_OPERATOR_EXCLUDE_IDS = new Set(['ensemble_forecast', 'multi_step_forecast']);

interface BaselineChallengerStructureRow {
  key: string;
  node_id: string;
  function_id: string;
  label: string;
  baseline_enabled: boolean;
  challenger_enabled: boolean;
}

/** Baseline：模板 JSON 里 config.enabled（默认 true）；Challenger：叠加后端 effective_structure_patch.node_switches */
function buildBaselineVsChallengerStructureRows(
  wf: EnhancedWorkflow,
  effectiveStructurePatch: Record<string, unknown> | null | undefined,
): BaselineChallengerStructureRow[] {
  const switches = (effectiveStructurePatch?.node_switches as Array<{ node_id?: string; enabled?: boolean }> | undefined) ?? [];
  const override = new Map<string, boolean>();
  switches.forEach((s) => {
    const nid = String(s.node_id || '').trim();
    if (nid && typeof s.enabled === 'boolean') override.set(nid, s.enabled);
  });
  const rows: BaselineChallengerStructureRow[] = [];
  (wf.nodes || []).forEach((n) => {
    const fid = String(n.data?.config?.functionId || '').trim();
    if (!fid) return;
    const baselineEnabled = n.data?.config?.enabled !== false;
    const challengerEnabled = override.has(n.id) ? Boolean(override.get(n.id)) : baselineEnabled;
    rows.push({
      key: n.id,
      node_id: n.id,
      function_id: fid,
      label: String(n.data?.label || ''),
      baseline_enabled: baselineEnabled,
      challenger_enabled: challengerEnabled,
    });
  });
  return rows;
}

/** 并联「叶子」预报模型（与关注模型多选对齐，不含 ensemble/multi_step） */
const PARALLEL_FORECAST_MODEL_IDS: string[] = [
  'xgboost_forecast',
  'lightgbm_forecast',
  'catboost_forecast',
  'ridge_forecast',
];

const PARALLEL_FORECAST_LABELS: Record<string, string> = {
  xgboost_forecast: 'XGBoost',
  lightgbm_forecast: 'LightGBM',
  catboost_forecast: 'CatBoost',
  ridge_forecast: 'Ridge',
};

function summarizeParallelForecastBranches(rows: BaselineChallengerStructureRow[]): {
  baselineLabels: string[];
  challengerLabels: string[];
} {
  const pick = (key: 'baseline_enabled' | 'challenger_enabled') =>
    PARALLEL_FORECAST_MODEL_IDS.filter((fid) => {
      const r = rows.find((x) => x.function_id === fid);
      return r && r[key];
    }).map((fid) => PARALLEL_FORECAST_LABELS[fid] || fid);
  return {
    baselineLabels: pick('baseline_enabled'),
    challengerLabels: pick('challenger_enabled'),
  };
}

/** 表格主列展示名（注册 id 过长或与业务语义不符时用友好名） */
function formatFunctionIdForUi(fid: string): { title: string; registryHint?: string } {
  if (fid === 'auto_tune_xgboost') {
    return { title: '贝叶斯超参优化', registryHint: 'auto_tune_xgboost' };
  }
  return { title: fid };
}

/** FastAPI detail 可能是 string 或对象（含 workflow_preflight_failed） */
function formatEnhancedApiError(err: unknown): string {
  const ax = err as { response?: { data?: { detail?: unknown } }; message?: string };
  const d = ax.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object') {
    const o = d as Record<string, unknown>;
    if (typeof o.message === 'string') return o.message;
    try {
      return JSON.stringify(o);
    } catch {
      return ax.message || '请求失败';
    }
  }
  return ax.message || String(err);
}

function compactJsonValue(value: unknown, maxLength = 90): string {
  if (value == null) return '-';
  if (typeof value === 'string') return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
  try {
    const text = JSON.stringify(value);
    return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
  } catch {
    return String(value);
  }
}

function patchItemCount(value: unknown): number {
  if (!value) return 0;
  if (Array.isArray(value)) return value.length;
  if (typeof value === 'object') return Object.keys(value as Record<string, unknown>).length;
  return 1;
}

function autoResearchGroupStatusColor(status: unknown): string {
  const s = String(status || '').toLowerCase();
  if (s === 'success') return 'green';
  if (s === 'failed' || s === 'error') return 'red';
  if (s === 'running') return 'blue';
  if (s === 'pending') return 'default';
  if (s === 'pruned') return 'orange';
  if (s === 'cancelled') return 'default';
  return 'default';
}

function granularityToDailyHorizon(v: unknown): number | null {
  const minutes = Number(v);
  if (!Number.isFinite(minutes) || minutes <= 0) return null;
  const points = 1440 / minutes;
  if (!Number.isFinite(points) || points <= 0) return null;
  return Math.round(points);
}

function buildAutoSearchSpace(profile: string, advanced?: Record<string, unknown>) {
  let base: Record<string, unknown>;
  if (profile === 'weekday_weekend') {
    base = {
      train_days: [21, 28, 35, 42, 56],
      backtest_train_days: [21, 28, 35, 42, 56],
      auto_tune_n_trials: [3, 5, 8, 12],
      daily_horizon: [96],
      backtest_apply_window_filter: [true],
      backtest_mask_target_values: [true],
    };
  } else if (profile === 'peak_valley') {
    base = {
      train_days: [14, 21, 30, 45, 60],
      backtest_train_days: [14, 21, 30, 45, 60],
      auto_tune_n_trials: [5, 8, 12, 16],
      daily_horizon: [96, 144],
      backtest_apply_window_filter: [true],
      backtest_mask_target_values: [true],
    };
  } else {
    base = {
      train_days: [30, 45, 60, 75],
      backtest_train_days: [30, 45, 60, 75],
      auto_tune_n_trials: [3, 5, 8],
      daily_horizon: [96],
      backtest_apply_window_filter: [true],
      backtest_mask_target_values: [true],
    };
  }
  const adv = advanced || {};
  const map: Array<[string, string]> = [
    ['xgb_eta_low', 'adv_xgb_eta_low_list'],
    ['xgb_eta_high', 'adv_xgb_eta_high_list'],
    ['xgb_max_depth_low', 'adv_xgb_depth_low_list'],
    ['xgb_max_depth_high', 'adv_xgb_depth_high_list'],
    ['xgb_subsample_low', 'adv_xgb_subsample_low_list'],
    ['xgb_subsample_high', 'adv_xgb_subsample_high_list'],
    ['xgb_lambda_low', 'adv_xgb_lambda_low_list'],
    ['xgb_lambda_high', 'adv_xgb_lambda_high_list'],
    ['xgb_min_child_weight_low', 'adv_xgb_min_child_low_list'],
    ['xgb_min_child_weight_high', 'adv_xgb_min_child_high_list'],
  ];
  map.forEach(([targetKey, fieldKey]) => {
    const arr = parseNumberList(adv[fieldKey]);
    if (arr.length > 0) base[targetKey] = arr;
  });
  const modelModeCandidates = parseStringList(adv.adv_local_parity_mode_candidates).map(s => s.toLowerCase())
    .filter(s => s === 'true' || s === 'false')
    .map(s => s === 'true');
  if (modelModeCandidates.length > 0) base.local_parity_mode = modelModeCandidates;
  const modelComboCandidates = parseStringList(adv.adv_model_combo_candidates, '|');
  if (modelComboCandidates.length > 0) base.local_parity_models = modelComboCandidates;
  return base;
}

function renderTrendPath(values: number[], width: number, height: number) {
  if (values.length < 2) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / span) * height;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

function buildTrendPoints(values: number[], width: number, height: number) {
  if (values.length === 0) return [] as Array<{ x: number; y: number }>;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values.map((v, i) => {
    const x = values.length === 1 ? width / 2 : (i / (values.length - 1)) * width;
    const y = height - ((v - min) / span) * height;
    return { x, y };
  });
}

// ─── param comparison helpers ────────────────────────────────────────────────

const renderParamRow = (
  key: string,
  label: string,
  hint: string,
  baseVal: unknown,
  challVal: unknown,
) => {
  const bStr =
    baseVal === null || baseVal === undefined
      ? '未设置'
      : Array.isArray(baseVal)
      ? JSON.stringify(baseVal)
      : String(baseVal);
  const cStr =
    challVal === null || challVal === undefined
      ? '未设置'
      : Array.isArray(challVal)
      ? JSON.stringify(challVal)
      : String(challVal);
  const isDiff = bStr !== cStr;
  return (
    <tr key={key}>
      <td style={{ padding: '4px 8px', width: 160 }}>
        <Tooltip title={hint || key}>
          <span style={{ cursor: 'help', fontSize: 13 }}>{label}</span>
        </Tooltip>
      </td>
      <td style={{ padding: '4px 8px' }}>
        <Tag color="geekblue">{bStr}</Tag>
      </td>
      <td style={{ padding: '4px 8px' }}>
        <Tag color={isDiff ? 'orange' : 'default'}>{cStr}</Tag>
        {isDiff && (
          <Tag color="orange" style={{ marginLeft: 4, fontSize: 11 }}>
            差异
          </Tag>
        )}
      </td>
    </tr>
  );
};

// ─── main component ──────────────────────────────────────────────────────────

const WorkflowBaselineComparePage: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();

  // workflow list
  const [workflows, setWorkflows] = useState<EnhancedWorkflowSummary[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);

  // form
  const [form] = Form.useForm();
  const [configDrawerOpen, setConfigDrawerOpen] = useState(false);
  const [showAdvancedDetails, setShowAdvancedDetails] = useState(false);
  const advancedDetailsAnchorRef = useRef<HTMLDivElement | null>(null);

  // compare job state
  const [comparing, setComparing] = useState(false);
  const [comparisonId, setComparisonId] = useState<string | null>(null);
  const [compareStatus, setCompareStatus] = useState<Record<string, unknown> | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [autoResearching, setAutoResearching] = useState(false);
  const [autoResearchRunId, setAutoResearchRunId] = useState<string | null>(null);
  const [autoResearchStatus, setAutoResearchStatus] = useState<Record<string, unknown> | null>(null);
  const [autoResearchTrials, setAutoResearchTrials] = useState<Record<string, unknown>[]>([]);
  const [selectedAutoResearchIteration, setSelectedAutoResearchIteration] = useState<number | null>(null);
  const [latestAutoRun, setLatestAutoRun] = useState<Record<string, unknown> | null>(null);
  const [latestAutoRuns, setLatestAutoRuns] = useState<Record<string, unknown>[]>([]);
  const [latestAutoRunLoading, setLatestAutoRunLoading] = useState(false);
  const [selectedProfileIteration, setSelectedProfileIteration] = useState<number | null>(null);
  const autoPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [proposalLoading, setProposalLoading] = useState(false);
  const [activeProposal, setActiveProposal] = useState<Record<string, unknown> | null>(null);
  const [proposalList, setProposalList] = useState<Record<string, unknown>[]>([]);
  const [recommendedProposalId, setRecommendedProposalId] = useState<string | null>(null);
  const [glmMeta, setGlmMeta] = useState<Record<string, unknown> | null>(null);
  const [proposalModalOpen, setProposalModalOpen] = useState(false);
  const [modelOperatorSelectOptions, setModelOperatorSelectOptions] = useState<{ value: string; label: string }[]>([]);
  const [structureProfileSelectOptions, setStructureProfileSelectOptions] = useState<{ value: string; label: string }[]>([]);
  const [featureRecipeSelectOptions, setFeatureRecipeSelectOptions] = useState<{ value: string; label: string }[]>([]);
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [precheckLoading, setPrecheckLoading] = useState(false);
  const [profileSlotDetail, setProfileSlotDetail] = useState<Record<string, unknown> | null>(null);
  const [profileSlotLoading, setProfileSlotLoading] = useState(false);
  const activeProposalId = String(activeProposal?.proposal_id || '');
  const [selfcheckLoading, setSelfcheckLoading] = useState(false);
  const [selfcheckOpen, setSelfcheckOpen] = useState(false);
  const [selfcheckResult, setSelfcheckResult] = useState<Record<string, unknown> | null>(null);
  const [structureCompareOpen, setStructureCompareOpen] = useState(false);
  const [structureCompareLoading, setStructureCompareLoading] = useState(false);
  const [structureCompareRows, setStructureCompareRows] = useState<BaselineChallengerStructureRow[]>([]);
  const [runtimePatchOpen, setRuntimePatchOpen] = useState(false);
  const [selectedRuntimePatchIndex, setSelectedRuntimePatchIndex] = useState<number | null>(null);

  const structureCompareForecastSummary = useMemo(
    () => summarizeParallelForecastBranches(structureCompareRows),
    [structureCompareRows],
  );

  const structureCompareEnsemble = useMemo(() => {
    const r = structureCompareRows.find((x) => x.function_id === 'ensemble_forecast');
    if (!r) return null;
    return { baseline: r.baseline_enabled, challenger: r.challenger_enabled };
  }, [structureCompareRows]);

  /** 关注模型下拉：去掉集成等非叶子预报选项 */
  const preferredModelOperatorOptions = useMemo(
    () => modelOperatorSelectOptions.filter(o => !PREFERRED_MODEL_OPERATOR_EXCLUDE_IDS.has(o.value)),
    [modelOperatorSelectOptions],
  );

  /** 多候选来自 API；若只有一条或列表异常，仍用当前 active 补一行，保证「查看」始终可用 */
  const proposalTableRows = useMemo(() => {
    if (proposalList.length > 0) return proposalList;
    if (activeProposal) return [activeProposal];
    return [];
  }, [proposalList, activeProposal]);

  const getTopRetrievalScore = useCallback((proposal: Record<string, unknown>) => {
    const refs = (proposal.memory_references as unknown[]) || [];
    let best: number | null = null;
    refs.forEach((it) => {
      if (!it || typeof it !== 'object') return;
      const v = Number((it as Record<string, unknown>).retrieval_score);
      if (!Number.isFinite(v)) return;
      if (best === null || v > best) best = v;
    });
    return best;
  }, []);

  const autoRunInsights = useMemo(() => {
    const st = autoResearchStatus || {};
    const status = String(st.status || '');
    const logs = ((st.logs as unknown[]) || []) as Record<string, unknown>[];
    const latestAuto = (st.latest_auto_proposal as Record<string, unknown> | undefined) || {};
    const latestLog = logs.length > 0 ? logs[logs.length - 1] : null;
    const latestMsg = String(latestLog?.message || '');
    const live = (st.current_iteration_live as Record<string, unknown> | undefined) || {};

    let phase = 'idle';
    let phaseText = '空闲';
    if (status === 'waiting_review') {
      phase = 'waiting_review';
      phaseText = '等待审核/继续';
    } else if (status === 'running' && Object.keys(live).length > 0) {
      phase = 'running_backtest';
      phaseText = '正在回测与训练';
    } else if (status === 'running' && latestMsg.includes('自动生成建议')) {
      phase = 'generating_or_applying';
      phaseText = '正在生成/应用建议';
    } else if (status === 'running') {
      phase = 'running_transition';
      phaseText = '轮次切换中';
    } else if (status === 'success') {
      phase = 'finished';
      phaseText = '已完成';
    } else if (status === 'failed') {
      phase = 'failed';
      phaseText = '运行失败';
    }

    const iterations = ((st.iterations as unknown[]) || []) as Record<string, unknown>[];
    let noTestDataCount = 0;
    let insufficientTrainDataCount = 0;
    let failedCount = 0;
    iterations.forEach((it) => {
      const err = String(it.error || '').toLowerCase();
      if (String(it.status || '') === 'failed') failedCount += 1;
      if (err.includes('无测试数据') || err.includes('no test data')) noTestDataCount += 1;
      if (err.includes('无训练数据') || err.includes('insufficient_train_data') || err.includes('no train data')) {
        insufficientTrainDataCount += 1;
      }
    });

    return {
      phase,
      phaseText,
      latestMsg,
      recommendationGenerated: Boolean(latestAuto.generated_at),
      recommendationApplied: Boolean(st.latest_applied_proposal_id),
      noTestDataCount,
      insufficientTrainDataCount,
      failedCount,
    };
  }, [autoResearchStatus]);

  useEffect(() => {
    const values = new Set<number>();
    autoResearchTrials.forEach((trial) => {
      const n = Number(trial.iteration_no ?? trial.iteration);
      if (Number.isFinite(n) && n > 0) values.add(n);
    });
    const latestGroups = ((autoResearchStatus?.latest_batch_groups as unknown[]) || []) as Record<string, unknown>[];
    latestGroups.forEach((group) => {
      const n = Number(group.iteration_no ?? group.iteration);
      if (Number.isFinite(n) && n > 0) values.add(n);
    });
    const sorted = Array.from(values).sort((a, b) => a - b);
    if (sorted.length === 0) return;
    if (selectedAutoResearchIteration == null || !values.has(selectedAutoResearchIteration)) {
      setSelectedAutoResearchIteration(sorted[sorted.length - 1]);
    }
  }, [autoResearchStatus, autoResearchTrials, selectedAutoResearchIteration]);

  // candidate pool
  const [pool, setPool] = useState<unknown[]>([]);
  const [loadingPool, setLoadingPool] = useState(false);
  const [verificationQueue, setVerificationQueue] = useState<Record<string, unknown>[]>([]);
  const [loadingVerificationQueue, setLoadingVerificationQueue] = useState(false);
  const [candidateRunRows, setCandidateRunRows] = useState<Record<string, unknown>[]>([]);
  const candidateRunProgressById = useMemo(() => {
    const map = new Map<string, number>();
    candidateRunRows.forEach((row) => {
      const runId = String(row.run_id || '');
      const progress = (row.progress as Record<string, unknown> | undefined) || {};
      const completed = Number(progress.iteration ?? row.current_iteration ?? 0);
      if (runId && Number.isFinite(completed)) {
        map.set(runId, completed);
      }
    });
    return map;
  }, [candidateRunRows]);
  const matureCandidatePool = useMemo(() => {
    return (pool as Record<string, unknown>[])
      .filter((item) => {
        const runId = String(item.source_run_id || '');
        const completed = Number(
          item.source_run_completed_iterations
          ?? candidateRunProgressById.get(runId)
          ?? 0,
        );
        return Boolean(runId) && Number.isFinite(completed) && completed >= 10;
      })
      .map((item) => {
        const runId = String(item.source_run_id || '');
        if (item.source_run_completed_iterations != null) return item;
        const completed = candidateRunProgressById.get(runId);
        return completed == null ? item : { ...item, source_run_completed_iterations: completed };
      })
      .sort((a, b) => {
        const sa = (a.summary as Record<string, unknown> | undefined) || {};
        const sb = (b.summary as Record<string, unknown> | undefined) || {};
        const av = Number(sa.mape_improvement ?? sa.score_advantage ?? -Infinity);
        const bv = Number(sb.mape_improvement ?? sb.score_advantage ?? -Infinity);
        return bv - av;
      });
  }, [candidateRunProgressById, pool]);

  // candidate pool detail drawer (任务 4.1 / 4.2)
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false);
  const [detailCandidate, setDetailCandidate] = useState<Record<string, unknown> | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // 任务 25.3：搜索空间注册表选择
  const [registryOptions, setRegistryOptions] = useState<{ value: string; label: string }[]>([]);
  const [selectedRegistryId, setSelectedRegistryId] = useState<string>('');  // 空字符串 = 自动匹配

  // production ref
  const [productionRef, setProductionRef] = useState<Record<string, unknown> | null>(null);

  // promote modal
  const [promoteModalOpen, setPromoteModalOpen] = useState(false);
  const [promotingCandidate, setPromotingCandidate] = useState<Record<string, unknown> | null>(null);
  const [promoteForm] = Form.useForm();
  const [promoting, setPromoting] = useState(false);
  const [verificationModalOpen, setVerificationModalOpen] = useState(false);
  const [verificationCandidate, setVerificationCandidate] = useState<Record<string, unknown> | null>(null);
  const [verificationForm] = Form.useForm();
  const [enqueueingVerification, setEnqueueingVerification] = useState(false);
  const [startVerificationModalOpen, setStartVerificationModalOpen] = useState(false);
  const [startVerificationItem, setStartVerificationItem] = useState<Record<string, unknown> | null>(null);
  const [startingVerification, setStartingVerification] = useState(false);
  const [startVerificationForm] = Form.useForm();
  const verificationByCandidateId = useMemo(() => {
    const map = new Map<string, Record<string, unknown>>();
    verificationQueue.forEach((item) => {
      const candidateId = String(item.candidate_id || '');
      if (candidateId && !map.has(candidateId)) map.set(candidateId, item);
    });
    return map;
  }, [verificationQueue]);

  // param comparison
  const [baselineParams, setBaselineParams] = useState<WorkflowParamsSummary | null>(null);
  const [challengerParams, setChallengerParams] = useState<WorkflowParamsSummary | null>(null);
  const [loadingParams, setLoadingParams] = useState(false);
  // challenger 参数覆盖：key -> 用户输入的新值（空字符串=不覆盖）
  const [challOverride, setChallOverride] = useState<Record<string, string>>({});
  // baseline 参数覆盖
  const [baselineOverride, setBaselineOverride] = useState<Record<string, string>>({});

  // 记录上次加载参数时的 baseline/challenger ID，只有 ID 变化才重置覆盖值
  const prevParamIdsRef = useRef<{ baseline?: string; challenger?: string }>({});

  // watch form values for param comparison
  const watchedBaselineId = Form.useWatch('baseline_workflow_id', form) as string | undefined;
  const watchedChallengerIds = Form.useWatch('challenger_workflow_ids', form) as string[] | undefined;
  const watchedChallengerId = watchedChallengerIds?.[0];
  const watchedStructureProfileId = Form.useWatch('structure_profile_id', form) as string | undefined;

  // ── init ──────────────────────────────────────────────────────────────────

  // 表单配置持久化 key
  const FORM_STORAGE_KEY = 'baseline_compare_form_values';
  const AUTO_RESEARCH_RUN_STORAGE_KEY = 'auto_research_run_id';

  const isAutoResearchTerminalStatus = (status: unknown) => {
    const s = String(status || '').toLowerCase();
    return s === 'success' || s === 'failed' || s === 'cancelled' || s === 'interrupted';
  };

  const getAutoResearchStatusColor = (status: unknown) => {
    const s = String(status || '').toLowerCase();
    if (s === 'success') return 'green';
    if (s === 'failed') return 'red';
    if (s === 'cancelled') return 'default';
    if (s === 'interrupted') return 'orange';
    if (s === 'running') return 'blue';
    if (s === 'pending') return 'processing';
    if (s === 'waiting_review') return 'purple';
    return 'default';
  };

  const getAutoResearchStatusText = (status: unknown) => {
    const s = String(status || '').toLowerCase();
    if (s === 'success') return '已完成';
    if (s === 'failed') return '失败';
    if (s === 'cancelled') return '已取消';
    if (s === 'interrupted') return '已中断';
    if (s === 'running') return '正在运行';
    if (s === 'pending') return '等待 worker';
    if (s === 'waiting_review') return '等待审核';
    if (s === 'cancelling') return '正在停止';
    return s || '未知';
  };

  const isAutoResearchActiveRow = (row: Record<string, unknown>) => {
    const status = String(row.status || '').toLowerCase();
    const jobStatus = String(row.job_status || '').toLowerCase();
    return (
      ['pending', 'running', 'waiting_review', 'cancelling'].includes(status)
      || ['pending', 'running'].includes(jobStatus)
    );
  };

  const isAutoResearchResumableRow = (row: Record<string, unknown>) => {
    const status = String(row.status || '').toLowerCase();
    return ['interrupted', 'failed', 'cancelled'].includes(status) && row.recoverable !== false;
  };

  const isAutoResearchValidRecentRow = (row: Record<string, unknown>) => {
    const runId = String(row.run_id || '');
    const progress = row.progress as Record<string, unknown> | undefined;
    return Boolean(runId) && (runId.startsWith('ares-') || Boolean(row.status) || Boolean(progress?.total_iterations));
  };

  const autoResearchRunSortTime = (row: Record<string, unknown>) =>
    String(row.job_updated_at || row.updated_at || row.created_at || '');

  const getAutoResearchCompletedIterations = (row: Record<string, unknown>) => {
    const progress = row.progress as Record<string, unknown> | undefined;
    const candidates = [
      row.source_run_completed_iterations,
      progress?.iteration,
      row.current_iteration,
    ];
    for (const item of candidates) {
      const n = Number(item);
      if (Number.isFinite(n) && n >= 0) return n;
    }
    return 0;
  };

  const choosePreferredAutoResearchRun = (rows: Record<string, unknown>[]) => {
    const validRows = rows.filter(isAutoResearchValidRecentRow);
    return (
      validRows.find(row => isAutoResearchActiveRow(row))
      || validRows.find(row => String(row.status || '').toLowerCase() === 'success')
      || validRows.find(row => String(row.status || '').toLowerCase() === 'interrupted')
      || validRows[0]
      || null
    );
  };

  const durableAutoRuns = useMemo(() => {
    let resumableCount = 0;
    return latestAutoRuns.filter((row) => {
      if (isAutoResearchActiveRow(row) || getAutoResearchCompletedIterations(row) >= 10) return true;
      if (isAutoResearchResumableRow(row) && resumableCount < 2) {
        resumableCount++;
        return true;
      }
      return false;
    });
  }, [latestAutoRuns]);

  const findLatestRecoverableAutoResearchRun = async () => {
    const res = await baselineCompareApi.listAutoResearchRuns(200);
    const rows = Array.isArray(res.runs) ? res.runs.filter(isAutoResearchValidRecentRow) : [];
    rows.sort((a, b) => autoResearchRunSortTime(b).localeCompare(autoResearchRunSortTime(a)));
    setLatestAutoRuns(rows);
    return choosePreferredAutoResearchRun(rows);
  };

  const detectLatestAutoResearchRun = async (showMessage = false) => {
    setLatestAutoRunLoading(true);
    try {
      const res = await baselineCompareApi.listAutoResearchRuns(200);
      const rows = Array.isArray(res.runs) ? res.runs.filter(isAutoResearchValidRecentRow) : [];
      rows.sort((a, b) => autoResearchRunSortTime(b).localeCompare(autoResearchRunSortTime(a)));
      const latest = choosePreferredAutoResearchRun(rows);
      setLatestAutoRuns(rows);
      setLatestAutoRun(latest);
      if (showMessage) {
        if (latest) {
          message.success(`已检测到最近 AutoResearch run：${String(latest.run_id || '-')}`);
        } else {
          message.info('没有检测到 AutoResearch run');
        }
      }
      return latest;
    } catch (err: unknown) {
      if (showMessage) {
        message.error(`检测最近 AutoResearch run 失败: ${(err as Error)?.message || '未知错误'}`);
      }
      setLatestAutoRun(null);
      setLatestAutoRuns([]);
      return null;
    } finally {
      setLatestAutoRunLoading(false);
    }
  };

  const openLatestAutoResearchRun = async (row: Record<string, unknown>) => {
    const runId = String(row.run_id || '');
    if (!runId) return;
    await recoverAutoResearchRun(runId);
  };

  const resumeLatestAutoResearchRun = async (row: Record<string, unknown>) => {
    const runId = String(row.run_id || '');
    if (!runId) return;
    try {
      const res = await baselineCompareApi.resumeAutoResearch(runId);
      message.success(`已从第 ${(res as Record<string, unknown>).resume_from_iteration} 轮继续训练`);
      setAutoResearchRunId(runId);
      persistAutoResearchRunId(runId);
      setAutoResearching(true);
      startAutoPolling(runId);
      await detectLatestAutoResearchRun(false);
    } catch (err: unknown) {
      message.error(`继续训练失败: ${formatEnhancedApiError(err)}`);
    }
  };

  const persistAutoResearchRunId = (runId: string) => {
    sessionStorage.setItem(AUTO_RESEARCH_RUN_STORAGE_KEY, runId);
    localStorage.setItem(AUTO_RESEARCH_RUN_STORAGE_KEY, runId);
  };

  const clearPersistedAutoResearchRunId = (runId?: string | null) => {
    const currentSession = sessionStorage.getItem(AUTO_RESEARCH_RUN_STORAGE_KEY);
    const currentLocal = localStorage.getItem(AUTO_RESEARCH_RUN_STORAGE_KEY);
    if (!runId || currentSession === runId) {
      sessionStorage.removeItem(AUTO_RESEARCH_RUN_STORAGE_KEY);
    }
    if (!runId || currentLocal === runId) {
      localStorage.removeItem(AUTO_RESEARCH_RUN_STORAGE_KEY);
    }
  };

  const loadAutoResearchTrials = async (runId: string) => {
    try {
      const res = await baselineCompareApi.listAutoResearchTrials(runId, 200);
      setAutoResearchTrials(Array.isArray(res.trials) ? res.trials : []);
    } catch (err) {
      console.warn('load autoresearch trials failed', err);
    }
  };

  const recoverAutoResearchRun = async (runId: string) => {
    setAutoResearchRunId(runId);
    persistAutoResearchRunId(runId);
    setAutoResearching(true);
    try {
      const status = await baselineCompareApi.getAutoResearchStatus(runId);
      setAutoResearchStatus(status);
      void loadAutoResearchTrials(runId);
      const s = String(status.status || '').toLowerCase();
      if (s === 'interrupted') {
        // interrupted 状态：保留面板显示恢复按钮，但不轮询
        setAutoResearching(false);
        return status;
      } else if (isAutoResearchTerminalStatus(status.status)) {
        setAutoResearching(false);
        clearPersistedAutoResearchRunId(runId);
        loadPool();
        return status;
      } else {
        startAutoPolling(runId);
        return status;
      }
    } catch (e: unknown) {
      const httpStatus = (e as { response?: { status?: number } })?.response?.status;
      setAutoResearching(false);
      if (httpStatus === 404) {
        clearPersistedAutoResearchRunId(runId);
        message.warning('自动实验任务不存在，已清除本地恢复记录');
      } else {
        message.warning('自动实验状态恢复失败，后端可能仍在运行；刷新或稍后重试');
      }
      return null;
    }
  };

  useEffect(() => {
    loadSummaries();
    loadPool();
    loadVerificationQueue();
    loadProductionRef();
    // 任务 25.3：加载可用注册表列表
    baselineCompareApi.listSearchRegistries().then(res => {
      const opts = [
        { value: '', label: '自动匹配（推荐）' },
        ...(res.registries || []).map(r => ({
          value: r.registry_id,
          label: `${r.registry_id}（${r.layers_count} 层）`,
        })),
      ];
      setRegistryOptions(opts);
    }).catch(() => {
      setRegistryOptions([{ value: '', label: '自动匹配（推荐）' }]);
    });

    // 恢复上次保存的表单配置
    try {
      const saved = localStorage.getItem(FORM_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (typeof parsed === 'object' && parsed !== null) {
          form.setFieldsValue(parsed);
        }
      }
    } catch { /* ignore */ }

    const baselineFromUrl = searchParams.get('baseline');
    const challengerFromUrl = searchParams.get('challenger');
    if (baselineFromUrl || challengerFromUrl) {
      form.setFieldsValue({
        baseline_workflow_id: baselineFromUrl || undefined,
        challenger_workflow_ids: challengerFromUrl ? [challengerFromUrl] : undefined,
      });
    }

    // 恢复上次未完成的比对任务
    const savedId = sessionStorage.getItem('baseline_compare_id');
    if (savedId) {
      setComparisonId(savedId);
      setComparing(true);
      // 先拉一次状态，如果已完成就直接展示结果，否则继续轮询
      baselineCompareApi.getCompareStatus(savedId).then(status => {
        setCompareStatus(status);
        const s = (status as Record<string, unknown>).status as string;
        if (s === 'success' || s === 'failed' || s === 'cancelled') {
          setComparing(false);
          sessionStorage.removeItem('baseline_compare_id');
          loadPool();
        } else {
          startPolling(savedId);
        }
      }).catch(() => {
        // 404 或其他错误，清除旧 ID
        setComparing(false);
        sessionStorage.removeItem('baseline_compare_id');
      });
    }

    const savedAutoRunId = sessionStorage.getItem(AUTO_RESEARCH_RUN_STORAGE_KEY)
      || localStorage.getItem(AUTO_RESEARCH_RUN_STORAGE_KEY);
    void (async () => {
      setDiscoveryLoading(true);
      try {
        const [opsRes, profRes, recipeRes] = await Promise.all([
          baselineCompareApi.listModelOperatorsAvailable(),
          baselineCompareApi.listStructureProfiles(),
          baselineCompareApi.listFeatureRecipes().catch((err: unknown) => {
            console.warn('[WorkflowBaselineCompare] feature recipes load failed', err);
            return { recipes: [] as { recipe_id?: string; title?: string }[] };
          }),
        ]);
        const ops = (opsRes.operators as { function_id?: string; name?: string }[] | undefined) || [];
        setModelOperatorSelectOptions(
          ops.map(o => ({
            value: String(o.function_id || ''),
            label: `${o.function_id || ''} — ${o.name || ''}`,
          })).filter(o => o.value),
        );
        const profiles = (profRes.profiles as { profile_id?: string; title?: string }[] | undefined) || [];
        const defId = typeof profRes.default_profile_id === 'string' ? profRes.default_profile_id : '';
        setStructureProfileSelectOptions(
          profiles.map(p => ({
            value: String(p.profile_id || ''),
            label: `${p.profile_id || ''}${p.title ? ` (${p.title})` : ''}`,
          })).filter(o => o.value),
        );
        const curPid = form.getFieldValue('structure_profile_id') as string | undefined;
        if (!curPid && defId) {
          form.setFieldsValue({ structure_profile_id: defId });
        }
        const recipes = (recipeRes.recipes as { recipe_id?: string; title?: string }[] | undefined) || [];
        setFeatureRecipeSelectOptions(
          recipes.map(r => ({
            value: String(r.recipe_id || ''),
            label: `${r.recipe_id || ''}${r.title ? ` — ${r.title}` : ''}`,
          })).filter(o => o.value),
        );
      } catch (e: unknown) {
        console.error('[WorkflowBaselineCompare] discovery load failed', e);
        const ax = e as { response?: { status?: number; data?: unknown }; message?: string };
        const st = ax.response?.status;
        message.open({
          type: 'warning',
          key: 'workflow-baseline-discovery-load',
          duration: 10,
          content: `加载可用模型算子或结构档案失败（HTTP ${st ?? '—'}）。请确认后端 http://localhost:8080 已启动且 Vite 代理生效；打开开发者工具 Network 查看 /api/workflows/enhanced/model-operators-available、structure-profiles 与 feature-recipes。控制台有更完整报错。仍可发起 AutoResearch（后端会用默认档案）。`,
        });
      } finally {
        setDiscoveryLoading(false);
      }
    })();

    void (async () => {
      try {
        const preferred = await detectLatestAutoResearchRun(false);
        const preferredRunId = String(preferred?.run_id || '');
        if (savedAutoRunId) {
          const targetRunId = preferredRunId || savedAutoRunId;
          const recovered = await recoverAutoResearchRun(targetRunId);
          const recoveredStatus = String(recovered?.status || '').toLowerCase();
          if (isAutoResearchRunningStatus(recoveredStatus) || recoveredStatus === 'waiting_review') {
            return;
          }
        }
        const active = preferred || await findLatestRecoverableAutoResearchRun();
        const runId = String(active?.run_id || '');
        if (runId) {
          await recoverAutoResearchRun(runId);
        }
      } catch {
        // 列表恢复只是兜底，失败不影响页面正常使用。
      }
      await detectLatestAutoResearchRun(false);
    })();

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      if (autoPollRef.current) clearInterval(autoPollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const pid = String(watchedStructureProfileId || '').trim();
    if (!pid) {
      setProfileSlotDetail(null);
      return;
    }
    let cancelled = false;
    setProfileSlotLoading(true);
    baselineCompareApi
      .getStructureProfileDetail(pid)
      .then(res => {
        if (!cancelled) setProfileSlotDetail(res as Record<string, unknown>);
      })
      .catch(() => {
        if (!cancelled) setProfileSlotDetail(null);
      })
      .finally(() => {
        if (!cancelled) setProfileSlotLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [watchedStructureProfileId]);

  // ── load summaries ────────────────────────────────────────────────────────

  const loadSummaries = useCallback(async () => {
    setLoadingWorkflows(true);
    try {
      const list = await enhancedWorkflowApi.listWorkflowSummaries();
      setWorkflows(list);
    } catch {
      message.error('加载模板列表失败');
    } finally {
      setLoadingWorkflows(false);
    }
  }, []);

  // ── load pool ─────────────────────────────────────────────────────────────

  const loadPool = useCallback(async () => {
    setLoadingPool(true);
    try {
      const [res, runsRes] = await Promise.all([
        baselineCompareApi.listCandidatePool(),
        baselineCompareApi.listAutoResearchRuns(200),
      ]);
      const candidates = (res.candidates ?? []) as Record<string, unknown>[];
      const sourceRunIds = Array.from(new Set(
        candidates
          .map(row => String(row.source_run_id || '').trim())
          .filter(Boolean),
      ));
      const trialRows = await Promise.all(
        sourceRunIds.map(async (runId) => {
          try {
            const trialsRes = await baselineCompareApi.listAutoResearchTrials(runId, 1000);
            const completed = new Set<number>();
            (trialsRes.trials || []).forEach((trial) => {
              const status = String(trial.status || '').toLowerCase();
              const n = Number(trial.iteration_no ?? trial.iteration);
              if (Number.isFinite(n) && n > 0 && ['success', 'failed', 'error', 'cancelled', 'interrupted'].includes(status)) {
                completed.add(n);
              }
            });
            return { run_id: runId, progress: { iteration: completed.size } };
          } catch {
            return { run_id: runId, progress: { iteration: 0 } };
          }
        }),
      );
      setPool(candidates);
      setCandidateRunRows([
        ...(Array.isArray(runsRes.runs) ? runsRes.runs : []),
        ...trialRows,
      ]);
    } catch {
      message.error('加载候选池失败');
    } finally {
      setLoadingPool(false);
    }
  }, []);

  const loadVerificationQueue = useCallback(async () => {
    setLoadingVerificationQueue(true);
    try {
      const res = await baselineCompareApi.listVerificationQueue();
      setVerificationQueue(Array.isArray(res.items) ? res.items : []);
    } catch {
      message.error('加载复验池失败');
    } finally {
      setLoadingVerificationQueue(false);
    }
  }, []);

  // ── load production ref ───────────────────────────────────────────────────

  const loadProductionRef = useCallback(async () => {
    try {
      const ref = await baselineCompareApi.getProductionWorkflowRef();
      setProductionRef(ref);
    } catch {
      // non-critical
    }
  }, []);

  // ── param comparison: watch baseline + challenger ─────────────────────────

  useEffect(() => {
    if (!watchedBaselineId || !watchedChallengerId) {
      setBaselineParams(null);
      setChallengerParams(null);
      return;
    }

    let cancelled = false;
    setLoadingParams(true);
    // 只有模板 ID 真正变化时才重置覆盖值，避免覆盖"填充示例参数"设置的值
    const prev = prevParamIdsRef.current;
    if (prev.baseline !== watchedBaselineId || prev.challenger !== watchedChallengerId) {
      // 只有模板 ID 真正变化时才重置，且两个 ID 不同时才重置（相同模板对比时保留用户设置的覆盖值）
      const bothSame = watchedBaselineId === watchedChallengerId;
      if (!bothSame) {
        setChallOverride({});
        setBaselineOverride({});
      }
      prevParamIdsRef.current = { baseline: watchedBaselineId, challenger: watchedChallengerId };
    }
    Promise.all([
      cloneWorkflowApi.getParamsSummary(watchedBaselineId),
      cloneWorkflowApi.getParamsSummary(watchedChallengerId),
    ])
      .then(([bp, cp]) => {
        if (!cancelled) {
          setBaselineParams(bp);
          setChallengerParams(cp);
        }
      })
      .catch(() => {
        if (!cancelled) message.warning('加载参数摘要失败');
      })
      .finally(() => {
        if (!cancelled) setLoadingParams(false);
      });

    return () => {
      cancelled = true;
    };
  }, [watchedBaselineId, watchedChallengerId]);

  // ── start compare ─────────────────────────────────────────────────────────

  const onStart = useCallback(async () => {
    let values: Record<string, unknown>;
    try {
      values = await form.validateFields();
    } catch {
      return;
    }

    const windowsRaw = (values.windows_text as string) || '';
    const windows = windowsRaw
      .split('\n')
      .map(l => l.trim())
      .filter(Boolean)
      .map(l => {
        const [s, e] = l.split('~');
        return { start_date: s?.trim(), end_date: e?.trim() };
      })
      .filter(w => w.start_date && w.end_date);

    if (windows.length === 0) {
      message.warning('请至少填写一个时间窗');
      return;
    }

    const body: Record<string, unknown> = {
      baseline_workflow_id: values.baseline_workflow_id,
      challenger_workflow_ids: values.challenger_workflow_ids,
      windows,
      score_margin: values.score_margin ?? 0,
      aggregate_method: values.aggregate_method ?? 'mean',
      add_to_candidate_pool: values.add_to_candidate_pool ?? true,
    };
    if (values.min_windows_challenger_better) {
      body.min_windows_challenger_better = values.min_windows_challenger_better;
    }

    // 评测量约：从结构化字段收集（两边共用的"尺子"）
    const contractObj: Record<string, unknown> = {
      backtest_mode: String(values.contract_backtest_mode || 'rolling_retrain'),
    };
    if (values.contract_train_days != null) contractObj.train_days = Number(values.contract_train_days);
    const dailyHorizonCompare =
      granularityToDailyHorizon(values.contract_time_granularity_min)
      ?? (values.contract_daily_horizon != null ? Number(values.contract_daily_horizon) : null);
    if (dailyHorizonCompare != null) contractObj.daily_horizon = dailyHorizonCompare;
    if (values.contract_apply_window_filter != null) contractObj.backtest_apply_window_filter = values.contract_apply_window_filter;
    if (values.contract_mask_target_values != null) contractObj.backtest_mask_target_values = values.contract_mask_target_values;
    if (values.contract_auto_tune_n_trials != null) contractObj.auto_tune_n_trials = Number(values.contract_auto_tune_n_trials);
    if (contractObj.auto_tune_n_trials == null) contractObj.auto_tune_n_trials = 5;
    if (Object.keys(contractObj).length > 0) body.evaluation_contract = contractObj;

    // baseline 专属参数覆盖
    const baselineOverrideClean: Record<string, unknown> = {};
    Object.entries(baselineOverride).forEach(([k, v]) => {
      if (v === '' || v === null || v === undefined) return;
      if (v === 'true') baselineOverrideClean[k] = true;
      else if (v === 'false') baselineOverrideClean[k] = false;
      else if (!isNaN(Number(v)) && String(v).trim() !== '') baselineOverrideClean[k] = Number(v);
      else baselineOverrideClean[k] = v;
    });
    if (Object.keys(baselineOverrideClean).length > 0) {
      body.baseline_config_override = baselineOverrideClean;
    }

    // challenger 专属参数覆盖（只影响 challenger，不影响 baseline）
    const challOverrideClean: Record<string, unknown> = {};
    Object.entries(challOverride).forEach(([k, v]) => {
      if (v === '' || v === null || v === undefined) return;
      if (v === 'true') challOverrideClean[k] = true;
      else if (v === 'false') challOverrideClean[k] = false;
      else if (!isNaN(Number(v)) && String(v).trim() !== '') challOverrideClean[k] = Number(v);
      else challOverrideClean[k] = v;
    });
    if (Object.keys(challOverrideClean).length > 0) {
      body.challenger_config_override = challOverrideClean;
    }

    setComparing(true);
    setCompareStatus(null);
    try {
      const res = await baselineCompareApi.startCompareAsync(body);
      setComparisonId(res.comparison_id);
      message.success(`比对任务已启动，ID: ${res.comparison_id}`);
      startPolling(res.comparison_id);
    } catch (e: unknown) {
      message.error((e as Error).message || '启动比对失败');
      setComparing(false);
    }
    // challOverride / baselineOverride 必须列入依赖，否则 useCallback 会长期捕获初始空对象，请求体不带覆盖（分差恒为 0）
  }, [form, challOverride, baselineOverride]);

  // ── cancel job ────────────────────────────────────────────────────────────

  const onCancelJob = useCallback(async () => {
    if (!comparisonId) return;
    try {
      await baselineCompareApi.cancelCompare(comparisonId);
      message.info('已发送取消请求');
      stopPolling();
      setComparing(false);
    } catch {
      message.error('取消失败');
    }
  }, [comparisonId]);

  // ── polling ───────────────────────────────────────────────────────────────

  const startPolling = (id: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    sessionStorage.setItem('baseline_compare_id', id);
    pollRef.current = setInterval(async () => {
      try {
        const status = await baselineCompareApi.getCompareStatus(id);
        setCompareStatus(status);
        const s = (status as Record<string, unknown>).status as string;
        if (s === 'success' || s === 'failed' || s === 'cancelled') {
          stopPolling();
          setComparing(false);
          sessionStorage.removeItem('baseline_compare_id');
          loadPool();
        }
      } catch (e: unknown) {
        const httpStatus = (e as { response?: { status?: number } })?.response?.status;
        if (httpStatus === 404) {
          stopPolling();
          setComparing(false);
          sessionStorage.removeItem('baseline_compare_id');
          setCompareStatus(null);
          message.warning('比对任务不存在（后端已重启），请重新启动比对');
        }
        // 其他错误忽略，继续轮询
      }
    }, 3000);
  };

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startAutoPolling = (runId: string) => {
    if (autoPollRef.current) clearInterval(autoPollRef.current);
    persistAutoResearchRunId(runId);
    const pollAutoResearchStatus = async () => {
      try {
        const status = await baselineCompareApi.getAutoResearchStatus(runId);
        setAutoResearchStatus(status);
        void loadAutoResearchTrials(runId);
        if (isAutoResearchTerminalStatus(status.status)) {
          if (autoPollRef.current) {
            clearInterval(autoPollRef.current);
            autoPollRef.current = null;
          }
          setAutoResearching(false);
          const s = String(status.status || '').toLowerCase();
          if (s !== 'interrupted') {
            clearPersistedAutoResearchRunId(runId);
            loadPool();
          }
        }
      } catch (e: unknown) {
        const httpStatus = (e as { response?: { status?: number } })?.response?.status;
        if (httpStatus === 404) {
          if (autoPollRef.current) {
            clearInterval(autoPollRef.current);
            autoPollRef.current = null;
          }
          setAutoResearching(false);
          setAutoResearchStatus(null);
          clearPersistedAutoResearchRunId(runId);
          message.warning('自动实验任务不存在（后端已重启），请重新启动');
        }
      }
    };
    void pollAutoResearchStatus();
    autoPollRef.current = setInterval(() => {
      void pollAutoResearchStatus();
    }, 1500);
  };

  const stopAutoPolling = () => {
    if (autoPollRef.current) {
      clearInterval(autoPollRef.current);
      autoPollRef.current = null;
    }
  };

  const onRunBaselinePrecheck = useCallback(async () => {
    let baselineId: string;
    try {
      await form.validateFields(['baseline_workflow_id']);
      baselineId = String(form.getFieldValue('baseline_workflow_id') || '').trim();
    } catch {
      message.warning('请先选择 Baseline 模板（表单校验未通过）');
      return;
    }
    if (!baselineId) {
      message.warning('请先选择 Baseline 模板');
      return;
    }
    setPrecheckLoading(true);
    try {
      const report = await baselineCompareApi.baselineWorkflowPrecheck({
        baseline_workflow_id: baselineId,
        max_rows: 800,
      }) as Record<string, unknown>;
      const ok = Boolean(report.success);
      const edges = (report.edge_reports as { passed?: boolean; source?: string; target?: string; error?: string }[]) || [];
      const failed = edges.filter(e => !e.passed).length;
      if (ok) {
        const failLines = edges
          .filter(e => !e.passed)
          .slice(0, 8)
          .map(e => `${e.source} → ${e.target}${e.error ? `: ${e.error}` : ''}`);
        Modal.success({
          title: '流水线预检通过',
          width: 640,
          content: (
            <div>
              <p style={{ marginBottom: 8 }}>
                已在样本限流（max_rows=800）下完成预检：共 <strong>{edges.length}</strong> 条边
                {failed > 0 ? (
                  <>，其中 <strong style={{ color: '#d46b08' }}>{failed}</strong> 条未通过（请见下方摘要或控制台 Network 响应）</>
                ) : (
                  <>，全部通过。</>
                )}
              </p>
              {failLines.length > 0 && (
                <ul style={{ fontSize: 12, paddingLeft: 18, maxHeight: 200, overflow: 'auto' }}>
                  {failLines.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              )}
            </div>
          ),
        });
      } else {
        Modal.warning({
          title: '流水线预检未通过',
          width: 720,
          content: (
            <div style={{ maxHeight: 420, overflow: 'auto' }}>
              <pre style={{ fontSize: 11, whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(report, null, 2)}
              </pre>
            </div>
          ),
        });
      }
    } catch (e: unknown) {
      message.error(formatEnhancedApiError(e));
    } finally {
      setPrecheckLoading(false);
    }
  }, [form]);

  const onStartAutoResearch = useCallback(async () => {
    let values: Record<string, unknown>;
    try {
      await form.validateFields(['baseline_workflow_id', 'windows_text']);
    } catch {
      return;
    }
    // validateFields 这里只校验了必填项；真实提交必须读取全部表单值（包含开关）。
    values = form.getFieldsValue(true) as Record<string, unknown>;
    const windowsRaw = (values.windows_text as string) || '';
    const windows = windowsRaw
      .split('\n')
      .map(l => l.trim())
      .filter(Boolean)
      .map(l => {
        const [s, e] = l.split('~');
        return { start_date: s?.trim(), end_date: e?.trim() };
      })
      .filter(w => w.start_date && w.end_date);
    if (windows.length === 0) {
      message.warning('请至少填写一个时间窗');
      return;
    }

    const contractObj: Record<string, unknown> = {};
    if (values.contract_backtest_mode) contractObj.backtest_mode = values.contract_backtest_mode;
    if (values.contract_train_days != null) contractObj.train_days = Number(values.contract_train_days);
    const dailyHorizonAuto =
      granularityToDailyHorizon(values.contract_time_granularity_min)
      ?? (values.contract_daily_horizon != null ? Number(values.contract_daily_horizon) : null);
    if (dailyHorizonAuto != null) contractObj.daily_horizon = dailyHorizonAuto;
    if (values.contract_apply_window_filter != null) contractObj.backtest_apply_window_filter = values.contract_apply_window_filter;
    if (values.contract_mask_target_values != null) contractObj.backtest_mask_target_values = values.contract_mask_target_values;
    if (values.contract_auto_tune_n_trials != null) contractObj.auto_tune_n_trials = Number(values.contract_auto_tune_n_trials);

    const searchSpace = buildAutoSearchSpace(String(values.auto_profile || 'general'), values);
    const recipePick = Array.isArray(values.auto_feature_recipe_ids)
      ? (values.auto_feature_recipe_ids as string[]).filter(Boolean)
      : [];
    if (recipePick.length > 0) {
      searchSpace.feature_recipe_id = recipePick;
    }
    const body: Record<string, unknown> = {
      baseline_workflow_id: values.baseline_workflow_id,
      windows,
      evaluation_contract: contractObj,
      max_iterations: Number(values.auto_max_iterations ?? 20),
      top_k: Number(values.auto_top_k ?? 10),
      search_space: searchSpace,
      scenario_tags: [String(values.auto_profile || 'general')],
      auto_full_automation: Boolean(values.auto_full_automation ?? false),
      auto_apply_risk_level_max: 'medium',
      memory_top_k: Number(values.auto_top_k ?? 3),
      structure_profile_id: values.structure_profile_id,
      skip_workflow_precheck: Boolean(values.skip_workflow_precheck ?? false),
      preferred_model_operator_ids: Array.isArray(values.preferred_model_operator_ids)
        ? (values.preferred_model_operator_ids as string[]).filter(Boolean)
        : [],
      ranking_policy: {
        min_mape_improvement: 0.0,
        max_abs_bias: 3.0,
        max_p95_ape: 35.0,
      },
      compare_config: {
        score_margin: values.score_margin ?? 0,
        aggregate_method: values.aggregate_method ?? 'mean',
        min_windows_challenger_better: values.min_windows_challenger_better ?? null,
        add_to_candidate_pool: values.add_to_candidate_pool ?? true,
        manual_gate: Boolean(values.auto_manual_gate ?? true) && !values.auto_full_automation,
        auto_full_automation: Boolean(values.auto_full_automation ?? false),
        // 人工闸门模式下也要自动生成建议（这样才有内容可以审核），只是不自动应用
        auto_generate_proposal: true,
        auto_apply_recommended: Boolean(values.auto_full_automation ?? false),
        auto_apply_risk_level_max: 'medium',
        memory_top_k: Number(values.auto_top_k ?? 3),
        // 任务 34.2：每轮评估组数
        batch_size: Number(values.auto_batch_size ?? 1),
        max_concurrent_batches: Number(values.auto_batch_size ?? 1),
        // 强制激活层：跳过层饱和等待
        force_activate: Array.isArray(values.force_activate_layers) ? values.force_activate_layers : [],
      },
    };
    body._client_expected_compare_config = { ...(body.compare_config as Record<string, unknown>) };
    body._client_expected_search_space = { ...searchSpace };
    // 任务 25.3：传入用户选择的注册表 ID（空字符串时后端自动匹配）
    if (selectedRegistryId) {
      body.registry_id = selectedRegistryId;
    }

    setAutoResearching(true);
    setAutoResearchStatus(null);
    setAutoResearchTrials([]);
    setSelectedAutoResearchIteration(null);
    try {
      const res = await baselineCompareApi.startAutoResearchAsync(body);
      setAutoResearchRunId(res.run_id);
      persistAutoResearchRunId(res.run_id);
      message.success(`自动实验已启动，ID: ${res.run_id}`);
      startAutoPolling(res.run_id);
    } catch (e: unknown) {
      setAutoResearching(false);
      message.error(formatEnhancedApiError(e));
    }
  }, [form]);

  const onCancelAutoResearch = useCallback(async () => {
    if (!autoResearchRunId) return;
    try {
      await baselineCompareApi.cancelAutoResearch(autoResearchRunId);
      setAutoResearchStatus(prev => ({
        ...(prev || {}),
        cancel_requested: true,
      }));
      // 不立即停轮询，继续观察直到后端状态切到 cancelled/success/failed
      setAutoResearching(true);
      message.info('已发送自动实验取消请求，正在等待后端停止当前任务…');
    } catch {
      message.error('取消自动实验失败');
    }
  }, [autoResearchRunId]);

  const onGenerateProposal = useCallback(async () => {
    if (!autoResearchRunId) {
      message.warning('请先启动自动实验');
      return;
    }
    const iterations = ((autoResearchStatus?.iterations as unknown[]) || []) as Record<string, unknown>[];
    const doneCount = iterations.filter(it => ['success', 'failed'].includes(String(it.status || ''))).length;
    if (doneCount < 1) {
      message.info('请先完成至少 1 轮实验，再生成建议 Diff');
      return;
    }
    setProposalLoading(true);
    try {
      const res = await baselineCompareApi.generateAutoResearchProposal(autoResearchRunId) as Record<string, unknown>;
      const arr = ((res.proposals as unknown[]) || []) as Record<string, unknown>[];
      const rid = (res.recommended_proposal_id as string | undefined) || null;
      setGlmMeta((res.glm_meta as Record<string, unknown> | undefined) || null);
      setProposalList(arr);
      setRecommendedProposalId(rid);
      const first = arr.find(p => String(p.proposal_id) === rid) || arr[0] || null;
      setActiveProposal(first);
      setProposalModalOpen(true);
      message.success('已生成建议 Diff');
    } catch (e: unknown) {
      message.error((e as Error).message || '生成建议失败');
    } finally {
      setProposalLoading(false);
    }
  }, [autoResearchRunId, autoResearchStatus]);

  const onApplyProposal = useCallback(async () => {
    const proposalId = activeProposal?.proposal_id as string | undefined;
    if (!proposalId) return;
    setProposalLoading(true);
    try {
      await baselineCompareApi.applyAutoResearchProposal(proposalId, { reviewer: 'user' });
      setActiveProposal(prev => prev ? { ...prev, status: 'applied' } : prev);
      message.success('建议已应用，将在后续迭代生效');
      setProposalModalOpen(false);
    } catch (e: unknown) {
      message.error((e as Error).message || '应用建议失败');
    } finally {
      setProposalLoading(false);
    }
  }, [activeProposal]);

  const onRejectProposal = useCallback(async () => {
    const proposalId = activeProposal?.proposal_id as string | undefined;
    if (!proposalId) return;
    setProposalLoading(true);
    try {
      await baselineCompareApi.rejectAutoResearchProposal(proposalId, {
        reviewer: 'user',
        reason: 'manual_reject',
      });
      setActiveProposal(prev => prev ? { ...prev, status: 'rejected' } : prev);
      message.info('建议已拒绝');
      setProposalModalOpen(false);
    } catch (e: unknown) {
      message.error((e as Error).message || '拒绝建议失败');
    } finally {
      setProposalLoading(false);
    }
  }, [activeProposal]);

  const onContinueAutoResearch = useCallback(async () => {
    if (!autoResearchRunId) return;
    setProposalLoading(true);
    try {
      const enableFull = Boolean(form.getFieldValue('auto_full_automation'));
      const memoryTopK = Number(form.getFieldValue('auto_top_k') ?? 3);
      await baselineCompareApi.continueAutoResearch(autoResearchRunId, {
        reviewer: 'user',
        enable_full_automation: enableFull,
        auto_apply_risk_level_max: 'medium',
        memory_top_k: Number.isFinite(memoryTopK) ? memoryTopK : 3,
      });
      message.success('已继续下一轮');
    } catch (e: unknown) {
      message.error((e as Error).message || '继续失败');
    } finally {
      setProposalLoading(false);
    }
  }, [autoResearchRunId, form]);

  const onRunSelfcheck = useCallback(async () => {
    if (!autoResearchRunId) {
      message.warning('请先启动自动实验');
      return;
    }
    setSelfcheckLoading(true);
    try {
      const res = await baselineCompareApi.autoResearchSelfcheck(autoResearchRunId);
      setSelfcheckResult(res);
      setSelfcheckOpen(true);
      message.success('自检完成');
    } catch (e: unknown) {
      message.error((e as Error).message || '自检失败');
    } finally {
      setSelfcheckLoading(false);
    }
  }, [autoResearchRunId]);

  const onOpenStructureCompare = useCallback(async () => {
    const st = autoResearchStatus;
    if (!st) {
      message.warning('暂无自动实验状态');
      return;
    }
    const bid = String(st.baseline_workflow_id || '').trim();
    if (!bid) {
      message.warning('状态中没有 baseline_workflow_id');
      return;
    }
    setStructureCompareOpen(true);
    setStructureCompareLoading(true);
    try {
      const wf = await enhancedWorkflowApi.loadWorkflow(bid);
      const patch = (st.effective_structure_patch as Record<string, unknown>) || {};
      setStructureCompareRows(buildBaselineVsChallengerStructureRows(wf, patch));
    } catch (e: unknown) {
      message.error(formatEnhancedApiError(e));
      setStructureCompareRows([]);
    } finally {
      setStructureCompareLoading(false);
    }
  }, [autoResearchStatus]);

  // ── promote ───────────────────────────────────────────────────────────────

  const openPromoteModal = (candidate: Record<string, unknown>) => {
    setPromotingCandidate(candidate);
    promoteForm.resetFields();
    setPromoteModalOpen(true);
  };

  const submitPromote = async () => {
    if (!promotingCandidate) return;
    let values: Record<string, unknown>;
    try {
      values = await promoteForm.validateFields();
    } catch {
      return;
    }
    setPromoting(true);
    try {
      await baselineCompareApi.promoteCandidate(promotingCandidate.id as string, {
        note: values.note as string | undefined,
        set_as_production: values.set_as_production as boolean | undefined,
        production_slot: (values.production_slot as string) || 'default',
        force: values.force as boolean | undefined,
      });
      message.success('Promote 成功');
      setPromoteModalOpen(false);
      loadPool();
      loadProductionRef();
    } catch (e: unknown) {
      message.error((e as Error).message || 'Promote 失败');
    } finally {
      setPromoting(false);
    }
  };

  // ── param comparison panel ────────────────────────────────────────────────

  const renderParamComparePanel = () => {
    if (!watchedBaselineId || !watchedChallengerId) return null;

    const baselineName = baselineParams?.workflow_name ?? watchedBaselineId;
    const challengerName = challengerParams?.workflow_name ?? watchedChallengerId;

    // 渲染一行：参数名 | Baseline值+覆盖输入 | Challenger值+覆盖输入
    const renderEditableRow = (
      key: string,
      label: string,
      hint: string,
      baseVal: unknown,
      challVal: unknown,
      gcKey: string,
    ) => {
      const bStr = baseVal === null || baseVal === undefined ? '未设置' : Array.isArray(baseVal) ? JSON.stringify(baseVal) : String(baseVal);
      const cStr = challVal === null || challVal === undefined ? '未设置' : Array.isArray(challVal) ? JSON.stringify(challVal) : String(challVal);
      const bOverride = baselineOverride[gcKey] ?? '';
      const cOverride = challOverride[gcKey] ?? '';
      const isDiff = bStr !== cStr;
      return (
        <tr key={key} style={{ borderBottom: '1px solid #f0f0f0' }}>
          <td style={{ padding: '6px 8px', width: 150 }}>
            <Tooltip title={hint || gcKey}>
              <span style={{ cursor: 'help', fontSize: 13 }}>{label}</span>
            </Tooltip>
          </td>
          <td style={{ padding: '6px 8px', width: 200 }}>
            <Tag color="geekblue" style={{ marginBottom: 4 }}>{bStr}</Tag>
            <br />
            <Input
              size="small"
              placeholder="覆盖值（留空=沿用）"
              value={bOverride}
              onChange={e => setBaselineOverride(prev => ({ ...prev, [gcKey]: e.target.value }))}
              style={{ width: 160, borderColor: bOverride ? '#1677ff' : undefined }}
              allowClear
            />
            {bOverride && <Tag color="blue" style={{ fontSize: 10, marginLeft: 4 }}>将覆盖</Tag>}
          </td>
          <td style={{ padding: '6px 8px', width: 200 }}>
            <Tag color={isDiff ? 'orange' : 'default'} style={{ marginBottom: 4 }}>{cStr}</Tag>
            {isDiff && <Tag color="orange" style={{ fontSize: 10, marginLeft: 2 }}>差异</Tag>}
            <br />
            <Input
              size="small"
              placeholder="覆盖值（留空=沿用）"
              value={cOverride}
              onChange={e => setChallOverride(prev => ({ ...prev, [gcKey]: e.target.value }))}
              style={{ width: 160, borderColor: cOverride ? '#fa8c16' : undefined }}
              allowClear
            />
            {cOverride && <Tag color="orange" style={{ fontSize: 10, marginLeft: 4 }}>将覆盖</Tag>}
          </td>
        </tr>
      );
    };

    const renderSection = (
      title: string,
      baseFields: ParamField[],
      challFields: ParamField[],
      editable = false,
    ) => {
      const allKeys = Array.from(new Set([...baseFields.map(f => f.key), ...challFields.map(f => f.key)]));
      if (allKeys.length === 0) return null;
      const baseMap = Object.fromEntries(baseFields.map(f => [f.key, f]));
      const challMap = Object.fromEntries(challFields.map(f => [f.key, f]));
      return (
        <div style={{ marginBottom: 16 }} key={title}>
          <div style={{ fontWeight: 600, marginBottom: 6, color: '#555', fontSize: 13 }}>{title}</div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ background: '#fafafa', borderBottom: '1px solid #e8e8e8' }}>
                <th style={{ padding: '4px 8px', textAlign: 'left', width: 150 }}>参数名</th>
                <th style={{ padding: '4px 8px', textAlign: 'left', width: 200 }}>
                  Baseline <Text type="secondary" style={{ fontSize: 11 }}>({baselineName})</Text>
                  {editable && <Text type="secondary" style={{ fontSize: 11, color: '#1677ff', marginLeft: 4 }}>可覆盖↓</Text>}
                </th>
                <th style={{ padding: '4px 8px', textAlign: 'left', width: 200 }}>
                  Challenger <Text type="secondary" style={{ fontSize: 11 }}>({challengerName})</Text>
                  {editable && <Text type="secondary" style={{ fontSize: 11, color: '#fa8c16', marginLeft: 4 }}>可覆盖↓</Text>}
                </th>
              </tr>
            </thead>
            <tbody>
              {allKeys.map(key => {
                const bf = baseMap[key];
                const cf = challMap[key];
                const label = bf?.label ?? cf?.label ?? key;
                const hint = bf?.hint ?? cf?.hint ?? '';
                if (editable) {
                  return renderEditableRow(key, label, hint, bf?.value, cf?.value, key);
                }
                return renderParamRow(key, label, hint, bf?.value, cf?.value);
              })}
            </tbody>
          </table>
        </div>
      );
    };

    const renderNodeSections = () => {
      const baseNodeMap = Object.fromEntries((baselineParams?.node_params ?? []).map((g: NodeParamGroup) => [g.node_id, g]));
      const challNodeMap = Object.fromEntries((challengerParams?.node_params ?? []).map((g: NodeParamGroup) => [g.node_id, g]));
      const allNodeIds = Array.from(new Set([
        ...(baselineParams?.node_params ?? []).map((g: NodeParamGroup) => g.node_id),
        ...(challengerParams?.node_params ?? []).map((g: NodeParamGroup) => g.node_id),
      ]));
      return allNodeIds.map(nodeId => {
        const bg = baseNodeMap[nodeId];
        const cg = challNodeMap[nodeId];
        const label = bg?.node_label ?? cg?.node_label ?? nodeId;
        return renderSection(`节点：${label}`, bg?.fields ?? [], cg?.fields ?? [], true);
      });
    };

    return (
      <Card
        title={
          <Space>
            <span>参数对比</span>
            <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
              global_config 层可直接覆盖；节点级参数需去编辑器修改后重新选择模板
            </Text>
          </Space>
        }
        size="small"
        style={{ marginBottom: 16 }}
      >
        <Spin spinning={loadingParams}>
          {!loadingParams && !baselineParams && !challengerParams && (
            <Text type="secondary">加载中…</Text>
          )}
          {(baselineParams || challengerParams) && (
            <>
              {renderSection('global_config 参数', baselineParams?.global_config_params ?? [], challengerParams?.global_config_params ?? [], true)}
              <Alert
                type="warning"
                showIcon
                style={{ marginTop: 8 }}
                message="节点级参数（如贝叶斯搜索轮数、lag 配置等）需在算法模板编辑器里修改后重新选择模板"
              />
            </>
          )}
        </Spin>
      </Card>
    );
  };

  // ── candidate pool columns ────────────────────────────────────────────────

  const metricFromWindows = (record: Record<string, unknown>, side: 'baseline' | 'challenger') => {
    const windows = (record.window_results as Record<string, unknown>[] | undefined)
      || ((record.result as Record<string, unknown> | undefined)?.window_results as Record<string, unknown>[] | undefined)
      || [];
    const values = windows.map((row) => {
      const metrics = ((row?.[side] as Record<string, unknown> | undefined)?.avg_metrics as Record<string, unknown> | undefined) || {};
      const raw = metrics.avg_mape ?? metrics.avg_smape;
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    }).filter((v): v is number => v != null);
    if (values.length === 0) return null;
    return values.reduce((sum, v) => sum + v, 0) / values.length;
  };

  const formatMape = (value: number | null) => (
    value == null ? <Text type="secondary">-</Text> : <Tag color="blue">{value.toFixed(4)}</Tag>
  );

  const verificationConfigSummary = (record: Record<string, unknown>) => {
    const override = (record.challenger_config_override || record.challenger_override || {}) as Record<string, unknown>;
    const globalPatch = (record.challenger_global_config_patch || record.effective_parameter_patch || {}) as Record<string, unknown>;
    const nodePatches = (record.challenger_node_param_patches || record.node_param_patches || []) as unknown[];
    const parts = [
      Object.keys(override).length ? JSON.stringify(override) : '',
      Object.keys(globalPatch).length ? `global=${JSON.stringify(globalPatch)}` : '',
      nodePatches.length ? `node=${nodePatches.length}` : '',
    ].filter(Boolean);
    return parts.join(' | ') || '-';
  };

  const defaultVerificationWindows = [
    { start_date: '2026-03-01', end_date: '2026-03-08' },
    { start_date: '2026-03-08', end_date: '2026-03-15' },
    { start_date: '2026-03-15', end_date: '2026-03-22' },
  ];

  const openVerificationModal = (candidate: Record<string, unknown>) => {
    setVerificationCandidate(candidate);
    verificationForm.setFieldsValue({
      windows: defaultVerificationWindows,
      aggregate_method: 'mean',
      min_windows_challenger_better: 2,
      score_margin: 0,
      auto_start: false,
      note: '',
    });
    setVerificationModalOpen(true);
  };

  const openStartVerificationModal = (item: Record<string, unknown>) => {
    setStartVerificationItem(item);
    const existingWindows = (item.windows as Array<{ start_date: string; end_date: string }>) || defaultVerificationWindows;
    startVerificationForm.setFieldsValue({
      windows: existingWindows,
      aggregate_method: String(item.aggregate_method || 'mean'),
      min_windows_challenger_better: Number(item.min_windows_challenger_better ?? 2),
      score_margin: Number(item.score_margin ?? 0),
    });
    setStartVerificationModalOpen(true);
  };

  const submitStartVerification = async () => {
    if (!startVerificationItem) return;
    let values: Record<string, unknown>;
    try {
      values = await startVerificationForm.validateFields();
    } catch {
      return;
    }
    const windows = ((values.windows as Array<Record<string, unknown>> | undefined) || [])
      .map((row) => ({
        start_date: String(row.start_date || '').trim(),
        end_date: String(row.end_date || '').trim(),
      }))
      .filter(row => row.start_date && row.end_date);
    if (windows.length === 0) {
      message.error('至少需要 1 个复验窗口');
      return;
    }
    setStartingVerification(true);
    try {
      const res = await baselineCompareApi.startVerification(startVerificationItem.id as string, {
        windows,
        aggregate_method: String(values.aggregate_method || 'mean'),
        min_windows_challenger_better: Number(values.min_windows_challenger_better ?? 2),
        score_margin: Number(values.score_margin ?? 0),
      });
      if (res.started) message.success('已启动复验');
      else message.info(String(res.reason || '未启动'));
      setStartVerificationModalOpen(false);
      loadVerificationQueue();
    } catch (e: unknown) {
      message.error((e as Error).message || '启动失败');
    } finally {
      setStartingVerification(false);
    }
  };

  const enqueueVerification = async () => {
    if (!verificationCandidate) return;
    let values: Record<string, unknown>;
    try {
      values = await verificationForm.validateFields();
    } catch {
      return;
    }
    const windows = ((values.windows as Record<string, unknown>[] | undefined) || [])
      .map((row) => ({
        start_date: String(row.start_date || '').trim(),
        end_date: String(row.end_date || '').trim(),
      }))
      .filter(row => row.start_date && row.end_date);
    if (windows.length === 0) {
      message.error('至少需要 1 个复验窗口');
      return;
    }
    setEnqueueingVerification(true);
    try {
      const res = await baselineCompareApi.enqueueCandidateVerification(verificationCandidate.id as string, {
        windows,
        aggregate_method: String(values.aggregate_method || 'mean'),
        min_windows_challenger_better: Number(values.min_windows_challenger_better ?? 2),
        score_margin: Number(values.score_margin ?? 0),
        auto_start: Boolean(values.auto_start),
        note: values.note as string | undefined,
      });
      message.success(res.deduped ? '复验池已有同类候选' : '已加入复验池');
      setVerificationModalOpen(false);
      await Promise.all([loadVerificationQueue(), loadPool()]);
    } catch (e: unknown) {
      message.error((e as Error).message || '加入复验池失败');
    } finally {
      setEnqueueingVerification(false);
    }
  };

  const refreshVerificationAndPool = async () => {
    await Promise.all([loadVerificationQueue(), loadPool()]);
  };

  const renderVerificationQueueCard = () => (
    <Card
      title={<span style={{ fontSize: 14, fontWeight: 600, color: uiInk, letterSpacing: -0.3 }}>复验池</span>}
      size="small"
      style={{ marginTop: 16, border: '1px solid #e8eef5', borderRadius: 12, boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)' }}
      extra={
        <Space>
          <Button size="small" onClick={refreshVerificationAndPool}>刷新</Button>
          <Button
            size="small"
            type="primary"
            onClick={async () => {
              try {
                const res = await baselineCompareApi.startNextVerification();
                if (res.started) message.success('已启动下一条复验');
                else message.info(String(res.reason || '没有可启动的复验项'));
                loadVerificationQueue();
              } catch (e: unknown) {
                message.error((e as Error).message || '启动复验失败');
              }
            }}
          >
            启动下一条
          </Button>
        </Space>
      }
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 10 }}
        message="复验池使用独立资源池，可与 AutoResearch run 同时执行。每次串行跑 1 条复验项；内存压力过高时后端会阻止自动启动。"
      />
      <Spin spinning={loadingVerificationQueue}>
        <Table
          dataSource={verificationQueue}
          rowKey="id"
          size="small"
          pagination={{ pageSize: 6 }}
          columns={[
            {
              title: '复验 ID',
              dataIndex: 'id',
              width: 150,
              render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text>,
            },
            {
              title: '候选',
              dataIndex: 'candidate_id',
              width: 150,
              render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text>,
            },
            {
              title: '配置',
              key: 'config',
              width: 220,
              render: (_: unknown, record: Record<string, unknown>) => (
                <Tooltip title={verificationConfigSummary(record)}>
                  <Text code style={{ fontSize: 11 }}>
                    {verificationConfigSummary(record)}
                  </Text>
                </Tooltip>
              ),
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 90,
              render: (v: string) => <Tag color={v === 'passed' ? 'green' : v === 'running' ? 'blue' : v === 'failed' ? 'red' : 'default'}>{v || '-'}</Tag>,
            },
            {
              title: '入池精度 (单窗口)',
              key: 'source_metrics',
              width: 200,
              render: (_: unknown, record: Record<string, unknown>) => {
                const sm = record.source_metrics as Record<string, unknown> | undefined;
                if (!sm) return <Text type="secondary">-</Text>;
                const bm = Number(sm.baseline_mape);
                const cm = Number(sm.challenger_mape);
                const imp = Number(sm.mape_improvement);
                return (
                  <Space direction="vertical" size={0} style={{ lineHeight: '1.4' }}>
                    <span style={{ fontSize: 11 }}>
                      B: {Number.isFinite(bm) ? bm.toFixed(4) : '-'}
                      {' → '}
                      C: {Number.isFinite(cm) ? cm.toFixed(4) : '-'}
                    </span>
                    {Number.isFinite(imp) && (
                      <Tag color={imp > 0 ? 'green' : imp < 0 ? 'red' : 'default'} style={{ fontSize: 10 }}>
                        {imp > 0 ? '+' : ''}{imp.toFixed(4)}
                      </Tag>
                    )}
                  </Space>
                );
              },
            },
            {
              title: '复验窗口',
              key: 'windows',
              width: 80,
              render: (_: unknown, record: Record<string, unknown>) => `${((record.windows as unknown[]) || []).length} 个`,
            },
            {
              title: '复验结果',
              key: 'result',
              width: 240,
              render: (_: unknown, record: Record<string, unknown>) => {
                const result = record.result as Record<string, unknown> | undefined;
                const summary = result?.summary as Record<string, unknown> | undefined;
                if (!summary) return <Text type="secondary">{String(record.failure_reason || '待执行')}</Text>;
                const aggB = Number(summary.aggregate_baseline_score);
                const aggC = Number(summary.aggregate_challenger_score);
                const adv = Number(summary.score_advantage ?? 0);
                return (
                  <Space direction="vertical" size={0} style={{ lineHeight: '1.4' }}>
                    <span style={{ fontSize: 11 }}>
                      B: {Number.isFinite(aggB) ? aggB.toFixed(4) : '-'}
                      {' → '}
                      C: {Number.isFinite(aggC) ? aggC.toFixed(4) : '-'}
                    </span>
                    <Space size={4}>
                      <Tag color={adv > 0 ? 'green' : adv < 0 ? 'red' : 'default'} style={{ fontSize: 10 }}>
                        {adv > 0 ? '+' : ''}{adv.toFixed(4)}
                      </Tag>
                      <Tag style={{ fontSize: 10 }}>{String(summary.windows_challenger_better ?? 0)}/{String(summary.windows_total ?? 0)} 窗口胜出</Tag>
                    </Space>
                  </Space>
                );
              },
            },
            {
              title: '操作',
              width: 140,
              render: (_: unknown, record: Record<string, unknown>) => (
                <Space size={4}>
                  <Button
                    size="small"
                    disabled={String(record.status || '') === 'running' || String(record.status || '') === 'passed'}
                    onClick={() => openStartVerificationModal(record)}
                  >
                    启动
                  </Button>
                  <Button
                    size="small"
                    danger
                    disabled={!['queued', 'running'].includes(String(record.status || ''))}
                    onClick={async () => {
                      try {
                        await baselineCompareApi.cancelVerification(record.id as string);
                        message.success('已发送取消');
                        loadVerificationQueue();
                      } catch (e: unknown) {
                        message.error((e as Error).message || '取消失败');
                      }
                    }}
                  >
                    取消
                  </Button>
                </Space>
              ),
            },
          ]}
          locale={{ emptyText: '暂无复验项' }}
        />
      </Spin>
    </Card>
  );

  const poolColumns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
      width: 180,
      render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text>,
    },
    {
      title: 'Challenger',
      dataIndex: 'challenger_workflow_id',
      key: 'challenger_workflow_id',
      width: 200,
      render: (v: string) => {
        const wf = workflows.find(w => w.id === v);
        return wf ? wf.name : v;
      },
    },
    {
      title: 'MAPE 改善',
      key: 'mape_improvement',
      width: 100,
      render: (_: unknown, record: Record<string, unknown>) => {
        const summary = record.summary as Record<string, unknown> | undefined;
        const adv = summary?.mape_improvement ?? summary?.score_advantage;
        const baseScore = summary?.aggregate_baseline_score;
        const challScore = summary?.aggregate_challenger_score;
        if (adv === null || adv === undefined) return <Tag>-</Tag>;
        const advNum = typeof adv === 'number' ? adv : Number(adv);
        return (
          <Tooltip title={`Baseline: ${baseScore ?? '-'} → Challenger: ${challScore ?? '-'}`}>
            <Tag color={advNum > 0 ? 'green' : advNum < 0 ? 'red' : 'default'}>
              {advNum > 0 ? '+' : ''}{typeof advNum === 'number' ? advNum.toFixed(4) : adv}
            </Tag>
          </Tooltip>
        );
      },
    },
    {
      title: 'Baseline MAPE',
      key: 'baseline_mape',
      width: 120,
      render: (_: unknown, record: Record<string, unknown>) => formatMape(metricFromWindows(record, 'baseline')),
    },
    {
      title: 'Challenge MAPE',
      key: 'challenge_mape',
      width: 130,
      render: (_: unknown, record: Record<string, unknown>) => formatMape(metricFromWindows(record, 'challenger')),
    },
    {
      title: 'Run 轮次',
      key: 'source_run_completed_iterations',
      width: 100,
      render: (_: unknown, record: Record<string, unknown>) => {
        const completed = record.source_run_completed_iterations;
        const total = record.source_run_total_iterations;
        return (
          <Tag color={Number(completed || 0) >= 10 ? 'green' : 'default'}>
            {String(completed ?? 0)}{total ? `/${String(total)}` : ''} 轮
          </Tag>
        );
      },
    },
    {
      title: '来源',
      key: 'source',
      width: 160,
      render: (_: unknown, record: Record<string, unknown>) => {
        const sourceRunId = record.source_run_id as string | undefined;
        const sourceIteration = record.source_iteration;
        if (sourceRunId) {
          return <Tag color="blue">AutoResearch 第 {String(sourceIteration ?? '?')} 轮</Tag>;
        }
        return <Tag>手动比对</Tag>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (v: string, record: Record<string, unknown>) => {
        const ver = verificationByCandidateId.get(String(record.id || ''));
        const verStatus = String(ver?.status || '');
        return (
          <Space size={4}>
            <Tag>{v ?? '-'}</Tag>
            {verStatus ? <Tag color={verStatus === 'passed' ? 'green' : verStatus === 'running' ? 'blue' : 'orange'}>复验:{verStatus}</Tag> : null}
          </Space>
        );
      },
    },
    {
      title: '写入时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: unknown, record: Record<string, unknown>) => (
        <Space size={4}>
          <Button
            size="small"
            onClick={async () => {
              setDetailDrawerOpen(true);
              setDetailCandidate(null);
              setLoadingDetail(true);
              try {
                const res = await baselineCompareApi.getCandidateDetail(record.id as string);
                setDetailCandidate(res.candidate);
              } catch {
                message.error('加载详情失败');
              } finally {
                setLoadingDetail(false);
              }
            }}
          >
            详情
          </Button>
          <Button
            size="small"
            type="primary"
            onClick={() => openPromoteModal(record)}
            disabled={record.status === 'promoted'}
          >
            Promote
          </Button>
          <Button
            size="small"
            onClick={() => openVerificationModal(record)}
          >
            入复验
          </Button>
          <Button
            size="small"
            danger
            onClick={async () => {
              try {
                await baselineCompareApi.deleteCandidate(record.id as string);
                message.success('已删除');
                loadPool();
              } catch {
                message.error('删除失败');
              }
            }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ];

  // ── render ────────────────────────────────────────────────────────────────

  const productionSlot = (productionRef?.slots as Record<string, unknown> | undefined)?.default as
    | Record<string, unknown>
    | undefined;
  const queuedVerificationCount = verificationQueue.filter((item) =>
    ['queued', 'running'].includes(String(item.status || '').toLowerCase()),
  ).length;
  const researchStage = verificationQueue.length > 0
    ? 4
    : matureCandidatePool.length > 0
      ? 3
      : autoResearchStatus
        ? 2
        : 1;
  const researchStages = [
    { title: '配置实验', description: '基线、时间窗与评测口径' },
    { title: '观察运行', description: '进度、问题、证据与策略' },
    { title: '筛选候选', description: '收益、新颖性与来源追溯' },
    { title: '复验提升', description: '多窗口确认后 Promote' },
  ];
  const cockpitCurveRows = collectAutoResearchCurveRows(autoResearchStatus, autoResearchTrials);
  const selectedCurveExists = selectedProfileIteration != null
    && cockpitCurveRows.some((row) => row.iteration === selectedProfileIteration);
  const challengerCurve = selectedCurveExists
    ? cockpitCurveRows.find((row) => row.iteration === selectedProfileIteration) || null
    : cockpitCurveRows[cockpitCurveRows.length - 1] || null;
  const historicalReferenceCurve = cockpitCurveRows.length > 1
    ? cockpitCurveRows.find((row) => row.iteration !== challengerCurve?.iteration) || null
    : null;
  const curveStep = Math.max(1, Math.ceil((challengerCurve?.points.length || 0) / 520));
  const cockpitCurvePoints = (challengerCurve?.points || []).filter((_, index) => index % curveStep === 0);
  const historicalPredictionByTimestamp = new Map(
    (historicalReferenceCurve?.points || []).map((point) => [point.timestamp, point.predicted]),
  );
  const hasTrueBaselineCurve = cockpitCurvePoints.some((point) => Number.isFinite(point.baseline_predicted));
  const baselineSeriesLabel = hasTrueBaselineCurve ? 'Baseline' : '首轮参考';
  const hasBaselineReference = hasTrueBaselineCurve || Boolean(historicalReferenceCurve);
  const curveLabels = cockpitCurvePoints.map((point) => {
    const raw = String(point.timestamp || '');
    return raw.length > 16 ? raw.slice(5, 16) : raw;
  });
  const curveActual = cockpitCurvePoints.map((point) => point.actual);
  const curveChallenger = cockpitCurvePoints.map((point) => point.predicted);
  const curveBaseline = cockpitCurvePoints.map((point, index) => {
    if (Number.isFinite(point.baseline_predicted)) return point.baseline_predicted as number;
    const byTimestamp = historicalPredictionByTimestamp.get(point.timestamp);
    if (Number.isFinite(byTimestamp)) return byTimestamp;
    const fallback = historicalReferenceCurve?.points[index * curveStep]?.predicted;
    return Number.isFinite(fallback) ? fallback : null;
  });
  const calculateCurveMape = (actual: number[], predicted: Array<number | null>) => {
    const errors = actual
      .map((value, index) => {
        const prediction = predicted[index];
        if (!Number.isFinite(value) || !Number.isFinite(prediction) || Math.abs(value) <= 1e-8) return null;
        return Math.abs((value - Number(prediction)) / value) * 100;
      })
      .filter((value): value is number => value != null);
    return errors.length > 0
      ? errors.reduce((sum, value) => sum + value, 0) / errors.length
      : null;
  };
  const baselineCurveMape = hasBaselineReference ? calculateCurveMape(curveActual, curveBaseline) : null;
  const challengerCurveMape = calculateCurveMape(curveActual, curveChallenger);
  const curveImprovement = baselineCurveMape != null && challengerCurveMape != null && baselineCurveMape !== 0
    ? ((baselineCurveMape - challengerCurveMape) / baselineCurveMape) * 100
    : null;
  const peakScatter = cockpitCurvePoints
    .map((point, index) => point.is_peak ? [curveLabels[index], point.actual] : null)
    .filter(Boolean);
  const valleyScatter = cockpitCurvePoints
    .map((point, index) => point.is_valley ? [curveLabels[index], point.actual] : null)
    .filter(Boolean);
  const cockpitCurveOption = {
    animationDuration: 320,
    color: ['#0f172a', '#94a3b8', '#2563eb', '#dc2626', '#0891b2'],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#0f172a',
      borderWidth: 0,
      textStyle: { color: '#ffffff', fontSize: 12 },
    },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 18,
      itemHeight: 8,
      textStyle: { color: '#475569', fontSize: 11 },
      data: hasBaselineReference
        ? ['实际值', baselineSeriesLabel, 'Challenger', '峰点', '谷点']
        : ['实际值', 'Challenger', '峰点', '谷点'],
    },
    grid: { left: 52, right: 18, top: 46, bottom: 42 },
    xAxis: {
      type: 'category',
      data: curveLabels,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      axisTick: { show: false },
      axisLabel: { color: '#64748b', fontSize: 10, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
      axisLabel: { color: '#64748b', fontSize: 10 },
    },
    series: [
      {
        name: '实际值',
        type: 'line',
        data: curveActual,
        showSymbol: false,
        smooth: 0.16,
        lineStyle: { width: 2.2, color: '#0f172a' },
      },
      ...(hasBaselineReference ? [{
        name: baselineSeriesLabel,
        type: 'line',
        data: curveBaseline,
        showSymbol: false,
        smooth: 0.16,
        lineStyle: { width: 1.8, type: 'dashed', color: '#94a3b8' },
      }] : []),
      {
        name: 'Challenger',
        type: 'line',
        data: curveChallenger,
        showSymbol: false,
        smooth: 0.16,
        lineStyle: { width: 2.2, color: '#2563eb' },
      },
      { name: '峰点', type: 'scatter', data: peakScatter, symbolSize: 7, itemStyle: { color: '#dc2626' } },
      { name: '谷点', type: 'scatter', data: valleyScatter, symbolSize: 7, itemStyle: { color: '#0891b2' } },
    ],
  };
  const runCompletedIterations = getAutoResearchCompletedIterations(autoResearchStatus || {});
  const runMaxIterations = Number(autoResearchStatus?.max_iterations || form.getFieldValue('auto_max_iterations') || 0);
  const runProgressPercent = runMaxIterations > 0
    ? Math.min(100, Math.round((runCompletedIterations / runMaxIterations) * 100))
    : 0;
  const topCandidate = matureCandidatePool[0] || null;
  const researchQuestions = ((autoResearchStatus?.research_questions as unknown[]) || []) as Record<string, unknown>[];
  const uniqueResearchQuestions = Array.from(
    researchQuestions.reduce<Map<string, Record<string, unknown>>>((acc, item) => {
      const key = String(
        item.question_key
        || `${String(item.question || '')}::${String(item.next_experiment_goal || '')}`,
      );
      acc.set(key, { ...(acc.get(key) || {}), ...item });
      return acc;
    }, new Map()).values(),
  );
  const openResearchQuestions = uniqueResearchQuestions
    .filter((item) => ['open', 'testing'].includes(String(item.status || 'open').toLowerCase()))
    .sort((a, b) =>
      Number(b.last_seen_iteration ?? b.iteration ?? b.first_seen_iteration ?? 0)
      - Number(a.last_seen_iteration ?? a.iteration ?? a.first_seen_iteration ?? 0),
    );
  const openQuestionCount = openResearchQuestions.length;
  const evidenceSummary = (autoResearchStatus?.evidence_summary as Record<string, unknown> | undefined) || {};
  const evidenceStrongCount = Number(
    evidenceSummary.strong
    ?? evidenceSummary.strong_count
    ?? evidenceSummary.multi_window_confirmed
    ?? 0,
  );
  const knowledgeGovernance = (autoResearchStatus?.knowledge_governance as Record<string, unknown> | undefined) || {};
  const activeKnowledgeCount = Number(
    knowledgeGovernance.active_count
    ?? knowledgeGovernance.active
    ?? knowledgeGovernance.total_active
    ?? 0,
  );
  const experimentInsights = (autoResearchStatus?.insights as Record<string, unknown> | undefined) || {};
  const effectiveDirections = ((experimentInsights.effective_directions as unknown[]) || []).map(String);
  const ineffectiveDirections = ((experimentInsights.ineffective_directions as unknown[]) || []).map(String);
  const hypothesesTested = Number(experimentInsights.total_hypotheses_tested || 0);
  const hypothesesVerified = Number(experimentInsights.hypotheses_verified || 0);
  const hypothesesDisproved = Number(experimentInsights.hypotheses_disproved || 0);
  const hypothesisChain = ((autoResearchStatus?.hypothesis_chain as unknown[]) || []) as Record<string, unknown>[];
  const glmCallHistory = ((autoResearchStatus?.glm_call_history as unknown[]) || []) as Record<string, unknown>[];
  const glmUsedCount = glmCallHistory.filter((record) => {
    const meta = (record.glm_meta as Record<string, unknown> | undefined) || {};
    return Boolean(meta.llm_used);
  }).length;
  const latestRunLogs = (((autoResearchStatus?.logs as unknown[]) || []) as Record<string, unknown>[]).slice(-40).reverse();
  const currentIterationLive = (autoResearchStatus?.current_iteration_live as Record<string, unknown> | undefined) || {};
  const currentLiveSummary = (currentIterationLive.live_summary as Record<string, unknown> | undefined) || {};
  const currentLiveProgress = (currentIterationLive.progress as Record<string, unknown> | undefined) || {};
  const currentBatchStatus = (autoResearchStatus?.batch_eval_status as Record<string, unknown> | undefined) || {};
  const currentBatchGroups = ((currentBatchStatus.groups as unknown[]) || []) as Record<string, unknown>[];
  const isLiveAutoResearchRun = isAutoResearchRunningStatus(autoResearchStatus?.status);
  const isCommandRunActive = autoResearchStatus ? isLiveAutoResearchRun : autoResearching;
  const currentPhase = isLiveAutoResearchRun
    ? String(currentLiveSummary.current_phase || currentLiveProgress.current_phase || 'preparing')
    : 'completed';
  const phaseLabels: Record<string, string> = {
    preparing: '准备运行环境',
    baseline_warmup: 'Baseline 预热',
    baseline_running: 'Baseline 回测',
    challenger_running: 'Challenger 回测',
    completed: '已完成',
  };
  const progressPercent = (row: Record<string, unknown>) => {
    const done = Number(row.windows_done ?? row.window_index ?? 0);
    const total = Number(row.windows_total ?? row.window_total ?? 0);
    if (!Number.isFinite(done) || !Number.isFinite(total) || total <= 0) return 0;
    return Math.max(0, Math.min(100, Math.round((done / total) * 100)));
  };
  const currentWindowDone = Number(currentLiveSummary.windows_done ?? currentLiveProgress.window_index ?? 0);
  const currentWindowTotal = Number(currentLiveSummary.windows_total ?? currentLiveProgress.window_total ?? 0);
  const showRealtimeProgress = Boolean(
    autoResearchStatus
    && (
      isLiveAutoResearchRun
      || currentBatchGroups.length > 0
      || currentWindowTotal > 0
    ),
  );
  const openFullEvidence = () => {
    setShowAdvancedDetails(true);
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        advancedDetailsAnchorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  };
  const recentRunsContent = latestAutoRunLoading && latestAutoRuns.length === 0 && !latestAutoRun ? (
    <Spin size="small" />
  ) : durableAutoRuns.length > 0 ? (
    <Space direction="vertical" size={8} style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        message={`长期列表默认显示：当前活跃 run、已完成不少于 10 轮的 run、以及可恢复的中断 run。当前显示 ${durableAutoRuns.length} / ${latestAutoRuns.length} 个。`}
      />
      <div className="autoresearch-run-list">
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          {durableAutoRuns.map((row) => {
            const runId = String(row.run_id || '');
            const active = autoResearchRunId === runId;
            const updatedAt = String(row.job_updated_at || row.updated_at || row.created_at || '');
            const completedIterations = getAutoResearchCompletedIterations(row);
            return (
              <div key={runId} className={`autoresearch-run-row ${active ? 'is-active' : ''}`}>
                <Space direction="vertical" size={1}>
                  <Space size={6} wrap>
                    <Text code style={{ fontSize: 12 }}>{runId || '-'}</Text>
                    {active ? <Tag color="blue">当前查看</Tag> : null}
                    {isAutoResearchActiveRow(row) ? <Tag color="processing">活跃</Tag> : null}
                    {completedIterations >= 10 ? <Tag color="green">长期记录</Tag> : null}
                  </Space>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {updatedAt ? updatedAt.replace('T', ' ').slice(0, 19) : '-'}
                  </Text>
                </Space>
                <Space wrap size={[4, 4]}>
                  <Tag color={getAutoResearchStatusColor(row.status)}>
                    {getAutoResearchStatusText(row.status)}
                  </Tag>
                  {row.job_status ? (
                    <Tag color={getAutoResearchStatusColor(row.job_status)}>
                      worker: {getAutoResearchStatusText(row.job_status)}
                    </Tag>
                  ) : null}
                </Space>
                <Space direction="vertical" size={2}>
                  {renderAutoResearchTrainingProgress(row, { width: '100%', showText: false })}
                  {renderAutoResearchIterationProgress(row, { width: '100%', showText: false })}
                  <Text type="secondary" style={{ fontSize: 11 }}>已完成 {completedIterations} 轮</Text>
                </Space>
                <Space size={6} wrap style={{ justifyContent: 'flex-end' }}>
                  <Button size="small" type={active ? 'default' : 'primary'} ghost={!active} onClick={() => void openLatestAutoResearchRun(row)}>
                    {isAutoResearchActiveRow(row) ? '恢复查看' : '查看结果'}
                  </Button>
                  {isAutoResearchResumableRow(row) ? (
                    <Button size="small" type="primary" onClick={() => void resumeLatestAutoResearchRun(row)}>
                      继续训练
                    </Button>
                  ) : null}
                </Space>
              </div>
            );
          })}
        </Space>
      </div>
    </Space>
  ) : (
    <Space>
      <Text type="secondary">暂无可恢复的 AutoResearch run</Text>
      <Button size="small" onClick={() => void detectLatestAutoResearchRun(true)}>立即检测</Button>
    </Space>
  );

  return (
    <div className="autoresearch-page">
      <div className="autoresearch-command-bar">
        <div className="autoresearch-command-bar__identity">
          <Text className="autoresearch-page-kicker">AutoResearch</Text>
          <div className="autoresearch-command-bar__title-row">
            <Typography.Title level={2} className="autoresearch-page-title">
              研究控制台
            </Typography.Title>
            <Tag color={getAutoResearchStatusColor(autoResearchStatus?.status)}>
              {autoResearchStatus
                ? getAutoResearchStatusText(autoResearchStatus.status)
                : '尚未运行'}
            </Tag>
          </div>
          <Text className="autoresearch-page-description">
            {autoResearchRunId
              ? `当前运行 ${autoResearchRunId}`
              : '配置实验后，系统将持续生成候选并积累可复验证据。'}
          </Text>
        </div>
        <div className="autoresearch-command-bar__progress">
          <div className="autoresearch-command-bar__progress-head">
            <span>研究进度</span>
            <strong>{runCompletedIterations} / {runMaxIterations || '-'}</strong>
          </div>
          <Progress percent={runProgressPercent} size="small" showInfo={false} />
          <Text type="secondary">{autoRunInsights.phaseText}</Text>
        </div>
        <Space className="autoresearch-command-bar__actions" wrap>
          <Button onClick={() => setShowAdvancedDetails((value) => !value)}>
            {showAdvancedDetails ? '收起高级诊断' : '高级诊断'}
          </Button>
          <Button onClick={() => setConfigDrawerOpen(true)}>
            实验配置
          </Button>
          <Button
            type="primary"
            loading={autoResearching && !autoResearchStatus}
            onClick={isCommandRunActive ? onCancelAutoResearch : onStartAutoResearch}
            danger={isCommandRunActive}
          >
            {isCommandRunActive ? '停止运行' : '启动自动实验'}
          </Button>
        </Space>
      </div>

      <div className="autoresearch-stage-rail" aria-label="AutoResearch 研究流程">
        {researchStages.map((stage, index) => {
          const stageNumber = index + 1;
          const stateClass = stageNumber === researchStage
            ? 'is-active'
            : stageNumber < researchStage
              ? 'is-complete'
              : '';
          return (
            <div className={`autoresearch-stage ${stateClass}`} key={stage.title}>
              <span className="autoresearch-stage__index">{stageNumber}</span>
              <span className="autoresearch-stage__title">{stage.title}</span>
              <span className="autoresearch-stage__description">{stage.description}</span>
            </div>
          );
        })}
      </div>

      {showRealtimeProgress && (
        <Card className="autoresearch-surface autoresearch-realtime-progress" size="small">
          <div className="autoresearch-realtime-progress__header">
            <div>
              <Text strong>{isLiveAutoResearchRun ? '实时执行进度' : '最近执行进度'}</Text>
              <Text type="secondary">
                第 {String(autoResearchStatus?.current_iteration || currentBatchStatus.iteration || '-')} 轮 · {phaseLabels[currentPhase] || currentPhase}
              </Text>
            </div>
            <Space size={6} wrap>
              {currentLiveSummary.current_window || currentLiveProgress.current_window ? (
                <Tag>{String(currentLiveSummary.current_window || currentLiveProgress.current_window)}</Tag>
              ) : null}
              <Tag color={isLiveAutoResearchRun ? 'processing' : 'default'}>
                {isLiveAutoResearchRun ? '约 1.5 秒刷新' : '已结束'}
              </Tag>
            </Space>
          </div>

          {currentBatchGroups.length > 1 ? (
            <div className="autoresearch-progress-groups">
              {currentBatchGroups.map((group, index) => {
                const status = String(group.status || 'pending').toLowerCase();
                const done = Number(group.windows_done ?? group.window_index ?? 0);
                const total = Number(group.windows_total ?? group.window_total ?? 0);
                const percent = progressPercent(group);
                const groupPhase = status === 'success' ? 'completed' : String(group.current_phase || '');
                return (
                  <div className={`autoresearch-progress-lane is-${status}`} key={String(group.group_idx ?? index)}>
                    <div className="autoresearch-progress-lane__head">
                      <div>
                        <strong>实验组 {Number(group.group_idx ?? index) + 1}</strong>
                        <span>{phaseLabels[groupPhase] || groupPhase || (status === 'pending' ? '等待调度' : '执行中')}</span>
                      </div>
                      <div className="autoresearch-progress-lane__value">
                        <strong>{percent}%</strong>
                        <span>{total > 0 ? `${done}/${total} 窗口` : getAutoResearchStatusText(status)}</span>
                      </div>
                    </div>
                    <Progress
                      percent={percent}
                      showInfo={false}
                      status={status === 'failed' || status === 'error' ? 'exception' : status === 'success' ? 'success' : 'active'}
                      strokeColor={status === 'pending' ? '#94a3b8' : '#2563eb'}
                    />
                    <Text type="secondary" ellipsis>
                      {String(group.current_window || '等待窗口信息')}
                    </Text>
                    <Collapse
                      ghost
                      size="small"
                      className="autoresearch-group-config"
                      items={[{
                        key: 'config',
                        label: '配置改动详情',
                        children: (() => {
                          const override = (group.override as Record<string, unknown> | undefined) || {};
                          const nodePatches = ((group.node_param_patches as unknown[]) || []) as Record<string, unknown>[];
                          const structurePatch = (group.structure_patch as Record<string, unknown> | undefined) || {};
                          const nodeSwitches = ((structurePatch.node_switches as unknown[]) || []) as Record<string, unknown>[];
                          const hasChanges = Object.keys(override).length > 0 || nodePatches.length > 0 || nodeSwitches.length > 0;
                          if (!hasChanges) return <Text type="secondary">该组相对 Baseline 无配置差异。</Text>;
                          return (
                            <div className="autoresearch-group-config__content">
                              {Object.keys(override).length > 0 && (
                                <section>
                                  <Text strong>全局参数</Text>
                                  <div className="autoresearch-config-chip-list">
                                    {Object.entries(override).map(([key, value]) => (
                                      <span key={key}><b>{key}</b> = {JSON.stringify(value)}</span>
                                    ))}
                                  </div>
                                </section>
                              )}
                              {nodePatches.length > 0 && (
                                <section>
                                  <Text strong>节点参数</Text>
                                  {nodePatches.map((patch, patchIndex) => (
                                    <div className="autoresearch-node-patch" key={`${String(patch.node_id || patch.functionId || patchIndex)}-${patchIndex}`}>
                                      <Text code>{String(patch.functionId || patch.node_id || 'unknown')}</Text>
                                      <span>
                                        {Object.entries((patch.param_patch as Record<string, unknown> | undefined) || {})
                                          .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
                                          .join(' · ')}
                                      </span>
                                    </div>
                                  ))}
                                </section>
                              )}
                              {nodeSwitches.length > 0 && (
                                <section>
                                  <Text strong>节点开关</Text>
                                  <div className="autoresearch-config-chip-list">
                                    {nodeSwitches.map((item, switchIndex) => (
                                      <span key={`${String(item.node_id || item.functionId || switchIndex)}-${switchIndex}`}>
                                        <b>{String(item.functionId || item.node_id || 'unknown')}</b>
                                        {' '}{item.enabled ? '启用' : '停用'}
                                      </span>
                                    ))}
                                  </div>
                                </section>
                              )}
                            </div>
                          );
                        })(),
                      }]}
                    />
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="autoresearch-progress-groups is-single">
              <div className="autoresearch-progress-lane">
                <div className="autoresearch-progress-lane__head">
                  <div>
                    <strong>{currentPhase === 'baseline_warmup' ? 'Baseline 缓存预热' : '当前窗口回测'}</strong>
                    <span>{phaseLabels[currentPhase] || currentPhase}</span>
                  </div>
                  <div className="autoresearch-progress-lane__value">
                    <strong>{progressPercent({
                      windows_done: currentWindowDone,
                      windows_total: currentWindowTotal,
                    })}%</strong>
                    <span>{currentWindowTotal > 0 ? `${currentWindowDone}/${currentWindowTotal} 窗口` : '准备中'}</span>
                  </div>
                </div>
                <Progress
                  percent={progressPercent({
                    windows_done: currentWindowDone,
                    windows_total: currentWindowTotal,
                  })}
                  showInfo={false}
                  status="active"
                  strokeColor="#2563eb"
                />
                <Text type="secondary" ellipsis>
                  {String(currentLiveSummary.current_window || currentLiveProgress.current_window || '正在准备首个窗口')}
                </Text>
              </div>
            </div>
          )}
        </Card>
      )}

      <Drawer
        title="实验配置与历史运行"
        open={configDrawerOpen}
        onClose={() => setConfigDrawerOpen(false)}
        width="min(1060px, 96vw)"
        styles={{ body: { padding: 20, background: '#f8fafc' } }}
      >
      <div className="autoresearch-workspace">
      <div className="autoresearch-primary-column">{/* ── 左栏开始 ── */}

      <div style={{ marginBottom: 14 }}>
        <Typography.Title level={4} style={{ marginBottom: 2 }}>
          实验配置
        </Typography.Title>
        <Text type="secondary" style={{ fontSize: 13 }}>
          先锁定 Baseline 和时间窗，再设置本次研究的统一评测口径。
        </Text>
      </div>

      {/* production ref banner */}
      {productionSlot?.workflow_id && (
        <Alert
          type="info"
          style={{ marginBottom: 12 }}
          showIcon
          message={
            <span>
              当前生产模板：
              <Text code style={{ fontSize: 12 }}>{productionSlot.workflow_id as string}</Text>
              {productionSlot.updated_at && (
                <Text type="secondary" style={{ marginLeft: 8, fontSize: 11 }}>
                  {dayjs(productionSlot.updated_at as string).format('MM-DD HH:mm')} 更新
                </Text>
              )}
              <Button
                size="small"
                type="link"
                onClick={() =>
                  form.setFieldsValue({
                    baseline_workflow_id: productionSlot.workflow_id as string,
                  })
                }
              >
                填入 Baseline
              </Button>
            </span>
          }
        />
      )}

      {/* main form - 自动实验模式 */}
      <Card
        size="small"
        className="autoresearch-surface autoresearch-config-card"
        style={{ ...experimentSetupCardStyle, boxShadow: undefined, borderRadius: undefined }}
        styles={{
          body: {
            padding: 16,
            background: '#ffffff',
          },
        }}
      >
        <Form
          form={form}
          layout="vertical"
          onValuesChange={(_changed, allValues) => {
            try {
              localStorage.setItem(FORM_STORAGE_KEY, JSON.stringify(allValues));
            } catch { /* ignore */ }
          }}
          initialValues={{
            score_margin: 0,
            aggregate_method: 'mean',
            add_to_candidate_pool: true,
            auto_profile: 'general',
            auto_max_iterations: 20,
            auto_top_k: 10,
            auto_manual_gate: true,
            auto_full_automation: false,
            structure_profile_id: 'load_forecast_linear_pipeline_v1',
            preferred_model_operator_ids: [] as string[],
            skip_workflow_precheck: false,
            adv_xgb_eta_low_list: '',
            adv_xgb_eta_high_list: '',
            adv_xgb_depth_low_list: '',
            adv_xgb_depth_high_list: '',
            adv_xgb_subsample_low_list: '',
            adv_xgb_subsample_high_list: '',
            adv_xgb_lambda_low_list: '',
            adv_xgb_lambda_high_list: '',
            adv_xgb_min_child_low_list: '',
            adv_xgb_min_child_high_list: '',
            contract_backtest_mode: 'rolling_retrain',
            contract_train_days: 30,
            contract_time_granularity_min: 15,
            contract_apply_window_filter: true,
            contract_mask_target_values: true,
            contract_auto_tune_n_trials: 5,
          }}
        >
          {/* ═══ Baseline 选择（自动实验模式不需要 Challenger） ═══ */}
          <Card
            size="small"
            className="autoresearch-config-section"
            title={
              <Space size={8}>
                <Tag className="autoresearch-step-number">1</Tag>
                <span>基线模板与时间窗</span>
              </Space>
            }
            style={experimentSectionStyle}
            styles={{ header: experimentSectionHeaderStyle, body: { padding: 12 } }}
          >
            <Form.Item
              name="baseline_workflow_id"
              label="Baseline（基线模板）"
              rules={[{ required: true, message: '请选择 Baseline' }]}
              style={{ marginBottom: 12 }}
            >
              <Select
                showSearch
                loading={loadingWorkflows}
                placeholder="选择基线模板"
                optionFilterProp="label"
                options={workflows.map(w => ({ value: w.id, label: w.name }))}
              />
            </Form.Item>

            <Form.Item
              name="windows_text"
              label={
                <Space>
                  <span>比对时间窗</span>
                  <Button size="small" type="link" onClick={() => form.setFieldsValue({ windows_text: windowsToText(toMonthWindows(3)) })}>
                    近 3 月
                  </Button>
                  <Button size="small" type="link" onClick={() => form.setFieldsValue({ windows_text: windowsToText(toMonthWindows(6)) })}>
                    近 6 月
                  </Button>
                  <Button size="small" type="link" onClick={() => form.setFieldsValue({ windows_text: windowsToText(toMonthWindows(12)) })}>
                    近 12 月
                  </Button>
                </Space>
              }
              rules={[{ required: true, message: '请填写时间窗' }]}
              style={{ marginBottom: 0 }}
            >
              <Input.TextArea rows={3} placeholder={'2024-01-01~2024-01-31\n2024-02-01~2024-02-29'} style={{ fontFamily: 'monospace', fontSize: 12 }} />
            </Form.Item>
          </Card>

          {/* ═══ 数据集管理 ═══ */}
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.baseline_workflow_id !== cur.baseline_workflow_id}>
            {({ getFieldValue }) => (
              <DatasetPanel
                workflowId={getFieldValue('baseline_workflow_id')}
                onDatasetChanged={() => { /* 可选：刷新 workflow 信息 */ }}
              />
            )}
          </Form.Item>

          {/* ═══ 自动实验配置 ═══ */}
          <Card
            size="small"
            className="autoresearch-config-section"
            title={
              <Space size={8}>
                <Tag className="autoresearch-step-number">2</Tag>
                <span>实验配置</span>
              </Space>
            }
            style={experimentSectionStyle}
            styles={{ header: experimentSectionHeaderStyle, body: { padding: 12 } }}
          >
            <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
              固定使用滚动重训；下方参数同时控制评测口径和自动实验搜索策略。
            </Text>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '0 16px', marginBottom: 8 }}>
              <Form.Item name="contract_train_days" label="训练天数" style={{ marginBottom: 8 }}>
                <InputNumber min={1} max={365} placeholder="30" style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="contract_time_granularity_min" label="时间粒度" style={{ marginBottom: 8 }}>
                <Select
                  style={{ width: '100%' }}
                  options={[
                    { value: 60, label: '60 min' },
                    { value: 30, label: '30 min' },
                    { value: 15, label: '15 min' },
                  ]}
                />
              </Form.Item>
              <Form.Item name="contract_auto_tune_n_trials" label="调参轮数" style={{ marginBottom: 8 }}>
                <InputNumber min={1} max={100} placeholder="5" style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="auto_max_iterations" label="最大迭代轮数" style={{ marginBottom: 8 }}>
                <InputNumber min={1} max={200} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="auto_top_k" label="保留 Top K" style={{ marginBottom: 8 }}>
                <InputNumber min={1} max={100} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item
                name="auto_batch_size"
                label="每轮评估组数"
                tooltip="每轮采样多组配置并行评估，取最优。增大可提升搜索效率，但需要更多计算资源。"
                style={{ marginBottom: 8 }}
                initialValue={1}
              >
                <InputNumber min={1} max={5} style={{ width: '100%' }} placeholder="1（默认）" />
              </Form.Item>
              <Form.Item name="add_to_candidate_pool" label="写入候选池" valuePropName="checked" style={{ marginBottom: 8 }}>
                <Switch defaultChecked />
              </Form.Item>
              <Form.Item
                name="force_activate_layers"
                label="强制激活层"
                tooltip="跳过层饱和等待，直接激活选中的搜索层。适合短 run 验证非参数方向。"
                style={{ marginBottom: 8 }}
              >
                <Select
                  mode="multiple"
                  allowClear
                  placeholder="不选则按自然饱和推进"
                  style={{ width: '100%' }}
                  options={[
                    { value: 'feature', label: 'feature（特征）' },
                    { value: 'model', label: 'model（模型）' },
                    { value: 'data', label: 'data（数据）' },
                    { value: 'risk', label: 'risk（风险）' },
                  ]}
                />
              </Form.Item>
            </div>
            <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
              <Form.Item name="contract_apply_window_filter" label="窗口过滤" valuePropName="checked" style={{ marginBottom: 0 }}>
                <Switch />
              </Form.Item>
              <Form.Item name="contract_mask_target_values" label="遮蔽目标值" valuePropName="checked" style={{ marginBottom: 0 }}>
                <Switch />
              </Form.Item>
              <Form.Item name="auto_manual_gate" label="人工闸门" valuePropName="checked" style={{ marginBottom: 0 }}
                tooltip="开启后每轮结束会暂停，等你审核建议后再继续"
              >
                <Switch onChange={(checked) => { if (checked) form.setFieldsValue({ auto_full_automation: false }); }} />
              </Form.Item>
              <Form.Item name="auto_full_automation" label="全自动运行" valuePropName="checked" style={{ marginBottom: 0 }}
                tooltip="自动生成建议并应用，不等待人工审核"
              >
                <Switch onChange={(checked) => { if (checked) form.setFieldsValue({ auto_manual_gate: false }); }} />
              </Form.Item>
            </div>
          </Card>

          {/* 操作按钮 */}
          {/* 任务 25.3：注册表选择器 */}
          <div className="autoresearch-action-bar">
            <Space size={8} wrap>
              <Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>搜索空间注册表</Text>
              <Select
                style={{ width: 260 }}
                size="small"
                value={selectedRegistryId}
                onChange={setSelectedRegistryId}
                options={registryOptions.length > 0 ? registryOptions : [{ value: '', label: '自动匹配（推荐）' }]}
              />
            </Space>
            <Space wrap>
              <Button
                type="primary"
                size="large"
                className="autoresearch-primary-action"
                loading={autoResearching && !autoResearchStatus}
                onClick={onStartAutoResearch}
                disabled={isCommandRunActive}
              >
                启动自动实验
              </Button>
              {isCommandRunActive && (
                <Button danger onClick={onCancelAutoResearch}>
                  停止
                </Button>
              )}
              <Button
                onClick={onGenerateProposal}
                loading={proposalLoading}
                disabled={(() => {
                  const iterations = ((autoResearchStatus?.iterations as unknown[]) || []) as Record<string, unknown>[];
                  return iterations.filter(it => ['success', 'failed'].includes(String(it.status || ''))).length < 1;
                })()}
              >
                生成建议 Diff
              </Button>
              <Button
                type="dashed"
                onClick={() => {
                  form.setFieldsValue({
                    baseline_workflow_id: 'workflow-20260511-optimal-505',
                    windows_text: '2026-03-01~2026-03-08',
                    contract_backtest_mode: 'rolling_retrain',
                    contract_train_days: 30,
                    contract_time_granularity_min: 15,
                    contract_apply_window_filter: true,
                    contract_mask_target_values: true,
                    contract_auto_tune_n_trials: 15,
                    auto_max_iterations: 10,
                    auto_top_k: 5,
                    auto_batch_size: 1,
                    auto_full_automation: true,
                    auto_manual_gate: false,
                    add_to_candidate_pool: true,
                  });
                  message.info('已填充快速模式参数，点击"启动自动实验"开始');
                }}
              >
                填充快速模式
              </Button>
              <Button onClick={loadSummaries}>刷新模板</Button>
            </Space>
          </div>
        </Form>
      </Card>

      </div>{/* 配置栏结束 */}
      </div>{/* 工作区 grid 结束 */}
      </Drawer>

      <div className="autoresearch-cockpit-grid">
        <Card
          className="autoresearch-surface autoresearch-curve-card"
          title={
            <div>
              <Text strong>预测曲线对比</Text>
              <Text type="secondary" className="autoresearch-card-subtitle">
                {hasTrueBaselineCurve ? '实际值、同窗 Baseline 与当前 Challenger' : '实际值、历史参考与当前 Challenger'}
              </Text>
            </div>
          }
          extra={
            cockpitCurveRows.length > 0 ? (
              <Select
                size="small"
                value={challengerCurve?.iteration}
                onChange={(value) => setSelectedProfileIteration(Number(value))}
                options={[...cockpitCurveRows].reverse().map((row) => ({
                  value: row.iteration,
                  label: `第 ${row.iteration} 轮`,
                }))}
                style={{ width: 118 }}
              />
            ) : null
          }
        >
          {cockpitCurvePoints.length > 0 ? (
            <>
              <div className="autoresearch-curve-metrics">
                <div>
                  <span>{hasTrueBaselineCurve ? 'Baseline MAPE' : '首轮参考 MAPE'}</span>
                  <strong>{baselineCurveMape != null ? `${baselineCurveMape.toFixed(2)}%` : '暂无'}</strong>
                </div>
                <div>
                  <span>Challenger MAPE</span>
                  <strong>{challengerCurveMape != null ? `${challengerCurveMape.toFixed(2)}%` : '暂无'}</strong>
                </div>
                <div>
                  <span>相对改善</span>
                  <strong className={curveImprovement != null && curveImprovement > 0 ? 'is-positive' : ''}>
                    {curveImprovement != null ? `${curveImprovement > 0 ? '+' : ''}${curveImprovement.toFixed(2)}%` : '待比较'}
                  </strong>
                </div>
                <div>
                  <span>曲线来源</span>
                  <strong>
                    {hasTrueBaselineCurve
                      ? `同窗 Baseline → 第 ${challengerCurve?.iteration} 轮`
                      : historicalReferenceCurve
                        ? `第 ${historicalReferenceCurve.iteration} 轮参考 → 第 ${challengerCurve?.iteration} 轮`
                        : `第 ${challengerCurve?.iteration} 轮`}
                  </strong>
                </div>
              </div>
              {!hasBaselineReference && (
                <Alert
                  type="info"
                  showIcon
                  className="autoresearch-inline-alert"
                  message="当前历史数据没有 Baseline 预测序列；新 run 将保存并展示真实同窗 Baseline 曲线。"
                />
              )}
              <ReactECharts
                option={cockpitCurveOption}
                style={{ height: 410 }}
                notMerge
                lazyUpdate
              />
            </>
          ) : (
            <div className="autoresearch-empty-state">
              <div className="autoresearch-empty-state__graphic">
                <span />
                <span />
                <span />
              </div>
              <Typography.Title level={4}>等待首轮预测结果</Typography.Title>
              <Text type="secondary">
                启动自动实验后，这里会展示 Actual、Baseline 与 Challenger 的真实预测曲线。
              </Text>
              <Button type="primary" onClick={() => setConfigDrawerOpen(true)}>
                打开实验配置
              </Button>
            </div>
          )}
        </Card>

        <Card
          className="autoresearch-surface autoresearch-conclusion-card"
          title={
            <div>
              <Text strong>研究结论</Text>
              <Text type="secondary" className="autoresearch-card-subtitle">
                当前证据是否足以进入复验
              </Text>
            </div>
          }
        >
          <div className="autoresearch-decision">
            <Text className="autoresearch-decision__eyebrow">系统建议</Text>
            <Typography.Title level={3}>
              {topCandidate
                ? '已有成熟候选，建议进入多窗口复验'
                : isCommandRunActive
                  ? '继续观察，等待候选形成'
                  : '尚无可执行研究结论'}
            </Typography.Title>
            <Text type="secondary">
              {topCandidate
                ? '单次收益只作为候选信号，通过复验后才允许 Promote 为新基线。'
                : '运行至少 10 轮后，成熟候选会按 MAPE 改善进入下方工作区。'}
            </Text>
          </div>

          <div className="autoresearch-conclusion-kpis">
            <div>
              <span>强证据</span>
              <strong>{Number.isFinite(evidenceStrongCount) ? evidenceStrongCount : 0}</strong>
            </div>
            <div>
              <span>开放问题</span>
              <strong>{openQuestionCount}</strong>
            </div>
            <div>
              <span>活跃知识</span>
              <strong>{Number.isFinite(activeKnowledgeCount) ? activeKnowledgeCount : 0}</strong>
            </div>
          </div>

          <Collapse
            bordered={false}
            defaultActiveKey={['evidence']}
            className="autoresearch-conclusion-collapse"
            items={[
              {
                key: 'evidence',
                label: 'Evidence 证据',
                children: (
                  <div className="autoresearch-ledger">
                    <span>成熟候选</span><strong>{matureCandidatePool.length}</strong>
                    <span>待处理复验</span><strong>{queuedVerificationCount}</strong>
                    <span>曲线改善</span>
                    <strong>{curveImprovement != null ? `${curveImprovement.toFixed(2)}%` : '待比较'}</strong>
                  </div>
                ),
              },
              {
                key: 'question',
                label: 'Question 问题',
                children: (
                  openResearchQuestions.length > 0 ? (
                    <div className="autoresearch-question-list">
                      {openResearchQuestions.map((question, index) => {
                        const status = String(question.status || 'open').toLowerCase();
                        const proposalSource = String(
                          question.question_source
                          || question.proposal_source
                          || question.source
                          || 'rule',
                        ).toLowerCase();
                        const sourceLabel = proposalSource === 'glm'
                          ? 'GLM 生成'
                          : proposalSource.startsWith('glm_')
                            ? 'GLM 回退'
                            : '规则生成';
                        const sourceColor = proposalSource === 'glm'
                          ? 'purple'
                          : proposalSource.startsWith('glm_')
                            ? 'orange'
                            : 'default';
                        const direction = String(question.target_direction || question.target_layer || '');
                        const goal = String(question.next_experiment_goal || '');
                        const lastSeenIteration = Number(
                          question.last_seen_iteration
                          ?? question.iteration
                          ?? question.first_seen_iteration
                          ?? 0,
                        );
                        return (
                          <div
                            className="autoresearch-question-item"
                            key={String(question.question_key || `${String(question.question || '')}-${index}`)}
                          >
                            <div className="autoresearch-question-item__head">
                              <span className="autoresearch-question-item__index">{index + 1}</span>
                              <Text strong>{String(question.question || '未命名研究问题')}</Text>
                              <Tag color={status === 'testing' ? 'orange' : 'blue'}>
                                {status}
                              </Tag>
                              <Tag color={sourceColor}>
                                {sourceLabel}
                              </Tag>
                            </div>
                            <div className="autoresearch-question-item__meta">
                              {direction && <span>方向：{direction}</span>}
                              {lastSeenIteration > 0 && <span>最近出现：第 {lastSeenIteration} 轮</span>}
                            </div>
                            {goal && (
                              <Text type="secondary" className="autoresearch-question-item__goal">
                                下一步：{goal}
                              </Text>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <Text type="secondary">当前没有开放的研究问题。</Text>
                  )
                ),
              },
              {
                key: 'knowledge',
                label: 'Knowledge 知识',
                children: (
                  <Text type="secondary">
                    当前 run 已激活 {Number.isFinite(activeKnowledgeCount) ? activeKnowledgeCount : 0} 条可复用知识。
                  </Text>
                ),
              },
              {
                key: 'strategy',
                label: 'Strategy 策略',
                children: (
                  <Text type="secondary">
                    {autoRunInsights.latestMsg || '等待运行日志生成下一步策略。'}
                  </Text>
                ),
              },
            ]}
          />

          <div className="autoresearch-conclusion-actions">
            <Button
              type="primary"
              block
              disabled={!topCandidate}
              onClick={() => topCandidate && openVerificationModal(topCandidate)}
            >
              加入复验池
            </Button>
            <Button block onClick={openFullEvidence} disabled={!autoResearchStatus}>
              {showAdvancedDetails ? '定位完整证据' : '查看完整证据'}
            </Button>
          </div>
        </Card>
      </div>

      <Card className="autoresearch-surface autoresearch-workbench-card">
        <Tabs
          defaultActiveKey="runs"
          items={[
            {
              key: 'runs',
              label: `最近运行 ${durableAutoRuns.length}`,
              children: (
                <div className="autoresearch-recent-runs-panel">
                  <div className="autoresearch-tab-toolbar">
                    <Text type="secondary">查看、恢复或继续历史 AutoResearch run。</Text>
                    <Button size="small" onClick={() => void detectLatestAutoResearchRun(true)} loading={latestAutoRunLoading}>
                      检测最近几次
                    </Button>
                  </div>
                  {recentRunsContent}
                </div>
              ),
            },
            {
              key: 'candidates',
              label: `候选池 ${matureCandidatePool.length}`,
              children: (
                <Spin spinning={loadingPool}>
                  <div className="autoresearch-tab-toolbar">
                    <Text type="secondary">
                      仅显示来源 run 已完成不少于 10 轮的候选，按 MAPE 改善排序。
                    </Text>
                    <Space>
                      <Button size="small" onClick={loadPool}>刷新</Button>
                      <Button
                        size="small"
                        danger
                        onClick={async () => {
                          try {
                            const res = await baselineCompareApi.clearCandidatePool();
                            message.success(`已清空 ${res.deleted_count} 条记录`);
                            loadPool();
                          } catch {
                            message.error('清空失败');
                          }
                        }}
                      >
                        清空全部
                      </Button>
                    </Space>
                  </div>
                  <Table
                    dataSource={matureCandidatePool}
                    columns={poolColumns}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 8 }}
                    locale={{ emptyText: '暂无成熟候选' }}
                  />
                </Spin>
              ),
            },
            {
              key: 'verification',
              label: `复验池 ${verificationQueue.length}`,
              children: (
                <Spin spinning={loadingVerificationQueue}>
                  <div className="autoresearch-tab-toolbar">
                    <Text type="secondary">
                      独立资源池串行执行，多窗口通过后才允许 Promote。
                    </Text>
                    <Space>
                      <Button size="small" onClick={refreshVerificationAndPool}>刷新</Button>
                      <Button
                        size="small"
                        type="primary"
                        onClick={async () => {
                          try {
                            const res = await baselineCompareApi.startNextVerification();
                            if (res.started) message.success('已启动下一条复验');
                            else message.info(String(res.reason || '没有可启动的复验项'));
                            loadVerificationQueue();
                          } catch (error: unknown) {
                            message.error((error as Error).message || '启动复验失败');
                          }
                        }}
                      >
                        启动下一条
                      </Button>
                    </Space>
                  </div>
                  <Table
                    dataSource={verificationQueue}
                    rowKey="id"
                    size="small"
                    pagination={{ pageSize: 8 }}
                    locale={{ emptyText: '暂无复验任务' }}
                    columns={[
                      {
                        title: '复验 ID',
                        dataIndex: 'id',
                        width: 160,
                        render: (value: string) => <Text code>{value || '-'}</Text>,
                      },
                      {
                        title: '候选',
                        dataIndex: 'candidate_id',
                        width: 160,
                        render: (value: string) => <Text code>{value || '-'}</Text>,
                      },
                      {
                        title: '配置',
                        key: 'config',
                        render: (_: unknown, record: Record<string, unknown>) => verificationConfigSummary(record),
                      },
                      {
                        title: '状态',
                        dataIndex: 'status',
                        width: 100,
                        render: (value: string) => (
                          <Tag color={value === 'passed' ? 'green' : value === 'running' ? 'blue' : value === 'failed' ? 'red' : 'default'}>
                            {value || '-'}
                          </Tag>
                        ),
                      },
                      {
                        title: '进度',
                        key: 'progress',
                        width: 120,
                        render: (_: unknown, record: Record<string, unknown>) => {
                          const progress = (record.progress as Record<string, unknown> | undefined) || {};
                          const done = Number(progress.completed ?? progress.done ?? 0);
                          const total = Number(progress.total ?? 0);
                          return total > 0 ? `${done} / ${total}` : '-';
                        },
                      },
                    ]}
                  />
                </Spin>
              ),
            },
            {
              key: 'insights',
              label: `实验洞察 ${hypothesesTested}`,
              children: (
                <div className="autoresearch-insight-panel">
                  <div className="autoresearch-tab-toolbar">
                    <Text type="secondary">汇总当前 run 的假设验证结果和有效研究方向。</Text>
                    <Button size="small" onClick={openFullEvidence} disabled={!autoResearchStatus}>
                      查看完整洞察
                    </Button>
                  </div>
                  <div className="autoresearch-insight-kpis">
                    <div><span>已测试假设</span><strong>{hypothesesTested}</strong></div>
                    <div><span>成立</span><strong className="is-success">{hypothesesVerified}</strong></div>
                    <div><span>否证</span><strong className="is-danger">{hypothesesDisproved}</strong></div>
                    <div><span>有效方向</span><strong>{effectiveDirections.length}</strong></div>
                  </div>
                  <div className="autoresearch-insight-grid">
                    <section>
                      <Text strong>最近假设链路</Text>
                      <div className="autoresearch-insight-list">
                        {hypothesisChain.length > 0 ? hypothesisChain.slice().reverse().slice(0, 6).map((item, index) => {
                          const status = String(item.status || 'pending_verification');
                          return (
                            <div className="autoresearch-insight-row" key={`${String(item.proposal_id || index)}-${index}`}>
                              <Tag color={status === 'verified' ? 'green' : status === 'disproved' ? 'red' : 'blue'}>
                                {status === 'verified' ? '已成立' : status === 'disproved' ? '已否证' : '待验证'}
                              </Tag>
                              <div>
                                <Text>{String(item.hypothesis || '未记录假设内容')}</Text>
                                <Text type="secondary">
                                  {item.applied_iteration != null ? `应用于第 ${String(item.applied_iteration)} 轮` : '尚未应用'}
                                </Text>
                              </div>
                            </div>
                          );
                        }) : <div className="autoresearch-log-empty">暂无假设验证记录</div>}
                      </div>
                    </section>
                    <section>
                      <Text strong>方向结论</Text>
                      <div className="autoresearch-direction-group">
                        {effectiveDirections.slice(0, 4).map((item, index) => (
                          <div className="autoresearch-direction-item is-effective" key={`effective-${index}`}>
                            <Tag color="green">有效</Tag><Text>{item}</Text>
                          </div>
                        ))}
                        {ineffectiveDirections.slice().reverse().slice(0, 4).map((item, index) => (
                          <div className="autoresearch-direction-item" key={`ineffective-${index}`}>
                            <Tag color="red">已否证</Tag><Text>{item}</Text>
                          </div>
                        ))}
                        {effectiveDirections.length === 0 && ineffectiveDirections.length === 0 && (
                          <div className="autoresearch-log-empty">暂无方向结论</div>
                        )}
                      </div>
                    </section>
                  </div>
                </div>
              ),
            },
            {
              key: 'glm',
              label: `GLM 记录 ${glmCallHistory.length}`,
              children: (
                <div className="autoresearch-glm-panel">
                  <div className="autoresearch-tab-toolbar">
                    <Text type="secondary">
                      共 {glmCallHistory.length} 次记录，其中 {glmUsedCount} 次真实调用 GLM。
                    </Text>
                    <Button size="small" onClick={openFullEvidence} disabled={!autoResearchStatus}>
                      查看完整调用详情
                    </Button>
                  </div>
                  <div className="autoresearch-glm-list">
                    {glmCallHistory.length > 0 ? glmCallHistory.slice().reverse().slice(0, 10).map((record, index) => {
                      const meta = (record.glm_meta as Record<string, unknown> | undefined) || {};
                      const llmUsed = Boolean(meta.llm_used);
                      const applied = Boolean(record.applied);
                      return (
                        <div className="autoresearch-glm-row" key={`${String(record.iteration || index)}-${index}`}>
                          <div className="autoresearch-glm-row__status">
                            <Tag color="blue">第 {String(record.iteration || '-')} 轮</Tag>
                            <Tag color={llmUsed ? 'purple' : 'default'}>
                              {llmUsed ? 'GLM 已调用' : '规则回退'}
                            </Tag>
                            <Tag color={applied ? 'green' : 'orange'}>
                              {applied ? '已应用' : '未应用'}
                            </Tag>
                          </div>
                          <div className="autoresearch-glm-row__content">
                            <Text strong>{String(record.hypothesis || '未记录实验假设')}</Text>
                            <Text type="secondary">
                              模型 {String(meta.model || '-')} · 耗时 {Number(record.duration_s || 0).toFixed(2)}s
                              {' · '}候选 {String(meta.candidates_count ?? record.generated_count ?? 0)}
                              {' · '}记忆命中 {String(meta.memory_hit_count ?? 0)}
                            </Text>
                            {record.skip_apply_reason && (
                              <Text type="secondary">未应用原因：{formatGlmSkipReason(String(record.skip_apply_reason))}</Text>
                            )}
                          </div>
                        </div>
                      );
                    }) : <div className="autoresearch-log-empty">当前 run 暂无 GLM 调用记录</div>}
                  </div>
                </div>
              ),
            },
            {
              key: 'logs',
              label: `运行日志 ${latestRunLogs.length}`,
              children: (
                <div className="autoresearch-log-panel">
                  <div className="autoresearch-tab-toolbar">
                    <Text type="secondary">显示当前 run 最近 40 条日志。</Text>
                    <Button size="small" onClick={() => void detectLatestAutoResearchRun(true)}>
                      刷新运行
                    </Button>
                  </div>
                  {latestRunLogs.length > 0 ? latestRunLogs.map((log, index) => (
                    <div className="autoresearch-log-row" key={`${String(log.created_at || log.timestamp || '')}-${index}`}>
                      <Text type="secondary">
                        {String(log.created_at || log.timestamp || '').replace('T', ' ').slice(0, 19) || '--:--:--'}
                      </Text>
                      <Tag>{String(log.level || log.status || 'info')}</Tag>
                      <Text>{String(log.message || log.detail || '-')}</Text>
                    </div>
                  )) : (
                    <div className="autoresearch-log-empty">暂无运行日志</div>
                  )}
                </div>
              ),
            },
          ]}
        />
      </Card>

      {/* compare status */}
      {compareStatus && (
        <Card size="small" title="比对状态" style={{ marginBottom: 16 }}>
          <Descriptions size="small" column={3}>
            <Descriptions.Item label="状态">
              <Tag color={
                (compareStatus as Record<string, unknown>).status === 'success' ? 'green' :
                (compareStatus as Record<string, unknown>).status === 'failed' ? 'red' :
                (compareStatus as Record<string, unknown>).status === 'running' ? 'blue' : 'default'
              }>
                {(compareStatus as Record<string, unknown>).status as string}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="比对 ID">
              <Text code style={{ fontSize: 11 }}>{comparisonId}</Text>
            </Descriptions.Item>
          </Descriptions>
          {/* 临时调试：显示后端返回的原始字段 */}
          <details style={{ marginTop: 8, fontSize: 11, color: '#888' }}>
            <summary style={{ cursor: 'pointer' }}>查看原始状态数据（调试用）</summary>
            <pre style={{ fontSize: 10, maxHeight: 300, overflow: 'auto', background: '#f5f5f5', padding: 8 }}>
              {JSON.stringify(
                Object.fromEntries(
                  Object.entries(compareStatus as Record<string, unknown>)
                    .filter(([k]) => ['status', 'progress', 'live_summary', 'summary', 'logs', 'error'].includes(k))
                    .map(([k, v]) => [k, k === 'logs'
                      ? (v as unknown[])?.slice(-5)  // 显示最后5条日志
                      : v])
                ),
                null, 2
              )}
            </pre>
          </details>

          {/* 实时中间结果 */}
          {(() => {
            const st = compareStatus as Record<string, unknown>;
            const live = (st.live_summary ?? st.summary) as Record<string, unknown> | undefined;
            const winResults = (st.live_window_results ?? st.window_results) as Record<string, unknown>[] | undefined;
            const prog = st.progress as Record<string, unknown> | undefined;
            if (!live && !prog) return null;
            const done = live?.windows_done as number | undefined;
            const total = live?.windows_total as number | undefined;
            const adv = live?.score_advantage as number | null | undefined;
            const bScore = live?.aggregate_baseline_score as number | null | undefined;
            const cScore = live?.aggregate_challenger_score as number | null | undefined;
            const wins = live?.windows_challenger_better as number | undefined;
            const comparable = live?.windows_comparable as number | undefined;
            return (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 8, alignItems: 'center' }}>
                  {done !== undefined && total !== undefined ? (
                    <span style={{ fontSize: 13 }}>
                      进度：<Tag color="blue">{done} / {total} 窗口</Tag>
                      {live?.current_window && (
                        <Text type="secondary" style={{ fontSize: 11, marginLeft: 4 }}>
                          当前：{live.current_window as string}
                          {live.current_phase === 'challenger_running' && ' — Baseline ✓ 跑 Challenger...'}
                        </Text>
                      )}
                    </span>
                  ) : prog ? (
                    <span style={{ fontSize: 13, color: '#888' }}>
                      窗口 {prog.window_index as number}/{prog.window_total as number}，Challenger {prog.challenger_index as number}/{prog.challenger_total as number}
                    </span>
                  ) : null}
                  {bScore != null && <span style={{ fontSize: 13 }}>Baseline：<Tag color="geekblue">{Number(bScore).toFixed(4)}</Tag></span>}
                  {cScore != null && <span style={{ fontSize: 13 }}>Challenger：<Tag color="purple">{Number(cScore).toFixed(4)}</Tag></span>}
                  {adv != null && (
                    <span style={{ fontSize: 13 }}>
                      分差：<Tag color={Number(adv) > 0 ? 'green' : Number(adv) < 0 ? 'red' : 'default'}>
                        {Number(adv) > 0 ? '+' : ''}{Number(adv).toFixed(4)}
                      </Tag>
                    </span>
                  )}
                  {wins !== undefined && comparable !== undefined && comparable > 0 && (
                    <span style={{ fontSize: 13 }}>优胜窗：<Tag>{wins}/{comparable}</Tag></span>
                  )}
                </div>
                {Array.isArray(winResults) && winResults.length > 0 && (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                    <thead>
                      <tr style={{ background: '#fafafa', borderBottom: '1px solid #e8e8e8' }}>
                        <th style={{ padding: '4px 8px', textAlign: 'left' }}>时间窗</th>
                        <th style={{ padding: '4px 8px', textAlign: 'left' }}>Baseline 分</th>
                        <th style={{ padding: '4px 8px', textAlign: 'left' }}>Challenger 分</th>
                        <th style={{ padding: '4px 8px', textAlign: 'left' }}>分差</th>
                        <th style={{ padding: '4px 8px', textAlign: 'left' }}>SMAPE (B / C)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(winResults as Record<string, unknown>[]).map((w, i) => {
                        const bs = w.baseline_score as number | null | undefined;
                        const cs = w.challenger_score as number | null | undefined;
                        const diff = bs != null && cs != null ? Number(cs) - Number(bs) : null;
                        const bm = (w.baseline as Record<string, unknown> | undefined)?.avg_metrics as Record<string, unknown> | undefined;
                        const cm = (w.challenger as Record<string, unknown> | undefined)?.avg_metrics as Record<string, unknown> | undefined;
                        return (
                          <tr key={i} style={{ borderBottom: '1px solid #f0f0f0' }}>
                            <td style={{ padding: '4px 8px' }}>{String(w.start_date)} ~ {String(w.end_date)}</td>
                            <td style={{ padding: '4px 8px' }}><Tag color="geekblue">{bs != null ? Number(bs).toFixed(4) : '—'}</Tag></td>
                            <td style={{ padding: '4px 8px' }}><Tag color="purple">{cs != null ? Number(cs).toFixed(4) : '—'}</Tag></td>
                            <td style={{ padding: '4px 8px' }}>
                              {diff != null ? (
                                <Tag color={diff > 0 ? 'green' : diff < 0 ? 'red' : 'default'}>
                                  {diff > 0 ? '+' : ''}{diff.toFixed(4)}
                                </Tag>
                              ) : '—'}
                            </td>
                            <td style={{ padding: '4px 8px', color: '#888' }}>
                              {bm?.avg_smape != null ? Number(bm.avg_smape).toFixed(2) : '—'}
                              {' / '}
                              {cm?.avg_smape != null ? Number(cm.avg_smape).toFixed(2) : '—'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })()}
        </Card>
      )}

      <div ref={advancedDetailsAnchorRef} className="autoresearch-advanced-anchor" />
      {showAdvancedDetails && autoResearchStatus && (
        <Card
          size="small"
          title={
            <Space size={8} wrap>
              <span style={{ fontSize: 14, fontWeight: 600, color: uiInk, letterSpacing: -0.3 }}>AutoResearch 控制台</span>
              <StatusPill value={String(autoResearchStatus.status || 'unknown')} />
              {['interrupted', 'failed', 'cancelled'].includes(String(autoResearchStatus.status || '').toLowerCase()) && autoResearchStatus.recoverable !== false && (
                <Button
                  size="small"
                  type="primary"
                  onClick={async () => {
                    if (!autoResearchRunId) return;
                    try {
                      const res = await baselineCompareApi.resumeAutoResearch(autoResearchRunId);
                      message.success(`已从第 ${(res as Record<string, unknown>).resume_from_iteration} 轮恢复`);
                      setAutoResearching(true);
                      startAutoPolling(autoResearchRunId);
                    } catch (err: unknown) {
                      message.error(`恢复失败: ${(err as Error)?.message || '未知错误'}`);
                    }
                  }}
                >
                  继续训练
                </Button>
              )}
            </Space>
          }
          style={autoResearchPanelStyle}
          extra={
            <Button
              type="primary"
              ghost
              size="small"
              onClick={onOpenStructureCompare}
              loading={structureCompareLoading}
            >
              Baseline / Challenger 全量对照
            </Button>
          }
        >
          {(() => {
            const p = (autoResearchStatus.progress as Record<string, unknown> | undefined) || {};
            const i = Number(p.iteration ?? 0);
            const t = Number(p.total_iterations ?? 0);
            const cfg = (autoResearchStatus.compare_config as Record<string, unknown> | undefined) || {};
            const auto = Boolean(cfg.auto_full_automation);
            const gate = Boolean(cfg.manual_gate);
            const gen = Boolean(cfg.auto_generate_proposal);
            const apply = Boolean(cfg.auto_apply_recommended);
            const risk = String(cfg.auto_apply_risk_level_max || '-');
            const align = (autoResearchStatus.config_alignment as Record<string, unknown> | undefined) || {};
            const checked = Boolean(align.checked);
            const matched = Boolean(align.matched);
            const mismatches = ((align.mismatches as unknown[]) || []) as Record<string, unknown>[];
            const ssMismatches = ((align.search_space_mismatches as unknown[]) || []) as Record<string, unknown>[];
            const activeLayers = (autoResearchStatus as Record<string, unknown>).active_layers as string[] | undefined;
            const registryId = (autoResearchStatus as Record<string, unknown>).registry_id as string | undefined;
            const searchPhase = String((autoResearchStatus as Record<string, unknown>).phase || '');
            const latestAuto = (autoResearchStatus.latest_auto_proposal as Record<string, unknown> | undefined) || {};
            const glm = (latestAuto.glm_meta as Record<string, unknown> | undefined) || {};
            const recId = String(latestAuto.recommended_proposal_id || '');
            const appliedId = String(autoResearchStatus.latest_applied_proposal_id || '');
            const justApplied = recId && appliedId && recId === appliedId;
            const allLayers = ['training', 'feature', 'model', 'data'];
            const layerLabels: Record<string, string> = {
              training: '训练层',
              feature: '特征层',
              model: '模型层',
              data: '数据层',
            };
            return (
              <Card size="small" style={autoResearchOverviewStyle} styles={{ body: { padding: 12 } }}>
                <div style={{ marginBottom: 10 }}>
                  {renderAutoResearchIterationProgress(autoResearchStatus, {
                    width: '100%',
                    size: 'default',
                  })}
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                  {/* 核心状态行：轮次 + run_id + 阶段 + 模式 */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, alignItems: 'center', fontSize: 12 }}>
                    <span style={{ fontWeight: 600, color: uiInk }}>轮次 {i}/{t}</span>
                    <Text code style={{ fontSize: 11 }}>{autoResearchRunId}</Text>
                    <StatusPill value={autoRunInsights.phase === 'running_backtest' ? 'running' : autoRunInsights.phase === 'finished' ? 'success' : autoRunInsights.phase === 'failed' ? 'failed' : autoRunInsights.phase || ''} />
                    <span style={{ color: uiMuted }}>{autoRunInsights.phaseText}</span>
                    <span style={{ color: auto ? uiGood : uiMuted }}>{auto ? '全自动' : '半自动'}</span>
                    {checked && (
                      <span style={{ color: matched ? uiGood : uiBad }}>{matched ? '✓ 参数对齐' : '✗ 参数差异'}</span>
                    )}
                  </div>
                  <Button size="small" onClick={onRunSelfcheck} loading={selfcheckLoading}>
                    一键自检
                  </Button>
                </div>
                {/* 配置详情：分两行，label-value 格式 */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 10, fontSize: 12 }}>
                  <span><span style={{ color: uiLabel }}>注册表</span> <span style={{ color: registryId ? uiAccent : uiMuted }}>{registryId || '未启用'}</span></span>
                  {registryId && activeLayers && (
                    <span>
                      <span style={{ color: uiLabel }}>激活层</span>{' '}
                      {allLayers.map((layer) => (
                        <span key={layer} style={{ marginRight: 6, color: activeLayers.includes(layer) ? uiGood : uiLabel }}>
                          {layerLabels[layer] || layer}{activeLayers.includes(layer) ? ' ●' : ' ○'}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, marginTop: 6, fontSize: 12 }}>
                  <span><span style={{ color: uiLabel }}>gate</span> <span style={{ color: gate ? uiWarn : uiGood }}>{gate ? '人工' : '自动'}</span></span>
                  <span><span style={{ color: uiLabel }}>生成</span> {String(gen)}</span>
                  <span><span style={{ color: uiLabel }}>应用</span> {String(apply)}</span>
                  <span><span style={{ color: uiLabel }}>risk_max</span> {risk}</span>
                  <span><span style={{ color: uiLabel }}>GLM</span> {String(glm.candidates_count ?? 0)}</span>
                  <span><span style={{ color: uiLabel }}>记忆</span> {String(glm.memory_hit_count ?? 0)}</span>
                </div>
                {!checked ? null : matched ? (
                  <div style={{ marginTop: 8 }}>
                    <Text style={{ fontSize: 12, color: uiMuted }}>
                      前端提交的关键运行参数与后端实际生效参数一致。
                    </Text>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                    {[...mismatches, ...ssMismatches].map((m, idx) => (
                      <Text key={idx} code style={{ fontSize: 11, color: uiBad }}>
                        {String(m.key)}: {String(m.expected)} → {String(m.effective)}
                      </Text>
                    ))}
                  </div>
                )}
              </Card>
            );
          })()}
          {(() => {
            const directionLabels: Record<string, string> = {
              parameter: '参数方向',
              feature: '特征方向',
              model: '模型方向',
              data: '数据方向',
              risk: '风险探索',
            };
            const statusColor: Record<string, string> = {
              success: 'green',
              running: 'blue',
              failed: 'red',
              error: 'red',
              cancelled: 'orange',
              interrupted: 'orange',
              testing: 'orange',
              open: 'blue',
              resolved: 'green',
              stale: 'default',
              candidate: 'orange',
              active: 'green',
              conflicted: 'red',
              rejected: 'red',
            };
            const labelDirection = (value: unknown) => {
              const raw = String(value || '').trim();
              return raw ? `${directionLabels[raw] || raw} (${raw})` : '-';
            };
            const researchState = ((autoResearchStatus as Record<string, unknown>).research_state as Record<string, unknown> | undefined) || {};
            const health = ((autoResearchStatus as Record<string, unknown>).exploration_health as Record<string, unknown> | undefined) || {};
            const coverage = (health.direction_coverage as Record<string, unknown> | undefined) || {};
            const evidenceSummary = ((autoResearchStatus as Record<string, unknown>).evidence_summary as Record<string, unknown> | undefined) || {};
            const evidenceRows = (((autoResearchStatus as Record<string, unknown>).evidence_records as unknown[] | undefined) || []) as Record<string, unknown>[];
            const latestEvidence = evidenceRows.length > 0 ? evidenceRows[evidenceRows.length - 1] : {};
            const currentRunKnowledgeCounts = evidenceRows.reduce((acc, row) => {
              const strength = String(row.evidence_strength || 'insufficient_evidence');
              if (strength === 'multi_window_confirmed') acc.active += 1;
              else if (strength === 'single_window_positive') acc.candidate += 1;
              else if (strength === 'multi_window_rejected' || strength === 'single_window_negative') acc.rejected += 1;
              else acc.insufficient += 1;
              return acc;
            }, { active: 0, candidate: 0, rejected: 0, insufficient: 0 });
            const rawQuestions = (((autoResearchStatus as Record<string, unknown>).research_questions as unknown[] | undefined) || []) as Record<string, unknown>[];
            const questionGeneration = ((autoResearchStatus as Record<string, unknown>).research_question_generation as Record<string, unknown> | undefined) || {};
            const glmRuntime = ((questionGeneration.glm_runtime as Record<string, unknown> | undefined)
              || ((autoResearchStatus as Record<string, unknown>).glm_questioner_runtime as Record<string, unknown> | undefined)
              || {});
            const questions = Array.from(rawQuestions.reduce<Map<string, Record<string, unknown>>>((acc, q) => {
              const key = String(q.question_key || `${String(q.question || '')}::${String(q.next_experiment_goal || '')}`);
              acc.set(key, { ...(acc.get(key) || {}), ...q });
              return acc;
            }, new Map()).values());
            const questionStatusRank = (q: Record<string, unknown>) => {
              const status = String(q.status || (q.recurring ? 'testing' : 'open'));
              if (status === 'testing') return 4;
              if (status === 'open') return 3;
              if (status === 'resolved') return 2;
              if (status === 'stale') return 1;
              return 0;
            };
            const questionKey = (q: Record<string, unknown>) => String(q.question_key || `${String(q.question || '')}::${String(q.next_experiment_goal || '')}`);
            const questionIterationValue = (q: Record<string, unknown>) => Number(q.last_seen_iteration ?? q.first_seen_iteration ?? q.iteration ?? 0);
            const latestQuestion = [...questions].sort((a, b) => (
              questionStatusRank(b) - questionStatusRank(a)
              || questionIterationValue(b) - questionIterationValue(a)
            ))[0] || {};
            const latestQuestionKey = questionKey(latestQuestion);
            const historyQuestions = questions
              .filter((q) => questionKey(q) !== latestQuestionKey)
              .sort((a, b) => questionIterationValue(b) - questionIterationValue(a))
              .slice(0, 8);
            const knowledge = ((autoResearchStatus as Record<string, unknown>).knowledge_governance as Record<string, unknown> | undefined) || {};
            const knowledgeCounts = (knowledge.status_counts as Record<string, unknown> | undefined) || {};
            const latestGroups = (((autoResearchStatus as Record<string, unknown>).latest_batch_groups as unknown[] | undefined) || []) as Record<string, unknown>[];
            const batchStatus = ((autoResearchStatus as Record<string, unknown>).batch_eval_status as Record<string, unknown> | undefined) || {};
            const runningGroups = ((batchStatus.groups as unknown[] | undefined) || []) as Record<string, unknown>[];
            const groupRows = latestGroups.length > 0 ? latestGroups : runningGroups;
            const bestGroup = groupRows.find((group) => Boolean(group.is_best)) || groupRows[0] || {};
            const progress = (autoResearchStatus.progress as Record<string, unknown> | undefined) || {};
            const iteration = bestGroup.iteration_no ?? bestGroup.iteration ?? progress.iteration ?? autoResearchStatus.current_iteration;
            const groupIdx = bestGroup.group_idx ?? bestGroup.group_index ?? bestGroup.group ?? '-';
            const changedVariables = Array.isArray(latestEvidence.changed_variables)
              ? latestEvidence.changed_variables
              : Array.isArray(bestGroup.changed_variables)
                ? bestGroup.changed_variables
                : [];
            const evidenceStrength = String(latestEvidence.evidence_strength || evidenceSummary.latest_strength || 'insufficient_evidence');
            const needsConfirmation = Boolean(
              latestEvidence.needs_multi_window_confirmation
              ?? latestEvidence.needs_confirmation
              ?? Number(evidenceSummary.needs_multi_window_confirmation || 0) > 0,
            );
            const improvement = latestEvidence.mape_improvement ?? bestGroup.mape_improvement ?? bestGroup.score_advantage;
            const windowsTotal = Number(latestEvidence.windows_total ?? evidenceSummary.windows_total ?? 0);
            const windowsSuccess = Number(latestEvidence.windows_success ?? evidenceSummary.windows_success ?? 0);
            const hasImprovement = improvement != null && Number.isFinite(Number(improvement));
            const rawCandidateClaim = latestEvidence.knowledge_claim
              ?? latestEvidence.claim
              ?? bestGroup.knowledge_claim
              ?? bestGroup.claim;
            const candidateKnowledgeText = rawCandidateClaim
              ? String(rawCandidateClaim)
              : changedVariables.length > 0
                ? `本轮候选结论：${labelDirection(bestGroup.target_direction || latestEvidence.target_direction)} 中 ${changedVariables.slice(0, 3).map(String).join('、')} 的改动，MAPE 变化 ${hasImprovement ? Number(improvement).toFixed(4) : '未知'}。`
                : `本轮候选结论：${labelDirection(bestGroup.target_direction || latestEvidence.target_direction)} 的实验结果，尚未形成明确知识声明。`;
            const evidenceIssue = evidenceStrength === 'insufficient_evidence'
              ? windowsTotal <= 0
                ? hasImprovement
                  ? '不足原因：只有 MAPE 提升值，但缺少对应回测窗口统计，不能确认这条结果来自有效窗口。'
                  : '不足原因：缺少可用的回测窗口统计和收益结果。'
                : windowsSuccess <= 0
                  ? '不足原因：有回测窗口记录，但没有成功窗口，不能作为有效证据。'
                  : '不足原因：当前结果未满足证据契约，暂不能升级为可沉淀知识。'
              : needsConfirmation
                ? '证据说明：当前仍需要复验，不能直接升级为高置信知识。'
                : '';
            const evidenceSentence = evidenceStrength === 'multi_window_confirmed'
              ? '当前实验结论已多窗口确认，可以作为有效证据。'
              : evidenceStrength === 'single_window_positive'
                ? '当前实验结论是单窗口正收益，需要复验。'
                : evidenceStrength === 'single_window_negative'
                  ? '当前实验结论是单窗口负收益，暂不沉淀为知识。'
                  : '当前实验结论证据不足，不能沉淀为知识。';
            const knowledgeSentence = currentRunKnowledgeCounts.active > 0
              ? `当前 run 已形成 ${currentRunKnowledgeCounts.active} 条有效知识。`
              : currentRunKnowledgeCounts.candidate > 0
                ? `当前 run 暂无有效知识，有 ${currentRunKnowledgeCounts.candidate} 条候选知识等待复验。`
                : '当前 run 暂无有效知识，等待多窗口确认。';
            const knowledgeStatusLabels: Record<string, string> = {
              candidate: '知识库候选知识',
              active: '知识库有效知识',
              conflicted: '知识库冲突知识',
              stale: '知识库过时知识',
              rejected: '知识库已拒绝知识',
            };
            const knowledgeStatusDescriptions: Record<string, string> = {
              candidate: 'candidate：知识库里的候选知识，已有证据支持，但通常还需要复验，默认不作为高置信结论。',
              active: 'active：知识库里的有效知识，已通过证据门控，当前可优先注入后续研究；不代表本轮 run 新产生。',
              conflicted: 'conflicted：知识库里的冲突知识，同时存在支持和反证，应该转成研究问题继续验证。',
              stale: 'stale：知识库里的过时知识，较久未被验证或置信度下降，只能作为弱参考。',
              rejected: 'rejected：知识库里被拒绝的知识，被证据否定或质量不足，不应指导后续采样。',
            };
            const cardGridStyle: React.CSSProperties = {
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
              gap: 16,
              marginBottom: 16,
            };
            const compactCardStyle: React.CSSProperties = {
              border: '1px solid #e8eef5',
              borderRadius: 10,
              background: '#fff',
              boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)',
              padding: 4,
            };
            const evidenceCardStyle: React.CSSProperties = {
              ...compactCardStyle,
              gridColumn: 'span 2',
              minWidth: 0,
            };
            const wrapTagStyle: React.CSSProperties = {
              whiteSpace: 'normal',
              height: 'auto',
              lineHeight: 1.45,
              maxWidth: '100%',
              overflowWrap: 'anywhere',
            };
            return (
              <Card
                size="small"
                style={autoResearchMutedCardStyle}
                title={
                  <span style={{ fontSize: 14, fontWeight: 600, color: uiInk, letterSpacing: -0.3 }}>
                    研究驾驶舱
                  </span>
                }
              >
                <div style={cardGridStyle}>
                  <Card size="small" style={compactCardStyle} title={<span style={{ fontSize: 13, fontWeight: 600, color: uiInk }}>Experiment</span>}>
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <div style={kvGridStyle}>
                        <span style={kvLabelStyle}>当前轮 / 组</span>
                        <Text style={{ fontSize: 12 }}>
                          第 {String(iteration ?? '-')} 轮 · 第 {String(groupIdx)} 组
                        </Text>
                        <span style={kvLabelStyle}>状态</span>
                        <StatusPill value={String(bestGroup.status || autoResearchStatus.status || '-')} />
                        <span style={kvLabelStyle}>研究方向</span>
                        <Text style={{ fontSize: 12 }}>
                          {labelDirection(bestGroup.target_direction || latestEvidence.target_direction)}
                        </Text>
                      </div>
                      <div>
                        <div style={kvLabelStyle}>本轮改动</div>
                        <Text style={{ fontSize: 12, color: uiMuted, lineHeight: 1.5 }}>
                          {changedVariables.length > 0 ? changedVariables.slice(0, 4).map(String).join('、') : '等待本轮结果'}
                        </Text>
                      </div>
                      {(bestGroup.failure_reason || latestEvidence.failure_reason || bestGroup.error) && (
                        <Text style={{ fontSize: 12, color: uiBad }}>
                          失败原因：{String(bestGroup.failure_reason || latestEvidence.failure_reason || bestGroup.error)}
                        </Text>
                      )}
                      <Collapse
                        ghost
                        size="small"
                        items={[{
                          key: 'experiment-detail',
                          label: '查看技术详情',
                          children: (
                            <Space direction="vertical" size={8} style={{ width: '100%' }}>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                这部分用于排查和追踪实验，不是普通结论字段。
                              </Text>
                              <Descriptions size="small" column={1} bordered>
                                <Descriptions.Item label="target_layer（实际改动层）">
                                  {String(bestGroup.target_layer || latestEvidence.target_layer || '-')}
                                </Descriptions.Item>
                                <Descriptions.Item label="patch_fingerprint（补丁指纹）">
                                  <Text code style={{ whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                                    {String(bestGroup.patch_fingerprint || latestEvidence.patch_fingerprint || '-')}
                                  </Text>
                                </Descriptions.Item>
                                <Descriptions.Item label="group（原始分组结果）">
                                  后端返回的本组实验原始 JSON，用于定位字段来源、失败原因和参数覆盖。
                                </Descriptions.Item>
                              </Descriptions>
                              <Collapse
                                ghost
                                size="small"
                                items={[{
                                  key: 'experiment-raw-json',
                                  label: '查看原始 JSON',
                                  children: (
                                    <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                      {JSON.stringify({
                                        target_layer: bestGroup.target_layer || latestEvidence.target_layer,
                                        patch_fingerprint: bestGroup.patch_fingerprint || latestEvidence.patch_fingerprint,
                                        group: bestGroup,
                                      }, null, 2)}
                                    </pre>
                                  ),
                                }]}
                              />
                            </Space>
                          ),
                        }]}
                      />
                    </Space>
                  </Card>

                  <Card size="small" style={evidenceCardStyle} title={<span style={{ fontSize: 13, fontWeight: 600, color: uiInk }}>Evidence</span>}>
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Text strong style={{ color: uiInk }}>{evidenceSentence}</Text>
                      <Text style={{ fontSize: 12, color: uiMuted }}>
                        待沉淀对象：{candidateKnowledgeText}
                      </Text>
                      {evidenceIssue && (
                        <Text style={{ fontSize: 12, color: evidenceStrength === 'insufficient_evidence' ? uiWarn : uiMuted }}>
                          {evidenceIssue}
                        </Text>
                      )}
                      <div style={kvGridStyle}>
                        <span style={kvLabelStyle}>窗口</span>
                        <Text style={{ fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
                          成功 {String(latestEvidence.windows_success ?? evidenceSummary.windows_success ?? '-')}
                          {' / '}
                          共 {String(latestEvidence.windows_total ?? evidenceSummary.windows_total ?? '-')}
                        </Text>
                        <span style={kvLabelStyle}>MAPE 提升</span>
                        <Text
                          style={{
                            fontSize: 12,
                            fontVariantNumeric: 'tabular-nums',
                            color: Number(improvement || 0) > 0 ? uiGood : Number(improvement || 0) < 0 ? uiBad : uiMuted,
                            fontWeight: 600,
                          }}
                        >
                          {improvement != null ? (Number(improvement) > 0 ? '+' : '') + Number(improvement).toFixed(4) : '-'}
                        </Text>
                        <span style={kvLabelStyle}>是否需复验</span>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: uiInk }}>
                          <span style={{ width: 7, height: 7, borderRadius: '50%', background: needsConfirmation ? uiWarn : uiGood, display: 'inline-block' }} />
                          {needsConfirmation ? '需要多窗口复验' : '暂不需要'}
                        </span>
                        <span style={kvLabelStyle}>证据强度</span>
                        <Text style={{ fontSize: 12, color: uiMuted }}>{evidenceStrength}</Text>
                      </div>
                    </Space>
                  </Card>

                  <Card size="small" style={compactCardStyle} title={<span style={{ fontSize: 13, fontWeight: 600, color: uiInk }}>Question</span>}>
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      {latestQuestion.question ? (
                        <>
                          {/* 问题本体提为主体 */}
                          <div>
                            <div style={kvLabelStyle}>当前研究问题</div>
                            <Text strong style={{ color: uiInk, display: 'block', marginTop: 3, lineHeight: 1.5 }}>
                              {String(latestQuestion.question)}
                            </Text>
                          </div>
                          <div style={kvGridStyle}>
                            <span style={kvLabelStyle}>状态</span>
                            <StatusPill value={String(latestQuestion.status || 'open')} />
                            <span style={kvLabelStyle}>来源</span>
                            <Text style={{ fontSize: 12 }}>
                              {String(latestQuestion.proposal_source || latestQuestion.source || 'rule')}
                              {questionGeneration.llm_used ? ' · GLM' : ''}
                            </Text>
                            <span style={kvLabelStyle}>证据数 / 历史问题</span>
                            <Text style={{ fontSize: 12, fontVariantNumeric: 'tabular-nums' }}>
                              {String(latestQuestion.evidence_count ?? 0)} · {historyQuestions.length}
                            </Text>
                            <span style={kvLabelStyle}>下一步验证</span>
                            <Text style={{ fontSize: 12, color: uiMuted }}>
                              {String(latestQuestion.next_experiment_goal || '-')}
                            </Text>
                          </div>
                          {!questionGeneration.llm_used && questionGeneration.fallback_reason ? (
                            <Text style={{ fontSize: 12, color: uiMuted }}>
                              GLM Questioner 未参与：{String(questionGeneration.fallback_reason)}
                            </Text>
                          ) : null}
                          {!questionGeneration.llm_used && glmRuntime.disabled_reason ? (
                            <Text style={{ fontSize: 12, color: uiWarn }}>
                              运行时诊断：{String(glmRuntime.disabled_reason)}
                            </Text>
                          ) : null}
                          <Collapse
                            ghost
                            size="small"
                            items={[
                              {
                                key: 'question-history',
                                label: `查看历史问题（${historyQuestions.length}）`,
                                children: historyQuestions.length > 0 ? (
                                  <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                    {historyQuestions.map((q, idx) => (
                                      <div
                                        key={`${questionKey(q)}-${idx}`}
                                        style={{ border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, background: '#fff' }}
                                      >
                                        <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                          <Space wrap size={[6, 6]}>
                                            <Tag>第 {String(q.last_seen_iteration ?? q.first_seen_iteration ?? q.iteration ?? '-')} 轮</Tag>
                                            <Tag color={statusColor[String(q.status || 'open')] || 'blue'}>{String(q.status || 'open')}</Tag>
                                            <Tag>证据 {String(q.evidence_count ?? 0)}</Tag>
                                            <Tag>来源 {String(q.proposal_source || q.source || 'rule')}</Tag>
                                          </Space>
                                          <Text>{String(q.question || '-')}</Text>
                                          <Text type="secondary" style={{ fontSize: 12 }}>
                                            下一步：{String(q.next_experiment_goal || '-')}
                                          </Text>
                                        </Space>
                                      </div>
                                    ))}
                                  </Space>
                                ) : (
                                  <Text type="secondary">暂无历史问题。</Text>
                                ),
                              },
                              {
                                key: 'question-detail',
                                label: '查看当前问题详情字段',
                                children: (
                                  <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                    {JSON.stringify({
                                      candidate_causes: latestQuestion.candidate_causes,
                                      evidence_refs: latestQuestion.evidence_refs || latestQuestion.evidence,
                                      expected_patch_intent: latestQuestion.expected_patch_intent,
                                    }, null, 2)}
                                  </pre>
                                ),
                              },
                            ]}
                          />
                        </>
                      ) : (
                        <Text type="secondary">第 1 轮完成后会显示系统正在研究的问题。</Text>
                      )}
                    </Space>
                  </Card>

                  <Card size="small" style={compactCardStyle} title={<span style={{ fontSize: 13, fontWeight: 600, color: uiInk }}>Knowledge</span>}>
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                      <Text strong style={{ color: uiInk }}>{knowledgeSentence}</Text>

                      {/* 当前 run 统计：用语义色小圆点 + 数字对齐 */}
                      <div>
                        <div style={sectionLabelStyle}>当前 run 知识产出</div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'auto auto 1fr', rowGap: 5, columnGap: 10, fontSize: 12, alignItems: 'center' }}>
                          <span style={{ width: 7, height: 7, borderRadius: '50%', background: uiGood, display: 'inline-block' }} />
                          <Text style={{ fontVariantNumeric: 'tabular-nums', minWidth: 20, textAlign: 'left' }}>{currentRunKnowledgeCounts.active}</Text>
                          <Text style={{ color: uiMuted }}>有效知识（多窗口确认）</Text>
                          <span style={{ width: 7, height: 7, borderRadius: '50%', background: uiWarn, display: 'inline-block' }} />
                          <Text style={{ fontVariantNumeric: 'tabular-nums', minWidth: 20, textAlign: 'left' }}>{currentRunKnowledgeCounts.candidate}</Text>
                          <Text style={{ color: uiMuted }}>候选知识（待复验）</Text>
                          <span style={{ width: 7, height: 7, borderRadius: '50%', background: uiBad, display: 'inline-block' }} />
                          <Text style={{ fontVariantNumeric: 'tabular-nums', minWidth: 20, textAlign: 'left' }}>{currentRunKnowledgeCounts.rejected}</Text>
                          <Text style={{ color: uiMuted }}>负向 / 拒绝</Text>
                          <span style={{ width: 7, height: 7, borderRadius: '50%', background: uiLabel, display: 'inline-block' }} />
                          <Text style={{ fontVariantNumeric: 'tabular-nums', minWidth: 20, textAlign: 'left' }}>{currentRunKnowledgeCounts.insufficient}</Text>
                          <Text style={{ color: uiMuted }}>证据不足</Text>
                        </div>
                      </div>

                      {/* 知识库可注入 */}
                      <div>
                        <div style={sectionLabelStyle}>知识库可注入候选</div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'auto auto 1fr', rowGap: 5, columnGap: 10, fontSize: 12, alignItems: 'center' }}>
                          {['active', 'candidate', 'conflicted', 'stale', 'rejected'].map((key) => {
                            const dotColor = key === 'active' ? uiGood : key === 'candidate' ? uiWarn : key === 'conflicted' ? uiBad : uiLabel;
                            return (
                              <React.Fragment key={key}>
                                <span style={{ width: 7, height: 7, borderRadius: '50%', background: dotColor, display: 'inline-block' }} />
                                <Text style={{ fontVariantNumeric: 'tabular-nums', minWidth: 20, textAlign: 'left' }}>{String(knowledgeCounts[key] ?? 0)}</Text>
                                <Text style={{ color: uiMuted }}>{knowledgeStatusLabels[key]}</Text>
                              </React.Fragment>
                            );
                          })}
                        </div>
                      </div>

                      <Collapse
                        ghost
                        size="small"
                        items={[{
                          key: 'knowledge-detail',
                          label: '查看知识治理摘要和字段说明',
                          children: (
                            <Space direction="vertical" size={8} style={{ width: '100%' }}>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                摘要里的 run_id 是当前页面所属 run；status_counts 来自知识库可注入候选，不表示这些知识都由当前 run 产生。
                              </Text>
                              <Space direction="vertical" size={4}>
                                {['candidate', 'active', 'conflicted', 'stale', 'rejected'].map((key) => (
                                  <Text key={key} type="secondary" style={{ fontSize: 12 }}>
                                    {knowledgeStatusDescriptions[key]}
                                  </Text>
                                ))}
                              </Space>
                              <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                {JSON.stringify(knowledge, null, 2)}
                              </pre>
                            </Space>
                          ),
                        }]}
                      />
                    </Space>
                  </Card>

                  <Card size="small" style={compactCardStyle} title={<span style={{ fontSize: 13, fontWeight: 600, color: uiInk }}>Strategy</span>}>
                    {(() => {
                      const v3Plans = ((autoResearchStatus as Record<string, unknown>).v3_planner_plans as Record<string, unknown>[] | undefined) || [];
                      const v3Profile = (autoResearchStatus as Record<string, unknown>).v3_planner_profile_signal as Record<string, unknown> | undefined;
                      const labelStyle: React.CSSProperties = { fontSize: 11, color: uiLabel, letterSpacing: 0.3 };

                      // v3 模式：展示 action 计划 + 画像信号
                      if (v3Plans.length > 0) {
                        return (
                          <Space direction="vertical" size={14} style={{ width: '100%' }}>
                            {/* 本轮 Action 计划 */}
                            <div>
                              <div style={labelStyle}>本轮 Action 计划</div>
                              <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 8 }}>
                                {v3Plans.map((plan, idx) => {
                                  const actionData = (plan.action as Record<string, unknown>) || {};
                                  const actionId = String(plan.action_id || actionData.action_id || '-');
                                  const stage = String(plan.stage || actionData.stage || '-');
                                  const priority = Number(plan.priority_score || 0);
                                  const variantIdx = plan.variant_index;
                                  const reason = String(plan.reason || '');
                                  const gate = (plan.novelty_gate_result as Record<string, unknown>) || {};
                                  return (
                                    <div
                                      key={`${actionId}-${idx}`}
                                      style={{
                                        padding: '8px 10px',
                                        border: `1px solid ${idx === 0 ? '#b7eb8f' : '#e8eef5'}`,
                                        borderRadius: 8,
                                        background: idx === 0 ? '#f6ffed' : '#fafbfc',
                                      }}
                                    >
                                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                        <span style={{ fontSize: 12, fontWeight: 600, color: uiInk }}>{actionId}</span>
                                        <span style={{ fontSize: 10, background: stage === 'A' ? '#e6f4ff' : stage === 'C' ? '#f6ffed' : '#f0f0f0', color: stage === 'A' ? uiAccent : stage === 'C' ? uiGood : uiMuted, borderRadius: 3, padding: '1px 5px' }}>
                                          Stage {stage}
                                        </span>
                                        <span style={{ fontSize: 11, color: uiMuted, marginLeft: 'auto', fontVariantNumeric: 'tabular-nums' }}>
                                          priority {priority.toFixed(2)} · variant {String(variantIdx ?? 0)}
                                        </span>
                                      </div>
                                      <Text style={{ fontSize: 11, color: uiMuted }}>{String(actionData.description || '')}</Text>
                                      {gate.decision && gate.decision !== 'pass' && (
                                        <div style={{ fontSize: 11, color: uiWarn, marginTop: 3 }}>
                                          gate: {String(gate.decision)} — {String(gate.reason || '')}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>

                            {/* 画像信号摘要 */}
                            {v3Profile && (
                              <div>
                                <div style={labelStyle}>画像信号</div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 6, fontSize: 11 }}>
                                  {[
                                    { k: '波动', v: v3Profile.volatility_level },
                                    { k: '周末敏感', v: v3Profile.weekend_sensitive ? '是' : '否' },
                                    { k: '漂移', v: typeof v3Profile.drift_strength === 'number' ? Number(v3Profile.drift_strength).toFixed(2) : '-' },
                                    { k: '天气相关', v: v3Profile.weather_correlated ? '是' : '否' },
                                    { k: '数据天数', v: v3Profile.data_length_days },
                                    { k: '噪声', v: v3Profile.noise_level },
                                  ].map((item) => (
                                    <span key={item.k} style={{ color: uiMuted }}>
                                      <span style={{ color: uiLabel }}>{item.k}</span> {String(item.v ?? '-')}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* 当前状态 */}
                            <div style={kvGridStyle}>
                              <span style={labelStyle}>研究状态</span>
                              <Text style={{ fontSize: 12 }}>{String(researchState.state || '-')}</Text>
                            </div>
                          </Space>
                        );
                      }

                      // fallback：旧版方向覆盖（v1/v2 run）
                      const recommendedRaw = String(
                        health.recommended_primary_direction || health.recommended_next_direction || '',
                      ).trim();
                      return (
                        <Space direction="vertical" size={14} style={{ width: '100%' }}>
                          <div>
                            <div style={labelStyle}>推荐下一方向</div>
                            <div style={{ fontSize: 15, fontWeight: 600, color: uiInk, marginTop: 3 }}>
                              {labelDirection(recommendedRaw)}
                            </div>
                          </div>
                          <div style={kvGridStyle}>
                            <span style={labelStyle}>当前研究状态</span>
                            <Text style={{ fontSize: 12 }}>{String(researchState.state || '-')}</Text>
                            <span style={labelStyle}>当前主线方向</span>
                            <Text style={{ fontSize: 12 }}>
                              {labelDirection(health.current_primary_direction || health.primary_direction)}
                            </Text>
                          </div>
                          <Text type="secondary" style={{ fontSize: 12, lineHeight: 1.55 }}>
                            {String(researchState.reason || health.primary_rotation_reason || '等待更多证据')}
                          </Text>
                          <div>
                            <div style={{ ...labelStyle, marginBottom: 8 }}>方向探索覆盖</div>
                            {['parameter', 'feature', 'model', 'data', 'risk'].map((direction) => {
                              const pct = Math.max(0, Math.min(100, Number(coverage[direction] || 0) * 100));
                              const isRecommended = direction === recommendedRaw;
                              return (
                                <div key={direction} style={{ marginBottom: 6 }}>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                                    <Text style={{ fontSize: 12, fontWeight: isRecommended ? 600 : 400, color: isRecommended ? uiAccent : uiMuted }}>{directionLabels[direction]}</Text>
                                    <Text style={{ fontSize: 12, color: uiLabel, fontVariantNumeric: 'tabular-nums' }}>{pct.toFixed(0)}%</Text>
                                  </div>
                                  <Progress percent={pct} size="small" showInfo={false} strokeColor={isRecommended ? uiAccent : '#d0d7e2'} />
                                </div>
                              );
                            })}
                          </div>
                        </Space>
                      );
                    })()}
                  </Card>
                </div>
              </Card>
            );
          })()}
          {(() => {
            const failed = (autoResearchStatus.last_failed_trial as Record<string, unknown> | undefined) || {};
            const err = autoResearchStatus.error || failed.error_message || failed.error;
            if (!err) return null;
            return (
              <Alert
                style={{ marginBottom: 10 }}
                type="error"
                showIcon
                message="最近失败原因"
                description={
                  <Space direction="vertical" size={4} style={{ width: '100%' }}>
                    <Text>{String(err)}</Text>
                    <Space wrap size={[6, 6]}>
                      {failed.iteration_no != null || failed.iteration != null ? (
                        <Tag>轮次: {String(failed.iteration_no ?? failed.iteration)}</Tag>
                      ) : null}
                      {failed.comparison_id ? <Tag>comparison_id: {String(failed.comparison_id)}</Tag> : null}
                      {failed.status ? <Tag color="red">status: {String(failed.status)}</Tag> : null}
                    </Space>
                  </Space>
                }
              />
            );
          })()}
          <Card
            size="small"
            style={autoResearchMutedCardStyle}
            title={
              <span style={{ fontSize: 14, fontWeight: 600, color: uiInk, letterSpacing: -0.3 }}>
                运行信号与洞察
              </span>
            }
          >
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 12 }}>
              {[
                { label: '建议生成', value: autoRunInsights.recommendationGenerated ? '已完成' : '未触发', dot: autoRunInsights.recommendationGenerated ? uiAccent : uiLabel },
                { label: '建议应用', value: autoRunInsights.recommendationApplied ? '已应用' : '未应用', dot: autoRunInsights.recommendationApplied ? uiGood : uiLabel },
                { label: '无测试数据', value: String(autoRunInsights.noTestDataCount), dot: autoRunInsights.noTestDataCount > 0 ? uiWarn : uiLabel },
                { label: '无训练数据', value: String(autoRunInsights.insufficientTrainDataCount), dot: autoRunInsights.insufficientTrainDataCount > 0 ? uiWarn : uiLabel },
                { label: '失败轮次', value: String(autoRunInsights.failedCount), dot: autoRunInsights.failedCount > 0 ? uiBad : uiLabel },
              ].map((item) => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ width: 7, height: 7, borderRadius: '50%', background: item.dot, flexShrink: 0 }} />
                  <span style={{ fontSize: 12 }}>
                    <span style={{ color: uiLabel }}>{item.label}</span>{' '}
                    <span style={{ color: uiInk }}>{item.value}</span>
                  </span>
                </div>
              ))}
            </div>
            <Text style={{ fontSize: 12, color: uiMuted }}>
              {autoRunInsights.latestMsg ? `最近：${autoRunInsights.latestMsg}` : '最近状态：-'}
            </Text>
            {/* 任务 6.3：收敛检测提示 + 一键停止 */}
            {(() => {
              const conv = (autoResearchStatus as Record<string, unknown>).convergence_status as Record<string, unknown> | undefined;
              if (!conv?.converged) return null;
              return (
                <Alert
                  style={{ marginTop: 8 }}
                  type="success"
                  showIcon
                  message="已检测到收敛"
                  description={
                    <Space direction="vertical" size={4}>
                      <span>{String(conv.reason ?? '')}</span>
                      <span style={{ fontSize: 11, color: '#888' }}>
                        MAPE 方差: {conv.mape_variance != null ? Number(conv.mape_variance).toFixed(6) : '-'}
                      </span>
                      <Button
                        size="small"
                        danger
                        onClick={async () => {
                          if (!autoResearchRunId) return;
                          try {
                            await baselineCompareApi.cancelAutoResearch(autoResearchRunId);
                            message.success('已发送停止指令');
                          } catch {
                            message.error('停止失败');
                          }
                        }}
                      >
                        一键停止实验
                      </Button>
                    </Space>
                  }
                />
              );
            })()}
            {(autoRunInsights.noTestDataCount > 0 || autoRunInsights.insufficientTrainDataCount > 0) && (
              <Alert
                style={{ marginTop: 8 }}
                type="warning"
                showIcon
                message="检测到数据覆盖问题"
                description="建议前移时间窗，或下调 train_days/backtest_train_days，必要时暂时关闭窗口过滤后再重跑。"
              />
            )}

            <div style={{ height: 1, background: '#f0f0f0', margin: '12px 0' }} />
            {renderAutoResearchCurveSection(
              autoResearchStatus,
              autoResearchTrials,
              selectedProfileIteration,
              setSelectedProfileIteration,
            )}
          {(() => {
            // 五卡片研究驾驶舱已承接研究问题、证据和知识摘要；旧产物区保留代码但默认不再渲染，避免信息重复。
            if (showAdvancedDetails) return null;
            const rawQuestions = ((autoResearchStatus as Record<string, unknown>).research_questions as unknown[] | undefined || []) as Record<string, unknown>[];
            const questions = Array.from(rawQuestions.reduce<Map<string, Record<string, unknown>>>((acc, q) => {
              const key = String(q.question_key || `${String(q.question || '')}::${String(q.next_experiment_goal || '')}`);
              acc.set(key, { ...(acc.get(key) || {}), ...q });
              return acc;
            }, new Map()).values());
            const questionStatusRank = (q: Record<string, unknown>) => {
              const status = String(q.status || (q.recurring ? 'testing' : 'open'));
              if (status === 'testing') return 4;
              if (status === 'open') return 3;
              if (status === 'resolved') return 2;
              if (status === 'stale') return 1;
              return 0;
            };
            const questionLastSeen = (q: Record<string, unknown>) => Number(q.last_seen_iteration ?? q.iteration ?? q.first_seen_iteration ?? 0);
            const diagnosis = (autoResearchStatus as Record<string, unknown>).tri_dataset_diagnosis as Record<string, unknown> | undefined;
            const datasetProfile = (autoResearchStatus as Record<string, unknown>).dataset_profile as Record<string, unknown> | undefined;
            const qualityWrap = (autoResearchStatus as Record<string, unknown>).experiment_quality as Record<string, unknown> | undefined;
            const reflections = ((autoResearchStatus as Record<string, unknown>).periodic_reflections as unknown[] | undefined || []) as Record<string, unknown>[];
            const latestQuestions = [...questions]
              .sort((a, b) => {
                const rankDelta = questionStatusRank(b) - questionStatusRank(a);
                if (rankDelta !== 0) return rankDelta;
                return questionLastSeen(b) - questionLastSeen(a);
              })
              .slice(0, 3);
            const latestReflection = reflections.length > 0 ? reflections[reflections.length - 1] : null;
            const reflectionDecision = latestReflection?.reflection_decision as Record<string, unknown> | undefined;
            const quality = (qualityWrap?.quality as Record<string, unknown> | undefined) || {};
            const validationProfile = (datasetProfile?.validation_profile as Record<string, unknown> | undefined)
              || (diagnosis?.validation_profile as Record<string, unknown> | undefined)
              || {};
            const hasResearchArtifacts = latestQuestions.length > 0 || diagnosis || qualityWrap || latestReflection;
            if (!hasResearchArtifacts) {
              const rows = ((autoResearchStatus.iterations as unknown[]) || []) as Record<string, unknown>[];
              const curIter = Number((autoResearchStatus.progress as Record<string, unknown> | undefined)?.iteration || 0);
              if (rows.length === 0 && curIter <= 0) return null;
              return (
                <Card size="small" style={autoResearchMutedCardStyle} title={<span style={{ fontSize: 14, fontWeight: 600, color: uiInk, letterSpacing: -0.3 }}>自主研究员产物</span>}>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    第 1 轮完成后会显示研究问题、误差诊断和实验质量评分；当前仍在首轮回测或产物生成中。
                  </Text>
                </Card>
              );
            }
            return (
              <Card size="small" style={autoResearchMutedCardStyle} title={<span style={{ fontSize: 14, fontWeight: 600, color: uiInk, letterSpacing: -0.3 }}>自主研究员产物</span>}>
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  {latestQuestions.length > 0 && (
                    <div>
                      <Text strong>研究问题</Text>
                      <Space direction="vertical" size={6} style={{ width: '100%', marginTop: 6 }}>
                        {latestQuestions.map((q, idx) => {
                          const status = String(q.status || (q.recurring ? 'testing' : 'open'));
                          const firstSeen = q.first_seen_iteration ?? q.iteration;
                          const lastSeen = q.last_seen_iteration ?? q.iteration;
                          const iterText = lastSeen == null ? '轮次未知' : `第 ${String(lastSeen)} 轮`;
                          const statusColor = status === 'resolved' ? 'green' : status === 'testing' ? 'orange' : status === 'stale' ? 'default' : 'blue';
                          const alertType = (status === 'resolved' ? 'success' : status === 'testing' || status === 'stale' || q.recurring ? 'warning' : 'info') as 'success' | 'warning' | 'info';
                          const proposalSource = String(q.proposal_source || '-');
                          return (
                            <Alert
                              key={`${String(q.question_key || q.iteration || 'q')}-${idx}`}
                              type={alertType}
                              showIcon
                              message={
                                <Space size={6} wrap>
                                  <Tag color="blue">{iterText}</Tag>
                                  <Tag color={statusColor}>{status}</Tag>
                                  {proposalSource !== '-' && (
                                    <Tag color={proposalSource === 'glm' ? 'purple' : proposalSource === 'glm_fallback' ? 'orange' : 'default'}>
                                      来源: {proposalSource}
                                    </Tag>
                                  )}
                                  <span>{String(q.question || '-')}</span>
                                </Space>
                              }
                              description={
                                <Space direction="vertical" size={2}>
                                  <Text type="secondary" style={{ fontSize: 12 }}>
                                    目标：{String(q.next_experiment_goal || '-')}
                                  </Text>
                                  {(firstSeen != null || lastSeen != null || q.evidence_count != null) && (
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                      生命周期：{firstSeen != null ? `第 ${String(firstSeen)} 轮` : '-'}
                                      {lastSeen != null && lastSeen !== firstSeen ? ` 至 第 ${String(lastSeen)} 轮` : ''}
                                      {q.evidence_count != null ? ` · 证据 ${String(q.evidence_count)}` : ''}
                                    </Text>
                                  )}
                                  {Array.isArray(q.candidate_causes) && q.candidate_causes.length > 0 && (
                                    <Space wrap size={[4, 4]}>
                                      {(q.candidate_causes as unknown[]).slice(0, 5).map((cause, i) => (
                                        <Tag key={i}>{String(cause)}</Tag>
                                      ))}
                                    </Space>
                                  )}
                                </Space>
                              }
                            />
                          );
                        })}
                      </Space>
                    </div>
                  )}

                  {(diagnosis || Object.keys(validationProfile).length > 0) && (
                    <div>
                      <Text strong>误差诊断</Text>
                      <div style={{ marginTop: 6 }}>
                        <Space wrap size={[8, 8]}>
                          <Tag color={diagnosis?.overfit_detection === 'confirmed_overfit' ? 'red' : 'green'}>
                            过拟合: {String(diagnosis?.overfit_detection || 'unknown')}
                          </Tag>
                          <Tag color="blue">
                            泛化: {String(diagnosis?.generalization_assessment || 'unknown')}
                          </Tag>
                          <Tag color={validationProfile.overfit_indicator === 'high' ? 'red' : validationProfile.overfit_indicator === 'moderate' ? 'orange' : 'default'}>
                            CV gap: {String(validationProfile.overfit_indicator || '-')}
                          </Tag>
                          {validationProfile.cv_val_mape != null && (
                            <Tag>CV MAPE: {Number(validationProfile.cv_val_mape).toFixed(4)}</Tag>
                          )}
                        </Space>
                        {diagnosis?.diagnosis_conclusion && (
                          <div style={{ marginTop: 6 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {String(diagnosis.diagnosis_conclusion)}
                            </Text>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {(() => {
                    const plotRows = collectAutoResearchCurveRows(autoResearchStatus, autoResearchTrials);
                    const plotOptions = plotRows
                      .map((row, idx) => {
                        const iteration = Number(row.iteration ?? idx + 1);
                        return Number.isFinite(iteration)
                          ? { label: `第 ${iteration} 轮`, value: iteration }
                          : null;
                      })
                      .filter(Boolean) as { label: string; value: number }[];
                    const selectedExists = selectedProfileIteration != null
                      && plotRows.some((row) => Number(row.iteration) === selectedProfileIteration);
                    const activePlot = selectedExists
                      ? plotRows.find((row) => Number(row.iteration) === selectedProfileIteration)
                      : (plotRows.length > 0 ? plotRows[plotRows.length - 1] : null);
                    const activeIteration = Number(activePlot?.iteration ?? 0);
                    const selectedDatasetProfile = (((autoResearchStatus as Record<string, unknown>).dataset_profiles as unknown[] | undefined || []) as Record<string, unknown>[])
                      .find((row) => Number(row.iteration) === activeIteration);
                    const activeValidationProfile = (selectedDatasetProfile?.validation_profile as Record<string, unknown> | undefined)
                      || validationProfile;
                    const rawPoints = activePlot?.points || [];
                    const step = Math.max(1, Math.ceil(rawPoints.length / 480));
                    const points = rawPoints.filter((_, idx) => idx % step === 0);
                    const xLabels = points.map((p) => {
                      const raw = String(p.timestamp || '');
                      return raw.length > 16 ? raw.slice(5, 16) : raw;
                    });
                    const actual = points.map((p) => Number(p.actual));
                    const predicted = points.map((p) => Number(p.predicted));
                    const ape = points.map((p) => {
                      const a = Number(p.actual);
                      const y = Number(p.predicted);
                      if (!Number.isFinite(a) || !Number.isFinite(y) || Math.abs(a) <= 1e-8) return null;
                      return Number((Math.abs((a - y) / a) * 100).toFixed(4));
                    });
                    const peakScatter = points
                      .map((p, idx) => p.is_peak ? [xLabels[idx], Number(p.actual)] : null)
                      .filter(Boolean);
                    const valleyScatter = points
                      .map((p, idx) => p.is_valley ? [xLabels[idx], Number(p.actual)] : null)
                      .filter(Boolean);
                    const cvLosses = ((activeValidationProfile.cv_fold_losses as unknown[] | undefined) || []) as Record<string, unknown>[];
                    const foldLabels = cvLosses.map((f) => `F${String(f.fold_id ?? '-')}`);
                    const trainLoss = cvLosses.map((f) => Number(f.train_loss));
                    const valLoss = cvLosses.map((f) => Number(f.val_loss));
                    const hasCurve = points.length > 0;
                    const hasCv = cvLosses.length > 0;
                    if (!hasCurve && !hasCv) return null;
                    const curveOption = {
                      tooltip: { trigger: 'axis' },
                      legend: { top: 0, data: ['实际负荷', '预测负荷', '峰点', '谷点'] },
                      grid: { left: 42, right: 18, top: 42, bottom: 34 },
                      xAxis: { type: 'category', data: xLabels, boundaryGap: false },
                      yAxis: { type: 'value', scale: true },
                      series: [
                        { name: '实际负荷', type: 'line', data: actual, smooth: true, showSymbol: false, lineStyle: { width: 2 } },
                        { name: '预测负荷', type: 'line', data: predicted, smooth: true, showSymbol: false, lineStyle: { width: 2 } },
                        { name: '峰点', type: 'scatter', data: peakScatter, symbolSize: 7 },
                        { name: '谷点', type: 'scatter', data: valleyScatter, symbolSize: 7 },
                      ],
                    };
                    const errorOption = {
                      tooltip: { trigger: 'axis' },
                      grid: { left: 42, right: 18, top: 28, bottom: 34 },
                      xAxis: { type: 'category', data: xLabels, boundaryGap: false },
                      yAxis: { type: 'value', name: 'APE %', min: 0 },
                      series: [
                        {
                          name: '绝对百分误差',
                          type: 'line',
                          data: ape,
                          smooth: true,
                          showSymbol: false,
                          areaStyle: { opacity: 0.12 },
                          markLine: {
                            symbol: 'none',
                            lineStyle: { type: 'dashed' },
                            data: [{ yAxis: 10, name: '10%' }],
                          },
                        },
                      ],
                    };
                    const cvOption = {
                      tooltip: { trigger: 'axis' },
                      legend: { top: 0, data: ['训练损失', '验证损失'] },
                      grid: { left: 42, right: 18, top: 42, bottom: 34 },
                      xAxis: { type: 'category', data: foldLabels },
                      yAxis: { type: 'value', scale: true },
                      series: [
                        { name: '训练损失', type: 'bar', data: trainLoss, barMaxWidth: 28 },
                        { name: '验证损失', type: 'line', data: valLoss, smooth: true, symbolSize: 7 },
                      ],
                    };
                    return (
                      <div>
                        <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 6 }} wrap>
                          <Text strong>三集画像曲线</Text>
                          {plotOptions.length > 0 && (
                            <Select
                              size="small"
                              style={{ width: 140 }}
                              value={activeIteration || undefined}
                              options={plotOptions.slice().reverse()}
                              onChange={(value) => setSelectedProfileIteration(Number(value))}
                            />
                          )}
                        </Space>
                        <div style={{ marginTop: 6, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 10 }}>
                          {hasCurve && (
                            <Card size="small" title={`测试集曲线画像（第 ${String(activeIteration || '-')} 轮）`}>
                              <ReactECharts option={curveOption} style={{ height: 260 }} />
                            </Card>
                          )}
                          {hasCurve && (
                            <Card size="small" title="测试集误差画像">
                              <ReactECharts option={errorOption} style={{ height: 260 }} />
                            </Card>
                          )}
                          {hasCv && (
                            <Card size="small" title="验证集 CV 画像">
                              <ReactECharts option={cvOption} style={{ height: 260 }} />
                            </Card>
                          )}
                        </div>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          可切换查看已完成轮次；长序列会自动抽样，避免页面卡顿。
                        </Text>
                      </div>
                    );
                  })()}

                  {(qualityWrap || latestReflection) && (
                    <div>
                      <Text strong>实验设计与阶段反思</Text>
                      <div style={{ marginTop: 6 }}>
                        <Space wrap size={[8, 8]}>
                          {qualityWrap && (
                            <>
                              <Tag color="purple">质量评分: {quality.composite_score != null ? Number(quality.composite_score).toFixed(3) : '-'}</Tag>
                              <Tag>单变量控制: {quality.single_variable_control != null ? Number(quality.single_variable_control).toFixed(2) : '-'}</Tag>
                              <Tag>知识增益: {quality.knowledge_gain_estimate != null ? Number(quality.knowledge_gain_estimate).toFixed(2) : '-'}</Tag>
                            </>
                          )}
                          {latestReflection && (
                            <>
                              <Tag color={reflectionDecision?.decision === 'shift_focus' ? 'orange' : reflectionDecision?.decision === 'expand_registry' ? 'red' : 'green'}>
                                决策: {String(reflectionDecision?.decision || '-')}
                              </Tag>
                              <Tag>趋势: {String(latestReflection.improvement_trend || '-')}</Tag>
                              <Tag>覆盖率: {latestReflection.exploration_coverage != null ? Number(latestReflection.exploration_coverage).toFixed(2) : '-'}</Tag>
                            </>
                          )}
                        </Space>
                        {reflectionDecision?.reason && (
                          <div style={{ marginTop: 6 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {String(reflectionDecision.reason)}
                            </Text>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </Space>
              </Card>
            );
          })()}
          {/* 任务 29.4：历史实验经验展示（首轮时显示） */}
          {(() => {
            const progress = (autoResearchStatus.progress as Record<string, unknown> | undefined) || {};
            const iteration = Number(progress.iteration || 0);
            const registryId = (autoResearchStatus as Record<string, unknown>).registry_id as string | undefined;
            // 只在前几轮显示（有参考价值）
            if (iteration > 3 || !registryId) return null;
            const insights = (autoResearchStatus as Record<string, unknown>).insights as Record<string, unknown> | undefined;
            const totalTested = Number(insights?.total_hypotheses_tested || 0);
            // 只在还没有足够本轮数据时显示历史经验
            if (totalTested >= 2) return null;
            return (
              <Alert
                type="info"
                showIcon
                style={{ marginBottom: 10 }}
                message={`参考了历史实验经验（注册表: ${registryId}）`}
                description={
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    首轮采样已注入历史相似实验的推荐配置作为偏好权重。
                    查看 GLM 建议的 rationale 可了解具体参考了哪些历史经验。
                  </Text>
                }
              />
            );
          })()}
          {/* GLM 调用记录（折叠面板，默认收起） */}
          {(() => {
            const glmHistory = (autoResearchStatus as Record<string, unknown>).glm_call_history as Record<string, unknown>[] | undefined;
            if (!glmHistory || glmHistory.length === 0) return null;
            const totalCalls = glmHistory.length;
            const totalDur = glmHistory.reduce((s, r) => s + Number(r.duration_s || 0), 0);
            const appliedCount = glmHistory.filter(r => r.applied).length;
            return (
              <Collapse
                ghost
                style={{ marginBottom: 8 }}
                items={[{
                  key: 'glm-history',
                  label: (
                    <span>
                      🤖 GLM 调用记录
                      <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                        共 {totalCalls} 次 · 累计 {totalDur.toFixed(1)}s · {appliedCount} 次已应用
                      </Text>
                    </span>
                  ),
                  children: (
                    <Collapse
                      ghost
                      size="small"
                      items={glmHistory.slice().reverse().map((record, idx) => {
                        const iter = Number(record.iteration || 0);
                        const dur = Number(record.duration_s || 0);
                        const applied = Boolean(record.applied);
                        const hypothesis = String(record.hypothesis || '');
                        const observation = String(record.observation || '');
                        const rationale = String(record.rationale || '');
                        const glmMeta = record.glm_meta as Record<string, unknown> | undefined;
                        const recommendedId = String(record.recommended_id || '');
                        const recommendedValid = record.recommended_valid;
                        const recommendedRisk = String(record.recommended_risk || '');
                        const riskMax = String(record.auto_apply_risk_level_max || '');
                        const skipReason = String(record.skip_apply_reason || '');
                        const skipReasonText = formatGlmSkipReason(skipReason);
                        const validationErrors = Array.isArray(record.validation_errors) ? record.validation_errors : [];
                        const glmInputDebug = record.glm_input_debug as Record<string, unknown> | undefined;
                        const userPrompt = String(glmInputDebug?.user_prompt || '');
                        const systemPrompt = String(glmInputDebug?.system_prompt || '');
                        const slimReport = glmInputDebug?.slim_report;
                        const memoryReferences = glmInputDebug?.memory_references;
                        const allowedKeys = glmInputDebug?.allowed_keys;
                        return {
                          key: String(idx),
                          label: (
                            <Space size={6} wrap>
                              <Tag color="blue" style={{ fontSize: 10 }}>第 {iter} 轮</Tag>
                              <Text style={{ fontSize: 11, color: '#888' }}>{dur.toFixed(1)}s</Text>
                              {applied
                                ? <Tag color="green" style={{ fontSize: 10 }}>✓ 已应用</Tag>
                                : <Tag color={skipReason ? 'orange' : 'default'} style={{ fontSize: 10 }}>
                                    未应用{skipReasonText ? `：${skipReasonText}` : ''}
                                  </Tag>
                              }
                              {recommendedId && (
                                <Tag color="purple" style={{ fontSize: 10 }}>推荐 {recommendedId}</Tag>
                              )}
                              {recommendedValid !== undefined && recommendedValid !== null && (
                                <Tag color={recommendedValid ? 'green' : 'red'} style={{ fontSize: 10 }}>
                                  valid: {String(Boolean(recommendedValid))}
                                </Tag>
                              )}
                              {recommendedRisk && (
                                <Tag color={recommendedRisk === 'low' ? 'green' : recommendedRisk === 'medium' ? 'orange' : 'red'} style={{ fontSize: 10 }}>
                                  risk: {recommendedRisk}{riskMax ? ` / max ${riskMax}` : ''}
                                </Tag>
                              )}
                              {hypothesis && (
                                <Text type="secondary" style={{ fontSize: 11, maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'inline-block' }}>
                                  {hypothesis}
                                </Text>
                              )}
                            </Space>
                          ),
                          children: (
                            <Space direction="vertical" size={6} style={{ width: '100%', paddingLeft: 8 }}>
                              <Space wrap size={[6, 6]}>
                                <Tag color="blue">generated: {String(record.generated_count ?? '-')}</Tag>
                                <Tag color={recommendedId ? 'purple' : 'default'}>recommended: {recommendedId || '-'}</Tag>
                                <Tag color={applied ? 'green' : 'default'}>applied: {String(applied)}</Tag>
                                {recommendedValid !== undefined && recommendedValid !== null && (
                                  <Tag color={recommendedValid ? 'green' : 'red'}>validator: {recommendedValid ? 'pass' : 'fail'}</Tag>
                                )}
                                {recommendedRisk && (
                                  <Tag color={recommendedRisk === 'low' ? 'green' : recommendedRisk === 'medium' ? 'orange' : 'red'}>
                                    risk: {recommendedRisk}
                                  </Tag>
                                )}
                                {riskMax && <Tag>risk_max: {riskMax}</Tag>}
                                {glmMeta && (
                                  <>
                                    <Tag>GLM候选: {String(glmMeta.candidates_count ?? 0)}</Tag>
                                    <Tag>记忆命中: {String(glmMeta.memory_hit_count ?? 0)}</Tag>
                                    <Tag>llm_used: {String(Boolean(glmMeta.llm_used))}</Tag>
                                  </>
                                )}
                              </Space>
                              {!applied && skipReasonText && (
                                <Alert
                                  type="warning"
                                  showIcon
                                  style={{ margin: '2px 0' }}
                                  message={`未自动应用：${skipReasonText}`}
                                  description={
                                    recommendedRisk && riskMax
                                      ? `推荐风险=${recommendedRisk}，当前自动应用阈值=${riskMax}`
                                      : undefined
                                  }
                                />
                              )}
                              {validationErrors.length > 0 && (
                                <Alert
                                  type="error"
                                  showIcon
                                  style={{ margin: '2px 0' }}
                                  message="validator 错误"
                                  description={
                                    <Space wrap size={[4, 4]}>
                                      {validationErrors.slice(0, 8).map((err, errIdx) => (
                                        <Tag key={errIdx} color="red" style={{ whiteSpace: 'normal', height: 'auto' }}>
                                          {String(err)}
                                        </Tag>
                                      ))}
                                    </Space>
                                  }
                                />
                              )}
                              {glmInputDebug && (
                                <Collapse
                                  size="small"
                                  ghost
                                  items={[{
                                    key: 'glm-input',
                                    label: (
                                      <Space size={6} wrap>
                                        <span>输入给 GLM 的内容</span>
                                        <Tag>{String(glmInputDebug.prompt_chars ?? '-')} chars</Tag>
                                        {glmInputDebug.truncated ? <Tag color="orange">已截断展示</Tag> : null}
                                      </Space>
                                    ),
                                    children: (
                                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                                        {systemPrompt && (
                                          <div>
                                            <Text strong style={{ fontSize: 12 }}>System prompt</Text>
                                            <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 180, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                              {systemPrompt}
                                            </pre>
                                          </div>
                                        )}
                                        {userPrompt && (
                                          <div>
                                            <Text strong style={{ fontSize: 12 }}>User prompt / experiment_report</Text>
                                            <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 320, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                              {userPrompt}
                                            </pre>
                                          </div>
                                        )}
                                        <Collapse
                                          size="small"
                                          items={[
                                            slimReport ? {
                                              key: 'slim-report',
                                              label: '结构化 slim_report',
                                              children: (
                                                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                                  {JSON.stringify(slimReport, null, 2)}
                                                </pre>
                                              ),
                                            } : null,
                                            memoryReferences ? {
                                              key: 'memory-refs',
                                              label: '检索到的历史记忆',
                                              children: (
                                                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                                  {JSON.stringify(memoryReferences, null, 2)}
                                                </pre>
                                              ),
                                            } : null,
                                            allowedKeys ? {
                                              key: 'allowed-keys',
                                              label: 'allowed_keys 白名单',
                                              children: (
                                                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                                  {JSON.stringify(allowedKeys, null, 2)}
                                                </pre>
                                              ),
                                            } : null,
                                          ].filter(Boolean) as NonNullable<React.ComponentProps<typeof Collapse>['items']>}
                                        />
                                      </Space>
                                    ),
                                  }]}
                                />
                              )}
                              {observation && (
                                <div>
                                  <Text type="secondary" style={{ fontSize: 11 }}>观察：</Text>
                                  <Text style={{ fontSize: 12 }}>{observation}</Text>
                                </div>
                              )}
                              {hypothesis && (
                                <div>
                                  <Text type="secondary" style={{ fontSize: 11 }}>假设：</Text>
                                  <Text strong style={{ fontSize: 12 }}>{hypothesis}</Text>
                                </div>
                              )}
                              {rationale && (
                                <div>
                                  <Text type="secondary" style={{ fontSize: 11 }}>建议理由：</Text>
                                  <Text style={{ fontSize: 12 }}>{rationale}</Text>
                                </div>
                              )}
                              {glmMeta && (
                                <div style={{ fontSize: 11, color: '#aaa', marginTop: 2 }}>
                                  模型: {String(glmMeta.model || '-')}
                                  <span style={{ marginLeft: 10 }}>候选数: {String(glmMeta.candidates_count || 0)}</span>
                                  <span style={{ marginLeft: 10 }}>记忆命中: {String(glmMeta.memory_hit_count || 0)}</span>
                                  <span style={{ marginLeft: 10 }}>llm_used: {String(Boolean(glmMeta.llm_used))}</span>
                                  {glmMeta.llm_error && (
                                    <span style={{ marginLeft: 10, color: '#ff4d4f' }}>错误: {String(glmMeta.llm_error)}</span>
                                  )}
                                </div>
                              )}
                            </Space>
                          ),
                        };
                      })}
                    />
                  ),
                }]}
              />
            );
          })()}
          {(() => {
            const rows = (((autoResearchStatus as Record<string, unknown>).parallel_research_results as unknown[] | undefined) || []) as Record<string, unknown>[];
            if (!rows.length) return null;
            const bestCount = rows.filter(r => Boolean(r.is_best)).length;
            return (
              <Collapse
                ghost
                style={{ marginBottom: 8 }}
                items={[{
                  key: 'parallel-research',
                  label: (
                    <span>
                      并行研究结果
                      <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                        共 {rows.length} 组 · 最优 {bestCount} 组
                      </Text>
                    </span>
                  ),
                  children: (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 10 }}>
                      {rows.map((row, idx) => {
                        const diagnosis = (row.diagnosis as Record<string, unknown> | undefined) || {};
                        const evidence = (diagnosis.evidence as unknown[] | undefined) || [];
                        const override = (row.override as Record<string, unknown> | undefined) || {};
                        return (
                          <div
                            key={`${String(row.group_idx ?? idx)}-${idx}`}
                            style={{
                              padding: 10,
                              border: `1px solid ${row.is_best ? '#b7eb8f' : '#f0f0f0'}`,
                              borderRadius: 8,
                              background: row.is_best ? '#fbfff7' : '#fff',
                            }}
                          >
                            <Space wrap size={[6, 6]} style={{ marginBottom: 6 }}>
                              <Tag color={row.is_best ? 'green' : 'blue'}>组 {Number(row.group_idx ?? idx) + 1}</Tag>
                              <Tag color={row.is_best ? 'green' : 'default'}>{row.is_best ? '本轮最优' : '对照学习'}</Tag>
                              <Tag>{String(row.status || '-')}</Tag>
                            </Space>
                            <div style={{ marginBottom: 6 }}>
                              <Text type="secondary" style={{ fontSize: 11 }}>研究问题：</Text>
                              <Text style={{ fontSize: 12 }}>{String(row.research_question_seed || '-')}</Text>
                            </div>
                            <div style={{ marginBottom: 6 }}>
                              <Text type="secondary" style={{ fontSize: 11 }}>候选假设：</Text>
                              <Text strong style={{ fontSize: 12 }}>{String(row.candidate_hypothesis_seed || '-')}</Text>
                            </div>
                            <Space wrap size={[4, 4]} style={{ marginBottom: 6 }}>
                              <Tag color="purple">诊断: {String(diagnosis.primary_cause || '-')}</Tag>
                              {evidence.slice(0, 4).map((item, i) => (
                                <Tag key={i}>{String(item)}</Tag>
                              ))}
                            </Space>
                            {Object.keys(override).length > 0 && (
                              <Collapse
                                size="small"
                                ghost
                                items={[{
                                  key: 'override',
                                  label: '本组参数',
                                  children: (
                                    <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 160, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                      {JSON.stringify(override, null, 2)}
                                    </pre>
                                  ),
                                }]}
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ),
                }]}
              />
            );
          })()}
          {/* 任务 23.2：实验洞察（放在 GLM 调用记录下方，便于对照输入/输出与假设验证） */}
          {(() => {
            const insights = (autoResearchStatus as Record<string, unknown>).insights as Record<string, unknown> | undefined;
            const disproved = (autoResearchStatus as Record<string, unknown>).disproved_hypotheses as unknown[] | undefined;
            const effective = (insights?.effective_directions as string[] | undefined) || [];
            const ineffective = (insights?.ineffective_directions as string[] | undefined) || [];
            const total = Number(insights?.total_hypotheses_tested || 0);
            const verified = Number(insights?.hypotheses_verified || 0);
            const disproved_count = Number(insights?.hypotheses_disproved || 0);
            const hypothesisChain = (((autoResearchStatus as Record<string, unknown>).hypothesis_chain as unknown[] | undefined) || []) as Record<string, unknown>[];
            const lastSkip = (autoResearchStatus as Record<string, unknown>).last_hypothesis_verification_skip as Record<string, unknown> | undefined;
            return (
              <Collapse
                ghost
                style={{ marginBottom: 8 }}
                items={[{
                  key: 'insights',
                  label: (
                    <span>
                      🧠 实验洞察
                      {total > 0 && (
                        <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                          已测试 {total} 个假设，{verified} 个成立，{disproved_count} 个否证
                        </Text>
                      )}
                    </span>
                  ),
                  children: (
                    <Space direction="vertical" size={8} style={{ width: '100%' }}>
                      {hypothesisChain.length > 0 && (
                        <div>
                          <Text strong style={{ fontSize: 12 }}>假设链路</Text>
                          <Space direction="vertical" size={6} style={{ width: '100%', marginTop: 6 }}>
                            {hypothesisChain.slice().reverse().slice(0, 6).map((h, i) => {
                              const status = String(h.status || 'pending_verification');
                              const expected = h.expected_outcome as Record<string, unknown> | undefined;
                              const verification = h.verification as Record<string, unknown> | undefined;
                              return (
                                <div
                                  key={`${String(h.proposal_id || i)}-${i}`}
                                  style={{
                                    padding: '8px 10px',
                                    border: '1px solid #f0f0f0',
                                    borderRadius: 8,
                                    background: '#fff',
                                  }}
                                >
                                  <Space wrap size={[6, 6]} style={{ marginBottom: 4 }}>
                                    <Tag color={status === 'verified' ? 'green' : status === 'disproved' ? 'red' : 'blue'}>
                                      {status === 'verified' ? '已成立' : status === 'disproved' ? '已否证' : '待验证'}
                                    </Tag>
                                    <Tag color="purple">{String(h.proposal_id || '-')}</Tag>
                                    {h.hypothesis_type && <Tag>{String(h.hypothesis_type)}</Tag>}
                                    {h.applied_iteration != null && <Tag>应用轮次: {String(h.applied_iteration)}</Tag>}
                                    {h.verified_iteration != null && <Tag>验证轮次: {String(h.verified_iteration)}</Tag>}
                                  </Space>
                                  <div>
                                    <Text type="secondary" style={{ fontSize: 11 }}>假设：</Text>
                                    <Text strong style={{ fontSize: 12 }}>{String(h.hypothesis || '-')}</Text>
                                  </div>
                                  {expected && (
                                    <div style={{ marginTop: 2 }}>
                                      <Text type="secondary" style={{ fontSize: 11 }}>预期：</Text>
                                      <Text style={{ fontSize: 12 }}>
                                        {String(expected.metric || '-')} {String(expected.direction || '-')} {String(expected.threshold ?? '-')}
                                        {expected.description ? `（${String(expected.description)}）` : ''}
                                      </Text>
                                    </div>
                                  )}
                                  {verification && (
                                    <div style={{ marginTop: 2 }}>
                                      <Text type="secondary" style={{ fontSize: 11 }}>验证：</Text>
                                      <Text style={{ fontSize: 12 }}>{String(verification.conclusion || '-')}</Text>
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </Space>
                        </div>
                      )}
                      {hypothesisChain.length === 0 && lastSkip && (
                        <Alert
                          type="info"
                          showIcon
                          message="暂无可验证假设"
                          description={`原因：${String(lastSkip.reason || '-')}`}
                        />
                      )}
                      {effective.length > 0 && (
                        <div>
                          <Text strong style={{ fontSize: 12, color: '#52c41a' }}>✓ 已验证有效方向</Text>
                          <div style={{ marginTop: 4 }}>
                            {effective.map((e, i) => (
                              <Tag key={i} color="success" style={{ marginBottom: 4, whiteSpace: 'normal', height: 'auto' }}>
                                {e}
                              </Tag>
                            ))}
                          </div>
                        </div>
                      )}
                      {ineffective.length > 0 && (
                        <div>
                          <Text strong style={{ fontSize: 12, color: '#ff4d4f' }}>✗ 已否证方向</Text>
                          <div style={{ marginTop: 4 }}>
                            {ineffective.map((e, i) => (
                              <Tag key={i} color="error" style={{ marginBottom: 4, whiteSpace: 'normal', height: 'auto' }}>
                                {e}
                              </Tag>
                            ))}
                          </div>
                        </div>
                      )}
                      {!effective.length && !ineffective.length && (
                        <Text type="secondary" style={{ fontSize: 12 }}>暂无洞察（需要已应用的假设完成下一轮验证）</Text>
                      )}
                    </Space>
                  ),
                }]}
              />
            );
          })()}
          {(() => {
            const adj = (autoResearchStatus.latest_auto_adjustment as Record<string, unknown> | undefined) || null;
            if (!adj) return null;
            return (
              <Alert
                style={{ marginBottom: 10 }}
                type="warning"
                showIcon
                message={`最近自动纠偏：${String(adj.type || 'auto_adjust')}`}
                description={
                  <Space wrap size={[8, 8]}>
                    <Tag color="orange">iteration: {String(adj.iteration ?? '-')}</Tag>
                    <Tag>{String(adj.applied_at ?? '-')}</Tag>
                    <Tag>{String(adj.message || '-')}</Tag>
                  </Space>
                }
              />
            );
          })()}
          {/* ── 运行状态 Banner（显眼的阶段指示） ── */}
          {(() => {
            const live = ((autoResearchStatus as Record<string, unknown>).current_iteration_live as Record<string, unknown> | undefined) || {};
            const liveSummary = (live.live_summary as Record<string, unknown> | undefined) || {};
            const phase = String(liveSummary.current_phase || autoRunInsights.phase || '').trim();
            const windowInfo = String(liveSummary.current_window || '').trim();
            const phaseLabels: Record<string, string> = {
              baseline_warmup: '🔵 正在建立 Baseline 缓存',
              baseline_running: '🔵 Baseline 回测中',
              challenger_running: '🟣 Challenger 回测中',
              rolling_backtest: '🔵 滚动回测中',
              generating_or_applying: '🟡 生成建议 / 应用中',
              waiting_review: '🟠 等待人工审核',
              finished: '🟢 本轮完成',
              running_backtest: '🔵 回测中',
              '': '',
            };
            const phaseText = phaseLabels[phase] || (phase ? `⚙️ ${phase}` : '');
            if (!phaseText) return null;
            return (
              <div
                style={{
                  marginBottom: 14,
                  padding: '10px 14px',
                  borderRadius: 10,
                  background: phase === 'finished' ? '#f6ffed' : phase.includes('waiting') ? '#fff7e6' : '#f0f7ff',
                  border: `1px solid ${phase === 'finished' ? '#b7eb8f' : phase.includes('waiting') ? '#ffd591' : '#91caff'}`,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <span style={{ fontSize: 14, fontWeight: 600, color: uiInk }}>{phaseText}</span>
                {windowInfo && <span style={{ fontSize: 12, color: uiMuted }}>窗口：{windowInfo}</span>}
              </div>
            );
          })()}
          {(() => {
            const latestGroups = ((autoResearchStatus.latest_batch_groups as unknown[]) || []) as Record<string, unknown>[];
            const batchStatus = (autoResearchStatus.batch_eval_status as Record<string, unknown> | undefined) || {};
            const runningGroups = ((batchStatus.groups as unknown[]) || []) as Record<string, unknown>[];
            const trialByIteration = new Map<number, Record<string, unknown>>();
            autoResearchTrials.forEach((trial) => {
              const n = Number(trial.iteration_no ?? trial.iteration);
              if (Number.isFinite(n) && n > 0) trialByIteration.set(n, trial);
            });
            const iterationSet = new Set<number>(Array.from(trialByIteration.keys()));
            latestGroups.forEach((group) => {
              const n = Number(group.iteration_no ?? group.iteration);
              if (Number.isFinite(n) && n > 0) iterationSet.add(n);
            });
            const runningIteration = Number(batchStatus.iteration);
            if (Number.isFinite(runningIteration) && runningIteration > 0 && runningGroups.length > 0) {
              iterationSet.add(runningIteration);
            }
            // 将 progress.iteration 也加入迭代集，让下拉框立即包含最新轮次
            const progressIter = Number((autoResearchStatus.progress as Record<string, unknown> | undefined)?.iteration);
            if (Number.isFinite(progressIter) && progressIter > 0) {
              iterationSet.add(progressIter);
            }
            const iterationOptions = Array.from(iterationSet)
              .sort((a, b) => b - a)
              .map((n) => ({ value: n, label: `第 ${n} 轮` }));
            let activeIteration = selectedAutoResearchIteration ?? iterationOptions[0]?.value;
            let activeTrial = activeIteration != null ? trialByIteration.get(activeIteration) : undefined;
            let groups = ((activeTrial?.batch_groups as unknown[]) || []) as Record<string, unknown>[];
            if ((!groups || groups.length === 0) && activeIteration != null) {
              groups = latestGroups.filter((group) => Number(group.iteration_no ?? group.iteration) === activeIteration);
            }
            if ((!groups || groups.length === 0) && activeIteration === runningIteration) {
              groups = runningGroups;
            }
            if ((!groups || groups.length === 0) && runningGroups.length > 1) {
              activeIteration = runningIteration;
              activeTrial = activeIteration != null ? trialByIteration.get(activeIteration) : undefined;
              groups = runningGroups;
            }
            if ((!groups || groups.length === 0) && latestGroups.length > 1) {
              const latestGroupIteration = Number(latestGroups[0]?.iteration_no ?? latestGroups[0]?.iteration);
              activeIteration = Number.isFinite(latestGroupIteration) ? latestGroupIteration : activeIteration;
              activeTrial = activeIteration != null ? trialByIteration.get(activeIteration) : undefined;
              groups = latestGroups;
            }
            if (!groups || groups.length <= 1) {
              // 如果选中轮次就是 progress 中的当前轮但 groups 还未就绪（batch_eval_status 尚未写入），展示加载状态
              if (activeIteration != null && Number.isFinite(progressIter) && activeIteration === progressIter) {
                return (
                  <Card size="small" style={{ marginBottom: 16, border: '1px solid #e8eef5', borderRadius: 12, boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)' }} title={<span>每轮多组改动 <Spin size="small" style={{ marginLeft: 8 }} /></span>}>
                    <Spin tip={`第 ${activeIteration} 轮实验正在准备中…`} style={{ width: '100%', padding: '20px 0' }} />
                  </Card>
                );
              }
              return null;
            }
            const failedCount = groups.filter((group) => ['failed', 'error', 'cancelled'].includes(String(group.status || '').toLowerCase())).length;
            const bestGroup = groups.find((group) => Boolean(group.is_best));
            const trialError = activeTrial?.error_message || activeTrial?.error;
            return (
              <Card
                size="small"
                style={{
                  marginBottom: 16,
                  border: '1px solid #e8eef5',
                  background: '#fff',
                  borderRadius: 12,
                  boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)',
                }}
                title={
                  <span style={{ fontSize: 14, fontWeight: 600, color: uiInk, letterSpacing: -0.3 }}>
                    每轮多组改动 <span style={{ fontSize: 12, fontWeight: 400, color: uiMuted, marginLeft: 8 }}>{groups.length} 组{bestGroup ? ` · 最优组 ${Number(bestGroup.group_idx ?? 0) + 1}` : ''}</span>
                  </span>
                }
                extra={
                  iterationOptions.length > 0 ? (
                    <Select
                      size="small"
                      style={{ width: 120 }}
                      value={activeIteration}
                      options={iterationOptions}
                      onChange={(v) => setSelectedAutoResearchIteration(Number(v))}
                    />
                  ) : null
                }
              >
                <Space direction="vertical" size={10} style={{ width: '100%' }}>
                  {trialError ? (
                    <Alert
                      type="error"
                      showIcon
                      message={`第 ${String(activeIteration ?? '-')} 轮失败原因`}
                      description={String(trialError)}
                    />
                  ) : null}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                    {groups.map((group, idx) => {
                      const status = String(group.status || 'unknown');
                      const override = (group.override as Record<string, unknown> | undefined) || {};
                      const structurePatch = (group.structure_patch as Record<string, unknown> | undefined) || {};
                      const globalPatch = (group.global_config_patch as Record<string, unknown> | undefined) || {};
                      const nodePatches = ((group.node_param_patches as unknown[]) || []) as Record<string, unknown>[];
                      const switches = ((structurePatch.node_switches as unknown[]) || []) as Record<string, unknown>[];
                      const patchCount = patchItemCount(override) + patchItemCount(globalPatch) + nodePatches.length + switches.length;
                      const scoreAdv = Number(group.score_advantage);
                      const mapeImprove = Number(group.mape_improvement);
                      return (
                        <div
                          key={`${String(group.comparison_id || idx)}-${idx}`}
                          style={{
                            border: `1px solid ${group.is_best ? '#b7eb8f' : status === 'failed' || status === 'error' ? '#ffa39e' : '#e8eef5'}`,
                            background: '#fff',
                            borderRadius: 10,
                            padding: 12,
                            minWidth: 0,
                          }}
                        >
                          {/* 头行：组号 + 状态圆点 + 方向 */}
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                            <span style={{ fontSize: 12, fontWeight: 600, color: uiInk }}>
                              组 {Number(group.group_idx ?? idx) + 1}
                            </span>
                            {group.is_best && <span style={{ fontSize: 10, background: uiGood, color: '#fff', borderRadius: 3, padding: '1px 5px' }}>最优</span>}
                            <StatusPill value={status} />
                            {group.candidate_source && <span style={{ fontSize: 11, color: uiMuted }}>{String(group.candidate_source)}</span>}
                            {group.selected_layer && <span style={{ fontSize: 11, color: uiAccent }}>{String(group.selected_layer)}</span>}
                          </div>
                          {group.hypothesis ? (
                            <Text style={{ fontSize: 12, color: uiMuted, display: 'block', marginBottom: 10 }}>
                              {String(group.hypothesis)}
                            </Text>
                          ) : null}
                          {/* 核心数值 */}
                          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 10, fontSize: 12 }}>
                            {Number.isFinite(mapeImprove) ? (
                              <span>
                                <span style={{ color: uiLabel }}>MAPE改善</span>{' '}
                                <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600, color: mapeImprove > 0 ? uiGood : uiBad }}>
                                  {mapeImprove > 0 ? '+' : ''}{mapeImprove.toFixed(4)}
                                </span>
                              </span>
                            ) : null}
                            {group.challenger_mape != null ? (
                              <span>
                                <span style={{ color: uiLabel }}>Challenger MAPE</span>{' '}
                                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{Number(group.challenger_mape).toFixed(4)}</span>
                              </span>
                            ) : null}
                            {group.duration_s != null ? (
                              <span>
                                <span style={{ color: uiLabel }}>耗时</span>{' '}
                                <span style={{ fontVariantNumeric: 'tabular-nums' }}>{Number(group.duration_s).toFixed(1)}s</span>
                              </span>
                            ) : null}
                            <span>
                              <span style={{ color: uiLabel }}>改动</span> {patchCount}
                            </span>
                          </div>
                          {/* ── 实时进度条（窗口级 + 日级） ── */}
                          {(group.windows_total != null || group.windows_done != null) ? (
                            <div style={{ margin: '4px 0' }}>
                              <Progress
                                percent={((group.windows_done ?? 0) / (group.windows_total ?? 1)) * 100}
                                size="small"
                                format={() => `窗口 ${group.window_index ?? group.windows_done ?? 0}/${group.windows_total ?? '?'}`}
                                status={
                                  group.status === 'running' || group.status === 'pending'
                                    ? 'active'
                                    : group.is_best || group.status === 'success' || group.is_verified
                                      ? 'success'
                                      : group.status === 'failed' || group.status === 'error'
                                        ? 'exception'
                                        : 'normal'
                                }
                                strokeLinecap="round"
                                style={{ marginBottom: (group.days_total ?? 0) > 0 ? 2 : 0 }}
                              />
                              {(group.days_total ?? 0) > 0 ? (
                                <Progress
                                  percent={((group.days_done ?? 0) / (group.days_total ?? 1)) * 100}
                                  size="small"
                                  status={(group.status === 'running' || group.status === 'pending') ? 'active' : 'normal'}
                                  format={() => {
                                    const dayInfo = group.current_day ? ` · ${String(group.current_day)}` : '';
                                    return `日 ${group.days_done ?? 0}/${group.days_total ?? '?'}${dayInfo}`;
                                  }}
                                  strokeLinecap="round"
                                />
                              ) : null}
                              {group.current_phase ? (
                                <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>
                                  {String(group.current_phase)}
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                          {group.error ? (
                            <Alert
                              type="error"
                              showIcon
                              style={{ marginBottom: 8 }}
                              message="本组失败"
                              description={String(group.error)}
                            />
                          ) : null}
                          <Space direction="vertical" size={8} style={{ width: '100%' }}>
                            {Object.keys(override).length > 0 ? (
                              <div>
                                <div style={sectionLabelStyle}>参数覆盖</div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                  {Object.entries(override).slice(0, 8).map(([k, v]) => (
                                    <Text key={k} code style={{ fontSize: 11 }}>{k}: {compactJsonValue(v)}</Text>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                            {switches.length > 0 ? (
                              <div>
                                <div style={sectionLabelStyle}>结构开关</div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                  {switches.slice(0, 8).map((sw, i) => (
                                    <span key={i} style={{ fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                                      <span style={{ width: 6, height: 6, borderRadius: '50%', background: sw.enabled === false ? uiBad : uiGood, display: 'inline-block' }} />
                                      <Text code style={{ fontSize: 11 }}>{String(sw.functionId || sw.node_id || '-')}</Text>
                                    </span>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                            {Object.keys(globalPatch).length > 0 ? (
                              <div>
                                <div style={sectionLabelStyle}>全局配置</div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                  {Object.entries(globalPatch).slice(0, 6).map(([k, v]) => (
                                    <Text key={k} code style={{ fontSize: 11 }}>{k}: {compactJsonValue(v)}</Text>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                            {nodePatches.length > 0 ? (
                              <div>
                                <div style={sectionLabelStyle}>节点参数</div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                  {nodePatches.slice(0, 6).map((np, i) => (
                                    <Text key={i} code style={{ fontSize: 11 }}>
                                      {String(np.functionId || np.node_id || '-')}: {compactJsonValue(np.param_patch || np)}
                                    </Text>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                          </Space>
                          <Collapse
                            ghost
                            size="small"
                            style={{ marginTop: 6 }}
                            items={[{
                              key: 'json',
                              label: '查看本组 JSON',
                              children: (
                                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto', background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 6, padding: 8, fontSize: 11 }}>
                                  {JSON.stringify(group, null, 2)}
                                </pre>
                              ),
                            }]}
                          />
                        </div>
                      );
                    })}
                  </div>
                </Space>
              </Card>
            );
          })()}
          {String(autoResearchStatus.status || '') === 'waiting_review' && (
            <Alert
              style={{ marginBottom: 10 }}
              type="warning"
              showIcon
              message="本轮已结束，等待你审核建议（或手动继续）后才会进入下一轮"
              action={
                <Space>
                  <Button size="small" onClick={onGenerateProposal} loading={proposalLoading}>
                    生成建议 Diff
                  </Button>
                  <Button size="small" type="primary" onClick={onContinueAutoResearch} loading={proposalLoading}>
                    继续下一轮
                  </Button>
                </Space>
              }
            />
          )}
          {(() => {
            return null;
          })()}

          {(() => {
            const best = autoResearchStatus.best_candidate as Record<string, unknown> | undefined;
            if (!best) return <Text type="secondary">暂无候选结果</Text>;
            const ev = (best.evaluation as Record<string, unknown> | undefined) || {};
            const challengerMape = ev.challenger_mape != null ? Number(ev.challenger_mape).toFixed(4) : '—';
            const baselineMape = ev.baseline_mape != null ? Number(ev.baseline_mape).toFixed(4) : '—';
            const mapeImprove = ev.mape_improvement != null ? Number(ev.mape_improvement).toFixed(4) : '—';
            const rmse = ev.challenger_rmse != null ? Number(ev.challenger_rmse).toFixed(4) : '—';
            return (
              <div
                style={{
                  marginBottom: 10,
                  padding: 12,
                  border: '1px solid #b7eb8f',
                  background: 'linear-gradient(135deg, #f6ffed 0%, #fafff5 100%)',
                  borderRadius: 10,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 12,
                  flexWrap: 'wrap',
                }}
              >
                <Space direction="vertical" size={2}>
                  <Space size={6} wrap>
                    <Text strong>当前最优</Text>
                    <Tag color="green">迭代 {String(best.iteration ?? '-')}</Tag>
                    <Tag color={ev.meets_constraints ? 'green' : 'default'}>
                      {ev.meets_constraints ? '约束达标' : '约束未达标'}
                    </Tag>
                  </Space>
                  <Space size={[8, 4]} wrap>
                    <Text type="secondary" style={{ fontSize: 12 }}>Baseline MAPE {baselineMape}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>MAPE 改善 {mapeImprove}</Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>RMSE {rmse}</Text>
                  </Space>
                </Space>
                <div
                  style={{
                    minWidth: 180,
                    padding: '8px 12px',
                    borderRadius: 10,
                    background: '#1677ff',
                    color: '#fff',
                    boxShadow: '0 6px 16px rgba(22, 119, 255, 0.22)',
                  }}
                >
                  <div style={{ fontSize: 11, opacity: 0.85, marginBottom: 2 }}>Challenger MAPE</div>
                  <div style={{ fontSize: 24, fontWeight: 700, lineHeight: 1.1 }}>{challengerMape}</div>
                </div>
              </div>
            );
          })()}

          {(() => {
            // 并行多组时，轮次实时对比面板无意义（不知道显示哪组的 Challenger），隐藏
            const _cfg = (autoResearchStatus.compare_config as Record<string, unknown> | undefined) || {};
            const _batchSize = Number(_cfg.batch_size ?? _cfg.max_concurrent_batches ?? 1);
            if (_batchSize > 1) return null;

            const liveWrap = (autoResearchStatus.current_iteration_live as Record<string, unknown> | undefined) || {};
            // 若实时数据为空，从 iterations 最近一轮降级取数
            const allIters = ((autoResearchStatus.iterations as unknown[]) || []) as Record<string, unknown>[];
            const lastIter = allIters.length > 0 ? allIters[allIters.length - 1] as Record<string, unknown> : null;
            const live = (liveWrap.live_summary as Record<string, unknown> | undefined)
              || (lastIter?.summary as Record<string, unknown> | undefined)
              || {};
            const prog = (liveWrap.progress as Record<string, unknown> | undefined) || {};
            const winRows = (liveWrap.live_window_results as Record<string, unknown>[] | undefined) || [];
            const bScore = live.aggregate_baseline_score as number | undefined;
            const cScore = live.aggregate_challenger_score as number | undefined;
            const adv = live.score_advantage as number | undefined;
            const done = live.windows_done as number | undefined;
            const total = live.windows_total as number | undefined;
            const currentPhase = String(live.current_phase || '');
            const isBaselineWarmup = currentPhase === 'baseline_warmup';
            // 额外判断：如果所有窗口的 baseline 和 challenger 完全相同，视为 Baseline 缓存阶段
            const allWindowsSame = Array.isArray(winRows) && winRows.length > 0 && winRows.every((r: Record<string, unknown>) => {
              const bs = r.baseline_score as number | null | undefined;
              const cs = r.challenger_score as number | null | undefined;
              return bs != null && cs != null && Math.abs(Number(bs) - Number(cs)) < 0.0001;
            });
            const hideChallenger = isBaselineWarmup || (allWindowsSame && !currentPhase.includes('challenger'));
            if (!Object.keys(live).length && !Object.keys(prog).length && !lastIter) return null;
            return (
              <Card
                size="small"
                style={autoResearchMutedCardStyle}
                title={
                  <span style={{ fontSize: 14, fontWeight: 600, color: uiInk, letterSpacing: -0.3 }}>
                    轮次实时对比（第 {String(autoResearchStatus.current_iteration ?? '-')} 轮）
                  </span>
                }
              >
                {hideChallenger && (
                  <Tag color="orange" style={{ marginBottom: 8 }}>正在建立 Baseline 缓存（首轮需要，后续复用）</Tag>
                )}
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
                  {done != null && total != null ? (
                    <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: uiAccent, display: 'inline-block' }} />
                      <span style={{ color: uiLabel }}>窗口进度</span> <span style={{ fontVariantNumeric: 'tabular-nums' }}>{done}/{total}</span>
                    </span>
                  ) : null}
                  {bScore != null ? (
                    <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ color: uiLabel }}>Baseline</span> <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>{Number(bScore).toFixed(4)}</span>
                    </span>
                  ) : null}
                  {!hideChallenger && cScore != null ? (
                    <span style={{ fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ color: uiLabel }}>Challenger</span> <span style={{ fontVariantNumeric: 'tabular-nums', fontWeight: 600, color: uiAccent }}>{Number(cScore).toFixed(4)}</span>
                    </span>
                  ) : null}
                  {!hideChallenger && adv != null ? (
                    <Tag color={Number(adv) > 0 ? 'green' : Number(adv) < 0 ? 'red' : 'default'}>
                      分差 {Number(adv) > 0 ? '+' : ''}{Number(adv).toFixed(4)}
                    </Tag>
                  ) : null}
                  {!hideChallenger && live.current_phase ? <Tag>{String(live.current_phase)}</Tag> : null}
                </div>
                {Array.isArray(winRows) && winRows.length > 0 && (
                  <Table
                    size="small"
                    pagination={false}
                    rowKey={(r: Record<string, unknown>) => `${String(r.start_date ?? '')}-${String(r.end_date ?? '')}`}
                    dataSource={winRows.slice(-5)}
                    columns={[
                      {
                        title: '时间窗',
                        render: (_, r: Record<string, unknown>) => `${String(r.start_date)} ~ ${String(r.end_date)}`,
                      },
                      {
                        title: 'Baseline',
                        render: (_, r: Record<string, unknown>) => {
                          const v = r.baseline_score as number | null | undefined;
                          return v != null ? Number(v).toFixed(4) : '—';
                        },
                      },
                      ...(!hideChallenger ? [{
                        title: 'Challenger',
                        render: (_: unknown, r: Record<string, unknown>) => {
                          const v = r.challenger_score as number | null | undefined;
                          return v != null ? Number(v).toFixed(4) : '—';
                        },
                      },
                      {
                        title: '分差',
                        render: (_: unknown, r: Record<string, unknown>) => {
                          const bs = r.baseline_score as number | null | undefined;
                          const cs = r.challenger_score as number | null | undefined;
                          if (bs == null || cs == null) return '—';
                          const d = Number(cs) - Number(bs);
                          return (
                            <Tag color={d > 0 ? 'green' : d < 0 ? 'red' : 'default'}>
                              {d > 0 ? '+' : ''}{d.toFixed(4)}
                            </Tag>
                          );
                        },
                      }] : []),
                    ]}
                  />
                )}
              </Card>
            );
          })()}

          {(() => {
            const rows = ((autoResearchStatus.iterations as unknown[]) || []) as Record<string, unknown>[];
            const okRows = rows.filter(r => r.status === 'success');
            const mapeSeries = okRows
              .map(r => Number((r.evaluation as Record<string, unknown> | undefined)?.mape_improvement))
              .filter(v => Number.isFinite(v));
            const advSeries = okRows
              .map(r => Number((r.evaluation as Record<string, unknown> | undefined)?.score_advantage))
              .filter(v => Number.isFinite(v));
            const liveWrap = (autoResearchStatus.current_iteration_live as Record<string, unknown> | undefined) || {};
            const liveSummary = (liveWrap.live_summary as Record<string, unknown> | undefined) || {};
            const liveAdv = Number(liveSummary.score_advantage);
            const liveB = Number(liveSummary.aggregate_baseline_score);
            const liveC = Number(liveSummary.aggregate_challenger_score);
            const hasLiveAdv = Number.isFinite(liveAdv);
            const hasLiveBC = Number.isFinite(liveB) && Number.isFinite(liveC) && liveB !== liveC;
            const advSeriesForRender = [...advSeries];
            if (hasLiveAdv) {
              advSeriesForRender.push(liveAdv);
            } else if (hasLiveBC) {
              advSeriesForRender.push(liveC - liveB);
            }
            if (mapeSeries.length === 0 && advSeriesForRender.length === 0) return null;
            const w = 320;
            const h = 70;
            const mapePath = renderTrendPath(mapeSeries, w, h);
            const advPath = renderTrendPath(advSeriesForRender, w, h);
            const mapePts = buildTrendPoints(mapeSeries, w, h);
            const advPts = buildTrendPoints(advSeriesForRender, w, h);
            const mapeBestIdx = mapeSeries.length > 0 ? mapeSeries.reduce((best, v, i, arr) => (v > arr[best] ? i : best), 0) : -1;
            const advBestIdx = advSeriesForRender.length > 0 ? advSeriesForRender.reduce((best, v, i, arr) => (v > arr[best] ? i : best), 0) : -1;
            const mapeMin = mapeSeries.length > 0 ? Math.min(...mapeSeries) : 0;
            const mapeMax = mapeSeries.length > 0 ? Math.max(...mapeSeries) : 0;
            const mapeZeroY = mapeSeries.length > 0 && mapeMin <= 0 && mapeMax >= 0
              ? h - ((0 - mapeMin) / ((mapeMax - mapeMin) || 1)) * h
              : null;
            const advMin = advSeriesForRender.length > 0 ? Math.min(...advSeriesForRender) : 0;
            const advMax = advSeriesForRender.length > 0 ? Math.max(...advSeriesForRender) : 0;
            const advZeroY = advSeriesForRender.length > 0 && advMin <= 0 && advMax >= 0
              ? h - ((0 - advMin) / ((advMax - advMin) || 1)) * h
              : null;
            return (
              <>
              </>
            );
          })()}

          </Card>

          <Table
            size="small"
            rowKey={(r: Record<string, unknown>) => String(r.comparison_id ?? r.iteration ?? Math.random())}
            pagination={{ pageSize: 10, size: 'small' }}
            dataSource={(() => {
              const allIters = ((autoResearchStatus.iterations as unknown[]) || []) as Record<string, unknown>[];
              if (allIters.length > 0) return [...allIters].reverse();
              // iterations 为空但实验在跑：显示当前轮的占位行
              const curIter = autoResearchStatus.current_iteration as number | undefined;
              if (curIter != null) {
                return [{ iteration: curIter, status: 'running', _placeholder: true }];
              }
              return [];
            })()}
            locale={{ emptyText: '暂无迭代记录（实验运行中…）' }}
            rowClassName={(row: Record<string, unknown>) =>
              row.is_control_round ? 'ant-table-row-disabled' : ''
            }
            columns={[
              {
                title: '轮次',
                dataIndex: 'iteration',
                width: 60,
                render: (v: number, row: Record<string, unknown>) => (
                  <span>
                    {v}
                    {row.is_control_round && (
                      <Tag color="default" style={{ marginLeft: 4, fontSize: 10 }}>对照</Tag>
                    )}
                  </span>
                ),
              },
              {
                title: '状态',
                dataIndex: 'status',
                width: 80,
                render: (v: string) => (
                  <Tag color={v === 'success' ? 'green' : v === 'failed' ? 'red' : v === 'running' ? 'blue' : 'default'} style={{ fontSize: 11 }}>
                    {v === 'success' ? '成功' : v === 'failed' ? '失败' : v === 'running' ? '运行中…' : v ?? '-'}
                  </Tag>
                ),
              },
              {
                title: 'MAPE 改善',
                render: (_, row: Record<string, unknown>) => {
                  const v = (row.evaluation as Record<string, unknown> | undefined)?.mape_improvement;
                  if (v == null) return <Text type="secondary">—</Text>;
                  const n = Number(v);
                  return <Tag color={n > 0 ? 'green' : n < 0 ? 'red' : 'default'}>{n > 0 ? '+' : ''}{n.toFixed(4)}</Tag>;
                },
                width: 110,
              },
              {
                title: 'Baseline MAPE',
                render: (_, row: Record<string, unknown>) => {
                  const v = (row.evaluation as Record<string, unknown> | undefined)?.baseline_mape;
                  return v != null ? <Tag color="blue">{Number(v).toFixed(4)}</Tag> : '—';
                },
                width: 120,
              },
              {
                title: 'Challenger MAPE',
                render: (_, row: Record<string, unknown>) => {
                  const v = (row.evaluation as Record<string, unknown> | undefined)?.challenger_mape;
                  return v != null ? Number(v).toFixed(4) : '—';
                },
                width: 130,
              },
              {
                title: 'RMSE',
                render: (_, row: Record<string, unknown>) => {
                  const v = (row.evaluation as Record<string, unknown> | undefined)?.challenger_rmse;
                  return v != null ? Number(v).toFixed(4) : '—';
                },
                width: 90,
              },
              {
                title: '约束',
                render: (_, row: Record<string, unknown>) => {
                  const ok = Boolean((row.evaluation as Record<string, unknown> | undefined)?.meets_constraints);
                  return <Tag color={ok ? 'green' : 'default'} style={{ fontSize: 11 }}>{ok ? '达标' : '未达标'}</Tag>;
                },
                width: 80,
              },
              {
                title: '覆盖参数',
                render: (_, row: Record<string, unknown>) => (
                  <Text code style={{ fontSize: 10 }}>
                    {JSON.stringify(row.override || {})}
                  </Text>
                ),
              },
              {
                // 任务 23.3：假设验证列
                title: '假设',
                width: 200,
                render: (_, row: Record<string, unknown>) => {
                  const hv = row.hypothesis_verification as Record<string, unknown> | undefined;
                  const hypothesis = hv?.hypothesis as string | undefined;
                  if (!hypothesis) return <Text type="secondary">—</Text>;
                  const verified = hv?.verified as boolean | undefined;
                  return (
                    <Space size={4}>
                      <Tooltip title={hypothesis}>
                        <Text style={{ fontSize: 11, maxWidth: 120, display: 'inline-block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {hypothesis}
                        </Text>
                      </Tooltip>
                      {verified !== undefined && (
                        <Tag color={verified ? 'success' : 'error'} style={{ fontSize: 10 }}>
                          {verified ? '✓ 成立' : '✗ 未成立'}
                        </Tag>
                      )}
                    </Space>
                  );
                },
              },
            ]}
          />

          {/* 任务 5.4：多目标 Pareto 前沿表格 */}
          {Array.isArray(autoResearchStatus.pareto_frontier) && (autoResearchStatus.pareto_frontier as unknown[]).length > 0 && (
            <Card
              size="small"
              title={<span style={{ fontSize: 14, fontWeight: 600, color: uiInk, letterSpacing: -0.3 }}>Pareto 前沿</span>}
              style={{ marginTop: 16, border: '1px solid #e8eef5', borderRadius: 12, boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)' }}
            >
              <Table
                size="small"
                rowKey={(r: Record<string, unknown>) => String(r.comparison_id ?? r.iteration ?? Math.random())}
                pagination={false}
                dataSource={(autoResearchStatus.pareto_frontier as unknown[]) as Record<string, unknown>[]}
                columns={[
                  { title: '迭代', dataIndex: 'iteration', width: 60 },
                  {
                    title: 'MAPE',
                    render: (_, row: Record<string, unknown>) => {
                      const v = (row.evaluation as Record<string, unknown> | undefined)?.challenger_mape;
                      return v != null ? <span style={{ fontVariantNumeric: 'tabular-nums', color: uiAccent, fontWeight: 600 }}>{Number(v).toFixed(4)}</span> : '—';
                    },
                    width: 100,
                  },
                  {
                    title: 'RMSE',
                    render: (_, row: Record<string, unknown>) => {
                      const v = (row.evaluation as Record<string, unknown> | undefined)?.challenger_rmse;
                      return v != null ? <span style={{ fontVariantNumeric: 'tabular-nums' }}>{Number(v).toFixed(4)}</span> : '—';
                    },
                    width: 100,
                  },
                  {
                    title: 'Bias',
                    render: (_, row: Record<string, unknown>) => {
                      const v = (row.evaluation as Record<string, unknown> | undefined)?.challenger_bias;
                      if (v == null) return '—';
                      const n = Number(v);
                      return <span style={{ fontVariantNumeric: 'tabular-nums', color: Math.abs(n) > 0.05 ? uiWarn : uiGood }}>{n.toFixed(4)}</span>;
                    },
                    width: 100,
                  },
                  {
                    title: 'P95 APE',
                    render: (_, row: Record<string, unknown>) => {
                      const v = (row.evaluation as Record<string, unknown> | undefined)?.challenger_p95_ape;
                      return v != null ? <span style={{ fontVariantNumeric: 'tabular-nums' }}>{Number(v).toFixed(4)}</span> : '—';
                    },
                    width: 100,
                  },
                  {
                    title: '耗时(s)',
                    render: (_, row: Record<string, unknown>) => {
                      const v = (row.evaluation as Record<string, unknown> | undefined)?.training_duration_s;
                      return v != null ? <span style={{ fontVariantNumeric: 'tabular-nums' }}>{Number(v).toFixed(1)}</span> : '—';
                    },
                    width: 80,
                  },
                  {
                    title: 'MAPE改善',
                    render: (_, row: Record<string, unknown>) => {
                      const v = (row.evaluation as Record<string, unknown> | undefined)?.mape_improvement;
                      if (v == null) return '—';
                      const n = Number(v);
                      return <span style={{ fontVariantNumeric: 'tabular-nums', color: n > 0 ? uiGood : uiBad, fontWeight: 600 }}>{n > 0 ? '+' : ''}{n.toFixed(4)}</span>;
                    },
                    width: 100,
                  },
                  {
                    title: '覆盖参数',
                    render: (_, row: Record<string, unknown>) => (
                      <Text code style={{ fontSize: 10 }}>{JSON.stringify(row.override || {})}</Text>
                    ),
                  },
                ]}
              />
            </Card>
          )}

          {renderVerificationQueueCard()}

          {autoResearchStatus.latest_applied_proposal_id && (
            <Alert
              style={{ marginTop: 10 }}
              type="success"
              showIcon
              message={`最新已应用建议: ${String(autoResearchStatus.latest_applied_proposal_id)}`}
            />
          )}
        </Card>
      )}

      {/* 候选池详情抽屉（任务 4.2） */}
      <Drawer
        title="候选池详情"
        open={detailDrawerOpen}
        onClose={() => setDetailDrawerOpen(false)}
        width={720}
        styles={{ body: { padding: 16 } }}
      >
        {loadingDetail ? (
          <Spin />
        ) : detailCandidate ? (
          <Space direction="vertical" style={{ width: '100%' }} size={16}>
            {/* 区块 1：配置快照 */}
            <Card size="small" title="配置快照">
              <Space direction="vertical" style={{ width: '100%' }} size={8}>
                <div>
                  <Text strong>challenger_override（评测量约覆盖）</Text>
                  <pre style={{ fontSize: 11, background: '#f5f5f5', padding: 8, borderRadius: 4, marginTop: 4 }}>
                    {JSON.stringify(detailCandidate.challenger_override ?? {}, null, 2)}
                  </pre>
                </div>
                <div>
                  <Text strong>effective_structure_patch（结构补丁）</Text>
                  <pre style={{ fontSize: 11, background: '#f5f5f5', padding: 8, borderRadius: 4, marginTop: 4 }}>
                    {JSON.stringify(detailCandidate.effective_structure_patch ?? {}, null, 2)}
                  </pre>
                </div>
                <div>
                  <Text strong>effective_parameter_patch（全局配置补丁）</Text>
                  <pre style={{ fontSize: 11, background: '#f5f5f5', padding: 8, borderRadius: 4, marginTop: 4 }}>
                    {JSON.stringify(detailCandidate.effective_parameter_patch ?? {}, null, 2)}
                  </pre>
                </div>
              </Space>
            </Card>

            {/* 区块 2：Diff 对比 */}
            <Card size="small" title="Diff 对比（相对 Baseline）">
              {(() => {
                const diff = detailCandidate.diff_from_baseline as Record<string, unknown> | undefined;
                if (!diff) return <Text type="secondary">无 diff 数据</Text>;
                const changed = (diff.changed_keys as Array<Record<string, unknown>> | undefined) ?? [];
                const added = (diff.added_keys as string[] | undefined) ?? [];
                const removed = (diff.removed_keys as string[] | undefined) ?? [];
                if (changed.length === 0 && added.length === 0 && removed.length === 0) {
                  return <Text type="secondary">与 Baseline 完全相同（无差异）</Text>;
                }
                return (
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={[
                      ...changed.map(r => ({ key: r.key, type: '变更', field: r.key, baseline: String(r.baseline ?? ''), challenger: String(r.challenger ?? '') })),
                      ...added.map(k => ({ key: k, type: '新增', field: k, baseline: '-', challenger: '(新增)' })),
                      ...removed.map(k => ({ key: k, type: '移除', field: k, baseline: '(原有)', challenger: '-' })),
                    ]}
                    columns={[
                      { title: '字段', dataIndex: 'field', key: 'field', width: 200, render: v => <Text code style={{ fontSize: 11 }}>{v}</Text> },
                      { title: 'Baseline', dataIndex: 'baseline', key: 'baseline', render: v => <Text type="secondary">{v}</Text> },
                      { title: 'Challenger', dataIndex: 'challenger', key: 'challenger', render: v => <Text strong>{v}</Text> },
                    ]}
                  />
                );
              })()}
            </Card>

            {/* 区块 3：指标 */}
            <Card size="small" title="指标">
              {(() => {
                const summary = detailCandidate.summary as Record<string, unknown> | undefined;
                if (!summary) return <Text type="secondary">无指标数据</Text>;
                return (
                  <Descriptions size="small" column={2} bordered>
                    <Descriptions.Item label="聚合方法">{String(summary.aggregate_method ?? '-')}</Descriptions.Item>
                    <Descriptions.Item label="分差（Challenger - Baseline）">
                      {summary.score_advantage != null ? Number(summary.score_advantage).toFixed(4) : '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label="Baseline 聚合分">
                      {summary.aggregate_baseline_score != null ? Number(summary.aggregate_baseline_score).toFixed(4) : '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label="Challenger 聚合分">
                      {summary.aggregate_challenger_score != null ? Number(summary.aggregate_challenger_score).toFixed(4) : '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label="总窗口数">{String(summary.windows_total ?? '-')}</Descriptions.Item>
                    <Descriptions.Item label="Challenger 优胜窗数">{String(summary.windows_challenger_better ?? '-')}</Descriptions.Item>
                    <Descriptions.Item label="满足分差">{summary.meets_score_margin ? '✓' : '✗'}</Descriptions.Item>
                    <Descriptions.Item label="满足优胜窗数">{summary.meets_win_count ? '✓' : '✗'}</Descriptions.Item>
                  </Descriptions>
                );
              })()}
            </Card>

            {/* 区块 4：关联信息 */}
            <Card size="small" title="关联信息">
              <Descriptions size="small" column={1} bordered>
                <Descriptions.Item label="comparison_id（比对任务 ID）">
                  <Text code style={{ fontSize: 11 }}>{String(detailCandidate.comparison_id ?? '-')}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="source_run_id（来源 AutoResearch run）">
                  <Text code style={{ fontSize: 11 }}>{String(detailCandidate.source_run_id || '（手动比对）')}</Text>
                </Descriptions.Item>
                <Descriptions.Item label="source_iteration（来源迭代轮次）">
                  {String(detailCandidate.source_iteration || '-')}
                </Descriptions.Item>
                <Descriptions.Item label="feature_recipe_id（特征配方 ID）">
                  {String(detailCandidate.feature_recipe_id || '-')}
                </Descriptions.Item>
              </Descriptions>
            </Card>
          </Space>
        ) : (
          <Text type="secondary">暂无数据</Text>
        )}
      </Drawer>

      <Modal
        title="自动实验建议 Diff 审核"
        open={proposalModalOpen}
        width="min(96vw, 1280px)"
        style={{ top: 24 }}
        styles={{ body: { maxHeight: 'calc(100vh - 180px)', overflowY: 'auto' } }}
        onCancel={() => setProposalModalOpen(false)}
        onOk={onApplyProposal}
        okText="接受并应用"
        cancelText="关闭"
        confirmLoading={proposalLoading}
        footer={[
          <Button key="reject" danger onClick={onRejectProposal} loading={proposalLoading}>
            拒绝建议
          </Button>,
          <Button key="close" onClick={() => setProposalModalOpen(false)}>
            关闭
          </Button>,
          <Button key="apply" type="primary" onClick={onApplyProposal} loading={proposalLoading}>
            接受并应用
          </Button>,
        ]}
      >
        {activeProposal ? (
          <>
            {glmMeta && (
              <Alert
                type={glmMeta.enabled ? ((glmMeta.candidates_count as number) > 0 ? 'success' : 'warning') : 'error'}
                showIcon
                style={{ marginBottom: 8 }}
                message="GLM 调用信息（用于排障）"
                description={
                  <div style={{ fontSize: 12 }}>
                    <div>enabled: {String(glmMeta.enabled)}</div>
                    <div>llm_used: {String(glmMeta.llm_used)}</div>
                    <div>candidates_count: {String(glmMeta.candidates_count)}</div>
                    <div>memory_hit_count: {String(glmMeta.memory_hit_count ?? 0)}</div>
                    <div>memory_top_k: {String(glmMeta.memory_top_k ?? '-')}</div>
                    {glmMeta.llm_error ? <div style={{ color: '#cf1322' }}>llm_error: {String(glmMeta.llm_error)}</div> : null}
                    {glmMeta.model ? <div>model: {String(glmMeta.model)}</div> : null}
                  </div>
                }
              />
            )}
            {proposalTableRows.length > 0 && (
              <Table
                size="small"
                pagination={false}
                scroll={{ x: 'max-content' }}
                rowKey={(r: Record<string, unknown>) => String(r.proposal_id)}
                dataSource={proposalTableRows}
                style={{ marginBottom: 8 }}
                onRow={(record: Record<string, unknown>) => ({
                  onClick: () => setActiveProposal({ ...record }),
                })}
                columns={[
                  {
                    title: '候选',
                    render: (_, r: Record<string, unknown>) => String(r.candidate_index ?? '-'),
                    width: 60,
                  },
                  {
                    title: '来源',
                    render: (_, r: Record<string, unknown>) => {
                      const used = Boolean(r.llm_used);
                      if (!used) return <Tag>rules</Tag>;
                      const m = String(r.llm_model || 'glm');
                      return <Tag color="purple">{m}</Tag>;
                    },
                    width: 90,
                  },
                  {
                    title: 'ID',
                    render: (_, r: Record<string, unknown>) => (
                      <Text code style={{ fontSize: 10 }}>{String(r.proposal_id)}</Text>
                    ),
                  },
                  {
                    title: '评分',
                    render: (_, r: Record<string, unknown>) => Number(r.score ?? 0).toFixed(2),
                    width: 90,
                  },
                  {
                    title: '检索分',
                    render: (_, r: Record<string, unknown>) => {
                      const top = getTopRetrievalScore(r);
                      if (top === null) return <Text type="secondary">-</Text>;
                      return top.toFixed(3);
                    },
                    width: 90,
                  },
                  {
                    title: '风险',
                    render: (_, r: Record<string, unknown>) => {
                      const risk = String(r.risk_level || 'low');
                      return <Tag color={risk === 'high' ? 'red' : risk === 'medium' ? 'orange' : 'green'}>{risk}</Tag>;
                    },
                    width: 90,
                  },
                  {
                    title: '推荐',
                    render: (_, r: Record<string, unknown>) => (
                      String(r.proposal_id) === String(recommendedProposalId) ? <Tag color="blue">推荐</Tag> : null
                    ),
                    width: 80,
                  },
                  {
                    title: '当前',
                    render: (_, r: Record<string, unknown>) => (
                      String(r.proposal_id) === activeProposalId ? <Tag color="gold">已选</Tag> : null
                    ),
                    width: 80,
                  },
                  {
                    title: '操作',
                    render: (_, r: Record<string, unknown>) => (
                      <Button size="small" onClick={() => setActiveProposal({ ...r })}>
                        查看
                      </Button>
                    ),
                    width: 80,
                  },
                ]}
              />
            )}
            <Descriptions size="small" column={2}>
              <Descriptions.Item label="Proposal ID">
                <Text code>{String(activeProposal.proposal_id || '-')}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="风险等级">
                <Tag color={
                  activeProposal.risk_level === 'high' ? 'red' :
                  activeProposal.risk_level === 'medium' ? 'orange' : 'green'
                }>
                  {String(activeProposal.risk_level || 'low')}
                </Tag>
              </Descriptions.Item>
            </Descriptions>
            <div style={{ marginBottom: 8 }}>
              {((activeProposal.notes as unknown[]) || []).map((n, i) => (
                <Tag key={i}>{String(n)}</Tag>
              ))}
              {activeProposal.llm_error && (
                <Tag color="red">llm_error: {String(activeProposal.llm_error)}</Tag>
              )}
            </div>
            {/* 假设卡片（任务 23.1）：有 hypothesis 字段时显示 */}
            {activeProposal.hypothesis && (
              <Card
                size="small"
                style={{ marginBottom: 8, borderColor: '#91caff', background: '#f0f7ff' }}
                styles={{ header: { background: '#e6f4ff' } }}
                title={<span>🔬 实验假设</span>}
              >
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  {activeProposal.observation && (
                    <div>
                      <Text type="secondary" style={{ fontSize: 11 }}>观察：</Text>
                      <Text style={{ fontSize: 12 }}>{String(activeProposal.observation)}</Text>
                    </div>
                  )}
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>假设：</Text>
                    <Text strong style={{ fontSize: 12 }}>{String(activeProposal.hypothesis)}</Text>
                    {activeProposal.hypothesis_type && (
                      <Tag color="blue" style={{ marginLeft: 8, fontSize: 11 }}>
                        {String(activeProposal.hypothesis_type)}
                      </Tag>
                    )}
                  </div>
                  {activeProposal.expected_outcome && (() => {
                    const eo = activeProposal.expected_outcome as Record<string, unknown>;
                    return (
                      <div>
                        <Text type="secondary" style={{ fontSize: 11 }}>预期：</Text>
                        <Text style={{ fontSize: 12 }}>
                          {String(eo.description || `${eo.metric} ${eo.direction} ${eo.threshold}`)}
                        </Text>
                      </div>
                    );
                  })()}
                  {activeProposal.fallback_if_failed && (
                    <div>
                      <Text type="secondary" style={{ fontSize: 11 }}>若未成立：</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>{String(activeProposal.fallback_if_failed)}</Text>
                    </div>
                  )}
                </Space>
              </Card>
            )}
            {/* 误差诊断卡片（任务 4.3） */}
            {activeProposal.error_diagnosis && (() => {
              const ed = activeProposal.error_diagnosis as Record<string, unknown>;
              const sourceColorMap: Record<string, string> = {
                weekend_pattern_shift: 'orange',
                data_coverage_insufficient: 'red',
                outlier_days: 'volcano',
                parameter_saturation: 'blue',
              };
              const source = String(ed.primary_error_source ?? '');
              const evidence = ed.evidence as Record<string, unknown> | undefined;
              return (
                <Card
                  size="small"
                  title="误差诊断"
                  style={{ marginBottom: 8, borderColor: '#faad14' }}
                  styles={{ header: { background: '#fffbe6' } }}
                >
                  <Space wrap>
                    <span>主要误差来源：</span>
                    <Tag color={sourceColorMap[source] ?? 'default'}>{source || '-'}</Tag>
                    <Tag color={ed.confidence === 'high' ? 'green' : ed.confidence === 'medium' ? 'orange' : 'default'}>
                      置信度: {String(ed.confidence ?? '-')}
                    </Tag>
                    <Tag color={ed.data_sufficiency === 'sufficient' ? 'green' : ed.data_sufficiency === 'partial' ? 'orange' : 'red'}>
                      数据充足度: {String(ed.data_sufficiency ?? '-')}
                    </Tag>
                  </Space>
                  {evidence && (
                    <Descriptions size="small" column={3} style={{ marginTop: 8 }}>
                      {evidence.avg_mape != null && (
                        <Descriptions.Item label="avg_mape（平均 MAPE）">{Number(evidence.avg_mape).toFixed(4)}</Descriptions.Item>
                      )}
                      {evidence.max_daily_mape != null && (
                        <Descriptions.Item label="max_daily_mape（最大 MAPE）">{Number(evidence.max_daily_mape).toFixed(4)}</Descriptions.Item>
                      )}
                      {evidence.total_days != null && (
                        <Descriptions.Item label="total_days / success_days">
                          {String(evidence.success_days ?? '-')} / {String(evidence.total_days ?? '-')}
                        </Descriptions.Item>
                      )}
                    </Descriptions>
                  )}
                </Card>
              );
            })()}
            <Card size="small" title="search_space_patch" style={{ marginBottom: 8 }}>
              <pre style={{ fontSize: 11, maxHeight: 180, overflow: 'auto', margin: 0 }}>
                {JSON.stringify(activeProposal.search_space_patch || {}, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="evaluation_contract_patch" style={{ marginBottom: 8 }}>
              <pre style={{ fontSize: 11, maxHeight: 180, overflow: 'auto', margin: 0 }}>
                {JSON.stringify(activeProposal.evaluation_contract_patch || {}, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="global_config_patch（模板 metadata.global_config）" style={{ marginBottom: 8 }}>
              <pre style={{ fontSize: 11, maxHeight: 160, overflow: 'auto', margin: 0 }}>
                {JSON.stringify(activeProposal.global_config_patch || {}, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="node_param_patches（节点 config，特征/模型参数层）" style={{ marginBottom: 8 }}>
              <pre style={{ fontSize: 11, maxHeight: 200, overflow: 'auto', margin: 0 }}>
                {JSON.stringify(activeProposal.node_param_patches || [], null, 2)}
              </pre>
            </Card>
            <Card size="small" title="structure_patch" style={{ marginBottom: 8 }}>
              <pre style={{ fontSize: 11, maxHeight: 160, overflow: 'auto', margin: 0 }}>
                {JSON.stringify(activeProposal.structure_patch || {}, null, 2)}
              </pre>
            </Card>
            <Card size="small" title="参考历史案例（memory_references）" style={{ marginBottom: 8 }}>
              {Array.isArray(activeProposal.memory_references) && (activeProposal.memory_references as unknown[]).length > 0 ? (
                <pre style={{ fontSize: 11, maxHeight: 140, overflow: 'auto', margin: 0 }}>
                  {JSON.stringify(activeProposal.memory_references || [], null, 2)}
                </pre>
              ) : (
                <Text type="secondary">暂无匹配历史案例</Text>
              )}
            </Card>
            <Card size="small" title="校验结果">
              {(() => {
                const v = (activeProposal.validation as Record<string, unknown> | undefined) || {};
                const valid = Boolean(v.valid);
                const errs = ((v.errors as unknown[]) || []).map(String);
                return (
                  <>
                    <Tag color={valid ? 'green' : 'red'}>{valid ? '通过' : '失败'}</Tag>
                    {!valid && errs.map((e, i) => (
                      <div key={i} style={{ color: '#cf1322', fontSize: 12 }}>{e}</div>
                    ))}
                  </>
                );
              })()}
            </Card>
          </>
        ) : (
          <Text type="secondary">暂无建议草案</Text>
        )}
      </Modal>

      <Modal
        title="Baseline / Challenger 全量对照"
        open={structureCompareOpen}
        onCancel={() => setStructureCompareOpen(false)}
        footer={[
          <Button key="ref" loading={structureCompareLoading} onClick={onOpenStructureCompare}>
            按当前状态刷新
          </Button>,
          <Button key="close" type="primary" onClick={() => setStructureCompareOpen(false)}>
            关闭
          </Button>,
        ]}
        width={960}
        destroyOnClose
      >
        {autoResearchStatus && (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              message="如何理解本表"
              description={
                <span>
                  Baseline 使用同一模板文件，不参与结构补丁（节点启用状态以模板 JSON 为准）。
                  Challenger 在相同模板上叠加后端当轮{' '}
                  <Text code>effective_structure_patch</Text>（关注模型 + 已应用的提案补丁等），以及{' '}
                  <Text code>effective_parameter_patch</Text>
                  （<Text code>global_config_patch</Text> + <Text code>node_param_patches</Text>，应用于 challenger 全局配置与节点参数）。
                  下方摘要汇总四条典型并联预报（XGBoost / LightGBM / CatBoost / Ridge）；完整开关见表格。
                </span>
              }
            />
            <Space wrap style={{ marginBottom: 10 }}>
              <Tag>
                baseline_workflow_id:{' '}
                <Text code>{String(autoResearchStatus.baseline_workflow_id || '-')}</Text>
              </Tag>
              <Tag color="blue">
                关注模型:{' '}
                {(() => {
                  const dc = (autoResearchStatus.discovery_context as Record<string, unknown>) || {};
                  const pref = dc.preferred_model_operator_ids as unknown;
                  const arr = Array.isArray(pref) ? pref.map(String) : [];
                  return arr.length ? arr.join(', ') : '（未选）';
                })()}
              </Tag>
            </Space>
            <Card size="small" title="并联预报模型（叶子分支）" style={{ marginBottom: 12 }}>
              <Descriptions column={1} size="small">
                <Descriptions.Item label="Baseline">
                  <Space wrap align="center">
                    {structureCompareForecastSummary.baselineLabels.length === 0 ? (
                      <Text type="secondary">模板中上述四个叶子节点均未启用或未出现</Text>
                    ) : (
                      <>
                        {structureCompareForecastSummary.baselineLabels.map((name) => (
                          <Tag key={`b-${name}`} color="green">{name}</Tag>
                        ))}
                        <Text type="secondary">共 {structureCompareForecastSummary.baselineLabels.length} 个</Text>
                      </>
                    )}
                  </Space>
                </Descriptions.Item>
                <Descriptions.Item label="Challenger">
                  <Space wrap align="center">
                    {structureCompareForecastSummary.challengerLabels.length === 0 ? (
                      <Text type="secondary">当前补丁下无启用的并联叶子模型</Text>
                    ) : (
                      <>
                        {structureCompareForecastSummary.challengerLabels.map((name) => (
                          <Tag key={`c-${name}`} color="blue">{name}</Tag>
                        ))}
                        <Text type="secondary">共 {structureCompareForecastSummary.challengerLabels.length} 个</Text>
                      </>
                    )}
                  </Space>
                </Descriptions.Item>
                {structureCompareEnsemble && (
                  <Descriptions.Item label="集成 ensemble_forecast">
                    <Space wrap>
                      <span>Baseline <Tag color={structureCompareEnsemble.baseline ? 'green' : 'default'}>{structureCompareEnsemble.baseline ? '开' : '关'}</Tag></span>
                      <span>Challenger <Tag color={structureCompareEnsemble.challenger ? 'green' : 'default'}>{structureCompareEnsemble.challenger ? '开' : '关'}</Tag></span>
                    </Space>
                  </Descriptions.Item>
                )}
              </Descriptions>
            </Card>
            <Spin spinning={structureCompareLoading}>
              <Table
                size="small"
                pagination={{ pageSize: 20, showSizeChanger: false }}
                rowKey="key"
                dataSource={structureCompareRows}
                scroll={{ x: 820 }}
                columns={[
                  {
                    title: '算子（展示名）',
                    dataIndex: 'function_id',
                    width: 200,
                    ellipsis: true,
                    render: (fid: string) => {
                      const { title, registryHint } = formatFunctionIdForUi(fid);
                      if (!registryHint) return <Text>{title}</Text>;
                      return (
                        <Tooltip title={`后端注册 functionId：${registryHint}`}>
                          <Text>{title}</Text>
                        </Tooltip>
                      );
                    },
                  },
                  { title: '节点标签', dataIndex: 'label', width: 160, ellipsis: true },
                  {
                    title: 'Baseline 启用',
                    dataIndex: 'baseline_enabled',
                    width: 110,
                    align: 'center',
                    render: (v: boolean) => (
                      <Tag color={v ? 'green' : 'default'}>{v ? '开' : '关'}</Tag>
                    ),
                  },
                  {
                    title: 'Challenger 启用',
                    dataIndex: 'challenger_enabled',
                    width: 120,
                    align: 'center',
                    render: (v: boolean) => (
                      <Tag color={v ? 'green' : 'default'}>{v ? '开' : '关'}</Tag>
                    ),
                  },
                  {
                    title: '差异',
                    key: 'diff',
                    width: 72,
                    align: 'center',
                    render: (_: unknown, r: BaselineChallengerStructureRow) =>
                      r.baseline_enabled !== r.challenger_enabled ? (
                        <Tag color="orange">有</Tag>
                      ) : (
                        <Tag>无</Tag>
                      ),
                  },
                  {
                    title: 'node_id',
                    dataIndex: 'node_id',
                    ellipsis: true,
                  },
                ]}
              />
            </Spin>

            {/* 区块 2：节点参数对照（任务 26.4） */}
            {(() => {
              const rp = (autoResearchStatus.runtime_patch as Record<string, unknown> | undefined) || {};
              const npp = (rp.node_param_patches as Record<string, unknown>[] | undefined) || [];
              if (!npp.length) return null;
              return (
                <Card size="small" title="节点参数对照（已应用的参数改动）" style={{ marginTop: 12 }}>
                  <Table
                    size="small"
                    pagination={false}
                    rowKey={(r: Record<string, unknown>, i) => `npp-${i}`}
                    dataSource={npp}
                    columns={[
                      { title: '节点 functionId', dataIndex: 'functionId', width: 180 },
                      { title: 'node_id', dataIndex: 'node_id', width: 160, ellipsis: true },
                      {
                        title: '参数改动',
                        render: (_, row: Record<string, unknown>) => {
                          const pp = row.param_patch as Record<string, unknown> | undefined;
                          if (!pp) return '—';
                          return (
                            <Space wrap size={4}>
                              {Object.entries(pp).map(([k, v]) => (
                                <span key={k} style={{ background: '#fff7e6', padding: '2px 6px', borderRadius: 4, fontSize: 11 }}>
                                  <Text type="secondary">{k}: </Text>
                                  <Tag color="orange" style={{ fontSize: 11 }}>{JSON.stringify(v)}</Tag>
                                </span>
                              ))}
                            </Space>
                          );
                        },
                      },
                    ]}
                  />
                </Card>
              );
            })()}

            {/* 区块 3：全局配置对照（任务 26.4） */}
            {(() => {
              const rp = (autoResearchStatus.runtime_patch as Record<string, unknown> | undefined) || {};
              const gcp = (rp.global_config_patch as Record<string, unknown> | undefined) || {};
              const entries = Object.entries(gcp);
              if (!entries.length) return null;
              return (
                <Card size="small" title="全局配置对照（已应用的全局配置改动）" style={{ marginTop: 12 }}>
                  <Table
                    size="small"
                    pagination={false}
                    rowKey={(_, i) => `gcp-${i}`}
                    dataSource={entries.map(([k, v]) => ({ key: k, value: v }))}
                    columns={[
                      { title: '配置项', dataIndex: 'key', width: 200 },
                      {
                        title: 'Challenger 值',
                        dataIndex: 'value',
                        render: (v: unknown) => <Tag color="orange" style={{ fontSize: 11 }}>{JSON.stringify(v)}</Tag>,
                      },
                    ]}
                  />
                </Card>
              );
            })()}

            {/* 区块 4：评测量约对照（Baseline vs Challenger，任务 26.4 扩展） */}
            {(() => {
              const rp = (autoResearchStatus.runtime_patch as Record<string, unknown> | undefined) || {};
              const evalPatch = (rp.evaluation_contract_patch as Record<string, unknown> | undefined) || {};
              const baseContract = (autoResearchStatus.evaluation_contract as Record<string, unknown> | undefined) || {};
              const override = (autoResearchStatus.current_override as Record<string, unknown> | undefined) || {};

              // 合并所有有改动的参数：evaluation_contract_patch + current_override
              const allChanges: Record<string, { baseline: unknown; challenger: unknown; source: string }> = {};
              for (const [k, v] of Object.entries(evalPatch)) {
                allChanges[k] = { baseline: baseContract[k], challenger: v, source: 'eval_patch' };
              }
              for (const [k, v] of Object.entries(override)) {
                if (!(k in allChanges)) {
                  allChanges[k] = { baseline: baseContract[k], challenger: v, source: 'override' };
                }
              }
              const rows = Object.entries(allChanges).map(([k, info]) => ({ key: k, ...info }));
              if (!rows.length) return null;

              return (
                <Card size="small" title="评测量约对照（Baseline vs Challenger 参数差异）" style={{ marginTop: 12 }}>
                  <Table
                    size="small"
                    pagination={false}
                    rowKey="key"
                    dataSource={rows}
                    columns={[
                      { title: '参数', dataIndex: 'key', width: 180 },
                      {
                        title: 'Baseline 值',
                        dataIndex: 'baseline',
                        width: 140,
                        render: (v: unknown) => v != null
                          ? <Tag>{JSON.stringify(v)}</Tag>
                          : <Text type="secondary">（模板默认）</Text>,
                      },
                      {
                        title: 'Challenger 值',
                        dataIndex: 'challenger',
                        width: 140,
                        render: (v: unknown) => <Tag color="orange" style={{ fontWeight: 600 }}>{JSON.stringify(v)}</Tag>,
                      },
                      {
                        title: '来源',
                        dataIndex: 'source',
                        width: 100,
                        render: (v: string) => (
                          <Tag color={v === 'eval_patch' ? 'purple' : 'blue'} style={{ fontSize: 10 }}>
                            {v === 'eval_patch' ? '已应用建议' : '本轮采样'}
                          </Tag>
                        ),
                      },
                    ]}
                  />
                </Card>
              );
            })()}

            {/* 区块 5：并发批量评估对比（上一轮所有组 vs Baseline） */}
            {(() => {
              const batchResults = (autoResearchStatus as Record<string, unknown>).last_batch_results as Record<string, unknown>[] | undefined;
              if (!batchResults || batchResults.length <= 1) return null;
              return (
                <Card
                  size="small"
                  title={`并发批量评估对比（上一轮 ${batchResults.length} 组 vs Baseline）`}
                  style={{ marginTop: 12, borderColor: '#722ed1' }}
                  styles={{ header: { background: '#f9f0ff' } }}
                >
                  <Table
                    size="small"
                    pagination={false}
                    rowKey={(r: Record<string, unknown>) => String(r.group_idx ?? Math.random())}
                    dataSource={batchResults as Record<string, unknown>[]}
                    rowClassName={(r: Record<string, unknown>) => r.is_best ? 'ant-table-row-selected' : ''}
                    columns={[
                      {
                        title: '组',
                        dataIndex: 'group_idx',
                        width: 60,
                        render: (v: number, r: Record<string, unknown>) => (
                          <span>
                            {v}
                            {r.is_best && <Tag color="gold" style={{ marginLeft: 4, fontSize: 10 }}>最优</Tag>}
                          </span>
                        ),
                      },
                      {
                        title: '覆盖参数',
                        dataIndex: 'override',
                        render: (v: Record<string, unknown>) => (
                          <Text code style={{ fontSize: 10 }}>{JSON.stringify(v || {})}</Text>
                        ),
                      },
                      {
                        title: 'MAPE 改善',
                        dataIndex: 'mape_improvement',
                        width: 110,
                        render: (v: number | null) => {
                          if (v == null) return <Text type="secondary">—</Text>;
                          return <Tag color={v > 0 ? 'success' : 'error'}>{v > 0 ? '+' : ''}{Number(v).toFixed(4)}</Tag>;
                        },
                      },
                      {
                        title: '分差',
                        dataIndex: 'score_advantage',
                        width: 100,
                        render: (v: number | null) => {
                          if (v == null) return <Text type="secondary">—</Text>;
                          return <Tag color={Number(v) > 0 ? 'success' : 'error'}>{Number(v) > 0 ? '+' : ''}{Number(v).toFixed(4)}</Tag>;
                        },
                      },
                      {
                        title: '状态',
                        dataIndex: 'status',
                        width: 80,
                        render: (v: string) => (
                          <Tag color={v === 'success' ? 'green' : v === 'failed' ? 'red' : 'default'} style={{ fontSize: 10 }}>
                            {v === 'success' ? '成功' : v === 'failed' ? '失败' : v}
                          </Tag>
                        ),
                      },
                    ]}
                  />
                </Card>
              );
            })()}

            {/* 区块 6：GLM 调用记录已移至自动实验状态卡片 */}
          </>
        )}
      </Modal>

      <Modal
        title="自动实验一键自检"
        open={selfcheckOpen}
        onCancel={() => setSelfcheckOpen(false)}
        footer={[
          <Button key="close" onClick={() => setSelfcheckOpen(false)}>
            关闭
          </Button>,
        ]}
        width={900}
      >
        {selfcheckResult ? (
          <>
            <Space style={{ marginBottom: 8 }} wrap>
              <Tag>run_id: {String(selfcheckResult.run_id || '-')}</Tag>
              <Tag>status: {String(selfcheckResult.status || '-')}</Tag>
              <Tag>checked_at: {String(selfcheckResult.checked_at || '-')}</Tag>
            </Space>
            <Table
              size="small"
              pagination={false}
              rowKey={(r: Record<string, unknown>, i) => `${String(r.item || i)}-${i}`}
              dataSource={((selfcheckResult.checks as unknown[]) || []) as Record<string, unknown>[]}
              columns={[
                {
                  title: '检查项',
                  dataIndex: 'item',
                  width: 180,
                },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 90,
                  render: (v: unknown) => {
                    const s = String(v || '');
                    return (
                      <Tag color={s === 'pass' ? 'green' : s === 'warn' ? 'orange' : s === 'fail' ? 'red' : 'blue'}>
                        {s}
                      </Tag>
                    );
                  },
                },
                {
                  title: '详情',
                  dataIndex: 'detail',
                  render: (v: unknown) => <Text>{String(v || '-')}</Text>,
                },
                {
                  title: '建议',
                  dataIndex: 'suggestion',
                  render: (v: unknown) => <Text type="secondary">{String(v || '-')}</Text>,
                },
              ]}
            />
          </>
        ) : (
          <Text type="secondary">暂无自检结果</Text>
        )}
      </Modal>

      <Drawer
        title="下轮生效改动 JSON"
        open={runtimePatchOpen}
        onClose={() => setRuntimePatchOpen(false)}
        width={720}
      >
        <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, background: '#fafafa', border: '1px solid #f0f0f0', borderRadius: 8, padding: 12 }}>
          {JSON.stringify((() => {
            const history = (((autoResearchStatus as Record<string, unknown> | null)?.runtime_patch_history as unknown[] | undefined) || []) as Record<string, unknown>[];
            const idx = selectedRuntimePatchIndex != null && history[selectedRuntimePatchIndex]
              ? selectedRuntimePatchIndex
              : (history.length > 0 ? history.length - 1 : null);
            const item = idx != null ? history[idx] : null;
            return item || ((autoResearchStatus?.runtime_patch as Record<string, unknown> | undefined) || {});
          })(), null, 2)}
        </pre>
      </Drawer>

      <Modal
        title="加入复验池"
        open={verificationModalOpen}
        onOk={enqueueVerification}
        onCancel={() => setVerificationModalOpen(false)}
        confirmLoading={enqueueingVerification}
        okText="加入复验池"
        width={760}
      >
        {verificationCandidate && (
          <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
            <Descriptions.Item label="候选 ID">
              <Text code>{String(verificationCandidate.id || '')}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="配置摘要">
              <Text code style={{ fontSize: 11 }}>
                {verificationConfigSummary({
                  challenger_config_override: verificationCandidate.challenger_override,
                  challenger_global_config_patch: verificationCandidate.effective_parameter_patch,
                  challenger_node_param_patches: verificationCandidate.node_param_patches,
                })}
              </Text>
            </Descriptions.Item>
            <Descriptions.Item label="当前窗口 MAPE">
              <Space>
                <span>Baseline {formatMape(metricFromWindows(verificationCandidate, 'baseline'))}</span>
                <span>Challenge {formatMape(metricFromWindows(verificationCandidate, 'challenger'))}</span>
              </Space>
            </Descriptions.Item>
          </Descriptions>
        )}
        <Form form={verificationForm} layout="vertical">
          <Form.List name="windows">
            {(fields, { add, remove }) => (
              <Form.Item label="复验窗口">
                <Space direction="vertical" style={{ width: '100%' }}>
                  {fields.map((field) => (
                    <Space key={field.key} align="baseline">
                      <Form.Item
                        {...field}
                        name={[field.name, 'start_date']}
                        rules={[{ required: true, message: '需要开始日期' }]}
                        style={{ marginBottom: 0 }}
                      >
                        <Input placeholder="YYYY-MM-DD" style={{ width: 140 }} />
                      </Form.Item>
                      <span>到</span>
                      <Form.Item
                        {...field}
                        name={[field.name, 'end_date']}
                        rules={[{ required: true, message: '需要结束日期' }]}
                        style={{ marginBottom: 0 }}
                      >
                        <Input placeholder="YYYY-MM-DD" style={{ width: 140 }} />
                      </Form.Item>
                      <Button size="small" danger onClick={() => remove(field.name)} disabled={fields.length <= 1}>
                        删除
                      </Button>
                    </Space>
                  ))}
                  <Button size="small" onClick={() => add({ start_date: '', end_date: '' })}>
                    添加窗口
                  </Button>
                </Space>
              </Form.Item>
            )}
          </Form.List>
          <Space size={12} wrap>
            <Form.Item name="aggregate_method" label="聚合方式" style={{ width: 180 }}>
              <Select
                options={[
                  { value: 'mean', label: 'mean' },
                  { value: 'median', label: 'median' },
                  { value: 'trimmed_mean', label: 'trimmed_mean' },
                ]}
              />
            </Form.Item>
            <Form.Item name="min_windows_challenger_better" label="至少胜出窗口数" style={{ width: 160 }}>
              <InputNumber min={0} precision={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="score_margin" label="最小分差" style={{ width: 140 }}>
              <InputNumber step={0.01} style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Form.Item name="auto_start" label="加入后立即启动" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="note" label="备注">
            <Input placeholder="可选备注" />
          </Form.Item>
        </Form>
      </Modal>

      {/* start verification config modal */}
      <Modal
        title="启动复验 - 配置确认"
        open={startVerificationModalOpen}
        onOk={submitStartVerification}
        onCancel={() => setStartVerificationModalOpen(false)}
        confirmLoading={startingVerification}
        okText="确认启动"
        width={700}
      >
        {startVerificationItem && (
          <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
            <Descriptions.Item label="复验 ID">
              <Text code>{String(startVerificationItem.id || '')}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="候选 ID">
              <Text code>{String(startVerificationItem.candidate_id || '')}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="配置">
              <Text code style={{ fontSize: 11 }}>
                {verificationConfigSummary(startVerificationItem)}
              </Text>
            </Descriptions.Item>
            <Descriptions.Item label="入池精度">
              {(() => {
                const sm = startVerificationItem.source_metrics as Record<string, unknown> | undefined;
                if (!sm) return <Text type="secondary">-</Text>;
                const bm = Number(sm.baseline_mape);
                const cm = Number(sm.challenger_mape);
                return (
                  <span style={{ fontSize: 12 }}>
                    Baseline {Number.isFinite(bm) ? bm.toFixed(4) : '-'}
                    {' → '}
                    Challenger {Number.isFinite(cm) ? cm.toFixed(4) : '-'}
                  </span>
                );
              })()}
            </Descriptions.Item>
          </Descriptions>
        )}
        <Form form={startVerificationForm} layout="vertical">
          <Form.List name="windows">
            {(fields, { add, remove }) => (
              <Form.Item label="复验窗口">
                <Space direction="vertical" style={{ width: '100%' }}>
                  {fields.map((field) => (
                    <Space key={field.key} align="baseline">
                      <Form.Item
                        {...field}
                        name={[field.name, 'start_date']}
                        rules={[{ required: true, message: '需要开始日期' }]}
                        style={{ marginBottom: 0 }}
                      >
                        <Input placeholder="YYYY-MM-DD" style={{ width: 140 }} />
                      </Form.Item>
                      <span>到</span>
                      <Form.Item
                        {...field}
                        name={[field.name, 'end_date']}
                        rules={[{ required: true, message: '需要结束日期' }]}
                        style={{ marginBottom: 0 }}
                      >
                        <Input placeholder="YYYY-MM-DD" style={{ width: 140 }} />
                      </Form.Item>
                      <Button size="small" danger onClick={() => remove(field.name)} disabled={fields.length <= 1}>
                        删除
                      </Button>
                    </Space>
                  ))}
                  <Button size="small" onClick={() => add({ start_date: '', end_date: '' })}>
                    添加窗口
                  </Button>
                </Space>
              </Form.Item>
            )}
          </Form.List>
          <Space size={12} wrap>
            <Form.Item name="aggregate_method" label="聚合方式" style={{ width: 180 }}>
              <Select
                options={[
                  { value: 'mean', label: 'mean' },
                  { value: 'median', label: 'median' },
                  { value: 'trimmed_mean', label: 'trimmed_mean' },
                ]}
              />
            </Form.Item>
            <Form.Item name="min_windows_challenger_better" label="至少胜出窗口数" style={{ width: 160 }}>
              <InputNumber min={0} precision={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="score_margin" label="最小分差" style={{ width: 140 }}>
              <InputNumber step={0.01} style={{ width: '100%' }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      {/* promote modal */}
      <Modal
        title="Promote 候选"
        open={promoteModalOpen}
        onOk={submitPromote}
        onCancel={() => setPromoteModalOpen(false)}
        confirmLoading={promoting}
        okText="确认 Promote"
      >
        {promotingCandidate && (
          <Descriptions size="small" column={1} style={{ marginBottom: 16 }}>
            <Descriptions.Item label="候选 ID">
              <Text code>{promotingCandidate.id as string}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="Challenger">
              {promotingCandidate.challenger_workflow_id as string}
            </Descriptions.Item>
            <Descriptions.Item label="聚合分">
              {(() => {
                const summary = (promotingCandidate.summary as Record<string, unknown> | undefined);
                const adv = summary?.score_advantage;
                const base = summary?.aggregate_baseline_score;
                const chall = summary?.aggregate_challenger_score;
                if (adv === null || adv === undefined) return '-';
                return `${Number(adv) > 0 ? '+' : ''}${Number(adv).toFixed(4)} (Baseline: ${base ?? '-'} → Challenger: ${chall ?? '-'})`;
              })()}
            </Descriptions.Item>
          </Descriptions>
        )}
        <Form form={promoteForm} layout="vertical">
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="默认只允许复验池 passed 的候选 Promote。未通过复验时需显式勾选人工强制 Promote。"
          />
          <Form.Item name="note" label="备注">
            <Input placeholder="可选备注" />
          </Form.Item>
          <Form.Item name="set_as_production" label="同步更新生产模板登记" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            noStyle
            shouldUpdate={(prev, cur) => prev.set_as_production !== cur.set_as_production}
          >
            {({ getFieldValue }) =>
              getFieldValue('set_as_production') ? (
                <Form.Item name="production_slot" label="生产槽位">
                  <Input placeholder="default" />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item name="force" label="人工强制 Promote（跳过复验门控）" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default WorkflowBaselineComparePage;
