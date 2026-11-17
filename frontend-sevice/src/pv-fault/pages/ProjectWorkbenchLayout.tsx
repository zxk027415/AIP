// @AI_GENERATED
/**
 * 领域无关的项目工作台壳（design §11 / §11.1 / §11.5）。
 *
 * 布局四层：① 项目上下文栏 ② 生命周期阶段带 ③ 下一步条 ④ 内容区（Outlet）。
 * 所有领域语义来自 SolutionCapabilityAdapter；壳不含 `if (solution === 'pv_fault')` 分支。
 * scope 切换清空由 ProjectScopeContext 的 generation 承担（§11.3）。
 *
 * requirements.md R1.1–R1.12、R2.1–R2.13、R13.2–R13.4。
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { NavLink, Outlet, useLocation, useParams } from 'react-router-dom';
import { Skeleton, Space, Tag, Typography } from 'antd';
import { useProjectScope } from '../../contexts/ProjectScopeContext';
import JourneyContextBar from '../../components/JourneyContextBar';
import { ActionStateView } from '../components/ActionStateView';
import CommandPalette from '../components/CommandPalette';
import { getSolutionAdapter } from '../adapters';
import { useJourneyContextStore } from '../../stores/journeyContextStore';
import { pvProjectsApi } from '../../services/pvProjectsApi';
import type { ProjectOverview } from '../../services/pvProjectsApi';
import '../styles/workbench.css';

const { Title } = Typography;

/** 传给阶段子路由的上下文（避免各页重复拉取 overview）。 */
export interface WorkbenchOutletContext {
  overview: ProjectOverview | null;
  adapter: ReturnType<typeof getSolutionAdapter>;
}

export function ProjectWorkbenchLayout(): JSX.Element {
  const { projectId = '' } = useParams();
  const { generation, refresh } = useProjectScope();
  const location = useLocation();
  const setContext = useJourneyContextStore((s) => s.setContext);
  const pushRecent = useJourneyContextStore((s) => s.pushRecent);

  const [overview, setOverview] = useState<ProjectOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // 已成功加载过的项目 id；用于区分"首次加载该项目"（显示骨架）与"同项目 generation 刷新"
  // （保留旧内容 + 静默重取），避免 StrictMode / generation 突发导致的加载态抖动与骨架卡死。
  const loadedProjectRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    // 仅在切换到新项目（尚未成功加载过）时清空并显示骨架；同项目内刷新保留内容、静默重取。
    if (loadedProjectRef.current !== projectId) {
      setOverview(null);
      setLoading(true);
    }
    setError(null);
    pvProjectsApi
      .getOverview(projectId)
      .then((data) => {
        if (cancelled) return;
        loadedProjectRef.current = projectId;
        setOverview(data);
        // 记录旅程上下文（继续上次 / 最近列表）。
        setContext({
          scenarioId: data.scenario_id,
          solutionId: data.solution_id,
          projectId: data.project_id,
          lastHref: location.pathname,
        });
        pushRecent({
          kind: 'project',
          id: data.project_id,
          label: data.project_name || data.project_id,
          href: `/projects/${data.project_id}/overview`,
          scenarioId: data.scenario_id,
          solutionId: data.solution_id,
          projectId: data.project_id,
        });
      })
      .catch(() => {
        if (!cancelled) setError('项目总览读取失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // generation：scope 变化即重取，丢弃旧上下文。
  }, [projectId, generation]);

  const adapter = useMemo(() => getSolutionAdapter(overview?.solution_id), [overview?.solution_id]);

  const activeSegment = useMemo(() => {
    const rest = location.pathname.replace(`/projects/${projectId}`, '').replace(/^\//, '');
    return rest.split('/')[0] || 'overview';
  }, [location.pathname, projectId]);

  if (loading) {
    return (
      <div style={{ padding: 24 }} role="status" aria-live="polite" aria-busy="true">
        <span className="pvwb-sr-only">正在加载项目工作台，请稍候</span>
        <Skeleton active paragraph={{ rows: 2 }} />
        <Skeleton active paragraph={{ rows: 4 }} style={{ marginTop: 16 }} />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: 24 }}>
        <ActionStateView
          descriptor={{
            state: 'recoverable_failure',
            title: '项目工作台加载失败',
            reason: error,
            nextAction: '刷新当前项目后重试',
            scope: { projectId },
          }}
          onRefresh={refresh}
        />
      </div>
    );
  }

  return (
    <div className="pvwb-shell">
      {/* 小屏提示：复杂操作改用桌面端（默认隐藏，仅 <768 显示；不隐藏 scope/阻断/风险文本） */}
      <div className="pvwb-desktop-hint" role="note">
        当前为小屏视图，画布 / 字段映射 / 治理等复杂操作建议改用桌面端完成；状态与关键详情仍可查看。
      </div>

      {/* ① 项目上下文栏 */}
      <div style={{ marginBottom: 20 }}>
        <Space align="center" wrap style={{ marginBottom: 4 }}>
          <Title level={3} style={{ margin: 0 }}>
            {overview?.project_name || projectId}
          </Title>
          {overview?.read_only && <Tag color="default">历史只读</Tag>}
        </Space>
        <JourneyContextBar
          labels={{ scenario: overview?.scenario_id, solution: adapter?.displayName || overview?.solution_id }}
        />
      </div>

      {/* 未注册适配器：领域无关兜底，不回落到光伏配置也不崩溃 */}
      {!adapter ? (
        <ActionStateView
          descriptor={{
            state: 'blocked',
            disabledReason: 'business_gate_blocked',
            title: '该解决方案尚未接入工作台',
            reason: `解决方案 ${overview?.solution_id || '（未设置）'} 尚未注册能力适配器，无法渲染其生命周期。`,
            nextAction: '为该项目设置一个已接入的算法方案，或注册对应领域适配器',
            scope: { projectId },
          }}
        />
      ) : (
        <>
          {/* ② 生命周期阶段带（横向；窄屏横向滚动，见 workbench.css） */}
          <div
            className="pvwb-stage-band"
            style={{
              borderBottom: '1px solid #f0f0f0',
              paddingBottom: 10,
              marginBottom: 28,
            }}
            role="navigation"
            aria-label="生命周期阶段"
          >
            <NavLink
              to={`/projects/${projectId}/overview`}
              style={{
                fontWeight: activeSegment === 'overview' ? 600 : 400,
                color: activeSegment === 'overview' ? '#fa8c16' : '#595959',
              }}
            >
              数据集与路径
            </NavLink>
            {adapter.lifecycleStages.map((stage) => (
              <NavLink
                key={stage.key}
                to={`/projects/${projectId}/${stage.routeSegment}`}
                style={{
                  fontWeight: activeSegment === stage.routeSegment ? 600 : 400,
                  color: activeSegment === stage.routeSegment ? '#fa8c16' : '#595959',
                }}
              >
                {stage.label}
              </NavLink>
            ))}
            {/* 非线性阶段直达入口，避免运行中心 / 跨数据集复验成为死角（可达性，10.6） */}
            {[
              { seg: 'runs', label: '运行中心' },
              { seg: 'validations', label: '跨数据集复验' },
            ].map((extra) => (
              <NavLink
                key={extra.seg}
                to={`/projects/${projectId}/${extra.seg}`}
                style={{
                  fontWeight: activeSegment === extra.seg ? 600 : 400,
                  color: activeSegment === extra.seg ? '#fa8c16' : '#8c8c8c',
                }}
              >
                {extra.label}
              </NavLink>
            ))}
          </div>

          {/* 命令面板（Ctrl/Cmd+K）：当前项目阶段 + 最近访问快速跳转 */}
          <CommandPalette
            projectId={projectId}
            stages={[
              { label: '数据集与路径', segment: 'overview' },
              ...adapter.lifecycleStages.map((s) => ({ label: s.label, segment: s.routeSegment })),
            ]}
          />

          {/* ③ 下一步条 + ④ 内容区（各阶段页面自渲染下一步与内容） */}
          <Outlet context={{ overview, adapter } satisfies WorkbenchOutletContext} />
        </>
      )}

    </div>
  );
}

export default ProjectWorkbenchLayout;

// @AI_GENERATED: end
