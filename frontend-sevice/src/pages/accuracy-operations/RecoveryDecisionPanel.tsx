// @AI_GENERATED
/**
 * RecoveryDecisionPanel.tsx — RCA 后的恢复仲裁与通道 A 执行面板。
 *
 * 仅展示并调用已有精度运营接口；通道 A 仍需用户在确认弹窗中明确执行。
 */
import React, { useState } from 'react';
import { Alert, Badge, Button, Card, Descriptions, Empty, Modal, Space, Tag, Typography } from 'antd';
import { ClockCircleOutlined, SwapOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { accuracyOperationsApi } from '../../services/accuracyOperationsApi';
import type { AccuracyAlert, DecisionStatus, RecoveryChannel, RecoveryDecision } from '../../types/accuracy-operations';

const { Text, Paragraph } = Typography;

const channelColor: Record<RecoveryChannel, string> = { shadow_switch: 'blue', observe: 'default' };
const channelLabel: Record<RecoveryChannel, string> = { shadow_switch: '通道 A · 影子切换', observe: '观察等待' };
const decisionStatusColor: Record<DecisionStatus, string> = { pending: 'orange', executing: 'blue', succeeded: 'green', failed: 'red', rolled_back: 'default' };
const decisionStatusLabel: Record<DecisionStatus, string> = { pending: '待执行', executing: '执行中', succeeded: '已成功', failed: '已失败', rolled_back: '已回滚' };

function SlaDeadlineText({ slaDeadline }: { slaDeadline: string }) {
  const deadline = new Date(slaDeadline);
  const remainingMs = deadline.getTime() - Date.now();
  const absoluteMs = Math.abs(remainingMs);
  const duration = `${Math.floor(absoluteMs / 3_600_000)}h ${Math.floor((absoluteMs % 3_600_000) / 60_000)}m`;
  const overdue = remainingMs < 0;
  return <Space><ClockCircleOutlined style={{ color: overdue ? '#f5222d' : '#1677ff' }} /><Text>{slaDeadline}</Text><Text type={overdue ? 'danger' : 'secondary'} style={{ fontSize: 12 }}>{overdue ? `（已超期 ${duration}）` : `（剩余 ${duration}）`}</Text></Space>;
}

interface ShadowSwitchModalProps {
  visible: boolean;
  slot: string;
  decision: RecoveryDecision;
  onConfirm: (updatedDecision: RecoveryDecision) => void;
  onCancel: () => void;
}

const ShadowSwitchModal: React.FC<ShadowSwitchModalProps> = ({ visible, slot, decision, onConfirm, onCancel }) => {
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleConfirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      const updatedDecision = await accuracyOperationsApi.executeShadowSwitch(slot, decision.target_workflow_id || '', decision.decision_id);
      onConfirm(updatedDecision);
    } catch (err: any) {
      setError(err?.response?.data?.detail?.message || err?.response?.data?.detail || err?.message || '执行影子切换失败，请重试。');
    } finally {
      setConfirming(false);
    }
  };

  return (
    <Modal
      title={<Space><SwapOutlined />确认执行通道 A</Space>}
      open={visible}
      onCancel={() => { if (!confirming) { setError(null); onCancel(); } }}
      maskClosable={!confirming}
      footer={[
        <Button key="cancel" onClick={onCancel} disabled={confirming}>取消</Button>,
        <Button key="confirm" type="primary" danger icon={<SwapOutlined />} loading={confirming} onClick={handleConfirm}>确认切换</Button>,
      ]}
    >
      <Descriptions column={1} size="small" bordered>
        <Descriptions.Item label="slot（槽位）">{slot}</Descriptions.Item>
        <Descriptions.Item label="目标影子版本"><Text code>{decision.target_workflow_id || '由后端重新定位'}@{decision.target_version_tag || '—'}</Text></Descriptions.Item>
        <Descriptions.Item label="decision_id（决策 ID）"><Text code>{decision.decision_id}</Text></Descriptions.Item>
      </Descriptions>
      <Alert type="warning" showIcon style={{ marginTop: 16 }} message="切换会真实变更当前槽位的 production/shadow/retired 身份" description="系统会追加一条部署切换审计事件；请只在确认目标槽位和仲裁理由正确后执行。" />
      {error ? <Alert type="error" showIcon style={{ marginTop: 12 }} message="切换失败" description={error} /> : null}
    </Modal>
  );
};

interface RecoveryDecisionPanelProps {
  /** decision — 已持久化或刚生成的恢复决策。 */
  decision: RecoveryDecision | null;
  /** alert — 当前选择的退化告警。 */
  alert: AccuracyAlert | null;
  /** onTriggerDecision — 在 RCA 成功后异步触发仲裁。 */
  onTriggerDecision: (slot: string, rcaReportId: string) => Promise<void>;
  /** onSwitchExecuted — 通道 A 成功后回传更新后的持久化决策。 */
  onSwitchExecuted: (updatedDecision: RecoveryDecision) => Promise<void>;
}

const RecoveryDecisionPanel: React.FC<RecoveryDecisionPanelProps> = ({ decision, alert, onTriggerDecision, onSwitchExecuted }) => {
  const [modalVisible, setModalVisible] = useState(false);
  const [triggering, setTriggering] = useState(false);

  const handleTriggerDecision = async () => {
    if (!alert?.rca_report_id) return;
    setTriggering(true);
    try { await onTriggerDecision(alert.slot, alert.rca_report_id); } finally { setTriggering(false); }
  };

  if (!alert) return <Card title={<><ThunderboltOutlined />恢复决策</>}><Empty description="请先在告警列表选择一条退化告警" /></Card>;

  if (!decision) {
    return (
      <Card title={<><ThunderboltOutlined />恢复决策</>}>
        {alert.rca_report_id ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text type="secondary">RCA 报告 <Text code>{alert.rca_report_id}</Text> 已就绪。仲裁会检查置信度、根因、样本数和影子优势。</Text>
            <Button type="primary" icon={<ThunderboltOutlined />} loading={triggering} onClick={() => void handleTriggerDecision()}>触发仲裁</Button>
          </Space>
        ) : <Empty description="请先触发并完成 RCA，才能生成恢复建议" />}
      </Card>
    );
  }

  const canExecuteSwitch = decision.channel === 'shadow_switch' && decision.status === 'pending';
  return (
    <>
      <Card title={<><ThunderboltOutlined />恢复决策</>} extra={canExecuteSwitch ? <Button type="primary" icon={<SwapOutlined />} onClick={() => setModalVisible(true)}>执行通道 A</Button> : null}>
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="恢复通道"><Tag color={channelColor[decision.channel]}>{channelLabel[decision.channel]}</Tag></Descriptions.Item>
          <Descriptions.Item label="决策理由"><Paragraph style={{ marginBottom: 0 }}>{decision.decision_reason}</Paragraph></Descriptions.Item>
          <Descriptions.Item label="执行状态"><Tag color={decisionStatusColor[decision.status]}>{decisionStatusLabel[decision.status]}</Tag></Descriptions.Item>
          <Descriptions.Item label="SLA 截止"><SlaDeadlineText slaDeadline={decision.sla_deadline} /></Descriptions.Item>
          <Descriptions.Item label="置信度门控">{decision.confidence_gate_passed ? <Badge status="success" text="通过" /> : <Badge status="error" text="未通过" />}</Descriptions.Item>
          {decision.target_workflow_id ? <Descriptions.Item label="通道 A 目标"><Text code>{decision.target_workflow_id}@{decision.target_version_tag || '—'}</Text></Descriptions.Item> : null}
          {decision.switch_event_id ? <Descriptions.Item label="切换事件 ID"><Text code>{decision.switch_event_id}</Text></Descriptions.Item> : null}
          {decision.rollback_of ? <Descriptions.Item label="回滚来源"><Text code>{decision.rollback_of}</Text></Descriptions.Item> : null}
          <Descriptions.Item label="decision_id（决策 ID）"><Text type="secondary">{decision.decision_id}</Text></Descriptions.Item>
        </Descriptions>
        {canExecuteSwitch ? <Alert type="info" showIcon style={{ marginTop: 12 }} message="通道 A 已获仲裁推荐，尚未执行" description="确认后才会提升目标 shadow 为 production，并将原 production 标记为 retired。" /> : null}
      </Card>
      <ShadowSwitchModal visible={modalVisible} slot={alert.slot} decision={decision} onConfirm={async (updatedDecision) => { setModalVisible(false); await onSwitchExecuted(updatedDecision); }} onCancel={() => setModalVisible(false)} />
    </>
  );
};

export default RecoveryDecisionPanel;
// @AI_GENERATED: end
