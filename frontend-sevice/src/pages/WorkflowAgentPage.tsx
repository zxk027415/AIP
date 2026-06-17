// @AI_GENERATED: Kiro v1.0
/**
 * Workflow Agent 主页面 — 智能编排
 * 左侧：可折叠步骤面板  右侧：画布预览
 * 状态通过 zustand store 持久化，页面切换不丢失
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Layout, Input, Button, Card, Tag, Progress, Empty, Spin,
  message, Space, Typography, Collapse, Dropdown, Tooltip,
} from 'antd';
import {
  SendOutlined, RocketOutlined, EditOutlined,
  WarningOutlined, InfoCircleOutlined, BulbOutlined, CopyOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import workflowAgentApi from '../services/workflowAgentApi';
import { industryApi } from '../services/industryApi';
import { enhancedWorkflowApi } from '../services/workflowEnhancedApi';
import type { IndustryTemplate } from '../services/industryApi';
import EnhancedCanvasWithProvider from '../components/workflow-enhanced/EnhancedCanvas';
import { useWorkflowAgentStore } from '../stores/workflowAgentStore';
import { td } from '../utils/dataTranslation';
// @AI_GENERATED: end

const { Sider, Content } = Layout;
const { TextArea } = Input;
const { Text, Title } = Typography;

// @AI_GENERATED: Kiro v1.0
const EXAMPLE_PROMPTS = [
  '光伏发电功率预测，基于气象数据和历史发电量',
  '锂电池SOC估计与SOH健康状态评估',
  '电网负荷预测与调度优化',
  '钢铁连铸坯质量预测与工艺参数优化',
  '光伏组件EL缺陷检测与良率分析',
  '动力电池一致性分选与容量预测',
  '工厂设备OEE分析与排程优化',
  '港口AGV路径规划与泊位调度优化',
  '楼宇暖通空调能耗优化与舒适度控制',
  '企业碳排放核算与碳足迹追踪',
  '工业SCADA大屏数据可视化与趋势分析',
  '基于LLM的工业设备日志智能解析',
  '产线产品表面缺陷视觉检测',
  '旋转设备振动信号故障诊断与RUL预测',
];

const PROMPT_TEMPLATE = '【行业】___  【目标】___  【数据】___  【约束】___';
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
function scoreTemplateRelevance(tpl: IndustryTemplate, query: string): number {
  if (!query.trim()) return 0;
  const q = query.toLowerCase();
  const tokens = q.split(/[\s,，、;；]+/).filter(Boolean);
  let score = 0;
  const name = tpl.name.toLowerCase();
  const desc = (tpl.description || '').toLowerCase();
  const cat = (tpl.display_category || '').toLowerCase();
  if (name.includes(q)) score += 50;
  if (q.includes(name)) score += 40;
  for (const tok of tokens) {
    if (tok.length < 2) continue;
    if (name.includes(tok)) score += 20;
    if (desc.includes(tok)) score += 10;
    if (cat.includes(tok)) score += 5;
  }
  return score;
}

function rankTemplates(templates: IndustryTemplate[], query: string, topN = 5) {
  const scored = templates.map((tpl) => ({ ...tpl, relevanceScore: scoreTemplateRelevance(tpl, query) }));
  scored.sort((a, b) => b.relevanceScore - a.relevanceScore);
  return scored.slice(0, topN);
}

function transformToEnhancedNodes(rawNodes: any[]) {
  return rawNodes.map((node: any) => ({
    id: node.id,
    type: 'enhanced' as const,
    position: node.position,
    data: {
      label: node.data.label,
      description: node.data.description || null,
      type: 'function' as const,
      inputs: (node.data.inputs || []).map((inp: any) => ({ ...inp, type: 'input' as const, dataType: (inp.type || 'any').toLowerCase() })),
      outputs: (node.data.outputs || []).map((out: any) => ({ ...out, type: 'output' as const, dataType: (out.type || 'any').toLowerCase() })),
      config: { functionId: node.data.functionId, ...node.data.parameters },
      status: 'idle' as const,
    },
  }));
}

function transformToEnhancedEdges(rawEdges: any[]) {
  return rawEdges.map((edge: any) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle || undefined,
    targetHandle: edge.targetHandle || undefined,
    type: 'smoothstep' as const,
  }));
}
// @AI_GENERATED: end

// @AI_GENERATED: Kiro v1.0
const WorkflowAgentPage: React.FC = () => {
  const navigate = useNavigate();
  // @AI_GENERATED
  const { t } = useTranslation();
  // @AI_GENERATED: end
  const promptTemplate = td(PROMPT_TEMPLATE);
  const store = useWorkflowAgentStore();
  const [loading, setLoading] = useState(false);
  const [openingInEditor, setOpeningInEditor] = useState(false);
  const [canvasReady, setCanvasReady] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setCanvasReady(true), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const expandPanel = (key: string) => {
    store.setActiveKeys(store.activeKeys.includes(key) ? store.activeKeys : [...store.activeKeys, key]);
  };

  const handleMatch = async () => {
    if (!store.description.trim()) {
      store.setErrorInfo({ step: 'input', message: t('workflowAgent.enterDescription'), severity: 'info' });
      return;
    }
    setLoading(true);
    store.setStep('matching');
    store.setErrorInfo(null);
    try {
      const res = await workflowAgentApi.matchScenario({ description: store.description });
      store.setMatches(res.matches || []);
      if ((res.matches || []).length === 0) {
        store.setErrorInfo({ step: 'matching', message: t('workflowAgent.noMatchFound'), severity: 'info' });
        store.setStep('input');
      } else {
        expandPanel('step-match');
      }
    } catch (e: any) {
      store.setErrorInfo({ step: 'matching', message: e?.response?.data?.detail || e?.message || t('workflowAgent.matchFailed') });
    } finally {
      setLoading(false);
    }
  };

  const handleSelectScenario = async (match: any) => {
    store.setSelectedScenario(match);
    setLoading(true);
    store.setStep('select-template');
    store.setErrorInfo(null);
    try {
      const tpls = await industryApi.getTemplates(match.scenario_id);
      if (!tpls || tpls.length === 0) {
        store.setRankedTemplates([]);
        store.setErrorInfo({ step: 'select-template', message: t('workflowAgent.noTemplatesForScenario'), severity: 'info' });
      } else {
        store.setRankedTemplates(rankTemplates(tpls, store.description, 5));
        expandPanel('step-template');
      }
    } catch (e: any) {
      store.setErrorInfo({ step: 'select-template', message: e?.response?.data?.detail || e?.message || t('workflowAgent.loadTemplateFailed') });
    } finally {
      setLoading(false);
    }
  };

  const handleSelectTemplate = async (tpl: any) => {
    store.setSelectedTemplate(tpl);
    if (!store.selectedScenario) return;
    setLoading(true);
    store.setStep('composing');
    store.setErrorInfo(null);
    try {
      const res = await workflowAgentApi.composeAlgorithms({
        scenario_id: store.selectedScenario.scenario_id,
        template_id: tpl.id,
      });
      store.setCombinations(res.combinations || []);
      expandPanel('step-combo');
    } catch (e: any) {
      store.setErrorInfo({ step: 'composing', message: e?.response?.data?.detail || e?.message || t('workflowAgent.composeFailed') });
    } finally {
      setLoading(false);
    }
  };

  const handleSelectCombo = async (combo: any) => {
    store.setSelectedCombo(combo);
    if (!store.selectedScenario) return;
    setLoading(true);
    store.setStep('generating');
    store.setErrorInfo(null);
    try {
      const res = await workflowAgentApi.generateWorkflow({
        combination: combo,
        scenario_id: store.selectedScenario.scenario_id,
      });
      store.setGeneratedWorkflow(res);
      const wf = res.workflow as any;
      store.setPreviewNodes(transformToEnhancedNodes(wf.nodes || []));
      store.setPreviewEdges(transformToEnhancedEdges(wf.edges || []));
      expandPanel('step-generate');
      store.setStep('validating');
      try {
        const vRes = await workflowAgentApi.validateWorkflow({
          workflow: res.workflow,
          scenario_id: store.selectedScenario.scenario_id,
        });
        store.setValidationResult(vRes);
        store.setStep('done');
        // 自动保存到历史
        setTimeout(() => store.saveToHistory(), 0);
      } catch (ve: any) {
        store.setErrorInfo({ step: 'validating', message: ve?.response?.data?.detail || ve?.message || t('workflowAgent.validateFailed') });
        store.setStep('done');
        setTimeout(() => store.saveToHistory(), 0);
      }
    } catch (e: any) {
      store.setErrorInfo({ step: 'generating', message: e?.response?.data?.detail || e?.message || t('workflowAgent.generateFailed') });
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    store.resetSession();
  };

  const handleRetry = () => {
    if (!store.errorInfo) return;
    store.setErrorInfo(null);
    switch (store.errorInfo.step) {
      case 'matching': handleMatch(); break;
      case 'select-template': if (store.selectedScenario) handleSelectScenario(store.selectedScenario); break;
      case 'composing': if (store.selectedTemplate) handleSelectTemplate(store.selectedTemplate); break;
      case 'generating':
      case 'validating': if (store.selectedCombo) handleSelectCombo(store.selectedCombo); break;
    }
  };

  const handleSkipError = () => {
    if (store.errorInfo?.step === 'validating') {
      store.setErrorInfo(null);
      store.setStep('done');
    }
  };

  const handleOpenInEditor = async () => {
    if (!store.generatedWorkflow?.workflow) return;
    setOpeningInEditor(true);
    try {
      const wf = store.generatedWorkflow.workflow as any;
      const nodes = transformToEnhancedNodes(wf.nodes || []);
      const edges = transformToEnhancedEdges(wf.edges || []);
      const name = store.selectedTemplate
        ? `${store.selectedTemplate.name} - ${store.selectedCombo?.profile || t('workflowAgent.template')}`
        : t('workflowAgent.intelligentOrchestrationTemplate');
      const saved = await enhancedWorkflowApi.saveWorkflow({
        name,
        description: store.generatedWorkflow.generation_summary,
        nodes,
        edges,
      });
      message.success(t('workflowAgent.savedRedirecting'));
      navigate(`/workflow/editor/${saved.id}`);
    } catch {
      message.error(t('workflowAgent.saveFailed'));
    } finally {
      setOpeningInEditor(false);
    }
  };

// @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  const collapseItems = (() => {
    const items: { key: string; label: React.ReactNode; children: React.ReactNode }[] = [];

    items.push({
      key: 'step-input',
      label: (
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Text strong>① {t('workflowAgent.requirementDescription')}</Text>
          <Dropdown menu={{
            items: [
              { key: 'tpl', label: <Text type="secondary" style={{ fontSize: 12 }}>📋 {t('workflowAgent.promptFramework')}</Text>,
                onClick: (e: any) => { e.domEvent?.stopPropagation(); navigator.clipboard.writeText(promptTemplate); message.success(t('workflowAgent.promptFrameworkCopied')); } },
              { type: 'divider' as const },
              ...EXAMPLE_PROMPTS.map((p, i) => ({
                key: `ex-${i}`, label: <Text style={{ fontSize: 12 }}>{td(p)}</Text>,
                onClick: (e: any) => { e.domEvent?.stopPropagation(); store.setDescription(td(p)); message.success(t('workflowAgent.exampleFilled')); },
              })),
            ],
          }} trigger={['click']} placement="bottomRight">
            <Button size="small" type="text" icon={<BulbOutlined />} onClick={(e) => e.stopPropagation()}>
              {t('workflowAgent.examples')}
            </Button>
          </Dropdown>
        </Space>
      ),
      children: (
        <div>
          <Tooltip title={t('workflowAgent.clickToCopyPrompt')} placement="topRight">
            <Tag color="geekblue" style={{ cursor: 'pointer', marginBottom: 8, fontSize: 11 }}
              onClick={() => { navigator.clipboard.writeText(promptTemplate); message.success(t('workflowAgent.promptFrameworkCopied')); }}>
              <CopyOutlined /> {promptTemplate}
            </Tag>
          </Tooltip>
          <TextArea rows={3} placeholder={t('workflowAgent.descriptionPlaceholder')}
            value={store.description} onChange={(e) => store.setDescription(e.target.value)}
            disabled={store.step !== 'input'} style={{ marginBottom: 12 }} />
          <Space>
            <Button type="primary" icon={<SendOutlined />} onClick={handleMatch}
              loading={loading && store.step === 'matching'}
              disabled={store.step !== 'input' && store.step !== 'matching'}>
              {t('workflowAgent.startMatching')}
            </Button>
            {store.step !== 'input' && <Button onClick={handleReset}>{t('workflowAgent.restart')}</Button>}
          </Space>
        </div>
      ),
    });

    if (store.matches.length > 0) {
      items.push({
        key: 'step-match',
        label: <Space><Text strong>② {t('workflowAgent.scenarioMatching')}</Text>{store.selectedScenario && <Tag color="blue">{store.selectedScenario.scenario_name}</Tag>}</Space>,
        children: store.selectedScenario ? (
          <Text type="secondary">{t('workflowAgent.selected')}：{store.selectedScenario.scenario_name}（{store.selectedScenario.confidence_score}%）</Text>
        ) : (
          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>{t('workflowAgent.matchedScenarios', { count: store.matches.length })}</Text>
            {store.matches.map((m) => (
              <Card key={m.scenario_id} size="small" hoverable style={{ marginBottom: 8, cursor: 'pointer' }} onClick={() => handleSelectScenario(m)}>
                <Space direction="vertical" size={4} style={{ width: '100%' }}>
                  <Space><Text strong>{m.scenario_name}</Text><Tag color="blue">{m.confidence_score}%</Tag></Space>
                  <Progress percent={m.confidence_score} size="small" showInfo={false} />
                  <Text type="secondary" style={{ fontSize: 12 }}>{m.rationale}</Text>
                </Space>
              </Card>
            ))}
          </div>
        ),
      });
    }

    if (store.selectedScenario && store.rankedTemplates.length > 0) {
      items.push({
        key: 'step-template',
        label: <Space><Text strong>③ {t('workflowAgent.selectTemplate')}</Text>{store.selectedTemplate && <Tag color="purple">{store.selectedTemplate.name}</Tag>}</Space>,
        children: store.selectedTemplate ? (
          <Text type="secondary">{t('workflowAgent.selected')}：{store.selectedTemplate.name}</Text>
        ) : (
          <div>
            <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>{t('workflowAgent.recommendedTemplates', { count: store.rankedTemplates.length })}</Text>
            {store.rankedTemplates.map((tpl, idx) => (
              <Card key={tpl.id} size="small" hoverable style={{ cursor: 'pointer', marginBottom: 8 }} onClick={() => handleSelectTemplate(tpl)}>
                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                  <Space>
                    {idx === 0 && <Tag color="red">{t('workflowAgent.bestMatch')}</Tag>}
                    {idx > 0 && idx < 3 && <Tag color="orange">{t('workflowAgent.recommended')}</Tag>}
                    <Text strong>{tpl.name}</Text>
                    <Tag color="purple">{tpl.display_category}</Tag>
                  </Space>
                  <Text type="secondary" style={{ fontSize: 12 }}>{tpl.description || t('workflowAgent.noDescription')}</Text>
                  {tpl.relevanceScore > 0 && <Progress percent={Math.min(tpl.relevanceScore, 100)} size="small" showInfo={false}
                    strokeColor={idx === 0 ? '#ff4d4f' : idx < 3 ? '#faad14' : '#1890ff'} />}
                </Space>
              </Card>
            ))}
          </div>
        ),
      });
    }

    if (store.selectedTemplate && store.combinations.length > 0) {
      items.push({
        key: 'step-combo',
        label: (
          <Space><Text strong>④ {t('workflowAgent.solutionRecommendation')}</Text>
            {store.selectedCombo && <Tag color={store.selectedCombo.profile === 'high-accuracy' ? 'green' : store.selectedCombo.profile === 'balanced' ? 'blue' : 'orange'}>
              {store.selectedCombo.profile === 'high-accuracy' ? t('workflowAgent.highAccuracy') : store.selectedCombo.profile === 'balanced' ? t('workflowAgent.balanced') : t('workflowAgent.lowLatency')}
            </Tag>}
          </Space>
        ),
        children: store.selectedCombo ? (
          <Text type="secondary">{t('workflowAgent.selected')}：{store.selectedCombo.profile === 'high-accuracy' ? t('workflowAgent.highAccuracySolution') : store.selectedCombo.profile === 'balanced' ? t('workflowAgent.balancedSolution') : t('workflowAgent.lowLatencySolution')}（{store.selectedCombo.overall_confidence}%）</Text>
        ) : (
          <div>
            {store.combinations.map((c, idx) => {
              const color = c.profile === 'high-accuracy' ? '#52c41a' : c.profile === 'balanced' ? '#1890ff' : '#fa8c16';
              const label = c.profile === 'high-accuracy' ? t('workflowAgent.highAccuracySolution') : c.profile === 'balanced' ? t('workflowAgent.balancedSolution') : t('workflowAgent.lowLatencySolution');
              return (
                <Card key={c.combination_id} size="small" style={{ marginBottom: 8, borderLeft: `3px solid ${color}` }}
                  title={<Space><Tag color={c.profile === 'high-accuracy' ? 'green' : c.profile === 'balanced' ? 'blue' : 'orange'}>{label}</Tag>
                    {idx === 0 && <Tag color="red">{t('workflowAgent.recommended')}</Tag>}
                    <Text type="secondary" style={{ fontSize: 12 }}>{t('workflowAgent.confidence')} {c.overall_confidence}%</Text></Space>}
                  extra={<Button type="primary" size="small" onClick={() => handleSelectCombo(c)}>{t('workflowAgent.select')}</Button>}>
                  {c.layers.map((layer) => (
                    <div key={layer.layer_name} style={{ marginBottom: 4 }}>
                      <Text strong style={{ fontSize: 12 }}>{layer.layer_name}：</Text>
                      {layer.algorithms.map((a) => <Tag key={a.algorithm_id} style={{ marginBottom: 2 }}>{a.algorithm_name}</Tag>)}
                    </div>
                  ))}
                </Card>
              );
            })}
          </div>
        ),
      });
    }

    if (store.generatedWorkflow) {
      const vr = store.validationResult;
      items.push({
        key: 'step-generate',
        label: (
          <Space>
            <Text strong>⑤ {t('workflowAgent.generateTemplate')}</Text>
            <Tag color="blue">{t('workflowAgent.nodes')}: {store.generatedWorkflow.node_count}</Tag>
            <Tag color="green">{t('workflowAgent.connections')}: {store.generatedWorkflow.edge_count}</Tag>
            {vr && <Tag color={vr.readiness_score >= 80 ? 'green' : vr.readiness_score >= 50 ? 'orange' : 'red'}>{t('workflowAgent.readiness')}: {vr.readiness_score}%</Tag>}
          </Space>
        ),
        children: (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Text style={{ fontSize: 13 }}>{store.generatedWorkflow.generation_summary}</Text>
            <Space><Tag color="blue">{t('workflowAgent.nodes')}: {store.generatedWorkflow.node_count}</Tag><Tag color="green">{t('workflowAgent.connections')}: {store.generatedWorkflow.edge_count}</Tag><Tag>{t('workflowAgent.duration')}: {store.generatedWorkflow.processing_time_ms}ms</Tag></Space>
            <Button type="primary" icon={<EditOutlined />} onClick={handleOpenInEditor} loading={openingInEditor} style={{ marginTop: 4 }}>{t('workflowAgent.openInEditor')}</Button>
          </Space>
        ),
      });
    }

    return items;
  })();
  // @AI_GENERATED: end

  // @AI_GENERATED: Kiro v1.0
  return (
    <Layout style={{ height: '100%', background: '#f5f5f5' }}>
      <Sider width={460} style={{ background: '#fff', padding: 16, overflowY: 'auto' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
          <Title level={4} style={{ margin: 0 }}><RocketOutlined /> {t('workflowAgent.title')}</Title>
          <Button size="small" onClick={() => navigate('/workflow-agent/history')}>{t('workflowAgent.historyRecords')}</Button>
        </Space>

        <Collapse activeKey={store.activeKeys} onChange={(keys) => store.setActiveKeys(keys as string[])}
          items={collapseItems} size="small" style={{ background: '#fff' }} />

        {loading && <Spin style={{ display: 'block', marginTop: 16 }} />}

        {store.errorInfo && !loading && (() => {
          const isInfo = store.errorInfo.severity === 'info';
          const borderColor = isInfo ? '#1890ff' : '#ff4d4f';
          return (
            <Card size="small" style={{ marginTop: 12, borderLeft: `3px solid ${borderColor}` }}
              title={<Space>{isInfo ? <InfoCircleOutlined style={{ color: '#1890ff' }} /> : <WarningOutlined style={{ color: '#ff4d4f' }} />}
                <Text type={isInfo ? 'secondary' : 'danger'}>{isInfo ? t('workflowAgent.hint') : t('workflowAgent.operationFailed')}</Text></Space>}>
              <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>{store.errorInfo.message}</Text>
              <Space>
                <Button type="primary" size="small" onClick={handleRetry}>{t('workflowAgent.retry')}</Button>
                {store.errorInfo.step === 'validating' && <Button size="small" onClick={handleSkipError}>{t('workflowAgent.skipValidation')}</Button>}
                <Button size="small" onClick={handleReset}>{t('workflowAgent.restart')}</Button>
              </Space>
            </Card>
          );
        })()}
      </Sider>

      <Content style={{ padding: 16, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
        {store.previewNodes.length > 0 && canvasReady ? (
          <div style={{ flex: 1, minHeight: 400, border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
            <EnhancedCanvasWithProvider nodes={store.previewNodes} edges={store.previewEdges}
              onNodesChange={store.setPreviewNodes} onEdgesChange={store.setPreviewEdges}
              onNodeSelect={() => {}} readOnly />
          </div>
        ) : store.previewNodes.length > 0 ? (
          <div style={{ flex: 1, minHeight: 400, border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Spin />
          </div>
        ) : (
          <Empty description={t('workflowAgent.waitingGenerate')} style={{ marginTop: 80 }} />
        )}
      </Content>
    </Layout>
  );
};

export default WorkflowAgentPage;
// @AI_GENERATED: end
