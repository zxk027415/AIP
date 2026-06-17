// @AI_GENERATED: Kiro v1.0
/**
 * 智能编排历史总览页面
 * 按行业场景分组展示，使用 Collapse 折叠面板 + 卡片展示算法模板核心属性
 */
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Card, Button, Tag, Space, Typography, Empty, Popconfirm, Collapse, Row, Col, Progress,
} from 'antd';
import {
  RocketOutlined, DeleteOutlined, ArrowLeftOutlined, ReloadOutlined,
  NodeIndexOutlined, BranchesOutlined, CheckCircleOutlined,
  ClockCircleOutlined, ExperimentOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useWorkflowAgentStore } from '../stores/workflowAgentStore';
import type { AgentSession } from '../stores/workflowAgentStore';

const { Text, Title } = Typography;

// @AI_GENERATED
const stepLabel = (step: string, t: (key: string) => string) => {
  const map: Record<string, string> = {
    input: t('workflowAgentHistory.stepInput'), matching: t('workflowAgentHistory.stepMatching'), 'select-template': t('workflowAgentHistory.stepSelectTemplate'),
    composing: t('workflowAgentHistory.stepComposing'), generating: t('workflowAgentHistory.stepGenerating'), validating: t('workflowAgentHistory.stepValidating'), done: t('workflowAgentHistory.stepDone'),
  };
  return map[step] || step;
};

const profileLabel = (profile: string, t: (key: string) => string) => {
  if (profile === 'high-accuracy') return t('workflowAgentHistory.highAccuracy');
  if (profile === 'balanced') return t('workflowAgentHistory.balanced');
  return t('workflowAgentHistory.lowLatency');
};
// @AI_GENERATED: end

const profileColor = (profile: string) => {
  if (profile === 'high-accuracy') return 'green';
  if (profile === 'balanced') return 'blue';
  return 'orange';
};

/** 按场景分组历史记录 */
function groupByScenario(sessions: AgentSession[]) {
  const groups: Record<string, { scenarioName: string; sessions: AgentSession[] }> = {};
  const ungrouped: AgentSession[] = [];

  for (const s of sessions) {
    if (s.selectedScenario) {
      const key = s.selectedScenario.scenario_id;
      if (!groups[key]) {
        groups[key] = { scenarioName: s.selectedScenario.scenario_name, sessions: [] };
      }
      groups[key].sessions.push(s);
    } else {
      ungrouped.push(s);
    }
  }
  return { groups, ungrouped };
}

const SessionCard: React.FC<{
  session: AgentSession;
  onRestore: (s: AgentSession) => void;
  onDelete: (id: string) => void;
}> = ({ session, onRestore, onDelete }) => {
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const wf = session.generatedWorkflow;
  const vr = session.validationResult;
  const combo = session.selectedCombo;

  return (
    <Card
      size="small"
      style={{ marginBottom: 10 }}
      title={
        <Space>
          <Text strong style={{ fontSize: 13 }}>{session.description || t('workflowAgentHistory.unnamed')}</Text>
          <Tag color={session.step === 'done' ? 'green' : 'blue'}>{stepLabel(session.step, t)}</Tag>
        </Space>
      }
      extra={
        <Space>
          <Button type="primary" size="small" icon={<ReloadOutlined />} onClick={() => onRestore(session)}>{t('workflowAgentHistory.restore')}</Button>
          <Popconfirm title={t('workflowAgentHistory.confirmDelete')} onConfirm={() => onDelete(session.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      }
    >
      <Row gutter={[16, 8]}>
        {/* 模板 */}
        {session.selectedTemplate && (
          <Col span={12}>
            <Space size={4}>
              <ExperimentOutlined style={{ color: '#722ed1' }} />
              <Text type="secondary" style={{ fontSize: 12 }}>{t('workflowAgentHistory.templateLabel')}：</Text>
              <Text style={{ fontSize: 12 }}>{session.selectedTemplate.name}</Text>
            </Space>
          </Col>
        )}
        {/* 方案 */}
        {combo && (
          <Col span={12}>
            <Space size={4}>
              <BranchesOutlined style={{ color: '#1890ff' }} />
              <Text type="secondary" style={{ fontSize: 12 }}>{t('workflowAgentHistory.solutionLabel')}：</Text>
              <Tag color={profileColor(combo.profile)} style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>
                {profileLabel(combo.profile, t)}
              </Tag>
              <Text style={{ fontSize: 12 }}>{t('workflowAgentHistory.confidence')} {combo.overall_confidence}%</Text>
            </Space>
          </Col>
        )}
        {/* 节点/连接 */}
        {wf && (
          <Col span={12}>
            <Space size={4}>
              <NodeIndexOutlined style={{ color: '#1890ff' }} />
              <Tag color="blue" style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>{t('workflowAgentHistory.nodes')}: {wf.node_count}</Tag>
              <Tag color="green" style={{ fontSize: 11, lineHeight: '18px', padding: '0 4px' }}>{t('workflowAgentHistory.connections')}: {wf.edge_count}</Tag>
              {wf.processing_time_ms && (
                <Text type="secondary" style={{ fontSize: 11 }}>{t('workflowAgentHistory.duration')} {wf.processing_time_ms}ms</Text>
              )}
            </Space>
          </Col>
        )}
        {/* 就绪度 */}
        {vr && (
          <Col span={12}>
            <Space size={4} align="center">
              <CheckCircleOutlined style={{ color: vr.readiness_score >= 80 ? '#52c41a' : '#faad14' }} />
              <Text type="secondary" style={{ fontSize: 12 }}>{t('workflowAgentHistory.readiness')}：</Text>
              <Progress
                percent={vr.readiness_score}
                size="small"
                style={{ width: 100, margin: 0 }}
                status={vr.readiness_score >= 80 ? 'success' : vr.readiness_score >= 50 ? 'normal' : 'exception'}
              />
            </Space>
          </Col>
        )}
        {/* 时间 */}
        <Col span={24}>
          <Space size={4}>
            <ClockCircleOutlined style={{ color: '#999' }} />
            <Text type="secondary" style={{ fontSize: 11 }}>
              {new Date(session.createdAt).toLocaleString()}
            </Text>
          </Space>
        </Col>
      </Row>
    </Card>
  );
};

const WorkflowAgentHistoryPage: React.FC = () => {
  const navigate = useNavigate();
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const { history, restoreFromHistory, deleteHistory } = useWorkflowAgentStore();

  const handleRestore = (session: AgentSession) => {
    restoreFromHistory(session.id);
    navigate('/workflow-agent');
  };

  const { groups, ungrouped } = useMemo(() => groupByScenario(history), [history]);

  const collapseItems = useMemo(() => {
    const items: { key: string; label: React.ReactNode; children: React.ReactNode }[] = [];

    // 按场景分组
    for (const [scenarioId, group] of Object.entries(groups)) {
      items.push({
        key: scenarioId,
        label: (
          <Space>
            <Text strong style={{ fontSize: 14 }}>{group.scenarioName}</Text>
            <Tag color="blue">{group.sessions.length} {t('workflowAgentHistory.records')}</Tag>
          </Space>
        ),
        children: (
          <div>
            {group.sessions.map((s) => (
              <SessionCard key={s.id} session={s} onRestore={handleRestore} onDelete={deleteHistory} />
            ))}
          </div>
        ),
      });
    }

    // 未分组（无场景的记录）
    if (ungrouped.length > 0) {
      items.push({
        key: '__ungrouped__',
        label: (
          <Space>
            <Text strong style={{ fontSize: 14 }}>{t('workflowAgentHistory.uncategorized')}</Text>
            <Tag>{ungrouped.length} {t('workflowAgentHistory.records')}</Tag>
          </Space>
        ),
        children: (
          <div>
            {ungrouped.map((s) => (
              <SessionCard key={s.id} session={s} onRestore={handleRestore} onDelete={deleteHistory} />
            ))}
          </div>
        ),
      });
    }

    return items;
  }, [groups, ungrouped, handleRestore, deleteHistory]);

  // 默认展开所有场景
  const defaultActiveKeys = useMemo(
    () => {
      const keys = [...Object.keys(groups), ...(ungrouped.length > 0 ? ['__ungrouped__'] : [])];
      // 首屏仅展开第一个分组，避免大量历史记录同时渲染导致切页卡顿
      return keys.slice(0, 1);
    },
    [groups, ungrouped],
  );

  return (
    <div style={{ padding: 24, maxWidth: 960, margin: '0 auto' }}>
      <Space style={{ marginBottom: 20 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/workflow-agent')}>{t('workflowAgentHistory.backToOrchestration')}</Button>
        <Title level={4} style={{ margin: 0 }}><RocketOutlined /> {t('workflowAgentHistory.title')}</Title>
        <Text type="secondary" style={{ fontSize: 13 }}>{t('workflowAgentHistory.totalRecords', { count: history.length })}</Text>
      </Space>

      {history.length === 0 ? (
        <Empty description={t('workflowAgentHistory.noHistory')} style={{ marginTop: 60 }}>
          <Button type="primary" onClick={() => navigate('/workflow-agent')}>{t('workflowAgentHistory.startNew')}</Button>
        </Empty>
      ) : (
        <Collapse
          items={collapseItems}
          defaultActiveKey={defaultActiveKeys}
          size="small"
          style={{ background: '#fafafa' }}
        />
      )}
    </div>
  );
};

export default WorkflowAgentHistoryPage;
// @AI_GENERATED: end
