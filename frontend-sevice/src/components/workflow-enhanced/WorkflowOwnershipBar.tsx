// @AI_GENERATED
/**
 * 工作流归属栏（design §35.4）。
 *
 * 读取并显示工作流的四层主干归属（scenario_id 行业场景 / solution_id 算法方案）；
 * 缺失时显示"未归属"并提供一键归属，而不是静默留空。
 * 已保存工作流：一键归属通过 PUT /workflows/enhanced/{id} 写入 scenario_id/solution_id。
 * 未保存空白画布：归属先本地记录并回调，待工作流保存后随之写入（诚实提示）。
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Button, Modal, Select, Space, Tag, Tooltip, message } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { industryApi } from '../../services/industryApi';
import type { IndustryTemplate } from '../../services/industryApi';
import type { IndustryScenario } from '../../types/industry';
import { enhancedWorkflowApi } from '../../services/workflowEnhancedApi';

interface WorkflowOwnershipBarProps {
  /** 当前工作流 ID；为 null 表示尚未保存的空白画布。 */
  workflowId: string | null;
  /** 已加载工作流 / 预填带入的归属。 */
  scenarioId?: string;
  solutionId?: string;
  /** 归属确定后回调（供编辑器在保存时一并写入未保存画布）。 */
  onAssigned?: (scenarioId: string, solutionId: string) => void;
}

const WorkflowOwnershipBar: React.FC<WorkflowOwnershipBarProps> = ({
  workflowId,
  scenarioId,
  solutionId,
  onAssigned,
}) => {
  const [scenarios, setScenarios] = useState<IndustryScenario[]>([]);
  const [curSolutions, setCurSolutions] = useState<IndustryTemplate[]>([]);
  const [draftSolutions, setDraftSolutions] = useState<IndustryTemplate[]>([]);

  const [curScenario, setCurScenario] = useState<string | undefined>(scenarioId);
  const [curSolution, setCurSolution] = useState<string | undefined>(solutionId);

  const [modalOpen, setModalOpen] = useState(false);
  const [draftScenario, setDraftScenario] = useState<string | undefined>(scenarioId);
  const [draftSolution, setDraftSolution] = useState<string | undefined>(solutionId);
  const [saving, setSaving] = useState(false);

  // props 变化（工作流重载）时重新同步显示。
  useEffect(() => setCurScenario(scenarioId), [scenarioId]);
  useEffect(() => setCurSolution(solutionId), [solutionId]);

  useEffect(() => {
    industryApi.getScenarios().then(setScenarios).catch(() => setScenarios([]));
  }, []);

  // 当前场景下的方案（用于显示方案名）。
  useEffect(() => {
    if (!curScenario) {
      setCurSolutions([]);
      return;
    }
    industryApi.getTemplates(curScenario).then(setCurSolutions).catch(() => setCurSolutions([]));
  }, [curScenario]);

  // 归属弹窗内草稿场景下的方案。
  useEffect(() => {
    if (!draftScenario) {
      setDraftSolutions([]);
      return;
    }
    industryApi
      .getTemplates(draftScenario)
      .then((list) => {
        setDraftSolutions(list);
        setDraftSolution((prev) => (prev && list.some((s) => s.id === prev) ? prev : undefined));
      })
      .catch(() => setDraftSolutions([]));
  }, [draftScenario]);

  const scenarioName = useMemo(
    () => scenarios.find((s) => s.id === curScenario)?.name || curScenario,
    [scenarios, curScenario],
  );
  const solutionName = useMemo(
    () => curSolutions.find((s) => s.id === curSolution)?.name || curSolution,
    [curSolutions, curSolution],
  );

  const hasOwnership = !!curScenario && !!curSolution;

  const openModal = () => {
    setDraftScenario(curScenario);
    setDraftSolution(curSolution);
    setModalOpen(true);
  };

  const handleAssign = async () => {
    if (!draftScenario || !draftSolution) return;
    if (!workflowId) {
      // 未保存画布：本地记录 + 回调，随保存写入。
      setCurScenario(draftScenario);
      setCurSolution(draftSolution);
      onAssigned?.(draftScenario, draftSolution);
      setModalOpen(false);
      message.info('已记录归属，保存工作流后写入');
      return;
    }
    try {
      setSaving(true);
      await enhancedWorkflowApi.updateWorkflow(workflowId, {
        scenario_id: draftScenario,
        solution_id: draftSolution,
      });
      setCurScenario(draftScenario);
      setCurSolution(draftSolution);
      onAssigned?.(draftScenario, draftSolution);
      setModalOpen(false);
      message.success('已写入归属');
    } catch {
      message.error('归属写入失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Space size={6} align="center">
        <span style={{ fontSize: 12, color: '#8c8c8c' }}>归属</span>
        {hasOwnership ? (
          <>
            <Tag color="blue" style={{ marginInlineEnd: 0 }}>
              场景：{scenarioName}
            </Tag>
            <Tag color="geekblue" style={{ marginInlineEnd: 0 }}>
              方案：{solutionName}
            </Tag>
          </>
        ) : (
          <Tag color="warning" style={{ marginInlineEnd: 0 }}>
            未归属
          </Tag>
        )}
        <Tooltip title={workflowId ? '设置 / 修改归属并写入工作流' : '保存工作流后写入归属'}>
          <Button size="small" type="link" icon={<EditOutlined />} onClick={openModal} style={{ paddingInline: 4 }}>
            {hasOwnership ? '修改归属' : '一键归属'}
          </Button>
        </Tooltip>
      </Space>

      <Modal
        open={modalOpen}
        title="设置工作流归属"
        okText={workflowId ? '写入归属' : '记录归属'}
        cancelText="取消"
        confirmLoading={saving}
        okButtonProps={{ disabled: !draftScenario || !draftSolution }}
        onOk={handleAssign}
        onCancel={() => setModalOpen(false)}
        destroyOnClose
      >
        <p style={{ fontSize: 13, color: '#8c8c8c', marginTop: 0 }}>
          归属写入工作流自身，使算法管理列表的"所属场景 / 方案"不再依赖名称猜测。
        </p>
        <Space direction="vertical" size={14} style={{ width: '100%' }}>
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>行业场景</div>
            <Select
              showSearch
              allowClear
              placeholder="搜索并选择行业场景"
              style={{ width: '100%' }}
              value={draftScenario}
              onChange={(v) => setDraftScenario(v)}
              optionFilterProp="label"
              options={scenarios.map((s) => ({ value: s.id, label: s.name }))}
            />
          </div>
          <div>
            <div style={{ fontSize: 13, marginBottom: 6 }}>算法方案</div>
            <Select
              showSearch
              allowClear
              placeholder={draftScenario ? '搜索并选择算法方案' : '请先选择行业场景'}
              style={{ width: '100%' }}
              value={draftSolution}
              disabled={!draftScenario}
              onChange={(v) => setDraftSolution(v)}
              optionFilterProp="label"
              options={draftSolutions.map((s) => ({ value: s.id, label: s.name }))}
              notFoundContent={draftScenario ? '该场景下暂无方案' : '请先选择行业场景'}
            />
          </div>
        </Space>
      </Modal>
    </>
  );
};

export default WorkflowOwnershipBar;
// @AI_GENERATED: end
