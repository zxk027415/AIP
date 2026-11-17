/**
 * SlotOpsClockBar — 调度/精度运营共用：当前检测到哪一天、演示喂数进度。
 */
import React from 'react';
import { Alert, Button, Space, Switch, Tag, Typography } from 'antd';
import { AuditOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import type { ObservabilityStatus } from '../../services/slotObservabilityApi';

const { Text } = Typography;

export type OpsClockStatus = ObservabilityStatus;

interface Props {
  status: OpsClockStatus | null;
  writable?: boolean;
  advancing?: boolean;
  replayBusy?: boolean;
  // @AI_GENERATED
  useRealModel?: boolean;
  onUseRealModelChange?: (value: boolean) => void;
  // @AI_GENERATED: end
  onAdvance?: () => void;
  onReset?: () => void;
  onReplayStep?: (points: 1 | 10 | 50) => void;
  onRebuildReplay?: () => void;
}

function pct(value?: number | null): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${(Number(value) * 100).toFixed(1)}%`;
}

const SlotOpsClockBar: React.FC<Props> = ({
  status,
  writable = false,
  advancing = false,
  replayBusy = false,
  useRealModel = false,
  onUseRealModelChange,
  onAdvance,
  onReset,
  onReplayStep,
  onRebuildReplay,
}) => {
  const day = status?.clock?.day;
  const index = status?.progress?.day_index ?? 0;
  // @AI_GENERATED: total_days 允许为空（pv_tsc 无演示总天数），不再硬回退 7。
  const total = status?.progress?.total_days;
  const acc = status?.accuracy;
  const slot = status?.slot || '';
  const replay = status?.replay;
  // pv_tsc 或后端 readonly 标记强制只读：既隐藏演示控件，也在 handler 层防御。
  const isTsc = slot === 'pv_tsc';
  const readOnly = status?.readonly === true;
  const effectiveWritable = writable && !isTsc && !readOnly;
  const guardedAdvance = () => { if (effectiveWritable) onAdvance?.(); };
  const guardedReset = () => { if (effectiveWritable) onReset?.(); };
  const guardedReplayStep = (points: 1 | 10 | 50) => { if (effectiveWritable) onReplayStep?.(points); };
  const guardedRebuildReplay = () => { if (effectiveWritable) onRebuildReplay?.(); };
  // @AI_GENERATED: end
  const reviewHref = acc?.review_id && slot
    ? `/iterative-labeling/review?review_id=${encodeURIComponent(acc.review_id)}&slot=${encodeURIComponent(slot)}`
    : (slot ? `/iterative-labeling?tab=pv_label&slot=${encodeURIComponent(slot)}` : '/iterative-labeling');
  return (
    <Alert
      type={status?.progress?.exhausted ? 'success' : 'info'}
      showIcon
      message={
        <Space wrap>
          {/* @AI_GENERATED: pv_tsc 用真实调度只读语义，不显示"演示 index/total"。 */}
          <Text strong>{day ? `当前业务日 ${day}` : (isTsc ? '尚未产出检测日' : '尚未喂入演示日')}</Text>
          {!isTsc && total != null ? <Tag>演示 {index}/{total}</Tag> : null}
          {isTsc ? <Tag color="purple">真实调度只读</Tag> : null}
          {/* @AI_GENERATED: end */}
          {status?.clock?.timestamp ? <Text type="secondary">{status.clock.timestamp}</Text> : null}
          {replay?.event_clock ? <Tag>事件时钟 {String(replay.event_clock).slice(0, 19)}</Tag> : null}
          {acc ? (
            <Tag color="blue">
              当日 Acc {pct(acc.classifier_accuracy)} · {acc.counted_units ?? 0} 条
            </Tag>
          ) : null}
          <Tag>未写入累计</Tag>
        </Space>
      }
      description={
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          {/* @AI_GENERATED: pv_tsc 描述走真实调度只读语义，不提"演示推进"。 */}
          <Text>
            {status?.note
              || (isTsc
                ? '时序分类检测由真实 pv_tsc_predict Challenger 调度推进：每日按设备日做多窗口 MultiRocket 分类 → 建 rev 会话 → 人工审核回流。本页只读，不提供演示推进。'
                : '调度推进下一天：喂 unlabeled → 检测 → 建 rev → 用真值自动审核 → 算精度。不写入累计账本。')}
            {acc?.review_id ? ` 会话 ${acc.review_id}` : ''}
          </Text>
          {/* @AI_GENERATED: end */}
          {slot === 'pv_point' && replay?.legacy ? (
            <Alert
              type="warning"
              showIcon
              message="当前 replay 仍是按设备整段走完的旧会话"
              description="日历会先铺满一台设备。点「重建交错会话」会取消旧会话，新会话按最早事件时间跨设备选点。正在跑的旧会话不会自动改。"
            />
          ) : null}
          {/* @AI_GENERATED: effectiveWritable 对 pv_tsc/只读强制为 false；handler 层另有 guard 防御。 */}
          {effectiveWritable ? (
            <Space wrap>
              {/* @AI_GENERATED */}
              <Switch
                checked={useRealModel}
                onChange={(v) => onUseRealModelChange?.(v)}
                checkedChildren="真实模型"
                unCheckedChildren="规则"
                style={{ marginRight: 4 }}
              />
              {/* @AI_GENERATED: end */}
              <Button type="primary" loading={advancing} disabled={Boolean(status?.progress?.exhausted)} onClick={guardedAdvance}>
                {status?.progress?.exhausted ? '演示 7 日已喂完' : '推进下一天（喂数+检测+自动审核）'}
              </Button>
              <Button onClick={guardedReset}>重置演示游标</Button>
              {slot === 'pv_point' && onReplayStep ? (
                <>
                  <Button loading={replayBusy} onClick={() => guardedReplayStep(1)}>推 1 点</Button>
                  <Button loading={replayBusy} onClick={() => guardedReplayStep(10)}>推 10 点</Button>
                  <Button loading={replayBusy} onClick={() => guardedReplayStep(50)}>推 50 点</Button>
                </>
              ) : null}
              {slot === 'pv_point' && replay?.legacy && onRebuildReplay ? (
                <Button danger loading={replayBusy} onClick={guardedRebuildReplay}>重建交错会话</Button>
              ) : null}
              <Link to={reviewHref}>
                <Button icon={<AuditOutlined />}>{acc?.review_id ? '打开当天审核' : '去审核工作台'}</Button>
              </Link>
            </Space>
          ) : (
            <Space wrap>
              <Text type="secondary">
                {isTsc || readOnly
                  ? '时序分类观测只读，检测由真实 pv_tsc_predict 调度推进，无演示推进/补检入口。'
                  : '精度运营只读。要推进水位请打开定时调度。'}
              </Text>
              <Link to={reviewHref}>
                <Button size="small" type="primary" icon={<AuditOutlined />}>
                  {acc?.review_id ? '打开当天审核' : '去审核工作台'}
                </Button>
              </Link>
            </Space>
          )}
          {/* @AI_GENERATED: end */}
        </Space>
      }
    />
  );
};

export default SlotOpsClockBar;
