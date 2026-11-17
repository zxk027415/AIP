// @AI_GENERATED
/**
 * 训练进度追踪器组件
 *
 * 使用 Ant Design Steps 展示四个训练步骤的状态，
 * 支持 waiting/running/completed/error 状态映射和耗时展示。
 */
import React from 'react';
import { Steps } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { TrainingStepInfo, TaskStatus } from '../../types/load-forecast';

export interface ProgressTrackerProps {
  steps: TrainingStepInfo[];
  currentStep: string | null;
  status: TaskStatus;
}

/** 将内部步骤状态映射为 Ant Design Steps 状态 */
function mapStepStatus(stepStatus: TrainingStepInfo['status']): 'wait' | 'process' | 'finish' | 'error' {
  switch (stepStatus) {
    case 'waiting':
      return 'wait';
    case 'running':
      return 'process';
    case 'completed':
      return 'finish';
    case 'error':
      return 'error';
    default:
      return 'wait';
  }
}

const ProgressTracker: React.FC<ProgressTrackerProps> = ({
  steps,
  currentStep,
  status,
}) => {
  const { t } = useTranslation();
  // 计算当前激活的步骤索引
  const currentIndex = steps.findIndex(
    (s) => s.status === 'running' || s.status === 'error'
  );

  const items = steps.map((step) => {
    const antStatus = mapStepStatus(step.status);
    const description =
      step.status === 'completed' && step.duration != null
        ? t('loadForecast.progress.durationSeconds', { seconds: step.duration.toFixed(1) })
        : step.status === 'running'
          ? t('loadForecast.progress.running')
          : undefined;

    return {
      title: step.label,
      status: antStatus as any,
      description,
      icon: step.status === 'running' ? <LoadingOutlined /> : undefined,
    };
  });

  return (
    <Steps
      current={currentIndex >= 0 ? currentIndex : undefined}
      items={items}
      size="small"
    />
  );
};

export default ProgressTracker;
// @AI_GENERATED: end
