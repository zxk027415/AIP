import React, { useEffect, useMemo, useState } from 'react';
import { Button, Empty, Modal, Spin, Steps } from 'antd';
import { CheckOutlined } from '@ant-design/icons';
import { enhancedWorkflowApi } from '../services/workflowEnhancedApi';
import { industryApi } from '../services/industryApi';
import type { EnhancedWorkflowSummary } from '../types/workflow-enhanced';
import type { IndustryScenario } from '../types/industry';

// ─── Props ───────────────────────────────────────────────────────────────────

interface CreateWorkflowWizardProps {
  open: boolean;
  onClose: () => void;
  /** Called when creation is confirmed. workflowId is the selected template ID, or undefined for blank. */
  onCreated: (workflowId?: string) => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

const CreateWorkflowWizard: React.FC<CreateWorkflowWizardProps> = ({ open, onClose, onCreated }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [selectedScenario, setSelectedScenario] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<IndustryScenario[]>([]);
  const [templates, setTemplates] = useState<EnhancedWorkflowSummary[]>([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);

  // Load scenarios on mount
  useEffect(() => {
    if (!open) return;
    industryApi.getScenarios().then(setScenarios).catch(() => setScenarios([]));
  }, [open]);

  // Load templates when entering step 2
  useEffect(() => {
    if (currentStep !== 1 || !selectedScenario) return;
    setLoadingTemplates(true);
    enhancedWorkflowApi
      .listWorkflowSummaries()
      .then((all) => {
        setTemplates(all.filter((t) => t.scenario_id === selectedScenario));
      })
      .catch(() => setTemplates([]))
      .finally(() => setLoadingTemplates(false));
  }, [currentStep, selectedScenario]);

  const handleClose = () => {
    setCurrentStep(0);
    setSelectedScenario(null);
    setSelectedTemplate(null);
    onClose();
  };

  const handleNext = () => {
    if (currentStep === 0 && selectedScenario) {
      setCurrentStep(1);
      setSelectedTemplate(null);
    } else if (currentStep === 1 && selectedTemplate) {
      // User selected a template — open editor with that template
      onCreated(selectedTemplate);
      resetState();
    }
  };

  const handleBack = () => {
    if (currentStep === 1) {
      setCurrentStep(0);
      setSelectedTemplate(null);
    }
  };

  const handleBlankCreate = () => {
    onCreated(undefined);
    resetState();
  };

  const resetState = () => {
    setCurrentStep(0);
    setSelectedScenario(null);
    setSelectedTemplate(null);
  };

  // Filter scenarios to only show those that have templates
  const scenariosWithData = useMemo(() => {
    // Show all scenarios from the industry_scenarios.json — even if no template matches yet
    return scenarios.slice(0, 6); // Max 6 for 2x3 grid per design spec
  }, [scenarios]);

  return (
    <Modal
      open={open}
      onCancel={handleClose}
      title={<span style={{ fontSize: 18, fontWeight: 600 }}>新建算法工作流</span>}
      width={680}
      footer={null}
      destroyOnClose
      styles={{ body: { padding: '0 24px 24px' } }}
    >
      {/* Steps indicator */}
      <Steps
        current={currentStep}
        size="small"
        style={{ marginBottom: 20, padding: '0 32px' }}
        items={[
          { title: '选择场景' },
          { title: '选择模板' },
          { title: '开始创建' },
        ]}
      />

      {/* Step 1: Select scenario */}
      {currentStep === 0 && (
        <>
          <p style={{ fontSize: 14, color: '#8c8c8c', margin: '0 0 16px' }}>
            选择业务场景，系统将推荐适用的算法模板
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16, overflow: 'hidden' }}>
            {scenariosWithData.map((scenario) => {
              const isSelected = selectedScenario === scenario.id;
              return (
                <ScenarioCard
                  key={scenario.id}
                  name={scenario.name}
                  description={scenario.description}
                  selected={isSelected}
                  onClick={() => setSelectedScenario(scenario.id)}
                />
              );
            })}
          </div>
          <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12, marginBottom: 16 }}>
            <a onClick={handleBlankCreate} style={{ fontSize: 13, color: '#8c8c8c' }}>
              跳过场景选择，直接空白创建 →
            </a>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Button onClick={handleClose}>取消</Button>
            <Button type="primary" disabled={!selectedScenario} onClick={handleNext}>
              下一步
            </Button>
          </div>
        </>
      )}

      {/* Step 2: Select template */}
      {currentStep === 1 && (
        <>
          <p style={{ fontSize: 14, color: '#8c8c8c', margin: '0 0 16px' }}>
            选择一个现有模板作为基础，或直接空白创建
          </p>
          {loadingTemplates ? (
            <div style={{ padding: '40px 0', textAlign: 'center' }}>
              <Spin />
            </div>
          ) : templates.length === 0 ? (
            <div style={{ padding: '24px 0', textAlign: 'center' }}>
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="该场景下暂无可用模板"
              />
              <p style={{ fontSize: 13, color: '#8c8c8c', margin: '8px 0 0' }}>
                可以直接空白创建，后续再关联场景
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16, maxHeight: 320, overflowY: 'auto' }}>
              {templates.map((tpl) => {
                const isSelected = selectedTemplate === tpl.id;
                return (
                  <TemplateCard
                    key={tpl.id}
                    name={tpl.name}
                    description={tpl.description}
                    nodeCount={tpl.nodeCount}
                    selected={isSelected}
                    onClick={() => setSelectedTemplate(tpl.id)}
                  />
                );
              })}
            </div>
          )}
          <div style={{ borderTop: '1px solid #f0f0f0', paddingTop: 12, marginBottom: 16 }}>
            <a onClick={handleBlankCreate} style={{ fontSize: 13, color: '#8c8c8c' }}>
              跳过模板选择，直接空白创建 →
            </a>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <Button onClick={handleBack}>上一步</Button>
            <Button type="primary" disabled={!selectedTemplate} onClick={handleNext}>
              基于此模板创建
            </Button>
          </div>
        </>
      )}
    </Modal>
  );
};

// ─── Sub-components ──────────────────────────────────────────────────────────

function ScenarioCard({ name, description, selected, onClick }: {
  name: string;
  description: string;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        position: 'relative',
        border: selected ? '2px solid #1677ff' : '1px solid #e8e8e8',
        borderRadius: 8,
        padding: '14px 16px',
        cursor: 'pointer',
        background: selected ? '#f0f7ff' : '#fff',
        transition: 'border-color 0.2s, background 0.2s',
        minWidth: 0,        // 允许 flex/grid 子元素收缩
        overflow: 'hidden', // 防止内容撑出边界
      }}
    >
      {selected && (
        <span style={{
          position: 'absolute', top: 8, right: 8,
          width: 18, height: 18, borderRadius: '50%',
          background: '#1677ff', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <CheckOutlined style={{ color: '#fff', fontSize: 10 }} />
        </span>
      )}
      <div style={{ fontWeight: 500, fontSize: 14, color: '#1f1f1f', marginBottom: 4 }}>{name}</div>
      <div style={{
        fontSize: 12,
        color: '#8c8c8c',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        display: '-webkit-box',
        WebkitLineClamp: 2,       // 最多两行，超出省略
        WebkitBoxOrient: 'vertical',
        whiteSpace: 'normal',     // 允许换行（配合 line-clamp 使用）
        lineHeight: '1.5',
        maxHeight: '36px',        // 两行高度兜底
      }}>
        {description}
      </div>
    </div>
  );
}

function TemplateCard({ name, description, nodeCount, selected, onClick }: {
  name: string;
  description?: string;
  nodeCount: number;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <div
      onClick={onClick}
      style={{
        border: selected ? '2px solid #1677ff' : '1px solid #e8e8e8',
        borderRadius: 8,
        padding: '12px 16px',
        cursor: 'pointer',
        background: selected ? '#f0f7ff' : '#fff',
        transition: 'border-color 0.2s, background 0.2s',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 500, fontSize: 14, color: '#1f1f1f' }}>{name}</span>
        <span style={{ fontSize: 11, color: '#8c8c8c' }}>{nodeCount} 个节点</span>
      </div>
      {description && (
        <div style={{ fontSize: 12, color: '#8c8c8c', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {description}
        </div>
      )}
    </div>
  );
}

export default CreateWorkflowWizard;
