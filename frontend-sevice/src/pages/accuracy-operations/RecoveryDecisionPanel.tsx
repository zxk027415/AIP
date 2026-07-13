// @AI_GENERATED
/**
 * RecoveryDecisionPanel.tsx — 恢复决策面板 + 影子切换确认弹窗
 *
 * 包含两个组件：
 *
 * 1. RecoveryDecisionPanel
 *    展示当前恢复决策状态，支持"触发仲裁"（无决策时）和"执行切换"（shadow_switch + pending 时）。
 *
 * 2. ShadowSwitchModal
 *    影子模型切换确认弹窗，确认后调用 accuracyOperationsApi.executeShadowSwitch。
 *
 * 相关 spec：accuracy-operations / Task 13.7
 */

import React, { useState } from 'react';
import {
  Card,
  Tag,
  Button,
  Descriptions,
  Modal,
  Typography,
  Alert,
  Space,
  Empty,
  Badge,
} from 'antd';
import {
  ThunderboltOutlined,
  SwapOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import { accuracyOperationsApi } from '../../services/accuracyOperationsApi';
import type {
  RecoveryDecision,
  AccuracyAlert,
  RecoveryChannel,
  DecisionStatus,
} from '../../types/accuracy-operations';

const { Text, Paragraph } = Typography;

// ===========================================================================
// 颜色/标签辅助
// ===========================================================================

/** channelColor — 恢复通道颜色 */
const channelColor: Record<RecoveryChannel, string> = {
  shadow_switch: 'blue',
  observe: 'default',
};

/** channelLabel — 恢复通道中文标签 */
const channelLabel: Record<RecoveryChannel, string> = {
  shadow_switch: '通道A · 影子切换',
  observe: '观察等待',
};

/** decisionStatusColor — 决策状态颜色（AntD Tag color） */
const decisionStatusColor: Record<DecisionStatus, string> = {
  pending: 'orange',
  executing: 'blue',
  succeeded: 'green',
  failed: 'red',
  rolled_back: 'default',
};

/** decisionStatusLabel — 决策状态中文 */
const decisionStatusLabel: Record<DecisionStatus, string> = {
  pending: '待执行',
  executing: '执行中',
  succeeded: '已成功',
  failed: '已失败',
  rolled_back: '已回滚',
};

// ===========================================================================
// 辅助：SLA 倒计时文字展示
// ===========================================================================

/**
 * SlaDeadlineText — 展示 SLA 截止时间与剩余时间
 * 若已超期则以红色标注。
 */
const SlaDeadlineText: React.FC<{ slaDeadline: string }> = ({ slaDeadline }) => {
  const deadline = new Date(slaDeadline);
  const now = new Date();
  const diffMs = deadline.getTime() - now.getTime();
  const isOverdue = diffMs < 0;

  const absDiffMs = Math.abs(diffMs);
  const hours = Math.floor(absDiffMs / 3600000);
  const minutes = Math.floor((absDiffMs % 3600000) / 60000);
  const remainText = `${hours}h ${minutes}m`;

  return (
    <Space>
      <ClockCircleOutlined style={{ color: isOverdue ? '#f5222d' : '#1677ff' }} />
      <Text style={{ color: isOverdue ? '#f5222d' : undefined }}>
        {slaDeadline}
      </Text>
      <Text type={isOverdue ? 'danger' : 'secondary'} style={{ fontSize: 12 }}>
        {isOverdue ? `（已超期 ${remainText}）` : `（剩余 ${remainText}）`}
      </Text>
    </Space>
  );
};

// ===========================================================================
// ShadowSwitchModal
// ===========================================================================

export interface ShadowSwitchModalProps {
  /** visible — 弹窗是否可见 */
  visible: boolean;
  /** slot — 当前操作槽位 */
  slot: string;
  /** decisionId — 关联的恢复决策 ID */
  decisionId: string;
  /** onConfirm — 切换成功后的回调 */
  onConfirm: () => void;
  /** onCancel — 取消弹窗的回调 */
  onCancel: () => void;
}

/**
 * ShadowSwitchModal — 确认影子模型切换弹窗
 *
 * 展示切换目标 slot 和 decision_id，附风险提示。
 * 确认后调用 POST /recovery/shadow-switch（shadow_workflow_id 传空字符串，
 * 由仲裁器重新锁定最优影子）。
 */
export const ShadowSwitchModal: React.FC<ShadowSwitchModalProps> = ({
  visible,
  slot,
  decisionId,
  onConfirm,
  onCancel,
}) => {
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      // shadow_workflow_id 传空字符串，仲裁器会重新找最优影子
      await accuracyOperationsApi.executeShadowSwitch(slot, '', decisionId);
      setConfirming(false);
      onConfirm();
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        '执行影子切换失败，请重试';
      setError(msg);
      setConfirming(false);
    }
  };

  const handleCancel = () => {
    if (confirming) return;
    setError(null);
    onCancel();
  };

  return (
    <Modal
      title={
        <Space>
          <SwapOutlined />
          确认影子模型切换
        </Space>
      }
      open={visible}
      onCancel={handleCancel}
      footer={[
        <Button key="cancel" onClick={handleCancel} disabled={confirming}>
          取消
        </Button>,
        <Button
          key="confirm"
          type="primary"
          danger
          loading={confirming}
          onClick={handleConfirm}
          icon={<SwapOutlined />}
        >
          确认切换
        </Button>,
      ]}
      maskClosable={!confirming}
    >
      <Descriptions column={1} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label="槽位 (slot)">{slot}</Descriptions.Item>
        <Descriptions.Item label="决策 ID (decision_id)">
          <Text code style={{ fontSize: 12 }}>{decisionId}</Text>
        </Descriptions.Item>
      </Descriptions>

      <Alert
        type="warning"
        showIcon
        message="操作风险提示"
        description="切换后将自动监控精度变化，若未改善将触发回滚。请确认当前有达标影子模型可切换。"
        style={{ marginBottom: error ? 12 : 0 }}
      />

      {error && (
        <Alert
          type="error"
          message="切换失败"
          description={error}
          showIcon
          style={{ marginTop: 12 }}
        />
      )}
    </Modal>
  );
};

// ===========================================================================
// RecoveryDecisionPanel
// ===========================================================================

export interface RecoveryDecisionPanelProps {
  /** decision — 当前恢复决策（null 表示尚未仲裁） */
  decision: RecoveryDecision | null;
  /** alert — 当前选中告警（用于判断是否可触发仲裁） */
  alert: AccuracyAlert | null;
  /**
   * onTriggerDecision — 触发仲裁的回调
   * @param slot — 槽位名称
   * @param rcaReportId — 关联 RCA 报告 ID
   */
  onTriggerDecision: (slot: string, rcaReportId: string) => void;
}

/**
 * RecoveryDecisionPanel — 恢复决策面板
 *
 * 根据决策/告警状态展示：
 * - 无决策且告警有 rca_report_id → "触发仲裁" 按钮
 * - 有决策 → 展示 channel、reason、SLA、状态
 * - channel=shadow_switch + status=pending → "执行切换" 按钮
 */
const RecoveryDecisionPanel: React.FC<RecoveryDecisionPanelProps> = ({
  decision,
  alert,
  onTriggerDecision,
}) => {
  const [modalVisible, setModalVisible] = useState(false);
  const [triggering, setTriggering] = useState(false);

  const handleTriggerDecision = () => {
    if (!alert?.rca_report_id) return;
    setTriggering(true);
    onTriggerDecision(alert.slot, alert.rca_report_id);
    // 父组件异步处理，不在本组件等待
    setTriggering(false);
  };

  const handleSwitchConfirmed = () => {
    setModalVisible(false);
    // 父组件可以监听 decision 状态变化来刷新
  };

  // ---------- 无告警 ----------
  if (!alert) {
    return (
      <Card title={<><ThunderboltOutlined /> 恢复决策</>}>
        <Empty description="请先选中告警" />
      </Card>
    );
  }

  // ---------- 无决策，但有 rca_report_id → 可触发仲裁 ----------
  if (!decision) {
    const canTrigger = Boolean(alert.rca_report_id);
    return (
      <Card title={<><ThunderboltOutlined /> 恢复决策</>}>
        {canTrigger ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text type="secondary">
              RCA 报告已就绪（{alert.rca_report_id}），可触发仲裁决策。
            </Text>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              loading={triggering}
              onClick={handleTriggerDecision}
            >
              触发仲裁
            </Button>
          </Space>
        ) : (
          <Empty description="请先完成 RCA 分析，再触发仲裁" />
        )}
      </Card>
    );
  }

  // ---------- 有决策 ----------
  const canExecuteSwitch =
    decision.channel === 'shadow_switch' && decision.status === 'pending';

  return (
    <>
      <Card
        title={<><ThunderboltOutlined /> 恢复决策</>}
        extra={
          canExecuteSwitch && (
            <Button
              type="primary"
              icon={<SwapOutlined />}
              onClick={() => setModalVisible(true)}
            >
              执行切换
            </Button>
          )
        }
      >
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="恢复通道">
            <Tag color={channelColor[decision.channel]}>
              {channelLabel[decision.channel]}
            </Tag>
          </Descriptions.Item>

          <Descriptions.Item label="决策理由">
            <Paragraph style={{ marginBottom: 0 }}>{decision.decision_reason}</Paragraph>
          </Descriptions.Item>

          <Descriptions.Item label="执行状态">
            <Tag color={decisionStatusColor[decision.status]}>
              {decisionStatusLabel[decision.status]}
            </Tag>
          </Descriptions.Item>

          <Descriptions.Item label="SLA 截止">
            <SlaDeadlineText slaDeadline={decision.sla_deadline} />
          </Descriptions.Item>

          <Descriptions.Item label="置信度门控">
            {decision.confidence_gate_passed ? (
              <Badge status="success" text="通过" />
            ) : (
              <Badge status="error" text="未通过" />
            )}
          </Descriptions.Item>

          {decision.switch_event_id && (
            <Descriptions.Item label="切换事件 ID">
              <Text code style={{ fontSize: 12 }}>{decision.switch_event_id}</Text>
            </Descriptions.Item>
          )}

          {decision.rollback_of && (
            <Descriptions.Item label="回滚来源">
              <Text code style={{ fontSize: 12 }}>{decision.rollback_of}</Text>
            </Descriptions.Item>
          )}

          <Descriptions.Item label="决策 ID">
            <Text type="secondary" style={{ fontSize: 12 }}>{decision.decision_id}</Text>
          </Descriptions.Item>

          <Descriptions.Item label="创建时间">
            <Text type="secondary" style={{ fontSize: 12 }}>{decision.created_at}</Text>
          </Descriptions.Item>
        </Descriptions>

        {canExecuteSwitch && (
          <Alert
            type="info"
            showIcon
            message="影子切换待执行"
            description="仲裁决策为通道A（影子切换），点击"执行切换"确认后将触发切换流程。"
            style={{ marginTop: 12 }}
          />
        )}
      </Card>

      {/* 影子切换确认弹窗 */}
      <ShadowSwitchModal
        visible={modalVisible}
        slot={alert.slot}
        decisionId={decision.decision_id}
        onConfirm={handleSwitchConfirmed}
        onCancel={() => setModalVisible(false)}
      />
    </>
  );
};

export default RecoveryDecisionPanel;
// @AI_GENERATED: end
