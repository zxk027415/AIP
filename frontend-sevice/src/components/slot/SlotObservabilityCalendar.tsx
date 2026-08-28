/**
 * SlotObservabilityCalendar — 天/点共用观测日历。调度页可写，精度运营只读。
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  DatePicker,
  Drawer,
  Input,
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
}

const SlotObservabilityCalendar: React.FC<Props> = ({ slot, writable = false, schedulerHref }) => {
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().subtract(6, 'day'), dayjs()]);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ObservabilityCalendar | null>(null);
  const [curveOpen, setCurveOpen] = useState(false);
  const [curveTitle, setCurveTitle] = useState('');
  const [curvePoints, setCurvePoints] = useState<Array<{ time: string; value: number | null }>>([]);

  const load = async () => {
    setLoading(true);
    try {
      const body = await slotObservabilityApi.getCalendar(
        slot,
        range[0].format('YYYY-MM-DD'),
        range[1].format('YYYY-MM-DD'),
        page,
      );
      setData(body);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: { message?: string } } }; message?: string };
      message.error(e.response?.data?.detail?.message || e.message || '读取观测日历失败');
    } finally {
      setLoading(false);
    }
  };

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
    const from = day || range[0].format('YYYY-MM-DD');
    const to = day || range[1].format('YYYY-MM-DD');
    setCurveTitle(`${row.device_key} · ${from} ~ ${to}`);
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
      title: day.slice(5),
      key: day,
      width: 88,
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

  return (
    <Space direction="vertical" size={12} style={{ width: '100%' }}>
      {slot === 'pv_point' ? (
        <Alert type="info" showIcon message="点路径日历是按日切面，检测仍按事件点到达，不套用三天闸门。" />
      ) : (
        <Alert
          type="info"
          showIcon
          message={`天路径占用门槛 ${data?.occupancy_ready || 173}/${data?.expected_points || 288}。当前水位日 ${data?.watermark_day || '未设置'}。`}
        />
      )}
      {!writable && schedulerHref ? (
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
          }}
        />
        <Input.Search placeholder="搜索设备" allowClear onSearch={setQuery} style={{ width: 220 }} />
        {writable && slot === 'pv_day' ? (
          <Button
            onClick={async () => {
              await slotObservabilityApi.advanceDay(slot);
              message.success('已推进下一天');
              void load();
            }}
          >
            推进下一天
          </Button>
        ) : null}
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
              return <path d={d} fill="none" stroke="#1677ff" strokeWidth="2" />;
            })()}
          </svg>
        )}
        {writable ? (
          <Button
            style={{ marginTop: 12 }}
            onClick={async () => {
              const device = curveTitle.split(' · ')[0];
              await slotObservabilityApi.manualDetect({ slot, device_key: device, reason: 'calendar_manual' });
              message.success('已记录手动检测（需二次确认后才会改水位）');
              void load();
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
