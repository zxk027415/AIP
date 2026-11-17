// @AI_GENERATED
/**
 * DegradationExperimentPanel — 人工注入/恢复精度劣化实验控件。
 *
 * 恢复拆成两步：
 *   1. 「恢复」按钮：仅还原 StationData + 指标（rerun_pipeline=false），接口秒级返回，不卡住。
 *   2. 「还原后重训」按钮：还原完成后按需触发 gap-1 日滚 + 精度回填（POST /experiments/retrigger-pipeline），
 *      可能需要几分钟，单独 loading 状态，不影响恢复本身。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, Descriptions, InputNumber, Select, Space, Typography, message } from 'antd';
import { ExperimentOutlined, RedoOutlined, SyncOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { accuracyOperationsApi } from '../../services/accuracyOperationsApi';

const { Text } = Typography;

interface DegradationExperimentPanelProps {
  slot: string;
  onChanged?: () => void;
}

type DegradeMode = 'noise' | 'missing' | 'zero_spike' | 'metric_rewrite';

interface InjectOutcome {
  injected_at?: string | null;
  mode?: string | null;
  rerun_pipeline?: boolean | null;
  rolling_mape_before?: number | null;
  post_train_rolling_mape?: number | null;
  post_train_window_mape?: number | null;
  rolling_mape_window_before?: number | null;
  rolling_mape_window_after?: number | null;
  rolling_mape_after?: number | null;
  rolling_mape_method?: string | null;
  rolling_mape_pooled_after?: number | null;
  degradation_pct?: number | null;
  mape_delta_pct?: number | null;
  baseline_mape?: number | null;
  daily_rolling_cycle_id?: string | null;
  daily_rolling_skipped?: boolean | null;
  experiment_alert_baseline?: number | null;
  experiment_alert_current?: number | null;
  experiment_alert_degradation_pct?: number | null;
}

function fmtPct(value: unknown, digits = 2): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? `${n.toFixed(digits)}%` : '—';
}

function parseInjectOutcome(raw: unknown): InjectOutcome | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  return {
    injected_at: o.injected_at != null ? String(o.injected_at) : null,
    mode: o.mode != null ? String(o.mode) : null,
    rerun_pipeline: o.rerun_pipeline != null ? Boolean(o.rerun_pipeline) : null,
    rolling_mape_before: o.rolling_mape_before != null ? Number(o.rolling_mape_before) : null,
    post_train_rolling_mape:
      o.post_train_rolling_mape != null
        ? Number(o.post_train_rolling_mape)
        : o.rolling_mape_after != null
          ? Number(o.rolling_mape_after)
          : null,
    post_train_window_mape:
      o.post_train_window_mape != null
        ? Number(o.post_train_window_mape)
        : o.rolling_mape_window_after != null
          ? Number(o.rolling_mape_window_after)
          : null,
    rolling_mape_window_before:
      o.rolling_mape_window_before != null ? Number(o.rolling_mape_window_before) : null,
    rolling_mape_window_after:
      o.rolling_mape_window_after != null ? Number(o.rolling_mape_window_after) : null,
    rolling_mape_after: o.rolling_mape_after != null ? Number(o.rolling_mape_after) : null,
    rolling_mape_method: o.rolling_mape_method != null ? String(o.rolling_mape_method) : null,
    rolling_mape_pooled_after:
      o.rolling_mape_pooled_after != null ? Number(o.rolling_mape_pooled_after) : null,
    degradation_pct: o.degradation_pct != null ? Number(o.degradation_pct) : null,
    mape_delta_pct: o.mape_delta_pct != null ? Number(o.mape_delta_pct) : null,
    baseline_mape: o.baseline_mape != null ? Number(o.baseline_mape) : null,
    daily_rolling_cycle_id:
      o.daily_rolling_cycle_id != null ? String(o.daily_rolling_cycle_id) : null,
    daily_rolling_skipped: o.daily_rolling_skipped != null ? Boolean(o.daily_rolling_skipped) : null,
    daily_rolling_skip_reason:
      o.daily_rolling_skip_reason != null ? String(o.daily_rolling_skip_reason) : null,
    experiment_alert_baseline:
      o.experiment_alert_baseline != null ? Number(o.experiment_alert_baseline) : null,
    experiment_alert_current:
      o.experiment_alert_current != null ? Number(o.experiment_alert_current) : null,
    experiment_alert_degradation_pct:
      o.experiment_alert_degradation_pct != null ? Number(o.experiment_alert_degradation_pct) : null,
  };
}

const DegradationExperimentPanel: React.FC<DegradationExperimentPanelProps> = ({
  slot,
  onChanged,
}) => {
  const [loading, setLoading] = useState(false);
  // @AI_GENERATED: retriggerLoading 独立于 loading，不让恢复按钮被重训卡住
  const [retriggerLoading, setRetriggerLoading] = useState(false);
  // restored：标记 StationData 已还原但日滚尚未触发
  const [restored, setRestored] = useState(false);
  // @AI_GENERATED: end
  const [injected, setInjected] = useState(false);
  const [targetPct, setTargetPct] = useState(20);
  const [mode, setMode] = useState<DegradeMode>('noise');
  const [statusText, setStatusText] = useState<string>('读取中…');
  const [injectOutcome, setInjectOutcome] = useState<InjectOutcome | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const res = await accuracyOperationsApi.getDegradationStatus(slot);
      setInjected(Boolean(res.injected));
      const outcome = parseInjectOutcome(res.inject_outcome);
      setInjectOutcome(outcome);
      const prod = res.production as Record<string, unknown> | undefined;
      const modeLabel = res.mode ? String(res.mode) : '';
      if (prod?.status) {
        const deg =
          prod.degradation_pct === null || prod.degradation_pct === undefined
            ? '—'
            : `${Number(prod.degradation_pct).toFixed(2)}%`;
        setStatusText(
          `指标 ${String(prod.status)}；当前滚动 MAPE ${fmtPct(prod.rolling_mape)}；相对基线 ${deg}` +
            (res.injected ? `（注入态${modeLabel ? `:${modeLabel}` : ''}）` : ''),
        );
      } else {
        setStatusText('尚无生产指标');
      }
    } catch (error) {
      setStatusText((error as Error).message || '状态读取失败');
    }
  }, [slot]);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const runActivate = async () => {
    setLoading(true);
    try {
      const res = await accuracyOperationsApi.activateMetrics(slot, 3);
      const count = typeof res.count === 'number' ? res.count : Number(res.count || 0);
      message.success(`已激活 ${count} 个版本指标（演示用，非真实回填）`);
      await refreshStatus();
      onChanged?.();
    } catch (error) {
      message.error((error as Error).message || '激活失败');
    } finally {
      setLoading(false);
    }
  };

  const runInject = async () => {
    setLoading(true);
    try {
      const res = await accuracyOperationsApi.injectDegradation({
        slot,
        target_degradation_pct: targetPct,
        mode,
        note: 'accuracy-ops-ui-data-level',
        rerun_pipeline: mode !== 'metric_rewrite',
      });
      const outcome = parseInjectOutcome(res.inject_outcome ?? res);
      if (outcome) setInjectOutcome(outcome);

      const alerts = Array.isArray(res.alerts_created) ? res.alerts_created : [];
      const postTrain = outcome?.post_train_rolling_mape;
      const before = outcome?.rolling_mape_before;
      const pipeline = res.pipeline as
        | { daily_rolling_cycle_id?: string | null; backfill_updated_versions?: number }
        | undefined;

      message.success(
        `注入完成：重训后 MAPE ${fmtPct(postTrain)}` +
          (before != null ? `（注入前 ${fmtPct(before)}）` : '') +
          (typeof res.experiment_alert_degradation_pct === 'number'
            ? `，告警判定 +${Number(res.experiment_alert_degradation_pct).toFixed(2)}%`
            : '') +
          (pipeline && !pipeline.daily_rolling_cycle_id && mode !== 'metric_rewrite'
            ? '；日滚未产出新 cycle'
            : '') +
          `；告警 ${alerts.length} 条`,
        8,
      );
      setInjected(true);
      setRestored(false);
      await refreshStatus();
      onChanged?.();
    } catch (error) {
      message.error((error as Error).message || '注入失败');
    } finally {
      setLoading(false);
    }
  };

  // @AI_GENERATED: 恢复拆成两步，避免日滚同步执行卡住
  const runRestore = async () => {
    setLoading(true);
    try {
      // rerun_pipeline=false（后端默认值）：仅还原 StationData + 指标，接口秒级返回
      await accuracyOperationsApi.restoreDegradation({ slot, close_open_alerts: true });
      message.success('已还原注入前数据/指标。如需刷新预测指标，点击「还原后重训」。');
      setInjectOutcome(null);
      setInjected(false);
      setRestored(true);           // 标记：数据已还原，可触发重训
      await refreshStatus();
      onChanged?.();
    } catch (error) {
      message.error((error as Error).message || '恢复失败');
    } finally {
      setLoading(false);
    }
  };

  /** 「还原后重训」：调用 retrigger-pipeline，单独 loading，不卡恢复按钮 */
  const runRetriggerPipeline = async () => {
    setRetriggerLoading(true);
    try {
      await accuracyOperationsApi.retriggerPipeline({ slot });
      message.success('重训完成，指标与曲线已刷新');
      setRestored(false);
      await refreshStatus();
      onChanged?.();
    } catch (error) {
      message.error((error as Error).message || '重训失败');
    } finally {
      setRetriggerLoading(false);
    }
  };
  // @AI_GENERATED: end

  return (
    <Card
      size="small"
      title={
        <Space>
          <ExperimentOutlined />
          实验：数据层劣化注入
        </Space>
      }
      style={{ marginBottom: 16 }}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="默认改 StationData（noise/missing），触发数据层劣化；注入后自动重训并展示「重训后 MAPE」。"
        description={
          <>
            告警口径：相对「注入前线上 MAPE」≥15% 触发（不是 AR 基线 5.66%）。
            <br />
            <strong>恢复</strong> 仅还原 StationData + 指标，立即完成；
            还原后可点 <strong>还原后重训</strong> 刷新预测曲线/指标（需数分钟，不阻塞恢复）。
          </>
        }
      />
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text type="secondary">{statusText}</Text>

        {injected && injectOutcome?.post_train_rolling_mape != null && (
          <Alert
            type="warning"
            showIcon
            message={
              <Space wrap>
                <Text strong>注入重训后 MAPE（劣化窗口）：</Text>
                <Text strong style={{ fontSize: 16, color: '#d48806' }}>
                  {fmtPct(injectOutcome.post_train_rolling_mape)}
                </Text>
                {injectOutcome.rolling_mape_method ? (
                  <Text type="secondary">（窗口 pooled / daily 加权）</Text>
                ) : null}
              </Space>
            }
            description={
              <Descriptions size="small" column={2} style={{ marginTop: 8 }}>
                <Descriptions.Item label="窗口注入前">
                  {fmtPct(
                    injectOutcome.rolling_mape_window_before ?? injectOutcome.rolling_mape_before,
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="相对窗口注入前">
                  {fmtPct(injectOutcome.mape_delta_pct)}
                </Descriptions.Item>
                <Descriptions.Item label="7日 median（参考）">
                  {fmtPct(injectOutcome.rolling_mape_after)}
                </Descriptions.Item>
                <Descriptions.Item label="AR 基线参考">
                  {fmtPct(injectOutcome.baseline_mape)}
                </Descriptions.Item>
                <Descriptions.Item label="告警判定（线上）">
                  {injectOutcome.experiment_alert_baseline != null &&
                  injectOutcome.experiment_alert_current != null ? (
                    <>
                      {fmtPct(injectOutcome.experiment_alert_baseline)} →{' '}
                      {fmtPct(injectOutcome.experiment_alert_current)}（
                      {fmtPct(injectOutcome.experiment_alert_degradation_pct)}）
                    </>
                  ) : (
                    '—'
                  )}
                </Descriptions.Item>
                <Descriptions.Item label="相对基线劣化（AR）">
                  {fmtPct(injectOutcome.degradation_pct)}
                </Descriptions.Item>
                <Descriptions.Item label="日滚 cycle">
                  {injectOutcome.daily_rolling_cycle_id
                    ? injectOutcome.daily_rolling_cycle_id.slice(0, 28)
                    : injectOutcome.daily_rolling_skipped
                      ? '未产出（见下）'
                      : '—'}
                </Descriptions.Item>
                {injectOutcome.daily_rolling_skipped && injectOutcome.daily_rolling_skip_reason ? (
                  <Descriptions.Item label="日滚跳过原因" span={2}>
                    <Text type="danger">{injectOutcome.daily_rolling_skip_reason}</Text>
                  </Descriptions.Item>
                ) : null}
              </Descriptions>
            }
          />
        )}

        <Space wrap>
          <Button onClick={() => void runActivate()} loading={loading}>
            激活指标（演示）
          </Button>
          <Select
            value={mode}
            style={{ width: 160 }}
            onChange={(v) => setMode(v)}
            options={[
              { value: 'noise', label: '噪声 (noise)' },
              { value: 'missing', label: '缺失 (missing)' },
              { value: 'zero_spike', label: '置零尖峰' },
              { value: 'metric_rewrite', label: '仅改指标(兜底)' },
            ]}
          />
          <InputNumber
            min={15}
            max={100}
            value={targetPct}
            onChange={(v) => setTargetPct(Number(v || 20))}
            addonAfter="%基线"
            style={{ width: 150 }}
            disabled={mode !== 'metric_rewrite'}
          />
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={() => void runInject()}
            loading={loading}
            disabled={injected || retriggerLoading}
          >
            注入劣化
          </Button>
          {/* @AI_GENERATED: 恢复拆两步 */}
          <Button
            icon={<RedoOutlined />}
            onClick={() => void runRestore()}
            loading={loading}
            disabled={!injected || retriggerLoading}
          >
            恢复
          </Button>
          <Button
            icon={<SyncOutlined />}
            onClick={() => void runRetriggerPipeline()}
            loading={retriggerLoading}
            disabled={!restored || loading}
          >
            还原后重训
          </Button>
          {/* @AI_GENERATED: end */}
          <Button onClick={() => void refreshStatus()} disabled={loading || retriggerLoading}>
            刷新状态
          </Button>
        </Space>
      </Space>
    </Card>
  );
};

export default DegradationExperimentPanel;
// @AI_GENERATED: end
