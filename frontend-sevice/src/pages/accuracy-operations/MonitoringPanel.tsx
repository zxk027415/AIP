// @AI_GENERATED
/**
 * MonitoringPanel.tsx — 精度监控面板
 *
 * 只读展示当前 slot 下所有模型形态（生产/影子/预上线）的精度监控指标：
 * version_tag、model_form、rolling_mape、rolling_mae、valid_cycle_count、status。
 * 数据来源：GET /accuracy-operations/monitoring/snapshot（经 accuracyOperationsStore.fetchMonitoringSnapshot）。
 *
 * 相关 spec：.kiro/specs/accuracy-operations/
 *   - Requirements 10.5（精度监控展示，只读）
 *   - Task 13.4
 */

import React, { useEffect } from 'react';
import { Card, Table, Tag, Spin, Alert, Button, Empty, Badge } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined } from '@ant-design/icons';
import { useAccuracyOperationsStore } from '../../stores/accuracyOperationsStore';
import type { MonitoringMetrics } from '../../types/accuracy-operations';

// ===========================================================================
// Props
// ===========================================================================

interface MonitoringPanelProps {
  /** slot — 当前操作槽位名称（如 "default"） */
  slot: string;
}

// ===========================================================================
// 内部类型：带形态标注的 MonitoringMetrics 行
// ===========================================================================

interface MetricsRow extends MonitoringMetrics {
  /** model_form — 展示用形态标签 */
  model_form: 'production' | 'shadow' | 'prelaunch';
  /** _rowKey — 表格 rowKey */
  _rowKey: string;
}

// ===========================================================================
// 工具函数
// ===========================================================================

/** getFormBadge — 形态 → Badge 颜色 + 中文标签 */
function getFormBadge(form: MetricsRow['model_form']): React.ReactNode {
  const map: Record<MetricsRow['model_form'], { color: string; text: string }> = {
    production: { color: 'green', text: '生产' },
    shadow: { color: 'blue', text: '影子' },
    prelaunch: { color: 'orange', text: '预上线' },
  };
  const cfg = map[form];
  return <Badge color={cfg.color} text={cfg.text} />;
}

/** formatMetric — 格式化数值型监控指标，null 时显示 "-" */
function formatMetric(val: number | null, decimals = 4): string {
  if (val === null || val === undefined) return '-';
  return val.toFixed(decimals);
}

// ===========================================================================
// 表格列定义
// ===========================================================================

const columns: ColumnsType<MetricsRow> = [
  {
    title: '版本',
    dataIndex: 'version_tag',
    key: 'version_tag',
    render: (v: string) => <code>{v}</code>,
  },
  {
    title: '形态',
    dataIndex: 'model_form',
    key: 'model_form',
    render: (form: MetricsRow['model_form']) => getFormBadge(form),
  },
  {
    title: '滚动 MAPE',
    dataIndex: 'rolling_mape',
    key: 'rolling_mape',
    align: 'right' as const,
    render: (v: number | null) => formatMetric(v),
  },
  {
    title: '滚动 MAE',
    dataIndex: 'rolling_mae',
    key: 'rolling_mae',
    align: 'right' as const,
    render: (v: number | null) => formatMetric(v),
  },
  {
    title: '有效周期数',
    dataIndex: 'valid_cycle_count',
    key: 'valid_cycle_count',
    align: 'right' as const,
    render: (v: number | null) => (v === null ? '-' : v),
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    render: (v: string | null) => {
      if (!v) return '-';
      const colorMap: Record<string, string> = {
        active: 'green',
        degraded: 'red',
        warning: 'orange',
        unknown: 'default',
      };
      return <Tag color={colorMap[v] ?? 'default'}>{v}</Tag>;
    },
  },
];

// ===========================================================================
// 组件
// ===========================================================================

/**
 * MonitoringPanel — 精度监控面板组件
 *
 * 按 生产模型 / 影子模型 / 预上线模型 三节展示监控快照。
 * 纯只读，无 RCA / 恢复操作按钮。
 */
const MonitoringPanel: React.FC<MonitoringPanelProps> = ({ slot }) => {
  const { monitoringSnapshot, loading, error, fetchMonitoringSnapshot } =
    useAccuracyOperationsStore();

  // 挂载或 slot 变更时拉取快照
  useEffect(() => {
    fetchMonitoringSnapshot(slot);
  }, [slot, fetchMonitoringSnapshot]);

  // ---------- 加载态 ----------
  if (loading.snapshot) {
    return (
      <Card title="精度监控" aria-label="精度监控面板">
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin tip="加载中..." />
        </div>
      </Card>
    );
  }

  // ---------- 错误态 ----------
  if (error.snapshot) {
    return (
      <Card title="精度监控" aria-label="精度监控面板">
        <Alert
          type="error"
          message="加载失败"
          description={error.snapshot}
          action={
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => fetchMonitoringSnapshot(slot)}
            >
              重试
            </Button>
          }
        />
      </Card>
    );
  }

  // ---------- 空态 ----------
  if (!monitoringSnapshot) {
    return (
      <Card title="精度监控" aria-label="精度监控面板">
        <Empty description="暂无数据" />
      </Card>
    );
  }

  // ---------- 构建各节表格数据 ----------
  const productionRows: MetricsRow[] = monitoringSnapshot.production
    ? [{ ...monitoringSnapshot.production, model_form: 'production', _rowKey: 'production-0' }]
    : [];

  const shadowRows: MetricsRow[] = monitoringSnapshot.shadows.map((m, i) => ({
    ...m,
    model_form: 'shadow',
    _rowKey: `shadow-${i}`,
  }));

  const prelaunchRows: MetricsRow[] = monitoringSnapshot.prelaunches.map((m, i) => ({
    ...m,
    model_form: 'prelaunch',
    _rowKey: `prelaunch-${i}`,
  }));

  const hasAnyData =
    productionRows.length > 0 || shadowRows.length > 0 || prelaunchRows.length > 0;

  if (!hasAnyData) {
    return (
      <Card title="精度监控" aria-label="精度监控面板">
        <Empty description="暂无数据" />
      </Card>
    );
  }

  // ---------- Section 渲染工具 ----------
  const renderSection = (title: string, rows: MetricsRow[]) => {
    if (rows.length === 0) return null;
    return (
      <div style={{ marginBottom: '20px' }}>
        <div
          style={{
            fontWeight: 600,
            fontSize: '13px',
            color: '#666',
            marginBottom: '8px',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}
        >
          {title}
        </div>
        <Table<MetricsRow>
          rowKey="_rowKey"
          columns={columns}
          dataSource={rows}
          pagination={false}
          size="small"
          bordered={false}
          aria-label={`${title}监控数据表`}
        />
      </div>
    );
  };

  return (
    <Card title="精度监控" aria-label="精度监控面板">
      {renderSection('生产模型', productionRows)}
      {renderSection('影子模型', shadowRows)}
      {renderSection('预上线模型', prelaunchRows)}
    </Card>
  );
};

export default MonitoringPanel;
// @AI_GENERATED: end
