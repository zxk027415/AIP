import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Button, DatePicker, Descriptions, Empty, Form,
  InputNumber, Modal, Select, Space, Spin, Switch, Table, Tabs, Tag, message,
} from 'antd';
import ReactECharts from 'echarts-for-react';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import type { ColumnsType } from 'antd/es/table';
import {
  getLeaderboard, getMetricsHistory, getProductionRegistry, getSwitchLog,
  rollback, getConfig, updateConfig, listVersions,
  getPrelaunchQueue, graduatePrelaunch, cancelPrelaunch,
} from '../services/precisionOpsApi';
import type {
  LeaderboardEntry, SwitchEvent, SlotConfig, ProductionRegistryEntry, VersionEntry,
  PrelaunchItem,
} from '../types/precision-ops';

// ─── 本地类型 ───────────────────────────────────────────────────────────────

interface LeaderboardRow extends LeaderboardEntry {
  version_tag: string;
  version_status: VersionEntry['status'];
}

// getMetricsHistory 后端返回形状约定（workflow_id → 时序点列表）
interface MetricsHistoryData {
  [workflowId: string]: {
    timestamps: string[];
    mapes: number[];
  };
}

// ─── 常量 ────────────────────────────────────────────────────────────────────

const TRIGGER_TYPE_COLOR: Record<SwitchEvent['trigger_type'], string> = {
  automatic: 'blue',
  manual: 'green',
  rollback: 'orange',
};

const VERSION_STATUS_COLOR: Record<VersionEntry['status'], string> = {
  production: 'success',
  shadow: 'processing',
  retired: 'default',
};

const CONFIG_FIELDS: { key: keyof SlotConfig; label: string; type: 'number' | 'switch'; min?: number; max?: number }[] = [
  { key: 'evaluation_window_days', label: '评估窗口天数', type: 'number', min: 1, max: 365 },
  { key: 'degradation_threshold_pct', label: '退化阈值 (%)', type: 'number', min: 0, max: 100 },
  { key: 'switch_margin_pct', label: '切换裕量 (%)', type: 'number', min: 0, max: 100 },
  { key: 'cooldown_hours', label: '冷却期 (h)', type: 'number', min: 0, max: 8760 },
  { key: 'min_valid_cycles', label: '最小有效周期数', type: 'number', min: 1 },
  { key: 'rollback_window_hours', label: '回滚窗口 (h)', type: 'number', min: 0, max: 8760 },
  { key: 'auto_switch_enabled', label: '自动切换', type: 'switch' },
];

// ─── 工具函数 ────────────────────────────────────────────────────────────────

function isMetricsHistoryData(v: unknown): v is MetricsHistoryData {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return false;
  return Object.values(v as Record<string, unknown>).every(
    (entry) =>
      entry &&
      typeof entry === 'object' &&
      Array.isArray((entry as MetricsHistoryData[string]).timestamps) &&
      Array.isArray((entry as MetricsHistoryData[string]).mapes),
  );
}

// ─── 主组件 ──────────────────────────────────────────────────────────────────

const PrecisionOpsDashboardPage: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage();
  const [slot, setSlot] = useState('default');
  const [activeTab, setActiveTab] = useState('leaderboard');

  // 排行榜
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [leaderboardLoading, setLeaderboardLoading] = useState(false);

  // 时序图
  const [metricsHistory, setMetricsHistory] = useState<MetricsHistoryData | null>(null);
  const [metricsLoading, setMetricsLoading] = useState(false);

  // 生产登记（最近一条切换事件来源）
  const [production, setProduction] = useState<ProductionRegistryEntry | null>(null);

  // 最近一条切换事件（用于 Banner）
  const [latestSwitch, setLatestSwitch] = useState<SwitchEvent | null>(null);

  // 切换日志
  const [switchLog, setSwitchLog] = useState<SwitchEvent[]>([]);
  const [switchLogTotal, setSwitchLogTotal] = useState(0);
  const [switchLogPage, setSwitchLogPage] = useState(1);
  const [switchLogLoading, setSwitchLogLoading] = useState(false);
  const [filterTriggerType, setFilterTriggerType] = useState<string | undefined>();
  const [filterDateRange, setFilterDateRange] = useState<[Dayjs, Dayjs] | null>(null);

  // 配置面板
  const [config, setConfig] = useState<SlotConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [configForm] = Form.useForm<Partial<SlotConfig>>();

  // 回滚
  const [rollbackLoading, setRollbackLoading] = useState(false);

  // 预上线
  const [prelaunchQueue, setPrelaunchQueue] = useState<PrelaunchItem[]>([]);
  const [prelaunchLoading, setPrelaunchLoading] = useState(false);
  const [workerStatus, setWorkerStatus] = useState<any>(null);

  // 自动刷新
  const lastUpdatedRef = useRef<number>(Date.now());
  const [secondsSinceUpdate, setSecondsSinceUpdate] = useState(0);

  // ─── 数据加载 ──────────────────────────────────────────────────────────────

  const loadLeaderboard = useCallback(async () => {
    setLeaderboardLoading(true);
    try {
      const [entries, versions] = await Promise.all([
        getLeaderboard(slot),
        listVersions(slot),
      ]);

      // entries 现在是 LeaderboardEntry[]（API 层已解包）
      // versions 现在是 VersionEntry[]（API 层已解包）
      const metricsMap = new Map(
        (Array.isArray(entries) ? entries : []).map((e) => [e.workflow_id, e])
      );

      const versionList = Array.isArray(versions) ? versions : [];

      const rows: LeaderboardRow[] = versionList
        .filter((v) => v.status !== 'retired')
        .map((v) => {
          const metrics = metricsMap.get(v.workflow_id);
          return {
            workflow_id: v.workflow_id,
            version_tag: v.version_tag,
            version_status: v.status,
            rolling_mape: metrics?.rolling_mape ?? 0,
            rolling_mae: metrics?.rolling_mae ?? 0,
            valid_cycle_count: metrics?.valid_cycle_count ?? 0,
            total_cycle_count: metrics?.total_cycle_count ?? 0,
            last_evaluated_at: metrics?.last_evaluated_at ?? '-',
            status: metrics?.status ?? 'insufficient_data',
          };
        });

      rows.sort((a, b) => {
        if (a.valid_cycle_count > 0 && b.valid_cycle_count === 0) return -1;
        if (a.valid_cycle_count === 0 && b.valid_cycle_count > 0) return 1;
        return a.rolling_mape - b.rolling_mape;
      });

      setLeaderboard(rows);
      lastUpdatedRef.current = Date.now();
      setSecondsSinceUpdate(0);
    } catch (err) {
      console.error('loadLeaderboard failed:', err);
    } finally {
      setLeaderboardLoading(false);
    }
  }, [slot]);

  const loadMetricsHistory = useCallback(async () => {
    setMetricsLoading(true);
    try {
      const raw = await getMetricsHistory(slot);
      setMetricsHistory(isMetricsHistoryData(raw) ? raw : null);
    } catch {
      // 保留上次
    } finally {
      setMetricsLoading(false);
    }
  }, [slot]);

  const loadProductionAndLatestSwitch = useCallback(async () => {
    try {
      const [prod, logResult] = await Promise.all([
        getProductionRegistry(slot),
        getSwitchLog(slot, { page: 1, page_size: 1 }),
      ]);
      setProduction(prod);
      setLatestSwitch(logResult.events[0] ?? null);
    } catch {
      // 静默失败
    }
  }, [slot]);

  const loadSwitchLog = useCallback(
    async (page = switchLogPage) => {
      setSwitchLogLoading(true);
      try {
        const params: Parameters<typeof getSwitchLog>[1] = {
          page,
          page_size: 20,
          trigger_type: filterTriggerType,
          start_time: filterDateRange ? filterDateRange[0].toISOString() : undefined,
          end_time: filterDateRange ? filterDateRange[1].toISOString() : undefined,
        };
        const result = await getSwitchLog(slot, params);
        setSwitchLog(result.events);
        setSwitchLogTotal(result.total);
        setSwitchLogPage(page);
      } catch {
        // 静默失败
      } finally {
        setSwitchLogLoading(false);
      }
    },
    [slot, switchLogPage, filterTriggerType, filterDateRange],
  );

  const loadConfig = useCallback(async () => {
    setConfigLoading(true);
    try {
      const cfg = await getConfig(slot);
      setConfig(cfg);
      configForm.setFieldsValue(cfg as unknown as Partial<SlotConfig>);
    } catch {
      // 静默失败
    } finally {
      setConfigLoading(false);
    }
  }, [slot, configForm]);

  const loadPrelaunch = useCallback(async () => {
    setPrelaunchLoading(true);
    try {
      const res = await getPrelaunchQueue(slot);
      setPrelaunchQueue(Array.isArray(res.queue) ? res.queue : []);
    } catch {
      // 静默失败
    } finally {
      setPrelaunchLoading(false);
    }
  }, [slot]);

  const loadWorkerStatus = useCallback(async () => {
    try {
      const api = (await import('../services/api')).default;
      const res: any = await api.get(`/precision-ops/${slot}/prediction-worker/status`);
      setWorkerStatus(res);
    } catch { /* ignore */ }
  }, [slot]);

  const handleStartWorker = useCallback(async () => {
    try {
      const api = (await import('../services/api')).default;
      await api.post(`/precision-ops/${slot}/prediction-worker/start`, {
        start_date: '2026-04-01',
        observation_days: 7,
        train_days: 60,
        interval_seconds: 15,
        graduate_tolerance_pct: 5.0,
      });
      message.success('定时预测已启动，每 15s 推进一天');
    } catch (err: any) {
      message.error(err?.response?.data?.message || '启动失败');
    }
  }, [slot]);

  const handleGraduatePrelaunch = useCallback(async (id: string) => {
    Modal.confirm({
      title: '确认上线',
      content: '预上线模型将正式切换为生产模型，原生产模型降级为影子版本。',
      okText: '确认上线',
      onOk: async () => {
        try {
          await graduatePrelaunch(slot, id);
          message.success('已正式上线');
          loadPrelaunch();
          loadLeaderboard();
          loadProductionAndLatestSwitch();
        } catch (err: any) {
          message.error(err?.message || '上线失败');
        }
      },
    });
  }, [slot, loadPrelaunch, loadLeaderboard, loadProductionAndLatestSwitch]);

  const handleCancelPrelaunch = useCallback(async (id: string) => {
    try {
      await cancelPrelaunch(slot, id);
      message.success('已取消');
      loadPrelaunch();
    } catch (err: any) {
      message.error(err?.message || '取消失败');
    }
  }, [slot, loadPrelaunch]);

  // ─── 初始化与 slot 切换 ────────────────────────────────────────────────────

  useEffect(() => {
    loadLeaderboard();
    loadMetricsHistory();
    loadProductionAndLatestSwitch();
    loadPrelaunch();
    loadWorkerStatus();
  }, [loadLeaderboard, loadMetricsHistory, loadProductionAndLatestSwitch, loadPrelaunch, loadWorkerStatus]);

  useEffect(() => {
    if (activeTab === 'history') {
      loadSwitchLog(1);
    } else if (activeTab === 'config') {
      loadConfig();
    }
  }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── 60s 自动刷新 ──────────────────────────────────────────────────────────

  useEffect(() => {
    const refreshInterval = setInterval(() => {
      loadLeaderboard();
      loadProductionAndLatestSwitch();
      loadPrelaunch();
      loadWorkerStatus();
    }, 15_000);
    const tickInterval = setInterval(() => {
      setSecondsSinceUpdate(Math.floor((Date.now() - lastUpdatedRef.current) / 1000));
    }, 1_000);
    return () => {
      clearInterval(refreshInterval);
      clearInterval(tickInterval);
    };
  }, [loadLeaderboard, loadProductionAndLatestSwitch, loadPrelaunch, loadWorkerStatus]);

  // ─── 操作处理 ──────────────────────────────────────────────────────────────

  const handleRollback = () => {
    Modal.confirm({
      title: '确认回滚',
      content: '将回滚到上一个生产版本，请确认。',
      okText: '确认回滚',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        setRollbackLoading(true);
        try {
          await rollback(slot);
          messageApi.success('回滚成功');
          loadLeaderboard();
          loadProductionAndLatestSwitch();
        } catch {
          messageApi.error('回滚失败');
        } finally {
          setRollbackLoading(false);
        }
      },
    });
  };

  const handleConfigSave = async () => {
    let values: Partial<SlotConfig>;
    try {
      values = await configForm.validateFields() as unknown as Partial<SlotConfig>;
    } catch {
      return;
    }
    setConfigSaving(true);
    try {
      const updated = await updateConfig(slot, values);
      setConfig(updated);
      messageApi.success('配置已更新');
    } catch {
      messageApi.error('更新配置失败');
    } finally {
      setConfigSaving(false);
    }
  };

  // ─── 回滚按钮是否禁用 ──────────────────────────────────────────────────────

  const isRollbackExpired = (() => {
    if (!latestSwitch || !config) return true;
    const expireAt = dayjs(latestSwitch.timestamp).add(config.rollback_window_hours, 'hour');
    return dayjs().isAfter(expireAt);
  })();

  // ─── 排行榜表格列定义 ──────────────────────────────────────────────────────

  const leaderboardColumns: ColumnsType<LeaderboardRow> = [
    {
      title: '版本标签',
      dataIndex: 'version_tag',
      render: (tag: string, record) =>
        record.version_status === 'production' ? (
          <strong style={{ color: '#16a34a' }}>{tag}</strong>
        ) : (
          tag
        ),
    },
    {
      title: '状态',
      dataIndex: 'version_status',
      render: (status: VersionEntry['status']) => (
        <Tag color={VERSION_STATUS_COLOR[status]}>
          {status === 'production' ? '生产' : status === 'shadow' ? '影子' : '退役'}
        </Tag>
      ),
    },
    {
      title: '7天平均 MAPE',
      dataIndex: 'rolling_mape',
      defaultSortOrder: 'ascend',
      sorter: (a, b) => a.rolling_mape - b.rolling_mape,
      render: (v: number, record: LeaderboardRow) =>
        record.valid_cycle_count > 0 ? `${v.toFixed(4)}%` : '-',
    },
    {
      title: '有效周期数',
      dataIndex: 'valid_cycle_count',
    },
    {
      title: '最近评估',
      dataIndex: 'last_evaluated_at',
      render: (v: string) => (v && v !== '-' ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-'),
    },
  ];

  // ─── 时序图 Option ─────────────────────────────────────────────────────────

  const metricsChartOption = (() => {
    if (!metricsHistory) return null;
    const workflowIds = Object.keys(metricsHistory);
    if (workflowIds.length < 2) return null;
    const series = workflowIds.map((id) => ({
      name: id,
      type: 'line' as const,
      data: metricsHistory[id].mapes,
      smooth: true,
    }));
    // 使用第一个 workflow 的 timestamps 作为 x 轴
    const xData = metricsHistory[workflowIds[0]].timestamps.map((t) =>
      dayjs(t).format('MM-DD HH:mm'),
    );
    return {
      tooltip: { trigger: 'axis' },
      legend: { data: workflowIds, bottom: 0 },
      grid: { bottom: 50 },
      xAxis: { type: 'category', data: xData },
      yAxis: { type: 'value', name: 'MAPE', min: 0 },
      series,
    };
  })();

  // ─── 切换日志表格列定义 ────────────────────────────────────────────────────

  const switchLogColumns: ColumnsType<SwitchEvent> = [
    {
      title: '时间',
      dataIndex: 'timestamp',
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm'),
      width: 160,
    },
    {
      title: '触发类型',
      dataIndex: 'trigger_type',
      render: (v: SwitchEvent['trigger_type']) => (
        <Tag color={TRIGGER_TYPE_COLOR[v]}>
          {v === 'automatic' ? '自动' : v === 'manual' ? '手动' : '回滚'}
        </Tag>
      ),
      width: 100,
    },
    { title: '来源版本', dataIndex: 'source_workflow_id' },
    { title: '目标版本', dataIndex: 'target_workflow_id' },
    {
      title: '来源 MAPE',
      dataIndex: 'source_rolling_mape',
      render: (v: number) => v.toFixed(4),
      width: 110,
    },
    {
      title: '目标 MAPE',
      dataIndex: 'target_rolling_mape',
      render: (v: number) => v.toFixed(4),
      width: 110,
    },
    { title: '决策原因', dataIndex: 'decision_reason', ellipsis: true },
  ];

  // ─── 渲染 ──────────────────────────────────────────────────────────────────

  const leaderboardContent = (
    <div>
      {/* 排行榜表格 */}
      <Spin spinning={leaderboardLoading}>
        {leaderboard.length === 0 && !leaderboardLoading ? (
          <Empty description="暂无精度评估数据" style={{ margin: '32px 0' }} />
        ) : (
          <Table<LeaderboardRow>
            rowKey="version_tag"
            columns={leaderboardColumns}
            dataSource={leaderboard}
            pagination={false}
            size="small"
            rowClassName={(row) =>
              row.version_status === 'production' ? 'precision-prod-row' : ''
            }
            style={{ marginBottom: 24 }}
          />
        )}
      </Spin>

      {/* 时序图 */}
      <div style={{ marginTop: 8 }}>
        <div style={{ fontWeight: 600, marginBottom: 8, fontSize: 13 }}>各版本 MAPE 时序对比</div>
        <Spin spinning={metricsLoading}>
          {!metricsChartOption ? (
            <Empty description="版本数量不足 2 个，暂无对比数据" style={{ margin: '16px 0' }} />
          ) : (
            <ReactECharts option={metricsChartOption} style={{ height: 280 }} />
          )}
        </Spin>
      </div>
    </div>
  );

  const historyContent = (
    <div>
      {/* 切换事件 Banner */}
      {latestSwitch && (
        <Alert
          type="info"
          style={{ marginBottom: 16 }}
          message={
            <Space wrap>
              <span>
                最近切换：<strong>{latestSwitch.source_workflow_id}</strong>
                {' → '}
                <strong>{latestSwitch.target_workflow_id}</strong>
              </span>
              <Tag color={TRIGGER_TYPE_COLOR[latestSwitch.trigger_type]}>
                {latestSwitch.trigger_type === 'automatic'
                  ? '自动'
                  : latestSwitch.trigger_type === 'manual'
                  ? '手动'
                  : '回滚'}
              </Tag>
              <span style={{ color: '#8c98a8', fontSize: 12 }}>
                {dayjs(latestSwitch.timestamp).format('YYYY-MM-DD HH:mm')}
              </span>
              <Button
                size="small"
                danger
                loading={rollbackLoading}
                disabled={isRollbackExpired}
                onClick={handleRollback}
              >
                {isRollbackExpired ? '回滚窗口已过期' : '一键回滚'}
              </Button>
            </Space>
          }
        />
      )}

      {/* 过滤器 */}
      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          allowClear
          placeholder="触发类型"
          style={{ width: 140 }}
          value={filterTriggerType}
          onChange={(v) => {
            setFilterTriggerType(v);
          }}
          options={[
            { label: '自动', value: 'automatic' },
            { label: '手动', value: 'manual' },
            { label: '回滚', value: 'rollback' },
          ]}
        />
        <DatePicker.RangePicker
          value={filterDateRange}
          onChange={(range) => {
            setFilterDateRange(range as [Dayjs, Dayjs] | null);
          }}
        />
        <Button
          type="primary"
          size="small"
          onClick={() => loadSwitchLog(1)}
        >
          查询
        </Button>
      </Space>

      {/* 切换日志表格 */}
      <Table<SwitchEvent>
        rowKey="event_id"
        columns={switchLogColumns}
        dataSource={switchLog}
        loading={switchLogLoading}
        size="small"
        scroll={{ x: 900 }}
        pagination={{
          current: switchLogPage,
          pageSize: 20,
          total: switchLogTotal,
          showSizeChanger: false,
          onChange: (page) => loadSwitchLog(page),
        }}
      />
    </div>
  );

  const configContent = (
    <Spin spinning={configLoading}>
      {config ? (
        <Form
          form={configForm}
          layout="vertical"
          style={{ maxWidth: 480 }}
          initialValues={config as unknown as Record<string, unknown>}
        >
          {CONFIG_FIELDS.map(({ key, label, type, min, max }) => (
            <Form.Item key={key} name={key} label={label}>
              {type === 'switch' ? (
                <Switch />
              ) : (
                <InputNumber
                  min={min}
                  max={max}
                  style={{ width: '100%' }}
                  precision={type === 'number' ? 2 : 0}
                />
              )}
            </Form.Item>
          ))}
          <Form.Item>
            <Button type="primary" loading={configSaving} onClick={handleConfigSave}>
              保存配置
            </Button>
          </Form.Item>
        </Form>
      ) : (
        <Empty description="暂无配置数据" />
      )}
    </Spin>
  );

  const prelaunchContent = (
    <Spin spinning={prelaunchLoading}>
      <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 12, color: '#8c98a8' }}>
          预上线模型跟随定时预测任务运行，观察期满后自动判定毕业或失败。生产模板切换后预上线对比基准同步更新。
        </span>
        <Space>
          <Button size="small" onClick={loadPrelaunch}>刷新</Button>
          {!workerStatus?.running && (
            <Button size="small" onClick={handleStartWorker}>
              启动模拟定时预测
            </Button>
          )}
          {workerStatus?.running && (
            <Tag color="processing">定时预测运行中 ({workerStatus.current_day}/{workerStatus.total_days} 天)</Tag>
          )}
        </Space>
      </div>
      {prelaunchQueue.length === 0 ? (
        <Empty description="暂无预上线项。从候选池复验通过后点击「入预上线」加入。" style={{ margin: '32px 0' }} />
      ) : (
        <Table
          rowKey="id"
          size="small"
          dataSource={prelaunchQueue}
          pagination={false}
          columns={[
            {
              title: '预上线模型',
              dataIndex: 'version_tag',
              width: 200,
              render: (v: string) => <strong>{v || '-'}</strong>,
            },
            {
              title: '7天平均 MAPE',
              dataIndex: 'current_rolling_mape',
              width: 140,
              render: (v: number | null) => v != null ? `${v.toFixed(4)}%` : <span style={{ color: '#8c98a8' }}>待积累</span>,
            },
            {
              title: '生产 7天平均 MAPE',
              dataIndex: 'production_rolling_mape',
              width: 160,
              render: (v: number | null) => v != null ? `${v.toFixed(4)}%` : '-',
            },
            {
              title: '观察进度',
              key: 'progress',
              width: 120,
              render: (_: unknown, record: PrelaunchItem) => {
                return `${record.evaluated_cycles || 0} / ${record.observation_days} 天`;
              },
            },
            {
              title: '状态',
              dataIndex: 'status',
              width: 90,
              render: (v: string) => {
                const colorMap: Record<string, string> = { observing: 'blue', graduated: 'green', failed: 'red', cancelled: 'default' };
                const labelMap: Record<string, string> = { observing: '观察中', graduated: '已毕业', failed: '未通过', cancelled: '已取消' };
                return <Tag color={colorMap[v] || 'default'}>{labelMap[v] || v}</Tag>;
              },
            },
            {
              title: '操作',
              key: 'actions',
              width: 140,
              render: (_: unknown, record: PrelaunchItem) => {
                if (record.status !== 'observing') return '-';
                return (
                  <Space size="small">
                    <Button size="small" type="primary" onClick={() => handleGraduatePrelaunch(record.id)}>上线</Button>
                    <Button size="small" danger onClick={() => handleCancelPrelaunch(record.id)}>取消</Button>
                  </Space>
                );
              },
            },
          ]}
        />
      )}
    </Spin>
  );

  return (
    <div style={{ padding: 24 }}>
      {contextHolder}

      {/* 顶部：标题 + 健康中心说明 + Slot 选择 */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>模型健康中心</h2>
          <Select
            value={slot}
            onChange={setSlot}
            style={{ width: 180 }}
            options={[{ label: 'default', value: 'default' }]}
            placeholder="选择槽位"
          />
          <span style={{ fontSize: 12, color: '#8c98a8' }}>
            最后更新于 {secondsSinceUpdate} 秒前
          </span>
        </div>
        {/* 操作引导横幅 */}
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 0 }}
          message={
            <span style={{ fontSize: 13 }}>
              本页为只读健康监控（精度榜、切换历史、精度趋势图）。
              切换、调度、预上线等操作请到{' '}
              <a href="/algorithm-deployment" style={{ fontWeight: 600 }}>算法部署</a>
              {' '}页面完成。
            </span>
          }
        />
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          { key: 'leaderboard', label: '精度排行榜', children: leaderboardContent },
          { key: 'history', label: '切换历史', children: historyContent },
          { key: 'config', label: '配置（只读）', children: configContent },
          {
            key: 'root_cause',
            label: '根因分析',
            children: (
              <div style={{ padding: '32px 0', textAlign: 'center', color: '#94a3b8' }}>
                <p style={{ fontSize: 16, marginBottom: 8 }}>📊 根因分析</p>
                <p style={{ fontSize: 13 }}>功能建设中，将支持数据漂移检测、概念漂移检测和精度异常归因分析。</p>
              </div>
            ),
          },
        ]}
      />

      {/* 生产版本行背景色 */}
      <style>{`.precision-prod-row { background-color: #f0fff4; }`}</style>
    </div>
  );
};

export default PrecisionOpsDashboardPage;
