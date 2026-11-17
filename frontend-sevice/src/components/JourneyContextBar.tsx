// @AI_GENERATED
/**
 * 平台旅程上下文栏：行业场景 › 算法方案 › 项目 › 诊断路径。
 *
 * 设计依据：design.md §33.3（解析优先级 URL → 页内选择 → store → 显式空态；绝不静默默认 slot）、
 * §11.3（就地切换清空下游）；requirements.md R1.1、R1.3–R1.5、R1.8、R1.9、R2.1、R2.8。
 *
 * 用法：放在页头下方，为跨模块页面提供一致的四层主干展示与逐段跳转 / 切换。
 * 段值优先取 URL（含别名兼容），缺失时回落到 journeyContextStore；两者都无则显示「未选择」。
 * 逐段点击导航到该层入口并携带已解析的上游主干；切换某段会清空其下游（store.switchLevel）。
 */

import { useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Space, Tag, Typography } from 'antd';
import { RightOutlined } from '@ant-design/icons';
import { buildJourneyHref, readSpine } from '../utils/journeyParams';
import type { JourneySpine } from '../utils/journeyParams';
import { useJourneyContextStore } from '../stores/journeyContextStore';
import type { SpineLevel } from '../stores/journeyContextStore';

const { Text } = Typography;

export interface JourneyContextBarProps {
  /** 可选：为各段提供人类可读名称（否则显示 id）。 */
  labels?: {
    scenario?: string;
    solution?: string;
    project?: string;
    slot?: string;
  };
  /** 是否显示项目段（非项目类页面可隐藏）。 */
  showProject?: boolean;
  /** 是否显示诊断路径段。 */
  showSlot?: boolean;
}

interface Segment {
  level: SpineLevel;
  label: string;
  value?: string;
  display?: string;
  href?: string;
}

export function JourneyContextBar({ labels, showProject = true, showSlot = true }: JourneyContextBarProps): JSX.Element {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const store = useJourneyContextStore();

  // §33.3：URL 优先，其次 store；不静默默认 slot。
  const spine = useMemo<JourneySpine>(() => {
    const fromUrl = readSpine(searchParams);
    return {
      scenarioId: fromUrl.scenarioId ?? store.scenarioId,
      solutionId: fromUrl.solutionId ?? store.solutionId,
      projectId: fromUrl.projectId ?? store.projectId,
      slot: fromUrl.slot ?? store.slot,
      workflowId: fromUrl.workflowId,
      datasetVersionId: fromUrl.datasetVersionId,
    };
  }, [searchParams, store.scenarioId, store.solutionId, store.projectId, store.slot]);

  const segments: Segment[] = [
    {
      level: 'scenario',
      label: '行业场景',
      value: spine.scenarioId,
      display: labels?.scenario || spine.scenarioId,
      href: spine.scenarioId ? `/industry/${encodeURIComponent(spine.scenarioId)}` : '/industry',
    },
    {
      level: 'solution',
      label: '算法方案',
      value: spine.solutionId,
      display: labels?.solution || spine.solutionId,
      href: buildJourneyHref('/algorithm-solutions', { scenarioId: spine.scenarioId, solutionId: spine.solutionId }),
    },
  ];
  if (showProject) {
    segments.push({
      level: 'project',
      label: '项目',
      value: spine.projectId,
      display: labels?.project || spine.projectId,
      href: spine.projectId ? `/projects/${encodeURIComponent(spine.projectId)}/overview` : '/projects',
    });
  }
  if (showSlot) {
    segments.push({
      level: 'slot',
      label: '诊断路径',
      value: spine.slot,
      display: labels?.slot || spine.slot,
    });
  }

  const handleSegmentClick = (seg: Segment) => {
    // 就地切换：跳转到该层入口并清空下游（§11.3）。slot 为页内维度，不跳转。
    if (seg.level === 'slot' || !seg.href) return;
    store.switchLevel(seg.level, seg.value);
    navigate(seg.href);
  };

  return (
    <div
      style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 6, padding: '6px 0' }}
      aria-label="旅程上下文：行业场景 算法方案 项目 诊断路径"
    >
      {segments.map((seg, idx) => (
        <Space key={seg.level} size={4} align="center">
          {idx > 0 && <RightOutlined style={{ fontSize: 10, color: '#bfbfbf' }} />}
          <Text type="secondary" style={{ fontSize: 12 }}>
            {seg.label}
          </Text>
          {seg.value ? (
            seg.level === 'slot' ? (
              <Tag color="orange" style={{ marginInlineEnd: 0 }}>{seg.display}</Tag>
            ) : (
              <a
                onClick={() => handleSegmentClick(seg)}
                style={{ cursor: 'pointer' }}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    handleSegmentClick(seg);
                  }
                }}
              >
                {seg.display}
              </a>
            )
          ) : (
            <Text type="secondary" style={{ fontSize: 12, color: '#bfbfbf' }}>
              未选择
            </Text>
          )}
        </Space>
      ))}
    </div>
  );
}

export default JourneyContextBar;

// @AI_GENERATED: end
