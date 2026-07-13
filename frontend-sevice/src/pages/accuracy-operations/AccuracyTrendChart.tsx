// @AI_GENERATED
/**
 * AccuracyTrendChart.tsx — 精度趋势图组件
 *
 * 展示当前 slot 下各模型形态（生产/影子）的 MAPE 对比。
 * 数据来源：useAccuracyOperationsStore 中的 monitoringSnapshot。
 * 无实时时序数据时，以柱状图展示快照指标对比。
 *
 * Props: { slot: string }
 * 相关 spec：accuracy-operations / Task 13.3
 */

import React, { useEffect } from 'react';
import {
  Card,
  Statistic,
  Row,
  Col,
  Spin,
  Alert,
  Empty,
  Tag,
  Typography,
  Table,
} from 'antd';
import { LineChartOutlined } from '@ant-design/icons';
import useAccuracyOperationsStore from '../../stores/accuracyOperationsStore';
import type { MonitoringMetrics } from '../../types/accuracy-operations';

const { Text } = Typography;

// ===========================================================================
// Props
// ===========================================================================

interface AccuracyTrendChartProps {
  /** slot — 当前操作槽位名称 */
  slot: string;
}

// ===========================================================================
// 辅助：MAPE 格式化
// ===========================================================================

/** formatMape — 将 MAPE 数值格式化为百分比字符串（保留 2 位小数） */
function formatMape(value: number | null): string {
  if (value === null || value === undefined) return '—';
  return `${(value * 100).toFixed(2)}%`;
}

/** mapeColor — 根据 MAPE 值返回语义色 */
function mapeColor(value: number | null): string {
  if (value === null) return '#8c8c8c';
  const pct = value * 100;
  if (pct < 5) return '#52c41a';   // 绿：优秀
  if (pct < 10) return '#faad14';  // 橙：警戒
  return '#f5222d';                // 红：退化
}

// ===========================================================================
// 柱状图（纯 AntD Table 实现，无 ECharts 依赖）
// ===========================================================================

interface BarRow {
  key: string;
  label: string;
  form: string;
  mape: number | null;
  mae: number | null;
  cycles: number | null;
  status: string | null;
}

interface MapeBarProps {
  value: number | null;
  maxValue: number;
}

/** MapeBar — 用 div 宽度模拟水平柱状条 */
const MapeBar: React.FC<MapeBarProps> = ({ value, maxValue }) => {
  if (value === null) {
    return <Text type="secondary">—</Text>;
  }
  const pct = value * 100;
  const barWidth = maxValue > 0 ? Math.min((pct / maxValue) * 100, 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div
        style={{
          width: `${Math.max(barWidth, 2)}%`,
          minWidth: 4,
          maxWidth: 160,
          height: 14,
          backgroundColor: mapeColor(value),
          borderRadius: 2,
          transition: 'width 0.3s',
        }}
      />
      <Text style={{ color: mapeColor(value), fontWeight: 600, whiteSpace: 'nowrap' }}>
        {formatMape(value)}
      </Text>
    </div>
  );
};

// ===========================================================================
// 主组件
// ===========================================================================

const AccuracyTrendChart: React.FC<AccuracyTrendChartProps> = ({ slot }) => {
  const {
    monitoringSnapshot,
    loading,
    error,
    fetchMonitoringSnapshot,
  } = useAccuracyOperationsStore();

  // 槽位切换时重新拉取快照
  useEffect(() => {
    if (slot) {
      fetchMonitoringSnapshot(slot);
    }
  }, [slot, fetchMonitoringSnapshot]);

  // ---------- 加载中 ----------
  if (loading.snapshot) {
    return (
      <Card title={<><LineChartOutlined /> 精度趋势</>}>
        <div style={{ textAlign: 'center', padding: '40px 0' }}>
          <Spin tip="加载精度监控快照…" />
        </div>
      </Card>
    );
  }

  // ---------- 错误 ----------
  if (error.snapshot) {
    return (
      <Card title={<><LineChartOutlined /> 精度趋势</>}>
        <Alert
          type="error"
          message="加载失败"
          description={error.snapshot}
          showIcon
          action={
            <a onClick={() => fetchMonitoringSnapshot(slot)}>重试</a>
          }
        />
      </Card>
    );
  }

  // ---------- 空态 ----------
  if (!monitoringSnapshot) {
    return (
      <Card title={<><LineChartOutlined /> 精度趋势</>}>
        <Empty description="暂无精度监控数据" />
      </Card>
    );
  }

  // ---------- 构建表格行 ----------
  const rows: BarRow[] = [];

  if (monitoringSnapshot.production) {
    const m = monitoringSnapshot.production;
    rows.push({
      key: `prod-${m.workflow_id}`,
      label: `生产 · ${m.version_tag || m.workflow_id}`,
      form: 'production',
      mape: m.rolling_mape,
      mae: m.rolling_mae,
      cycles: m.valid_cycle_count,
      status: m.status,
    });
  }

  monitoringSnapshot.shadows.forEach((m: MonitoringMetrics, i: number) => {
    rows.push({
      key: `shadow-${m.workflow_id}-${i}`,
      label: `影子${i + 1} · ${m.version_tag || m.workflow_id}`,
      form: 'shadow',
      mape: m.rolling_mape,
      mae: m.rolling_mae,
      cycles: m.valid_cycle_count,
      status: m.status,
    });
  });

  monitoringSnapshot.prelaunches.forEach((m: MonitoringMetrics, i: number) => {
    rows.push({
      key: `pre-${m.workflow_id}-${i}`,
      label: `预上线${i + 1} · ${m.version_tag || m.workflow_id}`,
      form: 'prelaunch',
      mape: m.rolling_mape,
      mae: m.rolling_mae,
      cycles: m.valid_cycle_count,
      status: m.status,
    });
  });

  // 计算最大 MAPE 用于柱宽比例（转为百分比单位）
  const maxMapePct = rows.reduce((acc, r) => {
    const pct = r.mape !== null ? r.mape * 100 : 0;
    return Math.max(acc, pct);
  }, 0);
  const chartMax = Math.max(maxMapePct * 1.1, 1); // 留 10% 余量，至少 1%

  // ---------- 汇总 Statistics ----------
  const prod = monitoringSnapshot.production;
  const bestShadow = monitoringSnapshot.shadows.reduce<MonitoringMetrics | null>(
    (best, s) => {
      if (s.rolling_mape === null) return best;
      if (best === null || best.rolling_mape === null) return s;
      return s.rolling_mape < best.rolling_mape ? s : best;
    },
    null,
  );

  // ---------- 表格列定义 ----------
  const columns = [
    {
      title: '形态 / 版本',
      dataIndex: 'label',
      key: 'label',
      render: (text: string, record: BarRow) => (
        <span>
          <Tag
            color={
              record.form === 'production'
                ? 'blue'
                : record.form === 'shadow'
                ? 'purple'
                : 'cyan'
            }
            style={{ marginRight: 6 }}
          >
            {record.form === 'production'
              ? '生产'
              : record.form === 'shadow'
              ? '影子'
              : '预上线'}
          </Tag>
          <Text style={{ fontSize: 12 }}>{text.split(' · ')[1] ?? text}</Text>
        </span>
      ),
    },
    {
      title: '滚动 MAPE',
      dataIndex: 'mape',
      key: 'mape',
      width: 220,
      render: (value: number | null) => (
        <MapeBar value={value} maxValue={chartMax} />
      ),
    },
    {
      title: '滚动 MAE',
      dataIndex: 'mae',
      key: 'mae',
      render: (value: number | null) =>
        value !== null ? value.toFixed(4) : <Text type="secondary">—</Text>,
    },
    {
      title: '有效周期',
      dataIndex: 'cycles',
      key: 'cycles',
      render: (value: number | null) =>
        value !== null ? value : <Text type="secondary">—</Text>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (value: string | null) =>
        value ? (
          <Tag color={value === 'active' ? 'green' : 'default'}>{value}</Tag>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
  ];

  return (
    <Card
      title={<><LineChartOutlined /> 精度趋势</>}
      extra={
        <Text type="secondary" style={{ fontSize: 12 }}>
          滚动 MAPE 趋势图（多形态对比），基于监控快照
        </Text>
      }
    >
      {/* 汇总指标行 */}
      <Row gutter={16} style={{ marginBottom: 20 }}>
        <Col span={6}>
          <Statistic
            title="生产模型 MAPE"
            value={prod?.rolling_mape !== null && prod?.rolling_mape !== undefined
              ? (prod.rolling_mape * 100).toFixed(2)
              : '—'}
            suffix={prod?.rolling_mape !== null && prod?.rolling_mape !== undefined ? '%' : ''}
            valueStyle={{ color: mapeColor(prod?.rolling_mape ?? null) }}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="最优影子 MAPE"
            value={bestShadow?.rolling_mape !== null && bestShadow?.rolling_mape !== undefined
              ? (bestShadow.rolling_mape * 100).toFixed(2)
              : '—'}
            suffix={bestShadow?.rolling_mape !== null && bestShadow?.rolling_mape !== undefined ? '%' : ''}
            valueStyle={{ color: mapeColor(bestShadow?.rolling_mape ?? null) }}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="影子模型数"
            value={monitoringSnapshot.shadows.length}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="预上线模型数"
            value={monitoringSnapshot.prelaunches.length}
          />
        </Col>
      </Row>

      {/* 柱状对比表 */}
      {rows.length === 0 ? (
        <Empty description="暂无模型监控数据" />
      ) : (
        <Table<BarRow>
          dataSource={rows}
          columns={columns}
          pagination={false}
          size="small"
          rowKey="key"
          style={{ marginTop: 8 }}
        />
      )}

      <div style={{ marginTop: 12 }}>
        <Text type="secondary" style={{ fontSize: 11 }}>
          说明：柱宽正比于滚动 MAPE 大小，颜色反映精度等级（绿&lt;5% / 橙5-10% / 红&gt;10%）。
          ECharts 时序趋势图待接入历史评估数据后启用。
        </Text>
      </div>
    </Card>
  );
};

export default AccuracyTrendChart;
// @AI_GENERATED: end
