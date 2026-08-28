/** G13.3 — legacy 只读说明条（pv_fault / TSC 等非新双路径产品槽）。 */
import React from 'react';
import { Alert } from 'antd';
import { HistoryOutlined } from '@ant-design/icons';

interface Props {
  slot: string;
  context?: 'accuracy-operations' | 'algorithm-deployment';
}

const LEGACY_SLOT_COPY: Record<string, { title: string; description: string }> = {
  pv_fault: {
    title: 'Legacy · pv_fault（TSC / 288 槽 / 双路径治理）',
    description:
      '本场景为历史光伏故障诊断链路，含 legacy_day / seq_annotation、Mock 喂数与日滚预测。'
      + '新产品天/点路径请使用 pv_day / pv_point；点路径日内告警走 replay_activity，不复用 TSC 账本。',
  },
  default: {
    title: 'Legacy · default 默认槽',
    description: '历史负荷预测/实验默认分区；正式产品请使用 load_forecast 或 pv_day / pv_point。',
  },
};

const LegacyReadOnlyBanner: React.FC<Props> = ({ slot, context = 'algorithm-deployment' }) => {
  const copy = LEGACY_SLOT_COPY[slot];
  if (!copy) return null;

  return (
    <Alert
      type="warning"
      showIcon
      icon={<HistoryOutlined />}
      message={copy.title}
      description={
        <>
          {copy.description}
          {context === 'accuracy-operations' ? ' 本页观测 legacy 运营证据，勿与 pv_point G12 告警混读。' : null}
        </>
      }
    />
  );
};

export default LegacyReadOnlyBanner;
