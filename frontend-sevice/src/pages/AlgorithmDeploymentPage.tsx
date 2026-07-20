// @AI_GENERATED: algorithm-deployment-refactor 9.1/9.2/9.3 + 阶段3
/**
 * AlgorithmDeploymentPage.tsx — 算法部署统一入口页面（四 Tab）
 *
 * Tab 列表：
 *   1. 模型管理（?tab=model）  — 生产/影子/预上线三区布局，切换/回滚/配置
 *   2. 数据管线（?tab=pipeline）— 管线启停
 *   3. 定时调度（?tab=scheduler）— cron 可编辑可触发
 *   4. 预上线（?tab=prelaunch）  — 入池/观察进度/手动毕业
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Descriptions, Row, Select, Space, Spin, Tabs, Tag, Typography, message } from 'antd';
import {
  ApartmentOutlined,
  ClockCircleOutlined,
  DeploymentUnitOutlined,
  ExperimentOutlined,
  RocketOutlined,
} from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import ModelManagementTab from './deployment/ModelManagementTab';
import PipelineTab from './deployment/PipelineTab';
import SchedulerTab from './deployment/SchedulerTab';
import PrelaunchTab from './deployment/PrelaunchTab';
import './deployment/algorithmDeploymentWorkspace.css';
// @AI_GENERATED: pv_fault 专用部署视图依赖
import { cumulativeTrainingApi, trainingWorkspaceApi } from '../services/iterativeLabelingApi';
// @AI_GENERATED: end

const { Title, Paragraph } = Typography;

type TabKey = 'model' | 'pipeline' | 'scheduler' | 'prelaunch';
const VALID_TABS: readonly TabKey[] = ['model', 'pipeline', 'scheduler', 'prelaunch'] as const;
const DEFAULT_TAB: TabKey = 'model';

// @AI_GENERATED: 部署页槽位选项和受控选择器
const DEPLOYMENT_SLOT_OPTIONS = [
  { label: 'load_forecast（负荷预测）', value: 'load_forecast' },
  { label: 'pv_fault（光伏故障诊断）', value: 'pv_fault' },
  { label: 'default（默认）', value: 'default' },
];
// @AI_GENERATED: end

const AlgorithmDeploymentPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  // @AI_GENERATED: 槽位受控 — URL ?slot= 参数驱动
  const storySlot = searchParams.get('slot')?.trim() || 'load_forecast';

  const handleSlotChange = (value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('slot', value);
    setSearchParams(next, { replace: true });
  };
  // @AI_GENERATED: end

  const activeTab: TabKey = useMemo(() => {
    const raw = searchParams.get('tab');
    return raw && (VALID_TABS as readonly string[]).includes(raw) ? (raw as TabKey) : DEFAULT_TAB;
  }, [searchParams]);

  const handleTabChange = (key: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('tab', key);
    setSearchParams(next, { replace: false });
  };

  return (
    <div className="algorithm-deployment-workspace">
      <div className="algorithm-deployment-container">
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Card className="deployment-page-header" bordered={false}>
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                <Space align="center" size={12}>
                  <RocketOutlined style={{ fontSize: 22, color: '#1677ff' }} />
                  <Title level={3} style={{ margin: 0 }}>算法部署</Title>
                  <Tag color="blue">模型全生命周期管理</Tag>
                </Space>
                {/* @AI_GENERATED: 槽位选择器 */}
                <Space size={8}>
                  <span style={{ fontSize: 13, color: '#64748b' }}>槽位</span>
                  <Select
                    value={storySlot}
                    onChange={handleSlotChange}
                    options={DEPLOYMENT_SLOT_OPTIONS}
                    style={{ width: 240 }}
                    size="middle"
                  />
                </Space>
                {/* @AI_GENERATED: end */}
              </div>
              <Paragraph type="secondary" style={{ marginBottom: 0, maxWidth: 900 }}>
                按槽位管理模型上线、生产/影子/预上线切换、数据管线和定时调度。
              </Paragraph>
            </Space>
          </Card>

          <Card className="deployment-page-tabs" bordered={false} bodyStyle={{ padding: '8px 16px 16px' }}>
            <Tabs
              activeKey={activeTab}
              onChange={handleTabChange}
              destroyInactiveTabPane={false}
              items={storySlot === 'pv_fault' ? [
                {
                  key: 'model',
                  label: <Space size={6}><DeploymentUnitOutlined />模型状态</Space>,
                  children: <PvFaultDeploymentView />,
                },
                {
                  key: 'scheduler',
                  label: <Space size={6}><ClockCircleOutlined />定时调度</Space>,
                  children: <SchedulerTab storySlot={storySlot} />,
                },
              ] : [
                {
                  key: 'model',
                  label: <Space size={6}><DeploymentUnitOutlined />模型管理</Space>,
                  children: <ModelManagementTab storySlot={storySlot} />,
                },
                {
                  key: 'pipeline',
                  label: <Space size={6}><ApartmentOutlined />数据管线</Space>,
                  children: <PipelineTab />,
                },
                {
                  key: 'scheduler',
                  label: <Space size={6}><ClockCircleOutlined />定时调度</Space>,
                  children: <SchedulerTab storySlot={storySlot} />,
                },
                {
                  key: 'prelaunch',
                  label: <Space size={6}><ExperimentOutlined />预上线</Space>,
                  children: <PrelaunchTab />,
                },
              ]}
            />
          </Card>
        </Space>
      </div>
    </div>
  );
};

// @AI_GENERATED: 光伏故障诊断部署专用视图 — 模型版本、累计训练、标签、重训
const PvFaultDeploymentView: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState<Record<string, any> | null>(null);
  const [labels, setLabels] = useState<Array<Record<string, any>>>([]);
  const [retrainRunning, setRetrainRunning] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ctState, labelsResp] = await Promise.all([
        cumulativeTrainingApi.getState('pv_fault'),
        fetch('/api/iterative-labeling/label-registry?slot=pv_fault').then(r => r.json()),
      ]);
      setState(ctState as Record<string, any>);
      setLabels(labelsResp?.labels ?? []);
    } catch {
      setState(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleRetrain = async () => {
    const requestId = state?.latest_retrain_request?.request_id;
    if (!requestId || state?.latest_retrain_request?.status !== 'queued') {
      messageApi.warning('当前没有可执行的 queued 重训请求');
      return;
    }
    setRetrainRunning(true);
    try {
      await cumulativeTrainingApi.runRetrainRequest(requestId, 'pv_fault');
      messageApi.success('重训完成（模型未自动发布，需在人工标注页确认后使用）');
      await load();
    } catch (err: any) {
      messageApi.error(err?.response?.data?.detail || '重训失败');
    } finally {
      setRetrainRunning(false);
    }
  };

  if (loading && !state) return <Spin style={{ display: 'block', margin: '60px auto' }} />;

  const latestRequest = state?.latest_retrain_request;
  const latestSnapshot = state?.latest_snapshot;
  const modelRef = state?.latest_completed_model_ref;

  return (
    <div>
      {contextHolder}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card size="small" title="当前模型与训练集" bordered>
            <Descriptions column={1} size="small" labelStyle={{ width: 140, color: '#64748b' }}>
              <Descriptions.Item label="生产模型">
                {modelRef ? <Tag color="success">{modelRef}</Tag> : <Tag>暂无模型</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="训练集快照">
                {latestSnapshot?.snapshot_id ? <Typography.Text code style={{ fontSize: 11 }}>{latestSnapshot.snapshot_id}</Typography.Text> : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="快照样本数">{latestSnapshot?.sample_count ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="快照标签类别">{latestSnapshot?.label_count ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="有效真值单元">{state?.effective_labeled_unit_count ?? 0}</Descriptions.Item>
              <Descriptions.Item label="累计新增变更">{state?.pending_change_count ?? 0} / 阈值 {state?.retrain_label_threshold ?? 20}</Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card size="small" title="已有标签" bordered>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {labels.length > 0 ? labels.map((l: any) => (
                <Tag key={l.label_id} color="blue" style={{ margin: 0 }}>
                  {l.label_name}（{l.label_id}）
                </Tag>
              )) : <Typography.Text type="secondary">暂无标签</Typography.Text>}
            </div>
          </Card>

          <Card size="small" title="重训控制" bordered style={{ marginTop: 12 }}>
            <Descriptions column={1} size="small" labelStyle={{ width: 120, color: '#64748b' }}>
              <Descriptions.Item label="重训请求">
                {latestRequest?.request_id ? <Typography.Text code style={{ fontSize: 11 }}>{latestRequest.request_id}</Typography.Text> : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="状态">
                {latestRequest?.status === 'completed' ? <Tag color="success">已完成</Tag>
                  : latestRequest?.status === 'queued' ? <Tag color="processing">等待执行</Tag>
                  : latestRequest?.status === 'running' ? <Tag color="processing">训练中</Tag>
                  : <Tag>未创建</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="距下次自动冻结">{state?.next_retrain_in ?? '—'} 次变更</Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 12, textAlign: 'right' }}>
              <Button
                type="primary"
                loading={retrainRunning}
                disabled={latestRequest?.status !== 'queued'}
                onClick={handleRetrain}
              >
                立即执行重训
              </Button>
            </div>
          </Card>
        </Col>
      </Row>

      <div style={{ marginTop: 16, padding: '8px 12px', background: '#fafafa', borderRadius: 6, fontSize: 12, color: '#8c8c8c' }}>
        光伏故障诊断不使用 shadow/production 部署体系。模型通过累计训练集达到阈值后自动冻结快照，人工确认执行重训后产生新模型。
        新模型由定时预测任务自动使用。
      </div>
    </div>
  );
};
// @AI_GENERATED: end

export default AlgorithmDeploymentPage;
// @AI_GENERATED: end
