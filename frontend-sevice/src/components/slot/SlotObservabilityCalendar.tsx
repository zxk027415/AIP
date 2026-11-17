/**
 * SlotObservabilityCalendar — 天/点共用观测日历。调度页可写，精度运营只读。
 */
import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  DatePicker,
  Drawer,
  Input,
  Modal,
  Pagination,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import {
  slotObservabilityApi,
  type ObservabilityCalendar,
  type ObservabilityRow,
} from '../../services/slotObservabilityApi';
import type { PvProductSlot } from '../../config/slotProductConfig';

const { RangePicker } = DatePicker;
const { Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  detected: 'green',
  ready: 'blue',
  arrived: 'blue',
  waiting: 'gold',
  skipped: 'red',
  empty: 'default',
};

interface Props {
  slot: PvProductSlot;
  writable?: boolean;
  schedulerHref?: string;
  /** 父页指定初始窗口时，不再用 occupancy/gold 最晚一周。 */
  preferredRange?: { from: string; to: string };
  onRangeChange?: (from: string, to: string) => void;
}

const SlotObservabilityCalendar: React.FC<Props> = ({
  slot,
  writable = false,
  schedulerHref,
  preferredRange,
  onRangeChange,
}) => {
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(() =>
    preferredRange?.from && preferredRange?.to
      ? [dayjs(preferredRange.from), dayjs(preferredRange.to)]
      : null,
  );
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  // @AI_GENERATED: 日历持久错误态，加载失败显式报错 + 重试，不静默留空表。
  const [loadError, setLoadError] = useState<string | null>(null);
  // @AI_GENERATED: end
  const [data, setData] = useState<ObservabilityCalendar | null>(null);
  const [curveOpen, setCurveOpen] = useState(false);
  const [curveTitle, setCurveTitle] = useState('');
  const [curveDevice, setCurveDevice] = useState('');
  const [curveDay, setCurveDay] = useState<string | undefined>();
  const [curvePoints, setCurvePoints] = useState<Array<{
    time: string;
    value: number | null;
    label?: unknown;
    predicted_label?: unknown;
  }>>([]);

  const lastNotified = useRef('');
  const prevSlot = useRef(slot);
  const appliedPref = useRef('');
  const notifyRange = (from: string, to: string) => {
    const key = `${from}|${to}`;
    if (!from || !to || lastNotified.current === key) return;
    lastNotified.current = key;
    onRangeChange?.(from, to);
  };

  const load = async () => {
    setLoading(true);
    // @AI_GENERATED: 每次加载先清错误，失败时保留错误态供重试。
    setLoadError(null);
    try {
      const body = await slotObservabilityApi.getCalendar(
        slot,
        range?.[0]?.format('YYYY-MM-DD'),
        range?.[1]?.format('YYYY-MM-DD'),
        page,
      );
      setData(body);
      const nextFrom = range?.[0]?.format('YYYY-MM-DD') || body.from;
      const nextTo = range?.[1]?.format('YYYY-MM-DD') || body.to;
      if (!range && body.from && body.to) {
        setRange([dayjs(body.from), dayjs(body.to)]);
      }
      if (nextFrom && nextTo) {
        notifyRange(nextFrom, nextTo);
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string | { message?: string } } }; message?: string };
      const detail = e.response?.data?.detail;
      setLoadError((typeof detail === 'string' ? detail : detail?.message) || e.message || '读取观测日历失败');
    } finally {
      setLoading(false);
    }
    // @AI_GENERATED: end
  };

  useEffect(() => {
    if (prevSlot.current === slot) return;
    prevSlot.current = slot;
    lastNotified.current = '';
    appliedPref.current = '';
    setRange(null);
    setPage(1);
    setData(null);
  }, [slot]);

  useEffect(() => {
    if (!preferredRange?.from || !preferredRange?.to) return;
    const key = `${preferredRange.from}|${preferredRange.to}`;
    if (appliedPref.current === key) return;
    appliedPref.current = key;
    setPage(1);
    setRange([dayjs(preferredRange.from), dayjs(preferredRange.to)]);
  }, [preferredRange?.from, preferredRange?.to]);

  useEffect(() => {
    void load();
  }, [slot, range, page]);

  const rows = useMemo(() => {
    const all = data?.rows || [];
    if (!query.trim()) return all;
    const q = query.trim().toLowerCase();
    return all.filter((row) => row.device_key.toLowerCase().includes(q) || String(row.device_id || '').toLowerCase().includes(q));
  }, [data, query]);

  const openCurve = async (row: ObservabilityRow, day?: string) => {
    const from = day || range?.[0]?.format('YYYY-MM-DD') || data?.from;
    const to = day || range?.[1]?.format('YYYY-MM-DD') || data?.to;
    if (!from || !to) return;
    setCurveTitle(`${row.device_key} · ${from} ~ ${to}`);
    setCurveDevice(row.device_key);
    setCurveDay(day);
    setCurveOpen(true);
    try {
      const body = await slotObservabilityApi.getCurve(slot, row.device_key, from, to);
      setCurvePoints(body.points || []);
    } catch (err: unknown) {
      message.error((err as Error).message || '读取曲线失败');
    }
  };

  const columns = [
    {
      title: '设备',
      dataIndex: 'device_key',
      width: 220,
      ellipsis: true,
      fixed: 'left' as const,
    },
    ...(data?.days || []).map((day) => ({
      title: day,
      key: day,
      width: 118,
      render: (_: unknown, row: ObservabilityRow) => {
        const cell = (row.cells || []).find((item) => item.date === day);
        if (!cell) return null;
        const pct = cell.completeness != null ? `${Math.round(Number(cell.completeness) * 100)}%` : '';
        return (
          <Tooltip
            title={`到达 ${cell.arrived_count}/${cell.expected_count || '—'} ${pct} · 模型 ${cell.model_id || '未检'} · ${cell.skip_reason || cell.status}`}
          >
            <Button
              size="small"
              type="text"
              onClick={() => void openCurve(row, day)}
            >
              <Tag color={STATUS_COLOR[cell.status || 'empty'] || 'default'}>
                {cell.late_arrival ? '迟 ' : ''}{cell.status}
              </Tag>
            </Button>
          </Tooltip>
        );
      },
    })),
  ];

  // @AI_GENERATED: pv_tsc 或后端 readonly 标记都强制只读，双重防御手工补检写入。
  const effectiveWritable = writable && slot !== 'pv_tsc' && !data?.readonly;
  // @AI_GENERATED: end
  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      {/* @AI_GENERATED: 日历加载失败显式报错 + 重试。 */}
      {loadError && (
        <Alert
          type="error"
          showIcon
          message="读取观测日历失败"
          description={loadError}
          action={<Button size="small" onClick={() => void load()}>重试</Button>}
        />
      )}
      {/* @AI_GENERATED: end */}
      {/* @AI_GENERATED: 三态日历说明，pv_tsc 走真实调度只读文案，不落入"天路径占用门槛"。 */}
      {slot === 'pv_point' ? (
        <Alert
          type="info"
          showIcon
          message={
            preferredRange
              ? `当前窗口 ${preferredRange.from}～${preferredRange.to}。列头是完整日期，和下面告警/曲线同一段。`
              : `点路径日历按日切面。当前业务日 ${data?.clock?.day || data?.watermark_day || '尚未喂入'}。默认窗口对齐已喂演示日，不是今天。`
          }
        />
      ) : slot === 'pv_tsc' ? (
        <Alert
          type="info"
          showIcon
          message={`时序分类日历只读：按设备日 ${data?.occupancy_ready || 173}/${data?.expected_points || 288} 点口径展示到达完整度。当前业务日 ${data?.clock?.day || data?.watermark_day || '尚未产出'}。检测由真实 pv_tsc_predict 调度推进，不提供演示推进或手工补检。`}
        />
      ) : (
        <Alert
          type="info"
          showIcon
          message={`天路径占用门槛 ${data?.occupancy_ready || 173}/${data?.expected_points || 288}。当前业务日 ${data?.clock?.day || data?.watermark_day || '尚未喂入'}。默认窗口对齐已喂演示日，不是今天。`}
        />
      )}
      {/* @AI_GENERATED: end */}
      {!effectiveWritable && schedulerHref ? (
        <Alert type="warning" showIcon message="精度运营日历只读" description={<a href={schedulerHref}>需要推进水位或手动检测时打开调度页</a>} />
      ) : null}
      <Space wrap>
        <RangePicker
          value={range}
          onChange={(next) => {
            if (!next?.[0] || !next?.[1]) return;
            if (next[1].diff(next[0], 'day') > 29) {
              message.warning('最长 30 天');
              return;
            }
            setPage(1);
            setRange([next[0], next[1]]);
            notifyRange(next[0].format('YYYY-MM-DD'), next[1].format('YYYY-MM-DD'));
          }}
        />
        <Input.Search placeholder="搜索设备" allowClear onSearch={setQuery} style={{ width: 220 }} />
        <Button onClick={() => void load()} loading={loading}>刷新</Button>
      </Space>
      <Table
        size="small"
        rowKey="device_key"
        loading={loading}
        pagination={false}
        scroll={{ x: 900 }}
        columns={columns}
        dataSource={rows}
        onRow={(row) => ({
          onDoubleClick: () => void openCurve(row),
        })}
      />
      <Pagination
        current={page}
        pageSize={data?.page_size || 50}
        total={data?.device_total || 0}
        onChange={setPage}
        showSizeChanger={false}
      />
      <Drawer title={curveTitle} width={640} open={curveOpen} onClose={() => setCurveOpen(false)}>
        {curvePoints.length === 0 ? <Text type="secondary">没有曲线点</Text> : (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <svg width="100%" viewBox="0 0 600 180">
              {(() => {
                const values = curvePoints.map((p) => p.value).filter((v): v is number => v != null);
                if (values.length < 2) return null;
                const min = Math.min(...values);
                const max = Math.max(...values);
                const span = max - min || 1;
                const d = curvePoints.map((p, i) => {
                  const x = (i / Math.max(curvePoints.length - 1, 1)) * 600;
                  const y = 180 - ((p.value == null ? min : p.value) - min) / span * 180;
                  return `${i === 0 ? 'M' : 'L'}${x},${y}`;
                }).join(' ');
                const predDots = curvePoints.map((p, i) => {
                  if (p.predicted_label == null || p.value == null) return null;
                  const x = (i / Math.max(curvePoints.length - 1, 1)) * 600;
                  const y = 180 - (p.value - min) / span * 180;
                  return <circle key={`p-${i}`} cx={x} cy={y} r={2.4} fill="#fa8c16" />;
                });
                const goldDots = curvePoints.map((p, i) => {
                  if (p.label == null || p.value == null) return null;
                  const x = (i / Math.max(curvePoints.length - 1, 1)) * 600;
                  const y = 180 - (p.value - min) / span * 180;
                  return <circle key={`g-${i}`} cx={x} cy={y} r={2.2} fill="none" stroke="#52c41a" strokeWidth={1.4} />;
                });
                return (
                  <>
                    <path d={d} fill="none" stroke="#1677ff" strokeWidth="2" />
                    {predDots}
                    {goldDots}
                  </>
                );
              })()}
            </svg>
            <Space size={12}>
              <Text type="secondary">蓝线=测量</Text>
              <Text type="secondary">橙点=预测标签</Text>
              <Text type="secondary">绿圈=gold 真值</Text>
            </Space>
          </Space>
        )}
        {effectiveWritable ? (
          <Button
            style={{ marginTop: 12 }}
            onClick={() => {
              Modal.confirm({
                title: '手动补检该设备？',
                content: `将对 ${curveDevice}${curveDay ? ` · ${curveDay}` : ''} 再跑一遍演示检测器，写入观测账本，不纳入累计。`,
                okText: '补检',
                onOk: async () => {
                  try {
                    const result = await slotObservabilityApi.manualDetect({
                      slot,
                      device_key: curveDevice,
                      day: curveDay,
                      reason: 'calendar_manual',
                    });
                    const body = result as { model_ran?: boolean; note?: string };
                    message.success(body.model_ran ? (body.note || '已补检') : `已记审计，检测未跑：${body.note || ''}`);
                    void load();
                  } catch (err: unknown) {
                    const e = err as { response?: { data?: { detail?: { message?: string } | string } }; message?: string };
                    const detail = e.response?.data?.detail;
                    message.error((typeof detail === 'string' ? detail : detail?.message) || e.message || '补检失败');
                    throw err;
                  }
                },
              });
            }}
          >
            手动补检该设备
          </Button>
        ) : null}
      </Drawer>
    </Space>
  );
};

export default SlotObservabilityCalendar;
