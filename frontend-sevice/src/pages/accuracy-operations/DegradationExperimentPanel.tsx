// @AI_GENERATED
/**
 * DegradationExperimentPanel — 人工注入/恢复精度劣化实验控件。
 *
 * 只抬高 AccuracyTracker 滚动指标并调用真实 AccuracyMonitor，不改生产身份。
 * 文案明确：不写入未来真值，不绕过 gap-1 日滚。
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Alert, Button, Card, InputNumber, Space, Typography, message } from 'antd';
import { ExperimentOutlined, RedoOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { accuracyOperationsApi } from '../../services/accuracyOperationsApi';

const { Text } = Typography;

interface DegradationExperimentPanelProps {
  slot: string;
  onChanged?: () => void;
}

const DegradationExperimentPanel: React.FC<DegradationExperimentPanelProps> = ({
  slot,
  onChanged,
}) => {
  const [loading, setLoading] = useState(false);
  const [injected, setInjected] = useState(false);
  const [targetPct, setTargetPct] = useState(20);
  const [statusText, setStatusText] = useState<string>('读取中…');

  const refreshStatus = useCallback(async () => {
    try {
      const res = await accuracyOperationsApi.getDegradationStatus(slot);
      setInjected(Boolean(res.injected));
      const prod = res.production;
      if (prod?.status) {
        const deg =
          prod.degradation_pct === null || prod.degradation_pct === undefined
            ? '—'
            : `${Number(prod.degradation_pct).toFixed(2)}%`;
        setStatusText(
          `指标 ${prod.status}；当前相对基线劣化 ${deg}` +
            (res.injected ? '（注入态）' : ''),
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
        note: 'accuracy-ops-ui',
      });
      const alerts = Array.isArray(res.alerts_created) ? res.alerts_created : [];
      const deg = typeof res.degradation_pct === 'number' ? res.degradation_pct : Number(res.degradation_pct || 0);
      message.success(`已注入劣化 ${deg.toFixed(2)}%，新建告警 ${alerts.length} 条`);
      await refreshStatus();
      onChanged?.();
    } catch (error) {
      message.error((error as Error).message || '注入失败');
    } finally {
      setLoading(false);
    }
  };

  const runRestore = async () => {
    setLoading(true);
    try {
      await accuracyOperationsApi.restoreDegradation({ slot, close_open_alerts: true });
      message.success('已恢复注入前指标');
      await refreshStatus();
      onChanged?.();
    } catch (error) {
      message.error((error as Error).message || '恢复失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card
      size="small"
      title={
        <Space>
          <ExperimentOutlined />
          实验：人工注入劣化
        </Space>
      }
      style={{ marginBottom: 16 }}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 12 }}
        message="只改滚动 MAPE 并走真实监控；不改 slots.json 生产，不写入未来真值。"
        description="若指标仍是 insufficient_data，先点「激活指标（演示）」。真实精度验收仍须 gap-1 日滚 + 回填。"
      />
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Text type="secondary">{statusText}</Text>
        <Space wrap>
          <Button onClick={() => void runActivate()} loading={loading}>
            激活指标（演示）
          </Button>
          <InputNumber
            min={15}
            max={100}
            value={targetPct}
            onChange={(v) => setTargetPct(Number(v || 20))}
            addonAfter="%"
            style={{ width: 140 }}
          />
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={() => void runInject()}
            loading={loading}
            disabled={injected}
          >
            注入劣化
          </Button>
          <Button
            icon={<RedoOutlined />}
            onClick={() => void runRestore()}
            loading={loading}
            disabled={!injected}
          >
            恢复指标
          </Button>
          <Button onClick={() => void refreshStatus()} disabled={loading}>
            刷新状态
          </Button>
        </Space>
      </Space>
    </Card>
  );
};

export default DegradationExperimentPanel;
// @AI_GENERATED: end
