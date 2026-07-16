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
import React, { useMemo } from 'react';
import { Card, Select, Space, Tabs, Tag, Typography } from 'antd';
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
              items={[
                {
                  key: 'model',
                  label: <Space size={6}><DeploymentUnitOutlined />模型管理</Space>,
                  // @AI_GENERATED: 透传 storySlot 以便 ModelManagementTab 可选择性聚焦
                  children: <ModelManagementTab storySlot={storySlot} />,
                  // @AI_GENERATED: end
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

export default AlgorithmDeploymentPage;
// @AI_GENERATED: end
