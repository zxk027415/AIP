// @AI_GENERATED
/**
 * 当前喂数数据集卡片：来源 / 日期范围 / 行数 / 指纹 / 是否自带真值，
 * 以及该路径的到达语义进度（按点 N/M 或待到齐 / 超期）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Select, Space, Tag, Typography, message } from 'antd';
import { slotDatasetsApi, type FeedSourceCurrent, type FeedSourceFacts } from '../../services/slotDatasetsApi';
import { slotObservabilityApi, type ObservabilityStatus } from '../../services/slotObservabilityApi';

const { Text } = Typography;

export type FeedProgressView = {
  feed?: ObservabilityStatus['feed'];
  progress?: ObservabilityStatus['progress'];
};

function shortFp(value?: string | null): string {
  if (!value) return '—';
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function semanticsLine(current: FeedSourceCurrent | null, progress?: FeedProgressView): string {
  const gran = String(current?.semantics?.granularity || '');
  const feed = progress?.feed;
  if (gran === 'point') {
    const totals = feed?.point_totals || {};
    const points = feed?.point_progress || {};
    const day = Object.keys(totals)[0] || Object.keys(points)[0];
    if (!day) return '按点推进：尚未开始';
    const n = Number(points[day] || 0);
    const m = Number(totals[day] || 0);
    return m > 0 ? `按点推进 ${n}/${m}（${day}）` : `按点推进 ${n}（${day}）`;
  }
  const waiting = feed?.waiting_days ?? 0;
  const expired = feed?.expired_days ?? 0;
  const gate = gran === 'device_day' ? '等整日到达' : '到达语义';
  return `${gate}：待到齐 ${waiting} 日 / 超期 ${expired} 日`;
}

export function FeedSourceCard({
  slot,
  progress,
  onChanged,
  title = '当前喂数数据集',
}: {
  slot: string;
  progress?: FeedProgressView | null;
  onChanged?: () => void;
  title?: string;
}): JSX.Element {
  const [current, setCurrent] = useState<FeedSourceCurrent | null>(null);
  const [candidates, setCandidates] = useState<Array<{ dataset_ref: string }>>([]);
  const [statusProgress, setStatusProgress] = useState<FeedProgressView | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [body, status] = await Promise.all([
        slotDatasetsApi.getFeedSources(200),
        slotObservabilityApi.getStatus(slot).catch(() => null),
      ]);
      setCandidates(body.candidates || []);
      setCurrent(body.current?.[slot] || null);
      if (status) {
        setStatusProgress(slot === 'pv_tsc' ? (status.demo_replay || status) : status);
      }
    } catch {
      message.error('喂数数据集读取失败');
    } finally {
      setLoading(false);
    }
  }, [slot]);

  useEffect(() => {
    void load();
  }, [load]);

  const source: FeedSourceFacts | null = current?.source || null;
  const selectedRef = source?.dataset_ref || current?.selection?.dataset_ref || null;
  const options = useMemo(() => {
    const seen = new Set<string>();
    const items = (candidates || [])
      .filter((item) => item.dataset_ref)
      .map((item) => {
        seen.add(item.dataset_ref);
        return { value: item.dataset_ref, label: item.dataset_ref };
      });
    if (selectedRef && !seen.has(selectedRef)) {
      items.unshift({ value: selectedRef, label: selectedRef });
    }
    return items;
  }, [candidates, selectedRef]);

  const onSelect = async (value: string | null) => {
    setSaving(true);
    try {
      await slotDatasetsApi.selectFeedSource(slot, value);
      message.success(value ? '已切换喂数数据集，下次推进按新源日历回放' : '已清空，回落内置生成');
      await load();
      onChanged?.();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: { message?: string } | string } } })?.response?.data?.detail;
      const text = typeof detail === 'string' ? detail : detail?.message;
      message.error(text || '切换喂数数据集失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card size="small" title={title} loading={loading} extra={<Button size="small" onClick={() => void load()}>刷新</Button>}>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        <Select
          showSearch
          allowClear
          style={{ width: '100%' }}
          placeholder="选择喂数数据集（可清空回落内置生成）"
          value={selectedRef || undefined}
          options={options}
          loading={saving}
          onChange={(value) => void onSelect(value ?? null)}
          filterOption={(input, option) =>
            String(option?.label || '').toLowerCase().includes(input.toLowerCase())
          }
        />
        {source ? (
          <Space wrap size={6}>
            <Tag>{source.date_min || '—'} ~ {source.date_max || '—'}</Tag>
            <Tag>{source.row_count != null ? `${source.row_count} 行` : '行数未知'}</Tag>
            <Tag>指纹 {shortFp(source.fingerprint)}</Tag>
            <Tag color={source.has_gold ? 'green' : 'default'}>
              {source.has_gold ? `自带真值（${source.gold_column || 'label'}）` : '无真值'}
            </Tag>
          </Space>
        ) : (
          <Text type="secondary">{current?.note || '未选择外部数据集：回落内置生成'}</Text>
        )}
        <Alert
          type="info"
          showIcon
          message={semanticsLine(current, progress || statusProgress || undefined)}
        />
      </Space>
    </Card>
  );
}

export default FeedSourceCard;
// @AI_GENERATED: end
