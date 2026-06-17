// @AI_GENERATED: Kiro v1.0
/**
 * Algorithm Agent 对话页面
 * 支持四种专业 Agent：Curator、Sandbox、Onboarding、Operation Master
 * 设计参考 DeepSeek Chat
 */
import { useState, useRef, useEffect } from 'react';
// @AI_GENERATED
import { useTranslation } from 'react-i18next';
// @AI_GENERATED: end
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Layout, Input, Button, Tag, Space, Typography, Spin,
  message, Tooltip, Empty, Collapse, Switch,
} from 'antd';
import {
  SendOutlined, RobotOutlined, PlusOutlined,
  BulbOutlined, ThunderboltOutlined,
  SearchOutlined, ExperimentOutlined, CloudUploadOutlined, SettingOutlined,
  DeleteOutlined, MenuFoldOutlined, MenuUnfoldOutlined,
  MoreOutlined, ApiOutlined, CheckCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAlgorithmAgentStore } from '../stores/algorithmAgentStore';
import algorithmAgentApi from '../services/algorithmAgentApi';
import type {
  AgentMessage, AgentType, SuggestedAction, LLMStatus,
  OperationObservability,
} from '../types/algorithm-agent';
// @AI_GENERATED
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const { Sider, Content } = Layout;
const { TextArea } = Input;
const { Text } = Typography;

// @AI_GENERATED: Kiro v1.0
// Agent 类型配置
const AGENT_CONFIGS: Record<AgentType, {
  name: string;
  englishName: string;
  description: string;
  icon: React.ReactNode;
  color: string;
  gradient: string;
  capabilities: string[];
  quickCommandIds: readonly string[];
}> = {
  curator: {
    name: '算法策划',
    englishName: 'Curator Agent',
    description: '基于场景关联搜索AI解决方案库、算法模板和数据集需求',
    icon: <SearchOutlined />,
    color: '#4f46e5',
    gradient: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
    capabilities: [
      '搜索AI解决方案库',
      '匹配算法模板',
      '分析数据集需求',
      '推荐最佳方案',
    ],
    quickCommandIds: [
      'searchSolutions',
      'recommendTemplates',
      'analyzeData',
      'compareSolutions',
      'scenarioMatch',
      'browseLibrary',
    ],
  },
  sandbox: {
    name: '算法回测',
    englishName: 'Sandbox Agent',
    description: '引导挂载数据集，自动适配算法模板并运行，给出精度评估',
    icon: <ExperimentOutlined />,
    color: '#059669',
    gradient: 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
    capabilities: [
      '引导数据集挂载',
      '自动适配算法模板',
      '执行模型训练',
      '评估训练和验证精度',
    ],
    quickCommandIds: [
      'mountDataset',
      'adaptAlgo',
      'startTrain',
      'viewMetrics',
      'tuneParams',
      'compareRuns',
    ],
  },
  onboarding: {
    name: '算法上线',
    englishName: 'Onboarding Agent',
    description: '将训练好的算法服务上线，支持定期训练和推理服务',
    icon: <CloudUploadOutlined />,
    color: '#d97706',
    gradient: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
    capabilities: [
      '算法服务上线',
      '配置定期训练',
      '部署推理服务',
      '监控服务状态',
    ],
    quickCommandIds: [
      'deployService',
      'scheduleRetrain',
      'deployApi',
      'serviceStatus',
      'versioning',
      'resources',
    ],
  },
  operation: {
    name: '算法运营',
    englishName: 'Operation Master',
    description: '精度漂移检测、根因分析、自动选择模型和重训调优',
    icon: <SettingOutlined />,
    color: '#dc2626',
    gradient: 'linear-gradient(135deg, #dc2626 0%, #ef4444 100%)',
    capabilities: [
      '精度漂移检测',
      '根因分析',
      '自动模型选择',
      '重训和调优',
    ],
    quickCommandIds: ['drift', 'rootCause', 'autoRetrain', 'tuneModel', 'abTest', 'weeklyReport'],
  },
};
// @AI_GENERATED: end

function getWelcomeMessage(agentType: AgentType, t: (key: string, options?: any) => string): string {
  return t(`algorithmAgent.welcome.${agentType}`);
}

// @AI_GENERATED: Kiro v1.0
const markdownStyles = `
  .markdown-content {
    font-size: 15px;
    line-height: 1.7;
    color: #1f2937;
  }
  .markdown-content p {
    margin: 0 0 12px 0;
  }
  .markdown-content p:last-child {
    margin-bottom: 0;
  }
  .markdown-content strong {
    font-weight: 600;
  }
  .markdown-content ul, .markdown-content ol {
    margin: 8px 0;
    padding-left: 20px;
  }
  .markdown-content li {
    margin: 4px 0;
  }
  .markdown-content .table-wrapper {
    width: 100%;
    max-width: 100%;
    overflow-x: auto;
    margin: 16px 0;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
  }
  .markdown-content table {
    border-collapse: collapse;
    font-size: 13px;
    white-space: nowrap;
    min-width: 100%;
    margin: 0;
  }
  .markdown-content th, .markdown-content td {
    border: 1px solid #e5e7eb;
    padding: 8px 12px;
    text-align: left;
  }
  .markdown-content th:first-child, .markdown-content td:first-child {
    border-left: none;
  }
  .markdown-content th:last-child, .markdown-content td:last-child {
    border-right: none;
  }
  .markdown-content tr:first-child th {
    border-top: none;
  }
  .markdown-content tr:last-child td {
    border-bottom: none;
  }
  .markdown-content th {
    background: #f9fafb;
    font-weight: 600;
    color: #374151;
    position: sticky;
    top: 0;
  }
  .markdown-content tr:nth-child(even) {
    background: #f9fafb;
  }
  .markdown-content tr:hover {
    background: #f3f4f6;
  }
  .markdown-content code {
    background: #f3f4f6;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 13px;
    font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  }
  .markdown-content pre {
    background: #1f2937;
    color: #f9fafb;
    padding: 16px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 12px 0;
  }
  .markdown-content pre code {
    background: transparent;
    padding: 0;
    color: inherit;
  }
  .final-summary-block {
    margin-top: 14px;
    padding: 12px 14px;
    border-radius: 10px;
    border: 1px solid #fecaca;
    background: #fef2f2;
  }
  .final-summary-block .markdown-content {
    color: #7f1d1d;
  }
  .final-summary-block .markdown-content h2,
  .final-summary-block .markdown-content h3 {
    color: #b91c1c;
    margin-top: 0;
    margin-bottom: 8px;
  }
  .final-summary-block .markdown-content code {
    background: #fee2e2;
  }
`;

// 自定义渲染器，为表格添加包装器
const MarkdownComponents = {
  table: ({ children, ...props }: any) => (
    <div className="table-wrapper">
      <table {...props}>{children}</table>
    </div>
  ),
};
// @AI_GENERATED: end

function splitFinalSummarySection(content: string): Array<{ text: string; highlighted: boolean }> {
  const re = /(#### 最终输出（[^）]+）[\s\S]*?)(?=\n#### 最终输出（|\n### |\n## |\s*$)/g;
  const blocks: Array<{ text: string; highlighted: boolean }> = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(content)) !== null) {
    const start = m.index;
    const end = re.lastIndex;
    if (start > last) {
      const normal = content.slice(last, start).trim();
      if (normal) blocks.push({ text: normal, highlighted: false });
    }
    const highlighted = content.slice(start, end).trim();
    if (highlighted) blocks.push({ text: highlighted, highlighted: true });
    last = end;
  }
  if (last < content.length) {
    const tail = content.slice(last).trim();
    if (tail) blocks.push({ text: tail, highlighted: false });
  }
  if (blocks.length === 0) {
    blocks.push({ text: content, highlighted: false });
  }
  return blocks;
}

/** 运营 Agent：模型在 agent_thinking 段中的自然语言推理过程（非工具参数列表） */
const ModelReasoningPanel: React.FC<{
  content: string;
  /** 在正文到达前，展示等待/进度文案 */
  progressMessage?: string | null;
}> = ({ content, progressMessage }) => {
  const { t } = useTranslation();
  if (!content?.trim() && !progressMessage) return null;
  return (
    <Collapse
      defaultActiveKey={['r']}
      ghost
      size="small"
      style={{ marginBottom: 12, width: '100%', background: '#f8fafc', borderRadius: 8, border: '1px solid #e2e8f0' }}
      items={[
        {
          key: 'r',
          label: (
            <Text style={{ fontSize: 13, color: '#334155' }}>
              💭 {t('algorithmAgent.modelReasoningTitle')}
            </Text>
          ),
          children: (
            <div style={{ maxHeight: 320, overflow: 'auto' }}>
              {!!progressMessage && !content && (
                <div style={{ fontSize: 13, color: '#64748b' }}>
                  <Spin size="small" style={{ marginRight: 8 }} />
                  {progressMessage}
                </div>
              )}
              {!!content?.trim() && (
                <div className="markdown-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
                    {content}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          ),
        },
      ]}
    />
  );
};

const formatScore = (v?: number): string => {
  if (typeof v !== 'number' || Number.isNaN(v)) return '-';
  return v.toFixed(2);
};

const OperationObservabilityPanel: React.FC<{ trace?: OperationObservability }> = ({ trace }) => {
  if (!trace) return null;
  const pre = trace.preloading;
  const routing = trace.routing;
  const execution = trace.execution;
  const ranked = routing?.ranked || [];
  const stages = execution?.stages || [];
  const sectionCardStyle: React.CSSProperties = {
    marginTop: 8,
    padding: '8px 10px',
    background: '#fffbeb',
    border: '1px solid #fde68a',
    borderRadius: 8,
  };
  const renderSimpleList = (title: string, items?: string[]) => {
    if (!Array.isArray(items) || items.length === 0) return null;
    return (
      <div style={sectionCardStyle}>
        <Text strong>{title}</Text>
        <div style={{ marginTop: 4 }}>
          {items.slice(0, 4).map((x, i) => (
            <div key={`${title}-${i}`}>- {x}</div>
          ))}
        </div>
      </div>
    );
  };
  const renderStageDetails = (stage: NonNullable<OperationObservability['execution']>['stages'][number]) => {
    const details = stage?.details as Record<string, any> | undefined;
    if (!details) return null;
    if (stage.agent === 'drift') {
      const report = (details.detailed_report || {}) as Record<string, any>;
      const evidence = Array.isArray(report.key_evidence) ? report.key_evidence : [];
      const immediate = Array.isArray(report.action_plan?.immediate) ? report.action_plan.immediate : [];
      return (
        <div style={{ marginTop: 6, color: '#92400e' }}>
          <div>风险={details.risk_level || '-'}；建议={details.recommendation || '-'}</div>
          {!!report.executive_summary && (
            <div style={sectionCardStyle}>
              <Text strong>结论</Text>
              <div style={{ marginTop: 4 }}>{report.executive_summary}</div>
            </div>
          )}
          {renderSimpleList('关键证据', evidence)}
          {renderSimpleList('建议动作（立即）', immediate)}
        </div>
      );
    }
    if (stage.agent === 'root_cause') {
      const top = Array.isArray(details.top_root_causes) ? details.top_root_causes : [];
      const checklist = (details.checklist || {}) as Record<string, any>;
      const abnormalCount = Object.values(checklist).filter((x: any) => x?.status === 'abnormal').length;
      const report = (details.detailed_report || {}) as Record<string, any>;
      const evidence = Array.isArray(report.key_evidence) ? report.key_evidence : [];
      const immediate = Array.isArray(report.action_plan?.immediate)
        ? report.action_plan.immediate.map((x: any) => `${x?.action || '-'}（预期=${x?.expected_improvement || '-'}）`)
        : [];
      const next = Array.isArray(report.action_plan?.next)
        ? report.action_plan.next.map((x: any) => `${x?.action || '-'}（预期=${x?.expected_improvement || '-'}）`)
        : [];
      return (
        <div style={{ marginTop: 6, color: '#92400e' }}>
          <div>异常检查项={abnormalCount}；Top根因={top.length}</div>
          {!!report.executive_summary && (
            <div style={sectionCardStyle}>
              <Text strong>结论</Text>
              <div style={{ marginTop: 4 }}>{report.executive_summary}</div>
            </div>
          )}
          {renderSimpleList('关键证据', evidence)}
          {renderSimpleList('建议动作（立即）', immediate)}
          {renderSimpleList('建议动作（下一步）', next)}
        </div>
      );
    }
    if (stage.agent === 'retrain') {
      const policy = details.new_retrain_policy as Record<string, any> | undefined;
      const event = (policy?.event_trigger || {}) as Record<string, any>;
      const report = (details.detailed_report || {}) as Record<string, any>;
      const reason = Array.isArray(details.policy_reasoning) ? details.policy_reasoning : [];
      return (
        <div style={{ marginTop: 6, color: '#92400e' }}>
          <div>策略={policy?.schedule_mode || '-'}；连续下降触发={event.consecutive_drop_days ?? '-'}天</div>
          <div>漂移引用：{String(details.drift_used ?? false)}</div>
          <div>回测触发：{String(details.backtest_triggered ?? false)}</div>
          {!!details.backtest_result?.summary && <div>回测结果：{String(details.backtest_result.summary)}</div>}
          {!!report.executive_summary && (
            <div style={sectionCardStyle}>
              <Text strong>结论</Text>
              <div style={{ marginTop: 4 }}>{report.executive_summary}</div>
            </div>
          )}
          {renderSimpleList('决策依据', reason)}
        </div>
      );
    }
    if (stage.agent === 'tuning') {
      const plan = details.tuning_plan as Record<string, any> | undefined;
      const report = (details.detailed_report || {}) as Record<string, any>;
      const rationale = Array.isArray(details.tuning_rationale) ? details.tuning_rationale : [];
      const cand = Array.isArray(details.candidate_priority)
        ? details.candidate_priority.map((x: any) => `Rank${x?.rank || '-'}: ${x?.action || '-'} | ${x?.reason || '-'}`)
        : [];
      return (
        <div style={{ marginTop: 6, color: '#92400e' }}>
          <div>trials={plan?.n_trials ?? '-'}，cv={plan?.cv_folds ?? '-'}，triggered={String(plan?.triggered ?? false)}</div>
          <div>漂移引用：{String(details.drift_used ?? false)}</div>
          <div>回测触发：{String(details.backtest_triggered ?? false)}</div>
          {!!details.backtest_result?.summary && <div>回测结果：{String(details.backtest_result.summary)}</div>}
          {!!report.executive_summary && (
            <div style={sectionCardStyle}>
              <Text strong>结论</Text>
              <div style={{ marginTop: 4 }}>{report.executive_summary}</div>
            </div>
          )}
          {renderSimpleList('决策依据', rationale)}
          {renderSimpleList('候选优先级', cand)}
        </div>
      );
    }
    return null;
  };
  return (
    <Collapse
      defaultActiveKey={['obs']}
      ghost
      size="small"
      style={{ marginBottom: 12, width: '100%', background: '#fff7ed', borderRadius: 8, border: '1px solid #fed7aa' }}
      items={[
        {
          key: 'obs',
          label: (
            <Text style={{ fontSize: 13, color: '#9a3412' }}>
              🔎 运营阶段可观测
            </Text>
          ),
          children: (
            <div style={{ fontSize: 13, color: '#7c2d12', display: 'grid', gap: 10 }}>
              <div>
                <Text strong>预读取</Text>
                <div style={{ marginTop: 4 }}>
                  模板：{pre?.template_found ? '已命中' : '未命中'}，workflow_id：{pre?.workflow_id || '-'}
                  {pre?.workflow_id_source ? `（来源：${pre.workflow_id_source}）` : ''}，
                  节点/连线：{pre?.node_count ?? 0}/{pre?.edge_count ?? 0}
                </div>
                {!!pre?.operator_ids?.length && (
                  <div style={{ marginTop: 4 }}>
                    算子：{pre.operator_ids.slice(0, 8).join(', ')}
                    {pre.operator_ids.length > 8 ? ' ...' : ''}
                  </div>
                )}
                {pre?.operator_param_keys && Object.keys(pre.operator_param_keys).length > 0 && (
                  <div style={{ marginTop: 4 }}>
                    参数预读：
                    {Object.entries(pre.operator_param_keys)
                      .slice(0, 2)
                      .map(([op, keys]) => `${op}[${(keys || []).slice(0, 4).join(',')}]`)
                      .join(' | ')}
                  </div>
                )}
                {!!pre?.template_error && <div style={{ marginTop: 4, color: '#b91c1c' }}>模板错误：{pre.template_error}</div>}
              </div>
              <div>
                <Text strong>路由打分</Text>
                {ranked.length > 0 ? (
                  <div style={{ marginTop: 4 }}>
                    {ranked.slice(0, 4).map(([name, score]) => (
                      <Tag key={name} style={{ marginBottom: 4 }}>
                        {name}: {formatScore(score)}
                      </Tag>
                    ))}
                  </div>
                ) : (
                  <div style={{ marginTop: 4 }}>暂无路由结果</div>
                )}
                {!!routing?.execution_plan?.length && (
                  <div style={{ marginTop: 4 }}>
                    执行计划：<Text code>{routing.execution_plan.join(' -> ')}</Text>
                  </div>
                )}
              </div>
              <div>
                <Text strong>子Agent执行</Text>
                {stages.length > 0 ? (
                  <div style={{ marginTop: 4 }}>
                    {stages.map((stage) => (
                      <div key={stage.agent} style={{ marginBottom: 4 }}>
                        <Tag color={stage.status === 'success' ? 'green' : 'red'}>{stage.agent}</Tag>
                        {stage.summary || (stage.status === 'success' ? '已完成' : '失败')}
                        {renderStageDetails(stage as any)}
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ marginTop: 4 }}>暂无执行结果</div>
                )}
              </div>
            </div>
          ),
        },
      ]}
    />
  );
};

function getTemplateTypeLabel(templateType: 'workflow' | 'skill', t: (key: string, options?: any) => string): string {
  return templateType === 'workflow' ? t('algorithmAgent.workflowTemplate') : 'Skill';
}

// @AI_GENERATED: Kiro v1.0
const MessageBubble: React.FC<{ msg: AgentMessage; agentType: AgentType }> = ({ msg, agentType }) => {
  const isUser = msg.role === 'user';
  const agentConfig = AGENT_CONFIGS[agentType];
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  
  const contentParts = !isUser ? splitFinalSummarySection(msg.content || '') : [{ text: msg.content || '', highlighted: false }];

  return (
    <div style={{ 
      marginBottom: 24, 
      display: 'flex', 
      flexDirection: 'column',
      alignItems: isUser ? 'flex-end' : 'flex-start',
    }}>
      <style>{markdownStyles}</style>
      {!isUser && (
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          marginBottom: 8,
          gap: 8,
        }}>
          <div style={{
            width: 24,
            height: 24,
            borderRadius: 6,
            background: agentConfig.gradient,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <RobotOutlined style={{ color: '#fff', fontSize: 14 }} />
          </div>
          <Text style={{ fontSize: 14, color: '#1f2937', fontWeight: 500 }}>{agentConfig.englishName}</Text>
        </div>
      )}
      <div style={{
        maxWidth: isUser ? '70%' : '100%',
        padding: isUser ? '10px 16px' : '0',
        borderRadius: isUser ? 20 : 0,
        background: isUser ? '#f3f4f6' : 'transparent',
        color: '#1f2937',
        wordBreak: 'break-word',
      }}>
        {isUser ? (
          <span style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</span>
        ) : (
          <>
            {!!msg.reasoningContent?.trim() && (
              <ModelReasoningPanel content={msg.reasoningContent} />
            )}
            {!!msg.operationObservability && (
              <OperationObservabilityPanel trace={msg.operationObservability} />
            )}
            {contentParts.map((part, idx) => (
              <div key={`part-${idx}`} className={part.highlighted ? 'final-summary-block' : ''} style={{ marginTop: idx === 0 ? 0 : 10 }}>
                <div className="markdown-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
                    {part.text}
                  </ReactMarkdown>
                </div>
              </div>
            ))}
          </>
        )}
        {msg.skill && (
          <div style={{ marginTop: 8 }}>
            <Tag color="purple" style={{ margin: 0, borderRadius: 4, fontSize: 12 }}>
              <ThunderboltOutlined /> {msg.skill}
            </Tag>
          </div>
        )}
        {!isUser && msg.llm_used && (
          <div style={{ marginTop: 8 }}>
            <Tag color="blue" style={{ margin: 0, borderRadius: 4, fontSize: 11 }}>
              <ApiOutlined /> {t('algorithmAgent.llmGenerated')}
            </Tag>
          </div>
        )}
        {msg.skillResult && (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Tag 
              color={msg.skillResult.status === 'success' ? 'green' : 'red'} 
              style={{ margin: 0, borderRadius: 4, fontSize: 12 }}
            >
              {msg.skillResult.status === 'success' ? t('algorithmAgent.execSuccess') : t('algorithmAgent.execFailed')}
            </Tag>
            <Text style={{ fontSize: 12, color: '#9ca3af' }}>
              {msg.skillResult.duration_ms}ms
            </Text>
          </div>
        )}
      </div>
    </div>
  );
};
// @AI_GENERATED: end


// @AI_GENERATED: Kiro v1.0
// Agent 选择卡片组件
const AgentCard: React.FC<{
  type: AgentType;
  isActive: boolean;
  onClick: () => void;
}> = ({ type, isActive, onClick }) => {
  const config = AGENT_CONFIGS[type];
  
  return (
    <div
      onClick={onClick}
      style={{
        padding: '12px',
        borderRadius: 12,
        cursor: 'pointer',
        background: isActive ? config.gradient : '#fff',
        border: isActive ? '2px solid transparent' : '1px solid #e5e7eb',
        boxSizing: 'border-box',
        transition: 'background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease',
        marginBottom: 8,
        minHeight: 56, // 固定最小高度防止切换时抖动
      }}
      onMouseEnter={(e) => {
        if (!isActive) {
          e.currentTarget.style.borderColor = config.color;
          e.currentTarget.style.boxShadow = `0 0 0 1px ${config.color}20`;
        }
      }}
      onMouseLeave={(e) => {
        if (!isActive) {
          e.currentTarget.style.borderColor = '#e5e7eb';
          e.currentTarget.style.boxShadow = 'none';
        }
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 32,
          height: 32,
          borderRadius: 8,
          background: isActive ? 'rgba(255,255,255,0.2)' : `${config.color}15`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: isActive ? '#fff' : config.color,
          fontSize: 16,
        }}>
          {config.icon}
        </div>
        <div style={{ flex: 1 }}>
          <Text style={{ 
            fontSize: 13, 
            fontWeight: 600, 
            color: isActive ? '#fff' : '#1f2937',
            display: 'block',
          }}>
            {td(config.name)}
          </Text>
          <Text style={{ 
            fontSize: 11, 
            color: isActive ? 'rgba(255,255,255,0.8)' : '#9ca3af',
          }}>
            {config.englishName}
          </Text>
        </div>
      </div>
    </div>
  );
};
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
const AlgorithmAgentPage: React.FC = () => {
  const store = useAlgorithmAgentStore();
  // @AI_GENERATED
  const { t, i18n } = useTranslation();
  // @AI_GENERATED: end
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [sending, setSending] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [llmStatus, setLLMStatus] = useState<LLMStatus | null>(null);
  const [streamingContent, setStreamingContent] = useState<string>('');
  const streamingContentRef = useRef<string>('');
  const [streamingReasoning, setStreamingReasoning] = useState<string>('');
  const streamingReasoningRef = useRef<string>('');
  const [streamingObservability, setStreamingObservability] = useState<OperationObservability | undefined>(undefined);
  const [reasoningProgressLine, setReasoningProgressLine] = useState<string | null>(null);
  const reasoningChunkedRef = useRef(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<any>(null);
  const welcomeAddedRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const lastAgentTypeRef = useRef<AgentType | null>(null);
  const templateHandledRef = useRef(false);
  const [storeHydrated, setStoreHydrated] = useState(() =>
    useAlgorithmAgentStore.persist.hasHydrated()
  );
  const [triggerBacktestAfterRetrain, setTriggerBacktestAfterRetrain] = useState<boolean>(
    Boolean(store.context.trigger_backtest_after_retrain)
  );
  const [triggerBacktestAfterTuning, setTriggerBacktestAfterTuning] = useState<boolean>(
    Boolean(store.context.trigger_backtest_after_tuning)
  );
  const [backtestStartDate, setBacktestStartDate] = useState<string>(store.context.backtest_start_date || '');
  const [backtestEndDate, setBacktestEndDate] = useState<string>(store.context.backtest_end_date || '');

  const currentAgentConfig = AGENT_CONFIGS[store.agentType];

  // @AI_GENERATED: Kiro v1.0
  // 从 localStorage 恢复完成前不要插入欢迎语，避免与已持久化的消息竞态
  useEffect(() => {
    if (useAlgorithmAgentStore.persist.hasHydrated()) {
      setStoreHydrated(true);
    }
    return useAlgorithmAgentStore.persist.onFinishHydration(() => {
      setStoreHydrated(true);
    });
  }, []);

  // 处理从策划 Agent 跳转时的模板预选
  useEffect(() => {
    if (templateHandledRef.current) return;
    
    const agent = searchParams.get('agent') as AgentType | null;
    const templateId = searchParams.get('templateId');
    const templateType = searchParams.get('templateType');
    const templateName = searchParams.get('templateName');
    
    if (agent === 'sandbox' && templateId && templateType && templateName) {
      templateHandledRef.current = true;
      
      // 切换到 Sandbox Agent
      store.setAgentType('sandbox');
      
      // 生成带模板信息的欢迎消息
      const templateTypeLabel = getTemplateTypeLabel(templateType as 'workflow' | 'skill', t);
      const welcomeWithTemplate = t('algorithmAgent.preselectedSandboxWelcome', {
        templateName: td(templateName),
        templateTypeLabel,
      });

      const welcomeMsg: AgentMessage = {
        id: `welcome-template-${Date.now()}`,
        role: 'assistant',
        content: welcomeWithTemplate,
        timestamp: new Date().toISOString(),
      };
      store.setMessages([welcomeMsg]);
      store.setSessionId(null);
      store.setSuggestedActions([
        { label: td('使用默认数据集'), action: 'use-default-dataset' },
        { label: td('上传新数据集'), action: 'upload-dataset' },
        { label: td('查看模板参数'), action: 'view-template-params' },
      ]);
      
      // 设置上下文，保存模板信息
      store.updateContext({
        preselected_template: {
          id: templateId,
          type: templateType as 'workflow' | 'skill',
          name: templateName,
        },
      });
      
      // 清除 URL 参数
      setSearchParams({});
      
      message.success(t('algorithmAgent.switchedToSandbox', { name: td(templateName) }));
    }
  }, [searchParams, t]);
  // @AI_GENERATED: end

  useEffect(() => {
    // 只在有新消息时滚动，且使用 instant 避免动画抖动
    if (store.messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'instant' });
    }
  }, [store.messages.length]);

  // 切换 Agent 时的欢迎消息已在 handleAgentChange 中处理
  // 这里只需要追踪 lastAgentTypeRef 用于其他逻辑
  useEffect(() => {
    lastAgentTypeRef.current = store.agentType;
  }, [store.agentType]);

  // 初始化欢迎消息（仅本地尚无任何消息且已 hydrates）
  useEffect(() => {
    if (!storeHydrated) {
      return;
    }
    if (store.messages.length === 0 && !welcomeAddedRef.current && !templateHandledRef.current) {
      welcomeAddedRef.current = true;
      store.addMessage({
        id: `welcome-${Date.now()}`,
        role: 'assistant',
        content: getWelcomeMessage(store.agentType, t),
        timestamp: new Date().toISOString(),
      });
    }
  }, [storeHydrated, store.messages.length, store.agentType, t]);

  // 语言切换后，实时刷新当前会话中的欢迎消息（不改动用户历史提问）
  useEffect(() => {
    if (store.messages.length === 0) return;
    if (store.messages.some((msg) => msg.role === 'user')) return;

    let changed = false;
    const nextMessages = store.messages.map((msg) => {
      if (msg.role !== 'assistant') return msg;

      if (msg.id.startsWith('welcome-template-')) {
        const template = store.context.preselected_template;
        if (!template) return msg;
        const nextContent = t('algorithmAgent.preselectedSandboxWelcome', {
          templateName: td(template.name),
          templateTypeLabel: getTemplateTypeLabel(template.type, t),
        });
        if (nextContent === msg.content) return msg;
        changed = true;
        return { ...msg, content: nextContent };
      }

      if (msg.id.startsWith('welcome-')) {
        const nextContent = getWelcomeMessage(store.agentType, t);
        if (nextContent === msg.content) return msg;
        changed = true;
        return { ...msg, content: nextContent };
      }

      return msg;
    });

    if (changed) {
      store.setMessages(nextMessages);
    }
  }, [i18n.language, store.messages, store.context.preselected_template, store.agentType, t]);

  useEffect(() => {
    setTriggerBacktestAfterRetrain(Boolean(store.context.trigger_backtest_after_retrain));
    setTriggerBacktestAfterTuning(Boolean(store.context.trigger_backtest_after_tuning));
    setBacktestStartDate(store.context.backtest_start_date || '');
    setBacktestEndDate(store.context.backtest_end_date || '');
  }, [store.sessionId]);

  // 获取 LLM 状态
  useEffect(() => {
    const fetchLLMStatus = async () => {
      try {
        const status = await algorithmAgentApi.getLLMStatus();
        setLLMStatus(status);
      } catch {
        setLLMStatus({ available: false, error: t('algorithmAgent.llmNotConfigured') });
      }
    };
    fetchLLMStatus();
  }, []);

  const handleSend = async () => {
    const content = store.inputValue.trim();
    if (!content || sending) return;
    const language = (i18n.language || '').toLowerCase().startsWith('en') ? 'en-US' : 'zh-CN';

    const userMsg: AgentMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };
    store.addMessage(userMsg);
    store.setInputValue('');
    setSending(true);
    setStreamingContent('');
    streamingContentRef.current = '';
    streamingReasoningRef.current = '';
    setStreamingReasoning('');
    setStreamingObservability(undefined);
    setReasoningProgressLine(null);
    reasoningChunkedRef.current = false;
    const msgId = `assistant-${Date.now()}`;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    try {
      abortControllerRef.current = algorithmAgentApi.chatStream(
        {
          session_id: store.sessionId || undefined,
          message: content,
          context: {
            ...store.context,
            agent_type: store.agentType,
            language,
            ...(store.agentType === 'operation'
              ? {
                  trigger_backtest_after_retrain: triggerBacktestAfterRetrain,
                  trigger_backtest_after_tuning: triggerBacktestAfterTuning,
                  backtest_start_date: backtestStartDate || undefined,
                  backtest_end_date: backtestEndDate || undefined,
                }
              : {}),
          },
          use_llm: true,
        },
        (chunk: string) => {
          setReasoningProgressLine(null);
          streamingContentRef.current += chunk;
          setStreamingContent(streamingContentRef.current);
        },
        (data: { llm_used: boolean; suggested_actions: any[]; operation_observability?: OperationObservability }) => {
          if (data.operation_observability) {
            setStreamingObservability(data.operation_observability);
          }
          const wid = data.operation_observability?.preloading?.workflow_id;
          if (typeof wid === 'string' && wid.trim()) {
            store.updateContext({ last_executed_workflow_id: wid.trim() });
          }
          const rs = streamingReasoningRef.current;
          const assistantMsg: AgentMessage = {
            id: msgId,
            role: 'assistant',
            content: streamingContentRef.current,
            timestamp: new Date().toISOString(),
            llm_used: data.llm_used,
            ...(rs.trim() ? { reasoningContent: rs } : {}),
            ...(data.operation_observability ? { operationObservability: data.operation_observability } : {}),
          };
          store.addMessage(assistantMsg);
          setStreamingContent('');
          streamingContentRef.current = '';
          setStreamingReasoning('');
          streamingReasoningRef.current = '';
          setStreamingObservability(undefined);
          setReasoningProgressLine(null);
          if (data.suggested_actions) {
            store.setSuggestedActions(data.suggested_actions);
            // @AI_GENERATED
            // 检测负荷预测训练跳转指令
            const navAction = data.suggested_actions.find(
              (a: any) => a.action === 'navigate-load-forecast-training'
            );
            if (navAction) {
              const params = navAction.params || {};
              const qs = new URLSearchParams();
              if (params.task_type) qs.set('task_type', params.task_type);
              if (params.parent_id) qs.set('parent_id', params.parent_id);
              if (params.child_id) qs.set('child_id', params.child_id);
              if (params.csv_path) qs.set('csv_path', params.csv_path);
              // 延迟 1.5 秒跳转，让用户看到响应
              setTimeout(() => {
                navigate(`/workflow/editor/workflow-load-forecast-training-v2`);
              }, 1500);
            }
            // @AI_GENERATED: end
          }
          store.saveToHistory();
          setSending(false);
          inputRef.current?.focus();
        },
        (sessionId: string) => {
          if (!store.sessionId) {
            store.setSessionId(sessionId);
          }
        },
        () => {
          const mockResponse: AgentMessage = {
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: getMockResponse(content, store.agentType),
            timestamp: new Date().toISOString(),
          };
          store.addMessage(mockResponse);
          store.setSuggestedActions(getMockSuggestions(content, store.agentType));
          setStreamingContent('');
          streamingContentRef.current = '';
          setStreamingReasoning('');
          streamingReasoningRef.current = '';
          setStreamingObservability(undefined);
          setReasoningProgressLine(null);
          setSending(false);
          inputRef.current?.focus();
        },
        (text: string) => {
          if (reasoningChunkedRef.current) {
            return;
          }
          streamingReasoningRef.current = text;
          setStreamingReasoning(text);
          setReasoningProgressLine(null);
        },
        (piece: string) => {
          if (!piece) {
            return;
          }
          reasoningChunkedRef.current = true;
          setReasoningProgressLine(null);
          streamingReasoningRef.current += piece;
          setStreamingReasoning(streamingReasoningRef.current);
        },
        (line: string) => {
          setReasoningProgressLine(line);
        },
      );
    } catch {
      const mockResponse: AgentMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: getMockResponse(content, store.agentType),
        timestamp: new Date().toISOString(),
      };
      store.addMessage(mockResponse);
      store.setSuggestedActions(getMockSuggestions(content, store.agentType));
      setStreamingContent('');
      streamingContentRef.current = '';
      setStreamingReasoning('');
      streamingReasoningRef.current = '';
      setStreamingObservability(undefined);
      setReasoningProgressLine(null);
      setSending(false);
      inputRef.current?.focus();
    }
  };

  const handleQuickCommand = (prompt: string) => {
    store.setInputValue(prompt);
    setTimeout(() => handleSend(), 100);
  };

  const handleSuggestedAction = (action: SuggestedAction) => {
    store.setInputValue(action.label);
    setTimeout(() => handleSend(), 100);
  };

  const handleNewSession = () => {
    store.startNewSession();
    store.addMessage({
      id: `welcome-${Date.now()}`,
      role: 'assistant',
      content: getWelcomeMessage(store.agentType, t),
      timestamp: new Date().toISOString(),
    });
    message.success(t('algorithmAgent.newSessionMsg'));
  };

  const handleAgentChange = (agentType: AgentType) => {
    if (agentType !== store.agentType) {
      // 保存当前会话
      if (store.messages.length > 1) {
        store.saveToHistory();
      }
      // 切换 Agent 时直接设置欢迎消息，避免先清空再添加导致的跳动
      const welcomeMsg: AgentMessage = {
        id: `welcome-${Date.now()}`,
        role: 'assistant',
        content: getWelcomeMessage(agentType, t),
        timestamp: new Date().toISOString(),
      };
      store.setAgentType(agentType);
      store.setMessages([welcomeMsg]);
      store.setSessionId(null);
      store.setSuggestedActions([]);
      message.info(`${t('algorithmAgent.switchedTo', { name: td(AGENT_CONFIGS[agentType].name) })}`);
    }
  };

  const handleLoadSession = async (sessionId: string) => {
    // 优先从本地历史加载
    const loaded = store.loadSessionFromHistory(sessionId);
    if (loaded) {
      message.success(t('algorithmAgent.loadSessionSuccess'));
    } else {
      // 如果本地没有，尝试从后端加载
      try {
        const session = await algorithmAgentApi.getSession(sessionId);
        store.loadSession(session.id, session.messages, session.context);
        message.success(t('algorithmAgent.loadSessionSuccess'));
      } catch {
        message.error(t('algorithmAgent.loadSessionFailed'));
      }
    }
  };

  const currentCommands = currentAgentConfig.quickCommandIds.map((id) => ({
    label: t(`algorithmAgent.quickCmd.${store.agentType}.${id}.label`),
    prompt: t(`algorithmAgent.quickCmd.${store.agentType}.${id}.prompt`),
  }));
// @AI_GENERATED: end


  // @AI_GENERATED: Kiro v1.0
  return (
    <Layout style={{ height: 'calc(100vh - 64px)', background: '#fff' }}>
      {/* 左侧边栏 */}
      <Sider
        width={280}
        collapsedWidth={0}
        collapsed={sidebarCollapsed}
        style={{
          background: '#f9fafb',
          borderRight: '1px solid #e5e7eb',
          overflow: 'hidden',
        }}
      >
        <div style={{ 
          height: '100%', 
          display: 'flex', 
          flexDirection: 'column',
          padding: '12px',
        }}>
          {/* Logo 区域 */}
          <div style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: 8,
            padding: '8px 4px',
            marginBottom: 12,
          }}>
            <div style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: currentAgentConfig.gradient,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <RobotOutlined style={{ color: '#fff', fontSize: 18 }} />
            </div>
            <div>
              <Text strong style={{ fontSize: 14, color: '#1f2937', display: 'block' }}>
                {t('algorithmAgent.brandTitle')}
              </Text>
              <Text style={{ fontSize: 11, color: '#9ca3af' }}>
                {t('algorithmAgent.lifecycleAssistant')}
              </Text>
            </div>
          </div>

          {/* 新建对话按钮 */}
          <Button
            type="text"
            icon={<PlusOutlined />}
            onClick={handleNewSession}
            style={{
              width: '100%',
              height: 40,
              borderRadius: 10,
              border: '1px dashed #d1d5db',
              color: '#6b7280',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
              marginBottom: 16,
            }}
          >
            {t('algorithmAgent.newChat')}
          </Button>

          {/* Agent 选择 */}
          <div style={{ marginBottom: 16 }}>
            <Text style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8, display: 'block' }}>
              {t('algorithmAgent.selectAgent')}
            </Text>
            {(['curator', 'sandbox', 'onboarding', 'operation'] as AgentType[]).map((type) => (
              <AgentCard
                key={type}
                type={type}
                isActive={store.agentType === type}
                onClick={() => handleAgentChange(type)}
              />
            ))}
          </div>

          {/* 历史会话列表 */}
          <div style={{ flex: 1, overflow: 'auto' }}>
            <Text style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8, display: 'block' }}>
              {t('algorithmAgent.historySession')}
            </Text>
            {store.sessionHistory.length === 0 ? (
              <Empty 
                image={Empty.PRESENTED_IMAGE_SIMPLE} 
                description={<Text style={{ color: '#9ca3af', fontSize: 12 }}>{t('algorithmAgent.noHistory')}</Text>}
                style={{ marginTop: 20 }}
              />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {store.sessionHistory.slice(0, 10).map((item) => (
                  <div
                    key={item.id}
                    onClick={() => handleLoadSession(item.id)}
                    style={{
                      padding: '10px 12px',
                      borderRadius: 8,
                      cursor: 'pointer',
                      background: store.sessionId === item.id ? '#e5e7eb' : 'transparent',
                      transition: 'background 0.2s',
                    }}
                    onMouseEnter={(e) => {
                      if (store.sessionId !== item.id) {
                        e.currentTarget.style.background = '#f3f4f6';
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (store.sessionId !== item.id) {
                        e.currentTarget.style.background = 'transparent';
                      }
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {item.agentType && (
                        <span style={{ 
                          fontSize: 12, 
                          color: AGENT_CONFIGS[item.agentType]?.color || '#6b7280' 
                        }}>
                          {AGENT_CONFIGS[item.agentType]?.icon}
                        </span>
                      )}
                      <Text 
                        ellipsis 
                        style={{ 
                          fontSize: 13, 
                          color: '#374151',
                          flex: 1,
                        }}
                      >
                        {item.title}
                      </Text>
                    </div>
                    <Text style={{ fontSize: 11, color: '#9ca3af' }}>
                      {new Date(item.updatedAt).toLocaleDateString()}
                    </Text>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 清空历史 */}
          {store.sessionHistory.length > 0 && (
            <Button
              type="text"
              size="small"
              icon={<DeleteOutlined />}
              onClick={() => { store.clearHistory(); message.success(t('algorithmAgent.historyClearedMsg')); }}
              style={{ color: '#9ca3af', marginTop: 8 }}
            >
              {t('algorithmAgent.clearHistory')}
            </Button>
          )}
        </div>
      </Sider>

      {/* 主内容区 */}
      <Content style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* 顶部栏 */}
        <div style={{ 
          height: 56,
          padding: '0 16px',
          borderBottom: '1px solid #e5e7eb',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Button
              type="text"
              icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              style={{ color: '#6b7280' }}
            />
            <div style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: currentAgentConfig.gradient,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              {currentAgentConfig.icon}
            </div>
            <div>
              <Text style={{ fontSize: 15, color: '#1f2937', fontWeight: 600 }}>
                {currentAgentConfig.englishName}
              </Text>
              <Text style={{ fontSize: 12, color: '#9ca3af', marginLeft: 8 }}>
                {td(currentAgentConfig.name)}
              </Text>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {/* LLM 状态指示器 */}
            <Tooltip 
              title={
                llmStatus?.available 
                  ? t('algorithmAgent.llmEnabled', { provider: llmStatus.provider, model: llmStatus.model })
                  : llmStatus?.message || llmStatus?.error || t('algorithmAgent.llmNotConfigured')
              }
            >
              <Tag 
                icon={llmStatus?.available ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                color={llmStatus?.available ? 'success' : 'default'}
                style={{ cursor: 'pointer' }}
              >
                <ApiOutlined style={{ marginRight: 4 }} />
                {llmStatus?.available ? 'LLM' : t('algorithmAgent.ruleMode')}
              </Tag>
            </Tooltip>
            <Tooltip title={t('algorithmAgent.moreOptions')}>
              <Button type="text" icon={<MoreOutlined />} style={{ color: '#6b7280' }} />
            </Tooltip>
          </div>
        </div>

        {/* 消息区域 */}
        <div style={{ 
          flex: 1, 
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0, // 确保 flex 子元素可以正确收缩
        }}>
          <div style={{ 
            maxWidth: 800, 
            width: '100%', 
            margin: '0 auto',
            padding: '24px 24px 0',
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            minHeight: 300, // 固定最小高度防止抖动
          }}>
            <div style={{ marginTop: 'auto' }}>
              {store.messages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} agentType={store.agentType} />
              ))}
              {/* 流式：模型「思考过程」+ 正式回答（运营 Agent 与后端 agent_thinking 对齐） */}
              {sending
                && (streamingContent
                  || streamingReasoning
                  || !!reasoningProgressLine) && (
                <div style={{ marginBottom: 24 }}>
                  <style>{markdownStyles}</style>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <div style={{
                      width: 24,
                      height: 24,
                      borderRadius: 6,
                      background: currentAgentConfig.gradient,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      <RobotOutlined style={{ color: '#fff', fontSize: 14 }} />
                    </div>
                    <Text style={{ fontSize: 14, color: '#1f2937', fontWeight: 500 }}>
                      {currentAgentConfig.englishName}
                    </Text>
                  </div>
                  <ModelReasoningPanel
                    content={streamingReasoning}
                    progressMessage={reasoningProgressLine}
                  />
                  {!!streamingObservability && (
                    <OperationObservabilityPanel trace={streamingObservability} />
                  )}
                  {!!streamingContent && (
                    <div className="markdown-content">
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MarkdownComponents}>
                        {streamingContent}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              )}
              {/* 等待首包 */}
              {sending
                && !streamingContent
                && !streamingReasoning
                && !reasoningProgressLine && (
                <div style={{ marginBottom: 24 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <div style={{
                      width: 24,
                      height: 24,
                      borderRadius: 6,
                      background: currentAgentConfig.gradient,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}>
                      <RobotOutlined style={{ color: '#fff', fontSize: 14 }} />
                    </div>
                    <Text style={{ fontSize: 14, color: '#1f2937', fontWeight: 500 }}>
                      {currentAgentConfig.englishName}
                    </Text>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Spin size="small" />
                    <Text style={{ color: '#9ca3af', fontSize: 14 }}>{t('algorithmAgent.thinking')}</Text>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>
        </div>

        {/* 输入区域 */}
        <div style={{ 
          padding: '16px 24px 24px',
          background: '#fff',
          flexShrink: 0,
        }}>
          <div style={{ maxWidth: 800, margin: '0 auto' }}>
            {/* 建议操作 */}
            {store.suggestedActions.length > 0 && (
              <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {store.suggestedActions.map((action, idx) => (
                  <Button
                    key={idx}
                    size="small"
                    onClick={() => handleSuggestedAction(action)}
                    style={{ 
                      borderRadius: 16, 
                      background: '#f3f4f6', 
                      border: 'none',
                      color: '#4b5563',
                      fontSize: 13,
                    }}
                  >
                    {td(action.label)}
                  </Button>
                ))}
              </div>
            )}

            {/* 快捷指令 */}
            <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {currentCommands.slice(0, 4).map((cmd, idx) => (
                <Button
                  key={idx}
                  size="small"
                  onClick={() => handleQuickCommand(cmd.prompt)}
                  style={{ 
                    borderRadius: 16, 
                    background: `${currentAgentConfig.color}10`, 
                    border: 'none',
                    color: currentAgentConfig.color,
                    fontSize: 13,
                  }}
                >
                  {cmd.label}
                </Button>
              ))}
              {currentCommands.length > 4 && (
                <Tooltip
                  title={
                    <Space direction="vertical" size={4}>
                      {currentCommands.slice(4).map((cmd, idx) => (
                        <Button
                          key={idx}
                          type="text"
                          size="small"
                          onClick={() => handleQuickCommand(cmd.prompt)}
                          style={{ color: '#fff', padding: '4px 8px' }}
                        >
                          {cmd.label}
                        </Button>
                      ))}
                    </Space>
                  }
                  placement="top"
                >
                  <Button
                    size="small"
                    type="text"
                    icon={<BulbOutlined />}
                    style={{ color: '#9ca3af', fontSize: 13 }}
                  >
                    {t('algorithmAgent.more')}
                  </Button>
                </Tooltip>
              )}
            </div>

            {store.agentType === 'operation' && (
              <div
                style={{
                  marginTop: 10,
                  marginBottom: 8,
                  padding: '10px 12px',
                  background: '#f9fafb',
                  border: '1px solid #e5e7eb',
                  borderRadius: 10,
                  display: 'grid',
                  gap: 8,
                }}
              >
                <Text style={{ fontSize: 12, color: '#4b5563', fontWeight: 600 }}>
                  回测触发设置（运营Agent）
                </Text>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <Text style={{ fontSize: 12, color: '#6b7280', minWidth: 160 }}>重训后触发真实回测</Text>
                  <Switch
                    size="small"
                    checked={triggerBacktestAfterRetrain}
                    onChange={(v) => {
                      setTriggerBacktestAfterRetrain(v);
                      store.updateContext({ trigger_backtest_after_retrain: v });
                    }}
                  />
                  <Text style={{ fontSize: 12, color: '#6b7280', minWidth: 160 }}>调优后触发真实回测</Text>
                  <Switch
                    size="small"
                    checked={triggerBacktestAfterTuning}
                    onChange={(v) => {
                      setTriggerBacktestAfterTuning(v);
                      store.updateContext({ trigger_backtest_after_tuning: v });
                    }}
                  />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <Text style={{ fontSize: 12, color: '#6b7280' }}>回测日期范围</Text>
                  <Input
                    value={backtestStartDate}
                    onChange={(e) => {
                      const v = e.target.value;
                      setBacktestStartDate(v);
                      store.updateContext({ backtest_start_date: v || undefined });
                    }}
                    placeholder="开始日期 YYYY-MM-DD"
                    style={{ width: 170 }}
                    size="small"
                  />
                  <Input
                    value={backtestEndDate}
                    onChange={(e) => {
                      const v = e.target.value;
                      setBacktestEndDate(v);
                      store.updateContext({ backtest_end_date: v || undefined });
                    }}
                    placeholder="结束日期 YYYY-MM-DD"
                    style={{ width: 170 }}
                    size="small"
                  />
                </div>
              </div>
            )}

            {/* 输入框 */}
            <div style={{ 
              background: '#f3f4f6',
              borderRadius: 24,
              padding: '8px 8px 8px 20px',
              display: 'flex',
              alignItems: 'flex-end',
              border: '1px solid transparent',
              transition: 'border-color 0.2s, box-shadow 0.2s',
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = currentAgentConfig.color;
              e.currentTarget.style.boxShadow = `0 0 0 2px ${currentAgentConfig.color}20`;
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = 'transparent';
              e.currentTarget.style.boxShadow = 'none';
            }}
            >
              <TextArea
                ref={inputRef}
                value={store.inputValue}
                onChange={(e) => store.setInputValue(e.target.value)}
                placeholder={t('algorithmAgent.askPlaceholder', { name: td(currentAgentConfig.name) })}
                autoSize={{ minRows: 1, maxRows: 6 }}
                onPressEnter={(e) => {
                  if (!e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                style={{ 
                  flex: 1,
                  border: 'none', 
                  background: 'transparent',
                  resize: 'none',
                  fontSize: 15,
                  padding: '4px 0',
                  boxShadow: 'none',
                  color: '#1f2937',
                }}
              />
              <Button
                type="primary"
                shape="circle"
                icon={<SendOutlined />}
                onClick={handleSend}
                loading={sending}
                disabled={!store.inputValue.trim()}
                style={{ 
                  background: store.inputValue.trim() ? currentAgentConfig.color : '#d1d5db',
                  border: 'none',
                  width: 36,
                  height: 36,
                  marginLeft: 8,
                  flexShrink: 0,
                }}
              />
            </div>
            <Text style={{ 
              display: 'block', 
              textAlign: 'center', 
              fontSize: 12, 
              color: '#9ca3af',
              marginTop: 12,
            }}>
              {t('algorithmAgent.enterToSend')}
            </Text>
          </div>
        </div>
      </Content>
    </Layout>
  );
};
// @AI_GENERATED: end


// @AI_GENERATED: Kiro v1.0
// Mock 响应函数（后端未实现时使用）
function getMockResponse(input: string, agentType: AgentType): string {
  const lowerInput = input.toLowerCase();
  
  switch (agentType) {
    case 'curator':
      if (lowerInput.includes('搜索') || lowerInput.includes('解决方案')) {
        return `好的，我来帮你搜索AI解决方案库。

**搜索结果**：

| 方案名称 | 适用场景 | 算法类型 | 精度指标 | 推荐指数 |
|---------|---------|---------|---------|---------|
| 光伏功率预测 | 新能源发电 | Ridge/LSTM | MAPE 7.73% | ⭐⭐⭐⭐⭐ |
| 负荷预测 | 电网调度 | XGBoost | MAPE 3.2% | ⭐⭐⭐⭐ |
| 风电功率预测 | 风力发电 | LightGBM | MAPE 8.5% | ⭐⭐⭐⭐ |

**推荐方案**：基于你的需求，推荐使用「光伏功率预测」方案。需要我详细介绍吗？`;
      }
      if (lowerInput.includes('推荐') || lowerInput.includes('模板')) {
        return `根据你的业务场景，我推荐以下算法模板：

**推荐模板**：光伏发电功率预测模板

📋 **模板信息**：
- 模板ID: pv-power-forecast
- 适用场景: 日前功率预测
- 核心算法: Ridge 回归 / LSTM
- 数据要求: 历史发电量 + 气象数据

📊 **性能指标**：
- 白天 MAPE: 7.73%
- R²: 0.9842
- 训练时间: < 1分钟

需要我帮你配置这个模板吗？`;
      }
      return `我是 Curator Agent，可以帮你：
• 搜索AI解决方案库
• 推荐算法模板
• 分析数据需求
• 对比方案优劣

请告诉我你的具体需求。`;

    case 'sandbox':
      if (lowerInput.includes('挂载') || lowerInput.includes('数据集')) {
        return `好的，让我引导你挂载数据集。

**数据集挂载向导**：

1️⃣ **选择数据源**
   - 本地上传 CSV/Excel
   - 数据库连接
   - API 接口

2️⃣ **数据格式要求**
   - 时间列: datetime 格式
   - 目标列: 数值型
   - 特征列: 数值型/类别型

3️⃣ **数据预览**
   上传后我会自动检测数据格式并给出建议。

请上传你的数据集，或告诉我数据源类型。`;
      }
      if (lowerInput.includes('训练') || lowerInput.includes('开始')) {
        return `好的，开始模型训练。

**训练配置**：
- 算法: Ridge 回归
- 数据集: pv_power_sample.csv
- 训练集: 70% | 验证集: 15% | 测试集: 15%

**训练进度**：
✅ 数据验证完成
✅ 特征工程完成
✅ 模型训练完成
✅ 模型评估完成

**精度结果**：
| 数据集 | MAPE | RMSE | R² |
|-------|------|------|-----|
| 训练集 | 6.85% | 118.2 | 0.9876 |
| 验证集 | 7.23% | 122.5 | 0.9854 |
| 测试集 | 7.73% | 124.5 | 0.9842 |

模型训练完成！需要我帮你部署上线吗？`;
      }
      return `我是 Sandbox Agent，可以帮你：
• 引导数据集挂载
• 自动适配算法模板
• 执行模型训练
• 评估精度指标

准备好数据集了吗？`;

    case 'onboarding':
      if (lowerInput.includes('上线') || lowerInput.includes('部署')) {
        return `好的，我来帮你将模型上线。

**上线配置**：

📦 **模型信息**：
- 模型名称: pv-power-forecast-v1.0
- 模型大小: 2.3 MB
- 推理延迟: < 10ms

🚀 **部署选项**：
1. **实时推理服务** - REST API，支持单条/批量预测
2. **批量预测任务** - 定时执行，结果写入数据库
3. **流式预测** - Kafka 消费，实时输出

⚙️ **资源配置**：
- CPU: 2核
- 内存: 4GB
- 副本数: 2

确认以上配置后，我将为你部署服务。是否继续？`;
      }
      if (lowerInput.includes('定期') || lowerInput.includes('重训')) {
        return `好的，配置定期训练计划。

**定期训练配置**：

⏰ **训练计划**：
- 触发方式: 定时 + 漂移触发
- 定时周期: 每周一 02:00
- 漂移阈值: MAPE 增加 > 2%

📊 **数据配置**：
- 训练数据: 最近 90 天
- 增量更新: 是
- 数据验证: 自动

🔄 **部署策略**：
- 自动部署: 精度提升时
- 灰度发布: 10% → 50% → 100%
- 回滚条件: 精度下降 > 1%

配置已保存，下次训练将在周一 02:00 自动执行。`;
      }
      return `我是 Onboarding Agent，可以帮你：
• 将模型上线为服务
• 配置定期训练计划
• 部署推理 API
• 监控服务状态

模型训练完成了吗？`;

    case 'operation':
      if (lowerInput.includes('漂移') || lowerInput.includes('检测')) {
        return `好的，执行精度漂移检测。

**漂移检测报告**：

📉 **数据漂移**：
- PSI 分数: 0.15 (轻度漂移)
- 漂移特征: temperature_forecast, cloud_cover
- 状态: ⚠️ 警告

📊 **概念漂移**：
- 精度变化: MAPE 7.73% → 9.12% (+1.39%)
- 趋势: 轻微下降
- 状态: ⚠️ 警告

🔍 **漂移原因分析**：
1. 气象数据分布变化（季节性）
2. 光伏板效率衰减
3. 新增遮挡物影响

**建议**：检测到轻度漂移，建议在 7 天内进行增量重训。`;
      }
      if (lowerInput.includes('根因') || lowerInput.includes('分析')) {
        return `好的，执行根因分析。

**精度下降根因分析**：

📊 **精度变化**：
- 基线 MAPE: 7.73%
- 当前 MAPE: 9.12%
- 下降幅度: +1.39%

🔍 **根因定位**：

| 因素 | 贡献度 | 详情 |
|-----|-------|------|
| 气象数据偏差 | 45% | 温度预报误差增大 |
| 季节性变化 | 30% | 冬季日照时长变化 |
| 设备老化 | 15% | 光伏板效率下降 |
| 数据质量 | 10% | 缺失值增加 |

**改进建议**：
1. 更新气象数据源，提高预报精度
2. 增加季节性特征，适应冬季模式
3. 校准设备效率参数
4. 加强数据质量监控`;
      }
      if (lowerInput.includes('重训') || lowerInput.includes('调优')) {
        return `好的，启动自动重训和调优。

**自动重训配置**：

🤖 **模型选择**：
- 候选算法: Ridge, XGBoost, LightGBM
- 选择策略: 交叉验证最优

⚡ **调优策略**：
- 方法: 贝叶斯优化
- 迭代次数: 50
- 目标: 最小化 MAPE

**重训进度**：
✅ 数据准备完成
✅ 模型选择: XGBoost (CV MAPE: 6.95%)
🔄 参数调优中... (32/50)

**当前最优结果**：
- MAPE: 7.12% (提升 0.61%)
- R²: 0.9867

预计 5 分钟后完成，是否自动部署最优模型？`;
      }
      return `我是 Operation Master，可以帮你：
• 检测精度漂移
• 分析下降根因
• 自动选择模型
• 重训和调优

让我来守护你的线上模型精度！`;

    default:
      return '请选择一个 Agent 开始对话。';
  }
}

function getMockSuggestions(input: string, agentType: AgentType): SuggestedAction[] {
  const lowerInput = input.toLowerCase();
  
  switch (agentType) {
    case 'curator':
      if (lowerInput.includes('搜索') || lowerInput.includes('推荐')) {
        return [
          { label: '查看详情', action: 'view-detail' },
          { label: '配置模板', action: 'config-template' },
          { label: '对比方案', action: 'compare-solutions' },
        ];
      }
      return [
        { label: '搜索解决方案', action: 'search' },
        { label: '推荐模板', action: 'recommend' },
      ];

    case 'sandbox':
      if (lowerInput.includes('训练')) {
        return [
          { label: '查看详细指标', action: 'view-metrics' },
          { label: '部署上线', action: 'deploy' },
          { label: '对比其他算法', action: 'compare' },
        ];
      }
      return [
        { label: '挂载数据集', action: 'mount-dataset' },
        { label: '开始训练', action: 'start-training' },
      ];

    case 'onboarding':
      if (lowerInput.includes('上线') || lowerInput.includes('部署')) {
        return [
          { label: '确认部署', action: 'confirm-deploy' },
          { label: '修改配置', action: 'modify-config' },
          { label: '查看服务状态', action: 'view-status' },
        ];
      }
      return [
        { label: '上线服务', action: 'deploy' },
        { label: '配置定期训练', action: 'config-schedule' },
      ];

    case 'operation':
      if (lowerInput.includes('漂移') || lowerInput.includes('分析')) {
        return [
          { label: '触发重训', action: 'trigger-retrain' },
          { label: '查看历史趋势', action: 'view-trend' },
          { label: '配置告警', action: 'config-alert' },
        ];
      }
      return [
        { label: '漂移检测', action: 'drift-detect' },
        { label: '根因分析', action: 'root-cause' },
      ];

    default:
      return [];
  }
}
// @AI_GENERATED: end

export default AlgorithmAgentPage;
