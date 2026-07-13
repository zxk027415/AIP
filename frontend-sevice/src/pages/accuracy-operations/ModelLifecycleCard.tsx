// @AI_GENERATED
/**
 * ModelLifecycleCard.tsx — 模型生命周期卡片
 *
 * 展示当前 slot 下所有模型版本及其形态（production / shadow / prelaunch / autoresearch）。
 * 数据来源：GET /accuracy-operations/models/lifecycle（经 accuracyOperationsStore.fetchLifecycle 拉取）。
 *
 * 相关 spec：.kiro/specs/accuracy-operations/
 *   - Requirements 10.2（生命周期视图展示）
 *   - Task 13.2
 */

import React, { useEffect } from 'react';
import { Card, Tag, Spin, Alert, Button, Empty } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useAccuracyOperationsStore } from '../../stores/accuracyOperationsStore';
import type { LifecycleNode } from '../../types/accuracy-operations';

// ===========================================================================
// Props
// ===========================================================================

interface ModelLifecycleCardProps {
  /** slot — 当前操作槽位名称（如 "default"） */
  slot: string;
}

// ===========================================================================
// 形态 → Tag 颜色映射
// ===========================================================================

/** getTagColor — 根据 model_form 返回 AntD Tag 颜色 */
function getTagColor(modelForm: string): string {
  switch (modelForm) {
    case 'production':
      return 'green';
    case 'shadow':
      return 'blue';
    case 'prelaunch':
      return 'orange';
    case 'autoresearch':
      return 'purple';
    default:
      return 'default';
  }
}

/** getFormLabel — 返回形态的中文显示标签 */
function getFormLabel(modelForm: string): string {
  switch (modelForm) {
    case 'production':
      return '生产';
    case 'shadow':
      return '影子';
    case 'prelaunch':
      return '预上线';
    case 'autoresearch':
      return 'AutoResearch';
    default:
      return modelForm;
  }
}

/** getStatusColor — 根据 node.status 返回状态 Tag 颜色 */
function getStatusColor(status: string): string {
  switch (status) {
    case 'active':
      return 'success';
    case 'retired':
      return 'default';
    case 'observing':
      return 'processing';
    default:
      return 'default';
  }
}

// ===========================================================================
// 组件
// ===========================================================================

/**
 * ModelLifecycleCard — 模型生命周期卡片组件
 *
 * 从 store 读取 lifecycle 数据，按 model_form 分组展示所有节点的
 * version_tag 和 status。
 */
const ModelLifecycleCard: React.FC<ModelLifecycleCardProps> = ({ slot }) => {
  const { lifecycle, loading, error, fetchLifecycle } = useAccuracyOperationsStore();

  // 挂载或 slot 变更时拉取数据
  useEffect(() => {
    fetchLifecycle(slot);
  }, [slot, fetchLifecycle]);

  // ---------- 加载态 ----------
  if (loading.lifecycle) {
    return (
      <Card title="模型生命周期" aria-label="模型生命周期卡片">
        <div style={{ textAlign: 'center', padding: '32px 0' }}>
          <Spin tip="加载中..." />
        </div>
      </Card>
    );
  }

  // ---------- 错误态 ----------
  if (error.lifecycle) {
    return (
      <Card title="模型生命周期" aria-label="模型生命周期卡片">
        <Alert
          type="error"
          message="加载失败"
          description={error.lifecycle}
          action={
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => fetchLifecycle(slot)}
            >
              重试
            </Button>
          }
        />
      </Card>
    );
  }

  // ---------- 空态 ----------
  if (!lifecycle || lifecycle.nodes.length === 0) {
    return (
      <Card title="模型生命周期" aria-label="模型生命周期卡片">
        <Empty description="暂无已注册模型" />
      </Card>
    );
  }

  // ---------- 正常态：按 model_form 分组展示 ----------
  const grouped = lifecycle.nodes.reduce<Record<string, LifecycleNode[]>>((acc, node) => {
    const key = node.model_form;
    if (!acc[key]) acc[key] = [];
    acc[key].push(node);
    return acc;
  }, {});

  // 固定展示顺序
  const formOrder = ['production', 'shadow', 'prelaunch', 'autoresearch'];
  const sortedKeys = [
    ...formOrder.filter((k) => grouped[k]),
    ...Object.keys(grouped).filter((k) => !formOrder.includes(k)),
  ];

  return (
    <Card title="模型生命周期" aria-label="模型生命周期卡片">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {sortedKeys.map((form) => (
          <div key={form} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', flexWrap: 'wrap' }}>
            {/* 形态标签（分组标题） */}
            <Tag color={getTagColor(form)} style={{ minWidth: '64px', textAlign: 'center' }}>
              {getFormLabel(form)}
            </Tag>
            {/* 该形态下所有节点 */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {grouped[form].map((node) => (
                <span
                  key={node.workflow_id}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                  title={`workflow_id: ${node.workflow_id}`}
                >
                  <Tag
                    color={getTagColor(node.model_form)}
                    aria-label={`${getFormLabel(node.model_form)} 版本 ${node.version_tag}`}
                  >
                    {node.version_tag}
                  </Tag>
                  <Tag color={getStatusColor(node.status)} style={{ fontSize: '11px' }}>
                    {node.status}
                  </Tag>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
};

export default ModelLifecycleCard;
// @AI_GENERATED: end
