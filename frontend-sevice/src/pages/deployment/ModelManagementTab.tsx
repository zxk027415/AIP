// @AI_GENERATED: algorithm-deployment-refactor 9.1 + 阶段2
/**
 * ModelManagementTab.tsx — "算法部署 → 模型管理" Tab
 *
 * 三区布局（本次更新）：
 *   1. 生产模型区
 *   2. 影子池区（锦标赛，排第一且连续优于生产才建议切换）
 *   3. 预上线池区（安全闸门，每个独立跟生产比，期满达标 → 毕业为 shadow）
 *
 * 自动切换配置弹窗新增字段：
 *   training_window_days（训练窗口天数）、max_shadow_slots（影子上限）、max_prelaunch_slots（预上线上限）
 *
 * 字段名变更：evaluation_window_days → switch_observation_days（向后兼容读旧值）
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Empty,
  Form,
  InputNumber,
  Modal,
  Progress,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  HistoryOutlined,
  ReloadOutlined,
  RollbackOutlined,
  SettingOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import {
  deploymentApi,
  type DeploymentSlotView,
  type ModelVersionView,
  type PrelaunchModelView,
  type SlotConfigUpdate,
  type VersionHistoryItem,
} from '../../services/deploymentApi';

const { Text } = Typography;

/** 版本历史 Modal 状态 */
interface VersionModalState {
  open: boolean;
  slot: string;
  loading: boolean;
  versions: VersionHistoryItem[];
}

/** 切换确认 Modal 状态 */
interface SwitchModalState {
  open: boolean;
  slot: string;
  target: ModelVersionView | null;
  submitting: boolean;
}

/** 回滚确认 Modal 状态 */
interface RollbackModalState {
  open: boolean;
  slot: string;
  submitting: boolean;
}

/** role 标签颜色映射 —— production/shadow/retired */
const ROLE_TAG_COLOR: Record<VersionHistoryItem['role'], string> = {
  production: 'green',
  shadow: 'blue',
  retired: 'default',
};

const ROLE_TAG_LABEL: Record<VersionHistoryItem['role'], string> = {
  production: '生产',
  shadow: '影子',
  retired: '已退役',
};

/**
 * formatMape —— 把 MAPE / accuracy_score 渲染成两位小数百分点；空值展示 "—"
 * 本项目内 accuracy_score 就是 MAPE（越低越好），所以直接展示数值 + %。
 */
function formatMape(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${v.toFixed(2)}%`;
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    // 展示到分钟即可，避免 slot 列表过密
    return d.toLocaleString('zh-CN', { hour12: false });
  } catch {
    return iso;
  }
}

/**
 * isShadowEligibleForSwitch —— 判断某个影子模型是否达到切换建议阈值
 *
 * 规则（与后端 SwitchDecisionEngine.check_switch_eligibility 保持一致的展示语义）：
 *   1) 已达到观察窗口天数：consecutive_better_days >= switch_observation_days
 *   2) 精度优于 production：accuracy_score < production.latest_mape（MAPE 越低越好）
 */
function isShadowEligibleForSwitch(
  shadow: ModelVersionView,
  slot: DeploymentSlotView,
): boolean {
  const prod = slot.production_model;
  if (!prod) return false;
  const prodMape = prod.latest_mape ?? prod.accuracy_score;
  const shadowMape = shadow.accuracy_score;
  if (prodMape === null || prodMape === undefined) return false;
  if (shadowMape === null || shadowMape === undefined) return false;
  // switch_observation_days 是新字段名，兼容旧字段名 evaluation_window_days
  const obsDays = slot.switch_observation_days ?? slot.evaluation_window_days ?? 7;
  return shadow.consecutive_better_days >= obsDays && shadowMape < prodMape;
}

/**
 * getPrelaunchStatus —— 判断预上线项的达标状态（用于 UI 颜色提示）
 */
function getPrelaunchStatus(
  item: PrelaunchModelView,
  prodMape: number | null | undefined,
): 'ok' | 'warning' | 'fail' | 'unknown' {
  const meta = item.prelaunch_meta;
  if (!meta || meta.current_rolling_mape === null || meta.current_rolling_mape === undefined) return 'unknown';
  const threshold = (prodMape ?? meta.production_rolling_mape ?? null);
  if (threshold === null) return 'unknown';
  const limit = threshold * (1 + meta.graduate_tolerance_pct / 100);
  const mape = meta.current_rolling_mape;
  if (mape <= limit * 0.98) return 'ok';   // 明显达标
  if (mape <= limit) return 'warning';     // 边缘达标
  return 'fail';                           // 超标
}

const ModelManagementTab: React.FC = () => {
  const [messageApi, contextHolder] = message.useMessage();
  const [loading, setLoading] = useState<boolean>(false);
  const [slots, setSlots] = useState<Record<string, DeploymentSlotView>>({});
  const [configSaving, setConfigSaving] = useState<Record<string, boolean>>({});

  // Config 弹窗状态
  const [configModal, setConfigModal] = useState<{
    open: boolean;
    slot: string;
    submitting: boolean;
  }>({ open: false, slot: '', submitting: false });
  const [configForm] = Form.useForm<SlotConfigUpdate>();

  const [versionModal, setVersionModal] = useState<VersionModalState>({
    open: false,
    slot: '',
    loading: false,
    versions: [],
  });
  const [switchModal, setSwitchModal] = useState<SwitchModalState>({
    open: false,
    slot: '',
    target: null,
    submitting: false,
  });
  const [rollbackModal, setRollbackModal] = useState<RollbackModalState>({
    open: false,
    slot: '',
    submitting: false,
  });

  // -------------------------------------------------------------------------
  // 数据加载
  // -------------------------------------------------------------------------

  const loadSlots = useCallback(async () => {
    setLoading(true);
    try {
      const res = await deploymentApi.listSlots();
      setSlots(res.slots ?? {});
    } catch (err: any) {
      messageApi.error(`加载部署槽位失败：${err?.message ?? String(err)}`);
      setSlots({});
    } finally {
      setLoading(false);
    }
  }, [messageApi]);

  useEffect(() => {
    loadSlots();
  }, [loadSlots]);

  // -------------------------------------------------------------------------
  // Config 弹窗
  // -------------------------------------------------------------------------

  const openConfigModal = (slotName: string) => {
    const slot = slots[slotName];
    if (!slot) return;
    configForm.setFieldsValue({
      auto_switch_enabled: slot.auto_switch_enabled,
      switch_observation_days: slot.switch_observation_days ?? slot.evaluation_window_days,
      cooldown_hours: slot.cooldown_hours,
      threshold_mape: slot.threshold_mape ?? undefined,
      training_window_days: slot.training_window_days ?? 30,
      max_shadow_slots: slot.max_shadow_slots ?? 3,
      max_prelaunch_slots: slot.max_prelaunch_slots ?? 2,
    });
    setConfigModal({ open: true, slot: slotName, submitting: false });
  };

  const closeConfigModal = () => {
    if (configModal.submitting) return;
    setConfigModal((s) => ({ ...s, open: false }));
    configForm.resetFields();
  };

  const submitConfig = async () => {
    try {
      const values = await configForm.validateFields();
      setConfigModal((s) => ({ ...s, submitting: true }));
      const payload: SlotConfigUpdate = {
        auto_switch_enabled: values.auto_switch_enabled,
        switch_observation_days: values.switch_observation_days,
        cooldown_hours: values.cooldown_hours,
        threshold_mape: values.threshold_mape ?? null,
        training_window_days: values.training_window_days,
        max_shadow_slots: values.max_shadow_slots,
        max_prelaunch_slots: values.max_prelaunch_slots,
      };
      const updated = await deploymentApi.updateSlotConfig(configModal.slot, payload);
      setSlots((prev) => ({
        ...prev,
        [configModal.slot]: {
          ...prev[configModal.slot],
          ...updated,
          // 同时用 alias 更新，兼容旧版 isShadowEligibleForSwitch 逻辑
          evaluation_window_days: updated.switch_observation_days ?? updated.evaluation_window_days,
        },
      }));
      messageApi.success(`已更新 ${configModal.slot} 的配置`);
      closeConfigModal();
    } catch (err: any) {
      if (err?.errorFields) return; // AntD validation error
      messageApi.error(`更新配置失败：${err?.message ?? String(err)}`);
      setConfigModal((s) => ({ ...s, submitting: false }));
    }
  };

  // -------------------------------------------------------------------------
  // 版本历史 Modal
  // -------------------------------------------------------------------------

  const openVersionModal = useCallback(
    async (slotName: string) => {
      setVersionModal({ open: true, slot: slotName, loading: true, versions: [] });
      try {
        const res = await deploymentApi.listVersions(slotName);
        setVersionModal({ open: true, slot: slotName, loading: false, versions: res.versions ?? [] });
      } catch (err: any) {
        messageApi.error(`加载版本历史失败：${err?.message ?? String(err)}`);
        setVersionModal({ open: true, slot: slotName, loading: false, versions: [] });
      }
    },
    [messageApi],
  );

  const closeVersionModal = () =>
    setVersionModal({ open: false, slot: '', loading: false, versions: [] });

  // -------------------------------------------------------------------------
  // 切换 Modal
  // -------------------------------------------------------------------------

  const openSwitchModal = (slotName: string, target: ModelVersionView) =>
    setSwitchModal({ open: true, slot: slotName, target, submitting: false });
  const closeSwitchModal = () =>
    setSwitchModal({ open: false, slot: '', target: null, submitting: false });

  const confirmSwitch = async () => {
    if (!switchModal.target) return;
    setSwitchModal((s) => ({ ...s, submitting: true }));
    try {
      await deploymentApi.switchModel(switchModal.slot, {
        target_workflow_id: switchModal.target.workflow_id,
        trigger_type: 'manual',
        reason: '人工操作从模型管理面板发起切换',
      });
      messageApi.success(`已切换：${switchModal.slot} → ${switchModal.target.version_tag}`);
      closeSwitchModal();
      await loadSlots();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      messageApi.error(`切换失败：${detail?.message ?? err?.message ?? String(err)}`);
      setSwitchModal((s) => ({ ...s, submitting: false }));
    }
  };

  // -------------------------------------------------------------------------
  // 回滚 Modal
  // -------------------------------------------------------------------------

  const openRollbackModal = (slotName: string) =>
    setRollbackModal({ open: true, slot: slotName, submitting: false });
  const closeRollbackModal = () =>
    setRollbackModal({ open: false, slot: '', submitting: false });

  const confirmRollback = async () => {
    setRollbackModal((s) => ({ ...s, submitting: true }));
    try {
      await deploymentApi.rollbackModel(rollbackModal.slot, { reason: '人工从模型管理面板发起回滚' });
      messageApi.success(`已回滚：${rollbackModal.slot}`);
      closeRollbackModal();
      await loadSlots();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      messageApi.error(`回滚失败：${detail?.message ?? err?.message ?? String(err)}`);
      setRollbackModal((s) => ({ ...s, submitting: false }));
    }
  };

  // -------------------------------------------------------------------------
  // 自动切换开关（快捷操作，不打开弹窗）
  // -------------------------------------------------------------------------

  const handleAutoSwitchChange = async (slotName: string, checked: boolean) => {
    setConfigSaving((s) => ({ ...s, [slotName]: true }));
    try {
      const updated = await deploymentApi.updateSlotConfig(slotName, { auto_switch_enabled: checked });
      setSlots((prev) => ({
        ...prev,
        [slotName]: {
          ...prev[slotName],
          auto_switch_enabled: updated.auto_switch_enabled,
          updated_at: updated.updated_at,
        },
      }));
      messageApi.success(`已${checked ? '启用' : '关闭'}自动切换：${slotName}`);
    } catch (err: any) {
      messageApi.error(`更新自动切换配置失败：${err?.message ?? String(err)}`);
    } finally {
      setConfigSaving((s) => ({ ...s, [slotName]: false }));
    }
  };

  // -------------------------------------------------------------------------
  // 渲染
  // -------------------------------------------------------------------------

  const slotList = useMemo(() => Object.values(slots), [slots]);

  return (
    <>
      {contextHolder}
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Text type="secondary">
            管理每个 slot 的生产 / 影子（锦标赛）/ 预上线（安全闸门）三类模型。
          </Text>
          <Button icon={<ReloadOutlined />} onClick={loadSlots} loading={loading}>
            刷新
          </Button>
        </div>

        <Spin spinning={loading}>
          {slotList.length === 0 ? (
            <Empty description="尚未配置任何部署槽位" />
          ) : (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              {slotList.map((slot) => (
                <SlotCard
                  key={slot.slot}
                  slot={slot}
                  configSaving={configSaving[slot.slot] ?? false}
                  onAutoSwitchChange={handleAutoSwitchChange}
                  onOpenConfig={() => openConfigModal(slot.slot)}
                  onViewVersions={() => openVersionModal(slot.slot)}
                  onSwitchTo={(model) => openSwitchModal(slot.slot, model)}
                  onRollback={() => openRollbackModal(slot.slot)}
                />
              ))}
            </Space>
          )}
        </Spin>
      </Space>

      {/* Config 弹窗 */}
      <Modal
        open={configModal.open}
        title={<Space><SettingOutlined />配置 — {configModal.slot}</Space>}
        onCancel={closeConfigModal}
        onOk={submitConfig}
        okText="保存"
        cancelText="取消"
        confirmLoading={configModal.submitting}
        maskClosable={!configModal.submitting}
        width={480}
        destroyOnClose
      >
        <Form form={configForm} layout="vertical" preserve={false} style={{ marginTop: 8 }}>
          <Form.Item name="auto_switch_enabled" label="自动切换" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="switch_observation_days"
            label={<span>切换观察天数 <Text type="secondary" style={{ fontSize: 12 }}>shadow 连续多少天优于生产才建议切换</Text></span>}
            rules={[{ required: true, type: 'number', min: 1, max: 30 }]}
          >
            <InputNumber min={1} max={30} style={{ width: '100%' }} addonAfter="天" />
          </Form.Item>
          <Form.Item
            name="training_window_days"
            label={<span>训练窗口天数 <Text type="secondary" style={{ fontSize: 12 }}>跟 AutoResearch train_days 语义一致</Text></span>}
            rules={[{ required: true, type: 'number', min: 7, max: 730 }]}
          >
            <InputNumber min={7} max={730} style={{ width: '100%' }} addonAfter="天" />
          </Form.Item>
          <Form.Item
            name="max_shadow_slots"
            label={<span>影子池上限 <Text type="secondary" style={{ fontSize: 12 }}>每日 cron 最多跑几个 shadow</Text></span>}
            rules={[{ required: true, type: 'number', min: 1, max: 10 }]}
          >
            <InputNumber min={1} max={10} style={{ width: '100%' }} addonAfter="个" />
          </Form.Item>
          <Form.Item
            name="max_prelaunch_slots"
            label={<span>预上线池上限 <Text type="secondary" style={{ fontSize: 12 }}>最多同时观察几个 prelaunch</Text></span>}
            rules={[{ required: true, type: 'number', min: 1, max: 5 }]}
          >
            <InputNumber min={1} max={5} style={{ width: '100%' }} addonAfter="个" />
          </Form.Item>
          <Form.Item
            name="cooldown_hours"
            label="切换冷却时长"
            rules={[{ required: true, type: 'number', min: 0 }]}
          >
            <InputNumber min={0} style={{ width: '100%' }} addonAfter="小时" />
          </Form.Item>
          <Form.Item name="threshold_mape" label="精度阈值（可选，低于此值触发回滚建议）">
            <InputNumber min={0} max={100} style={{ width: '100%' }} addonAfter="%" />
          </Form.Item>
        </Form>
      </Modal>

      <VersionHistoryModal state={versionModal} onClose={closeVersionModal} />

      <Modal
        open={switchModal.open}
        title={<Space><SwapOutlined style={{ color: '#faad14' }} /><span>确认切换生产模型</span></Space>}
        onCancel={closeSwitchModal}
        onOk={confirmSwitch}
        okText="确认切换"
        okButtonProps={{ danger: true, loading: switchModal.submitting }}
        cancelButtonProps={{ disabled: switchModal.submitting }}
        maskClosable={!switchModal.submitting}
        closable={!switchModal.submitting}
      >
        {switchModal.target && (
          <Space direction="vertical" size={8} style={{ width: '100%' }}>
            <Alert type="warning" showIcon message="切换后原生产模型将被降级为 retired 状态" />
            <Descriptions size="small" column={1} labelStyle={{ width: 120, color: '#64748b' }}>
              <Descriptions.Item label="槽位">{switchModal.slot}</Descriptions.Item>
              <Descriptions.Item label="目标版本">{switchModal.target.version_tag}</Descriptions.Item>
              <Descriptions.Item label="目标 MAPE">{formatMape(switchModal.target.accuracy_score)}</Descriptions.Item>
              <Descriptions.Item label="连续优于天数">{switchModal.target.consecutive_better_days}</Descriptions.Item>
            </Descriptions>
          </Space>
        )}
      </Modal>

      <Modal
        open={rollbackModal.open}
        title={<Space><RollbackOutlined style={{ color: '#faad14' }} /><span>确认回滚</span></Space>}
        onCancel={closeRollbackModal}
        onOk={confirmRollback}
        okText="确认回滚"
        okButtonProps={{ danger: true, loading: rollbackModal.submitting }}
        maskClosable={!rollbackModal.submitting}
        closable={!rollbackModal.submitting}
      >
        <Alert
          type="warning"
          showIcon
          message="回滚会把当前生产模型降级为 retired，前一版本恢复为 production"
          description={`槽位：${rollbackModal.slot}`}
        />
      </Modal>
    </>
  );
};

// ---------------------------------------------------------------------------
// SlotCard —— 单个 slot 的信息卡片（三区布局）
// ---------------------------------------------------------------------------

interface SlotCardProps {
  slot: DeploymentSlotView;
  configSaving: boolean;
  onAutoSwitchChange: (slotName: string, checked: boolean) => void;
  onOpenConfig: () => void;
  onViewVersions: () => void;
  onSwitchTo: (target: ModelVersionView) => void;
  onRollback: () => void;
}

const SlotCard: React.FC<SlotCardProps> = ({
  slot,
  configSaving,
  onAutoSwitchChange,
  onOpenConfig,
  onViewVersions,
  onSwitchTo,
  onRollback,
}) => {
  const prod = slot.production_model;
  const hasEligibleShadow = slot.shadow_models.some((s) => isShadowEligibleForSwitch(s, slot));
  const activePrelaunches = (slot.prelaunch_models ?? []).filter((m) => m.status === 'prelaunch');
  const obsDays = slot.switch_observation_days ?? slot.evaluation_window_days ?? 7;

  return (
    <Card
      bordered
      style={{ borderRadius: 10 }}
      bodyStyle={{ padding: 16 }}
      title={
        <Space size={10} wrap>
          <Tag color="geekblue" style={{ margin: 0 }}>slot</Tag>
          <span style={{ fontWeight: 600 }}>{slot.slot}</span>
          {hasEligibleShadow && (
            <Tag icon={<ThunderboltOutlined />} color="warning">有可切换影子</Tag>
          )}
          {activePrelaunches.length > 0 && (
            <Tag icon={<ClockCircleOutlined />} color="blue">
              预上线观察中 {activePrelaunches.length}/{slot.max_prelaunch_slots ?? 2}
            </Tag>
          )}
        </Space>
      }
      extra={
        <Space size={8}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            观察 {obsDays}天 · 训练 {slot.training_window_days ?? 30}天 · 冷却 {slot.cooldown_hours}h
          </Text>
          <Tooltip title="启用后满足观察窗口条件时自动切换；关闭仅 UI 高亮">
            <Space size={4}>
              <Text style={{ fontSize: 12, color: '#64748b' }}>自动切换</Text>
              <Switch
                size="small"
                checked={slot.auto_switch_enabled}
                loading={configSaving}
                onChange={(checked) => onAutoSwitchChange(slot.slot, checked)}
              />
            </Space>
          </Tooltip>
          <Button size="small" icon={<SettingOutlined />} onClick={onOpenConfig}>配置</Button>
          <Button size="small" icon={<HistoryOutlined />} onClick={onViewVersions}>版本历史</Button>
          <Button size="small" danger icon={<RollbackOutlined />} onClick={onRollback} disabled={!prod}>回滚</Button>
        </Space>
      }
    >
      {/* ── 生产模型区 ── */}
      <div style={{ marginBottom: 12 }}>
        <Text strong style={{ fontSize: 13, color: '#15803d' }}>🟢 生产模型</Text>
        {prod ? (
          <Card size="small" style={{ marginTop: 6, background: '#f0fdf4', borderColor: '#86efac' }} bordered>
            <Space size={24} wrap>
              <Space size={6}>
                <Text code style={{ fontSize: 12 }}>{prod.workflow_id}</Text>
                <Tag color="green">{prod.version_tag}</Tag>
              </Space>
              <Text style={{ fontSize: 13 }}>MAPE：<strong>{formatMape(prod.latest_mape ?? prod.accuracy_score)}</strong></Text>
              <Text type="secondary" style={{ fontSize: 12 }}>上线于：{formatDateTime(prod.deployed_at)}</Text>
            </Space>
          </Card>
        ) : (
          <div style={{ marginTop: 6, padding: '8px 12px', background: '#f8fafc', borderRadius: 6, color: '#94a3b8', fontSize: 13 }}>
            当前槽位尚无生产模型
          </div>
        )}
      </div>

      {/* ── 影子池区 ── */}
      <div style={{ marginBottom: 12 }}>
        <Text strong style={{ fontSize: 13, color: '#1d4ed8' }}>
          🔵 影子池（锦标赛） {slot.shadow_models.length}/{slot.max_shadow_slots ?? 3}
        </Text>
        {slot.shadow_models.length === 0 ? (
          <div style={{ marginTop: 6, padding: '8px 12px', background: '#f8fafc', borderRadius: 6, color: '#94a3b8', fontSize: 13 }}>
            暂无影子模型
          </div>
        ) : (
          <div style={{ marginTop: 6, border: '1px solid #e2e8f0', borderRadius: 6, overflow: 'hidden' }}>
            {slot.shadow_models.map((m, idx) => {
              const eligible = isShadowEligibleForSwitch(m, slot);
              return (
                <div
                  key={m.workflow_id}
                  style={{
                    padding: '8px 12px',
                    borderTop: idx > 0 ? '1px solid #f1f5f9' : undefined,
                    background: eligible ? '#fffbe6' : undefined,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                  }}
                >
                  <div style={{ flex: 1 }}>
                    <Space size={8} wrap>
                      <Tag color="blue">{m.version_tag}</Tag>
                      <Text code style={{ fontSize: 11 }}>{m.workflow_id}</Text>
                      {eligible && <Tag icon={<ThunderboltOutlined />} color="warning">可切换</Tag>}
                    </Space>
                    <div style={{ marginTop: 2, fontSize: 12, color: '#64748b' }}>
                      MAPE {formatMape(m.accuracy_score)} · 连续优于 {m.consecutive_better_days} 天
                    </div>
                  </div>
                  <Button
                    size="small"
                    type={eligible ? 'primary' : 'default'}
                    icon={<SwapOutlined />}
                    onClick={() => onSwitchTo(m)}
                  >
                    切换
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ── 预上线池区 ── */}
      <div>
        <Text strong style={{ fontSize: 13, color: '#7c3aed' }}>
          🟣 预上线池（安全闸门） {activePrelaunches.length}/{slot.max_prelaunch_slots ?? 2}
        </Text>
        {activePrelaunches.length === 0 ? (
          <div style={{ marginTop: 6, padding: '8px 12px', background: '#f8fafc', borderRadius: 6, color: '#94a3b8', fontSize: 13 }}>
            暂无预上线观察项。可在「预上线」Tab 入池。
          </div>
        ) : (
          <div style={{ marginTop: 6, border: '1px solid #e2e8f0', borderRadius: 6, overflow: 'hidden' }}>
            {activePrelaunches.map((m, idx) => {
              const meta = m.prelaunch_meta;
              const prodMape = prod?.accuracy_score;
              const statusCode = getPrelaunchStatus(m, prodMape);
              const statusColor = statusCode === 'ok' ? '#16a34a' : statusCode === 'warning' ? '#d97706' : statusCode === 'fail' ? '#dc2626' : '#94a3b8';
              const statusIcon = statusCode === 'ok' ? <CheckCircleOutlined /> : statusCode === 'warning' ? <WarningOutlined /> : statusCode === 'fail' ? <WarningOutlined /> : <ClockCircleOutlined />;
              const progressPct = meta ? Math.min(100, Math.round((meta.evaluated_cycles / meta.observation_days) * 100)) : 0;

              return (
                <div
                  key={m.workflow_id}
                  style={{
                    padding: '8px 12px',
                    borderTop: idx > 0 ? '1px solid #f1f5f9' : undefined,
                  }}
                >
                  <Space size={8} wrap>
                    <Tag color="purple">{m.version_tag}</Tag>
                    <Text code style={{ fontSize: 11 }}>{m.workflow_id}</Text>
                    <span style={{ color: statusColor, fontSize: 12 }}>
                      {statusIcon} MAPE {formatMape(meta?.current_rolling_mape)}
                    </span>
                  </Space>
                  {meta && (
                    <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Progress
                        percent={progressPct}
                        size="small"
                        style={{ flex: 1 }}
                        format={() => `${meta.evaluated_cycles}/${meta.observation_days}天`}
                        strokeColor={statusColor}
                      />
                      <Text type="secondary" style={{ fontSize: 11, whiteSpace: 'nowrap' }}>
                        容差 {meta.graduate_tolerance_pct}%
                      </Text>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Card>
  );
};

// ---------------------------------------------------------------------------
// VersionHistoryModal —— 版本历史弹窗
// ---------------------------------------------------------------------------

const VersionHistoryModal: React.FC<{
  state: VersionModalState;
  onClose: () => void;
}> = ({ state, onClose }) => {
  const columns: ColumnsType<VersionHistoryItem> = [
    {
      title: '角色',
      dataIndex: 'role',
      width: 90,
      render: (role: VersionHistoryItem['role']) => (
        <Tag color={ROLE_TAG_COLOR[role]}>{ROLE_TAG_LABEL[role]}</Tag>
      ),
    },
    {
      title: '版本',
      dataIndex: 'version_tag',
      width: 140,
    },
    {
      title: 'workflow_id',
      dataIndex: 'workflow_id',
      ellipsis: true,
      render: (id: string) => (
        <Text code copyable={{ text: id }} style={{ fontSize: 12 }}>
          {id}
        </Text>
      ),
    },
    {
      title: 'MAPE',
      dataIndex: 'accuracy_score',
      width: 100,
      render: (v: number | null) => formatMape(v),
    },
    {
      title: '连续优于',
      dataIndex: 'consecutive_better_days',
      width: 100,
      render: (d: number) => `${d} 天`,
    },
    {
      title: '注册时间',
      dataIndex: 'deployed_at',
      width: 180,
      render: (t: string) => formatDateTime(t),
    },
  ];
  return (
    <Modal
      open={state.open}
      title={`版本历史 — ${state.slot}`}
      onCancel={onClose}
      footer={<Button onClick={onClose}>关闭</Button>}
      width={880}
      destroyOnClose
    >
      <Spin spinning={state.loading}>
        <Table<VersionHistoryItem>
          size="small"
          rowKey="workflow_id"
          columns={columns}
          dataSource={state.versions}
          pagination={false}
          locale={{ emptyText: '暂无版本记录' }}
        />
      </Spin>
    </Modal>
  );
};

export default ModelManagementTab;
// @AI_GENERATED: end
