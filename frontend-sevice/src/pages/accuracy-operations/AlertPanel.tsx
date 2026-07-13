// @AI_GENERATED
/**
 * AlertPanel.tsx — 精度告警面板
 *
 * 展示当前 slot 下 production / shadow 形态的精度告警列表。
 * 支持按 AlertStatus 过滤，点击行触发 onSelectAlert 回调。
 * 数据来源：GET /accuracy-operations/alerts（经 accuracyOperationsStore.fetchAlerts）。
 *
 * 相关 spec：.kiro/specs/accuracy-operations/
 *   - Requirements 10.5（告警列表展示）
 *   - Task 13.5
 */

import React, { useEffect, useState } from 'react';
import { Card, Table, Tag, Select, Spin, Alert as AntAlert, Button, Empty, Badge } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ReloadOutlined } from '@ant-design/icons';
import { useAccuracyOperationsStore } from '../../stores/accuracyOperationsStore';
import type {
  AccuracyAlert,
  AlertStatus,
  ModelForm,
  AlertSeverity,
} from '../../types/accuracy-operations';

// ===========================================================================
// Props
// ===========================================================================

interface AlertPanelProps {
  /** slot — 当前操作槽位名称（如 "default"） */
  slot: string;
  /**
   * onSelectAlert — 点击告警行时的回调
   * @param alert — 被点击的 AccuracyAlert 实体
   */
  onSelectAlert?: (alert: AccuracyAlert) => void;
}

// ===========================================================================
// 常量
// ===========================================================================

/** STATUS_OPTIONS — 告警状态过滤下拉选项 */
const STATUS_OPTIONS: Array<{ label: string; value: AlertStatus | '' }> = [
  { label: '全部状态', value: '' },
  { label: '待处理 (open)', value: 'open' },
  { label: 'RCA 进行中 (rca_running)', value: 'rca_running' },
  { label: '恢复中 (recovering)', value: 'recovering' },
  { label: '观察中 (observing)', value: 'observing' },
  { label: '已关闭 (closed)', value: 'closed' },
];

// ===========================================================================
// 工具函数
// ===========================================================================

/** getModelFormBadge — model_form（形态）→ Badge */
function getModelFormBadge(form: ModelForm): React.ReactNode {
  const map: Record<ModelForm, { color: string; text: string }> = {
    production: { color: 'green', text: '生产' },
    shadow: { color: 'blue', text: '影子' },
  };
  const cfg = map[form];
  return <Badge color={cfg.color} text={cfg.text} />;
}

/** getSeverityTag — severity（严重级别）→ Tag */
function getSeverityTag(severity: AlertSeverity): React.ReactNode {
  const map: Record<AlertSeverity, string> = {
    warning: 'orange',
    critical: 'red',
  };
  const labelMap: Record<AlertSeverity, string> = {
    warning: '警告',
    critical: '严重',
  };
  return <Tag color={map[severity]}>{labelMap[severity]}</Tag>;
}

/** getStatusTag — status（告警状态）→ Tag */
function getStatusTag(status: AlertStatus): React.ReactNode {
  const map: Record<AlertStatus, string> = {
    open: 'blue',
    rca_running: 'processing',
    recovering: 'orange',
    observing: 'purple',
    closed: 'default',
  };
  const labelMap: Record<AlertStatus, string> = {
    open: '待处理',
    rca_running: 'RCA 中',
    recovering: '恢复中',
    observing: '观察中',
    closed: '已关闭',
  };
  return <Tag color={map[status]}>{labelMap[status]}</Tag>;
}

/** formatDate — ISO8601 时间 → 本地可读格式 */
function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

// ===========================================================================
// 表格列定义
// ===========================================================================

function buildColumns(
  onSelectAlert?: (alert: AccuracyAlert) => void,
): ColumnsType<AccuracyAlert> {
  return [
    {
      title: '告警 ID',
      dataIndex: 'alert_id',
      key: 'alert_id',
      width: 140,
      render: (v: string) => (
        <code style={{ fontSize: '12px', wordBreak: 'break-all' }}>{v}</code>
      ),
    },
    {
      title: '形态',
      dataIndex: 'model_form',
      key: 'model_form',
      width: 80,
      render: (form: ModelForm) => getModelFormBadge(form),
    },
    {
      title: '版本',
      dataIndex: 'version_tag',
      key: 'version_tag',
      render: (v: string) => <code>{v}</code>,
    },
    {
      title: '退化幅度',
      dataIndex: 'degradation_pct',
      key: 'degradation_pct',
      align: 'right' as const,
      width: 90,
      render: (v: number) => `${v.toFixed(2)}%`,
    },
    {
      title: '严重级别',
      dataIndex: 'severity',
      key: 'severity',
      width: 90,
      render: (v: AlertSeverity) => getSeverityTag(v),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: AlertStatus) => getStatusTag(v),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      render: (v: string) => formatDate(v),
    },
    ...(onSelectAlert
      ? [
          {
            title: '操作',
            key: 'action',
            width: 80,
            render: (_: unknown, record: AccuracyAlert) => (
              <Button
                type="link"
                size="small"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectAlert(record);
                }}
              >
                查看详情
              </Button>
            ),
          },
        ]
      : []),
  ];
}

// ===========================================================================
// 组件
// ===========================================================================

/**
 * AlertPanel — 精度告警面板组件
 *
 * - 展示 production / shadow 形态的告警列表（API 已过滤，客户端二次校验）
 * - 支持按状态过滤
 * - 点击行触发 onSelectAlert
 */
const AlertPanel: React.FC<AlertPanelProps> = ({ slot, onSelectAlert }) => {
  const { alerts, loading, error, fetchAlerts } = useAccuracyOperationsStore();

  /** statusFilter — 当前状态过滤值（'' 表示全部） */
  const [statusFilter, setStatusFilter] = useState<AlertStatus | ''>('');

  // 挂载或 slot 变更时拉取告警列表
  useEffect(() => {
    fetchAlerts(slot);
  }, [slot, fetchAlerts]);

  // ---------- 加载态 ----------
  if (loading.alerts) {
    return (
      <Card title="精度告警" aria-label="精度告警面板">
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin tip="加载中..." />
        </div>
      </Card>
    );
  }

  // ---------- 错误态 ----------
  if (error.alerts) {
    return (
      <Card title="精度告警" aria-label="精度告警面板">
        <AntAlert
          type="error"
          message="加载失败"
          description={error.alerts}
          action={
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => fetchAlerts(slot)}
            >
              重试
            </Button>
          }
        />
      </Card>
    );
  }

  // ---------- 客户端过滤：仅保留 production / shadow 形态，并按状态筛选 ----------
  const productionShadowAlerts = alerts.filter(
    (a) => a.model_form === 'production' || a.model_form === 'shadow',
  );

  const filteredAlerts = statusFilter
    ? productionShadowAlerts.filter((a) => a.status === statusFilter)
    : productionShadowAlerts;

  // ---------- 工具栏：状态过滤 ----------
  const toolbar = (
    <div style={{ marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span style={{ fontSize: '13px', color: '#666' }}>状态过滤：</span>
      <Select<AlertStatus | ''>
        value={statusFilter}
        onChange={setStatusFilter}
        style={{ width: 180 }}
        options={STATUS_OPTIONS}
        aria-label="按告警状态过滤"
      />
      <Button
        size="small"
        icon={<ReloadOutlined />}
        onClick={() => fetchAlerts(slot, statusFilter || undefined)}
        aria-label="刷新告警列表"
      >
        刷新
      </Button>
    </div>
  );

  // ---------- 空态 ----------
  if (filteredAlerts.length === 0) {
    return (
      <Card title="精度告警" aria-label="精度告警面板">
        {toolbar}
        <Empty description="暂无数据" />
      </Card>
    );
  }

  // ---------- 正常态 ----------
  return (
    <Card title="精度告警" aria-label="精度告警面板">
      {toolbar}
      <Table<AccuracyAlert>
        rowKey="alert_id"
        columns={buildColumns(onSelectAlert)}
        dataSource={filteredAlerts}
        pagination={{ pageSize: 20, showSizeChanger: false }}
        size="small"
        onRow={(record) => ({
          onClick: () => onSelectAlert?.(record),
          style: { cursor: onSelectAlert ? 'pointer' : 'default' },
          'aria-label': `告警 ${record.alert_id}`,
        })}
        aria-label="精度告警列表"
      />
    </Card>
  );
};

export default AlertPanel;
// @AI_GENERATED: end
