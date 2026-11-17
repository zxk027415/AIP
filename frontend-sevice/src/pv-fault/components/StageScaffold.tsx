// @AI_GENERATED
/**
 * 阶段页脚手架：为尚未实现的生命周期阶段提供诚实的「待实施」占位，
 * 同时作为后续任务填充真实内容的独立入口（design §2 红线：目标能力标注为待实施，不冒充已完成）。
 *
 * 每个阶段有自己的路由模块文件，避免多任务并行改同一页面（design §11.2 / tasks §2.1）。
 */

import type { ReactNode } from 'react';
import { Alert, Typography } from 'antd';
import { useProjectScope } from '../../contexts/ProjectScopeContext';

const { Title, Text } = Typography;

export interface StageScaffoldProps {
  /** 阶段标题，如「数据与兼容性」。 */
  title: string;
  /** 该阶段将实现什么（待实施说明）。 */
  pendingNote?: string;
  /** 对应实施任务编号，便于交接。 */
  plannedTask?: string;
  /** 真实内容（提供后不再显示待实施占位）。 */
  children?: ReactNode;
}

export function StageScaffold({ title, pendingNote, plannedTask, children }: StageScaffoldProps): JSX.Element {
  const { scope } = useProjectScope();
  return (
    <div style={{ padding: '4px 0' }}>
      <Title level={4} style={{ marginTop: 0 }}>
        {title}
      </Title>
      {children ?? (
        <Alert
          type="info"
          showIcon
          message={`${title} · 待实施`}
          description={
            <div>
              <div>{pendingNote || '该阶段将在后续实施任务中接入 scoped API 与共享组件。'}</div>
              {plannedTask && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  计划实施任务：{plannedTask}
                </Text>
              )}
              <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4 }}>
                当前项目 {scope.projectId || '—'}
                {scope.slot ? ` · 诊断路径 ${scope.slot}` : ''}
              </div>
            </div>
          }
        />
      )}
    </div>
  );
}

export default StageScaffold;

// @AI_GENERATED: end
