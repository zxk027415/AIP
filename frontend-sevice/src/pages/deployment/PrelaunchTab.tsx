// @AI_GENERATED: 阶段3 — PrelaunchTab
/**
 * PrelaunchTab.tsx — "算法部署 → 预上线" Tab
 *
 * 用途：
 *   - 展示当前所有槽位的预上线观察队列
 *   - 支持手动入池（填写 candidate_id / workflow_id / observation_days / tolerance）
 *   - 支持手动毕业（跳过观察期直接 → shadow）/ 取消（→ retired）
 *   - 每行显示观察进度条 + 当前 MAPE vs 生产 MAPE vs 门槛
 *
 * 语义说明：
 *   Prelaunch 是"安全闸门"，每个独立跟生产比（不互相竞争）
 *   毕业条件：observed_days >= observation_days + MAPE ≤ production*(1+tolerance/100)
 *   毕业后进入 shadow 池参加锦标赛
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  StopOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { deploymentApi, prelaunchApi, type PrelaunchModelView, type PrelaunchEnterRequest } from '../../services/deploymentApi';

const { Text } = Typography;

function formatMape(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${v.toFixed(2)}%`;
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('zh-CN', { hour12: false });
  } catch { return iso; }
}

const PrelaunchTab: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage();
  const [items, setItems] = useState<Array<PrelaunchModelView & { _slot: string }>>([]);
  const [loading, setLoading] = useState(false);
  const [rowLoading, setRowLoading] = useState<Record<string, boolean>>({});
  const [slotOptions, setSlotOptions] = useState<string[]>([]);

  // 入池弹窗
  const [enterOpen, setEnterOpen] = useState(false);
  const [enterSubmitting, setEnterSubmitting] = useState(false);
  const [enterForm] = Form.useForm<PrelaunchEnterRequest & { slot: string }>();

  // -------------------------------------------------------------------------
  // 加载数据
  // -------------------------------------------------------------------------

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const slotsRes = await deploymentApi.listSlots();
      const allSlots = Object.keys(slotsRes.slots ?? {});
      setSlotOptions(allSlots);

      const allItems: Array<PrelaunchModelView & { _slot: string }> = [];
      await Promise.all(
        allSlots.map(async (slot) => {
          try {
            const res = await prelaunchApi.listPrelaunches(slot);
            (res.prelaunches ?? []).forEach((item) => {
              allItems.push({ ...item, _slot: slot });
            });
          } catch { /* 单个 slot 失败静默 */ }
        })
      );
      // 按 status 排序：prelaunch 在前，retired 在后；同 status 按 started_at 降序
      allItems.sort((a, b) => {
        if (a.status !== b.status) {
          return a.status === 'prelaunch' ? -1 : 1;
        }
        const at = a.prelaunch_meta?.started_at ?? '';
        const bt = b.prelaunch_meta?.started_at ?? '';
        return bt.localeCompare(at);
      });
      setItems(allItems);
    } catch (err: any) {
      messageApi.error(`加载预上线队列失败：${err?.message ?? String(err)}`);
    } finally {
      setLoading(false);
    }
  }, [messageApi]);

  useEffect(() => { load(); }, [load]);

  // -------------------------------------------------------------------------
  // 手动毕业
  // -------------------------------------------------------------------------

  const handleGraduate = async (item: PrelaunchModelView & { _slot: string }) => {
    setRowLoading((s) => ({ ...s, [item.workflow_id]: true }));
    try {
      await prelaunchApi.graduatePrelaunch(item._slot, item.workflow_id);
      messageApi.success(`已手动毕业：${item.version_tag} → shadow`);
      await load();
    } catch (err: any) {
      messageApi.error(`手动毕业失败：${err?.message ?? String(err)}`);
    } finally {
      setRowLoading((s) => ({ ...s, [item.workflow_id]: false }));
    }
  };

  // -------------------------------------------------------------------------
  // 取消
  // -------------------------------------------------------------------------

  const handleCancel = async (item: PrelaunchModelView & { _slot: string }) => {
    setRowLoading((s) => ({ ...s, [item.workflow_id]: true }));
    try {
      await prelaunchApi.cancelPrelaunch(item._slot, item.workflow_id, 'manual_cancel');
      messageApi.success(`已取消：${item.version_tag}`);
      await load();
    } catch (err: any) {
      messageApi.error(`取消失败：${err?.message ?? String(err)}`);
    } finally {
      setRowLoading((s) => ({ ...s, [item.workflow_id]: false }));
    }
  };

  // -------------------------------------------------------------------------
  // 入池
  // -------------------------------------------------------------------------

  const openEnter = () => {
    enterForm.resetFields();
    enterForm.setFieldsValue({
      slot: slotOptions[0] ?? 'default',
      observation_days: 7,
      graduate_tolerance_pct: 5,
    });
    setEnterOpen(true);
  };

  const submitEnter = async () => {
    try {
      const values = await enterForm.validateFields();
      setEnterSubmitting(true);
      const { slot, ...body } = values;
      await prelaunchApi.enterPrelaunch(slot, body as PrelaunchEnterRequest);
      messageApi.success(`已入池：${body.workflow_id}`);
      setEnterOpen(false);
      await load();
    } catch (err: any) {
      if (err?.errorFields) return;
      messageApi.error(`入池失败：${err?.message ?? String(err)}`);
    } finally {
      setEnterSubmitting(false);
    }
  };

  // -------------------------------------------------------------------------
  // 表格列
  // -------------------------------------------------------------------------

  const columns: ColumnsType<PrelaunchModelView & { _slot: string }> = [
    {
      title: '槽位',
      dataIndex: '_slot',
      width: 110,
      render: (s: string) => <Tag>{s}</Tag>,
    },
    {
      title: '模型版本',
      dataIndex: 'version_tag',
      width: 160,
      render: (v: string, row) => (
        <Space direction="vertical" size={2}>
          <Text strong>{v}</Text>
          <Text code style={{ fontSize: 11 }}>{row.workflow_id}</Text>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s: string) => s === 'prelaunch'
        ? <Tag color="purple" icon={<ClockCircleOutlined />}>观察中</Tag>
        : <Tag color="default">已结束</Tag>,
    },
    {
      title: '观察进度',
      width: 180,
      render: (_: unknown, row) => {
        const meta = row.prelaunch_meta;
        if (!meta) return '—';
        const pct = Math.min(100, Math.round((meta.evaluated_cycles / meta.observation_days) * 100));
        return (
          <div>
            <Progress
              percent={pct}
              size="small"
              format={() => `${meta.evaluated_cycles}/${meta.observation_days}天`}
              strokeColor={pct >= 100 ? '#16a34a' : '#7c3aed'}
            />
          </div>
        );
      },
    },
    {
      title: '预上线 MAPE',
      width: 120,
      render: (_: unknown, row) => {
        const meta = row.prelaunch_meta;
        const mape = meta?.current_rolling_mape;
        const prod = meta?.production_rolling_mape;
        const tol = meta?.graduate_tolerance_pct ?? 5;
        const threshold = prod != null ? prod * (1 + tol / 100) : null;
        const ok = mape != null && threshold != null && mape <= threshold;
        return (
          <Space direction="vertical" size={1}>
            <Text style={{ color: ok ? '#16a34a' : '#dc2626', fontWeight: 600 }}>
              {ok ? <CheckCircleOutlined /> : <WarningOutlined />} {formatMape(mape)}
            </Text>
            {threshold != null && (
              <Text type="secondary" style={{ fontSize: 11 }}>门槛：{formatMape(threshold)}</Text>
            )}
          </Space>
        );
      },
    },
    {
      title: '生产 MAPE',
      width: 100,
      render: (_: unknown, row) => formatMape(row.prelaunch_meta?.production_rolling_mape),
    },
    {
      title: '入池时间',
      width: 160,
      render: (_: unknown, row) => formatDateTime(row.prelaunch_meta?.started_at),
    },
    {
      title: '操作',
      width: 200,
      fixed: 'right',
      render: (_: unknown, row) => {
        if (row.status !== 'prelaunch') return <Text type="secondary">已结束</Text>;
        const busy = rowLoading[row.workflow_id] ?? false;
        return (
          <Space size={4}>
            <Popconfirm
              title="确认手动毕业？"
              description="跳过观察期，直接提升为 shadow 参加锦标赛。"
              onConfirm={() => handleGraduate(row)}
              okText="毕业"
              cancelText="取消"
            >
              <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={busy}>
                手动毕业
              </Button>
            </Popconfirm>
            <Popconfirm
              title="确认取消？"
              description="取消后该候选变为 retired，不再观察。"
              onConfirm={() => handleCancel(row)}
              okText="取消观察"
              cancelText="保留"
              okButtonProps={{ danger: true }}
            >
              <Button size="small" danger icon={<StopOutlined />} loading={busy}>
                取消
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  const activeCount = items.filter((i) => i.status === 'prelaunch').length;

  return (
    <>
      {contextHolder}
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Alert
          type="info"
          showIcon
          message="预上线 — 安全闸门"
          description={
            <Text style={{ fontSize: 13 }}>
              每个预上线项独立跟生产模型比较（不互相竞争）。观察期满且 MAPE ≤ 生产×(1+容差) 则自动毕业为 shadow，
              再由 shadow 锦标赛决定谁上生产。可在这里手动入池候选、提前毕业或取消。
            </Text>
          }
        />

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary">观察中 {activeCount} 个</Text>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openEnter}>入池</Button>
          </Space>
        </div>

        <Table<PrelaunchModelView & { _slot: string }>
          size="middle"
          rowKey={(row) => `${row._slot}__${row.workflow_id}`}
          columns={columns}
          dataSource={items}
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          scroll={{ x: 1100 }}
          locale={{ emptyText: '暂无预上线记录' }}
        />
      </Space>

      {/* 入池弹窗 */}
      <Modal
        open={enterOpen}
        title="入预上线观察池"
        onCancel={() => { if (!enterSubmitting) setEnterOpen(false); }}
        onOk={submitEnter}
        okText="入池"
        cancelText="取消"
        confirmLoading={enterSubmitting}
        maskClosable={!enterSubmitting}
        width={500}
        destroyOnClose
      >
        <Form form={enterForm} layout="vertical" preserve={false}>
          <Form.Item name="slot" label="槽位" rules={[{ required: true }]}>
            <Select options={slotOptions.map((s) => ({ value: s, label: s }))} />
          </Form.Item>
          <Form.Item name="candidate_id" label="来源候选 ID" rules={[{ required: true, message: '请填写候选 ID' }]}>
            <Input placeholder="如：cand-abc123" />
          </Form.Item>
          <Form.Item name="workflow_id" label="Workflow ID" rules={[{ required: true, message: '请填写 workflow_id' }]}>
            <Input placeholder="如：workflow-load-forecast-backtest-v3" />
          </Form.Item>
          <Form.Item name="version_tag" label="版本标签（可选）">
            <Input placeholder="留空则自动生成" />
          </Form.Item>
          <Form.Item
            name="observation_days"
            label="观察天数"
            rules={[{ required: true, type: 'number', min: 1, max: 90 }]}
          >
            <InputNumber min={1} max={90} style={{ width: '100%' }} addonAfter="天" />
          </Form.Item>
          <Form.Item
            name="graduate_tolerance_pct"
            label={<span>毕业容差 <Text type="secondary" style={{ fontSize: 12 }}>预上线 MAPE 比生产高不超过此值仍可毕业</Text></span>}
            rules={[{ required: true, type: 'number', min: 0, max: 50 }]}
          >
            <InputNumber min={0} max={50} style={{ width: '100%' }} addonAfter="%" />
          </Form.Item>
          <Form.Item name="source_run_id" label="来源 Run ID（可选）">
            <Input placeholder="AutoResearch run_id（供审计）" />
          </Form.Item>
          <Form.Item name="note" label="备注（可选）">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default PrelaunchTab;
// @AI_GENERATED: end
